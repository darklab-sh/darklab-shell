# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read typed evidence through API v1."""

from __future__ import annotations

import argparse

from ..client import DarklabClient, DarklabCliError
from .evidence_links import handle_finding_evidence
from .service_evidence import handle_service_evidence


def handle_evidence(client: DarklabClient, args: argparse.Namespace) -> int:
    if args.evidence_command in {"list", "link", "unlink"}:
        return handle_finding_evidence(client, args)
    if args.evidence_command == "services":
        return handle_service_evidence(client, args)
    raise DarklabCliError("unknown evidence command")


__all__ = ["handle_evidence"]
