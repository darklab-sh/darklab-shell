# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 routes for typed Project finding evidence."""

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import ProjectWorkspaceError
from services.projects.finding_evidence import (
    link_finding_evidence_on_conn,
    unlink_finding_evidence_on_conn,
)
from services.projects.finding_verification import get_finding_verification_context
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _error(exc):
    if isinstance(exc, TeamPermissionDenied):
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    return api_routes._project_workspace_api_error(exc)


def _log_fields(session_id, owner_scope, project_id, finding_id, **extra):
    return {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": owner_scope.team_id,
        "project_id": project_id,
        "finding_id": finding_id,
        "source": "api_v1",
        **extra,
    }


@api_routes.api_v1_bp.route("/projects/<project_id>/findings/<finding_id>/evidence")
@api_routes.require_api_auth
def api_project_finding_evidence_list(project_id, finding_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        verification = get_finding_verification_context(
            session_id, project_id, finding_id, team_id=owner_scope.team_id
        )
    except (ProjectWorkspaceError, TeamPermissionDenied) as exc:
        return _error(exc)
    evidence = verification.pop("evidence", [])
    return jsonify(
        {"evidence": evidence, "total": len(evidence), "verification": verification}
    )


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/findings/<finding_id>/evidence",
    methods=["POST"],
)
@api_routes.require_api_auth
def api_project_finding_evidence_link(project_id, finding_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, Capability.TRIAGE_FINDINGS)
        data = api_routes._json_body()
        actor_member_id = str((owner_scope.member or {}).get("id") or "")

        def _link(conn):
            result = link_finding_evidence_on_conn(
                conn,
                session_id,
                project_id,
                finding_id,
                data,
                team_id=owner_scope.team_id,
                actor_member_id=actor_member_id,
            )
            if result["created"]:
                evidence = result["evidence"]
                record_event(
                    AuditEventType.FINDING_EVIDENCE_LINK,
                    target_id=finding_id,
                    project_id=project_id,
                    details={
                        "source": "api_v1",
                        "project_id": project_id,
                        "finding_id": finding_id,
                        "evidence_id": evidence["evidence_id"],
                        "evidence_type": evidence["evidence_type"],
                        "run_id": evidence["run_id"],
                    },
                    conn=conn,
                    **route_audit_fields(session_id, request, owner_scope),
                )
            return result

        result = run_project_transaction(_link)
    except (ProjectWorkspaceError, TeamPermissionDenied) as exc:
        return _error(exc)
    evidence = result["evidence"]
    api_routes.log.info("API_PROJECT_FINDING_EVIDENCE_LINKED", extra=_log_fields(
        session_id,
        owner_scope,
        project_id,
        finding_id,
        evidence_link_id=evidence["id"],
        evidence_type=evidence["evidence_type"],
        link_created=result["created"],
    ))
    return jsonify({"ok": True, **result}), 201 if result["created"] else 200


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/findings/<finding_id>/evidence/<evidence_link_id>",
    methods=["DELETE"],
)
@api_routes.require_api_auth
def api_project_finding_evidence_unlink(project_id, finding_id, evidence_link_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, Capability.TRIAGE_FINDINGS)

        def _unlink(conn):
            evidence = unlink_finding_evidence_on_conn(
                conn,
                session_id,
                project_id,
                finding_id,
                evidence_link_id,
                team_id=owner_scope.team_id,
            )
            record_event(
                AuditEventType.FINDING_EVIDENCE_UNLINK,
                target_id=finding_id,
                project_id=project_id,
                details={
                    "source": "api_v1",
                    "project_id": project_id,
                    "finding_id": finding_id,
                    "evidence_id": evidence["evidence_id"],
                    "evidence_type": evidence["evidence_type"],
                    "run_id": evidence["run_id"],
                },
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return evidence

        evidence = run_project_transaction(_unlink)
    except (ProjectWorkspaceError, TeamPermissionDenied) as exc:
        return _error(exc)
    api_routes.log.info("API_PROJECT_FINDING_EVIDENCE_UNLINKED", extra=_log_fields(
        session_id,
        owner_scope,
        project_id,
        finding_id,
        evidence_link_id=evidence_link_id,
        evidence_type=evidence["evidence_type"],
    ))
    return jsonify({"ok": True, "evidence": evidence})
