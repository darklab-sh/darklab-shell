"""Browser routes for session-owned scheduled runs."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from flask import Blueprint, jsonify, request

from config import CFG
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from extensions import limiter
from services.audit.automation import record_schedule_event, run_now_details
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.scheduler.commands import ScheduleCommandValidationError
from services.scheduler.cron import ScheduleCronError, default_timezone, next_fire, normalize_cron, validate_timezone
from services.scheduler.route_helpers import (
    fire_schedule_now,
    normalize_schedule_create_payload,
    normalize_schedule_update_payload,
)
from services.scheduler.serialization import get_user_schedule_for_owner, schedule_fire_payload, schedule_payload
from services.scheduler.service import (
    ScheduleError,
    create_schedule,
    delete_schedule,
    list_schedule_fires,
    list_for_owner,
    run_schedule_transaction,
    update_schedule,
)
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload
from services.session.variables import SessionVariableError
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScope, RequestScopeError, current_request_scope, scope_error_payload

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
            "team_id": schedule.team_id,
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


def _schedule_for_session_or_404(schedule_id: str, session_id: str, *, team_id: str = ""):
    schedule = get_user_schedule_for_owner(schedule_id, session_id, team_id=team_id)
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    try:
        schedules = [
            schedule_payload(schedule)
            for schedule in list_for_owner(session_id, team_id=owner_scope.team_id)
        ]
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    try:
        schedule = _schedule_for_session_or_404(schedule_id, session_id, team_id=owner_scope.team_id)
    except ScheduleNotFound as exc:
        return _schedule_error_response(exc)
    return jsonify({"schedule": schedule_payload(schedule)})


@schedules_bp.route("/schedules/<schedule_id>/fires")
def schedules_fires(schedule_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    try:
        schedule = _schedule_for_session_or_404(schedule_id, session_id, team_id=owner_scope.team_id)
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
        payload = normalize_schedule_create_payload(data, session_id)

        def _create(conn):
            schedule = create_schedule(
                session_id,
                team_id=owner_scope.team_id,
                **payload,
                conn=conn,
            )
            record_schedule_event(
                AuditEventType.SCHEDULE_CREATE,
                schedule,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="browser",
                conn=conn,
            )
            return schedule

        schedule = run_schedule_transaction(_create)
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    capability_response = _require_automation_capability(owner_scope)
    if capability_response:
        return capability_response
    try:
        schedule = _schedule_for_session_or_404(schedule_id, session_id, team_id=owner_scope.team_id)
    except ScheduleNotFound as exc:
        return _schedule_error_response(exc)
    data, body_error = _json_body()
    if body_error:
        return body_error
    if data is None:
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        updates = normalize_schedule_update_payload(data, session_id)

        def _update(conn):
            updated = update_schedule(schedule.id, updates, conn=conn)
            if updated is not None:
                record_schedule_event(
                    AuditEventType.SCHEDULE_UPDATE,
                    updated,
                    audit_fields=route_audit_fields(session_id, request, owner_scope),
                    source="browser",
                    details={"changed_fields": sorted(key for key in updates if key != "workspace_cwd")},
                    conn=conn,
                )
            return updated

        updated = run_schedule_transaction(_update)
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
    owner_scope, scope_response = _request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    capability_response = _require_automation_capability(owner_scope)
    if capability_response:
        return capability_response
    try:
        schedule = _schedule_for_session_or_404(schedule_id, session_id, team_id=owner_scope.team_id)
    except ScheduleNotFound as exc:
        return _schedule_error_response(exc)

    def _delete(conn):
        removed = delete_schedule(schedule.id, conn=conn)
        record_schedule_event(
            AuditEventType.SCHEDULE_DELETE,
            schedule,
            audit_fields=route_audit_fields(session_id, request, owner_scope),
            source="browser",
            details={"deleted_count": 1 if removed else 0},
            conn=conn,
        )
        return removed

    removed = run_schedule_transaction(_delete)
    log.info("SCHEDULE_DELETED", extra=_schedule_log_payload(schedule, session_id=session_id, removed=removed))
    return jsonify({"removed": removed})


@schedules_bp.route("/schedules/<schedule_id>/run-now", methods=["POST"])
@limiter.limit(_schedule_write_limit, key_func=get_session_id)
def schedules_run_now(schedule_id):
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
        schedule = _schedule_for_session_or_404(schedule_id, session_id, team_id=owner_scope.team_id)
    except ScheduleNotFound as exc:
        return _schedule_error_response(exc)
    try:
        def _run_now(conn):
            status, refreshed, fired_at = fire_schedule_now(conn, schedule)
            record_schedule_event(
                AuditEventType.SCHEDULE_RUN_NOW,
                refreshed or schedule,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="browser",
                details=run_now_details(
                    status,
                    fired_at=fired_at,
                    run_id=(refreshed or schedule).last_run_id,
                    last_error=(refreshed or schedule).last_error,
                ),
                conn=conn,
            )
            return status, refreshed, fired_at

        status, refreshed, fired_at = run_schedule_transaction(_run_now)
    except (ScheduleError, ScheduleCronError, ValueError) as exc:
        response = _schedule_error_response(exc)
        _log_schedule_rejected("run_now", session_id, exc, response, schedule_id=schedule.id)
        return response
    log.info("SCHEDULE_RUN_NOW", extra=_schedule_log_payload(
        refreshed or schedule,
        session_id=session_id,
        status=status,
        fired_at=fired_at,
        run_id=refreshed.last_run_id,
        last_error=refreshed.last_error,
    ))
    return jsonify({
        "status": status,
        "schedule": schedule_payload(refreshed),
        "fired_at": fired_at,
    })
