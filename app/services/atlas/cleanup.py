"""Cleanup helpers for Session Entity Atlas rows."""

from __future__ import annotations

from typing import Any

from core.database import DB_BACKEND
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.storage.body_store import delete_text_body

_ATLAS_CLEANUP_TEMP_TABLES = (
    "atlas_cleanup_run_ids",
    "atlas_cleanup_excluded_entities",
    "atlas_cleanup_excluded_findings",
    "atlas_cleanup_allowed_findings",
)


def _unique_ids(values: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)


def _insert_ignore_sql(table: str) -> str:
    return f"INSERT INTO {table} (id) VALUES (?) {dialect_for_backend(DB_BACKEND).insert_or_ignore_clause(('id',))}"  # nosec


def _create_cleanup_temp_table(conn, table_name: str) -> None:
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        conn.execute(f"DROP TABLE IF EXISTS pg_temp.{table_name}")  # nosec
        conn.execute(
            f"CREATE TEMP TABLE {table_name} (id TEXT PRIMARY KEY) ON COMMIT DROP"  # nosec
        )
        return
    conn.execute(f"CREATE TEMP TABLE IF NOT EXISTS {table_name} (id TEXT PRIMARY KEY)")  # nosec


def _public_preview(preview: dict[str, Any]) -> dict[str, Any]:
    entity_count = len(preview.get("entity_ids") or [])
    finding_count = len(preview.get("finding_ids") or [])
    curated_entity_count = int(preview.get("curated_entity_count") or 0)
    curated_finding_count = int(preview.get("curated_finding_count") or 0)
    return {
        "entities": entity_count,
        "findings": finding_count,
        "curated_entities": curated_entity_count,
        "curated_findings": curated_finding_count,
        "curated_total": curated_entity_count + curated_finding_count,
        "total": entity_count + finding_count,
        "has_cleanup": bool(entity_count or finding_count),
    }


def public_cleanup_preview(preview: dict[str, Any]) -> dict[str, Any]:
    """Return a client-safe cleanup preview without internal ids."""
    return _public_preview(preview)


def _finding_curated_sql() -> str:
    return (
        "COALESCE(NULLIF(f.status, ''), 'new') != 'new' "
        "OR COALESCE(NULLIF(f.review_state, ''), 'new') != 'new' "
        "OR EXISTS ("
        "  SELECT 1 FROM project_links finding_link "
        "  WHERE finding_link.entity_type = 'finding' "
        "  AND finding_link.entity_id = f.id"
        ") "
        "OR EXISTS ("
        "  SELECT 1 FROM entity_labels finding_label "
        "  WHERE finding_label.entity_type = 'finding' "
        "  AND finding_label.entity_id = f.id"
        ") "
        "OR EXISTS ("
        "  SELECT 1 FROM entity_notes finding_note "
        "  WHERE finding_note.entity_type = 'finding' "
        "  AND finding_note.entity_id = f.id"
        ")"
    )


def _entity_curated_sql() -> str:
    return (
        "EXISTS ("
        "  SELECT 1 FROM project_links entity_link "
        "  JOIN projects entity_project ON entity_project.id = entity_link.project_id "
        "  WHERE entity_link.entity_type = 'atlas_entity' "
        "  AND entity_link.entity_id = e.id "
        "  AND entity_project.session_id = e.session_id"
        ") "
        "OR EXISTS ("
        "  SELECT 1 FROM entity_labels entity_label "
        "  WHERE entity_label.entity_type = 'atlas_entity' "
        "  AND entity_label.entity_id = e.id"
        ") "
        "OR EXISTS ("
        "  SELECT 1 FROM entity_notes entity_note "
        "  WHERE entity_note.entity_type = 'atlas_entity' "
        "  AND entity_note.entity_id = e.id"
        ")"
    )


def atlas_run_cleanup_preview(
    conn,
    session_id: str,
    run_ids: list[str] | tuple[str, ...] | set[str],
    *,
    exclude_entity_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    exclude_finding_ids: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, Any]:
    """Find non-curated Atlas rows only linked to the given run ids."""
    ids = _unique_ids(run_ids)
    excluded_entities = _unique_ids(exclude_entity_ids)
    excluded_findings = _unique_ids(exclude_finding_ids)
    if not ids:
        return {
            "run_ids": [],
            "entity_ids": [],
            "finding_ids": [],
            "curated_entity_count": 0,
            "curated_finding_count": 0,
        }

    for table_name in _ATLAS_CLEANUP_TEMP_TABLES:
        _create_cleanup_temp_table(conn, table_name)
    conn.execute("DELETE FROM atlas_cleanup_run_ids")
    conn.execute("DELETE FROM atlas_cleanup_excluded_entities")
    conn.execute("DELETE FROM atlas_cleanup_excluded_findings")
    conn.execute("DELETE FROM atlas_cleanup_allowed_findings")
    conn.executemany(_insert_ignore_sql("atlas_cleanup_run_ids"), [(item,) for item in ids])
    conn.executemany(
        _insert_ignore_sql("atlas_cleanup_excluded_entities"),
        [(item,) for item in excluded_entities],
    )
    conn.executemany(
        _insert_ignore_sql("atlas_cleanup_excluded_findings"),
        [(item,) for item in excluded_findings],
    )

    finding_base = (
        "FROM findings f "
        "JOIN findings_occurrences fo ON fo.finding_id = f.id "
        "JOIN runs source_run ON source_run.id = fo.run_id AND source_run.session_id = f.session_id "
        "WHERE f.session_id = ? "
        "AND fo.run_id IN (SELECT id FROM atlas_cleanup_run_ids) "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM findings_occurrences other_fo "
        "  JOIN runs other_run ON other_run.id = other_fo.run_id AND other_run.session_id = f.session_id "
        "  WHERE other_fo.finding_id = f.id "
        "  AND other_fo.run_id NOT IN (SELECT id FROM atlas_cleanup_run_ids)"
        ") "
        "AND NOT EXISTS (SELECT 1 FROM atlas_cleanup_excluded_findings excluded WHERE excluded.id = f.id) "
    )
    finding_params = [session_id]
    finding_curated = _finding_curated_sql()
    finding_rows = conn.execute(
        "SELECT DISTINCT f.id " + finding_base + f"AND NOT ({finding_curated})",
        finding_params,
    ).fetchall()
    curated_finding_count = int(conn.execute(
        "SELECT COUNT(DISTINCT f.id) AS count " + finding_base + f"AND ({finding_curated})",
        finding_params,
    ).fetchone()["count"] or 0)

    excluded_findings_for_entities = _unique_ids([row["id"] for row in finding_rows] + excluded_findings)
    conn.executemany(
        _insert_ignore_sql("atlas_cleanup_allowed_findings"),
        [(item,) for item in excluded_findings_for_entities],
    )

    entity_base = (
        "FROM entities e "
        "JOIN entity_run_links erl ON erl.entity_id = e.id "
        "JOIN runs source_run ON source_run.id = erl.run_id AND source_run.session_id = e.session_id "
        "WHERE e.session_id = ? "
        "AND erl.run_id IN (SELECT id FROM atlas_cleanup_run_ids) "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM entity_run_links other_erl "
        "  JOIN runs other_run ON other_run.id = other_erl.run_id AND other_run.session_id = e.session_id "
        "  WHERE other_erl.entity_id = e.id "
        "  AND other_erl.run_id NOT IN (SELECT id FROM atlas_cleanup_run_ids)"
        ") "
        "AND NOT EXISTS (SELECT 1 FROM atlas_cleanup_excluded_entities excluded WHERE excluded.id = e.id) "
    )
    entity_params = [session_id]
    entity_curated = _entity_curated_sql()
    entity_child_block = (
        "AND NOT EXISTS ("
        "  SELECT 1 FROM findings child_f "
        "  WHERE child_f.session_id = e.session_id "
        "  AND child_f.entity_id = e.id "
        "  AND child_f.id NOT IN (SELECT id FROM atlas_cleanup_allowed_findings)"
        ") "
    )
    entity_rows = conn.execute(
        "SELECT DISTINCT e.id "
        + entity_base
        + f"AND NOT ({entity_curated}) "
        + entity_child_block,
        entity_params,
    ).fetchall()
    curated_entity_count = int(conn.execute(
        "SELECT COUNT(DISTINCT e.id) AS count " + entity_base + f"AND ({entity_curated})",
        entity_params,
    ).fetchone()["count"] or 0)

    return {
        "run_ids": ids,
        "entity_ids": [str(row["id"]) for row in entity_rows if row["id"]],
        "finding_ids": [str(row["id"]) for row in finding_rows if row["id"]],
        "curated_entity_count": curated_entity_count,
        "curated_finding_count": curated_finding_count,
    }


def delete_atlas_findings(conn, session_id: str, finding_ids: list[str] | tuple[str, ...] | set[str]) -> int:
    ids = _unique_ids(finding_ids)
    if not ids:
        return 0
    placeholders = _placeholders(ids)
    params = [session_id, *ids]
    owned = [
        str(row["id"])
        for row in conn.execute(
            f"SELECT id FROM findings WHERE session_id = ? AND id IN ({placeholders})",  # nosec
            params,
        ).fetchall()
    ]
    if not owned:
        return 0
    owned_placeholders = _placeholders(owned)
    conn.execute(
        "DELETE FROM project_links WHERE entity_type = 'finding' "  # nosec
        f"AND entity_id IN ({owned_placeholders})",
        owned,
    )
    conn.execute(
        "DELETE FROM entity_labels WHERE entity_type = 'finding' "  # nosec
        f"AND entity_id IN ({owned_placeholders})",
        owned,
    )
    conn.execute(
        "DELETE FROM entity_notes WHERE entity_type = 'finding' "  # nosec
        f"AND entity_id IN ({owned_placeholders})",
        owned,
    )
    conn.execute(
        f"DELETE FROM findings_occurrences WHERE finding_id IN ({owned_placeholders})",  # nosec
        owned,
    )
    cur = conn.execute(
        f"DELETE FROM findings WHERE session_id = ? AND id IN ({owned_placeholders})",  # nosec
        [session_id, *owned],
    )
    return int(cur.rowcount or 0)


def delete_atlas_entities(conn, session_id: str, entity_ids: list[str] | tuple[str, ...] | set[str]) -> dict[str, int]:
    ids = _unique_ids(entity_ids)
    if not ids:
        return {"entities": 0, "findings": 0}
    placeholders = _placeholders(ids)
    owned = [
        str(row["id"])
        for row in conn.execute(
            f"SELECT id FROM entities WHERE session_id = ? AND id IN ({placeholders})",  # nosec
            [session_id, *ids],
        ).fetchall()
    ]
    if not owned:
        return {"entities": 0, "findings": 0}
    owned_placeholders = _placeholders(owned)
    finding_rows = conn.execute(
        f"SELECT id FROM findings WHERE session_id = ? AND entity_id IN ({owned_placeholders})",  # nosec
        [session_id, *owned],
    ).fetchall()
    deleted_findings = delete_atlas_findings(conn, session_id, [str(row["id"]) for row in finding_rows if row["id"]])
    conn.execute(
        "DELETE FROM project_links WHERE entity_type = 'atlas_entity' "  # nosec
        f"AND entity_id IN ({owned_placeholders})",
        owned,
    )
    conn.execute(
        "DELETE FROM entity_labels WHERE entity_type = 'atlas_entity' "  # nosec
        f"AND entity_id IN ({owned_placeholders})",
        owned,
    )
    conn.execute(
        "DELETE FROM entity_notes WHERE entity_type = 'atlas_entity' "  # nosec
        f"AND entity_id IN ({owned_placeholders})",
        owned,
    )
    intel_rows = conn.execute(
        f"SELECT data_json FROM entity_intel_snapshots WHERE session_id = ? AND entity_id IN ({owned_placeholders})",  # nosec
        [session_id, *owned],
    ).fetchall()
    conn.execute(
        f"DELETE FROM entity_intel_snapshots WHERE session_id = ? AND entity_id IN ({owned_placeholders})",  # nosec
        [session_id, *owned],
    )
    for row in intel_rows:
        delete_text_body(row["data_json"])
    conn.execute(
        f"DELETE FROM entity_run_links WHERE entity_id IN ({owned_placeholders})",  # nosec
        owned,
    )
    cur = conn.execute(
        f"DELETE FROM entities WHERE session_id = ? AND id IN ({owned_placeholders})",  # nosec
        [session_id, *owned],
    )
    return {"entities": int(cur.rowcount or 0), "findings": deleted_findings}


def delete_atlas_cleanup_preview(conn, session_id: str, preview: dict[str, Any]) -> dict[str, int]:
    deleted_findings = delete_atlas_findings(conn, session_id, preview.get("finding_ids") or [])
    deleted_entities = delete_atlas_entities(conn, session_id, preview.get("entity_ids") or [])
    return {
        "entities": int(deleted_entities.get("entities") or 0),
        "findings": deleted_findings + int(deleted_entities.get("findings") or 0),
    }


def atlas_entity_delete_preview(conn, session_id: str, entity_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id FROM entities WHERE session_id = ? AND id = ?",
        (session_id, entity_id),
    ).fetchone()
    if not row:
        return None
    run_rows = conn.execute(
        "SELECT erl.run_id FROM entity_run_links erl "
        "JOIN runs r ON r.id = erl.run_id AND r.session_id = ? "
        "WHERE erl.entity_id = ?",
        (session_id, entity_id),
    ).fetchall()
    attached_findings = [
        str(finding["id"])
        for finding in conn.execute(
            "SELECT id FROM findings WHERE session_id = ? AND entity_id = ?",
            (session_id, entity_id),
        ).fetchall()
        if finding["id"]
    ]
    run_ids = [str(run["run_id"]) for run in run_rows if run["run_id"]]
    sibling_preview = None
    source_run_id = run_ids[0] if len(set(run_ids)) == 1 else ""
    if source_run_id:
        sibling_preview = atlas_run_cleanup_preview(
            conn,
            session_id,
            [source_run_id],
            exclude_entity_ids=[entity_id],
            exclude_finding_ids=attached_findings,
        )
    return {
        "entity_id": entity_id,
        "attached_finding_ids": attached_findings,
        "source_run_id": source_run_id,
        "sibling_cleanup": _public_preview(sibling_preview or {}),
    }


def atlas_finding_delete_preview(conn, session_id: str, finding_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, last_run_id FROM findings WHERE session_id = ? AND id = ?",
        (session_id, finding_id),
    ).fetchone()
    if not row:
        return None
    run_rows = conn.execute(
        "SELECT DISTINCT fo.run_id FROM findings_occurrences fo "
        "JOIN runs r ON r.id = fo.run_id AND r.session_id = ? "
        "WHERE fo.finding_id = ?",
        (session_id, finding_id),
    ).fetchall()
    run_ids = [str(run["run_id"]) for run in run_rows if run["run_id"]]
    if not run_ids and row["last_run_id"]:
        last_run = conn.execute(
            "SELECT id FROM runs WHERE session_id = ? AND id = ?",
            (session_id, row["last_run_id"]),
        ).fetchone()
        if last_run:
            run_ids = [str(row["last_run_id"])]
    source_run_id = run_ids[0] if len(set(run_ids)) == 1 else ""
    sibling_preview = None
    if source_run_id:
        sibling_preview = atlas_run_cleanup_preview(
            conn,
            session_id,
            [source_run_id],
            exclude_finding_ids=[finding_id],
        )
    return {
        "finding_id": finding_id,
        "source_run_id": source_run_id,
        "sibling_cleanup": _public_preview(sibling_preview or {}),
    }
