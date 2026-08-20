# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read, follow, and cancellation handlers for assessment batches."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from ..client import DarklabClient, DarklabCliError
from ..formatting import print_payload, print_table
from .assessment_batch_formatting import (
    batch_row,
    print_batch_event,
    print_batch_items,
    print_batch_summary,
)
from .assessment_batch_pages import batch_event_page, batch_item_page
from .project_references import resolve_active_project_id


_TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})
BATCH_PARTIAL_EXIT_CODE = 3
BATCH_CANCELED_EXIT_CODE = 4


def _batch(client: DarklabClient, batch_id: str) -> dict[str, Any]:
    payload = client.request("GET", f"/assessment-batches/{batch_id}")
    raw = payload.get("batch") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        raise DarklabCliError("assessment batch response is invalid")
    return raw


def _events(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw_events = page.get("events")
    if not isinstance(raw_events, list):
        raise DarklabCliError("assessment batch returned an invalid event page")
    if any(not isinstance(event, dict) for event in raw_events):
        raise DarklabCliError("assessment batch returned an invalid event")
    return raw_events


def _print_events(page: dict[str, Any], cursor: int, *, ndjson: bool) -> int:
    for event in _events(page):
        print_batch_event(event, ndjson=ndjson)
        try:
            cursor = max(cursor, int(str(event.get("sequence") or 0)))
        except (TypeError, ValueError) as exc:
            raise DarklabCliError("assessment batch event sequence is invalid") from exc
    return cursor


def _terminal_exit_code(batch: dict[str, Any]) -> int:
    status = str(batch.get("status") or "")
    if status == "failed":
        return 1
    if status == "canceled":
        return BATCH_CANCELED_EXIT_CODE
    progress = batch.get("progress")
    counts = progress if isinstance(progress, dict) else {}
    try:
        incomplete = sum(
            int(str(counts.get(key) or 0))
            for key in ("failed", "unavailable", "canceled", "skipped", "could_not_cancel")
        )
    except ValueError as exc:
        raise DarklabCliError("assessment batch progress is invalid") from exc
    return BATCH_PARTIAL_EXIT_CODE if incomplete else 0


def handle_batch_list(client: DarklabClient, args: argparse.Namespace) -> int:
    project_id = resolve_active_project_id(client, args.project_id)
    payload = client.request(
        "GET",
        f"/projects/{project_id}/assessment-batches",
        params={
            "assessment_id": args.assessment_id,
            "cursor": args.cursor,
            "limit": args.limit,
        },
    )
    batches = payload.get("batches") if isinstance(payload, dict) else None
    if not isinstance(batches, list) or any(not isinstance(batch, dict) for batch in batches):
        raise DarklabCliError("assessment batch list response is invalid")
    values: list[dict[str, Any]] = batches
    if args.format == "json":
        return print_payload(payload, "json")
    if args.format == "ndjson":
        for batch in values:
            print(json.dumps(batch, sort_keys=True))
        return 0
    print_table(
        [batch_row(batch) for batch in values],
        ("batch_id", "status", "items", "settled", "succeeded", "failed", "created"),
    )
    if isinstance(payload, dict) and payload.get("has_more"):
        print(f"More batches: --cursor {payload.get('next_cursor')}")
    return 0


def handle_batch_show(client: DarklabClient, args: argparse.Namespace) -> int:
    batch = _batch(client, args.batch_id)
    item_page = (
        batch_item_page(client, args.batch_id, cursor=args.item_cursor, limit=args.limit)
        if args.items
        else None
    )
    event_page = (
        batch_event_page(client, args.batch_id, cursor=args.event_cursor, limit=args.limit)
        if args.events
        else None
    )
    if args.format == "json":
        result: dict[str, Any] = {"batch": batch}
        if item_page is not None:
            result["item_page"] = item_page
        if event_page is not None:
            result["event_page"] = event_page
        return print_payload(result, "json")
    print_batch_summary(batch)
    if item_page is not None:
        print("Items:")
        print_batch_items(item_page)
    if event_page is not None:
        print("Events:")
        for event in _events(event_page):
            print_batch_event(event)
        if event_page.get("has_more"):
            print(f"More events: --event-cursor {event_page.get('next_cursor')}")
    return 0


def handle_batch_follow(client: DarklabClient, args: argparse.Namespace) -> int:
    if not 0.1 <= args.poll_interval <= 60:
        raise DarklabCliError("poll interval must be between 0.1 and 60 seconds")
    cursor = args.cursor
    try:
        while True:
            page = batch_event_page(client, args.batch_id, cursor=cursor, limit=100)
            cursor = _print_events(page, cursor, ndjson=args.format == "ndjson")
            while page.get("has_more"):
                previous_cursor = cursor
                page = batch_event_page(client, args.batch_id, cursor=cursor, limit=100)
                cursor = _print_events(page, cursor, ndjson=args.format == "ndjson")
                if cursor <= previous_cursor:
                    raise DarklabCliError("assessment batch event cursor did not advance")
            batch = _batch(client, args.batch_id)
            if str(batch.get("status") or "") in _TERMINAL_STATUSES:
                if args.format == "ndjson":
                    print(json.dumps({"type": "summary", "batch": batch}, sort_keys=True))
                else:
                    print("Final status:")
                    print_batch_summary(batch)
                return _terminal_exit_code(batch)
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print(
            f"stopped following batch {args.batch_id}; resume with "
            f"`darklab assessment batch follow {args.batch_id} --cursor {cursor}`",
            file=sys.stderr,
        )
        return 130


def handle_batch_cancel(client: DarklabClient, args: argparse.Namespace) -> int:
    batch = _batch(client, args.batch_id)
    if not args.confirm:
        if args.format == "json":
            return print_payload({"batch": batch, "cancellation_requested": False}, "json")
        print_batch_summary(batch)
        print("Preview only. Re-run with --confirm to request cancellation.")
        return 0
    project_id = str(batch.get("project_id") or "")
    if not project_id:
        raise DarklabCliError("assessment batch Project id is missing")
    payload = client.request(
        "POST", f"/projects/{project_id}/assessment-batches/{args.batch_id}/cancel", body={}
    )
    if args.format == "json":
        return print_payload(payload, "json")
    canceled = payload.get("batch") if isinstance(payload, dict) else None
    if not isinstance(canceled, dict):
        raise DarklabCliError("assessment batch cancellation response is invalid")
    print("Cancellation requested:")
    print_batch_summary(canceled)
    return 0


__all__ = [
    "BATCH_CANCELED_EXIT_CODE",
    "BATCH_PARTIAL_EXIT_CODE",
    "handle_batch_cancel",
    "handle_batch_follow",
    "handle_batch_list",
    "handle_batch_show",
]
