# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable identity for normalized DNSx takeover observations."""

from __future__ import annotations

import hashlib


DNSX_TAKEOVER_PARSER_VERSION = "dnsx-json-takeover-v2"


def dnsx_observation_id(
    run_id: str,
    hostname: str,
    observed_at: str,
    cnames: list[str],
    status_code: str,
    resolution_state: str,
    scope_decision: str,
    wildcard_filter: str,
) -> str:
    """Return the stable identity for one normalized DNSx observation."""
    source = "\x1f".join((
        run_id, hostname, observed_at, status_code,
        resolution_state, scope_decision, wildcard_filter, *cnames,
    ))
    return "dnsobs_" + hashlib.sha256(source.encode()).hexdigest()[:32]


__all__ = ["DNSX_TAKEOVER_PARSER_VERSION", "dnsx_observation_id"]
