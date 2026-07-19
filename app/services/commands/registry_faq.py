# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""FAQ content and rendering helpers for command discovery."""

from collections.abc import Callable
from copy import deepcopy
import html
import re

import config as app_config

FAQ_CATEGORY_ORDER = (
    "Getting started",
    "Core features",
    "Privacy & sessions",
    "Keyboard & controls",
    "Tool-specific behavior",
    "Limits & retention",
    "Other",
)
FAQ_CATEGORY_OTHER = "Other"


def _feature_enabled(feature, cfg=None):
    normalized = str(feature or "").strip().lower()
    if not normalized:
        return True
    active_cfg = app_config.CFG if cfg is None else cfg
    if normalized == "tour":
        return bool(active_cfg.get("tour_enabled", True))
    if normalized == "workspace":
        return bool(active_cfg.get("workspace_enabled", False))
    if normalized in {"interactive_pty", "pty"}:
        return bool(active_cfg.get("interactive_pty_enabled", False))
    return True


def _faq_entry_enabled(item, cfg=None):
    feature = item.get("feature") or item.get("requires_feature")
    if feature is None:
        return True
    if isinstance(feature, (list, tuple, set)):
        return all(_feature_enabled(value, cfg) for value in feature)
    return _feature_enabled(feature, cfg)


def _project_source_url(project_source=None):
    return project_source or app_config.PROJECT_SOURCE


def _normalize_faq_category(value):
    text = str(value or "").strip()
    if text in FAQ_CATEGORY_ORDER:
        return text
    return FAQ_CATEGORY_OTHER


def _normalize_faq_entry(entry):
    normalized = dict(entry)
    normalized["category"] = _normalize_faq_category(normalized.get("category"))
    return normalized


def _builtin_faq(app_name="darklab_shell", project_source=None, cfg=None):
    source_url = _project_source_url(project_source)
    entries = [
        {
            "question": "What is this?",
            "category": "Getting started",
            "answer": (
                f"{app_name} is a lightweight web interface for running network diagnostic and vulnerability "
                "scanning commands against remote endpoints, with output streamed in real time. It's designed "
                "for testing and troubleshooting remote hosts. "
                "It uses the Nmap Security Scanner for supported network scans: https://nmap.org/. "
                "For details, the project's README, supporting documentation, and source code for this release "
                f"are available in the darklab_shell GitLab repository: {source_url}"
            ),
            "answer_html": (
                f"{app_name} is a lightweight web interface for running network diagnostic and vulnerability "
                "scanning commands against remote endpoints, with output streamed in real time. It's designed for "
                "testing remote hosts with DNS, port, route, HTTP, and web app checks, without SSH access. For details, "
                "the project's README, supporting documentation, and source code for this release are available in the "
                f"<a href=\"{html.escape(source_url, quote=True)}\" target=\"_blank\" "
                "rel=\"noopener noreferrer\" class=\"faq-link\">darklab_shell GitLab repository</a>. "
                "Supported network scans use the <a href=\"https://nmap.org/\" target=\"_blank\" "
                "rel=\"noopener noreferrer\" class=\"faq-link\">Nmap Security Scanner</a>."
            ),
        },
        {
            "question": "What commands are allowed?",
            "category": "Getting started",
            "answer": (
                "Open the Command Registry from the menu, or run commands, commands --external, "
                "or commands info <command> in the web shell."
            ),
            "ui_kind": "allowed_commands",
        },
        {
            "question": "What are session Files?",
            "category": "Core features",
            "feature": "workspace",
            "answer": (
                "Files are app-managed, session-scoped text files for commands that need small inputs or outputs. "
                "Use the Files panel or run file help to create, view, edit, "
                "download, copy, move, touch, or delete files."
            ),
            "answer_html": (
                "Files are app-managed, session-scoped text files for commands that need small "
                "inputs or outputs. Use the <strong>Files</strong> panel or run "
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"file help\">file help</span> "
                "to create, view, edit, download, copy, move, touch, or delete files.<br><br>"
                "Commands can use explicitly enabled file flags, <code>command &gt; file</code>, "
                "<code>command &gt;&gt; file</code>, or a final <code>| tee file</code> sink. Other redirection remains blocked. "
                "Files stay scoped to the current browser session or named session token."
            ),
        },
        {
            "question": "What are Projects?",
            "category": "Core features",
            "answer": (
                "Projects collect related runs, targets, findings, artifacts, labels, notes, and "
                "evidence packages into one workspace."
            ),
            "answer_html": (
                "<strong>Projects</strong> collect related work into one workspace so an investigation "
                "doesn't have to live only in scattered history rows. Open the Projects modal from the "
                "rail or mobile menu, press <code>Alt+P</code>, or use "
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"project help\">project help</span> "
                "in the shell.<br><br>"
                "An active project can link new runs automatically, track targets discovered from typed "
                "command inputs and target-list files, organize run findings and file artifacts, compare "
                "runs, and build evidence packages. Project, run, target, finding, artifact, file, and "
                "package rows can carry labels and notes so the context stays attached to the work."
            ),
        },
        {
            "question": "What is Interactive PTY mode?",
            "category": "Core features",
            "feature": "interactive_pty",
            "answer": (
                "Interactive PTY mode opens supported interactive tools in a terminal-style window "
                "where you can type, resize the view, and save the finished output to history."
            ),
            "answer_html": (
                "<strong>Interactive PTY</strong> mode is for tools that work better in a live "
                "terminal-style view instead of plain scrolling output. Commands such as "
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"nc --interactive darklab.sh 80\">"
                "nc --interactive</span>, "
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"telnet --interactive darklab.sh 80\">"
                "telnet --interactive</span>, "
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"mtr --interactive darklab.sh\">"
                "mtr --interactive</span>, "
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"ffuf --interactive "
                "-u https://darklab.sh/FUZZ -w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt\">"
                "ffuf --interactive</span>, "
                "and "
                "<span class=\"allowed-chip faq-chip\" data-faq-command=\"masscan --interactive darklab.sh -p80,443\">"
                "masscan --interactive</span> "
                "open a focused terminal window where you can type into the tool, resize the view, "
                "and close or kill the run when you're done.<br><br>"
                "When the command finishes, its captured output is saved like a normal run, so it can "
                "still appear in history, search results, findings, and Projects when applicable."
            ),
        },
        {
            "question": "How do I save or share my results?",
            "category": "Core features",
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
            "category": "Core features",
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
            "category": "Privacy & sessions",
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
            "category": "Privacy & sessions",
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
            "category": "Getting started",
            "answer": (
                "The shell supports built-in commands plus a narrow set of built-in pipe helpers: grep, head, "
                "tail, wc -l, jq, sort, uniq, and tee. For the full list, run commands --built-in in the web shell."
            ),
            "answer_html": (
                "This shell includes two kinds of built-in behavior:<br><br>"
                "<strong>Built-in commands</strong> such as <code>status</code>, "
                "<code>history</code>, <code>retention</code>, <code>shortcuts</code>, "
                "<code>limits</code>, and <code>faq</code>. For a full list, run "
                "<code>commands --built-in</code>. These are provided directly by the shell.<br><br>"
                "<strong>Commands with built-in pipe support</strong> let you trim output with "
                "supported pipe helpers, for example <code>command | grep pattern</code>, "
                "<code>command | head -n 20</code>, <code>command | head -20</code>, "
                "<code>command | tail -n 20</code>, <code>command | tail -20</code>, "
                "<code>command | wc -l</code>, <code>command | jq -r .host</code>, <code>command | sort -rn</code>, or "
                "<code>command | uniq -c</code>. These helpers can also be chained together, "
                "for example <code>command | grep pattern | wc -l</code>. When Files are enabled, "
                "<code>command &gt; file</code> saves output quietly, <code>command &gt;&gt; file</code> appends it, and "
                "<code>command | tee file</code> also keeps it visible.<br><br>"
                "General shell piping, arbitrary chaining, and raw redirection remain blocked."
            ),
        },
        {
            "question": "How do I stop a running command?",
            "category": "Keyboard & controls",
            "answer": "Use the Kill button shown or press Ctrl+C while a command is running.",
            "answer_html": (
                "Click the <strong class=\"faq-kill-verb\">■ Kill</strong> button that appears "
                "while a command is running or press <code>Ctrl+C</code>. This sends SIGTERM to the "
                "entire process group on the server, stopping it immediately."
            ),
        },
        {
            "question": "Are there keyboard shortcuts?",
            "category": "Keyboard & controls",
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
            "category": "Keyboard & controls",
            "answer": "Use the mobile menu in the top-right corner.",
            "answer_html": (
                "On small screens the header buttons are replaced by a <strong>☰</strong> menu in the "
                "top-right corner. Tap it to access search, run history, line numbers, timestamps, "
                "theme, and this FAQ."
            ),
        },
        {
            "question": "How do I rename a tab?",
            "category": "Keyboard & controls",
            "answer": "Double-click the tab label, then press Enter or click away to confirm.",
            "answer_html": (
                "Double-click the tab label to edit it inline. Press <strong>Enter</strong> or click "
                "anywhere outside to confirm, or <strong>Escape</strong> to cancel. Once renamed, "
                "running a command won't overwrite the label — the tab keeps your chosen name."
            ),
        },
        {
            "question": "What are the retention and limit settings for this instance?",
            "category": "Limits & retention",
            "answer": "See the live retention and limit table in the FAQ modal or run retention in the web shell.",
            "ui_kind": "limits",
        },
        {
            "question": "What do the timestamp options do?",
            "category": "Keyboard & controls",
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
            "category": "Keyboard & controls",
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
            "category": "Tool-specific behavior",
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
            "category": "Tool-specific behavior",
            "answer": (
                "Plain mtr runs are converted to --report-wide mode so the shell can show and save "
                "readable output. Use mtr --interactive when Interactive PTY is enabled for the live view."
            ),
            "answer_html": (
                "Plain <code>mtr</code> runs are converted to <code>--report-wide</code> mode so the "
                "shell can stream readable rows and save the result to history. Use "
                "<code class=\"faq-example\">mtr --interactive google.com</code> when Interactive PTY "
                "is enabled and you want the live hop table. For report mode, you can change the cycle "
                "count with <code>-c</code>, e.g. <code class=\"faq-example\">mtr -c 20 google.com</code>."
            ),
        },
        {
            "question": "Can nmap and naabu use SYN scan mode?",
            "category": "Tool-specific behavior",
            "answer": (
                "They use TCP connect mode by default. Operators on supported Linux Docker hosts can "
                "enable raw-packet scanning. Once capability checks pass, nmap and naabu can use SYN "
                "mode without Docker privileged mode; explicit connect scans still work."
            ),
            "answer_html": (
                "<code>nmap</code> and <code>naabu</code> use TCP connect mode by default. Operators on "
                "supported Linux Docker hosts can enable raw-packet scanning. Once the runtime capability "
                "checks pass, Nmap keeps its SYN default and Naabu uses SYN mode without Docker privileged "
                "mode. Explicit <code>nmap -sT</code> and <code>naabu -scan-type c</code> commands still "
                "use connect mode."
            ),
        },
    ]
    return [_normalize_faq_entry(item) for item in entries if _faq_entry_enabled(item, cfg)]

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


def load_faq(path: str, cfg=None, *, load_yaml_list_with_local: Callable[[str], list]) -> list[dict[str, object]]:
    """Read custom FAQ entries and return normalized browser payloads."""
    data = load_yaml_list_with_local(path)
    result: list[dict[str, object]] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("question") or not item.get("answer"):
            continue
        if not _faq_entry_enabled(item, cfg):
            continue
        entry: dict[str, object] = {"question": str(item["question"]), "answer": str(item["answer"])}
        if item.get("answer_html"):
            entry["answer_html"] = str(item["answer_html"])
        else:
            entry["answer_html"] = render_faq_markup(str(entry["answer"]))
        entry["category"] = _normalize_faq_category(item.get("category"))
        result.append(entry)
    return result


def load_all_faq(
    path: str,
    app_name: str = "darklab_shell",
    project_source=None,
    cfg=None,
    *,
    load_yaml_list_with_local: Callable[[str], list],
) -> list[dict[str, object]]:
    """Return the built-in FAQ entries followed by any custom FAQ entries."""
    builtins: list[dict[str, object]] = [dict(item) for item in deepcopy(_builtin_faq(app_name, project_source, cfg))]
    return [
        *builtins,
        *load_faq(path, cfg, load_yaml_list_with_local=load_yaml_list_with_local),
    ]
