"""
Project entity label and note helpers.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import config as _config
from core.database import DB_BACKEND, db_connect, validate_project_entity_type
from core.database_backend import dialect_for_backend
from services.atlas.lookup import entity_exists_in_scope, finding_exists_in_scope, metadata_owner_id
from services.projects.contracts import (
    ENTITY_METADATA_TYPES,
    MAX_ENTITY_ID_LEN,
    MAX_ENTITY_NOTE_BODY_LEN,
    MAX_LABEL_LEN,
    MAX_PROJECT_NOTES_LEN,
    ProjectWorkspaceError,
    ProjectWorkspaceQuotaExceeded,
)
from services.projects.scope import normalize_team_id, shared_owner_where
from services.projects.utils import trim_text as _trim_text
from services.teams.scope import team_owner_context
from services.workspace.files import WorkspaceError, resolve_owner_workspace_path, resolve_workspace_path


def _cfg_int(key, default, *, cfg=None):
    if cfg is None:
        from config import CFG
        cfg = CFG
    try:
        value = int(cfg.get(key, default))
    except (AttributeError, TypeError, ValueError):
        value = default
    return max(0, value)


def _quota_exceeded(count, key, default):
    limit = _cfg_int(key, default)
    return limit > 0 and count >= limit


def _raise_quota(message):
    raise ProjectWorkspaceQuotaExceeded(message)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _label_order_sql() -> str:
    return dialect_for_backend(DB_BACKEND).case_insensitive_order("label") + ", created ASC"


def _new_entity_label_id() -> str:
    return "lbl_" + secrets.token_hex(8)


def _new_entity_note_id() -> str:
    return "note_" + secrets.token_hex(8)


def _row_to_label(row):
    if not row:
        return None
    item = {
        "id": row["id"],
        "session_id": row["session_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "label": row["label"],
        "source": row["source"],
        "created": row["created"],
    }
    if hasattr(row, "keys") and "team_id" in row.keys():
        item["team_id"] = row["team_id"] or ""
    return item


def _row_to_entity_note(row):
    if not row:
        return None
    item = {
        "id": row["id"],
        "session_id": row["session_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "body": row["body"],
        "created": row["created"],
        "updated": row["updated"],
    }
    if hasattr(row, "keys") and "team_id" in row.keys():
        item["team_id"] = row["team_id"] or ""
    return item


def _metadata_row_owner_values(session_id, team_id=""):
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        return str(session_id or "").strip() or normalized_team_id, normalized_team_id
    return str(session_id or "").strip(), ""


def _metadata_owner_where(session_id, team_id="", *, table_alias=""):
    prefix = f"{table_alias}." if table_alias else ""
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        legacy_session_id = _metadata_session_id(session_id, normalized_team_id)
        return (
            f"({prefix}team_id = ? OR "
            f"(({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?))",
            (normalized_team_id, legacy_session_id),
        )
    return (
        f"({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?",
        (str(session_id or "").strip(),),
    )


def _count_entity_metadata_for_ids(conn, table, entity_type, entity_ids, *, session_id="", team_id=""):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return 0
    placeholders = ",".join("?" for _ in values)
    params = [entity_type, *values]
    owner_sql = ""
    owner_params: tuple[str, ...] = ()
    if session_id or team_id:
        owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM {table} "  # nosec
        f"WHERE entity_type = ? AND entity_id IN ({placeholders})"
        + (f" AND {owner_sql}" if owner_sql else ""),
        [*params, *owner_params],
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _metadata_session_id(session_id, team_id=""):
    return metadata_owner_id(session_id, team_id)


def _entity_labels_by_id(conn, session_id, entity_type, entity_ids, *, team_id=""):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return {}
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "  # nosec
        "FROM entity_labels WHERE " + owner_sql + " AND entity_type = ? "
        f"AND entity_id IN ({placeholders}) "
        "ORDER BY " + _label_order_sql(),
        [*owner_params, entity_type, *values],
    ).fetchall()
    grouped = {value: [] for value in values}
    seen = set()
    for row in rows:
        dedupe_key = (str(row["entity_id"]), str(row["label"]))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        grouped.setdefault(str(row["entity_id"]), []).append(_row_to_label(row))
    return grouped


def _entity_notes_by_id(conn, session_id, entity_type, entity_ids, *, team_id=""):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return {}
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "  # nosec
        "FROM entity_notes WHERE " + owner_sql + " AND entity_type = ? "
        f"AND entity_id IN ({placeholders})",
        [*owner_params, entity_type, *values],
    ).fetchall()
    return {str(row["entity_id"]): _row_to_entity_note(row) for row in rows}


def _attach_project_notes(conn, session_id, projects, *, team_id=""):
    items = [project for project in projects if project]
    if not items:
        return items
    note_map = _entity_notes_by_id(conn, session_id, "project", [project["id"] for project in items], team_id=team_id)
    for project in items:
        project["note"] = note_map.get(str(project["id"]))
    return items


def _attach_project_labels(conn, session_id, projects, *, team_id=""):
    items = [project for project in projects if project]
    if not items:
        return items
    label_map = _entity_labels_by_id(conn, session_id, "project", [project["id"] for project in items], team_id=team_id)
    for project in items:
        project["labels"] = label_map.get(str(project["id"]), [])
    return items


def _attach_package_metadata(conn, session_id, packages, *, team_id=""):
    items = [package for package in packages if package]
    if not items:
        return items
    package_ids = [package["id"] for package in items]
    label_map = _entity_labels_by_id(conn, session_id, "package", package_ids, team_id=team_id)
    note_map = _entity_notes_by_id(conn, session_id, "package", package_ids, team_id=team_id)
    for package in items:
        package_id = str(package["id"])
        package["labels"] = label_map.get(package_id, [])
        package["note"] = note_map.get(package_id)
    return items


def _attach_target_metadata(conn, session_id, targets, *, team_id=""):
    items = [target for target in targets if target]
    if not items:
        return items
    target_ids = [target["id"] for target in items]
    label_map = _entity_labels_by_id(conn, session_id, "atlas_entity", target_ids, team_id=team_id)
    legacy_label_map = _entity_labels_by_id(conn, session_id, "target", target_ids, team_id=team_id)
    note_map = _entity_notes_by_id(conn, session_id, "atlas_entity", target_ids, team_id=team_id)
    legacy_note_map = _entity_notes_by_id(conn, session_id, "target", target_ids, team_id=team_id)
    for target in items:
        target_id = str(target["id"])
        target["labels"] = [*label_map.get(target_id, []), *legacy_label_map.get(target_id, [])]
        target["note"] = note_map.get(target_id) or legacy_note_map.get(target_id)
    return items


def _save_project_note(conn, session_id, project_id, notes, *, team_id=""):
    body = _trim_text(notes, MAX_PROJECT_NOTES_LEN)
    metadata_session, metadata_team_id = _metadata_row_owner_values(session_id, team_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    now = _now()
    if not body:
        conn.execute(
            "DELETE FROM entity_notes WHERE " + owner_sql + " AND entity_type = 'project' AND entity_id = ?",  # nosec
            (*owner_params, project_id),
        )
        return
    existing = conn.execute(
        "SELECT id FROM entity_notes WHERE " + owner_sql + " AND entity_type = 'project' AND entity_id = ?",  # nosec
        (*owner_params, project_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE entity_notes SET session_id = ?, team_id = ?, body = ?, updated = ? WHERE id = ?",
            (metadata_session, metadata_team_id, body, now, existing["id"]),
        )
        return
    count_sql, count_params = _metadata_owner_where(session_id, team_id)
    session_count = conn.execute(
        "SELECT COUNT(*) AS count FROM entity_notes WHERE " + count_sql,  # nosec
        count_params,
    ).fetchone()
    if _quota_exceeded(
        int(session_count["count"] or 0) if session_count else 0,
        "max_entity_notes_per_session",
        2000,
    ):
        _raise_quota("note quota exceeded for this session")
    for _ in range(10):
        note_id = _new_entity_note_id()
        result = conn.execute(
            "INSERT INTO entity_notes "
            "(id, session_id, team_id, entity_type, entity_id, body, created, updated) "
            "VALUES (?, ?, ?, 'project', ?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            (note_id, metadata_session, metadata_team_id, project_id, body, now, now),
        )
        if result.rowcount:
            return
    raise ProjectWorkspaceError("could not allocate an entity note id")


def _normalize_metadata_target(entity_type, entity_id):
    try:
        entity_type = validate_project_entity_type(_trim_text(entity_type, 64))
    except ValueError as exc:
        raise ProjectWorkspaceError(str(exc)) from None
    if entity_type not in ENTITY_METADATA_TYPES:
        raise ProjectWorkspaceError(f"entity metadata does not support {entity_type}")
    if entity_type == "target":
        entity_type = "atlas_entity"
    entity_id = _trim_text(entity_id, MAX_ENTITY_ID_LEN)
    if not entity_id:
        raise ProjectWorkspaceError("entity_id is required")
    return entity_type, entity_id


def _normalize_label_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("label payload must be an object")
    label = _trim_text(data.get("label"), MAX_LABEL_LEN)
    if not label:
        raise ProjectWorkspaceError("label is required")
    return label


def _normalize_entity_note_payload(data, *, partial=False):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("note payload must be an object")
    clean = {}
    if "body" in data or not partial:
        body = _trim_text(data.get("body"), MAX_ENTITY_NOTE_BODY_LEN)
        if not body:
            raise ProjectWorkspaceError("note body is required")
        clean["body"] = body
    return clean


def _workspace_file_belongs_to_session(session_id, entity_id, *, team_id=""):
    try:
        normalized_team_id = normalize_team_id(team_id)
        if normalized_team_id:
            path = resolve_owner_workspace_path(
                team_owner_context(normalized_team_id, actor_session_id=session_id),
                entity_id,
                _config.CFG,
            )
        else:
            path = resolve_workspace_path(session_id, entity_id, _config.CFG)
        return path.is_file()
    except (OSError, WorkspaceError):
        return False


def _shared_record_exists(conn, session_id, table, entity_id, *, team_id=""):
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE {owner_sql} AND id = ?",  # nosec
        (*owner_params, entity_id),
    ).fetchone()
    return row is not None


def _entity_belongs_to_session(conn, session_id, entity_type, entity_id, *, team_id=""):
    normalized_team_id = normalize_team_id(team_id)
    if entity_type == "workspace_file":
        return _workspace_file_belongs_to_session(session_id, entity_id, team_id=normalized_team_id)
    if entity_type in {"atlas_entity", "target"}:
        return entity_exists_in_scope(conn, session_id, entity_id, team_id=normalized_team_id)
    elif entity_type == "project":
        return _shared_record_exists(conn, session_id, "projects", entity_id, team_id=normalized_team_id)
    elif entity_type == "run":
        return _shared_record_exists(conn, session_id, "runs", entity_id, team_id=normalized_team_id)
    elif entity_type == "snapshot":
        return _shared_record_exists(conn, session_id, "snapshots", entity_id, team_id=normalized_team_id)
    elif entity_type == "run_file_artifact":
        if normalized_team_id:
            row = conn.execute(
                "SELECT 1 FROM run_file_artifacts rfa "
                "JOIN runs r ON r.id = rfa.run_id "
                "WHERE r.team_id = ? AND rfa.id = ?",
                (normalized_team_id, entity_id),
            ).fetchone()
            return row is not None
        row = conn.execute(
            "SELECT 1 FROM run_file_artifacts WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
        return row is not None
    elif entity_type == "finding":
        return finding_exists_in_scope(conn, session_id, entity_id, team_id=normalized_team_id)
    elif entity_type == "package":
        if normalized_team_id:
            row = conn.execute(
                "SELECT 1 FROM evidence_packages WHERE team_id = ? AND id = ?",
                (normalized_team_id, entity_id),
            ).fetchone()
            return row is not None
        row = conn.execute(
            "SELECT 1 FROM evidence_packages WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
        return row is not None
    else:
        return False
    return row is not None


def list_entity_labels(session_id, entity_type, entity_id, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        rows = conn.execute(
            "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "  # nosec
            "FROM entity_labels WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ? "
            "ORDER BY " + _label_order_sql(),
            (*owner_params, entity_type, entity_id),
        ).fetchall()
    labels = []
    seen = set()
    for row in rows:
        label = str(row["label"])
        if label in seen:
            continue
        seen.add(label)
        labels.append(_row_to_label(row))
    return labels


def add_entity_label(session_id, entity_type, entity_id, data, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    label = _normalize_label_payload(data)
    metadata_session, metadata_team_id = _metadata_row_owner_values(session_id, team_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    created = _now()
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        row = conn.execute(
            "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "  # nosec
            "FROM entity_labels WHERE " + owner_sql + " AND entity_type = ? "
            "AND entity_id = ? AND label = ?",
            [*owner_params, entity_type, entity_id, label],
        ).fetchone()
        if row:
            if normalize_team_id(team_id) and str(row["team_id"] or "") != metadata_team_id:
                conn.execute(
                    "UPDATE entity_labels SET session_id = ?, team_id = ? WHERE id = ?",
                    (metadata_session, metadata_team_id, row["id"]),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "
                    "FROM entity_labels WHERE id = ?",
                    (row["id"],),
                ).fetchone()
            return _row_to_label(row)
        count_sql, count_params = _metadata_owner_where(session_id, team_id)
        session_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_labels WHERE " + count_sql,  # nosec
            count_params,
        ).fetchone()
        if _quota_exceeded(
            int(session_count["count"] or 0) if session_count else 0,
            "max_entity_labels_per_session",
            5000,
        ):
            _raise_quota("label quota exceeded for this session")
        entity_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_labels "
            "WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ?",  # nosec
            [*owner_params, entity_type, entity_id],
        ).fetchone()
        if _quota_exceeded(
            int(entity_count["count"] or 0) if entity_count else 0,
            "max_entity_labels_per_entity",
            20,
        ):
            _raise_quota("label quota exceeded for this entity")
        for _ in range(10):
            label_id = _new_entity_label_id()
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, team_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, ?, ?, ?, ?, 'manual', ?)",
                (label_id, metadata_session, metadata_team_id, entity_type, entity_id, label, created),
            )
            row = conn.execute(
                "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "
                "FROM entity_labels WHERE id = ?",
                [label_id],
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_label(row)
        raise ProjectWorkspaceError("could not allocate an entity label id")


def delete_entity_label(session_id, entity_type, entity_id, data, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    label = _normalize_label_payload(data)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        result = conn.execute(
            "DELETE FROM entity_labels WHERE " + owner_sql + " AND entity_type = ? "  # nosec
            "AND entity_id = ? AND label = ?",
            (*owner_params, entity_type, entity_id, label),
        )
        conn.commit()
    return result.rowcount > 0


def entity_metadata_target_exists(session_id, entity_type, entity_id, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    with db_connect() as conn:
        return _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id)


def get_entity_note(session_id, entity_type, entity_id, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        row = conn.execute(
            "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "
            "FROM entity_notes WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ?",  # nosec
            (*owner_params, entity_type, entity_id),
        ).fetchone()
    return _row_to_entity_note(row)


def upsert_entity_note(session_id, entity_type, entity_id, data, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    payload = _normalize_entity_note_payload(data)
    metadata_session, metadata_team_id = _metadata_row_owner_values(session_id, team_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    now = _now()
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        existing = conn.execute(
            "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "
            "FROM entity_notes WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ?",  # nosec
            [*owner_params, entity_type, entity_id],
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE entity_notes SET session_id = ?, team_id = ?, body = ?, updated = ? WHERE id = ?",
                (metadata_session, metadata_team_id, payload["body"], now, existing["id"]),
            )
            row = conn.execute(
                "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "
                "FROM entity_notes WHERE id = ?",
                [existing["id"]],
            ).fetchone()
            conn.commit()
            return _row_to_entity_note(row)
        count_sql, count_params = _metadata_owner_where(session_id, team_id)
        session_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_notes WHERE " + count_sql,  # nosec
            count_params,
        ).fetchone()
        if _quota_exceeded(
            int(session_count["count"] or 0) if session_count else 0,
            "max_entity_notes_per_session",
            2000,
        ):
            _raise_quota("note quota exceeded for this session")
        for _ in range(10):
            note_id = _new_entity_note_id()
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, team_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note_id,
                    metadata_session,
                    metadata_team_id,
                    entity_type,
                    entity_id,
                    payload["body"],
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "
                "FROM entity_notes WHERE id = ?",
                [note_id],
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_entity_note(row)
        raise ProjectWorkspaceError("could not allocate an entity note id")


def delete_entity_note(session_id, entity_type, entity_id, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        result = conn.execute(
            "DELETE FROM entity_notes WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ?",  # nosec
            (*owner_params, entity_type, entity_id),
        )
        conn.commit()
    return result.rowcount > 0
