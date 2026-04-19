# Feature Details

Full per-feature reference for darklab shell. See the [README](README.md) for the quick summary and the [Quick Start](README.md#quick-start).

---

## Contents

- [Shell Prompt](#shell-prompt)
- [Recent Commands](#recent-commands)
- [Autocomplete](#autocomplete)
- [Reverse-History Search](#reverse-history-search)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Output Streaming and Display](#output-streaming-and-display)
- [Kill Running Processes](#kill-running-processes)
- [Status HUD](#status-hud)
- [Built-In Pipe Support](#built-in-pipe-support)
- [Output Search](#output-search)
- [Copy, Save, and Export](#copy-save-and-export)
- [Tabs & Run History](#tabs--run-history)
- [Guided Workflows](#guided-workflows)
- [Permalinks](#permalinks)
- [Share Redaction](#share-redaction)
- [Mobile Shell](#mobile-shell)
- [Built-In Commands](#built-in-commands)
- [Command Allowlist](#command-allowlist)
- [Wordlists](#wordlists)
- [Welcome Animation](#welcome-animation)
- [Custom FAQ](#custom-faq)
- [Theme Selector](#theme-selector)
- [Options Modal](#options-modal)
- [Persistence & Retention](#persistence--retention)
- [Session Tokens](#session-tokens)
- [Security and Process Isolation](#security-and-process-isolation)
- [Structured Logging](#structured-logging)
- [Operator Diagnostics](#operator-diagnostics)
- [Related Docs](#related-docs)

---

## Shell Prompt

**Purpose:** terminal-style prompt flow that mirrors real shell transcript semantics for command echo, blank-Enter, and Ctrl+C handling.

**Behavior:**

- Submitted commands are echoed inline above their output so the transcript reads like a real terminal session.
- Pressing **Enter** on a blank prompt adds a fresh prompt line without calling `/run`.
- **Ctrl+C** is context-aware: while a command is running it opens a kill confirmation dialog; while the tab is idle it drops a new prompt line.
- After highlighting transcript text on desktop, **ArrowUp**, **ArrowDown**, **Enter**, and **Ctrl+R** return control to the prompt without clearing the selection.
- While a command is running the live input prompt hides so output has full focus; once the command completes the prompt reappears immediately.

**Limits:** prompt flow is per-tab; selection-preserving key routing applies to desktop only (mobile uses native touch selection).

**Configuration:** none — prompt semantics are not user-tunable.

**Related files:** `app/static/js/controller.js` (composer + keypress dispatch), `app/static/js/runner.js` (echo on submit + prompt hide/show around `/run`).

---

## Recent Commands

**Purpose:** quick access to the most recent commands from the current session without opening the full history drawer.

**Behavior:**

- Desktop rail's `Recent` section renders clickable chips that load a command into the prompt when tapped.
- Mobile surfaces a persistent `Recent` peek row between the transcript and the composer showing a count plus a one-line preview; tapping opens a full pull-up recents sheet.
- The mobile recents sheet lists recent runs as tappable rows with per-row copy / permalink / restore actions, search, filter chips (root / exit / date / starred), and a clear-all control.
- Both surfaces update live as commands are run.

**Limits:** the most recent distinct commands only; hidden entirely until there is at least one command in history; entry count capped at `recent_commands_limit`.

**Configuration:** `recent_commands_limit` in `config.yaml` (default 8).

**Related files:** `app/static/js/shell_chrome.js` (desktop rail), `app/static/js/mobile_chrome.js` (mobile peek + sheet), `app/conf/config.yaml`.

---

## Autocomplete

**Purpose:** shell-like completion that expands to the longest shared prefix, cycles matches, and surfaces context-aware flag and value hints per tool.

**Behavior:**

- Suggestions load from `conf/autocomplete.yaml` at page load and match what the user types; the matched portion is highlighted in green.
- The dropdown opens below the prompt when there is room and flips above when space is tight, preserving top-to-bottom keyboard navigation order.
- `Tab` expands to the longest shared prefix, then cycles matches; `Shift+Tab` cycles backward; `Enter` accepts the highlighted match or runs the command if none is selected.
- After a known command root, the dropdown switches to contextual flag/value hints for that tool; after `|`, it switches into the built-in pipe stage (`grep`, `head`, `tail`, `wc -l`, `sort`, `uniq`).
- Already-used singleton-style flags are suppressed from contextual suggestions.

**Limits:** completions come only from the static YAML file(s); there is no shell introspection, no `--help` parsing, and no fuzzy matching beyond prefix + expand.

**Configuration:** `conf/autocomplete.yaml` (plus optional `conf/autocomplete.local.yaml`). Reloaded by the browser at page load — no server restart needed.

**Related files:** `app/static/js/autocomplete.js`, `app/conf/autocomplete.yaml`.

**Keyboard controls:**

| Key | Action |
|-----|--------|
| **↑ / ↓** | Navigate through suggestions |
| **Tab** | Expand to the longest shared prefix, then cycle suggestions forward |
| **Shift+Tab** | Cycle suggestions backward |
| **Enter** | Accept highlighted suggestion, or run the command if none selected |
| **Escape** | Dismiss the dropdown |

**Structured context format**

`conf/autocomplete.yaml` uses a single `context` key for root-aware flag and value hints:

```yaml
context:
  nmap:
    flags:
      - value: -sV
        description: Service/version detection
```

Inside `context`, each command root can define:

```yaml
nmap:
  flags:
    - value: -sV
      description: Service/version detection
    - value: -Pn
      description: Skip host discovery
  expects_value:
    - -p
  arg_hints:
    "-p":
      - value: "<ports>"
        description: Comma-separated ports or ranges
    "__positional__":
      - value: "<target>"
        description: Hostname, IP, or CIDR
```

How the keys work:

- `flags`
  - suggestions shown when the current token is a flag position for that command root, for example `nmap -`
- `expects_value`
  - flags whose next token should be treated as a value slot rather than another flag slot
  - example:
    - `curl -o <cursor>` will use the `-o` value hints instead of showing more curl flags
- `arg_hints`
  - controls what is shown after a specific token has been typed and accepted
  - each key under `arg_hints` is one of:
    - a real flag like `-o`, `-u`, or `-severity` — shows value suggestions after that flag
    - a flag mapped to an empty list `[]` — collapses the dropdown after that token (see terminal flags below)
    - the special key `__positional__`

`__positional__` means:
- use these hints when the user is typing a normal non-flag argument for that command and no more specific flag-value hint is taking priority
- these hints are also shown alongside flags when the user is sitting at `command `, so commands like `nmap ` can surface both `-sV` and `<target>` in the same dropdown
- examples:
  - `dig <cursor>` can suggest `<domain>`
  - `nmap <cursor>` can suggest `<target>`
  - `ffuf <cursor>` can suggest a target URL placeholder

More examples:

```yaml
curl:
  flags:
    - value: -H
      description: Add request header
    - value: -o
      description: Write body to file
  expects_value:
    - -H
    - -o
  arg_hints:
    "-H":
      - value: "Authorization: Bearer <token>"
        description: Example auth header
    "-o":
      - value: "/dev/null"
        description: Discard body and keep metadata
    "__positional__":
      - value: "https://"
        description: Start an HTTP or HTTPS URL
```

That means:
- `curl -` suggests curl flags
- `curl -H <cursor>` suggests header values
- `curl -o <cursor>` suggests file/value targets like `/dev/null`
- `curl <cursor>` suggests generic positional URL hints

**Terminal flags**

Map a flag to an empty list in `arg_hints` to suppress the dropdown after it is typed. This is used for flags that accept no further input — help flags, version flags, and exclusive subcommands that end the command:

```yaml
nmap:
  arg_hints:
    "-h": []          # after `nmap -h `, dropdown closes
    "-p":
      - value: "80,443"
        description: Common web ports

session-token:
  expects_value:
    - set             # `set` consumes the next token (the token value)
  arg_hints:
    "set":
      - value: "<token>"
        description: Paste a tok_... token or UUID from another device
    "generate": []    # after `session-token generate `, dropdown closes
    "clear": []
    "rotate": []
```

Do not add terminal flags to `expects_value` — that list is only for flags that genuinely consume a value argument. The empty `arg_hints` entry is sufficient on its own.

Practical authoring guidance:

- use `context` when the next useful suggestion depends on the command root or the preceding flag
- use `pipe_command: true` when that context entry should also appear after `command |`
- use `expects_value` only when the next token should be a value consumed by the preceding flag (e.g. `-p <ports>`, `-H <header>`)
- use `arg_hints["<flag>"]: []` for terminal flags and standalone subcommands so the dropdown collapses after they are typed
- use `arg_hints["__positional__"]` for unflagged arguments like hosts, URLs, domains, or CIDR targets
- prefer concrete values when prefix matching should work, and placeholders when the hint is mainly explanatory

The shipped file is intentionally small and focused. Add entries only for commands where token-aware guidance is clearly more useful than the flat whole-command list.

For built-in pipe support, the same file can also describe the narrow pipe stage:

```yaml
grep:
  pipe_command: true
  pipe_description: Filter lines by pattern
  flags:
    - value: -i
      description: Ignore case
    - value: -v
      description: Invert match
    - value: -E
      description: Extended regex

wc:
  pipe_command: true
  pipe_insert_value: "wc -l"
  pipe_label: "wc -l"
  pipe_description: Count lines
```

That means:
- `help | ` can suggest `grep`, `head`, `tail`, and `wc -l`
- `help | grep -` can suggest `-i`, `-v`, and `-E`
- `help | head -n ` or `help | tail -n ` can suggest common count values
- `help | wc ` can suggest `-l`

To update suggestions, edit `conf/autocomplete.yaml` and/or `conf/autocomplete.local.yaml`, then reload the page — no server restart needed.

---

## Reverse-History Search

**Purpose:** bash-style `Ctrl+R` search across the full session history — not just the in-memory recent-commands cache.

**Behavior:**

- `Ctrl+R` opens an interactive history search mode inline at the prompt; the dropdown does not appear until the first character is typed.
- Typing filters commands from the full session history in real time — the search queries the same server-side history the history drawer uses, so commands from earlier in the session or previous days are always reachable.
- **Enter** accepts the highlighted command and runs it immediately.
- **Tab** accepts the highlighted command without running it, leaving it editable in the prompt.
- **Ctrl+R** again cycles forward through the current matches.
- **Escape** dismisses the search and restores whatever draft was in the prompt before `Ctrl+R` was pressed.

**Limits:** results are capped at 10 entries — narrowing the query further surfaces deeper matches.

**Configuration:** none — behavior is not user-tunable.

**Related files:** `app/static/js/controller.js` (Ctrl+R keybinding + dropdown), `app/blueprints/history.py` (server-side history query).

---

## Keyboard Shortcuts

**Purpose:** app-safe chords for tab lifecycle, active-tab actions, and readline-style prompt editing, surfaced through both the `?` overlay and the `shortcuts` built-in.

**Behavior:**

- Tab chords use `Option`/`Alt` to avoid fighting browser `Ctrl`/`Cmd` bindings; terminal chords use `Ctrl` in the readline tradition.
- The `?` overlay opens from anywhere on the page (including the empty prompt); `shortcuts` prints the same reference as a text dump.
- Both surfaces read from a single canonical list via `GET /shortcuts`, so they cannot drift.

**Limits:** browser-native combos like `Cmd+T`, `Cmd+W`, and `Ctrl+Tab` are optional fallbacks only — browser interception is inconsistent across environments, especially on macOS.

**Configuration:** none — the chord list is defined in `app/fake_commands.py` and not user-tunable.

**Related files:** `app/static/js/app.js` (`handleTabShortcut` / `handleChromeShortcut` / `handleActionShortcut`), `app/static/js/controller.js` (document keydown cascade), `app/fake_commands.py` (`_CURRENT_SHORTCUTS`), `app/blueprints/content.py` (`GET /shortcuts`).

Shipped app-safe shortcuts:

| Shortcut | Action | Notes |
|----------|--------|-------|
| `Option+T` (`Alt+T`) | New tab | Preferred app-safe binding |
| `Option+W` (`Alt+W`) | Close current tab | Avoids fighting browser `Ctrl/Cmd+W` |
| `Option+ArrowRight` (`Alt+ArrowRight`) | Next tab | |
| `Option+ArrowLeft` (`Alt+ArrowLeft`) | Previous tab | |
| `Option+Tab` (`Alt+Tab`) | Next tab (Shift reverses) | Arrow and Tab are interchangeable |
| `Option+1` ... `Option+9` (`Alt+1` ... `Alt+9`) | Jump to tab 1 ... 9 | |
| `Enter` / `Escape` in kill confirmation | Confirm / cancel kill | Mirrors modal button intent |
| `Option+P` (`Alt+P`) | Create share snapshot for active tab | |
| `Option+Shift+C` (`Alt+Shift+C`) | Copy active tab output | Kept distinct from terminal `Ctrl+C` |
| `Ctrl+L` | Clear current tab output | Shell-style convenience |
| `Ctrl+A` | Move cursor to start of line | Readline-style editing |
| `Ctrl+E` | Move cursor to end of line | Readline-style editing |
| `Ctrl+U` | Delete from cursor to start of line | Readline-style editing |
| `Ctrl+K` | Delete from cursor to end of line | Readline-style editing |
| `Ctrl+W` | Delete one word to the left | Readline-style editing |
| `Option+B` / `Option+F` (`Alt+B` / `Alt+F`) | Move backward / forward by word | Readline-style editing |
| `Ctrl+R` | Reverse-history search | Type to filter; Enter runs; Tab accepts without running; Escape restores draft |

Browser-native combos like `Cmd+T`, `Cmd+W`, and `Ctrl+Tab` are intentionally treated as optional fallbacks rather than the primary contract because browser interception is inconsistent across environments, especially on macOS browsers.

The same shortcut reference is surfaced in two places in the shell:

- press `?` from anywhere on the page to open a dedicated transparent keyboard-shortcuts overlay — including from the command prompt itself when it is empty. Once any text is present in the prompt (or any other input), `?` types normally so args like `curl "…?foo=bar"` are not interfered with. The handler also skips modifier chords (`Ctrl` / `Meta` / `Alt`) and the welcome-animation active state
- run `shortcuts` in the shell to print the same reference as a text dump inside the current tab

Both surfaces read from the same canonical list in the backend (exposed to the browser via `GET /shortcuts`), so they cannot drift. The overlay lists the `?` binding itself as the first entry so the shortcut is self-documenting.

---

## Output Streaming and Display

**Purpose:** low-latency SSE streaming with a live tail, per-line prefix toggles (timestamps and line numbers), and an explicit stall notice when the connection silently drops.

**Behavior:**

- Command output arrives line-by-line over SSE; fast commands batch flushes, slow scans stream each line as it arrives.
- The output view follows the live tail automatically; scrolling away surfaces a tab-scoped jump-to-live / jump-to-bottom helper that disappears once the tail is rejoined.
- A live elapsed run-timer sits next to the status pill while a command runs; the final elapsed time is recorded in the exit line.
- Timestamps (elapsed or clock) and line numbers are independently toggleable from the tabbar controls (or the mobile menu); both are rendered from shared per-line prefix metadata so toggling updates existing output in place without re-fetching.
- When the SSE connection silently drops mid-run, the shell detects the stall and shows an inline notice instead of waiting indefinitely.

**Limits:** stall detection fires after 45 seconds of silence per tab; each tab has its own stall timeout so concurrent runs don't interfere.

**Configuration:** timestamp and line-number preferences persist in `localStorage`; both are off by default.

**Related files:** `app/static/js/runner.js` (SSE consumer + stall detection), `app/static/js/output.js` (prefix rendering + live-tail helper), `app/blueprints/run.py` (server-side SSE generator).

---

## Kill Running Processes

**Purpose:** operator-initiated termination of a running command via `SIGTERM` to the full process group, with a confirmation step to guard against accidental interrupts.

**Behavior:**

- Each tab shows a **■ Kill** button while a command is running; clicking it opens a confirmation dialog before sending `SIGTERM` to the full process group.
- `Enter` confirms and `Escape` cancels the dialog, matching the button labels.
- `Ctrl+C` routes through the same confirmation flow while a command is running.

**Limits:** kill dispatches from any Gunicorn worker — PID lookup goes through Redis so the request doesn't have to hit the worker that started the process. See [DECISIONS.md](DECISIONS.md) `Multi-worker Process Killing via Redis`.

**Configuration:** none — the kill path is not user-tunable.

**Related files:** `app/static/js/runner.js` (client-side kill + confirmation dialog), `app/blueprints/run.py` (`POST /kill`), `app/process.py` (`pid_register` / `pid_pop`).

---

## Status HUD

**Purpose:** a persistent desktop status surface that consolidates run state, connection health, session identity, and environment telemetry into one scanable row without displacing the terminal.

**Behavior:**

- The bottom bar renders eleven live pills on desktop: the left cluster covers run state, connection, and identity; the right cluster carries the output actions (share, copy, save, clear, kill).
- Pills start with a muted `—` placeholder at page load and transition to live values on the first poll.
- Server state is polled via `GET /status` every 15 seconds; uptime is interpolated locally between polls so the pill never looks frozen; the UTC clock ticks once per second in the browser.
- Latency is measured client-side with `performance.now()` around the fetch call.
- On narrow desktop widths the pill row falls back to horizontal overflow scrolling so the right-side HUD actions never get pushed off-screen.
- Mobile hides the HUD entirely; per-tab status and exit codes remain visible inline next to the prompt echo, and the run-notifications toggle in the Options modal covers the background-watch use case.

**Limits:** `/status` always returns 200 even when a component is degraded (reports `"down"` for that component) so HUD polling never flaps the UI or triggers SSE reconnect logic; `/health` remains the load-balancer contract and still returns 503 on degradation.

**Configuration:** none — the HUD is not user-tunable. Run notifications (a related cross-tab feature) are configured from the Options modal.

**Related files:** `app/static/js/shell_chrome.js` (HUD build + polling), `app/blueprints/assets.py` (`GET /status`).

**Pill reference:**

| Pill | Source | Notes |
|------|--------|-------|
| **STATUS** | Active tab's run state (`running` / `ok` / `fail` / `killed` / `idle`) | Coloured pill identical to the inline tab status dot |
| **LAST EXIT** | Exit code of the most recent finished run in any tab | `0` green, nonzero red, killed amber, `—` muted when no run has finished yet |
| **RUNS** | Number of running tabs over total tabs | Amber while any tab is running, muted when no tabs are active |
| **TRANSPORT** | SSE connection state | Auto-managed by the SSE reconnect logic |
| **LATENCY** | Round-trip time to `/status` in ms | Green `<150ms`, amber `<500ms`, red `>=500ms` |
| **MODE** | Current shell mode indicator | Reserved for future sandbox/lockdown modes |
| **SESSION** | Active session identity | `ANON` (muted) for UUID sessions, masked `tok_XXXX••••••••` (green) for named tokens — see [Session Tokens](#session-tokens) |
| **UPTIME** | Server process uptime | Returned by `/status` and ticked client-side between polls so the pill never looks frozen |
| **CLOCK** | Wall-clock `HH:MM:SS UTC` | Ticks every second in the browser |
| **DB** | SQLite connection state | `ONLINE` green, `OFFLINE` red |
| **REDIS** | Redis connection state | `ONLINE` green, `OFFLINE` red, `N/A` muted when no Redis is configured |

---

## Built-In Pipe Support

**Purpose:** a narrow app-native pipe stage (`grep`, `head`, `tail`, `wc -l`, `sort`, `uniq`) that keeps common post-filter use cases available without enabling general shell piping or redirection.

**Behavior:**

- One supported pipe stage per command; the filtered view is what appears in the terminal, history, permalinks, and exports for that run.
- Autocomplete understands the narrow pipe stage and can guide `grep`, `head`, `tail`, `wc -l`, `sort`, and `uniq` after `command |`.
- Arbitrary pipes, chaining, and redirection remain blocked at the command-validation layer.

**Limits:** only the six stages above are recognised. Combinable flags are supported within a stage (e.g. `sort -rn`) but stages cannot be chained.

**Configuration:** none — the supported stage set is hard-coded in `app/commands.py`.

**Related files:** `app/commands.py` (pipe-stage parser + validator), `app/blueprints/run.py` (applies the pipe filter to streamed output).

**Supported pipe forms:**

- `command | grep pattern`
- `command | grep -i pattern`
- `command | grep -v pattern`
- `command | grep -E pattern`
- `command | head`
- `command | head -n 20`
- `command | tail`
- `command | tail -n 20`
- `command | wc -l`
- `command | sort`
- `command | sort -r`
- `command | sort -n`
- `command | sort -u`
- `command | sort -rn` (flags combinable)
- `command | uniq`
- `command | uniq -c`

---

## Output Search

**Purpose:** in-transcript text search over the current tab output with case and regex toggles and keyboard navigation between matches.

**Behavior:**

- Click **⌕ search** in the tabbar (on the right, alongside the timestamp and line-number toggles) — or press `Alt+S` — to open the search bar above the output.
- Matches are highlighted in amber; the current match is highlighted brighter.
- Use **↑ / ↓** buttons or **Enter** / **Shift+Enter** to navigate between matches; **Escape** closes the search bar.
- Case-sensitivity (**Aa**) and regex mode (**.\***) toggles sit between the input and the match counter; both re-run the search immediately when clicked.

**Limits:** search scope is the active tab's rendered transcript only — not history from other tabs, not the full server-side run history. Invalid regex patterns render `invalid regex` instead of throwing.

**Configuration:** none — toggle state is not persisted across page reloads.

**Related files:** `app/static/js/search.js`, `app/static/js/shell_chrome.js` (tabbar search toggle).

**Toggle reference:**

| Button | Default | Behavior |
|--------|---------|-----------|
| **Aa** | off | Case-sensitive matching — when off, search is case-insensitive |
| **.\*** | off | Regular expression mode — when on, the search term is treated as a JavaScript regex; an invalid pattern shows `invalid regex` instead of throwing |

---

## Copy, Save, and Export

**Purpose:** surface consistent copy-to-clipboard and download-output actions (`txt` / `html` / `pdf`) across the desktop HUD, the mobile menu, and the permalink page.

**Behavior:**

- **Copy** copies the full plain-text output to the clipboard.
- **save ▾** is a dropdown with three export formats:
  - **txt** — plain-text file with a timestamped filename.
  - **html** — themed HTML file with ANSI colors preserved, renders correctly in a browser without the shell; fonts and theme colors are inlined so the file is fully self-contained.
  - **pdf** — themed PDF rendered entirely in the browser via jsPDF, no server round-trip; includes the app header, command, exit-status badge, timestamp, and full ANSI output.
- The same `save ▾` dropdown is available on the desktop HUD bar, the permalink page header, and the mobile menu, so the export experience is consistent across all surfaces.

**Limits:** local exports (txt, html, pdf) produce unredacted output — they show the true command output as it appeared in the terminal. Redaction is scoped exclusively to the permalink share flow.

**Configuration:** none — export formats and filename shape are not user-tunable.

**Related files:** `app/static/js/tabs.js` (per-tab save menu), `app/static/js/shell_chrome.js` (HUD save menu), `app/static/js/export_html.js` (shared HTML renderer), `app/static/js/export_pdf.js` (jsPDF renderer), `app/templates/permalink.html` (permalink save menu).

---

## Tabs & Run History

**Purpose:** multi-tab workspace with per-session run history, full-text search over commands and output, starring, and reload-safe reconnection to in-flight runs.

**Behavior:**

- Each command runs in the active tab; the **+** button opens additional tabs for side-by-side sessions. Tabs show a status dot (amber running, green success, red failed/killed) and label themselves from the last command run. Double-click to rename, drag to reorder, tab-scroll arrows when more tabs are open than fit the window width. Draft input is preserved per tab.
- The **⧖ history** button opens a slide-out drawer listing the last 50 completed runs with timestamps and exit codes. Click an entry to load its output into a new tab with the command shown as a styled prompt line. Each row has a toggleable **star** plus **copy** / **permalink** / **delete** actions. Starred runs list before unstarred ones regardless of age. Star state persists across sessions in `localStorage` keyed by command text.
- When full-output persistence is enabled, the history drawer's permalink points at the complete saved artifact; loading into a tab still uses the capped preview and shows a notice linking to the permalink if truncated. The active tab's **share snapshot** action creates a separate `/share/<id>` snapshot and can optionally redact before saving.
- The **delete all** button (history drawer + mobile recents sheet) prompts **Delete all** / **Delete Non-Favorites** / **Cancel** to separate destructive deletion from starred-only cleanup.
- If the page reloads mid-run, the shell restores a running placeholder tab with the kill action available, polls for completion, and swaps into the saved run output when it lands in history. Non-running tabs restore separately from `sessionStorage` with labels, transcript previews, statuses, and draft input preserved; restored completed tabs remount a live prompt immediately.

**Limits:** tab count capped by `max_tabs`; history drawer shows the last 50 completed runs only (older runs remain searchable via FTS); live output cannot be replayed after the SSE stream has ended (only persisted run output reappears after reload).

**Configuration:** `max_tabs` in `config.yaml` (default 8; `0` for unlimited).

**Related files:** `app/static/js/tabs.js` (tab lifecycle + drag + rename), `app/static/js/history.js` (history drawer + search UI), `app/blueprints/history.py` (history API + FTS queries), `app/database.py` (SQLite schema + FTS5 trigger wiring).

**Full-text search:** the history drawer supports full-text search across command text and stored run output, plus filters for command root, exit status, recent date range, and starred-only. The search field placeholder reads "search commands and output". Search is backed by a SQLite FTS5 virtual table (`runs_fts`) indexed on `command` and `output_search_text`. When full-output persistence is enabled, `output_search_text` is populated from the complete gzip artifact so early lines of long runs stay reachable; otherwise it falls back to the capped preview window. On mobile, advanced filters stay behind a dedicated `filters` toggle to preserve result space, the command-root field uses app-owned autocomplete, and row actions keep the drawer open so you can work through multiple entries without repeated reopen churn.

On mobile, the **☰** menu in the top-right header opens a bottom-sheet that groups session-scoped actions (search, line numbers, timestamps) and overlays (history, workflows, options, theme, FAQ, diag) — see the Mobile Shell section below for the full layout.

---

## Guided Workflows

**Purpose:** curated multi-step diagnostic sequences (DNS, TLS, HTTP, reachability, email) that load one command at a time into the prompt so the operator can run and inspect each step in turn.

**Behavior:**

- Workflows are listed in the **Workflows** panel on desktop and behind the mobile ☰ menu; opening one reveals its individual command steps.
- Clicking a step pre-fills the prompt with its `cmd` — nothing runs automatically, so the operator inspects and edits each step before pressing Run.
- Each step can show a short `note` explaining what the command checks.
- Built-in workflows cover DNS (`dig` A/NS/MX, public resolver comparison, delegation trace), TLS/HTTPS (`curl`, `openssl s_client`, `testssl`), HTTP triage (redirect-following curl, verbose curl, wget spider), quick reachability (`ping`, `nc`, fast `nmap`), and email server checks (MX/TXT record checks, SMTP port probes).
- Custom workflows can be added to `conf/workflows.yaml`; the file is re-read on every request so edits take effect without a restart.

**Limits:** step commands still run through the allowlist — a workflow step is only usable if its `cmd` is permitted by `allowed_commands.txt`.

**Configuration:** `conf/workflows.yaml` — list of entries with the following fields:

```yaml
- title: "My Custom Check"
  description: "A brief description shown in the workflow panel."
  steps:
    - cmd: "ping -c 4 example.com"
      note: "Is the host reachable?"
    - cmd: "nmap -F example.com"
      note: "What ports are open?"
```

- `title` — required; workflow heading.
- `description` — optional; shown below the title.
- `steps` — required list; each step needs at least a `cmd`.
- `cmd` — required; loaded into the prompt when the step is clicked.
- `note` — optional; helper text shown alongside the command.

**Related files:** `app/conf/workflows.yaml` (workflow definitions), `app/static/js/shell_chrome.js` (Workflows panel rendering), `app/blueprints/content.py` (workflows API endpoint).

---

## Permalinks

**Purpose:** stable, shareable URLs for individual runs and full-tab snapshots, persisted in SQLite under the `./data` volume and subject to `permalink_retention_days`.

**Behavior:**

- **Tab snapshot** (`/share/<id>`) — **share snapshot** on any tab captures the current output and, when a full saved artifact exists, shares that full output as a snapshot. The resulting URL opens a styled HTML page with ANSI color rendering, a `save ▾` dropdown (txt, html, pdf), a **copy** button, a **view json** option, and a link back to the shell. Honors the browser's saved line-number and timestamp preferences on load. Uses the Web Share API where supported; otherwise copies the URL to the clipboard. Recommended sharing path.
- **Single run** (`/history/<run_id>`) — the permalink button in the history drawer links to an individual run. Serves the full saved artifact when persistence is enabled; otherwise the capped preview stored in SQLite. Honors saved line-number and timestamp preferences on load.
- **Full output alias** (`/history/<run_id>/full`) — backward-compatible alias to the same run permalink, kept so older links and tests continue to resolve.
- Both permalink types persist across container restarts via the `./data` SQLite volume.

**Limits:** retained for `permalink_retention_days` only; the `./data` directory is the only writable path in an otherwise read-only container (created automatically on first run).

**Configuration:** `permalink_retention_days` in `config.yaml` (default 30).

**Related files:** `app/blueprints/history.py` (share + permalink routes), `app/permalinks.py` (ID generation + storage), `app/run_output_store.py` (full-output artifact lookup), `app/templates/permalink.html` (rendered share/permalink page).

---

## Share Redaction

**Purpose:** optional masking of common secrets and infrastructure details (bearer tokens, emails, IPs, hostnames) on snapshot permalinks, with a persistent raw-vs-redacted default controlled by the Options modal.

**Behavior:**

- When creating a share snapshot, the shell can prompt whether to share raw or redacted output.
- A built-in redaction baseline masks common secrets and infrastructure details; operators can append custom regex rules on top.
- Once a raw/redacted choice is saved as the persistent default in the [Options modal](#options-modal), subsequent share actions skip the prompt and reuse that choice — whether sharing is triggered from the prompt flow or directly from the Options modal.
- Redaction applies only to the snapshot payload; the stored run history is never modified.

**Limits:** local exports (txt, html, pdf) from a tab are not redacted — redaction is scoped exclusively to the share-permalink flow.

**Configuration:** baseline rules are built in; custom regex rules extend them. The raw-vs-redacted default is stored in the Options modal.

**Related files:** `app/redaction.py` (baseline + custom rule engine), `app/blueprints/history.py` (snapshot redaction entry point), `app/static/js/tabs.js` (share snapshot prompt + default handling).

---

## Mobile Shell

**Purpose:** a dedicated touch layout with its own composer, keyboard helper row, pull-up recents sheet, and bottom-sheet menu, so the shell remains usable on phones without inheriting desktop chrome patterns that don't translate.

**Behavior:**

- **Mobile composer dock** — a visible composer with its own Run button replaces the desktop inline input.
- **Keyboard helper row** — touch targets above the keyboard provide `Home`, `End`, single-character left/right moves, word-left / word-right jumps, delete-word, and delete-line without needing a hardware keyboard.
- **Recent peek + pull-up sheet** — an idle peek row between transcript and composer shows the recent-run count plus a one-line preview; tapping it opens a full-height recents sheet with search, filter chips (root / exit / date / starred), per-row copy/permalink/restore actions, and a clear-all control.
- **Output follow** — when the keyboard opens, the active output re-sticks to the bottom so the last line stays visible.
- **Stable layout** — the mobile shell uses a normal-flow layout that avoids Firefox keyboard flash, gap, and floating-composer regressions.
- **Shared state** — desktop and mobile Run buttons stay in sync: both disable together for blank prompts and running tabs.
- The **☰** menu in the top-right header opens a bottom-sheet with two grouped sections: a **session** group (search, line numbers toggle, timestamps picker) that affects the current terminal in place, and an **overlays** group (history, workflows, options, theme, FAQ, diag) that opens full-screen surfaces. `line numbers` is a single on/off row; `timestamps` expands inline into a three-mode picker (off / elapsed / clock). The history drawer's advanced filters stay behind a dedicated `filters` toggle to preserve result space.

**Limits:** the diag entry appears only for clients whose IP matches `diagnostics_allowed_cidrs`. The mobile layout activates on touch-sized viewports — desktop browsers at narrow widths keep the desktop chrome.

**Configuration:** no mobile-specific config keys beyond `diagnostics_allowed_cidrs`; layout activates automatically on touch viewports.

**Related files:** `app/static/js/mobile_chrome.js` (mobile shell bootstrap + composer + menu), `app/static/css/mobile-shell.css` (mobile layout + composer + bottom-sheet styles), `app/templates/index.html` (mobile-shell mount points).

---

## Built-In Commands

**Purpose:** native shell helpers that provide session introspection, guidance, and guarded responses without dispatching to external binaries.

**Behavior:**

- The shell ships several categories of built-ins, each rendered as terminal-native output rather than modal UI.
- Built-ins run entirely inside the app layer, so they remain available even when the corresponding external tool does not exist in the container.

**Utility commands**

- `help`, `history`, `last`, `limits`, `retention`, `status`, `which`, `type`, `faq`, `banner`, `fortune`, `jobs`, `shortcuts`, `clear`, `autocomplete`, `ls`, `version`, and `whoami` are available in every session.
- `ps` lists currently running processes for the session (PID, TTY, STAT, START, CMD columns), or shows a `no running processes` notice when idle.

**Shell identity commands**

- `env`, `pwd`, `uname`, `uname -a`, `id`, `groups`, `hostname`, `date`, `tty`, `who`, `uptime`, `ip a`, `route`, `df -h`, and `free -h` return stable shell-style information without exposing host internals.

**Guardrail commands**

- `sudo`, `reboot`, `poweroff`, `halt`, `shutdown now`, `su`, and the exact `rm -fr /` / `rm -rf /` patterns return explicit shell responses instead of pretending to run or silently failing.

**`man` support**

- `man <allowed-command>` renders the real man page when tooling exists.
- `man <built-in-command>` shows the built-in command summary instead.

**Limits:** built-ins intentionally cover only app-owned helpers and a narrow set of shell-identity responses. They are not a general shell-emulation layer.

**Configuration:** none. The built-in command surface is defined in application code, not in operator config.

**Related files:** `app/fake_commands.py` (built-in command registry + output rendering), `app/commands.py` (dispatch + man routing), `app/conf/autocomplete.yaml` (built-in autocomplete coverage), `app/static/js/controller.js` (client-side interception for app-owned command flows like `session-token`).

---

## Command Allowlist

**Purpose:** operator-controlled set of permitted command prefixes (with deny overrides) that gates every `/run` request before dispatch.

**Behavior:**

- Every `/run` request is checked against `conf/allowed_commands.txt` before dispatch.
- Allow entries match by prefix — a prefix of `ping` permits `ping google.com`, `ping -c 4 1.1.1.1`, etc. Be as specific or broad as you like: `nmap -sT` permits only TCP connect scans while `nmap` permits any nmap invocation.
- Deny entries (`!`-prefixed) take priority over allow entries and match anywhere in the command as space-separated tokens (not as a prefix).
- Category headings (`##`) group the FAQ command chips; comments (`#`) are ignored; deny entries are not surfaced to users.
- The file is re-read on every request, so edits take effect without a restart. Deleting or emptying the file disables restrictions entirely.
- Tool names and subcommand prefixes are matched **case-insensitively**; flag names are matched **with exact case** (so `!curl -K` blocks `-K` without blocking `-k`).
- `/dev/null` exception: denied output flags (`-o`, `-O`) are permitted when their argument is `/dev/null`, allowing patterns like `curl -o /dev/null -w "%{http_code}"`.

**Limits:** prefix matching is deliberately coarse — operators must be explicit with deny entries to block flag combinations on otherwise-allowed tools. Deny matching only applies once the tool prefix matches (e.g., `!nmap -sU` only affects `nmap` commands).

**Configuration:** `conf/allowed_commands.txt`, re-read per request.

```text
## Network Diagnostics
ping
curl
dig

## Vulnerability Scanning
nmap
!nmap -sU
!nmap --script
```

- One command prefix per line.
- `#` — comment (ignored).
- `##` — category group shown in the FAQ command list.
- `!` — deny prefix (takes priority over allow entries).

**Related files:** `app/conf/allowed_commands.txt` (allowlist file), `app/command_policy.py` (allow/deny matching logic), `app/blueprints/run.py` (policy gate at the `/run` entry point).

### Deny Prefixes

Deny matching has a few extra rules worth calling out:

- Denies match a flag anywhere in the command, not just immediately after the tool (`nmap -sT -sU 10.0.0.1` is still caught by `!nmap -sU`).
- Flag names are case-sensitive so you can deny `-K` without also denying `-k`.
- The `/dev/null` exception applies to common metadata-capture patterns:

```bash
curl -o /dev/null -s -w "%{http_code}" https://example.com
wget -q -O /dev/null --server-response https://example.com
```

---

## Wordlists

**Purpose:** pre-installed SecLists corpus available to any allowlisted tool that accepts a `-w` flag, so common discovery and fuzzing tasks run without a separate setup step.

**Behavior:**

- The full [SecLists](https://github.com/danielmiessler/SecLists) collection is installed inside the container at `/usr/share/wordlists/seclists/`.
- Any allowlisted tool that accepts a `-w` flag (gobuster, ffuf, dnsenum, fierce, etc.) can reference files under this path directly.
- The list is installed at container build time; no runtime fetch is required.

**Limits:** wordlists are read-only inside the container. The corpus is not updated between builds — rebuild the image to pick up a new SecLists release.

**Configuration:** no operator-facing config; the install path (`/usr/share/wordlists/seclists/`) is fixed.

**Related files:** `Dockerfile` (SecLists install step), `app/conf/allowed_commands.txt` (tools that accept `-w`).

**Layout reference:**

```text
/usr/share/wordlists/seclists/
├── Discovery/
│   ├── Web-Content/        — directory and file names (common.txt, big.txt, DirBuster-2007_*, raft-*, etc.)
│   ├── DNS/                — subdomain names (subdomains-top1million-5000.txt, -20000.txt, -110000.txt, etc.)
│   └── Infrastructure/     — infrastructure and service discovery
├── Fuzzing/                — fuzzing payloads (XSS, SQLi, path traversal, format strings, etc.)
├── Passwords/              — password lists and common credentials
├── Usernames/              — username lists
├── Payloads/               — attack and injection payloads
└── Miscellaneous/          — other lists
```

**Commonly used lists:**

| Path | Use with |
|------|----------|
| `Discovery/Web-Content/common.txt` | Fast directory scan |
| `Discovery/Web-Content/big.txt` | Broader directory scan |
| `Discovery/Web-Content/DirBuster-2007_directory-list-2.3-big.txt` | Thorough directory scan |
| `Discovery/DNS/subdomains-top1million-5000.txt` | Fast subdomain brute-force |
| `Discovery/DNS/subdomains-top1million-20000.txt` | Broader subdomain brute-force |

---

## Welcome Animation

**Purpose:** operator-configurable first-load sequence (ASCII banner, status block, sampled commands, rotating hints) that introduces the shell without turning into permanent chrome.

**Behavior:**

- On first page load the terminal renders a staged sequence: ASCII banner → status block → sampled commands → rotating footer hints.
- Banner text is loaded from `app/conf/ascii.txt`; status labels come from `welcome_status_labels` in `config.yaml`; sampled commands and their sample output come from `app/conf/welcome.yaml`; rotating footer hints come from `app/conf/app_hints.txt`.
- On touch-sized screens the flow uses `app/conf/ascii_mobile.txt` and `app/conf/app_hints_mobile.txt` instead of the wide desktop banner/hints, keeping status and hint timing but skipping sampled commands entirely.
- Sampled welcome commands are clickable and load into the prompt without running; the `TRY THIS FIRST` badge is clickable with the same behavior as the featured command text.
- App hints rotate until interrupted unless `welcome_hint_rotations` is set to `1`.
- If the user runs a command before the welcome sequence completes, the animation stops immediately and clears the partial output in that same tab only.
- An optional message of the day (`motd`) in `config.yaml` is displayed below the welcome sequence and supports `**bold**`, `` `inline code` ``, `[link](url)`, and newlines.

**Limits:** welcome files are fetched once on page load — edits require a reload (no restart needed). Missing files are gracefully skipped: no `welcome.yaml` means no sampled commands; no banner/hints files means no banner/hints; the sequence still runs with whatever parts are present.

**Configuration:**

- `config.yaml` — `welcome_status_labels`, `welcome_hint_rotations`, `motd`.
- `app/conf/welcome.yaml` — sampled commands:

```yaml
- cmd: "ping -c 3 google.com"
  out: |
    PING google.com: 56 data bytes
    64 bytes from 142.250.80.46: icmp_seq=0 ttl=116 time=8.4 ms
    ...
  group: network
  featured: true

- cmd: "# Just a comment with no output"
```

- `cmd` — required command text shown after `$`.
- `out` — optional sample output shown below the command; leading whitespace preserved, trailing stripped.
- `group` — optional sampling bucket used to keep the welcome set varied across categories.
- `featured` — optional boolean; featured commands are preferred for the first sample and get the `TRY THIS FIRST` badge.
- `app/conf/ascii.txt` / `ascii_mobile.txt` — desktop/mobile banner text.
- `app/conf/app_hints.txt` / `app_hints_mobile.txt` — rotating footer hint lines.

**Related files:** `app/blueprints/content.py` (welcome/banner/hint endpoints), `app/static/js/shell_chrome.js` + `app/static/js/mobile_chrome.js` (sequence rendering), `app/conf/welcome.yaml`, `app/conf/ascii.txt`, `app/conf/ascii_mobile.txt`, `app/conf/app_hints.txt`, `app/conf/app_hints_mobile.txt`.

---

## Custom FAQ

**Purpose:** operator-supplied FAQ entries appended to the built-in FAQ, with a safe markup subset for links, formatting, and clickable command chips.

**Behavior:**

- Entries in `app/conf/faq.yaml` are appended to the built-in FAQ returned by `/faq` and re-read on every request (no restart required).
- Each entry has a required `question` and one of `answer` (safe markup subset) or `answer_html` (exact HTML).
- The safe markup subset in `answer` supports `**bold**`, `*italic*`, `__underline__`, `` `inline code` ``, `- list items`, and command chips like `[[cmd:shortcuts]]` or `[[cmd:ping -c 1 127.0.0.1|custom label]]`.
- Chips behave like the built-in allowlist chips — clicking one loads the command into the prompt without running it.
- The file is optional — a missing or empty file shows only the built-in FAQ items.
- Built-in entries can use richer modal formatting while still rendering plain-text answers in the `faq` command.

**Limits:** the safe markup subset is deliberately narrow; anything outside it is shown literally. For arbitrary HTML (images, tables, custom classes) use `answer_html`.

**Configuration:** `app/conf/faq.yaml`:

```yaml
- question: "Where is this server located?"
  answer: "This server is hosted in New York, USA on a 10 Gbps uplink via Cogent and Zayo."

- question: "What is the outbound bandwidth?"
  answer: "Outbound traffic is limited to 1 Gbps sustained."
```

**Related files:** `app/conf/faq.yaml` (custom entries), `app/blueprints/content.py` (`/faq` endpoint + markup rendering), `app/static/js/shell_chrome.js` (FAQ modal + chip click wiring).

---

## Theme Selector

**Purpose:** live theme picker backed by the named variants under `app/conf/themes/`, with the choice persisted in `localStorage` and applied to the shell, permalink pages, and HTML exports.

**Behavior:**

- Click **◑ theme** in the desktop rail (or the **☰** menu on mobile) to open the theme selector modal.
- Picking a variant applies it immediately and saves the choice in `localStorage` so it persists across sessions on the same browser.
- The selected theme applies to the live shell, permalink pages, and HTML exports — so shared links render in the author's theme context when opened fresh.

**Limits:** theme selection is per-browser (not per-user on the server); clearing browser storage reverts to the default theme.

**Configuration:** theme variants live under `app/conf/themes/`; see [THEME.md](THEME.md) for authoring details (variable names, fallbacks, and how a new variant is registered).

**Related files:** `app/conf/themes/` (theme variant files), `app/static/js/theme.js` (selector modal + `localStorage` persistence), `app/static/css/theme-core.css` (variable surface), `THEME.md` (authoring guide).

---

## Options Modal

**Purpose:** per-browser display and sharing preferences (timestamps, line numbers, welcome intro, redaction default, run notifications), persisted via cookies and applied on every page load.

**Behavior:**

- Click **≡ options** in the desktop rail (or the **☰** menu on mobile) to open the modal.
- Timestamp and line-number settings mirror the tabbar quick toggles — changing either surface updates the other immediately.
- The welcome-intro setting controls whether the welcome animation plays on first tab: full animated sequence, instant settle, or no welcome tab at all.
- The share-snapshot redaction setting selects the default redaction choice (prompt / redacted / raw) so the share prompt is skipped once a preference is saved.
- Run notifications fire a browser desktop notification each time a run exits or is killed; the title shows only the command root (`$ curl`) and the body shows exit code and elapsed time. Enabling triggers the native permission prompt; if notifications are blocked, the toggle reverts with a toast.
- Preferences are stored in browser cookies and applied on every page load; they persist across sessions on the same device.

**Limits:** preferences are per-browser (not synced across devices); clearing cookies reverts to defaults. Blocked notification permission cannot be re-prompted by the toggle — it must be re-enabled in browser settings.

**Configuration:**

| Setting | Choices | Description |
|---------|---------|-------------|
| **Timestamps** | Off / Elapsed / Clock | Timestamp mode for output lines. Equivalent to the tabbar quick toggle |
| **Line Numbers** | on / off | Sequential line numbers beside output and the live prompt. Equivalent to the tabbar toggle |
| **Welcome Intro** | Animated / Disable Animation / Remove Completely | Welcome animation behavior on first tab |
| **Share Snapshot Redaction** | Prompt Until Set / Default To Redacted / Default To Raw | Default redaction choice for snapshot sharing |
| **Run Notifications** | on / off | Browser desktop notification on run exit or kill; title is command root, body is exit code + elapsed time |

**Related files:** `app/static/js/shell_chrome.js` (Options modal rendering + tabbar sync), `app/static/js/mobile_chrome.js` (mobile menu wiring), `app/static/js/notifications.js` (permission + notification dispatch).

---

## Persistence & Retention

**Purpose:** durable storage layout for run history, preview metadata, full-output artifacts, and tab snapshots, with time-based retention pruning on startup.

**Behavior:**

- Run history, preview metadata, full-output artifact metadata, and tab snapshots all live under `./data`.
- SQLite uses `./data/history.db`; persisted full-output artifacts are written as compressed files under `./data/run-output/`.
- The `./data` directory is created automatically on first run and persists across container restarts and recreations.
- On startup, runs, run-output artifact metadata, artifact files, and snapshots older than `permalink_retention_days` are pruned together.

**Limits:** `./data` is the only writable path in an otherwise read-only container. Setting `permalink_retention_days: 0` disables pruning entirely (unlimited retention). Never write to `./data/history.db` from the host — host/container SQLite version mismatches can corrupt the FTS5 btree.

**Configuration:** `permalink_retention_days` in `config.yaml` (default 365; `0` disables pruning).

**Related files:** `app/database.py` (schema + migrations + FTS5 wiring), `app/run_output_store.py` (compressed artifact writer + reader), `app/retention.py` (startup pruning), `app/blueprints/history.py` (reads + writes through the persistence layer). See [ARCHITECTURE.md](ARCHITECTURE.md) for full schema.

**Useful direct checks:**

```bash
# Row counts
sqlite3 data/history.db "SELECT COUNT(*) FROM runs; SELECT COUNT(*) FROM run_output_artifacts; SELECT COUNT(*) FROM snapshots;"

# Delete runs older than 90 days
sqlite3 data/history.db "DELETE FROM runs WHERE started < datetime('now', '-90 days');"

# Delete all snapshots
sqlite3 data/history.db "DELETE FROM snapshots;"
```

---

## Session Tokens

**Purpose:** optional persistent named identity (`tok_<32 hex>`) so run history, snapshots, and starred commands follow an operator across browsers and workstations without introducing a login layer.

**Behavior:**

- By default each browser gets an anonymous UUID stored in `localStorage` under `session_id`. A session token replaces that identity with a persistent `tok_<32 hex>` so run history, snapshots, and starred commands follow the operator across browsers and workstations.
- Tokens are generated server-side as `tok_` + 32 lowercase hex characters (36 chars total, cryptographically random) and recorded in the `session_tokens` table.
- The active token is stored in `localStorage` under `session_token`; the original UUID is always preserved under `session_id` so `session-token clear` has a stable fallback.
- The browser sends the active identity as `X-Session-ID` on every request; possession of the token string is the only authorization check (matching the existing anonymous session model).
- Changing the token in one tab propagates to all open tabs via the `storage` event — recent chips, starred state, history drawer, and the options-panel masked display all refresh without a reload.
- All `session-token` subcommands are intercepted client-side and never reach the server, so token values are not written to the command log.

**Terminal commands:**

- `session-token` (no subcommand) — prints current status: active token in masked form or "anonymous session".
- `session-token generate` — requests a new token and offers to migrate the current session's runs, snapshots, and starred commands. The token becomes active only after a successful migration; declining migration activates it as a fresh named session; migration failure leaves the old session active.
- `session-token set <token>` — adopts an existing token. UUIDs are always accepted; `tok_...` values must already exist on this server. The migration prompt is offered if the current session has history; verification failures fail closed rather than silently switching to an empty session.
- `session-token clear` — removes `session_token` from `localStorage` and reverts to the anonymous UUID session. Server-side history remains and can be reclaimed with `session-token set`.
- `session-token rotate` — generates a new token, migrates all runs/snapshots to it, then switches. The switch is **atomic** — migration failure aborts the rotation and keeps the old token active. Old token is retired on success.
- `session-token list` — calls `GET /session/token/info` and shows the active token in masked form with its creation date (or "anonymous session").
- `session-token revoke <token>` — permanently deletes the given token via `POST /session/token/revoke`. If the revoked token is the active one, the client clears `localStorage` and falls back to the anonymous UUID session. Runs, snapshots, and starred rows for the revoked token are not deleted but become unreachable.

**Options panel buttons:**

| Button | Shown when | Action |
|---|---|---|
| **Generate** | No token active | Generates a new token; copies it to the clipboard with a toast |
| **Set** | No token active | Opens a modal to paste an existing token from another device |
| **Rotate** | Token active | Generates a new token, migrates history, copies the new token |
| **Clear** | Token active | Removes the active token and reverts to the anonymous session |

If a session has run history, a migration confirmation modal is shown before Generate/Set/Rotate (same prompt as the terminal commands). `list` and `revoke` remain terminal-only.

**Limits:** there is no user-facing authentication — possession of the token is sufficient access. `POST /session/migrate` requires the `from_session_id` body field to match the caller's `X-Session-ID` header (mismatch returns 403), so a migration call can only move the caller's own data.

**Configuration:** no config keys — token issuance is always enabled. Token scope currently covers runs, snapshots, and starred commands.

**Related files:** `app/static/js/session.js` (client-side token flow + cross-tab `storage` sync), `app/blueprints/session.py` (`/session/token/*` and `/session/migrate` routes), `app/database.py` (`session_tokens` and `starred_commands` tables).

---

## Security and Process Isolation

**Purpose:** defence in depth against shell-injection, loopback callbacks, and worker impersonation, relying on allowlist validation plus OS-level user separation rather than browser trust.

**Behavior:**

- **Shell injection protection.** The app blocks metacharacters that enable command chaining and redirection — `&&`, `||`, `;`, backticks, `$()`, and redirection operators. `|` is allowed only within the constrained pipe model described in [Built-In Pipe Support](#built-in-pipe-support). Direct filesystem references to `/data` and `/tmp` are blocked as command arguments (using a negative lookbehind so URLs containing those strings as path segments are still permitted). Loopback targets (`localhost`, `127.0.0.1`, `0.0.0.0`, `[::1]`) are blocked at the validation layer.
- **Process isolation.** Gunicorn runs as unprivileged `appuser`; user-submitted commands run as separate unprivileged `scanner` processes. The container filesystem is read-only (`read_only: true`); `/data` is the only writable path and is accessible only to `appuser` (`chmod 700`). Container startup installs an OS-level guard so `scanner` cannot connect back to the app port.
- **Rate limiting + process tracking.** Redis-backed rate limiting prevents burst abuse across multiple Gunicorn workers. PID tracking in Redis keeps kill behavior correct when a kill request lands on a different worker than the one that started the process.
- **Session tracking.** Browsers send a stable `X-Session-ID` so history entries, rate-limit state, and test isolation remain scoped per client without requiring authentication.

**Limits:** there is no authentication layer — controls are defence in depth, not a user boundary. The allowlist plus OS-level isolation are the trust boundary; browser state is not trusted. Loopback blocking applies only to literal loopback addresses and not to private-range addresses that happen to be locally reachable.

**Configuration:**

- `allowed_commands.txt` — dispatch gate (see [Command Allowlist](#command-allowlist)).
- `trusted_proxy_cidrs` in `config.yaml` — CIDRs whose `X-Forwarded-For` is honored.
- `diagnostics_allowed_cidrs` in `config.yaml` — CIDRs permitted to reach `/diag`.
- `docker-compose.yml` — `read_only: true`, `init: true`, `user` directives, and the port-egress guard.

**Related files:** `app/command_policy.py` (metacharacter + loopback validation), `app/runner.py` (subprocess spawn as `scanner`), `app/kill.py` (Redis PID tracking), `docker-compose.yml` (filesystem + user isolation). See [ARCHITECTURE.md](ARCHITECTURE.md) for cross-worker signalling, the Redis-backed multi-worker kill path, and the `nmap` capability model.

---

## Structured Logging

**Purpose:** backend-emitted structured events (text or GELF JSON) with stable event names and context fields, so operators can observe the shell through a log aggregator without regex-parsing free-form strings.

**Behavior:**

- The backend emits structured log events at four levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`.
- Two output formats are supported: `text` (human-readable `key=value` pairs for local development) and `gelf` (JSON compatible with log aggregators).
- Each event carries structured context fields — session ID, command root, run ID, status — rather than interpolated strings, so log lines are machine-parseable without regex.
- Event names are stable (e.g. `RUN_START`, `RUN_END`, `KILL`, `DIAG_VIEWED`, `UNTRUSTED_PROXY`), letting aggregators filter by name without string matching.

**Limits:** field names and level semantics are stable, but specific numeric codes and free-form `message` strings are not part of the contract. Downstream consumers should key off event names and structured fields, not prose.

**Configuration:** `log_format` and `log_level` in `config.yaml` (`text` / `gelf`, default `text`; `DEBUG` / `INFO` / `WARNING` / `ERROR`, default `INFO`).

**Related files:** `app/logging_config.py` (format + level wiring, event emission helpers), `app/blueprints/run.py` (run lifecycle events), `app/blueprints/history.py` (snapshot + diag events).

---

## Operator Diagnostics

**Purpose:** a restricted operator-only status page for inspecting runtime health, storage state, config, and tool availability without opening a shell session.

**Behavior:**

- `/diag` provides a live operator view of the running instance and is disabled by default.
- When the visiting IP is in the allowed range, a `⊕ diag` button appears in the desktop rail and the mobile menu alongside the other toolbar buttons. It stays hidden for all other visitors.

### Enabling access

Add the IP addresses or CIDR ranges that should be allowed to reach the page to `config.yaml`:

```yaml
diagnostics_allowed_cidrs:
  - "127.0.0.1/32"    # localhost curl
  - "172.16.0.0/12"   # Docker bridge networks
```

- Access is checked against the resolved client IP, using the same trusted-proxy path as logging and rate limiting.
- `X-Forwarded-For` is honored only when the direct peer IP is inside `trusted_proxy_cidrs`; otherwise the app falls back to the direct peer IP and logs `UNTRUSTED_PROXY` when a forwarded header was supplied.
- The page returns 404 for all other requests.
- Denied access is logged as `DIAG_DENIED` with the resolved client IP and configured CIDRs; allowed access is logged as `DIAG_VIEWED`.

### What the page shows

| Section | Content |
|---------|---------|
| **App** | App version and configured name |
| **Database** | Connection status (`online` / `error`), total run and snapshot counts |
| **Redis** | Whether Redis is configured, and connection status when it is |
| **Vendor Assets** | Whether `ansi_up.js`, `jspdf.umd.min.js`, and the font files are present (`loaded`) or missing (`missing`) from `app/static/` |
| **Config** | All operational config values: rate limits, timeouts, output caps, retention, proxy CIDRs, log settings |
| **Activity** | Run counts for today, last 7 days, this month, this year, and all-time, plus outcome breakdown (success / failed / incomplete by exit code) |
| **Top Commands** | Top 10 commands by run frequency and top 5 longest individual runs |
| **Tools** | Per-tool availability derived from the allowlist — which command roots are present on `$PATH` and which are missing |

### JSON output

Append `?format=json` to get the same data as a JSON object, suitable for scripting or monitoring integrations:

```bash
curl http://localhost:8888/diag?format=json
```

**Limits:** `/diag` is gated entirely by IP/CIDR allowlists, not by an authentication layer. Empty `diagnostics_allowed_cidrs` disables it completely.

**Configuration:** `diagnostics_allowed_cidrs` in `config.yaml`; access resolution also depends on `trusted_proxy_cidrs` when the app is behind a proxy.

**Related files:** `app/blueprints/history.py` (`/diag` HTML + JSON responses), `app/static/css/diag.css` (page styling + mobile breakpoint behavior), `app/templates/diag.html` (diagnostics page markup), `README.md` (operator-facing config reference), `ARCHITECTURE.md` (diagnostics and logging runtime details).

---

## Related Docs

- [README.md](README.md) — quick summary, quick start, installed tools, and configuration reference
- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime layers, request flow, persistence schema, and security mechanics
- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, test workflow, linting, and merge request guidance
- [DECISIONS.md](DECISIONS.md) — architectural rationale, tradeoffs, and implementation-history notes
- [THEME.md](THEME.md) — theme registry, selector metadata, and override behavior
- [tests/README.md](tests/README.md) — test suite appendix, smoke-test coverage, and focused test commands
