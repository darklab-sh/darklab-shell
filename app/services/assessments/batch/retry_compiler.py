# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persist current immutable assessment-batch retry previews."""

from __future__ import annotations

from datetime import datetime

from services.assessments.batch.preview_storage import store_batch_preview
from services.assessments.batch.retry_draft import build_batch_retry_preview_draft


def compile_batch_retry_preview(
    session_id: str,
    project_id: str,
    assessment_id: str,
    source_batch_id: str,
    selection_data: object = None,
    *,
    team_id: str = "",
    current_time: datetime | None = None,
) -> dict[str, object]:
    """Compile and store one read-only retry preview against current state."""
    draft = build_batch_retry_preview_draft(
        session_id,
        project_id,
        assessment_id,
        source_batch_id,
        selection_data,
        team_id=team_id,
        current_time=current_time,
    )
    return store_batch_preview(draft, current_time=current_time)


__all__ = ["compile_batch_retry_preview"]
