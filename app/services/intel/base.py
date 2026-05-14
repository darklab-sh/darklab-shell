"""Base classes and exceptions for external intel providers."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Callable

from services.secrets.storage import get_secret_value_for_env


SecretGetter = Callable[[str, str], str | None]


class IntelProviderError(RuntimeError):
    """Base provider error."""


class ProviderMissingSecret(IntelProviderError):
    """Raised when a provider key is required but missing."""


class ProviderUnsupportedLookup(IntelProviderError):
    """Raised when a provider does not support the requested entity type."""


class ProviderClientUnavailable(IntelProviderError):
    """Raised when a live provider needs an HTTP/CLI client that is absent."""


@dataclass(frozen=True)
class IntelResult:
    provider: str
    entity_type: str
    canonical_value: str
    payload: dict[str, Any]
    http_status: int | None = None
    cache_hit: bool = False


@dataclass
class Provider(ABC):
    name: str
    secret_env: str
    secret_env_aliases: tuple[str, ...] = ()
    secret_getter: SecretGetter = get_secret_value_for_env
    client: Any = None
    cache_scopes: dict[str, str] = field(default_factory=dict)

    def secret_value(self, session_token: str) -> str:
        env_names = (self.secret_env, *self.secret_env_aliases)
        for env_name in env_names:
            value = self.secret_getter(session_token, env_name)
            if value:
                return value
        raise ProviderMissingSecret(f"{' or '.join(env_names)} is not configured")

    def rate_limit(
        self,
        session_token: str,
        *,
        profile: str = "",
        cfg: dict[str, Any] | None = None,
        redis_client=None,
        now: float | None = None,
    ):
        from services.intel.rate_limiter import check_rate_limit

        return check_rate_limit(
            session_token,
            self.name,
            profile=profile,
            cfg=cfg,
            redis_client=redis_client,
            now=now,
        )

    def cache_ttl(self, entity_type: str, *, cfg: dict[str, Any] | None = None) -> int:
        from services.intel.cache import cache_ttl

        scope = self.cache_scopes.get(str(entity_type or "").strip().lower(), entity_type)
        return cache_ttl(self.name, scope, cfg)

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del value, session_token, run_id
        raise ProviderUnsupportedLookup(f"{self.name} does not support IP lookups")

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del value, session_token, run_id
        raise ProviderUnsupportedLookup(f"{self.name} does not support domain lookups")

    def lookup_hash(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del value, session_token, run_id
        raise ProviderUnsupportedLookup(f"{self.name} does not support hash lookups")

    def lookup_cve(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del value, session_token, run_id
        raise ProviderUnsupportedLookup(f"{self.name} does not support CVE lookups")
