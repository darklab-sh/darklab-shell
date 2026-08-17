# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fixed limits and lossless chunk planning for assessment batches."""

from __future__ import annotations

from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_CHUNK_ITEM_LIMIT,
    BATCH_DEFAULT_INSTANCE_PARALLEL,
    BATCH_DEFAULT_OWNER_PARALLEL,
    BATCH_DEFAULT_PARALLEL,
    BATCH_HARD_INSTANCE_PARALLEL,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_HARD_OWNER_PARALLEL,
    BATCH_HARD_PARALLEL,
    BATCH_TARGET_PARALLEL,
    BatchConcurrency,
)


def _bounded_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise AssessmentBatchError("invalid_batch_policy", f"{name} must be an integer.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError("invalid_batch_policy", f"{name} must be an integer.") from exc
    if not minimum <= normalized <= maximum:
        raise AssessmentBatchError(
            "invalid_batch_policy",
            f"{name} must be between {minimum} and {maximum}.",
        )
    return normalized


def normalize_batch_concurrency(
    *,
    batch: object = BATCH_DEFAULT_PARALLEL,
    target: object = BATCH_TARGET_PARALLEL,
    owner: object = BATCH_DEFAULT_OWNER_PARALLEL,
    instance: object = BATCH_DEFAULT_INSTANCE_PARALLEL,
) -> BatchConcurrency:
    """Validate concurrency without weakening one-target serialization."""
    target_limit = _bounded_int(target, name="Target concurrency", minimum=1, maximum=1)
    return BatchConcurrency(
        batch=_bounded_int(batch, name="Batch concurrency", minimum=1, maximum=BATCH_HARD_PARALLEL),
        target=target_limit,
        owner=_bounded_int(owner, name="Owner concurrency", minimum=1, maximum=BATCH_HARD_OWNER_PARALLEL),
        instance=_bounded_int(
            instance,
            name="Instance concurrency",
            minimum=1,
            maximum=BATCH_HARD_INSTANCE_PARALLEL,
        ),
    )


def batch_chunk_sizes(item_count: object) -> tuple[int, ...]:
    """Partition every selected item into ordered chunks without truncation."""
    count = _bounded_int(
        item_count,
        name="Assessment batch item count",
        minimum=1,
        maximum=BATCH_HARD_ITEM_LIMIT,
    )
    full_chunks, remainder = divmod(count, BATCH_CHUNK_ITEM_LIMIT)
    sizes = (BATCH_CHUNK_ITEM_LIMIT,) * full_chunks
    if remainder:
        sizes += (remainder,)
    if sum(sizes) != count:
        raise AssertionError("assessment batch chunking lost items")
    return sizes


__all__ = ["batch_chunk_sizes", "normalize_batch_concurrency"]
