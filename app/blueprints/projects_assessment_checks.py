# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project assessment check-state and evidence browser routes."""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.assessments.contracts import (
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
)
from services.assessments.mutations import (
    link_manual_evidence_on_conn,
    unlink_manual_evidence_on_conn,
    update_manual_check_state_on_conn,
)
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability


def _error_response(exc: Exception):
    if isinstance(exc, AssessmentNotFound):
        status = 404
    elif isinstance(exc, (AssessmentConflict, ProjectWorkspaceQuotaExceeded)):
        status = 409
    else:
        status = 400
    return jsonify({"error": str(exc)}), status


def _payload(allowed: set[str]):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise AssessmentError("assessment payload must be a JSON object")
    if set(data) - allowed:
        raise AssessmentError("assessment payload contains unsupported fields")
    return data


def _details(change: dict, assessment_id: str, *, transition_kind: str) -> dict:
    check = change["check"]
    return {
        "project_id": (request.view_args or {}).get("project_id", ""),
        "assessment_id": assessment_id,
        "check_id": str(check.get("id") or ""),
        "check_key": str(check.get("check_key") or ""),
        "policy_level": str(check.get("policy_level") or ""),
        "from_state": str(change.get("from_state") or ""),
        "to_state": str(change.get("to_state") or ""),
        "transition_kind": transition_kind,
    }


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>",
    methods=["PATCH"],
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessment_check_update(project_id, assessment_id, check_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MUTATE_PROJECTS
    )
    if error_response:
        return error_response
    try:
        data = _payload({"state", "reason"})
        actor_member_id = project_routes._project_actor_member_id(session_id, team_id)

        def _update(conn):
            change = update_manual_check_state_on_conn(
                conn,
                session_id,
                project_id,
                assessment_id,
                check_id,
                data.get("state") or "",
                reason=data.get("reason") or "",
                team_id=team_id,
                actor_member_id=actor_member_id,
            )
            project_routes.record_event(
                AuditEventType.ASSESSMENT_CHECK_STATE_CHANGE,
                target_id=check_id,
                project_id=project_id,
                details=_details(change, assessment_id, transition_kind="manual_state"),
                conn=conn,
                **project_routes._project_audit_fields(session_id, team_id),
            )
            return change

        change = run_project_transaction(_update)
    except (AssessmentError, ProjectWorkspaceQuotaExceeded) as exc:
        return _error_response(exc)
    check = change["check"]
    project_routes.log.info("PROJECT_ASSESSMENT_CHECK_STATE_CHANGED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "check_id": check_id,
        "check_key": check["check_key"],
        "policy_level": check["policy_level"],
        "from_state": change["from_state"],
        "to_state": change["to_state"],
        "manual_override_cleared": change["manual_override_cleared"],
    })
    return jsonify({"ok": True, **change})


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/evidence",
    methods=["POST"],
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessment_evidence_link(project_id, assessment_id, check_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MUTATE_PROJECTS
    )
    if error_response:
        return error_response
    try:
        data = _payload({"evidence_type", "evidence_id"})
        actor_member_id = project_routes._project_actor_member_id(session_id, team_id)

        def _link(conn):
            change = link_manual_evidence_on_conn(
                conn,
                session_id,
                project_id,
                assessment_id,
                check_id,
                data.get("evidence_type") or "",
                data.get("evidence_id") or "",
                team_id=team_id,
                actor_member_id=actor_member_id,
            )
            details = _details(change, assessment_id, transition_kind="evidence_link")
            details.update({
                "evidence_id": change["evidence"]["evidence_id"],
                "evidence_type": change["evidence"]["evidence_type"],
            })
            project_routes.record_event(
                AuditEventType.ASSESSMENT_EVIDENCE_LINK,
                target_id=check_id,
                project_id=project_id,
                details=details,
                conn=conn,
                **project_routes._project_audit_fields(session_id, team_id),
            )
            return change

        change = run_project_transaction(_link)
    except (AssessmentError, ProjectWorkspaceQuotaExceeded) as exc:
        return _error_response(exc)
    evidence = change["evidence"]
    project_routes.log.info("PROJECT_ASSESSMENT_EVIDENCE_LINKED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "check_id": check_id,
        "evidence_type": evidence["evidence_type"],
        "evidence_id": evidence["evidence_id"],
        "from_state": change["from_state"],
        "to_state": change["to_state"],
        "manual_state_preserved": change["manual_state_preserved"],
    })
    return jsonify({"ok": True, **change}), 201


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "evidence/<evidence_link_id>",
    methods=["DELETE"],
)
@limiter.limit(project_routes._project_write_limit)
def projects_assessment_evidence_unlink(
    project_id,
    assessment_id,
    check_id,
    evidence_link_id,
):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MUTATE_PROJECTS
    )
    if error_response:
        return error_response
    try:
        actor_member_id = project_routes._project_actor_member_id(session_id, team_id)

        def _unlink(conn):
            change = unlink_manual_evidence_on_conn(
                conn,
                session_id,
                project_id,
                assessment_id,
                check_id,
                evidence_link_id,
                team_id=team_id,
                actor_member_id=actor_member_id,
            )
            details = _details(change, assessment_id, transition_kind="evidence_unlink")
            details.update({
                "evidence_id": change["deleted"]["evidence_id"],
                "evidence_type": change["deleted"]["evidence_type"],
            })
            project_routes.record_event(
                AuditEventType.ASSESSMENT_EVIDENCE_UNLINK,
                target_id=check_id,
                project_id=project_id,
                details=details,
                conn=conn,
                **project_routes._project_audit_fields(session_id, team_id),
            )
            return change

        change = run_project_transaction(_unlink)
    except (AssessmentError, ProjectWorkspaceQuotaExceeded) as exc:
        return _error_response(exc)
    deleted = change["deleted"]
    project_routes.log.info("PROJECT_ASSESSMENT_EVIDENCE_UNLINKED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "check_id": check_id,
        "evidence_type": deleted["evidence_type"],
        "evidence_id": deleted["evidence_id"],
        "from_state": change["from_state"],
        "to_state": change["to_state"],
        "manual_state_preserved": change["manual_state_preserved"],
    })
    return jsonify({"ok": True, **change})
