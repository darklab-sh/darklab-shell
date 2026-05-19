"""
Project workspace read/query helpers.
"""

from __future__ import annotations

from core.database import DB_BACKEND, db_connect
from core.database_backend import dialect_for_backend
from services.projects.active import active_project_id_from_preferences as _active_project_id_from_preferences
from services.projects.artifacts import (
    artifact_availability as _artifact_availability,
    row_to_run_file_artifact as _row_to_run_file_artifact,
)
from services.projects.contracts import MAX_ENTITY_ID_LEN
from services.projects.metadata import (
    _attach_package_metadata,
    _attach_project_labels,
    _attach_project_notes,
    _count_entity_metadata_for_ids,
    _entity_labels_by_id,
    _entity_notes_by_id,
)
from services.projects.models import (
    row_to_link as _row_to_link,
    row_to_project as _row_to_project,
    row_to_project_run as _row_to_project_run,
    row_to_target as _row_to_target,
)
from services.projects.packages import row_to_evidence_package as _row_to_evidence_package
from services.projects.utils import (
    normalize_page_window as _normalize_page_window,
    page_payload as _page_payload,
    trim_text as _trim_text,
)
from services.runs.kinds import RUN_KIND_EXTERNAL


def _metadata_filter_values(filters, key, max_len, *, lower=False):
    raw_values = filters.get(key)
    if raw_values is None:
        return []
    if isinstance(raw_values, str):
        raw_items = [raw_values]
    elif isinstance(raw_values, list):
        raw_items = raw_values
    else:
        raw_items = []
    values = []
    seen = set()
    for raw_value in raw_items:
        value = _trim_text(raw_value, max_len)
        if lower:
            value = value.lower()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values

def _project_list_order_sql():
    return (
        "ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END, "
        "CASE WHEN status = 'archived' THEN 1 ELSE 0 END, "
        + dialect_for_backend(DB_BACKEND).case_insensitive_order("name")
        + ", updated DESC, created DESC"
    )


def _project_list_where_sql(*, include_archived=False):
    if include_archived:
        return "WHERE session_id = ?"
    return "WHERE session_id = ? AND status != 'archived'"


def list_evidence_packages(session_id, project_id):
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        rows = conn.execute(
            "SELECT id, session_id, project_id, name, description, redaction_mode, "
            "include_artifacts, manifest, status, created, updated "
            "FROM evidence_packages WHERE session_id = ? AND project_id = ? "
            "ORDER BY updated DESC, created DESC",
            (session_id, project_id),
        ).fetchall()
        packages = [_row_to_evidence_package(row) for row in rows]
        _attach_package_metadata(conn, session_id, packages)
    return packages


def get_evidence_package(session_id, project_id, package_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, project_id, name, description, redaction_mode, "
            "include_artifacts, manifest, status, created, updated "
            "FROM evidence_packages WHERE session_id = ? AND project_id = ? AND id = ?",
            [session_id, project_id, package_id],
        ).fetchone()
        package = _row_to_evidence_package(row)
        _attach_package_metadata(conn, session_id, [package])
    return package


def _project_rows_to_list_projects(conn, session_id, rows, *, include_counts=False):
    projects = [
        project
        for row in rows
        if (project := _row_to_project(row)) is not None
    ]
    _attach_project_notes(conn, session_id, projects)
    _attach_project_labels(conn, session_id, projects)
    if include_counts:
        counts_by_project, finding_summaries_by_project = _project_list_metrics(
            conn,
            session_id,
            [project["id"] for project in projects],
        )
        for project in projects:
            project["counts"] = counts_by_project.get(project["id"], _empty_project_counts())
            project["finding_summary"] = finding_summaries_by_project.get(
                project["id"],
                _empty_project_finding_summary(),
            )
    return projects


def _empty_project_counts():
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


def _empty_project_finding_summary():
    return {
        "review_states": {},
        "severities": {},
    }


def _add_finding_summary_count(summary, *, review_state, severity, count):
    safe_count = int(count or 0)
    if safe_count <= 0:
        return
    state = str(review_state or "new").strip().lower() or "new"
    severity_name = str(severity or "info").strip().lower() or "info"
    summary["review_states"][state] = int(summary["review_states"].get(state, 0)) + safe_count
    summary["severities"][severity_name] = int(summary["severities"].get(severity_name, 0)) + safe_count


def _project_list_metrics(conn, session_id, project_ids):
    ids = [str(project_id) for project_id in project_ids if project_id]
    counts = {project_id: _empty_project_counts() for project_id in ids}
    finding_summaries = {project_id: _empty_project_finding_summary() for project_id in ids}
    if not ids:
        return counts, finding_summaries
    dialect = dialect_for_backend(DB_BACKEND)
    project_filter_sql, project_filter_params = dialect.in_clause("l.project_id", ids)
    package_filter_sql, package_filter_params = dialect.in_clause("project_id", ids)
    meta_filter_sql, meta_filter_params = dialect.in_clause("entity_id", ids)

    for row in conn.execute(
        "SELECT l.project_id, COUNT(*) AS count "  # nosec
        "FROM project_links l JOIN runs r ON r.id = l.entity_id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND r.session_id = ? AND r.run_kind = ? "
        "GROUP BY l.project_id",
        (*project_filter_params, session_id, RUN_KIND_EXTERNAL),
    ).fetchall():
        counts[str(row["project_id"])]["runs"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT l.project_id, e.type, l.review_state, COUNT(*) AS count "  # nosec
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'atlas_entity' "
        "AND e.session_id = ? AND COALESCE(e.suppressed, FALSE) = FALSE "
        "GROUP BY l.project_id, e.type, l.review_state",
        (*project_filter_params, session_id),
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
        "AND r.session_id = ? AND r.run_kind = ? "
        "GROUP BY l.project_id",
        (*project_filter_params, session_id, RUN_KIND_EXTERNAL),
    ).fetchall():
        counts[str(row["project_id"])]["artifacts"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT project_id, COUNT(*) AS count FROM evidence_packages "  # nosec
        "WHERE session_id = ? AND " + package_filter_sql + " "
        "GROUP BY project_id",
        (session_id, *package_filter_params),
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
        "JOIN findings f ON f.id = fo.finding_id AND f.session_id = ? "
        "AND COALESCE(f.suppressed, FALSE) = FALSE "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND r.session_id = ? AND r.run_kind = ? "
        "UNION "
        "SELECT l.project_id, f.id AS finding_id, "
        "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
        "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN findings f ON f.session_id = ? "
        "AND COALESCE(f.suppressed, FALSE) = FALSE "
        "AND (f.run_id = r.id OR f.first_run_id = r.id OR f.last_run_id = r.id) "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND r.session_id = ? AND r.run_kind = ? "
        "UNION "
        "SELECT l.project_id, f.id AS finding_id, "
        "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
        "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
        "FROM project_links l "
        "JOIN entities e ON e.id = l.entity_id "
        "JOIN findings f ON f.entity_id = e.id AND f.session_id = ? "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'atlas_entity' "
        "AND e.session_id = ? AND COALESCE(e.suppressed, FALSE) = FALSE "
        "AND COALESCE(f.suppressed, FALSE) = FALSE"
        ") grouped_findings GROUP BY project_id, review_state, severity",
        (
            session_id,
            *project_filter_params,
            session_id,
            RUN_KIND_EXTERNAL,
            session_id,
            *project_filter_params,
            session_id,
            RUN_KIND_EXTERNAL,
            session_id,
            *project_filter_params,
            session_id,
        ),
    ).fetchall():
        project_id = str(row["project_id"])
        count = int(row["count"] or 0)
        counts[project_id]["findings"] += count
        _add_finding_summary_count(
            finding_summaries[project_id],
            review_state=row["review_state"],
            severity=row["severity"],
            count=count,
        )

    for row in conn.execute(
        "SELECT entity_id AS project_id, COUNT(*) AS count FROM entity_labels "  # nosec
        "WHERE session_id = ? AND entity_type = 'project' AND " + meta_filter_sql + " "
        "GROUP BY entity_id",
        (session_id, *meta_filter_params),
    ).fetchall():
        counts[str(row["project_id"])]["labels"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT entity_id AS project_id, COUNT(*) AS count FROM entity_notes "  # nosec
        "WHERE session_id = ? AND entity_type = 'project' AND " + meta_filter_sql + " "
        "GROUP BY entity_id",
        (session_id, *meta_filter_params),
    ).fetchall():
        counts[str(row["project_id"])]["notes"] = int(row["count"] or 0)

    return counts, finding_summaries


def list_projects(session_id, *, include_archived=False):
    with db_connect() as conn:
        where_sql = _project_list_where_sql(include_archived=include_archived)
        active_project_id = _active_project_id_from_preferences(conn, session_id)
        rows = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "  # nosec
            "FROM projects "
            + where_sql
            + " "
            + _project_list_order_sql(),
            (session_id, active_project_id),
        ).fetchall()
        projects = _project_rows_to_list_projects(conn, session_id, rows)
    return projects


def list_projects_page(session_id, *, include_archived=False, limit=50, offset=0, include_counts=False):
    safe_limit, safe_offset = _normalize_page_window(limit, offset, maximum=100)
    with db_connect() as conn:
        where_sql = _project_list_where_sql(include_archived=include_archived)
        active_project_id = _active_project_id_from_preferences(conn, session_id)
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM projects " + where_sql,  # nosec
            (session_id,),
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        rows = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "  # nosec
            "FROM projects "
            + where_sql
            + " "
            + _project_list_order_sql()
            + " LIMIT ? OFFSET ?",
            (session_id, active_project_id, safe_limit, safe_offset),
        ).fetchall()
        projects = _project_rows_to_list_projects(conn, session_id, rows, include_counts=include_counts)
    return _page_payload("projects", projects, total, safe_limit, safe_offset)


def get_project(session_id, project_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "
            "FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        project = _row_to_project(row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
    return project


def _count_rows_for_ids(conn, table, column, ids):
    values = [str(value) for value in ids if value]
    if not values:
        return 0
    placeholders = ",".join("?" for _ in values)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE {column} IN ({placeholders})",  # nosec
        values,
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _project_run_count_maps(conn, session_id, run_ids):
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return {}, {}
    placeholders = ",".join("?" for _ in ids)
    finding_counts = {run_id: 0 for run_id in ids}
    artifact_counts = {run_id: 0 for run_id in ids}
    finding_rows = conn.execute(
        "SELECT run_id, COUNT(DISTINCT finding_id) AS count FROM ("  # nosec
        "SELECT fo.run_id AS run_id, fo.finding_id AS finding_id "
        "FROM findings_occurrences fo JOIN findings f ON f.id = fo.finding_id "
        f"WHERE f.session_id = ? AND COALESCE(f.suppressed, FALSE) = FALSE AND fo.run_id IN ({placeholders}) "
        "UNION "
        "SELECT run_id, id AS finding_id FROM findings "
        f"WHERE session_id = ? AND COALESCE(suppressed, FALSE) = FALSE AND run_id IN ({placeholders}) "
        "UNION "
        "SELECT first_run_id AS run_id, id AS finding_id FROM findings "
        f"WHERE session_id = ? AND COALESCE(suppressed, FALSE) = FALSE AND first_run_id IN ({placeholders}) "
        "UNION "
        "SELECT last_run_id AS run_id, id AS finding_id FROM findings "
        f"WHERE session_id = ? AND COALESCE(suppressed, FALSE) = FALSE AND last_run_id IN ({placeholders})"
        ") grouped_findings WHERE run_id IS NOT NULL AND run_id != '' GROUP BY run_id",
        (session_id, *ids, session_id, *ids, session_id, *ids, session_id, *ids),
    ).fetchall()
    for row in finding_rows:
        finding_counts[str(row["run_id"])] = int(row["count"] or 0)
    artifact_rows = conn.execute(
        "SELECT run_id, COUNT(*) AS count FROM run_file_artifacts "  # nosec
        f"WHERE run_id IN ({placeholders}) GROUP BY run_id",
        ids,
    ).fetchall()
    for row in artifact_rows:
        artifact_counts[str(row["run_id"])] = int(row["count"] or 0)
    return finding_counts, artifact_counts


def _project_atlas_entity_select_sql(*, target_only=False, entity_type="", extra_where=""):
    type_filter = "AND e.type IN ('domain', 'ip', 'url') " if target_only else ""
    if entity_type:
        type_filter += "AND e.type = ? "
    dialect = dialect_for_backend(DB_BACKEND)
    provider_list_expr = dialect.string_agg_distinct("eis.provider")
    value_order_expr = dialect.case_insensitive_order("e.canonical_value")
    return (
        "SELECT e.id, l.project_id, e.type, e.canonical_value, "  # nosec
        "COALESCE(("
        "SELECT erl.run_id FROM entity_run_links erl "
        "JOIN project_links run_link ON run_link.entity_type = 'run' AND run_link.entity_id = erl.run_id "
        "WHERE erl.entity_id = e.id AND run_link.project_id = l.project_id "
        "ORDER BY erl.last_seen_at DESC, erl.run_id DESC LIMIT 1"
        "), '') AS source_run_id, "
        "l.confidence, l.review_state, l.source, l.source_detail, "
        "e.occurrence_count, e.suppressed, e.suppressed_reason, e.suppressed_at, "
        "e.last_seen_at, e.created, COALESCE(NULLIF(l.updated, ''), l.created) AS updated, "
        "COALESCE(("
        "SELECT COUNT(DISTINCT erl.run_id) FROM entity_run_links erl "
        "JOIN runs er ON er.id = erl.run_id AND er.session_id = e.session_id "
        "WHERE erl.entity_id = e.id"
        "), 0) AS run_count, "
        "COALESCE(("
        "SELECT COUNT(DISTINCT eis.provider) FROM entity_intel_snapshots eis "
        "WHERE eis.session_id = e.session_id AND eis.entity_id = e.id "
        "AND (eis.status = 'ok' OR eis.status = 'partial')"
        "), 0) AS intel_provider_count "
        ", COALESCE(("
        "SELECT " + provider_list_expr + " FROM entity_intel_snapshots eis "
        "WHERE eis.session_id = e.session_id AND eis.entity_id = e.id "
        "AND (eis.status = 'ok' OR eis.status = 'partial')"
        "), '') AS intel_providers "
        ", COALESCE(("
        "SELECT MAX(eis.fetched_at) FROM entity_intel_snapshots eis "
        "WHERE eis.session_id = e.session_id AND eis.entity_id = e.id "
        "AND (eis.status = 'ok' OR eis.status = 'partial')"
        "), '') AS intel_last_refreshed "
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND e.session_id = ? "
        "AND COALESCE(e.suppressed, FALSE) = FALSE "
        + type_filter
        + (extra_where + " " if extra_where else "")
        + "ORDER BY e.type ASC, " + value_order_expr
    )


def _project_run_rows_to_items(conn, session_id, rows):
    run_ids = [row["id"] for row in rows if row["id"]]
    finding_counts, artifact_counts = _project_run_count_maps(conn, session_id, run_ids)
    run_labels = _entity_labels_by_id(conn, session_id, "run", run_ids)
    run_notes = _entity_notes_by_id(conn, session_id, "run", run_ids)
    runs = []
    for row in rows:
        item = _row_to_project_run(row)
        if not item:
            continue
        run_id = str(item["id"])
        item["finding_count"] = finding_counts.get(run_id, int(item.get("finding_count") or 0))
        item["artifact_count"] = artifact_counts.get(run_id, int(item.get("artifact_count") or 0))
        item["labels"] = run_labels.get(run_id, [])
        item["note"] = run_notes.get(run_id)
        runs.append(item)
    return runs


def _project_entity_counts_by_type(conn, session_id, project_id):
    rows = conn.execute(
        "SELECT e.type, COUNT(*) AS count "
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND e.session_id = ? "
        "AND COALESCE(e.suppressed, FALSE) = FALSE "
        "GROUP BY e.type",
        (project_id, session_id),
    ).fetchall()
    return {str(row["type"] or ""): int(row["count"] or 0) for row in rows}


def _project_entity_rows_to_items(conn, session_id, rows):
    entity_ids = [str(row["id"] or "") for row in rows if row["id"]]
    entity_labels = _entity_labels_by_id(conn, session_id, "atlas_entity", entity_ids)
    entity_notes = _entity_notes_by_id(conn, session_id, "atlas_entity", entity_ids)
    entities = []
    for row in rows:
        item = _row_to_target(row)
        if not item:
            continue
        item_id = str(item["id"])
        entities.append({
            **item,
            "labels": entity_labels.get(item_id, []),
            "note": entity_notes.get(item_id),
        })
    return entities


def _project_artifact_rows_to_items(session_id, conn, rows):
    artifact_ids = [str(row["id"] or "") for row in rows if row["id"]]
    artifact_labels = _entity_labels_by_id(conn, session_id, "run_file_artifact", artifact_ids)
    artifact_notes = _entity_notes_by_id(conn, session_id, "run_file_artifact", artifact_ids)
    artifacts = []
    for row in rows:
        item = _row_to_run_file_artifact(row)
        if not item:
            continue
        item_id = str(item["id"])
        artifacts.append({
            **item,
            **_artifact_availability(session_id, item),
            "labels": artifact_labels.get(item_id, []),
            "note": artifact_notes.get(item_id),
        })
    return artifacts


def get_project_summary(session_id, project_id):
    with db_connect() as conn:
        project_row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "
            "FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project_row:
            return None
        project = _row_to_project(project_row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
        run_link_rows = conn.execute(
            "SELECT l.id, l.project_id, l.entity_type, l.entity_id, l.source, l.created "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ? "
            "ORDER BY l.created DESC",
            (project_id, session_id, RUN_KIND_EXTERNAL),
        ).fetchall()
        atlas_link_rows = conn.execute(
            "SELECT l.id, l.project_id, l.entity_type, l.entity_id, l.source, l.created "
            "FROM project_links l JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
            "AND e.session_id = ? AND COALESCE(e.suppressed, FALSE) = FALSE "
            "ORDER BY l.created DESC",
            (project_id, session_id),
        ).fetchall()
        link_rows = [*run_link_rows, *atlas_link_rows]
        target_rows = conn.execute(
            _project_atlas_entity_select_sql(target_only=True),
            (project_id, session_id),
        ).fetchall()
        run_ids = [row["entity_id"] for row in run_link_rows if row["entity_type"] == "run"]
        entity_id_rows = conn.execute(
            "SELECT e.id, e.type "
            "FROM project_links l JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
            "AND e.session_id = ? AND COALESCE(e.suppressed, FALSE) = FALSE",
            (project_id, session_id),
        ).fetchall()
        entity_ids = [row["id"] for row in entity_id_rows]
        entity_counts_by_type = _project_entity_counts_by_type(conn, session_id, project_id)
        artifact_id_rows = []
        finding_rows = []
        finding_summary = _empty_project_finding_summary()
        run_rows = []
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            run_rows = conn.execute(
                "SELECT r.id, r.command, r.started, r.finished, r.exit_code, r.output_line_count, "
                "r.full_output_available, r.full_output_truncated, "
                "art.byte_size AS output_artifact_byte_size, "
                "art.line_count AS output_artifact_line_count, "
                "l.created, l.source AS link_source "
                "FROM project_links l JOIN runs r ON r.id = l.entity_id "
                "LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
                "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
                "AND r.run_kind = ? "
                "ORDER BY r.started DESC, l.created DESC",
                (project_id, session_id, RUN_KIND_EXTERNAL),
            ).fetchall()
            artifact_id_rows = conn.execute(
                "SELECT id "
                f"FROM run_file_artifacts WHERE run_id IN ({placeholders}) ",  # nosec
                run_ids,
            ).fetchall()
        if run_ids or entity_ids:
            finding_clauses = []
            finding_params = [session_id]
            if run_ids:
                run_placeholders = ",".join("?" for _ in run_ids)
                finding_clauses.append(
                    "EXISTS ("
                    "SELECT 1 FROM findings_occurrences fo "
                    "WHERE fo.finding_id = f.id "
                    f"AND fo.run_id IN ({run_placeholders})"  # nosec
                    ") "
                    f"OR f.run_id IN ({run_placeholders}) "  # nosec
                    f"OR f.first_run_id IN ({run_placeholders}) "  # nosec
                    f"OR f.last_run_id IN ({run_placeholders})"  # nosec
                )
                finding_params.extend([*run_ids, *run_ids, *run_ids, *run_ids])
            if entity_ids:
                entity_placeholders = ",".join("?" for _ in entity_ids)
                finding_clauses.append(f"f.entity_id IN ({entity_placeholders})")  # nosec
                finding_params.extend(entity_ids)
            finding_rows = conn.execute(
                "SELECT DISTINCT f.id, "
                "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
                "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
                "FROM findings f WHERE f.session_id = ? "
                "AND COALESCE(f.suppressed, FALSE) = FALSE AND ("  # nosec
                + " OR ".join(finding_clauses)
                + ")",
                finding_params,
            ).fetchall()
        artifact_ids = [row["id"] for row in artifact_id_rows]
        finding_ids = [row["id"] for row in finding_rows]
        for row in finding_rows:
            _add_finding_summary_count(
                finding_summary,
                review_state=row["review_state"],
                severity=row["severity"],
                count=1,
            )
        target_ids = [row["id"] for row in target_rows]
        package_rows = conn.execute(
            "SELECT id FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        ).fetchall()
        package_ids = [row["id"] for row in package_rows]
        target_labels = _entity_labels_by_id(conn, session_id, "atlas_entity", target_ids)
        target_notes = _entity_notes_by_id(conn, session_id, "atlas_entity", target_ids)
        label_count = (
            _count_entity_metadata_for_ids(conn, "entity_labels", "project", [project_id])
            + _count_entity_metadata_for_ids(conn, "entity_labels", "run", run_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "run_file_artifact", artifact_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "finding", finding_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "atlas_entity", entity_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "target", target_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "package", package_ids)
        )
        note_count = (
            _count_entity_metadata_for_ids(conn, "entity_notes", "project", [project_id])
            + _count_entity_metadata_for_ids(conn, "entity_notes", "run", run_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "run_file_artifact", artifact_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "finding", finding_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "atlas_entity", entity_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "target", target_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "package", package_ids)
        )
        run_items = _project_run_rows_to_items(conn, session_id, run_rows)
    links = [_row_to_link(row) for row in link_rows]
    targets = []
    for item in (_row_to_target(row) for row in target_rows):
        if not item:
            continue
        item_id = str(item["id"])
        targets.append({
            **item,
            "labels": target_labels.get(item_id, []),
            "note": target_notes.get(item_id),
        })
    confirmed_target_count = sum(1 for target in targets if target and target.get("review_state") == "confirmed")
    pending_target_count = sum(1 for target in targets if target and target.get("review_state") == "pending")
    runs = run_items
    packages = list_evidence_packages(session_id, project_id) or []
    return {
        "project": project,
        "links": links,
        "targets": targets,
        "entities": [],
        "entity_counts": entity_counts_by_type,
        "runs": runs,
        "artifacts": [],
        "packages": packages,
        "counts": {
            "runs": len(run_ids),
            "entities": sum(entity_counts_by_type.values()),
            "targets": confirmed_target_count,
            "pending_targets": pending_target_count,
            "artifacts": len(artifact_ids),
            "findings": len(finding_ids),
            "labels": label_count,
            "notes": note_count,
            "packages": len(package_ids),
        },
        "finding_summary": finding_summary,
    }


def _project_entity_page_payload(entities, total, limit, offset, counts_by_type=None):
    return _page_payload(
        "entities",
        entities,
        total,
        limit,
        offset,
        extra={"counts_by_type": counts_by_type if isinstance(counts_by_type, dict) else {}},
    )


def _project_entity_filter_clause(conn, session_id, project_id, filters):
    filters = filters if isinstance(filters, dict) else {}
    run_ids = set(_metadata_filter_values(filters, "run_id", MAX_ENTITY_ID_LEN))
    target_ids = _metadata_filter_values(filters, "target_id", MAX_ENTITY_ID_LEN)
    target_run_ids = _project_target_filter_run_ids(conn, session_id, project_id, target_ids)
    candidate_run_ids = None
    if run_ids:
        candidate_run_ids = set(run_ids)
    if target_run_ids is not None:
        candidate_run_ids = set(target_run_ids) if candidate_run_ids is None else candidate_run_ids.intersection(target_run_ids)
    if candidate_run_ids is None and not target_ids:
        return "", []
    if candidate_run_ids is not None and not candidate_run_ids and not target_ids:
        return "AND 1 = 0", []

    clauses = []
    params = []
    if candidate_run_ids:
        ordered_run_ids = sorted(candidate_run_ids)
        run_placeholders = ",".join("?" for _ in ordered_run_ids)
        clauses.append(
            "EXISTS ("
            "SELECT 1 FROM entity_run_links filtered_erl "
            "JOIN project_links filtered_run_link "
            "  ON filtered_run_link.project_id = ? "
            " AND filtered_run_link.entity_type = 'run' "
            " AND filtered_run_link.entity_id = filtered_erl.run_id "
            "JOIN runs filtered_run ON filtered_run.id = filtered_erl.run_id "
            "WHERE filtered_erl.entity_id = e.id "
            "AND filtered_run.session_id = ? "
            "AND filtered_run.run_kind = ? "
            f"AND filtered_erl.run_id IN ({run_placeholders})"  # nosec
            ")"
        )
        params.extend([project_id, session_id, RUN_KIND_EXTERNAL, *ordered_run_ids])
    if target_ids:
        target_placeholders = ",".join("?" for _ in target_ids)
        clauses.append(f"e.id IN ({target_placeholders})")  # nosec
        params.extend(target_ids)
    if not clauses:
        return "AND 1 = 0", []
    return "AND (" + " OR ".join(clauses) + ")", params


def list_project_entities(session_id, project_id, filters=None, *, entity_type="", limit=50, offset=0):
    safe_limit, safe_offset = _normalize_page_window(limit, offset)
    normalized_type = _trim_text(entity_type, 32).lower()
    with db_connect() as conn:
        project_row = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project_row:
            return None
        filter_sql, filter_params = _project_entity_filter_clause(conn, session_id, project_id, filters)
        counts_by_type = {}
        for row in conn.execute(
            "SELECT e.type, COUNT(*) AS count "  # nosec
            "FROM project_links l JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
            "AND e.session_id = ? AND COALESCE(e.suppressed, FALSE) = FALSE "
            + filter_sql
            + " GROUP BY e.type",
            (project_id, session_id, *filter_params),
        ).fetchall():
            counts_by_type[str(row["type"] or "")] = int(row["count"] or 0)
        total = int(counts_by_type.get(normalized_type, 0)) if normalized_type else sum(counts_by_type.values())
        params = [project_id, session_id]
        if normalized_type:
            params.append(normalized_type)
        rows = conn.execute(
            _project_atlas_entity_select_sql(entity_type=normalized_type, extra_where=filter_sql)
            + " LIMIT ? OFFSET ?",
            (*params, *filter_params, safe_limit, safe_offset),
        ).fetchall()
        entities = _project_entity_rows_to_items(conn, session_id, rows)
    return _project_entity_page_payload(entities, total, safe_limit, safe_offset, counts_by_type)


def _project_artifact_page_payload(artifacts, total, limit, offset, run_counts=None):
    return _page_payload(
        "artifacts",
        artifacts,
        total,
        limit,
        offset,
        extra={"run_counts": run_counts if isinstance(run_counts, dict) else {}},
    )


def _project_target_filter_run_ids(conn, session_id, project_id, target_ids):
    ids = [str(target_id) for target_id in target_ids if target_id]
    if not ids:
        return None
    placeholders = ",".join("?" for _ in ids)
    target_rows = conn.execute(
        "SELECT e.id, e.canonical_value "
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        "AND e.session_id = ? AND COALESCE(e.suppressed, FALSE) = FALSE "
        f"AND e.id IN ({placeholders})",  # nosec
        (project_id, session_id, *ids),
    ).fetchall()
    if len(target_rows) != len(ids):
        return set()
    run_ids = set()
    for row in target_rows:
        value = str(row["canonical_value"] or "").strip().lower()
        if not value:
            continue
        direct_rows = conn.execute(
            "SELECT l.entity_id AS run_id "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ? "
            "AND LOWER(r.command) LIKE ?",
            (project_id, session_id, RUN_KIND_EXTERNAL, f"%{value}%"),
        ).fetchall()
        run_ids.update(str(run["run_id"] or "") for run in direct_rows if run["run_id"])
    finding_rows = conn.execute(
        "WITH project_runs AS ("
        "  SELECT l.entity_id AS run_id FROM project_links l "
        "  JOIN runs r ON r.id = l.entity_id "
        "  WHERE l.project_id = ? AND l.entity_type = 'run' "
        "  AND r.session_id = ? AND r.run_kind = ?"
        "), target_findings AS ("
        "  SELECT f.id, f.run_id, f.first_run_id, f.last_run_id "
        "  FROM findings f WHERE f.session_id = ? "
        f"  AND COALESCE(f.entity_id, f.target_id) IN ({placeholders})"  # nosec
        ") "
        "SELECT DISTINCT run_id FROM ("
        "  SELECT fo.run_id AS run_id FROM findings_occurrences fo "
        "  JOIN target_findings tf ON tf.id = fo.finding_id "
        "  JOIN project_runs pr ON pr.run_id = fo.run_id "
        "  UNION "
        "  SELECT tf.run_id FROM target_findings tf JOIN project_runs pr ON pr.run_id = tf.run_id "
        "  UNION "
        "  SELECT tf.first_run_id FROM target_findings tf JOIN project_runs pr ON pr.run_id = tf.first_run_id "
        "  UNION "
        "  SELECT tf.last_run_id FROM target_findings tf JOIN project_runs pr ON pr.run_id = tf.last_run_id"
        ") matched_runs WHERE run_id IS NOT NULL AND run_id != ''",
        (project_id, session_id, RUN_KIND_EXTERNAL, session_id, *ids),
    ).fetchall()
    run_ids.update(str(row["run_id"] or "") for row in finding_rows if row["run_id"])
    return run_ids


def list_project_artifacts(session_id, project_id, filters=None, *, limit=50, offset=0):
    filters = filters if isinstance(filters, dict) else {}
    safe_limit, safe_offset = _normalize_page_window(limit, offset)
    with db_connect() as conn:
        project_row = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project_row:
            return None
        linked_run_rows = conn.execute(
            "SELECT l.entity_id AS run_id "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ?",
            (project_id, session_id, RUN_KIND_EXTERNAL),
        ).fetchall()
        allowed_run_ids = {str(row["run_id"] or "") for row in linked_run_rows if row["run_id"]}
        run_ids = _metadata_filter_values(filters, "run_id", MAX_ENTITY_ID_LEN)
        if run_ids:
            candidate_run_ids = allowed_run_ids.intersection(run_ids)
        else:
            candidate_run_ids = set(allowed_run_ids)
        target_ids = _metadata_filter_values(filters, "target_id", MAX_ENTITY_ID_LEN)
        target_run_ids = _project_target_filter_run_ids(conn, session_id, project_id, target_ids)
        if target_run_ids is not None:
            candidate_run_ids = candidate_run_ids.intersection(target_run_ids)
        if not candidate_run_ids:
            return _project_artifact_page_payload([], 0, safe_limit, safe_offset, {})
        ordered_run_ids = sorted(candidate_run_ids)
        placeholders = ",".join("?" for _ in ordered_run_ids)
        count_rows = conn.execute(
            "SELECT run_id, COUNT(*) AS count FROM run_file_artifacts "  # nosec
            "WHERE session_id = ? "
            f"AND run_id IN ({placeholders}) "  # nosec
            "GROUP BY run_id",
            (session_id, *ordered_run_ids),
        ).fetchall()
        run_counts = {str(row["run_id"] or ""): int(row["count"] or 0) for row in count_rows}
        total = sum(run_counts.values())
        rows = conn.execute(
            "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "  # nosec
            "detected_by, content_type, preview_type, content_sha256, created "
            "FROM run_file_artifacts WHERE session_id = ? "
            f"AND run_id IN ({placeholders}) "  # nosec
            "ORDER BY created DESC, id DESC "
            "LIMIT ? OFFSET ?",
            (session_id, *ordered_run_ids, safe_limit, safe_offset),
        ).fetchall()
        artifacts = _project_artifact_rows_to_items(session_id, conn, rows)
    return _project_artifact_page_payload(artifacts, total, safe_limit, safe_offset, run_counts)


def _list_all_project_artifacts(session_id, project_id):
    artifacts = []
    offset = 0
    while True:
        page = list_project_artifacts(session_id, project_id, {}, limit=200, offset=offset)
        if page is None:
            return None
        rows = page.get("artifacts") if isinstance(page, dict) else []
        if not rows:
            break
        artifacts.extend(rows)
        offset += len(rows)
        if offset >= int(page.get("total") or len(artifacts)):
            break
    return artifacts


def list_project_runs(session_id, project_id, *, limit=50, offset=0):
    safe_limit, safe_offset = _normalize_page_window(limit, offset)
    with db_connect() as conn:
        project_row = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project_row:
            return None
        total_row = conn.execute(
            "SELECT COUNT(*) AS count "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ?",
            (project_id, session_id, RUN_KIND_EXTERNAL),
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        rows = conn.execute(
            "SELECT r.id, r.command, r.started, r.finished, r.exit_code, r.output_line_count, "
            "r.full_output_available, r.full_output_truncated, "
            "art.byte_size AS output_artifact_byte_size, "
            "art.line_count AS output_artifact_line_count, "
            "l.created, l.source AS link_source "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
            "AND r.run_kind = ? "
            "ORDER BY r.started DESC, l.created DESC "
            "LIMIT ? OFFSET ?",
            (project_id, session_id, RUN_KIND_EXTERNAL, safe_limit, safe_offset),
        ).fetchall()
        runs = _project_run_rows_to_items(conn, session_id, rows)
    return _page_payload("runs", runs, total, safe_limit, safe_offset)


def get_project_run_file_artifact(session_id, project_id, artifact_id):
    artifact_id = _trim_text(artifact_id, MAX_ENTITY_ID_LEN)
    if not artifact_id:
        return None
    with db_connect() as conn:
        row = conn.execute(
            "SELECT a.id, a.session_id, a.run_id, a.workspace_path, a.display_name, a.kind, "
            "a.byte_size, a.detected_by, a.content_type, a.preview_type, a.content_sha256, a.created "
            "FROM run_file_artifacts a "
            "JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = a.run_id "
            "JOIN projects p ON p.id = l.project_id "
            "JOIN runs r ON r.id = a.run_id "
            "WHERE p.session_id = ? AND p.id = ? AND a.session_id = ? AND a.id = ? "
            "AND r.session_id = ?",
            (session_id, project_id, session_id, artifact_id, session_id),
        ).fetchone()
    artifact = _row_to_run_file_artifact(row)
    if not artifact:
        return None
    return {
        **artifact,
        **_artifact_availability(session_id, artifact),
    }
