"""
Execution routes: /runs (brokered command streaming), /run/client, and /kill.

The /runs start route is rate-limited per-IP via the shared limiter singleton.
"""

import json
import logging
import os
import re
import selectors
import codecs
import shlex
import shutil
import signal
import subprocess  # nosec B404
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from flask import Blueprint, Response, jsonify, request

from commands import (
    CommandValidationResult,
    command_root,
    interactive_pty_spec_for_command,
    is_command_allowed,
    parse_synthetic_postfilter,
    rewrite_command,
    runtime_missing_command_message,
    runtime_missing_command_name,
    split_command_argv,
    validate_command,
)
from config import CFG, SCANNER_PREFIX
from database import db_connect
from extensions import limiter
from builtin_commands import (
    execute_builtin_command,
    resolve_builtin_command,
    resolves_exact_special_builtin_command,
)
from helpers import get_client_ip, get_log_session_id, get_session_id
from process import (
    active_run_claim_owner,
    active_run_register,
    active_run_remove,
    active_run_touch_owner,
    active_runs_for_session,
    pid_pop,
    pid_pop_for_session,
    pid_register,
)
from run_broker import (
    broker_available,
    broker_unavailable_reason,
    get_run_events,
    publish_run_event,
    stream_run_events,
)
from run_output_store import RunOutputCapture, load_full_output_entries
from output_signals import OutputSignalClassifier
from project_workspace import link_run_to_active_project
from session_variables import SessionVariableError, expand_session_variables
from workspace import session_workspace_dir, WorkspaceDisabled
from pty_service import (
    PtyDependencyError,
    notify_pty_killed_event,
    pty_broker_available,
    pty_broker_unavailable_reason,
    pty_enabled,
    pty_run_snapshot,
    pty_run_belongs_to_session,
    resize_pty,
    start_pty_run,
    stream_pty_events,
    write_pty_input,
)

log = logging.getLogger("shell")

run_bp = Blueprint("run", __name__)


def _active_run_owner_value(value: object) -> str:
    return str(value or "").strip()[:128]


def _validate_command_for_run(command: str, session_id: str, workspace_cwd: str = "") -> CommandValidationResult:
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
    return validate_command(command, session_id=session_id, cfg=CFG, workspace_cwd=workspace_cwd)


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


def _prepare_run_child() -> None:
    os.setsid()
    os.umask(RUN_SUBPROCESS_UMASK)


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
        preview_max_bytes=CFG.get("output_preview_max_bytes", 0),
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


def _broker_output_payload(event_type, text, *, cls="", metadata=None):
    payload = {"text": text}
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
    return payload


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
        active_project_link = None
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
            try:
                active_project_link = link_run_to_active_project(conn, session_id, run_id)
            except Exception:
                active_project_link = None
                log.error("PROJECT_ACTIVE_RUN_LINK_ERROR", exc_info=True, extra={
                    "run_id": run_id,
                    "session": get_log_session_id(session_id),
                    "cmd": command,
                })
            conn.commit()
        if active_project_link:
            log.info("PROJECT_ACTIVE_RUN_LINKED", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "project_id": active_project_link["project_id"],
            })
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


_PTY_TRANSIENT_LINE_PATTERNS = (
    re.compile(r"^rate:\s+.*\bdone\b.*\bfound=\d+\b", re.IGNORECASE),
    re.compile(r"^::\s*Progress:\s*\[", re.IGNORECASE),
)


def _normalize_pty_entry(entry) -> dict[str, str]:
    if isinstance(entry, dict):
        return {
            "text": str(entry.get("text", "")),
            "cls": str(entry.get("cls", "")),
        }
    return {"text": str(entry), "cls": ""}


def _is_transient_pty_line(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    return any(pattern.search(value) for pattern in _PTY_TRANSIENT_LINE_PATTERNS)


def _split_pty_entries(entries: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    marker_index = next(
        (index for index, entry in enumerate(entries) if entry.get("cls") == "pty-marker"),
        -1,
    )
    if marker_index < 0:
        return entries, []
    return entries[:marker_index], entries[marker_index + 1:]


def _filter_transient_pty_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        entry for entry in entries
        if entry.get("cls") != "pty-marker" and not _is_transient_pty_line(entry.get("text", ""))
    ]


def _shape_completed_pty_entries(synthesized_lines, transcript_mode: object) -> list[dict[str, str]]:
    mode = str(transcript_mode or "final_frame").strip().lower()
    entries = [_normalize_pty_entry(item) for item in synthesized_lines]
    scrollback, final_frame = _split_pty_entries(entries)
    if mode == "scrollback_findings":
        shaped = _filter_transient_pty_entries(scrollback)
        if shaped:
            return shaped
        return _filter_transient_pty_entries(final_frame or entries)
    if mode == "all_sanitized":
        return _filter_transient_pty_entries(entries)
    return final_frame if final_frame else _filter_transient_pty_entries(entries)


def _persist_completed_pty_run(
    run,
    execution_command: str,
    finished_iso: str,
    exit_code: int,
    synthesized_lines,
    *,
    transcript_mode: object = "final_frame",
):
    capture = _run_output_capture(run.run_id)
    signal_classifier = OutputSignalClassifier(execution_command, cmd_type="real")
    for item in _shape_completed_pty_entries(synthesized_lines, transcript_mode):
        text = str(item.get("text", ""))
        cls = str(item.get("cls", ""))
        if cls == "pty-marker":
            capture.add_line(text, cls=cls)
            continue
        _capture_add_line_with_signals(capture, signal_classifier, text, cls=cls)
    _save_completed_run(
        run.run_id,
        run.session_id,
        run.command,
        run.started,
        finished_iso,
        exit_code,
        capture,
    )
    return {
        "preview_truncated": capture.preview_truncated,
        "output_line_count": capture.output_line_count,
        "full_output_available": capture.full_output_available,
    }


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
    active_project_link = None

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
        try:
            active_project_link = link_run_to_active_project(conn, session_id, run_id)
        except Exception:
            active_project_link = None
            log.error("PROJECT_ACTIVE_RUN_LINK_ERROR", exc_info=True, extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "cmd": command,
            })
        conn.commit()
    if active_project_link:
        log.info("PROJECT_ACTIVE_RUN_LINKED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "project_id": active_project_link["project_id"],
        })

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


class _WorkspacePathOutputFilter:
    """Display absolute session-workspace paths as user-facing workspace paths."""

    def __init__(self, session_id: str, cfg: dict):
        self.prefix = ""
        if not session_id or not cfg.get("workspace_enabled"):
            return
        try:
            self.prefix = str(session_workspace_dir(session_id, cfg).resolve(strict=False)).rstrip(os.sep)
        except (WorkspaceDisabled, OSError):
            self.prefix = ""

    def process_output_line(self, line: str) -> str:
        if not self.prefix:
            return line

        def _replace(match):
            suffix = match.group(1).lstrip("/")
            return f"/{suffix}" if suffix else "/"

        pattern = re.escape(self.prefix) + r"(/[\w@%+=:,./-]*)?"
        return re.sub(pattern, _replace, line)


@dataclass(frozen=True)
class _PreparedCommandInput:
    execution_command: str
    variable_notice: str
    postfilter: _SyntheticPostFilterProcessor


@dataclass(frozen=True)
class _PreparedRealCommand:
    execution_command: str
    command: str
    rewrite_notice: str | None
    validation: CommandValidationResult
    missing_runtime: str | None


@dataclass(frozen=True)
class _StartedRealCommand:
    run_id: str
    run_started: str
    proc: subprocess.Popen
    capture: RunOutputCapture
    signal_classifier: OutputSignalClassifier
    workspace_path_filter: _WorkspacePathOutputFilter


class _RunPreparationError(Exception):
    def __init__(self, message: str, *, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


class _RunSpawnError(Exception):
    pass


def _preparation_error_response(exc: _RunPreparationError):
    return jsonify({"error": str(exc)}), exc.status_code


def _coerce_positive_int(value: object, default: int) -> int:
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
    return number if number > 0 else default


def _interactive_pty_concurrency_limit() -> int:
    return _coerce_positive_int(CFG.get("interactive_pty_max_concurrent_per_session", 4), 4)


def _active_interactive_pty_count(session_id: str) -> int:
    return sum(
        1 for item in active_runs_for_session(session_id)
        if str(item.get("run_type", "command") or "command") == "pty"
    )


def _prepare_interactive_pty_command(
    original_command: str,
    session_id: str,
    client_ip: str,
    workspace_cwd: str = "",
) -> tuple[list[str], str, dict[str, object]]:
    tokens = split_command_argv(original_command)
    spec = interactive_pty_spec_for_command(original_command)
    if not tokens or not spec:
        root = tokens[0].lower() if tokens else "command"
        raise _RunPreparationError(f"Interactive PTY mode is not available for {root}", status_code=403)
    trigger_flag = str(spec.get("trigger_flag") or "").strip()
    if not trigger_flag or trigger_flag not in tokens[1:]:
        root = str(spec.get("root") or tokens[0].lower())
        raise _RunPreparationError(
            f"{root} interactive PTY commands must include {trigger_flag or 'the configured trigger flag'}",
            status_code=400,
        )
    argv = [token for token in tokens if token != trigger_flag]
    if bool(spec.get("requires_args", False)) and len(argv) < 2:
        root = str(spec.get("root") or tokens[0].lower())
        raise _RunPreparationError(f"{root} {trigger_flag} requires command arguments", status_code=400)
    execution_command = shlex.join(argv)
    validation = _validate_command_for_run(execution_command, session_id, workspace_cwd)
    if not validation.allowed:
        log.warning("CMD_DENIED", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command, "reason": validation.reason,
        })
        raise _RunPreparationError(validation.reason)
    execution_command = validation.exec_command or execution_command
    missing_runtime = runtime_missing_command_name(execution_command)
    if missing_runtime:
        raise _RunPreparationError(runtime_missing_command_message(missing_runtime), status_code=503)
    return split_command_argv(execution_command), execution_command, spec


def _prepare_command_input(
    original_command: str,
    session_id: str,
    client_ip: str,
    *,
    log_pipe: bool = False,
) -> _PreparedCommandInput:
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
            raise _RunPreparationError(str(exc)) from exc

    postfilter_spec, postfilter_error = parse_synthetic_postfilter(expanded_command)
    if postfilter_error:
        log.warning("CMD_DENIED", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command, "reason": postfilter_error,
        })
        raise _RunPreparationError(postfilter_error)
    execution_command = postfilter_spec["base_command"] if postfilter_spec else expanded_command
    if log_pipe and postfilter_spec:
        stage_kinds = [stage.get("kind") for stage in postfilter_spec.get("stages", []) if stage.get("kind")]
        log.debug("CMD_PIPE", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command,
            "kind": " -> ".join(stage_kinds) if stage_kinds else postfilter_spec.get("kind"),
        })
    try:
        postfilter = _SyntheticPostFilterProcessor(postfilter_spec)
    except ValueError as exc:
        raise _RunPreparationError(str(exc)) from exc
    return _PreparedCommandInput(
        execution_command=execution_command,
        variable_notice=variable_notice,
        postfilter=postfilter,
    )


def _filter_builtin_command_events(events, variable_notice: str, postfilter: _SyntheticPostFilterProcessor):
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
    return filtered_events


def _prepare_real_command(
    original_command: str,
    execution_command: str,
    session_id: str,
    client_ip: str,
    workspace_cwd: str = "",
) -> _PreparedRealCommand:
    validation = _validate_command_for_run(execution_command, session_id, workspace_cwd)
    if not validation.allowed:
        log.warning("CMD_DENIED", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": original_command, "reason": validation.reason,
        })
        raise _RunPreparationError(validation.reason)
    execution_command = validation.exec_command or execution_command

    command, notice = rewrite_command(execution_command, session_id=session_id, cfg=CFG)
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
    return _PreparedRealCommand(
        execution_command=execution_command,
        command=command,
        rewrite_notice=notice,
        validation=validation,
        missing_runtime=missing_runtime,
    )


def _start_real_command_process(
    original_command: str,
    session_id: str,
    client_ip: str,
    prepared_real: _PreparedRealCommand,
    *,
    owner_client_id: str = "",
    owner_tab_id: str = "",
) -> _StartedRealCommand:
    run_id = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = _run_output_capture(run_id)
    signal_classifier = OutputSignalClassifier(prepared_real.execution_command, cmd_type="real")
    workspace_path_filter = _WorkspacePathOutputFilter(session_id, CFG)

    try:
        proc = subprocess.Popen(
            SCANNER_PREFIX + [SHELL_BIN, "-c", prepared_real.command] if SCANNER_PREFIX
            else [SHELL_BIN, "-c", prepared_real.command],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=_prepare_run_child,
        )  # nosec B603
    except Exception as exc:
        log.error("RUN_SPAWN_ERROR", exc_info=True, extra={
            "ip": client_ip, "session": get_log_session_id(session_id), "cmd": original_command,
        })
        raise _RunSpawnError(str(exc)) from exc

    pid_register(run_id, proc.pid)
    active_run_register(
        run_id,
        proc.pid,
        session_id,
        original_command,
        run_started,
        owner_client_id=owner_client_id,
        owner_tab_id=owner_tab_id,
    )
    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": proc.pid, "cmd": original_command, "cmd_type": "real",
    })
    return _StartedRealCommand(
        run_id=run_id,
        run_started=run_started,
        proc=proc,
        capture=capture,
        signal_classifier=signal_classifier,
        workspace_path_filter=workspace_path_filter,
    )


def _publish_broker_captured_line(
    run_id: str,
    capture,
    signal_classifier,
    event_type: str,
    text: str,
    *,
    cls: str = "",
    run_started_dt,
):
    line_dt = datetime.now(timezone.utc)
    metadata = _capture_add_line_with_signals(
        capture,
        signal_classifier,
        text,
        cls=cls,
        ts_clock=line_dt.strftime("%H:%M:%S"),
        ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
    )
    publish_run_event(
        run_id,
        event_type,
        _broker_output_payload(event_type, text, cls=cls, metadata=metadata),
    )


def _brokered_synthetic_run(original_command, session_id, client_ip, events, exit_code=0, *, cmd_type="builtin"):
    run_id = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = _run_output_capture(run_id)
    signal_classifier = OutputSignalClassifier(original_command, cmd_type=cmd_type)
    run_started_dt = datetime.fromisoformat(run_started)

    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": 0, "cmd": original_command, "cmd_type": cmd_type,
    })
    publish_run_event(run_id, "started", {"run_id": run_id, "started": run_started})
    try:
        for event in events:
            if event.get("type") == "output":
                _publish_broker_captured_line(
                    run_id,
                    capture,
                    signal_classifier,
                    "output",
                    str(event.get("text", "")),
                    cls=str(event.get("cls", "")),
                    run_started_dt=run_started_dt,
                )
            elif event.get("type") == "clear":
                publish_run_event(run_id, "clear", {})
        finished = datetime.now(timezone.utc)
        elapsed = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
        log.info("RUN_END", extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
            "exit_code": exit_code, "elapsed": elapsed, "cmd": original_command,
            "cmd_type": cmd_type,
        })
        publish_run_event(run_id, "exit", {
            "code": exit_code,
            "elapsed": elapsed,
            "preview_truncated": capture.preview_truncated,
            "output_line_count": capture.output_line_count,
            "full_output_available": capture.full_output_available,
        })
        _save_completed_run(
            run_id, session_id, original_command, run_started,
            finished.isoformat(), exit_code, capture,
        )
    except Exception as exc:
        log.error("RUN_BROKER_SYNTHETIC_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
            "cmd": original_command,
        })
        publish_run_event(run_id, "error", {"text": str(exc)})
    return run_id


def _brokered_real_run_worker(
    *,
    run_id,
    proc,
    session_id,
    client_ip,
    original_command,
    run_started,
    capture,
    signal_classifier,
    postfilter,
    workspace_path_filter,
    variable_notice,
    rewrite_notice,
    workspace_notices,
):
    command_timeout = CFG["command_timeout_seconds"] or None
    heartbeat_interval = CFG.get("run_broker_heartbeat_seconds") or CFG["heartbeat_interval_seconds"]
    run_started_dt = datetime.fromisoformat(run_started)

    def _process_real_output_line(line: str) -> list[str]:
        return postfilter.process_output_line(workspace_path_filter.process_output_line(line))

    try:
        if variable_notice:
            _publish_broker_captured_line(
                run_id, capture, signal_classifier, "notice", variable_notice,
                cls="notice", run_started_dt=run_started_dt,
            )
        if rewrite_notice:
            _publish_broker_captured_line(
                run_id, capture, signal_classifier, "notice", f"[notice] {rewrite_notice}",
                cls="notice", run_started_dt=run_started_dt,
            )
        for workspace_notice in workspace_notices:
            _publish_broker_captured_line(
                run_id, capture, signal_classifier, "notice", workspace_notice,
                cls="notice", run_started_dt=run_started_dt,
            )

        if proc.stdout is None:
            raise RuntimeError("Process stdout pipe was not created")
        stream_reader = _make_nonblocking_stream_reader(proc.stdout)
        while True:
            if command_timeout:
                now_dt = datetime.now(timezone.utc)
                elapsed = (now_dt - run_started_dt).total_seconds()
                if elapsed >= command_timeout:
                    try:
                        _terminate_process_group(proc)
                    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                        pass
                    timeout_msg = _timeout_notice(command_timeout)
                    log.warning("CMD_TIMEOUT", extra={
                        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                        "timeout": command_timeout, "cmd": original_command,
                    })
                    _publish_broker_captured_line(
                        run_id, capture, signal_classifier, "notice", timeout_msg,
                        cls="notice", run_started_dt=run_started_dt,
                    )
                    break

            if _stdout_ready(proc.stdout, heartbeat_interval):
                lines, eof = _read_available_stream_lines(stream_reader)
                if not lines and eof:
                    break
                if not lines:
                    if proc.poll() is not None:
                        break
                    publish_run_event(run_id, "heartbeat", {})
                    continue
                for line in lines:
                    for filtered_line in _process_real_output_line(line):
                        _publish_broker_captured_line(
                            run_id,
                            capture,
                            signal_classifier,
                            "output",
                            filtered_line,
                            run_started_dt=run_started_dt,
                        )
            else:
                if proc.poll() is not None:
                    break
                publish_run_event(run_id, "heartbeat", {})

        trailing_lines, _ = _read_available_stream_lines(stream_reader, finalize=True)
        for line in trailing_lines:
            for filtered_line in _process_real_output_line(line):
                _publish_broker_captured_line(
                    run_id,
                    capture,
                    signal_classifier,
                    "output",
                    filtered_line,
                    run_started_dt=run_started_dt,
                )
        for filtered_line in postfilter.finalize_output_lines():
            _publish_broker_captured_line(
                run_id,
                capture,
                signal_classifier,
                "output",
                filtered_line,
                run_started_dt=run_started_dt,
            )
        exit_code = _wait_for_proc_exit_code(proc)
        elapsed = _finalize_completed_run(
            run_id, session_id, client_ip, original_command, run_started, exit_code, capture,
        )
        publish_run_event(run_id, "exit", {
            "code": exit_code,
            "elapsed": elapsed,
            "preview_truncated": capture.preview_truncated,
            "output_line_count": capture.output_line_count,
            "full_output_available": capture.full_output_available,
        })
    except Exception as exc:
        log.error("RUN_BROKER_STREAM_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
            "cmd": original_command,
        })
        publish_run_event(run_id, "error", {"text": str(exc)})
    finally:
        _cleanup_proc_stream(proc)
        pid_pop(run_id)
        active_run_remove(run_id)


def _run_belongs_to_session(run_id: str, session_id: str) -> bool:
    if not run_id or not session_id:
        return False
    active_ids = {str(item.get("run_id", "")) for item in active_runs_for_session(session_id)}
    if run_id in active_ids:
        return True
    try:
        with db_connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM runs WHERE id = ? AND session_id = ?",
                (run_id, session_id),
            ).fetchone()
            return row is not None
    except Exception:
        log.error("RUN_BROKER_SESSION_CHECK_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id),
        })
        return False


# ── Routes ────────────────────────────────────────────────────────────────────

@run_bp.route("/pty/runs", methods=["POST"])
@limiter.limit(lambda: (
    f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"
))
def start_interactive_pty_run():
    if not pty_enabled():
        return jsonify({"error": "Interactive PTY mode is disabled on this instance"}), 403
    if not pty_broker_available():
        return jsonify({"error": pty_broker_unavailable_reason()}), 503

    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    original_command = data.get("command", "")
    if not isinstance(original_command, str):
        return jsonify({"error": "Command must be a string"}), 400
    original_command = original_command.strip()
    if not original_command:
        return jsonify({"error": "No command provided"}), 400

    session_id = get_session_id()
    client_ip = get_client_ip()
    workspace_cwd = _active_run_owner_value(data.get("workspace_cwd", ""))
    try:
        argv, execution_command, pty_spec = _prepare_interactive_pty_command(
            original_command,
            session_id,
            client_ip,
            workspace_cwd,
        )
    except _RunPreparationError as exc:
        return _preparation_error_response(exc)

    pty_limit = _interactive_pty_concurrency_limit()
    active_pty_count = _active_interactive_pty_count(session_id)
    if active_pty_count >= pty_limit:
        return jsonify({
            "error": (
                "Interactive PTY limit reached for this session "
                f"({active_pty_count}/{pty_limit} active). Close or kill an active PTY before starting another."
            ),
        }), 429

    try:
        run = start_pty_run(
            session_id=session_id,
            client_ip=client_ip,
            command=original_command,
            argv=argv,
            rows=data.get("rows"),
            cols=data.get("cols"),
            default_rows=pty_spec.get("default_rows"),
            default_cols=pty_spec.get("default_cols"),
            owner_client_id=_active_run_owner_value(request.headers.get("X-Client-ID", "")),
            owner_tab_id=_active_run_owner_value(data.get("tab_id", "")),
            allow_input=(
                bool(pty_spec.get("allow_input", True))
                and str(pty_spec.get("input_safety") or "") != "no_input"
            ),
            max_runtime_seconds=_coerce_positive_int(
                pty_spec.get("max_runtime_seconds"),
                _coerce_positive_int(CFG.get("interactive_pty_max_runtime_seconds", 900), 900),
            ),
            completion_callback=lambda completed_run, finished_iso, exit_code, synthesized_lines: (
                _persist_completed_pty_run(
                    completed_run,
                    execution_command,
                    finished_iso,
                    exit_code,
                    synthesized_lines,
                    transcript_mode=pty_spec.get("transcript_mode"),
                )
            ),
        )
    except PtyDependencyError as exc:
        log.error("PTY_DEPENDENCY_ERROR", extra={
            "ip": client_ip, "session": get_log_session_id(session_id), "cmd": original_command,
        })
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        log.error("PTY_SPAWN_ERROR", exc_info=True, extra={
            "ip": client_ip, "session": get_log_session_id(session_id), "cmd": original_command,
        })
        return jsonify({"error": str(exc)}), 500
    return jsonify({
        "run_id": run.run_id,
        "stream": f"/pty/runs/{run.run_id}/stream",
        "command": execution_command,
        "interactive": True,
        "rows": run.rows,
        "cols": run.cols,
    }), 202


@run_bp.route("/pty/runs/<run_id>/stream")
def stream_interactive_pty_run(run_id):
    session_id = get_session_id()
    if not pty_run_belongs_to_session(run_id, session_id):
        return jsonify({"error": "Run not found"}), 404
    after_id = request.args.get("after", "0-0") or "0-0"
    owner_client_id = _active_run_owner_value(request.headers.get("X-Client-ID", ""))
    owner_tab_id = _active_run_owner_value(request.args.get("tab_id", ""))
    if owner_client_id and pty_run_belongs_to_session(run_id, session_id):
        active_run_claim_owner(run_id, owner_client_id, owner_tab_id)

    def generate():
        for item in stream_pty_events(run_id, session_id, after=after_id):
            if owner_client_id:
                active_run_touch_owner(run_id, owner_client_id, owner_tab_id)
            yield item

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _pty_snapshot_error_response(message: str):
    text = message or "PTY snapshot is not available"
    headers = {}
    if text == "Run not found":
        status = 404
    elif text in {"Run is closed", "PTY run is no longer active"}:
        status = 410
    elif "snapshot is not available" in text:
        status = 503
        headers["Retry-After"] = "1"
    else:
        status = 409
    return jsonify({"error": text}), status, headers


@run_bp.route("/pty/runs/<run_id>/snapshot")
def snapshot_interactive_pty_run(run_id):
    session_id = get_session_id()
    ok, message, snapshot = pty_run_snapshot(run_id, session_id)
    if not ok:
        return _pty_snapshot_error_response(message)
    return jsonify(snapshot)


@run_bp.route("/pty/runs/<run_id>/input", methods=["POST"])
@limiter.limit(lambda: (
    f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"
))
def send_interactive_pty_input(run_id):
    session_id = get_session_id()
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    ok, message = write_pty_input(
        run_id,
        session_id,
        data.get("data", ""),
        _active_run_owner_value(request.headers.get("X-Client-ID", "")),
        _active_run_owner_value(data.get("tab_id", "")),
    )
    if not ok:
        status = 404 if message == "Run not found" else 409 if "no longer active" in message else 400
        return jsonify({"error": message or "Input rejected"}), status
    return jsonify({"ok": True})


@run_bp.route("/pty/runs/<run_id>/resize", methods=["POST"])
@limiter.limit(lambda: (
    f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"
))
def resize_interactive_pty_run(run_id):
    session_id = get_session_id()
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    ok, message, rows, cols = resize_pty(run_id, session_id, data.get("rows"), data.get("cols"))
    if not ok:
        status = 404 if message == "Run not found" else 409 if "no longer active" in message else 400
        return jsonify({"error": message or "Resize rejected"}), status
    return jsonify({"ok": True, "rows": rows, "cols": cols})


@run_bp.route("/runs", methods=["POST"])
@limiter.limit(lambda: (
    f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"
))
def start_brokered_run():
    if not broker_available():
        return jsonify({"error": broker_unavailable_reason()}), 503

    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    original_command = data.get("command", "")
    session_id = get_session_id()
    client_ip = get_client_ip()
    owner_client_id = _active_run_owner_value(request.headers.get("X-Client-ID", ""))
    owner_tab_id = _active_run_owner_value(data.get("tab_id", ""))
    workspace_cwd = _active_run_owner_value(data.get("workspace_cwd", ""))
    if not isinstance(original_command, str):
        return jsonify({"error": "Command must be a string"}), 400
    original_command = original_command.strip()
    if not original_command:
        return jsonify({"error": "No command provided"}), 400

    if resolves_exact_special_builtin_command(original_command):
        events, exit_code = execute_builtin_command(original_command, session_id)
        run_id = _brokered_synthetic_run(original_command, session_id, client_ip, events, exit_code)
        return jsonify({"run_id": run_id, "stream": f"/runs/{run_id}/stream"}), 202

    try:
        prepared_input = _prepare_command_input(original_command, session_id, client_ip)
    except _RunPreparationError as exc:
        return _preparation_error_response(exc)

    if resolve_builtin_command(prepared_input.execution_command):
        events, exit_code = execute_builtin_command(prepared_input.execution_command, session_id)
        filtered_events = _filter_builtin_command_events(
            events,
            prepared_input.variable_notice,
            prepared_input.postfilter,
        )
        run_id = _brokered_synthetic_run(original_command, session_id, client_ip, filtered_events, exit_code)
        return jsonify({"run_id": run_id, "stream": f"/runs/{run_id}/stream"}), 202

    try:
        prepared_real = _prepare_real_command(
            original_command,
            prepared_input.execution_command,
            session_id,
            client_ip,
            workspace_cwd,
        )
    except _RunPreparationError as exc:
        return _preparation_error_response(exc)
    if prepared_real.missing_runtime:
        events = [{"type": "output", "text": runtime_missing_command_message(prepared_real.missing_runtime)}]
        run_id = _brokered_synthetic_run(original_command, session_id, client_ip, events, 127, cmd_type="missing")
        return jsonify({"run_id": run_id, "stream": f"/runs/{run_id}/stream"}), 202

    try:
        started = _start_real_command_process(
            original_command,
            session_id,
            client_ip,
            prepared_real,
            owner_client_id=owner_client_id,
            owner_tab_id=owner_tab_id,
        )
    except _RunSpawnError as exc:
        return jsonify({"error": str(exc)}), 500

    publish_run_event(started.run_id, "started", {"run_id": started.run_id, "started": started.run_started})
    threading.Thread(
        target=_brokered_real_run_worker,
        kwargs={
            "run_id": started.run_id,
            "proc": started.proc,
            "session_id": session_id,
            "client_ip": client_ip,
            "original_command": original_command,
            "run_started": started.run_started,
            "capture": started.capture,
            "signal_classifier": started.signal_classifier,
            "postfilter": prepared_input.postfilter,
            "workspace_path_filter": started.workspace_path_filter,
            "variable_notice": prepared_input.variable_notice,
            "rewrite_notice": prepared_real.rewrite_notice,
            "workspace_notices": _workspace_notice_lines(prepared_real.validation),
        },
        name=f"run-broker-{started.run_id[:8]}",
        daemon=True,
    ).start()
    return jsonify({"run_id": started.run_id, "stream": f"/runs/{started.run_id}/stream"}), 202


@run_bp.route("/runs/<run_id>/events")
def get_brokered_run_events(run_id):
    session_id = get_session_id()
    if not _run_belongs_to_session(run_id, session_id):
        return jsonify({"error": "Run not found"}), 404
    after_id = str(request.args.get("after", "0-0") or "0-0")
    try:
        limit = max(1, min(int(request.args.get("limit", 100) or 100), 500))
    except (TypeError, ValueError):
        limit = 100
    events = get_run_events(run_id, after_id=after_id, limit=limit)
    return jsonify({
        "run_id": run_id,
        "events": [event.as_payload() for event in events],
    })


@run_bp.route("/runs/<run_id>/stream")
def stream_brokered_run(run_id):
    session_id = get_session_id()
    if not _run_belongs_to_session(run_id, session_id):
        return jsonify({"error": "Run not found"}), 404
    after_id = str(request.args.get("after", "0-0") or "0-0")
    owner_client_id = _active_run_owner_value(request.headers.get("X-Client-ID", ""))
    owner_tab_id = _active_run_owner_value(request.args.get("tab_id", ""))

    def generate():
        for item in stream_run_events(run_id, after_id=after_id):
            if owner_client_id:
                active_run_touch_owner(run_id, owner_client_id, owner_tab_id)
            yield item

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@run_bp.route("/kill", methods=["POST"])
def kill_command():
    data      = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    run_id    = data.get("run_id", "")
    killer_tab_id = _active_run_owner_value(data.get("tab_id", ""))
    client_ip = get_client_ip()
    if not isinstance(run_id, str):
        return jsonify({"error": "run_id must be a string"}), 400
    session_id = get_session_id()
    killer_client_id = _active_run_owner_value(request.headers.get("X-Client-ID", ""))
    active_run = next(
        (run for run in active_runs_for_session(session_id) if run.get("run_id") == run_id),
        {},
    )
    run_type = str(active_run.get("run_type", "command") or "command").lower()
    pid       = pid_pop_for_session(run_id, session_id)
    if not pid:
        log.debug("KILL_MISS", extra={
            "ip": client_ip,
            "run_id": run_id,
            "session": get_log_session_id(session_id),
        })
        return jsonify({"error": "No such process"}), 404
    killed_payload = {
        "killer_client_id": killer_client_id,
        "killer_tab_id": killer_tab_id,
    }
    if run_type == "pty":
        notify_pty_killed_event(run_id, session_id, killed_payload)
    else:
        publish_run_event(run_id, "killed", killed_payload)
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
        log.info("RUN_KILL", extra={
            "run_id": run_id,
            "ip": client_ip,
            "session": get_log_session_id(session_id),
            "pid": pid,
            "pgid": pgid,
        })
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError) as e:
        log.warning("KILL_FAILED", extra={
            "run_id": run_id, "ip": client_ip, "pid": pid, "error": str(e),
        })
    return jsonify({"killed": True})
