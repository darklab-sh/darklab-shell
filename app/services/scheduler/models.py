"""Scheduler data models and constants."""

from __future__ import annotations

from dataclasses import dataclass

OWNER_KIND_USER = "user"
OWNER_KIND_WATCHER = "watcher"
OWNER_KIND_PROJECT_DIGEST = "project_digest"
OWNER_KINDS = frozenset({OWNER_KIND_USER, OWNER_KIND_WATCHER, OWNER_KIND_PROJECT_DIGEST})

SCHEDULE_KIND_COMMAND = "command"
SCHEDULE_KINDS = frozenset({SCHEDULE_KIND_COMMAND})

OVERLAP_POLICY_SKIP = "skip"
OVERLAP_POLICIES = frozenset({OVERLAP_POLICY_SKIP})

CADENCE_PRESETS = {
    "hourly": "0 * * * *",
    "daily": "0 0 * * *",
    "weekly": "0 0 * * 0",
}
# Cadence names are operator-facing. Keep OpenAPI, CLI choices, browser modal
# chips, and command-autocomplete hints aligned when this set changes.

FIRE_STATUS_SKIPPED_OVERLAP = "skipped_overlap"
FIRE_STATUS_SKIPPED_REVOKED = "skipped_revoked"
FIRE_STATUS_FIRED = "fired"
FIRE_STATUS_FAILED = "fire_failed"
FIRE_STATUSES = frozenset({
    FIRE_STATUS_SKIPPED_OVERLAP,
    FIRE_STATUS_SKIPPED_REVOKED,
    FIRE_STATUS_FIRED,
    FIRE_STATUS_FAILED,
})


@dataclass(frozen=True)
class Schedule:
    id: str
    session_token: str
    team_id: str
    owner_kind: str
    owner_id: str
    kind: str
    command_text: str
    cron_expr: str
    cadence_preset: str | None
    timezone: str
    enabled: bool
    next_run_at: str
    last_run_at: str
    last_run_id: str
    overlap_policy: str
    consecutive_failures: int
    label: str
    paused_reason: str
    last_error: str
    created: str
    updated: str


@dataclass(frozen=True)
class ScheduleFire:
    id: str
    schedule_id: str
    team_id: str
    owner_kind: str
    owner_id: str
    fired_at: str
    run_id: str
    status: str
    reason: str
