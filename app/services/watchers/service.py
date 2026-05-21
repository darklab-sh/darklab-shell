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
from services.scheduler.service import create_schedule, delete_schedule
from services.watchers.models import (
    DIFF_KIND_NONE,
    DIFF_KINDS,
    WATCHER_OPTION_DEFAULTS,
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
