# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Database-facing facade for bounded assessment-batch preview compilation."""

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
from services.assessments.batch.preview_storage import store_batch_preview
from services.assessments.probe_runtime import probe_planning_runtime


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
    draft = BatchPreviewDraft(
        session_id=session_id,
        team_id=team_id,
        project_id=project_id,
        assessment_id=assessment_id,
        profile_key=str(source.assessment["profile_key"] or ""),
        profile_version=str(source.assessment["profile_version"] or ""),
        selection=selection.public(),
        summary=summary,
        concurrency=selection.concurrency,
        items=items,
    )
    return store_batch_preview(draft, current_time=current_time)


__all__ = ["compile_batch_preview"]
