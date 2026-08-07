# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded exact package correlation against stored OSV applicability."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any

from services.assessments.version_correlation import correlate_version_observation
from services.assessments.version_ranges import match_cached_semver_range, normalize_purl


OSV_PACKAGE_PAGE_DEFAULT = 25
OSV_PACKAGE_PAGE_MAX = 50
_MAX_RANGES_PER_ADVISORY = 64
_LOOKUP_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def correlate_stored_osv_package_page(
    conn: Any,
    observation: dict[str, Any] | None,
    *,
    limit: int = OSV_PACKAGE_PAGE_DEFAULT,
    offset: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Page exact package matches from cached OSV rows without side effects."""
    page_limit = _bounded_int(limit, default=OSV_PACKAGE_PAGE_DEFAULT, maximum=OSV_PACKAGE_PAGE_MAX)
    page_offset = _bounded_int(offset, default=0, maximum=1_000_000, minimum=0)
    payload = _empty_page(limit=page_limit, offset=page_offset)
    item = observation if isinstance(observation, dict) else {}
    normalized = normalize_purl(item.get("purl"), explicit_version=item.get("version"))
    if normalized is None:
        return payload
    package_purl, version = normalized
    rows = conn.execute(
        "WITH candidate_advisories AS ("
        "SELECT advisory_id FROM package_advisories "
        "WHERE source = 'osv' AND package_purl = ? "
        "ORDER BY normalized_vulnerability_id, advisory_id LIMIT ? OFFSET ?"
        ") SELECT advisory.*, ranges.range_index, ranges.range_type, ranges.events_json "
        "FROM package_advisories advisory "
        "JOIN candidate_advisories candidate ON candidate.advisory_id = advisory.advisory_id "
        "LEFT JOIN package_advisory_ranges ranges ON ranges.advisory_id = advisory.advisory_id "
        "WHERE advisory.source = 'osv' AND advisory.package_purl = ? "
        "ORDER BY advisory.normalized_vulnerability_id, advisory.advisory_id, ranges.range_index",
        (package_purl, page_limit + 1, page_offset, package_purl),
    ).fetchall()
    groups = _group_rows(rows)
    advisory_ids = list(groups)
    selected_ids = advisory_ids[:page_limit]
    current = now or datetime.now(timezone.utc)
    matches: list[dict[str, Any]] = []
    rejected = 0
    for advisory_id in selected_ids:
        advisory = _advisory_payload(
            groups[advisory_id], package_purl=package_purl, version=version, now=current,
        )
        if advisory is None:
            rejected += 1
            continue
        metadata = advisory.pop("_metadata")
        for match in correlate_version_observation(item, [advisory]):
            match.update(metadata)
            matches.append(match)
    has_more = len(advisory_ids) > page_limit
    payload.update({
        "matches": matches,
        "candidate_advisory_count": len(selected_ids),
        "rejected_candidate_count": rejected,
        "has_more": has_more,
        "next_offset": page_offset + page_limit if has_more else None,
    })
    return payload


def _group_rows(rows: Any) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        advisory_id = str(item.get("advisory_id") or "")
        if advisory_id:
            grouped.setdefault(advisory_id, []).append(item)
    return grouped


def _advisory_payload(
    rows: list[dict[str, Any]],
    *,
    package_purl: str,
    version: str,
    now: datetime,
) -> dict[str, Any] | None:
    if not rows or len(rows) > _MAX_RANGES_PER_ADVISORY:
        return None
    parent_fields = (
        "advisory_id", "source_advisory_id", "normalized_vulnerability_id", "package_purl",
        "schema_version", "source_version", "modified_at", "expires_at", "origin", "lookup_key_hash",
        "affected_versions_json",
    )
    parents = {tuple(str(row.get(field) or "") for field in parent_fields) for row in rows}
    if len(parents) != 1:
        return None
    parent = dict(zip(parent_fields, parents.pop(), strict=True))
    if (
        parent["package_purl"] != package_purl
        or not parent["advisory_id"]
        or not parent["source_advisory_id"]
        or not parent["normalized_vulnerability_id"]
        or not parent["schema_version"]
        or not parent["source_version"]
        or parent["origin"] not in {"local", "external"}
        or (parent["origin"] == "external" and not _LOOKUP_HASH_RE.fullmatch(parent["lookup_key_hash"]))
        or (parent["origin"] == "local" and parent["lookup_key_hash"])
    ):
        return None
    versions = _affected_versions(parent["affected_versions_json"])
    ranges = _ranges(rows)
    if versions is None or ranges is None or not (versions or ranges):
        return None
    return {
        "id": parent["normalized_vulnerability_id"],
        "source": "osv",
        "source_version": parent["source_version"],
        "package_purl": package_purl,
        "affected_versions": versions,
        "affected_range": f"=={version}",
        "ranges": ranges,
        "_metadata": {
            "advisory_id": parent["advisory_id"],
            "advisory_source_id": parent["source_advisory_id"],
            "advisory_schema_version": parent["schema_version"],
            "advisory_origin": parent["origin"],
            "advisory_modified_at": parent["modified_at"],
            "advisory_expires_at": parent["expires_at"],
            "advisory_source_state": _source_state(parent["expires_at"], now=now),
        },
    }


def _affected_versions(value: str) -> list[str] | None:
    if len(value) > 524288:
        return None
    try:
        rows = json.loads(value)
    except (TypeError, ValueError):
        return None
    if not isinstance(rows, list) or len(rows) > 4096:
        return None
    versions = [str(row or "").strip() for row in rows]
    if any(not row or len(row) > 128 or any(char.isspace() or ord(char) < 32 for char in row) for row in versions):
        return None
    return versions if len(set(versions)) == len(versions) else None


def _ranges(rows: list[dict[str, Any]]) -> list[dict[str, str]] | None:
    ranges: list[dict[str, str]] = []
    indexes: set[int] = set()
    for row in rows:
        if row.get("range_index") is None:
            continue
        try:
            index = int(row["range_index"])
        except (TypeError, ValueError):
            return None
        events_json = str(row.get("events_json") or "")
        candidate = {"range_type": str(row.get("range_type") or ""), "events_json": events_json}
        if index < 0 or index in indexes or len(events_json) > 4096 or not _valid_range(candidate):
            return None
        indexes.add(index)
        ranges.append(candidate)
    return ranges


def _valid_range(candidate: dict[str, str]) -> bool:
    try:
        events = json.loads(candidate["events_json"])
        first = next(iter(events[0].values()))
    except (AttributeError, IndexError, TypeError, ValueError):
        return False
    probe = "0.0.0" if first == "0" else str(first)
    return match_cached_semver_range(probe, [candidate]) is not None


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
        "source": "osv", "matches": [], "limit": limit, "offset": offset,
        "candidate_advisory_count": 0, "rejected_candidate_count": 0,
        "has_more": False, "next_offset": None,
    }


__all__ = ["correlate_stored_osv_package_page"]
