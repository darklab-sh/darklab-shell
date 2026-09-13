# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Request-wide policy for open and credential-restricted deployments."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from flask import current_app, jsonify, redirect, request, url_for

from services.api_v1.serialization import json_error

from .browser_sessions import (
    BROWSER_CSRF_COOKIE,
    BROWSER_SESSION_COOKIE,
    create_browser_session,
    verify_csrf_token,
)
from .resolver import AuthenticatedContext

OPEN = "open"
TOKEN_REQUIRED = "token_required"
OIDC_REQUIRED = "oidc_required"
MIXED = "mixed"
log = logging.getLogger("shell")

# This is the complete restricted-mode allowlist. It contains only the sign-in
# boundary and assets or probes that cannot read a workspace.
RESTRICTED_PUBLIC_ENDPOINTS = frozenset({
    "static",
    "assets.favicon",
    "assets.health",
    "assets.status",
    "assets.metrics",
    "assets.static_build_asset",
    "assets.vendor_ansi_up_js",
    "assets.vendor_jspdf_js",
    "assets.vendor_xterm_js",
    "assets.vendor_xterm_fit_js",
    "assets.vendor_xterm_css",
    "assets.vendor_fonts",
    "auth.sign_in",
    "auth.redeem",
    "auth.oidc_start",
    "auth.oidc_callback",
})
RESTRICTED_SHARE_ENDPOINT = "history.get_share"
RESTRICTED_SHARE_CREATE_ENDPOINT = "history.save_share"
PRIVILEGE_CHANGE_ENDPOINTS = frozenset({
    "teams.session_teams_create",
    "teams.session_teams_join",
    "teams.session_teams_members_update",
    "teams.session_teams_members_remove",
    "teams.session_teams_leave",
    "teams.session_teams_recovery_redeem",
})


def active_config() -> Mapping[str, Any]:
    return current_app.config.get("DARKLAB_CONFIG", {})


def active_profile() -> str:
    return str(active_config().get("access_profile") or OPEN)


def is_restricted() -> bool:
    return active_profile() in {TOKEN_REQUIRED, OIDC_REQUIRED, MIXED}


def public_shares_enabled() -> bool:
    return bool(active_config().get("restricted_public_shares_enabled", False))


def is_public_endpoint(endpoint: str | None = None) -> bool:
    selected = endpoint or request.endpoint or ""
    if selected in RESTRICTED_PUBLIC_ENDPOINTS:
        return True
    return selected == RESTRICTED_SHARE_ENDPOINT and public_shares_enabled()


def safe_next_path(value: object, *, fallback: str = "/") -> str:
    path = str(value or "").strip()
    if not path.startswith("/") or path.startswith("//") or "\r" in path or "\n" in path:
        return fallback
    return path[:2048]


def _unauthorized_response():
    if request.path.startswith("/api/v1/"):
        return jsonify(json_error("credential_required", "Sign in is required.")), 401
    return jsonify({"error": "credential_required", "message": "Sign in is required."}), 401


def enforce_restricted_access(authentication_result):
    """Run before route handlers so protected code cannot read scoped data."""
    if not is_restricted():
        return None
    endpoint = request.endpoint or ""
    if endpoint == RESTRICTED_SHARE_ENDPOINT and not public_shares_enabled():
        return current_app.response_class(status=404)
    if is_public_endpoint(endpoint):
        return None
    if isinstance(authentication_result.context, AuthenticatedContext):
        context = authentication_result.context
        if active_profile() == TOKEN_REQUIRED and context.credential_type == "oidc":
            if endpoint == "content.index" and request.method in {"GET", "HEAD"}:
                return redirect(url_for("auth.sign_in", next=safe_next_path(request.full_path.rstrip("?"))))
            return _unauthorized_response()
        if active_profile() == OIDC_REQUIRED and not (
            context.credential_type == "oidc"
            or (context.credential_type == "pat" and request.path.startswith("/api/v1/"))
        ):
            if endpoint == "content.index" and request.method in {"GET", "HEAD"}:
                return redirect(url_for("auth.sign_in", next=safe_next_path(request.full_path.rstrip("?"))))
            return _unauthorized_response()
        if endpoint == RESTRICTED_SHARE_CREATE_ENDPOINT and not public_shares_enabled():
            return jsonify({
                "error": "public_shares_disabled",
                "message": "Public share links are disabled for this deployment.",
            }), 403
        return None
    if endpoint == "content.index" and request.method in {"GET", "HEAD"}:
        return redirect(url_for("auth.sign_in", next=safe_next_path(request.full_path.rstrip("?"))))
    return _unauthorized_response()


def enforce_browser_csrf(authentication_result):
    if not is_restricted() or request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return None
    # The standalone form has its own short-lived, HttpOnly double-submit nonce
    # and cannot add the application JavaScript's CSRF request header.
    if request.endpoint == "auth.sign_in":
        return None
    context = authentication_result.context
    if not isinstance(context, AuthenticatedContext) or context.authentication_method != "browser_cookie":
        return None
    cookie_token = str(request.cookies.get(BROWSER_CSRF_COOKIE) or "")
    header_token = str(request.headers.get("X-Darklab-CSRF") or "")
    if (
        not cookie_token
        or not hmac_compare(cookie_token, header_token)
        or not verify_csrf_token(context.browser_session_id, cookie_token)
    ):
        message = "The request couldn't be verified. Refresh the page and try again."
        if request.path.startswith("/api/v1/"):
            return jsonify(json_error("csrf_validation_failed", message)), 403
        return jsonify({"error": "csrf_validation_failed", "message": message}), 403
    return None


def hmac_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def rotate_browser_session_after_privilege_change(response):
    """Rotate the current cookie after a successful Team privilege change."""
    if (
        not is_restricted()
        or response.status_code >= 400
        or request.endpoint not in PRIVILEGE_CHANGE_ENDPOINTS
    ):
        return response
    from core.helpers import get_authentication_result

    context = get_authentication_result().context
    if not isinstance(context, AuthenticatedContext) or context.authentication_method != "browser_cookie":
        return response
    absolute_seconds = int(active_config().get("browser_session_absolute_hours", 12)) * 3600
    issued = create_browser_session(
        principal_id=context.principal_id,
        credential_id=context.credential_id,
        oidc_identity_id=context.oidc_identity_id,
        absolute_seconds=absolute_seconds,
        replace_session_id=context.browser_session_id,
        authenticated_at=context.browser_session_authenticated_at,
    )
    response.set_cookie(
        BROWSER_SESSION_COOKIE,
        issued.cookie_value,
        max_age=absolute_seconds,
        secure=True,
        httponly=True,
        samesite="Strict",
        path="/",
    )
    response.set_cookie(
        BROWSER_CSRF_COOKIE,
        issued.csrf_token,
        max_age=absolute_seconds,
        secure=True,
        httponly=False,
        samesite="Strict",
        path="/",
    )
    log.info(
        "BROWSER_SESSION_ROTATED",
        extra={
            "principal_id": context.principal_id,
            "credential_id": context.credential_id,
            "reason": "privilege_change",
        },
    )
    return response
