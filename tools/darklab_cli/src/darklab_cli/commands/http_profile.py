# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read Project HTTP profiles through API v1."""

from __future__ import annotations

import argparse

from ..client import DarklabClient, DarklabCliError
from .http_profile_formatting import print_http_profile, print_http_profiles
from .http_profile_mutations import handle_http_profile_mutation
from .project_references import resolve_active_project_id


def handle_http_profile(client: DarklabClient, args: argparse.Namespace) -> int:
    project_id = resolve_active_project_id(client, args.project_ref)
    collection_path = f"/projects/{project_id}/http-profiles"
    if args.http_profile_command == "list":
        payload = client.request("GET", collection_path)
        return print_http_profiles(payload, args.format)
    if args.http_profile_command == "show":
        payload = client.request("GET", f"{collection_path}/{args.profile_id}")
        return print_http_profile(payload, args.format)
    if args.http_profile_command in {"create", "update", "delete"}:
        return handle_http_profile_mutation(client, args, collection_path)
    raise DarklabCliError("unknown HTTP profile command")


__all__ = ["handle_http_profile"]
