# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Independent evidence retention after one shared retest run completes."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from core.helpers import get_log_session_id
from services.projects.contracts import ProjectWorkspaceError
from services.projects.finding_verification import link_completed_verification_run


log = logging.getLogger("shell")


def retest_batch_run_finalized_hook(
    session_id: str,
    plan: Mapping[str, Any],
    *,
    team_id: str = "",
) -> Callable[[str, dict[str, Any]], None]:
    """Link one completed shared run to each finding without all-or-nothing loss."""
    project_id = str(plan.get("project_id") or "")
    group_id = str(plan.get("id") or plan.get("group_id") or "")
    raw_items = plan.get("items")
    items = [item for item in raw_items or () if isinstance(item, Mapping)]

    def finalized(run_id: str, result: dict[str, Any]) -> None:
        summary = result.get("finalize_summary") if isinstance(result, dict) else {}
        project_link = result.get("active_project_link") if isinstance(result, dict) else {}
        if (
            not isinstance(summary, dict)
            or not summary.get("persisted")
            or not isinstance(project_link, dict)
            or str(project_link.get("project_id") or "") != project_id
        ):
            log.warning("PROJECT_RETEST_BATCH_EVIDENCE_LINK_SKIPPED", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "project_id": project_id,
                "group_id": group_id,
                "finding_count": len(items),
                "reason": "run_finalization_unavailable",
            })
            return
        linked_count = 0
        failed_count = 0
        for item in items:
            finding_id = str(item.get("finding_id") or "")
            check_id = str(item.get("check_id") or "")
            try:
                linked = link_completed_verification_run(
                    session_id,
                    project_id,
                    finding_id,
                    check_id,
                    run_id,
                    team_id=team_id,
                )
            except ProjectWorkspaceError as exc:
                failed_count += 1
                log.warning("PROJECT_RETEST_BATCH_EVIDENCE_LINK_SKIPPED", extra={
                    "run_id": run_id,
                    "session": get_log_session_id(session_id),
                    "team_id": team_id,
                    "project_id": project_id,
                    "group_id": group_id,
                    "finding_id": finding_id,
                    "check_id": check_id,
                    "reason": str(exc),
                })
            except Exception:
                failed_count += 1
                log.error("PROJECT_RETEST_BATCH_EVIDENCE_LINK_ERROR", exc_info=True, extra={
                    "run_id": run_id,
                    "session": get_log_session_id(session_id),
                    "team_id": team_id,
                    "project_id": project_id,
                    "group_id": group_id,
                    "finding_id": finding_id,
                    "check_id": check_id,
                })
            else:
                linked_count += int(bool(linked.get("created")))
        log.info("PROJECT_RETEST_BATCH_EVIDENCE_LINKED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "group_id": group_id,
            "finding_count": len(items),
            "linked_count": linked_count,
            "failed_count": failed_count,
        })

    return finalized


__all__ = ["retest_batch_run_finalized_hook"]
