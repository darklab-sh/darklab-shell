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

- **Headless API and CLI client**
  - Goal
    - Ship a stable REST surface plus a thin `darklab` CLI so runs, history, and artifacts are reachable from CI pipelines and local scripts without driving the browser shell. Authenticates with the existing `tok_` session-token model; reuses the run broker, history service, allowlist, deny-prefix, registry rewrite, and per-session rate-limit bucket so headless callers cannot bypass any browser-path constraint.
  - REST surface (`app/blueprints/api_v1.py`, mounted at `/api/v1`)
    - `POST /api/v1/runs` — start a run. Body `{"command": "...", "project_id": null}`. Returns `{"id": "...", "status": "running", "stream_url": "...", "history_url": "..."}`.
    - `GET /api/v1/runs/<id>` — current status, exit code when complete, byte/line counts.
    - `GET /api/v1/runs/<id>/stream` — SSE output stream reusing the run broker SSE path so multi-worker reattach already works; CLI consumes via `text/event-stream`.
    - `POST /api/v1/runs/<id>/cancel` — same termination semantics as the browser cancel button.
    - `GET /api/v1/history` — cursor-paginated. Query params `cursor`, `limit` (capped at 100), `project_id`, `q`, `since`, `until`.
    - `GET /api/v1/history/<id>` — run record with redaction honored.
    - `GET /api/v1/history/<id>/output` — raw transcript text or `?format=json` for the structured envelope used by the browser.
    - `GET /api/v1/history/<id>/artifacts` — list workspace artifacts; `GET /api/v1/history/<id>/artifacts/<name>` streams raw bytes with `Content-Disposition`.
    - `GET /api/v1/projects`, `GET /api/v1/projects/<id>`, `GET /api/v1/projects/<id>/findings`, `GET /api/v1/projects/<id>/packages` — read-only first pass; write paths land in a follow-up so the MVP stays small.
    - `GET /api/v1/openapi.json` — hand-written static schema served from the blueprint, validated by a CI test that loads it through `openapi-spec-validator`.
    - `GET /api/v1/health` — unauthenticated liveness probe (no session lookup, no DB hit beyond a `SELECT 1`).
  - Auth and rate limits
    - Accept the token in `Authorization: Bearer tok_...` (canonical for headless) and fall back to `X-Session-ID: tok_...` so existing browser-style callers keep working during rollout.
    - Validate against `session_tokens`; reject anonymous UUID sessions on `/api/v1/*` so headless callers are always bound to a durable, revocable token.
    - Reuse the existing per-session rate-limit bucket; do not introduce a second bucket so CLI traffic cannot escalate beyond the browser ceiling.
    - Exempt the blueprint from CSRF (token-bearing requests don't need it) but require the auth header on every route except `/api/v1/health` and `/api/v1/openapi.json`.
  - Validation and safety
    - Command validation reuses `_validate_command_for_run` (allowlist, deny-prefix, registry rewrite, variable expansion) so the headless path cannot run anything the browser cannot.
    - Reject interactive PTY commands on the v1 surface — PTY is browser-specific (xterm.js renderer, modal lifecycle); revisit if a demand emerges.
    - Mask the same fields as the browser when serializing run/history records (`SHODAN_API_KEY`, etc.).
  - CLI client (`tools/darklab_cli/`)
    - Tiny standalone Python package with its own `pyproject.toml`; talks to the server only via the REST blueprint, no shared imports with the Flask runtime.
    - Commands
      - `darklab run "<cmd>"` — POST, then follow the SSE stream and print lines to stdout; exits with the run's exit code.
      - `darklab tail <id>` — attach to an in-flight run's SSE stream.
      - `darklab history [--project ...] [--since ...] [--limit N]` — table or `--ndjson` machine output.
      - `darklab show <id>` — run record plus first/last N output lines.
      - `darklab download <id> [--artifact NAME | --workspace] [--out DIR]` — pull one artifact or zip the run workspace.
      - `darklab cancel <id>` — POST cancel.
      - `darklab whoami` — token-info round-trip for smoke testing.
    - Configuration via env (`DARKLAB_API_URL`, `DARKLAB_TOKEN`) with optional `~/.config/darklab/config.toml` fallback; `--api-url` / `--token` CLI flags override.
    - Distribution: in-repo first, `pip install ./tools/darklab_cli`; PyPI publish is a follow-up once the surface settles.
  - Streaming and output shape
    - SSE is the canonical run-output transport; the CLI synthesizes line-oriented output from the stream.
    - For machine consumers that prefer line-delimited JSON, expose `GET /api/v1/runs/<id>/stream?format=ndjson` returning the same broker events as one JSON object per line; the CLI offers `darklab run --ndjson` to pass that through unchanged.
  - Tests (`tests/py/`)
    - `test_api_v1_runs.py` — start/cancel/status round-trip, auth rejection matrix, allowlist rejection mirrors browser behavior, rate-limit bucket shared with browser session, openapi schema validates.
    - `test_api_v1_history.py` — cursor pagination, redaction parity with browser history endpoints, artifact download MIME and `Content-Disposition`.
    - `test_api_v1_stream.py` — SSE reattach across workers (already exercised for the browser path; reuse fixtures), `?format=ndjson` shape.
    - `tools/darklab_cli/tests/` — CLI argparse routing, env/config precedence, exit-code passthrough, `--ndjson` mode against a stub server.
  - Docs
    - New `docs/api.md` covering auth, the full endpoint table, SSE event shapes, error codes, and a curl quickstart.
    - New CONFIGURATION.md section pointing at `DARKLAB_API_URL` / `DARKLAB_TOKEN` and the CLI install path.
    - CHANGELOG entry under v2.0 Added; v2.0 merge-request and release-notes drafts updated; ARCHITECTURE.md gains a short "Headless API surface" bullet pointing at the blueprint and broker reuse.
  - Open Decisions
    - **Token header transport** — `Authorization: Bearer` only, `X-Session-ID` only, or both?
      - *Recommended:* accept both, with `Authorization: Bearer` documented as canonical. Bearer is conventional for headless clients and `curl`/CI tooling; keeping `X-Session-ID` as a fallback avoids a second token-distribution path during the v2.0 rollout. Cheap to drop the fallback later if it goes unused.
    - **Token scope model** — one `tok_` token grants both browser and CLI, or separate API-only tokens (e.g. `api_...` prefix with a capability column)?
      - *Recommended:* single `tok_` token for v1. Splitting capabilities adds a UI surface, a migration, and a new revocation path before there is any evidence a single operator needs separate browser vs CLI credentials. Revisit if and when multi-operator or fine-grained-scope demand appears.
    - **Rate limit policy** — shared bucket with the browser path, or separate CLI bucket?
      - *Recommended:* shared. Splitting buckets would let an operator double their effective ceiling by switching transports, which defeats the bucket's purpose. A shared bucket also makes debugging simpler — one number to reason about.
    - **Streaming default** — SSE only, NDJSON only, or both?
      - *Recommended:* both, SSE default. SSE matches the existing broker without translation and works in browsers; NDJSON is what most CLIs and shell pipelines want. `?format=ndjson` is a thin server-side adapter, not a parallel stream implementation.
    - **CLI distribution** — in-repo only, PyPI from v1, or both?
      - *Recommended:* in-repo only for v1. Publishing to PyPI commits to a maintenance cadence and a public name; better to let the CLI surface settle against real usage first. Document `pip install ./tools/darklab_cli` and revisit PyPI as a follow-up once the v1 surface has shipped unchanged for a release or two.
    - **Project write surface** — read-only projects in v1, or full CRUD?
      - *Recommended:* read-only in v1. Project mutation has more nuance (link ownership, target dedup, finding promotion); shipping read-only lets headless callers consume engagement data immediately while the write surface is designed deliberately, not derived from the browser endpoints under deadline pressure.
    - **PTY runs** — expose interactive PTYs through the API, or reject?
      - *Recommended:* reject in v1 with a clear error. xterm.js framing, control-stream draining, and modal lifecycle are browser concerns; modeling them as a generic API would either bloat the surface or quietly diverge from browser behavior. Revisit when a concrete headless-PTY use case appears.
    - **Workflows** — first-class endpoint or out of scope for v1?
      - *Recommended:* out of scope for v1; the CLI can compose runs locally if needed. Adding `/api/v1/workflows` cleanly requires a stable workflow-run record shape, and the existing browser workflow surface is still evolving — promote when it lands in CHANGELOG as stable.
    - **API versioning lifetime** — pin `/api/v1` and never break it, or allow additive-only changes within v1 plus a `v2` for breaking changes?
      - *Recommended:* additive-only within `v1`, with breaking changes deferred to `v2`. Document the contract in `docs/api.md`. A CI test diffs `openapi.json` against a checked-in baseline and fails on removals or signature changes so breakage is loud, not accidental.
    - **OpenAPI source of truth** — hand-written JSON file, or generated from Flask routes via a library (e.g. `apispec`, `flask-smorest`)?
      - *Recommended:* hand-written for v1, validated in CI. The endpoint count is small, a generator pulls in a dependency that affects the whole blueprint style, and the spec doubles as the contract test fixture. Switch to generation later only if the route count outgrows hand maintenance.

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

No technical debt is currently tracked.

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
