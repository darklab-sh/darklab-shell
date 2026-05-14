"""Metadata registry for app-native external intel providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CacheTtlSetting:
    config_key: str
    default_seconds: int


@dataclass(frozen=True)
class RateLimitSetting:
    bucket_config_key: str
    refill_config_key: str
    default_bucket: int
    default_refill_seconds: int


@dataclass(frozen=True)
class IntelProviderDefinition:
    id: str
    label: str
    entity_types: tuple[str, ...]
    secret_env: str = ""
    secret_env_aliases: tuple[str, ...] = ()
    optional_secret: bool = False
    cache_scopes: dict[str, str] = field(default_factory=dict)
    cache_ttls: dict[str, CacheTtlSetting] = field(default_factory=dict)
    rate_limits: dict[str, RateLimitSetting] = field(default_factory=dict)
    default_rate_limit_profile: str = ""
    tier: str = "shipped"
    app_native: bool = True

    @property
    def secret_env_names(self) -> tuple[str, ...]:
        names = [self.secret_env, *self.secret_env_aliases]
        return tuple(name for name in names if name)


INTEL_PROVIDERS: dict[str, IntelProviderDefinition] = {
    "shodan": IntelProviderDefinition(
        id="shodan",
        label="Shodan",
        entity_types=("ip",),
        secret_env="SHODAN_API_KEY",
        cache_scopes={"ip": "ip"},
        cache_ttls={
            "ip": CacheTtlSetting("intel_cache_ttl_shodan_ip_seconds", 86400),
            "search": CacheTtlSetting("intel_cache_ttl_shodan_search_seconds", 21600),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_shodan_bucket", "intel_rate_limit_shodan_refill_seconds", 5, 1),
        },
    ),
    "censys": IntelProviderDefinition(
        id="censys",
        label="Censys",
        entity_types=("ip",),
        secret_env="CENSYS_PAT",
        cache_scopes={"ip": "host"},
        cache_ttls={
            "host": CacheTtlSetting("intel_cache_ttl_censys_host_seconds", 21600),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_censys_bucket", "intel_rate_limit_censys_refill_seconds", 10, 6),
        },
    ),
    "virustotal": IntelProviderDefinition(
        id="virustotal",
        label="VirusTotal",
        entity_types=("domain", "hash"),
        secret_env="VT_API_KEY",
        secret_env_aliases=("VTCLI_APIKEY",),
        cache_scopes={"domain": "domain", "hash": "file"},
        cache_ttls={
            "domain": CacheTtlSetting("intel_cache_ttl_virustotal_domain_seconds", 21600),
            "file": CacheTtlSetting("intel_cache_ttl_virustotal_file_seconds", 86400),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_virustotal_public_bucket",
                "intel_rate_limit_virustotal_public_refill_seconds",
                4,
                15,
            ),
        },
    ),
    "greynoise": IntelProviderDefinition(
        id="greynoise",
        label="GreyNoise",
        entity_types=("ip",),
        secret_env="GREYNOISE_API_KEY",
        cache_scopes={"ip": "ip"},
        cache_ttls={
            "ip": CacheTtlSetting("intel_cache_ttl_greynoise_ip_seconds", 3600),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_greynoise_community_bucket",
                "intel_rate_limit_greynoise_community_refill_seconds",
                50,
                12096,
            ),
            "unauthenticated": RateLimitSetting(
                "intel_rate_limit_greynoise_unauthenticated_bucket",
                "intel_rate_limit_greynoise_unauthenticated_refill_seconds",
                10,
                8640,
            ),
        },
    ),
    "otx": IntelProviderDefinition(
        id="otx",
        label="AlienVault OTX",
        entity_types=("ip", "domain", "hash"),
        secret_env="OTX_API_KEY",
        cache_scopes={"ip": "indicator", "domain": "indicator", "hash": "indicator"},
        cache_ttls={
            "indicator": CacheTtlSetting("intel_cache_ttl_otx_indicator_seconds", 21600),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_otx_bucket",
                "intel_rate_limit_otx_refill_seconds",
                30,
                2,
            ),
        },
    ),
    "abuseipdb": IntelProviderDefinition(
        id="abuseipdb",
        label="AbuseIPDB",
        entity_types=("ip",),
        secret_env="ABUSEIPDB_API_KEY",
        cache_scopes={"ip": "ip"},
        cache_ttls={
            "ip": CacheTtlSetting("intel_cache_ttl_abuseipdb_ip_seconds", 21600),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_abuseipdb_bucket",
                "intel_rate_limit_abuseipdb_refill_seconds",
                20,
                4,
            ),
        },
    ),
    "teamcymru": IntelProviderDefinition(
        id="teamcymru",
        label="Team Cymru",
        entity_types=("ip",),
        cache_scopes={"ip": "ip"},
        cache_ttls={
            "ip": CacheTtlSetting("intel_cache_ttl_teamcymru_ip_seconds", 86400),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_teamcymru_bucket",
                "intel_rate_limit_teamcymru_refill_seconds",
                30,
                2,
            ),
        },
    ),
    "crtsh": IntelProviderDefinition(
        id="crtsh",
        label="crt.sh",
        entity_types=("domain",),
        cache_scopes={"domain": "domain"},
        cache_ttls={
            "domain": CacheTtlSetting("intel_cache_ttl_crtsh_domain_seconds", 86400),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_crtsh_bucket",
                "intel_rate_limit_crtsh_refill_seconds",
                10,
                6,
            ),
        },
    ),
    "hibp": IntelProviderDefinition(
        id="hibp",
        label="HIBP Pwned Passwords",
        entity_types=("hash",),
        cache_scopes={"hash": "password"},
        cache_ttls={
            "password": CacheTtlSetting("intel_cache_ttl_hibp_password_seconds", 604800),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_hibp_bucket",
                "intel_rate_limit_hibp_refill_seconds",
                10,
                2,
            ),
        },
    ),
    "nvd": IntelProviderDefinition(
        id="nvd",
        label="NVD",
        entity_types=("cve",),
        cache_scopes={"cve": "cve"},
        cache_ttls={
            "cve": CacheTtlSetting("intel_cache_ttl_nvd_cve_seconds", 86400),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_nvd_anonymous_bucket",
                "intel_rate_limit_nvd_anonymous_refill_seconds",
                5,
                6,
            ),
        },
    ),
}


def provider_definition(provider: str) -> IntelProviderDefinition | None:
    return INTEL_PROVIDERS.get(str(provider or "").strip().lower())


def provider_label(provider: str) -> str:
    definition = provider_definition(provider)
    if definition:
        return definition.label
    return str(provider or "").strip() or "Provider"


def providers_for_entity_type(entity_type: str) -> list[IntelProviderDefinition]:
    normalized = str(entity_type or "").strip().lower()
    return [
        definition
        for definition in INTEL_PROVIDERS.values()
        if normalized in definition.entity_types
    ]


def cache_scope(provider: str, entity_type: str) -> str:
    definition = provider_definition(provider)
    normalized_entity_type = str(entity_type or "").strip().lower()
    if not definition:
        return normalized_entity_type
    return definition.cache_scopes.get(normalized_entity_type, normalized_entity_type)


def cache_ttl_setting(provider: str, scope: str) -> CacheTtlSetting | None:
    definition = provider_definition(provider)
    if not definition:
        return None
    return definition.cache_ttls.get(str(scope or "").strip().lower())


def rate_limit_setting(provider: str, profile: str = "") -> RateLimitSetting | None:
    definition = provider_definition(provider)
    if not definition:
        return None
    normalized_profile = str(profile or "").strip().lower()
    return definition.rate_limits.get(normalized_profile) or definition.rate_limits.get(definition.default_rate_limit_profile)


def app_native_secret_consumers() -> list[dict[str, Any]]:
    consumers = []
    for definition in INTEL_PROVIDERS.values():
        if not definition.app_native or not definition.secret_env:
            continue
        consumers.append({
            "source": "app_native_intel",
            "consumer": f"intel {definition.label}",
            "provider": definition.id,
            "env": definition.secret_env,
            "fallback_envs": list(definition.secret_env_aliases),
            "optional": definition.optional_secret,
        })
    return consumers
