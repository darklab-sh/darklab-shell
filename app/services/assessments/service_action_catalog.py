# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed service-action metadata kept separate from registry behavior."""

# The catalog is intentionally a compact, reviewed data table.
# ruff: noqa: E501

from .service_actions import ServiceAction


def _action(key, label, rationale, command, targets):
    return ServiceAction(key, label, rationale, command, "standard", frozenset(targets))


ACTIONS = {
    "http": _action("http_profile", "Review HTTP surface", "The service identified an HTTP endpoint.", "command:httpx", {"domain", "ip", "url"}),
    "https": _action("https_profile", "Review HTTPS surface", "The service identified an HTTPS endpoint.", "command:httpx", {"domain", "ip", "url"}),
    "ssh": _action("ssh_enumeration", "Enumerate SSH safely", "The service fingerprint explicitly identified SSH.", "command:nmap", {"domain", "ip"}),
    "smtp": _action("smtp_enumeration", "Review SMTP service", "The service fingerprint explicitly identified SMTP.", "command:nmap", {"domain", "ip"}),
    "smb": _action("smb_enumeration", "Enumerate SMB safely", "The service fingerprint explicitly identified SMB.", "command:nmap", {"domain", "ip"}),
    "snmp": _action("snmp_enumeration", "Review SNMP service", "The service fingerprint explicitly identified SNMP.", "command:nmap", {"domain", "ip"}),
    "ldap": _action("ldap_enumeration", "Review LDAP service", "The service fingerprint explicitly identified LDAP.", "command:nmap", {"domain", "ip"}),
    "nfs": _action("nfs_enumeration", "Review NFS exports", "The service fingerprint explicitly identified NFS.", "command:nmap", {"domain", "ip"}),
    "rpcbind": _action("rpc_enumeration", "Review RPC services", "The service fingerprint explicitly identified RPC bind.", "command:nmap", {"domain", "ip"}),
    "ftp": _action("ftp_enumeration", "Review FTP service", "The service fingerprint explicitly identified FTP.", "command:nmap", {"domain", "ip"}),
    "dns": _action("dns_enumeration", "Review DNS service", "The service fingerprint explicitly identified DNS.", "command:nmap", {"domain", "ip"}),
    "mysql": _action("mysql_enumeration", "Review MySQL service", "The service fingerprint explicitly identified MySQL.", "command:nmap", {"domain", "ip"}),
    "postgresql": _action("postgresql_enumeration", "Review PostgreSQL service", "The service fingerprint explicitly identified PostgreSQL.", "command:nmap", {"domain", "ip"}),
    "redis": _action("redis_enumeration", "Review Redis service", "The service fingerprint explicitly identified Redis.", "command:nmap", {"domain", "ip"}),
    "imap": _action("imap_enumeration", "Review IMAP service", "The service fingerprint explicitly identified IMAP.", "command:nmap", {"domain", "ip"}),
    "pop3": _action("pop3_enumeration", "Review POP3 service", "The service fingerprint explicitly identified POP3.", "command:nmap", {"domain", "ip"}),
    "version-cve": _action("version_cve_correlation", "Review version-based CVEs", "A versioned observation can be matched against cached advisory data.", "evidence:version_cve_correlation", {"domain", "ip", "url"}),
}

ALIASES = {
    "http-alt": "http", "http-proxy": "http", "ssl/http": "https", "ssh?": "review",
    "microsoft-ds": "smb", "netbios-ssn": "smb", "msrpc": "rpcbind", "postgres": "postgresql",
    "postgresql?": "postgresql", "imap4": "imap", "pop3s": "pop3", "ssl/pop3": "pop3",
    "ssl/imap": "imap", "unknown": "review",
}
