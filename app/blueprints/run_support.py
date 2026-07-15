# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared support helpers for run route modules."""

from __future__ import annotations

from flask import jsonify

from services.teams.capabilities import Capability, require_capability, role_can
from services.teams.contracts import TeamPermissionDenied

CLIENT_SIDE_RUN_ROOTS = {
    "cat",
    "cd",
    "config",
    "file",
    "grep",
    "head",
    "ll",
    "ls",
    "mkdir",
    "pwd",
    "rm",
    "session-token",
    "sort",
    "tail",
    "theme",
    "tour",
    "uniq",
    "wc",
}


def active_run_owner_value(value: object) -> str:
    return str(value or "").strip()[:128]


def workspace_cwd_value(value: object) -> str:
    return str(value or "").strip()[:1024]


def client_side_run_command_allowed(command: str) -> bool:
    root = command.strip().split(maxsplit=1)[0].lower() if command.strip() else ""
    return root in CLIENT_SIDE_RUN_ROOTS


def coerce_positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        number = int(value)
    elif isinstance(value, (str, bytes, bytearray)):
        try:
            number = int(value)
        except ValueError:
            return default
    else:
        return default
    return number if number > 0 else default


def interactive_pty_concurrency_limit() -> int:
    from blueprints import run as run_routes

    return coerce_positive_int(run_routes.CFG.get("interactive_pty_max_concurrent_per_session", 4), 4)


def interactive_pty_input_limit() -> str:
    from blueprints import run as run_routes

    per_minute = coerce_positive_int(run_routes.CFG.get("interactive_pty_input_rate_limit_per_minute"), 500)
    per_second = coerce_positive_int(run_routes.CFG.get("interactive_pty_input_rate_limit_per_second"), 10)
    return f"{per_minute} per minute; {per_second} per second"


def interactive_pty_resize_limit() -> str:
    from blueprints import run as run_routes

    per_minute = coerce_positive_int(run_routes.CFG.get("interactive_pty_resize_rate_limit_per_minute"), 600)
    per_second = coerce_positive_int(run_routes.CFG.get("interactive_pty_resize_rate_limit_per_second"), 30)
    return f"{per_minute} per minute; {per_second} per second"


def active_interactive_pty_count(session_id: str) -> int:
    from blueprints import run as run_routes

    return sum(
        1 for item in run_routes.active_runs_for_session(session_id)
        if str(item.get("run_type", "command") or "command") == "pty"
    )


def team_capability_error_response(exc: TeamPermissionDenied):
    return jsonify({"error": "team_forbidden", "message": str(exc)}), 403


def require_team_capability(owner_scope, capability: Capability):
    if not owner_scope.is_team:
        return None
    try:
        require_capability(str((owner_scope.member or {}).get("role") or ""), capability)
    except TeamPermissionDenied as exc:
        return team_capability_error_response(exc)
    return None


def scope_has_team_capability(owner_scope, capability: Capability) -> bool:
    if not owner_scope.is_team:
        return True
    return role_can(str((owner_scope.member or {}).get("role") or ""), capability)


def team_audit_fields(owner_scope) -> dict[str, str]:
    member = owner_scope.member or {}
    return {
        "team_id": str(owner_scope.team_id or ""),
        "actor_member_id": str(member.get("id") or ""),
        "team_role": str(member.get("role") or ""),
    }
