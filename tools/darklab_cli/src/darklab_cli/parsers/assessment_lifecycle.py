# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for assessment-cycle lifecycle commands."""

from __future__ import annotations

import argparse


def register_assessment_lifecycle_parsers(
    commands: argparse._SubParsersAction,
) -> None:
    create = commands.add_parser(
        "create",
        help="Create an assessment cycle from a maintained profile.",
    )
    create.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    create.add_argument("profile_key", metavar="PROFILE_KEY")
    create.add_argument("--title")
    create.add_argument("--format", choices=("text", "json"), default="text")

    for command, help_text in (
        ("complete", "Complete an active assessment cycle."),
        ("archive", "Archive a completed assessment cycle."),
    ):
        transition = commands.add_parser(command, help=help_text)
        transition.add_argument(
            "project_id", metavar="PROJECT", help="Active Project slug or id."
        )
        transition.add_argument("assessment_id")
        transition.add_argument("--format", choices=("text", "json"), default="text")

    delete = commands.add_parser(
        "delete",
        help="Preview or explicitly delete an archived assessment cycle.",
    )
    delete.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    delete.add_argument("assessment_id")
    delete.add_argument(
        "--confirm",
        action="store_true",
        help="Delete the previewed cycle; without this flag the command is read-only.",
    )
    delete.add_argument("--format", choices=("text", "json"), default="text")


__all__ = ["register_assessment_lifecycle_parsers"]
