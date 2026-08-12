# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalize Atlas import files into parser-neutral rows."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import BytesIO, StringIO
import json
import logging
import re
from typing import Any, BinaryIO, IO, cast
from urllib.parse import urlsplit

from services.nuclei.provenance import nuclei_source_detail
from services.atlas.sarif_parser import parse_sarif_json

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from services.atlas.materializer import canonicalize_entity_record
from services.atlas.import_formats import SUPPORTED_FORMATS
from services.atlas.schema import ATLAS_ENTITY_TYPES
from services.atlas.import_archive import (
    ImportSourceError,
    PreparedImportSource,
    prepare_import_source,
)
from services.atlas.import_types import (
    ImportEntity,
    ImportEvidence,
    ImportFinding,
    ImportParseResult,
    ImportWarning,
)
from services.intel.canonical import entity_signature
from services.projects.findings import _finding_signature, _normalize_finding_signal_key

log = logging.getLogger("shell")

ENTITY_KINDS = ATLAS_ENTITY_TYPES
SEVERITIES = frozenset({"info", "low", "medium", "high", "critical"})
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_EXPANDED_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_ROWS = 5000
DEFAULT_MAX_WARNINGS = 100
DEFAULT_MAX_XML_ELEMENTS = 100000
MAX_TEXT_CHARS = 4096


class ImportParseError(ValueError):
    """Safe parser error intended for preview responses."""


@dataclass(frozen=True)
class ImportParserLimits:
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_expanded_bytes: int = DEFAULT_MAX_EXPANDED_BYTES
    max_rows: int = DEFAULT_MAX_ROWS
    max_warnings: int = DEFAULT_MAX_WARNINGS
    max_xml_elements: int = DEFAULT_MAX_XML_ELEMENTS


class _ParseState:
    def __init__(self, limits: ImportParserLimits):
        self.limits = limits
        self.row_count = 0
        self.skipped_count = 0
        self.warnings: list[ImportWarning] = []
        self.suppressed_warning_count = 0

    def next_row(self) -> int:
        self.row_count += 1
        if self.row_count > self.limits.max_rows:
            raise ImportParseError(f"Import row limit exceeded ({self.limits.max_rows}).")
        return self.row_count

    def warn(self, row_number: int, code: str, message: str, *, skipped: bool = True) -> None:
        self.skipped_count += int(bool(skipped))
        if len(self.warnings) >= self.limits.max_warnings:
            self.suppressed_warning_count += 1
            return
        self.warnings.append(ImportWarning(row_number, code, message))


def _warning_code_summary(warnings: list[ImportWarning], *, limit: int = 8) -> dict[str, int]:
    summary: dict[str, int] = {}
    for warning in warnings:
        code = _safe_text(warning.code, limit=64) or "unknown"
        summary[code] = summary.get(code, 0) + 1
    return dict(sorted(summary.items(), key=lambda item: (-item[1], item[0]))[:limit])


def parse_import_file(
    source: bytes | str | BinaryIO | IO[bytes],
    *,
    format_id: str,
    limits: ImportParserLimits | None = None,
) -> ImportParseResult:
    normalized_format = str(format_id or "").strip().lower()
    if normalized_format not in SUPPORTED_FORMATS:
        raise ImportParseError(f"Unsupported import format: {format_id!r}.")
    active_limits = limits or ImportParserLimits()
    prepared = read_import_source(source, active_limits)
    return parse_prepared_import(prepared, format_id=normalized_format, limits=active_limits)


def parse_prepared_import(
    prepared: PreparedImportSource,
    *,
    format_id: str,
    limits: ImportParserLimits,
) -> ImportParseResult:
    normalized_format = str(format_id or "").strip().lower()
    if normalized_format not in SUPPORTED_FORMATS:
        raise ImportParseError(f"Unsupported import format: {format_id!r}.")
    payload = prepared.payload
    log.debug("ATLAS_IMPORT_PARSE_STARTED", extra={
        "format_id": normalized_format,
        "upload_bytes": prepared.upload_bytes,
        "expanded_bytes": prepared.expanded_bytes,
        "compression": prepared.compression,
        "max_rows": limits.max_rows,
        "max_warnings": limits.max_warnings,
        "max_xml_elements": limits.max_xml_elements,
    })
    state = _ParseState(limits)
    entities: list[ImportEntity] = []
    findings: list[ImportFinding] = []
    evidence: list[ImportEvidence] = []

    if normalized_format == "generic_csv":
        _parse_generic_csv(payload, state, entities, findings)
    elif normalized_format == "generic_jsonl":
        _parse_generic_jsonl(payload, state, entities, findings)
    elif normalized_format == "nuclei_jsonl":
        _parse_nuclei_jsonl(payload, state, entities, findings)
    elif normalized_format == "sarif_json":
        parse_sarif_json(payload, state, entities, findings)
    elif normalized_format == "cyclonedx_json":
        from services.atlas.cyclonedx_parser import parse_cyclonedx_json
        parse_cyclonedx_json(payload, state, entities, findings, evidence)
    elif normalized_format == "greenbone_xml":
        from services.atlas.greenbone_parser import parse_greenbone_xml
        parse_greenbone_xml(payload, state, entities, findings)
    elif normalized_format == "nessus_xml":
        _parse_nessus_xml(payload, state, entities, findings, evidence)
    elif normalized_format == "zap_json":
        _parse_zap_json(payload, state, entities, findings)
    elif normalized_format == "zap_xml":
        _parse_zap_xml(payload, state, entities, findings)
    elif normalized_format == "burp_xml":
        _parse_burp_xml(payload, state, entities, findings)

    if state.row_count == 0:
        raise ImportParseError(f"No {normalized_format} rows were found.")
    warning_codes = _warning_code_summary(state.warnings)
    if state.suppressed_warning_count > 0:
        log.warning("ATLAS_IMPORT_WARNINGS_TRUNCATED", extra={
            "format_id": normalized_format,
            "skipped": state.skipped_count,
            "warning_count": len(state.warnings),
            "suppressed_warning_count": state.suppressed_warning_count,
            "max_warnings": limits.max_warnings,
            "warning_codes": warning_codes,
        })
    log.debug("ATLAS_IMPORT_PARSE_COMPLETED", extra={
        "format_id": normalized_format,
        "rows": state.row_count,
        "entities": len(entities),
        "findings": len(findings),
        "evidence": len(evidence),
        "skipped": state.skipped_count,
        "warning_count": len(state.warnings),
        "suppressed_warning_count": state.suppressed_warning_count,
        "warning_codes": warning_codes,
    })
    return ImportParseResult(
        format_id=normalized_format,
        row_count=state.row_count,
        skipped_count=state.skipped_count,
        entities=entities,
        findings=findings,
        evidence=evidence,
        warnings=state.warnings,
        suppressed_warning_count=state.suppressed_warning_count,
    )


def read_import_source(
    source: bytes | str | BinaryIO | IO[bytes],
    limits: ImportParserLimits,
) -> PreparedImportSource:
    try:
        return prepare_import_source(
            source,
            max_upload_bytes=limits.max_upload_bytes,
            max_expanded_bytes=limits.max_expanded_bytes,
        )
    except ImportSourceError as exc:
        raise ImportParseError(str(exc)) from exc


def _safe_text(value: Any, *, limit: int = MAX_TEXT_CHARS) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _safe_multiline(value: Any, *, limit: int = MAX_TEXT_CHARS) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:limit]


def _normalize_entity(
    kind: Any,
    value: Any,
    row_number: int,
    state: _ParseState,
    *,
    warn: bool = True,
    **kwargs: Any,
) -> ImportEntity | None:
    entity_kind = str(kind or "").strip().lower()
    if entity_kind == "host":
        return _entity_from_target(value, row_number, state, kwargs.get("source_detail") or {})
    if entity_kind not in ENTITY_KINDS:
        if warn:
            state.warn(row_number, "invalid_entity_kind", f"Unsupported entity kind: {kind!r}.")
        return None
    raw_value = _safe_text(value)
    canonical = canonicalize_entity_record({"type": entity_kind, "value": raw_value})
    if canonical is None:
        if warn:
            state.warn(row_number, "invalid_entity_value", f"Could not normalize {entity_kind} value.")
        return None
    normalized_kind, canonical_value = canonical
    return ImportEntity(
        row_number=row_number,
        kind=normalized_kind,
        value=raw_value,
        canonical_value=canonical_value,
        observed_at=_safe_text(kwargs.get("observed_at")),
        external_id=_safe_text(kwargs.get("external_id")),
        source_detail=dict(kwargs.get("source_detail") or {}),
    )


def _finding_subject(entity: ImportEntity | None, fallback: Any) -> str:
    if entity:
        return entity_signature(entity.kind, entity.canonical_value)
    return _safe_text(fallback)[:512]


def _normalize_severity(value: Any) -> str:
    severity = str(value or "").strip().lower()
    word_match = re.search(r"\b(info|informational|low|medium|moderate|high|critical)\b", severity, re.I)
    if word_match:
        severity = word_match.group(1).lower()
    if severity in {"informational", "none", "note"}:
        return "info"
    if severity in {"moderate", "warning"}:
        return "medium"
    if severity in SEVERITIES:
        return severity
    try:
        score = float(severity)
    except (TypeError, ValueError):
        return ""
    if score >= 9:
        return "critical"
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    if score > 0:
        return "low"
    return "info"


def _zap_severity(alert: dict[str, Any]) -> str:
    severity = _normalize_severity(alert.get("riskdesc") or alert.get("risk"))
    if severity:
        return severity
    riskcode = str(alert.get("riskcode") or "").strip()
    return {
        "0": "info",
        "1": "low",
        "2": "medium",
        "3": "high",
    }.get(riskcode, _normalize_severity(riskcode))


def _make_finding(
    *,
    row_number: int,
    tool_root: str,
    title: Any,
    severity: Any,
    affected_entity: ImportEntity | None = None,
    subject: Any = "",
    description: Any = "",
    remediation: Any = "",
    evidence: Any = "",
    external_id: Any = "",
    references: list[str] | None = None,
    observed_at: Any = "",
    source_detail: dict[str, Any] | None = None,
) -> ImportFinding | None:
    normalized_title = _safe_text(title) or _safe_text(external_id) or "Imported finding"
    normalized_subject = _finding_subject(affected_entity, subject)
    if not normalized_subject:
        return None
    normalized_severity = _normalize_severity(severity)
    signal_key = _normalize_finding_signal_key(
        "\n".join(part for part in (normalized_title, _safe_multiline(evidence)) if part)
    )
    signature_hash = _finding_signature(tool_root, "finding", normalized_severity, signal_key, normalized_subject)
    return ImportFinding(
        row_number=row_number,
        title=normalized_title,
        severity=normalized_severity,
        subject_key=normalized_subject,
        signature_hash=signature_hash,
        description=_safe_multiline(description),
        remediation=_safe_multiline(remediation),
        evidence=_safe_multiline(evidence),
        affected_entity=affected_entity,
        external_id=_safe_text(external_id),
        references=[_safe_text(ref) for ref in references or [] if _safe_text(ref)],
        observed_at=_safe_text(observed_at),
        source_detail=dict(source_detail or {}),
    )


def _parse_generic_csv(
    payload: bytes,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
) -> None:
    reader = csv.DictReader(StringIO(payload.decode("utf-8-sig", errors="replace")))
    if not reader.fieldnames:
        raise ImportParseError("CSV import is missing a header row.")
    for raw_row in reader:
        row_number = state.next_row()
        _parse_generic_mapping(raw_row, row_number, "generic", state, entities, findings)


def _parse_generic_jsonl(
    payload: bytes,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
) -> None:
    for raw_line in payload.decode("utf-8-sig", errors="replace").splitlines():
        if not raw_line.strip():
            continue
        row_number = state.next_row()
        try:
            raw_row = json.loads(raw_line)
        except json.JSONDecodeError:
            state.warn(row_number, "invalid_json", "JSONL row could not be decoded.")
            continue
        if not isinstance(raw_row, dict):
            state.warn(row_number, "invalid_json_shape", "JSONL row must be an object.")
            continue
        _parse_generic_mapping(raw_row, row_number, "generic", state, entities, findings)


def _parse_generic_mapping(
    raw_row: dict[str, Any],
    row_number: int,
    tool_root: str,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
) -> None:
    row_type = str(raw_row.get("row_type") or raw_row.get("type") or "").strip().lower()
    entity_kind = raw_row.get("entity_kind") or raw_row.get("kind")
    entity_value = raw_row.get("entity_value") or raw_row.get("value")
    entity = None
    if entity_kind or entity_value:
        entity = _normalize_entity(
            entity_kind,
            entity_value,
            row_number,
            state,
            observed_at=raw_row.get("observed_at"),
            external_id=raw_row.get("external_id"),
            source_detail={"adapter": tool_root},
        )
        if entity:
            entities.append(entity)
    if row_type == "entity" or not (raw_row.get("title") or raw_row.get("finding_title")):
        if not entity and not (entity_kind or entity_value):
            state.warn(row_number, "empty_entity_row", "Entity row did not contain a valid entity.")
        return
    finding = _make_finding(
        row_number=row_number,
        tool_root=tool_root,
        title=raw_row.get("title") or raw_row.get("finding_title"),
        severity=raw_row.get("severity"),
        affected_entity=entity,
        subject=raw_row.get("subject_key") or raw_row.get("subject"),
        description=raw_row.get("description"),
        evidence=raw_row.get("evidence"),
        external_id=raw_row.get("external_id"),
        references=_split_references(raw_row.get("references")),
        observed_at=raw_row.get("observed_at"),
        source_detail={"adapter": tool_root},
    )
    if finding:
        findings.append(finding)
    else:
        state.warn(row_number, "invalid_finding_subject", "Finding row did not contain a usable subject.")


def _split_references(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_safe_text(item) for item in value if _safe_text(item)]
    raw = str(value or "")
    return [_safe_text(item) for item in re.split(r"[\s,]+", raw) if _safe_text(item)]


def _parse_nuclei_jsonl(
    payload: bytes,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
) -> None:
    for raw_line in payload.decode("utf-8-sig", errors="replace").splitlines():
        if not raw_line.strip():
            continue
        row_number = state.next_row()
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            state.warn(row_number, "invalid_json", "Nuclei JSONL row could not be decoded.")
            continue
        if not isinstance(row, dict):
            state.warn(row_number, "invalid_json_shape", "Nuclei JSONL row must be an object.")
            continue
        row_data = cast(dict[str, Any], row)
        raw_info = row_data.get("info")
        info = cast(dict[str, Any], raw_info) if isinstance(raw_info, dict) else {}
        matched = row_data.get("matched-at") or row_data.get("host") or row_data.get("url") or row_data.get("ip")
        source_detail = nuclei_source_detail("", row=row_data)
        entity = _entity_from_target(matched, row_number, state, source_detail)
        if entity:
            entities.append(entity)
        references = info.get("reference") or info.get("references") or []
        if isinstance(references, str):
            references = [references]
        finding = _make_finding(
            row_number=row_number,
            tool_root="nuclei",
            title=info.get("name") or row_data.get("template-id"),
            severity=info.get("severity"),
            affected_entity=entity,
            subject=matched or row_data.get("template-id"),
            description=info.get("description"),
            evidence=row_data.get("matcher-name") or row_data.get("extracted-results") or row_data.get("curl-command"),
            external_id=row_data.get("template-id"),
            references=[_safe_text(ref) for ref in references if _safe_text(ref)],
            source_detail=source_detail,
        )
        if finding:
            findings.append(finding)


def _entity_from_target(target: Any, row_number: int, state: _ParseState, detail: dict[str, Any]) -> ImportEntity | None:
    raw = _safe_text(target)
    if not raw:
        return None
    for kind, candidate in _target_candidates(raw):
        entity = _normalize_entity(kind, candidate, row_number, state, warn=False, source_detail=detail)
        if entity:
            return entity
    state.warn(row_number, "invalid_target_value", "Could not normalize target value.")
    return None


def _target_candidates(raw: str) -> list[tuple[str, str]]:
    parsed = urlsplit(raw)
    if parsed.scheme and parsed.netloc:
        candidates = [("url", raw)]
        host_candidate = _target_host_candidate(parsed.hostname or "")
        if host_candidate:
            candidates.append(host_candidate)
        return candidates
    if re.fullmatch(r"CVE-\d{4}-\d{4,}", raw, re.I):
        return [("cve", raw)]
    if re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", raw):
        return [("hash", raw)]
    schemeless = urlsplit(f"//{raw}")
    if schemeless.netloc and schemeless.hostname:
        host_candidate = _target_host_candidate(schemeless.hostname)
        if host_candidate:
            return [host_candidate]
    if ":" in raw and not re.search(r"[a-z]", raw, re.I):
        return [("ip", raw)]
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", raw):
        return [("ip", raw)]
    return [("domain", raw)]


def _target_host_candidate(host: str) -> tuple[str, str] | None:
    normalized = host.strip().strip("[]")
    if not normalized:
        return None
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", normalized):
        return "ip", normalized
    if ":" in normalized and not re.search(r"[a-z]", normalized, re.I):
        return "ip", normalized
    return "domain", normalized


def _iter_xml_end_elements(payload: bytes, state: _ParseState):
    element_count = 0
    try:
        iterator = SafeElementTree.iterparse(
            BytesIO(payload),
            events=("end",),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
        for _event, elem in iterator:
            element_count += 1
            if element_count > state.limits.max_xml_elements:
                raise ImportParseError(f"XML element limit exceeded ({state.limits.max_xml_elements}).")
            yield elem
            elem.clear()
    except DefusedXmlException as exc:
        raise ImportParseError("XML import contains unsafe or unsupported XML declarations.") from exc
    except SafeElementTree.ParseError as exc:
        raise ImportParseError("XML import could not be parsed.") from exc


def _iter_xml_target_elements(payload: bytes, state: _ParseState, target_names: set[str]):
    element_count = 0
    active_depth = 0
    try:
        iterator = SafeElementTree.iterparse(
            BytesIO(payload),
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
        for event, elem in iterator:
            element_name = _local_name(elem.tag)
            if event == "start":
                if active_depth or element_name in target_names:
                    active_depth += 1
                continue
            element_count += 1
            if element_count > state.limits.max_xml_elements:
                raise ImportParseError(f"XML element limit exceeded ({state.limits.max_xml_elements}).")
            if not active_depth:
                elem.clear()
                continue
            if element_name in target_names and active_depth == 1:
                yield elem
                elem.clear()
                active_depth = 0
                continue
            active_depth -= 1
    except DefusedXmlException as exc:
        raise ImportParseError("XML import contains unsafe or unsupported XML declarations.") from exc
    except SafeElementTree.ParseError as exc:
        raise ImportParseError("XML import could not be parsed.") from exc


def _local_name(tag: Any) -> str:
    return str(tag or "").rsplit("}", 1)[-1].lower()


def _child_text(elem: Any, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(elem):
        if _local_name(child.tag) in wanted:
            return _safe_multiline(child.text)
    return ""


def _descendant_text(elem: Any) -> str:
    parts: list[str] = []
    for node in elem.iter():
        text = _safe_multiline(getattr(node, "text", ""))
        if text:
            parts.append(text)
    return _safe_multiline("\n".join(parts))


def _parse_nessus_xml(
    payload: bytes,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
    evidence: list[ImportEvidence],
) -> None:
    from services.atlas.nessus_versions import nessus_host_property

    host_stack: list[dict[str, Any]] = []
    active_report_item_depth = 0
    try:
        iterator = SafeElementTree.iterparse(
            BytesIO(payload),
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
        element_count = 0
        for event, elem in iterator:
            element_name = _local_name(elem.tag)
            if event == "start":
                if element_name == "reporthost":
                    host_stack.append({"host": _safe_text(elem.attrib.get("name")), "properties": {}})
                if active_report_item_depth or element_name == "reportitem":
                    active_report_item_depth += 1
                continue
            element_count += 1
            if element_count > state.limits.max_xml_elements:
                raise ImportParseError(f"XML element limit exceeded ({state.limits.max_xml_elements}).")
            if active_report_item_depth:
                if element_name == "reportitem" and active_report_item_depth == 1:
                    context = host_stack[-1] if host_stack else {}
                    _append_nessus_report_item(
                        elem, str(context.get("host") or ""), state, entities, findings, evidence,
                        (properties if isinstance((properties := context.get("properties")), dict) else {}),
                    )
                    elem.clear()
                    active_report_item_depth = 0
                    continue
                active_report_item_depth -= 1
                continue
            if element_name == "tag" and host_stack:
                nessus_host_property(host_stack[-1]["properties"], elem.attrib.get("name"), elem.text)
                elem.clear()
                continue
            if element_name != "reporthost":
                elem.clear()
                continue
            if host_stack:
                host_stack.pop()
            elem.clear()
    except DefusedXmlException as exc:
        raise ImportParseError("XML import contains unsafe or unsupported XML declarations.") from exc
    except SafeElementTree.ParseError as exc:
        raise ImportParseError("XML import could not be parsed.") from exc


def _append_nessus_report_item(
    elem: Any,
    parent_host: str,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
    evidence: list[ImportEvidence],
    host_properties: dict[str, str],
) -> None:
    from services.atlas.nessus_versions import append_nessus_version_evidence

    row_number = state.next_row()
    host = elem.attrib.get("host") or elem.attrib.get("hostname") or parent_host
    entity = _entity_from_target(host, row_number, state, {"adapter": "nessus"}) if host else None
    if entity:
        entities.append(entity)
    if append_nessus_version_evidence(
        elem,
        entity,
        row_number=row_number,
        properties=host_properties,
        evidence=evidence,
        evidence_limit=state.limits.max_rows,
    ):
        state.warn(
            row_number,
            "nessus_service_version_limit_reached",
            "Nessus service-version evidence was truncated at the configured limit.",
            skipped=False,
        )
    severity = _nessus_severity(elem.attrib.get("severity"))
    plugin_id = elem.attrib.get("pluginID") or elem.attrib.get("plugin_id")
    plugin_name = elem.attrib.get("pluginName") or elem.attrib.get("plugin_name")
    cve_values = _child_text(elem, "cve")
    for cve in re.findall(r"CVE-\d{4}-\d{4,}", cve_values, re.I):
        cve_entity = _normalize_entity("cve", cve, row_number, state, source_detail={"adapter": "nessus"})
        if cve_entity:
            entities.append(cve_entity)
    finding = _make_finding(
        row_number=row_number,
        tool_root="nessus",
        title=plugin_name or plugin_id,
        severity=severity,
        affected_entity=entity,
        subject=host or plugin_id,
        description=_child_text(elem, "description", "synopsis"),
        remediation=_child_text(elem, "solution"),
        evidence=_child_text(elem, "plugin_output"),
        external_id=plugin_id,
        references=_split_references(_child_text(elem, "see_also", "xref")),
        source_detail={
            "adapter": "nessus",
            "plugin_id": plugin_id,
            "port": elem.attrib.get("port", ""),
            "protocol": elem.attrib.get("protocol", ""),
            "service": elem.attrib.get("svc_name", ""),
        },
    )
    if finding:
        findings.append(finding)
    else:
        state.warn(row_number, "invalid_finding_subject", "Nessus finding did not contain a usable subject.")


def _nessus_severity(value: Any) -> str:
    return {
        "0": "info",
        "1": "low",
        "2": "medium",
        "3": "high",
        "4": "critical",
    }.get(str(value or "").strip(), _normalize_severity(value))


def _parse_zap_json(
    payload: bytes,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
) -> None:
    try:
        doc = json.loads(payload.decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ImportParseError("ZAP JSON report could not be decoded.") from exc
    sites = doc.get("site") if isinstance(doc, dict) else None
    if isinstance(sites, dict):
        sites = [sites]
    if not isinstance(sites, list):
        raise ImportParseError("ZAP JSON report is missing a site list.")
    for site in sites:
        alerts = site.get("alerts") if isinstance(site, dict) else None
        if isinstance(alerts, dict):
            alerts = [alerts]
        for alert in alerts or []:
            if not isinstance(alert, dict):
                continue
            row_number = state.next_row()
            _append_zap_alert(alert, row_number, state, entities, findings)


def _parse_zap_xml(
    payload: bytes,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
) -> None:
    for elem in _iter_xml_target_elements(payload, state, {"alertitem"}):
        row_number = state.next_row()
        alert = _zap_xml_alert_dict(elem)
        _append_zap_alert(alert, row_number, state, entities, findings)


def _zap_xml_alert_dict(elem: Any) -> dict[str, Any]:
    alert: dict[str, Any] = {}
    instances: list[dict[str, str]] = []
    for child in list(elem):
        name = _local_name(child.tag)
        if name == "instances":
            for instance in list(child):
                if _local_name(instance.tag) != "instance":
                    continue
                item = {
                    _local_name(field.tag): _safe_multiline(field.text)
                    for field in list(instance)
                    if _safe_multiline(field.text)
                }
                if item:
                    instances.append(item)
            continue
        alert[name] = _safe_multiline(child.text)
    if instances:
        alert["instances"] = instances
    return alert


def _append_zap_alert(
    alert: dict[str, Any],
    row_number: int,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
) -> None:
    instances = alert.get("instances")
    url = alert.get("url")
    param = alert.get("param")
    evidence = alert.get("evidence")
    if isinstance(instances, list) and instances:
        first = instances[0]
        if isinstance(first, dict):
            url = first.get("uri") or first.get("url") or url
            param = first.get("param") or param
            evidence = first.get("evidence") or evidence
    entity = _entity_from_target(url, row_number, state, {"adapter": "zap"})
    if entity:
        entities.append(entity)
    finding = _make_finding(
        row_number=row_number,
        tool_root="zap",
        title=alert.get("alert") or alert.get("name") or alert.get("pluginid"),
        severity=_zap_severity(alert),
        affected_entity=entity,
        subject=url or alert.get("pluginid"),
        description=alert.get("desc") or alert.get("description"),
        remediation=alert.get("solution"),
        evidence=evidence or param,
        external_id=alert.get("pluginid"),
        references=_split_references(alert.get("reference")),
        source_detail={"adapter": "zap", "confidence": alert.get("confidence"), "param": param},
    )
    if finding:
        findings.append(finding)


def _parse_burp_xml(
    payload: bytes,
    state: _ParseState,
    entities: list[ImportEntity],
    findings: list[ImportFinding],
) -> None:
    for elem in _iter_xml_target_elements(payload, state, {"issue"}):
        row_number = state.next_row()
        issue = {}
        for child in list(elem):
            name = _local_name(child.tag)
            issue[name] = _descendant_text(child) if name == "requestresponse" else _safe_multiline(child.text)
        host = issue.get("host")
        path = issue.get("path")
        target = host
        if host and path and host.startswith(("http://", "https://")):
            target = host.rstrip("/") + "/" + path.lstrip("/")
        entity = _entity_from_target(target, row_number, state, {"adapter": "burp"})
        if entity:
            entities.append(entity)
        finding = _make_finding(
            row_number=row_number,
            tool_root="burp",
            title=issue.get("name") or issue.get("type"),
            severity=issue.get("severity"),
            affected_entity=entity,
            subject=target or issue.get("serialnumber") or issue.get("type"),
            description=issue.get("issuedetail") or issue.get("background"),
            remediation=issue.get("remediationdetail"),
            evidence=issue.get("requestresponse") or issue.get("issuedetail"),
            external_id=issue.get("serialnumber") or issue.get("type"),
            references=_split_references(issue.get("references")),
            source_detail={"adapter": "burp", "confidence": issue.get("confidence")},
        )
        if finding:
            findings.append(finding)
