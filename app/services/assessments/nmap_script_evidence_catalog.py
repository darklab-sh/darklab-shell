# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact informational evidence families for reviewed Nmap NSE scripts."""

from typing import Final

from services.assessments.nmap_profile_catalog import PROFILES


INFORMATIONAL_SCRIPT_EVIDENCE: Final = {
    "ssl-cert": "tls_certificate",
    "ssl-enum-ciphers": "tls_ciphers",
    "ssh2-enum-algos": "ssh_algorithms",
    "ssh-hostkey": "ssh_host_keys",
    "smtp-commands": "mail_capabilities",
    "smb-protocols": "smb_dialects",
    "smb-security-mode": "smb_signing",
    "smb2-security-mode": "smb_signing",
    "smb2-capabilities": "smb_dialects",
    "smb-os-discovery": "smb_identity",
    "snmp-info": "snmp_metadata",
    "ldap-rootdse": "ldap_root_dse",
    "nfs-showmount": "nfs_exports",
    "rpcinfo": "rpc_programs",
    "ftp-syst": "ftp_capabilities",
    "ftp-anon": "anonymous_access",
    "dns-nsid": "dns_server_identity",
    "mysql-info": "database_metadata",
    "redis-info": "database_metadata",
    "imap-capabilities": "mail_capabilities",
    "pop3-capabilities": "mail_capabilities",
}


def _validate_evidence_catalog() -> None:
    vulnerability_scripts = set(PROFILES["vuln"].selectors)
    informational_scripts = {
        selector
        for profile in PROFILES.values()
        if profile.selector_kind == "scripts" and profile.key != "vuln"
        for selector in profile.selectors
    }
    if set(INFORMATIONAL_SCRIPT_EVIDENCE) != informational_scripts:
        raise ValueError("Nmap informational evidence catalog does not match reviewed profiles")
    if vulnerability_scripts & set(INFORMATIONAL_SCRIPT_EVIDENCE):
        raise ValueError("Nmap vulnerability scripts cannot emit informational evidence")


_validate_evidence_catalog()


__all__ = ["INFORMATIONAL_SCRIPT_EVIDENCE"]
