# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Refresh managed Nuclei templates and rebuild one complete batch preview."""

from __future__ import annotations

from core.database_access import get_db_connect
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.nuclei_preflight import batch_nuclei_preflight
from services.assessments.batch.nuclei_refresh_preview import rebuild_refreshed_preview
from services.assessments.batch.preview_storage import (
    get_batch_preview,
    store_batch_preview,
)
from services.assessments.batch.start_rebuild import rebuild_confirmed_batch_preview
from services.nuclei.template_refresh import (
    NucleiTemplateRefreshError,
    refresh_managed_nuclei_templates,
)


def active_nuclei_assessment_batch_exists() -> bool:
    """Return whether any nonterminal batch still depends on the shared cache."""
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT 1 FROM workflow_executions execution WHERE "
            "execution.execution_kind = 'assessment_batch' "
            "AND execution.status IN ('queued', 'running', 'canceling') "
            "AND EXISTS (SELECT 1 FROM assessment_batch_items item "
            "WHERE item.batch_id = execution.id AND item.action_id = 'nuclei') LIMIT 1"
        ).fetchone()
    return row is not None


def refresh_and_rebuild_batch_preview(
    session_id: str,
    project_id: str,
    assessment_id: str,
    preview_id: str,
    *,
    team_id: str = "",
) -> dict[str, object]:
    """Validate intent, refresh once, then persist a new approval snapshot."""
    preview = get_batch_preview(session_id, preview_id, team_id=team_id)
    if (
        str(preview.get("project_id") or "") != project_id
        or str(preview.get("assessment_id") or "") != assessment_id
    ):
        raise AssessmentBatchError(
            "batch_confirmation_mismatch",
            "The assessment batch preview doesn't match this Project cycle.",
            status_code=409,
        )
    source_batch_id = str(preview.get("source_batch_id") or "")
    current = rebuild_confirmed_batch_preview(
        session_id,
        project_id,
        assessment_id,
        preview,
        source_batch_id=source_batch_id,
        team_id=team_id,
    )
    if not batch_nuclei_preflight(current.summary):
        raise AssessmentBatchError(
            "nuclei_template_refresh_not_needed",
            "This assessment preview doesn't contain selected Nuclei commands.",
            status_code=409,
        )
    try:
        refresh = refresh_managed_nuclei_templates(
            active_batch_exists=active_nuclei_assessment_batch_exists,
        )
    except NucleiTemplateRefreshError as exc:
        raise AssessmentBatchError(exc.code, str(exc), status_code=exc.status_code) from exc
    rebuilt = rebuild_refreshed_preview(
        session_id, project_id, assessment_id, preview, source_batch_id, team_id,
    )
    return {
        "refresh": refresh,
        "preview": store_batch_preview(rebuilt),
    }


__all__ = [
    "active_nuclei_assessment_batch_exists",
    "refresh_and_rebuild_batch_preview",
]
