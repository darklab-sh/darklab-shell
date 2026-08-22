# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for Project HTTP-profile commands."""

from __future__ import annotations

import argparse


def register_http_profile_parser(subparsers: argparse._SubParsersAction) -> None:
    profiles = subparsers.add_parser(
        "http-profile",
        help="Read Project HTTP profiles with capability-aware reference details.",
    )
    commands = profiles.add_subparsers(dest="http_profile_command", required=True)
    list_profiles = commands.add_parser(
        "list",
        help="List saved HTTP profiles for an active Project.",
    )
    list_profiles.add_argument("project_ref", metavar="PROJECT")
    list_profiles.add_argument(
        "--format", choices=("text", "json", "ndjson"), default="text"
    )
    show_profile = commands.add_parser(
        "show",
        help="Show one saved HTTP profile.",
    )
    show_profile.add_argument("project_ref", metavar="PROJECT")
    show_profile.add_argument("profile_id", metavar="PROFILE_ID")
    show_profile.add_argument("--format", choices=("text", "json"), default="text")


__all__ = ["register_http_profile_parser"]
