# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed exact-version evidence from bounded Nessus report items."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.assessments.cpe_applicability import normalize_observed_cpe
from services.assessments.versioned_cpe import normalize_versioned_cpe
from services.atlas.import_types import ImportEntity, ImportEvidence
from services.intel.canonical import entity_signature


NESSUS_XML_CPE_PARSER_VERSION = "nessus-xml-cpe-v1"
NESSUS_XML_TOOL_VERSION = "Nessus XML v2"
NESSUS_REPORT_ITEM_CPE_LIMIT = 16
_SCAN_TIME_KEYS = ("host_end", "host_start")
_SCANNER_VERSION_KEYS = ("nessus_version", "nessus_server_version", "scanner_version")


def nessus_host_property(properties: dict[str, str], name: Any, value: Any) -> None:
    """Retain only bounded scan-time and scanner-version host properties."""
    key = "_".join(str(name or "").strip().casefold().replace("-", " ").split())
    if key not in {*_SCAN_TIME_KEYS, *_SCANNER_VERSION_KEYS}:
        return
    text = " ".join(str(value or "").split())
    if text and len(text) <= 128:
        properties[key] = text


def append_nessus_version_evidence(
    elem: Any,
    entity: ImportEntity | None,
    *,
    row_number: int,
    properties: dict[str, str],
    evidence: list[ImportEvidence],
    evidence_limit: int,
) -> bool:
    """Append exact service CPE observations and report whether rows were truncated."""
    if entity is None:
        return False
    observed_at = _observed_at(properties)
    tool_version = _tool_version(properties)
    target_key = entity_signature(entity.kind, entity.canonical_value)
    seen: set[str] = set()
    cpes = []
    for child in list(elem):
        if str(getattr(child, "tag", "")).rsplit("}", 1)[-1].casefold() != "cpe":
            continue
        cpe = normalize_versioned_cpe(getattr(child, "text", ""))
        if cpe and cpe not in seen:
            seen.add(cpe)
            cpes.append(cpe)
    truncated = len(cpes) > NESSUS_REPORT_ITEM_CPE_LIMIT
    for cpe in cpes[:NESSUS_REPORT_ITEM_CPE_LIMIT]:
        if len(evidence) >= evidence_limit:
            return True
        normalized = normalize_observed_cpe(cpe)
        if normalized is None:
            continue
        version = str(normalized["version"])
        service = " ".join(str(elem.attrib.get("svc_name") or "").split())[:128]
        evidence.append(ImportEvidence(
            row_number=row_number,
            evidence_type="nessus_service_version",
            subject_key=f"{target_key}\x1f{cpe}",
            label=" ".join(part for part in (entity.canonical_value, service, version) if part),
            external_id=" ".join(str(elem.attrib.get("pluginID") or elem.attrib.get("plugin_id") or "").split())[:128],
            observed_at=observed_at,
            source_detail={
                "adapter": "nessus",
                "target_kind": entity.kind,
                "target_value": entity.canonical_value,
                "target_key": target_key,
                "cpe": cpe,
                "version": version,
                "port": " ".join(str(elem.attrib.get("port") or "").split())[:16],
                "protocol": " ".join(str(elem.attrib.get("protocol") or "").split())[:16],
                "service": service,
                "tool_version": tool_version,
                "parser_version": NESSUS_XML_CPE_PARSER_VERSION,
                "source_observed_at": next((properties[key] for key in _SCAN_TIME_KEYS if properties.get(key)), ""),
                "source_observed_at_timezone": "source" if observed_at else "unspecified",
            },
        ))
    return truncated


def _observed_at(properties: dict[str, str]) -> str:
    for key in _SCAN_TIME_KEYS:
        value = properties.get(key, "")
        if not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return ""
def _tool_version(properties: dict[str, str]) -> str:
    for key in _SCANNER_VERSION_KEYS:
        version = properties.get(key, "")
        if version:
            return f"Nessus {version}"[:128]
    return NESSUS_XML_TOOL_VERSION


__all__ = [
    "NESSUS_XML_CPE_PARSER_VERSION",
    "NESSUS_XML_TOOL_VERSION",
    "append_nessus_version_evidence",
    "nessus_host_property",
]
