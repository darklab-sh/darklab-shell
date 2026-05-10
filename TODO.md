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

- **Future Project Workspace enhancements**
  - **Security and lifecycle**
    - Validate `workspace_file` entity ownership during session migration, or document that labels/notes on workspace-file paths can drift when a migrated token lands in a session with a different file at the same path.
    - Add a terminal-native `project rename <name-or-id> <new-name>` command so CLI users can rename projects without opening the modal.
    - Add parallel PATCH routes for partial project and target updates if the project workspace API ever becomes more than a trusted browser-only surface.
  - **Code organization**
    - Split `project_workspace.py` into focused modules once the surface settles. Natural boundaries are core project CRUD, entity metadata, findings, packages, and session migration.
    - Move Projects modal rendering and event wiring out of `shell_chrome.js` into a dedicated project workspace browser module.
    - Reduce repeated `projects.py` route boilerplate with small serialization/404 helpers.
  - **Capture, tagging, and navigation**
    - Expose `Add label`, `Add note`, `Open in project`, and `Add as project target` on transcript right-click or signal-tagged token long-press; this should replace the removed Projects-modal quick-add target flow.
    - Add contextual quick-add target entry points from history rows and workspace file previews once the shared action-menu pattern exists.
    - Consider a per-project current-target sub-state so `${target}` placeholder substitution can follow sustained work on a single host.
    - Decide whether `host` remains a visible target type or is retained only as a backend compatibility value.
    - Add a compact project switcher near the prompt with recently used projects and a Create New action.
    - Show run, finding, artifact, and package counts on project-list rows so project scale is visible before opening each project.
  - **Future-state mobile polish**
    - Add OS Back / browser Back support with `history.pushState` after the base sheet navigation is stable.
    - Add a project search/filter input above the mobile list once project counts justify it.
    - Consider swipe gestures for target and finding rows only after overflow-menu interactions are shipped and tested.
  - **Findings and comparison**
    - Extend the Findings tab filters beyond target/run/review state to command root, severity, scope, labels, and note state.
    - Add multi-select plus bulk review actions for high-volume finding review.
    - Prefetch finding counts and severity distribution so tab labels can show useful state such as unreviewed/high counts without opening the tab.
    - Extend comparison beyond run-to-run finding/artifact diffs to snapshots and package artifacts.
  - **Evidence packages**
    - Materialize evidence package archives at creation time if byte-for-byte repeat downloads become important.
    - Make package presets config-driven so new bundle profiles, such as internal review or external handoff, can be added without code changes.
    - Add richer per-finding remediation or verification fields if findings evolve beyond raw output capture.
    - Add richer target references in package exports, including derived relationships that are not directly visible in selected finding text.
    - Add richer provenance metadata and round-trip import hints for labels, notes, targets, findings, and packages.
    - Explore fuller direct template reuse for package run transcript pages without reintroducing app-hosted asset links.
    - Add redacted text/JSON derivatives for safe artifact types before allowing raw artifact inclusion in redacted packages.
    - Add richer redaction previews and per-item redaction warnings for package creation.
    - Add async package build progress for large Full Archive exports so long builds do not feel like stalled requests.
    - Add generated re-package names that preserve the original selection while incrementing the package label or timestamp.
    - Move package HTML rendering toward shared Jinja autoescape paths so package output escaping is template-owned instead of manual per-call escaping.
  - **Retention and mobile**
    - Finish pruning/retention behavior for project-linked runs and run-scoped artifacts.

- **Future interactive PTY enhancements**
  - **Future lifecycle and resilience**
    - Consider auto-displacing prior live attaches when a new browser client attaches to the same PTY run. When `active_run_claim_owner` flips the internal ownership marker to a different `client_id`, publish a single `displaced` event on the PTY stream so the prior tab can close its modal cleanly and append one notice such as `[interactive PTY moved to another tab]`. Skip same-client reconnects so the event only fires when the live view genuinely moves to a different browser context. With this in place, the remaining per-keystroke `[interactive PTY input ignored: ...]` notices in `_ptySendInput` could become rare edge-case failures instead of common transcript noise.
    - Revisit transport after real usage. The current pass uses Redis-brokered SSE plus narrow POST input/resize endpoints to avoid adding a WebSocket server dependency; WebSocket may still be useful if latency, throughput, or bidirectional control behavior becomes a real limitation.
  - **Future security**
    - Defer asciinema-style raw byte replay and input auditing until real usage shows they are needed.
  - **Future architecture**
    - Split `pty.js` into smaller modules once PTY work resumes in depth. Natural boundaries are orchestration/command detection, modal wiring/timer/status, and xterm session/resize handling.
    - Split `pty_service.py` once more PTY server behavior accumulates. Capture, run lifecycle, Redis stream transport, control-stream draining, and metadata storage are natural module boundaries.
    - Consider dropping the base `#pty-overlay` from `index.html` and building every PTY modal through `_ptyBuildOverlay`. Tab overlays are now normalized and reused, so this is cleanup rather than a leak fix; the benefit would be removing the remaining ID/class selector duality in `_ptyModalEls`.
    - Verify or document PTY modal positioning and mobile-sheet behavior with the overlay scoped inside `.tab-panel`. PTY startup is disabled on mobile, but the shared modal/mobile-sheet CSS still deserves a viewport sanity check if the modal layout changes again.
    - Introduce a small PTY host interface object for browser tests. `pty.js` still reaches into many runner globals; a host object would make tests less brittle and reduce global-surface coupling.
    - Add broader browser unit coverage for PTY tab state transitions and disabled normal-terminal behaviors as future PTY features are added.
  - **Future polish and operational visibility**
    - `_PTY_INPUT_MAX_BYTES`, `_PTY_BUFFER_LIMIT`, `_PTY_CONTROL_POLL_SECONDS`, `_PTY_SNAPSHOT_FALLBACK_ENTRY_LIMIT`, and similar tunables are module constants. Move to config so deploys can tune without a rebuild.
    - Add metrics covering concurrent PTY count, average and p95 duration, total input bytes, dropped input bytes, and control queue depth. Expose them through the existing `/diag` surface so operators have visibility comparable to other run paths.
    - The reader loop polls Redis every 200 ms via `xread block=1` for control events. With many concurrent PTYs this is wasted ops. Switch the control channel to Redis Pub/Sub (or a longer block window) so idle PTYs cost zero ops while output latency stays unaffected.
    - Surface snapshot age on the reattach payload. `_load_pty_snapshot` strips `created_at` before returning, so the frontend cannot tell whether the snapshot is fresh or 20+ seconds stale. Return the age and let the frontend show `[reattached - snapshot was Ns old]` when it crosses a threshold, so users know the screen they see may not match what the PTY is currently rendering.
    - Skip the unconditional `_store_pty_snapshot(run, force=True)` in `pty_run_snapshot` when the request hits the worker that owns the PTY. The route already returns the live in-memory payload to the caller, and the next reader-loop tick will publish to Redis naturally; the extra Redis SET costs one round-trip per attach for cross-worker freshness that is rarely consumed.
    - Consider pausing xterm rendering for hidden-tab PTYs. xterm.js running in a `display: none` panel still processes writes and grows scrollback (capped at 1000 lines, but still wasted CPU). Either drop incoming `output` chunks into the modal only when visible (queue and replay on tab focus) or accept the cost as small enough to ignore — worth measuring under a long-running ffuf in a backgrounded tab before spending engineering on it.

- **Run comparison follow-ups**
  - v1 split-pane comparison is shipped through canonical `/history/compare`; future work should build on the hunk model instead of reintroducing route- or modal-specific compare paths.
  - Keep the diff scope split intact: transcript output remains ordered and hunk-based, while finding/artifact object comparison remains key-based and order-insensitive so reordered findings do not register as added/removed.
  - **v2 — minimap rail, finding/artifact anchors, view-mode toggle**
    - **Backend changes** (`app/blueprints/history.py`, `app/project_workspace.py`)
      - Add `density_buckets: [{equal, added, removed, changed}, ...]` to the comparison response. Fixed length via a backend constant `COMPARE_MINIMAP_BUCKETS = 256` so payload shape stays stable across runs of any size; the frontend interpolates to actual rail height. Computed in a single pass over the same `hunks` walk so no extra diff cost.
      - Populate `output_line_index` on each finding/artifact for both sides where derivable. `_run_finding_compare_items` joins `findings.line_number` to the run's persisted line offsets; if the source output is no longer available, the field is omitted and the frontend falls back to non-anchored display.
      - No new endpoints; the consolidated `/history/compare` route gains the new fields and they flow through both entry points (history-drawer and project compare control) automatically.
    - **Frontend additions** (`app/static/js/history.js`, `app/static/css/components.css`, `app/static/js/state.js`)
      - Add `_renderHistoryCompareMinimap(buckets, totals)` rendered as a thin `<div class="history-compare-minimap">` rail anchored to the right edge of the split-pane container. Each bucket is a 2px-tall `<div>` whose background-color is the dominant op tone — `--green` (added), `--red` (removed), `--amber` (changed), low-opacity `--muted` (equal). Click on a bucket scrolls both panes to the corresponding line range through the existing sync-scroll binding. Hidden under `@media (max-width: 760px)` so unified mobile keeps the simpler layout.
      - Wire finding/artifact anchors: on `_renderHistoryCompareObjectSection` row click, find the matching pane row by `data-line-index` and scroll it into view in both panes; pulse a `.history-compare-line-pulse` class (`animation: pulse 800ms ease-out`) for visual confirmation. Emit `emitUiEvent('app:compare-anchor-scroll', {side, line_index})` so future modules can subscribe through the existing cross-module event bus.
      - Render a finding marker in each pane's left gutter at any line carrying an `output_line_index` match. Marker uses `.history-compare-finding-marker` with severity tone (`--red` high/critical, `--amber` medium, `--muted` info). Click on the marker scrolls the linked finding row in the findings section into view.
      - Add a view-mode toggle in the compare-modal header. Implement as a hidden `<select>` enhanced through `enhanceAppSelects()` per the App-native Select Primitive contract so it composes the `.dropdown-surface` / `.dropdown-item-touch` family and inherits keyboard / outside-click / `aria-expanded` behavior automatically. Modes:
        - `Side-by-side` (default at ≥ 760px) — v1 split layout.
        - `Unified` (default below 760px) — v1 unified layout.
        - `Changes only` — collapses every `equal` hunk to a single zero-context fold and skips equal lines entirely. Equivalent to the pre-v1 view but riding on the same hunk model.
        - `Findings only` — hides the split pane entirely, leaving the run cards, metrics row, counts banner, and findings/artifacts sections.
      - Persist the chosen mode in `state.js` as `comparisonViewMode` and add it to the Options modal so the choice survives reload through the same per-session-token preference path used by the rest of the shell. Mobile-first defaults still apply on first load.
      - Add a `±N context` chip row above the split pane composing `.chip` + `.chip-action` with options `±3 / ±10 / All`. Selection updates a frontend-only state and re-renders the lines region without re-fetching.
      - All new pressable surfaces route through `bindPressable`/`bindDisclosure`/`enhanceAppSelects` so they pick up the existing button-primitive allowlist, focus-trap, refocus-composer, and outside-click contracts without local wiring.
    - **Tests**
      - Backend: unit coverage for bucket aggregation (constant bucket count regardless of input size, sum of bucket counts equals total line count, off-by-one at the final bucket, finding `output_line_index` populated when persisted offsets are present and omitted when not).
      - Frontend: Vitest coverage for minimap bucket-to-DOM density mapping, finding-row click → pane scroll → pulse class lifecycle, view-mode toggle preference round-trip through `state.js`, `±N context` chip selection re-rendering folds without re-fetching.
      - E2E: extend the v1 Playwright spec with mode-toggle steps (verify each mode's row counts), minimap-click navigation, and finding-row click anchoring across both panes.
      - Update `tests/js/unit/button_primitives_allowlist.test.js` only if a new pressable surface lands outside the allowed primitive families (the `±N context` chips and the view-mode toggle should both inherit existing primitives).
    - **Docs**
      - Update the `Findings and comparison` sub-list to remove items now covered by v2.
      - If `ARCHITECTURE.md § Browser State Model` enumerates persisted preferences, add `comparisonViewMode` and the `±N context` default to that list.
      - `CHANGELOG.md` entry for v2 mirroring the v1 format.
      - Refresh the test-count locations once new tests land.

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
