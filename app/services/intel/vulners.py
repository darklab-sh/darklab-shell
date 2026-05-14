"""Vulners CVE provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_cve
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_cve_payload(raw: dict[str, Any]) -> dict[str, Any]:
    document = _first_document(raw)
    exploits = _exploit_rows(raw.get("exploits"))
    return {
        "title": str(document.get("title") or document.get("id") or ""),
        "severity": str(document.get("severity") or document.get("cvss3Severity") or document.get("cvssSeverity") or ""),
        "score": _score(document),
        "published": str(document.get("published") or ""),
        "modified": str(document.get("modified") or ""),
        "exploit_count": _int_or_len(raw.get("exploit_count"), exploits),
        "exploits": exploits,
        "references": _references(document),
    }


class VulnersProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("vulners")
        super().__init__(
            name="vulners",
            secret_env=definition.secret_env if definition else "VULNERS_API_KEY",
            cache_scopes=definition.cache_scopes if definition else {"cve": "cve"},
            **kwargs,
        )

    def lookup_cve(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("Vulners client is not configured")
        canonical = canonical_cve(value)
        raw = self.client.lookup_cve(canonical, api_key=api_key)
        raw["exploits"] = _search_documents(self.client.lookup_exploits(canonical, api_key=api_key))
        raw["exploit_count"] = len(raw["exploits"])
        payload = response_with_provider("cve", self.name, normalize_cve_payload(raw))
        return IntelResult(self.name, "cve", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _first_document(raw: dict[str, Any]) -> dict[str, Any]:
    documents = _search_documents(raw)
    return documents[0] if documents else {}


def _search_documents(raw: dict[str, Any]) -> list[dict[str, Any]]:
    data = raw.get("data")
    data_obj = data if isinstance(data, dict) else {}
    search = data_obj.get("search")
    if isinstance(search, list):
        return [item for item in search if isinstance(item, dict)]
    documents = data_obj.get("documents")
    if isinstance(documents, dict):
        return [item for item in documents.values() if isinstance(item, dict)]
    return []


def _score(document: dict[str, Any]) -> float | None:
    for key in ("cvss3Score", "cvssScore", "score"):
        value = document.get(key)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            continue
    return None


def _exploit_rows(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append({
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "href": str(item.get("href") or ""),
            "published": str(item.get("published") or ""),
        })
    return rows[:8]


def _references(document: dict[str, Any]) -> list[str]:
    raw_refs = document.get("references") or document.get("href")
    if isinstance(raw_refs, str):
        return [raw_refs] if raw_refs else []
    if not isinstance(raw_refs, list):
        return []
    return [str(item) for item in raw_refs if str(item).strip()][:8]


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
