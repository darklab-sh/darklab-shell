# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Compact public summary for one complete assessment-batch preview."""

from __future__ import annotations

from collections import Counter
from typing import Any

from services.assessments.batch.preview_models import BatchPreviewItem


_UNAVAILABLE_CODES = frozenset(
    {
        "plan_unavailable",
        "feature_unavailable",
        "target_unavailable",
        "target_changed",
    }
)


def build_preview_summary(
    *,
    check_count: int,
    reasons: Counter[str],
    items: tuple[BatchPreviewItem, ...],
    selected: list[BatchPreviewItem],
    target_hints: dict[str, dict[str, object]],
    selected_target_ids: set[str],
    selected_categories: set[str],
    source: Any,
    estimate: Any,
) -> dict[str, object]:
    """Describe selection, exclusions, credentials, chunking, and duration."""
    standard_selected = any(item.policy_level == "standard" for item in selected)
    return {
        "check_count": check_count,
        "eligible_check_count": sum(len(item.mappings) for item in items),
        "candidate_item_count": len(items),
        "selected_item_count": len(selected),
        "selected_target_count": len(selected_target_ids),
        "selected_target_entity_ids": sorted(selected_target_ids),
        "selected_categories": sorted(selected_categories),
        "fan_out": len(selected),
        "credential_classification": "none",
        "explicit_request_limit_item_count": sum(
            item.bounds.get("request_limit") is not None for item in selected
        ),
        "tool_bounded_request_item_count": sum(
            item.bounds.get("request_limit") is None for item in selected
        ),
        "maximum_item_duration_bound_seconds": max(
            (item.duration_bound_seconds for item in selected), default=0
        ),
        "potential_covered_check_count": sum(len(item.mappings) for item in selected),
        "safe_item_count": sum(item.policy_level == "safe" for item in items),
        "standard_item_count": sum(item.policy_level == "standard" for item in items),
        "standard_selected": standard_selected,
        "requires_standard_confirmation": standard_selected,
        "unavailable_check_count": sum(
            count for code, count in reasons.items() if code in _UNAVAILABLE_CODES
        ),
        "skipped_check_count": sum(reasons.values()),
        "reason_counts": dict(sorted(reasons.items())),
        "target_review_hints": [target_hints[key] for key in sorted(target_hints)],
        "enabled_http_profile_count": source.enabled_http_profile_count,
        "credentialed_http_profile_count": source.credentialed_http_profile_count,
        "credentialed_work_remains_individual": bool(
            source.credentialed_http_profile_count
        ),
        "chunk_sizes": list(estimate.chunk_sizes),
        "estimated_min_seconds": estimate.minimum_seconds,
        "estimated_max_seconds": estimate.maximum_seconds,
        "estimate_label": "Planning estimate, not a completion promise.",
    }


__all__ = ["build_preview_summary"]
