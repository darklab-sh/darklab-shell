"""URLhaus provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_domain, canonical_hash, canonical_ip, canonical_url
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_url_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_status": str(raw.get("query_status") or ""),
        "status": str(raw.get("url_status") or ""),
        "threat": str(raw.get("threat") or ""),
        "host": str(raw.get("host") or ""),
        "payloads": _payload_rows(raw.get("payloads")),
        "tags": _string_list(raw.get("tags")),
    }


def normalize_host_payload(raw: dict[str, Any]) -> dict[str, Any]:
    urls = _url_rows(raw.get("urls"))
    payloads = _payload_rows(raw.get("payloads"))
    return {
        "query_status": str(raw.get("query_status") or ""),
        "url_count": _int_or_len(raw.get("url_count"), urls),
        "payload_count": _int_or_len(raw.get("payload_count"), payloads),
        "urls": urls,
        "payloads": payloads,
    }


def normalize_hash_payload(raw: dict[str, Any]) -> dict[str, Any]:
    urls = _url_rows(raw.get("urls"))
    payloads = _payload_rows(raw.get("payloads"))
    return {
        "query_status": str(raw.get("query_status") or ""),
        "url_count": _int_or_len(raw.get("url_count"), urls),
        "payloads": payloads,
        "signature": str(raw.get("signature") or raw.get("malware") or ""),
        "file_type": str(raw.get("file_type") or ""),
    }


class UrlhausProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("urlhaus")
        super().__init__(
            name="urlhaus",
            secret_env=definition.secret_env if definition else "URLHAUS_AUTH_KEY",
            cache_scopes=definition.cache_scopes if definition else {
                "ip": "host",
                "domain": "host",
                "hash": "payload",
                "url": "url",
            },
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        return self._lookup_host(canonical_ip(value), "ip", session_token=session_token)

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        return self._lookup_host(canonical_domain(value), "domain", session_token=session_token)

    def lookup_hash(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("URLhaus client is not configured")
        canonical = canonical_hash(value)
        raw = self.client.lookup_payload(canonical.split(":", 1)[1], api_key=api_key)
        payload = response_with_provider("hash", self.name, normalize_hash_payload(raw))
        return IntelResult(self.name, "hash", canonical, payload, http_status=getattr(self.client, "last_status", None))

    def lookup_url(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("URLhaus client is not configured")
        canonical = canonical_url(value)
        raw = self.client.lookup_url(canonical, api_key=api_key)
        payload = response_with_provider("url", self.name, normalize_url_payload(raw))
        return IntelResult(self.name, "url", canonical, payload, http_status=getattr(self.client, "last_status", None))

    def _lookup_host(self, canonical: str, entity_type: str, *, session_token: str) -> IntelResult:
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("URLhaus client is not configured")
        raw = self.client.lookup_host(canonical, api_key=api_key)
        payload = response_with_provider(entity_type, self.name, normalize_host_payload(raw))
        return IntelResult(self.name, entity_type, canonical, payload, http_status=getattr(self.client, "last_status", None))


def _url_rows(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append({
            "url": str(item.get("url") or ""),
            "status": str(item.get("url_status") or item.get("status") or ""),
            "date_added": str(item.get("date_added") or item.get("dateadded") or ""),
            "threat": str(item.get("threat") or ""),
        })
    return rows[:8]


def _payload_rows(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append({
            "sha256": str(item.get("sha256_hash") or ""),
            "file_type": str(item.get("file_type") or ""),
            "signature": str(item.get("signature") or ""),
            "first_seen": str(item.get("firstseen") or item.get("first_seen") or ""),
        })
    return rows[:8]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()][:12]


def _int_or_len(value: object, rows: list[dict[str, str]]) -> int:
    if isinstance(value, bool):
        return len(rows)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not isinstance(value, str):
        return len(rows)
    try:
        return int(value)
    except ValueError:
        return len(rows)
