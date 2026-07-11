"""Shared cleanup reason summary helpers."""

from __future__ import annotations

from typing import Any

CLEANUP_REASON_VERSION = 1
CLEANUP_SAMPLE_CAP = 3
CLEANUP_SAMPLE_TEXT_MAX_LENGTH = 120

CLEANUP_BUCKETS = ("disposable", "kept_by_default", "not_eligible")
CLEANUP_KINDS = ("entities", "findings")
CLEANUP_SAMPLE_BUCKETS = ("kept_by_default", "not_eligible")

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
_CLEANUP_SAMPLE_FALLBACKS = {
    "entities": "Unknown entity",
    "findings": "Untitled finding",
}


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


def cleanup_sample_display_text(
    value: object,
    *,
    kind: str = "",
    max_length: int = CLEANUP_SAMPLE_TEXT_MAX_LENGTH,
) -> str:
    fallback = _CLEANUP_SAMPLE_FALLBACKS.get(kind, "Untitled item")
    text = str(value or "").strip() or fallback
    limit = max(1, int(max_length or 0))
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def _ordered_reason_codes(reason_codes: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    valid_codes = {
        str(code or "").strip()
        for code in reason_codes
        if str(code or "").strip() in CLEANUP_REASON_DEFINITIONS
    }
    return sorted(
        valid_codes,
        key=lambda code: _REASON_ORDER.index(code) if code in _REASON_ORDER else len(_REASON_ORDER),
    )


def _cleanup_sample_reason_payload(reason_codes: list[str] | tuple[str, ...] | set[str]) -> list[dict[str, str]]:
    return [
        {
            "code": code,
            "label": CLEANUP_REASON_DEFINITIONS[code]["label"],
        }
        for code in _ordered_reason_codes(reason_codes)
    ]


def _sample_display_record(
    display_values: dict[str, dict[str, Any]],
    kind: str,
    item_id: str,
) -> dict[str, Any]:
    raw_record = display_values.get(kind, {}).get(item_id)
    item_type = ""
    if isinstance(raw_record, dict):
        display_value = (
            raw_record.get("display_value")
            or raw_record.get("canonical_value")
            or raw_record.get("title")
            or raw_record.get("value")
            or ""
        )
        item_type = str(raw_record.get("item_type") or raw_record.get("type") or "").strip()
    else:
        display_value = raw_record
    record = {
        "display_value": cleanup_sample_display_text(display_value, kind=kind),
    }
    if item_type:
        record["item_type"] = cleanup_sample_display_text(item_type, max_length=40)
    return record


def _cleanup_sample_item(
    bucket: str,
    kind: str,
    item_id: str,
    reason_codes: list[str] | tuple[str, ...] | set[str],
    display_values: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    item = {
        "bucket": bucket,
        "kind": kind,
        **_sample_display_record(display_values, kind, item_id),
        "reasons": _cleanup_sample_reason_payload(reason_codes),
    }
    return item


class CleanupSampleCollector:
    """Keep the lowest bounded IDs per cleanup bucket/kind for later display lookup."""

    def __init__(self, *, cap: int = CLEANUP_SAMPLE_CAP) -> None:
        self.cap = max(0, int(cap or 0))
        self._records: dict[tuple[str, str], dict[str, set[str]]] = {}

    def record(
        self,
        bucket: str,
        kind: str,
        item_id: object,
        reason_codes: list[str] | tuple[str, ...] | set[str],
    ) -> None:
        if self.cap <= 0 or bucket not in CLEANUP_SAMPLE_BUCKETS or kind not in CLEANUP_KINDS:
            return
        normalized_id = str(item_id or "").strip()
        ordered_codes = _ordered_reason_codes(reason_codes)
        if not normalized_id:
            return
        records = self._records.setdefault((bucket, kind), {})
        records.setdefault(normalized_id, set()).update(ordered_codes)
        for overflow_id in sorted(records)[self.cap:]:
            records.pop(overflow_id, None)

    def ids_by_kind(self) -> dict[str, list[str]]:
        ids: dict[str, set[str]] = {kind: set() for kind in CLEANUP_KINDS}
        for (_bucket, kind), records in self._records.items():
            ids.setdefault(kind, set()).update(records)
        return {kind: sorted(values) for kind, values in ids.items() if values}

    def build(
        self,
        bucket_counts: dict[str, dict[str, int]],
        display_values: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        samples: dict[str, dict[str, dict[str, Any]]] = {}
        for bucket in CLEANUP_SAMPLE_BUCKETS:
            for kind in CLEANUP_KINDS:
                bucket_kind_total = int(bucket_counts.get(bucket, {}).get(kind) or 0)
                if bucket_kind_total <= 0:
                    continue
                records = self._records.get((bucket, kind), {})
                if not records:
                    continue
                items = [
                    _cleanup_sample_item(bucket, kind, item_id, records[item_id], display_values)
                    for item_id in sorted(records)
                ]
                omitted = max(0, bucket_kind_total - len(items))
                samples.setdefault(bucket, {})[kind] = {
                    "items": items,
                    "omitted": omitted,
                }
        return samples


def build_cleanup_reason_summary(
    bucket_counts: dict[str, dict[str, int]],
    reason_counts: dict[tuple[str, str], dict[str, int]],
    *,
    samples: dict[str, Any] | None = None,
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

    summary = {
        "version": CLEANUP_REASON_VERSION,
        "buckets": buckets,
        "reasons": reasons,
    }
    if samples:
        summary["samples"] = samples
    return summary
