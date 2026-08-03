# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalized Intel freshness and Atlas overview fields."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


INTEL_FRESHNESS_FRESH = "fresh"
INTEL_FRESHNESS_STALE = "stale"
INTEL_FRESHNESS_UNKNOWN = "unknown"
INTEL_FRESHNESS_NOT_AVAILABLE = "not_available"


def _intel_provider_payload(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    provider = str(snapshot.get("provider") or "").strip().lower()
    data = snapshot.get("data") if isinstance(snapshot.get("data"), dict) else {}
    providers = data.get("providers") if isinstance(data, dict) else {}
    if not isinstance(providers, dict):
        return {}
    payload = providers.get(provider)
    if isinstance(payload, dict):
        return payload
    for key, value in providers.items():
        if str(key or "").strip().lower() == provider and isinstance(value, dict):
            return value
    return {}


def _snapshot_has_intel(snapshot: Mapping[str, Any]) -> bool:
    data = snapshot.get("data") if isinstance(snapshot.get("data"), dict) else {}
    summary = data.get("summary") if isinstance(data, dict) else None
    if isinstance(summary, dict):
        providers = summary.get("providers_with_data")
        if isinstance(providers, list) and providers:
            return True
        has_intel = summary.get("has_intel")
        if isinstance(has_intel, bool):
            return has_intel
    return bool(_intel_provider_payload(snapshot))


def _parse_expiry(value: object) -> datetime | None:
    rendered = str(value or "").strip().replace("Z", "+00:00")
    if not rendered:
        return None
    try:
        parsed = datetime.fromisoformat(rendered)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(rendered)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def intel_freshness(snapshots: Iterable[Mapping[str, Any]]) -> str:
    values = [snapshot.get("expires_at") for snapshot in snapshots if _snapshot_has_intel(snapshot)]
    if not values:
        return INTEL_FRESHNESS_NOT_AVAILABLE
    now = datetime.now(timezone.utc)
    states = []
    for value in values:
        expires_at = _parse_expiry(value)
        if expires_at is None:
            states.append(INTEL_FRESHNESS_UNKNOWN)
        elif expires_at < now:
            states.append(INTEL_FRESHNESS_STALE)
        else:
            states.append(INTEL_FRESHNESS_FRESH)
    if INTEL_FRESHNESS_FRESH in states:
        return INTEL_FRESHNESS_FRESH
    if states and all(state == INTEL_FRESHNESS_STALE for state in states):
        return INTEL_FRESHNESS_STALE
    return INTEL_FRESHNESS_UNKNOWN


def intel_overview(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": str(summary.get("status") or "none"),
        "freshness": str(summary.get("freshness") or INTEL_FRESHNESS_NOT_AVAILABLE),
        "snapshot_count": int(summary.get("snapshot_count") or 0),
        "provider_count": int(summary.get("provider_count") or 0),
        "providers_with_data": list(summary.get("providers_with_data") or []),
        "last_refresh_at": str(summary.get("last_refresh_at") or ""),
        "highlight_count": int(summary.get("highlight_count") or 0),
        "highlights": list(summary.get("highlights") or []),
        "summary": dict(summary),
    }
