# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Private run-value handling and safe metadata helpers."""

from __future__ import annotations

import logging
from typing import Any, Callable

from core.helpers import get_log_session_id
from services.commands.registry import (
    command_root,
    is_help_invocation,
    required_secrets_for_command,
)
from services.runs.contracts import RunPreparationError
from services.runs.execution_override import apply_reviewed_execution
from services.runs.start_context import append_trusted_execution_args
from services.secrets.storage import InvalidSecretName, get_secret_value_for_env
from services.secrets.vault import MasterKeyError, SecretDecryptError

log = logging.getLogger("shell")


def status_for_exit_code(exit_code: object) -> str:
    if not isinstance(exit_code, (int, str, bytes, bytearray)):
        return "complete"
    try:
        return "succeeded" if int(exit_code) == 0 else "failed"
    except (TypeError, ValueError):
        return "complete"


def normalized_private_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}, key=len, reverse=True))


def contains_private_value(value: object, private_values: tuple[str, ...]) -> bool:
    text = str(value or "")
    return any(
        private_value in text
        for private_value in normalized_private_values(private_values)
    )


def redact_private_values(value: object, private_values: tuple[str, ...]) -> str:
    text = str(value or "")
    for private_value in normalized_private_values(private_values):
        if private_value not in text:
            continue
        if len(private_value) < 3:
            return "[redacted]"
        text = text.replace(private_value, "[redacted]")
    return text


def prepare_command_input(
    handlers: Any,
    original_command: str,
    display_command: str,
    session_id: str,
    client_ip: str,
    private_values: tuple[str, ...],
    **run_context: object,
) -> Any:
    kwargs: dict[str, object] = {"display_command": display_command, **run_context}
    if private_values:
        kwargs["private_values"] = private_values
    return handlers.prepare_command_input(original_command, session_id, client_ip, **kwargs)


def prepare_real_command(
    handlers: Any,
    original_command: str,
    execution_command: str,
    display_command: str,
    session_id: str,
    client_ip: str,
    workspace_cwd: str,
    private_values: tuple[str, ...],
    *,
    team_id: str,
    owner_context: object,
    trusted_execution_args: tuple[str, ...] = (),
    reviewed_execution: object | None = None,
    output_signal_context: object | None = None,
) -> Any:
    kwargs: dict[str, object] = {"display_command": display_command}
    if private_values:
        kwargs["private_values"] = private_values
    if team_id:
        kwargs.update({"team_id": team_id, "owner_context": owner_context})
    prepared = handlers.prepare_real_command(
        original_command,
        execution_command,
        session_id,
        client_ip,
        workspace_cwd,
        **kwargs,
    )
    prepared = apply_reviewed_execution(
        prepared,
        reviewed_execution,
        output_signal_context=output_signal_context,
    )
    return append_trusted_execution_args(prepared, trusted_execution_args)


def public_workspace_metadata(
    handlers: Any,
    validation: Any,
    session_id: str,
    private_values: tuple[str, ...],
) -> tuple[list[str], list[dict[str, Any]]]:
    notices = [
        notice
        for notice in handlers.workspace_notice_lines(validation)
        if not contains_private_value(notice, private_values)
    ]
    artifacts = [
        artifact
        for artifact in handlers.workspace_artifacts_from_validation(validation, session_id)
        if not any(
            contains_private_value(value, private_values)
            for value in artifact.values()
        )
    ]
    return notices, artifacts


def resolve_secret_environment(
    command: str,
    session_id: str,
    *,
    display_command: str = "",
    team_id: str = "",
    is_help_invocation_fn: Callable[[str], bool] = is_help_invocation,
    required_secrets_for_command_fn: Callable[[str], list[dict[str, Any]]] = required_secrets_for_command,
    get_secret_value_for_env_fn: Callable[..., str | None] = get_secret_value_for_env,
    command_root_fn: Callable[[str], str | None] = command_root,
) -> tuple[dict[str, str], list[str]]:
    safe_command = str(display_command or command)
    if is_help_invocation_fn(command):
        return {}, []
    declarations = required_secrets_for_command_fn(command)
    if not declarations:
        return {}, []
    if not session_id:
        raise RunPreparationError(
            "A valid session is required before commands can use encrypted secrets.",
            status_code=401,
        )

    secret_scope_id = team_id or session_id
    env_overrides: dict[str, str] = {}
    missing_required: list[str] = []
    missing_optional: list[str] = []
    missing_labels: dict[str, str] = {}
    for declaration in declarations:
        env_name = str(declaration.get("env") or "").strip().upper()
        if not env_name:
            continue
        inject_env_name = str(declaration.get("inject_env") or env_name).strip().upper()
        if not inject_env_name:
            continue
        raw_fallback_envs = declaration.get("fallback_envs")
        fallback_envs = [
            str(item or "").strip().upper()
            for item in (raw_fallback_envs if isinstance(raw_fallback_envs, list) else [])
            if str(item or "").strip()
        ]
        lookup_env_names = [env_name, *[item for item in fallback_envs if item != env_name]]
        try:
            value = None
            for lookup_env_name in lookup_env_names:
                value = get_secret_value_for_env_fn(
                    secret_scope_id,
                    lookup_env_name,
                    audit_session_id=session_id,
                    team_id=team_id,
                )
                if value is not None:
                    break
        except (InvalidSecretName, MasterKeyError, SecretDecryptError) as exc:
            log.error("SECRET_ENV_RESOLVE_FAILED", exc_info=True, extra={
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "command_root": command_root_fn(safe_command) or "",
                "secret_name": env_name,
                "lookup_env_names": lookup_env_names,
                "error_type": type(exc).__name__,
            })
            raise RunPreparationError("Secrets vault unavailable. Check server logs.", status_code=503) from exc
        if value is None:
            missing_label = " or ".join(lookup_env_names)
            if bool(declaration.get("optional", False)):
                missing_optional.append(env_name)
            else:
                missing_required.append(env_name)
                missing_labels[env_name] = missing_label
            continue
        env_overrides[inject_env_name] = value

    if missing_required:
        if len(missing_required) == 1:
            subject = f"secret {missing_labels.get(missing_required[0], missing_required[0])}"
            setup_hint = "Set it via \"secret set NAME\" or the Options > Secrets panel."
            if team_id:
                setup_hint = "Set it in Options > Secrets while the team scope is active."
        else:
            subject = "secrets " + ", ".join(
                missing_labels.get(env_name, env_name)
                for env_name in missing_required
            )
            setup_hint = "Set each one via \"secret set NAME\" or the Options > Secrets panel."
            if team_id:
                setup_hint = "Set them in Options > Secrets while the team scope is active."
        raise RunPreparationError(
            f"Run requires {subject} which is not set. " + setup_hint,
            status_code=403,
        )
    for env_name in missing_optional:
        log.warning("SECRET_OPTIONAL_MISSING", extra={
            "session": get_log_session_id(session_id),
            "secret_name": env_name,
            "command_root": command_root_fn(safe_command) or "",
        })
    return env_overrides, sorted(env_overrides)
