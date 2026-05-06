from __future__ import annotations

"""Constrained PTY lifecycle for first-pass interactive runs."""

import fcntl
import importlib
import json
import logging
import os
import pty
import re
import select
import signal
import struct
import subprocess  # nosec B404
import termios
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, cast

from config import CFG, SCANNER_PREFIX
from process import active_run_register, active_run_remove, pid_pop, pid_register, redis_client

try:
    pyte: Any | None = importlib.import_module("pyte")
except ImportError:  # pragma: no cover - exercised in deploys after requirements install
    pyte = None

log = logging.getLogger("shell")

SUDO_BIN = "/usr/bin/sudo"
KILL_BIN = "/bin/kill"
RUN_SUBPROCESS_UMASK = 0o027
_PTY_BUFFER_LIMIT = 512
_PTY_INPUT_MAX_BYTES = 4096
_PTY_HEARTBEAT_SECONDS = 15.0
_PTY_CONTROL_POLL_SECONDS = 0.2
_PTY_STREAM_FETCH_COUNT = 100
_PTY_STREAM_MAXLEN = 5000
_PTY_CAPTURE_MIN_HISTORY_LINES = 2000
_PTY_CAPTURE_MAX_HISTORY_LINES = 10000
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _plain_terminal_text(value: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))


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


def _terminal_history_line_limit(value: object) -> int:
    max_output_lines = _coerce_non_negative_int(value, 0)
    if max_output_lines <= 0:
        return _PTY_CAPTURE_MAX_HISTORY_LINES
    return max(
        _PTY_CAPTURE_MIN_HISTORY_LINES,
        min(max_output_lines * 2, _PTY_CAPTURE_MAX_HISTORY_LINES),
    )


def _trim_trailing_blank_lines(lines: list[str]) -> list[str]:
    trimmed = list(lines)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed


def _terminal_line_to_text(line: object) -> str:
    if isinstance(line, str):
        return line
    if isinstance(line, dict):
        cells: list[tuple[int, object]] = []
        for key, value in line.items():
            try:
                cells.append((int(key), value))
            except (TypeError, ValueError):
                continue
        return "".join(
            str(getattr(cell, "data", cell) or "")
            for _column, cell in sorted(cells, key=lambda item: item[0])
        )
    values = getattr(line, "values", None)
    if callable(values):
        value_cells = values()
        if isinstance(value_cells, Iterable):
            return "".join(str(getattr(cell, "data", cell) or "") for cell in value_cells)
    return str(line)


class PtyTerminalCapture:
    """Server-side terminal view used only for saved PTY history."""

    def __init__(self, rows: int, cols: int, history_lines: int):
        self.rows = rows
        self.cols = cols
        self.history_lines = max(0, int(history_lines or 0))
        self._lock = threading.Lock()
        self._screen = None
        self._stream = None
        self._stream_failed = False
        self._fallback_pending = ""
        self._fallback_lines: deque[str] = deque(maxlen=max(1, self.history_lines + rows))
        pyte_module = pyte
        if pyte_module is None:
            return
        try:
            self._screen = pyte_module.HistoryScreen(cols, rows, history=self.history_lines)
            self._stream = pyte_module.Stream(self._screen)
        except Exception:
            log.warning("PTY_CAPTURE_INIT_FAILED", exc_info=True)
            self._screen = None
            self._stream = None

    def feed(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            if self._stream is not None and not self._stream_failed:
                try:
                    self._stream.feed(text)
                    return
                except Exception:
                    self._stream_failed = True
                    self._screen = None
                    self._stream = None
                    log.warning("PTY_CAPTURE_FEED_FAILED", exc_info=True)
            self._feed_fallback(text)

    def resize(self, rows: int, cols: int) -> None:
        with self._lock:
            self.rows = rows
            self.cols = cols
            if self._screen is None:
                return
            resize = getattr(self._screen, "resize", None)
            if not callable(resize):
                return
            try:
                resize(lines=rows, columns=cols)
            except TypeError:
                resize(rows, cols)
            except Exception:
                log.warning("PTY_CAPTURE_RESIZE_FAILED", exc_info=True)

    def synthesize_entries(self) -> list[dict[str, str]]:
        with self._lock:
            scrollback = self._scrollback_lines()
            final_frame = self._final_frame_lines()
        entries = [{"text": line, "cls": ""} for line in scrollback]
        if scrollback and final_frame:
            entries.append({"text": "", "cls": "pty-marker"})
        entries.extend({"text": line, "cls": ""} for line in final_frame)
        if entries:
            return entries
        return [{"text": "[interactive PTY exited with no output]", "cls": "notice"}]

    def _feed_fallback(self, text: str) -> None:
        plain = _plain_terminal_text(text)
        if not plain:
            return
        self._fallback_pending += plain
        parts = self._fallback_pending.split("\n")
        self._fallback_pending = parts.pop() if parts else ""
        for line in parts:
            self._fallback_lines.append(line.rstrip())

    def _scrollback_lines(self) -> list[str]:
        if self._screen is not None:
            history = getattr(self._screen, "history", None)
            top = getattr(history, "top", []) if history is not None else []
            # pyte history rows are cell mappings; display rows below are already strings.
            return [_terminal_line_to_text(line).rstrip() for line in list(top)]
        lines = list(self._fallback_lines)
        if self._fallback_pending:
            lines.append(self._fallback_pending.rstrip())
        return _trim_trailing_blank_lines(lines)

    def _final_frame_lines(self) -> list[str]:
        if self._screen is None:
            return []
        display = getattr(self._screen, "display", [])
        return _trim_trailing_blank_lines([str(line).rstrip() for line in list(display)])


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
    completion_callback: Callable[["PtyRun", str, int, Sequence[dict[str, str]]], dict[str, object]] | None = None
    events: deque[PtyEvent] = field(default_factory=lambda: deque(maxlen=_PTY_BUFFER_LIMIT))
    seq: int = 0
    closed: bool = False
    exit_code: int | None = None
    control_event_id: str = "0-0"
    condition: threading.Condition = field(default_factory=threading.Condition)

    def append_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        body = dict(payload or {})
        if self.brokered:
            publish_pty_event(self.run_id, event_type, body)
            if event_type in {"exit", "error"}:
                _store_pty_meta(self, closed=True)
            return
        with self.condition:
            self.seq += 1
            self.events.append(PtyEvent(self.seq, event_type, body))
            self.condition.notify_all()


_runs: dict[str, PtyRun] = {}
_runs_lock = threading.Lock()


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
    return {
        "TERM": "xterm-256color",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    }


def _terminate_run(run: PtyRun) -> None:
    if run.proc.poll() is not None:
        return
    try:
        pgid = run.proc.pid
        if SCANNER_PREFIX:
            subprocess.run(
                [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
                timeout=5,
            )  # nosec B603
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


def pty_run_belongs_to_session(run_id: str, session_id: str) -> bool:
    meta = _load_pty_meta(run_id)
    return bool(meta and meta.get("session_id") == session_id)


def publish_pty_event(run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> str:
    if not redis_client:
        raise RuntimeError("Redis is not available for PTY events")
    data = dict(payload or {})
    data["type"] = str(event_type)
    data.setdefault("created_at", time.time())
    event_id = _coerce_text(redis_client.xadd(
        _stream_key(run_id),
        {"payload": json.dumps(data, separators=(",", ":"))},
        maxlen=_PTY_STREAM_MAXLEN,
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
                continue
            raw = str(control.get("data", "") or "").encode("utf-8", errors="replace")
            if raw and len(raw) <= _PTY_INPUT_MAX_BYTES:
                try:
                    os.write(run.master_fd, raw)
                except OSError:
                    pass
        elif action == "resize":
            run.rows = _bounded_dimension(control.get("rows"), run.rows, 10, 60)
            run.cols = _bounded_dimension(control.get("cols"), run.cols, 40, 240)
            _set_pty_size(run.master_fd, run.rows, run.cols)
            run.terminal_capture.resize(run.rows, run.cols)
            _store_pty_meta(run)


def _reader_loop(run: PtyRun, client_ip: str) -> None:
    started_dt = datetime.fromisoformat(run.started)
    last_heartbeat = time.time()
    try:
        run.append_event("started", {
            "run_id": run.run_id,
            "started": run.started,
            "interactive": True,
        })
        while True:
            _apply_pty_controls(run)
            if run.max_runtime_seconds:
                elapsed = (datetime.now(timezone.utc) - started_dt).total_seconds()
                if elapsed >= run.max_runtime_seconds and run.proc.poll() is None:
                    run.append_event("notice", {
                        "text": f"[timeout] Interactive PTY exceeded {run.max_runtime_seconds}s limit and was killed.",
                    })
                    _terminate_run(run)

            ready, _, _ = select.select([run.master_fd], [], [], _PTY_CONTROL_POLL_SECONDS)
            if ready:
                try:
                    chunk = os.read(run.master_fd, 4096)
                except OSError:
                    chunk = b""
                if chunk:
                    text = chunk.decode("utf-8", errors="replace")
                    run.terminal_capture.feed(text)
                    run.append_event("output", {"text": text})
                    continue
            if run.proc.poll() is not None:
                break
            now = time.time()
            if now - last_heartbeat >= _PTY_HEARTBEAT_SECONDS:
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
        log.info("RUN_END", extra={
            "run_id": run.run_id,
            "session": run.session_id,
            "ip": client_ip,
            "exit_code": code,
            "elapsed": elapsed,
            "cmd": run.command,
            "cmd_type": "pty",
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
    completion_callback: Callable[[PtyRun, str, int, Sequence[dict[str, str]]], dict[str, object]] | None = None,
) -> PtyRun:
    default_rows_i = _bounded_dimension(default_rows, 24, 10, 60)
    default_cols_i = _bounded_dimension(default_cols, 100, 40, 240)
    rows_i = _bounded_dimension(rows, default_rows_i, 10, 60)
    cols_i = _bounded_dimension(cols, default_cols_i, 40, 240)
    terminal_history_lines = _terminal_history_line_limit(CFG.get("max_output_lines", 0))
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    master_fd, slave_fd = pty.openpty()
    _set_pty_size(slave_fd, rows_i, cols_i)
    try:
        proc = subprocess.Popen(
            SCANNER_PREFIX + argv if SCANNER_PREFIX else argv,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            shell=False,
            close_fds=True,
            preexec_fn=_prepare_child,
            env=_command_env(),
        )  # nosec B603
    except Exception:
        try:
            os.close(master_fd)
        except OSError:
            pass
        raise
    finally:
        try:
            os.close(slave_fd)
        except OSError:
            pass

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
        completion_callback=completion_callback,
    )
    with _runs_lock:
        _runs[run_id] = run
    _store_pty_meta(run)
    pid_register(run_id, proc.pid)
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
    log.info("RUN_START", extra={
        "run_id": run_id,
        "session": session_id,
        "ip": client_ip,
        "pid": proc.pid,
        "cmd": command,
        "cmd_type": "pty",
    })
    threading.Thread(
        target=_reader_loop,
        args=(run, client_ip),
        name=f"pty-run-{run_id[:8]}",
        daemon=True,
    ).start()
    return run


def get_pty_run(run_id: str, session_id: str) -> PtyRun | None:
    with _runs_lock:
        run = _runs.get(run_id)
    if not run or run.session_id != session_id:
        return None
    return run


def write_pty_input(run_id: str, session_id: str, data: object) -> tuple[bool, str]:
    meta = _load_pty_meta(run_id)
    if not meta or meta.get("session_id") != session_id:
        return False, "Run not found"
    if meta.get("closed"):
        return False, "Run is closed"
    text = str(data or "")
    if not text:
        return True, ""
    raw = text.encode("utf-8", errors="replace")
    if len(raw) > _PTY_INPUT_MAX_BYTES:
        return False, "Input is too large for this interactive run"
    if redis_client:
        _queue_pty_control(run_id, "input", {"data": text})
        return True, ""
    run = get_pty_run(run_id, session_id)
    if not run:
        return False, "Run not found"
    if not run.allow_input:
        return False, "This interactive run does not accept input"
    try:
        os.write(run.master_fd, raw)
        return True, ""
    except OSError as exc:
        return False, str(exc)


def resize_pty(run_id: str, session_id: str, rows: object, cols: object) -> tuple[bool, str, int, int]:
    meta = _load_pty_meta(run_id)
    if not meta or meta.get("session_id") != session_id:
        return False, "Run not found", 0, 0
    if meta.get("closed"):
        return False, "Run is closed", 0, 0
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
                run.condition.wait(timeout=_PTY_HEARTBEAT_SECONDS)
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
    if not pty_run_belongs_to_session(run_id, session_id):
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
            redis_client.xread({_stream_key(run_id): current_id}, count=_PTY_STREAM_FETCH_COUNT, block=block_ms),
        )
        if not rows:
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
