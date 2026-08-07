# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Owner-scoped joins for separately captured DNSx takeover evidence."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from typing import Any

from services.assessments.dns_takeover_identity import (
    DNSX_TAKEOVER_PARSER_VERSION,
    dnsx_observation_id,
)
from services.assessments.dns_takeover_observations import DNSX_MAX_CNAME_CHAIN
from services.intel.canonical import CanonicalizationError, canonical_domain


DNSX_TARGET_CORRELATION_VERSION = "dnsx-target-correlation-v1"
DNSX_TARGET_MAX_SKEW_SECONDS, DNSX_TARGET_MAX_ALLOWED_RUNS = 86_400, 256


def correlate_dnsx_target_observation(
    source: dict[str, Any] | None,
    target: dict[str, Any] | None,
    *,
    allowed_source_run_ids: Collection[str],
    max_skew_seconds: int = DNSX_TARGET_MAX_SKEW_SECONDS,
) -> dict[str, Any] | None:
    """Join an exact ultimate CNAME target result without reading or writing state."""
    allowed = _allowed_runs(allowed_source_run_ids)
    source_row = _evidence(source)
    target_row = _evidence(target)
    if not allowed or not source_row or not target_row:
        return None
    if source_row["source_run_id"] not in allowed or target_row["source_run_id"] not in allowed:
        return None
    if source_row.get("truncated") or target_row.get("truncated"):
        return None
    cname_chain = _domains(source_row.get("cname_chain"))
    if not cname_chain or cname_chain[-1] != target_row["hostname"]:
        return None
    target_chain = _domains(target_row.get("cname_chain"))
    combined_chain = [*cname_chain, *target_chain]
    if len(combined_chain) > DNSX_MAX_CNAME_CHAIN:
        return None
    try:
        skew_limit = min(DNSX_TARGET_MAX_SKEW_SECONDS, max(0, int(max_skew_seconds)))
    except (TypeError, ValueError):
        return None
    if abs((target_row["_time"] - source_row["_time"]).total_seconds()) > skew_limit:
        return None
    target_state = (
        str(target_row.get("resolution_state") or "unknown")
        if target_row.get("scope_decision") == "in_scope"
        else "uncertain"
    )
    return {
        "hostname": source_row["hostname"],
        "cname_chain": combined_chain,
        "provider_fingerprint": (
            source_row.get("provider_fingerprint") or target_row.get("provider_fingerprint") or {}
        ),
        "scope_decision": source_row.get("scope_decision", "unknown"),
        "wildcard_filter": source_row.get("wildcard_filter", "unknown"),
        "target_resolution_state": target_state,
        "source_observation": _reference(source_row),
        "target_observation": _reference(target_row),
        "correlation_version": DNSX_TARGET_CORRELATION_VERSION,
    }


def _evidence(value: dict[str, Any] | None) -> dict[str, Any] | None:
    item = value if isinstance(value, dict) else {}
    observation_id = _text(item.get("observation_id"), 64)
    run_id = _text(item.get("source_run_id"), 128)
    hostname = _domain(item.get("hostname"))
    parsed = _timestamp(item.get("observed_at"))
    cname_chain = _domains(item.get("cname_chain"))
    resolution = _text(item.get("resolution_state"), 32).casefold()
    status_code = _text(item.get("status_code"), 32).upper()
    scope = _text(item.get("scope_decision"), 32).casefold()
    wildcard = _text(item.get("wildcard_filter"), 32).casefold()
    if (
        item.get("parser_version") != DNSX_TAKEOVER_PARSER_VERSION
        or not run_id
        or not hostname
        or parsed is None
        or observation_id != dnsx_observation_id(
            run_id, hostname, _text(item.get("observed_at"), 64), cname_chain,
            status_code, resolution, scope, wildcard,
        )
    ):
        return None
    if resolution not in {"negative", "resolved", "uncertain", "unknown"}:
        return None
    provider = item.get("provider_fingerprint")
    return {
        "observation_id": observation_id,
        "source_run_id": run_id,
        "hostname": hostname,
        "cname_chain": cname_chain,
        "resolution_state": resolution,
        "status_code": status_code,
        "scope_decision": scope if scope in {"in_scope", "out_of_scope", "unknown"} else "unknown",
        "wildcard_filter": wildcard if wildcard in {"auto", "manual", "not_checked", "unknown"} else "unknown",
        "provider_fingerprint": _provider(provider),
        "truncated": bool(item.get("truncated")),
        "observed_at": _text(item.get("observed_at"), 64),
        "parser_version": DNSX_TAKEOVER_PARSER_VERSION,
        "_time": parsed,
    }


def _reference(item: dict[str, Any]) -> dict[str, str]:
    return {
        "observation_id": str(item["observation_id"]),
        "source_run_id": str(item["source_run_id"]),
        "hostname": str(item["hostname"]),
        "resolution_state": str(item["resolution_state"]),
        "status_code": str(item["status_code"]),
        "scope_decision": str(item["scope_decision"]),
        "observed_at": str(item["observed_at"]),
        "parser_version": str(item["parser_version"]),
    }


def _allowed_runs(values: Collection[str]) -> set[str]:
    if (
        isinstance(values, (str, bytes))
        or not isinstance(values, Collection)
        or not 0 < len(values) <= DNSX_TARGET_MAX_ALLOWED_RUNS
    ):
        return set()
    rows = {_text(value, 128) for value in values}
    rows.discard("")
    return rows


def _domains(value: Any) -> list[str]:
    values = value if isinstance(value, list) else []
    rows: list[str] = []
    for candidate in values[:DNSX_MAX_CNAME_CHAIN]:
        normalized = _domain(candidate)
        if normalized and normalized not in rows:
            rows.append(normalized)
    return rows


def _domain(value: Any) -> str:
    try:
        return canonical_domain(_text(value, 512).rstrip("."))
    except CanonicalizationError:
        return ""


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(_text(value, 64).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _provider(value: Any) -> dict[str, str]:
    item = value if isinstance(value, dict) else {}
    name = _text(item.get("name"), 128).casefold()
    kind = _text(item.get("type"), 64).casefold()
    return {key: value for key, value in (("name", name), ("type", kind)) if value}


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text if len(text) <= limit and not any(ord(char) < 32 for char in raw) else ""


__all__ = [
    "DNSX_TARGET_CORRELATION_VERSION",
    "DNSX_TARGET_MAX_SKEW_SECONDS",
    "correlate_dnsx_target_observation",
]
