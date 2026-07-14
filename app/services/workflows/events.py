# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Replayable workflow execution events derived from durable state."""

from __future__ import annotations

from collections.abc import Mapping


TERMINAL_STEP_STATUSES = frozenset({"succeeded", "failed", "canceled"})
TERMINAL_EXECUTION_STATUSES = frozenset({"completed", "failed", "canceled"})


def _event(event_type: str, timestamp: object, **payload: object) -> dict[str, object]:
    return {
        "type": event_type,
        "timestamp": str(timestamp or ""),
        **payload,
    }


def execution_events(execution: Mapping[str, object]) -> list[dict[str, object]]:
    """Build a stable, value-free event stream for one execution snapshot."""
    execution_id = str(execution.get("id") or "")
    events = [_event(
        "started",
        execution.get("created"),
        execution_id=execution_id,
        workflow_id=str(execution.get("workflow_id") or ""),
    )]
    raw_steps = execution.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    for raw_step in steps:
        if not isinstance(raw_step, Mapping):
            continue
        step_id = str(raw_step.get("step_id") or "")
        step_index = int(raw_step.get("step_index") or 0)
        run_id = str(raw_step.get("run_id") or "")
        common = {
            "execution_id": execution_id,
            "step_id": step_id,
            "step_index": step_index,
            "run_id": run_id,
        }
        step_started = raw_step.get("started")
        if step_started:
            events.append(_event("step_started", raw_step.get("started"), **common))
        status = str(raw_step.get("status") or "")
        if not step_started or status not in TERMINAL_STEP_STATUSES or not raw_step.get("finished"):
            continue
        events.append(_event(
            "step_completed",
            raw_step.get("finished"),
            **common,
            status=status,
            exit_code=raw_step.get("exit_code"),
            selected_transition=str(raw_step.get("selected_transition") or ""),
            transition_reason=str(raw_step.get("transition_reason") or ""),
        ))
        capture_names = raw_step.get("capture_names")
        names = [str(name) for name in capture_names if str(name)] if isinstance(capture_names, list) else []
        if names:
            events.append(_event(
                "capture_saved",
                raw_step.get("finished"),
                **common,
                capture_names=names,
                count=len(names),
            ))
    status = str(execution.get("status") or "")
    if status in TERMINAL_EXECUTION_STATUSES and execution.get("finished"):
        events.append(_event(
            status,
            execution.get("finished"),
            execution_id=execution_id,
            status=status,
        ))
    for cursor, item in enumerate(events, start=1):
        item["cursor"] = cursor
    return events


def replay_execution_events(
    execution: Mapping[str, object],
    *,
    after: int = 0,
    limit: int = 100,
) -> dict[str, object]:
    """Return a bounded cursor page from an execution's durable event stream."""
    bounded_after = max(0, int(after or 0))
    bounded_limit = max(1, min(int(limit or 100), 100))
    available = [
        item for item in execution_events(execution)
        if int(str(item.get("cursor") or 0)) > bounded_after
    ]
    page = available[:bounded_limit]
    next_cursor = int(str(page[-1]["cursor"])) if page else bounded_after
    return {
        "events": page,
        "next_cursor": next_cursor,
        "has_more": len(available) > len(page),
    }
