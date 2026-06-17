"""Encrypted per-session secrets routes."""

from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, request

from config import CFG
from core.helpers import get_session_id
from extensions import limiter
from services.audit.context import route_audit_fields
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
from services.teams.capabilities import Capability, require_capability, role_can
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScope, RequestScopeError, current_request_scope, scope_error_payload

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


def _active_secret_scope() -> tuple[str, RequestScope | None, str, Any]:
    session_id, error_response = _required_session_id()
    if error_response:
        return "", None, "", error_response
    try:
        scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return session_id, None, "", (jsonify(payload), status)
    return session_id, scope, scope.owner_id, None


def _secret_scope_payload(scope: RequestScope) -> dict[str, str | bool]:
    role = str((scope.member or {}).get("role") or "")
    return {
        "scope": "team" if scope.is_team else "personal",
        "team_id": scope.team_id,
        "can_manage": (not scope.is_team) or role_can(role, Capability.MANAGE_SECRETS),
    }


def _team_secret_audit_fields(scope: RequestScope, *, surface: str = "browser") -> dict[str, str]:
    if not scope.is_team:
        return {}
    member = scope.member or {}
    return {
        "actor_member_id": str(member.get("id") or ""),
        "actor_role": str(member.get("role") or ""),
        "surface": surface,
    }


def _emit_scoped_secret_event(event: str, session_id: str, scope: RequestScope, **extra: Any) -> None:
    emit_secret_event(
        event,
        session_id,
        team_id=scope.team_id,
        **_team_secret_audit_fields(scope),
        **extra,
    )


def _require_team_secret_manager(scope: RequestScope, session_id: str, *, action: str, secret_name: str = ""):
    if not scope.is_team:
        return None
    role = str((scope.member or {}).get("role") or "")
    try:
        require_capability(
            role,
            Capability.MANAGE_SECRETS,
            team_id=scope.team_id,
            actor_member_id=str((scope.member or {}).get("id") or ""),
            action=action,
            route=str(request.path or ""),
            method=str(request.method or ""),
            surface="browser",
        )
    except TeamPermissionDenied:
        emit_secret_event(
            "SECRET_ACTION_REJECTED",
            session_id,
            name=secret_name,
            team_id=scope.team_id,
            action=action,
            capability=Capability.MANAGE_SECRETS.value,
            reason="team_forbidden",
            level=logging.WARNING,
            **_team_secret_audit_fields(scope),
        )
        return jsonify({"error": "team_forbidden", "message": "Your team role cannot manage shared secrets."}), 403
    return None


@secrets_bp.route("/session/secrets", methods=["GET"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_list():
    _session_id, scope, secret_scope_id, error_response = _active_secret_scope()
    if error_response:
        return error_response
    assert scope is not None
    try:
        return jsonify({"secrets": list_secret_metadata(secret_scope_id), **_secret_scope_payload(scope)})
    except (InvalidSecretName, SecretConsumerEnvConflict, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)


@secrets_bp.route("/session/secrets", methods=["POST"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_upsert():
    session_id, scope, secret_scope_id, error_response = _active_secret_scope()
    if error_response:
        return error_response
    assert scope is not None
    capability_response = _require_team_secret_manager(scope, session_id, action="secret_upsert")
    if capability_response:
        return capability_response
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    if "value" not in data:
        return jsonify({"error": "value_required"}), 400
    try:
        metadata, created = upsert_secret(
            secret_scope_id,
            str(data.get("name") or ""),
            str(data.get("value") or ""),
            data.get("consumer_envs"),
            audit_session_id=session_id,
            team_id=scope.team_id,
            audit_fields=route_audit_fields(session_id, request, scope),
        )
    except (InvalidSecretName, SecretConsumerEnvConflict, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)
    _emit_scoped_secret_event(
        "SECRET_CREATED" if created else "SECRET_UPDATED",
        session_id,
        scope,
        name=str(metadata["name"]),
        consumer_envs=metadata["consumer_envs"],
    )
    return jsonify({**metadata, **_secret_scope_payload(scope)}), 201 if created else 200


@secrets_bp.route("/session/secrets/<name>", methods=["DELETE"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_delete(name):
    session_id, scope, secret_scope_id, error_response = _active_secret_scope()
    if error_response:
        return error_response
    assert scope is not None
    audit_name = str(name or "").strip().upper()
    capability_response = _require_team_secret_manager(
        scope,
        session_id,
        action="secret_delete",
        secret_name=audit_name,
    )
    if capability_response:
        return capability_response
    try:
        removed = delete_secret(
            secret_scope_id,
            name,
            audit_session_id=session_id,
            team_id=scope.team_id,
            audit_fields=route_audit_fields(session_id, request, scope),
        )
    except (InvalidSecretName, SecretConsumerEnvConflict, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)
    if removed:
        _emit_scoped_secret_event("SECRET_DELETED", session_id, scope, name=audit_name)
    else:
        _emit_scoped_secret_event("SECRET_DELETE_NOOP", session_id, scope, name=audit_name)
    return jsonify({"removed": removed, **_secret_scope_payload(scope)})


@secrets_bp.route("/session/secrets/rotate", methods=["POST"])
@limiter.limit(_secrets_route_limit, key_func=get_session_id)
def session_secrets_rotate():
    session_id, scope, secret_scope_id, error_response = _active_secret_scope()
    if error_response:
        return error_response
    assert scope is not None
    capability_response = _require_team_secret_manager(scope, session_id, action="secret_rotate")
    if capability_response:
        return capability_response
    try:
        count = rewrap_session_secrets(
            secret_scope_id,
            audit_session_id=session_id,
            team_id=scope.team_id,
            audit_fields=route_audit_fields(session_id, request, scope),
        )
    except (InvalidSecretName, SecretConsumerEnvConflict, InvalidSecretValue, MasterKeyError, SecretDecryptError) as exc:
        return _secret_error(exc)
    _emit_scoped_secret_event("SECRET_ROTATED", session_id, scope, count=count)
    return jsonify({"rewrapped": count, **_secret_scope_payload(scope)})
