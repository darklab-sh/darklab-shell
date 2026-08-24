# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed, scope-safe evidence links for Project findings."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_connect
from services.assessments.contracts import AssessmentNotFound
from services.assessments.evidence_sources import load_assessment_evidence_source
from services.projects.contracts import (
    FINDING_EVIDENCE_TYPES,
    MAX_ENTITY_ID_LEN,
    MAX_FINDING_EVIDENCE_SNIPPET_LEN,
    ProjectWorkspaceError,
    ProjectWorkspaceNotFound,
)
from services.projects.finding_evidence_sources import load_finding_evidence_source
from services.projects.scope import shared_owner_where
from services.projects.utils import (
    new_finding_evidence_link_id,
    now,
    quota_exceeded,
    raise_quota,
    text_exceeds_limit,
    trim_text,
)


_LINK_SELECT_SQL = (
    "SELECT id, project_id, finding_id, evidence_type, evidence_id, run_id, "
    "line_number, snippet, created_by_member_id, created_at FROM finding_evidence_links"
)


def _finding_in_project(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
) -> None:
    try:
        load_assessment_evidence_source(
            conn,
            session_id,
            team_id,
            project_id,
            "finding",
            finding_id,
        )
    except AssessmentNotFound as exc:
        raise ProjectWorkspaceNotFound("finding was not found in this project scope") from exc


def _normalize_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("finding evidence payload must be a JSON object")
    if set(data) - {"evidence_type", "evidence_id", "line_number", "snippet"}:
        raise ProjectWorkspaceError("finding evidence payload contains unsupported fields")
    evidence_type = trim_text(data.get("evidence_type"), 32).lower()
    evidence_id = trim_text(data.get("evidence_id"), MAX_ENTITY_ID_LEN)
    if evidence_type not in FINDING_EVIDENCE_TYPES:
        raise ProjectWorkspaceError("finding evidence type is unsupported")
    if not evidence_id:
        raise ProjectWorkspaceError("finding evidence_id is required")
    try:
        line_number = int(data.get("line_number", -1))
    except (TypeError, ValueError) as exc:
        raise ProjectWorkspaceError("finding evidence line_number must be an integer") from exc
    if evidence_type == "run_line" and line_number < 0:
        raise ProjectWorkspaceError("run_line evidence requires a zero-based line_number")
    if evidence_type != "run_line" and line_number != -1:
        raise ProjectWorkspaceError("line_number is only supported for run_line evidence")
    if text_exceeds_limit(data.get("snippet"), MAX_FINDING_EVIDENCE_SNIPPET_LEN):
        raise ProjectWorkspaceError(
            f"finding evidence snippet exceeds {MAX_FINDING_EVIDENCE_SNIPPET_LEN} characters"
        )
    snippet = trim_text(data.get("snippet"), MAX_FINDING_EVIDENCE_SNIPPET_LEN)
    if evidence_type != "run_line" and snippet:
        raise ProjectWorkspaceError("snippet is only supported for run_line evidence")
    return {
        "evidence_type": evidence_type,
        "evidence_id": evidence_id,
        "line_number": line_number,
        "snippet": snippet,
    }


def _row_payload(row: Any, source: dict[str, Any] | None) -> dict[str, Any]:
    available = source is not None
    return {
        "id": str(row["id"] or ""),
        "project_id": str(row["project_id"] or ""),
        "finding_id": str(row["finding_id"] or ""),
        "evidence_type": str(row["evidence_type"] or ""),
        "evidence_id": str(row["evidence_id"] or ""),
        "run_id": str((source or {}).get("run_id") or row["run_id"] or ""),
        "line_number": int(row["line_number"]),
        "snippet": str(row["snippet"] or ""),
        "label": str((source or {}).get("label") or row["evidence_id"] or ""),
        "observed_at": str((source or {}).get("observed_at") or ""),
        "source_state": "available" if available else "unavailable",
        "created_by_member_id": str(row["created_by_member_id"] or ""),
        "created_at": str(row["created_at"] or ""),
    }


def list_finding_evidence_links_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    finding_id: str,
    *,
    team_id: str = "",
) -> list[dict[str, Any]]:
    _finding_in_project(conn, session_id, team_id, project_id, finding_id)
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    query = "".join((
        _LINK_SELECT_SQL,
        " WHERE ",
        owner_sql,
        " AND project_id = ? AND finding_id = ? ORDER BY created_at ASC, id ASC",
    ))
    rows = conn.execute(
        query,
        (*owner_params, project_id, finding_id),
    ).fetchall()
    result = []
    for row in rows:
        try:
            source = load_finding_evidence_source(
                conn,
                session_id,
                team_id,
                project_id,
                str(row["evidence_type"]),
                str(row["evidence_id"]),
                int(row["line_number"]),
            )
        except (ProjectWorkspaceError, ProjectWorkspaceNotFound):
            source = None
        result.append(_row_payload(row, source))
    return result


def attach_finding_evidence_links(
    session_id: str,
    project_id: str,
    findings: list[dict[str, Any]],
    *,
    team_id: str = "",
) -> None:
    """Attach package-safe typed evidence to an already scoped finding list."""
    if not findings:
        return
    with get_db_connect()() as conn:
        for finding in findings:
            finding_id = str(finding.get("id") or "")
            if not finding_id:
                finding["evidence_links"] = []
                continue
            try:
                finding["evidence_links"] = list_finding_evidence_links_on_conn(
                    conn,
                    session_id,
                    project_id,
                    finding_id,
                    team_id=team_id,
                )
            except ProjectWorkspaceNotFound:
                finding["evidence_links"] = []


def link_finding_evidence_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    finding_id: str,
    data: Any,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    payload = _normalize_payload(data)
    _finding_in_project(conn, session_id, team_id, project_id, finding_id)
    source = load_finding_evidence_source(
        conn,
        session_id,
        team_id,
        project_id,
        payload["evidence_type"],
        payload["evidence_id"],
        payload["line_number"],
    )
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    existing_query = "".join((
        _LINK_SELECT_SQL,
        " WHERE ",
        owner_sql,
        " AND project_id = ? AND finding_id = ? AND evidence_type = ? "
        "AND evidence_id = ? AND line_number = ?",
    ))
    existing = conn.execute(
        existing_query,
        (
            *owner_params,
            project_id,
            finding_id,
            payload["evidence_type"],
            payload["evidence_id"],
            payload["line_number"],
        ),
    ).fetchone()
    if existing:
        return {"created": False, "evidence": _row_payload(existing, source)}
    owner_count_query = "".join((
        "SELECT COUNT(*) AS count FROM finding_evidence_links WHERE ",
        owner_sql,
    ))
    owner_count = conn.execute(
        owner_count_query,
        owner_params,
    ).fetchone()
    if quota_exceeded(
        int(owner_count["count"] or 0),
        "max_finding_evidence_links_per_owner",
        10000,
    ):
        raise_quota("finding evidence link quota exceeded for this owner")
    finding_count_query = "".join((
        "SELECT COUNT(*) AS count FROM finding_evidence_links WHERE ",
        owner_sql,
        " AND project_id = ? AND finding_id = ?",
    ))
    finding_count = conn.execute(
        finding_count_query,
        (*owner_params, project_id, finding_id),
    ).fetchone()
    if quota_exceeded(
        int(finding_count["count"] or 0),
        "max_finding_evidence_links_per_finding",
        200,
    ):
        raise_quota("finding evidence link quota exceeded for this finding")
    evidence_link_id = new_finding_evidence_link_id()
    created_at = now()
    conn.execute(
        "INSERT INTO finding_evidence_links "
        "(id, session_id, team_id, project_id, finding_id, evidence_type, evidence_id, "
        "run_id, line_number, snippet, created_by_session_id, created_by_member_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            evidence_link_id,
            session_id,
            team_id,
            project_id,
            finding_id,
            payload["evidence_type"],
            payload["evidence_id"],
            source["run_id"],
            payload["line_number"],
            payload["snippet"],
            session_id,
            actor_member_id,
            created_at,
        ),
    )
    row = conn.execute(
        "SELECT id, project_id, finding_id, evidence_type, evidence_id, run_id, "
        "line_number, snippet, created_by_member_id, created_at "
        "FROM finding_evidence_links WHERE id = ?",
        (evidence_link_id,),
    ).fetchone()
    from services.assessments.reconciliation import (  # noqa: PLC0415
        reconcile_active_assessments_for_finding_on_conn,
    )

    reconcile_active_assessments_for_finding_on_conn(conn, finding_id)
    return {"created": True, "evidence": _row_payload(row, source)}


def unlink_finding_evidence_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    finding_id: str,
    evidence_link_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    _finding_in_project(conn, session_id, team_id, project_id, finding_id)
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    query = "".join((
        _LINK_SELECT_SQL,
        " WHERE ",
        owner_sql,
        " AND project_id = ? AND finding_id = ? AND id = ?",
    ))
    row = conn.execute(
        query,
        (*owner_params, project_id, finding_id, evidence_link_id),
    ).fetchone()
    if not row:
        raise ProjectWorkspaceNotFound("finding evidence link was not found")
    conn.execute("DELETE FROM finding_evidence_links WHERE id = ?", (evidence_link_id,))
    from services.assessments.reconciliation import (  # noqa: PLC0415
        reconcile_active_assessments_for_finding_on_conn,
    )

    reconcile_active_assessments_for_finding_on_conn(conn, finding_id)
    return _row_payload(row, None)
