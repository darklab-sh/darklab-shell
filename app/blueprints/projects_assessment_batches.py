# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser read routes for durable assessment batches."""

from flask import jsonify, request

from blueprints import projects as project_routes
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.event_page import get_batch_event_page
from services.assessments.batch.read_model import (
    get_batch_item_page,
    list_assessment_batches,
    require_batch_parent,
)


def _error(exc: AssessmentBatchError):
    payload: dict[str, object] = {"error": str(exc), "code": exc.code}
    if exc.details:
        payload["details"] = exc.details
    return jsonify(payload), exc.status_code


def _owner():
    return project_routes._project_owner()


@project_routes.projects_bp.get("/projects/<project_id>/assessment-batches")
def projects_assessment_batches_list(project_id):
    session_id, team_id, error_response = _owner()
    if error_response:
        return error_response
    try:
        page = list_assessment_batches(
            session_id,
            team_id=team_id,
            project_id=project_id,
            assessment_id=request.args.get("assessment_id", ""),
            cursor=request.args.get("cursor", ""),
            limit=request.args.get("limit", 50),
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify(page)


@project_routes.projects_bp.get("/assessment-batches/<batch_id>")
def projects_assessment_batch_get(batch_id):
    session_id, team_id, error_response = _owner()
    if error_response:
        return error_response
    try:
        batch = require_batch_parent(session_id, batch_id, team_id=team_id)
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify({"batch": batch})


@project_routes.projects_bp.get("/assessment-batches/<batch_id>/items")
def projects_assessment_batch_items(batch_id):
    session_id, team_id, error_response = _owner()
    if error_response:
        return error_response
    try:
        page = get_batch_item_page(
            session_id,
            batch_id,
            team_id=team_id,
            cursor=request.args.get("cursor", 0),
            limit=request.args.get("limit", 100),
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify(page)


@project_routes.projects_bp.get("/assessment-batches/<batch_id>/events")
def projects_assessment_batch_events(batch_id):
    session_id, team_id, error_response = _owner()
    if error_response:
        return error_response
    try:
        page = get_batch_event_page(
            session_id,
            batch_id,
            team_id=team_id,
            cursor=request.args.get("cursor", 0),
            limit=request.args.get("limit", 100),
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify(page)


__all__ = [
    "projects_assessment_batch_events",
    "projects_assessment_batch_get",
    "projects_assessment_batch_items",
    "projects_assessment_batches_list",
]
