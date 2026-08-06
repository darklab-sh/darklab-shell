# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for assessor-authored Project findings."""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceError
from services.projects.manual_findings import (
    create_manual_finding_on_conn,
    update_manual_finding_on_conn,
)
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability


def _conflict_response(result):
    return jsonify({"ok": False, **result}), 409


@project_routes.projects_bp.route("/projects/<project_id>/findings", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def project_manual_finding_create(project_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.TRIAGE_FINDINGS
    )
    if error_response:
        return error_response
    try:
        actor_member_id = project_routes._project_actor_member_id(session_id, team_id)
        data = request.get_json(silent=True)

        def _create(conn):
            result = create_manual_finding_on_conn(
                conn,
                session_id,
                project_id,
                data,
                team_id=team_id,
                actor_member_id=actor_member_id,
            )
            if not result["created"]:
                return result
            finding = result["finding"]
            project_routes.record_event(
                AuditEventType.FINDING_MANUAL_CREATE,
                target_id=finding["id"],
                project_id=project_id,
                details={
                    "project_id": project_id,
                    "finding_id": finding["id"],
                    "target_id": finding["target_id"],
                    "severity": finding["severity"],
                    "manual_revision": finding["manual_revision"],
                    "evidence_count": len(finding["evidence_links"]),
                    "duplicate_override": result["duplicate_override"],
                },
                conn=conn,
                **project_routes._project_audit_fields(session_id, team_id),
            )
            return result

        result = run_project_transaction(_create)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if not result["created"]:
        project_routes.log.debug("PROJECT_MANUAL_FINDING_CONFLICT", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "conflict": result["conflict"],
            "duplicate_count": len(result.get("duplicates", [])),
        })
        return _conflict_response(result)
    finding = result["finding"]
    project_routes.log.info("PROJECT_MANUAL_FINDING_CREATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "finding_id": finding["id"],
        "target_id": finding["target_id"],
        "severity": finding["severity"],
        "manual_revision": finding["manual_revision"],
        "evidence_count": len(finding["evidence_links"]),
        "duplicate_override": result["duplicate_override"],
    })
    return jsonify({"ok": True, **result}), 201


@project_routes.projects_bp.route(
    "/projects/<project_id>/findings/<finding_id>", methods=["PATCH"]
)
@limiter.limit(project_routes._project_write_limit)
def project_manual_finding_update(project_id, finding_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.TRIAGE_FINDINGS
    )
    if error_response:
        return error_response
    try:
        actor_member_id = project_routes._project_actor_member_id(session_id, team_id)
        data = request.get_json(silent=True)

        def _update(conn):
            result = update_manual_finding_on_conn(
                conn,
                session_id,
                project_id,
                finding_id,
                data,
                team_id=team_id,
                actor_member_id=actor_member_id,
            )
            if not result["updated"]:
                return result
            finding = result["finding"]
            project_routes.record_event(
                AuditEventType.FINDING_MANUAL_UPDATE,
                target_id=finding_id,
                project_id=project_id,
                details={
                    "project_id": project_id,
                    "finding_id": finding_id,
                    "target_id": finding["target_id"],
                    "severity": finding["severity"],
                    "manual_revision": finding["manual_revision"],
                    "changed_fields": result["changed_fields"],
                    "duplicate_override": result["duplicate_override"],
                },
                conn=conn,
                **project_routes._project_audit_fields(session_id, team_id),
            )
            return result

        result = run_project_transaction(_update)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if not result["updated"]:
        project_routes.log.debug("PROJECT_MANUAL_FINDING_UPDATE_CONFLICT", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "finding_id": finding_id,
            "conflict": result["conflict"],
            "current_revision": result.get("current_revision"),
            "duplicate_count": len(result.get("duplicates", [])),
        })
        return _conflict_response(result)
    finding = result["finding"]
    project_routes.log.info("PROJECT_MANUAL_FINDING_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "finding_id": finding_id,
        "target_id": finding["target_id"],
        "severity": finding["severity"],
        "manual_revision": finding["manual_revision"],
        "changed_fields": result["changed_fields"],
        "duplicate_override": result["duplicate_override"],
    })
    return jsonify({"ok": True, **result})
