# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""One post-commit milestone for terminal Assessment batches."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re

from core.database_access import get_db_connect
from services.assessments.batch.parent_completion import (
    batch_progress_details_on_conn,
)
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


log = logging.getLogger("shell")
_SAFE_REASON_RE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})


def _timestamp(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _duration_ms(started: object, finished: object) -> int:
    start = _timestamp(started)
    end = _timestamp(finished)
    if start is None or end is None:
        return 0
    return max(0, int((end - start).total_seconds() * 1000))


def record_terminal_batch_milestone(batch_id: str, *, changed: bool) -> bool:
    """Emit once after the caller commits a real parent terminal transition."""
    if not changed:
        return False
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT status, failure_code, created, finished FROM workflow_executions "
            "WHERE id = ? AND execution_kind = ?",
            (batch_id, ASSESSMENT_BATCH_EXECUTION_KIND),
        ).fetchone()
        if not row or str(row["status"] or "") not in _TERMINAL_STATUSES:
            return False
        progress = batch_progress_details_on_conn(conn, batch_id)
    status = str(row["status"])
    reason = str(row["failure_code"] or status).strip().lower()
    if not _SAFE_REASON_RE.fullmatch(reason):
        reason = "unknown"
    log.info(
        "ASSESSMENT_BATCH_COMPLETED",
        extra={
            "batch_id": batch_id,
            "batch_status": status,
            "duration_ms": _duration_ms(row["created"], row["finished"]),
            "reason_code": reason,
            "succeeded": progress["succeeded"],
            "failed": progress["failed"],
            "unavailable": progress["unavailable"],
            "canceled": progress["canceled"],
            "could_not_cancel": progress["could_not_cancel"],
        },
    )
    return True


__all__ = ["record_terminal_batch_milestone"]
