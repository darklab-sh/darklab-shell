"""
History and share routes: run history, single-run permalinks, snapshot permalinks.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, Response, jsonify, request

import config as _config
import services.runs.comparison as run_comparison
from core.helpers import (
    get_client_ip,
    get_log_session_id,
    get_session_id,
)
from services.history.permalinks import _format_duration, _permalink_error_page, _permalink_page
from services.history.queries import (
    bulk_delete_runs,
    bulk_delete_snapshots,
    bulk_export_rows,
    clear_history_runs,
    compare_candidate_rows,
    compare_persisted_objects,
    compare_run_rows,
    delete_history_run,
    delete_snapshot,
    history_insights,
    history_run_cleanup_preview as load_history_run_cleanup_preview,
    history_run_private_metadata,
    history_run_row,
    list_history_items,
    recent_history_commands,
    save_snapshot,
    schedule_refs_for_active_runs,
    session_history_stats,
    snapshot_row,
)
from services.history.run_metadata import (
    normalize_history_filter_text as _normalize_history_filter_text,
)
from core.process import active_runs_for_session
from services.audit.context import route_audit_fields
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScopeError, current_request_scope, requested_team_id, scope_error_payload
from services.atlas.cleanup import (
    public_cleanup_preview,
)
from services.ai.assists import (
    AIAssistRouteError,
    enqueue_next_commands_assist,
    enqueue_summary_assist,
    list_run_assists,
)
from services.projects.comparisons import compare_project_runs
from services.projects.contracts import (
    BULK_AUDIT_FAILURE_LIMIT,
    MAX_BULK_RUN_ACTION_ITEMS,
    MAX_ENTITY_ID_LEN,
    ProjectWorkspaceError,
)
from core.redaction import line_entries_from_events, omit_raw_only_line_entries, redact_line_entries
from services.runs.output_model import LineKind, line_event_from_legacy, to_legacy_entry
from services.runs.output_store import (
    load_run_output_entries_for_run,
    preview_output_entries_from_run,
)
from services.runs.structured_filters import (
    structured_filters_from_params,
)
from services.scheduler.models import OWNER_KIND_WATCHER
from services.storage.body_store import inline_threshold_bytes, load_text_body, maybe_store_text_body
from services.metrics_lazy import app_metrics

APP_VERSION = _config.APP_VERSION
CFG = _config.CFG

log = logging.getLogger("shell")

history_bp = Blueprint("history", __name__)


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


def _truthy_request_arg(name: str) -> bool:
    return str(request.args.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _team_capability_error_response(exc: TeamPermissionDenied):
    return jsonify({"error": "team_forbidden", "message": str(exc)}), 403


def _require_team_capability(owner_scope, capability: Capability):
    if not owner_scope.is_team:
        return None
    try:
        require_capability(str((owner_scope.member or {}).get("role") or ""), capability)
    except TeamPermissionDenied as exc:
        return _team_capability_error_response(exc)
    return None


def _require_history_mutation_capability(owner_scope):
    return _require_team_capability(owner_scope, Capability.MANAGE_HISTORY)


BULK_HISTORY_EXPORT_MAX_ITEMS = 500
BULK_HISTORY_EXPORT_MAX_BYTES = 50 * 1024 * 1024


@history_bp.before_request
def _require_history_write_session():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not get_session_id():
        return jsonify({"error": "session_required"}), 401
    return None


def _parse_history_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _ai_route_error(exc: AIAssistRouteError):
    return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


def _parse_history_int(value, default, *, minimum=1, maximum=None):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    if parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


# ── Preview output helpers ────────────────────────────────────────────────────

def _preview_output_entries_from_run(run):
    return preview_output_entries_from_run(run)


def _preview_output_from_run(run):
    return [entry["text"] for entry in _preview_output_entries_from_run(run)]


def _preview_notice(run):
    if not run.get("preview_truncated"):
        return None
    shown = CFG.get("max_output_lines", 0) or len(_preview_output_from_run(run))
    total = run.get("output_line_count") or shown
    if run.get("full_output_available"):
        return (
            f"[preview truncated — only the last {shown} lines are shown here, "
            "but the full output had "
            f"{total} lines. To view the full output, use either permalink "
            "button now; after another command, use this command's history "
            "permalink.]"
        )
    return (
        f"[preview truncated — only the last {shown} lines are shown here, "
        f"but the full output had {total} lines. "
        "Full output persistence is disabled or unavailable]"
    )


def _run_output_structured_summary(events):
    summary = {
        "kinds": {},
        "signals": {},
        "entity_types": {},
        "outline": [],
        "signal_toc": [],
    }
    seen_signal_lines = set()
    for fallback_index, event in enumerate(events):
        line_number = event.line_index if isinstance(event.line_index, int) else fallback_index
        summary["kinds"][event.kind.value] = summary["kinds"].get(event.kind.value, 0) + 1
        for signal in event.signals:
            summary["signals"][signal.value] = summary["signals"].get(signal.value, 0) + 1
            signal_key = (signal.value, line_number)
            if signal_key not in seen_signal_lines and len(summary["signal_toc"]) < 25:
                seen_signal_lines.add(signal_key)
                summary["signal_toc"].append({
                    "line_number": line_number + 1,
                    "signal": signal.value,
                    "text": event.text[:160],
                })
        for entity in event.entities:
            summary["entity_types"][entity.type] = summary["entity_types"].get(entity.type, 0) + 1
        if event.role.value in {"section-header", "kv"} and len(summary["outline"]) < 25:
            summary["outline"].append({
                "line_number": line_number + 1,
                "role": event.role.value,
                "text": event.text[:160],
            })
    return summary


def _resolve_compare_request(session_id, left_id, right_id, project_id="", baseline_label=""):
    project_comparison = None
    if project_id:
        try:
            project_comparison = compare_project_runs(session_id, project_id, {
                "left_run_id": left_id,
                "right_run_id": right_id,
                "baseline_label": baseline_label,
            })
        except ProjectWorkspaceError as exc:
            return "", "", None, (jsonify({"error": str(exc)}), 400)
        if project_comparison is None:
            return "", "", None, (jsonify({"error": "project not found"}), 404)
        left_id = str(project_comparison.get("left_run_id") or "")
        right_id = str(project_comparison.get("right_run_id") or "")
    if not left_id or not right_id:
        return "", "", None, (jsonify({"error": "left and right run ids are required"}), 400)
    if left_id == right_id:
        return "", "", None, (jsonify({"error": "Choose two different runs to compare"}), 400)
    return left_id, right_id, project_comparison, None


def _parse_compare_range_value(name):
    raw = request.args.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# Routes

@history_bp.route("/history")
def get_history():
    """Return the most recent completed runs for this session."""
    # History is isolated per anonymous browser session, not shared globally.
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    query, structured_filters = structured_filters_from_params(
        request.args,
        query=_normalize_history_filter_text(request.args.get("q")),
    )
    command_root = _normalize_history_filter_text(request.args.get("command_root")).lower()
    exit_code_filter = _normalize_history_filter_text(request.args.get("exit_code")).lower()
    date_range = _normalize_history_filter_text(request.args.get("date_range")).lower()
    type_filter = _normalize_history_filter_text(request.args.get("type")).lower() or "all"
    project_id = _normalize_history_filter_text(request.args.get("project_id"))
    starred_only = _parse_history_bool(request.args.get("starred_only"))
    include_total = _parse_history_bool(request.args.get("include_total"))
    page = _parse_history_int(request.args.get("page"), 1)
    page_size = _parse_history_int(request.args.get("page_size"), CFG["history_panel_limit"], maximum=200)
    # scope=command suppresses FTS so the search only considers the command
    # column. Reverse-i-search uses this to behave like bash i-search — matching
    # on typed command text, not on output text that FTS would otherwise pull in.
    scope = _normalize_history_filter_text(request.args.get("scope")).lower()
    if type_filter not in {"all", "runs", "runs_builtin", "runs_external", "snapshots"}:
        type_filter = "all"

    result = list_history_items(
        session_id=session_id,
        owner_scope=owner_scope,
        query=query,
        structured_filters=structured_filters,
        command_root=command_root,
        exit_code_filter=exit_code_filter,
        date_range=date_range,
        type_filter=type_filter,
        project_id=project_id,
        starred_only=starred_only,
        include_total=include_total,
        page=page,
        page_size=page_size,
        scope=scope,
    )
    log.info("HISTORY_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": len(result.items),
        "query_present": bool(query),
        "query_len": len(query),
        "output_search": bool(result.fts_query),
        "command_root": command_root or None,
        "exit_code_filter": exit_code_filter or None,
        "date_range": date_range or None,
        "type_filter": type_filter,
        "project_id": project_id or None,
        "starred_only": starred_only or None,
        "page": result.current_page,
        "page_size": page_size,
    })
    payload = {
        "items": result.items,
        "runs": result.runs,
        "roots": result.roots,
        "page": result.current_page,
        "page_size": page_size,
        "has_prev": result.current_page > 1,
        "has_next": bool(result.page_count and result.current_page < result.page_count),
    }
    if include_total:
        payload["total_count"] = result.total_count
        payload["page_count"] = result.page_count
    return jsonify(payload)


@history_bp.route("/history/commands")
def get_history_commands():
    """Return recent distinct run commands for prompt history and recents."""
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    limit = _parse_history_int(
        request.args.get("limit"),
        CFG["recent_commands_limit"],
        maximum=200,
    )
    runs = recent_history_commands(owner_scope, limit=limit)
    log.debug("HISTORY_COMMANDS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": len(runs),
        "limit": limit,
    })
    return jsonify({
        "commands": [run["command"] for run in runs],
        "runs": runs,
        "limit": limit,
    })


@history_bp.route("/history/stats")
def get_history_stats():
    """Return compact session-level history counters for Status Monitor."""
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    payload = session_history_stats(session_id, owner_scope)
    log.debug("HISTORY_STATS_VIEWED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id),
    })
    return jsonify(payload)


@history_bp.route("/history/insights")
def get_history_insights():
    """Return compact visual history data for the Status Monitor."""
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    requested_days = _normalize_history_filter_text(request.args.get("days")).lower()
    days = (
        None
        if requested_days in {"", "auto"}
        else _parse_history_int(requested_days, 28, minimum=28, maximum=365)
    )
    payload = history_insights(session_id, owner_scope, days=days)
    log.debug("HISTORY_INSIGHTS_VIEWED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id),
        "days": payload.get("days"),
    })
    return jsonify(payload)


@history_bp.route("/history/active")
def get_active_history_runs():
    """Return currently running commands for this session."""
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    client_id = str(request.headers.get("X-Client-ID", "") or "").strip()[:128]
    runs = active_runs_for_session(session_id, client_id=client_id, team_id=owner_scope.team_id)
    include_scheduled = _truthy_request_arg("include_scheduled")
    if runs:
        run_ids = [str(run.get("run_id") or "") for run in runs if str(run.get("run_id") or "")]
        scheduled_by_run = schedule_refs_for_active_runs(run_ids)
        filtered_runs = []
        for run in runs:
            run_id = str(run.get("run_id") or "")
            schedule_ref = scheduled_by_run.get(run_id)
            _apply_schedule_ref(run, schedule_ref)
            if include_scheduled or not run.get("scheduled"):
                filtered_runs.append(run)
        runs = filtered_runs
    log.debug("ACTIVE_RUNS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": len(runs),
        "include_scheduled": include_scheduled,
    })
    return jsonify({"runs": runs})


@history_bp.route("/history/<run_id>/compare-candidates")
def get_run_compare_candidates(run_id):
    """Return ranked previous runs that are plausible comparisons for a run."""
    session_id = get_session_id()
    limit = _parse_history_int(request.args.get("limit"), 5, maximum=20)
    source, rows = compare_candidate_rows(session_id, run_id)
    if not source:
        return jsonify({"error": "Run not found"}), 404

    candidates = []
    for row in rows:
        payload = run_comparison.run_candidate_payload(row, source)
        if payload["score"] > 0:
            candidates.append(payload)
    candidates.sort(key=lambda item: (int(item["score"]), str(item.get("started") or "")), reverse=True)
    candidates = candidates[:limit]
    return jsonify({
        "source": run_comparison.compare_run_summary(source),
        "candidates": candidates,
        "suggested": candidates[0] if candidates else None,
    })


@history_bp.route("/history/compare")
def compare_history_runs():
    """Compare two completed runs from the current session."""
    session_id = get_session_id()
    project_id = _normalize_history_filter_text(request.args.get("project_id"))
    baseline_label = _normalize_history_filter_text(request.args.get("baseline_label"))
    left_id = _normalize_history_filter_text(request.args.get("left") or request.args.get("left_run_id"))
    right_id = _normalize_history_filter_text(request.args.get("right") or request.args.get("right_run_id"))
    left_id, right_id, project_comparison, error = _resolve_compare_request(
        session_id,
        left_id,
        right_id,
        project_id,
        baseline_label,
    )
    if error:
        return error

    left_run, right_run = compare_run_rows(session_id, left_id, right_id)
    if not left_run or not right_run:
        return jsonify({"error": "Run not found"}), 404

    left_entries, left_output = run_comparison.compare_entries_for_diff(left_run)
    right_entries, right_output = run_comparison.compare_entries_for_diff(right_run)
    left_finding_count = run_comparison.finding_count_for_entries(left_run, left_entries)
    right_finding_count = run_comparison.finding_count_for_entries(right_run, right_entries)
    diff = run_comparison.hunk_line_diff(
        left_entries,
        right_entries,
        max_changed_lines=run_comparison.COMPARE_MAX_CHANGED_LINES,
        max_hunks=run_comparison.COMPARE_MAX_HUNKS,
        inline_context=run_comparison.COMPARE_INLINE_EQUAL_CONTEXT,
    )
    project_truncated = project_comparison.get("truncated", {}) if project_comparison else {}
    if project_comparison:
        finding_objects = project_comparison.get("objects", {}).get("findings", {})
        artifact_objects = project_comparison.get("objects", {}).get("artifacts", {})
        left_persisted_finding_count = int(project_comparison.get("left", {}).get("persisted_finding_count") or 0)
        right_persisted_finding_count = int(project_comparison.get("right", {}).get("persisted_finding_count") or 0)
        left_artifact_count = int(project_comparison.get("left", {}).get("artifact_count") or 0)
        right_artifact_count = int(project_comparison.get("right", {}).get("artifact_count") or 0)
    else:
        compare_objects = compare_persisted_objects(session_id, left_id, right_id)
        finding_objects = compare_objects["finding_objects"]
        artifact_objects = compare_objects["artifact_objects"]
        left_persisted_finding_count = compare_objects["left_persisted_finding_count"]
        right_persisted_finding_count = compare_objects["right_persisted_finding_count"]
        left_artifact_count = compare_objects["left_artifact_count"]
        right_artifact_count = compare_objects["right_artifact_count"]
        project_truncated = compare_objects["project_truncated"]
    finding_objects = run_comparison.add_compare_line_indexes(finding_objects, left_entries, right_entries)
    density_buckets = run_comparison.density_buckets_for_hunks(diff["hunks"])

    truncated = {
        "left": bool(left_output["partial"] or project_truncated.get("left")),
        "right": bool(right_output["partial"] or project_truncated.get("right")),
        "changed_lines": bool(
            diff["truncated"]["hunks_omitted"]
            or diff["truncated"]["lines_omitted"]["total"]
        ),
        "hunks_omitted": diff["truncated"]["hunks_omitted"],
        "lines_omitted": diff["truncated"]["lines_omitted"],
    }
    for key in ("findings", "artifacts", "item_limit"):
        if key in project_truncated:
            truncated[key] = project_truncated[key]
    payload = {
        "left_run_id": left_id,
        "right_run_id": right_id,
        "left": {
            **run_comparison.compare_run_summary(left_run),
            "finding_count": left_finding_count,
            "persisted_finding_count": left_persisted_finding_count,
            "artifact_count": left_artifact_count,
            "output_source": left_output,
        },
        "right": {
            **run_comparison.compare_run_summary(right_run),
            "finding_count": right_finding_count,
            "persisted_finding_count": right_persisted_finding_count,
            "artifact_count": right_artifact_count,
            "output_source": right_output,
        },
        "deltas": run_comparison.compare_deltas(left_run, right_run, left_finding_count, right_finding_count),
        "objects": {
            "findings": finding_objects,
            "artifacts": artifact_objects,
            "entities": run_comparison.compare_entity_sets(left_entries, right_entries),
        },
        "derived_changes": run_comparison.compare_derived_changes(
            left_run,
            right_run,
            left_entries,
            right_entries,
        ),
        "hunks": diff["hunks"],
        "density_buckets": density_buckets,
        "totals": diff["totals"],
        "truncated": truncated,
        "limits": {
            "max_changed_lines": run_comparison.COMPARE_MAX_CHANGED_LINES,
            "max_hunks": run_comparison.COMPARE_MAX_HUNKS,
            "inline_equal_context": run_comparison.COMPARE_INLINE_EQUAL_CONTEXT,
            "line_display_truncate": run_comparison.COMPARE_LINE_DISPLAY_TRUNCATE,
            "lazy_equal_page_limit": run_comparison.COMPARE_LAZY_EQUAL_PAGE_LIMIT,
            "lazy_equal_byte_limit": run_comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT,
            "minimap_buckets": run_comparison.COMPARE_MINIMAP_BUCKETS,
        },
    }
    if project_comparison:
        payload["project_id"] = project_id
        payload["baseline_label"] = project_comparison.get("baseline_label", baseline_label)
    return jsonify(payload)


@history_bp.route("/history/compare/lines")
def compare_history_lines():
    """Return a bounded filtered-output slice for lazy compare hunk expansion."""
    session_id = get_session_id()
    project_id = _normalize_history_filter_text(request.args.get("project_id"))
    baseline_label = _normalize_history_filter_text(request.args.get("baseline_label"))
    left_id = _normalize_history_filter_text(request.args.get("left") or request.args.get("left_run_id"))
    right_id = _normalize_history_filter_text(request.args.get("right") or request.args.get("right_run_id"))
    side = _normalize_history_filter_text(request.args.get("side")).lower()
    start = _parse_compare_range_value("start")
    end = _parse_compare_range_value("end")
    if side not in {"a", "b"}:
        return jsonify({"error": "side must be a or b"}), 400
    if start is None or end is None or start < 0 or end < start:
        return jsonify({"error": "start and end must define a valid range"}), 400

    left_id, right_id, _, error = _resolve_compare_request(
        session_id,
        left_id,
        right_id,
        project_id,
        baseline_label,
    )
    if error:
        return error
    left_run, right_run = compare_run_rows(session_id, left_id, right_id)
    if not left_run or not right_run:
        return jsonify({"error": "Run not found"}), 404
    selected_run = left_run if side == "a" else right_run
    entries, _ = run_comparison.compare_entries_for_diff(selected_run)
    available_end = len(entries)
    range_clamped = end > available_end
    if start > available_end:
        start = available_end
    if range_clamped:
        end = available_end

    lines = []
    byte_count = 0
    cursor = start
    while cursor < end and len(lines) < run_comparison.COMPARE_LAZY_EQUAL_PAGE_LIMIT:
        entry = entries[cursor]
        payload = run_comparison.compare_line_payload(entry)
        encoded_len = len(payload["text"].encode("utf-8", errors="replace"))
        next_byte_count = byte_count + encoded_len
        would_exceed_byte_limit = next_byte_count > run_comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT
        if lines and would_exceed_byte_limit:
            break
        lines.append(payload)
        byte_count = next_byte_count
        cursor += 1
        # Always return at least one line, even when that single line exceeds the
        # byte cap, then stop before appending more.
        if byte_count >= run_comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT:
            break

    return jsonify({
        "lines": lines,
        "start": start,
        "end": cursor,
        "truncated": bool(cursor < end or range_clamped),
        "range_clamped": range_clamped,
        "page_limit": run_comparison.COMPARE_LAZY_EQUAL_PAGE_LIMIT,
        "byte_limit": run_comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT,
        **({"note": "requested range exceeded available compared output"} if range_clamped else {}),
    })


@history_bp.route("/runs/<run_id>/ai-assists")
def history_run_ai_assists(run_id):
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    try:
        assists = list_run_assists(session_id, run_id, team_id=owner_scope.team_id)
    except AIAssistRouteError as exc:
        return _ai_route_error(exc)
    return jsonify({"assists": assists})


@history_bp.route("/runs/<run_id>/ai-summary", methods=["POST"])
def history_run_ai_summary(run_id):
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    data = request.get_json(silent=True)
    if data is not None and not isinstance(data, dict):
        return jsonify({"error": "invalid_body", "message": "Request body must be a JSON object"}), 400
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    try:
        assist, status_code = enqueue_summary_assist(
            session_id,
            run_id,
            team_id=owner_scope.team_id,
            force=_parse_history_bool((data or {}).get("force")),
        )
    except AIAssistRouteError as exc:
        return _ai_route_error(exc)
    return jsonify({"assist": assist}), status_code


@history_bp.route("/runs/<run_id>/ai-next-commands", methods=["POST"])
def history_run_ai_next_commands(run_id):
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    data = request.get_json(silent=True)
    if data is not None and not isinstance(data, dict):
        return jsonify({"error": "invalid_body", "message": "Request body must be a JSON object"}), 400
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    try:
        assist, status_code = enqueue_next_commands_assist(
            session_id,
            run_id,
            team_id=owner_scope.team_id,
            force=_parse_history_bool((data or {}).get("force")),
        )
    except AIAssistRouteError as exc:
        return _ai_route_error(exc)
    return jsonify({"assist": assist}), status_code


@history_bp.route("/history/<run_id>")
def get_run(run_id):
    """Serve a styled HTML permalink page for a single run, or JSON if ?json is passed."""
    session_id = get_session_id()
    run = history_run_row(run_id)
    if not run:
        log.warning("RUN_NOT_FOUND", extra={
            "ip": get_client_ip(),
            "run_id": run_id,
            "session": get_log_session_id(session_id),
        })
        return _permalink_error_page("run")
    run_team_id = str(run.get("team_id") or "")
    requested_run_team_id = requested_team_id(request)
    team_scope_allowed = False
    if run_team_id and requested_run_team_id:
        if requested_run_team_id != run_team_id:
            if "json" in request.args:
                return jsonify({
                    "error": "team_scope_mismatch",
                    "message": "This run belongs to a different team scope.",
                }), 404
            return _permalink_error_page("run")
        try:
            team_scope_allowed = current_request_scope(session_id, request).team_id == run_team_id
        except RequestScopeError as exc:
            if "json" in request.args:
                payload, status = scope_error_payload(exc)
                return jsonify(payload), status
            return _permalink_error_page("run")
    run["preview_truncated"] = bool(run.get("preview_truncated"))
    run["full_output_available"] = bool(run.get("full_output_available"))
    run["full_output_truncated"] = bool(run.get("full_output_truncated"))
    preview_requested = request.args.get("preview") == "1"
    output_result = load_run_output_entries_for_run(
        run,
        prefer_full=not preview_requested,
        log_event="HISTORY_FULL_OUTPUT_LOAD_FAILED",
    )
    is_full_view = output_result.source == "full"
    run["full_output_fallback"] = output_result.fallback
    run["output_entries"] = output_result.entries
    run["output"] = [entry["text"] for entry in run["output_entries"]]
    run["output_summary"] = _run_output_structured_summary(output_result.events)
    if is_full_view:
        if run["full_output_truncated"]:
            truncated_mb = CFG.get("full_output_max_mb", 0)
            run["output"].append(
                f"[full output truncated after {truncated_mb} MB]"
            )
            run["output_entries"].append(to_legacy_entry(line_event_from_legacy(
                f"[full output truncated after {truncated_mb} MB]",
                kind=LineKind.notice,
            )))
    include_private_metadata = (
        not run_team_id
        and str(run.get("session_id") or "") == str(session_id or "")
    )
    if run_team_id:
        include_private_metadata = team_scope_allowed
    run_metadata = history_run_private_metadata(
        run_id,
        session_id,
        run_team_id,
        include_private_metadata=include_private_metadata,
    )
    artifacts_by_run = run_metadata["artifacts_by_run"]
    finding_counts_by_run = run_metadata["finding_counts_by_run"]
    atlas_counts = run_metadata["atlas_counts"]
    findings_by_run = run_metadata["findings_by_run"]
    labels_by_run = run_metadata["labels_by_run"]
    notes_by_run = run_metadata["notes_by_run"]
    scheduled_by_run = run_metadata["scheduled_by_run"]
    if not include_private_metadata:
        run["output_entries"] = line_entries_from_events(omit_raw_only_line_entries(run["output_entries"]))
        run["output"] = [
            str(entry.get("text", "")) if isinstance(entry, dict) else str(entry)
            for entry in run["output_entries"]
        ]
        run["output_preview"] = json.dumps(run["output_entries"])
        run["output_search_text"] = "\n".join(run["output"])
    run["artifacts"] = artifacts_by_run.get(str(run_id), [])
    run["artifact_count"] = len(run["artifacts"])
    run["findings"] = findings_by_run.get(str(run_id), [])
    run["labels"] = labels_by_run.get(str(run_id), [])
    run["note"] = (notes_by_run.get(str(run_id), []) or [None])[0]
    run["finding_count"] = finding_counts_by_run.get(str(run_id), 0)
    run["label_count"] = len(run["labels"])
    run["note_count"] = len(notes_by_run.get(str(run_id), []))
    run.update(atlas_counts.get(str(run_id), {
        "atlas_entity_count": 0,
        "atlas_finding_count": 0,
    }))
    _apply_schedule_ref(run, scheduled_by_run.get(str(run_id)))
    run["preview_notice"] = _preview_notice(run) if not is_full_view else None
    log.info("RUN_VIEWED", extra={
        "ip": get_client_ip(), "run_id": run_id,
        "session": get_log_session_id(session_id),
        "run_session": get_log_session_id(run.get("session_id")),
        "cmd": run["command"], "full_output": is_full_view,
    })

    if "json" in request.args:
        return jsonify(run)

    content_lines = list(run["output_entries"])
    preview_notice = run["preview_notice"]
    if preview_notice:
        content_lines.append(to_legacy_entry(line_event_from_legacy(preview_notice, kind=LineKind.notice)))

    line_count = len(content_lines)
    if is_full_view:
        lines_label = f"{line_count:,} lines · full output"
        if run.get("full_output_truncated"):
            lines_label += " (truncated)"
    elif run.get("preview_truncated"):
        total = run.get("output_line_count") or line_count
        lines_label = f"preview · {line_count:,} of {total:,} lines"
    else:
        lines_label = f"{line_count:,} lines"

    meta = {
        "exit_code": run.get("exit_code"),
        "duration": _format_duration(run["started"], run["finished"]) if run.get("finished") else None,
        "lines": lines_label,
        "artifact_count": run["artifact_count"],
        "finding_count": run["finding_count"],
        "atlas_entity_count": run["atlas_entity_count"],
        "atlas_finding_count": run["atlas_finding_count"],
        "label_count": run["label_count"],
        "note_count": run["note_count"],
        "version": APP_VERSION,
    }

    return _permalink_page(
        title=f"$ {run['command']}" + (" (full output)" if is_full_view else ""),
        label=run["command"],
        created=run["started"],
        content_lines=content_lines,
        json_url=f"/history/{run_id}?json",
        meta=meta,
        command=run["command"],
    )


@history_bp.route("/history/<run_id>", methods=["DELETE"])
def delete_run(run_id):
    """Delete a specific run from history for this session."""
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_history_mutation_capability(owner_scope)
    if capability_response is not None:
        return capability_response
    prune_atlas = str(request.args.get("prune_atlas") or "").strip().lower() in {"1", "true", "yes"}
    prune_curated_atlas = str(request.args.get("prune_curated_atlas") or "").strip().lower() in {"1", "true", "yes"}
    deleted_count, atlas_cleanup = delete_history_run(
        session_id=session_id,
        owner_scope=owner_scope,
        run_id=run_id,
        prune_atlas=prune_atlas,
        prune_curated_atlas=prune_curated_atlas,
        audit_fields=route_audit_fields(session_id, request, owner_scope),
    )
    if deleted_count:
        log.info("HISTORY_DELETED", extra={
            "ip": get_client_ip(), "run_id": run_id, "session": get_log_session_id(session_id),
        })
    else:
        log.debug("HISTORY_DELETE_MISS", extra={
            "ip": get_client_ip(), "run_id": run_id, "session": get_log_session_id(session_id),
        })
    return jsonify({"ok": True, "atlas_cleanup": atlas_cleanup})


@history_bp.route("/history/<run_id>/atlas-cleanup-preview")
def history_run_atlas_cleanup_preview(run_id):
    """Preview non-curated Atlas rows that can be removed with a run."""
    session_id = get_session_id()
    preview = load_history_run_cleanup_preview(session_id, run_id)
    if preview is None:
        return jsonify({"error": "run not found"}), 404
    return jsonify({"ok": True, "cleanup": public_cleanup_preview(preview)})


def _normalize_bulk_ids_payload(data, key, *, required=True, limit=MAX_BULK_RUN_ACTION_ITEMS):
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    raw_ids = data.get(key)
    if raw_ids is None and not required:
        return [], None
    if not isinstance(raw_ids, list):
        return None, (jsonify({"error": f"{key} must be a list"}), 400)
    if len(raw_ids) > limit:
        return None, (jsonify({"error": "too_many", "limit": limit}), 400)
    ids = []
    seen = set()
    for raw_id in raw_ids:
        if not isinstance(raw_id, str):
            return None, (jsonify({"error": f"{key} entries must be strings"}), 400)
        item_id = raw_id.strip()
        if len(item_id) > MAX_ENTITY_ID_LEN:
            return None, (jsonify({"error": f"{key} entries are too long", "limit": MAX_ENTITY_ID_LEN}), 400)
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        ids.append(item_id)
    if not ids and required:
        return None, (jsonify({"error": f"{key} is required"}), 400)
    return ids, None


def _normalize_bulk_run_ids_payload(data, *, required=True, limit=MAX_BULK_RUN_ACTION_ITEMS):
    return _normalize_bulk_ids_payload(data, "run_ids", required=required, limit=limit)


def _normalize_bulk_snapshot_ids_payload(data, *, required=True, limit=MAX_BULK_RUN_ACTION_ITEMS):
    return _normalize_bulk_ids_payload(data, "snapshot_ids", required=required, limit=limit)


def _bulk_delete_result(counts, item_id, status, *, key="run_id", reason=None):
    counts[status] = counts.get(status, 0) + 1
    item = {key: item_id, "status": status}
    if reason:
        item["reason"] = reason
    return item


def _bulk_delete_failures(results, *, key="run_id"):
    failures = []
    for item in results:
        if item.get("status") not in {"not_found", "rejected"}:
            continue
        failure = {
            key: item.get(key) or "",
            "status": item.get("status") or "",
        }
        if item.get("reason"):
            failure["reason"] = item.get("reason")
        failures.append(failure)
        if len(failures) >= BULK_AUDIT_FAILURE_LIMIT:
            break
    return failures


def _normalize_bulk_export_payload(data):
    if not isinstance(data, dict):
        return None, None, None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    export_format = str(data.get("format") or "txt").strip().lower()
    if export_format not in {"txt", "jsonl"}:
        return None, None, None, (jsonify({"error": "unsupported_format", "formats": ["txt", "jsonl"]}), 400)
    run_ids, error_response = _normalize_bulk_run_ids_payload(
        data,
        required=False,
        limit=BULK_HISTORY_EXPORT_MAX_ITEMS,
    )
    if error_response is not None:
        return None, None, None, error_response
    snapshot_ids, error_response = _normalize_bulk_snapshot_ids_payload(
        data,
        required=False,
        limit=BULK_HISTORY_EXPORT_MAX_ITEMS,
    )
    if error_response is not None:
        return None, None, None, error_response
    assert run_ids is not None
    assert snapshot_ids is not None
    if len(run_ids) + len(snapshot_ids) > BULK_HISTORY_EXPORT_MAX_ITEMS:
        return None, None, None, (
            jsonify({"error": "too_many", "limit": BULK_HISTORY_EXPORT_MAX_ITEMS}),
            400,
        )
    if not run_ids and not snapshot_ids:
        return None, None, None, (jsonify({"error": "selection_required"}), 400)
    return run_ids, snapshot_ids, export_format, None


def _history_export_filename(export_format):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = "jsonl" if export_format == "jsonl" else "txt"
    return f"darklab-history-{stamp}.{suffix}"


def _history_export_run_record(run):
    output = load_run_output_entries_for_run(run, log_event="BULK_HISTORY_EXPORT_OUTPUT_LOAD_FAILED")
    lines = [str(entry.get("text") or "") for entry in output.entries]
    return {
        "kind": "run",
        "id": str(run.get("id") or ""),
        "command": str(run.get("command") or ""),
        "run_kind": str(run.get("run_kind") or ""),
        "status": "completed",
        "started": run.get("started"),
        "finished": run.get("finished"),
        "exit_code": run.get("exit_code"),
        "line_count": len(lines),
        "output_source": output.source,
        "output_truncated": bool(output.truncated),
        "lines": lines,
    }


def _history_export_snapshot_record(snapshot):
    try:
        content = json.loads(load_text_body(snapshot.get("content")) or "[]")
    except (TypeError, json.JSONDecodeError, ValueError):
        content = []
    lines = []
    for item in content:
        if isinstance(item, str):
            lines.append(item)
        elif isinstance(item, dict):
            lines.append(str(item.get("text") or ""))
    return {
        "kind": "snapshot",
        "id": str(snapshot.get("id") or ""),
        "label": str(snapshot.get("label") or ""),
        "created": snapshot.get("created"),
        "line_count": len(lines),
        "lines": lines,
    }


def _history_export_skip_record(item_kind, item_id, status, reason=""):
    record = {"kind": item_kind, "id": item_id, "status": status}
    if reason:
        record["reason"] = reason
    return record


def _history_export_bytes(lines):
    return sum(len(line.encode("utf-8")) for line in lines)


def _history_export_jsonl_summary(items, skipped, *, truncated):
    return json.dumps({
        "kind": "summary",
        "items": int(items),
        "skipped": skipped,
        "truncated": bool(truncated),
    }, sort_keys=True, separators=(",", ":")) + "\n"


def _history_export_jsonl_lines(records, skipped):
    accepted = []
    emitted = 0
    truncated = False
    summary_bytes = len(_history_export_jsonl_summary(0, skipped, truncated=True).encode("utf-8"))
    for record in records:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        line_bytes = len(line.encode("utf-8"))
        if emitted + line_bytes + summary_bytes > BULK_HISTORY_EXPORT_MAX_BYTES:
            truncated = True
            break
        emitted += line_bytes
        accepted.append(line)
    for line in accepted:
        yield line
    yield _history_export_jsonl_summary(len(accepted), skipped, truncated=truncated)


def _history_export_txt_block(record):
    if record.get("kind") == "run":
        lines = [
            f"-- run {record.get('id')} --\n",
            f"command: {record.get('command')}\n",
            f"started: {record.get('started') or ''}\n",
            f"finished: {record.get('finished') or ''}\n",
            f"exit_code: {record.get('exit_code') if record.get('exit_code') is not None else ''}\n\n",
        ]
    else:
        lines = [
            f"-- snapshot {record.get('id')} --\n",
            f"label: {record.get('label')}\n",
            f"created: {record.get('created') or ''}\n\n",
        ]
    for line in record.get("lines") or []:
        lines.append(f"{line}\n")
    lines.append("\n")
    return lines


def _history_export_txt_skipped_footer(skipped):
    if not skipped:
        return []
    lines = ["-- skipped --\n"]
    for item in skipped:
        lines.append("\t".join([
            str(item.get("id") or ""),
            str(item.get("kind") or ""),
            str(item.get("reason") or item.get("status") or ""),
        ]) + "\n")
    return lines


def _history_export_txt_lines(records, skipped):
    accepted_blocks = []
    emitted = 0
    truncated = False
    footer = _history_export_txt_skipped_footer(skipped)
    footer_bytes = _history_export_bytes(footer)
    header_bytes = len("darklab history export\nitems: 0\ntruncated: yes\n\n".encode("utf-8"))
    for record in records:
        block = _history_export_txt_block(record)
        block_bytes = _history_export_bytes(block)
        if emitted + block_bytes + footer_bytes + header_bytes > BULK_HISTORY_EXPORT_MAX_BYTES:
            truncated = True
            break
        emitted += block_bytes
        accepted_blocks.append(block)
    yield f"darklab history export\nitems: {len(accepted_blocks)}\ntruncated: {'yes' if truncated else 'no'}\n\n"
    for block in accepted_blocks:
        yield from block
    if skipped:
        yield from footer


@history_bp.route("/history/bulk-export", methods=["POST"])
def bulk_export_history():
    """Export selected completed runs and snapshots for this session."""
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    run_ids, snapshot_ids, export_format, error_response = _normalize_bulk_export_payload(
        request.get_json(silent=True) or {},
    )
    if error_response is not None:
        return error_response
    assert run_ids is not None
    assert snapshot_ids is not None
    assert export_format is not None

    active_ids = {
        str(item.get("run_id") or "")
        for item in active_runs_for_session(session_id, team_id=owner_scope.team_id)
        if item.get("run_id")
    }
    records = []
    skipped = []
    counts = {"exported": 0, "not_found": 0, "rejected": 0}
    owned_runs, owned_snapshots = bulk_export_rows(owner_scope, run_ids, snapshot_ids)

    for run_id in run_ids:
        if run_id in active_ids:
            skipped.append(_history_export_skip_record("run", run_id, "rejected", "running"))
            _bulk_delete_result(counts, run_id, "rejected", reason="running")
            continue
        run = owned_runs.get(run_id)
        if run is None:
            skipped.append(_history_export_skip_record("run", run_id, "not_found"))
            _bulk_delete_result(counts, run_id, "not_found")
            continue
        if run.get("finished") is None and run.get("exit_code") is None:
            skipped.append(_history_export_skip_record("run", run_id, "rejected", "incomplete"))
            _bulk_delete_result(counts, run_id, "rejected", reason="incomplete")
            continue
        records.append(_history_export_run_record(run))
        _bulk_delete_result(counts, run_id, "exported")

    for snapshot_id in snapshot_ids:
        snapshot = owned_snapshots.get(snapshot_id)
        if snapshot is None:
            skipped.append(_history_export_skip_record("snapshot", snapshot_id, "not_found"))
            _bulk_delete_result(counts, snapshot_id, "not_found", key="snapshot_id")
            continue
        records.append(_history_export_snapshot_record(snapshot))
        _bulk_delete_result(counts, snapshot_id, "exported", key="snapshot_id")

    filename = _history_export_filename(export_format)
    if export_format == "jsonl":
        lines = _history_export_jsonl_lines(records, skipped)
        content_type = "application/x-ndjson; charset=utf-8"
    else:
        lines = _history_export_txt_lines(records, skipped)
        content_type = "text/plain; charset=utf-8"

    log.info("HISTORY_BULK_EXPORTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "format": export_format,
        "counts": counts,
        "failures": skipped[:BULK_AUDIT_FAILURE_LIMIT],
    })
    return Response(
        lines,
        content_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@history_bp.route("/history/bulk-delete", methods=["POST"])
def bulk_delete_history():
    """Delete selected completed runs for this session."""
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_history_mutation_capability(owner_scope)
    if capability_response is not None:
        return capability_response
    run_ids, error_response = _normalize_bulk_run_ids_payload(request.get_json(silent=True) or {})
    if error_response is not None:
        return error_response
    active_ids = {
        str(item.get("run_id") or "")
        for item in active_runs_for_session(session_id, team_id=owner_scope.team_id)
        if item.get("run_id")
    }
    assert run_ids is not None
    counts, results = bulk_delete_runs(
        owner_scope=owner_scope,
        session_id=session_id,
        run_ids=run_ids,
        active_ids=active_ids,
        result_factory=_bulk_delete_result,
        audit_fields=route_audit_fields(session_id, request, owner_scope),
    )
    log.info("HISTORY_BULK_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": counts["deleted"],
        "counts": counts,
        "failures": _bulk_delete_failures(results),
    })
    return jsonify({"ok": True, "counts": counts, "results": results})


@history_bp.route("/history", methods=["DELETE"])
def clear_history():
    """Delete all runs for this session."""
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_history_mutation_capability(owner_scope)
    if capability_response is not None:
        return capability_response
    deleted_count = clear_history_runs(
        owner_scope=owner_scope,
        audit_fields=route_audit_fields(session_id, request, owner_scope),
    )
    log.info("HISTORY_CLEARED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id), "count": deleted_count,
    })
    return jsonify({"ok": True})


@history_bp.route("/share", methods=["POST"])
def save_share():
    """Save a tab snapshot (all output from a tab) for sharing via permalink."""
    # Snapshot permalinks capture the currently visible tab transcript rather than
    # requiring a completed run ID, so the client POSTs normalized line objects.
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    label   = data.get("label", "untitled")
    content = data.get("content", [])  # list of {text, cls} objects
    apply_redaction = data.get("apply_redaction", True)
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = _require_team_capability(owner_scope, Capability.MANAGE_HISTORY)
    if capability_response:
        return capability_response
    if not isinstance(label, str):
        return jsonify({"error": "Label must be a string"}), 400
    if not isinstance(content, list):
        return jsonify({"error": "Content must be a list"}), 400
    if not isinstance(apply_redaction, bool):
        return jsonify({"error": "apply_redaction must be a boolean"}), 400
    for item in content:
        if isinstance(item, str):
            continue
        if not isinstance(item, dict):
            return jsonify({"error": "Content items must be strings or objects"}), 400
        if not isinstance(item.get("text"), str):
            return jsonify({"error": "Content objects must include a string text field"}), 400
        if "cls" in item and not isinstance(item["cls"], str):
            return jsonify({"error": "Content objects must use string cls values"}), 400
    label = label.strip()
    content_events = omit_raw_only_line_entries(content)
    if CFG.get("share_redaction_enabled") and apply_redaction:
        content_events = redact_line_entries(content_events, _config.get_share_redaction_rules(CFG))
    content = line_entries_from_events(content_events, compact=True, preserve_plain_strings=True)
    share_id = str(uuid.uuid4())
    created  = datetime.now(timezone.utc).isoformat()
    content_json = json.dumps(content)
    stored_content = maybe_store_text_body(
        "snapshot",
        share_id,
        content_json,
        inline_threshold_bytes(CFG.get("snapshots_inline_max_bytes")),
    )
    save_snapshot(
        session_id=session_id,
        team_id=owner_scope.team_id,
        share_id=share_id,
        label=label,
        created=created,
        stored_content=stored_content,
        audit_fields=route_audit_fields(session_id, request, owner_scope),
        audit_details={
            "snapshot_id": share_id,
            "safe_label": label,
            "redaction_mode": "configured" if apply_redaction else "none",
            "source": "share",
            "run_id": str(data.get("run_id") or ""),
        },
        redaction_audit=bool(CFG.get("share_redaction_enabled") and apply_redaction),
    )
    log.info("SHARE_CREATED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id), "share_id": share_id,
        "label": label, "redacted": apply_redaction,
        "run_id": str(data.get("run_id") or ""),
        "included_artifacts": len(data.get("artifacts") or []) if isinstance(data.get("artifacts"), list) else 0,
        "redaction_mode": "configured" if apply_redaction else "none",
    })
    app_metrics.record_snapshot_created("manual")
    return jsonify({"id": share_id, "url": f"/share/{share_id}"})


@history_bp.route("/share/bulk-delete", methods=["POST"])
def bulk_delete_shares():
    """Delete selected snapshots for this session."""
    session_id = get_session_id()
    snapshot_ids, error_response = _normalize_bulk_snapshot_ids_payload(request.get_json(silent=True) or {})
    if error_response is not None:
        return error_response
    assert snapshot_ids is not None
    counts, results = bulk_delete_snapshots(
        session_id=session_id,
        snapshot_ids=snapshot_ids,
        result_factory=_bulk_delete_result,
        audit_fields=route_audit_fields(session_id, request),
    )
    log.info("SHARES_BULK_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": counts["deleted"],
        "counts": counts,
        "failures": _bulk_delete_failures(results, key="snapshot_id"),
    })
    return jsonify({"ok": True, "counts": counts, "results": results})


@history_bp.route("/share/<share_id>")
def get_share(share_id):
    """Serve a styled HTML permalink page for a full tab snapshot."""
    snap = snapshot_row(share_id)
    if not snap:
        log.warning("SHARE_NOT_FOUND", extra={"ip": get_client_ip(), "share_id": share_id})
        return _permalink_error_page("snapshot")
    try:
        content_lines = json.loads(load_text_body(snap["content"]) or "[]")
    except (TypeError, json.JSONDecodeError, ValueError):
        content_lines = []
    log.info("SHARE_VIEWED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(), "share_id": share_id,
        "label": snap["label"],
    })
    app_metrics.record_snapshot_view(bool(snap.get("redacted", False)))

    if "json" in request.args:
        snap["content"] = content_lines
        return jsonify(snap)

    meta = {
        "exit_code": None,
        "duration": None,
        "lines": f"{len(content_lines):,} lines",
        "version": APP_VERSION,
    }

    return _permalink_page(
        title=snap["label"],
        label=snap["label"],
        created=snap["created"],
        content_lines=content_lines,
        json_url=f"/share/{share_id}?json",
        meta=meta,
        command=snap["label"],
    )


@history_bp.route("/share/<share_id>", methods=["DELETE"])
def delete_share(share_id):
    """Delete a snapshot owned by the current session."""
    session_id = get_session_id()
    deleted_count = delete_snapshot(
        session_id=session_id,
        share_id=share_id,
        audit_fields=route_audit_fields(session_id, request),
    )
    log.info("SHARE_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "share_id": share_id,
        "deleted": deleted_count > 0,
    })
    return jsonify({"ok": True})
