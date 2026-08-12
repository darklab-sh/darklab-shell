# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 routes for Project HTTP assessment profiles."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
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
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.queries import run_project_transaction
from services.teams.capabilities import Capability, role_can
from services.teams.contracts import TeamPermissionDenied


def _error(exc: Exception):
    if isinstance(exc, HttpProfileNotFound):
        code, status = "not_found", 404
    elif isinstance(exc, ProjectWorkspaceQuotaExceeded):
        code, status = "quota_exceeded", 409
    elif isinstance(exc, HttpProfileConflict):
        code, status = "http_profile_conflict", 409
    elif isinstance(exc, TeamPermissionDenied):
        code, status = "team_forbidden", 403
    else:
        code, status = "invalid_http_profile", 400
    return api_routes._api_json_error(code, str(exc), status)


def _request_context(*, write: bool = False):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    if write:
        api_routes._require_api_team_capability(
            owner_scope,
            Capability.MANAGE_SECRETS,
        )
    actor_member_id = str((owner_scope.member or {}).get("id") or "")
    return session_id, owner_scope, actor_member_id


def _can_manage_references(owner_scope) -> bool:
    if not owner_scope.is_team:
        return True
    return role_can(
        str((owner_scope.member or {}).get("role") or ""),
        Capability.MANAGE_SECRETS,
    )


def _audit_details(profile: dict, *, deleted_count: int = 0) -> dict:
    summary = http_profile_audit_summary(profile)
    details = {"source": "api_v1", **summary}
    if deleted_count:
        details["deleted_count"] = deleted_count
    return details


def _log_fields(session_id: str, owner_scope, project_id: str, profile: dict):
    summary = http_profile_audit_summary(profile)
    return {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": owner_scope.team_id,
        "project_id": project_id,
        "profile_id": summary["profile_id"],
        "role": summary["role"],
        "enabled": summary["enabled"],
        "reference_counts": summary["counts"],
        "source": "api_v1",
    }


@api_routes.api_v1_bp.route("/projects/<project_id>/http-profiles")
@api_routes.require_api_auth
def api_project_http_profiles(project_id):
    try:
        session_id, owner_scope, _actor_member_id = _request_context()
        profiles = list_http_profiles(
            session_id,
            project_id,
            team_id=owner_scope.team_id,
            include_references=_can_manage_references(owner_scope),
        )
    except (HttpProfileError, TeamPermissionDenied) as exc:
        return _error(exc)
    if profiles is None:
        return api_routes._api_json_error("not_found", "Project not found.", 404)
    return jsonify(profiles)


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/http-profiles/<profile_id>"
)
@api_routes.require_api_auth
def api_project_http_profile(project_id, profile_id):
    try:
        session_id, owner_scope, _actor_member_id = _request_context()
        profile = get_http_profile(
            session_id,
            project_id,
            profile_id,
            team_id=owner_scope.team_id,
            include_references=_can_manage_references(owner_scope),
        )
    except (HttpProfileError, TeamPermissionDenied) as exc:
        return _error(exc)
    if profile is None:
        return api_routes._api_json_error("not_found", "HTTP profile not found.", 404)
    return jsonify({"profile": profile})


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/http-profiles",
    methods=["POST"],
)
@api_routes.require_api_auth
def api_project_http_profile_create(project_id):
    try:
        session_id, owner_scope, actor_member_id = _request_context(write=True)
        data = api_routes._json_body()

        def _create(conn):
            profile = create_http_profile_on_conn(
                conn,
                session_id,
                project_id,
                data,
                team_id=owner_scope.team_id,
                actor_member_id=actor_member_id,
            )
            record_event(
                AuditEventType.HTTP_PROFILE_CREATE,
                target_id=profile["id"],
                project_id=project_id,
                details=_audit_details(profile),
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return profile

        profile = run_project_transaction(_create)
    except (
        HttpProfileError,
        ProjectWorkspaceQuotaExceeded,
        TeamPermissionDenied,
    ) as exc:
        return _error(exc)
    api_routes.log.info(
        "API_PROJECT_HTTP_PROFILE_CREATED",
        extra=_log_fields(session_id, owner_scope, project_id, profile),
    )
    return jsonify({"ok": True, "profile": profile}), 201


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/http-profiles/<profile_id>",
    methods=["PATCH"],
)
@api_routes.require_api_auth
def api_project_http_profile_update(project_id, profile_id):
    try:
        session_id, owner_scope, actor_member_id = _request_context(write=True)
        data = api_routes._json_body()

        def _update(conn):
            profile = update_http_profile_on_conn(
                conn,
                session_id,
                project_id,
                profile_id,
                data,
                team_id=owner_scope.team_id,
                actor_member_id=actor_member_id,
            )
            record_event(
                AuditEventType.HTTP_PROFILE_UPDATE,
                target_id=profile_id,
                project_id=project_id,
                details=_audit_details(profile),
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return profile

        profile = run_project_transaction(_update)
    except (
        HttpProfileError,
        ProjectWorkspaceQuotaExceeded,
        TeamPermissionDenied,
    ) as exc:
        return _error(exc)
    api_routes.log.info(
        "API_PROJECT_HTTP_PROFILE_UPDATED",
        extra=_log_fields(session_id, owner_scope, project_id, profile),
    )
    return jsonify({"ok": True, "profile": profile})


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/http-profiles/<profile_id>",
    methods=["DELETE"],
)
@api_routes.require_api_auth
def api_project_http_profile_delete(project_id, profile_id):
    try:
        session_id, owner_scope, _actor_member_id = _request_context(write=True)

        def _delete(conn):
            summary = delete_http_profile_on_conn(
                conn,
                session_id,
                project_id,
                profile_id,
                team_id=owner_scope.team_id,
            )
            record_event(
                AuditEventType.HTTP_PROFILE_DELETE,
                target_id=profile_id,
                project_id=project_id,
                details=_audit_details(summary, deleted_count=1),
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
            return summary

        summary = run_project_transaction(_delete)
    except (
        HttpProfileError,
        ProjectWorkspaceQuotaExceeded,
        TeamPermissionDenied,
    ) as exc:
        return _error(exc)
    api_routes.log.info(
        "API_PROJECT_HTTP_PROFILE_DELETED",
        extra=_log_fields(session_id, owner_scope, project_id, summary),
    )
    return jsonify({"ok": True, "removed": True})
