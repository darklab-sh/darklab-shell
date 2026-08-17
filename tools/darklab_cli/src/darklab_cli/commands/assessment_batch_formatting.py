# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Human-readable output for assessment-batch CLI commands."""

from __future__ import annotations

import json
from typing import Any

from ..formatting import print_table


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _count(value: object) -> int:
    try:
        return int(str(value or 0))
    except (TypeError, ValueError):
        return 0


def _duration(seconds: object) -> str:
    total = _count(seconds)
    if total < 60:
        return f"{total}s"
    minutes, remainder = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {remainder}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def print_batch_preview(preview: dict[str, Any], items: list[dict[str, Any]]) -> None:
    summary = _mapping(preview.get("summary"))
    profile = _mapping(preview.get("profile"))
    concurrency = _mapping(preview.get("concurrency"))
    print(f"Assessment batch preview: {preview.get('preview_id', '')}")
    print(f"Project: {preview.get('project_id', '')}")
    print(f"Assessment: {preview.get('assessment_id', '')}")
    if preview.get("source_batch_id"):
        print(f"Retry of: {preview.get('source_batch_id')}")
    print(f"Profile: {profile.get('key', '')} {profile.get('version', '')}".rstrip())
    print(
        "Selection: "
        f"{_count(preview.get('selected_item_count'))} commands across "
        f"{_count(summary.get('selected_target_count'))} targets; may cover "
        f"{_count(preview.get('potential_covered_check_count'))} checks"
    )
    print(
        "Estimate: "
        f"{_duration(summary.get('estimated_min_seconds'))} to "
        f"{_duration(summary.get('estimated_max_seconds'))} "
        "(planning estimate, not a completion promise)"
    )
    print(
        "Concurrency: "
        f"batch {concurrency.get('batch', '')}; target {concurrency.get('target', '')}; "
        f"owner {concurrency.get('owner', '')}; instance {concurrency.get('instance', '')}"
    )
    if summary.get("requires_standard_confirmation"):
        print("Policy: standard commands selected; separate confirmation required")
    reasons = _mapping(summary.get("reason_counts"))
    if reasons:
        rendered = ", ".join(f"{key}={value}" for key, value in sorted(reasons.items()))
        print(f"Skipped or unavailable: {rendered}")
    if summary.get("credentialed_work_remains_individual"):
        print("Credentials: protected HTTP-profile work remains individual")
    print(f"Approval digest: {str(preview.get('plan_digest') or '')[:12]}")
    selected = [item for item in items if item.get("selected")]
    if not selected:
        print("No selected commands.")
        return
    print("Commands:")
    for item in selected:
        target = _mapping(item.get("target"))
        action = _mapping(item.get("action"))
        print(
            f"  {item.get('item_index')}. [{item.get('policy_level', '')}] "
            f"{action.get('id', '')} -> {target.get('value', '')}"
        )
        print(f"     {item.get('display_command', '')}")


def batch_row(batch: dict[str, Any]) -> dict[str, Any]:
    progress = _mapping(batch.get("progress"))
    return {
        "batch_id": batch.get("batch_id"),
        "status": batch.get("status"),
        "items": batch.get("item_count"),
        "settled": progress.get("settled"),
        "succeeded": progress.get("succeeded"),
        "failed": progress.get("failed"),
        "unavailable": progress.get("unavailable"),
        "created": batch.get("created"),
    }


def print_batch_summary(batch: dict[str, Any]) -> None:
    print_table(
        [batch_row(batch)],
        ("batch_id", "status", "items", "settled", "succeeded", "failed", "unavailable", "created"),
    )
    failure_code = str(batch.get("failure_code") or "")
    if failure_code:
        print(f"Failure reason: {failure_code}")


def print_batch_items(page: dict[str, Any]) -> None:
    raw_values = page.get("items")
    values: list[object] = raw_values if isinstance(raw_values, list) else []
    rows: list[dict[str, Any]] = []
    for raw in values:
        if not isinstance(raw, dict):
            continue
        target = _mapping(raw.get("target"))
        rows.append({**raw, "target": target.get("value", "")})
    print_table(
        rows,
        ("item_index", "status", "attempt", "action_id", "target", "run_id", "reason_code"),
    )
    if page.get("has_more"):
        print(f"More items: --item-cursor {page.get('next_cursor')}")


def print_batch_event(event: dict[str, Any], *, ndjson: bool = False) -> None:
    if ndjson:
        print(json.dumps(event, sort_keys=True))
        return
    suffix = " ".join(
        value
        for value in (
            str(event.get("status") or ""),
            str(event.get("reason_code") or ""),
            str(event.get("run_id") or ""),
        )
        if value
    )
    print(
        f"[{event.get('sequence', '')}] {event.get('created', '')} "
        f"{event.get('event_type', '')}{(' ' + suffix) if suffix else ''}"
    )
__all__ = [
    "batch_row",
    "print_batch_event",
    "print_batch_items",
    "print_batch_preview",
    "print_batch_summary",
]
