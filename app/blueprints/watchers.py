"""Browser routes for session-owned change-detection watchers."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from flask import Blueprint, jsonify, request

from config import CFG
from core import database
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from extensions import limiter
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload
from services.scheduler.commands import ScheduleCommandValidationError, validate_schedule_command
from services.scheduler.cron import ScheduleCronError
from services.scheduler.dispatch import fire_schedule
from services.scheduler.service import ScheduleError, coerce_schedule_bool, get_schedule
from services.session.variables import SessionVariableError
from services.watchers.serialization import watcher_fire_payload, watcher_payload
from services.watchers.service import (
    WatcherError,
    accept_baseline,
    create_watcher,
    delete_watcher,
    get_watcher,
    list_for_session,
    list_watcher_fires,
    pause_watcher,
    resume_watcher,
    update_watcher,
)

log = logging.getLogger("shell")

watchers_bp = Blueprint("watchers", __name__)


class WatcherRouteError(ValueError):
    """Raised when watcher route input is invalid."""


class WatcherNotFound(WatcherRouteError):
    """Raised when a watcher is not visible to the current session."""


class BaselineRunNotFound(WatcherRouteError):
    """Raised when a baseline run is not visible to the current session."""


class BaselineRunNotCompleted(WatcherRouteError):
    """Raised when a baseline run is not complete enough to watch."""


def _watcher_write_limit():
    return f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"


def _json_body() -> tuple[dict[str, Any] | None, Any]:
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    return data, None


def _required_token_session():
    session_id = get_session_id()
    if not session_id:
        return "", (jsonify({"error": "session_required"}), 401)
    if not str(session_id).startswith("tok_"):
        return "", (jsonify({"error": "session_token_required"}), 401)
    return session_id, None


def _response_status(response) -> int:
    if isinstance(response, tuple) and len(response) > 1:
        try:
            return int(response[1])
        except (TypeError, ValueError):
            return 400
    return 400


def _watcher_log_payload(watcher=None, *, session_id: str = "", source: str = "browser", **extra) -> dict[str, object]:
    payload: dict[str, object] = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id or getattr(watcher, "session_token", "")),
        "source": source,
    }
    if watcher is not None:
        payload.update({
            "watcher_id": watcher.id,
            "schedule_id": watcher.schedule_id,
            "baseline_run_id": watcher.baseline_run_id,
            "last_run_id": watcher.last_run_id,
            "state": watcher.state,
        })
    payload.update(extra)
    return payload


def _watcher_error_response(exc):
    if isinstance(exc, WatcherNotFound):
        return jsonify({"error": "watcher_not_found"}), 404
    if isinstance(exc, BaselineRunNotFound):
        return jsonify({"error": "baseline_run_not_found"}), 404
    if isinstance(exc, BaselineRunNotCompleted):
        return jsonify({"error": "invalid_baseline", "message": str(exc)}), 400
    if isinstance(exc, WatcherError):
        status = 409 if "quota" in str(exc).lower() else 400
        return jsonify({"error": "invalid_watcher", "message": str(exc)}), status
    if isinstance(exc, (ScheduleError, ScheduleCronError)):
        return jsonify({"error": "invalid_watcher", "message": str(exc)}), 400
    if isinstance(exc, ScheduleCommandValidationError):
        return jsonify({"error": "invalid_command", "message": str(exc)}), 400
    if isinstance(exc, SessionVariableError):
        return jsonify({"error": "invalid_command", "message": str(exc)}), 400
    if isinstance(exc, ValueError):
        return jsonify({"error": "invalid_watcher", "message": str(exc)}), 400
    return jsonify({"error": "invalid_watcher"}), 400


def _log_watcher_rejected(action: str, session_id: str, exc: Exception, response, watcher_id: str = "") -> None:
    log.warning("WATCHER_REQUEST_REJECTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "source": "browser",
        "action": action,
        "watcher_id": watcher_id,
        "status": _response_status(response),
        "error": str(exc),
    })


def _watcher_for_session_or_404(watcher_id: str, session_id: str, *, conn=None):
    watcher = get_watcher(watcher_id, conn=conn)
    if watcher is None or watcher.session_token != session_id:
        raise WatcherNotFound("watcher not found")
    return watcher


def _baseline_run_for_session_or_error(run_id: str, session_id: str, *, conn=None) -> dict[str, Any]:
    baseline_id = str(run_id or "").strip()
    if not baseline_id:
        raise BaselineRunNotFound("baseline run not found")
    assert conn is not None
    row = conn.execute(
        "SELECT id, session_id, command, finished FROM runs WHERE id = ? AND session_id = ?",
        (baseline_id, session_id),
    ).fetchone()
    if row is None:
        raise BaselineRunNotFound("baseline run not found")
    finished = str(row["finished"] if isinstance(row, dict) else row["finished"] or "").strip()
    if not finished:
        raise BaselineRunNotCompleted("baseline run must be completed")
    return dict(row)


def _baseline_mode_from_create(data: dict[str, Any]) -> str:
    requested = str(data.get("baseline_mode") or "").strip().lower().replace("-", "_")
    if requested in {"first_run", "first"}:
        return "first_run"
    if requested in {"existing_run", "existing", "run"}:
        return "existing_run"
    return "existing_run" if str(data.get("baseline_run_id") or "").strip() else "first_run"


def _schedule_for_watcher(watcher, *, conn=None):
    schedule = get_schedule(watcher.schedule_id, conn=conn)
    if schedule is None:
        raise WatcherError("watcher schedule not found")
    return schedule


@watchers_bp.route("/watchers")
def watchers_list():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        with database.db_connect() as conn:
            watchers = list_for_session(session_id, conn=conn)
            schedules = {
                watcher.schedule_id: get_schedule(watcher.schedule_id, conn=conn)
                for watcher in watchers
            }
    except (WatcherError, ScheduleError, ValueError) as exc:
        response = _watcher_error_response(exc)
        _log_watcher_rejected("list", session_id, exc, response)
        return response
    log.debug("WATCHERS_LISTED", extra=_watcher_log_payload(None, session_id=session_id, count=len(watchers)))
    return jsonify({
        "watchers": [
            watcher_payload(watcher, schedule=schedules.get(watcher.schedule_id))
            for watcher in watchers
        ],
    })


@watchers_bp.route("/watchers", methods=["POST"])
@limiter.limit(_watcher_write_limit, key_func=get_session_id)
def watchers_create():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    if data is None:
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        with database.db_connect() as conn:
            baseline_mode = _baseline_mode_from_create(data)
            baseline: dict[str, Any] = {}
            if baseline_mode == "existing_run":
                baseline = _baseline_run_for_session_or_error(str(data.get("baseline_run_id") or ""), session_id, conn=conn)
            command_text = str(data.get("command") or data.get("command_text") or baseline.get("command") or "")
            command = validate_schedule_command(
                command_text,
                session_id,
                workspace_cwd=str(data.get("workspace_cwd") or ""),
            )
            watcher = create_watcher(
                session_id,
                command_text=command,
                baseline_run_id=str(baseline.get("id") or ""),
                cron_expr=data.get("cron_expr"),
                cadence_preset=data.get("cadence_preset"),
                timezone_name=data.get("timezone"),
                label=str(data.get("label") or ""),
                options=data.get("options"),
                enabled=coerce_schedule_bool(data.get("enabled"), default=True),
                conn=conn,
            )
            schedule = _schedule_for_watcher(watcher, conn=conn)
            conn.commit()
    except (
        BaselineRunNotFound,
        BaselineRunNotCompleted,
        WatcherError,
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        SessionVariableError,
        ValueError,
    ) as exc:
        response = _watcher_error_response(exc)
        _log_watcher_rejected("create", session_id, exc, response)
        return response
    log.info("WATCHER_ROUTE_CREATED", extra=_watcher_log_payload(watcher, session_id=session_id))
    return jsonify({"watcher": watcher_payload(watcher, schedule=schedule)}), 201


@watchers_bp.route("/watchers/<watcher_id>", methods=["PATCH"])
@limiter.limit(_watcher_write_limit, key_func=get_session_id)
def watchers_update(watcher_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    if data is None:
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(watcher_id, session_id, conn=conn)
            updates = dict(data)
            if "command" in updates or "command_text" in updates:
                updates["command_text"] = validate_schedule_command(
                    updates.get("command", updates.get("command_text")),
                    session_id,
                    workspace_cwd=str(updates.get("workspace_cwd") or ""),
                )
            if "timezone_name" in updates and "timezone" not in updates:
                updates["timezone"] = updates.pop("timezone_name")
            state = str(updates.pop("state", "") or "").strip().lower()
            enabled_value = updates.get("enabled")
            enabled_update = coerce_schedule_bool(enabled_value) if enabled_value is not None else None
            pause_requested = state == "paused" or updates.pop("pause", False) is True or enabled_update is False
            resume_requested = (
                state in {"ok", "resume", "active"}
                or updates.pop("resume", False) is True
                or enabled_update is True
            )
            updates.pop("enabled", None)
            updates.pop("workspace_cwd", None)
            updates.pop("reason", None)
            updated = update_watcher(watcher.id, updates, conn=conn) if updates else watcher
            if updated is None:
                raise WatcherNotFound("watcher not found")
            if pause_requested:
                updated = pause_watcher(updated.id, str(data.get("reason") or "operator paused"), conn=conn)
            elif resume_requested:
                updated = resume_watcher(updated.id, conn=conn)
            if updated is None:
                raise WatcherNotFound("watcher not found")
            schedule = _schedule_for_watcher(updated, conn=conn)
            conn.commit()
    except (
        WatcherNotFound,
        WatcherError,
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        SessionVariableError,
        ValueError,
    ) as exc:
        response = _watcher_error_response(exc)
        _log_watcher_rejected("update", session_id, exc, response, watcher_id)
        return response
    log.info("WATCHER_ROUTE_UPDATED", extra=_watcher_log_payload(updated, session_id=session_id))
    return jsonify({"watcher": watcher_payload(updated, schedule=schedule)})


@watchers_bp.route("/watchers/<watcher_id>", methods=["DELETE"])
@limiter.limit(_watcher_write_limit, key_func=get_session_id)
def watchers_delete(watcher_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(watcher_id, session_id, conn=conn)
            removed = delete_watcher(watcher.id, conn=conn)
            conn.commit()
    except (WatcherNotFound, WatcherError, ScheduleError, ValueError) as exc:
        response = _watcher_error_response(exc)
        _log_watcher_rejected("delete", session_id, exc, response, watcher_id)
        return response
    log.info("WATCHER_ROUTE_DELETED", extra=_watcher_log_payload(watcher, session_id=session_id, removed=removed))
    return jsonify({"removed": removed})


@watchers_bp.route("/watchers/<watcher_id>/fires")
def watchers_fires(watcher_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        limit = normalize_page_limit(request.args.get("limit"), default=20, maximum=100)
        offset = normalize_page_offset(request.args.get("offset"))
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(watcher_id, session_id, conn=conn)
            fires, total = list_watcher_fires(watcher.id, limit=limit, offset=offset, conn=conn)
    except (WatcherNotFound, WatcherError, ValueError) as exc:
        response = _watcher_error_response(exc)
        _log_watcher_rejected("fires", session_id, exc, response, watcher_id)
        return response
    log.debug("WATCHER_FIRES_LISTED", extra=_watcher_log_payload(
        watcher,
        session_id=session_id,
        count=len(fires),
        total=total,
        limit=limit,
        offset=offset,
    ))
    return jsonify(page_payload("fires", [watcher_fire_payload(fire) for fire in fires], total, limit, offset))


@watchers_bp.route("/watchers/<watcher_id>/accept-baseline", methods=["POST"])
@limiter.limit(_watcher_write_limit, key_func=get_session_id)
def watchers_accept_baseline(watcher_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    data = data or {}
    try:
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(watcher_id, session_id, conn=conn)
            accepted = accept_baseline(watcher.id, run_id=data.get("run_id"), conn=conn)
            if accepted is None:
                raise WatcherNotFound("watcher not found")
            schedule = _schedule_for_watcher(accepted, conn=conn)
            conn.commit()
    except (WatcherNotFound, WatcherError, ScheduleError, ValueError) as exc:
        response = _watcher_error_response(exc)
        _log_watcher_rejected("accept_baseline", session_id, exc, response, watcher_id)
        return response
    log.info("WATCHER_ROUTE_BASELINE_ACCEPTED", extra=_watcher_log_payload(accepted, session_id=session_id))
    return jsonify({"watcher": watcher_payload(accepted, schedule=schedule)})


@watchers_bp.route("/watchers/<watcher_id>/run-now", methods=["POST"])
@limiter.limit(_watcher_write_limit, key_func=get_session_id)
def watchers_run_now(watcher_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    fired_at = datetime.now(timezone.utc).isoformat()
    try:
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(watcher_id, session_id, conn=conn)
            schedule = _schedule_for_watcher(watcher, conn=conn)
            status = fire_schedule(conn, schedule, fired_at=fired_at)
            refreshed = get_watcher(watcher.id, conn=conn) or watcher
            refreshed_schedule = get_schedule(schedule.id, conn=conn) or schedule
            conn.commit()
    except (WatcherNotFound, WatcherError, ScheduleError, ScheduleCronError, ValueError) as exc:
        response = _watcher_error_response(exc)
        _log_watcher_rejected("run_now", session_id, exc, response, watcher_id)
        return response
    log.info("WATCHER_ROUTE_RUN_NOW", extra=_watcher_log_payload(
        refreshed,
        session_id=session_id,
        status=status,
        fired_at=fired_at,
        run_id=refreshed.last_run_id,
        last_error=refreshed.last_error,
    ))
    return jsonify({
        "status": status,
        "watcher": watcher_payload(refreshed, schedule=refreshed_schedule),
        "fired_at": fired_at,
    })
