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
  - **Current state:** `mtr --interactive <host>` has a guarded PTY path behind `interactive_pty_enabled`, uses dedicated `/pty/runs` start/stream/input/resize routes, brokers PTY events through Redis in multi-worker deployments, renders the live terminal in an xterm.js modal, and appends completed PTY runs back into the normal terminal/history output path using server-side terminal capture.
  - Add lifecycle cleanup beyond process exit and max runtime, including stale closed-run cleanup and clearer browser-disconnect behavior.
  - Treat worker-death mid-run as a known limitation: the server-side terminal screen lives on the worker that owns `master_fd`, so a worker crash before exit drops the run from history. Periodic terminal-state snapshots into Redis would address this and are deferred until real usage shows they are needed.
  - Consider a small run metadata marker later, such as `run_type=pty`, so the UI can badge saved interactive runs without changing how their plain-text output is stored.
  - Defer asciinema-style raw byte replay, input auditing, and per-tool capture profiles until real usage shows they are needed.
  - Add browser unit coverage for PTY tab state transitions and disabled normal-terminal behaviors.
  - Add one Playwright smoke test that starts the first supported PTY command, receives screen output, resizes, and kills it cleanly.
  - Revisit transport after real usage: the current pass uses Redis-brokered SSE plus narrow POST input/resize endpoints to avoid adding a WebSocket server dependency; WebSocket may still be useful if latency or throughput becomes a problem.

- **PTY fixes and enhancements**
  - **Backend bugs**
    - PTY command preparation validates the stripped command but starts the original argv without passing the tab's workspace CWD or using `validation.exec_command`. This means CWD-aware workspace file flags and runtime rewrites can drift from normal `/runs` behavior for commands such as `ffuf --interactive -w targets.txt` or `masscan --interactive -iL targets.txt`. Pass `workspace_cwd` into `/pty/runs`, validate with that CWD, and spawn the validated/rewrite-aware argv.
    - `_ptyReadStream` breaks when the SSE body ends without receiving an `exit` event but does not finalize, reconnect, or mark the tab as detached. Mirror the normal runner's stream-ended-without-exit behavior: check `/history/active`, keep Kill available if the PTY is still active, and poll for the saved result instead of leaving the modal/tab stale.
    - `/kill` publishes the `killed` event to `runstream:<id>` via the regular broker for every run, including PTY runs, but PTY clients subscribe to `ptystream:<id>`. The kernel signal still reaches the process and the `exit` event fires correctly through the PTY reader loop, but the explicit "killed by user" notification never surfaces in the PTY stream. Branch on `run_type == "pty"` in `kill_command` and call `pty_service.publish_pty_event` instead.
    - `stream_interactive_pty_run` does not call `active_run_touch_owner`, so PTY runs go owner-stale after `run_broker_owner_stale_seconds` even while the owning tab is actively streaming. Mirror the touch loop already used by `/runs/<id>/stream`.
    - The frontend modal singleton silently disposes the prior xterm when a second `--interactive` command starts in another tab, but the prior backend run keeps running until `interactive_pty_max_runtime_seconds` expires. Pick one rule and enforce it both client- and server-side: refuse a second concurrent PTY per session, auto-kill the prior on dispose, or refocus the existing modal instead of opening a new one.
    - `start_pty_run` only wraps `subprocess.Popen` in try/except. If a later step such as thread start or dataclass construction raises, `master_fd` and the live process are orphaned. Wrap the whole start path so cleanup is symmetric with the reader-loop teardown.
  - **Security**
    - `/pty/runs/<run_id>/input` and `/pty/runs/<run_id>/resize` carry no rate limit. `_PTY_INPUT_MAX_BYTES` caps each request at 4 KB but a misbehaving client can flood the PTY at high rate. Apply the same `limiter.limit` decorator already used by `/pty/runs`.
    - JS truncates input via `String(data).slice(0, 4096)` (UTF-16 code units) while the server checks UTF-8 byte length. A multi-byte paste can clear the JS slice and still trip the server cap, returning a 400 the user cannot diagnose. Match the units on both sides and surface a notice when truncation happens.
    - The Ctrl+C interception in `_ptyInstallKeyboardHandlers` is hardcoded to "confirm kill" rather than passing `\x03` to the PTY. Correct for `mtr/ffuf/masscan` but breaks any future tool that handles `\x03` itself. Move the behavior to a per-tool registry flag such as `interactive.intercept_ctrl_c: true` rather than baking it into the frontend.
    - `_command_env` builds a four-variable env (`TERM`, `LANG`, `LC_ALL`, `PATH`) and falls back to `/usr/local/bin:/usr/bin:/bin` when the host PATH is empty. Future tools that read config files (`HOME`, `USER`) or rely on a richer container PATH will fail silently. Inherit a vetted subset of the host environment instead of reconstructing from primitives.
    - Interactive input is a broader policy surface than normal command validation because keystrokes after process start are not re-validated. Keep the first-pass allowlist narrow and require future PTY tools to declare an explicit input-safety profile before enabling tools with shell escapes, external command prompts, file pickers, or embedded interpreters.
  - **UX gaps**
    - The PTY modal is anchored to the document, not to a tab. Switching tabs while a PTY is running leaves the modal visible against the wrong tab, and the new tab has no affordance indicating that another tab still owns the live terminal. Either follow tab focus (hide on switch, restore on return) or surface a "PTY running" indicator with a reopen action in the running tab's transcript.
    - When the modal is closed the PTY surface disappears from the UI even though Status Monitor lists the run. Add a "PTY running — click to reopen" indicator in the running tab to bridge this gap until the reattach plan below lands.
    - Reload/Status Monitor attach currently rejects PTY runs because the browser cannot reconstruct stateful terminal output from a blank xterm. Keep that behavior user-facing and actionable until the reattach plan lands: show why Attach is disabled, point users back to the owning tab when possible, and avoid implying the run is unrecoverable if it is still active.
    - Mobile experience is unverified. xterm.js does not pop the iOS Safari virtual keyboard for `div role="application"`. Validate on a phone or document mobile as unsupported with a clear notice instead of letting the modal load and quietly stay non-interactive.
    - xterm.js plus the fit addon load on first interactive command, adding ~200–500 ms of visible latency before the modal is usable. Preload the vendor assets at app boot when `interactive_pty_enabled` is true, or surface a "loading terminal…" state.
    - Browser back/forward or external navigation while a PTY is running silently orphans the run on the server. Add a `beforeunload` warning when a PTY is active so the user gets one chance to confirm.
    - `_ptySendInput` truncates pastes at 4096 bytes with no notice. Surface a one-line in-terminal notice when truncation happens so users know the rest did not land.
    - xterm.js theme is captured at terminal-creation time. Switching the app theme while a PTY is open leaves the terminal with stale colors until reload. Listen for theme changes and apply a fresh theme via `term.options.theme = ...` while the PTY is alive.
    - Completed PTY transcript rendering is currently one-size-fits-all. The parent transcript appends the final frame, which is ideal for `mtr` but can omit useful scrolled findings from `ffuf`/`masscan` or include noisy status redraws depending on the tool. Add a registry-owned transcript mode later, such as `final_frame`, `scrollback_findings`, or `all_sanitized`, once real sessions show which tools need custom output shaping.
  - **Architecture**
    - `pty.js` is 725 lines and growing. Split into `pty.js` (orchestration, command detection, entry point), `pty_modal.js` (modal HTML wiring, timer, status), and `pty_terminal.js` (xterm session, resize handlers).
    - `pty_service.py` is ~840 lines mixing terminal capture, run lifecycle, Redis stream transport, control-stream draining, and meta storage. Capture and transport are natural module boundaries; splitting them keeps the lifecycle file readable.
    - The Vitest finalize test mocks 14 globals to exercise pty.js. Introduce a small PTY host interface object that pty.js receives at init and the tests inject a fake for, so the runner.js global surface stops bleeding into PTY tests.
    - `pyte` is optional at import time, but saved PTY history quality depends on it. If `interactive_pty_enabled` is true and `pyte` is missing, surface a startup/diagnostics warning or fail PTY startup with a clear operator message instead of silently falling back to the lossy plain-text capture path.
  - **Polish and operational**
    - `_PTY_INPUT_MAX_BYTES`, `_PTY_BUFFER_LIMIT`, `_PTY_CONTROL_POLL_SECONDS`, and similar tunables are module constants. Move to config so deploys can tune without a rebuild.
    - Add metrics covering concurrent PTY count, average and p95 duration, total input bytes, dropped input bytes, and control queue depth. Expose them through the existing `/diag` surface so operators have visibility comparable to other run paths.
    - The reader loop polls Redis every 200 ms via `xread block=1` for control events. With many concurrent PTYs this is wasted ops. Switch the control channel to Redis Pub/Sub (or a longer block window) so idle PTYs cost zero ops while output latency stays unaffected.
    - `_loadPtyScriptOnce` can wait forever on an existing script tag that already failed before the retry was attached. Track failed vendor asset loads or replace failed script/link tags before retrying so a transient xterm asset failure can recover cleanly.

- **Implementation plan: reattach to active PTY runs from a new browser context**
  - **Goal:** make the existing reload-restore and Status Monitor "Attach" flows work for PTY runs the way they already do for normal `/runs`. Today both paths explicitly reject `run_type === 'pty'` (`runner.js:295`, `runner.js:412`, and the `_isPtyRun` guards in `status_monitor.js`) because PTY output is stateful and cannot be reconstructed by replaying events from `after_id` against a blank xterm. The work below restores screen state at attach time and then follows live, in three additive tiers.
  - **Phase 1 — Plain-text resume**
    - Add `GET /pty/runs/<run_id>/snapshot` returning the existing `synthesize_entries()` text plus `rows`, `cols`, and the most recent `after_event_id`. The session-owner check matches the other PTY routes; reject when the run is not in `_runs` on this worker so the caller can surface the worker-death case clearly.
    - Add `attachInteractivePtyCommand(runId)` on the frontend: open a fresh xterm modal, `term.write()` the snapshot text plus a one-line `[reattached — earlier formatting lost]` notice, then subscribe to `/pty/runs/<run_id>/stream?after=<event_id>` to follow live.
    - Flip the rejection guards: `_shouldAutoRestoreActiveRun`, `attachActiveRunFromMonitor`, and the `_isPtyRun` action gates in `status_monitor.js`. For runs owned by the current session, route them through `attachInteractivePtyCommand` instead of refusing.
    - Decide and codify the multi-subscriber input policy now, even though it is technically a Phase 2/3 problem. The simplest rule is "the most recent attach holds input, earlier subscribers go read-only," issued as a server-owned attach token tied to a single client id. Locking this in during Phase 1 avoids a behavior change once users rely on the feature.
    - Document worker-death as a Phase 1 limitation: reattach only works while the worker that owns `master_fd` is alive. Phase 3 removes it.
    - Tests: snapshot endpoint shape and session-owner enforcement; attach flow that writes the snapshot and subscribes from the supplied event id; one Playwright smoke that submits an interactive command, reloads or clicks Attach, and asserts the live PTY continues in the new context.
  - **Phase 2 — Stateful pyte snapshot**
    - Add a pyte → ANSI serializer that walks `screen.history.top` and `screen.display`, emitting SGR changes, cell data, scroll-region setup, alt-screen toggle when active, and a final cursor-position move. Target the subset xterm.js needs to recreate the screen, not full ECMA-48 fidelity.
    - Switch the snapshot endpoint payload from synthesized text to the serialized ANSI byte stream and update the attach flow to `term.write()` those bytes. No other frontend logic changes; everything from Phase 1 still applies.
    - Replace the Phase 1 `[reattached — earlier formatting lost]` notice with a subtler `[reattached]` line once snapshots restore colors, cursor, and scroll state faithfully. The audit trail is still useful even when the visual difference disappears.
    - Cap serializer output to a hard byte ceiling so a runaway alt-screen plus deep history cannot turn one reattach into a multi-megabyte response.
    - Tests: feed a known sequence into pyte, snapshot, feed the snapshot into a fresh pyte, assert `display` and `history` round-trip. Cover SGR, cursor position, scroll regions, and alt-screen states.
  - **Phase 3 — Distributed snapshots**
    - Periodically push the serialized pyte snapshot to Redis from the reader loop (every N bytes or every N seconds, whichever fires first). Cap snapshot age so stale reattaches degrade to "earlier output truncated" instead of silently lying about state.
    - Read snapshots from Redis in the snapshot endpoint instead of relying on a worker-resident pyte instance. Lets any worker serve the reattach, removes the worker-death limitation, and removes any need for sticky sessions during reattach.
    - Reuse `run_broker_active_stream_ttl_seconds` for the snapshot key TTL so completed-run cleanup stays unified instead of growing a parallel retention knob.
    - Tests: simulate worker death by mocking the `_runs` lookup to return None and assert the Redis-backed snapshot path still produces a usable terminal; verify the periodic publisher does not regress live SSE latency under sustained output.
  - **Cross-cutting decisions**
    - **Snapshot freshness race:** the snapshot endpoint must return the `after_event_id` corresponding to the last event applied to the snapshot, so the subscribe call closes the gap deterministically. No locks needed; ordering is guaranteed by the Redis xstream id space.
    - **Modal integration:** reattach should target the PTY modal, not the main transcript. If the modal is gone after a reload, the main tab shows a "Reopen PTY" button that opens the modal from a user gesture and runs the attach flow.
    - **Bandwidth:** Phase 2 snapshots for a 24×100 terminal are at most ~24 KB; Phase 1 is ~2–3 KB. Not a sizing constraint, but pair the Phase 2 hard ceiling with a one-line size-warning log so unexpected blowup is visible in operator metrics.
    - **Status Monitor parity:** once Phase 1 lands, the Attach action for PTY runs should use the same hover/focus chrome as normal runs. No PTY-specific styling; the rejection guards were the only difference.

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

- **Transcript noise classification**
  - Future cleanup for saved command output across both normal runs and interactive PTY runs.
  - Avoid broad duplicate-line removal because repeated lines can be meaningful findings for some tools.
  - Classify known progress/status/redraw lines before history/search/finding classification, starting with high-noise shapes from tools like `masscan`, `ffuf`, `nuclei`, and ProjectDiscovery tools that emit frequent status updates.
  - Keep real newline-terminated findings and normal scrollback untouched.
  - For interactive PTY runs, keep the final visible frame available so users can still inspect the last terminal state, even when progress/status redraw lines are excluded from searchable saved transcript text.
  - For normal runs, prefer command-specific noise classifiers over global suppression so raw output stays faithful while search, findings, summaries, and previews become easier to use.

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

- **Interactive PTY transport future-state**
  - Revisit whether the current Redis-brokered SSE plus POST input/resize transport should move to WebSockets after real use.
  - The current model keeps deployment simple and avoids a WebSocket runtime, but a bidirectional socket could reduce input latency and simplify the modal terminal stream once PTY usage grows.
