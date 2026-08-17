# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""History query helpers owned by the service layer."""

from __future__ import annotations

import logging
import math
import time
from hashlib import sha256
from dataclasses import dataclass
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, SQLiteOperationalError, dialect_for_backend
from core.helpers import GRACEFUL_TERMINATION_EXIT_CODE, get_log_session_id
from core.output_signals import command_root as output_command_root
from core.process import active_runs_for_session
from services.assessments.batch.provenance import (
    apply_assessment_batch_provenance,
    assessment_batch_provenance_by_run,
)
from services.metrics_lazy import app_metrics
from services.history.run_metadata import (
    history_add_filters,
    history_column_exists,
    history_cutoff_for_range,
    history_offloaded_search_run_ids,
    history_run_kind_sql,
    history_table_exists,
    run_atlas_counts_by_run,
    run_file_artifacts_by_run,
    run_finding_counts_by_run,
)
from services.history.search import run_search_clause, sqlite_fts_query
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL
from services.runs.output_store import load_run_output_events_for_run
from services.runs.structured_filters import (
    entity_run_exists_clause,
    filters_have_summary_selectors,
    filters_need_line_event_scan,
    run_output_summary_exists_clause,
    run_matches_structured_filters,
)
from services.scheduler.models import OWNER_KIND_WATCHER
from services.scheduler.service import schedule_refs_by_run
from services.workflows.storage import apply_workflow_provenance, workflow_provenance_by_run
from services.history.insights import history_insights as history_insights
from services.history import mutations as _history_mutations

log = logging.getLogger("shell")


@dataclass(frozen=True)
class HistoryListResult:
    items: list[dict[str, Any]]
    runs: list[dict[str, Any]]
    roots: list[str]
    total_count: int | None
    page_count: int
    current_page: int
    fts_query: str | None


def delete_history_run(**kwargs):
    return _history_mutations.delete_history_run(**kwargs)


def history_run_cleanup_preview(session_id: str, run_id: str, owner_scope=None):
    return _history_mutations.history_run_cleanup_preview(session_id, run_id, owner_scope=owner_scope)


def bulk_export_rows(owner_scope, run_ids: list[str], snapshot_ids: list[str]):
    return _history_mutations.bulk_export_rows(owner_scope, run_ids, snapshot_ids)


def bulk_delete_runs(**kwargs):
    return _history_mutations.bulk_delete_runs(**kwargs)


def clear_history_runs(**kwargs):
    return _history_mutations.clear_history_runs(**kwargs)


def save_snapshot(**kwargs):
    return _history_mutations.save_snapshot(**kwargs)


def bulk_delete_snapshots(**kwargs):
    return _history_mutations.bulk_delete_snapshots(**kwargs)


def snapshot_row(share_id: str):
    return _history_mutations.snapshot_row(share_id)


def delete_snapshot(**kwargs):
    return _history_mutations.delete_snapshot(**kwargs)


def build_fts_query(raw: str) -> str | None:
    return sqlite_fts_query(raw)


def history_run_root(command: str) -> str:
    return output_command_root(command) or str(command or "").strip().split(maxsplit=1)[0].lower() or "unknown"


def history_root_rows_from_command_rows(rows) -> list[dict[str, str]]:
    latest_by_root: dict[str, str] = {}
    for row in rows:
        root = history_run_root(str(row["command"] or ""))
        if not root:
            continue
        latest_started = str(row["latest_started"] or "")
        if root not in latest_by_root or latest_started > latest_by_root[root]:
            latest_by_root[root] = latest_started
    return [
        {"root": root, "latest_started": latest_started}
        for root, latest_started in sorted(
            latest_by_root.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:50]
    ]


def history_match_clause(query: str, scope: str, *, force_like: bool = False):
    clause = run_search_clause(
        get_db_backend(),
        query,
        scope,
        alias="r",
        prefer_sqlite_fts=get_db_backend() != DatabaseBackend.POSTGRES and not force_like,
        postgres_placeholder="?",
    )
    return clause.sql, clause.params, clause.fts_query


def history_base_clause(
    session_id: str,
    owner_scope,
    query: str,
    command_root: str,
    exit_code_filter: str,
    date_range: str,
    scope: str,
    project_id: str,
    *,
    starred_only: bool = False,
    run_kind: str = "all",
    has_run_kind_column: bool = True,
    force_like: bool = False,
    offloaded_match_run_ids=None,
):
    scope_sql, scope_params = owner_scope.predicate(table_alias="r")
    sql = f" FROM runs r WHERE {scope_sql}"
    params: list[Any] = list(scope_params)
    if run_kind in {RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL}:
        run_kind_expr = "r.run_kind" if has_run_kind_column else history_run_kind_sql("r.command", get_db_backend())
        sql += f" AND {run_kind_expr} = ?"
        params.append(run_kind)
    if project_id:
        sql += (
            " AND EXISTS (SELECT 1 FROM project_links pl "
            "JOIN projects p ON p.id = pl.project_id "
            "WHERE p.session_id = ? AND p.id = ? "
            "AND pl.entity_type = 'run' AND pl.entity_id = r.id) "
        )
        params.extend([session_id, project_id])
    if starred_only:
        sql += (
            " AND EXISTS (SELECT 1 FROM starred_commands sc "
            "WHERE sc.session_id = r.session_id AND sc.command = r.command)"
        )
    match_sql, match_params, fts_q = history_match_clause(query, scope, force_like=force_like)
    offloaded_ids = [str(run_id) for run_id in (offloaded_match_run_ids or [])]
    if match_sql and offloaded_ids:
        match_predicate = match_sql[5:] if match_sql.startswith(" AND ") else match_sql
        placeholders = ", ".join("?" for _ in offloaded_ids)
        sql += f" AND (({match_predicate}) OR r.id IN ({placeholders}))"
        params.extend(match_params)
        params.extend(offloaded_ids)
    else:
        sql += match_sql
        params.extend(match_params)
    sql, params = history_add_filters(sql, params, command_root, exit_code_filter, date_range)
    return sql, params, fts_q


def history_structured_filter_run_ids(
    conn,
    run_sql,
    run_params,
    structured_filters,
    *,
    session_id: str = "",
    team_id: str = "",
):
    summary_sql, _summary_params = run_output_summary_exists_clause(structured_filters, run_alias="r")
    summary_available = bool(summary_sql) and history_table_exists(conn, "run_output_summary")
    needs_summary_fallback = filters_have_summary_selectors(structured_filters) and not summary_available
    if not filters_need_line_event_scan(structured_filters) and not needs_summary_fallback:
        return None
    rows = conn.execute(
        "SELECT r.*, ("  # nosec
        "SELECT art.rel_path FROM run_output_artifacts art "
        "WHERE art.run_id = r.id ORDER BY art.created DESC LIMIT 1"
        ") AS rel_path "
        + run_sql
        + " ORDER BY r.started DESC, r.id DESC LIMIT 2000",
        run_params,
    ).fetchall()
    run_ids: list[str] = []
    for row in rows:
        run = dict(row)
        result = load_run_output_events_for_run(
            run,
            log_event="HISTORY_STRUCTURED_OUTPUT_LOAD_FAILED",
        )
        if run_matches_structured_filters(result.events, structured_filters):
            run_ids.append(str(run.get("id") or ""))
    log.debug("HISTORY_STRUCTURED_FILTER_SCAN", extra={
        "session": get_log_session_id(session_id),
        "team_scope": bool(team_id),
        "candidate_count": len(rows),
        "matched_count": len(run_ids),
        "summary_available": summary_available,
        "needs_summary_fallback": needs_summary_fallback,
    })
    return run_ids


def history_run_filter_clause(
    *,
    conn,
    session_id: str,
    owner_scope,
    query: str,
    structured_filters,
    command_root: str,
    exit_code_filter: str,
    date_range: str,
    project_id: str,
    starred_only: bool,
    run_kind: str,
    scope: str,
    has_run_kind_column: bool,
    force_like: bool = False,
) -> tuple[str, list[Any], str | None]:
    offloaded_match_run_ids = []
    if query and scope != "command":
        offloaded_match_run_ids = history_offloaded_search_run_ids(
            conn,
            session_id,
            owner_scope.team_id,
            query,
            command_root,
            exit_code_filter,
            date_range,
            project_id,
            starred_only=starred_only,
            run_kind=run_kind,
            has_run_kind_column=has_run_kind_column,
        )
    run_sql, run_params, fts_q = history_base_clause(
        session_id,
        owner_scope,
        query,
        command_root,
        exit_code_filter,
        date_range,
        scope,
        project_id,
        starred_only=starred_only,
        run_kind=run_kind,
        has_run_kind_column=has_run_kind_column,
        force_like=force_like,
        offloaded_match_run_ids=offloaded_match_run_ids,
    )
    if structured_filters.active:
        entity_sql, entity_params = entity_run_exists_clause(structured_filters, run_alias="r")
        if entity_sql:
            run_sql += entity_sql
            run_params = [*run_params, *entity_params]
        summary_sql, summary_params = run_output_summary_exists_clause(structured_filters, run_alias="r")
        if summary_sql and history_table_exists(conn, "run_output_summary"):
            run_sql += summary_sql
            run_params = [*run_params, *summary_params]
        structured_ids = history_structured_filter_run_ids(
            conn,
            run_sql,
            run_params,
            structured_filters,
            session_id=session_id,
            team_id=str(getattr(owner_scope, "team_id", "") or ""),
        )
        if structured_ids is not None:
            if structured_ids:
                placeholders = ", ".join("?" for _ in structured_ids)
                run_sql += f" AND r.id IN ({placeholders})"
                run_params = [*run_params, *structured_ids]
            else:
                run_sql += " AND 1 = 0"
    return run_sql, run_params, fts_q


def history_snapshot_base_clause(owner_scope, query: str, date_range: str, project_id: str = ""):
    scope_sql, scope_params = owner_scope.predicate(table_alias="s")
    sql = f" FROM snapshots s WHERE {scope_sql}"
    params: list[Any] = list(scope_params)
    if project_id:
        sql += " AND 1 = 0"
    if query:
        if get_db_backend() == DatabaseBackend.POSTGRES:
            sql += " AND s.label ILIKE ?"
            params.append(f"%{query}%")
        else:
            sql += " AND LOWER(s.label) LIKE ?"
            params.append(f"%{query.lower()}%")
    cutoff = history_cutoff_for_range(date_range)
    if cutoff:
        sql += " AND s.created >= ?"
        params.append(cutoff)
    return sql, params


def entity_labels_by_entity_ids(conn, entity_type: str, entity_ids) -> dict[str, list[dict[str, object]]]:
    ids = [str(entity_id) for entity_id in entity_ids if entity_id]
    if not ids:
        return {}
    if not history_table_exists(conn, "entity_labels"):
        return {entity_id: [] for entity_id in ids}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT id, session_id, entity_type, entity_id, label, source, created FROM entity_labels "  # nosec
        "WHERE entity_type = ? "
        f"AND entity_id IN ({placeholders}) "
        "ORDER BY " + dialect_for_backend(get_db_backend()).case_insensitive_order("label") + ", created ASC",
        [entity_type, *ids],
    ).fetchall()
    grouped = {entity_id: [] for entity_id in ids}
    for row in rows:
        grouped.setdefault(str(row["entity_id"]), []).append({
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "label": row["label"],
            "source": row["source"],
            "created": row["created"],
        })
    return grouped


def entity_notes_by_entity_ids(conn, entity_type: str, entity_ids) -> dict[str, list[dict[str, object]]]:
    ids = [str(entity_id) for entity_id in entity_ids if entity_id]
    if not ids:
        return {}
    if not history_table_exists(conn, "entity_notes"):
        return {entity_id: [] for entity_id in ids}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT id, session_id, entity_type, entity_id, body, created, updated FROM entity_notes "  # nosec
        "WHERE entity_type = ? "
        f"AND entity_id IN ({placeholders}) "
        "ORDER BY updated ASC, id ASC",
        [entity_type, *ids],
    ).fetchall()
    grouped = {entity_id: [] for entity_id in ids}
    for row in rows:
        grouped.setdefault(str(row["entity_id"]), []).append({
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "body": row["body"],
            "created": row["created"],
            "updated": row["updated"],
        })
    return grouped


def project_links_by_run(conn, session_id: str, run_ids) -> dict[str, list[dict[str, object]]]:
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return {}
    if not (
        history_table_exists(conn, "project_links")
        and history_table_exists(conn, "projects")
    ):
        return {run_id: [] for run_id in ids}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT l.id, l.project_id, l.entity_id AS run_id, l.source, l.created, "  # nosec
        "p.name AS project_name, p.slug AS project_slug, p.status AS project_status "
        "FROM project_links l "
        "JOIN projects p ON p.id = l.project_id "
        "JOIN runs r ON r.id = l.entity_id "
        "WHERE p.session_id = ? "
        "AND l.entity_type = 'run' "
        "AND r.session_id = ? AND r.run_kind = ? "
        f"AND l.entity_id IN ({placeholders}) "
        "ORDER BY LOWER(p.name) ASC, l.created ASC",
        [session_id, session_id, RUN_KIND_EXTERNAL, *ids],
    ).fetchall()
    grouped = {run_id: [] for run_id in ids}
    for row in rows:
        grouped.setdefault(str(row["run_id"]), []).append({
            "id": row["id"],
            "project_id": row["project_id"],
            "entity_type": "run",
            "entity_id": row["run_id"],
            "source": row["source"],
            "created": row["created"],
            "project": {
                "id": row["project_id"],
                "name": row["project_name"],
                "slug": row["project_slug"],
                "status": row["project_status"],
            },
        })
    return grouped


def run_findings_by_run(conn, run_ids) -> dict[str, list[dict[str, object]]]:
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT f.id, f.session_id, fo.run_id, COALESCE(f.entity_id, f.target_id) AS target_id, f.kind AS scope, "  # nosec
        "f.title, COALESCE(fo.snippet, f.raw_line) AS raw_line, fo.line_number, "
        "f.severity, f.fingerprint, f.status AS review_state, f.created "
        "FROM findings_occurrences fo JOIN findings f ON f.id = fo.finding_id "
        f"WHERE fo.run_id IN ({placeholders}) "
        "ORDER BY fo.line_number ASC, f.created ASC, f.id ASC",
        ids,
    ).fetchall()
    grouped = {run_id: [] for run_id in ids}
    for row in rows:
        primary_target_id = str(row["target_id"] or "")
        target_ids = [primary_target_id] if primary_target_id else []
        grouped.setdefault(str(row["run_id"]), []).append({
            "id": row["id"],
            "run_id": row["run_id"],
            "target_id": primary_target_id,
            "target_ids": target_ids,
            "scope": row["scope"],
            "title": row["title"],
            "raw_line": row["raw_line"],
            "line_number": int(row["line_number"] or 0),
            "severity": row["severity"] or "",
            "fingerprint": row["fingerprint"],
            "review_state": row["review_state"],
            "created": row["created"],
        })
    return grouped


def run_labels_by_run(conn, run_ids):
    return entity_labels_by_entity_ids(conn, "run", run_ids)


def run_notes_by_run(conn, run_ids):
    return entity_notes_by_entity_ids(conn, "run", run_ids)


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


def list_history_items(
    *,
    session_id: str,
    owner_scope,
    query: str,
    structured_filters,
    command_root: str,
    exit_code_filter: str,
    date_range: str,
    type_filter: str,
    project_id: str,
    starred_only: bool,
    include_total: bool,
    page: int,
    page_size: int,
    scope: str,
) -> HistoryListResult:
    run_kind = {
        "runs_builtin": "builtin",
        "runs_external": "external",
    }.get(type_filter, "all")

    def _query_history(conn, *, force_like=False):
        roots_rows = []
        fts_q = None
        run_sql = ""
        run_params: list[Any] = []
        has_run_kind_column = history_column_exists(conn, "runs", "run_kind")
        snapshots_available = history_table_exists(conn, "snapshots")
        if type_filter in {"all", "runs", "runs_builtin", "runs_external"}:
            run_sql, run_params, fts_q = history_run_filter_clause(
                conn=conn,
                session_id=session_id,
                owner_scope=owner_scope,
                query=query,
                structured_filters=structured_filters,
                command_root=command_root,
                exit_code_filter=exit_code_filter,
                date_range=date_range,
                project_id=project_id,
                starred_only=starred_only,
                run_kind=run_kind,
                scope=scope,
                has_run_kind_column=has_run_kind_column,
                force_like=force_like,
            )
            root_command_rows = conn.execute(
                "SELECT r.command, MAX(r.started) AS latest_started"
                + run_sql
                + " GROUP BY r.command "
                + " ORDER BY latest_started DESC "
                + " LIMIT 1000",
                run_params,
            ).fetchall()
            roots_rows = history_root_rows_from_command_rows(root_command_rows)

        snap_sql = ""
        snap_params: list[Any] = []
        snapshot_filters_active = bool(
            command_root
            or exit_code_filter not in {"", "all"}
            or starred_only
            or scope == "command"
            or structured_filters.active
        )
        if (
            snapshots_available
            and type_filter in {"all", "snapshots"}
            and not snapshot_filters_active
        ):
            snap_sql, snap_params = history_snapshot_base_clause(owner_scope, query, date_range, project_id)

        total_count = None
        if include_total:
            total_count = 0
            if run_sql:
                total_count += int(conn.execute("SELECT COUNT(*) AS count" + run_sql, run_params).fetchone()["count"])
            if snap_sql:
                total_count += int(conn.execute("SELECT COUNT(*) AS count" + snap_sql, snap_params).fetchone()["count"])
        page_count = math.ceil(total_count / page_size) if include_total and total_count else 0
        current_page = max(page, 1)
        if include_total:
            current_page = min(current_page, page_count or 1)
        offset = (current_page - 1) * page_size

        run_select = (
            "SELECT 'run' AS type, r.id, "
            + ("r.run_kind" if has_run_kind_column else history_run_kind_sql("r.command", get_db_backend()))
            + " AS run_kind, r.command, r.started, r.finished, r.exit_code, "
            "r.preview_truncated, r.output_line_count, r.full_output_available, r.full_output_truncated, "
            "r.command AS label, r.started AS created, r.started AS sort_created"
            + run_sql
        ) if run_sql else ""
        snap_select = (
            "SELECT 'snapshot' AS type, s.id, NULL AS run_kind, NULL AS command, NULL AS started, "
            "NULL AS finished, NULL AS exit_code, "
            "NULL AS preview_truncated, NULL AS output_line_count, NULL AS full_output_available, "
            "NULL AS full_output_truncated, s.label AS label, s.created AS created, s.created AS sort_created"
            + snap_sql
        ) if snap_sql else ""
        item_sql_parts = [part for part in (run_select, snap_select) if part]
        if item_sql_parts:
            item_sql = " UNION ALL ".join(item_sql_parts) + " ORDER BY sort_created DESC LIMIT ? OFFSET ?"
            item_params = []
            if run_select:
                item_params.extend(run_params)
            if snap_select:
                item_params.extend(snap_params)
            item_params.extend([page_size, offset])
            rows = conn.execute(item_sql, item_params).fetchall()
        else:
            rows = []

        paged_items = []
        for row in rows:
            item = dict(row)
            item["_sort_created"] = item.pop("sort_created", None)
            if item.get("type") == "run":
                item["preview_truncated"] = bool(item.get("preview_truncated"))
                item["full_output_available"] = bool(item.get("full_output_available"))
                item["full_output_truncated"] = bool(item.get("full_output_truncated"))
            paged_items.append(item)
        paged_runs = [item for item in paged_items if item.get("type") == "run"]
        paged_snapshots = [item for item in paged_items if item.get("type") == "snapshot"]
        run_ids = [item["id"] for item in paged_runs]
        snapshot_ids = [item["id"] for item in paged_snapshots]
        artifacts_by_run = run_file_artifacts_by_run(conn, run_ids)
        projects_by_run = project_links_by_run(conn, session_id, run_ids)
        finding_counts_by_run = run_finding_counts_by_run(conn, run_ids)
        atlas_counts = run_atlas_counts_by_run(
            conn,
            session_id,
            run_ids,
            team_id=owner_scope.team_id,
        )
        scheduled_by_run = schedule_refs_by_run(conn, run_ids)
        labels_by_run = entity_labels_by_entity_ids(conn, "run", run_ids)
        notes_by_run = entity_notes_by_entity_ids(conn, "run", run_ids)
        workflow_provenance = workflow_provenance_by_run(
            conn,
            run_ids,
            owner_scope=owner_scope,
        )
        batch_provenance = assessment_batch_provenance_by_run(
            conn,
            run_ids,
            owner_scope=owner_scope,
        )
        labels_by_snapshot = entity_labels_by_entity_ids(conn, "snapshot", snapshot_ids)
        notes_by_snapshot = entity_notes_by_entity_ids(conn, "snapshot", snapshot_ids)
        for item in paged_runs:
            item["artifacts"] = artifacts_by_run.get(str(item["id"]), [])
            item["artifact_count"] = len(item["artifacts"])
            item["project_links"] = projects_by_run.get(str(item["id"]), [])
            item["project_link_count"] = len(item["project_links"])
            item["labels"] = labels_by_run.get(str(item["id"]), [])
            item["note"] = (notes_by_run.get(str(item["id"]), []) or [None])[0]
            run_id = str(item["id"])
            item["finding_count"] = finding_counts_by_run.get(run_id, 0)
            item["label_count"] = len(item["labels"])
            item["note_count"] = len(notes_by_run.get(run_id, []))
            item.update(atlas_counts.get(str(item["id"]), {
                "atlas_entity_count": 0,
                "atlas_finding_count": 0,
            }))
            _apply_schedule_ref(item, scheduled_by_run.get(str(item["id"])))
            apply_workflow_provenance(item, workflow_provenance.get(str(item["id"])))
            apply_assessment_batch_provenance(
                item,
                batch_provenance.get(str(item["id"])),
            )
        for item in paged_snapshots:
            item["labels"] = labels_by_snapshot.get(str(item["id"]), [])
            item["note"] = (notes_by_snapshot.get(str(item["id"]), []) or [None])[0]
            item["label_count"] = len(item["labels"])
            item["note_count"] = 1 if item["note"] else 0
        return paged_items, paged_runs, roots_rows, total_count, page_count, current_page, fts_q

    with get_db_connect()() as conn:
        try:
            query_started = time.perf_counter()
            items, runs, roots_rows, total_count, page_count, current_page, fts_q = _query_history(conn)
            app_metrics.record_db_query(
                "history_list_fts" if fts_q else "history_list",
                time.perf_counter() - query_started,
            )
        except SQLiteOperationalError as exc:
            if query and build_fts_query(query):
                app_metrics.record_history_search_fallback(
                    "missing_fts" if "runs_fts" in str(exc).lower() else "fts_error"
                )
                reason = "missing_fts" if "runs_fts" in str(exc).lower() else "fts_error"
                log.warning("FTS_SEARCH_FALLBACK", extra={
                    "session": get_log_session_id(session_id),
                    "query_len": len(query),
                    "query_hash": sha256(query.encode("utf-8")).hexdigest()[:16],
                    "reason": reason,
                    "error_type": type(exc).__name__,
                })
                query_started = time.perf_counter()
                items, runs, roots_rows, total_count, page_count, current_page, fts_q = _query_history(
                    conn,
                    force_like=True,
                )
                app_metrics.record_db_query("history_list_like_fallback", time.perf_counter() - query_started)
            else:
                raise
    for item in items:
        item.pop("_sort_created", None)
    return HistoryListResult(
        items=items,
        runs=runs,
        roots=[str(row["root"]) for row in roots_rows if row["root"]],
        total_count=total_count,
        page_count=page_count,
        current_page=current_page,
        fts_query=fts_q,
    )


def recent_history_commands(owner_scope, *, limit: int) -> list[dict[str, str]]:
    scope_sql, scope_params = owner_scope.predicate()
    recent_commands_sql = (
        "SELECT command, MAX(started) AS latest_started "  # nosec
        "FROM runs "
        "WHERE "
        + scope_sql
        + " GROUP BY command ORDER BY latest_started DESC LIMIT ?"
    )
    with get_db_connect()() as conn:
        rows = conn.execute(recent_commands_sql, (*scope_params, limit)).fetchall()
    return [
        {"command": str(row["command"]), "started": row["latest_started"]}
        for row in rows
        if row["command"]
    ]


def session_history_stats(session_id: str, owner_scope) -> dict[str, Any]:
    with get_db_connect()() as conn:
        scope_sql, scope_params = owner_scope.predicate()
        if get_db_backend() == DatabaseBackend.POSTGRES:
            run_stats_prefix = """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN exit_code = 0 THEN 1 ELSE 0 END) AS succeeded,
                       SUM(
                           CASE
                               WHEN exit_code IS NOT NULL AND exit_code != 0 AND exit_code != ?
                               THEN 1
                               ELSE 0
                           END
                       ) AS failed,
                       SUM(CASE WHEN exit_code IS NULL THEN 1 ELSE 0 END) AS incomplete,
                       AVG(
                           CASE
                               WHEN NULLIF(started, '') IS NOT NULL AND NULLIF(finished, '') IS NOT NULL
                               THEN EXTRACT(
                                   EPOCH FROM (
                                       NULLIF(finished, '')::timestamptz - NULLIF(started, '')::timestamptz
                                   )
                               )
                               ELSE NULL
                           END
                       ) AS average_elapsed_seconds
                  FROM runs
                 WHERE """
        else:
            run_stats_prefix = """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN exit_code = 0 THEN 1 ELSE 0 END) AS succeeded,
                       SUM(
                           CASE
                               WHEN exit_code IS NOT NULL AND exit_code != 0 AND exit_code != ?
                               THEN 1
                               ELSE 0
                           END
                       ) AS failed,
                       SUM(CASE WHEN exit_code IS NULL THEN 1 ELSE 0 END) AS incomplete,
                       AVG(
                           CASE
                               WHEN NULLIF(started, '') IS NOT NULL AND NULLIF(finished, '') IS NOT NULL
                               THEN (julianday(finished) - julianday(started)) * 86400.0
                               ELSE NULL
                           END
                       ) AS average_elapsed_seconds
                  FROM runs
                 WHERE """
        run_row = conn.execute(
            run_stats_prefix + scope_sql,
            (GRACEFUL_TERMINATION_EXIT_CODE, *scope_params),
        ).fetchone()
        snapshots = 0
        if history_table_exists(conn, "snapshots"):
            snapshot_scope_sql, snapshot_scope_params = owner_scope.predicate()
            snapshots = int(conn.execute(
                "SELECT COUNT(*) AS count FROM snapshots WHERE " + snapshot_scope_sql,  # nosec
                snapshot_scope_params,
            ).fetchone()["count"] or 0)
        starred = 0
        if history_table_exists(conn, "starred_commands"):
            starred = int(conn.execute(
                "SELECT COUNT(*) AS count FROM starred_commands WHERE session_id = ?",
                (session_id,),
            ).fetchone()["count"] or 0)
    return {
        "runs": {
            "total": int(run_row["total"] or 0),
            "succeeded": int(run_row["succeeded"] or 0),
            "failed": int(run_row["failed"] or 0),
            "incomplete": int(run_row["incomplete"] or 0),
            "average_elapsed_seconds": (
                float(run_row["average_elapsed_seconds"])
                if run_row["average_elapsed_seconds"] is not None
                else None
            ),
        },
        "snapshots": snapshots,
        "starred_commands": starred,
        "active_runs": len(active_runs_for_session(session_id, team_id=owner_scope.team_id)),
    }


def schedule_refs_for_active_runs(run_ids) -> dict[str, dict[str, str]]:
    with get_db_connect()() as conn:
        return schedule_refs_by_run(conn, [str(run_id) for run_id in run_ids if str(run_id or "")])


def history_run_row(run_id: str):
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.id = ?",
            (run_id,),
        ).fetchone()
        run = dict(row) if row else None
        if run:
            provenance = workflow_provenance_by_run(conn, [run_id], include_steps=True).get(run_id)
            apply_workflow_provenance(run, provenance)
            batch_provenance = assessment_batch_provenance_by_run(conn, [run_id]).get(run_id)
            apply_assessment_batch_provenance(run, batch_provenance)
    return run


def history_run_private_metadata(run_id: str, session_id: str, run_team_id: str, *, include_private_metadata: bool):
    with get_db_connect()() as conn:
        artifacts_by_run = run_file_artifacts_by_run(conn, [run_id])
        finding_counts_by_run = run_finding_counts_by_run(conn, [run_id]) if include_private_metadata else {}
        atlas_counts = (
            run_atlas_counts_by_run(conn, session_id, [run_id], team_id=run_team_id)
            if include_private_metadata else {}
        )
        findings_by_run = run_findings_by_run(conn, [run_id]) if include_private_metadata else {}
        labels_by_run = run_labels_by_run(conn, [run_id]) if include_private_metadata else {}
        notes_by_run = run_notes_by_run(conn, [run_id]) if include_private_metadata else {}
        scheduled_by_run = schedule_refs_by_run(conn, [run_id]) if include_private_metadata else {}
    return {
        "artifacts_by_run": artifacts_by_run,
        "finding_counts_by_run": finding_counts_by_run,
        "atlas_counts": atlas_counts,
        "findings_by_run": findings_by_run,
        "labels_by_run": labels_by_run,
        "notes_by_run": notes_by_run,
        "scheduled_by_run": scheduled_by_run,
    }
