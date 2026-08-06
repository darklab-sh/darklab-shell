# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for typed Project finding evidence."""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceError
from services.projects.finding_evidence import (
    link_finding_evidence_on_conn,
    unlink_finding_evidence_on_conn,
)
from services.projects.finding_verification import get_finding_verification_context
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability

@project_routes.projects_bp.route("/projects/<project_id>/findings/<finding_id>/evidence")
def project_finding_evidence_list(project_id, finding_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        verification = get_finding_verification_context(
            session_id, project_id, finding_id, team_id=team_id
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    evidence = verification.pop("evidence", [])
    return jsonify(
        {"evidence": evidence, "total": len(evidence), "verification": verification}
    )


@project_routes.projects_bp.route(
    "/projects/<project_id>/findings/<finding_id>/evidence",
    methods=["POST"],
)
@limiter.limit(project_routes._project_write_limit)
def project_finding_evidence_link(project_id, finding_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.TRIAGE_FINDINGS
    )
    if error_response:
        return error_response
    try:
        data = request.get_json(silent=True)
        actor_member_id = project_routes._project_actor_member_id(session_id, team_id)

        def _link(conn):
            result = link_finding_evidence_on_conn(
                conn,
                session_id,
                project_id,
                finding_id,
                data,
                team_id=team_id,
                actor_member_id=actor_member_id,
            )
            if result["created"]:
                evidence = result["evidence"]
                project_routes.record_event(
                    AuditEventType.FINDING_EVIDENCE_LINK,
                    target_id=finding_id,
                    project_id=project_id,
                    details={
                        "project_id": project_id,
                        "finding_id": finding_id,
                        "evidence_id": evidence["evidence_id"],
                        "evidence_type": evidence["evidence_type"],
                        "run_id": evidence["run_id"],
                    },
                    conn=conn,
                    **project_routes._project_audit_fields(session_id, team_id),
                )
            return result

        result = run_project_transaction(_link)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    evidence = result["evidence"]
    project_routes.log.info("PROJECT_FINDING_EVIDENCE_LINKED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "finding_id": finding_id,
        "evidence_link_id": evidence["id"],
        "evidence_type": evidence["evidence_type"],
        "created": result["created"],
    })
    return jsonify({"ok": True, **result}), 201 if result["created"] else 200


@project_routes.projects_bp.route(
    "/projects/<project_id>/findings/<finding_id>/evidence/<evidence_link_id>",
    methods=["DELETE"],
)
@limiter.limit(project_routes._project_write_limit)
def project_finding_evidence_unlink(project_id, finding_id, evidence_link_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.TRIAGE_FINDINGS
    )
    if error_response:
        return error_response
    try:
        def _unlink(conn):
            evidence = unlink_finding_evidence_on_conn(
                conn,
                session_id,
                project_id,
                finding_id,
                evidence_link_id,
                team_id=team_id,
            )
            project_routes.record_event(
                AuditEventType.FINDING_EVIDENCE_UNLINK,
                target_id=finding_id,
                project_id=project_id,
                details={
                    "project_id": project_id,
                    "finding_id": finding_id,
                    "evidence_id": evidence["evidence_id"],
                    "evidence_type": evidence["evidence_type"],
                    "run_id": evidence["run_id"],
                },
                conn=conn,
                **project_routes._project_audit_fields(session_id, team_id),
            )
            return evidence

        evidence = run_project_transaction(_unlink)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    project_routes.log.info("PROJECT_FINDING_EVIDENCE_UNLINKED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "finding_id": finding_id,
        "evidence_link_id": evidence_link_id,
        "evidence_type": evidence["evidence_type"],
    })
    return jsonify({"ok": True, "evidence": evidence})
