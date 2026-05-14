"""Normalized response shapes for external intel provider results."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


ENTITY_TYPES = {"ip", "domain", "hash", "cve"}

EMPTY_PROVIDER_SHAPES: dict[str, dict[str, Any]] = {
    "ip": {
        "shodan": {"ports": [], "banners": [], "cves": [], "last_update": ""},
        "censys": {
            "ports": [],
            "protocols": [],
            "services": [],
            "names": [],
            "location": {},
            "autonomous_system": {},
            "last_updated_at": "",
        },
        "greynoise": {"classification": "", "name": "", "last_seen": ""},
        "otx": {"pulse_count": 0, "reputation": None, "pulses": [], "tags": []},
        "abuseipdb": {
            "abuse_confidence_score": None,
            "total_reports": 0,
            "country_code": "",
            "usage_type": "",
            "isp": "",
            "domain": "",
            "is_tor": False,
            "last_reported_at": "",
        },
        "teamcymru": {"asn": "", "prefix": "", "cc": "", "registry": "", "allocated": "", "name": ""},
    },
    "domain": {
        "virustotal": {"reputation": None, "last_analysis_stats": {}, "recent_urls": [], "whois": ""},
        "otx": {"pulse_count": 0, "reputation": None, "pulses": [], "tags": []},
        "crtsh": {"certificate_count": 0, "names": [], "issuers": [], "first_seen": "", "last_seen": ""},
    },
    "hash": {
        "virustotal": {"verdict": "", "last_analysis_stats": {}, "type_description": "", "tags": [], "names": []},
        "otx": {"pulse_count": 0, "reputation": None, "pulses": [], "tags": []},
        "hibp": {"pwned": False, "count": 0, "prefix": ""},
    },
    "cve": {
        "nvd": {
            "published": "",
            "last_modified": "",
            "severity": "",
            "score": None,
            "description": "",
            "references": [],
        },
    },
}


def empty_response(entity_type: str) -> dict[str, Any]:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type not in EMPTY_PROVIDER_SHAPES:
        raise ValueError(f"unsupported intel entity type: {entity_type}")
    return {
        "providers": deepcopy(EMPTY_PROVIDER_SHAPES[normalized_type]),
        "summary": {
            "has_intel": False,
            "providers_with_data": [],
            "cache_status": {},
        },
    }


def provider_has_data(value: Any) -> bool:
    if isinstance(value, dict):
        return any(provider_has_data(item) for item in value.values())
    if isinstance(value, list):
        return bool(value)
    return value not in {"", None, False}


def response_with_provider(
    entity_type: str,
    provider: str,
    payload: dict[str, Any],
    *,
    cache_hit: bool = False,
) -> dict[str, Any]:
    response = empty_response(entity_type)
    provider_name = str(provider or "").strip().lower()
    if provider_name not in response["providers"]:
        raise ValueError(f"unsupported provider for {entity_type}: {provider}")
    response["providers"][provider_name] = payload
    if provider_has_data(payload):
        response["summary"]["has_intel"] = True
        response["summary"]["providers_with_data"] = [provider_name]
    response["summary"]["cache_status"] = {provider_name: "hit" if cache_hit else "miss"}
    return response
