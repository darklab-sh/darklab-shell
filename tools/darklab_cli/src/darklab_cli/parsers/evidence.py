# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for typed evidence commands."""

from __future__ import annotations

import argparse

from .evidence_links import register_finding_evidence_parsers

def register_evidence_parser(subparsers: argparse._SubParsersAction) -> None:
    evidence = subparsers.add_parser(
        "evidence",
        help="Read and manage typed evidence without copying source records.",
    )
    commands = evidence.add_subparsers(dest="evidence_command", required=True)
    register_finding_evidence_parsers(commands)
    services = commands.add_parser(
        "services",
        help="Page through structured Nmap service evidence for one saved run.",
    )
    services.add_argument("run_id", metavar="RUN_ID")
    services.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    services.add_argument("--offset", type=int, default=0, help="Rows to skip; max 100000.")
    services.add_argument("--format", choices=("text", "json", "ndjson"), default="text")


__all__ = ["register_evidence_parser"]
