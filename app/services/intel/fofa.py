"""FOFA provider normalization."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from services.intel.base import IntelResult, Provider, ProviderApiError, ProviderClientUnavailable, ProviderMissingSecret
from services.intel.canonical import canonical_domain, canonical_ip, canonical_url
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_search_payload(raw: dict[str, Any]) -> dict[str, Any]:
    rows = raw.get("results")
    raw_rows = rows if isinstance(rows, list) else []
    results = [_normalize_row(row) for row in raw_rows[:10]]
    filtered = [row for row in results if row]
    return {
        "result_count": _int_value(raw.get("size") or raw.get("total") or len(filtered)),
        "results": filtered,
        "has_more": bool(raw.get("next_page") or raw.get("has_more") or len(raw_rows) > len(filtered)),
    }


class FofaProvider(Provider):
    def __init__(self, **kwargs: Any):
        definition = provider_definition("fofa")
        super().__init__(
            name="fofa",
            secret_env=definition.secret_env if definition else "FOFA_KEY",
            secret_env_aliases=definition.secret_env_aliases
            if definition
            else ("FOFA_API_KEY", "FOFA_APIKEY", "FOFA_TOKEN"),
            required_secret_envs=definition.required_secret_envs if definition else ("FOFA_EMAIL",),
            cache_scopes=definition.cache_scopes if definition else {"ip": "search", "domain": "search", "url": "search"},
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        canonical = canonical_ip(value)
        return self._lookup("ip", canonical, f'ip="{canonical}"', session_token=session_token, run_id=run_id)

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        canonical = canonical_domain(value)
        return self._lookup("domain", canonical, f'domain="{canonical}"', session_token=session_token, run_id=run_id)

    def lookup_url(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        canonical = canonical_url(value)
        host = urlsplit(canonical).hostname or canonical
        return self._lookup("url", canonical, f'host="{host}"', session_token=session_token, run_id=run_id)

    def _lookup(self, entity_type: str, canonical: str, query: str, *, session_token: str, run_id: str) -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        email = self.secret_getter(session_token, "FOFA_EMAIL") or ""
        if not email:
            raise ProviderMissingSecret("FOFA_EMAIL is not configured")
        if not self.client:
            raise ProviderClientUnavailable("FOFA client is not configured")
        raw = self.client.search(query, email=email, api_key=api_key, size=10)
        if raw.get("error") is True:
            raise ProviderApiError(
                str(raw.get("errmsg") or "FOFA request failed"),
                status=getattr(self.client, "last_status", None),
            )
        payload = response_with_provider(entity_type, self.name, normalize_search_payload(raw))
        return IntelResult(self.name, entity_type, canonical, payload, http_status=getattr(self.client, "last_status", None))


def _normalize_row(row: object) -> dict[str, Any]:
    values = row if isinstance(row, list) else []
    keys = ("host", "ip", "port", "protocol", "title", "server", "country")
    mapped = {key: str(values[index] or "").strip() for index, key in enumerate(keys) if index < len(values)}
    port = _int_value(mapped.get("port"))
    return {
        "host": mapped.get("host", ""),
        "ip": mapped.get("ip", ""),
        "port": port,
        "protocol": mapped.get("protocol", ""),
        "title": mapped.get("title", ""),
        "server": mapped.get("server", ""),
        "country": mapped.get("country", ""),
    }


def _int_value(value: object) -> int:
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return 0
