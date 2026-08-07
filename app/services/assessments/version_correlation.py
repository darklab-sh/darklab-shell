# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact, inference-only product/package version to CVE correlation."""

from __future__ import annotations

from typing import Any


def correlate_version_observation(
    observation: dict[str, Any] | None,
    advisories: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    """Return only exact identifier and version matches from cached advisory data."""
    item = observation if isinstance(observation, dict) else {}
    version = _text(item.get("version"), 128)
    purl = _text(item.get("purl"), 512)
    cpe = _text(item.get("cpe"), 512)
    if not version or not (purl or cpe):
        return []
    matches = []
    for advisory in advisories if isinstance(advisories, (list, tuple)) else []:
        if not isinstance(advisory, dict):
            continue
        vulnerability_id = _text(advisory.get("cve_id") or advisory.get("id"), 128)
        if not vulnerability_id:
            continue
        identifiers = {_text(value, 512) for value in advisory.get("purls", []) if _text(value, 512)}
        identifiers.update(_text(value, 512) for value in advisory.get("cpe_names", []) if _text(value, 512))
        observed_identifier = purl or cpe
        if observed_identifier not in identifiers:
            continue
        affected_versions = {
            _text(value, 128) for value in advisory.get("affected_versions", []) if _text(value, 128)
        }
        if version not in affected_versions:
            continue
        matches.append({
            "vulnerability_id": vulnerability_id,
            "confidence": "high",
            "match_basis": "exact_purl_version" if purl else "exact_cpe_version",
            "observed_identifier": observed_identifier,
            "observed_version": version,
            "affected_range": _text(advisory.get("affected_range"), 256),
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


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


__all__ = ["correlate_version_observation"]
