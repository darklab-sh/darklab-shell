# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded CycloneDX JSON vulnerability normalization for Atlas imports."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit


def parse_cyclonedx_json(payload, state, entities, findings) -> None:
    """Import asserted vulnerabilities while keeping inventory-only components inert."""
    from services.atlas.import_parser import ImportParseError, _make_finding, _safe_text

    try:
        document = json.loads(payload.decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ImportParseError("CycloneDX report could not be decoded.") from exc
    if not isinstance(document, dict) or str(document.get("bomFormat") or "").casefold() != "cyclonedx":
        raise ImportParseError("CycloneDX report must declare bomFormat CycloneDX.")
    spec_version = _safe_text(document.get("specVersion"), limit=16)
    if not spec_version.startswith("1."):
        raise ImportParseError("Unsupported CycloneDX specification version.")
    components = {
        str(component.get("bom-ref")): component
        for component in document.get("components", [])
        if isinstance(component, dict) and component.get("bom-ref")
    }
    vulnerabilities = document.get("vulnerabilities")
    if vulnerabilities is None:
        vulnerabilities = []
    if not isinstance(vulnerabilities, list):
        raise ImportParseError("CycloneDX vulnerabilities must be an array.")
    for vulnerability in vulnerabilities:
        row_number = state.next_row()
        if not isinstance(vulnerability, dict):
            state.warn(row_number, "invalid_cyclonedx_vulnerability", "CycloneDX vulnerability must be an object.")
            continue
        vuln_id = _safe_text(vulnerability.get("id"), limit=256)
        if not vuln_id:
            state.warn(row_number, "missing_cyclonedx_vulnerability_id", "CycloneDX vulnerability is missing an id.")
            continue
        analysis = vulnerability.get("analysis") if isinstance(vulnerability.get("analysis"), dict) else {}
        if str(analysis.get("state") or "").casefold() == "not_affected":
            continue
        component_refs = [
            str(item.get("ref")) for item in vulnerability.get("affects", [])
            if isinstance(item, dict) and item.get("ref") in components
        ]
        component = components.get(component_refs[0], {}) if component_refs else {}
        component_name = _safe_text(component.get("name"), limit=256)
        component_version = _safe_text(component.get("version"), limit=128)
        subject = component.get("purl") or component_name or vuln_id
        rating = _best_rating(vulnerability.get("ratings"))
        finding = _make_finding(
            row_number=row_number,
            tool_root="cyclonedx",
            title=vulnerability.get("source") or vuln_id,
            severity=rating.get("severity") or rating.get("score"),
            subject=subject,
            description=vulnerability.get("description"),
            remediation=vulnerability.get("recommendation"),
            external_id=vuln_id,
            references=[_safe_uri(ref.get("url")) for ref in vulnerability.get("references", []) if isinstance(ref, dict)],
            source_detail={
                "adapter": "cyclonedx",
                "spec_version": spec_version,
                "vulnerability_id": vuln_id,
                "component_name": component_name,
                "component_version": component_version,
                "component_purl": _safe_text(component.get("purl"), limit=512),
                "component_refs": component_refs[:16],
                "analysis_state": _safe_text(analysis.get("state"), limit=64),
            },
        )
        if finding:
            findings.append(finding)
        else:
            state.warn(row_number, "invalid_cyclonedx_subject", "CycloneDX vulnerability had no usable component subject.")


def _best_rating(ratings: Any) -> dict[str, Any]:
    if not isinstance(ratings, list):
        return {}
    for rating in ratings:
        if isinstance(rating, dict):
            severity = rating.get("severity")
            score = rating.get("score")
            if severity or score is not None:
                return {"severity": severity, "score": score}
    return {}


def _safe_uri(value: Any) -> str:
    uri = str(value or "").strip()
    parsed = urlsplit(uri)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc and "@" not in parsed.netloc:
        return uri[:2048]
    return ""
