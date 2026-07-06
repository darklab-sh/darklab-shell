"""Project artifact read/query helpers."""

from __future__ import annotations

from core.database_access import get_db_connect
from services.projects.actors import actor_for_session as _actor_for_session
from services.projects.actors import team_actor_map as _team_actor_map
from services.projects.artifacts import (
    artifact_availability as _artifact_availability,
    artifact_owner_context as _artifact_owner_context,
    row_to_run_file_artifact as _row_to_run_file_artifact,
)
from services.projects.contracts import MAX_ENTITY_ID_LEN
from services.projects.metadata import _entity_labels_by_id, _entity_notes_by_id
from services.projects.scope import shared_owner_where
from services.projects.utils import (
    metadata_filter_values as _metadata_filter_values,
    normalize_page_window as _normalize_page_window,
    page_payload as _page_payload,
    trim_text as _trim_text,
)
from services.runs.kinds import RUN_KIND_EXTERNAL


def _project_entity_owner_clause(session_id, team_id="", *, table_alias="e"):
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias=table_alias)
    return f" AND {owner_sql} ", owner_params


def _project_finding_owner_clause(session_id, team_id="", *, table_alias="f"):
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias=table_alias)
    return f" AND {owner_sql} ", owner_params


def _project_artifact_rows_to_items(session_id, conn, rows, *, team_id=""):
    artifact_ids = [str(row["id"] or "") for row in rows if row["id"]]
    artifact_labels = _entity_labels_by_id(conn, session_id, "run_file_artifact", artifact_ids, team_id=team_id)
    artifact_notes = _entity_notes_by_id(conn, session_id, "run_file_artifact", artifact_ids, team_id=team_id)
    actors = _team_actor_map(conn, team_id, [row["session_id"] for row in rows if row["session_id"]])
    artifacts = []
    for row in rows:
        item = _row_to_run_file_artifact(row)
        if not item:
            continue
        item_id = str(item["id"])
        artifact_owner_session = str(item.get("session_id") or session_id)
        owner_context = _artifact_owner_context(artifact_owner_session, item)
        artifact = {
            **item,
            **_artifact_availability(artifact_owner_session, item, owner_context=owner_context),
            "labels": artifact_labels.get(item_id, []),
            "note": artifact_notes.get(item_id),
        }
        actor = _actor_for_session(item.get("session_id"), actors)
        if actor:
            artifact["created_by"] = actor
        artifacts.append(artifact)
    return artifacts


def _project_artifact_page_payload(artifacts, total, limit, offset, run_counts=None):
    return _page_payload(
        "artifacts",
        artifacts,
        total,
        limit,
        offset,
        extra={"run_counts": run_counts if isinstance(run_counts, dict) else {}},
    )


def _project_target_filter_run_ids(conn, session_id, project_id, target_ids, *, team_id=""):
    ids = [str(target_id) for target_id in target_ids if target_id]
    if not ids:
        return None
    placeholders = ",".join("?" for _ in ids)
    entity_owner_sql, entity_owner_params = _project_entity_owner_clause(session_id, team_id)
    finding_owner_sql, finding_owner_params = _project_finding_owner_clause(session_id, team_id)
    target_rows = conn.execute(
        "SELECT e.id, e.canonical_value "  # nosec
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        + entity_owner_sql
        + "AND COALESCE(e.suppressed, FALSE) = FALSE "
        f"AND e.id IN ({placeholders})",  # nosec
        (project_id, *entity_owner_params, *ids),
    ).fetchall()
    if len(target_rows) != len(ids):
        return set()
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
    run_ids = set()
    for row in target_rows:
        value = str(row["canonical_value"] or "").strip().lower()
        if not value:
            continue
        direct_rows = conn.execute(
            "SELECT l.entity_id AS run_id "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
            "AND LOWER(r.command) LIKE ?",
            (project_id, *run_owner_params, RUN_KIND_EXTERNAL, f"%{value}%"),
        ).fetchall()
        run_ids.update(str(run["run_id"] or "") for run in direct_rows if run["run_id"])
    finding_rows = conn.execute(
        "WITH project_runs AS ("
        "  SELECT l.entity_id AS run_id FROM project_links l "
        "  JOIN runs r ON r.id = l.entity_id "
        "  WHERE l.project_id = ? AND l.entity_type = 'run' "
        "  AND " + run_owner_sql + " AND r.run_kind = ?"  # nosec
        "), target_findings AS ("
        "  SELECT f.id, f.run_id, f.first_run_id, f.last_run_id "
        "  FROM findings f WHERE 1 = 1 "
        + finding_owner_sql
        + f"  AND COALESCE(f.entity_id, f.target_id) IN ({placeholders})"  # nosec
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
        (project_id, *run_owner_params, RUN_KIND_EXTERNAL, *finding_owner_params, *ids),
    ).fetchall()
    run_ids.update(str(row["run_id"] or "") for row in finding_rows if row["run_id"])
    return run_ids


def list_project_artifacts(session_id, project_id, filters=None, *, limit=50, offset=0, team_id=""):
    filters = filters if isinstance(filters, dict) else {}
    safe_limit, safe_offset = _normalize_page_window(limit, offset)
    search = _trim_text(filters.get("q") or filters.get("query") or "", 128).lower()
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
        linked_run_rows = conn.execute(
            "SELECT l.entity_id AS run_id "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND " + run_owner_sql + " AND r.run_kind = ?",  # nosec
            (project_id, *run_owner_params, RUN_KIND_EXTERNAL),
        ).fetchall()
        allowed_run_ids = {str(row["run_id"] or "") for row in linked_run_rows if row["run_id"]}
        run_ids = _metadata_filter_values(filters, "run_id", MAX_ENTITY_ID_LEN)
        if run_ids:
            candidate_run_ids = allowed_run_ids.intersection(run_ids)
        else:
            candidate_run_ids = set(allowed_run_ids)
        target_ids = _metadata_filter_values(filters, "target_id", MAX_ENTITY_ID_LEN)
        target_run_ids = _project_target_filter_run_ids(conn, session_id, project_id, target_ids, team_id=team_id)
        if target_run_ids is not None:
            candidate_run_ids = candidate_run_ids.intersection(target_run_ids)
        if not candidate_run_ids:
            return _project_artifact_page_payload([], 0, safe_limit, safe_offset, {})
        ordered_run_ids = sorted(candidate_run_ids)
        placeholders = ",".join("?" for _ in ordered_run_ids)
        artifact_search_sql = (
            "AND (? = '' OR LOWER(COALESCE(display_name, '')) LIKE ? "
            "OR LOWER(COALESCE(workspace_path, '')) LIKE ? "
            "OR LOWER(COALESCE(kind, '')) LIKE ?) "
        )
        count_rows = conn.execute(
            "SELECT run_id, COUNT(*) AS count FROM run_file_artifacts "  # nosec
            f"WHERE run_id IN ({placeholders}) "  # nosec
            + artifact_search_sql +
            "GROUP BY run_id",
            (*ordered_run_ids, search, search_like, search_like, search_like),
        ).fetchall()
        run_counts = {str(row["run_id"] or ""): int(row["count"] or 0) for row in count_rows}
        total = sum(run_counts.values())
        rows = conn.execute(
            "SELECT a.id, a.session_id, a.run_id, a.workspace_path, a.display_name, a.kind, a.byte_size, "  # nosec
            "a.detected_by, a.content_type, a.preview_type, a.content_sha256, a.created, "
            "r.team_id AS run_team_id "
            "FROM run_file_artifacts a JOIN runs r ON r.id = a.run_id "
            f"WHERE a.run_id IN ({placeholders}) "  # nosec
            "AND (? = '' OR LOWER(COALESCE(a.display_name, '')) LIKE ? "
            "OR LOWER(COALESCE(a.workspace_path, '')) LIKE ? "
            "OR LOWER(COALESCE(a.kind, '')) LIKE ?) "
            "ORDER BY a.created DESC, a.id DESC "
            "LIMIT ? OFFSET ?",
            (*ordered_run_ids, search, search_like, search_like, search_like, safe_limit, safe_offset),
        ).fetchall()
        artifacts = _project_artifact_rows_to_items(session_id, conn, rows, team_id=team_id)
    return _project_artifact_page_payload(artifacts, total, safe_limit, safe_offset, run_counts)


def _list_all_project_artifacts(session_id, project_id, *, team_id=""):
    artifacts = []
    offset = 0
    while True:
        page = list_project_artifacts(session_id, project_id, {}, limit=200, offset=offset, team_id=team_id)
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


def get_project_run_file_artifact(session_id, project_id, artifact_id, *, team_id=""):
    artifact_id = _trim_text(artifact_id, MAX_ENTITY_ID_LEN)
    if not artifact_id:
        return None
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
        row = conn.execute(
            "SELECT a.id, a.session_id, a.run_id, a.workspace_path, a.display_name, a.kind, "
            "a.byte_size, a.detected_by, a.content_type, a.preview_type, a.content_sha256, a.created, "
            "r.team_id AS run_team_id "
            "FROM run_file_artifacts a "
            "JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = a.run_id "
            "JOIN projects p ON p.id = l.project_id "
            "JOIN runs r ON r.id = a.run_id "
            "WHERE " + project_owner_sql + " AND p.id = ? AND a.id = ? "  # nosec
            "AND " + run_owner_sql,
            (*project_owner_params, project_id, artifact_id, *run_owner_params),
        ).fetchone()
        actors = _team_actor_map(conn, team_id, [row["session_id"]] if row else [])
    artifact = _row_to_run_file_artifact(row)
    if not artifact:
        return None
    artifact_owner_session = str(artifact.get("session_id") or session_id)
    owner_context = _artifact_owner_context(artifact_owner_session, artifact)
    result = {
        **artifact,
        **_artifact_availability(artifact_owner_session, artifact, owner_context=owner_context),
    }
    actor = _actor_for_session(artifact.get("session_id"), actors)
    if actor:
        result["created_by"] = actor
    return result
