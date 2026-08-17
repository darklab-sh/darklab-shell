# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persist current bounded assessment-batch preview drafts."""

from __future__ import annotations

from datetime import datetime

from services.assessments.batch.preview_draft import build_batch_preview_draft
from services.assessments.batch.preview_storage import store_batch_preview


def compile_batch_preview(
    session_id: str,
    project_id: str,
    assessment_id: str,
    selection_data: object = None,
    *,
    team_id: str = "",
    current_time: datetime | None = None,
) -> dict[str, object]:
    """Compile and persist one read-only bounded assessment-batch preview."""
    draft = build_batch_preview_draft(
        session_id,
        project_id,
        assessment_id,
        selection_data,
        team_id=team_id,
        current_time=current_time,
    )
    return store_batch_preview(draft, current_time=current_time)


__all__ = ["build_batch_preview_draft", "compile_batch_preview"]
