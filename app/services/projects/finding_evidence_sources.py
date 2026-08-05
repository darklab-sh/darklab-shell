# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scope-safe source resolution for typed Project finding evidence."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.contracts import AssessmentError, AssessmentNotFound
from services.assessments.evidence_sources import load_assessment_evidence_source
from services.projects.contracts import ProjectWorkspaceError, ProjectWorkspaceNotFound
from services.projects.scope import shared_owner_where


_IMAGE_EXTENSIONS = (".gif", ".jpeg", ".jpg", ".png", ".webp")


def _run_payload(source, evidence_type: str, *, line_number: int = -1) -> dict[str, Any]:
    run_id = str(source.facts.run_id or source.evidence_id or "")
    label = str(source.facts.command_root or "Run")
    if evidence_type == "run_line":
        label = f"{label} line {line_number + 1}"
    elif evidence_type == "run_artifact":
        label = f"{label} output"
    elif evidence_type == "retest_run":
        label = f"Retest: {label}"
    return {"run_id": run_id, "label": label, "observed_at": source.observed_at}


def _project_run_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    evidence_type: str,
    evidence_id: str,
    line_number: int,
) -> dict[str, Any]:
    source_type = "run_artifact" if evidence_type == "run_artifact" else "run"
    source = load_assessment_evidence_source(
        conn,
        session_id,
        team_id,
        project_id,
        source_type,
        evidence_id,
    )
    if evidence_type == "run_line":
        row = conn.execute(
            "SELECT output_line_count FROM runs WHERE id = ?",
            (evidence_id,),
        ).fetchone()
        known_count = int(row["output_line_count"] or 0) if row else 0
        if known_count and line_number >= known_count:
            raise ProjectWorkspaceError("finding evidence line_number is outside the saved run output")
    return _run_payload(source, evidence_type, line_number=line_number)


def _workspace_artifact_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    evidence_type: str,
    evidence_id: str,
) -> dict[str, Any]:
    source = load_assessment_evidence_source(
        conn,
        session_id,
        team_id,
        project_id,
        "workspace_artifact",
        evidence_id,
    )
    row = conn.execute(
        "SELECT run_id, workspace_path, display_name, content_type, kind "
        "FROM run_file_artifacts WHERE id = ?",
        (evidence_id,),
    ).fetchone()
    if not row:
        raise ProjectWorkspaceNotFound("finding evidence was not found in this project scope")
    content_type = str(row["content_type"] or "").lower()
    workspace_path = str(row["workspace_path"] or "")
    kind = str(row["kind"] or "").lower()
    if evidence_type == "screenshot" and not (
        content_type.startswith("image/")
        or kind == "screenshot"
        or workspace_path.lower().endswith(_IMAGE_EXTENSIONS)
    ):
        raise ProjectWorkspaceError("screenshot evidence must reference a stored image artifact")
    return {
        "run_id": str(row["run_id"] or source.facts.run_id or ""),
        "label": str(row["display_name"] or workspace_path or evidence_id),
        "observed_at": source.observed_at,
    }


def _owned_entity_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    evidence_id: str,
) -> dict[str, Any]:
    source = load_assessment_evidence_source(
        conn,
        session_id,
        team_id,
        project_id,
        "atlas_entity",
        evidence_id,
    )
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="e")
    query = "".join((
        "SELECT e.type, e.canonical_value FROM entities e WHERE ",
        owner_sql,
        " AND e.id = ?",
    ))
    row = conn.execute(
        query,
        (*owner_params, evidence_id),
    ).fetchone()
    return {
        "run_id": str(source.facts.run_id or ""),
        "label": str(row["canonical_value"] or evidence_id) if row else evidence_id,
        "observed_at": source.observed_at,
    }


def _project_target_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    evidence_id: str,
) -> dict[str, Any]:
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
    query = "".join((
        "SELECT e.type, e.canonical_value, e.last_seen_at, l.source, l.source_detail, "
        "COALESCE((SELECT erl.run_id FROM entity_run_links erl "
        "JOIN project_links run_link ON run_link.entity_type = 'run' "
        "AND run_link.entity_id = erl.run_id "
        "WHERE erl.entity_id = e.id AND run_link.project_id = l.project_id "
        "ORDER BY erl.last_seen_at DESC, erl.run_id DESC LIMIT 1), '') AS source_run_id "
        "FROM project_links l JOIN projects p ON p.id = l.project_id "
        "JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        "AND e.type IN ('domain', 'ip', 'url') AND ",
        owner_sql,
        " AND e.id = ?",
    ))
    row = conn.execute(
        query,
        (project_id, *owner_params, evidence_id),
    ).fetchone()
    if not row:
        raise ProjectWorkspaceNotFound("finding evidence was not found in this project scope")
    source_detail = dialect_for_backend(get_db_backend()).decode_json_dict(row["source_detail"])
    is_target = str(row["source"] or "") in {"auto_command", "auto_input_file"}
    target_marker = source_detail.get("project_target")
    if isinstance(target_marker, str):
        target_marker = target_marker.strip().lower() in {"1", "true", "yes", "on"}
    if not (is_target or bool(target_marker)):
        raise ProjectWorkspaceNotFound("finding evidence was not found in this project scope")
    return {
        "run_id": str(row["source_run_id"] or ""),
        "label": str(row["canonical_value"] or evidence_id),
        "observed_at": str(row["last_seen_at"] or ""),
    }


def _assessment_check_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    evidence_id: str,
) -> dict[str, Any]:
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="a")
    query = "".join((
        "SELECT c.check_key, c.target_value, c.last_evidence_at "
        "FROM project_assessment_checks c "
        "JOIN project_assessments a ON a.id = c.assessment_id "
        "WHERE a.project_id = ? AND ",
        owner_sql,
        " AND c.id = ?",
    ))
    row = conn.execute(
        query,
        (project_id, *owner_params, evidence_id),
    ).fetchone()
    if not row:
        raise ProjectWorkspaceNotFound("finding evidence was not found in this project scope")
    label = str(row["check_key"] or evidence_id)
    if row["target_value"]:
        label = f"{label}: {row['target_value']}"
    return {"run_id": "", "label": label, "observed_at": str(row["last_evidence_at"] or "")}


def load_finding_evidence_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    evidence_type: str,
    evidence_id: str,
    line_number: int,
) -> dict[str, Any]:
    """Resolve one typed source inside the active owner and Project scope."""
    try:
        if evidence_type in {"run", "run_line", "run_artifact", "retest_run"}:
            return _project_run_source(
                conn, session_id, team_id, project_id, evidence_type, evidence_id, line_number
            )
        if evidence_type in {"workspace_file", "screenshot"}:
            return _workspace_artifact_source(
                conn, session_id, team_id, project_id, evidence_type, evidence_id
            )
        if evidence_type == "atlas_entity":
            return _owned_entity_source(conn, session_id, team_id, project_id, evidence_id)
        if evidence_type == "project_target":
            return _project_target_source(conn, session_id, team_id, project_id, evidence_id)
        if evidence_type == "assessment_check":
            return _assessment_check_source(conn, session_id, team_id, project_id, evidence_id)
    except AssessmentNotFound as exc:
        raise ProjectWorkspaceNotFound("finding evidence was not found in this project scope") from exc
    except AssessmentError as exc:
        raise ProjectWorkspaceError(str(exc)) from exc
    raise ProjectWorkspaceError("finding evidence type is unsupported")
