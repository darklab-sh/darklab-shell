# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Best-effort confirmed takeover materialization during run finalization."""

from __future__ import annotations

from collections.abc import Sequence
import logging
from typing import Any, Callable

from core.helpers import get_log_session_id
from services.assessments.takeover_finding_materialization import materialize_takeover_confirmation
from services.metrics_lazy import app_metrics
from services.runs.persistence import run_finalize_savepoint


log = logging.getLogger("shell")


def materialize_takeover_confirmation_for_finalize(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    command: str,
    exit_code: int,
    entries: Sequence[object],
    active_project_link: dict[str, Any] | None,
    recorded_findings: list[dict[str, Any]],
    *,
    materialize_takeover_confirmation_fn: Callable = materialize_takeover_confirmation,
) -> dict[str, Any] | None:
    project_id = str((active_project_link or {}).get("project_id") or "")
    if not project_id:
        return None
    try:
        finding = run_finalize_savepoint(
            conn,
            "takeover_confirmation",
            lambda: materialize_takeover_confirmation_fn(
                conn, session_id, team_id, project_id, run_id, command, exit_code, entries,
            ),
        )
    except Exception as exc:
        app_metrics.record_run_finalize_error("takeover_confirmation")
        log.error("TAKEOVER_CONFIRMATION_FINALIZE_ERROR", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "error_class": type(exc).__name__,
        })
        return None
    if finding:
        recorded_findings.append(finding)
        log.info("TAKEOVER_CONFIRMATION_MATERIALIZED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "finding_id": str(finding.get("id") or ""),
            "finding_created": bool(finding.get("created_now")),
        })
    return finding


__all__ = ["materialize_takeover_confirmation_for_finalize"]
