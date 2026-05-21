from __future__ import annotations

"""Constrained PTY lifecycle for interactive runs."""

import fcntl
import json
import logging
import os
import pty
import select
import signal
import struct
import subprocess
import tempfile
import termios
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, cast

from config import CFG, SCANNER_PREFIX
from core.process import (
    active_run_claim_owner_transition,
    active_run_owned_by,
    active_run_register,
    active_run_remove,
    active_runs_for_session,
    pid_pop,
    pid_register,
    redis_client,
)
from services.pty import capture as pty_capture
from services.pty.capture import (
    PtyTerminalCapture as _BasePtyTerminalCapture,
    _terminal_history_line_limit,
)
from services.runs.output_model import LineKind, line_event_from_legacy, to_legacy_entry
from services import metrics as app_metrics

log = logging.getLogger("shell")
pyte = pty_capture.pyte
_PTY_CAPTURE_MAX_HISTORY_LINES = pty_capture._PTY_CAPTURE_MAX_HISTORY_LINES
_PTY_CAPTURE_MIN_HISTORY_LINES = pty_capture._PTY_CAPTURE_MIN_HISTORY_LINES
_PTY_SNAPSHOT_MAX_BYTES = pty_capture._PTY_SNAPSHOT_MAX_BYTES

SUDO_BIN = "/usr/bin/sudo"
KILL_BIN = "/bin/kill"
RUN_SUBPROCESS_UMASK = 0o027
_PTY_BUFFER_LIMIT = 512
_PTY_INPUT_MAX_BYTES = 4096
_PTY_HEARTBEAT_SECONDS = 15.0
_PTY_CONTROL_POLL_SECONDS = 0.2
_PTY_STREAM_FETCH_COUNT = 100
_PTY_STREAM_MAXLEN = 5000
_PTY_SNAPSHOT_PUBLISH_BYTES = 8192
_PTY_SNAPSHOT_PUBLISH_SECONDS = 1.0
_PTY_SNAPSHOT_MIN_PUBLISH_SECONDS = 0.2
_PTY_SNAPSHOT_FALLBACK_ENTRY_LIMIT = 200
_PTY_STALE_MESSAGE = "PTY run is no longer active"
_PTY_ENV_PASSTHROUGH_KEYS = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "TMPDIR",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NO_COLOR",
    "CLICOLOR",
    "COLORTERM",
)
def _coerce_non_negative_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        number = int(value)
    elif isinstance(value, (str, bytes, bytearray)):
        try:
            number = int(value)
        except ValueError:
            return default
    else:
        return default
    return number if number >= 0 else default


def _cfg_positive_int(key: str, default: int) -> int:
    return max(1, _coerce_non_negative_int(CFG.get(key), default))


def _cfg_positive_float(key: str, default: float) -> float:
    value = CFG.get(key)
    if value is None or isinstance(value, bool):
        return default
    try:
        number = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _pty_buffer_limit() -> int:
    return _cfg_positive_int("interactive_pty_buffer_limit", _PTY_BUFFER_LIMIT)


def _pty_input_max_bytes() -> int:
    return _cfg_positive_int("interactive_pty_input_max_bytes", _PTY_INPUT_MAX_BYTES)


def _pty_heartbeat_seconds() -> float:
    return _cfg_positive_float("interactive_pty_heartbeat_seconds", _PTY_HEARTBEAT_SECONDS)


def _pty_control_poll_seconds() -> float:
    return _cfg_positive_float("interactive_pty_control_poll_seconds", _PTY_CONTROL_POLL_SECONDS)


def _pty_stream_fetch_count() -> int:
    return _cfg_positive_int("interactive_pty_stream_fetch_count", _PTY_STREAM_FETCH_COUNT)


def _pty_stream_maxlen() -> int:
    return _cfg_positive_int("interactive_pty_stream_maxlen", _PTY_STREAM_MAXLEN)


def _pty_snapshot_publish_bytes() -> int:
    return _cfg_positive_int("interactive_pty_snapshot_publish_bytes", _PTY_SNAPSHOT_PUBLISH_BYTES)


def _pty_snapshot_publish_seconds() -> float:
    return _cfg_positive_float("interactive_pty_snapshot_publish_seconds", _PTY_SNAPSHOT_PUBLISH_SECONDS)


def _pty_snapshot_min_publish_seconds() -> float:
    return _cfg_positive_float("interactive_pty_snapshot_min_publish_seconds", _PTY_SNAPSHOT_MIN_PUBLISH_SECONDS)


def _pty_snapshot_fallback_entry_limit() -> int:
    return _cfg_positive_int("interactive_pty_snapshot_fallback_entry_limit", _PTY_SNAPSHOT_FALLBACK_ENTRY_LIMIT)


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


def _active_ttl() -> int:
    return max(1, int(CFG.get("run_broker_active_stream_ttl_seconds", 14400) or 14400))


def _completed_ttl() -> int:
    return max(1, int(CFG.get("run_broker_completed_stream_ttl_seconds", 3600) or 3600))


def _stream_key(run_id: str) -> str:
    return f"ptystream:{run_id}"


def _control_key(run_id: str) -> str:
    return f"ptycontrol:{run_id}"


def _meta_key(run_id: str) -> str:
    return f"ptymeta:{run_id}"


def _snapshot_key(run_id: str) -> str:
    return f"ptysnapshot:{run_id}"


def _coerce_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _is_valid_stream_event_id(event_id: str | None) -> bool:
    try:
        left, right = str(event_id or "").split("-", 1)
        int(left)
        int(right)
    except (TypeError, ValueError):
        return False
    return True


def _normalize_event_id(event_id: str | None) -> str:
    if not event_id or event_id in {"-", "0", "0-0"}:
        return "0-0"
    return str(event_id) if _is_valid_stream_event_id(str(event_id)) else "0-0"


def _decode_payload(fields: object) -> dict[str, Any] | None:
    if not isinstance(fields, dict):
        return None
    raw = fields.get("payload")
    if raw is None:
        raw = fields.get(b"payload")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _prepare_child() -> None:
    os.setsid()
    os.umask(RUN_SUBPROCESS_UMASK)


def _bounded_dimension(value: object, default: int, min_value: int, max_value: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        number = int(value)
    elif isinstance(value, (str, bytes, bytearray)):
        try:
            number = int(value)
        except ValueError:
            return default
    else:
        return default
    return min(max(number, min_value), max_value)


def _set_pty_size(fd: int, rows: int, cols: int) -> None:
    try:
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)
    except OSError:
        pass


def _command_env() -> dict[str, str]:
    env = {
        key: value
        for key in _PTY_ENV_PASSTHROUGH_KEYS
        if (value := os.environ.get(key))
    }
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.setdefault("HOME", tempfile.gettempdir())
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", env.get("LANG", "C.UTF-8"))
    env["TERM"] = "xterm-256color"
    return env


def _terminate_run(run: PtyRun) -> None:
    if run.proc.poll() is not None:
        return
    try:
        pgid = run.proc.pid
        if SCANNER_PREFIX:
            subprocess.run(
                [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
                timeout=5,
            )
        else:
            os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
        pass


def _store_pty_meta(run: PtyRun, *, closed: bool = False) -> None:
    if not redis_client:
        return
    payload = {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "command": run.command,
        "started": run.started,
        "rows": run.rows,
        "cols": run.cols,
        "closed": bool(closed),
    }
    redis_client.set(
        _meta_key(run.run_id),
        json.dumps(payload, separators=(",", ":")),
        ex=_completed_ttl() if closed else _active_ttl(),
    )
    if closed:
        redis_client.delete(_control_key(run.run_id), _snapshot_key(run.run_id))


def _delete_pty_meta(run_id: str) -> None:
    if not redis_client:
        return
    redis_client.delete(_meta_key(run_id))
    redis_client.delete(_control_key(run_id))
    redis_client.delete(_snapshot_key(run_id))


def _delete_pty_runtime_state(run_id: str, *, include_stream: bool = False) -> None:
    if not redis_client:
        return
    keys = [_meta_key(run_id), _control_key(run_id), _snapshot_key(run_id)]
    if include_stream:
        keys.append(_stream_key(run_id))
    redis_client.delete(*keys)


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
        "command": run.command,
        "started": run.started,
        "rows": run.rows,
        "cols": run.cols,
        "closed": run.closed,
    }


def _load_pty_meta_for_session(run_id: str, session_id: str) -> dict[str, Any] | None:
    meta = _load_pty_meta(run_id)
    if not meta or meta.get("session_id") != session_id:
        return None
    return meta


def _active_pty_run_is_tracked(run_id: str, session_id: str) -> bool:
    with _runs_lock:
        run = _runs.get(run_id)
    if run and run.session_id == session_id and not run.closed:
        return True
    try:
        active_runs = active_runs_for_session(session_id)
    except Exception:
        log.warning("PTY_ACTIVE_RUN_CHECK_FAILED", exc_info=True, extra={
            "run_id": run_id,
            "session": session_id,
        })
        return True
    return any(
        str(item.get("run_id", "")) == run_id
        and str(item.get("run_type", "command") or "command") == "pty"
        for item in active_runs
    )


def _prune_stale_open_pty(run_id: str, session_id: str, meta: dict[str, Any] | None = None) -> bool:
    current_meta = meta if meta is not None else _load_pty_meta_for_session(run_id, session_id)
    if not current_meta or current_meta.get("closed"):
        return False
    if _active_pty_run_is_tracked(run_id, session_id):
        return False
    _delete_pty_runtime_state(run_id, include_stream=True)
    log.warning("PTY_STALE_RUN_CLEANED", extra={
        "run_id": run_id,
        "session": session_id,
        "cmd": str(current_meta.get("command", "")),
    })
    return True


def _load_active_pty_meta_for_session(run_id: str, session_id: str) -> tuple[dict[str, Any] | None, str]:
    meta = _load_pty_meta_for_session(run_id, session_id)
    if not meta:
        return None, "Run not found"
    if meta.get("closed"):
        return None, "Run is closed"
    if _prune_stale_open_pty(run_id, session_id, meta):
        return None, _PTY_STALE_MESSAGE
    return meta, ""


def _limited_snapshot_entries(entries: Sequence[dict[str, object]], ansi_snapshot: str) -> list[dict[str, object]]:
    if ansi_snapshot:
        return []
    fallback_entry_limit = _pty_snapshot_fallback_entry_limit()
    if len(entries) <= fallback_entry_limit:
        return [dict(entry) for entry in entries]
    return [
        to_legacy_entry(
            line_event_from_legacy(
                "[earlier PTY snapshot entries omitted; terminal snapshot resumes visually]",
                kind=LineKind.notice,
            ),
            include_timestamps=False,
        ),
        *[dict(entry) for entry in entries[-fallback_entry_limit:]],
    ]


def _pty_snapshot_payload_from_run(run: PtyRun, *, distributed: bool = False) -> dict[str, Any]:
    entries = run.terminal_capture.synthesize_entries()
    ansi_snapshot, snapshot_truncated = run.terminal_capture.ansi_snapshot()
    # Redis snapshots omit fallback entries when ANSI is available to keep the
    # distributed payload bounded; local snapshots keep both for direct callers.
    payload: dict[str, Any] = {
        "run_id": run.run_id,
        "command": run.command,
        "started": run.started,
        "rows": run.rows,
        "cols": run.cols,
        "after_event_id": run.capture_event_id,
        "entries": _limited_snapshot_entries(entries, ansi_snapshot) if distributed else entries,
        "snapshot_format": "ansi" if ansi_snapshot else "plain",
        "ansi_snapshot": ansi_snapshot,
        "snapshot_truncated": snapshot_truncated,
    }
    if distributed:
        payload["session_id"] = run.session_id
        payload["created_at"] = time.time()
    return payload


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
    redis_client.set(
        _snapshot_key(run.run_id),
        json.dumps(payload, separators=(",", ":")),
        ex=_active_ttl(),
    )


def _load_pty_snapshot(run_id: str, session_id: str) -> dict[str, Any] | None:
    if not redis_client:
        return None
    raw = redis_client.get(_snapshot_key(run_id))
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("session_id") != session_id:
        return None
    response = dict(payload)
    try:
        created_at = float(response.get("created_at", 0) or 0)
    except (TypeError, ValueError):
        created_at = 0
    if created_at:
        response["snapshot_age_seconds"] = round(max(0.0, time.time() - created_at), 3)
    else:
        response["snapshot_age_seconds"] = None
    response.pop("session_id", None)
    response.pop("created_at", None)
    return response


def pty_run_belongs_to_session(run_id: str, session_id: str) -> bool:
    return _load_pty_meta_for_session(run_id, session_id) is not None


def notify_pty_killed_event(run_id: str, session_id: str, payload: dict[str, Any] | None = None) -> bool:
    meta, _message = _load_active_pty_meta_for_session(run_id, session_id)
    if not meta:
        return False
    if redis_client:
        publish_pty_event(run_id, "killed", payload or {})
        return True
    run = get_pty_run(run_id, session_id)
    if not run:
        return False
    run.append_event("killed", payload or {})
    return True


def claim_pty_stream_owner(run_id: str, session_id: str, owner_client_id: str = "", owner_tab_id: str = "") -> bool:
    if not owner_client_id or not pty_run_belongs_to_session(run_id, session_id):
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
    run = get_pty_run(run_id, session_id)
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
    event_id = _coerce_text(redis_client.xadd(
        _stream_key(run_id),
        {"payload": json.dumps(data, separators=(",", ":"))},
        maxlen=_pty_stream_maxlen(),
        approximate=True,
    ))
    redis_client.expire(_stream_key(run_id), _completed_ttl() if event_type in {"exit", "error"} else _active_ttl())
    return event_id


def _queue_pty_control(run_id: str, action: str, payload: dict[str, Any]) -> None:
    if not redis_client:
        raise RuntimeError("Redis is not available for PTY control events")
    body = dict(payload)
    body["action"] = action
    redis_client.xadd(_control_key(run_id), {"payload": json.dumps(body, separators=(",", ":"))}, maxlen=1000, approximate=True)
    redis_client.expire(_control_key(run_id), _active_ttl())
    try:
        app_metrics.PTY_CONTROL_QUEUE_DEPTH.set(int(cast(Any, redis_client.xlen(_control_key(run_id)))))
    except Exception as exc:
        log.debug("PTY_METRIC_WRITE_FAILED", extra={"run_id": run_id, "metric": "control_queue_depth", "error": str(exc)})


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
            payload = _decode_payload(fields)
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
                except OSError:
                    pass
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
            _store_pty_meta(run)
            _store_pty_snapshot(run, force=True)
    if redis_client:
        try:
            app_metrics.PTY_CONTROL_QUEUE_DEPTH.set(int(cast(Any, redis_client.xlen(_control_key(run.run_id)))))
        except Exception as exc:
            log.debug("PTY_METRIC_WRITE_FAILED", extra={
                "run_id": run.run_id,
                "metric": "control_queue_depth",
                "error": str(exc),
            })


def _reader_loop(run: PtyRun, client_ip: str) -> None:
    started_dt = datetime.fromisoformat(run.started)
    last_heartbeat = time.time()
    try:
        run.append_event("started", {
            "run_id": run.run_id,
            "started": run.started,
            "interactive": True,
        })
        _store_pty_snapshot(run, force=True)
        while True:
            _apply_pty_controls(run)
            if run.max_runtime_seconds:
                elapsed = (datetime.now(timezone.utc) - started_dt).total_seconds()
                if elapsed >= run.max_runtime_seconds and run.proc.poll() is None:
                    run.append_event("notice", {
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
                        run.capture_event_id = run.append_event("output", {"text": text})
                        run.snapshot_pending_bytes += len(chunk)
                    _store_pty_snapshot(run)
                    continue
            if run.proc.poll() is not None:
                break
            now = time.time()
            if now - last_heartbeat >= _pty_heartbeat_seconds():
                run.append_event("heartbeat", {})
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
        run.append_event("error", {"text": str(exc)})
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
        _store_pty_snapshot(run, force=True)
        log.info("PTY_SNAPSHOT_PERSISTED", extra={
            "run_id": run.run_id,
            "session": run.session_id,
            "rows": run.rows,
            "cols": run.cols,
            "forced": True,
        })
        run.append_event("exit", exit_payload)
        try:
            os.close(run.master_fd)
        except OSError:
            pass
        with _runs_lock:
            _runs.pop(run.run_id, None)
        pid_pop(run.run_id)
        active_run_remove(run.run_id)
        if redis_client:
            redis_client.delete(_control_key(run.run_id))
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
            except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                pass
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
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
            except OSError:
                pass
        raise
    finally:
        if slave_fd >= 0:
            try:
                os.close(slave_fd)
            except OSError:
                pass


def get_pty_run(run_id: str, session_id: str) -> PtyRun | None:
    with _runs_lock:
        run = _runs.get(run_id)
    if not run or run.session_id != session_id:
        return None
    return run


def pty_run_snapshot(run_id: str, session_id: str) -> tuple[bool, str, dict[str, Any] | None]:
    run = get_pty_run(run_id, session_id)
    if not run:
        meta = _load_pty_meta_for_session(run_id, session_id)
        if meta:
            if meta.get("closed"):
                return False, "Run is closed", None
            if _prune_stale_open_pty(run_id, session_id, meta):
                return False, _PTY_STALE_MESSAGE, None
            snapshot = _load_pty_snapshot(run_id, session_id)
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
    _store_pty_snapshot(run, force=True)
    return True, "", snapshot


def write_pty_input(
    run_id: str,
    session_id: str,
    data: object,
    owner_client_id: str = "",
    owner_tab_id: str = "",
) -> tuple[bool, str]:
    meta, message = _load_active_pty_meta_for_session(run_id, session_id)
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
        _queue_pty_control(run_id, "input", {"data": text})
        app_metrics.PTY_INPUT_BYTES.inc(len(raw))
        return True, ""
    run = get_pty_run(run_id, session_id)
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


def resize_pty(run_id: str, session_id: str, rows: object, cols: object) -> tuple[bool, str, int, int]:
    meta, message = _load_active_pty_meta_for_session(run_id, session_id)
    if not meta:
        return False, message, 0, 0
    rows_i = _bounded_dimension(rows, meta.get("rows", 24), 10, 60)
    cols_i = _bounded_dimension(cols, meta.get("cols", 100), 40, 240)
    if redis_client:
        _queue_pty_control(run_id, "resize", {"rows": rows_i, "cols": cols_i})
        meta["rows"] = rows_i
        meta["cols"] = cols_i
        redis_client.set(_meta_key(run_id), json.dumps(meta, separators=(",", ":")), ex=_active_ttl())
        return True, "", rows_i, cols_i
    run = get_pty_run(run_id, session_id)
    if not run:
        return False, "Run not found", 0, 0
    run.rows = rows_i
    run.cols = cols_i
    _set_pty_size(run.master_fd, run.rows, run.cols)
    run.terminal_capture.resize(run.rows, run.cols)
    _store_pty_snapshot(run, force=True)
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


def stream_pty_events(run_id: str, session_id: str, after: str = "0-0") -> Iterator[str]:
    meta = _load_pty_meta_for_session(run_id, session_id)
    if not meta:
        return
    if _prune_stale_open_pty(run_id, session_id, meta):
        yield f"data: {json.dumps({'type': 'error', 'text': _PTY_STALE_MESSAGE})}\n\n"
        return
    if not redis_client:
        run = get_pty_run(run_id, session_id)
        if not run:
            return
        yield from _stream_local_pty_events(run, after=after)
        return

    current_id = _normalize_event_id(after)
    block_ms = max(1, int(float(CFG.get("run_broker_subscriber_block_seconds", 15) or 15) * 1000))
    while True:
        rows = cast(
            list[tuple[Any, list[tuple[Any, dict[str, Any]]]]],
            redis_client.xread({_stream_key(run_id): current_id}, count=_pty_stream_fetch_count(), block=block_ms),
        )
        if not rows:
            meta = _load_pty_meta_for_session(run_id, session_id)
            if not meta:
                yield f"data: {json.dumps({'type': 'error', 'text': _PTY_STALE_MESSAGE})}\n\n"
                return
            if meta.get("closed"):
                return
            if _prune_stale_open_pty(run_id, session_id, meta):
                yield f"data: {json.dumps({'type': 'error', 'text': _PTY_STALE_MESSAGE})}\n\n"
                return
            yield ": heartbeat\n\n"
            continue
        for _key, stream_rows in rows:
            for event_id, fields in stream_rows:
                current_id = _coerce_text(event_id)
                payload = _decode_payload(fields)
                if payload is None:
                    continue
                body = dict(payload)
                body["event_id"] = current_id
                yield f"id: {current_id}\ndata: {json.dumps(body)}\n\n"
                if body.get("type") in {"exit", "error"}:
                    return
