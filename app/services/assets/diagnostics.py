"""Database-backed helpers for asset and diagnostics routes."""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.database_backend import DatabaseBackend, sqlite_journal_mode, sqlite_page_stats
from core.helpers import GRACEFUL_TERMINATION_EXIT_CODE
from services.audit.retention import maybe_prune_events
from services.diagnostics.classifier_drift import classifier_drift_report
from services.diagnostics.storage import (
    PROJECT_WORKSPACE_COUNT_TABLES,
    format_bytes,
    storage_snapshot,
    table_storage_breakdown,
)

log = logging.getLogger("shell")


def _database_context():
    from core.database import db_connect

    return db_connect()


def _database_backend() -> DatabaseBackend:
    from core.database import DB_BACKEND

    return DB_BACKEND


def _database_path() -> Path:
    from core.database import DB_PATH

    return Path(DB_PATH)


def fmt_elapsed(seconds: Any) -> str:
    s = int(seconds or 0)
    if s >= 3600:
        h, m = s // 3600, (s % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"
    if s >= 60:
        m, r = s // 60, s % 60
        return f"{m}m {r}s" if r else f"{m}m"
    return f"{s}s"


def fmt_diag_duration_ms(value: Any) -> str:
    ms = float(value or 0)
    if ms >= 1000:
        seconds = ms / 1000
        if seconds >= 10:
            return f"{seconds:.0f}s"
        return f"{seconds:.1f}s"
    if ms >= 100:
        return f"{ms:.0f} ms"
    return f"{ms:g} ms"


def row_value(row: Any, key: str, index: int, default: Any = None) -> Any:
    if hasattr(row, "keys"):
        try:
            return row[key]
        except KeyError:
            pass
    try:
        return row[index]
    except (IndexError, KeyError, TypeError):
        return default


def ping_database() -> None:
    with _database_context() as conn:
        conn.execute("SELECT 1")


def status_database_state() -> str:
    try:
        with _database_context() as conn:
            conn.execute("SELECT 1")
            try:
                maybe_prune_events(conn=conn)
                conn.commit()
            except Exception:
                rollback = getattr(conn, "rollback", None)
                if callable(rollback):
                    rollback()

                log.warning("AUDIT_RETENTION_PERIODIC_PRUNE_FAILED", exc_info=True)
            return "ok"
    except Exception:
        log.warning("STATUS_DATABASE_DOWN", exc_info=True, extra={"backend": _database_backend().value})
        return "down"


def diag_table_storage_breakdown(conn: Any, table_counts: dict[str, int] | None = None) -> dict:
    return _with_largest_runs_empty_state(table_storage_breakdown(conn, _database_backend(), table_counts))


def _with_largest_runs_empty_state(storage: dict[str, Any]) -> dict[str, Any]:
    if not storage.get("largest_runs") and not storage.get("largest_runs_skipped"):
        storage["largest_runs_skipped"] = "no saved runs"
    return storage


def diag_database_stats() -> dict:
    """Snapshot database health without letting optional probes blank the panel."""
    backend = _database_backend()
    db_path = _database_path()
    info: dict[str, Any] = {"backend": backend.value}

    if backend == DatabaseBackend.POSTGRES:
        with _database_context() as conn:
            t0 = time.perf_counter()
            conn.execute("SELECT 1").fetchone()
            info["ping_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            info["ping_human"] = fmt_diag_duration_ms(info["ping_ms"])
            try:
                snapshot = storage_snapshot(conn, backend, db_path=str(db_path))
                table_counts = snapshot["table_counts"]
                info["tables"] = snapshot["tables"]
                info["runs"] = table_counts.get("runs", 0)
                info["snapshots"] = table_counts.get("snapshots", 0)
                info["project_workspace"] = {
                    label: table_counts.get(table_name, 0)
                    for table_name, label in PROJECT_WORKSPACE_COUNT_TABLES.items()
                }
                info["storage"] = _with_largest_runs_empty_state(snapshot["storage"])
                info["dbstat_available"] = bool(info["storage"].get("dbstat_available"))
                info["storage_stats_available"] = bool(info["storage"].get("storage_stats_available"))
                info["size"] = int(snapshot.get("size") or 0)
                info["size_human"] = snapshot.get("size_human") or format_bytes(info["size"])
            except Exception:
                log.warning(
                    "DIAG_DATABASE_STATS_PARTIAL",
                    exc_info=True,
                    extra={"backend": backend.value, "probe": "storage_snapshot"},
                )
        return info

    try:
        st = db_path.stat()
        info["size"] = int(st.st_size)
        info["size_human"] = format_bytes(info["size"])
        info["mtime"] = int(st.st_mtime)
        info["mtime_age_human"] = f"{fmt_elapsed(int(time.time()) - info['mtime'])} ago"
    except OSError:
        pass

    wal_path = db_path.with_name(db_path.name + "-wal")
    try:
        wal_size = int(wal_path.stat().st_size)
    except OSError:
        wal_size = 0
    info["wal_size"] = wal_size
    info["wal_size_human"] = format_bytes(wal_size)

    with _database_context() as conn:
        try:
            t0 = time.perf_counter()
            conn.execute("SELECT 1").fetchone()
            info["ping_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            info["ping_human"] = fmt_diag_duration_ms(info["ping_ms"])
        except Exception:
            log.debug(
                "DIAG_DATABASE_OPTIONAL_PROBE_FAILED",
                exc_info=True,
                extra={"backend": backend.value, "probe": "ping"},
            )
        try:
            info["journal_mode"] = sqlite_journal_mode(conn)
        except Exception:
            log.debug(
                "DIAG_DATABASE_OPTIONAL_PROBE_FAILED",
                exc_info=True,
                extra={"backend": backend.value, "probe": "journal_mode"},
            )
        try:
            page_stats = sqlite_page_stats(conn)
            page_count = page_stats["page_count"]
            page_size = page_stats["page_size"]
            freelist = page_stats["freelist_count"]
            info["page_count"] = page_count
            info["page_size"] = page_size
            info["freelist_count"] = freelist
            info["reclaimable_size"] = freelist * page_size
            info["reclaimable_size_human"] = format_bytes(freelist * page_size)
        except Exception:
            log.debug(
                "DIAG_DATABASE_OPTIONAL_PROBE_FAILED",
                exc_info=True,
                extra={"backend": backend.value, "probe": "page_stats"},
            )

        snapshot: dict[str, Any] = {}
        try:
            snapshot = storage_snapshot(conn, backend, db_path=str(db_path))
            info["tables"] = snapshot["tables"]
            table_counts = snapshot["table_counts"]
            for table in snapshot["tables"]:
                if table["name"] == "runs":
                    info["runs"] = table["rows"]
                elif table["name"] == "snapshots":
                    info["snapshots"] = table["rows"]
            info["project_workspace"] = {
                label: table_counts.get(table_name, 0)
                for table_name, label in PROJECT_WORKSPACE_COUNT_TABLES.items()
            }
            info["storage"] = _with_largest_runs_empty_state(snapshot["storage"])
            info["dbstat_available"] = bool(info["storage"].get("dbstat_available"))
            info["storage_stats_available"] = bool(info["storage"].get("storage_stats_available"))
        except Exception:
            log.warning(
                "DIAG_DATABASE_STATS_PARTIAL",
                exc_info=True,
                extra={"backend": backend.value, "probe": "storage_snapshot"},
            )

        try:
            info["fts_orphans"] = int(snapshot.get("fts_orphans") or 0)
        except Exception:
            log.debug(
                "DIAG_DATABASE_OPTIONAL_PROBE_FAILED",
                exc_info=True,
                extra={"backend": backend.value, "probe": "fts_orphans"},
            )

    return info


def diag_usage_stats(tz_offset_raw: Any) -> dict:
    stats: dict[str, Any] = {"ok": False}
    try:
        with _database_context() as conn:
            try:
                tz_offset_min = int(tz_offset_raw or 0)
            except (TypeError, ValueError):
                tz_offset_min = 0
            local_tz = timezone(timedelta(minutes=-tz_offset_min))
            now_local = datetime.now(timezone.utc).astimezone(local_tz)
            fmt = "%Y-%m-%d %H:%M:%S"
            cutoffs = [
                (
                    "today",
                    now_local.replace(
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0
                    ).astimezone(timezone.utc).strftime(fmt)
                ),
                ("this week", (datetime.now(timezone.utc) - timedelta(days=7)).strftime(fmt)),
                (
                    "this month",
                    now_local.replace(
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0
                    ).astimezone(timezone.utc).strftime(fmt)
                ),
                (
                    "this year",
                    now_local.replace(
                        month=1,
                        day=1,
                        hour=0,
                        minute=0,
                        second=0,
                        microsecond=0).astimezone(timezone.utc).strftime(fmt)
                ),
            ]
            activity = []
            for label, cutoff in cutoffs:
                row = conn.execute("SELECT COUNT(*) AS count FROM runs WHERE started >= ?", (cutoff,)).fetchone()
                activity.append({"label": label, "count": row_value(row, "count", 0, 0)})
            stats["activity"] = activity

            row = conn.execute(
                """SELECT
                     SUM(CASE WHEN exit_code = 0                             THEN 1 ELSE 0 END) AS success,
                     SUM(
                         CASE
                             WHEN exit_code IS NOT NULL AND exit_code != 0 AND exit_code != ?
                             THEN 1
                             ELSE 0
                         END
                     ) AS failed,
                     SUM(CASE WHEN exit_code IS NULL                         THEN 1 ELSE 0 END) AS incomplete
                   FROM runs""",
                (GRACEFUL_TERMINATION_EXIT_CODE,),
            ).fetchone()
            stats["outcomes"] = {
                "success": row_value(row, "success", 0, 0) or 0,
                "failed": row_value(row, "failed", 1, 0) or 0,
                "incomplete": row_value(row, "incomplete", 2, 0) or 0,
            }

            rows = conn.execute(
                "SELECT command, COUNT(*) AS n FROM runs GROUP BY command ORDER BY n DESC LIMIT 10"
            ).fetchall()
            stats["top_by_freq"] = [
                {"command": row_value(row, "command", 0, ""), "count": row_value(row, "n", 1, 0)}
                for row in rows
            ]

            if _database_backend() == DatabaseBackend.POSTGRES:
                duration_sql = """SELECT command,
                                         ROUND(EXTRACT(EPOCH FROM (
                                             finished::timestamptz - started::timestamptz
                                         ))) AS elapsed_s
                                    FROM runs
                                   WHERE finished IS NOT NULL AND started IS NOT NULL
                                   ORDER BY elapsed_s DESC
                                   LIMIT 5"""
            else:
                duration_sql = """SELECT command,
                                         ROUND((julianday(finished) - julianday(started)) * 86400) AS elapsed_s
                                    FROM runs
                                   WHERE finished IS NOT NULL AND started IS NOT NULL
                                   ORDER BY elapsed_s DESC
                                   LIMIT 5"""
            rows = conn.execute(duration_sql).fetchall()
            stats["top_by_duration"] = [
                {"command": row_value(row, "command", 0, ""), "elapsed": fmt_elapsed(row_value(row, "elapsed_s", 1, 0))}
                for row in rows
            ]

        stats["ok"] = True
    except Exception as exc:
        log.warning("DIAG_USAGE_STATS_FAILED", exc_info=True, extra={"backend": _database_backend().value})
        stats["error"] = str(exc)
    return stats


def classifier_drift_report_from_db(
    *,
    run_limit: Any = None,
    line_limit: Any = None,
    command_root_filter: Any = None,
    include_full: Any = None,
) -> dict:
    with _database_context() as conn:
        return classifier_drift_report(
            conn,
            run_limit=run_limit,
            line_limit=line_limit,
            command_root_filter=command_root_filter,
            include_full=include_full,
        )
