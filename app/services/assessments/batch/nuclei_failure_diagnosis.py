# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Collapse repeated Nuclei template failures into one batch diagnosis."""

from __future__ import annotations

from typing import Any


NUCLEI_TEMPLATE_FAILURE_CODE = "nuclei_template_loading_failed"
NUCLEI_TEMPLATE_RETRY_ACTION = "refresh_nuclei_templates_and_retry"

_TEMPLATE_FAILURE_MARKERS = (
    "could not load templates",
    "error loading templates",
    "failed to load template",
    "failed to parse template",
    "no templates provided for scan",
    "template validation error",
    "templates are not compatible",
    "template is not compatible",
)


def is_nuclei_template_failure(output: object) -> bool:
    """Recognize bounded, tool-specific template loading failures."""
    normalized = str(output or "").casefold()
    return any(marker in normalized for marker in _TEMPLATE_FAILURE_MARKERS)


def nuclei_template_failure_diagnostics(
    conn: Any,
    batch_id: str,
) -> list[dict[str, object]]:
    """Return at most one aggregate diagnosis for current failed attempts."""
    rows = conn.execute(
        "SELECT child.run_id, run.output_search_text FROM assessment_batch_items item "
        "JOIN workflow_execution_children child ON child.execution_id = item.batch_id "
        "AND child.step_id = item.step_id AND child.ordinal = item.child_ordinal "
        "AND child.attempt = (SELECT MAX(latest.attempt) "
        "FROM workflow_execution_children latest "
        "WHERE latest.execution_id = child.execution_id "
        "AND latest.step_id = child.step_id AND latest.ordinal = child.ordinal) "
        "JOIN runs run ON run.id = child.run_id WHERE item.batch_id = ? "
        "AND item.action_id = 'nuclei' AND child.status = 'failed' "
        "ORDER BY item.item_index",
        (batch_id,),
    ).fetchall()
    affected = sum(
        1 for row in rows if is_nuclei_template_failure(row["output_search_text"])
    )
    if not affected:
        return []
    command_label = "command" if affected == 1 else "commands"
    return [{
        "code": NUCLEI_TEMPLATE_FAILURE_CODE,
        "level": "error",
        "title": "Nuclei couldn't load the managed templates",
        "message": (
            f"{affected} Nuclei {command_label} failed while loading or validating "
            "the managed template snapshot. Update the templates, rebuild the retry "
            "preview, and review it before starting a new batch."
        ),
        "affected_command_count": affected,
        "recommended_action": NUCLEI_TEMPLATE_RETRY_ACTION,
    }]


__all__ = [
    "NUCLEI_TEMPLATE_FAILURE_CODE",
    "NUCLEI_TEMPLATE_RETRY_ACTION",
    "is_nuclei_template_failure",
    "nuclei_template_failure_diagnostics",
]
