# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Build complete assessment-batch preview drafts without persisting them."""

from __future__ import annotations

from datetime import datetime

from core.database_access import get_db_connect
from services.assessments.batch.preview_builder import BatchPreviewBuilder
from services.assessments.batch.preview_models import BatchPreviewDraft
from services.assessments.batch.preview_query import (
    iter_batch_check_rows,
    load_batch_preview_source,
)
from services.assessments.batch.preview_selection import normalize_preview_selection
from services.assessments.probe_runtime import probe_planning_runtime


def build_batch_preview_draft(
    session_id: str,
    project_id: str,
    assessment_id: str,
    selection_data: object = None,
    *,
    team_id: str = "",
    current_time: datetime | None = None,
) -> BatchPreviewDraft:
    """Build one current stable-ordered draft without creating durable rows."""
    del current_time
    selection = normalize_preview_selection(selection_data)
    runtime = probe_planning_runtime()
    with get_db_connect()() as conn:
        source = load_batch_preview_source(
            conn, session_id, team_id, project_id, assessment_id
        )
        builder = BatchPreviewBuilder(
            project_id,
            selection,
            runtime,
            source.assessment["profile_snapshot"],
        )
        for row in iter_batch_check_rows(
            conn, session_id, team_id, project_id, assessment_id
        ):
            builder.observe(row)
    items, summary = builder.finish(source)
    return BatchPreviewDraft(
        session_id=session_id,
        team_id=team_id,
        project_id=project_id,
        assessment_id=assessment_id,
        source_batch_id="",
        profile_key=str(source.assessment["profile_key"] or ""),
        profile_version=str(source.assessment["profile_version"] or ""),
        selection=selection.public(),
        summary=summary,
        concurrency=selection.concurrency,
        items=items,
    )

__all__ = ["build_batch_preview_draft"]
