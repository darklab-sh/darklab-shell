# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scope-safe source loading for manually linked assessment evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from services.assessments.contracts import AssessmentError, AssessmentNotFound
from services.assessments.evidence_matching import (
    EvidenceIdentity,
    RunEvidenceFacts,
    canonical_evidence_identity,
    load_run_evidence_facts,
)
from services.projects.scope import shared_owner_where

_PROJECT_RUN_SQL = (
    "SELECT r.id FROM runs r JOIN project_links pl "
    "ON pl.entity_type = 'run' AND pl.entity_id = r.id "
    "WHERE pl.project_id = ? AND {owner_sql} AND r.id = ?"
)
_FINDING_SQL = (
    "SELECT f.id, f.run_id, f.first_run_id, f.last_run_id, f.entity_id, "
    "f.target_id, f.tool_root, f.created FROM findings f WHERE {owner_sql} "
    "AND f.id = ? AND ("
    "EXISTS (SELECT 1 FROM project_links pl WHERE pl.project_id = ? "
    "AND pl.entity_type = 'run' AND pl.entity_id IN "
    "(f.run_id, f.first_run_id, f.last_run_id)) OR "
    "EXISTS (SELECT 1 FROM findings_occurrences fo "
    "JOIN project_links pl ON pl.entity_type = 'run' AND pl.entity_id = fo.run_id "
    "WHERE fo.finding_id = f.id AND pl.project_id = ?) OR "
    "EXISTS (SELECT 1 FROM project_links pe WHERE pe.project_id = ? "
    "AND pe.entity_type = 'atlas_entity' "
    "AND pe.entity_id = COALESCE(f.entity_id, f.target_id)))"
)
_ENTITY_SQL = (
    "SELECT e.id, e.type, e.canonical_value, e.last_seen_at FROM entities e "
    "JOIN project_links pl ON pl.entity_type = 'atlas_entity' AND pl.entity_id = e.id "
    "WHERE pl.project_id = ? AND pl.review_state = 'confirmed' AND {owner_sql} "
    "AND e.id = ?"
)
_WORKFLOW_SQL = (
    "SELECT w.id, w.workflow_id, w.status, w.finished, w.created "
    "FROM workflow_executions w WHERE w.execution_kind = ? AND {owner_sql} AND w.project_id = ? "
    "AND w.id = ?"
)


@dataclass(frozen=True)
class AssessmentEvidenceSource:
    evidence_type: str
    evidence_id: str
    observed_at: str
    facts: RunEvidenceFacts


def _project_run_facts(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    run_id: str,
) -> RunEvidenceFacts | None:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="r",
    )
    row = conn.execute(
        _PROJECT_RUN_SQL.format(owner_sql=owner_sql),
        (project_id, *owner_params, run_id),
    ).fetchone()
    if not row:
        return None
    return load_run_evidence_facts(conn, str(row["id"]))


def _run_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    run_id: str,
    evidence_type: str,
    evidence_id: str,
) -> AssessmentEvidenceSource:
    facts = _project_run_facts(conn, session_id, team_id, project_id, run_id)
    if facts is None:
        raise AssessmentNotFound("assessment evidence was not found in this project scope")
    return AssessmentEvidenceSource(
        evidence_type=evidence_type,
        evidence_id=evidence_id,
        observed_at=facts.finished_at,
        facts=facts,
    )


def _finding_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
) -> AssessmentEvidenceSource:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="f",
    )
    row = conn.execute(
        _FINDING_SQL.format(owner_sql=owner_sql),
        (*owner_params, finding_id, project_id, project_id, project_id),
    ).fetchone()
    if not row:
        raise AssessmentNotFound("assessment evidence was not found in this project scope")
    candidate_ids = [
        str(row["last_run_id"] or ""),
        str(row["run_id"] or ""),
        str(row["first_run_id"] or ""),
    ]
    occurrence_rows = conn.execute(
        "SELECT fo.run_id FROM findings_occurrences fo "
        "JOIN project_links pl ON pl.entity_type = 'run' AND pl.entity_id = fo.run_id "
        "WHERE fo.finding_id = ? AND pl.project_id = ? ORDER BY fo.seen_at DESC",
        (finding_id, project_id),
    ).fetchall()
    candidate_ids.extend(str(item["run_id"] or "") for item in occurrence_rows)
    for run_id in dict.fromkeys(value for value in candidate_ids if value):
        facts = _project_run_facts(conn, session_id, team_id, project_id, run_id)
        if facts is not None:
            facts = replace(
                facts,
                finding_count=max(1, facts.finding_count),
                structured_output_kinds=facts.structured_output_kinds | {"findings"},
            )
            return AssessmentEvidenceSource(
                evidence_type="finding",
                evidence_id=finding_id,
                observed_at=str(row["created"] or facts.finished_at),
                facts=facts,
            )
    entity_id = str(row["entity_id"] or row["target_id"] or "")
    entity = conn.execute(
        "SELECT e.type, e.canonical_value FROM entities e "
        "JOIN project_links pl ON pl.entity_type = 'atlas_entity' AND pl.entity_id = e.id "
        "WHERE pl.project_id = ? AND e.id = ?",
        (project_id, entity_id),
    ).fetchone()
    identity = (
        canonical_evidence_identity(entity["canonical_value"], entity["type"])
        if entity
        else None
    )
    facts = RunEvidenceFacts(
        run_id="",
        command_root=str(row["tool_root"] or ""),
        finished_at=str(row["created"] or ""),
        exit_code=None,
        target_identities=(identity,) if identity else (),
        structured_output_kinds=frozenset({"findings"}),
        workflow_actions=frozenset(),
        finding_count=1,
    )
    return AssessmentEvidenceSource(
        evidence_type="finding",
        evidence_id=finding_id,
        observed_at=facts.finished_at,
        facts=facts,
    )


def _entity_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    entity_id: str,
) -> AssessmentEvidenceSource:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="e",
    )
    row = conn.execute(
        _ENTITY_SQL.format(owner_sql=owner_sql),
        (project_id, *owner_params, entity_id),
    ).fetchone()
    if not row:
        raise AssessmentNotFound("assessment evidence was not found in this project scope")
    run_rows = conn.execute(
        "SELECT erl.run_id FROM entity_run_links erl "
        "JOIN project_links pl ON pl.entity_type = 'run' AND pl.entity_id = erl.run_id "
        "WHERE erl.entity_id = ? AND pl.project_id = ? ORDER BY erl.last_seen_at DESC",
        (entity_id, project_id),
    ).fetchall()
    for run_row in run_rows:
        facts = _project_run_facts(
            conn,
            session_id,
            team_id,
            project_id,
            str(run_row["run_id"] or ""),
        )
        if facts is not None:
            return AssessmentEvidenceSource(
                evidence_type="atlas_entity",
                evidence_id=entity_id,
                observed_at=str(row["last_seen_at"] or facts.finished_at),
                facts=facts,
            )
    identity = canonical_evidence_identity(row["canonical_value"], row["type"])
    facts = RunEvidenceFacts(
        run_id="",
        command_root="",
        finished_at=str(row["last_seen_at"] or ""),
        exit_code=None,
        target_identities=(identity,) if identity else (),
        structured_output_kinds=frozenset({"entities"}),
        workflow_actions=frozenset(),
        finding_count=0,
    )
    return AssessmentEvidenceSource(
        evidence_type="atlas_entity",
        evidence_id=entity_id,
        observed_at=facts.finished_at,
        facts=facts,
    )


def _workflow_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    execution_id: str,
) -> AssessmentEvidenceSource:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="w",
    )
    row = conn.execute(
        _WORKFLOW_SQL.format(owner_sql=owner_sql),
        ("workflow", *owner_params, project_id, execution_id),
    ).fetchone()
    if not row:
        raise AssessmentNotFound("assessment evidence was not found in this project scope")
    run_rows = conn.execute(
        "SELECT run_id FROM workflow_execution_steps "
        "WHERE execution_id = ? AND run_id != '' ORDER BY step_index ASC",
        (execution_id,),
    ).fetchall()
    identities: set[EvidenceIdentity] = set()
    kinds: set[str] = set()
    finding_count = 0
    command_root = ""
    for run_row in run_rows:
        facts = _project_run_facts(
            conn,
            session_id,
            team_id,
            project_id,
            str(run_row["run_id"] or ""),
        )
        if facts is None:
            continue
        command_root = command_root or facts.command_root
        identities.update(facts.target_identities)
        kinds.update(facts.structured_output_kinds)
        finding_count += facts.finding_count
    finished_at = str(row["finished"] or "")
    succeeded = str(row["status"] or "") == "completed"
    facts = RunEvidenceFacts(
        run_id="",
        command_root=command_root,
        finished_at=finished_at,
        exit_code=0 if succeeded else None,
        target_identities=tuple(sorted(identities, key=lambda item: (item.entity_type, item.canonical_value))),
        structured_output_kinds=frozenset(kinds),
        workflow_actions=frozenset({str(row["workflow_id"] or "")}),
        finding_count=finding_count,
    )
    return AssessmentEvidenceSource(
        evidence_type="workflow_execution",
        evidence_id=execution_id,
        observed_at=finished_at or str(row["created"] or ""),
        facts=facts,
    )


def load_assessment_evidence_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    evidence_type: str,
    evidence_id: str,
) -> AssessmentEvidenceSource:
    """Load one saved evidence source only when it belongs to the active scope."""
    if evidence_type == "run":
        return _run_source(
            conn, session_id, team_id, project_id, evidence_id, evidence_type, evidence_id
        )
    if evidence_type == "finding":
        return _finding_source(conn, session_id, team_id, project_id, evidence_id)
    if evidence_type == "atlas_entity":
        return _entity_source(conn, session_id, team_id, project_id, evidence_id)
    if evidence_type == "workflow_execution":
        return _workflow_source(conn, session_id, team_id, project_id, evidence_id)
    if evidence_type == "run_artifact":
        row = conn.execute(
            "SELECT run_id FROM run_output_artifacts WHERE run_id = ?",
            (evidence_id,),
        ).fetchone()
        run_id = str(row["run_id"] or "") if row else ""
        return _run_source(
            conn, session_id, team_id, project_id, run_id, evidence_type, evidence_id
        )
    if evidence_type == "workspace_artifact":
        row = conn.execute(
            "SELECT run_id FROM run_file_artifacts WHERE id = ?",
            (evidence_id,),
        ).fetchone()
        run_id = str(row["run_id"] or "") if row else ""
        return _run_source(
            conn, session_id, team_id, project_id, run_id, evidence_type, evidence_id
        )
    if evidence_type == "screenshot":
        raise AssessmentError("stored screenshot evidence is not available")
    raise AssessmentError("assessment evidence type is unsupported")
