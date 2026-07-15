# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for session-owned outbound notification channels."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from config import CFG
from core.helpers import get_session_id
from extensions import limiter
from services.audit.context import route_audit_fields
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
from services.projects.utils import normalize_page_limit, normalize_page_offset
from services.secrets.vault import MasterKeyError, SecretDecryptError
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScopeError, current_request_scope, scope_error_payload

notifications_bp = Blueprint("notifications", __name__)


def _notification_route_limit():
    limit = int(CFG.get("secrets_rate_limit_per_minute") or 30)
    return f"{limit} per minute"


def _required_token_session():
    session_id = get_session_id()
    if not session_id:
        return "", (jsonify({"error": "session_required"}), 401)
    if not str(session_id).startswith("tok_"):
        return "", (jsonify({"error": "session_token_required"}), 401)
    return session_id, None


def _json_body() -> tuple[dict[str, Any] | None, Any]:
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    return data, None


def _notification_error(exc):
    if isinstance(exc, NotificationChannelError):
        return jsonify({"error": exc.code, "message": str(exc)}), exc.status_code
    if isinstance(exc, TeamPermissionDenied):
        return jsonify({"error": "team_forbidden", "message": str(exc)}), 403
    if isinstance(exc, (MasterKeyError, SecretDecryptError)):
        return jsonify({"error": "vault_unavailable"}), 503
    if isinstance(exc, ValueError):
        return jsonify({"error": "invalid_notification_channel", "message": str(exc)}), 400
    return jsonify({"error": "invalid_notification_channel"}), 400


def _notification_scope(session_id: str):
    try:
        return current_request_scope(session_id, request), None
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return None, (jsonify(payload), status)


def _require_manage_notifications(scope) -> None:
    if scope is None or not scope.is_team:
        return
    member = scope.member or {}
    require_capability(str(member.get("role") or ""), Capability.MANAGE_NOTIFICATIONS)


@notifications_bp.route("/session/notification-channels", methods=["GET"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_channels_list():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    scope, scope_error = _notification_scope(session_id)
    if scope_error:
        return scope_error
    try:
        return jsonify({"channels": list_notification_channels(session_id, team_id=scope.team_id if scope else "")})
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_error(exc)


@notifications_bp.route("/session/notification-channel-kinds", methods=["GET"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_channel_kinds():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    return jsonify(notification_channel_kind_contract())


@notifications_bp.route("/session/notification-events", methods=["GET"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_events_list():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    scope, scope_error = _notification_scope(session_id)
    if scope_error:
        return scope_error
    try:
        return jsonify(
            list_notification_events(
                session_id,
                limit=normalize_page_limit(request.args.get("limit"), default=10, maximum=50),
                offset=normalize_page_offset(request.args.get("offset")),
                status=str(request.args.get("status") or ""),
                channel_id=str(request.args.get("channel_id") or ""),
                trigger=str(request.args.get("trigger") or ""),
                team_id=scope.team_id if scope else "",
            )
        )
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_error(exc)


@notifications_bp.route("/session/notification-channels", methods=["POST"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_channels_create():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    if data is None:
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        scope, scope_error = _notification_scope(session_id)
        if scope_error:
            return scope_error
        _require_manage_notifications(scope)
        channel = create_notification_channel(
            session_id,
            data,
            team_id=scope.team_id if scope else "",
            audit_fields=route_audit_fields(session_id, request, scope),
            audit_source="browser",
        )
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_error(exc)
    return jsonify({"channel": channel}), 201


@notifications_bp.route("/session/notification-channels/<channel_id>", methods=["PATCH"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_channels_update(channel_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    if data is None:
        return jsonify({"error": "Request body must be a JSON object"}), 400
    try:
        scope, scope_error = _notification_scope(session_id)
        if scope_error:
            return scope_error
        _require_manage_notifications(scope)
        channel = update_notification_channel(
            session_id,
            channel_id,
            data,
            team_id=scope.team_id if scope else "",
            audit_fields=route_audit_fields(session_id, request, scope),
            audit_source="browser",
        )
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_error(exc)
    return jsonify({"channel": channel})


@notifications_bp.route("/session/notification-channels/<channel_id>", methods=["DELETE"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_channels_delete(channel_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        scope, scope_error = _notification_scope(session_id)
        if scope_error:
            return scope_error
        _require_manage_notifications(scope)
        removed = delete_notification_channel(
            session_id,
            channel_id,
            team_id=scope.team_id if scope else "",
            audit_fields=route_audit_fields(session_id, request, scope),
            audit_source="browser",
        )
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_error(exc)
    return jsonify({"removed": removed})


@notifications_bp.route("/session/notification-channels/<channel_id>/test", methods=["POST"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_channels_test(channel_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        scope, scope_error = _notification_scope(session_id)
        if scope_error:
            return scope_error
        _require_manage_notifications(scope)
        result = send_test_notification(
            session_id,
            channel_id,
            team_id=scope.team_id if scope else "",
            audit_fields=route_audit_fields(session_id, request, scope),
            audit_source="browser",
        )
    except (NotificationChannelError, TeamPermissionDenied, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_error(exc)
    return jsonify(result)
