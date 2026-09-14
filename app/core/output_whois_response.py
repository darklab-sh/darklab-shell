# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validate WHOIS targets and recognize their matching registration fields."""

from __future__ import annotations

from collections.abc import Sequence
import ipaddress
import re

from core.output_entities import _domain_candidate_has_allowed_suffix, _is_public_ip
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip


_DOMAIN_FIELD = re.compile(r"^(?:domain(?:\s+name)?\s*:|\[domain\s+name\])\s*(.*)$", re.I)
_NETWORK_FIELD = re.compile(r"^(?:inet6?num|netrange|cidr|route6?|(?:network:)?ip-network)\s*:\s*(.+)$", re.I)


def _canonical_target(target: str, extra_domain_suffixes: Sequence[str]) -> tuple[str, str]:
    try:
        canonical = canonical_ip(target)
    except CanonicalizationError:
        canonical = ""
    if canonical:
        return ("ip", canonical) if _is_public_ip(canonical) else ("", "")
    try:
        canonical = canonical_domain(target)
    except CanonicalizationError:
        return "", ""
    if not _domain_candidate_has_allowed_suffix(canonical, extra_domain_suffixes):
        return "", ""
    return "domain", canonical


class WhoisTargetResponse:
    """Match registration data, including a domain field continued on the next line."""

    def __init__(self, target: str, extra_domain_suffixes: Sequence[str]) -> None:
        self.entity_type, self.target = _canonical_target(target, extra_domain_suffixes)
        self.pending_domain = False

    def matches(self, text: str) -> bool:
        if self.entity_type == "domain":
            field = _DOMAIN_FIELD.fullmatch(text)
            if field:
                value = field.group(1).strip()
                self.pending_domain = not value
            elif self.pending_domain:
                value = text
                self.pending_domain = False
            else:
                return False
            try:
                return canonical_domain(value) == self.target
            except CanonicalizationError:
                return False
        field = _NETWORK_FIELD.fullmatch(text) if self.entity_type == "ip" else None
        if not field:
            return False
        target = ipaddress.ip_address(self.target)
        for value in field.group(1).split(","):
            try:
                if "-" in value:
                    start, end = (ipaddress.ip_address(part.strip()) for part in value.split("-", 1))
                    if start.version == target.version == end.version and int(start) <= int(target) <= int(end):
                        return True
                elif target in ipaddress.ip_network(value.strip(), strict=False):
                    return True
            except ValueError:
                continue
        return False
