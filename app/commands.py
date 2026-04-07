"""
Command loading, validation, and rewriting.

This module has no dependency on Flask or other app modules — it contains
pure functions that can be imported and tested in isolation.
"""

from copy import deepcopy
import os
import re
import shlex
import shutil
import yaml

_HERE = os.path.dirname(__file__)
_CONF = os.path.join(_HERE, "conf")
ALLOWED_COMMANDS_FILE = os.path.join(_CONF, "allowed_commands.txt")
AUTOCOMPLETE_FILE     = os.path.join(_CONF, "auto_complete.txt")
FAQ_FILE              = os.path.join(_CONF, "faq.yaml")
WELCOME_FILE          = os.path.join(_CONF, "welcome.yaml")
ASCII_FILE            = os.path.join(_CONF, "ascii.txt")
ASCII_MOBILE_FILE     = os.path.join(_CONF, "ascii_mobile.txt")
APP_HINTS_FILE        = os.path.join(_CONF, "app_hints.txt")

BUILTIN_FAQ = [
    {
        "question": "What is this?",
        "answer": (
            "shell.darklab.sh is a lightweight web interface for running network diagnostic "
            "and vulnerability scanning commands against remote endpoints, with output streamed "
            "in real time. It's designed for testing and troubleshooting remote hosts."
        ),
        "answer_html": (
            "shell.darklab.sh is a lightweight web interface for running network diagnostic "
            "and vulnerability scanning commands against remote endpoints, with output streamed "
            "in real time. It's designed for testing and troubleshooting remote hosts — things "
            "like DNS lookups, port scans, traceroutes, HTTP checks, and web app vulnerability "
            "scans — without needing SSH access to a server. For more detailed information, see "
            "the <a href=\"https://gitlab.com/darklab.sh/shell.darklab.sh\" target=\"_blank\" "
            "rel=\"noopener\" style=\"color:var(--green)\">README on GitLab</a>."
        ),
    },
    {
        "question": "What commands are allowed?",
        "answer": "Use the grouped allowlist shown in the FAQ modal or run ls in the web shell.",
        "ui_kind": "allowed_commands",
    },
    {
        "question": "Why does mtr look different here?",
        "answer": (
            "mtr requires a real terminal (TTY) for its live interactive display, which isn't "
            "available in a web shell. It runs in --report-wide mode instead."
        ),
        "answer_html": (
            "<code>mtr</code> requires a real terminal (TTY) for its live interactive display, "
            "which isn't available in a web shell. It's automatically run in "
            "<code>--report-wide</code> mode instead, which runs 10 probe cycles and prints a "
            "summary table. You can control the cycle count with <code>-c</code>, e.g. "
            "<code class=\"faq-example\">mtr -c 20 google.com</code>"
        ),
    },
    {
        "question": "Can I request a new tool?",
        "answer": "Yes. Contact the instance operator to request additional allowlisted tools.",
        "answer_html": (
            "Yes! If there's a tool you'd like added, send a request to "
            "<strong>admin [at] darklab [dot] sh</strong> and we'll consider it for a future update."
        ),
    },
    {
        "question": "How do tabs and permalinks work?",
        "answer": (
            "Each command runs in the active tab. Use additional tabs to keep results visible "
            "side by side. The permalink action saves a shareable view of the visible output."
        ),
        "answer_html": (
            "Each command runs in the currently active tab. You can open additional tabs with the "
            "<strong>+</strong> button to run commands side by side and keep results from "
            "different sessions visible at the same time. Each tab tracks its own status "
            "independently. Double-click a tab label to rename it.<br><br>"
            "The <strong>permalink</strong> button on each tab captures everything currently "
            "visible in that tab and saves it as a shareable page. The link opens a styled HTML "
            "view with ANSI color rendering and options to copy to clipboard, save as .html, save "
            "as .txt, or view raw JSON. Permalinks survive container restarts.<br><br>"
            "The <strong>⧖ history</strong> panel shows your recent runs. You can load any past "
            "result into a new tab, copy a single-run permalink from there, or <strong>★ star</strong> "
            "a command to pin it to the top of the list."
        ),
    },
    {
        "question": "How do I stop a running command?",
        "answer": "Use the Kill button shown while a command is running.",
        "answer_html": (
            "Click the <strong style=\"color:var(--red)\">■ Kill</strong> button that appears "
            "while a command is running. This sends SIGTERM to the entire process group on the "
            "server, stopping it immediately."
        ),
    },
    {
        "question": "How do I access search, history and theme on mobile?",
        "answer": "Use the mobile menu in the top-right corner.",
        "answer_html": (
            "On small screens the header buttons are replaced by a <strong>☰</strong> menu in the "
            "top-right corner. Tap it to access search, run history, line numbers, timestamps, "
            "theme, and this FAQ."
        ),
    },
    {
        "question": "How do I save or share my results?",
        "answer": "Use permalink, copy, save .html, or save .txt from the tab action bar.",
        "answer_html": (
            "There are several options from the action bar below each tab's output:<br><br>"
            "<strong>permalink</strong> — saves a snapshot of everything visible in the tab and "
            "generates a shareable URL. The snapshot page lets the recipient copy, download, or "
            "view the raw data.<br>"
            "<strong>copy</strong> — copies the full plain-text output to your clipboard.<br>"
            "<strong>save .html</strong> — downloads a self-contained HTML file with ANSI colors "
            "preserved, suitable for archiving or sending to someone without a browser link.<br>"
            "<strong>save .txt</strong> — downloads a plain-text version of the output.<br><br>"
            "Single-run permalinks are also available from the <strong>⧖ history</strong> panel."
        ),
    },
    {
        "question": "How do I rename a tab?",
        "answer": "Double-click the tab label, then press Enter or click away to confirm.",
        "answer_html": (
            "Double-click the tab label to edit it inline. Press <strong>Enter</strong> or click "
            "anywhere outside to confirm, or <strong>Escape</strong> to cancel. Once renamed, "
            "running a command won't overwrite the label — the tab keeps your chosen name."
        ),
    },
    {
        "question": "What do the timestamp options do?",
        "answer": "They toggle off, elapsed, and clock timestamp display modes for output lines.",
        "answer_html": (
            "The <strong>timestamps</strong> button in the terminal bar cycles through three modes:"
            "<br><br><strong>off</strong> — no timestamps shown (default).<br>"
            "<strong>elapsed</strong> — shows how many seconds after the command started each line "
            "appeared (e.g. <code>+4.2s</code>). Useful for understanding how long different "
            "stages of a scan take.<br><strong>clock</strong> — shows the wall-clock time each "
            "line was received (e.g. <code>14:32:01</code>). Useful for correlating output with "
            "events elsewhere."
        ),
    },
    {
        "question": "What do the line number options do?",
        "answer": "They toggle numbered output lines on and off for easier line-by-line reference.",
        "answer_html": (
            "The <strong>line numbers</strong> button in the terminal bar toggles numbered output "
            "lines on and off.<br><br><strong>off</strong> — no line numbers are shown (default)."
            "<br><strong>on</strong> — every output line is prefixed with a sequence number so "
            "you can reference specific rows while reading long scans or copied output."
        ),
    },
    {
        "question": "Are there keyboard shortcuts?",
        "answer": (
            "Yes. Run keys in the web shell for the current shortcut list, including tab, output, "
            "kill-dialog, welcome, autocomplete, and readline-style editing bindings."
        ),
        "answer_html": (
            "Yes. Current shell-style shortcuts include:<br><br>"
            "<strong>Ctrl+C</strong> — open kill confirmation while a command is running, or drop "
            "to a fresh prompt line when idle.<br>"
            "<strong>Enter</strong> on a blank prompt — create a new empty prompt line.<br>"
            "<strong>Option+T</strong> / <strong>Alt+T</strong> and <strong>Option+W</strong> / "
            "<strong>Alt+W</strong> — open or close the current tab.<br>"
            "<strong>Option+←/→</strong> and <strong>Option+1...9</strong> "
            "(<strong>Alt+←/→</strong>, <strong>Alt+1...9</strong>) — switch tabs.<br>"
            "<strong>Option+P</strong> (<strong>Alt+P</strong>) — create a permalink for the "
            "active tab.<br><strong>Option+Shift+C</strong> (<strong>Alt+Shift+C</strong>) — copy "
            "the active tab output.<br><strong>Ctrl+L</strong> — clear the active tab.<br>"
            "<strong>Kill dialog:</strong> <strong>Enter</strong> confirms and "
            "<strong>Escape</strong> cancels.<br><strong>Ctrl+A</strong>, <strong>Ctrl+E</strong>, "
            "<strong>Ctrl+W</strong>, <strong>Ctrl+U</strong>, <strong>Ctrl+K</strong>, "
            "<strong>Option+B</strong>, and <strong>Option+F</strong> (<strong>Alt+B</strong>, "
            "<strong>Alt+F</strong>) provide readline-style prompt editing.<br>"
            "<strong>Welcome screen:</strong> printable typing, <strong>Enter</strong>, "
            "and <strong>Escape</strong> all settle the welcome animation immediately.<br>"
            "<strong>Autocomplete:</strong> <strong>↑↓</strong> navigate, <strong>Tab</strong> "
            "accepts, <strong>Enter</strong> accepts or runs, and <strong>Escape</strong> "
            "dismisses.<br><br>On macOS, the app-safe tab/action shortcuts use the "
            "<strong>Option</strong> key. The <strong>Ctrl+...</strong> bindings are intentional "
            "shell-style controls, not replacements for browser <strong>Command</strong> "
            "shortcuts.<br><br>You can also run <code>keys</code> in the terminal for the current "
            "shortcut reference and any remaining browser-native fallback notes."
        ),
    },
    {
        "question": "Are my commands visible to other users?",
        "answer": "No. History and saved data are scoped to your anonymous browser session.",
        "answer_html": (
            "No. Each browser session is assigned an anonymous ID stored in your browser's local "
            "storage. Your run history, starred commands, and saved snapshots are only visible to "
            "sessions sharing that ID — in practice, just your own browser tabs. Commands are not "
            "broadcast or shared between users."
        ),
    },
    {
        "question": "What are the retention and limit settings for this instance?",
        "answer": "See the live retention and limit table in the FAQ modal or run retention in the web shell.",
        "ui_kind": "limits",
    },
    {
        "question": "What wordlists are available?",
        "answer": "The SecLists collection is installed at /usr/share/wordlists/seclists/.",
        "answer_html": (
            "The full <a href=\"https://github.com/danielmiessler/SecLists\" target=\"_blank\" "
            "rel=\"noopener\" style=\"color:var(--green)\">SecLists</a> collection is installed at "
            "<code>/usr/share/wordlists/seclists/</code>. Commonly used lists:<ul>"
            "<li><code>Discovery/Web-Content/common.txt</code> — fast directory scan</li>"
            "<li><code>Discovery/Web-Content/big.txt</code> — broader directory scan</li>"
            "<li><code>Discovery/Web-Content/DirBuster-2007_directory-list-2.3-big.txt</code> — "
            "thorough directory scan</li></ul>"
        ),
    },
]

# Shell metacharacters that can chain or redirect commands.
# Used for detection (SHELL_CHAIN_RE.search) and splitting (split_chained_commands).
# Both use >>? so > and >> are matched without allowing whitespace between them.
SHELL_CHAIN_RE = re.compile(r'&&|\|\|?|;;?|`|\$\(|>>?|<')

# Pre-compiled path blocking patterns — negative lookbehind prevents false
# positives on URLs such as https://darklab.sh/data/ or /tmp/ path segments.
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


def load_all_faq():
    """Return the built-in FAQ entries followed by any custom faq.yaml entries."""
    return [*(deepcopy(BUILTIN_FAQ)), *load_faq()]


def load_welcome():
    """Read welcome.yaml and return startup blocks for the welcome typeout.
    Returns an empty list if the file is missing or empty, disabling the welcome animation."""
    if not os.path.exists(WELCOME_FILE):
        return []
    with open(WELCOME_FILE) as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        return []
    return [
        {
            "cmd": str(item.get("cmd", "")).strip(),
            "out": str(item.get("out", "")).rstrip() if item.get("out") else "",
            "group": str(item.get("group", "")).strip().lower() if item.get("group") else "",
            "featured": bool(item.get("featured", False)),
        }
        for item in data
        if isinstance(item, dict) and item.get("cmd")
    ]


def load_ascii_art():
    """Read ascii.txt and return the welcome banner art as plain text.
    Returns an empty string if the file is missing or empty."""
    if not os.path.exists(ASCII_FILE):
        return ""
    with open(ASCII_FILE) as f:
        return f.read().rstrip()


def load_ascii_mobile_art():
    """Read ascii_mobile.txt and return the compact mobile banner art."""
    if not os.path.exists(ASCII_MOBILE_FILE):
        return ""
    with open(ASCII_MOBILE_FILE) as f:
        return f.read().rstrip()


def load_welcome_hints():
    """Read app_hints.txt and return a list of app-usage hints."""
    if not os.path.exists(APP_HINTS_FILE):
        return []
    hints = []
    with open(APP_HINTS_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                hints.append(line)
    return hints


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


def split_command_argv(command: str) -> list[str]:
    """Split a shell-like command string into argv tokens for simple root-command inspection."""
    try:
        return shlex.split(command)
    except ValueError:
        return command.strip().split()


def command_root(command: str) -> str | None:
    """Return the first argv token from a command string, lowercased."""
    parts = split_command_argv(command)
    if not parts:
        return None
    return parts[0].strip().lower() or None


def resolve_runtime_command(command_name: str) -> str | None:
    """Return the absolute path to command_name if installed on this instance."""
    return shutil.which(command_name)


def runtime_missing_command_name(command: str) -> str | None:
    """Return the missing root command name for a command string, or None if installed/empty."""
    root = command_root(command)
    if not root:
        return None
    return None if resolve_runtime_command(root) else root


def runtime_missing_command_message(command_name: str) -> str:
    """Return the standard instance-level message for missing runtime commands."""
    return f"Command is not installed on this instance: {command_name}"


def split_chained_commands(command: str) -> list[str]:
    """Split a command string on any shell chaining/piping/redirection operator
    and return the individual command tokens so each can be validated."""
    parts = SHELL_CHAIN_RE.split(command)
    return [p.strip() for p in parts if p.strip()]


def _is_denied(cmd_lower: str, deny_entries: list[str]) -> bool:
    """Return True if cmd_lower matches any deny entry.
    A deny entry like 'curl -o' is matched if:
      - the command starts with the deny prefix, OR
      - the tool prefix matches AND the flag appears anywhere as a space-separated
        token in the command, so 'curl -s -o file' is caught as well as 'curl -o file'.
    For single-character flags (e.g. -e, -c), the flag is also matched when combined
    with other single-char flags in a group: 'nc -ve' is caught by '!nc -e', and
    'nc -vc' is caught by '!nc -c'. Multi-char flags (--script, -oN) use exact-token
    matching only.
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
        if not (cmd_lower == tool_prefix or cmd_lower.startswith(tool_prefix + " ")):
            continue
        # Single-char flag (e.g. -e): also match when combined with other flags
        # in a group, such as -ve or -zve. Multi-char flags use exact-token match only.
        if len(flag) == 2 and flag[0] == '-' and flag[1].isalpha():
            char = re.escape(flag[1])
            pattern = r'(?<= )-[a-z]*' + char + r'[a-z]*(?= |$)'
        else:
            pattern = r'(?<= )' + re.escape(flag) + r'(?= |$)'
        if re.search(pattern, cmd_lower):
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
