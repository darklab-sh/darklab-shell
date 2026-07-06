"""Brokered run output publishing and worker lifecycle helpers."""

from __future__ import annotations

import logging
import subprocess
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from config import resolve_effective_cfg
from core.helpers import get_log_session_id
from services.runs.kinds import run_kind_for_cmd_type
from services.runs.output_model import LineEvent, LineKind, LineRole, line_event_from_legacy

log = logging.getLogger("shell")


class BrokerOutputBatcher:
    def __init__(
        self,
        run_id: str,
        capture,
        signal_classifier,
        *,
        run_started_dt,
        capture_event_with_signals_fn: Callable[..., tuple[Any, LineEvent]],
        broker_output_payload_fn: Callable[..., dict[str, Any]],
        publish_run_event_fn: Callable[[str, str, dict[str, Any]], Any],
        to_wire_fn: Callable[[LineEvent], dict[str, Any]],
        monotonic_fn: Callable[[], float] = time.monotonic,
        live_batch_size: int = 200,
        max_age_seconds: float = 0.75,
        max_latency_seconds: float = 0.075,
        coalesced_roles: set[LineRole] | None = None,
    ):
        self.run_id = run_id
        self.capture = capture
        self.signal_classifier = signal_classifier
        self.run_started_dt = run_started_dt
        self.capture_event_with_signals_fn = capture_event_with_signals_fn
        self.broker_output_payload_fn = broker_output_payload_fn
        self.publish_run_event_fn = publish_run_event_fn
        self.to_wire_fn = to_wire_fn
        self.monotonic_fn = monotonic_fn
        self.live_batch_size = live_batch_size
        self.max_age_seconds = max_age_seconds
        self.max_latency_seconds = max_latency_seconds
        self.coalesced_roles = coalesced_roles or {LineRole.progress, LineRole.status_line}
        self.events: list[LineEvent] = []
        self.first_event_monotonic = 0.0
        self.last_flush_monotonic = 0.0
        self.coalesced_line_count = 0

    def add(self, text: str, *, cls: str = "", kind: LineKind | str | None = None, event: LineEvent | None = None) -> None:
        now = self.monotonic_fn()
        line_dt = datetime.now(timezone.utc)
        base_event = event or line_event_from_legacy(
            text,
            cls,
            kind=kind,
            ts_clock=line_dt.strftime("%H:%M:%S"),
            ts_elapsed=f"+{(line_dt - self.run_started_dt).total_seconds():.1f}s",
        )
        _metadata, captured_event = self.capture_event_with_signals_fn(
            self.capture,
            self.signal_classifier,
            event=base_event,
        )
        self._append_live_event(captured_event, now=now)
        if (
            len(self.events) >= self.live_batch_size
            or self._is_due(now=now)
            or self._should_flush_for_latency(now)
        ):
            self.flush()

    def _append_live_event(self, event: LineEvent, *, now: float) -> None:
        if not self.events:
            self.first_event_monotonic = now
        if (
            event.role in self.coalesced_roles
            and self.events
            and self.events[-1].role == event.role
        ):
            self.events[-1] = event
            self.coalesced_line_count += 1
            return
        self.events.append(event)

    def _is_due(self, *, now: float | None = None) -> bool:
        current = self.monotonic_fn() if now is None else now
        return bool(
            self.events
            and self.first_event_monotonic
            and current - self.first_event_monotonic >= self.max_age_seconds
        )

    def _should_flush_for_latency(self, now: float) -> bool:
        if not self.events:
            return False
        if not self.last_flush_monotonic:
            return True
        return now - self.last_flush_monotonic >= self._max_latency_seconds()

    def _max_latency_seconds(self) -> float:
        if self.events and all(event.role in self.coalesced_roles for event in self.events):
            return self.max_age_seconds
        return self.max_latency_seconds

    def flush_due(self) -> None:
        if self._is_due():
            self.flush()

    def flush(self) -> None:
        if not self.events:
            return
        events = self.events
        coalesced_line_count = self.coalesced_line_count
        self.events = []
        self.first_event_monotonic = 0.0
        self.last_flush_monotonic = self.monotonic_fn()
        self.coalesced_line_count = 0
        if len(events) == 1:
            payload = self.broker_output_payload_fn("output", event=events[0])
            if coalesced_line_count:
                payload["coalesced_line_count"] = coalesced_line_count
            self.publish_run_event_fn(
                self.run_id,
                "output",
                payload,
            )
            return
        payload: dict[str, object] = {"lines": [self.to_wire_fn(event) for event in events]}
        if coalesced_line_count:
            payload["coalesced_line_count"] = coalesced_line_count
        self.publish_run_event_fn(
            self.run_id,
            "output_batch",
            payload,
        )


def publish_broker_captured_line(
    run_id: str,
    capture,
    signal_classifier,
    event_type: str,
    text: str,
    *,
    cls: str = "",
    kind: LineKind | str | None = None,
    event: LineEvent | None = None,
    run_started_dt,
    capture_event_with_signals_fn: Callable[..., tuple[Any, LineEvent]],
    broker_output_payload_fn: Callable[..., dict[str, Any]],
    publish_run_event_fn: Callable[[str, str, dict[str, Any]], Any],
) -> None:
    line_dt = datetime.now(timezone.utc)
    base_event = event or line_event_from_legacy(
        text,
        cls,
        kind=kind,
        ts_clock=line_dt.strftime("%H:%M:%S"),
        ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
    )
    _metadata, captured_event = capture_event_with_signals_fn(
        capture,
        signal_classifier,
        event=base_event,
    )
    publish_run_event_fn(
        run_id,
        event_type,
        broker_output_payload_fn(event_type, event=captured_event),
    )


def brokered_synthetic_run(
    original_command,
    session_id,
    client_ip,
    events,
    exit_code=0,
    *,
    cmd_type="builtin",
    owner_tab_id="",
    team_id="",
    cfg: dict[str, Any] | None = None,
    run_output_capture_fn: Callable[[str], Any],
    output_signal_classifier_cls: Callable[..., Any],
    publish_run_event_fn: Callable[[str, str, dict[str, Any]], Any],
    publish_broker_captured_line_fn: Callable[..., Any],
    save_completed_run_fn: Callable[..., Any],
    app_metrics_obj,
) -> str:
    active_cfg = resolve_effective_cfg(cfg)
    run_id = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = run_output_capture_fn(run_id)
    signal_classifier = output_signal_classifier_cls(
        original_command,
        cmd_type=cmd_type,
        extra_domain_suffixes=active_cfg.get("output_entity_extra_domain_suffixes", []),
    )
    run_started_dt = datetime.fromisoformat(run_started)

    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": 0, "cmd": original_command, "cmd_type": cmd_type,
    })
    app_metrics_obj.record_run_started(
        original_command,
        run_kind_for_cmd_type(cmd_type),
        active=False,
    )
    publish_run_event_fn(run_id, "started", {"run_id": run_id, "started": run_started})
    try:
        for event in events:
            if event.get("type") == "output":
                publish_broker_captured_line_fn(
                    run_id,
                    capture,
                    signal_classifier,
                    "output",
                    str(event.get("text", "")),
                    cls=str(event.get("cls", "")),
                    run_started_dt=run_started_dt,
                )
            elif event.get("type") == "clear":
                publish_run_event_fn(run_id, "clear", {})
        finished = datetime.now(timezone.utc)
        elapsed = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
        log.info("RUN_END", extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
            "exit_code": exit_code, "elapsed": elapsed, "cmd": original_command,
            "cmd_type": cmd_type,
            "output_line_count": capture.output_line_count,
            "preview_truncated": capture.preview_truncated,
            "full_output_available": capture.full_output_available,
            "full_output_truncated": capture.full_output_truncated,
        })
        publish_run_event_fn(run_id, "exit", {
            "code": exit_code,
            "elapsed": elapsed,
            "preview_truncated": capture.preview_truncated,
            "output_line_count": capture.output_line_count,
            "full_output_available": capture.full_output_available,
        })
        save_completed_run_fn(
            run_id, session_id, team_id, original_command, run_started,
            finished.isoformat(), exit_code, capture,
            link_active_project=cmd_type == "real",
            run_kind=run_kind_for_cmd_type(cmd_type),
            owner_tab_id=owner_tab_id,
        )
        app_metrics_obj.record_completed_run(
            original_command,
            run_kind_for_cmd_type(cmd_type),
            exit_code,
            elapsed,
            capture,
        )
    except Exception as exc:
        log.error("RUN_BROKER_SYNTHETIC_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
            "cmd": original_command,
        })
        publish_run_event_fn(run_id, "error", {"text": str(exc)})
    return run_id


def brokered_real_run_worker(
    *,
    run_id,
    proc,
    session_id,
    team_id,
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
    workspace_artifacts,
    owner_tab_id,
    link_project_id="",
    cfg: dict[str, Any] | None = None,
    trufflehog_output_filter_cls: Callable[[str], Any],
    publish_broker_captured_line_fn: Callable[..., Any],
    output_batcher_cls: Callable[..., Any],
    make_nonblocking_stream_reader_fn: Callable[..., Any],
    stdout_ready_fn: Callable[..., bool],
    read_available_stream_lines_fn: Callable[..., tuple[list[str], bool]],
    wait_for_proc_exit_code_fn: Callable[..., int | None],
    timeout_notice_fn: Callable[[int], str],
    terminate_process_group_fn: Callable[..., Any],
    finalize_completed_run_fn: Callable[..., dict[str, Any]],
    publish_project_finalize_notices_fn: Callable[..., Any],
    publish_run_event_fn: Callable[[str, str, dict[str, Any]], Any],
    cleanup_proc_stream_fn: Callable[..., Any],
    pid_pop_fn: Callable[[str], Any],
    active_run_remove_fn: Callable[[str], Any],
    poll_seconds: float,
    datetime_cls: Any = datetime,
) -> None:
    cfg_source = "explicit" if cfg is not None else "global"
    active_cfg: dict[str, Any] = {}
    try:
        active_cfg = resolve_effective_cfg(cfg)
        command_timeout = active_cfg["command_timeout_seconds"] or None
        heartbeat_interval = active_cfg.get("run_broker_heartbeat_seconds") or active_cfg["heartbeat_interval_seconds"]
        run_started_dt = datetime_cls.fromisoformat(run_started)
        trufflehog_output_filter = trufflehog_output_filter_cls(original_command)
    except (KeyError, TypeError, ValueError) as exc:
        log.error("RUN_BROKER_STREAM_CONFIG_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "ip": client_ip,
            "cmd": original_command,
            "cfg_source": cfg_source,
            "missing_key": str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else "",
            "error_type": type(exc).__name__,
            "command_timeout_present": "command_timeout_seconds" in active_cfg,
            "heartbeat_interval_present": (
                "heartbeat_interval_seconds" in active_cfg
                or "run_broker_heartbeat_seconds" in active_cfg
            ),
        })
        try:
            publish_run_event_fn(run_id, "error", {"text": str(exc)})
        except Exception:
            log.error("RUN_BROKER_STREAM_CONFIG_ERROR_PUBLISH_FAILED", exc_info=True, extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "ip": client_ip,
            })
        finally:
            cleanup_proc_stream_fn(proc)
            pid_pop_fn(run_id)
            active_run_remove_fn(run_id)
        return

    def _process_real_output_line(line: str) -> list[str]:
        filtered = workspace_path_filter.process_output_line(line)
        filtered = trufflehog_output_filter.process_output_line(filtered)
        return postfilter.process_output_line(filtered)

    try:
        if variable_notice:
            publish_broker_captured_line_fn(
                run_id, capture, signal_classifier, "notice", variable_notice,
                kind=LineKind.notice, run_started_dt=run_started_dt,
            )
        if rewrite_notice:
            publish_broker_captured_line_fn(
                run_id, capture, signal_classifier, "notice", f"[notice] {rewrite_notice}",
                kind=LineKind.notice, run_started_dt=run_started_dt,
            )
        for workspace_notice in workspace_notices:
            publish_broker_captured_line_fn(
                run_id, capture, signal_classifier, "notice", workspace_notice,
                kind=LineKind.notice, run_started_dt=run_started_dt,
            )

        if proc.stdout is None:
            raise RuntimeError("Process stdout pipe was not created")
        stream_reader = make_nonblocking_stream_reader_fn(proc.stdout)
        output_batcher = output_batcher_cls(
            run_id,
            capture,
            signal_classifier,
            run_started_dt=run_started_dt,
        )
        stream_fd = stream_reader.get("fd")
        stream_is_nonblocking = stream_fd is not None
        stream_poll_target = stream_fd if stream_is_nonblocking else proc.stdout
        if stream_poll_target is None:
            raise RuntimeError("Process stdout pipe was not created")
        heartbeat_seconds = max(poll_seconds, float(heartbeat_interval or 0))
        next_heartbeat_monotonic = time.monotonic() + heartbeat_seconds
        while True:
            if command_timeout:
                now_dt = datetime_cls.now(timezone.utc)
                elapsed = (now_dt - run_started_dt).total_seconds()
                if elapsed >= command_timeout:
                    try:
                        terminate_process_group_fn(proc)
                    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                        log.warning("CMD_TIMEOUT_TERMINATE_FAILED", exc_info=True, extra={
                            "run_id": run_id,
                            "session": get_log_session_id(session_id),
                            "ip": client_ip,
                            "cmd": original_command,
                        })
                    timeout_msg = timeout_notice_fn(command_timeout)
                    log.warning("CMD_TIMEOUT", extra={
                        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
                        "timeout": command_timeout, "cmd": original_command,
                    })
                    output_batcher.flush()
                    publish_broker_captured_line_fn(
                        run_id, capture, signal_classifier, "notice", timeout_msg,
                        kind=LineKind.notice, run_started_dt=run_started_dt,
                    )
                    break

            try:
                stdout_ready = stdout_ready_fn(stream_poll_target, poll_seconds)
            except ValueError:
                log.debug(
                    "RUN_STREAM_POLL_FALLBACK",
                    extra={
                        "run_id": run_id,
                        "session": get_log_session_id(session_id),
                        "stream_fd_present": stream_fd is not None,
                        "poll_seconds": poll_seconds,
                    },
                )
                stdout_ready = True
            if stdout_ready or stream_is_nonblocking:
                lines, eof = read_available_stream_lines_fn(stream_reader)
                if not lines and eof:
                    break
                if not lines:
                    if proc.poll() is not None:
                        break
                    now_monotonic = time.monotonic()
                    if now_monotonic >= next_heartbeat_monotonic:
                        publish_run_event_fn(run_id, "heartbeat", {})
                        next_heartbeat_monotonic = now_monotonic + heartbeat_seconds
                    continue
                for line in lines:
                    for filtered_line in _process_real_output_line(line):
                        output_batcher.add(filtered_line)
                output_batcher.flush_due()
            else:
                output_batcher.flush_due()
                if proc.poll() is not None:
                    break
                now_monotonic = time.monotonic()
                if now_monotonic >= next_heartbeat_monotonic:
                    publish_run_event_fn(run_id, "heartbeat", {})
                    next_heartbeat_monotonic = now_monotonic + heartbeat_seconds

        trailing_lines, _ = read_available_stream_lines_fn(stream_reader, finalize=True)
        for line in trailing_lines:
            for filtered_line in _process_real_output_line(line):
                output_batcher.add(filtered_line)
        for filtered_line in postfilter.finalize_output_lines():
            output_batcher.add(filtered_line)
        output_batcher.flush()
        exit_code = wait_for_proc_exit_code_fn(proc)
        finalize_info = finalize_completed_run_fn(
            run_id,
            session_id,
            team_id,
            client_ip,
            original_command,
            run_started,
            exit_code,
            capture,
            workspace_artifacts=workspace_artifacts,
            owner_tab_id=owner_tab_id,
            link_project_id=link_project_id,
        )
        elapsed = finalize_info["elapsed"]
        active_project_link = finalize_info.get("active_project_link")
        finalize_summary = finalize_info.get("finalize_summary") if isinstance(finalize_info, dict) else {}
        publish_project_finalize_notices_fn(run_id, active_project_link, finalize_summary)
        publish_run_event_fn(run_id, "exit", {
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
        publish_run_event_fn(run_id, "error", {"text": str(exc)})
    finally:
        cleanup_proc_stream_fn(proc)
        pid_pop_fn(run_id)
        active_run_remove_fn(run_id)
