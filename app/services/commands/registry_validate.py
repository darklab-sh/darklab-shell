"""High-level command validation orchestration for the command registry."""

from typing import Any, Mapping

import config as app_config
from services.commands.postfilters import parse_synthetic_postfilter
from services.commands.registry_validation import (
    LOOPBACK_RE,
    PATH_DATA_RE,
    PATH_TMP_RE,
    SHELL_CHAIN_RE,
    is_allowed_by_policy,
    is_denied,
    nmap_raw_scan_restriction_reason,
    split_command_argv,
)
from services.teams.scope import OwnerContext


def validate_command(
    command: str,
    *,
    result_cls: type,
    load_command_policy,
    load_allow_grouping_flags,
    restricted_inline_input_reason,
    reserved_interactive_deny_matches,
    trufflehog_git_uri_restriction_reason,
    puredns_resolver_restriction_reason,
    rewrite_workspace_file_flags,
    workspace_read_file_restriction_reason,
    apply_workspace_runtime_environment,
    session_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    workspace_cwd: str = "",
    extra_allowed_prefixes: list[str] | None = None,
    owner_context: OwnerContext | None = None,
) -> Any:
    """Validate a command and return the caller's validation result type."""
    cfg = cfg or app_config.CFG
    allowed, denied = load_command_policy()
    allow_grouping = load_allow_grouping_flags()
    if allowed is None:
        return result_cls(True, display_command=command, exec_command=command)
    if extra_allowed_prefixes:
        allowed = [*allowed, *extra_allowed_prefixes]

    synthetic_postfilter, postfilter_error = parse_synthetic_postfilter(command)
    if postfilter_error:
        return result_cls(False, postfilter_error, display_command=command, exec_command=command)
    command_to_validate = synthetic_postfilter["base_command"] if synthetic_postfilter else command

    if not synthetic_postfilter and SHELL_CHAIN_RE.search(command):
        return result_cls(
            False,
            "Shell operators (&&, |, ;, >, etc.) are not permitted.",
            display_command=command,
            exec_command=command_to_validate,
        )

    if PATH_DATA_RE.search(command_to_validate):
        return result_cls(
            False, "Access to /data is not permitted.",
            display_command=command, exec_command=command_to_validate,
        )
    if PATH_TMP_RE.search(command_to_validate):
        return result_cls(
            False, "Access to /tmp is not permitted.",
            display_command=command, exec_command=command_to_validate,
        )
    if LOOPBACK_RE.search(command_to_validate):
        return result_cls(
            False, "Connections to the local host are not permitted.",
            display_command=command, exec_command=command_to_validate,
        )

    nmap_raw_reason = nmap_raw_scan_restriction_reason(command_to_validate)
    if nmap_raw_reason:
        return result_cls(
            False,
            nmap_raw_reason,
            display_command=command,
            exec_command=command_to_validate,
        )

    restricted_reason = restricted_inline_input_reason(command_to_validate, cfg)
    if restricted_reason:
        return result_cls(
            False,
            restricted_reason,
            display_command=command,
            exec_command=command_to_validate,
        )

    if denied and reserved_interactive_deny_matches(command_to_validate.strip(), denied):
        return result_cls(
            False,
            f"Command not allowed: '{command.strip()}'",
            display_command=command,
            exec_command=command_to_validate,
        )

    trufflehog_git_reason = trufflehog_git_uri_restriction_reason(command_to_validate)
    if trufflehog_git_reason:
        return result_cls(
            False,
            trufflehog_git_reason,
            display_command=command,
            exec_command=command_to_validate,
        )

    puredns_resolver_reason = puredns_resolver_restriction_reason(command_to_validate)
    if puredns_resolver_reason:
        return result_cls(
            False,
            puredns_resolver_reason,
            display_command=command,
            exec_command=command_to_validate,
        )

    exec_command, exempt_flags, reads, writes, exec_paths, workspace_error = rewrite_workspace_file_flags(
        command_to_validate,
        session_id,
        cfg,
        workspace_cwd=workspace_cwd,
        owner_context=owner_context,
    )
    if workspace_error:
        return result_cls(
            False,
            workspace_error,
            display_command=command,
            exec_command=command_to_validate,
        )

    restricted_file_reason = workspace_read_file_restriction_reason(
        command_to_validate,
        session_id,
        cfg,
        workspace_cwd=workspace_cwd,
        owner_context=owner_context,
    )
    if restricted_file_reason:
        return result_cls(
            False,
            restricted_file_reason,
            display_command=command,
            exec_command=command_to_validate,
        )

    command_tokens = split_command_argv(command_to_validate.strip())

    if denied and is_denied(command_to_validate.strip(), denied, exempt_flags=exempt_flags):
        return result_cls(
            False,
            f"Command not allowed: '{command.strip()}'",
            display_command=command,
            exec_command=command_to_validate,
        )

    if not is_allowed_by_policy(command_tokens, allowed, allow_grouping):
        return result_cls(
            False,
            f"Command not allowed: '{command.strip()}'",
            display_command=command,
            exec_command=command_to_validate,
        )

    exec_command = apply_workspace_runtime_environment(exec_command)

    return result_cls(
        True,
        display_command=command,
        exec_command=exec_command,
        workspace_reads=reads,
        workspace_writes=writes,
        workspace_exec_paths=exec_paths,
    )
