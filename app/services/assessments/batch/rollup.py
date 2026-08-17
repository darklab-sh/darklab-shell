# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Deterministic assessment-batch progress derived from child attempts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from services.assessments.batch.contracts import (
    BATCH_COULD_NOT_CANCEL_ERROR_CODE,
    BATCH_ITEM_STATUSES,
    BATCH_UNAVAILABLE_ERROR_CODES,
    AssessmentBatchError,
    BatchProgress,
)


def derive_batch_progress(
    children: Iterable[Mapping[str, object]],
    *,
    cancellation_requested: bool = False,
) -> BatchProgress:
    """Return one public rollup without storing a second item-state machine."""
    rows = list(children)
    if not rows:
        raise AssessmentBatchError(
            "empty_batch",
            "An assessment batch must contain at least one item.",
        )
    counts = {
        "pending": 0,
        "launching": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "unavailable": 0,
        "canceled": 0,
        "could_not_cancel": 0,
    }
    for row in rows:
        status = str(row.get("status") or "")
        if status not in BATCH_ITEM_STATUSES:
            raise AssessmentBatchError(
                "invalid_batch_state",
                "Assessment batch child state is invalid.",
            )
        error_code = str(row.get("error_code") or "")
        if status == "failed" and error_code == BATCH_COULD_NOT_CANCEL_ERROR_CODE:
            counts["could_not_cancel"] += 1
        elif status == "failed" and error_code in BATCH_UNAVAILABLE_ERROR_CODES:
            counts["unavailable"] += 1
        else:
            counts[status if status != "skipped" else "canceled"] += 1

    active = counts["launching"] + counts["running"]
    unsettled = counts["pending"] + active
    started = len(rows) - counts["pending"]
    if cancellation_requested:
        status = "canceling" if unsettled else "canceled"
    elif not unsettled:
        status = "completed"
    elif started:
        status = "running"
    else:
        status = "queued"
    return BatchProgress(total=len(rows), status=status, **counts)


__all__ = ["derive_batch_progress"]
