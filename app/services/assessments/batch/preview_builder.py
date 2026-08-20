# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""In-memory assembly for stable, deduplicated assessment-batch previews."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.action_plan_payload import digest_plan
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_MAX_CHECK_MAPPINGS_PER_ITEM,
    BATCH_MAX_TOTAL_CHECK_MAPPINGS,
    BATCH_PREVIEW_BUILD_MAX_BYTES,
    BATCH_PREVIEW_MAX_CHECK_ROWS,
)
from services.assessments.batch.plan_policy import (
    batch_execution_key,
    evaluate_shared_batch,
)
from services.assessments.batch.preview_classification import (
    check_exclusion_reason,
    target_review_hints,
)
from services.assessments.batch.preview_estimate import (
    duration_bound_seconds,
    estimate_batch_duration,
)
from services.assessments.batch.preview_models import BatchCheckMapping, BatchPreviewItem
from services.assessments.batch.nuclei_preflight import NucleiPreflightTracker
from services.assessments.batch.preview_selection import BatchPreviewSelection
from services.assessments.batch.preview_summary import build_preview_summary
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.assessments.probe_plans import build_probe_plan
from services.assessments.probe_runtime import ProbePlanningRuntime


@dataclass
class _CompiledItem:
    execution_key: str
    policy_level: str
    action_key: str
    action_id: str
    target: dict[str, str]
    plan: dict[str, Any]
    duration_bound_seconds: int
    selected: bool
    mappings: list[BatchCheckMapping] = field(default_factory=list)


def _canonical_size(value: object) -> int:
    return len(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
    )


def _frozen_checks(snapshot: object) -> dict[str, Mapping[str, Any]]:
    decoded = dialect_for_backend(get_db_backend()).decode_json_dict(snapshot)
    checks: dict[str, Mapping[str, Any]] = {}
    for item in decoded.get("checks", []):
        if isinstance(item, Mapping):
            key = str(item.get("key") or "")
            if key:
                checks[key] = item
    return checks


def _target(row: Any) -> dict[str, str]:
    return {
        "entity_id": str(row["current_target_id"] or ""),
        "type": str(row["current_target_type"] or ""),
        "value": str(row["current_target_value"] or ""),
    }


def _plan(
    row: Any,
    project_id: str,
    action_id: str,
    runtime: ProbePlanningRuntime,
) -> dict[str, Any]:
    policy = str(row["policy_level"] or "")
    request = ProbePlanRequest(
        project_id=project_id,
        action_id=action_id,
        entity_id=str(row["target_entity_id"] or ""),
        nuclei_profile=policy if action_id == "nuclei" else "safe",
    )
    plan = build_probe_plan(
        request,
        _target(row),
        available_features=runtime.available_features,
        intrusive_actions_enabled=False,
        template_snapshot=runtime.template_snapshot,
    )
    if not plan.get("launchable"):
        availability = plan.get("availability")
        available = availability if isinstance(availability, Mapping) else {}
        raise AssessmentBatchError(
            str(available.get("code") or "plan_unavailable"),
            str(available.get("reason") or "This check isn't available for a batch."),
        )
    decision = evaluate_shared_batch(
        [plan],
        minimum_items=1,
        maximum_items=1,
        allowed_policy_levels={"safe", "standard"},
        excluded_actions={"schemathesis", "zap", "oast"},
        require_exact_command=False,
    )
    if not decision.allowed:
        raise AssessmentBatchError(
            decision.code or "plan_unavailable",
            decision.reason or "This check isn't eligible for an assessment batch.",
        )
    return plan


def _mapping(row: Any, frozen: Mapping[str, Any]) -> BatchCheckMapping:
    frozen_digest = digest_plan(frozen)
    identity = {
        "assessment_id": str(row["assessment_id"] or ""),
        "check_id": str(row["check_id"] or ""),
        "check_key": str(row["check_key"] or ""),
        "target_entity_id": str(row["target_entity_id"] or ""),
        "frozen_check_digest": frozen_digest,
    }
    return BatchCheckMapping(
        assessment_id=identity["assessment_id"],
        check_id=identity["check_id"],
        check_key=identity["check_key"],
        target_entity_id=identity["target_entity_id"],
        coverage_key=digest_plan(identity),
        frozen_check_digest=frozen_digest,
    )


def _public_item(item: _CompiledItem) -> BatchPreviewItem:
    return BatchPreviewItem(
        execution_key=item.execution_key,
        selected=item.selected,
        policy_level=item.policy_level,
        action_key=item.action_key,
        action_id=item.action_id,
        target_entity_id=item.target["entity_id"],
        target_type=item.target["type"],
        target_value=item.target["value"],
        profile_identity={
            "tool": dict(item.plan.get("profile") or {}),
            "http": dict(item.plan.get("http_profile") or {}),
        },
        bounds=dict(item.plan.get("bounds") or {}),
        display_command=str(item.plan.get("display_command") or ""),
        public_plan_digest=str(item.plan.get("plan_digest") or ""),
        public_plan=item.plan,
        duration_bound_seconds=item.duration_bound_seconds,
        mappings=tuple(sorted(item.mappings, key=lambda value: value.check_id)),
    )


def _sort_key(item: _CompiledItem) -> tuple[str, ...]:
    return (
        item.target["type"],
        item.target["value"].casefold(),
        item.action_id,
        item.policy_level,
        str(item.plan.get("display_command") or ""),
        item.execution_key,
    )


class BatchPreviewBuilder:
    """Collect bounded check rows into one immutable preview draft body."""

    def __init__(
        self,
        project_id: str,
        selection: BatchPreviewSelection,
        runtime: ProbePlanningRuntime,
        profile_snapshot: object,
    ) -> None:
        self.project_id = project_id
        self.selection = selection
        self.runtime = runtime
        self.frozen_by_key = _frozen_checks(profile_snapshot)
        self.reasons: Counter[str] = Counter()
        self.compiled: dict[tuple[str, ...], _CompiledItem] = {}
        self.target_ids: set[str] = set()
        self.categories: set[str] = set()
        self.target_hints: dict[str, dict[str, object]] = {}
        self.selected_target_ids: set[str] = set()
        self.selected_categories: set[str] = set()
        self.check_count = 0
        self.mapping_count = 0
        self.build_bytes = 0
        self.nuclei_preflight = NucleiPreflightTracker(runtime.template_health)

    def observe(self, row: Any) -> None:
        """Classify and, when eligible, merge one streamed frozen check row."""
        self.check_count += 1
        if self.check_count > BATCH_PREVIEW_MAX_CHECK_ROWS:
            raise AssessmentBatchError(
                "preview_check_limit_exceeded",
                f"Assessment batch previews support at most {BATCH_PREVIEW_MAX_CHECK_ROWS} checks.",
                status_code=409,
            )
        target_id = str(row["target_entity_id"] or "")
        category = str(row["category"] or "")
        self.target_ids.add(target_id)
        self.categories.add(category)
        frozen = self.frozen_by_key.get(str(row["check_key"] or ""))
        reason = check_exclusion_reason(row, frozen)
        if reason:
            self.reasons[reason] += 1
            return
        if not self.selection.selects(target_id, category):
            self.reasons["selection_excluded"] += 1
            return
        self._remember_hints(row)
        action_key = str(row["recommended_action_key"] or "")
        action_id = action_key.partition(":")[2]
        self.nuclei_preflight.observe(action_id, row, self.selection.include_standard)
        try:
            plan = _plan(row, self.project_id, action_id, self.runtime)
        except (AssessmentBatchError, ProbeError) as exc:
            self.reasons[str(getattr(exc, "code", "plan_unavailable"))] += 1
            return
        execution_identity = batch_execution_key(plan)
        item = self.compiled.get(execution_identity)
        if item is None:
            item = self._new_item(row, action_key, action_id, plan, execution_identity)
            self.compiled[execution_identity] = item
        if item.selected:
            self.selected_target_ids.add(target_id)
            self.selected_categories.add(category)
        self._add_mapping(item, row, frozen or {})

    def _remember_hints(self, row: Any) -> None:
        hints = target_review_hints(row)
        if not hints:
            return
        target_id = str(row["target_entity_id"] or "")
        self.target_hints[target_id] = {
            "target_entity_id": target_id,
            "target_type": str(row["target_type"] or ""),
            "target_value": str(row["target_value"] or ""),
            "hints": list(hints),
        }

    def _new_item(
        self,
        row: Any,
        action_key: str,
        action_id: str,
        plan: dict[str, Any],
        execution_identity: tuple[str, ...],
    ) -> _CompiledItem:
        if len(self.compiled) >= BATCH_HARD_ITEM_LIMIT:
            raise AssessmentBatchError(
                "preview_candidate_limit_exceeded",
                f"Assessment batch previews support at most {BATCH_HARD_ITEM_LIMIT} candidate commands.",
                status_code=409,
            )
        item = _CompiledItem(
            execution_key=digest_plan({"execution": execution_identity}),
            policy_level=str(row["policy_level"] or ""),
            action_key=action_key,
            action_id=action_id,
            target=_target(row),
            plan=plan,
            duration_bound_seconds=duration_bound_seconds(action_id, plan.get("bounds")),
            selected=(
                str(row["policy_level"] or "") == "safe"
                or self.selection.include_standard
            ),
        )
        self.build_bytes += _canonical_size(plan) + _canonical_size(execution_identity)
        return item

    def _add_mapping(
        self, item: _CompiledItem, row: Any, frozen: Mapping[str, Any]
    ) -> None:
        if len(item.mappings) >= BATCH_MAX_CHECK_MAPPINGS_PER_ITEM:
            raise AssessmentBatchError(
                "preview_mapping_limit_exceeded",
                f"One shared command maps to more than {BATCH_MAX_CHECK_MAPPINGS_PER_ITEM} checks.",
                status_code=409,
            )
        self.mapping_count += 1
        if self.mapping_count > BATCH_MAX_TOTAL_CHECK_MAPPINGS:
            raise AssessmentBatchError(
                "preview_mapping_limit_exceeded",
                "The assessment batch preview has too many check mappings.",
                status_code=409,
            )
        mapping = _mapping(row, frozen)
        item.mappings.append(mapping)
        self.build_bytes += _canonical_size(mapping.__dict__)
        self._check_memory()

    def _check_memory(self) -> None:
        if self.build_bytes > BATCH_PREVIEW_BUILD_MAX_BYTES:
            raise AssessmentBatchError(
                "preview_memory_limit_exceeded",
                "The assessment batch preview is too large to build safely.",
                status_code=409,
            )

    def _validate_scope(self) -> None:
        selected_targets = set(self.selection.target_entity_ids) | set(
            self.selection.excluded_target_entity_ids
        )
        selected_categories = set(self.selection.categories) | set(
            self.selection.excluded_categories
        )
        missing_targets = sorted(selected_targets - self.target_ids)
        missing_categories = sorted(selected_categories - self.categories)
        if missing_targets or missing_categories:
            raise AssessmentBatchError(
                "batch_selection_not_found",
                "One or more selected assessment targets or categories weren't found.",
                status_code=409,
                details={
                    "target_entity_ids": missing_targets,
                    "categories": missing_categories,
                },
            )

    def finish(
        self, source: Any, *, allow_empty: bool = False
    ) -> tuple[tuple[BatchPreviewItem, ...], dict[str, object]]:
        """Validate selection limits and return stable items plus compact summary."""
        self._validate_scope()
        items = tuple(
            _public_item(item) for item in sorted(self.compiled.values(), key=_sort_key)
        )
        selected = [item for item in items if item.selected]
        if not selected and not allow_empty and not self.nuclei_preflight:
            raise AssessmentBatchError(
                "empty_batch_plan",
                "No supported assessment commands are selected. Include standard "
                "checks or change the target and category selection.",
                status_code=409,
                details={"reason_counts": dict(sorted(self.reasons.items()))},
            )
        if len(selected) > self.selection.item_limit:
            raise AssessmentBatchError(
                "preview_item_limit_exceeded",
                f"The selection has {len(selected)} commands, above its "
                f"{self.selection.item_limit}-item limit. Narrow the selection or "
                "raise the limit and preview again.",
                status_code=409,
                details={"selected_item_count": len(selected), "item_limit": self.selection.item_limit},
            )
        estimate = estimate_batch_duration(
            items, parallel=self.selection.concurrency.batch
        )
        summary = build_preview_summary(
            check_count=self.check_count,
            reasons=self.reasons,
            items=items,
            selected=selected,
            target_hints=self.target_hints,
            selected_target_ids=self.selected_target_ids,
            selected_categories=self.selected_categories,
            source=source,
            estimate=estimate,
        )
        summary.update(self.nuclei_preflight.summary())
        self.build_bytes += _canonical_size(self.selection.public()) + _canonical_size(
            summary
        )
        self._check_memory()
        return items, summary


__all__ = ["BatchPreviewBuilder"]
