"""Watcher data models and constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.diff import models as diff_models

WATCHER_STATE_OK = "ok"
WATCHER_STATE_CHANGED = "changed"
WATCHER_STATE_FIRING = "firing"
WATCHER_STATE_PAUSED = "paused"
WATCHER_STATE_ERROR = "error"
WATCHER_STATES = frozenset({
    WATCHER_STATE_OK,
    WATCHER_STATE_CHANGED,
    WATCHER_STATE_FIRING,
    WATCHER_STATE_PAUSED,
    WATCHER_STATE_ERROR,
})

DIFF_KIND_SIGNAL = diff_models.DIFF_KIND_SIGNAL
DIFF_KIND_TEXTUAL = diff_models.DIFF_KIND_TEXTUAL
DIFF_KIND_NONE = diff_models.DIFF_KIND_NONE
DIFF_KINDS = diff_models.DIFF_KINDS

WATCHER_OPTION_DEFAULTS: dict[str, bool] = {
    "suppress_removals": False,
    "notify_metadata_changes": False,
}


@dataclass(frozen=True)
class Watcher:
    id: str
    session_token: str
    team_id: str
    label: str
    command_text: str
    schedule_id: str
    baseline_run_id: str
    last_run_id: str
    last_diff_summary: dict[str, Any]
    state: str
    state_reason: str
    last_error: str
    options: dict[str, bool]
    consecutive_no_change: int
    consecutive_changed: int
    consecutive_failures: int
    created: str
    updated: str


@dataclass(frozen=True)
class WatcherFire:
    id: str
    watcher_id: str
    team_id: str
    baseline_run_id: str
    run_id: str
    diff_summary: dict[str, Any]
    diff_kind: str
    truncated: bool
    notification_event_ids: list[str]
    state_at_fire: str
    created: str


WatcherDiff = diff_models.DiffResult


WATCHER_FAILURE_DISABLE_THRESHOLD = 5
