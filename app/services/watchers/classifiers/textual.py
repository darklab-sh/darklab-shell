"""Textual watcher diff fallback."""

from __future__ import annotations

from typing import Any

from services.runs import comparison as run_comparison
from services.watchers.classifiers import register_classifier
from services.watchers.models import DIFF_KIND_NONE, DIFF_KIND_TEXTUAL, WatcherDiff


def applies_to(_command_text: str, _run: dict[str, Any], _conn=None) -> bool:
    return True


@register_classifier("textual", applies_to=applies_to)
def diff(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    options: dict[str, bool] | None = None,
    _conn=None,
) -> WatcherDiff:
    left_entries, left_output = run_comparison.compare_entries_for_diff(baseline_run)
    right_entries, right_output = run_comparison.compare_entries_for_diff(current_run)
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
    return WatcherDiff(summary=summary, kind=kind, truncated=is_truncated)
