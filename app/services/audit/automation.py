"""Audit helpers for schedule and watcher definition changes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import AuditEventType
from .recorder import record_event


def run_now_details(status: str, *, fired_at: str, run_id: str = "", last_error: str = "") -> dict[str, Any]:
    normalized_status = str(status or "").strip()
    details: dict[str, Any] = {
        "status": normalized_status,
        "fired_at": str(fired_at or ""),
        "run_id": str(run_id or ""),
        "reason": _run_now_reason(normalized_status, last_error=last_error),
    }
    return details


def schedule_details(schedule: Any, *, source: str, **extra: Any) -> dict[str, Any]:
    details: dict[str, Any] = {
        "source": source,
        "schedule_id": str(getattr(schedule, "id", "") or ""),
        "enabled": bool(getattr(schedule, "enabled", False)),
        "cron_expr": str(getattr(schedule, "cron_expr", "") or ""),
        "cadence_preset": str(getattr(schedule, "cadence_preset", "") or ""),
        "timezone": str(getattr(schedule, "timezone", "") or ""),
        "next_run_at": str(getattr(schedule, "next_run_at", "") or ""),
        "label": str(getattr(schedule, "label", "") or ""),
    }
    details.update({key: value for key, value in extra.items() if value is not None})
    return details


def watcher_details(watcher: Any, *, source: str, **extra: Any) -> dict[str, Any]:
    details: dict[str, Any] = {
        "source": source,
        "watcher_id": str(getattr(watcher, "id", "") or ""),
        "schedule_id": str(getattr(watcher, "schedule_id", "") or ""),
        "baseline_run_id": str(getattr(watcher, "baseline_run_id", "") or ""),
        "run_id": str(getattr(watcher, "last_run_id", "") or ""),
        "status": str(getattr(watcher, "state", "") or ""),
        "reason": str(getattr(watcher, "state_reason", "") or ""),
        "label": str(getattr(watcher, "label", "") or ""),
    }
    details.update({key: value for key, value in extra.items() if value is not None})
    return details


def _run_now_reason(status: str, *, last_error: str = "") -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "fired":
        return ""
    if normalized in {"fire_failed", "skipped_overlap", "skipped_revoked"}:
        return normalized
    if str(last_error or "").strip():
        return "fire_failed"
    if normalized:
        return "run_not_fired"
    return ""


def record_schedule_event(
    event_type: AuditEventType,
    schedule: Any,
    *,
    audit_fields: Mapping[str, Any],
    source: str,
    details: Mapping[str, Any] | None = None,
    conn=None,
) -> None:
    record_event(
        event_type,
        target_id=str(getattr(schedule, "id", "") or ""),
        details=schedule_details(schedule, source=source, **dict(details or {})),
        conn=conn,
        **dict(audit_fields),
    )


def record_watcher_event(
    event_type: AuditEventType,
    watcher: Any,
    *,
    audit_fields: Mapping[str, Any],
    source: str,
    details: Mapping[str, Any] | None = None,
    conn=None,
) -> None:
    record_event(
        event_type,
        target_id=str(getattr(watcher, "id", "") or ""),
        details=watcher_details(watcher, source=source, **dict(details or {})),
        conn=conn,
        **dict(audit_fields),
    )
