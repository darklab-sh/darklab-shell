# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Shared per-request helpers used across blueprints.

Covers client-IP resolution (trusted-proxy aware), session-ID extraction,
active-theme resolution, and the authoritative font manifest.
These are kept here so multiple blueprints can import them without creating
circular dependencies through app.py.
"""

import ipaddress
import logging
import re
from functools import lru_cache

from flask import g, has_request_context, request

from config import THEME_REGISTRY_MAP, resolve_effective_cfg

log = logging.getLogger("shell")

_IP_RE = re.compile(r"^((\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{2,39})$")
_UNTRUSTED_PROXY_LOGGED_FLAG = "_untrusted_proxy_logged"
GRACEFUL_TERMINATION_EXIT_CODE = -15
GRACEFUL_TERMINATION_EXIT_CODES = frozenset({GRACEFUL_TERMINATION_EXIT_CODE})
_AUTH_RESULT_KEY = "darklab_authentication_result"
LEGACY_SESSION_ADAPTER_REMOVAL_ITEM = 11


class AuthenticationRejected(RuntimeError):
    """Raised when a request supplied an identity that failed authentication."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class LegacyIdentityAdapterUnavailable(RuntimeError):
    """Raised until principal ownership replaces the v2 session owner seam."""


def _coerce_exit_code(exit_code):
    if exit_code is None:
        return None
    try:
        return int(exit_code)
    except (TypeError, ValueError):
        return None


def is_graceful_termination_exit_code(exit_code):
    """Return true for process exits that mean the run was externally stopped."""
    code = _coerce_exit_code(exit_code)
    return code in GRACEFUL_TERMINATION_EXIT_CODES


def is_failed_exit_code(exit_code):
    """Return true when an exit code should count as a command failure."""
    code = _coerce_exit_code(exit_code)
    return code is not None and code != 0 and code not in GRACEFUL_TERMINATION_EXIT_CODES


def is_valid_anonymous_session_id(session_id):
    """Return whether ``personal_workspace_id`` is a browser-generated anonymous UUID."""
    try:
        from services.auth.contracts import validate_anonymous_uuid  # noqa: PLC0415

        validate_anonymous_uuid(str(session_id or ""))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


@lru_cache(maxsize=8)
def _trusted_proxy_networks(cidr_values):
    # Trusted proxy CIDRs change rarely, so cache the parsed networks and reuse
    # them across requests instead of reparsing the same strings every time.
    networks = []
    for cidr in cidr_values:
        if not cidr:
            continue
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _peer_ip_is_trusted(peer_ip):
    if not peer_ip:
        return False
    try:
        ip_obj = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    trusted_networks = _trusted_proxy_networks(tuple(resolve_effective_cfg().get("trusted_proxy_cidrs", ())))
    return any(ip_obj in network for network in trusted_networks)


def _resolve_forwarded_client_ip(peer_ip, forwarded_for):
    # Walk the forwarded chain from right to left and return the first hop that
    # is not itself another trusted proxy.
    if not forwarded_for:
        return peer_ip
    trusted_networks = _trusted_proxy_networks(tuple(resolve_effective_cfg().get("trusted_proxy_cidrs", ())))
    forwarded_chain = [part.strip() for part in forwarded_for.split(",") if part.strip()]
    if not forwarded_chain:
        return peer_ip
    for candidate in reversed(forwarded_chain):
        if not _IP_RE.match(candidate):
            continue
        try:
            candidate_ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if any(candidate_ip in network for network in trusted_networks):
            continue
        return candidate
    return peer_ip


def _log_untrusted_proxy(peer_ip, forwarded_for):
    if getattr(g, _UNTRUSTED_PROXY_LOGGED_FLAG, False):
        return
    setattr(g, _UNTRUSTED_PROXY_LOGGED_FLAG, True)
    log.warning(
        "UNTRUSTED_PROXY",
        extra={
            "ip": peer_ip,
            "proxy_ip": peer_ip,
            "forwarded_for": forwarded_for,
            "path": request.path,
        },
    )


def ip_is_in_cidrs(ip_str, cidrs):
    """Return True if ip_str falls within any of the given CIDR strings."""
    if not ip_str or not cidrs:
        return False
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip_obj in network for network in _trusted_proxy_networks(tuple(cidrs)))


def get_client_ip():
    """Return the real client IP.

    Only honors X-Forwarded-For when the direct peer IP is in the configured
    trusted-proxy list; otherwise falls back to the direct connection IP.
    """
    # Keep all IP resolution rules in one place so logging hooks, rate limiting,
    # and route handlers agree on the same client identity.
    peer_ip = request.remote_addr or ""
    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if _peer_ip_is_trusted(peer_ip):
        return _resolve_forwarded_client_ip(peer_ip, forwarded_for)
    if forwarded_for:
        _log_untrusted_proxy(peer_ip, forwarded_for)
    return peer_ip


def get_authentication_result():
    """Return the request's cached, typed authentication result."""
    from services.auth.resolver import resolve_authentication  # noqa: PLC0415

    existing = getattr(g, _AUTH_RESULT_KEY, None)
    if existing is not None:
        return existing
    result = resolve_authentication(request.headers)
    setattr(g, _AUTH_RESULT_KEY, result)
    return result


def get_session_id():
    """Return the request's personal owner id through the transition adapter."""
    from services.auth.resolver import (  # noqa: PLC0415
        AnonymousContext,
        AuthenticatedContext,
        LegacySessionContext,
    )

    result = get_authentication_result()
    if result.failed:
        raise AuthenticationRejected(result.error_code, result.message)
    context = result.context
    if isinstance(context, LegacySessionContext):
        return context.session_id
    if isinstance(context, AnonymousContext):
        return context.anonymous_id
    if isinstance(context, AuthenticatedContext):
        return context.personal_workspace_id
    return ""


def require_authenticated_context():
    """Return an authenticated principal context or raise a typed rejection."""
    from services.auth.resolver import AuthenticatedContext  # noqa: PLC0415

    result = get_authentication_result()
    if result.failed:
        raise AuthenticationRejected(result.error_code, result.message)
    if not isinstance(result.context, AuthenticatedContext):
        raise AuthenticationRejected("credential_required", "An access credential is required.")
    return result.context


def get_log_session_id(session_id=None):
    """Return a log-safe session identifier.

    Anonymous UUID-style sessions are correlation IDs and can be logged as-is.
    ``tok_`` sessions are bearer credentials, so logs keep only the visible
    prefix needed for correlation and mask the secret suffix.
    """
    if session_id is None:
        try:
            from services.auth.resolver import (  # noqa: PLC0415
                AnonymousContext,
                AuthenticatedContext,
                LegacySessionContext,
            )

            context = get_authentication_result().context
            if isinstance(context, LegacySessionContext):
                value = context.session_id
            elif isinstance(context, AnonymousContext):
                value = context.anonymous_id
            elif isinstance(context, AuthenticatedContext):
                value = context.credential_id
            else:
                value = ""
        except (AuthenticationRejected, RuntimeError):
            value = ""
    else:
        value = str(session_id or "")
        # Callers that still use the historical ``session`` log field often
        # pass the personal workspace or principal identifier needed by the
        # storage layer.  When that identifier belongs to the authenticated
        # request, correlate by the safe credential lookup id instead of
        # emitting a durable ownership identifier.
        if value.startswith(("wsp_", "prn_")):
            try:
                from services.auth.resolver import AuthenticatedContext  # noqa: PLC0415

                context = get_authentication_result().context
                if isinstance(context, AuthenticatedContext) and value in {
                    context.personal_workspace_id,
                    context.principal_id,
                }:
                    value = context.credential_id
            except (AuthenticationRejected, RuntimeError):
                pass
    if value.startswith("tok_"):
        return f"{value[:8]}********"
    if value.startswith(("crd_", "pat_")):
        return f"{value[:12]}********"
    return value


# ── Font manifest ──────────────────────────────────────────────────────────────
# Single source of truth for vendored font files. Browser-facing CSS uses WOFF2
# while PDF export keeps TrueType files available for jsPDF.

FONT_FILES = [
    ("JetBrains Mono", 300, "JetBrainsMono-300.ttf"),
    ("JetBrains Mono", 400, "JetBrainsMono-400.ttf"),
    ("JetBrains Mono", 700, "JetBrainsMono-700.ttf"),
    ("Syne", 700, "Syne-700.ttf"),
    ("Syne", 800, "Syne-800.ttf"),
]

WEB_FONT_FILES = [
    ("JetBrains Mono", 300, "JetBrainsMono-300.woff2"),
    ("JetBrains Mono", 400, "JetBrainsMono-400.woff2"),
    ("JetBrains Mono", 700, "JetBrainsMono-700.woff2"),
    ("Syne", 700, "Syne-700.woff2"),
    ("Syne", 800, "Syne-800.woff2"),
]


# ── Theme resolution ───────────────────────────────────────────────────────────

def resolve_theme() -> tuple[str, str]:
    """Return ``(theme_name, source)`` for the current request.

    Resolution order: pref_theme_name cookie → legacy pref_theme cookie →
    default_theme config → hard-coded fallback.  ``source`` is one of
    ``"pref_theme_name"``, ``"pref_theme"``, ``"default_theme"``, or
    ``"fallback"``.  Safe to call outside a request context.
    """
    default = resolve_effective_cfg().get("default_theme", "darklab_obsidian.yaml")
    if not has_request_context():
        return default, "fallback"
    try:
        theme_name = request.cookies.get("pref_theme_name", "").strip()
        if theme_name and theme_name in THEME_REGISTRY_MAP:
            return theme_name, "pref_theme_name"
        legacy = request.cookies.get("pref_theme", "").strip()
        if legacy and legacy in THEME_REGISTRY_MAP:
            return legacy, "pref_theme"
        source = "default_theme" if default in THEME_REGISTRY_MAP else "fallback"
        return default, source
    except Exception:
        return default, "fallback"


def current_theme_name() -> str:
    """Return the active theme name for the current request.

    Delegates to :func:`resolve_theme`; use that directly when the resolution
    source is also needed (e.g. for debug logging).
    """
    return resolve_theme()[0]
