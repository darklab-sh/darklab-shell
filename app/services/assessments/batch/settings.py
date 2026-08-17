# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validated operator policy for bounded assessment batches."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from config import resolve_effective_cfg
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_DEFAULT_INSTANCE_PARALLEL,
    BATCH_DEFAULT_ITEM_LIMIT,
    BATCH_DEFAULT_MAX_ACTIVE_PER_OWNER,
    BATCH_DEFAULT_OWNER_PARALLEL,
    BATCH_DEFAULT_PARALLEL,
    BATCH_HARD_INSTANCE_PARALLEL,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_HARD_MAX_ACTIVE_PER_OWNER,
    BATCH_HARD_OWNER_PARALLEL,
    BATCH_HARD_PARALLEL,
    BATCH_RETENTION_DAYS,
    BatchConcurrency,
)
from services.assessments.batch.policy import normalize_batch_concurrency


@dataclass(frozen=True)
class AssessmentBatchSettings:
    """The active limits applied consistently across every launch surface."""

    item_limit: int = BATCH_DEFAULT_ITEM_LIMIT
    max_active_per_owner: int = BATCH_DEFAULT_MAX_ACTIVE_PER_OWNER
    max_parallel: int = BATCH_DEFAULT_PARALLEL
    max_owner_parallel: int = BATCH_DEFAULT_OWNER_PARALLEL
    max_instance_parallel: int = BATCH_DEFAULT_INSTANCE_PARALLEL
    retention_days: int = BATCH_RETENTION_DAYS
    max_runtime_seconds: int = 14_400


def _bounded(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except TypeError, ValueError:
        return default
    return parsed if minimum <= parsed <= maximum else default


def assessment_batch_settings(
    cfg: Mapping[str, Any] | None = None,
) -> AssessmentBatchSettings:
    """Return defensive runtime settings from the validated app configuration."""
    raw = resolve_effective_cfg(cfg).get("assessment_batches", {})
    values = raw if isinstance(raw, Mapping) else {}
    return AssessmentBatchSettings(
        item_limit=_bounded(
            values.get("item_limit"),
            default=BATCH_DEFAULT_ITEM_LIMIT,
            minimum=1,
            maximum=BATCH_HARD_ITEM_LIMIT,
        ),
        max_active_per_owner=_bounded(
            values.get("max_active_per_owner"),
            default=BATCH_DEFAULT_MAX_ACTIVE_PER_OWNER,
            minimum=1,
            maximum=BATCH_HARD_MAX_ACTIVE_PER_OWNER,
        ),
        max_parallel=_bounded(
            values.get("max_parallel"),
            default=BATCH_DEFAULT_PARALLEL,
            minimum=1,
            maximum=BATCH_HARD_PARALLEL,
        ),
        max_owner_parallel=_bounded(
            values.get("max_owner_parallel"),
            default=BATCH_DEFAULT_OWNER_PARALLEL,
            minimum=1,
            maximum=BATCH_HARD_OWNER_PARALLEL,
        ),
        max_instance_parallel=_bounded(
            values.get("max_instance_parallel"),
            default=BATCH_DEFAULT_INSTANCE_PARALLEL,
            minimum=1,
            maximum=BATCH_HARD_INSTANCE_PARALLEL,
        ),
        retention_days=_bounded(
            values.get("retention_days"),
            default=BATCH_RETENTION_DAYS,
            minimum=0,
            maximum=3650,
        ),
        max_runtime_seconds=_bounded(
            values.get("max_runtime_seconds"),
            default=14_400,
            minimum=60,
            maximum=604_800,
        ),
    )


def _selection_int(value: object, *, default: int, label: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise AssessmentBatchError("invalid_batch_selection", f"{label} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError("invalid_batch_selection", f"{label} must be an integer.") from exc


def configured_preview_policy(
    values: Mapping[str, object],
    *,
    settings: AssessmentBatchSettings | None = None,
) -> tuple[int, BatchConcurrency]:
    """Resolve selection defaults without allowing client-side policy widening."""
    active = settings or assessment_batch_settings()
    item_limit = _selection_int(values.get("item_limit"), default=active.item_limit, label="Item limit")
    if not 1 <= item_limit <= active.item_limit:
        raise AssessmentBatchError(
            "invalid_batch_selection",
            f"Item limit must be between 1 and the configured maximum of {active.item_limit}.",
        )
    concurrency = normalize_batch_concurrency(
        batch=values.get("max_parallel", active.max_parallel),
        owner=values.get("max_owner_parallel", active.max_owner_parallel),
        instance=values.get("max_instance_parallel", active.max_instance_parallel),
    )
    for label, value, maximum in (
        ("Batch concurrency", concurrency.batch, active.max_parallel),
        ("Owner concurrency", concurrency.owner, active.max_owner_parallel),
        ("Instance concurrency", concurrency.instance, active.max_instance_parallel),
    ):
        if value > maximum:
            raise AssessmentBatchError(
                "invalid_batch_selection",
                f"{label} exceeds the configured maximum of {maximum}.",
            )
    return item_limit, concurrency


__all__ = [
    "AssessmentBatchSettings",
    "assessment_batch_settings",
    "configured_preview_policy",
]
