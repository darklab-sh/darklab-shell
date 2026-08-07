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


_ACTIONS = {
    "http": ServiceAction(
        "http_profile", "Review HTTP surface", "The service identified an HTTP endpoint.",
        "command:httpx", "standard", frozenset({"domain", "ip", "url"}),
    ),
    "https": ServiceAction(
        "https_profile", "Review HTTPS surface", "The service identified an HTTPS endpoint.",
        "command:httpx", "standard", frozenset({"domain", "ip", "url"}),
    ),
    "ssh": ServiceAction(
        "ssh_enumeration", "Enumerate SSH safely", "The service fingerprint explicitly identified SSH.",
        "command:nmap", "standard", frozenset({"domain", "ip"}),
    ),
    "smtp": ServiceAction(
        "smtp_enumeration", "Review SMTP service", "The service fingerprint explicitly identified SMTP.",
        "command:nmap", "standard", frozenset({"domain", "ip"}),
    ),
}

_ALIASES = {
    "http-alt": "http",
    "http-proxy": "http",
    "ssl/http": "https",
    "ssh?": "review",
    "unknown": "review",
}


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
    key = _ALIASES.get(normalized, normalized)
    action = _ACTIONS.get(key)
    if action is None or target_type not in action.target_types:
        return ()
    return (action,)


def service_evidence_state(service: str | None, *, port: int | None = None) -> str:
    """Classify service evidence without inferring a service from a port number."""
    normalized = str(service or "").strip().casefold()
    if not normalized or normalized in {"unknown", "ambiguous", "review"}:
        return "needs_review"
    return "identified" if normalized in _ACTIONS or normalized in _ALIASES else "unsupported"


__all__ = ["ServiceAction", "service_actions", "service_evidence_state"]
