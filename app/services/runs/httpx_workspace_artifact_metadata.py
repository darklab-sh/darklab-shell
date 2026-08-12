# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validated HTTPx screenshot-directory artifact metadata."""

from __future__ import annotations

from services.commands.registry import CommandValidationResult
from services.commands.registry_validation import split_command_argv


HTTPX_SCREENSHOT_DIRECTORY = "httpx_screenshot_directory"
HTTPX_SCREENSHOT_DIRECTORY_FLAGS = ("-srd", "-store-response-dir")


def httpx_screenshot_artifact_metadata(
    validation: CommandValidationResult,
    writes: list[str],
) -> dict[str, dict[str, str]]:
    display_tokens = split_command_argv(validation.display_command)
    if (
        not display_tokens
        or display_tokens[0].lower() != "httpx"
        or not {"-ss", "-screenshot"}.intersection(display_tokens)
    ):
        return {}
    tokens = split_command_argv(validation.exec_command)
    paths = [
        (argument, tokens[index + 1])
        for index, argument in enumerate(tokens[:-1])
        if argument in HTTPX_SCREENSHOT_DIRECTORY_FLAGS and not tokens[index + 1].startswith("-")
    ]
    if len(paths) != 1:
        return {}
    source_flag, resolved_path = paths[0]
    workspace_path = _matching_workspace_write(resolved_path, writes)
    if not workspace_path:
        return {}
    return {workspace_path: {
        "structured_output": HTTPX_SCREENSHOT_DIRECTORY,
        "source_flag": source_flag,
    }}


def _matching_workspace_write(resolved_path: str, writes: list[str]) -> str:
    normalized_resolved = str(resolved_path or "").replace("\\", "/").rstrip("/")
    matches = [
        path
        for path in writes
        if _normalized_path(path)
        and (
            normalized_resolved == _normalized_path(path)
            or normalized_resolved.endswith(f"/{_normalized_path(path)}")
        )
    ]
    return matches[0] if len(matches) == 1 else ""


def _normalized_path(path: str) -> str:
    return str(path).replace("\\", "/").strip("/")


__all__ = ["HTTPX_SCREENSHOT_DIRECTORY", "httpx_screenshot_artifact_metadata"]
