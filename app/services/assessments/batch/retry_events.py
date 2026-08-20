# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic source-lineage events for user-requested assessment-batch retries."""

from __future__ import annotations

from typing import Any

from services.assessments.batch.events import append_batch_event_on_conn


def append_retry_created_on_conn(
    conn: Any,
    source_batch_id: str,
    retry_batch_id: str,
    item_count: int,
    created: str,
) -> None:
    """Record a new retry on its immutable terminal source parent."""
    normalized_source = str(source_batch_id or "").strip()
    if not normalized_source:
        return
    append_batch_event_on_conn(
        conn,
        normalized_source,
        "retry_created",
        status="queued",
        source_batch_id=normalized_source,
        retry_batch_id=retry_batch_id,
        details={"item_count": item_count},
        created=created,
    )


__all__ = ["append_retry_created_on_conn"]
