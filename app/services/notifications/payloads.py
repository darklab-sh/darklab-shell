"""Stable payload builders for notification triggers."""

from __future__ import annotations

from datetime import datetime, timezone
import shlex
from typing import Any
from urllib.parse import urljoin

from config import CFG
from services.notifications.models import (
    TRIGGER_PTY_SESSION_ENDED,
    TRIGGER_PROJECT_DIGEST,
    TRIGGER_RUN_COMPLETE,
    TRIGGER_SCHEDULED_RUN_FAILED,
    TRIGGER_TEST,
    TRIGGER_WATCHER_CHANGED,
    TRIGGER_WATCHER_ERROR,
    TRIGGER_WATCHER_RECOVERED,
    notification_app_name,
)

MAX_DIGEST_TOP_CHANGES = 5
MAX_DIGEST_CHANGE_LABEL_LENGTH = 140


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


def build_project_digest_payload(
    *,
    project: dict[str, Any],
    summary: dict[str, Any],
    digest_identity: dict[str, str],
    quiet: bool = False,
) -> dict[str, Any]:
    top_changes = summary.get("top_changes")
    safe_top_changes = _safe_digest_top_changes(top_changes)
    relative_link = _project_monitoring_path(project, summary, digest_identity)
    monitoring_url = _absolute_or_relative_url(relative_link)
    return {
        "trigger": TRIGGER_PROJECT_DIGEST,
        "app_name": notification_app_name(),
        "occurred_at": _utc_now(),
        "project_id": str(project.get("id") or digest_identity.get("project_id") or ""),
        "project_name": str(project.get("name") or "Project"),
        "digest_identity": dict(digest_identity),
        "project_monitoring_path": relative_link,
        "project_monitoring_url": monitoring_url,
        "top_changes": safe_top_changes,
        "summary_fields": {
            "project": str(project.get("name") or "Project"),
            "window": (
                f"{digest_identity.get('window_start', '')} to {digest_identity.get('window_end', '')}"
            ).strip(),
            "changed": int(summary.get("changed_monitor_count") or 0),
            "recovered": int(summary.get("recovered_monitor_count") or 0),
            "failed": int(summary.get("failed_monitor_count") or 0),
            "highest_severity": str(summary.get("highest_severity") or "none"),
            "top_changes": len(safe_top_changes),
            "monitoring_link": monitoring_url,
            "quiet": "yes" if quiet else "no",
        },
    }


def _project_monitoring_path(project: dict[str, Any], summary: dict[str, Any], digest_identity: dict[str, str]) -> str:
    links = summary.get("links")
    if isinstance(links, dict):
        raw_link = str(links.get("project_monitoring") or "").strip()
        if raw_link.startswith("/"):
            return raw_link
    project_id = str(project.get("id") or digest_identity.get("project_id") or "").strip()
    return f"/projects/{project_id}/monitoring" if project_id else "/projects"


def _absolute_or_relative_url(path: str) -> str:
    base_url = str(CFG.get("app_public_base_url") or "").strip()
    if not base_url:
        return path
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _safe_digest_top_changes(value: Any) -> list[dict[str, str]]:
    raw_changes = value if isinstance(value, list) else []
    safe_changes: list[dict[str, str]] = []
    for item in raw_changes:
        if not isinstance(item, dict):
            continue
        safe_changes.append({
            "severity": str(item.get("severity") or "none")[:40],
            "fire_kind": str(item.get("fire_kind") or "")[:80],
            "watcher_label": str(item.get("watcher_label") or "")[:120],
            "label": str(item.get("label") or "")[:MAX_DIGEST_CHANGE_LABEL_LENGTH],
            "created": str(item.get("created") or "")[:80],
        })
        if len(safe_changes) >= MAX_DIGEST_TOP_CHANGES:
            break
    return safe_changes


def build_test_payload(channel_id: str = "") -> dict[str, Any]:
    app_name = notification_app_name()
    return {
        "trigger": TRIGGER_TEST,
        "app_name": app_name,
        "message": f"{app_name} test notification",
        "channel_id": str(channel_id or ""),
        "occurred_at": _utc_now(),
    }
