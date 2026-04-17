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

from config import CFG, THEME_REGISTRY_MAP

log = logging.getLogger("shell")

_IP_RE = re.compile(r"^((\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{2,39})$")
_UNTRUSTED_PROXY_LOGGED_FLAG = "_untrusted_proxy_logged"


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
    trusted_networks = _trusted_proxy_networks(tuple(CFG.get("trusted_proxy_cidrs", ())))
    return any(ip_obj in network for network in trusted_networks)


def _resolve_forwarded_client_ip(peer_ip, forwarded_for):
    # Walk the forwarded chain from right to left and return the first hop that
    # is not itself another trusted proxy.
    if not forwarded_for:
        return peer_ip
    trusted_networks = _trusted_proxy_networks(tuple(CFG.get("trusted_proxy_cidrs", ())))
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


def get_session_id():
    """Extract the anonymous session ID from the X-Session-ID request header."""
    return request.headers.get("X-Session-ID", "").strip()


# ── Font manifest ──────────────────────────────────────────────────────────────
# Single source of truth for vendored font files.  assets.py derives its route
# allowlist from this list; permalinks.py uses it to generate @font-face CSS.
# Adding or removing a font here automatically propagates to both surfaces.

FONT_FILES = [
    ("JetBrains Mono", 300, "JetBrainsMono-300.ttf"),
    ("JetBrains Mono", 400, "JetBrainsMono-400.ttf"),
    ("JetBrains Mono", 700, "JetBrainsMono-700.ttf"),
    ("Syne", 700, "Syne-700.ttf"),
    ("Syne", 800, "Syne-800.ttf"),
]


# ── Theme resolution ───────────────────────────────────────────────────────────

def resolve_theme() -> tuple[str, str]:
    """Return ``(theme_name, source)`` for the current request.

    Resolution order: pref_theme_name cookie → legacy pref_theme cookie →
    default_theme config → hard-coded fallback.  ``source`` is one of
    ``"pref_theme_name"``, ``"pref_theme"``, ``"default_theme"``, or
    ``"fallback"``.  Safe to call outside a request context.
    """
    default = CFG.get("default_theme", "darklab_obsidian.yaml")
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
