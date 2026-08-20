# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser mutation route for managed Nuclei assessment templates."""

from typing import Any, cast

from flask import jsonify

from blueprints import projects as project_routes
from extensions import limiter
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.nuclei_refresh import refresh_and_rebuild_batch_preview
from services.audit.models import AuditEventType
from services.teams.capabilities import Capability


def _error(exc: AssessmentBatchError):
    payload: dict[str, object] = {"error": str(exc), "code": exc.code}
    if exc.details:
        payload["details"] = exc.details
    return jsonify(payload), exc.status_code


@project_routes.projects_bp.post(
    "/projects/<project_id>/assessments/<assessment_id>/batch-previews/"
    "<preview_id>/nuclei-templates/refresh"
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessment_nuclei_templates_refresh(
    project_id: str,
    assessment_id: str,
    preview_id: str,
):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.RUN_COMMANDS
    )
    if error_response:
        return error_response
    try:
        result = refresh_and_rebuild_batch_preview(
            session_id,
            project_id,
            assessment_id,
            preview_id,
            team_id=team_id,
        )
    except AssessmentBatchError as exc:
        project_routes.log.warning(
            "PROJECT_NUCLEI_TEMPLATE_REFRESH_REJECTED",
            extra={
                "session": project_routes.get_log_session_id(session_id),
                "team_id": team_id,
                "project_id": project_id,
                "assessment_id": assessment_id,
                "reason_code": exc.code,
            },
        )
        return _error(exc)
    preview = cast(dict[str, Any], result.get("preview") or {})
    refresh = cast(dict[str, Any], result.get("refresh") or {})
    project_routes.record_event(
        AuditEventType.ASSESSMENT_NUCLEI_TEMPLATE_REFRESH,
        target_id=assessment_id,
        project_id=project_id,
        details={
            "source": "browser",
            "project_id": project_id,
            "status": str(refresh.get("status") or ""),
            "count": int(preview.get("selected_item_count") or 0),
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info(
        "PROJECT_NUCLEI_TEMPLATE_REFRESHED",
        extra={
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "assessment_id": assessment_id,
            "release_version": str(refresh.get("release_version") or ""),
        },
    )
    return jsonify(result)


__all__ = ["projects_assessment_nuclei_templates_refresh"]
