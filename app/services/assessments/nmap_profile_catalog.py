# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed and validated Nmap NSE profile data."""

import re
from typing import Final

from services.assessments.nmap_profile_contracts import NmapProfile


ALLOWED_CATEGORY_SELECTORS: Final = frozenset({"safe", "default", "version", "discovery"})
EXCLUDED_CATEGORIES: Final = (
    "auth", "brute", "dos", "exploit", "external", "fuzzer", "intrusive",
)
_SELECTOR_RE: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _profile(
    key: str,
    label: str,
    selectors: tuple[str, ...],
    evidence_kinds: tuple[str, ...],
    *,
    selector_kind: str = "scripts",
    policy_level: str = "standard",
    requires_confirmation: bool = False,
) -> NmapProfile:
    return NmapProfile(
        key=key,
        label=label,
        policy_level=policy_level,
        selector_kind=selector_kind,
        selectors=selectors,
        evidence_kinds=evidence_kinds,
        requires_confirmation=requires_confirmation,
    )


PROFILES = {
    "safe": _profile("safe", "Safe NSE review", ("safe",), ("service_metadata",), selector_kind="category", policy_level="safe"),
    "default": _profile("default", "Default NSE review", ("default",), ("service_metadata",), selector_kind="category"),
    "version": _profile("version", "Version NSE review", ("version",), ("service_versions",), selector_kind="category"),
    "discovery": _profile("discovery", "Discovery NSE review", ("discovery",), ("service_metadata",), selector_kind="category"),
    "vuln": _profile(
        "vuln", "Reviewed vulnerability checks",
        ("ssl-heartbleed", "ssl-poodle", "smb-vuln-ms17-010"),
        ("vulnerability_checks",), requires_confirmation=True,
    ),
    "tls": _profile("tls", "TLS configuration", ("ssl-cert", "ssl-enum-ciphers"), ("tls_certificate", "tls_ciphers")),
    "ssh": _profile("ssh", "SSH algorithms and keys", ("ssh2-enum-algos", "ssh-hostkey"), ("ssh_algorithms", "ssh_host_keys")),
    "smtp": _profile("smtp", "SMTP capabilities", ("smtp-commands",), ("mail_capabilities",)),
    "smb": _profile(
        "smb", "SMB protocol and signing",
        (
            "smb-protocols", "smb-security-mode", "smb2-security-mode",
            "smb2-capabilities", "smb-os-discovery",
        ),
        ("smb_dialects", "smb_signing", "smb_identity"),
    ),
    "snmp": _profile("snmp", "SNMP service details", ("snmp-info",), ("snmp_metadata",)),
    "ldap": _profile("ldap", "LDAP Root DSE", ("ldap-rootdse",), ("ldap_root_dse",)),
    "nfs": _profile("nfs", "NFS exports", ("nfs-showmount",), ("nfs_exports",)),
    "rpc": _profile("rpc", "RPC program inventory", ("rpcinfo",), ("rpc_programs",)),
    "ftp": _profile("ftp", "FTP service details", ("ftp-syst",), ("ftp_capabilities",)),
    "dns": _profile("dns", "DNS server identity", ("dns-nsid",), ("dns_server_identity",)),
    "mysql": _profile("mysql", "MySQL service details", ("mysql-info",), ("database_metadata",)),
    "redis": _profile("redis", "Redis service details", ("redis-info",), ("database_metadata",)),
    "imap": _profile("imap", "IMAP capabilities", ("imap-capabilities",), ("mail_capabilities",)),
    "pop3": _profile("pop3", "POP3 capabilities", ("pop3-capabilities",), ("mail_capabilities",)),
}


def _validate_catalog() -> None:
    for key, profile in PROFILES.items():
        if key != profile.key or not _SELECTOR_RE.fullmatch(key):
            raise ValueError("invalid app-owned Nmap profile key")
        if profile.selector_kind not in {"category", "scripts"} or not profile.selectors:
            raise ValueError(f"invalid selector contract for Nmap profile: {key}")
        if any(not _SELECTOR_RE.fullmatch(selector) for selector in profile.selectors):
            raise ValueError(f"invalid selector in Nmap profile: {key}")
        if (
            profile.selector_kind == "category"
            and not set(profile.selectors) <= ALLOWED_CATEGORY_SELECTORS
        ):
            raise ValueError(f"unreviewed category in Nmap profile: {key}")
        if profile.selector_kind == "scripts" and set(profile.selectors) & set(EXCLUDED_CATEGORIES):
            raise ValueError(f"category selector used as a script in Nmap profile: {key}")


_validate_catalog()


__all__ = ["EXCLUDED_CATEGORIES", "PROFILES"]
