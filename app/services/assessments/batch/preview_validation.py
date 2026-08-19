# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fail-closed validation for immutable assessment-batch preview drafts."""

from __future__ import annotations

from collections.abc import Mapping

from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_MAX_CHECK_MAPPINGS_PER_ITEM,
    BATCH_MAX_TOTAL_CHECK_MAPPINGS,
)
from services.assessments.batch.preview_models import (
    BatchCheckMapping,
    BatchPreviewDraft,
    BatchPreviewItem,
)
from services.assessments.batch.nuclei_preflight import blocked_nuclei_preflight
from services.assessments.probe_plan_digest import probe_plan_digest


def _is_hex_digest(value: object) -> bool:
    normalized = str(value or "")
    return len(normalized) == 64 and all(char in "0123456789abcdef" for char in normalized)


def _validate_mapping(item: BatchPreviewItem, mapping: BatchCheckMapping) -> None:
    if (
        not mapping.assessment_id
        or not mapping.check_id
        or not mapping.check_key
        or mapping.target_entity_id != item.target_entity_id
        or not _is_hex_digest(mapping.coverage_key)
        or not _is_hex_digest(mapping.frozen_check_digest)
    ):
        raise AssessmentBatchError(
            "invalid_batch_preview", "Assessment batch check mapping is invalid."
        )


def _validate_item(item: BatchPreviewItem) -> None:
    plan = item.public_plan
    target = value if isinstance(value := plan.get("target"), Mapping) else {}
    action = value if isinstance(value := plan.get("action"), Mapping) else {}
    bounds = value if isinstance(value := plan.get("bounds"), Mapping) else {}
    if (
        not _is_hex_digest(item.execution_key)
        or not _is_hex_digest(item.public_plan_digest)
        or item.policy_level not in {"safe", "standard"}
        or not item.action_key
        or not item.action_id
        or not item.target_entity_id
        or not item.target_type
        or not item.target_value
        or not item.display_command
        or not isinstance(item.selected, bool)
        or isinstance(item.duration_bound_seconds, bool)
        or not isinstance(item.duration_bound_seconds, int)
        or item.duration_bound_seconds < 1
        or not item.mappings
        or len(item.mappings) > BATCH_MAX_CHECK_MAPPINGS_PER_ITEM
        or str(plan.get("plan_digest") or "") != item.public_plan_digest
        or probe_plan_digest(plan) != item.public_plan_digest
        or str(plan.get("display_command") or "") != item.display_command
        or str(plan.get("policy_level") or "") != item.policy_level
        or str(action.get("id") or "") != item.action_id
        or item.action_key != f"command:{item.action_id}"
        or str(target.get("entity_id") or "") != item.target_entity_id
        or str(target.get("type") or "") != item.target_type
        or str(target.get("value") or "") != item.target_value
        or str(bounds.get("credential_use") or "none") != "none"
        or not bool(plan.get("launchable"))
    ):
        raise AssessmentBatchError(
            "invalid_batch_preview", "Assessment batch preview item is invalid."
        )
    for mapping in item.mappings:
        _validate_mapping(item, mapping)


def validate_preview_draft(draft: BatchPreviewDraft) -> tuple[int, int, int, int]:
    """Return selected, mapping, safe, and standard counts after validation."""
    if not draft.session_id or not draft.project_id or not draft.assessment_id:
        raise AssessmentBatchError(
            "invalid_batch_preview", "Assessment batch preview scope is invalid."
        )
    empty_allowed = bool(draft.source_batch_id) or blocked_nuclei_preflight(draft.summary)
    if len(draft.items) > BATCH_HARD_ITEM_LIMIT or (not draft.items and not empty_allowed):
        raise AssessmentBatchError(
            "invalid_batch_preview",
            f"Assessment batch previews require between 1 and {BATCH_HARD_ITEM_LIMIT} items.",
        )
    execution_keys: set[str] = set()
    check_ids: set[str] = set()
    selected = safe = standard = mappings = 0
    for item in draft.items:
        _validate_item(item)
        if item.execution_key in execution_keys:
            raise AssessmentBatchError(
                "invalid_batch_preview",
                "Assessment batch execution keys must be unique.",
            )
        execution_keys.add(item.execution_key)
        selected += int(item.selected)
        safe += int(item.policy_level == "safe")
        standard += int(item.policy_level == "standard")
        mappings += len(item.mappings)
        for mapping in item.mappings:
            if mapping.check_id in check_ids:
                raise AssessmentBatchError(
                    "invalid_batch_preview",
                    "Assessment checks may map to only one item.",
                )
            check_ids.add(mapping.check_id)
    if (not selected and not empty_allowed) or mappings > BATCH_MAX_TOTAL_CHECK_MAPPINGS:
        raise AssessmentBatchError(
            "invalid_batch_preview", "Assessment batch preview selection is invalid."
        )
    return selected, mappings, safe, standard


__all__ = ["validate_preview_draft"]
