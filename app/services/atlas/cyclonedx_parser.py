# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded CycloneDX JSON inventory, dependency, and VEX normalization."""

from __future__ import annotations

import json
from typing import Any

from services.atlas.cyclonedx_details import (
    component_records,
    dependency_records,
    document_provenance,
    safe_references,
    vulnerability_detail,
)


def parse_cyclonedx_json(payload, state, entities, findings, evidence) -> None:
    """Append typed SBOM evidence and only affected vulnerability findings."""
    from services.atlas.import_parser import ImportParseError, _safe_text
    from services.atlas.import_types import ImportEvidence

    try:
        document = json.loads(payload.decode("utf-8-sig", errors="replace"))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ImportParseError("CycloneDX report could not be decoded.") from exc
    if not isinstance(document, dict) or str(document.get("bomFormat") or "").casefold() != "cyclonedx":
        raise ImportParseError("CycloneDX report must declare bomFormat CycloneDX.")
    spec_version = _safe_text(document.get("specVersion"), limit=16)
    if not spec_version.startswith("1."):
        raise ImportParseError("Unsupported CycloneDX specification version.")
    provenance = document_provenance(document, spec_version)
    components = component_records(document, state, evidence, provenance)
    dependency_records(document, components, state, evidence, provenance)
    raw_vulnerabilities = document.get("vulnerabilities")
    vulnerabilities = [] if raw_vulnerabilities is None else raw_vulnerabilities
    if not isinstance(vulnerabilities, list):
        raise ImportParseError("CycloneDX vulnerabilities must be an array.")
    for raw in vulnerabilities:
        row_number = state.next_row()
        vulnerability = raw if isinstance(raw, dict) else {}
        vuln_id = _safe_text(vulnerability.get("id"), limit=256)
        if not vuln_id:
            state.warn(
                row_number,
                "missing_cyclonedx_vulnerability_id",
                "CycloneDX vulnerability is missing an id.",
            )
            continue
        detail = vulnerability_detail(vulnerability, components, provenance)
        evidence.append(ImportEvidence(
            row_number=row_number,
            evidence_type="cyclonedx_vulnerability",
            subject_key=vuln_id,
            label=vuln_id,
            external_id=vuln_id,
            observed_at=str(provenance.get("observed_at") or ""),
            source_detail={
                "adapter": "cyclonedx",
                "vulnerability_id": vuln_id,
                **detail,
            },
        ))
        raw_analysis = detail.get("analysis")
        analysis = raw_analysis if isinstance(raw_analysis, dict) else {}
        category = str(analysis.get("category") or "affected")
        if category != "affected":
            state.warn(
                row_number,
                "cyclonedx_vex_disposition_recorded",
                "CycloneDX VEX disposition was retained as evidence for review.",
                skipped=False,
            )
            continue
        _append_findings(
            vulnerability,
            vuln_id,
            detail,
            row_number,
            state,
            findings,
        )


def _append_findings(
    vulnerability: dict[str, Any],
    vuln_id: str,
    detail: dict[str, Any],
    row_number: int,
    state: Any,
    findings: list[Any],
) -> None:
    from services.atlas.import_parser import _make_finding, _safe_text

    rating = _best_rating(vulnerability.get("ratings"))
    raw_source = vulnerability.get("source")
    raw_components = detail.get("components")
    source = raw_source if isinstance(raw_source, dict) else {}
    components = raw_components if isinstance(raw_components, list) else []
    subjects = components
    appended = False
    for component in subjects:
        if len(findings) >= state.limits.max_rows:
            state.warn(
                row_number,
                "cyclonedx_finding_limit_reached",
                "CycloneDX findings were truncated at the configured row limit.",
                skipped=False,
            )
            break
        component_detail = component if isinstance(component, dict) else {}
        subject = (
            component_detail.get("purl")
            or component_detail.get("cpe")
            or component_detail.get("bom_ref")
            or vuln_id
        )
        finding = _make_finding(
            row_number=row_number,
            tool_root="cyclonedx",
            title=_safe_text(source.get("name"), limit=256) or vuln_id,
            severity=rating.get("severity") or rating.get("score"),
            subject=subject,
            description=vulnerability.get("description") or vulnerability.get("detail"),
            remediation=vulnerability.get("recommendation"),
            external_id=vuln_id,
            references=safe_references(vulnerability.get("references")),
            observed_at=detail.get("observed_at"),
            source_detail={
                "adapter": "cyclonedx",
                "vulnerability_id": vuln_id,
                "rating": rating,
                "component": component_detail,
                **detail,
            },
        )
        if finding:
            findings.append(finding)
            appended = True
    if not appended:
        state.warn(
            row_number,
            "invalid_cyclonedx_subject",
            "CycloneDX vulnerability had no usable subject.",
        )


def _best_rating(value: Any) -> dict[str, Any]:
    from services.atlas.import_parser import _safe_text

    ratings = value if isinstance(value, list) else []
    for raw in ratings:
        rating = raw if isinstance(raw, dict) else {}
        severity = _safe_text(rating.get("severity"), limit=32)
        score = _score(rating.get("score"))
        if severity or score is not None:
            return {
                key: item for key, item in (
                    ("severity", severity),
                    ("score", score),
                    ("method", _safe_text(rating.get("method"), limit=64)),
                    ("vector", _safe_text(rating.get("vector"), limit=256)),
                ) if item not in (None, "")
            }
    return {}


def _score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 10 else None


__all__ = ["parse_cyclonedx_json"]
