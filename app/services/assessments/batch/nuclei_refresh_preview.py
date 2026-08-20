# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Post-refresh Nuclei preview rebuild and launch-readiness checks."""

from collections.abc import Mapping

from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.nuclei_preflight import batch_nuclei_preflight
from services.assessments.batch.preview_models import BatchPreviewDraft
from services.assessments.batch.start_rebuild import rebuild_confirmed_batch_preview


def rebuild_refreshed_preview(
    session_id: str,
    project_id: str,
    assessment_id: str,
    preview: Mapping[str, object],
    source_batch_id: str,
    team_id: str,
) -> BatchPreviewDraft:
    """Rebuild a preview and reject a cache that still fails Nuclei preflight."""
    rebuilt = rebuild_confirmed_batch_preview(
        session_id,
        project_id,
        assessment_id,
        preview,
        source_batch_id=source_batch_id,
        team_id=team_id,
    )
    preflight = batch_nuclei_preflight(rebuilt.summary)
    if preflight.get("launchable") is not True or preflight.get("state") != "ready":
        raise AssessmentBatchError(
            "nuclei_template_refresh_unready",
            "The managed templates were updated, but the rebuilt plan's Nuclei preflight isn't ready.",
            status_code=409,
            details={
                "state": str(preflight.get("state") or "unavailable"),
                "validation_state": str(preflight.get("validation_state") or "not_run"),
                "reason_code": str(preflight.get("reason_code") or ""),
            },
        )
    return rebuilt


__all__ = ["rebuild_refreshed_preview"]
