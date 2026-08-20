# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Preview and start handlers for headless assessment batches."""

from __future__ import annotations

import argparse
from typing import Any

from ..client import DarklabClient, DarklabCliError, die
from ..formatting import print_payload
from .assessment_batch_formatting import print_batch_preview, print_batch_summary
from .assessment_batch_pages import preview_items
from .project_references import resolve_active_project_id


def _selection(args: argparse.Namespace) -> dict[str, object]:
    return {
        "target_entity_ids": list(args.target),
        "excluded_target_entity_ids": list(args.exclude_target),
        "categories": list(args.category),
        "excluded_categories": list(args.exclude_category),
        "include_standard": bool(args.include_standard),
        "item_limit": args.item_limit,
        "max_parallel": args.max_parallel,
        "max_owner_parallel": args.max_owner_parallel,
        "max_instance_parallel": args.max_instance_parallel,
    }


def _create_preview(
    client: DarklabClient, args: argparse.Namespace
) -> tuple[str, dict[str, Any], list[dict[str, Any]], str]:
    project_id = resolve_active_project_id(client, args.project_id)
    path = f"/projects/{project_id}/assessments/{args.assessment_id}"
    payload = client.request("POST", f"{path}/batch-previews", body=_selection(args))
    raw_preview = payload.get("preview") if isinstance(payload, dict) else None
    if not isinstance(raw_preview, dict):
        raise DarklabCliError("assessment batch preview response is invalid")
    preview: dict[str, Any] = raw_preview
    preview_id = str(preview.get("preview_id") or "")
    if not preview_id:
        raise DarklabCliError("assessment batch preview id is missing")
    return project_id, preview, preview_items(client, preview_id), path


def handle_batch_plan(client: DarklabClient, args: argparse.Namespace) -> int:
    _project_id, preview, items, _path = _create_preview(client, args)
    if args.format == "json":
        return print_payload({"preview": preview, "items": items}, "json")
    print_batch_preview(preview, items)
    return 0


def handle_batch_start(client: DarklabClient, args: argparse.Namespace) -> int:
    if args.confirm_standard and not args.include_standard:
        return die("--confirm-standard requires --include-standard")
    _project_id, preview, items, path = _create_preview(client, args)
    if args.format != "json":
        print_batch_preview(preview, items)
    if not args.confirm:
        if args.format == "json":
            print_payload({"preview": preview, "items": items, "started": False}, "json")
        else:
            print("Preview only. Re-run with --confirm to start this batch.")
        return 0
    raw_summary = preview.get("summary")
    summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
    if summary.get("requires_standard_confirmation") and not args.confirm_standard:
        return die(
            "standard-policy commands are selected; review the preview and add "
            "--confirm-standard"
        )
    result = client.request(
        "POST",
        f"{path}/assessment-batches",
        body={
            "preview_id": str(preview.get("preview_id") or ""),
            "plan_digest": str(preview.get("plan_digest") or ""),
            "confirmed": True,
            "standard_confirmed": bool(args.confirm_standard),
        },
    )
    if args.format == "json":
        return print_payload(result, "json")
    batch = result.get("batch") if isinstance(result, dict) else None
    if not isinstance(batch, dict):
        raise DarklabCliError("assessment batch start response is invalid")
    print("Batch started:")
    print_batch_summary(batch)
    print(f"Follow progress: darklab assessment batch follow {batch.get('batch_id', '')}")
    return 0


__all__ = ["handle_batch_plan", "handle_batch_start"]
