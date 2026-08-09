# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed Nuclei template profiles and fixed command arguments."""

from __future__ import annotations

from typing import Any, NamedTuple


class NucleiProfile(NamedTuple):
    key: str
    label: str
    policy_level: str
    severity: str
    template_families: tuple[str, ...]
    include_tags: tuple[str, ...]
    protocol_types: tuple[str, ...]
    excluded_tags: tuple[str, ...]
    excluded_protocols: tuple[str, ...]
    headless: bool = False
    dast: bool = False
    template_source: str = "managed_cache"
    requires_confirmation: bool = False


_READ_ONLY_EXCLUDED_TAGS = (
    "auth", "brute", "dos", "exploit", "fuzz", "intrusive", "oast", "dast",
)
_CODE_AND_LOCAL_PROTOCOLS = ("code", "javascript", "file", "workflow", "whois")
_PROFILES = {
    "safe": NucleiProfile(
        key="safe", label="Safe exposure review", policy_level="safe",
        severity="high,critical",
        template_families=("Exposure", "Misconfiguration", "Technology", "TLS"),
        include_tags=("exposure", "misconfig", "tech", "ssl"),
        protocol_types=("http", "tcp", "ssl"),
        excluded_tags=_READ_ONLY_EXCLUDED_TAGS,
        excluded_protocols=_CODE_AND_LOCAL_PROTOCOLS + ("headless",),
    ),
    "standard": NucleiProfile(
        key="standard", label="Standard vulnerability review", policy_level="standard",
        severity="medium,high,critical",
        template_families=(
            "Exposure", "Misconfiguration", "Known CVEs", "Technology",
            "Network services", "TLS", "API",
        ),
        include_tags=("exposure", "misconfig", "cve", "tech", "network", "ssl", "api"),
        protocol_types=("http", "tcp", "ssl"),
        excluded_tags=_READ_ONLY_EXCLUDED_TAGS,
        excluded_protocols=_CODE_AND_LOCAL_PROTOCOLS + ("headless",),
    ),
    "intrusive": NucleiProfile(
        key="intrusive", label="Intrusive headless and DAST review",
        policy_level="intrusive", severity="low,medium,high,critical",
        template_families=("Headless", "DAST"),
        include_tags=("intrusive", "headless", "dast", "fuzz"),
        protocol_types=("http", "headless"),
        excluded_tags=("auth", "brute", "dos", "exploit", "oast", "code"),
        excluded_protocols=_CODE_AND_LOCAL_PROTOCOLS,
        headless=True, dast=True, requires_confirmation=True,
    ),
}


def nuclei_profile_keys() -> tuple[str, ...]:
    return tuple(_PROFILES)


def nuclei_profile(profile: str = "safe") -> NucleiProfile:
    """Return a reviewed profile; unknown values fail closed to safe."""
    return _PROFILES.get(str(profile or "").strip().lower(), _PROFILES["safe"])


def nuclei_profile_args(profile: str = "safe") -> tuple[str, ...]:
    selected = nuclei_profile(profile)
    args = (
        "-severity", selected.severity, "-tags", ",".join(selected.include_tags),
        "-type", ",".join(selected.protocol_types),
        "-exclude-tags", ",".join(selected.excluded_tags),
        "-exclude-type", ",".join(selected.excluded_protocols),
        "-no-interactsh", "-disable-redirects", "-disable-update-check",
    )
    if selected.headless:
        args += ("-headless",)
    return (*args, "-dast", "-fuzz-aggression", "low") if selected.dast else args


def public_nuclei_profile(profile: str = "safe") -> dict[str, Any]:
    selected = nuclei_profile(profile)
    return {
        "key": selected.key, "label": selected.label,
        "policy_level": selected.policy_level,
        "template_source": selected.template_source,
        "template_families": list(selected.template_families),
        "excluded_tags": list(selected.excluded_tags),
        "excluded_protocols": list(selected.excluded_protocols),
        "headless": selected.headless, "dast": selected.dast,
        "update_policy": "explicit_only",
    }
