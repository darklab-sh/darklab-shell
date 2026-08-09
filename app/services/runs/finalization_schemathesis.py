# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Best-effort structured persistence for one reviewed Schemathesis run."""

from __future__ import annotations

import logging
from typing import Any, Callable

from core.helpers import get_log_session_id
from services.assessments.schemathesis_evidence_persistence import (
    persist_reviewed_schemathesis_report,
)
from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution
from services.assessments.schemathesis_report_context import (
    ReviewedSchemathesisReportContext,
)
from services.metrics_lazy import app_metrics
from services.runs.completion_policy_contracts import RunCompletionPolicy
from services.runs.persistence import run_finalize_savepoint


log = logging.getLogger("shell")


def persist_schemathesis_evidence_for_finalize(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    observed_at: str,
    active_project_link: dict[str, Any] | None,
    recorded_findings: list[dict[str, Any]],
    completion_policy: RunCompletionPolicy | None,
    *,
    persist_reviewed_schemathesis_report_fn: Callable = persist_reviewed_schemathesis_report,
) -> dict[str, Any] | None:
    """Store private report facts without making ordinary runs depend on them."""
    if type(completion_policy) is not RunCompletionPolicy:
        return None
    execution = completion_policy.schemathesis_execution
    if type(execution) is not ReviewedSchemathesisExecution:
        return None
    context = execution.report_context
    if type(context) is not ReviewedSchemathesisReportContext:
        return None
    project_id = str((active_project_link or {}).get("project_id") or "")
    if not project_id or project_id != context.project_id:
        _log_failure(
            session_id,
            team_id,
            run_id,
            context.project_id,
            "project_link_changed",
            RuntimeError("reviewed Schemathesis Project link changed"),
        )
        return None
    try:
        summary = run_finalize_savepoint(
            conn,
            "schemathesis_evidence",
            lambda: persist_reviewed_schemathesis_report_fn(
                conn,
                session_id,
                team_id,
                run_id,
                observed_at,
                context,
            ),
        )
    except Exception as exc:
        _log_failure(
            session_id,
            team_id,
            run_id,
            project_id,
            str(getattr(exc, "code", "persistence_failed") or "persistence_failed"),
            exc,
        )
        return None
    findings = summary.pop("findings", [])
    recorded_findings.extend(findings)
    log.info("SCHEMATHESIS_EVIDENCE_MATERIALIZED", extra={
        "run_id": run_id,
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "assessment_id": context.assessment_id,
        "check_id": context.check_id,
        **summary,
        "finding_ids": [str(item.get("id") or "") for item in findings],
    })
    return summary


def _log_failure(
    session_id: str,
    team_id: str,
    run_id: str,
    project_id: str,
    error_code: str,
    exc: Exception,
) -> None:
    app_metrics.record_run_finalize_error("schemathesis_evidence")
    log.error("SCHEMATHESIS_EVIDENCE_FINALIZE_ERROR", extra={
        "run_id": run_id,
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "error_code": error_code,
        "error_class": type(exc).__name__,
    })


__all__ = ["persist_schemathesis_evidence_for_finalize"]
