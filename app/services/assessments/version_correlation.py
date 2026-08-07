# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact, inference-only product/package version to CVE correlation."""

from __future__ import annotations

from typing import Any

from services.assessments.cpe_applicability import match_cpe_applicability, normalize_observed_cpe
from services.assessments.version_ranges import match_cached_semver_range, normalize_purl


def correlate_version_observation(
    observation: dict[str, Any] | None,
    advisories: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    """Return only exact identifier and version matches from cached advisory data."""
    item = observation if isinstance(observation, dict) else {}
    version = _text(item.get("version"), 128)
    purl_record = normalize_purl(item.get("purl"), explicit_version=version)
    purl = purl_record[0] if purl_record else ""
    if purl_record:
        version = purl_record[1]
    cpe_record = normalize_observed_cpe(item.get("cpe"), explicit_version=version)
    cpe = str(cpe_record.get("identifier") or "") if cpe_record else ""
    if cpe_record and not purl:
        version = str(cpe_record["version"])
    if not version or not (purl or cpe):
        return []
    matches = []
    for advisory in advisories if isinstance(advisories, (list, tuple)) else []:
        if not isinstance(advisory, dict):
            continue
        vulnerability_id = _text(advisory.get("cve_id") or advisory.get("id"), 128)
        if not vulnerability_id:
            continue
        purl_versions = _advisory_purls(advisory)
        cpe_names = {_text(value, 512) for value in advisory.get("cpe_names", []) if _text(value, 512)}
        observed_identifier = purl or cpe
        if purl and purl not in purl_versions:
            continue
        affected_versions = {
            _text(value, 128) for value in advisory.get("affected_versions", []) if _text(value, 128)
        }
        affected_versions.update(purl_versions.get(purl, set()))
        range_match = match_cached_semver_range(version, advisory.get("ranges")) if purl else None
        cpe_match = match_cpe_applicability(cpe_record, advisory.get("cpe_matches")) if not purl else None
        exact_cpe = bool(not purl and cpe in cpe_names and version in affected_versions)
        if version not in affected_versions and range_match is None and cpe_match is None:
            continue
        if not purl and not exact_cpe and cpe_match is None:
            continue
        match_basis = "exact_purl_version" if purl else "exact_cpe_version"
        affected_range = _text(advisory.get("affected_range"), 256)
        range_type = "EXACT"
        if range_match is not None:
            match_basis = "exact_purl_semver_range"
            affected_range = range_match["affected_range"]
            range_type = range_match["range_type"]
        elif cpe_match is not None:
            match_basis = cpe_match["match_basis"]
            affected_range = cpe_match["affected_range"]
            range_type = cpe_match["range_type"]
        matches.append({
            "vulnerability_id": vulnerability_id,
            "confidence": "high",
            "match_basis": match_basis,
            "observed_identifier": observed_identifier,
            "observed_version": version,
            "affected_range": affected_range,
            "range_type": range_type,
            "advisory_source": _text(advisory.get("source"), 64),
            "advisory_source_version": _text(advisory.get("source_version"), 128),
            "validation_method": "version_inference",
        })
    return matches


def materialize_version_findings(
    observation: dict[str, Any] | None,
    advisories: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    source_run_id: str = "",
    source_kind: str = "run",
    observed_at: str = "",
    tool_version: str = "",
) -> list[dict[str, Any]]:
    """Build provenance-rich inference records from exact advisory matches."""
    item = observation if isinstance(observation, dict) else {}
    matches = correlate_version_observation(item, advisories)
    observation_id = _text(item.get("observation_id"), 128)
    target = _text(item.get("target") or item.get("canonical_value"), 512)
    records = []
    for match in matches:
        records.append({
            "kind": "finding",
            "validation_method": "version_inference",
            "title": f"Version may be affected by {match['vulnerability_id']}",
            "vulnerability_id": match["vulnerability_id"],
            "confidence": match["confidence"],
            "match_basis": match["match_basis"],
            "affected_range": match["affected_range"],
            "range_type": match["range_type"],
            "advisory_source": match["advisory_source"],
            "advisory_source_version": match["advisory_source_version"],
            "target": target,
            "source": {
                "run_id": _text(source_run_id, 128),
                "kind": _text(source_kind, 32),
                "observation_id": observation_id,
                "observed_at": _text(observed_at, 64),
                "tool_version": _text(tool_version, 128),
            },
        })
    return records


def _advisory_purls(advisory: dict[str, Any]) -> dict[str, set[str]]:
    values = list(advisory.get("purls", [])) if isinstance(advisory.get("purls"), (list, tuple)) else []
    if advisory.get("package_purl"):
        values.append(advisory["package_purl"])
    normalized: dict[str, set[str]] = {}
    for value in values:
        record = normalize_purl(value, explicit_version="", require_version=False)
        if record:
            versions = normalized.setdefault(record[0], set())
            if record[1]:
                versions.add(record[1])
    return normalized


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


__all__ = ["correlate_version_observation"]
