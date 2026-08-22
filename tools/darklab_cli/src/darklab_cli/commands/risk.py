# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read configured CVE risk state through API v1."""

from __future__ import annotations

import argparse

from ..client import DarklabClient, DarklabCliError
from ..formatting import print_collection


_FEED_FIELDS = (
    "source",
    "status",
    "origin",
    "source_version",
    "model_version",
    "published_at",
    "retrieved_at",
    "accepted_at",
    "age_hours",
    "record_count",
    "last_attempt_at",
    "last_error",
    "source_url",
    "attribution",
    "terms_url",
    "live_refresh_enabled",
)


def handle_risk(client: DarklabClient, args: argparse.Namespace) -> int:
    if args.risk_command != "status":
        raise DarklabCliError("unknown risk command")
    payload = client.request("GET", "/risk/feeds")
    return print_collection(payload, "feeds", args.format, fields=_FEED_FIELDS)


__all__ = ["handle_risk"]
