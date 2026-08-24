# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Final settlement for active children after batch cancellation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.assessments.batch.cancellation_state import (
    terminalize_batch_cancellation_on_conn,
)
from services.assessments.batch.cancellation_events import (
    record_batch_child_canceled_on_conn,
)
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_COULD_NOT_CANCEL_ERROR_CODE,
)
from services.assessments.batch.events import append_batch_event_on_conn
from services.assessments.batch.lifecycle_events import (
    record_batch_child_settled_on_conn,
)
from services.assessments.batch.notifications import enqueue_terminal_batch_summary
from services.assessments.batch.terminal_observability import record_terminal_batch_milestone
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_checkpoint import checkpoint_from_payload


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _lock_suffix() -> str:
    return " FOR UPDATE" if get_db_backend() == DatabaseBackend.POSTGRES else ""


def _settled_status(row: Any, exit_code: int) -> tuple[str, str]:
    if str(row["error_code"] or "") == BATCH_COULD_NOT_CANCEL_ERROR_CODE:
        return "failed", BATCH_COULD_NOT_CANCEL_ERROR_CODE
    if int(exit_code) == 0:
        return "succeeded", ""
    return "canceled", "cancelled"


def finalize_canceling_batch_run(
    run_id: str,
    exit_code: int,
) -> dict[str, object] | None:
    """Settle one bound run without retrying after cancellation intent."""
    dialect = dialect_for_backend(get_db_backend())
    finished = _now()
    with get_db_connect()() as conn:
        conn.execute(dialect.begin_immediate_sql())
        row = conn.execute(
            "SELECT c.*, s.step_index, s.fanout_checkpoint, "
            "e.status AS execution_status, e.failure_code AS parent_failure_code "
            "FROM workflow_execution_children c "
            "JOIN workflow_execution_steps s ON s.execution_id = c.execution_id "
            "AND s.step_id = c.step_id "
            "JOIN workflow_executions e ON e.id = c.execution_id "
            "WHERE c.run_id = ? AND e.execution_kind = ?" + _lock_suffix(),  # nosec
            (run_id, ASSESSMENT_BATCH_EXECUTION_KIND),
        ).fetchone()
        if (
            not row
            or str(row["execution_status"] or "") != "canceling"
            or str(row["status"] or "") != "running"
        ):
            conn.rollback()
            return None
        checkpoint = checkpoint_from_payload(
            dialect.decode_json_dict(row["fanout_checkpoint"])
        )
        ordinal = int(row["ordinal"])
        if ordinal not in checkpoint.running:
            raise AssessmentBatchError(
                "batch_state_mismatch",
                "Assessment batch cancellation checkpoint is invalid.",
                status_code=409,
            )
        status, error_code = _settled_status(row, int(exit_code))
        changed = conn.execute(
            "UPDATE workflow_execution_children SET status = ?, exit_code = ?, "
            "error_code = ?, finished = ? WHERE id = ? AND status = 'running'",
            (status, int(exit_code), error_code, finished, str(row["id"])),
        )
        if changed.rowcount != 1:
            conn.rollback()
            return None
        if status == "succeeded":
            next_checkpoint = checkpoint.mark_completed([ordinal])
        elif status == "failed":
            next_checkpoint = checkpoint.mark_failed([ordinal])
        else:
            next_checkpoint = checkpoint.mark_skipped([ordinal])
        conn.execute(
            "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
            "WHERE execution_id = ? AND step_id = ?",
            (
                dialect.json_param(next_checkpoint.to_payload()),
                str(row["execution_id"]),
                str(row["step_id"]),
            ),
        )
        if status == "canceled":
            record_batch_child_canceled_on_conn(conn, row)
        else:
            record_batch_child_settled_on_conn(
                conn,
                row,
                status=status,
                error_code=error_code,
            )
        if not next_checkpoint.pending and not next_checkpoint.running:
            parent_failure = str(row["parent_failure_code"] or "")
            chunk_status = "failed" if parent_failure else "canceled"
            chunk_reason = parent_failure or "cancelled"
            conn.execute(
                "UPDATE workflow_execution_steps SET status = ?, error_code = ?, finished = ? "
                "WHERE execution_id = ? AND step_id = ? "
                "AND status IN ('launching', 'running')",
                (
                    chunk_status,
                    chunk_reason,
                    finished,
                    str(row["execution_id"]),
                    str(row["step_id"]),
                ),
            )
            append_batch_event_on_conn(
                conn,
                str(row["execution_id"]),
                "chunk_status_changed",
                chunk_index=int(row["step_index"]),
                status=chunk_status,
                reason_code=chunk_reason,
                created=finished,
            )
        terminalized = terminalize_batch_cancellation_on_conn(
            conn,
            str(row["execution_id"]),
            finished=finished,
        )
        conn.commit()
    if terminalized:
        record_terminal_batch_milestone(str(row["execution_id"]), changed=True)
        enqueue_terminal_batch_summary(str(row["execution_id"]))
    return {
        "execution_id": str(row["execution_id"]),
        "step_id": str(row["step_id"]),
        "ordinal": ordinal,
        "status": status,
        "error_code": error_code,
    }


__all__ = ["finalize_canceling_batch_run"]
