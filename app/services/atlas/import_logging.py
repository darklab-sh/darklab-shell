# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded numeric fields for Atlas import logs and audit records."""

from __future__ import annotations

from typing import Any

_WORKFLOW_COUNT_FIELDS = (
    "rows", "valid", "skipped", "warnings", "duplicate", "new", "updated",
    "entity_valid", "entity_new", "entity_duplicate",
    "finding_valid", "finding_new", "finding_duplicate",
    "evidence_valid", "evidence_new", "finding_subject_entities_to_create",
    "project_target_candidates", "entities_created", "entities_updated",
    "findings_created", "findings_updated", "finding_remediations_imported",
    "entity_links", "finding_occurrences", "evidence_imported",
    "project_links_added", "project_links_existing",
    "project_targets_created", "project_targets_existing",
)

_ROUTE_COUNT_FIELDS = tuple(
    field for field in _WORKFLOW_COUNT_FIELDS
    if field not in {"duplicate", "finding_remediations_imported"}
)


def safe_count_fields(counts: Any) -> dict[str, int]:
    """Return the complete low-cardinality count set used by service logs."""
    return _count_fields(counts, _WORKFLOW_COUNT_FIELDS)


def route_count_log_fields(counts: Any) -> dict[str, int]:
    """Return the stable route/audit count set without source record contents."""
    return _count_fields(counts, _ROUTE_COUNT_FIELDS)


def _count_fields(counts: Any, names: tuple[str, ...]) -> dict[str, int]:
    raw = counts if isinstance(counts, dict) else {}
    fields: dict[str, int] = {}
    for key in names:
        if key not in raw:
            continue
        try:
            fields[key] = int(raw.get(key) or 0)
        except (TypeError, ValueError):
            fields[key] = 0
    return fields


__all__ = ["route_count_log_fields", "safe_count_fields"]
