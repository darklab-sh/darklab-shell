# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded persistence orchestration for applied Nessus version evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from services.assessments.nessus_stored_nvd import correlate_nessus_import_with_stored_nvd
from services.assessments.version_inference_materialization import materialize_correlated_version_inferences
from services.assessments.version_inference_persistence import persist_version_inference_candidate


NESSUS_INFERENCE_MAX_CANDIDATES = 100


def materialize_nessus_import_version_inferences(
    conn: Any,
    session_id: str,
    *,
    source_batch_id: str,
    team_id: str = "",
    now: datetime | None = None,
    correlate_fn: Callable[..., dict[str, Any]] = correlate_nessus_import_with_stored_nvd,
    persist_fn: Callable[..., dict[str, Any] | None] = persist_version_inference_candidate,
) -> dict[str, Any]:
    """Correlate one applied Nessus batch and persist a capped candidate set."""
    correlation = correlate_fn(
        conn,
        session_id,
        source_batch_id=source_batch_id,
        team_id=team_id,
        now=now,
    )
    return materialize_correlated_version_inferences(
        conn,
        session_id,
        correlation,
        team_id=team_id,
        candidate_limit=NESSUS_INFERENCE_MAX_CANDIDATES,
        persist_fn=persist_fn,
    )


__all__ = ["NESSUS_INFERENCE_MAX_CANDIDATES", "materialize_nessus_import_version_inferences"]
