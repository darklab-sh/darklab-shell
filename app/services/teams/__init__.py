# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Dormant team-mode foundation services."""

from .capabilities import Capability, capabilities_for_role, require_capability, role_can
from .ownership_queries import (
    AttributionValues,
    OwnerKeyShape,
    OwnershipPredicate,
    PersonalTeamRows,
    attribution_values,
    composite_owner_predicate,
    personal_only_owner_predicate,
    team_capable_owner_predicate,
    token_keyed_owner_predicate,
)
from .scope import OwnerContext, anonymous_owner_context, owner_context_for_scope, personal_owner_context, team_owner_context

__all__ = [
    "Capability",
    "AttributionValues",
    "OwnerKeyShape",
    "OwnerContext",
    "OwnershipPredicate",
    "PersonalTeamRows",
    "anonymous_owner_context",
    "attribution_values",
    "capabilities_for_role",
    "composite_owner_predicate",
    "owner_context_for_scope",
    "personal_only_owner_predicate",
    "personal_owner_context",
    "require_capability",
    "role_can",
    "team_capable_owner_predicate",
    "team_owner_context",
    "token_keyed_owner_predicate",
]
