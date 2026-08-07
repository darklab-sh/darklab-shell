# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validated metadata for run-scoped workspace artifacts."""

from __future__ import annotations

from services.commands.registry import AMASS_DEFAULT_WORKSPACE_DIR, CommandValidationResult
from services.commands.registry_validation import split_command_argv

APP_MANAGED_WORKSPACE_ARTIFACT_PREFIXES = (
    AMASS_DEFAULT_WORKSPACE_DIR.strip("/"),
)


def _nmap_xml_exec_paths(validation: CommandValidationResult) -> list[str]:
    display_tokens = split_command_argv(validation.display_command)
    if not display_tokens or display_tokens[0].lower() != "nmap":
        return []

    tokens = split_command_argv(validation.exec_command)
    paths = []
    index = 1
    while index < len(tokens):
        argument = tokens[index]
        if argument == "-oX":
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
                paths.append(tokens[index + 1])
                index += 2
                continue
        elif argument.startswith("-oX"):
            value = argument[len("-oX"):]
            if value and not value.startswith(("-", "=")):
                paths.append(value)
        index += 1
    return paths


def _matching_workspace_write(resolved_path: str, writes: list[str]) -> str:
    normalized_resolved = str(resolved_path or "").replace("\\", "/").rstrip("/")
    normalized_writes = [
        (path, str(path).replace("\\", "/").strip("/"))
        for path in writes
    ]
    matches = [
        path
        for path, normalized_path in normalized_writes
        if normalized_path
        and (
            normalized_resolved == normalized_path
            or normalized_resolved.endswith(f"/{normalized_path}")
        )
    ]
    return matches[0] if len(matches) == 1 else ""


def workspace_artifact_metadata(validation: CommandValidationResult) -> dict[str, dict[str, str]]:
    """Return metadata only for unambiguous, validated Nmap XML writes."""
    if not validation.allowed:
        return {}
    writes = list(dict.fromkeys(validation.workspace_writes))
    metadata = {}
    for resolved_path in _nmap_xml_exec_paths(validation):
        workspace_path = _matching_workspace_write(resolved_path, writes)
        if workspace_path:
            metadata[workspace_path] = {
                "structured_output": "nmap_xml",
                "source_flag": "-oX",
            }
    return metadata


def is_app_managed_workspace_artifact_path(workspace_path: str) -> bool:
    normalized = str(workspace_path or "").strip().replace("\\", "/").strip("/")
    if not normalized:
        return False
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in APP_MANAGED_WORKSPACE_ARTIFACT_PREFIXES
        if prefix
    )
