# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Revalidate reviewed Dalfox output before it becomes a saved finding."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from typing import Any

from core.output_targets import tokenize_command
from services.assessments.dalfox_parameter_evidence import (
    resolve_project_dalfox_parameter_evidence,
)
from services.assessments.dalfox_xss_command import reviewed_dalfox_xss_command_plan
from services.assessments.dalfox_xss_finding_persistence import persist_dalfox_xss_observations
from services.assessments.dalfox_xss_observations import DalfoxXssObservationState
from services.projects.scope import shared_owner_where


def materialize_dalfox_xss_findings(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    run_id: str,
    command: str,
    exit_code: int,
    entries: Sequence[object],
) -> list[dict[str, Any]]:
    """Save only output that still matches its exact Project-scoped launch evidence."""
    active_run = _active_run_row(
        conn, session_id, team_id, project_id, run_id, command, exit_code,
    )
    summary = _single_stored_summary(entries, run_id)
    if active_run is None or summary is None:
        return []
    target = str(summary.get("target") or "")
    evidence = resolve_project_dalfox_parameter_evidence(
        conn,
        session_id,
        team_id,
        project_id,
        str(summary.get("source_parameter_run_id") or ""),
        str(summary.get("source_parameter_observation_id") or ""),
        expected_target=target,
    )
    if evidence is None:
        return []
    plan = reviewed_dalfox_xss_command_plan(evidence)
    if plan is None or not _active_command_matches(command, plan.command):
        return []
    context = evidence.xss_context(request_limit=int(plan.request_limit or 0))
    if context is None:
        return []
    reviewed = _reparse_stored_output(entries, command, run_id, context)
    if reviewed is None:
        return []
    observations, line_numbers = reviewed
    entity = _owned_url_entity(conn, session_id, team_id, run_id, target)
    if entity is None:
        return []
    return persist_dalfox_xss_observations(
        conn,
        session_id,
        team_id,
        project_id,
        run_id,
        str(active_run["finished"] or ""),
        entity,
        observations,
        line_numbers,
        source_parameter_run_id=evidence.source_run_id,
    )


def _active_run_row(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    run_id: str,
    command: str,
    exit_code: int,
) -> Any | None:
    if int(exit_code) != 0:
        return None
    project_owner_sql, project_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p",
    )
    run_owner_sql, run_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="r",
    )
    # Owner predicates are fixed helper output; every value remains bound.
    sql = "".join((
        "SELECT r.id, r.command, r.finished, r.exit_code, r.output_line_count FROM projects p ",
        "JOIN project_links pl ON pl.project_id = p.id AND pl.entity_type = 'run' ",
        "JOIN runs r ON r.id = pl.entity_id WHERE p.id = ? AND r.id = ? AND ",
        project_owner_sql,
        " AND ",
        run_owner_sql,
        " LIMIT 2",
    ))
    rows = conn.execute(
        sql,
        (project_id, run_id, *project_owner_params, *run_owner_params),
    ).fetchall()
    if len(rows) != 1:
        return None
    row = rows[0]
    return row if (
        str(row["command"] or "") == command
        and bool(row["finished"])
        and row["exit_code"] == 0
    ) else None


def _single_stored_summary(entries: Sequence[object], run_id: str) -> dict[str, Any] | None:
    summaries: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        detail = entry.get("source_detail")
        summary = detail.get("dalfox_xss_scan") if isinstance(detail, Mapping) else None
        if isinstance(summary, Mapping):
            summaries.append(dict(summary))
    if (
        len(summaries) != 1
        or str(summaries[0].get("source_run_id") or "") != run_id
        or summaries[0].get("truncated") is not False
    ):
        return None
    return summaries[0]


def _active_command_matches(command: str, expected: str) -> bool:
    actual_tokens = tokenize_command(command)
    expected_tokens = tokenize_command(expected)
    if actual_tokens == expected_tokens:
        return True
    trailing = actual_tokens[len(expected_tokens):]
    return (
        actual_tokens[:len(expected_tokens)] == expected_tokens
        and len(trailing) == 2
        and trailing[0] == "--config"
        and os.path.isabs(trailing[1])
        and not any(character in trailing[1] for character in ("\x00", "\r", "\n"))
    )


def _reparse_stored_output(
    entries: Sequence[object],
    command: str,
    run_id: str,
    context: Any,
) -> tuple[list[dict[str, Any]], list[int]] | None:
    state = DalfoxXssObservationState(command, run_id, context)
    observations: list[dict[str, Any]] = []
    line_numbers: list[int] = []
    for fallback_index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        expected = state.metadata(str(entry.get("text") or ""))
        expected_detail = expected.get("source_detail") if isinstance(expected, Mapping) else None
        stored_detail = entry.get("source_detail")
        expected_xss = _xss_detail(expected_detail)
        stored_xss = _xss_detail(stored_detail)
        if expected_xss != stored_xss:
            return None
        values = expected_xss.get("dalfox_xss_observations")
        if not isinstance(values, list):
            continue
        line_number = entry.get("line_index")
        line_number = line_number if isinstance(line_number, int) else fallback_index
        for value in values:
            if not isinstance(value, Mapping):
                return None
            observations.append(dict(value))
            line_numbers.append(line_number)
    if (
        not observations
        or len(observations) != len(line_numbers)
        or not state.complete_findings_stream(context)
    ):
        return None
    return observations, line_numbers


def _xss_detail(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: value[key]
        for key in ("dalfox_xss_scan", "dalfox_xss_observations")
        if key in value
    }


def _owned_url_entity(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    target: str,
) -> Any | None:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e",
    )
    sql = "".join((
        "SELECT e.id, e.type, e.canonical_value FROM entities e ",
        "JOIN entity_run_links link ON link.entity_id = e.id WHERE ",
        owner_sql,
        " AND e.type = 'url' AND e.canonical_value = ? AND link.run_id = ? LIMIT 2",
    ))
    rows = conn.execute(
        sql,
        (*owner_params, target, run_id),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


__all__ = ["materialize_dalfox_xss_findings"]
