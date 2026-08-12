# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment-cycle lifecycle updates and safe historical cleanup."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.database_access import get_db_connect
from services.assessments.contracts import (
    ASSESSMENT_MAX_TITLE_LEN,
    ASSESSMENT_STATUSES,
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
)
from services.assessments.deletion_preview import assessment_deletion_preview
from services.assessments.reconciliation import reconcile_assessment_findings_on_conn
from services.assessments.reconciliation_cleanup import (
    delete_assessment_reconciliation_on_conn,
)
from services.assessments.serialization import row_to_assessment
from services.projects.scope import shared_owner_where
from services.projects.utils import now


_ASSESSMENT_COLUMNS = (
    "a.id, a.team_id, a.project_id, a.title, a.profile_key, a.profile_version, "
    "a.profile_snapshot, a.status, a.started_at, a.completed_at, a.archived_at, "
    "a.created_by_member_id, a.updated_by_member_id, a.created_at, a.updated_at"
)


def _normalize_required(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise AssessmentError(f"assessment {label} is required")
    return normalized


def _normalize_title(value: object) -> str:
    title = _normalize_required(value, "title")
    if len(title) > ASSESSMENT_MAX_TITLE_LEN:
        raise AssessmentError(
            f"assessment title exceeds {ASSESSMENT_MAX_TITLE_LEN} characters"
        )
    return title


def _assessment_row(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    team_id: str,
) -> Any:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="p",
    )
    query = "".join((
        "SELECT ",
        _ASSESSMENT_COLUMNS,
        ", p.status AS project_status FROM project_assessments a ",
        "JOIN projects p ON p.id = a.project_id WHERE ",
        owner_sql,
        " AND p.id = ? AND a.id = ?",
    ))
    return conn.execute(
        query,
        (*owner_params, project_id, assessment_id),
    ).fetchone()


def _load_assessment(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    team_id: str,
) -> Any:
    row = _assessment_row(
        conn,
        session_id,
        project_id,
        assessment_id,
        team_id=team_id,
    )
    if not row:
        raise AssessmentNotFound("assessment was not found in this scope")
    return row


def _update_cycle(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    payload: Mapping[str, object],
    *,
    team_id: str,
    actor_member_id: str,
) -> dict[str, Any]:
    unknown = sorted(set(payload) - {"title", "status"})
    if unknown:
        raise AssessmentError("assessment update contains unsupported fields")
    if not payload:
        raise AssessmentError("assessment update is required")
    row = _load_assessment(
        conn,
        session_id,
        project_id,
        assessment_id,
        team_id=team_id,
    )
    if str(row["project_status"] or "") == "archived":
        raise AssessmentConflict("archived projects are read-only")
    current_status = str(row["status"] or "")
    if current_status == "archived":
        raise AssessmentConflict("archived assessments are read-only")

    title = str(row["title"] or "")
    if "title" in payload:
        if current_status != "active":
            raise AssessmentConflict("completed assessments are read-only")
        title = _normalize_title(payload.get("title"))

    next_status = str(payload.get("status", current_status) or "").strip().lower()
    if next_status not in ASSESSMENT_STATUSES:
        raise AssessmentError("assessment status is unsupported")
    allowed_transitions = {
        "active": {"active", "completed", "archived"},
        "completed": {"completed", "archived"},
    }
    if next_status not in allowed_transitions.get(current_status, set()):
        raise AssessmentConflict("completed assessments cannot be reopened")

    title_changed = title != str(row["title"] or "")
    status_changed = next_status != current_status
    if not title_changed and not status_changed:
        raise AssessmentError("assessment update did not change anything")

    changed_at = now()
    completed_at = row["completed_at"]
    archived_at = row["archived_at"]
    if next_status == "completed" and current_status == "active":
        completed_at = changed_at
    if next_status == "archived":
        archived_at = changed_at
    result = conn.execute(
        "UPDATE project_assessments SET title = ?, status = ?, completed_at = ?, "
        "archived_at = ?, updated_by_session_id = ?, updated_by_member_id = ?, "
        "updated_at = ? WHERE id = ? AND project_id = ? AND status = ? AND updated_at = ?",
        (
            title,
            next_status,
            completed_at,
            archived_at,
            session_id,
            actor_member_id,
            changed_at,
            assessment_id,
            project_id,
            current_status,
            row["updated_at"],
        ),
    )
    if not result.rowcount:
        raise AssessmentConflict("assessment changed during this update")
    if next_status == "completed" and current_status == "active":
        reconcile_assessment_findings_on_conn(conn, assessment_id)
    updated = _load_assessment(
        conn,
        session_id,
        project_id,
        assessment_id,
        team_id=team_id,
    )
    return {
        "assessment": row_to_assessment(updated),
        "from_status": current_status,
        "to_status": next_status,
        "title_changed": title_changed,
        "transition_kind": (
            "archive" if next_status == "archived" else
            "complete" if next_status == "completed" else
            "update"
        ),
    }


def update_assessment_cycle(
    session_id: str,
    project_id: str,
    assessment_id: str,
    payload: Mapping[str, object] | object,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    conn: Any = None,
) -> dict[str, Any]:
    """Update an active cycle or move it forward through its lifecycle."""
    normalized_session_id = _normalize_required(session_id, "session")
    normalized_project_id = _normalize_required(project_id, "project")
    normalized_assessment_id = _normalize_required(assessment_id, "id")
    if not isinstance(payload, Mapping):
        raise AssessmentError("assessment update must be a JSON object")
    normalized_team_id = str(team_id or "").strip()
    normalized_actor_member_id = str(actor_member_id or "").strip()
    if conn is not None:
        return _update_cycle(
            conn,
            normalized_session_id,
            normalized_project_id,
            normalized_assessment_id,
            payload,
            team_id=normalized_team_id,
            actor_member_id=normalized_actor_member_id,
        )
    with get_db_connect()() as opened:
        updated = _update_cycle(
            opened,
            normalized_session_id,
            normalized_project_id,
            normalized_assessment_id,
            payload,
            team_id=normalized_team_id,
            actor_member_id=normalized_actor_member_id,
        )
        opened.commit()
        return updated


def preview_assessment_deletion(
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    team_id: str = "",
    conn: Any = None,
) -> dict[str, Any]:
    """Describe the assessment-owned rows a hard deletion would remove."""
    normalized_session_id = _normalize_required(session_id, "session")
    normalized_project_id = _normalize_required(project_id, "project")
    normalized_assessment_id = _normalize_required(assessment_id, "id")
    normalized_team_id = str(team_id or "").strip()

    def _preview(active_conn: Any) -> dict[str, Any]:
        row = _load_assessment(
            active_conn,
            normalized_session_id,
            normalized_project_id,
            normalized_assessment_id,
            team_id=normalized_team_id,
        )
        return assessment_deletion_preview(active_conn, row)

    if conn is not None:
        return _preview(conn)
    with get_db_connect()() as opened:
        return _preview(opened)


def delete_assessment_cycle(
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    team_id: str = "",
    conn: Any = None,
) -> dict[str, Any]:
    """Delete one archived cycle tree while preserving every source record."""
    normalized_session_id = _normalize_required(session_id, "session")
    normalized_project_id = _normalize_required(project_id, "project")
    normalized_assessment_id = _normalize_required(assessment_id, "id")
    normalized_team_id = str(team_id or "").strip()

    def _delete(active_conn: Any) -> dict[str, Any]:
        row = _load_assessment(
            active_conn,
            normalized_session_id,
            normalized_project_id,
            normalized_assessment_id,
            team_id=normalized_team_id,
        )
        if str(row["project_status"] or "") == "archived":
            raise AssessmentConflict("archived projects are read-only")
        if str(row["status"] or "") != "archived":
            raise AssessmentConflict("only archived assessments can be deleted")
        preview = assessment_deletion_preview(active_conn, row)
        delete_assessment_reconciliation_on_conn(active_conn, normalized_assessment_id)
        active_conn.execute(
            "DELETE FROM schemathesis_operation_evidence WHERE report_id IN "
            "(SELECT id FROM schemathesis_run_evidence WHERE assessment_id = ?)",
            (normalized_assessment_id,),
        )
        active_conn.execute(
            "DELETE FROM schemathesis_run_evidence WHERE assessment_id = ?",
            (normalized_assessment_id,),
        )
        active_conn.execute(
            "DELETE FROM project_assessment_evidence WHERE assessment_id = ?",
            (normalized_assessment_id,),
        )
        active_conn.execute(
            "DELETE FROM project_assessment_checks WHERE assessment_id = ?",
            (normalized_assessment_id,),
        )
        result = active_conn.execute(
            "DELETE FROM project_assessments WHERE id = ? AND project_id = ?",
            (normalized_assessment_id, normalized_project_id),
        )
        if not result.rowcount:
            raise AssessmentConflict("assessment changed during deletion")
        return preview

    if conn is not None:
        return _delete(conn)
    with get_db_connect()() as opened:
        deleted = _delete(opened)
        opened.commit()
        return deleted
