# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded DNSx evidence for later dangling-record review."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.assessments.dns_takeover_identity import (
    DNSX_TAKEOVER_PARSER_VERSION,
    dnsx_observation_id,
)
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip
from services.assessments.dns_takeover_context import (
    dnsx_command_scope_domain,
    dnsx_scope_decision,
    dnsx_wildcard_filter,
)


DNSX_MAX_CNAME_CHAIN = 16
DNSX_MAX_ADDRESSES = 32
DNSX_MAX_RESOLVERS = 8
_TRANSIENT_CODES = frozenset({"SERVFAIL", "REFUSED", "FORMERR", "NOTIMP"})


def dnsx_json_metadata(
    record: dict[str, Any] | None,
    *,
    command: str,
    source_run_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """Return safe takeover evidence from one structured DNSx row."""
    observation = normalize_dnsx_takeover_observation(
        record,
        command=command,
        source_run_id=source_run_id,
    )
    return {"takeover_observations": [observation]} if observation else {}


def normalize_dnsx_takeover_observation(
    record: dict[str, Any] | None,
    *,
    command: str,
    source_run_id: str,
) -> dict[str, Any] | None:
    """Normalize DNSx JSON without treating a CNAME as proof of takeover."""
    item = record if isinstance(record, dict) else {}
    run_id = _text(source_run_id, 128)
    hostname = _domain(item.get("host"))
    observed_at = _timestamp(item.get("timestamp"))
    if not run_id or not hostname or not observed_at:
        return None
    cnames, cname_truncated = _domains(item.get("cname"), DNSX_MAX_CNAME_CHAIN)
    addresses, address_truncated = _addresses(item, DNSX_MAX_ADDRESSES)
    resolvers, resolver_truncated = _resolvers(item.get("resolver"))
    status_code = _text(item.get("status_code"), 32).upper()
    scope_root = dnsx_command_scope_domain(command)
    provider_name = _text(item.get("cdn-name"), 128).casefold()
    provider_type = _text(item.get("cdn-type"), 64).casefold()
    resolution_state = _resolution_state(status_code, addresses, cnames)
    wildcard_filter = dnsx_wildcard_filter(command)
    scope_decision = dnsx_scope_decision(hostname, scope_root)
    return {
        "observation_id": dnsx_observation_id(
            run_id, hostname, observed_at, cnames, status_code,
            resolution_state, scope_decision, wildcard_filter,
        ),
        "hostname": hostname,
        "cname_chain": cnames,
        "addresses": addresses,
        "status_code": status_code,
        "resolution_state": resolution_state,
        "target_resolution_state": "not_checked",
        "provider_fingerprint": {
            "name": provider_name,
            "type": provider_type,
        } if provider_name or provider_type else {},
        "resolvers": resolvers,
        "wildcard_filter": wildcard_filter,
        "scope_root": scope_root,
        "scope_decision": scope_decision,
        "source_run_id": run_id,
        "observed_at": observed_at,
        "parser_version": DNSX_TAKEOVER_PARSER_VERSION,
        "truncated": cname_truncated or address_truncated or resolver_truncated,
    }


def _domains(value: Any, limit: int) -> tuple[list[str], bool]:
    values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    rows: list[str] = []
    for candidate in values[:limit]:
        normalized = _domain(candidate)
        if normalized and normalized not in rows:
            rows.append(normalized)
    return rows, len(values) > limit


def _addresses(item: dict[str, Any], limit: int) -> tuple[list[str], bool]:
    values: list[Any] = []
    for key in ("a", "aaaa"):
        row = item.get(key)
        values.extend(row if isinstance(row, list) else [row] if isinstance(row, str) else [])
    rows: list[str] = []
    for candidate in values[:limit]:
        try:
            normalized = canonical_ip(_text(candidate, 128))
        except CanonicalizationError:
            continue
        if normalized not in rows:
            rows.append(normalized)
    return rows, len(values) > limit


def _resolvers(value: Any) -> tuple[list[str], bool]:
    values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    rows: list[str] = []
    for candidate in values[:DNSX_MAX_RESOLVERS]:
        resolver = _text(candidate, 256)
        if resolver and "@" not in resolver and resolver not in rows:
            rows.append(resolver)
    return rows, len(values) > DNSX_MAX_RESOLVERS


def _domain(value: Any) -> str:
    try:
        return canonical_domain(_text(value, 512).rstrip("."))
    except CanonicalizationError:
        return ""


def _resolution_state(status_code: str, addresses: list[str], cnames: list[str]) -> str:
    if status_code == "NXDOMAIN":
        return "negative"
    if status_code in _TRANSIENT_CODES:
        return "uncertain"
    if status_code == "NOERROR" and (addresses or cnames):
        return "resolved"
    return "unknown"


def _timestamp(value: Any) -> str:
    text = _text(value, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return text if parsed.tzinfo is not None else ""


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text if text and len(text) <= limit and not any(ord(char) < 32 for char in raw) else ""


__all__ = [
    "DNSX_MAX_CNAME_CHAIN",
    "DNSX_TAKEOVER_PARSER_VERSION",
    "dnsx_observation_id",
    "dnsx_json_metadata",
    "normalize_dnsx_takeover_observation",
]
