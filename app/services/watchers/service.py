"""Backend-agnostic watcher persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid
from typing import Any

from core import database
from core.database_backend import dialect_for_backend
from services.notifications.models import require_durable_session_token
from services.scheduler.models import OWNER_KIND_WATCHER
from services.scheduler.service import create_schedule, delete_schedule, pause_schedule, resume_schedule, update_schedule
from services.watchers.models import (
    DIFF_KIND_NONE,
    DIFF_KINDS,
    WATCHER_FAILURE_DISABLE_THRESHOLD,
    WATCHER_OPTION_DEFAULTS,
    WATCHER_STATE_ERROR,
    WATCHER_STATE_FIRING,
    WATCHER_STATE_OK,
    WATCHER_STATE_PAUSED,
    WATCHER_STATES,
    Watcher,
    WatcherFire,
)

log = logging.getLogger("shell")


class WatcherError(ValueError):
    """Raised when watcher input cannot be persisted."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _watcher_id() -> str:
    return f"wtr_{uuid.uuid4().hex}"


def _watcher_fire_id() -> str:
    return f"wtf_{uuid.uuid4().hex}"


def _dialect():
    return dialect_for_backend(database.DB_BACKEND)


def _bool_param(value: Any) -> Any:
    return _dialect().boolean_param(value)


def _value(row: Any, key: str, default: Any = "") -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def normalize_watcher_options(options: dict[str, Any] | None) -> dict[str, bool]:
    if options is None:
        return dict(WATCHER_OPTION_DEFAULTS)
    if not isinstance(options, dict):
        raise WatcherError("watcher options must be an object")
    unknown = sorted(set(options) - set(WATCHER_OPTION_DEFAULTS))
    if unknown:
        raise WatcherError("unsupported watcher option: " + ", ".join(unknown))
    normalized = dict(WATCHER_OPTION_DEFAULTS)
    for key, value in options.items():
        if not isinstance(value, bool):
            raise WatcherError(f"watcher option {key} must be true or false")
        normalized[key] = value
    return normalized


def row_to_watcher(row: Any) -> Watcher:
    return Watcher(
        id=str(_value(row, "id")),
        session_token=str(_value(row, "session_token")),
        label=str(_value(row, "label")),
        command_text=str(_value(row, "command_text")),
        schedule_id=str(_value(row, "schedule_id")),
        baseline_run_id=str(_value(row, "baseline_run_id")),
        last_run_id=str(_value(row, "last_run_id")),
        last_diff_summary=_dialect().decode_json_dict(_value(row, "last_diff_summary_json", {})),
        state=str(_value(row, "state") or WATCHER_STATE_OK),
        state_reason=str(_value(row, "state_reason")),
        last_error=str(_value(row, "last_error")),
        options=normalize_watcher_options(_dialect().decode_json_dict(_value(row, "options_json", {}))),
        consecutive_no_change=int(_value(row, "consecutive_no_change", 0) or 0),
        consecutive_changed=int(_value(row, "consecutive_changed", 0) or 0),
        consecutive_failures=int(_value(row, "consecutive_failures", 0) or 0),
        created=str(_value(row, "created")),
        updated=str(_value(row, "updated")),
    )


def row_to_watcher_fire(row: Any) -> WatcherFire:
    return WatcherFire(
        id=str(_value(row, "id")),
        watcher_id=str(_value(row, "watcher_id")),
        baseline_run_id=str(_value(row, "baseline_run_id")),
        run_id=str(_value(row, "run_id")),
        diff_summary=_dialect().decode_json_dict(_value(row, "diff_summary_json", {})),
        diff_kind=str(_value(row, "diff_kind") or DIFF_KIND_NONE),
        truncated=_as_bool(_value(row, "truncated")),
        notification_event_ids=[
            str(item) for item in _dialect().decode_json_list(_value(row, "notification_event_ids_json", []))
        ],
        state_at_fire=str(_value(row, "state_at_fire")),
        created=str(_value(row, "created")),
    )


def _max_watchers_per_session() -> int:
    raw = database.CFG.get("watchers", {}).get("max_per_session")
    try:
        configured = int(raw or 32)
    except (TypeError, ValueError):
        log.warning("WATCHER_CONFIG_INVALID", extra={
            "key": "watchers.max_per_session",
            "value": str(raw),
            "fallback": 32,
        })
        configured = 32
    return max(1, configured)


def _watcher_count(conn, session_token: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM watchers WHERE session_token = ?",
        (session_token,),
    ).fetchone()
    return int(_value(row, "count", 0) or 0)


def get_watcher(watcher_id: str, *, conn=None) -> Watcher | None:
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        row = conn.execute("SELECT * FROM watchers WHERE id = ?", (watcher_id,)).fetchone()
        return row_to_watcher(row) if row else None
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def list_for_session(session_token: str, *, conn=None) -> list[Watcher]:
    session = require_durable_session_token(session_token)
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        rows = conn.execute(
            "SELECT * FROM watchers WHERE session_token = ? ORDER BY updated DESC",
            (session,),
        ).fetchall()
        return [row_to_watcher(row) for row in rows]
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def list_watcher_fires(watcher_id: str, *, limit: int = 50, offset: int = 0, conn=None) -> tuple[list[WatcherFire], int]:
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM watcher_fires WHERE watcher_id = ?",
            (watcher_id,),
        ).fetchone()
        total = int(_value(total_row, "count", 0) or 0)
        rows = conn.execute(
            """
            SELECT * FROM watcher_fires
            WHERE watcher_id = ?
            ORDER BY created DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (watcher_id, max(0, int(limit)), max(0, int(offset))),
        ).fetchall()
        return [row_to_watcher_fire(row) for row in rows], total
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def create_watcher(
    session_token: str,
    *,
    command_text: str,
    baseline_run_id: str,
    cron_expr: str | None = None,
    cadence_preset: str | None = None,
    timezone_name: str | None = None,
    label: str = "",
    options: dict[str, Any] | None = None,
    enabled: bool = True,
    conn=None,
) -> Watcher:
    session = require_durable_session_token(session_token)
    command = str(command_text or "").strip()
    baseline = str(baseline_run_id or "").strip()
    if not command:
        raise WatcherError("command text is required")
    if not baseline:
        raise WatcherError("baseline run id is required")
    normalized_options = normalize_watcher_options(options)
    watcher_id = _watcher_id()
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        if _watcher_count(conn, session) >= _max_watchers_per_session():
            raise WatcherError("watcher quota exceeded for this session")
        schedule = create_schedule(
            session,
            command_text=command,
            cron_expr=cron_expr,
            cadence_preset=cadence_preset,
            timezone_name=timezone_name,
            label=label,
            owner_kind=OWNER_KIND_WATCHER,
            owner_id=watcher_id,
            enabled=enabled,
            conn=conn,
        )
        now = _utc_now()
        state = WATCHER_STATE_OK if enabled else WATCHER_STATE_PAUSED
        state_reason = "" if enabled else "created_paused"
        conn.execute(
            """
            INSERT INTO watchers (
                id, session_token, label, command_text, schedule_id, baseline_run_id,
                last_run_id, last_diff_summary_json, state, state_reason, last_error,
                options_json, consecutive_no_change, consecutive_changed, consecutive_failures,
                created, updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                watcher_id,
                session,
                str(label or "").strip(),
                command,
                schedule.id,
                baseline,
                "",
                _dialect().json_param({}),
                state,
                state_reason,
                "",
                _dialect().json_param(normalized_options),
                0,
                0,
                0,
                now,
                now,
            ),
        )
        if ctx is not None:
            conn.commit()
        watcher = get_watcher(watcher_id, conn=conn)
        if watcher is None:
            raise WatcherError("watcher disappeared during create")
        log.info("WATCHER_CREATED", extra={
            "watcher_id": watcher.id,
            "schedule_id": watcher.schedule_id,
            "session": watcher.session_token,
        })
        return watcher
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def update_watcher(watcher_id: str, updates: dict[str, Any], *, conn=None) -> Watcher | None:
    watcher = get_watcher(watcher_id, conn=conn)
    if watcher is None:
        return None
    label = str(updates.get("label", watcher.label) or "").strip()
    options = normalize_watcher_options(updates.get("options", watcher.options))
    schedule_updates: dict[str, Any] = {}
    for key in ("command_text", "cron_expr", "cadence_preset", "timezone", "enabled", "paused_reason"):
        if key in updates:
            schedule_updates[key] = updates[key]
    if "command_text" in updates:
        next_command = str(updates.get("command_text") or "").strip()
        if not next_command:
            raise WatcherError("command text is required")
    else:
        next_command = watcher.command_text
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        if schedule_updates:
            updated_schedule = update_schedule(watcher.schedule_id, schedule_updates, conn=conn)
            if updated_schedule is None:
                raise WatcherError("watcher schedule not found")
            next_command = updated_schedule.command_text
        now = _utc_now()
        conn.execute(
            """
            UPDATE watchers
            SET label = ?, command_text = ?, options_json = ?, updated = ?
            WHERE id = ?
            """,
            (label, next_command, _dialect().json_param(options), now, watcher.id),
        )
        if ctx is not None:
            conn.commit()
        refreshed = get_watcher(watcher.id, conn=conn)
        if refreshed is not None:
            log.info("WATCHER_UPDATED", extra={
                "watcher_id": refreshed.id,
                "schedule_id": refreshed.schedule_id,
                "session": refreshed.session_token,
            })
        return refreshed
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def pause_watcher(watcher_id: str, reason: str = "", *, conn=None) -> Watcher | None:
    return set_watcher_state(
        watcher_id,
        state=WATCHER_STATE_PAUSED,
        state_reason=reason or "paused",
        schedule_enabled=False,
        conn=conn,
    )


def resume_watcher(watcher_id: str, *, conn=None) -> Watcher | None:
    watcher = set_watcher_state(
        watcher_id,
        state=WATCHER_STATE_OK,
        state_reason="",
        last_error="",
        consecutive_failures=0,
        schedule_enabled=True,
        conn=conn,
    )
    return watcher


def accept_baseline(watcher_id: str, *, run_id: str | None = None, conn=None) -> Watcher | None:
    watcher = get_watcher(watcher_id, conn=conn)
    if watcher is None:
        return None
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        baseline_run_id = str(run_id or "").strip()
        if not baseline_run_id:
            row = conn.execute(
                "SELECT run_id FROM watcher_fires WHERE watcher_id = ? AND run_id != '' "
                "ORDER BY created DESC, id DESC LIMIT 1",
                (watcher.id,),
            ).fetchone()
            baseline_run_id = str(_value(row, "run_id") or "")
        if not baseline_run_id:
            raise WatcherError("no watcher fire is available to accept")
        now = _utc_now()
        conn.execute(
            """
            UPDATE watchers
            SET baseline_run_id = ?, state = ?, state_reason = ?, last_error = ?,
                consecutive_no_change = ?, consecutive_changed = ?, consecutive_failures = ?,
                updated = ?
            WHERE id = ?
            """,
            (baseline_run_id, WATCHER_STATE_OK, "", "", 0, 0, 0, now, watcher.id),
        )
        if ctx is not None:
            conn.commit()
        refreshed = get_watcher(watcher.id, conn=conn)
        if refreshed is not None:
            log.info("WATCHER_BASELINE_ACCEPTED", extra={
                "watcher_id": refreshed.id,
                "baseline_run_id": refreshed.baseline_run_id,
                "session": refreshed.session_token,
            })
        return refreshed
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def delete_watcher(watcher_id: str, *, conn=None) -> bool:
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        watcher = get_watcher(watcher_id, conn=conn)
        if watcher is None:
            return False
        conn.execute("DELETE FROM watcher_fires WHERE watcher_id = ?", (watcher.id,))
        conn.execute("DELETE FROM watchers WHERE id = ?", (watcher.id,))
        delete_schedule(watcher.schedule_id, conn=conn)
        if ctx is not None:
            conn.commit()
        log.info("WATCHER_DELETED", extra={
            "watcher_id": watcher.id,
            "schedule_id": watcher.schedule_id,
            "session": watcher.session_token,
        })
        return True
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def record_watcher_fire(
    conn,
    watcher: Watcher,
    *,
    run_id: str,
    baseline_run_id: str | None = None,
    diff_summary: dict[str, Any] | None = None,
    diff_kind: str = DIFF_KIND_NONE,
    truncated: bool = False,
    notification_event_ids: list[str] | None = None,
    state_at_fire: str | None = None,
) -> WatcherFire:
    run = str(run_id or "").strip()
    if not run:
        raise WatcherError("watcher fire run id is required")
    if diff_kind not in DIFF_KINDS:
        raise WatcherError("unsupported watcher diff kind")
    if state_at_fire and state_at_fire not in WATCHER_STATES:
        raise WatcherError("unsupported watcher state")
    created = _utc_now()
    # The conflict clause comes from hardcoded column names via the dialect helper.
    insert_sql = (
        "INSERT INTO watcher_fires "  # nosec B608
        "(id, watcher_id, baseline_run_id, run_id, diff_summary_json, diff_kind, "
        "truncated, notification_event_ids_json, state_at_fire, created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        + _dialect().insert_or_ignore_clause(("watcher_id", "run_id"))
    )
    conn.execute(
        insert_sql,
        (
            _watcher_fire_id(),
            watcher.id,
            baseline_run_id or watcher.baseline_run_id,
            run,
            _dialect().json_param(diff_summary or {}),
            diff_kind,
            _bool_param(truncated),
            _dialect().json_param(notification_event_ids or []),
            state_at_fire or watcher.state,
            created,
        ),
    )
    row = conn.execute(
        "SELECT * FROM watcher_fires WHERE watcher_id = ? AND run_id = ?",
        (watcher.id, run),
    ).fetchone()
    if row is None:
        raise WatcherError("watcher fire disappeared during create")
    return row_to_watcher_fire(row)


def update_watcher_fire(
    conn,
    fire_id: str,
    *,
    diff_summary: dict[str, Any],
    diff_kind: str,
    truncated: bool,
    notification_event_ids: list[str] | None = None,
    state_at_fire: str,
) -> WatcherFire | None:
    if diff_kind not in DIFF_KINDS:
        raise WatcherError("unsupported watcher diff kind")
    if state_at_fire not in WATCHER_STATES:
        raise WatcherError("unsupported watcher state")
    conn.execute(
        """
        UPDATE watcher_fires
        SET diff_summary_json = ?, diff_kind = ?, truncated = ?,
            notification_event_ids_json = ?, state_at_fire = ?
        WHERE id = ?
        """,
        (
            _dialect().json_param(diff_summary),
            diff_kind,
            _bool_param(truncated),
            _dialect().json_param(notification_event_ids or []),
            state_at_fire,
            fire_id,
        ),
    )
    row = conn.execute("SELECT * FROM watcher_fires WHERE id = ?", (fire_id,)).fetchone()
    return row_to_watcher_fire(row) if row else None


def pending_fire_for_run(conn, run_id: str) -> tuple[Watcher, WatcherFire] | None:
    row = conn.execute(
        "SELECT * FROM watcher_fires WHERE run_id = ? AND state_at_fire = ? ORDER BY created ASC LIMIT 1",
        (run_id, WATCHER_STATE_FIRING),
    ).fetchone()
    if row is None:
        return None
    fire = row_to_watcher_fire(row)
    watcher = get_watcher(fire.watcher_id, conn=conn)
    if watcher is None:
        return None
    return watcher, fire


def set_watcher_state(
    watcher_id: str,
    *,
    state: str,
    state_reason: str = "",
    last_error: str = "",
    last_run_id: str | None = None,
    last_diff_summary: dict[str, Any] | None = None,
    consecutive_no_change: int | None = None,
    consecutive_changed: int | None = None,
    consecutive_failures: int | None = None,
    schedule_enabled: bool | None = None,
    conn=None,
) -> Watcher | None:
    if state not in WATCHER_STATES:
        raise WatcherError("unsupported watcher state")
    watcher = get_watcher(watcher_id, conn=conn)
    if watcher is None:
        return None
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        now = _utc_now()
        next_no_change = watcher.consecutive_no_change if consecutive_no_change is None else max(0, int(consecutive_no_change))
        next_changed = watcher.consecutive_changed if consecutive_changed is None else max(0, int(consecutive_changed))
        next_failures = watcher.consecutive_failures if consecutive_failures is None else max(0, int(consecutive_failures))
        conn.execute(
            """
            UPDATE watchers
            SET state = ?, state_reason = ?, last_error = ?, last_run_id = ?,
                last_diff_summary_json = ?, consecutive_no_change = ?,
                consecutive_changed = ?, consecutive_failures = ?, updated = ?
            WHERE id = ?
            """,
            (
                state,
                state_reason,
                last_error,
                watcher.last_run_id if last_run_id is None else last_run_id,
                _dialect().json_param(watcher.last_diff_summary if last_diff_summary is None else last_diff_summary),
                next_no_change,
                next_changed,
                next_failures,
                now,
                watcher.id,
            ),
        )
        if schedule_enabled is False:
            pause_schedule(watcher.schedule_id, state_reason or state, conn=conn)
        elif schedule_enabled is True:
            resume_schedule(watcher.schedule_id, conn=conn)
        if ctx is not None:
            conn.commit()
        return get_watcher(watcher.id, conn=conn)
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def pause_watchers_for_deleted_baselines(conn, run_ids: list[str]) -> int:
    ids = [str(run_id or "").strip() for run_id in run_ids if str(run_id or "").strip()]
    if not ids:
        return 0
    placeholders = ", ".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT id, session_token, schedule_id, baseline_run_id FROM watchers "  # nosec B608
        f"WHERE baseline_run_id IN ({placeholders})",
        ids,
    ).fetchall()
    count = 0
    for row in rows:
        watcher_id = str(_value(row, "id") or "")
        baseline_run_id = str(_value(row, "baseline_run_id") or "")
        updated = set_watcher_state(
            watcher_id,
            state=WATCHER_STATE_ERROR,
            state_reason="baseline_deleted",
            last_error="baseline run was deleted",
            schedule_enabled=False,
            conn=conn,
        )
        if updated is not None:
            count += 1
            log.warning("WATCHER_BASELINE_DELETED", extra={
                "watcher_id": watcher_id,
                "baseline_run_id": baseline_run_id,
                "session": str(_value(row, "session_token") or ""),
            })
    return count


def failure_disable_threshold() -> int:
    return WATCHER_FAILURE_DISABLE_THRESHOLD
