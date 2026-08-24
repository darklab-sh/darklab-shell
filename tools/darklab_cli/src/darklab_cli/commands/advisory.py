# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Run explicit advisory acquisition through API v1."""

from __future__ import annotations

import argparse

from ..client import DarklabClient, DarklabCliError
from ..formatting import print_payload


_ACTIONABLE_ERRORS = {
    "team_forbidden": "OSV lookup requires the TRIAGE_FINDINGS capability for the selected team.",
    "osv_lookup_disabled": (
        "External OSV lookups are disabled. Set cve_risk.osv_advisory_mode "
        "to external and retry."
    ),
    "osv_lookup_failed": (
        "The OSV provider lookup failed. Check outbound access and provider "
        "availability, then retry."
    ),
    "osv_lookup_busy": "The OSV lookup budget is temporarily busy. Wait a moment, then retry.",
}


def handle_advisory(client: DarklabClient, args: argparse.Namespace) -> int:
    if args.advisory_command != "osv":
        raise DarklabCliError("unknown advisory command")
    purl = args.purl
    version = args.version
    if not isinstance(purl, str) or not purl.strip():
        raise DarklabCliError("advisory osv PURL must not be empty")
    if not isinstance(version, str) or not version.strip():
        raise DarklabCliError("advisory osv VERSION must not be empty")
    try:
        payload = client.request(
            "POST",
            "/advisories/osv/lookup",
            body={"purl": purl, "version": version},
        )
    except DarklabCliError as exc:
        message = _ACTIONABLE_ERRORS.get(exc.code)
        if not message:
            raise
        raise DarklabCliError(
            message,
            status=exc.status,
            code=exc.code,
            details=exc.details,
        ) from exc
    return print_payload(payload, args.format)


__all__ = ["handle_advisory"]
