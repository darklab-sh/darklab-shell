"""Scanner port entity helpers for output signal classification."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import re

from core.output_entities import _add_entity
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip, canonical_port

log = logging.getLogger("shell")

_NMAP_OPEN_PORT_ROW_RE = re.compile(
    r"^(?P<port>\d+)/(?P<proto>tcp|udp)\s+open\S*\s+(?P<service>\S+)(?:\s+(?P<version>.*\S))?\s*$",
    re.I,
)

def _nmap_target_host(value: str) -> str:
    token = str(value or "").strip().split(maxsplit=1)[0] if str(value or "").strip() else ""
    if token.startswith("[") and "]" in token:
        return token[1:token.index("]")]
    if token.count(":") == 1:
        host, port = token.rsplit(":", 1)
        if port.isdigit():
            return host
    return token


def _nmap_target_entities(value: str, source_line: int | None) -> list[dict[str, object]]:
    host = _nmap_target_host(value)
    if not host:
        return []
    try:
        canonical = canonical_ip(host)
    except CanonicalizationError:
        try:
            canonical = canonical_domain(host)
        except CanonicalizationError:
            return []
        return [{
            "type": "domain",
            "value": host,
            "canonical_value": canonical,
            "confidence": "medium",
            **({"source_line": source_line} if source_line is not None else {}),
        }]
    return [{
        "type": "ip",
        "value": host,
        "canonical_value": canonical,
        "confidence": "high",
        **({"source_line": source_line} if source_line is not None else {}),
    }]


def _host_entity_type_and_canonical(host: str) -> tuple[str, str] | None:
    raw_host = str(host or "").strip().strip("[]")
    if not raw_host:
        return None
    try:
        return "ip", canonical_ip(raw_host)
    except CanonicalizationError:
        try:
            return "domain", canonical_domain(raw_host)
        except CanonicalizationError:
            return None


def _port_entity_value(host_canonical: str, port: object, proto: object = "tcp") -> str:
    host_part = f"[{host_canonical}]" if ":" in str(host_canonical or "") else str(host_canonical or "")
    return f"{host_part}:{str(port or '').strip()}/{str(proto or 'tcp').strip().lower()}"


def _port_skip_host_context(host: object) -> dict[str, object]:
    raw_host = str(host or "").strip().strip("[]")
    if not raw_host:
        return {"host_kind": "empty", "host_hash": ""}
    try:
        ipaddress.ip_address(raw_host)
        host_kind = "ip_literal"
    except ValueError:
        host_kind = "domain_like" if "." in raw_host else "other"
    host_hash = hashlib.sha256(raw_host.lower().encode("utf-8", "replace")).hexdigest()[:12]
    return {"host_kind": host_kind, "host_hash": host_hash}


def _log_port_entity_skipped(
    scanner_root: str,
    source_line: int | None,
    reason: str,
    *,
    host: object,
    port: object,
    proto: object,
) -> None:
    if not scanner_root:
        return
    log.debug(
        "OUTPUT_SIGNAL_PORT_ENTITY_SKIPPED",
        extra={
            "command_root": scanner_root,
            "line_index": source_line if source_line is not None else -1,
            "reason": reason,
            "port": str(port or "").strip()[:16],
            "proto": str(proto or "tcp").strip().lower()[:16],
            **_port_skip_host_context(host),
        },
    )


def _port_entities_for_host(
    host: str,
    port: object,
    proto: object,
    source_line: int | None,
    *,
    service: str = "",
    version: str = "",
    banner: str = "",
    scanner_root: str = "",
) -> list[dict[str, object]]:
    host_identity = _host_entity_type_and_canonical(host)
    if host_identity is None:
        _log_port_entity_skipped(scanner_root, source_line, "invalid_host", host=host, port=port, proto=proto)
        return []
    host_type, host_canonical = host_identity
    raw_value = _port_entity_value(host_canonical, port, proto)
    try:
        port_canonical = canonical_port(raw_value)
    except CanonicalizationError:
        _log_port_entity_skipped(scanner_root, source_line, "invalid_port", host=host, port=port, proto=proto)
        return []
    entities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    _add_entity(
        entities,
        seen,
        entity_type=host_type,
        value=str(host or "").strip(),
        canonical_value=host_canonical,
        source_line=source_line,
    )
    attributes = {
        key: value
        for key, value in {
            "service": str(service or "").strip(),
            "version": str(version or "").strip(),
            "banner": str(banner or "").strip(),
        }.items()
        if value
    }
    _add_entity(
        entities,
        seen,
        entity_type="port",
        value=raw_value,
        canonical_value=port_canonical,
        source_line=source_line,
        attributes=attributes,
    )
    return entities


def _nc_bracket_entity_host(display_host: object, bracket_host: object) -> str:
    display = str(display_host or "").strip()
    if display.lower() not in {"unknown", "(unknown)"} and _host_entity_type_and_canonical(display) is not None:
        return display
    return str(bracket_host or "").strip()


def _nmap_port_entities(scan_target: str | None, port_line: str, source_line: int | None) -> list[dict[str, object]]:
    target = str(scan_target or "").strip()
    if not target:
        return []
    match = _NMAP_OPEN_PORT_ROW_RE.match(str(port_line or "").strip())
    if not match:
        return []
    host = _nmap_target_host(target)
    return _port_entities_for_host(
        host,
        match.group("port"),
        match.group("proto"),
        source_line,
        service=match.group("service") or "",
        version=match.group("version") or "",
        scanner_root="nmap",
    )


def _nmap_service_context(scan_target: str | None, port_line: str) -> str:
    target = str(scan_target or "").strip()
    if not target:
        return ""
    match = _NMAP_OPEN_PORT_ROW_RE.match(str(port_line or "").strip())
    if not match:
        return ""
    service = str(match.group("service") or "").strip()
    version = str(match.group("version") or "").strip()
    if service.lower() in {"netbios-ssn", "microsoft-ds"} and version.lower().startswith("samba"):
        service = "samba"
    if not service:
        return ""
    host = target if ":" not in target or target.startswith("[") else f"[{target}]"
    return f"{host}:{match.group('port')} {service.lower()}"

