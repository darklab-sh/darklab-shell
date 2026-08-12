# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded exact CPE correlation against stored NVD applicability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.assessments.cpe_applicability import (
    match_cpe_applicability,
    normalize_observed_cpe,
)
from services.assessments.version_correlation import correlate_version_observation


NVD_CPE_PAGE_DEFAULT = 25
NVD_CPE_PAGE_MAX = 50
_MAX_MATCHES_PER_CVE = 64


def correlate_stored_nvd_cpe_page(
    conn: Any,
    observation: dict[str, Any] | None,
    *,
    limit: int = NVD_CPE_PAGE_DEFAULT,
    offset: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Page inference matches for one exact CPE observation without side effects."""
    page_limit = _bounded_int(limit, default=NVD_CPE_PAGE_DEFAULT, maximum=NVD_CPE_PAGE_MAX)
    page_offset = _bounded_int(offset, default=0, maximum=1_000_000, minimum=0)
    payload = _empty_page(limit=page_limit, offset=page_offset)
    item = observation if isinstance(observation, dict) else {}
    observed = normalize_observed_cpe(item.get("cpe"), explicit_version=item.get("version"))
    if observed is None:
        return payload
    fields = observed["fields"]
    identity = tuple(str(fields[index]).casefold() for index in (2, 3, 4))
    rows = conn.execute(
        "WITH candidate_cves AS ("
        "SELECT cve_id FROM cve_advisory_cpe_matches "
        "WHERE source = 'nvd' AND cpe_part = ? AND cpe_vendor = ? AND cpe_product = ? "
        "GROUP BY cve_id ORDER BY cve_id LIMIT ? OFFSET ?"
        ") SELECT m.* FROM cve_advisory_cpe_matches m "
        "JOIN candidate_cves candidate ON candidate.cve_id = m.cve_id "
        "WHERE m.source = 'nvd' AND m.cpe_part = ? AND m.cpe_vendor = ? AND m.cpe_product = ? "
        "ORDER BY m.cve_id, m.match_criteria_id",
        (*identity, page_limit + 1, page_offset, *identity),
    ).fetchall()
    groups = _group_rows(rows)
    cve_ids = sorted(groups)
    selected_ids = cve_ids[:page_limit]
    has_more = len(cve_ids) > page_limit
    advisories = []
    rejected = 0
    metadata: dict[str, dict[str, str]] = {}
    current = now or datetime.now(timezone.utc)
    for cve_id in selected_ids:
        group = groups[cve_id]
        meta = _consistent_metadata(group, now=current)
        if meta is None or len(group) > _MAX_MATCHES_PER_CVE:
            rejected += 1
            continue
        metadata[cve_id] = meta
        advisories.append({
            "id": cve_id,
            "source": "nvd",
            "source_version": meta["source_version"],
            "cpe_matches": [_match_payload(row) for row in group],
        })
    matches = correlate_version_observation(item, advisories)
    for match in matches:
        cve_id = str(match["vulnerability_id"])
        meta = metadata[cve_id]
        rule = _matched_rule(observed, groups[cve_id], match)
        match.update({
            "advisory_origin": meta["origin"],
            "advisory_expires_at": meta["expires_at"],
            "advisory_source_state": meta["source_state"],
            "advisory_criteria": str(rule.get("criteria") or ""),
            "advisory_match_criteria_id": str(rule.get("match_criteria_id") or ""),
        })
    payload.update({
        "matches": matches,
        "candidate_cve_count": len(selected_ids),
        "rejected_candidate_count": rejected,
        "has_more": has_more,
        "next_offset": page_offset + page_limit if has_more else None,
    })
    return payload


def _group_rows(rows: Any) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        cve_id = str(item.get("cve_id") or "")
        if cve_id:
            grouped.setdefault(cve_id, []).append(item)
    return grouped


def _consistent_metadata(rows: list[dict[str, Any]], *, now: datetime) -> dict[str, str] | None:
    values = {
        (
            str(row.get("source_version") or ""),
            str(row.get("origin") or ""),
            str(row.get("expires_at") or ""),
        )
        for row in rows
    }
    if len(values) != 1:
        return None
    source_version, origin, expires_at = values.pop()
    if not source_version or origin not in {"local", "external"}:
        return None
    return {
        "source_version": source_version,
        "origin": origin,
        "expires_at": expires_at,
        "source_state": _source_state(expires_at, now=now),
    }


def _match_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "criteria": str(row.get("criteria") or ""),
        "match_criteria_id": str(row.get("match_criteria_id") or ""),
        "vulnerable": True,
        "applicability_complete": True,
        "negate": False,
        "version_start_including": str(row.get("version_start_including") or ""),
        "version_start_excluding": str(row.get("version_start_excluding") or ""),
        "version_end_including": str(row.get("version_end_including") or ""),
        "version_end_excluding": str(row.get("version_end_excluding") or ""),
        "all_versions": bool(row.get("all_versions")),
    }


def _matched_rule(
    observed: dict[str, Any],
    rows: list[dict[str, Any]],
    match: dict[str, Any],
) -> dict[str, Any]:
    for row in rows:
        payload = _match_payload(row)
        result = match_cpe_applicability(observed, [payload])
        if result and result["match_basis"] == match["match_basis"]:
            return payload
    return {}


def _source_state(expires_at: str, *, now: datetime) -> str:
    if not expires_at:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return "stale"
    if parsed.tzinfo is None:
        return "stale"
    current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return "stale" if parsed <= current else "current"


def _bounded_int(value: Any, *, default: int, maximum: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _empty_page(*, limit: int, offset: int) -> dict[str, Any]:
    return {
        "source": "nvd",
        "matches": [],
        "limit": limit,
        "offset": offset,
        "candidate_cve_count": 0,
        "rejected_candidate_count": 0,
        "has_more": False,
        "next_offset": None,
    }


__all__ = ["correlate_stored_nvd_cpe_page"]
