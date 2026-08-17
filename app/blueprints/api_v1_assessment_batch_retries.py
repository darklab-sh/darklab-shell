# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 preview and confirmed start routes for assessment-batch retries."""

from typing import Any, cast

from flask import jsonify

from blueprints import api_v1 as api_routes
from blueprints.api_v1_assessment_batch_mutations import _audit, _body, _error, _mapping
from blueprints.api_v1_assessment_batch_previews import _selection_body
from core.helpers import get_log_session_id
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.lifecycle_contracts import normalize_batch_start_request
from services.assessments.batch.read_model import require_batch_parent
from services.assessments.batch.retry_actions import start_confirmed_assessment_batch_retry
from services.assessments.batch.retry_compiler import compile_batch_retry_preview
from services.audit.models import AuditEventType
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _source(session_id: str, team_id: str, project_id: str, batch_id: str):
    source = require_batch_parent(session_id, batch_id, team_id=team_id)
    if str(source.get("project_id") or "") != project_id:
        raise AssessmentBatchError(
            "batch_not_found", "Assessment batch wasn't found.", status_code=404
        )
    return source


@api_routes.api_v1_bp.post(
    "/projects/<project_id>/assessment-batches/<batch_id>/retry-previews"
)
@api_routes.limiter.limit(
    api_routes._api_team_write_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_retry_preview(project_id, batch_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        source = _source(session_id, owner_scope.team_id, project_id, batch_id)
        preview = compile_batch_retry_preview(
            session_id,
            project_id,
            str(source.get("assessment_id") or ""),
            batch_id,
            _selection_body(),
            team_id=owner_scope.team_id,
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify({"preview": preview}), 201


@api_routes.api_v1_bp.post(
    "/projects/<project_id>/assessment-batches/<batch_id>/retry"
)
@api_routes.limiter.limit(
    api_routes._api_team_write_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_retry(project_id, batch_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, Capability.RUN_COMMANDS)
        source = _source(session_id, owner_scope.team_id, project_id, batch_id)
        confirmation = normalize_batch_start_request(_body())
        result = start_confirmed_assessment_batch_retry(
            session_id,
            project_id,
            str(source.get("assessment_id") or ""),
            batch_id,
            confirmation,
            team_id=owner_scope.team_id,
            actor_member_id=str((owner_scope.member or {}).get("id") or ""),
            actor_role=(
                str((owner_scope.member or {}).get("role") or "")
                if owner_scope.is_team
                else ""
            ),
        )
    except (AssessmentBatchError, TeamPermissionDenied) as exc:
        return _error(exc)
    batch = _mapping(result.get("batch"))
    launch = _mapping(result.get("launch"))
    _audit(
        AuditEventType.ASSESSMENT_BATCH_RETRY,
        session_id,
        owner_scope,
        project_id,
        batch,
    )
    api_routes.log.info(
        "API_ASSESSMENT_BATCH_RETRY_STARTED",
        extra={
            "session": get_log_session_id(session_id),
            "team_id": owner_scope.team_id,
            "project_id": project_id,
            "assessment_id": str(batch.get("assessment_id") or ""),
            "source_batch_id": batch_id,
            "batch_id": str(batch.get("batch_id") or ""),
            "item_count": int(cast(Any, batch.get("item_count") or 0)),
            "launched_count": int(cast(Any, launch.get("launched") or 0)),
        },
    )
    return jsonify(result), 202


__all__ = ["api_assessment_batch_retry", "api_assessment_batch_retry_preview"]
