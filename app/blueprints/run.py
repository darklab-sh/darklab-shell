"""
Execution routes: /run (SSE command streaming) and /kill.

The /run route is rate-limited per-IP via the shared limiter singleton.
"""

import json
import logging
import os
import re
import selectors
import codecs
import shutil
import signal
import subprocess  # nosec B404
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import cast

from flask import Blueprint, Response, jsonify, request

from commands import (
    CommandValidationResult,
    command_root,
    is_command_allowed,
    parse_synthetic_postfilter,
    rewrite_command,
    runtime_missing_command_message,
    runtime_missing_command_name,
    validate_command,
)
from config import CFG, SCANNER_PREFIX
from database import db_connect
from extensions import limiter
from fake_commands import (
    execute_fake_command,
    resolve_fake_command,
    resolves_exact_special_fake_command,
)
from helpers import get_client_ip, get_log_session_id, get_session_id
from process import active_run_register, active_run_remove, pid_pop, pid_register
from run_output_store import RunOutputCapture, load_full_output_entries
from output_signals import OutputSignalClassifier
from session_variables import SessionVariableError, expand_session_variables

log = logging.getLogger("shell")

run_bp = Blueprint("run", __name__)


def _validate_command_for_run(command: str, session_id: str) -> CommandValidationResult:
    # Several route tests monkeypatch this module's legacy is_command_allowed
    # symbol to keep subprocess behavior focused. Honor that seam while the
    # runtime path uses the richer validator for workspace rewrites.
    if getattr(is_command_allowed, "__module__", "") != "commands":
        allowed, reason = is_command_allowed(command)
        return CommandValidationResult(
            allowed,
            reason,
            display_command=command,
            exec_command=command,
        )
    return validate_command(command, session_id=session_id, cfg=CFG)


def _workspace_notice_lines(validation: CommandValidationResult) -> list[str]:
    notices: list[str] = []
    for path in validation.workspace_reads:
        notices.append(f"[workspace] reading {path}")
    for path in validation.workspace_writes:
        notices.append(f"[workspace] writing {path}")
    return notices


SHELL_BIN = shutil.which("sh") or "/bin/sh"
SUDO_BIN  = shutil.which("sudo") or "/usr/bin/sudo"
KILL_BIN  = shutil.which("kill") or "/bin/kill"

CLIENT_SIDE_RUN_ROOTS = {
    "cat",
    "cd",
    "config",
    "file",
    "grep",
    "head",
    "ll",
    "ls",
    "mkdir",
    "pwd",
    "rm",
    "session-token",
    "sort",
    "tail",
    "theme",
    "uniq",
    "wc",
}


def _variable_notice_line(expanded_command: str, used_names: tuple[str, ...]) -> str:
    variables = ", ".join(f"${name}" for name in used_names)
    return f"[vars] expanded {variables}: {expanded_command}"
RUN_SUBPROCESS_UMASK = 0o027
DETACHED_DRAIN_GRACE_SECONDS = 30
DETACHED_DRAIN_FALLBACK_TIMEOUT_SECONDS = 3600


def _prepare_run_child() -> None:
    os.setsid()
    os.umask(RUN_SUBPROCESS_UMASK)


def _detached_drain_ceiling_seconds(command_timeout: int | float | None) -> int | float:
    base_timeout = command_timeout if command_timeout else DETACHED_DRAIN_FALLBACK_TIMEOUT_SECONDS
    return base_timeout + DETACHED_DRAIN_GRACE_SECONDS


def _terminate_process_group(proc) -> None:
    pgid = os.getpgid(proc.pid)
    if SCANNER_PREFIX:
        subprocess.run(
            [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
            timeout=5
        )  # nosec B603
    else:
        os.killpg(pgid, signal.SIGTERM)


# ── Run output helpers ────────────────────────────────────────────────────────

def _run_output_capture(run_id):
    # Keep an inline preview for fast history reads, but spill large/full output
    # into compressed artifacts once a run exceeds the preview window.
    return RunOutputCapture(
        run_id=run_id,
        preview_limit=CFG["max_output_lines"],
        persist_full_output=CFG.get("persist_full_run_output", False),
        full_output_max_bytes=CFG.get("full_output_max_bytes", 0),
    )


def _capture_add_line_with_signals(capture, classifier, text, *, cls="", ts_clock="", ts_elapsed=""):
    metadata = classifier.classify_line(text, cls=cls) if classifier else {}
    capture.add_line(
        text,
        cls=cls,
        ts_clock=ts_clock,
        ts_elapsed=ts_elapsed,
        signals=metadata.get("signals") if isinstance(metadata.get("signals"), list) else None,
        line_index=metadata.get("line_index") if isinstance(metadata.get("line_index"), int) else None,
        command_root=str(metadata.get("command_root", "")),
        target=str(metadata.get("target", "")),
    )
    return metadata


def _sse_output_event(event_type, text, *, cls="", metadata=None):
    payload = {"type": event_type, "text": text}
    if cls:
        payload["cls"] = cls
    if isinstance(metadata, dict):
        if isinstance(metadata.get("signals"), list):
            payload["signals"] = metadata["signals"]
        if isinstance(metadata.get("line_index"), int):
            payload["line_index"] = metadata["line_index"]
        if isinstance(metadata.get("command_root"), str):
            payload["command_root"] = metadata["command_root"]
        if isinstance(metadata.get("target"), str):
            payload["target"] = metadata["target"]
    return f"data: {json.dumps(payload)}\n\n"


def _extract_output_search_text(preview_lines):
    return "\n".join(
        str(line.get("text", "")) if isinstance(line, dict) else str(line)
        for line in preview_lines
        if line is not None
    )


def _save_completed_run(run_id, session_id, command, run_started, finished_iso, exit_code, capture):
    # Persist preview text and artifact metadata together so history/permalink
    # readers never observe half-written run state.
    capture.finalize()
    try:
        preview_lines = list(capture.preview_lines)
        # Index full output when available so early lines of long runs are searchable.
        # Falls back to preview if the artifact can't be read.
        if capture.full_output_available and capture.artifact_rel_path:
            try:
                full_entries = load_full_output_entries(capture.artifact_rel_path)
                search_text = _extract_output_search_text(full_entries)
            except Exception:
                search_text = _extract_output_search_text(preview_lines)
        else:
            search_text = _extract_output_search_text(preview_lines)
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs "
                "("
                "id, session_id, command, started, finished, exit_code, output, output_preview, "
                "preview_truncated, output_line_count, full_output_available, full_output_truncated, "
                "output_search_text"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    session_id,
                    command,
                    run_started,
                    finished_iso,
                    exit_code,
                    None,
                    json.dumps(preview_lines),
                    int(capture.preview_truncated),
                    capture.output_line_count,
                    int(capture.full_output_available),
                    int(capture.full_output_truncated),
                    search_text,
                )
            )
            if capture.full_output_available and capture.artifact_rel_path:
                conn.execute(
                    "INSERT OR REPLACE INTO run_output_artifacts "
                    "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        capture.artifact_rel_path,
                        "gzip",
                        capture.full_output_bytes,
                        capture.output_line_count,
                        int(capture.full_output_truncated),
                        finished_iso,
                    )
                )
            conn.commit()
    except Exception:
        log.error("RUN_SAVED_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "cmd": command,
        })


def _finalize_completed_run(run_id, session_id, client_ip, original_command, run_started, exit_code, capture, *, cmd_type="real"):
    finished = datetime.now(timezone.utc)
    elapsed = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
    log.info("RUN_END", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "exit_code": exit_code, "elapsed": elapsed, "cmd": original_command,
        "cmd_type": cmd_type,
    })
    _save_completed_run(
        run_id, session_id, original_command, run_started,
        finished.isoformat(), exit_code, capture,
    )
    return elapsed


def _timeout_notice(command_timeout):
    return f"[timeout] Command exceeded {command_timeout}s limit and was killed."


def _stdout_ready(stream, timeout):
    sel = selectors.DefaultSelector()
    try:
        sel.register(stream, selectors.EVENT_READ)
        return bool(sel.select(timeout))
    finally:
        sel.close()


def _make_nonblocking_stream_reader(stream):
    fileno = getattr(stream, "fileno", None)
    if not callable(fileno):
        return {"stream": stream, "fd": None, "decoder": None, "pending": ""}
    fd = fileno()
    if not isinstance(fd, int):
        return {"stream": stream, "fd": None, "decoder": None, "pending": ""}
    fd = cast(int, fd)
    try:
        os.set_blocking(fd, False)
    except OSError as exc:
        log.warning("RUN_STREAM_NONBLOCKING_UNAVAILABLE", extra={"fd": fd, "error": str(exc)})
        return {"stream": stream, "fd": None, "decoder": None, "pending": ""}
    encoding = getattr(stream, "encoding", None) or "utf-8"
    errors = getattr(stream, "errors", None) or "replace"
    return {
        "fd": fd,
        "decoder": codecs.getincrementaldecoder(encoding)(errors=errors),
        "pending": "",
    }


def _read_available_stream_lines(reader_state, *, finalize=False):
    if reader_state.get("fd") is None:
        line = reader_state["stream"].readline()
        if line:
            return [line], False
        return [], True

    lines = []
    pending = str(reader_state.get("pending", ""))
    eof = False

    while True:
        try:
            chunk = os.read(reader_state["fd"], 4096)
        except BlockingIOError:
            break
        if not chunk:
            eof = True
            break
        pending += reader_state["decoder"].decode(chunk)
        split = pending.splitlines(keepends=True)
        if split and not split[-1].endswith(("\n", "\r")):
            pending = split.pop()
        else:
            pending = ""
        lines.extend(split)

    if finalize:
        pending += reader_state["decoder"].decode(b"", final=True)
        if pending:
            lines.append(pending)
            pending = ""

    reader_state["pending"] = pending
    return lines, eof


def _cleanup_proc_stream(proc):
    stdout = getattr(proc, "stdout", None)
    if stdout is not None and not getattr(stdout, "closed", False):
        try:
            stdout.close()
        except Exception:
            pass
    if getattr(proc, "returncode", None) is None:
        _wait_for_proc_exit_code(proc)


def _wait_for_proc_exit_code(proc):
    if getattr(proc, "returncode", None) is not None:
        return proc.returncode
    try:
        return proc.wait(timeout=5)
    except TypeError:
        return proc.wait()
    except Exception:
        return getattr(proc, "returncode", None)


def _synthetic_run_response(original_command, session_id, client_ip, events, exit_code=0, *, cmd_type="builtin"):
    # Synthetic commands deliberately reuse the same persistence/logging path as
    # real commands so the shell treats them as first-class runs.
    run_id      = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = _run_output_capture(run_id)
    signal_classifier = OutputSignalClassifier(original_command, cmd_type=cmd_type)

    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": 0, "cmd": original_command, "cmd_type": cmd_type,
    })

    def generate():
        try:
            yield f"data: {json.dumps({'type': 'started', 'run_id': run_id})}\n\n"
            run_started_dt = datetime.fromisoformat(run_started)
            for event in events:
                if event.get("type") == "output":
                    line = event.get("text", "")
                    line_dt = datetime.now(timezone.utc)
                    metadata = _capture_add_line_with_signals(
                        capture,
                        signal_classifier,
                        line,
                        cls=str(event.get("cls", "")),
                        ts_clock=line_dt.strftime("%H:%M:%S"),
                        ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                    )
                    yield _sse_output_event(
                        "output",
                        line + "\n",
                        cls=str(event.get("cls", "")),
                        metadata=metadata,
                    )
                elif event.get("type") == "clear":
                    yield f"data: {json.dumps({'type': 'clear'})}\n\n"

            finished = datetime.now(timezone.utc)
            elapsed = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
            log.info("RUN_END", extra={
                "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                "exit_code": exit_code, "elapsed": elapsed, "cmd": original_command,
                "cmd_type": cmd_type,
            })
            yield f"data: {json.dumps({
                'type': 'exit',
                'code': exit_code,
                'elapsed': elapsed,
                'preview_truncated': capture.preview_truncated,
                'output_line_count': capture.output_line_count,
                'full_output_available': capture.full_output_available,
            })}\n\n"
            _save_completed_run(
                run_id, session_id, original_command, run_started,
                finished.isoformat(), exit_code, capture,
            )
        except Exception as e:
            log.error("RUN_STREAM_ERROR", exc_info=True, extra={
                "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                "cmd": original_command,
            })
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


def _fake_run_response(original_command, session_id, client_ip):
    events, exit_code = execute_fake_command(original_command, session_id)
    return _synthetic_run_response(original_command, session_id, client_ip, events, exit_code)


def _client_side_run_command_allowed(command: str) -> bool:
    root = command.strip().split(maxsplit=1)[0].lower() if command.strip() else ""
    return root in CLIENT_SIDE_RUN_ROOTS


def _normalize_client_side_run_lines(lines):
    if not isinstance(lines, list):
        return []
    max_lines = int(CFG.get("max_output_lines", 0) or 0)
    source_lines = lines if max_lines <= 0 else lines[:max_lines]
    normalized = []
    for item in source_lines:
        if isinstance(item, dict):
            text = str(item.get("text", ""))
            cls = str(item.get("cls", ""))
        else:
            text = str(item)
            cls = ""
        normalized.append({"text": text, "cls": cls, "tsC": "", "tsE": ""})
    return normalized


@run_bp.route("/run/client", methods=["POST"])
def save_client_side_run():
    """Persist browser-owned built-in command output as a normal history run."""
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    command = data.get("command", "")
    if not isinstance(command, str):
        return jsonify({"error": "Command must be a string"}), 400
    command = command.strip()
    if not command:
        return jsonify({"error": "No command provided"}), 400
    if not _client_side_run_command_allowed(command):
        return jsonify({"error": "Client-side run persistence is limited to browser-owned built-ins"}), 403

    try:
        exit_code = int(data.get("exit_code", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "exit_code must be an integer"}), 400

    raw_lines = data.get("lines", [])
    raw_line_count = len(raw_lines) if isinstance(raw_lines, list) else 0
    lines = _normalize_client_side_run_lines(raw_lines)
    preview_truncated = int(raw_line_count > len(lines))
    session_id = get_session_id()
    client_ip = get_client_ip()
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    finished = datetime.now(timezone.utc)
    output_search_text = _extract_output_search_text(lines)

    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": 0, "cmd": command, "cmd_type": "client-builtin",
    })

    with db_connect() as conn:
        conn.execute(
            "INSERT INTO runs "
            "("
            "id, session_id, command, started, finished, exit_code, output, output_preview, "
            "preview_truncated, output_line_count, full_output_available, full_output_truncated, "
            "output_search_text"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                session_id,
                command,
                started.isoformat(),
                finished.isoformat(),
                exit_code,
                None,
                json.dumps(lines),
                preview_truncated,
                raw_line_count,
                0,
                0,
                output_search_text,
            ),
        )
        conn.commit()

    elapsed = round((finished - started).total_seconds(), 1)
    log.info("RUN_END", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "exit_code": exit_code, "elapsed": elapsed, "cmd": command,
        "cmd_type": "client-builtin",
    })
    return jsonify({"ok": True, "run_id": run_id, "output_line_count": raw_line_count})


class _SyntheticPostFilterStageProcessor:
    """Apply one narrow app-native post-filter stage without enabling pipes."""

    def __init__(self, spec):
        self.spec = spec or {}
        self.kind = self.spec.get("kind")
        self._count = 0
        self._emitted = 0
        self._tail_buffer = deque(maxlen=int(self.spec.get("count", 0) or 0))
        self._grep_match = None
        self._line_buffer = []

        if self.kind == "grep":
            pattern = self.spec["pattern"]
            flags = re.IGNORECASE if self.spec.get("ignore_case") else 0
            if self.spec.get("extended"):
                try:
                    compiled = re.compile(pattern, flags)
                except re.error as exc:
                    raise ValueError(f"Invalid synthetic grep regex: {exc}") from exc

                def _matches(line):
                    return bool(compiled.search(line))
            else:
                needle = pattern.lower() if self.spec.get("ignore_case") else pattern

                def _matches(line):
                    haystack = line.lower() if self.spec.get("ignore_case") else line
                    return needle in haystack

            if self.spec.get("invert_match"):
                self._grep_match = lambda line: not _matches(line)
            else:
                self._grep_match = _matches

    def process_output_line(self, line: str) -> list[str]:
        if not self.kind:
            return [line]

        normalized = str(line).rstrip("\n")
        if self.kind == "grep":
            return [line] if self._grep_match and self._grep_match(normalized) else []

        if self.kind == "head":
            if self._emitted >= int(self.spec.get("count", 0) or 0):
                return []
            self._emitted += 1
            return [line]

        if self.kind == "tail":
            self._tail_buffer.append(line)
            return []

        if self.kind == "wc_l":
            self._count += 1
            return []

        if self.kind in ("sort", "uniq"):
            self._line_buffer.append(line)
            return []

        return [line]

    def finalize_output_lines(self) -> list[str]:
        if self.kind == "tail":
            return list(self._tail_buffer)
        if self.kind == "wc_l":
            return [str(self._count)]

        if self.kind == "sort":
            numeric = self.spec.get("numeric", False)

            def _sort_key(ln):
                s = ln.rstrip("\n").lstrip()
                if numeric:
                    m = re.match(r'^[-+]?\d+\.?\d*', s)
                    return float(m.group(0)) if m else float("-inf")
                return s.lower()

            result = sorted(self._line_buffer, key=_sort_key,
                            reverse=self.spec.get("reverse", False))
            if self.spec.get("unique"):
                seen: set = set()
                deduped = []
                for ln in result:
                    key = ln.rstrip("\n")
                    if key not in seen:
                        seen.add(key)
                        deduped.append(ln)
                result = deduped
            return result

        if self.kind == "uniq":
            result = []
            prev = None
            if self.spec.get("count"):
                groups: list[tuple[int, str]] = []
                cnt = 0
                for ln in self._line_buffer:
                    n = ln.rstrip("\n")
                    if n == prev:
                        cnt += 1
                    else:
                        if prev is not None:
                            groups.append((cnt, prev))
                        prev = n
                        cnt = 1
                if prev is not None:
                    groups.append((cnt, prev))
                return [f"{c:7d} {ln}\n" for c, ln in groups]
            for ln in self._line_buffer:
                n = ln.rstrip("\n")
                if n != prev:
                    result.append(ln)
                    prev = n
            return result

        return []


class _SyntheticPostFilterProcessor:
    """Apply one or more narrow app-native post-filter stages in order."""

    def __init__(self, spec):
        self.spec = spec or {}
        stages = self.spec.get("stages") if isinstance(self.spec, dict) else None
        if stages:
            self.stages = [_SyntheticPostFilterStageProcessor(stage) for stage in stages]
        else:
            self.stages = [_SyntheticPostFilterStageProcessor(self.spec)]

    def process_output_line(self, line: str) -> list[str]:
        lines = [line]
        for stage in self.stages:
            next_lines = []
            for current in lines:
                next_lines.extend(stage.process_output_line(current))
            lines = next_lines
        return lines

    def finalize_output_lines(self) -> list[str]:
        lines: list[str] = []
        for stage in self.stages:
            next_lines = []
            for current in lines:
                next_lines.extend(stage.process_output_line(current))
            next_lines.extend(stage.finalize_output_lines())
            lines = next_lines
        return lines


# ── Routes ────────────────────────────────────────────────────────────────────

@run_bp.route("/run", methods=["POST"])
@limiter.limit(lambda: (
    f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"
))
def run_command():
    # Stream newline-delimited SSE events so the browser can render output in
    # real time without waiting for the subprocess to finish.
    data             = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    original_command = data.get("command", "")
    session_id       = get_session_id()
    client_ip        = get_client_ip()
    if not isinstance(original_command, str):
        return jsonify({"error": "Command must be a string"}), 400
    original_command = original_command.strip()
    if not original_command:
        return jsonify({"error": "No command provided"}), 400
    if resolves_exact_special_fake_command(original_command):
        return _fake_run_response(original_command, session_id, client_ip)
    expanded_command = original_command
    variable_notice = ""
    if command_root(original_command) != "var":
        try:
            expansion = expand_session_variables(original_command, session_id)
            expanded_command = expansion.command
            if expanded_command != original_command:
                variable_notice = _variable_notice_line(expanded_command, expansion.used_names)
        except SessionVariableError as exc:
            log.warning("CMD_DENIED", extra={
                "ip": client_ip, "session": get_log_session_id(session_id),
                "cmd": original_command, "reason": str(exc),
            })
            return jsonify({"error": str(exc)}), 403

    postfilter_spec, postfilter_error = parse_synthetic_postfilter(expanded_command)
    if postfilter_error:
        log.warning("CMD_DENIED", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command, "reason": postfilter_error,
        })
        return jsonify({"error": postfilter_error}), 403
    execution_command = postfilter_spec["base_command"] if postfilter_spec else expanded_command
    if postfilter_spec:
        stage_kinds = [stage.get("kind") for stage in postfilter_spec.get("stages", []) if stage.get("kind")]
        log.debug("CMD_PIPE", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command,
            "kind": " -> ".join(stage_kinds) if stage_kinds else postfilter_spec.get("kind"),
        })
    try:
        postfilter = _SyntheticPostFilterProcessor(postfilter_spec)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 403

    if resolve_fake_command(execution_command):
        events, exit_code = execute_fake_command(execution_command, session_id)
        if variable_notice:
            events = [{"type": "output", "text": variable_notice, "cls": "notice"}] + events
        filtered_events = []
        for event in events:
            if event.get("type") != "output":
                filtered_events.append(event)
                continue
            for filtered_line in postfilter.process_output_line(str(event.get("text", ""))):
                filtered_event = dict(event)
                filtered_event["text"] = filtered_line.rstrip("\n")
                filtered_events.append(filtered_event)
        for filtered_line in postfilter.finalize_output_lines():
            filtered_events.append({"type": "output", "text": filtered_line.rstrip("\n")})
        events = filtered_events
        return _synthetic_run_response(original_command, session_id, client_ip, events, exit_code)

    validation = _validate_command_for_run(execution_command, session_id)
    if not validation.allowed:
        log.warning("CMD_DENIED", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command, "reason": validation.reason,
        })
        return jsonify({"error": validation.reason}), 403
    execution_command = validation.exec_command or execution_command

    command, notice = rewrite_command(execution_command)
    if command != execution_command:
        log.info("CMD_REWRITE", extra={
            "ip": client_ip, "original": original_command, "rewritten": command,
        })

    missing_runtime = runtime_missing_command_name(command)
    if missing_runtime:
        log.warning("CMD_MISSING", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command, "missing": missing_runtime,
        })
        return _synthetic_run_response(
            original_command,
            session_id,
            client_ip,
            [{"type": "output", "text": runtime_missing_command_message(missing_runtime)}],
            127,
            cmd_type="missing",
        )

    run_id      = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = _run_output_capture(run_id)
    signal_classifier = OutputSignalClassifier(execution_command, cmd_type="real")

    # Start the process immediately — before the generator runs — so the PID
    # is registered before any kill request could arrive
    try:
        proc = subprocess.Popen(
            SCANNER_PREFIX + [SHELL_BIN, "-c", command] if SCANNER_PREFIX
            else [SHELL_BIN, "-c", command],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=_prepare_run_child,
        )  # nosec B603
    except Exception as e:
        log.error("RUN_SPAWN_ERROR", exc_info=True, extra={
            "ip": client_ip, "session": get_log_session_id(session_id), "cmd": original_command,
        })
        return jsonify({"error": str(e)}), 500

    pid_register(run_id, proc.pid)
    active_run_register(run_id, proc.pid, session_id, original_command, run_started)
    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": proc.pid, "cmd": original_command, "cmd_type": "real",
    })

    # Heartbeat interval in seconds — keeps the SSE connection alive through
    # nginx and browser idle timeouts when a command produces no output
    HEARTBEAT_INTERVAL = CFG["heartbeat_interval_seconds"]
    COMMAND_TIMEOUT    = CFG["command_timeout_seconds"] or None  # None = no timeout

    def _continue_run_detached():
        try:
            run_started_dt = datetime.fromisoformat(run_started)
            if proc.stdout is None:
                raise RuntimeError("Process stdout pipe was not created")
            stream_reader = _make_nonblocking_stream_reader(proc.stdout)
            detached_started_monotonic = time.monotonic()
            detached_ceiling = _detached_drain_ceiling_seconds(COMMAND_TIMEOUT)
            while True:
                detached_elapsed = time.monotonic() - detached_started_monotonic
                if detached_ceiling and detached_elapsed >= detached_ceiling:
                    try:
                        _terminate_process_group(proc)
                    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                        pass
                    log.warning("DETACHED_DRAIN_TIMEOUT", extra={
                        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                        "timeout": detached_ceiling, "cmd": original_command,
                    })
                    break
                if COMMAND_TIMEOUT:
                    now_dt = datetime.now(timezone.utc)
                    elapsed = (now_dt - run_started_dt).total_seconds()
                    if elapsed >= COMMAND_TIMEOUT:
                        try:
                            pgid = os.getpgid(proc.pid)
                            if SCANNER_PREFIX:
                                subprocess.run(
                                    [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
                                    timeout=5
                                )  # nosec B603
                            else:
                                os.killpg(pgid, signal.SIGTERM)
                        except (ProcessLookupError, OSError):
                            pass
                        timeout_msg = _timeout_notice(COMMAND_TIMEOUT)
                        line_dt = now_dt
                        _capture_add_line_with_signals(
                            capture,
                            signal_classifier,
                            timeout_msg,
                            cls="notice",
                            ts_clock=line_dt.strftime("%H:%M:%S"),
                            ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                        )
                        log.warning("CMD_TIMEOUT", extra={
                            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                            "timeout": COMMAND_TIMEOUT, "cmd": original_command,
                        })
                        break
                if _stdout_ready(proc.stdout, HEARTBEAT_INTERVAL):
                    lines, eof = _read_available_stream_lines(stream_reader)
                    if not lines and eof:
                        break
                    for line in lines:
                        filtered_lines = postfilter.process_output_line(line)
                        for filtered_line in filtered_lines:
                            line_dt = datetime.now(timezone.utc)
                            _capture_add_line_with_signals(
                                capture,
                                signal_classifier,
                                filtered_line,
                                ts_clock=line_dt.strftime("%H:%M:%S"),
                                ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                            )
                else:
                    if proc.poll() is not None:
                        break

            trailing_lines, _ = _read_available_stream_lines(stream_reader, finalize=True)
            for line in trailing_lines:
                filtered_lines = postfilter.process_output_line(line)
                for filtered_line in filtered_lines:
                    line_dt = datetime.now(timezone.utc)
                    _capture_add_line_with_signals(
                        capture,
                        signal_classifier,
                        filtered_line,
                        ts_clock=line_dt.strftime("%H:%M:%S"),
                        ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                    )
            for filtered_line in postfilter.finalize_output_lines():
                line_dt = datetime.now(timezone.utc)
                _capture_add_line_with_signals(
                    capture,
                    signal_classifier,
                    filtered_line,
                    ts_clock=line_dt.strftime("%H:%M:%S"),
                    ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                )
            exit_code = _wait_for_proc_exit_code(proc)
            _finalize_completed_run(
                run_id, session_id, client_ip, original_command, run_started, exit_code, capture,
            )
        except Exception:
            log.error("RUN_STREAM_ERROR", exc_info=True, extra={
                "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                "cmd": original_command,
            })
        finally:
            _cleanup_proc_stream(proc)
            pid_pop(run_id)
            active_run_remove(run_id)

    def generate():
        detached = False
        try:
            # Send the run_id first so the client can call /kill
            yield f"data: {json.dumps({'type': 'started', 'run_id': run_id})}\n\n"
            run_started_dt = datetime.fromisoformat(run_started)

            if variable_notice:
                notice_dt = datetime.now(timezone.utc)
                metadata = _capture_add_line_with_signals(
                    capture,
                    signal_classifier,
                    variable_notice,
                    cls="notice",
                    ts_clock=notice_dt.strftime("%H:%M:%S"),
                    ts_elapsed=f"+{(notice_dt - run_started_dt).total_seconds():.1f}s",
                )
                yield _sse_output_event("notice", variable_notice, metadata=metadata)

            # If the command was rewritten, surface a notice to the user
            if notice:
                notice_dt = datetime.now(timezone.utc)
                metadata = _capture_add_line_with_signals(
                    capture,
                    signal_classifier,
                    f"[notice] {notice}",
                    cls="notice",
                    ts_clock=notice_dt.strftime("%H:%M:%S"),
                    ts_elapsed=f"+{(notice_dt - run_started_dt).total_seconds():.1f}s",
                )
                yield _sse_output_event("notice", notice, metadata=metadata)

            for workspace_notice in _workspace_notice_lines(validation):
                notice_dt = datetime.now(timezone.utc)
                metadata = _capture_add_line_with_signals(
                    capture,
                    signal_classifier,
                    workspace_notice,
                    cls="notice",
                    ts_clock=notice_dt.strftime("%H:%M:%S"),
                    ts_elapsed=f"+{(notice_dt - run_started_dt).total_seconds():.1f}s",
                )
                yield _sse_output_event("notice", workspace_notice, metadata=metadata)

            if proc.stdout is None:
                raise RuntimeError("Process stdout pipe was not created")
            stream_reader = _make_nonblocking_stream_reader(proc.stdout)
            while True:
                # Check timeout at the top of every iteration so it fires even
                # during continuous output, not only during idle heartbeat periods.
                if COMMAND_TIMEOUT:
                    now_dt = datetime.now(timezone.utc)
                    elapsed = (now_dt - run_started_dt).total_seconds()
                    if elapsed >= COMMAND_TIMEOUT:
                        try:
                            pgid = os.getpgid(proc.pid)
                            if SCANNER_PREFIX:
                                subprocess.run(
                                    [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
                                    timeout=5
                                )  # nosec B603
                            else:
                                os.killpg(pgid, signal.SIGTERM)
                        except (ProcessLookupError, OSError):
                            pass
                        timeout_msg = _timeout_notice(COMMAND_TIMEOUT)
                        log.warning("CMD_TIMEOUT", extra={
                            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                            "timeout": COMMAND_TIMEOUT, "cmd": original_command,
                        })
                        line_dt = now_dt
                        metadata = _capture_add_line_with_signals(
                            capture,
                            signal_classifier,
                            timeout_msg,
                            cls="notice",
                            ts_clock=line_dt.strftime("%H:%M:%S"),
                            ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                        )
                        yield _sse_output_event("notice", timeout_msg, metadata=metadata)
                        break
                # Wait up to HEARTBEAT_INTERVAL seconds for output
                if _stdout_ready(proc.stdout, HEARTBEAT_INTERVAL):
                    lines, eof = _read_available_stream_lines(stream_reader)
                    if not lines and eof:
                        # EOF — process has finished
                        break
                    if not lines:
                        # Data is readable but not line-complete yet (for example,
                        # a progress renderer without a newline). Keep the browser
                        # stall timer fed while preserving the buffered partial line.
                        if proc.poll() is not None:
                            break
                        yield ": heartbeat\n\n"
                        continue
                    for line in lines:
                        filtered_lines = postfilter.process_output_line(line)
                        for filtered_line in filtered_lines:
                            line_dt = datetime.now(timezone.utc)
                            metadata = _capture_add_line_with_signals(
                                capture,
                                signal_classifier,
                                filtered_line,
                                ts_clock=line_dt.strftime("%H:%M:%S"),
                                ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                            )
                            yield _sse_output_event("output", filtered_line, metadata=metadata)
                else:
                    # No output within the interval — send a heartbeat comment
                    # to keep nginx and the browser from treating the connection as idle
                    if proc.poll() is not None:
                        break
                    yield ": heartbeat\n\n"

            trailing_lines, _ = _read_available_stream_lines(stream_reader, finalize=True)
            for line in trailing_lines:
                filtered_lines = postfilter.process_output_line(line)
                for filtered_line in filtered_lines:
                    line_dt = datetime.now(timezone.utc)
                    metadata = _capture_add_line_with_signals(
                        capture,
                        signal_classifier,
                        filtered_line,
                        ts_clock=line_dt.strftime("%H:%M:%S"),
                        ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                    )
                    yield _sse_output_event("output", filtered_line, metadata=metadata)
            for filtered_line in postfilter.finalize_output_lines():
                line_dt = datetime.now(timezone.utc)
                metadata = _capture_add_line_with_signals(
                    capture,
                    signal_classifier,
                    filtered_line,
                    ts_clock=line_dt.strftime("%H:%M:%S"),
                    ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                )
                yield _sse_output_event("output", filtered_line, metadata=metadata)
            exit_code = _wait_for_proc_exit_code(proc)
            elapsed = _finalize_completed_run(
                run_id, session_id, client_ip, original_command, run_started, exit_code, capture,
            )
            yield f"data: {json.dumps({
                'type': 'exit',
                'code': exit_code,
                'elapsed': elapsed,
                'preview_truncated': capture.preview_truncated,
                'output_line_count': capture.output_line_count,
                'full_output_available': capture.full_output_available,
            })}\n\n"
        except GeneratorExit:
            detached = True
            threading.Thread(
                target=_continue_run_detached,
                name=f"run-drain-{run_id[:8]}",
                daemon=True,
            ).start()
            raise
        except Exception as e:
            log.error("RUN_STREAM_ERROR", exc_info=True, extra={
                "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                "cmd": original_command,
            })
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        finally:
            if not detached:
                _cleanup_proc_stream(proc)
                pid_pop(run_id)
                active_run_remove(run_id)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@run_bp.route("/kill", methods=["POST"])
def kill_command():
    data      = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    run_id    = data.get("run_id", "")
    client_ip = get_client_ip()
    if not isinstance(run_id, str):
        return jsonify({"error": "run_id must be a string"}), 400
    pid       = pid_pop(run_id)
    if not pid:
        log.debug("KILL_MISS", extra={"ip": client_ip, "run_id": run_id})
        return jsonify({"error": "No such process"}), 404
    active_run_remove(run_id)
    try:
        # Subprocesses call os.setsid() during child setup, which makes PGID
        # == PID at creation time. Use the stored PID directly as the
        # PGID rather than calling os.getpgid() — if the subprocess has
        # already exited and its PID was reused (e.g. by a new Gunicorn
        # worker), os.getpgid() would return the wrong PGID and we would
        # accidentally send SIGTERM to a gunicorn worker process group.
        # Using the original PID as the PGID is safe: if the process group
        # no longer exists the signal fails with ESRCH instead of hitting
        # an unrelated process.
        pgid = pid
        if SCANNER_PREFIX:
            # Processes run as scanner — appuser can't signal them directly.
            # Use sudo kill to send SIGTERM to the entire process group.
            subprocess.run(
                [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
                timeout=5
            )  # nosec B603
        else:
            # Local dev — same user, can kill directly
            os.killpg(pgid, signal.SIGTERM)
        log.info("RUN_KILL", extra={"run_id": run_id, "ip": client_ip, "pid": pid, "pgid": pgid})
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError) as e:
        log.warning("KILL_FAILED", extra={
            "run_id": run_id, "ip": client_ip, "pid": pid, "error": str(e),
        })
    return jsonify({"killed": True})
