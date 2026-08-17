# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Immutable in-memory contracts for assessment-batch previews."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from services.assessments.batch.contracts import BatchConcurrency


@dataclass(frozen=True)
class BatchCheckMapping:
    """One frozen check that an ordinary child run may satisfy."""

    assessment_id: str
    check_id: str
    check_key: str
    target_entity_id: str
    coverage_key: str
    frozen_check_digest: str


@dataclass(frozen=True)
class BatchPreviewItem:
    """One exact, credential-free public plan and its coverage mappings."""

    execution_key: str
    selected: bool
    policy_level: str
    action_key: str
    action_id: str
    target_entity_id: str
    target_type: str
    target_value: str
    profile_identity: Mapping[str, Any]
    bounds: Mapping[str, Any]
    display_command: str
    public_plan_digest: str
    public_plan: Mapping[str, Any]
    duration_bound_seconds: int
    mappings: tuple[BatchCheckMapping, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BatchPreviewDraft:
    """A complete stable-ordered snapshot ready for server-owned storage."""

    session_id: str
    team_id: str
    project_id: str
    assessment_id: str
    profile_key: str
    profile_version: str
    selection: Mapping[str, Any]
    summary: Mapping[str, Any]
    concurrency: BatchConcurrency
    items: tuple[BatchPreviewItem, ...]


__all__ = [
    "BatchCheckMapping",
    "BatchPreviewDraft",
    "BatchPreviewItem",
]
