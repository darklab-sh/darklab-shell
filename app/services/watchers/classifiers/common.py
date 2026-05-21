"""Shared helpers for watcher diff classifiers."""

from __future__ import annotations

from collections import Counter
import re
import shlex
from typing import Any

from core.output_signals import strip_ansi_codes
from services.runs import comparison as run_comparison

MAX_CHANGED_SIGNALS = 1000


def command_root(command_text: str) -> str:
    raw = str(command_text or "").strip()
    if not raw:
        return ""
    try:
        return shlex.split(raw)[0].lower()
    except ValueError:
        return raw.split()[0].lower() if raw.split() else ""


def normalized_lines(run: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    entries, output_info = run_comparison.compare_entries_for_diff(run)
    lines = [strip_ansi_codes(str(entry.get("text") or "")).strip() for entry in entries]
    return [line for line in lines if line], output_info


def list_delta(left_items: list[dict[str, Any]], right_items: list[dict[str, Any]], *, key: str = "key") -> dict[str, Any]:
    left_counts = Counter(str(item.get(key) or "") for item in left_items if str(item.get(key) or ""))
    right_counts = Counter(str(item.get(key) or "") for item in right_items if str(item.get(key) or ""))
    added_remaining = right_counts - left_counts
    removed_remaining = left_counts - right_counts

    def _collect(items: list[dict[str, Any]], remaining: Counter[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: Counter[str] = Counter()
        for item in items:
            item_key = str(item.get(key) or "")
            if not item_key or remaining[item_key] <= seen[item_key]:
                continue
            seen[item_key] += 1
            if len(rows) < MAX_CHANGED_SIGNALS:
                rows.append(item)
        return rows

    added = _collect(right_items, added_remaining)
    removed = _collect(left_items, removed_remaining)
    added_count = sum(added_remaining.values())
    removed_count = sum(removed_remaining.values())
    return {
        "added": added,
        "removed": removed,
        "added_count": added_count,
        "removed_count": removed_count,
        "unchanged_count": sum((left_counts & right_counts).values()),
        "truncated": added_count + removed_count > len(added) + len(removed),
    }


def host_from_text(text: str) -> str:
    raw = str(text or "").strip().lower()
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    raw = raw.rsplit("@", 1)[-1]
    if raw.startswith("[") and "]" in raw:
        raw = raw[1:raw.index("]")]
    elif ":" in raw:
        raw = raw.split(":", 1)[0]
    raw = raw.strip(".")
    return raw if re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,251}\.[a-z]{2,63}", raw) else ""
