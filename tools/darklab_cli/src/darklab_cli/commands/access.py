# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Principal and current-PAT CLI commands."""

from __future__ import annotations

import argparse

from ..client import DarklabClient, die
from ..formatting import print_collection, print_payload


def handle_access(client: DarklabClient, args: argparse.Namespace) -> int:
    if args.command == "whoami":
        return print_payload(client.request("GET", "/whoami"), args.format)
    if args.credential_command == "status":
        return print_payload(client.request("GET", "/principal"), args.format)
    if args.credential_command == "list":
        payload = client.request("GET", "/credentials")
        return print_collection(
            payload,
            "credentials",
            args.format,
            fields=("id", "credential_type", "label", "expires_at", "revoked_at"),
        )
    if args.credential_command == "revoke":
        return print_payload(
            client.request(
                "POST",
                "/credentials/current/revoke",
                body={"reason": args.reason},
            ),
            args.format,
        )
    return die("unknown credential command")
