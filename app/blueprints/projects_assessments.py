# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project assessment-cycle browser routes."""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.assessments.contracts import (
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
)
from services.assessments.lifecycle import delete_assessment_cycle, preview_assessment_deletion, update_assessment_cycle
from services.assessments.profile_summaries import list_assessment_profile_summaries
from services.assessments.read_model import get_assessment_read_model, list_assessment_cycles
from services.assessments.storage import create_assessment_cycle
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability


def _bool_arg(name: str) -> bool:
    return str(request.args.get(name) or "").strip().lower() in {"1", "true", "yes"}


def _assessment_error_response(exc: Exception):
    if isinstance(exc, AssessmentNotFound):
        status = 404
    elif isinstance(exc, (AssessmentConflict, ProjectWorkspaceQuotaExceeded)):
        status = 409
    else:
        status = 400
    return jsonify({"error": str(exc)}), status


def _check_filters() -> dict[str, str]:
    return {
        "category": str(request.args.get("category") or ""),
        "state": str(request.args.get("state") or ""),
        "target_type": str(request.args.get("target_type") or ""),
        "policy_level": str(request.args.get("policy_level") or ""),
        "evidence_state": str(request.args.get("evidence_state") or ""),
    }


def _audit_details(assessment: dict, *, transition_kind: str, **details):
    return {
        "project_id": str(assessment.get("project_id") or ""),
        "assessment_id": str(assessment.get("id") or ""),
        "profile_key": str(assessment.get("profile_key") or ""),
        "profile_version": str(assessment.get("profile_version") or ""),
        "status": str(assessment.get("status") or ""),
        "transition_kind": transition_kind,
        **details,
    }


@project_routes.projects_bp.route("/projects/<project_id>/assessments")
def projects_assessments_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        page = list_assessment_cycles(
            session_id,
            project_id,
            status=request.args.get("status") or "",
            include_archived=_bool_arg("include_archived"),
            limit=project_routes._parse_int(
                request.args.get("limit"), 50, minimum=1, maximum=200
            ),
            offset=project_routes._parse_int(
                request.args.get("offset"), 0, minimum=0, maximum=100000
            ),
            team_id=team_id,
        )
    except AssessmentError as exc:
        return _assessment_error_response(exc)
    if page is not None:
        page["profiles"] = list_assessment_profile_summaries()
    return project_routes._project_json_or_404(page)


@project_routes.projects_bp.route("/projects/<project_id>/assessments", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_assessments_create(project_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MUTATE_PROJECTS
    )
    if error_response:
        return error_response
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify({"error": "assessment payload must be a JSON object"}), 400
    if set(data) - {"profile_key", "title"}:
        return jsonify({"error": "assessment payload contains unsupported fields"}), 400
    try:
        created = create_assessment_cycle(
            session_id,
            project_id,
            str(data.get("profile_key") or ""),
            title=str(data.get("title") or ""),
            team_id=team_id,
            actor_member_id=project_routes._project_actor_member_id(session_id, team_id),
        )
    except (AssessmentError, ProjectWorkspaceQuotaExceeded) as exc:
        return _assessment_error_response(exc)
    assessment = created["assessment"]
    project_routes.record_event(
        AuditEventType.ASSESSMENT_CREATE,
        target_id=assessment["id"],
        project_id=project_id,
        details=_audit_details(
            assessment,
            transition_kind="create",
            count=int(created["rollup"].get("total_checks") or 0),
        ),
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("PROJECT_ASSESSMENT_CREATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "assessment_id": assessment["id"],
        "profile_key": assessment["profile_key"],
        "profile_version": assessment["profile_version"],
        "check_count": int(created["rollup"].get("total_checks") or 0),
    })
    return jsonify({"ok": True, **created}), 201


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>"
)
def projects_assessments_get(project_id, assessment_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        assessment = get_assessment_read_model(
            session_id,
            project_id,
            assessment_id,
            check_filters=_check_filters(),
            check_limit=project_routes._parse_int(
                request.args.get("limit"), 50, minimum=1, maximum=200
            ),
            check_offset=project_routes._parse_int(
                request.args.get("offset"), 0, minimum=0, maximum=100000
            ),
            team_id=team_id,
        )
    except AssessmentError as exc:
        return _assessment_error_response(exc)
    return project_routes._project_json_or_404(
        assessment,
        error="assessment not found",
    )


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>",
    methods=["PATCH"],
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessments_update(project_id, assessment_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MUTATE_PROJECTS
    )
    if error_response:
        return error_response
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    actor_member_id = project_routes._project_actor_member_id(session_id, team_id)
    try:
        change = update_assessment_cycle(
            session_id,
            project_id,
            assessment_id,
            data,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
    except AssessmentError as exc:
        return _assessment_error_response(exc)
    assessment = change["assessment"]
    event_type = {
        "complete": AuditEventType.ASSESSMENT_COMPLETE,
        "archive": AuditEventType.ASSESSMENT_ARCHIVE,
    }.get(change["transition_kind"], AuditEventType.ASSESSMENT_UPDATE)
    project_routes.record_event(
        event_type,
        target_id=assessment_id,
        project_id=project_id,
        details=_audit_details(
            assessment,
            transition_kind=change["transition_kind"],
            from_state=change["from_status"],
            to_state=change["to_status"],
            changed_fields=[
                field for field, changed in (
                    ("title", change["title_changed"]),
                    ("status", change["from_status"] != change["to_status"]),
                ) if changed
            ],
        ),
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("PROJECT_ASSESSMENT_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "from_status": change["from_status"],
        "to_status": change["to_status"],
        "transition_kind": change["transition_kind"],
        "title_changed": change["title_changed"],
    })
    return jsonify({"ok": True, "assessment": assessment})


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/delete-preview"
)
def projects_assessments_delete_preview(project_id, assessment_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        preview = preview_assessment_deletion(
            session_id,
            project_id,
            assessment_id,
            team_id=team_id,
        )
    except AssessmentError as exc:
        return _assessment_error_response(exc)
    return jsonify({"preview": preview})


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>",
    methods=["DELETE"],
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessments_delete(project_id, assessment_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MUTATE_PROJECTS
    )
    if error_response:
        return error_response

    def _delete(conn):
        preview = delete_assessment_cycle(
            session_id,
            project_id,
            assessment_id,
            team_id=team_id,
            conn=conn,
        )
        assessment = preview["assessment"]
        counts = preview["will_delete"]
        project_routes.record_event(
            AuditEventType.ASSESSMENT_DELETE,
            target_id=assessment_id,
            project_id=project_id,
            details=_audit_details(
                assessment,
                transition_kind="delete",
                counts=counts,
                deleted_count=1,
            ),
            conn=conn,
            **project_routes._project_audit_fields(session_id, team_id),
        )
        return preview

    try:
        deleted = run_project_transaction(_delete)
    except AssessmentError as exc:
        return _assessment_error_response(exc)
    project_routes.log.info("PROJECT_ASSESSMENT_DELETED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "check_count": deleted["will_delete"]["checks"],
        "evidence_count": deleted["will_delete"]["evidence_links"],
    })
    return jsonify({"ok": True, "deleted": deleted})
