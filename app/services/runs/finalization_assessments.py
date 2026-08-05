# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment hooks for completed-run persistence."""

from __future__ import annotations

from typing import Any, Callable
import logging

from core.helpers import get_log_session_id
from services.assessments.coverage import reconcile_run_evidence_on_conn
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.runs.finalization_summaries import auto_promote_summary_ids, auto_promote_summary_results
from services.runs.persistence import run_finalize_savepoint


log = logging.getLogger("shell")


def reconcile_assessment_evidence_for_finalize(
    conn: Any,
    run_id: str,
    session_id: str,
    team_id: str,
    active_project_link: dict | None,
    auto_promote_summary: dict | None,
    *,
    reconcile_run_evidence_fn: Callable = reconcile_run_evidence_on_conn,
) -> dict[str, int] | None:
    """Link compatible evidence without making assessment work fatal to a run."""
    project_ids = auto_promote_summary_ids(auto_promote_summary_results(auto_promote_summary), "project_id")
    active_project_id = str((active_project_link or {}).get("project_id") or "")
    if active_project_id:
        project_ids = sorted({*project_ids, active_project_id})
    if not project_ids:
        return None
    try:
        summary = run_finalize_savepoint(
            conn,
            "assessment_evidence",
            lambda: reconcile_run_evidence_fn(conn, run_id),
        )
    except ProjectWorkspaceQuotaExceeded as exc:
        log.warning("PROJECT_ASSESSMENT_EVIDENCE_SKIPPED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_ids": project_ids,
            "reason": str(exc),
        })
        return None
    except Exception:
        log.error("PROJECT_ASSESSMENT_EVIDENCE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_ids": project_ids,
        })
        return None
    if int(summary.get("checks_matched") or 0):
        log.info("PROJECT_ASSESSMENT_EVIDENCE_MATCHED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_ids": project_ids,
            **{key: int(value or 0) for key, value in summary.items()},
        })
    return summary
