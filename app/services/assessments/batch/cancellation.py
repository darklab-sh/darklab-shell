# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Truthful cancellation for one durable assessment batch."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from core.helpers import get_log_session_id
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_COULD_NOT_CANCEL_ERROR_CODE,
    BATCH_TERMINAL_STATUSES,
)
from services.assessments.batch.cancellation_state import (
    terminalize_batch_cancellation_on_conn,
)
from services.assessments.batch.cancellation_events import (
    record_batch_child_canceled_on_conn,
)
from services.assessments.batch.events import append_batch_event_on_conn
from services.assessments.batch.storage_read import get_batch_parent
from services.assessments.batch.claim_fairness import lock_batch_claim_gate
from services.projects.scope import shared_owner_where
from services.runs.cancellation import request_active_run_cancellation
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_checkpoint import checkpoint_from_payload


log = logging.getLogger("shell")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _dialect():
    return dialect_for_backend(get_db_backend())


def _lock_suffix() -> str:
    return " FOR UPDATE" if get_db_backend() == DatabaseBackend.POSTGRES else ""


def _unfinished_rows(conn: Any, batch_id: str) -> list[Any]:
    return conn.execute(
        "SELECT c.*, s.step_index, s.status AS step_status, s.fanout_checkpoint "
        "FROM workflow_execution_children c "
        "JOIN workflow_execution_steps s ON s.execution_id = c.execution_id "
        "AND s.step_id = c.step_id WHERE c.execution_id = ? "
        "AND c.status IN ('pending', 'launching', 'running') "
        "ORDER BY s.step_index, c.ordinal, c.attempt" + _lock_suffix(),  # nosec B608
        (batch_id,),
    ).fetchall()


def _cancel_unstarted_on_conn(
    conn: Any,
    batch_id: str,
    rows: list[Any],
    *,
    finished: str,
) -> tuple[str, ...]:
    by_step: dict[str, list[Any]] = defaultdict(list)
    run_ids: set[str] = set()
    for row in rows:
        status = str(row["status"] or "")
        run_id = str(row["run_id"] or "")
        if (status == "running") != bool(run_id):
            raise AssessmentBatchError(
                "batch_state_mismatch",
                "Assessment batch cancellation found an invalid child state.",
                status_code=409,
            )
        by_step[str(row["step_id"])].append(row)
        if run_id:
            run_ids.add(run_id)

    for step_id, step_rows in by_step.items():
        checkpoint = checkpoint_from_payload(
            _dialect().decode_json_dict(step_rows[0]["fanout_checkpoint"])
        )
        canceled_ordinals = [
            int(row["ordinal"]) for row in step_rows if not str(row["run_id"] or "")
        ]
        next_checkpoint = checkpoint.mark_skipped(canceled_ordinals).cancel()
        conn.execute(
            "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
            "WHERE execution_id = ? AND step_id = ?",
            (_dialect().json_param(next_checkpoint.to_payload()), batch_id, step_id),
        )
        for row in step_rows:
            if str(row["run_id"] or ""):
                continue
            changed = conn.execute(
                "UPDATE workflow_execution_children SET status = 'canceled', "
                "error_code = 'cancelled', finished = ? WHERE id = ? "
                "AND status IN ('pending', 'launching') AND run_id = ''",
                (finished, str(row["id"])),
            )
            if changed.rowcount != 1:
                raise AssessmentBatchError(
                    "batch_state_mismatch",
                    "Assessment batch cancellation changed during settlement.",
                    status_code=409,
                )
            record_batch_child_canceled_on_conn(conn, row)
        if not next_checkpoint.running:
            changed = conn.execute(
                "UPDATE workflow_execution_steps SET status = 'canceled', finished = ? "
                "WHERE execution_id = ? AND step_id = ? "
                "AND status IN ('pending', 'launching', 'running')",
                (finished, batch_id, step_id),
            )
            if changed.rowcount:
                append_batch_event_on_conn(
                    conn,
                    batch_id,
                    "chunk_status_changed",
                    chunk_index=int(step_rows[0]["step_index"]),
                    status="canceled",
                    reason_code="cancelled",
                    created=finished,
                )
    return tuple(sorted(run_ids))


def request_batch_cancellation_on_conn(
    conn: Any,
    session_id: str,
    batch_id: str,
    *,
    team_id: str = "",
) -> tuple[str, ...] | None:
    """Record cancellation intent and return bound runs that still need a signal."""
    lock_batch_claim_gate(conn)
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    row = conn.execute(
        "SELECT e.status FROM workflow_executions e "
        "JOIN assessment_batches b ON b.execution_id = e.id "
        "WHERE e.execution_kind = ? AND " + owner_sql + " AND e.id = ?" + _lock_suffix(),  # nosec B608
        (ASSESSMENT_BATCH_EXECUTION_KIND, *owner_params, batch_id),
    ).fetchone()
    if not row:
        return None
    status = str(row["status"] or "")
    if status in BATCH_TERMINAL_STATUSES:
        return ()
    if status not in {"queued", "running", "canceling"}:
        raise AssessmentBatchError(
            "batch_state_mismatch",
            "Assessment batch isn't in a cancellable state.",
            status_code=409,
        )
    finished = _now()
    if status != "canceling":
        changed = conn.execute(
            "UPDATE workflow_executions SET status = 'canceling', updated = ? "
            "WHERE id = ? AND status IN ('queued', 'running')",
            (finished, batch_id),
        )
        if changed.rowcount != 1:
            raise AssessmentBatchError(
                "batch_cancel_conflict",
                "Assessment batch cancellation changed concurrently.",
                status_code=409,
            )
        append_batch_event_on_conn(
            conn,
            batch_id,
            "parent_status_changed",
            status="canceling",
            reason_code="cancelled",
            created=finished,
        )
    run_ids = _cancel_unstarted_on_conn(
        conn,
        batch_id,
        _unfinished_rows(conn, batch_id),
        finished=finished,
    )
    terminalize_batch_cancellation_on_conn(conn, batch_id, finished=finished)
    return run_ids


def record_cancel_signal_failure(batch_id: str, run_id: str) -> bool:
    """Mark one still-running child without implying its process stopped."""
    with get_db_connect()() as conn:
        conn.execute(_dialect().begin_immediate_sql())
        changed = conn.execute(
            "UPDATE workflow_execution_children SET error_code = ? "
            "WHERE execution_id = ? AND run_id = ? AND status = 'running' "
            "AND EXISTS (SELECT 1 FROM workflow_executions e WHERE e.id = ? "
            "AND e.status = 'canceling' AND e.execution_kind = ?)",
            (
                BATCH_COULD_NOT_CANCEL_ERROR_CODE,
                batch_id,
                run_id,
                batch_id,
                ASSESSMENT_BATCH_EXECUTION_KIND,
            ),
        )
        conn.commit()
    return changed.rowcount == 1


def cancel_assessment_batch(
    session_id: str,
    batch_id: str,
    *,
    team_id: str = "",
    cancel_run_fn: Callable[..., bool] = request_active_run_cancellation,
) -> dict[str, object] | None:
    """Request cancellation, signal active children, and return current progress."""
    with get_db_connect()() as conn:
        conn.execute(_dialect().begin_immediate_sql())
        run_ids = request_batch_cancellation_on_conn(
            conn, session_id, batch_id, team_id=team_id
        )
        if run_ids is None:
            conn.rollback()
            return None
        conn.commit()
    signal_failures = 0
    for run_id in run_ids:
        try:
            cancel_run_fn(run_id, session_id, team_id=team_id)
        except Exception as exc:
            signal_failures += 1
            record_cancel_signal_failure(batch_id, run_id)
            log.warning(
                "ASSESSMENT_BATCH_CANCEL_SIGNAL_FAILED",
                extra={
                    "batch_id": batch_id,
                    "run_id": run_id,
                    "error_type": type(exc).__name__,
                    "session": get_log_session_id(session_id),
                    "team_id": str(team_id or ""),
                },
            )
    batch = get_batch_parent(session_id, batch_id, team_id=team_id)
    return {
        "batch": batch or {},
        "signal_failures": signal_failures,
    }


__all__ = [
    "cancel_assessment_batch",
    "record_cancel_signal_failure",
    "request_batch_cancellation_on_conn",
]
