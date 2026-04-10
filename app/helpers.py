"""
Shared per-request helpers used across blueprints.

Covers client-IP resolution (trusted-proxy aware) and session-ID extraction.
These are kept here so multiple blueprints can import them without creating
circular dependencies through app.py.
"""

import ipaddress
import logging
import re
from functools import lru_cache

from flask import g, request

from config import CFG

log = logging.getLogger("shell")

_IP_RE = re.compile(r"^((\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{2,39})$")
_UNTRUSTED_PROXY_LOGGED_FLAG = "_untrusted_proxy_logged"


@lru_cache(maxsize=8)
def _trusted_proxy_networks(cidr_values):
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
