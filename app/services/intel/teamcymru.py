# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Team Cymru IP-to-ASN provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_ip
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_ip_payload(raw: dict[str, Any]) -> dict[str, Any]:
    records = raw.get("records")
    if not isinstance(records, list):
        return _empty_payload()
    names_by_asn = _asn_names_by_asn(raw.get("asn_records"))
    for line in records:
        parsed = _parse_txt_record(str(line or ""))
        if parsed["asn"]:
            if not parsed["name"]:
                parsed["name"] = _name_for_origin_asn(parsed["asn"], names_by_asn)
            return parsed
    return _empty_payload()


class TeamCymruProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("teamcymru")
        super().__init__(
            name="teamcymru",
            secret_env="",
            cache_scopes=definition.cache_scopes if definition else {"ip": "ip"},
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del session_token, run_id
        if not self.client:
            raise ProviderClientUnavailable("Team Cymru client is not configured")
        canonical = canonical_ip(value)
        raw = self.client.lookup_ip(canonical)
        payload = response_with_provider("ip", self.name, normalize_ip_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _parse_txt_record(value: str) -> dict[str, str]:
    cleaned = value.strip().strip('"')
    parts = [part.strip().strip('"') for part in cleaned.split("|")]
    if len(parts) < 5:
        return _empty_payload()
    return {
        "asn": parts[0],
        "prefix": parts[1],
        "cc": parts[2],
        "registry": parts[3],
        "allocated": parts[4],
        "name": " | ".join(parts[5:]).strip() if len(parts) > 5 else "",
    }


def _parse_asn_txt_record(value: str) -> tuple[str, str] | None:
    cleaned = value.strip().strip('"')
    parts = [part.strip().strip('"') for part in cleaned.split("|")]
    if len(parts) < 5:
        return None
    asn = parts[0].upper().removeprefix("AS").strip()
    name = " | ".join(parts[4:]).strip()
    if not asn or not name:
        return None
    return asn, name


def _asn_names_by_asn(records: Any) -> dict[str, str]:
    if not isinstance(records, list):
        return {}
    names = {}
    for record in records:
        parsed = _parse_asn_txt_record(str(record or ""))
        if parsed:
            names[parsed[0]] = parsed[1]
    return names


def _name_for_origin_asn(value: str, names_by_asn: dict[str, str]) -> str:
    names = []
    seen = set()
    for token in value.replace(",", " ").split():
        asn = token.upper().removeprefix("AS").strip()
        name = names_by_asn.get(asn)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return ", ".join(names)


def _empty_payload() -> dict[str, str]:
    return {"asn": "", "prefix": "", "cc": "", "registry": "", "allocated": "", "name": ""}
