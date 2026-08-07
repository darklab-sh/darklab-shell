# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Run command preparation and process lifecycle helpers."""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config import SCANNER_PREFIX, resolve_effective_cfg
from core.helpers import get_log_session_id
from core.output_signals import OutputSignalClassifier
from services.commands.registry import (
    CommandValidationResult,
    command_root,
    interactive_pty_spec_for_command,
    parse_synthetic_postfilter,
    rewrite_command,
    runtime_missing_command_name,
    runtime_missing_command_message,
    split_command_argv,
)
from services.commands.raw_packets import scan_transport_log_context
from services.runs.broker_worker import (
    BrokerOutputBatcher,  # noqa: F401 - compatibility seam for blueprints.run/tests
    brokered_real_run_worker,  # noqa: F401 - compatibility seam for blueprints.run/tests
    brokered_synthetic_run,  # noqa: F401 - compatibility seam for blueprints.run/tests
    publish_broker_captured_line,  # noqa: F401 - compatibility seam for blueprints.run/tests
)
from services.runs.output_model import LineKind, line_event_from_legacy, to_legacy_output_event
from services.runs.output_store import RunOutputCapture
from services.runs.process_control import (
    ensure_scanner_process_group_current as _ensure_scanner_process_group_current,
    process_group_is_gone as process_group_is_gone,
    signal_process_group as _signal_process_group,
)
from services.runs.project_notices import (
    publish_counted_project_notice as publish_counted_project_notice,
    publish_project_finalize_notices as publish_project_finalize_notices,
)
from services.runs.scope import (
    RunSessionVisibility as RunSessionVisibility,
    effective_owner_context as effective_owner_context,
    run_scope_mismatch_payload as run_scope_mismatch_payload,
    run_session_visibility as run_session_visibility,
    validate_command_for_run as validate_command_for_run,
    validate_command_with_effective_owner,
)
from services.runs.start import (
    RunPreparationError,
    RunSpawnError,
)
from services.runs.private_data import (
    contains_private_value,
    redact_private_values,
    resolve_secret_environment,
)
from services.secrets.audit import emit_secret_event
from services.session.variables import SessionVariableError, expand_session_variables
from services.teams.scope import OwnerContext, owner_context_for_scope, personal_owner_context

log = logging.getLogger("shell")

SHELL_BIN = shutil.which("sh") or "/bin/sh"
STDBUF_BIN = shutil.which("stdbuf")
SUDO_BIN = shutil.which("sudo") or "/usr/bin/sudo"
KILL_BIN = shutil.which("kill") or "/bin/kill"


@dataclass(frozen=True)
class PreparedCommandInput:
    execution_command: str
    variable_notice: str
    postfilter: Any


@dataclass(frozen=True)
class PreparedRealCommand:
    registry_command: str
    execution_command: str
    command: str
    rewrite_notice: str | None
    validation: CommandValidationResult
    missing_runtime: str | None
    display_missing_runtime: str | None
    env_overrides: dict[str, str]
    secret_env_names: list[str]


@dataclass(frozen=True)
class StartedRealCommand:
    run_id: str
    run_started: str
    proc: subprocess.Popen
    capture: RunOutputCapture
    signal_classifier: OutputSignalClassifier
    workspace_path_filter: Any


def signal_process_group(
    pgid: int,
    *,
    scanner_prefix: list[str] | tuple[str, ...] | str | None = None,
    sudo_bin: str = SUDO_BIN,
    kill_bin: str = KILL_BIN,
    gone_delays: tuple[float, ...],
    subprocess_run_fn: Callable[..., Any] = subprocess.run,
) -> None:
    _signal_process_group(
        pgid,
        scanner_prefix=scanner_prefix,
        sudo_bin=sudo_bin,
        kill_bin=kill_bin,
        gone_delays=gone_delays,
        subprocess_run_fn=subprocess_run_fn,
    )


def ensure_scanner_process_group_current(
    run_id: str,
    pid: int,
    session_id: str,
    team_id: str = "",
    *,
    scanner_prefix: list[str] | tuple[str, ...] | str | None = None,
    active_run_pid_start_matches_fn: Callable[..., bool],
) -> None:
    _ensure_scanner_process_group_current(
        run_id,
        pid,
        session_id,
        team_id,
        scanner_prefix=scanner_prefix,
        active_run_pid_start_matches_fn=active_run_pid_start_matches_fn,
    )


def workspace_notice_lines(validation: CommandValidationResult) -> list[str]:
    notices: list[str] = []
    for path in validation.workspace_reads:
        notices.append(f"[workspace] reading {path}")
    for path in validation.workspace_writes:
        notices.append(f"[workspace] writing {path}")
    return notices


def variable_notice_line(expanded_command: str, used_names: tuple[str, ...]) -> str:
    variables = ", ".join(f"${name}" for name in used_names)
    return f"[vars] expanded {variables}: {expanded_command}"


def cmd_denied_log_extra(client_ip: str, session_id: str, command: str, reason: str) -> dict[str, Any]:
    reason_text = str(reason or "")
    deny_kind, rule_id = "policy", ""
    if "raw-packet" in (reason_lower := reason_text.lower()) or "nmap raw mode" in reason_lower or " is blocked:" in reason_lower:
        deny_kind = "raw_packet"
        rule_id = "raw_packet_policy" if " is blocked:" in reason_lower else "raw_packet_readiness"
    elif "secret" in reason_lower or "vault" in reason_lower:
        deny_kind = "secret"
    elif "workspace" in reason_lower or "path" in reason_lower:
        deny_kind = "workspace"
    elif "shell operators" in reason_lower:
        deny_kind = "shell_operator"
    return {
        "ip": client_ip, "session": get_log_session_id(session_id),
        "cmd": command, "reason": reason_text,
        "deny_kind": deny_kind, "rule_id": rule_id,
    }


def filter_builtin_command_events(events, variable_notice: str, postfilter) -> list[dict[str, Any]]:
    if variable_notice:
        events = [to_legacy_output_event(line_event_from_legacy(variable_notice, kind=LineKind.notice))] + events
    filtered_events = []
    for event in events:
        if event.get("type") != "output":
            filtered_events.append(event)
            continue
        for filtered_line in postfilter.process_output_line(str(event.get("text", ""))):
            filtered_event = dict(event)
            filtered_event["text"] = filtered_line.rstrip("\n")
            if not postfilter.should_publish_output_line(filtered_line):
                filtered_event["suppress_live"] = True
            filtered_events.append(filtered_event)
    for filtered_line in postfilter.finalize_output_lines():
        filtered_event = {"type": "output", "text": filtered_line.rstrip("\n")}
        if not postfilter.should_publish_output_line(filtered_line):
            filtered_event["suppress_live"] = True
        filtered_events.append(filtered_event)
    return filtered_events


def prepare_interactive_pty_command(
    original_command: str,
    session_id: str,
    client_ip: str,
    workspace_cwd: str = "",
    *,
    owner_context: OwnerContext | None = None,
    split_command_argv_fn: Callable[[str], list[str]] = split_command_argv,
    interactive_pty_spec_for_command_fn: Callable[[str], dict[str, Any] | None] = interactive_pty_spec_for_command,
    validate_command_with_effective_owner_fn: Callable[..., CommandValidationResult] = validate_command_with_effective_owner,
    runtime_missing_command_name_fn: Callable[[str], str | None] = runtime_missing_command_name,
    runtime_missing_command_message_fn: Callable[[str], str] = runtime_missing_command_message,
    cmd_denied_log_extra_fn: Callable[[str, str, str, str], dict[str, Any]] = cmd_denied_log_extra,
) -> tuple[list[str], str, dict[str, Any]]:
    tokens = split_command_argv_fn(original_command)
    spec = interactive_pty_spec_for_command_fn(original_command)
    if not tokens or not spec:
        root = tokens[0].lower() if tokens else "command"
        raise RunPreparationError(f"Interactive PTY mode is not available for {root}", status_code=403)
    trigger_flag = str(spec.get("trigger_flag") or "").strip()
    if not trigger_flag or trigger_flag not in tokens[1:]:
        root = str(spec.get("root") or tokens[0].lower())
        raise RunPreparationError(
            f"{root} interactive PTY commands must include {trigger_flag or 'the configured trigger flag'}",
            status_code=400,
        )
    argv = [token for token in tokens if token != trigger_flag]
    if bool(spec.get("requires_args", False)) and len(argv) < 2:
        root = str(spec.get("root") or tokens[0].lower())
        raise RunPreparationError(f"{root} {trigger_flag} requires command arguments", status_code=400)
    execution_command = shlex.join(argv)
    extra_allowed_prefixes = [str(spec.get("root") or tokens[0].lower())]
    validation = validate_command_with_effective_owner_fn(
        execution_command,
        session_id,
        workspace_cwd,
        extra_allowed_prefixes=extra_allowed_prefixes,
        owner_context=owner_context,
    )
    if not validation.allowed:
        log.warning("CMD_DENIED", extra=cmd_denied_log_extra_fn(client_ip, session_id, original_command, validation.reason))
        raise RunPreparationError(validation.reason)
    execution_command = validation.exec_command or execution_command
    missing_runtime = runtime_missing_command_name_fn(execution_command)
    if missing_runtime:
        raise RunPreparationError(runtime_missing_command_message_fn(missing_runtime), status_code=503)
    return split_command_argv_fn(execution_command), execution_command, spec


def runtime_env_names(command: str) -> list[str]:
    names: list[str] = []
    tokens = split_command_argv(command)
    start = 1 if tokens and tokens[0] == "env" else 0
    for token in tokens[start:]:
        if "=" not in token or token.startswith("-"):
            break
        name = token.split("=", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            names.append(name)
            continue
        break
    return names


def prepare_command_input(
    original_command: str,
    session_id: str,
    client_ip: str,
    *,
    display_command: str = "",
    private_values: tuple[str, ...] = (),
    log_pipe: bool = False,
    owner_context: OwnerContext | None = None,
    team_role: str = "",
    workspace_cwd: str = "",
    cfg: Mapping[str, Any] | None = None,
    command_root_fn: Callable[[str], str | None] = command_root,
    expand_session_variables_fn: Callable[..., Any] = expand_session_variables,
    parse_synthetic_postfilter_fn: Callable[[str], tuple[dict[str, Any] | None, str | None]] = parse_synthetic_postfilter,
    postfilter_processor_cls: Callable[[dict[str, Any] | None], Any],
    variable_notice_line_fn: Callable[[str, tuple[str, ...]], str],
    cmd_denied_log_extra_fn: Callable[[str, str, str, str], dict[str, Any]],
) -> PreparedCommandInput:
    safe_command = str(display_command or original_command)
    expanded_command = original_command
    variable_notice = ""
    if command_root_fn(original_command) != "var":
        try:
            expansion = expand_session_variables_fn(original_command, session_id)
            expanded_command = expansion.command
            if expanded_command != original_command:
                safe_expansion = expand_session_variables_fn(safe_command, session_id)
                variable_notice = variable_notice_line_fn(safe_expansion.command, expansion.used_names)
        except SessionVariableError as exc:
            safe_error = redact_private_values(exc, private_values)
            log.warning("CMD_DENIED", extra=cmd_denied_log_extra_fn(client_ip, session_id, safe_command, safe_error))
            raise RunPreparationError(safe_error) from exc

    postfilter_spec, postfilter_error = parse_synthetic_postfilter_fn(expanded_command)
    if postfilter_error:
        safe_error = redact_private_values(postfilter_error, private_values)
        log.warning("CMD_DENIED", extra=cmd_denied_log_extra_fn(client_ip, session_id, safe_command, safe_error))
        raise RunPreparationError(safe_error)
    execution_command = postfilter_spec["base_command"] if postfilter_spec else expanded_command
    if log_pipe and postfilter_spec:
        stage_kinds = [stage.get("kind") for stage in postfilter_spec.get("stages", []) if stage.get("kind")]
        log.debug("CMD_PIPE", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": safe_command,
            "kind": " -> ".join(stage_kinds) if stage_kinds else postfilter_spec.get("kind"),
        })
    try:
        postfilter = postfilter_processor_cls(postfilter_spec)
        if postfilter_spec and postfilter_spec.get("sink"):
            postfilter.configure_output_sink(
                owner_context=owner_context or personal_owner_context(session_id),
                team_role=team_role,
                workspace_cwd=workspace_cwd,
                cfg=resolve_effective_cfg(cfg),
            )
    except ValueError as exc:
        raise RunPreparationError(redact_private_values(exc, private_values)) from exc
    return PreparedCommandInput(
        execution_command=execution_command,
        variable_notice=variable_notice,
        postfilter=postfilter,
    )


def prepare_real_command(
    original_command: str,
    execution_command: str,
    session_id: str,
    client_ip: str,
    workspace_cwd: str = "",
    *,
    display_command: str = "",
    private_values: tuple[str, ...] = (),
    team_id: str = "",
    owner_context: OwnerContext | None = None,
    effective_owner_context_fn: Callable[[OwnerContext | None, str], OwnerContext | None],
    validate_command_with_owner_fn: Callable[..., CommandValidationResult],
    rewrite_command_fn: Callable[..., tuple[str, str | None]] = rewrite_command,
    runtime_missing_command_name_fn: Callable[[str], str | None] = runtime_missing_command_name,
    resolve_secret_environment_fn: Callable[..., tuple[dict[str, str], list[str]]] = resolve_secret_environment,
    command_root_fn: Callable[[str], str | None] = command_root,
    cmd_denied_log_extra_fn: Callable[[str, str, str, str], dict[str, Any]],
    cfg: Mapping[str, Any] | None = None,
) -> PreparedRealCommand:
    safe_command = str(display_command or original_command)
    active_cfg = resolve_effective_cfg(cfg)
    registry_command = execution_command
    effective_context = effective_owner_context_fn(owner_context, session_id)
    validation = validate_command_with_owner_fn(
        execution_command,
        session_id,
        workspace_cwd,
        owner_context=effective_context,
    )
    if not validation.allowed:
        safe_reason = redact_private_values(validation.reason, private_values)
        log.warning(
            "CMD_DENIED",
            extra=cmd_denied_log_extra_fn(
                client_ip,
                session_id,
                safe_command,
                safe_reason,
            ),
        )
        raise RunPreparationError(safe_reason)
    execution_command = validation.exec_command or execution_command
    if effective_context is not None:
        command, notice = rewrite_command_fn(
            execution_command,
            session_id=session_id,
            cfg=active_cfg,
            owner_context=effective_context,
        )
    else:
        command, notice = rewrite_command_fn(execution_command, session_id=session_id, cfg=active_cfg)
    if command != execution_command:
        log.debug("CMD_REWRITE_APPLIED", extra={
            "ip": client_ip,
            "session": get_log_session_id(session_id),
            "command_root": command_root_fn(safe_command) or "",
            "rewrite_notice": redact_private_values(notice or "", private_values),
            "workspace_read_count": len(validation.workspace_reads),
            "workspace_write_count": len(validation.workspace_writes),
            "workspace_exec_path_count": len(validation.workspace_exec_paths),
            "runtime_env_names": runtime_env_names(command),
        })
    missing_runtime = runtime_missing_command_name_fn(command)
    display_missing_runtime = missing_runtime
    if missing_runtime and safe_command != original_command:
        display_missing_runtime = command_root_fn(safe_command) or "command"
    if missing_runtime:
        log.warning("CMD_MISSING", extra={
            "ip": client_ip, "session": get_log_session_id(session_id),
            "cmd": safe_command, "missing": display_missing_runtime,
        })
    resolve_secret_kwargs: dict[str, object] = {"team_id": team_id}
    if private_values:
        resolve_secret_kwargs["display_command"] = safe_command
    env_overrides, secret_env_names = resolve_secret_environment_fn(
        registry_command,
        session_id,
        **resolve_secret_kwargs,
    )
    return PreparedRealCommand(
        registry_command=registry_command,
        execution_command=execution_command,
        command=command,
        rewrite_notice=redact_private_values(notice or "", private_values) or None,
        validation=validation,
        missing_runtime=missing_runtime,
        display_missing_runtime=display_missing_runtime,
        env_overrides=env_overrides,
        secret_env_names=secret_env_names,
    )


def real_command_popen_argv(
    prepared_real: PreparedRealCommand,
    *,
    scanner_prefix: list[str] | tuple[str, ...] | str | None = None,
    stdbuf_bin: str | None = None,
    shell_bin: str | None = None,
) -> list[str]:
    configured_prefix = SCANNER_PREFIX if scanner_prefix is None else scanner_prefix
    prefix = [configured_prefix] if isinstance(configured_prefix, str) else list(configured_prefix or [])
    if prefix and prepared_real.secret_env_names and prefix[0] == "sudo":
        prefix.insert(1, "--preserve-env=" + ",".join(prepared_real.secret_env_names))
    command = secret_aware_shell_command(prepared_real)
    command_argv = line_buffered_shell_argv(
        command,
        stdbuf_bin=STDBUF_BIN if stdbuf_bin is None else stdbuf_bin,
        shell_bin=SHELL_BIN if shell_bin is None else shell_bin,
    )
    return prefix + command_argv if prefix else command_argv


def line_buffered_shell_argv(command: str, *, stdbuf_bin: str | None = None, shell_bin: str | None = None) -> list[str]:
    shell_argv = [shell_bin or SHELL_BIN, "-c", command]
    if not stdbuf_bin:
        return shell_argv
    return [stdbuf_bin, "-oL", "-eL", *shell_argv]


def secret_aware_shell_command(prepared_real: PreparedRealCommand) -> str:
    if (
        command_root(prepared_real.registry_command) == "shodan" and
        "SHODAN_API_KEY" in prepared_real.secret_env_names
    ):
        return shodan_configured_shell_command(prepared_real.command)
    return prepared_real.command


def shodan_configured_shell_command(command: str) -> str:
    warnings_filter = "ignore:pkg_resources is deprecated as an API:UserWarning"
    return (
        "__darklab_shodan_home=$(mktemp -d) && "
        "trap 'rm -rf \"$__darklab_shodan_home\"' EXIT HUP INT TERM && "
        "mkdir -p \"$__darklab_shodan_home/.shodan\" && "
        "chmod 700 \"$__darklab_shodan_home/.shodan\" && "
        "printf '%s' \"$SHODAN_API_KEY\" > \"$__darklab_shodan_home/.shodan/api_key\" && "
        "chmod 600 \"$__darklab_shodan_home/.shodan/api_key\" && "
        f"HOME=\"$__darklab_shodan_home\" PYTHONWARNINGS={shlex.quote(warnings_filter)} {command}"
    )


def history_safe_command_for_storage(command: str) -> str:
    parts = split_command_argv(command)
    if len(parts) > 3 and parts[0].lower() == "secret" and parts[1].lower() == "set":
        return f"secret set {parts[2]}"
    return command


def start_real_command_process(
    original_command: str,
    session_id: str,
    client_ip: str,
    prepared_real: PreparedRealCommand,
    *,
    private_values: tuple[str, ...] = (),
    owner_client_id: str = "",
    owner_tab_id: str = "",
    team_id: str = "",
    owner_context: OwnerContext | None = None,
    cfg: Mapping[str, Any] | None = None,
    run_output_capture_fn: Callable[[str], RunOutputCapture],
    popen_fn: Callable[..., subprocess.Popen] = subprocess.Popen,
    preexec_fn: Callable[[], None] | None = None,
    pid_register_fn: Callable[[str, int], Any],
    active_run_register_fn: Callable[..., Any],
    emit_secret_event_fn: Callable[..., Any] = emit_secret_event,
    output_signal_classifier_cls: Callable[..., OutputSignalClassifier] = OutputSignalClassifier,
    workspace_path_filter_cls: Callable[..., Any],
    owner_context_for_scope_fn: Callable[..., OwnerContext] = owner_context_for_scope,
    command_root_fn: Callable[[str], str | None] = command_root,
    scanner_prefix: list[str] | tuple[str, ...] | str | None = None,
    stdbuf_bin: str | None = None,
    shell_bin: str | None = None,
    datetime_cls: Any = datetime,
) -> StartedRealCommand:
    run_id = str(uuid.uuid4())
    run_started = datetime_cls.now(timezone.utc).isoformat()
    cfg_source = "explicit" if cfg is not None else "global"
    output_entity_suffix_count: int | None = None
    try:
        active_cfg = resolve_effective_cfg(cfg)
        output_entity_suffixes = active_cfg.get("output_entity_extra_domain_suffixes", [])
        output_entity_suffix_count = len(output_entity_suffixes) if hasattr(output_entity_suffixes, "__len__") else None
        capture = run_output_capture_fn(run_id)
        signal_classifier = output_signal_classifier_cls(
            original_command,
            cmd_type="real",
            extra_domain_suffixes=output_entity_suffixes,
            source_run_id=run_id,
        )
        workspace_owner = owner_context or owner_context_for_scope_fn(session_id, team_id=team_id)
        workspace_path_filter = workspace_path_filter_cls(session_id, active_cfg, owner_context=workspace_owner)
        env_overrides = dict(prepared_real.env_overrides)
    except Exception as exc:
        safe_error = redact_private_values(exc, private_values)
        log.error("RUN_SPAWN_SETUP_FAILED", exc_info=True, extra={
            "run_id": run_id,
            "ip": client_ip,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "cmd": original_command,
            "cfg_source": cfg_source,
            "workspace_filter": "init",
            "output_entity_suffix_count": output_entity_suffix_count,
        })
        raise RunSpawnError(safe_error) from exc
    log.debug("RUN_SPAWN_SETUP_RESOLVED", extra={
        "run_id": run_id,
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "cfg_source": cfg_source,
        "workspace_filter_enabled": bool(active_cfg.get("workspace_enabled")),
        "output_entity_suffix_count": output_entity_suffix_count,
    })
    popen_env = None

    try:
        if env_overrides:
            popen_env = os.environ.copy()
            popen_env.update(env_overrides)
        proc = popen_fn(
            real_command_popen_argv(
                prepared_real,
                scanner_prefix=scanner_prefix,
                stdbuf_bin=stdbuf_bin,
                shell_bin=shell_bin,
            ),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=preexec_fn,
            env=popen_env,
        )
    except Exception as exc:
        safe_error = redact_private_values(exc, private_values)
        safe_exc_info: object = True
        if contains_private_value(exc, private_values):
            safe_exception = RunSpawnError(safe_error)
            safe_exc_info = (RunSpawnError, safe_exception, exc.__traceback__)
        log.error("RUN_SPAWN_ERROR", exc_info=safe_exc_info, extra={
            "ip": client_ip, "session": get_log_session_id(session_id), "cmd": original_command,
        })
        raise RunSpawnError(safe_error) from exc
    finally:
        # Best-effort scrub of plaintext from the parent process after spawn.
        # Python strings are immutable, so this drops references rather than
        # guaranteeing bytewise heap clearing. The subprocess has its own copy.
        for key in env_overrides:
            env_overrides[key] = ""
        prepared_real.env_overrides.clear()
        if popen_env is not None:
            for key in prepared_real.secret_env_names:
                popen_env[key] = ""

    pid_register_fn(run_id, proc.pid)
    active_kwargs = {
        "owner_client_id": owner_client_id,
        "owner_tab_id": owner_tab_id,
    }
    if team_id:
        active_kwargs["team_id"] = team_id
    active_run_register_fn(
        run_id,
        proc.pid,
        session_id,
        original_command,
        run_started,
        **active_kwargs,
    )
    log.info("RUN_START", extra={
        "run_id": run_id, "session": get_log_session_id(session_id), "ip": client_ip,
        "pid": proc.pid, "cmd": original_command, "cmd_type": "real",
        **scan_transport_log_context(prepared_real.command, active_cfg),
    })
    if prepared_real.secret_env_names:
        emit_secret_event_fn(
            "SECRET_INJECTED",
            session_id,
            consumer_envs=prepared_real.secret_env_names,
            run_id=run_id,
            command_root=command_root_fn(original_command) or "",
        )
    return StartedRealCommand(
        run_id=run_id,
        run_started=run_started,
        proc=proc,
        capture=capture,
        signal_classifier=signal_classifier,
        workspace_path_filter=workspace_path_filter,
    )
