"""Backend-agnostic scheduled run persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from core import database
from core.database_backend import dialect_for_backend
from services.notifications.models import require_durable_session_token
from services.scheduler.cron import default_timezone, next_fire, normalize_cron, validate_timezone
from services.scheduler.models import (
    FIRE_STATUSES,
    OWNER_KIND_USER,
    OWNER_KINDS,
    OVERLAP_POLICY_SKIP,
    SCHEDULE_KIND_COMMAND,
    SCHEDULE_KINDS,
    Schedule,
    ScheduleFire,
)


class ScheduleError(ValueError):
    """Raised when schedule input cannot be persisted."""


def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now() -> str:
    return _utc_now_dt().isoformat()


def _schedule_id() -> str:
    return f"sch_{uuid.uuid4().hex}"


def _fire_id() -> str:
    return f"scf_{uuid.uuid4().hex}"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _value(row: Any, key: str, default: Any = "") -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def row_to_schedule(row: Any) -> Schedule:
    return Schedule(
        id=str(_value(row, "id")),
        session_token=str(_value(row, "session_token")),
        owner_kind=str(_value(row, "owner_kind") or OWNER_KIND_USER),
        owner_id=str(_value(row, "owner_id")),
        kind=str(_value(row, "kind") or SCHEDULE_KIND_COMMAND),
        command_text=str(_value(row, "command_text")),
        cron_expr=str(_value(row, "cron_expr")),
        cadence_preset=_value(row, "cadence_preset") or None,
        timezone=str(_value(row, "timezone") or "UTC"),
        enabled=_as_bool(_value(row, "enabled")),
        next_run_at=str(_value(row, "next_run_at")),
        last_run_at=str(_value(row, "last_run_at")),
        last_run_id=str(_value(row, "last_run_id")),
        overlap_policy=str(_value(row, "overlap_policy") or OVERLAP_POLICY_SKIP),
        consecutive_failures=int(_value(row, "consecutive_failures", 0) or 0),
        label=str(_value(row, "label")),
        paused_reason=str(_value(row, "paused_reason")),
        last_error=str(_value(row, "last_error")),
        created=str(_value(row, "created")),
        updated=str(_value(row, "updated")),
    )


def row_to_schedule_fire(row: Any) -> ScheduleFire:
    return ScheduleFire(
        id=str(_value(row, "id")),
        schedule_id=str(_value(row, "schedule_id")),
        owner_kind=str(_value(row, "owner_kind") or OWNER_KIND_USER),
        owner_id=str(_value(row, "owner_id")),
        fired_at=str(_value(row, "fired_at")),
        run_id=str(_value(row, "run_id")),
        status=str(_value(row, "status")),
        reason=str(_value(row, "reason")),
    )


def _normalize_owner_kind(value: str | None) -> str:
    owner_kind = str(value or OWNER_KIND_USER).strip().lower()
    if owner_kind not in OWNER_KINDS:
        raise ScheduleError("schedule owner kind must be user or watcher")
    return owner_kind


def _normalize_kind(value: str | None) -> str:
    kind = str(value or SCHEDULE_KIND_COMMAND).strip().lower()
    if kind not in SCHEDULE_KINDS:
        raise ScheduleError("schedule kind must be command")
    return kind


def _bool_param(value: Any) -> Any:
    return dialect_for_backend(database.DB_BACKEND).boolean_param(value)


def _next_fire_iso(cron_expr: str, timezone_name: str, after: datetime | None = None) -> str:
    return next_fire(cron_expr, after or _utc_now_dt(), timezone_name).isoformat()


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def create_schedule(
    session_token: str,
    *,
    command_text: str,
    cron_expr: str | None = None,
    cadence_preset: str | None = None,
    timezone_name: str | None = None,
    label: str = "",
    owner_kind: str = OWNER_KIND_USER,
    owner_id: str = "",
    enabled: bool = True,
    conn=None,
) -> Schedule:
    session = require_durable_session_token(session_token)
    owner = _normalize_owner_kind(owner_kind)
    kind = _normalize_kind(SCHEDULE_KIND_COMMAND)
    command = str(command_text or "").strip()
    if not command:
        raise ScheduleError("command text is required")
    schedule_tz = validate_timezone(timezone_name or default_timezone())
    normalized_cron, normalized_preset = normalize_cron(cron_expr, cadence_preset=cadence_preset)
    now = _utc_now()
    schedule = Schedule(
        id=_schedule_id(),
        session_token=session,
        owner_kind=owner,
        owner_id=str(owner_id or ""),
        kind=kind,
        command_text=command,
        cron_expr=normalized_cron,
        cadence_preset=normalized_preset,
        timezone=schedule_tz,
        enabled=bool(enabled),
        next_run_at=_next_fire_iso(normalized_cron, schedule_tz),
        last_run_at="",
        last_run_id="",
        overlap_policy=OVERLAP_POLICY_SKIP,
        consecutive_failures=0,
        label=str(label or "").strip(),
        paused_reason="",
        last_error="",
        created=now,
        updated=now,
    )
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        conn.execute(
            """
            INSERT INTO schedules (
                id, session_token, owner_kind, owner_id, kind, command_text, cron_expr,
                cadence_preset, timezone, enabled, next_run_at, last_run_at, last_run_id,
                overlap_policy, consecutive_failures, label, paused_reason, last_error,
                created, updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                schedule.id,
                schedule.session_token,
                schedule.owner_kind,
                schedule.owner_id,
                schedule.kind,
                schedule.command_text,
                schedule.cron_expr,
                schedule.cadence_preset,
                schedule.timezone,
                _bool_param(schedule.enabled),
                schedule.next_run_at,
                schedule.last_run_at,
                schedule.last_run_id,
                schedule.overlap_policy,
                schedule.consecutive_failures,
                schedule.label,
                schedule.paused_reason,
                schedule.last_error,
                schedule.created,
                schedule.updated,
            ),
        )
        if ctx is not None:
            conn.commit()
        return schedule
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def get_schedule(schedule_id: str, *, conn=None) -> Schedule | None:
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        return row_to_schedule(row) if row else None
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def list_for_session(session_token: str, *, include_watchers: bool = False, conn=None) -> list[Schedule]:
    session = require_durable_session_token(session_token)
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        if include_watchers:
            rows = conn.execute(
                "SELECT * FROM schedules WHERE session_token = ? ORDER BY updated DESC",
                (session,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM schedules WHERE session_token = ? AND owner_kind = ? ORDER BY updated DESC",
                (session, OWNER_KIND_USER),
            ).fetchall()
        return [row_to_schedule(row) for row in rows]
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def update_schedule(schedule_id: str, updates: dict[str, Any], *, conn=None) -> Schedule | None:
    schedule = get_schedule(schedule_id, conn=conn)
    if schedule is None:
        return None
    next_command = str(updates.get("command_text", schedule.command_text) or "").strip()
    if not next_command:
        raise ScheduleError("command text is required")
    next_timezone = validate_timezone(updates.get("timezone") or schedule.timezone)
    if "cron_expr" in updates or "cadence_preset" in updates:
        next_cron, next_preset = normalize_cron(
            updates.get("cron_expr", schedule.cron_expr),
            cadence_preset=updates.get("cadence_preset"),
        )
    else:
        next_cron, next_preset = schedule.cron_expr, schedule.cadence_preset
    enabled = _as_bool(updates.get("enabled", schedule.enabled))
    next_run_at = _next_fire_iso(next_cron, next_timezone) if enabled else schedule.next_run_at
    now = _utc_now()
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        conn.execute(
            """
            UPDATE schedules
            SET command_text = ?, cron_expr = ?, cadence_preset = ?, timezone = ?, enabled = ?,
                next_run_at = ?, label = ?, paused_reason = ?, last_error = ?, updated = ?
            WHERE id = ?
            """,
            (
                next_command,
                next_cron,
                next_preset,
                next_timezone,
                _bool_param(enabled),
                next_run_at,
                str(updates.get("label", schedule.label) or "").strip(),
                str(updates.get("paused_reason", schedule.paused_reason) or ""),
                str(updates.get("last_error", schedule.last_error) or ""),
                now,
                schedule_id,
            ),
        )
        if ctx is not None:
            conn.commit()
        return get_schedule(schedule_id, conn=conn)
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def pause_schedule(schedule_id: str, reason: str = "", *, conn=None) -> Schedule | None:
    return update_schedule(schedule_id, {"enabled": False, "paused_reason": reason or "paused"}, conn=conn)


def resume_schedule(schedule_id: str, *, conn=None) -> Schedule | None:
    return update_schedule(schedule_id, {"enabled": True, "paused_reason": ""}, conn=conn)


def delete_schedule(schedule_id: str, *, conn=None) -> bool:
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        result = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        if ctx is not None:
            conn.commit()
        return bool(getattr(result, "rowcount", 0))
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def record_schedule_fire(
    conn,
    schedule: Schedule,
    *,
    status: str,
    fired_at: str | None = None,
    run_id: str = "",
    reason: str = "",
) -> ScheduleFire:
    if status not in FIRE_STATUSES:
        raise ScheduleError("unsupported schedule fire status")
    fire = ScheduleFire(
        id=_fire_id(),
        schedule_id=schedule.id,
        owner_kind=schedule.owner_kind,
        owner_id=schedule.owner_id,
        fired_at=fired_at or _utc_now(),
        run_id=str(run_id or ""),
        status=status,
        reason=str(reason or ""),
    )
    conn.execute(
        """
        INSERT INTO schedule_fires (id, schedule_id, owner_kind, owner_id, fired_at, run_id, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (fire.id, fire.schedule_id, fire.owner_kind, fire.owner_id, fire.fired_at, fire.run_id, fire.status, fire.reason),
    )
    return fire


def due_schedules(conn, *, now: str | None = None, limit: int = 50) -> list[Schedule]:
    cutoff = now or _utc_now()
    rows = conn.execute(
        """
        SELECT * FROM schedules
        WHERE enabled = ? AND next_run_at != '' AND next_run_at <= ?
        ORDER BY next_run_at ASC, id ASC
        LIMIT ?
        """,
        (_bool_param(True), cutoff, max(1, int(limit))),
    ).fetchall()
    return [row_to_schedule(row) for row in rows]


def mark_schedule_after_fire(
    conn,
    schedule: Schedule,
    *,
    fired_at: str,
    run_id: str = "",
    last_error: str = "",
) -> Schedule:
    next_run = _next_fire_iso(schedule.cron_expr, schedule.timezone, _parse_time(fired_at))
    failures = schedule.consecutive_failures + 1 if last_error else 0
    conn.execute(
        """
        UPDATE schedules
        SET last_run_at = ?, last_run_id = ?, next_run_at = ?, last_error = ?,
            consecutive_failures = ?, updated = ?
        WHERE id = ?
        """,
        (fired_at, run_id or "", next_run, last_error or "", failures, _utc_now(), schedule.id),
    )
    refreshed = get_schedule(schedule.id, conn=conn)
    if refreshed is None:
        raise ScheduleError("schedule disappeared during fire update")
    return refreshed
