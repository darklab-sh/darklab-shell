"""crt.sh provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_domain
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_domain_payload(raw: list[Any]) -> dict[str, Any]:
    names: list[str] = []
    issuers: list[str] = []
    first_seen = ""
    last_seen = ""
    row_count = 0
    for row in raw:
        if not isinstance(row, dict):
            continue
        row_count += 1
        for name in str(row.get("name_value") or "").splitlines():
            normalized = name.strip().lower().lstrip("*.").rstrip(".")
            if normalized and normalized not in names:
                names.append(normalized)
        issuer = str(row.get("issuer_name") or "").strip()
        if issuer and issuer not in issuers:
            issuers.append(issuer)
        not_before = str(row.get("not_before") or "").strip()
        if not_before:
            first_seen = min(first_seen, not_before) if first_seen else not_before
            last_seen = max(last_seen, not_before) if last_seen else not_before
    return {
        "certificate_count": row_count,
        "names": names[:50],
        "issuers": issuers[:12],
        "first_seen": first_seen,
        "last_seen": last_seen,
    }


class CrtshProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("crtsh")
        super().__init__(
            name="crtsh",
            secret_env="",
            cache_scopes=definition.cache_scopes if definition else {"domain": "domain"},
            **kwargs,
        )

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del session_token, run_id
        if not self.client:
            raise ProviderClientUnavailable("crt.sh client is not configured")
        canonical = canonical_domain(value)
        raw = self.client.lookup_domain(canonical)
        payload = response_with_provider("domain", self.name, normalize_domain_payload(raw))
        return IntelResult(self.name, "domain", canonical, payload, http_status=getattr(self.client, "last_status", None))
