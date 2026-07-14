# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atlas intel snapshot shaping and summary highlights."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.intel.registry import provider_label
from services.storage.body_store import load_text_body, stored_body_pointer

MAX_INTEL_SUMMARY_HIGHLIGHTS = 8


def _load_json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        if not stored_body_pointer(value):
            return value
        text = load_text_body(value)
    elif isinstance(value, str) or value is None:
        text = load_text_body(value)
    else:
        return {}
    return dialect_for_backend(get_db_backend()).decode_json_dict(text)


def _row_to_intel_snapshot(row) -> dict[str, Any]:
    data = _load_json_dict(row["data_json"])
    return {
        "id": row["id"],
        "provider": row["provider"],
        "status": row["status"],
        "summary": row["summary"],
        "data": data,
        "fetched_at": row["fetched_at"],
        "expires_at": row["expires_at"],
    }


def _intel_provider_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    provider = str(snapshot.get("provider") or "").strip().lower()
    data = snapshot.get("data") if isinstance(snapshot.get("data"), dict) else {}
    providers = data.get("providers") if isinstance(data, dict) else {}
    if not isinstance(providers, dict):
        return {}
    payload = providers.get(provider)
    if isinstance(payload, dict):
        return payload
    for key, value in providers.items():
        if str(key or "").strip().lower() == provider and isinstance(value, dict):
            return value
    return {}


def _snapshot_has_intel(snapshot: dict[str, Any]) -> bool:
    data = snapshot.get("data") if isinstance(snapshot.get("data"), dict) else {}
    summary = data.get("summary") if isinstance(data, dict) else None
    if isinstance(summary, dict):
        providers = summary.get("providers_with_data")
        if isinstance(providers, list) and providers:
            return True
        has_intel = summary.get("has_intel")
        if isinstance(has_intel, bool):
            return has_intel
    return bool(_intel_provider_payload(snapshot))


def _highlight(label: str, value: object, provider: str, tone: str = "neutral") -> dict[str, str] | None:
    rendered = _render_value(value)
    if not rendered:
        return None
    provider_id = str(provider or "").strip().lower()
    return {
        "label": label,
        "value": rendered,
        "provider": provider_id,
        "provider_label": provider_label(provider_id),
        "tone": tone,
    }


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(int(value) if isinstance(value, float) and value.is_integer() else value)
    if isinstance(value, str):
        return value.strip()
    return ""


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _list_values(value: object, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    results = []
    for item in value:
        rendered = _render_value(item)
        if rendered and rendered not in results:
            results.append(rendered)
        if len(results) >= limit:
            break
    return results


def _join_list(value: object, *, limit: int = 6) -> str:
    values = _list_values(value, limit=limit)
    if not values:
        return ""
    extra = len(value) - len(values) if isinstance(value, list) else 0
    suffix = f" +{extra} more" if extra > 0 else ""
    return ", ".join(values) + suffix


def _analysis_stats(value: object) -> str:
    stats = value if isinstance(value, dict) else {}
    malicious = _int_or_none(stats.get("malicious")) or 0
    suspicious = _int_or_none(stats.get("suspicious")) or 0
    harmless = _int_or_none(stats.get("harmless")) or 0
    if malicious or suspicious:
        return f"{malicious} malicious · {suspicious} suspicious"
    if harmless:
        return f"{harmless} harmless"
    return ""


def _asn_summary(value: object) -> str:
    row = value if isinstance(value, dict) else {}
    asn = _render_value(row.get("asn") or row.get("number"))
    name = _render_value(row.get("name") or row.get("description"))
    if asn and not asn.upper().startswith("AS"):
        asn = f"AS{asn}"
    return " ".join(part for part in (asn, name) if part)


def _location_summary(value: object) -> str:
    row = value if isinstance(value, dict) else {}
    return ", ".join(
        part for part in (
            _render_value(row.get("city")),
            _render_value(row.get("region")),
            _render_value(row.get("country") or row.get("country_code")),
        )
        if part
    )


def _pulse_count(value: object) -> str:
    count = _int_or_none(value)
    if count is None:
        return ""
    return f"{count} pulse{'s' if count != 1 else ''}"


def _highlights_for_provider(
    entity_type: str,
    provider: str,
    payload: dict[str, Any],
) -> list[dict[str, str]]:
    items: list[dict[str, str] | None] = []
    if entity_type == "ip":
        items = _ip_highlights(provider, payload)
    elif entity_type == "domain":
        items = _domain_highlights(provider, payload)
    elif entity_type == "hash":
        items = _hash_highlights(provider, payload)
    elif entity_type == "cve":
        items = _cve_highlights(provider, payload)
    elif entity_type == "url":
        items = _url_highlights(provider, payload)
    return [item for item in items if item]


def _ip_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    if provider == "shodan":
        return [
            _highlight("Open ports", _join_list(payload.get("ports"), limit=8), provider),
            _highlight("CVEs", _join_list(payload.get("cves"), limit=5), provider, "warning"),
            _highlight("Last updated", payload.get("last_update"), provider),
        ]
    if provider == "censys":
        return [
            _highlight("Open ports", _join_list(payload.get("ports"), limit=8), provider),
            _highlight("Names", _join_list(payload.get("names"), limit=4), provider),
            _highlight("ASN", _asn_summary(payload.get("autonomous_system")), provider),
            _highlight("Location", _location_summary(payload.get("location")), provider),
        ]
    if provider == "greynoise":
        noise = payload.get("noise")
        riot = payload.get("riot")
        noise_parts = []
        if isinstance(noise, bool):
            noise_parts.append(f"noise: {'yes' if noise else 'no'}")
        if isinstance(riot, bool):
            noise_parts.append(f"RIOT: {'yes' if riot else 'no'}")
        return [
            _highlight("GreyNoise", " · ".join(noise_parts), provider),
            _highlight("Classification", payload.get("classification"), provider),
            _highlight("Name", payload.get("name"), provider),
        ]
    if provider == "abuseipdb":
        score = _int_or_none(payload.get("abuse_confidence_score"))
        return [
            _highlight("Abuse score", f"{score}/100" if score is not None else "", provider),
            _highlight("Reports", payload.get("total_reports"), provider),
            _highlight("Network", payload.get("isp") or payload.get("domain"), provider),
            _highlight("Country", payload.get("country_code"), provider),
        ]
    if provider == "ipinfo":
        location = ", ".join(
            part for part in (
                _render_value(payload.get("city")),
                _render_value(payload.get("region")),
                _render_value(payload.get("country")),
            )
            if part
        )
        asn = " ".join(
            part for part in (
                _render_value(payload.get("asn")),
                _render_value(payload.get("org")),
            )
            if part
        )
        return [
            _highlight("ASN", asn, provider),
            _highlight("Hostname", payload.get("hostname") or payload.get("domain"), provider),
            _highlight("Location", location, provider),
        ]
    if provider == "teamcymru":
        asn = " ".join(
            part for part in (
                _render_value(payload.get("asn")),
                _render_value(payload.get("name")),
            )
            if part
        )
        return [
            _highlight("ASN", asn, provider),
            _highlight("Prefix", payload.get("prefix"), provider),
            _highlight("Registry", payload.get("registry"), provider),
        ]
    if provider == "routeviews":
        return [
            _highlight("Prefix", payload.get("prefix"), provider),
            _highlight("Origins", _join_list(payload.get("origins"), limit=5), provider),
            _highlight("RPKI", payload.get("rpki"), provider),
        ]
    return _shared_ioc_highlights(provider, payload)


def _domain_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    if provider == "virustotal":
        return [
            _highlight("Analysis", _analysis_stats(payload.get("last_analysis_stats")), provider),
            _highlight("Reputation", payload.get("reputation"), provider),
        ]
    if provider == "crtsh":
        return [
            _highlight("Certificates", payload.get("certificate_count"), provider),
            _highlight("Names", _join_list(payload.get("names"), limit=4), provider),
            _highlight("Last seen", payload.get("last_seen"), provider),
            _highlight("Latest expiry", payload.get("latest_expiry"), provider),
        ]
    if provider == "urlscan":
        return [_highlight("urlscan results", payload.get("result_count"), provider)]
    if provider == "securitytrails":
        return [_highlight("Subdomains", payload.get("subdomain_count"), provider)]
    return _shared_ioc_highlights(provider, payload)


def _hash_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    if provider == "virustotal":
        return [
            _highlight("Verdict", payload.get("verdict"), provider, "warning"),
            _highlight("Analysis", _analysis_stats(payload.get("last_analysis_stats")), provider),
            _highlight("Type", payload.get("type_description"), provider),
        ]
    if provider == "hibp":
        count = _int_or_none(payload.get("count")) or 0
        return [_highlight("Pwned password", f"{count} matches" if count else "not found", provider)]
    return _shared_ioc_highlights(provider, payload)


def _cve_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    return [
        _highlight("Severity", payload.get("severity"), provider, "warning"),
        _highlight("Score", payload.get("score"), provider, "warning"),
        _highlight("Exploits", payload.get("exploit_count"), provider, "warning"),
        _highlight("Published", payload.get("published"), provider),
    ]


def _url_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    if provider == "urlhaus":
        return [
            _highlight("URL status", payload.get("status") or payload.get("query_status"), provider, "warning"),
            _highlight("Threat", payload.get("threat"), provider, "warning"),
            _highlight("Host", payload.get("host"), provider),
        ]
    if provider == "urlscan":
        return [_highlight("urlscan results", payload.get("result_count"), provider)]
    return _shared_ioc_highlights(provider, payload)


def _shared_ioc_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    return [
        _highlight("Pulses", _pulse_count(payload.get("pulse_count")), provider),
        _highlight("Reputation", payload.get("reputation"), provider),
        _highlight("URLs", payload.get("url_count"), provider),
        _highlight("Payloads", payload.get("payload_count"), provider),
        _highlight("IOCs", payload.get("ioc_count"), provider),
        _highlight("Malware", _join_list(payload.get("malware"), limit=4), provider, "warning"),
        _highlight("Tags", _join_list(payload.get("tags"), limit=5), provider),
    ]


def _dedupe_highlights(highlights: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    result = []
    for item in highlights:
        key = (item["label"], item["value"], item["provider"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= MAX_INTEL_SUMMARY_HIGHLIGHTS:
            break
    return result


def summarize_intel_snapshots(
    entity_type: str,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    providers_with_data: list[str] = []
    highlights: list[dict[str, str]] = []
    latest_fetched_at = ""
    for snapshot in snapshots:
        provider = str(snapshot.get("provider") or "").strip().lower()
        if not provider:
            continue
        fetched_at = str(snapshot.get("fetched_at") or "")
        if fetched_at > latest_fetched_at:
            latest_fetched_at = fetched_at
        has_data = _snapshot_has_intel(snapshot)
        payload = _intel_provider_payload(snapshot)
        if has_data and provider not in providers_with_data:
            providers_with_data.append(provider)
        if str(snapshot.get("status") or "") == "ok" and payload:
            highlights.extend(_highlights_for_provider(str(entity_type or ""), provider, payload))
    highlights = _dedupe_highlights(highlights)
    status = "none"
    if snapshots:
        status = "available" if providers_with_data or highlights else "empty"
    return {
        "status": status,
        "providers_with_data": providers_with_data,
        "highlight_count": len(highlights),
        "highlights": highlights,
        "updated_at": latest_fetched_at,
    }
