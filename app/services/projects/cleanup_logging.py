# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Structured logging fields for Project cleanup mutations."""

from __future__ import annotations

from typing import Any


def project_unlink_cleanup_fields(
    data: dict[str, Any],
    cleanup_stats: dict[str, Any] | None,
) -> dict[str, int | bool]:
    stats = cleanup_stats or {}
    include_entities = bool(data.get("include_entities") or data.get("include_curated_entities"))
    include_curated = bool(data.get("include_curated_entities"))
    curated_findings = max(0, int(stats.get("curated_findings") or 0))
    kept_curated_findings = max(0, int(stats.get("kept_curated_findings") or 0))
    return {
        "include_entities_requested": include_entities,
        "include_curated_entities_requested": include_curated,
        "unlinked_entity_count": max(0, int(stats.get("removed") or 0)),
        "unlinked_finding_count": (
            max(0, int(stats.get("run_findings") or 0))
            + max(0, int(stats.get("removable_findings") or 0))
            + max(0, curated_findings - kept_curated_findings)
        ),
        "unlinked_curated_entity_count": max(0, int(stats.get("removed_curated") or 0)),
        "unlinked_curated_finding_count": max(0, curated_findings - kept_curated_findings),
        "kept_entity_count": max(0, int(stats.get("available") or 0) - int(stats.get("removed") or 0)),
        "kept_finding_count": kept_curated_findings,
    }
