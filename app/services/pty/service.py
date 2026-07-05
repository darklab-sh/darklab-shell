"""Constrained PTY lifecycle for interactive runs."""

from __future__ import annotations

import json
import logging
import os
import pty
import select
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, cast

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from config import CFG, SCANNER_PREFIX
from core.process import (
    active_run_claim_owner_transition,
    active_run_owned_by,
    active_run_register,
    active_run_remove,
    active_runs_for_team,
    active_runs_for_session,
    pid_pop,
    pid_register,
)
from services.pty import capture as pty_capture
from services.pty.capture import (
    PtyTerminalCapture as _BasePtyTerminalCapture,
    _terminal_history_line_limit,
)
from services.runs.broker import _is_redis_idle_timeout_error
from services.metrics_lazy import app_metrics
from services.pty.runtime import (
    KILL_BIN as KILL_BIN,
    SUDO_BIN as SUDO_BIN,
    bounded_dimension as _bounded_dimension,
    command_env as _command_env,
    prepare_child as _prepare_child,
    set_pty_size as _set_pty_size,
    terminate_run as _terminate_run,
)
from services.pty.snapshots import (
    pty_snapshot_payload_from_run as _pty_snapshot_payload_from_run,
)
from services.pty import state as pty_state
from services.pty.settings import (
    _PTY_BUFFER_LIMIT as _PTY_BUFFER_LIMIT,
    _PTY_CAPTURE_MAX_HISTORY_LINES as _PTY_CAPTURE_MAX_HISTORY_LINES,
    _PTY_CAPTURE_MIN_HISTORY_LINES as _PTY_CAPTURE_MIN_HISTORY_LINES,
    _PTY_INPUT_MAX_BYTES as _PTY_INPUT_MAX_BYTES,
    _PTY_SNAPSHOT_MAX_BYTES as _PTY_SNAPSHOT_MAX_BYTES,
    _PTY_SNAPSHOT_PUBLISH_BYTES as _PTY_SNAPSHOT_PUBLISH_BYTES,
    _coerce_non_negative_int as _coerce_non_negative_int,
    _pty_buffer_limit,
    _pty_control_poll_seconds,
    _pty_heartbeat_seconds,
    _pty_input_max_bytes,
    _pty_snapshot_min_publish_seconds,
    _pty_snapshot_publish_bytes,
    _pty_snapshot_publish_seconds,
    _pty_stream_fetch_count,
    _pty_stream_maxlen,
)
from services.pty.wire import (
    coerce_text as _coerce_text,
    control_key as _control_key,
    decode_payload as _decode_payload,
    json_payload_size as _json_payload_size,
    meta_key as _meta_key,
    normalize_event_id as _normalize_event_id,
    snapshot_key as _snapshot_key,
    stream_key as _stream_key,
)

log = logging.getLogger("shell")


redis_client = pty_state.RedisClientProxy()

_active_ttl = pty_state.active_ttl
_completed_ttl = pty_state.completed_ttl
_meta_matches_scope = pty_state.meta_matches_scope


def _store_pty_meta(run: "PtyRun", *, closed: bool = False) -> None:
    pty_state.store_pty_meta(run, redis_client=redis_client, closed=closed)


def _safe_store_pty_meta(run: "PtyRun", *, closed: bool = False) -> bool:
    return pty_state.safe_store_pty_meta(run, redis_client=redis_client, closed=closed)


def _delete_pty_meta(run_id: str) -> None:
    pty_state.delete_pty_meta(run_id, redis_client=redis_client)


def _delete_pty_runtime_state(run_id: str, *, include_stream: bool = False) -> None:
    pty_state.delete_pty_runtime_state(
        run_id,
        redis_client=redis_client,
        include_stream=include_stream,
    )


def _load_pty_snapshot(run_id: str, session_id: str, team_id: str = "") -> dict[str, Any] | None:
    return pty_state.load_pty_snapshot(
        run_id,
        session_id,
        team_id,
        redis_client=redis_client,
    )
pyte = pty_capture.pyte

_PTY_STALE_MESSAGE = "PTY run is no longer active"

class PtyDependencyError(RuntimeError):
    """Raised when an enabled PTY run cannot meet required dependencies."""


class PtyTerminalCapture(_BasePtyTerminalCapture):
    """Compatibility wrapper for tests that monkeypatch pty_service.pyte."""

    def __init__(self, rows: int, cols: int, history_lines: int):
        pty_capture.pyte = pyte
        super().__init__(rows, cols, history_lines)


@dataclass
class PtyEvent:
    seq: int
    type: str
    payload: dict[str, Any]


@dataclass
class PtyRun:
    run_id: str
    session_id: str
    team_id: str
    command: str
    argv: list[str]
    started: str
    master_fd: int
    proc: subprocess.Popen
    rows: int
    cols: int
    allow_input: bool
    max_runtime_seconds: int
    brokered: bool
    terminal_capture: PtyTerminalCapture
    owner_tab_id: str = ""
    completion_callback: Callable[["PtyRun", str, int, Sequence[dict[str, object]]], dict[str, object]] | None = None
    events: deque[PtyEvent] = field(default_factory=lambda: deque(maxlen=_pty_buffer_limit()))
    seq: int = 0
    closed: bool = False
    exit_code: int | None = None
    control_event_id: str = "0-0"
    capture_event_id: str = "0-0"
    snapshot_published_event_id: str = "0-0"
    snapshot_pending_bytes: int = 0
    snapshot_last_published: float = 0.0
    snapshot_truncation_logged: bool = False
    snapshot_lock: threading.Lock = field(default_factory=threading.Lock)
    condition: threading.Condition = field(default_factory=threading.Condition)

    def append_event(self, event_type: str, payload: dict[str, Any] | None = None) -> str:
        body = dict(payload or {})
        if self.brokered:
            event_id = publish_pty_event(self.run_id, event_type, body)
            if event_type in {"exit", "error"}:
                _store_pty_meta(self, closed=True)
            return event_id
        with self.condition:
            self.seq += 1
            self.events.append(PtyEvent(self.seq, event_type, body))
            self.condition.notify_all()
            return str(self.seq)


_runs: dict[str, PtyRun] = {}
_runs_lock = threading.Lock()

# PTY lock order: acquire snapshot_lock before terminal_capture._lock when a
# snapshot needs both. Feed/resize paths use terminal_capture._lock only, and
# event delivery uses condition separately.


def pty_enabled() -> bool:
    return bool(CFG.get("interactive_pty_enabled", False))


def pty_worker_supported() -> bool:
    try:
        workers = int(os.environ.get("WEB_CONCURRENCY", "1") or "1")
    except ValueError:
        workers = 1
    return workers <= 1


def pty_broker_available() -> bool:
    return bool(redis_client) or pty_worker_supported()


def pty_broker_unavailable_reason() -> str:
    return "Interactive PTY mode requires Redis for multi-worker deployments or WEB_CONCURRENCY=1."


def _load_pty_meta(run_id: str) -> dict[str, Any] | None:
    if redis_client:
        raw = redis_client.get(_meta_key(run_id))
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return None
            return data if isinstance(data, dict) else None
    with _runs_lock:
        run = _runs.get(run_id)
    if not run:
        return None
    return {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "team_id": run.team_id,
        "command": run.command,
        "started": run.started,
        "rows": run.rows,
        "cols": run.cols,
        "closed": run.closed,
    }


def _load_pty_meta_for_scope(run_id: str, session_id: str, team_id: str = "") -> dict[str, Any] | None:
    meta = _load_pty_meta(run_id)
    if not meta or not _meta_matches_scope(meta, session_id, team_id):
        return None
    return meta


def _load_pty_meta_for_session(run_id: str, session_id: str) -> dict[str, Any] | None:
    return _load_pty_meta_for_scope(run_id, session_id, "")


def _active_pty_run_is_tracked(run_id: str, session_id: str, team_id: str = "") -> bool:
    with _runs_lock:
        run = _runs.get(run_id)
    run_meta = {"session_id": run.session_id, "team_id": run.team_id} if run else {}
    if run and _meta_matches_scope(run_meta, session_id, team_id) and not run.closed:
        return True
    try:
        active_runs = active_runs_for_team(team_id) if team_id else active_runs_for_session(session_id, team_id="")
    except Exception:
        log.warning("PTY_ACTIVE_RUN_CHECK_FAILED", exc_info=True, extra={
            "run_id": run_id,
            "session": session_id,
            "team_id": team_id,
        })
        return True
    return any(
        str(item.get("run_id", "")) == run_id
        and str(item.get("run_type", "command") or "command") == "pty"
        for item in active_runs
    )


def _prune_stale_open_pty(
    run_id: str,
    session_id: str,
    team_id: str = "",
    meta: dict[str, Any] | None = None,
) -> bool:
    current_meta = meta if meta is not None else _load_pty_meta_for_scope(run_id, session_id, team_id)
    if not current_meta or current_meta.get("closed"):
        return False
    if _active_pty_run_is_tracked(run_id, session_id, team_id):
        return False
    _delete_pty_runtime_state(run_id, include_stream=True)
    log.warning("PTY_STALE_RUN_CLEANED", extra={
        "run_id": run_id,
        "session": session_id,
        "team_id": team_id,
        "cmd": str(current_meta.get("command", "")),
    })
    return True


def _load_active_pty_meta_for_scope(
    run_id: str,
    session_id: str,
    team_id: str = "",
) -> tuple[dict[str, Any] | None, str]:
    meta = _load_pty_meta_for_scope(run_id, session_id, team_id)
    if not meta:
        return None, "Run not found"
    if meta.get("closed"):
        return None, "Run is closed"
    if _prune_stale_open_pty(run_id, session_id, team_id, meta):
        return None, _PTY_STALE_MESSAGE
    return meta, ""


def _store_pty_snapshot(run: PtyRun, *, force: bool = False) -> None:
    if not redis_client:
        return
    now = time.time()
    if not force:
        if run.capture_event_id == run.snapshot_published_event_id:
            return
        if (
            now - run.snapshot_last_published < _pty_snapshot_min_publish_seconds()
            and run.snapshot_published_event_id != "0-0"
        ):
            return
        if (
            run.snapshot_pending_bytes < _pty_snapshot_publish_bytes()
            and now - run.snapshot_last_published < _pty_snapshot_publish_seconds()
            and run.snapshot_published_event_id != "0-0"
        ):
            return
    with run.snapshot_lock:
        payload = _pty_snapshot_payload_from_run(run, distributed=True)
        if payload.get("snapshot_truncated") and not run.snapshot_truncation_logged:
            run.snapshot_truncation_logged = True
            log.warning("PTY_SNAPSHOT_TRUNCATED", extra={
                "run_id": run.run_id,
                "session": run.session_id,
                "cmd": run.command,
            })
        run.snapshot_pending_bytes = 0
        run.snapshot_last_published = now
        run.snapshot_published_event_id = run.capture_event_id
    payload_json = json.dumps(payload, separators=(",", ":"))
    redis_client.set(
        _snapshot_key(run.run_id),
        payload_json,
        ex=_active_ttl(),
    )
    log.debug("PTY_SNAPSHOT_PUBLISHED", extra={
        "run_id": run.run_id,
        "after_event_id": str(payload.get("after_event_id", "")),
        "snapshot_format": str(payload.get("snapshot_format", "")),
        "snapshot_truncated": bool(payload.get("snapshot_truncated")),
        "payload_bytes": _json_payload_size(payload_json),
    })


def _safe_store_pty_snapshot(run: PtyRun, *, force: bool = False) -> bool:
    try:
        _store_pty_snapshot(run, force=force)
        return True
    except Exception as exc:
        log.error("PTY_SNAPSHOT_SAVE_FAILED", exc_info=True, extra={
            "run_id": run.run_id,
            "session": run.session_id,
            "team_id": run.team_id,
            "cmd": run.command,
            "force": force,
            "error": str(exc),
        })
        return False


def pty_run_belongs_to_session(run_id: str, session_id: str) -> bool:
    return _load_pty_meta_for_session(run_id, session_id) is not None


def pty_run_belongs_to_scope(run_id: str, session_id: str, team_id: str = "") -> bool:
    return _load_pty_meta_for_scope(run_id, session_id, team_id) is not None


def notify_pty_killed_event(
    run_id: str,
    session_id: str,
    payload: dict[str, Any] | None = None,
    *,
    team_id: str = "",
) -> bool:
    meta, _message = _load_active_pty_meta_for_scope(run_id, session_id, team_id)
    if not meta:
        return False
    if redis_client:
        publish_pty_event(run_id, "killed", payload or {})
        return True
    run = get_pty_run(run_id, session_id, team_id=team_id)
    if not run:
        return False
    run.append_event("killed", payload or {})
    return True


def claim_pty_stream_owner(
    run_id: str,
    session_id: str,
    owner_client_id: str = "",
    owner_tab_id: str = "",
    *,
    team_id: str = "",
) -> bool:
    if not owner_client_id or not pty_run_belongs_to_scope(run_id, session_id, team_id):
        return False
    transition = active_run_claim_owner_transition(run_id, owner_client_id, owner_tab_id)
    if not transition.get("claimed"):
        return False
    if not transition.get("changed_client"):
        return True
    payload = {
        "text": "[interactive PTY moved to another tab]",
        "displaced_client_id": str(transition.get("previous_client_id", "") or ""),
        "displaced_tab_id": str(transition.get("previous_tab_id", "") or ""),
        "owner_client_id": owner_client_id,
        "owner_tab_id": owner_tab_id,
    }
    if redis_client:
        publish_pty_event(run_id, "displaced", payload)
        log.info("PTY_OWNERSHIP_DISPLACED", extra={
            "run_id": run_id,
            "session": session_id,
            "owner_client_id": owner_client_id,
            "owner_tab_id": owner_tab_id,
            "displaced_client_id": payload["displaced_client_id"],
            "displaced_tab_id": payload["displaced_tab_id"],
        })
        return True
    run = get_pty_run(run_id, session_id, team_id=team_id)
    if run:
        run.append_event("displaced", payload)
        log.info("PTY_OWNERSHIP_DISPLACED", extra={
            "run_id": run_id,
            "session": session_id,
            "owner_client_id": owner_client_id,
            "owner_tab_id": owner_tab_id,
            "displaced_client_id": payload["displaced_client_id"],
            "displaced_tab_id": payload["displaced_tab_id"],
        })
    return True


def publish_pty_event(run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> str:
    if not redis_client:
        raise RuntimeError("Redis is not available for PTY events")
    data = dict(payload or {})
    data["type"] = str(event_type)
    data.setdefault("created_at", time.time())
    payload_json = json.dumps(data, separators=(",", ":"))
    stream_key = _stream_key(run_id)
    event_id = _coerce_text(redis_client.xadd(
        stream_key,
        {"payload": payload_json},
        maxlen=_pty_stream_maxlen(),
        approximate=True,
    ))
    redis_client.expire(stream_key, _completed_ttl() if event_type in {"exit", "error"} else _active_ttl())
    log.debug("PTY_EVENT_PUBLISHED", extra={
        "run_id": run_id,
        "event_type": str(event_type),
        "event_id": event_id,
        "stream_key": stream_key,
        "payload_bytes": _json_payload_size(payload_json),
    })
    return event_id


def _safe_append_pty_event(run: PtyRun, event_type: str, payload: dict[str, Any] | None = None) -> str:
    try:
        return run.append_event(event_type, payload)
    except Exception as exc:
        log.error("PTY_EVENT_PUBLISH_FAILED", exc_info=True, extra={
            "run_id": run.run_id,
            "session": run.session_id,
            "team_id": run.team_id,
            "event_type": event_type,
            "cmd": run.command,
            "error": str(exc),
        })
        return ""


def _queue_pty_control(run_id: str, action: str, payload: dict[str, Any]) -> None:
    if not redis_client:
        raise RuntimeError("Redis is not available for PTY control events")
    body = dict(payload)
    body["action"] = action
    payload_json = json.dumps(body, separators=(",", ":"))
    control_key = _control_key(run_id)
    redis_client.xadd(control_key, {"payload": payload_json}, maxlen=1000, approximate=True)
    redis_client.expire(control_key, _active_ttl())
    queue_depth: int | None = None
    try:
        queue_depth = int(cast(Any, redis_client.xlen(control_key)))
        app_metrics.PTY_CONTROL_QUEUE_DEPTH.set(queue_depth)
    except Exception as exc:
        log.debug("PTY_METRIC_WRITE_FAILED", extra={"run_id": run_id, "metric": "control_queue_depth", "error": str(exc)})
    log.debug("PTY_CONTROL_QUEUED", extra={
        "run_id": run_id,
        "action": action,
        "queue_depth": queue_depth,
        "payload_bytes": _json_payload_size(payload_json),
    })


def _read_pty_control(run: PtyRun) -> list[dict[str, Any]]:
    if not redis_client:
        return []
    rows = cast(
        list[tuple[Any, list[tuple[Any, dict[str, Any]]]]],
        redis_client.xread({_control_key(run.run_id): run.control_event_id}, count=100, block=1),
    )
    controls: list[dict[str, Any]] = []
    for _key, stream_rows in rows or []:
        for event_id, fields in stream_rows:
            run.control_event_id = _coerce_text(event_id)
            payload = _decode_payload(fields, run_id=run.run_id, event_id=run.control_event_id, context="control")
            if payload is not None:
                controls.append(payload)
    return controls


def _apply_pty_controls(run: PtyRun) -> None:
    for control in _read_pty_control(run):
        action = str(control.get("action", ""))
        if action == "input":
            if not run.allow_input:
                log.warning("PTY_INPUT_DROPPED", extra={
                    "run_id": run.run_id,
                    "session": run.session_id,
                    "reason": "input_disabled",
                })
                continue
            raw = str(control.get("data", "") or "").encode("utf-8", errors="replace")
            if raw and len(raw) <= _pty_input_max_bytes():
                try:
                    os.write(run.master_fd, raw)
                    log.debug("PTY_CONTROL_APPLIED", extra={"run_id": run.run_id, "action": action, "bytes": len(raw)})
                except OSError as exc:
                    log.warning(
                        "PTY_INPUT_WRITE_FAILED",
                        extra={
                            "run_id": run.run_id,
                            "session": run.session_id,
                            "bytes": len(raw),
                            "error": str(exc),
                        },
                    )
            elif raw:
                log.warning("PTY_INPUT_DROPPED", extra={
                    "run_id": run.run_id,
                    "session": run.session_id,
                    "reason": "too_large",
                    "bytes": len(raw),
                })
        elif action == "resize":
            run.rows = _bounded_dimension(control.get("rows"), run.rows, 10, 60)
            run.cols = _bounded_dimension(control.get("cols"), run.cols, 40, 240)
            _set_pty_size(run.master_fd, run.rows, run.cols)
            run.terminal_capture.resize(run.rows, run.cols)
            _safe_store_pty_meta(run)
            _safe_store_pty_snapshot(run, force=True)
            log.debug("PTY_CONTROL_APPLIED", extra={
                "run_id": run.run_id,
                "action": action,
                "rows": run.rows,
                "cols": run.cols,
            })
    if redis_client:
        try:
            app_metrics.PTY_CONTROL_QUEUE_DEPTH.set(int(cast(Any, redis_client.xlen(_control_key(run.run_id)))))
        except Exception as exc:
            log.debug("PTY_METRIC_WRITE_FAILED", extra={
                "run_id": run.run_id,
                "metric": "control_queue_depth",
                "error": str(exc),
            })


def _cleanup_finished_pty_runtime(run: PtyRun) -> bool:
    redis_runtime_keys_removed = False
    cleanup_errors = 0

    try:
        os.close(run.master_fd)
    except OSError as exc:
        cleanup_errors += 1
        log.error("PTY_READER_CLEANUP_FAILED", exc_info=True, extra={
            "run_id": run.run_id,
            "pid": run.proc.pid,
            "session": run.session_id,
            "team_id": run.team_id,
            "stage": "close_master",
            "error": str(exc),
        })

    try:
        with _runs_lock:
            _runs.pop(run.run_id, None)
    except Exception as exc:
        cleanup_errors += 1
        log.error("PTY_READER_CLEANUP_FAILED", exc_info=True, extra={
            "run_id": run.run_id,
            "pid": run.proc.pid,
            "session": run.session_id,
            "team_id": run.team_id,
            "stage": "local_registry",
            "error": str(exc),
        })

    try:
        pid_pop(run.run_id)
    except Exception as exc:
        cleanup_errors += 1
        log.error("PTY_READER_CLEANUP_FAILED", exc_info=True, extra={
            "run_id": run.run_id,
            "pid": run.proc.pid,
            "session": run.session_id,
            "team_id": run.team_id,
            "stage": "pid_registry",
            "error": str(exc),
        })

    try:
        active_run_remove(run.run_id)
    except Exception as exc:
        cleanup_errors += 1
        log.error("PTY_READER_CLEANUP_FAILED", exc_info=True, extra={
            "run_id": run.run_id,
            "pid": run.proc.pid,
            "session": run.session_id,
            "team_id": run.team_id,
            "stage": "active_run_registry",
            "error": str(exc),
        })

    if redis_client:
        try:
            redis_client.delete(_control_key(run.run_id))
            redis_runtime_keys_removed = True
        except Exception as exc:
            cleanup_errors += 1
            log.error("PTY_READER_CLEANUP_FAILED", exc_info=True, extra={
                "run_id": run.run_id,
                "pid": run.proc.pid,
                "session": run.session_id,
                "team_id": run.team_id,
                "stage": "redis_runtime_keys",
                "error": str(exc),
            })

    log.info("PTY_RUNTIME_CLEANED", extra={
        "run_id": run.run_id,
        "pid": run.proc.pid,
        "session": run.session_id,
        "team_id": run.team_id,
        "redis_runtime_keys_removed": redis_runtime_keys_removed,
        "cleanup_errors": cleanup_errors,
    })
    return cleanup_errors == 0


def _reader_loop(run: PtyRun, client_ip: str) -> None:
    started_dt = datetime.fromisoformat(run.started)
    last_heartbeat = time.time()
    try:
        _safe_append_pty_event(run, "started", {
            "run_id": run.run_id,
            "started": run.started,
            "interactive": True,
        })
        _safe_store_pty_snapshot(run, force=True)
        while True:
            _apply_pty_controls(run)
            if run.max_runtime_seconds:
                elapsed = (datetime.now(timezone.utc) - started_dt).total_seconds()
                if elapsed >= run.max_runtime_seconds and run.proc.poll() is None:
                    _safe_append_pty_event(run, "notice", {
                        "text": f"[timeout] Interactive PTY exceeded {run.max_runtime_seconds}s limit and was killed.",
                    })
                    _terminate_run(run)

            ready, _, _ = select.select([run.master_fd], [], [], _pty_control_poll_seconds())
            if ready:
                try:
                    chunk = os.read(run.master_fd, 4096)
                except OSError:
                    chunk = b""
                if chunk:
                    text = chunk.decode("utf-8", errors="replace")
                    with run.snapshot_lock:
                        run.terminal_capture.feed(text)
                        event_id = _safe_append_pty_event(run, "output", {"text": text})
                        if event_id:
                            run.capture_event_id = event_id
                        run.snapshot_pending_bytes += len(chunk)
                    _safe_store_pty_snapshot(run)
                    continue
            if run.proc.poll() is not None:
                break
            now = time.time()
            if now - last_heartbeat >= _pty_heartbeat_seconds():
                _safe_append_pty_event(run, "heartbeat", {})
                last_heartbeat = now

        exit_code = run.proc.wait(timeout=5)
        run.exit_code = exit_code
    except Exception as exc:
        log.error("PTY_STREAM_ERROR", exc_info=True, extra={
            "run_id": run.run_id,
            "session": run.session_id,
            "ip": client_ip,
            "cmd": run.command,
        })
        _safe_append_pty_event(run, "error", {"text": str(exc)})
        exit_code = run.proc.returncode if run.proc.returncode is not None else 1
        run.exit_code = exit_code
    finally:
        run.closed = True
        finished = datetime.now(timezone.utc)
        elapsed = round((finished - started_dt).total_seconds(), 1)
        code = run.exit_code if run.exit_code is not None else run.proc.returncode
        code = int(code if code is not None else 1)
        completion_summary: dict[str, object] = {}
        try:
            if run.completion_callback:
                completion_summary = run.completion_callback(
                    run,
                    finished.isoformat(),
                    code,
                    run.terminal_capture.synthesize_entries(),
                )
        except Exception:
            log.error("PTY_RUN_SAVE_ERROR", exc_info=True, extra={
                "run_id": run.run_id,
                "session": run.session_id,
                "ip": client_ip,
                "cmd": run.command,
            })
        exit_payload = {"code": code, "elapsed": elapsed, "interactive": True}
        exit_payload.update(completion_summary)
        if _safe_store_pty_snapshot(run, force=True):
            log.info("PTY_SNAPSHOT_PERSISTED", extra={
                "run_id": run.run_id,
                "session": run.session_id,
                "rows": run.rows,
                "cols": run.cols,
                "forced": True,
            })
        _safe_append_pty_event(run, "exit", exit_payload)
        _cleanup_finished_pty_runtime(run)
        output_line_count = 0
        raw_output_line_count = completion_summary.get("output_line_count", 0)
        if isinstance(raw_output_line_count, (int, str, bytes, bytearray)):
            try:
                output_line_count = int(raw_output_line_count)
            except (TypeError, ValueError):
                output_line_count = 0
        log.info("RUN_END", extra={
            "run_id": run.run_id,
            "session": run.session_id,
            "ip": client_ip,
            "exit_code": code,
            "elapsed": elapsed,
            "cmd": run.command,
            "cmd_type": "pty",
            "output_line_count": output_line_count,
            "full_output_truncated": bool(completion_summary.get("full_output_truncated")),
            "full_output_available": bool(completion_summary.get("full_output_available")),
            "artifact_count": 0,
        })
        log.info("PTY_SESSION_ENDED", extra={
            "run_id": run.run_id,
            "session": run.session_id,
            "ip": client_ip,
            "exit_code": code,
            "elapsed": elapsed,
            "cmd": run.command,
        })
        with run.condition:
            run.condition.notify_all()


def start_pty_run(
    *,
    session_id: str,
    client_ip: str,
    command: str,
    argv: list[str],
    team_id: str = "",
    rows: object = None,
    cols: object = None,
    default_rows: object = 24,
    default_cols: object = 100,
    owner_client_id: str = "",
    owner_tab_id: str = "",
    allow_input: bool = True,
    max_runtime_seconds: int = 900,
    completion_callback: Callable[[PtyRun, str, int, Sequence[dict[str, object]]], dict[str, object]] | None = None,
) -> PtyRun:
    if pyte is None:
        raise PtyDependencyError(
            "Interactive PTY startup requires pyte for server-side terminal capture; "
            "install pyte or disable interactive PTY mode."
        )
    default_rows_i = _bounded_dimension(default_rows, 24, 10, 60)
    default_cols_i = _bounded_dimension(default_cols, 100, 40, 240)
    rows_i = _bounded_dimension(rows, default_rows_i, 10, 60)
    cols_i = _bounded_dimension(cols, default_cols_i, 40, 240)
    terminal_history_lines = _terminal_history_line_limit(CFG.get("max_output_lines", 0))
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    master_fd = -1
    slave_fd = -1
    proc: subprocess.Popen | None = None
    run: PtyRun | None = None
    meta_stored = False
    pid_registered = False
    active_registered = False
    try:
        master_fd, slave_fd = pty.openpty()
        _set_pty_size(slave_fd, rows_i, cols_i)
        proc = subprocess.Popen(
            SCANNER_PREFIX + argv if SCANNER_PREFIX else argv,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            shell=False,
            close_fds=True,
            preexec_fn=_prepare_child,
            env=_command_env(),
        )
        try:
            os.close(slave_fd)
        except OSError:
            pass
        slave_fd = -1

        run = PtyRun(
            run_id=run_id,
            session_id=session_id,
            team_id=str(team_id or ""),
            command=command,
            argv=list(argv),
            started=started,
            master_fd=master_fd,
            proc=proc,
            rows=rows_i,
            cols=cols_i,
            allow_input=allow_input,
            max_runtime_seconds=max_runtime_seconds,
            brokered=bool(redis_client),
            terminal_capture=PtyTerminalCapture(rows_i, cols_i, terminal_history_lines),
            owner_tab_id=owner_tab_id,
            completion_callback=completion_callback,
        )
        with _runs_lock:
            _runs[run_id] = run
        _store_pty_meta(run)
        meta_stored = True
        pid_register(run_id, proc.pid)
        pid_registered = True
        active_run_register(
            run_id,
            proc.pid,
            session_id,
            command,
            started,
            owner_client_id=owner_client_id,
            owner_tab_id=owner_tab_id,
            run_type="pty",
            team_id=str(team_id or ""),
        )
        active_registered = True
        log.info("RUN_START", extra={
            "run_id": run_id,
            "session": session_id,
            "ip": client_ip,
            "pid": proc.pid,
            "cmd": command,
            "cmd_type": "pty",
        })
        log.info("PTY_SESSION_STARTED", extra={
            "run_id": run_id,
            "session": session_id,
            "ip": client_ip,
            "pid": proc.pid,
            "cmd": command,
            "rows": rows_i,
            "cols": cols_i,
            "allow_input": bool(allow_input),
        })
        threading.Thread(
            target=_reader_loop,
            args=(run, client_ip),
            name=f"pty-run-{run_id[:8]}",
            daemon=True,
        ).start()
        return run
    except Exception:
        if run is not None:
            _terminate_run(run)
        elif proc is not None and proc.poll() is None:
            try:
                pgid = proc.pid
                if SCANNER_PREFIX:
                    subprocess.run(
                        [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
                        timeout=5,
                    )
                else:
                    os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, subprocess.TimeoutExpired, OSError) as cleanup_exc:
                log.warning(
                    "PTY_STARTUP_CLEANUP_FAILED",
                    exc_info=True,
                    extra={"run_id": run_id, "stage": "terminate", "error": str(cleanup_exc)},
                )
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired as cleanup_exc:
                log.warning(
                    "PTY_STARTUP_CLEANUP_FAILED",
                    exc_info=True,
                    extra={"run_id": run_id, "stage": "wait", "error": str(cleanup_exc)},
                )
        if pid_registered:
            pid_pop(run_id)
        if active_registered:
            active_run_remove(run_id)
        if meta_stored:
            _delete_pty_meta(run_id)
        with _runs_lock:
            _runs.pop(run_id, None)
        if master_fd >= 0:
            try:
                os.close(master_fd)
            except OSError as cleanup_exc:
                log.warning(
                    "PTY_STARTUP_CLEANUP_FAILED",
                    exc_info=True,
                    extra={"run_id": run_id, "stage": "close_master", "error": str(cleanup_exc)},
                )
        raise
    finally:
        if slave_fd >= 0:
            try:
                os.close(slave_fd)
            except OSError:
                pass


def get_pty_run(run_id: str, session_id: str, *, team_id: str = "") -> PtyRun | None:
    with _runs_lock:
        run = _runs.get(run_id)
    if not run or not _meta_matches_scope({"session_id": run.session_id, "team_id": run.team_id}, session_id, team_id):
        return None
    return run


def pty_run_snapshot(
    run_id: str,
    session_id: str,
    *,
    team_id: str = "",
) -> tuple[bool, str, dict[str, Any] | None]:
    run = get_pty_run(run_id, session_id, team_id=team_id)
    if not run:
        meta = _load_pty_meta_for_scope(run_id, session_id, team_id)
        if meta:
            if meta.get("closed"):
                return False, "Run is closed", None
            if _prune_stale_open_pty(run_id, session_id, team_id, meta):
                return False, _PTY_STALE_MESSAGE, None
            snapshot = _load_pty_snapshot(run_id, session_id, team_id)
            if snapshot is not None:
                snapshot_age = snapshot.get("snapshot_age_seconds")
                if isinstance(snapshot_age, (int, float)):
                    app_metrics.PTY_SNAPSHOT_AGE.observe(max(0.0, float(snapshot_age)))
                return True, "", snapshot
            if redis_client:
                return False, "PTY snapshot is not available yet", None
            return False, "PTY snapshot is not available from this worker", None
        return False, "Run not found", None
    with run.snapshot_lock:
        snapshot = _pty_snapshot_payload_from_run(run)
    snapshot["snapshot_age_seconds"] = 0
    _safe_store_pty_snapshot(run, force=True)
    return True, "", snapshot


def write_pty_input(
    run_id: str,
    session_id: str,
    data: object,
    owner_client_id: str = "",
    owner_tab_id: str = "",
    *,
    team_id: str = "",
) -> tuple[bool, str]:
    meta, message = _load_active_pty_meta_for_scope(run_id, session_id, team_id)
    if not meta:
        return False, message
    if owner_client_id and not active_run_owned_by(run_id, owner_client_id, owner_tab_id):
        app_metrics.PTY_INPUT_DROPPED_BYTES.labels("not_owner").inc(
            len(str(data or "").encode("utf-8", errors="replace"))
        )
        return False, "PTY input is owned by another attached tab"
    text = str(data or "")
    if not text:
        return True, ""
    raw = text.encode("utf-8", errors="replace")
    if len(raw) > _pty_input_max_bytes():
        app_metrics.PTY_INPUT_DROPPED_BYTES.labels("oversize").inc(len(raw))
        return False, "Input is too large for this interactive run"
    if redis_client:
        try:
            _queue_pty_control(run_id, "input", {"data": text})
        except Exception as exc:
            log.warning("PTY_CONTROL_QUEUE_FAILED", exc_info=True, extra={
                "run_id": run_id,
                "session": session_id,
                "team_id": team_id,
                "action": "input",
                "payload_bytes": len(raw),
                "error": str(exc),
            })
            return False, str(exc)
        app_metrics.PTY_INPUT_BYTES.inc(len(raw))
        return True, ""
    run = get_pty_run(run_id, session_id, team_id=team_id)
    if not run:
        app_metrics.PTY_INPUT_DROPPED_BYTES.labels("closed").inc(len(raw))
        return False, "Run not found"
    if not run.allow_input:
        app_metrics.PTY_INPUT_DROPPED_BYTES.labels("closed").inc(len(raw))
        return False, "This interactive run does not accept input"
    try:
        os.write(run.master_fd, raw)
        app_metrics.PTY_INPUT_BYTES.inc(len(raw))
        return True, ""
    except OSError as exc:
        return False, str(exc)


def resize_pty(
    run_id: str,
    session_id: str,
    rows: object,
    cols: object,
    *,
    team_id: str = "",
) -> tuple[bool, str, int, int]:
    meta, message = _load_active_pty_meta_for_scope(run_id, session_id, team_id)
    if not meta:
        return False, message, 0, 0
    rows_i = _bounded_dimension(rows, meta.get("rows", 24), 10, 60)
    cols_i = _bounded_dimension(cols, meta.get("cols", 100), 40, 240)
    if redis_client:
        try:
            _queue_pty_control(run_id, "resize", {"rows": rows_i, "cols": cols_i})
        except Exception as exc:
            log.warning("PTY_CONTROL_QUEUE_FAILED", exc_info=True, extra={
                "run_id": run_id,
                "session": session_id,
                "team_id": team_id,
                "action": "resize",
                "payload_bytes": _json_payload_size(json.dumps({"rows": rows_i, "cols": cols_i}, separators=(",", ":"))),
                "error": str(exc),
            })
            return False, str(exc), 0, 0
        meta["rows"] = rows_i
        meta["cols"] = cols_i
        try:
            redis_client.set(_meta_key(run_id), json.dumps(meta, separators=(",", ":")), ex=_active_ttl())
        except Exception as exc:
            log.error("PTY_META_SAVE_FAILED", exc_info=True, extra={
                "run_id": run_id,
                "session": session_id,
                "team_id": team_id,
                "cmd": str(meta.get("command", "") or ""),
                "closed": False,
                "error": str(exc),
            })
            return False, str(exc), 0, 0
        return True, "", rows_i, cols_i
    run = get_pty_run(run_id, session_id, team_id=team_id)
    if not run:
        return False, "Run not found", 0, 0
    run.rows = rows_i
    run.cols = cols_i
    _set_pty_size(run.master_fd, run.rows, run.cols)
    run.terminal_capture.resize(run.rows, run.cols)
    _safe_store_pty_snapshot(run, force=True)
    return True, "", run.rows, run.cols


def _stream_local_pty_events(run: PtyRun, after: str = "0-0") -> Iterator[str]:
    try:
        cursor = max(0, int(after or 0))
    except ValueError:
        cursor = 0
    while True:
        with run.condition:
            events = [event for event in run.events if event.seq > cursor]
            if not events and run.closed:
                return
            if not events:
                run.condition.wait(timeout=_pty_heartbeat_seconds())
                events = [event for event in run.events if event.seq > cursor]
            if not events:
                yield "event: heartbeat\ndata: {}\n\n"
                continue
        for event in events:
            cursor = event.seq
            payload = dict(event.payload)
            payload["type"] = event.type
            payload["event_id"] = str(event.seq)
            yield f"id: {event.seq}\ndata: {json.dumps(payload)}\n\n"
        if run.closed and events and events[-1].type == "exit":
            return


def stream_pty_events(run_id: str, session_id: str, after: str = "0-0", *, team_id: str = "") -> Iterator[str]:
    meta = _load_pty_meta_for_scope(run_id, session_id, team_id)
    if not meta:
        return
    if not redis_client:
        if _prune_stale_open_pty(run_id, session_id, team_id, meta):
            yield f"data: {json.dumps({'type': 'error', 'text': _PTY_STALE_MESSAGE})}\n\n"
            return
        run = get_pty_run(run_id, session_id, team_id=team_id)
        if not run:
            return
        yield from _stream_local_pty_events(run, after=after)
        return

    current_id = _normalize_event_id(after)
    block_ms = max(1, int(float(CFG.get("run_broker_subscriber_block_seconds", 15) or 15) * 1000))
    first_read = True
    while True:
        try:
            rows = cast(
                list[tuple[Any, list[tuple[Any, dict[str, Any]]]]],
                redis_client.xread(
                    {_stream_key(run_id): current_id},
                    count=_pty_stream_fetch_count(),
                    block=1 if first_read else block_ms,
                ),
            )
        except (RedisTimeoutError, RedisConnectionError) as exc:
            if not _is_redis_idle_timeout_error(exc):
                raise
            rows = []
        first_read = False
        if not rows:
            meta = _load_pty_meta_for_scope(run_id, session_id, team_id)
            if not meta:
                yield f"data: {json.dumps({'type': 'error', 'text': _PTY_STALE_MESSAGE})}\n\n"
                return
            if meta.get("closed"):
                return
            if _prune_stale_open_pty(run_id, session_id, team_id, meta):
                yield f"data: {json.dumps({'type': 'error', 'text': _PTY_STALE_MESSAGE})}\n\n"
                return
            yield ": heartbeat\n\n"
            continue
        for _key, stream_rows in rows:
            for event_id, fields in stream_rows:
                current_id = _coerce_text(event_id)
                payload = _decode_payload(fields, run_id=run_id, event_id=current_id, context="stream")
                if payload is None:
                    log.warning("PTY_STREAM_EVENT_SKIPPED", extra={
                        "run_id": run_id,
                        "event_id": current_id,
                        "session": session_id,
                        "team_id": team_id,
                    })
                    continue
                body = dict(payload)
                body["event_id"] = current_id
                yield f"id: {current_id}\ndata: {json.dumps(body)}\n\n"
                if body.get("type") in {"exit", "error"}:
                    return
