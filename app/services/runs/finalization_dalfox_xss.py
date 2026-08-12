# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Best-effort reviewed Dalfox finding materialization during finalization."""

from __future__ import annotations

from collections.abc import Sequence
import logging
from typing import Any, Callable

from core.helpers import get_log_session_id
from services.assessments.dalfox_xss_finding_materialization import (
    materialize_dalfox_xss_findings,
)
from services.metrics_lazy import app_metrics
from services.runs.finalization_observability import log_finalize_error
from services.runs.persistence import run_finalize_savepoint


log = logging.getLogger("shell")


def materialize_dalfox_xss_findings_for_finalize(
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
    materialize_dalfox_xss_findings_fn: Callable = materialize_dalfox_xss_findings,
) -> list[dict[str, Any]]:
    project_id = str((active_project_link or {}).get("project_id") or "")
    if not project_id:
        return []
    try:
        findings = run_finalize_savepoint(
            conn,
            "dalfox_xss_findings",
            lambda: materialize_dalfox_xss_findings_fn(
                conn, session_id, team_id, project_id, run_id, command, exit_code, entries,
            ),
        )
    except Exception as exc:
        app_metrics.record_run_finalize_error("dalfox_xss_findings")
        log_finalize_error(
            log,
            "DALFOX_XSS_FINDINGS_FINALIZE_ERROR",
            exc,
            "dalfox_xss_findings",
            run_id=run_id,
            session=get_log_session_id(session_id),
            team_id=team_id,
            project_id=project_id,
        )
        return []
    if findings:
        recorded_findings.extend(findings)
        log.info("DALFOX_XSS_FINDINGS_MATERIALIZED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "finding_count": len(findings),
            "finding_created_count": sum(bool(item.get("created_now")) for item in findings),
            "finding_ids": [str(item.get("id") or "") for item in findings],
        })
    return findings


__all__ = ["materialize_dalfox_xss_findings_for_finalize"]
