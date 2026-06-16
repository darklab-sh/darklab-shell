"""Textual diff fallback."""

from __future__ import annotations

from typing import Any

from services.diff.classifiers import register_classifier
from services.diff.models import DIFF_KIND_NONE, DIFF_KIND_TEXTUAL, DiffResult
from services.runs import comparison as run_comparison


def applies_to(_command_text: str, _run: dict[str, Any], _conn=None) -> bool:
    return True


def _ignored_line_patterns(options: dict[str, Any] | None) -> list[str]:
    raw_patterns = (options or {}).get("ignore_line_patterns", [])
    if not isinstance(raw_patterns, list):
        return []
    patterns: list[str] = []
    for item in raw_patterns:
        pattern = str(item or "").strip()
        if pattern and pattern not in patterns:
            patterns.append(pattern)
    return patterns


def _filter_ignored_entries(entries: list[dict[str, Any]], patterns: list[str]) -> tuple[list[dict[str, Any]], int]:
    if not patterns:
        return entries, 0
    filtered = [
        entry for entry in entries
        if not any(pattern in str(entry.get("text") or "") for pattern in patterns)
    ]
    return filtered, len(entries) - len(filtered)


@register_classifier("textual", applies_to=applies_to)
def diff(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    options: dict[str, Any] | None = None,
    _conn=None,
) -> DiffResult:
    left_entries, left_output = run_comparison.compare_entries_for_diff(baseline_run)
    right_entries, right_output = run_comparison.compare_entries_for_diff(current_run)
    ignored_patterns = _ignored_line_patterns(options)
    left_entries, ignored_left = _filter_ignored_entries(left_entries, ignored_patterns)
    right_entries, ignored_right = _filter_ignored_entries(right_entries, ignored_patterns)
    hunk_diff = run_comparison.hunk_line_diff(
        left_entries,
        right_entries,
        max_changed_lines=1000,
        max_hunks=run_comparison.COMPARE_MAX_HUNKS,
        inline_context=run_comparison.COMPARE_INLINE_EQUAL_CONTEXT,
    )
    totals = dict(hunk_diff.get("totals") or {})
    entity_delta = run_comparison.compare_entity_sets(left_entries, right_entries)
    added = int(totals.get("added_line_count") or 0)
    removed = int(totals.get("removed_line_count") or 0)
    changed = int(totals.get("changed_line_count") or 0)
    raw_truncated = hunk_diff.get("truncated")
    truncated_info: dict[str, Any] = raw_truncated if isinstance(raw_truncated, dict) else {}
    lines_omitted = truncated_info.get("lines_omitted") if isinstance(truncated_info, dict) else {}
    omitted_total = int((lines_omitted or {}).get("total") or 0) if isinstance(lines_omitted, dict) else 0
    is_truncated = bool(
        left_output.get("partial")
        or right_output.get("partial")
        or int(truncated_info.get("hunks_omitted") or 0)
        or omitted_total
    )
    effective_removed = 0 if bool((options or {}).get("suppress_removals")) else removed
    effective_entity_removed = 0 if bool((options or {}).get("suppress_removals")) else len(entity_delta["removed"])
    summary = {
        "classifier": "textual",
        "added_line_count": added,
        "removed_line_count": removed,
        "changed_line_count": changed,
        "equal_line_count": int(totals.get("equal_line_count") or 0),
        "left_total_lines": int(totals.get("left_total_lines") or 0),
        "right_total_lines": int(totals.get("right_total_lines") or 0),
        "left_output_source": str(left_output.get("source") or ""),
        "right_output_source": str(right_output.get("source") or ""),
        "hunks_omitted": int(truncated_info.get("hunks_omitted") or 0),
        "lines_omitted": omitted_total,
        "ignored_line_pattern_count": len(ignored_patterns),
        "ignored_line_count": ignored_left + ignored_right,
        "suppressed_removed_line_count": removed - effective_removed,
        "entity_added_count": len(entity_delta["added"]),
        "entity_removed_count": len(entity_delta["removed"]),
        "suppressed_removed_entity_count": len(entity_delta["removed"]) - effective_entity_removed,
        "entity_unchanged_count": int(entity_delta.get("unchanged_count") or 0),
    }
    if entity_delta["added"] or entity_delta["removed"]:
        summary["entities"] = entity_delta
    has_entity_change = bool(entity_delta["added"] or effective_entity_removed)
    kind = DIFF_KIND_TEXTUAL if added or effective_removed or changed or has_entity_change else DIFF_KIND_NONE
    return DiffResult(summary=summary, kind=kind, truncated=is_truncated)
