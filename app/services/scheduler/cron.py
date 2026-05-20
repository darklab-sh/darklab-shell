"""Cron parsing and next-fire helpers for schedules."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from services.scheduler import scheduler_cfg
from services.scheduler.models import CADENCE_PRESETS


class ScheduleCronError(ValueError):
    """Raised when a schedule cadence or timezone is invalid."""


def default_timezone() -> str:
    value = str(scheduler_cfg().get("default_timezone") or "UTC").strip() or "UTC"
    validate_timezone(value)
    return value


def validate_timezone(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ScheduleCronError("timezone is required")
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ScheduleCronError("timezone must be an IANA timezone name") from exc
    return normalized


def canonical_cron_for_preset(preset: str | None) -> str | None:
    if preset in ("", None):
        return None
    normalized = str(preset).strip().lower()
    try:
        return CADENCE_PRESETS[normalized]
    except KeyError as exc:
        raise ScheduleCronError("cadence preset must be hourly, daily, or weekly") from exc


def normalize_cron(cron_expr: str | None = None, *, cadence_preset: str | None = None) -> tuple[str, str | None]:
    preset_expr = canonical_cron_for_preset(cadence_preset)
    if preset_expr is not None:
        validate_cron(preset_expr)
        return preset_expr, str(cadence_preset).strip().lower()
    normalized = " ".join(str(cron_expr or "").strip().split())
    validate_cron(normalized)
    return normalized, None


def validate_cron(cron_expr: str) -> str:
    normalized = " ".join(str(cron_expr or "").strip().split())
    parts = normalized.split()
    if len(parts) != 5 or normalized.startswith("@"):
        raise ScheduleCronError("cron expression must use five POSIX fields")
    if not croniter.is_valid(normalized):
        raise ScheduleCronError("cron expression is invalid")
    return normalized


def _aware_after(after: datetime, tz_name: str) -> datetime:
    tz = ZoneInfo(validate_timezone(tz_name))
    base = after if after.tzinfo is not None else after.replace(tzinfo=timezone.utc)
    return base.astimezone(tz)


def next_fire(cron_expr: str, after: datetime, timezone_name: str = "UTC") -> datetime:
    normalized = validate_cron(cron_expr)
    iterator = croniter(normalized, _aware_after(after, timezone_name))
    return iterator.get_next(datetime).astimezone(timezone.utc)
