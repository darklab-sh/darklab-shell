# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persisted finding identity, loading, and run-to-run comparison helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import re
from typing import Any, Mapping

from core.output_signals import strip_ansi_codes


MAX_COMPARE_ITEMS_PER_SIDE = 5000

_SEVERITY_WORD = r"info|low|medium|high|critical"
_BRACKETED_SEVERITY_RE = re.compile(rf"\[(?:{_SEVERITY_WORD})\]", re.I)
_KEYED_SEVERITY_RE = re.compile(
    rf"((?:\"severity\"|'severity'|\bseverity\b|\brisk\b)\s*[:=]\s*[\"']?)(?:{_SEVERITY_WORD})\b",
    re.I,
)
_PHRASE_SEVERITY_RE = re.compile(rf"\b(?:{_SEVERITY_WORD})\s+severity\b", re.I)
_TRUFFLEHOG_STATE_RE = re.compile(r"^(TruffleHog\s+)(?:verified|unknown|unverified)(\s+)", re.I)
_VULNERS_SCORE_RE = re.compile(
    r"^(?P<prefix>\|_?\s+\S+\s+)(?:10(?:\.0)?|[0-9](?:\.\d)?)(?P<suffix>\s+https://vulners\.com/\S+)",
    re.I,
)
_GROUPED_VULNERS_SCORE_RE = re.compile(
    r"(\b(?:max\s+)?CVSS score\s+)(?:10(?:\.0)?|[0-9](?:\.\d)?)",
    re.I,
)
_GROUPED_SEVERITY_RE = re.compile(rf"(\bseverity\s+)(?:{_SEVERITY_WORD})\b", re.I)


def compare_item_limit(limit=None) -> int:
    if limit is None:
        limit = MAX_COMPARE_ITEMS_PER_SIDE
    try:
        return max(0, int(limit))
    except (TypeError, ValueError):
        return MAX_COMPARE_ITEMS_PER_SIDE


def severity_neutral_signal_key(text: object) -> str:
    """Normalize only the source tokens currently used to derive severity."""
    normalized = strip_ansi_codes(str(text or "")).strip()
    normalized = _TRUFFLEHOG_STATE_RE.sub(r"\1<verification>\2", normalized)
    normalized = _VULNERS_SCORE_RE.sub(r"\g<prefix><score>\g<suffix>", normalized)
    normalized = _GROUPED_VULNERS_SCORE_RE.sub(r"\1<score>", normalized)
    normalized = _GROUPED_SEVERITY_RE.sub(r"\1<severity>", normalized)
    normalized = _BRACKETED_SEVERITY_RE.sub("[<severity>]", normalized)
    normalized = _KEYED_SEVERITY_RE.sub(r"\1<severity>", normalized)
    normalized = _PHRASE_SEVERITY_RE.sub("<severity> severity", normalized)
    return re.sub(r"\s+", " ", normalized).strip().lower()[:512]


def severity_neutral_subject_key(value: object) -> str:
    parts = str(value or "").strip().split(":", 2)
    if len(parts) == 3 and parts[0].lower() == "unscoped":
        parts[2] = severity_neutral_signal_key(parts[2])
    return ":".join(parts).lower()


def finding_comparison_key(*, tool_root: object, kind: object, subject_key: object, text: object) -> str:
    signal_key = severity_neutral_signal_key(text)
    if not signal_key:
        return ""
    raw = "\x1f".join((
        str(tool_root or "").strip().lower(),
        str(kind or "finding").strip().lower(),
        severity_neutral_subject_key(subject_key),
        signal_key,
    )).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _row_value(row: Mapping[str, Any], key: str, default: Any = "") -> Any:
    try:
        value = row[key]
    except (KeyError, TypeError):
        return default
    return default if value is None else value


def finding_compare_key(row: Mapping[str, Any]) -> str:
    stored = str(_row_value(row, "comparison_key") or "").strip()
    if stored.startswith("raw:"):
        parts = stored[4:].split("\x1f", 3)
        if len(parts) == 4:
            return finding_comparison_key(
                tool_root=parts[0],
                kind=parts[1],
                subject_key=parts[2],
                text=parts[3],
            )
    if stored:
        return stored
    return finding_comparison_key(
        tool_root=_row_value(row, "tool_root"),
        kind=_row_value(row, "kind", "finding"),
        subject_key=_row_value(row, "subject_key"),
        text=_row_value(row, "occurrence_snippet") or _row_value(row, "raw_line") or _row_value(row, "title"),
    )


def run_finding_compare_items(
    conn,
    owner_scope,
    run_id,
    *,
    include_line_number=False,
    include_created=False,
    limit=None,
):
    limit = compare_item_limit(limit)
    run_scope_sql, run_scope_params = owner_scope.predicate(table_alias="r")
    finding_scope_sql, finding_scope_params = owner_scope.predicate(table_alias="f")
    where_sql = (
        " WHERE fo.run_id = ? AND " + run_scope_sql + " AND " + finding_scope_sql  # nosec
    )
    params = (run_id, *run_scope_params, *finding_scope_params)
    total = conn.execute(
        "SELECT COUNT(*) AS count FROM findings_occurrences fo "  # nosec
        "JOIN findings f ON f.id = fo.finding_id JOIN runs r ON r.id = fo.run_id" + where_sql,
        params,
    ).fetchone()["count"]
    rows = conn.execute(
        "SELECT f.id, f.raw_line, f.title, f.fingerprint, f.status AS review_state, "  # nosec
        "f.tool_root, f.kind, f.subject_key, fo.observed_severity, fo.comparison_key, "
        "fo.snippet AS occurrence_snippet, fo.line_number, f.created "
        "FROM findings_occurrences fo JOIN findings f ON f.id = fo.finding_id "
        "JOIN runs r ON r.id = fo.run_id" + where_sql +
        " ORDER BY fo.line_number ASC, f.id ASC LIMIT ?",
        (*params, limit),
    ).fetchall()
    items = []
    for row in rows:
        comparison_key = finding_compare_key(row)
        item = {
            "key": comparison_key,
            "comparison_key": comparison_key,
            "id": row["id"],
            "title": row["title"] or "",
            "raw_line": row["occurrence_snippet"] or row["raw_line"] or "",
            "severity": row["observed_severity"] or "",
            "review_state": row["review_state"] or "",
        }
        if include_line_number:
            item["line_number"] = row["line_number"]
        if include_created:
            item["created"] = row["created"]
        items.append(item)
    total = int(total or 0)
    return items, total, total > len(items)


def _generic_compare(items_left: list[dict[str, Any]], items_right: list[dict[str, Any]]) -> dict[str, Any]:
    def item_key(item):
        return str(item.get("key") or item.get("fingerprint") or item.get("id") or "")
    left_counts = Counter(item_key(item) for item in items_left if item_key(item))
    right_counts = Counter(item_key(item) for item in items_right if item_key(item))
    def collect(source, remaining):
        seen = Counter()
        result = []
        for item in source:
            key = item_key(item)
            if key and remaining[key] > seen[key]:
                seen[key] += 1
                result.append(item)
        return result
    return {
        "added": collect(items_right, right_counts - left_counts),
        "removed": collect(items_left, left_counts - right_counts),
        "unchanged_count": sum((left_counts & right_counts).values()),
    }


def compare_finding_items(left_items: list[dict[str, Any]], right_items: list[dict[str, Any]]) -> dict[str, Any]:
    left_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    right_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    left_fallback = []
    right_fallback = []
    key_order = []
    seen_keys = set()
    for source, grouped, fallback in (
        (left_items, left_by_key, left_fallback),
        (right_items, right_by_key, right_fallback),
    ):
        for item in source:
            key = str(item.get("comparison_key") or "")
            if not key:
                fallback.append(item)
                continue
            grouped[key].append(item)
            if key not in seen_keys:
                seen_keys.add(key)
                key_order.append(key)
    added = []
    removed = []
    changed = []
    unchanged_count = 0
    for key in key_order:
        left_rows = list(left_by_key.get(key, []))
        right_rows = list(right_by_key.get(key, []))
        exact = Counter(str(row.get("severity") or "") for row in left_rows)
        exact &= Counter(str(row.get("severity") or "") for row in right_rows)
        def unmatched(rows):
            remaining_matches = exact.copy()
            result = []
            for row in rows:
                severity = str(row.get("severity") or "")
                if remaining_matches[severity]:
                    remaining_matches[severity] -= 1
                else:
                    result.append(row)
            return result
        unmatched_left = unmatched(left_rows)
        unmatched_right = unmatched(right_rows)
        unchanged_count += sum(exact.values())
        pair_count = min(len(unmatched_left), len(unmatched_right))
        for index in range(pair_count):
            changed.append({
                "key": key,
                "before": unmatched_left[index],
                "after": unmatched_right[index],
                "changed_fields": ["severity"],
            })
        removed.extend(unmatched_left[pair_count:])
        added.extend(unmatched_right[pair_count:])

    fallback_diff = _generic_compare(left_fallback, right_fallback)
    return {
        "added": [*added, *fallback_diff["added"]],
        "removed": [*removed, *fallback_diff["removed"]],
        "changed": changed,
        "unchanged_count": unchanged_count + int(fallback_diff["unchanged_count"]),
    }
