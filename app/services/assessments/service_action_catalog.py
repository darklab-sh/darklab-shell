# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed service-action metadata kept separate from registry behavior."""

# The catalog is intentionally a compact, reviewed data table.
# ruff: noqa: E501

from .service_actions import ServiceAction


_SERVICE_UNSUPPORTED = (
    "ambiguous_service",
    "conflicting_service_evidence",
    "port_only_inference",
)


def _action(
    key,
    label,
    rationale,
    command,
    targets,
    *,
    required_features=(),
    expected_evidence=("structured_service_output", "atlas_service_entity"),
    unsupported_conditions=_SERVICE_UNSUPPORTED,
    nmap_profile="",
):
    return ServiceAction(
        key,
        label,
        rationale,
        command,
        "standard",
        frozenset(targets),
        frozenset(required_features),
        frozenset(expected_evidence),
        tuple(unsupported_conditions),
        nmap_profile,
    )


_NMAP_FEATURES = {"nmap", "reviewed_nse_profiles"}


ACTIONS = {
    "http": _action("http_profile", "Review HTTP surface", "The service identified an HTTP endpoint.", "command:httpx", {"domain", "ip", "url"}, required_features={"httpx", "confirmed_project_target"}, expected_evidence={"http_metadata", "atlas_service_entity"}),
    "https": _action("https_profile", "Review HTTPS surface", "The service identified an HTTPS endpoint.", "command:httpx", {"domain", "ip", "url"}, required_features={"httpx", "confirmed_project_target"}, expected_evidence={"http_metadata", "tls_metadata", "atlas_service_entity"}),
    "ssh": _action("ssh_enumeration", "Enumerate SSH safely", "The service fingerprint explicitly identified SSH.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="ssh"),
    "smtp": _action("smtp_enumeration", "Review SMTP service", "The service fingerprint explicitly identified SMTP.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="smtp"),
    "smb": _action("smb_enumeration", "Enumerate SMB safely", "The service fingerprint explicitly identified SMB.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="smb"),
    "snmp": _action("snmp_enumeration", "Review SNMP service", "The service fingerprint explicitly identified SNMP.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="snmp"),
    "ldap": _action("ldap_enumeration", "Review LDAP service", "The service fingerprint explicitly identified LDAP.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="ldap"),
    "nfs": _action("nfs_enumeration", "Review NFS exports", "The service fingerprint explicitly identified NFS.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="nfs"),
    "rpcbind": _action("rpc_enumeration", "Review RPC services", "The service fingerprint explicitly identified RPC bind.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="rpc"),
    "ftp": _action("ftp_enumeration", "Review FTP service", "The service fingerprint explicitly identified FTP.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="ftp"),
    "dns": _action("dns_enumeration", "Review DNS service", "The service fingerprint explicitly identified DNS.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="dns"),
    "mysql": _action("mysql_enumeration", "Review MySQL service", "The service fingerprint explicitly identified MySQL.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="mysql"),
    "postgresql": _action("postgresql_enumeration", "Review PostgreSQL service", "The service fingerprint explicitly identified PostgreSQL.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="version"),
    "redis": _action("redis_enumeration", "Review Redis service", "The service fingerprint explicitly identified Redis.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="redis"),
    "imap": _action("imap_enumeration", "Review IMAP service", "The service fingerprint explicitly identified IMAP.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="imap"),
    "pop3": _action("pop3_enumeration", "Review POP3 service", "The service fingerprint explicitly identified POP3.", "command:nmap", {"domain", "ip"}, required_features=_NMAP_FEATURES, nmap_profile="pop3"),
    "version-cve": _action("version_cve_correlation", "Review version-based CVEs", "A versioned observation can be matched against cached advisory data.", "evidence:version_cve_correlation", {"domain", "ip", "url"}, required_features={"cached_advisory_data", "version_identifier"}, expected_evidence={"version_observation", "cve_advisory_match"}, unsupported_conditions=("missing_version_identifier", "unsupported_advisory_source", "ambiguous_product")),
}

ALIASES = {
    "http-alt": "http", "http-proxy": "http", "ssl/http": "https", "ssh?": "review",
    "microsoft-ds": "smb", "netbios-ssn": "smb", "msrpc": "rpcbind", "postgres": "postgresql",
    "postgresql?": "postgresql", "imap4": "imap", "pop3s": "pop3", "ssl/pop3": "pop3",
    "ssl/imap": "imap", "unknown": "review",
}
