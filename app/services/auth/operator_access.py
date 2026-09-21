# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser-only, principal-bound policy for every operator page."""

import logging
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit

from flask import current_app, g, jsonify, redirect, request

from .access_profile import active_config, active_profile, safe_next_path
from .operator_grants import has_grant
from .observability import _request_value, log_operator_access_denied
from .resolver import AuthenticatedContext, AuthenticationState, resolve_authentication

log = logging.getLogger("shell")


def is_operator_request():
    return (request.path == "/admin" or request.path.startswith("/admin/")
            or request.path == "/diag" or request.path.startswith("/diag/")
            or request.path == "/audit" or request.path.startswith("/audit/")
            or (request.path == "/auth/oidc/callback" and request.args.get("state", "").startswith("admin_")))


def profile_allowed():
    return active_profile() in {"token_required", "oidc_required", "mixed"}


def browser_eligible(context):
    if (not profile_allowed() or not isinstance(context, AuthenticatedContext)
            or context.authentication_method != "browser_cookie"):
        return False
    if active_profile() == "oidc_required" and context.credential_type != "oidc":
        return False
    if active_profile() == "token_required" and context.credential_type != "portable":
        return False
    return has_grant(context.principal_id)


def navigation_eligible():
    if not profile_allowed():
        return False
    from core.helpers import AuthenticationRejected, get_authentication_result
    try:
        return browser_eligible(get_authentication_result().context)
    except AuthenticationRejected:
        raise
    except Exception:
        return False


def fresh(context, *, now=None):
    value = (context.browser_session_provider_authenticated_at if context.credential_type == "oidc"
             else context.browser_session_authenticated_at)
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
    log_operator_access_denied(reason)
    return current_app.response_class(status=404)


def unavailable_response():
    request.environ["darklab_operator_denied"] = True
    return jsonify({"error": "operator_access_unavailable"}), 503


def _log_unavailable(exc, *, stage):
    log.error("INSTANCE_OPERATOR_ACCESS_UNAVAILABLE", extra={
        **log_context(), "reason": _request_value(type(exc).__name__, 80),
        "stage": stage, "http_status": 503,
        "endpoint": _request_value(request.endpoint, 160),
    })


def return_path(value):
    """Return to an operator document, never replay a data request or probe."""
    parsed = urlsplit(safe_next_path(value, fallback="/admin/"))
    if parsed.path in {"/admin", "/admin/", "/admin/settings", "/admin/reauth"}:
        query = urlencode([(key, item[:256]) for key, item in parse_qsl(parsed.query[:4096])
                           if key in {"view", "search", "group", "source", "warnings"}][:20])
        return "/admin/" + ("?" + query if query else "")
    if parsed.path == "/audit" or parsed.path.startswith("/audit/"):
        path = "/audit"
    elif parsed.path == "/diag" or parsed.path.startswith("/diag/"):
        path = "/diag"
    else:
        return "/admin/"
    keys = {"event_type", "actor", "actor_member_id", "actor_session_hash", "owner_session_hash",
            "session_id", "team_id", "project_id", "target_type", "target_id", "correlation_id",
            "date_from", "date_to", "limit", "offset"} if path == "/audit" else {"tz_offset"}
    query = urlencode([(key, item[:256]) for key, item in parse_qsl(parsed.query[:4096]) if key in keys][:20])
    return path + ("?" + query if query else "")


def data_request():
    return (request.path in {"/admin/settings", "/admin/access", "/diag/classifier-inspector",
                             "/diag/classifier-drift", "/diag/ai-test"}
            or request.args.get("format") == "json"
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.accept_mimetypes.best == "application/json")


def require_authentication(*, reauthenticate=False):
    destination = "/admin/reauth" if reauthenticate else "/auth/sign-in"
    path = return_path(request.values.get("next") if request.path in {"/admin/reauth", "/admin/access"} else request.full_path)
    destination += "?" + urlencode({"next": path})
    if data_request():
        return jsonify({"error": "reauthentication_required" if reauthenticate else "sign_in_required",
                        "destination": destination}), 401
    return redirect(destination)


def enforce_operator_access():
    if not is_operator_request():
        return None
    if not profile_allowed():
        return hidden_response("profile")
    if request.path == "/auth/oidc/callback":
        # The matched Lax state cookie binds a provider return to the source
        # session. Strict browser-session cookies need not survive that return.
        return None
    from core.helpers import AuthenticationRejected, get_authentication_result, record_failed_authentication
    try:
        authentication = get_authentication_result()
        record_failed_authentication(authentication)
        eligible = browser_eligible(authentication.context)
    except AuthenticationRejected:
        raise
    except Exception as exc:
        _log_unavailable(exc, stage="initial_check")
        return unavailable_response()
    if authentication.failed and authentication.state != AuthenticationState.EXPIRED_CREDENTIAL:
        return hidden_response("ineligible")
    context = authentication.context
    if authentication.state in {AuthenticationState.NO_CREDENTIAL, AuthenticationState.EXPIRED_CREDENTIAL}:
        return require_authentication()
    if not eligible:
        return hidden_response("ineligible")
    g.operator_context = context
    if request.endpoint != "admin.reauthenticate" and not fresh(context):
        return require_authentication(reauthenticate=True)
    return None


class OperatorAccessLost(RuntimeError):
    """A protected operation can no longer emit data or launch a probe."""


class OperatorAccessUnavailable(RuntimeError):
    """Live operator authority could not be checked because a dependency failed."""


def recheck_access():
    """Re-resolve live authority at export and probe boundaries without the request cache."""
    try:
        if not profile_allowed():
            raise OperatorAccessLost("operator access unavailable")
        authentication = resolve_authentication(
            request.headers, cookies=request.cookies,
            browser_session_idle_seconds=int(active_config().get("browser_session_idle_minutes", 30)) * 60,
        )
        if authentication.failed or not browser_eligible(authentication.context) or not fresh(authentication.context):
            raise OperatorAccessLost("operator access unavailable")
    except OperatorAccessLost:
        raise
    except Exception as exc:
        _log_unavailable(exc, stage="live_check")
        raise OperatorAccessUnavailable("operator access unavailable") from None


def log_context():
    from core.helpers import get_client_ip
    context = getattr(g, "operator_context", None)
    return {"principal_id": getattr(context, "principal_id", ""),
            "credential_id": getattr(context, "credential_id", ""),
            "ip": get_client_ip(), "request_id": str(request.environ.get("darklab_request_id") or "")}
