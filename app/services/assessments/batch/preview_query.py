# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded owner-scoped reads for the assessment-batch preview compiler."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.batch.contracts import AssessmentBatchError
from services.projects.scope import shared_owner_where


CHECK_FETCH_SIZE = 256
HTTP_PROFILE_READ_LIMIT = 51


@dataclass(frozen=True)
class BatchPreviewSource:
    """Frozen cycle identity plus bounded saved-profile classification."""

    assessment: Any
    enabled_http_profile_count: int
    credentialed_http_profile_count: int


def _active_assessment(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
) -> Any:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="a"
    )
    row = conn.execute(
        "SELECT a.id, a.project_id, a.profile_key, a.profile_version, "
        "a.profile_snapshot, a.status, p.status AS project_status "
        "FROM project_assessments a JOIN projects p ON p.id = a.project_id WHERE "
        + owner_sql  # nosec
        + " AND a.project_id = ? AND a.id = ? AND a.status = 'active' "
        "AND p.status != 'archived' LIMIT 1",
        (*owner_params, project_id, assessment_id),
    ).fetchone()
    if not row:
        raise AssessmentBatchError(
            "assessment_not_active",
            "The active assessment wasn't found in this Project scope.",
            status_code=409,
        )
    return row


def _http_profile_counts(
    conn: Any, session_id: str, team_id: str, project_id: str
) -> tuple[int, int]:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="h"
    )
    rows = conn.execute(
        "SELECT h.headers_json, h.secret_refs_json, h.file_refs_json, "
        "h.login_workflow_id, h.token_capture_rules_json "
        "FROM project_http_profiles h WHERE "
        + owner_sql  # nosec
        + " AND h.project_id = ? AND h.enabled = ? "
        "ORDER BY h.id LIMIT ?",
        (*owner_params, project_id, True, HTTP_PROFILE_READ_LIMIT),
    ).fetchall()
    if len(rows) >= HTTP_PROFILE_READ_LIMIT:
        raise AssessmentBatchError(
            "preview_query_limit",
            "This Project has too many HTTP profiles to classify safely.",
            status_code=409,
        )
    dialect = dialect_for_backend(get_db_backend())
    credentialed = 0
    for row in rows:
        has_private_context = any(
            (
                dialect.decode_json_list(row["headers_json"]),
                dialect.decode_json_dict(row["secret_refs_json"]),
                dialect.decode_json_dict(row["file_refs_json"]),
                str(row["login_workflow_id"] or ""),
                dialect.decode_json_list(row["token_capture_rules_json"]),
            )
        )
        credentialed += int(has_private_context)
    return len(rows), credentialed


def load_batch_preview_source(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
) -> BatchPreviewSource:
    """Load fixed preview metadata without materializing check rows."""
    assessment = _active_assessment(
        conn, session_id, team_id, project_id, assessment_id
    )
    enabled, credentialed = _http_profile_counts(conn, session_id, team_id, project_id)
    return BatchPreviewSource(assessment, enabled, credentialed)


def iter_batch_check_rows(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
) -> Iterator[Any]:
    """Stream frozen checks with their exact current confirmed target state."""
    assessment_owner_sql, assessment_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="a"
    )
    entity_owner_sql, entity_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    query = "".join(
        (
            "SELECT c.id AS check_id, c.assessment_id, c.category, c.check_key, ",
            "c.target_entity_id, c.target_type, c.target_value, c.applicability, ",
            "c.policy_level, c.state, c.state_source, c.state_reason, ",
            "c.recommended_action_key, a.profile_key, a.profile_version, ",
            "a.profile_snapshot, pl.source AS target_source, ",
            "pl.confidence AS target_confidence, e.id AS current_target_id, ",
            "e.type AS current_target_type, e.canonical_value AS current_target_value, ",
            "(SELECT COUNT(*) FROM project_assessment_evidence evidence ",
            "WHERE evidence.check_id = c.id AND evidence.source_state = 'unavailable') ",
            "AS unavailable_evidence_count FROM project_assessment_checks c ",
            "JOIN project_assessments a ON a.id = c.assessment_id ",
            "LEFT JOIN project_links pl ON pl.project_id = a.project_id ",
            "AND pl.entity_type = 'atlas_entity' AND pl.review_state = 'confirmed' ",
            "AND pl.entity_id = c.target_entity_id ",
            "LEFT JOIN entities e ON e.id = pl.entity_id AND ",
            entity_owner_sql,
            " AND COALESCE(e.suppressed, FALSE) = FALSE WHERE ",
            assessment_owner_sql,
            " AND a.project_id = ? AND a.id = ? AND a.status = 'active' ",
            "ORDER BY c.category, c.target_type, LOWER(c.target_value), c.check_key, c.id",
        )
    )
    cursor = conn.execute(
        query,
        (
            *entity_owner_params,
            *assessment_owner_params,
            project_id,
            assessment_id,
        ),
    )
    while True:
        rows = cursor.fetchmany(CHECK_FETCH_SIZE)
        if not rows:
            break
        yield from rows


__all__ = [
    "BatchPreviewSource",
    "iter_batch_check_rows",
    "load_batch_preview_source",
]
