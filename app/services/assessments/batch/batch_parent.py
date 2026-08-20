# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Owner-scoped assessment-batch parent state and progress."""

from __future__ import annotations

from dataclasses import asdict

from core.database_access import get_db_connect
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.nuclei_failure_diagnosis import (
    nuclei_template_failure_diagnostics,
)
from services.assessments.batch.rollup import derive_batch_progress
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


def get_batch_parent(
    session_id: str,
    batch_id: str,
    *,
    team_id: str = "",
) -> dict[str, object] | None:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    with get_db_connect()() as conn:
        parent = conn.execute(
            "SELECT b.*, e.status, e.project_id, e.created AS execution_created, e.updated, "
            "e.finished, e.failure_code FROM assessment_batches b "
            "JOIN workflow_executions e ON e.id = b.execution_id "
            "WHERE e.execution_kind = ? AND " + owner_sql + " AND b.execution_id = ?",  # nosec
            (ASSESSMENT_BATCH_EXECUTION_KIND, *owner_params, batch_id),
        ).fetchone()
        if not parent:
            return None
        chunks = conn.execute(
            "SELECT step_id, step_index, status, fanout_checkpoint, started, finished "
            "FROM workflow_execution_steps WHERE execution_id = ? ORDER BY step_index ASC",
            (batch_id,),
        ).fetchall()
        children = conn.execute(
            "SELECT c.step_id, c.ordinal, c.attempt, c.run_id, c.status, c.exit_code, "
            "c.error_code, c.created, c.started, c.finished FROM workflow_execution_children c "
            "WHERE c.execution_id = ? AND c.attempt = ("
            "SELECT MAX(latest.attempt) FROM workflow_execution_children latest "
            "WHERE latest.execution_id = c.execution_id AND latest.step_id = c.step_id "
            "AND latest.ordinal = c.ordinal) ORDER BY c.step_id ASC, c.ordinal ASC",
            (batch_id,),
        ).fetchall()
        diagnostics = nuclei_template_failure_diagnostics(conn, batch_id)
    child_rows = [{str(key): row[key] for key in row.keys()} for row in children]
    progress = derive_batch_progress(
        child_rows,
        cancellation_requested=str(parent["status"] or "") in {"canceling", "canceled"},
    )
    if progress.total != int(parent["item_count"]):
        raise AssessmentBatchError(
            "batch_state_mismatch",
            "Assessment batch child state doesn't match its confirmed item count.",
            status_code=409,
        )
    public_progress = asdict(progress)
    public_progress["settled"] = progress.settled
    return {
        "schema_version": 1,
        "batch_id": str(parent["execution_id"]),
        "assessment_id": str(parent["assessment_id"]),
        "project_id": str(parent["project_id"]),
        "preview_id": str(parent["preview_id"]),
        "preview_digest": str(parent["preview_digest"]),
        "source_batch_id": str(parent["source_execution_id"] or ""),
        "status": "failed" if str(parent["status"] or "") == "failed" else progress.status,
        "item_count": int(parent["item_count"]),
        "chunk_count": len(chunks),
        "concurrency": {
            "batch": int(parent["max_parallel"]),
            "target": int(parent["max_target_parallel"]),
            "owner": int(parent["max_owner_parallel"]),
            "instance": int(parent["max_instance_parallel"]),
        },
        "progress": public_progress,
        "diagnostics": diagnostics,
        "next_event_sequence": int(parent["next_event_sequence"]),
        "created": str(parent["execution_created"] or ""),
        "updated": str(parent["updated"] or ""),
        "finished": str(parent["finished"] or ""),
        "failure_code": str(parent["failure_code"] or ""),
    }


__all__ = ["get_batch_parent"]
