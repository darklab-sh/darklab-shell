# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Create, update, and delete Project HTTP profiles through API v1."""

from __future__ import annotations

import argparse
from typing import Any

from ..client import DarklabClient, DarklabCliError
from ..http_profile_payloads import read_http_profile_input
from .confirmations import destructive_action_confirmed
from .http_profile_formatting import print_http_profile, print_http_profile_deleted


def _actionable_error(exc: DarklabCliError, command: str) -> DarklabCliError:
    if exc.code == "team_forbidden":
        message = (
            "HTTP-profile changes require the MANAGE_SECRETS capability for "
            "the selected team."
        )
    elif exc.code == "http_profile_conflict" and command == "update":
        message = (
            "The HTTP profile changed or its name now conflicts. Review the current "
            "profile and retry with its current --revision."
        )
    elif exc.code == "http_profile_conflict":
        message = "An HTTP profile with that name already exists in this Project."
    else:
        return exc
    return DarklabCliError(
        message, status=exc.status, code=exc.code, details=exc.details
    )


def _request(
    client: DarklabClient,
    method: str,
    path: str,
    *,
    command: str,
    body: dict[str, Any] | None = None,
) -> Any:
    try:
        return client.request(method, path, body=body)
    except DarklabCliError as exc:
        actionable = _actionable_error(exc, command)
        if actionable is exc:
            raise
        raise actionable from exc


def handle_http_profile_mutation(
    client: DarklabClient,
    args: argparse.Namespace,
    collection_path: str,
) -> int:
    command = args.http_profile_command
    if command in {"create", "update"}:
        body = read_http_profile_input(args.input, update=command == "update")
        method, path = "POST", collection_path
        if command == "update":
            if args.revision < 1:
                raise DarklabCliError("HTTP profile revision must be at least 1")
            body["revision"] = args.revision
            method, path = "PATCH", f"{collection_path}/{args.profile_id}"
        payload = _request(client, method, path, command=command, body=body)
        return print_http_profile(payload, args.format)
    if command == "delete":
        path = f"{collection_path}/{args.profile_id}"
        preview = client.request("GET", path)
        if not destructive_action_confirmed(
            preview,
            confirmed=args.confirm,
            output_format=args.format,
            action="delete this HTTP profile",
            render_text=lambda value: print_http_profile(value, "text"),
        ):
            return 0
        payload = _request(client, "DELETE", path, command=command)
        return print_http_profile_deleted(payload, args.format, args.profile_id)
    raise DarklabCliError("unknown HTTP profile mutation")


__all__ = ["handle_http_profile_mutation"]
