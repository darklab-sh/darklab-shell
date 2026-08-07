# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded persistence orchestration for structured Nmap version inference."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from services.assessments.nmap_stored_nvd import correlate_nmap_xml_with_stored_nvd
from services.assessments.version_inference_persistence import persist_version_inference_candidate


NMAP_INFERENCE_MAX_CANDIDATES = 100


def materialize_nmap_xml_version_inferences(
    conn: Any,
    session_id: str,
    payload: bytes | str,
    *,
    source_run_id: str,
    team_id: str = "",
    observed_at: str = "",
    now: datetime | None = None,
    correlate_fn: Callable[..., dict[str, Any]] = correlate_nmap_xml_with_stored_nvd,
    persist_fn: Callable[..., dict[str, Any] | None] = persist_version_inference_candidate,
) -> dict[str, Any]:
    """Correlate one Nmap XML document and persist a capped candidate set."""
    correlation = correlate_fn(
        conn,
        payload,
        source_run_id=source_run_id,
        observed_at=observed_at,
        now=now,
    )
    pages = correlation.get("observations") if isinstance(correlation, dict) else None
    pages = pages if isinstance(pages, list) else []
    candidates = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("candidates"), list):
            continue
        candidates.extend(
            candidate for candidate in page["candidates"] if isinstance(candidate, dict)
        )
    selected = candidates[:NMAP_INFERENCE_MAX_CANDIDATES]
    materialized_count = 0
    finding_created_count = 0
    source_created_count = 0
    for candidate in selected:
        result = persist_fn(conn, session_id, candidate, team_id=team_id)
        if result is None:
            continue
        materialized_count += 1
        finding_created_count += int(bool(result.get("created")))
        source_created_count += int(bool(result.get("source_created")))
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
        "truncated": (
            bool(correlation.get("truncated")) if isinstance(correlation, dict) else False
        ) or skipped_count > 0,
    }


__all__ = ["NMAP_INFERENCE_MAX_CANDIDATES", "materialize_nmap_xml_version_inferences"]
