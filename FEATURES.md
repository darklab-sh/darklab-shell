# Feature Details

This is the detailed feature reference for darklab_shell. If you want the short version or setup steps, start with the [README](README.md) and [Quick Start](README.md#quick-start).

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
- [Command Findings](#command-findings)
- [Session Entity Atlas](#session-entity-atlas)
- [Copy, Save, and Export](#copy-save-and-export)
- [Tabs & Run History](#tabs--run-history)
- [Run Comparison](#run-comparison)
- [Guided Workflows](#guided-workflows)
- [Scheduled Runs](#scheduled-runs)
- [Permalinks](#permalinks)
- [Share Redaction](#share-redaction)
- [Mobile Shell](#mobile-shell)
- [Built-In Commands](#built-in-commands)
- [Headless API and CLI](#headless-api-and-cli)
- [Outbound Notifications](#outbound-notifications)
- [Session Command Variables](#session-command-variables)
- [Session Files](#session-files)
- [Project Workspaces](#project-workspaces)
- [Evidence Packages](#evidence-packages)
- [Command Allowlist](#command-allowlist)
- [Interactive PTY Mode](#interactive-pty-mode)
- [Wordlists](#wordlists)
- [Welcome Animation](#welcome-animation)
- [Onboarding Tour](#onboarding-tour)
- [Custom FAQ](#custom-faq)
- [Theme Selector](#theme-selector)
- [Options Modal](#options-modal)
- [Persistence & Retention](#persistence--retention)
- [Session Tokens](#session-tokens)
- [Encrypted Secrets](#encrypted-secrets)
- [External Intel](#external-intel)
- [Security and Process Isolation](#security-and-process-isolation)
- [Structured Logging](#structured-logging)
- [Operator Diagnostics](#operator-diagnostics)
- [Related Docs](#related-docs)

---

## Shell Prompt

**Purpose:** a terminal-like prompt that keeps command echo, blank Enter, and Ctrl+C behavior predictable.

**Behavior:**

- Submitted commands are echoed inline above their output so the transcript reads like a real terminal session.
- Pressing **Enter** on a blank prompt adds a fresh prompt line without starting a run.
- **Ctrl+C** is context-aware: while a command is running it opens a kill confirmation dialog; while the tab is idle it drops a new prompt line.
- After highlighting transcript text on desktop, **ArrowUp**, **ArrowDown**, **Enter**, and **Ctrl+R** return control to the prompt without clearing the selection.
- Desktop prompt text is selectable in place: drag selection, reverse-direction selection, double-click word selection, and copied transcript ranges all behave like normal transcript text, including prompt prefixes from historical rows.
- While a command is running the live input prompt hides so output has full focus; once the command completes the prompt reappears immediately.

**Limits:** prompt flow is per-tab. Selection-preserving key handling is desktop-only; mobile uses the browser's normal touch selection.

**Configuration:** none.

**Related files:** `app/static/js/controller.js` (composer + keypress handling), `app/static/js/runner.js` (command echo and prompt hide/show around `/runs`).

---

## Recent Commands

**Purpose:** quick access to recent commands without opening the full history drawer.

**Behavior:**

- Desktop rail's `Recent` section renders clickable chips that load a command into the prompt when tapped.
- Mobile shows a persistent `Recent` peek row between the transcript and the composer with a count plus a one-line preview.
- Prompt Up/Down history, desktop rail recents, and the mobile recent peek load from the same newest-distinct command list and include known commands regardless of exit code.
- Tapping the mobile recent peek opens the same History panel as the mobile menu. Search, filters, and bulk actions live behind a collapsible **history tools** row so the list stays clean until you need the extra controls. Tapping a row opens Run Details, the primary row actions keep **copy command** and **restore** one tap away, and secondary actions such as permalink, delete, compare, project linking, metadata editing, and copy run id live in the row/details action menus. Select mode supports visible-page bulk actions for completed runs and saved snapshots, including project add/remove for runs and delete for selected history items.
- Both views update live as commands are run.

**Limits:** compact recents and Up/Down history use only the newest distinct commands. They stay hidden until history exists and are capped by `recent_commands_limit`. The full desktop and mobile History panel is paginated by `history_panel_limit`.

**Configuration:** `recent_commands_limit` in `config.yaml`; see [CONFIGURATION.md](CONFIGURATION.md).

**Related files:** `app/static/js/shell_chrome.js` (desktop rail), `app/static/js/mobile_chrome.js` (mobile peek + menu), `app/conf/config.yaml`.

---

## Autocomplete

**Purpose:** shell-like completion for commands, flags, files, wordlists, variables, and tool-specific values.

**Behavior:**

- Tool suggestions load from the command registry at page load and use ranked exact, prefix, token-boundary, substring, and fuzzy matching. Matched text is highlighted in green.
- App-owned built-in commands use the same matching engine as YAML-backed tools.
- Workspace file paths and installed wordlist paths match by useful path segments and filename substrings, so users can type the part they remember instead of the beginning of the path.
- Workspace move slots marked as target values suggest loaded session files and folders. `file move` and `mv` suggest sources first, then destination folders (including `/`) once the source is selected.
- Value slots marked as domains, hosts, targets, IPs, URLs, or port sets capture up to 10 recent targets per kind for the active session token. They show back up only in compatible autocomplete slots, and URLs are saved without query strings or fragments. Recents persist across browser restarts and devices when the same `tok_...` session token is active.
- The dropdown opens below the prompt when there is room and flips above when space is tight, preserving top-to-bottom keyboard navigation order.
- `Tab` expands to the longest shared prefix, then cycles matches; `Shift+Tab` cycles backward; `Enter` accepts the highlighted match or runs the command if none is selected.
- While typing a command root, a unique root match shows real example invocations. For commands with scoped subcommands, this includes both root-level and subcommand examples.
- After a known command root plus a trailing space, the dropdown switches to grammar-style suggestions for that tool: root/global flags, subcommands, and positional hints.
- While typing a subcommand token, examples narrow to the matching subcommand once the prefix is unique. For example, `amass s` can show `amass subs ...` examples, while an ambiguous prefix such as `gobuster d` keeps showing `dir` and `dns` token choices.
- After a known subcommand plus a trailing space, the dropdown switches to that subcommand's scoped flags and value hints.
- After `|`, autocomplete switches into the built-in pipe stage (`grep`, `head`, `tail`, `wc -l`, `sort`, `uniq`).
- Already-used singleton-style flags are suppressed from contextual suggestions.

**Limits:** external-tool completions come from the command-registry YAML, while app-owned built-ins come from the app's built-in autocomplete YAML. The app does not inspect the live shell and does not parse `--help` output.

**Configuration:** external-tool suggestions use `conf/commands.yaml` plus optional local overlays; see [CONFIGURATION.md#command-registry-autocomplete](CONFIGURATION.md#command-registry-autocomplete) and [docs/external-command-integrations.md](docs/external-command-integrations.md). App-owned built-ins use `app/services/commands/builtin_autocomplete.yaml`.

**Related files:** `app/static/js/autocomplete.js`, `app/static/js/app.js`, `app/services/commands/builtin_autocomplete.yaml`, `app/conf/commands.yaml`, `app/blueprints/session.py`, `app/core/database.py`.

**Keyboard controls:**

| Key | Action |
|-----|--------|
| **↑ / ↓** | Navigate through suggestions |
| **Tab** | Expand to the longest shared prefix, then cycle suggestions forward |
| **Shift+Tab** | Cycle suggestions backward |
| **Enter** | Accept highlighted suggestion, or run the command if none selected |
| **Escape** | Dismiss the dropdown |

Autocomplete schema and authoring details live in [CONFIGURATION.md#command-registry-autocomplete](CONFIGURATION.md#command-registry-autocomplete).

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

**Limits:** results are capped at 10 entries — narrowing the query further shows deeper matches.

**Configuration:** none — behavior is not user-tunable.

**Related files:** `app/static/js/controller.js` (Ctrl+R keybinding + dropdown), `app/blueprints/history.py` (server-side history query).

---

## Keyboard Shortcuts

**Purpose:** app-safe chords for tab lifecycle, active-tab actions, and readline-style prompt editing, shown through both the `?` overlay and the `shortcuts` built-in.

**Behavior:**

- Tab chords use `Option`/`Alt` to avoid fighting browser `Ctrl`/`Cmd` bindings; terminal chords use `Ctrl` in the readline tradition.
- While the active tab is running, app-level tab, active-tab, and UI shortcuts still work from the prompt. Normal text entry and readline-style editing shortcuts stay blocked until the run finishes, `Ctrl+C` opens the kill confirmation, and `Ctrl+D` stays disabled while the run is active.
- The `?` overlay opens from anywhere on the page (including the empty prompt); `shortcuts` prints the same reference as a text dump.
- Both views read from a single shared list via `GET /shortcuts`, so they cannot drift.

**Limits:** browser-native combos like `Cmd+T`, `Cmd+W`, and `Ctrl+Tab` are optional fallbacks only — browser interception is inconsistent across environments, especially on macOS.

**Configuration:** none — the chord list is defined in `app/services/commands/builtins.py` and not user-tunable.

**Related files:** `app/static/js/features/shortcuts/global_shortcuts.js` (shortcut matching and dispatch), `app/static/js/controller.js` (document keydown cascade), `app/services/commands/builtins_catalog.py` (`_CURRENT_SHORTCUTS`), `app/blueprints/content.py` (`GET /shortcuts`).

Shipped app-safe shortcuts:

| Shortcut | Action | Notes |
|----------|--------|-------|
| `Option+T` (`Alt+T`) | New tab | Preferred app-safe binding |
| `Option+W` (`Alt+W`) | Close current tab | Avoids fighting browser `Ctrl/Cmd+W` |
| `Shift+Option+ArrowRight` (`Shift+Alt+ArrowRight`) | Next tab | Keeps plain Option/Alt+Arrow available for terminal word movement |
| `Shift+Option+ArrowLeft` (`Shift+Alt+ArrowLeft`) | Previous tab | Keeps plain Option/Alt+Arrow available for terminal word movement |
| `Option+Tab` (`Alt+Tab`) | Next tab (Shift reverses) | App-level tab cycling |
| `Option+1` ... `Option+9` (`Alt+1` ... `Alt+9`) | Jump to tab 1 ... 9 | |
| `Enter` / `Escape` in kill confirmation | Confirm / cancel kill | Mirrors modal button intent |
| `Option+P` (`Alt+P`) | Create share snapshot for active tab | |
| `Option+Shift+C` (`Alt+Shift+C`) | Copy active tab output | Kept distinct from terminal `Ctrl+C` |
| `Option+M` (`Alt+M`) | Open/close the Status Monitor | Toggles the modal/sheet with live runs, session health, and idle dashboard metrics |
| `Option+Shift+F` (`Alt+Shift+F`) | Open Files | Leaves `Option+F` / `Alt+F` available for terminal word-forward |
| `Option+Shift+S` (`Alt+Shift+S`) | Open/close Schedules | Leaves `Option+S` / `Alt+S` for transcript search |
| `Option+Shift+W` (`Alt+Shift+W`) | Open/close Watchers | Leaves `Option+W` / `Alt+W` for closing the current tab |
| `Ctrl+L` | Clear current tab output | Shell-style convenience |
| `Ctrl+D` | Close current tab | Same tab-close path as `exit` / `quit` and the tab close button |
| `Ctrl+A` | Move cursor to start of line | Readline-style editing |
| `Ctrl+E` | Move cursor to end of line | Readline-style editing |
| `Ctrl+U` | Delete from cursor to start of line | Readline-style editing |
| `Ctrl+K` | Delete from cursor to end of line | Readline-style editing |
| `Ctrl+W` | Delete one word to the left | Readline-style editing |
| `Option+B` / `Option+F` (`Alt+B` / `Alt+F`) | Move backward / forward by word | Readline-style editing |
| `Option+ArrowLeft` / `Option+ArrowRight` (`Alt+ArrowLeft` / `Alt+ArrowRight`) | Move backward / forward by word | Terminal-style cursor movement |
| `Ctrl+R` | Reverse-history search | Type to filter; Enter runs; Tab accepts without running; Escape restores draft |

Browser-native combos like `Cmd+T`, `Cmd+W`, and `Ctrl+Tab` are intentionally treated as optional fallbacks rather than the primary contract because browser interception is inconsistent across environments, especially on macOS browsers.

The same shortcut reference appears in two places in the shell:

- press `?` from anywhere on the page to open the keyboard-shortcuts overlay — including from the command prompt itself when it is empty. Once any text is present in the prompt (or any other input), `?` types normally so args like `curl "…?foo=bar"` are not interfered with. The handler also skips modifier chords (`Ctrl` / `Meta` / `Alt`) and the welcome-animation active state
- run `shortcuts` in the shell to print the same reference as a text dump inside the current tab

Both views read from the same backend list (exposed to the browser via `GET /shortcuts`), so they cannot drift. The overlay lists the `?` binding itself as the first entry so the shortcut is self-documenting.

---

## Output Streaming and Display

**Purpose:** low-latency SSE streaming with a live tail, per-line prefix toggles (timestamps and line numbers), and explicit recovery cues when the live stream goes quiet and later resumes.

**Behavior:**

- Command output arrives line-by-line over SSE; fast commands batch flushes, slow scans stream each line as it arrives.
- Each output row carries structured `kind` and `role` metadata, so live transcripts, restored history, permalinks, exports, and `/api/v1` streams agree on whether a line is normal output, a notice, a prompt echo, a section header, or another known row type.
- Stored output can be filtered by structured fields in the API and CLI. `darklab grep` and `darklab output` accept selectors for signal, severity kind, structural role, entity value, and entity type, so scripts can pull only findings, only errors, or only lines tied to a specific host/CVE without local JSON parsing.
- The output view follows the live tail automatically, including during bursty runs that repaint quickly. Only a real user scroll-away disables follow mode and shows the tab-scoped jump-to-live / jump-to-bottom helper until the tail is rejoined.
- A live elapsed run-timer sits next to the status pill while a command runs; the final elapsed time is recorded in the exit line.
- Timestamps (elapsed or clock) and line numbers are independently toggleable from the tabbar controls (or the mobile menu). Timestamp fragments stay on each row, while line numbers are assigned once as output is emitted so high-volume commands do not have to renumber thousands of visible rows after `max_output_lines` trimming begins.
- Live output rendering batches bursty streams, skips full transcript scans on normal appends, uses browser content visibility for offscreen rows, and trims old rendered rows without changing the retained raw-output model. Once `max_output_lines` is reached, visible line numbers continue increasing with the command's emitted output order rather than resetting to `1` for the remaining rendered window.
- Very noisy brokered commands automatically enter high-volume output mode after `high_volume_output_line_threshold` received lines. The tab keeps running and counting output, but the browser renders periodic status lines instead of every row until the user chooses to resume live rendering for new output.
- When the SSE stream goes quiet for 45 seconds, the shell shows inline warning copy instead of waiting indefinitely with a spinning run state.
- If the original stream later resumes, the shell prints an inline reconnection success line, restores the tab/HUD to `RUNNING`, re-enables the kill affordance, and continues streaming output in place.
- If a normal command stream detaches while the backend run is still active, the shell reattaches the brokered stream in the original tab when that tab still exists, keeps the run timer tied to the server start time, and prints a clear `[reattached to active run after stream recovery]` notice.

**Limits:** stall detection fires after 45 seconds of silence per tab; each tab has its own stall timeout so concurrent runs don't interfere. Reattach uses the normal brokered run stream and falls back to a recovery tab when the original browser tab is gone.

**Configuration:** timestamp and line-number preferences persist in browser cookies; both are off by default.

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

**Related files:** `app/static/js/runner.js` (client-side kill + confirmation dialog), `app/blueprints/run.py` (`POST /kill`), `app/core/process.py` (`pid_register` / `pid_pop`).

---

## Status HUD

**Purpose:** a persistent desktop status row that brings together run state, connection health, session identity, and environment telemetry without displacing the terminal.

**Behavior:**

- The bottom bar renders eleven live pills on desktop: the left cluster covers run state, connection, and identity; the right cluster carries the output actions (share, copy, save, clear, kill).
- Pills start with a muted `—` placeholder at page load and transition to live values on the first poll.
- Server state is polled via `GET /status` on a visibility-aware cadence: every 3 seconds while the tab is visible and every 15 seconds while hidden. Uptime is interpolated locally between polls so the pill never looks frozen, and the clock ticks once per second in the browser.
- Latency is measured client-side with `performance.now()` around the fetch call.
- On narrow desktop widths the pill row falls back to horizontal overflow scrolling so the right-side HUD actions never get pushed off-screen.
- Mobile hides the HUD entirely; per-tab status and exit codes remain visible inline next to the prompt echo, and the run-notifications toggle in the Options modal covers the background-watch use case.

**Limits:** `/status` always returns 200 even when a component is degraded (reports `"down"` for that component) so HUD polling never flaps the UI or triggers SSE reconnect logic; `/health` remains the load-balancer contract and still returns 503 on degradation.

**Configuration:** the `CLOCK` pill mode is user-tunable from the Options modal (`UTC` or browser-local time). Local mode prefers the browser's short timezone label (for example `CDT`) and falls back to a GMT offset label when the browser cannot provide a stable abbreviation. Run notifications remain a separate Options-modal preference.

**Related files:** `app/static/js/shell_chrome.js` (HUD build + polling), `app/blueprints/assets.py` (`GET /status`).

**Pill reference:**

| Pill | Source | Notes |
|------|--------|-------|
| **STATUS** | Active tab's run state (`running` / `ok` / `fail` / `killed` / `idle`) | Coloured pill identical to the inline tab status dot |
| **LAST EXIT** | Exit code of the most recent finished run in any tab | `0` green, nonzero red, killed red, `—` muted when no run has finished yet; dims to muted while any tab is actively running |
| **TABS** | Total tab count, with active-run annotation (`N · M active`) when any tab is running | Amber while any tab is running, muted when no tabs are active |
| **TRANSPORT** | SSE connection state | Reflects live-stream health; quiet streams can warn inline and then resume without losing the active run |
| **LATENCY** | Round-trip time to `/status` in ms | Green `<250ms`, amber `<500ms`, red `>=500ms` |
| **MODE** | Current shell mode indicator | Shows the active shell mode |
| **SESSION** | Active session identity | `ANON` (muted) for UUID sessions, masked `tok_XXXX••••` (green) for named tokens — see [Session Tokens](#session-tokens) |
| **UPTIME** | Server process uptime | Returned by `/status` and ticked client-side between polls so the pill never looks frozen |
| **CLOCK** | Wall clock in `UTC` or browser-local time | Ticks every second in the browser; local mode prefers the browser's short timezone label and falls back to a GMT offset |
| **DB** | Configured database connection state | `ONLINE` green, `OFFLINE` red |
| **REDIS** | Redis connection state | `ONLINE` green, `OFFLINE` red, `N/A` muted when no Redis is configured |

**Command Constellation:** the Status Monitor visualises recent run history as a constellation chart with a clock-time X axis and a log-elapsed Y axis. By default the X axis auto-fits to your active hours so the canvas stays a full sky rather than a long dead zone: edges with no activity are trimmed, and interior low-density bands (the sleep window of an operator whose runs span both ends of the day) collapse onto a `//` seam marker so the visible canvas reads as continuous clock time. Toggle to **Full day** in the legend if you want strict 24-hour reading; the seam disappears and every hour gets its proportional share of the axis. Hours with no real runs are filled by a desaturated ambient layer, and a clock-pinned daylight gradient paints the 24h cycle behind the stars so noon, dusk, and night always appear at their true hour-of-day positions in either mode. Stars use structured output metadata too: warning/error runs pick up stronger tones, and runs with more findings get a larger plotted point.

---

## Built-In Pipe Support

**Purpose:** narrow app-native pipe helpers (`grep`, `head`, `tail`, `wc -l`, `sort`, `uniq`) that keep common post-filter use cases available without enabling general shell piping or redirection.

**Behavior:**

- One or more supported helper stages can be chained in a single command; the final filtered view is what appears in the terminal, history, permalinks, and exports for that run.
- Autocomplete understands the narrow pipe stage and can guide `grep`, `head`, `tail`, `wc -l`, `sort`, and `uniq` after `command |`.
- Workspace `ls` / `file list` keep their compact one-line display when run directly, but pipe helpers receive short listings as one logical entry per line so common forms like `ls | grep txt` behave like a normal terminal.
- Arbitrary pipes, chaining, and redirection remain blocked at the command-validation layer.

**Limits:** only the six helper stages above are recognised. Combinable flags are supported within a stage (e.g. `sort -rn`) and supported stages can be chained together (e.g. `command | grep pattern | wc -l`).

**Configuration:** none — the supported stage set is hard-coded in `app/services/commands/registry.py`.

**Related files:** `app/services/commands/registry.py` (pipe-stage parser + validator), `app/blueprints/run.py` (applies the pipe filter to streamed output).

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
- `command | grep pattern | wc -l`
- `command | sort -u | uniq -c`

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

## Command Findings

**Purpose:** show high-signal lines from the active tab so operators can review findings, warnings, errors, and roll-up summaries without manually skimming every line of noisy tool output.

**Behavior:**

- The tabbar search control now advertises findings directly as **⌕ search • N findings** when the active tab contains matched findings.
- A compact signal strip beside search shows scoped counts for **F / W / E / S**:
  - **F** — findings
  - **W** — warnings
  - **E** — errors
  - **S** — summary lines
- Clicking a signal chip opens the search bar in that scope immediately. Re-clicking the same chip cycles to the next match in the same way as the search bar’s **↓** button.
- The search bar now supports scope buttons for **text**, **findings**, **warnings**, **errors**, and **summaries**. Scope buttons show live counts, and findings-heavy output opens directly into the **findings** scope.
- Findings are pattern-driven rather than command-whitelisted. Live `/runs` output is classified server-side and carries additive per-line signal metadata through history restore and share/permalink payloads; the browser uses that metadata as the source of truth for counts, scoped navigation, and summaries. The current server matcher is tuned for the tool output the shell already shows most often:
  - open-port, service, and reverse-DNS rows from scanners such as `nmap`, `naabu`, `rustscan`, and `nc`
  - hit rows from `ffuf`, `gobuster`, and related directory fuzzers, with `ffuf` hits tied back to the full URL produced from the command's `FUZZ` template
  - passive domain and IP rows from `assetfinder`
  - severity-tagged result rows from `nuclei`
  - DNS answers and query outcomes from `dig`, `host`, and `nslookup`
  - certificate and TLS verdict lines from `openssl s_client`, `sslscan`, `sslyze`, and `testssl`, including `s_client` certificate subjects, issuers, key details, validity windows, negotiated TLS details, and verification status without treating PEM bodies as findings
- Noise-heavy lines are intentionally excluded from findings when they behave like banners, progress meters, or startup chatter instead of actionable results.
- The same server pass also attaches structured entity metadata to external command output lines when it sees public IPs, hostnames, hashes, or CVE IDs. That metadata is kept with live streams, restored history, saved full-output artifacts, and the Session Entity Atlas without re-parsing transcripts.
- User-killed runs are intentionally **not** counted as errors; the transcript still shows the kill line, but the signal counts stay focused on issues the operator may need to investigate.
- The **summarize** button appends a synthetic **Command Findings:** block to the active tab after the tab is idle. The summary groups external command blocks by server-provided command and target metadata when present, merges repeated runs for the same command/target, collapses duplicate full-command labels with a repeat count, includes only command blocks that produced at least one finding/warning/error/summary line, and falls back to per-command sections when target metadata is unavailable. The button stays disabled while the active tab has a running command so synthetic summary output cannot mix into live command output.
- Run Details shows a compact output summary above restored transcripts, including counts by severity kind, signal, and entity type plus quick outline rows for section headers, key/value rows, and signal-bearing lines.
- If a single command produces per-target metadata for multiple targets, such as `nmap -iL ...` output with multiple `Nmap scan report for ...` sections, the summary splits that one command into separate target sections instead of combining every host's findings together.
- Built-in command output is intentionally excluded from findings, warnings, errors, summaries, and generated command-findings blocks so help/status/catalog text does not create review noise.
- External command help output is also treated as reference text, so examples shown by `-h`, `--help`, and tool-specific help flags do not create findings or Atlas entities.
- Summary blocks are helper UI output, not raw command output. They do not feed back into the signal counters or search matches.

**Limits:** signal detection is server-classified, scoped to the active tab’s transcript, and intentionally favors the project’s supported toolset over arbitrary command output. Browser-side signal fallback is intentionally not used; older restored output without signal metadata is treated as signal-unavailable. A command with no matched findings, warnings, errors, or summary lines does not appear in the generated summary block.

**Configuration:** none — the current scopes, server matchers, and summary format are app-defined and not operator-configurable.

**Related files:** `app/core/output_signals.py` (server-side signal classification), `app/blueprints/run.py` (SSE metadata), `app/services/runs/output_store.py` (signal metadata persistence), `app/static/js/search.js` (metadata-driven scoped navigation and summaries), `app/static/js/controller.js` (chip-to-search navigation), `app/static/js/output.js` (metadata rendering and summary line behavior), `app/static/css/primitives/components.css` and `app/static/css/shell-chrome.css` (tabbar signal controls).

---

## Session Entity Atlas

**Purpose:** browse the entities the shell has seen across saved external runs, without starting from a specific project or transcript.

**Behavior:**

- Open **Atlas** from the desktop rail, mobile menu, `Alt+A`, History row actions, Run Details, or a project filtered view.
- Atlas groups saved entities by **Findings**, **Hosts/IPs**, **Domains**, **Hashes**, **CVEs**, and **URLs**. Entity rows show the canonical value, hit count, source-run count, project links, and labels.
- Atlas search matches entity values plus Atlas labels and notes, so curated metadata is as findable as values copied from command output.
- Atlas can be scoped to one source run from Run Details or from the Atlas run filter. The filter applies across the Findings queue, entity tabs, tab counts, and entity exports until you clear the visible run chip.
- Run Details shows the source run's Atlas entity count and includes paged entity tabs for the same entity types, so you can inspect generated hosts, domains, hashes, CVEs, and URLs without leaving the run modal.
- Entity details page through source runs and findings when an entity appears across more rows than fit in one view, so older evidence stays reachable without loading the whole collection at once.
- Saved views remember useful Atlas filter sets for the active session token, including search text, source run, orphan filter, suppression filter, Findings review state, and project scope. Applying a saved view keeps you on the current Atlas tab, and **Clear filters** returns the visible filter controls and saved-view picker to their defaults while keeping a project-scoped Atlas launch anchored to that project.
- On mobile, Atlas uses a list/detail flow with Back navigation, compact filters, bottom-sheet actions, and select mode from the overflow menu so entity triage fits the same touch pattern as Projects and History.
- The **Findings** tab works as the cross-run triage queue. It lists deduped findings, supports text, project, source-run, and review-state filters, opens finding detail with source-run and entity navigation, and can update or delete selected visible findings in bulk.
- Selecting an entity opens a detail side sheet with first/last seen times, project links, labels, notes, cached intel snapshots, source runs, and related findings.
- Select mode adds checkboxes on the visible page for any Atlas tab. You can suppress or restore selected noisy rows without deleting source data, delete selected findings directly, or delete selected entities and their attached findings in one confirmed action.
- Entity tokens in saved and live transcripts can open Atlas directly. Long-pressing or right-clicking a token opens quick actions for copying the value, refreshing intel, editing metadata in Atlas, or refocusing the transcript line.
- **Refresh intel** fetches current app-native intel for that entity and stores normalized provider snapshots back on the entity.
- **Clean Atlas** on a source run removes that run's Atlas links while keeping the run transcript in History. Disposable single-source rows can be removed at the same time, while curated rows are kept by default when they have a project link, project-visible finding relationship, label, note, or review state. Cleanup confirmations include a separate opt-in when you really do want to delete those curated single-source rows too.
- **Add to active project** links the entity to the current project without copying it. Project-filtered Atlas opens show only the entities linked to that project.
- Labels and notes use the same metadata editor model as History, Files, and Projects, so entity notes stay attached to the entity wherever it appears.
- Entity tabs can export the current Atlas filter as CSV or JSONL. Exports include summary fields, suppression state, labels, notes, project names, and provider names that have cached intel, but they leave raw provider response bodies out.

**Limits:** Atlas only includes entities materialized from saved external-run output after the entity store was added. Built-in commands do not create Atlas entities.

**Configuration:** Atlas uses existing history retention, intel cache, and provider-secret settings. Provider keys are managed through Options → Secrets or `secret set NAME`.

**Related files:** `app/blueprints/atlas.py`, `app/services/atlas/`, `app/static/js/features/atlas/`, `app/static/css/features/atlas.css`, `app/static/css/features/atlas-mobile.css`, `app/core/output_signals.py`.

---

## Copy, Save, and Export

**Purpose:** keep copy-to-clipboard and download-output actions (`txt` / `html` / `pdf`) consistent across the desktop HUD, Run Details, mobile menu, and permalink page.

**Behavior:**

- **Copy** copies the full plain-text output to the clipboard.
- **save ▾** is a dropdown with three export formats:
  - **txt** — plain-text file with a timestamped filename.
  - **html** — themed HTML file with ANSI colors preserved, renders correctly in a browser without the shell; fonts and theme colors are inlined so the file is fully self-contained.
  - **pdf** — themed PDF rendered entirely in the browser via jsPDF, no server round-trip; includes the app header, command, exit-status badge, timestamp, and full ANSI output while following the same header/meta ordering and transcript-preparation model as the browser-rendered permalink and saved-HTML surfaces.
- The same `save ▾` dropdown is available on the desktop HUD bar, the Run Details header for saved runs, the permalink page header, and the mobile menu, so the export experience is consistent across all surfaces.
- Permalink pages and saved HTML exports include a **highlights** toggle. Turning it off hides finding badges and removes entity-token styling from dense output while keeping the original text and structured metadata available.
- The browser-rendered parity target is permalink/share page ↔ saved HTML. PDF is intentionally treated as a best-effort renderer against that same browser baseline rather than a separately styled surface.

**Limits:** local text exports produce unredacted output. Local HTML/PDF exports also stay unredacted, except for raw-only app-native intel response bodies, which are replaced with an omission notice so provider data does not leave the browser as styled share/export content.

**Configuration:** none — export formats and filename shape are not user-tunable.

**Related files:** `app/static/js/tabs.js` (per-tab save menu), `app/static/js/shell_chrome.js` (HUD save menu), `app/static/js/features/history/history_run_details.js` (saved-run export menu), `app/static/js/export_html.js` (shared browser export model), `app/static/js/export_pdf.js` (jsPDF renderer consuming the shared model), `app/static/js/permalink.js` (permalink/share save actions), `app/static/css/terminal_export.css` (shared browser export chrome).

---

## Tabs & Run History

**Purpose:** multi-tab workspace with per-session run history, full-text search over commands and output, starring, and reload-safe reconnection to in-flight runs.

**Behavior:**

- Each command runs in the active tab; the **+** button opens additional tabs for side-by-side sessions. Tabs show a status dot (amber running, green success, red failed/killed) and start with labels such as `shell 1`, `shell 2`, and `shell 3`. Commands that keep running past the brief visual grace period show temporarily in the tab label, then the tab returns to its stable label when the command finishes. Double-click to rename, drag to reorder, tab-scroll arrows when more tabs are open than fit the window width. Draft input is preserved per tab.
- The **⧖ history** button opens a slide-out drawer listing persisted session history with a `type` filter for **all**, **runs: all**, **runs: built-in**, **runs: external**, and **snapshots**. Run rows open Run Details on click; each row also has a toggleable **star** plus **copy command**, **restore**, **permalink**, **delete**, and project-aware **more** actions for external runs. External run rows show their Atlas entity and finding counts when structured Atlas data exists. Snapshot rows show the snapshot label and created time plus **open** / **copy link** / **edit** / **delete** actions. Run and snapshot rows surface existing label badges and note indicators so project/workflow context is visible without opening another modal. The **restore** action loads the run's output into a tab with the command shown as a styled prompt line (activating an existing matching tab when one exists). Starred runs list before unstarred ones regardless of age. Star state persists server-side per session and follows named session tokens.
- Select mode adds checkboxes for completed runs and saved snapshots on the visible page. **Select all**, **Clear**, and the top-level **Actions** menu let you add selected external runs to the active project, add them to a chosen project, remove them from linked projects, or delete selected history items in one pass. Bulk project actions skip runs that are already in the requested state instead of failing the whole request, and running rows are not selectable for bulk delete.
- The History row and Run Details **more** menus are project-aware for external runs: unlinked runs offer **add to active project** and **add to project**, while runs that are already linked to one or more projects show **remove from project** instead. Removing a run from a project can also remove same-run disposable Atlas entity links from that project, with a separate checkbox for curated entity links and counts for findings that will leave the Project Findings tab. Built-in runs stay in History without project-link actions.
- When full-output persistence is enabled, the history drawer's permalink points at the complete saved artifact; loading into a tab still uses the capped preview and shows a notice linking to the permalink if truncated. The active tab's **share snapshot** action creates a separate `/share/<id>` snapshot and can optionally redact before saving.
- The **delete all** button in History prompts **Delete all** / **Delete Non-Favorites** / **Cancel** to separate destructive deletion from starred-only cleanup.
- If the page reloads mid-run, the shell restores a running placeholder tab with the kill action available and subscribes back to the brokered `/runs/<run_id>/stream` for replay plus live output when events are still retained. Active-run recovery is client-aware: another browser using the same session token can see the live run in Status Monitor without automatically creating a terminal tab or taking over the stream. Non-running tabs restore separately from `sessionStorage` with labels, transcript previews, statuses, and draft input preserved; restored completed tabs remount a live prompt immediately.

**Limits:** tab count capped by `max_tabs`; history surfaces paginate stored items rather than showing one unbounded list; brokered live replay is bounded by configured replay retention and `max_output_lines`, after which completed-run restore relies on persisted history/output artifacts. Snapshot search matches the snapshot label, not the full snapshot body content.

**Configuration:** `max_tabs` in `config.yaml` (default 8; `0` for unlimited).

**Related files:** `app/static/js/tabs.js` (tab lifecycle + drag + rename), `app/static/js/history.js` (history drawer + search UI), `app/blueprints/history.py` (history API + search queries), `app/core/database.py` (database schema, startup migration, and retention pruning).

**Full-text search:** the history surfaces support a shared `type` filter, run-subtype filters, project filters for linked runs, and full-text search across command text and stored run output for run rows, with additional filters for command name, exit status, recent date range, starred-only, and structured output selectors such as `signal:findings`, `kind:error`, `kind!=info`, `role:exit-fail`, `entity:darklab.sh`, and `entity_type:cve`. The drawer also exposes `signal`, `kind`, `entity`, and `entity_type` as visible controls, so common structured-output searches don't require memorizing query syntax. The search field placeholder reads "search history". Search is backend-aware: SQLite uses `runs_fts` with a `LIKE` fallback for short terms, while Postgres uses substring `ILIKE` clauses backed by `pg_trgm` indexes. When full-output persistence is enabled, `output_search_text` is populated from the complete gzip artifact so early lines of long runs stay reachable; otherwise it falls back to the capped preview window. Snapshot search matches the snapshot label only, and snapshots remain share/history records rather than project-linked records. On mobile, search, advanced filters, and bulk actions stay behind the dedicated **history tools** toggle to preserve result space; the command-name field uses app-owned autocomplete, and row actions keep the sheet open where that matches the desktop action contract. Ctrl+R stays command-only so reverse history search keeps normal shell expectations.

On mobile, the **☰** menu in the top-right header opens a bottom-sheet that groups session-scoped actions (search, clear, line numbers, timestamps) and overlays (options, history, status, commands, workflows, files, theme, FAQ, diag) — see the Mobile Shell section below for the full layout.

---

## Run Comparison

**Purpose:** compare two saved runs without manually switching between transcripts, while preserving enough surrounding context to understand what changed.

**Behavior:**

- Run comparison can launch from the History drawer, Run Details modal, mobile History panel, and Projects modal. Project-scoped comparison uses the same canonical compare flow as History after resolving the selected linked runs or baseline label.
- Transcript comparison strips app chrome lines before diffing, keeps each run's original output order, and aligns changed hunks across Run A and Run B. Unchanged context is folded by default with **Show unchanged lines** controls and lazy expansion for large equal regions.
- Users can switch between responsive view modes: automatic for the current screen, side-by-side where space allows, unified, changes-only, and findings-only. Context controls expose compact, expanded, and all-context views for the current comparison without changing the user's saved default options.
- **Prev change** and **Next change** navigate between changed transcript regions. Restore actions can load Run A, Run B, or both runs back into terminal tabs, and **Copy summary** creates a concise text summary of the comparison.
- Findings and run-owned artifacts are compared as objects rather than raw line positions. This keeps matching findings/artifacts stable even when tools emit the same results in a different order. Added, removed, and changed object groups include per-side totals and truncation metadata.
- Mobile uses the same comparison overlay with stacked output panes, mobile-safe dropdown placement, and touch-friendly controls.

**Limits:** comparison is optimized for saved run history, not live streams. Very large equal regions are summarized until expanded, and backend byte/hunk caps protect the compare payload from unbounded responses.

**Configuration:** compare view and compare context defaults are saved user options. Server-side compare limits are fixed application constants rather than operator-facing `config.yaml` settings.

**Related files:** `app/services/runs/comparison.py` (shared compare helpers), `app/blueprints/history.py` (history compare routes), `app/blueprints/projects.py` (project compare route), `app/static/js/features/run-comparison/` (compare launcher, controls, navigation, and renderer), and `app/static/css/features/run-comparison.css` (desktop/mobile compare layout).

---

## Guided Workflows

**Purpose:** curated and user-saved multi-step diagnostic sequences that turn repeat checks into reviewable command playbooks.

**Behavior:**

- Workflows are listed in the **Workflows** panel on desktop and behind the mobile ☰ menu; user-created workflows appear above the built-in catalog under **My workflows**.
- Clicking a step pre-fills the prompt with its `cmd`; each step can also be run directly, and `Run all` queues the rendered steps sequentially in the active tab.
- The **New** workflow editor saves session-scoped workflows with a title, description, ordered command steps, optional notes, and `{{variables}}` inferred from the commands.
- The terminal-native `workflow` command supports `workflow list`, `workflow show <name>`, and `workflow run <name> [--variable value ...]`; missing required variables are prompted transcript-style before the run is queued.
- Each step can show a short `note` explaining what the command checks.
- User-created workflows are stored with the active session and migrate with session tokens.
- Built-in workflows cover DNS troubleshooting, TLS/HTTPS checks, HTTP triage, quick reachability, email server checks, passive domain recon, subdomain enumeration and validation, web directory discovery, SSL/TLS deep dives, CDN/edge behavior checks, API recon, network path analysis, fast port/service triage, and Files-backed chained recon such as subdomain HTTP triage and crawl-and-scan.
- Custom workflows can be added to `conf/workflows.yaml`; the file is re-read on every request so edits take effect without a restart.
- Workflows that depend on Files can declare `feature_required: workspace`; those entries are hidden when `workspace_enabled` is off.

**Limits:** step commands still run through the command policy — a workflow step is only usable if its `cmd` is permitted by `commands.yaml`.

**Configuration:** `conf/workflows.yaml` — operator-defined workflow entries use the same normalized shape as saved user workflows. User-created workflows store that shape in the session database, while `conf/workflows.yaml` keeps deployment-wide entries in YAML.

```yaml
- title: "My Custom Check"
  description: "A brief description shown in the workflow panel."
  inputs:
    - id: domain
      label: "Domain"
      type: domain
      required: true
      placeholder: "example.com"
      default: "darklab.sh"
  steps:
    - cmd: "ping -c 4 {{domain}}"
      note: "Is the host reachable?"
    - cmd: "nmap -F {{domain}}"
      note: "What ports are open?"
```

- `title` — required; workflow heading.
- `description` — optional; shown below the title.
- `inputs` — optional list of template variables that can be referenced as `{{id}}` inside step commands and notes.
- `id` — required per input; lowercase letters, numbers, and underscores.
- `type` — optional per input; accepted values are `text`, `domain`, `host`, `url`, `port`, and `path`.
- `required`, `placeholder`, `default`, and `help` — optional per input; used by the Workflows panel, `workflow run` prompting, and runtime autocomplete.
- `steps` — required list; each step needs at least a `cmd`.
- `cmd` — required; loaded into the prompt when the step is clicked and rendered with workflow inputs when variables are present.
- `note` — optional; helper text shown alongside the command.
- `feature_required` — optional feature gate such as `workspace`; hides the workflow when the required app feature is disabled.

**Related files:** `app/conf/workflows.yaml` (operator workflow definitions), `app/services/workflows/user_workflows.py` (session workflow storage), `app/static/js/app.js` (workflow editor and CLI), `app/static/js/shell_chrome.js` (Workflows panel rendering), `app/blueprints/content.py` and `app/blueprints/session.py` (workflow API endpoints).

---

## Scheduled Runs

**Purpose:** recurring commands that keep running on a cadence after the browser tab is closed.

**Behavior:**

- The **Schedules** modal opens from the desktop rail or mobile menu and lists schedules owned by the active durable `tok_` session.
- Each schedule stores one command, an optional label, an enabled/paused state, an IANA timezone chosen from a dropdown, and either an hourly/daily/weekly preset or a five-field cron expression.
- The editor previews the next three fire times before saving. Preview timing is computed by the server and displayed in the selected schedule timezone, so the browser uses the same cron rules as the worker.
- Saved schedules can be edited, paused, resumed, deleted, refreshed, or fired immediately from the modal. Manual fires use the same audit path as worker-fired runs.
- The modal asks before closing, refreshing, opening a fired run, or switching schedules when the current form has unsaved changes.
- Fired runs appear in normal History with a `scheduled` badge. Clicking that badge, or the Schedule row in Run Details, reopens the schedule that created the run.
- Run Details includes **Schedule this command**, which opens the Schedules modal with the completed run's command already filled in.
- The schedule detail view shows recent fire audit rows. Fired rows can open the resulting Run Details modal, and rows with an older completed fire on the current page can compare against that previous fire.
- If the owning session token is revoked, the worker disables the schedule and the browser shows it as paused instead of deleting it.

**Limits:** schedules require a durable session token. Anonymous sessions cannot create schedules because there is no durable owner for the worker to enforce after the browser closes. Cron support is strict five-field POSIX cron, and custom cron expressions cannot run more often than every five minutes. Workflow scheduling, blackout calendars, and per-target schedules are out of scope.

**Configuration:** scheduler settings live under `scheduler` in `config.yaml`, including `max_per_session`, `default_timezone`, `tick_seconds`, `max_catchup_window_seconds`, `missed_fire_policy`, and the SQLite `lock_path`. See [CONFIGURATION.md](CONFIGURATION.md) and [docs/schedules.md](docs/schedules.md).

**Related files:** `app/blueprints/schedules.py` (browser schedule routes), `app/services/scheduler/` (cron, storage, dispatch, and worker helpers), `app/static/js/features/schedules/schedules_modal.js` (Schedules modal), `app/static/css/features/schedules.css` (modal layout), and `docs/schedules.md` (operator guide).

---

## Watchers

**Purpose:** recurring change checks that compare each new run against a captured baseline run.

**Behavior:**

- The **Watchers** modal opens from the desktop rail, mobile menu, or Run Details.
- Run Details and the History drawer action menu include **Create watcher from this baseline**, which opens the modal with the completed run already selected as the baseline.
- New watchers can use **First run** mode, which captures the first successful watcher fire as the baseline without needing an existing run id.
- The Baseline run field includes a short helper card for operators who prefer to paste a run id manually in **Existing run** mode.
- Each watcher owns a schedule, reruns the watched command on that cadence, and compares each completed watcher run against the current baseline.
- Watcher textual diffs ignore progress/status-line/PTY chrome and include entity-set deltas in the saved summary, so noisy redraws do not look like real changes and newly observed hosts, URLs, hashes, or CVEs are easier to spot.
- Watcher rows show whether the latest check is `ok`, `pending baseline`, `changed`, `firing`, `paused`, or `error`.
- The detail pane shows the last diff summary, recent fire audit rows with expandable diff details, links back to the runs created by watcher fires, and a direct Compare action for baseline-vs-fire review.
- Empty checks still appear in the fire audit as `diff_kind='none'`, so it's clear the watcher is still running even when nothing changed.
- Operators can pause, resume, manually fire, delete, or accept the latest run as the new baseline from the modal. Accepting a baseline asks for confirmation because it discards the previous comparison point.
- The modal asks before closing, refreshing, opening a watcher run, or switching watchers when the current form has unsaved changes.

**Limits:** watchers require a durable `tok_` session token. Anonymous sessions cannot create watchers because the scheduler needs a stable owner. First-run watchers require a command because there is no completed run to inherit from yet. Watchers monitor one baseline command at a time, use the same five-minute minimum custom cron interval as schedules, and keep bounded diff summaries rather than unlimited raw diff payloads.

**Related files:** `app/blueprints/watchers.py` (browser watcher routes), `app/services/watchers/` (watcher state, diff classifiers, finalization, and fire audit helpers), `app/static/js/features/watchers/watchers_modal.js` (Watchers modal), `app/static/css/features/watchers.css` (modal layout), and `docs/watchers.md` (operator guide).

---

## Permalinks

**Purpose:** stable, shareable URLs for individual runs and full-tab snapshots, persisted through the configured database and subject to `permalink_retention_days`.

**Behavior:**

- **Tab snapshot** (`/share/<id>`) — **share snapshot** on any tab captures the current output and, when a full saved artifact exists, shares that full output as a snapshot. The resulting URL opens a styled HTML page with ANSI color rendering, a `save ▾` dropdown (txt, html, pdf), a **copy** button, a **view json** option, and a link back to the shell. Honors the browser's saved line-number and timestamp preferences on load. Uses the Web Share API where supported; otherwise copies the URL to the clipboard. Recommended sharing path.
- **Single run** (`/history/<run_id>`) — the permalink button in the history drawer links to an individual run. Serves the full saved artifact when persistence is enabled; otherwise the capped preview stored in the configured database. Honors saved line-number and timestamp preferences on load.
- Both permalink types persist across container restarts through the configured database and any file-backed artifacts under `./data`.

**Limits:** retained for `permalink_retention_days` only; the `./data` directory is the only writable path in an otherwise read-only container (created automatically on first run).

**Configuration:** `permalink_retention_days` in `config.yaml` (default 365).

**Related files:** `app/blueprints/history.py` (share + permalink routes), `app/services/history/permalinks.py` (ID generation + storage), `app/services/runs/output_store.py` (full-output artifact lookup), `app/templates/permalink.html` (rendered share/permalink page).

---

## Share Redaction

**Purpose:** optional masking of common secrets and infrastructure details (bearer tokens, emails, IPs, hostnames) on snapshot permalinks, with a persistent raw-vs-redacted default controlled by the Options modal.

**Behavior:**

- When creating a share snapshot, the shell can prompt whether to share raw or redacted output.
- A built-in redaction baseline masks common secrets and infrastructure details; operators can append custom regex rules on top.
- App-native `intel` response bodies are raw-only for sharing: snapshot payloads replace those lines with `Intel data omitted from share` even when the user chooses raw sharing.
- Once a raw/redacted choice is saved as the persistent default in the [Options modal](#options-modal), subsequent share actions skip the prompt and reuse that choice — whether sharing is triggered from the prompt flow or directly from the Options modal.
- Redaction applies only to the snapshot payload; the stored run history is never modified.

**Limits:** local text exports from a tab are not redacted. Local HTML/PDF exports follow the same raw-only intel omission rule as share pages, but ordinary regex redaction is scoped exclusively to the share-permalink flow.

**Configuration:** baseline rules are built in; custom regex rules extend them. The raw-vs-redacted default is stored in the Options modal.

**Related files:** `app/core/redaction.py` (baseline + custom rule engine), `app/blueprints/history.py` (snapshot redaction entry point), `app/static/js/tabs.js` (share snapshot prompt + default handling).

---

## Mobile Shell

**Purpose:** a dedicated touch layout with its own composer, keyboard helper row, recent-run peek, and bottom-sheet menu, so the shell remains usable on phones without inheriting desktop chrome patterns that don't translate.

**Behavior:**

- **Mobile composer dock** — a visible composer with its own Run button replaces the desktop inline input.
- **Keyboard helper row** — touch targets above the keyboard provide `Home`, `End`, single-character left/right moves, word-left / word-right jumps, delete-word, and delete-line without needing a hardware keyboard.
- **Recent peek + History panel** — an idle peek row between transcript and composer shows the recent-run count plus a one-line preview; tapping it opens the same History panel as the mobile menu. Search, filters, and bulk actions stay collapsed behind **history tools** until needed.
- **Output follow** — when the keyboard opens, the active output re-sticks to the bottom so the last line stays visible.
- **Stable layout** — the mobile shell uses a normal-flow layout that avoids Firefox keyboard flash, gap, and floating-composer regressions.
- **Shared state** — desktop and mobile Run buttons stay in sync: both disable together for blank prompts and running tabs.
- The **☰** menu in the top-right header opens a bottom-sheet with two grouped sections: a **session** group (search, clear, line numbers toggle, timestamps picker) that affects the current terminal in place, and an **overlays** group (options, history, status, commands, workflows, files, theme, FAQ, diag). The sheet closes through the backdrop, Escape, or the shared grab/drag contract rather than a visible `X` button. `clear` wipes the active tab's output while preserving its run state; `line numbers` is a single on/off row; `timestamps` expands inline into a three-mode picker (off / elapsed / clock). The History panel's search, filters, and bulk controls stay behind a dedicated **history tools** toggle to preserve result space.

**Limits:** the diag entry appears only for clients whose IP matches `diagnostics_allowed_cidrs`. The mobile layout activates on touch-sized viewports — desktop browsers at narrow widths keep the desktop chrome.

**Configuration:** no mobile-specific config keys beyond `diagnostics_allowed_cidrs`; layout activates automatically on touch viewports.

**Related files:** `app/static/js/mobile_chrome.js` (mobile shell bootstrap + composer + menu), `app/static/css/mobile.css` (mobile layout + composer + bottom-sheet styles), `app/static/css/mobile-chrome.css` (shared mobile sheet chrome), `app/templates/index.html` (mobile-shell mount points).

---

## Built-In Commands

**Purpose:** native shell helpers that provide session introspection, guidance, and guarded responses without dispatching to external binaries.

**Behavior:**

- The shell ships several categories of built-ins, each rendered as terminal-native output rather than modal UI.
- Built-ins run entirely inside the app layer, so they remain available even when the corresponding external tool does not exist in the container.

**Utility commands**

- `help`, `commands`, `history`, `last`, `limits`, `retention`, `status`, `runs`, `jobs`, `stats`, `config`, `theme`, `which`, `type`, `wordlist`, `faq`, `banner`, `fortune`, `shortcuts`, `clear`, `exit` / `quit`, `version`, and `whoami` are available in every session.
- `status` prints a compact session summary: masked active session ID, session type, run count, snapshot count, starred-command count, whether saved Options exist for the session, session-variable count, active-run count, compact session file usage when Files are enabled, and the current instance-level save/retention limits.
- `runs` prints app-native active-run metadata for the current session, including CPU percent derived from cumulative CPU seconds over run elapsed time, RSS-memory snapshot, and a hint that the desktop `STATUS` HUD pill opens real-time monitoring; `jobs` is a compatibility alias for the same terminal output. `runs -v` also prints full run IDs, started timestamps, cumulative CPU time, and active-run metadata source, while `runs --json` prints the active-run snapshot in JSON for debugging or automation. On desktop, the `STATUS`, `LAST EXIT`, and `TABS` HUD pills open the Status Monitor modal, and `Option+M` / `Alt+M` toggles the same view. The monitor is also available from the desktop rail and mobile menu, stays useful when idle with system/resource/session cards and visual history widgets, lists active commands as divided rows, exposes Attach/Kill actions for visible active runs, and shows best-effort CPU and RSS memory telemetry as circular meters/sparklines with memory fill normalized against 1 GB when backend process stats are available.
- `stats` prints session activity totals and external-tool command-root breakdowns: runs, snapshots, starred commands, active runs, success rate, average duration, and the top non-built-in command roots by run count.
- `project` manages case folders from the terminal: list/create/use/rename/current/clear/archive/unarchive/delete, link or unlink runs, link the last eligible run, and list/add/quick-add/remove project targets.
- `schedule` manages saved recurring commands, while `watch` turns a completed baseline run into a recurring change-detection monitor.
- `cd [folder]`, `pwd`, `file list [-l] [folder]`, `file show <file>`, `file add [file]`, `file add-dir <folder>`, `file edit <file>`, `file download <file>`, `file move <source> <destination>`, and confirmed `file delete [-r|-f|-rf] <file-or-folder>` / `file rm [-r|-f|-rf] <file-or-folder>`, plus the convenience aliases `ls [-l] [folder]`, `cat <file>`, `mkdir <folder>`, `mv <source> <destination>`, and confirmed `rm [-r|-f|-rf] <file-or-folder>`, expose keyboard-first access to the current session files when workspace storage is enabled. `cd` is tab-local and treats the session workspace root as `/`; relative file commands resolve from that tab's current workspace folder. `file add` opens a blank file editor, `file add <file>` opens the same editor with the file name prefilled, `file add-dir` / `mkdir` creates a folder, `file download <file>` starts a browser download, and `file move` / `mv` move or rename a file or folder. `file list` / `ls` list the current folder non-recursively in short form by default; `file list -l` / `ls -l` show the long listing with type, size, and modified columns.
- `grep`, `head`, `tail`, `wc -l`, `sort`, and `uniq` also work as standalone workspace-file commands, for example `grep -i admin targets.txt`, `head -n 20 output.txt`, `wc -l urls.txt`, and `sort -u names.txt`. They reuse the same constrained helper implementation as built-in pipe stages and never expose arbitrary shell piping or host filesystem access.
- `theme` lists and applies runtime theme variants from the terminal. `config` lists, reads, and updates user options such as line numbers, timestamps, welcome behavior, share redaction defaults, run notifications, and HUD clock mode.
- `ps` lists currently running processes for the session (PID, TTY, STAT, START, CMD columns), or shows a `no running processes` notice when idle.

**Shell identity commands**

- `env`, `pwd`, `uname`, `uname -a`, `id`, `groups`, `hostname`, `date`, `tty`, `who`, `uptime`, `ip a`, `route`, `df -h`, and `free -h` return stable shell-style information without exposing host internals. When Files are enabled, `pwd` is handled by the workspace layer and prints the active tab's workspace path.

**Guardrail commands**

- `sudo`, `reboot`, `poweroff`, `halt`, `shutdown now`, `su`, and the exact `rm -fr /` / `rm -rf /` patterns return explicit shell responses instead of pretending to run or silently failing.

**`man` support**

- `man <allowed-command>` renders the real man page when tooling exists.
- `man <built-in-command>` shows the built-in command summary instead.

**Limits:** built-ins intentionally cover only app-owned helpers and a narrow set of shell-identity responses. They are not a general shell-emulation layer.

**Configuration:** none. Built-in commands are defined in application code, not in operator config.

**Related files:** `app/services/commands/builtins.py` (built-in command registry + output rendering), `app/services/commands/registry.py` (dispatch, autocomplete loading, and man routing), `app/services/commands/builtin_autocomplete.yaml` (built-in autocomplete grammar), `app/static/js/app.js` (dynamic autocomplete hooks, client-side command flows, and Options/theme command handling), `app/static/js/runner.js` (client-side command interception).

---

## Headless API and CLI

**Purpose:** run commands and read saved data from scripts, CI jobs, or a local terminal without driving the browser shell.

**Behavior:**

- `/api/v1` authenticates with existing `tok_...` session tokens and rejects anonymous browser UUID sessions.
- API-started runs use the same command validation, registry rewrites, runtime checks, brokered stream, history persistence, Atlas capture, and project capture behavior as browser-started runs.
- Scripts can start non-interactive runs, wait for final run status, stream broker events as SSE or NDJSON, cancel active current-session runs, read history/ranged output/artifacts, search saved output with line context, inspect Atlas entities and findings, download run artifacts by stable artifact id, inspect project data, manage scheduled commands and outbound notification channels, read notification delivery audits, and link or unlink completed external runs from active projects.
- API streams start with a schema row and then send typed output rows with backward-compatible `type` and `text` fields; see [docs/api.md](docs/api.md#streaming) for the stream shape.
- Saved schedules fire through the same brokered run path as manual runs. History rows and Run Details mark scheduled runs with their schedule id, and revoked tokens or overlapping prior runs leave clear fire-audit rows instead of failing silently.
- History responses include the same batched artifact, finding, Atlas entity, and Atlas finding counts shown in History and Run Details.
- The bundled `darklab` CLI wraps the API with `whoami`, `run`, `active`, `tail`, `cancel`, `history`, `grep`, `show`, `output`, `artifacts`, `atlas`, `projects`, `project`, `project-findings`, `project-runs`, `project-entities`, `project-packages`, `schedule`, `notify`, `completion`, and `download` commands. `darklab run --wait` waits for final status for shell scripts, `darklab active` lists current jobs for the token, `darklab run --link-project NAME` resolves friendly project names before linking completed external runs, `darklab grep <pattern>` searches saved output across runs, `darklab atlas ...` reads Atlas summary, source runs, entities, and findings, `darklab schedule ...` manages saved recurring commands, `darklab notify ...` manages notification channels without accepting plaintext secrets on the command line, `darklab completion bash|zsh|fish` prints static shell completion, and `darklab completion install --shell auto` installs it into the current user's shell-completion directory. Live tailing fails clearly if a stream closes before the run reaches an exit, killed, or error event, and Ctrl+C while following output detaches without cancelling the server-side run.
- CLI configuration uses flags first, then `DARKLAB_API_URL`, `DARKLAB_TOKEN`, and `DARKLAB_TIMEOUT`, then the TOML file at `~/.config/darklab/config.toml`.

**Limits:** API v1 is intentionally non-interactive. It does not expose Interactive PTY start/input/resize routes, general project mutation routes, workflow execution, API-only token scopes, or workspace ZIP downloads.

**Configuration:** no server-side API-specific settings. CLI users can set `DARKLAB_API_URL`, `DARKLAB_TOKEN`, `DARKLAB_TIMEOUT`, or `~/.config/darklab/config.toml`; see [docs/api.md](docs/api.md).

**Related files:** `app/blueprints/api_v1.py` (`/api/v1` routes), `app/services/api_v1/` (auth, serialization, and OpenAPI helpers), `docs/api.md` (user guide), `docs/api-v1-openapi.json` (checked-in OpenAPI snapshot), `scripts/generate_api_openapi.py` (OpenAPI generator), and `tools/darklab_cli/` (bundled CLI package).

---

## Outbound Notifications

**Purpose:** send queued app events to destinations outside the browser so long-running work can report back even when the tab is not in front of you.

**Behavior:**

- Durable `tok_` sessions can manage outbound channels from the Options **Notifications** tab, `/api/v1/notification-channels`, or `darklab notify`.
- Supported destinations are generic JSON webhooks, Slack incoming webhooks, Discord incoming webhooks, Telegram Bot API chats, Pushover, and SMTP email.
- Channel secrets are write-only. Webhook URLs, bot tokens, Pushover tokens, and related secret values are stored through the encrypted vault; list responses only say whether each required secret is configured.
- SMTP email uses operator-owned transport settings from `notifications.smtp.*`, while each email channel chooses its recipients and optional reply-to address.
- External non-PTY run finalization queues a `run_complete` notification with the configured `app_name`, run id, command root, exit code, token hint, and summary counts. Built-in commands and PTY sessions do not send `run_complete` by default.
- The trigger list also includes `pty_session_ended`, `scheduled_run_failed`, `watcher_changed`, `watcher_error`, `watcher_recovered`, and `test`; a channel sends only when a matching app source queues that trigger.
- Test sends use the same queue and delivery path as real notifications, so a successful test verifies both channel config and delivery plumbing. Muted channels stay configured but do not queue test sends or other deliveries until unmuted.
- Delivery events are queued, claimed by the notification worker, retried with backoff when failures are retryable, and moved to dead-letter state when attempts or retry age are exhausted. Sent delivery audit rows are pruned after the configured retention window.
- Webhook-style channels reject non-public destinations by default, with an operator allowlist for trusted internal receivers.
- Delivery audit rows are available from each channel's **Deliveries** control in the Options **Notifications** tab, through `/api/v1/notification-events`, and through `darklab notify events`; the CLI can also update, mute, unmute, test, and delete channels.

**Limits:** anonymous browser sessions cannot create outbound channels. Email channels require SMTP settings before they can be saved or tested. Channel payloads are intentionally compact and should still be sent only to destinations you trust.

**Configuration:** `notifications.*` controls do-not-disturb, per-channel delivery rate, HTTP/test timeouts, private webhook destination allowlisting, SMTP transport, sent-event retention, and retry behavior. `app_name` controls outbound titles/messages. See [CONFIGURATION.md](CONFIGURATION.md) and [docs/notifications.md](docs/notifications.md).

**Related files:** `app/services/notifications/` (channel registry, payload builders, queue dispatcher, worker, and secret helpers), `app/blueprints/notifications.py` (browser channel routes), `app/blueprints/api_v1.py` (API channel and audit routes), `app/static/js/features/preferences/notification_channels.js` (Options **Notifications** tab), `docs/notifications.md` (setup and payload guide).

---

## Session Command Variables

**Purpose:** reuse common target values across commands without mutating the subprocess environment.

**Behavior:**

- `var set NAME value` stores a value for the current session. Names must match `[A-Z][A-Z0-9_]{0,31}`.
- `var list` prints the current session variables, and `var unset NAME` removes one.
- Commands can reference variables as `$NAME` or `${NAME}`. The app expands those references before built-in command dispatch, built-in pipe handling, command policy validation, workspace rewrites, and subprocess launch.
- Undefined variables or unsupported `$...` syntax are denied before a process is spawned.
- Run history keeps the typed command, while the transcript emits a `[vars] expanded ...` notice so the expanded command remains visible.
- Autocomplete suggests defined variable names when typing `$...` and suggests existing names plus common `HOST`, `PORT`, and `IP_ADDR` starters for `var set`.
- Variables are session-scoped and migrate with session-token identity changes.

**Limits:** variables are intended for targets, ports, and paths, not secrets. Values are not redacted and are visible in `var list`, autocomplete descriptions, and the expansion notice.

**Related files:** `app/services/session/variables.py`, `app/services/commands/builtins.py`, `app/blueprints/run.py`, `app/static/js/app.js`.

---

## Encrypted Secrets

**Purpose:** store per-session API keys for approved tools without putting those values in terminal commands, transcripts, history, snapshots, or logs.

**Behavior:**

- The Options modal includes a **Secrets** section where users can add, replace, and delete secret values for the active session. The add flow suggests the API key names declared by the command and provider registries first, with a custom option for local overlays or future integrations.
- **Provider Status** in the Secrets section shows which intel providers are usable now, which ones still need an API key, the app-facing secret names, supported lookup types or CLI uses, and broad account/free-tier notes. Clicking a secret name opens the add-secret prompt with that key selected.
- `secret set NAME` opens the same browser-owned value prompt from the terminal. The command line contains only the name; the value is entered in the modal and is not echoed.
- `secret list` shows stored names and their consumer environment bindings. It never prints values.
- `secret unset NAME` deletes one stored secret. `secret show-consumers` and its `providers` alias show intel provider readiness with the same usable versus needs-configuration summary as the Provider Status modal.
- Command registry entries can declare `requires_secrets`. When a matching command runs, the backend decrypts the needed value in memory and passes it to the subprocess environment. Missing required secrets stop the run before launch with a clear message.
- Secret declarations can also map a user-friendly secret name to a vendor-required environment name. For example, VirusTotal CLI runs accept either `VT_API_KEY` or the native `VTCLI_APIKEY` stored secret, and the app passes the value to `vt` as `VTCLI_APIKEY`.

**Limits:** stored values are replace-only. The app does not reveal or copy a saved secret back out of the vault.

**Configuration:** operators provide the vault master key with `SECRETS_MASTER_KEY` or let the app create an app-owned key file under the data directory. Tool bindings live in `app/conf/commands.yaml` through `requires_secrets`.

**Related files:** `app/blueprints/secrets.py`, `app/services/secrets/`, `app/services/commands/builtins_secrets.py`, `app/static/js/features/preferences/secrets_panel.js`, `app/conf/commands.yaml`.

---

## External Intel

**Purpose:** query configured passive-intel providers without making users paste API keys into the terminal.

**Behavior:**

- `intel ip <ip>` queries Shodan, Censys, GreyNoise, AlienVault OTX, AbuseIPDB, IPinfo, Team Cymru, URLhaus, ThreatFox, and RouteViews, then shows ports, CVEs, banner summaries, Censys services and ownership context, GreyNoise classification, OTX pulse context, AbuseIPDB report confidence, IPinfo geolocation and ASN details, malware-distribution context, IOC matches, and IP-to-ASN/BGP ownership context when those providers return data.
- `intel domain <domain>` queries VirusTotal, AlienVault OTX, crt.sh, URLhaus, ThreatFox, urlscan.io, and paid-only SecurityTrails when configured, then shows reputation, analysis stats, recent URLs, WHOIS summary data, OTX pulse context, certificate counts, names, issuers, first/last certificate sightings, URLhaus host context, ThreatFox IOC matches, urlscan.io search hits, and SecurityTrails DNS/WHOIS/subdomain pivots.
- `intel url <url>` queries URLhaus, ThreatFox, and urlscan.io, then shows malware-distribution status, IOC context, and matching urlscan.io search results without submitting a new scan.
- `intel hash <md5|sha1|sha256>` autodetects the hash type by length, queries VirusTotal, AlienVault OTX, URLhaus, and ThreatFox, and checks SHA1 hashes against HIBP Pwned Passwords by sending only the first five SHA1 characters.
- `intel cve <CVE-ID>` queries NVD and Vulners, then shows severity, score, publish/modified dates, summary, references, exploit counts, and exploitability context when provider data is available.
- Each provider pane reports whether it came from cache, was rate-limited, hit quota backoff, or is missing a required encrypted secret.
- Private, loopback, and other non-public IPs are blocked by default because vendor intel on those addresses is not useful. `--include-private` allows an explicit override.
- The external `shodan`, `vt`, `greynoise`, `ipinfo`, `urlscan-cli`, and `chaos` CLI wrappers remain available for users who want provider-native output. `shodan domain` and `shodan host` output also feeds structured findings for DNS records, host IPs, hostnames, open ports, and HTTP titles, with weak mail policy rows and private DNS addresses flagged as warnings. `ipinfo <ip>` highlights IP, hostname, and organization rows while keeping geography and timezone rows as context.

**Limits:** Shodan, Censys, VirusTotal, GreyNoise, AlienVault OTX, AbuseIPDB, URLhaus, ThreatFox, Vulners, urlscan.io, and SecurityTrails require user-provided provider keys. SecurityTrails currently requires a paid account. Team Cymru, crt.sh, HIBP Pwned Passwords, NVD, and RouteViews work without saved keys but still use the app's per-session rate limiting and cache layer to avoid accidental bursts. Provider terms and quotas are still enforced by each vendor.

**Configuration:** users store `SHODAN_API_KEY`, `CENSYS_PAT`, optional `CENSYS_ORGANIZATION_ID`, `GREYNOISE_API_KEY`, `VT_API_KEY`, `OTX_API_KEY`, `ABUSEIPDB_API_KEY`, optional `IPINFO_TOKEN`, `URLHAUS_AUTH_KEY`, `THREATFOX_AUTH_KEY`, `VULNERS_API_KEY`, `URLSCAN_API_KEY`, `SECURITYTRAILS_API_KEY`, or `PDCP_API_KEY` through Options → Secrets or `secret set NAME`. The Options picker suggests those known keys from the provider registry and command registry, while the terminal command still accepts explicit names such as the VirusTotal CLI's native `VTCLI_APIKEY`. Operators tune cache TTLs and rate-limit buckets in `conf/config.yaml`.

**Related files:** `app/services/intel/`, `app/services/commands/builtins_intel.py`, `app/conf/commands.yaml`, `app/conf/config.yaml`.

---

## Session Files

**Purpose:** optional app-managed per-session file access for commands that need small input or output files, without turning the app into a general-purpose shell filesystem.

**Behavior:**

- Session file storage is disabled by default and controlled by server-side `workspace_*` config keys.
- Each browser/session token gets a hashed session directory under the configured workspace root.
- Session directories use sticky, setgid, group-scoped permissions and app-created files are group-readable but not world-readable; commands run as the unprivileged `scanner` user with a restrictive umask so tool-created workspace outputs follow the same boundary.
- Production session file storage uses a host bind mount by default. The current image uses `appuser` `995:995` and `scanner` `994:994`; bind-mount roots should be pre-owned by `995:995`, with the workspace root set to `0730`, session directories set to `3730`, app-created files set to `0640`, and command-created writable outputs allowed as `0660`.
- Workspace access updates the hashed session directory activity timestamp. Periodic cleanup removes inactive `sess_*` directories after `workspace_inactivity_ttl_hours`; it does not delete individual files solely because their file timestamps are old.
- File names are relative and display-friendly; absolute paths, traversal, backslashes, hidden names, symlinks, and paths outside the session root are rejected. Text reads and downloads also use final-component no-follow opens where supported, so the app keeps the same session-root boundary even if a path is swapped after validation.
- The Files panel can create, view, edit, move, download, and delete text files owned by the current session; JSON and JSONL/NDJSON files are pretty-printed in the read-only viewer, and open file previews can be refreshed manually or opt into auto-refresh while following appended output at the bottom. Files can also be dragged onto folder rows after confirmation.
- The add/edit file modal includes labels and a private note for the workspace file. File rows surface existing labels/notes from the generic entity metadata store, and move/delete operations update or clear that metadata with the file so project views and package exports do not keep stale paths.
- The `file` built-in provides terminal access to the same file model through `cd [folder]`, `pwd`, `file list [-l] [folder]`, `file show <file>`, `file add [file]`, `file add-dir <folder>`, `file edit <file>`, `file download <file>`, `file move <source> <destination>`, and confirmed `file delete [-r|-f|-rf] <file-or-folder>` / `file rm [-r|-f|-rf] <file-or-folder>`; `file add` opens a blank file editor unless a filename is provided, `file add-dir` creates a folder, `file download <file>` starts the same browser download path as the Files panel, and `file move` moves or renames files and folders. `cd` is tracked per tab, treats the session workspace root as `/`, and causes relative commands such as `ls`, `cat`, `mv`, `rm`, and `file show` to resolve from the tab's current workspace folder.
- The `ls [-l] [folder]`, `cat <file>`, `mkdir <folder>`, `mv <source> <destination>`, `rm [-r|-f|-rf] <file-or-folder>`, `grep <pattern> <file>`, `head [-n N] <file>`, `tail [-n N] <file>`, `wc -l <file>`, `sort [-r|-n|-u] <file>`, and `uniq [-c] <file>` aliases map to app-native workspace operations only; they do not expose arbitrary host/container filesystem access.
- `file list`, `ls`, `file move`, `mv`, and confirmed `file delete` support simple `*` patterns such as `file ls darklab-*`, `mv darklab-* darklab/`, and `file delete scan-*`. A `*` matches inside one path segment and does not cross `/`; moving multiple matches requires the destination to already be a folder.
- `file delete <file>`, `file rm <file>`, and `rm <file>` first verify the target exists, then require the same transcript-owned yes/no confirmation model as other destructive terminal-native actions. Folder deletion requires `-r` or `-rf` before the confirmation is shown, including when a glob matches one or more folders.
- Loaded workspace file and folder names feed autocomplete for `file show`, `file edit`, `file download`, `file move`, `file delete`, `file rm`, `cat`, `ls`, `mv`, and `rm`.
- Workspace-only external-tool examples and flags in `commands.yaml` are hidden from autocomplete unless Files are enabled, so operators can add discoverable file workflows without exposing unusable suggestions on instances that keep Files disabled.
- Selected command flags declared in `commands.yaml` can consume or write session files. At execution time, user-facing names such as `targets.txt` are validated and rewritten to the session workspace path passed to the subprocess.
- `wget` downloads default to the active Files folder when Files are enabled. Operators can still choose a subfolder with `-P downloads` or `--directory-prefix=downloads`.
- Shell navigation and redirection remain blocked; all file access must go through the Files panel, workspace routes, the `file` built-in, or explicitly declared command flags.

**Configuration:** Files use `workspace_*` settings in `conf/config.yaml` and per-command `workspace_flags` in `conf/commands.yaml`; see [CONFIGURATION.md](CONFIGURATION.md) for storage recipes.

**Related files:** `app/services/workspace/files.py` (path, quota, permission, and cleanup helpers), `app/blueprints/workspace.py` (workspace file routes), `app/static/js/workspace.js` (Files panel), `app/services/commands/builtins.py` (`file` built-in), `app/services/commands/registry.py` (workspace flag validation and rewrite).

---

## Project Workspaces

**Purpose:** lightweight case folders that keep related shell work, findings, files, targets, and export packages together while leaving the terminal as the primary workflow.

**Behavior:**

- Projects group top-level source records by link rather than copy. Current project links support completed runs and Atlas entities; Targets stay as the curated domain/IP/URL subset for scope tracking, while the Entities tab shows every linked Atlas entity type. Run-owned artifacts surface through linked runs, and findings surface through linked runs or linked Atlas entities. Project list rows show run, finding, artifact, and package counts before you open a project, and the Findings tab label can show prefetched new/high counts when that project has triage work waiting. Snapshots and manually selected workspace files stay in their history/files surfaces and are intentionally not project-linked.
- The desktop rail and mobile menu open the Projects modal for creating, selecting, clearing, archiving, deleting, and reviewing projects. The active-project HUD shows current project context, and project changes broadcast across same-session tabs.
- Active projects can automatically link completed external command runs and, when enabled, the Atlas entities those runs produce. Manual run-link actions confirm first and can also add the Atlas entities found in those runs, with the entity count shown before anything is saved. When automatic entity linking reaches the project link limit, the run stream reports the skipped entity count. Removing a run from a project can also remove same-run disposable Atlas entity links, while curated entity links are counted separately and kept unless you opt in; the confirmation also shows how many related findings will stop appearing in the project. Built-in runs stay in history without project links or project-derived findings, and **Link last run** backfills the most recent eligible run when needed. In the terminal, `project link run last` resolves within the current tab so parallel tabs don't steal each other's latest run.
- Project details expose project labels, project notes stored through `entity_notes` with `entity_type='project'`, editable Atlas-backed targets, linked Atlas entities, linked runs, findings, artifacts, and packages. Suppressed Atlas entities and findings stay hidden from default project views until they're restored in Atlas. The Findings tab pages through large result sets, shows each finding's source command, and keeps its tab count tied to the full server-side total, including findings attached through linked runs or linked Atlas entities. Command, severity, scope, run, target, review-state, label, and note filters help narrow busy projects without loading every finding at once, and visible-page selection can update review state in bulk. Labels and notes are also editable for linked runs, findings, Atlas entities, run file artifacts, workspace files, and packages through the shared entity metadata editor.
- The Entities tab mirrors Atlas entity types for project-linked rows with compact type tabs, shows cached intel provider context, opens entities in Atlas for deeper intel review or refresh, links more session Atlas entities from a picker, bulk-unlinks visible entities from the project, and exports project-scoped entities as CSV or JSONL.
- Finding review supports status updates, visible-page bulk review/delete, source-run restore with line highlighting, target attribution, orphan-source filtering, filtering, and sorting. Artifact rows show availability/checksum state and offer scoped preview/download actions for still-available workspace files.
- Evidence packages are draft project manifests. The wizard records name/description, package labels/notes, transcript/finding/artifact/target selections, redaction mode, artifact inclusion, private-note inclusion, size estimates, and artifact warnings. Full Archive packages select transcript HTML for every selected run by default, and the Include step has compact select-all/clear menus for transcript HTML, findings, and targets. The preview shows a best-guess ZIP size, the expanded content size before compression, and the optional full-text fallback files for capped transcripts, using stored output byte counts when available so the estimate stays conservative without wildly overcounting text. Existing package rows support polled downloads with visible archive-preparation status, re-package, manifest preview, delete, and metadata edit actions.
- Package downloads produce a capped archive with `manifest.json`, `README.md`, static `index.html`, selected run transcript pages, finding/target JSON and Markdown exports, selected metadata/notes exports, optional raw artifacts for raw packages, and redacted text/JSON artifact derivatives for redacted packages. The downloaded manifest also records included transcript line indexes, signals, entities, and source run ids for the lines that were actually exported.
- Project run comparison uses the same canonical `/history/compare` flow as the History drawer. It can compare two linked runs directly or compare a selected run against the newest linked run with a chosen run label; the dedicated Run Comparison section covers the shared transcript, finding, and artifact comparison behavior.
- History project filtering returns linked external runs for the selected project. Run-subtype filters can further split all runs, built-in runs, and external runs while snapshots remain available through the normal snapshot filter.

**Limits:** projects are session-scoped and do not copy source history. Deleting a project removes its project metadata, targets, packages, and links, but not the underlying run history or workspace files. Entity notes are intentionally one note per supported entity rather than comment threads.

**Configuration:** project, metadata, and evidence-package limits are configured in `conf/config.yaml`; see [CONFIGURATION.md](CONFIGURATION.md).

**Related files:** `app/services/projects/workspace.py` (project relationship, metadata, and package helpers), `app/blueprints/projects.py` (project routes), `app/static/js/shell_chrome.js` (Projects modal), `app/static/js/history.js` (history project filters and metadata actions), `app/static/js/workspace.js` (workspace file metadata), and `app/core/database.py` (project workspace schema).

---

## Evidence Packages

**Purpose:** turn selected project evidence into a downloadable review bundle while preserving raw/redacted export choices and private metadata boundaries.

**Behavior:**

- Package creation starts from the Projects modal's Packages tab. The wizard records name, description, labels, notes, redaction mode, artifact inclusion, private-note inclusion, and the selected runs, findings, artifacts, and targets.
- Package rows show preset/redaction/size summaries and offer polled downloads with visible archive-preparation status, re-package, manifest preview, metadata edit, and delete actions.
- Downloaded archives include `manifest.json`, `README.md`, static `index.html`, selected run transcript pages, full-text companions for capped transcripts, selected finding/target JSON and Markdown exports, selected label/private-note exports, note Markdown exports, optional raw artifacts for raw packages, and redacted text/JSON artifact derivatives for redacted packages.
- Re-package starts from the previous manifest selection so an operator can rebuild the same bundle after project data changes.

**Limits:** package manifests are draft records, and the archive is built at download time from still-available project data and workspace artifacts. Redacted packages never include raw artifact files; binary or unknown artifact types are skipped unless they're exported in a raw package.

**Configuration:** evidence-package limits are configured in `conf/config.yaml`; see [CONFIGURATION.md](CONFIGURATION.md).

**Related files:** `app/services/projects/workspace.py` (manifest and archive builder), `app/blueprints/projects.py` (package routes), and `app/static/js/shell_chrome.js` (wizard, package rows, and manifest preview).

---

## Command Allowlist

**Purpose:** operator-controlled set of permitted command prefixes (with deny overrides) that gates every `/runs` request before dispatch.

**Behavior:**

- Every `/runs` request is checked against the `policy` blocks in `conf/commands.yaml` before dispatch.
- Allow entries match by prefix — a prefix of `ping` permits `ping google.com`, `ping -c 4 1.1.1.1`, etc. Be as specific or broad as you like: `nmap -sT` permits only TCP connect scans while `nmap` permits any nmap invocation.
- Deny entries take priority over allow entries and match anywhere in the command as space-separated tokens (not as a prefix).
- Category metadata also drives the command catalog; deny entries are not shown to users.
- The desktop rail and mobile menu expose a Command Registry modal/sheet that lists supported external commands by category, supports search, and opens the same per-command details used by `commands info <root>`.
- The registry is re-read on every request for command policy, so edits take effect without a restart. Deleting or emptying the registry disables restrictions entirely.
- Tool names and subcommand prefixes are matched **case-insensitively**; flag names are matched **with exact case** (so `!curl -K` blocks `-K` without blocking `-k`).
- `/dev/null` exception: denied output flags (`-o`, `-O`) are permitted when their argument is `/dev/null`, allowing patterns like `curl -o /dev/null -w "%{http_code}"`.
- Operators can set `restricted_command_input_cidrs` to reject literal IP/CIDR targets in command slots declared with target-like `value_type` metadata (`domain`, `host`, `ip`, `cidr`, `target`, or `url`). The check catches literal IPs, overlapping CIDR arguments, URL hosts, host:port values, and app-readable workspace input files passed through declared read flags.
- Command-specific runtime adaptations are also declared in the registry. `inject_flags` handles safe default flags such as `nmap -sT`, `nuclei -ud /tmp/nuclei-templates`, `naabu -scan-type c`, and `mtr --report-wide`; managed workspace directories and environment wrappers handle Amass' session-scoped database path.

**Limits:** prefix matching is deliberately coarse — operators must be explicit with deny entries to block flag combinations on otherwise-allowed tools. Deny matching only applies once the tool prefix matches (e.g., `!nmap -sU` only affects `nmap` commands). Restricted command inputs only inspect literal values in metadata-known target slots; domain names are not DNS-resolved.

**Configuration:** command policy uses `conf/commands.yaml`; restricted target inputs use `restricted_command_input_cidrs` in `conf/config.yaml`. See [CONFIGURATION.md](CONFIGURATION.md) and [docs/external-command-integrations.md](docs/external-command-integrations.md).

```yaml
commands:
- root: nmap
  category: Port & Service Scanning
  policy:
    allow:
    - nmap
    deny:
    - nmap -sU
    - nmap --script
```

- `policy.allow` — allowed command prefixes.
- `policy.deny` — denied prefixes/flags that take priority over allow entries.
- `category` — command catalog grouping.
- `autocomplete.*.value_type` — declares target-like values for autocomplete and optional restricted-input checks.

**Related files:** `app/conf/commands.yaml` (command registry), `app/services/commands/registry.py` (allow/deny matching logic), `app/blueprints/run.py` (policy gate at the `/runs` entry point).

### Deny Prefixes

Deny matching has a few extra rules worth calling out:

- Denies match a flag anywhere in the command, not just immediately after the tool (`nmap -sT -sU 10.0.0.1` is still caught by `!nmap -sU`). Long flags also match attached values, so `!tool --api-key` catches `tool --api-key=value`.
- Flag names are case-sensitive so you can deny `-K` without also denying `-k`.
- The `/dev/null` exception applies to common metadata-capture patterns:

```bash
curl -o /dev/null -s -w "%{http_code}" https://example.com
wget -q -O /dev/null --server-response https://example.com
```

---

## Interactive PTY Mode

**Purpose:** run approved interactive and screen-oriented tools inside a real browser terminal when line-oriented streaming would lose important live state.

**Behavior:**

- Commands with registry-owned interactive metadata, currently `nc --interactive`, `telnet --interactive`, `mtr --interactive`, `ffuf --interactive`, and `masscan --interactive`, are reserved for the PTY route instead of normal `/runs`.
- The browser opens a tab-scoped xterm.js modal, preloads the terminal assets, starts the PTY through `/pty/runs`, and sends keyboard input and terminal resizes through bounded POST routes.
- If the same PTY run is opened from another browser client, the previous live owner closes cleanly and adds an `[interactive PTY moved to another tab]` notice instead of leaving two live terminals fighting for the same run.
- Completed PTY runs append a saved static transcript and exit status back into the parent shell tab, then persist through the normal history/search/finding path. Registry transcript modes decide whether a tool saves the final visible frame or scrollback-style findings.
- Reload recovery and Status Monitor Attach use bounded ANSI snapshots and show when a restored snapshot was already stale. Redis-backed deployments can serve output streams, input/resize control, and reattach snapshots from any worker without sticky routing; single-worker local development can run without Redis when configured.
- `/diag` includes PTY operator metrics for active terminals, completed duration, input volume, dropped input, and queued controls.

**Limits:** disabled by default, desktop-only, and restricted to commands that explicitly declare PTY behavior in the command registry. PTY runs have a configured max runtime and per-session concurrency cap. Multi-worker deployments require Redis unless `run_broker_require_redis` is intentionally relaxed for local development.

**Configuration:** Interactive PTY uses `interactive_pty_*` settings plus each command's `interactive` registry block; see [CONFIGURATION.md](CONFIGURATION.md).

**Related files:** `app/services/pty/service.py` (server-side PTY lifecycle and snapshots), `app/services/pty/transcript.py` (saved transcript shaping), `app/blueprints/run.py` (PTY routes), `app/static/js/pty.js` (browser terminal controller), `app/static/js/vendor/xterm.js`, `app/static/js/vendor/xterm-addon-fit.js`, and `app/conf/commands.yaml` (interactive command metadata).

---

## Wordlists

**Purpose:** pre-installed SecLists corpus available to allowlisted tools, plus a curated app catalog so users can discover useful wordlists without memorizing the SecLists directory tree.

**Behavior:**

- The full [SecLists](https://github.com/danielmiessler/SecLists) collection is installed inside the container at `/usr/share/wordlists/seclists/`.
- The built-in `wordlist` command lists and searches curated installed wordlists:
  - `wordlist` / `wordlist list` prints the curated catalog.
  - `wordlist list dns` filters to one category.
  - `wordlist search raft` searches names, paths, descriptions, aliases, and categories.
  - `wordlist path common.txt` prints a single copy-friendly path.
  - `wordlist --all` lists the full installed SecLists file corpus for deeper browsing.
- Autocomplete suggests installed wordlists only when command metadata explicitly marks a value slot with `value_type: wordlist`.
- `wordlist_category` filters autocomplete to relevant categories such as `dns`, `web-content`, `api`, `cms`, `fuzzing`, `passwords`, `usernames`, and `user-agents`.
- Workspace file hints stay separate from installed SecLists suggestions. A tool flag such as `gobuster dir -w` can suggest both session files and installed web-content wordlists without treating every file path as a SecLists entry.
- Any allowlisted tool can still reference files under the SecLists path directly when the command policy permits that path.
- The list is installed at container build time; no runtime fetch is required.

**Limits:** wordlists are read-only inside the container. Normal command output and autocomplete use the curated catalog instead of exposing every file under SecLists; use `wordlist --all` for the full scanned tree. The corpus is not updated between builds — rebuild the image to pick up a new SecLists release.

**Configuration:** `app/conf/wordlists.yaml` defines curated category globs under the fixed install path. External command value slots opt into installed-wordlist autocomplete through `value_type: wordlist` and `wordlist_category` in `app/conf/commands.yaml`.

**Related files:** `Dockerfile` (SecLists install step), `app/conf/wordlists.yaml` (curated catalog), `app/services/commands/wordlists.py` (catalog loader), `app/conf/commands.yaml` (typed wordlist slots), `app/static/js/autocomplete.js` (slot-aware suggestions).

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
- When the onboarding tour has visible chapters, the welcome flow adds a tour entry line. Desktop users can type `tour` or open the visual tour; mobile users get the CLI-only `tour` entry point.
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

## Onboarding Tour

**Purpose:** an optional guided introduction that helps new users learn the main shell, history, comparison, workflow, project, files, PTY, options, and FAQ flows without leaving the app.

**Behavior:**

- The welcome flow can point users at the tour, and users can start it again with the `tour` built-in command or the visual tour link in FAQ.
- The terminal `tour` command types each chapter into the transcript, pauses after each chapter, and lets the user press any key to continue or `q` to stop.
- Terminal tour `Try this` chips open the sample command in a new tab so the tour tab stays readable while the user experiments.
- The desktop visual tour uses a carousel with app-shaped previews. `Try this` actions close the carousel and open the matching app surface when one exists, such as History, Workflows, Projects, Files, Options, or FAQ.
- Feature-gated chapters are hidden when their feature is unavailable. Interactive Tools stays hidden on mobile because interactive PTY sessions are desktop-only.

**Configuration:** `app/conf/tour.yaml` stores chapter text, sample commands, and visual illustration keys. See [CONFIGURATION.md](CONFIGURATION.md#tour-configuration) for the file format.

**Related files:** `app/conf/tour.yaml`, `app/static/js/app.js` (`tour` built-in), `app/static/js/tour_modal.js` (visual carousel), `app/static/css/welcome.css` (tour visuals), `app/blueprints/content.py` (tour content loader).

---

## Custom FAQ

**Purpose:** operator-supplied FAQ entries appended to the built-in FAQ, with section grouping and a safe markup subset for links, formatting, and clickable command chips.

**Behavior:**

- Entries in `app/conf/faq.yaml` are appended to the built-in FAQ returned by `/faq` and re-read on every request (no restart required).
- Each entry has a required `question` and one of `answer` (safe markup subset) or `answer_html` (exact HTML).
- Entries can include `category` to place them under a FAQ section. Missing or unknown categories appear under **Other**, so local entries still show up if a category is mistyped.
- The FAQ stays in one scrollable modal with section headers instead of tabs, so browser search can still find answers. Links can open a specific answer with `#faq=<question-slug>` or a section with `#faq-section=<section-slug>`.
- The safe markup subset in `answer` supports `**bold**`, `*italic*`, `__underline__`, `` `inline code` ``, `- list items`, and command chips like `[[cmd:shortcuts]]` or `[[cmd:ping -c 1 127.0.0.1|custom label]]`.
- Chips behave like the built-in allowlist chips — clicking one loads the command into the prompt without running it.
- The file is optional — a missing or empty file shows only the built-in FAQ items.
- Built-in entries can use richer modal formatting while still rendering plain-text answers in the `faq` command.

**Limits:** the safe markup subset is deliberately narrow; anything outside it is shown literally. For arbitrary HTML (images, tables, custom classes) use `answer_html`.

**Configuration:** `app/conf/faq.yaml`:

```yaml
- question: "Where is this server located?"
  category: "Other"
  answer: "This server is hosted in New York, USA on a 10 Gbps uplink via Cogent and Zayo."

- question: "What is the outbound bandwidth?"
  category: "Other"
  answer: "Outbound traffic is limited to 1 Gbps sustained."
```

**Related files:** `app/conf/faq.yaml` (custom entries), `app/blueprints/content.py` (`/faq` endpoint + markup rendering), `app/static/js/features/command-registry/command_registry.js` (FAQ grouping + chip click wiring).

---

## Theme Selector

**Purpose:** live theme picker backed by the named variants under `app/conf/themes/`, with the choice persisted as part of the active session preference snapshot and cached locally for reload continuity.

**Behavior:**

- Click **◑ theme** in the desktop rail (or the **☰** menu on mobile) to open the theme selector modal.
- Run `theme`, `theme list`, `theme current`, or `theme set <theme>` in the terminal to inspect or apply the same theme variants without opening the modal. Theme names are suggested after `theme set`.
- Picking a variant applies it immediately and saves the choice into the current session's preference snapshot, while also caching it locally so reloads stay fast.
- The selected theme applies to the live shell, permalink pages, and HTML exports — so shared links render in the author's theme context when opened fresh.

**Limits:** anonymous UUID sessions keep their own browser-local theme choice, while named session tokens restore the saved theme across browsers and devices. Clearing browser storage removes the local cache but does not erase a named session token's saved theme on the server.

**Configuration:** theme variants live under `app/conf/themes/`; see [THEME.md](THEME.md) for authoring details (variable names, fallbacks, and how a new variant is registered).

**Related files:** `app/conf/themes/` (theme variant files), `app/static/js/app.js` (selector modal, terminal command, and preference persistence), `app/static/css/core/base.css` (runtime theme variable surface), `app/templates/theme_vars_style.html` and `app/templates/theme_vars_script.html` (server-rendered theme metadata), `THEME.md` (authoring guide).

---

## Options Modal

**Purpose:** session-owned controls for presentation, run behavior, session identity, and provider secrets that follow the active session identity while still caching locally for fast reloads.

**Behavior:**

- Click **≡ options** in the desktop rail (or the **☰** menu on mobile) to open the modal.
- The modal has three tabs: **Preferences** for display, identity, run, and compare controls, **Secrets** for provider readiness plus stored API keys, and **Notifications** for outbound delivery channels. The last tab you used is remembered with the rest of your session preferences.
- Run `config`, `config list`, `config get <option>`, or `config set <option> <value>` in the terminal to inspect or update the same user options without opening the modal. Option names are suggested after `config get` or `config set`, and option values are suggested after a selected option.
- Timestamp and line-number settings mirror the tabbar quick toggles — changing either surface updates the other immediately.
- The HUD clock setting chooses whether the desktop `CLOCK` pill renders in `UTC` or browser-local time. This control is intentionally hidden from the mobile Options sheet because the HUD itself is desktop-only.
- The welcome-intro setting controls whether the welcome animation plays on first tab: full animated sequence, instant settle, or no welcome tab at all.
- The share-snapshot redaction setting selects the default redaction choice (prompt / redacted / raw) so the share prompt is skipped once a preference is saved.
- The project capture settings control whether completed external command runs are added to the active project and whether generated Atlas entities are added with those auto-linked runs.
- Run notifications fire a browser desktop notification each time a run exits or is killed; the title shows only the command root (`$ curl`) and the body shows exit code and elapsed time. Enabling triggers the native permission prompt; if notifications are blocked, the toggle reverts with a toast. This toggle is intentionally hidden from the mobile Options sheet because the feature is treated as desktop-oriented chrome behavior.
- The **Notifications** tab lists outbound channels for durable session tokens. You can add, edit, mute, delete, and send a test notification for supported destinations without exposing write-only secret values after save.
- Preferences are stored server-side per session and mirrored into browser cookies/local storage for reload continuity, so a named session token restores the same option set across browsers and devices.
- The **Secrets** tab includes Provider Status, Add secret, Refresh, and the stored secret list so a long list of saved keys does not push the preference controls out of view.

**Limits:** anonymous UUID sessions remain browser-local by design, so only named session tokens carry preferences and outbound notification channels across devices. Blocked browser notification permission cannot be re-prompted by the toggle — it must be re-enabled in browser settings. Email channels require operator SMTP settings before they can be saved or tested.

**Configuration:**

| Setting | Choices | Description |
|---------|---------|-------------|
| **Timestamps** | Off / Elapsed / Clock | Timestamp mode for output lines. Equivalent to the tabbar quick toggle |
| **Line Numbers** | on / off | Sequential line numbers beside output and the live prompt. Equivalent to the tabbar toggle |
| **HUD Clock** | UTC / Local Time | Timezone mode for the desktop HUD `CLOCK` pill; shown on desktop, hidden from the mobile Options sheet |
| **Welcome Intro** | Animated / Disable Animation / Remove Completely | Welcome animation behavior on first tab |
| **Share Snapshot Redaction** | Prompt Until Set / Default To Redacted / Default To Raw | Default redaction choice for snapshot sharing |
| **Project Run Capture** | on / off | Add completed external command runs to the active project |
| **Project Entity Capture** | on / off | Add generated Atlas entities when an auto-linked run is added to the active project |
| **Run Notifications** | on / off | Browser desktop notification on run exit or kill; title is command root, body is exit code + elapsed time; shown on desktop, hidden from the mobile Options sheet |

**Terminal option keys:** `line-numbers`, `timestamps`, `welcome`, `share-redaction`, `project-auto-link-runs`, `project-auto-link-run-entities`, `run-notifications`, `hud-clock`, `compare-view`, `compare-context`, `prompt-username`.

**Related files:** `app/static/js/features/preferences/preferences.js` (Options modal state, notification preference, and session preference persistence), `app/static/js/features/preferences/notification_channels.js` (outbound channel list, editor, mute/delete, and test sends), `app/static/js/features/terminal/local_commands.js` (terminal `config` command), `app/static/js/features/preferences/secrets_panel.js` (encrypted secret rows and value prompt), `app/static/js/runner.js` (run-completion notification dispatch and browser-owned terminal command routing), `app/static/js/shell_chrome.js` (desktop options navigation), `app/static/js/mobile_chrome.js` (mobile menu wiring).

---

## Persistence & Retention

**Purpose:** durable storage layout for run history, preview metadata, full-output artifacts, and tab snapshots, with time-based retention pruning on startup.

**Behavior:**

- SQLite stores run history, preview metadata, full-output artifact metadata, and tab snapshots in `./data/history.db`.
- Postgres stores database rows in Postgres while still using `./data` for full-output artifacts, body-store files, and the app-owned secret key file.
- Persisted full-output artifacts are written as compressed files under `./data/run-output/`.
- Optional body-store thresholds can move large run search text, tab snapshot bodies, and Atlas intel payloads into compressed files under `./data/body-store/` while the app keeps reading them normally.
- The `./data` directory is created automatically on first run and persists filesystem-backed artifacts across container restarts and recreations.
- On startup, runs, run-output artifact metadata, artifact files, and snapshots older than `permalink_retention_days` are pruned together.

**Limits:** `./data` is the only writable path in an otherwise read-only container. Setting `permalink_retention_days: 0` disables pruning entirely (unlimited retention). On SQLite deployments, never write to `./data/history.db` from the host — host/container SQLite version mismatches can corrupt the FTS5 btree.

**Configuration:** `permalink_retention_days` in `config.yaml` (default 365; `0` disables pruning). `runs_search_text_inline_max_bytes`, `snapshots_inline_max_bytes`, and `intel_payload_inline_max_bytes` default to `0`, which keeps those bodies inline.

**Related files:** `app/core/database.py` (schema, migrations, backend selection, and startup pruning), `app/services/runs/output_store.py` (compressed artifact writer + reader), `app/blueprints/history.py` (reads + writes through the persistence layer). See [ARCHITECTURE.md](ARCHITECTURE.md) for full schema.

**Useful direct checks:**

Prefer `/diag` for storage and row-count checks because it works on both backends. The commands below are SQLite-only maintenance examples for stopped containers or controlled local copies:

```bash
# Count rows
sqlite3 data/history.db "SELECT COUNT(*) FROM runs; SELECT COUNT(*) FROM run_output_artifacts; SELECT COUNT(*) FROM snapshots;"

# Inspect page-level storage when dbstat is available
sqlite3 data/history.db "SELECT name, SUM(pgsize) AS bytes FROM dbstat GROUP BY name ORDER BY bytes DESC LIMIT 10;"
```

---

## Session Tokens

**Purpose:** optional persistent named identity (`tok_<32 hex>`) so run history, snapshots, starred commands, session variables, workspace files, project workspace records, recent targets, user workflows, active-project context, and saved user options follow an operator across browsers and workstations without introducing a login layer.

**Behavior:**

- By default each browser gets an anonymous UUID stored in `localStorage` under `session_id`, plus a separate browser/client id used for active-run ownership. A session token replaces the session identity with a persistent `tok_<32 hex>` so run history, snapshots, starred commands, session variables, workspace files, project workspace records, recent targets, user workflows, active-project context, theme choice, and other saved Options settings follow the operator across browsers and workstations without making every browser automatically own the same live run.
- Tokens are generated server-side as `tok_` + 32 lowercase hex characters (36 chars total, cryptographically random) and recorded in the `session_tokens` table.
- The active token is stored in `localStorage` under `session_token`; the original UUID is always preserved under `session_id` so `session-token clear` has a stable fallback.
- The browser sends the active identity as `X-Session-ID` on every request; possession of the token string is the only authorization check (matching the existing anonymous session model).
- Changing the token in one tab propagates to all open tabs via the `storage` event — recent chips, starred state, history drawer, session-scoped preferences, and the options-panel masked display all refresh without a reload.
- `session-token` subcommands are rendered client-side so token values are not sent through the normal `/runs` execution path. Successful commands are saved through the allowlisted `/run/client` history path with token-bearing arguments masked before they are stored or shown in recent-command views.

**Terminal commands:**

- `session-token` (no subcommand) — prints current status: active token in masked form or "anonymous session".
- `session-token generate` — requests a new token and offers to migrate the current session's runs, snapshots, starred commands, saved user options, session variables, user workflows, project workspace records, recent targets, active-project context, and workspace files when the current session has portable data. The token becomes active only after a successful migration; declining migration activates it as a fresh named session; migration failure leaves the old session active.
- `session-token set <token>` — adopts an existing token. UUIDs are always accepted; `tok_...` values must already exist on this server. The migration prompt is offered if the current session has history or workspace files; answering `no` skips migration and still applies the token, while `Ctrl+C` cancels the whole set flow.
- `session-token copy` — copies the active token to the clipboard without printing the raw token in the terminal.
- `session-token clear` — opens a terminal-owned yes/no confirmation, removes `session_token` from `localStorage` only after explicit confirmation, and reverts to the anonymous UUID session. `Ctrl+C` cancels the clear flow. Server-side session data remains and can be reclaimed with `session-token set`.
- `session-token rotate` — generates a new token, migrates all runs, snapshots, starred commands, session variables, user workflows, project workspace records, recent targets, active-project context, workspace files, and saved user options (when the destination has no saved preferences yet), then switches. The switch is **atomic** — migration failure aborts the rotation and keeps the old token active. Old token is retired on success.
- `session-token list` — calls `GET /session/token/info` and shows the active token in masked form with its creation date (or "anonymous session").
- `session-token revoke <token>` — opens a transcript-owned yes/no confirmation, warns that the token's history and workspace files will not be recoverable from the app after revocation, then permanently deletes the given token via `POST /session/token/revoke` only after an explicit `yes`. If the revoked token is the active one, the client clears `localStorage` and falls back to the anonymous UUID session. Runs, snapshots, starred rows, saved preferences, and workspace files for the revoked token are not deleted but become unreachable.

**Options panel buttons:**

| Button | Shown when | Action |
|---|---|---|
| **Generate** | No token active | Generates a new token; copies it to the clipboard with a toast |
| **Set** | No token active | Opens a modal to paste an existing token from another device |
| **Copy** | Token active | Copies the active token to the clipboard |
| **Rotate** | Token active | Generates a new token, migrates session data, copies the new token |
| **Clear** | Token active | Opens a destructive confirm, optionally copies the token, then reverts to the anonymous session |

If a session has run history, workspace files, project workspace records, user workflows, or recent targets, the terminal `generate` and `set` flows use transcript-owned yes/no migration prompts; `clear` and `revoke` use transcript-owned destructive confirmations. The Options panel uses the shared modal confirm primitive for its own set/clear actions. `list` and `revoke` remain terminal-only.

**Limits:** there is no user-facing authentication — possession of the token is sufficient access. `POST /session/migrate` requires the `from_session_id` body field to match the caller's `X-Session-ID` header (mismatch returns 403), so a migration call can only move the caller's own data.

**Configuration:** no config keys — token issuance is always enabled. Token scope covers runs, snapshots, starred commands, session variables, user workflows, project workspace records, recent targets, active-project context, saved user options, and app-managed workspace files when Files are enabled.

**Related files:** `app/static/js/session.js` (client-side token flow + cross-tab `storage` sync), `app/blueprints/session.py` (`/session/token/*`, `/session/preferences`, and `/session/migrate` routes), `app/core/database.py` (`session_tokens`, `session_preferences`, and `starred_commands` tables).

---

## Security and Process Isolation

**Purpose:** defence in depth against shell-injection, loopback callbacks, and worker impersonation, relying on allowlist validation plus OS-level user separation rather than browser trust.

**Behavior:**

- **Shell injection protection.** The app blocks metacharacters that enable command chaining and redirection — `&&`, `||`, `;`, backticks, `$()`, and redirection operators. `|` is allowed only within the constrained pipe model described in [Built-In Pipe Support](#built-in-pipe-support). Direct filesystem references to `/data` and `/tmp` are blocked as command arguments (using a negative lookbehind so URLs containing those strings as path segments are still permitted). Loopback targets (`localhost`, `127.0.0.1`, `0.0.0.0`, `[::1]`) are blocked at the validation layer.
- **Process isolation.** Gunicorn runs as unprivileged `appuser`; user-submitted commands run as separate unprivileged `scanner` processes. The container filesystem is read-only (`read_only: true`); `/data` is accessible only to `appuser` (`chmod 700`), while optional session workspaces use a shared appuser/scanner group with non-world-readable files. Container startup installs an OS-level guard so `scanner` cannot connect back to the app port.
- **Rate limiting + process tracking.** Redis-backed rate limiting prevents burst abuse across multiple Gunicorn workers. PID tracking in Redis keeps kill behavior correct when a kill request lands on a different worker than the one that started the process.
- **Session tracking.** Browsers send a stable `X-Session-ID` so history entries, rate-limit state, and test isolation remain scoped per client without requiring authentication.

**Limits:** there is no authentication layer — controls are defence in depth, not a user boundary. The allowlist plus OS-level isolation are the trust boundary; browser state is not trusted. Loopback blocking applies only to literal loopback addresses and not to private-range addresses that happen to be locally reachable.

**Configuration:**

- `commands.yaml` — dispatch gate (see [Command Allowlist](#command-allowlist)).
- `trusted_proxy_cidrs` in `config.yaml` — CIDRs whose `X-Forwarded-For` is honored.
- `diagnostics_allowed_cidrs` in `config.yaml` — CIDRs permitted to reach `/diag` and `/metrics`.
- `docker-compose.yml` — `read_only: true`, `init: true`, `user` directives, and the port-egress guard.

**Related files:** `app/services/commands/registry.py` (metacharacter, loopback, allow/deny, and rewrite validation), `app/blueprints/run.py` (subprocess spawn and `/kill` route), `app/core/process.py` (Redis PID tracking), `docker-compose.yml` (filesystem + user isolation). See [ARCHITECTURE.md](ARCHITECTURE.md) for cross-worker signalling, the Redis-backed multi-worker kill path, and the `nmap` capability model.

---

## Structured Logging

**Purpose:** backend-emitted structured events (text or GELF JSON) with stable event names and context fields, so operators can observe the shell through a log aggregator without regex-parsing free-form strings.

**Behavior:**

- The backend emits structured log events at four levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`.
- Two output formats are supported: `text` (human-readable `key=value` pairs for local development) and `gelf` (JSON compatible with log aggregators).
- Each event carries structured context fields — session ID, command root, run ID, status — rather than interpolated strings, so log lines are machine-parseable without regex.
- Event names are stable (e.g. `RUN_START`, `RUN_END`, `RUN_KILL`, `DIAG_VIEWED`, `UNTRUSTED_PROXY`), letting aggregators filter by name without string matching.

**Limits:** field names and level semantics are stable, but specific numeric codes and free-form `message` strings are not part of the contract. Downstream consumers should key off event names and structured fields, not prose.

**Configuration:** `log_format` and `log_level` in `config.yaml`; see [CONFIGURATION.md](CONFIGURATION.md).

**Related files:** `app/core/logging_setup.py` (format + level wiring), `app/blueprints/run.py` (run lifecycle events), `app/blueprints/history.py` (history/share events), `app/blueprints/session.py` (token, preference, and starred-command events), `app/blueprints/assets.py` (diagnostics events).

---

## Operator Diagnostics

**Purpose:** restricted operator-only surfaces for inspecting current runtime health and scraping trendable Prometheus metrics without opening a shell session.

**Behavior:**

- `/diag` provides a live operator view of the running instance and is disabled by default.
- The diagnostics page includes a classifier inspector near the top of the page. Paste one output line, optionally add the command context, and it shows the line's `kind`, `role`, signals, entities, command root, and target using the same backend classifier used for saved runs without rerunning the heavier diagnostics probes. An Advanced disclosure keeps the legacy line-class override available when you need to debug old transcript classes.
- The classifier drift report samples recent saved output on demand and calls out spots where stored metadata no longer matches today's classifier, where help output produced findings/entities, or where useful-looking output stayed as plain body text. Samples can be sent straight into the one-line inspector for a closer look.
- `/metrics` returns Prometheus text for scrape-based monitoring and uses the same IP/CIDR allowlist as `/diag`.
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
- `/diag` and `/metrics` return 404 for all other requests.
- Denied access is logged as `DIAG_DENIED` with the resolved client IP and configured CIDRs; allowed access is logged as `DIAG_VIEWED`.

### What the page shows

| Section | Content |
|---------|---------|
| **App** | App version and configured name |
| **Database** | Connection status (`online` / `error`), active backend, total run and snapshot counts, SQLite file/WAL size or Postgres relation sizes, reclaimable space where available, table row counts, and backend-specific search-index checks |
| **Storage breakdown** | Table/index or relation storage grouped by runs, snapshots, Atlas/findings, projects, session data, and secrets. Shows allocated bytes when SQLite has `dbstat`, Postgres relation sizes through catalog functions, logical payload estimates, search-index rollups, and the largest saved runs. |
| **Redis** | Whether Redis is configured, and connection status when it is |
| **Vendor Assets** | Whether `ansi_up.js`, `jspdf.umd.min.js`, and the font files are present (`loaded`) or missing (`missing`) from `app/static/` |
| **Config** | All operational config values: rate limits, timeouts, output caps, retention, proxy CIDRs, log settings |
| **Classifier Inspector** | One-line output classifier check for kind, role, signals, entities, command root, target, and ANSI-stripped text; the Inspect action updates this section without reloading the full page |
| **Classifier Drift Report** | On-demand recent-output sampler for classifier drift, help-output noise, structural-role findings, entity-only lines, and body-heavy runs, with samples that open in the inspector |
| **Activity** | Run counts for today, last 7 days, this month, this year, and all-time, plus outcome breakdown (success / failed / incomplete). SIGTERM-terminated runs stay in totals but are not counted as failures. |
| **Top Commands** | Top 10 commands by run frequency and top 5 longest individual runs |
| **Tools** | Per-tool availability derived from the allowlist — which command roots are present on `$PATH` and which are missing |

### JSON output

Append `?format=json` to get the same data as a JSON object, suitable for scripting or monitoring integrations:

```bash
curl http://localhost:8888/diag?format=json
```

### Prometheus metrics

`/metrics` is meant for Prometheus, Grafana, and similar monitoring stacks. It exposes `darklab_` metrics for HTTP volume and latency, active and completed runs, PTY activity, rate-limit pressure, broker mode and subscribers, database and Redis health, selected database hot-path latency, workspace usage, Atlas/finding counts, intel provider results and cache size, evidence package builds, snapshots, client errors, and unhandled server exceptions. Labels are bounded to safe values such as command roots, provider IDs, endpoint names, status classes, and coarse outcomes.

```bash
curl http://localhost:8888/metrics
```

The repo also includes a starter Grafana dashboard at `examples/grafana/darklab-overview.json`.

**Limits:** `/diag` and `/metrics` are gated entirely by IP/CIDR allowlists, not by an authentication layer. Empty `diagnostics_allowed_cidrs` disables `/diag` completely and prevents `/metrics` from being scraped. Set `metrics_enabled: false` to keep `/diag` available while hiding `/metrics`.

**Configuration:** `diagnostics_allowed_cidrs`, `trusted_proxy_cidrs`, `metrics_enabled`, `prometheus_multiproc_dir`, and metrics histogram bucket settings in `config.yaml`; see [CONFIGURATION.md](CONFIGURATION.md).

**Related files:** `app/blueprints/assets.py` (`/diag` HTML/JSON responses and `/metrics`), `app/services/metrics/` (Prometheus metric definitions and scrape-time collectors), `app/static/css/diag.css` (page styling + mobile breakpoint behavior), `app/templates/diag.html` (diagnostics page markup), `examples/grafana/darklab-overview.json` (starter dashboard), `README.md` (operator-facing config reference), `ARCHITECTURE.md` (diagnostics and logging runtime details).

---

## Related Docs

- [Default.md](.gitlab/merge_request_templates/Default.md) - default GitLab merge request template
- [ARCHITECTURE.md](ARCHITECTURE.md) - runtime layers, request flow, persistence, security, and app internals
- [CHANGELOG.md](CHANGELOG.md) - release-by-release changes
- [CONFIGURATION.md](CONFIGURATION.md) - operator config reference for `app/conf/`, `.env`, Compose, storage, and production tuning
- [CONTRIBUTING.md](CONTRIBUTING.md) - local setup, test workflow, linting, branch workflow, and merge request guidance
- [CONTRIBUTORS.md](CONTRIBUTORS.md) - contributor and acknowledgement notes
- [DECISIONS.md](DECISIONS.md) - architectural rationale, tradeoffs, and implementation-history notes
- [DOC_STANDARDS.md](DOC_STANDARDS.md) - documentation structure, templates, and review rules
- [README.md](README.md) - project overview, quick start, documentation map, and installed tools
- [THEME.md](THEME.md) - theme registry, token reference, and custom theme authoring
- [TODO.md](TODO.md) - open follow-ups, research notes, known issues, and future ideas
- [ARCHITECTURE.md → Atlas Export Schema](ARCHITECTURE.md#export-schema) - Session Entity Atlas CSV/JSONL export schema and filters
- [docs/api.md](docs/api.md) - headless API and bundled CLI usage guide
- [docs/external-command-integrations.md](docs/external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/notifications.md](docs/notifications.md) - outbound notification channels, payloads, retries, and setup guide
- [docs/postgres-migration.md](docs/postgres-migration.md) - offline SQLite-to-Postgres cutover helper and validation workflow
- [docs/schedules.md](docs/schedules.md) - scheduled-command cadence, timezone, worker, and audit behavior
- [docs/storage-scaling.md](docs/storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [docs/watchers.md](docs/watchers.md) - change-detection watcher baseline, diff, scheduler, and notification behavior
- [tests/README.md](tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
