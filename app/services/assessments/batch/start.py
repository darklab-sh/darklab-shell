# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Digest-pinned confirmed start for one current assessment-batch preview."""

from __future__ import annotations

import hmac

from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.preview_digest import batch_preview_digest
from services.assessments.batch.nuclei_preflight import validate_batch_nuclei_preflight
from services.assessments.batch.nuclei_lock import assessment_batch_nuclei_cache_lock
from services.assessments.batch.preview_storage import get_batch_preview
from services.assessments.batch.start_rebuild import rebuild_confirmed_batch_preview
from services.assessments.batch.start_replay import confirmed_batch_replay
from services.assessments.batch.start_storage import materialize_confirmed_batch


def _approval_digest(value: object) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise AssessmentBatchError(
            "invalid_batch_confirmation",
            "Assessment batch approval digest is invalid.",
        )
    return digest


def start_assessment_batch(
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    preview_id: str,
    plan_digest: object,
    confirmed: object,
    nuclei_snapshot_confirmed: object = False,
    standard_confirmed: object = False,
    team_id: str = "",
    source_batch_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    owner_client_id: str = "",
    owner_tab_id: str = "",
    max_active: int | None = None,
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
    if not isinstance(nuclei_snapshot_confirmed, bool):
        raise AssessmentBatchError(
            "invalid_batch_confirmation",
            "nuclei_snapshot_confirmed must be true or false.",
        )
    digest = _approval_digest(plan_digest)
    normalized_source = str(source_batch_id or "").strip()
    replay = confirmed_batch_replay(
        session_id,
        project_id,
        assessment_id,
        preview_id,
        digest,
        team_id=team_id,
        expected_source_batch_id=normalized_source,
    )
    if replay:
        return replay
    preview = get_batch_preview(session_id, preview_id, team_id=team_id)
    stored_digest = str(preview.get("plan_digest") or "")
    if (
        str(preview.get("project_id") or "") != project_id
        or str(preview.get("assessment_id") or "") != assessment_id
        or str(preview.get("source_batch_id") or "") != normalized_source
        or not hmac.compare_digest(stored_digest, digest)
    ):
        raise AssessmentBatchError(
            "batch_confirmation_mismatch",
            "The assessment batch approval doesn't match this cycle preview.",
            status_code=409,
        )
    with assessment_batch_nuclei_cache_lock(preview.get("summary")):
        current_draft = rebuild_confirmed_batch_preview(
            session_id,
            project_id,
            assessment_id,
            preview,
            source_batch_id=normalized_source,
            team_id=team_id,
        )
        validate_batch_nuclei_preflight(
            current_draft.summary,
            stale_confirmed=nuclei_snapshot_confirmed,
        )
        current_digest = batch_preview_digest(current_draft)
        if not hmac.compare_digest(current_digest, stored_digest):
            raise AssessmentBatchError(
                "batch_preview_stale",
                "The assessment batch plan changed; create and review a new preview.",
                status_code=409,
            )
        selected_items = sum(int(item.selected) for item in current_draft.items)
        if not selected_items:
            raise AssessmentBatchError(
                "empty_batch_retry",
                "No failed or unfinished commands are currently eligible to retry.",
                status_code=409,
            )
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
            source_batch_id=normalized_source,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            owner_client_id=owner_client_id,
            owner_tab_id=owner_tab_id,
            max_active=max_active,
        )


__all__ = ["start_assessment_batch"]
