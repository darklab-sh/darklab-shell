# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Digest-pinned confirmed start for one current assessment-batch preview."""

from __future__ import annotations

import hmac
from collections.abc import Mapping

from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_DEFAULT_MAX_ACTIVE_PER_OWNER,
)
from services.assessments.batch.preview_digest import batch_preview_digest
from services.assessments.batch.preview_draft import build_batch_preview_draft
from services.assessments.batch.preview_storage import get_batch_preview
from services.assessments.batch.start_storage import (
    confirmed_batch_replay,
    materialize_confirmed_batch,
)


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _approval_digest(value: object) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise AssessmentBatchError(
            "invalid_batch_confirmation",
            "Assessment batch approval digest is invalid.",
        )
    return digest


def _selection_for_rebuild(preview: Mapping[str, object]) -> dict[str, object]:
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


def start_assessment_batch(
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    preview_id: str,
    plan_digest: object,
    confirmed: object,
    standard_confirmed: object = False,
    team_id: str = "",
    source_batch_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    owner_client_id: str = "",
    owner_tab_id: str = "",
    max_active: int = BATCH_DEFAULT_MAX_ACTIVE_PER_OWNER,
) -> dict[str, object]:
    """Rebuild, verify, and atomically materialize one immutable batch snapshot."""
    if confirmed is not True:
        raise AssessmentBatchError(
            "batch_confirmation_required",
            "Starting an assessment batch requires explicit confirmation.",
            status_code=409,
        )
    if not isinstance(standard_confirmed, bool):
        raise AssessmentBatchError(
            "invalid_batch_confirmation",
            "standard_confirmed must be true or false.",
        )
    digest = _approval_digest(plan_digest)
    replay = confirmed_batch_replay(
        session_id,
        project_id,
        assessment_id,
        preview_id,
        digest,
        team_id=team_id,
    )
    if replay:
        return replay
    preview = get_batch_preview(session_id, preview_id, team_id=team_id)
    stored_digest = str(preview.get("plan_digest") or "")
    if (
        str(preview.get("project_id") or "") != project_id
        or str(preview.get("assessment_id") or "") != assessment_id
        or not hmac.compare_digest(stored_digest, digest)
    ):
        raise AssessmentBatchError(
            "batch_confirmation_mismatch",
            "The assessment batch approval doesn't match this cycle preview.",
            status_code=409,
        )
    try:
        current_draft = build_batch_preview_draft(
            session_id,
            project_id,
            assessment_id,
            _selection_for_rebuild(preview),
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
    current_digest = batch_preview_digest(current_draft)
    if not hmac.compare_digest(current_digest, stored_digest):
        raise AssessmentBatchError(
            "batch_preview_stale",
            "The assessment batch plan changed; create and review a new preview.",
            status_code=409,
        )
    selected_items = sum(int(item.selected) for item in current_draft.items)
    return materialize_confirmed_batch(
        session_id=session_id,
        team_id=team_id,
        project_id=project_id,
        assessment_id=assessment_id,
        preview_id=preview_id,
        preview_digest=digest,
        item_count=selected_items,
        concurrency=current_draft.concurrency,
        standard_confirmed=standard_confirmed,
        source_batch_id=source_batch_id,
        actor_member_id=actor_member_id,
        actor_role=actor_role,
        owner_client_id=owner_client_id,
        owner_tab_id=owner_tab_id,
        max_active=max_active,
    )


__all__ = ["start_assessment_batch"]
