# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 Project assessment check and evidence routes."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.assessments.contracts import AssessmentError
from services.assessments.mutations import (
    link_manual_evidence_on_conn,
    unlink_manual_evidence_on_conn,
    update_manual_check_state_on_conn,
)
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied

from blueprints.api_v1_assessments import _assessment_api_error


def _payload(allowed: set[str]):
    data = api_routes._json_body()
    if set(data) - allowed:
        raise AssessmentError("assessment payload contains unsupported fields")
    return data


def _request_context():
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    api_routes._require_api_team_capability(
        owner_scope,
        Capability.MUTATE_PROJECTS,
    )
    actor_member_id = str((owner_scope.member or {}).get("id") or "")
    return session_id, owner_scope, actor_member_id


def _details(change: dict, assessment_id: str, *, transition_kind: str) -> dict:
    check = change["check"]
    view_args = request.view_args or {}
    return {
        "source": "api_v1",
        "project_id": str(view_args.get("project_id") or ""),
        "assessment_id": assessment_id,
        "check_id": str(check.get("id") or ""),
        "check_key": str(check.get("check_key") or ""),
        "policy_level": str(check.get("policy_level") or ""),
        "from_state": str(change.get("from_state") or ""),
        "to_state": str(change.get("to_state") or ""),
        "transition_kind": transition_kind,
    }


def _log_fields(
    session_id: str,
    owner_scope,
    project_id: str,
    assessment_id: str,
    check_id: str,
    **details,
):
    return {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": owner_scope.team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "check_id": check_id,
        "source": "api_v1",
        **details,
    }


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>",
    methods=["PATCH"],
)
@api_routes.require_api_auth
def api_project_assessment_check_update(project_id, assessment_id, check_id):
    try:
        session_id, owner_scope, actor_member_id = _request_context()
        data = _payload({"state", "reason"})

        def _update(conn):
            change = update_manual_check_state_on_conn(
                conn,
                session_id,
                project_id,
                assessment_id,
                check_id,
                data.get("state") or "",
                reason=data.get("reason") or "",
                team_id=owner_scope.team_id,
                actor_member_id=actor_member_id,
            )
            record_event(
                AuditEventType.ASSESSMENT_CHECK_STATE_CHANGE,
                target_id=check_id,
                project_id=project_id,
                details=_details(
                    change,
                    assessment_id,
                    transition_kind="manual_state",
                ),
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return change

        change = run_project_transaction(_update)
    except (AssessmentError, ProjectWorkspaceQuotaExceeded, TeamPermissionDenied) as exc:
        return _assessment_api_error(exc)
    check = change["check"]
    api_routes.log.info(
        "API_PROJECT_ASSESSMENT_CHECK_STATE_CHANGED",
        extra=_log_fields(
            session_id,
            owner_scope,
            project_id,
            assessment_id,
            check_id,
            check_key=check["check_key"],
            policy_level=check["policy_level"],
            from_state=change["from_state"],
            to_state=change["to_state"],
            manual_override_cleared=change["manual_override_cleared"],
        ),
    )
    return jsonify({"ok": True, **change})


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/evidence",
    methods=["POST"],
)
@api_routes.require_api_auth
def api_project_assessment_evidence_link(project_id, assessment_id, check_id):
    try:
        session_id, owner_scope, actor_member_id = _request_context()
        data = _payload({"evidence_type", "evidence_id"})

        def _link(conn):
            change = link_manual_evidence_on_conn(
                conn,
                session_id,
                project_id,
                assessment_id,
                check_id,
                data.get("evidence_type") or "",
                data.get("evidence_id") or "",
                team_id=owner_scope.team_id,
                actor_member_id=actor_member_id,
            )
            details = _details(
                change,
                assessment_id,
                transition_kind="evidence_link",
            )
            details.update({
                "evidence_id": change["evidence"]["evidence_id"],
                "evidence_type": change["evidence"]["evidence_type"],
            })
            record_event(
                AuditEventType.ASSESSMENT_EVIDENCE_LINK,
                target_id=check_id,
                project_id=project_id,
                details=details,
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return change

        change = run_project_transaction(_link)
    except (AssessmentError, ProjectWorkspaceQuotaExceeded, TeamPermissionDenied) as exc:
        return _assessment_api_error(exc)
    evidence = change["evidence"]
    api_routes.log.info(
        "API_PROJECT_ASSESSMENT_EVIDENCE_LINKED",
        extra=_log_fields(
            session_id,
            owner_scope,
            project_id,
            assessment_id,
            check_id,
            evidence_type=evidence["evidence_type"],
            evidence_id=evidence["evidence_id"],
            from_state=change["from_state"],
            to_state=change["to_state"],
            manual_state_preserved=change["manual_state_preserved"],
        ),
    )
    return jsonify({"ok": True, **change}), 201


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "evidence/<evidence_link_id>",
    methods=["DELETE"],
)
@api_routes.require_api_auth
def api_project_assessment_evidence_unlink(
    project_id,
    assessment_id,
    check_id,
    evidence_link_id,
):
    try:
        session_id, owner_scope, actor_member_id = _request_context()

        def _unlink(conn):
            change = unlink_manual_evidence_on_conn(
                conn,
                session_id,
                project_id,
                assessment_id,
                check_id,
                evidence_link_id,
                team_id=owner_scope.team_id,
                actor_member_id=actor_member_id,
            )
            details = _details(
                change,
                assessment_id,
                transition_kind="evidence_unlink",
            )
            details.update({
                "evidence_id": change["deleted"]["evidence_id"],
                "evidence_type": change["deleted"]["evidence_type"],
            })
            record_event(
                AuditEventType.ASSESSMENT_EVIDENCE_UNLINK,
                target_id=check_id,
                project_id=project_id,
                details=details,
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return change

        change = run_project_transaction(_unlink)
    except (AssessmentError, ProjectWorkspaceQuotaExceeded, TeamPermissionDenied) as exc:
        return _assessment_api_error(exc)
    deleted = change["deleted"]
    api_routes.log.info(
        "API_PROJECT_ASSESSMENT_EVIDENCE_UNLINKED",
        extra=_log_fields(
            session_id,
            owner_scope,
            project_id,
            assessment_id,
            check_id,
            evidence_type=deleted["evidence_type"],
            evidence_id=deleted["evidence_id"],
            from_state=change["from_state"],
            to_state=change["to_state"],
            manual_state_preserved=change["manual_state_preserved"],
        ),
    )
    return jsonify({"ok": True, **change})
