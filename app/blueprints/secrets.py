"""Encrypted per-session secrets routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from config import CFG
from core.helpers import get_session_id
from extensions import limiter
from services.secrets.audit import emit_secret_event
from services.secrets.storage import (
    InvalidSecretName,
    SecretConsumerEnvConflict,
    delete_secret,
    list_secret_metadata,
    rewrap_session_secrets,
    upsert_secret,
)
from services.secrets.vault import InvalidSecretValue, MasterKeyError, SecretDecryptError

secrets_bp = Blueprint("secrets", __name__)


def _secrets_route_limit():
    limit = int(CFG.get("secrets_rate_limit_per_minute") or 30)
    return f"{limit} per minute"


def _secret_error(exc):
    if isinstance(exc, InvalidSecretName):
        return jsonify({"error": "invalid_name"}), 400
    if isinstance(exc, SecretConsumerEnvConflict):
        return jsonify({
            "error": "consumer_env_conflict",
            "env": exc.env_name,
            "existing_name": exc.existing_name,
        }), 409
    if isinstance(exc, InvalidSecretValue):
        return jsonify({"error": "invalid_value", "message": str(exc)}), 400
    if isinstance(exc, (MasterKeyError, SecretDecryptError)):
        return jsonify({"error": "vault_unavailable"}), 503
    return jsonify({"error": "invalid_secret"}), 400


def _required_session_id():
    session_id = get_session_id()
    if not session_id:
        return "", (jsonify({"error": "session_required"}), 401)
    return session_id, None


@secrets_bp.route("/session/secrets", methods=["GET"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_list():
    session_id, error_response = _required_session_id()
    if error_response:
        return error_response
    try:
        return jsonify({"secrets": list_secret_metadata(session_id)})
    except (InvalidSecretName, SecretConsumerEnvConflict, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)


@secrets_bp.route("/session/secrets", methods=["POST"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_upsert():
    session_id, error_response = _required_session_id()
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    if "value" not in data:
        return jsonify({"error": "value_required"}), 400
    try:
        metadata, created = upsert_secret(
            session_id,
            str(data.get("name") or ""),
            str(data.get("value") or ""),
            data.get("consumer_envs"),
        )
    except (InvalidSecretName, SecretConsumerEnvConflict, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)
    emit_secret_event(
        "SECRET_CREATED" if created else "SECRET_UPDATED",
        session_id,
        name=str(metadata["name"]),
        consumer_envs=metadata["consumer_envs"],
    )
    return jsonify(metadata), 201 if created else 200


@secrets_bp.route("/session/secrets/<name>", methods=["DELETE"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_delete(name):
    session_id, error_response = _required_session_id()
    if error_response:
        return error_response
    try:
        removed = delete_secret(session_id, name)
    except (InvalidSecretName, SecretConsumerEnvConflict, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)
    if removed:
        emit_secret_event("SECRET_DELETED", session_id, name=str(name or "").strip().upper())
    else:
        emit_secret_event("SECRET_DELETE_NOOP", session_id, name=str(name or "").strip().upper())
    return jsonify({"removed": removed})


@secrets_bp.route("/session/secrets/rotate", methods=["POST"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_rotate():
    session_id, error_response = _required_session_id()
    if error_response:
        return error_response
    try:
        count = rewrap_session_secrets(session_id)
    except (InvalidSecretName, SecretConsumerEnvConflict, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)
    emit_secret_event("SECRET_ROTATED", session_id, count=count)
    return jsonify({"rewrapped": count})
