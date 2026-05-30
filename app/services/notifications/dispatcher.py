"""Notification event enqueue and delivery helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import logging
import uuid
from typing import Any, Iterable

from core import database
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.notifications import notification_cfg
from services.notifications.channels import register_builtin_channels
from services.notifications.base import channel_class_for_kind
from services.notifications.models import (
    STATUS_DEAD,
    STATUS_PENDING,
    STATUS_RETRY_WAIT,
    STATUS_SENT,
    TRIGGERS,
    ChannelResult,
    NotificationChannel,
    NotificationEvent,
)

log = logging.getLogger("shell")

CHANNEL_DELIVERY_LIMIT_PER_MINUTE = 10
CLAIM_LEASE_SECONDS = 300
MAX_ATTEMPTS = 6
RETRY_MAX_AGE_HOURS = 24


def _retry_cfg() -> dict[str, Any]:
    cfg = notification_cfg().get("retry", {})
    return cfg if isinstance(cfg, dict) else {}


def _events_cfg() -> dict[str, Any]:
    cfg = notification_cfg().get("events", {})
    return cfg if isinstance(cfg, dict) else {}


def _delivery_rate_limit_per_minute() -> int:
    return max(1, int(notification_cfg().get("delivery_rate_per_minute") or CHANNEL_DELIVERY_LIMIT_PER_MINUTE))


def _do_not_disturb() -> bool:
    return bool(notification_cfg().get("do_not_disturb"))


def _max_attempts() -> int:
    return max(1, int(_retry_cfg().get("max_attempts") or MAX_ATTEMPTS))


def _retry_max_age_hours() -> int:
    return max(1, int(_retry_cfg().get("max_age_hours") or RETRY_MAX_AGE_HOURS))


def _events_retention_days() -> int:
    raw = _events_cfg().get("retention_days")
    if raw in ("", None):
        return 30
    return max(0, int(raw))


def _base_retry_delay_seconds() -> int:
    return max(1, int(_retry_cfg().get("base_delay_seconds") or 30))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _json_param(value: Any) -> Any:
    return dialect_for_backend(database.DB_BACKEND).json_param(value)


def _event_id() -> str:
    return f"nte_{uuid.uuid4().hex}"


def _normalize_trigger(trigger: str) -> str:
    normalized = str(trigger or "").strip()
    if normalized not in TRIGGERS:
        supported = ", ".join(sorted(TRIGGERS))
        raise ValueError(f"unsupported notification trigger {trigger!r}; expected one of: {supported}")
    return normalized


def _normalize_payload(trigger: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    normalized.setdefault("trigger", trigger)
    normalized.setdefault("occurred_at", _utc_now())
    return normalized


@contextmanager
def _managed_connection(conn=None):
    if conn is not None:
        yield conn, False
        return
    with database.db_connect() as opened:
        yield opened, True


def _channel_rows_for_trigger(
    conn,
    session_token: str,
    trigger: str,
    *,
    team_id: str = "",
    channel_ids: Iterable[str] | None = None,
    include_muted: bool = False,
) -> list[Any]:
    selected_channel_ids = {str(channel_id) for channel_id in channel_ids or () if str(channel_id or "").strip()}
    if team_id:
        owner_sql = "team_id = ?"
        owner_params = (team_id,)
    else:
        owner_sql = "(team_id IS NULL OR team_id = '') AND session_token = ?"
        owner_params = (session_token,)
    rows = conn.execute(
        "SELECT id, session_token, team_id, kind, label, secrets_json, config_json, triggers_json, "
        "muted, created, updated "
        f"FROM notification_channels WHERE {owner_sql} ORDER BY lower(label) ASC, created ASC, id ASC",  # nosec
        owner_params,
    ).fetchall()
    channels = []
    for row in rows:
        if selected_channel_ids and str(row["id"]) not in selected_channel_ids:
            continue
        channel = NotificationChannel.from_row(row)
        if channel.muted and not include_muted:
            continue
        if trigger in channel.triggers:
            channels.append(row)
    return channels


def enqueue(
    trigger: str,
    payload: dict[str, Any],
    session_token: str,
    *,
    conn=None,
    dispatch_sync: bool = False,
    run_id: str | None = None,
    channel_ids: Iterable[str] | None = None,
    include_muted: bool = False,
    team_id: str = "",
) -> list[str]:
    """Queue one notification event for every matching channel."""
    normalized_trigger = _normalize_trigger(trigger)
    event_payload = _normalize_payload(normalized_trigger, payload)
    now = _utc_now()
    queued_ids: list[str] = []
    with _managed_connection(conn) as (active_conn, owns_conn):
        for channel_row in _channel_rows_for_trigger(
            active_conn,
            session_token,
            normalized_trigger,
            team_id=team_id,
            channel_ids=channel_ids,
            include_muted=include_muted,
        ):
            event_id = _event_id()
            queued_ids.append(event_id)
            active_conn.execute(
                "INSERT INTO notification_events "
                "(id, session_token, team_id, channel_id, trigger, payload_json, status, attempts, "
                "next_attempt_at, last_attempt_at, last_error, run_id, created, dead_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    session_token,
                    team_id,
                    channel_row["id"],
                    normalized_trigger,
                    _json_param(event_payload),
                    STATUS_PENDING,
                    0,
                    "",
                    "",
                    "",
                    run_id or str(event_payload.get("run_id") or ""),
                    now,
                    "",
                ),
            )
        if dispatch_sync and queued_ids:
            dispatch_due_events(
                conn=active_conn,
                event_ids=queued_ids,
                include_muted_channel_ids=channel_ids if include_muted else None,
            )
        if owns_conn:
            active_conn.commit()
    log.info(
        "NOTIFICATION_ENQUEUED",
        extra={
            "trigger": normalized_trigger,
            "queued": len(queued_ids),
            "run_id": run_id or str(event_payload.get("run_id") or ""),
            "session": get_log_session_id(session_token),
            "team_id": team_id,
        },
    )
    return queued_ids


def _where_ids(column: str, values: Iterable[str]) -> tuple[str, list[str]]:
    ids = [str(value) for value in values if value]
    if not ids:
        return "1 = 0", []
    placeholders = ", ".join("?" for _ in ids)
    return f"{column} IN ({placeholders})", ids


def _due_event_rows(conn, *, limit: int, event_ids: list[str] | None, now: str) -> list[Any]:
    if event_ids is not None:
        where_sql, params = _where_ids("id", event_ids)
        return conn.execute(
            "SELECT id, session_token, team_id, channel_id, trigger, payload_json, status, attempts, "
            "next_attempt_at, last_attempt_at, last_error, run_id, created, dead_at "
            "FROM notification_events "
            f"WHERE {where_sql} AND status IN (?, ?) "  # nosec
            "AND (next_attempt_at = '' OR next_attempt_at <= ?) "
            "ORDER BY created ASC LIMIT ?",
            [*params, STATUS_PENDING, STATUS_RETRY_WAIT, now, int(limit)],
        ).fetchall()
    return conn.execute(
        "SELECT id, session_token, team_id, channel_id, trigger, payload_json, status, attempts, "
        "next_attempt_at, last_attempt_at, last_error, run_id, created, dead_at "
        "FROM notification_events WHERE status IN (?, ?) "
        "AND (next_attempt_at = '' OR next_attempt_at <= ?) "
        "ORDER BY created ASC LIMIT ?",
        (STATUS_PENDING, STATUS_RETRY_WAIT, now, int(limit)),
    ).fetchall()


def _claim_event(conn, event_id: str, *, now: str) -> bool:
    lease_until = (datetime.fromisoformat(now) + timedelta(seconds=CLAIM_LEASE_SECONDS)).isoformat()
    cur = conn.execute(
        "UPDATE notification_events "
        "SET status = ?, last_attempt_at = ?, next_attempt_at = ? "
        "WHERE id = ? AND status IN (?, ?) "
        "AND (next_attempt_at = '' OR next_attempt_at <= ?)",
        (STATUS_RETRY_WAIT, now, lease_until, event_id, STATUS_PENDING, STATUS_RETRY_WAIT, now),
    )
    return int(getattr(cur, "rowcount", 0) or 0) == 1


def _channel_sends_this_minute(conn, channel_id: str, *, now: str, exclude_event_id: str = "") -> int:
    minute_start = (datetime.fromisoformat(now) - timedelta(seconds=60)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM notification_events "
        "WHERE channel_id = ? AND id <> ? AND status IN (?, ?, ?) AND attempts > ? AND last_attempt_at >= ?",
        (channel_id, str(exclude_event_id or ""), STATUS_SENT, STATUS_RETRY_WAIT, STATUS_DEAD, 0, minute_start),
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _load_channel(conn, channel_id: str) -> NotificationChannel | None:
    row = conn.execute(
        "SELECT id, session_token, team_id, kind, label, secrets_json, config_json, triggers_json, muted, created, updated "
        "FROM notification_channels WHERE id = ?",
        (channel_id,),
    ).fetchone()
    if row is None:
        return None
    return NotificationChannel.from_row(row)


def _mark_sent(conn, event: NotificationEvent, now: str) -> None:
    conn.execute(
        "UPDATE notification_events "
        "SET status = ?, attempts = ?, last_attempt_at = ?, next_attempt_at = '', last_error = '' "
        "WHERE id = ?",
        (STATUS_SENT, event.attempts + 1, now, event.id),
    )
    log.info(
        "NOTIFICATION_DISPATCHED",
        extra={
            "event_id": event.id,
            "channel_id": event.channel_id,
            "trigger": event.trigger,
            "session": get_log_session_id(event.session_token),
        },
    )


def _retry_delay_seconds(attempts: int) -> int:
    return min(3600, 2 ** max(0, int(attempts)) * _base_retry_delay_seconds())


def _mark_failed(conn, event: NotificationEvent, result: ChannelResult, now: str) -> None:
    attempts = event.attempts + 1
    created_at = _parse_time(event.created)
    age_expired = bool(created_at and datetime.fromisoformat(now) - created_at > timedelta(hours=_retry_max_age_hours()))
    should_retry = result.retryable and attempts < _max_attempts() and not age_expired
    if should_retry:
        next_attempt = (datetime.fromisoformat(now) + timedelta(seconds=_retry_delay_seconds(attempts))).isoformat()
        conn.execute(
            "UPDATE notification_events "
            "SET status = ?, attempts = ?, last_attempt_at = ?, next_attempt_at = ?, last_error = ? "
            "WHERE id = ?",
            (STATUS_RETRY_WAIT, attempts, now, next_attempt, result.error[:500], event.id),
        )
        log.warning(
            "NOTIFICATION_RETRIED",
            extra={
                "event_id": event.id,
                "channel_id": event.channel_id,
                "trigger": event.trigger,
                "session": get_log_session_id(event.session_token),
                "attempts": attempts,
                "next_attempt_at": next_attempt,
                "retryable": result.retryable,
                "age_expired": age_expired,
                "max_attempts": _max_attempts(),
                "error": result.error[:200],
            },
        )
        return
    conn.execute(
        "UPDATE notification_events "
        "SET status = ?, attempts = ?, last_attempt_at = ?, next_attempt_at = '', "
        "last_error = ?, dead_at = ? WHERE id = ?",
        (STATUS_DEAD, attempts, now, result.error[:500], now, event.id),
    )
    log.warning(
        "NOTIFICATION_DELIVERY_FAILED",
        extra={
            "event_id": event.id,
            "channel_id": event.channel_id,
            "trigger": event.trigger,
            "session": get_log_session_id(event.session_token),
            "attempts": attempts,
            "retryable": result.retryable,
            "age_expired": age_expired,
            "max_attempts": _max_attempts(),
            "error": result.error[:200],
        },
    )


def _defer_event(conn, event: NotificationEvent, now: str, *, reason: str, delay_seconds: int) -> None:
    next_attempt = (datetime.fromisoformat(now) + timedelta(seconds=max(1, int(delay_seconds)))).isoformat()
    conn.execute(
        "UPDATE notification_events "
        "SET status = ?, last_attempt_at = ?, next_attempt_at = ?, last_error = ? "
        "WHERE id = ?",
        (STATUS_RETRY_WAIT, now, next_attempt, reason[:500], event.id),
    )
    log.info(
        "NOTIFICATION_DEFERRED",
        extra={
            "event_id": event.id,
            "channel_id": event.channel_id,
            "trigger": event.trigger,
            "session": get_log_session_id(event.session_token),
            "reason": reason[:80],
        },
    )


def _dispatch_event(conn, row: Any, *, now: str, include_muted_channel_ids: set[str] | None = None) -> bool:
    event = NotificationEvent.from_row(row)
    channel = _load_channel(conn, event.channel_id)
    muted_allowed = channel is not None and channel.id in (include_muted_channel_ids or set())
    if channel is None or (channel.muted and not muted_allowed):
        _mark_failed(conn, event, ChannelResult.terminal("notification channel is unavailable"), now)
        return False
    if _do_not_disturb():
        _defer_event(
            conn,
            event,
            now,
            reason="notification do-not-disturb is active",
            delay_seconds=_base_retry_delay_seconds(),
        )
        return False
    if _channel_sends_this_minute(conn, channel.id, now=now, exclude_event_id=event.id) >= _delivery_rate_limit_per_minute():
        _defer_event(
            conn,
            event,
            now,
            reason="notification channel rate limit reached",
            delay_seconds=60,
        )
        return False
    channel_cls = channel_class_for_kind(channel.kind)
    if channel_cls is None:
        log.warning(
            "NOTIFICATION_CHANNEL_REGISTRY_MISS",
            extra={"event_id": event.id, "channel_id": event.channel_id, "kind": channel.kind},
        )
        register_builtin_channels()
        channel_cls = channel_class_for_kind(channel.kind)
    if channel_cls is None:
        _mark_failed(conn, event, ChannelResult.terminal(f"notification channel {channel.kind!r} is not registered"), now)
        return False
    try:
        result = channel_cls(channel).send(event.payload)
    except Exception as exc:  # noqa: BLE001
        log.error(
            "NOTIFICATION_CHANNEL_SEND_EXCEPTION",
            exc_info=True,
            extra={
                "event_id": event.id,
                "channel_id": event.channel_id,
                "kind": channel.kind,
                "trigger": event.trigger,
            },
        )
        result = ChannelResult.retry(str(exc))
    if result.ok:
        _mark_sent(conn, event, now)
        return True
    _mark_failed(conn, event, result, now)
    return False


def dispatch_due_events(
    conn=None,
    *,
    limit: int = 100,
    event_ids: list[str] | None = None,
    include_muted_channel_ids: Iterable[str] | None = None,
) -> int:
    """Deliver due notification events and return the number sent successfully."""
    now = _utc_now()
    delivered = 0
    muted_channel_ids = {
        str(channel_id)
        for channel_id in include_muted_channel_ids or ()
        if str(channel_id or "").strip()
    }
    with _managed_connection(conn) as (active_conn, owns_conn):
        for row in _due_event_rows(active_conn, limit=limit, event_ids=event_ids, now=now):
            if not _claim_event(active_conn, row["id"], now=now):
                continue
            if _dispatch_event(active_conn, row, now=now, include_muted_channel_ids=muted_channel_ids):
                delivered += 1
        if owns_conn:
            active_conn.commit()
    return delivered


def prune_sent_events(conn=None, *, now: str | None = None) -> int:
    """Delete old sent notification audit rows and return the number pruned."""
    retention_days = _events_retention_days()
    if retention_days <= 0:
        return 0
    current = now or _utc_now()
    cutoff = (datetime.fromisoformat(current) - timedelta(days=retention_days)).isoformat()
    with _managed_connection(conn) as (active_conn, owns_conn):
        cur = active_conn.execute(
            "DELETE FROM notification_events WHERE status = ? AND created < ?",
            (STATUS_SENT, cutoff),
        )
        pruned = int(getattr(cur, "rowcount", 0) or 0)
        if owns_conn:
            active_conn.commit()
    if pruned:
        log.info("NOTIFICATION_EVENTS_PRUNED", extra={"count": pruned, "retention_days": retention_days})
    return pruned


def payload_from_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        raw = row.get("payload_json")
    else:
        raw = row["payload_json"]
    if isinstance(raw, dict):
        return raw
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}
