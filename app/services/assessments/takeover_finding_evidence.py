# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded Project run evidence for takeover finding materialization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

TAKEOVER_EVIDENCE_MAX_RUNS = 256
TAKEOVER_EVIDENCE_MAX_EVENTS = 1_000
TAKEOVER_EVIDENCE_MAX_BYTES = 4 * 1024 * 1024


def project_takeover_evidence(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    current_run_id: str,
    current_entries: Sequence[object],
) -> dict[str, Any] | None:
    """Load complete preview evidence or reject instead of returning a partial set."""
    rows = _project_dns_rows(
        conn, session_id, team_id, project_id, current_run_id,
    )
    if len(rows) > TAKEOVER_EVIDENCE_MAX_RUNS:
        return None

    dns_events: list[dict[str, Any]] = []
    dns_rows: dict[str, dict[str, Any]] = {}
    allowed_runs = {str(current_run_id or "")}
    used_bytes = 0
    for row in rows:
        run_id = str(row["id"] or "")
        payload = str(row["output_preview"] or "[]")
        used_bytes += len(payload.encode("utf-8"))
        if used_bytes > TAKEOVER_EVIDENCE_MAX_BYTES:
            return None
        try:
            entries = json.loads(payload)
        except (TypeError, ValueError):
            return None
        if not isinstance(entries, list):
            return None
        allowed_runs.add(run_id)
        if not _collect_dns_events(entries, run_id, dns_events, dns_rows):
            return None

    if not _valid_current_entries(current_entries, str(current_run_id or "")):
        return None
    return {
        "allowed_run_ids": allowed_runs,
        "dns_events": dns_events,
        "dns_rows": dns_rows,
    }


def _project_dns_rows(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    current_run_id: str,
) -> list[Any]:
    tail = (
        " AND r.id != ? AND r.command LIKE 'dnsx %' "
        "ORDER BY COALESCE(r.finished, r.started) DESC, r.id DESC LIMIT ?"
    )
    prefix = (
        "SELECT r.id, r.output_preview FROM project_links link "
        "JOIN runs r ON r.id = link.entity_id "
        "WHERE link.project_id = ? AND link.entity_type = 'run' AND "
    )
    if team_id:
        return conn.execute(
            prefix + "r.team_id = ? AND r.team_id != ''" + tail,
            (project_id, team_id, current_run_id, TAKEOVER_EVIDENCE_MAX_RUNS + 1),
        ).fetchall()
    return conn.execute(
        prefix + "r.session_id = ? AND r.team_id = ''" + tail,
        (project_id, session_id, current_run_id, TAKEOVER_EVIDENCE_MAX_RUNS + 1),
    ).fetchall()


def _collect_dns_events(
    entries: Sequence[object],
    run_id: str,
    events: list[dict[str, Any]],
    rows: dict[str, dict[str, Any]],
) -> bool:
    for fallback_index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        detail = entry.get("source_detail")
        values = detail.get("takeover_observations") if isinstance(detail, Mapping) else None
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, Mapping) or str(value.get("source_run_id") or "") != run_id:
                return False
            observation_id = str(value.get("observation_id") or "")
            if not observation_id:
                return False
            line_number = entry.get("line_index")
            if not isinstance(line_number, int):
                line_number = fallback_index
            stored = {"observation": dict(value), "run_id": run_id, "line_number": line_number}
            if observation_id in rows and rows[observation_id] != stored:
                return False
            rows[observation_id] = stored
            events.append({"source_detail": {"takeover_observations": [dict(value)]}})
            if len(events) > TAKEOVER_EVIDENCE_MAX_EVENTS:
                return False
    return True


def _valid_current_entries(entries: Sequence[object], run_id: str) -> bool:
    if not run_id or isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        return False
    return len(entries) <= TAKEOVER_EVIDENCE_MAX_EVENTS


__all__ = [
    "TAKEOVER_EVIDENCE_MAX_BYTES",
    "TAKEOVER_EVIDENCE_MAX_EVENTS",
    "TAKEOVER_EVIDENCE_MAX_RUNS",
    "project_takeover_evidence",
]
