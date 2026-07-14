"""Bounded lifecycle logging for run comparisons."""

from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("shell")

_MAX_DERIVED_GROUPS = 16
_MAX_DERIVED_GROUP_ID_LEN = 40


def _truncation_active(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_truncation_active(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_truncation_active(item) for item in value)
    return bool(value)


def _output_source(output: dict[str, Any]) -> str:
    value = str(output.get("source") or "unknown").lower()
    return value if value in {"full", "preview", "unknown"} else "unknown"


def log_run_comparison_viewed(
    *,
    owner_scope: Any,
    project_id: str,
    left_run_id: str,
    right_run_id: str,
    left_output: dict[str, Any],
    right_output: dict[str, Any],
    finding_objects: dict[str, Any],
    derived_changes: dict[str, Any],
    truncated: dict[str, Any],
    started_at: float,
) -> None:
    output_truncated = bool(left_output.get("partial") or right_output.get("partial"))
    changed_lines_truncated = bool(truncated.get("changed_lines"))
    findings_truncated = _truncation_active(truncated.get("findings"))
    artifacts_truncated = _truncation_active(truncated.get("artifacts"))
    derived_truncated = bool(derived_changes.get("truncated"))
    group_ids = [
        str(group.get("id") or "")[:_MAX_DERIVED_GROUP_ID_LEN]
        for group in derived_changes.get("groups", [])[:_MAX_DERIVED_GROUPS]
        if isinstance(group, dict) and str(group.get("id") or "").strip()
    ]
    log.info("RUN_COMPARISON_VIEWED", extra={
        "owner_scope": "team" if str(getattr(owner_scope, "team_id", "") or "") else "personal",
        "project_scoped": bool(project_id),
        "left_run_id": str(left_run_id)[:160],
        "right_run_id": str(right_run_id)[:160],
        "duration_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
        "left_output_source": _output_source(left_output),
        "right_output_source": _output_source(right_output),
        "findings_added": len(finding_objects.get("added", [])),
        "findings_removed": len(finding_objects.get("removed", [])),
        "findings_changed": len(finding_objects.get("changed", [])),
        "derived_group_ids": ",".join(group_ids),
        "output_truncated": output_truncated,
        "changed_lines_truncated": changed_lines_truncated,
        "findings_truncated": findings_truncated,
        "artifacts_truncated": artifacts_truncated,
        "derived_truncated": derived_truncated,
        "comparison_partial": any((
            output_truncated,
            changed_lines_truncated,
            findings_truncated,
            artifacts_truncated,
            derived_truncated,
        )),
    })
