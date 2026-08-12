# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment evidence cleanup that preserves historical source identity."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from services.projects.utils import now


RUN_EVIDENCE_UNAVAILABLE_REASON = "Source run deleted from History."
_RUN_ID_BATCH_SIZE = 500
_MARK_RUN_EVIDENCE_UNAVAILABLE_SQL = (
    "UPDATE project_assessment_evidence SET source_state = 'unavailable', unavailable_at = ?, "
    "unavailable_reason = ?, updated_at = ? WHERE evidence_type = 'run' "
    "AND source_state = 'available' AND evidence_id IN ({placeholders})"
)


def _run_id_batches(run_ids: Iterable[object]):
    normalized = list(dict.fromkeys(
        value
        for value in (str(run_id or "").strip() for run_id in run_ids)
        if value
    ))
    for offset in range(0, len(normalized), _RUN_ID_BATCH_SIZE):
        yield normalized[offset:offset + _RUN_ID_BATCH_SIZE]


def mark_run_evidence_unavailable_on_conn(conn: Any, run_ids: Iterable[object]) -> int:
    """Turn available run evidence into complete, idempotent tombstones."""
    timestamp = now()
    updated = 0
    for batch in _run_id_batches(run_ids):
        placeholders = ",".join("?" for _ in batch)
        # Only the number of fixed placeholders is constructed here; every id is bound.
        cursor = conn.execute(
            _MARK_RUN_EVIDENCE_UNAVAILABLE_SQL.format(placeholders=placeholders),
            [timestamp, RUN_EVIDENCE_UNAVAILABLE_REASON, timestamp, *batch],
        )
        updated += int(cursor.rowcount or 0)
    return updated
