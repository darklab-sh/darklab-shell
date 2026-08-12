# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment-specific app-owned helper commands."""

from __future__ import annotations

from services.assessments.historical_urls import (
    normalize_domain_scoped_historical_urls,
    normalize_scope_domain,
)
from services.commands.builtin_registry import (
    BuiltinCommandSpec,
    BuiltinExecutionContext,
    build_builtin_command_spec,
)
from services.commands.builtins_format import output_line
from services.commands.registry_validation import split_command_argv
from services.teams.capabilities import Capability, role_can
from services.workspace.files import read_owner_workspace_text_file, write_owner_workspace_text_file
from services.workspace.models import (
    InvalidWorkspacePath,
    WorkspaceBinaryFile,
    WorkspaceDisabled,
    WorkspaceFileNotFound,
    WorkspacePathNotFound,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
)


_URLSCOPE_USAGE = "Usage: urlscope <domain> <source-file> <destination-file>"


def _urlscope_error(exc: Exception) -> str:
    if isinstance(exc, WorkspaceDisabled):
        return "Files storage is disabled on this instance"
    if isinstance(exc, (WorkspaceFileNotFound, WorkspacePathNotFound)):
        return "source file was not found"
    if isinstance(exc, WorkspaceBinaryFile):
        return "source file must be UTF-8 text"
    if isinstance(exc, WorkspacePermissionDenied):
        return "workspace file access was denied"
    if isinstance(exc, WorkspaceQuotaExceeded):
        return "destination exceeds the Files limit"
    if isinstance(exc, InvalidWorkspacePath):
        return str(exc)
    raise exc


def run_builtin_urlscope(
    command: str,
    context: BuiltinExecutionContext,
) -> tuple[list[dict[str, object]], int]:
    """Write normalized, deduplicated in-domain URLs to one bounded Files entry."""
    parts = split_command_argv(command)
    if len(parts) != 4:
        return [output_line(_URLSCOPE_USAGE)], 1
    domain = normalize_scope_domain(parts[1])
    if not domain:
        return [output_line("urlscope: domain is invalid")], 1
    owner = context.owner_context
    if owner.is_team and not role_can(context.team_role, Capability.MANAGE_WORKSPACE_FILES):
        return [output_line("urlscope: your team role can view Files but can't change them")], 1
    try:
        source = read_owner_workspace_text_file(owner, parts[2], context.effective_cfg)
        rows = normalize_domain_scoped_historical_urls(source.splitlines(), domain)
        payload = "".join(f"{row['url']}\n" for row in rows)
        written = write_owner_workspace_text_file(owner, parts[3], payload, context.effective_cfg)
    except Exception as exc:
        return [output_line(f"urlscope: {_urlscope_error(exc)}")], 1
    return [
        output_line(
            f"urlscope: wrote {len(rows)} scoped URL{'s' if len(rows) != 1 else ''} to {written['path']}",
            "builtin-success",
        )
    ], 0


_URLSCOPE_AUTOCOMPLETE = {
    "root": "urlscope",
    "description": "built-in: normalize and scope a URL file before active web checks",
    "feature_required": "workspace",
    "autocomplete": {
        "argument_limit": 3,
        "arguments": [
            {
                "value": "<domain>",
                "hint_only": True,
                "value_type": "domain",
                "description": "Approved root domain",
            },
            {
                "value": "<source-file>",
                "hint_only": True,
                "value_type": "workspace_path",
                "description": "Files entry containing candidate URLs",
            },
            {
                "value": "<destination-file>",
                "hint_only": True,
                "value_type": "workspace_path",
                "description": "Files entry for normalized in-scope URLs",
            },
        ],
    },
}


def builtin_command_specs() -> tuple[BuiltinCommandSpec, ...]:
    return (
        build_builtin_command_spec(
            _URLSCOPE_AUTOCOMPLETE,
            handler_key="urlscope",
            handler=run_builtin_urlscope,
            name="urlscope <domain> <source-file> <destination-file>",
            description="Normalize, deduplicate, and scope URLs before active web checks.",
        ),
    )
