# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for shared CVE risk commands."""

from __future__ import annotations

import argparse


def register_risk_parser(subparsers: argparse._SubParsersAction) -> None:
    risk = subparsers.add_parser(
        "risk",
        help="Read configured CVE risk feed state without starting refreshes.",
    )
    commands = risk.add_subparsers(dest="risk_command", required=True)
    status = commands.add_parser(
        "status",
        help="Show stored EPSS and KEV feed freshness and configuration.",
    )
    status.add_argument("--format", choices=("text", "json", "ndjson"), default="text")


__all__ = ["register_risk_parser"]
