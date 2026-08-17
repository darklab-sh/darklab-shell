# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Surface-neutral assessment-batch start and cancellation actions."""

from __future__ import annotations

from collections.abc import Mapping

from services.assessments.batch.cancellation import cancel_assessment_batch
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.execution import launch_assessment_batch
from services.assessments.batch.read_model import require_batch_parent
from services.assessments.batch.start import start_assessment_batch
from services.metrics_lazy import app_metrics


def start_confirmed_assessment_batch(
    session_id: str,
    project_id: str,
    assessment_id: str,
    confirmation: Mapping[str, object],
    *,
    team_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    owner_client_id: str = "",
    owner_tab_id: str = "",
) -> dict[str, object]:
    """Materialize a digest-pinned batch and fill its currently fair slots."""
    try:
        batch = start_assessment_batch(
            session_id,
            project_id,
            assessment_id,
            preview_id=str(confirmation.get("preview_id") or ""),
            plan_digest=confirmation.get("plan_digest"),
            confirmed=confirmation.get("confirmed"),
            standard_confirmed=confirmation.get("standard_confirmed", False),
            team_id=team_id,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            owner_client_id=owner_client_id,
            owner_tab_id=owner_tab_id,
        )
        batch_id = str(batch.get("batch_id") or "")
        launch = launch_assessment_batch(batch_id)
        current = require_batch_parent(session_id, batch_id, team_id=team_id)
    except AssessmentBatchError:
        app_metrics.record_assessment_batch_action("start", "rejected")
        raise
    except Exception:
        app_metrics.record_assessment_batch_action("start", "failed")
        raise
    app_metrics.record_assessment_batch_action("start", "accepted")
    return {"batch": current, "launch": launch}


def request_assessment_batch_cancellation(
    session_id: str,
    project_id: str,
    batch_id: str,
    *,
    team_id: str = "",
) -> dict[str, object]:
    """Cancel one owner- and Project-scoped batch without hiding signal failures."""
    try:
        current = require_batch_parent(session_id, batch_id, team_id=team_id)
        if str(current.get("project_id") or "") != str(project_id or ""):
            raise AssessmentBatchError(
                "batch_not_found", "Assessment batch wasn't found.", status_code=404
            )
        result = cancel_assessment_batch(session_id, batch_id, team_id=team_id)
        if result is None:
            raise AssessmentBatchError(
                "batch_not_found", "Assessment batch wasn't found.", status_code=404
            )
    except AssessmentBatchError:
        app_metrics.record_assessment_batch_action("cancel", "rejected")
        raise
    except Exception:
        app_metrics.record_assessment_batch_action("cancel", "failed")
        raise
    app_metrics.record_assessment_batch_action("cancel", "accepted")
    return result


__all__ = [
    "request_assessment_batch_cancellation",
    "start_confirmed_assessment_batch",
]
