"""Dormant team-mode foundation services."""

from .capabilities import Capability, capabilities_for_role, require_capability, role_can
from .scope import OwnerContext, personal_owner_context, team_owner_context

__all__ = [
    "Capability",
    "OwnerContext",
    "capabilities_for_role",
    "personal_owner_context",
    "require_capability",
    "role_can",
    "team_owner_context",
]
