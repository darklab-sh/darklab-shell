# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Thin API v1 client commands for Project-scoped probes."""

from __future__ import annotations

import argparse
from typing import Any

from ..client import DarklabClient, DarklabCliError
from ..formatting import print_payload, print_table


def handle_probe(client: DarklabClient, args: argparse.Namespace) -> int:
    base_path = f"/projects/{args.project_id}/probes"
    if args.probe_command == "list":
        payload = client.request(
            "GET", base_path,
            params={"service": args.service, "target_type": args.target_type},
        )
        if args.format == "json":
            return print_payload(payload, "json")
        _print_catalog(payload.get("catalog") if isinstance(payload, dict) else {})
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
        _print_plan(plan)
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

def _print_catalog(raw_catalog: Any) -> None:
    catalog = raw_catalog if isinstance(raw_catalog, dict) else {}
    raw_actions = catalog.get("actions")
    actions = raw_actions if isinstance(raw_actions, list) else []
    rows = []
    for raw_action in actions:
        if not isinstance(raw_action, dict):
            continue
        availability = raw_action.get("availability")
        availability = availability if isinstance(availability, dict) else {}
        raw_target_types = raw_action.get("target_types")
        target_types = raw_target_types if isinstance(raw_target_types, list) else []
        rows.append({
            "id": raw_action.get("id"),
            "policy": raw_action.get("policy_level"),
            "targets": ",".join(str(value) for value in target_types),
            "available": bool(availability.get("available")),
            "label": raw_action.get("label"),
        })
    print_table(rows, ("id", "policy", "targets", "available", "label"))
    raw_nmap_profiles = catalog.get("nmap_profiles")
    raw_nuclei_profiles = catalog.get("nuclei_profiles")
    nmap_profiles = raw_nmap_profiles if isinstance(raw_nmap_profiles, list) else []
    nuclei_profiles = raw_nuclei_profiles if isinstance(raw_nuclei_profiles, list) else []
    print(f"Nmap profiles: {_profile_keys(nmap_profiles)}")
    print(f"Nuclei profiles: {_profile_keys(nuclei_profiles)}")


def _profile_keys(profiles: list[Any]) -> str:
    keys = [str(item.get("key") or "") for item in profiles if isinstance(item, dict)]
    return ", ".join(key for key in keys if key) or "none"


def _print_plan(plan: dict[str, Any]) -> None:
    raw_action = plan.get("action")
    raw_target = plan.get("target")
    raw_bounds = plan.get("bounds")
    raw_availability = plan.get("availability")
    raw_expected_evidence = plan.get("expected_evidence")
    action = raw_action if isinstance(raw_action, dict) else {}
    target = raw_target if isinstance(raw_target, dict) else {}
    bounds = raw_bounds if isinstance(raw_bounds, dict) else {}
    availability = raw_availability if isinstance(raw_availability, dict) else {}
    expected_evidence = raw_expected_evidence if isinstance(raw_expected_evidence, list) else []
    print_table([{
        "action": action.get("id"),
        "policy": plan.get("policy_level"),
        "target": f"{target.get('type') or ''}:{target.get('value') or ''}",
        "launchable": bool(plan.get("launchable")),
        "command": plan.get("display_command"),
    }], ("action", "policy", "target", "launchable", "command"))
    print(f"Bounds: {bounds.get('summary') or 'No command bounds available'}")
    print(f"Expected evidence: {', '.join(str(value) for value in expected_evidence) or 'run output'}")
    print(f"Approval digest: {str(plan.get('plan_digest') or '')[:12]}")
    if not availability.get("available"):
        print(f"Unavailable: {availability.get('reason') or availability.get('code') or 'not available'}")


__all__ = ["handle_probe"]
