# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Thin API v1 client commands for Project-scoped probes."""

from __future__ import annotations

import argparse
import re
from typing import Any

from ..client import DarklabClient, DarklabCliError
from ..formatting import print_payload, print_table
from .probe_formatting import print_probe_catalog, print_probe_plan

_PROJECT_ID_RE = re.compile(r"^prj_[A-Za-z0-9_-]{1,64}$")


def handle_probe(client: DarklabClient, args: argparse.Namespace) -> int:
    project_id = _resolve_project_id(client, args.project_id)
    base_path = f"/projects/{project_id}/probes"
    if args.probe_command == "list":
        payload = client.request(
            "GET", base_path,
            params={"service": args.service, "target_type": args.target_type},
        )
        if args.format == "json":
            return print_payload(payload, "json")
        print_probe_catalog(payload.get("catalog") if isinstance(payload, dict) else {})
        return 0

    entity_id = _resolve_entity_id(client, args, base_path)
    request_body = {
        "action_id": args.action_id,
        "entity_id": entity_id,
        **({"http_profile_id": args.http_profile_id} if args.http_profile_id else {}),
        **({"nmap_profile": args.nmap_profile} if args.nmap_profile else {}),
        "nuclei_profile": args.nuclei_profile,
    }
    preview = client.request("POST", f"{base_path}/plan", body=request_body)
    raw_plan = preview.get("plan") if isinstance(preview, dict) else {}
    plan: dict[str, Any] = raw_plan if isinstance(raw_plan, dict) else {}
    if args.probe_command == "plan" or not args.confirm:
        if args.format == "json":
            return print_payload(preview, "json")
        print_probe_plan(plan)
        if args.probe_command == "run":
            print("Preview only. Re-run with --confirm to start this probe.")
        return 0
    if not plan.get("launchable"):
        reason = str(plan.get("unavailable_reason") or "probe action is unavailable")
        raise DarklabCliError(reason)
    launched = client.request("POST", f"{base_path}/run", body={
        **request_body,
        "confirmed": True,
        "plan_digest": str(plan.get("plan_digest") or ""),
        **({"workspace_cwd": args.workspace_cwd} if args.workspace_cwd else {}),
    })
    if args.format == "json":
        return print_payload(launched, "json")
    run = launched.get("run") if isinstance(launched, dict) else {}
    if isinstance(run, dict):
        print_table([run], ("id", "status", "command", "history_url"))
    return 0


def _resolve_entity_id(client: DarklabClient, args: argparse.Namespace, base_path: str) -> str:
    entity_id = str(args.entity_id or "").strip()
    target_value = str(args.target_value or "").strip()
    if bool(entity_id) == bool(target_value):
        raise DarklabCliError("provide either TARGET or --entity-id, but not both")
    if entity_id:
        return entity_id
    payload = client.request(
        "POST", f"{base_path}/targets/resolve", body={"target_value": target_value},
    )
    target = payload.get("target") if isinstance(payload, dict) else {}
    resolved = str(target.get("entity_id") or "") if isinstance(target, dict) else ""
    if not resolved:
        raise DarklabCliError("the server didn't return a confirmed Project target id")
    return resolved


def _resolve_project_id(client: DarklabClient, project_ref: object) -> str:
    reference = str(project_ref or "").strip()
    if _PROJECT_ID_RE.fullmatch(reference):
        return reference
    offset = 0
    while True:
        payload = client.request("GET", "/projects", params={"limit": 100, "offset": offset})
        projects = payload.get("projects") if isinstance(payload, dict) else []
        if not isinstance(projects, list):
            break
        for project in projects:
            if not isinstance(project, dict):
                continue
            if (
                str(project.get("status") or "").casefold() == "active"
                and str(project.get("slug") or "").casefold() == reference.casefold()
            ):
                project_id = str(project.get("id") or "")
                if _PROJECT_ID_RE.fullmatch(project_id):
                    return project_id
        offset += len(projects)
        if not payload.get("has_more") or not projects:
            break
    raise DarklabCliError(f"active Project slug not found: {reference}")


__all__ = ["handle_probe"]
