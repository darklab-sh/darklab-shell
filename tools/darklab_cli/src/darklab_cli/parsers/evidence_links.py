# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for Project finding-evidence links."""

from __future__ import annotations

import argparse


EVIDENCE_TYPE_CHOICES = (
    "run",
    "run_line",
    "run_artifact",
    "workspace_file",
    "screenshot",
    "atlas_entity",
    "project_target",
    "assessment_check",
    "retest_run",
)


def _finding_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    parser.add_argument("finding_id", metavar="FINDING")


def register_finding_evidence_parsers(commands: argparse._SubParsersAction) -> None:
    listing = commands.add_parser("list", help="List every typed link for one finding.")
    _finding_arguments(listing)
    listing.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    link = commands.add_parser("link", help="Link one Project-owned evidence source.")
    _finding_arguments(link)
    link.add_argument("evidence_type", metavar="TYPE", choices=EVIDENCE_TYPE_CHOICES)
    link.add_argument("evidence_id", metavar="EVIDENCE_ID")
    link.add_argument(
        "--line-number",
        type=int,
        help="Zero-based source line; required only for run_line evidence.",
    )
    link.add_argument("--snippet", help="Optional run_line excerpt, up to 1000 characters.")
    link.add_argument("--format", choices=("text", "json"), default="text")

    unlink = commands.add_parser("unlink", help="Remove one stable finding-evidence link.")
    _finding_arguments(unlink)
    unlink.add_argument("evidence_link_id", metavar="LINK_ID")
    unlink.add_argument("--format", choices=("text", "json"), default="text")


__all__ = ["EVIDENCE_TYPE_CHOICES", "register_finding_evidence_parsers"]
