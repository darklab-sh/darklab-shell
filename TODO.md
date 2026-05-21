# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Feature Enhancements](#feature-enhancements)
  - [Atlas Enhancements](#atlas-enhancements)
  - [Future Project Workspace enhancements](#future-project-workspace-enhancements)
  - [Future interactive PTY enhancements](#future-interactive-pty-enhancements)
- [Research](#research)
- [Ideas](#ideas)
  - [Tool-specific guidance](#tool-specific-guidance)
  - [Command catalog future-state](#command-catalog-future-state)
  - [Command outcome summaries](#command-outcome-summaries)
  - [Transcript noise classification](#transcript-noise-classification)
  - [Run comparison enhancements](#run-comparison-enhancements)
  - [Bulk history export and share](#bulk-history-export-and-share)
  - [Autocomplete suggestions from output context](#autocomplete-suggestions-from-output-context)
  - [Mobile share ergonomics](#mobile-share-ergonomics)
  - [PWA install and service-worker push](#pwa-install-and-service-worker-push)
  - [Engagement report builder](#engagement-report-builder)
- [Architecture](#architecture)
  - [Unified terminal built-in lifecycle](#unified-terminal-built-in-lifecycle)
  - [Plugin-style helper command registry](#plugin-style-helper-command-registry)
  - [Lightweight Jinja base template](#lightweight-jinja-base-template)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

- **Promote shared run/history API helpers out of browser blueprints.**
  - `app/blueprints/api_v1.py` intentionally reuses private helpers from `blueprints.run` and `blueprints.history` to keep v1 behavior aligned with the browser path.
  - Once the API surface settles, move the shared run-start, stream, history-output, and history-count pieces into service modules so browser routes and `/api/v1` routes both depend on stable service boundaries instead of private route helpers.

- **Migrate inline modal action-result text to `showToast` for consistency.**
  - The Atlas overlay, Workflows modal, Run Comparison, tab exports, permalink, and the Session Token copy/apply/clear/rotate paths already toast every action result via `showToast(message, tone)`. The Options → Notifications panel was migrated in a recent fix using a local `_toast()` helper that routes through `showToast` and falls back to the inline message bar only when the global is missing — that's the model the surfaces below should adopt.
  - Pattern A — `field-save-status` inline "saved" badges. Small `<span role="status" aria-live="polite">saved</span>` flashed next to an input. Replace with a one-shot toast on save.
    - Options → Prompt name: `#options-prompt-username-saved` (`app/templates/index.html:1041`); driven by `showPromptUsernameSavedIndicator` / `hidePromptUsernameSavedIndicator` in `app/static/js/features/preferences/preferences.js:483, 491, 493, 497`.
    - Run Details → Project notes editor: `#project-notes-save-status` (`app/templates/index.html:834`).
    - Run Details → Project labels editor: `#project-labels-save-status` (`app/templates/index.html:839`).
  - Pattern B — persistent in-modal message bars. One shared element holds the latest action result until overwritten or dismissed. Migrate success paths to `showToast`; keep the bar only for long-running progress (e.g., package archive build polling).
    - Options → Secrets panel (`app/static/js/features/preferences/secrets_panel.js`).
      - Element: `#options-secrets-msg`; helper: `_optionsSecretsShowMsg(message, isError)` at line 36-39.
      - Success strings to migrate: `` `${normalizedName} saved.` ``, `` `${normalizedName} replaced.` ``, `` `${normalizedName} deleted.` `` (lines 655-657, 715), `'Secret entry canceled.'` (line 683).
      - Error strings to migrate: `'Unable to open secret editor'`, `'Unable to edit secret'`, `'Unable to delete secret'`, `'Save failed — …'`, `'Failed to load secrets — …'`, `'Failed to load provider status — …'` (lines 214, 366, 437, 448, 472, 661).
    - Options → Session Token controls (`app/static/js/features/preferences/session_token_controls.js`).
      - Element: `#options-session-token-msg`; helper at lines 31-33. Copy/apply/clear/rotate already toast (lines 112, 363, 406, 407, 417); the gap is the validation/error paths (`'Invalid token — expected tok_… or a UUID'` line 268, rotate-verify error line 295) plus the masked-token display at line 8.
      - The token-display field at line 8 is current-state, not an action result — leave it inline.
    - Projects modal — the biggest offender (~60 call sites). Element rendered by `app/static/js/features/projects/project_workspace_shell.js:38-60` (`project-workspace-message` + `project-workspace-message-text` plus a `[data-project-message-dismiss]` close button so the bar persists until clicked); helper `setProjectWorkspaceMessage(text, {error, toast})` called across `app/static/js/features/projects/*.js`. Note: `project_workspace_shell.js:29-31` already imports `showToast`, so the surface is wired up.
      - Success strings to migrate: `'Target added to selected project.'` / `'Target updated.'` (`project_targets.js:164`), `` `${n} entities added to project.` `` (`project_entities.js:931`), `'Package created.'` (`project_packages.js:1183`), `'Project deleted.'` (`project_workspace_events.js:752`), `'Findings deleted.'` (`project_workspace_events.js:886`), `'Target removed.'` (`project_workspace_events.js:933`), `'Run removed from project.'` (`project_workspace_events.js:994`), `'Package deleted.'` (`project_workspace_events.js:1066`), `` `${kind} metadata saved.` `` (`project_entity_editor.js:80`), `` `${removedCount} unavailable ${noun} removed; …` `` (`project_packages.js:1168`).
      - Error strings to migrate: `'Could not save target.'` (`project_targets.js:166`), `'Could not load project runs.'` (`project_runs.js:59`), `'Package action failed.'` (`project_packages.js:1548`), plus the rest under the existing `error: true` paths.
      - Keep inline only: long-running status that updates while polling, e.g., `` `Preparing package archive: ${packageJobMessage(current)}` `` (`project_packages.js:1238`). Toast would flash repeatedly.
    - Workspace / Files modal (`app/static/js/workspace.js`).
      - Element: `workspaceMessage`; helper `setWorkspaceMessage(message, tone)` at lines 65-70. There is already a `_showWorkspaceToast` fallback (lines 72-77) that prefers `showToast` when available — but the success paths bypass it and call `setWorkspaceMessage` directly.
      - Success strings to migrate to `showToast`: `` `Saved ${savedPath}` `` (line 1065), `` `Created folder ${path}` `` (line 1081), `` `Deleted ${kind} ${path}` `` (line 1243), `` `Moved ${source} to ${destination}` `` (line 1257).
      - Error strings: route through `_showWorkspaceToast` (already toast-aware) instead of `setWorkspaceMessage(..., 'error')` at lines 1037, 1089, 1167, 1291, 1475.
  - Out of scope (leave inline). Editor-local validation that fails in place inside the editor card body — `editor.error.textContent = …` in `notification_channels.js:364`, custom-secret editor `err.textContent = …` at `secrets_panel.js:619, 627, 637`, session-token apply/rotate error nodes at `session_token_controls.js:268, 295`. These are field-contextual errors, not transient action results.
  - Acceptance criteria when the migration lands:
    - Every success path in Patterns A and B routes through `showToast` (or a local `_toast()` helper that wraps it).
    - Pattern A's three `field-save-status` spans can be removed from the templates (no consumers left).
    - The Projects modal's `setProjectWorkspaceMessage` becomes either deleted (if no caller needs it after migration) or restricted to the long-running polling case in `project_packages.js:1238`.
    - The Workspace modal's `setWorkspaceMessage` is reduced to load-error/empty-state messaging; success paths use `showToast`.

---

## Feature Enhancements

### API / CLI Enhancements
- **CLI tab completion for `darklab`.**
  - Add `darklab completion zsh|bash|fish` so operators can install shell completion without adding a runtime dependency.
  - First slice should be static completion for subcommands, nested subcommands, option names, and fixed choices such as `--format text|json|ndjson`, `--orphan-filter hide|all|only`, and notification channel kinds.
  - Later, consider quiet API-backed dynamic completion for high-value live values such as project names, active run ids, and notification channel ids. Dynamic completion should fail silently when the API is unavailable and avoid slow network calls on every tab press.
- **Webhook receiver / `POST /api/v1/intel/<provider>` passthrough.**
  - Not for v1.1, but worth scoping — once outbound notifications land, the headless API becomes the natural place to receive `pull-request-merged` / `engagement-kicked-off` webhooks that auto-create projects.
- **CLI: `darklab logs <run_id>`.**
  - A thin wrapper over ranged output reads. An operator-shaped command that makes the CLI feel like a tool rather than an HTTP client.
- **CLI: `darklab session token-info / revoke`.**
  - Token lifecycle from the CLI, gated on the current token having a `tok_` scope. Avoids forcing operators back to the browser to manage their own keys.

### Atlas Enhancements
- **Future**
  - Entity graph view (visual link map across hosts, domains, hashes, CVEs).
  - Auto-promote rules — entities matching saved patterns auto-promote into a project.
  - Time-travel view: "what did the Atlas look like a week ago?" using retained snapshots.
  - Side-by-side entity comparison (their runs, findings, intel snapshots).
  - Cross-session Atlas view for operators managing multiple sessions or shared infrastructure.
  - Atlas import from external triage tools.

### Future Project Workspace enhancements
- **Security and lifecycle**
  - Add parallel PATCH routes for partial project and target updates if the project workspace API ever becomes more than a trusted browser-only surface.
- **Capture, tagging, and navigation**
  - Add a compact project switcher near the prompt with recently used projects and a Create New action.
- **Future-state mobile polish**
  - Consider swipe gestures for target and finding rows only after overflow-menu interactions are shipped and tested.
- **Findings and comparison**
  - Extend comparison beyond run-to-run finding/artifact diffs to snapshots and package artifacts.
- **Evidence packages**
  - Materialize evidence package archives at creation time if byte-for-byte repeat downloads become important.
  - Make package presets config-driven so new bundle profiles, such as internal review or external handoff, can be added without code changes.
  - Add richer per-finding remediation or verification fields if findings evolve beyond raw output capture.
  - Add richer target references in package exports, including derived relationships that are not directly visible in selected finding text.
  - Add richer provenance metadata and round-trip import hints for labels, notes, targets, findings, and packages.
  - Explore fuller direct template reuse for package run transcript pages without reintroducing app-hosted asset links.
  - Add generated re-package names that preserve the original selection while incrementing the package label or timestamp.

### Future interactive PTY enhancements
- **Future lifecycle and resilience**
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
  - The reader loop polls Redis every 200 ms via `xread block=1` for control events. With many concurrent PTYs this is wasted ops. Switch the control channel to Redis Pub/Sub (or a longer block window) so idle PTYs cost zero ops while output latency stays unaffected.
  - Skip the unconditional `_store_pty_snapshot(run, force=True)` in `pty_run_snapshot` when the request hits the worker that owns the PTY. The route already returns the live in-memory payload to the caller, and the next reader-loop tick will publish to Redis naturally; the extra Redis SET costs one round-trip per attach for cross-worker freshness that is rarely consumed.
  - Consider pausing xterm rendering for hidden-tab PTYs. xterm.js running in a `display: none` panel still processes writes and grows scrollback (capped at 1000 lines, but still wasted CPU). Either drop incoming `output` chunks into the modal only when visible (queue and replay on tab focus) or accept the cost as small enough to ignore — worth measuring under a long-running ffuf in a backgrounded tab before spending engineering on it.

## Research

No research items are currently tracked.

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Tool-specific guidance
- Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `naabu`, or `nuclei`.
- Good fit for the existing help / FAQ / welcome surfaces.
- Merge this with onboarding and command hints into a broader user guidance layer:
  - command-specific caveats
  - what to expect while a tool runs
  - examples of when to use one tool vs another

### Command catalog future-state
- Add `commands search <term>` for roots, descriptions, categories, examples, and flag text.
- Add `commands --json` or `commands info --json <root>` for debugging, export, and future UI reuse.
- Add optional richer registry fields such as `details`, `notes`, `common_flags`, or `gotchas` when a flag or tool needs more than a short autocomplete description.
- Add command-specific guidance for web-shell behavior, including injected safe defaults, quiet-running tools, generated Files output, and managed session state.
- Add autocomplete side previews later: when a root, subcommand, or flag is highlighted, show the command description or flag note in a small help pane.
- Add hover/focus cards for FAQ chips once the command-details modal behavior has settled.
- Consider including pipe helpers in a separate “Pipes” section once command catalog UX exists.
- Consider linking command catalog entries to real `man` output where available, while keeping app-native allowed-subset details primary.

### Command outcome summaries
- For selected tools, generate short app-native summaries below the raw output. Security tool output is high-volume; a clear findings layer is what separates a purpose-built tool from a raw terminal.
- Keep raw output primary — the summary is additive, never a replacement.
- Start narrow: nmap (open ports + service table), dig (records returned), curl (status code + redirect chain), openssl s_client (cert expiry + trust chain).
- The structured output model (see Architecture) is the right long-term foundation. Build this feature so it can move onto that model later instead of requiring it up front.

### Transcript noise classification
- Future cleanup for saved command output across both normal runs and interactive PTY runs.
- Avoid broad duplicate-line removal because repeated lines can be meaningful findings for some tools.
- Classify known progress/status/redraw lines before history/search/finding classification, starting with high-noise shapes from tools like `masscan`, `ffuf`, `nuclei`, and ProjectDiscovery tools that emit frequent status updates.
- Keep real newline-terminated findings and normal scrollback untouched.
- For interactive PTY runs, keep the final visible frame available so users can still inspect the last terminal state, even when progress/status redraw lines are excluded from searchable saved transcript text.
- For normal runs, prefer command-specific noise classifiers over global suppression so raw output stays faithful while search, findings, summaries, and previews become easier to use.

### Run comparison enhancements
- Future-state enhancements after the shared split-pane comparison flow has real use.
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
  - Snapshot/permalink compare if the run-vs-run model continues to work well.
  - `Export comparison` once share/export packages have a stable artifact model.
- Future UX/testing:
  - Consider date-range filters in the manual compare picker if day grouping plus `Load More` is not enough for deep history.
  - Broaden Playwright coverage for edge/mobile layout paths after the UI settles.
  - Add focused large/noisy comparison regression coverage if real-world outputs expose performance issues beyond current backend and unit coverage.

### Bulk history export and share
- The history drawer can delete all, delete non-favorites, and use visible-page multi-select for bulk project add/remove plus selected-item delete. Bulk export to JSONL/txt and bulk share would close the remaining gap when packaging selected history items after an engagement.

### Autocomplete suggestions from output context
- When a previous command's output is in the active tab, `| grep` completions could suggest patterns already present in that output — IP addresses, hostnames, status codes, CVE strings — as candidates alongside the generic flag list.
- Narrow but would make the pipe stage feel predictive rather than generic.

### Mobile share ergonomics
- The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
  - save/share actions tuned for one-handed use
  - clearer copy/share/export affordances inside the mobile shell
  - better share handoff after snapshot creation

### PWA install and service-worker push
- Make the mobile shell installable and deliver completion pings via web-push so phone users get notified when the tab is closed or the device is asleep. Today mobile notifications are intentionally hidden because foreground-only notifications are not useful on phones.
- **Entry-level scope:**
  - Add a manifest, app icons, and a small service worker so users can "Add to Home Screen" and launch into a standalone mobile shell.
  - VAPID-signed web-push subscription tied to the active session token; subscribe and unsubscribe from the Options sheet.
  - Reuse the run-complete event hook from the outbound-notifications surface so push is just another channel.
- **Architecture:**
  - New `app/static/manifest.webmanifest`, icon assets under `app/static/icons/`, and `app/static/sw.js` registered from `app.js` only when the runtime supports it.
  - New `WebPushChannel` in the notifications service; VAPID keys stored as operator config; per-session-token subscription endpoint at `/session/push/subscribe`.
  - Service worker scope is intentionally narrow — render notifications and open the tab on click; no caching of dynamic transcript content so users never see stale output.
  - Gotchas: iOS Safari requires the user to install the PWA before push works; document this in CONFIGURATION.md.

### Engagement report builder
- Turn a project workspace into a styled markdown/PDF engagement report — methodology, scope, targets, findings table, remediation notes, screenshots. Evidence packages today are raw bundles; this is the narrative deliverable a customer reads.
- **Entry-level scope:**
  - One-click "Generate report" from a project, with an editable cover page (engagement name, dates, operator, contact).
  - Sections auto-populated from project data: targets, findings grouped by severity, included runs (with permalinks), artifacts.
  - Output formats: markdown source plus rendered HTML and PDF, reusing the existing export pipeline.
  - Operator-editable section templates in a new `app/conf/report_templates.yaml`.
- **Architecture:**
  - New `app/services/reports/` service composing project-workspace data with existing finding/run/artifact serializers; templating via Jinja autoescape (aligns with the package HTML rendering follow-up in Open TODOs).
  - Adds `GET/POST /projects/<id>/report` to `app/blueprints/projects.py`.
  - Browser surface: a "Report" tab inside the existing Projects modal; renderer reuses `export_html.js` and `export_pdf.js`.
  - Honors share-redaction defaults; the draft is always previewed before download so this stays additive to evidence packages, not a replacement.

---

## Architecture

### Unified terminal built-in lifecycle
- Browser-owned built-ins (`theme`, `config`, and `session-token`) need browser execution for DOM state, local storage, clipboard, and transcript-owned confirmations, while server-owned built-ins naturally flow through `/runs`.
- The long-term cleanup target is one terminal-command lifecycle after execution:
  - normalize built-in output into a shared result shape
  - apply pipe helpers against that shape
  - mask sensitive command arguments once
  - render transcript output once
  - persist server-backed history once
  - load recents and prompt history from the same saved run model
- Keep execution ownership separate where it matters, but remove duplicated recents/history/pipe/persistence glue so browser-owned and server-owned built-ins cannot drift.

### Plugin-style helper command registry
- Turn the built-in command layer into a cleaner extension point for future app-native helpers.

### Lightweight Jinja base template
- `index.html`, `permalink_base.html`, and `diag.html` now all share the same ~10 lines of `<head>` bootstrap (charset, viewport, color-scheme meta, favicon, `fonts.css`, `styles.css`, theme var includes, and the two vendor scripts). With three templates the duplication is starting to pay for the indirection.
- A `base.html` factoring out the common `<head>` and `data-theme` body attribute would prevent drift and make adding a fourth page type trivial.

### Interactive PTY transport future-state
- Revisit whether the current Redis-brokered SSE plus POST input/resize transport should move to WebSockets after real use.
- The current model keeps deployment simple and avoids a WebSocket runtime, but a bidirectional socket could reduce input latency and simplify the modal terminal stream once PTY usage grows.
