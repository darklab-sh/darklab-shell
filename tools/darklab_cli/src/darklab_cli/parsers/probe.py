# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for Project-scoped probe commands."""

from __future__ import annotations

import argparse


def _target_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action_id", metavar="ACTION")
    parser.add_argument("target_value", nargs="?", metavar="TARGET")
    parser.add_argument("--project", dest="project_id", required=True, help="Active Project slug or id that owns the target.")
    parser.add_argument("--entity-id", help="Confirmed Project target id instead of an exact target value.")
    parser.add_argument("--http-profile", dest="http_profile_id", help="Protected Project HTTP profile id.")
    parser.add_argument("--nmap-profile")
    parser.add_argument("--nuclei-profile", default="safe")
    parser.add_argument("--format", choices=("text", "json"), default="text")

def register_probe_parser(subparsers: argparse._SubParsersAction) -> None:
    probe = subparsers.add_parser(
        "probe",
        help="List, preview, and run bounded commands against confirmed Project targets.",
    )
    commands = probe.add_subparsers(dest="probe_command", required=True)

    listing = commands.add_parser("list", help="List reviewed probe actions and profiles.")
    listing.add_argument("--project", dest="project_id", required=True, help="Active Project slug or id.")
    listing.add_argument("--service", help="Show recommendations for one discovered service.")
    listing.add_argument("--target-type", choices=("domain", "ip", "url"))
    listing.add_argument("--format", choices=("text", "json"), default="text")

    plan = commands.add_parser("plan", help="Preview one bounded probe without starting a run.")
    _target_arguments(plan)

    run = commands.add_parser("run", help="Preview a probe and optionally start it.")
    _target_arguments(run)
    run.add_argument(
        "--confirm",
        action="store_true",
        help="Start the freshly previewed probe; without this flag the command is read-only.",
    )
    run.add_argument("--workspace-cwd")


__all__ = ["register_probe_parser"]
