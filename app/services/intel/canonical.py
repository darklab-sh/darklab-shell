"""Canonical entity keys shared by intel providers and future Atlas storage."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit


CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.I)
HEX_HASH_RE = re.compile(r"^[0-9a-f]+$", re.I)
MAX_CANONICAL_VALUE_BYTES = 2048


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


def canonical_url(value: str) -> str:
    raw = str(value or "").strip()
    parts = urlsplit(raw)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise CanonicalizationError("invalid URL")
    scheme = parts.scheme.lower()
    host = canonical_domain(parts.hostname or "")
    try:
        parsed_port = parts.port
    except ValueError as exc:
        raise CanonicalizationError("invalid URL") from exc
    is_default_port = (scheme == "http" and parsed_port == 80) or (scheme == "https" and parsed_port == 443)
    port = f":{parsed_port}" if parsed_port and not is_default_port else ""
    netloc = host + port
    path = quote(unquote(parts.path or ""), safe="/:@")
    if path == "/" and not parts.query:
        path = ""
    elif not parts.query and path.endswith("/"):
        path = path.rstrip("/")
    query = quote(unquote(parts.query), safe="=&;:@/?")
    canonical = urlunsplit((scheme, netloc, path, query, ""))
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
    raise CanonicalizationError(f"unsupported entity type: {entity_type}")


def entity_signature(entity_type: str, canonical_value: str) -> str:
    raw = f"{str(entity_type or '').lower()}\x1f{canonical_value}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()
