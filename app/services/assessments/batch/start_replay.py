# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Idempotent lookup for already-confirmed assessment-batch previews."""

from __future__ import annotations

import hmac

from core.database_access import get_db_connect
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.storage_read import get_batch_parent
from services.projects.scope import shared_owner_where


def confirmed_batch_replay(
    session_id: str,
    project_id: str,
    assessment_id: str,
    preview_id: str,
    preview_digest: str,
    *,
    team_id: str = "",
    expected_source_batch_id: str = "",
) -> dict[str, object] | None:
    """Return an already-started batch only for the same preview lineage."""
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p"
    )
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT p.plan_digest, p.started_execution_id, p.source_execution_id "
            "FROM assessment_batch_previews p WHERE "
            + owner_sql  # nosec B608: fixed owner clause
            + " AND p.id = ? AND p.project_id = ? AND p.assessment_id = ?",
            (*owner_params, preview_id, project_id, assessment_id),
        ).fetchone()
    if not row:
        return None
    if (
        str(row["source_execution_id"] or "")
        != str(expected_source_batch_id or "").strip()
        or not hmac.compare_digest(str(row["plan_digest"] or ""), preview_digest)
    ):
        raise AssessmentBatchError(
            "batch_confirmation_mismatch",
            "The assessment batch approval doesn't match this cycle preview.",
            status_code=409,
        )
    batch_id = str(row["started_execution_id"] or "")
    if not batch_id:
        return None
    batch = get_batch_parent(session_id, batch_id, team_id=team_id)
    if not batch:
        raise AssessmentBatchError(
            "batch_state_mismatch",
            "The confirmed assessment batch couldn't be loaded.",
            status_code=409,
        )
    return batch


__all__ = ["confirmed_batch_replay"]
