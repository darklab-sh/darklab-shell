# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded child scheduling through the normal command-run boundary."""

from __future__ import annotations

from collections.abc import Mapping

from services.workflows import storage
from services.workflows.compiler import WorkflowDefinitionError
from services.workflows.fanout import MAX_CHILD_RUNS, expand_collection_step
from services.workflows.fanout_checkpoint import checkpoint_from_payload
from services.workflows.fanout_child_lifecycle import claim_fanout_child
from services.workflows.fanout_child_run import launch_fanout_child
from services.workflows.fanout_children import initialize_fanout_children, list_fanout_children
from services.workflows.fanout_launch_state import finalize_empty_fanout_parent
from services.workflows.fanout_policy import MAX_RETRIES, normalize_fanout_policy


def _integer(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _parent_step(execution: Mapping[str, object], step_id: str) -> Mapping[str, object] | None:
    raw_steps = execution.get("steps")
    for step in raw_steps if isinstance(raw_steps, list) else []:
        if isinstance(step, Mapping) and str(step.get("step_id") or "") == step_id:
            return step
    return None


def _fanout_plan(
    execution: Mapping[str, object],
    step: Mapping[str, object],
) -> tuple[str, list[dict[str, object]]]:
    raw_policy = step.get("for_each")
    if not isinstance(raw_policy, Mapping):
        raise WorkflowDefinitionError("workflow fan-out policy is unavailable")
    collection_name = str(raw_policy.get("collection") or "")
    raw_variables = execution.get("variables")
    variables = raw_variables if isinstance(raw_variables, Mapping) else {}
    items = variables.get(collection_name)
    if not isinstance(items, list):
        raise WorkflowDefinitionError("workflow fan-out collection is unavailable")
    scalar_variables = {
        str(name): str(value)
        for name, value in variables.items()
        if not isinstance(value, list)
    }
    expanded = expand_collection_step(
        step,
        scalar_variables,
        collection_name,
        items,
        max_children=MAX_CHILD_RUNS,
    )
    unique_items: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        unique_items.append(value)
        if len(unique_items) >= len(expanded):
            break
    return collection_name, [
        dict(plan, item=item)
        for plan, item in zip(expanded, unique_items, strict=True)
    ]


def _pending_attempt(
    children: list[dict[str, object]],
    ordinal: int,
) -> dict[str, object] | None:
    matches = [
        child
        for child in children
        if _integer(child.get("ordinal"), 0) == ordinal
        and str(child.get("status") or "") == "pending"
    ]
    return max(matches, key=lambda child: _integer(child.get("attempt"), 1), default=None)


def launch_fanout_batch(
    execution: Mapping[str, object],
    step: Mapping[str, object],
    current_role: str,
) -> dict[str, object]:
    """Fill the parent's bounded parallel slots and return only safe launch state."""
    execution_id = str(execution.get("id") or "")
    step_id = str(step.get("id") or "")
    collection_name, plans = _fanout_plan(execution, step)
    initialize_fanout_children(execution_id, step_id, len(plans))
    if not plans:
        return {
            "execution_id": execution_id,
            "step_id": step_id,
            "status": "completed",
            "launched": [],
            "parent_transition": finalize_empty_fanout_parent(execution_id, step_id) or {},
        }
    policy = normalize_fanout_policy(step.get("for_each"))
    launched: list[dict[str, object]] = []
    parent_transition: dict[str, object] = {}
    max_attempts = MAX_CHILD_RUNS * (MAX_RETRIES + 1)
    for _iteration in range(max_attempts):
        current = storage.get_execution_by_id(execution_id)
        if not current:
            break
        parent = _parent_step(current, step_id)
        checkpoint_payload = (parent or {}).get("fanout_checkpoint")
        if not isinstance(parent, Mapping) or not isinstance(checkpoint_payload, Mapping):
            break
        if str(parent.get("status") or "") not in {"launching", "running"}:
            break
        checkpoint = checkpoint_from_payload(dict(checkpoint_payload))
        if len(checkpoint.running) >= policy.max_parallel or not checkpoint.pending:
            break
        ordinal = checkpoint.pending[0]
        children = list_fanout_children(execution_id, step_id)
        pending = _pending_attempt(children, ordinal)
        if not pending:
            raise WorkflowDefinitionError("workflow fan-out pending child is unavailable")
        claimed = claim_fanout_child(
            execution_id,
            step_id,
            ordinal,
            attempt=_integer(pending.get("attempt"), 1),
        )
        if not claimed:
            continue
        launch, outcome = launch_fanout_child(
            current,
            step,
            plans[ordinal],
            claimed,
            collection_name,
            current_role,
        )
        if launch:
            launched.append(launch)
        raw_transition = outcome.get("parent_transition")
        if isinstance(raw_transition, Mapping) and raw_transition:
            parent_transition = dict(raw_transition)
            break
    return {
        "execution_id": execution_id,
        "step_id": step_id,
        "status": "running" if not parent_transition else "completed",
        "launched": launched,
        "parent_transition": parent_transition,
    }
