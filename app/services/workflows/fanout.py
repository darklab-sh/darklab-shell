# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded command expansion for workflow collection fan-out."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from services.workflows.compiler import WorkflowDefinitionError, render_step_command, workflow_tokens
from services.workflows.collections import MAX_CAPTURE_VALUE_BYTES

MAX_CHILD_RUNS = 32


def expand_collection_step(
    step: Mapping[str, object],
    variables: Mapping[str, str],
    collection_name: str,
    items: Iterable[object],
    *,
    max_children: int = MAX_CHILD_RUNS,
) -> list[dict[str, object]]:
    """Render one private child command per safe collection item.

    The returned commands are for the launch layer only; callers must use the
    normal policy and scope checks for every child before starting it.
    """
    name = str(collection_name or "").strip()
    if not name or name not in workflow_tokens(str(step.get("cmd") or "")):
        raise WorkflowDefinitionError("fan-out collection must be referenced by the step command")
    try:
        limit = min(max(int(max_children), 1), MAX_CHILD_RUNS)
    except (TypeError, ValueError) as exc:
        raise WorkflowDefinitionError("fan-out child limit must be an integer") from exc
    expanded: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        if len(value.encode("utf-8")) > MAX_CAPTURE_VALUE_BYTES:
            raise WorkflowDefinitionError("fan-out item exceeds the capture value limit")
        if any(ord(char) < 32 and char != "\t" for char in value):
            raise WorkflowDefinitionError("fan-out item contains control characters")
        seen.add(value)
        if len(expanded) >= limit:
            break
        child_variables = {str(key): str(val) for key, val in variables.items()}
        child_variables[name] = value
        expanded.append({"ordinal": len(expanded), "command": render_step_command(step, child_variables)})
    return expanded
