"""Shared database storage diagnostics for /diag and Prometheus."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.database_backend import (
    DatabaseBackend,
    postgres_storage_rows,
    postgres_table_names,
    postgres_table_row_count,
    quote_identifier,
    quote_sqlite_identifier,
    sqlite_compileoption_used,
    sqlite_dbstat_rows,
    sqlite_fts_orphan_count,
    sqlite_fts_virtual_table_names,
    sqlite_page_stats,
    sqlite_schema_objects,
    sqlite_table_columns,
    sqlite_table_names,
    sqlite_table_row_count,
)


PROJECT_WORKSPACE_COUNT_TABLES = {
    "projects": "projects",
    "project_links": "links",
    "run_file_artifacts": "artifacts",
    "findings": "findings",
    "entity_labels": "labels",
    "entity_notes": "notes",
    "evidence_packages": "packages",
}
_FTS_SHADOW_SUFFIXES = ("_data", "_idx", "_content", "_docsize", "_config")
_STORAGE_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Runs and transcripts", (
        "runs",
        "runs_fts",
        "run_output_artifacts",
    )),
    ("Snapshots and permalinks", (
        "snapshots",
    )),
    ("Atlas and findings", (
        "entities",
        "entity_run_links",
        "entity_intel_snapshots",
        "findings",
        "findings_occurrences",
        "entity_labels",
        "entity_notes",
    )),
    ("Projects and workspace", (
        "projects",
        "project_links",
        "run_file_artifacts",
        "evidence_packages",
    )),
    ("Session data", (
        "session_tokens",
        "session_preferences",
        "starred_commands",
        "session_variables",
        "user_workflows",
        "recent_values",
    )),
    ("Security", (
        "secrets",
    )),
)
_STORAGE_BUCKET_BY_TABLE = {
    table_name: bucket_name
    for bucket_name, table_names in _STORAGE_BUCKETS
    for table_name in table_names
}
_PAYLOAD_COLUMNS = {
    "runs": ("command", "output", "output_preview", "output_search_text"),
    "run_output_artifacts": ("rel_path", "compression"),
    "run_file_artifacts": ("workspace_path", "display_name", "kind", "content_type", "preview_type", "content_sha256"),
    "snapshots": ("label", "content"),
    "entities": ("type", "canonical_value", "signature_hash"),
    "entity_run_links": ("entity_id", "run_id"),
    "entity_intel_snapshots": ("provider", "status", "summary", "data_json"),
    "findings": (
        "target_id", "scope", "entity_id", "subject_key", "signature_hash",
        "severity", "kind", "tool_root", "title", "raw_line",
    ),
    "findings_occurrences": ("finding_id", "run_id", "snippet"),
    "projects": ("name", "slug", "description", "status", "color"),
    "project_links": ("entity_type", "entity_id", "source", "review_state", "source_detail"),
    "evidence_packages": ("name", "description", "redaction_mode", "manifest", "status"),
    "session_tokens": ("token",),
    "session_preferences": ("session_id", "preferences"),
    "starred_commands": ("session_id", "command"),
    "session_variables": ("session_id", "name", "value"),
    "user_workflows": ("session_id", "title", "description", "inputs", "steps"),
    "recent_values": ("session_id", "kind", "value"),
    "secrets": ("session_token", "name", "ciphertext", "nonce", "consumer_envs"),
    "entity_labels": ("entity_type", "entity_id", "label", "source"),
    "entity_notes": ("entity_type", "entity_id", "body"),
}
_PAYLOAD_BYTE_COLUMNS = {
    "run_output_artifacts": ("byte_size",),
    "run_file_artifacts": ("byte_size",),
}
_LARGEST_RUNS_LIMIT = 10
_LARGEST_RUNS_ROWCOUNT_LIMIT = 100_000
_LARGEST_RUNS_SQL_BY_COLUMNS = {
    (): (
        "SELECT id, command, 0 AS payload_bytes "
        "FROM runs ORDER BY payload_bytes DESC LIMIT ?"
    ),
    ("output",): (
        "SELECT id, command, LENGTH(COALESCE(output, '')) AS payload_bytes "
        "FROM runs ORDER BY payload_bytes DESC LIMIT ?"
    ),
    ("output_preview",): (
        "SELECT id, command, LENGTH(COALESCE(output_preview, '')) AS payload_bytes "
        "FROM runs ORDER BY payload_bytes DESC LIMIT ?"
    ),
    ("output_search_text",): (
        "SELECT id, command, LENGTH(COALESCE(output_search_text, '')) AS payload_bytes "
        "FROM runs ORDER BY payload_bytes DESC LIMIT ?"
    ),
    ("output", "output_preview"): (
        "SELECT id, command, "
        "(LENGTH(COALESCE(output, '')) + LENGTH(COALESCE(output_preview, ''))) AS payload_bytes "
        "FROM runs ORDER BY payload_bytes DESC LIMIT ?"
    ),
    ("output", "output_search_text"): (
        "SELECT id, command, "
        "(LENGTH(COALESCE(output, '')) + LENGTH(COALESCE(output_search_text, ''))) AS payload_bytes "
        "FROM runs ORDER BY payload_bytes DESC LIMIT ?"
    ),
    ("output_preview", "output_search_text"): (
        "SELECT id, command, "
        "(LENGTH(COALESCE(output_preview, '')) + LENGTH(COALESCE(output_search_text, ''))) AS payload_bytes "
        "FROM runs ORDER BY payload_bytes DESC LIMIT ?"
    ),
    ("output", "output_preview", "output_search_text"): (
        "SELECT id, command, "
        "(LENGTH(COALESCE(output, '')) + LENGTH(COALESCE(output_preview, '')) + "
        "LENGTH(COALESCE(output_search_text, ''))) AS payload_bytes "
        "FROM runs ORDER BY payload_bytes DESC LIMIT ?"
    ),
}
_SNAPSHOT_CACHE_TTL_SECONDS = 8.0
_SNAPSHOT_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def format_bytes(n: Any) -> str:
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.1f} GB"


def _row_value(row: Any, key: str, index: int, default: Any = None) -> Any:
    if hasattr(row, "keys"):
        try:
            return row[key]
        except KeyError:
            pass
    try:
        return row[index]
    except (IndexError, KeyError, TypeError):
        return default


def _fts_parent_for_shadow(name: str, virtual_names: set[str]) -> str | None:
    for parent in virtual_names:
        if any(name == f"{parent}{suffix}" for suffix in _FTS_SHADOW_SUFFIXES):
            return parent
    return None


def _storage_bucket_for_table(name: str, kind: str = "table") -> str:
    if kind == "index":
        return "Indexes"
    return _STORAGE_BUCKET_BY_TABLE.get(name, "Other")


def _sum_payload_expr(
    text_columns: tuple[str, ...],
    byte_columns: tuple[str, ...] = (),
    *,
    backend: DatabaseBackend = DatabaseBackend.SQLITE,
) -> str:
    parts = [
        "COALESCE(SUM(LENGTH(COALESCE("
        + quote_identifier(column, backend)
        + ("::text" if backend == DatabaseBackend.POSTGRES else "")
        + ", ''))), 0)"
        for column in text_columns
    ]
    parts.extend(
        "COALESCE(SUM(" + quote_identifier(column, backend) + "), 0)"
        for column in byte_columns
    )
    return " + ".join(parts) or "0"


def _postgres_table_columns_by_table(conn: Any) -> dict[str, set[str]]:
    rows = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema()"
    ).fetchall()
    columns: dict[str, set[str]] = {}
    for row in rows:
        table_name = str(_row_value(row, "table_name", 0) or "")
        column_name = str(_row_value(row, "column_name", 1) or "")
        if table_name and column_name:
            columns.setdefault(table_name, set()).add(column_name)
    return columns


def _finalize_entries(entries: dict[str, dict[str, Any]], *, sqlite_dbstat_available: bool = True) -> dict[str, Any]:
    for entry in entries.values():
        for key in ("allocated", "payload", "overhead", "unused", "logical_payload"):
            value = entry.get(key)
            entry[f"{key}_human"] = format_bytes(value) if value is not None else "—"
        rows = entry.get("rows")
        logical_payload = entry.get("logical_payload")
        entry["avg_row_payload"] = (
            int(logical_payload / rows)
            if rows and logical_payload is not None
            else None
        )
        entry["avg_row_payload_human"] = (
            format_bytes(entry["avg_row_payload"])
            if entry["avg_row_payload"] is not None
            else "—"
        )
        entry["shadows"] = sorted(entry.get("shadows") or [], key=lambda item: item.get("allocated") or 0, reverse=True)

    bucket_map: dict[str, dict[str, Any]] = {}
    bucket_order = [name for name, _ in _STORAGE_BUCKETS] + ["Indexes", "Other"]
    for entry in entries.values():
        bucket_name = str(entry.get("bucket") or "Other")
        bucket = bucket_map.setdefault(bucket_name, {
            "name": bucket_name,
            "allocated": 0,
            "payload": 0,
            "logical_payload": 0,
            "rows": [],
        })
        bucket["rows"].append(entry)
        for key in ("allocated", "payload", "logical_payload"):
            bucket[key] += int(entry.get(key) or 0)

    buckets = []
    for bucket_name in bucket_order:
        bucket = bucket_map.get(bucket_name)
        if not bucket:
            continue
        bucket["rows"].sort(key=lambda item: (
            int(item.get("allocated") or 0),
            int(item.get("logical_payload") or 0),
            str(item.get("name") or ""),
        ), reverse=True)
        for key in ("allocated", "payload", "logical_payload"):
            bucket[f"{key}_human"] = (
                format_bytes(bucket[key])
                if sqlite_dbstat_available or key == "logical_payload"
                else "—"
            )
        buckets.append(bucket)

    total_allocated = sum(int(entry.get("allocated") or 0) for entry in entries.values())
    total_payload = sum(int(entry.get("payload") or 0) for entry in entries.values())
    total_logical = sum(int(entry.get("logical_payload") or 0) for entry in entries.values())
    result: dict[str, Any] = {
        "buckets": buckets,
        "total_allocated_bytes": total_allocated,
        "total_payload_bytes": total_payload,
        "total_logical_payload_bytes": total_logical,
        "wasted_bytes": max(0, total_allocated - total_payload),
    }
    for key in ("total_allocated_bytes", "total_payload_bytes", "total_logical_payload_bytes", "wasted_bytes"):
        result[f"{key}_human"] = format_bytes(result[key])

    largest_entry = max(
        entries.values(),
        key=lambda item: (int(item.get("allocated") or 0), int(item.get("logical_payload") or 0)),
        default=None,
    )
    if largest_entry:
        result["largest_object"] = {
            "name": largest_entry.get("name"),
            "allocated": largest_entry.get("allocated"),
            "allocated_human": largest_entry.get("allocated_human"),
            "logical_payload": largest_entry.get("logical_payload"),
            "logical_payload_human": largest_entry.get("logical_payload_human"),
        }
    return result


def _postgres_table_storage_breakdown(conn: Any, table_counts: dict[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "backend": "postgres",
        "dbstat_available": False,
        "storage_stats_available": True,
        "buckets": [],
        "largest_runs": [],
        "total_allocated_bytes": 0,
        "total_payload_bytes": 0,
        "total_logical_payload_bytes": 0,
        "wasted_bytes": 0,
        "errors": [],
    }
    entries: dict[str, dict[str, Any]] = {}
    try:
        rows = postgres_storage_rows(conn)
    except Exception as exc:
        rows = []
        result["storage_stats_available"] = False
        result["errors"].append(f"Postgres storage aggregate failed: {exc}")

    for row in rows:
        name = str(_row_value(row, "name", 0) or "")
        relkind = str(_row_value(row, "kind", 1) or "")
        kind = "index" if relkind == "i" else "table"
        allocated = int(_row_value(row, "allocated", 2, 0) or 0)
        payload = int(_row_value(row, "payload", 3, 0) or 0)
        overhead = int(_row_value(row, "overhead", 4, 0) or 0)
        estimated_rows = _row_value(row, "rows", 5)
        entries[name] = {
            "name": name,
            "kind": kind,
            "bucket": _storage_bucket_for_table(name, kind),
            "rows": table_counts.get(name, int(estimated_rows or 0) if kind != "index" else None),
            "allocated": allocated,
            "payload": payload,
            "overhead": overhead,
            "unused": None,
            "pages": None,
            "logical_payload": None,
            "shadows": [],
        }

    for table_name, count in table_counts.items():
        entries.setdefault(table_name, {
            "name": table_name,
            "kind": "table",
            "bucket": _storage_bucket_for_table(table_name),
            "rows": count,
            "allocated": None,
            "payload": None,
            "overhead": None,
            "unused": None,
            "pages": None,
            "logical_payload": None,
            "shadows": [],
        })

    columns_by_table = _postgres_table_columns_by_table(conn)
    for table_name, columns in _PAYLOAD_COLUMNS.items():
        if table_name not in entries:
            continue
        try:
            live_columns = columns_by_table.get(table_name, set())
            selected_text = tuple(column for column in columns if column in live_columns)
            selected_bytes = tuple(
                column for column in _PAYLOAD_BYTE_COLUMNS.get(table_name, ())
                if column in live_columns
            )
            if not selected_text and not selected_bytes:
                entries[table_name]["logical_payload"] = 0
                continue
            expr = _sum_payload_expr(selected_text, selected_bytes, backend=DatabaseBackend.POSTGRES)
            value = conn.execute(
                "SELECT " + expr + " AS value FROM " + quote_identifier(table_name, DatabaseBackend.POSTGRES),  # nosec
            ).fetchone()
            entries[table_name]["logical_payload"] = int(_row_value(value, "value", 0, 0) or 0)
        except Exception as exc:
            entries[table_name]["payload_error"] = str(exc)

    result.update(_finalize_entries(entries))
    _attach_largest_object_bytes(result, entries)

    try:
        if "runs" in entries:
            live_run_columns = columns_by_table.get("runs", set())
            required_columns = {"id", "command"}
            if not required_columns.issubset(live_run_columns):
                raise ValueError("runs table is missing required identity columns")
            payload_columns = tuple(
                column
                for column in ("output", "output_preview", "output_search_text")
                if column in live_run_columns
            )
            rows = conn.execute(
                _LARGEST_RUNS_SQL_BY_COLUMNS[payload_columns],
                (_LARGEST_RUNS_LIMIT,),
            ).fetchall()
            result["largest_runs"] = _largest_run_rows(rows)
    except Exception as exc:
        result["errors"].append(f"largest runs probe failed: {exc}")
    return result


def _sqlite_table_storage_breakdown(conn: Any, table_counts: dict[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "backend": "sqlite",
        "dbstat_available": False,
        "storage_stats_available": False,
        "buckets": [],
        "largest_runs": [],
        "total_allocated_bytes": 0,
        "total_payload_bytes": 0,
        "total_logical_payload_bytes": 0,
        "wasted_bytes": 0,
        "errors": [],
    }
    master: dict[str, dict[str, str]] = {}
    virtual_names: set[str] = set()

    try:
        rows = sqlite_schema_objects(conn)
        for row in rows:
            name = str(_row_value(row, "name", 0) or "")
            obj_type = str(_row_value(row, "type", 1) or "")
            tbl_name = str(_row_value(row, "tbl_name", 2) or "")
            sql = str(_row_value(row, "sql", 3, "") or "")
            master[name] = {"type": obj_type, "tbl_name": tbl_name, "sql": sql}
            if sql.upper().startswith("CREATE VIRTUAL TABLE") and "FTS" in sql.upper():
                virtual_names.add(name)
    except Exception as exc:
        result["errors"].append(f"schema listing failed: {exc}")

    try:
        result["dbstat_available"] = sqlite_compileoption_used(conn, "ENABLE_DBSTAT_VTAB")
    except Exception as exc:
        result["errors"].append(f"dbstat probe failed: {exc}")

    entries: dict[str, dict[str, Any]] = {}
    for name, meta in master.items():
        obj_type = meta.get("type")
        if obj_type == "table" and _fts_parent_for_shadow(name, virtual_names):
            continue
        kind = "index" if obj_type == "index" else "table"
        if name in virtual_names:
            kind = "virtual-table"
        entries[name] = {
            "name": name,
            "kind": kind,
            "bucket": _storage_bucket_for_table(name, kind),
            "rows": table_counts.get(name),
            "allocated": None,
            "payload": None,
            "overhead": None,
            "unused": None,
            "pages": None,
            "logical_payload": None,
            "shadows": [],
        }

    if result["dbstat_available"]:
        try:
            rows = sqlite_dbstat_rows(conn)
            result["storage_stats_available"] = True
            for row in rows:
                name = str(_row_value(row, "name", 0) or "")
                allocated = int(_row_value(row, "allocated", 1, 0) or 0)
                payload = int(_row_value(row, "payload", 2, 0) or 0)
                overhead = int(_row_value(row, "overhead", 3, 0) or 0)
                unused = int(_row_value(row, "unused", 4, 0) or 0)
                pages = int(_row_value(row, "pages", 5, 0) or 0)
                parent = _fts_parent_for_shadow(name, virtual_names)
                if parent:
                    parent_entry = entries.setdefault(parent, {
                        "name": parent,
                        "kind": "virtual-table",
                        "bucket": _storage_bucket_for_table(parent),
                        "rows": table_counts.get(parent),
                        "allocated": 0,
                        "payload": 0,
                        "overhead": 0,
                        "unused": 0,
                        "pages": 0,
                        "logical_payload": None,
                        "shadows": [],
                    })
                    for key, value in (
                        ("allocated", allocated), ("payload", payload),
                        ("overhead", overhead), ("unused", unused), ("pages", pages),
                    ):
                        parent_entry[key] = int(parent_entry.get(key) or 0) + value
                    parent_entry["shadows"].append({
                        "name": name,
                        "allocated": allocated,
                        "allocated_human": format_bytes(allocated),
                        "payload": payload,
                        "payload_human": format_bytes(payload),
                        "pages": pages,
                    })
                    continue
                entry = entries.get(name)
                if not entry:
                    kind = "index" if name.startswith("sqlite_autoindex_") else "other"
                    if master.get(name, {}).get("type") == "index":
                        kind = "index"
                    entry = entries[name] = {
                        "name": name,
                        "kind": kind,
                        "bucket": _storage_bucket_for_table(name, kind),
                        "rows": table_counts.get(name),
                        "logical_payload": None,
                        "shadows": [],
                    }
                entry.update({
                    "allocated": allocated,
                    "payload": payload,
                    "overhead": overhead,
                    "unused": unused,
                    "pages": pages,
                })
        except Exception as exc:
            result["dbstat_available"] = False
            result["errors"].append(f"dbstat aggregate failed: {exc}")

    for table_name, columns in _PAYLOAD_COLUMNS.items():
        if table_name not in entries:
            continue
        try:
            live_columns = sqlite_table_columns(conn, table_name)
            selected_text = tuple(column for column in columns if column in live_columns)
            selected_bytes = tuple(
                column for column in _PAYLOAD_BYTE_COLUMNS.get(table_name, ())
                if column in live_columns
            )
            if not selected_text and not selected_bytes:
                entries[table_name]["logical_payload"] = 0
                continue
            expr = _sum_payload_expr(selected_text, selected_bytes)
            value = conn.execute(
                "SELECT " + expr + " FROM " + quote_sqlite_identifier(table_name),  # nosec
            ).fetchone()[0]
            entries[table_name]["logical_payload"] = int(value or 0)
        except Exception as exc:
            entries[table_name]["payload_error"] = str(exc)

    for entry in entries.values():
        if entry.get("rows") is None and entry.get("kind") != "index":
            entry["rows"] = table_counts.get(entry["name"])
    result.update(_finalize_entries(entries, sqlite_dbstat_available=bool(result["dbstat_available"])))
    _attach_largest_object_bytes(result, entries)

    try:
        runs_count = int(table_counts.get("runs") or 0)
        if "runs" in entries and (result["dbstat_available"] or runs_count < _LARGEST_RUNS_ROWCOUNT_LIMIT):
            live_run_columns = sqlite_table_columns(conn, "runs")
            required_columns = {"id", "command"}
            if not required_columns.issubset(live_run_columns):
                raise ValueError("runs table is missing required identity columns")
            payload_columns = tuple(
                column
                for column in ("output", "output_preview", "output_search_text")
                if column in live_run_columns
            )
            rows = conn.execute(
                _LARGEST_RUNS_SQL_BY_COLUMNS[payload_columns],
                (_LARGEST_RUNS_LIMIT,),
            ).fetchall()
            result["largest_runs"] = _largest_run_rows(rows)
        elif "runs" in entries:
            result["largest_runs_skipped"] = f"runs row count is {runs_count:,}"
    except Exception as exc:
        result["errors"].append(f"largest runs probe failed: {exc}")
    return result


def _attach_largest_object_bytes(result: dict[str, Any], entries: dict[str, dict[str, Any]]) -> None:
    largest_entry = max(
        entries.values(),
        key=lambda item: (int(item.get("allocated") or 0), int(item.get("logical_payload") or 0)),
        default=None,
    )
    if largest_entry:
        result["largest_object"] = {
            "name": largest_entry.get("name"),
            "allocated": largest_entry.get("allocated"),
            "allocated_human": largest_entry.get("allocated_human"),
            "logical_payload": largest_entry.get("logical_payload"),
            "logical_payload_human": largest_entry.get("logical_payload_human"),
        }


def _largest_run_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(_row_value(row, "id", 0)),
            "command": str(_row_value(row, "command", 1)),
            "payload": int(_row_value(row, "payload_bytes", 2, 0) or 0),
            "payload_human": format_bytes(_row_value(row, "payload_bytes", 2, 0)),
        }
        for row in rows
    ]


def table_storage_breakdown(
    conn: Any,
    backend: DatabaseBackend,
    table_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    table_counts = dict(table_counts or {})
    if backend == DatabaseBackend.POSTGRES:
        return _postgres_table_storage_breakdown(conn, table_counts)
    return _sqlite_table_storage_breakdown(conn, table_counts)


def _table_counts(conn: Any, backend: DatabaseBackend) -> tuple[list[dict[str, int | str]], dict[str, int]]:
    tables: list[dict[str, int | str]] = []
    names = postgres_table_names(conn) if backend == DatabaseBackend.POSTGRES else _sqlite_visible_table_names(conn)
    for name in names:
        try:
            count = (
                postgres_table_row_count(conn, name)
                if backend == DatabaseBackend.POSTGRES
                else sqlite_table_row_count(conn, name)
            )
        except Exception:
            continue
        tables.append({"name": name, "rows": int(count)})
    return tables, {str(item["name"]): int(item["rows"]) for item in tables}


def _sqlite_visible_table_names(conn: Any) -> list[str]:
    virtual_names = sqlite_fts_virtual_table_names(conn)
    shadow_names = {
        f"{vname}{suffix}"
        for vname in virtual_names
        for suffix in _FTS_SHADOW_SUFFIXES
    }
    return [str(name) for name in sqlite_table_names(conn) if str(name) not in shadow_names]


def _snapshot_cache_key(conn: Any, backend: DatabaseBackend, db_path: str) -> tuple[Any, ...]:
    if backend == DatabaseBackend.POSTGRES:
        try:
            row = conn.execute("SELECT current_database() AS database, current_schema() AS schema").fetchone()
            return (
                backend.value,
                str(_row_value(row, "database", 0) or ""),
                str(_row_value(row, "schema", 1) or ""),
            )
        except Exception:
            return (backend.value, "postgres")
    return (backend.value, str(Path(db_path or "").resolve()) if db_path else "")


def storage_snapshot(
    conn: Any,
    backend: DatabaseBackend,
    *,
    db_path: str = "",
    ttl_seconds: float = _SNAPSHOT_CACHE_TTL_SECONDS,
) -> dict[str, Any]:
    key = _snapshot_cache_key(conn, backend, db_path)
    now = time.monotonic()
    cached = _SNAPSHOT_CACHE.get(key)
    if ttl_seconds > 0 and cached and now - cached[0] <= ttl_seconds:
        return cached[1]

    tables, table_counts = _table_counts(conn, backend)
    storage = table_storage_breakdown(conn, backend, table_counts)
    result: dict[str, Any] = {
        "backend": backend.value,
        "tables": tables,
        "table_counts": table_counts,
        "storage": storage,
        "allocated_by_object": _allocated_by_object(storage),
        "size": int(storage.get("total_allocated_bytes") or 0),
        "size_human": format_bytes(storage.get("total_allocated_bytes") or 0),
        "reclaimable_size": 0,
        "fts_orphans": 0,
    }
    if backend == DatabaseBackend.SQLITE:
        if db_path:
            try:
                result["size"] = int(Path(db_path).stat().st_size)
                result["size_human"] = format_bytes(result["size"])
            except OSError:
                pass
        try:
            page_stats = sqlite_page_stats(conn)
            result["page_stats"] = page_stats
            result["reclaimable_size"] = int(page_stats["page_size"]) * int(page_stats["freelist_count"])
        except Exception:
            pass
        try:
            result["fts_orphans"] = sqlite_fts_orphan_count(conn)
        except Exception:
            pass

    if ttl_seconds > 0:
        _SNAPSHOT_CACHE[key] = (now, result)
    return result


def _allocated_by_object(storage: dict[str, Any]) -> dict[str, int]:
    allocated: dict[str, int] = {}
    for bucket in storage.get("buckets") or []:
        for row in bucket.get("rows") or []:
            name = str(row.get("name") or "")
            if not name:
                continue
            allocated[name] = int(row.get("allocated") or 0)
    return allocated


def clear_storage_snapshot_cache() -> None:
    _SNAPSHOT_CACHE.clear()
