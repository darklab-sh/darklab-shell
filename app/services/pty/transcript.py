"""Helpers for shaping completed interactive PTY transcripts."""

from __future__ import annotations

import re

_PTY_TRANSIENT_LINE_PATTERNS = (
    re.compile(r"^rate:\s+.*\bdone\b.*\bfound=\d+\b", re.IGNORECASE),
    re.compile(r"^::\s*Progress:\s*\[", re.IGNORECASE),
)


def normalize_pty_entry(entry) -> dict[str, str]:
    if isinstance(entry, dict):
        return {
            "text": str(entry.get("text", "")),
            "cls": str(entry.get("cls", "")),
        }
    return {"text": str(entry), "cls": ""}


def is_transient_pty_line(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    return any(pattern.search(value) for pattern in _PTY_TRANSIENT_LINE_PATTERNS)


def split_pty_entries(entries: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    marker_index = next(
        (index for index, entry in enumerate(entries) if entry.get("cls") == "pty-marker"),
        -1,
    )
    if marker_index < 0:
        return entries, []
    return entries[:marker_index], entries[marker_index + 1:]


def filter_transient_pty_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        entry for entry in entries
        if entry.get("cls") != "pty-marker" and not is_transient_pty_line(entry.get("text", ""))
    ]


def shape_completed_pty_entries(synthesized_lines, transcript_mode: object) -> list[dict[str, str]]:
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
