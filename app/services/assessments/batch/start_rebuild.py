# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Current-state rebuild for a digest-confirmed assessment-batch preview."""

from __future__ import annotations

from collections.abc import Mapping

from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.preview_draft import build_batch_preview_draft
from services.assessments.batch.preview_models import BatchPreviewDraft
from services.assessments.batch.retry_draft import build_batch_retry_preview_draft


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _selection(preview: Mapping[str, object]) -> dict[str, object]:
    selection = _mapping(preview.get("selection"))
    concurrency = _mapping(preview.get("concurrency"))
    selection.update(
        {
            "max_parallel": concurrency.get("batch"),
            "max_owner_parallel": concurrency.get("owner"),
            "max_instance_parallel": concurrency.get("instance"),
        }
    )
    return selection


def rebuild_confirmed_batch_preview(
    session_id: str,
    project_id: str,
    assessment_id: str,
    preview: Mapping[str, object],
    *,
    source_batch_id: str,
    team_id: str,
) -> BatchPreviewDraft:
    """Regenerate the current initial or retry draft for stale-plan detection."""
    try:
        if source_batch_id:
            return build_batch_retry_preview_draft(
                session_id,
                project_id,
                assessment_id,
                source_batch_id,
                _selection(preview),
                team_id=team_id,
            )
        return build_batch_preview_draft(
            session_id,
            project_id,
            assessment_id,
            _selection(preview),
            team_id=team_id,
        )
    except AssessmentBatchError as exc:
        if exc.code == "assessment_not_active":
            raise
        raise AssessmentBatchError(
            "batch_preview_stale",
            "The assessment batch plan changed; create and review a new preview.",
            status_code=409,
            details={"reason_code": exc.code},
        ) from exc


__all__ = ["rebuild_confirmed_batch_preview"]
