# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 routes for assessor-authored Project findings."""

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import ProjectWorkspaceError
from services.projects.manual_findings import (
    create_manual_finding_on_conn,
    update_manual_finding_on_conn,
)
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _error(exc):
    if isinstance(exc, TeamPermissionDenied):
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    return api_routes._project_workspace_api_error(exc)


def _log_fields(session_id, owner_scope, project_id, finding_id="", **extra):
    return {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": owner_scope.team_id,
        "project_id": project_id,
        "finding_id": finding_id,
        "source": "api_v1",
        **extra,
    }


@api_routes.api_v1_bp.route("/projects/<project_id>/findings", methods=["POST"])
@api_routes.require_api_auth
def api_project_manual_finding_create(project_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(
            owner_scope, Capability.TRIAGE_FINDINGS
        )
        data = api_routes._json_body()
        actor_member_id = str((owner_scope.member or {}).get("id") or "")

        def _create(conn):
            result = create_manual_finding_on_conn(
                conn,
                session_id,
                project_id,
                data,
                team_id=owner_scope.team_id,
                actor_member_id=actor_member_id,
            )
            if not result["created"]:
                return result
            finding = result["finding"]
            record_event(
                AuditEventType.FINDING_MANUAL_CREATE,
                target_id=finding["id"],
                project_id=project_id,
                details={
                    "source": "api_v1",
                    "project_id": project_id,
                    "finding_id": finding["id"],
                    "target_id": finding["target_id"],
                    "severity": finding["severity"],
                    "manual_revision": finding["manual_revision"],
                    "evidence_count": len(finding["evidence_links"]),
                    "duplicate_override": result["duplicate_override"],
                },
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return result

        result = run_project_transaction(_create)
    except (ProjectWorkspaceError, TeamPermissionDenied) as exc:
        return _error(exc)
    if not result["created"]:
        api_routes.log.debug("API_PROJECT_MANUAL_FINDING_CONFLICT", extra=_log_fields(
            session_id,
            owner_scope,
            project_id,
            conflict=result["conflict"],
            duplicate_count=len(result.get("duplicates", [])),
        ))
        return jsonify({"ok": False, **result}), 409
    finding = result["finding"]
    api_routes.log.info("API_PROJECT_MANUAL_FINDING_CREATED", extra=_log_fields(
        session_id,
        owner_scope,
        project_id,
        finding["id"],
        target_id=finding["target_id"],
        severity=finding["severity"],
        manual_revision=finding["manual_revision"],
        evidence_count=len(finding["evidence_links"]),
        duplicate_override=result["duplicate_override"],
    ))
    return jsonify({"ok": True, **result}), 201


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/findings/<finding_id>", methods=["PATCH"]
)
@api_routes.require_api_auth
def api_project_manual_finding_update(project_id, finding_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(
            owner_scope, Capability.TRIAGE_FINDINGS
        )
        data = api_routes._json_body()
        actor_member_id = str((owner_scope.member or {}).get("id") or "")

        def _update(conn):
            result = update_manual_finding_on_conn(
                conn,
                session_id,
                project_id,
                finding_id,
                data,
                team_id=owner_scope.team_id,
                actor_member_id=actor_member_id,
            )
            if not result["updated"]:
                return result
            finding = result["finding"]
            record_event(
                AuditEventType.FINDING_MANUAL_UPDATE,
                target_id=finding_id,
                project_id=project_id,
                details={
                    "source": "api_v1",
                    "project_id": project_id,
                    "finding_id": finding_id,
                    "target_id": finding["target_id"],
                    "severity": finding["severity"],
                    "manual_revision": finding["manual_revision"],
                    "changed_fields": result["changed_fields"],
                    "duplicate_override": result["duplicate_override"],
                },
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return result

        result = run_project_transaction(_update)
    except (ProjectWorkspaceError, TeamPermissionDenied) as exc:
        return _error(exc)
    if not result["updated"]:
        api_routes.log.debug("API_PROJECT_MANUAL_FINDING_UPDATE_CONFLICT", extra=_log_fields(
            session_id,
            owner_scope,
            project_id,
            finding_id,
            conflict=result["conflict"],
            current_revision=result.get("current_revision"),
            duplicate_count=len(result.get("duplicates", [])),
        ))
        return jsonify({"ok": False, **result}), 409
    finding = result["finding"]
    api_routes.log.info("API_PROJECT_MANUAL_FINDING_UPDATED", extra=_log_fields(
        session_id,
        owner_scope,
        project_id,
        finding_id,
        target_id=finding["target_id"],
        severity=finding["severity"],
        manual_revision=finding["manual_revision"],
        changed_fields=result["changed_fields"],
        duplicate_override=result["duplicate_override"],
    ))
    return jsonify({"ok": True, **result})
