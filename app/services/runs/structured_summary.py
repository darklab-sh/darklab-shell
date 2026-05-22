"""Run-level indexes for structured output fields."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from services.runs.output_model import LineEvent, from_wire
from services.runs.output_store import unknown_line_event_collector


SUMMARY_FAMILY_KIND = "kind"
SUMMARY_FAMILY_ROLE = "role"
SUMMARY_FAMILY_SIGNAL = "signal"
SUMMARY_FAMILIES = frozenset({SUMMARY_FAMILY_KIND, SUMMARY_FAMILY_ROLE, SUMMARY_FAMILY_SIGNAL})


def summarize_events(events: Iterable[LineEvent]) -> dict[str, dict[str, int]]:
    summary: dict[str, Counter[str]] = {
        SUMMARY_FAMILY_KIND: Counter(),
        SUMMARY_FAMILY_ROLE: Counter(),
        SUMMARY_FAMILY_SIGNAL: Counter(),
    }
    for event in events:
        summary[SUMMARY_FAMILY_KIND][event.kind.value] += 1
        summary[SUMMARY_FAMILY_ROLE][event.role.value] += 1
        for signal in event.signals:
            summary[SUMMARY_FAMILY_SIGNAL][signal.value] += 1
    return {family: dict(counts) for family, counts in summary.items() if counts}


def summarize_entries(entries: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    events: list[LineEvent] = []
    unknown_collector = unknown_line_event_collector({"source": "run_output_summary"})
    for entry in entries:
        if isinstance(entry, Mapping):
            events.append(from_wire(entry, unknown_collector))
    return summarize_events(events)


def replace_run_output_summary(conn, run_id: str, entries: Iterable[Mapping[str, Any]]) -> None:
    run_id = str(run_id or "").strip()
    if not run_id:
        return
    summary = summarize_entries(entries)
    conn.execute("DELETE FROM run_output_summary WHERE run_id = ?", (run_id,))
    rows: list[tuple[str, str, str, int]] = []
    for family, counts in summary.items():
        for value, count in counts.items():
            if value and count:
                rows.append((run_id, family, value, int(count)))
    if not rows:
        return
    conn.executemany(
        "INSERT INTO run_output_summary (run_id, family, value, count) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (run_id, family, value) DO UPDATE SET count = excluded.count",
        rows,
    )
