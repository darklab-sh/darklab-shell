# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Sanitized recovery events for assessment-batch children."""

from __future__ import annotations

from typing import Any

from services.assessments.batch.events import append_batch_event_on_conn
from services.assessments.batch.lifecycle_events import batch_child_event_identity


def record_batch_child_recovered_on_conn(conn: Any, row: Any) -> None:
    """Record one atomic abandoned-claim reset without exposing item values."""
    chunk_index, item_index = batch_child_event_identity(conn, row)
    append_batch_event_on_conn(
        conn,
        str(row["execution_id"]),
        "item_recovered",
        chunk_index=chunk_index,
        item_ordinal=item_index,
        status="pending",
        reason_code="recovery_claim_reset",
        details={"attempt": int(row["attempt"])},
    )


__all__ = ["record_batch_child_recovered_on_conn"]
