# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded cleanup for terminal assessment-batch coordinator state."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from core.database_access import db_connection_scope
from services.assessments.batch.settings import assessment_batch_settings
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND

log = logging.getLogger("shell")

_PRUNE_LIMIT = 500


def _cutoff(now: datetime, retention_days: int) -> str:
    current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return (current.astimezone(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")


def _leaf_ids(conn: Any, *, cutoff: str, current: str, limit: int) -> list[str]:
    rows = conn.execute(
        "SELECT e.id FROM workflow_executions e "
        "JOIN assessment_batches b ON b.execution_id = e.id "
        "WHERE e.execution_kind = ? "
        "AND e.status IN ('completed', 'failed', 'canceled') "
        "AND e.finished IS NOT NULL AND e.finished < ? "
        "AND NOT EXISTS (SELECT 1 FROM assessment_batches child "
        "WHERE child.source_execution_id = e.id) "
        "AND NOT EXISTS (SELECT 1 FROM assessment_batch_previews preview "
        "WHERE preview.source_execution_id = e.id AND preview.expires_at > ?) "
        "ORDER BY e.finished ASC, e.id ASC LIMIT ?",
        (ASSESSMENT_BATCH_EXECUTION_KIND, cutoff, current, limit),
    ).fetchall()
    return [str(row["id"]) for row in rows]


def _delete_batch_state(conn: Any, batch_id: str) -> int:
    preview_rows = conn.execute(
        "SELECT id FROM assessment_batch_previews WHERE started_execution_id = ? OR source_execution_id = ?",
        (batch_id, batch_id),
    ).fetchall()
    for row in preview_rows:
        preview_id = str(row["id"])
        conn.execute("DELETE FROM assessment_batch_preview_item_checks WHERE preview_id = ?", (preview_id,))
        conn.execute("DELETE FROM assessment_batch_preview_items WHERE preview_id = ?", (preview_id,))
        conn.execute("DELETE FROM assessment_batch_previews WHERE id = ?", (preview_id,))
    conn.execute("DELETE FROM assessment_batch_item_checks WHERE batch_id = ?", (batch_id,))
    conn.execute("DELETE FROM assessment_batch_items WHERE batch_id = ?", (batch_id,))
    conn.execute("DELETE FROM assessment_batch_events WHERE batch_id = ?", (batch_id,))
    conn.execute("DELETE FROM workflow_execution_children WHERE execution_id = ?", (batch_id,))
    conn.execute("DELETE FROM workflow_execution_steps WHERE execution_id = ?", (batch_id,))
    conn.execute("DELETE FROM assessment_batches WHERE execution_id = ?", (batch_id,))
    cursor = conn.execute("DELETE FROM workflow_executions WHERE id = ?", (batch_id,))
    return max(0, int(getattr(cursor, "rowcount", 0) or 0))


def prune_terminal_assessment_batches(
    *,
    cfg: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    limit: int = _PRUNE_LIMIT,
) -> int:
    """Delete old terminal leaves while preserving retained retry ancestry and runs."""
    retention_days = assessment_batch_settings(cfg).retention_days
    if retention_days == 0:
        return 0
    remaining = max(1, min(int(limit or _PRUNE_LIMIT), _PRUNE_LIMIT))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    current_text = current.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cutoff = _cutoff(current, retention_days)
    pruned = 0
    with db_connection_scope() as conn:
        while remaining:
            batch_ids = _leaf_ids(conn, cutoff=cutoff, current=current_text, limit=remaining)
            if not batch_ids:
                break
            deleted_on_pass = 0
            for batch_id in batch_ids:
                deleted = _delete_batch_state(conn, batch_id)
                deleted_on_pass += deleted
                pruned += deleted
                remaining -= deleted
            conn.commit()
            if deleted_on_pass == 0:
                break
    if pruned:
        log.info(
            "ASSESSMENT_BATCHES_PRUNED",
            extra={"count": pruned, "retention_days": retention_days},
        )
    return pruned


__all__ = ["prune_terminal_assessment_batches"]
