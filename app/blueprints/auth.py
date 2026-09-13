# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser principal and credential lifecycle routes."""

from __future__ import annotations

import base64
import hmac
import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

import core.process as process_state
from config import get_theme_entry
from core.helpers import (
    AuthenticationRejected,
    current_theme_name,
    get_authentication_result,
    get_client_ip,
    require_authenticated_context,
)
from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
)
from services.audit.context import request_audit_fields
from services.auth import lifecycle
from services.auth.access_profile import active_config, active_profile, is_restricted, safe_next_path
from services.auth.browser_sessions import (
    BROWSER_CSRF_COOKIE,
    BROWSER_SESSION_COOKIE,
    create_browser_session,
    revoke_browser_session,
    revoke_principal_browser_sessions,
)
from services.auth.contracts import (
    CredentialNotFound,
    IdentityStorageError,
    LastCredentialLockout,
    PrincipalDisabled,
)
from services.auth.rate_limit import check_anonymous_issuance, check_failed_redemption
from services.auth import oidc
from services.auth.resolver import (
    AnonymousContext,
    AuthenticatedContext,
    public_lookup_id_from_headers,
    redeem_portable_credential,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
log = logging.getLogger("shell")

# This list is intentionally small and test-audited. No GET route may return a
# reusable secret.
SECRET_BEARING_ENDPOINTS = frozenset({
    "auth.create_principal",
    "auth.redeem",
    "auth.create_credential",
    "auth.rotate_credential",
})
_SIGN_IN_NONCE_COOKIE = "darklab_sign_in_nonce"
_SIGN_IN_NONCE_MAX_AGE = 600


def _oidc_sign_in_enabled() -> bool:
    return active_profile() in {"oidc_required", "mixed"} and oidc.configured(active_config())


def _credential_sign_in_enabled() -> bool:
    return active_profile() in {"token_required", "mixed"}


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


def _session_cookie_seconds() -> int:
    return int(active_config().get("browser_session_absolute_hours", 12)) * 3600


def _set_browser_session_cookies(response, issued) -> None:
    response.set_cookie(
        BROWSER_SESSION_COOKIE,
        issued.cookie_value,
        max_age=_session_cookie_seconds(),
        secure=True,
        httponly=True,
        samesite="Strict",
        path="/",
    )
    response.set_cookie(
        BROWSER_CSRF_COOKIE,
        issued.csrf_token,
        max_age=_session_cookie_seconds(),
        secure=True,
        httponly=False,
        samesite="Strict",
        path="/",
    )


def _clear_browser_session_cookies(response) -> None:
    for name, httponly in ((BROWSER_SESSION_COOKIE, True), (BROWSER_CSRF_COOKIE, False)):
        response.delete_cookie(name, secure=True, httponly=httponly, samesite="Strict", path="/")


def _issue_browser_session(
    context: AuthenticatedContext,
    *,
    replace_session_id: str = "",
) -> object:
    return create_browser_session(
        principal_id=context.principal_id,
        credential_id=context.credential_id,
        oidc_identity_id=context.oidc_identity_id,
        absolute_seconds=_session_cookie_seconds(),
        replace_session_id=replace_session_id or context.browser_session_id,
    )


def _new_sign_in_nonce() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def _valid_sign_in_nonce(form_value: str) -> bool:
    cookie_value = str(request.cookies.get(_SIGN_IN_NONCE_COOKIE) or "")
    return bool(cookie_value) and hmac.compare_digest(cookie_value, str(form_value or ""))


@auth_bp.route("/sign-in", methods=["GET", "POST"])
def sign_in():
    if not is_restricted():
        return redirect("/")
    next_path = safe_next_path(request.values.get("next"))
    error = "Provider sign-in couldn't be completed. Please try again." if request.args.get("oidc_error") else ""
    if request.method == "POST":
        if not _credential_sign_in_enabled():
            return current_app.response_class(status=404)
        if not _valid_sign_in_nonce(str(request.form.get("sign_in_nonce") or "")):
            error = "The sign-in page expired. Reload it and try again."
        else:
            secret = str(request.form.get("credential") or "")
            result = redeem_portable_credential(secret)
            if not result.failed and isinstance(result.context, AuthenticatedContext):
                lifecycle.record_redemption(result.context, request_fields=_request_fields())
                request_context = get_authentication_result().context
                replace_id = (
                    request_context.browser_session_id
                    if isinstance(request_context, AuthenticatedContext) else ""
                )
                issued = _issue_browser_session(result.context, replace_session_id=replace_id)
                log.info(
                    "BROWSER_SESSION_CREATED",
                    extra={
                        "principal_id": result.context.principal_id,
                        "credential_id": result.context.credential_id,
                        "source": "sign_in_form",
                    },
                )
                response = _no_store(redirect(next_path))
                _set_browser_session_cookies(response, issued)
                response.delete_cookie(
                    _SIGN_IN_NONCE_COOKIE,
                    secure=True,
                    httponly=True,
                    samesite="Strict",
                    path="/auth/sign-in",
                )
                return response
            limited = check_failed_redemption(
                get_client_ip(),
                public_lookup_id_from_headers({"X-Darklab-Credential": secret}),
                redis_client=process_state.redis_client,
                enabled=bool(current_app.config.get("RATELIMIT_ENABLED", True)),
            )
            if not limited.allowed:
                error = "Too many sign-in attempts. Wait a moment and try again."
            else:
                lifecycle.record_authentication_failure(result, request_fields=_request_fields())
                error = "That access credential isn't valid."
    nonce = _new_sign_in_nonce()
    current_theme = get_theme_entry(
        current_theme_name(),
        fallback=str(active_config().get("default_theme") or "darklab_obsidian.yaml"),
    )
    response = _no_store(current_app.make_response(render_template(
        "restricted_sign_in.html",
        app_name=active_config().get("app_name", "darklab_shell"),
        current_theme=current_theme,
        current_theme_css=current_theme["vars"],
        next_path=next_path,
        sign_in_nonce=nonce,
        error=error,
        credential_sign_in_enabled=_credential_sign_in_enabled(),
        oidc_sign_in_enabled=_oidc_sign_in_enabled(),
    )))
    response.set_cookie(
        _SIGN_IN_NONCE_COOKIE,
        nonce,
        max_age=_SIGN_IN_NONCE_MAX_AGE,
        secure=True,
        httponly=True,
        samesite="Strict",
        path="/auth/sign-in",
    )
    return response


def _set_oidc_state_cookie(response, state: str) -> None:
    response.set_cookie(
        oidc.OIDC_STATE_COOKIE, state, max_age=oidc.FLOW_SECONDS,
        secure=True, httponly=True, samesite="Lax", path="/auth/oidc/callback",
    )


def _clear_oidc_state_cookie(response) -> None:
    response.delete_cookie(
        oidc.OIDC_STATE_COOKIE, secure=True, httponly=True,
        samesite="Lax", path="/auth/oidc/callback",
    )


def _oidc_error_response(exc: BaseException):
    log.warning("OIDC_AUTH_FAILED", extra={"reason": type(exc).__name__, "stage": request.endpoint or ""})
    response = _no_store(redirect("/auth/sign-in?oidc_error=1"))
    _clear_oidc_state_cookie(response)
    return response


@auth_bp.get("/oidc/start")
def oidc_start():
    if not _oidc_sign_in_enabled():
        return current_app.response_class(status=404)
    try:
        request_context = get_authentication_result().context
        url, state = oidc.start_flow(
            active_config(), purpose="sign_in",
            browser_session_id=(
                request_context.browser_session_id
                if isinstance(request_context, AuthenticatedContext) else ""
            ),
            next_path=safe_next_path(request.args.get("next")),
        )
    except IdentityStorageError as exc:
        return _oidc_error_response(exc)
    response = _no_store(redirect(url))
    _set_oidc_state_cookie(response, state)
    return response


@auth_bp.get("/oidc/callback")
def oidc_callback():
    if not _oidc_sign_in_enabled() and not (is_restricted() and oidc.configured(active_config())):
        return current_app.response_class(status=404)
    expected = urlsplit(str(active_config().get("oidc_redirect_uri") or ""))
    if request.host.lower() != expected.netloc.lower() or request.path != expected.path:
        return _oidc_error_response(oidc.OIDCError("The callback origin did not match the configured redirect."))
    try:
        flow = oidc.consume_flow(
            str(request.args.get("state") or ""),
            str(request.cookies.get(oidc.OIDC_STATE_COOKIE) or ""),
        )
        if request.args.get("error"):
            raise oidc.OIDCError("The provider declined the sign-in request.")
        issuer, subject = oidc.exchange_code(active_config(), flow, str(request.args.get("code") or ""))
        identity = oidc.complete_identity(active_config(), flow, issuer, subject)
        credential_id = ""
        oidc_identity_id = identity.id
        authenticated_at: str | None = None
        if flow.purpose == "link":
            credential_id, authenticated_at = oidc.linked_credential_source(flow)
            oidc_identity_id = ""
        issued = create_browser_session(
            principal_id=identity.principal_id, absolute_seconds=_session_cookie_seconds(),
            replace_session_id=flow.browser_session_id, credential_id=credential_id,
            oidc_identity_id=oidc_identity_id, authenticated_at=authenticated_at,
        )
        if flow.purpose == "sign_in" and flow.browser_session_id:
            revoke_browser_session(flow.browser_session_id, reason="OIDC sign-in rotation")
    except IdentityStorageError as exc:
        return _oidc_error_response(exc)
    log.info("OIDC_BROWSER_SESSION_CREATED", extra={"principal_id": identity.principal_id, "purpose": flow.purpose})
    response = _no_store(redirect(safe_next_path(flow.next_path)))
    _set_browser_session_cookies(response, issued)
    _clear_oidc_state_cookie(response)
    return response


def _recent_credential_session(context: AuthenticatedContext) -> bool:
    return context.credential_type == "portable" and _recent_browser_session(context)


def _recent_browser_session(context: AuthenticatedContext) -> bool:
    if context.authentication_method != "browser_cookie":
        return False
    authenticated = context.browser_session_authenticated_at
    if not authenticated:
        return False
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(authenticated)).total_seconds()
    return 0 <= age <= oidc.RECENT_AUTH_SECONDS


@auth_bp.post("/oidc/link")
def oidc_link():
    if not is_restricted() or not oidc.configured(active_config()):
        return current_app.response_class(status=404)
    context = require_authenticated_context()
    if not _recent_credential_session(context):
        return jsonify({
            "error": "recent_credential_required",
            "message": "Sign in again with your credential before linking.",
        }), 403
    try:
        url, state = oidc.start_flow(
            active_config(), purpose="link", principal_id=context.principal_id,
            browser_session_id=context.browser_session_id,
        )
    except oidc.OIDCError as exc:
        log.warning("OIDC_LINK_START_FAILED", extra={"reason": type(exc).__name__})
        return jsonify({"error": "oidc_unavailable", "message": "The identity provider is unavailable."}), 503
    response = _no_store(jsonify({"authorization_url": url}))
    _set_oidc_state_cookie(response, state)
    return response


@auth_bp.get("/oidc/identity")
def oidc_identity():
    if not is_restricted() or not oidc.configured(active_config()):
        return current_app.response_class(status=404)
    context = require_authenticated_context()
    linked = oidc.find_identity(context.principal_id, str(active_config()["oidc_issuer"]))
    return _no_store(jsonify({"linked": linked is not None, "issuer": active_config()["oidc_issuer"]}))


@auth_bp.post("/oidc/unlink")
def oidc_unlink():
    if not is_restricted() or not oidc.configured(active_config()):
        return current_app.response_class(status=404)
    context = require_authenticated_context()
    if not _recent_credential_session(context):
        return jsonify({
            "error": "recent_credential_required",
            "message": "Sign in again with your credential before unlinking.",
        }), 403
    try:
        changed = oidc.unlink_identity(context.principal_id, str(active_config()["oidc_issuer"]))
    except oidc.OIDCError as exc:
        return jsonify({"error": "oidc_unlink_blocked", "message": str(exc)}), 409
    log.info("OIDC_IDENTITY_UNLINKED", extra={"principal_id": context.principal_id, "changed": changed})
    response = _no_store(jsonify({"unlinked": changed, "sessions_revoked": changed}))
    if changed:
        _clear_browser_session_cookies(response)
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
    if is_restricted():
        return jsonify({
            "error": "anonymous_issuance_disabled",
            "message": "Anonymous credential issuance is disabled in this access profile.",
        }), 403
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
    if active_profile() == "oidc_required":
        return jsonify({"error": "credential_sign_in_disabled", "message": "Use provider sign-in."}), 403
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
    response = _no_store(jsonify({"authentication": _context_payload(result.context)}))
    if is_restricted():
        request_context = get_authentication_result().context
        replace_id = (
            request_context.browser_session_id
            if isinstance(request_context, AuthenticatedContext) else ""
        )
        issued = _issue_browser_session(result.context, replace_session_id=replace_id)
        _set_browser_session_cookies(response, issued)
        log.info(
            "BROWSER_SESSION_CREATED",
            extra={
                "principal_id": result.context.principal_id,
                "credential_id": result.context.credential_id,
                "source": "credential_redemption",
            },
        )
    return response


def _context_payload(context: AuthenticatedContext) -> dict:
    return {
        "principal_id": context.principal_id,
        "personal_workspace_id": context.personal_workspace_id,
        "credential_id": context.credential_id,
        "credential_type": context.credential_type,
        "authentication_method": context.authentication_method,
        "browser_session": context.authentication_method == "browser_cookie",
        "browser_session_expires_at": context.browser_session_absolute_expires_at,
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


@auth_bp.post("/logout")
def logout():
    context = require_authenticated_context()
    if context.browser_session_id:
        revoke_browser_session(context.browser_session_id, reason="logout")
        log.info(
            "BROWSER_SESSION_REVOKED",
            extra={
                "principal_id": context.principal_id,
                "credential_id": context.credential_id,
                "reason": "logout",
            },
        )
    response = current_app.response_class(status=204)
    _clear_browser_session_cookies(response)
    return _no_store(response)


@auth_bp.post("/sessions/revoke-all")
def revoke_all_sessions():
    context = require_authenticated_context()
    if active_profile() in {"oidc_required", "mixed"} and not _recent_browser_session(context):
        return jsonify({
            "error": "recent_authentication_required",
            "message": "Sign in again before revoking every browser session.",
        }), 403
    count = revoke_principal_browser_sessions(context.principal_id)
    log.info(
        "BROWSER_SESSIONS_REVOKED",
        extra={
            "principal_id": context.principal_id,
            "credential_id": context.credential_id,
            "count": count,
            "reason": "revoke_all",
        },
    )
    response = _no_store(jsonify({"revoked_sessions": count}))
    _clear_browser_session_cookies(response)
    return response


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
