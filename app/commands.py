"""
Command loading, validation, and rewriting.

This module has no dependency on Flask — it contains pure helpers that can be
imported and tested in isolation.
"""

from copy import deepcopy
import html
import os
import re
import shlex
import shutil
import yaml

import config as app_config

_HERE = os.path.dirname(__file__)
_CONF = os.path.join(_HERE, "conf")
ALLOWED_COMMANDS_FILE = os.path.join(_CONF, "allowed_commands.txt")
AUTOCOMPLETE_CONTEXT_FILE = os.path.join(_CONF, "autocomplete.yaml")
FAQ_FILE              = os.path.join(_CONF, "faq.yaml")
WORKFLOWS_FILE        = os.path.join(_CONF, "workflows.yaml")
WELCOME_FILE          = os.path.join(_CONF, "welcome.yaml")
ASCII_FILE            = os.path.join(_CONF, "ascii.txt")
ASCII_MOBILE_FILE     = os.path.join(_CONF, "ascii_mobile.txt")
APP_HINTS_FILE        = os.path.join(_CONF, "app_hints.txt")
APP_HINTS_MOBILE_FILE = os.path.join(_CONF, "app_hints_mobile.txt")


def _project_readme_url(project_readme=None):
    return project_readme or app_config.PROJECT_README


def _builtin_faq(app_name="darklab_shell", project_readme=None):
    readme_url = _project_readme_url(project_readme)
    return [
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
            "answer": "Use the grouped allowlist shown in the FAQ modal or run ls in the web shell.",
            "ui_kind": "allowed_commands",
        },
        {
            "question": "What built-in shell features are supported?",
            "answer": (
                "The shell supports built-in commands plus a narrow set of commands with built-in "
                "pipe support like grep, head, tail, wc -l, sort, and uniq. For a full list of built-in commands, "
                "run the command help in the web shell."
            ),
            "answer_html": (
                "This shell includes two kinds of built-in behavior:<br><br>"
                "<strong>Built-in commands</strong> such as <code>status</code>, "
                "<code>history</code>, <code>retention</code>, <code>shortcuts</code>, "
                "<code>limits</code>, and <code>faq</code>. For a full list, run the command <code>help</code>."
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
            "question": "What are the retention and limit settings for this instance?",
            "answer": "See the live retention and limit table in the FAQ modal or run retention in the web shell.",
            "ui_kind": "limits",
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


def load_allowed_commands():
    """Read allowed_commands.txt and return (allow_prefixes, deny_prefixes).
    allow_prefixes is None if the file doesn't exist or has no allow entries (= unrestricted).
    deny_prefixes is always a list. Lines starting with ! are deny prefixes and take
    priority over allow prefixes — use them to block specific flags on an allowed command.
    Allow prefixes are normalized to lowercase for case-insensitive matching; deny prefixes
    preserve their original flag casing so entries like !curl -K do not block curl -k."""
    # Returning (None, []) is the app-wide sentinel for unrestricted mode.
    if not os.path.exists(ALLOWED_COMMANDS_FILE):
        return None, []
    prefixes = []
    denied = []
    for raw_line in _load_text_lines(ALLOWED_COMMANDS_FILE):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            denied.append(line[1:].strip())
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


def load_all_faq(app_name="darklab_shell", project_readme=None):
    """Return the built-in FAQ entries followed by any custom faq.yaml entries."""
    return [*(deepcopy(_builtin_faq(app_name, project_readme))), *load_faq()]


def _builtin_workflows():
    return [
        {
            "title": "DNS Troubleshooting",
            "description": "Diagnose why a domain isn't resolving or returns unexpected results.",
            "steps": [
                {"cmd": "dig darklab.sh A",          "note": "Does it resolve? Check the ANSWER section."},
                {"cmd": "dig darklab.sh NS",          "note": "Which nameservers are authoritative?"},
                {"cmd": "dig @8.8.8.8 darklab.sh A", "note": "Does a public resolver see it differently?"},
                {"cmd": "dig darklab.sh +trace",      "note": "Trace delegation step by step from the root."},
                {"cmd": "dig darklab.sh MX",          "note": "Check mail exchanger records."},
            ],
        },
        {
            "title": "TLS / HTTPS Check",
            "description": "Verify a domain's certificate, chain, and TLS configuration.",
            "steps": [
                {"cmd": "curl -Iv https://darklab.sh",
                 "note": "Check response headers and certificate details."},
                {"cmd": "openssl s_client -connect darklab.sh:443",
                 "note": "Inspect the raw TLS handshake and certificate chain."},
                {"cmd": "testssl darklab.sh",
                 "note": "Run a full TLS audit including ciphers and known vulnerabilities."},
            ],
        },
        {
            "title": "HTTP Triage",
            "description": "Investigate what a web server is returning.",
            "steps": [
                {"cmd": "curl -sIL https://darklab.sh",
                 "note": "Follow redirects and inspect the final response headers."},
                {"cmd": "curl -sv -o /dev/null https://darklab.sh| head -60",
                 "note": "Verbose output with timing, TLS detail, and headers."},
                {"cmd": "wget -S --spider https://darklab.sh",
                 "note": "Spider check with full server response headers."},
            ],
        },
        {
            "title": "Quick Reachability Check",
            "description": "Confirm a host is up and identify which ports are open.",
            "steps": [
                {"cmd": "ping -c 4 darklab.sh",    "note": "Is the host reachable? Check latency and packet loss."},
                {"cmd": "nc -zv darklab.sh 443",   "note": "Is HTTPS open and accepting connections?"},
                {"cmd": "nmap -F darklab.sh",      "note": "Fast scan of the 100 most common ports."},
            ],
        },
        {
            "title": "Email Server Check",
            "description": "Verify mail delivery configuration for a domain.",
            "steps": [
                {"cmd": "dig darklab.sh MX",       "note": "Which mail servers handle email for this domain?"},
                {"cmd": "dig darklab.sh TXT",      "note": "Check SPF, DKIM policy, and other TXT records."},
                {"cmd": "dig _dmarc.darklab.sh TXT",
                 "note": "Check the DMARC policy published for the domain."},
                {"cmd": "dig @8.8.8.8 darklab.sh MX",
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
            "steps": [
                {"cmd": "whois darklab.sh", "note": "Review registration, registrar, and allocation context."},
                {"cmd": "dig darklab.sh NS", "note": "Identify authoritative nameservers for the domain."},
                {"cmd": "subfinder -d darklab.sh -silent", "note": "Find passively observed subdomains."},
                {"cmd": "dnsrecon -d darklab.sh", "note": "Enumerate common DNS records and transfer hints."},
            ],
        },
        {
            "title": "Subdomain Enumeration & Validation",
            "description": "Discover candidate subdomains, resolve them, and probe likely web services.",
            "steps": [
                {"cmd": "subfinder -d darklab.sh -silent", "note": "Collect passive subdomain candidates."},
                {
                    "cmd": (
                        "dnsx -d darklab.sh "
                        "-w /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt -resp"
                    ),
                    "note": "Resolve common subdomains and keep the DNS response context.",
                },
                {
                    "cmd": "pd-httpx -u https://darklab.sh -title -status-code -tech-detect",
                    "note": "Probe HTTPS and collect status, title, and technology hints.",
                },
            ],
        },
        {
            "title": "Web Directory Discovery",
            "description": "Look for common web paths and follow up on interesting responses.",
            "steps": [
                {
                    "cmd": (
                        "ffuf -u https://darklab.sh/FUZZ "
                        "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt"
                    ),
                    "note": "Fuzz common paths and watch for non-baseline status codes or sizes.",
                },
                {
                    "cmd": (
                        "gobuster dir -u https://tor-stats.darklab.sh "
                        "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt"
                    ),
                    "note": "Run a second directory check with a different scanner.",
                },
                {"cmd": "curl -sIL https://darklab.sh/admin", "note": "Inspect redirects and headers for a candidate path."},
            ],
        },
        {
            "title": "SSL / TLS Deep Dive",
            "description": "Inspect certificates, protocol support, cipher exposure, and known TLS weaknesses.",
            "steps": [
                {"cmd": "sslscan darklab.sh", "note": "Enumerate protocols, ciphers, and certificate metadata."},
                {"cmd": "sslyze --certinfo darklab.sh", "note": "Validate certificate chain details."},
                {
                    "cmd": "openssl s_client -connect darklab.sh:443 -servername darklab.sh",
                    "note": "Inspect the raw handshake and served certificate chain.",
                },
                {"cmd": "testssl darklab.sh", "note": "Run the broader TLS configuration audit."},
            ],
        },
        {
            "title": "CDN / Edge Behavior Check",
            "description": "Compare DNS, ownership, redirects, headers, and WAF/CDN edge signals.",
            "steps": [
                {"cmd": "dig darklab.sh A", "note": "Check the current address records."},
                {"cmd": "whois darklab.sh", "note": "Review ownership and provider hints."},
                {"cmd": "curl -sIL https://darklab.sh", "note": "Inspect redirects, cache headers, and edge headers."},
                {"cmd": "wafw00f https://darklab.sh", "note": "Look for WAF or CDN fingerprints."},
            ],
        },
        {
            "title": "API Recon",
            "description": "Triage API-style endpoints with headers, methods, JSON negotiation, and path fuzzing.",
            "steps": [
                {"cmd": "curl -sI https://darklab.sh/api", "note": "Check whether the API path responds and how."},
                {"cmd": "curl -sX OPTIONS -I https://darklab.sh/api", "note": "Inspect allowed methods and CORS-style headers."},
                {
                    "cmd": "curl -sH Accept:application/json https://darklab.sh/api",
                    "note": "Ask for JSON explicitly and inspect the response shape.",
                },
                {
                    "cmd": (
                        "ffuf -u https://darklab.sh/FUZZ "
                        "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt"
                    ),
                    "note": "Fuzz common API-adjacent paths and versions.",
                },
            ],
        },
        {
            "title": "Network Path Analysis",
            "description": "Diagnose reachability, route shape, latency, and packet-loss symptoms.",
            "steps": [
                {"cmd": "ping -c 10 darklab.sh", "note": "Measure basic reachability, latency, and packet loss."},
                {"cmd": "mtr darklab.sh", "note": "Summarize path loss and latency in report mode."},
                {"cmd": "traceroute darklab.sh", "note": "Capture a static routed path to the target."},
                {"cmd": "tcptraceroute darklab.sh 443", "note": "Trace the TCP path toward HTTPS specifically."},
            ],
        },
        {
            "title": "Fast Port Discovery to Service Fingerprint",
            "description": "Sweep for exposed ports quickly, then fingerprint and validate important services.",
            "steps": [
                {"cmd": "rustscan -a darklab.sh --range 1-1000", "note": "Quickly sweep the first thousand ports."},
                {"cmd": "naabu -host darklab.sh -silent", "note": "Run a second fast TCP discovery pass."},
                {"cmd": "nmap -sV darklab.sh", "note": "Fingerprint services once you know exposure is present."},
                {"cmd": "nc -zv darklab.sh 80", "note": "Validate a specific expected port manually."},
            ],
        },
    ]


def load_workflows():
    """Read workflows.yaml and return a list of workflow dicts."""
    data = _load_yaml_list_with_local(WORKFLOWS_FILE)
    if not data:
        return []
    result = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        description = str(entry.get("description") or "").strip()
        steps = entry.get("steps") or []
        if not title or not isinstance(steps, list):
            continue
        clean_steps = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            cmd = str(step.get("cmd") or "").strip()
            note = str(step.get("note") or "").strip()
            if cmd:
                clean_steps.append({"cmd": cmd, "note": note})
        if clean_steps:
            result.append({"title": title, "description": description, "steps": clean_steps})
    return result


def load_all_workflows():
    """Return the built-in workflows followed by any custom workflows.yaml entries."""
    return [*_builtin_workflows(), *load_workflows()]


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


def _load_autocomplete_config(path):
    loaded = _load_yaml_mapping(path)
    if not loaded:
        return {"context": {}}

    raw_context = loaded.get("context", {})
    return {
        "context": _normalize_autocomplete_context(raw_context),
    }


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
    return result


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


def _normalize_autocomplete_context(data):
    if not isinstance(data, dict):
        return {}
    normalized = {}
    for raw_root, raw_spec in data.items():
        root = str(raw_root or "").strip().lower()
        if not root or not isinstance(raw_spec, dict):
            continue
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

        raw_argument_limit = raw_spec.get("argument_limit")
        argument_limit = raw_argument_limit if isinstance(raw_argument_limit, int) and raw_argument_limit > 0 else None

        for raw_sub in raw_spec.get("subcommands", []) or []:
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

        raw_pipe_spec = raw_spec.get("pipe")
        pipe_spec: dict[str, object] = raw_pipe_spec if isinstance(raw_pipe_spec, dict) else {}
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

        normalized[root] = {
            "flags": flags,
            "expects_value": expects_value,
            "arg_hints": arg_hints,
            "argument_limit": argument_limit,
            "pipe_command": pipe_command,
            "pipe_insert_value": pipe_insert_value,
            "pipe_label": pipe_label,
            "pipe_description": pipe_description,
            "examples": examples,
        }
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

        seen_examples = {item["value"].lower() for item in current.get("examples", []) if isinstance(item, dict)}
        for ex in spec.get("examples", []) or []:
            key = str(ex["value"]).lower()
            if key in seen_examples:
                continue
            seen_examples.add(key)
            current.setdefault("examples", []).append(ex)
    return merged


def load_autocomplete_context():
    """Read the unified autocomplete YAML and return structured root-aware suggestions."""
    base = _load_autocomplete_config(AUTOCOMPLETE_CONTEXT_FILE)
    root, ext = os.path.splitext(AUTOCOMPLETE_CONTEXT_FILE)
    local = _load_autocomplete_config(f"{root}.local{ext}")
    return _merge_autocomplete_context(base.get("context", {}), local.get("context", {}))


def _spread_sensitive_smoke_commands(commands: list[str]) -> list[str]:
    """De-clump bursty network lookups without changing source ownership/order.

    The smoke corpus should still be *collected* in source order from
    autocomplete examples and workflow steps, but some roots are more likely to
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
    """Return the user-facing smoke-test corpus from autocomplete examples and workflows."""
    commands = []
    seen = set()

    for spec in load_autocomplete_context().values():
        if not isinstance(spec, dict):
            continue
        for example in spec.get("examples") or []:
            if not isinstance(example, dict):
                continue
            command = str(example.get("value") or "").strip()
            if not command or command in seen:
                continue
            seen.add(command)
            commands.append(command)

    for workflow in load_all_workflows():
        if not isinstance(workflow, dict):
            continue
        for step in workflow.get("steps") or []:
            if not isinstance(step, dict):
                continue
            command = str(step.get("cmd") or "").strip()
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


def _is_denied(command: str, deny_entries: list[str]) -> bool:
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


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Return (allowed, reason). Blocks if any chained segment isn't on the allowlist,
    or if the raw input contains shell operators or references to protected paths.
    Deny prefixes (lines starting with ! in allowed_commands.txt) take priority over
    allow prefixes, letting operators block specific flags on an otherwise-allowed command."""
    allowed, denied = load_allowed_commands()
    if allowed is None:
        return True, ""  # no file or empty file = unrestricted

    synthetic_postfilter, postfilter_error = parse_synthetic_postfilter(command)
    if postfilter_error:
        return False, postfilter_error
    command_to_validate = synthetic_postfilter["base_command"] if synthetic_postfilter else command

    # Block shell chaining/redirection operators outright when restrictions are active
    if not synthetic_postfilter and SHELL_CHAIN_RE.search(command):
        return False, "Shell operators (&&, |, ;, >, etc.) are not permitted."

    if _PATH_DATA_RE.search(command_to_validate):
        return False, "Access to /data is not permitted."
    if _PATH_TMP_RE.search(command_to_validate):
        return False, "Access to /tmp is not permitted."
    if _LOOPBACK_RE.search(command_to_validate):
        return False, "Connections to the local host are not permitted."

    cmd_lower = command_to_validate.strip().lower()

    # Deny prefixes take priority — checked before allow list
    if denied and _is_denied(command_to_validate.strip(), denied):
        return False, f"Command not allowed: '{command.strip()}'"

    if not any(cmd_lower == prefix or cmd_lower.startswith(prefix + " ")
               for prefix in allowed):
        return False, f"Command not allowed: '{command.strip()}'"

    return True, ""


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
