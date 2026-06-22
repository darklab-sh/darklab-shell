"""Data models and constants for outbound notifications."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

CHANNEL_KIND_WEBHOOK = "webhook"
CHANNEL_KIND_SLACK = "slack"
CHANNEL_KIND_DISCORD = "discord"
CHANNEL_KIND_TELEGRAM = "telegram"
CHANNEL_KIND_PUSHOVER = "pushover"
CHANNEL_KIND_EMAIL = "email"

CHANNEL_KINDS = frozenset({
    CHANNEL_KIND_WEBHOOK,
    CHANNEL_KIND_SLACK,
    CHANNEL_KIND_DISCORD,
    CHANNEL_KIND_TELEGRAM,
    CHANNEL_KIND_PUSHOVER,
    CHANNEL_KIND_EMAIL,
})

TRIGGER_RUN_COMPLETE = "run_complete"
TRIGGER_PTY_SESSION_ENDED = "pty_session_ended"
TRIGGER_WATCHER_CHANGED = "watcher_changed"
TRIGGER_WATCHER_ERROR = "watcher_error"
TRIGGER_WATCHER_RECOVERED = "watcher_recovered"
TRIGGER_SCHEDULED_RUN_FAILED = "scheduled_run_failed"
TRIGGER_PROJECT_DIGEST = "project_digest"
TRIGGER_TEST = "test"

TRIGGERS = frozenset({
    TRIGGER_RUN_COMPLETE,
    TRIGGER_PTY_SESSION_ENDED,
    TRIGGER_WATCHER_CHANGED,
    TRIGGER_WATCHER_ERROR,
    TRIGGER_WATCHER_RECOVERED,
    TRIGGER_SCHEDULED_RUN_FAILED,
    TRIGGER_PROJECT_DIGEST,
    TRIGGER_TEST,
})

STATUS_PENDING = "pending"
STATUS_RETRY_WAIT = "retry_wait"
STATUS_SENT = "sent"
STATUS_DEAD = "dead"

EVENT_STATUSES = frozenset({
    STATUS_PENDING,
    STATUS_RETRY_WAIT,
    STATUS_SENT,
    STATUS_DEAD,
})

DEFAULT_NOTIFICATION_APP_NAME = "darklab_shell"


def notification_app_name() -> str:
    try:
        from config import CFG

        configured = CFG.get("app_name")
    except Exception:  # pragma: no cover - defensive fallback for import-time edge cases
        configured = ""
    name = str(configured or "").strip()
    return name or DEFAULT_NOTIFICATION_APP_NAME


def is_durable_session_token(session_token: str) -> bool:
    return str(session_token or "").startswith("tok_")


def require_durable_session_token(session_token: str) -> str:
    token = str(session_token or "").strip()
    if not is_durable_session_token(token):
        raise ValueError("notification channels require a durable session token")
    return token


def _decode_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _decode_json_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, tuple):
        raw_values = value
    elif isinstance(value, list):
        raw_values = tuple(value)
    else:
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, ValueError):
            parsed = []
        raw_values = tuple(parsed) if isinstance(parsed, list) else ()
    return tuple(str(item) for item in raw_values if str(item or "").strip())


@dataclass(frozen=True)
class NotificationChannel:
    id: str
    session_token: str
    team_id: str
    kind: str
    label: str
    secrets: dict[str, Any]
    config: dict[str, Any]
    triggers: tuple[str, ...]
    muted: bool
    created: str
    updated: str

    @property
    def secret_owner_token(self) -> str:
        return self.team_id or self.session_token

    @classmethod
    def from_row(cls, row: Any) -> "NotificationChannel":
        return cls(
            id=str(row["id"]),
            session_token=str(row["session_token"]),
            team_id=str(row["team_id"] or "") if "team_id" in row.keys() else "",
            kind=str(row["kind"]),
            label=str(row["label"] or ""),
            secrets=_decode_json_dict(row["secrets_json"]),
            config=_decode_json_dict(row["config_json"]),
            triggers=_decode_json_list(row["triggers_json"]),
            muted=bool(row["muted"]),
            created=str(row["created"]),
            updated=str(row["updated"]),
        )


@dataclass(frozen=True)
class NotificationEvent:
    id: str
    session_token: str
    team_id: str
    channel_id: str
    trigger: str
    payload: dict[str, Any]
    status: str
    attempts: int
    next_attempt_at: str
    last_attempt_at: str
    last_error: str
    run_id: str
    created: str
    dead_at: str

    @classmethod
    def from_row(cls, row: Any) -> "NotificationEvent":
        return cls(
            id=str(row["id"]),
            session_token=str(row["session_token"]),
            team_id=str(row["team_id"] or "") if "team_id" in row.keys() else "",
            channel_id=str(row["channel_id"]),
            trigger=str(row["trigger"]),
            payload=_decode_json_dict(row["payload_json"]),
            status=str(row["status"]),
            attempts=int(row["attempts"] or 0),
            next_attempt_at=str(row["next_attempt_at"] or ""),
            last_attempt_at=str(row["last_attempt_at"] or ""),
            last_error=str(row["last_error"] or ""),
            run_id=str(row["run_id"] or ""),
            created=str(row["created"]),
            dead_at=str(row["dead_at"] or ""),
        )


@dataclass(frozen=True)
class ChannelResult:
    ok: bool
    retryable: bool = False
    error: str = ""

    @classmethod
    def success(cls) -> "ChannelResult":
        return cls(ok=True)

    @classmethod
    def retry(cls, error: str) -> "ChannelResult":
        return cls(ok=False, retryable=True, error=str(error or "delivery failed"))

    @classmethod
    def terminal(cls, error: str) -> "ChannelResult":
        return cls(ok=False, retryable=False, error=str(error or "delivery failed"))
