"""Dormant team-mode foundation services."""

from .capabilities import Capability, capabilities_for_role, require_capability, role_can
from .scope import OwnerContext, anonymous_owner_context, owner_context_for_scope, personal_owner_context, team_owner_context

__all__ = [
    "Capability",
    "OwnerContext",
    "anonymous_owner_context",
    "capabilities_for_role",
    "owner_context_for_scope",
    "personal_owner_context",
    "require_capability",
    "role_can",
    "team_owner_context",
]
