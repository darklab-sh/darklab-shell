"""Provider orchestration for app-native intel lookups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from config import CFG
from core import process
from services.intel import audit, cache
from services.intel.base import (
    IntelProviderError,
    IntelResult,
    Provider,
    ProviderApiError,
    ProviderClientUnavailable,
    ProviderMissingSecret,
)
from services.intel.canonical import canonical_entity
from services.intel.clients import (
    AbuseIpdbApiClient,
    CensysApiClient,
    CrtshApiClient,
    GreyNoiseApiClient,
    HibpPwnedPasswordsClient,
    NvdApiClient,
    OtxApiClient,
    RouteViewsApiClient,
    SecurityTrailsApiClient,
    ShodanApiClient,
    TeamCymruDnsClient,
    ThreatFoxApiClient,
    UrlhausApiClient,
    UrlscanApiClient,
    VirusTotalApiClient,
    VulnersApiClient,
)
from services.intel.abuseipdb import AbuseIpdbProvider
from services.intel.censys import CensysProvider
from services.intel.crtsh import CrtshProvider
from services.intel.greynoise import GreyNoiseProvider
from services.intel.hibp import HibpPwnedPasswordsProvider
from services.intel.nvd import NvdProvider
from services.intel.otx import OtxProvider
from services.intel.routeviews import RouteViewsProvider
from services.intel.securitytrails import SecurityTrailsProvider
from services.intel.registry import provider_label, providers_for_entity_type
from services.intel.shodan import ShodanProvider
from services.intel.teamcymru import TeamCymruProvider
from services.intel.threatfox import ThreatFoxProvider
from services.intel.urlhaus import UrlhausProvider
from services.intel.urlscan import UrlscanProvider
from services.intel.virustotal import VirusTotalProvider
from services.intel.vulners import VulnersProvider


ProviderFactory = Callable[[], Provider]


@dataclass(frozen=True)
class ProviderLookup:
    provider: str
    result: IntelResult | None = None
    status: str = "ok"
    message: str = ""
    retry_after_seconds: int = 0
    reset_at: float | None = None


@dataclass(frozen=True)
class IntelLookupResult:
    entity_type: str
    canonical_value: str
    providers: list[ProviderLookup]

    @property
    def configured_count(self) -> int:
        return sum(1 for item in self.providers if item.status != "missing_secret")

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.providers if item.result is not None)


def default_provider_factories(entity_type: str, canonical_value: str = "") -> list[ProviderFactory]:
    factories = []
    for definition in providers_for_entity_type(entity_type):
        if definition.id == "hibp" and not str(canonical_value or "").startswith("sha1:"):
            continue
        factory = _provider_factory(definition.id)
        if factory:
            factories.append(factory)
    return factories


def _provider_factory(provider_id: str) -> ProviderFactory | None:
    if provider_id == "shodan":
        return lambda: ShodanProvider(client=ShodanApiClient())
    if provider_id == "censys":
        return lambda: CensysProvider(client=CensysApiClient())
    if provider_id == "greynoise":
        return lambda: GreyNoiseProvider(client=GreyNoiseApiClient())
    if provider_id == "virustotal":
        return lambda: VirusTotalProvider(client=VirusTotalApiClient())
    if provider_id == "otx":
        return lambda: OtxProvider(client=OtxApiClient())
    if provider_id == "abuseipdb":
        return lambda: AbuseIpdbProvider(client=AbuseIpdbApiClient())
    if provider_id == "teamcymru":
        return lambda: TeamCymruProvider(client=TeamCymruDnsClient())
    if provider_id == "crtsh":
        return lambda: CrtshProvider(client=CrtshApiClient())
    if provider_id == "hibp":
        return lambda: HibpPwnedPasswordsProvider(client=HibpPwnedPasswordsClient())
    if provider_id == "nvd":
        return lambda: NvdProvider(client=NvdApiClient())
    if provider_id == "vulners":
        return lambda: VulnersProvider(client=VulnersApiClient())
    if provider_id == "urlscan":
        return lambda: UrlscanProvider(client=UrlscanApiClient())
    if provider_id == "urlhaus":
        return lambda: UrlhausProvider(client=UrlhausApiClient())
    if provider_id == "threatfox":
        return lambda: ThreatFoxProvider(client=ThreatFoxApiClient())
    if provider_id == "securitytrails":
        return lambda: SecurityTrailsProvider(client=SecurityTrailsApiClient())
    if provider_id == "routeviews":
        return lambda: RouteViewsProvider(client=RouteViewsApiClient())
    return None


def lookup_entity(
    entity_type: str,
    value: str,
    *,
    session_id: str,
    run_id: str = "",
    provider_factories: list[ProviderFactory] | None = None,
    cfg: dict[str, Any] | None = None,
    redis_client=None,
) -> IntelLookupResult:
    normalized_type = str(entity_type or "").strip().lower()
    active_cfg = cfg or CFG
    active_redis = process.redis_client if redis_client is None else redis_client
    canonical = canonical_entity(normalized_type, value)
    lookups: list[ProviderLookup] = []
    factories = (
        provider_factories
        if provider_factories is not None
        else default_provider_factories(normalized_type, canonical)
    )
    for factory in factories:
        provider = factory()
        lookups.append(_lookup_provider(
            provider,
            normalized_type,
            canonical,
            session_id=session_id,
            run_id=run_id,
            cfg=active_cfg,
            redis_client=active_redis,
        ))
    return IntelLookupResult(normalized_type, canonical, lookups)


def _lookup_provider(
    provider: Provider,
    entity_type: str,
    canonical: str,
    *,
    session_id: str,
    run_id: str,
    cfg: dict[str, Any],
    redis_client,
) -> ProviderLookup:
    try:
        provider.secret_value(session_id)
    except ProviderMissingSecret as exc:
        return ProviderLookup(provider.name, status="missing_secret", message=str(exc))

    cached = cache.get_cached_response(provider.name, entity_type, canonical, redis_client=redis_client)
    if cached is not None:
        result = IntelResult(provider.name, entity_type, canonical, cached, cache_hit=True)
        audit.emit_intel_lookup(
            session_id,
            provider.name,
            entity_type,
            run_id=run_id,
            cache_hit=True,
        )
        return ProviderLookup(provider.name, result=result)

    quota = cache.get_quota_exhausted(session_id, provider.name, redis_client=redis_client)
    if quota:
        return ProviderLookup(
            provider.name,
            status="quota_exhausted",
            message=_quota_message(provider.name, quota),
            reset_at=_float_or_none(quota.get("reset_at")),
        )

    rate_limit = provider.rate_limit(session_id, cfg=cfg, redis_client=redis_client)
    if not rate_limit.allowed:
        return ProviderLookup(
            provider.name,
            status="rate_limited",
            message=f"{_provider_label(provider.name)} rate limit reached. Try again in {rate_limit.retry_after_seconds}s.",
            retry_after_seconds=rate_limit.retry_after_seconds,
        )

    try:
        result = _provider_lookup(provider, entity_type, canonical, session_id=session_id, run_id=run_id)
    except ProviderApiError as exc:
        if exc.status == 429:
            quota = cache.set_quota_exhausted(
                session_id,
                provider.name,
                reset_at=exc.reset_at,
                cfg=cfg,
                redis_client=redis_client,
            )
            return ProviderLookup(
                provider.name,
                status="quota_exhausted",
                message=_quota_message(provider.name, quota),
                reset_at=_float_or_none(quota.get("reset_at")),
            )
        return ProviderLookup(provider.name, status="error", message=str(exc))
    except ProviderClientUnavailable as exc:
        return ProviderLookup(provider.name, status="error", message=str(exc))
    except IntelProviderError as exc:
        return ProviderLookup(provider.name, status="error", message=str(exc))

    ttl = provider.cache_ttl(result.entity_type, cfg=cfg)
    cache.set_cached_response(
        provider.name,
        result.entity_type,
        result.canonical_value,
        result.payload,
        ttl_seconds=ttl,
        redis_client=redis_client,
    )
    audit.emit_intel_lookup(
        session_id,
        provider.name,
        result.entity_type,
        run_id=run_id,
        cache_hit=False,
        http_status=result.http_status or "",
        entity_count=1 if result.payload.get("summary", {}).get("has_intel") else 0,
    )
    return ProviderLookup(provider.name, result=result)


def _provider_lookup(provider: Provider, entity_type: str, canonical: str, *, session_id: str, run_id: str) -> IntelResult:
    if entity_type == "ip":
        return provider.lookup_ip(canonical, session_token=session_id, run_id=run_id)
    if entity_type == "domain":
        return provider.lookup_domain(canonical, session_token=session_id, run_id=run_id)
    if entity_type == "hash":
        hash_value = canonical.split(":", 1)[1] if ":" in canonical else canonical
        return provider.lookup_hash(hash_value, session_token=session_id, run_id=run_id)
    if entity_type == "cve":
        return provider.lookup_cve(canonical, session_token=session_id, run_id=run_id)
    if entity_type == "url":
        return provider.lookup_url(canonical, session_token=session_id, run_id=run_id)
    raise IntelProviderError(f"unsupported intel entity type: {entity_type}")


def _provider_label(provider: str) -> str:
    return provider_label(provider)


def _quota_message(provider: str, quota: dict) -> str:
    reset_at = quota.get("reset_at")
    suffix = f" Refresh after {reset_at}." if reset_at else ""
    return f"{_provider_label(provider)} quota exhausted.{suffix}"


def _float_or_none(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
