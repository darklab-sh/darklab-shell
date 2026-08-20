# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable coordinator kinds sharing the workflow execution tables."""

WORKFLOW_EXECUTION_KIND = "workflow"
ASSESSMENT_BATCH_EXECUTION_KIND = "assessment_batch"
EXECUTION_KINDS = frozenset({
    WORKFLOW_EXECUTION_KIND,
    ASSESSMENT_BATCH_EXECUTION_KIND,
})


def require_execution_kind(value: object) -> str:
    normalized = str(value or "").strip()
    if normalized not in EXECUTION_KINDS:
        raise ValueError("unsupported execution kind")
    return normalized


__all__ = [
    "ASSESSMENT_BATCH_EXECUTION_KIND",
    "EXECUTION_KINDS",
    "WORKFLOW_EXECUTION_KIND",
    "require_execution_kind",
]
