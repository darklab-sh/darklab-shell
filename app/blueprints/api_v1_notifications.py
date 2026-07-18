# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 notification channel routes."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.projects.utils import normalize_page_limit, normalize_page_offset
from services.notifications.channels_store import (
    NotificationChannelError,
    create_notification_channel,
    delete_notification_channel,
    list_notification_channels,
    list_notification_events,
    notification_channel_kind_contract,
    send_test_notification,
    update_notification_channel,
)
from services.secrets.vault import MasterKeyError, SecretDecryptError
from services.teams.contracts import TeamPermissionDenied


@api_routes.api_v1_bp.route("/notification-channels", methods=["GET"])
@api_routes.require_api_auth
def api_notification_channels():
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        return jsonify({"channels": list_notification_channels(session_id, team_id=owner_scope.team_id)})
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return api_routes._notification_api_error(exc)


@api_routes.api_v1_bp.route("/notification-channel-kinds", methods=["GET"])
@api_routes.require_api_auth
def api_notification_channel_kinds():
    return jsonify(notification_channel_kind_contract())


@api_routes.api_v1_bp.route("/notification-channels", methods=["POST"])
@api_routes.require_api_auth
def api_notification_channel_create():
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._require_notification_manage_scope()
        channel = create_notification_channel(
            session_id,
            api_routes._json_body(),
            team_id=owner_scope.team_id,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
            audit_source="api_v1",
        )
    except api_routes.ApiAuthError as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return api_routes._notification_api_error(exc)
    api_routes.log.info("API_NOTIFICATION_CHANNEL_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(api_routes._require_session_id()),
        "channel_id": channel["id"],
        "kind": channel["kind"],
    })
    return jsonify({"channel": channel}), 201


@api_routes.api_v1_bp.route("/notification-channels/<channel_id>", methods=["PATCH"])
@api_routes.require_api_auth
def api_notification_channel_update(channel_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._require_notification_manage_scope()
        channel = update_notification_channel(
            session_id,
            channel_id,
            api_routes._json_body(),
            team_id=owner_scope.team_id,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
            audit_source="api_v1",
        )
    except api_routes.ApiAuthError as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return api_routes._notification_api_error(exc)
    api_routes.log.info("API_NOTIFICATION_CHANNEL_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(api_routes._require_session_id()),
        "channel_id": channel["id"],
        "kind": channel["kind"],
    })
    return jsonify({"channel": channel})


@api_routes.api_v1_bp.route("/notification-channels/<channel_id>", methods=["DELETE"])
@api_routes.require_api_auth
def api_notification_channel_delete(channel_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._require_notification_manage_scope()
        removed = delete_notification_channel(
            session_id,
            channel_id,
            team_id=owner_scope.team_id,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
            audit_source="api_v1",
        )
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return api_routes._notification_api_error(exc)
    api_routes.log.info("API_NOTIFICATION_CHANNEL_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(api_routes._require_session_id()),
        "channel_id": channel_id,
        "removed": removed,
    })
    return jsonify({"removed": removed})


@api_routes.api_v1_bp.route("/notification-channels/<channel_id>/test", methods=["POST"])
@api_routes.require_api_auth
def api_notification_channel_test(channel_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._require_notification_manage_scope()
        result = send_test_notification(
            session_id,
            channel_id,
            team_id=owner_scope.team_id,
            audit_fields=api_routes.route_audit_fields(session_id, request, owner_scope),
            audit_source="api_v1",
        )
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return api_routes._notification_api_error(exc)
    api_routes.log.info("API_NOTIFICATION_CHANNEL_TESTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(api_routes._require_session_id()),
        "channel_id": channel_id,
        "event_count": int(result.get("queued") or 0),
    })
    return jsonify(result)


@api_routes.api_v1_bp.route("/notification-events")
@api_routes.require_api_auth
def api_notification_events():
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        events = list_notification_events(
            session_id,
            limit=normalize_page_limit(request.args.get("limit"), 50, 100),
            offset=normalize_page_offset(request.args.get("offset")),
            status=str(request.args.get("status") or ""),
            channel_id=str(request.args.get("channel_id") or ""),
            trigger=str(request.args.get("trigger") or ""),
            team_id=owner_scope.team_id,
        )
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return api_routes._notification_api_error(exc)
    return jsonify(events)
