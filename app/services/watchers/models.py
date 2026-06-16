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

WATCHER_FIRE_KIND_CHANGED = "changed"
WATCHER_FIRE_KIND_RECOVERED = "recovered"
WATCHER_FIRE_KIND_FAILED = "failed"
WATCHER_FIRE_KIND_NO_CHANGE = "no_change"
WATCHER_FIRE_KIND_BASELINE_CREATED = "baseline_created"
WATCHER_FIRE_KIND_BASELINE_ACCEPTED = "baseline_accepted"
WATCHER_FIRE_KIND_PAUSED = "paused"
WATCHER_FIRE_KIND_UNCLASSIFIED = "unclassified"
WATCHER_FIRE_KINDS = frozenset({
    WATCHER_FIRE_KIND_CHANGED,
    WATCHER_FIRE_KIND_RECOVERED,
    WATCHER_FIRE_KIND_FAILED,
    WATCHER_FIRE_KIND_NO_CHANGE,
    WATCHER_FIRE_KIND_BASELINE_CREATED,
    WATCHER_FIRE_KIND_BASELINE_ACCEPTED,
    WATCHER_FIRE_KIND_PAUSED,
    WATCHER_FIRE_KIND_UNCLASSIFIED,
})

WATCHER_ACK_NEW = "new"
WATCHER_ACK_ACKNOWLEDGED = "acknowledged"
WATCHER_ACK_EXPECTED = "expected"
WATCHER_ACK_NEEDS_ACTION = "needs_action"
WATCHER_ACK_RESOLVED = "resolved"
WATCHER_ACK_STATES = frozenset({
    WATCHER_ACK_NEW,
    WATCHER_ACK_ACKNOWLEDGED,
    WATCHER_ACK_EXPECTED,
    WATCHER_ACK_NEEDS_ACTION,
    WATCHER_ACK_RESOLVED,
})

DIFF_KIND_SIGNAL = diff_models.DIFF_KIND_SIGNAL
DIFF_KIND_TEXTUAL = diff_models.DIFF_KIND_TEXTUAL
DIFF_KIND_NONE = diff_models.DIFF_KIND_NONE
DIFF_KINDS = diff_models.DIFF_KINDS

WATCHER_OPTION_DEFAULTS: dict[str, bool] = {
    "suppress_removals": False,
    "notify_metadata_changes": False,
}

WATCHER_POLICY_SIGNAL_CLASSES = frozenset({"findings", "entities", "ports"})
WATCHER_POLICY_DEFAULTS: dict[str, Any] = {
    "ignore_line_patterns": [],
    "alert_after_repeated_changes": 1,
    "alert_signal_classes": [],
}


@dataclass(frozen=True)
class Watcher:
    id: str
    session_token: str
    team_id: str
    project_id: str
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
    policy: dict[str, Any]
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
    state_reason: str
    fire_kind: str
    ack_state: str
    ack_note: str
    ack_by: str
    ack_at: str
    created: str


WatcherDiff = diff_models.DiffResult


WATCHER_FAILURE_DISABLE_THRESHOLD = 5
