# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Sanitized assessment events attached to shared child transitions."""

from __future__ import annotations

from typing import Any

from services.assessments.batch.contracts import BATCH_CHUNK_ITEM_LIMIT
from services.assessments.batch.events import append_batch_event_on_conn


def _item(conn: Any, row: Any) -> Any:
    item = conn.execute(
        "SELECT item_index FROM assessment_batch_items "
        "WHERE batch_id = ? AND step_id = ? AND child_ordinal = ?",
        (
            str(row["execution_id"]),
            str(row["step_id"]),
            int(row["ordinal"]),
        ),
    ).fetchone()
    if not item:
        raise ValueError("assessment batch child item is unavailable")
    return item


def _event_identity(conn: Any, row: Any) -> tuple[int, int]:
    item_index = int(_item(conn, row)["item_index"])
    return item_index // BATCH_CHUNK_ITEM_LIMIT, item_index


def record_batch_child_bound_on_conn(conn: Any, row: Any, run_id: str) -> None:
    chunk_index, item_index = _event_identity(conn, row)
    append_batch_event_on_conn(
        conn,
        str(row["execution_id"]),
        "item_run_bound",
        chunk_index=chunk_index,
        item_ordinal=item_index,
        status="running",
        run_id=run_id,
        details={"attempt": int(row["attempt"])},
    )


def record_batch_child_settled_on_conn(
    conn: Any,
    row: Any,
    *,
    status: str,
    error_code: str,
    retry_child_id: str = "",
) -> None:
    chunk_index, item_index = _event_identity(conn, row)
    event_type = "item_succeeded" if status == "succeeded" else "item_failed"
    append_batch_event_on_conn(
        conn,
        str(row["execution_id"]),
        event_type,
        chunk_index=chunk_index,
        item_ordinal=item_index,
        status=status,
        reason_code=error_code,
        run_id=str(row["run_id"] or ""),
        details={"attempt": int(row["attempt"])},
    )
    if retry_child_id:
        append_batch_event_on_conn(
            conn,
            str(row["execution_id"]),
            "retry_created",
            chunk_index=chunk_index,
            item_ordinal=item_index,
            status="pending",
            reason_code=error_code,
            details={"attempt": int(row["attempt"]) + 1},
        )


__all__ = [
    "record_batch_child_bound_on_conn",
    "record_batch_child_settled_on_conn",
]
