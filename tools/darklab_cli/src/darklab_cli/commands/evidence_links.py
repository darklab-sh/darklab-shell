# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""List, link, and unlink typed Project finding evidence."""

from __future__ import annotations

import argparse
from typing import Any

from ..client import DarklabClient, DarklabCliError
from ..formatting import print_collection, print_payload, print_table
from .project_references import resolve_active_project_id


_EVIDENCE_FIELDS = (
    "id",
    "evidence_type",
    "evidence_id",
    "line_number",
    "source_state",
    "label",
)


def _actionable_error(exc: DarklabCliError) -> DarklabCliError:
    if exc.code != "team_forbidden":
        return exc
    return DarklabCliError(
        "Finding evidence changes require the TRIAGE_FINDINGS capability for the selected team.",
        status=exc.status,
        code=exc.code,
        details=exc.details,
    )


def _link_body(args: argparse.Namespace) -> dict[str, Any]:
    run_line = args.evidence_type == "run_line"
    if run_line and (args.line_number is None or args.line_number < 0):
        raise DarklabCliError("run_line evidence requires a zero-based --line-number")
    if not run_line and args.line_number is not None:
        raise DarklabCliError("--line-number is only valid for run_line evidence")
    if not run_line and args.snippet is not None:
        raise DarklabCliError("--snippet is only valid for run_line evidence")
    return {
        "evidence_type": args.evidence_type,
        "evidence_id": args.evidence_id,
        **({"line_number": args.line_number} if args.line_number is not None else {}),
        **({"snippet": args.snippet} if args.snippet is not None else {}),
    }


def handle_finding_evidence(client: DarklabClient, args: argparse.Namespace) -> int:
    body = _link_body(args) if args.evidence_command == "link" else None
    if args.evidence_command not in {"list", "link", "unlink"}:
        raise DarklabCliError("unknown finding evidence command")
    project_id = resolve_active_project_id(client, args.project_id)
    path = f"/projects/{project_id}/findings/{args.finding_id}/evidence"
    if args.evidence_command == "list":
        payload = client.request("GET", path)
        return print_collection(payload, "evidence", args.format, fields=_EVIDENCE_FIELDS)
    method = "POST"
    if args.evidence_command == "unlink":
        method = "DELETE"
        path += f"/{args.evidence_link_id}"
    try:
        payload = client.request(method, path, body=body)
    except DarklabCliError as exc:
        actionable = _actionable_error(exc)
        if actionable is exc:
            raise
        raise actionable from exc
    if args.format == "json":
        return print_payload(payload, "json")
    evidence = payload.get("evidence") if isinstance(payload, dict) else None
    if not isinstance(evidence, dict):
        raise DarklabCliError("finding evidence mutation response is invalid")
    if args.evidence_command == "link" and payload.get("created") is False:
        print("Evidence link already exists; no changes were made.")
    elif args.evidence_command == "link":
        print("Evidence linked.")
    else:
        print("Evidence link removed.")
    print_table([evidence], _EVIDENCE_FIELDS)
    return 0


__all__ = ["handle_finding_evidence"]
