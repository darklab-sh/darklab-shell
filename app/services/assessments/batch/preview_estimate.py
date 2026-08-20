# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Deterministic planning windows for ordered assessment-batch chunks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from services.assessments.batch.policy import batch_chunk_sizes
from services.assessments.batch.preview_models import BatchPreviewItem


_FALLBACK_SECONDS = {
    "curl": 30,
    "ping": 10,
    "dnsrecon": 300,
    "gau": 120,
    "httpx": 120,
    "katana": 300,
    "dalfox": 60,
    "sqlmap": 120,
    "sslyze": 120,
    "testssl": 600,
    "nmap": 600,
    "nuclei": 600,
}


@dataclass(frozen=True)
class BatchDurationEstimate:
    """A conservative, non-promissory completion window."""

    minimum_seconds: int
    maximum_seconds: int
    chunk_sizes: tuple[int, ...]


def duration_bound_seconds(action_id: str, bounds: object) -> int:
    """Return an explicit command bound or a reviewed fallback ceiling."""
    if isinstance(bounds, dict):
        value = bounds.get("time_limit_seconds")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return _FALLBACK_SECONDS.get(action_id, 600)


def _chunk_maximum(items: list[BatchPreviewItem], parallel: int) -> int:
    workers = [0] * parallel
    targets: dict[str, int] = {}
    for item in items:
        worker_index = min(range(parallel), key=workers.__getitem__)
        started = max(workers[worker_index], targets.get(item.target_entity_id, 0))
        finished = started + item.duration_bound_seconds
        workers[worker_index] = finished
        targets[item.target_entity_id] = finished
    return max(workers, default=0)


def estimate_batch_duration(
    items: tuple[BatchPreviewItem, ...], *, parallel: int
) -> BatchDurationEstimate:
    """Account for 32-item barriers, worker limits, and target serialization."""
    selected = [item for item in items if item.selected]
    if not selected:
        return BatchDurationEstimate(0, 0, ())
    sizes = batch_chunk_sizes(len(selected))
    minimum = maximum = offset = 0
    for size in sizes:
        chunk = selected[offset : offset + size]
        offset += size
        target_counts = Counter(item.target_entity_id for item in chunk)
        minimum += max(
            (len(chunk) + parallel - 1) // parallel,
            max(target_counts.values(), default=0),
        )
        maximum += _chunk_maximum(chunk, parallel)
    return BatchDurationEstimate(minimum, maximum, sizes)


__all__ = [
    "BatchDurationEstimate",
    "duration_bound_seconds",
    "estimate_batch_duration",
]
