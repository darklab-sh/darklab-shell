# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Lossless heterogeneous assessment-item claim through shared fan-out state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, cast

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.assessments.batch.claim_fairness import (
    global_fairness_reason,
    lock_batch_claim_gate,
    target_is_active,
)
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.events import append_batch_event_on_conn
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_checkpoint import checkpoint_from_payload
from services.workflows.fanout_child_claim import claim_fanout_child_on_conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _dialect():
    return dialect_for_backend(get_db_backend())


def _lock_suffix() -> str:
    return " FOR UPDATE" if get_db_backend() == DatabaseBackend.POSTGRES else ""


def _batch_context(conn: Any, batch_id: str) -> dict[str, object]:
    row = conn.execute(
        "SELECT e.id AS execution_id, e.session_id, e.team_id, e.status AS execution_status, "
        "e.current_step_id, b.max_parallel, b.max_target_parallel, "
        "b.max_owner_parallel, b.max_instance_parallel, s.step_index, "
        "s.status AS step_status, s.fanout_checkpoint "
        "FROM workflow_executions e "
        "JOIN assessment_batches b ON b.execution_id = e.id "
        "JOIN workflow_execution_steps s ON s.execution_id = e.id "
        "AND s.step_id = e.current_step_id "
        "WHERE e.id = ? AND e.execution_kind = ?" + _lock_suffix(),  # nosec
        (batch_id, ASSESSMENT_BATCH_EXECUTION_KIND),
    ).fetchone()
    if not row:
        raise AssessmentBatchError(
            "batch_not_found", "Assessment batch wasn't found.", status_code=404
        )
    return {str(key): row[key] for key in row.keys()}


def _candidate(
    conn: Any,
    batch_id: str,
    step_id: str,
    ordinal: int,
) -> dict[str, object]:
    row = conn.execute(
        "SELECT c.id AS child_id, c.ordinal, c.attempt, c.status AS child_status, "
        "item.item_index, item.target_entity_id, item.target_type, item.target_value, "
        "item.action_key, item.action_id, item.policy_level, item.profile_identity_json, "
        "item.bounds_json, item.display_command, item.public_plan_digest, "
        "item.public_plan_json, item.duration_bound_seconds "
        "FROM workflow_execution_children c "
        "JOIN assessment_batch_items item ON item.batch_id = c.execution_id "
        "AND item.step_id = c.step_id AND item.child_ordinal = c.ordinal "
        "WHERE c.execution_id = ? AND c.step_id = ? AND c.ordinal = ? "
        "AND c.status = 'pending' ORDER BY c.attempt DESC LIMIT 1",
        (batch_id, step_id, ordinal),
    ).fetchone()
    if not row:
        raise AssessmentBatchError(
            "batch_state_mismatch",
            "Assessment batch pending child doesn't have one immutable item.",
            status_code=409,
        )
    return {str(key): row[key] for key in row.keys()}


def _activate_chunk(
    conn: Any,
    context: Mapping[str, object],
    *,
    created: str,
) -> None:
    batch_id = str(context.get("execution_id") or "")
    step_id = str(context.get("current_step_id") or "")
    if str(context.get("step_status") or "") != "pending":
        return
    changed = conn.execute(
        "UPDATE workflow_execution_steps SET status = 'launching', started = ? "
        "WHERE execution_id = ? AND step_id = ? AND status = 'pending'",
        (created, batch_id, step_id),
    )
    if changed.rowcount != 1:
        raise AssessmentBatchError(
            "batch_claim_conflict", "Assessment batch chunk claim changed.", status_code=409
        )
    if str(context.get("execution_status") or "") == "queued":
        conn.execute(
            "UPDATE workflow_executions SET status = 'running', updated = ? "
            "WHERE id = ? AND status = 'queued'",
            (created, batch_id),
        )
        append_batch_event_on_conn(
            conn, batch_id, "parent_status_changed", status="running", created=created
        )
    append_batch_event_on_conn(
        conn,
        batch_id,
        "chunk_status_changed",
        chunk_index=int(cast(Any, context.get("step_index") or 0)),
        status="launching",
        created=created,
    )


def _public_claim(
    context: Mapping[str, object],
    candidate: Mapping[str, object],
    child: Mapping[str, object],
) -> dict[str, object]:
    return {
        "status": "claimed",
        "reason_code": "",
        "batch_id": str(context.get("execution_id") or ""),
        "step_id": str(context.get("current_step_id") or ""),
        "chunk_index": int(cast(Any, context.get("step_index") or 0)),
        "item_index": int(cast(Any, candidate.get("item_index") or 0)),
        "child": dict(child),
        "item": {
            "action_key": str(candidate.get("action_key") or ""),
            "action_id": str(candidate.get("action_id") or ""),
            "policy_level": str(candidate.get("policy_level") or ""),
            "target": {
                "entity_id": str(candidate.get("target_entity_id") or ""),
                "type": str(candidate.get("target_type") or ""),
                "value": str(candidate.get("target_value") or ""),
            },
            "profile_identity": _dialect().decode_json_dict(
                candidate.get("profile_identity_json")
            ),
            "bounds": _dialect().decode_json_dict(candidate.get("bounds_json")),
            "display_command": str(candidate.get("display_command") or ""),
            "public_plan_digest": str(candidate.get("public_plan_digest") or ""),
            "public_plan": _dialect().decode_json_dict(
                candidate.get("public_plan_json")
            ),
            "duration_bound_seconds": int(
                cast(Any, candidate.get("duration_bound_seconds") or 0)
            ),
        },
    }


def claim_next_batch_item(batch_id: str) -> dict[str, object]:
    """Claim the first currently fair item without skipping stable item order."""
    created = _now()
    with get_db_connect()() as conn:
        conn.execute(_dialect().begin_immediate_sql())
        lock_batch_claim_gate(conn)
        context = _batch_context(conn, str(batch_id or ""))
        if str(context["execution_status"] or "") not in {"queued", "running"}:
            conn.rollback()
            return {"status": "idle", "reason_code": "batch_not_runnable"}
        if str(context["step_status"] or "") not in {"pending", "launching", "running"}:
            conn.rollback()
            return {"status": "idle", "reason_code": "chunk_not_runnable"}
        checkpoint = checkpoint_from_payload(
            _dialect().decode_json_dict(context["fanout_checkpoint"])
        )
        if not checkpoint.pending:
            conn.rollback()
            return {"status": "idle", "reason_code": "no_pending_items"}
        reason = global_fairness_reason(conn, context)
        if reason:
            conn.rollback()
            return {"status": "deferred", "reason_code": reason}
        step_id = str(context["current_step_id"] or "")
        blocked_by_target = False
        for ordinal in checkpoint.pending:
            candidate = _candidate(conn, str(batch_id), step_id, ordinal)
            if target_is_active(
                conn, context, str(candidate.get("target_entity_id") or "")
            ):
                blocked_by_target = True
                continue
            _activate_chunk(conn, context, created=created)
            child = claim_fanout_child_on_conn(
                conn,
                str(batch_id),
                step_id,
                ordinal,
                attempt=int(cast(Any, candidate.get("attempt") or 1)),
                execution_kind=ASSESSMENT_BATCH_EXECUTION_KIND,
                started=created,
            )
            if not child:
                raise AssessmentBatchError(
                    "batch_claim_conflict",
                    "Assessment batch child claim changed.",
                    status_code=409,
                )
            append_batch_event_on_conn(
                conn,
                str(batch_id),
                "item_claimed",
                chunk_index=int(cast(Any, context.get("step_index") or 0)),
                item_ordinal=int(cast(Any, candidate.get("item_index") or 0)),
                status="launching",
                details={"attempt": int(cast(Any, candidate.get("attempt") or 1))},
                created=created,
            )
            conn.commit()
            return _public_claim(context, candidate, child)
        conn.rollback()
    return {
        "status": "deferred" if blocked_by_target else "idle",
        "reason_code": "target_parallel_limit" if blocked_by_target else "no_pending_items",
    }


__all__ = ["claim_next_batch_item"]
