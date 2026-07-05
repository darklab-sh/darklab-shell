"""API v1 watcher routes."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload
from services.scheduler.route_helpers import normalize_watcher_update_payload
from services.watchers import api_operations as watcher_api
from services.watchers.serialization import watcher_fire_payload, watcher_payload


@api_routes.api_v1_bp.route("/watchers", methods=["GET"])
@api_routes.require_api_auth
def api_watchers():
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        watchers, schedules = watcher_api.list_watchers_for_api(session_id, team_id=owner_scope.team_id)
    except (api_routes.WatcherError, api_routes.ScheduleError, ValueError) as exc:
        return api_routes._watcher_api_error(exc)
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    api_routes.log.debug("API_WATCHERS_LISTED", extra=api_routes._api_watcher_log_payload(
        None,
        session_id=session_id,
        count=len(watchers),
        limit=limit,
        offset=offset,
    ))
    payloads = [
        watcher_payload(watcher, schedule=schedules.get(watcher.schedule_id))
        for watcher in watchers
    ]
    return jsonify(page_payload("watchers", payloads[offset:offset + limit], len(payloads), limit, offset))


@api_routes.api_v1_bp.route("/watchers", methods=["POST"])
@api_routes.require_api_auth
def api_watcher_create():
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MANAGE_AUTOMATION)
        data = api_routes._json_body()
        watcher, schedule = watcher_api.create_watcher_from_body_for_api(
            session_id,
            team_id=owner_scope.team_id,
            data=data,
            command_validator=api_routes.validate_schedule_command,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
        )
    except (
        api_routes.ApiAuthError,
        api_routes.TeamPermissionDenied,
        api_routes.WatcherError,
        api_routes.ScheduleError,
        api_routes.ScheduleCronError,
        api_routes.ScheduleCommandValidationError,
        api_routes.SessionVariableError,
        ValueError,
    ) as exc:
        return api_routes._watcher_api_error(exc)
    api_routes.log.info("API_WATCHER_CREATED", extra=api_routes._api_watcher_log_payload(watcher, session_id=session_id))
    return jsonify({"watcher": watcher_payload(watcher, schedule=schedule)}), 201


@api_routes.api_v1_bp.route("/watchers/<watcher_id>", methods=["GET"])
@api_routes.require_api_auth
def api_watcher(watcher_id):
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        watcher, schedule = watcher_api.watcher_detail_for_api(watcher_id, session_id, team_id=owner_scope.team_id)
    except (api_routes.ApiAuthError, api_routes.WatcherError, api_routes.ScheduleError, ValueError) as exc:
        return api_routes._watcher_api_error(exc)
    return jsonify({"watcher": watcher_payload(watcher, schedule=schedule)})


@api_routes.api_v1_bp.route("/watchers/<watcher_id>", methods=["PATCH"])
@api_routes.require_api_auth
def api_watcher_update(watcher_id):
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MANAGE_AUTOMATION)
        data = api_routes._json_body()
        route_update = normalize_watcher_update_payload(
            data,
            session_id,
            command_validator=api_routes.validate_schedule_command,
        )
        updated, schedule = watcher_api.update_watcher_for_api(
            watcher_id,
            session_id,
            team_id=owner_scope.team_id,
            route_update=route_update,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
        )
    except (
        api_routes.ApiAuthError,
        api_routes.TeamPermissionDenied,
        api_routes.WatcherError,
        api_routes.ScheduleError,
        api_routes.ScheduleCronError,
        api_routes.ScheduleCommandValidationError,
        api_routes.SessionVariableError,
        ValueError,
    ) as exc:
        return api_routes._watcher_api_error(exc)
    api_routes.log.info("API_WATCHER_UPDATED", extra=api_routes._api_watcher_log_payload(
        updated,
        session_id=session_id,
        changed_fields=",".join(sorted(key for key in data if key != "workspace_cwd")),
    ))
    return jsonify({"watcher": watcher_payload(updated, schedule=schedule)})


@api_routes.api_v1_bp.route("/watchers/<watcher_id>", methods=["DELETE"])
@api_routes.require_api_auth
def api_watcher_delete(watcher_id):
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MANAGE_AUTOMATION)
        watcher, removed = watcher_api.delete_watcher_for_api(
            watcher_id,
            session_id,
            team_id=owner_scope.team_id,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
        )
    except (
        api_routes.ApiAuthError,
        api_routes.TeamPermissionDenied,
        api_routes.WatcherError,
        api_routes.ScheduleError,
        ValueError,
    ) as exc:
        return api_routes._watcher_api_error(exc)
    api_routes.log.info(
        "API_WATCHER_DELETED",
        extra=api_routes._api_watcher_log_payload(watcher, session_id=session_id, removed=removed),
    )
    return jsonify({"removed": removed})


@api_routes.api_v1_bp.route("/watchers/<watcher_id>/run-now", methods=["POST"])
@api_routes.require_api_auth
def api_watcher_run_now(watcher_id):
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MANAGE_AUTOMATION)
        status, refreshed, refreshed_schedule, fired_at = watcher_api.fire_watcher_now_for_api(
            watcher_id,
            session_id,
            team_id=owner_scope.team_id,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
        )
    except (
        api_routes.ApiAuthError,
        api_routes.TeamPermissionDenied,
        api_routes.WatcherError,
        api_routes.ScheduleError,
        api_routes.ScheduleCronError,
        ValueError,
    ) as exc:
        return api_routes._watcher_api_error(exc)
    api_routes.log.info("API_WATCHER_RUN_NOW", extra=api_routes._api_watcher_log_payload(
        refreshed,
        session_id=session_id,
        status=status,
        fired_at=fired_at,
        run_id=refreshed.last_run_id,
        last_error=refreshed.last_error,
    ))
    return jsonify({
        "status": status,
        "fired_at": fired_at,
        "watcher": watcher_payload(refreshed, schedule=refreshed_schedule),
    })


@api_routes.api_v1_bp.route("/watchers/<watcher_id>/fires", methods=["GET"])
@api_routes.require_api_auth
def api_watcher_fires(watcher_id):
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        limit = normalize_page_limit(request.args.get("limit"), 50, 100)
        offset = normalize_page_offset(request.args.get("offset"))
        watcher, fires, total = watcher_api.watcher_fires_for_api(
            watcher_id,
            session_id,
            team_id=owner_scope.team_id,
            limit=limit,
            offset=offset,
        )
    except (api_routes.ApiAuthError, api_routes.WatcherError, ValueError) as exc:
        return api_routes._watcher_api_error(exc)
    api_routes.log.debug("API_WATCHER_FIRES_LISTED", extra=api_routes._api_watcher_log_payload(
        watcher,
        session_id=session_id,
        count=len(fires),
        total=total,
        limit=limit,
        offset=offset,
    ))
    return jsonify(page_payload("fires", [watcher_fire_payload(fire) for fire in fires], total, limit, offset))


@api_routes.api_v1_bp.route("/watchers/<watcher_id>/accept-baseline", methods=["POST"])
@api_routes.require_api_auth
def api_watcher_accept_baseline(watcher_id):
    session_id = api_routes._require_session_id()
    try:
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MANAGE_AUTOMATION)
        data = api_routes._json_body()
        accepted, schedule = watcher_api.accept_watcher_baseline_for_api(
            watcher_id,
            session_id,
            team_id=owner_scope.team_id,
            run_id=data.get("run_id"),
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
        )
    except (
        api_routes.ApiAuthError,
        api_routes.TeamPermissionDenied,
        api_routes.WatcherError,
        api_routes.ScheduleError,
        ValueError,
    ) as exc:
        return api_routes._watcher_api_error(exc)
    api_routes.log.info(
        "API_WATCHER_BASELINE_ACCEPTED",
        extra=api_routes._api_watcher_log_payload(accepted, session_id=session_id),
    )
    return jsonify({"watcher": watcher_payload(accepted, schedule=schedule)})
