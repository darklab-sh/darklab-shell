# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Command output that must not produce saved entity metadata."""

from __future__ import annotations

import re


_NMAP_ENTITY_NOISE_RE = re.compile(
    r"^(?:Starting Nmap\b.*\bhttps://nmap\.org\b|"
    r"Service detection performed\. Please report any incorrect results at https://nmap\.org/submit/ \.|"
    r".*\bfollowing fingerprints? at https://nmap\.org/cgi-bin/submit\.cgi\?new-service\b.*|"
    r"SF:)", re.I)
_SQLMAP_ENTITY_NOISE_RE = re.compile(
    r"^(?:(?:\[\d{2}:\d{2}:\d{2}\]\s+)?\[WARNING\]\s+you've provided target URL without any GET parameters "
    r"\(e\.g\. 'http://(?:www\.)?site\.com/article\.php\?id=1'\) and without providing any POST parameters "
    r"through option '--data'|\|_\|V\.\.\.\s+\|_\|\s+https://sqlmap\.org/?)\s*$", re.I)
_HTTPX_ENTITY_NOISE_RE = re.compile(
    r"^\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+INFO\s+Model not found, downloading "
    r"url=https://huggingface\.co/datasets/happyhackingspace/dit/resolve/main/model\.json "
    r"dest=/tmp/\.dit/model\.json\s*$", re.I)
_TESTSSL_ENTITY_NOISE_RE = re.compile(
    r"^(?:Using\s+OpenSSL\b.*|"
    r"on\s+\S+:/opt/testssl\.sh/bin/openssl\.\S+|"
    r"testssl version \S+ from https://testssl\.sh/?|"
    r"Please file bugs @ https://testssl\.sh/bugs/?|"
    r"(?:Certificate Revocation List|OCSP URI)\s+"
    r"https?://(?:[a-z0-9-]+\.)+lencr\.org(?:/\S*)?|"
    r".*https://search\.censys\.io/search\?\S+|"
    r"Specification documentation\s+"
    r"https://github\.com/ssllabs/research/wiki/SSL-Server-Rating-Guide/?"
    r")\s*$", re.I)
_WHOIS_ENTITY_NOISE_RE = re.compile(
    r"^(?:(?:Registrar WHOIS Server|Registrar URL|Name Server):\s+\S+|"
    r"Domain Status:\s+\S+\s+https://icann\.org/epp(?:#\S+)?|.*https://(?:icann\.org/(?:epp|wicf/?)|"
    r"www\.identity\.digital/about/policies/whois-layered-access/|www\.namecheap\.com/?))", re.I)
_COMMAND_ENTITY_EXCLUDES = {
    "httpx": _HTTPX_ENTITY_NOISE_RE, "nmap": _NMAP_ENTITY_NOISE_RE,
    "sqlmap": _SQLMAP_ENTITY_NOISE_RE, "testssl": _TESTSSL_ENTITY_NOISE_RE,
    "whois": _WHOIS_ENTITY_NOISE_RE,
}


def command_output_excludes_entities(root: str, text: str) -> bool:
    """Return whether known command boilerplate contains example entities."""
    pattern = _COMMAND_ENTITY_EXCLUDES.get(root)
    return bool(pattern and pattern.search(text))
