# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Conservative service-to-action recommendations for assessment surfaces."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceAction:
    """One reviewed action that may be suggested for explicit service evidence."""

    key: str
    label: str
    rationale: str
    command: str
    policy_level: str
    target_types: frozenset[str]
    required_features: frozenset[str]
    expected_evidence: frozenset[str]
    unsupported_conditions: tuple[str, ...]


from .service_action_catalog import ACTIONS, ALIASES  # noqa: E402


def service_actions(
    service: str | None,
    *,
    port: int | None = None,
    target_type: str = "",
) -> tuple[ServiceAction, ...]:
    """Return actions only when the reported service is explicit and compatible."""
    normalized = str(service or "").strip().casefold()
    if not normalized or normalized in {"review", "ambiguous"}:
        return ()
    key = ALIASES.get(normalized, normalized)
    action = ACTIONS.get(key)
    if action is None or (target_type and target_type not in action.target_types):
        return ()
    return (action,)


def service_evidence_state(service: str | None, *, port: int | None = None) -> str:
    """Classify service evidence without inferring a service from a port number."""
    normalized = str(service or "").strip().casefold()
    resolved = ALIASES.get(normalized, normalized)
    if not normalized or resolved in {"unknown", "ambiguous", "review"}:
        return "needs_review"
    return "identified" if resolved in ACTIONS else "unsupported"


__all__ = ["ServiceAction", "service_actions", "service_evidence_state"]
