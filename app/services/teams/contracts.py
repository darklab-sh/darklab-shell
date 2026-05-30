"""Shared team-mode constants and exceptions."""

from __future__ import annotations


TEAM_ROLES = frozenset({"owner", "admin", "operator", "viewer"})
TEAM_STATUSES = frozenset({"active", "archived", "deleted"})
TEAM_MEMBER_STATUSES = frozenset({"active", "removed"})
OWNER_SCOPES = frozenset({"personal", "team"})

MAX_TEAM_NAME_LEN = 120
MAX_TEAM_SLUG_LEN = 80
MAX_TEAM_MEMBER_DISPLAY_NAME_LEN = 120
MAX_TEAM_INVITE_LABEL_LEN = 120


class TeamError(ValueError):
    """Raised when team-mode input or state is invalid."""


class TeamNotFound(TeamError):
    """Raised when a referenced team entity is missing."""


class TeamArchived(TeamError):
    """Raised when a team exists but cannot accept active-scope work."""


class TeamPermissionDenied(TeamError):
    """Raised when a team role lacks a requested capability."""


class TeamOwnerRequired(TeamError):
    """Raised when an operation would leave a team without an owner."""


class TeamSlugUnavailable(TeamError):
    """Raised when a team slug is already in use."""
