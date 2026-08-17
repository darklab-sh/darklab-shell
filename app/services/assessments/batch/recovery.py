# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Startup recovery for heterogeneous durable assessment batches."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.batch.cancellation import (
    request_batch_cancellation_on_conn,
    signal_batch_cancellation_runs,
)
from services.assessments.batch.cancellation_settlement import (
    finalize_canceling_batch_run,
)
from services.assessments.batch.finalization import finalize_assessment_batch_run
from services.assessments.batch.recovery_snapshot import (
    BatchRecoverySnapshotError,
    load_batch_recovery_snapshot,
)
from services.assessments.batch.recovery_stop import (
    stop_assessment_batch_for_recovery,
)
from services.assessments.batch.execution import launch_assessment_batch
from services.metrics_lazy import app_metrics
from services.workflows import storage
from services.workflows.execution_authorization import (
    current_execution_role,
    execution_expired,
)
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_child_lifecycle import (
    finalize_fanout_child_run,
    reset_launching_fanout_child_for_recovery,
)
from services.workflows.recovery_runs import run_is_still_active


log = logging.getLogger("shell")
_RESULT_KEYS = ("recovered", "left_running", "failed", "ignored")


def _active_children(children: object) -> list[Mapping[str, object]]:
    if not isinstance(children, list):
        return []
    return [
        child
        for child in children
        if isinstance(child, Mapping)
        and str(child.get("status") or "") in {"launching", "running"}
    ]


def _recover_canceling(
    execution: Mapping[str, object],
    children: object,
) -> str:
    batch_id = str(execution.get("id") or "")
    session_id = str(execution.get("session_id") or "")
    team_id = str(execution.get("team_id") or "")
    dialect = dialect_for_backend(get_db_backend())
    with get_db_connect()() as conn:
        conn.execute(dialect.begin_immediate_sql())
        run_ids = request_batch_cancellation_on_conn(
            conn,
            session_id,
            batch_id,
            team_id=team_id,
        )
        conn.commit()
    if run_ids:
        signal_batch_cancellation_runs(
            session_id,
            ((batch_id, run_ids),),
            team_id=team_id,
        )
    recovered = False
    live = False
    for child in _active_children(children):
        run_id = str(child.get("run_id") or "")
        if not run_id:
            continue
        completed = storage.completed_run_for_recovery(run_id)
        if completed:
            recovered = bool(
                finalize_assessment_batch_run(
                    run_id,
                    int(str(completed.get("exit_code") or 0)),
                )
            ) or recovered
        elif run_is_still_active(execution, run_id):
            live = True
        else:
            recovered = bool(finalize_canceling_batch_run(run_id, 1)) or recovered
    refreshed = storage.get_execution_by_id(
        batch_id,
        execution_kind=ASSESSMENT_BATCH_EXECUTION_KIND,
    )
    if not refreshed or str(refreshed.get("status") or "") in {
        "completed",
        "failed",
        "canceled",
    }:
        return "recovered" if recovered or bool(refreshed) else "ignored"
    return "recovered" if recovered else "left_running" if live else "recovered"


def _stop_and_reconcile(
    execution: Mapping[str, object],
    reason_code: str,
    detail: str,
) -> str:
    batch_id = str(execution.get("id") or "")
    stopped = stop_assessment_batch_for_recovery(batch_id, reason_code, detail)
    for run_id in tuple(stopped.get("run_ids") or ()):
        completed = storage.completed_run_for_recovery(str(run_id))
        if completed:
            finalize_assessment_batch_run(
                str(run_id),
                int(str(completed.get("exit_code") or 0)),
            )
        elif not run_is_still_active(execution, str(run_id)):
            finalize_canceling_batch_run(str(run_id), 1)
    return "failed"


def _recover_runnable(
    execution: Mapping[str, object],
    children: object,
) -> str:
    batch_id = str(execution.get("id") or "")
    recovered = False
    for child in _active_children(children):
        status = str(child.get("status") or "")
        run_id = str(child.get("run_id") or "")
        if status == "launching" and not run_id:
            recovered = reset_launching_fanout_child_for_recovery(
                str(child.get("id") or "")
            ) or recovered
            continue
        if status != "running" or not run_id:
            continue
        completed = storage.completed_run_for_recovery(run_id)
        if completed:
            recovered = bool(
                finalize_assessment_batch_run(
                    run_id,
                    int(str(completed.get("exit_code") or 0)),
                )
            ) or recovered
            continue
        if run_is_still_active(execution, run_id):
            continue
        finalized = finalize_fanout_child_run(
            run_id,
            1,
            error_code="active_run_missing",
        )
        if finalized:
            recovered = True
            log.warning(
                "ASSESSMENT_BATCH_RECOVERY_CHILD_MISSING",
                extra={
                    "batch_id": batch_id,
                    "step_id": str(child.get("step_id") or ""),
                    "ordinal": int(child.get("ordinal") or 0),
                    "attempt": int(child.get("attempt") or 1),
                    "run_id": run_id,
                },
            )
    current = storage.get_execution_by_id(
        batch_id,
        execution_kind=ASSESSMENT_BATCH_EXECUTION_KIND,
    )
    if not current or str(current.get("status") or "") not in storage.ACTIVE_EXECUTION_STATUSES:
        return "recovered" if recovered else "ignored"
    launched = launch_assessment_batch(batch_id)
    if int(launched.get("launched") or 0):
        return "recovered"
    refreshed_status = str(launched.get("status") or "")
    if refreshed_status == "failed":
        return "failed"
    return "recovered" if recovered else "left_running"


def recover_assessment_batch(batch_id: str) -> str:
    """Reconcile one durable batch without launching a child twice."""
    execution = storage.get_execution_by_id(
        str(batch_id or ""),
        execution_kind=ASSESSMENT_BATCH_EXECUTION_KIND,
    )
    if not execution or str(execution.get("status") or "") not in storage.ACTIVE_EXECUTION_STATUSES:
        return "ignored"
    try:
        snapshot = load_batch_recovery_snapshot(str(batch_id))
    except (BatchRecoverySnapshotError, ValueError) as exc:
        log.warning(
            "ASSESSMENT_BATCH_RECOVERY_FAILED",
            extra={
                "batch_id": str(batch_id),
                "reason": "recovery_snapshot_invalid",
                "error_type": type(exc).__name__,
            },
        )
        return _stop_and_reconcile(
            execution,
            "recovery_snapshot_invalid",
            "The assessment batch snapshot couldn't be recovered safely.",
        )
    if not snapshot:
        return "ignored"
    if not bool(snapshot.get("scope_available")):
        return _stop_and_reconcile(
            execution,
            "scope_unavailable",
            "The assessment batch Project or active assessment is no longer available.",
        )
    if execution_expired(execution):
        return _stop_and_reconcile(
            execution,
            "execution_timeout",
            "The assessment batch exceeded its maximum runtime.",
        )
    authorization_code, authorization_detail, _role = current_execution_role(execution)
    if authorization_code:
        return _stop_and_reconcile(
            execution,
            authorization_code,
            authorization_detail,
        )
    if str(execution.get("status") or "") == "canceling":
        return _recover_canceling(execution, snapshot.get("children"))
    return _recover_runnable(execution, snapshot.get("children"))


def recover_assessment_batches(*, limit: int = 100) -> dict[str, int]:
    """Page through every active assessment batch during runtime startup."""
    result = {**{key: 0 for key in _RESULT_KEYS}, "errors": 0}
    after_created = ""
    after_id = ""
    page_limit = max(1, min(int(limit or 100), 500))
    while True:
        page = storage.active_execution_page_for_recovery(
            limit=page_limit,
            after_created=after_created,
            after_id=after_id,
            execution_kind=ASSESSMENT_BATCH_EXECUTION_KIND,
        )
        if not page:
            break
        for batch_id, created in page:
            try:
                outcome = recover_assessment_batch(batch_id)
            except Exception:
                result["errors"] += 1
                app_metrics.record_assessment_batch_recovery_action("failed")
                log.error(
                    "ASSESSMENT_BATCH_RECOVERY_ERROR",
                    exc_info=True,
                    extra={
                        "batch_id": batch_id,
                        "stage": "recover_batch",
                        "pid": os.getpid(),
                        "recovery_owner": True,
                    },
                )
            else:
                if outcome in _RESULT_KEYS:
                    result[outcome] += 1
                    app_metrics.record_assessment_batch_recovery_action(outcome)
            after_created = created
            after_id = batch_id
        if len(page) < page_limit:
            break
    log.info(
        "ASSESSMENT_BATCH_RECOVERY_COMPLETED",
        extra={
            **result,
            "examined": sum(result.values()),
            "pid": os.getpid(),
            "recovery_owner": True,
        },
    )
    return result


__all__ = ["recover_assessment_batch", "recover_assessment_batches"]
