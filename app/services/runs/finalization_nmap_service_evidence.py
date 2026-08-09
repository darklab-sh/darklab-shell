# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Best-effort persistence for bounded informational Nmap service evidence."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any, Callable

from core.helpers import get_log_session_id
from services.assessments.nmap_service_evidence_persistence import (
    persist_nmap_xml_service_observations,
)
from services.metrics_lazy import app_metrics
from services.runs.persistence import run_finalize_savepoint

log = logging.getLogger("shell")


def _safe_summary(summary: object) -> dict[str, int | bool]:
    value = summary if isinstance(summary, Mapping) else {}
    return {
        "observation_count": max(0, int(value.get("observation_count") or 0)),
        "created_count": max(0, int(value.get("created_count") or 0)),
        "skipped_count": max(0, int(value.get("skipped_count") or 0)),
        "truncated": bool(value.get("truncated")),
    }


def persist_nmap_service_evidence_for_finalize(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    payload: str | None,
    observed_at: str,
    *,
    persist_nmap_xml_service_observations_fn: Callable = persist_nmap_xml_service_observations,
) -> dict[str, int | bool] | None:
    """Store informational facts without risking the completed run transaction."""
    if payload is None:
        return None
    try:
        summary = run_finalize_savepoint(
            conn,
            "nmap_service_evidence",
            lambda: _safe_summary(
                persist_nmap_xml_service_observations_fn(
                    conn,
                    session_id,
                    payload,
                    source_run_id=run_id,
                    team_id=team_id,
                    observed_at=observed_at,
                )
            ),
        )
    except Exception as exc:
        app_metrics.record_run_finalize_error("nmap_evidence")
        log.error("NMAP_SERVICE_EVIDENCE_FINALIZE_ERROR", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "error_class": type(exc).__name__,
        })
        return None
    log.info("NMAP_SERVICE_EVIDENCE_FINALIZED", extra={
        "run_id": run_id,
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        **summary,
    })
    return summary


__all__ = ["persist_nmap_service_evidence_for_finalize"]
