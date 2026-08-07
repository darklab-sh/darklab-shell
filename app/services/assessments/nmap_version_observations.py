# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded exact CPE observations from structured Nmap XML."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from services.assessments.cpe_applicability import normalize_observed_cpe
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip, canonical_port


NMAP_XML_PARSER_VERSION = "nmap-xml-cpe-v1"
NMAP_XML_MAX_BYTES = 5 * 1024 * 1024
NMAP_XML_MAX_ELEMENTS = 50_000
NMAP_XML_MAX_OBSERVATIONS = 50
_CPE_COMPONENT_RE = re.compile(r"^[a-z0-9._-]{1,128}$", re.I)


def parse_nmap_xml_cpe_observations(
    payload: bytes | str,
    *,
    source_run_id: str,
    observed_at: str = "",
) -> dict[str, Any]:
    """Return exact, versioned Nmap service CPE observations without side effects."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    run_id = _text(source_run_id, 128)
    if not isinstance(raw, bytes) or not run_id or not raw or len(raw) > NMAP_XML_MAX_BYTES:
        return _empty()
    try:
        root = SafeElementTree.fromstring(raw)
    except (SafeElementTree.ParseError, DefusedXmlException, ValueError):
        return _empty()
    if root.tag != "nmaprun" or sum(1 for _ in root.iter()) > NMAP_XML_MAX_ELEMENTS:
        return _empty()
    tool_version = _text(root.get("version"), 128)
    timestamp = _observed_at(root, observed_at)
    if not tool_version or not timestamp:
        return _empty()
    observations: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    truncated = False
    for host in root.findall("host"):
        host_value = _host_value(host)
        if not host_value:
            continue
        for port in host.findall("./ports/port"):
            target = _port_target(host_value, port)
            service = port.find("service")
            state = port.find("state")
            if not target or service is None or state is None or state.get("state") != "open":
                continue
            for cpe_node in service.findall("cpe"):
                cpe = _normalize_nmap_cpe(cpe_node.text)
                if not cpe or (target, cpe) in seen:
                    continue
                if len(observations) >= NMAP_XML_MAX_OBSERVATIONS:
                    truncated = True
                    break
                seen.add((target, cpe))
                record = normalize_observed_cpe(cpe)
                if record is None:
                    continue
                observations.append({
                    "observation_id": _observation_id(run_id, target, cpe),
                    "target": target,
                    "cpe": cpe,
                    "version": str(record["version"]),
                })
            if truncated:
                break
        if truncated:
            break
    return {
        "source": "nmap_xml",
        "source_run_id": run_id,
        "tool_version": tool_version,
        "parser_version": NMAP_XML_PARSER_VERSION,
        "observed_at": timestamp,
        "observations": observations,
        "truncated": truncated,
    }


def _host_value(host: Any) -> str:
    for node in host.findall("address"):
        value = str(node.get("addr") or "")
        try:
            return canonical_ip(value)
        except CanonicalizationError:
            continue
    for node in host.findall("./hostnames/hostname"):
        value = str(node.get("name") or "")
        try:
            return canonical_domain(value)
        except CanonicalizationError:
            continue
    return ""


def _port_target(host: str, port: Any) -> str:
    port_id = str(port.get("portid") or "")
    protocol = str(port.get("protocol") or "").lower()
    host_part = f"[{host}]" if ":" in host else host
    try:
        return canonical_port(f"{host_part}:{port_id}/{protocol}")
    except CanonicalizationError:
        return ""


def _normalize_nmap_cpe(value: Any) -> str:
    raw = str(value or "").strip()
    if normalize_observed_cpe(raw) is not None:
        return raw
    if not raw.startswith("cpe:/"):
        return ""
    components = raw[5:].split(":")
    if not 4 <= len(components) <= 7 or components[0] not in {"a", "h", "o"}:
        return ""
    if any(not _CPE_COMPONENT_RE.fullmatch(component) for component in components[:4]):
        return ""
    if any(component and not _CPE_COMPONENT_RE.fullmatch(component) for component in components[4:]):
        return ""
    legacy = components + ["*"] * (7 - len(components))
    fields = [*legacy, "*", "*", "*", "*"]
    candidate = "cpe:2.3:" + ":".join(component or "*" for component in fields)
    return candidate if normalize_observed_cpe(candidate) is not None else ""


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


def _observation_id(run_id: str, target: str, cpe: str) -> str:
    digest = hashlib.sha256(f"{run_id}\x1f{target}\x1f{cpe}".encode()).hexdigest()
    return "obs_" + digest[:32]


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _empty() -> dict[str, Any]:
    return {
        "source": "nmap_xml", "source_run_id": "", "tool_version": "",
        "parser_version": NMAP_XML_PARSER_VERSION, "observed_at": "",
        "observations": [], "truncated": False,
    }


__all__ = ["NMAP_XML_PARSER_VERSION", "parse_nmap_xml_cpe_observations"]
