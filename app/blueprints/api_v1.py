"""Headless API v1 routes."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable

from flask import Blueprint, Response, jsonify, request, send_file

from config import CFG, SCANNER_PREFIX
from core.database import DB_BACKEND, db_connect
from core.helpers import get_client_ip, get_log_session_id
from core.process import active_runs_for_session, pid_pop_for_session
from extensions import limiter
from services.api_v1.auth import ApiAuthError, current_api_session, require_api_auth
from services.api_v1.openapi import openapi_spec
from services.api_v1.serialization import artifact_summary, json_error, run_summary
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
from services.history.search import run_search_clause
from services.notifications.channels_store import (
    NotificationChannelError,
    create_notification_channel,
    delete_notification_channel,
    list_notification_channels,
    list_notification_events,
    send_test_notification,
    update_notification_channel,
)
from services.projects.artifacts import artifact_availability
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
from services.runs.output_store import load_full_output_entries
from services.scheduler.commands import ScheduleCommandValidationError, validate_schedule_command
from services.scheduler.cron import ScheduleCronError
from services.scheduler.dispatch import fire_schedule
from services.scheduler.models import OWNER_KIND_USER
from services.scheduler.service import (
    ScheduleError,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_for_session as list_schedules_for_session,
    list_schedule_fires,
    schedule_ids_by_run,
    update_schedule,
)
from services.secrets.vault import MasterKeyError, SecretDecryptError
from services.session.variables import SessionVariableError
from services.workspace.files import WorkspaceError, open_workspace_file_for_download

from blueprints.history import (  # noqa: PLC0415
    _history_offloaded_search_run_ids,
    _normalize_history_filter_text,
    _preview_output_entries_from_run,
    _run_atlas_counts_by_run,
    _run_file_artifacts_by_run,
    _run_metadata_counts_by_run,
)
from blueprints.run import (  # noqa: PLC0415
    KILL_BIN,
    SUDO_BIN,
    _RunPreparationError,
    _RunSpawnError,
    _brokered_real_run_worker,
    _brokered_synthetic_run,
    _filter_builtin_command_events,
    _history_safe_command_for_storage,
    _prepare_command_input,
    _prepare_real_command,
    _run_belongs_to_session,
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


api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")
limiter.limit(_api_route_limit)(api_v1_bp)


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


def _schedule_payload(schedule) -> dict[str, Any]:
    payload = asdict(schedule)
    payload.pop("session_token", None)
    payload["enabled"] = bool(schedule.enabled)
    return payload


def _schedule_fire_payload(fire) -> dict[str, Any]:
    return asdict(fire)


def _schedule_for_api_session(schedule_id: str, session_id: str):
    schedule = get_schedule(schedule_id)
    if schedule is None or schedule.session_token != session_id or schedule.owner_kind != OWNER_KIND_USER:
        raise ApiAuthError("not_found", "Schedule not found.", status_code=404)
    return schedule


def _schedule_api_error(exc: Exception):
    if isinstance(exc, ApiAuthError):
        return _api_json_error(exc.code, exc.message, exc.status_code)
    if isinstance(exc, ScheduleCronError):
        return _api_json_error("invalid_schedule", str(exc), 400)
    if isinstance(exc, ScheduleCommandValidationError):
        return _api_json_error("invalid_command", str(exc), 400)
    if isinstance(exc, SessionVariableError):
        return _api_json_error("invalid_command", str(exc), 400)
    if isinstance(exc, ScheduleError):
        status = 409 if "quota" in str(exc).lower() else 400
        return _api_json_error("invalid_schedule", str(exc), status)
    if isinstance(exc, ValueError):
        return _api_json_error("invalid_schedule", str(exc), 400)
    raise exc


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


def _run_status_from_active_or_row(run_id: str, session_id: str) -> dict[str, Any] | None:
    for active in active_runs_for_session(session_id):
        if str(active.get("run_id") or "") == run_id:
            return _active_run_summary(active)
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE session_id = ? AND id = ?",
            (session_id, run_id),
        ).fetchone()
        if not row:
            return None
        run = dict(row)
        artifacts = _run_file_artifacts_by_run(conn, [run_id]).get(run_id, [])
        run["artifact_count"] = len(artifacts)
        run.update(_run_metadata_counts_by_run(conn, [run_id]).get(run_id, {}))
        run.update(_run_atlas_counts_by_run(conn, session_id, [run_id]).get(run_id, {}))
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


def _requested_project_id(data: dict[str, Any], session_id: str) -> str:
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        return ""
    project = get_project(session_id, project_id)
    if project is None:
        raise ApiAuthError("not_found", "Project not found.", status_code=404)
    if str(project.get("status") or "") == "archived":
        raise ApiAuthError("archived_project", "Archived projects cannot receive new API run links.", status_code=409)
    return project_id


def _active_project_for_write(session_id: str, project_id: str) -> dict[str, Any] | None:
    project = get_project(session_id, project_id)
    if project is None:
        return None
    if str(project.get("status") or "") == "archived":
        raise ApiAuthError("archived_project", "Archived projects cannot be modified through API v1.", status_code=409)
    return project


def _history_where(
    session_id: str,
    filters: dict[str, str],
    *,
    offloaded_ids: list[str] | None = None,
    search_scope: str = "all",
):
    where = ["r.session_id = ?"]
    params: list[Any] = [session_id]
    if filters["run_kind"]:
        where.append("r.run_kind = ?")
        params.append(filters["run_kind"])
    if filters["project_id"]:
        where.append(
            "EXISTS (SELECT 1 FROM project_links pl JOIN projects p ON p.id = pl.project_id "
            "WHERE p.session_id = ? AND p.id = ? AND pl.entity_type = 'run' AND pl.entity_id = r.id)"
        )
        params.extend([session_id, filters["project_id"]])
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


def _history_search_candidate_runs(session_id: str, filters: dict[str, str]) -> list[dict[str, Any]]:
    offloaded_ids: list[str] = []
    if filters["q"]:
        with db_connect() as conn:
            offloaded_ids = _history_offloaded_search_run_ids(
                conn,
                session_id,
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
            filters,
            offloaded_ids=offloaded_ids,
            search_scope="all",
        )
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


def _entry_text(entry: object) -> str:
    if isinstance(entry, dict):
        return str(entry.get("text", ""))
    return str(entry)


def _run_output_search_matches(run: dict[str, Any], query: str, context: int) -> list[dict[str, Any]]:
    needle = query.casefold()
    lines = [_entry_text(entry) for entry in _run_output_entries(run)]
    matches: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if needle not in line.casefold():
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
            "context_before": lines[before_start:index],
            "context_after": lines[index + 1:after_end],
        })
    return matches


def _history_output_search(session_id: str, query: str, context: int) -> list[dict[str, Any]]:
    filters = _history_filters()
    filters["q"] = query
    matches: list[dict[str, Any]] = []
    for run in _history_search_candidate_runs(session_id, filters):
        matches.extend(_run_output_search_matches(run, query, context))
    return matches


def _history_rows(session_id: str, limit: int, offset: int, filters: dict[str, str]):
    offloaded_ids: list[str] = []
    if filters["q"]:
        with db_connect() as conn:
            offloaded_ids = _history_offloaded_search_run_ids(
                conn,
                session_id,
                filters["q"],
                "",
                "",
                "",
                filters["project_id"],
                run_kind=filters["run_kind"] or "all",
            )
    with db_connect() as conn:
        where_sql, params = _history_where(session_id, filters, offloaded_ids=offloaded_ids)
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
        atlas = _run_atlas_counts_by_run(conn, session_id, run_ids)
        scheduled = schedule_ids_by_run(conn, run_ids)
    for run in runs:
        run_id = str(run["id"])
        run["artifact_count"] = len(artifacts.get(run_id, []))
        run.update(metadata.get(run_id, {}))
        run.update(atlas.get(run_id, {}))
        run["schedule_id"] = scheduled.get(run_id, "")
        run["scheduled"] = bool(run["schedule_id"])
    return runs, total


def _load_run_detail(session_id: str, run_id: str) -> dict[str, Any] | None:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.session_id = ? AND runs.id = ?",
            (session_id, run_id),
        ).fetchone()
        if not row:
            return None
        run = dict(row)
        artifacts = _run_file_artifacts_by_run(conn, [run_id]).get(run_id, [])
        run["artifacts"] = artifacts
        run["artifact_count"] = len(artifacts)
        run.update(_run_metadata_counts_by_run(conn, [run_id]).get(run_id, {}))
        run.update(_run_atlas_counts_by_run(conn, session_id, [run_id]).get(run_id, {}))
        schedule_id = schedule_ids_by_run(conn, [run_id]).get(run_id, "")
        run["schedule_id"] = schedule_id
        run["scheduled"] = bool(schedule_id)
    return run


def _run_output_entries(run: dict[str, Any], *, full: bool = True) -> list[dict[str, Any]]:
    use_full = full and bool(run.get("full_output_available")) and bool(run.get("rel_path"))
    if use_full:
        try:
            return load_full_output_entries(str(run.get("rel_path") or ""))
        except Exception as exc:
            log.warning("API_FULL_OUTPUT_LOAD_FAILED", extra={
                "run_id": str(run.get("id") or ""),
                "session": get_log_session_id(str(run.get("session_id") or "")),
                "rel_path": str(run.get("rel_path") or ""),
                "error": str(exc),
            })
    return _preview_output_entries_from_run(run)


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


def _artifact_for_run(session_id: str, run_id: str, artifact_id: str) -> dict[str, Any] | None:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
            "detected_by, content_type, preview_type, content_sha256, created "
            "FROM run_file_artifacts WHERE session_id = ? AND run_id = ? AND id = ?",
            (session_id, run_id, artifact_id),
        ).fetchone()
    if not row:
        return None
    artifact = dict(row)
    artifact.update(artifact_availability(session_id, artifact))
    return artifact


def _artifacts_for_run(session_id: str, run_id: str) -> list[dict[str, Any]] | None:
    with db_connect() as conn:
        run_row = conn.execute(
            "SELECT 1 FROM runs WHERE session_id = ? AND id = ?",
            (session_id, run_id),
        ).fetchone()
        if not run_row:
            return None
        rows = conn.execute(
            "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
            "detected_by, content_type, preview_type, content_sha256, created "
            "FROM run_file_artifacts WHERE session_id = ? AND run_id = ? "
            "ORDER BY created ASC, workspace_path ASC",
            (session_id, run_id),
        ).fetchall()
    artifacts = []
    for row in rows:
        artifact = dict(row)
        artifact.update(artifact_availability(session_id, artifact))
        artifacts.append(artifact_summary(artifact))
    return artifacts


def _sse_after_id() -> str:
    explicit = str(request.args.get("after") or "").strip()
    if explicit:
        return explicit
    return str(request.headers.get("Last-Event-ID") or "0-0").strip() or "0-0"


def _ndjson_from_sse_chunks(chunks: Iterable[str]):
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
                for line in lines:
                    if line.startswith("id:"):
                        event_id = line[3:].strip()
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
                if event_id and isinstance(payload, dict):
                    payload.setdefault("event_id", event_id)
                yield json.dumps(payload, separators=(",", ":")) + "\n"
    except Exception as exc:
        yield json.dumps({
            "event": "error",
            "code": "stream_error",
            "message": str(exc) or "Run stream interrupted.",
        }) + "\n"


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
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    runs, total = _history_rows(session_id, limit, offset, _history_filters())
    return jsonify(page_payload("runs", [run_summary(run) for run in runs], total, limit, offset))


@api_v1_bp.route("/history/search")
@require_api_auth
def api_history_search():
    query = _normalize_history_filter_text(request.args.get("q"))
    if not query:
        return _api_json_error("missing_query", "q is required.", 400)
    session_id = _require_session_id()
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    context = _parse_int(request.args.get("context"), 2, minimum=0, maximum=10)
    matches = _history_output_search(session_id, query, context)
    page = matches[offset:offset + limit]
    return jsonify(page_payload(
        "matches",
        page,
        len(matches),
        limit,
        offset,
        extra={"query": query, "context": context},
    ))


@api_v1_bp.route("/atlas")
@require_api_auth
def api_atlas_summary():
    with db_connect() as conn:
        return jsonify(atlas_summary(
            conn,
            _require_session_id(),
            run_id=request.args.get("run_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
        ))


@api_v1_bp.route("/atlas/runs")
@require_api_auth
def api_atlas_runs():
    limit = normalize_page_limit(request.args.get("limit"), 30, 50)
    with db_connect() as conn:
        return jsonify(list_atlas_source_runs(
            conn,
            _require_session_id(),
            query=request.args.get("q") or "",
            run_id=request.args.get("run_id") or "",
            limit=limit,
        ))


@api_v1_bp.route("/atlas/entities")
@require_api_auth
def api_atlas_entities():
    limit = normalize_page_limit(request.args.get("limit"), 50, 200)
    offset = normalize_page_offset(request.args.get("offset"))
    entity_type = request.args.get("entity_type") or request.args.get("type") or ""
    with db_connect() as conn:
        return jsonify(list_atlas_entities(
            conn,
            _require_session_id(),
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
    runs_offset = normalize_page_offset(request.args.get("runs_offset"))
    findings_offset = normalize_page_offset(request.args.get("findings_offset"))
    with db_connect() as conn:
        detail = entity_detail(
            conn,
            _require_session_id(),
            entity_id,
            runs_offset=runs_offset,
            findings_offset=findings_offset,
        )
    if detail is None:
        return _api_json_error("not_found", "Atlas entity not found.", 404)
    return jsonify(detail)


@api_v1_bp.route("/atlas/findings")
@require_api_auth
def api_atlas_findings():
    limit = normalize_page_limit(request.args.get("limit"), 50, 200)
    offset = normalize_page_offset(request.args.get("offset"))
    review_states = request.args.getlist("review_state") or request.args.getlist("status")
    with db_connect() as conn:
        return jsonify(list_atlas_findings(
            conn,
            _require_session_id(),
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
    with db_connect() as conn:
        detail = finding_detail(conn, _require_session_id(), finding_id)
    if detail is None:
        return _api_json_error("not_found", "Atlas finding not found.", 404)
    return jsonify(detail)


@api_v1_bp.route("/history/<run_id>")
@require_api_auth
def api_history_run(run_id):
    run = _load_run_detail(_require_session_id(), run_id)
    if run is None:
        return _api_json_error("not_found", "Run not found.", 404)
    detail = run_summary(run)
    detail["artifacts"] = [artifact_summary(artifact) for artifact in run.get("artifacts", [])]
    return jsonify({"run": detail})


@api_v1_bp.route("/history/<run_id>/output")
@api_v1_bp.route("/runs/<run_id>/output")
@require_api_auth
def api_history_run_output(run_id):
    run = _load_run_detail(_require_session_id(), run_id)
    if run is None:
        return _api_json_error("not_found", "Run not found.", 404)
    entries = _run_output_entries(run)
    try:
        line_range = _parse_output_range(request.args.get("range"))
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    all_lines = [str(entry.get("text", "")) if isinstance(entry, dict) else str(entry) for entry in entries]
    lines = _slice_output_lines(all_lines, line_range)
    if str(request.args.get("format") or "text").lower() == "json":
        payload = {
            "run_id": run_id,
            "preview": not bool(run.get("full_output_available") and run.get("rel_path")),
            "full_output_available": bool(run.get("full_output_available")),
            "truncated": bool(run.get("preview_truncated") or run.get("full_output_truncated")),
            "line_count": len(all_lines),
            "lines": lines,
        }
        if line_range is not None:
            payload["range"] = {"start": line_range[0], "end": line_range[1], "returned": len(lines)}
        return jsonify(payload)
    return Response("\n".join(lines), mimetype="text/plain; charset=utf-8")


@api_v1_bp.route("/history/<run_id>/artifacts")
@require_api_auth
def api_history_run_artifacts(run_id):
    artifacts = _artifacts_for_run(_require_session_id(), run_id)
    if artifacts is None:
        return _api_json_error("not_found", "Run not found.", 404)
    return jsonify({"artifacts": artifacts})


@api_v1_bp.route("/history/<run_id>/artifacts/<artifact_id>")
@require_api_auth
def api_history_run_artifact_download(run_id, artifact_id):
    session_id = _require_session_id()
    artifact = _artifact_for_run(session_id, run_id, artifact_id)
    if artifact is None:
        return _api_json_error("not_found", "Artifact not found.", 404)
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return _api_json_error("artifact_unavailable", artifact.get("file_status_detail") or "Artifact unavailable.", status)
    try:
        handle = open_workspace_file_for_download(session_id, artifact["workspace_path"], CFG)
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
    include_archived = str(request.args.get("include_archived") or "").lower() in {"1", "true", "yes"}
    return jsonify(list_projects_page(
        session_id,
        include_archived=include_archived,
        include_counts=True,
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
    ))


@api_v1_bp.route("/projects/<project_id>")
@require_api_auth
def api_project(project_id):
    project = get_project(_require_session_id(), project_id)
    if project is None:
        return _api_json_error("not_found", "Project not found.", 404)
    return jsonify({"project": project})


@api_v1_bp.route("/projects/<project_id>/findings")
@require_api_auth
def api_project_findings(project_id):
    session_id = _require_session_id()
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
    )
    if findings is None:
        return _api_json_error("not_found", "Project not found.", 404)
    return jsonify(findings)


@api_v1_bp.route("/projects/<project_id>/runs")
@require_api_auth
def api_project_runs(project_id):
    runs = list_project_runs(
        _require_session_id(),
        project_id,
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
    )
    if runs is None:
        return _api_json_error("not_found", "Project not found.", 404)
    return jsonify(runs)


@api_v1_bp.route("/projects/<project_id>/entities")
@require_api_auth
def api_project_entities(project_id):
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
    )
    if entities is None:
        return _api_json_error("not_found", "Project not found.", 404)
    return jsonify(entities)


@api_v1_bp.route("/projects/<project_id>/packages")
@require_api_auth
def api_project_packages(project_id):
    packages = list_evidence_packages(_require_session_id(), project_id)
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
        schedules = [_schedule_payload(schedule) for schedule in list_schedules_for_session(session_id)]
    except (ScheduleError, ScheduleCronError, ValueError) as exc:
        return _schedule_api_error(exc)
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    return jsonify(page_payload("schedules", schedules[offset:offset + limit], len(schedules), limit, offset))


@api_v1_bp.route("/schedules", methods=["POST"])
@require_api_auth
def api_schedule_create():
    session_id = _require_session_id()
    try:
        data = _json_body()
        command = validate_schedule_command(
            data.get("command", data.get("command_text")),
            session_id,
            workspace_cwd=str(data.get("workspace_cwd") or ""),
        )
        schedule = create_schedule(
            session_id,
            command_text=command,
            cron_expr=data.get("cron_expr"),
            cadence_preset=data.get("cadence_preset"),
            timezone_name=data.get("timezone", data.get("timezone_name")),
            label=str(data.get("label") or ""),
            enabled=bool(data.get("enabled", True)),
        )
    except (
        ApiAuthError,
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        SessionVariableError,
        ValueError,
    ) as exc:
        return _schedule_api_error(exc)
    log.info("API_SCHEDULE_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "schedule_id": schedule.id,
    })
    return jsonify({"schedule": _schedule_payload(schedule)}), 201


@api_v1_bp.route("/schedules/<schedule_id>", methods=["GET"])
@require_api_auth
def api_schedule(schedule_id):
    try:
        schedule = _schedule_for_api_session(schedule_id, _require_session_id())
    except ApiAuthError as exc:
        return _schedule_api_error(exc)
    return jsonify({"schedule": _schedule_payload(schedule)})


@api_v1_bp.route("/schedules/<schedule_id>", methods=["PATCH"])
@require_api_auth
def api_schedule_update(schedule_id):
    session_id = _require_session_id()
    try:
        schedule = _schedule_for_api_session(schedule_id, session_id)
        updates = dict(_json_body())
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
        ApiAuthError,
        ScheduleError,
        ScheduleCronError,
        ScheduleCommandValidationError,
        SessionVariableError,
        ValueError,
    ) as exc:
        return _schedule_api_error(exc)
    if updated is None:
        return _api_json_error("not_found", "Schedule not found.", 404)
    log.info("API_SCHEDULE_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "schedule_id": updated.id,
    })
    return jsonify({"schedule": _schedule_payload(updated)})


@api_v1_bp.route("/schedules/<schedule_id>", methods=["DELETE"])
@require_api_auth
def api_schedule_delete(schedule_id):
    session_id = _require_session_id()
    try:
        schedule = _schedule_for_api_session(schedule_id, session_id)
    except ApiAuthError as exc:
        return _schedule_api_error(exc)
    removed = delete_schedule(schedule.id)
    log.info("API_SCHEDULE_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "schedule_id": schedule.id,
        "removed": removed,
    })
    return jsonify({"removed": removed})


@api_v1_bp.route("/schedules/<schedule_id>/run-now", methods=["POST"])
@require_api_auth
def api_schedule_run_now(schedule_id):
    session_id = _require_session_id()
    try:
        schedule = _schedule_for_api_session(schedule_id, session_id)
        fired_at = datetime.now(timezone.utc).isoformat()
        with db_connect() as conn:
            status = fire_schedule(conn, schedule, fired_at=fired_at)
            refreshed = get_schedule(schedule.id, conn=conn)
            conn.commit()
    except (ApiAuthError, ScheduleError, ScheduleCronError, ValueError) as exc:
        return _schedule_api_error(exc)
    log.info("API_SCHEDULE_RUN_NOW", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "schedule_id": schedule.id,
        "status": status,
    })
    return jsonify({
        "status": status,
        "fired_at": fired_at,
        "schedule": _schedule_payload(refreshed or schedule),
    })


@api_v1_bp.route("/schedules/<schedule_id>/fires", methods=["GET"])
@require_api_auth
def api_schedule_fires(schedule_id):
    try:
        schedule = _schedule_for_api_session(schedule_id, _require_session_id())
        limit = normalize_page_limit(request.args.get("limit"), 50, 100)
        offset = normalize_page_offset(request.args.get("offset"))
        fires, total = list_schedule_fires(schedule.id, limit=limit, offset=offset)
    except (ApiAuthError, ScheduleError, ValueError) as exc:
        return _schedule_api_error(exc)
    return jsonify(page_payload("fires", [_schedule_fire_payload(fire) for fire in fires], total, limit, offset))


@api_v1_bp.route("/notification-channels", methods=["GET"])
@require_api_auth
def api_notification_channels():
    try:
        return jsonify({"channels": list_notification_channels(_require_session_id())})
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_api_error(exc)


@api_v1_bp.route("/notification-channels", methods=["POST"])
@require_api_auth
def api_notification_channel_create():
    try:
        channel = create_notification_channel(_require_session_id(), _json_body())
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
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
        channel = update_notification_channel(_require_session_id(), channel_id, _json_body())
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
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
        removed = delete_notification_channel(_require_session_id(), channel_id)
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
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
        result = send_test_notification(_require_session_id(), channel_id)
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
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
        events = list_notification_events(
            _require_session_id(),
            limit=normalize_page_limit(request.args.get("limit"), 50, 100),
            offset=normalize_page_offset(request.args.get("offset")),
            status=str(request.args.get("status") or ""),
            channel_id=str(request.args.get("channel_id") or ""),
            trigger=str(request.args.get("trigger") or ""),
        )
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_api_error(exc)
    return jsonify(events)


@api_v1_bp.route("/runs")
@require_api_auth
def api_active_runs():
    runs = [_active_run_summary(active) for active in active_runs_for_session(_require_session_id())]
    return jsonify({"runs": runs, "total": len(runs)})


@api_v1_bp.route("/runs", methods=["POST"])
@require_api_auth
def api_runs_start():
    if not broker_available():
        log.warning("API_BROKER_UNAVAILABLE", extra={
            "ip": get_client_ip(),
            "reason": broker_unavailable_reason(),
        })
        response, status = _api_json_error("broker_unavailable", broker_unavailable_reason(), 503)
        response.headers["Retry-After"] = "5"
        return response, status
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
    try:
        link_project_id = _requested_project_id(data, session_id)
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
    client_ip = get_client_ip()
    owner_tab_id = ""
    workspace_cwd = _workspace_cwd_value(data.get("workspace_cwd", ""))

    if resolves_exact_special_builtin_command(original_command):
        if link_project_id:
            return _api_json_error(
                "project_link_not_supported",
                "Project links only support external command runs.",
                409,
            )
        events, exit_code = execute_builtin_command(original_command, session_id, tab_id=owner_tab_id)
        run_id = _brokered_synthetic_run(
            _history_safe_command_for_storage(original_command),
            session_id,
            client_ip,
            events,
            exit_code,
            owner_tab_id=owner_tab_id,
        )
        log.info("API_RUN_STARTED", extra={
            "ip": client_ip,
            "session": get_log_session_id(session_id),
            "run_id": run_id,
            "cmd": original_command,
            "cmd_type": "builtin",
            "project_id": link_project_id,
        })
        return jsonify(_run_started_payload(run_id, status=_status_for_exit_code(exit_code))), 202

    try:
        prepared_input = _prepare_command_input(original_command, session_id, client_ip)
    except _RunPreparationError as exc:
        return _api_json_error("command_rejected", str(exc), exc.status_code)

    if resolve_builtin_command(prepared_input.execution_command):
        if link_project_id:
            return _api_json_error(
                "project_link_not_supported",
                "Project links only support external command runs.",
                409,
            )
        events, exit_code = execute_builtin_command(prepared_input.execution_command, session_id, tab_id=owner_tab_id)
        run_id = _brokered_synthetic_run(
            _history_safe_command_for_storage(original_command),
            session_id,
            client_ip,
            _filter_builtin_command_events(events, prepared_input.variable_notice, prepared_input.postfilter),
            exit_code,
            owner_tab_id=owner_tab_id,
        )
        log.info("API_RUN_STARTED", extra={
            "ip": client_ip,
            "session": get_log_session_id(session_id),
            "run_id": run_id,
            "cmd": original_command,
            "cmd_type": "builtin",
            "project_id": link_project_id,
        })
        return jsonify(_run_started_payload(run_id, status=_status_for_exit_code(exit_code))), 202

    try:
        prepared_real = _prepare_real_command(
            original_command,
            prepared_input.execution_command,
            session_id,
            client_ip,
            workspace_cwd,
        )
    except _RunPreparationError as exc:
        return _api_json_error("command_rejected", str(exc), exc.status_code)

    if prepared_real.missing_runtime:
        if link_project_id:
            return _api_json_error(
                "project_link_not_supported",
                "Project links only support completed external command runs.",
                409,
            )
        run_id = _brokered_synthetic_run(
            original_command,
            session_id,
            client_ip,
            [{"type": "output", "text": runtime_missing_command_message(prepared_real.missing_runtime)}],
            127,
            cmd_type="missing",
            owner_tab_id=owner_tab_id,
        )
        log.info("API_RUN_STARTED", extra={
            "ip": client_ip,
            "session": get_log_session_id(session_id),
            "run_id": run_id,
            "cmd": original_command,
            "cmd_type": "missing",
            "project_id": link_project_id,
        })
        return jsonify(_run_started_payload(run_id, status="failed")), 202

    try:
        started = _start_real_command_process(original_command, session_id, client_ip, prepared_real)
    except _RunSpawnError as exc:
        return _api_json_error("spawn_failed", str(exc), 500)

    publish_run_event(started.run_id, "started", {"run_id": started.run_id, "started": started.run_started})
    threading.Thread(
        target=_brokered_real_run_worker,
        kwargs={
            "run_id": started.run_id,
            "proc": started.proc,
            "session_id": session_id,
            "client_ip": client_ip,
            "original_command": original_command,
            "run_started": started.run_started,
            "capture": started.capture,
            "signal_classifier": started.signal_classifier,
            "postfilter": prepared_input.postfilter,
            "workspace_path_filter": started.workspace_path_filter,
            "variable_notice": prepared_input.variable_notice,
            "rewrite_notice": prepared_real.rewrite_notice,
            "workspace_notices": _workspace_notice_lines(prepared_real.validation),
            "workspace_artifacts": _workspace_artifacts_from_validation(prepared_real.validation, session_id),
            "owner_tab_id": owner_tab_id,
            "link_project_id": link_project_id,
        },
        name=f"api-run-broker-{started.run_id[:8]}",
        daemon=True,
    ).start()
    log.info("API_RUN_STARTED", extra={
        "ip": client_ip,
        "session": get_log_session_id(session_id),
        "run_id": started.run_id,
        "cmd": original_command,
        "cmd_type": "real",
        "project_id": link_project_id,
    })
    return jsonify(_run_started_payload(started.run_id)), 202


def _status_for_exit_code(exit_code: object) -> str:
    if not isinstance(exit_code, (int, str, bytes, bytearray)):
        return "complete"
    try:
        return "succeeded" if int(exit_code) == 0 else "failed"
    except (TypeError, ValueError):
        return "complete"


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
    run = _run_status_from_active_or_row(run_id, _require_session_id())
    if run is None:
        return _api_json_error("not_found", "Run not found.", 404)
    return jsonify({"run": run})


@api_v1_bp.route("/runs/<run_id>/wait", methods=["POST"])
@require_api_auth
def api_run_wait(run_id):
    session_id = _require_session_id()
    timeout = _parse_float(request.args.get("timeout"), 30.0, minimum=0.0, maximum=3600.0)
    deadline = time.monotonic() + timeout
    poll_interval = 0.1
    while True:
        run = _run_status_from_active_or_row(run_id, session_id)
        if run is None:
            return _api_json_error("not_found", "Run not found.", 404)
        if str(run.get("status") or "") != "running":
            return jsonify({"run": run})
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _api_json_error("wait_timeout", "Run is still running.", 408)
        time.sleep(min(poll_interval, remaining))


@api_v1_bp.route("/runs/<run_id>/projects/<project_id>", methods=["POST"])
@require_api_auth
def api_run_project_link(run_id, project_id):
    session_id = _require_session_id()
    try:
        if _active_project_for_write(session_id, project_id) is None:
            return _api_json_error("not_found", "Project not found.", 404)
        link = link_project_entity(
            session_id,
            project_id,
            {"entity_type": "run", "entity_id": run_id, "source": "manual"},
        )
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
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
    try:
        if _active_project_for_write(session_id, project_id) is None:
            return _api_json_error("not_found", "Project not found.", 404)
        deleted = unlink_project_entity(
            session_id,
            project_id,
            {"entity_type": "run", "entity_id": run_id},
        )
    except ApiAuthError as exc:
        return _api_json_error(exc.code, exc.message, exc.status_code)
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
    if not _run_belongs_to_session(run_id, session_id):
        return _api_json_error("not_found", "Run not found.", 404)
    after_id = _sse_after_id()
    log.debug("API_RUN_STREAM_ATTACHED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "after_id": after_id,
        "format": str(request.args.get("format") or "sse"),
    })
    if str(request.args.get("format") or "").lower() == "ndjson":
        return Response(
            _ndjson_from_sse_chunks(stream_run_events(run_id, after_id=after_id)),
            mimetype="application/x-ndjson",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )
    return Response(
        stream_run_events(run_id, after_id=after_id),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@api_v1_bp.route("/runs/<run_id>/cancel", methods=["POST"])
@require_api_auth
def api_run_cancel(run_id):
    session_id = _require_session_id()
    active_run = next(
        (run for run in active_runs_for_session(session_id) if run.get("run_id") == run_id),
        {},
    )
    if not active_run:
        return _api_json_error("not_found", "Run not found.", 404)
    pid = pid_pop_for_session(run_id, session_id)
    if not pid:
        return _api_json_error("not_found", "No active process found for run.", 404)
    publish_run_event(run_id, "killed", {"api": True})
    try:
        if SCANNER_PREFIX:
            subprocess.run([SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pid}"], timeout=5)
        else:
            os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError) as exc:
        log.warning("API_RUN_CANCEL_SIGNAL_FAILED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "error": str(exc),
        })
    return jsonify({"killed": True, "id": run_id})
