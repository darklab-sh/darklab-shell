"""Stable payload builders for notification triggers."""

from __future__ import annotations

from datetime import datetime, timezone
import shlex
from typing import Any

from services.notifications.models import (
    TRIGGER_PTY_SESSION_ENDED,
    TRIGGER_RUN_COMPLETE,
    TRIGGER_SCHEDULED_RUN_FAILED,
    TRIGGER_TEST,
    TRIGGER_WATCHER_CHANGED,
    TRIGGER_WATCHER_ERROR,
    TRIGGER_WATCHER_RECOVERED,
    notification_app_name,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _command_root(command: Any) -> str:
    raw = str(command or "").strip()
    if not raw:
        return ""
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()
    return parts[0] if parts else ""


def _session_hint(session_token: Any) -> str:
    token = str(session_token or "")
    return token[-4:] if token else ""


def build_run_complete_payload(run: Any, findings_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    session_token = _value(run, "session_token", _value(run, "session_id", ""))
    return {
        "trigger": TRIGGER_RUN_COMPLETE,
        "app_name": notification_app_name(),
        "occurred_at": _utc_now(),
        "session_token_hint": _session_hint(session_token),
        "run_id": str(_value(run, "id", _value(run, "run_id", "")) or ""),
        "command_root": _command_root(_value(run, "command", "")),
        "exit_code": _value(run, "exit_code", None),
        "summary_fields": dict(findings_summary or {}),
    }


def build_pty_session_ended_payload(run: Any) -> dict[str, Any]:
    payload = build_run_complete_payload(run)
    payload["trigger"] = TRIGGER_PTY_SESSION_ENDED
    return payload


def build_watcher_changed_payload(watcher: Any, diff_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "trigger": TRIGGER_WATCHER_CHANGED,
        "app_name": notification_app_name(),
        "occurred_at": _utc_now(),
        "watcher_id": str(_value(watcher, "id", _value(watcher, "watcher_id", "")) or ""),
        "summary_fields": dict(diff_summary or {}),
    }


def build_watcher_error_payload(watcher: Any, error: str) -> dict[str, Any]:
    return {
        "trigger": TRIGGER_WATCHER_ERROR,
        "app_name": notification_app_name(),
        "occurred_at": _utc_now(),
        "watcher_id": str(_value(watcher, "id", _value(watcher, "watcher_id", "")) or ""),
        "summary_fields": {"error": str(error or "watcher failed")},
    }


def build_watcher_recovered_payload(watcher: Any) -> dict[str, Any]:
    return {
        "trigger": TRIGGER_WATCHER_RECOVERED,
        "app_name": notification_app_name(),
        "occurred_at": _utc_now(),
        "watcher_id": str(_value(watcher, "id", _value(watcher, "watcher_id", "")) or ""),
        "summary_fields": {},
    }


def build_scheduled_run_failed_payload(schedule: Any, error: str) -> dict[str, Any]:
    return {
        "trigger": TRIGGER_SCHEDULED_RUN_FAILED,
        "app_name": notification_app_name(),
        "occurred_at": _utc_now(),
        "schedule_id": str(_value(schedule, "id", _value(schedule, "schedule_id", "")) or ""),
        "command_root": _command_root(_value(schedule, "command_text", _value(schedule, "command", ""))),
        "summary_fields": {"error": str(error or "scheduled run failed")},
    }


def build_test_payload(channel_id: str = "") -> dict[str, Any]:
    app_name = notification_app_name()
    return {
        "trigger": TRIGGER_TEST,
        "app_name": app_name,
        "message": f"{app_name} test notification",
        "channel_id": str(channel_id or ""),
        "occurred_at": _utc_now(),
    }
