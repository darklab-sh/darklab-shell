# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded paging helpers for headless assessment-batch commands."""

from __future__ import annotations

from typing import Any

from ..client import DarklabClient, DarklabCliError


def preview_items(client: DarklabClient, preview_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = 0
    while True:
        page = client.request(
            "GET",
            f"/assessment-batch-previews/{preview_id}/items",
            params={"cursor": cursor, "limit": 100},
        )
        values = page.get("items") if isinstance(page, dict) else None
        if not isinstance(values, list):
            raise DarklabCliError("assessment batch preview returned an invalid item page")
        if any(not isinstance(item, dict) for item in values):
            raise DarklabCliError("assessment batch preview returned an invalid item")
        items.extend(values)
        if len(items) > 512:
            raise DarklabCliError("assessment batch preview exceeded the 512-item limit")
        next_cursor = page.get("next_cursor") if isinstance(page, dict) else None
        if next_cursor is None:
            return items
        try:
            normalized = int(next_cursor)
        except (TypeError, ValueError) as exc:
            raise DarklabCliError("assessment batch preview returned an invalid cursor") from exc
        if normalized <= cursor or normalized > 512:
            raise DarklabCliError("assessment batch preview cursor did not advance")
        cursor = normalized


def batch_item_page(
    client: DarklabClient, batch_id: str, *, cursor: int, limit: int
) -> dict[str, Any]:
    payload = client.request(
        "GET",
        f"/assessment-batches/{batch_id}/items",
        params={"cursor": cursor, "limit": limit},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise DarklabCliError("assessment batch returned an invalid item page")
    return payload


def batch_event_page(
    client: DarklabClient, batch_id: str, *, cursor: int, limit: int
) -> dict[str, Any]:
    payload = client.request(
        "GET",
        f"/assessment-batches/{batch_id}/events",
        params={"cursor": cursor, "limit": limit},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise DarklabCliError("assessment batch returned an invalid event page")
    return payload


__all__ = ["batch_event_page", "batch_item_page", "preview_items"]
