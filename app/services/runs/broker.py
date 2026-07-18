# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Run broker event storage and replay helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
import json
import logging
import threading
import time
from typing import Any, cast

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from config import resolve_effective_cfg
from core import process
from services.runs.output_model import (
    LINE_EVENT_SCHEMA_VERSION,
    LineEvent,
    LineKind,
    from_wire,
    line_event_from_legacy,
    to_wire,
)

log = logging.getLogger("shell")

TERMINAL_EVENT_TYPES = {"exit", "error"}
REPLAY_TRIM_NOTICE = "[live replay starts here; earlier output was trimmed due to size]"
LINE_BOUNDED_REPLAY_TYPES = {"output", "output_batch", "notice"}
LINE_EVENT_TYPES = {"output", "notice"}
REDIS_STREAM_DISCONNECT_ERRORS = (RedisConnectionError, RedisTimeoutError)
BROKER_RESERVED_PAYLOAD_KEYS = {"type", "event", "created_at", "event_id"}
SCHEMA_EVENT_PAYLOAD = {
    "type": "schema",
    "event": "schema",
    "v": LINE_EVENT_SCHEMA_VERSION,
    "kind": "line_event",
}


def _redis_client() -> Any | None:
    return process.redis_client


def _stream_key(run_id: str) -> str:
    return f"runstream:{run_id}"


def _is_redis_idle_timeout_error(exc: BaseException) -> bool:
    if isinstance(exc, RedisTimeoutError):
        return True
    if isinstance(exc, RedisConnectionError):
        message = str(exc).lower()
        return "timeout reading" in message or "timed out" in message
    return False


def _schema_sse() -> str:
    return f"event: schema\ndata: {json.dumps(SCHEMA_EVENT_PAYLOAD)}\n\n"


def _line_event_payload(event_type: str, payload: dict[str, Any] | LineEvent | None = None) -> dict[str, Any]:
    if isinstance(payload, LineEvent):
        return to_wire(payload)
    if not isinstance(payload, dict) or "text" not in payload:
        return dict(payload or {})

    base = dict(payload)
    if event_type == "notice" and not base.get("kind") and not base.get("cls"):
        event = line_event_from_legacy(base.get("text", ""), kind=LineKind.notice)
    else:
        event = from_wire(base, _unknown_line_event_collector(str(base.get("run_id") or "")))
    data = to_wire(event)
    for key, value in base.items():
        if key not in data and key not in BROKER_RESERVED_PAYLOAD_KEYS:
            data[key] = value
    return data


def _unknown_line_event_collector(run_id: str):
    seen: set[tuple[str, str]] = set()

    def collect(family: str, value: str) -> None:
        key = (family, value)
        if key in seen:
            return
        seen.add(key)
        log.warning("LINE_EVENT_UNKNOWN_VALUE", extra={"run_id": run_id, "family": family, "value": value})

    return collect


def _event_payload(event_type: str, payload: dict[str, Any] | LineEvent | None = None) -> dict[str, Any]:
    data: dict[str, Any]
    if event_type in LINE_EVENT_TYPES:
        data = _line_event_payload(event_type, payload)
    elif isinstance(payload, LineEvent):
        data = to_wire(payload)
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        data = {}
    data["type"] = str(event_type)
    data.setdefault("created_at", time.time())
    return data


def _event_size(event: "BrokerEvent") -> int:
    return len(json.dumps(event.payload, separators=(",", ":")).encode("utf-8"))


def _coerce_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _is_trim_notice(event: "BrokerEvent") -> bool:
    return (
        event.payload.get("type") == "notice"
        and event.payload.get("text") == REPLAY_TRIM_NOTICE
    )


def _line_bounded_replay_event_count(events: list["BrokerEvent"]) -> int:
    count = 0
    for event in events:
        count += _line_bounded_replay_event_count_for_event(event)
    return count


def _line_bounded_replay_event_count_for_event(event: "BrokerEvent") -> int:
    event_type = event.payload.get("type")
    if event_type not in LINE_BOUNDED_REPLAY_TYPES or _is_trim_notice(event):
        return 0
    if event_type == "output_batch":
        lines = event.payload.get("lines")
        return len(lines) if isinstance(lines, list) else 1
    return 1


def _batch_event_with_last_lines(event: "BrokerEvent", count: int) -> "BrokerEvent":
    lines = event.payload.get("lines")
    if event.payload.get("type") != "output_batch" or not isinstance(lines, list):
        return event
    payload = dict(event.payload)
    payload["lines"] = lines[-max(0, int(count)):]
    return BrokerEvent(event.event_id, payload)


def _make_trim_notice_event() -> "BrokerEvent":
    return BrokerEvent(
        f"{int(time.time() * 1000)}-trim",
        _event_payload(
            "notice",
            line_event_from_legacy(REPLAY_TRIM_NOTICE, kind=LineKind.notice),
        ),
    )


def _is_resumable_event(event: "BrokerEvent") -> bool:
    return not _is_trim_notice(event)


def _is_valid_stream_event_id(event_id: str) -> bool:
    try:
        left, right = str(event_id).split("-", 1)
        int(left)
        int(right)
    except (TypeError, ValueError):
        return False
    return True


def _normalize_resume_event_id(event_id: str | None) -> str:
    if _is_beginning_event_id(event_id or ""):
        return "0-0"
    return str(event_id) if _is_valid_stream_event_id(str(event_id)) else "0-0"


def _is_beginning_event_id(event_id: str) -> bool:
    return not event_id or event_id in ("-", "0-0")


def _bounded_replay_events(events: list["BrokerEvent"]) -> list["BrokerEvent"]:
    max_events = _max_replay_events()
    if max_events <= 0 or _line_bounded_replay_event_count(events) <= max_events:
        return events

    bounded: list[BrokerEvent] = []
    remaining = max_events
    for event in reversed(events):
        line_count = _line_bounded_replay_event_count_for_event(event)
        if line_count:
            if remaining <= 0:
                continue
            if line_count > remaining:
                bounded.append(_batch_event_with_last_lines(event, remaining))
                remaining = 0
                continue
            remaining -= line_count
        bounded.append(event)
    bounded.reverse()
    if not bounded or not _is_trim_notice(bounded[0]):
        bounded.insert(0, _make_trim_notice_event())
    return bounded


def _prepend_trim_notice(events: list["BrokerEvent"]) -> list["BrokerEvent"]:
    if events and _is_trim_notice(events[0]):
        return events
    return [_make_trim_notice_event()] + events


def _is_after(left: str, right: str) -> bool:
    if _is_beginning_event_id(right):
        return True
    try:
        left_ms, left_seq = [int(part) for part in str(left).split("-", 1)]
        right_ms, right_seq = [int(part) for part in str(right).split("-", 1)]
    except (TypeError, ValueError):
        return False
    return (left_ms, left_seq) > (right_ms, right_seq)


@dataclass(frozen=True)
class BrokerEvent:
    event_id: str
    payload: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        body = dict(self.payload)
        if _is_resumable_event(self):
            body["event_id"] = self.event_id
        return body

    def as_sse(self) -> str:
        body = self.as_payload()
        if _is_resumable_event(self):
            return f"id: {self.event_id}\ndata: {json.dumps(body)}\n\n"
        return f"data: {json.dumps(body)}\n\n"


class _MemoryRunBrokerStore:
    def __init__(self) -> None:
        self._lock = threading.Condition()
        self._events: dict[str, list[BrokerEvent]] = defaultdict(list)
        self._bytes: dict[str, int] = defaultdict(int)
        self._closed: set[str] = set()
        self._expires_at: dict[str, float] = {}

    def publish(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | LineEvent | None = None,
    ) -> BrokerEvent:
        with self._lock:
            self._purge_locked(run_id)
            events = self._events[run_id]
            event_id = f"{int(time.time() * 1000)}-{len(events)}"
            event = BrokerEvent(event_id, _event_payload(event_type, payload))
            events.append(event)
            self._bytes[run_id] += _event_size(event)
            self._trim_locked(run_id)
            if event_type in TERMINAL_EVENT_TYPES:
                self._closed.add(run_id)
                self._expires_at[run_id] = time.time() + _completed_ttl()
            else:
                self._expires_at[run_id] = time.time() + _active_ttl()
            self._lock.notify_all()
            return event

    def events_after(
        self,
        run_id: str,
        after_id: str = "0-0",
        limit: int = 100,
    ) -> list[BrokerEvent]:
        after_id = _normalize_resume_event_id(after_id)
        with self._lock:
            self._purge_locked(run_id)
            return self._events_after_locked(run_id, after_id, limit)

    def wait_after(
        self,
        run_id: str,
        after_id: str = "0-0",
        timeout: float = 15.0,
    ) -> list[BrokerEvent]:
        after_id = _normalize_resume_event_id(after_id)
        deadline = time.time() + max(0.0, float(timeout or 0))
        with self._lock:
            while True:
                self._purge_locked(run_id)
                rows = self._events_after_locked(run_id, after_id, limit=100)
                if rows or run_id in self._closed or time.time() >= deadline:
                    return rows
                self._lock.wait(timeout=max(0.0, deadline - time.time()))

    def replay(self, run_id: str) -> list[BrokerEvent]:
        with self._lock:
            self._purge_locked(run_id)
            return _bounded_replay_events(list(self._events.get(run_id, [])))

    def _events_after_locked(
        self,
        run_id: str,
        after_id: str = "0-0",
        limit: int = 100,
    ) -> list[BrokerEvent]:
        after_id = _normalize_resume_event_id(after_id)
        rows = [event for event in self._events.get(run_id, []) if _is_after(event.event_id, after_id)]
        return rows[: max(0, int(limit or 0))]

    def _purge_locked(self, run_id: str) -> None:
        expires_at = self._expires_at.get(run_id)
        if expires_at is None or expires_at > time.time():
            return
        self._events.pop(run_id, None)
        self._bytes.pop(run_id, None)
        self._closed.discard(run_id)
        self._expires_at.pop(run_id, None)

    def _trim_locked(self, run_id: str) -> None:
        max_bytes = _max_replay_bytes()
        events = self._events.get(run_id, [])
        trimmed = False
        while max_bytes > 0 and len(events) > 1 and self._bytes[run_id] > max_bytes:
            removed = events.pop(0)
            self._bytes[run_id] -= _event_size(removed)
            trimmed = True

        max_events = _max_replay_events()
        while max_events > 0 and len(events) > 1 and _line_bounded_replay_event_count(events) > max_events:
            remove_index = 1 if events and _is_trim_notice(events[0]) else 0
            removed = events[remove_index]
            lines = removed.payload.get("lines")
            if removed.payload.get("type") == "output_batch" and isinstance(lines, list) and len(lines) > 1:
                original_size = _event_size(removed)
                payload = dict(removed.payload)
                payload["lines"] = lines[1:]
                trimmed_event = BrokerEvent(removed.event_id, payload)
                events[remove_index] = trimmed_event
                self._bytes[run_id] -= original_size - _event_size(trimmed_event)
            else:
                removed = events.pop(remove_index)
                self._bytes[run_id] -= _event_size(removed)
            trimmed = True

        already_marked = bool(events and _is_trim_notice(events[0]))
        if trimmed and not already_marked:
            notice = _make_trim_notice_event()
            events.insert(0, notice)
            self._bytes[run_id] += _event_size(notice)
            log.warning("BROKER_REPLAY_TRIMMED", extra={
                "run_id": run_id,
                "mode": broker_mode(),
                "max_events": _max_replay_events(),
                "max_bytes": _max_replay_bytes(),
                "remaining_events": len(events),
            })

    def snapshot(self) -> dict[str, int]:
        """Diagnostic snapshot of in-memory broker state. Read-only — does
        not purge or trim. Used by `/diag` to surface fallback usage when
        Redis is not configured."""
        with self._lock:
            now = time.time()
            active = 0
            closed = 0
            expired_pending_purge = 0
            total_events = 0
            total_bytes = 0
            for run_id, events in self._events.items():
                total_events += len(events)
                total_bytes += self._bytes.get(run_id, 0)
                if run_id in self._closed:
                    closed += 1
                else:
                    active += 1
                expires_at = self._expires_at.get(run_id)
                if expires_at is not None and expires_at <= now:
                    expired_pending_purge += 1
            return {
                "streams":               len(self._events),
                "active":                active,
                "closed":                closed,
                "expired_pending_purge": expired_pending_purge,
                "events":                total_events,
                "bytes":                 total_bytes,
            }


class _RedisRunBrokerStore:
    def publish(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | LineEvent | None = None,
    ) -> BrokerEvent:
        redis_client = _redis_client()
        if not redis_client:
            raise RuntimeError("Redis is not available for run broker events")
        key = _stream_key(run_id)
        data = _event_payload(event_type, payload)
        event_id = _coerce_text(redis_client.xadd(key, {"payload": json.dumps(data, separators=(",", ":"))}))
        redis_client.expire(key, _completed_ttl() if event_type in TERMINAL_EVENT_TYPES else _active_ttl())
        _trim_redis_stream(key)
        return BrokerEvent(event_id, data)

    def events_after(
        self,
        run_id: str,
        after_id: str = "0-0",
        limit: int = 100,
    ) -> list[BrokerEvent]:
        redis_client = _redis_client()
        if not redis_client:
            return []
        after_id = _normalize_resume_event_id(after_id)
        rows = cast(
            list[tuple[Any, dict[str, Any]]],
            redis_client.xrange(_stream_key(run_id), min=after_id, count=max(0, int(limit or 0))),
        )
        events: list[BrokerEvent] = []
        for event_id, fields in rows:
            event_id = _coerce_text(event_id)
            if not _is_after(event_id, after_id or "0-0"):
                continue
            payload = _decode_payload(fields, run_id=run_id, event_id=event_id)
            if payload is not None:
                events.append(BrokerEvent(event_id, payload))
        return events

    def wait_after(
        self,
        run_id: str,
        after_id: str = "0-0",
        timeout: float = 15.0,
    ) -> list[BrokerEvent]:
        redis_client = _redis_client()
        if not redis_client:
            return []
        after_id = _normalize_resume_event_id(after_id)
        try:
            rows = cast(
                list[tuple[Any, list[tuple[Any, dict[str, Any]]]]],
                redis_client.xread(
                    {_stream_key(run_id): after_id},
                    count=100,
                    block=max(1, int(float(timeout or 0) * 1000)),
                ),
            )
        except (RedisTimeoutError, RedisConnectionError) as exc:
            if _is_redis_idle_timeout_error(exc):
                return []
            raise
        events: list[BrokerEvent] = []
        for _key, stream_rows in rows or []:
            for event_id, fields in stream_rows:
                payload = _decode_payload(fields, run_id=run_id, event_id=_coerce_text(event_id))
                if payload is not None:
                    events.append(BrokerEvent(_coerce_text(event_id), payload))
        return events

    def replay(self, run_id: str) -> list[BrokerEvent]:
        redis_client = _redis_client()
        if not redis_client:
            return []
        key = _stream_key(run_id)
        fetch_count = _replay_fetch_count()
        rows = cast(
            list[tuple[Any, dict[str, Any]]],
            redis_client.xrevrange(
                key,
                max="+",
                min="-",
                count=fetch_count,
            ),
        )
        events: list[BrokerEvent] = []
        for event_id, fields in reversed(rows or []):
            payload = _decode_payload(fields, run_id=run_id, event_id=_coerce_text(event_id))
            if payload is not None:
                events.append(BrokerEvent(_coerce_text(event_id), payload))
        bounded = _bounded_replay_events(events)
        try:
            stream_length = int(cast(Any, redis_client.xlen(key)))
        except (TypeError, ValueError, AttributeError):
            stream_length = len(rows or [])
        if stream_length > len(rows or []):
            log.warning("BROKER_REPLAY_TRIMMED", extra={
                "run_id": run_id,
                "mode": broker_mode(),
                "max_events": _max_replay_events(),
                "max_bytes": _max_replay_bytes(),
                "remaining_events": len(bounded),
            })
            return _prepend_trim_notice(bounded)
        return bounded


def _decode_payload(fields: object, *, run_id: str = "", event_id: str = "") -> dict[str, Any] | None:
    if not isinstance(fields, dict):
        log.warning("BROKER_PAYLOAD_DECODE_FAILED", extra={
            "run_id": run_id,
            "event_id": event_id,
            "reason": "invalid_fields",
        })
        return None
    raw = fields.get("payload")
    if raw is None:
        raw = fields.get(b"payload")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        log.warning("BROKER_PAYLOAD_DECODE_FAILED", extra={
            "run_id": run_id,
            "event_id": event_id,
            "reason": "missing_payload",
        })
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("BROKER_PAYLOAD_DECODE_FAILED", extra={
            "run_id": run_id,
            "event_id": event_id,
            "reason": "json_decode",
            "error": str(exc),
        })
        return None
    if not isinstance(payload, dict):
        log.warning("BROKER_PAYLOAD_DECODE_FAILED", extra={
            "run_id": run_id,
            "event_id": event_id,
            "reason": "invalid_payload",
        })
        return None
    return payload


def _active_ttl() -> int:
    return max(1, int(resolve_effective_cfg().get("run_broker_active_stream_ttl_seconds", 14400) or 14400))


def _completed_ttl() -> int:
    return max(1, int(resolve_effective_cfg().get("run_broker_completed_stream_ttl_seconds", 3600) or 3600))


def _max_replay_bytes() -> int:
    return max(0, int(resolve_effective_cfg().get("run_broker_max_replay_bytes", 10485760) or 0))


def _max_replay_events() -> int:
    return max(0, int(resolve_effective_cfg().get("max_output_lines", 5000) or 0))


def _replay_fetch_count() -> int:
    max_events = _max_replay_events()
    if max_events <= 0:
        return 10000
    return max(100, max_events + 100)


def _redis_stream_maxlen() -> int:
    return max(1000, _replay_fetch_count() * 2)


def _trim_redis_stream(key: str) -> None:
    redis_client = _redis_client()
    if not redis_client:
        return
    try:
        redis_client.xtrim(key, maxlen=_redis_stream_maxlen(), approximate=True)
    except AttributeError:
        log.warning("BROKER_REDIS_TRIM_UNAVAILABLE", extra={
            "key": key,
            "reason": "missing_xtrim",
        })
        return
    except TypeError:
        log.debug("BROKER_REDIS_TRIM_RETRY", extra={
            "key": key,
            "maxlen": _redis_stream_maxlen(),
            "reason": "signature",
        })
        redis_client.xtrim(key, _redis_stream_maxlen(), approximate=True)


def broker_available() -> bool:
    active_cfg = resolve_effective_cfg()
    return bool(active_cfg.get("run_broker_enabled", True)) and (
        not active_cfg.get("run_broker_require_redis", True) or bool(_redis_client())
    )


def broker_unavailable_reason() -> str:
    active_cfg = resolve_effective_cfg()
    if not active_cfg.get("run_broker_enabled", True):
        return "Run broker is disabled by configuration."
    if active_cfg.get("run_broker_require_redis", True) and not _redis_client():
        return "Run broker requires Redis, but Redis is not available."
    return ""


_memory_store = _MemoryRunBrokerStore()


def memory_store_snapshot() -> dict[str, int]:
    """Public accessor for the in-memory broker snapshot — used by `/diag`."""
    return _memory_store.snapshot()


def broker_mode() -> str:
    """`redis` when the configured Redis client is in use, `in_process` when
    the in-memory fallback is the active backend."""
    return "redis" if _redis_client() else "in_process"


def _store():
    if _redis_client():
        return _RedisRunBrokerStore()
    return _memory_store


def publish_run_event(run_id: str, event_type: str, payload: dict[str, Any] | LineEvent | None = None) -> BrokerEvent:
    from services import metrics as app_metrics  # noqa: PLC0415

    try:
        event = _store().publish(run_id, event_type, payload)
    except RuntimeError as exc:
        app_metrics.record_broker_publish_error("redis_unavailable")
        log.warning("BROKER_PUBLISH_FAILED", extra={
            "run_id": run_id,
            "event_type": event_type,
            "reason": "redis_unavailable",
            "error": str(exc),
        })
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        app_metrics.record_broker_publish_error("serialize")
        log.warning("BROKER_PUBLISH_FAILED", extra={
            "run_id": run_id,
            "event_type": event_type,
            "reason": "serialize",
            "error": str(exc),
        })
        raise
    except Exception as exc:
        app_metrics.record_broker_publish_error("unknown")
        log.warning("BROKER_PUBLISH_FAILED", extra={
            "run_id": run_id,
            "event_type": event_type,
            "reason": "unknown",
            "error": str(exc),
        })
        raise
    app_metrics.record_broker_event(event_type)
    return event


def get_run_events(run_id: str, after_id: str = "0-0", limit: int = 100) -> list[BrokerEvent]:
    return _store().events_after(run_id, after_id, limit)


def replay_run_events(run_id: str) -> list[BrokerEvent]:
    return _store().replay(run_id)


def stream_run_events(run_id: str, after_id: str = "0-0") -> Iterator[str]:
    from services import metrics as app_metrics  # noqa: PLC0415

    app_metrics.record_broker_subscriber_delta(1)
    current_id = _normalize_resume_event_id(after_id)
    yield _schema_sse()
    if not _is_beginning_event_id(current_id):
        log.debug("BROKER_STREAM_REATTACHED", extra={"run_id": run_id, "after_id": current_id})
    block_seconds = max(1.0, float(resolve_effective_cfg().get("run_broker_subscriber_block_seconds", 15) or 15))
    try:
        if _is_beginning_event_id(current_id):
            for event in replay_run_events(run_id):
                if _is_resumable_event(event):
                    current_id = event.event_id
                yield event.as_sse()
                if event.payload.get("type") in TERMINAL_EVENT_TYPES:
                    return
        while True:
            try:
                events = _store().wait_after(run_id, current_id, timeout=block_seconds)
            except (RedisTimeoutError, RedisConnectionError) as exc:
                if not _is_redis_idle_timeout_error(exc):
                    raise
                yield ": heartbeat\n\n"
                continue
            if not events:
                yield ": heartbeat\n\n"
                continue
            for event in events:
                if _is_resumable_event(event):
                    current_id = event.event_id
                yield event.as_sse()
                if event.payload.get("type") in TERMINAL_EVENT_TYPES:
                    return
    except REDIS_STREAM_DISCONNECT_ERRORS as exc:
        log.debug("BROKER_STREAM_CLIENT_GONE", extra={
            "run_id": run_id,
            "reason": str(exc),
        })
        return
    finally:
        app_metrics.record_broker_subscriber_delta(-1)
