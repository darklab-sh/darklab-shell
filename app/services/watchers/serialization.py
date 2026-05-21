"""Shared watcher payload shaping helpers."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from services.scheduler.models import Schedule
from services.scheduler.serialization import schedule_payload
from services.watchers.models import Watcher, WatcherFire


def watcher_payload(watcher: Watcher, *, schedule: Schedule | None = None) -> dict[str, Any]:
    payload = asdict(watcher)
    payload.pop("session_token", None)
    payload["options"] = dict(watcher.options)
    if schedule is not None:
        payload["schedule"] = schedule_payload(schedule)
    return payload


def watcher_fire_payload(fire: WatcherFire) -> dict[str, Any]:
    return asdict(fire)
