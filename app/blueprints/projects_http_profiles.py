# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for Project HTTP assessment profiles."""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.assessments.http_profile_contracts import (
    HttpProfileConflict,
    HttpProfileError,
    HttpProfileNotFound,
)
from services.assessments.http_profiles import (
    create_http_profile_on_conn,
    delete_http_profile_on_conn,
    get_http_profile,
    http_profile_audit_summary,
    list_http_profiles,
    update_http_profile_on_conn,
)
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability, role_can
from services.teams.request_scope import RequestScopeError, current_request_scope


def _error(exc: Exception):
    if isinstance(exc, HttpProfileNotFound):
        status = 404
    elif isinstance(exc, (HttpProfileConflict, ProjectWorkspaceQuotaExceeded)):
        status = 409
    else:
        status = 400
    return jsonify({"error": str(exc)}), status


def _can_manage_references(session_id: str, team_id: str) -> bool:
    if not team_id:
        return True
    try:
        scope = current_request_scope(session_id, request, allow_archived=request.method == "GET")
    except RequestScopeError:
        return False
    return role_can(
        str((scope.member or {}).get("role") or ""),
        Capability.MANAGE_SECRETS,
    )


def _log_fields(session_id: str, team_id: str, project_id: str, profile: dict):
    safe = http_profile_audit_summary(profile)
    return {
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "profile_id": safe["profile_id"],
        "role": safe["role"],
        "enabled": safe["enabled"],
        "reference_counts": safe["counts"],
    }


@project_routes.projects_bp.route("/projects/<project_id>/http-profiles")
def projects_http_profiles_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    profiles = list_http_profiles(
        session_id,
        project_id,
        team_id=team_id,
        include_references=_can_manage_references(session_id, team_id),
    )
    return project_routes._project_json_or_404(profiles)


@project_routes.projects_bp.route("/projects/<project_id>/http-profiles/<profile_id>")
def projects_http_profiles_get(project_id, profile_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    profile = get_http_profile(
        session_id,
        project_id,
        profile_id,
        team_id=team_id,
        include_references=_can_manage_references(session_id, team_id),
    )
    return project_routes._project_json_or_404(profile, key="profile")


@project_routes.projects_bp.route("/projects/<project_id>/http-profiles", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_http_profiles_create(project_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MANAGE_SECRETS
    )
    if error_response:
        return error_response
    try:
        actor_member_id = project_routes._project_actor_member_id(session_id, team_id)
        data = request.get_json(silent=True)

        def _create(conn):
            profile = create_http_profile_on_conn(
                conn,
                session_id,
                project_id,
                data,
                team_id=team_id,
                actor_member_id=actor_member_id,
            )
            project_routes.record_event(
                AuditEventType.HTTP_PROFILE_CREATE,
                target_id=profile["id"],
                project_id=project_id,
                details=http_profile_audit_summary(profile),
                conn=conn,
                **project_routes._project_audit_fields(session_id, team_id),
            )
            return profile

        profile = run_project_transaction(_create)
    except (HttpProfileError, ProjectWorkspaceQuotaExceeded) as exc:
        return _error(exc)
    project_routes.log.info(
        "PROJECT_HTTP_PROFILE_CREATED",
        extra=_log_fields(session_id, team_id, project_id, profile),
    )
    return jsonify({"ok": True, "profile": profile}), 201


@project_routes.projects_bp.route(
    "/projects/<project_id>/http-profiles/<profile_id>", methods=["PATCH"]
)
@limiter.limit(project_routes._project_write_limit)
def projects_http_profiles_update(project_id, profile_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MANAGE_SECRETS
    )
    if error_response:
        return error_response
    try:
        actor_member_id = project_routes._project_actor_member_id(session_id, team_id)
        data = request.get_json(silent=True)

        def _update(conn):
            profile = update_http_profile_on_conn(
                conn,
                session_id,
                project_id,
                profile_id,
                data,
                team_id=team_id,
                actor_member_id=actor_member_id,
            )
            project_routes.record_event(
                AuditEventType.HTTP_PROFILE_UPDATE,
                target_id=profile_id,
                project_id=project_id,
                details=http_profile_audit_summary(profile),
                conn=conn,
                **project_routes._project_audit_fields(session_id, team_id),
            )
            return profile

        profile = run_project_transaction(_update)
    except (HttpProfileError, ProjectWorkspaceQuotaExceeded) as exc:
        return _error(exc)
    project_routes.log.info(
        "PROJECT_HTTP_PROFILE_UPDATED",
        extra=_log_fields(session_id, team_id, project_id, profile),
    )
    return jsonify({"ok": True, "profile": profile})


@project_routes.projects_bp.route(
    "/projects/<project_id>/http-profiles/<profile_id>", methods=["DELETE"]
)
@limiter.limit(project_routes._project_write_limit)
def projects_http_profiles_delete(project_id, profile_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MANAGE_SECRETS
    )
    if error_response:
        return error_response
    try:
        def _delete(conn):
            summary = delete_http_profile_on_conn(
                conn,
                session_id,
                project_id,
                profile_id,
                team_id=team_id,
            )
            project_routes.record_event(
                AuditEventType.HTTP_PROFILE_DELETE,
                target_id=profile_id,
                project_id=project_id,
                details={**summary, "deleted_count": 1},
                conn=conn,
                **project_routes._project_audit_fields(session_id, team_id),
            )
            return summary

        summary = run_project_transaction(_delete)
    except HttpProfileError as exc:
        return _error(exc)
    project_routes.log.info(
        "PROJECT_HTTP_PROFILE_DELETED",
        extra=_log_fields(session_id, team_id, project_id, summary),
    )
    return jsonify({"ok": True, "removed": True})
