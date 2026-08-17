# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser start and cancellation routes for durable assessment batches."""

from collections.abc import Mapping

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.batch.lifecycle_actions import (
    request_assessment_batch_cancellation,
    start_confirmed_assessment_batch,
)
from services.assessments.batch.lifecycle_contracts import (
    BATCH_MUTATION_REQUEST_MAX_BYTES,
    normalize_batch_cancel_request,
    normalize_batch_start_request,
)
from services.audit.models import AuditEventType
from services.teams.capabilities import Capability


def _error(exc: AssessmentBatchError):
    payload: dict[str, object] = {"error": str(exc), "code": exc.code}
    if exc.details:
        payload["details"] = exc.details
    return jsonify(payload), exc.status_code


def _body(*, optional: bool = False) -> object:
    if request.content_length and request.content_length > BATCH_MUTATION_REQUEST_MAX_BYTES:
        raise AssessmentBatchError(
            "batch_mutation_request_too_large",
            "Assessment batch request exceeds the 16 KiB limit.",
            status_code=413,
        )
    data = request.get_json(silent=True)
    if data is None and request.get_data(cache=True):
        raise AssessmentBatchError(
            "invalid_batch_request", "Assessment batch request must be valid JSON."
        )
    if data is None and not optional:
        raise AssessmentBatchError(
            "invalid_batch_start", "Assessment batch start must be a JSON object."
        )
    return data


def _actor_role(session_id: str, team_id: str) -> str:
    if not team_id:
        return ""
    try:
        scope = project_routes.current_request_scope(session_id, request)
    except project_routes.RequestScopeError:
        return ""
    return str((scope.member or {}).get("role") or "")


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise AssessmentBatchError(
            "batch_state_mismatch",
            "Assessment batch lifecycle returned invalid state.",
            status_code=409,
        )
    return dict(value)


def _audit(
    event_type: AuditEventType,
    session_id: str,
    team_id: str,
    project_id: str,
    batch: dict[str, object],
    *,
    source: str,
) -> None:
    project_routes.record_event(
        event_type,
        target_id=str(batch.get("batch_id") or ""),
        project_id=project_id,
        details={
            "source": source,
            "project_id": project_id,
            "assessment_id": str(batch.get("assessment_id") or ""),
            "batch_id": str(batch.get("batch_id") or ""),
            "status": str(batch.get("status") or ""),
            "count": int(batch.get("item_count") or 0),
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )


@project_routes.projects_bp.post(
    "/projects/<project_id>/assessments/<assessment_id>/assessment-batches"
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessment_batch_start(project_id, assessment_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.RUN_COMMANDS
    )
    if error_response:
        return error_response
    try:
        confirmation = normalize_batch_start_request(_body())
        from blueprints import run as run_routes  # noqa: PLC0415

        result = start_confirmed_assessment_batch(
            session_id,
            project_id,
            assessment_id,
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
        AuditEventType.ASSESSMENT_BATCH_START,
        session_id,
        team_id,
        project_id,
        batch,
        source="browser",
    )
    project_routes.log.info(
        "PROJECT_ASSESSMENT_BATCH_STARTED",
        extra={
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "assessment_id": assessment_id,
            "batch_id": str(batch.get("batch_id") or ""),
            "item_count": int(batch.get("item_count") or 0),
            "launched_count": int(launch.get("launched") or 0),
        },
    )
    return jsonify(result), 202


@project_routes.projects_bp.post(
    "/projects/<project_id>/assessment-batches/<batch_id>/cancel"
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessment_batch_cancel(project_id, batch_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.RUN_COMMANDS
    )
    if error_response:
        return error_response
    try:
        normalize_batch_cancel_request(_body(optional=True))
        result = request_assessment_batch_cancellation(
            session_id, project_id, batch_id, team_id=team_id
        )
    except AssessmentBatchError as exc:
        return _error(exc)
    batch = _mapping(result.get("batch"))
    _audit(
        AuditEventType.ASSESSMENT_BATCH_CANCEL,
        session_id,
        team_id,
        project_id,
        batch,
        source="browser",
    )
    project_routes.log.info(
        "PROJECT_ASSESSMENT_BATCH_CANCEL_REQUESTED",
        extra={
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "assessment_id": str(batch.get("assessment_id") or ""),
            "batch_id": batch_id,
            "batch_status": str(batch.get("status") or ""),
            "signal_failure_count": int(result.get("signal_failures") or 0),
        },
    )
    return jsonify(result)


__all__ = [
    "projects_assessment_batch_cancel",
    "projects_assessment_batch_start",
]
