# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Canonical entity keys shared by intel providers and future Atlas storage."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit


CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.I)
HEX_HASH_RE = re.compile(r"^[0-9a-f]+$", re.I)
MAX_CANONICAL_VALUE_BYTES = 2048
_AMBIGUOUS_PATH_ESCAPE_RE = re.compile(r"%(?:25)+(?:2e|2f|5c)|%(?:2f|5c)", re.I)
_INVALID_PERCENT_ESCAPE_RE = re.compile(r"%(?![0-9a-f]{2})", re.I)
PORT_RE = re.compile(r"^(?P<port>\d{1,5})(?:/(?P<proto>[a-z][a-z0-9-]*))?$", re.I)
BRACKETED_HOST_PORT_RE = re.compile(
    r"^\[(?P<host>[^\]]+)]:(?P<port>\d{1,5})(?:/(?P<proto>[a-z][a-z0-9-]*))?$",
    re.I,
)
UNBRACKETED_HOST_PORT_RE = re.compile(
    r"^(?P<host>[^:\s]+):(?P<port>\d{1,5})(?:/(?P<proto>[a-z][a-z0-9-]*))?$",
    re.I,
)


class CanonicalizationError(ValueError):
    """Raised when an entity cannot be converted into a stable key."""


def canonical_ip(value: str) -> str:
    try:
        return ipaddress.ip_address(str(value or "").strip()).compressed.lower()
    except ValueError as exc:
        raise CanonicalizationError("invalid IP address") from exc


def canonical_domain(value: str) -> str:
    domain = str(value or "").strip().rstrip(".").lower()
    if not domain or any(ch.isspace() for ch in domain):
        raise CanonicalizationError("invalid domain")
    try:
        return domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise CanonicalizationError("invalid domain") from exc


def detect_hash_algorithm(value: str) -> str:
    token = str(value or "").strip().lower()
    if not HEX_HASH_RE.fullmatch(token):
        raise CanonicalizationError("hash must be hex")
    if len(token) == 32:
        return "md5"
    if len(token) == 40:
        return "sha1"
    if len(token) == 64:
        return "sha256"
    raise CanonicalizationError("hash must be MD5, SHA1, or SHA256")


def canonical_hash(value: str, algorithm: str | None = None) -> str:
    token = str(value or "").strip().lower()
    if not HEX_HASH_RE.fullmatch(token):
        raise CanonicalizationError("hash must be hex")
    algo = str(algorithm or detect_hash_algorithm(token)).strip().lower()
    expected_lengths = {"md5": 32, "sha1": 40, "sha256": 64}
    if expected_lengths.get(algo) != len(token):
        raise CanonicalizationError("hash length does not match algorithm")
    return f"{algo}:{token}"


def canonical_cve(value: str) -> str:
    token = str(value or "").strip().upper()
    if not CVE_RE.fullmatch(token):
        raise CanonicalizationError("invalid CVE id")
    return token


def _remove_dot_segments(path: str) -> str:
    """Apply the RFC 3986 remove-dot-segments algorithm to one decoded path."""
    pending = path
    rendered = ""
    while pending:
        if pending.startswith("../"):
            pending = pending[3:]
        elif pending.startswith("./"):
            pending = pending[2:]
        elif pending.startswith("/./"):
            pending = pending[2:]
        elif pending == "/.":
            pending = "/"
        elif pending.startswith("/../"):
            pending = pending[3:]
            rendered = rendered.rsplit("/", 1)[0]
        elif pending == "/..":
            pending = "/"
            rendered = rendered.rsplit("/", 1)[0]
        elif pending in {".", ".."}:
            pending = ""
        else:
            separator = pending.find("/", 1 if pending.startswith("/") else 0)
            if separator < 0:
                rendered += pending
                pending = ""
            else:
                rendered += pending[:separator]
                pending = pending[separator:]
    return rendered


def canonical_url_path(value: str, *, reject_dot_segments: bool = False) -> str:
    """Return one unambiguous, RFC 3986-normalized URL path."""
    raw = str(value or "")
    if (
        "\\" in raw
        or _INVALID_PERCENT_ESCAPE_RE.search(raw)
        or _AMBIGUOUS_PATH_ESCAPE_RE.search(raw)
    ):
        raise CanonicalizationError("URL path contains an ambiguous escape")
    try:
        decoded = unquote(raw, errors="strict")
    except UnicodeDecodeError as exc:
        raise CanonicalizationError("URL path contains invalid UTF-8") from exc
    normalized = _remove_dot_segments(decoded)
    if reject_dot_segments and normalized != decoded:
        raise CanonicalizationError("URL path contains dot segments")
    return quote(normalized, safe="/:@")


def canonical_url(value: str) -> str:
    raw = str(value or "").strip()
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise CanonicalizationError("invalid URL")
    scheme = parts.scheme.lower()
    try:
        parsed_host_ip = ipaddress.ip_address(str(parts.hostname or "").strip())
    except ValueError:
        host = canonical_domain(parts.hostname or "")
    else:
        host = parsed_host_ip.compressed.lower()
        if parsed_host_ip.version == 6:
            host = f"[{host}]"
    try:
        parsed_port = parts.port
    except ValueError as exc:
        raise CanonicalizationError("invalid URL") from exc
    is_default_port = (scheme == "http" and parsed_port == 80) or (scheme == "https" and parsed_port == 443)
    port = f":{parsed_port}" if parsed_port and not is_default_port else ""
    netloc = host + port
    path = canonical_url_path(parts.path or "")
    if path == "/" and not parts.query:
        path = ""
    query = quote(unquote(parts.query), safe="=&;:@/?")
    canonical = urlunsplit((scheme, netloc, path, query, ""))
    if len(canonical.encode("utf-8")) > MAX_CANONICAL_VALUE_BYTES:
        raise CanonicalizationError("canonical value is too long")
    return canonical


def _canonical_port_host(value: str) -> tuple[str, str]:
    try:
        return "ip", canonical_ip(value)
    except CanonicalizationError:
        return "domain", canonical_domain(value)


def _normalize_port_parts(port: object, proto: object = None) -> tuple[str, str]:
    try:
        port_number = int(str(port or "").strip())
    except (TypeError, ValueError) as exc:
        raise CanonicalizationError("invalid port") from exc
    if port_number < 1 or port_number > 65535:
        raise CanonicalizationError("port out of range")
    normalized_proto = str(proto or "tcp").strip().lower()
    if normalized_proto not in {"tcp", "udp"}:
        raise CanonicalizationError("invalid port protocol")
    return str(port_number), normalized_proto


def parse_canonical_port(value: str) -> tuple[str, str, str, str]:
    """Return ``(host_type, canonical_host, port, proto)`` for a port entity."""
    token = str(value or "").strip()
    match = BRACKETED_HOST_PORT_RE.fullmatch(token)
    if match:
        host_type, host = _canonical_port_host(match.group("host"))
        port, proto = _normalize_port_parts(match.group("port"), match.group("proto"))
        return host_type, host, port, proto

    match = UNBRACKETED_HOST_PORT_RE.fullmatch(token)
    if match:
        raw_host = match.group("host")
        if ":" in raw_host:
            raise CanonicalizationError("IPv6 port hosts must be bracketed")
        host_type, host = _canonical_port_host(raw_host)
        port, proto = _normalize_port_parts(match.group("port"), match.group("proto"))
        return host_type, host, port, proto

    raise CanonicalizationError("invalid port entity")


def canonical_port(value: str) -> str:
    host_type, host, port, proto = parse_canonical_port(value)
    if host_type == "ip":
        try:
            parsed = ipaddress.ip_address(host)
        except ValueError as exc:
            raise CanonicalizationError("invalid port host") from exc
        host_part = f"[{host}]" if parsed.version == 6 else host
    else:
        host_part = host
    canonical = f"{host_part}:{port}/{proto}"
    if len(canonical.encode("utf-8")) > MAX_CANONICAL_VALUE_BYTES:
        raise CanonicalizationError("canonical value is too long")
    return canonical


def canonical_entity(entity_type: str, value: str, *, algorithm: str | None = None) -> str:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type == "ip":
        return canonical_ip(value)
    if normalized_type in {"domain", "host"}:
        return canonical_domain(value)
    if normalized_type == "hash":
        return canonical_hash(value, algorithm=algorithm)
    if normalized_type == "cve":
        return canonical_cve(value)
    if normalized_type == "url":
        return canonical_url(value)
    if normalized_type == "port":
        return canonical_port(value)
    raise CanonicalizationError(f"unsupported entity type: {entity_type}")


def entity_signature(entity_type: str, canonical_value: str) -> str:
    raw = f"{str(entity_type or '').lower()}\x1f{canonical_value}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()
