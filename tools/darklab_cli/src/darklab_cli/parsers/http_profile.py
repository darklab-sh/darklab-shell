# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for Project HTTP-profile commands."""

from __future__ import annotations

import argparse


def register_http_profile_parser(subparsers: argparse._SubParsersAction) -> None:
    profiles = subparsers.add_parser(
        "http-profile",
        help="Read and manage Project HTTP profiles without accepting Secret values.",
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
    create_profile = commands.add_parser(
        "create",
        help="Create an HTTP profile from a bounded JSON object.",
    )
    create_profile.add_argument("project_ref", metavar="PROJECT")
    create_profile.add_argument(
        "--input", required=True, metavar="PATH|-",
        help="JSON object file, or - for standard input.",
    )
    create_profile.add_argument("--format", choices=("text", "json"), default="text")
    update_profile = commands.add_parser(
        "update",
        help="Update an HTTP profile using its current revision.",
    )
    update_profile.add_argument("project_ref", metavar="PROJECT")
    update_profile.add_argument("profile_id", metavar="PROFILE_ID")
    update_profile.add_argument("--revision", required=True, type=int)
    update_profile.add_argument(
        "--input", required=True, metavar="PATH|-",
        help="JSON object file, or - for standard input.",
    )
    update_profile.add_argument("--format", choices=("text", "json"), default="text")
    delete_profile = commands.add_parser(
        "delete",
        help="Preview or explicitly delete one HTTP profile.",
    )
    delete_profile.add_argument("project_ref", metavar="PROJECT")
    delete_profile.add_argument("profile_id", metavar="PROFILE_ID")
    delete_profile.add_argument(
        "--confirm",
        action="store_true",
        help="Delete the previewed profile; without this flag the command is read-only.",
    )
    delete_profile.add_argument("--format", choices=("text", "json"), default="text")


__all__ = ["register_http_profile_parser"]
