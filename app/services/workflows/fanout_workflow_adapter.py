# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Render homogeneous workflow fan-out children into generic launch specs."""

from __future__ import annotations

from collections.abc import Mapping

from services.workflows.child_launch_spec import ChildLaunchSpec
from services.workflows.compiler import (
    WorkflowDefinitionError,
    render_step_display_command,
    workflow_private_values,
)


def _child_variables(
    execution: Mapping[str, object],
    collection_name: str,
    item: object,
) -> dict[str, str]:
    raw_variables = execution.get("variables")
    variables = raw_variables if isinstance(raw_variables, Mapping) else {}
    result = {
        str(name): str(value)
        for name, value in variables.items()
        if not isinstance(value, list)
    }
    result[collection_name] = str(item)
    return result


def workflow_fanout_launch_spec(
    execution: Mapping[str, object],
    step: Mapping[str, object],
    plan: Mapping[str, object],
    collection_name: str,
) -> ChildLaunchSpec:
    """Render one workflow-only template and private collection substitution."""
    item = plan.get("item")
    if item is None:
        raise WorkflowDefinitionError("workflow fan-out child value is unavailable")
    raw_variables = execution.get("variables")
    raw_definition = execution.get("definition_snapshot")
    variables = raw_variables if isinstance(raw_variables, Mapping) else {}
    definition = raw_definition if isinstance(raw_definition, Mapping) else {}
    child_variables = _child_variables(execution, collection_name, item)
    return ChildLaunchSpec(
        execution_command=str(plan.get("command") or ""),
        display_command=render_step_display_command(step, definition, child_variables),
        private_values=workflow_private_values(definition, variables),
    )


__all__ = ["workflow_fanout_launch_spec"]
