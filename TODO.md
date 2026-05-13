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

- **History multi-select bulk actions**
  - **Scope**
    - Add visible-page-only multi-select for run rows in the History drawer. Selection does not span pagination, search, filters, or type changes in v1.
    - Bulk actions cover **delete**, **add to active project**, **add to project**, and **remove from project**.
    - Keep all three project actions available for mixed selections so users can normalize selected runs regardless of current link state.
    - Make project actions idempotent: already-linked runs are skipped during add, already-unlinked runs are skipped during remove, and neither case fails the whole bulk action.
    - Reuse existing UI primitives for all controls: shared `btn` classes, `chrome-row` row behavior, `dropdown-surface` / save-menu patterns, app-native selects, `showConfirm`, `bindPressable`, focus helpers, and existing mobile sheet/dropdown placement rules.
  - **Phase 1 - Selection state and row rendering**
    - Add a small History selection model keyed by visible run id, storing the run object needed by bulk actions.
    - Add a **Select mode** toggle beside **Select all**, **Clear selection**, and a top-level **Actions** menu.
    - Show row checkboxes only when select mode is enabled.
    - In select mode, make clicking a run row toggle selection instead of opening Run Details. Row-level buttons, row action menus, restore, permalink, compare, and delete should keep their existing behavior and stop propagation.
    - Keep select mode enabled across page/filter/search changes, but clear selected rows when the visible result set changes.
  - **Phase 2 - Bulk toolbar behavior**
    - Render selected count in the toolbar, such as `3 selected`.
    - Disable **Select all**, **Clear selection**, and **Actions** when there are no visible selectable rows or no selected rows as appropriate.
    - **Select all** selects only visible run rows on the current page.
    - **Clear selection** clears the current visible selection without closing select mode.
    - After successful bulk actions, clear selected rows but leave select mode enabled.
  - **Phase 3 - Batch backend routes**
    - Add batch project link and unlink routes so ownership checks, skipped counts, and partial-success reporting stay server-owned.
    - Suggested add route: `POST /projects/<project_id>/links/bulk` with `{"entity_type":"run","entity_ids":["run-1","run-2"]}`.
    - Suggested remove route: `DELETE /projects/<project_id>/links/bulk` with the same payload shape.
    - Return count groups such as `added`, `already_linked`, `removed`, `not_linked`, `not_found`, and `rejected`.
    - Add a bulk history delete route for selected visible runs rather than firing one request per row.
  - **Phase 4 - Bulk project actions**
    - **Add to active project** resolves the current active project and posts all selected run ids to the batch link route.
    - **Add to project** reuses the existing project picker, including active-project-first ordering, then posts all selected run ids to the batch link route.
    - **Remove from project** removes selected runs from one chosen project. If selected runs are linked to multiple projects, show a project picker populated from their linked projects. Do not remove a run from every linked project unless a separate explicit action is added later.
    - Refresh History and Projects state after successful bulk link/unlink so row menus and project views reflect the new state immediately.
  - **Phase 5 - Bulk delete**
    - Confirm destructive deletes with `showConfirm`, including a count such as `Delete 5 selected runs?`.
    - Delete only selected run rows in v1. Snapshot multi-delete can be a follow-up if needed.
    - After delete, refresh the current History page. If the page becomes empty and a previous page exists, move back one page.
  - **Phase 6 - Feedback and tests**
    - Show concise result feedback such as `Added 4 runs to darklab.sh - 2 already linked` or `Removed 3 runs from darklab.sh - 1 was not linked`.
    - Add backend coverage for idempotent add/remove, cross-session rejection, missing ids, partial success, and bulk delete ownership checks.
    - Add browser unit coverage for select mode, row-click selection, select all visible, clear selection, toolbar disabled states, project picker flows, and immediate menu refresh after bulk actions.
    - Add one desktop and one mobile Playwright flow covering selection, project add/remove, and toolbar usability.

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
  - Consider active-tab compare, snapshot/permalink compare, package-artifact compare, and export/share comparison once the run-vs-run model has more production use.
  - Add focused large/noisy output regressions if real scanner output exposes performance or alignment gaps beyond the current backend, Vitest, and Playwright coverage.

## Research

No research items are currently tracked.

---

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

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

- **Scheduled and recurring runs**
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

- **Watchers (change-detection monitors)**
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

- **Outbound notifications (webhooks, Slack, Discord, email)**
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

- **Encrypted secrets vault**
  - First-class store for tool API keys (Shodan, VirusTotal, WPScan token, custom auth headers) that get injected as env vars into commands declared in `commands.yaml` as needing them. Distinct from session command variables, which are plaintext convenience and are visible in typed transcripts.
  - **Entry-level scope:**
    - Operator generates a per-deployment master key in config; user-facing CRUD via `secret set NAME`, `secret list`, `secret unset NAME` built-ins and an Options-modal panel.
    - Values are AES-GCM encrypted at rest, never echoed, never expanded into typed history.
    - `commands.yaml` declares the env var a tool consumes (for example `WPSCAN_API_TOKEN`, `SHODAN_API_KEY`); the registry injects only the secrets that match.
    - Audit log records which run consumed which secret name (never the value).
  - **Architecture:**
    - New `app/services/secrets/` service with key wrap/unwrap helpers and a SQLite `secrets` table (session_token, name, ciphertext, nonce, consumer_envs).
    - Crypto via Python's `cryptography` library; master key sourced from `SECRETS_MASTER_KEY` env with a documented init flow in CONFIGURATION.md.
    - Injection happens in the runtime-environment build path in `app/services/commands/registry.py`, alongside the existing `XDG_CONFIG_HOME` Files redirect, and is logged through the structured log channel.
    - Built-ins join the session built-in family. Secrets are strictly env-only — never expanded as `$VAR` — so they cannot leak into shared transcripts, snapshot exports, or permalinks.

- **Headless API and CLI client**
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

- **PWA install and service-worker push**
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

- **Engagement report builder**
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

- **Prometheus `/metrics` endpoint**
  - Operator observability beyond `/diag`: active-run gauge, exit-code distribution, per-tool runtime histograms, rate-limit rejections — scrapeable for Grafana.
  - **Entry-level scope:**
    - New IP-gated `/metrics` route exposing OpenMetrics-format text. Same IP allowlist as `/diag` so it is not internet-exposed by default.
    - Initial metric set:
      - `darklab_active_runs`
      - `darklab_run_total{tool,exit_code}`
      - `darklab_run_duration_seconds{tool}` (histogram)
      - `darklab_rate_limit_rejections_total`
      - `darklab_pty_active`
      - `darklab_workspace_quota_bytes{state}`
  - **Architecture:**
    - Use the `prometheus_client` Python library with a multiprocess collector compatible with Gunicorn workers (`PROMETHEUS_MULTIPROC_DIR` writable inside the container).
    - Counters/histograms are updated from the run-finalize path in `app/blueprints/run.py`, the rate limiter in `app/extensions.py`, and the PTY service.
    - Route lives next to `/diag` in `app/blueprints/assets.py`; documented in CONFIGURATION.md alongside the existing diagnostics surface.

- **Findings triage inbox**
  - Folded into the Session Entity Atlas idea below as phase 4 (the Findings tab becomes the inbox surface). Kept here so the standalone scope/architecture stays reviewable if the Atlas does not land first.
  - Cross-run, cross-project queue of every finding and warning the classifier has emitted, with status (new / triaged / confirmed / false-positive) and a "seen before in run X" dedupe link. Today findings live per-run; this surfaces patterns over time.
  - **Entry-level scope:**
    - A Findings modal listing all classifier-emitted findings and warnings across saved runs for the active session, with filters for severity, status, tool, and project.
    - Per-finding actions: mark triaged, confirm, mark false-positive, jump to source run, optionally pin into a project as a structured finding.
    - Dedupe: identical finding signature across runs collapses into one row with a count and first/last-seen timestamps.
  - **Architecture:**
    - New `app/services/findings/` service that materializes per-run finding records from `app/core/output_signals.py` into a `findings_inbox` SQLite table at run-finalize time. Each row carries a stable signature hash for dedupe.
    - New `app/blueprints/findings.py` for list, filter, and status routes.
    - Browser surface: new `app/static/js/features/findings/findings_inbox.js` and `app/static/css/features/findings.css`; entry points from the History drawer, Run Details modal, and Projects modal.
    - The natural consumer of the structured output model in Architecture: design the inbox schema so it can move onto richer line/event data later without breaking the dedupe signature.

- **External intel service integrations**
  - Connect darklab_shell to passive recon and reputation services (Shodan, VirusTotal, GreyNoise, and friends) so scanner output and findings can be enriched without leaving the shell. Existing tools answer "what does this host expose right now?"; intel services answer "what does the rest of the internet already know about it?".
  - **v1 ship list — Shodan, VirusTotal, GreyNoise**
    - Rationale:
      - Shodan covers passive ports, banners, and historical CVE data.
      - VirusTotal covers file hashes, URLs, domains, and passive DNS.
      - GreyNoise classifies whether an IP is internet background noise or targeted.
      - Together they answer most "should I care about this host?" triage questions.
    - Ship in two passes:
      - Pass 1 (CLI wrapper): install `shodan`, `vt-cli`, and a `greynoise` CLI in the Dockerfile and register allowed subcommands/flags in `commands.yaml` with declared env-consumer slots (`SHODAN_API_KEY`, `VT_API_KEY`, `GREYNOISE_API_KEY`). Users get the same allowlist, autocomplete, history, Files, and rate-limit behavior as every other tool.
      - Pass 2 (app-native built-in): add an `intel ip|domain|hash` built-in backed by Python provider modules so users have one uniform output card across all three providers.
    - Hard dependencies:
      - Encrypted secrets vault (existing Ideas entry) — every provider needs an API key, and a parallel per-integration ciphertext path should not exist.
      - Provider abstraction (below) — landed once, reused by every future provider.
    - Architecture:
      - New `app/services/intel/` service with a `Provider` base class and `shodan.py`, `virustotal.py`, `greynoise.py` modules implementing `lookup_ip`, `lookup_domain`, `lookup_hash`, `lookup_cve` as applicable.
      - Per-provider token-bucket rate limiter plus a Redis-backed response cache with provider-tunable TTL (passive intel data changes slowly).
      - Audit log of which run hit which provider with which entity, written through the structured log channel; never logs the response body.
      - Built-in lives in a new `app/services/commands/builtins_intel.py`; browser surface is a uniform `intel` result card rendered by a new `app/static/js/features/intel/intel_card.js`.
      - Sharing: intel response bodies are treated as raw-only and excluded from snapshot permalinks by the existing share-redaction baseline.
  - **Cross-cutting infrastructure to land once, before or with v1**
    - Encrypted secrets vault — already an Ideas entry above; required for every integration here.
    - Provider abstraction (`app/services/intel/providers/`):
      - `Provider` base class with shared lookup methods.
      - Per-provider token-bucket rate limiter.
      - Redis-backed response cache.
      - Run/entity audit log.
    - Entity-aware output classifier hooks:
      - Extend `app/core/output_signals.py` to surface extracted IPs, domains, hashes, and CVEs as structured events.
      - Downstream features (sidecar panel, findings enricher, pipe helpers) all consume the same event stream.
      - Aligns with the structured output model called out in Architecture below.
  - **Integration patterns (each can land independently once the shared infra exists)**
    - CLI wrapper — install vendor CLI in the Dockerfile, register in `commands.yaml`, inject the secret. Lightest path; first home for Shodan, VT, Censys, BuiltWith, urlscan.
    - App-native `intel` built-in — single command (`intel ip|domain|hash|cve`) aggregating multiple providers behind one uniform output card via `app/services/intel/`.
    - Sidecar enrichment panel — opt-in passive lookups fire alongside a scanner run; render Shodan ports, GreyNoise verdict, IPinfo ASN, VT reputation in a collapsible panel next to the transcript. Off by default per session; auditable per run.
    - Findings enricher — when the classifier extracts an entity, the findings inbox auto-attaches enrichment from relevant providers, turning the inbox from a queue into a triage workbench.
    - Workflow steps — Workflows can chain native tools with intel lookups (for example `subfinder → dnsx → pd-httpx → virustotal-domain → urlscan`).
    - Pipe helper enrichment — new `| enrich-shodan` / `| enrich-greynoise` post-filters that walk stdin for entities and append one annotation per line. Fits the existing synthetic pipe-helper model in `app/services/commands/postfilters.py`.
    - Project workspace enrichment — when a host/domain is added as a project target, optionally pre-fetch passive snapshots and store them as workspace artifacts under `/intel/<target>/`, becoming part of evidence packages and the engagement report builder idea.
  - **Future provider candidates (after v1)**
    - Host/port intel — Censys, BinaryEdge, ZoomEye.
    - URL/file reputation — urlscan.io, Hybrid Analysis, Triage, Joe Sandbox.
    - Passive DNS / asset discovery — SecurityTrails, AlienVault OTX, Chaos (ProjectDiscovery; integrates naturally with the already-shipped subfinder/dnsx/pd-httpx via env var), crt.sh (free, no key needed).
    - Threat intel / reputation — AbuseIPDB, ThreatFox, MISP.
    - ASN / WHOIS / geo — IPinfo, Team Cymru, BGPView (free).
    - Breach / credential exposure — HaveIBeenPwned, DeHashed, IntelX.
    - Tech detection — BuiltWith, Wappalyzer CLI.
    - CVE / vuln data — NVD, Vulners, ExploitDB.
  - **Anti-patterns to avoid**
    - Do not call live intel APIs during a scanner run by default. It costs API quota and surprises users; sidecar enrichment must be opt-in per session or project.
    - Do not log API keys, full response bodies, or raw entity lists into shared transcripts, snapshot permalinks, or exports. Treat intel response bodies as raw-only in the share-redaction baseline.
    - Do not reimplement what a vendor CLI already does well — wrap it, inject the secret, log usage, move on.

- **Session Entity Atlas (entity-first triage surface)**
  - Reframe darklab_shell's exploration model so entities (findings, hosts/IPs, domains, hashes, CVEs, URLs) become the primary navigation primitive — not runs, not projects. Runs become the *source* of entities. Projects become a *curated subset* of entities for engagement work. The active session token owns the entity graph.
  - **The gap it closes:**
    - Every run already produces classified findings, but the rich exploration UI lives inside Projects. Runs not linked to a project surface findings only inside Run Details with no aggregation, triage state, or cross-run pivot.
    - The proposed `intel` built-in widens the gap because intel data is inherently entity-shaped — a Shodan record is about an IP, not the nmap run that produced it. Without an entity-first surface, Findings, Intel, and Projects each grow parallel triage modals that show fragments of the same picture.
    - Project membership stops being a gate on tooling. Users can recon casually and curate later without losing the engagement-grade Projects surface.
  - **UI shape:**
    - New top-level **Atlas** surface with the same prominence as History — desktop left-rail entry, mobile menu item, keyboard shortcut. Not a stacked modal.
    - Atlas tabs across the top: Findings, Hosts/IPs, Domains, Hashes, CVEs, URLs. Each tab is a filterable, sortable list of distinct entities extracted across every saved run for the active session token.
    - Entity Detail side sheet opens from any row or from a tagged transcript token:
      - Identity strip — type, canonical value, first/last seen, run count.
      - Intel snapshot card — Shodan / VT / GreyNoise / IPinfo / etc., with explicit refresh so cache state is visible.
      - Source runs list — every run that mentioned the entity, with command, tool, finding count, jump-to-line link.
      - Findings extracted on the entity across all runs.
      - Labels and notes via the existing `ui_entity_metadata.js` helper.
      - Promote-to-project action.
    - Transcript ↔ Atlas wiring:
      - Tagged tokens become click targets; click opens entity detail; long-press / right-click exposes the full action menu (label, note, promote, copy, lookup intel).
      - Hover popover on tagged tokens shows the high-signal summary (GreyNoise verdict, Shodan port count, VT positives) without leaving the transcript.
      - "See in run" inside entity detail jumps back to the source line in the original run.
  - **Phased rollout:**
    - Phase 1 — Read-only Atlas: render Findings, Hosts, Domains, Hashes, CVEs tabs from data already classified by `app/core/output_signals.py`. Rows click into their source run; no new metadata yet. Ships value alone.
    - Phase 2 — Entity Detail: aggregate across runs, attach labels/notes, dedupe via stable signature, "see in run" navigation.
    - Phase 3 — Intel attachment: explicit `intel` results, sidecar enrichment, and pipe-helper enrichment all write into entity-keyed intel rows; entity detail renders them.
    - Phase 4 — Findings triage state: promote the Findings triage inbox actions (new / triaged / confirmed / false-positive, signature dedupe) onto the Findings tab. The standalone Findings triage inbox idea folds in here instead of shipping as its own surface.
    - Phase 5 — Project linking: adding to a project becomes a tag on the entity row; project workspace, evidence packages, and engagement report builder all read from the same entity store.
  - **Architecture:**
    - Storage:
      - New `entities` table keyed by (session_token, type, canonical_value, signature_hash) for stable dedupe across runs.
      - `entity_run_links` (entity_id, run_id, first_seen, last_seen, occurrence_count) so cross-run aggregation is a single join.
      - `entity_intel_snapshots` (entity_id, provider, payload_json, fetched_at, ttl) keyed by provider so refresh and quota stories stay tractable.
      - `entity_project_links` (entity_id, project_id) replaces a per-project copy of entity rows.
    - Services:
      - New `app/services/atlas/` service with materialization helpers that run at run-finalize time, consuming entity events surfaced by the entity-aware output classifier hooks called out under the intel integrations idea.
      - Entities are extracted lazily and deduped via stable signature so long sessions do not balloon SQLite. Materialization is idempotent so re-finalizing a run does not double-count.
      - Reuses the existing label/note helpers, run-comparison structured-finding model, and intel provider modules.
    - Routes:
      - New `app/blueprints/atlas.py` for list, filter, detail, and entity-mutation routes (labels, notes, project links, intel refresh).
      - Existing Findings, Run Details, and Projects routes read from the same entity store rather than maintaining parallel finding queues.
    - Browser surface:
      - New `app/static/js/features/atlas/` for the Atlas surface, tab list rendering, entity detail side sheet, transcript hover popover, and tagged-token action menu.
      - New `app/static/css/features/atlas.css`.
      - Run Details, Projects, and the `intel` result card all link into entity detail rather than re-rendering entity data locally.
    - Sharing and exports:
      - Entity rows themselves never appear in snapshot permalinks; only the source run transcript does. The existing share-redaction baseline already covers raw transcript content.
      - Engagement report builder (separate idea) reads from the entity store for "targets", "findings", and "intel observations" sections, replacing per-project ad-hoc aggregation.
  - **Anti-patterns to avoid:**
    - Do not build the Atlas as yet-another-modal stacked over History. It needs first-class chrome treatment (rail entry, shortcut, mobile menu item) or it will be invisible.
    - Do not duplicate entity metadata between Atlas and Projects. Project membership is a tag on the entity row; labels, notes, and intel live on the entity.
    - Do not materialize entities eagerly for every line of output. Extract lazily from classifier events at finalization and dedupe with stable signatures so SQLite cost scales with distinct entities, not output volume.
    - Do not gate intel data on the user calling `intel` explicitly. Sidecar enrichment, pipe-helper enrichment, and explicit `intel` calls must all write through the same per-entity intel rows so a user who never types `intel` still sees enriched data.
    - Do not break runs that have no findings. Utility commands and failed commands produce zero entities; the Atlas must treat that as the normal case, not an empty state worth surfacing.
  - **Relationships to other ideas:**
    - Folds in the **Findings triage inbox** idea as phase 4 — the inbox becomes the Findings lens on the Atlas, not a separate surface.
    - Provides the natural home for **External intel service integrations** — entity detail is where intel snapshots live; sidecar enrichment, the `intel` built-in, and pipe-helper enrichment all write here.
    - Consumes the entity-aware output classifier hooks called out under intel integrations and the **structured output model** under Architecture.
    - Reframes **Project workspaces** as a curation layer over the entity store rather than the only triage surface; project linking is a tag, not a copy.

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
