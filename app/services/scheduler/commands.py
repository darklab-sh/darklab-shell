"""Shared scheduled-command validation helpers."""

from __future__ import annotations

from typing import Any

from config import CFG
from services.commands.registry import command_root, rewrite_command, validate_command
from services.session.variables import expand_session_variables


class ScheduleCommandValidationError(ValueError):
    """Raised when a scheduled command cannot be accepted."""


def validate_schedule_command(command: Any, session_id: str, *, workspace_cwd: str = "") -> str:
    """Validate a command for later scheduled execution and return its typed form."""
    if not isinstance(command, str):
        raise ScheduleCommandValidationError("command must be a string")
    original_command = command.strip()
    if not original_command:
        raise ScheduleCommandValidationError("command is required")

    expanded_command = original_command
    if command_root(original_command) != "var":
        expanded_command = expand_session_variables(original_command, session_id).command

    validation = validate_command(
        expanded_command,
        session_id=session_id,
        cfg=CFG,
        workspace_cwd=str(workspace_cwd or "").strip()[:1024],
    )
    if not validation.allowed:
        raise ScheduleCommandValidationError(validation.reason or "command is not allowed")

    rewrite_command(validation.exec_command or expanded_command, session_id=session_id, cfg=CFG)
    return original_command
