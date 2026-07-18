# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Structured logging fields for History cleanup mutations."""

from __future__ import annotations

from typing import Any


def history_cleanup_log_fields(
    cleanup_preview: dict[str, Any] | None,
    atlas_cleanup: dict[str, int],
    *,
    prune_atlas: bool,
    prune_curated_atlas: bool,
) -> dict[str, int | bool]:
    buckets = ((cleanup_preview or {}).get("cleanup_reasons") or {}).get("buckets") or {}

    def bucket_count(bucket: str, kind: str) -> int:
        return max(0, int((buckets.get(bucket) or {}).get(kind) or 0))

    removed_entities = max(0, int(atlas_cleanup.get("entities") or 0))
    removed_findings = max(0, int(atlas_cleanup.get("findings") or 0))
    disposable_entities = bucket_count("disposable", "entities")
    disposable_findings = bucket_count("disposable", "findings")
    curated_entities = bucket_count("kept_by_default", "entities")
    curated_findings = bucket_count("kept_by_default", "findings")
    total_entities = disposable_entities + curated_entities + bucket_count("not_eligible", "entities")
    total_findings = disposable_findings + curated_findings + bucket_count("not_eligible", "findings")
    removed_curated_entities = min(curated_entities, max(0, removed_entities - disposable_entities))
    removed_curated_findings = min(curated_findings, max(0, removed_findings - disposable_findings))
    return {
        "prune_atlas_requested": bool(prune_atlas),
        "prune_curated_atlas_requested": bool(prune_curated_atlas),
        "atlas_removed_entity_count": removed_entities,
        "atlas_removed_finding_count": removed_findings,
        "atlas_removed_curated_entity_count": removed_curated_entities,
        "atlas_removed_curated_finding_count": removed_curated_findings,
        "atlas_kept_entity_count": max(0, total_entities - removed_entities),
        "atlas_kept_finding_count": max(0, total_findings - removed_findings),
    }
