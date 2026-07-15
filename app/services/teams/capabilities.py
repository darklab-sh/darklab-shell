# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Role-to-capability checks for team mode."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from .contracts import TeamPermissionDenied

log = logging.getLogger("shell")


class Capability(str, Enum):
    VIEW_TEAM = "view_team"
    MANAGE_OWNERS = "manage_owners"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_INVITES = "manage_invites"
    MANAGE_RECOVERY = "manage_recovery"
    ARCHIVE_TEAM = "archive_team"
    RUN_COMMANDS = "run_commands"
    MANAGE_HISTORY = "manage_history"
    MANAGE_WORKSPACE_FILES = "manage_workspace_files"
    MANAGE_AUTOMATION = "manage_automation"
    MUTATE_PROJECTS = "mutate_projects"
    TRIAGE_FINDINGS = "triage_findings"
    MANAGE_WORKFLOWS = "manage_workflows"
    MANAGE_NOTIFICATIONS = "manage_notifications"
    MANAGE_SECRETS = "manage_secrets"


ROLE_CAPABILITIES: dict[str, frozenset[Capability]] = {
    "owner": frozenset(Capability),
    "admin": frozenset({
        Capability.VIEW_TEAM,
        Capability.MANAGE_MEMBERS,
        Capability.MANAGE_INVITES,
        Capability.RUN_COMMANDS,
        Capability.MANAGE_HISTORY,
        Capability.MANAGE_WORKSPACE_FILES,
        Capability.MANAGE_AUTOMATION,
        Capability.MUTATE_PROJECTS,
        Capability.TRIAGE_FINDINGS,
        Capability.MANAGE_WORKFLOWS,
        Capability.MANAGE_NOTIFICATIONS,
        Capability.MANAGE_SECRETS,
    }),
    "operator": frozenset({
        Capability.VIEW_TEAM,
        Capability.RUN_COMMANDS,
        Capability.MANAGE_HISTORY,
        Capability.MANAGE_WORKSPACE_FILES,
        Capability.MANAGE_AUTOMATION,
        Capability.MUTATE_PROJECTS,
        Capability.TRIAGE_FINDINGS,
    }),
    "viewer": frozenset({
        Capability.VIEW_TEAM,
    }),
}


def _coerce_capability(capability: Capability | str) -> Capability | None:
    if isinstance(capability, Capability):
        return capability
    try:
        return Capability(capability)
    except ValueError:
        return None


def role_can(role: str, capability: Capability | str) -> bool:
    """Return whether a role grants a capability."""
    normalized = _coerce_capability(capability)
    if normalized is None:
        return False
    return normalized in ROLE_CAPABILITIES.get(role, frozenset())


def capabilities_for_role(role: str) -> tuple[str, ...]:
    """Return the public capability names granted to a role."""
    granted = ROLE_CAPABILITIES.get(role, frozenset())
    return tuple(capability.value for capability in Capability if capability in granted)


def _capability_denied_fields(
    role: str,
    capability_value: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    fields = {
        "actor_role": str(role or ""),
        "capability": capability_value,
    }
    for key in (
        "team_id",
        "actor_member_id",
        "action",
        "route",
        "method",
        "source",
        "surface",
        "session",
        "ip",
    ):
        value = context.get(key)
        if value is not None:
            fields[key] = str(value)
    return fields


def require_capability(role: str, capability: Capability | str, **context: Any) -> None:
    """Raise when a role does not grant a capability."""
    if role_can(role, capability):
        return
    normalized = _coerce_capability(capability)
    capability_value = normalized.value if normalized else str(capability)
    log.warning(
        "TEAM_CAPABILITY_DENIED",
        extra=_capability_denied_fields(role, capability_value, context),
    )
    raise TeamPermissionDenied(f"Role {role!r} lacks team capability {capability_value!r}")
