# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""History retention policy and assessment-safe source cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable

from core.database_backend import DatabaseBackend
from services.assessments.cleanup import mark_run_evidence_unavailable_on_conn

log = logging.getLogger("shell")


def prune_retention_on_conn(
    conn: Any,
    *,
    cfg: dict[str, Any],
    backend: DatabaseBackend,
    delete_run_artifacts_fn: Callable[[Any, list[str]], None],
    delete_snapshot_metadata_fn: Callable[[Any, list[str]], None],
) -> dict[str, int]:
    """Delete expired History sources while retaining assessment tombstones."""
    counts = {"runs": 0, "snapshots": 0}
    days = cfg.get("permalink_retention_days", 0)
    if not days or days <= 0:
        return counts

    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
    if backend == DatabaseBackend.POSTGRES:
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
            (cutoff,),
        ).fetchall()
    ]
    old_snapshot_ids = [
        row["id"]
        for row in conn.execute(
            f"SELECT id FROM snapshots WHERE {created_older_sql}",  # nosec
            (cutoff,),
        ).fetchall()
    ]
    unavailable_evidence_count = mark_run_evidence_unavailable_on_conn(conn, old_run_ids)
    delete_run_artifacts_fn(conn, old_run_ids)
    delete_snapshot_metadata_fn(conn, old_snapshot_ids)
    cur_runs = conn.execute(
        f"DELETE FROM runs WHERE {started_older_sql}",  # nosec
        (cutoff,),
    )
    cur_snaps = conn.execute(
        f"DELETE FROM snapshots WHERE {created_older_sql}",  # nosec
        (cutoff,),
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
            "assessment_evidence_unavailable_count": unavailable_evidence_count,
        })
    return counts
