# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Headless API v1 routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request

from config import CFG
from core.helpers import get_client_ip, get_log_session_id
from core.process import active_runs_for_session, active_runs_for_team, pid_for_session  # noqa: F401 - compatibility seam for api_v1_runs/tests
from extensions import limiter
from services.api_v1.auth import ApiAuthError, current_api_session, require_api_auth  # noqa: F401 - compatibility seam for api_v1 resource modules
from services.api_v1.serialization import json_error, run_summary
from blueprints.api_v1_streaming import (
    ndjson_from_sse_chunks as _ndjson_from_sse_chunks,  # noqa: F401 - compatibility seam for api_v1_runs/tests
    sse_after_id as _sse_after_id,  # noqa: F401 - compatibility seam for api_v1_runs/tests
    sse_chunks_with_error_logging as _sse_chunks_with_error_logging,  # noqa: F401 - compatibility seam for api_v1_runs/tests
)
from services.audit.context import (
    request_audit_fields,
    route_audit_fields,  # noqa: F401 - compatibility seam for api_v1 resource modules
)
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.commands.registry import (
    interactive_pty_spec_for_command,  # noqa: F401 - compatibility seam for api_v1_runs/tests
    runtime_missing_command_message,
    split_command_argv,  # noqa: F401 - compatibility seam for api_v1_runs/tests
)
from services.history import api_queries as history_api
from services.history.run_metadata import normalize_history_filter_text as _normalize_history_filter_text
from services.notifications.channels_store import NotificationChannelError
from services.projects.contracts import (
    ProjectWorkspaceError,
    ProjectWorkspaceNotFound,
    ProjectWorkspaceQuotaExceeded,
)
from services.projects.queries import get_project
from services.runs.broker import (
    broker_available,  # noqa: F401 - compatibility seam for api_v1_runs/tests
    broker_unavailable_reason,  # noqa: F401 - compatibility seam for api_v1_runs/tests
    publish_run_event,  # noqa: F401 - compatibility seam for api_v1_runs/tests
    stream_run_events,  # noqa: F401 - compatibility seam for api_v1_runs/tests
)
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL
from services.runs.output_model import LineEvent
from services.runs.start import (
    RunStartHandlers,
    RunStartRejected,  # noqa: F401 - compatibility seam for api_v1_runs/tests
    start_brokered_run as _start_brokered_run_service,  # noqa: F401 - compatibility seam for api_v1_runs/tests
)
from services.teams.capabilities import Capability, require_capability
from services.teams import api_operations as team_api  # noqa: F401 - compatibility seam for api_v1_teams/tests
from services.teams import storage as team_storage
from services.teams.contracts import (
    TeamError,
    TeamArchived,
    TeamNotFound,
    TeamOwnerRequired,
    TeamPermissionDenied,
    TeamSlugUnavailable,
)
from services.teams.request_scope import RequestScopeError, current_request_scope
from services.watchers.service import pause_team_watchers_and_schedules  # noqa: F401 - compatibility seam for api_v1_teams/tests
from services.runs.structured_filters import StructuredOutputFilters
from services.scheduler.commands import (
    ScheduleCommandValidationError,
    validate_schedule_command,  # noqa: F401 - compatibility seam for api_v1 schedule/watcher tests
)
from services.scheduler.cron import ScheduleCronError, next_fire
from services.scheduler.route_helpers import (
    RouteBaselineRunNotCompleted,
    RouteBaselineRunNotFound,
)
from services.scheduler.serialization import get_user_schedule_for_owner
from services.scheduler.service import ScheduleError
from services.secrets.vault import MasterKeyError, SecretDecryptError
from services.session.variables import SessionVariableError
from services.watchers.service import WatcherError, get_watcher

from blueprints.run import (  # noqa: PLC0415
    _RunPreparationError,  # noqa: F401
    _RunSpawnError,  # noqa: F401
    _brokered_real_run_worker,
    _brokered_synthetic_run,
    _filter_builtin_command_events,
    _history_safe_command_for_storage,
    _prepare_command_input,
    _prepare_real_command,
    _ensure_scanner_process_group_current,  # noqa: F401
    _signal_process_group,  # noqa: F401
    _start_real_command_process,
    _workspace_cwd_value,  # noqa: F401
    _workspace_artifacts_from_validation,
    _workspace_notice_lines,
    execute_builtin_command,
    resolve_builtin_command,
    resolves_exact_special_builtin_command,
)

log = logging.getLogger("shell")


def _api_route_limit() -> str:
    return f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"


def _api_team_read_route_limit() -> str:
    minute_limit = int(CFG.get("team_read_rate_limit_per_minute") or 180)
    second_limit = int(CFG.get("team_read_rate_limit_per_second") or 20)
    return f"{minute_limit} per minute; {second_limit} per second"


def _api_team_write_route_limit() -> str:
    limit = int(CFG.get("team_write_rate_limit_per_minute") or 30)
    return f"{limit} per minute"


def _api_team_rate_limit_key() -> str:
    authorization = str(request.headers.get("Authorization") or "").strip()
    bearer_prefix = "Bearer "
    if authorization.lower().startswith(bearer_prefix.lower()):
        token = authorization[len(bearer_prefix):].strip()
        if token:
            return token
    session_id = str(request.headers.get("X-Session-ID") or "").strip()
    return session_id or get_client_ip()


api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
limiter.limit(_api_route_limit)(api_v1_bp)


def _api_run_start_handlers() -> RunStartHandlers:
    return RunStartHandlers(
        resolves_exact_special_builtin_command=resolves_exact_special_builtin_command,
        execute_builtin_command=execute_builtin_command,
        history_safe_command_for_storage=_history_safe_command_for_storage,
        brokered_synthetic_run=_brokered_synthetic_run,
        prepare_command_input=_prepare_command_input,
        resolve_builtin_command=resolve_builtin_command,
        filter_builtin_command_events=_filter_builtin_command_events,
        prepare_real_command=_prepare_real_command,
        runtime_missing_command_message=runtime_missing_command_message,
        start_real_command_process=_start_real_command_process,
        publish_run_event=publish_run_event,
        brokered_real_run_worker=_brokered_real_run_worker,
        workspace_notice_lines=_workspace_notice_lines,
        workspace_artifacts_from_validation=_workspace_artifacts_from_validation,
    )


def _api_json_error(code: str, message: str, status: int):
    return jsonify(json_error(code, message)), status


def _project_workspace_api_error(exc: ProjectWorkspaceError):
    if isinstance(exc, ProjectWorkspaceNotFound):
        return _api_json_error("not_found", str(exc), 404)
    if isinstance(exc, ProjectWorkspaceQuotaExceeded):
        return _api_json_error("quota_exceeded", str(exc), 409)
    return _api_json_error("invalid_project_link", str(exc), 400)


def _notification_api_error(exc: Exception):
    if isinstance(exc, NotificationChannelError):
        code = exc.code
        message = str(exc)
        status_code = exc.status_code
    elif isinstance(exc, TeamPermissionDenied):
        code = "team_forbidden"
        message = str(exc)
        status_code = 403
    elif isinstance(exc, (MasterKeyError, SecretDecryptError)):
        code = "vault_unavailable"
        message = "Notification channel secrets are unavailable."
        status_code = 503
    elif isinstance(exc, ValueError):
        code = "invalid_notification_channel"
        message = str(exc)
        status_code = 400
    else:
        raise exc
    try:
        session = get_log_session_id(current_api_session().token)
    except Exception:
        session = ""
    log.warning("API_NOTIFICATION_CHANNEL_REJECTED", extra={
        "ip": get_client_ip(),
        "session": session,
        "code": code,
        "http_status": status_code,
        "route": str(request.path or ""),
        "method": str(request.method or ""),
    })
    return _api_json_error(code, message, status_code)


def _team_api_error_code_and_status(exc: Exception) -> tuple[str, int]:
    if isinstance(exc, TeamPermissionDenied):
        return "team_forbidden", 403
    if isinstance(exc, TeamOwnerRequired):
        return "team_owner_required", 409
    if isinstance(exc, TeamSlugUnavailable):
        return "team_slug_unavailable", 409
    if isinstance(exc, TeamArchived):
        return "team_archived", 409
    if isinstance(exc, TeamNotFound):
        return "team_not_found", 404
    if isinstance(exc, (TeamError, ValueError)):
        return "invalid_team_request", 400
    return "team_route_failed", 500


def _team_api_error(exc: Exception):
    code, status = _team_api_error_code_and_status(exc)
    message = str(exc) if status < 500 else "Team request failed."
    return _api_json_error(code, message, status)


def _api_team_member(conn, team_id: str, session_token: str) -> dict[str, Any]:
    member = team_storage.get_team_membership(conn, team_id, session_token)
    if not member:
        raise TeamNotFound("Team not found.")
    return member


def _api_actor_log_fields(actor: dict[str, Any] | None) -> dict[str, Any]:
    if not actor:
        return {}
    return {
        "actor_member_id": str(actor.get("id") or ""),
        "actor_role": str(actor.get("role") or ""),
    }


def _api_actor_audit_fields(
    session_token: str,
    *,
    team_id: str = "",
    actor: dict[str, Any] | None = None,
    actor_member_id: str = "",
    actor_role: str = "",
    actor_display_name: str = "",
) -> dict[str, Any]:
    actor_member_id = actor_member_id or str((actor or {}).get("id") or "")
    actor_role = actor_role or str((actor or {}).get("role") or "")
    actor_display_name = actor_display_name or str(
        (actor or {}).get("display_name") or (actor or {}).get("name") or ""
    )
    return {
        "session_id": session_token,
        "actor_session_id": session_token,
        "team_id": team_id,
        "actor_member_id": actor_member_id,
        "actor_role": actor_role,
        "actor_display_name": actor_display_name,
        **request_audit_fields(request),
    }


def _record_api_team_audit(
    event_type: AuditEventType,
    *,
    session_token: str,
    team_id: str,
    actor: dict[str, Any] | None = None,
    actor_member_id: str = "",
    actor_role: str = "",
    actor_display_name: str = "",
    details: dict[str, Any] | None = None,
    conn=None,
) -> None:
    record_event(
        event_type,
        target_id=team_id,
        details={"source": "api_v1", **(details or {})},
        conn=conn,
        **_api_actor_audit_fields(
            session_token,
            team_id=team_id,
            actor=actor,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            actor_display_name=actor_display_name,
        ),
    )


def _api_team_log_fields(
    action: str,
    *,
    session_token: str,
    team_id: str = "",
    result: str = "ok",
    actor: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "action": action,
        "team_id": team_id,
        "session": get_log_session_id(session_token),
        "ip": get_client_ip(),
        "result": result,
        "source": "api_v1",
        "route": str(request.path or ""),
        "method": str(request.method or ""),
        **_api_actor_log_fields(actor),
        **extra,
    }


def _log_api_team_event(
    action: str,
    *,
    session_token: str,
    team_id: str = "",
    result: str = "ok",
    actor: dict[str, Any] | None = None,
    **extra: Any,
) -> None:
    fields = _api_team_log_fields(action, session_token=session_token, team_id=team_id, result=result, actor=actor, **extra)
    if result == "ok":
        log.info("TEAM_ACTION", extra=fields)
    else:
        log.warning("TEAM_ACTION_REJECTED", extra=fields)


def _log_api_team_exception(
    action: str,
    exc: Exception,
    *,
    session_token: str,
    team_id: str = "",
    actor: dict[str, Any] | None = None,
    **extra: Any,
):
    code, status = _team_api_error_code_and_status(exc)
    fields = _api_team_log_fields(
        action,
        session_token=session_token,
        team_id=team_id,
        result="error",
        actor=actor,
        reason=code,
        error_code=code,
        http_status=status,
        **extra,
    )
    if status >= 500:
        log.error("TEAM_ACTION_FAILED", extra=fields, exc_info=True)
    else:
        log.warning("TEAM_ACTION_REJECTED", extra=fields)
    return _team_api_error(exc)


def _require_notification_manage_scope():
    owner_scope = _api_request_scope()
    if owner_scope.is_team:
        member = owner_scope.member or {}
        require_capability(str(member.get("role") or ""), Capability.MANAGE_NOTIFICATIONS)
    return owner_scope


def _require_api_team_capability(owner_scope, capability: Capability) -> None:
    if not owner_scope.is_team:
        return
    member = owner_scope.member or {}
    require_capability(str(member.get("role") or ""), capability)


def _schedule_for_api_session(schedule_id: str, session_id: str, *, team_id: str = ""):
    schedule = get_user_schedule_for_owner(schedule_id, session_id, team_id=team_id)
    if schedule is None:
        raise ApiAuthError("not_found", "Schedule not found.", status_code=404)
    return schedule


def _api_schedule_error_shape(exc: Exception) -> tuple[str, str, int]:
    if isinstance(exc, ApiAuthError):
        return exc.code, exc.message, exc.status_code
    if isinstance(exc, TeamPermissionDenied):
        return "team_forbidden", str(exc), 403
    if isinstance(exc, ScheduleCronError):
        return "invalid_schedule", str(exc), 400
    if isinstance(exc, ScheduleCommandValidationError):
        return "invalid_command", str(exc), 400
    if isinstance(exc, SessionVariableError):
        return "invalid_command", str(exc), 400
    if isinstance(exc, ScheduleError):
        status = 409 if "quota" in str(exc).lower() else 400
        return "invalid_schedule", str(exc), status
    if isinstance(exc, ValueError):
        return "invalid_schedule", str(exc), 400
    raise exc


def _schedule_api_error(exc: Exception):
    code, message, status = _api_schedule_error_shape(exc)
    try:
        session = get_log_session_id(current_api_session().token)
    except Exception:
        session = ""
    log.warning("API_SCHEDULE_REJECTED", extra={
        "ip": get_client_ip(),
        "session": session,
        "code": code,
        "http_status": status,
        "route": str(request.path or ""),
        "method": str(request.method or ""),
        "error": message,
    })
    return _api_json_error(code, message, status)


def _api_schedule_log_payload(schedule=None, *, session_id: str = "", **extra) -> dict[str, object]:
    payload: dict[str, object] = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id or getattr(schedule, "session_token", "")),
        "source": "api",
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


def _api_schedule_next_fires(schedule, *, count: int = 3) -> list[str]:
    cursor = datetime.now(timezone.utc)
    next_fires: list[str] = []
    for _ in range(count):
        cursor = next_fire(schedule.cron_expr, cursor, schedule.timezone)
        next_fires.append(cursor.isoformat())
    return next_fires


def _watcher_for_api_session(watcher_id: str, session_id: str, *, team_id: str = "", conn=None):
    watcher = get_watcher(watcher_id, conn=conn)
    if watcher is None:
        raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
    if team_id:
        if watcher.team_id != team_id:
            raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
        return watcher
    if watcher.team_id or watcher.session_token != session_id:
        raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
    return watcher


def _api_watcher_error_shape(exc: Exception) -> tuple[str, str, int]:
    if isinstance(exc, ApiAuthError):
        return exc.code, exc.message, exc.status_code
    if isinstance(exc, TeamPermissionDenied):
        return "team_forbidden", str(exc), 403
    if isinstance(exc, ScheduleCronError):
        return "invalid_watcher", str(exc), 400
    if isinstance(exc, ScheduleCommandValidationError):
        return "invalid_command", str(exc), 400
    if isinstance(exc, SessionVariableError):
        return "invalid_command", str(exc), 400
    if isinstance(exc, RouteBaselineRunNotFound):
        return "not_found", "Baseline run not found.", 404
    if isinstance(exc, RouteBaselineRunNotCompleted):
        return "invalid_watcher", str(exc), 400
    if isinstance(exc, WatcherError):
        status = 409 if "quota" in str(exc).lower() else 400
        return "invalid_watcher", str(exc), status
    if isinstance(exc, ScheduleError):
        status = 409 if "quota" in str(exc).lower() else 400
        return "invalid_watcher", str(exc), status
    if isinstance(exc, ValueError):
        return "invalid_watcher", str(exc), 400
    raise exc


def _watcher_api_error(exc: Exception):
    code, message, status = _api_watcher_error_shape(exc)
    try:
        session = get_log_session_id(current_api_session().token)
    except Exception:
        session = ""
    log.warning("API_WATCHER_REJECTED", extra={
        "ip": get_client_ip(),
        "session": session,
        "code": code,
        "http_status": status,
        "route": str(request.path or ""),
        "method": str(request.method or ""),
        "error": message,
    })
    return _api_json_error(code, message, status)


def _api_watcher_log_payload(watcher=None, *, session_id: str = "", **extra) -> dict[str, object]:
    payload: dict[str, object] = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id or getattr(watcher, "session_token", "")),
        "source": "api",
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


@api_v1_bp.errorhandler(ApiAuthError)
def _handle_api_auth_error(exc: ApiAuthError):
    log.warning("API_AUTH_FAILED", extra={
        "ip": get_client_ip(),
        "code": exc.code,
        "http_status": exc.status_code,
    })
    return _api_json_error(exc.code, exc.message, exc.status_code)


def _require_session_id() -> str:
    return current_api_session().token


def _api_request_scope():
    try:
        return current_request_scope(_require_session_id(), request)
    except RequestScopeError as exc:
        raise ApiAuthError(exc.code, exc.message, status_code=exc.status_code) from exc


def _json_body() -> dict[str, Any]:
    parsed_json = request.get_json(silent=True)
    if parsed_json is None:
        return {}
    if not isinstance(parsed_json, dict):
        raise ApiAuthError("invalid_body", "Request body must be a JSON object.", status_code=400)
    return parsed_json


def _parse_int(value: object, default: int, *, minimum: int = 0, maximum: int = 100000) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _parse_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_float(value: object, default: float, *, minimum: float = 0.0, maximum: float = 3600.0) -> float:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _run_kind_filter(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"external", "real"}:
        return RUN_KIND_EXTERNAL
    if candidate in {"builtin", "missing"}:
        return RUN_KIND_BUILTIN
    return ""


def _history_datetime_filter(name: str) -> str:
    raw = _normalize_history_filter_text(request.args.get(name))
    if not raw:
        return ""
    value = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    if "T" not in value and " " not in value:
        raise ApiAuthError(
            f"invalid_{name}",
            f"{name} must be an ISO 8601 datetime such as 2026-05-19T00:00:00Z.",
            status_code=400,
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ApiAuthError(
            f"invalid_{name}",
            f"{name} must be an ISO 8601 datetime such as 2026-05-19T00:00:00Z.",
            status_code=400,
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat()


def _active_runs_for_owner(session_id: str, team_id: str = "", client_id: str = "") -> list[dict[str, Any]]:
    if team_id:
        return active_runs_for_team(team_id, client_id=client_id)
    return active_runs_for_session(session_id, client_id=client_id, team_id="")


def _run_status_from_active_or_row(run_id: str, session_id: str, team_id: str = "") -> dict[str, Any] | None:
    for active in _active_runs_for_owner(session_id, team_id):
        if str(active.get("run_id") or "") == run_id:
            return _active_run_summary(active)
    run = history_api.run_status_from_active_or_row(run_id, session_id, team_id)
    return run_summary(run) if run is not None else None


def _active_run_summary(active: dict[str, Any]) -> dict[str, Any]:
    return history_api.active_run_summary(active)


def _history_filters() -> dict[str, str]:
    return {
        "q": _normalize_history_filter_text(request.args.get("q")),
        "project_id": _normalize_history_filter_text(request.args.get("project_id")),
        "run_kind": _run_kind_filter(request.args.get("run_kind")),
        "exit_code": _normalize_history_filter_text(request.args.get("exit_code")),
        "since": _history_datetime_filter("since"),
        "until": _history_datetime_filter("until"),
    }


def _requested_project_id(data: dict[str, Any], session_id: str, *, team_id: str = "") -> str:
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        return ""
    project = get_project(session_id, project_id, team_id=team_id)
    if project is None:
        raise ApiAuthError("not_found", "Project not found.", status_code=404)
    if str(project.get("status") or "") == "archived":
        raise ApiAuthError("archived_project", "Archived projects cannot receive new API run links.", status_code=409)
    return project_id


def _active_project_for_write(session_id: str, project_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    project = get_project(session_id, project_id, team_id=team_id)
    if project is None:
        return None
    if str(project.get("status") or "") == "archived":
        raise ApiAuthError("archived_project", "Archived projects cannot be modified through API v1.", status_code=409)
    return project


def _history_where(
    session_id: str,
    team_id: str,
    filters: dict[str, str],
    *,
    offloaded_ids: list[str] | None = None,
    search_scope: str = "all",
):
    return history_api.history_where(
        session_id,
        team_id,
        filters,
        offloaded_ids=offloaded_ids,
        search_scope=search_scope,
    )


def _history_search_candidate_runs(
    session_id: str,
    team_id: str,
    filters: dict[str, str],
    structured_filters,
) -> list[dict[str, Any]]:
    return history_api.history_search_candidate_runs(session_id, team_id, filters, structured_filters)


def _run_output_search_matches(
    run: dict[str, Any],
    query: str,
    context: int,
    structured_filters,
) -> list[dict[str, Any]]:
    return history_api.run_output_search_matches(run, query, context, structured_filters)


def _history_output_search(
    session_id: str,
    team_id: str,
    query: str,
    context: int,
    structured_filters,
) -> list[dict[str, Any]]:
    filters = _history_filters()
    return history_api.history_output_search(session_id, team_id, filters, query, context, structured_filters)


def _structured_filters_payload(structured_filters: StructuredOutputFilters) -> dict[str, list[str]]:
    return {
        "signals": list(structured_filters.signals),
        "kinds": list(structured_filters.kinds),
        "exclude_kinds": list(structured_filters.exclude_kinds),
        "roles": list(structured_filters.roles),
        "entities": list(structured_filters.entities),
        "entity_types": list(structured_filters.entity_types),
    }


def _history_rows(
    session_id: str,
    team_id: str,
    limit: int,
    offset: int,
    filters: dict[str, str],
    structured_filters=None,
):
    return history_api.history_rows(session_id, team_id, limit, offset, filters, structured_filters)


def _load_run_detail(session_id: str, team_id: str, run_id: str) -> dict[str, Any] | None:
    return history_api.load_run_detail(session_id, team_id, run_id)


def _run_output_events(run: dict[str, Any], *, full: bool = True) -> list[LineEvent]:
    return history_api.run_output_events(run, full=full)


def _parse_output_range(value: object) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "-" not in text:
        raise ApiAuthError("invalid_range", "range must use N-M line numbers.", status_code=400)
    start_text, end_text = text.split("-", 1)
    try:
        start = int(start_text)
        end = int(end_text)
    except (TypeError, ValueError) as exc:
        raise ApiAuthError("invalid_range", "range must use N-M line numbers.", status_code=400) from exc
    if start < 1 or end < start:
        raise ApiAuthError("invalid_range", "range must use 1-based line numbers with M >= N.", status_code=400)
    return start, end


def _slice_output_lines(lines: list[str], line_range: tuple[int, int] | None) -> list[str]:
    if line_range is None:
        return lines
    start, end = line_range
    return lines[start - 1:end]


def _slice_output_events(events: list[LineEvent], line_range: tuple[int, int] | None) -> list[LineEvent]:
    if line_range is None:
        return events
    start, end = line_range
    return events[start - 1:end]


def _artifact_for_run(session_id: str, team_id: str, run_id: str, artifact_id: str) -> dict[str, Any] | None:
    return history_api.artifact_for_run(session_id, team_id, run_id, artifact_id)


def _artifacts_for_run(session_id: str, team_id: str, run_id: str) -> list[dict[str, Any]] | None:
    return history_api.artifacts_for_run(session_id, team_id, run_id)


from blueprints import api_v1_assessment_action_launch as _api_v1_assessment_action_launch, api_v1_assessment_actions as _api_v1_assessment_actions, api_v1_assessment_checks as _api_v1_assessment_checks, api_v1_assessment_zap as _api_v1_assessment_zap, api_v1_assessments as _api_v1_assessments, api_v1_finding_evidence as _api_v1_finding_evidence, api_v1_http_profiles as _api_v1_http_profiles, api_v1_manual_findings as _api_v1_manual_findings, api_v1_notifications as _api_v1_notifications, api_v1_osv_lookup as _api_v1_osv_lookup, api_v1_verification_actions as _api_v1_verification_actions  # noqa: E402,F401,E501
from blueprints import api_v1_atlas_lookup as _api_v1_atlas_lookup  # noqa: E402,F401
from blueprints import api_v1_atlas_profile as _api_v1_atlas_profile, api_v1_read as _api_v1_read  # noqa: E402,F401
from blueprints import api_v1_run_evidence as _api_v1_run_evidence, api_v1_runs as _api_v1_runs, api_v1_schedules as _api_v1_schedules, api_v1_teams as _api_v1_teams, api_v1_watchers as _api_v1_watchers  # noqa: E402,F401,E501


def __getattr__(name: str):
    for module in (_api_v1_assessment_action_launch, _api_v1_assessment_actions, _api_v1_assessment_checks, _api_v1_assessment_zap, _api_v1_assessments, _api_v1_atlas_lookup, _api_v1_atlas_profile, _api_v1_finding_evidence, _api_v1_http_profiles, _api_v1_manual_findings, _api_v1_notifications, _api_v1_osv_lookup, _api_v1_read, _api_v1_run_evidence, _api_v1_runs, _api_v1_schedules, _api_v1_teams, _api_v1_verification_actions, _api_v1_watchers):  # noqa: E501
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(name)


def _run_started_payload(run_id: str, *, status: str = "running") -> dict[str, str]:
    return {
        "id": run_id,
        "status": status,
        "stream_url": f"/api/v1/runs/{run_id}/stream",
        "history_url": f"/api/v1/history/{run_id}",
    }
