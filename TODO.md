# TODO

This file tracks open work, known issues, technical debt, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Ideas are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
- [Research](#research)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Ideas](#ideas)
- [Architecture](#architecture)

---

## Open TODOs

- **Interactive PTY mode follow-ups after the first pass**
  - **Current state:** `mtr --interactive <host>` has a guarded PTY path behind `interactive_pty_enabled`, uses dedicated `/pty/runs` start/stream/input/resize routes, brokers PTY events through Redis in multi-worker deployments, and renders the browser terminal with vendored xterm.js.
  - Add lifecycle cleanup beyond process exit and max runtime, including stale closed-run cleanup and clearer browser-disconnect behavior.
  - **Implementation plan: persist PTY runs through server-side terminal capture**
    - Add a lightweight server-side terminal emulator, likely `pyte`, to each `PtyRun` so every PTY output chunk is fed to both the existing live SSE/Redis stream and a backend screen model. Keep live rendering in xterm.js; the server-side emulator is for persistence, search, signal discovery, and future reattach snapshots.
    - Size pyte's `HistoryScreen` to roughly `2 * max_output_lines` so its built-in scrollback ceiling does not silently truncate earlier than the existing preview/artifact spillover; the existing config knob continues to govern disk usage.
    - On resize, resize the server-side screen model alongside the real PTY and browser terminal so persisted scrollback geometry matches what the user saw.
    - Refactor the PTY reader loop's `finally` clause to flow through the same `_save_completed_run` plumbing used by `/runs`; today it only calls `pid_pop` and `active_run_remove`, so extracting a shared finalizer is the bulk of the implementation work.
    - Persist on every exit path — clean process exit, max-runtime timeout, `/kill`, and stream errors — by keeping synthesis inside `finally` rather than only the success branch.
    - On exit, synthesize ANSI-free saved output from terminal scrollback plus the final visible frame.
    - rstrip each synthesized line so pyte's column padding does not bleed into preview snippets or FTS results.
    - Trim trailing blank lines from the final frame while preserving useful internal spacing.
    - Always include the final frame, even if it duplicates the tail of scrollback, so saved interactive runs clearly show the last visible terminal state.
    - Emit the separator between scrollback and final frame as a `cls`-tagged line (for example `cls="pty-marker"`) rather than a literal text marker, so downstream consumers can filter the seam without regex-matching the marker text.
    - Skip the separator when scrollback is empty (the `mtr` case), so a lone marker with nothing above it does not appear in saved output.
    - When both scrollback and final frame are blank, persist a single notice line such as `[interactive PTY exited with no output]` so the history row stays coherent.
    - Remove the unused `run.capture: list[str]` buffer on `PtyRun` once pyte owns persistence-side capture, so two parallel captured-bytes paths cannot drift.
    - Persist the synthesized lines through the normal run history/output path so previews, full-output artifacts, FTS, permalinks, shares, retention, and exports keep working without a PTY-specific database fork.
    - Keep the saved `runs.command` value as the user-typed original (including the trigger flag) so History re-run sends users back through the PTY route; use the stripped `execution_command` only when initializing `OutputSignalClassifier`, so signal rules see the same command shape they would for a normal `/runs` invocation.
    - Run `OutputSignalClassifier` once after PTY exit against the stable synthesized text, not incrementally against live redraw bytes.
    - Verify quit-by-keystroke (`q` for mtr, etc.) already exits with code 0 for each interactive tool before adding any special-case mapping; most ncurses tools already do.
    - Treat worker-death mid-run as a known limitation: the pyte screen lives on the worker that owns `master_fd`, so a worker crash before exit drops the run from history. Periodic pyte-state snapshots into Redis would address this and are deferred until real usage shows they are needed.
    - Consider a small run metadata marker later, such as `run_type=pty`, so the UI can badge saved interactive runs without changing how their plain-text output is stored.
    - Defer asciinema-style raw byte replay, input auditing, and per-tool capture profiles until real usage shows they are needed.
  - Add browser unit coverage for PTY tab state transitions and disabled normal-terminal behaviors.
  - Add one Playwright smoke test that starts the first supported PTY command, receives screen output, resizes, and kills it cleanly.
  - Revisit transport after real usage: the current pass uses Redis-brokered SSE plus narrow POST input/resize endpoints to avoid adding a WebSocket server dependency; WebSocket may still be useful if latency or throughput becomes a problem.

## Research

No research items are currently tracked.

---

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

No technical debt items are currently tracked.

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

- **Tool-specific guidance**
  - Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `naabu`, or `nuclei`.
  - Good fit for the existing help / FAQ / welcome surfaces.
  - Merge this with onboarding and command hints into a broader user guidance layer:
    - command-specific caveats
    - what to expect while a tool runs
    - examples of when to use one tool vs another

- **Command catalog future-state**
  - Add `commands search <term>` for roots, descriptions, categories, examples, and flag text.
  - Add `commands --json` or `commands info --json <root>` for debugging, export, and future UI reuse.
  - Add optional richer registry fields such as `details`, `notes`, `common_flags`, or `gotchas` when a flag or tool needs more than a short autocomplete description.
  - Add command-specific guidance for web-shell behavior, including injected safe defaults, quiet-running tools, generated Files output, and managed session state.
  - Add autocomplete side previews later: when a root, subcommand, or flag is highlighted, show the command description or flag note in a small help pane.
  - Add hover/focus cards for FAQ chips once the command-details modal behavior has settled.
  - Consider including pipe helpers in a separate “Pipes” section once command catalog UX exists.
  - Consider linking command catalog entries to real `man` output where available, while keeping app-native allowed-subset details primary.

- **Command outcome summaries**
  - For selected tools, generate short app-native summaries below the raw output. Security tool output is high-volume; a clear findings layer is what separates a purpose-built tool from a raw terminal.
  - Keep raw output primary — the summary is additive, never a replacement.
  - Start narrow: nmap (open ports + service table), dig (records returned), curl (status code + redirect chain), openssl s_client (cert expiry + trust chain).
  - The structured output model (see Architecture) is the right long-term foundation. Build this feature so it can move onto that model later instead of requiring it up front.

- **Run comparison enhancements**
  - Future-state enhancements after the v1 history-row comparison flow has real use.
    - Finding-level diffs using persisted signal/finding metadata:
      - New findings.
      - Disappeared findings.
      - Unchanged findings.
      - Changed severity or changed metadata.
    - Tool-aware diffs for common scanner outputs:
      - `nmap`: ports, protocols, services, versions, and state changes.
      - URL/status/title lists: new URLs, disappeared URLs, status changes, title changes.
      - Subdomain lists: new and disappeared names.
      - TLS/certificate output: issuer, subject, SAN, validity, and fingerprint changes.
    - Keep tool-aware parsers additive; raw changed/added/removed output should remain the fallback.
  - Future entry points and packaging:
    - Active tab `Compare` action for restored/completed runs.
    - Findings strip action such as `Compare findings with previous run`.
    - Workflow provenance in comparison summaries once workflow-linked runs exist.
    - Project baseline compare once projects exist.
    - Snapshot/permalink compare if the run-vs-run model continues to work well.
    - `Export comparison` once share/export packages have a stable artifact model.
  - Future UX/testing:
    - Consider date-range filters in the manual compare picker if day grouping plus `Load More` is not enough for deep history.
    - Add Playwright coverage for the compare launcher/result flow on desktop and mobile after the UI settles.
    - Add focused large/noisy comparison regression coverage if real-world outputs expose performance issues beyond current backend and unit coverage.

- **Bulk history operations**
  - The history drawer can delete all or delete non-favorites. Adding multi-select (checkbox mode) with bulk delete, bulk export to JSONL/txt, and bulk share would close a real gap when clearing out a session after an engagement or exporting selected findings.

- **Autocomplete suggestions from output context**
  - When a previous command's output is in the active tab, `| grep` completions could suggest patterns already present in that output — IP addresses, hostnames, status codes, CVE strings — as candidates alongside the generic flag list.
  - Narrow but would make the pipe stage feel predictive rather than generic.

- **Mobile share ergonomics**
  - The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
    - save/share actions tuned for one-handed use
    - clearer copy/share/export affordances inside the mobile shell
    - better share handoff after snapshot creation

---

## Architecture

- **Structured output model**
  - Preserve richer line/event details consistently for all runs.
  - This would improve search, comparison, redaction, exports, and permalink fidelity.
  - Command outcome summaries are buildable without this foundation, but design them so they can move onto the structured model later. Summary parsers should consume structured line events, not re-parse raw text forever.

- **Unified terminal built-in lifecycle**
  - Browser-owned built-ins (`theme`, `config`, and `session-token`) need browser execution for DOM state, local storage, clipboard, and transcript-owned confirmations, while server-owned built-ins naturally flow through `/runs`.
  - The long-term cleanup target is one terminal-command lifecycle after execution:
    - normalize built-in output into a shared result shape
    - apply pipe helpers against that shape
    - mask sensitive command arguments once
    - render transcript output once
    - persist server-backed history once
    - load recents and prompt history from the same saved run model
  - Keep execution ownership separate where it matters, but remove duplicated recents/history/pipe/persistence glue so browser-owned and server-owned built-ins cannot drift.

- **Plugin-style helper command registry**
  - Turn the built-in command layer into a cleaner extension point for future app-native helpers.

- **Lightweight Jinja base template**
  - `index.html`, `permalink_base.html`, and `diag.html` now all share the same ~10 lines of `<head>` bootstrap (charset, viewport, color-scheme meta, favicon, `fonts.css`, `styles.css`, theme var includes, and the two vendor scripts). With three templates the duplication is starting to pay for the indirection.
  - A `base.html` factoring out the common `<head>` and `data-theme` body attribute would prevent drift and make adding a fourth page type trivial.

- **Interactive PTY mode for screen-based tools**
  - Explore an optional PTY + WebSocket + browser terminal emulator path for a small allowlisted set of interactive or screen-redrawing tools such as `mtr`, without turning the app into a general-purpose remote shell.
  - Best fit is a separate interactive-command mode or tab type, not a full browser shell session.
  - This would be a larger architecture change because it needs:
    - server-side PTY management
    - bidirectional browser transport
    - terminal resize handling
    - stricter command scoping and lifecycle cleanup
