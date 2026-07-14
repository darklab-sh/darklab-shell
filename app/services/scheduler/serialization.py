# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared schedule payload and ownership helpers."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from services.scheduler.models import OWNER_KIND_USER, Schedule, ScheduleFire
from services.scheduler.service import get_schedule


def schedule_payload(schedule: Schedule) -> dict[str, Any]:
    payload = asdict(schedule)
    payload.pop("session_token", None)
    payload["enabled"] = bool(schedule.enabled)
    return payload


def schedule_fire_payload(fire: ScheduleFire) -> dict[str, Any]:
    return asdict(fire)


def get_user_schedule_for_owner(schedule_id: str, session_id: str, *, team_id: str = "") -> Schedule | None:
    schedule = get_schedule(schedule_id)
    if schedule is None or schedule.owner_kind != OWNER_KIND_USER:
        return None
    if team_id:
        return schedule if schedule.team_id == team_id else None
    if schedule.team_id or schedule.session_token != session_id:
        return None
    return schedule


def get_user_schedule_for_session(schedule_id: str, session_id: str) -> Schedule | None:
    return get_user_schedule_for_owner(schedule_id, session_id, team_id="")
