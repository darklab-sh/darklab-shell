"""Have I Been Pwned Pwned Passwords provider normalization."""

from __future__ import annotations

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_hash
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_hash_payload(raw: str, sha1_hash: str) -> dict[str, object]:
    prefix = sha1_hash[:5].upper()
    suffix = sha1_hash[5:].upper()
    count = 0
    for line in str(raw or "").splitlines():
        candidate, _, raw_count = line.partition(":")
        if candidate.strip().upper() != suffix:
            continue
        try:
            count = int(raw_count.strip())
        except ValueError:
            count = 0
        break
    return {
        "pwned": count > 0,
        "count": count,
        "prefix": prefix,
    }


class HibpPwnedPasswordsProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("hibp")
        super().__init__(
            name="hibp",
            secret_env="",
            cache_scopes=definition.cache_scopes if definition else {"hash": "password"},
            **kwargs,
        )

    def lookup_hash(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del session_token, run_id
        if not self.client:
            raise ProviderClientUnavailable("HIBP Pwned Passwords client is not configured")
        canonical = canonical_hash(value)
        algorithm, sha1_hash = canonical.split(":", 1)
        if algorithm != "sha1":
            payload = response_with_provider("hash", self.name, {"pwned": False, "count": 0, "prefix": ""})
            return IntelResult(self.name, "hash", canonical, payload)
        raw = self.client.lookup_sha1_prefix(sha1_hash[:5])
        payload = response_with_provider("hash", self.name, normalize_hash_payload(raw, sha1_hash))
        return IntelResult(self.name, "hash", canonical, payload, http_status=getattr(self.client, "last_status", None))
