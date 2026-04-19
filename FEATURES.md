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

The shell maintains a terminal-style prompt flow throughout each session:

- Submitted commands are echoed inline above their output so the transcript reads like a real terminal session
- Pressing **Enter** on a blank prompt adds a fresh prompt line without calling `/run`
- **Ctrl+C** is context-aware: while a command is running it opens a kill confirmation dialog; while the tab is idle it drops a new prompt line
- After highlighting transcript text on desktop, **ArrowUp**, **ArrowDown**, **Enter**, and **Ctrl+R** return control to the prompt without clearing the selection

While a command is running the live input prompt hides so output has full focus. Once the command completes the prompt reappears immediately.

---

## Recent Commands

Recent commands are surfaced in two places: the desktop rail's Recent section (clickable chips that load a command into the prompt), and on mobile a persistent "Recent" peek row between the transcript and the composer that shows a count plus a one-line preview and opens a full pull-up recents sheet on tap. The sheet lists recent runs as tappable rows with per-row copy / permalink / restore actions, search, filter chips (root / exit / date / starred), and a clear-all control. Both surfaces show the most recent distinct commands up to the `recent_commands_limit` configured in `config.yaml` (default 8), are hidden until there is at least one command in history, and update live as commands are run.

---

## Autocomplete

Autocomplete suggestions are loaded from `conf/autocomplete.yaml` at page load and matched against what you type. Suggestions are rendered as a terminal-style vertical list aligned with the command text (after the prompt prefix), and the matched portion is highlighted in green.

Placement rules:
- The list opens below the prompt when there is room
- If space below is tight, it flips above the prompt
- When shown above, suggestions keep their normal top-to-bottom order so keyboard navigation stays consistent with the below-prompt view

**Keyboard controls:**

| Key | Action |
|-----|--------|
| **↑ / ↓** | Navigate through suggestions |
| **Tab** | Expand to the longest shared prefix, then cycle suggestions forward |
| **Shift+Tab** | Cycle suggestions backward |
| **Enter** | Accept highlighted suggestion, or run the command if none selected |
| **Escape** | Dismiss the dropdown |

Completion behavior is intentionally shell-like rather than picker-like:

- if there is only one match, `Tab` accepts it immediately
- if multiple matches share a longer common prefix than what you typed, the first `Tab` expands to that shared prefix
- once no longer shared prefix remains, repeated `Tab` presses move the highlight through the current matches
- `Enter` accepts the currently highlighted match
- once a known command root is in place, the dropdown can switch to contextual flag/value hints for that tool and only replaces the current token instead of the whole command
- at `command `, contextual mode can show positional hints alongside flags so required arguments stay visible before you type them
- after `command |`, contextual mode can switch into the supported built-in pipe stage and suggest `grep`, `head`, `tail`, `wc -l`, `sort`, and `uniq`, then narrow to stage-specific flags and count hints
- already-used singleton-style flags are suppressed from contextual suggestions so the dropdown stays focused on the next useful options

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

`Ctrl+R` opens an interactive history search mode inline at the prompt:

- The dropdown does not appear until the first character is typed
- Typing filters commands from the full session history in real time — the search queries the same server-side history the history drawer uses, so commands from earlier in the session or previous days are always reachable
- Results are capped at 10; narrowing the query further surfaces deeper matches
- **Enter** accepts the highlighted command and runs it immediately
- **Tab** accepts the highlighted command without running it, leaving it editable in the prompt
- **Ctrl+R** again cycles forward through the current matches
- **Escape** dismisses the search and restores whatever draft was in the prompt before `Ctrl+R` was pressed

---

## Keyboard Shortcuts

On macOS, `Option` is the key used for the app-safe `Alt` shortcuts. The `Ctrl+...` bindings are intentional shell-style controls and are separate from browser `Command` shortcuts.

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

**Real-time streaming**

Command output arrives line by line over SSE. Fast commands batch flushes to avoid overwhelming the browser; slow or long-running scans stream each line as it arrives. The output view follows the live tail automatically until you scroll away.

When the SSE connection silently drops mid-run, the shell detects the stall and shows an inline notice so you know to investigate rather than waiting indefinitely.

**Run timer**

A live elapsed timer sits next to the status pill while a command runs. The final elapsed time is recorded in the exit line so you can see how long a completed scan took.

**Timestamps and line numbers**

Both are off by default and can be toggled independently from the tabbar's inline controls (and from the mobile menu):

- **Elapsed timestamps** — show time-since-start for each line
- **Clock timestamps** — show wall-clock time for each line
- **Line numbers** — sequential line count from the start of output

Both modes are rendered from shared per-line prefix metadata, so toggling them updates existing output in place without re-fetching anything. Preferences are saved in `localStorage` and persist across sessions.

**Live tail helper**

When you scroll away from the bottom of a streaming tab, a jump-to-live / jump-to-bottom button appears. It is scoped to the active tab and disappears once you return to the tail.

---

## Kill Running Processes

Each tab shows a **■ Kill** button while a command is running. Clicking it opens a confirmation dialog before sending `SIGTERM` to the full process group, so accidental clicks don't interrupt a long scan.

`Enter` confirms and `Escape` cancels the dialog, matching the button labels. The same confirmation flow applies whether you use the button or `Ctrl+C`.

---

## Status HUD

The persistent bottom bar on desktop surfaces eleven live pills that describe the current run, transport, and environment state. The left cluster covers run state, connection, and identity; the right cluster carries the output actions (share, copy, save, clear, kill). Pills start with a muted `—` placeholder at page load and transition to live values on the first poll.

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

The backing endpoint is a lightweight `GET /status` that returns `{uptime, db, redis, server_time}` as always-200 JSON so a degraded component never flaps the HUD or triggers reconnect logic — it reports `"down"` for that component while the rest of the UI continues to work. `/status` is polled every 15 seconds; latency is measured client-side with `performance.now()` around the fetch call.

On narrow desktop widths the pill row falls back to horizontal overflow scrolling so the right-side HUD actions never get pushed off-screen. Mobile hides the HUD entirely; per-tab status and exit codes remain visible inline next to the prompt echo, and the run notifications toggle in the Options modal covers the background-watch use case.

---

## Built-In Pipe Support

The shell supports a narrow built-in pipe model without enabling general shell piping:

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

Behavior:

- use one supported pipe stage per command
- the filtered view is what appears in the terminal, history, permalinks, and exports for that run
- autocomplete understands this narrow pipe stage and can guide `grep`, `head`, `tail`, `wc -l`, `sort`, and `uniq` after `command |`
- arbitrary pipes, chaining, and redirection remain blocked

---

## Output Search

Click **⌕ search** in the tabbar (on the right, alongside the timestamp and line-number toggles) to open the search bar above the output. Matches are highlighted in amber; the current match is highlighted brighter. Use **↑↓** buttons or **Enter** / **Shift+Enter** to navigate between matches. Press **Escape** to close.

Two toggle buttons sit between the input and the match counter:

| Button | Default | Behavior |
|--------|---------|-----------|
| **Aa** | off | Case-sensitive matching — when off, search is case-insensitive |
| **.\*** | off | Regular expression mode — when on, the search term is treated as a JavaScript regex; an invalid pattern shows `invalid regex` instead of throwing |

Both toggles re-run the search immediately when clicked.

---

## Copy, Save, and Export

Four actions are available from the desktop HUD bar at the bottom of the shell (and from the mobile menu sheet):

- **Copy** — copies the full plain-text output to the clipboard
- **save ▾** — a dropdown with three export formats:
  - **txt** — plain-text file with a timestamped filename
  - **html** — themed HTML file with ANSI colors preserved, renders correctly in a browser without the shell; fonts and theme colors are inlined so the file is fully self-contained
  - **pdf** — themed PDF rendered entirely in the browser via jsPDF, no server round-trip; includes the app header, command, exit-status badge, timestamp, and full ANSI output

The same `save ▾` dropdown is available on the desktop HUD bar, the permalink page header, and the mobile menu, so the export experience is consistent across all surfaces.

All local exports (txt, html, pdf) produce unredacted output — they show the true command output as it appeared in the terminal. Redaction is scoped exclusively to the permalink share flow.

---

## Tabs & Run History

Each command runs in the currently active tab. You can open additional tabs with the **+** button to run commands side by side and keep results from different sessions visible simultaneously. Each tab shows a colored status dot (amber = running, green = success, red = failed or killed) and is labelled with the last command that was run in it. Double-click a tab label to rename it inline. Draft input is preserved per tab — switching away and back restores whatever you had typed without losing it. The **+** button is disabled once the tab limit is reached; the limit is configurable via `max_tabs` in `config.yaml` (default 8, set to 0 for unlimited). When more tabs are open than fit the window width, use the tab-scroll arrows or drag tabs to reorder.

The **⧖ history** button opens a slide-out drawer showing the last 50 completed runs with timestamps and exit codes. Click any entry to load its output into a new tab — the command is shown at the top of the output as a normal styled prompt line followed by the results. Each entry has a toggleable **star** to the left of the command plus three actions: **copy** (copies the command text to the clipboard), **permalink** (copies the canonical `/history/<run_id>` link for that saved run), and **delete**. Starred entries and chips show a **★** indicator and are always listed before unstarred ones regardless of age. Star state is stored in `localStorage` by command text and persists across sessions. Large history restores show an in-drawer loading overlay so slower machines do not look hung while the preview is fetched and rendered.

When full-output persistence is enabled, the history drawer **permalink** action automatically points at the complete saved output of that run. The active tab's **share snapshot** action creates a separate `/share/<id>` snapshot of the current tab view and can optionally redact it before saving. Loading a history entry into a normal tab still uses the capped preview (`/history/<run_id>?json&preview=1`) so the browser is not forced to render very large scans. If the preview was truncated, the tab includes a notice pointing to the permalink for the full output.

The **delete all** button at the top of the history drawer (also present in the mobile recents sheet) prompts with three options: **Delete all** removes the entire history, **Delete Non-Favorites** removes only unstarred runs while keeping starred ones, and **Cancel** dismisses the prompt. The button was renamed from "clear all" to make it clear it is a destructive database deletion rather than a display-only clear.

The history drawer also supports full-text search across both command text and stored run output, plus filters for command root, exit status, recent date range, and starred-only results. Typing a term like a port number, CVE identifier, IP address, or any other string from a previous scan's output will surface matching runs. The search field placeholder reads "search commands and output" to reflect this. Search is backed by a SQLite FTS5 virtual table (`runs_fts`) indexed on the `command` and `output_search_text` columns. When full-output persistence is enabled, `output_search_text` is populated from the complete gzip artifact so even early lines of long runs are reachable; otherwise it falls back to the capped preview window. On mobile, the advanced filters stay behind a dedicated `filters` toggle to preserve result space, the command-root field uses app-owned autocomplete suggestions instead of the browser's native picker, and the common row actions keep the drawer open so you can work through multiple history entries without repeated reopen churn.

If the page reloads while a command is still running, the shell restores a running placeholder tab for that session instead of dropping the command on the floor. Live output cannot be replayed after the SSE stream is gone, but the restored tab keeps the kill action available, shows the submitted command with the normal prompt styling, polls for completion, and swaps into the saved run output automatically when the run lands in history.

Non-running tabs are restored separately from browser `sessionStorage`. That restore path brings back tab labels, transcript previews, statuses, and saved draft input for the current browser session, and restored completed tabs remount a usable live prompt immediately so you can continue working without tab-switching to wake the prompt back up.

On mobile, the **☰** menu in the top-right corner of the header opens a bottom-sheet menu that groups session-scoped actions (search, line numbers, timestamps) and overlays (history, workflows, options, theme, FAQ, diag) — see the Mobile Shell section below for the full layout.

---

## Guided Workflows

Guided workflows are built-in diagnostic sequences that load individual command steps directly into the active prompt. Each step can be clicked to pre-fill the prompt, letting you run checks one at a time without re-typing commands.

Built-in workflows:

- **DNS Troubleshooting** — diagnose why a domain isn't resolving or returns unexpected results (`dig` A/NS/MX, public resolver comparison, delegation trace)
- **TLS / HTTPS Check** — verify a domain's certificate, chain, and TLS configuration (`curl`, `openssl s_client`, `testssl`)
- **HTTP Triage** — investigate what a web server is returning (redirect-following curl, verbose curl, wget spider)
- **Quick Reachability Check** — confirm a host is up and which ports are open (`ping`, `nc`, fast `nmap`)
- **Email Server Check** — verify mail delivery configuration (MX/TXT record checks, SMTP port probes)

Custom workflows can be added to `conf/workflows.yaml`. The file is re-read on every request — no restart needed.

**Format:**

```yaml
- title: "My Custom Check"
  description: "A brief description shown in the workflow panel."
  steps:
    - cmd: "ping -c 4 example.com"
      note: "Is the host reachable?"
    - cmd: "nmap -F example.com"
      note: "What ports are open?"
```

Fields:

- `title` — required; shown as the workflow heading
- `description` — optional; shown below the title
- `steps` — required list; each step needs at least a `cmd`
- `cmd` — required; the command loaded into the prompt when the step is clicked
- `note` — optional; helper text shown alongside the command

---

## Permalinks

There are two types of permalink:

**Tab snapshot** (`/share/<id>`) — clicking **share snapshot** on any tab captures the current tab output and, when a full saved artifact exists, shares that full output as a snapshot in SQLite. The resulting URL opens a styled HTML page with ANSI color rendering, a `save ▾` dropdown (txt, html, pdf), a **copy** button (full text to clipboard), a **view json** option, and a link back to the shell. It also honors the browser's saved line-number and timestamp preferences on load. On browsers that support the Web Share API, the share action invokes the native OS share sheet; otherwise it copies the URL to the clipboard. This is the recommended way to share results.

**Single run** (`/history/<run_id>`) — the permalink button in the run history drawer links to an individual run result. If a persisted full-output artifact exists, this permalink serves the full saved output; otherwise it serves the capped preview stored in SQLite. It also honors the browser's saved line-number and timestamp preferences on load.

**Full output alias** (`/history/<run_id>/full`) — backward-compatible alias to the same run permalink. This exists so older links and tests continue to resolve cleanly.

Both types persist across container restarts via the `./data` SQLite volume. The `./data` directory is the only writable path in an otherwise read-only container and is created automatically on first run.

---

## Share Redaction

When creating a share snapshot, the shell can prompt whether to share raw or redacted output. A built-in redaction baseline masks common secrets and infrastructure details; operators can append custom regex rules on top.

Once you choose raw or redacted, that preference can be saved as a persistent default in the [Options modal](#options-modal) so subsequent share actions skip the prompt and reuse the same choice. The default applies consistently whether sharing is triggered from the prompt flow or directly from the Options modal.

Redaction applies only to the snapshot — the stored run history is never modified.

---

## Mobile Shell

On touch-sized screens the app switches to a dedicated mobile layout:

- **Mobile composer dock** — a visible composer with its own Run button replaces the desktop inline input
- **Keyboard helper row** — a row of touch targets above the keyboard provides `Home`, `End`, single-character left/right moves, word-left / word-right jumps, delete-word, and delete-line without requiring a hardware keyboard
- **Recent peek + pull-up sheet** — an idle peek row between the transcript and the composer shows the recent-run count plus a one-line preview; tapping it opens a full-height recents sheet with search, filter chips (root / exit / date / starred), per-row copy/permalink/restore actions, and a clear-all control
- **Output follow** — when the keyboard opens, the active output re-sticks to the bottom so the last line stays visible
- **Stable layout** — the mobile shell uses a normal-flow layout that avoids Firefox keyboard flash, gap, and floating-composer regressions
- **Shared state** — desktop and mobile Run buttons are kept in sync: both disable together for blank prompts and running tabs

On mobile, the **☰** menu in the top-right corner of the header opens a bottom-sheet menu with two grouped sections: a session group (search, line numbers toggle, timestamps picker) that affects the current terminal in place, and an overlays group (history, workflows, options, theme, FAQ, and the diagnostics page for IPs in `diagnostics_allowed_cidrs`) that opens full-screen surfaces. `line numbers` is a single on/off row; `timestamps` expands inline to a three-mode picker (off / elapsed / clock) so the active mode is always visible. The history drawer's advanced filters stay behind a dedicated `filters` toggle to preserve result space.

---

## Built-In Commands

The shell provides several categories of native commands that run without dispatching to external binaries.

**Utility commands**

`help`, `history`, `last`, `limits`, `retention`, `status`, `which`, `type`, `faq`, `banner`, `fortune`, `jobs`, `shortcuts`, `clear`, `autocomplete`, `ls`, `version`, and `whoami` are available in every session. `ps` lists currently running processes for the session (PID, TTY, STAT, START, CMD columns), or shows a "no running processes" notice when idle.

**Shell identity commands**

`env`, `pwd`, `uname`, `uname -a`, `id`, `groups`, `hostname`, `date`, `tty`, `who`, `uptime`, `ip a`, `route`, `df -h`, and `free -h` return stable shell-style information without exposing host internals.

**Guardrail commands**

`sudo`, `reboot`, `poweroff`, `halt`, `shutdown now`, `su`, and the exact `rm -fr /` / `rm -rf /` patterns return explicit shell responses instead of pretending to run or silently failing.

**`man` support**

`man <allowed-command>` renders the real man page when tooling exists. `man <built-in-command>` shows the built-in command summary instead.

---

## Command Allowlist

Allowed commands are controlled by `conf/allowed_commands.txt`. The file is re-read on every request, so changes take effect immediately without restarting the server.

**Format:**
- One command prefix per line
- Lines starting with `#` are comments and are ignored
- Lines starting with `##` define a category group shown in the FAQ command list (e.g. `## Network Diagnostics`)
- Lines starting with `!` are **deny prefixes** — they take priority over allow prefixes, letting you block specific flags on an otherwise-allowed command (see below)
- Matching is prefix-based: a prefix of `ping` permits `ping google.com`, `ping -c 4 1.1.1.1`, etc.
- Be as specific or broad as you like — `nmap -sT` permits only TCP connect scans, while `nmap` permits any nmap invocation

**Example:**

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

Commands in the FAQ are displayed grouped by their `##` category, with each chip clickable to load the command into the input bar. Commands before any `##` header are shown in an unnamed group. Deny prefixes (`!` lines) are not shown to users.

To **disable restrictions entirely**, delete `conf/allowed_commands.txt` or leave it empty — all commands will be permitted.

### Deny Prefixes

Lines starting with `!` are deny prefixes and take priority over allow prefixes. They let you block specific flags or subcommands on an otherwise-allowed tool:

```text
nmap
!nmap -sU
!nmap --script
```

This allows all `nmap` invocations except those containing `-sU` or `--script` as a flag. Unlike allow entries, deny matching is not purely prefix-based — the flag is matched anywhere in the command as a space-separated token, so `nmap -sT -sU 10.0.0.1` is caught as well as `nmap -sU 10.0.0.1`. The tool prefix must still match (`!nmap -sU` only applies to `nmap` commands).

Tool names and subcommand prefixes are matched **case-insensitively**. Flag names are matched **with exact case**, so `!curl -K` blocks `curl -K` (insecure TLS) without also blocking `curl -k` (insecure, lowercase). Use the exact flag casing you want to deny.

**`/dev/null` exception:** denied output flags are permitted when their argument is `/dev/null`. This allows common patterns like discarding the response body while capturing metadata:

```bash
curl -o /dev/null -s -w "%{http_code}" https://example.com
wget -q -O /dev/null --server-response https://example.com
```

---

## Wordlists

The full [SecLists](https://github.com/danielmiessler/SecLists) collection is installed at `/usr/share/wordlists/seclists/` and available to any tool that accepts a `-w` flag (gobuster, ffuf, dnsenum, fierce, etc.).

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

When the page first loads, the terminal can render a staged welcome sequence:

- ASCII banner text loaded from `app/conf/ascii.txt`
- a startup-status block using labels from `welcome_status_labels`
- curated sampled commands and their sample output from `app/conf/welcome.yaml`
- rotating footer hints loaded from `app/conf/app_hints.txt`

On touch-sized screens the welcome flow uses `app/conf/ascii_mobile.txt` and `app/conf/app_hints_mobile.txt` instead of the wide desktop banner and desktop hint file, while keeping the same status and hint timing and skipping the sampled command blocks.

If `welcome.yaml` is absent or empty, the sampled-command portion is skipped. If `ascii.txt`, `app_hints.txt`, `ascii_mobile.txt`, or `app_hints_mobile.txt` are absent, those parts are skipped as well.

An optional message of the day (`motd`) can also be configured in `config.yaml` to display below the welcome sequence. It supports `**bold**`, `` `inline code` ``, `[link](url)`, and newlines.

**Format:**

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

Fields:

- `cmd` — required command text shown after `$`
- `out` — optional sample output shown below that command
- `group` — optional sampling bucket used to keep the welcome set varied across categories
- `featured` — optional boolean; featured commands are preferred for the first sample and get the `TRY THIS FIRST` badge

Notes:

- Leading whitespace in `out` is preserved; trailing whitespace is stripped
- Sampled welcome commands are clickable and load directly into the prompt without running
- The `TRY THIS FIRST` badge is clickable and has the same behavior as clicking the featured command text
- App hints rotate until interrupted unless `welcome_hint_rotations` is set to `1`
- If the user runs a command before the welcome sequence completes, it stops immediately and clears the partial output in that same tab only

The welcome files are fetched once on page load. Edit `conf/welcome.yaml`, `conf/ascii.txt`, `conf/ascii_mobile.txt`, `conf/app_hints.txt`, or `conf/app_hints_mobile.txt` and reload the page to see changes without restarting the server.

---

## Custom FAQ

Instance-specific FAQ entries can be added to `app/conf/faq.yaml`. Entries are appended after the built-in FAQ items returned by `/faq` and are re-read on every request — no restart needed.

**Format:**

```yaml
- question: "Where is this server located?"
  answer: "This server is hosted in New York, USA on a 10 Gbps uplink via Cogent and Zayo."

- question: "What is the outbound bandwidth?"
  answer: "Outbound traffic is limited to 1 Gbps sustained."
```

The file is optional — if it doesn't exist or contains no valid entries, the FAQ modal shows only the built-in items. Custom entries can use a small safe markup subset in `answer` for bold, italics, underline, inline code, bullet lists, and clickable command chips. Chips behave like the built-in allowlist chips and load the command into the prompt when clicked:

- `**bold**`
- `*italic*`
- `__underline__`
- `` `inline code` ``
- `- list items`
- `[[cmd:shortcuts]]` or `[[cmd:ping -c 1 127.0.0.1|custom label]]`

Use `answer_html` if you need exact HTML. Built-in entries can still use richer modal formatting while showing plain-text answers in the `faq` command.

---

## Theme Selector

Click **◑ theme** in the desktop rail (or the **☰** menu on mobile) to open the dedicated theme selector modal. Pick any registered theme variant and the choice is saved in `localStorage` and persists across sessions. The theme applies to the live shell, permalink pages, and HTML exports. For theme authoring details, see [THEME.md](THEME.md).

---

## Options Modal

Click **≡ options** in the desktop rail (or the **☰** menu on mobile) to open the Options modal. It exposes per-browser display and sharing preferences that are saved in cookies and applied on every page load:

| Setting | Choices | Description |
|---------|---------|-------------|
| **Timestamps** | Off / Elapsed / Clock | Controls the timestamp mode for output lines. Equivalent to the quick toggle in the tabbar |
| **Line Numbers** | on / off | Shows or hides sequential line numbers beside output and the live prompt. Equivalent to the tabbar toggle |
| **Welcome Intro** | Animated / Disable Animation / Remove Completely | Controls whether the welcome animation plays on the first tab: full animated sequence, instant settle, or no welcome tab at all |
| **Share Snapshot Redaction** | Prompt Until Set / Default To Redacted / Default To Raw | Sets the default redaction choice for snapshot sharing so the prompt is skipped once a preference is saved |
| **Run Notifications** | on / off | When enabled, a browser desktop notification fires each time a run exits or is killed. The notification title shows only the command root (e.g. `$ curl`) to avoid exposing arguments or token values; the body shows exit code and elapsed time. Enabling triggers the native browser permission prompt if needed; if the browser has already blocked notifications, the toggle reverts and a toast is shown |

All preferences are stored in browser cookies and persist across sessions on the same device.

---

## Persistence & Retention

Run history, preview metadata, full-output artifact metadata, and tab snapshots live under `./data`. SQLite uses `./data/history.db`, while persisted full-output artifacts are written as compressed files under `./data/run-output/`. The writable `./data` directory is created automatically on first run and persists across container restarts and recreations.

Retention is controlled by `permalink_retention_days` in `config.yaml`. On startup, runs, run-output artifact metadata, artifact files, and snapshots older than the configured number of days are pruned together. The built-in default is `365` days; `0` means unlimited retention.

Useful direct checks:

```bash
# Row counts
sqlite3 data/history.db "SELECT COUNT(*) FROM runs; SELECT COUNT(*) FROM run_output_artifacts; SELECT COUNT(*) FROM snapshots;"

# Delete runs older than 90 days
sqlite3 data/history.db "DELETE FROM runs WHERE started < datetime('now', '-90 days');"

# Delete all snapshots
sqlite3 data/history.db "DELETE FROM snapshots;"
```

For the schema and persistence-layer details, use [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Session Tokens

By default the shell assigns each browser an anonymous UUID stored in `localStorage` under `session_id`. Session tokens let you replace that anonymous identity with a persistent named token so your run history, snapshots, and shell identity follow you across browsers and workstations — without a login screen.

**Terminal commands**

Run `session-token` (no subcommand) to see the current status: active token in masked form or "anonymous session" if none is set.

- **`session-token generate`** — requests a new `tok_<32 hex>` token from the server and offers to migrate the current session’s runs, snapshots, and starred commands. The token becomes active only after the optional migration step completes successfully; if you decline migration it activates immediately as a fresh named session, and if migration fails the old session stays active.

- **`session-token set <token>`** — adopts an existing token, for example one generated on another device. The value is validated before being applied: UUIDs are always allowed, while `tok_...` values must already exist on this server. If the current session has run history, the same migration prompt is offered; verification failures fail closed rather than silently switching to an empty session.

- **`session-token clear`** — removes `session_token` from `localStorage` and reverts to the original anonymous UUID session. The token's run history remains in the server database and can be reclaimed with `session-token set` at any time.

- **`session-token rotate`** — generates a new token and migrates all run history and snapshots from the old identity to the new one before switching. The switch is **atomic**: if the migration call fails, the rotation is aborted and the old token stays active. The old token is retired after a successful rotate.

- **`session-token list`** — calls `GET /session/token/info` and displays the active token in masked form along with its creation date. Shows "anonymous session" if no token is set.

- **`session-token revoke <token>`** — permanently deletes the given token from the server via `POST /session/token/revoke`. If the revoked token is the currently active one, the client also clears `localStorage` and falls back to the anonymous UUID session. Possession of the token string is the only authorization check, matching the existing session model. Revocation invalidates the token at the API layer immediately; the old runs, snapshots, and starred-command rows are not deleted, but the revoked token can no longer read or write them.

All subcommands (`generate`, `set`, `clear`, `rotate`, `list`, `revoke`) are intercepted client-side and never reach the server, so token values are not written to the command log.

**Options panel**

The options panel (⚙) shows the active session token in masked form (e.g. `tok_abcd••••••••`) when one is set, or "No session token — anonymous session" otherwise. Four shortcut buttons cover the common inline token actions — their visibility is conditional on whether a token is currently active. `list` and `revoke` remain terminal-only commands:

| Button | Shown when | Action |
|---|---|---|
| **Generate** | No token active | Generates a new session token directly; copies the new token to the clipboard with a toast notification |
| **Set** | No token active | Opens a dedicated input modal to paste an existing token from another device |
| **Rotate** | Token active | Generates a new token and migrates all history to it; copies the new token to the clipboard with a toast notification |
| **Clear** | Token active | Removes the active session token and reverts to the anonymous UUID session |

If a session has run history, a history migration confirmation modal is shown before completing Generate, Set, or Rotate — the same migration prompt that appears when using the terminal commands. After any operation, the masked token display updates immediately without a page reload, and the recent command chips and starred commands also refresh to reflect the new session.

**Cross-tab sync**

When you change your session token in one tab, all other open tabs adopt the new identity automatically via the browser `storage` event. Passive tabs also refresh recent-command chips, starred-command state, the history drawer, and the options-panel token display, so the visible UI stays aligned with the new `X-Session-ID` without a reload.

**Token format and storage**

Tokens are generated server-side as `tok_` + 32 lowercase hex characters (36 chars total, cryptographically random). The active token is stored in `localStorage` under `session_token`; the original UUID is always preserved under `session_id` so `session-token clear` has a stable fallback. Issued tokens are recorded in the `session_tokens` table `(token TEXT PRIMARY KEY, created TEXT)`.

**History migration**

`POST /session/migrate` reassigns all `runs` and `snapshots` rows from one `session_id` to another in a single transaction. The `from_session_id` in the request body must match the caller's `X-Session-ID` header — any mismatch returns 403 — so users can only migrate their own session data.

**Current scope**

Run history, snapshots, and starred commands all migrate across sessions. Starred commands are backed by the `starred_commands` server table and `/session/starred` endpoints, so they follow a session token to any browser or workstation. On first token activation, commands already starred in `localStorage` are seeded to the server automatically.

---

## Security and Process Isolation

darklab shell uses layered controls rather than trusting the browser alone.

**Shell injection protection**

The app blocks metacharacters that enable command chaining and redirection: `&&`, `||`, `;`, backticks, `$()`, and redirection operators. Within the supported pipe model, `|` is allowed only in the constrained form described in [Built-In Pipe Support](#built-in-pipe-support). Direct filesystem references to `/data` and `/tmp` are also blocked as command arguments (using a negative lookbehind so URLs containing those strings as path segments are still permitted).

Loopback targets (`localhost`, `127.0.0.1`, `0.0.0.0`, `[::1]`) are blocked at the validation layer.

**Process isolation**

Gunicorn runs as unprivileged `appuser`. User-submitted commands run as separate unprivileged `scanner` processes. The container filesystem is read-only (`read_only: true`); `/data` is the only writable path and is accessible only to `appuser` (`chmod 700`). Container startup adds an OS-level guard so `scanner` cannot connect back to the app port.

**Rate limiting and process tracking**

Redis-backed rate limiting prevents burst abuse across multiple Gunicorn workers. PID tracking in Redis keeps kill-path behavior correct when a kill request lands on a different worker than the one that started the process.

**Session tracking**

Browsers send a stable `X-Session-ID` header so history entries, rate limit state, and test isolation remain scoped per client without requiring authentication.

For developer-facing details on cross-user signalling, Redis-backed multi-worker kill, and the `nmap` capability model, use [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Structured Logging

The backend emits structured log events at four levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Two output formats are supported:

- `text` — human-readable `key=value` pairs for local development
- `gelf` — JSON structured format compatible with log aggregators

The active format and level are set in `config.yaml`. Each log event carries structured context fields (session ID, command root, run ID, status) rather than interpolated strings, so log lines are machine-parseable without regex.

---

## Operator Diagnostics

The `/diag` endpoint provides a live operator view of the running instance without requiring a shell session. It is disabled by default and restricted to specific IP ranges so it is never exposed to end users.

### Enabling access

Add the IP addresses or CIDR ranges that should be allowed to reach the page to `config.yaml`:

```yaml
diagnostics_allowed_cidrs:
  - "127.0.0.1/32"    # localhost curl
  - "172.16.0.0/12"   # Docker bridge networks
```

Access is checked against the resolved client IP, using the same trusted-proxy path as logging and rate limiting. `X-Forwarded-For` is only honored when the direct peer IP is inside `trusted_proxy_cidrs`; otherwise the app falls back to the direct peer IP and logs `UNTRUSTED_PROXY` when a forwarded header was supplied. The page returns 404 for all other requests. Denied access is logged as `DIAG_DENIED` with the resolved client IP and configured CIDRs; allowed access is logged as `DIAG_VIEWED`.

When the visiting IP is in the allowed range, a `⊕ diag` button appears in the desktop rail and the mobile menu alongside the other toolbar buttons. It is hidden for all other visitors.

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

---

## Related Docs

- [README.md](README.md) — quick summary, quick start, installed tools, and configuration reference
- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime layers, request flow, persistence schema, and security mechanics
- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, test workflow, linting, and merge request guidance
- [DECISIONS.md](DECISIONS.md) — architectural rationale, tradeoffs, and implementation-history notes
- [THEME.md](THEME.md) — theme registry, selector metadata, and override behavior
- [tests/README.md](tests/README.md) — test suite appendix, smoke-test coverage, and focused test commands
