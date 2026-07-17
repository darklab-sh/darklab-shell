# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
SQLite persistence — connection helper, schema initialisation, and retention pruning.
The configured data directory holds the database; otherwise, writable /data or local-dev /tmp is used.

Tables include runs, snapshots, tokens, workflows, automation, Atlas, and Projects.
FTS: runs_fts (FTS5 virtual table over runs.command + runs.output_search_text).
"""

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from time import monotonic

import fcntl

from config import CFG, resolve_data_dir
from core.database_backend import (
    SQLiteOperationalError,
    DatabaseBackend,
    configured_database_backend,
    configured_database_dialect,
    connect_postgres,
    connect_postgres_sqlite_compat,
    connect_sqlite,
    postgres_advisory_lock_id,
    postgres_table_names,
    sqlite_table_exists,
)
from core.helpers import get_log_session_id
from services.runs.output_store import delete_artifact_file, ensure_run_output_dir, load_full_output_entries
from services.runs.structured_summary import replace_run_output_summary
from services.atlas.recalculation import recalculate_atlas_entities, recalculate_atlas_findings
from services.storage.body_store import delete_text_body

log = logging.getLogger("shell")

# APP_DATA_DIR lets test workers and local tooling isolate their own databases.
DATA_DIR = resolve_data_dir()
DB_PATH  = os.path.join(DATA_DIR, "history.db")
DB_INIT_LOCK_PATH = os.path.join(DATA_DIR, "history.db.init.lock")
DB_BACKEND = configured_database_backend(CFG)
DB_DIALECT = configured_database_dialect(CFG)

PROJECT_ENTITY_TYPES = frozenset({
    "atlas_entity",
    "project",
    "run",
    "snapshot",
    "workspace_file",
    "run_file_artifact",
    "finding",
    "target",
    "package",
})

PROJECT_LINK_SOURCES = frozenset({
    "auto_command",
    "auto_input_file",
    "manual",
    "active_project",
    "auto_promote_rule",
    "package_flow",
    "migration",
})


def validate_project_entity_type(entity_type):
    if entity_type not in PROJECT_ENTITY_TYPES:
        raise ValueError(f"Unsupported project entity type: {entity_type!r}")
    return entity_type


def validate_project_link_source(source):
    if source not in PROJECT_LINK_SOURCES:
        raise ValueError(f"Unsupported project link source: {source!r}")
    return source


def db_connect():
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        return connect_postgres_sqlite_compat(CFG)
    # WAL mode lets history/permalink reads proceed while active runs are still
    # being written, which keeps the UI responsive under load.
    return connect_sqlite(DB_PATH, timeout=10)


def _run_schema_migrations(conn, backend: DatabaseBackend) -> list[str]:
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations, run_migrations_with_advisory_lock

    if backend == DatabaseBackend.POSTGRES:
        return run_migrations_with_advisory_lock(conn, MIGRATIONS)
    return run_migrations(conn, MIGRATIONS, backend=backend)


def _json_column_sql(default: str | None = None) -> str:
    return configured_database_dialect(CFG).json_column_definition(default)


@contextmanager
def _db_init_lock():
    """Serialize schema/bootstrap work across Gunicorn workers."""
    waiting_started = monotonic()
    log.debug("DB_INIT_LOCK_WAITING", extra={"backend": DB_BACKEND.value, "lock_path": DB_INIT_LOCK_PATH})
    with open(DB_INIT_LOCK_PATH, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        log.debug(
            "DB_INIT_LOCK_ACQUIRED",
            extra={
                "backend": DB_BACKEND.value,
                "lock_path": DB_INIT_LOCK_PATH,
                "wait_ms": int((monotonic() - waiting_started) * 1000),
            },
        )
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            log.debug("DB_INIT_LOCK_RELEASED", extra={"backend": DB_BACKEND.value, "lock_path": DB_INIT_LOCK_PATH})


def _create_schema(conn):
    """Create baseline SQLite tables through the unified migration baseline."""
    from core.migrations.baseline import create_sqlite_schema  # noqa: PLC0415

    create_sqlite_schema(conn)


def _create_indexes(conn):
    """Create baseline SQLite indexes through the unified migration baseline."""
    from core.migrations.baseline import create_sqlite_indexes  # noqa: PLC0415

    create_sqlite_indexes(conn)


def _extract_search_text_from_preview_json(raw_preview):
    """Extract plain text from a JSON-encoded preview_lines value."""
    try:
        entries = json.loads(raw_preview)
        if not isinstance(entries, list):
            return ""
        texts = []
        for entry in entries:
            if isinstance(entry, dict):
                t = entry.get("text", "")
                if isinstance(t, str):
                    texts.append(t)
            elif isinstance(entry, str):
                texts.append(entry)
        return "\n".join(texts)
    except Exception:  # noqa: BLE001
        return ""


def _populate_output_search_text(conn) -> int:
    """Backfill output_search_text for existing rows.

    Uses the full gzip artifact when available so early lines of long runs are
    indexed, with a fallback to the inline preview when the artifact is absent
    or unreadable.
    """
    rows = conn.execute(
        "SELECT r.rowid, r.output_preview, r.full_output_available, art.rel_path "
        "FROM runs r "
        "LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
        "WHERE r.output_search_text IS NULL AND r.output_preview IS NOT NULL"
    ).fetchall()
    updated_count = 0
    artifact_fallback_count = 0
    failed_count = 0
    for row in rows:
        try:
            if row["full_output_available"] and row["rel_path"]:
                try:
                    entries = load_full_output_entries(row["rel_path"])
                    search_text = "\n".join(
                        str(e.get("text", "")) for e in entries if isinstance(e, dict)
                    )
                except Exception as exc:  # noqa: BLE001
                    artifact_fallback_count += 1
                    log.debug("OUTPUT_SEARCH_TEXT_BACKFILL_ARTIFACT_FALLBACK", extra={
                        "run_rowid": row["rowid"],
                        "rel_path": row["rel_path"],
                        "error_type": type(exc).__name__,
                    })
                    search_text = _extract_search_text_from_preview_json(row["output_preview"])
            else:
                search_text = _extract_search_text_from_preview_json(row["output_preview"])
            result = conn.execute(
                "UPDATE runs SET output_search_text = ? WHERE rowid = ?",
                (search_text, row["rowid"])
            )
            updated_count += int(getattr(result, "rowcount", 0) or 0)
        except Exception:  # noqa: BLE001
            failed_count += 1
            log.warning("OUTPUT_SEARCH_TEXT_BACKFILL_ROW_FAILED", exc_info=True, extra={
                "run_rowid": row["rowid"],
                "has_artifact": bool(row["rel_path"]),
            })
            continue
    if artifact_fallback_count or failed_count:
        log.warning("OUTPUT_SEARCH_TEXT_BACKFILL_DEGRADED", extra={
            "artifact_fallbacks": artifact_fallback_count,
            "failed_rows": failed_count,
        })
    return updated_count


def _rebuild_runs_fts(conn) -> bool:
    """Rebuild SQLite FTS rows after startup changes indexed run text."""
    if DB_BACKEND != DatabaseBackend.SQLITE:
        return False
    if not sqlite_table_exists(conn, "runs_fts"):
        return False
    try:
        conn.execute("INSERT INTO runs_fts(runs_fts) VALUES ('rebuild')")
        log.debug("RUNS_FTS_REBUILD_COMPLETED", extra={"database_backend": DB_BACKEND.value})
        return True
    except SQLiteOperationalError as exc:
        log.warning("RUNS_FTS_REBUILD_FAILED", extra={
            "database_backend": DB_BACKEND.value,
            "error": str(exc),
        })
        raise


def _backfill_watcher_monitoring_fields(conn):
    """Fill derived watcher monitoring fields for rows written before those fields existed."""
    if DB_BACKEND != DatabaseBackend.SQLITE:
        return
    try:
        result = conn.execute(
            """
            UPDATE watcher_fires
            SET state_reason = CASE
                    WHEN json_extract(diff_summary_json, '$.baseline_created') = 1 THEN 'baseline_created'
                    WHEN state_at_fire = 'changed' THEN 'diff_detected'
                    WHEN state_at_fire = 'error' THEN 'run_failed'
                    WHEN state_at_fire = 'paused' THEN 'paused'
                    WHEN state_at_fire = 'ok' THEN 'no_change'
                    ELSE ''
                END,
                fire_kind = CASE
                    WHEN json_extract(diff_summary_json, '$.baseline_created') = 1 THEN 'baseline_created'
                    WHEN state_at_fire = 'changed' THEN 'changed'
                    WHEN state_at_fire = 'error' THEN 'failed'
                    WHEN state_at_fire = 'paused' THEN 'paused'
                    WHEN state_at_fire = 'ok' THEN 'no_change'
                    ELSE 'unclassified'
                END
            WHERE fire_kind = 'unclassified'
            """
        )
        log.debug("WATCHER_MONITORING_FIRE_BACKFILL_COMPLETED", extra={
            "database_backend": DB_BACKEND.value,
            "affected_rows": int(getattr(result, "rowcount", 0) or 0),
        })
    except SQLiteOperationalError as exc:
        log.warning("WATCHER_MONITORING_FIRE_BACKFILL_FAILED", extra={
            "database_backend": DB_BACKEND.value,
            "error": str(exc),
        })
    try:
        result = conn.execute(
            """
            UPDATE watchers
            SET project_id = (
                SELECT MIN(p.id)
                FROM project_links pl
                JOIN projects p ON p.id = pl.project_id
                WHERE pl.entity_type = 'run'
                  AND pl.entity_id = watchers.baseline_run_id
                  AND (
                    (watchers.team_id != '' AND p.team_id = watchers.team_id)
                    OR ((watchers.team_id IS NULL OR watchers.team_id = '')
                        AND (p.team_id IS NULL OR p.team_id = '')
                        AND p.session_id = watchers.session_token)
                  )
            )
            WHERE (project_id IS NULL OR project_id = '')
              AND baseline_run_id != ''
              AND (
                SELECT COUNT(DISTINCT p.id)
                FROM project_links pl
                JOIN projects p ON p.id = pl.project_id
                WHERE pl.entity_type = 'run'
                  AND pl.entity_id = watchers.baseline_run_id
                  AND (
                    (watchers.team_id != '' AND p.team_id = watchers.team_id)
                    OR ((watchers.team_id IS NULL OR watchers.team_id = '')
                        AND (p.team_id IS NULL OR p.team_id = '')
                        AND p.session_id = watchers.session_token)
                  )
              ) = 1
            """
        )
        log.debug("WATCHER_PROJECT_INFERENCE_BACKFILL_COMPLETED", extra={
            "database_backend": DB_BACKEND.value,
            "affected_rows": int(getattr(result, "rowcount", 0) or 0),
        })
    except SQLiteOperationalError as exc:
        log.warning("WATCHER_PROJECT_INFERENCE_BACKFILL_FAILED", extra={
            "database_backend": DB_BACKEND.value,
            "error": str(exc),
        })


def _run_post_schema_maintenance(conn):
    log.info("POST_SCHEMA_MAINTENANCE_STARTED", extra={"backend": DB_BACKEND.value})
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        namespace = "darklab_shell_db_init"
        lock_id = postgres_advisory_lock_id(namespace)
        start = monotonic()
        log.debug("POST_SCHEMA_MAINTENANCE_LOCK_WAITING", extra={
            "backend": DB_BACKEND.value,
            "namespace": namespace,
            "lock_id": lock_id,
        })
        conn.execute(
            "SELECT pg_advisory_xact_lock(?)",
            (lock_id,),
        )
        log.debug("POST_SCHEMA_MAINTENANCE_LOCK_ACQUIRED", extra={
            "backend": DB_BACKEND.value,
            "namespace": namespace,
            "lock_id": lock_id,
            "wait_ms": int((monotonic() - start) * 1000),
        })
    completed_steps: list[str] = []

    def run_step(step_name, func):
        log.debug("POST_SCHEMA_MAINTENANCE_STEP_STARTED", extra={
            "backend": DB_BACKEND.value,
            "step": step_name,
        })
        try:
            func()
        except Exception:
            log.error("POST_SCHEMA_MAINTENANCE_STEP_FAILED", exc_info=True, extra={
                "backend": DB_BACKEND.value,
                "step": step_name,
            })
            raise
        completed_steps.append(step_name)

    if DB_BACKEND == DatabaseBackend.SQLITE:
        def sqlite_output_search_backfill():
            if _populate_output_search_text(conn):
                _rebuild_runs_fts(conn)

        run_step("sqlite_output_search_text_backfill", sqlite_output_search_backfill)
        run_step("sqlite_watcher_monitoring_backfill", lambda: _backfill_watcher_monitoring_fields(conn))
    run_step("run_output_summary_backfill", lambda: _populate_run_output_summary(conn))
    run_step("retention_prune", lambda: _prune_retention(conn))
    from services.audit.retention import prune_events, warn_if_disabled  # noqa: PLC0415

    def audit_retention():
        warn_if_disabled()
        prune_events(conn=conn)

    run_step("audit_retention_prune", audit_retention)
    run_step("project_target_audit", lambda: _audit_project_target_host_type_collapse(conn))
    run_step("url_host_entity_link_backfill", lambda: _backfill_url_host_entity_links(conn))
    log.info("POST_SCHEMA_MAINTENANCE_COMPLETED", extra={
        "backend": DB_BACKEND.value,
        "steps": ",".join(completed_steps),
    })


def _populate_run_output_summary(conn):
    """Backfill structured run-output summary rows for existing runs."""
    if not hasattr(conn, "execute"):
        return
    if DB_BACKEND == DatabaseBackend.SQLITE and not sqlite_table_exists(conn, "run_output_summary"):
        return
    if DB_BACKEND == DatabaseBackend.SQLITE and not sqlite_table_exists(conn, "run_output_summary_status"):
        return
    try:
        rows = conn.execute(
            "SELECT r.id, r.output_preview, art.rel_path "
            "FROM runs r "
            "LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM run_output_summary s WHERE s.run_id = r.id) "
            "AND NOT EXISTS ("
            "SELECT 1 FROM run_output_summary_status st "
            "WHERE st.run_id = r.id AND st.status IN ('complete', 'empty', 'failed'))"
        ).fetchall()
    except SQLiteOperationalError:
        log.warning("RUN_OUTPUT_SUMMARY_BACKFILL_QUERY_FAILED", exc_info=True, extra={
            "backend": DB_BACKEND.value,
        })
        return
    populated = 0
    failed = 0
    artifact_unreadable_count = 0
    preview_unreadable_count = 0
    for row in rows:
        run_id = str(row["id"] or "")
        entries = None
        source = ""
        error = ""
        rel_path = str(row["rel_path"] or "").strip()
        if rel_path:
            try:
                entries = load_full_output_entries(rel_path)
                source = "artifact"
            except Exception:  # noqa: BLE001
                artifact_unreadable_count += 1
                source = "artifact"
                error = "artifact_unreadable"
        if entries is None:
            try:
                parsed = json.loads(str(row["output_preview"] or "[]"))
                entries = parsed if isinstance(parsed, list) else []
                source = "preview"
            except (TypeError, ValueError, json.JSONDecodeError):
                failed += 1
                preview_unreadable_count += 1
                _record_run_output_summary_status(
                    conn,
                    run_id,
                    status="failed",
                    source=source or "preview",
                    error=error or "preview_unreadable",
                )
                entries = []
                continue
        replace_run_output_summary(conn, run_id, entries)
        _record_run_output_summary_status(
            conn,
            run_id,
            status="complete" if entries else "empty",
            source=source,
            error=error,
        )
        populated += 1
    if populated or failed:
        log.info("RUN_OUTPUT_SUMMARY_BACKFILLED", extra={"runs": populated, "failed": failed})
    if artifact_unreadable_count or preview_unreadable_count or failed:
        log.warning("RUN_OUTPUT_SUMMARY_BACKFILL_DEGRADED", extra={
            "backend": DB_BACKEND.value,
            "artifact_unreadable": artifact_unreadable_count,
            "preview_unreadable": preview_unreadable_count,
            "failed": failed,
        })


def _record_run_output_summary_status(conn, run_id: str, *, status: str, source: str, error: str = "") -> None:
    if not run_id:
        return
    attempted_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO run_output_summary_status "
        "(run_id, status, source, attempted_at, attempts, error) "
        "VALUES (?, ?, ?, ?, 1, ?) "
        "ON CONFLICT(run_id) DO UPDATE SET "
        "status = excluded.status, "
        "source = excluded.source, "
        "attempted_at = excluded.attempted_at, "
        "attempts = CASE "
        "WHEN run_output_summary_status.attempts >= 2147483647 "
        "THEN run_output_summary_status.attempts "
        "ELSE run_output_summary_status.attempts + 1 END, "
        "error = excluded.error",
        (run_id, status, source, attempted_at, _bounded_backfill_error(error)),
    )


def _bounded_backfill_error(error: str) -> str:
    text = str(error or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:160]


def _create_fts_schema(conn):
    """Create baseline SQLite FTS schema through the unified migration baseline."""
    from core.migrations.baseline import create_sqlite_fts_schema  # noqa: PLC0415

    create_sqlite_fts_schema(conn)


def delete_run_artifacts(conn, run_ids):
    # The database row is the source of truth; once it is gone, best-effort file
    # cleanup can run without leaving dangling metadata behind.
    ids = [run_id for run_id in run_ids if run_id]
    if not ids:
        return

    try:
        from services.watchers.service import pause_watchers_for_deleted_baselines  # noqa: PLC0415

        pause_watchers_for_deleted_baselines(conn, ids)
    except Exception:
        log.error("WATCHER_BASELINE_DELETE_HOOK_ERROR", exc_info=True)

    placeholders = ",".join("?" for _ in ids)
    conn.execute(f"UPDATE workflow_execution_steps SET run_id = '' WHERE run_id IN ({placeholders})", ids)  # nosec
    rows = conn.execute(
        f"SELECT rel_path FROM run_output_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    search_text_rows = conn.execute(
        f"SELECT output_search_text FROM runs WHERE id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    file_artifact_rows = conn.execute(
        f"SELECT id FROM run_file_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    file_artifact_ids = [row["id"] for row in file_artifact_rows if row["id"]]
    entity_rows = conn.execute(
        f"SELECT DISTINCT entity_id FROM entity_run_links WHERE run_id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    entity_ids = [row["entity_id"] for row in entity_rows if row["entity_id"]]
    finding_rows = conn.execute(
        f"SELECT DISTINCT finding_id FROM findings_occurrences WHERE run_id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    finding_ids = [row["finding_id"] for row in finding_rows if row["finding_id"]]
    conn.execute(
        "DELETE FROM project_links WHERE entity_type = 'run' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    conn.execute(
        "DELETE FROM entity_labels WHERE entity_type = 'run' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    conn.execute(
        "DELETE FROM entity_notes WHERE entity_type = 'run' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    if file_artifact_ids:
        artifact_placeholders = ",".join("?" for _ in file_artifact_ids)
        conn.execute(
            "DELETE FROM project_links WHERE entity_type = 'run_file_artifact' "  # nosec
            f"AND entity_id IN ({artifact_placeholders})",
            file_artifact_ids,
        )
        conn.execute(
            "DELETE FROM entity_labels WHERE entity_type = 'run_file_artifact' "  # nosec
            f"AND entity_id IN ({artifact_placeholders})",
            file_artifact_ids,
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE entity_type = 'run_file_artifact' "  # nosec
            f"AND entity_id IN ({artifact_placeholders})",
            file_artifact_ids,
        )
    conn.execute(
        f"DELETE FROM findings_occurrences WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    recalculate_atlas_findings(conn, finding_ids)
    conn.execute(
        f"DELETE FROM entity_run_links WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    conn.execute(
        f"DELETE FROM scan_target_observations WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    recalculate_atlas_entities(conn, entity_ids)
    conn.execute(
        f"DELETE FROM run_file_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    conn.execute(
        f"DELETE FROM run_output_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    try:
        conn.execute(
            f"DELETE FROM run_output_summary WHERE run_id IN ({placeholders})",  # nosec
            ids,
        )
    except SQLiteOperationalError:
        pass
    try:
        conn.execute(
            f"DELETE FROM run_output_summary_status WHERE run_id IN ({placeholders})",  # nosec
            ids,
        )
    except SQLiteOperationalError:
        pass
    try:
        assist_rows = conn.execute(
            f"SELECT id FROM ai_run_assists WHERE run_id IN ({placeholders})",  # nosec
            ids,
        ).fetchall()
        assist_ids = [row["id"] for row in assist_rows if row["id"]]
        if assist_ids:
            assist_placeholders = ",".join("?" for _ in assist_ids)
            conn.execute(
                f"DELETE FROM ai_suggestion_validations WHERE assist_id IN ({assist_placeholders})",  # nosec
                assist_ids,
            )
        conn.execute(
            f"DELETE FROM ai_run_assists WHERE run_id IN ({placeholders})",  # nosec
            ids,
        )
    except SQLiteOperationalError:
        pass
    for row in rows:
        delete_artifact_file(row["rel_path"])
    for row in search_text_rows:
        delete_text_body(row["output_search_text"])


def delete_snapshot_metadata(conn, snapshot_ids):
    ids = [snapshot_id for snapshot_id in snapshot_ids if snapshot_id]
    if not ids:
        return

    placeholders = ",".join("?" for _ in ids)
    snapshot_rows = conn.execute(
        f"SELECT content FROM snapshots WHERE id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    conn.execute(
        "DELETE FROM project_links WHERE entity_type = 'snapshot' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    conn.execute(
        "DELETE FROM entity_labels WHERE entity_type = 'snapshot' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    for row in snapshot_rows:
        delete_text_body(row["content"])
    conn.execute(
        "DELETE FROM entity_notes WHERE entity_type = 'snapshot' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )


def _prune_retention(conn, *, cfg=None) -> dict[str, int]:
    """Delete runs and snapshots older than permalink_retention_days."""
    counts = {"runs": 0, "snapshots": 0}
    active_cfg = CFG if cfg is None else cfg
    days = active_cfg.get("permalink_retention_days", 0)
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
        if DB_BACKEND == DatabaseBackend.POSTGRES:
            run_older_sql = "r.started::timestamptz < ?::timestamptz"
            started_older_sql = "started::timestamptz < ?::timestamptz"
            created_older_sql = "created::timestamptz < ?::timestamptz"
        else:
            run_older_sql = "datetime(r.started) < ?"
            started_older_sql = "datetime(started) < ?"
            created_older_sql = "datetime(created) < ?"
        linked_run_row = conn.execute(
            "SELECT COUNT(DISTINCT r.id) AS linked_runs, COUNT(DISTINCT l.project_id) AS linked_projects "
            "FROM runs r JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = r.id "
            f"WHERE {run_older_sql}",  # nosec
            (cutoff,),
        ).fetchone()
        linked_run_count = int(linked_run_row["linked_runs"] or 0) if linked_run_row else 0
        linked_project_count = int(linked_run_row["linked_projects"] or 0) if linked_run_row else 0
        if linked_run_count:
            log.warning("PROJECT_RETENTION_WARNING", extra={
                "linked_runs": linked_run_count,
                "projects": linked_project_count,
                "retention_days": days,
            })
        old_run_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM runs WHERE {started_older_sql}",  # nosec
                (cutoff,)
            ).fetchall()
        ]
        old_snapshot_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM snapshots WHERE {created_older_sql}",  # nosec
                (cutoff,)
            ).fetchall()
        ]
        delete_run_artifacts(conn, old_run_ids)
        delete_snapshot_metadata(conn, old_snapshot_ids)
        cur_runs  = conn.execute(
            f"DELETE FROM runs WHERE {started_older_sql}",  # nosec
            (cutoff,)
        )
        cur_snaps = conn.execute(
            f"DELETE FROM snapshots WHERE {created_older_sql}",  # nosec
            (cutoff,)
        )
        counts = {
            "runs": int(cur_runs.rowcount or 0),
            "snapshots": int(cur_snaps.rowcount or 0),
        }
        if cur_runs.rowcount or cur_snaps.rowcount:
            log.info("DB_PRUNED", extra={
                "runs": cur_runs.rowcount,
                "snapshots": cur_snaps.rowcount,
                "retention_days": days,
            })
    return counts


def prune_retention(conn, *, cfg=None) -> dict[str, int]:
    """Delete expired run and snapshot data using the normal retention policy."""
    return _prune_retention(conn, cfg=cfg)


def _table_exists_for_backend(conn, table_name: str) -> bool:
    if DB_BACKEND == DatabaseBackend.SQLITE:
        return sqlite_table_exists(conn, table_name)
    row = conn.execute("SELECT to_regclass(?) AS table_name", (table_name,)).fetchone()
    if not row:
        return False
    try:
        value = row["table_name"]
    except (TypeError, KeyError, IndexError):
        value = row[0]
    return bool(value)


def _audit_project_target_host_type_collapse(conn) -> None:
    try:
        host_entity_count = 0
        if _table_exists_for_backend(conn, "entities"):
            row = conn.execute("SELECT COUNT(*) AS count FROM entities WHERE type = ?", ("host",)).fetchone()
            host_entity_count = int(row["count"] or 0) if row else 0
        legacy_target_table_count = sum(
            1
            for table_name in ("project_targets", "finding_targets")
            if _table_exists_for_backend(conn, table_name)
        )
        log.info("PROJECT_TARGET_HOST_TYPE_AUDIT", extra={
            "host_entity_rows": host_entity_count,
            "legacy_target_tables_present": legacy_target_table_count > 0,
            "legacy_target_table_count": legacy_target_table_count,
            "migration_required": bool(host_entity_count or legacy_target_table_count),
        })
    except Exception:
        log.debug("PROJECT_TARGET_HOST_TYPE_AUDIT_FAILED", exc_info=True)


def _backfill_url_host_entity_links(conn) -> None:
    try:
        from services.atlas.materializer import upsert_entity, url_host_identity  # noqa: PLC0415
    except Exception:
        log.warning("ATLAS_URL_HOST_BACKFILL_FAILED", exc_info=True, extra={
            "stage": "import",
            "backend": DB_BACKEND.value,
        })
        return
    try:
        rows = conn.execute(
            "SELECT id, session_id, team_id, canonical_value, first_seen_at, last_seen_at "
            "FROM entities "
            "WHERE type = 'url' AND COALESCE(host_entity_id, '') = ''"
        ).fetchall()
    except Exception:
        log.warning("ATLAS_URL_HOST_BACKFILL_FAILED", exc_info=True, extra={
            "stage": "query",
            "backend": DB_BACKEND.value,
        })
        return
    updated_count = 0
    invalid_url_count = 0
    host_upsert_miss_count = 0
    update_miss_count = 0
    for row in rows:
        identity = url_host_identity(str(row["canonical_value"] or ""))
        if identity is None:
            invalid_url_count += 1
            continue
        host_type, host_canonical = identity
        seen_at = str(row["first_seen_at"] or row["last_seen_at"] or "")
        session_id = str(row["session_id"] or "")
        team_id = str(row["team_id"] or "")
        try:
            host_entity_id = upsert_entity(
                conn,
                session_id,
                host_type,
                host_canonical,
                team_id=team_id,
                seen_at=seen_at,
                occurrence_count=0,
            )
        except Exception:
            log.error("ATLAS_URL_HOST_BACKFILL_ROW_FAILED", exc_info=True, extra={
                "stage": "upsert_host",
                "backend": DB_BACKEND.value,
                "url_entity_id": str(row["id"] or ""),
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "host_entity_type": host_type,
            })
            raise
        if not host_entity_id:
            host_upsert_miss_count += 1
            continue
        try:
            result = conn.execute(
                "UPDATE entities SET host_entity_id = ? "
                "WHERE id = ? AND type = 'url' AND COALESCE(host_entity_id, '') = ''",
                (host_entity_id, row["id"]),
            )
        except Exception:
            log.error("ATLAS_URL_HOST_BACKFILL_ROW_FAILED", exc_info=True, extra={
                "stage": "update_url_link",
                "backend": DB_BACKEND.value,
                "url_entity_id": str(row["id"] or ""),
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "host_entity_type": host_type,
            })
            raise
        updated_rows = max(0, int(result.rowcount or 0))
        if updated_rows:
            updated_count += updated_rows
        else:
            update_miss_count += 1
    skipped_count = invalid_url_count + host_upsert_miss_count + update_miss_count
    if updated_count:
        log.info("ATLAS_URL_HOST_BACKFILL_COMPLETED", extra={
            "backend": DB_BACKEND.value,
            "url_entity_count": len(rows),
            "updated_count": updated_count,
            "skipped_count": skipped_count,
        })
    if skipped_count:
        log.warning("ATLAS_URL_HOST_BACKFILL_SKIPPED_ROWS", extra={
            "backend": DB_BACKEND.value,
            "url_entity_count": len(rows),
            "invalid_url_count": invalid_url_count,
            "host_upsert_miss_count": host_upsert_miss_count,
            "update_miss_count": update_miss_count,
        })


def _schema_startup_action(
    backend: DatabaseBackend,
    versions: list[str],
    branch: str,
    migrations,
) -> str:
    if not versions:
        return "noop"
    baseline = next((migration for migration in migrations if migration.baseline_apply is not None), None)
    baseline_version = baseline.version if baseline is not None else ""
    if baseline_version and "fresh" in branch and baseline_version in versions:
        stamped_versions = [version for version in versions if version < baseline_version]
        future_versions = [version for version in versions if version > baseline_version]
        log.info("SCHEMA_BASELINE_CREATED", extra={
            "backend": backend.value,
            "baseline_version": baseline_version,
            "legacy_versions_stamped": len(stamped_versions),
            "executed_versions": ",".join([baseline_version, *future_versions]),
        })
        if stamped_versions:
            log.info("SCHEMA_MIGRATIONS_STAMPED", extra={
                "backend": backend.value,
                "versions": ",".join(stamped_versions),
                "reason": "fresh_unified_baseline",
            })
        if future_versions:
            log.info("SCHEMA_MIGRATIONS_APPLIED", extra={
                "backend": backend.value,
                "versions": ",".join(future_versions),
            })
        return "baseline_created"
    if branch == "sqlite_preledger_current_head":
        log.info("SCHEMA_MIGRATIONS_STAMPED", extra={
            "backend": backend.value,
            "versions": ",".join(versions),
            "reason": "preledger_current_head",
        })
        return "preledger_stamped"
    log.info("SCHEMA_MIGRATIONS_APPLIED", extra={
        "backend": backend.value,
        "versions": ",".join(versions),
    })
    return "migrations_applied"


def _postgres_schema_init_branch(conn, migrations) -> str:
    from core.migrations.runner import applied_versions  # noqa: PLC0415

    if "schema_migrations" not in postgres_table_names(conn):
        return "postgres_fresh_unified_baseline"
    applied = applied_versions(conn)
    baseline = next((migration for migration in migrations if migration.baseline_apply is not None), None)
    baseline_version = baseline.version if baseline is not None else ""
    legacy_versions = {migration.version for migration in migrations if baseline_version and migration.version < baseline_version}
    if not applied:
        return "postgres_fresh_unified_baseline"
    if baseline_version and baseline_version not in applied and legacy_versions and legacy_versions.issubset(applied):
        return "postgres_legacy_through_0038"
    return "postgres_ledgered"


def db_init():
    """Create the runs and snapshots tables if they don't exist, and prune old records."""
    phase = "ensure_output_dir"
    schema_action = "noop"
    try:
        ensure_run_output_dir()
        log.info("DB_BACKEND_SELECTED", extra={"backend": DB_BACKEND.value})
        log.info("DB_INIT_STARTED", extra={"backend": DB_BACKEND.value})
        if DB_BACKEND == DatabaseBackend.POSTGRES:
            from core.migrations import MIGRATIONS  # noqa: PLC0415

            versions_changed = 0
            phase = "connect"
            with connect_postgres(CFG) as conn:
                phase = "schema_branch"
                branch = _postgres_schema_init_branch(conn, MIGRATIONS)
                log.debug("POSTGRES_SCHEMA_INIT_BRANCH_SELECTED", extra={
                    "branch": branch,
                    "backend": DB_BACKEND.value,
                })
                phase = "migrations"
                applied = _run_schema_migrations(conn, DB_BACKEND)
                versions_changed = len(applied)
                schema_action = _schema_startup_action(DB_BACKEND, applied, branch, MIGRATIONS)
                phase = "commit"
                conn.commit()
            phase = "maintenance"
            with db_connect() as conn:
                _run_post_schema_maintenance(conn)
                phase = "commit"
                conn.commit()
            log.info("DB_INIT_COMPLETED", extra={
                "backend": DB_BACKEND.value,
                "schema_versions_changed": versions_changed,
                "schema_action": schema_action,
                "maintenance_completed": True,
            })
            return
        phase = "lock"
        with _db_init_lock():
            _db_init_sqlite_locked(schema_action)
    except Exception:
        log.error(
            "DB_INIT_FAILED",
            exc_info=True,
            extra={"backend": DB_BACKEND.value, "phase": phase, "schema_action": schema_action},
        )
        raise


def _db_init_sqlite_locked(schema_action: str = "noop") -> None:
    versions_changed = 0
    with db_connect() as conn:
        from core.migrations.reconciliation import (  # noqa: PLC0415
            sqlite_has_app_schema,
            sqlite_has_migration_ledger,
            stamp_verified_sqlite_head,
        )
        from core.migrations import MIGRATIONS  # noqa: PLC0415

        had_migration_ledger = sqlite_has_migration_ledger(conn)
        had_app_schema = sqlite_has_app_schema(conn)
        if not had_migration_ledger and not had_app_schema:
            branch = "sqlite_fresh_unified_baseline"
            log.debug("SQLITE_SCHEMA_INIT_BRANCH_SELECTED", extra={
                "had_migration_ledger": had_migration_ledger,
                "had_app_schema": had_app_schema,
                "branch": branch,
            })
            applied = _run_schema_migrations(conn, DB_BACKEND)
            versions_changed = len(applied)
            schema_action = _schema_startup_action(DB_BACKEND, applied, branch, MIGRATIONS)
        elif not had_migration_ledger:
            branch = "sqlite_preledger_current_head"
            log.debug("SQLITE_SCHEMA_INIT_BRANCH_SELECTED", extra={
                "had_migration_ledger": had_migration_ledger,
                "had_app_schema": had_app_schema,
                "branch": branch,
            })
            stamped = stamp_verified_sqlite_head(conn, MIGRATIONS)
            versions_changed = len(stamped)
            schema_action = _schema_startup_action(DB_BACKEND, stamped, branch, MIGRATIONS)
        else:
            branch = "sqlite_ledgered"
            log.debug("SQLITE_SCHEMA_INIT_BRANCH_SELECTED", extra={
                "had_migration_ledger": had_migration_ledger,
                "had_app_schema": had_app_schema,
                "branch": branch,
            })
            applied = _run_schema_migrations(conn, DB_BACKEND)
            versions_changed = len(applied)
            schema_action = _schema_startup_action(DB_BACKEND, applied, branch, MIGRATIONS)
        _run_post_schema_maintenance(conn)
        conn.commit()
    log.info("DB_INIT_COMPLETED", extra={
        "backend": DB_BACKEND.value,
        "schema_versions_changed": versions_changed,
        "schema_action": schema_action,
        "maintenance_completed": True,
    })
