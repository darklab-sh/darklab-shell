# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment-cycle command handlers for the headless CLI."""

from __future__ import annotations

import argparse
from typing import Any

from ..client import DarklabClient, die
from ..formatting import print_collection, print_payload, print_table


def handle_assessment(client: DarklabClient, args: argparse.Namespace) -> int:
    base_path = f"/projects/{args.project_id}/assessments"
    match args.assessment_command:
        case "list":
            payload = client.request("GET", base_path, params={
                "limit": args.limit, "offset": args.offset, "status": args.status,
                "include_archived": args.include_archived or args.status == "archived",
            })
            return print_collection(
                payload, "assessments", args.format,
                fields=("id", "status", "profile_key", "profile_version", "title"),
            )
        case "show":
            payload = client.request("GET", f"{base_path}/{args.assessment_id}")
            if args.format == "json":
                return print_payload(payload, "json")
            assessment = payload.get("assessment") if isinstance(payload, dict) else {}
            rollup = payload.get("rollup") if isinstance(payload, dict) else {}
            if isinstance(assessment, dict):
                print_table([assessment], ("id", "status", "profile_key", "profile_version", "title"))
            if isinstance(rollup, dict):
                print_table(
                    [rollup],
                    ("applicable_checks", "covered_checks", "checks_awaiting_review", "untested_checks"),
                )
            return 0
        case "checks":
            payload = client.request("GET", f"{base_path}/{args.assessment_id}", params={
                "limit": args.limit, "offset": args.offset, "category": args.category,
                "state": args.state, "target_type": args.target_type,
                "policy_level": args.policy_level, "evidence_state": args.evidence_state,
            })
            checks_page = payload.get("checks") if isinstance(payload, dict) else {}
            return print_collection(
                checks_page if isinstance(checks_page, dict) else {}, "checks", args.format,
                fields=("id", "state", "policy_level", "category", "target_type", "target_value", "check_key"),
            )
        case "set-state" | "clear-state":
            state = args.state if args.assessment_command == "set-state" else "not_started"
            reason = args.reason if args.assessment_command == "set-state" else ""
            payload = client.request(
                "PATCH", f"{base_path}/{args.assessment_id}/checks/{args.check_id}",
                body={"state": state, "reason": reason},
            )
            if args.format == "json":
                return print_payload(payload, "json")
            check = payload.get("check") if isinstance(payload, dict) else {}
            if isinstance(check, dict):
                print_table([check], ("id", "state", "state_source", "state_reason", "check_key"))
            return 0
        case "start-action":
            return _start_action(client, args, base_path)
    return die("unknown assessment command")


def _start_action(client: DarklabClient, args: argparse.Namespace, base_path: str) -> int:
    action_path = f"{base_path}/{args.assessment_id}/checks/{args.check_id}/recommended-action"
    selections = {
        key: value for key, value in {
            "http_profile_id": args.http_profile_id,
            "source_run_id": args.source_run_id,
            "parameter_observation_id": args.parameter_observation_id,
            "schema_artifact_id": args.schema_artifact_id,
        }.items() if value}
    preview = client.request("GET", action_path, params=selections or None)
    plan = preview.get("plan") if isinstance(preview, dict) and isinstance(preview.get("plan"), dict) else {}
    if not args.confirm:
        if args.format == "json":
            return print_payload(preview, "json")
        print_assessment_action_plan(plan)
        print("Preview only. Re-run with --confirm to start this action.")
        return 0
    if args.format != "json":
        print_assessment_action_plan(plan)
    if not plan.get("launchable"):
        return die(str(plan.get("unavailable_reason") or "assessment action is unavailable"))
    payload = client.request("POST", action_path, body={
        "confirmed": True, "plan_digest": str(plan.get("plan_digest") or ""),
        **selections,
        **({"workspace_cwd": args.workspace_cwd} if args.workspace_cwd else {}),
    })
    if args.format == "json":
        return print_payload(payload, "json")
    run = payload.get("run") if isinstance(payload, dict) else {}
    if isinstance(run, dict):
        print_table([run], ("id", "status", "command"))
    return 0


def print_assessment_action_plan(plan: dict[str, Any]) -> None:
    raw_target = plan.get("target")
    raw_action = plan.get("action")
    raw_http_profile = plan.get("http_profile")
    target = raw_target if isinstance(raw_target, dict) else {}
    action = raw_action if isinstance(raw_action, dict) else {}
    http_profile = raw_http_profile if isinstance(raw_http_profile, dict) else {}
    print_table([{
        "action": action.get("key") or "", "policy": plan.get("policy_level") or "",
        "target": f"{target.get('type') or ''}:{target.get('value') or ''}",
        "http_profile": http_profile.get("name") or "None",
        "launchable": bool(plan.get("launchable")), "command": plan.get("display_command") or "",
    }], ("action", "policy", "target", "http_profile", "launchable", "command"))


__all__ = ["handle_assessment", "print_assessment_action_plan"]
