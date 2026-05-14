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
    for line in records:
        parsed = _parse_txt_record(str(line or ""))
        if parsed["asn"]:
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
    if len(parts) < 6:
        return _empty_payload()
    return {
        "asn": parts[0],
        "prefix": parts[1],
        "cc": parts[2],
        "registry": parts[3],
        "allocated": parts[4],
        "name": " | ".join(parts[5:]).strip(),
    }


def _empty_payload() -> dict[str, str]:
    return {"asn": "", "prefix": "", "cc": "", "registry": "", "allocated": "", "name": ""}
