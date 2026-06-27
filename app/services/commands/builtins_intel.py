"""App-native external intel built-in command handlers."""

from __future__ import annotations

import ipaddress
from typing import Any

from services.commands.builtins_format import format_native_record, output_line
from services.commands.registry import split_command_argv
from services.intel.canonical import CanonicalizationError
from services.intel.lookup import IntelLookupResult, ProviderLookup, lookup_entity
from services.intel.registry import provider_label


def run_builtin_intel(command: str, session_id: str, *, team_id: str = "") -> tuple[list[dict[str, object]], int]:
    parts = split_command_argv(command)
    if len(parts) <= 1 or parts[1].lower() in {"help", "-h", "--help"}:
        return _intel_usage(), 0

    entity_type = parts[1].lower()
    if entity_type not in {"ip", "domain", "hash", "cve", "url"}:
        return [output_line(f"intel: unsupported lookup type '{entity_type}'"), *_intel_usage()], 1

    include_private = "--include-private" in parts[2:]
    values = [part for part in parts[2:] if part != "--include-private"]
    if len(values) != 1:
        return [output_line(f"Usage: intel {entity_type} <value>")], 1
    raw_value = values[0]

    if entity_type == "ip":
        private_error = _private_ip_error(raw_value, include_private=include_private)
        if private_error:
            return [output_line(private_error)], 1

    try:
        result = lookup_entity(entity_type, raw_value, session_id=team_id or session_id)
    except CanonicalizationError as exc:
        message = "Hash must be hex MD5/SHA1/SHA256" if entity_type == "hash" else str(exc)
        return [output_line(f"intel: {message}")], 1

    lines = _format_lookup_result(result)
    exit_code = 0 if result.success_count or result.configured_count else 1
    return lines, exit_code


def _intel_usage() -> list[dict[str, object]]:
    return [
        output_line("Intel commands:", "builtin-section"),
        output_line("  intel ip <ip> [--include-private]", "builtin-help-row"),
        output_line("  intel domain <domain>", "builtin-help-row"),
        output_line("  intel url <url>", "builtin-help-row"),
        output_line("  intel hash <md5|sha1|sha256>", "builtin-help-row"),
        output_line("  intel cve <CVE-ID>", "builtin-help-row"),
        output_line("Configure provider keys with `secret set NAME` or Options > Secrets.", "builtin-note"),
    ]


def _private_ip_error(value: str, *, include_private: bool) -> str:
    if include_private:
        return ""
    try:
        ip = ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return ""
    if ip.is_global:
        return ""
    return (
        f"IP {ip.compressed} is in a private/loopback range; intel providers cannot meaningfully classify it. "
        "Use --include-private if you really want to query."
    )


def _format_lookup_result(result: IntelLookupResult) -> list[dict[str, object]]:
    lines = [
        output_line(
            f"Intel lookup: {result.entity_type} {result.canonical_value}",
            "builtin-section",
        ),
    ]
    for index, provider in enumerate(result.providers):
        if index > 0:
            lines.append(output_line("", "builtin-spacer"))
        lines.extend(_format_provider_lookup(provider, result.entity_type))
    if result.providers and result.configured_count == 0:
        lines.append(output_line("No providers are configured for this lookup.", "builtin-note"))
        lines.append(output_line("Use `providers` to see provider setup status and accepted secret names.", "builtin-note"))
    return lines


def _format_provider_lookup(provider: ProviderLookup, entity_type: str) -> list[dict[str, object]]:
    label = _provider_label(provider.provider)
    if provider.status == "missing_secret":
        return [output_line(f"{label}: not configured - {provider.message}", "builtin-note")]
    if provider.status in {"rate_limited", "quota_exhausted", "error"}:
        return [output_line(f"{label}: {provider.message}", "builtin-warning")]
    if provider.result is None:
        return [output_line(f"{label}: no result", "builtin-note")]

    cache_label = _provider_cache_label(provider)
    lines = [output_line(f"{label} results - {cache_label}", "builtin-section")]
    provider_payload = provider.result.payload.get("providers", {}).get(provider.provider, {})
    if not isinstance(provider_payload, dict):
        return [*lines, output_line("  no provider data returned", "builtin-note")]
    if entity_type == "ip" and provider.provider == "shodan":
        lines.extend(_format_shodan(provider_payload))
    elif entity_type == "ip" and provider.provider == "shodan_internetdb":
        lines.extend(_format_shodan_internetdb(provider_payload))
    elif entity_type == "ip" and provider.provider == "censys":
        lines.extend(_format_censys(provider_payload))
    elif entity_type == "ip" and provider.provider == "greynoise":
        lines.extend(_format_greynoise(provider_payload))
    elif entity_type == "ip" and provider.provider == "otx":
        lines.extend(_format_otx(provider_payload))
    elif entity_type == "ip" and provider.provider == "abuseipdb":
        lines.extend(_format_abuseipdb(provider_payload))
    elif entity_type == "ip" and provider.provider == "ipinfo":
        lines.extend(_format_ipinfo(provider_payload))
    elif entity_type == "ip" and provider.provider == "teamcymru":
        lines.extend(_format_teamcymru(provider_payload))
    elif entity_type == "ip" and provider.provider == "urlhaus":
        lines.extend(_format_urlhaus_host(provider_payload))
    elif entity_type == "ip" and provider.provider == "threatfox":
        lines.extend(_format_threatfox(provider_payload))
    elif entity_type == "ip" and provider.provider == "routeviews":
        lines.extend(_format_routeviews(provider_payload))
    elif entity_type == "ip" and provider.provider in {"fofa", "zoomeye"}:
        lines.extend(_format_search_rows(provider_payload))
    elif entity_type == "domain" and provider.provider == "virustotal":
        lines.extend(_format_virustotal_domain(provider_payload))
    elif entity_type == "domain" and provider.provider == "otx":
        lines.extend(_format_otx(provider_payload))
    elif entity_type == "domain" and provider.provider == "tls_certificate":
        lines.extend(_format_tls_certificate(provider_payload))
    elif entity_type == "domain" and provider.provider == "crtsh":
        lines.extend(_format_crtsh(provider_payload))
    elif entity_type == "domain" and provider.provider == "urlhaus":
        lines.extend(_format_urlhaus_host(provider_payload))
    elif entity_type == "domain" and provider.provider == "threatfox":
        lines.extend(_format_threatfox(provider_payload))
    elif entity_type == "domain" and provider.provider == "urlscan":
        lines.extend(_format_urlscan(provider_payload))
    elif entity_type == "domain" and provider.provider == "securitytrails":
        lines.extend(_format_securitytrails(provider_payload))
    elif entity_type == "domain" and provider.provider in {"fofa", "zoomeye"}:
        lines.extend(_format_search_rows(provider_payload))
    elif entity_type == "hash" and provider.provider == "virustotal":
        lines.extend(_format_virustotal_hash(provider_payload))
    elif entity_type == "hash" and provider.provider == "otx":
        lines.extend(_format_otx(provider_payload))
    elif entity_type == "hash" and provider.provider == "hibp":
        lines.extend(_format_hibp(provider_payload))
    elif entity_type == "hash" and provider.provider == "urlhaus":
        lines.extend(_format_urlhaus_hash(provider_payload))
    elif entity_type == "hash" and provider.provider == "threatfox":
        lines.extend(_format_threatfox(provider_payload))
    elif entity_type == "cve" and provider.provider == "nvd":
        lines.extend(_format_nvd(provider_payload))
    elif entity_type == "cve" and provider.provider == "vulners":
        lines.extend(_format_vulners(provider_payload))
    elif entity_type == "url" and provider.provider == "urlhaus":
        lines.extend(_format_urlhaus_url(provider_payload))
    elif entity_type == "url" and provider.provider == "threatfox":
        lines.extend(_format_threatfox(provider_payload))
    elif entity_type == "url" and provider.provider == "urlscan":
        lines.extend(_format_urlscan(provider_payload))
    elif entity_type == "url" and provider.provider in {"fofa", "zoomeye"}:
        lines.extend(_format_search_rows(provider_payload))
    else:
        lines.append(output_line("  no formatter for provider data", "builtin-note"))
    return lines


def _provider_cache_label(provider: ProviderLookup) -> str:
    if provider.result and provider.result.cache_hit:
        return "retrieved from cache:"
    cache_status = None
    if provider.result:
        summary = provider.result.payload.get("summary")
        if isinstance(summary, dict):
            statuses = summary.get("cache_status")
            if isinstance(statuses, dict):
                cache_status = statuses.get(provider.provider)
    if cache_status == "disabled":
        return "retrieved live (cache disabled):"
    return "retrieved and cached:"


def _format_shodan(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("ports", _join_values(payload.get("ports")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("cves", _join_values(payload.get("cves")) or "none", 14), "builtin-kv"),
    ]
    last_update = str(payload.get("last_update") or "")
    if last_update:
        lines.append(output_line(format_native_record("last update", last_update, 14), "builtin-kv"))
    banners = payload.get("banners")
    if isinstance(banners, list) and banners:
        lines.append(output_line("banners:", "builtin-subsection"))
        for row in banners[:3]:
            if not isinstance(row, dict):
                continue
            port = str(row.get("port") or "?")
            transport = str(row.get("transport") or "tcp")
            product = str(row.get("product") or "").strip()
            data = _truncate(str(row.get("data") or "").strip().replace("\n", " "), 96)
            summary = " - ".join(part for part in (product, data) if part)
            lines.append(output_line(f"  {port}/{transport} {summary}".rstrip(), "builtin-kv"))
    return lines


def _format_shodan_internetdb(payload: dict[str, Any]) -> list[dict[str, object]]:
    return [
        output_line(format_native_record("ports", _join_values(payload.get("ports")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("cves", _join_values(payload.get("cves")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("hostnames", _join_values(payload.get("hostnames")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("cpes", _join_values(payload.get("cpes")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("tags", _join_values(payload.get("tags")) or "none", 14), "builtin-kv"),
    ]


def _format_search_rows(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("results", str(payload.get("result_count") or 0), 14), "builtin-kv"),
    ]
    rows = payload.get("results")
    if isinstance(rows, list) and rows:
        lines.append(output_line("matches:", "builtin-subsection"))
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            host = str(row.get("host") or row.get("ip") or "-")
            port = str(row.get("port") or "").strip()
            protocol = str(row.get("protocol") or "").strip()
            title = _truncate(str(row.get("title") or row.get("app") or row.get("server") or "").strip(), 72)
            endpoint = f"{host}:{port}" if port else host
            suffix = " - ".join(part for part in (protocol, title) if part)
            lines.append(output_line(f"  {endpoint} {suffix}".rstrip(), "builtin-kv"))
    if payload.get("has_more"):
        lines.append(output_line("more results available from provider", "builtin-note"))
    return lines


def _format_greynoise(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = []
    message = str(payload.get("message") or "").strip()
    if message:
        lines.append(output_line(format_native_record("status", message, 14), "builtin-kv"))
    lines.extend([
        output_line(format_native_record("classification", str(payload.get("classification") or "unknown"), 14), "builtin-kv"),
        output_line(format_native_record("name", str(payload.get("name") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("last seen", str(payload.get("last_seen") or "-"), 14), "builtin-kv"),
    ])
    if isinstance(payload.get("noise"), bool):
        lines.append(output_line(format_native_record("noise", "yes" if payload.get("noise") else "no", 14), "builtin-kv"))
    if isinstance(payload.get("riot"), bool):
        lines.append(output_line(format_native_record("riot", "yes" if payload.get("riot") else "no", 14), "builtin-kv"))
    link = str(payload.get("link") or "").strip()
    if link:
        lines.append(output_line(format_native_record("link", link, 14), "builtin-kv"))
    return lines


def _format_censys(payload: dict[str, Any]) -> list[dict[str, object]]:
    autonomous_system = payload.get("autonomous_system")
    asn = autonomous_system if isinstance(autonomous_system, dict) else {}
    location = payload.get("location")
    place = location if isinstance(location, dict) else {}
    lines = [
        output_line(format_native_record("ports", _join_values(payload.get("ports")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("protocols", _join_values(payload.get("protocols")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("asn", str(asn.get("asn") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("org", str(asn.get("name") or asn.get("description") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("country", str(place.get("country") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("updated", str(payload.get("last_updated_at") or "-"), 14), "builtin-kv"),
    ]
    services = payload.get("services")
    if isinstance(services, list) and services:
        lines.append(output_line("services:", "builtin-subsection"))
        for row in services[:5]:
            if not isinstance(row, dict):
                continue
            port = str(row.get("port") or "?")
            transport = str(row.get("transport") or "-")
            protocol = str(row.get("protocol") or "-")
            software = _truncate(str(row.get("software") or "").strip(), 64)
            suffix = f" - {software}" if software else ""
            lines.append(output_line(f"  {port}/{transport} {protocol}{suffix}".rstrip(), "builtin-kv"))
    names = payload.get("names")
    if isinstance(names, list) and names:
        lines.append(output_line(format_native_record("names", _join_values(names) or "none", 14), "builtin-kv"))
    return lines


def _format_teamcymru(payload: dict[str, Any]) -> list[dict[str, object]]:
    return [
        output_line(format_native_record("asn", str(payload.get("asn") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("prefix", str(payload.get("prefix") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("registry", str(payload.get("registry") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("name", str(payload.get("name") or "-"), 14), "builtin-kv"),
    ]


def _format_otx(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("pulses", str(payload.get("pulse_count") or 0), 14), "builtin-kv"),
        output_line(format_native_record("reputation", str(payload.get("reputation")), 14), "builtin-kv"),
        output_line(format_native_record("tags", _join_values(payload.get("tags")) or "none", 14), "builtin-kv"),
    ]
    pulses = payload.get("pulses")
    if isinstance(pulses, list) and pulses:
        lines.append(output_line("pulses:", "builtin-subsection"))
        for pulse in pulses[:5]:
            if not isinstance(pulse, dict):
                continue
            name = _truncate(str(pulse.get("name") or pulse.get("id") or ""), 96)
            modified = str(pulse.get("modified") or "")
            suffix = f" ({modified})" if modified else ""
            lines.append(output_line(f"  {name}{suffix}".rstrip(), "builtin-kv"))
    return lines


def _format_abuseipdb(payload: dict[str, Any]) -> list[dict[str, object]]:
    score = payload.get("abuse_confidence_score")
    return [
        output_line(format_native_record("confidence", str(score) if score is not None else "-", 14), "builtin-kv"),
        output_line(format_native_record("reports", str(payload.get("total_reports") or 0), 14), "builtin-kv"),
        output_line(format_native_record("country", str(payload.get("country_code") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("usage", str(payload.get("usage_type") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("isp", str(payload.get("isp") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("tor", "yes" if payload.get("is_tor") else "no", 14), "builtin-kv"),
        output_line(format_native_record("last report", str(payload.get("last_reported_at") or "-"), 14), "builtin-kv"),
    ]


def _format_ipinfo(payload: dict[str, Any]) -> list[dict[str, object]]:
    country = str(payload.get("country") or payload.get("country_code") or "-")
    place_parts = [
        str(payload.get("city") or "").strip(),
        str(payload.get("region") or "").strip(),
    ]
    place = ", ".join(part for part in place_parts if part)
    return [
        output_line(format_native_record("asn", str(payload.get("asn") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("org", str(payload.get("org") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("domain", str(payload.get("domain") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("country", country, 14), "builtin-kv"),
        output_line(format_native_record("place", place or "-", 14), "builtin-kv"),
        output_line(format_native_record("hostname", str(payload.get("hostname") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("timezone", str(payload.get("timezone") or "-"), 14), "builtin-kv"),
    ]


def _format_virustotal_domain(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("reputation", str(payload.get("reputation")), 14), "builtin-kv"),
        output_line(format_native_record("analysis", _stats_summary(payload.get("last_analysis_stats")), 14), "builtin-kv"),
    ]
    urls = payload.get("recent_urls")
    if isinstance(urls, list) and urls:
        lines.append(output_line("recent urls:", "builtin-subsection"))
        for url in urls[:3]:
            lines.append(output_line(f"  {_truncate(str(url), 110)}", "builtin-kv"))
    whois = str(payload.get("whois") or "").strip().replace("\n", " ")
    if whois:
        lines.append(output_line(format_native_record("whois", _truncate(whois, 110), 14), "builtin-kv"))
    return lines


def _format_crtsh(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("certificates", str(payload.get("certificate_count") or 0), 14), "builtin-kv"),
        output_line(format_native_record("first seen", str(payload.get("first_seen") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("last seen", str(payload.get("last_seen") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("latest expiry", str(payload.get("latest_expiry") or "-"), 14), "builtin-kv"),
    ]
    names = payload.get("names")
    if isinstance(names, list) and names:
        lines.append(output_line("names:", "builtin-subsection"))
        for name in names[:8]:
            lines.append(output_line(f"  {name}", "builtin-kv"))
    issuers = payload.get("issuers")
    if isinstance(issuers, list) and issuers:
        lines.append(output_line(format_native_record("issuers", _join_values(issuers) or "none", 14), "builtin-kv"))
    return lines


def _format_tls_certificate(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("host", str(payload.get("host") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("port", str(payload.get("port") or 443), 14), "builtin-kv"),
        output_line(format_native_record("not before", str(payload.get("first_seen") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("not after", str(payload.get("latest_expiry") or "-"), 14), "builtin-kv"),
    ]
    issuer = str(payload.get("issuers", [""])[0] if isinstance(payload.get("issuers"), list) and payload.get("issuers") else "")
    if issuer:
        lines.append(output_line(format_native_record("issuer", _truncate(issuer, 110), 14), "builtin-kv"))
    fingerprint = str(payload.get("fingerprint_sha256") or "").strip()
    if fingerprint:
        lines.append(output_line(format_native_record("sha256", fingerprint, 14), "builtin-kv"))
    names = payload.get("names")
    if isinstance(names, list) and names:
        lines.append(output_line("names:", "builtin-subsection"))
        for name in names[:8]:
            lines.append(output_line(f"  {name}", "builtin-kv"))
    return lines


def _format_virustotal_hash(payload: dict[str, Any]) -> list[dict[str, object]]:
    return [
        output_line(format_native_record("verdict", str(payload.get("verdict") or "unknown"), 14), "builtin-kv"),
        output_line(format_native_record("analysis", _stats_summary(payload.get("last_analysis_stats")), 14), "builtin-kv"),
        output_line(format_native_record("type", str(payload.get("type_description") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("tags", _join_values(payload.get("tags")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("names", _join_values(payload.get("names")) or "none", 14), "builtin-kv"),
    ]


def _format_hibp(payload: dict[str, Any]) -> list[dict[str, object]]:
    count = int(payload.get("count") or 0)
    return [
        output_line(format_native_record("pwned", "yes" if count else "no", 14), "builtin-kv"),
        output_line(format_native_record("seen count", str(count), 14), "builtin-kv"),
        output_line(format_native_record("sent prefix", str(payload.get("prefix") or "-"), 14), "builtin-kv"),
    ]


def _format_nvd(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("severity", str(payload.get("severity") or "unknown"), 14), "builtin-kv"),
        output_line(format_native_record("score", str(payload.get("score") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("published", str(payload.get("published") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("modified", str(payload.get("last_modified") or "-"), 14), "builtin-kv"),
    ]
    description = str(payload.get("description") or "").strip().replace("\n", " ")
    if description:
        lines.append(output_line(format_native_record("summary", _truncate(description, 110), 14), "builtin-kv"))
    refs = payload.get("references")
    if isinstance(refs, list) and refs:
        lines.append(output_line("references:", "builtin-subsection"))
        for ref in refs[:5]:
            lines.append(output_line(f"  {_truncate(str(ref), 110)}", "builtin-kv"))
    return lines


def _format_vulners(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("severity", str(payload.get("severity") or "unknown"), 14), "builtin-kv"),
        output_line(format_native_record("score", str(payload.get("score") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("exploits", str(payload.get("exploit_count") or 0), 14), "builtin-kv"),
        output_line(format_native_record("published", str(payload.get("published") or "-"), 14), "builtin-kv"),
    ]
    title = str(payload.get("title") or "").strip()
    if title:
        lines.append(output_line(format_native_record("title", _truncate(title, 110), 14), "builtin-kv"))
    exploits = payload.get("exploits")
    if isinstance(exploits, list) and exploits:
        lines.append(output_line("exploits:", "builtin-subsection"))
        for item in exploits[:5]:
            if not isinstance(item, dict):
                continue
            label = _truncate(str(item.get("title") or item.get("id") or ""), 96)
            href = str(item.get("href") or "")
            suffix = f" - {href}" if href else ""
            lines.append(output_line(f"  {label}{suffix}".rstrip(), "builtin-kv"))
    refs = payload.get("references")
    if isinstance(refs, list) and refs:
        lines.append(output_line("references:", "builtin-subsection"))
        for ref in refs[:5]:
            lines.append(output_line(f"  {_truncate(str(ref), 110)}", "builtin-kv"))
    return lines


def _format_urlhaus_host(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("status", str(payload.get("query_status") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("urls", str(payload.get("url_count") or 0), 14), "builtin-kv"),
        output_line(format_native_record("payloads", str(payload.get("payload_count") or 0), 14), "builtin-kv"),
    ]
    urls = payload.get("urls")
    if isinstance(urls, list) and urls:
        lines.append(output_line("urls:", "builtin-subsection"))
        for item in urls[:5]:
            if not isinstance(item, dict):
                continue
            lines.append(output_line(
                f"  {_truncate(str(item.get('url') or ''), 110)} {str(item.get('status') or '')}".rstrip(),
                "builtin-kv",
            ))
    return lines


def _format_urlhaus_hash(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("status", str(payload.get("query_status") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("signature", str(payload.get("signature") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("file type", str(payload.get("file_type") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("urls", str(payload.get("url_count") or 0), 14), "builtin-kv"),
    ]
    payloads = payload.get("payloads")
    if isinstance(payloads, list) and payloads:
        lines.append(output_line("payloads:", "builtin-subsection"))
        for item in payloads[:5]:
            if not isinstance(item, dict):
                continue
            lines.append(output_line(
                f"  {_truncate(str(item.get('sha256') or ''), 72)} {str(item.get('signature') or '')}".rstrip(),
                "builtin-kv",
            ))
    return lines


def _format_urlhaus_url(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(
            format_native_record("status", str(payload.get("status") or payload.get("query_status") or "-"), 14),
            "builtin-kv",
        ),
        output_line(format_native_record("threat", str(payload.get("threat") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("host", str(payload.get("host") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("tags", _join_values(payload.get("tags")) or "none", 14), "builtin-kv"),
    ]
    payloads = payload.get("payloads")
    if isinstance(payloads, list) and payloads:
        lines.append(output_line("payloads:", "builtin-subsection"))
        for item in payloads[:5]:
            if not isinstance(item, dict):
                continue
            lines.append(output_line(
                f"  {_truncate(str(item.get('sha256') or ''), 72)} {str(item.get('signature') or '')}".rstrip(),
                "builtin-kv",
            ))
    return lines


def _format_threatfox(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("status", str(payload.get("query_status") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("iocs", str(payload.get("ioc_count") or 0), 14), "builtin-kv"),
        output_line(format_native_record("malware", _join_values(payload.get("malware")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("tags", _join_values(payload.get("tags")) or "none", 14), "builtin-kv"),
    ]
    iocs = payload.get("iocs")
    if isinstance(iocs, list) and iocs:
        lines.append(output_line("iocs:", "builtin-subsection"))
        for item in iocs[:5]:
            if not isinstance(item, dict):
                continue
            ioc = _truncate(str(item.get("ioc") or ""), 80)
            malware = str(item.get("malware") or "")
            threat_type = str(item.get("threat_type") or "")
            suffix = " - ".join(part for part in (threat_type, malware) if part)
            lines.append(output_line(f"  {ioc} {suffix}".rstrip(), "builtin-kv"))
    return lines


def _format_urlscan(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("results", str(payload.get("result_count") or 0), 14), "builtin-kv"),
        output_line(format_native_record("has more", "yes" if payload.get("has_more") else "no", 14), "builtin-kv"),
    ]
    results = payload.get("results")
    if isinstance(results, list) and results:
        lines.append(output_line("results:", "builtin-subsection"))
        for item in results[:5]:
            if not isinstance(item, dict):
                continue
            marker = "malicious" if item.get("malicious") else "observed"
            url = _truncate(str(item.get("url") or item.get("domain") or ""), 90)
            scan_id = str(item.get("scan_id") or "")
            lines.append(output_line(f"  {marker}: {url} {scan_id}".rstrip(), "builtin-kv"))
    return lines


def _format_securitytrails(payload: dict[str, Any]) -> list[dict[str, object]]:
    whois = payload.get("whois")
    dns = payload.get("dns")
    whois_obj = whois if isinstance(whois, dict) else {}
    dns_obj = dns if isinstance(dns, dict) else {}
    lines = [
        output_line(format_native_record("subdomains", str(payload.get("subdomain_count") or 0), 14), "builtin-kv"),
        output_line(format_native_record("registrar", str(whois_obj.get("registrar") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("created", str(whois_obj.get("created") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("expires", str(whois_obj.get("expires") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("a", _join_values(dns_obj.get("a")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("ns", _join_values(dns_obj.get("ns")) or "none", 14), "builtin-kv"),
    ]
    subdomains = payload.get("subdomains")
    if isinstance(subdomains, list) and subdomains:
        lines.append(output_line("subdomains:", "builtin-subsection"))
        for item in subdomains[:8]:
            lines.append(output_line(f"  {item}", "builtin-kv"))
    return lines


def _format_routeviews(payload: dict[str, Any]) -> list[dict[str, object]]:
    lines = [
        output_line(format_native_record("prefix", str(payload.get("prefix") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("rpki", str(payload.get("rpki") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("collectors", str(payload.get("collector_count") or 0), 14), "builtin-kv"),
    ]
    origins = payload.get("origins")
    if isinstance(origins, list) and origins:
        lines.append(output_line("origins:", "builtin-subsection"))
        for item in origins[:5]:
            if not isinstance(item, dict):
                continue
            asn = str(item.get("asn") or "")
            name = str(item.get("name") or "")
            collector = str(item.get("collector") or "")
            suffix = " - ".join(part for part in (name, collector) if part)
            lines.append(output_line(f"  AS{asn} {suffix}".rstrip(), "builtin-kv"))
    return lines


def _stats_summary(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    keys = ("malicious", "suspicious", "harmless", "undetected")
    return ", ".join(f"{key}={value.get(key, 0)}" for key in keys if key in value) or "none"


def _join_values(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item) for item in value[:12])


def _truncate(value: str, length: int) -> str:
    return value if len(value) <= length else value[: max(0, length - 3)] + "..."


def _provider_label(provider: str) -> str:
    return provider_label(provider)
