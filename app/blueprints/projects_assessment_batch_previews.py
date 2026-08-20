# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for bounded assessment-batch previews."""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_PREVIEW_REQUEST_MAX_BYTES,
)
from services.assessments.batch.preview_compiler import compile_batch_preview
from services.assessments.batch.preview_storage import (
    get_batch_preview,
    get_batch_preview_items,
)


def _error(exc: AssessmentBatchError):
    payload: dict[str, object] = {"error": str(exc), "code": exc.code}
    if exc.details:
        payload["details"] = exc.details
    return jsonify(payload), exc.status_code


def _selection_body() -> dict[str, object]:
    if (
        request.content_length
        and request.content_length > BATCH_PREVIEW_REQUEST_MAX_BYTES
    ):
        raise AssessmentBatchError(
            "batch_preview_request_too_large",
            "Assessment batch preview request exceeds the 64 KiB limit.",
            status_code=413,
        )
    data = request.get_json(silent=True)
    if data is None:
        if request.get_data(cache=True):
            raise AssessmentBatchError(
                "invalid_batch_selection",
                "Assessment batch selection must be valid JSON.",
            )
        return {}
    if not isinstance(data, dict):
        raise AssessmentBatchError(
            "invalid_batch_selection",
            "Assessment batch selection must be an object.",
        )
    return data


def _owner():
    return project_routes._project_owner()


@project_routes.projects_bp.post(
    "/projects/<project_id>/assessments/<assessment_id>/batch-previews"
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessment_batch_preview_create(project_id, assessment_id):
    session_id, team_id, error_response = _owner()
    if error_response:
        return error_response
    try:
        preview = compile_batch_preview(
            session_id,
            project_id,
            assessment_id,
            _selection_body(),
            team_id=team_id,
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify({"preview": preview}), 201


@project_routes.projects_bp.get("/assessment-batch-previews/<preview_id>")
def projects_assessment_batch_preview_get(preview_id):
    session_id, team_id, error_response = _owner()
    if error_response:
        return error_response
    try:
        preview = get_batch_preview(session_id, preview_id, team_id=team_id)
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify({"preview": preview})


@project_routes.projects_bp.get("/assessment-batch-previews/<preview_id>/items")
def projects_assessment_batch_preview_items(preview_id):
    session_id, team_id, error_response = _owner()
    if error_response:
        return error_response
    try:
        page = get_batch_preview_items(
            session_id,
            preview_id,
            team_id=team_id,
            cursor=request.args.get("cursor", 0),
            limit=request.args.get("limit", 100),
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    return jsonify(page)


__all__ = [
    "projects_assessment_batch_preview_create",
    "projects_assessment_batch_preview_get",
    "projects_assessment_batch_preview_items",
]
