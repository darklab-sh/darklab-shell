# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded persistence orchestration for structured HTTPx version inference."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from services.assessments.httpx_stored_nvd import correlate_httpx_json_with_stored_nvd
from services.assessments.version_inference_materialization import materialize_correlated_version_inferences
from services.assessments.version_inference_persistence import persist_version_inference_candidate


HTTPX_INFERENCE_MAX_CANDIDATES = 100


def materialize_httpx_json_version_inferences(
    conn: Any,
    session_id: str,
    record: dict[str, Any] | None,
    *,
    source_run_id: str,
    tool_version: str,
    team_id: str = "",
    now: datetime | None = None,
    correlate_fn: Callable[..., dict[str, Any]] = correlate_httpx_json_with_stored_nvd,
    persist_fn: Callable[..., dict[str, Any] | None] = persist_version_inference_candidate,
) -> dict[str, Any]:
    """Correlate one HTTPx JSON row and persist a capped candidate set."""
    correlation = correlate_fn(
        conn,
        record,
        source_run_id=source_run_id,
        tool_version=tool_version,
        now=now,
    )
    return materialize_correlated_version_inferences(
        conn,
        session_id,
        correlation,
        team_id=team_id,
        candidate_limit=HTTPX_INFERENCE_MAX_CANDIDATES,
        persist_fn=persist_fn,
    )


__all__ = ["HTTPX_INFERENCE_MAX_CANDIDATES", "materialize_httpx_json_version_inferences"]
