"""Project list count and finding-summary query helpers."""

from __future__ import annotations

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.projects.metadata import _metadata_owner_where
from services.projects.scope import shared_owner_where
from services.runs.kinds import RUN_KIND_EXTERNAL


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
    return {
        "review_states": {},
        "severities": {},
    }


def add_finding_summary_count(summary, *, review_state, severity, count):
    safe_count = int(count or 0)
    if safe_count <= 0:
        return
    state = str(review_state or "new").strip().lower() or "new"
    severity_name = str(severity or "info").strip().lower() or "info"
    summary["review_states"][state] = int(summary["review_states"].get(state, 0)) + safe_count
    summary["severities"][severity_name] = int(summary["severities"].get(severity_name, 0)) + safe_count


def project_entity_owner_clause(session_id, team_id="", *, table_alias="e"):
    if team_id:
        return "", ()
    prefix = f"{table_alias}." if table_alias else ""
    return f"AND {prefix}session_id = ? ", (session_id,)


def project_finding_owner_clause(session_id, team_id="", *, table_alias="f"):
    if team_id:
        return "", ()
    prefix = f"{table_alias}." if table_alias else ""
    return f"AND {prefix}session_id = ? ", (session_id,)


def project_list_metrics(conn, session_id, project_ids, *, team_id=""):
    ids = [str(project_id) for project_id in project_ids if project_id]
    counts = {project_id: empty_project_counts() for project_id in ids}
    finding_summaries = {project_id: empty_project_finding_summary() for project_id in ids}
    if not ids:
        return counts, finding_summaries
    dialect = dialect_for_backend(get_db_backend())
    project_filter_sql, project_filter_params = dialect.in_clause("l.project_id", ids)
    package_filter_sql, package_filter_params = dialect.in_clause("project_id", ids)
    meta_filter_sql, meta_filter_params = dialect.in_clause("entity_id", ids)
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
    metadata_owner_sql, metadata_owner_params = _metadata_owner_where(session_id, team_id)
    entity_owner_sql, entity_owner_params = project_entity_owner_clause(session_id, team_id)
    finding_owner_sql, finding_owner_params = project_finding_owner_clause(session_id, team_id)

    for row in conn.execute(
        "SELECT l.project_id, COUNT(*) AS count "  # nosec
        "FROM project_links l JOIN runs r ON r.id = l.entity_id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
        "GROUP BY l.project_id",
        (*project_filter_params, *run_owner_params, RUN_KIND_EXTERNAL),
    ).fetchall():
        counts[str(row["project_id"])]["runs"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT l.project_id, e.type, l.review_state, COUNT(*) AS count "  # nosec
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'atlas_entity' "
        + entity_owner_sql
        + "AND COALESCE(e.suppressed, FALSE) = FALSE "
        "GROUP BY l.project_id, e.type, l.review_state",
        (*project_filter_params, *entity_owner_params),
    ).fetchall():
        project_counts = counts[str(row["project_id"])]
        count = int(row["count"] or 0)
        project_counts["entities"] += count
        if row["type"] in {"domain", "ip", "url"}:
            if row["review_state"] == "pending":
                project_counts["pending_targets"] += count
            else:
                project_counts["targets"] += count

    for row in conn.execute(
        "SELECT l.project_id, COUNT(a.id) AS count "  # nosec
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN run_file_artifacts a ON a.run_id = r.id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
        "GROUP BY l.project_id",
        (*project_filter_params, *run_owner_params, RUN_KIND_EXTERNAL),
    ).fetchall():
        counts[str(row["project_id"])]["artifacts"] = int(row["count"] or 0)

    package_owner_sql = "" if team_id else "session_id = ? AND "
    package_owner_params = () if team_id else (session_id,)
    for row in conn.execute(
        "SELECT project_id, COUNT(*) AS count FROM evidence_packages "  # nosec
        "WHERE " + package_owner_sql + package_filter_sql + " "
        "GROUP BY project_id",
        (*package_owner_params, *package_filter_params),
    ).fetchall():
        counts[str(row["project_id"])]["packages"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT project_id, review_state, severity, COUNT(DISTINCT finding_id) AS count FROM ("  # nosec
        "SELECT l.project_id, fo.finding_id, "
        "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
        "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN findings_occurrences fo ON fo.run_id = r.id "
        "JOIN findings f ON f.id = fo.finding_id "
        + finding_owner_sql
        + "AND COALESCE(f.suppressed, FALSE) = FALSE "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
        "UNION "
        "SELECT l.project_id, f.id AS finding_id, "
        "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
        "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN findings f ON 1 = 1 "
        + finding_owner_sql
        + "AND COALESCE(f.suppressed, FALSE) = FALSE "
        "AND (f.run_id = r.id OR f.first_run_id = r.id OR f.last_run_id = r.id) "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
        "UNION "
        "SELECT l.project_id, f.id AS finding_id, "
        "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
        "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
        "FROM project_links l "
        "JOIN entities e ON e.id = l.entity_id "
        "JOIN findings f ON f.entity_id = e.id "
        + finding_owner_sql
        + "AND COALESCE(f.suppressed, FALSE) = FALSE "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'atlas_entity' "
        + entity_owner_sql
        + "AND COALESCE(e.suppressed, FALSE) = FALSE "
        ") grouped_findings GROUP BY project_id, review_state, severity",
        (
            *finding_owner_params,
            *project_filter_params,
            *run_owner_params,
            RUN_KIND_EXTERNAL,
            *finding_owner_params,
            *project_filter_params,
            *run_owner_params,
            RUN_KIND_EXTERNAL,
            *finding_owner_params,
            *project_filter_params,
            *entity_owner_params,
        ),
    ).fetchall():
        project_id = str(row["project_id"])
        count = int(row["count"] or 0)
        counts[project_id]["findings"] += count
        add_finding_summary_count(
            finding_summaries[project_id],
            review_state=row["review_state"],
            severity=row["severity"],
            count=count,
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

    return counts, finding_summaries
