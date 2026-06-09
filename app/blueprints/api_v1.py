"""Headless API v1 routes."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Iterable

from flask import Blueprint, Response, jsonify, request, send_file

from config import CFG
from core.database import DB_BACKEND, db_connect
from core.helpers import get_client_ip, get_log_session_id
from core.process import active_runs_for_session, active_runs_for_team, pid_for_session
from extensions import limiter
from services.api_v1.auth import ApiAuthError, current_api_session, require_api_auth
from services.api_v1.openapi import openapi_spec
from services.api_v1.serialization import artifact_summary, json_error, run_summary
from services.audit.automation import record_schedule_event, record_watcher_event, run_now_details
from services.audit.context import request_audit_fields, route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.commands.registry import (
    interactive_pty_spec_for_command,
    runtime_missing_command_message,
    split_command_argv,
)
from services.atlas.lookup import (
    atlas_summary,
    entity_detail,
    finding_detail,
    list_entities as list_atlas_entities,
    list_findings as list_atlas_findings,
    list_source_runs as list_atlas_source_runs,
)
from services.ai.assists import AIAssistRouteError, enqueue_next_commands_assist, enqueue_summary_assist, list_run_assists
from services.history.search import run_search_clause
from services.history.run_metadata import (
    history_offloaded_search_run_ids as _history_offloaded_search_run_ids,
    normalize_history_filter_text as _normalize_history_filter_text,
    run_atlas_counts_by_run as _run_atlas_counts_by_run,
    run_file_artifacts_by_run as _run_file_artifacts_by_run,
    run_metadata_counts_by_run as _run_metadata_counts_by_run,
)
from services.notifications.channels_store import (
    NotificationChannelError,
    create_notification_channel,
    delete_notification_channel,
    list_notification_channels,
    list_notification_events,
    notification_channel_kind_contract,
    send_test_notification,
    update_notification_channel,
)
from services.projects.artifacts import artifact_availability, artifact_owner_context
from services.projects.contracts import (
    ProjectWorkspaceError,
    ProjectWorkspaceNotFound,
    ProjectWorkspaceQuotaExceeded,
)
from services.projects.findings import list_project_findings
from services.projects.links import link_project_entity, unlink_project_entity
from services.projects.queries import (
    get_project,
    list_evidence_packages,
    list_project_entities,
    list_project_runs,
    list_projects_page,
)
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload
from services.runs.broker import (
    broker_available,
    broker_unavailable_reason,
    publish_run_event,
    stream_run_events,
)
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL
from services.runs.output_model import LineEvent, to_wire
from services.runs.output_store import load_run_output_events_for_run
from services.runs.start import (
    RunStartHandlers,
    RunStartRejected,
    start_brokered_run as _start_brokered_run_service,
)
from services.teams.capabilities import Capability, require_capability
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
from services.watchers.service import pause_team_watchers_and_schedules
from services.runs.structured_filters import (
    StructuredOutputFilters,
    entity_run_exists_clause,
    event_matches_structured_filters,
    filters_have_summary_selectors,
    filters_need_line_event_scan,
    filter_events,
    run_output_summary_exists_clause,
    structured_filters_from_params,
)
from services.scheduler.commands import ScheduleCommandValidationError, validate_schedule_command
from services.scheduler.cron import ScheduleCronError, next_fire
from services.scheduler.models import OWNER_KIND_WATCHER
from services.scheduler.route_helpers import (
    RouteBaselineRunNotCompleted,
    RouteBaselineRunNotFound,
    fire_schedule_now,
    fire_watcher_now,
    normalize_schedule_create_payload,
    normalize_schedule_update_payload,
    normalize_watcher_create_payload,
    normalize_watcher_update_payload,
)
from services.scheduler.serialization import get_user_schedule_for_owner, schedule_fire_payload, schedule_payload
from services.scheduler.service import (
    ScheduleError,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_for_owner as list_schedules_for_owner,
    list_schedule_fires,
    schedule_refs_by_run,
    update_schedule,
)
from services.secrets.vault import MasterKeyError, SecretDecryptError
from services.session.variables import SessionVariableError
from services.watchers.serialization import watcher_fire_payload, watcher_payload
from services.watchers.service import (
    WatcherError,
    accept_baseline,
    create_watcher,
    delete_watcher,
    get_watcher,
    list_for_owner as list_watchers_for_owner,
    list_watcher_fires,
    pause_watcher,
    resume_watcher,
    update_watcher,
)
from services.workspace.files import WorkspaceError, open_owner_workspace_file_for_download

from blueprints.run import (  # noqa: PLC0415
    _RunPreparationError,
    _RunSpawnError,
    _brokered_real_run_worker,
    _brokered_synthetic_run,
    _filter_builtin_command_events,
    _history_safe_command_for_storage,
    _prepare_command_input,
    _prepare_real_command,
    _signal_process_group,
    _start_real_command_process,
    _workspace_cwd_value,
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
        "status": status_code,
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
        status=status,
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
        "status": status,
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
        "status": status,
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
        "status": exc.status_code,
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


def _run_owner_clause(session_id: str, team_id: str, *, alias: str = "r") -> tuple[str, list[Any]]:
    prefix = f"{alias}." if alias else ""
    if team_id:
        return f"{prefix}team_id = ?", [team_id]
    return f"{prefix}session_id = ? AND ({prefix}team_id IS NULL OR {prefix}team_id = '')", [session_id]


def _apply_schedule_ref(run: dict[str, Any], schedule_ref: dict[str, str] | None) -> None:
    ref = schedule_ref or {}
    schedule_id = str(ref.get("schedule_id") or "")
    owner_kind = str(ref.get("owner_kind") or "")
    owner_id = str(ref.get("owner_id") or "")
    run["schedule_id"] = schedule_id
    run["scheduled"] = bool(schedule_id)
    run["schedule_owner_kind"] = owner_kind
    run["schedule_owner_id"] = owner_id
    run["watcher_id"] = owner_id if owner_kind == OWNER_KIND_WATCHER else ""
    run["schedule_label"] = str(ref.get("watcher_label" if owner_kind == OWNER_KIND_WATCHER else "schedule_label") or "")


def _project_owner_clause(session_id: str, team_id: str, *, alias: str = "p") -> tuple[str, list[Any]]:
    prefix = f"{alias}." if alias else ""
    if team_id:
        return f"{prefix}team_id = ?", [team_id]
    return f"{prefix}session_id = ? AND ({prefix}team_id IS NULL OR {prefix}team_id = '')", [session_id]


def _active_runs_for_owner(session_id: str, team_id: str = "", client_id: str = "") -> list[dict[str, Any]]:
    if team_id:
        return active_runs_for_team(team_id, client_id=client_id)
    return active_runs_for_session(session_id, client_id=client_id, team_id="")


def _run_status_from_active_or_row(run_id: str, session_id: str, team_id: str = "") -> dict[str, Any] | None:
    for active in _active_runs_for_owner(session_id, team_id):
        if str(active.get("run_id") or "") == run_id:
            return _active_run_summary(active)
    with db_connect() as conn:
        scope_sql, scope_params = _run_owner_clause(session_id, team_id, alias="")
        row = conn.execute(
            f"SELECT * FROM runs WHERE {scope_sql} AND id = ?",  # nosec
            (*scope_params, run_id),
        ).fetchone()
        if not row:
            return None
        run = dict(row)
        artifacts = _run_file_artifacts_by_run(conn, [run_id]).get(run_id, [])
        run["artifact_count"] = len(artifacts)
        run.update(_run_metadata_counts_by_run(conn, [run_id]).get(run_id, {}))
        run.update(_run_atlas_counts_by_run(conn, session_id, [run_id], team_id=team_id).get(run_id, {}))
    return run_summary(run)


def _active_run_summary(active: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(active.get("run_id") or ""),
        "command": str(active.get("command") or ""),
        "started": active.get("started"),
        "finished": None,
        "status": "running",
        "exit_code": None,
        "run_kind": str(active.get("run_type") or "command"),
        "output_line_count": 0,
        "preview_truncated": False,
        "full_output_available": False,
        "full_output_truncated": False,
        "artifact_count": 0,
        "finding_count": 0,
        "atlas_entity_count": 0,
        "atlas_finding_count": 0,
    }


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
    scope_sql, scope_params = _run_owner_clause(session_id, team_id)
    where = [scope_sql]
    params: list[Any] = list(scope_params)
    if filters["run_kind"]:
        where.append("r.run_kind = ?")
        params.append(filters["run_kind"])
    if filters["project_id"]:
        project_scope_sql, project_scope_params = _project_owner_clause(session_id, team_id)
        where.append(
            "EXISTS (SELECT 1 FROM project_links pl JOIN projects p ON p.id = pl.project_id "
            f"WHERE {project_scope_sql} AND p.id = ? AND pl.entity_type = 'run' AND pl.entity_id = r.id)"  # nosec
        )
        params.extend([*project_scope_params, filters["project_id"]])
    if filters["exit_code"]:
        try:
            where.append("r.exit_code = ?")
            params.append(int(filters["exit_code"]))
        except ValueError:
            pass
    if filters["since"]:
        where.append("r.started >= ?")
        params.append(filters["since"])
    if filters["until"]:
        where.append("r.started <= ?")
        params.append(filters["until"])
    if filters["q"]:
        search = run_search_clause(DB_BACKEND, filters["q"], search_scope, alias="r", postgres_placeholder="?")
        if search.predicate_sql:
            if offloaded_ids:
                placeholders = ",".join("?" for _ in offloaded_ids)
                where.append(f"(({search.predicate_sql}) OR r.id IN ({placeholders}))")
                params.extend(search.params)
                params.extend(offloaded_ids)
            else:
                where.append(search.predicate_sql)
                params.extend(search.params)
    return " WHERE " + " AND ".join(where), params


def _history_search_candidate_runs(
    session_id: str,
    team_id: str,
    filters: dict[str, str],
    structured_filters: StructuredOutputFilters,
) -> list[dict[str, Any]]:
    offloaded_ids: list[str] = []
    if filters["q"]:
        with db_connect() as conn:
            offloaded_ids = _history_offloaded_search_run_ids(
                conn,
                session_id,
                team_id,
                filters["q"],
                "",
                "",
                "",
                filters["project_id"],
                run_kind=filters["run_kind"] or "all",
            )
    with db_connect() as conn:
        where_sql, params = _history_where(
            session_id,
            team_id,
            filters,
            offloaded_ids=offloaded_ids,
            search_scope="all",
        )
        entity_sql, entity_params = entity_run_exists_clause(structured_filters, run_alias="r")
        if entity_sql:
            where_sql += entity_sql
            params = [*params, *entity_params]
        summary_sql, summary_params = run_output_summary_exists_clause(structured_filters, run_alias="r")
        if summary_sql:
            where_sql += summary_sql
            params = [*params, *summary_params]
        rows = conn.execute(
            "SELECT r.*, ("  # nosec
            "SELECT art.rel_path FROM run_output_artifacts art "
            "WHERE art.run_id = r.id ORDER BY art.created DESC LIMIT 1"
            ") AS rel_path FROM runs r"
            + where_sql
            + " ORDER BY r.started DESC, r.id DESC",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def _run_output_search_matches(
    run: dict[str, Any],
    query: str,
    context: int,
    structured_filters: StructuredOutputFilters,
) -> list[dict[str, Any]]:
    needle = query.casefold()
    events = _run_output_events(run)
    lines = [event.text for event in events]
    matches: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        line = event.text
        if needle and needle not in line.casefold():
            continue
        if structured_filters.active and not event_matches_structured_filters(event, structured_filters):
            continue
        before_start = max(0, index - context)
        after_end = min(len(lines), index + context + 1)
        matches.append({
            "run_id": str(run.get("id") or ""),
            "command": str(run.get("command") or ""),
            "started": run.get("started"),
            "finished": run.get("finished"),
            "line_number": index + 1,
            "line": line,
            "kind": event.kind.value,
            "role": event.role.value,
            "signals": [signal.value for signal in event.signals],
            "entities": [entity.to_wire() for entity in event.entities],
            "context_before": lines[before_start:index],
            "context_after": lines[index + 1:after_end],
        })
    return matches


def _history_output_search(
    session_id: str,
    team_id: str,
    query: str,
    context: int,
    structured_filters: StructuredOutputFilters,
) -> list[dict[str, Any]]:
    filters = _history_filters()
    filters["q"] = query
    matches: list[dict[str, Any]] = []
    for run in _history_search_candidate_runs(session_id, team_id, filters, structured_filters):
        matches.extend(_run_output_search_matches(run, query, context, structured_filters))
    return matches


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
    structured_filters: StructuredOutputFilters | None = None,
):
    offloaded_ids: list[str] = []
    if filters["q"]:
        with db_connect() as conn:
            offloaded_ids = _history_offloaded_search_run_ids(
                conn,
                session_id,
                team_id,
                filters["q"],
                "",
                "",
                "",
                filters["project_id"],
                run_kind=filters["run_kind"] or "all",
            )
    with db_connect() as conn:
        where_sql, params = _history_where(session_id, team_id, filters, offloaded_ids=offloaded_ids)
        if structured_filters and structured_filters.active:
            entity_sql, entity_params = entity_run_exists_clause(structured_filters, run_alias="r")
            if entity_sql:
                where_sql += entity_sql
                params = [*params, *entity_params]
            summary_sql, summary_params = run_output_summary_exists_clause(structured_filters, run_alias="r")
            if summary_sql:
                where_sql += summary_sql
                params = [*params, *summary_params]
            needs_line_scan = filters_need_line_event_scan(structured_filters) or (
                filters_have_summary_selectors(structured_filters) and not summary_sql
            )
            if needs_line_scan:
                rows = conn.execute(
                    "SELECT r.*, ("  # nosec
                    "SELECT art.rel_path FROM run_output_artifacts art "
                    "WHERE art.run_id = r.id ORDER BY art.created DESC LIMIT 1"
                    ") AS rel_path FROM runs r"
                    + where_sql
                    + " ORDER BY r.started DESC LIMIT 2000",
                    params,
                ).fetchall()
                matching_runs = [dict(row) for row in rows]
                matching_runs = [
                    run for run in matching_runs
                    if any(event_matches_structured_filters(event, structured_filters) for event in _run_output_events(run))
                ]
                total = len(matching_runs)
                runs = matching_runs[offset:offset + limit]
            else:
                total_row = conn.execute("SELECT COUNT(*) AS count FROM runs r" + where_sql, params).fetchone()  # nosec B608
                total = int(total_row["count"] or 0) if total_row else 0
                rows = conn.execute(
                    "SELECT r.id, r.run_kind, r.command, r.started, r.finished, r.exit_code, "  # nosec
                    "r.preview_truncated, r.output_line_count, r.full_output_available, r.full_output_truncated "
                    "FROM runs r"
                    + where_sql
                    + " ORDER BY r.started DESC LIMIT ? OFFSET ?",
                    (*params, limit, offset),
                ).fetchall()
                runs = [dict(row) for row in rows]
        else:
            total_row = conn.execute("SELECT COUNT(*) AS count FROM runs r" + where_sql, params).fetchone()  # nosec B608
            total = int(total_row["count"] or 0) if total_row else 0
            rows = conn.execute(
                "SELECT r.id, r.run_kind, r.command, r.started, r.finished, r.exit_code, "  # nosec
                "r.preview_truncated, r.output_line_count, r.full_output_available, r.full_output_truncated "
                "FROM runs r"
                + where_sql
                + " ORDER BY r.started DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            runs = [dict(row) for row in rows]
        run_ids = [str(run["id"]) for run in runs]
        artifacts = _run_file_artifacts_by_run(conn, run_ids)
        metadata = _run_metadata_counts_by_run(conn, run_ids)
        atlas = _run_atlas_counts_by_run(conn, session_id, run_ids, team_id=team_id)
        scheduled = schedule_refs_by_run(conn, run_ids)
    for run in runs:
        run_id = str(run["id"])
        run["artifact_count"] = len(artifacts.get(run_id, []))
        run.update(metadata.get(run_id, {}))
        run.update(atlas.get(run_id, {}))
        _apply_schedule_ref(run, scheduled.get(run_id))
    return runs, total


def _load_run_detail(session_id: str, team_id: str, run_id: str) -> dict[str, Any] | None:
    with db_connect() as conn:
        scope_sql, scope_params = _run_owner_clause(session_id, team_id, alias="runs")
        row = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            f"WHERE {scope_sql} AND runs.id = ?",  # nosec
            (*scope_params, run_id),
        ).fetchone()
        if not row:
            return None
        run = dict(row)
        artifacts = _run_file_artifacts_by_run(conn, [run_id]).get(run_id, [])
        run["artifacts"] = artifacts
        run["artifact_count"] = len(artifacts)
        run.update(_run_metadata_counts_by_run(conn, [run_id]).get(run_id, {}))
        run.update(_run_atlas_counts_by_run(conn, session_id, [run_id], team_id=team_id).get(run_id, {}))
        _apply_schedule_ref(run, schedule_refs_by_run(conn, [run_id]).get(run_id))
    return run


def _run_output_events(run: dict[str, Any], *, full: bool = True) -> list[LineEvent]:
    result = load_run_output_events_for_run(
        run,
        prefer_full=full,
        log_event="API_FULL_OUTPUT_LOAD_FAILED",
    )
    run["_output_source"] = result.source
    run["_output_fallback"] = result.fallback
    return result.events


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
    with db_connect() as conn:
        scope_sql, scope_params = _run_owner_clause(session_id, team_id, alias="")
        run_row = conn.execute(
            f"SELECT session_id, team_id FROM runs WHERE {scope_sql} AND id = ?",  # nosec
            (*scope_params, run_id),
        ).fetchone()
        if not run_row:
            return None
        row = conn.execute(
            "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
            "detected_by, content_type, preview_type, content_sha256, created, ? AS run_team_id "
            "FROM run_file_artifacts WHERE run_id = ? AND id = ?",
            (str(run_row["team_id"] or ""), run_id, artifact_id),
        ).fetchone()
    if not row:
        return None
    artifact = dict(row)
    owner_context = artifact_owner_context(str(artifact.get("session_id") or ""), artifact)
    artifact.update(artifact_availability(str(artifact.get("session_id") or ""), artifact, owner_context=owner_context))
    return artifact


def _artifacts_for_run(session_id: str, team_id: str, run_id: str) -> list[dict[str, Any]] | None:
    with db_connect() as conn:
        scope_sql, scope_params = _run_owner_clause(session_id, team_id, alias="")
        run_row = conn.execute(
            f"SELECT session_id, team_id FROM runs WHERE {scope_sql} AND id = ?",  # nosec
            (*scope_params, run_id),
        ).fetchone()
        if not run_row:
            return None
        rows = conn.execute(
            "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
            "detected_by, content_type, preview_type, content_sha256, created, ? AS run_team_id "
            "FROM run_file_artifacts WHERE run_id = ? "
            "ORDER BY created ASC, workspace_path ASC",
            (str(run_row["team_id"] or ""), run_id),
        ).fetchall()
    artifacts = []
    for row in rows:
        artifact = dict(row)
        owner_context = artifact_owner_context(str(artifact.get("session_id") or ""), artifact)
        artifact.update(artifact_availability(str(artifact.get("session_id") or ""), artifact, owner_context=owner_context))
        artifacts.append(artifact_summary(artifact))
    return artifacts


def _sse_after_id() -> str:
    explicit = str(request.args.get("after") or "").strip()
    if explicit:
        return explicit
    return str(request.headers.get("Last-Event-ID") or "0-0").strip() or "0-0"


def _log_api_run_stream_error(
    exc: Exception,
    *,
    run_id: str,
    session_id: str,
    team_id: str = "",
    stream_format: str = "sse",
    ip: str = "",
    route: str = "",
    method: str = "",
) -> None:
    log.error(
        "API_RUN_STREAM_ERROR",
        extra={
            "ip": ip,
            "session": get_log_session_id(session_id),
            "run_id": run_id,
            "team_id": team_id,
            "route": route,
            "method": method,
            "format": stream_format,
        },
        exc_info=True,
    )


def _ndjson_from_sse_chunks(
    chunks: Iterable[str],
    *,
    run_id: str = "",
    session_id: str = "",
    team_id: str = "",
    ip: str = "",
    route: str = "",
    method: str = "",
):
    try:
        for chunk in chunks:
            if not chunk:
                continue
            for part in chunk.split("\n\n"):
                lines = part.splitlines()
                if lines and all(line.startswith(":") for line in lines if line):
                    yield json.dumps({"type": "heartbeat"}, separators=(",", ":")) + "\n"
                    continue
                data_lines = []
                event_id = ""
                event_type = ""
                for line in lines:
                    if line.startswith("id:"):
                        event_id = line[3:].strip()
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    if line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                if not data_lines:
                    continue
                data = "\n".join(data_lines)
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    yield data + "\n"
                    continue
                if isinstance(payload, dict):
                    if event_type:
                        payload.setdefault("event", event_type)
                    if event_id:
                        payload.setdefault("event_id", event_id)
                yield json.dumps(payload, separators=(",", ":")) + "\n"
    except Exception as exc:
        if run_id or session_id or team_id:
            _log_api_run_stream_error(
                exc,
                run_id=run_id,
                session_id=session_id,
                team_id=team_id,
                stream_format="ndjson",
                ip=ip,
                route=route,
                method=method,
            )
        yield json.dumps({
            "event": "error",
            "code": "stream_error",
            "message": str(exc) or "Run stream interrupted.",
        }) + "\n"


def _sse_chunks_with_error_logging(
    chunks: Iterable[str],
    *,
    run_id: str,
    session_id: str,
    team_id: str,
    ip: str,
    route: str,
    method: str,
):
    try:
        yield from chunks
    except Exception as exc:
        _log_api_run_stream_error(
            exc,
            run_id=run_id,
            session_id=session_id,
            team_id=team_id,
            stream_format="sse",
            ip=ip,
            route=route,
            method=method,
        )
        payload = json.dumps({
            "event": "error",
            "code": "stream_error",
            "message": str(exc) or "Run stream interrupted.",
        }, separators=(",", ":"))
        yield f"event: error\ndata: {payload}\n\n"


@api_v1_bp.route("/teams", methods=["GET"])
@limiter.limit(_api_team_read_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_list():
    session_id = _require_session_id()
    with db_connect() as conn:
        teams = team_storage.list_teams_for_token(conn, session_id)
    return jsonify({"teams": teams})


@api_v1_bp.route("/teams", methods=["POST"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_create():
    session_id = _require_session_id()
    data = _json_body()
    try:
        with db_connect() as conn:
            team, recovery = team_storage.create_team_with_recovery_code(
                conn,
                name=str(data.get("name") or ""),
                slug=str(data.get("slug") or ""),
                creator_session_token=session_id,
                display_name=str(data.get("display_name") or ""),
            )
            detail = team_storage.team_detail(conn, team["id"], current_session_token=session_id)
            _record_api_team_audit(
                AuditEventType.TEAM_CREATE,
                session_token=session_id,
                team_id=team["id"],
                actor_member_id=team.get("creator_member_id", ""),
                actor_role="owner",
                details={"role": "owner"},
                conn=conn,
            )
            conn.commit()
        _log_api_team_event(
            "create",
            session_token=session_id,
            team_id=team["id"],
            actor_member_id=team.get("creator_member_id", ""),
            actor_role="owner",
        )
        return jsonify({"team": (detail or {}).get("team", {}), "recovery_code": recovery["code"]}), 201
    except Exception as exc:
        return _log_api_team_exception("create", exc, session_token=session_id)


@api_v1_bp.route("/teams/<team_id>", methods=["GET"])
@limiter.limit(_api_team_read_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_detail(team_id: str):
    session_id = _require_session_id()
    actor = None
    try:
        with db_connect() as conn:
            actor = _api_team_member(conn, team_id, session_id)
            detail = team_storage.team_detail(conn, team_id, current_session_token=session_id)
        if not detail:
            raise TeamNotFound("Team not found.")
        return jsonify(detail)
    except Exception as exc:
        return _log_api_team_exception("detail", exc, session_token=session_id, team_id=team_id, actor=actor)


@api_v1_bp.route("/teams/<team_id>", methods=["PATCH"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_update(team_id: str):
    session_id = _require_session_id()
    data = _json_body()
    actor = None
    try:
        with db_connect() as conn:
            actor = _api_team_member(conn, team_id, session_id)
            require_capability(actor["role"], Capability.ARCHIVE_TEAM)
            status = str(data.get("status") or "").strip().lower()
            team = team_storage.update_team_status(conn, team_id, status=status)
            paused = {"watchers": 0, "schedules": 0}
            if status == "archived":
                paused = pause_team_watchers_and_schedules(conn, team_id, reason="team_archived")
            detail = team_storage.team_detail(conn, team_id, current_session_token=session_id)
            event_type = AuditEventType.TEAM_ARCHIVE if status == "archived" else AuditEventType.TEAM_REACTIVATE
            _record_api_team_audit(
                event_type,
                session_token=session_id,
                team_id=team_id,
                actor=actor,
                details={
                    "status": team["status"],
                    "to_state": team["status"],
                    "paused_watchers": paused["watchers"],
                    "paused_schedules": paused["schedules"],
                },
                conn=conn,
            )
            conn.commit()
        if status == "archived":
            log.info(
                "TEAM_ARCHIVE_AUTOMATION_PAUSED",
                extra=_api_team_log_fields(
                    "archive_automation_paused",
                    session_token=session_id,
                    team_id=team_id,
                    actor=actor,
                    status=team["status"],
                    paused_watchers=paused["watchers"],
                    paused_schedules=paused["schedules"],
                ),
            )
        _log_api_team_event(
            "update",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            status=team["status"],
            paused_watchers=paused["watchers"],
            paused_schedules=paused["schedules"],
        )
        return jsonify(detail or {"team": team})
    except Exception as exc:
        return _log_api_team_exception("update", exc, session_token=session_id, team_id=team_id, actor=actor)


@api_v1_bp.route("/teams/<team_id>/invites", methods=["POST"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_invites_create(team_id: str):
    session_id = _require_session_id()
    data = _json_body()
    actor = None
    try:
        with db_connect() as conn:
            actor = _api_team_member(conn, team_id, session_id)
            team_storage.require_active_team(conn, team_id)
            role = str(data.get("role") or "operator").strip()
            require_capability(actor["role"], Capability.MANAGE_OWNERS if role == "owner" else Capability.MANAGE_INVITES)
            invite = team_storage.create_team_invite_with_code(
                conn,
                team_id=team_id,
                role=role,
                created_by_member_id=actor["id"],
                expires_at=str(data.get("expires_at") or ""),
                max_uses=int(data.get("max_uses") or 1),
                label=str(data.get("label") or ""),
            )
            _record_api_team_audit(
                AuditEventType.TEAM_INVITE,
                session_token=session_id,
                team_id=team_id,
                actor=actor,
                details={"target_invite_id": invite["id"], "role": role},
                conn=conn,
            )
            conn.commit()
        _log_api_team_event(
            "invite_create",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_invite_id=invite["id"],
        )
        return jsonify({"invite": invite}), 201
    except Exception as exc:
        return _log_api_team_exception("invite_create", exc, session_token=session_id, team_id=team_id, actor=actor)


@api_v1_bp.route("/teams/<team_id>/invites/<invite_id>", methods=["DELETE"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_invites_revoke(team_id: str, invite_id: str):
    session_id = _require_session_id()
    actor = None
    try:
        with db_connect() as conn:
            actor = _api_team_member(conn, team_id, session_id)
            team_storage.require_active_team(conn, team_id)
            require_capability(actor["role"], Capability.MANAGE_INVITES)
            invite = conn.execute("SELECT team_id FROM team_invites WHERE id = ?", (invite_id,)).fetchone()
            if not invite or str(invite["team_id"] or "") != team_id:
                raise TeamNotFound("Team invite not found.")
            removed = team_storage.revoke_team_invite(conn, invite_id)
            if removed:
                _record_api_team_audit(
                    AuditEventType.TEAM_REVOKE,
                    session_token=session_id,
                    team_id=team_id,
                    actor=actor,
                    details={"target_invite_id": invite_id, "kind": "invite"},
                    conn=conn,
                )
            conn.commit()
        _log_api_team_event(
            "invite_revoke",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_invite_id=invite_id,
            result="ok" if removed else "not_found",
        )
        return jsonify({"removed": removed})
    except Exception as exc:
        return _log_api_team_exception(
            "invite_revoke",
            exc,
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_invite_id=invite_id,
        )


@api_v1_bp.route("/teams/join", methods=["POST"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_join():
    session_id = _require_session_id()
    data = _json_body()
    try:
        with db_connect() as conn:
            member = team_storage.redeem_team_invite(
                conn,
                code=str(data.get("code") or ""),
                session_token=session_id,
                display_name=str(data.get("display_name") or ""),
            )
            detail = team_storage.team_detail(conn, member["team_id"], current_session_token=session_id)
            _record_api_team_audit(
                AuditEventType.TEAM_JOIN,
                session_token=session_id,
                team_id=member["team_id"],
                actor_member_id=member["id"],
                actor_role=str(member.get("role") or ""),
                actor_display_name=str(member.get("display_name") or ""),
                details={"target_member_id": member["id"], "role": str(member.get("role") or ""), "kind": "invite"},
                conn=conn,
            )
            conn.commit()
        _log_api_team_event(
            "invite_redeem",
            session_token=session_id,
            team_id=member["team_id"],
            actor_member_id=member["id"],
            actor_role=member.get("role", ""),
        )
        return jsonify(detail or {"member": member}), 201
    except Exception as exc:
        return _log_api_team_exception("invite_redeem", exc, session_token=session_id)


@api_v1_bp.route("/teams/<team_id>/members/<member_id>", methods=["PATCH"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_members_update(team_id: str, member_id: str):
    session_id = _require_session_id()
    data = _json_body()
    actor = None
    try:
        with db_connect() as conn:
            actor = _api_team_member(conn, team_id, session_id)
            team_storage.require_active_team(conn, team_id)
            target = team_storage.get_member(conn, member_id)
            if not target or target["team_id"] != team_id:
                raise TeamNotFound("Team member not found.")
            new_role = str(data.get("role") or target["role"]).strip()
            if target["role"] == "owner" or new_role == "owner":
                require_capability(actor["role"], Capability.MANAGE_OWNERS)
            elif actor["id"] != member_id:
                require_capability(actor["role"], Capability.MANAGE_MEMBERS)
            member = team_storage.update_team_member(
                conn,
                member_id,
                role=new_role if "role" in data else None,
                display_name=str(data.get("display_name")) if "display_name" in data else None,
            )
            if not member:
                raise TeamNotFound("Team member not found.")
            if "role" in data and str(target["role"] or "") != str(member["role"] or ""):
                _record_api_team_audit(
                    AuditEventType.TEAM_ROLE_CHANGE,
                    session_token=session_id,
                    team_id=team_id,
                    actor=actor,
                    details={
                        "target_member_id": member_id,
                        "from_role": str(target["role"] or ""),
                        "to_role": str(member["role"] or ""),
                    },
                    conn=conn,
                )
            conn.commit()
        _log_api_team_event(
            "member_update",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )
        return jsonify({"member": team_storage.public_member(member)})
    except Exception as exc:
        return _log_api_team_exception(
            "member_update",
            exc,
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )


@api_v1_bp.route("/teams/<team_id>/members/<member_id>", methods=["DELETE"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_members_remove(team_id: str, member_id: str):
    session_id = _require_session_id()
    actor = None
    try:
        with db_connect() as conn:
            actor = _api_team_member(conn, team_id, session_id)
            team_storage.require_active_team(conn, team_id)
            target = team_storage.get_member(conn, member_id)
            if not target or target["team_id"] != team_id:
                raise TeamNotFound("Team member not found.")
            if target["role"] == "owner":
                require_capability(actor["role"], Capability.MANAGE_OWNERS)
            elif actor["id"] != member_id:
                require_capability(actor["role"], Capability.MANAGE_MEMBERS)
            removed = team_storage.soft_remove_team_member(conn, member_id)
            if removed:
                _record_api_team_audit(
                    AuditEventType.TEAM_MEMBER_REMOVE,
                    session_token=session_id,
                    team_id=team_id,
                    actor=actor,
                    details={"target_member_id": member_id, "role": str(target["role"] or "")},
                    conn=conn,
                )
            conn.commit()
        _log_api_team_event(
            "member_remove",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )
        return jsonify({"removed": removed})
    except Exception as exc:
        return _log_api_team_exception(
            "member_remove",
            exc,
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )


@api_v1_bp.route("/teams/<team_id>/leave", methods=["POST"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_leave(team_id: str):
    session_id = _require_session_id()
    actor = None
    try:
        with db_connect() as conn:
            actor = _api_team_member(conn, team_id, session_id)
            removed = team_storage.soft_remove_team_member(conn, actor["id"])
            if removed:
                _record_api_team_audit(
                    AuditEventType.TEAM_LEAVE,
                    session_token=session_id,
                    team_id=team_id,
                    actor=actor,
                    details={"target_member_id": actor["id"], "role": str(actor.get("role") or "")},
                    conn=conn,
                )
            conn.commit()
        _log_api_team_event("leave", session_token=session_id, team_id=team_id, actor=actor)
        return jsonify({"removed": removed})
    except Exception as exc:
        return _log_api_team_exception("leave", exc, session_token=session_id, team_id=team_id, actor=actor)


@api_v1_bp.route("/teams/<team_id>/recovery/rotate", methods=["POST"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_recovery_rotate(team_id: str):
    session_id = _require_session_id()
    actor = None
    try:
        with db_connect() as conn:
            actor = _api_team_member(conn, team_id, session_id)
            team_storage.require_active_team(conn, team_id)
            require_capability(actor["role"], Capability.MANAGE_RECOVERY)
            recovery = team_storage.rotate_team_recovery_code(
                conn,
                team_id=team_id,
                created_by_member_id=actor["id"],
            )
            _record_api_team_audit(
                AuditEventType.TEAM_RECOVERY_ROTATE,
                session_token=session_id,
                team_id=team_id,
                actor=actor,
                details={"target_recovery_id": recovery["id"]},
                conn=conn,
            )
            conn.commit()
        _log_api_team_event(
            "recovery_rotate",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_recovery_id=recovery["id"],
        )
        return jsonify({"recovery_code": recovery["code"], "recovery": recovery})
    except Exception as exc:
        return _log_api_team_exception(
            "recovery_rotate",
            exc,
            session_token=session_id,
            team_id=team_id,
            actor=actor,
        )


@api_v1_bp.route("/teams/recovery/redeem", methods=["POST"])
@limiter.limit(_api_team_write_route_limit, key_func=_api_team_rate_limit_key)
@require_api_auth
def api_teams_recovery_redeem():
    session_id = _require_session_id()
    data = _json_body()
    try:
        with db_connect() as conn:
            member = team_storage.redeem_team_recovery_code(
                conn,
                code=str(data.get("code") or ""),
                session_token=session_id,
                display_name=str(data.get("display_name") or ""),
            )
            detail = team_storage.team_detail(conn, member["team_id"], current_session_token=session_id)
            _record_api_team_audit(
                AuditEventType.TEAM_RECOVERY_REDEEM,
                session_token=session_id,
                team_id=member["team_id"],
                actor_member_id=member["id"],
                actor_role=str(member.get("role") or ""),
                actor_display_name=str(member.get("display_name") or ""),
                details={
                    "target_member_id": member["id"],
                    "role": str(member.get("role") or ""),
                    "kind": "recovery",
                },
                conn=conn,
            )
            conn.commit()
        _log_api_team_event(
            "recovery_redeem",
            session_token=session_id,
            team_id=member["team_id"],
            actor_member_id=member["id"],
            actor_role=member.get("role", ""),
        )
        return jsonify(detail or {"member": member})
    except Exception as exc:
        return _log_api_team_exception("recovery_redeem", exc, session_token=session_id)


@api_v1_bp.route("/health")
def api_health():
    return jsonify({"ok": True, "version": openapi_spec()["info"]["version"]})


@api_v1_bp.route("/openapi.json")
def api_openapi():
    log.debug("API_OPENAPI_FETCHED", extra={"ip": get_client_ip()})
    return jsonify(openapi_spec())


@api_v1_bp.route("/whoami")
@require_api_auth
def api_whoami():
    session = current_api_session()
    return jsonify({
        "token_created": session.created,
        "last_seen_at": session.last_seen_at,
    })


@api_v1_bp.route("/history")
@require_api_auth
def api_history():
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    filters = _history_filters()
    filters["q"], structured_filters = structured_filters_from_params(request.args, query=filters["q"])
    runs, total = _history_rows(session_id, owner_scope.team_id, limit, offset, filters, structured_filters)
    return jsonify(page_payload("runs", [run_summary(run) for run in runs], total, limit, offset))


@api_v1_bp.route("/history/search")
@require_api_auth
def api_history_search():
    query, structured_filters = structured_filters_from_params(
        request.args,
        query=_normalize_history_filter_text(request.args.get("q")),
    )
    if not query and not structured_filters.active:
        return _api_json_error("missing_query", "q is required.", 400)
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    context = _parse_int(request.args.get("context"), 2, minimum=0, maximum=10)
    matches = _history_output_search(session_id, owner_scope.team_id, query, context, structured_filters)
    page = matches[offset:offset + limit]
    return jsonify(page_payload(
        "matches",
        page,
        len(matches),
        limit,
        offset,
        extra={
            "query": query,
            "context": context,
            "filters": _structured_filters_payload(structured_filters),
        },
    ))


@api_v1_bp.route("/atlas")
@require_api_auth
def api_atlas_summary():
    owner_scope = _api_request_scope()
    with db_connect() as conn:
        return jsonify(atlas_summary(
            conn,
            _require_session_id(),
            team_id=owner_scope.team_id,
            run_id=request.args.get("run_id") or "",
            project_id=request.args.get("project_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
        ))


@api_v1_bp.route("/atlas/runs")
@require_api_auth
def api_atlas_runs():
    owner_scope = _api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 30, 50)
    with db_connect() as conn:
        return jsonify(list_atlas_source_runs(
            conn,
            _require_session_id(),
            team_id=owner_scope.team_id,
            query=request.args.get("q") or "",
            run_id=request.args.get("run_id") or "",
            limit=limit,
        ))


@api_v1_bp.route("/atlas/entities")
@require_api_auth
def api_atlas_entities():
    owner_scope = _api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 50, 200)
    offset = normalize_page_offset(request.args.get("offset"))
    entity_type = request.args.get("entity_type") or request.args.get("type") or ""
    with db_connect() as conn:
        return jsonify(list_atlas_entities(
            conn,
            _require_session_id(),
            team_id=owner_scope.team_id,
            entity_type=entity_type,
            query=request.args.get("q") or "",
            project_id=request.args.get("project_id") or "",
            run_id=request.args.get("run_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
            limit=limit,
            offset=offset,
        ))


@api_v1_bp.route("/atlas/entities/<entity_id>")
@require_api_auth
def api_atlas_entity(entity_id):
    owner_scope = _api_request_scope()
    runs_offset = normalize_page_offset(request.args.get("runs_offset"))
    findings_offset = normalize_page_offset(request.args.get("findings_offset"))
    with db_connect() as conn:
        detail = entity_detail(
            conn,
            _require_session_id(),
            entity_id,
            team_id=owner_scope.team_id,
            runs_offset=runs_offset,
            findings_offset=findings_offset,
        )
    if detail is None:
        return _api_json_error("not_found", "Atlas entity not found.", 404)
    return jsonify(detail)


@api_v1_bp.route("/atlas/findings")
@require_api_auth
def api_atlas_findings():
    owner_scope = _api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 50, 200)
    offset = normalize_page_offset(request.args.get("offset"))
    review_states = request.args.getlist("review_state") or request.args.getlist("status")
    with db_connect() as conn:
        return jsonify(list_atlas_findings(
            conn,
            _require_session_id(),
            team_id=owner_scope.team_id,
            query=request.args.get("q") or "",
            project_id=request.args.get("project_id") or "",
            run_id=request.args.get("run_id") or "",
            review_states=review_states,
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
            limit=limit,
            offset=offset,
        ))


@api_v1_bp.route("/atlas/findings/<finding_id>")
@require_api_auth
def api_atlas_finding(finding_id):
    owner_scope = _api_request_scope()
    with db_connect() as conn:
        detail = finding_detail(conn, _require_session_id(), finding_id, team_id=owner_scope.team_id)
    if detail is None:
        return _api_json_error("not_found", "Atlas finding not found.", 404)
    return jsonify(detail)


@api_v1_bp.route("/history/<run_id>")
@require_api_auth
def api_history_run(run_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    run = _load_run_detail(session_id, owner_scope.team_id, run_id)
    if run is None:
        return _api_json_error("not_found", "Run not found.", 404)
    detail = run_summary(run)
    detail["artifacts"] = [artifact_summary(artifact) for artifact in run.get("artifacts", [])]
    return jsonify({"run": detail})


@api_v1_bp.route("/history/<run_id>/output")
@api_v1_bp.route("/runs/<run_id>/output")
@require_api_auth
def api_history_run_output(run_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    run = _load_run_detail(session_id, owner_scope.team_id, run_id)
    if run is None:
        return _api_json_error("not_found", "Run not found.", 404)
    _, structured_filters = structured_filters_from_params(request.args)
    events = _run_output_events(run)
    try:
        line_range = _parse_output_range(request.args.get("range"))
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    ranged_events = _slice_output_events(events, line_range)
    filtered_events = filter_events(ranged_events, structured_filters)
    all_lines = [event.text for event in events]
    lines = [event.text for event in filtered_events]
    if str(request.args.get("format") or "text").lower() == "json":
        payload = {
            "run_id": run_id,
            "preview": run.get("_output_source") != "full",
            "full_output_available": bool(run.get("full_output_available")),
            "truncated": bool(run.get("preview_truncated") or run.get("full_output_truncated")),
            "line_count": len(all_lines),
            "returned": len(lines),
            "lines": lines,
            "entries": [to_wire(event) for event in filtered_events],
        }
        if line_range is not None:
            payload["range"] = {"start": line_range[0], "end": line_range[1], "returned": len(lines)}
        if structured_filters.active:
            payload["filters"] = _structured_filters_payload(structured_filters)
        return jsonify(payload)
    return Response("\n".join(lines), mimetype="text/plain; charset=utf-8")


@api_v1_bp.route("/history/<run_id>/artifacts")
@require_api_auth
def api_history_run_artifacts(run_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    artifacts = _artifacts_for_run(session_id, owner_scope.team_id, run_id)
    if artifacts is None:
        return _api_json_error("not_found", "Run not found.", 404)
    return jsonify({"artifacts": artifacts})


@api_v1_bp.route("/history/<run_id>/artifacts/<artifact_id>")
@require_api_auth
def api_history_run_artifact_download(run_id, artifact_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    artifact = _artifact_for_run(session_id, owner_scope.team_id, run_id, artifact_id)
    if artifact is None:
        return _api_json_error("not_found", "Artifact not found.", 404)
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return _api_json_error("artifact_unavailable", artifact.get("file_status_detail") or "Artifact unavailable.", status)
    try:
        artifact_session_id = str(artifact.get("session_id") or "")
        owner_context = artifact_owner_context(artifact_session_id, artifact)
        handle = open_owner_workspace_file_for_download(owner_context, artifact["workspace_path"], CFG)
    except WorkspaceError as exc:
        return _api_json_error("artifact_unavailable", str(exc), 404)
    log.info("API_ARTIFACT_DOWNLOADED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "artifact_id": artifact_id,
        "byte_size": int(artifact.get("byte_size") or 0),
    })
    return send_file(
        handle,
        as_attachment=True,
        download_name=artifact.get("display_name") or os.path.basename(artifact["workspace_path"]) or "artifact",
        mimetype=artifact.get("content_type") or "application/octet-stream",
    )


@api_v1_bp.route("/projects")
@require_api_auth
def api_projects():
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    include_archived = str(request.args.get("include_archived") or "").lower() in {"1", "true", "yes"}
    return jsonify(list_projects_page(
        session_id,
        include_archived=include_archived,
        include_counts=True,
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
        team_id=owner_scope.team_id,
    ))


@api_v1_bp.route("/projects/<project_id>")
@require_api_auth
def api_project(project_id):
    owner_scope = _api_request_scope()
    project = get_project(_require_session_id(), project_id, team_id=owner_scope.team_id)
    if project is None:
        return _api_json_error("not_found", "Project not found.", 404)
    return jsonify({"project": project})


@api_v1_bp.route("/projects/<project_id>/findings")
@require_api_auth
def api_project_findings(project_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    findings = list_project_findings(
        session_id,
        project_id,
        {
            "run_id": request.args.getlist("run_id"),
            "target_id": request.args.getlist("target_id"),
            "review_state": request.args.getlist("review_state"),
            "scope": request.args.getlist("scope"),
            "severity": request.args.getlist("severity"),
            "command_root": request.args.getlist("command_root"),
            "orphan_filter": request.args.get("orphan_filter", "hide"),
        },
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
        include_total=True,
        team_id=owner_scope.team_id,
    )
    if findings is None:
        return _api_json_error("not_found", "Project not found.", 404)
    return jsonify(findings)


@api_v1_bp.route("/projects/<project_id>/runs")
@require_api_auth
def api_project_runs(project_id):
    owner_scope = _api_request_scope()
    runs = list_project_runs(
        _require_session_id(),
        project_id,
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
        query=request.args.get("q") or "",
        team_id=owner_scope.team_id,
    )
    if runs is None:
        return _api_json_error("not_found", "Project not found.", 404)
    return jsonify(runs)


@api_v1_bp.route("/projects/<project_id>/entities")
@require_api_auth
def api_project_entities(project_id):
    owner_scope = _api_request_scope()
    entities = list_project_entities(
        _require_session_id(),
        project_id,
        {
            "run_id": request.args.getlist("run_id"),
            "target_id": request.args.getlist("target_id"),
        },
        entity_type=str(request.args.get("entity_type") or ""),
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
        team_id=owner_scope.team_id,
    )
    if entities is None:
        return _api_json_error("not_found", "Project not found.", 404)
    return jsonify(entities)


@api_v1_bp.route("/projects/<project_id>/packages")
@require_api_auth
def api_project_packages(project_id):
    owner_scope = _api_request_scope()
    packages = list_evidence_packages(_require_session_id(), project_id, team_id=owner_scope.team_id)
    if packages is None:
        return _api_json_error("not_found", "Project not found.", 404)
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    return jsonify(page_payload("packages", packages[offset:offset + limit], len(packages), limit, offset))


@api_v1_bp.route("/schedules", methods=["GET"])
@require_api_auth
def api_schedules():
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        schedules = [
            schedule_payload(schedule)
            for schedule in list_schedules_for_owner(session_id, team_id=owner_scope.team_id)
        ]
    except (ScheduleError, ScheduleCronError, ValueError) as exc:
        return _schedule_api_error(exc)
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    log.debug("API_SCHEDULES_LISTED", extra=_api_schedule_log_payload(
        None,
        session_id=session_id,
        count=len(schedules),
        limit=limit,
        offset=offset,
    ))
    return jsonify(page_payload("schedules", schedules[offset:offset + limit], len(schedules), limit, offset))


@api_v1_bp.route("/schedules", methods=["POST"])
@require_api_auth
def api_schedule_create():
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        _require_api_team_capability(owner_scope, Capability.MANAGE_AUTOMATION)
        data = _json_body()
        payload = normalize_schedule_create_payload(
            data,
            session_id,
            command_validator=validate_schedule_command,
        )
        with db_connect() as conn:
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
                source="api_v1",
                conn=conn,
            )
            conn.commit()
    except (
        ApiAuthError,
        TeamPermissionDenied,
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        SessionVariableError,
        ValueError,
    ) as exc:
        return _schedule_api_error(exc)
    log.info("API_SCHEDULE_CREATED", extra=_api_schedule_log_payload(schedule, session_id=session_id))
    return jsonify({"schedule": schedule_payload(schedule)}), 201


@api_v1_bp.route("/schedules/<schedule_id>", methods=["GET"])
@require_api_auth
def api_schedule(schedule_id):
    try:
        owner_scope = _api_request_scope()
        schedule = _schedule_for_api_session(
            schedule_id,
            _require_session_id(),
            team_id=owner_scope.team_id,
        )
        next_fires = _api_schedule_next_fires(schedule)
    except (ApiAuthError, ScheduleError, ScheduleCronError, ValueError) as exc:
        return _schedule_api_error(exc)
    return jsonify({"schedule": schedule_payload(schedule), "next_fires": next_fires})


@api_v1_bp.route("/schedules/<schedule_id>", methods=["PATCH"])
@require_api_auth
def api_schedule_update(schedule_id):
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        _require_api_team_capability(owner_scope, Capability.MANAGE_AUTOMATION)
        schedule = _schedule_for_api_session(schedule_id, session_id, team_id=owner_scope.team_id)
        updates = normalize_schedule_update_payload(
            _json_body(),
            session_id,
            command_validator=validate_schedule_command,
        )
        with db_connect() as conn:
            updated = update_schedule(schedule.id, updates, conn=conn)
            if updated is not None:
                record_schedule_event(
                    AuditEventType.SCHEDULE_UPDATE,
                    updated,
                    audit_fields=route_audit_fields(session_id, request, owner_scope),
                    source="api_v1",
                    details={"changed_fields": sorted(key for key in updates if key != "workspace_cwd")},
                    conn=conn,
                )
            conn.commit()
    except (
        ApiAuthError,
        TeamPermissionDenied,
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        SessionVariableError,
        ValueError,
    ) as exc:
        return _schedule_api_error(exc)
    if updated is None:
        return _api_json_error("not_found", "Schedule not found.", 404)
    log.info("API_SCHEDULE_UPDATED", extra=_api_schedule_log_payload(
        updated,
        session_id=session_id,
        changed_fields=",".join(sorted(key for key in updates if key != "workspace_cwd")),
    ))
    return jsonify({"schedule": schedule_payload(updated)})


@api_v1_bp.route("/schedules/<schedule_id>", methods=["DELETE"])
@require_api_auth
def api_schedule_delete(schedule_id):
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        _require_api_team_capability(owner_scope, Capability.MANAGE_AUTOMATION)
        schedule = _schedule_for_api_session(schedule_id, session_id, team_id=owner_scope.team_id)
    except (ApiAuthError, TeamPermissionDenied) as exc:
        return _schedule_api_error(exc)
    with db_connect() as conn:
        removed = delete_schedule(schedule.id, conn=conn)
        record_schedule_event(
            AuditEventType.SCHEDULE_DELETE,
            schedule,
            audit_fields=route_audit_fields(session_id, request, owner_scope),
            source="api_v1",
            details={"deleted_count": 1 if removed else 0},
            conn=conn,
        )
        conn.commit()
    log.info("API_SCHEDULE_DELETED", extra=_api_schedule_log_payload(schedule, session_id=session_id, removed=removed))
    return jsonify({"removed": removed})


@api_v1_bp.route("/schedules/<schedule_id>/run-now", methods=["POST"])
@require_api_auth
def api_schedule_run_now(schedule_id):
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        _require_api_team_capability(owner_scope, Capability.MANAGE_AUTOMATION)
        schedule = _schedule_for_api_session(schedule_id, session_id, team_id=owner_scope.team_id)
        with db_connect() as conn:
            status, refreshed, fired_at = fire_schedule_now(conn, schedule)
            record_schedule_event(
                AuditEventType.SCHEDULE_RUN_NOW,
                refreshed or schedule,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="api_v1",
                details=run_now_details(
                    status,
                    fired_at=fired_at,
                    run_id=(refreshed or schedule).last_run_id,
                    last_error=(refreshed or schedule).last_error,
                ),
                conn=conn,
            )
            conn.commit()
    except (ApiAuthError, TeamPermissionDenied, ScheduleError, ScheduleCronError, ValueError) as exc:
        return _schedule_api_error(exc)
    log.info("API_SCHEDULE_RUN_NOW", extra=_api_schedule_log_payload(
        refreshed or schedule,
        session_id=session_id,
        status=status,
        fired_at=fired_at,
        run_id=refreshed.last_run_id,
        last_error=refreshed.last_error,
    ))
    return jsonify({
        "status": status,
        "fired_at": fired_at,
        "schedule": schedule_payload(refreshed),
    })


@api_v1_bp.route("/schedules/<schedule_id>/fires", methods=["GET"])
@require_api_auth
def api_schedule_fires(schedule_id):
    try:
        owner_scope = _api_request_scope()
        schedule = _schedule_for_api_session(
            schedule_id,
            _require_session_id(),
            team_id=owner_scope.team_id,
        )
        limit = normalize_page_limit(request.args.get("limit"), 50, 100)
        offset = normalize_page_offset(request.args.get("offset"))
        fires, total = list_schedule_fires(schedule.id, limit=limit, offset=offset)
    except (ApiAuthError, ScheduleError, ValueError) as exc:
        return _schedule_api_error(exc)
    log.debug("API_SCHEDULE_FIRES_LISTED", extra=_api_schedule_log_payload(
        schedule,
        session_id=schedule.session_token,
        count=len(fires),
        total=total,
        limit=limit,
        offset=offset,
    ))
    return jsonify(page_payload("fires", [schedule_fire_payload(fire) for fire in fires], total, limit, offset))


@api_v1_bp.route("/watchers", methods=["GET"])
@require_api_auth
def api_watchers():
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        with db_connect() as conn:
            watchers = list_watchers_for_owner(session_id, team_id=owner_scope.team_id, conn=conn)
            schedules = {
                watcher.schedule_id: get_schedule(watcher.schedule_id, conn=conn)
                for watcher in watchers
            }
    except (WatcherError, ScheduleError, ValueError) as exc:
        return _watcher_api_error(exc)
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    log.debug("API_WATCHERS_LISTED", extra=_api_watcher_log_payload(
        None,
        session_id=session_id,
        count=len(watchers),
        limit=limit,
        offset=offset,
    ))
    payloads = [
        watcher_payload(watcher, schedule=schedules.get(watcher.schedule_id))
        for watcher in watchers
    ]
    return jsonify(page_payload("watchers", payloads[offset:offset + limit], len(payloads), limit, offset))


@api_v1_bp.route("/watchers", methods=["POST"])
@require_api_auth
def api_watcher_create():
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        _require_api_team_capability(owner_scope, Capability.MANAGE_AUTOMATION)
        data = _json_body()
        with db_connect() as conn:
            payload = normalize_watcher_create_payload(
                data,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
                command_validator=validate_schedule_command,
            )
            watcher = create_watcher(
                session_id,
                team_id=owner_scope.team_id,
                **payload,
                conn=conn,
            )
            schedule = get_schedule(watcher.schedule_id, conn=conn)
            record_watcher_event(
                AuditEventType.WATCHER_CREATE,
                watcher,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="api_v1",
                conn=conn,
            )
            conn.commit()
    except (
        ApiAuthError,
        TeamPermissionDenied,
        WatcherError,
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        SessionVariableError,
        ValueError,
    ) as exc:
        return _watcher_api_error(exc)
    log.info("API_WATCHER_CREATED", extra=_api_watcher_log_payload(watcher, session_id=session_id))
    return jsonify({"watcher": watcher_payload(watcher, schedule=schedule)}), 201


@api_v1_bp.route("/watchers/<watcher_id>", methods=["GET"])
@require_api_auth
def api_watcher(watcher_id):
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        with db_connect() as conn:
            watcher = _watcher_for_api_session(
                watcher_id,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            schedule = get_schedule(watcher.schedule_id, conn=conn)
    except (ApiAuthError, WatcherError, ScheduleError, ValueError) as exc:
        return _watcher_api_error(exc)
    return jsonify({"watcher": watcher_payload(watcher, schedule=schedule)})


@api_v1_bp.route("/watchers/<watcher_id>", methods=["PATCH"])
@require_api_auth
def api_watcher_update(watcher_id):
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        _require_api_team_capability(owner_scope, Capability.MANAGE_AUTOMATION)
        data = _json_body()
        with db_connect() as conn:
            watcher = _watcher_for_api_session(
                watcher_id,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            route_update = normalize_watcher_update_payload(
                data,
                session_id,
                command_validator=validate_schedule_command,
            )
            updated = update_watcher(watcher.id, route_update.updates, conn=conn) if route_update.updates else watcher
            if updated is None:
                raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
            event_type = AuditEventType.WATCHER_UPDATE
            if route_update.pause_requested:
                updated = pause_watcher(updated.id, route_update.reason, conn=conn)
                event_type = AuditEventType.WATCHER_PAUSE
            elif route_update.resume_requested:
                updated = resume_watcher(updated.id, conn=conn)
                event_type = AuditEventType.WATCHER_RESUME
            if updated is None:
                raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
            schedule = get_schedule(updated.schedule_id, conn=conn)
            record_watcher_event(
                event_type,
                updated,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="api_v1",
                details={
                    "changed_fields": sorted(key for key in route_update.updates if key != "workspace_cwd"),
                    "reason": route_update.reason if route_update.pause_requested else "",
                },
                conn=conn,
            )
            conn.commit()
    except (
        ApiAuthError,
        TeamPermissionDenied,
        WatcherError,
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        SessionVariableError,
        ValueError,
    ) as exc:
        return _watcher_api_error(exc)
    log.info("API_WATCHER_UPDATED", extra=_api_watcher_log_payload(
        updated,
        session_id=session_id,
        changed_fields=",".join(sorted(key for key in data if key != "workspace_cwd")),
    ))
    return jsonify({"watcher": watcher_payload(updated, schedule=schedule)})


@api_v1_bp.route("/watchers/<watcher_id>", methods=["DELETE"])
@require_api_auth
def api_watcher_delete(watcher_id):
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        _require_api_team_capability(owner_scope, Capability.MANAGE_AUTOMATION)
        with db_connect() as conn:
            watcher = _watcher_for_api_session(
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
                source="api_v1",
                details={"deleted_count": 1 if removed else 0},
                conn=conn,
            )
            conn.commit()
    except (ApiAuthError, TeamPermissionDenied, WatcherError, ScheduleError, ValueError) as exc:
        return _watcher_api_error(exc)
    log.info("API_WATCHER_DELETED", extra=_api_watcher_log_payload(watcher, session_id=session_id, removed=removed))
    return jsonify({"removed": removed})


@api_v1_bp.route("/watchers/<watcher_id>/run-now", methods=["POST"])
@require_api_auth
def api_watcher_run_now(watcher_id):
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        _require_api_team_capability(owner_scope, Capability.MANAGE_AUTOMATION)
        with db_connect() as conn:
            watcher = _watcher_for_api_session(
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
                source="api_v1",
                details=run_now_details(
                    status,
                    fired_at=fired_at,
                    run_id=refreshed.last_run_id,
                    last_error=refreshed.last_error,
                ),
                conn=conn,
            )
            conn.commit()
    except (ApiAuthError, TeamPermissionDenied, WatcherError, ScheduleError, ScheduleCronError, ValueError) as exc:
        return _watcher_api_error(exc)
    log.info("API_WATCHER_RUN_NOW", extra=_api_watcher_log_payload(
        refreshed,
        session_id=session_id,
        status=status,
        fired_at=fired_at,
        run_id=refreshed.last_run_id,
        last_error=refreshed.last_error,
    ))
    return jsonify({
        "status": status,
        "fired_at": fired_at,
        "watcher": watcher_payload(refreshed, schedule=refreshed_schedule),
    })


@api_v1_bp.route("/watchers/<watcher_id>/fires", methods=["GET"])
@require_api_auth
def api_watcher_fires(watcher_id):
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        limit = normalize_page_limit(request.args.get("limit"), 50, 100)
        offset = normalize_page_offset(request.args.get("offset"))
        with db_connect() as conn:
            watcher = _watcher_for_api_session(
                watcher_id,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            fires, total = list_watcher_fires(watcher.id, limit=limit, offset=offset, conn=conn)
    except (ApiAuthError, WatcherError, ValueError) as exc:
        return _watcher_api_error(exc)
    log.debug("API_WATCHER_FIRES_LISTED", extra=_api_watcher_log_payload(
        watcher,
        session_id=session_id,
        count=len(fires),
        total=total,
        limit=limit,
        offset=offset,
    ))
    return jsonify(page_payload("fires", [watcher_fire_payload(fire) for fire in fires], total, limit, offset))


@api_v1_bp.route("/watchers/<watcher_id>/accept-baseline", methods=["POST"])
@require_api_auth
def api_watcher_accept_baseline(watcher_id):
    session_id = _require_session_id()
    try:
        owner_scope = _api_request_scope()
        _require_api_team_capability(owner_scope, Capability.MANAGE_AUTOMATION)
        data = _json_body()
        with db_connect() as conn:
            watcher = _watcher_for_api_session(
                watcher_id,
                session_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            accepted = accept_baseline(watcher.id, run_id=data.get("run_id"), conn=conn)
            if accepted is None:
                raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
            schedule = get_schedule(accepted.schedule_id, conn=conn)
            record_watcher_event(
                AuditEventType.WATCHER_ACCEPT_BASELINE,
                accepted,
                audit_fields=route_audit_fields(session_id, request, owner_scope),
                source="api_v1",
                details={"baseline_run_id": accepted.baseline_run_id},
                conn=conn,
            )
            conn.commit()
    except (ApiAuthError, TeamPermissionDenied, WatcherError, ScheduleError, ValueError) as exc:
        return _watcher_api_error(exc)
    log.info("API_WATCHER_BASELINE_ACCEPTED", extra=_api_watcher_log_payload(accepted, session_id=session_id))
    return jsonify({"watcher": watcher_payload(accepted, schedule=schedule)})


@api_v1_bp.route("/notification-channels", methods=["GET"])
@require_api_auth
def api_notification_channels():
    try:
        session_id = _require_session_id()
        owner_scope = _api_request_scope()
        return jsonify({"channels": list_notification_channels(session_id, team_id=owner_scope.team_id)})
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_api_error(exc)


@api_v1_bp.route("/notification-channel-kinds", methods=["GET"])
@require_api_auth
def api_notification_channel_kinds():
    return jsonify(notification_channel_kind_contract())


@api_v1_bp.route("/notification-channels", methods=["POST"])
@require_api_auth
def api_notification_channel_create():
    try:
        session_id = _require_session_id()
        owner_scope = _require_notification_manage_scope()
        channel = create_notification_channel(
            session_id,
            _json_body(),
            team_id=owner_scope.team_id,
            audit_fields=route_audit_fields(session_id, request, owner_scope),
            audit_source="api_v1",
        )
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_api_error(exc)
    log.info("API_NOTIFICATION_CHANNEL_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(_require_session_id()),
        "channel_id": channel["id"],
        "kind": channel["kind"],
    })
    return jsonify({"channel": channel}), 201


@api_v1_bp.route("/notification-channels/<channel_id>", methods=["PATCH"])
@require_api_auth
def api_notification_channel_update(channel_id):
    try:
        session_id = _require_session_id()
        owner_scope = _require_notification_manage_scope()
        channel = update_notification_channel(
            session_id,
            channel_id,
            _json_body(),
            team_id=owner_scope.team_id,
            audit_fields=route_audit_fields(session_id, request, owner_scope),
            audit_source="api_v1",
        )
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_api_error(exc)
    log.info("API_NOTIFICATION_CHANNEL_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(_require_session_id()),
        "channel_id": channel["id"],
        "kind": channel["kind"],
    })
    return jsonify({"channel": channel})


@api_v1_bp.route("/notification-channels/<channel_id>", methods=["DELETE"])
@require_api_auth
def api_notification_channel_delete(channel_id):
    try:
        session_id = _require_session_id()
        owner_scope = _require_notification_manage_scope()
        removed = delete_notification_channel(
            session_id,
            channel_id,
            team_id=owner_scope.team_id,
            audit_fields=route_audit_fields(session_id, request, owner_scope),
            audit_source="api_v1",
        )
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_api_error(exc)
    log.info("API_NOTIFICATION_CHANNEL_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(_require_session_id()),
        "channel_id": channel_id,
        "removed": removed,
    })
    return jsonify({"removed": removed})


@api_v1_bp.route("/notification-channels/<channel_id>/test", methods=["POST"])
@require_api_auth
def api_notification_channel_test(channel_id):
    try:
        session_id = _require_session_id()
        owner_scope = _require_notification_manage_scope()
        result = send_test_notification(
            session_id,
            channel_id,
            team_id=owner_scope.team_id,
            audit_fields=route_audit_fields(session_id, request, owner_scope),
            audit_source="api_v1",
        )
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_api_error(exc)
    log.info("API_NOTIFICATION_CHANNEL_TESTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(_require_session_id()),
        "channel_id": channel_id,
        "event_count": int(result.get("queued") or 0),
    })
    return jsonify(result)


@api_v1_bp.route("/notification-events")
@require_api_auth
def api_notification_events():
    try:
        session_id = _require_session_id()
        owner_scope = _api_request_scope()
        events = list_notification_events(
            session_id,
            limit=normalize_page_limit(request.args.get("limit"), 50, 100),
            offset=normalize_page_offset(request.args.get("offset")),
            status=str(request.args.get("status") or ""),
            channel_id=str(request.args.get("channel_id") or ""),
            trigger=str(request.args.get("trigger") or ""),
            team_id=owner_scope.team_id,
        )
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_api_error(exc)
    return jsonify(events)


@api_v1_bp.route("/runs")
@require_api_auth
def api_active_runs():
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    runs = [_active_run_summary(active) for active in _active_runs_for_owner(session_id, owner_scope.team_id)]
    return jsonify({"runs": runs, "total": len(runs)})


@api_v1_bp.route("/runs", methods=["POST"])
@require_api_auth
def api_runs_start():
    parsed_json = request.get_json(silent=True)
    data = parsed_json if parsed_json is not None else {}
    if not isinstance(data, dict):
        return _api_json_error("invalid_body", "Request body must be a JSON object.", 400)
    original_command = data.get("command", "")
    if not isinstance(original_command, str):
        return _api_json_error("invalid_command", "Command must be a string.", 400)
    original_command = original_command.strip()
    if not original_command:
        return _api_json_error("missing_command", "Command is required.", 400)
    interactive_spec = interactive_pty_spec_for_command(original_command)
    interactive_trigger = str((interactive_spec or {}).get("trigger_flag") or "").strip()
    if interactive_trigger and interactive_trigger in split_command_argv(original_command)[1:]:
        return _api_json_error("interactive_pty_not_supported", "Interactive PTY runs are not supported by API v1.", 409)

    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    try:
        _require_api_team_capability(owner_scope, Capability.RUN_COMMANDS)
        link_project_id = _requested_project_id(data, session_id, team_id=owner_scope.team_id)
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except TeamPermissionDenied as exc:
        return _api_json_error("team_forbidden", str(exc), 403)
    if not broker_available():
        log.warning("API_BROKER_UNAVAILABLE", extra={
            "ip": get_client_ip(),
            "reason": broker_unavailable_reason(),
        })
        response, status = _api_json_error("broker_unavailable", broker_unavailable_reason(), 503)
        response.headers["Retry-After"] = "5"
        return response, status
    client_ip = get_client_ip()
    owner_tab_id = ""
    workspace_cwd = _workspace_cwd_value(data.get("workspace_cwd", ""))
    team_role = str((owner_scope.member or {}).get("role") or "") if owner_scope.is_team else ""

    try:
        started = _start_brokered_run_service(
            original_command=original_command,
            session_id=session_id,
            team_id=owner_scope.team_id,
            team_role=team_role,
            client_ip=client_ip,
            handlers=_api_run_start_handlers(),
            owner_tab_id=owner_tab_id,
            workspace_cwd=workspace_cwd,
            link_project_id=link_project_id,
            thread_name_prefix="api-run-broker",
        )
    except RunStartRejected as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except _RunPreparationError as exc:
        return _api_json_error("command_rejected", str(exc), exc.status_code)
    except _RunSpawnError as exc:
        return _api_json_error("spawn_failed", str(exc), 500)
    log.info("API_RUN_STARTED", extra={
        "ip": client_ip,
        "session": get_log_session_id(session_id),
        "run_id": started.run_id,
        "cmd": original_command,
        "cmd_type": started.cmd_type,
        "project_id": link_project_id,
    })
    return jsonify(_run_started_payload(started.run_id, status=started.status)), 202


def _run_started_payload(run_id: str, *, status: str = "running") -> dict[str, str]:
    return {
        "id": run_id,
        "status": status,
        "stream_url": f"/api/v1/runs/{run_id}/stream",
        "history_url": f"/api/v1/history/{run_id}",
    }


@api_v1_bp.route("/runs/<run_id>")
@require_api_auth
def api_run_status(run_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    run = _run_status_from_active_or_row(run_id, session_id, owner_scope.team_id)
    if run is None:
        return _api_json_error("not_found", "Run not found.", 404)
    return jsonify({"run": run})


@api_v1_bp.route("/runs/<run_id>/wait", methods=["POST"])
@require_api_auth
def api_run_wait(run_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    timeout = _parse_float(request.args.get("timeout"), 30.0, minimum=0.0, maximum=3600.0)
    deadline = time.monotonic() + timeout
    poll_interval = 0.1
    while True:
        run = _run_status_from_active_or_row(run_id, session_id, owner_scope.team_id)
        if run is None:
            return _api_json_error("not_found", "Run not found.", 404)
        if str(run.get("status") or "") != "running":
            return jsonify({"run": run})
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _api_json_error("wait_timeout", "Run is still running.", 408)
        time.sleep(min(poll_interval, remaining))


@api_v1_bp.route("/runs/<run_id>/ai-assists")
@require_api_auth
def api_run_ai_assists(run_id):
    owner_scope = _api_request_scope()
    try:
        assists = list_run_assists(_require_session_id(), run_id, team_id=owner_scope.team_id)
    except AIAssistRouteError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    return jsonify({"assists": assists})


@api_v1_bp.route("/runs/<run_id>/ai-summary", methods=["POST"])
@require_api_auth
def api_run_ai_summary(run_id):
    owner_scope = _api_request_scope()
    try:
        _require_api_team_capability(owner_scope, Capability.RUN_COMMANDS)
        assist, status_code = enqueue_summary_assist(
            _require_session_id(),
            run_id,
            team_id=owner_scope.team_id,
            force=_parse_bool(_json_body().get("force")),
        )
    except AIAssistRouteError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except TeamPermissionDenied as exc:
        return _api_json_error("team_forbidden", str(exc), 403)
    return jsonify({"assist": assist}), status_code


@api_v1_bp.route("/runs/<run_id>/ai-next-commands", methods=["POST"])
@require_api_auth
def api_run_ai_next_commands(run_id):
    owner_scope = _api_request_scope()
    try:
        _require_api_team_capability(owner_scope, Capability.RUN_COMMANDS)
        assist, status_code = enqueue_next_commands_assist(
            _require_session_id(),
            run_id,
            team_id=owner_scope.team_id,
            force=_parse_bool(_json_body().get("force")),
        )
    except AIAssistRouteError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except TeamPermissionDenied as exc:
        return _api_json_error("team_forbidden", str(exc), 403)
    return jsonify({"assist": assist}), status_code


@api_v1_bp.route("/runs/<run_id>/projects/<project_id>", methods=["POST"])
@require_api_auth
def api_run_project_link(run_id, project_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    try:
        _require_api_team_capability(owner_scope, Capability.MUTATE_PROJECTS)
        if _active_project_for_write(session_id, project_id, team_id=owner_scope.team_id) is None:
            return _api_json_error("not_found", "Project not found.", 404)
        link = link_project_entity(
            session_id,
            project_id,
            {"entity_type": "run", "entity_id": run_id, "source": "manual"},
            team_id=owner_scope.team_id,
        )
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except TeamPermissionDenied as exc:
        return _api_json_error("team_forbidden", str(exc), 403)
    except ProjectWorkspaceError as exc:
        return _project_workspace_api_error(exc)
    if link is None:
        return _api_json_error("not_found", "Project not found.", 404)
    log.info("API_PROJECT_RUN_LINKED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "project_id": project_id,
        "link_source": link.get("source") or "",
    })
    return jsonify({"ok": True, "link": link}), 201


@api_v1_bp.route("/runs/<run_id>/projects/<project_id>", methods=["DELETE"])
@require_api_auth
def api_run_project_unlink(run_id, project_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    try:
        _require_api_team_capability(owner_scope, Capability.MUTATE_PROJECTS)
        if _active_project_for_write(session_id, project_id, team_id=owner_scope.team_id) is None:
            return _api_json_error("not_found", "Project not found.", 404)
        deleted = unlink_project_entity(
            session_id,
            project_id,
            {"entity_type": "run", "entity_id": run_id},
            team_id=owner_scope.team_id,
        )
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except TeamPermissionDenied as exc:
        return _api_json_error("team_forbidden", str(exc), 403)
    except ProjectWorkspaceError as exc:
        return _project_workspace_api_error(exc)
    if deleted is None:
        return _api_json_error("not_found", "Project not found.", 404)
    if not deleted:
        return _api_json_error("not_found", "Project link not found.", 404)
    log.info("API_PROJECT_RUN_UNLINKED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "project_id": project_id,
    })
    return jsonify({"ok": True})


@api_v1_bp.route("/runs/<run_id>/stream")
@require_api_auth
def api_run_stream(run_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    if _run_status_from_active_or_row(run_id, session_id, owner_scope.team_id) is None:
        return _api_json_error("not_found", "Run not found.", 404)
    after_id = _sse_after_id()
    log.debug("API_RUN_STREAM_ATTACHED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "team_id": owner_scope.team_id,
        "after_id": after_id,
        "format": str(request.args.get("format") or "sse"),
    })
    stream_log_fields = {
        "ip": get_client_ip(),
        "route": str(request.path or ""),
        "method": str(request.method or ""),
    }
    if str(request.args.get("format") or "").lower() == "ndjson":
        return Response(
            _ndjson_from_sse_chunks(
                stream_run_events(run_id, after_id=after_id),
                run_id=run_id,
                session_id=session_id,
                team_id=owner_scope.team_id,
                **stream_log_fields,
            ),
            mimetype="application/x-ndjson",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )
    return Response(
        _sse_chunks_with_error_logging(
            stream_run_events(run_id, after_id=after_id),
            run_id=run_id,
            session_id=session_id,
            team_id=owner_scope.team_id,
            **stream_log_fields,
        ),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@api_v1_bp.route("/runs/<run_id>/cancel", methods=["POST"])
@require_api_auth
def api_run_cancel(run_id):
    session_id = _require_session_id()
    owner_scope = _api_request_scope()
    try:
        _require_api_team_capability(owner_scope, Capability.RUN_COMMANDS)
    except TeamPermissionDenied as exc:
        return _api_json_error("team_forbidden", str(exc), 403)
    active_run = next(
        (
            run for run in active_runs_for_session(session_id, team_id=owner_scope.team_id)
            if run.get("run_id") == run_id
        ),
        {},
    )
    if not active_run:
        return _api_json_error("not_found", "Run not found.", 404)
    pid = pid_for_session(run_id, session_id)
    if not pid:
        return _api_json_error("not_found", "No active process found for run.", 404)
    try:
        _signal_process_group(pid)
        publish_run_event(run_id, "killed", {"api": True})
    except ProcessLookupError as exc:
        publish_run_event(run_id, "killed", {"api": True})
        log.warning("API_RUN_CANCEL_SIGNAL_FAILED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "error": str(exc),
        })
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("API_RUN_CANCEL_SIGNAL_FAILED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "error": str(exc),
        })
        return _api_json_error("cancel_failed", "Failed to signal process.", 500)
    return jsonify({"killed": True, "id": run_id})
