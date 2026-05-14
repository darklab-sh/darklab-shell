"""App-native external intel built-in command handlers."""

from __future__ import annotations

import ipaddress
from typing import Any

from services.commands.builtins_format import format_native_record, output_line
from services.commands.registry import split_command_argv
from services.intel.canonical import CanonicalizationError
from services.intel.lookup import IntelLookupResult, ProviderLookup, lookup_entity
from services.intel.registry import provider_label


def run_builtin_intel(command: str, session_id: str) -> tuple[list[dict[str, str]], int]:
    parts = split_command_argv(command)
    if len(parts) <= 1 or parts[1].lower() in {"help", "-h", "--help"}:
        return _intel_usage(), 0

    entity_type = parts[1].lower()
    if entity_type not in {"ip", "domain", "hash", "cve"}:
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
        result = lookup_entity(entity_type, raw_value, session_id=session_id)
    except CanonicalizationError as exc:
        message = "Hash must be hex MD5/SHA1/SHA256" if entity_type == "hash" else str(exc)
        return [output_line(f"intel: {message}")], 1

    lines = _format_lookup_result(result)
    exit_code = 0 if result.success_count or result.configured_count else 1
    return lines, exit_code


def _intel_usage() -> list[dict[str, str]]:
    return [
        output_line("Intel commands:", "builtin-section"),
        output_line("  intel ip <ip> [--include-private]", "builtin-help-row"),
        output_line("  intel domain <domain>", "builtin-help-row"),
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


def _format_lookup_result(result: IntelLookupResult) -> list[dict[str, str]]:
    lines = [
        output_line(
            f"Intel lookup: {result.entity_type} {result.canonical_value}",
            "builtin-section",
        ),
    ]
    for provider in result.providers:
        lines.extend(_format_provider_lookup(provider, result.entity_type))
    if result.providers and result.configured_count == 0:
        lines.append(output_line("No providers are configured for this lookup.", "builtin-note"))
        lines.append(output_line("Use `secret show-consumers` to see accepted secret names.", "builtin-note"))
    return lines


def _format_provider_lookup(provider: ProviderLookup, entity_type: str) -> list[dict[str, str]]:
    label = _provider_label(provider.provider)
    if provider.status == "missing_secret":
        return [output_line(f"{label}: not configured - {provider.message}", "builtin-note")]
    if provider.status in {"rate_limited", "quota_exhausted", "error"}:
        return [output_line(f"{label}: {provider.message}", "builtin-warning")]
    if provider.result is None:
        return [output_line(f"{label}: no result", "builtin-note")]

    cache_label = "cache hit" if provider.result.cache_hit else "cache miss"
    lines = [output_line(f"{label}: {cache_label}", "builtin-subsection")]
    provider_payload = provider.result.payload.get("providers", {}).get(provider.provider, {})
    if not isinstance(provider_payload, dict):
        return [*lines, output_line("  no provider data returned", "builtin-note")]
    if entity_type == "ip" and provider.provider == "shodan":
        lines.extend(_format_shodan(provider_payload))
    elif entity_type == "ip" and provider.provider == "censys":
        lines.extend(_format_censys(provider_payload))
    elif entity_type == "ip" and provider.provider == "greynoise":
        lines.extend(_format_greynoise(provider_payload))
    elif entity_type == "ip" and provider.provider == "otx":
        lines.extend(_format_otx(provider_payload))
    elif entity_type == "ip" and provider.provider == "abuseipdb":
        lines.extend(_format_abuseipdb(provider_payload))
    elif entity_type == "ip" and provider.provider == "teamcymru":
        lines.extend(_format_teamcymru(provider_payload))
    elif entity_type == "domain" and provider.provider == "virustotal":
        lines.extend(_format_virustotal_domain(provider_payload))
    elif entity_type == "domain" and provider.provider == "otx":
        lines.extend(_format_otx(provider_payload))
    elif entity_type == "domain" and provider.provider == "crtsh":
        lines.extend(_format_crtsh(provider_payload))
    elif entity_type == "hash" and provider.provider == "virustotal":
        lines.extend(_format_virustotal_hash(provider_payload))
    elif entity_type == "hash" and provider.provider == "otx":
        lines.extend(_format_otx(provider_payload))
    elif entity_type == "hash" and provider.provider == "hibp":
        lines.extend(_format_hibp(provider_payload))
    elif entity_type == "cve" and provider.provider == "nvd":
        lines.extend(_format_nvd(provider_payload))
    else:
        lines.append(output_line("  no formatter for provider data", "builtin-note"))
    return lines


def _format_shodan(payload: dict[str, Any]) -> list[dict[str, str]]:
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


def _format_greynoise(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        output_line(format_native_record("classification", str(payload.get("classification") or "unknown"), 14), "builtin-kv"),
        output_line(format_native_record("name", str(payload.get("name") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("last seen", str(payload.get("last_seen") or "-"), 14), "builtin-kv"),
    ]


def _format_censys(payload: dict[str, Any]) -> list[dict[str, str]]:
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


def _format_teamcymru(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        output_line(format_native_record("asn", str(payload.get("asn") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("prefix", str(payload.get("prefix") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("registry", str(payload.get("registry") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("name", str(payload.get("name") or "-"), 14), "builtin-kv"),
    ]


def _format_otx(payload: dict[str, Any]) -> list[dict[str, str]]:
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


def _format_abuseipdb(payload: dict[str, Any]) -> list[dict[str, str]]:
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


def _format_virustotal_domain(payload: dict[str, Any]) -> list[dict[str, str]]:
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


def _format_crtsh(payload: dict[str, Any]) -> list[dict[str, str]]:
    lines = [
        output_line(format_native_record("certificates", str(payload.get("certificate_count") or 0), 14), "builtin-kv"),
        output_line(format_native_record("first seen", str(payload.get("first_seen") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("last seen", str(payload.get("last_seen") or "-"), 14), "builtin-kv"),
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


def _format_virustotal_hash(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        output_line(format_native_record("verdict", str(payload.get("verdict") or "unknown"), 14), "builtin-kv"),
        output_line(format_native_record("analysis", _stats_summary(payload.get("last_analysis_stats")), 14), "builtin-kv"),
        output_line(format_native_record("type", str(payload.get("type_description") or "-"), 14), "builtin-kv"),
        output_line(format_native_record("tags", _join_values(payload.get("tags")) or "none", 14), "builtin-kv"),
        output_line(format_native_record("names", _join_values(payload.get("names")) or "none", 14), "builtin-kv"),
    ]


def _format_hibp(payload: dict[str, Any]) -> list[dict[str, str]]:
    count = int(payload.get("count") or 0)
    return [
        output_line(format_native_record("pwned", "yes" if count else "no", 14), "builtin-kv"),
        output_line(format_native_record("seen count", str(count), 14), "builtin-kv"),
        output_line(format_native_record("sent prefix", str(payload.get("prefix") or "-"), 14), "builtin-kv"),
    ]


def _format_nvd(payload: dict[str, Any]) -> list[dict[str, str]]:
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
