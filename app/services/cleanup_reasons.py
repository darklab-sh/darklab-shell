"""Shared cleanup reason summary helpers."""

from __future__ import annotations

from typing import Any

CLEANUP_REASON_VERSION = 1

CLEANUP_BUCKETS = ("disposable", "kept_by_default", "not_eligible")
CLEANUP_KINDS = ("entities", "findings")

CLEANUP_REASON_DEFINITIONS = {
    "default_project_link": {
        "label": "default Project link",
        "description": "Created from the run link with default cleanup-safe metadata.",
    },
    "auto_target_project_link": {
        "label": "auto target Project link",
        "description": "Created automatically from command target metadata.",
    },
    "custom_project_link": {
        "label": "custom Project link",
        "description": "Has manual or custom Project link metadata, so it is kept by default.",
    },
    "other_project_links": {
        "label": "linked to another Project",
        "description": "Still belongs to another Project.",
    },
    "entity_project_link": {
        "label": "linked to a Project",
        "description": "The Atlas entity is linked to a Project.",
    },
    "seen_in_other_runs": {
        "label": "seen elsewhere",
        "description": "Also appears in another run.",
    },
    "entity_label": {
        "label": "labeled",
        "description": "Has an Atlas entity label.",
    },
    "entity_note": {
        "label": "noted",
        "description": "Has an Atlas entity note.",
    },
    "finding_review_state": {
        "label": "reviewed finding",
        "description": "Has a finding status or review state that is not new.",
    },
    "finding_project_link": {
        "label": "finding Project link",
        "description": "The finding is directly linked to a Project.",
    },
    "finding_label": {
        "label": "finding label",
        "description": "The finding has a label.",
    },
    "finding_note": {
        "label": "finding note",
        "description": "The finding has a note.",
    },
    "finding_project_run_occurrence": {
        "label": "Project-linked occurrence",
        "description": "The finding appears in a run linked to a Project.",
    },
    "finding_direct_project_run": {
        "label": "Project-linked source run",
        "description": "The finding source run is linked to a Project.",
    },
    "finding_parent_entity_project_link": {
        "label": "Project-linked entity",
        "description": "The finding's Atlas entity is linked to a Project.",
    },
    "finding_attached_to_kept_entity": {
        "label": "attached to kept entity",
        "description": "The finding remains visible because its Atlas entity is being kept.",
    },
    "finding_attached_to_removed_entity": {
        "label": "attached to removed entity",
        "description": "The finding is removed because its Atlas entity link is removed.",
    },
    "source_run_removed": {
        "label": "source run removed",
        "description": "The finding is removed because the run link is removed.",
    },
    "imported_entity": {
        "label": "imported entity",
        "description": "Imported Atlas entities are not eligible for this cleanup.",
    },
    "imported_finding": {
        "label": "imported finding",
        "description": "Imported Atlas findings are not eligible for this cleanup.",
    },
    "entity_has_kept_findings": {
        "label": "has kept findings",
        "description": "The entity still has findings that are kept by default or not eligible for cleanup.",
    },
}

_REASON_ORDER = tuple(CLEANUP_REASON_DEFINITIONS)


def empty_cleanup_bucket_counts() -> dict[str, dict[str, int]]:
    return {bucket: {kind: 0 for kind in CLEANUP_KINDS} for bucket in CLEANUP_BUCKETS}


def set_cleanup_bucket_count(
    bucket_counts: dict[str, dict[str, int]],
    bucket: str,
    kind: str,
    count: int,
) -> None:
    if bucket not in CLEANUP_BUCKETS or kind not in CLEANUP_KINDS:
        return
    bucket_counts.setdefault(bucket, {item_kind: 0 for item_kind in CLEANUP_KINDS})[kind] = max(0, int(count or 0))


def increment_cleanup_reason(
    reason_counts: dict[tuple[str, str], dict[str, int]],
    code: str,
    bucket: str,
    kind: str,
    amount: int = 1,
) -> None:
    if code not in CLEANUP_REASON_DEFINITIONS or bucket not in CLEANUP_BUCKETS or kind not in CLEANUP_KINDS:
        return
    key = (code, bucket)
    counts = reason_counts.setdefault(key, {item_kind: 0 for item_kind in CLEANUP_KINDS})
    counts[kind] += max(0, int(amount or 0))


def build_cleanup_reason_summary(
    bucket_counts: dict[str, dict[str, int]],
    reason_counts: dict[tuple[str, str], dict[str, int]],
) -> dict[str, Any]:
    buckets: dict[str, dict[str, int]] = {}
    for bucket in CLEANUP_BUCKETS:
        entity_count = int(bucket_counts.get(bucket, {}).get("entities") or 0)
        finding_count = int(bucket_counts.get(bucket, {}).get("findings") or 0)
        buckets[bucket] = {
            "entities": entity_count,
            "findings": finding_count,
            "total": entity_count + finding_count,
        }

    reasons = []
    ordered_keys = sorted(
        reason_counts,
        key=lambda item: (_REASON_ORDER.index(item[0]) if item[0] in _REASON_ORDER else len(_REASON_ORDER), item[1]),
    )
    for code, bucket in ordered_keys:
        definition = CLEANUP_REASON_DEFINITIONS.get(code)
        if not definition:
            continue
        counts = reason_counts.get((code, bucket), {})
        entity_count = int(counts.get("entities") or 0)
        finding_count = int(counts.get("findings") or 0)
        total = entity_count + finding_count
        if total <= 0:
            continue
        reasons.append({
            "code": code,
            "bucket": bucket,
            "label": definition["label"],
            "description": definition["description"],
            "entities": entity_count,
            "findings": finding_count,
            "total": total,
        })

    return {
        "version": CLEANUP_REASON_VERSION,
        "buckets": buckets,
        "reasons": reasons,
    }
