# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Best-effort assessment finding reconciliation during run finalization."""

from __future__ import annotations

import logging
from typing import Any

from core.helpers import get_log_session_id
from services.assessments.reconciliation import reconcile_assessments_for_run_on_conn
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.runs.persistence import run_finalize_savepoint


log = logging.getLogger("shell")


def reconcile_assessment_findings_for_finalize(
    conn: Any,
    run_id: str,
    session_id: str,
    team_id: str,
    project_ids: list[str],
) -> None:
    try:
        summary = run_finalize_savepoint(
            conn,
            "assessment_finding_reconciliation",
            lambda: reconcile_assessments_for_run_on_conn(conn, run_id),
        )
    except ProjectWorkspaceQuotaExceeded as exc:
        log.warning("PROJECT_ASSESSMENT_FINDING_RECONCILIATION_SKIPPED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_ids": project_ids,
            "reason": str(exc),
        })
    except Exception:
        log.error("PROJECT_ASSESSMENT_FINDING_RECONCILIATION_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_ids": project_ids,
        })
    else:
        if int(summary.get("assessments_reconciled") or 0):
            log.info("PROJECT_ASSESSMENT_FINDINGS_RECONCILED", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "project_ids": project_ids,
                "assessment_count": int(summary.get("assessments_reconciled") or 0),
                "finding_delta_count": int(summary.get("deltas_written") or 0),
            })
