"""Browser routes for session-owned scheduled runs."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from flask import Blueprint, jsonify, request

from config import CFG
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from extensions import limiter
from services.scheduler.commands import ScheduleCommandValidationError, validate_schedule_command
from services.scheduler.cron import ScheduleCronError, default_timezone, next_fire, normalize_cron, validate_timezone
from services.scheduler.dispatch import fire_schedule
from services.scheduler.serialization import get_user_schedule_for_session, schedule_fire_payload, schedule_payload
from services.scheduler.service import (
    ScheduleError,
    coerce_schedule_bool,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedule_fires,
    list_for_session,
    update_schedule,
)
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload
from services.session.variables import SessionVariableError

log = logging.getLogger("shell")

schedules_bp = Blueprint("schedules", __name__)


class ScheduleRouteError(ValueError):
    """Raised when schedule route input is invalid."""


class ScheduleNotFound(ScheduleRouteError):
    """Raised when a schedule is not visible to the current session."""


def _schedule_write_limit():
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


def _schedule_error_response(exc):
    if isinstance(exc, ScheduleNotFound):
        return jsonify({"error": "schedule_not_found"}), 404
    if isinstance(exc, ScheduleCronError):
        return jsonify({"error": "invalid_schedule", "message": str(exc)}), 400
    if isinstance(exc, ScheduleError):
        status = 409 if "quota" in str(exc).lower() else 400
        return jsonify({"error": "invalid_schedule", "message": str(exc)}), status
    if isinstance(exc, ScheduleCommandValidationError):
        return jsonify({"error": "invalid_schedule", "message": str(exc)}), 400
    if isinstance(exc, SessionVariableError):
        return jsonify({"error": "invalid_command", "message": str(exc)}), 400
    if isinstance(exc, ScheduleRouteError):
        return jsonify({"error": "invalid_schedule", "message": str(exc)}), 400
    if isinstance(exc, ValueError):
        return jsonify({"error": "invalid_schedule", "message": str(exc)}), 400
    return jsonify({"error": "invalid_schedule"}), 400


def _response_status(response) -> int:
    if isinstance(response, tuple) and len(response) > 1:
        try:
            return int(response[1])
        except (TypeError, ValueError):
            return 400
    return 400


def _schedule_log_payload(schedule=None, *, session_id: str = "", source: str = "browser", **extra) -> dict[str, object]:
    payload: dict[str, object] = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id or getattr(schedule, "session_token", "")),
        "source": source,
    }
    if schedule is not None:
        payload.update({
            "schedule_id": schedule.id,
            "enabled": schedule.enabled,
            "cron_expr": schedule.cron_expr,
            "cadence_preset": schedule.cadence_preset or "",
            "timezone": schedule.timezone,
            "next_run_at": schedule.next_run_at,
            "consecutive_failures": schedule.consecutive_failures,
        })
    payload.update(extra)
    return payload


def _log_schedule_rejected(action: str, session_id: str, exc: Exception, response, schedule_id: str = "") -> None:
    log.warning("SCHEDULE_REQUEST_REJECTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "source": "browser",
        "action": action,
        "schedule_id": schedule_id,
        "status": _response_status(response),
        "error": str(exc),
    })


def _schedule_for_session_or_404(schedule_id: str, session_id: str):
    schedule = get_user_schedule_for_session(schedule_id, session_id)
    if schedule is None:
        raise ScheduleNotFound("schedule not found")
    return schedule


@schedules_bp.route("/schedules/preview")
def schedules_preview():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        cron_expr, cadence_preset = normalize_cron(
            request.args.get("cron") or request.args.get("cron_expr"),
            cadence_preset=request.args.get("cadence_preset") or request.args.get("preset"),
        )
        timezone_name = validate_timezone(request.args.get("tz") or request.args.get("timezone") or default_timezone())
        cursor = datetime.now(timezone.utc)
        next_fires = []
        for _ in range(3):
            cursor = next_fire(cron_expr, cursor, timezone_name)
            next_fires.append(cursor.isoformat())
    except (ScheduleCronError, ValueError) as exc:
        response = _schedule_error_response(exc)
        _log_schedule_rejected("preview", session_id, exc, response)
        return response
    log.debug("SCHEDULE_PREVIEW_GENERATED", extra=_schedule_log_payload(
        None,
        session_id=session_id,
        cron_expr=cron_expr,
        cadence_preset=cadence_preset or "",
        timezone=timezone_name,
        next_fire_count=len(next_fires),
    ))
    return jsonify({
        "cron_expr": cron_expr,
        "cadence_preset": cadence_preset,
        "timezone": timezone_name,
        "next_fires": next_fires,
    })


@schedules_bp.route("/schedules")
def schedules_list():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        schedules = [schedule_payload(schedule) for schedule in list_for_session(session_id)]
    except (ScheduleError, ScheduleCronError, ValueError) as exc:
        response = _schedule_error_response(exc)
        _log_schedule_rejected("list", session_id, exc, response)
        return response
    log.debug("SCHEDULES_LISTED", extra=_schedule_log_payload(None, session_id=session_id, count=len(schedules)))
    return jsonify({"schedules": schedules})


@schedules_bp.route("/schedules/<schedule_id>")
def schedules_detail(schedule_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        schedule = _schedule_for_session_or_404(schedule_id, session_id)
    except ScheduleNotFound as exc:
        return _schedule_error_response(exc)
    return jsonify({"schedule": schedule_payload(schedule)})


@schedules_bp.route("/schedules/<schedule_id>/fires")
def schedules_fires(schedule_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        schedule = _schedule_for_session_or_404(schedule_id, session_id)
        limit = normalize_page_limit(request.args.get("limit"), default=20, maximum=100)
        offset = normalize_page_offset(request.args.get("offset"))
        fires, total = list_schedule_fires(schedule.id, limit=limit, offset=offset)
    except (ScheduleNotFound, ScheduleError, ValueError) as exc:
        response = _schedule_error_response(exc)
        _log_schedule_rejected("fires", session_id, exc, response, schedule_id=schedule_id)
        return response
    log.debug("SCHEDULE_FIRES_LISTED", extra=_schedule_log_payload(
        schedule,
        session_id=session_id,
        count=len(fires),
        total=total,
        limit=limit,
        offset=offset,
    ))
    return jsonify(page_payload("fires", [schedule_fire_payload(fire) for fire in fires], total, limit, offset))


@schedules_bp.route("/schedules", methods=["POST"])
@limiter.limit(_schedule_write_limit, key_func=get_session_id)
def schedules_create():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    if data is None:
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        command = validate_schedule_command(
            data.get("command"),
            session_id,
            workspace_cwd=str(data.get("workspace_cwd") or ""),
        )
        schedule = create_schedule(
            session_id,
            command_text=command,
            cron_expr=data.get("cron_expr"),
            cadence_preset=data.get("cadence_preset"),
            timezone_name=data.get("timezone"),
            label=str(data.get("label") or ""),
            enabled=coerce_schedule_bool(data.get("enabled"), default=True),
        )
    except (
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        ScheduleRouteError,
        SessionVariableError,
        ValueError,
    ) as exc:
        response = _schedule_error_response(exc)
        _log_schedule_rejected("create", session_id, exc, response)
        return response
    log.info("SCHEDULE_CREATED", extra=_schedule_log_payload(schedule, session_id=session_id))
    return jsonify({"schedule": schedule_payload(schedule)}), 201


@schedules_bp.route("/schedules/<schedule_id>", methods=["PATCH"])
@limiter.limit(_schedule_write_limit, key_func=get_session_id)
def schedules_update(schedule_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        schedule = _schedule_for_session_or_404(schedule_id, session_id)
    except ScheduleNotFound as exc:
        return _schedule_error_response(exc)
    data, body_error = _json_body()
    if body_error:
        return body_error
    if data is None:
        return jsonify({"error": "Request body must be a JSON object"}), 400
    updates = dict(data)
    try:
        if "command" in updates or "command_text" in updates:
            updates["command_text"] = validate_schedule_command(
                updates.get("command", updates.get("command_text")),
                session_id,
                workspace_cwd=str(updates.get("workspace_cwd") or ""),
            )
        if "timezone_name" in updates and "timezone" not in updates:
            updates["timezone"] = updates.pop("timezone_name")
        updated = update_schedule(schedule.id, updates)
    except (
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        ScheduleRouteError,
        SessionVariableError,
        ValueError,
    ) as exc:
        response = _schedule_error_response(exc)
        _log_schedule_rejected("update", session_id, exc, response, schedule_id=schedule.id)
        return response
    if updated is None:
        response = (jsonify({"error": "schedule_not_found"}), 404)
        _log_schedule_rejected("update", session_id, ScheduleNotFound("schedule not found"), response, schedule_id)
        return response
    log.info("SCHEDULE_UPDATED", extra=_schedule_log_payload(
        updated,
        session_id=session_id,
        changed_fields=",".join(sorted(key for key in updates if key != "workspace_cwd")),
    ))
    return jsonify({"schedule": schedule_payload(updated)})


@schedules_bp.route("/schedules/<schedule_id>", methods=["DELETE"])
@limiter.limit(_schedule_write_limit, key_func=get_session_id)
def schedules_delete(schedule_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        schedule = _schedule_for_session_or_404(schedule_id, session_id)
    except ScheduleNotFound as exc:
        return _schedule_error_response(exc)
    removed = delete_schedule(schedule.id)
    log.info("SCHEDULE_DELETED", extra=_schedule_log_payload(schedule, session_id=session_id, removed=removed))
    return jsonify({"removed": removed})


@schedules_bp.route("/schedules/<schedule_id>/run-now", methods=["POST"])
@limiter.limit(_schedule_write_limit, key_func=get_session_id)
def schedules_run_now(schedule_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        schedule = _schedule_for_session_or_404(schedule_id, session_id)
    except ScheduleNotFound as exc:
        return _schedule_error_response(exc)
    fired_at = datetime.now(timezone.utc).isoformat()
    try:
        from core import database

        with database.db_connect() as conn:
            status = fire_schedule(conn, schedule, fired_at=fired_at)
            refreshed = get_schedule(schedule.id, conn=conn)
            conn.commit()
    except (ScheduleError, ScheduleCronError, ValueError) as exc:
        response = _schedule_error_response(exc)
        _log_schedule_rejected("run_now", session_id, exc, response, schedule_id=schedule.id)
        return response
    log.info("SCHEDULE_RUN_NOW", extra=_schedule_log_payload(
        refreshed or schedule,
        session_id=session_id,
        status=status,
        fired_at=fired_at,
        run_id=(refreshed or schedule).last_run_id,
        last_error=(refreshed or schedule).last_error,
    ))
    return jsonify({
        "status": status,
        "schedule": schedule_payload(refreshed or schedule),
        "fired_at": fired_at,
    })
