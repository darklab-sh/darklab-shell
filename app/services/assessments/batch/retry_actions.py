# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Surface-neutral confirmed start for immutable assessment-batch retries."""

from __future__ import annotations

from collections.abc import Mapping

from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.execution import launch_assessment_batch
from services.assessments.batch.read_model import require_batch_parent
from services.assessments.batch.start import start_assessment_batch
from services.metrics_lazy import app_metrics


def start_confirmed_assessment_batch_retry(
    session_id: str,
    project_id: str,
    assessment_id: str,
    source_batch_id: str,
    confirmation: Mapping[str, object],
    *,
    team_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    owner_client_id: str = "",
    owner_tab_id: str = "",
) -> dict[str, object]:
    try:
        batch = start_assessment_batch(
            session_id,
            project_id,
            assessment_id,
            preview_id=str(confirmation.get("preview_id") or ""),
            plan_digest=confirmation.get("plan_digest"),
            confirmed=confirmation.get("confirmed"),
            nuclei_snapshot_confirmed=confirmation.get("nuclei_snapshot_confirmed", False),
            standard_confirmed=confirmation.get("standard_confirmed", False),
            team_id=team_id,
            source_batch_id=source_batch_id,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            owner_client_id=owner_client_id,
            owner_tab_id=owner_tab_id,
        )
        batch_id = str(batch.get("batch_id") or "")
        launch = launch_assessment_batch(batch_id)
        current = require_batch_parent(session_id, batch_id, team_id=team_id)
    except AssessmentBatchError:
        app_metrics.record_assessment_batch_action("retry", "rejected")
        raise
    except Exception:
        app_metrics.record_assessment_batch_action("retry", "failed")
        raise
    app_metrics.record_assessment_batch_action("retry", "accepted")
    return {"batch": current, "launch": launch}


__all__ = ["start_confirmed_assessment_batch_retry"]
