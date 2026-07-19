# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Execution routes: /runs (brokered command streaming), /run/client, and /kill.

The /runs start route is rate-limited per-IP via the shared limiter singleton.
"""

import logging
import os
import shutil
import subprocess
import time
import uuid  # noqa: F401 - compatibility seam for tests and run_client
from datetime import datetime  # noqa: F401 - compatibility seam for run-lifecycle tests

from flask import Blueprint, Response, jsonify, request  # noqa: F401

from services.commands.registry import (
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
    command_project_target_inputs,
)
from config import CFG, SCANNER_PREFIX, get_share_redaction_rules, resolve_effective_cfg
from extensions import limiter  # noqa: F401 - compatibility seam for run_broker/run_pty
from services.commands.builtins import execute_builtin_command, resolve_builtin_command, resolves_exact_special_builtin_command
from core.helpers import get_client_ip, get_log_session_id, get_session_id  # noqa: F401
from core.process import (
    active_run_belongs_to_scope,
    active_run_pid_start_matches,
    active_run_register,
    active_run_remove,
    active_run_touch_owner,
    active_runs_for_team,
    active_runs_for_session,
    pid_for_session,  # noqa: F401 - compatibility seam for run_kill
    pid_for_team,  # noqa: F401 - compatibility seam for run_kill
    pid_pop,
    pid_register,
)
from services.teams.request_scope import RequestScope, RequestScopeError, current_request_scope  # noqa: F401
from services.teams.request_scope import requested_team_id, scope_error_payload  # noqa: F401
from services.teams.scope import OwnerContext, owner_context_for_scope
from services.teams.capabilities import Capability  # noqa: F401 - compatibility seam for route submodules
from services.runs.broker import (
    broker_available,  # noqa: F401 - compatibility seam for run_broker
    broker_mode,  # noqa: F401 - compatibility seam for run_broker
    broker_unavailable_reason,  # noqa: F401 - compatibility seam for run_broker
    get_run_events,  # noqa: F401 - compatibility seam for run_broker
    publish_run_event,
    stream_run_events,  # noqa: F401 - compatibility seam for run_broker
)
from services.runs.output_store import RunOutputCapture, load_full_output_entries
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL  # noqa: F401
from services.runs import finalization as run_finalization
from services.runs.finalization import apply_auto_promote_rules_for_run  # noqa: F401
from services.runs import lifecycle as run_lifecycle
from services.runs import postfilters as run_postfilters
from services.runs.output_model import (
    LineEvent,
    LineKind,
    LineRole,
    line_event_from_legacy,
    to_wire,
)
from services.runs.persistence import (
    insert_run_row,  # noqa: F401 - compatibility seam for run_client
    run_finalize_savepoint,  # noqa: F401 - compatibility seam for run_client
    run_persistence_transaction,  # noqa: F401 - compatibility seam for tests and run_client
    run_scope_visibility_from_db,
    scan_target_observation_count,  # noqa: F401 - compatibility seam for run_client
)
from services.runs.structured_summary import replace_run_output_summary  # noqa: F401
from services.runs.start import (
    RunPreparationError as _RunPreparationError,
    RunSpawnError as _RunSpawnError,  # noqa: F401 - compatibility seam for run_broker/API tests
    RunStartHandlers,
    start_brokered_run as _start_brokered_run_service,  # noqa: F401 - compatibility seam for run_broker
)
from services.storage.body_store import (  # noqa: F401
    inline_threshold_bytes,
    maybe_store_text_body,
)
from services.atlas.materializer import materialize_run_entities
from services.secrets.audit import emit_secret_event
from services.secrets.storage import get_secret_value_for_env
from services.runs.streaming import (
    cleanup_proc_stream as _cleanup_proc_stream,
    make_nonblocking_stream_reader as _make_nonblocking_stream_reader,
    read_available_stream_lines as _read_available_stream_lines,
    stdout_ready as _stdout_ready,
    timeout_notice as _timeout_notice,
    wait_for_proc_exit_code as _wait_for_proc_exit_code,
)
from services.runs.workspace_artifacts import (
    workspace_artifacts_from_validation as _workspace_artifacts_from_validation,
    workspace_artifacts_with_sizes as _workspace_artifacts_with_sizes,
)
from core.output_signals import OutputSignalClassifier
from services.projects.findings import record_run_findings
from services.projects.links import link_active_project_run_entities
from services.projects.targets import record_project_target_discoveries
from services.metrics_lazy import app_metrics
from services.session.variables import expand_session_variables
from services.pty.service import (
    PtyDependencyError,  # noqa: F401 - compatibility seam for tests and run_pty
    claim_pty_stream_owner,  # noqa: F401 - compatibility seam for tests and run_pty
    notify_pty_killed_event,  # noqa: F401 - compatibility seam for run_kill
    pty_broker_available,  # noqa: F401 - compatibility seam for tests and run_pty
    pty_broker_unavailable_reason,  # noqa: F401 - compatibility seam for tests and run_pty
    pty_enabled,  # noqa: F401 - compatibility seam for tests and run_pty
    pty_run_snapshot,  # noqa: F401 - compatibility seam for tests and run_pty
    pty_run_belongs_to_scope,
    resize_pty,  # noqa: F401 - compatibility seam for tests and run_pty
    start_pty_run,  # noqa: F401 - compatibility seam for tests and run_pty
    stream_pty_events,  # noqa: F401 - compatibility seam for tests and run_pty
    write_pty_input,  # noqa: F401 - compatibility seam for tests and run_pty
)
from services.pty.transcript import shape_completed_pty_entries
from blueprints.run_support import (
    CLIENT_SIDE_RUN_ROOTS, coerce_positive_int as _coerce_positive_int,  # noqa: F401
    active_interactive_pty_count as _active_interactive_pty_count, active_run_owner_value as _active_run_owner_value,  # noqa: F401
    client_side_run_command_allowed as _client_side_run_command_allowed,  # noqa: F401
    interactive_pty_concurrency_limit as _interactive_pty_concurrency_limit,  # noqa: F401
    interactive_pty_input_limit as _interactive_pty_input_limit, interactive_pty_resize_limit as _interactive_pty_resize_limit,  # noqa: F401
    require_team_capability as _require_team_capability, scope_has_team_capability as _scope_has_team_capability,  # noqa: F401
    team_audit_fields as _team_audit_fields, workspace_cwd_value as _workspace_cwd_value,  # noqa: F401
)

log = logging.getLogger("shell")

run_bp = Blueprint("run", __name__)

_RunSessionVisibility = run_lifecycle.RunSessionVisibility


def _validate_command_for_run(
    command: str,
    session_id: str,
    workspace_cwd: str = "",
    *,
    extra_allowed_prefixes: list[str] | None = None,
    owner_context: OwnerContext | None = None,
) -> CommandValidationResult:
    return run_lifecycle.validate_command_for_run(
        command,
        session_id,
        workspace_cwd,
        extra_allowed_prefixes=extra_allowed_prefixes,
        owner_context=owner_context,
        cfg=CFG,
        is_command_allowed_fn=is_command_allowed,
        validate_command_fn=validate_command,
    )


def _validate_command_with_effective_owner(
    command: str,
    session_id: str,
    workspace_cwd: str = "",
    *,
    extra_allowed_prefixes: list[str] | None = None,
    owner_context: OwnerContext | None = None,
) -> CommandValidationResult:
    return run_lifecycle.validate_command_with_effective_owner(
        command,
        session_id,
        workspace_cwd,
        extra_allowed_prefixes=extra_allowed_prefixes,
        owner_context=owner_context,
        validate_command_for_run_fn=_validate_command_for_run,
    )


_effective_owner_context = run_lifecycle.effective_owner_context
_workspace_notice_lines = run_lifecycle.workspace_notice_lines


SHELL_BIN = shutil.which("sh") or "/bin/sh"
STDBUF_BIN = shutil.which("stdbuf")
SUDO_BIN  = shutil.which("sudo") or "/usr/bin/sudo"
KILL_BIN  = shutil.which("kill") or "/bin/kill"

_variable_notice_line = run_lifecycle.variable_notice_line
RUN_SUBPROCESS_UMASK = 0o027


def _prepare_run_child() -> None:
    os.setsid()
    os.umask(RUN_SUBPROCESS_UMASK)


def _terminate_process_group(proc) -> None:
    pgid = os.getpgid(proc.pid)
    _signal_process_group(pgid)


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


def _capture_event_with_signals(
    capture,
    classifier,
    text: str = "",
    *,
    cls: str = "",
    ts_clock: str = "",
    ts_elapsed: str = "",
    event: LineEvent | None = None,
):
    return run_finalization.capture_event_with_signals(
        capture,
        classifier,
        text,
        cls=cls,
        ts_clock=ts_clock,
        ts_elapsed=ts_elapsed,
        event=event,
    )


def _broker_output_payload(_event_type, text: str = "", *, cls: str = "", event: LineEvent | None = None):
    payload_event = event or line_event_from_legacy(text, cls)
    return to_wire(payload_event)


_RUN_OUTPUT_LIVE_BATCH_SIZE = 200
_RUN_OUTPUT_LIVE_BATCH_MAX_AGE_SECONDS = 0.75
_RUN_OUTPUT_LIVE_BATCH_MAX_LATENCY_SECONDS = 0.075
_RUN_OUTPUT_POLL_SECONDS = 0.05
_RUN_OUTPUT_LIVE_BATCH_COALESCED_ROLES = {LineRole.progress, LineRole.status_line}
_KILL_PROCESS_GROUP_GONE_DELAYS = (0.0, 0.05, 0.15, 0.3, 0.5)
_ACTIVE_RUN_OWNER_TOUCH_INTERVAL_SECONDS = 5.0
_active_run_owner_touch_monotonic = time.monotonic


def _maybe_touch_active_run_owner(
    run_id: str,
    owner_client_id: str,
    owner_tab_id: str,
    *,
    last_touch_monotonic: float | None,
) -> float | None:
    if not owner_client_id:
        return last_touch_monotonic
    now = _active_run_owner_touch_monotonic()
    if (
        last_touch_monotonic is not None
        and now - last_touch_monotonic < _ACTIVE_RUN_OWNER_TOUCH_INTERVAL_SECONDS
    ):
        return last_touch_monotonic
    active_run_touch_owner(run_id, owner_client_id, owner_tab_id)
    return now


def _BrokerOutputBatcher(run_id: str, capture, signal_classifier, *, run_started_dt):
    return run_lifecycle.BrokerOutputBatcher(
        run_id,
        capture,
        signal_classifier,
        run_started_dt=run_started_dt,
        capture_event_with_signals_fn=lambda *args, **kwargs: _capture_event_with_signals(*args, **kwargs),
        broker_output_payload_fn=lambda *args, **kwargs: _broker_output_payload(*args, **kwargs),
        publish_run_event_fn=lambda *args, **kwargs: publish_run_event(*args, **kwargs),
        to_wire_fn=to_wire,
        monotonic_fn=time.monotonic,
        live_batch_size=_RUN_OUTPUT_LIVE_BATCH_SIZE,
        max_age_seconds=_RUN_OUTPUT_LIVE_BATCH_MAX_AGE_SECONDS,
        max_latency_seconds=_RUN_OUTPUT_LIVE_BATCH_MAX_LATENCY_SECONDS,
        coalesced_roles=_RUN_OUTPUT_LIVE_BATCH_COALESCED_ROLES,
    )


def _process_group_is_gone(pgid: int) -> bool:
    return run_lifecycle.process_group_is_gone(pgid, delays=_KILL_PROCESS_GROUP_GONE_DELAYS)


def _signal_process_group(pgid: int) -> None:
    run_lifecycle.signal_process_group(
        pgid,
        scanner_prefix=SCANNER_PREFIX,
        sudo_bin=SUDO_BIN,
        kill_bin=KILL_BIN,
        gone_delays=_KILL_PROCESS_GROUP_GONE_DELAYS,
        subprocess_run_fn=subprocess.run,
    )


def _ensure_scanner_process_group_current(
    run_id: str,
    pid: int,
    session_id: str,
    team_id: str = "",
) -> None:
    run_lifecycle.ensure_scanner_process_group_current(
        run_id,
        pid,
        session_id,
        team_id=team_id,
        scanner_prefix=SCANNER_PREFIX,
        active_run_pid_start_matches_fn=active_run_pid_start_matches,
    )


_SEARCH_ENTITY_MAX_BYTES = run_finalization.SEARCH_ENTITY_MAX_BYTES
_line_events_from_output_entries = run_finalization.line_events_from_output_entries
_bounded_entity_search_values = run_finalization.bounded_entity_search_values
_search_text_from_events = run_finalization.search_text_from_events
_extract_output_search_text = run_finalization.extract_output_search_text
_log_atlas_entities_captured = run_finalization.log_atlas_entities_captured


def _save_completed_run(
    run_id,
    session_id,
    team_id,
    command,
    run_started,
    finished_iso,
    exit_code,
    capture,
    *,
    workspace_artifacts=None,
    link_active_project=True,
    link_project_id="",
    run_kind=RUN_KIND_EXTERNAL,
    owner_tab_id="",
    finalize_summary=None,
    cfg=None,
):
    active_cfg = CFG if cfg is None else cfg
    return run_finalization.save_completed_run(
        run_id,
        session_id,
        team_id,
        command,
        run_started,
        finished_iso,
        exit_code,
        capture,
        workspace_artifacts=workspace_artifacts,
        link_active_project=link_active_project,
        link_project_id=link_project_id,
        run_kind=run_kind,
        owner_tab_id=owner_tab_id,
        finalize_summary=finalize_summary,
        cfg=active_cfg,
        load_full_output_entries_fn=load_full_output_entries,
        workspace_artifacts_with_sizes_fn=_workspace_artifacts_with_sizes,
        record_run_findings_fn=record_run_findings,
        materialize_run_entities_fn=materialize_run_entities,
        run_persistence_transaction_fn=run_persistence_transaction,
        apply_auto_promote_rules_for_run_fn=apply_auto_promote_rules_for_run,
        command_project_target_inputs_fn=command_project_target_inputs,
        record_project_target_discoveries_fn=record_project_target_discoveries,
        link_active_project_run_entities_fn=link_active_project_run_entities,
    )


def _finalize_completed_run(
    run_id,
    session_id,
    team_id,
    client_ip,
    original_command,
    run_started,
    exit_code,
    capture,
    *,
    cmd_type="real",
    workspace_artifacts=None,
    owner_tab_id="",
    link_project_id="",
):
    return run_finalization.finalize_completed_run(
        run_id,
        session_id,
        team_id,
        client_ip,
        original_command,
        run_started,
        exit_code,
        capture,
        cmd_type=cmd_type,
        workspace_artifacts=workspace_artifacts,
        owner_tab_id=owner_tab_id,
        link_project_id=link_project_id,
        cfg=CFG,
        save_completed_run_fn=_save_completed_run,
    )


def _persist_completed_pty_run(
    run,
    execution_command: str,
    finished_iso: str,
    exit_code: int,
    synthesized_lines,
    *,
    transcript_mode: object = "final_frame",
    owner_tab_id: str = "",
):
    return run_finalization.persist_completed_pty_run(
        run,
        execution_command,
        finished_iso,
        exit_code,
        synthesized_lines,
        transcript_mode=transcript_mode,
        owner_tab_id=owner_tab_id,
        cfg=CFG,
        capture_factory=_run_output_capture,
        capture_event_with_signals_fn=_capture_event_with_signals,
        save_completed_run_fn=_save_completed_run,
    )


_shape_completed_pty_entries = shape_completed_pty_entries


def _normalize_client_side_run_lines(lines, command: str):
    return run_finalization.normalize_client_side_run_lines(
        lines,
        command,
        cfg=resolve_effective_cfg(),
        capture_event_with_signals_fn=_capture_event_with_signals,
        output_signal_classifier_cls=OutputSignalClassifier,
        get_share_redaction_rules_fn=get_share_redaction_rules,
    )


_SyntheticPostFilterStageProcessor = run_postfilters.SyntheticPostFilterStageProcessor
_SyntheticPostFilterProcessor = run_postfilters.SyntheticPostFilterProcessor
_parse_jq_input_values = run_postfilters.parse_jq_input_values
_jq_path_value = run_postfilters.jq_path_value
_jq_path_exists = run_postfilters.jq_path_exists
_select_jq_values = run_postfilters.select_jq_values
_jq_filter_text = run_postfilters.jq_filter_text
_format_jq_value = run_postfilters.format_jq_value
_WorkspacePathOutputFilter = run_postfilters.WorkspacePathOutputFilter
_TruffleHogOutputFilter = run_postfilters.TruffleHogOutputFilter

_PreparedCommandInput = run_lifecycle.PreparedCommandInput
_PreparedRealCommand = run_lifecycle.PreparedRealCommand
_StartedRealCommand = run_lifecycle.StartedRealCommand


def _preparation_error_response(exc: _RunPreparationError):
    return jsonify({"error": str(exc)}), exc.status_code


def _run_start_handlers() -> RunStartHandlers:
    return RunStartHandlers(
        resolves_exact_special_builtin_command=resolves_exact_special_builtin_command,
        execute_builtin_command=execute_builtin_command,
        history_safe_command_for_storage=_history_safe_command_for_storage,
        brokered_synthetic_run=_brokered_synthetic_run,
        prepare_command_input=_prepare_command_input,
        resolve_builtin_command=resolve_builtin_command,
        filter_builtin_command_events=_filter_builtin_command_events,
        prepare_real_command=_prepare_real_command,
        runtime_missing_command_message=runtime_missing_command_message,
        start_real_command_process=_start_real_command_process,
        publish_run_event=publish_run_event,
        brokered_real_run_worker=_brokered_real_run_worker,
        workspace_notice_lines=_workspace_notice_lines,
        workspace_artifacts_from_validation=_workspace_artifacts_from_validation,
    )


_cmd_denied_log_extra = run_lifecycle.cmd_denied_log_extra


def _prepare_interactive_pty_command(
    original_command: str,
    session_id: str,
    client_ip: str,
    workspace_cwd: str = "",
    *,
    owner_context: OwnerContext | None = None,
) -> tuple[list[str], str, dict[str, object]]:
    return run_lifecycle.prepare_interactive_pty_command(
        original_command,
        session_id,
        client_ip,
        workspace_cwd,
        owner_context=owner_context,
        split_command_argv_fn=split_command_argv,
        interactive_pty_spec_for_command_fn=interactive_pty_spec_for_command,
        validate_command_with_effective_owner_fn=_validate_command_with_effective_owner,
        runtime_missing_command_name_fn=runtime_missing_command_name,
        runtime_missing_command_message_fn=runtime_missing_command_message,
        cmd_denied_log_extra_fn=_cmd_denied_log_extra,
    )


def _prepare_command_input(
    original_command: str,
    session_id: str,
    client_ip: str,
    *,
    log_pipe: bool = False,
    **private_kwargs,
) -> _PreparedCommandInput:
    return run_lifecycle.prepare_command_input(
        original_command,
        session_id,
        client_ip,
        log_pipe=log_pipe,
        command_root_fn=command_root,
        expand_session_variables_fn=expand_session_variables,
        parse_synthetic_postfilter_fn=parse_synthetic_postfilter,
        postfilter_processor_cls=_SyntheticPostFilterProcessor,
        variable_notice_line_fn=_variable_notice_line,
        cmd_denied_log_extra_fn=_cmd_denied_log_extra,
        **private_kwargs,
    )


_filter_builtin_command_events = run_lifecycle.filter_builtin_command_events
_runtime_env_names = run_lifecycle.runtime_env_names


def _resolve_secret_environment(command: str, session_id: str, *, team_id: str = "", **private_kwargs) -> tuple[dict[str, str], list[str]]:  # noqa: E501
    return run_lifecycle.resolve_secret_environment(
        command,
        session_id,
        team_id=team_id,
        get_secret_value_for_env_fn=get_secret_value_for_env,
        **private_kwargs,
    )


def _prepare_real_command(
    original_command: str,
    execution_command: str,
    session_id: str,
    client_ip: str,
    workspace_cwd: str = "",
    *,
    team_id: str = "",
    owner_context: OwnerContext | None = None,
    **private_kwargs,
) -> _PreparedRealCommand:
    return run_lifecycle.prepare_real_command(
        original_command,
        execution_command,
        session_id,
        client_ip,
        workspace_cwd,
        team_id=team_id,
        owner_context=owner_context,
        effective_owner_context_fn=_effective_owner_context,
        validate_command_with_owner_fn=_validate_command_with_effective_owner,
        rewrite_command_fn=rewrite_command,
        runtime_missing_command_name_fn=runtime_missing_command_name,
        resolve_secret_environment_fn=_resolve_secret_environment,
        command_root_fn=command_root,
        cmd_denied_log_extra_fn=_cmd_denied_log_extra,
        cfg=CFG,
        **private_kwargs,
    )


def _real_command_popen_argv(prepared_real: _PreparedRealCommand) -> list[str]:
    return run_lifecycle.real_command_popen_argv(
        prepared_real,
        scanner_prefix=SCANNER_PREFIX,
        stdbuf_bin=STDBUF_BIN,
        shell_bin=SHELL_BIN,
    )


def _line_buffered_shell_argv(command: str) -> list[str]:
    return run_lifecycle.line_buffered_shell_argv(command, stdbuf_bin=STDBUF_BIN, shell_bin=SHELL_BIN)


_secret_aware_shell_command = run_lifecycle.secret_aware_shell_command
_shodan_configured_shell_command = run_lifecycle.shodan_configured_shell_command
_history_safe_command_for_storage = run_lifecycle.history_safe_command_for_storage


def _start_real_command_process(
    original_command: str,
    session_id: str,
    client_ip: str,
    prepared_real: _PreparedRealCommand,
    *,
    owner_client_id: str = "",
    owner_tab_id: str = "",
    team_id: str = "",
    owner_context: OwnerContext | None = None,
    **private_kwargs,
) -> _StartedRealCommand:
    return run_lifecycle.start_real_command_process(
        original_command,
        session_id,
        client_ip,
        prepared_real,
        owner_client_id=owner_client_id,
        owner_tab_id=owner_tab_id,
        team_id=team_id,
        owner_context=owner_context,
        cfg=CFG,
        run_output_capture_fn=_run_output_capture,
        popen_fn=subprocess.Popen,
        preexec_fn=_prepare_run_child,
        pid_register_fn=pid_register,
        active_run_register_fn=active_run_register,
        emit_secret_event_fn=emit_secret_event,
        output_signal_classifier_cls=OutputSignalClassifier,
        workspace_path_filter_cls=_WorkspacePathOutputFilter,
        owner_context_for_scope_fn=owner_context_for_scope,
        command_root_fn=command_root,
        scanner_prefix=SCANNER_PREFIX,
        stdbuf_bin=STDBUF_BIN,
        shell_bin=SHELL_BIN,
        datetime_cls=datetime,
        **private_kwargs,
    )


def _publish_broker_captured_line(
    run_id: str,
    capture,
    signal_classifier,
    event_type: str,
    text: str,
    *,
    cls: str = "",
    kind: LineKind | str | None = None,
    event: LineEvent | None = None,
    run_started_dt, publish: bool = True,
):
    run_lifecycle.publish_broker_captured_line(
        run_id,
        capture,
        signal_classifier,
        event_type,
        text,
        cls=cls,
        kind=kind,
        event=event,
        run_started_dt=run_started_dt,
        publish=publish,
        capture_event_with_signals_fn=_capture_event_with_signals,
        broker_output_payload_fn=_broker_output_payload,
        publish_run_event_fn=publish_run_event,
    )


def _brokered_synthetic_run(
    original_command,
    session_id,
    client_ip,
    events,
    exit_code=0,
    *,
    cmd_type="builtin",
    owner_tab_id="",
    team_id="", **kwargs,
):
    return run_lifecycle.brokered_synthetic_run(
        original_command,
        session_id,
        client_ip,
        events,
        exit_code,
        cmd_type=cmd_type,
        owner_tab_id=owner_tab_id,
        team_id=team_id,
        cfg=CFG,
        run_output_capture_fn=_run_output_capture,
        output_signal_classifier_cls=OutputSignalClassifier,
        publish_run_event_fn=publish_run_event,
        publish_broker_captured_line_fn=_publish_broker_captured_line,
        save_completed_run_fn=_save_completed_run,
        app_metrics_obj=app_metrics, **kwargs,
    )


def _publish_counted_project_notice(
    run_id: str,
    *,
    count: int,
    singular: str,
    plural: str,
    text_template: str,
    payload: dict[str, object],
) -> None:
    run_lifecycle.publish_counted_project_notice(
        run_id,
        count=count,
        singular=singular,
        plural=plural,
        text_template=text_template,
        payload=payload,
        publish_run_event_fn=publish_run_event,
    )


def _publish_project_finalize_notices(run_id: str, active_project_link, finalize_summary) -> None:
    run_lifecycle.publish_project_finalize_notices(
        run_id,
        active_project_link,
        finalize_summary,
        publish_run_event_fn=publish_run_event,
    )


def _brokered_real_run_worker(**kwargs):
    run_lifecycle.brokered_real_run_worker(
        **kwargs,
        cfg=CFG,
        trufflehog_output_filter_cls=_TruffleHogOutputFilter,
        publish_broker_captured_line_fn=_publish_broker_captured_line,
        output_batcher_cls=_BrokerOutputBatcher,
        make_nonblocking_stream_reader_fn=_make_nonblocking_stream_reader,
        stdout_ready_fn=_stdout_ready,
        read_available_stream_lines_fn=_read_available_stream_lines,
        wait_for_proc_exit_code_fn=_wait_for_proc_exit_code,
        timeout_notice_fn=_timeout_notice,
        terminate_process_group_fn=_terminate_process_group,
        finalize_completed_run_fn=_finalize_completed_run,
        publish_project_finalize_notices_fn=_publish_project_finalize_notices,
        publish_run_event_fn=publish_run_event,
        cleanup_proc_stream_fn=_cleanup_proc_stream,
        pid_pop_fn=pid_pop,
        active_run_remove_fn=active_run_remove,
        poll_seconds=_RUN_OUTPUT_POLL_SECONDS,
        datetime_cls=datetime,
    )


def _run_belongs_to_session(run_id: str, session_id: str) -> bool:
    return bool(_run_session_visibility(run_id, session_id, "")["allowed"])


def pty_run_belongs_to_session(run_id: str, session_id: str) -> bool:
    return pty_run_belongs_to_scope(run_id, session_id, "")


_run_scope_mismatch_payload = run_lifecycle.run_scope_mismatch_payload


def _run_visibility_error_response(visibility: _RunSessionVisibility):
    if visibility.get("scope_mismatch"):
        return jsonify(_run_scope_mismatch_payload(str(visibility.get("actual_team_id", "") or ""))), 409
    return jsonify({"error": "Run not found"}), 404


def _run_session_visibility(run_id: str, session_id: str, team_id: str = "") -> _RunSessionVisibility:
    return run_lifecycle.run_session_visibility(
        run_id,
        session_id,
        team_id,
        active_run_belongs_to_scope_fn=active_run_belongs_to_scope,
        active_runs_for_team_fn=active_runs_for_team,
        active_runs_for_session_fn=active_runs_for_session,
        run_scope_visibility_from_db_fn=run_scope_visibility_from_db,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

from blueprints import run_broker as _run_broker_routes  # noqa: E402,F401
from blueprints import run_client as _run_client_routes  # noqa: E402,F401
from blueprints import run_kill as _run_kill_routes  # noqa: E402,F401
from blueprints import run_pty as _run_pty_routes  # noqa: E402,F401

_RUN_ROUTE_EXPORTS = {
    **dict.fromkeys(("get_brokered_run_events", "start_brokered_run", "stream_brokered_run"), _run_broker_routes),
    "save_client_side_run": _run_client_routes, "kill_command": _run_kill_routes,
    **dict.fromkeys((
        "resize_interactive_pty_run", "send_interactive_pty_input", "snapshot_interactive_pty_run",
        "start_interactive_pty_run", "stream_interactive_pty_run",
    ), _run_pty_routes),
}


def __getattr__(name: str):
    if name in _RUN_ROUTE_EXPORTS:
        return getattr(_RUN_ROUTE_EXPORTS[name], name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
