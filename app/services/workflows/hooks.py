# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Failure-isolated hooks from the shared run lifecycle."""

from __future__ import annotations

import logging

from core.helpers import get_log_session_id
from services.metrics_lazy import app_metrics
from services.workflows.executions import execution_elapsed_seconds, finalize_workflow_run
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_child_queries import fanout_child_for_run
from services.workflows.storage import execution_for_run, fail_execution_for_run


log = logging.getLogger("shell")


def finalize_workflow_run_safely(persisted, run_id, session_id, exit_code, capture) -> None:
    if not persisted:
        return
    try:
        child = fanout_child_for_run(run_id)
        if (
            child
            and str(child.get("execution_kind") or "")
            == ASSESSMENT_BATCH_EXECUTION_KIND
        ):
            from services.assessments.batch.finalization import (  # noqa: PLC0415
                finalize_assessment_batch_run_safely,
            )

            finalize_assessment_batch_run_safely(
                run_id,
                session_id,
                int(exit_code),
            )
            return
        finalize_workflow_run(run_id, exit_code, capture)
    except Exception:
        execution = execution_for_run(run_id) or {}
        changed = fail_execution_for_run(
            run_id,
            "finalization_hook_failed",
            "The workflow could not advance after its run was saved.",
        )
        if changed:
            app_metrics.record_workflow_step_outcome("failed")
            app_metrics.record_workflow_execution_outcome(
                "failed",
                execution_elapsed_seconds(execution),
            )
        log.error("WORKFLOW_FINALIZE_ERROR", exc_info=True, extra={
            "execution_id": str(execution.get("id") or ""),
            "step_id": str(execution.get("current_step_id") or ""),
            "run_id": run_id,
            "stage": "run_finalization_hook",
            "session": get_log_session_id(session_id),
        })
