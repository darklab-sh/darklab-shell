# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 start and cancellation routes for durable assessment batches."""

from collections.abc import Mapping

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_log_session_id
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
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _error(exc: Exception):
    if isinstance(exc, AssessmentBatchError):
        payload: dict[str, object] = {
            "error": {
                "code": exc.code,
                "message": str(exc),
                **({"details": exc.details} if exc.details else {}),
            }
        }
        return jsonify(payload), exc.status_code
    if isinstance(exc, TeamPermissionDenied):
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    raise exc


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
    owner_scope,
    project_id: str,
    batch: dict[str, object],
) -> None:
    record_event(
        event_type,
        target_id=str(batch.get("batch_id") or ""),
        project_id=project_id,
        details={
            "source": "api_v1",
            "project_id": project_id,
            "assessment_id": str(batch.get("assessment_id") or ""),
            "batch_id": str(batch.get("batch_id") or ""),
            "status": str(batch.get("status") or ""),
            "count": int(batch.get("item_count") or 0),
        },
        **route_audit_fields(session_id, request, owner_scope),
    )


@api_routes.api_v1_bp.post(
    "/projects/<project_id>/assessments/<assessment_id>/assessment-batches"
)
@api_routes.limiter.limit(
    api_routes._api_team_write_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_start(project_id, assessment_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(
            owner_scope, Capability.RUN_COMMANDS
        )
        confirmation = normalize_batch_start_request(_body())
        result = start_confirmed_assessment_batch(
            session_id,
            project_id,
            assessment_id,
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
        AuditEventType.ASSESSMENT_BATCH_START,
        session_id,
        owner_scope,
        project_id,
        batch,
    )
    api_routes.log.info(
        "API_ASSESSMENT_BATCH_STARTED",
        extra={
            "session": get_log_session_id(session_id),
            "team_id": owner_scope.team_id,
            "project_id": project_id,
            "assessment_id": assessment_id,
            "batch_id": str(batch.get("batch_id") or ""),
            "item_count": int(batch.get("item_count") or 0),
            "launched_count": int(launch.get("launched") or 0),
        },
    )
    return jsonify(result), 202


@api_routes.api_v1_bp.post(
    "/projects/<project_id>/assessment-batches/<batch_id>/cancel"
)
@api_routes.limiter.limit(
    api_routes._api_team_write_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_assessment_batch_cancel(project_id, batch_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(
            owner_scope, Capability.RUN_COMMANDS
        )
        normalize_batch_cancel_request(_body(optional=True))
        result = request_assessment_batch_cancellation(
            session_id, project_id, batch_id, team_id=owner_scope.team_id
        )
    except (AssessmentBatchError, TeamPermissionDenied) as exc:
        return _error(exc)
    batch = _mapping(result.get("batch"))
    _audit(
        AuditEventType.ASSESSMENT_BATCH_CANCEL,
        session_id,
        owner_scope,
        project_id,
        batch,
    )
    api_routes.log.info(
        "API_ASSESSMENT_BATCH_CANCEL_REQUESTED",
        extra={
            "session": get_log_session_id(session_id),
            "team_id": owner_scope.team_id,
            "project_id": project_id,
            "assessment_id": str(batch.get("assessment_id") or ""),
            "batch_id": batch_id,
            "batch_status": str(batch.get("status") or ""),
            "signal_failure_count": int(result.get("signal_failures") or 0),
        },
    )
    return jsonify(result)


__all__ = ["api_assessment_batch_cancel", "api_assessment_batch_start"]
