# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe public progress summaries for workflow fan-out."""

from __future__ import annotations

from collections.abc import Mapping

MAX_FAILURE_SAMPLES = 3
_STATUSES = {"pending", "running", "succeeded", "failed", "skipped"}


def summarize_fanout_results(results: object, *, cancelled: bool = False) -> dict[str, object]:
    """Return counts and bounded failure codes without exposing child values."""
    rows = results if isinstance(results, list) else []
    counts = {status: 0 for status in _STATUSES}
    failure_samples: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        status = str(row.get("status") or "pending").strip().lower()
        if status not in _STATUSES:
            status = "pending"
        counts[status] += 1
        if status == "failed" and len(failure_samples) < MAX_FAILURE_SAMPLES:
            code = str(row.get("error_code") or "child_failed").strip().lower()
            if code and code not in failure_samples and len(code) <= 64:
                failure_samples.append(code)
    return {
        "total": len(rows),
        "pending": counts["pending"],
        "running": counts["running"],
        "succeeded": counts["succeeded"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
        "cancelled": bool(cancelled),
        "failure_samples": failure_samples,
    }
