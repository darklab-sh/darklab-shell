# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed ordinary actions shared by assessments and one-off probes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BaseAction:
    """One reviewed ordinary action shared by every bounded launch surface."""

    action_id: str
    label: str
    purpose: str
    mode: str
    policy_level: str
    target_types: frozenset[str]
    required_features: frozenset[str]
    expected_evidence: frozenset[str]
    revision: str = "1"
    exclusions: tuple[str, ...] = field(default_factory=tuple)

def _action(
    action_id: str,
    label: str,
    purpose: str,
    mode: str,
    policy_level: str,
    target_types: set[str],
    expected_evidence: set[str],
    *,
    exclusions: tuple[str, ...] = (),
    required_features: set[str] | None = None,
) -> BaseAction:
    return BaseAction(
        action_id=action_id,
        label=label,
        purpose=purpose,
        mode=mode,
        policy_level=policy_level,
        target_types=frozenset(target_types),
        required_features=frozenset(required_features or {action_id}),
        expected_evidence=frozenset(expected_evidence),
        exclusions=exclusions,
    )


ACTIONS = {
    "curl": _action(
        "curl", "Curl headers", "Review one HTTP response without following redirects.",
        "head", "safe", {"domain", "ip", "url"}, {"http_response"},
    ),
    "ping": _action(
        "ping", "Ping", "Check whether one approved host responds.",
        "reachability", "safe", {"domain", "ip"}, {"run"},
    ),
    "dnsrecon": _action(
        "dnsrecon", "DNSRecon", "Collect standard DNS records for one domain.",
        "standard_records", "safe", {"domain"}, {"dns_records", "entities"},
    ),
    "gau": _action(
        "gau", "Gau", "Collect passive historical URLs without probing them.",
        "passive_urls", "safe", {"domain"}, {"urls"},
    ),
    "httpx": _action(
        "httpx", "HTTPx", "Review response metadata and detected web technologies.",
        "web_metadata", "safe", {"domain", "ip", "url"},
        {"http_responses", "services", "entities"},
    ),
    "katana": _action(
        "katana", "Katana", "Crawl one approved web target to depth one.",
        "shallow_crawl", "standard", {"domain", "url"}, {"urls"},
    ),
    "dalfox": _action(
        "dalfox", "Dalfox", "Discover parameters without sending XSS payloads.",
        "parameter_discovery", "standard", {"domain", "ip", "url"},
        {"http_parameters"},
        exclusions=("xss_payloads", "remote_wordlists", "oast"),
    ),
    "sqlmap": _action(
        "sqlmap", "SQLmap", "Run bounded detection-only SQL injection checks.",
        "detection_only", "standard", {"url"}, {"findings"},
        exclusions=("data_extraction", "os_takeover", "file_access"),
    ),
    "sslyze": _action(
        "sslyze", "SSLyze", "Review the certificate chain for one TLS host.",
        "certificate", "safe", {"domain", "ip"}, {"tls_certificate"},
    ),
    "testssl": _action(
        "testssl", "testssl", "Run a fast high-severity TLS review.",
        "fast_high_severity", "standard", {"domain", "ip"},
        {"tls_configuration", "findings"},
    ),
    "nmap": _action(
        "nmap", "Nmap", "Review the top 100 TCP ports and service versions.",
        "service_scan", "standard", {"domain", "ip"},
        {"ports", "services", "entities"},
        required_features={"nmap", "reviewed_nse_profiles"},
    ),
    "nuclei": _action(
        "nuclei", "Nuclei", "Run one reviewed local template profile.",
        "template_profile", "safe", {"domain", "ip", "url"}, {"findings"},
        exclusions=("oast", "automatic_template_updates"),
        required_features={"nuclei", "managed_nuclei_templates"},
    ),
}


def base_action(action_id: str) -> BaseAction | None:
    """Return one exact canonical action; aliases aren't accepted here."""
    return ACTIONS.get(str(action_id or "").strip().casefold())


def base_action_target_types(action_id: str) -> frozenset[str]:
    selected = base_action(action_id)
    return selected.target_types if selected else frozenset()


__all__ = [
    "ACTIONS",
    "BaseAction",
    "base_action",
    "base_action_target_types",
]
