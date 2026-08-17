# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Failure-isolated assessment-batch child finalization."""

from __future__ import annotations

import logging

from core.helpers import get_log_session_id
from services.assessments.batch.cancellation_settlement import (
    finalize_canceling_batch_run,
)
from services.assessments.batch.execution import launch_assessment_batch
from services.workflows import storage
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_child_lifecycle import finalize_fanout_child_run
from services.workflows.fanout_child_queries import fanout_child_for_run


log = logging.getLogger("shell")


def finalize_assessment_batch_run(
    run_id: str,
    exit_code: int,
) -> dict[str, object] | None:
    """Settle one saved child exactly once, then refill available launch slots."""
    child = fanout_child_for_run(run_id)
    if (
        not child
        or str(child.get("execution_kind") or "") != ASSESSMENT_BATCH_EXECUTION_KIND
    ):
        return None
    canceled = finalize_canceling_batch_run(run_id, int(exit_code))
    if canceled is not None:
        return canceled
    finalized = finalize_fanout_child_run(run_id, int(exit_code))
    if not finalized:
        return None
    launch_assessment_batch(str(child.get("execution_id") or ""))
    return finalized


def finalize_assessment_batch_run_safely(
    run_id: str,
    session_id: str,
    exit_code: int,
) -> None:
    """Keep batch advancement failures from rolling back ordinary run persistence."""
    try:
        finalize_assessment_batch_run(run_id, exit_code)
    except Exception:
        child = fanout_child_for_run(run_id) or {}
        batch_id = str(child.get("execution_id") or "")
        if batch_id:
            execution = storage.get_execution_by_id(
                batch_id,
                execution_kind=ASSESSMENT_BATCH_EXECUTION_KIND,
            ) or {}
            storage.fail_execution(
                batch_id,
                "finalization_hook_failed",
                "The assessment batch couldn't advance after its run was saved.",
                step_id=str(execution.get("current_step_id") or ""),
            )
        log.error(
            "ASSESSMENT_BATCH_FINALIZE_ERROR",
            exc_info=True,
            extra={
                "batch_id": batch_id,
                "run_id": run_id,
                "session": get_log_session_id(session_id),
            },
        )


__all__ = [
    "finalize_assessment_batch_run",
    "finalize_assessment_batch_run_safely",
]
