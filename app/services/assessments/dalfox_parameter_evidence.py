# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Resolve one saved Dalfox parameter observation inside its Project scope."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.helpers import get_log_session_id
from services.assessments.dalfox_parameter_observations import (
    DALFOX_DISCOVERY_PARSER_VERSION,
    DALFOX_MAX_PARAMETER_OBSERVATIONS,
    DalfoxParameterObservationState,
    dalfox_parameter_observation_id,
)
from services.assessments.dalfox_xss_observations import ReviewedDalfoxXssContext
from services.projects.scope import shared_owner_where
from services.runs.output_store import load_run_output_events_for_run


DALFOX_PARAMETER_EVIDENCE_MAX_EVENTS = 1_024


@dataclass(frozen=True)
class ReviewedDalfoxParameterEvidence:
    """Trusted saved evidence that can seed one separately reviewed XSS plan."""

    source_run_id: str
    observation_id: str
    target: str
    parameter: str
    location: str
    tool_version: str
    parser_version: str

    def xss_context(self, *, request_limit: int) -> ReviewedDalfoxXssContext:
        """Build the typed active-result context without accepting caller target data."""
        return ReviewedDalfoxXssContext(
            target=self.target,
            parameter=self.parameter,
            location=self.location,
            source_parameter_run_id=self.source_run_id,
            source_parameter_observation_id=self.observation_id,
            request_limit=request_limit,
        )


def resolve_project_dalfox_parameter_evidence(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    source_run_id: str,
    observation_id: str,
    *,
    expected_target: str,
) -> ReviewedDalfoxParameterEvidence | None:
    """Return one complete, exact, owner-scoped saved observation or fail closed."""
    run_id = str(source_run_id or "").strip()
    wanted_id = str(observation_id or "").strip()
    if not run_id or not wanted_id:
        return None
    row = _project_run_row(conn, session_id, team_id, project_id, run_id)
    if row is None:
        return None
    run = dict(row)
    if (
        str(run.get("run_kind") or "") != "external"
        or not run.get("finished")
        or run.get("exit_code") != 0
        or bool(run.get("preview_truncated"))
        or bool(run.get("full_output_truncated"))
        or bool(run.get("full_output_available")) and not str(run.get("rel_path") or "")
    ):
        return None
    command_state = DalfoxParameterObservationState(str(run.get("command") or ""), run_id)
    if not command_state.target:
        return None
    loaded = load_run_output_events_for_run(
        run,
        failure_log_extra={
            "session": get_log_session_id(session_id),
            "team_id": str(team_id or "")[:64],
            "project_id": str(project_id or "")[:64],
            "evidence_kind": "dalfox_parameter_observation",
        },
    )
    if loaded.partial or not loaded.events or len(loaded.events) > DALFOX_PARAMETER_EVIDENCE_MAX_EVENTS:
        return None
    return review_dalfox_parameter_events(
        loaded.events,
        run_id,
        wanted_id,
        command_state.target,
        expected_target=str(expected_target or "").strip(),
    )


def _project_run_row(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    run_id: str,
) -> Any | None:
    project_owner_sql, project_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p",
    )
    run_owner_sql, run_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="r",
    )
    # Both owner predicates come from fixed helpers; all values stay bound.
    sql = "".join((
        "SELECT r.id, r.session_id, r.team_id, r.run_kind, r.command, r.finished, ",
        "r.exit_code, r.output_preview, r.preview_truncated, r.full_output_available, ",
        "r.full_output_truncated, art.rel_path FROM projects p ",
        "JOIN project_links pl ON pl.project_id = p.id ",
        "JOIN runs r ON r.id = pl.entity_id ",
        "LEFT JOIN run_output_artifacts art ON art.run_id = r.id ",
        "WHERE p.id = ? AND pl.entity_type = 'run' AND r.id = ? AND ",
        project_owner_sql,
        " AND ",
        run_owner_sql,
        " LIMIT 2",
    ))
    rows = conn.execute(
        sql,
        (project_id, run_id, *project_owner_params, *run_owner_params),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


def review_dalfox_parameter_events(
    events: list[Any],
    run_id: str,
    observation_id: str,
    command_target: str,
    *,
    expected_target: str,
) -> ReviewedDalfoxParameterEvidence | None:
    summary: dict[str, Any] | None = None
    selected: dict[str, Any] | None = None
    for event in events:
        detail = event.source_detail if hasattr(event, "source_detail") else None
        if not isinstance(detail, Mapping):
            continue
        candidate_summary = detail.get("parameter_discovery")
        if isinstance(candidate_summary, Mapping):
            value = dict(candidate_summary)
            if summary is not None or not _valid_summary(value, run_id, command_target):
                return None
            summary = value
        candidates = detail.get("parameter_observations")
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            value = dict(candidate)
            if str(value.get("observation_id") or "") != observation_id:
                continue
            if summary is None or selected is not None:
                return None
            selected = value
    if summary is None or selected is None:
        return None
    target = str(selected.get("target") or "")
    if not _valid_observation(selected, summary, run_id, command_target):
        return None
    if not expected_target or target != expected_target:
        return None
    try:
        context = ReviewedDalfoxXssContext(
            target=target,
            parameter=str(selected.get("parameter") or ""),
            location=str(selected.get("location") or ""),
            source_parameter_run_id=run_id,
            source_parameter_observation_id=observation_id,
            request_limit=1,
        )
    except ValueError:
        return None
    return ReviewedDalfoxParameterEvidence(
        source_run_id=run_id,
        observation_id=observation_id,
        target=context.target,
        parameter=context.parameter,
        location=context.location,
        tool_version=str(selected.get("tool_version") or ""),
        parser_version=DALFOX_DISCOVERY_PARSER_VERSION,
    )


def _valid_summary(summary: Mapping[str, Any], run_id: str, command_target: str) -> bool:
    count = summary.get("reported_parameter_count")
    return bool(
        str(summary.get("target") or "") == command_target
        and str(summary.get("mode") or "") == "only_discovery"
        and str(summary.get("source_run_id") or "") == run_id
        and str(summary.get("tool_version") or "")
        and str(summary.get("parser_version") or "") == DALFOX_DISCOVERY_PARSER_VERSION
        and isinstance(count, int)
        and not isinstance(count, bool)
        and 0 <= count <= DALFOX_MAX_PARAMETER_OBSERVATIONS
        and summary.get("truncated") is False
    )


def _valid_observation(
    observation: Mapping[str, Any],
    summary: Mapping[str, Any],
    run_id: str,
    command_target: str,
) -> bool:
    return bool(
        str(observation.get("target") or "") == command_target
        and str(observation.get("source_run_id") or "") == run_id
        and str(observation.get("observation_id") or "") == dalfox_parameter_observation_id(
            run_id,
            command_target,
            str(observation.get("location") or ""),
            str(observation.get("parameter") or ""),
        )
        and str(observation.get("tool_version") or "")
        == str(summary.get("tool_version") or "")
        and str(observation.get("parser_version") or "") == DALFOX_DISCOVERY_PARSER_VERSION
        and int(summary.get("reported_parameter_count") or 0) > 0
    )


__all__ = [
    "DALFOX_PARAMETER_EVIDENCE_MAX_EVENTS",
    "ReviewedDalfoxParameterEvidence",
    "review_dalfox_parameter_events",
    "resolve_project_dalfox_parameter_evidence",
]
