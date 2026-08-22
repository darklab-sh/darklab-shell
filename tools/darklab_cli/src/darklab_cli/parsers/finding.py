# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for assessor-authored finding commands."""

from __future__ import annotations

import argparse


def _input_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        required=True,
        metavar="PATH|-",
        help="Read one finding JSON object from a file, or use - for stdin.",
    )
    parser.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="Create or save despite the server's possible-duplicate check.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")


def register_finding_parser(subparsers: argparse._SubParsersAction) -> None:
    finding = subparsers.add_parser(
        "finding",
        help="Create and edit assessor-authored Project findings.",
    )
    commands = finding.add_subparsers(dest="finding_command", required=True)
    create = commands.add_parser(
        "create",
        help="Create a finding from a confirmed Project target and structured input.",
    )
    create.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    _input_argument(create)
    edit = commands.add_parser(
        "edit",
        help="Edit a manual finding with an explicit expected revision.",
    )
    edit.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    edit.add_argument("finding_id", metavar="FINDING")
    edit.add_argument("--expected-revision", type=int, required=True)
    _input_argument(edit)


__all__ = ["register_finding_parser"]
