# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 Project assessment-cycle routes."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from blueprints.assessment_batch_lifecycle import (
    assessment_check_filters as _check_filters,
    batch_lifecycle_pending_response,
)
from core.helpers import get_client_ip, get_log_session_id
from services.assessments.contracts import (
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
)
from services.assessments.batch.lifecycle_guard import BatchLifecycleCancellation
from services.assessments.lifecycle import (
    delete_assessment_cycle,
    preview_assessment_deletion,
    update_assessment_cycle,
)
from services.assessments.profile_summaries import list_assessment_profile_summaries
from services.assessments.read_model import (
    get_assessment_read_model,
    list_assessment_cycles,
)
from services.assessments.storage import create_assessment_cycle
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _assessment_api_error(exc: Exception):
    if isinstance(exc, AssessmentNotFound):
        code, status = "not_found", 404
    elif isinstance(exc, ProjectWorkspaceQuotaExceeded):
        code, status = "quota_exceeded", 409
    elif isinstance(exc, AssessmentConflict):
        code, status = "assessment_conflict", 409
    elif isinstance(exc, TeamPermissionDenied):
        code, status = "team_forbidden", 403
    else:
        code, status = "invalid_assessment", 400
    return api_routes._api_json_error(code, str(exc), status)


def _request_context(*, write: bool = False):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    if write:
        api_routes._require_api_team_capability(
            owner_scope,
            Capability.MUTATE_PROJECTS,
        )
    actor_member_id = str((owner_scope.member or {}).get("id") or "")
    return session_id, owner_scope, actor_member_id


def _bool_arg(name: str) -> bool:
    return str(request.args.get(name) or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _audit_details(assessment: dict, *, transition_kind: str, **details):
    return {
        "source": "api_v1",
        "project_id": str(assessment.get("project_id") or ""),
        "assessment_id": str(assessment.get("id") or ""),
        "profile_key": str(assessment.get("profile_key") or ""),
        "profile_version": str(assessment.get("profile_version") or ""),
        "status": str(assessment.get("status") or ""),
        "transition_kind": transition_kind,
        **details,
    }


def _log_fields(
    session_id: str,
    owner_scope,
    project_id: str,
    assessment_id: str = "",
    **details,
):
    return {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": owner_scope.team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "source": "api_v1",
        **details,
    }


@api_routes.api_v1_bp.route("/projects/<project_id>/assessments")
@api_routes.require_api_auth
def api_project_assessments(project_id):
    try:
        session_id, owner_scope, _actor_member_id = _request_context()
        page = list_assessment_cycles(
            session_id,
            project_id,
            status=request.args.get("status") or "",
            include_archived=_bool_arg("include_archived"),
            limit=api_routes._parse_int(
                request.args.get("limit"),
                50,
                minimum=1,
                maximum=200,
            ),
            offset=api_routes._parse_int(
                request.args.get("offset"),
                0,
                minimum=0,
                maximum=100000,
            ),
            team_id=owner_scope.team_id,
        )
    except AssessmentError as exc:
        return _assessment_api_error(exc)
    if page is None:
        return api_routes._api_json_error("not_found", "Project not found.", 404)
    page["profiles"] = list_assessment_profile_summaries()
    return jsonify(page)


@api_routes.api_v1_bp.route("/projects/<project_id>/assessments", methods=["POST"])
@api_routes.require_api_auth
def api_project_assessment_create(project_id):
    try:
        session_id, owner_scope, actor_member_id = _request_context(write=True)
        data = api_routes._json_body()
        if set(data) - {"profile_key", "title"}:
            raise AssessmentError("assessment payload contains unsupported fields")
        created = create_assessment_cycle(
            session_id,
            project_id,
            str(data.get("profile_key") or ""),
            title=str(data.get("title") or ""),
            team_id=owner_scope.team_id,
            actor_member_id=actor_member_id,
        )
        assessment = created["assessment"]
        record_event(
            AuditEventType.ASSESSMENT_CREATE,
            target_id=assessment["id"],
            project_id=project_id,
            details=_audit_details(
                assessment,
                transition_kind="create",
                count=int(created["rollup"].get("total_checks") or 0),
            ),
            **route_audit_fields(session_id, request, owner_scope),
        )
    except (AssessmentError, ProjectWorkspaceQuotaExceeded, TeamPermissionDenied) as exc:
        return _assessment_api_error(exc)
    api_routes.log.info(
        "API_PROJECT_ASSESSMENT_CREATED",
        extra=_log_fields(
            session_id,
            owner_scope,
            project_id,
            assessment["id"],
            profile_key=assessment["profile_key"],
            profile_version=assessment["profile_version"],
            check_count=int(created["rollup"].get("total_checks") or 0),
        ),
    )
    return jsonify({"ok": True, **created}), 201


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>",
)
@api_routes.require_api_auth
def api_project_assessment(project_id, assessment_id):
    try:
        session_id, owner_scope, _actor_member_id = _request_context()
        assessment = get_assessment_read_model(
            session_id,
            project_id,
            assessment_id,
            check_filters=_check_filters(),
            check_limit=api_routes._parse_int(
                request.args.get("limit"),
                50,
                minimum=1,
                maximum=200,
            ),
            check_offset=api_routes._parse_int(
                request.args.get("offset"),
                0,
                minimum=0,
                maximum=100000,
            ),
            finding_priority=request.args.get("finding_priority") or "",
            finding_limit=api_routes._parse_int(request.args.get("finding_limit"), 20, minimum=1, maximum=100),
            finding_offset=api_routes._parse_int(request.args.get("finding_offset"), 0, minimum=0, maximum=100000),
            team_id=owner_scope.team_id,
        )
    except AssessmentError as exc:
        return _assessment_api_error(exc)
    if assessment is None:
        return api_routes._api_json_error("not_found", "Assessment not found.", 404)
    return jsonify(assessment)


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>",
    methods=["PATCH"],
)
@api_routes.require_api_auth
def api_project_assessment_update(project_id, assessment_id):
    try:
        session_id, owner_scope, actor_member_id = _request_context(write=True)
        data = api_routes._json_body()

        def _update(conn):
            change = update_assessment_cycle(
                session_id,
                project_id,
                assessment_id,
                data,
                team_id=owner_scope.team_id,
                actor_member_id=actor_member_id,
                conn=conn,
            )
            if isinstance(change, BatchLifecycleCancellation):
                return change
            assessment = change["assessment"]
            event_type = {
                "complete": AuditEventType.ASSESSMENT_COMPLETE,
                "archive": AuditEventType.ASSESSMENT_ARCHIVE,
            }.get(change["transition_kind"], AuditEventType.ASSESSMENT_UPDATE)
            record_event(
                event_type,
                target_id=assessment_id,
                project_id=project_id,
                details=_audit_details(
                    assessment,
                    transition_kind=change["transition_kind"],
                    from_state=change["from_status"],
                    to_state=change["to_status"],
                    changed_fields=[
                        field
                        for field, changed in (
                            ("title", change["title_changed"]),
                            (
                                "status",
                                change["from_status"] != change["to_status"],
                            ),
                        )
                        if changed
                    ],
                ),
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return change

        change = run_project_transaction(_update)
    except (AssessmentError, ProjectWorkspaceQuotaExceeded, TeamPermissionDenied) as exc:
        return _assessment_api_error(exc)
    if isinstance(change, BatchLifecycleCancellation):
        return batch_lifecycle_pending_response(change, session_id, team_id=owner_scope.team_id, api=True)
    assessment = change["assessment"]
    api_routes.log.info(
        "API_PROJECT_ASSESSMENT_UPDATED",
        extra=_log_fields(
            session_id,
            owner_scope,
            project_id,
            assessment_id,
            from_status=change["from_status"],
            to_status=change["to_status"],
            transition_kind=change["transition_kind"],
            title_changed=change["title_changed"],
        ),
    )
    return jsonify({"ok": True, "assessment": assessment})


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/delete-preview",
)
@api_routes.require_api_auth
def api_project_assessment_delete_preview(project_id, assessment_id):
    try:
        session_id, owner_scope, _actor_member_id = _request_context()
        preview = preview_assessment_deletion(
            session_id,
            project_id,
            assessment_id,
            team_id=owner_scope.team_id,
        )
    except AssessmentError as exc:
        return _assessment_api_error(exc)
    return jsonify({"preview": preview})
@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>",
    methods=["DELETE"],
)
@api_routes.require_api_auth
def api_project_assessment_delete(project_id, assessment_id):
    try:
        session_id, owner_scope, _actor_member_id = _request_context(write=True)

        def _delete(conn):
            preview = delete_assessment_cycle(
                session_id,
                project_id,
                assessment_id,
                team_id=owner_scope.team_id,
                conn=conn,
            )
            if isinstance(preview, BatchLifecycleCancellation):
                return preview
            assessment = preview["assessment"]
            record_event(
                AuditEventType.ASSESSMENT_DELETE,
                target_id=assessment_id,
                project_id=project_id,
                details=_audit_details(
                    assessment,
                    transition_kind="delete",
                    counts=preview["will_delete"],
                    deleted_count=1,
                ),
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return preview

        deleted = run_project_transaction(_delete)
    except (AssessmentError, ProjectWorkspaceQuotaExceeded, TeamPermissionDenied) as exc:
        return _assessment_api_error(exc)
    if isinstance(deleted, BatchLifecycleCancellation):
        return batch_lifecycle_pending_response(deleted, session_id, team_id=owner_scope.team_id, api=True)
    api_routes.log.info(
        "API_PROJECT_ASSESSMENT_DELETED",
        extra=_log_fields(
            session_id,
            owner_scope,
            project_id,
            assessment_id,
            check_count=deleted["will_delete"]["checks"],
            evidence_count=deleted["will_delete"]["evidence_links"],
        ),
    )
    return jsonify({"ok": True, "deleted": deleted})
