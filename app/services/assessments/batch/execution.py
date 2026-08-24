# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded heterogeneous launch and run-finalization coordination."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping

from services.assessments.batch.claim import claim_next_batch_item
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_MAX_ATTEMPTS,
)
from services.assessments.batch.events import append_batch_event
from services.assessments.batch.notifications import enqueue_terminal_batch_summary
from services.assessments.batch.revalidation import build_batch_child_launch_spec
from services.assessments.batch.recovery_stop import (
    stop_assessment_batch_for_recovery,
)
from services.assessments.batch.settings import assessment_batch_settings
from services.metrics_lazy import app_metrics
from services.workflows import storage
from services.workflows.execution_authorization import (
    current_execution_role,
    execution_expired,
)
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_child_run import launch_fanout_child
from services.workflows.fanout_launch_state import fail_launching_fanout_child


log = logging.getLogger("shell")


def _integer(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _parent_is_terminal(result: Mapping[str, object] | None) -> bool:
    transition = result.get("parent_transition") if result else None
    return isinstance(transition, Mapping) and bool(transition.get("terminal"))


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
        chunk_index=_integer(claim.get("chunk_index")),
        item_ordinal=_integer(claim.get("item_index")),
        status="launching",
        details={
            "attempt": _integer(child.get("attempt"), 1)
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
            if claim_status == "deferred":
                app_metrics.record_assessment_batch_deferral(reason_code)
                log.debug(
                    "ASSESSMENT_BATCH_LAUNCH_DEFERRED",
                    extra={
                        "batch_id": str(batch_id),
                        "reason_code": reason_code,
                        "launched_count": launched,
                    },
                )
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
        launch_started = time.perf_counter()
        try:
            launch_spec = build_batch_child_launch_spec(execution, item)
        except AssessmentBatchError as exc:
            app_metrics.record_assessment_batch_rejection(exc.code)
            app_metrics.record_assessment_batch_launch(
                "rejected", time.perf_counter() - launch_started
            )
            settled = fail_launching_fanout_child(child_id, exc.code)
            reason_code = exc.code
            if not settled or _parent_is_terminal(settled):
                break
            continue
        except Exception as exc:
            app_metrics.record_assessment_batch_launch(
                "failed", time.perf_counter() - launch_started
            )
            settled = fail_launching_fanout_child(child_id, "launch_failed")
            reason_code = "launch_failed"
            log.error(
                "ASSESSMENT_BATCH_ITEM_MATERIALIZE_ERROR",
                exc_info=True,
                extra={
                    "batch_id": str(batch_id),
                    "item_index": _integer(claim.get("item_index")),
                    "error_type": type(exc).__name__,
                },
            )
            if not settled or _parent_is_terminal(settled):
                break
            continue
        _record_launch(claim)
        try:
            started, _state = launch_fanout_child(
                execution,
                str(claim.get("step_id") or ""),
                child,
                current_role,
                launch_spec,
            )
        except Exception:
            app_metrics.record_assessment_batch_launch(
                "failed", time.perf_counter() - launch_started
            )
            raise
        app_metrics.record_assessment_batch_launch(
            "launched" if started else "failed",
            time.perf_counter() - launch_started,
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
    refreshed_status = str(refreshed.get("status") or "not_found")
    if refreshed_status in {"completed", "failed", "canceled"}:
        enqueue_terminal_batch_summary(str(batch_id))
    return {
        "status": refreshed_status,
        "batch_id": str(batch_id),
        "launched": launched,
        "reason_code": reason_code,
    }


__all__ = ["launch_assessment_batch"]
