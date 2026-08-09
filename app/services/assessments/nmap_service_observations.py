# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded informational service observations from structured Nmap XML."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from services.assessments.nmap_script_evidence_catalog import (
    INFORMATIONAL_SCRIPT_EVIDENCE,
)
from services.intel.canonical import (
    CanonicalizationError,
    canonical_domain,
    canonical_ip,
    canonical_port,
)


NMAP_SERVICE_XML_PARSER_VERSION = "nmap-xml-service-evidence-v1"
NMAP_SERVICE_XML_MAX_BYTES = 5 * 1024 * 1024
NMAP_SERVICE_XML_MAX_ELEMENTS = 50_000
NMAP_SERVICE_XML_MAX_OBSERVATIONS = 100
NMAP_SERVICE_XML_MAX_FIELDS = 128
NMAP_SERVICE_XML_MAX_FIELD_DEPTH = 8
NMAP_SERVICE_XML_MAX_VALUE_LENGTH = 512


def parse_nmap_xml_service_observations(
    payload: bytes | str,
    *,
    source_run_id: str,
    observed_at: str = "",
) -> dict[str, Any]:
    """Return exact structured NSE facts without interpreting them as findings."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    run_id = _text(source_run_id, 128)
    if not isinstance(raw, bytes) or not run_id or not raw or len(raw) > NMAP_SERVICE_XML_MAX_BYTES:
        return _empty()
    try:
        root = SafeElementTree.fromstring(raw)
    except (SafeElementTree.ParseError, DefusedXmlException, ValueError):
        return _empty()
    if root.tag != "nmaprun" or sum(1 for _ in root.iter()) > NMAP_SERVICE_XML_MAX_ELEMENTS:
        return _empty()
    tool_version = _text(root.get("version"), 128)
    timestamp = _observed_at(root, observed_at)
    if not tool_version or not timestamp:
        return _empty()

    observations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    truncated = False
    for host in root.findall("host"):
        host_value = _host_value(host)
        if not host_value:
            continue
        for port in host.findall("./ports/port"):
            state = port.find("state")
            target = _port_target(host_value, port)
            if state is None or state.get("state") != "open" or not target:
                continue
            service = port.find("service")
            service_name = _text(service.get("name"), 64) if service is not None else ""
            for script in port.findall("script"):
                script_id = _text(script.get("id"), 64)
                evidence_kind = INFORMATIONAL_SCRIPT_EVIDENCE.get(script_id)
                if not evidence_kind or (target, script_id) in seen:
                    continue
                fields, fields_truncated = _structured_fields(script)
                if not fields:
                    continue
                if len(observations) >= NMAP_SERVICE_XML_MAX_OBSERVATIONS:
                    truncated = True
                    break
                seen.add((target, script_id))
                observations.append({
                    "observation_id": _observation_id(run_id, target, script_id),
                    "target": target,
                    "service": service_name,
                    "script_id": script_id,
                    "evidence_kind": evidence_kind,
                    "classification": "informational",
                    "fields": fields,
                    "fields_truncated": fields_truncated,
                })
                truncated = truncated or fields_truncated
                if len(observations) >= NMAP_SERVICE_XML_MAX_OBSERVATIONS:
                    truncated = True
                    break
            if len(observations) >= NMAP_SERVICE_XML_MAX_OBSERVATIONS:
                break
        if len(observations) >= NMAP_SERVICE_XML_MAX_OBSERVATIONS:
            break
    return {
        "source": "nmap_xml_service_evidence",
        "source_run_id": run_id,
        "tool_version": tool_version,
        "parser_version": NMAP_SERVICE_XML_PARSER_VERSION,
        "observed_at": timestamp,
        "observations": observations,
        "truncated": truncated,
    }


def _structured_fields(script: Any) -> tuple[list[dict[str, Any]], bool]:
    fields: list[dict[str, Any]] = []
    state = {"truncated": False, "stop": False}
    for index, child in enumerate(script):
        if child.tag not in {"table", "elem"}:
            continue
        _walk_field(child, (), index, fields, state, 0)
        if state["stop"]:
            break
    return fields, state["truncated"]


def _walk_field(
    node: Any,
    parent_path: tuple[str, ...],
    sibling_index: int,
    fields: list[dict[str, Any]],
    state: dict[str, bool],
    depth: int,
) -> None:
    if depth >= NMAP_SERVICE_XML_MAX_FIELD_DEPTH:
        state["truncated"] = True
        return
    key = _text(node.get("key"), 64)
    segment = key or str(sibling_index)
    path = (*parent_path, segment)
    if node.tag == "elem":
        normalized_value = " ".join(str(node.text or "").split())
        value = normalized_value[:NMAP_SERVICE_XML_MAX_VALUE_LENGTH]
        if value:
            if len(fields) >= NMAP_SERVICE_XML_MAX_FIELDS:
                state.update(truncated=True, stop=True)
                return
            fields.append({"path": list(path), "value": value})
        state["truncated"] = state["truncated"] or len(normalized_value) > NMAP_SERVICE_XML_MAX_VALUE_LENGTH
        return
    for index, child in enumerate(node):
        if child.tag not in {"table", "elem"}:
            continue
        _walk_field(child, path, index, fields, state, depth + 1)
        if state["stop"]:
            return


def _host_value(host: Any) -> str:
    for node in host.findall("address"):
        try:
            return canonical_ip(str(node.get("addr") or ""))
        except CanonicalizationError:
            continue
    for node in host.findall("./hostnames/hostname"):
        try:
            return canonical_domain(str(node.get("name") or ""))
        except CanonicalizationError:
            continue
    return ""


def _port_target(host: str, port: Any) -> str:
    host_part = f"[{host}]" if ":" in host else host
    value = f"{host_part}:{port.get('portid') or ''}/{str(port.get('protocol') or '').lower()}"
    try:
        return canonical_port(value)
    except CanonicalizationError:
        return ""


def _observed_at(root: Any, explicit: str) -> str:
    value = _text(explicit, 64)
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
        return value if parsed.tzinfo is not None else ""
    finished = root.find("./runstats/finished")
    try:
        epoch = int(str(finished.get("time") or "")) if finished is not None else 0
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch > 0 else ""
    except (OverflowError, OSError, ValueError):
        return ""


def _observation_id(run_id: str, target: str, script_id: str) -> str:
    digest = hashlib.sha256(f"{run_id}\x1f{target}\x1f{script_id}".encode()).hexdigest()
    return "obs_" + digest[:32]


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _empty() -> dict[str, Any]:
    return {
        "source": "nmap_xml_service_evidence", "source_run_id": "", "tool_version": "",
        "parser_version": NMAP_SERVICE_XML_PARSER_VERSION, "observed_at": "",
        "observations": [], "truncated": False,
    }


__all__ = ["NMAP_SERVICE_XML_PARSER_VERSION", "parse_nmap_xml_service_observations"]
