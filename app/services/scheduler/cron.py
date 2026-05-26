"""Cron parsing and next-fire helpers for schedules."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import tz as dateutil_tz
from croniter import croniter

from services.scheduler import scheduler_cfg
from services.scheduler.models import CADENCE_PRESETS


class ScheduleCronError(ValueError):
    """Raised when a schedule cadence or timezone is invalid."""


MIN_CRON_INTERVAL_MINUTES = 5


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
    _validate_minute_spacing(parts[0])
    return normalized


def _validate_minute_spacing(minute_field: str) -> None:
    minutes = _expand_minute_field(minute_field)
    if len(minutes) <= 1:
        return
    ordered = sorted(minutes)
    gaps = [next_minute - minute for minute, next_minute in zip(ordered, ordered[1:])]
    gaps.append((ordered[0] + 60) - ordered[-1])
    if min(gaps) < MIN_CRON_INTERVAL_MINUTES:
        raise ScheduleCronError("cron minute field cannot run more often than every 5 minutes")


def _expand_minute_field(minute_field: str) -> set[int]:
    values: set[int] = set()
    for segment in minute_field.split(","):
        segment = segment.strip()
        if not segment:
            raise ScheduleCronError("cron expression is invalid")
        base, step = _split_minute_step(segment)
        start, end = _minute_range(base, has_step="/" in segment)
        values.update(range(start, end + 1, step))
    return values


def _split_minute_step(segment: str) -> tuple[str, int]:
    if "/" not in segment:
        return segment, 1
    base, step_text = segment.split("/", 1)
    try:
        step = int(step_text)
    except ValueError as exc:
        raise ScheduleCronError("cron expression is invalid") from exc
    if step <= 0:
        raise ScheduleCronError("cron expression is invalid")
    return base or "*", step


def _minute_range(base: str, *, has_step: bool = False) -> tuple[int, int]:
    if base == "*":
        return 0, 59
    if "-" in base:
        start_text, end_text = base.split("-", 1)
        start = _minute_number(start_text)
        end = _minute_number(end_text)
        if start > end:
            raise ScheduleCronError("cron expression is invalid")
        return start, end
    minute = _minute_number(base)
    if has_step:
        return minute, 59
    return minute, minute


def _minute_number(value: str) -> int:
    try:
        minute = int(value)
    except ValueError as exc:
        raise ScheduleCronError("cron expression is invalid") from exc
    if minute < 0 or minute > 59:
        raise ScheduleCronError("cron expression is invalid")
    return minute


def _aware_after(after: datetime, tz_name: str) -> datetime:
    tz = ZoneInfo(validate_timezone(tz_name))
    base = after if after.tzinfo is not None else after.replace(tzinfo=timezone.utc)
    return base.astimezone(tz)


def _resolve_local_wall_time(value: datetime, tz_name: str) -> datetime:
    zone = dateutil_tz.gettz(validate_timezone(tz_name))
    if zone is None:
        raise ScheduleCronError("timezone must be an IANA timezone name")
    local = value.replace(tzinfo=None).replace(tzinfo=zone)
    if not dateutil_tz.datetime_exists(local):
        local = dateutil_tz.resolve_imaginary(local)
    elif dateutil_tz.datetime_ambiguous(local):
        local = local.replace(fold=0)
    return local.astimezone(timezone.utc)


def next_fire(cron_expr: str, after: datetime, timezone_name: str = "UTC") -> datetime:
    normalized = validate_cron(cron_expr)
    local_after = _aware_after(after, timezone_name)
    iterator = croniter(normalized, local_after.replace(tzinfo=None))
    return _resolve_local_wall_time(iterator.get_next(datetime), timezone_name)
