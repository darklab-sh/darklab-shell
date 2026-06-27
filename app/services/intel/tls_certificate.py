"""Live TLS certificate provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_domain
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_domain_payload(raw: dict[str, Any]) -> dict[str, Any]:
    names = [str(item or "").strip().lower() for item in raw.get("names", []) if str(item or "").strip()]
    issuer = str(raw.get("issuer") or "").strip()
    not_before = str(raw.get("not_before") or "").strip()
    not_after = str(raw.get("not_after") or "").strip()
    fingerprint = str(raw.get("fingerprint_sha256") or "").strip()
    certificate = {
        "id": fingerprint[:16],
        "names": names[:12],
        "issuer": issuer,
        "subject": str(raw.get("subject") or "").strip(),
        "not_before": not_before,
        "not_after": not_after,
        "fingerprint_sha256": fingerprint,
    }
    return {
        "certificate_count": 1 if not_after or fingerprint else 0,
        "names": names[:50],
        "issuers": [issuer] if issuer else [],
        "first_seen": not_before,
        "last_seen": not_before,
        "latest_expiry": not_after,
        "host": str(raw.get("host") or "").strip(),
        "port": int(raw.get("port") or 443),
        "subject": certificate["subject"],
        "fingerprint_sha256": fingerprint,
        "certificates": [certificate] if certificate["not_after"] or certificate["fingerprint_sha256"] else [],
    }


class TlsCertificateProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("tls_certificate")
        super().__init__(
            name="tls_certificate",
            secret_env="",
            cache_scopes=definition.cache_scopes if definition else {"domain": "domain"},
            **kwargs,
        )

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del session_token, run_id
        if not self.client:
            raise ProviderClientUnavailable("TLS certificate client is not configured")
        canonical = canonical_domain(value)
        raw = self.client.lookup_domain(canonical)
        payload = response_with_provider("domain", self.name, normalize_domain_payload(raw))
        return IntelResult(self.name, "domain", canonical, payload, http_status=getattr(self.client, "last_status", None))
