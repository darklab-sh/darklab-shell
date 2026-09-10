# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser principal and credential lifecycle routes."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

import core.process as process_state
from core.helpers import (
    AuthenticationRejected,
    get_authentication_result,
    get_client_ip,
    require_authenticated_context,
)
from services.audit.context import request_audit_fields
from services.auth import lifecycle
from services.auth.contracts import (
    CredentialNotFound,
    IdentityStorageError,
    LastCredentialLockout,
    PrincipalDisabled,
)
from services.auth.rate_limit import check_anonymous_issuance, check_failed_redemption
from services.auth.resolver import (
    AnonymousContext,
    AuthenticatedContext,
    public_lookup_id_from_headers,
    redeem_portable_credential,
)


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# This list is intentionally small and test-audited. No GET route may return a
# reusable secret.
SECRET_BEARING_ENDPOINTS = frozenset({
    "auth.create_principal",
    "auth.redeem",
    "auth.create_credential",
    "auth.rotate_credential",
})


def _payload() -> dict:
    value = request.get_json(silent=True)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise IdentityStorageError("request body must be a JSON object")
    return value


def _no_store(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


def _secret_response(issued, *, status: int = 201):
    return _no_store(jsonify({
        "credential": issued.metadata.to_safe_dict(),
        "secret": issued.secret,
    })), status


def _error(exc: BaseException):
    if isinstance(exc, LastCredentialLockout):
        status, code = 409, "last_credential_lockout"
    elif isinstance(exc, CredentialNotFound):
        status, code = 404, "credential_not_found"
    elif isinstance(exc, PrincipalDisabled):
        status, code = 403, "principal_disabled"
    elif isinstance(exc, PermissionError):
        status, code = 403, "credential_forbidden"
    else:
        status, code = 400, "invalid_credential_request"
    return jsonify({"error": code, "message": str(exc)}), status


def _request_fields() -> dict:
    return request_audit_fields(request)


@auth_bp.post("/principals")
def create_principal():
    result = get_authentication_result()
    if result.failed:
        raise AuthenticationRejected(result.error_code, result.message)
    if not isinstance(result.context, AnonymousContext):
        return jsonify({
            "error": "anonymous_identity_required",
            "message": "A validated anonymous identity is required for an upgrade.",
        }), 401
    limited = check_anonymous_issuance(
        get_client_ip(),
        redis_client=process_state.redis_client,
        enabled=bool(current_app.config.get("RATELIMIT_ENABLED", True)),
    )
    if not limited.allowed:
        return jsonify({
            "error": "credential_issuance_rate_limited",
            "retry_after": limited.retry_after,
        }), 429
    try:
        bundle = lifecycle.create_principal(
            anonymous_id=result.context.anonymous_id,
            credential_label=str(_payload().get("label") or ""),
            request_fields=_request_fields(),
        )
    except (IdentityStorageError, PermissionError) as exc:
        return _error(exc)
    response = jsonify({
        **bundle.to_safe_dict(),
        "secret": bundle.credential.secret,
    })
    return _no_store(response), 201


@auth_bp.post("/credentials/redeem")
def redeem():
    secret = str(_payload().get("secret") or "")
    result = redeem_portable_credential(secret)
    if result.failed or not isinstance(result.context, AuthenticatedContext):
        limited = check_failed_redemption(
            get_client_ip(),
            public_lookup_id_from_headers({"X-Darklab-Credential": secret}),
            redis_client=process_state.redis_client,
            enabled=bool(current_app.config.get("RATELIMIT_ENABLED", True)),
        )
        if limited.allowed:
            lifecycle.record_authentication_failure(result, request_fields=_request_fields())
        if not limited.allowed:
            return jsonify({"error": "credential_redemption_rate_limited", "retry_after": limited.retry_after}), 429
        return jsonify({"error": result.error_code or "invalid_credential", "message": result.message}), 401
    lifecycle.record_redemption(result.context, request_fields=_request_fields())
    return _no_store(jsonify({"authentication": _context_payload(result.context)}))


def _context_payload(context: AuthenticatedContext) -> dict:
    return {
        "principal_id": context.principal_id,
        "personal_workspace_id": context.personal_workspace_id,
        "credential_id": context.credential_id,
        "credential_type": context.credential_type,
        "authentication_method": context.authentication_method,
        "selected_team_id": context.selected_team_id or None,
        "role": context.role or None,
        "capabilities": sorted(context.capabilities),
    }


def _require_pat_scope(context: AuthenticatedContext, scope: str) -> None:
    if context.credential_type == "pat" and scope not in context.capabilities:
        raise PermissionError(f"PAT requires the {scope} scope")


@auth_bp.get("/principal")
def current_principal():
    try:
        context = require_authenticated_context()
        _require_pat_scope(context, "identity:read")
    except PermissionError as exc:
        return _error(exc)
    except AuthenticationRejected as exc:
        return jsonify({"error": exc.code, "message": exc.message}), 401
    return jsonify({
        "principal": {
            "id": context.principal_id,
            "status": "active",
            "personal_workspace_id": context.personal_workspace_id,
        },
        "authentication": _context_payload(context),
    })


@auth_bp.post("/local-access/clear")
def clear_local_access():
    """Ask the browser to clear local identity and credential storage."""
    response = current_app.response_class(status=204)
    response.headers["Clear-Site-Data"] = '"storage"'
    return _no_store(response)


@auth_bp.get("/credentials")
def credentials():
    try:
        context = require_authenticated_context()
        _require_pat_scope(context, "identity:read")
        if context.credential_type == "pat":
            items = [item for item in lifecycle.list_safe_credentials(context) if item.id == context.credential_id]
        else:
            items = lifecycle.list_safe_credentials(context)
        return jsonify({"credentials": [item.to_safe_dict() for item in items]})
    except (AuthenticationRejected, IdentityStorageError, PermissionError) as exc:
        if isinstance(exc, AuthenticationRejected):
            return jsonify({"error": exc.code, "message": exc.message}), 401
        return _error(exc)


@auth_bp.post("/credentials")
def create_credential():
    try:
        context = require_authenticated_context()
        data = _payload()
        issued = lifecycle.issue(
            context,
            credential_type=str(data.get("type") or "portable"),
            label=str(data.get("label") or ""),
            expires_at=data.get("expires_at"),
            scopes=data.get("scopes"),
            request_fields=_request_fields(),
        )
        return _secret_response(issued)
    except (AuthenticationRejected, IdentityStorageError, PermissionError) as exc:
        if isinstance(exc, AuthenticationRejected):
            return jsonify({"error": exc.code, "message": exc.message}), 401
        return _error(exc)


@auth_bp.patch("/credentials/<credential_id>")
def update_credential(credential_id: str):
    try:
        context = require_authenticated_context()
        data = _payload()
        allowed = set(data).intersection({"label", "expires_at"})
        if len(allowed) != 1 or set(data) != allowed:
            raise IdentityStorageError("supply exactly one of label or expires_at")
        if "label" in data:
            metadata = lifecycle.rename(
                context,
                credential_id,
                str(data.get("label") or ""),
                request_fields=_request_fields(),
            )
        else:
            metadata = lifecycle.change_expiry(
                context,
                credential_id,
                data.get("expires_at"),
                request_fields=_request_fields(),
            )
        return jsonify({"credential": metadata.to_safe_dict()})
    except (AuthenticationRejected, IdentityStorageError, PermissionError) as exc:
        if isinstance(exc, AuthenticationRejected):
            return jsonify({"error": exc.code, "message": exc.message}), 401
        return _error(exc)


@auth_bp.get("/credentials/<credential_id>/durable-work")
def credential_durable_work(credential_id: str):
    try:
        context = require_authenticated_context()
        _require_pat_scope(context, "identity:read")
        disposition = lifecycle.list_credential_durable_work(context, credential_id)
        return jsonify({"durable_work": disposition.to_safe_dict()})
    except (AuthenticationRejected, IdentityStorageError, PermissionError) as exc:
        if isinstance(exc, AuthenticationRejected):
            return jsonify({"error": exc.code, "message": exc.message}), 401
        return _error(exc)


@auth_bp.post("/credentials/<credential_id>/rotate")
def rotate_credential(credential_id: str):
    try:
        context = require_authenticated_context()
        data = _payload()
        issued = lifecycle.rotate(
            context,
            credential_id,
            label=data.get("label"),
            expires_at=data.get("expires_at"),
            request_fields=_request_fields(),
        )
        return _secret_response(issued)
    except (AuthenticationRejected, IdentityStorageError, PermissionError) as exc:
        if isinstance(exc, AuthenticationRejected):
            return jsonify({"error": exc.code, "message": exc.message}), 401
        return _error(exc)


@auth_bp.post("/credentials/<credential_id>/revoke")
def revoke_credential(credential_id: str):
    try:
        context = require_authenticated_context()
        data = _payload()
        result = lifecycle.revoke(
            context,
            credential_id,
            reason=str(data.get("reason") or ""),
            confirm_lockout=data.get("confirm_lockout") is True,
            pause_related_work=data.get("pause_related_work") is True,
            include_durable_work=True,
            request_fields=_request_fields(),
        )
        if isinstance(result, tuple):
            metadata, disposition = result
            durable_work = disposition.to_safe_dict()
        else:  # Compatibility for route-level test doubles.
            metadata = result
            durable_work = {"affected": [], "paused": [], "affected_count": 0, "paused_count": 0}
        return jsonify({"credential": metadata.to_safe_dict(), "durable_work": durable_work})
    except (AuthenticationRejected, IdentityStorageError, PermissionError) as exc:
        if isinstance(exc, AuthenticationRejected):
            return jsonify({"error": exc.code, "message": exc.message}), 401
        return _error(exc)
