# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""PAT-safe principal and current-credential API routes."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from services.api_v1.auth import current_api_session
from services.audit.context import request_audit_fields
from services.auth import lifecycle
from services.auth.contracts import IdentityStorageError
from services.auth.resolver import AuthenticatedContext


def _pat_context() -> AuthenticatedContext:
    session = current_api_session()
    return AuthenticatedContext(
        principal_id=session.principal_id,
        personal_workspace_id=session.owner_id,
        workspace_storage_key="",
        credential_id=session.credential_id,
        credential_type="pat",
        authentication_method="pat_bearer",
        credential_created_at=session.created_at or "",
        credential_last_used_at=session.last_seen_at,
        credential_expires_at=session.expires_at,
        capabilities=session.scopes,
    )


@api_routes.api_v1_bp.get("/principal")
@api_routes.require_api_auth
def api_current_principal():
    session = current_api_session()
    return jsonify({
        "principal": {
            "id": session.principal_id,
            "status": "active",
            "personal_workspace_id": session.owner_id,
        },
        "authentication": {
            "method": "pat_bearer",
            "credential_id": session.credential_id,
            "credential_type": "pat",
            "scopes": sorted(session.scopes),
        },
    })


@api_routes.api_v1_bp.get("/credentials")
@api_routes.require_api_auth
def api_current_credentials():
    context = _pat_context()
    item = next(
        credential
        for credential in lifecycle.list_safe_credentials(context)
        if credential.id == context.credential_id
    )
    return jsonify({"credentials": [item.to_safe_dict()]})


@api_routes.api_v1_bp.post("/credentials/current/revoke")
@api_routes.require_api_auth
def api_revoke_current_credential():
    context = _pat_context()
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return api_routes._api_json_error("invalid_body", "Request body must be a JSON object.", 400)
    try:
        metadata = lifecycle.revoke(
            context,
            context.credential_id,
            reason=str(body.get("reason") or "self-revoked"),
            request_fields=request_audit_fields(request),
        )
    except (IdentityStorageError, PermissionError) as exc:
        return api_routes._api_json_error("invalid_credential_request", str(exc), 400)
    return jsonify({"credential": metadata.to_safe_dict()})
