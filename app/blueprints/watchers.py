"""Browser routes for session-owned change-detection watchers."""

from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, request

from config import CFG
from core import database
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from extensions import limiter
from services.audit.automation import record_watcher_event, run_now_details
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload
from services.scheduler.commands import ScheduleCommandValidationError
from services.scheduler.cron import ScheduleCronError
from services.scheduler.route_helpers import (
    RouteBaselineRunNotCompleted,
    RouteBaselineRunNotFound,
    fire_watcher_now,
    normalize_watcher_create_payload,
    normalize_watcher_update_payload,
    schedule_for_watcher,
)
from services.scheduler.service import ScheduleError, get_schedule
from services.session.variables import SessionVariableError
from services.watchers.serialization import watcher_fire_payload, watcher_payload
from services.watchers.service import (
    WatcherError,
    accept_baseline,
    create_watcher,
    delete_watcher,
    get_watcher,
    list_for_owner,
    list_watcher_fires,
    pause_watcher,
    resume_watcher,
    update_watcher,
)
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScope, RequestScopeError, current_request_scope, scope_error_payload

log = logging.getLogger("shell")

watchers_bp = Blueprint("watchers", __name__)


class WatcherRouteError(ValueError):
    """Raised when watcher route input is invalid."""


class WatcherNotFound(WatcherRouteError):
    """Raised when a watcher is not visible to the current session."""


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
            "team_id": watcher.team_id,
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
    if isinstance(exc, RouteBaselineRunNotFound):
        return jsonify({"error": "baseline_run_not_found"}), 404
    if isinstance(exc, RouteBaselineRunNotCompleted):
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


def _request_scope_response(session_id: str) -> tuple[RequestScope | None, Any]:
    try:
        return current_request_scope(session_id, request), None
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return None, (jsonify(payload), status)


def _team_capability_error_response(exc: TeamPermissionDenied):
    return jsonify({"error": "team_forbidden", "message": str(exc)}), 403


def _require_automation_capability(owner_scope: RequestScope):
    if not owner_scope.is_team:
        return None
    try:
        require_capability(str((owner_scope.member or {}).get("role") or ""), Capability.MANAGE_AUTOMATION)
    except TeamPermissionDenied as exc:
        return _team_capability_error_response(exc)
    return None


def _watcher_for_session_or_404(watcher_id: str, session_id: str, *, team_id: str = "", conn=None):
    watcher = get_watcher(watcher_id, conn=conn)
    if watcher is None:
        raise WatcherNotFound("watcher not found")
    if team_id:
        if watcher.team_id != team_id:
            raise WatcherNotFound("watcher not found")
        return watcher
    if watcher.team_id or watcher.session_token != session_id:
        raise WatcherNotFound("watcher not found")
    return watcher


@watchers_bp.route("/watchers")
def watchers_list():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    try:
        with database.db_connect() as conn:
            watchers = list_for_owner(session_id, team_id=owner_scope.team_id, conn=conn)
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    capability_response = _require_automation_capability(owner_scope)
    if capability_response:
        return capability_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    if data is None:
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        with database.db_connect() as conn:
            payload = normalize_watcher_create_payload(
                data,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            watcher = create_watcher(
                session_id,
                team_id=owner_scope.team_id,
                **payload,
                conn=conn,
            )
            schedule = schedule_for_watcher(watcher, conn=conn)
            record_watcher_event(
                AuditEventType.WATCHER_CREATE,
                watcher,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="browser",
                conn=conn,
            )
            conn.commit()
    except (
        RouteBaselineRunNotFound,
        RouteBaselineRunNotCompleted,
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    capability_response = _require_automation_capability(owner_scope)
    if capability_response:
        return capability_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    if data is None:
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(
                watcher_id,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            route_update = normalize_watcher_update_payload(data, session_id)
            updated = update_watcher(watcher.id, route_update.updates, conn=conn) if route_update.updates else watcher
            if updated is None:
                raise WatcherNotFound("watcher not found")
            event_type = AuditEventType.WATCHER_UPDATE
            if route_update.pause_requested:
                updated = pause_watcher(updated.id, route_update.reason, conn=conn)
                event_type = AuditEventType.WATCHER_PAUSE
            elif route_update.resume_requested:
                updated = resume_watcher(updated.id, conn=conn)
                event_type = AuditEventType.WATCHER_RESUME
            if updated is None:
                raise WatcherNotFound("watcher not found")
            schedule = schedule_for_watcher(updated, conn=conn)
            record_watcher_event(
                event_type,
                updated,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="browser",
                details={
                    "changed_fields": sorted(key for key in route_update.updates if key != "workspace_cwd"),
                    "reason": route_update.reason if route_update.pause_requested else "",
                },
                conn=conn,
            )
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    capability_response = _require_automation_capability(owner_scope)
    if capability_response:
        return capability_response
    try:
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(
                watcher_id,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            removed = delete_watcher(watcher.id, conn=conn)
            record_watcher_event(
                AuditEventType.WATCHER_DELETE,
                watcher,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="browser",
                details={"deleted_count": 1 if removed else 0},
                conn=conn,
            )
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    try:
        limit = normalize_page_limit(request.args.get("limit"), default=20, maximum=100)
        offset = normalize_page_offset(request.args.get("offset"))
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(
                watcher_id,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    capability_response = _require_automation_capability(owner_scope)
    if capability_response:
        return capability_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    data = data or {}
    try:
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(
                watcher_id,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            accepted = accept_baseline(watcher.id, run_id=data.get("run_id"), conn=conn)
            if accepted is None:
                raise WatcherNotFound("watcher not found")
            schedule = schedule_for_watcher(accepted, conn=conn)
            record_watcher_event(
                AuditEventType.WATCHER_ACCEPT_BASELINE,
                accepted,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="browser",
                details={"baseline_run_id": accepted.baseline_run_id},
                conn=conn,
            )
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    capability_response = _require_automation_capability(owner_scope)
    if capability_response:
        return capability_response
    try:
        with database.db_connect() as conn:
            watcher = _watcher_for_session_or_404(
                watcher_id,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            status, refreshed, refreshed_schedule, fired_at = fire_watcher_now(conn, watcher)
            record_watcher_event(
                AuditEventType.WATCHER_RUN_NOW,
                refreshed,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="browser",
                details=run_now_details(
                    status,
                    fired_at=fired_at,
                    run_id=refreshed.last_run_id,
                    last_error=refreshed.last_error,
                ),
                conn=conn,
            )
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
