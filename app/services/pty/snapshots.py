"""PTY snapshot payload shaping helpers."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from services.runs.output_model import LineKind, from_wire, line_event_from_legacy, to_wire
from services.runs.output_store import unknown_line_event_collector
from services.pty.settings import _pty_snapshot_fallback_entry_limit

_PTY_SNAPSHOT_UNKNOWN_COLLECTOR = unknown_line_event_collector({"source": "pty_snapshot"})


def pty_snapshot_wire_entry(entry: object) -> dict[str, object]:
    if isinstance(entry, dict):
        return to_wire(from_wire(entry, _PTY_SNAPSHOT_UNKNOWN_COLLECTOR))
    return to_wire(line_event_from_legacy(str(entry)))


def pty_snapshot_wire_entries(entries: Sequence[object]) -> list[dict[str, object]]:
    return [pty_snapshot_wire_entry(entry) for entry in entries]


def limited_snapshot_entries(entries: Sequence[dict[str, object]], ansi_snapshot: str) -> list[dict[str, object]]:
    if ansi_snapshot:
        return []
    fallback_entry_limit = _pty_snapshot_fallback_entry_limit()
    if len(entries) <= fallback_entry_limit:
        return pty_snapshot_wire_entries(entries)
    return [
        to_wire(
            line_event_from_legacy(
                "[earlier PTY snapshot entries omitted; terminal snapshot resumes visually]",
                kind=LineKind.notice,
            ),
        ),
        *pty_snapshot_wire_entries(entries[-fallback_entry_limit:]),
    ]


def pty_snapshot_payload_from_run(run: Any, *, distributed: bool = False) -> dict[str, Any]:
    entries = run.terminal_capture.synthesize_entries()
    ansi_snapshot, snapshot_truncated = run.terminal_capture.ansi_snapshot()
    # Redis snapshots omit fallback entries when ANSI is available to keep the
    # distributed payload bounded; local snapshots keep both for direct callers.
    payload: dict[str, Any] = {
        "run_id": run.run_id,
        "command": run.command,
        "started": run.started,
        "rows": run.rows,
        "cols": run.cols,
        "after_event_id": run.capture_event_id,
        "entries": limited_snapshot_entries(entries, ansi_snapshot) if distributed else pty_snapshot_wire_entries(entries),
        "snapshot_format": "ansi" if ansi_snapshot else "plain",
        "ansi_snapshot": ansi_snapshot,
        "snapshot_truncated": snapshot_truncated,
    }
    if distributed:
        payload["session_id"] = run.session_id
        payload["team_id"] = run.team_id
        payload["created_at"] = time.time()
    return payload
