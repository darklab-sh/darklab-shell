# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""CIDR-first, browser-only instance inspection boundary."""

import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

from flask import current_app, g, jsonify, redirect, request

from .access_profile import active_config, active_profile, safe_next_path
from .operator_grants import has_grant
from .resolver import AuthenticatedContext

log = logging.getLogger("shell")


def is_operator_request():
    return (request.path == "/admin" or request.path.startswith("/admin/")
            or (request.path == "/auth/oidc/callback" and request.args.get("state", "").startswith("admin_")))


def network_profile_allowed():
    from core.helpers import get_client_ip, ip_is_in_cidrs
    return (ip_is_in_cidrs(get_client_ip(), active_config().get("diagnostics_allowed_cidrs", []))
            and active_profile() in {"token_required", "oidc_required", "mixed"})


def browser_eligible(context):
    if not isinstance(context, AuthenticatedContext) or context.authentication_method != "browser_cookie":
        return False
    if active_profile() == "oidc_required" and context.credential_type != "oidc":
        return False
    if active_profile() == "token_required" and context.credential_type != "portable":
        return False
    return has_grant(context.principal_id)


def navigation_eligible():
    if not network_profile_allowed():
        return False
    from core.helpers import get_authentication_result
    return browser_eligible(get_authentication_result().context)


def fresh(context, *, now=None):
    value = context.browser_session_authenticated_at
    if not value:
        return False
    try:
        authenticated = datetime.fromisoformat(value)
        age = ((now or datetime.now(timezone.utc)) - authenticated).total_seconds()
    except (ValueError, TypeError):
        return False
    return 0 <= age < int(active_config().get("admin_console_reauth_minutes", 30)) * 60


def private_response(response):
    if is_operator_request():
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Referrer-Policy"] = "same-origin"
        response.vary.add("Cookie")
    return response


def hidden_response(reason):
    request.environ["darklab_operator_denied"] = True
    log.warning("INSTANCE_OPERATOR_ACCESS_DENIED", extra={"reason": reason, "http_status": 404})
    return current_app.response_class(status=404)


def require_authentication(*, reauthenticate=False):
    destination = "/admin/reauth" if reauthenticate else "/auth/sign-in"
    path = safe_next_path(request.values.get("next"), fallback="/admin/") if request.path == "/admin/reauth" else "/admin/"
    destination += "?" + urlencode({"next": path})
    if request.path == "/admin/settings":
        return jsonify({"error": "reauthentication_required" if reauthenticate else "sign_in_required",
                        "destination": destination}), 401
    return redirect(destination)


def enforce_operator_access():
    if not is_operator_request():
        return None
    # This is deliberately before authentication resolution and grant queries.
    if not network_profile_allowed():
        return hidden_response("network_or_profile")
    if request.path == "/auth/oidc/callback":
        # The matched Lax state cookie binds a provider return to the source
        # session. Strict browser-session cookies need not survive that return.
        return None
    from core.helpers import get_authentication_result
    context = get_authentication_result().context
    if not isinstance(context, AuthenticatedContext) or context.authentication_method != "browser_cookie":
        return require_authentication()
    if not browser_eligible(context):
        return hidden_response("ineligible")
    g.operator_context = context
    if request.endpoint != "admin.reauthenticate" and not fresh(context):
        return require_authentication(reauthenticate=True)
    return None
