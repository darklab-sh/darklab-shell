"""Project list count and finding-summary query helpers."""

from __future__ import annotations

import logging
from collections import defaultdict

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.projects.metadata import _metadata_owner_where
from services.projects.owner_clauses import project_entity_owner_clause, project_finding_owner_clause
from services.projects.scope import shared_owner_where
from services.query_debug import log_project_list_metrics_debug, query_debug_started
from services.runs.kinds import RUN_KIND_EXTERNAL

log = logging.getLogger("shell")


def empty_project_counts():
    return {
        "runs": 0,
        "entities": 0,
        "targets": 0,
        "pending_targets": 0,
        "artifacts": 0,
        "findings": 0,
        "labels": 0,
        "notes": 0,
        "packages": 0,
    }


def empty_project_finding_summary():
    return {"review_states": {}, "severities": {}}


def add_finding_summary_count(summary, *, review_state, severity, count):
    safe_count = int(count or 0)
    if safe_count <= 0:
        return
    state = str(review_state or "new").strip().lower() or "new"
    severity_name = str(severity or "info").strip().lower() or "info"
    summary["review_states"][state] = int(summary["review_states"].get(state, 0)) + safe_count
    summary["severities"][severity_name] = int(summary["severities"].get(severity_name, 0)) + safe_count


def _chunks(values, size=500):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _join_sql(*parts):
    return "".join(parts)


def _empty_project_sets(ids):
    return {project_id: set() for project_id in ids}


def _record_project_finding(
    counts,
    finding_summaries,
    seen_findings,
    project_id,
    finding_id,
    *,
    review_state,
    severity,
):
    if project_id not in counts or not finding_id or finding_id in seen_findings[project_id]:
        return
    seen_findings[project_id].add(finding_id)
    counts[project_id]["findings"] += 1
    add_finding_summary_count(
        finding_summaries[project_id],
        review_state=review_state,
        severity=severity,
        count=1,
    )


def project_list_metrics(conn, session_id, project_ids, *, team_id=""):
    debug_started_at = query_debug_started(log)
    ids = [str(project_id) for project_id in project_ids if project_id]
    counts = {project_id: empty_project_counts() for project_id in ids}
    finding_summaries = {project_id: empty_project_finding_summary() for project_id in ids}
    if not ids:
        log_project_list_metrics_debug(log, debug_started_at, 0, 0, 0, 0, 0, bool(team_id))
        return counts, finding_summaries
    dialect = dialect_for_backend(get_db_backend())
    project_filter_sql, project_filter_params = dialect.in_clause("l.project_id", ids)
    package_filter_sql, package_filter_params = dialect.in_clause("project_id", ids)
    meta_filter_sql, meta_filter_params = dialect.in_clause("entity_id", ids)
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
    metadata_owner_sql, metadata_owner_params = _metadata_owner_where(session_id, team_id)
    entity_owner_sql, entity_owner_params = project_entity_owner_clause(session_id, team_id)
    finding_owner_sql, finding_owner_params = project_finding_owner_clause(session_id, team_id)

    project_run_ids = _empty_project_sets(ids)
    run_project_ids = defaultdict(set)
    for row in conn.execute(
        "SELECT l.project_id, l.entity_id AS run_id "  # nosec
        "FROM project_links l JOIN runs r ON r.id = l.entity_id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND " + run_owner_sql + " AND r.run_kind = ?",  # nosec
        (*project_filter_params, *run_owner_params, RUN_KIND_EXTERNAL),
    ).fetchall():
        project_id = str(row["project_id"] or "")
        run_id = str(row["run_id"] or "")
        if project_id in project_run_ids and run_id:
            project_run_ids[project_id].add(run_id)
            run_project_ids[run_id].add(project_id)
    for project_id, run_ids in project_run_ids.items():
        counts[project_id]["runs"] = len(run_ids)

    project_entity_ids = _empty_project_sets(ids)
    entity_project_ids = defaultdict(set)
    for row in conn.execute(
        "SELECT l.project_id, e.id AS entity_id, e.type, l.review_state "  # nosec
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'atlas_entity' "
        + entity_owner_sql
        + "AND COALESCE(e.suppressed, FALSE) = FALSE",
        (*project_filter_params, *entity_owner_params),
    ).fetchall():
        project_id = str(row["project_id"] or "")
        entity_id = str(row["entity_id"] or "")
        if project_id not in project_entity_ids or not entity_id:
            continue
        project_counts = counts[project_id]
        project_entity_ids[project_id].add(entity_id)
        entity_project_ids[entity_id].add(project_id)
        project_counts["entities"] += 1
        if row["type"] in {"domain", "ip", "url"}:
            if row["review_state"] == "pending":
                project_counts["pending_targets"] += 1
            else:
                project_counts["targets"] += 1

    all_run_ids = sorted(run_project_ids)
    run_chunk_count = 0
    for run_id_chunk in _chunks(all_run_ids):
        run_chunk_count += 1
        run_filter_sql, run_filter_params = dialect.in_clause("run_id", run_id_chunk)
        for row in conn.execute(
            "SELECT run_id, COUNT(*) AS count FROM run_file_artifacts "  # nosec
            "WHERE " + run_filter_sql + " GROUP BY run_id",  # nosec
            run_filter_params,
        ).fetchall():
            run_id = str(row["run_id"] or "")
            artifact_count = int(row["count"] or 0)
            for project_id in run_project_ids.get(run_id, ()):
                counts[project_id]["artifacts"] += artifact_count

    package_owner_sql = "" if team_id else "session_id = ? AND "
    package_owner_params = () if team_id else (session_id,)
    for row in conn.execute(
        "SELECT project_id, COUNT(*) AS count FROM evidence_packages "  # nosec
        "WHERE " + package_owner_sql + package_filter_sql + " "
        "GROUP BY project_id",
        (*package_owner_params, *package_filter_params),
    ).fetchall():
        counts[str(row["project_id"])]["packages"] = int(row["count"] or 0)

    seen_findings = _empty_project_sets(ids)
    for run_id_chunk in _chunks(all_run_ids):
        occurrence_filter_sql, occurrence_filter_params = dialect.in_clause("fo.run_id", run_id_chunk)
        occurrence_finding_sql = _join_sql(
            "SELECT fo.run_id, fo.finding_id, ",
            "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, ",
            "COALESCE(NULLIF(f.severity, ''), 'info') AS severity ",
            "FROM findings_occurrences fo ",
            "JOIN findings f ON f.id = fo.finding_id ",
            finding_owner_sql,
            "AND COALESCE(f.suppressed, FALSE) = FALSE ",
            "WHERE ",
            occurrence_filter_sql,
        )
        for row in conn.execute(
            occurrence_finding_sql,
            (*finding_owner_params, *occurrence_filter_params),
        ).fetchall():
            run_id = str(row["run_id"] or "")
            for project_id in run_project_ids.get(run_id, ()):
                _record_project_finding(
                    counts,
                    finding_summaries,
                    seen_findings,
                    project_id,
                    str(row["finding_id"] or ""),
                    review_state=row["review_state"],
                    severity=row["severity"],
                )

        for run_column in ("run_id", "first_run_id", "last_run_id"):
            run_filter_sql, run_filter_params = dialect.in_clause(f"f.{run_column}", run_id_chunk)
            for row in conn.execute(
                f"SELECT f.{run_column} AS linked_run_id, f.id AS finding_id, "  # nosec
                "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
                "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
                "FROM findings f "
                "WHERE " + run_filter_sql + " "  # nosec
                + finding_owner_sql
                + "AND COALESCE(f.suppressed, FALSE) = FALSE",
                (*run_filter_params, *finding_owner_params),
            ).fetchall():
                run_id = str(row["linked_run_id"] or "")
                for project_id in run_project_ids.get(run_id, ()):
                    _record_project_finding(
                        counts,
                        finding_summaries,
                        seen_findings,
                        project_id,
                        str(row["finding_id"] or ""),
                        review_state=row["review_state"],
                        severity=row["severity"],
                    )

    all_entity_ids = sorted(entity_project_ids)
    entity_chunk_count = 0
    for entity_id_chunk in _chunks(all_entity_ids):
        entity_chunk_count += 1
        entity_filter_sql, entity_filter_params = dialect.in_clause("f.entity_id", entity_id_chunk)
        for row in conn.execute(
            "SELECT f.entity_id, f.id AS finding_id, "
            "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
            "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
            "FROM findings f "
            "WHERE " + entity_filter_sql + " "  # nosec
            + finding_owner_sql
            + "AND COALESCE(f.suppressed, FALSE) = FALSE",
            (*entity_filter_params, *finding_owner_params),
        ).fetchall():
            entity_id = str(row["entity_id"] or "")
            for project_id in entity_project_ids.get(entity_id, ()):
                _record_project_finding(
                    counts,
                    finding_summaries,
                    seen_findings,
                    project_id,
                    str(row["finding_id"] or ""),
                    review_state=row["review_state"],
                    severity=row["severity"],
                )

    for row in conn.execute(
        "SELECT entity_id AS project_id, COUNT(*) AS count FROM entity_labels "  # nosec
        "WHERE " + metadata_owner_sql + " AND entity_type = 'project' AND " + meta_filter_sql + " "
        "GROUP BY entity_id",
        (*metadata_owner_params, *meta_filter_params),
    ).fetchall():
        counts[str(row["project_id"])]["labels"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT entity_id AS project_id, COUNT(*) AS count FROM entity_notes "  # nosec
        "WHERE " + metadata_owner_sql + " AND entity_type = 'project' AND " + meta_filter_sql + " "
        "GROUP BY entity_id",
        (*metadata_owner_params, *meta_filter_params),
    ).fetchall():
        counts[str(row["project_id"])]["notes"] = int(row["count"] or 0)

    log_project_list_metrics_debug(
        log, debug_started_at, len(ids), len(all_run_ids), len(all_entity_ids),
        run_chunk_count, entity_chunk_count, bool(team_id),
    )
    return counts, finding_summaries
