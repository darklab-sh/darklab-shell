# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded heterogeneous launch and run-finalization coordination."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from services.assessments.batch.claim import claim_next_batch_item
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_MAX_ATTEMPTS,
)
from services.assessments.batch.events import append_batch_event
from services.assessments.batch.revalidation import build_batch_child_launch_spec
from services.assessments.batch.recovery_stop import (
    stop_assessment_batch_for_recovery,
)
from services.assessments.batch.settings import assessment_batch_settings
from services.workflows import storage
from services.workflows.execution_authorization import (
    current_execution_role,
    execution_expired,
)
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_child_run import launch_fanout_child
from services.workflows.fanout_launch_state import fail_launching_fanout_child


log = logging.getLogger("shell")


def _execution(batch_id: str) -> dict[str, object] | None:
    return storage.get_execution_by_id(
        batch_id,
        execution_kind=ASSESSMENT_BATCH_EXECUTION_KIND,
    )


def _stop_execution(
    execution: Mapping[str, object],
    code: str,
    detail: str,
) -> None:
    stop_assessment_batch_for_recovery(
        str(execution.get("id") or ""),
        code,
        detail,
    )


def _authorized_role(execution: Mapping[str, object]) -> tuple[bool, str]:
    if execution_expired(execution, max_runtime_seconds=assessment_batch_settings().max_runtime_seconds):
        _stop_execution(
            execution,
            "execution_timeout",
            "The assessment batch exceeded its maximum runtime.",
        )
        return False, ""
    code, detail, role = current_execution_role(execution)
    if code:
        _stop_execution(execution, code, detail)
        return False, ""
    return True, role


def _record_launch(claim: Mapping[str, object]) -> None:
    child = claim.get("child")
    append_batch_event(
        str(claim.get("batch_id") or ""),
        "item_launched",
        chunk_index=int(claim.get("chunk_index") or 0),
        item_ordinal=int(claim.get("item_index") or 0),
        status="launching",
        details={
            "attempt": int(child.get("attempt") or 1)
            if isinstance(child, Mapping)
            else 1
        },
    )


def launch_assessment_batch(batch_id: str) -> dict[str, object]:
    """Fill currently fair launch slots without exposing persisted item values."""
    execution = _execution(str(batch_id or ""))
    if not execution:
        return {"status": "not_found", "batch_id": str(batch_id or ""), "launched": 0}
    status = str(execution.get("status") or "")
    if status not in {"queued", "running"}:
        return {"status": status, "batch_id": str(batch_id), "launched": 0}
    allowed, current_role = _authorized_role(execution)
    if not allowed:
        return {"status": "failed", "batch_id": str(batch_id), "launched": 0}

    launched = 0
    reason_code = ""
    for _ in range(BATCH_HARD_ITEM_LIMIT * BATCH_MAX_ATTEMPTS):
        claim = claim_next_batch_item(str(batch_id))
        claim_status = str(claim.get("status") or "")
        if claim_status != "claimed":
            reason_code = str(claim.get("reason_code") or "")
            break
        child = claim.get("child")
        item = claim.get("item")
        if not isinstance(child, Mapping) or not isinstance(item, Mapping):
            raise AssessmentBatchError(
                "batch_state_mismatch",
                "The claimed assessment item is incomplete.",
                status_code=409,
            )
        child_id = str(child.get("id") or "")
        try:
            launch_spec = build_batch_child_launch_spec(execution, item)
        except AssessmentBatchError as exc:
            settled = fail_launching_fanout_child(child_id, exc.code)
            reason_code = exc.code
            if not settled or bool(
                (settled.get("parent_transition") or {}).get("terminal")
            ):
                break
            continue
        except Exception as exc:
            settled = fail_launching_fanout_child(child_id, "launch_failed")
            reason_code = "launch_failed"
            log.error(
                "ASSESSMENT_BATCH_ITEM_MATERIALIZE_ERROR",
                exc_info=True,
                extra={
                    "batch_id": str(batch_id),
                    "item_index": int(claim.get("item_index") or 0),
                    "error_type": type(exc).__name__,
                },
            )
            if not settled or bool(
                (settled.get("parent_transition") or {}).get("terminal")
            ):
                break
            continue
        _record_launch(claim)
        started, _state = launch_fanout_child(
            execution,
            str(claim.get("step_id") or ""),
            child,
            current_role,
            launch_spec,
        )
        if started:
            launched += 1
    else:
        raise AssessmentBatchError(
            "batch_launch_limit",
            "Assessment batch launch attempts exceeded the fixed safety limit.",
            status_code=409,
        )
    refreshed = _execution(str(batch_id)) or {}
    return {
        "status": str(refreshed.get("status") or "not_found"),
        "batch_id": str(batch_id),
        "launched": launched,
        "reason_code": reason_code,
    }


__all__ = ["launch_assessment_batch"]
