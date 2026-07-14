# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared schedule and watcher route normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from services.scheduler.commands import validate_schedule_command
from services.scheduler.dispatch import fire_schedule
from services.scheduler.service import coerce_schedule_bool, get_schedule
from services.watchers.service import WatcherError, get_watcher


class RouteBaselineRunNotFound(ValueError):
    """Raised when a watcher baseline run is not visible to the session."""


class RouteBaselineRunNotCompleted(ValueError):
    """Raised when a watcher baseline run is not complete enough to use."""


@dataclass(frozen=True)
class WatcherRouteUpdate:
    updates: dict[str, Any]
    pause_requested: bool
    resume_requested: bool
    reason: str


def normalize_schedule_create_payload(
    data: Mapping[str, Any],
    session_id: str,
    *,
    command_validator=validate_schedule_command,
) -> dict[str, Any]:
    command = command_validator(
        data.get("command", data.get("command_text")),
        session_id,
        workspace_cwd=str(data.get("workspace_cwd") or ""),
    )
    return {
        "command_text": command,
        "cron_expr": data.get("cron_expr"),
        "cadence_preset": data.get("cadence_preset"),
        "timezone_name": data.get("timezone", data.get("timezone_name")),
        "label": str(data.get("label") or ""),
        "enabled": coerce_schedule_bool(data.get("enabled"), default=True),
    }


def normalize_schedule_update_payload(
    data: Mapping[str, Any],
    session_id: str,
    *,
    command_validator=validate_schedule_command,
) -> dict[str, Any]:
    updates = dict(data)
    if "command" in updates or "command_text" in updates:
        updates["command_text"] = command_validator(
            updates.get("command", updates.get("command_text")),
            session_id,
            workspace_cwd=str(updates.get("workspace_cwd") or ""),
        )
    if "timezone_name" in updates and "timezone" not in updates:
        updates["timezone"] = updates.pop("timezone_name")
    return updates


def baseline_mode_from_watcher_create(data: Mapping[str, Any]) -> str:
    requested = str(data.get("baseline_mode") or "").strip().lower().replace("-", "_")
    if requested in {"first_run", "first"}:
        return "first_run"
    if requested in {"existing_run", "existing", "run"}:
        return "existing_run"
    return "existing_run" if str(data.get("baseline_run_id") or "").strip() else "first_run"


def baseline_run_for_owner(run_id: str, session_id: str, *, team_id: str = "", conn) -> dict[str, Any]:
    baseline_id = str(run_id or "").strip()
    if not baseline_id:
        raise RouteBaselineRunNotFound("baseline run not found")
    normalized_team_id = str(team_id or "").strip()
    if normalized_team_id:
        owner_sql = "team_id = ?"
        owner_params = (normalized_team_id,)
    else:
        owner_sql = "(team_id IS NULL OR team_id = '') AND session_id = ?"
        owner_params = (session_id,)
    row = conn.execute(
        f"SELECT id, session_id, team_id, command, finished FROM runs WHERE id = ? AND {owner_sql}",  # nosec
        (baseline_id, *owner_params),
    ).fetchone()
    if row is None:
        raise RouteBaselineRunNotFound("baseline run not found")
    finished = str(row["finished"] or "").strip()
    if not finished:
        raise RouteBaselineRunNotCompleted("baseline run must be completed")
    return dict(row)


def baseline_run_for_session(run_id: str, session_id: str, *, conn) -> dict[str, Any]:
    return baseline_run_for_owner(run_id, session_id, team_id="", conn=conn)


def normalize_watcher_create_payload(
    data: Mapping[str, Any],
    session_id: str,
    *,
    team_id: str = "",
    conn,
    command_validator=validate_schedule_command,
) -> dict[str, Any]:
    baseline: dict[str, Any] = {}
    if baseline_mode_from_watcher_create(data) == "existing_run":
        baseline = baseline_run_for_owner(str(data.get("baseline_run_id") or ""), session_id, team_id=team_id, conn=conn)
    command_text = str(data.get("command") or data.get("command_text") or baseline.get("command") or "")
    command = command_validator(
        command_text,
        session_id,
        workspace_cwd=str(data.get("workspace_cwd") or ""),
    )
    return {
        "command_text": command,
        "baseline_run_id": str(baseline.get("id") or ""),
        "project_id": str(data.get("project_id") or ""),
        "cron_expr": data.get("cron_expr"),
        "cadence_preset": data.get("cadence_preset"),
        "timezone_name": data.get("timezone", data.get("timezone_name")),
        "label": str(data.get("label") or ""),
        "options": data.get("options"),
        "policy": data.get("policy"),
        "enabled": coerce_schedule_bool(data.get("enabled"), default=True),
    }


def normalize_watcher_update_payload(
    data: Mapping[str, Any],
    session_id: str,
    *,
    command_validator=validate_schedule_command,
) -> WatcherRouteUpdate:
    updates = dict(data)
    if "command" in updates or "command_text" in updates:
        updates["command_text"] = command_validator(
            updates.get("command", updates.get("command_text")),
            session_id,
            workspace_cwd=str(updates.get("workspace_cwd") or ""),
        )
    if "timezone_name" in updates and "timezone" not in updates:
        updates["timezone"] = updates.pop("timezone_name")
    state = str(updates.pop("state", "") or "").strip().lower()
    enabled_value = updates.get("enabled")
    enabled_update = coerce_schedule_bool(enabled_value) if enabled_value is not None else None
    pause_requested = state == "paused" or updates.pop("pause", False) is True or enabled_update is False
    resume_requested = (
        state in {"ok", "resume", "active"}
        or updates.pop("resume", False) is True
        or enabled_update is True
    )
    reason = str(updates.pop("reason", "") or "operator paused")
    updates.pop("enabled", None)
    updates.pop("workspace_cwd", None)
    return WatcherRouteUpdate(
        updates=updates,
        pause_requested=pause_requested,
        resume_requested=resume_requested,
        reason=reason,
    )


def schedule_for_watcher(watcher, *, conn):
    schedule = get_schedule(watcher.schedule_id, conn=conn)
    if schedule is None:
        raise WatcherError("watcher schedule not found")
    return schedule


def fire_schedule_now(conn, schedule, *, fired_at: str | None = None):
    fired_at = fired_at or datetime.now(timezone.utc).isoformat()
    status = fire_schedule(conn, schedule, fired_at=fired_at)
    refreshed = get_schedule(schedule.id, conn=conn)
    return status, refreshed or schedule, fired_at


def fire_watcher_now(conn, watcher, *, fired_at: str | None = None):
    fired_at = fired_at or datetime.now(timezone.utc).isoformat()
    schedule = schedule_for_watcher(watcher, conn=conn)
    status = fire_schedule(conn, schedule, fired_at=fired_at)
    refreshed = get_watcher(watcher.id, conn=conn) or watcher
    refreshed_schedule = get_schedule(schedule.id, conn=conn) or schedule
    return status, refreshed, refreshed_schedule, fired_at
