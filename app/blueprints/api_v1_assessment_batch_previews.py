# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 routes for bounded assessment-batch previews."""

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from blueprints.assessment_batch_request_body import selection_body as _selection_body
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.preview_compiler import compile_batch_preview
from services.assessments.batch.preview_storage import (
    get_batch_preview,
    get_batch_preview_items,
)


def _error(exc: AssessmentBatchError):
    payload = {
        "error": {
            "code": exc.code,
            "message": str(exc),
            **({"details": exc.details} if exc.details else {}),
        }
    }
    return jsonify(payload), exc.status_code


def _context():
    session_id = api_routes._require_session_id()
    return session_id, api_routes._api_request_scope()


@api_routes.api_v1_bp.post(
    "/projects/<project_id>/assessments/<assessment_id>/batch-previews"
)
@api_routes.limiter.limit(
    api_routes._api_team_write_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_preview_create(project_id, assessment_id):
    try:
        session_id, owner_scope = _context()
        preview = compile_batch_preview(
            session_id,
            project_id,
            assessment_id,
            _selection_body(),
            team_id=owner_scope.team_id,
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify({"preview": preview}), 201


@api_routes.api_v1_bp.get("/assessment-batch-previews/<preview_id>")
@api_routes.limiter.limit(
    api_routes._api_team_read_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_preview_get(preview_id):
    try:
        session_id, owner_scope = _context()
        preview = get_batch_preview(session_id, preview_id, team_id=owner_scope.team_id)
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify({"preview": preview})


@api_routes.api_v1_bp.get("/assessment-batch-previews/<preview_id>/items")
@api_routes.limiter.limit(
    api_routes._api_team_read_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_preview_items(preview_id):
    try:
        session_id, owner_scope = _context()
        page = get_batch_preview_items(
            session_id,
            preview_id,
            team_id=owner_scope.team_id,
            cursor=request.args.get("cursor", 0),
            limit=request.args.get("limit", 100),
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify(page)


__all__ = [
    "api_assessment_batch_preview_create",
    "api_assessment_batch_preview_get",
    "api_assessment_batch_preview_items",
]
