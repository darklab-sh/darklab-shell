# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read paged Nmap service evidence through API v1."""

from __future__ import annotations

import argparse
from typing import Any

from ..client import DarklabClient, DarklabCliError
from ..formatting import print_collection


_SERVICE_FIELDS = (
    "target",
    "service",
    "script_id",
    "evidence_kind",
    "fields",
    "observed_at",
)


def handle_service_evidence(client: DarklabClient, args: argparse.Namespace) -> int:
    if not 1 <= args.limit <= 100:
        raise DarklabCliError("evidence services limit must be between 1 and 100")
    if not 0 <= args.offset <= 100000:
        raise DarklabCliError("evidence services offset must be between 0 and 100000")
    payload = client.request(
        "GET",
        f"/runs/{args.run_id}/service-evidence",
        params={"limit": args.limit, "offset": args.offset},
    )
    observations = payload.get("observations") if isinstance(payload, dict) else None
    if args.format == "text" and not _mapping_items(observations):
        print("No service evidence.")
        return 0
    return print_collection(
        payload,
        "observations",
        args.format,
        fields=_SERVICE_FIELDS,
    )


def _mapping_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


__all__ = ["handle_service_evidence"]
