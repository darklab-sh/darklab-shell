# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project workspace read/query helpers.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.atlas.scope import metadata_owner_id
from services.projects.contracts import MAX_ENTITY_ID_LEN
from services.projects.metadata import (
    _attach_project_labels,
    _attach_project_notes,
    _count_entity_metadata_for_ids,
    _entity_labels_by_id,
    _entity_notes_by_id,
    _metadata_owner_where,
)
from services.projects.list_metrics import (
    add_finding_summary_count as _add_finding_summary_count,
    empty_project_finding_summary as _empty_project_finding_summary,
    project_entity_owner_clause as _project_entity_owner_clause,
    project_finding_owner_clause as _project_finding_owner_clause,
)
from services.projects import list_queries as _list_queries
from services.projects.list_switcher import list_projects_switcher as _list_projects_switcher_impl
from services.projects.models import (
    row_to_link as _row_to_link,
    row_to_project as _row_to_project,
    row_to_project_run as _row_to_project_run,
    row_to_target as _row_to_target,
)
from services.projects.artifact_queries import (
    _list_all_project_artifacts as _list_all_project_artifacts_impl,
    _project_target_filter_run_ids as _project_target_filter_run_ids,
    get_project_run_file_artifact as _get_project_run_file_artifact_impl,
    list_project_artifacts as _list_project_artifacts_impl,
)
from services.projects.package_queries import get_evidence_package as _get_evidence_package_impl
from services.projects.package_queries import list_evidence_packages as _list_evidence_packages_impl
from services.projects.scope import project_select_columns, shared_owner_where
from services.projects.utils import (
    metadata_filter_values as _metadata_filter_values,
    normalize_page_window as _normalize_page_window,
    page_payload as _page_payload,
    trim_text as _trim_text,
)
from services.runs.kinds import RUN_KIND_EXTERNAL
from services.storage.transactions import run_transaction
from services.workflows.storage import apply_workflow_provenance, workflow_provenance_by_run

_T = TypeVar("_T")


def run_project_transaction(callback: Callable[[Any], _T]) -> _T:
    return run_transaction(callback, connect=get_db_connect())


def list_projects(session_id, *, include_archived=False, team_id=""):
    return _list_queries.list_projects(session_id, include_archived=include_archived, team_id=team_id)


def list_projects_page(session_id, *, include_archived=False, limit=50, offset=0, include_counts=False, team_id=""):
    return _list_queries.list_projects_page(
        session_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        include_counts=include_counts,
        team_id=team_id,
    )


def list_projects_switcher(session_id, *, query="", limit=8, team_id=""):
    return _list_projects_switcher_impl(session_id, query=query, limit=limit, team_id=team_id)


def list_project_artifacts(session_id, project_id, filters=None, *, limit=50, offset=0, team_id=""):
    return _list_project_artifacts_impl(
        session_id,
        project_id,
        filters,
        limit=limit,
        offset=offset,
        team_id=team_id,
    )


def get_project_run_file_artifact(session_id, project_id, artifact_id, *, team_id=""):
    return _get_project_run_file_artifact_impl(session_id, project_id, artifact_id, team_id=team_id)


def _list_all_project_artifacts(session_id, project_id, *, team_id=""):
    return _list_all_project_artifacts_impl(session_id, project_id, team_id=team_id)


def list_evidence_packages(session_id, project_id, *, team_id=""):
    return _list_evidence_packages_impl(session_id, project_id, team_id=team_id)


def get_evidence_package(session_id, project_id, package_id, *, team_id=""):
    return _get_evidence_package_impl(session_id, project_id, package_id, team_id=team_id)


def get_project(session_id, project_id, *, team_id=""):
    with get_db_connect()() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project_select_prefix = "SELECT "
        project_where_prefix = " FROM projects WHERE "
        project_id_suffix = " AND id = ?"
        project_sql = (
            project_select_prefix
            + project_select_columns()
            + project_where_prefix
            + owner_sql
            + project_id_suffix
        )
        row = conn.execute(
            project_sql,
            (*owner_params, project_id),
        ).fetchone()
        project = _row_to_project(row)
        _attach_project_notes(conn, session_id, [project], team_id=team_id)
        _attach_project_labels(conn, session_id, [project], team_id=team_id)
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


def _project_run_count_maps(conn, session_id, run_ids, *, team_id=""):
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return {}, {}
    placeholders = ",".join("?" for _ in ids)
    finding_counts = {run_id: 0 for run_id in ids}
    artifact_counts = {run_id: 0 for run_id in ids}
    finding_owner_sql, finding_owner_params = _project_finding_owner_clause(session_id, team_id, table_alias="f")
    direct_finding_owner_sql, direct_finding_owner_params = _project_finding_owner_clause(session_id, team_id, table_alias="")
    finding_rows = conn.execute(
        "SELECT run_id, COUNT(DISTINCT finding_id) AS count FROM ("  # nosec
        "SELECT fo.run_id AS run_id, fo.finding_id AS finding_id "
        "FROM findings_occurrences fo JOIN findings f ON f.id = fo.finding_id "
        f"WHERE 1 = 1 {finding_owner_sql}"
        f"AND COALESCE(f.suppressed, FALSE) = FALSE AND fo.run_id IN ({placeholders}) "
        "UNION "
        "SELECT run_id, id AS finding_id FROM findings "
        f"WHERE 1 = 1 {direct_finding_owner_sql}"
        f"AND COALESCE(suppressed, FALSE) = FALSE AND run_id IN ({placeholders}) "
        "UNION "
        "SELECT first_run_id AS run_id, id AS finding_id FROM findings "
        f"WHERE 1 = 1 {direct_finding_owner_sql}"
        f"AND COALESCE(suppressed, FALSE) = FALSE AND first_run_id IN ({placeholders}) "
        "UNION "
        "SELECT last_run_id AS run_id, id AS finding_id FROM findings "
        f"WHERE 1 = 1 {direct_finding_owner_sql}"
        f"AND COALESCE(suppressed, FALSE) = FALSE AND last_run_id IN ({placeholders})"
        ") grouped_findings WHERE run_id IS NOT NULL AND run_id != '' GROUP BY run_id",
        (
            *finding_owner_params,
            *ids,
            *direct_finding_owner_params,
            *ids,
            *direct_finding_owner_params,
            *ids,
            *direct_finding_owner_params,
            *ids,
        ),
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


def _project_atlas_entity_select_sql(*, target_only=False, entity_type="", extra_where="", team_id=""):
    type_filter = "AND e.type IN ('domain', 'ip', 'url') " if target_only else ""
    if entity_type:
        type_filter += "AND e.type = ? "
    run_owner_sql, _run_owner_params = shared_owner_where("", team_id=team_id, table_alias="er")
    entity_owner_sql = "" if team_id else "AND e.session_id = ? AND e.team_id = '' "
    dialect = dialect_for_backend(get_db_backend())
    provider_list_expr = dialect.string_agg_distinct("eis.provider")
    value_order_expr = dialect.case_insensitive_order("e.canonical_value")
    return (
        "SELECT e.id, l.id AS link_id, l.project_id, e.type, e.canonical_value, "  # nosec
        "e.host_entity_id, e.attributes_json, "
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
        "JOIN runs er ON er.id = erl.run_id AND " + run_owner_sql + " "
        "WHERE erl.entity_id = e.id"
        "), 0) AS run_count, "
        "COALESCE(("
        "SELECT COUNT(DISTINCT eis.provider) FROM entity_intel_snapshots eis "
        "WHERE eis.session_id = ? AND eis.entity_id = e.id "
        "AND (eis.status = 'ok' OR eis.status = 'partial')"
        "), 0) AS intel_provider_count "
        ", COALESCE(("
        "SELECT " + provider_list_expr + " FROM entity_intel_snapshots eis "
        "WHERE eis.session_id = ? AND eis.entity_id = e.id "
        "AND (eis.status = 'ok' OR eis.status = 'partial')"
        "), '') AS intel_providers "
        ", COALESCE(("
        "SELECT MAX(eis.fetched_at) FROM entity_intel_snapshots eis "
        "WHERE eis.session_id = ? AND eis.entity_id = e.id "
        "AND (eis.status = 'ok' OR eis.status = 'partial')"
        "), '') AS intel_last_refreshed "
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        + entity_owner_sql
        + "AND COALESCE(e.suppressed, FALSE) = FALSE "
        + type_filter
        + (extra_where + " " if extra_where else "")
        + "ORDER BY e.type ASC, " + value_order_expr
    )


def _project_run_rows_to_items(conn, session_id, rows, *, team_id="", include_provenance=False):
    run_ids = [row["id"] for row in rows if row["id"]]
    finding_counts, artifact_counts = _project_run_count_maps(conn, session_id, run_ids, team_id=team_id)
    run_labels = _entity_labels_by_id(conn, session_id, "run", run_ids, team_id=team_id)
    run_notes = _entity_notes_by_id(conn, session_id, "run", run_ids, team_id=team_id)
    workflow_provenance = workflow_provenance_by_run(
        conn,
        [str(run_id) for run_id in run_ids],
        session_id=session_id,
        team_id=team_id,
    )
    runs = []
    for row in rows:
        item = _row_to_project_run(row, include_provenance=include_provenance)
        if not item:
            continue
        run_id = str(item["id"])
        item["finding_count"] = finding_counts.get(run_id, int(item.get("finding_count") or 0))
        item["artifact_count"] = artifact_counts.get(run_id, int(item.get("artifact_count") or 0))
        item["labels"] = run_labels.get(run_id, [])
        item["note"] = run_notes.get(run_id)
        apply_workflow_provenance(item, workflow_provenance.get(run_id))
        runs.append(item)
    return runs


def _project_entity_counts_by_type(conn, session_id, project_id, *, team_id=""):
    entity_owner_sql, entity_owner_params = _project_entity_owner_clause(session_id, team_id)
    rows = conn.execute(
        "SELECT e.type, COUNT(*) AS count "  # nosec
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        + entity_owner_sql
        + "AND COALESCE(e.suppressed, FALSE) = FALSE "
        "GROUP BY e.type",
        (project_id, *entity_owner_params),
    ).fetchall()
    return {str(row["type"] or ""): int(row["count"] or 0) for row in rows}


def _project_entity_rows_to_items(conn, session_id, rows, *, team_id="", include_provenance=False):
    entity_ids = [str(row["id"] or "") for row in rows if row["id"]]
    entity_labels = _entity_labels_by_id(conn, session_id, "atlas_entity", entity_ids, team_id=team_id)
    entity_notes = _entity_notes_by_id(conn, session_id, "atlas_entity", entity_ids, team_id=team_id)
    entities = []
    for row in rows:
        item = _row_to_target(row, include_provenance=include_provenance)
        if not item:
            continue
        item_id = str(item["id"])
        entities.append({
            **item,
            "labels": entity_labels.get(item_id, []),
            "note": entity_notes.get(item_id),
        })
    return entities


def _project_finding_scope(session_id, project_id, *, team_id=""):
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
    finding_owner_sql, finding_owner_params = _project_finding_owner_clause(session_id, team_id)
    entity_owner_sql, entity_owner_params = _project_entity_owner_clause(session_id, team_id)
    sql = (
        "SELECT fo.finding_id AS finding_id, "  # nosec
        "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
        "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN findings_occurrences fo ON fo.run_id = r.id "
        "JOIN findings f ON f.id = fo.finding_id "
        + finding_owner_sql
        + "AND COALESCE(f.suppressed, FALSE) = FALSE "
        "WHERE l.project_id = ? AND l.entity_type = 'run' "
        "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
        "UNION "
        "SELECT f.id AS finding_id, "
        "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
        "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN findings f ON 1 = 1 "
        + finding_owner_sql
        + "AND COALESCE(f.suppressed, FALSE) = FALSE "
        "AND (f.run_id = r.id OR f.first_run_id = r.id OR f.last_run_id = r.id) "
        "WHERE l.project_id = ? AND l.entity_type = 'run' "
        "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
        "UNION "
        "SELECT f.id AS finding_id, "
        "COALESCE(NULLIF(f.status, ''), 'new') AS review_state, "
        "COALESCE(NULLIF(f.severity, ''), 'info') AS severity "
        "FROM project_links l "
        "JOIN entities e ON e.id = l.entity_id "
        "JOIN findings f ON f.entity_id = e.id "
        + finding_owner_sql
        + "AND COALESCE(f.suppressed, FALSE) = FALSE "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        + entity_owner_sql
        + "AND COALESCE(e.suppressed, FALSE) = FALSE"
    )
    params = (
        *finding_owner_params,
        project_id,
        *run_owner_params,
        RUN_KIND_EXTERNAL,
        *finding_owner_params,
        project_id,
        *run_owner_params,
        RUN_KIND_EXTERNAL,
        *finding_owner_params,
        project_id,
        *entity_owner_params,
    )
    return sql, params


def _project_finding_metadata_count(conn, session_id, project_id, table, *, team_id=""):
    scope_sql, scope_params = _project_finding_scope(session_id, project_id, team_id=team_id)
    metadata_owner_sql, metadata_owner_params = _metadata_owner_where(session_id, team_id, table_alias="m")
    row = conn.execute(
        f"SELECT COUNT(DISTINCT m.id) AS count FROM {table} m "  # nosec
        "JOIN (SELECT DISTINCT finding_id FROM ("
        + scope_sql
        + ")) project_findings ON project_findings.finding_id = m.entity_id "
        "WHERE " + metadata_owner_sql + " AND m.entity_type = 'finding'",
        (*scope_params, *metadata_owner_params),
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _project_finding_summary_rows(conn, session_id, project_id, *, team_id=""):
    scope_sql, scope_params = _project_finding_scope(session_id, project_id, team_id=team_id)
    return conn.execute(
        "WITH project_findings AS ("  # nosec
        + scope_sql
        + """)
        SELECT review_state, severity, COUNT(DISTINCT finding_id) AS count
        FROM project_findings
        GROUP BY review_state, severity
        """,
        scope_params,
    ).fetchall()




def get_project_summary(session_id, project_id, *, team_id="", include_provenance=False):
    with get_db_connect()() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
        project_select_prefix = "SELECT "
        project_where_prefix = " FROM projects WHERE "
        project_id_suffix = " AND id = ?"
        project_sql = (
            project_select_prefix
            + project_select_columns()
            + project_where_prefix
            + owner_sql
            + project_id_suffix
        )
        project_row = conn.execute(
            project_sql,
            (*owner_params, project_id),
        ).fetchone()
        if not project_row:
            return None
        project = _row_to_project(project_row)
        _attach_project_notes(conn, session_id, [project], team_id=team_id)
        _attach_project_labels(conn, session_id, [project], team_id=team_id)
        entity_owner_sql, entity_owner_params = _project_entity_owner_clause(session_id, team_id)
        metadata_session = metadata_owner_id(session_id, team_id)
        run_link_rows = conn.execute(
            "SELECT l.id, l.project_id, l.entity_type, l.entity_id, l.source, l.created, "
            "l.confidence, l.review_state, l.source_detail "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
            "ORDER BY l.created DESC",
            (project_id, *run_owner_params, RUN_KIND_EXTERNAL),
        ).fetchall()
        atlas_link_rows = conn.execute(
            "SELECT l.id, l.project_id, l.entity_type, l.entity_id, l.source, l.created, "  # nosec
            "l.confidence, l.review_state, l.source_detail "
            "FROM project_links l JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
            + entity_owner_sql
            + "AND COALESCE(e.suppressed, FALSE) = FALSE "
            "ORDER BY l.created DESC",
            (project_id, *entity_owner_params),
        ).fetchall()
        link_rows = [*run_link_rows, *atlas_link_rows]
        target_rows = conn.execute(
            _project_atlas_entity_select_sql(target_only=True, team_id=team_id) + " LIMIT ?",
            (*run_owner_params, metadata_session, metadata_session, metadata_session, project_id, *entity_owner_params, 200),
        ).fetchall()
        run_ids = [row["entity_id"] for row in run_link_rows if row["entity_type"] == "run"]
        entity_id_rows = conn.execute(
            "SELECT e.id, e.type "  # nosec
            "FROM project_links l JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
            + entity_owner_sql
            + "AND COALESCE(e.suppressed, FALSE) = FALSE",
            (project_id, *entity_owner_params),
        ).fetchall()
        entity_ids = [row["id"] for row in entity_id_rows]
        entity_counts_by_type = _project_entity_counts_by_type(conn, session_id, project_id, team_id=team_id)
        target_count_rows = conn.execute(
            "SELECT l.review_state, COUNT(*) AS count "  # nosec
            "FROM project_links l JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
            + entity_owner_sql
            + "AND COALESCE(e.suppressed, FALSE) = FALSE "
            "AND e.type IN ('domain', 'ip', 'url') "
            "GROUP BY l.review_state",
            (project_id, *entity_owner_params),
        ).fetchall()
        target_counts_by_review = {
            str(row["review_state"] or "confirmed"): int(row["count"] or 0)
            for row in target_count_rows
        }
        artifact_id_rows = []
        finding_count = 0
        finding_summary = _empty_project_finding_summary()
        run_rows = []
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            run_rows = conn.execute(
                "SELECT r.id, r.command, r.started, r.finished, r.exit_code, r.output_line_count, "
                "r.full_output_available, r.full_output_truncated, "
                "art.byte_size AS output_artifact_byte_size, "
                "art.line_count AS output_artifact_line_count, "
                "l.id AS link_id, l.confidence AS link_confidence, "
                "l.review_state AS link_review_state, l.source_detail AS link_source_detail, "
                "l.created, l.source AS link_source "
                "FROM project_links l JOIN runs r ON r.id = l.entity_id "
                "LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
                "WHERE l.project_id = ? AND l.entity_type = 'run' AND " + run_owner_sql + " "  # nosec
                "AND r.run_kind = ? "
                "ORDER BY r.started DESC, l.created DESC",
                (project_id, *run_owner_params, RUN_KIND_EXTERNAL),
            ).fetchall()
            artifact_id_rows = conn.execute(
                "SELECT id "
                f"FROM run_file_artifacts WHERE run_id IN ({placeholders}) ",  # nosec
                run_ids,
            ).fetchall()
        finding_rows = _project_finding_summary_rows(conn, session_id, project_id, team_id=team_id)
        artifact_ids = [row["id"] for row in artifact_id_rows]
        for row in finding_rows:
            count = int(row["count"] or 0)
            finding_count += count
            _add_finding_summary_count(
                finding_summary,
                review_state=row["review_state"],
                severity=row["severity"],
                count=count,
            )
        target_ids = [row["id"] for row in target_rows]
        package_where = "project_id = ?"
        package_params = [project_id]
        if not team_id:
            package_where += " AND session_id = ?"
            package_params.append(session_id)
        package_rows = conn.execute(
            "SELECT id FROM evidence_packages WHERE " + package_where,  # nosec
            package_params,
        ).fetchall()
        package_ids = [row["id"] for row in package_rows]
        target_labels = _entity_labels_by_id(conn, session_id, "atlas_entity", target_ids, team_id=team_id)
        target_notes = _entity_notes_by_id(conn, session_id, "atlas_entity", target_ids, team_id=team_id)
        label_count = (
            _count_entity_metadata_for_ids(conn, "entity_labels", "project", [project_id], session_id=session_id, team_id=team_id)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "run", run_ids, session_id=session_id, team_id=team_id)
            + _count_entity_metadata_for_ids(
                conn,
                "entity_labels",
                "run_file_artifact",
                artifact_ids,
                session_id=session_id,
                team_id=team_id,
            )
            + _project_finding_metadata_count(conn, session_id, project_id, "entity_labels", team_id=team_id)
            + _count_entity_metadata_for_ids(
                conn,
                "entity_labels",
                "atlas_entity",
                entity_ids,
                session_id=session_id,
                team_id=team_id,
            )
            + _count_entity_metadata_for_ids(conn, "entity_labels", "target", target_ids, session_id=session_id, team_id=team_id)
            + _count_entity_metadata_for_ids(
                conn,
                "entity_labels",
                "package",
                package_ids,
                session_id=session_id,
                team_id=team_id,
            )
        )
        note_count = (
            _count_entity_metadata_for_ids(conn, "entity_notes", "project", [project_id], session_id=session_id, team_id=team_id)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "run", run_ids, session_id=session_id, team_id=team_id)
            + _count_entity_metadata_for_ids(
                conn,
                "entity_notes",
                "run_file_artifact",
                artifact_ids,
                session_id=session_id,
                team_id=team_id,
            )
            + _project_finding_metadata_count(conn, session_id, project_id, "entity_notes", team_id=team_id)
            + _count_entity_metadata_for_ids(
                conn,
                "entity_notes",
                "atlas_entity",
                entity_ids,
                session_id=session_id,
                team_id=team_id,
            )
            + _count_entity_metadata_for_ids(conn, "entity_notes", "target", target_ids, session_id=session_id, team_id=team_id)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "package", package_ids, session_id=session_id, team_id=team_id)
        )
        run_items = _project_run_rows_to_items(
            conn,
            session_id,
            run_rows,
            team_id=team_id,
            include_provenance=include_provenance,
        )
    links = [_row_to_link(row, include_provenance=include_provenance) for row in link_rows]
    targets = []
    for item in (_row_to_target(row, include_provenance=include_provenance) for row in target_rows):
        if not item:
            continue
        item_id = str(item["id"])
        targets.append({
            **item,
            "labels": target_labels.get(item_id, []),
            "note": target_notes.get(item_id),
        })
    pending_target_count = target_counts_by_review.get("pending", 0)
    confirmed_target_count = sum(count for state, count in target_counts_by_review.items() if state != "pending")
    runs = run_items
    packages = list_evidence_packages(session_id, project_id, team_id=team_id) or []
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
            "findings": finding_count,
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


def _project_entity_filter_clause(conn, session_id, project_id, filters, *, team_id=""):
    filters = filters if isinstance(filters, dict) else {}
    run_ids = set(_metadata_filter_values(filters, "run_id", MAX_ENTITY_ID_LEN))
    target_ids = _metadata_filter_values(filters, "target_id", MAX_ENTITY_ID_LEN)
    host_entity_ids = _metadata_filter_values(filters, "host_entity_id", MAX_ENTITY_ID_LEN)
    target_run_ids = _project_target_filter_run_ids(conn, session_id, project_id, target_ids, team_id=team_id)
    candidate_run_ids = None
    if run_ids:
        candidate_run_ids = set(run_ids)
    if target_run_ids is not None:
        candidate_run_ids = set(target_run_ids) if candidate_run_ids is None else candidate_run_ids.intersection(target_run_ids)
    if candidate_run_ids is None and not target_ids and not host_entity_ids:
        return "", []
    if candidate_run_ids is not None and not candidate_run_ids and not target_ids and not host_entity_ids:
        return "AND 1 = 0", []

    clauses = []
    params = []
    if candidate_run_ids:
        run_owner_sql, run_owner_params = shared_owner_where(
            session_id,
            team_id=team_id,
            table_alias="filtered_run",
        )
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
            "AND " + run_owner_sql + " "  # nosec
            "AND filtered_run.run_kind = ? "
            f"AND filtered_erl.run_id IN ({run_placeholders})"  # nosec
            ")"
        )
        params.extend([project_id, *run_owner_params, RUN_KIND_EXTERNAL, *ordered_run_ids])
    if target_ids:
        target_placeholders = ",".join("?" for _ in target_ids)
        clauses.append(f"e.id IN ({target_placeholders})")  # nosec
        params.extend(target_ids)
    if host_entity_ids:
        host_placeholders = ",".join("?" for _ in host_entity_ids)
        clauses.append(f"e.host_entity_id IN ({host_placeholders})")  # nosec
        params.extend(host_entity_ids)
    if not clauses:
        return "AND 1 = 0", []
    return "AND (" + " OR ".join(clauses) + ")", params


def list_project_entities(session_id, project_id, filters=None, *, entity_type="", limit=50, offset=0, team_id=""):
    safe_limit, safe_offset = _normalize_page_window(limit, offset)
    normalized_type = _trim_text(entity_type, 32).lower()
    with get_db_connect()() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project_row = conn.execute(
            "SELECT 1 FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        ).fetchone()
        if not project_row:
            return None
        filter_sql, filter_params = _project_entity_filter_clause(
            conn,
            session_id,
            project_id,
            filters,
            team_id=team_id,
        )
        entity_owner_sql, entity_owner_params = _project_entity_owner_clause(session_id, team_id)
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="er")
        metadata_session = metadata_owner_id(session_id, team_id)
        counts_by_type = {}
        for row in conn.execute(
            "SELECT e.type, COUNT(*) AS count "  # nosec
            "FROM project_links l JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
            + entity_owner_sql
            + "AND COALESCE(e.suppressed, FALSE) = FALSE "
            + filter_sql
            + " GROUP BY e.type",
            (project_id, *entity_owner_params, *filter_params),
        ).fetchall():
            counts_by_type[str(row["type"] or "")] = int(row["count"] or 0)
        total = int(counts_by_type.get(normalized_type, 0)) if normalized_type else sum(counts_by_type.values())
        params = [*run_owner_params, metadata_session, metadata_session, metadata_session, project_id, *entity_owner_params]
        if normalized_type:
            params.append(normalized_type)
        rows = conn.execute(
            _project_atlas_entity_select_sql(
                entity_type=normalized_type,
                extra_where=filter_sql,
                team_id=team_id,
            )
            + " LIMIT ? OFFSET ?",
            (*params, *filter_params, safe_limit, safe_offset),
        ).fetchall()
        entities = _project_entity_rows_to_items(conn, session_id, rows, team_id=team_id)
    return _project_entity_page_payload(entities, total, safe_limit, safe_offset, counts_by_type)




def list_project_runs(session_id, project_id, *, limit=50, offset=0, team_id="", include_provenance=False, query=""):
    safe_limit, safe_offset = _normalize_page_window(limit, offset)
    search = _trim_text(query, 256).lower()
    search_like = f"%{search}%"
    with get_db_connect()() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
        project_row = conn.execute(
            "SELECT 1 FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        ).fetchone()
        if not project_row:
            return None
        total_row = conn.execute(
            "SELECT COUNT(*) AS count "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
            "AND (? = '' OR LOWER(COALESCE(r.command, '')) LIKE ? OR LOWER(r.id) LIKE ?) ",
            (project_id, *run_owner_params, RUN_KIND_EXTERNAL, search, search_like, search_like),
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        rows = conn.execute(
            "SELECT r.id, r.command, r.started, r.finished, r.exit_code, r.output_line_count, "
            "r.full_output_available, r.full_output_truncated, "
            "art.byte_size AS output_artifact_byte_size, "
            "art.line_count AS output_artifact_line_count, "
            "l.id AS link_id, l.confidence AS link_confidence, "
            "l.review_state AS link_review_state, l.source_detail AS link_source_detail, "
            "l.created, l.source AS link_source "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' AND " + run_owner_sql + " "  # nosec
            "AND r.run_kind = ? "
            "AND (? = '' OR LOWER(COALESCE(r.command, '')) LIKE ? OR LOWER(r.id) LIKE ?) "
            "ORDER BY r.started DESC, l.created DESC, r.id DESC, l.id DESC "
            "LIMIT ? OFFSET ?",
            (project_id, *run_owner_params, RUN_KIND_EXTERNAL, search, search_like, search_like, safe_limit, safe_offset),
        ).fetchall()
        runs = _project_run_rows_to_items(
            conn,
            session_id,
            rows,
            team_id=team_id,
            include_provenance=include_provenance,
        )
    return _page_payload("runs", runs, total, safe_limit, safe_offset)
