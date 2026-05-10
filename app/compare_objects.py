"""Shared object comparison helpers for run comparison responses."""

import re
from collections import Counter

from output_signals import strip_ansi_codes

MAX_COMPARE_ITEMS_PER_SIDE = 5000


def compare_item_limit(limit=None):
    if limit is None:
        limit = MAX_COMPARE_ITEMS_PER_SIDE
    try:
        return max(0, int(limit))
    except (TypeError, ValueError):
        return MAX_COMPARE_ITEMS_PER_SIDE


def finding_compare_key(row):
    for value in (row["raw_line"], row["title"]):
        normalized = re.sub(r"\s+", " ", strip_ansi_codes(str(value or ""))).strip()
        if normalized:
            return normalized
    return row["fingerprint"] or ""


def run_finding_compare_items(
    conn,
    session_id,
    run_id,
    *,
    include_line_number=False,
    include_created=False,
):
    limit = compare_item_limit()
    total = conn.execute(
        "SELECT COUNT(*) AS count FROM findings WHERE session_id = ? AND run_id = ?",
        (session_id, run_id),
    ).fetchone()["count"]
    rows = conn.execute(
        "SELECT id, raw_line, title, severity, fingerprint, review_state, line_number, created "
        "FROM findings WHERE session_id = ? AND run_id = ? ORDER BY created ASC, id ASC LIMIT ?",
        (session_id, run_id, limit),
    ).fetchall()
    items = []
    for row in rows:
        item = {
            "key": finding_compare_key(row),
            "id": row["id"],
            "title": row["title"] or "",
            "raw_line": row["raw_line"] or "",
            "severity": row["severity"] or "",
            "review_state": row["review_state"] or "",
        }
        if include_line_number:
            item["line_number"] = row["line_number"]
        if include_created:
            item["created"] = row["created"]
        items.append(item)
    total = int(total or 0)
    return items, total, total > len(items)


def run_artifact_compare_items(
    conn,
    session_id,
    run_id,
    *,
    include_display_name=False,
    include_created=False,
):
    limit = compare_item_limit()
    total = conn.execute(
        "SELECT COUNT(*) AS count FROM run_file_artifacts WHERE session_id = ? AND run_id = ?",
        (session_id, run_id),
    ).fetchone()["count"]
    rows = conn.execute(
        "SELECT id, workspace_path, display_name, kind, byte_size, detected_by, content_sha256, created "
        "FROM run_file_artifacts WHERE session_id = ? AND run_id = ? ORDER BY created ASC, id ASC LIMIT ?",
        (session_id, run_id, limit),
    ).fetchall()
    items = []
    for row in rows:
        item = {
            "key": row["content_sha256"] or row["workspace_path"] or row["id"],
            "id": row["id"],
            "workspace_path": row["workspace_path"] or "",
            "kind": row["kind"] or "",
            "byte_size": row["byte_size"],
            "detected_by": row["detected_by"] or "",
            "content_sha256": row["content_sha256"] or "",
        }
        if include_display_name:
            item["display_name"] = row["display_name"] or ""
        if include_created:
            item["created"] = row["created"]
        items.append(item)
    total = int(total or 0)
    return items, total, total > len(items)


def compare_items(left_items, right_items):
    left_counts = Counter(item["key"] for item in left_items if item.get("key"))
    right_counts = Counter(item["key"] for item in right_items if item.get("key"))
    added_remaining = right_counts - left_counts
    removed_remaining = left_counts - right_counts

    def _collect(source_items, remaining):
        rows = []
        seen = Counter()
        for item in source_items:
            key = item.get("key")
            if not key or remaining[key] <= seen[key]:
                continue
            seen[key] += 1
            rows.append(item)
        return rows

    return {
        "added": _collect(right_items, added_remaining),
        "removed": _collect(left_items, removed_remaining),
        "unchanged_count": sum((left_counts & right_counts).values()),
    }
