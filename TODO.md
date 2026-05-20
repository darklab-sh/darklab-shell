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
  - [Structured output model](#structured-output-model)
  - [Unified terminal built-in lifecycle](#unified-terminal-built-in-lifecycle)
  - [Plugin-style helper command registry](#plugin-style-helper-command-registry)
  - [Lightweight Jinja base template](#lightweight-jinja-base-template)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

- **Scheduled and recurring runs**
  - Goal
    - Add time-driven runs to the app. Operators save a command with a cron expression or cadence preset, and the run fires on that cadence without keeping a browser tab open. Fired runs land in normal history tagged `scheduled` with a link back to the originating schedule.
    - Reuse the existing `/runs` broker, command preparation path (allowlist, deny-prefix, registry rewrite, variable expansion), and history persistence so a scheduled run is indistinguishable from a manually-launched run except for the source tag.
    - Reuse the shipped outbound notification queue for scheduled-run-failed and run-complete fan-out.
    - Non-goals for v1: workflow scheduling (commands only), cross-session schedules, per-target scheduling, calendar-based holidays/blackout windows.
  - Phase 0 — schema, scheduler process, and tick infrastructure
    - Add `app/core/migrations/v0010_schedules.py` (plus SQLite equivalent in `core/database.py`):
      - `schedules` — `id, session_token, owner_kind ('user'|'watcher'), owner_id, kind ('command'), command_text, cron_expr, cadence_preset ('hourly'|'daily'|'weekly'|null), timezone, enabled, next_run_at, last_run_at, last_run_id, overlap_policy ('skip'), consecutive_failures, label, paused_reason, last_error, created, updated`. One physical table stores both normal schedules and watcher-owned schedules; `owner_kind` controls dispatch. `overlap_policy` is stored for forward compatibility, but v1 always writes and enforces `skip`.
      - `schedule_fires` — `id, schedule_id, owner_kind, owner_id, fired_at, run_id, status ('skipped_overlap'|'skipped_revoked'|'fired'|'fire_failed'), reason`. Append-only audit.
    - Add `app/services/scheduler/`:
      - `models.py` — `Schedule`, `ScheduleFire` dataclasses.
      - `cron.py` — cron parsing and `next_fire(cron_expr, after, timezone)` using `croniter` (single new pip dependency). Cadence presets normalize to canonical cron strings on save.
      - `service.py` — `create / update / delete / pause / resume / list_for_session` library functions, backend-agnostic.
      - `worker.py` — the dedicated scheduler process entry point. Computes `next_run_at` for each enabled row, sleeps until the soonest, fires, writes back `last_run_at` / `next_run_at`.
      - `recovery.py` — at worker startup, scan for schedules whose `next_run_at` is in the past and apply the missed-fire policy: coalesce missed fires into one catch-up fire within `scheduler.max_catchup_window_seconds`, skip older missed windows with an audit row, then resume normal cadence.
      - `dispatch.py` — routes due rows by ownership. `owner_kind='user'` starts a normal scheduled command; `owner_kind='watcher'` calls watcher orchestration instead of launching a generic scheduled run.
    - Process model: the scheduler runs as a dedicated Gunicorn-sibling process started by `entrypoint.sh`. It does **not** run inside Flask workers — worker rotation must not lose ticks. Exactly one scheduler process per deployment; coordination uses a Postgres advisory lock (`pg_advisory_lock` on the reserved `darklab_shell_scheduler` namespace) or, for SQLite deployments, a filesystem lock at `data/scheduler.lock`. If the lock is held by another process, the second scheduler exits cleanly. `entrypoint.sh` supervises the scheduler in a small restart loop with crash logging and a short sleep/backoff so unexpected worker exit is visible and self-healing.
    - Timezone model: `scheduler.default_timezone` is the operator default (UTC out of the box), and each schedule can override it. Cron input is strict five-field POSIX cron; cadence presets are stored as canonical five-field cron strings.
    - Schedule creation requires a durable `tok_` session owner. Anonymous UUID sessions cannot create schedules because scheduled work must survive browser restarts and token revocation must be enforceable.
    - Acceptance criteria
      - `croniter` parses every documented cadence preset.
      - Two simultaneously-started scheduler processes do not both fire a schedule.
      - A schedule whose `next_run_at` is now-50min still fires according to the missed-fire policy.
      - A watcher-owned schedule never appears as an editable normal schedule and never double-starts both a scheduled run and a watcher run.
  - Phase 1 — REST blueprint and validation
    - Add `app/blueprints/schedules.py`, mounted at `/schedules`:
      - `GET /schedules` — list current-session normal schedules (`owner_kind='user'`) with derived `next_run_at` and `enabled`.
      - `POST /schedules` — create a normal schedule with `owner_kind='user'`. Validates: command goes through the same allowlist/deny-prefix/registry-rewrite pipeline as `/runs` (without spawning), cron expression parses as five-field POSIX cron (reject seconds-field and `@` aliases), timezone is in the IANA list, schedule count is under the per-session cap of 32.
      - `PATCH /schedules/<id>` — partial update (enabled toggle, cron change, label, command change re-validates).
      - `DELETE /schedules/<id>`.
      - `POST /schedules/<id>/run-now` — operator-initiated immediate fire; uses the same dispatch/preparation path as a scheduler-driven fire but fires directly from the web worker. It does not depend on the scheduler process being healthy.
    - Each normal scheduled fire enqueues through the existing `/runs` broker with `session_token` set to the schedule owner, `run_kind='external'`, and `metadata.scheduled = {schedule_id, fired_at, manual}`. The broker refuses if the session token is revoked; the scheduler logs the skip and writes a `skipped_revoked` `schedule_fires` row.
    - Tests: `tests/py/test_schedules.py` covering CRUD, cross-session 404, allowlist rejection on create, allowlist re-validation on PATCH, manual run-now path.
  - Phase 2 — Fire path and broker integration
    - The scheduler `worker.py` polls `schedules` for the next fire roughly every 5 seconds. For each due row:
      - Resolve the session token. If revoked since the schedule was saved, write `skipped_revoked`, disable the schedule, and emit `SCHEDULE_DISABLED_REVOKED`.
      - Apply the v1 overlap policy: if the previous fire's run is still active, skip with `skipped_overlap`. Queueing and kill-and-fire are intentionally deferred so a stuck or long-running scan does not create backlog or destroy useful evidence.
      - Route through `scheduler.dispatch.fire(schedule)`. For `owner_kind='user'`, reuse `_validate_command_for_run` from `blueprints/run.py` (extracted to a shared helper in `services/runs/preparation.py` so the scheduler does not import a blueprint). On rejection, log and write `fire_failed`.
      - For `owner_kind='watcher'`, call the watcher fire entry point; the watcher service starts the run and later computes the diff from the run-finalization hook. The scheduler does not also start a normal scheduled command.
      - On success, record the resulting `run_id` on both `schedules.last_run_id` and a new `schedule_fires` row.
    - Hook into the notification dispatcher: on `fire_failed` for normal schedules and on `run_complete` for a scheduled run, enqueue with triggers `scheduled_run_failed` / `run_complete` respectively. Watcher-owned schedule failures use `watcher_error` from the watcher service so channel routing stays precise.
    - Acceptance criteria
      - Scheduled runs appear in `/history` with a visible "scheduled" badge tied to `schedule_id`.
      - Scheduled runs show the same badge in Run Details with a `schedule_id` link that opens the Schedules modal at that schedule.
      - A schedule whose token is revoked stops firing and is disabled.
      - Two due schedules with overlapping windows still fire in a deterministic order (by `next_run_at`, then `id`).
  - Phase 3 — Terminal `schedule` built-in
    - Add `schedule` to the session built-in family with subcommands: `list`, `create --cron "<expr>" -- <cmd>`, `create --every hourly|daily|weekly -- <cmd>`, `pause <id>`, `resume <id>`, `delete <id>`, `run <id>`, `info <id>`.
    - Browser-owned (like `theme`, `config`, `session-token`) because output is transcript-shaped and confirmations belong inline. Reuses the shared pending-confirm state used by `session-token`.
    - Autocomplete: schedule IDs complete against the active session's schedule list.
  - Phase 4 — Browser Schedules modal
    - New `app/static/js/features/schedules/`. Modal lives beside Workflows. Two-column layout: list on left, detail/edit on right.
    - Cadence editor: preset chips (Every hour / day / week / custom cron) plus a live "next 3 fires" preview computed via a token-authenticated, no-body, no-write server endpoint (`GET /schedules/preview?cron=...&tz=...`) so the browser does not bundle a croniter clone.
    - History rows for a schedule's past fires link to their run detail.
    - Run Details gets a "Schedule this command" action that opens the Schedules modal pre-filled from that run's command, giving operators a visible path from a completed run to a recurring schedule.
    - Revoked-token state appears as a clear paused badge: "this schedule is paused because its session token was revoked." The schedule is disabled, not deleted, so the operator can re-enable after re-issuing the token.
    - Pressables and confirms follow the design-system primitives.
  - Phase 5 — CLI and API surfaces
    - `/api/v1/schedules` GET/POST/PATCH/DELETE plus `/api/v1/schedules/<id>/run-now` and `/api/v1/schedules/<id>/fires` (paginated audit).
    - CLI: `darklab schedule list / create / pause / resume / delete / run / info / fires`.
    - CLI `darklab schedule create` accepts both `--cron "0 * * * *" -- <cmd>` and `--every hourly|daily|weekly -- <cmd>` for symmetry with the modal. The CLI joins `argv_after_dashdash` with spaces and submits that as the command body, so operators can pass normal shell-shaped command arguments without wrapping the whole command in one quoted string.
  - Phase 6 — hardening, docs, release
    - Docs: new `docs/schedules.md` covering cron support, timezone handling, missed-fire behavior, overlap policy, fan-out to notifications, and the per-session schedule cap.
    - `CONFIGURATION.md` updates for `scheduler.{lock_path, tick_seconds, max_per_session, missed_fire_policy, max_catchup_window_seconds, default_timezone}`. `scheduler.max_per_session` defaults to 32.
    - `ARCHITECTURE.md` gains a "Scheduler process" subsection under Runtime Topology and lists the reserved advisory-lock namespaces used by migrations, scheduler, notification worker, and notification sweep.
    - Log events: `SCHEDULE_FIRED`, `SCHEDULE_SKIPPED_OVERLAP`, `SCHEDULE_FIRE_FAILED`, `SCHEDULER_PROCESS_BOOTED`, `SCHEDULER_MISSED_FIRES_RECOVERED`, `SCHEDULE_DISABLED_REVOKED`.
    - Smoke tests cover a full create → fire → history-link cycle against a fast tick-rate test config.

- **Watchers (change-detection monitors)**
  - Goal
    - First-class change-detection. Each watcher is "rerun command X on cadence Y, diff against baseline Z, deliver a notification only when the diff is non-empty." Builds on the scheduler service for cadence and the notifications service for delivery; reuses `app/services/runs/comparison.py` for diff computation.
    - The unit of value: operators stop watching their tabs for "is anything new on this nmap?" and the app tells them.
    - Land **after** scheduler and notifications. A watcher without a scheduler is just a manual diff; a watcher without notifications is just a database row.
    - Non-goals for v1: watchers across multiple commands, watcher graphs, threshold-based alerting (e.g., "only fire if 3 new ports"), watcher history retention beyond a fixed cap.
  - Phase 0 — schema and data model
    - Add `app/core/migrations/v0011_watchers.py` (plus SQLite equivalent):
      - `watchers` — `id, session_token, label, command_text, schedule_id, baseline_run_id, last_run_id, last_diff_summary_json, state ('ok'|'changed'|'firing'|'paused'|'error'), state_reason, last_error, options_json, consecutive_no_change, consecutive_changed, consecutive_failures, created, updated`. `options_json` stores strictly validated watcher policy flags such as `suppress_removals` and `notify_metadata_changes`; additions and removals count as diffs by default, while metadata/severity-only changes stay opt-in until classifiers stabilize. Promote these flags to typed columns if the validated option set grows beyond three fields.
      - `watcher_fires` — `id, watcher_id, baseline_run_id, run_id, diff_summary_json, diff_kind ('signal'|'textual'|'none'), truncated, notification_event_ids_json, state_at_fire, created`. Append-only audit with a unique constraint on `(watcher_id, run_id)` so duplicate run-finalization paths cannot create duplicate watcher fires.
    - The watcher row owns its schedule. The paired schedule uses `owner_kind='watcher'` and `owner_id=<watcher_id>` in the shared `schedules` table, and `watchers.schedule_id` is unique so a schedule cannot be shared between a watcher and a regular scheduled run.
    - Watchers are capped at 32 per session by default (`watchers.max_per_session`), mirroring the schedule cap because each watcher owns one schedule.
    - Watcher creation requires a durable `tok_` session owner. Anonymous UUID sessions cannot create watchers because watcher cadence, baseline state, and notifications must survive browser restarts.
    - Acceptance criteria
      - A new watcher inserts both a `watchers` row and a `schedules` row in one transaction.
      - Deleting a watcher removes both rows atomically.
      - A normal schedule cannot claim a watcher-owned schedule row, and the Schedules UI/API does not expose watcher-owned rows as ordinary schedules.
      - Two watchers wrapping the same command still fire separate runs; watcher state and baseline acceptance are never shared across watchers.
      - Duplicate finalize calls for the same `(watcher_id, run_id)` are idempotent and never emit duplicate notifications.
  - Phase 1 — Service composition
    - Add `app/services/watchers/`:
      - `models.py` — `Watcher`, `WatcherFire`, `WatcherDiff` dataclasses.
      - `service.py` — `create / update / delete / pause / resume / accept_baseline / list_for_session` library functions.
      - `runner.py` — the watcher fire hook called by the scheduler worker when it fires a watcher-owned schedule. Responsibilities: kick the run through the broker, record the pending watcher fire, and return quickly so the scheduler is not blocked by a long scan.
      - `finalize.py` — run-finalization hook that claims the pending watcher fire for the completed run, computes the diff against `baseline_run_id`, updates watcher state, and enqueues `watcher_changed`, `watcher_error`, or `watcher_recovered` notifications as appropriate. The state machine is explicit: non-empty diff after `ok` or `recovered` emits `watcher_changed`; empty diff after `changed` emits optional `watcher_recovered`; empty diff after `ok` stays quiet; failed watcher runs set `state='error'`, do not promote the failed run to baseline, and emit `watcher_error`. After five consecutive failures, disable the watcher and log `WATCHER_DISABLED_AFTER_ERRORS`.
      - `diff.py` — thin wrapper over `services/runs/comparison.py` that returns a normalized `WatcherDiff` regardless of which comparator fired (signal-based, textual added/removed).
    - Scheduler hook: extend `scheduler.dispatch` so `owner_kind='watcher'` rows call `watchers.runner.handle_fire(schedule)`. Watchers do not have a separate timer; they ride the scheduler, but the scheduler never waits for watcher run completion.
    - Run cleanup hook: if a baseline run is deleted from history, pause the watcher, set `state='error'`, set `state_reason='baseline_deleted'`, and emit the documented log event.
  - Phase 2 — Diff classifier policies
    - First classifier slice:
      - `findings.py` — when the source run carries structured findings, diff finding fingerprints directly.
      - `textual.py` — line-level added/removed fallback when no structured classifier matches. Documented as "noisy on tools with non-deterministic output ordering — prefer a signal classifier when one fits."
    - Follow-up classifier slice in the same phase after the service contract is stable:
      - `ports.py` — `nmap`-shaped output: added ports, removed ports, service or state changes.
      - `hosts.py` — subdomain/host lists: added names, removed names.
      - `tls.py` — `openssl s_client` output: issuer, subject, SAN, validity, fingerprint changes.
    - Classifiers register through a decorator inside `watchers/classifiers/`. Each classifier exposes `applies_to(command_text, run) -> bool` and `diff(baseline_run, current_run) -> WatcherDiff`. The runner picks the first that applies, falling back to textual.
    - Diff input uses full stored output when available. If only capped transcript output is available, the `WatcherDiff` carries `truncated=true` and the notification says the diff may be incomplete. Each fire stores at most 1,000 changed signals with a `truncated` flag so one runaway scan cannot fill the audit table.
    - Tests: golden inputs for each classifier in `tests/py/test_watchers_classifiers.py`, asserting the structured diff shape.
  - Phase 3 — REST blueprint
    - Add `app/blueprints/watchers.py`, mounted at `/watchers`:
      - `GET /watchers` — list current-session watchers with derived state.
      - `POST /watchers` — create. Requires a `baseline_run_id` from a completed run in the current `tok_` session, a `cron_expr`, and either inherits command text from the baseline or accepts an override.
      - `PATCH /watchers/<id>` — pause/resume, change cadence, change label.
      - `DELETE /watchers/<id>` — cascades through to the watcher's owning schedule row.
      - `POST /watchers/<id>/accept-baseline` — manually promotes the most recent fire's run to the new baseline. Idempotent. Baselines do not rotate automatically in v1.
      - `POST /watchers/<id>/run-now` — operator-initiated immediate fire.
    - Tests: cross-session 404, baseline validation, accept-baseline state transitions, cascade delete, no shared fires across watchers with the same command.
  - Phase 4 — Terminal `watch` built-in
    - Add `watch` to the session built-in family with subcommands: `list`, `create <baseline_run_id> --cron "<expr>"`, `create <baseline_run_id> --every hourly|daily|weekly`, `pause <id>`, `resume <id>`, `delete <id>`, `accept <id>`, `run <id>`, `info <id>`.
    - Symmetric with the `schedule` built-in. Autocomplete completes watcher IDs against the current session.
  - Phase 5 — Browser Watchers modal
    - New `app/static/js/features/watchers/`. Modal lives beside Schedules.
    - Watcher row state: `ok` (last fire matched baseline) / `changed` (last fire had a non-empty diff and is awaiting accept) / `firing` (fire in progress) / `paused` / `error`.
    - Detail pane shows the last diff using a reusable component shared with the existing Run Comparison overlay so visual treatment stays consistent.
    - Empty-diff fires are visible in watcher audit as `diff_kind='none'` so operators can confirm a watcher is still running even when nothing changed.
    - Run Details gets a "Create watcher from this baseline" action that opens the Watchers modal pre-filled with that run as the baseline.
    - Accept-baseline is a confirm modal (discards the prior baseline); resume from paused is a single click.
  - Phase 6 — CLI and API surfaces
    - `/api/v1/watchers` GET/POST/PATCH/DELETE plus `/api/v1/watchers/<id>/accept-baseline`, `/run-now`, and `/fires` (paginated audit).
    - CLI: `darklab watch list / create / pause / resume / delete / accept / run / info / fires`.
  - Phase 7 — hardening, docs, release
    - Docs: new `docs/watchers.md` covering the diff model, classifier inventory, baseline lifecycle, and how watchers interact with the scheduler and notifications.
    - `ARCHITECTURE.md` gains a "Watchers" subsection under Backend Architecture.
    - Log events: `WATCHER_FIRED`, `WATCHER_CHANGED`, `WATCHER_RECOVERED`, `WATCHER_ERROR`, `WATCHER_BASELINE_ACCEPTED`, `WATCHER_DIFF_FAILED`, `WATCHER_DISABLED_AFTER_ERRORS`.
    - Smoke tests cover a full create → fire (no change) → fire (changed) → notify → accept-baseline cycle.

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

- **Promote shared run/history API helpers out of browser blueprints.**
  - `app/blueprints/api_v1.py` intentionally reuses private helpers from `blueprints.run` and `blueprints.history` to keep v1 behavior aligned with the browser path.
  - Once the API surface settles, move the shared run-start, stream, history-output, and history-count pieces into service modules so browser routes and `/api/v1` routes both depend on stable service boundaries instead of private route helpers.

---

## Feature Enhancements

### API / CLI Enhancements
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
