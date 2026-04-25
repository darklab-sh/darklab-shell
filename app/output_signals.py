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

_DNS_SIGNAL_ROOTS = {"dig", "host", "nslookup"}
_DNS_BARE_IP_RE = re.compile(
    r"^(?:(?:\d{1,3}\.){3}\d{1,3}|[0-9a-f:]*[0-9a-f]+:[0-9a-f:]*[0-9a-f]+)$",
    re.I,
)
_DNS_SHORT_MX_RE = re.compile(r"^\d+\s+\S+\.$", re.I)
_HOSTNAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}\.?$",
    re.I,
)


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
        self.line_index = 0
        self.previous_text = ""

    def classify_line(self, text: str, cls: str = "") -> dict[str, object]:
        text = str(text or "").rstrip("\n")
        cls = str(cls or "")
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
        if self.target:
            metadata["target"] = self.target
        if scopes:
            metadata["signals"] = scopes
        self.line_index += 1
        self.previous_text = text.strip()
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
    stripped = str(text or "").strip()
    if not stripped:
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
        elif any(pattern.search(stripped) for pattern in _SIGNAL_PATTERNS["findings"]):
            finding = True
        if finding:
            scopes.append("findings")

    for scope in ("warnings", "errors", "summaries"):
        if any(pattern.search(stripped) for pattern in _SIGNAL_PATTERNS[scope]):
            scopes.append(scope)

    return list(dict.fromkeys(scopes))
