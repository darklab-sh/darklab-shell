"""Report draft persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import secrets

from core.database import DB_BACKEND, db_connect
from core.database_backend import dialect_for_backend, integrity_error_types
from services.projects.contracts import ProjectWorkspaceError
from services.projects.scope import shared_owner_where

from .models import REPORT_FORMAT_VERSION, default_report_draft, normalize_report_draft


class ReportDraftConflict(ProjectWorkspaceError):
    """Raised when a report draft save races with another writer."""


def _new_report_id() -> str:
    return "rpt_" + secrets.token_hex(8)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _decode_draft(value: Any) -> dict[str, Any]:
    return dialect_for_backend(DB_BACKEND).decode_json_dict(value)


def row_to_report_draft(row) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "team_id": row["team_id"],
        "project_id": row["project_id"],
        "draft": normalize_report_draft(_decode_draft(row["draft"])),
        "report_format_version": int(row["report_format_version"] or REPORT_FORMAT_VERSION),
        "created": row["created"],
        "updated": row["updated"],
    }


def _report_owner_where(session_id: str, *, team_id: str = "", table_alias: str = "") -> tuple[str, tuple[str, ...]]:
    return shared_owner_where(session_id, team_id=team_id, table_alias=table_alias)


def get_report_draft_on_conn(conn, session_id: str, project_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    owner_sql, owner_params = _report_owner_where(session_id, team_id=team_id)
    row = conn.execute(
        "SELECT id, session_id, team_id, project_id, draft, report_format_version, created, updated "
        "FROM project_reports WHERE " + owner_sql + " AND project_id = ?",  # nosec
        (*owner_params, str(project_id or "").strip()),
    ).fetchone()
    return row_to_report_draft(row)


def get_report_draft(session_id: str, project_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    with db_connect() as conn:
        return get_report_draft_on_conn(conn, session_id, project_id, team_id=team_id)


def default_report_record(session_id: str, project_id: str, *, team_id: str = "") -> dict[str, Any]:
    timestamp = _now()
    return {
        "id": "",
        "session_id": str(session_id or "").strip(),
        "team_id": str(team_id or "").strip(),
        "project_id": str(project_id or "").strip(),
        "draft": default_report_draft(),
        "report_format_version": REPORT_FORMAT_VERSION,
        "created": timestamp,
        "updated": "",
    }


def save_report_draft_on_conn(
    conn,
    session_id: str,
    project_id: str,
    draft: dict[str, Any] | None,
    *,
    team_id: str = "",
    expected_updated: str = "",
) -> dict[str, Any]:
    normalized_session_id = str(session_id or "").strip()
    normalized_team_id = str(team_id or "").strip()
    normalized_project_id = str(project_id or "").strip()
    normalized_draft = normalize_report_draft(draft or {})
    expected = str(expected_updated or "").strip()
    existing = get_report_draft_on_conn(
        conn,
        normalized_session_id,
        normalized_project_id,
        team_id=normalized_team_id,
    )
    if existing:
        if not expected or str(existing["updated"] or "") != expected:
            raise ReportDraftConflict("report draft changed; reload before saving")
        timestamp = _now()
        conn.execute(
            "UPDATE project_reports SET draft = ?, report_format_version = ?, updated = ? WHERE id = ?",
            (
                dialect_for_backend(DB_BACKEND).json_param(normalized_draft),
                REPORT_FORMAT_VERSION,
                timestamp,
                existing["id"],
            ),
        )
        refreshed = get_report_draft_on_conn(
            conn,
            normalized_session_id,
            normalized_project_id,
            team_id=normalized_team_id,
        )
        if refreshed is None:
            raise ProjectWorkspaceError("report draft save failed")
        return refreshed

    if expected:
        raise ReportDraftConflict("report draft changed; reload before saving")
    timestamp = _now()
    report_id = _new_report_id()
    try:
        conn.execute(
            "INSERT INTO project_reports "
            "(id, session_id, team_id, project_id, draft, report_format_version, created, updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                report_id,
                normalized_session_id,
                normalized_team_id,
                normalized_project_id,
                dialect_for_backend(DB_BACKEND).json_param(normalized_draft),
                REPORT_FORMAT_VERSION,
                timestamp,
                timestamp,
            ),
        )
    except integrity_error_types(DB_BACKEND) as exc:
        raise ReportDraftConflict("report draft changed; reload before saving") from exc
    inserted = get_report_draft_on_conn(
        conn,
        normalized_session_id,
        normalized_project_id,
        team_id=normalized_team_id,
    )
    if inserted is None:
        raise ProjectWorkspaceError("report draft save failed")
    return inserted


def save_report_draft(
    session_id: str,
    project_id: str,
    draft: dict[str, Any] | None,
    *,
    team_id: str = "",
    expected_updated: str = "",
) -> dict[str, Any]:
    with db_connect() as conn:
        saved = save_report_draft_on_conn(
            conn,
            session_id,
            project_id,
            draft,
            team_id=team_id,
            expected_updated=expected_updated,
        )
        conn.commit()
        return saved
