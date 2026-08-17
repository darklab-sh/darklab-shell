# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 read routes for durable assessment batches."""

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.event_page import get_batch_event_page
from services.assessments.batch.read_model import (
    get_batch_item_page,
    list_assessment_batches,
    require_batch_parent,
)


def _error(exc: AssessmentBatchError):
    payload: dict[str, object] = {
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


@api_routes.api_v1_bp.get("/projects/<project_id>/assessment-batches")
@api_routes.limiter.limit(
    api_routes._api_team_read_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batches_list(project_id):
    try:
        session_id, owner_scope = _context()
        page = list_assessment_batches(
            session_id,
            team_id=owner_scope.team_id,
            project_id=project_id,
            assessment_id=request.args.get("assessment_id", ""),
            cursor=request.args.get("cursor", ""),
            limit=request.args.get("limit", 50),
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify(page)


@api_routes.api_v1_bp.get("/assessment-batches/<batch_id>")
@api_routes.limiter.limit(
    api_routes._api_team_read_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_get(batch_id):
    try:
        session_id, owner_scope = _context()
        batch = require_batch_parent(
            session_id, batch_id, team_id=owner_scope.team_id
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify({"batch": batch})


@api_routes.api_v1_bp.get("/assessment-batches/<batch_id>/items")
@api_routes.limiter.limit(
    api_routes._api_team_read_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_items(batch_id):
    try:
        session_id, owner_scope = _context()
        page = get_batch_item_page(
            session_id,
            batch_id,
            team_id=owner_scope.team_id,
            cursor=request.args.get("cursor", 0),
            limit=request.args.get("limit", 100),
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify(page)


@api_routes.api_v1_bp.get("/assessment-batches/<batch_id>/events")
@api_routes.limiter.limit(
    api_routes._api_team_read_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_events(batch_id):
    try:
        session_id, owner_scope = _context()
        page = get_batch_event_page(
            session_id,
            batch_id,
            team_id=owner_scope.team_id,
            cursor=request.args.get("cursor", 0),
            limit=request.args.get("limit", 100),
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify(page)


__all__ = [
    "api_assessment_batch_events",
    "api_assessment_batch_get",
    "api_assessment_batch_items",
    "api_assessment_batches_list",
]
