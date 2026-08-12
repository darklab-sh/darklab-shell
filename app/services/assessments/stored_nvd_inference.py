# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Unsaved finding candidates from stored NVD CPE applicability."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.assessments.nvd_cpe_correlation import correlate_stored_nvd_cpe_page
from services.assessments.version_finding_candidates import materialize_version_match_candidates


def materialize_stored_nvd_cpe_candidate_page(
    conn: Any,
    observation: dict[str, Any] | None,
    *,
    source_id: str,
    source_kind: str,
    observed_at: str,
    tool_version: str,
    parser_version: str,
    limit: int = 25,
    offset: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Page exact stored matches as provenance-complete unsaved candidates."""
    correlation = correlate_stored_nvd_cpe_page(
        conn,
        observation,
        limit=limit,
        offset=offset,
        now=now,
    )
    matches = correlation.pop("matches")
    candidates = materialize_version_match_candidates(
        observation,
        matches,
        source_id=source_id,
        source_kind=source_kind,
        observed_at=observed_at,
        tool_version=tool_version,
        parser_version=parser_version,
        require_complete_provenance=True,
    )
    correlation.update({
        "candidates": candidates,
        "matched_cve_count": len(matches),
        "unmaterialized_match_count": len(matches) - len(candidates),
    })
    return correlation


__all__ = ["materialize_stored_nvd_cpe_candidate_page"]
