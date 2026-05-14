"""urlscan.io provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_domain, canonical_url
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_search_payload(raw: dict[str, Any]) -> dict[str, Any]:
    raw_results = raw.get("results")
    results = []
    if isinstance(raw_results, list):
        for item in raw_results[:8]:
            if not isinstance(item, dict):
                continue
            page = item.get("page")
            task = item.get("task")
            verdicts = item.get("verdicts")
            page_obj = page if isinstance(page, dict) else {}
            task_obj = task if isinstance(task, dict) else {}
            verdict_obj = verdicts if isinstance(verdicts, dict) else {}
            overall_obj = verdict_obj.get("overall")
            overall = overall_obj if isinstance(overall_obj, dict) else {}
            results.append({
                "url": str(page_obj.get("url") or task_obj.get("url") or ""),
                "domain": str(page_obj.get("domain") or ""),
                "ip": str(page_obj.get("ip") or ""),
                "scan_id": str(task_obj.get("uuid") or item.get("_id") or ""),
                "time": str(task_obj.get("time") or item.get("indexedAt") or ""),
                "malicious": bool(overall.get("malicious")),
                "score": overall.get("score"),
            })
    total = raw.get("total")
    count = _int_or_len(total, results)
    return {"result_count": count, "results": results, "has_more": bool(raw.get("has_more"))}


class UrlscanProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("urlscan")
        super().__init__(
            name="urlscan",
            secret_env=definition.secret_env if definition else "URLSCAN_API_KEY",
            cache_scopes=definition.cache_scopes if definition else {"domain": "search", "url": "search"},
            **kwargs,
        )

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("urlscan.io client is not configured")
        canonical = canonical_domain(value)
        raw = self.client.search(f"domain:{canonical}", api_key=api_key)
        payload = response_with_provider("domain", self.name, normalize_search_payload(raw))
        return IntelResult(self.name, "domain", canonical, payload, http_status=getattr(self.client, "last_status", None))

    def lookup_url(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("urlscan.io client is not configured")
        canonical = canonical_url(value)
        raw = self.client.search(f'page.url:"{canonical}"', api_key=api_key)
        payload = response_with_provider("url", self.name, normalize_search_payload(raw))
        return IntelResult(self.name, "url", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _int_or_len(value: object, rows: list[dict[str, Any]]) -> int:
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
