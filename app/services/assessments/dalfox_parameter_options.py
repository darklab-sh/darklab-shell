# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded saved-parameter choices for the reviewed Assessment XSS action."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.helpers import get_log_session_id
from services.assessments.command_modes import (
    DALFOX_PARAMETER_DISCOVERY_MODE,
    assessment_command_mode,
)
from services.assessments.dalfox_parameter_evidence import (
    DALFOX_PARAMETER_EVIDENCE_MAX_EVENTS,
    ReviewedDalfoxParameterEvidence,
    review_dalfox_parameter_events,
)
from services.assessments.dalfox_parameter_observations import (
    DalfoxParameterObservationState,
)
from services.projects.scope import shared_owner_where
from services.runs.output_store import load_run_output_events_for_run


DALFOX_PARAMETER_OPTION_MAX_RUNS = 100
DALFOX_PARAMETER_OPTION_MAX_ITEMS = 64


@dataclass(frozen=True)
class DalfoxParameterOptions:
    """Reviewed choices plus an explicit whole-catalog overflow state."""

    items: tuple[ReviewedDalfoxParameterEvidence, ...]
    overflow: bool = False

    def public_items(self) -> list[dict[str, str]]:
        return [{
            "source_run_id": item.source_run_id,
            "observation_id": item.observation_id,
            "parameter": item.parameter,
            "location": item.location,
            "tool_version": item.tool_version,
        } for item in self.items]

    def selected(self, source_run_id: str, observation_id: str) -> ReviewedDalfoxParameterEvidence | None:
        matches = [
            item for item in self.items
            if item.source_run_id == source_run_id and item.observation_id == observation_id
        ]
        return matches[0] if len(matches) == 1 else None


def list_project_dalfox_parameter_options(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    expected_target: str,
) -> DalfoxParameterOptions:
    """Return newest reviewed parameter identities for one exact Project URL."""
    rows = _candidate_run_rows(conn, session_id, team_id, project_id)
    if len(rows) > DALFOX_PARAMETER_OPTION_MAX_RUNS:
        return DalfoxParameterOptions((), overflow=True)
    items: list[ReviewedDalfoxParameterEvidence] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        run = dict(row)
        command = str(run.get("command") or "")
        state = DalfoxParameterObservationState(command, str(run.get("id") or ""))
        if (
            assessment_command_mode(command) != DALFOX_PARAMETER_DISCOVERY_MODE
            or state.target != expected_target
            or not _complete_run(run)
        ):
            continue
        loaded = load_run_output_events_for_run(run, failure_log_extra={
            "session": get_log_session_id(session_id),
            "team_id": str(team_id or "")[:64],
            "project_id": str(project_id or "")[:64],
            "evidence_kind": "dalfox_parameter_options",
        })
        if loaded.partial or len(loaded.events) > DALFOX_PARAMETER_EVIDENCE_MAX_EVENTS:
            continue
        for observation_id in _observation_ids(loaded.events):
            evidence = review_dalfox_parameter_events(
                loaded.events,
                str(run.get("id") or ""),
                observation_id,
                state.target,
                expected_target=expected_target,
            )
            if evidence is None:
                continue
            identity = (evidence.parameter, evidence.location)
            if identity in seen:
                continue
            seen.add(identity)
            items.append(evidence)
            if len(items) > DALFOX_PARAMETER_OPTION_MAX_ITEMS:
                return DalfoxParameterOptions((), overflow=True)
    return DalfoxParameterOptions(tuple(items))


def _candidate_run_rows(
    conn: Any, session_id: str, team_id: str, project_id: str,
) -> list[Any]:
    project_sql, project_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p",
    )
    run_sql, run_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="r",
    )
    sql = "".join((
        "SELECT r.id, r.run_kind, r.command, r.finished, r.exit_code, ",
        "r.output_preview, r.preview_truncated, r.full_output_available, ",
        "r.full_output_truncated, art.rel_path FROM projects p ",
        "JOIN project_links pl ON pl.project_id = p.id ",
        "JOIN runs r ON r.id = pl.entity_id ",
        "LEFT JOIN run_output_artifacts art ON art.run_id = r.id ",
        "WHERE p.id = ? AND pl.entity_type = 'run' AND LOWER(r.command) LIKE 'dalfox %' AND ",
        project_sql, " AND ", run_sql,
        " ORDER BY r.finished DESC, r.id DESC LIMIT ?",
    ))
    return conn.execute(sql, (
        project_id, *project_params, *run_params, DALFOX_PARAMETER_OPTION_MAX_RUNS + 1,
    )).fetchall()


def _complete_run(run: Mapping[str, Any]) -> bool:
    return bool(
        str(run.get("run_kind") or "") == "external"
        and run.get("finished")
        and run.get("exit_code") == 0
        and not run.get("preview_truncated")
        and not run.get("full_output_truncated")
        and not (run.get("full_output_available") and not str(run.get("rel_path") or ""))
    )


def _observation_ids(events: list[Any]) -> tuple[str, ...]:
    values: list[str] = []
    for event in events:
        detail = event.source_detail if hasattr(event, "source_detail") else None
        observations = detail.get("parameter_observations") if isinstance(detail, Mapping) else None
        if not isinstance(observations, list):
            continue
        for observation in observations:
            value = str(observation.get("observation_id") or "") if isinstance(observation, Mapping) else ""
            if value and value not in values:
                values.append(value)
    return tuple(values)


__all__ = [
    "DALFOX_PARAMETER_OPTION_MAX_ITEMS",
    "DALFOX_PARAMETER_OPTION_MAX_RUNS",
    "DalfoxParameterOptions",
    "list_project_dalfox_parameter_options",
]
