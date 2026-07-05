"""Workspace flag and path helpers for command registry validation."""

from __future__ import annotations

import os
import shlex
from collections.abc import Callable

import config as app_config
from services.commands import registry_targets
from services.commands.registry_validation import split_command_argv
from services.teams.scope import OwnerContext, owner_context_for_scope
from services.workspace.files import (
    ensure_owner_workspace,
    InvalidWorkspacePath,
    WorkspaceDisabled,
    WorkspaceFileNotFound,
    WorkspaceQuotaExceeded,
    prepare_owner_workspace_target_for_command,
    prepare_workspace_directory_for_command,
    read_owner_workspace_text_file,
    resolve_owner_workspace_path,
)

WGET_DIRECTORY_PREFIX_FLAGS = ("-P", "--directory-prefix")


def workspace_flag_specs_by_root(load_commands_registry: Callable[[], dict]) -> dict[str, list[dict[str, object]]]:
    registry = load_commands_registry()
    specs: dict[str, list[dict[str, object]]] = {}
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if root:
            specs[root] = [
                item for item in entry.get("workspace_flags", []) or []
                if isinstance(item, dict)
            ]
    return specs


def runtime_adaptations_by_root(load_commands_registry: Callable[[], dict]) -> dict[str, dict[str, object]]:
    registry = load_commands_registry()
    adaptations: dict[str, dict[str, object]] = {}
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        runtime_adaptations = entry.get("runtime_adaptations")
        if root and isinstance(runtime_adaptations, dict) and runtime_adaptations:
            adaptations[root] = runtime_adaptations
    return adaptations


def workspace_flag_applies_to_command(spec: dict[str, object], tokens: list[str]) -> bool:
    subcommands = spec.get("subcommands")
    if not subcommands:
        return True
    if not isinstance(subcommands, list) or len(tokens) < 2:
        return False
    command_sub = tokens[1].strip().lower()
    return command_sub in {str(item).strip().lower() for item in subcommands}


def managed_workspace_directory_applies(spec: dict[str, object], tokens: list[str]) -> bool:
    if not spec or not tokens:
        return False
    raw_subcommands = spec.get("subcommands")
    subcommands = raw_subcommands if isinstance(raw_subcommands, list) else []
    if subcommands:
        if len(tokens) < 2:
            return False
        command_sub = tokens[1].strip().lower()
        if command_sub not in {str(item).strip().lower() for item in subcommands}:
            return False
    raw_skip_if_any = spec.get("skip_if_any")
    skip_if_any = {
        str(item) for item in raw_skip_if_any
        if str(item)
    } if isinstance(raw_skip_if_any, list) else set()
    if skip_if_any and any(token in skip_if_any for token in tokens[1:]):
        return False
    return True


def managed_workspace_directory_for_root(
    root: str,
    *,
    runtime_adaptations_by_root: Callable[[], dict[str, dict[str, object]]],
) -> dict[str, object]:
    adaptations = runtime_adaptations_by_root().get(root.lower(), {})
    managed = adaptations.get("managed_workspace_directory") if isinstance(adaptations, dict) else {}
    return managed if isinstance(managed, dict) else {}


def workspace_flag_matches_token(token: str, spec: dict[str, object]) -> bool:
    flag = str(spec.get("flag") or "")
    if not flag:
        return False
    if token == flag:
        return True
    value_kind = str(spec.get("value") or "required")
    if value_kind not in {"attached", "separate_or_attached"}:
        return False
    if flag.startswith("--"):
        return token.startswith(f"{flag}=")
    return token.startswith(flag) and token != flag


def wget_has_directory_prefix(tokens: list[str]) -> bool:
    for token in tokens[1:]:
        for flag in WGET_DIRECTORY_PREFIX_FLAGS:
            if token == flag:
                return True
            if flag == "-P" and token.startswith("-P") and token != "-P":
                return True
            if flag.startswith("--") and token.startswith(f"{flag}="):
                return True
    return False


def workspace_flag_value(tokens: list[str], index: int, spec: dict[str, object]) -> tuple[str | None, int | None, str | None]:
    flag = str(spec.get("flag") or "")
    value_kind = str(spec.get("value") or "required")
    token = tokens[index]
    if token == flag:
        label = "session directory name" if str(spec.get("kind") or "") == "directory" else "session file name"
        if index + 1 >= len(tokens) or str(tokens[index + 1]).startswith("-"):
            return None, None, f"{flag} requires a {label}"
        return tokens[index + 1], index + 1, None
    if value_kind in {"attached", "separate_or_attached"}:
        if flag.startswith("--") and token.startswith(f"{flag}="):
            return token[len(flag) + 1:], index, None
        if not flag.startswith("--") and token.startswith(flag) and token != flag:
            return token[len(flag):], index, None
    return None, None, None


def normalize_workspace_command_path(value: str, cwd: str = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        raise InvalidWorkspacePath("file name is required")
    if "\x00" in raw or "\\" in raw:
        raise InvalidWorkspacePath("file name contains unsupported characters")
    if os.path.isabs(raw):
        return raw

    base_parts = [part for part in str(cwd or "").split("/") if part]
    for raw_part in raw.split("/"):
        part = raw_part.strip()
        if not part or part == ".":
            continue
        if part == "..":
            if not base_parts:
                raise InvalidWorkspacePath("file path escapes the workspace directory")
            base_parts.pop()
            continue
        base_parts.append(part)
    normalized = "/".join(base_parts)
    if not normalized:
        raise InvalidWorkspacePath("file name is required")
    return normalized


def invalid_workspace_file_path_reason(value: str, detail: str = "") -> str:
    display_value = str(value or "").strip() or "<empty>"
    detail = str(detail or "").strip()
    if detail:
        return f"Invalid file path: {display_value} ({detail})"
    return f"Invalid file path: {display_value}"


def absolute_workspace_flag_path_error(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "file name is required"
    if "\x00" in raw or "\\" in raw:
        return "file name contains unsupported characters"
    if os.path.isabs(raw):
        parts = [part for part in raw.split("/") if part]
        if any(part == ".." for part in parts):
            return "file path escapes the workspace directory"
    return ""


def workspace_owner_context(session_id: str, owner_context: OwnerContext | None = None) -> OwnerContext:
    if owner_context is not None:
        return owner_context
    return owner_context_for_scope(session_id)


def workspace_flag_absolute_passthrough(value: str, mode: str) -> bool:
    raw = str(value or "").strip()
    if not os.path.isabs(raw):
        return False
    if raw == "/dev/null" and mode in {"write", "read_write"}:
        return True
    return mode in {"read", "read_write"} and raw.startswith("/usr/share/wordlists/")


def wget_default_directory_prefix(
    session_id: str,
    cfg: dict | None,
    workspace_cwd: str,
    *,
    owner_context: OwnerContext | None = None,
) -> tuple[str, str]:
    active_cfg = cfg or app_config.CFG
    if not session_id:
        return "", ""
    owner = workspace_owner_context(session_id, owner_context)
    if not str(workspace_cwd or "").strip():
        try:
            resolved = ensure_owner_workspace(owner, active_cfg).resolve(strict=True)
            prepare_workspace_directory_for_command(resolved, mode="write")
        except (InvalidWorkspacePath, WorkspaceDisabled, WorkspaceFileNotFound) as exc:
            return "", str(exc)
        except OSError as exc:
            return "", str(exc)
        return str(resolved), ""
    try:
        workspace_value = normalize_workspace_command_path(workspace_cwd)
        resolved = resolve_owner_workspace_path(owner, workspace_value, active_cfg, ensure_parent=True)
        prepare_workspace_directory_for_command(resolved, mode="write")
    except (InvalidWorkspacePath, WorkspaceDisabled, WorkspaceFileNotFound) as exc:
        return "", str(exc)
    except OSError as exc:
        return "", str(exc)
    return str(resolved), ""


def workspace_read_file_restriction_reason(
    command: str,
    session_id: str,
    cfg: dict | None = None,
    *,
    workspace_cwd: str = "",
    owner_context: OwnerContext | None = None,
    networks,
    load_commands_registry: Callable[[], dict],
    load_autocomplete_context: Callable[[dict | None], dict],
) -> str:
    if not networks or not session_id:
        return ""
    owner = workspace_owner_context(session_id, owner_context)
    tokens = split_command_argv(command)
    if not tokens:
        return ""
    specs = [
        spec for spec in workspace_flag_specs_by_root(load_commands_registry).get(tokens[0].lower(), [])
        if workspace_flag_applies_to_command(spec, tokens)
        and spec.get("mode") in {"read", "read_write"}
        and spec.get("kind") != "directory"
    ]
    if not specs:
        return ""
    autocomplete_spec, _ = registry_targets.autocomplete_spec_for_tokens(
        tokens,
        cfg=cfg,
        load_autocomplete_context=load_autocomplete_context,
    )
    flag_value_types = registry_targets.autocomplete_value_flag_types(autocomplete_spec)
    index = 1
    while index < len(tokens):
        matched_spec = next((spec for spec in specs if workspace_flag_matches_token(tokens[index], spec)), None)
        if not matched_spec:
            index += 1
            continue
        flag = str(matched_spec.get("flag") or "")
        value_type = flag_value_types.get(flag, "")
        user_value, value_index, _ = workspace_flag_value(tokens, index, matched_spec)
        if (
            user_value
            and value_index is not None
            and not os.path.isabs(user_value)
            and registry_targets.value_type_is_restrictable(value_type)
        ):
            try:
                normalized_value = normalize_workspace_command_path(user_value, workspace_cwd)
                text = read_owner_workspace_text_file(owner, normalized_value, cfg)
            except (InvalidWorkspacePath, WorkspaceDisabled, WorkspaceFileNotFound, OSError):
                index = (value_index + 1) if value_index is not None else index + 1
                continue
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                blocked = registry_targets.restricted_value_match(line, networks)
                if blocked:
                    return f"Session file {normalized_value} contains restricted IP/CIDR value: {blocked}"
        index = (value_index + 1) if value_index is not None else index + 1
    return ""


def rewrite_workspace_file_flags(
    command: str,
    session_id: str,
    cfg: dict | None = None,
    *,
    workspace_cwd: str = "",
    owner_context: OwnerContext | None = None,
    load_commands_registry: Callable[[], dict],
    runtime_adaptations_by_root: Callable[[], dict[str, dict[str, object]]],
) -> tuple[str, set[str], list[str], list[str], list[str], str]:
    active_cfg = cfg or app_config.CFG
    tokens = split_command_argv(command)
    if not tokens:
        return command, set(), [], [], [], ""

    specs = [
        spec for spec in workspace_flag_specs_by_root(load_commands_registry).get(tokens[0].lower(), [])
        if workspace_flag_applies_to_command(spec, tokens)
    ]
    if not specs:
        return command, set(), [], [], [], ""

    if not active_cfg.get("workspace_enabled"):
        index = 1
        while index < len(tokens):
            matched_spec = next((spec for spec in specs if workspace_flag_matches_token(tokens[index], spec)), None)
            if not matched_spec:
                index += 1
                continue
            user_value, value_index, error = workspace_flag_value(tokens, index, matched_spec)
            if error:
                return command, set(), [], [], [], error
            if user_value and value_index is not None and not os.path.isabs(user_value):
                return (
                    command,
                    set(),
                    [],
                    [],
                    [],
                    "Files are disabled on this instance; session file flags are not available.",
                )
            index = (value_index + 1) if value_index is not None else index + 1
        return command, set(), [], [], [], ""

    owner = workspace_owner_context(session_id, owner_context)
    root = tokens[0].lower()
    managed_dir = managed_workspace_directory_for_root(root, runtime_adaptations_by_root=runtime_adaptations_by_root)
    managed_dir_flag = str(managed_dir.get("flag") or "")
    managed_dir_name = str(managed_dir.get("directory") or "")
    managed_dir_specs = [spec for spec in specs if spec.get("flag") == managed_dir_flag]
    has_managed_dir = any(
        workspace_flag_matches_token(token, spec)
        for token in tokens[1:]
        for spec in managed_dir_specs
    )
    managed_dir_applies = (
        bool(managed_dir_flag and managed_dir_name and managed_dir_specs)
        and managed_workspace_directory_applies(managed_dir, tokens)
    )
    if managed_dir_applies and not has_managed_dir:
        tokens = tokens + [managed_dir_flag, managed_dir_name]
    elif managed_dir_applies and has_managed_dir and managed_dir.get("reject_alternate", True):
        for index, token in enumerate(tokens):
            matched_spec = next((spec for spec in managed_dir_specs if workspace_flag_matches_token(token, spec)), None)
            if not matched_spec:
                continue
            user_value, _, error = workspace_flag_value(tokens, index, matched_spec)
            if error:
                return command, set(), [], [], [], error
            normalized_value = (user_value or "").rstrip(os.sep)
            is_managed_value = (
                normalized_value == managed_dir_name
                or (
                    os.path.isabs(normalized_value)
                    and normalized_value.endswith(f"{os.sep}{managed_dir_name}")
                )
            )
            if normalized_value and not is_managed_value:
                reject_message = str(managed_dir.get("reject_message") or "").strip()
                return (
                    command,
                    set(),
                    [],
                    [],
                    [],
                    reject_message or f"{tokens[0]} uses the managed {managed_dir_name} workspace directory.",
                )
            break

    rewritten_tokens = list(tokens)
    exempt_flags: set[str] = set()
    reads: list[str] = []
    writes: list[str] = []
    exec_paths: list[str] = []
    index = 1
    while index < len(tokens):
        matched_spec = next((spec for spec in specs if workspace_flag_matches_token(tokens[index], spec)), None)
        if not matched_spec:
            index += 1
            continue

        flag = str(matched_spec.get("flag") or "")
        user_value, value_index, error = workspace_flag_value(tokens, index, matched_spec)
        if error:
            return command, set(), [], [], [], error
        if not user_value or value_index is None:
            index += 1
            continue

        mode = str(matched_spec.get("mode") or "")
        kind = str(matched_spec.get("kind") or "file")
        workspace_value = user_value
        if os.path.isabs(user_value):
            path_error = absolute_workspace_flag_path_error(user_value)
            if path_error:
                return command, set(), [], [], [], invalid_workspace_file_path_reason(user_value, path_error)
            if workspace_flag_absolute_passthrough(user_value, mode):
                index = value_index + 1
                continue
            workspace_value = user_value.lstrip("/")
        if not (
            managed_dir_applies
            and flag == managed_dir_flag
            and workspace_value.rstrip(os.sep) == managed_dir_name
        ):
            try:
                workspace_value = normalize_workspace_command_path(workspace_value, workspace_cwd)
            except InvalidWorkspacePath as exc:
                return command, set(), [], [], [], invalid_workspace_file_path_reason(user_value, str(exc))

        try:
            resolved = prepare_owner_workspace_target_for_command(
                owner,
                workspace_value,
                active_cfg,
                mode=mode,
                kind=kind,
            )
        except InvalidWorkspacePath as exc:
            return command, set(), [], [], [], invalid_workspace_file_path_reason(user_value, str(exc))
        except (WorkspaceDisabled, WorkspaceFileNotFound, WorkspaceQuotaExceeded) as exc:
            return command, set(), [], [], [], str(exc)

        resolved_value = str(resolved)
        if value_index == index and tokens[index] != flag:
            rewritten_tokens[index] = f"{flag}={resolved_value}" if flag.startswith("--") else f"{flag}{resolved_value}"
        else:
            rewritten_tokens[value_index] = resolved_value

        exempt_flags.add(flag)
        exec_paths.append(resolved_value)
        if kind != "directory" and mode in {"read", "read_write"}:
            reads.append(workspace_value)
        if mode in {"write", "read_write"}:
            writes.append(workspace_value)
        index = value_index + 1

    if root == "wget" and active_cfg.get("workspace_enabled") and not wget_has_directory_prefix(rewritten_tokens):
        default_prefix, default_prefix_error = wget_default_directory_prefix(
            session_id,
            active_cfg,
            workspace_cwd,
            owner_context=owner_context,
        )
        if default_prefix_error:
            return command, set(), [], [], [], default_prefix_error
        if default_prefix:
            rewritten_tokens.extend(["-P", default_prefix])
            exec_paths.append(default_prefix)

    return shlex.join(rewritten_tokens), exempt_flags, reads, writes, exec_paths, ""
