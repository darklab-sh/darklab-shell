"""Runtime command adaptation helpers for command registry entries."""

from __future__ import annotations

import os
import re
import shlex
from typing import Any, Callable, Mapping

from services.commands.registry_validation import split_command_argv
from services.teams.scope import OwnerContext, owner_context_for_scope
from services.workspace.files import (
    ensure_owner_workspace,
    InvalidWorkspacePath,
    WorkspaceDisabled,
)


def runtime_injection_blocked(tokens: list[str], inject: dict[str, object]) -> bool:
    raw_unless_any = inject.get("unless_any")
    unless_any = [
        str(item) for item in raw_unless_any
        if str(item)
    ] if isinstance(raw_unless_any, list) else []
    for blocker in unless_any:
        if any(
            token == blocker or (blocker.startswith("--") and token.startswith(f"{blocker}="))
            for token in tokens[1:]
        ):
            return True
    raw_regexes = inject.get("unless_any_regex")
    regexes = raw_regexes if isinstance(raw_regexes, list) else []
    for raw_pattern in regexes:
        pattern = str(raw_pattern)
        try:
            if any(re.search(pattern, token) for token in tokens[1:]):
                return True
        except re.error:
            continue
    return False


def _workspace_owner_context(session_id: str, owner_context: OwnerContext | None = None) -> OwnerContext:
    if owner_context is not None:
        return owner_context
    return owner_context_for_scope(session_id)


def runtime_injection_token(
    token: str,
    *,
    session_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    owner_context: OwnerContext | None = None,
) -> str:
    if "{session_workspace}" not in token:
        return token
    if not session_id:
        return ""
    try:
        workspace_dir = ensure_owner_workspace(_workspace_owner_context(session_id, owner_context), cfg)
    except (InvalidWorkspacePath, WorkspaceDisabled, OSError):
        return ""
    return token.replace("{session_workspace}", str(workspace_dir))


def runtime_injection_flags(
    inject: dict[str, object],
    *,
    session_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    owner_context: OwnerContext | None = None,
) -> list[str]:
    raw_flags = inject.get("flags")
    if not isinstance(raw_flags, list):
        return []
    flags = [
        runtime_injection_token(str(flag), session_id=session_id, cfg=cfg, owner_context=owner_context).strip()
        for flag in raw_flags
    ]
    return [flag for flag in flags if flag]


def apply_runtime_inject_flags(
    command: str,
    *,
    runtime_adaptations_by_root: Callable[[], dict[str, dict[str, object]]],
    session_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    owner_context: OwnerContext | None = None,
) -> tuple[str, str | None]:
    tokens = split_command_argv(command)
    if not tokens:
        return command.strip(), None
    adaptations = runtime_adaptations_by_root().get(tokens[0].lower(), {})
    inject_flags = adaptations.get("inject_flags") if isinstance(adaptations, dict) else []
    if not isinstance(inject_flags, list) or not inject_flags:
        return command.strip(), None

    active_cfg = cfg or {}
    rewritten = list(tokens)
    notices: list[str] = []
    changed = False
    for inject in inject_flags:
        if not isinstance(inject, dict):
            continue
        if inject.get("requires_workspace") and not (session_id and active_cfg.get("workspace_enabled")):
            continue
        flags = runtime_injection_flags(inject, session_id=session_id, cfg=cfg, owner_context=owner_context)
        if not flags or runtime_injection_blocked(rewritten, inject):
            continue
        position = str(inject.get("position") or "prepend").strip().lower()
        if position == "command_prefix":
            rewritten = flags + rewritten
        elif position == "append":
            rewritten.extend(flags)
        else:
            rewritten[1:1] = flags
        notice = str(inject.get("notice") or "").strip()
        if notice:
            notices.append(notice)
        changed = True
    return (shlex.join(rewritten), notices[0] if notices else None) if changed else (command.strip(), None)


def runtime_environment_value(template: str, tokens: list[str], env_spec: dict[str, object]) -> str:
    managed_flag = str(env_spec.get("managed_directory_flag") or "").strip()
    managed_directory = ""
    managed_workspace_parent = ""
    if managed_flag:
        for index, token in enumerate(tokens[:-1]):
            if token != managed_flag:
                continue
            directory = tokens[index + 1].rstrip(os.sep)
            if os.path.isabs(directory):
                managed_directory = directory
                managed_workspace_parent = os.path.dirname(directory)
            break
    return (
        template
        .replace("{managed_workspace_directory}", managed_directory)
        .replace("{managed_workspace_parent}", managed_workspace_parent)
    )


def apply_workspace_runtime_environment(
    command: str,
    *,
    runtime_adaptations_by_root: Callable[[], dict[str, dict[str, object]]],
) -> str:
    tokens = split_command_argv(command)
    if not tokens:
        return command

    adaptations = runtime_adaptations_by_root().get(tokens[0].lower(), {})
    env_specs = adaptations.get("environment") if isinstance(adaptations, dict) else []
    if not isinstance(env_specs, list) or not env_specs:
        return command

    env_tokens = []
    for env_spec in env_specs:
        if not isinstance(env_spec, dict):
            continue
        name = str(env_spec.get("name") or "").strip()
        template = str(env_spec.get("value") or "").strip()
        if not name or not template:
            continue
        value = runtime_environment_value(template, tokens, env_spec)
        if not value:
            continue
        env_tokens.append(f"{name}={value}")

    return shlex.join(["env", *env_tokens, *tokens]) if env_tokens else command
