"""Browser routes for session-owned outbound notification channels."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from config import CFG
from core.helpers import get_session_id
from extensions import limiter
from services.notifications.channels_store import (
    NotificationChannelError,
    create_notification_channel,
    delete_notification_channel,
    list_notification_channels,
    send_test_notification,
    update_notification_channel,
)
from services.secrets.vault import MasterKeyError, SecretDecryptError

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
    if isinstance(exc, (MasterKeyError, SecretDecryptError)):
        return jsonify({"error": "vault_unavailable"}), 503
    if isinstance(exc, ValueError):
        return jsonify({"error": "invalid_notification_channel", "message": str(exc)}), 400
    return jsonify({"error": "invalid_notification_channel"}), 400


@notifications_bp.route("/session/notification-channels", methods=["GET"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_channels_list():
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        return jsonify({"channels": list_notification_channels(session_id)})
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
        channel = create_notification_channel(session_id, data)
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
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
        channel = update_notification_channel(session_id, channel_id, data)
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_error(exc)
    return jsonify({"channel": channel})


@notifications_bp.route("/session/notification-channels/<channel_id>", methods=["DELETE"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_channels_delete(channel_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        removed = delete_notification_channel(session_id, channel_id)
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_error(exc)
    return jsonify({"removed": removed})


@notifications_bp.route("/session/notification-channels/<channel_id>/test", methods=["POST"])
@limiter.limit(_notification_route_limit, key_func=get_session_id)
def session_notification_channels_test(channel_id):
    session_id, error_response = _required_token_session()
    if error_response:
        return error_response
    try:
        event_ids = send_test_notification(session_id, channel_id)
    except (NotificationChannelError, MasterKeyError, SecretDecryptError, ValueError) as exc:
        return _notification_error(exc)
    return jsonify({"queued": len(event_ids), "event_ids": event_ids})
