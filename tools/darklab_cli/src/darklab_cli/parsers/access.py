# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Principal and credential command parsers."""

from __future__ import annotations

import argparse


def register_access_parser(sub: argparse._SubParsersAction) -> None:
    whoami = sub.add_parser("whoami", help="Show the current principal and PAT metadata.")
    whoami.add_argument("--format", choices=("text", "json"), default="text")
    credential = sub.add_parser("credential", help="Inspect or revoke the PAT used by this CLI.")
    credential_sub = credential.add_subparsers(dest="credential_command", required=True)
    status = credential_sub.add_parser("status", help="Show the current principal and PAT metadata.")
    status.add_argument("--format", choices=("text", "json"), default="text")
    listing = credential_sub.add_parser("list", help="Show safe metadata for the current PAT.")
    listing.add_argument("--format", choices=("text", "json", "ndjson"), default="text")
    revoke = credential_sub.add_parser("revoke", help="Revoke the current PAT.")
    revoke.add_argument("--reason", default="CLI self-revocation")
    revoke.add_argument("--format", choices=("text", "json"), default="text")

