"""Shodan output helpers for output signal classification."""

from __future__ import annotations

import re

from core.output_entities import _is_private_or_reserved_ip, _is_public_ip

_SHODAN_DNS_RECORD_TYPES = {"A", "AAAA", "CNAME", "MX", "NS", "SOA", "TXT"}
_SHODAN_DNS_FINDING_TYPES = {"A", "AAAA", "CNAME", "MX", "NS", "SOA"}
_SHODAN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.I)
_SHODAN_HOST_IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_SHODAN_HOSTNAME_RE = re.compile(r"^Hostnames:\s+\S", re.I)
_SHODAN_PORT_RE = re.compile(r"^\s*\d+/(?:tcp|udp)(?:\s+\S.*)?$", re.I)
_SHODAN_HTTP_TITLE_RE = re.compile(r"^\s*\|--\s+HTTP title:\s+\S", re.I)
_SHODAN_HOST_SUMMARY_RE = re.compile(
    r"^(?:(?:City|Country|Organization|Updated|Number of open ports):\s+\S|Ports:\s*$)",
    re.I,
)
_SHODAN_WEAK_MAIL_POLICY_RE = re.compile(
    r"\bv=DMARC1\b[^;\n]*(?:;\s*)?p=none\b|"
    r"\bv=spf1\b.*(?:~all|\?all)\b",
    re.I,
)
_SHODAN_HTTP_WARNING_RE = re.compile(
    r"HTTP title:.*(?:\b5\d\d\b|Service Temporarily Unavailable|Index of /|Default Page)",
    re.I,
)

def _parse_shodan_dns_row(stripped: str) -> tuple[str, str, str] | None:
    parts = str(stripped or "").strip().split(None, 2)
    if len(parts) < 2:
        return None
    first = parts[0].upper()
    if first in _SHODAN_DNS_RECORD_TYPES:
        value = parts[1] if len(parts) == 2 else f"{parts[1]} {parts[2]}"
        return "", first, value
    if len(parts) >= 3 and parts[1].upper() in _SHODAN_DNS_RECORD_TYPES:
        return parts[0], parts[1].upper(), parts[2]
    return None


def _is_shodan_dns_text_row(stripped: str) -> bool:
    parsed = _parse_shodan_dns_row(stripped)
    return bool(parsed and parsed[1] == "TXT")


def _is_shodan_finding(stripped: str) -> bool:
    parsed = _parse_shodan_dns_row(stripped)
    if parsed:
        _, record_type, _ = parsed
        return record_type in _SHODAN_DNS_FINDING_TYPES
    return (
        (bool(_SHODAN_HOST_IP_RE.match(stripped)) and _is_public_ip(stripped))
        or bool(_SHODAN_HOSTNAME_RE.search(stripped))
        or bool(_SHODAN_PORT_RE.search(stripped))
        or bool(_SHODAN_HTTP_TITLE_RE.search(stripped))
    )


def _is_shodan_warning(stripped: str) -> bool:
    parsed = _parse_shodan_dns_row(stripped)
    if parsed:
        _, record_type, value = parsed
        if record_type in {"A", "AAAA"} and _is_private_or_reserved_ip(value.split()[0] if value else ""):
            return True
        if record_type == "TXT" and _SHODAN_WEAK_MAIL_POLICY_RE.search(value):
            return True
    return bool(_SHODAN_HTTP_WARNING_RE.search(stripped))


def _is_shodan_summary(stripped: str) -> bool:
    return bool(_SHODAN_HOST_SUMMARY_RE.search(stripped))

