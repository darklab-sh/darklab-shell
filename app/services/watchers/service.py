# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Backend-agnostic watcher persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid
from typing import Any, Callable, TypeVar

from config import resolve_effective_cfg
from core import database
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.notifications.models import require_durable_session_token
from services.scheduler.models import OWNER_KIND_WATCHER
from services.scheduler.service import (
    create_schedule,
    delete_schedule,
    pause_schedule,
    pause_team_schedules,
    resume_schedule,
    update_schedule,
)
from services.watchers.models import (
    DIFF_KIND_NONE,
    DIFF_KINDS,
    WATCHER_ACK_NEW,
    WATCHER_ACK_STATES,
    WATCHER_FAILURE_DISABLE_THRESHOLD,
    WATCHER_FIRE_KIND_BASELINE_ACCEPTED,
    WATCHER_FIRE_KIND_BASELINE_CREATED,
    WATCHER_FIRE_KIND_CHANGED,
    WATCHER_FIRE_KIND_FAILED,
    WATCHER_FIRE_KIND_NO_CHANGE,
    WATCHER_FIRE_KIND_PAUSED,
    WATCHER_FIRE_KIND_RECOVERED,
    WATCHER_FIRE_KIND_UNCLASSIFIED,
    WATCHER_FIRE_KINDS,
    WATCHER_OPTION_DEFAULTS,
    WATCHER_POLICY_DEFAULTS,
    WATCHER_POLICY_SIGNAL_CLASSES,
    WATCHER_STATE_CHANGED,
    WATCHER_STATE_ERROR,
    WATCHER_STATE_FIRING,
    WATCHER_STATE_OK,
    WATCHER_STATE_PAUSED,
    WATCHER_STATES,
    Watcher,
    WatcherFire,
)
from services.storage.transactions import run_read, run_transaction

log = logging.getLogger("shell")
_T = TypeVar("_T")


class WatcherError(ValueError):
    """Raised when watcher input cannot be persisted."""


def run_watcher_read(callback: Callable[[Any], _T]) -> _T:
    return run_read(callback, connect=database.db_connect)


def run_watcher_transaction(callback: Callable[[Any], _T]) -> _T:
    return run_transaction(callback, connect=database.db_connect)


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


def _watcher_log_payload(watcher: Watcher, **extra: Any) -> dict[str, Any]:
    payload = {
        "watcher_id": watcher.id,
        "schedule_id": watcher.schedule_id,
        "session": get_log_session_id(watcher.session_token),
        "team_id": watcher.team_id,
        "project_id": watcher.project_id,
        "state": watcher.state,
    }
    payload.update(extra)
    return payload


def _watcher_update_fields(
    watcher: Watcher,
    *,
    label: str,
    next_project_id: str,
    next_command: str,
    options: dict[str, Any],
    policy: dict[str, Any],
    schedule_updates: dict[str, Any],
) -> list[str]:
    fields: list[str] = []
    if label != watcher.label:
        fields.append("label")
    if next_project_id != watcher.project_id:
        fields.append("project_id")
    if next_command != watcher.command_text:
        fields.append("command_text")
    if options != watcher.options:
        fields.append("options")
    if policy != watcher.policy:
        fields.append("policy")
    for key in sorted(str(item) for item in schedule_updates if str(item)):
        if key not in fields:
            fields.append(key)
    return fields


def _watcher_run_owner_clause(watcher: Watcher, *, table_alias: str = "r") -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    if watcher.team_id:
        return f"{prefix}team_id = ?", (watcher.team_id,)
    return f"({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?", (watcher.session_token,)


def _accepted_baseline_run_id(conn, watcher: Watcher, run_id: str | None = None) -> str:
    requested = str(run_id or "").strip()
    owner_sql, owner_params = _watcher_run_owner_clause(watcher, table_alias="r")
    where = [
        "f.watcher_id = ?",
        "f.run_id != ''",
        owner_sql,
        "COALESCE(r.finished, '') != ''",
    ]
    params: list[Any] = [watcher.id, *owner_params]
    if requested:
        where.append("f.run_id = ?")
        params.append(requested)
    row = conn.execute(
        "SELECT f.run_id FROM watcher_fires f "
        "JOIN runs r ON r.id = f.run_id "
        "WHERE " + " AND ".join(where) + " "  # nosec
        "ORDER BY f.created DESC, f.id DESC LIMIT 1",
        tuple(params),
    ).fetchone()
    accepted = str(_value(row, "run_id") or "").strip()
    if accepted:
        return accepted
    if requested:
        raise WatcherError("baseline run must be a completed run from this watcher")
    raise WatcherError("no completed watcher fire is available to accept")


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


def _copy_watcher_policy_defaults() -> dict[str, Any]:
    return {
        "ignore_line_patterns": list(WATCHER_POLICY_DEFAULTS["ignore_line_patterns"]),
        "alert_after_repeated_changes": WATCHER_POLICY_DEFAULTS["alert_after_repeated_changes"],
        "alert_signal_classes": list(WATCHER_POLICY_DEFAULTS["alert_signal_classes"]),
    }


def normalize_watcher_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    if policy is None:
        return _copy_watcher_policy_defaults()
    if not isinstance(policy, dict):
        raise WatcherError("watcher policy must be an object")
    unknown = sorted(set(policy) - set(WATCHER_POLICY_DEFAULTS))
    if unknown:
        raise WatcherError("unsupported watcher policy field: " + ", ".join(unknown))

    patterns_raw = policy.get("ignore_line_patterns", WATCHER_POLICY_DEFAULTS["ignore_line_patterns"])
    if not isinstance(patterns_raw, list):
        raise WatcherError("watcher policy ignore_line_patterns must be a list")
    patterns: list[str] = []
    for item in patterns_raw:
        if not isinstance(item, str):
            raise WatcherError("watcher policy ignore_line_patterns must contain strings")
        pattern = item.strip()
        if not pattern or pattern in patterns:
            continue
        if len(pattern) > 120:
            raise WatcherError("watcher policy ignore_line_patterns entries must be 120 characters or less")
        patterns.append(pattern)
    if len(patterns) > 20:
        raise WatcherError("watcher policy supports at most 20 ignore line patterns")

    repeated_raw = policy.get(
        "alert_after_repeated_changes",
        WATCHER_POLICY_DEFAULTS["alert_after_repeated_changes"],
    )
    if isinstance(repeated_raw, bool):
        raise WatcherError("watcher policy alert_after_repeated_changes must be an integer")
    try:
        repeated = int(repeated_raw)
    except (TypeError, ValueError):
        raise WatcherError("watcher policy alert_after_repeated_changes must be an integer") from None
    if repeated < 1 or repeated > 10:
        raise WatcherError("watcher policy alert_after_repeated_changes must be between 1 and 10")

    classes_raw = policy.get("alert_signal_classes", WATCHER_POLICY_DEFAULTS["alert_signal_classes"])
    if not isinstance(classes_raw, list):
        raise WatcherError("watcher policy alert_signal_classes must be a list")
    classes: list[str] = []
    for item in classes_raw:
        if not isinstance(item, str):
            raise WatcherError("watcher policy alert_signal_classes must contain strings")
        value = item.strip().lower()
        if value not in WATCHER_POLICY_SIGNAL_CLASSES:
            raise WatcherError("unsupported watcher policy signal class: " + value)
        if value not in classes:
            classes.append(value)

    return {
        "ignore_line_patterns": patterns,
        "alert_after_repeated_changes": repeated,
        "alert_signal_classes": classes,
    }


def row_to_watcher(row: Any) -> Watcher:
    return Watcher(
        id=str(_value(row, "id")),
        session_token=str(_value(row, "session_token")),
        team_id=str(_value(row, "team_id")),
        project_id=str(_value(row, "project_id")),
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
        policy=normalize_watcher_policy(_dialect().decode_json_dict(_value(row, "policy_json", {}))),
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
        team_id=str(_value(row, "team_id")),
        baseline_run_id=str(_value(row, "baseline_run_id")),
        run_id=str(_value(row, "run_id")),
        diff_summary=_dialect().decode_json_dict(_value(row, "diff_summary_json", {})),
        diff_kind=str(_value(row, "diff_kind") or DIFF_KIND_NONE),
        truncated=_as_bool(_value(row, "truncated")),
        notification_event_ids=[
            str(item) for item in _dialect().decode_json_list(_value(row, "notification_event_ids_json", []))
        ],
        state_at_fire=str(_value(row, "state_at_fire")),
        state_reason=str(_value(row, "state_reason")),
        fire_kind=str(_value(row, "fire_kind") or WATCHER_FIRE_KIND_UNCLASSIFIED),
        ack_state=str(_value(row, "ack_state") or WATCHER_ACK_NEW),
        ack_note=str(_value(row, "ack_note")),
        ack_by=str(_value(row, "ack_by")),
        ack_at=str(_value(row, "ack_at")),
        created=str(_value(row, "created")),
    )


def _max_watchers_per_session() -> int:
    raw = resolve_effective_cfg().get("watchers", {}).get("max_per_session")
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


def _owner_watcher_clause(session_token: str, team_id: str = "", *, table_alias: str = "") -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    normalized_team_id = str(team_id or "").strip()
    if normalized_team_id:
        return f"{prefix}team_id = ?", (normalized_team_id,)
    return f"({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_token = ?", (session_token,)


def _watcher_count(conn, session_token: str, *, team_id: str = "") -> int:
    owner_sql, owner_params = _owner_watcher_clause(session_token, team_id)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM watchers WHERE {owner_sql}",  # nosec
        owner_params,
    ).fetchone()
    return int(_value(row, "count", 0) or 0)


def _project_owner_clause(session_token: str, team_id: str = "", *, table_alias: str = "") -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    normalized_team_id = str(team_id or "").strip()
    if normalized_team_id:
        return f"{prefix}team_id = ?", (normalized_team_id,)
    return f"({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?", (session_token,)


def _project_in_owner_scope(conn, session_token: str, project_id: str, *, team_id: str = "") -> bool:
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return True
    owner_sql, owner_params = _project_owner_clause(session_token, team_id, table_alias="p")
    row = conn.execute(
        "SELECT p.id FROM projects p WHERE " + owner_sql + " AND p.id = ? LIMIT 1",  # nosec
        (*owner_params, normalized_project_id),
    ).fetchone()
    return row is not None


def infer_project_id_from_run_link(conn, session_token: str, run_id: str, *, team_id: str = "") -> tuple[str, int]:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return "", 0
    owner_sql, owner_params = _project_owner_clause(session_token, team_id, table_alias="p")
    rows = conn.execute(
        "SELECT DISTINCT p.id FROM project_links pl "
        "JOIN projects p ON p.id = pl.project_id "
        "WHERE pl.entity_type = 'run' AND pl.entity_id = ? AND " + owner_sql,  # nosec
        (normalized_run_id, *owner_params),
    ).fetchall()
    ids = [str(_value(row, "id") or "").strip() for row in rows if str(_value(row, "id") or "").strip()]
    return (ids[0] if len(ids) == 1 else ""), len(ids)


def normalize_watcher_project_id(
    conn,
    session_token: str,
    *,
    team_id: str = "",
    requested_project_id: str = "",
    baseline_run_id: str = "",
) -> str:
    project_id = str(requested_project_id or "").strip()
    if not project_id and baseline_run_id:
        project_id, candidate_count = infer_project_id_from_run_link(conn, session_token, baseline_run_id, team_id=team_id)
        reason = "matched" if project_id else ("ambiguous" if candidate_count > 1 else "none")
        log.debug("WATCHER_PROJECT_INFERENCE", extra={
            "session": get_log_session_id(session_token),
            "team_id": team_id,
            "baseline_run_id": str(baseline_run_id or "").strip(),
            "candidate_count": candidate_count,
            "selected_project_id": project_id,
            "reason": reason,
        })
    if project_id and not _project_in_owner_scope(conn, session_token, project_id, team_id=team_id):
        log.warning("WATCHER_PROJECT_ASSIGNMENT_REJECTED", extra={
            "session": get_log_session_id(session_token),
            "team_id": team_id,
            "requested_project_id": project_id,
            "baseline_run_id": str(baseline_run_id or "").strip(),
            "reason": "scope_mismatch",
        })
        raise WatcherError("watcher project must belong to the same scope")
    return project_id


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
    return list_for_owner(session, team_id="", conn=conn)


def list_for_owner(session_token: str, *, team_id: str = "", conn=None) -> list[Watcher]:
    session = require_durable_session_token(session_token)
    owner_sql, owner_params = _owner_watcher_clause(session, team_id)
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        rows = conn.execute(
            f"SELECT * FROM watchers WHERE {owner_sql} ORDER BY updated DESC",  # nosec
            owner_params,
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
    team_id: str = "",
    command_text: str,
    baseline_run_id: str = "",
    project_id: str = "",
    cron_expr: str | None = None,
    cadence_preset: str | None = None,
    timezone_name: str | None = None,
    label: str = "",
    options: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    enabled: bool = True,
    conn=None,
) -> Watcher:
    session = require_durable_session_token(session_token)
    normalized_team_id = str(team_id or "").strip()
    command = str(command_text or "").strip()
    baseline = str(baseline_run_id or "").strip()
    if not command:
        raise WatcherError("command text is required")
    normalized_options = normalize_watcher_options(options)
    normalized_policy = normalize_watcher_policy(policy)
    watcher_id = _watcher_id()
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        if _watcher_count(conn, session, team_id=normalized_team_id) >= _max_watchers_per_session():
            raise WatcherError("watcher quota exceeded for this scope")
        normalized_project_id = normalize_watcher_project_id(
            conn,
            session,
            team_id=normalized_team_id,
            requested_project_id=project_id,
            baseline_run_id=baseline,
        )
        schedule = create_schedule(
            session,
            team_id=normalized_team_id,
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
        state_reason = "pending_baseline" if enabled and not baseline else ("" if enabled else "created_paused")
        conn.execute(
            """
            INSERT INTO watchers (
                id, session_token, team_id, project_id, label, command_text, schedule_id, baseline_run_id,
                last_run_id, last_diff_summary_json, state, state_reason, last_error,
                options_json, policy_json, consecutive_no_change, consecutive_changed, consecutive_failures,
                created, updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                watcher_id,
                session,
                normalized_team_id,
                normalized_project_id,
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
                _dialect().json_param(normalized_policy),
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
        log.info("WATCHER_CREATED", extra=_watcher_log_payload(watcher))
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
    policy = normalize_watcher_policy(updates.get("policy", watcher.policy))
    next_project_id = watcher.project_id
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
        if "project_id" in updates:
            next_project_id = normalize_watcher_project_id(
                conn,
                watcher.session_token,
                team_id=watcher.team_id,
                requested_project_id=str(updates.get("project_id") or "").strip(),
                baseline_run_id=watcher.baseline_run_id,
            )
        changed_fields = _watcher_update_fields(
            watcher,
            label=label,
            next_project_id=next_project_id,
            next_command=next_command,
            options=options,
            policy=policy,
            schedule_updates=schedule_updates,
        )
        log.debug("WATCHER_UPDATE_PREPARED", extra=_watcher_log_payload(
            watcher,
            next_project_id=next_project_id,
            next_command_changed=next_command != watcher.command_text,
            ignore_line_pattern_count=len(policy.get("ignore_line_patterns", [])),
            alert_after_repeated_changes=policy.get("alert_after_repeated_changes", 1),
            alert_signal_classes=",".join(policy.get("alert_signal_classes", [])),
        ))
        now = _utc_now()
        conn.execute(
            """
            UPDATE watchers
            SET label = ?, project_id = ?, command_text = ?, options_json = ?, policy_json = ?, updated = ?
            WHERE id = ?
            """,
            (
                label,
                next_project_id,
                next_command,
                _dialect().json_param(options),
                _dialect().json_param(policy),
                now,
                watcher.id,
            ),
        )
        if ctx is not None:
            conn.commit()
        refreshed = get_watcher(watcher.id, conn=conn)
        if refreshed is not None:
            log.info("WATCHER_UPDATED", extra=_watcher_log_payload(
                refreshed,
                changed_fields=",".join(changed_fields),
                policy_changed=policy != watcher.policy,
                options_changed=options != watcher.options,
                schedule_changed=bool(schedule_updates),
                enabled=refreshed.state != WATCHER_STATE_PAUSED,
            ))
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
    existing = get_watcher(watcher_id, conn=conn)
    watcher = set_watcher_state(
        watcher_id,
        state=WATCHER_STATE_OK,
        state_reason="pending_baseline" if existing is not None and not existing.baseline_run_id else "",
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
        baseline_run_id = _accepted_baseline_run_id(conn, watcher, run_id)
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
        conn.execute(
            """
            UPDATE watcher_fires
            SET fire_kind = ?, state_reason = ?
            WHERE watcher_id = ? AND run_id = ?
            """,
            (WATCHER_FIRE_KIND_BASELINE_ACCEPTED, "baseline_accepted", watcher.id, baseline_run_id),
        )
        if ctx is not None:
            conn.commit()
        refreshed = get_watcher(watcher.id, conn=conn)
        if refreshed is not None:
            log.info(
                "WATCHER_BASELINE_ACCEPTED",
                extra=_watcher_log_payload(refreshed, baseline_run_id=refreshed.baseline_run_id),
            )
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
        log.info("WATCHER_DELETED", extra=_watcher_log_payload(watcher))
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
    state_reason: str = "",
    fire_kind: str = "",
) -> WatcherFire:
    run = str(run_id or "").strip()
    if not run:
        raise WatcherError("watcher fire run id is required")
    if diff_kind not in DIFF_KINDS:
        raise WatcherError("unsupported watcher diff kind")
    if state_at_fire and state_at_fire not in WATCHER_STATES:
        raise WatcherError("unsupported watcher state")
    normalized_fire_kind = fire_kind or _fire_kind_from_state(state_at_fire or watcher.state, state_reason)
    if normalized_fire_kind not in WATCHER_FIRE_KINDS:
        raise WatcherError("unsupported watcher fire kind")
    created = _utc_now()
    # The conflict clause comes from hardcoded column names via the dialect helper.
    insert_sql = (
        "INSERT INTO watcher_fires "  # nosec
        "(id, watcher_id, baseline_run_id, run_id, diff_summary_json, diff_kind, "
        "truncated, notification_event_ids_json, state_at_fire, state_reason, fire_kind, "
        "ack_state, ack_note, ack_by, ack_at, created, team_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
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
            state_reason,
            normalized_fire_kind,
            WATCHER_ACK_NEW,
            "",
            "",
            "",
            created,
            watcher.team_id,
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
    state_reason: str = "",
    fire_kind: str = "",
) -> WatcherFire | None:
    if diff_kind not in DIFF_KINDS:
        raise WatcherError("unsupported watcher diff kind")
    if state_at_fire not in WATCHER_STATES:
        raise WatcherError("unsupported watcher state")
    normalized_fire_kind = fire_kind or _fire_kind_from_state(state_at_fire, state_reason)
    if normalized_fire_kind not in WATCHER_FIRE_KINDS:
        raise WatcherError("unsupported watcher fire kind")
    conn.execute(
        """
        UPDATE watcher_fires
        SET diff_summary_json = ?, diff_kind = ?, truncated = ?,
            notification_event_ids_json = ?, state_at_fire = ?, state_reason = ?, fire_kind = ?
        WHERE id = ?
        """,
        (
            _dialect().json_param(diff_summary),
            diff_kind,
            _bool_param(truncated),
            _dialect().json_param(notification_event_ids or []),
            state_at_fire,
            state_reason,
            normalized_fire_kind,
            fire_id,
        ),
    )
    row = conn.execute("SELECT * FROM watcher_fires WHERE id = ?", (fire_id,)).fetchone()
    return row_to_watcher_fire(row) if row else None


def _fire_kind_from_state(state: str, state_reason: str = "") -> str:
    reason = str(state_reason or "").strip()
    if reason == "baseline_created":
        return WATCHER_FIRE_KIND_BASELINE_CREATED
    if reason == "baseline_accepted":
        return WATCHER_FIRE_KIND_BASELINE_ACCEPTED
    if reason == "recovered":
        return WATCHER_FIRE_KIND_RECOVERED
    if state == WATCHER_STATE_CHANGED:
        return WATCHER_FIRE_KIND_CHANGED
    if state == WATCHER_STATE_ERROR:
        return WATCHER_FIRE_KIND_FAILED
    if state == WATCHER_STATE_PAUSED:
        return WATCHER_FIRE_KIND_PAUSED
    if state == WATCHER_STATE_OK:
        return WATCHER_FIRE_KIND_NO_CHANGE
    return WATCHER_FIRE_KIND_UNCLASSIFIED


def update_watcher_fire_ack(
    conn,
    fire_id: str,
    *,
    ack_state: str,
    ack_note: str = "",
    ack_by: str = "",
    ack_at: str = "",
) -> WatcherFire | None:
    normalized_ack_state = str(ack_state or "").strip() or WATCHER_ACK_NEW
    if normalized_ack_state not in WATCHER_ACK_STATES:
        raise WatcherError("unsupported watcher acknowledgement state")
    existing = conn.execute("SELECT ack_state FROM watcher_fires WHERE id = ?", (fire_id,)).fetchone()
    previous_ack_state = str(_value(existing, "ack_state") or WATCHER_ACK_NEW)
    conn.execute(
        """
        UPDATE watcher_fires
        SET ack_state = ?, ack_note = ?, ack_by = ?, ack_at = ?
        WHERE id = ?
        """,
        (
            normalized_ack_state,
            str(ack_note or ""),
            str(ack_by or ""),
            str(ack_at or ""),
            fire_id,
        ),
    )
    row = conn.execute("SELECT * FROM watcher_fires WHERE id = ?", (fire_id,)).fetchone()
    if not row:
        return None
    fire = row_to_watcher_fire(row)
    extra = {
        "fire_id": fire.id,
        "ack_state": fire.ack_state,
        "previous_ack_state": previous_ack_state,
        "note_chars": len(fire.ack_note),
        "ack_by_present": bool(fire.ack_by),
        "ack_at_present": bool(fire.ack_at),
    }
    log.debug("WATCHER_FIRE_ACK_PERSISTED", extra=extra)
    if previous_ack_state != fire.ack_state:
        log.info("WATCHER_FIRE_ACK_CHANGED", extra=extra)
    return fire


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
        "SELECT id, session_token, team_id, project_id, schedule_id, baseline_run_id FROM watchers "  # nosec
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
                "session": get_log_session_id(str(_value(row, "session_token") or "")),
                "team_id": str(_value(row, "team_id") or ""),
                "project_id": str(_value(row, "project_id") or ""),
            })
    return count


def pause_team_watchers_and_schedules(conn, team_id: str, *, reason: str = "team_archived") -> dict[str, int]:
    normalized_team_id = str(team_id or "").strip()
    if not normalized_team_id:
        return {"watchers": 0, "schedules": 0}
    rows = conn.execute(
        "SELECT id FROM watchers WHERE team_id = ? AND state != ?",
        (normalized_team_id, WATCHER_STATE_PAUSED),
    ).fetchall()
    count = 0
    for row in rows:
        watcher_id = str(_value(row, "id") or "")
        if set_watcher_state(
            watcher_id,
            state=WATCHER_STATE_PAUSED,
            state_reason=reason,
            schedule_enabled=False,
            conn=conn,
        ) is not None:
            count += 1
    # Schedules without a watcher row are still paused by the scheduler service.
    paused_schedules = pause_team_schedules(conn, normalized_team_id, reason=reason)
    paused = {"watchers": count, "schedules": paused_schedules}
    log.info("TEAM_AUTOMATION_PAUSED", extra={
        "team_id": normalized_team_id,
        "reason": reason,
        "paused_watchers": paused["watchers"],
        "paused_schedules": paused["schedules"],
    })
    return paused


def pause_team_watchers(conn, team_id: str, *, reason: str = "team_archived") -> int:
    return pause_team_watchers_and_schedules(conn, team_id, reason=reason)["watchers"]


def clear_project_membership(conn, project_id: str) -> int:
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return 0
    result = conn.execute(
        "UPDATE watchers SET project_id = '', updated = ? WHERE project_id = ?",
        (_utc_now(), normalized_project_id),
    )
    watcher_count = int(getattr(result, "rowcount", 0) or 0)
    if watcher_count:
        log.info("WATCHER_PROJECT_MEMBERSHIP_CLEARED", extra={
            "project_id": normalized_project_id,
            "watcher_count": watcher_count,
        })
    return watcher_count


def failure_disable_threshold() -> int:
    return WATCHER_FAILURE_DISABLE_THRESHOLD
