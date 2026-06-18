"""Metadata registry for external intel providers."""

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
    required_secret_envs: tuple[str, ...] = ()
    optional_secret: bool = False
    cache_scopes: dict[str, str] = field(default_factory=dict)
    cache_ttls: dict[str, CacheTtlSetting] = field(default_factory=dict)
    rate_limits: dict[str, RateLimitSetting] = field(default_factory=dict)
    default_rate_limit_profile: str = ""
    tier: str = "shipped"
    access_note: str = "Account-backed"
    app_native: bool = True
    uses: tuple[str, ...] = ()

    @property
    def secret_env_names(self) -> tuple[str, ...]:
        names = [self.secret_env, *self.secret_env_aliases, *self.required_secret_envs]
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
        access_note="Free signup; paid tiers",
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
        access_note="Account-backed; paid tiers",
    ),
    "shodan_internetdb": IntelProviderDefinition(
        id="shodan_internetdb",
        label="Shodan InternetDB",
        entity_types=("ip",),
        cache_scopes={"ip": "ip"},
        cache_ttls={
            "ip": CacheTtlSetting("intel_cache_ttl_shodan_internetdb_ip_seconds", 86400),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_shodan_internetdb_bucket",
                "intel_rate_limit_shodan_internetdb_refill_seconds",
                30,
                2,
            ),
        },
        access_note="Free public lookup",
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
        access_note="Free signup; paid tiers",
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
        access_note="Free community key",
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
        access_note="Free signup",
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
        access_note="Free signup; paid tiers",
    ),
    "ipinfo": IntelProviderDefinition(
        id="ipinfo",
        label="IPinfo",
        entity_types=("ip",),
        secret_env="IPINFO_TOKEN",
        optional_secret=True,
        cache_scopes={"ip": "ip"},
        cache_ttls={
            "ip": CacheTtlSetting("intel_cache_ttl_ipinfo_ip_seconds", 21600),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_ipinfo_bucket", "intel_rate_limit_ipinfo_refill_seconds", 30, 2),
        },
        access_note="Free public basics; optional account token",
        uses=("intel ip", "ipinfo CLI"),
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
        access_note="Free public lookup",
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
        access_note="Free public lookup",
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
        access_note="Free public lookup",
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
        access_note="Free public lookup",
    ),
    "vulners": IntelProviderDefinition(
        id="vulners",
        label="Vulners",
        entity_types=("cve",),
        secret_env="VULNERS_API_KEY",
        cache_scopes={"cve": "cve"},
        cache_ttls={
            "cve": CacheTtlSetting("intel_cache_ttl_vulners_cve_seconds", 86400),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_vulners_bucket", "intel_rate_limit_vulners_refill_seconds", 10, 6),
        },
        access_note="Free signup; paid tiers",
    ),
    "urlscan": IntelProviderDefinition(
        id="urlscan",
        label="urlscan.io",
        entity_types=("domain", "url"),
        secret_env="URLSCAN_API_KEY",
        cache_scopes={"domain": "search", "url": "search"},
        cache_ttls={
            "search": CacheTtlSetting("intel_cache_ttl_urlscan_search_seconds", 21600),
            "result": CacheTtlSetting("intel_cache_ttl_urlscan_result_seconds", 86400),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_urlscan_bucket", "intel_rate_limit_urlscan_refill_seconds", 10, 6),
        },
        access_note="Free signup; paid tiers",
    ),
    "urlhaus": IntelProviderDefinition(
        id="urlhaus",
        label="URLhaus",
        entity_types=("ip", "domain", "hash", "url"),
        secret_env="URLHAUS_AUTH_KEY",
        cache_scopes={"ip": "host", "domain": "host", "hash": "payload", "url": "url"},
        cache_ttls={
            "host": CacheTtlSetting("intel_cache_ttl_urlhaus_host_seconds", 21600),
            "payload": CacheTtlSetting("intel_cache_ttl_urlhaus_payload_seconds", 86400),
            "url": CacheTtlSetting("intel_cache_ttl_urlhaus_url_seconds", 21600),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_urlhaus_bucket", "intel_rate_limit_urlhaus_refill_seconds", 20, 3),
        },
        access_note="Free abuse.ch Auth-Key",
    ),
    "threatfox": IntelProviderDefinition(
        id="threatfox",
        label="ThreatFox",
        entity_types=("ip", "domain", "hash", "url"),
        secret_env="THREATFOX_AUTH_KEY",
        cache_scopes={"ip": "ioc", "domain": "ioc", "hash": "hash", "url": "ioc"},
        cache_ttls={
            "ioc": CacheTtlSetting("intel_cache_ttl_threatfox_ioc_seconds", 21600),
            "hash": CacheTtlSetting("intel_cache_ttl_threatfox_hash_seconds", 86400),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_threatfox_bucket", "intel_rate_limit_threatfox_refill_seconds", 20, 3),
        },
        access_note="Free abuse.ch Auth-Key",
    ),
    "securitytrails": IntelProviderDefinition(
        id="securitytrails",
        label="SecurityTrails",
        entity_types=("domain",),
        secret_env="SECURITYTRAILS_API_KEY",
        cache_scopes={"domain": "domain"},
        cache_ttls={
            "domain": CacheTtlSetting("intel_cache_ttl_securitytrails_domain_seconds", 86400),
        },
        rate_limits={
            "": RateLimitSetting(
                "intel_rate_limit_securitytrails_bucket",
                "intel_rate_limit_securitytrails_refill_seconds",
                10,
                6,
            ),
        },
        access_note="Paid account required",
    ),
    "fofa": IntelProviderDefinition(
        id="fofa",
        label="FOFA",
        entity_types=("ip", "domain", "url"),
        secret_env="FOFA_KEY",
        secret_env_aliases=("FOFA_API_KEY", "FOFA_APIKEY", "FOFA_TOKEN"),
        required_secret_envs=("FOFA_EMAIL",),
        cache_scopes={"ip": "search", "domain": "search", "url": "search"},
        cache_ttls={
            "search": CacheTtlSetting("intel_cache_ttl_fofa_search_seconds", 21600),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_fofa_bucket", "intel_rate_limit_fofa_refill_seconds", 10, 6),
        },
        access_note="Paid account or F-point balance required",
    ),
    "zoomeye": IntelProviderDefinition(
        id="zoomeye",
        label="ZoomEye",
        entity_types=("ip", "domain", "url"),
        secret_env="ZOOMEYE_API_KEY",
        cache_scopes={"ip": "search", "domain": "search", "url": "search"},
        cache_ttls={
            "search": CacheTtlSetting("intel_cache_ttl_zoomeye_search_seconds", 21600),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_zoomeye_bucket", "intel_rate_limit_zoomeye_refill_seconds", 10, 6),
        },
        access_note="Paid account or resource credits required",
    ),
    "routeviews": IntelProviderDefinition(
        id="routeviews",
        label="RouteViews",
        entity_types=("ip",),
        cache_scopes={"ip": "prefix"},
        cache_ttls={
            "prefix": CacheTtlSetting("intel_cache_ttl_routeviews_prefix_seconds", 21600),
        },
        rate_limits={
            "": RateLimitSetting("intel_rate_limit_routeviews_bucket", "intel_rate_limit_routeviews_refill_seconds", 20, 3),
        },
        access_note="Free public lookup",
    ),
    "chaos": IntelProviderDefinition(
        id="chaos",
        label="ProjectDiscovery Chaos",
        entity_types=("domain",),
        secret_env="PDCP_API_KEY",
        app_native=False,
        access_note="ProjectDiscovery Cloud account key",
        uses=("chaos CLI",),
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
        if definition.app_native and normalized in definition.entity_types
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
        for env_name in definition.required_secret_envs:
            consumers.append({
                "source": "app_native_intel",
                "consumer": f"intel {definition.label}",
                "provider": definition.id,
                "env": env_name,
                "fallback_envs": [],
                "optional": definition.optional_secret,
            })
        if definition.id == "censys":
            consumers.append({
                "source": "app_native_intel",
                "consumer": "intel Censys organization",
                "provider": definition.id,
                "env": "CENSYS_ORGANIZATION_ID",
                "fallback_envs": [],
                "optional": True,
            })
    return consumers


def provider_status_catalog() -> list[dict[str, Any]]:
    """Return metadata-only provider status inputs for the browser."""
    return [
        {
            "id": definition.id,
            "label": definition.label,
            "entity_types": list(definition.entity_types),
            "secret_env": definition.secret_env,
            "secret_env_aliases": list(definition.secret_env_aliases),
            "required_secret_envs": list(definition.required_secret_envs),
            "secret_env_names": list(definition.secret_env_names),
            "requires_secret": bool(definition.secret_env),
            "optional_secret": bool(definition.optional_secret),
            "access_note": definition.access_note,
            "app_native": definition.app_native,
            "uses": list(definition.uses or _default_provider_uses(definition)),
        }
        for definition in INTEL_PROVIDERS.values()
    ]


def _default_provider_uses(definition: IntelProviderDefinition) -> tuple[str, ...]:
    if definition.app_native:
        return tuple(f"intel {entity_type}" for entity_type in definition.entity_types)
    return ()
