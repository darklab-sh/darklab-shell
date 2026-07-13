"""API-facing history and run query helpers owned by the history service."""

from __future__ import annotations

import logging
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.helpers import get_log_session_id
from core.process import active_runs_for_session, active_runs_for_team
from services.history.run_metadata import (
    history_offloaded_search_run_ids,
    run_atlas_counts_by_run,
    run_file_artifacts_by_run,
    run_metadata_counts_by_run,
)
from services.history.search import run_search_clause
from services.projects.artifacts import artifact_availability, artifact_owner_context
from services.runs.output_model import LineEvent
from services.runs.output_store import load_run_output_events_for_run
from services.runs.structured_filters import (
    StructuredOutputFilters,
    entity_run_exists_clause,
    event_matches_structured_filters,
    filters_have_summary_selectors,
    filters_need_line_event_scan,
    run_output_summary_exists_clause,
)
from services.scheduler.models import OWNER_KIND_WATCHER
from services.scheduler.service import schedule_refs_by_run
from services.workflows.storage import apply_workflow_provenance, workflow_provenance_by_run

log = logging.getLogger("shell")


def run_owner_clause(session_id: str, team_id: str, *, alias: str = "r") -> tuple[str, list[Any]]:
    prefix = f"{alias}." if alias else ""
    if team_id:
        return f"{prefix}team_id = ?", [team_id]
    return f"{prefix}session_id = ? AND ({prefix}team_id IS NULL OR {prefix}team_id = '')", [session_id]


def project_owner_clause(session_id: str, team_id: str, *, alias: str = "p") -> tuple[str, list[Any]]:
    prefix = f"{alias}." if alias else ""
    if team_id:
        return f"{prefix}team_id = ?", [team_id]
    return f"{prefix}session_id = ? AND ({prefix}team_id IS NULL OR {prefix}team_id = '')", [session_id]


def apply_schedule_ref(run: dict[str, Any], schedule_ref: dict[str, str] | None) -> None:
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


def active_runs_for_owner(session_id: str, team_id: str = "", client_id: str = "") -> list[dict[str, Any]]:
    if team_id:
        return active_runs_for_team(team_id, client_id=client_id)
    return active_runs_for_session(session_id, client_id=client_id, team_id="")


def active_run_summary(active: dict[str, Any]) -> dict[str, Any]:
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


def run_status_from_active_or_row(run_id: str, session_id: str, team_id: str = "") -> dict[str, Any] | None:
    for active in active_runs_for_owner(session_id, team_id):
        if str(active.get("run_id") or "") == run_id:
            return active_run_summary(active)
    with get_db_connect()() as conn:
        scope_sql, scope_params = run_owner_clause(session_id, team_id, alias="")
        row = conn.execute(
            f"SELECT * FROM runs WHERE {scope_sql} AND id = ?",  # nosec
            (*scope_params, run_id),
        ).fetchone()
        if not row:
            return None
        run = dict(row)
        artifacts = run_file_artifacts_by_run(conn, [run_id]).get(run_id, [])
        run["artifact_count"] = len(artifacts)
        run.update(run_metadata_counts_by_run(conn, [run_id]).get(run_id, {}))
        run.update(run_atlas_counts_by_run(conn, session_id, [run_id], team_id=team_id).get(run_id, {}))
    return run


def history_where(
    session_id: str,
    team_id: str,
    filters: dict[str, str],
    *,
    offloaded_ids: list[str] | None = None,
    search_scope: str = "all",
) -> tuple[str, list[Any]]:
    scope_sql, scope_params = run_owner_clause(session_id, team_id)
    where = [scope_sql]
    params: list[Any] = list(scope_params)
    if filters["run_kind"]:
        where.append("r.run_kind = ?")
        params.append(filters["run_kind"])
    if filters["project_id"]:
        project_scope_sql, project_scope_params = project_owner_clause(session_id, team_id)
        where.append(
            "EXISTS (SELECT 1 FROM project_links pl JOIN projects p ON p.id = pl.project_id "  # nosec
            f"WHERE {project_scope_sql} AND p.id = ? AND pl.entity_type = 'run' AND pl.entity_id = r.id)"
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
        search = run_search_clause(get_db_backend(), filters["q"], search_scope, alias="r", postgres_placeholder="?")
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


def run_output_events(run: dict[str, Any], *, full: bool = True) -> list[LineEvent]:
    result = load_run_output_events_for_run(run, prefer_full=full, log_event="API_FULL_OUTPUT_LOAD_FAILED")
    run["_output_source"] = result.source
    run["_output_fallback"] = result.fallback
    return result.events


def history_search_candidate_runs(
    session_id: str,
    team_id: str,
    filters: dict[str, str],
    structured_filters: StructuredOutputFilters,
) -> list[dict[str, Any]]:
    offloaded_ids: list[str] = []
    if filters["q"]:
        with get_db_connect()() as conn:
            offloaded_ids = history_offloaded_search_run_ids(
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
    with get_db_connect()() as conn:
        where_sql, params = history_where(
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
    log.debug("API_HISTORY_DATA_ACCESS", extra={
        "session": get_log_session_id(session_id),
        "team_scope": bool(team_id),
        "branch": "candidate_runs",
        "has_query": bool(filters.get("q")),
        "offloaded_id_count": len(offloaded_ids),
        "structured_active": structured_filters.active,
        "line_scan": False,
        "candidate_count": len(rows),
        "result_count": len(rows),
    })
    return [dict(row) for row in rows]


def run_output_search_matches(
    run: dict[str, Any],
    query: str,
    context: int,
    structured_filters: StructuredOutputFilters,
) -> list[dict[str, Any]]:
    needle = query.casefold()
    events = run_output_events(run)
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


def history_output_search(
    session_id: str,
    team_id: str,
    filters: dict[str, str],
    query: str,
    context: int,
    structured_filters: StructuredOutputFilters,
) -> list[dict[str, Any]]:
    search_filters = dict(filters)
    search_filters["q"] = query
    matches: list[dict[str, Any]] = []
    for run in history_search_candidate_runs(session_id, team_id, search_filters, structured_filters):
        matches.extend(run_output_search_matches(run, query, context, structured_filters))
    return matches


def history_rows(
    session_id: str,
    team_id: str,
    limit: int,
    offset: int,
    filters: dict[str, str],
    structured_filters: StructuredOutputFilters | None = None,
) -> tuple[list[dict[str, Any]], int]:
    offloaded_ids: list[str] = []
    if filters["q"]:
        with get_db_connect()() as conn:
            offloaded_ids = history_offloaded_search_run_ids(
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
    with get_db_connect()() as conn:
        where_sql, params = history_where(session_id, team_id, filters, offloaded_ids=offloaded_ids)
        needs_line_scan = False
        candidate_count: int | None = None
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
                candidate_count = len(rows)
                matching_runs = [dict(row) for row in rows]
                matching_runs = [
                    run
                    for run in matching_runs
                    if any(event_matches_structured_filters(event, structured_filters) for event in run_output_events(run))
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
        artifacts = run_file_artifacts_by_run(conn, run_ids)
        metadata = run_metadata_counts_by_run(conn, run_ids)
        atlas = run_atlas_counts_by_run(conn, session_id, run_ids, team_id=team_id)
        scheduled = schedule_refs_by_run(conn, run_ids)
        workflow_provenance = workflow_provenance_by_run(conn, run_ids)
    for run in runs:
        run_id = str(run["id"])
        run["artifact_count"] = len(artifacts.get(run_id, []))
        run.update(metadata.get(run_id, {}))
        run.update(atlas.get(run_id, {}))
        apply_schedule_ref(run, scheduled.get(run_id))
        apply_workflow_provenance(run, workflow_provenance.get(run_id))
    log.debug("API_HISTORY_DATA_ACCESS", extra={
        "session": get_log_session_id(session_id),
        "team_scope": bool(team_id),
        "branch": "history_rows",
        "has_query": bool(filters.get("q")),
        "offloaded_id_count": len(offloaded_ids),
        "structured_active": bool(structured_filters and structured_filters.active),
        "line_scan": needs_line_scan,
        "candidate_count": candidate_count,
        "result_count": len(runs),
    })
    return runs, total


def load_run_detail(session_id: str, team_id: str, run_id: str) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        scope_sql, scope_params = run_owner_clause(session_id, team_id, alias="runs")
        row = conn.execute(
            "SELECT runs.*, art.rel_path "  # nosec
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            f"WHERE {scope_sql} AND runs.id = ?",
            (*scope_params, run_id),
        ).fetchone()
        if not row:
            return None
        run = dict(row)
        artifacts = run_file_artifacts_by_run(conn, [run_id]).get(run_id, [])
        run["artifacts"] = artifacts
        run["artifact_count"] = len(artifacts)
        run.update(run_metadata_counts_by_run(conn, [run_id]).get(run_id, {}))
        run.update(run_atlas_counts_by_run(conn, session_id, [run_id], team_id=team_id).get(run_id, {}))
        apply_schedule_ref(run, schedule_refs_by_run(conn, [run_id]).get(run_id))
        provenance = workflow_provenance_by_run(conn, [run_id], include_steps=True).get(run_id)
        apply_workflow_provenance(run, provenance)
    return run


def artifact_for_run(session_id: str, team_id: str, run_id: str, artifact_id: str) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        scope_sql, scope_params = run_owner_clause(session_id, team_id, alias="")
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


def artifacts_for_run(session_id: str, team_id: str, run_id: str) -> list[dict[str, Any]] | None:
    with get_db_connect()() as conn:
        scope_sql, scope_params = run_owner_clause(session_id, team_id, alias="")
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
        artifacts.append(artifact)
    return artifacts
