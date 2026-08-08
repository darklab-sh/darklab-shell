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
- [Cleanup Confirmations](#cleanup-confirmations)
- [Copy, Save, and Export](#copy-save-and-export)
- [Tabs & Run History](#tabs--run-history)
- [AI Assists](#ai-assists)
- [Run Comparison](#run-comparison)
- [Guided Workflows](#guided-workflows)
- [Scheduled Runs](#scheduled-runs)
- [Watchers](#watchers)
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
- [Production Installation](#production-installation)
- [Operator Backups](#operator-backups)
- [Session Tokens](#session-tokens)
- [Team-Mode](#team-mode)
- [Encrypted Secrets](#encrypted-secrets)
- [External Intel](#external-intel)
- [Raw-Packet Scanning](#raw-packet-scanning)
- [Security and Process Isolation](#security-and-process-isolation)
- [Structured Logging](#structured-logging)
- [Audit Log](#audit-log)
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

---

## Autocomplete

**Purpose:** shell-like completion for commands, flags, files, wordlists, variables, and tool-specific values.

**Behavior:**

- Tool suggestions load from the command registry at page load and use ranked exact, prefix, token-boundary, substring, and fuzzy matching. Matched text is highlighted in green.
- App-owned built-in commands use the same matching engine as YAML-backed tools.
- Workspace file paths and installed wordlist paths match by useful path segments and filename substrings, so users can type the part they remember instead of the beginning of the path.
- Workspace move slots marked as workspace paths suggest loaded active-scope Files and folders. `file move` and `mv` suggest sources first, then destination folders (including `/`) once the source is selected.
- Value slots marked as domains, hosts, targets, IPs, URLs, or port sets capture up to 10 recent targets per kind for the active session token. They show back up only in compatible autocomplete slots, and URLs are saved without query strings or fragments. Recents persist across browser restarts and devices when the same `tok_...` session token is active.
- The dropdown opens below the prompt when there is room and flips above when space is tight, preserving top-to-bottom keyboard navigation order.
- `Tab` expands to the longest shared prefix, then cycles matches; `Shift+Tab` cycles backward; `Enter` accepts the highlighted match or runs the command if none is selected.
- While typing a command root, a unique root match shows real example invocations. For commands with scoped subcommands, this includes both root-level and subcommand examples.
- After a known command root plus a trailing space, the dropdown switches to grammar-style suggestions for that tool: root/global flags, subcommands, and positional hints.
- While typing a subcommand token, examples narrow to the matching subcommand once the prefix is unique. For example, `amass s` can show `amass subs ...` examples, while an ambiguous prefix such as `gobuster d` keeps showing `dir` and `dns` token choices.
- After a known subcommand plus a trailing space, the dropdown switches to that subcommand's scoped flags and value hints.
- After `|`, autocomplete switches into the built-in pipe stage (`grep`, `head`, `tail`, `wc -l`, `jq`, `sort`, `uniq`).
- Inside a `| grep` stage, the dropdown also suggests tokens already visible in the active tab's output — IPv4/IPv6 addresses, hostnames, CVE identifiers, HTTP status codes, and frequently repeated words — ranked by token kind then frequency and offered as grep patterns alongside grep's own flags. Suggestions are drawn only from the active tab and never widen the allowed command surface.
- Already-used singleton-style flags are suppressed from contextual suggestions.

**Limits:** external-tool completions come from the command-registry YAML, while app-owned built-ins come from the app's built-in autocomplete YAML. The app does not inspect the live shell and does not parse `--help` output. Output-derived grep suggestions read only the active tab's rendered lines, not other tabs or the host.

**Configuration:** external-tool suggestions use `conf/commands.yaml` plus optional local overlays; see [CONFIGURATION.md#command-registry-autocomplete](CONFIGURATION.md#command-registry-autocomplete). App-owned built-in grammar isn't operator-configurable.

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

---

## Keyboard Shortcuts

**Purpose:** app-safe chords for tab lifecycle, active-tab actions, and readline-style prompt editing, shown through both the `?` overlay and the `shortcuts` built-in.

**Behavior:**

- Tab chords use `Option`/`Alt` to avoid fighting browser `Ctrl`/`Cmd` bindings; terminal chords use `Ctrl` in the readline tradition.
- While the active tab is running, app-level tab, active-tab, and UI shortcuts still work from the prompt. Normal text entry and readline-style editing shortcuts stay blocked until the run finishes, `Ctrl+C` opens the kill confirmation, and `Ctrl+D` stays disabled while the run is active.
- The `?` overlay opens from anywhere on the page (including the empty prompt); `shortcuts` prints the same reference as a text dump.
- Both views read from a single shared list via `GET /shortcuts`, so they cannot drift.

**Limits:** browser-native combos like `Cmd+T`, `Cmd+W`, and `Ctrl+Tab` are optional fallbacks only — browser interception is inconsistent across environments, especially on macOS.

**Configuration:** none; the chord list isn't user-tunable.

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
| `Option+A` (`Alt+A`) | Open/close Atlas | Browse saved entities and findings |
| `Option+Q` (`Alt+Q`) | Open Quick Lookup | Find the saved profile for one hostname, IP address, or URL |
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

- press `?` from anywhere on the page to open the keyboard-shortcuts overlay — including from the command prompt itself when it is empty, and even as the first key after page load while the welcome animation is settling. Once any text is present in the prompt (or any other input), `?` types normally so args like `curl "…?foo=bar"` are not interfered with. The handler also skips modifier chords (`Ctrl` / `Meta` / `Alt`)
- run `shortcuts` in the shell to print the same reference as a text dump inside the current tab

Both views read from the same backend list (exposed to the browser via `GET /shortcuts`), so they cannot drift. The overlay lists the `?` binding itself as the first entry so the shortcut is self-documenting.

---

## Output Streaming and Display

**Purpose:** low-latency SSE streaming with a live tail, per-line prefix toggles (timestamps and line numbers), and explicit recovery cues when the live stream goes quiet and later resumes.

**Behavior:**

- Command output arrives line-by-line over SSE; fast commands batch flushes, slow scans stream each line as it arrives.
- Each output row carries structured `kind` and `role` metadata, so live transcripts, restored history, permalinks, exports, and `/api/v1` streams agree on whether a line is normal output, a notice, a prompt echo, a section header, or another known row type.
- Known scanner chatter can also carry noise metadata for progress, status, and boilerplate lines. The transcript still shows what the command printed, but search text, comparison, summaries, and package indexes can use the quieter view.
- Stored output can be filtered by structured fields in the API and CLI. `darklab grep` and `darklab output` accept selectors for signal, severity kind, structural role, entity value, and entity type, so scripts can pull only findings, only errors, or only lines tied to a specific host/CVE without local JSON parsing.
- The output view follows the live tail automatically, including during bursty runs that repaint quickly. Only a real user scroll-away disables follow mode and shows the tab-scoped jump-to-live / jump-to-bottom helper until the tail is rejoined.
- A live elapsed run-timer sits next to the status pill while a command runs; the final elapsed time is recorded in the exit line.
- Timestamps (elapsed or clock) and line numbers are independently toggleable from the tabbar controls (or the mobile menu). Timestamp fragments stay on each row, while line numbers are assigned once as output is emitted so high-volume commands do not have to renumber thousands of visible rows after `max_output_lines` trimming begins.
- Completed output for supported noisy tools can show a short **Command
  outcome** block below the transcript. The summary is deterministic and
  app-native, not AI-generated, and currently covers common `nmap`, `dig`,
  `nslookup`, `curl`, and `openssl s_client` outcomes such as open ports, DNS
  answers, HTTP redirects, and certificate details.
- Live output rendering batches bursty streams, skips full transcript scans on normal appends, uses browser content visibility for offscreen rows, and trims old rendered rows without changing the retained raw-output model. Once `max_output_lines` is reached, visible line numbers continue increasing with the command's emitted output order rather than resetting to `1` for the remaining rendered window.
- Very noisy brokered commands automatically enter high-volume output mode after `high_volume_output_line_threshold` received lines. The tab keeps running and counting output, but the browser renders periodic status lines instead of every row until the user chooses to resume live rendering for new output.
- When the SSE stream goes quiet for 45 seconds, the shell shows inline warning copy instead of waiting indefinitely with a spinning run state.
- If the original stream later resumes, the shell prints an inline reconnection success line, restores the tab/HUD to `RUNNING`, re-enables the kill affordance, and continues streaming output in place.
- If a normal command stream detaches while the backend run is still active, the shell reattaches the brokered stream in the original tab when that tab still exists, keeps the run timer tied to the server start time, and prints a clear `[reattached to active run after stream recovery]` notice.

**Limits:** stall detection fires after 45 seconds of silence per tab; each tab has its own stall timeout so concurrent runs don't interfere. Reattach uses the normal brokered run stream and falls back to a recovery tab when the original browser tab is gone. Noise classification is intentionally narrow and command-aware; unknown output stays visible and searchable. Outcome summaries are additive and best-effort; when a supported parser can't derive a useful result, the transcript simply renders without the extra block.

**Configuration:** timestamp and line-number preferences are off by default and follow the active session token. They are mirrored locally for reload continuity, but named sessions restore the same option set across browsers and devices. Command outcome summaries are on by default and can be disabled from Options or with `config set command-outcome-summaries off`.

When command outcome summaries are enabled, text, HTML, PDF, Run Details, and permalink/share exports include the same visible summary block. The saved raw transcript remains unchanged, so the summary is always a derived view of the captured output rather than a replacement for it.

---

## Kill Running Processes

**Purpose:** operator-initiated termination of a running command via `SIGTERM` to the full process group, with a confirmation step to guard against accidental interrupts.

**Behavior:**

- Each tab shows a **■ Kill** button while a command is running; clicking it opens a confirmation dialog before sending `SIGTERM` to the full process group.
- `Enter` confirms and `Escape` cancels the dialog, matching the button labels.
- `Ctrl+C` routes through the same confirmation flow while a command is running.

**Limits:** kill dispatches from any Gunicorn worker — PID lookup goes through Redis so the request doesn't have to hit the worker that started the process. See [DECISIONS.md](DECISIONS.md) `Multi-worker Process Killing via Redis`.

**Configuration:** none — the kill path is not user-tunable.

---

## Status HUD

**Purpose:** a persistent desktop status row that brings together run state, connection health, session identity, and environment telemetry without displacing the terminal.

**Behavior:**

- The bottom bar renders live run, connection, identity, scope, and environment context on desktop; the right cluster carries the output actions (share, copy, save, clear, kill).
- Pills start with a muted `—` placeholder at page load and transition to live values on the first poll.
- Server state is polled via `GET /status` on a visibility-aware cadence: every 3 seconds while the tab is visible and every 15 seconds while hidden. Uptime is interpolated locally between polls so the pill never looks frozen, and the clock ticks once per second in the browser.
- Latency is measured client-side with `performance.now()` around the fetch call.
- The scope cell shows the active personal/team scope and opens a compact pop-up menu matching the Project switcher style, without search or creation controls. The Options **Teams** tab also offers a Personal row so users can switch back from a team scope without leaving Options.
- On narrow desktop widths the pill row falls back to horizontal overflow scrolling so the right-side HUD actions never get pushed off-screen.
- Mobile hides the HUD entirely; per-tab status and exit codes remain visible inline next to the prompt echo, and the run-notifications toggle in the Options modal covers the background-watch use case.

**Limits:** `/status` always returns 200 even when a component is degraded (reports `"down"` for that component) so HUD polling never flaps the UI or triggers SSE reconnect logic; `/health` remains the load-balancer contract and still returns 503 on degradation.

**Configuration:** the `CLOCK` pill mode is user-tunable from the Options modal (`UTC` or browser-local time). Local mode prefers the browser's short timezone label (for example `CDT`) and falls back to a GMT offset label when the browser cannot provide a stable abbreviation. Run notifications remain a separate Options-modal preference.

**Pill reference:**

| Pill | Source | Notes |
|------|--------|-------|
| **STATUS** | Active tab's run state (`running` / `ok` / `fail` / `killed` / `idle`) | Coloured pill identical to the inline tab status dot |
| **LAST EXIT** | Exit code of the most recent finished run in any tab | `0` green, nonzero red, killed red, `—` muted when no run has finished yet; dims to muted while any tab is actively running |
| **TABS** | Total tab count, with active-run annotation (`N · M active`) when any tab is running | Amber while any tab is running, muted when no tabs are active |
| **LATENCY** | Round-trip time to `/status` in ms | Green `<250ms`, amber `<500ms`, red `>=500ms` |
| **SESSION** | Active session identity | `ANON` (muted) for UUID sessions, masked `tok_XXXX••••` (green) for named tokens — see [Session Tokens](#session-tokens) |
| **UPTIME** | Server process uptime | Returned by `/status` and ticked client-side between polls so the pill never looks frozen |
| **CLOCK** | Wall clock in `UTC` or browser-local time | Ticks every second in the browser; local mode prefers the browser's short timezone label and falls back to a GMT offset |
| **DB** | Configured database connection state | `ONLINE` green, `OFFLINE` red |
| **REDIS** | Redis connection state | `ONLINE` green, `OFFLINE` red, `N/A` muted when no Redis is configured |

**Command Constellation:** the Status Monitor visualises recent run history as a constellation chart with a clock-time X axis and a log-elapsed Y axis. By default the X axis auto-fits to your active hours so the canvas stays a full sky rather than a long dead zone: edges with no activity are trimmed, and interior low-density bands (the sleep window of an operator whose runs span both ends of the day) collapse onto a `//` seam marker so the visible canvas reads as continuous clock time. Toggle to **Full day** in the legend if you want strict 24-hour reading; the seam disappears and every hour gets its proportional share of the axis. Hours with no real runs are filled by a desaturated ambient layer, and a clock-pinned daylight gradient paints the 24h cycle behind the stars so noon, dusk, and night always appear at their true hour-of-day positions in either mode. Stars use structured output metadata too: warning/error runs pick up stronger tones, and runs with more findings get a larger plotted point.

---

## Built-In Pipe Support

**Purpose:** narrow app-native pipe helpers (`grep`, `head`, `tail`, `wc -l`, `jq`, `sort`, `uniq`) plus safe Files output capture, without enabling a general shell pipeline.

**Behavior:**

- One or more supported helper stages can be chained in a single command; the final filtered view is what appears in the terminal, history, permalinks, and exports for that run.
- Server-side `sort` and `uniq` stages cap their buffered input with `max_output_lines` when that setting is nonzero and add a `[post-filter]` notice if later lines are skipped before the final result.
- `jq` is an app-owned JSON/JSONL selector, not the host binary. It supports object fields such as `.host`, array iteration such as `.results[]`, key-existence filters such as `select(has("ip"))`, equality filters such as `select(.status == "ok")`, contains filters such as `select(.title contains "login")`, pretty JSON output by default, `-c` for compact JSON, and `-r` for scalar text output.
- Autocomplete understands the narrow pipe stage and can guide `grep`, `head`, `tail`, `wc -l`, `jq`, `sort`, and `uniq` after `command |`.
- Workspace `ls` / `file list` keep their compact one-line display when run directly, but pipe helpers receive short listings as one logical entry per line so common forms like `ls | grep txt` behave like a normal terminal.
- `command > file` overwrites a file in the current Files folder and suppresses the command output from the live terminal. `command >> file` appends to the file and also suppresses live output. `command | tee file` overwrites the file and keeps the same output visible.
- Output files receive the same post-filtered, path-masked, secret-redacted stream that run history stores. Personal/team scope, write permissions, safe relative paths, quotas, and maximum file size come from the normal Files boundary. Existing directory destinations and unsafe paths are rejected before the command starts.
- A failed output write makes the run fail, including unattended scheduled built-ins. Unexpected filesystem failures return a generic message while the server log keeps the diagnostic detail.
- Autocomplete includes `tee` and active Files paths after a supported pipe. `file help` shows all three output-capture forms.
- Arbitrary pipes, command chaining, and all redirection outside the three app-managed Files forms remain blocked at the command-validation layer.

**Limits:** only the seven filter stages and final Files sinks above are recognised. `>` and `tee` overwrite their destination; `>>` appends. File-descriptor redirects such as `2>` and `2>>` aren't supported and fail closed with a stdout-only message. Combinable flags are supported within a filter stage (e.g. `sort -rn`) and supported stages can be chained together (e.g. `command | grep pattern | wc -l`). The `jq` helper intentionally rejects arbitrary jq programs, shell escapes, joins, transforms, arithmetic, recursion, and file access. Malformed JSON produces a generic error without echoing the input line.

**Configuration:** external command metadata lives in `conf/commands.yaml`; the built-in helper grammar and execution limits aren't operator-configurable.

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
- `command | jq .host`
- `command | jq -r .host`
- `command | jq -c .host`
- `command | jq .results[]`
- `command | jq 'select(has("ip"))'`
- `command | jq 'select(.status == "ok")'`
- `command | jq 'select(.title contains "login")'`
- `command | sort`
- `command | sort -r`
- `command | sort -n`
- `command | sort -u`
- `command | sort -rn` (flags combinable)
- `command | uniq`
- `command | uniq -c`
- `command | grep pattern | wc -l`
- `command | sort -u | uniq -c`
- `command > output.txt`
- `command >> output.txt`
- `command | tee output.txt`
- `command | grep pattern | tee matches.txt`

---

## Output Search

**Purpose:** in-transcript text search over the current tab output with case and regex toggles and keyboard navigation between matches.

**Behavior:**

- Click **⌕ search** in the tabbar (on the right, alongside the timestamp and line-number toggles) — or press `Alt+S` — to open the search bar above the output.
- Matches are highlighted in amber; the current match is highlighted brighter.
- Use **↑ / ↓** buttons or **Enter** / **Shift+Enter** to navigate between matches; **Escape** closes the search bar.
- Case-sensitivity (**Aa**) and regex mode (**.\***) toggles sit between the input and the match counter; both re-run the search immediately when clicked.
- Saved history search text for new runs skips lines the app has classified as progress, status, or boilerplate noise, so repeated scanner updates are less likely to drown out useful matches. The tab's visible transcript remains unchanged.

**Limits:** search scope is the active tab's rendered transcript only — not history from other tabs, not the full server-side run history. Invalid regex patterns render `invalid regex` instead of throwing.

**Configuration:** none — toggle state is not persisted across page reloads.

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
  - historical URL rows from `gau`, kept as passive discovery metadata rather than vulnerability findings
  - severity-tagged result rows from `nuclei`
  - JSON rows from `tlsx`, `cdncheck`, TruffleHog, and `puredns`
  - DNS answers and query outcomes from `dig`, `host`, and `nslookup`
  - certificate and TLS verdict lines from `openssl s_client`, `sslscan`, `sslyze`, and `testssl`, including `s_client` certificate subjects, issuers, key details, validity windows, negotiated TLS details, and verification status without treating PEM bodies as findings
- Structured output from the staged external tools feeds Atlas and saved run metadata directly:
  - `gau` URL rows become Atlas URL entities with passive-provider and source-run provenance, so archived paths can be reviewed before any live probe without being mistaken for vulnerabilities.
  - `tlsx -json` rows create TLS findings, domain/IP/certificate-hash entities, and warnings for certificate or probe problems.
  - `cdncheck -jsonl` rows create host/IP entities and summary context; CDN, cloud, and WAF matches are not treated as vulnerabilities.
  - TruffleHog JSON rows create redacted findings from detector, verification, source, repository, file, commit, and line metadata without storing raw secret values as titles or snippets.
  - `puredns` valid-domain rows create domain entities and findings, while wildcard rows are warnings and workspace output files stay tied to run-file artifact records.
  - Nuclei output and Nuclei JSONL imports keep template-source provenance so later review can tell whether findings came from the managed template cache, a workspace template path, a pinned-looking clone, or an operator-updated template set.
- Noise-heavy lines are intentionally excluded from findings when they behave like banners, progress meters, or startup chatter instead of actionable results.
- The same server pass also attaches structured entity metadata to external command output lines when it sees public IPs, hostnames, hashes, or CVE IDs. Generic hostname extraction uses an offline Public Suffix List check so dotted code snippets like `classlist.add` or `document.queryselector` do not become domains. Full URLs, scanner-specific rows, imports, and explicit project targets use stronger parser paths and keep their current behavior. That metadata is kept with live streams, restored history, saved full-output artifacts, and the Session Entity Atlas without re-parsing transcripts.
- User-killed runs are intentionally **not** counted as errors; the transcript still shows the kill line, but the signal counts stay focused on issues the operator may need to investigate.
- The **summarize** button appends a synthetic **Command Findings:** block to the active tab after the tab is idle. The summary groups external command blocks by server-provided command and target metadata when present, merges repeated runs for the same command/target, collapses duplicate full-command labels with a repeat count, includes only command blocks that produced at least one finding/warning/error/summary line, and falls back to per-command sections when target metadata is unavailable. The button stays disabled while the active tab has a running command so synthetic summary output cannot mix into live command output.
- Run Details shows a compact output summary above restored transcripts, including counts by severity kind, signal, and entity type plus quick outline rows for section headers, key/value rows, and signal-bearing lines.
- If a single command produces per-target metadata for multiple targets, such as `nmap -iL ...` output with multiple `Nmap scan report for ...` sections, the summary splits that one command into separate target sections instead of combining every host's findings together.
- Built-in command output is intentionally excluded from findings, warnings, errors, summaries, and generated command-findings blocks so help/status/catalog text does not create review noise.
- External command help output is also treated as reference text, so examples shown by `-h`, `--help`, and tool-specific help flags do not create findings or Atlas entities.
- Summary blocks are helper UI output, not raw command output. They do not feed back into the signal counters or search matches.

**Limits:** signal detection is server-classified, scoped to the active tab’s transcript, and intentionally favors the project’s supported toolset over arbitrary command output. Browser-side signal fallback is intentionally not used; older restored output without signal metadata is treated as signal-unavailable. A command with no matched findings, warnings, errors, or summary lines does not appear in the generated summary block.

**Configuration:** `output_entity_extra_domain_suffixes` can opt generic bare-hostname extraction into internal suffixes such as `.local` or `.corp`. The current scopes, server matchers, and summary format are otherwise app-defined and not operator-configurable.

---

## Session Entity Atlas

**Purpose:** browse the entities the shell has seen across saved external runs, without starting from a specific project or transcript.

### Quick Lookup

Quick Lookup opens the exact saved Atlas profile for one hostname, IP address, or HTTP(S) URL without making you search or page through the Atlas list. Open it beside Atlas in the desktop rail or mobile menu, or press `Alt+Q` / `Option+Q`. These shell entry points use the current personal or team scope.

- Choose **Auto** to detect the value type, or choose **Hostname**, **IP**, or **URL** to require one. Hostname records appear as the Atlas `domain` type. URLs must be absolute and start with `http://` or `https://`; URL-shaped input without a scheme is rejected instead of being guessed.
- Invalid input gets a specific correction, while a valid value with no saved record gets a separate no-record result. Quick Lookup can show a bounded choice when legacy data contains more than one visible exact record. If an exact URL isn't saved but its hostname or IP is, **Open known parent host** offers that saved profile without pretending it matched the URL.
- **New lookup** returns to the form. **Open in Atlas** moves a found record into normal Atlas browsing. No-record results can **Search Atlas** or **Switch scope**, and command suggestions only prefill the terminal composer—they never run automatically.
- Results read saved scan evidence, findings, relationships, metadata, and owner-scoped Intel snapshots. Looking up a value doesn't run a command, create an entity, or contact an Intel provider. **Refresh intel** remains the explicit action for fetching current provider data.

**Behavior:**

- Open **Atlas** from the desktop rail, mobile menu, `Alt+A`, History row actions, Run Details, Project Overview, or a project filtered view. Direct entity links from transcripts, Run Details, Projects, and Project Overview open the full profile immediately.
- Use the active desktop, mobile, or keyboard Quick Lookup entry again to close it. Exact resolution includes suppressed and source-less records visible in the active scope and accepts one host at a time, so network ranges get a clear single-host explanation.
- Atlas groups saved entities by **Findings**, **IPs**, **Domains**, **Ports**, **Hashes**, **CVEs**, and **URLs**. Entity rows show the canonical value, hit count, source-run count, project links, and labels. Port rows come from app-captured scanner output and can show the service or version when the tool reported it. Domain and IP details list related URLs and ports, while URL and port details link back to their stored parent host.
- Atlas search matches entity values plus Atlas labels and notes, so curated metadata is as findable as values copied from command output.
- Atlas can be scoped to one source run from Run Details or from the Atlas run filter, and to one project from Projects or from the Atlas project filter. Those filters apply across the Findings queue, entity tabs, tab counts, and entity exports until you clear the visible chip or use **Clear filters**.
- The Atlas toolbar can import external triage files from Nuclei JSONL, Nessus XML, OWASP ZAP JSON/XML, Burp Suite XML, Generic CSV, and Generic JSONL. Imports show a preview with counts, samples, and row warnings before anything is written. Applying an import writes a high-level audit row with the source tool, format, selected options, project id, row/count summary, and created/updated counts without storing imported row bodies. From a project-filtered Atlas view, you can also link imported entities to that project or create project targets from imported domains, IPs, and URLs.
- When a team scope is active, Atlas views follow team-owned source runs. Team members can review deduplicated team-owned entities, source runs, and findings produced by shared runs, add shared labels and notes, refresh cached intel, update finding review/suppression state, and link Atlas entities into team projects without pulling in their personal Atlas rows.
- Run Details shows the source run's Atlas entity count and includes paged entity tabs for the same entity types, so you can inspect generated IPs, domains, ports, hashes, CVEs, and URLs without leaving the run modal.
- Entity details page through source runs, direct findings, related URLs, and related ports when more rows exist than fit in one view, so older evidence stays reachable without loading the whole collection at once. Paging keeps the current entity and reading position in place.
- Saved views remember useful Atlas filter sets for the active session token, including search text, source run, orphan filter, suppression filter, Findings review state, and project scope. Applying a saved view keeps you on the current Atlas tab, and **Clear filters** returns the visible filter controls, project scope, source-run scope, and saved-view picker to their defaults.
- On mobile, Atlas uses a list/detail flow with Back navigation, compact filters, bottom-sheet actions, and select mode from the overflow menu so entity triage fits the same touch pattern as Projects and History.
- The **Findings** tab works as the cross-run triage queue. It lists deduped findings, supports text, project, source-run, review-state, and verification-status filters, opens finding detail with source-run and entity navigation, and can update or delete selected visible findings in bulk. Each saved finding keeps how it entered the app—run, import, or manual—separate from how the evidence was validated, so an imported assertion isn't presented as a command result. Matching observations of the same CVE or scanner rule on the same exact affected subject share one review state and one remediation guide, while their validation method, confidence, verification steps, verification status, verification notes, and evidence remain separate. Different targets, vulnerabilities, and rules don't share guidance automatically. Compact badges show when follow-up work exists without crowding the list. Verification status uses `not_started`, `ready_to_verify`, `verified`, `needs_retest`, or `not_applicable`. On desktop, the larger Findings Board opens from the rail, Atlas toolbar, or Projects and groups findings into New, Reviewed, False positive, and Follow-up lanes for quicker review-state triage. Mobile keeps Findings in the list flow so the review tools fit the narrow screen.
- Selecting an entity opens a quick detail pane grouped as **Observed by darklab_shell**, **Findings and work**, **Relationships**, **Evidence**, **Metadata**, then **External intelligence**. Findings stay near the top, Projects appear before long relationship lists, and finding, URL, port, app-port, source-run, and import collections show up to three rows before offering a link to the complete focused view. **View profile** expands that same Atlas dialog into a focused workspace with **Overview**, **Evidence**, **Findings**, and **Intel** views; **Back to results** restores the same filters, page, selection, and reading position. The focused profile shows the canonical identity, first and last observation, project-link count, suppression, and missing-source state above its tabs, with **Copy value** available on desktop and mobile. When Atlas is scoped to a Project, domain, IP, and URL profiles can open **Create finding** with that entity attached as evidence, and assessor-authored findings keep a separate **Edit finding** action. Finding summary cards open the exact direct, related-URL, related-port, or combined findings behind each count. The observed section shows whether darklab_shell has run a port scan, whether that scan surfaced app-captured ports, when it last ran, and which scanner recorded it; a completed scan with no surfaced ports is clearly different from an entity that hasn't been scanned. Host profiles show a compact app-captured port list with the reported protocol, service, version, banner availability, number of sightings, last-seen time, and source-run count. URL and port details label scan coverage and shared host evidence as coming from the resolved parent host. When Atlas is filtered to a project, the profile also shows watcher state and recent watcher changes matched to that entity. Owner-wide profiles leave that project-only section out. Host profiles show findings on the host separately from findings on immediate URL and port children, plus a clearly labeled combined host-surface total. Suppressed findings are counted separately instead of inflating the active severity, review, or verification summaries. The external intelligence summary says whether cached data is fresh, stale, unknown, or unavailable, shows how many providers returned data and when it was refreshed, and keeps each raw provider response in its existing expandable card. Domain profiles also surface relevant certificate state, while domain and IP profiles call out differences between app-captured and provider-reported ports as a recorded comparison rather than a finding; comparison actions jump to the app evidence or provider data that explains the difference. Empty profiles suggest the next useful action, such as running a scan, refreshing Intel, or opening the parent host. Direct findings and related entities use the same full-width clickable row style, source-run titles open Run Details, and linked projects offer both **Open Project** and unlink actions. The focused Evidence view keeps complete paged collections and the per-run **Clean from Atlas** action. Closing a linked Project returns to the same Atlas or Quick Lookup profile, local view, related-entity path, and reading position. Mobile uses the same four profile views, native Back behavior, and sticky detail footer without opening another overlay.
- Select mode adds checkboxes on the visible page for any Atlas tab. You can suppress or restore selected noisy rows without deleting source data, delete selected findings directly, or delete selected entities and their attached findings in one confirmed action.
- Entity tokens in saved and live transcripts can open Atlas directly. Long-pressing or right-clicking a token opens quick actions for copying the value, refreshing intel, editing metadata in Atlas, or refocusing the transcript line.
- **Refresh intel** fetches current app-native intel for provider-backed entities, shows a progress panel while slower providers run, and stores normalized provider snapshots back on the entity. Port entities are app-captured scanner evidence, so they don't offer provider refresh.
- **Clean Atlas** removes a source run's Atlas links while keeping its History transcript. The shared [Cleanup Confirmations](#cleanup-confirmations) rules explain what else can be removed and what stays protected.
- **Add to active project** links the entity to the current project without copying it. Project-filtered Atlas opens show only the entities linked to that project.
- Labels and notes use the same metadata editor model as History, Files, and Projects, so entity notes stay attached to the entity wherever it appears.
- Entity tabs can export the current Atlas filter as CSV or JSONL. Exports include summary fields, port host/service metadata, suppression state, labels, notes, project names, and provider names that have cached intel, but they leave raw provider response bodies out.

**Importing external reports:** Atlas imports are for bringing third-party triage results into the entity and finding view without pretending those results came from a shell command.

- Supported formats are Nuclei JSONL, Nessus XML, OWASP ZAP JSON/XML, Burp Suite XML, Generic CSV, and Generic JSONL.
- Nuclei JSONL imports preserve template-source provenance when the source data includes it, matching the provenance shown on saved Nuclei output.
- Preview always runs before apply. It shows parsed row counts, new/duplicate/update counts, sample entities and findings, row warnings, and which apply options are available for the current personal or team scope.
- Invalid rows stay out of the apply step and appear as preview warnings. Imported severity values are normalized into Atlas severities when possible; unsupported severity text is kept from becoming a misleading review signal.
- Dedicated report adapters preserve clear remediation fields as finding triage guidance. Nessus `solution`, ZAP `solution`, and Burp Suite `remediationDetail` text become finding remediation when the imported finding is applied, while existing operator-edited remediation is kept if a later import disagrees.
- Imports do not create History rows, terminal transcripts, command artifacts, or run-comparison inputs. They create Atlas records with an import origin and imported-assertion evidence method, plus the existing import-source provenance.
- Imported detail views show whether a source created the row or added another source to an existing row, using labels such as `Created by Nuclei JSONL import` or `Also seen in Nessus XML import`.
- Apply is idempotent. Re-applying the same draft returns the existing batch instead of duplicating entities, findings, source links, or project links.
- Team imports use the active team scope. Importing findings requires triage permission, and any path that creates entities, links entities to projects, or creates project targets requires project-mutation permission. If a finding references a new normalizable entity, applying that finding needs both permissions.
- Project-scoped imports can optionally link imported entities to the current project and create project targets from imported domains, IPs, and URLs. Creating targets creates or reuses the matching Atlas entities so the target has the same canonical identity and import provenance. Those options are opt-in and use the normal Project target and quota checks.
- Upload size, parsed rows, finding count, warning count, XML element count, preview sample size, warning sample size, and draft lifetime are all bounded by operator configuration. Drafts expire if they are previewed but not applied.

**Generic CSV and JSONL import schema:** use these formats when a tool does not have a dedicated adapter yet, or when you want to shape a small triage handoff yourself. Each row/object can describe an entity, a finding tied to an entity, or a finding tied only to a `subject_key`.

Supported fields:

- `row_type` or `type`: use `entity` for entity-only rows. Rows with a finding title are treated as finding rows.
- `entity_kind` or `kind`: one of `domain`, `ip`, `port`, `url`, `cve`, or `hash`. `host` is accepted as a domain alias. Imported URL rows create or reuse the scoped domain or IP host entity and store that relationship on the URL row. Imported port rows accept `host:port/proto` values, default to TCP when the protocol is omitted, and support TCP or UDP. IPv6 hosts use brackets, such as `[2001:db8::1]:443/tcp`. Port rows do not create a separate host row unless the file also includes that host as its own entity.
- `entity_value` or `value`: the value to normalize into Atlas.
- `subject_key` or `subject`: a stable subject for a finding that does not have a normalizable entity.
- `title` or `finding_title`: the finding title.
- `severity`: `info`, `low`, `medium`, `high`, or `critical`. Numeric scores and common words such as `moderate` are normalized when possible.
- `description`, `evidence`, `external_id`, `references`, and `observed_at`: optional provenance and finding detail fields. CSV references can be separated by commas or whitespace; JSONL references can be a string or an array.

Malformed or ambiguous port values stay out of apply and show up as preview warnings, so the import can be corrected before it changes Atlas.

Runnable Generic CSV example:

```csv
row_type,entity_kind,entity_value,subject_key,title,severity,description,evidence,references,external_id,observed_at
entity,domain,darklab.sh,,,,,,inventory-1,2026-06-01T12:00:00Z
entity,port,darklab.sh:443/tcp,,,,,,inventory-2,2026-06-01T12:02:00Z
finding,url,https://darklab.sh/login,,Missing CSP,medium,Header missing,No CSP,https://owasp.org,ext-1,2026-06-01T12:05:00Z
finding,,,third-party-app,Vendor finding,high,Manual review,Tool reported finding,,ext-2,2026-06-01T12:10:00Z
```

Runnable Generic JSONL example:

```jsonl
{"row_type":"entity","entity_kind":"domain","entity_value":"darklab.sh","external_id":"inventory-1","observed_at":"2026-06-01T12:00:00Z"}
{"row_type":"entity","entity_kind":"port","entity_value":"[2001:db8::1]:53/udp","external_id":"inventory-2","observed_at":"2026-06-01T12:02:00Z"}
{"row_type":"finding","entity_kind":"url","entity_value":"https://darklab.sh/login","title":"Missing CSP","severity":"medium","description":"Header missing","evidence":"No CSP","references":["https://owasp.org"],"external_id":"ext-1","observed_at":"2026-06-01T12:05:00Z"}
{"row_type":"finding","subject_key":"third-party-app","title":"Vendor finding","severity":"high","description":"Manual review","evidence":"Tool reported finding","external_id":"ext-2","observed_at":"2026-06-01T12:10:00Z"}
```

**Limits:** Atlas only includes entities materialized from saved external-run output after the entity store was added. Built-in commands do not create Atlas entities.

**Configuration:** Atlas uses existing history retention, intel cache, and provider-secret settings. Provider keys are managed through Options → Secrets or `secret set NAME`.

---

## Cleanup Confirmations

**Purpose:** make optional Atlas cleanup predictable anywhere a run or project link is being removed.

Cleanup previews use the same three groups across History, Projects, and Atlas:

- **Disposable** rows only depend on the source or link being removed and have no saved curation that needs protection. You can opt into removing them with the surrounding action.
- **Kept by default** rows have a project link, project-visible finding relationship, label, note, or review state. They remain unless you select the separate option for kept single-source rows.
- **Not eligible** rows still have another source or were imported independently, so the current cleanup cannot remove them.

Optional cleanup checkboxes start unchecked. Confirmations show counts and reasons before anything changes, and compact samples for kept-by-default or not-eligible rows stay collapsed until you open them.

**History:** deleting a run always removes its transcript. The confirmation can also remove disposable Atlas entities and findings that only came from that run, with a separate opt-in for kept single-source rows.

**Projects:** removing one or more runs from a Project can also remove disposable same-run Atlas entity links from that Project. The confirmation separately counts kept links, rows that aren't eligible, and related findings that will leave the Project Findings view.

**Atlas:** **Clean Atlas** removes a source run's Atlas links without deleting its History transcript. Deleting an entity or finding can also offer a same-source sibling cleanup; the selected row is handled by the delete action itself and doesn't block eligible sibling cleanup.

**Limits:** cleanup stays inside the active personal or team scope. Not-eligible rows can't be forced through these cleanup options; remove their other source or relationship first when that is appropriate.

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

---

## Tabs & Run History

**Purpose:** multi-tab workspace with per-session run history, full-text search over commands and output, starring, and reload-safe reconnection to in-flight runs.

**Behavior:**

- Each command runs in the active tab; the **+** button opens additional tabs for side-by-side sessions. Tabs show a status dot (amber running, green success, red failed/killed) and start with labels such as `shell 1`, `shell 2`, and `shell 3`. Commands that keep running past the brief visual grace period show temporarily in the tab label, then the tab returns to its stable label when the command finishes. Double-click to rename, drag to reorder, tab-scroll arrows when more tabs are open than fit the window width. Draft input is preserved per tab.
- The **⧖ history** button opens a slide-out drawer listing persisted session history with a `type` filter for **all**, **runs: all**, **runs: built-in**, **runs: external**, and **snapshots**. Run rows open Run Details on click; each row also has a toggleable **star** plus **copy command**, **restore**, **permalink**, **delete**, and project-aware **more** actions for external runs. External run rows show their Atlas entity and finding counts when structured Atlas data exists. Snapshot rows show the snapshot label and created time plus **open** / **copy link** / **edit** / **delete** actions. Run and snapshot rows surface existing label badges and note indicators so project/workflow context is visible without opening another modal. The **restore** action loads the run's output into a tab with the command shown as a styled prompt line (activating an existing matching tab when one exists). Starred runs list before unstarred ones regardless of age. Star state persists server-side per session and follows named session tokens.
- Select mode adds checkboxes for completed runs and saved snapshots on the visible page. **Select all**, **Clear**, and the top-level **Actions** menu let you add selected external runs to the active project, add them to a chosen project, remove them from linked projects, export selected history as readable text or JSONL, or delete selected history items in one pass. Bulk project actions skip runs that are already in the requested state instead of failing the whole request, export files call out skipped rows inside the download, and running rows are not selectable for bulk delete.
- The History row and Run Details **more** menus are project-aware for external runs: unlinked runs offer **add to active project** and **add to project**, while runs that are already linked to one or more projects show **remove from project** instead. Run removal follows the shared [Cleanup Confirmations](#cleanup-confirmations) rules for optional Atlas entity-link cleanup. Built-in runs stay in History without project-link actions.
- When a saved run belongs to the active Project, Run Details can select up to 20 output lines and either create a finding from them or add them as typed evidence to an existing finding. Selection keeps exact saved line numbers, stays available after a failed save, and uses the same finding editor and team permissions as Project Findings.
- When AI assists are enabled, Run Details can show a summary card and next-command suggestions for completed external runs. See [AI Assists](#ai-assists) for the full behavior and privacy model.
- When full-output persistence is enabled, the history drawer's permalink points at the complete saved artifact; loading into a tab still uses the capped preview and shows a notice linking to the permalink if truncated. The active tab's **share snapshot** action creates a separate `/share/<id>` snapshot and can optionally redact before saving.
- The **delete all** button in History follows the active filters and shows the exact number of matching runs before anything is removed. The confirmation offers counted **Delete all** and **Delete Non-Favorites** choices, so you can clear a filtered result set without touching unrelated history or keep starred matches while deleting the rest.
- If the page reloads mid-run, the shell restores a running placeholder tab with the kill action available and subscribes back to the brokered `/runs/<run_id>/stream` for replay plus live output when events are still retained. Active-run recovery is client-aware: another browser using the same session token can see the live run in Status Monitor without automatically creating a terminal tab or taking over the stream. Scheduled and watcher-fired runs also stay in Status Monitor until you explicitly attach to them. Non-running tabs restore separately from `sessionStorage` with labels, transcript previews, statuses, and draft input preserved; restored completed tabs remount a live prompt immediately.
- If a restored or attached run belongs to a different personal/team scope, the terminal shows a scope-switch message instead of treating the run as missing.

**Limits:** tab count capped by `max_tabs`; history surfaces paginate stored items rather than showing one unbounded list; brokered live replay is bounded by configured replay retention and `max_output_lines`, after which completed-run restore relies on persisted history/output artifacts. Snapshot search matches the snapshot label, not the full snapshot body content.

**Configuration:** `max_tabs` in `config.yaml` (default 8; `0` for unlimited).

**Full-text search:** the history surfaces support a shared `type` filter, run-subtype filters, project filters for linked runs, and full-text search across command text and stored run output for run rows, with additional filters for command name, exit status, recent date range, starred-only, and structured output selectors such as `signal:findings`, `kind:error`, `kind!=info`, `role:exit-fail`, `entity:darklab.sh`, and `entity_type:cve`. The drawer also exposes `signal`, `kind`, `entity`, and `entity_type` as visible controls, so common structured-output searches don't require memorizing query syntax. The search field placeholder reads "search history". Search is backend-aware: SQLite uses `runs_fts` with a `LIKE` fallback for short terms, while Postgres uses substring `ILIKE` clauses backed by `pg_trgm` indexes. When full-output persistence is enabled, `output_search_text` is populated from the complete gzip artifact so early lines of long runs stay reachable; otherwise it falls back to the capped preview window. Snapshot search matches the snapshot label only, and snapshots remain share/history records rather than project-linked records. On mobile, search, advanced filters, and bulk actions stay behind the dedicated **history tools** toggle to preserve result space; the command-name field uses app-owned autocomplete, and row actions keep the sheet open where that matches the desktop action contract. Ctrl+R stays command-only so reverse history search keeps normal shell expectations.

On mobile, the **☰** menu in the top-right header opens a bottom-sheet that groups session-scoped actions (search, clear, line numbers, timestamps) and overlays (options, workflows, scope, Atlas, Quick Lookup, Projects, History, Files, Schedules, Watchers, Findings, Status, Commands, FAQ, Theme, diag) — see the Mobile Shell section below for the full layout.

---

## AI Assists

**Purpose:** optional summaries and next-command drafts for completed runs, designed to help operators review noisy output without handing control to the model.

**Behavior:**

- AI assists are off by default. When enabled, Run Details shows AI cards only for completed external runs, not active runs or built-in command rows.
- **AI Summary** produces a short summary, key signals, warnings, and a next-step hint. The summary is separate from the transcript and never replaces stored output, findings, Atlas entities, search text, or comparison data.
- **AI Next Commands** drafts follow-up commands with short reasons. Suggestions are treated as untrusted until the app validates the command root, target, known open ports, redaction placeholders, and a small set of known-bad flags.
- Accepted suggestions show a **Copy** action. If `AI_FEATURE_RUN_SUGGESTIONS` is enabled, they can also show **Run**, which submits through the normal composer path so command policy still gets the final say.
- Rejected suggestions stay visible under **Blocked** with a rejection reason such as `target_absent`, `port_absent`, `unknown_root`, `invalid_flag`, or `redaction_sentinel`.
- Refreshing an AI card queues new work or returns a cached result. While a request is queued or generating, the card shows status, progress text, and provider progress such as elapsed time and token counts when the provider reports them.
- In an active team scope, AI cards for team-owned runs are visible to team members and reuse the team's cached assist rows. Personal scope never mixes in team-owned AI output.
- Backend rate-limit, queue, provider, malformed-response, and no-context errors are shown in the matching AI card without clearing unrelated completed AI output.
- Operators can point assists at an OpenAI-compatible provider, including the bundled llama.cpp Compose profile. The default posture requires a private provider URL unless an operator explicitly allows another CIDR range.
- AI context is built from completed run metadata, persisted findings, compact remediation/verification rows, and bounded output sections. Share/export redaction rules run before provider calls, and target validation prevents suggestions from introducing unrelated hosts.

**Limits:** AI output is assistant-generated metadata, not authoritative scan truth. Summaries can still be wrong, and suggestions can be blocked even when a human could adapt them safely. Multi-target or heavily redacted runs may produce generic summaries or blocked suggestions when the app cannot prove a single safe target.

**Configuration:** `AI_ENABLED`, `AI_WORKER_ENABLED`, `AI_BASE_URL`, `AI_MODEL`, `AI_FEATURE_SUMMARY`, `AI_FEATURE_NEXT_COMMANDS`, and `AI_FEATURE_RUN_SUGGESTIONS` control the common setup. See [Configuration](CONFIGURATION.md#environment-variables-and-env) for the full operator list and [AI Privacy Posture](docs/ai-privacy.md) for provider, storage, and logging details.

---

## Run Comparison

**Purpose:** compare two saved runs without manually switching between transcripts, while preserving enough surrounding context to understand what changed.

**Behavior:**

- Run comparison can launch from the History drawer, Run Details modal, mobile History panel, Projects modal, the desktop active-tab HUD, or the mobile menu. A compact action beside a completed tab's Findings signal opens the same comparison directly in **Findings only** mode.
- App-launched comparisons place the older baseline on the left and the newer/current run on the right, so added means newly present and removed means no longer present. Direct API requests still honor the `left` and `right` ids exactly as supplied.
- Automatic and manual previous-run choices include completed external runs from the active personal or team scope. Running, built-in, unsaved, and inaccessible runs don't appear as candidates.
- Transcript comparison strips app chrome lines before diffing, keeps each run's original output order, and aligns changed hunks across **Baseline** and **Current**. Unchanged context is folded by default with **Show unchanged lines** controls and lazy expansion for large equal regions.
- Lines classified as transcript noise are folded out of the default comparison so progress/status churn doesn't look like a meaningful change. When that happens, the comparison shows a muted note with the number of folded noisy lines.
- When supported scan output exposes stable structure, Run comparison shows a compact **Detected changes** section above the transcript diff. It summarizes nmap port/service changes, web URL/status/title changes, discovered hosts, and TLS subject, issuer, alternative-name, validity, SHA-256 fingerprint, and verification changes. Anchored rows jump back to the matching transcript line; an unsupported or ambiguous pair simply keeps the raw diff.
- Users can switch between responsive view modes: automatic for the current screen, side-by-side where space allows, unified, changes-only, and findings-only. **Findings only** is literal: it shows changed, added, and removed persisted findings while hiding transcript hunks, detected tool groups, entities, and artifacts. Context controls expose compact, expanded, and all-context views for the current comparison without changing the user's saved default options.
- **Prev change** and **Next change** navigate between changed transcript regions. Restore actions can load the baseline, current run, or both runs back into terminal tabs, and **Copy summary** creates a concise text summary of the comparison.
- Findings and run-owned artifacts are compared as objects rather than raw line positions. This keeps matching findings/artifacts stable even when tools emit the same results in a different order. Finding occurrences retain the severity observed by each run, so a matching finding whose severity changes appears once under **Changed findings**, with baseline/current severity and a jump action for each transcript side. Added, removed, and changed object groups include per-side totals and truncation metadata.
- Severity history is exact for occurrences recorded after schema migration `0044`. Older occurrence rows use a best-effort value rebuilt from retained finding and snippet data; when a dependable match isn't available, comparison shows separate added and removed findings instead of guessing at a severity change.
- Runs started by a workflow show their playbook title and step in the comparison card. **View playbook** opens the existing Workflows execution view instead of creating a separate provenance surface.
- Mobile uses the same comparison overlay with stacked output panes, mobile-safe dropdown placement, and touch-friendly controls.

**Limits:** comparison is optimized for saved run history, not live streams. Very large equal regions are summarized until expanded, and backend byte/hunk caps protect the compare payload from unbounded responses.

**Configuration:** compare view and compare context defaults are saved user options. Server-side compare limits are fixed application constants rather than operator-facing `config.yaml` settings.

---

## Guided Workflows

**Purpose:** curated and user-saved multi-step diagnostic sequences that turn repeat checks into reviewable command playbooks.

**Behavior:**

- **Browse all workflows** in the desktop rail, `Alt+G`, and the mobile ☰ menu open the same Workflows workspace. The **Workflows** tab has search, source filters, grouped personal/team/built-in definitions, and one selected detail. Clicking a workflow in the desktop rail opens that workspace with the definition selected instead of hiding the rest of the catalog.
- Clicking a step pre-fills the prompt with its `cmd`, and each step can also be run directly. `Run all` keeps legacy workflows in the active tab and starts a durable server execution for explicit v2 playbooks.
- The **Executions** tab shows recent durable playbooks in the active personal or team scope, including their current step, elapsed time, branch outcome, capture names, and linked runs. Active runs can be attached to a terminal tab, completed runs open in Run Details, and cancellation asks for confirmation before stopping the current step.
- Active playbooks continue when the Workflows panel closes. Reopening the panel, reloading the app, or switching scope restores the matching execution state; the desktop modal and mobile sheet use the same controls.
- The **New Workflow** editor saves personal workflows by default, or shared team workflows when a team scope is active. Saved workflows can be edited or deleted from their detail view; deleting one keeps the workspace open, selects the next definition, and removes the deleted item from the desktop rail immediately. The Parameters section supports text, target, domain, host, URL, port, port-set, Files-path, and wordlist values with labels, defaults, placeholders, help, and required state. Steps have stable IDs, **After success** and **After failure** routes, and repeatable exact-exit-code routes that take priority over those defaults. Steps can be reordered or renamed without losing their routes; a deleted destination stays visibly marked until the route is changed or removed. Each step can capture a first line, matching line, structured entity, or JSON Pointer value for later steps; command previews label those future values as available during the playbook. Invalid parameters, steps, transitions, exit codes, and captures are called out beside the matching field.
- The terminal-native `workflow` command supports `list`, `show`, and `run`; missing required variables are prompted transcript-style. Sensitive values use masked fields and non-echoing prompts, and must be omitted from inline flags so they don't appear in the command transcript. Starting an execution still stores all supplied values, including sensitive inputs, in the owner-scoped execution record and database backups, so credentials that shouldn't become workflow history belong in app-managed Secrets. Sensitive inputs appear as `[redacted]` in active-run summaries, History command text, Run Details, logs, metrics, and notifications, while values captured from an earlier step appear as named placeholders. Execution status responses contain progress and linked-run state, not stored inputs, captured values, definition snapshots, session tokens, or browser ownership hints. This boundary covers app-managed metadata; a command that prints a value can still put it in its own saved output. A terminal-started playbook returns its durable execution id and points to `workflow status` instead of leaving an initial-step snapshot that can go stale. Playbooks started with **Run all** keep progress in the Workflows panel without adding partial status to the active terminal. `workflow runs`, `workflow status <execution-id>`, and `workflow cancel <execution-id>` expose durable v2 execution state.
- Each step can show a short `note` explaining what the command checks.
- Personal workflows are stored with the active session and migrate with session tokens. Shared team workflows stay in that team scope; owners and admins can create, edit, and delete them, while other team members can use them when running commands.
- Built-in workflows cover DNS troubleshooting, TLS/HTTPS checks, HTTP triage, quick reachability, email server checks, passive domain recon, subdomain enumeration and validation, web directory discovery, SSL/TLS deep dives, CDN/edge behavior checks, API recon, network path analysis, fast port/service triage, and Files-backed chained recon such as subdomain HTTP triage, Historical Web Surface Triage, and crawl-and-scan.
- Historical Web Surface Triage collects archived URLs with `gau` without probing them, keeps only normalized URLs on the approved domain or its subdomains, and checks that set for live HTTP services. It rechecks scope before Katana receives confirmed live URLs and again before the final HTTPx summary. Each intermediate Files entry is capped, so a large archive result can't silently become an unbounded active scan.
- Custom workflows can be added to `conf/workflows.yaml`; the file is re-read on every request so edits take effect without a restart. Invalid v2 entries, unsupported explicit versions, and malformed YAML are rejected instead of exposing a partial playbook.
- Workflows that depend on Files can declare `feature_required: workspace`; those entries are hidden when `workspace_enabled` is off.

**Limits:** every step still runs through the normal command policy and runtime readiness checks. The server allows three active executions per personal or team owner by default and stops an execution after four hours. Team state, the initiator's membership and run permission, and the initiating session token are checked again before each step. Workflow, step, parameter, and capture ids start with a lowercase letter and then use lowercase letters, numbers, and underscores. Saved personal/team definitions allow up to 24 parameters and 40 steps; titles are capped at 120 characters, descriptions and step notes at 1,000, commands at 1,200, and supplied values at 4,096. Captures are limited to eight small scalar values per step and use bounded line, entity, or JSON Pointer selectors rather than arbitrary expressions.

**Configuration:** `conf/workflows.yaml` accepts legacy linear entries and explicit `version: 2` playbooks. User-created workflows store the same shape in the active personal or team scope. `workflow_active_execution_limit` and `workflow_execution_max_runtime_seconds` control the server-side execution bounds. See [Workflow Playbooks](docs/workflows.md) for the complete YAML, parameter, transition, capture, terminal, and recovery reference.

**Learn more:** [Workflow Playbooks](docs/workflows.md) covers authoring, parameters, transitions, captures, terminal use, persistence, recovery, and team behavior.

---

## Scheduled Runs

**Purpose:** recurring commands that keep running on a cadence after the browser tab is closed.

**Behavior:**

- The **Schedules** modal opens from the desktop rail or mobile menu and lists schedules for the active personal or team scope.
- Each schedule stores one command, an optional label, an enabled/paused state, an IANA timezone chosen from a dropdown, and either an hourly/daily/weekly preset or a five-field cron expression.
- The editor previews the next three fire times before saving. Preview timing is computed by the server and displayed in the selected schedule timezone, so the browser uses the same cron rules as the worker.
- Saved schedules can be edited, paused, resumed, deleted, refreshed, or fired immediately from the modal. Manual fires use the same audit path as worker-fired runs.
- The modal asks before closing, refreshing, opening a fired run, or switching schedules when the current form has unsaved changes.
- Fired runs appear in normal History with a `scheduled` badge. Clicking that badge, or the Schedule row in Run Details, reopens the schedule that created the run. Active scheduled runs stay in Status Monitor on page load and only attach to the terminal when you choose **Attach**.
- Run Details includes **Schedule this command**, which opens the Schedules modal with the completed run's command already filled in.
- The schedule detail view shows recent fire audit rows. Fired rows can open the resulting Run Details modal, and rows with an older completed fire on the current page can compare against that previous fire.
- If the owning session token is revoked, the worker disables personal schedules owned by that token and the browser shows them as paused instead of deleting them. When a team is archived, team-owned schedules pause in place instead of moving into a member's personal scope. Reactivating the team keeps those schedules paused until someone resumes them.

**Limits:** schedules require a durable session token. Anonymous sessions cannot create schedules because there is no durable owner for the worker to enforce after the browser closes. Cron support is strict five-field POSIX cron, and custom cron expressions cannot run more often than every five minutes. Workflow scheduling, blackout calendars, and per-target schedules are out of scope.

**Configuration:** scheduler settings live under `scheduler` in `config.yaml`, including `max_per_session`, `default_timezone`, `tick_seconds`, `max_catchup_window_seconds`, `missed_fire_policy`, and the SQLite `lock_path`. See [CONFIGURATION.md](CONFIGURATION.md) and [docs/schedules.md](docs/schedules.md).

**Learn more:** [Scheduled Runs](docs/schedules.md) covers cadence, timezones, worker behavior, audits, API/CLI use, and notifications.

---

## Watchers

**Purpose:** recurring change checks that compare each new run against a captured baseline run.

**Behavior:**

- The **Watchers** modal opens from the desktop rail, mobile menu, or Run Details and follows the active personal or team scope.
- Run Details and the History drawer action menu include **Create watcher from this baseline**, which opens the modal with the completed run already selected as the baseline in the same scope as that run.
- New watchers can use **First run** mode, which captures the first successful watcher fire as the baseline without needing an existing run id.
- The modal includes a Project selector, so a watcher and its future external runs stay together on that Project's Monitoring tab even if another Project is active when a check finishes. Unassigned watchers don't inherit the active Project. `darklab watch create --project PROJECT_ID` sets the same link for CLI-created watchers, and `darklab watch set-project` can add, change, or clear it later.
- The Baseline run field includes a short helper card for operators who prefer to paste a run id manually in **Existing run** mode.
- Each watcher owns a schedule, reruns the watched command on that cadence, and compares each completed watcher run against the current baseline.
- Watcher textual diffs ignore progress/status-line/PTY chrome and optional line patterns, and include entity-set deltas in the saved summary, so noisy redraws do not look like real changes and newly observed hosts, URLs, hashes, or CVEs are easier to spot.
- Watcher rows show whether the latest check is `ok`, `pending baseline`, `changed`, `firing`, `paused`, or `error`.
- The detail pane shows the last diff summary, recent fire audit rows with expandable diff details, links back to the runs created by watcher fires, and a direct Compare action for baseline-vs-fire review.
- Empty checks still appear in the fire audit as `diff_kind='none'`, so it's clear the watcher is still running even when nothing changed.
- Operators can pause, resume, manually fire, delete, or accept the latest run as the new baseline from the modal. Accepting a baseline asks for confirmation because it discards the previous comparison point.
- The modal asks before closing, refreshing, opening a watcher run, or switching watchers when the current form has unsaved changes.
- Team-owned watchers pause when their team is archived. Reactivating the team restores access, but archive-paused watchers stay paused until someone resumes them.

**Limits:** watchers require a durable `tok_` session token. Anonymous sessions cannot create watchers because the scheduler needs a stable owner. First-run watchers require a command because there is no completed run to inherit from yet. Watchers monitor one baseline command at a time, use the same five-minute minimum custom cron interval as schedules, and keep bounded diff summaries rather than unlimited raw diff payloads.

**Learn more:** [Watchers](docs/watchers.md) covers baselines, schedules, diff behavior, projects, API/CLI use, worker recovery, and notifications.

---

## Permalinks

**Purpose:** stable, shareable URLs for individual runs and full-tab snapshots, persisted through the configured database and subject to `permalink_retention_days`.

**Behavior:**

- **Tab snapshot** (`/share/<id>`) — **share snapshot** on any tab captures the current output and, when a full saved artifact exists, shares that full output as a snapshot. The resulting URL opens a styled HTML page with ANSI color rendering, a `save ▾` dropdown (txt, html, pdf), a **copy** button, a **view json** option, and a link back to the shell. Honors the browser's saved line-number and timestamp preferences on load. Uses the Web Share API where supported; otherwise copies the URL to the clipboard. Recommended sharing path.
- **Single run** (`/history/<run_id>`) — the permalink button in the history drawer links to an individual run. Serves the full saved artifact when persistence is enabled; otherwise the capped preview stored in the configured database. Team-owned run permalinks still open as shareable bearer links; team-private labels, notes, findings, and Atlas counts only appear when the viewer also sends a valid active team scope. Honors saved line-number and timestamp preferences on load.
- Both permalink types persist across container restarts through the configured database and any file-backed artifacts under `./data`.

**Limits:** retained for `permalink_retention_days` only; the `./data` directory is the only writable path in an otherwise read-only container (created automatically on first run).

**Configuration:** `permalink_retention_days` in `config.yaml` (default 365).

---

## Share Redaction

**Purpose:** optional masking of common secrets and infrastructure details (bearer tokens, private-key blocks, emails, IPs, and hostnames) on snapshot permalinks, with a persistent raw-vs-redacted default controlled by the Options modal.

**Behavior:**

- When creating a share snapshot, the shell can prompt whether to share raw or redacted output.
- A built-in redaction baseline masks common secrets and infrastructure details. It recognizes PEM and PGP private keys even when a command prints the block across several lines, and operators can append custom regex rules on top.
- App-native `intel` response bodies are raw-only for sharing: snapshot payloads replace those lines with `Intel data omitted from share` even when the user chooses raw sharing.
- Once a raw/redacted choice is saved as the persistent default in the [Options modal](#options-modal), subsequent share actions skip the prompt and reuse that choice — whether sharing is triggered from the prompt flow or directly from the Options modal.
- Redaction applies only to the snapshot payload; the stored run history is never modified.

**Limits:** local text exports from a tab are not redacted. Local HTML/PDF exports follow the same raw-only intel omission rule as share pages, but ordinary regex redaction is scoped exclusively to the share-permalink flow.

**Configuration:** baseline rules are built in; custom regex rules extend them. The raw-vs-redacted default is stored in the Options modal.

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
- The **☰** menu in the top-right header opens a bottom-sheet with two grouped sections: a **session** group (search, clear, line numbers toggle, timestamps picker) that affects the current terminal in place, and an **overlays** group that keeps Options first, then follows the desktop tool order for workflows, scope, Atlas, Quick Lookup, Projects, History, Files, Schedules, Watchers, Findings, Status, Commands, FAQ, Theme, and diag. Scope, Projects, Workflows, History, Atlas, Files, Schedules, Watchers, and Theme show compact hints when there is useful context to show. The sheet closes through the backdrop, Escape, or the shared grab/drag contract rather than a visible `X` button. `clear` wipes the active tab's output while preserving its run state; `line numbers` is a single on/off row; `timestamps` expands inline into a three-mode picker (off / elapsed / clock). The History panel's search, filters, and bulk controls stay behind a dedicated **history tools** toggle to preserve result space.

**Limits:** the diag entry appears only for clients whose IP matches `diagnostics_allowed_cidrs`. The mobile layout activates on touch-sized viewports — desktop browsers at narrow widths keep the desktop chrome.

**Configuration:** no mobile-specific config keys beyond `diagnostics_allowed_cidrs`; layout activates automatically on touch viewports.

---

## Built-In Commands

**Purpose:** native shell helpers that provide session introspection, guidance, and guarded responses without dispatching to external binaries.

**Behavior:**

- The shell ships several categories of built-ins, each rendered as terminal-native output rather than modal UI.
- Built-ins run entirely inside the app layer, so they remain available even when the corresponding external tool does not exist in the container.

**Utility commands**

- `help`, `commands`, `history`, `last`, `limits`, `retention`, `status`, `runs`, `jobs`, `stats`, `config`, `theme`, `which`, `type`, `wordlist`, `faq`, `banner`, `fortune`, `shortcuts`, `clear`, `exit` / `quit`, `version`, and `whoami` are available in every session.
- `status` prints a compact session summary: masked active session ID, session type, run count, snapshot count, starred-command count, whether saved Options exist for the session, session-variable count, active-run count, compact session file usage when Files are enabled, and the current instance-level save/retention limits.
- `runs` prints app-native active-run metadata for the current personal or team scope, including CPU percent derived from cumulative CPU seconds over run elapsed time, RSS-memory snapshot, and a hint that the desktop `STATUS` HUD pill opens real-time monitoring; `jobs` is a compatibility alias for the same terminal output. `runs -v` also prints full run IDs, started timestamps, cumulative CPU time, and active-run metadata source, while `runs --json` prints the active-run snapshot in JSON for debugging or automation. On desktop, the `STATUS`, `LAST EXIT`, and `TABS` HUD pills open the Status Monitor modal, and `Option+M` / `Alt+M` toggles the same view. The monitor is also available from the desktop rail and mobile menu, stays useful when idle with system/resource/session cards and visual history widgets, lists active commands as divided rows, exposes Attach/Kill actions for visible active runs, and shows best-effort CPU and RSS memory telemetry as circular meters/sparklines with memory fill normalized against 1 GB when backend process stats are available.
- `stats` prints session activity totals and external-tool command-root breakdowns: runs, snapshots, starred commands, active runs, success rate, average duration, and the top non-built-in command roots by run count.
- `project` manages case folders from the terminal: list/create/use/rename/current/clear/archive/unarchive/delete, link or unlink runs, link the last eligible run, and list/add/quick-add/remove project targets.
- `schedule` manages saved recurring commands, while `watch` turns a completed baseline run into a recurring change-detection monitor.
- `cd [folder]`, `pwd`, `file list [-l] [folder]`, `file show <file>`, `file diff <file1> <file2>`, `file add [file]`, `file add-dir <folder>`, `file edit <file>`, `file download <file>`, `file copy <source> <destination>`, `file move <source> <destination>`, `file touch <file>`, and confirmed `file delete [-r|-f|-rf] <file-or-folder>` / `file rm [-r|-f|-rf] <file-or-folder>`, plus the convenience aliases `ls [-l] [folder]`, `cat <file>`, `mkdir <folder>`, `cp <source> <destination>`, `mv <source> <destination>`, `touch <file>`, and confirmed `rm [-r|-f|-rf] <file-or-folder>`, expose keyboard-first access to the active personal or team Files workspace when workspace storage is enabled. `cd` is tab-local and treats the active workspace root as `/`; relative file commands resolve from that tab's current workspace folder. `file add` opens a blank file editor, `file add <file>` opens the same editor with the file name prefilled, `file add-dir` / `mkdir` creates a folder, `file download <file>` starts a browser download, `file copy` / `cp` copies one file without replacing an existing destination, `file move` / `mv` move or rename a file or folder, and `file touch` / `touch` creates an empty file or updates its modified time without truncating it. `file list` / `ls` list the current folder non-recursively in short form by default; `file list -l` / `ls -l` show the long listing with type, size, and modified columns.
- `diff <source1> <source2>` compares two workspace files, two completed runs written as `run:<run-id>`, or a file and run together, such as `diff file:expected.txt run:<run-id>`. Bare file names resolve from the current tab's Files folder. `diff --last` compares the last two completed runs from that tab without requiring Files to be enabled. Comparisons use the classic `<` / `>` layout by default, with `-q` / `--brief`, `-u` / `--unified`, and `-y` / `--side-by-side` available for familiar alternate output. Each file source can contain up to 5,000 lines and 500,000 UTF-8 bytes; larger files return an explicit error instead of a partial comparison.
- `urlscope <domain> <source-file> <destination-file>` normalizes and deduplicates HTTP(S) URLs from one Files entry, then writes at most 256 URLs whose host is the exact approved domain or one of its subdomains. It rejects credential-bearing URLs, fragments, malformed domains, and suffix lookalikes before the destination is used by an active web check.
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

---

## Headless API and CLI

**Purpose:** run commands and read saved data from scripts, CI jobs, or a local terminal without driving the browser shell.

**Behavior:**

- `/api/v1` authenticates with existing `tok_...` session tokens and rejects anonymous browser UUID sessions.
- API-started runs use the same command validation, registry rewrites, runtime checks, brokered stream, history persistence, Atlas capture, and project capture behavior as browser-started runs.
- Scripts can start non-interactive runs, wait for final run status, stream broker events as SSE or NDJSON, cancel active personal/team-scope runs, read history/ranged output/artifacts, search saved output with line context, inspect Atlas entities and findings, resolve an exact saved hostname, IP address, or URL without paging through Atlas, explicitly look up one exact package version in OSV, download run artifacts by stable artifact id, inspect project data and assessment cycles, manage Project HTTP profiles, manage scheduled commands and outbound notification channels, read notification delivery audits, and link or unlink completed external runs from active projects.
- API streams start with a schema row and then send typed output rows with backward-compatible `type` and `text` fields; see [docs/api.md](docs/api.md#streaming) for the stream shape.
- Saved schedules fire through the same brokered run path as manual runs and keep the personal or team scope they were created in. History rows and Run Details mark scheduled runs with their schedule id, and revoked tokens, archived teams, or overlapping prior runs leave clear fire-audit rows instead of failing silently.
- History responses include the same batched artifact, finding, Atlas entity, and Atlas finding counts shown in History and Run Details.
- Project assessment routes let API clients create and review cycles, page and filter target-specific checks, record reasoned manual exclusions, attach compatible saved evidence, preview or start a finding's saved verification action, and complete, archive, preview, or delete a cycle through the same Project and team-permission boundaries as the browser.
- The bundled `darklab` CLI wraps the API with `whoami`, `run`, `active`, `tail`, `cancel`, `history`, `grep`, `show`, `output`, `artifacts`, `atlas`, `projects`, `project`, `project-findings`, `project-runs`, `project-entities`, `project-packages`, `assessment`, `team`, `schedule`, `notify`, `completion`, and `download` commands. `darklab assessment ...` lists and inspects Project cycles, filters their checks, records or clears reasoned manual decisions, previews a saved finding-verification action, and starts it only after an explicit `--confirm`. `darklab run --wait` waits for final status for shell scripts, `darklab active` lists current jobs for the token, `darklab run --link-project NAME` resolves friendly project names before linking completed external runs, `darklab history --type` filters run history by external commands or built-ins, `darklab grep <pattern>` searches saved output across runs, `darklab atlas ...` reads Atlas summary, source runs, entities, and findings, `darklab team ...` creates teams, manages members and invites, joins scopes, and saves the active CLI team, `darklab schedule ...` manages saved recurring commands, `darklab notify ...` manages notification channels without accepting plaintext secrets on the command line, `darklab completion bash|zsh|fish` prints static shell completion, and `darklab completion install --shell auto` installs it into the current user's shell-completion directory. Live tailing fails clearly if a stream closes before the run reaches an exit, killed, or error event, and Ctrl+C while following output detaches without cancelling the server-side run.
- CLI configuration uses flags first, then `DARKLAB_API_URL`, `DARKLAB_TOKEN`, `DARKLAB_TEAM`, and `DARKLAB_TIMEOUT`, then the TOML file at `~/.config/darklab/config.toml`. CLI writes keep that file at `0600` because it can store a session token.

**Limits:** API v1 is intentionally non-interactive. Outside the assessment-cycle contract and completed-run project links, it does not expose general Project mutation routes. It also does not expose Interactive PTY start/input/resize routes, workflow execution, API-only token scopes, or workspace ZIP downloads.

**Configuration:** no server-side API-specific settings. CLI users can set `DARKLAB_API_URL`, `DARKLAB_TOKEN`, `DARKLAB_TEAM`, `DARKLAB_TIMEOUT`, or `~/.config/darklab/config.toml`; see [docs/api.md](docs/api.md).

**Learn more:** [Headless API and CLI](docs/api.md) covers authentication, commands, streaming, pagination, errors, and the checked-in OpenAPI contract.

---

## Outbound Notifications

**Purpose:** send queued app events to destinations outside the browser so long-running work can report back even when the tab is not in front of you.

**Behavior:**

- Durable `tok_` sessions can manage personal outbound channels from the Options **Notifications** tab, the terminal `notify` built-in, `/api/v1/notification-channels`, or `darklab notify`. When a browser or API request is in an active team scope, owners and admins can manage team-owned channels, while other members can read the team's delivery audit history. Secret-valued channel creation stays in Options, the API, or the CLI's prompt/secret-file flow instead of accepting secrets in terminal command text.
- Supported destinations are generic JSON webhooks, Slack incoming webhooks, Discord incoming webhooks, Telegram Bot API chats, Pushover, and SMTP email.
- Channel secrets are write-only. Webhook URLs, bot tokens, Pushover tokens, and related secret values are stored through the encrypted vault; list responses only say whether each required secret is configured.
- SMTP email uses operator-owned transport settings from `notifications.smtp.*`, while each email channel chooses its recipients and optional reply-to address.
- External non-PTY run finalization queues a `run_complete` notification with the configured `app_name`, run id, command root, exit code, token hint, and summary counts. Built-in commands and PTY sessions do not send `run_complete` by default.
- The trigger list also includes `pty_session_ended`, `scheduled_run_failed`, `watcher_changed`, `watcher_error`, `watcher_recovered`, and `test`; a channel sends only when a matching app source queues that trigger.
- Test sends use the same queue and delivery path as real notifications, so a successful test verifies both channel config and delivery plumbing. Muted channels skip normal deliveries but can still receive an explicit test send for troubleshooting.
- Delivery events keep the personal or team scope that created them, are claimed by the notification worker, retried with backoff when failures are retryable, and moved to dead-letter state when attempts or retry age are exhausted. Sent delivery audit rows are pruned after the configured retention window.
- Webhook-style channels reject non-public destinations by default, with an operator allowlist for trusted internal receivers.
- Delivery audit rows are available from each channel's **Deliveries** control in the Options **Notifications** tab, through `/api/v1/notification-events`, the terminal `notify events` built-in, and `darklab notify events`; the terminal built-in and CLI can also update, mute, unmute, test, and delete channels.
- Channel create, update, delete, mute/unmute, and manual test actions are also written to the operator audit log as config-change rows. Those rows describe the action and channel metadata, but they do not store webhook URLs, bot tokens, Pushover keys, SMTP passwords, or replacement secret values.

**Limits:** anonymous browser sessions cannot create outbound channels. Email channels require SMTP settings before they can be saved or tested. Channel payloads are intentionally compact and should still be sent only to destinations you trust.

**Configuration:** `notifications.*` controls do-not-disturb, per-channel delivery rate, HTTP/test timeouts, private webhook destination allowlisting, SMTP transport, sent-event retention, and retry behavior. `app_name` controls outbound titles/messages. See [CONFIGURATION.md](CONFIGURATION.md) and [docs/notifications.md](docs/notifications.md).

**Learn more:** [Outbound Notifications](docs/notifications.md) covers channel setup, payloads, delivery retries, privacy, and troubleshooting.

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

---

## Encrypted Secrets

**Purpose:** store personal or team API keys for approved tools without putting those values in terminal commands, transcripts, history, snapshots, or logs.

**Behavior:**

- The Options modal includes a **Secrets** section where users can add, replace, and delete secret values for the active personal or team scope. The add flow suggests the API key names declared by the command and provider registries first, with a custom option for local overlays.
- **Provider Status** in the Secrets section shows which intel providers are usable in the active scope, which ones still need an API key, the app-facing secret names, supported lookup types or CLI uses, and broad account/free-tier notes. Clicking a secret name opens the add-secret prompt with that key selected.
- Team secrets are separate from personal secrets. Personal keys are not inherited into a team, and only team owners and admins can add, replace, delete, or rotate team secrets; other members can consume matching team secrets through approved commands without reading values.
- `secret set NAME` opens the same browser-owned value prompt from the terminal. The command line contains only the name; the value is entered in the modal and is not echoed.
- `secret list` shows stored names and their consumer environment bindings. It never prints values.
- `secret unset NAME` deletes one stored secret in the active scope. `secret show-consumers` and its `providers` alias show intel provider readiness with the same usable versus needs-configuration summary as the Provider Status modal. The same output shows the version, origin, age, and live-refresh setting for the shared FIRST EPSS and CISA KEV data, plus the configured mode and saved-data status for NVD and OSV advisory sources.
- Command registry entries can declare `requires_secrets`. When a matching command runs, the backend decrypts the needed value in memory and passes it to the subprocess environment. Missing required secrets stop the run before launch with a clear message; optional secrets let registered commands keep running normally when no value is saved.
- Secret declarations can also map a user-friendly secret name to a vendor-required environment name. For example, VirusTotal CLI runs accept either `VT_API_KEY` or the native `VTCLI_APIKEY` stored secret, and the app passes the value to `vt` as `VTCLI_APIKEY`.

**WPScan:** `wpscan` runs without an API token and uses `WPSCAN_API_TOKEN` for API-backed vulnerability data when that value is saved through Options → Secrets or `secret set WPSCAN_API_TOKEN`. The app passes the token only to the WPScan process, and inline `--api-token` values are blocked so they can't enter command history, transcripts, snapshots, or logs.

**Limits:** stored values are replace-only. The app does not reveal or copy a saved secret back out of the vault.

**Configuration:** operators provide the vault master key with `SECRETS_MASTER_KEY` or let the app create an app-owned key file under the data directory. Tool bindings live in `app/conf/commands.yaml` through `requires_secrets`.

---

## External Intel

**Purpose:** query configured passive-intel providers without making users paste API keys into the terminal.

**Behavior:**

- `intel ip <ip>` queries Shodan, Shodan InternetDB, Censys, GreyNoise, AlienVault OTX, AbuseIPDB, IPinfo, Team Cymru, URLhaus, ThreatFox, FOFA, ZoomEye, and RouteViews, then shows ports, CVEs, banner summaries, InternetDB hostnames/CPEs/tags, Censys services and ownership context, GreyNoise classification, OTX pulse context, AbuseIPDB report confidence, IPinfo geolocation and ASN details, malware-distribution context, IOC matches, FOFA/ZoomEye search matches, and IP-to-ASN/BGP ownership context when those providers return data.
- `intel domain <domain>` queries VirusTotal, AlienVault OTX, the live TLS certificate on port 443, crt.sh, URLhaus, ThreatFox, urlscan.io, paid-only SecurityTrails, FOFA, and ZoomEye when configured, then shows reputation, analysis stats, recent URLs, WHOIS summary data, OTX pulse context, served certificate expiry/issuer/names, certificate-transparency counts and sightings when crt.sh responds, URLhaus host context, ThreatFox IOC matches, urlscan.io search hits, SecurityTrails DNS/WHOIS/subdomain pivots, and bounded FOFA/ZoomEye search matches.
- `intel url <url>` queries URLhaus, ThreatFox, urlscan.io, FOFA, and ZoomEye, then shows malware-distribution status, IOC context, matching urlscan.io search results, and bounded provider search matches without submitting a new scan.
- `intel hash <md5|sha1|sha256>` autodetects the hash type by length, queries VirusTotal, AlienVault OTX, URLhaus, and ThreatFox, and checks SHA1 hashes against HIBP Pwned Passwords by sending only the first five SHA1 characters.
- `intel cve <CVE-ID>` shows stored FIRST EPSS probability and percentile, CISA KEV status, and any accepted NVD advisory status, CVSS vector/score, and CWE ids alongside the live NVD and Vulners result. Stored signals include their source version, publication/fetch time, expiry, origin, and freshness; a CISA BOD 22-01 date is labeled as federal directive context rather than the Project's remediation deadline. EPSS is presented as an exploitation estimate, not as a complete risk score. Saved finding responses carry stable observation references plus one remediation reference per CVE and keep confidence, exposure, and asset context separate from that public-risk order.
- Each provider pane reports whether it came from cache, was rate-limited, hit quota backoff, or is missing a required encrypted secret.
- Private, loopback, and other non-public IPs are blocked by default because vendor intel on those addresses is not useful. `--include-private` allows an explicit override.
- The external `shodan`, `vt`, `greynoise`, `ipinfo`, `urlscan-cli`, and `chaos` CLI wrappers remain available for users who want provider-native output. `shodan domain` and `shodan host` output also feeds structured findings for DNS records, host IPs, hostnames, open ports, and HTTP titles, with weak mail policy rows and private DNS addresses flagged as warnings. `ipinfo <ip>` highlights IP, hostname, and organization rows while keeping geography and timezone rows as context.

**Limits:** Shodan, Censys, VirusTotal, GreyNoise, AlienVault OTX, AbuseIPDB, URLhaus, ThreatFox, Vulners, urlscan.io, SecurityTrails, FOFA, and ZoomEye require user-provided provider keys. FOFA also requires the account email as `FOFA_EMAIL`, accepts `FOFA_KEY`, `FOFA_API_KEY`, `FOFA_APIKEY`, or `FOFA_TOKEN` for the API key, and needs an F-point balance for search calls. ZoomEye uses `ZOOMEYE_API_KEY` with the regional `api.zoomeye.ai` API and needs available resource credits. SecurityTrails currently requires a paid account. Shodan InternetDB, Team Cymru, live TLS certificate checks, crt.sh, HIBP Pwned Passwords, NVD, and RouteViews work without saved keys but still use the app's per-session rate limiting and cache layer to avoid accidental bursts. Release-pinned EPSS and KEV snapshots work offline and never make a request from a finding, report, Atlas profile, or Project view. Operators can load OSV package applicability from a local full-record dataset or allow exact package lookups through the API. Each lookup discloses its one PURL and version to OSV, never a full SBOM or discovered inventory, and requires finding-triage permission in team scope. No read surface starts acquisition. Stored NVD data describes a CVE; it does not prove that a scanned product or version is affected. Provider terms and quotas are still enforced by each vendor.

**Version inference:** when a successful Nmap service scan writes validated XML with `-oX`, an exact versioned CPE can be checked against stored NVD applicability rules after the run completes. A defensible match creates an inferred finding with its source run and advisory context; it remains visibly different from an active probe that confirmed vulnerable behavior. Failed scans and ordinary XML files aren't correlated. Stored OSV rules can also match one exact PURL and version against an explicit affected version or supported SEMVER range without contacting OSV or changing a finding. Exact versioned PURLs and CPEs from bounded CycloneDX JSON components use the same read-only candidate boundaries: PURLs use OSV and CPEs use NVD. Results retain the component, import batch, format, parser, observation time, affected range, and advisory context. An inventory component alone isn't a vulnerability, PURL and CPE evidence stays distinct, and malformed or conflicting versions fail closed. Maintained HTTPx assessment actions request structured, version-enriched CPE output. Exact technology/CPE agreements stay with the run as reviewable evidence and can be checked locally against stored NVD rules to prepare a provenance-complete inference candidate. A separate guarded write accepts that candidate only for the successful owner-scoped HTTPx run and its exact linked URL, then rechecks the parser family and stored advisory rule before saving the inference. Unversioned, conflicting, fuzzy, cross-tool, or ambiguous evidence remains output only. Viewing or correlating HTTPx and package evidence doesn't contact a provider or create inferred findings automatically.

**Configuration:** users store `SHODAN_API_KEY`, `CENSYS_PAT`, optional `CENSYS_ORGANIZATION_ID`, `GREYNOISE_API_KEY`, `VT_API_KEY`, `OTX_API_KEY`, `ABUSEIPDB_API_KEY`, optional `IPINFO_TOKEN`, `URLHAUS_AUTH_KEY`, `THREATFOX_AUTH_KEY`, `VULNERS_API_KEY`, `URLSCAN_API_KEY`, `SECURITYTRAILS_API_KEY`, `FOFA_KEY` or a FOFA alias, `FOFA_EMAIL`, `ZOOMEYE_API_KEY`, `PDCP_API_KEY`, `GITHUB_TOKEN`, or `GITLAB_TOKEN` through Options → Secrets or `secret set NAME`. The Options picker suggests those known keys from the provider registry and command registry, while the terminal command still accepts explicit names such as the VirusTotal CLI's native `VTCLI_APIKEY`. Operators tune cache TTLs and rate-limit buckets in `conf/config.yaml`. The `cve_risk` section controls the bundled EPSS/KEV baseline, stale-data label, bounded scheduler refresh, EPSS event thresholds, optional local or explicit-refresh NVD advisory storage, and the separate local or explicit OSV package-data mode. All outbound or shared-advisory modes are off until the operator enables them.

---

## Session Files

**Purpose:** optional app-managed personal/team file access for commands that need small input or output files, without turning the app into a general-purpose shell filesystem.

**Behavior:**

- Session file storage is disabled by default. Compose operators can enable it and choose temporary or persistent storage with the adjacent `WORKSPACE_*` settings in `.env`.
- Each browser/session token gets a hashed session directory under the configured workspace root.
- Session directories use sticky, setgid, group-scoped permissions and app-created files are group-readable but not world-readable; commands run as the unprivileged `scanner` user with a restrictive umask so tool-created workspace outputs follow the same boundary.
- Production Files storage uses a host bind mount by default. The current image uses `appuser` `995:995` and `scanner` `994:994`; bind-mount roots should be pre-owned by `995:995`, with the workspace root set to `0730`, owner directories set to `3730`, app-created files set to `0640`, and command-created writable outputs allowed as `0660`.
- Workspace access updates the hashed session directory activity timestamp. Periodic cleanup removes inactive `sess_*` directories after `workspace_inactivity_ttl_hours`; it does not delete individual files solely because their file timestamps are old.
- File names are relative and display-friendly; absolute paths, traversal, backslashes, hidden names, symlinks, and paths outside the session root are rejected. Text reads and downloads also use final-component no-follow opens where supported, so the app keeps the same session-root boundary even if a path is swapped after validation.
- The Files panel is a compact personal or team file browser with breadcrumbs, an Up control, a `..` parent row outside the Files root, folders-first rows, file-type icons, linked-record context, friendly timestamps, and separate file-count and storage indicators. Search filters the current folder by name or visible context, sorting supports name, modified time, and size, and each row keeps secondary actions in a keyboard-friendly overflow menu. Clicking anywhere in a row outside that menu selects its file or opens its folder; the file or folder name remains the keyboard-accessible primary control. On desktop, selecting a file shows its quick preview, metadata, linked runs and projects, labels, notes, and common actions in a side inspector without leaving the folder. On narrow screens the same browser becomes a compact two-column list and opens files in the focused full viewer.
- The panel can create, view, edit, move, download, and delete text files owned by the active scope; JSON and JSONL/NDJSON files are pretty-printed in the read-only viewer, and open file previews can be refreshed manually or opt into auto-refresh while following appended output at the bottom. Files and folders can also be dragged onto folder rows or the `..` parent row after confirmation.
- Team Files live in a separate `team_*` workspace directory. The Files panel reloads when you switch personal/team scope and keeps the current folder separate per scope. Team viewers can list, read, preview, and download team files; owners, admins, and operators can also create, edit, move, and delete files. Archived teams stay readable in Files but cannot change files until reactivated.
- The add/edit file modal includes labels and a private note for the workspace file. File rows surface existing labels/notes from the generic entity metadata store, and move/delete operations update or clear that metadata with the file so project views and package exports do not keep stale paths. Team-file labels and notes are shared with team members and stay separate from personal file metadata.
- File writes and appends, copy/touch operations, folder creation, and file/folder moves write best-effort audit rows with the path, destination path, file count, and byte size where applicable. Deletes keep their fail-closed audit row. Audit details do not store file contents.
- The `file` built-in provides terminal access to the same file model through `cd [folder]`, `pwd`, `file list [-l] [folder]`, `file show <file>`, `file add [file]`, `file add-dir <folder>`, `file edit <file>`, `file download <file>`, `file copy <source> <destination>`, `file move <source> <destination>`, `file touch <file>`, and confirmed `file delete [-r|-f|-rf] <file-or-folder>` / `file rm [-r|-f|-rf] <file-or-folder>`; `file add` opens a blank file editor unless a filename is provided, `file add-dir` creates a folder, `file download <file>` starts the same browser download path as the Files panel, `file copy` copies one file without replacing an existing destination, `file move` moves or renames files and folders, and `file touch` creates an empty file or refreshes its modified time. `cd` is tracked per tab, treats the active personal/team workspace root as `/`, and causes relative commands such as `ls`, `cat`, `cp`, `mv`, `touch`, `rm`, and `file show` to resolve from the tab's current workspace folder. Team viewers can read through the terminal built-ins, but write commands are blocked before they open browser confirmations.
- The `ls [-l] [folder]`, `cat <file>`, `mkdir <folder>`, `cp <source> <destination>`, `mv <source> <destination>`, `touch <file>`, `rm [-r|-f|-rf] <file-or-folder>`, `grep <pattern> <file>`, `head [-n N] <file>`, `tail [-n N] <file>`, `wc -l <file>`, `sort [-r|-n|-u] <file>`, and `uniq [-c] <file>` aliases map to app-native workspace operations only; they do not expose arbitrary host/container filesystem access.
- `file list`, `ls`, `file move`, `mv`, and confirmed `file delete` support simple `*` patterns such as `file ls darklab-*`, `mv darklab-* darklab/`, and `file delete scan-*`. A `*` matches inside one path segment and does not cross `/`; moving multiple matches requires the destination to already be a folder.
- `file delete <file>`, `file rm <file>`, and `rm <file>` first verify the target exists, then require the same transcript-owned yes/no confirmation model as other destructive terminal-native actions. Folder deletion requires `-r` or `-rf` before the confirmation is shown, including when a glob matches one or more folders.
- Loaded workspace file and folder names feed autocomplete for `file show`, `file edit`, `file download`, `file copy`, `file move`, `file touch`, `file delete`, `file rm`, `cat`, `ls`, `cp`, `mv`, `touch`, `rm`, and `tee` destinations.
- Workspace-only external-tool examples and flags in `commands.yaml` are hidden from autocomplete unless Files are enabled, so operators can add discoverable file workflows without exposing unusable suggestions on instances that keep Files disabled.
- Selected command flags declared in `commands.yaml` can consume or write active personal/team Files. At execution time, user-facing names such as `targets.txt` are validated and rewritten to the active workspace path passed to the subprocess; output then maps absolute hashed paths back to user-facing Files paths.
- `wget` downloads default to the active Files folder when Files are enabled. Operators can still choose a subfolder with `-P downloads` or `--directory-prefix=downloads`.
- Raw shell navigation and redirection remain blocked. The supported `command > file`, `command >> file`, and final `| tee file` forms write only through the Files boundary; other file access must go through the Files panel, workspace routes, the `file` built-in, or explicitly declared command flags.

**Configuration:** set `WORKSPACE_ENABLED`, `WORKSPACE_BACKEND`, and `WORKSPACE_ROOT` in `.env`. Direct source runs export the same variables; see [CONFIGURATION.md](CONFIGURATION.md) for storage recipes.

---

## Project Workspaces

**Purpose:** lightweight case folders that keep related shell work, findings, files, targets, and export packages together while leaving the terminal as the primary workflow.

**Behavior:**

- Projects group top-level source records by link rather than copy. Current project links support completed runs and Atlas entities; Targets are the curated `domain`, `url`, and `ip` set used for scope tracking, while the Entities tab shows every linked Atlas entity type. Domain targets accept DNS names, URL targets accept full HTTP(S) URLs, and IP targets accept single IPv4 or IPv6 addresses. Legacy `host` target inputs from older API/import callers are still accepted as compatibility aliases and saved as `domain` or `ip`; the target editor and new validation messages only present `domain`, `url`, and `ip`. Run-owned artifacts surface through linked runs, and findings surface through linked runs or linked Atlas entities. Project list rows show run, finding, artifact, and package counts before you open a project, and the Findings tab label can show prefetched new/high counts when that project has triage work waiting. When team scope is active, team-owned Projects and team-owned run links are visible to other members of that team. Snapshots and manually selected workspace files stay in their history/files surfaces and are intentionally not project-linked.
- The desktop rail and mobile menu open the Projects modal for creating, selecting, clearing, archiving, deleting, and reviewing projects. The active-project HUD shows current project context and opens a compact switcher for quickly choosing or clearing the active project without leaving the terminal. Project changes broadcast across same-session tabs.
- Active projects can automatically link completed external command runs and, when enabled, the Atlas entities those runs produce. Project Entities rules can also preview and save recurring matches for owned domains, IP ranges, URLs, CVEs, and hashes, then apply those matches manually or to new runs as they finish. A rule set to apply automatically watches every new run in the same personal or team scope and adds matches to the project that owns the rule, even when that project is not the active project for the command. If a rule matches entities for the active project, those entities are added as confirmed rule-created links instead of waiting in the normal confirm/dismiss queue. Broad patterns and regex rules are rejected instead of quietly linking too much. Manual run-link actions confirm first and can also add the Atlas entities found in those runs, with the entity count shown before anything is saved. When automatic entity linking reaches the project link limit, the run stream reports the skipped entity count. Removing a run from a project follows the shared [Cleanup Confirmations](#cleanup-confirmations) rules for optional same-run Atlas entity-link cleanup. Built-in runs stay in history without project links or project-derived findings, and **Link last run** backfills the most recent eligible run when needed. In the terminal, `project link run last` resolves within the current tab so parallel tabs don't steal each other's latest run.
- Project details expose project labels, project notes stored through `entity_notes` with `entity_type='project'`, editable Atlas-backed targets, linked Atlas entities, linked runs, findings, artifacts, and packages. Team-owned projects share linked-run artifacts and evidence packages with team members, while package and artifact rows keep creator/member context when it is available. Artifact previews, downloads, and package archives read files from the source run's personal or team Files workspace, so a teammate can open artifacts from a team run without switching into the run creator's personal workspace. Suppressed Atlas entities and findings stay hidden from default project views until they're restored in Atlas. The Findings tab pages through large result sets, shows each finding's source command, and keeps its tab count tied to the full server-side total, including findings attached through linked runs or linked Atlas entities. Assessors can use **Create finding** to record an issue against a confirmed Project target when no parser or scanner produced it; the same editor can start from an Assessment check, a Project-scoped Atlas domain/IP/URL profile, or selected lines in Run Details with that saved context already attached. Assessor-authored rows keep **Edit finding**, labels/notes, and triage as separate actions in Project Findings, Atlas, and Run Details. The editor checks required fields, identifiers, CVSS, and safe HTTP(S) references before saving. Likely duplicates require a second confirmation, stale edits are rejected, and changing the title, severity, or details doesn't change the finding's stable observation or remediation identity. API clients use the same saved-finding contract. Saved findings retain the same summary, impact, reproduction steps, confidence, CVE/CWE ids, CVSS details, safe reference links, and stable observation/remediation references in Projects, Run Details, Atlas, focused entity profiles, and API clients, with explicit empty values for older records. A Project finding can also keep typed supporting references to runs, exact transcript lines, full output, workspace artifacts, screenshots, Atlas entities, Project targets, assessment checks, and retest runs. Each reference must belong to the same owner and Project, removed sources stay labeled unavailable, and evidence packages preserve the references with the selected finding. The triage view shows the originating assessment check and frozen profile version, warns when the live profile changed or original evidence disappeared, and classifies up to 25 completed Project runs against the saved tool, target, completion, and output rules. **Run verification** recomputes the originating check's bounded command from its frozen action and current confirmed target, shows the exact policy, scope, limits, and credential use for confirmation, then links the run to the Project and opens the normal terminal. Archived or changed context, stale confirmation, workflows, unsupported commands, and intrusive or destructive policy fail closed. A completed launched run is retained as retest evidence automatically. The newest compatible retest can suggest **Needs retest** when the same exact issue appears again, or **Verified** after a successful check that explicitly supports a clean result. The suggestion explains why and can fill the status field, but the assessor still has to review the evidence and save the final decision. A non-comparable run can be retained after a warning, compared with the original, and removed later without changing the saved status. Final `verified`, `needs_retest`, and `not_applicable` decisions record when they were saved and who saved them without exposing a personal session token. Observation references keep inferred, imported, manual, and actively confirmed evidence separate; matching issues share a remediation reference, review state, and remediation guidance without merging different owners, affected subjects, or vulnerabilities. When different targets, CVEs, or rules still describe one fix, an assessor can use the shared triage editor to search for the other finding, preview the affected observations, and explicitly merge their remediation groups. The selected target group's review state and guidance become shared, while verification steps, status, notes, evidence, and validation method stay with each observation. CVE findings use the same server-side priority order in Projects and Atlas: CISA KEV entries first, then EPSS probability and percentile, stored NVD CVSS, and newer findings as the stable tie-breaker. Compact labels explain KEV, EPSS, CVSS, advisory status, and source freshness instead of hiding them behind a composite score. Command, severity, scope, run, target, review-state, verification-status, label, and note filters help narrow busy projects without loading every finding at once; verification status uses `not_started`, `ready_to_verify`, `verified`, `needs_retest`, or `not_applicable`. The list view keeps visible-page bulk review, the inline board groups the current filtered findings into review lanes, and the larger board modal gives the same project a roomier drag/drop triage surface. Finding rows open the matching Atlas finding, **See in run** jumps back to the exact raw output line, and rows/cards can open the shared triage editor for remediation and verification handoff work. Board cards show the saved verification/remediation badges after triage changes. Labels and notes remain editable for linked runs, findings, Atlas entities, run file artifacts, workspace files, and packages through the shared entity metadata editor.
- **Fix first** separately ranks the current cycle's findings by CISA KEV, EPSS, CVSS, and age without changing its coverage totals. Each remediation group appears once with the reasons for its placement, observation and evidence totals, strongest validation method, confidence, exposure, and last-seen context. Expanding a row keeps inferred, confirmed, imported, and manual observations distinct and can open any one in the shared triage editor. Risk filters and paging don't disturb the check worklist. Overview shows the active cycle's compact total and top issues, and its actions open that exact Assessment cycle and priority filter.
- The **Assessment** tab turns saved Project evidence into a practical coverage worklist. Start a Network or Web cycle from a maintained profile, switch between current and earlier cycles, review covered, awaiting-review, untested, excluded, and unavailable-evidence totals, and narrow checks by category or state. Target rows expand in place to show each check, its policy level, evidence count, manual-decision state, and missing-source warning. Each check can open **Create finding** with the confirmed target and assessment check already selected as evidence, or preview and start its saved recommended action. The action preview shows the exact command, target, policy, scope, limits, and credential use before confirmation; supported safe and standard commands are linked to the Project and open in the normal terminal, while stale, changed, unsupported, intrusive, and destructive plans stop safely. Large check sets page instead of loading at once. Completing a cycle also adds a **Finding changes** summary against the newest compatible earlier cycle. New, persistent, not-observed, regressed, and incomparable remediation groups stay separate, and each row can open the current or earlier finding evidence. Related observations count once. A clean cycle only produces **Not observed** when the same frozen check has available compatible evidence and explicitly supports a clean result; missing or changed evidence is labeled incomparable instead. A regression requires a previously human-verified issue to appear again. Operators can complete or archive cycles after a warning confirmation. An archived cycle can be deleted after a preview shows its saved check, evidence-link, and comparison counts; the source runs, findings, entities, and files remain. Desktop and mobile use the same saved cycle and permissions, and the tab remembers its selected cycle, filters, expanded targets, page, reading position, and return context for each Project. Mobile check actions use the shared action sheet, and view-only team members can review the work but can't change a cycle, create a finding, or start a run. Overview and Findings show the same compact remediation-group totals and open the exact cycle behind them.
- Structured DNSx runs keep bounded CNAME, address, response, provider, wildcard-filter, scope, time, and source-run context for dangling-record review. A saved CNAME isn't called a takeover finding, and an unchecked provider target stays labeled as unchecked until separate evidence supports a review decision.
- Web assessment cycles include a dedicated **Subdomain takeover confirmation** for one approved domain. The preview shows one request against the app's reviewed provider fingerprint, with redirects, saved credentials, callbacks, and resource claims disabled. A successful match becomes a high-severity finding only when the same Project has compatible saved DNS source and negative-target results from the preceding 24 hours. The finding links all three exact source lines; incomplete, conflicting, stale, or cross-scope evidence stays unconfirmed, and the check never claims the provider resource.
- The **Web Surface** tab gives desktop and mobile users a paged gallery of verified HTTPx screenshots linked to the Project. Each card keeps the saved URL, page title, response status, technologies, HTTP role, capture time, and source run together. It compares the visual hash with the nearest earlier capture from a different run only when the exact URL and HTTP role match, then labels the result changed, unchanged, no baseline, unavailable for comparison, or outside the bounded comparison window. This is evidence for review, not a vulnerability finding. Filters narrow captures by target, exact HTTP status, technology, role, visual hash, or comparison result, while grouping organizes the visible page by those same details. If a large collection reaches a bounded search or comparison window, the gallery says how many recent captures were checked instead of implying that older captures matched nothing. Available images can expand in place or open in a focused full view. Previous and next buttons, left and right arrow keys, and horizontal swipes move through the viewable captures on the current page, with clear position and boundary states. Closing the viewer returns focus to the card that opened it. URL actions open the matching Atlas profile, and source actions open Run Details. Changed, missing, unavailable, or conflicting files remain visible with a clear status instead of being dropped. Images load through the authenticated artifact route, and captured HTML is never rendered in the app.
- Project HTTP assessment profiles let the Assessment tab and API clients save role-specific web-testing context once: exact Project hosts and paths, header names, request limits, token-capture rules, and references to app-managed Secrets, login workflows, or client-certificate Files. Credential values aren't copied into the profile or returned by the API. Desktop and mobile show the role, scope, request bounds, enabled state, and whether referenced Secrets are available. Members with Secret-management permission can create, edit, disable, or delete a profile and use **Manage Secrets** to add or replace values in Options. Team viewers see redacted counts instead of reference names. Supported Curl, HTTPx, Katana, Nuclei, and Dalfox actions ask which available role to use before the final preview; disabled or incomplete profiles stay visible for repair but can't be selected. Dalfox actions perform bounded parameter discovery only: active XSS payloads, remote wordlists, redirects, and callback modes stay disabled. The app rechecks scope and access at launch, keeps the visible command redacted, and removes short-lived credential material afterward. Saving or viewing a profile doesn't start a scan.
- The Overview tab gives each project a target-first attack-surface summary. It rolls up target count, app-captured open ports and services, cached-provider open ports and services, app/provider port drift, app-captured scan coverage, coverage gaps, finding review progress, verification progress, Assessment finding changes, recent run/triage/artifact tempo, deliverables status, targets with critical or high findings, certificate status, provider highlights, recent project activity, and recent-change state, then lets you jump into the existing workspace tabs with the selected target and high-signal filters already applied. App-captured ports and services are shown first when available, with long port lists summarized so the Overview stays readable. Provider-backed ports, services, certificates, and highlights are labeled as cached data, with stale/no-intel states and the latest checked time shown on each target row when available. URL targets use their stored Atlas host link when available, so host-level ports and services show up without reparsing the URL each time. The target worklist keeps findings and severity visible, skips repeated empty-state rows, and includes an optional filter for hiding unscanned targets that have no findings.
- App-captured scan coverage comes from supported scanner families: nmap, masscan, rustscan, naabu, and `nc` port checks. Curl connection lines can add positive port evidence when the transcript reports a connection, but they are not counted as scan-coverage observations. Quiet scans are counted as "scanned with no app-captured ports" only when darklab_shell can associate the run with a concrete project target.
- The finding progress strip shows New → Reviewed → Important/follow-up and Not started → Ready → Verified → Needs retest, with false-positive, suppressed, and not-applicable counts called out separately so the totals stay honest.
- The tempo strip shows the last linked run, runs in the last seven days, the latest triage update, the latest captured run artifact, and a short activity trail from the project's own audit history.
- The coverage-gap worklist calls out targets with no app-captured scan, targets with findings awaiting verification, and targets that still need review or follow-up. Each row opens the existing Entities or Findings tab with the matching filters applied.
- The deliverables strip shows the latest package save/build, latest report save/export, and whether the report is fresh against the newest finding or triage activity.
- Overview target rows label cached provider ports separately from app-captured scan evidence. When scanner output includes service or version metadata, the row shows it with the app-captured port. When a supported scan touched a target but surfaced no app-captured ports, the row says that plainly without claiming the host has no open ports. URL targets use the app-captured evidence from their linked host entity when that host is known, and port-drift actions open the Project Entities Ports tab filtered to that host with a clearable host chip.
- The Entities tab mirrors Atlas entity types for project-linked rows with compact type tabs, shows cached intel provider context, opens entities in Atlas for deeper intel review or refresh, links more session Atlas entities from a picker, bulk-unlinks visible entities from the project, exports project-scoped entities as CSV or JSONL, and labels rule-created rows with the auto-promote rule that added them. The Rules panel is available on desktop and mobile; view-only users can preview readable rules but cannot create, change, apply, or delete them.
- Finding review supports status updates, visible-page bulk review/delete, source-run restore with line highlighting, target attribution, orphan-source filtering, filtering, and sorting. Artifact rows show availability/checksum state and offer scoped preview/download actions for still-available workspace files.
- Evidence packages are draft project manifests built from selected project material.
  - The wizard starts from operator-configured presets, including the shipped Evidence, Summary, Full Archive, and Redacted choices.
  - Packages record name/description, package labels/notes, transcript/finding/artifact/target selections, redaction mode, artifact inclusion, private-note inclusion, size estimates, artifact warnings, safe project-link provenance, and import hints for later review.
  - Full Archive packages select transcript HTML for every selected run by default, and the Include step has compact select-all/clear menus for transcript HTML, findings, and targets.
  - The preview shows a best-guess ZIP size, expanded content size before compression, a concise provenance summary, and optional full-text fallback files for capped transcripts.
  - Existing package rows support polled downloads, visible archive-preparation status, re-package, manifest preview with the same provenance summary above the raw JSON, delete, and metadata edit actions.
  - Job-backed package downloads include a safe audit correlation in the manifest and README so the bundle can be tied back to the build event without exposing session-derived details.
  - Packages containing CVE findings snapshot the exact EPSS/KEV/NVD rows, source versions, dates, checksums, attribution, and non-endorsement notice used at build time, so a later refresh doesn't rewrite what the package reported.
  - Packages with selected findings from a compared Assessment cycle preserve the matching current and earlier finding/evidence references, remediation-level state, and explicit comparison reasons. Unselected remediation groups stay out of that package.
- The Report tab turns selected project material into a narrative engagement report.
  - Operators can edit engagement metadata, executive summary, methodology, cover notes, and date ranges; toggle and reorder shipped sections; choose included runs, targets, findings, and artifacts; save drafts; preview rendered HTML; export the markdown/HTML archive; or use browser Print/PDF.
  - Included-evidence controls page through large projects instead of loading everything into one long list. All/None choices apply to the full filtered set, small hand-picked selections stay saved even when you page or filter away from them, compact summaries show saved selected or excluded ids, and oversized bulk choices stay represented as filters rather than thousands of stored ids.
  - Findings in report output show readable target references with target type/value when export settings allow it, source run, and relationship source when the project has that context.
  - CVE findings show the KEV/EPSS/CVSS reasons behind their placement. Reports and report manifests pin the public source versions, dates, checksums, attribution, and non-endorsement notice used for that export.
  - Reports with selected findings from a compared Assessment cycle include the same current and earlier finding/evidence references and explicit comparison reasons in readable output and archive provenance.
  - The editor shows available source provenance before the included-item list and falls back cleanly when source details are not present in the current project view.
  - Report archives include a compact manifest with generated-by details, redaction/export choices, section choices, selected entity ids/counts, large-selection filters, bounded exclusions, and resolved build-time counts.
  - Job-backed report exports include a safe audit correlation in the manifest, limited to the build event type, job id, and correlation id.
  - Operator-configured report templates appear as a selector when more than one template is available.
  - View-only team members can preview and download the default readable report, but they can't save drafts or switch to private-note or unredacted variants.
- The Activity tab gives project users a scoped change trail without opening the operator-wide diagnostics view.
  - Personal project owners and team members who can view the project can see safe rows for project-linked activity, report/package builds, finding review changes, imports, and related evidence actions.
  - Filters for event type, actor, target type, target id, and date range keep busy projects readable, and pagination loads only the current page.
  - Rows show time, actor, action, target, summary, and collapsed safe details. Team-viewer access stays read-only, and older rows may disappear when audit retention is configured.
  - Metadata edit sheets show a compact Recent activity panel for the item you're editing. The panel loads a small page, then links into the filtered Activity tab when you need the broader trail.
- The Monitoring tab gives project users a project-scoped view of scheduled watchers that belong to the project, with a **New monitor** action that opens the watcher form already linked to the current project.
  - Public risk changes appear in a separate **CVE Risk Changes** section when an open Project finding becomes KEV-listed, crosses the configured EPSS activation threshold, or its stored NVD advisory is disputed, rejected, withdrawn, reinstated, or materially downgraded. The first accepted NVD record stays silent, later rows show the earlier and current values, and one acknowledgement applies to the owner-scoped event everywhere it's projected. Each linked Project can choose its own digest delivery setting.
  - Digest notification controls live on the Monitoring tab too. Project owners and team members who can manage automation or notifications can turn digests on, choose hourly/daily/weekly cadence, pick explicit notification channels, and decide whether quiet no-change digests should be sent. View-only team members can still see the current settings, last sent/check timestamps, next due time, and delivery issue text when it exists. Digest delivery attempts also appear in each channel's delivery history with the project name and digest window.
  - Status cards split monitors into active, changed, failed, quiet, and paused groups without double-counting quiet checks.
  - Filters for status, severity, tool/classifier, group, cadence, changed window, acknowledgement state, and linked target keep busy projects readable without reloading the tab.
  - Monitor cards are grouped by derived categories such as External perimeter/ports, DNS/subdomains, Certificates, Web checks, Findings, and Custom commands. Each card shows the watcher label, command, cadence, current state, severity, noise-policy flags, repeated-change alert threshold, signal-class alert filter, and latest fire so teams can spot changed or stalled checks quickly.
  - Ignored-line patterns apply to textual fallback diffs. Alert signal classes use the notification groups Findings, Entities, and Ports; certificate/TLS alerts count under Ports even though the dashboard shows Certificates as its own group.
  - Fire rows include compact top signals, such as new open ports, changed TLS fields, new hosts, findings, or textual fallback counts, while the deeper evidence stays in Run Details and Compare.
  - The timeline keeps completed watcher fires visible even when old runs have been deleted. Available runs open in Run Details, and Compare is enabled only when both the current and baseline runs still exist.
  - Operators can pause or resume a monitor, queue a run, open its settings, confirm and accept a new baseline, or mark changed and failed timeline fires as acknowledged, expected, needs action, or resolved. Notes stay with the fire, while the audit trail records safe metadata about the triage change.
- Package downloads produce a capped archive with `manifest.json`, `README.md`, static `index.html`, selected run transcript pages, finding/target JSON and Markdown exports, selected metadata/notes exports, optional raw artifacts for raw packages, and redacted text/JSON artifact derivatives for redacted packages.
  - Finding JSON and Markdown include remediation, verification steps, verification status, and target references for selected findings.
  - Verification notes follow the package's private-notes option, and redacted packages scrub remediation and verification text while omitting target-reference values before rendering JSON or Markdown.
  - The downloaded manifest records included transcript line indexes, signals, entities, source run ids, bounded source categories for selected project links, and import-hint warnings when redaction, excluded private notes, or unavailable artifacts limit what the archive can recreate later.
- Package transcript HTML and companion text files stay faithful to the captured output. The manifest's derived transcript line index skips classified transcript noise so downstream review tools start from the cleaner view without losing the raw transcript pages.
- Project run comparison uses the same canonical `/history/compare` flow as the History drawer. It can compare two linked runs directly or compare a selected run against the newest linked run with a chosen run label; the dedicated Run Comparison section covers the shared transcript, finding, and artifact comparison behavior.
- History project filtering returns linked external runs for the selected project. Run-subtype filters can further split all runs, built-in runs, and external runs while snapshots remain available through the normal snapshot filter.

**Auto-promote rules:** the Project Entities **Rules** panel lets a project keep known-good Atlas entities linked without repeating the same picker work.

- Each rule chooses an entity kind, a match mode, and a pattern. Supported kinds are **Any**, domain, IP, port, URL, CVE, and hash. Supported match modes are exact, contains, wildcard, domain suffix, and CIDR, with only the modes that make sense for the selected kind shown in the editor. Regex rules are unavailable and are rejected by the server.
- Domain suffix rules match the apex domain and its subdomains, so `darklab.sh` matches both `darklab.sh` and `graph.darklab.sh`. CIDR rules support IPv4 and IPv6 addresses. Contains and wildcard rules reject very short or overly broad patterns so one loose rule doesn't link most of Atlas by accident.
- Optional filters can narrow a rule to entities first seen after the rule was created, entities from specific source runs, entities seen in runs with selected command roots, or suppressed entities. Suppressed entities are skipped unless the rule explicitly includes them.
- Preview shows the matches and must be refreshed before saving an enabled rule whenever match-affecting fields change. **Apply now** links the current matches once. **Apply automatically to new runs** watches new runs in the same personal or team scope and links matching entities into the project that owns the rule, even when another project is active for the command.
- If a rule matches an entity already waiting in the active project's confirm/dismiss queue, the rule confirms it as an auto-promoted project link. Existing links stay in place when a rule is disabled, edited, or deleted; rule changes apply to later previews, manual applies, and automatic run applies.
- Project rule quotas, preview caps, manual apply caps, run-finalization caps, and per-session preview rate limits keep broad rules bounded. Capped previews and applies tell the UI when more matches may exist beyond the returned window.

**Limits:** projects are personal- or team-scoped and do not copy source history. Deleting a project removes its project metadata, targets, packages, and links, but not the underlying run history or workspace files. Entity notes are intentionally one note per supported entity rather than comment threads.

**Configuration:** project, metadata, auto-promote, and evidence-package limits are configured in `conf/config.yaml`; see [CONFIGURATION.md](CONFIGURATION.md).

---

## Evidence Packages

**Purpose:** turn selected project evidence into a downloadable review bundle while preserving raw/redacted export choices and private metadata boundaries.

**Behavior:**

- Package creation starts from the Projects modal's Packages tab. The wizard records name, description, labels, notes, redaction mode, artifact inclusion, private-note inclusion, and the selected runs, findings, artifacts, and targets. Team-owned project packages are visible to members in that team scope and keep creator context when the creator is still known.
- Package rows show preset/redaction/size summaries, compact source/provenance chips when the manifest has source context, and offer polled downloads with visible archive-preparation status, re-package, manifest preview, metadata edit, and delete actions.
- Downloaded archives include `manifest.json`, `README.md`, static `index.html`, selected run transcript pages, full-text companions for capped transcripts, selected finding/target JSON and Markdown exports, selected label/private-note exports, note Markdown exports, optional raw artifacts for raw packages, and redacted text/JSON artifact derivatives for redacted packages. The manifest records the package's redaction mode, selected entity ids/counts, privacy choices, bounded build and project-link provenance, safe audit correlation for job-backed downloads, finding target references, and import hints for recreating package metadata, labels, notes, source links, target relationships, and finding review state from the archive.
- Run transcript pages and full-text companions keep the captured output intact. The manifest's transcript index omits classified progress/status/boilerplate noise so package consumers can focus on useful lines first.
- Re-package starts from the previous manifest selection so an operator can rebuild the same bundle after project data changes.

**Limits:** package manifests are draft records, and the archive is built at download time from still-available project data and workspace artifacts. Redacted packages never include raw artifact files; binary or unknown artifact types are skipped unless they're exported in a raw package.

**Configuration:** evidence-package limits are configured in `conf/config.yaml`; see [CONFIGURATION.md](CONFIGURATION.md).

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
- Operators can set `RESTRICTED_COMMAND_INPUT_CIDRS` to reject literal IP/CIDR targets in command slots declared with target-like `value_type` metadata (`domain`, `host`, `ip`, `cidr`, `target`, or `url`). The check catches literal IPs, overlapping CIDR arguments, URL hosts, host:port values, and app-readable workspace input files passed through declared read flags. Built-in workspace path slots such as `mv` and `file move` stay out of this target check.
- Command-specific runtime adaptations are also declared in the registry. `inject_flags` handles safe default flags such as `nmap -sT`, `nuclei -ud /tmp/nuclei-templates`, `naabu -scan-type c`, and `mtr --report-wide`; managed workspace directories and environment wrappers handle Amass' active personal/team database path.
- The external command registry and app-owned helper catalog feed terminal discovery and hide entries whose `feature_required` is disabled:
  - `commands` lists built-in and allowed external roots, followed by an app-native pipe-helpers section (`grep`, `head`, `tail`, `wc -l`, `jq`, `sort`, `uniq`) labeled as app-managed filters rather than arbitrary shell pipelines.
  - `commands info <root> [subcommand]` describes either a built-in helper or external command, including its examples, flags, arguments, subcommands, and any authored knowledge guidance; `commands info <root> --json` prints the same entry as one deterministic JSON line for copy or debugging.
  - `commands search <term>` searches built-in helpers and external commands across root, category, description, example values, and knowledge notes/gotchas, ranks root-prefix hits first, and groups results by category.
- Each command entry can carry an optional `knowledge` block — `notes`, `gotchas`, `safe_defaults`, `common_flags`, and an `artifact_behavior` scalar — surfaced in `commands info`, `commands search`, and the registry modal. The fields are descriptive guidance only and never affect allow/deny policy; they ship seeded for high-traffic tools such as `nmap`, `nuclei`, `httpx`, `ffuf`, and `gobuster`.

**Limits:** prefix matching is deliberately coarse — operators must be explicit with deny entries to block flag combinations on otherwise-allowed tools. Deny matching only applies once the tool prefix matches (e.g., `!nmap -sU` only affects `nmap` commands). Restricted command inputs only inspect literal values in metadata-known target slots; domain names are not DNS-resolved.

**Configuration:** command policy uses `conf/commands.yaml`; restricted target inputs use `RESTRICTED_COMMAND_INPUT_CIDRS` in `.env`. See [CONFIGURATION.md](CONFIGURATION.md) and [docs/external-command-integrations.md](docs/external-command-integrations.md).

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
- `knowledge` — optional descriptive guidance (`notes`, `gotchas`, `safe_defaults`, `common_flags`, `artifact_behavior`) shown in discovery surfaces; never policy-bearing. See [CONFIGURATION.md](CONFIGURATION.md#command-knowledge).

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
- The browser opens a tab-scoped xterm.js modal, preloads the terminal assets, starts the PTY through `/pty/runs`, and sends keyboard input and terminal resizes through bounded POST routes. When a team scope is active, the live PTY run is visible to team members and command-capable roles can attach, input, resize, or kill it while viewers remain read-only.
- If the same PTY run is opened from another browser client, the previous live owner closes cleanly and adds an `[interactive PTY moved to another tab]` notice instead of leaving two live terminals fighting for the same run.
- Completed PTY runs append a saved static transcript and exit status back into the parent shell tab, then persist through the normal history/search/finding path. Registry transcript modes decide whether a tool saves the final visible frame or scrollback-style findings.
- Reload recovery and Status Monitor Attach use bounded ANSI snapshots and show when a restored snapshot was already stale. Redis-backed deployments can serve output streams, input/resize control, and reattach snapshots from any worker without sticky routing; single-worker local development can run without Redis when configured.
- `/diag` includes PTY operator metrics for active terminals, completed duration, input volume, dropped input, and queued controls.

**Limits:** disabled by default, desktop-only, and restricted to commands that explicitly declare PTY behavior in the command registry. PTY runs have a configured max runtime and per-session concurrency cap. Multi-worker deployments require Redis unless `run_broker_require_redis` is intentionally relaxed for local development.

**Configuration:** Compose deployments enable the feature with `INTERACTIVE_PTY_ENABLED=true`; optional fine-tuning remains under the `interactive_pty_*` YAML settings. Each approved command also has an app-owned `interactive` registry block; see [CONFIGURATION.md](CONFIGURATION.md#enable-interactive-pty).

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
- Workspace file hints stay separate from installed SecLists suggestions. A tool flag such as `gobuster dir -w` can suggest both active Files entries and installed web-content wordlists without treating every file path as a SecLists entry.
- Any allowlisted tool can still reference files under the SecLists path directly when the command policy permits that path.
- The list is installed at container build time; no runtime fetch is required.

**Limits:** wordlists are read-only inside the container. Normal command output and autocomplete use the curated catalog instead of exposing every file under SecLists; use `wordlist --all` for the full scanned tree. The corpus is not updated between builds — rebuild the image to pick up a new SecLists release.

**Configuration:** `app/conf/wordlists.yaml` defines curated category globs under the fixed install path. External command value slots opt into installed-wordlist autocomplete through `value_type: wordlist` and `wordlist_category` in `app/conf/commands.yaml`.

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

---

## Onboarding Tour

**Purpose:** an optional guided introduction that helps new users learn the main shell, history, comparison, workflow, project, team, files, PTY, options, and FAQ flows without leaving the app.

**Behavior:**

- The welcome flow can point users at the tour, and users can start it again with the `tour` built-in command or the visual tour link in FAQ.
- The terminal `tour` command types each chapter into the transcript, pauses after each chapter, and lets the user press any key to continue or `q` to stop.
- Terminal tour `Try this` chips open the sample command in a new tab so the tour tab stays readable while the user experiments.
- The desktop visual tour uses a carousel with app-shaped previews. `Try this` actions close the carousel and open the matching app surface when one exists, such as History, Workflows, Projects, Teams, Files, Options, or FAQ.
- Feature-gated chapters are hidden when their feature is unavailable. Interactive Tools stays hidden on mobile because interactive PTY sessions are desktop-only.

**Configuration:** `app/conf/tour.yaml` stores chapter text, sample commands, and visual illustration keys. See [CONFIGURATION.md](CONFIGURATION.md#onboarding-tour) for the file format.

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

---

## Options Modal

**Purpose:** session-owned controls for presentation, run behavior, session identity, and provider secrets that follow the active session identity while still caching locally for fast reloads.

**Behavior:**

- Click **≡ options** in the desktop rail (or the **☰** menu on mobile) to open the modal.
- The modal has four tabs: **Preferences** for display, identity, run, and compare controls, **Secrets** for provider readiness plus stored API keys, **Teams** for shared team scopes, members, invites, and recovery codes, and **Notifications** for outbound delivery channels. The last tab you used is remembered with the rest of your session preferences.
- Run `config`, `config list`, `config get <option>`, or `config set <option> <value>` in the terminal to inspect or update the same user options without opening the modal. Option names are suggested after `config get` or `config set`, and option values are suggested after a selected option.
- Timestamp and line-number settings mirror the tabbar quick toggles — changing either surface updates the other immediately.
- The HUD clock setting chooses whether the desktop `CLOCK` pill renders in `UTC` or browser-local time. This control is intentionally hidden from the mobile Options sheet because the HUD itself is desktop-only.
- The welcome-intro setting controls whether the welcome animation plays on first tab: full animated sequence, instant settle, or no welcome tab at all.
- The share-snapshot redaction setting selects the default redaction choice (prompt / redacted / raw) so the share prompt is skipped once a preference is saved.
- The project capture settings control whether completed external command runs are added to the active project and whether generated Atlas entities are added with those auto-linked runs.
- Run notifications fire a browser desktop notification each time a run exits or is killed; the title shows only the command root (`$ curl`) and the body shows exit code and elapsed time. Enabling triggers the native permission prompt; if notifications are blocked, the toggle reverts with a toast. This toggle is intentionally hidden from the mobile Options sheet because the feature is treated as desktop-oriented chrome behavior.
- The **Notifications** tab lists outbound channels for the active personal or team scope. You can add, edit, mute, delete, and send a test notification for supported destinations without exposing write-only secret values after save; team-scope channel changes are limited to owners and admins.
- The **Teams** tab lists teams attached to the active session token, creates new teams, redeems invite or recovery codes, edits member display names and roles, revokes invites, rotates recovery codes, archives/reactivates teams, and can switch the active scope. `/api/v1/teams` exposes the full team-management contract for API clients, `darklab team ...` covers script-friendly team creation, joins, member updates, invites, recovery codes, and saved CLI scope, and the terminal `team` built-in covers common in-shell actions such as create, list, join, invite, leave, and recovery-code rotation. The desktop HUD opens a compact scope menu, while the mobile menu opens the scope selector sheet. Team read routes have their own token-keyed rate limit so normal Options-tab and scope-switch refreshes don't crowd out invite or recovery-code writes. Team scope shares team-owned runs, History, Run Details, Projects, project targets, finding review, labels, notes, cached Atlas intel, shared workflows, schedules, watchers, notification delivery history, completed-run AI assists, and explicit team secrets while personal work remains separate. Archived teams stay visible for review and reactivation, but they cannot be used for active team work, invites, membership edits, invite revocation, or recovery-code rotation until reactivated. Reactivating an archived team restores access, but schedules and watchers paused by archival stay paused until someone resumes them. Team roles keep viewers read-only while operators, admins, and owners handle the write actions their roles allow; desktop and mobile menus hide or disable write-only controls before they can open confirmations, and team payloads include capability names so browser and API clients can show the same allowed actions the server enforces.
- Preferences are stored server-side per session and mirrored into browser cookies/local storage for reload continuity, so a named session token restores the same option set across browsers and devices.
- The **Secrets** tab includes Provider Status, Add secret, Refresh, and the stored secret list so a long list of saved keys does not push the preference controls out of view.

**Limits:** anonymous UUID sessions remain browser-local by design, so only named session tokens carry preferences, team memberships, and outbound notification channels across devices. Blocked browser notification permission cannot be re-prompted by the toggle — it must be re-enabled in browser settings. Email channels require operator SMTP settings before they can be saved or tested.

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
| **Command Outcome Summaries** | on / off | Show deterministic app-native outcome summaries below supported completed command output |

**Terminal option keys:** `line-numbers`, `timestamps`, `welcome`, `share-redaction`, `project-auto-link-runs`, `project-auto-link-run-entities`, `run-notifications`, `command-outcome-summaries`, `hud-clock`, `compare-view`, `compare-context`, `prompt-username`.

---

## Persistence & Retention

**Purpose:** durable storage layout for run history, preview metadata, full-output artifacts, and tab snapshots, with time-based retention pruning at startup and during the scheduler worker's daily cleanup pass.

**Behavior:**

- SQLite stores run history, preview metadata, full-output artifact metadata, and tab snapshots in `./data/history.db`.
- Postgres stores database rows in Postgres while still using `./data` for full-output artifacts, body-store files, and the app-owned secret key file.
- Persisted full-output artifacts are written as compressed files under hash-sharded `./data/run-output/` paths.
- Optional body-store thresholds can move large run search text, tab snapshot bodies, and Atlas intel payloads into compressed files under `./data/body-store/` while the app keeps reading them normally.
- The `./data` directory is created automatically on first run and persists filesystem-backed artifacts across container restarts and recreations.
- Runs, run-output artifact metadata, artifact files, and snapshots older than `permalink_retention_days` are pruned together at startup and by the scheduler worker's daily retention pass.

**Limits:** `./data` is the only writable path in an otherwise read-only container. Setting `permalink_retention_days: 0` disables pruning entirely (unlimited retention). On SQLite deployments, never write to `./data/history.db` from the host — host/container SQLite version mismatches can corrupt the FTS5 btree.

**Configuration:** `permalink_retention_days` in `config.yaml` (default 365; `0` disables pruning). `runs_search_text_inline_max_bytes`, `snapshots_inline_max_bytes`, and `intel_payload_inline_max_bytes` default to `0`, which keeps those bodies inline.

**Useful direct checks:**

Prefer `/diag` for storage and row-count checks because it works on both backends. The commands below are SQLite-only maintenance examples for stopped containers or controlled local copies:

```bash
# Count rows
sqlite3 data/history.db "SELECT COUNT(*) FROM runs; SELECT COUNT(*) FROM run_output_artifacts; SELECT COUNT(*) FROM snapshots;"

# Inspect page-level storage when dbstat is available
sqlite3 data/history.db "SELECT name, SUM(pgsize) AS bytes FROM dbstat GROUP BY name ORDER BY bytes DESC LIMIT 10;"
```

---

## Production Installation

**Purpose:** install and operate a released darklab_shell stack without cloning or building the source repository.

**Behavior:**

- The release installer creates a small deployment directory from one deterministic archive with production Compose, an environment file, local configuration starters, persistent data folders, managed-file checksums, the project license, third-party notices, a release manifest, a lifecycle command, and a verifier that confirms the pulled image matches both recorded registry digests before startup.
- The app is licensed under GNU AGPLv3. Its rail footer, mobile menu footer, and FAQ link to the exact source tag and README for each official release. Modified network versions must point that link at their corresponding source and prominently offer it to every remote user at no charge through a standard or customary copying method; the full license controls. Project-owned source files keep short SPDX notices when they're copied separately, while generated and third-party files retain their own notices.
- Production pulls one exact `docker.io/darklabsh/darklab-shell` release tag on Linux AMD64 and ARM64. Docker chooses the native child image automatically, the same complete image index is available from the GitLab Container Registry, and the installed manifest records both matching index digests plus the reviewed child digest and measured sizes for each platform. The installed verifier rejects unsupported hosts and any image selection that has drifted from that platform map.
- Each protected release publishes a CycloneDX SBOM and full Grype vulnerability report for every included platform, SLSA provenance, and an evidence index tied to the source commit, pipeline, shared registry index digest, child digests, and shared Python base resolution. Fixed Critical findings block publication. GitLab's keyless Sigstore identity signs both immutable index references, their child manifests, and `SHA256SUMS`. The Docker Hub overview publishes the expected issuer and certificate identity separately, and the public smoke path checks that description before it verifies, installs, and starts the release.
- The app publishes port 8888 on every host interface by default so remote operators can connect without first configuring a reverse proxy. Operators can narrow `HOST_BIND_ADDRESS` to loopback, restrict the port with a firewall, and review local settings, [raw-packet scanning](#raw-packet-scanning), optional Postgres, optional local AI, and reverse-proxy exposure before starting it.
- Shipped commands, workflows, themes, and other catalogs stay in the image. Matching operator files under `conf/` add to or override those defaults without hiding newer image content.
- Private host permissions stay intact: container startup validates and stages the complete `conf/` overlay tree into an app-owned runtime copy before the web and worker processes start.
- The installer verifies its exact release files and prepares the directory, but it doesn't pull or start containers until the operator runs the printed commands.
- `darklab-deploy` checks release-owned file drift, creates and verifies SQLite or Postgres backups through one-off release-image containers, restores managed backups, migrates SQLite to bundled Postgres with backup and row-count validation, verifies online upgrade archives against the publisher's signed checksum manifest, upgrades only to a newer exact release, and removes managed files without deleting operator state. When `compose.operator.yaml` exists beside the installed stack, every lifecycle Compose invocation uses it automatically and upgrade instructions include it. Fresh replacement installs can explicitly adopt a managed Postgres backup while retaining their new database credentials, and the destination must be empty before the transactional restore starts. Migration and adoption inspect bundled Postgres through its local container socket, safely synchronize an empty retained cluster's password, and refuse to overwrite a named volume containing user tables. The migration reads locked-down app data through Docker and keeps host-side files owned by the installation user. Offline archives remain an explicit operator-verified path.

**Limits:** The current production platform and compatibility status live in the canonical [Supported Runtimes](CONFIGURATION.md#supported-runtimes) table. The app has no user authentication boundary, so the default all-interface listener must be limited to trusted networks with a host or upstream firewall. Production reads a private snapshot of `conf/` at container start, so host-side overlay edits need `docker compose restart shell`. Tour chapters and the curated wordlist map are image-owned rather than operator overlays. Database migrations can be forward-only, so the lifecycle command refuses downgrades and takes a verified backup before upgrades and restores. Tags ending in `-rc.N` are validation candidates rather than official releases and may be removed after testing.

**Configuration:** see the [Quick Start](README.md#quick-start) and [Docker Compose Files](CONFIGURATION.md#docker-compose-files).

---

## Operator Backups

**Purpose:** scheduled, deployment-aware backups for self-hosted operators.

**Behavior:**

- `./darklab-deploy backup` runs the backup engine in a one-off release-image container with the installation's exact mounts and settings.
- SQLite installations get a consistent `history.db` snapshot through SQLite's backup API. Postgres installations get a custom-format `pg_dump` archive, with the bundled database started temporarily when a backup finds it stopped.
- The backup includes the selected database, durable app data, local configuration, `.env`, managed release metadata, and the complete managed workspace directory even when Files is currently disabled.
- Data and workspaces are read through the container mounts, so operators don't need to loosen app-owned host permissions or run the lifecycle command with `sudo`.
- Each backup writes a redacted manifest, checksums, restore notes, and either a `.tar.gz` archive or an unpacked directory when `--compress none` is used.
- Large files are checksummed without loading the whole file into memory, and collision-safe output names keep closely timed backups from replacing each other.
- Retention runs record their cutoff and candidate scan in the manifest, then report examined, removed, and failed counts after the new backup is safely published. Unexpected script failures include a traceback for unattended-job diagnosis.
- `./darklab-deploy restore` verifies checksums, takes a safety backup, stages local config and durable workspaces, preserves the installed image and target Postgres credentials, and uses one Postgres transaction before it commits host files. Successful restores return those files to the installation user, recreate the app when restored environment settings changed, keep any installed Compose override active, and wait for the app to become healthy; failures leave it stopped with the safety-backup recovery command.

**Limits:** backup archives contain sensitive material, including local settings and the app-owned secrets key file. Run backups during quiet periods when you need the strongest database-plus-filesystem consistency.

**Configuration:** see [CONFIGURATION.md → Operator Backups](CONFIGURATION.md#operator-backups) for lifecycle commands, retention, restore, and backend adoption.

---

## Session Tokens

**Purpose:** optional persistent named identity (`tok_<32 hex>`) so run history, snapshots, starred commands, session variables, workspace files, project workspace records and assessments, recent targets, user workflows, completed personal workflow executions, active-project context, and saved user options follow an operator across browsers and workstations without introducing a login layer.

**Behavior:**

- By default each browser gets an anonymous UUID stored in `localStorage` under `session_id`, plus a separate browser/client id used for active-run ownership. A session token replaces the session identity with a persistent `tok_<32 hex>` so run history, snapshots, starred commands, session variables, workspace files, project workspace records and assessments, recent targets, user workflows, completed personal workflow executions, active-project context, team memberships, theme choice, and other saved Options settings follow the operator across browsers and workstations without making every browser automatically own the same live run.
- Tokens are generated server-side as `tok_` + 32 lowercase hex characters (36 chars total, cryptographically random) and recorded in the `session_tokens` table.
- The active token is stored in `localStorage` under `session_token`; the original UUID is always preserved under `session_id` so `session-token clear` has a stable fallback.
- The browser sends the active identity as `X-Session-ID` on every request; possession of the token string is the only authorization check (matching the existing anonymous session model).
- Changing the token in one tab propagates to all open tabs via the `storage` event — recent chips, starred state, history drawer, session-scoped preferences, and the options-panel masked display all refresh without a reload.
- `session-token` subcommands are rendered client-side so token values are not sent through the normal `/runs` execution path. Successful commands are saved through the allowlisted `/run/client` history path with token-bearing arguments masked before they are stored or shown in recent-command views.
- Token generation, revocation, and migration are written to the audit log with masked labels and hashes only. The raw token value is never stored in audit details.

**Terminal commands:**

- `session-token` (no subcommand) — prints current status: active token in masked form or "anonymous session".
- `session-token generate` — requests a new token and offers to migrate the current session's runs, snapshots, starred commands, saved user options, session variables, user workflows, completed personal workflow executions, project workspace records and assessments, recent targets, active-project context, and workspace files when the current session has portable data. The token becomes active only after a successful migration; declining migration activates it as a fresh named session; migration failure leaves the old session active.
- `session-token set <token>` — adopts an existing token. UUIDs are always accepted; `tok_...` values must already exist on this server. The migration prompt is offered if the current session has history or workspace files; answering `no` skips migration and still applies the token, while `Ctrl+C` cancels the whole set flow.
- `session-token copy` — copies the active token to the clipboard without printing the raw token in the terminal.
- `session-token clear` — opens a terminal-owned yes/no confirmation, removes `session_token` from `localStorage` only after explicit confirmation, and reverts to the anonymous UUID session. `Ctrl+C` cancels the clear flow. Server-side session data remains and can be reclaimed with `session-token set`.
- `session-token rotate` — generates a new token, migrates all runs, snapshots, starred commands, session variables, user workflows, completed personal workflow executions, project workspace records and assessments, recent targets, active-project context, workspace files, and saved user options (when the destination has no saved preferences yet), then switches. The switch is **atomic** — migration failure aborts the rotation and keeps the old token active. Old token is retired on success.
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

If a session has run history, workspace files, project workspace records or assessments, user workflows, completed personal workflow executions, or recent targets, the terminal `generate` and `set` flows use transcript-owned yes/no migration prompts; `clear` and `revoke` use transcript-owned destructive confirmations. The Options panel uses the shared modal confirm primitive for its own set/clear actions. `list` and `revoke` remain terminal-only.

**Limits:** there is no user-facing authentication — possession of the token is sufficient access. `POST /session/migrate` requires the `from_session_id` body field to match the caller's `X-Session-ID` header (mismatch returns 403), so a migration call can only move the caller's own data. Migration and rotation return `409 active_workflow_execution` while the current identity has an active workflow execution; wait for it to finish or cancel it before retrying. Completed personal execution history moves to the destination token, while team-owned history stays with the team.

**Configuration:** no config keys — token issuance is always enabled. Token scope covers runs, snapshots, starred commands, session variables, user workflows, completed personal workflow executions, project workspace records and assessments, recent targets, active-project context, saved user options, and app-managed workspace files when Files are enabled.

---

## Team-Mode

**Purpose:** shared workspaces for trusted operators who want to run scans, review results, and manage follow-up work together without mixing personal history into the team view.

**Behavior:**

- Durable session-token users can create teams, join with invite or recovery codes, manage members, and switch between personal and team scope from Options → Teams, the desktop HUD scope menu, the mobile scope selector, `/api/v1`, the terminal `team` built-in, or the bundled `darklab team ...` CLI commands.
- Team scope is explicit. Personal scope shows only your own data, while team scope shows team-owned runs, History, Run Details, recent values, Files, Projects, Project targets, linked-run artifacts, evidence packages, deduplicated Atlas entities and findings, Atlas labels and notes, finding review state, cached intel, workflows, schedules, watchers, notification channels and delivery history, AI assists, package builds, explicit team secrets, and provider readiness.
- Team roles keep day-to-day collaboration simple: viewers can read shared team data, operators can run and triage, admins can manage most shared settings, and owners can manage the team itself. The server includes capability names in team responses, so browser and API clients can show actions that match what the server enforces. In view-only team scope, write, destructive, suppression, history metadata edit and delete, share snapshot, and finding-review controls are disabled before confirmation when possible, Projects select mode stays unavailable where selection only leads to write actions, Findings Board cards do not expose drag/drop triage, and stale denials explain that the current role cannot make the change.
- Teams always keep at least one active owner. The Teams tab locks the current owner's role selector while they are the only active owner; after another owner exists, owners can step down normally.
- Team owners and admins can open an Activity subtab in the selected team detail panel. It shows safe team-scoped audit rows for governance and shared-configuration activity, with filters, paging, collapsed details, and the same retention note used by project activity. The team overview also shows a compact Recent activity preview for that selected team.
- Team secrets are separate from personal secrets. Personal provider keys are not inherited by teams, and team secret values stay write-only after save.
- Archived teams stay visible for review and reactivation, but they cannot start new team-scoped work, accept invite/recovery redemption, edit members, rotate recovery codes, or dispatch stale schedules until reactivated. Schedules and watchers paused during archival stay paused until someone resumes them.
- Team-owned Projects, Atlas rows, schedules, watchers, notification channels, workflows, AI assists, packages, and artifacts keep personal data out of the team scope while letting members work from the same shared evidence.
- Live team runs and interactive PTY sessions can be watched by other team members with the right scope. Team-scoped kill and run-control actions use the same role checks as starting a command.
- Team-aware API and CLI calls use `X-Team-ID`, `DARKLAB_TEAM`, or the saved CLI team config. `darklab team switch` validates the team before saving, preserves unknown config keys and comments, and keeps token-bearing config files owner-readable only.

**Limits:** Team-Mode is for trusted operators on the same self-hosted instance. It is not SSO, billing, per-project ACLs, or a full multi-tenant product. Destructive Atlas cleanup/delete actions require a triage-capable team role and stay inside the active personal or team scope.

**Configuration:** no global config switch. Team-Mode requires durable session tokens because anonymous browser sessions cannot safely identify team members across devices.

---

## Raw-Packet Scanning

**Purpose:** let supported Linux Docker deployments use Nmap, Naabu, and Masscan modes that need packet sockets without running the container in privileged mode or launching scanner commands as root.

**Behavior:**

- The feature is off by default. After an operator enables it, each scanner activates only when its Linux capability, executable, and file-capability checks pass.
- Ready Nmap runs can use the normal SYN default plus explicit SYN, UDP, OS detection, traceroute, and raw host-discovery modes. An explicit `-sT` remains a connect scan.
- Ready Naabu runs can use SYN mode unless the command explicitly asks for connect mode.
- Masscan becomes available only when its raw-packet checks pass because it has no connect-mode fallback. Its help path remains available while scanning is inactive.
- Raw-only autocomplete and Command Registry choices appear only for a tool whose checks pass, so users aren't offered modes the deployment can't run.
- `/diag` shows configured, available, and active state for each scanner. Startup logs carry the same bounded readiness result, and an unavailable opt-in produces a warning with the failed prerequisite category.

**Limits:** Nmap and Naabu fall back to connect mode when the feature is disabled or unavailable; Masscan points users to RustScan or `nmap -sT`. User-supplied Nmap privileged mode, source/decoy/MAC spoofing, and link-layer `--send-eth` stay blocked. The feature doesn't enable Docker privileged mode, host networking, Macvlan/IPvlan, or root scanner processes.

Restricted-CIDR deployments add another boundary. Raw Nmap activates only when the protected firewall marker matches the effective CIDR list, then uses the IP path covered by the scanner-user OUTPUT rules. Packet-socket Naabu and Masscan stay inactive because their traffic doesn't cross that path; separate host or Docker bridge rules don't count as readiness proof. The app-port guard applies only to container-local destinations, so an authorized remote host using the same port remains scannable.

**Configuration:** set `RAW_PACKET_SCANNING_ENABLED=true` in `.env`. Direct source runs export the same variable. See [CONFIGURATION.md → Raw-packet scanning](CONFIGURATION.md#raw-packet-scanning) for readiness requirements, restricted-network behavior, diagnostics, and examples.

---

## Security and Process Isolation

**Purpose:** defence in depth against shell-injection, loopback callbacks, and worker impersonation, relying on allowlist validation plus OS-level user separation rather than browser trust.

**Behavior:**

- **Shell injection protection.** The app blocks metacharacters that enable command chaining or arbitrary redirection — `&&`, `||`, `;`, backticks, `$()`, `<`, and unsupported control operators. `|` is allowed only within the constrained pipe model described in [Built-In Pipe Support](#built-in-pipe-support), while `>` and `>>` are accepted only as final app-managed Files sinks. Direct filesystem references to `/data` and `/tmp` are blocked as command arguments (using a negative lookbehind so URLs containing those strings as path segments are still permitted). Loopback targets (`localhost`, `127.0.0.1`, `0.0.0.0`, `[::1]`) are blocked at the validation layer.
- **Process isolation.** Gunicorn runs as unprivileged `appuser`; user-submitted commands run as separate unprivileged `scanner` processes. The container filesystem is read-only (`read_only: true`); `/data` is accessible only to `appuser` (`chmod 700`), while optional session workspaces use a shared appuser/scanner group with non-world-readable files. Container startup installs an OS-level guard so `scanner` cannot connect back to the app port.
- **Opt-in raw-packet scans.** Capability-backed scanner modes use the same unprivileged process boundary and fail closed when their readiness checks don't pass. See [Raw-Packet Scanning](#raw-packet-scanning) for tool behavior, fallbacks, restricted-network limits, and setup.
- **Rate limiting + process tracking.** Redis-backed rate limiting prevents burst abuse across multiple Gunicorn workers, including noisy scans against random app paths that would otherwise crowd out normal browser and command requests. PID tracking in Redis keeps kill behavior correct when a kill request lands on a different worker than the one that started the process.
- **Session tracking.** Browsers send a stable `X-Session-ID` so history entries, rate-limit state, and test isolation remain scoped per client without requiring authentication.

**Limits:** there is no authentication layer — controls are defence in depth, not a user boundary. The allowlist plus OS-level isolation are the trust boundary; browser state is not trusted. Loopback blocking applies only to literal loopback addresses and not to private-range addresses that happen to be locally reachable.

**Configuration:**

- `commands.yaml` — dispatch gate (see [Command Allowlist](#command-allowlist)).
- `trusted_proxy_cidrs` in `config.yaml` — CIDRs whose `X-Forwarded-For` is honored.
- `diagnostics_allowed_cidrs` in `config.yaml` — CIDRs permitted to reach `/diag`, `/diag/audit`, and `/metrics`.
- `compose.dev.yaml` for development and the installed `compose.yaml` for production — `read_only: true`, `init: true`, `user` directives, and the port-egress guard.
- `RAW_PACKET_SCANNING_ENABLED` in `.env` — capability-backed raw scanning opt-in.

---

## Structured Logging

**Purpose:** backend-emitted structured events (text or GELF JSON) with stable event names and context fields, so operators can observe the shell through a log aggregator without regex-parsing free-form strings.

**Behavior:**

- The backend emits structured log events at four levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`.
- Two output formats are supported: `text` (human-readable `key=value` pairs for local development) and `gelf` (JSON compatible with log aggregators).
- Each event carries structured context fields — session ID, command root, run ID, HTTP code, or a feature-specific state — rather than interpolated strings, so log lines are machine-parseable without regex.
- GELF fields keep a consistent type across events. HTTP codes stay numeric, feature states stay text, and the formatter avoids the ambiguous legacy `_status` field so OpenSearch can index the stream without status-mapping conflicts.
- Event names are stable (e.g. `RUN_START`, `RUN_END`, `RUN_KILL`, `DIAG_VIEWED`, `UNTRUSTED_PROXY`), letting aggregators filter by name without string matching.
- Browser reports preserve `DEBUG`, `INFO`, `WARNING`, and `ERROR` semantics on the server. Only warning/error reports increment the client-error metric, and safe correlation fields such as artifact IDs are allowlisted explicitly.
- Startup configuration events honor the selected level and text/GELF format even though file loading happens before the runtime logger is ready. Fatal configuration errors keep bounded phase, source, key, and error-type context without logging file contents, values, or parser tracebacks.
- History deletion and Project unlink events include bounded cleanup flags and entity/finding counts in both INFO logs and audit details, without sample values or raw finding/entity text.

**Limits:** field names and level semantics are stable, but specific numeric codes and free-form `message` strings are not part of the contract. Downstream consumers should key off event names and structured fields, not prose.

**Configuration:** `log_format` and `log_level` in `config.yaml`; see [CONFIGURATION.md](CONFIGURATION.md).

**Learn more:** [Logging Reference](docs/logging.md) lists levels, output formats, event names, fields, redaction expectations, and troubleshooting steps.

---

## Audit Log

**Purpose:** a trail of important app actions. Operators get the full IP-gated diagnostics view, while project users and team owners/admins get scoped Activity views for work they can already see.

**Behavior:**

- Open `/diag/audit` from an allowed operator network to review audit rows across the instance. The page uses the same `diagnostics_allowed_cidrs` gate as `/diag` and `/metrics`.
- The viewer lists recent rows with created time, event type, actor, target, scope, and a native details drawer. Details are a safe JSON envelope with allowlisted fields such as actor context, scope, target, job/correlation ids, and bounded action metadata.
- Filters cover event type, actor, team, project, target type, target id, correlation/job chain, date range, and page size. Event choices include short hints so rows such as `history.delete` read as run-deletion events instead of opaque codes.
- CSV and JSON export buttons download the currently filtered result set. Exports honor `audit_export_max_rows`; when more rows match, CSV adds a truncation marker and JSON returns `truncated: true` with a short hint to narrow the filters.
- If `audit_log_enabled` is turned off, the viewer still shows existing rows and displays a warning banner. New product actions proceed without writing new audit rows while audit logging is disabled.
- Rows store hashed session identity, optional team/member actor context, bounded client IP, and bounded user-agent text. Treat those request fields as operator metadata that may still be sensitive in shared environments.
- Audit rows are intentionally smaller than raw app data. File rows do not store file contents, notification rows do not store webhook URLs or secrets, session-token rows store only masked labels and hashes, and import rows store source/options/counts rather than imported bodies.
- The Projects modal also exposes a scoped Activity tab. It shows safe project activity for personal project owners and team members who can view that team project, with filters and pagination but without operator-only request/session metadata. Project metadata edit sheets include a compact Recent activity panel for the current item and can jump into the filtered Activity tab.
- Options → Teams exposes an Activity subtab for team owners and admins. It focuses on team governance and shared-configuration rows, keeps invite/recovery codes, raw tokens, session hashes, IPs, and user agents out of the browser response, and stays unavailable to operators/viewers. The selected team overview shows owners/admins a small Recent activity preview before the full subtab.

**Limits:** `/diag/audit` is an operator-wide view. Anyone allowed through `diagnostics_allowed_cidrs` can see personal and team activity, actor labels, target ids, request metadata, and safe details visible to the audit table. Do not expose it broadly in multi-tenant deployments until you have a narrower owner-scoped audit surface in front of it. The audit log is a product-action trail, not a complete replacement for infrastructure logs.

**Configuration:** `audit_log_enabled`, `audit_retention_days`, `audit_export_max_rows`, `diagnostics_allowed_cidrs`, and `trusted_proxy_cidrs` in `config.yaml`; see [CONFIGURATION.md](CONFIGURATION.md).

---

## Operator Diagnostics

**Purpose:** restricted operator-only surfaces for inspecting current runtime health and scraping trendable Prometheus metrics without opening a shell session.

**Behavior:**

- `/diag` provides a live operator view of the running instance and is disabled by default.
- `/diag/audit` provides the audit-log workflow described in [Audit Log](#audit-log), using the same diagnostics allowlist.
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
| **Vendor Assets** | Whether the bundled browser libraries and font files are present (`loaded`) or missing (`missing`) |
| **Raw-packet Scanning** | Whether the operator opt-in is disabled, ready, or unavailable, plus per-tool capability status and the failed prerequisite category |
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

`/metrics` is meant for Prometheus, Grafana, and similar monitoring stacks. It exposes `darklab_` metrics for HTTP volume and latency, active and completed runs, PTY activity, durable workflow execution and step outcomes/durations, workflow capture failures, cancellations and recovery, rate-limit pressure, broker mode and subscribers, database and Redis health, selected database hot-path latency, Postgres pool health, AI queue health, AI Redis coordination key pressure, workspace usage, Atlas/finding counts, intel provider results and cache size, evidence package builds, snapshots, client errors, and unhandled server exceptions. Labels are bounded to safe values such as command roots, provider IDs, endpoint names, status classes, and coarse outcomes. Workflow metric labels don't include workflow names, input or capture values, targets, paths, or output text.

```bash
curl http://localhost:8888/metrics
```

The repo also includes a starter Grafana dashboard at `examples/grafana/darklab-overview.json`.

**Limits:** `/diag`, `/diag/audit`, and `/metrics` are gated entirely by IP/CIDR allowlists, not by an authentication layer. Empty `diagnostics_allowed_cidrs` disables `/diag` and `/diag/audit` completely and prevents `/metrics` from being scraped. Set `metrics_enabled: false` to keep `/diag` and `/diag/audit` available while hiding `/metrics`.

**Configuration:** `diagnostics_allowed_cidrs`, `trusted_proxy_cidrs`, `metrics_enabled`, and metric histogram buckets live in `config.local.yaml`; `PROMETHEUS_MULTIPROC_DIR` lives in `.env`. See [CONFIGURATION.md](CONFIGURATION.md).

---

## Related Docs

- [README.md](README.md#quick-start) - quick start and project overview
- [CONFIGURATION.md](CONFIGURATION.md) - operator settings and supported runtimes
- [ARCHITECTURE.md](ARCHITECTURE.md) - runtime and security contracts
- [THEME.md](THEME.md) - themes and semantic color tokens
- [docs/tools.md](docs/tools.md) - bundled tool discovery and user guidance
