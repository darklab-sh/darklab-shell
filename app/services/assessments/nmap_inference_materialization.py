# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded persistence orchestration for structured Nmap version inference."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from services.assessments.nmap_stored_nvd import correlate_nmap_xml_with_stored_nvd
from services.assessments.version_inference_materialization import materialize_correlated_version_inferences
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
    return materialize_correlated_version_inferences(
        conn,
        session_id,
        correlation,
        team_id=team_id,
        candidate_limit=NMAP_INFERENCE_MAX_CANDIDATES,
        persist_fn=persist_fn,
    )


__all__ = ["NMAP_INFERENCE_MAX_CANDIDATES", "materialize_nmap_xml_version_inferences"]
