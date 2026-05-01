"""
Command loading, validation, and rewriting.

This module has no dependency on Flask — it contains pure helpers that can be
imported and tested in isolation.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import html
import ipaddress
import os
import re
import shlex
import shutil
import yaml
from urllib.parse import urlparse

import config as app_config
from workspace import (
    ensure_session_workspace,
    InvalidWorkspacePath,
    WorkspaceDisabled,
    WorkspaceFileNotFound,
    prepare_workspace_directory_for_command,
    prepare_workspace_file_for_command,
    read_workspace_text_file,
    resolve_workspace_path,
)

_HERE = os.path.dirname(__file__)
_CONF = os.path.join(_HERE, "conf")
COMMANDS_REGISTRY_FILE = os.path.join(_CONF, "commands.yaml")
BUILTIN_AUTOCOMPLETE_FILE = os.path.join(_HERE, "builtin_autocomplete.yaml")
FAQ_FILE              = os.path.join(_CONF, "faq.yaml")
WORKFLOWS_FILE        = os.path.join(_CONF, "workflows.yaml")
WELCOME_FILE          = os.path.join(_CONF, "welcome.yaml")
ASCII_FILE            = os.path.join(_CONF, "ascii.txt")
ASCII_MOBILE_FILE     = os.path.join(_CONF, "ascii_mobile.txt")
APP_HINTS_FILE        = os.path.join(_CONF, "app_hints.txt")
APP_HINTS_MOBILE_FILE = os.path.join(_CONF, "app_hints_mobile.txt")
AMASS_DEFAULT_WORKSPACE_DIR = "amass"
RESTRICTABLE_VALUE_TYPES = {"cidr", "domain", "host", "ip", "target", "url"}
NMAP_DENIED_RAW_FLAGS = {"-sS"}
NMAP_SCAN_MODE_FLAGS = {
    "-sA", "-sF", "-sI", "-sL", "-sM", "-sN", "-sO", "-sS",
    "-sT", "-sU", "-sW", "-sX", "-sY", "-sZ", "-sn",
}


@dataclass(frozen=True)
class CommandValidationResult:
    allowed: bool
    reason: str = ""
    display_command: str = ""
    exec_command: str = ""
    workspace_reads: list[str] = field(default_factory=list)
    workspace_writes: list[str] = field(default_factory=list)
    workspace_exec_paths: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)


def _project_readme_url(project_readme=None):
    return project_readme or app_config.PROJECT_README


def _builtin_faq(app_name="darklab_shell", project_readme=None, cfg=None):
    readme_url = _project_readme_url(project_readme)
    entries = [
        {
            "question": "What is this?",
            "answer": (
                f"{app_name} is a lightweight web interface for running network diagnostic "
                "and vulnerability scanning commands against remote endpoints, with output streamed "
                "in real time. It's designed for testing and troubleshooting remote hosts. "
                f"See the project README: {readme_url}"
            ),
            "answer_html": (
                f"{app_name} is a lightweight web interface for running network diagnostic "
                "and vulnerability scanning commands against remote endpoints, with output streamed "
                "in real time. It's designed for testing and troubleshooting remote hosts — things "
                "like DNS lookups, port scans, traceroutes, HTTP checks, and web app vulnerability "
                "scans — without needing SSH access to a server. For more detailed information, see "
                f"the project <a href=\"{html.escape(readme_url, quote=True)}\" target=\"_blank\" "
                "rel=\"noopener\" class=\"faq-link\">README</a>."
            ),
        },
        {
            "question": "What commands are allowed?",
            "answer": "Use the grouped allowlist shown in the FAQ modal or run commands --external in the web shell.",
            "ui_kind": "allowed_commands",
        },
        {
            "question": "What are session Files?",
            "feature": "workspace",
            "answer": (
                "Files are app-managed, session-scoped text files for commands that need small inputs "
                "or outputs. Use the Files panel or run file help to create, view, edit, "
                "download, or delete files."
            ),
            "answer_html": (
                "Files are app-managed, session-scoped text files for commands that need small "
                "inputs or outputs. Use the <strong>Files</strong> panel or run "
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"file help\">file help</span> "
                "to create, view, edit, download, or delete files.<br><br>"
                "Commands can only read or write files through command flags explicitly enabled "
                "in the command registry. Shell navigation and redirection are still blocked. "
                "Files stay scoped to the current browser session or named session token."
            ),
        },
        {
            "question": "How do I save or share my results?",
            "answer": "Use share snapshot, copy, save .html, or save .txt from the tab action bar.",
            "answer_html": (
                "There are several options below each tab's output:<br><br>"
                "<code>share snapshot</code> — saves a shareable snapshot of everything visible in "
                "the current tab and generates a <code>/share</code> URL. When redaction is enabled, "
                "you can choose whether that snapshot should be shared raw or redacted before it is "
                "saved.<br>"
                "<code>copy</code> — copies the full plain-text output to your clipboard.<br>"
                "<code>save .html</code> — downloads a themed HTML file with ANSI colors "
                "preserved. It uses app-hosted vendor fonts when viewed alongside this shell and "
                "falls back to browser monospace fonts offline.<br>"
                "<code>save .txt</code> — downloads a plain-text version of the output.<br><br>"
                "The <strong>⧖ history</strong> panel also provides <code>run permalink</code>, which "
                "copies the canonical <code>/history/&lt;run_id&gt;</code> link for one saved command."
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
                "The <strong>share snapshot</strong> button captures everything currently visible in "
                "that tab and saves it as a shareable <code>/share</code> page. If a full saved "
                "artifact exists, the snapshot uses that full output. The shared page opens a styled "
                "HTML view with ANSI color rendering and options to copy to clipboard, save as .html, "
                "save as .txt, or view raw JSON. Snapshot links survive container restarts.<br><br>"
                "The <strong>⧖ history</strong> panel shows your recent runs. You can load any past "
                "result into a new tab, copy a <strong>run permalink</strong> from there, or "
                "<strong>★ star</strong> a command to pin it to the top of the list. Use "
                "<strong>share snapshot</strong> when you want a share/export view of the active tab; "
                "use <strong>run permalink</strong> when you want the canonical link for one saved "
                "command in history."
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
            "question": "How do session tokens work?",
            "answer": (
                "Without a session token, your history is tied to your current browser — switch browsers "
                "or workstations and you start fresh. Set a token and any browser that uses the same "
                "token shares your run history, starred commands, and saved user options."
            ),
            "answer_html": (
                "Without a session token, your history is tied to your current browser. Switch to a "
                "different browser or workstation and you start fresh.<br><br>"
                "Set a <strong>session token</strong> and any browser that uses the same token shares "
                "your run history, starred commands, and saved user options — useful if you work across "
                "multiple machines or want to pick up where you left off after clearing your browser.<br><br>"
                "Use these commands to manage your session token:<br><br>"
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"session-token\">session-token</span>"
                " — show whether a token is active.<br>"
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"session-token generate\">session-token generate</span>"
                " — create and activate a new random token.<br>"
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"session-token set \">session-token set</span>"
                " — activate a specific token you already have.<br>"
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"session-token rotate\">session-token rotate</span>"
                " — replace your current token with a new random one.<br>"
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"session-token clear\">session-token clear</span>"
                " — remove your token and return to a browser-local session.<br><br>"
                "You can also use the <strong>Generate</strong>, <strong>Set</strong>, "
                "<strong>Rotate</strong>, and <strong>Clear</strong> buttons in the "
                "<strong>Options</strong> panel."
            ),
        },
        {
            "question": "What built-in shell features are supported?",
            "answer": (
                "The shell supports built-in commands plus a narrow set of commands with built-in "
                "pipe support like grep, head, tail, wc -l, sort, and uniq. For a full list of built-in "
                "commands, run commands --built-in in the web shell."
            ),
            "answer_html": (
                "This shell includes two kinds of built-in behavior:<br><br>"
                "<strong>Built-in commands</strong> such as <code>status</code>, "
                "<code>history</code>, <code>retention</code>, <code>shortcuts</code>, "
                "<code>limits</code>, and <code>faq</code>. For a full list, run "
                "<code>commands --built-in</code>."
                " These are provided directly by the shell.<br><br>"
                "<strong>Commands with built-in pipe support</strong> let you trim output with "
                "supported pipe helpers, for example <code>command | grep pattern</code>, "
                "<code>command | head -n 20</code>, <code>command | head -20</code>, "
                "<code>command | tail -n 20</code>, <code>command | tail -20</code>, "
                "<code>command | wc -l</code>, <code>command | sort -rn</code>, or "
                "<code>command | uniq -c</code>. These helpers can also be chained together, "
                "for example <code>command | grep pattern | wc -l</code>.<br><br>"
                "General shell piping, arbitrary chaining, and redirection are still blocked."
            ),
        },
        {
            "question": "How do I stop a running command?",
            "answer": "Use the Kill button shown or press Ctrl+C while a command is running.",
            "answer_html": (
                "Click the <strong class=\"faq-kill-verb\">■ Kill</strong> button that appears "
                "while a command is running or press <code>Ctrl+C</code>. This sends SIGTERM to the "
                "entire process group on the server, stopping it immediately."
            ),
        },
        {
            "question": "Are there keyboard shortcuts?",
            "answer": (
                "Press ? from the terminal for the keyboard shortcuts overlay, "
                "or run 'shortcuts' in the shell for the same reference as a text dump."
            ),
            "answer_html": (
                "Press <code>?</code> from anywhere on the page to open the keyboard "
                "shortcuts overlay — including from the command prompt itself, as long "
                "as the prompt is empty. Once any text is in the prompt, <code>?</code> "
                "types normally so args like <code>curl \"…?foo=bar\"</code> are not "
                "interfered with. The overlay is a transparent reference covering tab, "
                "output, kill-dialog, welcome, autocomplete, and readline-style editing "
                "bindings.<br><br>"
                "For the same reference as plain text inside a tab, run "
                "<code>shortcuts</code> in the shell. Both surfaces read from the same "
                "source so they never drift."
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
            "question": "What are the retention and limit settings for this instance?",
            "answer": "See the live retention and limit table in the FAQ modal or run retention in the web shell.",
            "ui_kind": "limits",
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
            "question": "What wordlists are available?",
            "answer": "The SecLists collection is installed at /usr/share/wordlists/seclists/.",
            "answer_html": (
                "The full <a href=\"https://github.com/danielmiessler/SecLists\" target=\"_blank\" "
                "rel=\"noopener\" class=\"faq-link\">SecLists</a> collection is installed at "
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
        {
            "question": "Why does naabu use connect scan mode?",
            "answer": (
                "naabu defaults to raw SYN scanning which requires libpcap and elevated privileges "
                "not reliably available inside the container. It automatically runs with -scan-type c "
                "instead, using TCP connect scanning like nmap -sT. Results are the same."
            ),
            "answer_html": (
                "<code>naabu</code> defaults to raw SYN packet scanning via libpcap, which requires "
                "privileges that aren't reliably available in this environment. It automatically runs "
                "with <code>-scan-type c</code>, switching to TCP connect mode (equivalent to "
                "<code>nmap -sT</code>). Open ports are detected the same way — only the underlying "
                "method differs."
            ),
        },
    ]
    return [item for item in entries if _faq_entry_enabled(item, cfg)]

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
    # Every shipped config asset can be overridden by a sibling *.local.* file
    # so operators can customize behavior without editing tracked defaults.
    root, ext = os.path.splitext(path)
    return f"{root}.local{ext}"


def _load_text_lines(path):
    # Treat these config files as simple line lists and discard comments/blanks
    # before higher-level loaders consume them.
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

# Loopback address detection — catches bare hostnames and addresses embedded in
# URLs (e.g. "curl http://localhost:8888/diag" or "curl 127.0.0.1:8888/faq").
# Word-boundary anchors prevent false positives on hostnames that contain these
# strings as a substring.
_LOOPBACK_RE = re.compile(r'\blocalhost\b|127\.0\.0\.1|\b0\.0\.0\.0\b|\[::1\]', re.IGNORECASE)


def _split_shell_control_tokens(command: str) -> list[str]:
    """Split a shell-like command while keeping control operators as tokens."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars='|&;<>')
        lexer.whitespace_split = True
        lexer.commenters = ''
        return list(lexer)
    except ValueError:
        return []


def _parse_synthetic_grep_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the post-filter stage for the narrow app-native grep helper."""
    if stage_tokens[0].lower() != 'grep':
        return None, None

    options = {"ignore_case": False, "invert_match": False, "extended": False}
    pattern = None
    for token in stage_tokens[1:]:
        if pattern is not None:
            return None, "Synthetic grep only supports a single pattern argument."
        if token.startswith('-') and token != '-':
            if token.startswith('--'):
                return None, "Synthetic grep supports only -i, -v, and -E."
            for flag in token[1:]:
                if flag == 'i':
                    options["ignore_case"] = True
                elif flag == 'v':
                    options["invert_match"] = True
                elif flag == 'E':
                    options["extended"] = True
                else:
                    return None, "Synthetic grep supports only -i, -v, and -E."
            continue
        pattern = token

    if pattern is None:
        return None, "Synthetic grep requires a pattern."

    return {
        "kind": "grep",
        "pattern": pattern,
        **options,
    }, None


def _parse_synthetic_head_tail_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse narrow app-native head/tail helpers with default count, -n, or -<number>."""
    command_name = stage_tokens[0].lower()
    if command_name not in {"head", "tail"}:
        return None, None

    count = 10
    if len(stage_tokens) == 1:
        return {"kind": command_name, "count": count}, None

    if len(stage_tokens) == 2 and stage_tokens[1].startswith('-') and stage_tokens[1][1:].isdigit():
        return {"kind": command_name, "count": int(stage_tokens[1][1:])}, None

    if len(stage_tokens) != 3 or stage_tokens[1] != "-n":
        return None, f"Synthetic {command_name} supports only `-n <count>` or `-<count>`."
    if not stage_tokens[2].isdigit():
        return None, f"Synthetic {command_name} requires a non-negative numeric count."

    return {"kind": command_name, "count": int(stage_tokens[2])}, None


def _parse_synthetic_wc_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the narrow app-native `wc -l` helper."""
    if stage_tokens[0].lower() != "wc":
        return None, None
    if stage_tokens[1:] == ["-l"]:
        return {"kind": "wc_l"}, None
    return None, "Synthetic wc supports only `wc -l`."


_SORT_VALID_FLAGS = frozenset("rnu")


def _parse_synthetic_sort_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the narrow app-native sort helper. Supports -r, -n, -u in any combination."""
    if stage_tokens[0].lower() != "sort":
        return None, None
    if len(stage_tokens) == 1:
        return {"kind": "sort", "reverse": False, "numeric": False, "unique": False}, None
    if len(stage_tokens) == 2:
        flag = stage_tokens[1]
        if flag.startswith('-') and flag[1:] and set(flag[1:]).issubset(_SORT_VALID_FLAGS):
            chars = set(flag[1:])
            return {"kind": "sort", "reverse": "r" in chars,
                    "numeric": "n" in chars, "unique": "u" in chars}, None
    return None, "Synthetic sort supports only -r, -n, and -u flags."


def _parse_synthetic_uniq_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the narrow app-native uniq helper. Supports uniq and uniq -c."""
    if stage_tokens[0].lower() != "uniq":
        return None, None
    if len(stage_tokens) == 1:
        return {"kind": "uniq", "count": False}, None
    if len(stage_tokens) == 2 and stage_tokens[1] == "-c":
        return {"kind": "uniq", "count": True}, None
    return None, "Synthetic uniq supports only -c."


def _parse_synthetic_postfilter_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    for parser in (
        _parse_synthetic_grep_stage,
        _parse_synthetic_head_tail_stage,
        _parse_synthetic_wc_stage,
        _parse_synthetic_sort_stage,
        _parse_synthetic_uniq_stage,
    ):
        spec, error = parser(stage_tokens)
        if spec or error:
            return spec, error
    return None, None


def parse_synthetic_postfilter(command: str) -> tuple[dict | None, str | None]:
    """Parse a narrow app-native `command | helper ...` post-filter pipeline.

    Returns (spec, error_message). spec is None when the command does not use
    the synthetic post-filter path. error_message is populated only when the
    input is clearly trying to use a supported helper but the stage is invalid.
    """
    stripped = command.strip()
    if '|' not in stripped:
        return None, None
    if '`' in stripped or '$(' in stripped:
        return None, None

    tokens = _split_shell_control_tokens(stripped)
    if not tokens:
        return None, None

    disallowed_control = {'&&', '||', ';', ';;', '>', '>>', '<', '&'}
    if any(token in disallowed_control for token in tokens):
        return None, None

    pipe_indexes = [index for index, token in enumerate(tokens) if token == '|']
    if not pipe_indexes:
        return None, None

    base_tokens = tokens[:pipe_indexes[0]]
    if not base_tokens:
        return None, "Synthetic post-filters require `command | helper ...`."

    stage_specs: list[dict] = []
    stage_start = pipe_indexes[0] + 1
    for pipe_index in pipe_indexes[1:] + [len(tokens)]:
        stage_tokens = tokens[stage_start:pipe_index]
        if not stage_tokens:
            return None, "Synthetic post-filters require `command | helper ...`."

        spec, error = _parse_synthetic_postfilter_stage(stage_tokens)
        if error:
            return None, error
        if not spec:
            return None, None

        stage_specs.append(spec)
        stage_start = pipe_index + 1

    return {
        "base_command": shlex.join(base_tokens),
        "stages": stage_specs,
        "kind": stage_specs[0]["kind"],
    }, None


def _empty_autocomplete_context_entry() -> dict:
    return {
        "flags": [],
        "expects_value": [],
        "arg_hints": {},
        "sequence_arg_hints": {},
        "close_after": {},
        "subcommands": {},
        "argument_limit": None,
        "pipe_command": False,
        "pipe_insert_value": "",
        "pipe_label": "",
        "pipe_description": "",
        "examples": [],
    }


def _normalize_policy_list(items, *, lowercase: bool) -> list[str]:
    result = []
    seen = set()
    for item in items or []:
        value = str(item or "").strip()
        if not value:
            continue
        if lowercase:
            value = value.lower()
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_workspace_flags(items) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        flag = str(item.get("flag") or "").strip()
        mode = str(item.get("mode") or "").strip().lower()
        value = str(item.get("value") or "").strip().lower()
        if not flag or mode not in {"read", "write", "read_write"}:
            continue
        if value not in {"required", "separate", "attached", "separate_or_attached"}:
            value = "required"
        subcommands = tuple(
            sorted(
                str(subcommand).strip().lower()
                for subcommand in item.get("subcommands", []) or []
                if str(subcommand).strip()
            )
        )
        key = (flag, mode, value, str(item.get("kind") or "").strip().lower(), subcommands)
        if key in seen:
            continue
        seen.add(key)
        normalized: dict[str, object] = {"flag": flag, "mode": mode, "value": value}
        if subcommands:
            normalized["subcommands"] = list(subcommands)
        kind = str(item.get("kind") or "").strip().lower()
        if kind == "directory":
            normalized["kind"] = kind
        output_format = str(item.get("format") or "").strip().lower()
        if output_format:
            normalized["format"] = output_format
        max_file_mb = item.get("max_file_mb")
        if isinstance(max_file_mb, int | float) and max_file_mb > 0:
            normalized["max_file_mb"] = max_file_mb
        result.append(normalized)
    return result


def _normalize_allow_grouping_flags(raw_entry: dict) -> list[str]:
    result: list[str] = []
    seen = set()
    autocomplete = raw_entry.get("autocomplete")
    raw_flags = autocomplete.get("flags", []) if isinstance(autocomplete, dict) else []
    for raw_flag in raw_flags or []:
        if not isinstance(raw_flag, dict) or not raw_flag.get("allow_grouping") or raw_flag.get("takes_value"):
            continue
        value = str(raw_flag.get("value") or "").strip()
        if not re.fullmatch(r"-[A-Za-z]", value):
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_runtime_inject_flags(items) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        raw_flags = item.get("flags") or item.get("tokens") or []
        flags = [
            str(flag).strip()
            for flag in raw_flags
            if str(flag).strip()
        ] if isinstance(raw_flags, list) else []
        if not flags:
            continue
        position = str(item.get("position") or "prepend").strip().lower()
        if position == "prefix":
            position = "command_prefix"
        if position not in {"prepend", "append", "command_prefix"}:
            position = "prepend"
        unless_any = [
            str(token).strip()
            for token in item.get("unless_any", []) or []
            if str(token).strip()
        ]
        unless_any_regex = [
            str(pattern).strip()
            for pattern in item.get("unless_any_regex", []) or []
            if str(pattern).strip()
        ]
        normalized: dict[str, object] = {
            "flags": flags,
            "position": position,
            "unless_any": unless_any,
            "unless_any_regex": unless_any_regex,
        }
        notice = str(item.get("notice") or item.get("output_notice") or "").strip()
        if notice:
            normalized["notice"] = notice
        if item.get("requires_workspace"):
            normalized["requires_workspace"] = True
        result.append(normalized)
    return result


def _normalize_runtime_managed_workspace_directory(item) -> dict[str, object]:
    if not isinstance(item, dict):
        return {}
    flag = str(item.get("flag") or "").strip()
    directory = str(item.get("directory") or item.get("path") or "").strip().strip("/")
    if not flag or not directory:
        return {}
    subcommands = [
        str(subcommand).strip().lower()
        for subcommand in item.get("subcommands", []) or []
        if str(subcommand).strip()
    ]
    skip_if_any = [
        str(token).strip()
        for token in item.get("skip_if_any", []) or []
        if str(token).strip()
    ]
    result: dict[str, object] = {
        "flag": flag,
        "directory": directory,
        "subcommands": _dedupe_preserve_order(subcommands),
        "skip_if_any": _dedupe_preserve_order(skip_if_any),
        "reject_alternate": bool(item.get("reject_alternate", True)),
        "counts_as_workspace_write": bool(item.get("counts_as_workspace_write", True)),
    }
    reject_message = str(item.get("reject_message") or "").strip()
    if reject_message:
        result["reject_message"] = reject_message
    return result


def _normalize_runtime_environment(items) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name or not value:
            continue
        normalized: dict[str, object] = {"name": name, "value": value}
        managed_flag = str(item.get("managed_directory_flag") or "").strip()
        if managed_flag:
            normalized["managed_directory_flag"] = managed_flag
        result.append(normalized)
    return result


def _normalize_runtime_adaptations(raw_value) -> dict[str, object]:
    raw = raw_value if isinstance(raw_value, dict) else {}
    adaptations: dict[str, object] = {}
    inject_flags = _normalize_runtime_inject_flags(raw.get("inject_flags"))
    if inject_flags:
        adaptations["inject_flags"] = inject_flags
    managed_directory = _normalize_runtime_managed_workspace_directory(
        raw.get("managed_workspace_directory")
    )
    if managed_directory:
        adaptations["managed_workspace_directory"] = managed_directory
    environment = _normalize_runtime_environment(raw.get("environment"))
    if environment:
        adaptations["environment"] = environment
    return adaptations


def _normalize_registry_autocomplete(root: str, raw_spec) -> dict:
    if not isinstance(raw_spec, dict) or not raw_spec:
        return {}
    return _normalize_autocomplete_context({root: raw_spec}).get(root, {})


def _normalize_commands_registry_entry(raw_entry, *, pipe_helper: bool = False) -> dict | None:
    if not isinstance(raw_entry, dict):
        return None
    root = str(raw_entry.get("root") or "").strip().lower()
    if not root:
        return None

    entry = {
        "root": root,
        "autocomplete": _normalize_registry_autocomplete(root, raw_entry.get("autocomplete")),
    }
    description = str(raw_entry.get("description") or "").strip()
    if description:
        entry["description"] = description
    feature_required = raw_entry.get("feature_required") or raw_entry.get("requires_feature") or raw_entry.get("feature")
    if feature_required:
        if isinstance(feature_required, (list, tuple, set)):
            entry["feature_required"] = [
                str(value).strip().lower() for value in feature_required if str(value).strip()
            ]
        else:
            entry["feature_required"] = str(feature_required).strip().lower()
    if pipe_helper:
        return entry

    raw_policy_value = raw_entry.get("policy")
    raw_policy = raw_policy_value if isinstance(raw_policy_value, dict) else {}
    entry["category"] = str(raw_entry.get("category") or "").strip()
    entry["policy"] = {
        "allow": _normalize_policy_list(raw_policy.get("allow"), lowercase=True),
        "deny": _normalize_policy_list(raw_policy.get("deny"), lowercase=False),
    }
    entry["workspace_flags"] = _normalize_workspace_flags(raw_entry.get("workspace_flags"))
    entry["allow_grouping_flags"] = _normalize_allow_grouping_flags(raw_entry)
    entry["runtime_adaptations"] = _normalize_runtime_adaptations(raw_entry.get("runtime_adaptations"))
    return entry


def _load_commands_registry_file(path: str) -> dict:
    loaded = _load_yaml_mapping(path)
    commands = []
    pipe_helpers = []
    for raw_entry in loaded.get("commands", []) or []:
        entry = _normalize_commands_registry_entry(raw_entry)
        if entry:
            commands.append(entry)
    for raw_entry in loaded.get("pipe_helpers", []) or []:
        entry = _normalize_commands_registry_entry(raw_entry, pipe_helper=True)
        if entry:
            pipe_helpers.append(entry)
    return {
        "version": int(loaded.get("version") or 1),
        "commands": commands,
        "pipe_helpers": pipe_helpers,
    }


def _merge_command_registry_entries(base_entry: dict, overlay_entry: dict, *, pipe_helper: bool = False) -> dict:
    merged = deepcopy(base_entry)
    if not pipe_helper:
        if overlay_entry.get("category"):
            merged["category"] = overlay_entry["category"]
        policy = merged.setdefault("policy", {"allow": [], "deny": []})
        for allow in overlay_entry.get("policy", {}).get("allow", []) or []:
            if allow not in policy.setdefault("allow", []):
                policy["allow"].append(allow)
        for deny in overlay_entry.get("policy", {}).get("deny", []) or []:
            if deny not in policy.setdefault("deny", []):
                policy["deny"].append(deny)
        allow_grouping_flags = merged.setdefault("allow_grouping_flags", [])
        for flag in overlay_entry.get("allow_grouping_flags", []) or []:
            if flag not in allow_grouping_flags:
                allow_grouping_flags.append(flag)
        workspace_flags = merged.setdefault("workspace_flags", [])
        existing_workspace_flags = {
            (
                item.get("flag"),
                item.get("mode"),
                item.get("value"),
                item.get("kind"),
                tuple(item.get("subcommands", []) or []),
            )
            for item in workspace_flags if isinstance(item, dict)
        }
        for workspace_flag in overlay_entry.get("workspace_flags", []) or []:
            key = (
                workspace_flag.get("flag"),
                workspace_flag.get("mode"),
                workspace_flag.get("value"),
                workspace_flag.get("kind"),
                tuple(workspace_flag.get("subcommands", []) or []),
            )
            if key not in existing_workspace_flags:
                workspace_flags.append(deepcopy(workspace_flag))
                existing_workspace_flags.add(key)

        runtime_adaptations = merged.setdefault("runtime_adaptations", {})
        overlay_runtime = overlay_entry.get("runtime_adaptations") or {}
        if overlay_runtime.get("managed_workspace_directory"):
            runtime_adaptations["managed_workspace_directory"] = deepcopy(
                overlay_runtime["managed_workspace_directory"]
            )
        if overlay_runtime.get("inject_flags"):
            existing_inject = {
                (
                    tuple(item.get("flags", []) or []),
                    item.get("position"),
                    tuple(item.get("unless_any", []) or []),
                    tuple(item.get("unless_any_regex", []) or []),
                )
                for item in runtime_adaptations.setdefault("inject_flags", [])
                if isinstance(item, dict)
            }
            for inject in overlay_runtime.get("inject_flags", []) or []:
                key = (
                    tuple(inject.get("flags", []) or []),
                    inject.get("position"),
                    tuple(inject.get("unless_any", []) or []),
                    tuple(inject.get("unless_any_regex", []) or []),
                )
                if key not in existing_inject:
                    runtime_adaptations.setdefault("inject_flags", []).append(deepcopy(inject))
                    existing_inject.add(key)
        if overlay_runtime.get("environment"):
            existing_env = {
                (item.get("name"), item.get("value"), item.get("managed_directory_flag"))
                for item in runtime_adaptations.setdefault("environment", [])
                if isinstance(item, dict)
            }
            for env_item in overlay_runtime.get("environment", []) or []:
                key = (env_item.get("name"), env_item.get("value"), env_item.get("managed_directory_flag"))
                if key not in existing_env:
                    runtime_adaptations.setdefault("environment", []).append(deepcopy(env_item))
                    existing_env.add(key)

    base_autocomplete = merged.get("autocomplete") or _empty_autocomplete_context_entry()
    overlay_autocomplete = overlay_entry.get("autocomplete") or {}
    if overlay_autocomplete:
        merged["autocomplete"] = _merge_autocomplete_context(
            {merged["root"]: base_autocomplete},
            {merged["root"]: overlay_autocomplete},
        )[merged["root"]]
    elif "autocomplete" not in merged:
        merged["autocomplete"] = {}
    return merged


def _merge_commands_registry(base: dict, overlay: dict) -> dict:
    merged = {
        "version": int(base.get("version") or 1),
        "commands": deepcopy(base.get("commands") or []),
        "pipe_helpers": deepcopy(base.get("pipe_helpers") or []),
    }

    def merge_list(key: str, *, pipe_helper: bool = False) -> None:
        existing = {entry["root"]: index for index, entry in enumerate(merged[key])}
        for overlay_entry in overlay.get(key) or []:
            root = overlay_entry["root"]
            if root in existing:
                index = existing[root]
                merged[key][index] = _merge_command_registry_entries(
                    merged[key][index],
                    overlay_entry,
                    pipe_helper=pipe_helper,
                )
            else:
                existing[root] = len(merged[key])
                merged[key].append(deepcopy(overlay_entry))

    merge_list("commands")
    merge_list("pipe_helpers", pipe_helper=True)
    return merged


def load_commands_registry():
    """Read commands.yaml plus optional commands.local.yaml overlays."""
    base = _load_commands_registry_file(COMMANDS_REGISTRY_FILE)
    root, ext = os.path.splitext(COMMANDS_REGISTRY_FILE)
    local = _load_commands_registry_file(f"{root}.local{ext}")
    return _merge_commands_registry(base, local)


def load_builtin_autocomplete_registry():
    """Read app-owned built-in autocomplete grammar.

    This lives outside app/conf because built-in command grammar is not an
    operator-facing policy/config surface. It still uses the same registry
    shape and normalizer as external command autocomplete.
    """
    return _load_commands_registry_file(BUILTIN_AUTOCOMPLETE_FILE)


def load_command_policy():
    """Return allow/deny prefixes from commands.yaml."""
    registry = load_commands_registry()
    allow_prefixes: list[str] = []
    deny_prefixes: list[str] = []
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        raw_policy_value = entry.get("policy")
        policy = raw_policy_value if isinstance(raw_policy_value, dict) else {}
        allow_prefixes.extend(policy.get("allow") or [])
        deny_prefixes.extend(policy.get("deny") or [])

    allow_prefixes = _dedupe_preserve_order(allow_prefixes)
    deny_prefixes = _dedupe_preserve_order(deny_prefixes)
    return (allow_prefixes if allow_prefixes else None), deny_prefixes


def load_allow_grouping_flags() -> dict[str, set[str]]:
    """Return short flags that may be grouped for allow-prefix matching."""
    registry = load_commands_registry()
    grouped: dict[str, set[str]] = {}
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if not root:
            continue
        flags = {
            str(flag)
            for flag in entry.get("allow_grouping_flags", []) or []
            if re.fullmatch(r"-[A-Za-z]", str(flag))
        }
        if flags:
            grouped.setdefault(root, set()).update(flags)
    return grouped


def autocomplete_context_from_commands_registry(registry: dict, cfg=None) -> dict:
    """Return the browser autocomplete context from a loaded command registry."""
    context = {}
    for section in ("commands", "pipe_helpers"):
        for entry in registry.get(section, []) or []:
            root = str(entry.get("root") or "").strip().lower()
            autocomplete = entry.get("autocomplete")
            if (
                root
                and isinstance(autocomplete, dict)
                and autocomplete
                and _suggestion_enabled_for_features(entry, cfg)
            ):
                spec = _attach_workspace_autocomplete_flags(
                    deepcopy(autocomplete),
                    entry.get("workspace_flags") or [],
                )
                if entry.get("description"):
                    spec["description"] = entry["description"]
                if entry.get("feature_required"):
                    spec["feature_required"] = entry["feature_required"]
                context[root] = spec
    return _filter_autocomplete_context_by_features(context, app_config.CFG if cfg is None else cfg)


def _attach_workspace_autocomplete_flags(spec: dict, workspace_flags: list[dict[str, object]]) -> dict:
    """Mark value-taking autocomplete flags that should use live session files."""
    read_flags = [
        str(item.get("flag") or "")
        for item in workspace_flags
        if isinstance(item, dict)
        and item.get("mode") == "read"
        and item.get("kind") != "directory"
        and item.get("flag")
    ]
    if not read_flags:
        return spec

    def _relevant_flags(target_spec: dict, subcommand: str = "") -> list[str]:
        expects = {str(token) for token in target_spec.get("expects_value", []) or []}
        hints = {str(token) for token in (target_spec.get("arg_hints") or {})}
        relevant = []
        for item in workspace_flags:
            if not isinstance(item, dict) or item.get("mode") != "read" or item.get("kind") == "directory":
                continue
            flag = str(item.get("flag") or "")
            if not flag:
                continue
            raw_subcommands = item.get("subcommands")
            subcommands = (
                {str(value) for value in raw_subcommands}
                if isinstance(raw_subcommands, (list, tuple, set))
                else set()
            )
            if subcommand and subcommands and subcommand not in subcommands:
                continue
            if flag in expects or flag in hints:
                relevant.append(flag)
        return _dedupe_preserve_order(relevant)

    root_flags = _relevant_flags(spec)
    if root_flags:
        spec["workspace_file_flags"] = root_flags
    for subcommand, sub_spec in (spec.get("subcommands") or {}).items():
        if not isinstance(sub_spec, dict):
            continue
        sub_flags = _relevant_flags(sub_spec, str(subcommand))
        if sub_flags:
            sub_spec["workspace_file_flags"] = sub_flags
    return spec


def load_autocomplete_context_from_commands_registry(cfg=None) -> dict:
    """Read autocomplete metadata from commands.yaml and app-owned built-ins."""
    external = autocomplete_context_from_commands_registry(load_commands_registry(), cfg=cfg)
    builtins = autocomplete_context_from_commands_registry(load_builtin_autocomplete_registry(), cfg=cfg)
    return _merge_autocomplete_context(external, builtins)


def _feature_enabled(feature, cfg=None):
    normalized = str(feature or "").strip().lower()
    if not normalized:
        return True
    active_cfg = app_config.CFG if cfg is None else cfg
    if normalized == "workspace":
        return bool(active_cfg.get("workspace_enabled", False))
    return True


def _faq_entry_enabled(item, cfg=None):
    feature = item.get("feature") or item.get("requires_feature")
    if feature is None:
        return True
    if isinstance(feature, (list, tuple, set)):
        return all(_feature_enabled(value, cfg) for value in feature)
    return _feature_enabled(feature, cfg)


def load_faq(cfg=None):
    """Read faq.yaml and return a list of {question, answer} dicts.
    Returns an empty list if the file doesn't exist or contains no valid entries."""
    data = _load_yaml_list_with_local(FAQ_FILE)
    result = []
    for item in data:
        if not isinstance(item, dict) or not item.get("question") or not item.get("answer"):
            continue
        if not _faq_entry_enabled(item, cfg):
            continue
        entry = {"question": str(item["question"]), "answer": str(item["answer"])}
        if item.get("answer_html"):
            entry["answer_html"] = str(item["answer_html"])
        else:
            entry["answer_html"] = render_faq_markup(entry["answer"])
        result.append(entry)
    return result


def load_all_faq(app_name="darklab_shell", project_readme=None, cfg=None):
    """Return the built-in FAQ entries followed by any custom faq.yaml entries."""
    return [*(deepcopy(_builtin_faq(app_name, project_readme, cfg))), *load_faq(cfg)]


def _builtin_workflows():
    return [
        {
            "title": "DNS Troubleshooting",
            "description": "Diagnose why a domain isn't resolving or returns unexpected results.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "dig {{domain}} A", "note": "Does it resolve? Check the ANSWER section."},
                {"cmd": "dig {{domain}} NS", "note": "Which nameservers are authoritative?"},
                {"cmd": "dig @8.8.8.8 {{domain}} A", "note": "Does a public resolver see it differently?"},
                {"cmd": "dig {{domain}} +trace", "note": "Trace delegation step by step from the root."},
                {"cmd": "dig {{domain}} MX", "note": "Check mail exchanger records."},
            ],
        },
        {
            "title": "TLS / HTTPS Check",
            "description": "Verify a domain's certificate, chain, and TLS configuration.",
            "inputs": [
                {
                    "id": "host", "label": "Host", "type": "host", "required": True,
                    "placeholder": "example.com", "default": "ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "curl -Iv https://{{host}}", "note": "Check response headers and certificate details."},
                {"cmd": "openssl s_client -connect {{host}}:443",
                 "note": "Inspect the raw TLS handshake and certificate chain."},
                {"cmd": "testssl {{host}}", "note": "Run a full TLS audit including ciphers and known vulnerabilities."},
            ],
        },
        {
            "title": "HTTP Triage",
            "description": "Investigate what a web server is returning.",
            "inputs": [
                {
                    "id": "url", "label": "URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "curl -sIL {{url}}", "note": "Follow redirects and inspect the final response headers."},
                {"cmd": "curl -sv -o /dev/null {{url}}| head -60",
                 "note": "Verbose output with timing, TLS detail, and headers."},
                {"cmd": "wget -S --spider {{url}}", "note": "Spider check with full server response headers."},
            ],
        },
        {
            "title": "Quick Reachability Check",
            "description": "Confirm a host is up and identify which ports are open.",
            "inputs": [
                {
                    "id": "host", "label": "Host", "type": "host", "required": True,
                    "placeholder": "example.com", "default": "ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "ping -c 4 {{host}}", "note": "Is the host reachable? Check latency and packet loss."},
                {"cmd": "nc -zv {{host}} 443", "note": "Is HTTPS open and accepting connections?"},
                {"cmd": "nmap -F {{host}}", "note": "Fast scan of the 100 most common ports."},
            ],
        },
        {
            "title": "Email Server Check",
            "description": "Verify mail delivery configuration for a domain.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "dig {{domain}} MX", "note": "Which mail servers handle email for this domain?"},
                {"cmd": "dig {{domain}} TXT", "note": "Check SPF, DKIM policy, and other TXT records."},
                {"cmd": "dig _dmarc.{{domain}} TXT",
                 "note": "Check the DMARC policy published for the domain."},
                {"cmd": "dig @8.8.8.8 {{domain}} MX",
                 "note": (
                     "Confirm a public resolver sees the same MX records. If you want to test "
                     "SMTP ports with nc, target one of the MX hosts returned above rather than "
                     "the apex domain."
                 )},
            ],
        },
        {
            "title": "Domain OSINT / Passive Recon",
            "description": "Gather ownership, delegation, and passive subdomain context before active probing.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "whois {{domain}}", "note": "Review registration, registrar, and allocation context."},
                {"cmd": "dig {{domain}} NS", "note": "Identify authoritative nameservers for the domain."},
                {"cmd": "subfinder -d {{domain}} -silent", "note": "Find passively observed subdomains."},
                {"cmd": "dnsrecon -d {{domain}}", "note": "Enumerate common DNS records and transfer hints."},
            ],
        },
        {
            "title": "Subdomain Enumeration & Validation",
            "description": "Discover candidate subdomains, resolve them, and probe likely web services.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
                {
                    "id": "url", "label": "Probe URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "subfinder -d {{domain}} -silent", "note": "Collect passive subdomain candidates."},
                {
                    "cmd": (
                        "dnsx -d {{domain}} "
                        "-w /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt -resp"
                    ),
                    "note": "Resolve common subdomains and keep the DNS response context.",
                },
                {
                    "cmd": "pd-httpx -u {{url}} -title -status-code -tech-detect",
                    "note": "Probe HTTPS and collect status, title, and technology hints.",
                },
            ],
        },
        {
            "title": "Subdomain HTTP Triage",
            "description": (
                "Write discovered subdomains to Files, probe them for live HTTP services, "
                "then save a compact HTTP summary for review."
            ),
            "feature_required": "workspace",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                    "help": "The root domain to enumerate and triage.",
                },
            ],
            "steps": [
                {
                    "cmd": "subfinder -d {{domain}} -silent -o subdomains.txt",
                    "note": "Discover subdomains and save one hostname per line to Files.",
                },
                {
                    "cmd": "pd-httpx -l subdomains.txt -silent -o live-urls.txt",
                    "note": "Read the generated subdomain file and save live HTTP(S) URLs.",
                },
                {
                    "cmd": "pd-httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt",
                    "note": "Read live URLs and save status, title, and technology hints.",
                },
            ],
        },
        {
            "title": "Crawl And Scan",
            "description": (
                "Crawl a starting URL into Files, summarize discovered URLs, then run a focused "
                "high/critical nuclei pass against the crawl output."
            ),
            "feature_required": "workspace",
            "inputs": [
                {
                    "id": "url", "label": "URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                    "help": "The HTTP or HTTPS URL to crawl and scan.",
                },
            ],
            "steps": [
                {
                    "cmd": "katana -u {{url}} -d 1 -silent -o crawled-urls.txt",
                    "note": "Crawl one level from the seed URL and save discovered URLs.",
                },
                {
                    "cmd": "pd-httpx -l crawled-urls.txt -status-code -title -o crawled-http.txt",
                    "note": "Read crawled URLs and save HTTP status/title context.",
                },
                {
                    "cmd": "nuclei -l crawled-urls.txt -severity high,critical -o nuclei-findings.txt",
                    "note": "Run focused high/critical templates against the crawl output.",
                },
            ],
        },
        {
            "title": "Web Directory Discovery",
            "description": "Look for common web paths and follow up on interesting responses.",
            "inputs": [
                {
                    "id": "url", "label": "URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://tor-stats.darklab.sh",
                },
            ],
            "steps": [
                {
                    "cmd": (
                        "ffuf -u {{url}}/FUZZ "
                        "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt"
                    ),
                    "note": "Fuzz common paths and watch for non-baseline status codes or sizes.",
                },
                {
                    "cmd": (
                        "gobuster dir -u {{url}} "
                        "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt"
                    ),
                    "note": "Run a second directory check with a different scanner.",
                },
                {"cmd": "curl -sIL {{url}}/admin",
                 "note": "Inspect redirects and headers for a candidate path."},
            ],
        },
        {
            "title": "SSL / TLS Deep Dive",
            "description": "Inspect certificates, protocol support, cipher exposure, and known TLS weaknesses.",
            "inputs": [
                {
                    "id": "host", "label": "Host", "type": "host", "required": True,
                    "placeholder": "example.com", "default": "ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "sslscan {{host}}", "note": "Enumerate protocols, ciphers, and certificate metadata."},
                {"cmd": "sslyze --certinfo {{host}}", "note": "Validate certificate chain details."},
                {
                    "cmd": "openssl s_client -connect {{host}}:443 -servername {{host}}",
                    "note": "Inspect the raw handshake and served certificate chain.",
                },
                {"cmd": "testssl {{host}}", "note": "Run the broader TLS configuration audit."},
            ],
        },
        {
            "title": "CDN / Edge Behavior Check",
            "description": "Compare DNS, ownership, redirects, headers, and WAF/CDN edge signals.",
            "inputs": [
                {
                    "id": "domain", "label": "Domain", "type": "domain", "required": True,
                    "placeholder": "example.com", "default": "darklab.sh",
                },
                {
                    "id": "url", "label": "Web URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "dig {{domain}} A", "note": "Check the current address records."},
                {"cmd": "whois {{domain}}", "note": "Review ownership and provider hints."},
                {"cmd": "curl -sIL {{url}}", "note": "Inspect redirects, cache headers, and edge headers."},
                {"cmd": "wafw00f https://{{domain}}", "note": "Look for WAF or CDN fingerprints."},
            ],
        },
        {
            "title": "API Recon",
            "description": "Triage API-style endpoints with headers, methods, JSON negotiation, and path fuzzing.",
            "inputs": [
                {
                    "id": "url", "label": "Base URL", "type": "url", "required": True,
                    "placeholder": "https://example.com", "default": "https://ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "curl -sI {{url}}/api", "note": "Check whether the API path responds and how."},
                {
                    "cmd": "curl -sX OPTIONS -I {{url}}/api",
                    "note": "Inspect allowed methods and CORS-style headers.",
                },
                {
                    "cmd": "curl -sH Accept:application/json {{url}}/api",
                    "note": "Ask for JSON explicitly and inspect the response shape.",
                },
                {
                    "cmd": (
                        "ffuf -u {{url}}/FUZZ "
                        "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt"
                    ),
                    "note": "Fuzz common API-adjacent paths and versions.",
                },
            ],
        },
        {
            "title": "Network Path Analysis",
            "description": "Diagnose reachability, route shape, latency, and packet-loss symptoms.",
            "inputs": [
                {
                    "id": "host", "label": "Host", "type": "host", "required": True,
                    "placeholder": "example.com", "default": "ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "ping -c 10 {{host}}", "note": "Measure basic reachability, latency, and packet loss."},
                {"cmd": "mtr {{host}}", "note": "Summarize path loss and latency in report mode."},
                {"cmd": "traceroute {{host}}", "note": "Capture a static routed path to the target."},
                {"cmd": "tcptraceroute {{host}} 443", "note": "Trace the TCP path toward HTTPS specifically."},
            ],
        },
        {
            "title": "Fast Port Discovery to Service Fingerprint",
            "description": "Sweep for exposed ports quickly, then fingerprint and validate important services.",
            "inputs": [
                {
                    "id": "host", "label": "Host", "type": "host", "required": True,
                    "placeholder": "example.com", "default": "ip.darklab.sh",
                },
            ],
            "steps": [
                {"cmd": "rustscan -a {{host}} --range 1-1000", "note": "Quickly sweep the first thousand ports."},
                {"cmd": "naabu -host {{host}} -silent", "note": "Run a second fast TCP discovery pass."},
                {"cmd": "nmap -sV {{host}}", "note": "Fingerprint services once you know exposure is present."},
                {"cmd": "nc -zv {{host}} 80", "note": "Validate a specific expected port manually."},
            ],
        },
    ]


_WORKFLOW_INPUT_TYPES = {"domain", "host", "url", "port", "path"}
_WORKFLOW_INPUT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_WORKFLOW_TOKEN_RE = re.compile(r"{{\s*([a-z][a-z0-9_]*)\s*}}")


def _workflow_tokens(value: str) -> set[str]:
    return set(_WORKFLOW_TOKEN_RE.findall(value or ""))


def _render_workflow_text(value: str, inputs: dict[str, str]) -> str:
    return _WORKFLOW_TOKEN_RE.sub(lambda match: inputs.get(match.group(1), ""), value or "")


def _normalize_workflow_inputs(raw_inputs):
    if not isinstance(raw_inputs, list):
        return []
    result = []
    seen_ids = set()
    for item in raw_inputs:
        if not isinstance(item, dict):
            continue
        input_id = str(item.get("id") or "").strip().lower()
        input_type = str(item.get("type") or "").strip().lower()
        if (
            not input_id
            or input_id in seen_ids
            or not _WORKFLOW_INPUT_ID_RE.fullmatch(input_id)
            or input_type not in _WORKFLOW_INPUT_TYPES
        ):
            continue
        label = str(item.get("label") or input_id.replace("_", " ").title()).strip()
        placeholder = str(item.get("placeholder") or "").strip()
        default = str(item.get("default") or "").strip()
        help_text = str(item.get("help") or "").strip()
        normalized = {
            "id": input_id,
            "label": label or input_id.replace("_", " ").title(),
            "type": input_type,
            "required": bool(item.get("required", False)),
            "placeholder": placeholder,
            "default": default,
            "help": help_text,
        }
        result.append(normalized)
        seen_ids.add(input_id)
    return result


def _normalize_workflow_entry(entry):
    if not isinstance(entry, dict):
        return None
    title = str(entry.get("title") or "").strip()
    description = str(entry.get("description") or "").strip()
    steps = entry.get("steps") or []
    if not title or not isinstance(steps, list):
        return None
    inputs = _normalize_workflow_inputs(entry.get("inputs") or [])
    declared_ids = {item["id"] for item in inputs}
    clean_steps = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        cmd = str(step.get("cmd") or "").strip()
        note = str(step.get("note") or "").strip()
        if not cmd:
            continue
        tokens = _workflow_tokens(cmd) | _workflow_tokens(note)
        if tokens and not tokens.issubset(declared_ids):
            continue
        clean_steps.append({"cmd": cmd, "note": note})
    if not clean_steps:
        return None
    normalized = {
        "title": title,
        "description": description,
        "inputs": inputs,
        "steps": clean_steps,
    }
    feature_required = entry.get("feature_required") or entry.get("requires_feature") or entry.get("feature")
    if feature_required:
        if isinstance(feature_required, (list, tuple, set)):
            normalized["feature_required"] = [
                str(value).strip().lower() for value in feature_required if str(value).strip()
            ]
        else:
            normalized["feature_required"] = str(feature_required).strip().lower()
    return normalized


def normalize_workflow_entry(entry):
    """Return a normalized workflow entry or None when the payload is invalid."""
    return _normalize_workflow_entry(entry)


def _workflow_entry_enabled(entry, cfg=None):
    return _suggestion_enabled_for_features(entry, cfg)


def load_workflows():
    """Read workflows.yaml and return a list of workflow dicts."""
    data = _load_yaml_list_with_local(WORKFLOWS_FILE)
    if not data:
        return []
    result = []
    for entry in data:
        normalized = _normalize_workflow_entry(entry)
        if normalized:
            result.append(normalized)
    return result


def _workflow_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(title or "").strip().lower()).strip("-")
    return slug or "workflow"


def _workflow_with_catalog_metadata(entry, source, index):
    item = dict(entry)
    item["source"] = source
    item.setdefault("id", f"{source}:{_workflow_slug(item.get('title', 'workflow'))}-{index + 1}")
    return item


def load_all_workflows(cfg=None):
    """Return the built-in workflows followed by any custom workflows.yaml entries."""
    builtins = []
    for idx, entry in enumerate(_builtin_workflows()):
        normalized = _normalize_workflow_entry(entry)
        if normalized and _workflow_entry_enabled(normalized, cfg):
            builtins.append(_workflow_with_catalog_metadata(normalized, "builtin", idx))
    custom = [
        _workflow_with_catalog_metadata(workflow, "config", idx)
        for idx, workflow in enumerate(load_workflows())
        if _workflow_entry_enabled(workflow, cfg)
    ]
    return [*builtins, *custom]


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


def _hint_category_enabled(category, cfg=None):
    active_cfg = app_config.CFG if cfg is None else cfg
    normalized = str(category or "general").strip().lower()
    if normalized in ("", "general"):
        return True
    if normalized == "workspace":
        return bool(active_cfg.get("workspace_enabled", False))
    return True


def _load_scoped_hints(path, cfg=None):
    hints = []
    seen = set()
    for candidate in (path, _local_overlay_path(path)):
        if not os.path.exists(candidate):
            continue
        category = "general"
        with open(candidate) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    category = line[1:-1].strip().lower() or "general"
                    continue
                if _hint_category_enabled(category, cfg) and line not in seen:
                    hints.append(line)
                    seen.add(line)
    return hints


def load_welcome_hints(cfg=None):
    """Read app_hints.txt and return enabled app-usage hints."""
    return _load_scoped_hints(APP_HINTS_FILE, cfg)


def load_mobile_welcome_hints(cfg=None):
    """Read app_hints_mobile.txt and return enabled mobile-specific hints."""
    return _load_scoped_hints(APP_HINTS_MOBILE_FILE, cfg)


def _load_yaml_mapping(path):
    try:
        with open(path) as f:
            loaded = yaml.safe_load(f) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_context_suggestion(item):
    if isinstance(item, str):
        value = item.strip()
        return {"value": value, "description": ""} if value else None
    if not isinstance(item, dict):
        return None
    raw_value = item.get("value")
    if raw_value is None and item.get("placeholder") is not None:
        raw_value = item.get("placeholder")
    value = str(raw_value or "").strip()
    if not value:
        return None
    description = str(item.get("description", "")).strip()
    result: dict[str, object] = {"value": value, "description": description}
    # Insert text is whitespace-significant (e.g. "set " to leave the caret
    # past a trailing space), so only strip when the key is absent.
    raw_insert = item.get("insert")
    if raw_insert is not None:
        result["insertValue"] = str(raw_insert)
    raw_label = item.get("label")
    if raw_label is not None:
        label = str(raw_label).strip()
        if label:
            result["label"] = label
    if "hintOnly" in item:
        result["hintOnly"] = bool(item.get("hintOnly"))
    value_type = str(item.get("value_type") or item.get("value_kind") or item.get("type") or "").strip().lower()
    if value_type:
        result["value_type"] = value_type
    raw_wordlist_category = item.get("wordlist_category")
    if raw_wordlist_category:
        if isinstance(raw_wordlist_category, (list, tuple, set)):
            categories = [
                str(value).strip().lower()
                for value in raw_wordlist_category
                if str(value).strip()
            ]
            if categories:
                result["wordlist_category"] = categories
        else:
            category = str(raw_wordlist_category).strip().lower()
            if category:
                result["wordlist_category"] = category
    feature_required = item.get("feature_required") or item.get("requires_feature") or item.get("feature")
    if feature_required:
        if isinstance(feature_required, (list, tuple, set)):
            result["feature_required"] = [str(value).strip().lower() for value in feature_required if str(value).strip()]
        else:
            result["feature_required"] = str(feature_required).strip().lower()
    return result


def _suggestion_enabled_for_features(item, cfg=None) -> bool:
    if not isinstance(item, dict):
        return True
    feature_required = item.get("feature_required") or item.get("requires_feature") or item.get("feature")
    if not feature_required:
        return True
    if isinstance(feature_required, (list, tuple, set)):
        return all(_feature_enabled(value, cfg) for value in feature_required)
    return _feature_enabled(feature_required, cfg)


def _filter_autocomplete_context_by_features(context: dict, cfg=None) -> dict:
    filtered: dict[str, dict] = {}
    for root, raw_spec in (context or {}).items():
        if not isinstance(raw_spec, dict):
            continue
        spec = deepcopy(raw_spec)
        raw_flags = [item for item in spec.get("flags", []) or [] if isinstance(item, dict)]
        enabled_flags = [item for item in raw_flags if _suggestion_enabled_for_features(item, cfg)]
        disabled_flag_tokens = {
            str(item.get("value") or "")
            for item in raw_flags
            if item not in enabled_flags and item.get("value")
        }
        spec["flags"] = enabled_flags
        spec["expects_value"] = [
            token for token in spec.get("expects_value", []) or []
            if str(token) not in disabled_flag_tokens
        ]
        spec["arg_hints"] = {
            trigger: [
                item for item in hints or []
                if _suggestion_enabled_for_features(item, cfg)
            ]
            for trigger, hints in (spec.get("arg_hints") or {}).items()
            if str(trigger) not in disabled_flag_tokens
        }
        spec["examples"] = [
            item for item in spec.get("examples", []) or []
            if _suggestion_enabled_for_features(item, cfg)
        ]
        spec["sequence_arg_hints"] = {
            trigger: [
                item for item in hints or []
                if _suggestion_enabled_for_features(item, cfg)
            ]
            for trigger, hints in (spec.get("sequence_arg_hints") or {}).items()
        }
        filtered_subcommands = {}
        for name, raw_sub_spec in (spec.get("subcommands") or {}).items():
            if not isinstance(raw_sub_spec, dict):
                continue
            sub_spec = deepcopy(raw_sub_spec)
            sub_raw_flags = [item for item in sub_spec.get("flags", []) or [] if isinstance(item, dict)]
            sub_enabled_flags = [item for item in sub_raw_flags if _suggestion_enabled_for_features(item, cfg)]
            sub_disabled_flag_tokens = {
                str(item.get("value") or "")
                for item in sub_raw_flags
                if item not in sub_enabled_flags and item.get("value")
            }
            sub_spec["flags"] = sub_enabled_flags
            sub_spec["expects_value"] = [
                token for token in sub_spec.get("expects_value", []) or []
                if str(token) not in sub_disabled_flag_tokens
            ]
            sub_spec["arg_hints"] = {
                trigger: [
                    item for item in hints or []
                    if _suggestion_enabled_for_features(item, cfg)
                ]
                for trigger, hints in (sub_spec.get("arg_hints") or {}).items()
                if str(trigger) not in sub_disabled_flag_tokens
            }
            sub_spec["examples"] = [
                item for item in sub_spec.get("examples", []) or []
                if _suggestion_enabled_for_features(item, cfg)
            ]
            sub_spec["sequence_arg_hints"] = {
                trigger: [
                    item for item in hints or []
                    if _suggestion_enabled_for_features(item, cfg)
                ]
                for trigger, hints in (sub_spec.get("sequence_arg_hints") or {}).items()
            }
            filtered_subcommands[name] = sub_spec
        spec["subcommands"] = filtered_subcommands
        filtered[root] = spec
    return filtered


def _append_unique_context_token(bucket, seen, raw_token):
    token = str(raw_token or "").strip()
    if not token:
        return
    key = token
    if key in seen:
        return
    seen.add(key)
    bucket.append(token)


def _append_unique_context_suggestions(bucket, seen, raw_items):
    for raw_item in raw_items or []:
        hint = _normalize_context_suggestion(raw_item)
        if not hint:
            continue
        key = str(hint["value"]).lower()
        if key in seen:
            continue
        seen.add(key)
        bucket.append(hint)


def _normalize_single_autocomplete_spec(raw_spec: dict, *, include_pipe: bool = True) -> dict:
    flags = []
    seen_flags = set()
    for raw_flag in raw_spec.get("flags", []) or []:
        flag = _normalize_context_suggestion(raw_flag)
        if not flag:
            continue
        key = str(flag["value"]).lower()
        if key in seen_flags:
            continue
        seen_flags.add(key)
        flags.append(flag)

    expects_value = []
    seen_value_flags = set()

    arg_hints = {}

    def _hint_bucket(trigger):
        bucket = arg_hints.setdefault(trigger, [])
        seen = {str(item.get("value", "")).lower() for item in bucket if isinstance(item, dict)}
        return bucket, seen

    for raw_flag in raw_spec.get("flags", []) or []:
        if not isinstance(raw_flag, dict):
            continue
        token = str(raw_flag.get("value") or "").strip()
        if not token:
            continue
        flag_value_type = str(
            raw_flag.get("value_type")
            or raw_flag.get("value_kind")
            or raw_flag.get("type")
            or ""
        ).strip().lower()
        if raw_flag.get("takes_value"):
            _append_unique_context_token(expects_value, seen_value_flags, token)
        if raw_flag.get("closes"):
            arg_hints.setdefault(token, [])
        hint_sources = []
        raw_value_hint = raw_flag.get("value_hint")
        if raw_value_hint is not None:
            hint_sources.extend(raw_value_hint if isinstance(raw_value_hint, list) else [raw_value_hint])
        if raw_flag.get("suggest") is not None:
            hint_sources.extend(raw_flag.get("suggest") or [])
        if flag_value_type and not hint_sources:
            hint_sources.append({
                "placeholder": f"<{flag_value_type}>",
                "description": str(raw_flag.get("description") or "").strip(),
                "value_type": flag_value_type,
            })
        if hint_sources:
            bucket, seen = _hint_bucket(token)
            if flag_value_type:
                enriched_sources = []
                for source in hint_sources:
                    if isinstance(source, dict):
                        enriched = dict(source)
                        enriched.setdefault("value_type", flag_value_type)
                        if raw_flag.get("wordlist_category") and "wordlist_category" not in enriched:
                            enriched["wordlist_category"] = raw_flag.get("wordlist_category")
                        enriched_sources.append(enriched)
                    else:
                        enriched_sources.append(source)
                hint_sources = enriched_sources
            _append_unique_context_suggestions(bucket, seen, hint_sources)

    positional_bucket, positional_seen = _hint_bucket("__positional__")
    _append_unique_context_suggestions(
        positional_bucket,
        positional_seen,
        raw_spec.get("arguments") or [],
    )

    raw_subcommands = raw_spec.get("subcommands")
    subcommand_specs = {}
    if isinstance(raw_subcommands, dict):
        for raw_name, raw_sub_spec in raw_subcommands.items():
            name = str(raw_name or "").strip().lower()
            if not name or not isinstance(raw_sub_spec, dict):
                continue
            description = str(raw_sub_spec.get("description") or "").strip()
            nested = _normalize_single_autocomplete_spec(raw_sub_spec, include_pipe=False)
            if description:
                nested["description"] = description
            subcommand_specs[name] = nested
            display = {
                "value": name,
                "description": description,
                "insert": raw_sub_spec.get("insert", f"{name} "),
            }
            normalized_sub = _normalize_context_suggestion(display)
            if normalized_sub:
                key = str(normalized_sub["value"]).lower()
                if key not in positional_seen:
                    positional_seen.add(key)
                    positional_bucket.append(normalized_sub)
    else:
        for raw_sub in raw_subcommands or []:
            if not isinstance(raw_sub, dict):
                continue
            token = str(raw_sub.get("value") or "").strip()
            if not token:
                continue
            if raw_sub.get("takes_value"):
                _append_unique_context_token(expects_value, seen_value_flags, token)
            if raw_sub.get("closes"):
                arg_hints.setdefault(token, [])

            hint_sources = []
            raw_value_hint = raw_sub.get("value_hint")
            if raw_value_hint is not None:
                hint_sources.extend(raw_value_hint if isinstance(raw_value_hint, list) else [raw_value_hint])
            if raw_sub.get("suggest") is not None:
                hint_sources.extend(raw_sub.get("suggest") or [])
            if hint_sources:
                bucket, seen = _hint_bucket(token)
                _append_unique_context_suggestions(bucket, seen, hint_sources)

            subcommand_display = {
                "value": token,
                "description": str(raw_sub.get("description", "")).strip(),
            }
            if raw_sub.get("takes_value"):
                placeholder = None
                if isinstance(raw_value_hint, dict):
                    placeholder = raw_value_hint.get("placeholder") or raw_value_hint.get("value")
                elif isinstance(raw_value_hint, list) and raw_value_hint:
                    first_hint = raw_value_hint[0]
                    if isinstance(first_hint, dict):
                        placeholder = first_hint.get("placeholder") or first_hint.get("value")
                if placeholder:
                    subcommand_display["value"] = f"{token} {str(placeholder).strip()}"
                raw_insert = raw_sub.get("insert")
                subcommand_display["insert"] = str(raw_insert) if raw_insert is not None else f"{token} "
            else:
                raw_insert = raw_sub.get("insert")
                if raw_insert is not None:
                    subcommand_display["insert"] = str(raw_insert)
            normalized_sub = _normalize_context_suggestion(subcommand_display)
            if normalized_sub and not raw_sub.get("hidden"):
                key = str(normalized_sub["value"]).lower()
                if key not in positional_seen:
                    positional_seen.add(key)
                    positional_bucket.append(normalized_sub)

    raw_argument_limit = raw_spec.get("argument_limit")
    argument_limit = raw_argument_limit if isinstance(raw_argument_limit, int) and raw_argument_limit > 0 else None

    sequence_arg_hints = {}
    for trigger, hints in (raw_spec.get("sequence_arg_hints") or {}).items():
        bucket = []
        seen = set()
        _append_unique_context_suggestions(bucket, seen, hints)
        sequence_arg_hints[str(trigger or "").strip().lower()] = bucket

    close_after = {}
    raw_close_after = raw_spec.get("close_after")
    if isinstance(raw_close_after, dict):
        for raw_token, raw_limit in raw_close_after.items():
            token = str(raw_token or "").strip().lower()
            if not token:
                continue
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                continue
            if limit >= 0:
                close_after[token] = limit

    raw_pipe_spec = raw_spec.get("pipe")
    pipe_spec: dict[str, object] = raw_pipe_spec if include_pipe and isinstance(raw_pipe_spec, dict) else {}
    pipe_command = bool(pipe_spec.get("enabled"))
    pipe_insert_value = str(pipe_spec.get("insert") or "").strip()
    pipe_label = str(pipe_spec.get("label") or "").strip() or pipe_insert_value
    pipe_description = str(pipe_spec.get("description") or "").strip()

    examples = []
    seen_examples = set()
    for raw_ex in raw_spec.get("examples", []) or []:
        ex = _normalize_context_suggestion(raw_ex)
        if not ex:
            continue
        key = str(ex["value"]).lower()
        if key in seen_examples:
            continue
        seen_examples.add(key)
        examples.append(ex)

    return {
        "flags": flags,
        "expects_value": expects_value,
        "arg_hints": arg_hints,
        "sequence_arg_hints": sequence_arg_hints,
        "close_after": close_after,
        "subcommands": subcommand_specs,
        "argument_limit": argument_limit,
        "pipe_command": pipe_command,
        "pipe_insert_value": pipe_insert_value,
        "pipe_label": pipe_label,
        "pipe_description": pipe_description,
        "examples": examples,
    }


def _normalize_autocomplete_context(data):
    if not isinstance(data, dict):
        return {}
    normalized = {}
    for raw_root, raw_spec in data.items():
        root = str(raw_root or "").strip().lower()
        if not root or not isinstance(raw_spec, dict):
            continue
        normalized[root] = _normalize_single_autocomplete_spec(raw_spec)
    return normalized


def _merge_autocomplete_context(base, overlay):
    merged = deepcopy(base if isinstance(base, dict) else {})
    for root, spec in (overlay or {}).items():
        if not isinstance(spec, dict):
            continue
        current = merged.setdefault(root, {
            "flags": [],
            "expects_value": [],
            "arg_hints": {},
            "sequence_arg_hints": {},
            "close_after": {},
            "subcommands": {},
            "argument_limit": None,
            "pipe_command": False,
            "pipe_insert_value": "",
            "pipe_label": "",
            "pipe_description": "",
            "examples": [],
        })

        if isinstance(spec.get("argument_limit"), int) and spec["argument_limit"] > 0:
            current["argument_limit"] = spec["argument_limit"]

        if spec.get("description"):
            current["description"] = spec["description"]
        if spec.get("feature_required"):
            current["feature_required"] = spec["feature_required"]

        if spec.get("pipe_command"):
            current["pipe_command"] = True
        if spec.get("pipe_insert_value"):
            current["pipe_insert_value"] = spec["pipe_insert_value"]
        if spec.get("pipe_label"):
            current["pipe_label"] = spec["pipe_label"]
        if spec.get("pipe_description"):
            current["pipe_description"] = spec["pipe_description"]
        if not current.get("pipe_label") and current.get("pipe_insert_value"):
            current["pipe_label"] = current["pipe_insert_value"]

        seen_flags = {item["value"].lower() for item in current.get("flags", []) if isinstance(item, dict)}
        for flag in spec.get("flags", []) or []:
            key = str(flag["value"]).lower()
            if key in seen_flags:
                continue
            seen_flags.add(key)
            current.setdefault("flags", []).append(flag)

        seen_value_flags = {str(item) for item in current.get("expects_value", [])}
        for token in spec.get("expects_value", []) or []:
            key = str(token)
            if key in seen_value_flags:
                continue
            seen_value_flags.add(key)
            current.setdefault("expects_value", []).append(token)

        for trigger, hints in (spec.get("arg_hints", {}) or {}).items():
            bucket = current.setdefault("arg_hints", {}).setdefault(trigger, [])
            seen_hints = {item["value"].lower() for item in bucket if isinstance(item, dict)}
            for hint in hints or []:
                key = hint["value"].lower()
                if key in seen_hints:
                    continue
                seen_hints.add(key)
                bucket.append(hint)

        for trigger, hints in (spec.get("sequence_arg_hints", {}) or {}).items():
            bucket = current.setdefault("sequence_arg_hints", {}).setdefault(trigger, [])
            seen_hints = {item["value"].lower() for item in bucket if isinstance(item, dict)}
            for hint in hints or []:
                key = hint["value"].lower()
                if key in seen_hints:
                    continue
                seen_hints.add(key)
                bucket.append(hint)

        current.setdefault("close_after", {}).update(spec.get("close_after") or {})

        current_subcommands = current.setdefault("subcommands", {})
        for name, sub_spec in (spec.get("subcommands") or {}).items():
            if not isinstance(sub_spec, dict):
                continue
            sub_name = str(name or "").strip().lower()
            if not sub_name:
                continue
            if sub_name not in current_subcommands:
                current_subcommands[sub_name] = deepcopy(sub_spec)
                continue
            merged_sub = _merge_autocomplete_context(
                {sub_name: current_subcommands[sub_name]},
                {sub_name: sub_spec},
            )
            current_subcommands[sub_name] = merged_sub[sub_name]

        seen_examples = {item["value"].lower() for item in current.get("examples", []) if isinstance(item, dict)}
        for ex in spec.get("examples", []) or []:
            key = str(ex["value"]).lower()
            if key in seen_examples:
                continue
            seen_examples.add(key)
            current.setdefault("examples", []).append(ex)
    return merged


def _spread_sensitive_smoke_commands(commands: list[str]) -> list[str]:
    """De-clump bursty network lookups without changing source ownership/order.

    The smoke corpus should still be *collected* in source order from
    registry examples and workflow steps, but some roots are more likely to
    hit transient upstream throttling when run back-to-back. Spread those roots
    apart opportunistically while preserving relative order as much as possible.
    """
    sensitive_roots = {"dig", "whois"}
    scheduled: list[str] = []
    deferred: list[str] = []

    def _root(command: str) -> str:
        return split_command_argv(command)[0].lower() if command.strip() else ""

    def _last_sensitive_root() -> str:
        for command in reversed(scheduled):
            root = _root(command)
            if root in sensitive_roots:
                return root
        return ""

    def _flush_deferred(*, allow_sensitive_after_sensitive: bool = False) -> None:
        if not deferred:
            return
        last_root = _root(scheduled[-1]) if scheduled else ""
        last_sensitive_root = _last_sensitive_root()
        fallback_index = None
        for index, command in enumerate(deferred):
            root = _root(command)
            if root == last_root:
                continue
            if (
                not allow_sensitive_after_sensitive
                and last_root in sensitive_roots
                and root in sensitive_roots
            ):
                continue
            if root != last_sensitive_root:
                scheduled.append(deferred.pop(index))
                return
            if fallback_index is None:
                fallback_index = index
        if fallback_index is not None:
            scheduled.append(deferred.pop(fallback_index))

    for command in commands:
        root = _root(command)
        last_root = _root(scheduled[-1]) if scheduled else ""
        if root in sensitive_roots and last_root in sensitive_roots:
            deferred.append(command)
            continue
        scheduled.append(command)
        if root not in sensitive_roots:
            _flush_deferred()

    while deferred:
        before = len(deferred)
        _flush_deferred(allow_sensitive_after_sensitive=True)
        if len(deferred) == before:
            scheduled.append(deferred.pop(0))

    return scheduled


def load_container_smoke_test_commands():
    """Return the user-facing smoke-test corpus from registry examples and workflows."""
    commands = []
    seen = set()

    def _example_sources(spec: dict):
        yield from spec.get("examples") or []
        for sub_spec in (spec.get("subcommands") or {}).values():
            if isinstance(sub_spec, dict):
                yield from _example_sources(sub_spec)

    # The generic smoke corpus has no per-command file setup. Workspace-only
    # examples are covered by dedicated workspace smoke fixtures instead.
    for spec in load_autocomplete_context_from_commands_registry({"workspace_enabled": False}).values():
        if not isinstance(spec, dict):
            continue
        for example in _example_sources(spec):
            if not isinstance(example, dict):
                continue
            if not _suggestion_enabled_for_features(example, {"workspace_enabled": False}):
                continue
            command = str(example.get("value") or "").strip()
            if not command or command in seen:
                continue
            seen.add(command)
            commands.append(command)

    for workflow in load_all_workflows({"workspace_enabled": False}):
        if not isinstance(workflow, dict):
            continue
        workflow_inputs = {
            item["id"]: str(item.get("default") or "").strip()
            for item in workflow.get("inputs") or []
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        for step in workflow.get("steps") or []:
            if not isinstance(step, dict):
                continue
            command = str(step.get("cmd") or "").strip()
            tokens = _workflow_tokens(command)
            if tokens:
                if not tokens.issubset({key for key, value in workflow_inputs.items() if value}):
                    continue
                command = _render_workflow_text(command, workflow_inputs).strip()
            if not command or command in seen:
                continue
            seen.add(command)
            commands.append(command)

    return _spread_sensitive_smoke_commands(commands)


def split_command_argv(command: str) -> list[str]:
    """Split a shell-like command string into argv tokens for simple root-command inspection."""
    # Validation works on argv-style tokens only. The app never invokes a shell
    # parser here because that would blur the security model.
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


def _nmap_scan_mode_from_token(token: str) -> str | None:
    for flag in NMAP_SCAN_MODE_FLAGS:
        if token == flag or token.startswith(f"{flag}="):
            return flag
        if token.startswith(flag) and token.startswith("-s") and len(token) > len(flag):
            return flag
    return None


def _nmap_raw_scan_restriction_reason(command: str) -> str:
    tokens = split_command_argv(command)
    if not tokens or tokens[0].lower() != "nmap":
        return ""
    if "--privileged" in tokens:
        return "nmap raw-socket mode is not supported; use TCP connect scans with -sT."
    for token in tokens[1:]:
        if _nmap_scan_mode_from_token(token) in NMAP_DENIED_RAW_FLAGS:
            return "nmap SYN scans (-sS) are not supported; use TCP connect scans with -sT."
    return ""


def _runtime_injection_blocked(tokens: list[str], inject: dict[str, object]) -> bool:
    raw_unless_any = inject.get("unless_any")
    unless_any = [
        str(item) for item in raw_unless_any
        if str(item)
    ] if isinstance(raw_unless_any, list) else []
    for blocker in unless_any:
        if any(
            token == blocker or (blocker.startswith("--") and token.startswith(f"{blocker}="))
            for token in tokens[1:]
        ):
            return True
    raw_regexes = inject.get("unless_any_regex")
    regexes = raw_regexes if isinstance(raw_regexes, list) else []
    for raw_pattern in regexes:
        pattern = str(raw_pattern)
        try:
            if any(re.search(pattern, token) for token in tokens[1:]):
                return True
        except re.error:
            continue
    return False


def _runtime_injection_token(
    token: str,
    *,
    session_id: str = "",
    cfg: dict | None = None,
) -> str:
    if "{session_workspace}" not in token:
        return token
    if not session_id:
        return ""
    try:
        workspace_dir = ensure_session_workspace(session_id, cfg)
    except (InvalidWorkspacePath, WorkspaceDisabled, OSError):
        return ""
    return token.replace("{session_workspace}", str(workspace_dir))


def _runtime_injection_flags(
    inject: dict[str, object],
    *,
    session_id: str = "",
    cfg: dict | None = None,
) -> list[str]:
    raw_flags = inject.get("flags")
    if not isinstance(raw_flags, list):
        return []
    flags = [
        _runtime_injection_token(str(flag), session_id=session_id, cfg=cfg).strip()
        for flag in raw_flags
    ]
    return [flag for flag in flags if flag]


def _apply_runtime_inject_flags(
    command: str,
    *,
    session_id: str = "",
    cfg: dict | None = None,
) -> tuple[str, str | None]:
    tokens = split_command_argv(command)
    if not tokens:
        return command.strip(), None
    adaptations = _runtime_adaptations_by_root().get(tokens[0].lower(), {})
    inject_flags = adaptations.get("inject_flags") if isinstance(adaptations, dict) else []
    if not isinstance(inject_flags, list) or not inject_flags:
        return command.strip(), None

    rewritten = list(tokens)
    notices: list[str] = []
    changed = False
    for inject in inject_flags:
        if not isinstance(inject, dict):
            continue
        if inject.get("requires_workspace") and not (session_id and (cfg or app_config.CFG).get("workspace_enabled")):
            continue
        flags = _runtime_injection_flags(inject, session_id=session_id, cfg=cfg)
        if not flags or _runtime_injection_blocked(rewritten, inject):
            continue
        position = str(inject.get("position") or "prepend")
        if position == "command_prefix":
            rewritten = flags + rewritten
        elif position == "append":
            rewritten.extend(flags)
        else:
            rewritten[1:1] = flags
        notice = str(inject.get("notice") or "").strip()
        if notice:
            notices.append(notice)
        changed = True
    return (shlex.join(rewritten), notices[0] if notices else None) if changed else (command.strip(), None)


def resolve_runtime_command(command_name: str) -> str | None:
    """Return the absolute path to command_name if installed on this instance."""
    return shutil.which(command_name)


def runtime_missing_command_name(command: str) -> str | None:
    """Return the missing root command name for a command string, or None if installed/empty."""
    tokens = split_command_argv(command)
    root = tokens[0].strip().lower() if tokens else None
    if root == "env":
        for token in tokens[1:]:
            if "=" in token and not token.startswith("-"):
                continue
            root = token.strip().lower()
            break
        else:
            root = None
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


def _tokens_start_with(command_tokens: list[str], prefix_tokens: list[str]) -> bool:
    if len(command_tokens) < len(prefix_tokens):
        return False
    return all(cmd.lower() == prefix.lower() for cmd, prefix in zip(command_tokens, prefix_tokens))


def _flag_matches_token(flag: str, token: str) -> bool:
    if not flag:
        return False
    if flag.startswith("--"):
        return token == flag
    if len(flag) == 2 and flag[0] == '-' and flag[1].isalpha():
        if token == flag:
            return True
        # Combined short-flag group matching: `-ve` matches `-e`, `-sOL` matches `-O`.
        # Only applies when the token looks like a POSIX short-flag bundle:
        # single dash, all-alphabetic, at most 4 chars (e.g. -ef, -sVT).
        # Tokens of 5+ chars (e.g. -host, -timeout, -list) are long-form single-dash
        # options used by many non-POSIX tools and must match exactly.
        if (token.startswith('-') and not token.startswith('--')
                and len(token) <= 4 and token[1:].isalpha()):
            return flag[1] in token[1:]
        return False
    return token == flag


def _grouped_short_flag_members(token: str, allow_grouping_flags: set[str]) -> set[str] | None:
    if not token.startswith("-") or token.startswith("--") or len(token) < 2:
        return None
    if not token[1:].isalpha():
        return None
    members = {f"-{char}" for char in token[1:]}
    if not members or not members.issubset(allow_grouping_flags):
        return None
    return members


def _allowed_prefix_matches_with_grouping(
    command_tokens: list[str],
    prefix_tokens: list[str],
    allow_grouping_flags: set[str],
) -> bool:
    if not command_tokens or not prefix_tokens or not allow_grouping_flags:
        return False
    if command_tokens[0].lower() != prefix_tokens[0].lower():
        return False

    required_grouped_flags = set()
    for token in prefix_tokens[1:]:
        if token in allow_grouping_flags:
            required_grouped_flags.add(token)
            continue
        # Keep non-groupable prefixes on the original exact-prefix path.
        return False
    if not required_grouped_flags:
        return False

    command_grouped_flags = set()
    for token in command_tokens[1:]:
        members = _grouped_short_flag_members(token, allow_grouping_flags)
        if members is None:
            break
        command_grouped_flags.update(members)

    return required_grouped_flags.issubset(command_grouped_flags)


def _is_allowed_by_policy(command_tokens: list[str], allowed: list[str], allow_grouping: dict[str, set[str]]) -> bool:
    cmd_lower = shlex.join(command_tokens).lower()
    for prefix in allowed:
        if cmd_lower == prefix or cmd_lower.startswith(prefix + " "):
            return True
        prefix_tokens = split_command_argv(prefix)
        root = prefix_tokens[0].lower() if prefix_tokens else ""
        if _allowed_prefix_matches_with_grouping(command_tokens, prefix_tokens, allow_grouping.get(root, set())):
            return True
    return False


def _workspace_flag_specs_by_root() -> dict[str, list[dict[str, object]]]:
    registry = load_commands_registry()
    specs: dict[str, list[dict[str, object]]] = {}
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if root:
            specs[root] = [
                item for item in entry.get("workspace_flags", []) or []
                if isinstance(item, dict)
            ]
    return specs


def _runtime_adaptations_by_root() -> dict[str, dict[str, object]]:
    registry = load_commands_registry()
    adaptations: dict[str, dict[str, object]] = {}
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        runtime_adaptations = entry.get("runtime_adaptations")
        if root and isinstance(runtime_adaptations, dict) and runtime_adaptations:
            adaptations[root] = runtime_adaptations
    return adaptations


def _workspace_flag_applies_to_command(spec: dict[str, object], tokens: list[str]) -> bool:
    subcommands = spec.get("subcommands")
    if not subcommands:
        return True
    if not isinstance(subcommands, list) or len(tokens) < 2:
        return False
    command_sub = tokens[1].strip().lower()
    return command_sub in {str(item).strip().lower() for item in subcommands}


def _managed_workspace_directory_applies(spec: dict[str, object], tokens: list[str]) -> bool:
    if not spec or not tokens:
        return False
    raw_subcommands = spec.get("subcommands")
    subcommands = raw_subcommands if isinstance(raw_subcommands, list) else []
    if subcommands:
        if len(tokens) < 2:
            return False
        command_sub = tokens[1].strip().lower()
        if command_sub not in {str(item).strip().lower() for item in subcommands}:
            return False
    raw_skip_if_any = spec.get("skip_if_any")
    skip_if_any = {
        str(item) for item in raw_skip_if_any
        if str(item)
    } if isinstance(raw_skip_if_any, list) else set()
    if skip_if_any and any(token in skip_if_any for token in tokens[1:]):
        return False
    return True


def _managed_workspace_directory_for_root(root: str) -> dict[str, object]:
    adaptations = _runtime_adaptations_by_root().get(root.lower(), {})
    managed = adaptations.get("managed_workspace_directory") if isinstance(adaptations, dict) else {}
    return managed if isinstance(managed, dict) else {}


def _workspace_flag_matches_token(token: str, spec: dict[str, object]) -> bool:
    flag = str(spec.get("flag") or "")
    if not flag:
        return False
    if token == flag:
        return True
    value_kind = str(spec.get("value") or "required")
    if value_kind not in {"attached", "separate_or_attached"}:
        return False
    if flag.startswith("--"):
        return token.startswith(f"{flag}=")
    return token.startswith(flag) and token != flag


def _workspace_flag_value(tokens: list[str], index: int, spec: dict[str, object]) -> tuple[str | None, int | None, str | None]:
    flag = str(spec.get("flag") or "")
    value_kind = str(spec.get("value") or "required")
    token = tokens[index]
    if token == flag:
        label = "session directory name" if str(spec.get("kind") or "") == "directory" else "session file name"
        if index + 1 >= len(tokens) or str(tokens[index + 1]).startswith("-"):
            return None, None, f"{flag} requires a {label}"
        return tokens[index + 1], index + 1, None
    if value_kind in {"attached", "separate_or_attached"}:
        if flag.startswith("--") and token.startswith(f"{flag}="):
            return token[len(flag) + 1:], index, None
        if not flag.startswith("--") and token.startswith(flag) and token != flag:
            return token[len(flag):], index, None
    return None, None, None


def _restricted_command_networks(cfg: dict | None = None) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    active_cfg = cfg or app_config.CFG
    raw_values = active_cfg.get("restricted_command_input_cidrs") or []
    if isinstance(raw_values, str):
        raw_values = [raw_values]
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw_value in raw_values if isinstance(raw_values, list) else []:
        value = str(raw_value or "").strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def _value_type_is_restrictable(value_type: str) -> bool:
    return str(value_type or "").strip().lower() in RESTRICTABLE_VALUE_TYPES


def _dict_value(data: dict[str, object], key: str) -> dict:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _list_value(data: dict[str, object], key: str) -> list:
    value = data.get(key)
    return value if isinstance(value, list) else []


def _autocomplete_value_type_from_hint(spec: dict[str, object], trigger: str) -> str:
    hints = _dict_value(spec, "arg_hints").get(trigger) or []
    for hint in hints:
        if not isinstance(hint, dict):
            continue
        value_type = str(hint.get("value_type") or "").strip().lower()
        if value_type:
            return value_type
    return ""


def _autocomplete_flag_value_types(spec: dict[str, object]) -> dict[str, str]:
    value_types: dict[str, str] = {}
    for flag in _list_value(spec, "flags"):
        if not isinstance(flag, dict):
            continue
        token = str(flag.get("value") or "").strip()
        if not token:
            continue
        value_type = str(flag.get("value_type") or "").strip().lower()
        if not value_type:
            value_type = _autocomplete_value_type_from_hint(spec, token)
        if value_type:
            value_types[token] = value_type
    for trigger in _dict_value(spec, "arg_hints"):
        token = str(trigger or "").strip()
        if token and token != "__positional__" and token not in value_types:
            value_type = _autocomplete_value_type_from_hint(spec, token)
            if value_type:
                value_types[token] = value_type
    return value_types


def _autocomplete_positional_value_types(spec: dict[str, object]) -> list[str]:
    value_types = []
    for hint in _dict_value(spec, "arg_hints").get("__positional__", []) or []:
        if not isinstance(hint, dict):
            continue
        value_type = str(hint.get("value_type") or "").strip().lower()
        if _value_type_is_restrictable(value_type):
            value_types.append(value_type)
    return _dedupe_preserve_order(value_types)


def _autocomplete_spec_needs_normalization(spec: dict[str, object]) -> bool:
    if "arg_hints" not in spec or "arguments" in spec:
        return True
    return any(
        isinstance(flag, dict) and ("takes_value" in flag or "value_hint" in flag)
        for flag in _list_value(spec, "flags")
    )


def _autocomplete_spec_for_tokens(tokens: list[str], cfg: dict | None = None) -> tuple[dict[str, object], int]:
    if not tokens:
        return {}, 1
    context = load_autocomplete_context_from_commands_registry(cfg=cfg)
    spec = context.get(tokens[0].lower()) or {}
    if isinstance(spec, dict) and _autocomplete_spec_needs_normalization(spec):
        spec = _normalize_single_autocomplete_spec(spec)
    start_index = 1
    subcommands = spec.get("subcommands") if isinstance(spec, dict) else None
    if isinstance(subcommands, dict) and len(tokens) > 1:
        sub_spec = subcommands.get(tokens[1].lower())
        if isinstance(sub_spec, dict):
            if _autocomplete_spec_needs_normalization(sub_spec):
                sub_spec = _normalize_single_autocomplete_spec(sub_spec, include_pipe=False)
            return sub_spec, 2
    return (spec if isinstance(spec, dict) else {}), start_index


def _flag_value_from_token(tokens: list[str], index: int, flag: str) -> tuple[str | None, int | None]:
    token = tokens[index]
    if token == flag:
        if index + 1 >= len(tokens) or tokens[index + 1].startswith("-"):
            return None, None
        return tokens[index + 1], index + 1
    if flag.startswith("--") and token.startswith(f"{flag}="):
        return token[len(flag) + 1:], index
    if not flag.startswith("--") and token.startswith(flag) and token != flag:
        return token[len(flag):], index
    return None, None


def _candidate_host_tokens(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    candidates = [raw.strip("[]")]
    if "://" in raw:
        parsed = urlparse(raw)
        if parsed.hostname:
            candidates.append(parsed.hostname)
    elif raw.startswith("//"):
        parsed = urlparse(f"scheme:{raw}")
        if parsed.hostname:
            candidates.append(parsed.hostname)
    if raw.startswith("[") and "]" in raw:
        candidates.append(raw[1:raw.index("]")])
    elif raw.count(":") == 1 and "/" not in raw:
        host, port = raw.rsplit(":", 1)
        if host and port.isdigit():
            candidates.append(host)
    return _dedupe_preserve_order([item.strip("[]") for item in candidates if item.strip("[]")])


def _restricted_value_match(value: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> str | None:
    if not networks:
        return None
    for candidate in _candidate_host_tokens(value):
        try:
            if "/" in candidate:
                candidate_network = ipaddress.ip_network(candidate, strict=False)
                if any(candidate_network.overlaps(network) for network in networks):
                    return candidate
            else:
                candidate_ip = ipaddress.ip_address(candidate)
                if any(candidate_ip in network for network in networks):
                    return candidate
        except ValueError:
            continue
    return None


def _restricted_input_reason(value: str) -> str:
    return f"Command input targets restricted IP/CIDR value: {value}"


def _restricted_inline_input_reason(command: str, cfg: dict | None = None) -> str:
    networks = _restricted_command_networks(cfg)
    if not networks:
        return ""
    tokens = split_command_argv(command)
    if not tokens:
        return ""
    spec, start_index = _autocomplete_spec_for_tokens(tokens, cfg=cfg)
    if not spec:
        return ""
    flag_value_types = _autocomplete_flag_value_types(spec)
    positional_types = _autocomplete_positional_value_types(spec)
    consumed: set[int] = set(range(start_index))
    positional_index = 0

    index = start_index
    while index < len(tokens):
        token = tokens[index]
        matched_flag = None
        matched_value_index = None
        for flag, value_type in flag_value_types.items():
            value, value_index = _flag_value_from_token(tokens, index, flag)
            if value is None or value_index is None:
                continue
            matched_flag = flag
            matched_value_index = value_index
            if _value_type_is_restrictable(value_type):
                blocked = _restricted_value_match(value, networks)
                if blocked:
                    return _restricted_input_reason(blocked)
            break
        if matched_flag is not None:
            consumed.add(index)
            if matched_value_index is not None:
                consumed.add(matched_value_index)
            index = (matched_value_index + 1) if matched_value_index is not None else index + 1
            continue
        if token.startswith("-"):
            consumed.add(index)
            index += 1
            continue
        if index not in consumed and positional_types:
            value_type = positional_types[min(positional_index, len(positional_types) - 1)]
            positional_index += 1
            if _value_type_is_restrictable(value_type):
                blocked = _restricted_value_match(token, networks)
                if blocked:
                    return _restricted_input_reason(blocked)
        index += 1
    return ""


def _workspace_read_file_restriction_reason(
    command: str,
    session_id: str,
    cfg: dict | None = None,
) -> str:
    networks = _restricted_command_networks(cfg)
    if not networks or not session_id:
        return ""
    tokens = split_command_argv(command)
    if not tokens:
        return ""
    specs = [
        spec for spec in _workspace_flag_specs_by_root().get(tokens[0].lower(), [])
        if _workspace_flag_applies_to_command(spec, tokens)
        and spec.get("mode") in {"read", "read_write"}
        and spec.get("kind") != "directory"
    ]
    if not specs:
        return ""
    autocomplete_spec, _ = _autocomplete_spec_for_tokens(tokens, cfg=cfg)
    flag_value_types = _autocomplete_flag_value_types(autocomplete_spec)
    index = 1
    while index < len(tokens):
        matched_spec = next((spec for spec in specs if _workspace_flag_matches_token(tokens[index], spec)), None)
        if not matched_spec:
            index += 1
            continue
        flag = str(matched_spec.get("flag") or "")
        value_type = flag_value_types.get(flag, "")
        user_value, value_index, _ = _workspace_flag_value(tokens, index, matched_spec)
        if (
            user_value
            and value_index is not None
            and not os.path.isabs(user_value)
            and _value_type_is_restrictable(value_type)
        ):
            try:
                text = read_workspace_text_file(session_id, user_value, cfg)
            except (InvalidWorkspacePath, WorkspaceDisabled, WorkspaceFileNotFound, OSError):
                text = ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                blocked = _restricted_value_match(line, networks)
                if blocked:
                    return f"Session file {user_value} contains restricted IP/CIDR value: {blocked}"
        index = (value_index + 1) if value_index is not None else index + 1
    return ""


def _rewrite_workspace_file_flags(
    command: str,
    session_id: str,
    cfg: dict | None = None,
) -> tuple[str, set[str], list[str], list[str], list[str], str]:
    cfg = cfg or app_config.CFG
    tokens = split_command_argv(command)
    if not tokens:
        return command, set(), [], [], [], ""

    specs = [
        spec for spec in _workspace_flag_specs_by_root().get(tokens[0].lower(), [])
        if _workspace_flag_applies_to_command(spec, tokens)
    ]
    if not specs:
        return command, set(), [], [], [], ""

    if not cfg.get("workspace_enabled"):
        index = 1
        while index < len(tokens):
            matched_spec = next((spec for spec in specs if _workspace_flag_matches_token(tokens[index], spec)), None)
            if not matched_spec:
                index += 1
                continue
            user_value, value_index, error = _workspace_flag_value(tokens, index, matched_spec)
            if error:
                return command, set(), [], [], [], error
            if user_value and value_index is not None and not os.path.isabs(user_value):
                return (
                    command,
                    set(),
                    [],
                    [],
                    [],
                    "Files are disabled on this instance; session file flags are not available.",
                )
            index = (value_index + 1) if value_index is not None else index + 1
        return command, set(), [], [], [], ""

    root = tokens[0].lower()
    managed_dir = _managed_workspace_directory_for_root(root)
    managed_dir_flag = str(managed_dir.get("flag") or "")
    managed_dir_name = str(managed_dir.get("directory") or "")
    managed_dir_specs = [spec for spec in specs if spec.get("flag") == managed_dir_flag]
    has_managed_dir = any(
        _workspace_flag_matches_token(token, spec)
        for token in tokens[1:]
        for spec in managed_dir_specs
    )
    managed_dir_applies = (
        bool(managed_dir_flag and managed_dir_name and managed_dir_specs)
        and _managed_workspace_directory_applies(managed_dir, tokens)
    )
    if managed_dir_applies and not has_managed_dir:
        tokens = tokens + [managed_dir_flag, managed_dir_name]
    elif managed_dir_applies and has_managed_dir and managed_dir.get("reject_alternate", True):
        for index, token in enumerate(tokens):
            matched_spec = next((spec for spec in managed_dir_specs if _workspace_flag_matches_token(token, spec)), None)
            if not matched_spec:
                continue
            user_value, _, error = _workspace_flag_value(tokens, index, matched_spec)
            if error:
                return command, set(), [], [], [], error
            normalized_value = (user_value or "").rstrip(os.sep)
            if normalized_value and os.path.basename(normalized_value) != managed_dir_name:
                reject_message = str(managed_dir.get("reject_message") or "").strip()
                return (
                    command,
                    set(),
                    [],
                    [],
                    [],
                    reject_message or f"{tokens[0]} uses the managed {managed_dir_name} session directory.",
                )
            break

    rewritten_tokens = list(tokens)
    exempt_flags: set[str] = set()
    reads: list[str] = []
    writes: list[str] = []
    exec_paths: list[str] = []
    index = 1
    while index < len(tokens):
        matched_spec = next((spec for spec in specs if _workspace_flag_matches_token(tokens[index], spec)), None)
        if not matched_spec:
            index += 1
            continue

        flag = str(matched_spec.get("flag") or "")
        user_value, value_index, error = _workspace_flag_value(tokens, index, matched_spec)
        if error:
            return command, set(), [], [], [], error
        if not user_value or value_index is None:
            index += 1
            continue

        mode = str(matched_spec.get("mode") or "")
        kind = str(matched_spec.get("kind") or "file")
        if os.path.isabs(user_value):
            index = value_index + 1
            continue

        try:
            resolved = resolve_workspace_path(
                session_id,
                user_value,
                cfg,
                ensure_parent=mode in {"write", "read_write"} or kind == "directory",
            )
            if kind == "directory":
                prepare_workspace_directory_for_command(resolved, mode=mode)
            else:
                if mode in {"read", "read_write"} and not resolved.is_file():
                    raise WorkspaceFileNotFound(f"session file not found: {user_value}")
                prepare_workspace_file_for_command(resolved, mode=mode)
        except (InvalidWorkspacePath, WorkspaceDisabled, WorkspaceFileNotFound) as exc:
            return command, set(), [], [], [], str(exc)

        resolved_value = str(resolved)
        if value_index == index and tokens[index] != flag:
            rewritten_tokens[index] = f"{flag}={resolved_value}" if flag.startswith("--") else f"{flag}{resolved_value}"
        else:
            rewritten_tokens[value_index] = resolved_value

        exempt_flags.add(flag)
        exec_paths.append(resolved_value)
        if kind != "directory" and mode in {"read", "read_write"}:
            reads.append(user_value)
        if mode in {"write", "read_write"}:
            writes.append(user_value)
        index = value_index + 1

    return shlex.join(rewritten_tokens), exempt_flags, reads, writes, exec_paths, ""


def _runtime_environment_value(template: str, tokens: list[str], env_spec: dict[str, object]) -> str:
    managed_flag = str(env_spec.get("managed_directory_flag") or "").strip()
    managed_directory = ""
    managed_workspace_parent = ""
    if managed_flag:
        for index, token in enumerate(tokens[:-1]):
            if token != managed_flag:
                continue
            directory = tokens[index + 1].rstrip(os.sep)
            if os.path.isabs(directory):
                managed_directory = directory
                managed_workspace_parent = os.path.dirname(directory)
            break
    return (
        template
        .replace("{managed_workspace_directory}", managed_directory)
        .replace("{managed_workspace_parent}", managed_workspace_parent)
    )


def _apply_workspace_runtime_environment(command: str) -> str:
    tokens = split_command_argv(command)
    if not tokens:
        return command

    adaptations = _runtime_adaptations_by_root().get(tokens[0].lower(), {})
    env_specs = adaptations.get("environment") if isinstance(adaptations, dict) else []
    if not isinstance(env_specs, list) or not env_specs:
        return command

    env_tokens = []
    for env_spec in env_specs:
        if not isinstance(env_spec, dict):
            continue
        name = str(env_spec.get("name") or "").strip()
        template = str(env_spec.get("value") or "").strip()
        if not name or not template:
            continue
        value = _runtime_environment_value(template, tokens, env_spec)
        if not value:
            continue
        env_tokens.append(f"{name}={value}")

    return shlex.join(["env", *env_tokens, *tokens]) if env_tokens else command


def _is_denied(command: str, deny_entries: list[str], *, exempt_flags: set[str] | None = None) -> bool:
    """Return True if command matches any deny entry.
    Deny entries match tool/subcommand prefixes case-insensitively, but flags are
    matched exactly as written. A deny entry like 'curl -o' is matched if:
      - the command starts with the deny prefix, OR
      - the tool prefix matches AND the flag appears anywhere after it in the command,
        so 'curl -s -o file' is caught as well as 'curl -o file'.
    For single-character flags (e.g. -e, -c), the flag is also matched when combined
    with other single-char flags in a group: 'nc -ve' is caught by '!nc -e', and
    'nc -vc' is caught by '!nc -c'. Multi-char flags (--script, -oN) use exact-token
    matching only.
    Exception: a denied output flag is allowed when its argument is /dev/null,
    permitting common patterns like 'curl -o /dev/null -w "%{http_code}" <url>'.
    """
    command_tokens = split_command_argv(command)
    if not command_tokens:
        return False

    exempt_flags = exempt_flags or set()
    for d in deny_entries:
        deny_tokens = split_command_argv(d)
        if not deny_tokens:
            continue

        if len(deny_tokens) == 1:
            if command_tokens[0].lower() == deny_tokens[0].lower():
                return True
            continue

        tool_prefix = deny_tokens[:-1]
        flag = deny_tokens[-1]
        if flag in exempt_flags:
            continue
        if not _tokens_start_with(command_tokens, tool_prefix):
            continue

        tail = command_tokens[len(tool_prefix):]
        for idx, token in enumerate(tail):
            if not _flag_matches_token(flag, token):
                continue
            if idx + 1 < len(tail) and tail[idx + 1] == "/dev/null":
                break
            return True
    return False


def validate_command(
    command: str,
    *,
    session_id: str = "",
    cfg: dict | None = None,
) -> CommandValidationResult:
    """Validate a command and return the display command plus execution command.

    Workspace-aware file/directory flags are still denied by default. When
    workspace storage is enabled, declared workspace flags are validated and
    rewritten to the current session workspace before deny-prefix checks run.
    """
    cfg = cfg or app_config.CFG
    allowed, denied = load_command_policy()
    allow_grouping = load_allow_grouping_flags()
    if allowed is None:
        return CommandValidationResult(True, display_command=command, exec_command=command)

    synthetic_postfilter, postfilter_error = parse_synthetic_postfilter(command)
    if postfilter_error:
        return CommandValidationResult(False, postfilter_error, display_command=command, exec_command=command)
    command_to_validate = synthetic_postfilter["base_command"] if synthetic_postfilter else command

    # Block shell chaining/redirection operators outright when restrictions are active
    if not synthetic_postfilter and SHELL_CHAIN_RE.search(command):
        return CommandValidationResult(
            False,
            "Shell operators (&&, |, ;, >, etc.) are not permitted.",
            display_command=command,
            exec_command=command_to_validate,
        )

    if _PATH_DATA_RE.search(command_to_validate):
        return CommandValidationResult(
            False, "Access to /data is not permitted.",
            display_command=command, exec_command=command_to_validate,
        )
    if _PATH_TMP_RE.search(command_to_validate):
        return CommandValidationResult(
            False, "Access to /tmp is not permitted.",
            display_command=command, exec_command=command_to_validate,
        )
    if _LOOPBACK_RE.search(command_to_validate):
        return CommandValidationResult(
            False, "Connections to the local host are not permitted.",
            display_command=command, exec_command=command_to_validate,
        )

    nmap_raw_reason = _nmap_raw_scan_restriction_reason(command_to_validate)
    if nmap_raw_reason:
        return CommandValidationResult(
            False,
            nmap_raw_reason,
            display_command=command,
            exec_command=command_to_validate,
        )

    restricted_reason = _restricted_inline_input_reason(command_to_validate, cfg)
    if restricted_reason:
        return CommandValidationResult(
            False,
            restricted_reason,
            display_command=command,
            exec_command=command_to_validate,
        )

    exec_command, exempt_flags, reads, writes, exec_paths, workspace_error = _rewrite_workspace_file_flags(
        command_to_validate,
        session_id,
        cfg,
    )
    if workspace_error:
        return CommandValidationResult(
            False,
            workspace_error,
            display_command=command,
            exec_command=command_to_validate,
        )

    restricted_file_reason = _workspace_read_file_restriction_reason(command_to_validate, session_id, cfg)
    if restricted_file_reason:
        return CommandValidationResult(
            False,
            restricted_file_reason,
            display_command=command,
            exec_command=command_to_validate,
        )

    command_tokens = split_command_argv(command_to_validate.strip())

    # Deny prefixes take priority — checked before allow list
    if denied and _is_denied(command_to_validate.strip(), denied, exempt_flags=exempt_flags):
        return CommandValidationResult(
            False,
            f"Command not allowed: '{command.strip()}'",
            display_command=command,
            exec_command=command_to_validate,
        )

    if not _is_allowed_by_policy(command_tokens, allowed, allow_grouping):
        return CommandValidationResult(
            False,
            f"Command not allowed: '{command.strip()}'",
            display_command=command,
            exec_command=command_to_validate,
        )

    exec_command = _apply_workspace_runtime_environment(exec_command)

    return CommandValidationResult(
        True,
        display_command=command,
        exec_command=exec_command,
        workspace_reads=reads,
        workspace_writes=writes,
        workspace_exec_paths=exec_paths,
    )


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Return (allowed, reason) for legacy callers."""
    result = validate_command(command)
    return result.allowed, result.reason


def rewrite_command(
    command: str,
    *,
    session_id: str = "",
    cfg: dict | None = None,
) -> tuple[str, str | None]:
    """Rewrite commands that need a TTY or specific flags into a safe non-interactive equivalent.
    Returns (rewritten_command, notice_message_or_None)."""
    return _apply_runtime_inject_flags(command, session_id=session_id, cfg=cfg)
