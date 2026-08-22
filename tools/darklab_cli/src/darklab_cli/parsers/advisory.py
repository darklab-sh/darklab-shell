# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for explicit advisory acquisition commands."""

from __future__ import annotations

import argparse


def register_advisory_parser(subparsers: argparse._SubParsersAction) -> None:
    advisory = subparsers.add_parser(
        "advisory",
        help="Run explicit advisory lookups; ordinary reads never contact providers.",
    )
    commands = advisory.add_subparsers(dest="advisory_command", required=True)
    osv = commands.add_parser(
        "osv",
        help="Send one exact PURL and version to the configured OSV provider.",
        description=(
            "Explicitly send one exact PURL and version to the configured OSV provider. "
            "This is the only darklab CLI path that can start an OSV lookup."
        ),
    )
    osv.add_argument("purl", metavar="PURL")
    osv.add_argument("version", metavar="VERSION")
    osv.add_argument("--format", choices=("text", "json"), default="text")


__all__ = ["register_advisory_parser"]
