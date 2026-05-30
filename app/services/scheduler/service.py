"""Backend-agnostic scheduled run persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid
from typing import Any

from core import database
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.notifications.models import require_durable_session_token
from services.scheduler.cron import default_timezone, next_fire, normalize_cron, validate_timezone
from services.scheduler.models import (
    FIRE_STATUSES,
    FIRE_STATUS_FIRED,
    OWNER_KIND_USER,
    OWNER_KINDS,
    OVERLAP_POLICY_SKIP,
    SCHEDULE_KIND_COMMAND,
    SCHEDULE_KINDS,
    Schedule,
    ScheduleFire,
)

log = logging.getLogger("shell")


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


def coerce_schedule_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _as_bool(value: Any) -> bool:
    return coerce_schedule_bool(value)


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
        team_id=str(_value(row, "team_id")),
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
        team_id=str(_value(row, "team_id")),
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


def _max_schedules_per_session() -> int:
    raw = database.CFG.get("scheduler", {}).get("max_per_session")
    try:
        configured = int(raw or 32)
    except (TypeError, ValueError):
        log.warning("SCHEDULER_CONFIG_INVALID", extra={
            "key": "scheduler.max_per_session",
            "value": str(raw),
            "fallback": 32,
        })
        configured = 32
    return max(1, configured)


def _owner_schedule_clause(session_token: str, team_id: str = "", *, table_alias: str = "") -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    normalized_team_id = str(team_id or "").strip()
    if normalized_team_id:
        return f"{prefix}team_id = ?", (normalized_team_id,)
    return f"({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_token = ?", (session_token,)


def _normal_schedule_count(conn, session_token: str, *, team_id: str = "") -> int:
    owner_sql, owner_params = _owner_schedule_clause(session_token, team_id)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM schedules WHERE {owner_sql} AND owner_kind = ?",  # nosec
        (*owner_params, OWNER_KIND_USER),
    ).fetchone()
    return int(_value(row, "count", 0) or 0)


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
    team_id: str = "",
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
        team_id=str(team_id or "").strip(),
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
        if (
            schedule.owner_kind == OWNER_KIND_USER
            and _normal_schedule_count(conn, session, team_id=schedule.team_id) >= _max_schedules_per_session()
        ):
            raise ScheduleError("schedule quota exceeded for this scope")
        conn.execute(
            """
            INSERT INTO schedules (
                id, session_token, team_id, owner_kind, owner_id, kind, command_text, cron_expr,
                cadence_preset, timezone, enabled, next_run_at, last_run_at, last_run_id,
                overlap_policy, consecutive_failures, label, paused_reason, last_error,
                created, updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                schedule.id,
                schedule.session_token,
                schedule.team_id,
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
        log.debug("SCHEDULE_PERSISTED", extra={
            "schedule_id": schedule.id,
            "owner_kind": schedule.owner_kind,
            "enabled": schedule.enabled,
            "cron_expr": schedule.cron_expr,
            "cadence_preset": schedule.cadence_preset or "",
            "timezone": schedule.timezone,
            "next_run_at": schedule.next_run_at,
        })
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
    return list_for_owner(session, team_id="", include_watchers=include_watchers, conn=conn)


def list_for_owner(
    session_token: str,
    *,
    team_id: str = "",
    include_watchers: bool = False,
    conn=None,
) -> list[Schedule]:
    session = require_durable_session_token(session_token)
    owner_sql, owner_params = _owner_schedule_clause(session, team_id)
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        if include_watchers:
            rows = conn.execute(
                f"SELECT * FROM schedules WHERE {owner_sql} ORDER BY updated DESC",  # nosec
                owner_params,
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM schedules WHERE {owner_sql} AND owner_kind = ? ORDER BY updated DESC",  # nosec
                (*owner_params, OWNER_KIND_USER),
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
    next_label = str(updates.get("label", schedule.label) or "").strip()
    next_paused_reason = str(updates.get("paused_reason", schedule.paused_reason) or "")
    next_last_error = str(updates.get("last_error", schedule.last_error) or "")
    try:
        next_failures = max(0, int(updates.get("consecutive_failures", schedule.consecutive_failures) or 0))
    except (TypeError, ValueError) as exc:
        raise ScheduleError("consecutive failures must be a non-negative integer") from exc
    if "enabled" in updates and enabled and schedule.enabled is False and not next_paused_reason:
        next_last_error = ""
        next_failures = 0
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
                next_run_at = ?, label = ?, paused_reason = ?, last_error = ?,
                consecutive_failures = ?, updated = ?
            WHERE id = ?
            """,
            (
                next_command,
                next_cron,
                next_preset,
                next_timezone,
                _bool_param(enabled),
                next_run_at,
                next_label,
                next_paused_reason,
                next_last_error,
                next_failures,
                now,
                schedule_id,
            ),
        )
        if ctx is not None:
            conn.commit()
        refreshed = get_schedule(schedule_id, conn=conn)
        if refreshed is not None:
            log.debug("SCHEDULE_STATE_UPDATED", extra={
                "schedule_id": refreshed.id,
                "owner_kind": refreshed.owner_kind,
                "enabled": refreshed.enabled,
                "cron_expr": refreshed.cron_expr,
                "cadence_preset": refreshed.cadence_preset or "",
                "timezone": refreshed.timezone,
                "next_run_at": refreshed.next_run_at,
            })
        return refreshed
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def pause_schedule(schedule_id: str, reason: str = "", *, conn=None) -> Schedule | None:
    return update_schedule(schedule_id, {"enabled": False, "paused_reason": reason or "paused"}, conn=conn)


def resume_schedule(schedule_id: str, *, conn=None) -> Schedule | None:
    return update_schedule(
        schedule_id,
        {"enabled": True, "paused_reason": "", "last_error": "", "consecutive_failures": 0},
        conn=conn,
    )


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
        team_id=schedule.team_id,
        owner_kind=schedule.owner_kind,
        owner_id=schedule.owner_id,
        fired_at=fired_at or _utc_now(),
        run_id=str(run_id or ""),
        status=status,
        reason=str(reason or ""),
    )
    conn.execute(
        """
        INSERT INTO schedule_fires (id, schedule_id, team_id, owner_kind, owner_id, fired_at, run_id, status, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fire.id,
            fire.schedule_id,
            fire.team_id,
            fire.owner_kind,
            fire.owner_id,
            fire.fired_at,
            fire.run_id,
            fire.status,
            fire.reason,
        ),
    )
    return fire


def list_schedule_fires(schedule_id: str, *, limit: int = 50, offset: int = 0, conn=None) -> tuple[list[ScheduleFire], int]:
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM schedule_fires WHERE schedule_id = ?",
            (schedule_id,),
        ).fetchone()
        total = int(_value(total_row, "count", 0) or 0)
        rows = conn.execute(
            """
            SELECT * FROM schedule_fires
            WHERE schedule_id = ?
            ORDER BY fired_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (schedule_id, max(0, int(limit)), max(0, int(offset))),
        ).fetchall()
        return [row_to_schedule_fire(row) for row in rows], total
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def schedule_ids_by_run(conn, run_ids: list[str]) -> dict[str, str]:
    ids = [str(run_id or "") for run_id in run_ids if str(run_id or "").strip()]
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    try:
        rows = conn.execute(
            "SELECT run_id, schedule_id FROM schedule_fires "  # nosec
            f"WHERE status = ? AND run_id IN ({placeholders}) "
            "ORDER BY fired_at DESC, id DESC",
            (FIRE_STATUS_FIRED, *ids),
        ).fetchall()
    except Exception as exc:
        if _is_missing_schedule_fires_table(exc):
            log.warning("SCHEDULE_FIRE_LOOKUP_UNAVAILABLE", extra={
                "run_count": len(ids),
                "error": str(exc),
            })
            return {}
        raise
    schedule_by_run: dict[str, str] = {}
    for row in rows:
        run_id = str(_value(row, "run_id") or "")
        # Rows are newest first, so the first schedule for a run wins.
        if run_id and run_id not in schedule_by_run:
            schedule_by_run[run_id] = str(_value(row, "schedule_id") or "")
    return schedule_by_run


def _is_missing_schedule_fires_table(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "schedule_fires" in text
        and (
            "no such table" in text
            or "undefinedtable" in text
            or "does not exist" in text
        )
    )


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


def pause_team_schedules(conn, team_id: str, *, reason: str = "team_archived") -> int:
    normalized_team_id = str(team_id or "").strip()
    if not normalized_team_id:
        return 0
    result = conn.execute(
        """
        UPDATE schedules
        SET enabled = ?, paused_reason = ?, updated = ?
        WHERE team_id = ? AND enabled = ?
        """,
        (_bool_param(False), reason, _utc_now(), normalized_team_id, _bool_param(True)),
    )
    return int(getattr(result, "rowcount", 0) or 0)


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
    log.debug("SCHEDULE_AFTER_FIRE_UPDATED", extra={
        "schedule_id": refreshed.id,
        "team_id": refreshed.team_id,
        "session": get_log_session_id(refreshed.session_token),
        "owner_kind": refreshed.owner_kind,
        "owner_id": refreshed.owner_id,
        "run_id": run_id or "",
        "fired_at": fired_at,
        "next_run_at": refreshed.next_run_at,
        "consecutive_failures": refreshed.consecutive_failures,
        "last_error": refreshed.last_error,
    })
    return refreshed
