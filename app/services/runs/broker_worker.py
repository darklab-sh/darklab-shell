# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Brokered run output publishing and worker lifecycle helpers."""

from __future__ import annotations

import logging
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from config import resolve_effective_cfg
from core.helpers import get_log_session_id
from services.runs.broker_batcher import BrokerOutputBatcher  # noqa: F401 - compatibility re-export
from services.runs.broker_capture import publish_broker_captured_line as publish_broker_captured_line
from services.runs.contracts import create_run_capture
from services.runs.completion_policy import RunCompletionPolicy, effective_run_exit_code
from services.runs.kinds import run_kind_for_cmd_type
from services.runs.output_model import LineKind
from services.runs.worker_cleanup import cleanup_broker_worker

log = logging.getLogger("shell")


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
    cfg: Mapping[str, Any] | None = None,
    run_output_capture_fn: Callable[[str], Any],
    output_signal_classifier_cls: Callable[..., Any],
    publish_run_event_fn: Callable[[str, str, dict[str, Any]], Any],
    publish_broker_captured_line_fn: Callable[..., Any],
    save_completed_run_fn: Callable[..., Any], app_metrics_obj,
    run_created_hook: Callable[[str, object | None], None] | None = None,
) -> str:
    active_cfg = resolve_effective_cfg(cfg)
    run_id = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = create_run_capture(run_id, run_output_capture_fn, run_created_hook)
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
                    publish=not bool(event.get("suppress_live")),
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
    completion_policy: RunCompletionPolicy | None = None,
    run_finalized_hook=None,
    run_cleanup_hook=None,
    cfg: Mapping[str, Any] | None = None,
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
    active_cfg: Mapping[str, Any] = {}
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
            cleanup_broker_worker(
                proc,
                run_id,
                session_id,
                team_id,
                client_ip,
                cleanup_proc_stream_fn,
                pid_pop_fn,
                active_run_remove_fn,
                run_cleanup_hook,
            )
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
                        output_batcher.add(
                            filtered_line,
                            publish=postfilter.should_publish_output_line(filtered_line),
                        )
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
                output_batcher.add(
                    filtered_line,
                    publish=postfilter.should_publish_output_line(filtered_line),
                )
        for filtered_line in postfilter.finalize_output_lines():
            output_batcher.add(
                filtered_line,
                publish=postfilter.should_publish_output_line(filtered_line),
            )
        output_batcher.flush()
        tool_exit_code = wait_for_proc_exit_code_fn(proc)
        exit_code = effective_run_exit_code(
            tool_exit_code,
            completion_policy=completion_policy,
            signal_classifier=signal_classifier,
            output_sink_error=bool(postfilter.output_sink_error),
        )
        if exit_code != tool_exit_code:
            log.info("RUN_EXIT_CODE_ACCEPTED", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "ip": client_ip,
                "cmd": original_command,
                "tool_exit_code": tool_exit_code,
                "exit_code": exit_code,
                "completion_policy": completion_policy.name if completion_policy else "",
            })
        finalize_kwargs = {
            "workspace_artifacts": workspace_artifacts,
            "owner_tab_id": owner_tab_id,
            "link_project_id": link_project_id,
        }
        if completion_policy is not None:
            finalize_kwargs["completion_policy"] = completion_policy
        finalize_info = finalize_completed_run_fn(
            run_id,
            session_id,
            team_id,
            client_ip,
            original_command,
            run_started,
            exit_code,
            capture,
            **finalize_kwargs,
        )
        if run_finalized_hook:
            run_finalized_hook(run_id, finalize_info)
        elapsed = finalize_info["elapsed"]
        active_project_link = finalize_info.get("active_project_link")
        finalize_summary = finalize_info.get("finalize_summary") if isinstance(finalize_info, dict) else {}
        publish_project_finalize_notices_fn(run_id, active_project_link, finalize_summary)
        exit_payload = {
            "code": exit_code,
            "elapsed": elapsed,
            "preview_truncated": capture.preview_truncated,
            "output_line_count": capture.output_line_count,
            "full_output_available": capture.full_output_available,
        }
        if exit_code != tool_exit_code:
            exit_payload["tool_exit_code"] = tool_exit_code
        publish_run_event_fn(run_id, "exit", exit_payload)
    except Exception as exc:
        log.error("RUN_BROKER_STREAM_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
            "cmd": original_command,
        })
        publish_run_event_fn(run_id, "error", {"text": str(exc)})
    finally:
        cleanup_broker_worker(
            proc,
            run_id,
            session_id,
            team_id,
            client_ip,
            cleanup_proc_stream_fn,
            pid_pop_fn,
            active_run_remove_fn,
            run_cleanup_hook,
        )
