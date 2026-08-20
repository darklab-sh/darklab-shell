# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser preview and confirmed start routes for assessment-batch retries."""

from typing import Any, cast

from flask import jsonify, request

from blueprints import projects as project_routes
from blueprints.projects_assessment_batch_mutations import (
    _actor_role,
    _audit,
    _body,
    _error,
    _mapping,
)
from blueprints.projects_assessment_batch_previews import (
    _error as _preview_error,
    _owner,
    _selection_body,
)
from extensions import limiter
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.lifecycle_contracts import normalize_batch_start_request
from services.assessments.batch.read_model import require_batch_parent
from services.assessments.batch.retry_actions import start_confirmed_assessment_batch_retry
from services.assessments.batch.retry_compiler import compile_batch_retry_preview
from services.audit.models import AuditEventType
from services.teams.capabilities import Capability


def _source(session_id: str, team_id: str, project_id: str, batch_id: str):
    source = require_batch_parent(session_id, batch_id, team_id=team_id)
    if str(source.get("project_id") or "") != project_id:
        raise AssessmentBatchError(
            "batch_not_found", "Assessment batch wasn't found.", status_code=404
        )
    return source


@project_routes.projects_bp.post(
    "/projects/<project_id>/assessment-batches/<batch_id>/retry-previews"
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessment_batch_retry_preview(project_id, batch_id):
    session_id, team_id, error_response = _owner()
    if error_response:
        return error_response
    try:
        source = _source(session_id, team_id, project_id, batch_id)
        preview = compile_batch_retry_preview(
            session_id,
            project_id,
            str(source.get("assessment_id") or ""),
            batch_id,
            _selection_body(),
            team_id=team_id,
        )
    except AssessmentBatchError as exc:
        return _preview_error(exc)
    return jsonify({"preview": preview}), 201


@project_routes.projects_bp.post(
    "/projects/<project_id>/assessment-batches/<batch_id>/retry"
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessment_batch_retry(project_id, batch_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.RUN_COMMANDS
    )
    if error_response:
        return error_response
    try:
        source = _source(session_id, team_id, project_id, batch_id)
        confirmation = normalize_batch_start_request(_body())
        from blueprints import run as run_routes  # noqa: PLC0415

        result = start_confirmed_assessment_batch_retry(
            session_id,
            project_id,
            str(source.get("assessment_id") or ""),
            batch_id,
            confirmation,
            team_id=team_id,
            actor_member_id=project_routes._project_actor_member_id(
                session_id, team_id
            ),
            actor_role=_actor_role(session_id, team_id),
            owner_client_id=run_routes._active_run_owner_value(
                request.headers.get("X-Client-ID", "")
            ),
            owner_tab_id=run_routes._active_run_owner_value(
                confirmation.get("tab_id", "")
            ),
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    batch = _mapping(result.get("batch"))
    launch = _mapping(result.get("launch"))
    _audit(
        AuditEventType.ASSESSMENT_BATCH_RETRY,
        session_id,
        team_id,
        project_id,
        batch,
        source="browser",
    )
    project_routes.log.info(
        "PROJECT_ASSESSMENT_BATCH_RETRY_STARTED",
        extra={
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "assessment_id": str(batch.get("assessment_id") or ""),
            "source_batch_id": batch_id,
            "batch_id": str(batch.get("batch_id") or ""),
            "item_count": int(cast(Any, batch.get("item_count") or 0)),
            "launched_count": int(cast(Any, launch.get("launched") or 0)),
        },
    )
    return jsonify(result), 202


__all__ = ["projects_assessment_batch_retry", "projects_assessment_batch_retry_preview"]
