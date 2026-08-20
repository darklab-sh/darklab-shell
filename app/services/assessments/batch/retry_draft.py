# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Rebuild immutable retry previews from current cycle and source outcomes."""

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
from services.assessments.batch.retry_scope import load_batch_retry_scope_on_conn
from services.assessments.probe_runtime import probe_planning_runtime


def build_batch_retry_preview_draft(
    session_id: str,
    project_id: str,
    assessment_id: str,
    source_batch_id: str,
    selection_data: object = None,
    *,
    team_id: str = "",
    current_time: datetime | None = None,
) -> BatchPreviewDraft:
    """Build a new plan only for failed or unfinished source work."""
    del current_time
    selection = normalize_preview_selection(selection_data)
    runtime = probe_planning_runtime()
    with get_db_connect()() as conn:
        source = load_batch_preview_source(
            conn, session_id, team_id, project_id, assessment_id
        )
        retry_scope = load_batch_retry_scope_on_conn(
            conn,
            session_id,
            team_id,
            project_id,
            assessment_id,
            source_batch_id,
        )
        builder = BatchPreviewBuilder(
            project_id,
            selection,
            runtime,
            source.assessment["profile_snapshot"],
        )
        seen_check_ids: set[str] = set()
        for row in iter_batch_check_rows(
            conn, session_id, team_id, project_id, assessment_id
        ):
            check_id = str(row["check_id"] or "")
            if check_id in retry_scope.eligible_check_ids:
                seen_check_ids.add(check_id)
                builder.observe(row)
            else:
                builder.target_ids.add(str(row["target_entity_id"] or ""))
                builder.categories.add(str(row["category"] or ""))
        missing = retry_scope.eligible_check_ids - seen_check_ids
        if missing:
            builder.reasons["retry_check_missing"] += len(missing)
    items, summary = builder.finish(source, allow_empty=True)
    summary.update(retry_scope.public_summary())
    return BatchPreviewDraft(
        session_id=session_id,
        team_id=team_id,
        project_id=project_id,
        assessment_id=assessment_id,
        source_batch_id=retry_scope.source_batch_id,
        profile_key=str(source.assessment["profile_key"] or ""),
        profile_version=str(source.assessment["profile_version"] or ""),
        selection=selection.public(),
        summary=summary,
        concurrency=selection.concurrency,
        items=items,
    )


__all__ = ["build_batch_retry_preview_draft"]
