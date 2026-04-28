"""
Command loading, validation, and rewriting.

This module has no dependency on Flask — it contains pure helpers that can be
imported and tested in isolation.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import html
import os
import re
import shlex
import shutil
import yaml

import config as app_config
from workspace import (
    InvalidWorkspacePath,
    WorkspaceDisabled,
    WorkspaceFileNotFound,
    prepare_workspace_directory_for_command,
    prepare_workspace_file_for_command,
    resolve_workspace_path,
)

_HERE = os.path.dirname(__file__)
_CONF = os.path.join(_HERE, "conf")
COMMANDS_REGISTRY_FILE = os.path.join(_CONF, "commands.yaml")
FAQ_FILE              = os.path.join(_CONF, "faq.yaml")
WORKFLOWS_FILE        = os.path.join(_CONF, "workflows.yaml")
WELCOME_FILE          = os.path.join(_CONF, "welcome.yaml")
ASCII_FILE            = os.path.join(_CONF, "ascii.txt")
ASCII_MOBILE_FILE     = os.path.join(_CONF, "ascii_mobile.txt")
APP_HINTS_FILE        = os.path.join(_CONF, "app_hints.txt")
APP_HINTS_MOBILE_FILE = os.path.join(_CONF, "app_hints_mobile.txt")
AMASS_DEFAULT_WORKSPACE_DIR = "amass"
AMASS_MANAGED_DATABASE_SUBCOMMANDS = {"enum", "subs", "track", "viz"}


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


def autocomplete_context_from_commands_registry(registry: dict, cfg=None) -> dict:
    """Return the browser autocomplete context from a loaded command registry."""
    context = {}
    for section in ("commands", "pipe_helpers"):
        for entry in registry.get(section, []) or []:
            root = str(entry.get("root") or "").strip().lower()
            autocomplete = entry.get("autocomplete")
            if root and isinstance(autocomplete, dict) and autocomplete:
                context[root] = _attach_workspace_autocomplete_flags(
                    deepcopy(autocomplete),
                    entry.get("workspace_flags") or [],
                )
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
    """Read autocomplete metadata from commands.yaml."""
    return autocomplete_context_from_commands_registry(load_commands_registry(), cfg=cfg)


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
    return {
        "title": title,
        "description": description,
        "inputs": inputs,
        "steps": clean_steps,
    }


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


def load_all_workflows():
    """Return the built-in workflows followed by any custom workflows.yaml entries."""
    builtins = []
    for entry in _builtin_workflows():
        normalized = _normalize_workflow_entry(entry)
        if normalized:
            builtins.append(normalized)
    return [*builtins, *load_workflows()]


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
        if hint_sources:
            bucket, seen = _hint_bucket(token)
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
            if normalized_sub:
                key = str(normalized_sub["value"]).lower()
                if key not in positional_seen:
                    positional_seen.add(key)
                    positional_bucket.append(normalized_sub)

    raw_argument_limit = raw_spec.get("argument_limit")
    argument_limit = raw_argument_limit if isinstance(raw_argument_limit, int) and raw_argument_limit > 0 else None

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

    for workflow in load_all_workflows():
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


def _workspace_flag_applies_to_command(spec: dict[str, object], tokens: list[str]) -> bool:
    subcommands = spec.get("subcommands")
    if not subcommands:
        return True
    if not isinstance(subcommands, list) or len(tokens) < 2:
        return False
    command_sub = tokens[1].strip().lower()
    return command_sub in {str(item).strip().lower() for item in subcommands}


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

    amass_dir_specs = [spec for spec in specs if spec.get("flag") == "-dir"]
    has_amass_dir = any(
        _workspace_flag_matches_token(token, spec)
        for token in tokens[1:]
        for spec in amass_dir_specs
    )
    is_amass_database_command = (
        tokens[0].lower() == "amass"
        and len(tokens) > 1
        and tokens[1].lower() in AMASS_MANAGED_DATABASE_SUBCOMMANDS
        and not any(token in {"-h", "-help", "--help"} for token in tokens[1:])
    )
    if is_amass_database_command and not has_amass_dir:
        tokens = tokens + ["-dir", AMASS_DEFAULT_WORKSPACE_DIR]
    elif is_amass_database_command and has_amass_dir:
        for index, token in enumerate(tokens):
            matched_spec = next((spec for spec in amass_dir_specs if _workspace_flag_matches_token(token, spec)), None)
            if not matched_spec:
                continue
            user_value, _, error = _workspace_flag_value(tokens, index, matched_spec)
            if error:
                return command, set(), [], [], [], error
            normalized_value = (user_value or "").rstrip(os.sep)
            if normalized_value and os.path.basename(normalized_value) != AMASS_DEFAULT_WORKSPACE_DIR:
                return (
                    command,
                    set(),
                    [],
                    [],
                    [],
                    f"Amass database commands use the managed {AMASS_DEFAULT_WORKSPACE_DIR} session directory.",
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


def _apply_workspace_runtime_environment(command: str) -> str:
    tokens = split_command_argv(command)
    if not tokens or tokens[0].lower() != "amass":
        return command

    for index, token in enumerate(tokens[:-1]):
        if token != "-dir":
            continue
        directory = tokens[index + 1].rstrip(os.sep)
        if not os.path.isabs(directory) or os.path.basename(directory) != AMASS_DEFAULT_WORKSPACE_DIR:
            return command

        # Amass v5 auto-starts `amass engine`; point its default config dir at
        # the same parent used by the rewritten `-dir` database path.
        xdg_config_home = os.path.dirname(directory)
        return shlex.join(["env", f"XDG_CONFIG_HOME={xdg_config_home}", *tokens])

    return command


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

    cmd_lower = command_to_validate.strip().lower()

    # Deny prefixes take priority — checked before allow list
    if denied and _is_denied(command_to_validate.strip(), denied, exempt_flags=exempt_flags):
        return CommandValidationResult(
            False,
            f"Command not allowed: '{command.strip()}'",
            display_command=command,
            exec_command=command_to_validate,
        )

    if not any(cmd_lower == prefix or cmd_lower.startswith(prefix + " ")
               for prefix in allowed):
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


def rewrite_command(command: str) -> tuple[str, str | None]:
    """Rewrite commands that need a TTY or specific flags into a safe non-interactive equivalent.
    Returns (rewritten_command, notice_message_or_None)."""
    # Runtime rewrites are kept explicit and side-effect free. The optional note
    # explains to users/tests why the command was adjusted.
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

    # naabu: force connect scan mode so it uses TCP connect() instead of raw SYN packets.
    # Raw packet scanning via libpcap/gopacket requires elevated privileges that are
    # not reliably available inside the container; connect mode works like nmap -sT.
    if re.match(r'^naabu\b', stripped, re.IGNORECASE):
        if not re.search(r'-scan-type\b|-st\b', stripped):
            return re.sub(r'^naabu\b', 'naabu -scan-type c', stripped, flags=re.IGNORECASE), None

    return stripped, None
