# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Observed exact-value resolution for Project-scoped probes."""

from __future__ import annotations

import logging
import time

from core.database_access import get_db_connect
from services.assessments.probe_contracts import PROBE_TARGET_TYPES, ProbeError, ProbePlanRequest
from services.assessments.probe_log_context import ProbeLogContext, probe_context_fields
from services.assessments.probe_log_safety import safe_probe_code, safe_probe_id
from services.assessments.probe_observability_support import sanitized_probe_exc_info
from services.assessments.probe_targets import resolve_probe_target
from services.metrics_lazy import app_metrics


log = logging.getLogger("shell")
_WARN_CODES = frozenset({"probe_target_ambiguous", "probe_target_type_unsupported", "project_archived"})


def _fields(
    project_id: str,
    context: ProbeLogContext | None,
    *,
    entity_id: str = "",
    target_type: str = "",
    candidate_count: int = 0,
    error_code: str = "",
    started: float,
) -> dict[str, object]:
    return {
        **probe_context_fields((context,), {}),
        "project_id": safe_probe_id(project_id, "prj"),
        "entity_id": safe_probe_id(entity_id, "ent"),
        "target_type": target_type if target_type in PROBE_TARGET_TYPES else "",
        "selector_kind": "exact_value",
        "candidate_count": min(max(candidate_count, 0), 3),
        "duration_ms": max(round((time.monotonic() - started) * 1000), 0),
        "error_code": safe_probe_code(error_code, "") if error_code else "",
    }


def resolve_observed_probe_target(
    session_id: str,
    project_id: str,
    *,
    team_id: str,
    target_value: str,
    observability: ProbeLogContext | None,
) -> dict[str, str]:
    started = time.monotonic()
    request = ProbePlanRequest(project_id=project_id, action_id="", target_value=target_value)
    try:
        with get_db_connect()() as conn:
            target = resolve_probe_target(conn, session_id, team_id, request)
    except ProbeError as exc:
        candidates = exc.details.get("candidate_entity_ids")
        count = len(candidates) if isinstance(candidates, list) else 0
        app_metrics.record_probe_operation("resolve", "rejected")
        logger = log.warning if exc.code in _WARN_CODES else log.info
        logger(
            "PROJECT_PROBE_TARGET_REJECTED",
            extra=_fields(
                project_id, observability, candidate_count=count,
                error_code=exc.code, started=started,
            ),
        )
        raise
    except Exception as exc:
        app_metrics.record_probe_operation("resolve", "failed")
        log.error(
            "PROJECT_PROBE_TARGET_RESOLUTION_FAILED",
            exc_info=sanitized_probe_exc_info(exc),
            extra=_fields(project_id, observability, error_code="unexpected_failure", started=started),
        )
        raise
    app_metrics.record_probe_operation("resolve", "success")
    log.debug(
        "PROJECT_PROBE_TARGET_RESOLVED",
        extra=_fields(
            project_id, observability, entity_id=target["entity_id"],
            target_type=target["type"], candidate_count=1, started=started,
        ),
    )
    return target


__all__ = ["resolve_observed_probe_target"]
