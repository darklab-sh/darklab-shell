# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Strict, surface-neutral selection input for assessment-batch previews."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_DEFAULT_INSTANCE_PARALLEL,
    BATCH_DEFAULT_ITEM_LIMIT,
    BATCH_DEFAULT_OWNER_PARALLEL,
    BATCH_DEFAULT_PARALLEL,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_PREVIEW_MAX_CATEGORY_SELECTIONS,
    BATCH_PREVIEW_MAX_TARGET_SELECTIONS,
    BatchConcurrency,
)
from services.assessments.batch.policy import normalize_batch_concurrency


_ALLOWED_FIELDS = frozenset(
    {
        "target_entity_ids",
        "excluded_target_entity_ids",
        "categories",
        "excluded_categories",
        "include_standard",
        "item_limit",
        "max_parallel",
        "max_owner_parallel",
        "max_instance_parallel",
    }
)


def _identifiers(value: object, *, label: str, maximum: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise AssessmentBatchError(
            "invalid_batch_selection", f"{label} must be a list."
        )
    normalized: list[str] = []
    for item in value:
        selected = str(item or "").strip()
        if not selected or len(selected) > 128:
            raise AssessmentBatchError(
                "invalid_batch_selection", f"{label} contains an invalid value."
            )
        normalized.append(selected)
    if len(normalized) > maximum or len(set(normalized)) != len(normalized):
        raise AssessmentBatchError(
            "invalid_batch_selection", f"{label} is oversized or contains duplicates."
        )
    return tuple(sorted(normalized))


def _integer(value: object, *, default: int, label: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise AssessmentBatchError(
            "invalid_batch_selection", f"{label} must be an integer."
        )
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError(
            "invalid_batch_selection", f"{label} must be an integer."
        ) from exc
    return normalized


@dataclass(frozen=True)
class BatchPreviewSelection:
    """One validated set of targets, categories, policy, and concurrency."""

    target_entity_ids: tuple[str, ...] = ()
    excluded_target_entity_ids: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    excluded_categories: tuple[str, ...] = ()
    include_standard: bool = False
    item_limit: int = BATCH_DEFAULT_ITEM_LIMIT
    concurrency: BatchConcurrency = BatchConcurrency()

    def selects(self, target_entity_id: str, category: str) -> bool:
        """Return whether one otherwise eligible check is in the requested scope."""
        return (
            (not self.target_entity_ids or target_entity_id in self.target_entity_ids)
            and target_entity_id not in self.excluded_target_entity_ids
            and (not self.categories or category in self.categories)
            and category not in self.excluded_categories
        )

    def public(self) -> dict[str, object]:
        return {
            "target_entity_ids": list(self.target_entity_ids),
            "excluded_target_entity_ids": list(self.excluded_target_entity_ids),
            "categories": list(self.categories),
            "excluded_categories": list(self.excluded_categories),
            "include_standard": self.include_standard,
            "item_limit": self.item_limit,
        }


def normalize_preview_selection(data: object) -> BatchPreviewSelection:
    """Reject ambiguous or oversized preview selections before database work."""
    if data is None:
        values: Mapping[str, object] = {}
    elif isinstance(data, Mapping):
        values = data
    else:
        raise AssessmentBatchError(
            "invalid_batch_selection", "Assessment batch selection must be an object."
        )
    unknown = sorted(str(key) for key in values if key not in _ALLOWED_FIELDS)
    if unknown:
        raise AssessmentBatchError(
            "invalid_batch_selection",
            "Assessment batch selection contains unsupported fields.",
            details={"fields": unknown},
        )
    included_targets = _identifiers(
        values.get("target_entity_ids"),
        label="Target selection",
        maximum=BATCH_PREVIEW_MAX_TARGET_SELECTIONS,
    )
    excluded_targets = _identifiers(
        values.get("excluded_target_entity_ids"),
        label="Excluded target selection",
        maximum=BATCH_PREVIEW_MAX_TARGET_SELECTIONS,
    )
    included_categories = _identifiers(
        values.get("categories"),
        label="Category selection",
        maximum=BATCH_PREVIEW_MAX_CATEGORY_SELECTIONS,
    )
    excluded_categories = _identifiers(
        values.get("excluded_categories"),
        label="Excluded category selection",
        maximum=BATCH_PREVIEW_MAX_CATEGORY_SELECTIONS,
    )
    if set(included_targets) & set(excluded_targets) or set(included_categories) & set(
        excluded_categories
    ):
        raise AssessmentBatchError(
            "invalid_batch_selection",
            "Included and excluded assessment batch selections must not overlap.",
        )
    include_standard = values.get("include_standard", False)
    if not isinstance(include_standard, bool):
        raise AssessmentBatchError(
            "invalid_batch_selection", "include_standard must be true or false."
        )
    item_limit = _integer(
        values.get("item_limit"), default=BATCH_DEFAULT_ITEM_LIMIT, label="Item limit"
    )
    if not 1 <= item_limit <= BATCH_HARD_ITEM_LIMIT:
        raise AssessmentBatchError(
            "invalid_batch_selection",
            f"Item limit must be between 1 and {BATCH_HARD_ITEM_LIMIT}.",
        )
    concurrency = normalize_batch_concurrency(
        batch=values.get("max_parallel", BATCH_DEFAULT_PARALLEL),
        owner=values.get("max_owner_parallel", BATCH_DEFAULT_OWNER_PARALLEL),
        instance=values.get("max_instance_parallel", BATCH_DEFAULT_INSTANCE_PARALLEL),
    )
    return BatchPreviewSelection(
        target_entity_ids=included_targets,
        excluded_target_entity_ids=excluded_targets,
        categories=included_categories,
        excluded_categories=excluded_categories,
        include_standard=include_standard,
        item_limit=item_limit,
        concurrency=concurrency,
    )


__all__ = ["BatchPreviewSelection", "normalize_preview_selection"]
