# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared value formatting for human-readable probe output."""

from __future__ import annotations

from typing import Any


def list_values(value: Any) -> str:
    return ",".join(str(item) for item in value) if isinstance(value, list) else ""


def profile_summaries(raw_profiles: Any) -> str:
    profiles = raw_profiles if isinstance(raw_profiles, list) else []
    summaries = []
    for item in profiles:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        availability = item.get("availability")
        availability = availability if isinstance(availability, dict) else {}
        summary = str(item["key"])
        if availability.get("available") is False:
            reason = availability.get("reason") or availability.get("code") or "not available"
            summary += f" (unavailable: {reason})"
        summaries.append(summary)
    return ", ".join(summaries) or "none"


__all__ = ["list_values", "profile_summaries"]
