# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validated metadata for run-scoped workspace artifacts."""

from __future__ import annotations

from services.commands.registry import AMASS_DEFAULT_WORKSPACE_DIR, CommandValidationResult
from services.commands.registry_validation import split_command_argv
from services.runs.httpx_workspace_artifact_metadata import httpx_screenshot_artifact_metadata

APP_MANAGED_WORKSPACE_ARTIFACT_PREFIXES = (AMASS_DEFAULT_WORKSPACE_DIR.strip("/"),)
NMAP_XML_SOURCE_FLAG = "-oX"
NMAP_XML_STRUCTURED_OUTPUT = "nmap_xml"


def _nmap_xml_exec_paths(validation: CommandValidationResult) -> list[str]:
    display_tokens = split_command_argv(validation.display_command)
    if not display_tokens or display_tokens[0].lower() != "nmap":
        return []

    tokens = split_command_argv(validation.exec_command)
    paths = []
    index = 1
    while index < len(tokens):
        argument = tokens[index]
        if argument == NMAP_XML_SOURCE_FLAG:
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
                paths.append(tokens[index + 1])
                index += 2
                continue
        elif argument.startswith(NMAP_XML_SOURCE_FLAG):
            value = argument[len(NMAP_XML_SOURCE_FLAG):]
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
    """Return metadata only for unambiguous validated structured outputs."""
    if not validation.allowed:
        return {}
    writes = list(dict.fromkeys(validation.workspace_writes))
    metadata: dict[str, dict[str, str]] = {}
    resolved_paths = _nmap_xml_exec_paths(validation)
    if len(resolved_paths) == 1:
        workspace_path = _matching_workspace_write(resolved_paths[0], writes)
        if workspace_path:
            metadata[workspace_path] = {
                "structured_output": NMAP_XML_STRUCTURED_OUTPUT,
                "source_flag": NMAP_XML_SOURCE_FLAG,
            }
    metadata.update(httpx_screenshot_artifact_metadata(validation, writes))
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
