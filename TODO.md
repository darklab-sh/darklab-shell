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
  - [Scheduled and recurring runs](#scheduled-and-recurring-runs)
  - [Watchers (change-detection monitors)](#watchers-change-detection-monitors)
  - [Outbound notifications (webhooks, Slack, Discord, email)](#outbound-notifications-webhooks-slack-discord-email)
  - [Headless API and CLI client](#headless-api-and-cli-client)
  - [PWA install and service-worker push](#pwa-install-and-service-worker-push)
  - [Engagement report builder](#engagement-report-builder)
- [Architecture](#architecture)
  - [Structured output model](#structured-output-model)
  - [Unified terminal built-in lifecycle](#unified-terminal-built-in-lifecycle)
  - [Plugin-style helper command registry](#plugin-style-helper-command-registry)
  - [Lightweight Jinja base template](#lightweight-jinja-base-template)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

- **Project workspace navigation polish**
  - Add a terminal-native `project rename <name-or-id> <new-name>` command so CLI users can rename projects without opening the modal.
  - Show run, finding, artifact, and package counts on project-list rows so project scale is visible before opening each project.
  - Prefetch finding counts and severity distribution so tab labels can show useful state such as unreviewed/high counts without opening the tab.
- **Evidence package export hardening**
  - Add redacted text/JSON derivatives for safe artifact types before allowing raw artifact inclusion in redacted packages.
  - Add richer redaction previews and per-item redaction warnings for package creation.
  - Add async package build progress for large Full Archive exports so long builds do not feel like stalled requests.
  - Move package HTML rendering toward shared Jinja autoescape paths so package output escaping is template-owned instead of manual per-call escaping.
- **Interactive PTY lifecycle and operator visibility**
  - Auto-displace prior live attaches when a new browser client attaches to the same PTY run. When `active_run_claim_owner` flips the internal ownership marker to a different `client_id`, publish a single `displaced` event on the PTY stream so the prior tab can close its modal cleanly and append one notice such as `[interactive PTY moved to another tab]`. Skip same-client reconnects so the event only fires when the live view genuinely moves to a different browser context.
  - Surface snapshot age on the reattach payload. `_load_pty_snapshot` strips `created_at` before returning, so the frontend cannot tell whether the snapshot is fresh or 20+ seconds stale. Return the age and let the frontend show `[reattached - snapshot was Ns old]` when it crosses a threshold.
  - Move `_PTY_INPUT_MAX_BYTES`, `_PTY_BUFFER_LIMIT`, `_PTY_CONTROL_POLL_SECONDS`, `_PTY_SNAPSHOT_FALLBACK_ENTRY_LIMIT`, and similar tunables to config so deploys can tune without a rebuild.
  - Add PTY metrics covering concurrent PTY count, average and p95 duration, total input bytes, dropped input bytes, and control queue depth. Expose them through the existing `/diag` surface so operators have visibility comparable to other run paths.

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

- **Project route boilerplate** — reduce repeated `projects.py` route boilerplate with small serialization/404 helpers.

---

## Feature Enhancements

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

### Scheduled and recurring runs
- Cron-style scheduler so any command or workflow can fire on a cadence (daily nmap, hourly httpx, weekly subdomain sweep) without keeping the tab open. Nothing in the app is currently time-driven.
- **Entry-level scope:**
  - Save a schedule from any command or workflow with a cron expression or a small cadence preset (hourly/daily/weekly).
  - Schedules belong to the active session token and migrate with it.
  - Fired runs land in normal history tagged `scheduled` with the originating schedule ID.
  - List/pause/delete schedules through a new `schedule` built-in plus a Schedules modal beside Workflows.
- **Architecture:**
  - New `app/services/scheduler/` service backed by APScheduler (or a small Redis sorted-set tick loop) running in a dedicated `scheduler` process so worker restarts do not lose ticks.
  - SQLite `schedules` table: id, session_token, command/workflow ref, cron, enabled, last_run_at, next_run_at.
  - At fire time the scheduler enqueues through the existing `/runs` broker under the owning session so allowlist, deny-prefix, registry rewrite, and history persistence are reused unchanged.
  - New `app/blueprints/schedules.py` for CRUD; new `schedule` handler in the session built-in family; new `app/static/js/features/schedules/` for the modal and runtime autocomplete.
  - Gotchas: cron string validation, surfacing missed fires after a container restart, and tearing down schedules when their session token is revoked.

### Watchers (change-detection monitors)
- Pair a recurring command with a stored baseline and notify only when output diverges (new open port, new subdomain, new finding signature, TLS cert change). Builds on the run-comparison diff engine but exposes it as a persistent first-class object, not a one-off compare.
- **Entry-level scope:**
  - Create a watcher from any completed run ("watch this nmap for new open ports").
  - Watchers reuse the scheduler service to re-run on a cadence.
  - Each fire stores a structured diff against the prior accepted baseline; notifications fire only on non-empty diffs.
  - A Watchers modal shows status (ok / changed / firing), last fire, last diff, with accept-new-baseline and pause actions.
- **Architecture:**
  - New `app/services/watchers/` service composing the scheduler service with the existing comparison helpers in `app/services/runs/comparison.py`.
  - SQLite `watchers` table: id, session_token, command, schedule_ref, baseline_run_id, last_run_id, last_diff_summary, state.
  - Reuses the structured finding/signal model when present; falls back to textual added/removed line diffs otherwise. The structured output model called out in Architecture is the natural long-term substrate.
  - Fires through the new outbound-notifications surface so a watcher hit can reach Slack/email/push without duplicating delivery code.

### Outbound notifications (webhooks, Slack, Discord, email)
- Run-complete, finding-classified, and watcher-fired events fan out to external channels per session or per project. Existing notifications are browser-foreground only; this closes the loop for solo operators running long scans away from the tab.
- **Entry-level scope:**
  - Configure one or more channels per session token. Start with a generic JSON webhook; layer Slack, Discord, and SMTP email on the same channel abstraction.
  - Triggers: run-complete (per exit-code policy), finding-classified, watcher-fired, scheduled-run-failed.
  - Per-channel mute plus a global "do not disturb" toggle.
  - Notification body uses only the command root, matching the existing browser desktop-notification policy that intentionally avoids exposing arguments or token values.
- **Architecture:**
  - New `app/services/notifications/` service with a `Channel` base class and `WebhookChannel`, `SlackChannel`, `DiscordChannel`, `EmailChannel` implementations. SMTP is operator-config-gated in `app/conf/config.yaml`.
  - SQLite `notification_channels` table (per session token, encrypted secret column for webhook URL / bot token) and `notification_events` for delivery audit and retry.
  - Hook points: run finalization in `app/blueprints/run.py`, watcher fire path, scheduler error path.
  - Browser surface: Options modal "Notifications" section; new `app/static/js/features/preferences/notification_channels.js`.
  - Secret storage rides on the encrypted-secrets-vault idea below rather than introducing a parallel ciphertext path.

### Headless API and CLI client
- Stable REST endpoints plus a thin `darklab` CLI, authenticated by an existing session token, that can launch runs, poll history, and pull artifacts from CI pipelines or local scripts.
- **Entry-level scope:**
  - REST: `POST /api/v1/runs`, `GET /api/v1/runs/<id>`, `GET /api/v1/runs/<id>/stream` (SSE), `GET /api/v1/history`, `GET /api/v1/history/<id>/output`, authenticated via `Authorization: Bearer tok_...`.
  - CLI: `darklab run "nmap …"`, `darklab tail <id>`, `darklab history`, `darklab download <id> [--workspace]`.
  - Same allowlist, deny-prefix, registry-rewrite, and rate-limit bucket as the browser path so headless use cannot bypass per-session limits.
- **Architecture:**
  - New `app/blueprints/api_v1.py` reusing the existing run broker, history service, and validation; OpenAPI/JSON schema published at `/api/v1/openapi.json` for clients to consume.
  - CLI ships as a tiny Python package under `tools/darklab_cli/` with its own `pyproject.toml`; communicates only via the REST blueprint, no shared imports with the server runtime.
  - Output streaming reuses the broker SSE path so multi-worker reattach already works.
  - Documented in a new `docs/api.md` plus a CONFIGURATION.md section.

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

### Structured output model
- Preserve richer line/event details consistently for all runs.
- This would improve search, comparison, redaction, exports, and permalink fidelity.
- Command outcome summaries are buildable without this foundation, but design them so they can move onto the structured model later. Summary parsers should consume structured line events, not re-parse raw text forever.

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
