"""Server-side output signal classification.

The browser renders and navigates signals, but the backend owns the command
output semantics so live streams, history restores, shares, and future exports
can agree on what counts as a finding, warning, error, or summary line.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse


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
_PD_HTTPX_RESULT_RE = re.compile(r"^https?://\S+\s+\[\d{3}\](?:\s+\[[^\]]*\])*", re.I)
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


def _strip_ansi_codes(value: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", str(value or ""))


def _normalize_signal_text(value: str) -> str:
    # Match against plain text while preserving the original ANSI-rich line for
    # terminal rendering, history, exports, and shares.
    return _strip_ansi_codes(str(value or "")).strip()


def _looks_like_clean_url(value: str) -> bool:
    raw = _normalize_signal_text(value)
    if not re.match(r"^https?://\S+$", raw, re.I):
        return False
    return not re.search(r"(?:'\+|\+'\$|/\$1\b)", raw)


def _is_command_scoped_finding(root: str, stripped: str) -> bool:
    if root in {"dnsx", "subfinder"}:
        return bool(_HOSTNAME_RE.search(stripped))
    if root == "fierce":
        return bool(re.match(r"^(?:Found:|NS:|SOA:)\s+\S+", stripped, re.I))
    if root == "dnsenum":
        return bool(_CIDR_RE.search(stripped))
    if root == "dnsrecon":
        return bool(re.match(r"^\[\*\]\s+DNSSEC is configured for\s+\S+", stripped, re.I))
    if root in {"pd-httpx", "httpx"}:
        return bool(_PD_HTTPX_RESULT_RE.search(stripped))
    if root in _CRAWL_URL_ROOTS:
        return _looks_like_clean_url(stripped)
    if root == "wafw00f":
        return bool(_WAFW00F_RESULT_RE.search(stripped))
    if root == "nikto":
        return not _NIKTO_SKIP_RE.search(stripped) and (
            bool(_NIKTO_FINDING_RE.search(stripped)) or bool(re.match(r"^\+\s+\S", stripped))
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
    if root == "wpscan":
        return bool(_WPSCAN_API_TOKEN_WARNING_RE.search(stripped))
    return False


def _is_command_scoped_summary(root: str, stripped: str) -> bool:
    if root == "wafw00f":
        return bool(_WAFW00F_REQUESTS_RE.search(stripped))
    if root == "naabu":
        return bool(_NAABU_FOUND_PORTS_RE.search(stripped))
    if root == "nuclei":
        return bool(_SCAN_COMPLETED_RE.search(stripped))
    return False


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


def command_root(command: str) -> str:
    tokens = tokenize_command(command)
    return str(tokens[0] if tokens else "").lower()


def _strip_url_target(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        parsed = urlparse(raw)
        return parsed.netloc or raw
    return re.sub(r"[/?#].*$", "", re.sub(r"^[a-z][a-z0-9+.-]*://", "", raw, flags=re.I))


def _find_flag_value(tokens: list[str], names: set[str]) -> str:
    for index, token in enumerate(tokens[1:], start=1):
        if token in names and index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
            return tokens[index + 1]
        match = re.match(r"^([^=]+)=(.+)$", token)
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
    if root == "nslookup" and re.match(r"^server$", positionals[0] if positionals else "", re.I):
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

    if root in {"curl", "httpx", "pd-httpx", "wafw00f"}:
        positionals = _positional_targets(
            tokens,
            skip_values_after={
                "-H", "--header", "-A", "--user-agent", "-o", "--output",
                "-w", "--write-out", "--connect-timeout", "-m", "--max-time",
            },
        )
        target = next((token for token in positionals if re.match(r"^[a-z][a-z0-9+.-]*://", token, re.I)), "")
        if not target:
            target = next((token for token in positionals if "." in token), "")
        return _strip_url_target(target) if target else None

    if root in {"ffuf", "gobuster", "feroxbuster", "katana", "nikto", "nuclei"}:
        target = _find_flag_value(tokens, {"-u", "--url", "-target", "--target"})
        return _strip_url_target(re.sub(r"/FUZZ\b.*$", "", target, flags=re.I)) if target else None

    if root == "assetfinder":
        positionals = _positional_targets(tokens)
        target = next((token for token in positionals if "." in token), "")
        return _strip_url_target(target) if target else None

    if root in {"nmap", "rustscan", "naabu", "sslscan", "sslyze", "testssl"}:
        positionals = [
            token for token in _positional_targets(
                tokens,
                skip_values_after={
                    "-p", "--ports", "--top-ports", "-oA", "-oG", "-oN", "-oX",
                    "-iL", "--script", "--script-args", "--rate", "--timeout",
                    "--host-timeout",
                },
                skip_values_for_prefix=re.compile(r"^-o[AGNX]$", re.I),
            )
            if not re.match(r"^\d+(?:,\d+)*$", token)
        ]
        return ", ".join(positionals) if positionals else None

    if root == "nc":
        positionals = [
            token for token in _positional_targets(tokens, skip_values_after={"-w", "-i", "-s", "-p"})
            if not re.match(r"^\d+(?:-\d+)?$", token)
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
        self.current_target: str | None = None
        self.line_index = 0
        self.previous_text = ""

    def _line_target(self, text: str) -> str | None:
        stripped = _normalize_signal_text(text)
        if self.root == "nmap":
            report_match = _NMAP_REPORT_TARGET_RE.match(stripped)
            if report_match:
                self.current_target = report_match.group(1).strip()
            elif re.match(r"^Nmap done:\b", stripped, re.I):
                return self.target
            if self.current_target:
                return self.current_target
        return self.target

    def classify_line(self, text: str, cls: str = "") -> dict[str, object]:
        text = str(text or "").rstrip("\n")
        cls = str(cls or "")
        target = self._line_target(text)
        scopes = classify_line(
            text,
            cls=cls,
            command=self.command,
            root=self.root,
            previous_text=self.previous_text,
            include_signals=self.cmd_type not in {"builtin"},
        )
        metadata: dict[str, object] = {
            "line_index": self.line_index,
            "command_root": self.root,
        }
        if target:
            metadata["target"] = target
        if scopes:
            metadata["signals"] = scopes
        self.line_index += 1
        self.previous_text = _normalize_signal_text(text)
        return metadata


def classify_line(
    text: str,
    *,
    cls: str = "",
    command: str = "",
    root: str | None = None,
    previous_text: str = "",
    include_signals: bool = True,
) -> list[str]:
    if not include_signals:
        return []
    stripped = _normalize_signal_text(text)
    if not stripped:
        return []
    if any(pattern.search(stripped) for pattern in _APP_SIGNAL_EXCLUDES):
        return []
    scopes: list[str] = []
    root = root if root is not None else command_root(command)

    if cls == "notice":
        scopes.append("warnings")
    if cls in {"denied", "exit-fail"} and not re.match(r"^\[killed by user(?:\b|[^\w])", stripped, re.I):
        scopes.append("errors")

    if re.match(r"^\[killed by user(?:\b|[^\w])", stripped, re.I):
        return scopes

    if not any(pattern.search(stripped) for pattern in _FINDINGS_EXCLUDES):
        finding = False
        if re.search(r"\bmail exchanger\s*=\s*\S+", stripped, re.I):
            finding = True
        elif re.search(r"\btext\s*=\s*.+", stripped, re.I):
            finding = True
        elif re.search(r"\bcanonical name\s*=\s*\S+", stripped, re.I):
            finding = True
        elif re.search(r"^Address(?:es)?:\s+[0-9a-f:.]+\b", stripped, re.I):
            finding = bool(re.search(r"^Name:\s+\S+", previous_text, re.I))
        elif root in _DNS_SIGNAL_ROOTS and (_DNS_BARE_IP_RE.search(stripped) or _DNS_SHORT_MX_RE.search(stripped)):
            finding = True
        elif root == "assetfinder" and _HOSTNAME_RE.search(stripped):
            finding = True
        elif _is_command_scoped_finding(root, stripped):
            finding = True
        elif any(pattern.search(stripped) for pattern in _SIGNAL_PATTERNS["findings"]):
            finding = True
        if finding:
            scopes.append("findings")

    for scope in ("warnings", "errors", "summaries"):
        command_scoped_match = (
            (scope == "warnings" and _is_command_scoped_warning(root, stripped))
            or (scope == "summaries" and _is_command_scoped_summary(root, stripped))
        )
        if command_scoped_match or any(pattern.search(stripped) for pattern in _SIGNAL_PATTERNS[scope]):
            scopes.append(scope)

    return list(dict.fromkeys(scopes))
