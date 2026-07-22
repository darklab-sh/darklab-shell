# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Filesystem boundary for app-managed run output sinks."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from services.teams.scope import OwnerContext
from services.workspace.file_mutations import append_owner_workspace_text_file
from services.workspace.files import (
    InvalidWorkspacePath,
    WorkspaceDisabled,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
    resolve_owner_workspace_path,
    write_owner_workspace_text_file,
)


log = logging.getLogger("shell")


def preflight_output_sink_destination(
    owner: OwnerContext,
    relative_path: str,
    cfg: Mapping[str, Any] | None,
) -> None:
    """Reject unsafe or directory destinations before a command starts."""
    try:
        destination = resolve_owner_workspace_path(owner, relative_path, cfg)
    except InvalidWorkspacePath as exc:
        if str(exc) == "parent directory does not exist":
            return
        raise ValueError(str(exc)) from exc
    except OSError as exc:
        log.warning("WORKSPACE_OUTPUT_SINK_PREFLIGHT_FAILED", exc_info=True, extra={
            "destination": relative_path,
            "error_type": type(exc).__name__,
        })
        raise ValueError("Output redirection destination could not be checked.") from exc
    try:
        if destination.is_dir():
            raise ValueError("Output redirection destination must be a file, not a directory.")
    except OSError as exc:
        log.warning("WORKSPACE_OUTPUT_SINK_PREFLIGHT_FAILED", exc_info=True, extra={
            "destination": relative_path,
            "error_type": type(exc).__name__,
        })
        raise ValueError("Output redirection destination could not be checked.") from exc


def write_output_sink_text(
    owner: OwnerContext,
    relative_path: str,
    text: str,
    cfg: Mapping[str, Any] | None,
    *,
    append: bool,
) -> str:
    """Write captured output and return a safe user-facing error, if any."""
    writer = append_owner_workspace_text_file if append else write_owner_workspace_text_file
    try:
        writer(owner, relative_path, text, cfg)
    except (
        InvalidWorkspacePath,
        WorkspaceDisabled,
        WorkspacePermissionDenied,
        WorkspaceQuotaExceeded,
    ) as exc:
        return str(exc) or type(exc).__name__
    except OSError as exc:
        log.warning("WORKSPACE_OUTPUT_SINK_WRITE_FAILED", exc_info=True, extra={
            "destination": relative_path,
            "error_type": type(exc).__name__,
        })
        return "could not write the file"
    return ""
