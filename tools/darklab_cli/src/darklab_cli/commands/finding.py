# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Create and edit assessor-authored Project findings through API v1."""

from __future__ import annotations

import argparse
from typing import Any

from ..client import DarklabClient, DarklabCliError
from ..formatting import print_payload, print_table
from ..payloads import read_json_object
from .project_references import resolve_active_project_id


_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
_CONTROL_FIELDS = frozenset({"allow_duplicate", "expected_revision"})

def _mutation_body(args: argparse.Namespace) -> dict[str, Any]:
    body = read_json_object(args.input)
    control_fields = sorted(set(body).intersection(_CONTROL_FIELDS))
    if control_fields:
        flags = ", ".join(f"--{field.replace('_', '-')}" for field in control_fields)
        raise DarklabCliError(
            f"structured finding input can't set CLI control fields; use {flags}"
        )
    severity = body.get("severity")
    if severity is not None and (
        not isinstance(severity, str) or severity.strip().lower() not in _SEVERITIES
    ):
        raise DarklabCliError(
            "finding severity must be critical, high, medium, low, or info"
        )
    if args.allow_duplicate:
        body["allow_duplicate"] = True
    if args.finding_command == "edit":
        if args.expected_revision < 0:
            raise DarklabCliError("finding expected revision must be non-negative")
        body["expected_revision"] = args.expected_revision
    return body


def _actionable_error(exc: DarklabCliError) -> DarklabCliError:
    if exc.code == "team_forbidden":
        message = (
            "Finding changes require the TRIAGE_FINDINGS capability for the selected team."
        )
    elif exc.code == "possible_duplicate":
        details = exc.details if isinstance(exc.details, dict) else {}
        duplicates = details.get("duplicates")
        ids = [str(item.get("id")) for item in duplicates if isinstance(item, dict)] if isinstance(duplicates, list) else []
        suffix = f" Possible matches: {', '.join(ids)}." if ids else ""
        message = (
            "The server found a possible duplicate; review it and retry with "
            f"--allow-duplicate only when the new record is intentional.{suffix}"
        )
    elif exc.code == "stale_revision":
        details = exc.details if isinstance(exc.details, dict) else {}
        current = details.get("current_revision")
        suffix = f" The current revision is {current}." if current is not None else ""
        message = (
            "The finding changed after the expected revision; review the current record and "
            f"retry with its revision.{suffix}"
        )
    else:
        return exc
    return DarklabCliError(message, status=exc.status, code=exc.code, details=exc.details)


def handle_finding(client: DarklabClient, args: argparse.Namespace) -> int:
    body = _mutation_body(args)
    project_id = resolve_active_project_id(client, args.project_id)
    path = f"/projects/{project_id}/findings"
    method = "POST"
    if args.finding_command == "edit":
        method = "PATCH"
        path += f"/{args.finding_id}"
    elif args.finding_command != "create":
        raise DarklabCliError("unknown finding command")
    try:
        payload = client.request(method, path, body=body)
    except DarklabCliError as exc:
        actionable = _actionable_error(exc)
        if actionable is exc:
            raise
        raise actionable from exc
    if args.format == "json":
        return print_payload(payload, "json")
    finding = payload.get("finding") if isinstance(payload, dict) else None
    if not isinstance(finding, dict):
        raise DarklabCliError("finding mutation response is invalid")
    print_table([finding], ("id", "manual_revision", "severity", "title", "target_id"))
    if payload.get("duplicate_override"):
        print("Duplicate override: yes")
    return 0


__all__ = ["handle_finding"]
