"""Workspace file metadata query helpers."""

from __future__ import annotations

from typing import Any

def _workspace_project_names_expr() -> str:
    from core.database import DB_BACKEND  # noqa: PLC0415
    from core.database_backend import dialect_for_backend  # noqa: PLC0415

    return dialect_for_backend(DB_BACKEND).string_agg_distinct("p.name")


def _workspace_label_order_sql() -> str:
    from core.database import DB_BACKEND  # noqa: PLC0415
    from core.database_backend import dialect_for_backend  # noqa: PLC0415

    return dialect_for_backend(DB_BACKEND).case_insensitive_order("label") + ", created ASC"


def _workspace_metadata_owner_where(scope: Any, table_alias: str = "") -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    if getattr(scope, "is_team", False):
        team_id = str(getattr(scope, "team_id", "") or "")
        return (
            f"({prefix}team_id = ? OR "
            f"(({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?))",
            (team_id, team_id),
        )
    return (
        f"({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?",
        (str(getattr(scope, "owner_id", "") or ""),),
    )


def workspace_file_metadata_by_path(scope: Any, paths: list[Any]) -> dict[str, dict[str, Any]]:
    from core.database import db_connect  # noqa: PLC0415

    clean_paths = sorted({str(path) for path in paths if path})
    if not clean_paths:
        return {}
    placeholders = ",".join("?" for _ in clean_paths)
    project_names_expr = _workspace_project_names_expr()
    label_order_sql = _workspace_label_order_sql()
    run_owner_sql, run_owner_params = scope.predicate(table_alias="r")
    project_owner_sql, project_owner_params = scope.predicate(table_alias="p")
    metadata_owner_sql, metadata_owner_params = _workspace_metadata_owner_where(scope)
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT rfa.workspace_path, COUNT(DISTINCT rfa.id) AS artifact_count, "  # nosec
            "COUNT(DISTINCT rfa.run_id) AS run_count, MAX(r.started) AS last_seen, "
            f"{project_names_expr} AS project_names "
            "FROM run_file_artifacts rfa "
            "LEFT JOIN runs r ON r.id = rfa.run_id "
            "LEFT JOIN project_links pl ON pl.entity_type = 'run' AND pl.entity_id = rfa.run_id "
            "LEFT JOIN projects p ON p.id = pl.project_id AND " + project_owner_sql + " "
            "WHERE " + run_owner_sql + " "
            f"AND rfa.workspace_path IN ({placeholders}) "
            "GROUP BY rfa.workspace_path",
            [*project_owner_params, *run_owner_params, *clean_paths],
        ).fetchall()
        label_rows = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, label, source, created "  # nosec
            "FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "
            f"AND entity_id IN ({placeholders}) "
            f"ORDER BY {label_order_sql}",
            [*metadata_owner_params, *clean_paths],
        ).fetchall()
        note_rows = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, body, created, updated "  # nosec
            "FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *clean_paths],
        ).fetchall()
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        project_names = [
            name for name in str(row["project_names"] or "").split(",")
            if name
        ]
        metadata[str(row["workspace_path"])] = {
            "artifact_count": int(row["artifact_count"] or 0),
            "artifact_run_count": int(row["run_count"] or 0),
            "artifact_last_seen": row["last_seen"] or "",
            "project_names": project_names,
        }
    for row in label_rows:
        path = str(row["entity_id"])
        item = metadata.setdefault(path, {})
        item.setdefault("labels", []).append({
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "label": row["label"],
            "source": row["source"],
            "created": row["created"],
        })
    for row in note_rows:
        path = str(row["entity_id"])
        item = metadata.setdefault(path, {})
        item["note"] = {
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "body": row["body"],
            "created": row["created"],
            "updated": row["updated"],
        }
    return metadata


def delete_workspace_file_metadata(scope: Any, paths: list[str]) -> None:
    from core.database import db_connect  # noqa: PLC0415

    clean_paths = sorted({str(path) for path in paths if path})
    if not clean_paths:
        return
    placeholders = ",".join("?" for _ in clean_paths)
    metadata_owner_sql, metadata_owner_params = _workspace_metadata_owner_where(scope)
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *clean_paths],
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *clean_paths],
        )
        conn.commit()


def move_workspace_file_metadata(scope: Any, path_map: dict[str, str]) -> None:
    from core.database import db_connect  # noqa: PLC0415

    clean_map = {
        str(source): str(destination)
        for source, destination in path_map.items()
        if source and destination and str(source) != str(destination)
    }
    if not clean_map:
        return
    destinations = sorted(set(clean_map.values()))
    placeholders = ",".join("?" for _ in destinations)
    metadata_owner_sql, metadata_owner_params = _workspace_metadata_owner_where(scope)
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *destinations],
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *destinations],
        )
        for source, destination in clean_map.items():
            conn.execute(  # nosec
                "UPDATE entity_labels SET entity_id = ? "  # nosec
                "WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' AND entity_id = ?",
                (destination, *metadata_owner_params, source),
            )
            conn.execute(  # nosec
                "UPDATE entity_notes SET entity_id = ? "  # nosec
                "WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' AND entity_id = ?",
                (destination, *metadata_owner_params, source),
            )
        conn.commit()

