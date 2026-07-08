"""
Project link mutation helpers.
"""

from __future__ import annotations

import config as _config
from core.database import (
    validate_project_entity_type,
    validate_project_link_source,
)
from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.atlas.scope import entity_exists_in_scope
from services.projects.contracts import (
    ACTIVE_PROJECT_PREF_KEY,
    MAX_BULK_RUN_ACTION_ITEMS,
    MAX_ENTITY_ID_LEN,
    PROJECT_LINK_ENTITY_TYPES,
    ProjectWorkspaceError,
    ProjectWorkspaceNotFound,
)
from services.projects.models import (
    PROJECT_TARGET_SOURCE_DETAIL_FLAG,
    row_to_link as _row_to_link,
)
from services.projects.preferences import (
    clear_active_project_preference as _clear_active_project_preference,
    load_session_preferences as _load_session_preferences,
    project_auto_link_external_runs_enabled as _project_auto_link_external_runs_enabled,
    project_auto_link_run_entities_enabled as _project_auto_link_run_entities_enabled,
    save_session_preferences as _save_session_preferences,
)
from services.projects.scope import shared_owner_where
from services.projects.utils import (
    new_project_link_id as _new_project_link_id,
    now as _now,
    quota_exceeded as _quota_exceeded,
    raise_quota as _raise_quota,
    trim_text as _trim_text,
)
from services.runs.kinds import RUN_KIND_EXTERNAL, is_project_linkable_run_kind, normalize_run_kind
from services.workspace.files import WorkspaceError, resolve_workspace_path


def _cfg_limit(key, default):
    try:
        value = int(_config.CFG.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(0, value)


def _quota_budget(count, key, default):
    limit = _cfg_limit(key, default)
    if limit <= 0:
        return None
    return max(0, limit - count)


def _budget_available(*budgets):
    return all(budget is None or budget > 0 for budget in budgets)


def _consume_budget(budget):
    return None if budget is None else max(0, budget - 1)


def _active_project_preference_key(team_id=""):
    normalized_team_id = str(team_id or "").strip()
    if normalized_team_id:
        return f"{ACTIVE_PROJECT_PREF_KEY}:{normalized_team_id}"
    return ACTIVE_PROJECT_PREF_KEY


def _project_link_count(conn, project_id, *, entity_type=None):
    if entity_type:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_links WHERE project_id = ? AND entity_type = ?",
            (project_id, entity_type),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_links WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    return int(row["count"] or 0) if row else 0


def _project_link_budgets(conn, project_id, entity_type):
    link_budget = _quota_budget(
        _project_link_count(conn, project_id),
        "max_project_links_per_project",
        5000,
    )
    entity_budget = None
    if entity_type == "atlas_entity":
        entity_budget = _quota_budget(
            _project_link_count(conn, project_id, entity_type="atlas_entity"),
            "max_project_entities_per_project",
            5000,
        )
    return link_budget, entity_budget


def link_run_to_active_project(conn, session_id, run_id, *, team_id=""):
    if not _project_auto_link_external_runs_enabled(conn, session_id):
        return None
    preferences = _load_session_preferences(conn, session_id)
    preference_key = _active_project_preference_key(team_id)
    project_id = str(preferences.get(preference_key) or "")
    if not project_id:
        return None
    project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
    project = conn.execute(
        "SELECT id, name, slug FROM projects "
        "WHERE " + project_owner_sql + " AND id = ? AND status != 'archived'",  # nosec
        (*project_owner_params, project_id),
    ).fetchone()
    if not project:
        if preference_key == ACTIVE_PROJECT_PREF_KEY:
            _clear_active_project_preference(conn, session_id)
        else:
            preferences.pop(preference_key, None)
            _save_session_preferences(conn, session_id, preferences)
        return None
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id)
    run = conn.execute(
        "SELECT command, run_kind FROM runs WHERE " + run_owner_sql + " AND id = ?",  # nosec
        (*run_owner_params, run_id),
    ).fetchone()
    if not run:
        return None
    run_kind = normalize_run_kind(run["run_kind"], command=str(run["command"] or ""))
    if not is_project_linkable_run_kind(run_kind):
        return None
    created = _now()
    for _ in range(10):
        link_id = _new_project_link_id()
        conn.execute(
            "INSERT INTO project_links "
            "(id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, 'active_project', ?) "
            "ON CONFLICT(project_id, entity_type, entity_id) DO NOTHING",
            (link_id, project_id, run_id, created),
        )
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = 'run' AND entity_id = ?",
            (project_id, run_id),
        ).fetchone()
        if row:
            link = _row_to_link(row)
            if link is not None:
                link["project_name"] = project["name"] or project["slug"] or project["id"]
            return link
    raise ProjectWorkspaceError("could not allocate an active project link id")


def link_run_to_project_on_conn(conn, session_id, project_id, run_id, *, source="manual", team_id=""):
    source = validate_project_link_source(source)
    project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id)
    project = conn.execute(
        "SELECT id, name, slug FROM projects "
        "WHERE " + project_owner_sql + " AND id = ? AND status != 'archived'",  # nosec
        (*project_owner_params, project_id),
    ).fetchone()
    if not project:
        raise ProjectWorkspaceNotFound("project not found")
    run = conn.execute(
        "SELECT command, run_kind FROM runs WHERE " + run_owner_sql + " AND id = ?",  # nosec
        (*run_owner_params, run_id),
    ).fetchone()
    if not run:
        raise ProjectWorkspaceNotFound("run not found")
    run_kind = normalize_run_kind(run["run_kind"], command=str(run["command"] or ""))
    if not is_project_linkable_run_kind(run_kind):
        raise ProjectWorkspaceError("project links only support external runs")
    row = conn.execute(
        "SELECT id, project_id, entity_type, entity_id, source, created "
        "FROM project_links WHERE project_id = ? AND entity_type = 'run' AND entity_id = ?",
        (project_id, run_id),
    ).fetchone()
    if row:
        link = _row_to_link(row)
        if link is not None:
            link["project_name"] = project["name"] or project["slug"] or project["id"]
        return link
    if _quota_exceeded(
        _project_link_count(conn, project_id),
        "max_project_links_per_project",
        5000,
    ):
        _raise_quota("project link quota exceeded for this project")
    created = _now()
    for _ in range(10):
        link_id = _new_project_link_id()
        conn.execute(
            "INSERT INTO project_links "
            "(id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, ?, ?) "
            "ON CONFLICT(project_id, entity_type, entity_id) DO NOTHING",
            (link_id, project_id, run_id, source, created),
        )
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = 'run' AND entity_id = ?",
            (project_id, run_id),
        ).fetchone()
        if row:
            link = _row_to_link(row)
            if link is not None:
                link["project_name"] = project["name"] or project["slug"] or project["id"]
            return link
    raise ProjectWorkspaceError("could not allocate a project link id")


def link_active_project_run_entities(conn, session_id, project_id, run_id, *, team_id=""):
    if not _project_auto_link_run_entities_enabled(conn, session_id):
        return None
    return _link_project_run_entities_on_conn(
        conn,
        session_id,
        project_id,
        [run_id],
        source="active_project",
        team_id=team_id,
    )


def _insert_project_link(
    conn,
    project_id,
    entity_type,
    entity_id,
    source,
    *,
    confidence=1.0,
    review_state="confirmed",
    source_detail=None,
):
    entity_type = validate_project_entity_type(entity_type)
    source = validate_project_link_source(source)
    created = _now()
    detail_json = dialect_for_backend(get_db_backend()).json_param(source_detail if isinstance(source_detail, dict) else {})
    for _ in range(10):
        link_id = _new_project_link_id()
        conn.execute(
            "INSERT INTO project_links "
            "(id, project_id, entity_type, entity_id, source, confidence, review_state, source_detail, updated, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id, entity_type, entity_id) DO NOTHING",
            (link_id, project_id, entity_type, entity_id, source, confidence, review_state, detail_json, created, created),
        )
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            (project_id, entity_type, entity_id),
        ).fetchone()
        if row:
            return _row_to_link(row)
    raise ProjectWorkspaceError("could not allocate a project link id")


def insert_project_link_with_quota(
    conn,
    project_id,
    entity_type,
    entity_id,
    source,
    *,
    confidence=1.0,
    review_state="confirmed",
    source_detail=None,
):
    entity_type = validate_project_entity_type(entity_type)
    row = conn.execute(
        "SELECT id, project_id, entity_type, entity_id, source, created "
        "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
        (project_id, entity_type, entity_id),
    ).fetchone()
    if row:
        return _row_to_link(row)
    if _quota_exceeded(
        _project_link_count(conn, project_id),
        "max_project_links_per_project",
        5000,
    ):
        _raise_quota("project link quota exceeded for this project")
    if entity_type == "atlas_entity" and _quota_exceeded(
        _project_link_count(conn, project_id, entity_type="atlas_entity"),
        "max_project_entities_per_project",
        5000,
    ):
        _raise_quota("project entity quota exceeded for this project")
    return _insert_project_link(
        conn,
        project_id,
        entity_type,
        entity_id,
        source,
        confidence=confidence,
        review_state=review_state,
        source_detail=source_detail,
    )


def _run_entity_ids_for_project_link(conn, session_id, run_ids, *, team_id=""):
    normalized_run_ids = [str(run_id or "").strip() for run_id in run_ids]
    normalized_run_ids = [run_id for run_id in normalized_run_ids if run_id]
    if not normalized_run_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_run_ids)
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
    rows = conn.execute(
        "SELECT linked.id "
        "FROM ("
        "  SELECT e.id, MAX(e.last_seen_at) AS sort_seen_at, MIN(e.canonical_value) AS sort_value "
        "  FROM entity_run_links erl "
        "  JOIN entities e ON e.id = erl.entity_id "
        "  JOIN runs r ON r.id = erl.run_id "
        "  WHERE " + run_owner_sql + " AND e.session_id = ? "  # nosec
        f"  AND erl.run_id IN ({placeholders}) "
        "  GROUP BY e.id"
        ") linked "
        "ORDER BY linked.sort_seen_at DESC, linked.sort_value ASC",
        [*run_owner_params, session_id, *normalized_run_ids],
    ).fetchall()
    return [str(row["id"]) for row in rows if row["id"]]


def _normalize_project_run_ids_payload(data):
    raw_run_ids = data.get("run_ids") if isinstance(data, dict) else None
    if raw_run_ids is None and isinstance(data, dict):
        raw_run_ids = [data.get("run_id")]
    if not isinstance(raw_run_ids, list):
        raise ProjectWorkspaceError("run_ids must be a list")
    if len(raw_run_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        raise ProjectWorkspaceError("too_many")
    run_ids = []
    seen = set()
    for raw_run_id in raw_run_ids:
        run_id = _trim_text(raw_run_id, MAX_ENTITY_ID_LEN)
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        run_ids.append(run_id)
    if not run_ids:
        raise ProjectWorkspaceError("run_ids is required")
    return run_ids


def _project_run_entity_link_stats(conn, project_id, entity_ids):
    stats = {
        "available": len(entity_ids),
        "added": 0,
        "already_linked": 0,
        "rejected": 0,
        "linkable": 0,
    }
    if not entity_ids:
        return stats
    placeholders = ",".join("?" for _ in entity_ids)
    linked_rows = conn.execute(
        "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' "  # nosec
        f"AND entity_id IN ({placeholders})",
        [project_id, *entity_ids],
    ).fetchall()
    linked_ids = {str(row["entity_id"]) for row in linked_rows}
    stats["already_linked"] = len(linked_ids)
    stats["linkable"] = max(0, len(entity_ids) - len(linked_ids))
    return stats


def _project_visible_finding_ids(conn, session_id, project_id, *, excluded_run_ids=None, excluded_entity_ids=None):
    run_ids = [str(run_id or "") for run_id in (excluded_run_ids or []) if str(run_id or "")]
    entity_ids = [str(entity_id or "") for entity_id in (excluded_entity_ids or []) if str(entity_id or "")]
    run_exclusion_sql = ""
    entity_exclusion_sql = ""
    params = [project_id, session_id]
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        run_exclusion_sql = f" AND l.entity_id NOT IN ({placeholders})"  # nosec
        params.extend(run_ids)
    params.extend([project_id, session_id])
    if entity_ids:
        placeholders = ",".join("?" for _ in entity_ids)
        entity_exclusion_sql = f" AND l.entity_id NOT IN ({placeholders})"  # nosec
        params.extend(entity_ids)
    params.append(session_id)
    rows = conn.execute(
        "WITH project_runs AS ("
        "  SELECT l.entity_id AS run_id FROM project_links l "
        "  JOIN runs r ON r.id = l.entity_id "
        "  WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ?"
        + run_exclusion_sql +  # nosec B608
        "), project_entities AS ("
        "  SELECT l.entity_id FROM project_links l "
        "  JOIN entities e ON e.id = l.entity_id "
        "  WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND e.session_id = ?"
        + entity_exclusion_sql +  # nosec B608
        ") "
        "SELECT DISTINCT f.id FROM findings f "
        "WHERE f.session_id = ? AND COALESCE(f.suppressed, FALSE) = FALSE AND ("
        "  EXISTS ("
        "    SELECT 1 FROM findings_occurrences scope_fo "
        "    JOIN project_runs pr ON pr.run_id = scope_fo.run_id "
        "    WHERE scope_fo.finding_id = f.id"
        "  ) "
        "  OR EXISTS ("
        "    SELECT 1 FROM project_runs pr "
        "    WHERE pr.run_id = f.run_id OR pr.run_id = f.first_run_id OR pr.run_id = f.last_run_id"
        "  ) "
        "  OR EXISTS ("
        "    SELECT 1 FROM project_entities pe "
        "    WHERE pe.entity_id = COALESCE(f.entity_id, f.target_id)"
        "  )"
        ")",
        params,
    ).fetchall()
    return {str(row["id"]) for row in rows if row["id"]}


def _attach_project_run_entity_unlink_finding_stats(conn, stats, session_id, project_id, run_ids, removable_ids, curated_ids):
    current_finding_ids = _project_visible_finding_ids(conn, session_id, project_id)
    after_run_finding_ids = _project_visible_finding_ids(
        conn,
        session_id,
        project_id,
        excluded_run_ids=run_ids,
    )
    after_removable_finding_ids = _project_visible_finding_ids(
        conn,
        session_id,
        project_id,
        excluded_run_ids=run_ids,
        excluded_entity_ids=removable_ids,
    )
    after_curated_finding_ids = _project_visible_finding_ids(
        conn,
        session_id,
        project_id,
        excluded_run_ids=run_ids,
        excluded_entity_ids=[*removable_ids, *curated_ids],
    )
    stats["run_findings"] = len(current_finding_ids - after_run_finding_ids)
    stats["removable_findings"] = len(after_run_finding_ids - after_removable_finding_ids)
    stats["curated_findings"] = len(after_removable_finding_ids - after_curated_finding_ids)
    stats["kept_curated_findings"] = stats["curated_findings"]


def preview_project_run_entity_links(session_id, project_id, data, *, team_id=""):
    run_ids = _normalize_project_run_ids_payload(data)
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            [*project_owner_params, project_id],
        ).fetchone()
        if not project:
            return None
        run_maps = _bulk_project_run_maps(conn, session_id, run_ids, team_id=team_id)
        if any(run_id not in run_maps["owned"] for run_id in run_ids):
            raise ProjectWorkspaceNotFound("run not found for this session")
        if any(run_id not in run_maps["linkable"] for run_id in run_ids):
            raise ProjectWorkspaceError("project links only support external runs")
        entity_ids = _run_entity_ids_for_project_link(conn, session_id, run_ids, team_id=team_id)
        stats = _project_run_entity_link_stats(conn, project_id, entity_ids)
    stats["run_count"] = len(run_ids)
    return stats


def _source_detail_flag_enabled(source_detail, key):
    detail = dialect_for_backend(get_db_backend()).decode_json_dict(source_detail)
    value = detail.get(key)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _project_run_entity_link_is_disposable(row):
    source = str(row["source"] or "")
    review_state = str(row["review_state"] or "confirmed")
    confidence = float(row["confidence"] or 1.0)
    source_detail = row["source_detail"]
    has_default_project_link = (
        abs(confidence - 1.0) < 0.0001
        and review_state == "confirmed"
        and dialect_for_backend(get_db_backend()).decode_json_dict(source_detail) == {}
    )
    if has_default_project_link:
        return True
    return (
        source == "auto_command"
        and abs(confidence - 1.0) < 0.0001
        and review_state == "pending"
        and _source_detail_flag_enabled(source_detail, PROJECT_TARGET_SOURCE_DETAIL_FLAG)
    )


def _project_run_entity_unlink_candidates(conn, session_id, project_id, run_ids, *, include_curated=False):
    stats = {
        "available": 0,
        "removable": 0,
        "curated": 0,
        "kept_curated": 0,
        "removed": 0,
        "removed_curated": 0,
        "run_findings": 0,
        "removable_findings": 0,
        "curated_findings": 0,
        "kept_curated_findings": 0,
        "run_count": len(run_ids),
    }
    if not run_ids:
        return stats, []
    placeholders = ",".join("?" for _ in run_ids)
    rows = conn.execute(
        "SELECT DISTINCT e.id, l.source, l.confidence, l.review_state, l.source_detail, "
        "EXISTS ("
        "  SELECT 1 FROM entity_run_links other_erl "
        "  WHERE other_erl.entity_id = e.id "
        f"  AND other_erl.run_id NOT IN ({placeholders})"
        ") AS has_other_runs, "
        "EXISTS ("
        "  SELECT 1 FROM project_links other_l "
        "  WHERE other_l.entity_type = 'atlas_entity' "
        "  AND other_l.entity_id = e.id "
        "  AND other_l.project_id != ?"
        ") AS has_other_projects, "
        "EXISTS ("
        "  SELECT 1 FROM entity_labels lbl "
        "  WHERE lbl.session_id = ? "
        "  AND lbl.entity_type = 'atlas_entity' "
        "  AND lbl.entity_id = e.id"
        ") AS has_labels, "
        "EXISTS ("
        "  SELECT 1 FROM entity_notes note "
        "  WHERE note.session_id = ? "
        "  AND note.entity_type = 'atlas_entity' "
        "  AND note.entity_id = e.id "
        "  AND trim(note.body) != ''"
        ") AS has_note, "
        "EXISTS ("
        "  SELECT 1 FROM findings child_f "
        "  WHERE child_f.session_id = e.session_id "
        "  AND child_f.entity_id = e.id "
        "  AND ("
        "    COALESCE(NULLIF(child_f.status, ''), 'new') != 'new' "
        "    OR COALESCE(NULLIF(child_f.review_state, ''), 'new') != 'new' "
        "    OR EXISTS ("
        "      SELECT 1 FROM project_links child_link "
        "      WHERE child_link.entity_type = 'finding' "
        "      AND child_link.entity_id = child_f.id"
        "    ) "
        "    OR EXISTS ("
        "      SELECT 1 FROM entity_labels child_label "
        "      WHERE child_label.entity_type = 'finding' "
        "      AND child_label.entity_id = child_f.id"
        "    ) "
        "    OR EXISTS ("
        "      SELECT 1 FROM entity_notes child_note "
        "      WHERE child_note.entity_type = 'finding' "
        "      AND child_note.entity_id = child_f.id"
        "    )"
        "  )"
        ") AS has_curated_findings "
        "FROM entity_run_links erl "
        "JOIN entities e ON e.id = erl.entity_id "
        "JOIN runs r ON r.id = erl.run_id "
        "JOIN project_links l ON l.project_id = ? "
        "AND l.entity_type = 'atlas_entity' "
        "AND l.entity_id = e.id "
        "WHERE r.session_id = ? AND e.session_id = ? "  # nosec
        f"AND erl.run_id IN ({placeholders})",
        [
            *run_ids,
            project_id,
            session_id,
            session_id,
            project_id,
            session_id,
            session_id,
            *run_ids,
        ],
    ).fetchall()
    removable_ids = []
    curated_ids = []
    for row in rows:
        stats["available"] += 1
        is_curated = any((
            int(row["has_other_runs"] or 0) > 0,
            int(row["has_other_projects"] or 0) > 0,
            int(row["has_labels"] or 0) > 0,
            int(row["has_note"] or 0) > 0,
            int(row["has_curated_findings"] or 0) > 0,
            not _project_run_entity_link_is_disposable(row),
        ))
        if is_curated:
            curated_ids.append(str(row["id"]))
            continue
        removable_ids.append(str(row["id"]))
    stats["removable"] = len(removable_ids)
    stats["curated"] = len(curated_ids)
    stats["kept_curated"] = 0 if include_curated else len(curated_ids)
    if include_curated:
        removable_ids.extend(curated_ids)
        stats["kept_curated_findings"] = 0
    _attach_project_run_entity_unlink_finding_stats(
        conn,
        stats,
        session_id,
        project_id,
        run_ids,
        removable_ids if not include_curated else removable_ids[:stats["removable"]],
        curated_ids,
    )
    if include_curated:
        stats["kept_curated_findings"] = 0
    return stats, removable_ids


def preview_project_run_entity_unlinks(session_id, project_id, data, *, team_id=""):
    run_ids = _normalize_project_run_ids_payload(data)
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            [*project_owner_params, project_id],
        ).fetchone()
        if not project:
            return None
        run_maps = _bulk_project_run_maps(conn, session_id, run_ids, team_id=team_id)
        if any(run_id not in run_maps["owned"] for run_id in run_ids):
            raise ProjectWorkspaceNotFound("run not found for this session")
        stats, _ = _project_run_entity_unlink_candidates(conn, session_id, project_id, run_ids)
    return stats


def unlink_project_run_entities(session_id, project_id, run_ids, *, include_curated=False, team_id=""):
    normalized_run_ids = []
    seen = set()
    for raw_run_id in run_ids:
        run_id = _trim_text(raw_run_id, MAX_ENTITY_ID_LEN)
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        normalized_run_ids.append(run_id)
    with get_db_connect()() as conn:
        conn.execute(dialect_for_backend(get_db_backend()).begin_immediate_sql())
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            [*project_owner_params, project_id],
        ).fetchone()
        if not project:
            return None
        run_maps = _bulk_project_run_maps(conn, session_id, normalized_run_ids, team_id=team_id)
        owned_run_ids = [run_id for run_id in normalized_run_ids if run_id in run_maps["owned"]]
        stats, removable_ids = _project_run_entity_unlink_candidates(
            conn,
            session_id,
            project_id,
            owned_run_ids,
            include_curated=include_curated,
        )
        if removable_ids:
            placeholders = ",".join("?" for _ in removable_ids)
            result = conn.execute(
                "DELETE FROM project_links WHERE project_id = ? "
                "AND entity_type = 'atlas_entity' "  # nosec
                f"AND entity_id IN ({placeholders})",
                [project_id, *removable_ids],
            )
            stats["removed"] = max(0, int(result.rowcount or 0))
            if include_curated:
                stats["removed_curated"] = min(stats["curated"], max(0, stats["removed"] - stats["removable"]))
        conn.commit()
    return stats


def _link_project_run_entities_on_conn(conn, session_id, project_id, run_ids, source="manual", *, team_id=""):
    source = validate_project_link_source(source)
    normalized_run_ids = [
        _trim_text(run_id, MAX_ENTITY_ID_LEN)
        for run_id in run_ids
    ]
    normalized_run_ids = [run_id for run_id in normalized_run_ids if run_id]
    if not normalized_run_ids:
        return _project_run_entity_link_stats(conn, project_id, [])
    project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
    project = conn.execute(
        "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
        [*project_owner_params, project_id],
    ).fetchone()
    if not project:
        return None
    run_maps = _bulk_project_run_maps(conn, session_id, normalized_run_ids, team_id=team_id)
    linkable_run_ids = [run_id for run_id in normalized_run_ids if run_id in run_maps["linkable"]]
    entity_ids = _run_entity_ids_for_project_link(conn, session_id, linkable_run_ids, team_id=team_id)
    stats = _project_run_entity_link_stats(conn, project_id, entity_ids)
    new_link_budget, new_entity_budget = _project_link_budgets(conn, project_id, "atlas_entity")
    linked_rows = set()
    if entity_ids:
        placeholders = ",".join("?" for _ in entity_ids)
        linked_rows = {
            str(row["entity_id"])
            for row in conn.execute(
                "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' "  # nosec
                f"AND entity_id IN ({placeholders})",
                [project_id, *entity_ids],
            ).fetchall()
        }
    for entity_id in entity_ids:
        if entity_id in linked_rows:
            continue
        if not _budget_available(new_link_budget, new_entity_budget):
            stats["rejected"] += 1
            continue
        _insert_project_link(conn, project_id, "atlas_entity", entity_id, source)
        stats["added"] += 1
        new_link_budget = _consume_budget(new_link_budget)
        new_entity_budget = _consume_budget(new_entity_budget)
    stats["linkable"] = max(0, stats["available"] - stats["already_linked"])
    stats["run_count"] = len(normalized_run_ids)
    return stats


def link_project_run_entities(session_id, project_id, run_ids, source="manual", *, team_id=""):
    with get_db_connect()() as conn:
        conn.execute(dialect_for_backend(get_db_backend()).begin_immediate_sql())
        stats = _link_project_run_entities_on_conn(conn, session_id, project_id, run_ids, source=source, team_id=team_id)
        conn.commit()
    return stats


def _normalize_link_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("project link payload must be an object")
    try:
        entity_type = validate_project_entity_type(_trim_text(data.get("entity_type"), 64))
    except ValueError as exc:
        raise ProjectWorkspaceError(str(exc)) from None
    if entity_type not in PROJECT_LINK_ENTITY_TYPES:
        raise ProjectWorkspaceError(f"project links do not support {entity_type}")
    entity_id = _trim_text(data.get("entity_id"), MAX_ENTITY_ID_LEN)
    if not entity_id:
        raise ProjectWorkspaceError("entity_id is required")
    source = validate_project_link_source(_trim_text(data.get("source") or "manual", 64))
    return entity_type, entity_id, source


def _normalize_bulk_link_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("project link payload must be an object")
    try:
        entity_type = validate_project_entity_type(_trim_text(data.get("entity_type"), 64))
    except ValueError as exc:
        raise ProjectWorkspaceError(str(exc)) from None
    if entity_type not in PROJECT_LINK_ENTITY_TYPES:
        raise ProjectWorkspaceError(f"project links do not support {entity_type}")
    raw_ids = data.get("entity_ids")
    if not isinstance(raw_ids, list):
        raise ProjectWorkspaceError("entity_ids must be a list")
    if len(raw_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        raise ProjectWorkspaceError("too_many")
    entity_ids = []
    seen = set()
    for raw_id in raw_ids:
        entity_id = _trim_text(raw_id, MAX_ENTITY_ID_LEN)
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        entity_ids.append(entity_id)
    if not entity_ids:
        raise ProjectWorkspaceError("entity_ids is required")
    source = validate_project_link_source(_trim_text(data.get("source") or "manual", 64))
    return entity_type, entity_ids, source


def _workspace_file_belongs_to_session(session_id, entity_id):
    try:
        path = resolve_workspace_path(session_id, entity_id, _config.CFG)
        return path.is_file()
    except (OSError, WorkspaceError):
        return False


def _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
    if entity_type == "workspace_file":
        return _workspace_file_belongs_to_session(session_id, entity_id)
    if entity_type in {"atlas_entity", "target"}:
        row = conn.execute(
            "SELECT 1 FROM entities WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "project":
        row = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "run":
        row = conn.execute(
            "SELECT 1 FROM runs WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "snapshot":
        row = conn.execute(
            "SELECT 1 FROM snapshots WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "run_file_artifact":
        row = conn.execute(
            "SELECT 1 FROM run_file_artifacts WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "finding":
        row = conn.execute(
            "SELECT 1 FROM findings WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "package":
        row = conn.execute(
            "SELECT 1 FROM evidence_packages WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    else:
        return False
    return row is not None


def _run_is_project_linkable(conn, session_id, run_id, *, team_id=""):
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    row = conn.execute(
        "SELECT command, run_kind FROM runs WHERE " + owner_sql + " AND id = ?",  # nosec
        (*owner_params, run_id),
    ).fetchone()
    if not row:
        return False
    return is_project_linkable_run_kind(normalize_run_kind(row["run_kind"], command=str(row["command"] or "")))


def _run_belongs_to_owner(conn, session_id, run_id, *, team_id=""):
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    row = conn.execute(
        "SELECT 1 FROM runs WHERE " + owner_sql + " AND id = ?",  # nosec
        (*owner_params, run_id),
    ).fetchone()
    return row is not None


def list_project_links(session_id, project_id, *, team_id=""):
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            (*project_owner_params, project_id),
        ).fetchone()
        if not project:
            return None
        rows = conn.execute(
            "SELECT l.id, l.project_id, l.entity_type, l.entity_id, l.source, l.created "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND " + run_owner_sql + " AND r.run_kind = ? "  # nosec
            "ORDER BY l.created DESC",
            (project_id, *run_owner_params, RUN_KIND_EXTERNAL),
        ).fetchall()
    return [_row_to_link(row) for row in rows]


def link_project_entity(session_id, project_id, data, *, team_id=""):
    entity_type, entity_id, source = _normalize_link_payload(data)
    created = _now()
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            (*project_owner_params, project_id),
        ).fetchone()
        if not project:
            return None
        if entity_type == "run":
            entity_exists = _run_belongs_to_owner(conn, session_id, entity_id, team_id=team_id)
        else:
            entity_exists = (
                entity_exists_in_scope(conn, session_id, entity_id, team_id=team_id)
                if entity_type == "atlas_entity"
                else not team_id and _entity_belongs_to_session(conn, session_id, entity_type, entity_id)
            )
        if not entity_exists:
            raise ProjectWorkspaceNotFound(f"{entity_type} not found for this session")
        if entity_type == "run" and not _run_is_project_linkable(conn, session_id, entity_id, team_id=team_id):
            raise ProjectWorkspaceError("project links only support external runs")
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            [project_id, entity_type, entity_id],
        ).fetchone()
        if row:
            return _row_to_link(row)
        if _quota_exceeded(
            _project_link_count(conn, project_id),
            "max_project_links_per_project",
            5000,
        ):
            _raise_quota("project link quota exceeded for this project")
        if entity_type == "atlas_entity" and _quota_exceeded(
            _project_link_count(conn, project_id, entity_type="atlas_entity"),
            "max_project_entities_per_project",
            5000,
        ):
            _raise_quota("project entity quota exceeded for this project")
        for _ in range(10):
            link_id = _new_project_link_id()
            conn.execute(
                "INSERT INTO project_links "
                "(id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id, entity_type, entity_id) DO NOTHING",
                (link_id, project_id, entity_type, entity_id, source, created),
            )
            row = conn.execute(
                "SELECT id, project_id, entity_type, entity_id, source, created "
                "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
                [project_id, entity_type, entity_id],
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_link(row)
        raise ProjectWorkspaceError("could not allocate a project link id")


def _project_bulk_result(statuses, entity_type, entity_id, status, *, reason=None):
    statuses[status] = statuses.get(status, 0) + 1
    item = (
        {"entity_id": entity_id, "status": status}
        if entity_type == "atlas_entity"
        else {"run_id": entity_id, "status": status}
    )
    if reason:
        item["reason"] = reason
    return item


def _bulk_project_run_maps(conn, session_id, run_ids, *, team_id=""):
    placeholders = ",".join("?" for _ in run_ids)
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    owned_rows = conn.execute(
        "SELECT id, command, run_kind FROM runs WHERE " + owner_sql + f" AND id IN ({placeholders})",  # nosec
        [*owner_params, *run_ids],
    ).fetchall()
    owned = {str(row["id"]) for row in owned_rows}
    linkable = {
        str(row["id"])
        for row in owned_rows
        if is_project_linkable_run_kind(normalize_run_kind(row["run_kind"], command=str(row["command"] or "")))
    }
    return {
        "owned": owned,
        "linkable": linkable,
    }


def _bulk_project_entity_maps(conn, session_id, entity_type, entity_ids, *, team_id=""):
    if entity_type == "run":
        return _bulk_project_run_maps(conn, session_id, entity_ids, team_id=team_id)
    if team_id:
        owned = set()
        for entity_id in entity_ids:
            if entity_exists_in_scope(conn, session_id, entity_id, team_id=team_id):
                owned.add(entity_id)
        return {
            "owned": owned,
            "linkable": set(owned),
        }
    if entity_type != "atlas_entity":
        return {"owned": set(), "linkable": set()}
    placeholders = ",".join("?" for _ in entity_ids)
    rows = conn.execute(
        f"SELECT id FROM entities WHERE session_id = ? AND id IN ({placeholders})",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    owned = {str(row["id"]) for row in rows}
    return {
        "owned": owned,
        "linkable": set(owned),
    }


def link_project_entities(session_id, project_id, data, *, team_id=""):
    entity_type, entity_ids, source = _normalize_bulk_link_payload(data)
    counts = {
        "added": 0,
        "already_linked": 0,
        "removed": 0,
        "not_linked": 0,
        "not_found": 0,
        "rejected": 0,
    }
    results = []
    with get_db_connect()() as conn:
        conn.execute(dialect_for_backend(get_db_backend()).begin_immediate_sql())
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            [*project_owner_params, project_id],
        ).fetchone()
        if not project:
            return None
        entity_maps = _bulk_project_entity_maps(conn, session_id, entity_type, entity_ids, team_id=team_id)
        placeholders = ",".join("?" for _ in entity_ids)
        link_rows = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "  # nosec
            "FROM project_links WHERE project_id = ? AND entity_type = ? "
            f"AND entity_id IN ({placeholders})",
            [project_id, entity_type, *entity_ids],
        ).fetchall()
        linked_by_id = {str(row["entity_id"]): _row_to_link(row) for row in link_rows}
        new_link_budget, new_entity_budget = _project_link_budgets(conn, project_id, entity_type)
        links = []
        for entity_id in entity_ids:
            if entity_id not in entity_maps["owned"]:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "not_found"))
                continue
            if entity_id not in entity_maps["linkable"]:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "rejected", reason="builtin"))
                continue
            if entity_id in linked_by_id:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "already_linked"))
                continue
            if not _budget_available(new_link_budget, new_entity_budget):
                results.append(_project_bulk_result(counts, entity_type, entity_id, "rejected", reason="policy_blocked"))
                continue
            link = _insert_project_link(conn, project_id, entity_type, entity_id, source)
            links.append(link)
            new_link_budget = _consume_budget(new_link_budget)
            new_entity_budget = _consume_budget(new_entity_budget)
            results.append(_project_bulk_result(counts, entity_type, entity_id, "added"))
        conn.commit()
    return {"ok": True, "counts": counts, "results": results, "links": links}


def unlink_project_entity(session_id, project_id, data, *, team_id=""):
    raw = data if isinstance(data, dict) else {}
    entity_type, entity_id, _ = _normalize_link_payload({**raw, "source": "manual"})
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            [*project_owner_params, project_id],
        ).fetchone()
        if not project:
            return None
        result = conn.execute(
            "DELETE FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            (project_id, entity_type, entity_id),
        )
        conn.commit()
    return result.rowcount > 0


def unlink_project_entities(session_id, project_id, data, *, team_id=""):
    entity_type, entity_ids, _ = _normalize_bulk_link_payload({**(data if isinstance(data, dict) else {}), "source": "manual"})
    counts = {
        "added": 0,
        "already_linked": 0,
        "removed": 0,
        "not_linked": 0,
        "not_found": 0,
        "rejected": 0,
    }
    results = []
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            [*project_owner_params, project_id],
        ).fetchone()
        if not project:
            return None
        entity_maps = _bulk_project_entity_maps(conn, session_id, entity_type, entity_ids, team_id=team_id)
        placeholders = ",".join("?" for _ in entity_ids)
        link_rows = conn.execute(
            "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = ? "  # nosec
            f"AND entity_id IN ({placeholders})",
            [project_id, entity_type, *entity_ids],
        ).fetchall()
        linked_ids = {str(row["entity_id"]) for row in link_rows}
        removable_ids = []
        for entity_id in entity_ids:
            if entity_id not in entity_maps["owned"]:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "not_found"))
                continue
            if entity_id not in linked_ids:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "not_linked"))
                continue
            removable_ids.append(entity_id)
            results.append(_project_bulk_result(counts, entity_type, entity_id, "removed"))
        if removable_ids:
            remove_placeholders = ",".join("?" for _ in removable_ids)
            conn.execute(
                "DELETE FROM project_links WHERE project_id = ? AND entity_type = ? "  # nosec
                f"AND entity_id IN ({remove_placeholders})",
                [project_id, entity_type, *removable_ids],
            )
        conn.commit()
    return {"ok": True, "counts": counts, "results": results}
