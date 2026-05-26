"""
Project entity label and note helpers.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import config as _config
from core.database import DB_BACKEND, db_connect, validate_project_entity_type
from core.database_backend import dialect_for_backend
from services.projects.contracts import (
    ENTITY_METADATA_TYPES,
    MAX_ENTITY_ID_LEN,
    MAX_ENTITY_NOTE_BODY_LEN,
    MAX_LABEL_LEN,
    MAX_PROJECT_NOTES_LEN,
    ProjectWorkspaceError,
    ProjectWorkspaceQuotaExceeded,
)
from services.projects.utils import trim_text as _trim_text
from services.workspace.files import WorkspaceError, resolve_workspace_path


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
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "label": row["label"],
        "source": row["source"],
        "created": row["created"],
    }


def _row_to_entity_note(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "body": row["body"],
        "created": row["created"],
        "updated": row["updated"],
    }


def _count_entity_metadata_for_ids(conn, table, entity_type, entity_ids):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return 0
    placeholders = ",".join("?" for _ in values)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE entity_type = ? AND entity_id IN ({placeholders})",  # nosec
        [entity_type, *values],
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _entity_labels_by_id(conn, session_id, entity_type, entity_ids):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return {}
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT id, session_id, entity_type, entity_id, label, source, created "  # nosec
        "FROM entity_labels WHERE session_id = ? AND entity_type = ? "
        f"AND entity_id IN ({placeholders}) "
        "ORDER BY " + _label_order_sql(),
        [session_id, entity_type, *values],
    ).fetchall()
    grouped = {value: [] for value in values}
    for row in rows:
        grouped.setdefault(str(row["entity_id"]), []).append(_row_to_label(row))
    return grouped


def _entity_notes_by_id(conn, session_id, entity_type, entity_ids):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return {}
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT id, session_id, entity_type, entity_id, body, created, updated "  # nosec
        "FROM entity_notes WHERE session_id = ? AND entity_type = ? "
        f"AND entity_id IN ({placeholders})",
        [session_id, entity_type, *values],
    ).fetchall()
    return {str(row["entity_id"]): _row_to_entity_note(row) for row in rows}


def _attach_project_notes(conn, session_id, projects):
    items = [project for project in projects if project]
    if not items:
        return items
    note_map = _entity_notes_by_id(conn, session_id, "project", [project["id"] for project in items])
    for project in items:
        project["note"] = note_map.get(str(project["id"]))
    return items


def _attach_project_labels(conn, session_id, projects):
    items = [project for project in projects if project]
    if not items:
        return items
    label_map = _entity_labels_by_id(conn, session_id, "project", [project["id"] for project in items])
    for project in items:
        project["labels"] = label_map.get(str(project["id"]), [])
    return items


def _attach_package_metadata(conn, session_id, packages):
    items = [package for package in packages if package]
    if not items:
        return items
    package_ids = [package["id"] for package in items]
    label_map = _entity_labels_by_id(conn, session_id, "package", package_ids)
    note_map = _entity_notes_by_id(conn, session_id, "package", package_ids)
    for package in items:
        package_id = str(package["id"])
        package["labels"] = label_map.get(package_id, [])
        package["note"] = note_map.get(package_id)
    return items


def _attach_target_metadata(conn, session_id, targets):
    items = [target for target in targets if target]
    if not items:
        return items
    target_ids = [target["id"] for target in items]
    label_map = _entity_labels_by_id(conn, session_id, "atlas_entity", target_ids)
    legacy_label_map = _entity_labels_by_id(conn, session_id, "target", target_ids)
    note_map = _entity_notes_by_id(conn, session_id, "atlas_entity", target_ids)
    legacy_note_map = _entity_notes_by_id(conn, session_id, "target", target_ids)
    for target in items:
        target_id = str(target["id"])
        target["labels"] = [*label_map.get(target_id, []), *legacy_label_map.get(target_id, [])]
        target["note"] = note_map.get(target_id) or legacy_note_map.get(target_id)
    return items


def _save_project_note(conn, session_id, project_id, notes):
    body = _trim_text(notes, MAX_PROJECT_NOTES_LEN)
    now = _now()
    if not body:
        conn.execute(
            "DELETE FROM entity_notes WHERE session_id = ? AND entity_type = 'project' AND entity_id = ?",
            (session_id, project_id),
        )
        return
    existing = conn.execute(
        "SELECT id FROM entity_notes WHERE session_id = ? AND entity_type = 'project' AND entity_id = ?",
        (session_id, project_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE entity_notes SET body = ?, updated = ? WHERE session_id = ? AND entity_type = 'project' AND entity_id = ?",
            (body, now, session_id, project_id),
        )
        return
    session_count = conn.execute(
        "SELECT COUNT(*) AS count FROM entity_notes WHERE session_id = ?",
        (session_id,),
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
            "(id, session_id, entity_type, entity_id, body, created, updated) "
            "VALUES (?, ?, 'project', ?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            (note_id, session_id, project_id, body, now, now),
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


def list_entity_labels(session_id, entity_type, entity_id):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        rows = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, label, source, created "  # nosec B608
            "FROM entity_labels WHERE session_id = ? AND entity_type = ? AND entity_id = ? "
            "ORDER BY " + _label_order_sql(),
            (session_id, entity_type, entity_id),
        ).fetchall()
    return [_row_to_label(row) for row in rows]


def add_entity_label(session_id, entity_type, entity_id, data):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    label = _normalize_label_payload(data)
    created = _now()
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        row = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, label, source, created "
            "FROM entity_labels WHERE session_id = ? AND entity_type = ? "
            "AND entity_id = ? AND label = ?",
            [session_id, entity_type, entity_id, label],
        ).fetchone()
        if row:
            return _row_to_label(row)
        session_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_labels WHERE session_id = ?",
            [session_id],
        ).fetchone()
        if _quota_exceeded(
            int(session_count["count"] or 0) if session_count else 0,
            "max_entity_labels_per_session",
            5000,
        ):
            _raise_quota("label quota exceeded for this session")
        entity_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_labels "
            "WHERE session_id = ? AND entity_type = ? AND entity_id = ?",
            [session_id, entity_type, entity_id],
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
                "(id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, ?, ?, ?, 'manual', ?) "
                "ON CONFLICT(session_id, entity_type, entity_id, label) DO NOTHING",
                (label_id, session_id, entity_type, entity_id, label, created),
            )
            row = conn.execute(
                "SELECT id, session_id, entity_type, entity_id, label, source, created "
                "FROM entity_labels WHERE session_id = ? AND entity_type = ? "
                "AND entity_id = ? AND label = ?",
                [session_id, entity_type, entity_id, label],
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_label(row)
        raise ProjectWorkspaceError("could not allocate an entity label id")


def delete_entity_label(session_id, entity_type, entity_id, data):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    label = _normalize_label_payload(data)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        result = conn.execute(
            "DELETE FROM entity_labels WHERE session_id = ? AND entity_type = ? "
            "AND entity_id = ? AND label = ?",
            (session_id, entity_type, entity_id, label),
        )
        conn.commit()
    return result.rowcount > 0


def entity_metadata_target_exists(session_id, entity_type, entity_id):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    with db_connect() as conn:
        return _entity_belongs_to_session(conn, session_id, entity_type, entity_id)


def get_entity_note(session_id, entity_type, entity_id):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        row = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, body, created, updated "
            "FROM entity_notes WHERE session_id = ? AND entity_type = ? AND entity_id = ?",
            (session_id, entity_type, entity_id),
        ).fetchone()
    return _row_to_entity_note(row)


def upsert_entity_note(session_id, entity_type, entity_id, data):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    payload = _normalize_entity_note_payload(data)
    now = _now()
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        existing = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, body, created, updated "
            "FROM entity_notes WHERE session_id = ? AND entity_type = ? AND entity_id = ?",
            [session_id, entity_type, entity_id],
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE entity_notes SET body = ?, updated = ? WHERE session_id = ? AND entity_type = ? AND entity_id = ?",
                (payload["body"], now, session_id, entity_type, entity_id),
            )
            row = conn.execute(
                "SELECT id, session_id, entity_type, entity_id, body, created, updated "
                "FROM entity_notes WHERE session_id = ? AND entity_type = ? AND entity_id = ?",
                [session_id, entity_type, entity_id],
            ).fetchone()
            conn.commit()
            return _row_to_entity_note(row)
        session_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_notes WHERE session_id = ?",
            [session_id],
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
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(session_id, entity_type, entity_id) DO NOTHING",
                (
                    note_id,
                    session_id,
                    entity_type,
                    entity_id,
                    payload["body"],
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id, session_id, entity_type, entity_id, body, created, updated "
                "FROM entity_notes WHERE id = ? AND session_id = ?",
                [note_id, session_id],
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_entity_note(row)
        raise ProjectWorkspaceError("could not allocate an entity note id")


def delete_entity_note(session_id, entity_type, entity_id):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        result = conn.execute(
            "DELETE FROM entity_notes WHERE session_id = ? AND entity_type = ? AND entity_id = ?",
            (session_id, entity_type, entity_id),
        )
        conn.commit()
    return result.rowcount > 0
