# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only operator console and verified session step-up."""

import logging
from types import SimpleNamespace
from urllib.parse import urlencode

from config import get_theme_entry
from core.helpers import current_theme_name, get_authentication_result
from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request
from services.audit.context import request_audit_fields
from services.auth import lifecycle, oidc, operator_access, operator_reauth
from services.auth.access_profile import active_config
from services.auth.browser_sessions import BROWSER_CSRF_COOKIE, BROWSER_SESSION_COOKIE
from services.auth.contracts import IdentityStorageError
from services.auth.oidc_diagnostics import log_oidc_failure
from services.auth.resolver import AuthenticatedContext, redeem_portable_credential

from .auth import (
    _clear_oidc_state_cookie,
    _redemption_limit,
    _set_browser_session_cookies,
    _set_oidc_state_cookie,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
log = logging.getLogger("shell")


@admin_bp.route("/reauth", methods=["GET", "POST"])
def reauthenticate():
    context = g.operator_context
    next_path = operator_access.return_path(request.values.get("next"))
    error = "Verification couldn't be completed. Please try again." if request.args.get("error") else ""
    if request.args.get("error") == "provider_freshness":
        error = (
            "Your identity provider didn't confirm a fresh sign-in. Operator access requires a signed auth_time "
            "from a new authentication. Ask your operator to check the provider configuration before trying again."
        )
    status = 200
    limited = None
    provider = context.credential_type == "oidc"
    if request.method == "POST":
        if provider:
            try:
                url, state = oidc.start_flow(
                    active_config(), purpose="admin_reauth", principal_id=context.principal_id,
                    browser_session_id=context.browser_session_id, next_path=next_path,
                )
                response = redirect(url)
                _set_oidc_state_cookie(response, state)
                return response
            except IdentityStorageError as exc:
                failure = exc if isinstance(exc, oidc.OIDCError) else oidc.OIDCUnavailable("provider unavailable")
                log_oidc_failure(failure, purpose="admin_reauth")
                error = "The identity provider is unavailable. Please try again."
                status = 503
        else:
            secret = str(request.form.get("credential") or "")
            limited = _redemption_limit(secret)
            result = redeem_portable_credential(secret) if limited.allowed else None
            if (result and not result.failed and isinstance(result.context, AuthenticatedContext)
                    and result.context.principal_id == context.principal_id):
                try:
                    # Recheck eligibility after credential verification, before
                    # the transactional session/grant validation and rotation.
                    if not operator_access.profile_allowed():
                        return operator_access.hidden_response("profile")
                    issued = operator_reauth.rotate_verified_session(
                        context, active_config(), credential_context=result.context,
                        request_fields=request_audit_fields(request),
                    )
                except IdentityStorageError:
                    log.warning("INSTANCE_OPERATOR_REAUTH_FAILED", extra={"reason": "source_unavailable"})
                    return redirect("/admin/reauth?" + urlencode({"next": next_path, "error": "1"}))
                response = redirect(next_path)
                _set_browser_session_cookies(response, issued)
                return response
            if result is not None:
                limited = _redemption_limit(secret, failed=True)
                if result.failed and limited.allowed:
                    lifecycle.record_authentication_failure(result, request_fields=request_audit_fields(request))
            log.warning("INSTANCE_OPERATOR_REAUTH_FAILED", extra={
                "reason": "credential_rejected" if limited.allowed else "rate_limited",
            })
            error = "Verification failed. Use an active credential for this account."
            status = 400
            if not limited.allowed:
                error, status = "Too many attempts. Wait a moment and try again.", 429
    return render_reauthentication_form(error=error, status=status, limited=limited)


def render_reauthentication_form(*, error="", status=200, limited=None, csrf_rejected=False):
    """Render verification errors without replaying a rejected form submission."""
    provider = g.operator_context.credential_type == "oidc"
    next_path = operator_access.return_path(request.values.get("next"))
    theme = get_theme_entry(current_theme_name(), fallback=str(active_config().get("default_theme")))
    response = current_app.make_response(render_template(
        "restricted_sign_in.html", app_name=active_config()["app_name"], current_theme=theme,
        current_theme_css=theme["vars"], next_path=next_path, error=error,
        reauthentication=True, credential_sign_in_enabled=not provider, oidc_sign_in_enabled=provider,
        csrf_token=request.cookies.get(BROWSER_CSRF_COOKIE, ""),
        csrf_rejected=csrf_rejected,
    ))
    response.status_code = status
    if status == 429 and limited is not None:
        response.headers["Retry-After"] = str(limited.retry_after)
    return response


def complete_provider_reauthentication(flow, proof):
    if not operator_access.profile_allowed():
        return operator_access.hidden_response("profile")
    # Strict session cookies may be absent on a cross-site callback. The
    # consumed flow and matched HttpOnly state cookie identify the source;
    # an explicitly present different/invalid session must never override it.
    if request.cookies.get(BROWSER_SESSION_COOKIE):
        current = get_authentication_result().context
        if (not isinstance(current, AuthenticatedContext) or current.principal_id != flow.principal_id
                or current.browser_session_id != flow.browser_session_id):
            raise operator_reauth.OperatorReauthenticationError("verification is unavailable")
    source = SimpleNamespace(principal_id=flow.principal_id, browser_session_id=flow.browser_session_id,
                             authentication_method="browser_cookie")
    issued = operator_reauth.rotate_verified_session(
        source, active_config(), provider_proof=proof, request_fields=request_audit_fields(request),
    )
    response = redirect(operator_access.return_path(flow.next_path))
    _set_browser_session_cookies(response, issued)
    _clear_oidc_state_cookie(response)
    return response


@admin_bp.get("/")
def index():
    theme = get_theme_entry(current_theme_name(), fallback=str(active_config()["default_theme"]))
    return render_template("admin.html", app_name=active_config()["app_name"],
                           current_theme=theme, current_theme_css=theme["vars"])


@admin_bp.get("/settings")
def settings():
    from services.operator_console import loaded_settings
    return jsonify(loaded_settings(g.operator_context, request_audit_fields(request)))


@admin_bp.get("/access")
def access_status():
    """The shared request boundary verifies access without reading settings or creating view events."""
    return "", 204
