# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Preview and start immutable assessment-batch retries."""

from __future__ import annotations

import argparse
from typing import Any

from ..client import DarklabClient, DarklabCliError, die
from ..formatting import print_payload
from .assessment_batch_formatting import print_batch_preview, print_batch_summary
from .assessment_batch_pages import preview_items
from .assessment_batch_preview import _selection


def _source_batch(client: DarklabClient, batch_id: str) -> dict[str, Any]:
    payload = client.request("GET", f"/assessment-batches/{batch_id}")
    raw = payload.get("batch") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        raise DarklabCliError("assessment batch response is invalid")
    if not raw.get("project_id") or not raw.get("assessment_id"):
        raise DarklabCliError("assessment batch retry scope is missing")
    return raw


def _retry_preview(
    client: DarklabClient, args: argparse.Namespace
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    source = _source_batch(client, args.batch_id)
    path = (
        f"/projects/{source['project_id']}/assessment-batches/"
        f"{args.batch_id}"
    )
    payload = client.request(
        "POST", f"{path}/retry-previews", body=_selection(args)
    )
    raw = payload.get("preview") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        raise DarklabCliError("assessment batch retry preview response is invalid")
    preview: dict[str, Any] = raw
    preview_id = str(preview.get("preview_id") or "")
    if not preview_id:
        raise DarklabCliError("assessment batch retry preview id is missing")
    if str(preview.get("source_batch_id") or "") != args.batch_id:
        raise DarklabCliError("assessment batch retry preview lineage is invalid")
    return preview, preview_items(client, preview_id), path


def handle_batch_retry(client: DarklabClient, args: argparse.Namespace) -> int:
    if args.confirm_standard and not args.include_standard:
        return die("--confirm-standard requires --include-standard")
    preview, items, path = _retry_preview(client, args)
    if args.format != "json":
        print_batch_preview(preview, items)
    if not args.confirm:
        if args.format == "json":
            return print_payload(
                {"preview": preview, "items": items, "started": False}, "json"
            )
        print("Preview only. Re-run with --confirm to start this retry.")
        return 0
    summary = preview.get("summary")
    details: dict[str, Any] = summary if isinstance(summary, dict) else {}
    if details.get("requires_standard_confirmation") and not args.confirm_standard:
        return die(
            "standard-policy commands are selected; review the preview and add "
            "--confirm-standard"
        )
    if not int(preview.get("selected_item_count") or 0):
        return die("no failed or unfinished commands are currently retryable")
    result = client.request(
        "POST",
        f"{path}/retry",
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
        raise DarklabCliError("assessment batch retry response is invalid")
    print("Retry started:")
    print_batch_summary(batch)
    print(f"Follow progress: darklab assessment batch follow {batch.get('batch_id', '')}")
    return 0


__all__ = ["handle_batch_retry"]
