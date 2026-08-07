# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable storage for normalized NVD CPE applicability matches."""

from __future__ import annotations

from typing import Any, Mapping

from services.intel.cpe import parse_cpe23
from services.intel.nvd_applicability import normalize_nvd_cpe_matches


_MAX_MATCHES = 512
_NORMALIZER_CHUNK = 128


def replace_nvd_cpe_matches(
    conn: Any,
    cve_id: str,
    payload: Mapping[str, Any],
    *,
    origin: str,
    source_version: str,
    fetched_at: str,
    expires_at: str,
) -> int:
    """Replace one CVE's matches with a fully revalidated accepted snapshot."""
    conn.execute(
        "DELETE FROM cve_advisory_cpe_matches WHERE source = 'nvd' AND cve_id = ?",
        (cve_id,),
    )
    matches = _validated_matches(payload.get("cpe_matches"))
    for item in matches:
        fields = parse_cpe23(item["criteria"])
        if fields is None:
            continue
        conn.execute(
            "INSERT INTO cve_advisory_cpe_matches ("
            "source, cve_id, match_criteria_id, criteria, cpe_part, cpe_vendor, cpe_product, "
            "criteria_version, version_start_including, version_start_excluding, "
            "version_end_including, version_end_excluding, all_versions, source_version, "
            "origin, fetched_at, expires_at) VALUES ("
            "'nvd', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cve_id,
                item["matchCriteriaId"],
                item["criteria"],
                fields[2].casefold(),
                fields[3].casefold(),
                fields[4].casefold(),
                fields[5],
                item.get("versionStartIncluding", ""),
                item.get("versionStartExcluding", ""),
                item.get("versionEndIncluding", ""),
                item.get("versionEndExcluding", ""),
                bool(item.get("all_versions")),
                source_version,
                origin,
                fetched_at,
                expires_at,
            ),
        )
    return len(matches)


def remove_stale_local_nvd_cpe_matches(conn: Any, *, source_version: str) -> None:
    """Remove matches that aren't part of the accepted local NVD snapshot."""
    conn.execute(
        "DELETE FROM cve_advisory_cpe_matches WHERE source = 'nvd' "
        "AND (origin != 'local' OR source_version != ?)",
        (source_version,),
    )


def _validated_matches(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)) or len(value) > _MAX_MATCHES:
        return []
    eligible = [
        item for item in value
        if isinstance(item, dict)
        and item.get("vulnerable") is True
        and item.get("applicability_complete") is True
        and item.get("negate") is False
    ]
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for offset in range(0, len(eligible), _NORMALIZER_CHUNK):
        wrapper = [{"nodes": [{
            "operator": "OR",
            "negate": False,
            "cpeMatch": eligible[offset:offset + _NORMALIZER_CHUNK],
        }]}]
        for item in normalize_nvd_cpe_matches(wrapper):
            match_id = str(item["matchCriteriaId"])
            if match_id in seen:
                continue
            seen.add(match_id)
            normalized.append(item)
    return normalized


__all__ = ["remove_stale_local_nvd_cpe_matches", "replace_nvd_cpe_matches"]
