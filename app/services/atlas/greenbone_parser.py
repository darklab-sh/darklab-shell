# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded Greenbone native XML result normalization for Atlas imports."""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Any
from urllib.parse import urlsplit

from services.projects.findings import _finding_signature, _normalize_finding_signal_key


MAX_GREENBONE_CVE_IDS = 32
MAX_GREENBONE_REFERENCES = 32


def parse_greenbone_xml(payload, state, entities, findings) -> None:
    """Append Greenbone GMP XML results to the shared Atlas collections."""
    from services.atlas.import_parser import _iter_xml_target_elements

    for elem in _iter_xml_target_elements(payload, state, {"result"}):
        row_number = state.next_row()
        _append_greenbone_result(elem, row_number, state, entities, findings)


def _append_greenbone_result(elem, row_number, state, entities, findings) -> None:
    from services.atlas.import_parser import (
        _entity_from_target,
        _make_finding,
        _normalize_entity,
        _safe_multiline,
        _safe_text,
    )

    nvt = _direct_child(elem, "nvt")
    host_elem = _direct_child(elem, "host")
    host = _safe_text(getattr(host_elem, "text", ""), limit=512)
    hostname = _nested_text(host_elem, "hostname", limit=512)
    target = host or hostname
    nvt_oid = _safe_text(getattr(nvt, "attrib", {}).get("oid"), limit=256)
    title = _direct_text(elem, "name") or _nested_text(nvt, "name", limit=512)
    if nvt is None or not nvt_oid:
        state.warn(
            row_number,
            "missing_greenbone_nvt_oid",
            "Greenbone result is missing its NVT OID.",
        )
        return
    if not target:
        state.warn(
            row_number,
            "missing_greenbone_host",
            "Greenbone result is missing its host.",
        )
        return

    result_id = _safe_text(getattr(elem, "attrib", {}).get("id"), limit=128)
    location = _direct_text(elem, "port", limit=128)
    port, protocol = _greenbone_location(location)
    severity_score = _direct_text(elem, "severity", limit=32)
    threat = _direct_text(elem, "threat", limit=32)
    qod = _direct_child(elem, "qod")
    qod_value = _nested_text(qod, "value", limit=16)
    qod_type = _nested_text(qod, "type", limit=64)
    description = _direct_text(elem, "description")
    solution = _direct_text(elem, "solution") or _nested_text(nvt, "solution")
    observed_at = (
        _direct_text(elem, "modification_time", limit=64)
        or _direct_text(elem, "creation_time", limit=64)
    )
    family = _nested_text(nvt, "family", limit=256)
    scan_nvt_version = _direct_text(elem, "scan_nvt_version", limit=128)
    cves, web_references, cves_truncated, references_truncated = _greenbone_references(
        nvt,
        title,
        description,
    )
    if cves_truncated:
        state.warn(
            row_number,
            "greenbone_cve_limit_reached",
            "Greenbone CVE references were truncated at the per-result limit.",
            skipped=False,
        )
    if references_truncated:
        state.warn(
            row_number,
            "greenbone_reference_limit_reached",
            "Greenbone web references were truncated at the per-result limit.",
            skipped=False,
        )

    rule_identity = f"nvt:{nvt_oid}"
    source_detail: dict[str, Any] = {
        "adapter": "greenbone",
        "rule_identity": rule_identity,
        "nvt_oid": nvt_oid,
        "result_id": result_id,
        "family": family,
        "location": location,
        "port": port,
        "protocol": protocol,
        "hostname": hostname,
        "severity_score": severity_score,
        "threat": threat,
        "qod_value": qod_value,
        "qod_type": qod_type,
        "scan_nvt_version": scan_nvt_version,
        "cve_ids": cves,
    }
    entity = _entity_from_target(target, row_number, state, source_detail)
    if entity:
        entities.append(entity)
    for cve in cves:
        cve_entity = _normalize_entity(
            "cve",
            cve,
            row_number,
            state,
            source_detail={"adapter": "greenbone", "nvt_oid": nvt_oid},
        )
        if cve_entity:
            entities.append(cve_entity)

    evidence = _greenbone_evidence(
        description=_safe_multiline(description),
        location=location,
        qod_value=qod_value,
        qod_type=qod_type,
        cves=cves,
    )
    finding = _make_finding(
        row_number=row_number,
        tool_root="greenbone",
        title=title or nvt_oid,
        severity=severity_score or _greenbone_threat_severity(threat),
        affected_entity=entity,
        subject=target,
        description=description,
        remediation=solution,
        evidence=evidence,
        external_id=nvt_oid,
        references=web_references,
        observed_at=observed_at,
        source_detail=source_detail,
    )
    if finding:
        finding = replace(
            finding,
            signature_hash=_finding_signature(
                "greenbone",
                "finding",
                finding.severity,
                _normalize_finding_signal_key(rule_identity),
                finding.subject_key,
            ),
        )
        findings.append(finding)
    else:
        state.warn(
            row_number,
            "invalid_greenbone_subject",
            "Greenbone result did not contain a usable host subject.",
        )


def _local_name(tag: Any) -> str:
    return str(tag or "").rsplit("}", 1)[-1].lower()


def _direct_child(elem, name: str):
    if elem is None:
        return None
    wanted = name.lower()
    return next((child for child in list(elem) if _local_name(child.tag) == wanted), None)


def _direct_text(elem, name: str, *, limit: int = 4096) -> str:
    from services.atlas.import_parser import _safe_multiline

    child = _direct_child(elem, name)
    return _safe_multiline(getattr(child, "text", ""), limit=limit)


def _nested_text(elem, name: str, *, limit: int = 4096) -> str:
    from services.atlas.import_parser import _safe_multiline

    if elem is None:
        return ""
    wanted = name.lower()
    for child in elem.iter():
        if child is elem or _local_name(child.tag) != wanted:
            continue
        return _safe_multiline(getattr(child, "text", ""), limit=limit)
    return ""


def _greenbone_location(value: str) -> tuple[str, str]:
    location = str(value or "").strip().lower()
    if "/" not in location:
        return (location if location.isdigit() else ""), ""
    port, protocol = location.rsplit("/", 1)
    return (port if port.isdigit() else ""), (protocol if protocol in {"tcp", "udp"} else "")


def _greenbone_threat_severity(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"log", "false positive"}:
        return "info"
    return normalized


def _greenbone_references(nvt, *text_values: str) -> tuple[list[str], list[str], bool, bool]:
    cves: list[str] = []
    web_references: list[str] = []
    cve_overflow = False
    reference_overflow = False
    refs = _direct_child(nvt, "refs")
    for ref in list(refs) if refs is not None else []:
        if _local_name(ref.tag) != "ref":
            continue
        ref_id = str(ref.attrib.get("id") or "").strip()
        ref_type = str(ref.attrib.get("type") or "").strip().lower()
        for cve in re.findall(r"\bCVE-\d{4}-\d{4,}\b", ref_id, re.IGNORECASE):
            normalized = cve.upper()
            if normalized in cves:
                continue
            if len(cves) >= MAX_GREENBONE_CVE_IDS:
                cve_overflow = True
                continue
            cves.append(normalized)
        if ref_type in {"url", "web", "link"} or ref_id.lower().startswith(("http://", "https://")):
            if not _safe_web_reference(ref_id) or ref_id in web_references:
                continue
            if len(web_references) >= MAX_GREENBONE_REFERENCES:
                reference_overflow = True
                continue
            web_references.append(ref_id)
    for value in text_values:
        for cve in re.findall(r"\bCVE-\d{4}-\d{4,}\b", str(value or ""), re.IGNORECASE):
            normalized = cve.upper()
            if normalized in cves:
                continue
            if len(cves) >= MAX_GREENBONE_CVE_IDS:
                cve_overflow = True
                continue
            cves.append(normalized)
    return cves, web_references, cve_overflow, reference_overflow


def _safe_web_reference(value: str) -> bool:
    if not value or "\\" in value or any(ord(char) < 32 for char in value):
        return False
    parsed = urlsplit(value)
    return all((
        parsed.scheme.lower() in {"http", "https"},
        bool(parsed.hostname),
        parsed.username is None,
        parsed.password is None,
    ))


def _greenbone_evidence(
    *,
    description: str,
    location: str,
    qod_value: str,
    qod_type: str,
    cves: list[str],
) -> str:
    from services.atlas.import_parser import _safe_multiline

    details = [description]
    if cves:
        details.append("CVE references: " + ", ".join(cves))
    if location:
        details.append("Location: " + location)
    if qod_value:
        qod_label = f"QoD: {qod_value}%"
        if qod_type:
            qod_label += f" ({qod_type})"
        details.append(qod_label)
    return _safe_multiline("\n".join(item for item in details if item))


__all__ = ["parse_greenbone_xml"]
