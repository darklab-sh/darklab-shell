"""
Command loading, validation, and rewriting.

This module has no dependency on Flask or other app modules — it contains
pure functions that can be imported and tested in isolation.
"""

import os
import re
import yaml

_HERE = os.path.dirname(__file__)
ALLOWED_COMMANDS_FILE = os.path.join(_HERE, "allowed_commands.txt")
AUTOCOMPLETE_FILE     = os.path.join(_HERE, "auto_complete.txt")
FAQ_FILE              = os.path.join(_HERE, "faq.yaml")

# Shell metacharacters that can chain or redirect commands.
# Used for detection (SHELL_CHAIN_RE.search) and splitting (split_chained_commands).
# Both use >>? so > and >> are matched without allowing whitespace between them.
SHELL_CHAIN_RE = re.compile(r'&&|\|\|?|;;?|`|\$\(|>>?|<')

# Pre-compiled path blocking patterns — negative lookbehind prevents false
# positives on URLs such as https://example.com/data/ or /tmp/ path segments.
_PATH_DATA_RE = re.compile(r'(?<![\w:/])/data\b')
_PATH_TMP_RE  = re.compile(r'(?<![\w:/])/tmp\b')


def load_allowed_commands():
    """Read allowed_commands.txt and return (allow_prefixes, deny_prefixes).
    allow_prefixes is None if the file doesn't exist or has no allow entries (= unrestricted).
    deny_prefixes is always a list. Lines starting with ! are deny prefixes and take
    priority over allow prefixes — use them to block specific flags on an allowed command."""
    if not os.path.exists(ALLOWED_COMMANDS_FILE):
        return None, []
    prefixes = []
    denied = []
    with open(ALLOWED_COMMANDS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                denied.append(line[1:].strip().lower())
            else:
                prefixes.append(line.lower())
    return (prefixes if prefixes else None), denied


def load_allowed_commands_grouped():
    """Read allowed_commands.txt and return commands grouped by ## Category headers.
    Returns a list of {name, commands} dicts, or None if file is empty/missing.
    Lines starting with ! (deny prefixes) are excluded from the display list."""
    if not os.path.exists(ALLOWED_COMMANDS_FILE):
        return None
    groups = []
    current = None
    with open(ALLOWED_COMMANDS_FILE) as f:
        for line in f:
            line = line.strip()
            if line.startswith("## "):
                current = {"name": line[3:].strip(), "commands": []}
                groups.append(current)
            elif line and not line.startswith("#") and not line.startswith("!"):
                if current is None:
                    current = {"name": "", "commands": []}
                    groups.append(current)
                current["commands"].append(line.lower())
    groups = [g for g in groups if g["commands"]]
    return groups if groups else None


def load_faq():
    """Read faq.yaml and return a list of {question, answer} dicts.
    Returns an empty list if the file doesn't exist or contains no valid entries."""
    if not os.path.exists(FAQ_FILE):
        return []
    with open(FAQ_FILE) as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        return []
    return [
        {"question": str(item["question"]), "answer": str(item["answer"])}
        for item in data
        if isinstance(item, dict) and item.get("question") and item.get("answer")
    ]


def load_autocomplete():
    """Read auto_complete.txt and return a list of suggestion strings."""
    if not os.path.exists(AUTOCOMPLETE_FILE):
        return []
    suggestions = []
    with open(AUTOCOMPLETE_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                suggestions.append(line)
    return suggestions


def split_chained_commands(command: str) -> list[str]:
    """Split a command string on any shell chaining/piping/redirection operator
    and return the individual command tokens so each can be validated."""
    parts = re.split(r'&&|\|\|?|;;?|`|\$\(|>>?|<', command)
    return [p.strip() for p in parts if p.strip()]


def _is_denied(cmd_lower: str, deny_entries: list[str]) -> bool:
    """Return True if cmd_lower matches any deny entry.
    A deny entry like 'curl -o' is matched if:
      - the command starts with the deny prefix, OR
      - the tool prefix matches AND the flag appears anywhere as a space-separated
        token in the command, so 'curl -s -o file' is caught as well as 'curl -o file'.
    Exception: a denied output flag is allowed when its argument is /dev/null,
    permitting common patterns like 'curl -o /dev/null -w "%{http_code}" <url>'.
    """
    for d in deny_entries:
        if cmd_lower == d or cmd_lower.startswith(d + " "):
            # Exception: flag argument is /dev/null (discard output, not writing to filesystem)
            if cmd_lower.startswith(d + " /dev/null"):
                continue
            return True
        # Split deny entry at first flag (" -") to allow flag-anywhere matching.
        # e.g. "curl -o" → tool="curl", flag="-o"
        #      "gobuster dir -o" → tool="gobuster dir", flag="-o"
        space_flag = d.find(" -")
        if space_flag == -1:
            continue
        tool_prefix = d[:space_flag]
        flag = d[space_flag + 1:]
        if cmd_lower == tool_prefix or cmd_lower.startswith(tool_prefix + " "):
            if re.search(r'(?<= )' + re.escape(flag) + r'(?= |$)', cmd_lower):
                # Exception: flag argument is /dev/null
                if re.search(r'(?<= )' + re.escape(flag) + r' /dev/null\b', cmd_lower):
                    continue
                return True
    return False


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Return (allowed, reason). Blocks if any chained segment isn't on the allowlist,
    or if the raw input contains shell operators or references to protected paths.
    Deny prefixes (lines starting with ! in allowed_commands.txt) take priority over
    allow prefixes, letting operators block specific flags on an otherwise-allowed command."""
    allowed, denied = load_allowed_commands()
    if allowed is None:
        return True, ""  # no file or empty file = unrestricted

    # Block shell chaining/redirection operators outright when restrictions are active
    if SHELL_CHAIN_RE.search(command):
        return False, "Shell operators (&&, |, ;, >, etc.) are not permitted."

    if _PATH_DATA_RE.search(command):
        return False, "Access to /data is not permitted."
    if _PATH_TMP_RE.search(command):
        return False, "Access to /tmp is not permitted."

    cmd_lower = command.strip().lower()

    # Deny prefixes take priority — checked before allow list
    if denied and _is_denied(cmd_lower, denied):
        return False, f"Command not allowed: '{command.strip()}'"

    if not any(cmd_lower == prefix or cmd_lower.startswith(prefix + " ")
               for prefix in allowed):
        return False, f"Command not allowed: '{command.strip()}'"

    return True, ""


def rewrite_command(command: str) -> tuple[str, str | None]:
    """Rewrite commands that need a TTY or specific flags into a safe non-interactive equivalent.
    Returns (rewritten_command, notice_message_or_None)."""
    stripped = command.strip()

    # mtr: force --report-wide mode if not already using a report flag
    if re.match(r'^mtr\b', stripped, re.IGNORECASE):
        if not re.search(r'--report\b|--report-wide\b|-r\b', stripped):
            rewritten = re.sub(r'^mtr\b', 'mtr --report-wide', stripped, flags=re.IGNORECASE)
            return rewritten, "Note: mtr has been run in --report-wide mode (non-interactive). See FAQ for details."

    # nmap: inject --privileged so raw socket features work for the scanner user
    # (the nmap binary has cap_net_raw,cap_net_admin via setcap in the Dockerfile)
    if re.match(r'^nmap\b', stripped, re.IGNORECASE):
        if not re.search(r'--privileged\b', stripped):
            return re.sub(r'^nmap\b', 'nmap --privileged', stripped, flags=re.IGNORECASE), None

    # nuclei: force -ud /tmp/nuclei-templates so it writes to tmpfs, not the read-only fs
    if re.match(r'^nuclei\b', stripped, re.IGNORECASE):
        if not re.search(r'-ud\b', stripped):
            return re.sub(r'^nuclei\b', 'nuclei -ud /tmp/nuclei-templates', stripped, flags=re.IGNORECASE), None

    # wapiti: force plain text output to stdout so results appear in the terminal
    # instead of being written to a report file in /tmp that users can't easily access
    if re.match(r'^wapiti\b', stripped, re.IGNORECASE):
        if not re.search(r'\-o\b|--output\b', stripped):
            notice = "Note: wapiti output is being redirected to the terminal (-f txt -o /dev/stdout)."
            return stripped + ' -f txt -o /dev/stdout', notice

    return stripped, None
