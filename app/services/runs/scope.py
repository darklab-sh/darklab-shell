# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Run scope visibility and command validation helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any, NotRequired, TypedDict

from config import resolve_effective_cfg
from core.helpers import get_log_session_id
from services.commands.registry import CommandValidationResult, is_command_allowed, validate_command
from services.teams.scope import OwnerContext

log = logging.getLogger("shell")


class RunSessionVisibility(TypedDict):
    allowed: bool
    active_match: bool
    db_match: bool
    active_count: int
    scope_mismatch: NotRequired[bool]
    actual_team_id: NotRequired[str]


def run_scope_mismatch_payload(actual_team_id: str) -> dict[str, str]:
    if actual_team_id:
        return {
            "error": "run_scope_mismatch",
            "message": "Run exists in a different team scope. Switch to that team scope to view it.",
            "scope": "team",
            "team_id": actual_team_id,
        }
    return {
        "error": "run_scope_mismatch",
        "message": "Run exists in personal scope. Switch to personal scope to view it.",
        "scope": "personal",
        "team_id": "",
    }


def run_session_visibility(
    run_id: str,
    session_id: str,
    team_id: str = "",
    *,
    active_run_belongs_to_scope_fn: Callable[[str, str, str], bool],
    active_runs_for_team_fn: Callable[[str], list[dict[str, Any]]],
    active_runs_for_session_fn: Callable[..., list[dict[str, Any]]],
    run_scope_visibility_from_db_fn: Callable[[str, str, str], tuple[bool, bool, str]],
) -> RunSessionVisibility:
    if not run_id or not session_id:
        return {
            "allowed": False,
            "active_match": False,
            "db_match": False,
            "active_count": 0,
        }
    if active_run_belongs_to_scope_fn(run_id, session_id, team_id):
        return {
            "allowed": True,
            "active_match": True,
            "db_match": False,
            "active_count": 1,
        }
    scoped_active_runs = (
        active_runs_for_team_fn(team_id)
        if team_id
        else active_runs_for_session_fn(session_id, team_id="")
    )
    active_ids = {str(item.get("run_id", "")) for item in scoped_active_runs}
    active_match = run_id in active_ids
    if active_match:
        return {
            "allowed": True,
            "active_match": True,
            "db_match": False,
            "active_count": len(active_ids),
        }
    for item in active_runs_for_session_fn(session_id, team_id=None):
        if str(item.get("run_id", "")) == run_id:
            return {
                "allowed": False,
                "active_match": False,
                "db_match": False,
                "active_count": len(active_ids),
                "scope_mismatch": True,
                "actual_team_id": str(item.get("team_id", "") or ""),
            }
    try:
        db_match, scope_mismatch, actual_team_id = run_scope_visibility_from_db_fn(run_id, session_id, team_id)
        return {
            "allowed": db_match,
            "active_match": False,
            "db_match": db_match,
            "active_count": len(active_ids),
            "scope_mismatch": scope_mismatch,
            "actual_team_id": actual_team_id,
        }
    except Exception:
        log.error("RUN_BROKER_SESSION_CHECK_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": get_log_session_id(session_id),
        })
        return {
            "allowed": False,
            "active_match": False,
            "db_match": False,
            "active_count": len(active_ids),
        }


def effective_owner_context(owner_context: OwnerContext | None, session_id: str) -> OwnerContext | None:
    if owner_context is None:
        return None
    if owner_context.is_team:
        return owner_context
    if owner_context.owner_id != str(session_id or "").strip():
        return owner_context
    return None


def validate_command_for_run(
    command: str,
    session_id: str,
    workspace_cwd: str = "",
    *,
    extra_allowed_prefixes: list[str] | None = None,
    owner_context: OwnerContext | None = None,
    cfg: Mapping[str, Any] | None = None,
    is_command_allowed_fn: Callable[[str], tuple[bool, str]] = is_command_allowed,
    validate_command_fn: Callable[..., CommandValidationResult] = validate_command,
) -> CommandValidationResult:
    # Several route tests monkeypatch the blueprint's legacy is_command_allowed
    # symbol to keep subprocess behavior focused. Honor that seam when injected.
    if getattr(is_command_allowed_fn, "__module__", "") != "services.commands.registry":
        allowed, reason = is_command_allowed_fn(command)
        return CommandValidationResult(
            allowed,
            reason,
            display_command=command,
            exec_command=command,
        )
    active_cfg = resolve_effective_cfg(cfg)
    effective_owner = effective_owner_context(owner_context, session_id)
    if effective_owner is not None:
        return validate_command_fn(
            command,
            session_id=session_id,
            cfg=active_cfg,
            workspace_cwd=workspace_cwd,
            extra_allowed_prefixes=extra_allowed_prefixes,
            owner_context=effective_owner,
        )
    return validate_command_fn(
        command,
        session_id=session_id,
        cfg=active_cfg,
        workspace_cwd=workspace_cwd,
        extra_allowed_prefixes=extra_allowed_prefixes,
    )


def validate_command_with_effective_owner(
    command: str,
    session_id: str,
    workspace_cwd: str = "",
    *,
    extra_allowed_prefixes: list[str] | None = None,
    owner_context: OwnerContext | None = None,
    validate_command_for_run_fn: Callable[..., CommandValidationResult] = validate_command_for_run,
) -> CommandValidationResult:
    effective_owner = effective_owner_context(owner_context, session_id)
    if effective_owner is not None:
        return validate_command_for_run_fn(
            command,
            session_id,
            workspace_cwd,
            extra_allowed_prefixes=extra_allowed_prefixes,
            owner_context=effective_owner,
        )
    if extra_allowed_prefixes is not None:
        return validate_command_for_run_fn(
            command,
            session_id,
            workspace_cwd,
            extra_allowed_prefixes=extra_allowed_prefixes,
        )
    return validate_command_for_run_fn(command, session_id, workspace_cwd)
