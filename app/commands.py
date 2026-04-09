"""
Command loading, validation, and rewriting.

This module has no dependency on Flask or other app modules — it contains
pure functions that can be imported and tested in isolation.
"""

from copy import deepcopy
import html
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
APP_HINTS_MOBILE_FILE = os.path.join(_CONF, "app_hints_mobile.txt")

def _builtin_faq(app_name="darklab shell", project_readme="https://gitlab.com/darklab.sh/shell.darklab.sh#darklab-shell"):
    return [
        {
            "question": "What is this?",
            "answer": (
                f"{app_name} is a lightweight web interface for running network diagnostic "
                "and vulnerability scanning commands against remote endpoints, with output streamed "
                "in real time. It's designed for testing and troubleshooting remote hosts."
            ),
            "answer_html": (
                f"{app_name} is a lightweight web interface for running network diagnostic "
                "and vulnerability scanning commands against remote endpoints, with output streamed "
                "in real time. It's designed for testing and troubleshooting remote hosts — things "
                "like DNS lookups, port scans, traceroutes, HTTP checks, and web app vulnerability "
                "scans — without needing SSH access to a server. For more detailed information, see "
                f"the project README at <a href=\"{html.escape(project_readme, quote=True)}\" "
                "target=\"_blank\" rel=\"noopener\" style=\"color:var(--green)\">README</a>."
            ),
        },
        {
            "question": "What commands are allowed?",
            "answer": "Use the grouped allowlist shown in the FAQ modal or run ls in the web shell.",
            "ui_kind": "allowed_commands",
        },
        {
            "question": "How do I save or share my results?",
            "answer": "Use permalink, copy, save .html, or save .txt from the tab action bar.",
            "answer_html": (
                "There are several options below each tab's output:<br><br>"
                "<code>permalink</code> — saves a snapshot of everything visible in the tab and "
                "generates a shareable URL. The snapshot page lets the recipient copy, download, or "
                "inspect the raw data.<br>"
                "<code>copy</code> — copies the full plain-text output to your clipboard.<br>"
                "<code>save .html</code> — downloads a themed HTML file with ANSI colors "
                "preserved. It uses app-hosted vendor fonts when viewed alongside this shell and "
                "falls back to browser monospace fonts offline.<br>"
                "<code>save .txt</code> — downloads a plain-text version of the output.<br><br>"
                "Single-run permalinks are also available from the <strong>⧖ history</strong> panel."
            ),
        },
        {
            "question": "How do tabs and permalinks work?",
            "answer": (
                "Each command runs in the active tab. Use additional tabs to keep results visible "
                "side by side."
            ),
            "answer_html": (
                "Each command runs in the currently active tab. Open additional tabs with the "
                "<strong>+</strong> button to keep results from different sessions visible at the "
                "same time. Each tab tracks its own status independently. Double-click a tab label to "
                "rename it.<br><br>"
                "The <strong>permalink</strong> button captures everything currently visible in that "
                "tab and saves it as a shareable page. If a full saved artifact exists, the permalink "
                "uses that full output. The link opens a styled HTML view with ANSI color rendering "
                "and options to copy to clipboard, save as .html, save as .txt, or view raw JSON. "
                "Permalinks survive container restarts.<br><br>"
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
            "question": "Are there keyboard shortcuts?",
            "answer": (
                "Yes. Run shortcuts in the web shell for the current shortcut list, including tab, output, "
                "kill-dialog, welcome, autocomplete, and readline-style editing bindings."
            ),
            "answer_html": (
                "Yes. Current shell-style shortcuts include:<br><br>"
                "<ul style=\"margin:0 0 0 18px;padding:0;line-height:1.6\">"
                "<li><code>Ctrl+C</code> — open kill confirmation while a command is running, or "
                "drop to a fresh prompt line when idle.</li>"
                "<li><code>Enter</code> on a blank prompt — create a new empty prompt line.</li>"
                "<li><code>Option+T</code> / <code>Alt+T</code> and <code>Option+W</code> / "
                "<code>Alt+W</code> — open or close the current tab.</li>"
                "<li><code>Option+←/→</code> and <code>Option+1...9</code> (<code>Alt+←/→</code>, "
                "<code>Alt+1...9</code>) — switch tabs.</li>"
                "<li><code>Option+P</code> (<code>Alt+P</code>) — create a permalink for the active "
                "tab.</li>"
                "<li><code>Option+Shift+C</code> (<code>Alt+Shift+C</code>) — copy the active tab "
                "output.</li>"
                "<li><code>Ctrl+L</code> — clear the active tab.</li>"
                "<li><strong>Kill dialog:</strong> <code>Enter</code> confirms and "
                "<code>Escape</code> cancels.</li>"
                "<li><code>Ctrl+A</code>, <code>Ctrl+E</code>, <code>Ctrl+W</code>, "
                "<code>Ctrl+U</code>, <code>Ctrl+K</code>, <code>Option+B</code>, and "
                "<code>Option+F</code> (<code>Alt+B</code>, <code>Alt+F</code>) provide "
                "readline-style prompt editing.</li>"
                "<li><strong>Welcome screen:</strong> printable typing, <code>Enter</code>, and "
                "<code>Escape</code> all settle the welcome animation immediately.</li>"
                "<li><strong>Autocomplete:</strong> <code>↑↓</code> navigate, <code>Tab</code> "
                "accepts, <code>Enter</code> accepts or runs, and <code>Escape</code> dismisses.</li>"
                "</ul>"
                "<br>On macOS, the app-safe tab/action shortcuts use the <strong>Option</strong> "
                "key. The <strong>Ctrl+...</strong> bindings are intentional shell-style controls, "
                "not replacements for browser <strong>Command</strong> shortcuts.<br><br>You can "
                "also run <code>shortcuts</code> in the terminal for the current shortcut reference."
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
        {
            "question": "Why does mtr look different here?",
            "answer": (
                "mtr requires a real terminal (TTY) for its live interactive display, which isn't "
                "available in a web shell. It runs in --report-wide mode instead."
            ),
            "answer_html": (
                "<code>mtr</code> needs a real terminal (TTY) for its interactive display, which "
                "isn't available in a web shell. It automatically runs in <code>--report-wide</code> "
                "mode here, printing 10 probe cycles and a summary table. You can change the cycle "
                "count with <code>-c</code>, e.g. <code class=\"faq-example\">mtr -c 20 google.com</code>"
            ),
        },
    ]

_FAQ_CHIP_RE = re.compile(r'\[\[(?:cmd|chip):(.+?)\]\]')
_FAQ_BOLD_RE = re.compile(r'\*\*(.+?)\*\*')
_FAQ_ITALIC_RE = re.compile(r'(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)')
_FAQ_UNDER_RE = re.compile(r'__(.+?)__')
_FAQ_CODE_RE = re.compile(r'`([^`]+)`')


def _faq_inline_markup(text):
    text = html.escape(str(text), quote=False)

    def repl_chip(match):
        raw = match.group(1).strip()
        if not raw:
            return ''
        cmd, label = raw, raw
        if '|' in raw:
            cmd, label = raw.split('|', 1)
            cmd = cmd.strip()
            label = label.strip() or cmd
        cmd = html.escape(cmd, quote=True)
        label = html.escape(label, quote=False)
        return (
            f'<span class="allowed-chip faq-chip" role="button" tabindex="0" '
            f'data-faq-command="{cmd}">{label}</span>'
        )

    text = _FAQ_CHIP_RE.sub(repl_chip, text)
    text = _FAQ_CODE_RE.sub(r'<code>\1</code>', text)
    text = _FAQ_BOLD_RE.sub(r'<strong>\1</strong>', text)
    text = _FAQ_UNDER_RE.sub(r'<u>\1</u>', text)
    text = _FAQ_ITALIC_RE.sub(r'<em>\1</em>', text)
    return text


def render_faq_markup(text):
    """Render a safe FAQ mini-markup string to HTML."""
    if text is None:
        return ""

    lines = str(text).replace('\r\n', '\n').replace('\r', '\n').split('\n')
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        stripped = line.lstrip()
        if stripped.startswith('- ') or stripped.startswith('* '):
            items = []
            while i < len(lines):
                candidate = lines[i]
                candidate_stripped = candidate.lstrip()
                if not candidate_stripped or not (candidate_stripped.startswith('- ') or candidate_stripped.startswith('* ')):
                    break
                items.append(f"<li>{_faq_inline_markup(candidate_stripped[2:].strip())}</li>")
                i += 1
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue

        para_lines = []
        while i < len(lines):
            candidate = lines[i]
            candidate_stripped = candidate.lstrip()
            if not candidate.strip() or candidate_stripped.startswith('- ') or candidate_stripped.startswith('* '):
                break
            para_lines.append(_faq_inline_markup(candidate.strip()))
            i += 1
        blocks.append("<br>".join(para_lines))

    return "<br><br>".join(blocks)


def _local_overlay_path(path):
    root, ext = os.path.splitext(path)
    return f"{root}.local{ext}"


def _load_text_lines(path):
    lines = []
    for candidate in (path, _local_overlay_path(path)):
        if not os.path.exists(candidate):
            continue
        with open(candidate) as f:
            lines.extend(f.readlines())
    return lines


def _load_yaml_list(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or []
    return data if isinstance(data, list) else []


def _load_yaml_list_with_local(path):
    items = _load_yaml_list(path)
    local_path = _local_overlay_path(path)
    if os.path.exists(local_path):
        try:
            items.extend(_load_yaml_list(local_path))
        except yaml.YAMLError:
            pass
    return items


def _dedupe_preserve_order(values):
    return list(dict.fromkeys(values))

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
    for raw_line in _load_text_lines(ALLOWED_COMMANDS_FILE):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            denied.append(line[1:].strip().lower())
        else:
            prefixes.append(line.lower())
    prefixes = _dedupe_preserve_order(prefixes)
    denied = _dedupe_preserve_order(denied)
    return (prefixes if prefixes else None), denied


def load_allowed_commands_grouped():
    """Read allowed_commands.txt and return commands grouped by ## Category headers.
    Returns a list of {name, commands} dicts, or None if file is empty/missing.
    Lines starting with ! (deny prefixes) are excluded from the display list."""
    if not os.path.exists(ALLOWED_COMMANDS_FILE):
        return None
    groups = []
    group_map = {}
    current = None
    for raw_line in _load_text_lines(ALLOWED_COMMANDS_FILE):
        line = raw_line.strip()
        if line.startswith("## "):
            name = line[3:].strip()
            current = group_map.get(name)
            if current is None:
                current = {"name": name, "commands": []}
                groups.append(current)
                group_map[name] = current
        elif line and not line.startswith("#") and not line.startswith("!"):
            if current is None:
                current = group_map.get("")
                if current is None:
                    current = {"name": "", "commands": []}
                    groups.append(current)
                    group_map[""] = current
            current["commands"].append(line.lower())
    for group in groups:
        group["commands"] = _dedupe_preserve_order(group["commands"])
    groups = [g for g in groups if g["commands"]]
    return groups if groups else None


def load_faq():
    """Read faq.yaml and return a list of {question, answer} dicts.
    Returns an empty list if the file doesn't exist or contains no valid entries."""
    data = _load_yaml_list_with_local(FAQ_FILE)
    result = []
    for item in data:
        if not isinstance(item, dict) or not item.get("question") or not item.get("answer"):
            continue
        entry = {"question": str(item["question"]), "answer": str(item["answer"])}
        if item.get("answer_html"):
            entry["answer_html"] = str(item["answer_html"])
        else:
            entry["answer_html"] = render_faq_markup(entry["answer"])
        result.append(entry)
    return result


def load_all_faq(app_name="darklab shell", project_readme="https://gitlab.com/darklab.sh/shell.darklab.sh#darklab-shell"):
    """Return the built-in FAQ entries followed by any custom faq.yaml entries."""
    return [*(deepcopy(_builtin_faq(app_name, project_readme))), *load_faq()]


def load_welcome():
    """Read welcome.yaml and return startup blocks for the welcome typeout.
    Returns an empty list if the file is missing or empty, disabling the welcome animation."""
    data = _load_yaml_list_with_local(WELCOME_FILE)
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
    local_path = _local_overlay_path(ASCII_FILE)
    if os.path.exists(local_path):
        with open(local_path) as f:
            return f.read().rstrip()
    if not os.path.exists(ASCII_FILE):
        return ""
    with open(ASCII_FILE) as f:
        return f.read().rstrip()


def load_ascii_mobile_art():
    """Read ascii_mobile.txt and return the compact mobile banner art."""
    local_path = _local_overlay_path(ASCII_MOBILE_FILE)
    if os.path.exists(local_path):
        with open(local_path) as f:
            return f.read().rstrip()
    if not os.path.exists(ASCII_MOBILE_FILE):
        return ""
    with open(ASCII_MOBILE_FILE) as f:
        return f.read().rstrip()


def load_welcome_hints():
    """Read app_hints.txt and return a list of app-usage hints."""
    hints = []
    seen = set()
    for raw_line in _load_text_lines(APP_HINTS_FILE):
        line = raw_line.strip()
        if line and not line.startswith("#") and line not in seen:
            hints.append(line)
            seen.add(line)
    return hints


def load_mobile_welcome_hints():
    """Read app_hints_mobile.txt and return a list of mobile-specific hints."""
    hints = []
    seen = set()
    for raw_line in _load_text_lines(APP_HINTS_MOBILE_FILE):
        line = raw_line.strip()
        if line and not line.startswith("#") and line not in seen:
            hints.append(line)
            seen.add(line)
    return hints


def load_autocomplete():
    """Read auto_complete.txt and return a list of suggestion strings."""
    suggestions = []
    seen = set()
    for raw_line in _load_text_lines(AUTOCOMPLETE_FILE):
        line = raw_line.strip()
        if line and not line.startswith("#") and line not in seen:
            suggestions.append(line)
            seen.add(line)
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
