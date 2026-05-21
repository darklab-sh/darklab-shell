"""Helpers for shaping completed interactive PTY transcripts."""

from __future__ import annotations

import re

from services.runs.output_model import LineRole, line_event_from_legacy, to_legacy_entry

_PTY_TRANSIENT_LINE_PATTERNS = (
    re.compile(r"^rate:\s+.*\bdone\b.*\bfound=\d+\b", re.IGNORECASE),
    re.compile(r"^::\s*Progress:\s*\[", re.IGNORECASE),
)


def normalize_pty_entry(entry) -> dict[str, object]:
    if isinstance(entry, dict):
        return to_legacy_entry(
            line_event_from_legacy(str(entry.get("text", "")), entry.get("cls", "")),
            include_timestamps=False,
        )
    return to_legacy_entry(line_event_from_legacy(str(entry)), include_timestamps=False)


def is_transient_pty_line(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    return any(pattern.search(value) for pattern in _PTY_TRANSIENT_LINE_PATTERNS)


def _entry_role(entry: dict[str, object]) -> LineRole:
    return line_event_from_legacy(str(entry.get("text", "")), entry.get("cls", "")).role


def _is_pty_marker_entry(entry: dict[str, object]) -> bool:
    return _entry_role(entry) == LineRole.pty_marker


def split_pty_entries(entries: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    marker_index = next(
        (index for index, entry in enumerate(entries) if _is_pty_marker_entry(entry)),
        -1,
    )
    if marker_index < 0:
        return entries, []
    return entries[:marker_index], entries[marker_index + 1:]


def filter_transient_pty_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        entry for entry in entries
        if not _is_pty_marker_entry(entry) and not is_transient_pty_line(str(entry.get("text", "")))
    ]


def shape_completed_pty_entries(synthesized_lines, transcript_mode: object) -> list[dict[str, object]]:
    mode = str(transcript_mode or "final_frame").strip().lower()
    entries = [normalize_pty_entry(item) for item in synthesized_lines]
    scrollback, final_frame = split_pty_entries(entries)
    if mode == "scrollback_findings":
        shaped = filter_transient_pty_entries(scrollback)
        if shaped:
            return shaped
        return filter_transient_pty_entries(final_frame or entries)
    if mode == "all_sanitized":
        return filter_transient_pty_entries(entries)
    return final_frame if final_frame else filter_transient_pty_entries(entries)
