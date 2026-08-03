# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project monitoring context for one Atlas entity profile."""

from __future__ import annotations

from typing import Any

from services.projects.monitoring import get_project_monitoring


_MONITOR_STATES = ("active", "changed", "failed", "quiet", "paused")
_RECENT_CHANGE_FIELDS = (
    "fire_id",
    "watcher_id",
    "watcher_label",
    "fire_kind",
    "created",
    "severity",
    "classifier",
    "label",
    "run_id",
    "baseline_run_id",
    "run_available",
    "baseline_run_available",
)


def _empty_context(*, project_id: str = "", applicable: bool = False) -> dict[str, Any]:
    return {
        "applicable": applicable,
        "project_id": project_id,
        "project_name": "",
        "state": "not_monitored" if applicable else "not_applicable",
        "watcher_count": 0,
        "counts": {state: 0 for state in _MONITOR_STATES},
        "latest_change_at": "",
        "recent_changes": [],
        "links": {},
    }


def _target_ids(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        str(item.get("id") or "")
        for item in value
        if isinstance(item, dict) and str(item.get("id") or "")
    }


def _monitoring_state(counts: dict[str, int], watcher_count: int) -> str:
    if watcher_count <= 0:
        return "not_monitored"
    for state in ("failed", "changed", "active", "quiet", "paused"):
        if int(counts.get(state) or 0) > 0:
            return state
    return "not_monitored"


def entity_project_monitoring_context(
    session_id: str,
    project_id: str,
    entity_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    """Return watcher state and recent changes only for an explicit project."""
    normalized_project_id = str(project_id or "").strip()
    normalized_entity_id = str(entity_id or "").strip()
    if not normalized_project_id:
        return _empty_context()

    context = _empty_context(project_id=normalized_project_id, applicable=True)
    payload = get_project_monitoring(
        session_id,
        normalized_project_id,
        team_id=team_id,
        fire_limit=5,
    )
    if payload is None:
        context["state"] = "unavailable"
        return context

    project = payload.get("project")
    if isinstance(project, dict):
        context["project_name"] = str(project.get("name") or "")

    matching_monitors = []
    monitors = payload.get("monitors")
    if isinstance(monitors, list):
        matching_monitors = [
            monitor
            for monitor in monitors
            if isinstance(monitor, dict)
            and normalized_entity_id in _target_ids(monitor.get("linked_targets"))
        ]
    counts = {state: 0 for state in _MONITOR_STATES}
    for monitor in matching_monitors:
        state = str(monitor.get("dashboard_state") or "active")
        if state in counts:
            counts[state] += 1
    context["counts"] = counts
    context["watcher_count"] = len(matching_monitors)
    context["state"] = _monitoring_state(counts, len(matching_monitors))

    summary = payload.get("summary")
    if isinstance(summary, dict):
        changes = summary.get("top_changes")
        if isinstance(changes, list):
            context["recent_changes"] = [
                {field: change.get(field) for field in _RECENT_CHANGE_FIELDS}
                for change in changes
                if isinstance(change, dict)
                and normalized_entity_id in {
                    str(target_id or "")
                    for target_id in change.get("target_ids", [])
                }
            ]
        links = summary.get("links")
        if isinstance(links, dict):
            context["links"] = {
                str(key): str(value)
                for key, value in links.items()
                if str(key or "") and str(value or "")
            }
    context["latest_change_at"] = max(
        (str(change.get("created") or "") for change in context["recent_changes"]),
        default="",
    )
    return context
