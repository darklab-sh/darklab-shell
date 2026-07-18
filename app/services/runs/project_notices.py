# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-related run notice formatting helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def publish_counted_project_notice(
    run_id: str,
    *,
    count: int,
    singular: str,
    plural: str,
    text_template: str,
    payload: dict[str, object],
    publish_run_event_fn: Callable[[str, str, dict[str, Any]], Any],
) -> None:
    if count <= 0:
        return
    label = singular if count == 1 else plural
    publish_run_event_fn(run_id, "notice", {
        **payload,
        "text": text_template.format(count=count, label=label),
    })


def publish_project_finalize_notices(
    run_id: str,
    active_project_link,
    finalize_summary,
    *,
    publish_run_event_fn: Callable[[str, str, dict[str, Any]], Any],
) -> None:
    def _publish_counted(**kwargs) -> None:
        publish_counted_project_notice(run_id, publish_run_event_fn=publish_run_event_fn, **kwargs)

    if active_project_link:
        project_name = str(
            active_project_link.get("project_name")
            or active_project_link.get("project_id")
            or "active project"
        )
        project_payload = {
            "project_id": active_project_link.get("project_id"),
            "project_name": project_name,
        }
        publish_run_event_fn(run_id, "notice", {
            **project_payload,
            "text": f"[project] linked run to {project_name}",
            "project_linked": True,
        })
        discovered_target_count = int(active_project_link.get("discovered_target_count") or 0)
        linked_entity_count = int(active_project_link.get("linked_entity_count") or 0)
        rejected_entity_count = int(active_project_link.get("rejected_entity_count") or 0)
        for spec in (
            {
                "count": discovered_target_count,
                "singular": "target",
                "plural": "targets",
                "text_template": f"[project] discovered {{count}} {{label}} for {project_name}",
                "payload": {
                    **project_payload,
                    "project_targets_discovered": True,
                    "target_count": discovered_target_count,
                },
            },
            {
                "count": linked_entity_count,
                "singular": "Atlas entity",
                "plural": "Atlas entities",
                "text_template": f"[project] linked {{count}} {{label}} to {project_name}",
                "payload": {
                    **project_payload,
                    "project_entities_linked": True,
                    "entity_count": linked_entity_count,
                },
            },
            {
                "count": rejected_entity_count,
                "singular": "Atlas entity",
                "plural": "Atlas entities",
                "text_template": (
                    f"[project] skipped {{count}} {{label}} for {project_name} "
                    "because the project link limit was reached"
                ),
                "payload": {
                    **project_payload,
                    "project_entities_rejected": True,
                    "entity_count": rejected_entity_count,
                    "reason": "project_link_limit",
                },
            },
        ):
            _publish_counted(**spec)
    if isinstance(finalize_summary, dict):
        auto_promote_count = int(finalize_summary.get("project_auto_promote_count") or 0)
        promoted_count = int(finalize_summary.get("project_auto_promote_promoted_count") or 0)
        project_ids = [
            str(project_id)
            for project_id in (finalize_summary.get("project_auto_promote_project_ids") or [])
            if str(project_id or "")
        ]
        _publish_counted(
            count=auto_promote_count,
            singular="Atlas entity",
            plural="Atlas entities",
            text_template="[project] auto-promoted {count} {label}",
            payload={
                "project_id": project_ids[0] if len(project_ids) == 1 else "",
                "project_ids": project_ids,
                "project_auto_promoted": True,
                "entity_count": auto_promote_count,
                "promoted_count": promoted_count,
            },
        )
