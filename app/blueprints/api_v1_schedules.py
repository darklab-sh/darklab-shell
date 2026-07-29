# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 schedule routes."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from services.scheduler import api_operations as schedule_api
from services.scheduler.route_helpers import normalize_schedule_create_payload, normalize_schedule_update_payload
from services.scheduler.serialization import schedule_fire_payload, schedule_payload
from services.scheduler.service import list_for_owner as list_schedules_for_owner, list_schedule_fires
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload


@api_routes.api_v1_bp.route("/schedules", methods=["GET"])
@api_routes.require_api_auth
def api_schedules():
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        schedules = [
            schedule_payload(schedule)
            for schedule in list_schedules_for_owner(session_id, team_id=owner_scope.team_id)
        ]
    except (api_routes.ScheduleError, api_routes.ScheduleCronError, ValueError) as exc:
        return api_routes._schedule_api_error(exc)
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    api_routes.log.debug("API_SCHEDULES_LISTED", extra=api_routes._api_schedule_log_payload(
        None,
        session_id=session_id,
        count=len(schedules),
        limit=limit,
        offset=offset,
    ))
    return jsonify(page_payload("schedules", schedules[offset:offset + limit], len(schedules), limit, offset))


@api_routes.api_v1_bp.route("/schedules", methods=["POST"])
@api_routes.require_api_auth
def api_schedule_create():
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MANAGE_AUTOMATION)
        data = api_routes._json_body()
        payload = normalize_schedule_create_payload(
            data,
            session_id,
            command_validator=api_routes.validate_schedule_command,
        )
        schedule = schedule_api.create_schedule_for_api(
            session_id,
            team_id=owner_scope.team_id,
            payload=payload,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
        )
    except (
        api_routes.ApiAuthError,
        api_routes.TeamPermissionDenied,
        api_routes.ScheduleError,
        api_routes.ScheduleCronError,
        api_routes.ScheduleCommandValidationError,
        api_routes.SessionVariableError,
        ValueError,
    ) as exc:
        return api_routes._schedule_api_error(exc)
    api_routes.log.info("API_SCHEDULE_CREATED", extra=api_routes._api_schedule_log_payload(schedule, session_id=session_id))
    return jsonify({"schedule": schedule_payload(schedule)}), 201


@api_routes.api_v1_bp.route("/schedules/<schedule_id>", methods=["GET"])
@api_routes.require_api_auth
def api_schedule(schedule_id):
    try:
        owner_scope = api_routes._api_request_scope()
        schedule = api_routes._schedule_for_api_session(
            schedule_id,
            api_routes._require_session_id(),
            team_id=owner_scope.team_id,
        )
        next_fires = api_routes._api_schedule_next_fires(schedule)
    except (api_routes.ApiAuthError, api_routes.ScheduleError, api_routes.ScheduleCronError, ValueError) as exc:
        return api_routes._schedule_api_error(exc)
    return jsonify({"schedule": schedule_payload(schedule), "next_fires": next_fires})


@api_routes.api_v1_bp.route("/schedules/<schedule_id>", methods=["PATCH"])
@api_routes.require_api_auth
def api_schedule_update(schedule_id):
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MANAGE_AUTOMATION)
        schedule = api_routes._schedule_for_api_session(schedule_id, session_id, team_id=owner_scope.team_id)
        updates = normalize_schedule_update_payload(
            api_routes._json_body(),
            session_id,
            command_validator=api_routes.validate_schedule_command,
        )
        updated = schedule_api.update_schedule_for_api(
            schedule.id,
            updates,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
        )
    except (
        api_routes.ApiAuthError,
        api_routes.TeamPermissionDenied,
        api_routes.ScheduleError,
        api_routes.ScheduleCronError,
        api_routes.ScheduleCommandValidationError,
        api_routes.SessionVariableError,
        ValueError,
    ) as exc:
        return api_routes._schedule_api_error(exc)
    if updated is None:
        return api_routes._api_json_error("not_found", "Schedule not found.", 404)
    api_routes.log.info("API_SCHEDULE_UPDATED", extra=api_routes._api_schedule_log_payload(
        updated,
        session_id=session_id,
        changed_fields=",".join(sorted(key for key in updates if key != "workspace_cwd")),
    ))
    return jsonify({"schedule": schedule_payload(updated)})


@api_routes.api_v1_bp.route("/schedules/<schedule_id>", methods=["DELETE"])
@api_routes.require_api_auth
def api_schedule_delete(schedule_id):
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MANAGE_AUTOMATION)
        schedule = api_routes._schedule_for_api_session(schedule_id, session_id, team_id=owner_scope.team_id)
    except (api_routes.ApiAuthError, api_routes.TeamPermissionDenied) as exc:
        return api_routes._schedule_api_error(exc)
    removed = schedule_api.delete_schedule_for_api(
        schedule,
        audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
    )
    api_routes.log.info(
        "API_SCHEDULE_DELETED",
        extra=api_routes._api_schedule_log_payload(schedule, session_id=session_id, removed=removed),
    )
    return jsonify({"removed": removed})


@api_routes.api_v1_bp.route("/schedules/<schedule_id>/run-now", methods=["POST"])
@api_routes.require_api_auth
def api_schedule_run_now(schedule_id):
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MANAGE_AUTOMATION)
        schedule = api_routes._schedule_for_api_session(schedule_id, session_id, team_id=owner_scope.team_id)
        status, refreshed, fired_at = schedule_api.fire_schedule_now_for_api(
            schedule,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
        )
    except (
        api_routes.ApiAuthError,
        api_routes.TeamPermissionDenied,
        api_routes.ScheduleError,
        api_routes.ScheduleCronError,
        ValueError,
    ) as exc:
        return api_routes._schedule_api_error(exc)
    api_routes.log.info("API_SCHEDULE_RUN_NOW", extra=api_routes._api_schedule_log_payload(
        refreshed or schedule,
        session_id=session_id,
        fire_status=status,
        fired_at=fired_at,
        run_id=refreshed.last_run_id,
        last_error=refreshed.last_error,
    ))
    return jsonify({
        "status": status,
        "fired_at": fired_at,
        "schedule": schedule_payload(refreshed),
    })


@api_routes.api_v1_bp.route("/schedules/<schedule_id>/fires", methods=["GET"])
@api_routes.require_api_auth
def api_schedule_fires(schedule_id):
    try:
        owner_scope = api_routes._api_request_scope()
        schedule = api_routes._schedule_for_api_session(
            schedule_id,
            api_routes._require_session_id(),
            team_id=owner_scope.team_id,
        )
        limit = normalize_page_limit(request.args.get("limit"), 50, 100)
        offset = normalize_page_offset(request.args.get("offset"))
        fires, total = list_schedule_fires(schedule.id, limit=limit, offset=offset)
    except (api_routes.ApiAuthError, api_routes.ScheduleError, ValueError) as exc:
        return api_routes._schedule_api_error(exc)
    api_routes.log.debug("API_SCHEDULE_FIRES_LISTED", extra=api_routes._api_schedule_log_payload(
        schedule,
        session_id=schedule.session_token,
        count=len(fires),
        total=total,
        limit=limit,
        offset=offset,
    ))
    return jsonify(page_payload(
        "fires",
        [schedule_fire_payload(fire) for fire in fires],
        total,
        limit,
        offset,
    ))
