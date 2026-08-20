# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Sanitized item event emitted by assessment-batch cancellation."""

from __future__ import annotations

from typing import Any

from services.assessments.batch.events import append_batch_event_on_conn
from services.assessments.batch.lifecycle_events import batch_child_event_identity


def record_batch_child_canceled_on_conn(conn: Any, row: Any) -> None:
    chunk_index, item_index = batch_child_event_identity(conn, row)
    append_batch_event_on_conn(
        conn,
        str(row["execution_id"]),
        "item_canceled",
        chunk_index=chunk_index,
        item_ordinal=item_index,
        status="canceled",
        reason_code="cancelled",
        run_id=str(row["run_id"] or ""),
        details={"attempt": int(row["attempt"])},
    )


__all__ = ["record_batch_child_canceled_on_conn"]
