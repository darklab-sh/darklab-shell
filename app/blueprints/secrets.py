"""Encrypted per-session secrets routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from config import CFG
from core.helpers import get_session_id
from extensions import limiter
from services.secrets.audit import emit_secret_event
from services.secrets.storage import (
    InvalidSecretName,
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
    if isinstance(exc, InvalidSecretValue):
        return jsonify({"error": "invalid_value", "message": str(exc)}), 400
    if isinstance(exc, (MasterKeyError, SecretDecryptError)):
        return jsonify({"error": "vault_unavailable"}), 503
    return jsonify({"error": "invalid_secret"}), 400


@secrets_bp.route("/session/secrets", methods=["GET"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_list():
    try:
        return jsonify({"secrets": list_secret_metadata(get_session_id())})
    except (InvalidSecretName, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)


@secrets_bp.route("/session/secrets", methods=["POST"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_upsert():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    if "value" not in data:
        return jsonify({"error": "value_required"}), 400
    try:
        metadata, created = upsert_secret(
            get_session_id(),
            str(data.get("name") or ""),
            str(data.get("value") or ""),
            data.get("consumer_envs"),
        )
    except (InvalidSecretName, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)
    emit_secret_event(
        "SECRET_CREATED" if created else "SECRET_UPDATED",
        get_session_id(),
        name=str(metadata["name"]),
        consumer_envs=metadata["consumer_envs"],
    )
    return jsonify(metadata), 201 if created else 200


@secrets_bp.route("/session/secrets/<name>", methods=["DELETE"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_delete(name):
    try:
        removed = delete_secret(get_session_id(), name)
    except (InvalidSecretName, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)
    if removed:
        emit_secret_event("SECRET_DELETED", get_session_id(), name=str(name or "").strip().upper())
    return jsonify({"removed": removed})


@secrets_bp.route("/session/secrets/rotate", methods=["POST"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_rotate():
    try:
        count = rewrap_session_secrets(get_session_id())
    except (InvalidSecretName, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)
    emit_secret_event("SECRET_ROTATED", get_session_id(), count=count)
    return jsonify({"rewrapped": count})
