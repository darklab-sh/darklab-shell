# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared bounded persistence for prevalidated version-inference pages."""

from __future__ import annotations

from typing import Any, Callable

from services.assessments.version_inference_persistence import persist_version_inference_candidate


def materialize_correlated_version_inferences(
    conn: Any,
    session_id: str,
    correlation: dict[str, Any] | None,
    *,
    team_id: str = "",
    candidate_limit: int,
    persist_fn: Callable[..., dict[str, Any] | None] = persist_version_inference_candidate,
) -> dict[str, Any]:
    """Persist a capped set of candidates from one read-only correlation result."""
    result = correlation if isinstance(correlation, dict) else {}
    pages = result.get("observations")
    pages = pages if isinstance(pages, list) else []
    candidates = [
        candidate
        for page in pages
        if isinstance(page, dict) and isinstance(page.get("candidates"), list)
        for candidate in page["candidates"]
        if isinstance(candidate, dict)
    ]
    selected = candidates[:max(0, candidate_limit)]
    materialized_count = finding_created_count = source_created_count = 0
    for candidate in selected:
        saved = persist_fn(conn, session_id, candidate, team_id=team_id)
        if saved is None:
            continue
        materialized_count += 1
        finding_created_count += int(bool(saved.get("created")))
        source_created_count += int(bool(saved.get("source_created")))
    skipped_count = max(0, len(candidates) - len(selected))
    return {
        "observation_count": len(pages),
        "candidate_count": len(candidates),
        "attempted_count": len(selected),
        "materialized_count": materialized_count,
        "finding_created_count": finding_created_count,
        "source_created_count": source_created_count,
        "rejected_count": len(selected) - materialized_count,
        "skipped_count": skipped_count,
        "truncated": bool(result.get("truncated")) or skipped_count > 0,
    }


__all__ = ["materialize_correlated_version_inferences"]
