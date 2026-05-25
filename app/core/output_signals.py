"""Server-side output signal classification.

The browser renders and navigates signals, but the backend owns the command
output semantics so live streams, history restores, shares, and future exports
can agree on what counts as a finding, warning, error, or summary line.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import ipaddress
import re
from urllib.parse import urlparse

from services.runs.output_model import LineRole
from services.intel.canonical import (
    CanonicalizationError,
    canonical_cve,
    canonical_domain,
    canonical_hash,
    canonical_ip,
    canonical_url,
    detect_hash_algorithm,
)


SIGNAL_SCOPES = ("findings", "warnings", "errors", "summaries")

_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")

_SIGNAL_PATTERNS = {
    "findings": [
        re.compile(r"^\d+/(?:tcp|udp)\s+open\b", re.I),
        re.compile(r"\bdiscovered open port\b", re.I),
        re.compile(r"^\S+\s+\[[^\]]+\]\s+\d+\s+\([^)]+\)\s+open\b", re.I),
        re.compile(r"\[(?:info|low|medium|high|critical)\]", re.I),
        re.compile(r"^\s*/\S+\s+\[status:\s*\d{3}\b", re.I),
        re.compile(r"\bHTTP/[\d.]+\s+\d{3}\b", re.I),
        re.compile(r"\bVULNERABLE\b", re.I),
        re.compile(r"\bnot vulnerable\b", re.I),
        re.compile(r"\bverify return code:\s*0\b", re.I),
        re.compile(r"\bnotAfter=", re.I),
        re.compile(r"^\S+\.\s+\d+\s+(?:IN\s+)?(?:A|AAAA|CNAME|MX|NS|TXT|SOA|PTR)\b", re.I),
        re.compile(r"^\S+\s+(?:A|AAAA|CNAME|MX|NS|TXT|SOA|PTR)\s+\S+"),
        re.compile(r"^\S+\s+has address\s+[0-9a-f:.]+\b", re.I),
        re.compile(r"^\S+\s+mail is handled by\s+\d+\s+\S+", re.I),
        re.compile(r"\bService Info:", re.I),
        re.compile(r"\bOS details:", re.I),
        re.compile(r"\bssl-issuer\b", re.I),
    ],
    "warnings": [
        re.compile(r"\bwarning\b", re.I),
        re.compile(r"\bwarn\b", re.I),
        re.compile(r"\bnote:", re.I),
        re.compile(r"\bunreliable\b", re.I),
        re.compile(r"\bretrying\b", re.I),
        re.compile(r"\brate limited\b", re.I),
    ],
    "errors": [
        re.compile(r"\berror\b", re.I),
        re.compile(r"\bfailed\b", re.I),
        re.compile(r"\bdenied\b", re.I),
        re.compile(r"\btimeout\b", re.I),
        re.compile(r"\bunreachable\b", re.I),
        re.compile(r"\brefused\b", re.I),
        re.compile(r"\bcannot write\b", re.I),
        re.compile(r"\bread-only file system\b", re.I),
        re.compile(r"no servers could be reached", re.I),
        re.compile(r"\bcould not\b", re.I),
        re.compile(r"\binvalid\b", re.I),
        re.compile(r"\bstalled\b", re.I),
    ],
    "summaries": [
        re.compile(r"\bsummary\b", re.I),
        re.compile(r"\bNmap done:\b", re.I),
        re.compile(r"\bhosts? up\b", re.I),
        re.compile(r"\bpacket loss\b", re.I),
        re.compile(r"\brtt min/avg/max\b", re.I),
        re.compile(r"\berrors?:\s*\d+\b", re.I),
        re.compile(r"\bfound:\s*\d+\b", re.I),
        re.compile(r"\bTotal requests:\b", re.I),
        re.compile(r"\bDuration:\b", re.I),
        re.compile(r"\bRequests/sec:\b", re.I),
        re.compile(r"\bProcessed Requests:\b", re.I),
    ],
}

_FINDINGS_EXCLUDES = [
    re.compile(r"^Starting Nmap", re.I),
    re.compile(r"^Nmap \d", re.I),
    re.compile(r"^Nmap scan initiated", re.I),
    re.compile(r"^Progress:\s*", re.I),
    re.compile(r"^:: Progress:", re.I),
    re.compile(r"^Fuzz Faster U Fool", re.I),
    re.compile(r"^Templates loaded for current scan", re.I),
    re.compile(r"^Using Interactsh Server", re.I),
    re.compile(r"^; <<>> DiG", re.I),
    re.compile(r"^;;", re.I),
    re.compile(r"^Usage:\s+", re.I),
    re.compile(r"^usage:\s+", re.I),
    re.compile(r"^\[options\]$", re.I),
    re.compile(r"^the tool you love", re.I),
    re.compile(r"^rustscan$", re.I),
    re.compile(r"^Testing SSL server", re.I),
    re.compile(r"^CHECKING CONNECTIVITY", re.I),
    re.compile(r"^OpenSSL$", re.I),
    re.compile(r"^projectdiscovery\.io$", re.I),
]

_APP_SIGNAL_EXCLUDES = [
    re.compile(r"^\[workspace\]\s+(?:reading|writing)\s+\S", re.I),
]

_DNS_SIGNAL_ROOTS = {"dig", "host", "nslookup"}
_CRAWL_URL_ROOTS = {"katana"}
_PROJECTDISCOVERY_ROOTS = {"chaos", "dnsx", "httpx", "katana", "naabu", "nuclei", "subfinder"}
_HTTPX_RESULT_RE = re.compile(r"^https?://\S+\s+\[\d{3}\](?:\s+\[[^\]]*\])*", re.I)
_PROJECTDISCOVERY_ENTITY_NOISE_RE = re.compile(
    r"^(?:\s*projectdiscovery\.io|\[INF\]\s+Using\s+Interactsh\s+Server:\s+oast\.site)\s*$",
    re.I,
)
_GOBUSTER_RESULT_RE = re.compile(
    r"^\S(?:.*\S)?\s+\(Status:\s*\d{3}\)\s+\[Size:\s*\d+\](?:\s+\[-->\s+\S+\])?$",
    re.I,
)
_GOBUSTER_CONFIG_RE = re.compile(
    r"^\[\+\]\s+(?:Url|Method|Threads|Wordlist|Negative Status codes|User Agent|Timeout):\s+.+$",
    re.I,
)
_WAFW00F_RESULT_RE = re.compile(r"^\[\+\]\s+The site\s+https?://\S+\s+is behind\s+.+\bWAF\.", re.I)
_WAFW00F_REQUESTS_RE = re.compile(r"^\[~\]\s+Number of requests:\s*\d+\b", re.I)
_NIKTO_SKIP_RE = re.compile(
    r"^\+\s+(?:Start Time|End Time|1 host\(s\) tested|ERROR|No CGI Directories found|Scan terminated):?",
    re.I,
)
_NIKTO_FINDING_RE = re.compile(
    r"^(?:\+\s+(?:Target IP|Target Hostname|Target Port|SSL Info|Server|Platform):|"
    r"(?:CN|SAN|Ciphers|Issuer):\s+)",
    re.I,
)
_WPSCAN_API_TOKEN_WARNING_RE = re.compile(r"^\[!\]\s+No WPScan API Token\b", re.I)
_WPSCAN_SKIP_RE = re.compile(
    r"^\[\+\]\s+(?:Started|Finished|Requests Done|Cached Requests|Data Sent|Data Received|Memory used|Elapsed time|"
    r"Enumerating|Checking Plugin Versions)",
    re.I,
)
_WPSCAN_FINDING_RE = re.compile(
    r"^\[\+\]\s+(?:Headers|robots\.txt found:|XML-RPC seems to be enabled:|WordPress readme found:|"
    r"Debug Log found:|The external WP-Cron seems to be enabled:|WordPress version .* identified|"
    r"WordPress theme in use:)",
    re.I,
)
_TESTSSL_FINDING_RE = re.compile(
    r"^(?:TLS\s+1(?:\.\d)?\s+offered|ALPN/HTTP2\b|Forward Secrecy\b|FS is offered|"
    r"Elliptic curves offered:|Common Name \(CN\)|subjectAltName \(SAN\)|Trust \(hostname\)|"
    r"Certificate Validity \(UTC\)|Issuer\s+|HTTP Status Code|Strict Transport Security|Server banner|"
    r"Overall Grade|ROBOT\s+|Secure Renegotiation|BREACH \(CVE-|LOGJAM \(CVE-)",
    re.I,
)
_TESTSSL_ENTITY_NOISE_RE = re.compile(
    r"^(?:Using\s+OpenSSL\b.*|on\s+\S+:/opt/testssl\.sh/bin/openssl\.\S+)\s*$",
    re.I,
)
_SSLSCAN_FINDING_RE = re.compile(
    r"^(?:TLSv1\.[23]\s+enabled|Server supports TLS Fallback SCSV|(?:Preferred|Accepted)\s+TLSv1\.[23]\s+|"
    r"Signature Algorithm:|RSA Key Strength:|Subject:|Altnames:|Issuer:|Not valid before:|Not valid after:)",
    re.I,
)
_SSLYZE_FINDING_RE = re.compile(
    r"^(?:Common Name:|Issuer:|Not Before:|Not After:|Key Size:|SubjAltName - DNS Names:|"
    r"Received Chain:|Verified Chain:|TLS_[A-Z0-9_]+\s+\d+\s+|Forward Secrecy\s+OK - Supported|"
    r"TLS_FALLBACK_SCSV:\s+OK - Supported|Supported curves:)",
    re.I,
)
_HOST_PORT_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}:\d+$", re.I)
_RUSTSCAN_OPEN_RE = re.compile(r"^Open\s+[0-9a-f:.]+:\d+$", re.I)
_NAABU_FOUND_PORTS_RE = re.compile(r"^\[INF\]\s+Found\s+\d+\s+ports?\s+on host\b", re.I)
_NUCLEI_RESULT_RE = re.compile(r"^\[[^\]]+\]\s+\[[a-z0-9_-]+\]\s+\[(?:info|low|medium|high|critical)\]\s+\S+", re.I)
_SCAN_COMPLETED_RE = re.compile(r"^\[INF\]\s+Scan completed\b.*\bmatches found\.", re.I)
_MASSCAN_STARTUP_RE = re.compile(
    r"^(?:Starting masscan\b|Initiating SYN Stealth Scan|Scanning\s+\d+\s+hosts?\s+\[\d+\s+ports/host\])",
    re.I,
)
_MASSCAN_RATE_RE = re.compile(r"^rate:\s+.*\bdone\b.*\bfound=\d+\b", re.I)
_FFUF_PROGRESS_RE = re.compile(r"^::\s*Progress:\s*\[\d+/\d+\]\s*::", re.I)
_FFUF_PROGRESS_DETAIL_RE = re.compile(
    r"^::\s*Progress:\s*\[(\d+)/(\d+)\]\s*::.*\bErrors:\s*(\d+)\s*::",
    re.I,
)
_FFUF_RESULT_RE = re.compile(
    r"^(.+?)\s+\[Status:\s*(\d{3}),\s*Size:\s*\d+,\s*Words:\s*\d+,\s*Lines:\s*\d+,\s*Duration:\s*[^\]]+\]$",
    re.I,
)
_FFUF_CONFIG_RE = re.compile(
    r"^::\s+(?:Method|URL|Wordlist|Follow redirects|Calibration|Timeout|Threads|Matcher)\s+:\s+\S",
    re.I,
)
_FFUF_SEPARATOR_RE = re.compile(r"^_{8,}$")
_FFUF_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+(?:[-.\w]*)?$", re.I)
_FFUF_ASCII_BANNER_RE = re.compile(r"^[\\/\s_'.,{}()|]+$")
_CLEAN_HTTP_URL_RE = re.compile(r"^https?://\S+$", re.I)
_URL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_URL_TAIL_RE = re.compile(r"[/?#].*$")
_SHELL_TEMPLATE_URL_NOISE_RE = re.compile(r"(?:'\+|\+'\$|/\$1\b)")
_FIERCE_FINDING_RE = re.compile(r"^(?:Found:|NS:|SOA:)\s+\S+", re.I)
_DNSRECON_FINDING_RE = re.compile(r"^\[\*\]\s+DNSSEC is configured for\s+\S+", re.I)
_WHOIS_FINDING_RE = re.compile(
    r"^(?:Domain Name|Registrar WHOIS Server|Registrar URL|Registrar|Registrar IANA ID|"
    r"Registrar Abuse Contact (?:Email|Phone)|Domain Status|Name Server):\s+\S|"
    r"^DNSSEC:\s+(?!unsigned\b)\S",
    re.I,
)
_WHOIS_SUMMARY_RE = re.compile(
    r"^(?:Updated Date|Creation Date|Registry Expiry Date|Expiry Date|Expiration Date|"
    r"Registrar Registration Expiration Date):\s+\S|"
    r"^>>>\s+Last update of WHOIS database:",
    re.I,
)
_WHOIS_WARNING_RE = re.compile(
    r"^DNSSEC:\s+unsigned\b|"
    r"^Domain Status:\s+(?:clientHold|serverHold|redemptionPeriod|pendingDelete|inactive)\b",
    re.I,
)
_WGET_FINDING_RE = re.compile(
    r"^Resolving\s+\S+.*\.\.\.\s+\S|"
    r"^\s*HTTP/\d(?:\.\d)?\s+\d{3}\b|"
    r"^\s*(?:Server|Content-Type):\s+\S",
    re.I,
)
_WGET_SUMMARY_RE = re.compile(
    r"^Connecting to .*\.\.\. connected\.|"
    r"^\s*Content-Length:\s*\d+\b|"
    r"^Length:\s*\d+\s+\[[^\]]+\]",
    re.I,
)
_SHODAN_DNS_RECORD_TYPES = {"A", "AAAA", "CNAME", "MX", "NS", "SOA", "TXT"}
_SHODAN_DNS_FINDING_TYPES = {"A", "AAAA", "CNAME", "MX", "NS", "SOA"}
_SHODAN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.I)
_SHODAN_HOST_IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_SHODAN_HOSTNAME_RE = re.compile(r"^Hostnames:\s+\S", re.I)
_SHODAN_PORT_RE = re.compile(r"^\s*\d+/(?:tcp|udp)(?:\s+\S.*)?$", re.I)
_SHODAN_HTTP_TITLE_RE = re.compile(r"^\s*\|--\s+HTTP title:\s+\S", re.I)
_SHODAN_HOST_SUMMARY_RE = re.compile(
    r"^(?:(?:City|Country|Organization|Updated|Number of open ports):\s+\S|Ports:\s*$)",
    re.I,
)
_SHODAN_WEAK_MAIL_POLICY_RE = re.compile(
    r"\bv=DMARC1\b[^;\n]*(?:;\s*)?p=none\b|"
    r"\bv=spf1\b.*(?:~all|\?all)\b",
    re.I,
)
_SHODAN_HTTP_WARNING_RE = re.compile(
    r"HTTP title:.*(?:\b5\d\d\b|Service Temporarily Unavailable|Index of /|Default Page)",
    re.I,
)
_IPINFO_FINDING_RE = re.compile(r"^-\s+(?:IP|Hostname|Organization)\s+\S", re.I)
_IPINFO_SUMMARY_RE = re.compile(
    r"^-\s+(?:Anycast|City|Region|Country|Currency|Location|Postal|Timezone)\s+\S",
    re.I,
)
_OPENSSL_FINDING_RE = re.compile(
    r"^(?:Connecting to\s+\S+|"
    r"depth=\d+\s+.*\bCN=|"
    r"\s*(?:\d+\s+)?[is]:.+|"
    r"\s*a:PKEY:\s+.+|"
    r"\s*v:NotBefore:\s+.+\bNotAfter:\s+.+|"
    r"subject=.+|"
    r"issuer=.+|"
    r"Peer signing digest:\s+\S+|"
    r"Peer signature type:\s+\S+|"
    r"Negotiated TLS[^\s]* group:\s+\S+|"
    r"New,\s*TLS[^,]+,\s*Cipher is\s+\S+|"
    r"Protocol:\s+\S+|"
    r"Server public key is\s+\d+\s+bit|"
    r"Verify return code:\s*0\b)",
    re.I,
)
_OPENSSL_WARNING_RE = re.compile(
    r"^(?:No ALPN negotiated|"
    r"Verification error:.+|"
    r"Verify return code:\s*(?!0\b)\d+|"
    r"verify error:num=.+|"
    r"Protocol:\s*(?:SSLv[^\s,]*|TLSv1(?:\.0|\.1)?\b(?!\.))|"
    r"New,.*Cipher is.*(?:RC4|3DES|NULL|EXPORT|MD5|DES-CBC3)|"
    r"Server public key is\s+(?:[1-9]\d{0,2}|10[0-1]\d|102[0-4])\s+bit|"
    r"Compression:\s+(?!NONE\b)\S+)",
    re.I,
)
_OPENSSL_SUMMARY_RE = re.compile(
    r"^(?:Certificate chain|"
    r"Server certificate|"
    r"No client certificate CA names sent|"
    r"verify return:1|"
    r"SSL handshake has read\s+\d+\s+bytes and written\s+\d+\s+bytes|"
    r"Verification:\s+OK|"
    r"This TLS version forbids renegotiation\.|"
    r"Compression:\s+NONE|"
    r"Expansion:\s+NONE|"
    r"Early data was not sent|"
    r"DONE)$",
    re.I,
)
_OPENSSL_PEM_BOUNDARY_RE = re.compile(r"^-{5}(?:BEGIN|END) CERTIFICATE-{5}$")
_OPENSSL_PEM_BODY_RE = re.compile(r"^[A-Za-z0-9+/]{32,}={0,2}$")
_OPENSSL_CONNECTED_RE = re.compile(r"^CONNECTED\([0-9A-Fa-f]+\)$")
_NIKTO_PLUS_LINE_RE = re.compile(r"^\+\s+\S")
_FLAG_ASSIGNMENT_RE = re.compile(r"^([^=]+)=(.+)$")
_NSLOOKUP_SERVER_RE = re.compile(r"^server$", re.I)
_FUZZ_SUFFIX_RE = re.compile(r"/FUZZ\b.*$", re.I)
_NMAP_OUTPUT_PREFIX_RE = re.compile(r"^-o[AGNX]$", re.I)
_PORT_LIST_RE = re.compile(r"^\d+(?:,\d+)*$")
_PORT_RANGE_RE = re.compile(r"^\d+(?:-\d+)?$")
_NMAP_DONE_RE = re.compile(r"^Nmap done:\b", re.I)
_NMAP_RDNS_RE = re.compile(r"^rDNS record for\s+\S+:\s+\S+", re.I)
_NMAP_HOST_UP_RE = re.compile(r"^Host is up\b", re.I)
_KILLED_BY_USER_RE = re.compile(r"^\[killed by user(?:\b|[^\w])", re.I)
_DNS_MAIL_EXCHANGER_RE = re.compile(r"\bmail exchanger\s*=\s*\S+", re.I)
_DNS_TEXT_RE = re.compile(r"\btext\s*=\s*.+", re.I)
_DNS_CANONICAL_NAME_RE = re.compile(r"\bcanonical name\s*=\s*\S+", re.I)
_DNS_ADDRESS_RE = re.compile(r"^Address(?:es)?:\s+[0-9a-f:.]+\b", re.I)
_DNS_NAME_RE = re.compile(r"^Name:\s+\S+", re.I)
_DIG_HEADER_RE = re.compile(r"^;;\s+->>HEADER<<-.*\bstatus:\s*(\S+)", re.I)
_DIG_ZERO_ANSWER_RE = re.compile(r"^;;\s+flags:.*\bANSWER:\s*0\b", re.I)
_DIG_SUMMARY_RE = re.compile(
    r"^;;\s+(?:Query time:\s+\d+\s+msec|SERVER:\s+\S+|MSG SIZE\s+rcvd:\s+\d+)\b",
    re.I,
)
_DIG_WARNING_STATUSES = {"NXDOMAIN", "SERVFAIL", "REFUSED", "FORMERR", "NOTIMP", "TIMEOUT"}
_NSLOOKUP_SUMMARY_RE = re.compile(r"^(?:Server:\s+\S|Non-authoritative answer:|Name:\s+\S)", re.I)
_NSLOOKUP_WARNING_RE = re.compile(r"^(?:\*\*\s+server can't find\b|;;\s+connection timed out\b)", re.I)
_NSLOOKUP_ADDRESS_RE = re.compile(r"^Address(?:es)?:\s+([0-9a-f:.]+)\b", re.I)
_CIDR_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}$")
_DNS_BARE_IP_RE = re.compile(
    r"^(?:(?:\d{1,3}\.){3}\d{1,3}|[0-9a-f:]*[0-9a-f]+:[0-9a-f:]*[0-9a-f]+)$",
    re.I,
)
_DNS_SHORT_MX_RE = re.compile(r"^\d+\s+\S+\.$", re.I)
_HOSTNAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}\.?$",
    re.I,
)
_NMAP_REPORT_TARGET_RE = re.compile(r"^Nmap scan report for\s+(.+?)(?:\s+\(([^)]+)\))?$", re.I)
_NMAP_ENTITY_NOISE_RE = re.compile(
    r"^(?:Starting Nmap\b.*\bhttps://nmap\.org\b|"
    r"Service detection performed\. Please report any incorrect results at https://nmap\.org/submit/ \.|"
    r".*\bfollowing fingerprints at https://nmap\.org/cgi-bin/submit\.cgi\?new-service\b.*|"
    r"SF:)",
    re.I,
)
_ENTITY_IPV4_RE = re.compile(
    r"(?<![\w.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\w.])"
)
_ENTITY_IPV6_RE = re.compile(r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,}[0-9a-f:.%]{0,45}(?![\w:])", re.I)
_ENTITY_HOSTNAME_RE = re.compile(
    r"(?<![@\w-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}\.?(?![\w-])",
    re.I,
)
_ENTITY_URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.I)
_ENTITY_HASH_RE = re.compile(r"(?<![0-9a-f])(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})(?![0-9a-f])", re.I)
_ENTITY_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I)
_ENTITY_FILELIKE_SUFFIXES = {
    "bak",
    "cfg",
    "conf",
    "css",
    "csv",
    "db",
    "eot",
    "gif",
    "gz",
    "html",
    "ico",
    "ini",
    "jpeg",
    "jpg",
    "js",
    "json",
    "log",
    "map",
    "md",
    "out",
    "php",
    "png",
    "sqlite",
    "svg",
    "ttf",
    "txt",
    "wasm",
    "webp",
    "woff",
    "woff2",
    "xml",
    "yaml",
    "yml",
    "zip",
}


def _is_public_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _is_private_or_reserved_ip(value: str) -> bool:
    try:
        return not ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _entity_confidence(entity_type: str) -> str:
    return "medium" if entity_type == "domain" else "high"


def _add_entity(
    entities: list[dict[str, object]],
    seen: set[tuple[str, str]],
    *,
    entity_type: str,
    value: str,
    canonical_value: str,
    source_line: int | None,
    start: int | None = None,
    end: int | None = None,
) -> None:
    key = (entity_type, canonical_value)
    if key in seen:
        return
    seen.add(key)
    item: dict[str, object] = {
        "type": entity_type,
        "value": value,
        "canonical_value": canonical_value,
        "confidence": _entity_confidence(entity_type),
    }
    if source_line is not None:
        item["source_line"] = source_line
    if start is not None and end is not None and 0 <= start < end:
        item["start"] = start
        item["end"] = end
    entities.append(item)


def _seen_entities(entities: list[dict[str, object]]) -> set[tuple[str, str]]:
    return {
        (str(item.get("type") or ""), str(item.get("canonical_value") or ""))
        for item in entities
        if isinstance(item, dict)
    }


def _looks_like_file_hostname(value: str) -> bool:
    token = str(value or "").strip().rstrip(".").lower()
    suffix = token.rsplit(".", 1)[-1] if "." in token else ""
    return suffix in _ENTITY_FILELIKE_SUFFIXES


def _span_overlaps(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def strip_ansi_codes(value: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", str(value or ""))


def _strip_ansi_codes(value: str) -> str:
    return strip_ansi_codes(value)


def _normalize_signal_text(value: str) -> str:
    # Match against plain text while preserving the original ANSI-rich line for
    # terminal rendering, history, exports, and shares.
    return _strip_ansi_codes(str(value or "")).strip()


def extract_entities(
    text: str,
    *,
    include_private_ips: bool = False,
    source_line: int | None = None,
    normalized_text: str | None = None,
) -> list[dict[str, object]]:
    stripped = normalized_text if normalized_text is not None else _normalize_signal_text(text)
    if not stripped:
        return []

    entities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    url_tail_spans: list[tuple[int, int]] = []

    for match in _ENTITY_IPV4_RE.finditer(stripped):
        raw = match.group(0)
        try:
            canonical = canonical_ip(raw)
        except CanonicalizationError:
            continue
        if not include_private_ips and not _is_public_ip(canonical):
            continue
        _add_entity(
            entities,
            seen,
            entity_type="ip",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    for match in _ENTITY_IPV6_RE.finditer(stripped):
        raw = match.group(0).strip("[]")
        try:
            canonical = canonical_ip(raw)
        except CanonicalizationError:
            continue
        if "." in canonical:
            continue
        if not include_private_ips and not _is_public_ip(canonical):
            continue
        _add_entity(
            entities,
            seen,
            entity_type="ip",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    for match in _ENTITY_URL_RE.finditer(stripped):
        raw_url = match.group(0)
        host = urlparse(raw_url).hostname or ""
        if not host or "\\" in host or _looks_like_file_hostname(host):
            continue
        try:
            canonical = canonical_domain(host)
        except CanonicalizationError:
            continue
        host_offset = raw_url.lower().find(host.lower())
        start = match.start() + host_offset if host_offset >= 0 else match.start()
        end = start + len(host) if host_offset >= 0 else match.end()
        if host_offset >= 0 and end < match.end():
            url_tail_spans.append((end, match.end()))
        _add_entity(
            entities,
            seen,
            entity_type="domain",
            value=host,
            canonical_value=canonical,
            source_line=source_line,
            start=start,
            end=end,
        )

    for match in _ENTITY_HOSTNAME_RE.finditer(stripped):
        if _span_overlaps(url_tail_spans, match.start(), match.end()):
            continue
        raw = match.group(0).rstrip(".")
        if "\\" in raw or _looks_like_file_hostname(raw):
            continue
        try:
            canonical = canonical_domain(raw)
        except CanonicalizationError:
            continue
        _add_entity(
            entities,
            seen,
            entity_type="domain",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    for match in _ENTITY_HASH_RE.finditer(stripped):
        raw = match.group(0)
        try:
            algorithm = detect_hash_algorithm(raw)
            canonical = canonical_hash(raw, algorithm=algorithm)
        except CanonicalizationError:
            continue
        _add_entity(
            entities,
            seen,
            entity_type="hash",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    for match in _ENTITY_CVE_RE.finditer(stripped):
        raw = match.group(0)
        try:
            canonical = canonical_cve(raw)
        except CanonicalizationError:
            continue
        _add_entity(
            entities,
            seen,
            entity_type="cve",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    return entities


def _looks_like_clean_url(value: str) -> bool:
    raw = _normalize_signal_text(value)
    if not _CLEAN_HTTP_URL_RE.match(raw):
        return False
    return not _SHELL_TEMPLATE_URL_NOISE_RE.search(raw)


def _parse_shodan_dns_row(stripped: str) -> tuple[str, str, str] | None:
    parts = str(stripped or "").strip().split(None, 2)
    if len(parts) < 2:
        return None
    first = parts[0].upper()
    if first in _SHODAN_DNS_RECORD_TYPES:
        value = parts[1] if len(parts) == 2 else f"{parts[1]} {parts[2]}"
        return "", first, value
    if len(parts) >= 3 and parts[1].upper() in _SHODAN_DNS_RECORD_TYPES:
        return parts[0], parts[1].upper(), parts[2]
    return None


def _nmap_report_entities(stripped: str, source_line: int | None) -> list[dict[str, object]]:
    match = _NMAP_REPORT_TARGET_RE.match(stripped)
    if not match:
        return []

    entities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    def add_target(raw_value: str, *, start: int, end: int) -> None:
        value = str(raw_value or "").strip().strip("[]")
        if not value:
            return
        try:
            canonical = canonical_ip(value)
        except CanonicalizationError:
            try:
                canonical = canonical_domain(value)
            except CanonicalizationError:
                return
            _add_entity(
                entities,
                seen,
                entity_type="host",
                value=value,
                canonical_value=canonical,
                source_line=source_line,
                start=start,
                end=end,
            )
            return
        _add_entity(
            entities,
            seen,
            entity_type="ip",
            value=value,
            canonical_value=canonical,
            source_line=source_line,
            start=start,
            end=end,
        )

    add_target(match.group(1), start=match.start(1), end=match.end(1))
    if match.group(2):
        add_target(match.group(2), start=match.start(2), end=match.end(2))
    return entities


def _is_shodan_dns_text_row(stripped: str) -> bool:
    parsed = _parse_shodan_dns_row(stripped)
    return bool(parsed and parsed[1] == "TXT")


def _is_shodan_finding(stripped: str) -> bool:
    parsed = _parse_shodan_dns_row(stripped)
    if parsed:
        _, record_type, _ = parsed
        return record_type in _SHODAN_DNS_FINDING_TYPES
    return (
        (bool(_SHODAN_HOST_IP_RE.match(stripped)) and _is_public_ip(stripped))
        or bool(_SHODAN_HOSTNAME_RE.search(stripped))
        or bool(_SHODAN_PORT_RE.search(stripped))
        or bool(_SHODAN_HTTP_TITLE_RE.search(stripped))
    )


def _is_shodan_warning(stripped: str) -> bool:
    parsed = _parse_shodan_dns_row(stripped)
    if parsed:
        _, record_type, value = parsed
        if record_type in {"A", "AAAA"} and _is_private_or_reserved_ip(value.split()[0] if value else ""):
            return True
        if record_type == "TXT" and _SHODAN_WEAK_MAIL_POLICY_RE.search(value):
            return True
    return bool(_SHODAN_HTTP_WARNING_RE.search(stripped))


def _is_shodan_summary(stripped: str) -> bool:
    return bool(_SHODAN_HOST_SUMMARY_RE.search(stripped))


def _is_openssl_noise(stripped: str) -> bool:
    return (
        stripped == "---"
        or bool(_OPENSSL_CONNECTED_RE.match(stripped))
        or bool(_OPENSSL_PEM_BOUNDARY_RE.match(stripped))
        or bool(_OPENSSL_PEM_BODY_RE.match(stripped))
    )


def _parse_ffuf_progress(stripped: str) -> tuple[int, int, int] | None:
    match = _FFUF_PROGRESS_DETAIL_RE.match(stripped)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _is_ffuf_final_progress(stripped: str) -> bool:
    parsed = _parse_ffuf_progress(stripped)
    return bool(parsed and parsed[0] >= parsed[1] and parsed[1] > 0)


def _is_ffuf_progress_warning(stripped: str) -> bool:
    parsed = _parse_ffuf_progress(stripped)
    return bool(parsed and parsed[2] > 0)


def _parse_ffuf_result(stripped: str) -> tuple[str, int] | None:
    match = _FFUF_RESULT_RE.match(stripped)
    if not match:
        return None
    return match.group(1).strip(), int(match.group(2))


def _is_ffuf_warning(stripped: str) -> bool:
    if _is_ffuf_progress_warning(stripped):
        return True
    parsed = _parse_ffuf_result(stripped)
    return bool(parsed and 500 <= parsed[1] <= 599)


def _is_ffuf_noise(stripped: str) -> bool:
    return (
        bool(_FFUF_SEPARATOR_RE.match(stripped))
        or bool(_FFUF_VERSION_RE.match(stripped))
        or bool(_FFUF_ASCII_BANNER_RE.match(stripped))
    )


def _ffuf_result_url(command_target: str, result_path: str) -> str | None:
    raw_path = str(result_path or "").strip()
    if not raw_path:
        return None
    if _URL_SCHEME_RE.match(raw_path):
        return raw_path
    base = str(command_target or "").strip()
    if not _URL_SCHEME_RE.match(base):
        return None
    if "FUZZ" in base:
        return base.replace("FUZZ", raw_path.lstrip("/"), 1)
    if raw_path.startswith("/"):
        parsed = urlparse(base)
        return f"{parsed.scheme}://{parsed.netloc}{raw_path}"
    return f"{base.rstrip('/')}/{raw_path.lstrip('/')}"


def _dig_status(stripped: str) -> str:
    match = _DIG_HEADER_RE.match(stripped)
    return match.group(1).strip().upper().rstrip(",") if match else ""


def _is_dns_warning(root: str, stripped: str) -> bool:
    if root == "nslookup":
        return bool(_NSLOOKUP_WARNING_RE.search(stripped))
    if root != "dig":
        return False
    status = _dig_status(stripped)
    return status in _DIG_WARNING_STATUSES or bool(_DIG_ZERO_ANSWER_RE.search(stripped))


def _is_dns_summary(root: str, stripped: str) -> bool:
    if root == "nslookup":
        return bool(_NSLOOKUP_SUMMARY_RE.search(stripped))
    if root != "dig":
        return False
    return bool(_dig_status(stripped)) or bool(_DIG_SUMMARY_RE.search(stripped))


def _is_nslookup_address_finding(stripped: str) -> bool:
    match = _NSLOOKUP_ADDRESS_RE.match(stripped)
    return bool(match and _is_public_ip(match.group(1)))


def _is_command_scoped_finding(root: str, stripped: str) -> bool:
    if root in {"dnsx", "subfinder"}:
        return bool(_HOSTNAME_RE.search(stripped))
    if root == "nslookup":
        return _is_nslookup_address_finding(stripped)
    if root == "ffuf":
        return bool(_parse_ffuf_result(stripped))
    if root == "fierce":
        return bool(_FIERCE_FINDING_RE.match(stripped))
    if root == "dnsenum":
        return bool(_CIDR_RE.search(stripped))
    if root == "dnsrecon":
        return bool(_DNSRECON_FINDING_RE.match(stripped))
    if root == "nmap":
        return bool(_NMAP_RDNS_RE.search(stripped))
    if root == "whois":
        return bool(_WHOIS_FINDING_RE.search(stripped))
    if root == "wget":
        return bool(_WGET_FINDING_RE.search(stripped))
    if root == "shodan":
        return _is_shodan_finding(stripped)
    if root == "ipinfo":
        return bool(_IPINFO_FINDING_RE.search(stripped))
    if root == "openssl":
        return bool(_OPENSSL_FINDING_RE.search(stripped))
    if root == "httpx":
        return bool(_HTTPX_RESULT_RE.search(stripped))
    if root == "gobuster":
        return bool(_GOBUSTER_RESULT_RE.search(stripped))
    if root in _CRAWL_URL_ROOTS:
        return _looks_like_clean_url(stripped)
    if root == "wafw00f":
        return bool(_WAFW00F_RESULT_RE.search(stripped))
    if root == "nikto":
        return not _NIKTO_SKIP_RE.search(stripped) and (
            bool(_NIKTO_FINDING_RE.search(stripped)) or bool(_NIKTO_PLUS_LINE_RE.match(stripped))
        )
    if root == "wpscan":
        return not _WPSCAN_SKIP_RE.search(stripped) and bool(_WPSCAN_FINDING_RE.search(stripped))
    if root == "testssl":
        return bool(_TESTSSL_FINDING_RE.search(stripped))
    if root == "sslscan":
        return bool(_SSLSCAN_FINDING_RE.search(stripped))
    if root == "sslyze":
        return bool(_SSLYZE_FINDING_RE.search(stripped))
    if root == "naabu":
        return bool(_HOST_PORT_RE.search(stripped))
    if root == "rustscan":
        return bool(_RUSTSCAN_OPEN_RE.search(stripped))
    if root == "nuclei":
        return bool(_NUCLEI_RESULT_RE.search(stripped))
    return False


def _is_command_scoped_warning(root: str, stripped: str) -> bool:
    if _is_dns_warning(root, stripped):
        return True
    if root == "ffuf":
        return _is_ffuf_warning(stripped)
    if root == "whois":
        return bool(_WHOIS_WARNING_RE.search(stripped))
    if root == "shodan":
        return _is_shodan_warning(stripped)
    if root == "openssl":
        return bool(_OPENSSL_WARNING_RE.search(stripped))
    if root == "wpscan":
        return bool(_WPSCAN_API_TOKEN_WARNING_RE.search(stripped))
    return False


def _is_command_scoped_summary(root: str, stripped: str) -> bool:
    if _is_dns_summary(root, stripped):
        return True
    if root == "ffuf":
        return bool(_FFUF_CONFIG_RE.search(stripped)) or _is_ffuf_final_progress(stripped)
    if root == "whois":
        return bool(_WHOIS_SUMMARY_RE.search(stripped))
    if root == "wget":
        return bool(_WGET_SUMMARY_RE.search(stripped))
    if root == "shodan":
        return _is_shodan_summary(stripped)
    if root == "ipinfo":
        return bool(_IPINFO_SUMMARY_RE.search(stripped))
    if root == "openssl":
        return bool(_OPENSSL_SUMMARY_RE.search(stripped))
    if root == "wafw00f":
        return bool(_WAFW00F_REQUESTS_RE.search(stripped))
    if root == "naabu":
        return bool(_NAABU_FOUND_PORTS_RE.search(stripped))
    if root == "nuclei":
        return bool(_SCAN_COMPLETED_RE.search(stripped))
    if root == "nmap":
        return bool(_NMAP_HOST_UP_RE.search(stripped))
    return False


def _is_command_scoped_signal_noise(root: str, stripped: str) -> bool:
    if root == "ffuf":
        if _is_ffuf_noise(stripped):
            return True
        if _FFUF_PROGRESS_RE.search(stripped):
            return not (_is_ffuf_final_progress(stripped) or _is_ffuf_progress_warning(stripped))
    if root == "gobuster" and _GOBUSTER_CONFIG_RE.search(stripped):
        return True
    if root == "openssl" and _is_openssl_noise(stripped):
        return True
    if _is_progress_role_line(root, stripped):
        return True
    return False


def _is_progress_role_line(root: str, stripped: str) -> bool:
    if root == "masscan" and _MASSCAN_RATE_RE.search(stripped):
        return True
    if root == "ffuf" and _FFUF_PROGRESS_RE.search(stripped):
        return True
    return False


def _extract_entities_for_command(
    root: str,
    text: str,
    *,
    source_line: int | None = None,
    normalized_text: str | None = None,
    ansi_stripped_text: str | None = None,
    command_target: str | None = None,
    command_url_template: str | None = None,
) -> list[dict[str, object]]:
    stripped = normalized_text if normalized_text is not None else _normalize_signal_text(text)
    plain = ansi_stripped_text if ansi_stripped_text is not None else _strip_ansi_codes(str(text or "")).rstrip("\n\r")
    if root in _PROJECTDISCOVERY_ROOTS and _PROJECTDISCOVERY_ENTITY_NOISE_RE.search(plain):
        return []
    if root == "testssl" and _TESTSSL_ENTITY_NOISE_RE.search(stripped):
        return []
    if root == "masscan" and _MASSCAN_STARTUP_RE.search(stripped):
        return []
    if root == "nmap" and _NMAP_ENTITY_NOISE_RE.search(stripped):
        return []
    if root == "nmap":
        nmap_report_entities = _nmap_report_entities(stripped, source_line)
        if nmap_report_entities:
            return nmap_report_entities
    if root == "openssl" and _is_openssl_noise(stripped):
        return []
    if root == "ffuf" and (_is_ffuf_noise(stripped) or bool(_FFUF_CONFIG_RE.search(stripped))):
        return []
    entities = extract_entities(text, source_line=source_line, normalized_text=stripped)
    if root == "ffuf" and (command_url_template or command_target):
        parsed_result = _parse_ffuf_result(stripped)
        if not parsed_result:
            return entities
        result_path, _ = parsed_result
        result_url = _ffuf_result_url(command_url_template or str(command_target or ""), result_path)
        if not result_url:
            return entities
        try:
            canonical = canonical_url(result_url)
        except CanonicalizationError:
            return entities
        seen = _seen_entities(entities)
        start = plain.find(result_path)
        _add_entity(
            entities,
            seen,
            entity_type="url",
            value=result_url,
            canonical_value=canonical,
            source_line=source_line,
            start=start if start >= 0 else None,
            end=(start + len(result_path)) if start >= 0 else None,
        )
        return entities
    if root != "shodan" or not command_target:
        return entities

    parsed = _parse_shodan_dns_row(stripped)
    if not parsed:
        return entities
    label, record_type, _ = parsed
    if not label or record_type not in _SHODAN_DNS_FINDING_TYPES or not _SHODAN_LABEL_RE.match(label):
        return entities

    fqdn = f"{label}.{str(command_target).strip().rstrip('.')}"
    try:
        canonical = canonical_domain(fqdn)
    except CanonicalizationError:
        return entities
    seen = _seen_entities(entities)
    _add_entity(
        entities,
        seen,
        entity_type="domain",
        value=fqdn,
        canonical_value=canonical,
        source_line=source_line,
        start=plain.find(label) if label in plain else None,
        end=(plain.find(label) + len(label)) if label in plain else None,
    )
    return entities


def tokenize_command(command: str) -> list[str]:
    tokens: list[str] = []
    source = str(command or "").strip()
    current = ""
    quote = ""
    i = 0
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == quote:
                quote = ""
            elif ch == "\\" and i + 1 < len(source):
                i += 1
                current += source[i]
            else:
                current += ch
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            i += 1
            continue
        if ch.isspace():
            if current:
                tokens.append(current)
                current = ""
            i += 1
            continue
        current += ch
        i += 1
    if current:
        tokens.append(current)
    return tokens


@lru_cache(maxsize=512)
def _is_help_output_command(command: str, root: str | None = None) -> bool:
    if not str(command or "").strip():
        return False
    try:
        from services.commands.registry import is_help_invocation
    except Exception:
        return False
    return is_help_invocation(command, root=root)


def command_root(command: str) -> str:
    tokens = tokenize_command(command)
    return str(tokens[0] if tokens else "").lower()


def _strip_url_target(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if _URL_SCHEME_RE.match(raw):
        parsed = urlparse(raw)
        return parsed.netloc or raw
    return _URL_TAIL_RE.sub("", _URL_SCHEME_RE.sub("", raw))


def _find_flag_value(tokens: list[str], names: set[str]) -> str:
    for index, token in enumerate(tokens[1:], start=1):
        if token in names and index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
            return tokens[index + 1]
        match = _FLAG_ASSIGNMENT_RE.match(token)
        if match and match.group(1) in names:
            return match.group(2)
    return ""


def _positional_targets(
    tokens: list[str],
    *,
    skip_values_after: set[str] | None = None,
    skip_values_for_prefix: re.Pattern[str] | None = None,
) -> list[str]:
    skip_values_after = skip_values_after or set()
    skip_values_for_prefix = skip_values_for_prefix or re.compile(r"^$")
    result: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if not token:
            index += 1
            continue
        if token.startswith("-"):
            if token in skip_values_after or skip_values_for_prefix.search(token):
                next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
                if next_token and not next_token.startswith("-"):
                    index += 1
            index += 1
            continue
        result.append(token)
        index += 1
    return result


def _dns_target(tokens: list[str], root: str) -> str:
    record_types = {"a", "aaaa", "cname", "mx", "ns", "txt", "soa", "ptr", "srv", "caa", "any"}
    positionals = [
        token for token in tokens[1:]
        if token and not token.startswith("-") and not token.startswith("+")
        and not token.startswith("@") and token.lower() not in record_types
    ]
    if root == "nslookup" and _NSLOOKUP_SERVER_RE.match(positionals[0] if positionals else ""):
        return positionals[1] if len(positionals) > 1 else ""
    return positionals[0] if positionals else ""


def extract_target(command: str) -> str | None:
    tokens = tokenize_command(command)
    root = str(tokens[0] if tokens else "").lower()
    if not root:
        return None

    if root in {"dig", "host", "nslookup"}:
        target = _dns_target(tokens, root)
        return _strip_url_target(target) if target else None

    if root == "dnsrecon":
        target = _find_flag_value(tokens, {"-d", "--domain"})
        return _strip_url_target(target) if target else None

    if root in {"curl", "httpx", "wafw00f"}:
        positionals = _positional_targets(
            tokens,
            skip_values_after={
                "-H", "--header", "-A", "--user-agent", "-o", "--output",
                "-w", "--write-out", "--connect-timeout", "-m", "--max-time",
            },
        )
        target = next((token for token in positionals if _URL_SCHEME_RE.match(token)), "")
        if not target:
            target = next((token for token in positionals if "." in token), "")
        return _strip_url_target(target) if target else None

    if root == "nikto":
        target = _find_flag_value(tokens, {"-h", "-u", "--url", "-target", "--target"})
        return _strip_url_target(_FUZZ_SUFFIX_RE.sub("", target)) if target else None

    if root in {"ffuf", "gobuster", "feroxbuster", "katana", "nuclei"}:
        target = _find_flag_value(tokens, {"-u", "--url", "-target", "--target"})
        return _strip_url_target(_FUZZ_SUFFIX_RE.sub("", target)) if target else None

    if root == "assetfinder":
        positionals = _positional_targets(tokens)
        target = next((token for token in positionals if "." in token), "")
        return _strip_url_target(target) if target else None

    if root == "shodan" and len(tokens) >= 3 and tokens[1].lower() in {"domain", "host"}:
        positionals = _positional_targets(tokens[1:], skip_values_after={"--fields", "--limit"})
        target = positionals[0] if positionals else ""
        return _strip_url_target(target) if target else None

    if root == "ipinfo":
        positionals = _positional_targets(tokens, skip_values_after={"--format", "--token"})
        target = positionals[0] if positionals else ""
        return _strip_url_target(target) if target else None

    if root in {"nmap", "rustscan", "naabu", "sslscan", "sslyze", "testssl"}:
        positionals = [
            token for token in _positional_targets(
                tokens,
                skip_values_after={
                    "-p", "--ports", "--top-ports", "-oA", "-oG", "-oN", "-oX",
                    "-iL", "-script", "--script", "--script-args", "--rate", "--timeout",
                    "--host-timeout",
                },
                skip_values_for_prefix=_NMAP_OUTPUT_PREFIX_RE,
            )
            if not _PORT_LIST_RE.match(token)
        ]
        return ", ".join(positionals) if positionals else None

    if root == "nc":
        positionals = [
            token for token in _positional_targets(tokens, skip_values_after={"-w", "-i", "-s", "-p"})
            if not _PORT_RANGE_RE.match(token)
        ]
        return _strip_url_target(positionals[0]) if positionals else None

    if root == "openssl":
        target = _find_flag_value(tokens, {"-connect"})
        return _strip_url_target(target) if target else None

    return None


@dataclass
class OutputSignalClassifier:
    command: str
    cmd_type: str = "real"

    def __post_init__(self) -> None:
        self.root = command_root(self.command)
        self.target = extract_target(self.command)
        self.url_template = ""
        if self.root == "ffuf":
            self.url_template = _find_flag_value(tokenize_command(self.command), {"-u", "--url"})
        self.is_help_output = _is_help_output_command(self.command, self.root)
        self.current_target: str | None = None
        self.line_index = 0
        self.previous_text = ""

    def _line_target(self, normalized_text: str) -> str | None:
        if self.root == "nmap":
            report_match = _NMAP_REPORT_TARGET_RE.match(normalized_text)
            if report_match:
                self.current_target = report_match.group(1).strip()
            elif _NMAP_DONE_RE.match(normalized_text):
                return self.target
            if self.current_target:
                return self.current_target
        return self.target

    def classify_line(self, text: str, cls: str = "") -> dict[str, object]:
        text = str(text or "").rstrip("\n")
        cls = str(cls or "")
        ansi_stripped = _strip_ansi_codes(text).rstrip("\n\r")
        normalized_text = ansi_stripped.strip()
        target = self._line_target(normalized_text)
        scopes = classify_line(
            text,
            cls=cls,
            command=self.command,
            root=self.root,
            previous_text=self.previous_text,
            include_signals=self.cmd_type not in {"builtin"} and not self.is_help_output,
            is_help_output=self.is_help_output,
            normalized_text=normalized_text,
        )
        metadata: dict[str, object] = {
            "line_index": self.line_index,
            "command_root": self.root,
        }
        if target:
            metadata["target"] = target
        if scopes:
            metadata["signals"] = scopes
        role = classify_line_role(
            text,
            root=self.root,
            command=self.command,
            normalized_text=normalized_text,
        )
        if role is not None:
            metadata["role"] = role.value
        can_extract_entities = (
            role not in {LineRole.progress, LineRole.status_line}
            and self.cmd_type not in {"builtin"}
            and not self.is_help_output
        )
        if can_extract_entities:
            entities = _extract_entities_for_command(
                self.root,
                text,
                source_line=self.line_index,
                normalized_text=normalized_text,
                ansi_stripped_text=ansi_stripped,
                command_target=self.target,
                command_url_template=self.url_template,
            )
            if entities:
                metadata["entities"] = entities
        self.line_index += 1
        self.previous_text = normalized_text
        return metadata


def classify_line(
    text: str,
    *,
    cls: str = "",
    command: str = "",
    root: str | None = None,
    previous_text: str = "",
    include_signals: bool = True,
    is_help_output: bool | None = None,
    normalized_text: str | None = None,
) -> list[str]:
    if not include_signals:
        return []
    stripped = normalized_text if normalized_text is not None else _normalize_signal_text(text)
    if not stripped:
        return []
    if any(pattern.search(stripped) for pattern in _APP_SIGNAL_EXCLUDES):
        return []
    scopes: list[str] = []
    root = root if root is not None else command_root(command)
    help_output = is_help_output if is_help_output is not None else _is_help_output_command(command, root)
    if help_output:
        return scopes
    if _is_command_scoped_signal_noise(root, stripped):
        return scopes

    if cls == "notice":
        scopes.append("warnings")
    if cls in {"denied", "exit-fail"} and not _KILLED_BY_USER_RE.match(stripped):
        scopes.append("errors")

    if _KILLED_BY_USER_RE.match(stripped):
        return scopes

    if not any(pattern.search(stripped) for pattern in _FINDINGS_EXCLUDES):
        finding = False
        if root == "shodan" and _is_shodan_dns_text_row(stripped):
            finding = False
        elif _DNS_MAIL_EXCHANGER_RE.search(stripped):
            finding = True
        elif _DNS_TEXT_RE.search(stripped):
            finding = True
        elif _DNS_CANONICAL_NAME_RE.search(stripped):
            finding = True
        elif _DNS_ADDRESS_RE.search(stripped):
            finding = bool(_DNS_NAME_RE.search(previous_text)) or (
                root == "nslookup" and _is_nslookup_address_finding(stripped)
            )
        elif root in _DNS_SIGNAL_ROOTS and (_DNS_BARE_IP_RE.search(stripped) or _DNS_SHORT_MX_RE.search(stripped)):
            finding = True
        elif root == "assetfinder" and (_HOSTNAME_RE.search(stripped) or _is_public_ip(stripped)):
            finding = True
        elif _is_command_scoped_finding(root, stripped):
            finding = True
        elif any(pattern.search(stripped) for pattern in _SIGNAL_PATTERNS["findings"]):
            finding = True
        if finding:
            scopes.append("findings")

    suppress_generic_summary = (
        root == "ffuf"
        and bool(_FFUF_PROGRESS_RE.search(stripped))
        and not _is_ffuf_final_progress(stripped)
    )
    for scope in ("warnings", "errors", "summaries"):
        command_scoped_match = (
            (scope == "warnings" and _is_command_scoped_warning(root, stripped))
            or (scope == "summaries" and _is_command_scoped_summary(root, stripped))
        )
        generic_match = not (scope == "summaries" and suppress_generic_summary) and any(
            pattern.search(stripped) for pattern in _SIGNAL_PATTERNS[scope]
        )
        if command_scoped_match or generic_match:
            scopes.append(scope)

    return list(dict.fromkeys(scopes))


def classify_line_role(
    text: str,
    *,
    root: str | None = None,
    command: str = "",
    normalized_text: str | None = None,
) -> LineRole | None:
    stripped = normalized_text if normalized_text is not None else _normalize_signal_text(text)
    if not stripped:
        return None
    root = root if root is not None else command_root(command)
    if _is_progress_role_line(root, stripped):
        return LineRole.progress
    return None
