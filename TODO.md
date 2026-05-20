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

- **Outbound notifications (webhooks, Slack, Discord, SMTP email)**
  - Goal
    - Ship a pluggable `Channel`-based delivery layer so app events (run finalization, finding classification, watcher fires, scheduled-run failures) can be sent to external destinations per session token.
    - Existing notifications are browser-foreground only. This closes the loop for solo operators running long scans away from the tab and is the delivery surface the scheduler and watchers features will depend on.
    - Land this **before** scheduler/watchers so the automation features can hook into a real delivery surface rather than building one inline.
    - Non-goals for v1: web-push (covered by the PWA Idea), per-project channels (sessions only), per-channel templating, real-time delivery dashboards.
  - Phase 0 — schema, base class, and dispatcher
    - Add `app/core/migrations/v0009_notification_channels.py` (and the equivalent SQLite `CREATE TABLE` in `core/database.py`) for two tables:
      - `notification_channels` — `id, session_token, kind ('webhook'|'slack'|'discord'|'email'), label, secret_kid, config_json, triggers_json, muted, created, updated`. Plain labels and identifiers stay TEXT; webhook URL, bot token, SMTP password go through the existing encrypted-secrets vault — `secret_kid` is the vault row reference, plaintext is never stored on this table.
      - `notification_events` — `id, channel_id, trigger ('run_complete'|'finding_classified'|'watcher_fired'|'scheduled_run_failed'), payload_json, status ('pending'|'sent'|'failed'|'dead'), attempts, last_attempt_at, last_error, run_id, created`. Used for delivery audit and retry.
    - Add `app/services/notifications/`:
      - `models.py` — `Channel` dataclass, `NotificationEvent` dataclass, trigger-name string constants.
      - `base.py` — abstract `Channel` with `send(payload: dict) -> ChannelResult` and `validate_config(config: dict) -> list[str]`.
      - `dispatcher.py` — `enqueue(trigger, payload, session_token)` writes a row to `notification_events`, then either dispatches synchronously (test/dev) or hands off to the delivery worker.
      - `worker.py` — background thread that drains `pending` rows, applies exponential-backoff retry, moves rows `failed → dead` after the configured retry count.
      - `secrets.py` — thin wrapper around the existing secrets vault for read/store of channel secrets, with a small per-call audit row written through the existing secrets-audit path.
    - Acceptance criteria
      - `Channel` is registerable: `register_channel("webhook", WebhookChannel)`.
      - Dispatcher can be invoked synchronously from tests without spawning the worker.
      - All secret storage rides on the existing vault; no new ciphertext column path is invented.
      - Helpers in `services/notifications/*` import nothing from `blueprints/*`.
  - Phase 1 — `WebhookChannel` (generic JSON)
    - First concrete implementation in `app/services/notifications/channels/webhook.py`.
    - Payload shape (stable across channels): `{trigger, occurred_at, session_token_hint (last 4 chars), run_id, command_root, exit_code, summary_fields:{...}, schedule_id?, watcher_id?}`. **Never** include full command text or argv — match the existing browser desktop-notification policy that exposes command root only.
    - HTTP client uses `urllib.request` (stdlib) with a configurable timeout; 2xx is success, 3xx follows the same redirect rules as the API client, 5xx and timeouts retry up to the configured max, 4xx is terminal.
    - Tests: `tests/py/test_notifications_webhook.py` covering 2xx success, 5xx retry then success, 4xx terminal, malformed-URL rejection, timeout retry, payload shape stability.
  - Phase 2 — `SlackChannel` and `DiscordChannel`
    - `app/services/notifications/channels/slack.py` + `channels/discord.py`. Both use incoming-webhook URLs (no bot scopes, no OAuth) for v1 simplicity.
    - Format payloads with their native shapes: Slack `blocks` with a header + key-value section; Discord `embeds` with a title + fields. Share a `format_summary_fields(payload)` helper in `channels/_format.py`.
    - Reuse the webhook delivery primitive from Phase 1; only the body differs.
    - Tests: format-output snapshot tests plus the same delivery-matrix as the webhook channel.
  - Phase 3 — `EmailChannel` (SMTP)
    - `app/services/notifications/channels/email.py`. Uses `smtplib` + `email.message.EmailMessage` (stdlib).
    - Operator-gated: requires `notifications.smtp.{host, port, user, password_secret_id, from_address, tls}` in `app/conf/config.yaml`. If unset, the email channel kind is rejected at create time with a clear error.
    - Subject line: `[darklab] {trigger}: {command_root}`. Body is plain-text key/value first, HTML alternative second; HTML is rendered through Jinja autoescape (matches the package HTML rendering pattern).
    - Tests: `tests/py/test_notifications_email.py` using `aiosmtpd` in-process or mocking `smtplib.SMTP`.
  - Phase 4 — Hook points and trigger fan-out
    - Run finalization: in `app/blueprints/run.py`, after the existing post-finalize code in `_brokered_real_run_worker`, call `notifications.dispatcher.enqueue("run_complete", build_payload(run), session_token)` for the owning session. Add a separate `finding_classified` enqueue when post-run finding classification rows are written.
    - Synthetic and PTY runs participate the same way; gate fan-out on `run_kind == 'external'` so noisy builtin runs (e.g., `help`) don't fan out by default.
    - `scheduled_run_failed` and `watcher_fired` hooks are stubbed in the dispatcher here; their actual call sites land with Scheduler and Watchers.
    - Redaction: the same `_history_safe_command_for_storage`-style masking used for permalinks runs over `summary_fields` before enqueue.
    - Per-channel mute and a global `notifications.do_not_disturb` config knob short-circuit the dispatcher before any HTTP call.
  - Phase 5 — Browser Options surface
    - New `app/static/js/features/preferences/notification_channels.js`. Add a "Notifications" section to the Options modal with: channel list (kind icon, label, mute toggle), create/edit form per kind (URL field for webhook/slack/discord, host/port/auth for SMTP), trigger checkboxes, "Send test notification" button.
    - Secrets entered in the form are submitted through the existing secrets-vault flow; channel rows store only the `secret_kid` reference, never the plaintext.
    - Confirms use `showConfirm()`. Pressables follow the button primitive family.
  - Phase 6 — CLI and API surfaces
    - Add `/api/v1/notification-channels` GET/POST/PATCH/DELETE in `app/blueprints/api_v1.py`. Read endpoints return channels for the calling token; write endpoints accept the same JSON the browser sends. Secret material is write-only — GETs return masked metadata.
    - Add `/api/v1/notification-events` GET (paginated) for delivery audit.
    - CLI: `darklab notify list / create / delete / test / events`. The CLI never accepts a plaintext secret on the command line; it prompts via stdin or reads from `--secret-file PATH`.
  - Phase 7 — hardening, docs, release
    - Docs: new `docs/notifications.md` covering payload shape, channel-kind matrix, retry/dead-letter policy, redaction guarantees, SMTP operator config, and a webhook curl quickstart.
    - `CONFIGURATION.md` updates for the `notifications.*` config tree.
    - `ARCHITECTURE.md` gains a short "Notifications surface" subsection under Backend Architecture and log-event entries for `NOTIFICATION_DISPATCHED` / `NOTIFICATION_DELIVERY_FAILED` / `NOTIFICATION_RETRIED`.
    - `CHANGELOG.md`, v2.0 merge-request, and release-notes updates.
    - Contract test: assert every `register_channel(name, cls)` channel implements both `validate_config` and `send`.
  - Open Decisions
    - **Delivery model** — synchronous-from-hook, in-process worker thread, dedicated worker process, or external queue (Redis/Celery)?
      - *Recommended:* in-process worker thread with a database-backed queue. Synchronous-from-hook blocks run finalization on a flaky third party; an external queue adds infrastructure for a feature that may see one delivery per hour. A worker thread with the existing `notification_events` table as the queue is the smallest model that retries safely and does not couple delivery to request lifecycle.
    - **Retry policy shape** — fixed retries, exponential backoff, or operator-tunable?
      - *Recommended:* exponential backoff with jitter, three attempts (1s → 10s → 60s), then move to `failed`; a periodic sweep re-queues `failed → pending` for up to 24 hours before marking `dead`. Attempt count is operator-tunable in `notifications.retry.max_attempts`; the backoff curve is fixed.
    - **Channel secrets storage** — new ciphertext column on `notification_channels`, or reuse the existing encrypted-secrets vault?
      - *Recommended:* reuse the vault. It already solves KEK rotation, audit logging, and operator-key bootstrap; introducing a parallel ciphertext column duplicates that work and creates two key rotation surfaces. Store only `secret_kid` on the channel row.
    - **Trigger configuration** — channels declare which triggers they accept, or triggers declare which channels they fan out to?
      - *Recommended:* channels declare. Each row carries `triggers_json: ["run_complete", "watcher_fired"]`. Trigger sources call `dispatcher.enqueue(trigger, payload, session_token)` and the dispatcher fans out to all channels whose `triggers_json` includes that trigger and whose `muted` flag is false.
    - **Notification body content** — command root only, or include exit code, line count, and finding count?
      - *Recommended:* command root, exit code, elapsed, run_id, and a small `summary_fields` map per trigger (e.g., `{"new_findings": 4}` for `finding_classified`). Argv, full command text, and workspace paths are never included. Matches the browser desktop-notification policy and keeps webhooks safe to point at shared channels.
    - **Slack/Discord auth method** — incoming webhooks or bot tokens?
      - *Recommended:* incoming webhooks for v1. No OAuth scopes, no app-install dance, single URL per channel. Promote to bot-token in v2 when operators ask for threading or @mentions.
    - **SMTP library** — stdlib `smtplib` or third-party (e.g., `emails`, `yagmail`)?
      - *Recommended:* stdlib `smtplib` + `email.message.EmailMessage`. The feature is one transactional message per fire; the stdlib is sufficient and avoids a third-party runtime dependency.
    - **Do-not-disturb scope** — global only, per-channel only, or both?
      - *Recommended:* both. Global is the "I'm in a meeting" switch; per-channel is for "this Slack webhook is currently noisy." Two booleans, no extra schema.
    - **PII / secret scrubbing** — at enqueue time or at send time?
      - *Recommended:* at enqueue time, before any row is written to `notification_events`. Once a payload is in the queue it may be retried, replayed for audit, or exported during diagnostics — scrubbing at send only protects the outbound HTTP body, not the audit trail.
    - **Per-channel rate limiting** — none, fixed cap, or operator-tunable?
      - *Recommended:* fixed cap of 10 deliveries per channel per minute, enforced inside the dispatcher. Beyond that, deliveries queue. Stays well under Slack/Discord's published webhook limits without operator tuning. Cap is exposed as `notifications.per_channel_rate.{minute, second}` for later tuning.

- **Scheduled and recurring runs**
  - Goal
    - Add time-driven runs to the app. Operators save a command with a cron expression or cadence preset, and the run fires on that cadence without keeping a browser tab open. Fired runs land in normal history tagged `scheduled` with a link back to the originating schedule.
    - Reuse the existing `/runs` broker, command preparation path (allowlist, deny-prefix, registry rewrite, variable expansion), and history persistence so a scheduled run is indistinguishable from a manually-launched run except for the source tag.
    - Land Outbound Notifications (above) **before** this so scheduled-run-failed / run-complete fan-out is a real surface, not a stub.
    - Non-goals for v1: workflow scheduling (commands only), cross-session schedules, per-target scheduling, calendar-based holidays/blackout windows.
  - Phase 0 — schema, scheduler process, and tick infrastructure
    - Add `app/core/migrations/v0010_schedules.py` (plus SQLite equivalent in `core/database.py`):
      - `schedules` — `id, session_token, kind ('command'), command_text, cron_expr, cadence_preset ('hourly'|'daily'|'weekly'|null), timezone, enabled, next_run_at, last_run_at, last_run_id, consecutive_failures, label, created, updated`.
      - `schedule_fires` — `id, schedule_id, fired_at, run_id, status ('skipped_overlap'|'skipped_revoked'|'fired'|'fire_failed'), reason`. Append-only audit.
    - Add `app/services/scheduler/`:
      - `models.py` — `Schedule`, `ScheduleFire` dataclasses.
      - `cron.py` — cron parsing and `next_fire(cron_expr, after, timezone)` using `croniter` (single new pip dependency). Cadence presets normalize to canonical cron strings on save.
      - `service.py` — `create / update / delete / pause / resume / list_for_session` library functions, backend-agnostic.
      - `worker.py` — the dedicated scheduler process entry point. Computes `next_run_at` for each enabled row, sleeps until the soonest, fires, writes back `last_run_at` / `next_run_at`.
      - `recovery.py` — at worker startup, scan for schedules whose `next_run_at` is in the past and apply the missed-fire policy.
    - Process model: the scheduler runs as a dedicated Gunicorn-sibling process started by `entrypoint.sh`. It does **not** run inside Flask workers — worker rotation must not lose ticks. Exactly one scheduler process per deployment; coordination uses a Postgres advisory lock (`pg_advisory_lock` on a fixed namespace string) or, for SQLite deployments, a filesystem lock at `data/scheduler.lock`. If the lock is held by another process, the second scheduler exits cleanly.
    - Acceptance criteria
      - `croniter` parses every documented cadence preset.
      - Two simultaneously-started scheduler processes do not both fire a schedule.
      - A schedule whose `next_run_at` is now-50min still fires according to the missed-fire policy.
  - Phase 1 — REST blueprint and validation
    - Add `app/blueprints/schedules.py`, mounted at `/schedules`:
      - `GET /schedules` — list current-session schedules with derived `next_run_at` and `enabled`.
      - `POST /schedules` — create. Validates: command goes through the same allowlist/deny-prefix/registry-rewrite pipeline as `/runs` (without spawning), cron expression parses, timezone is in the IANA list, schedule count under the per-session cap.
      - `PATCH /schedules/<id>` — partial update (enabled toggle, cron change, label, command change re-validates).
      - `DELETE /schedules/<id>`.
      - `POST /schedules/<id>/run-now` — operator-initiated immediate fire; uses the same code path as a scheduler-driven fire.
    - Each scheduled fire enqueues through the existing `/runs` broker with `session_token` set to the schedule owner, `run_kind='external'`, and `metadata.scheduled = {schedule_id, fired_at, manual}`. The broker refuses if the session token is revoked; the scheduler logs the skip and writes a `skipped_revoked` `schedule_fires` row.
    - Tests: `tests/py/test_schedules.py` covering CRUD, cross-session 404, allowlist rejection on create, allowlist re-validation on PATCH, manual run-now path.
  - Phase 2 — Fire path and broker integration
    - The scheduler `worker.py` polls `schedules` for the next fire roughly every 5 seconds. For each due row:
      - Resolve the session token. If revoked since the schedule was saved, write `skipped_revoked`, disable the schedule, and emit `SCHEDULE_DISABLED_REVOKED`.
      - Apply the overlap policy (see Open Decisions): if the previous fire's run is still active, either skip with `skipped_overlap` or kill-and-restart.
      - Reuse `_validate_command_for_run` from `blueprints/run.py` (extracted to a shared helper in `services/runs/preparation.py` so the scheduler does not import a blueprint). On rejection, log and write `fire_failed`.
      - On success, call into the broker the same way the API v1 `POST /api/v1/runs` does, then record the resulting `run_id` on both `schedules.last_run_id` and a new `schedule_fires` row.
    - Hook into the notification dispatcher: on `fire_failed` and on `run_complete` for a scheduled run, enqueue with triggers `scheduled_run_failed` / `run_complete` respectively. The dispatcher decides which channels are interested.
    - Acceptance criteria
      - Scheduled runs appear in `/history` with a visible "scheduled" badge tied to `schedule_id`.
      - A schedule whose token is revoked stops firing and is disabled.
      - Two due schedules with overlapping windows still fire in a deterministic order (by `next_run_at`, then `id`).
  - Phase 3 — Terminal `schedule` built-in
    - Add `schedule` to the session built-in family with subcommands: `list`, `create <cron> "<cmd>"`, `pause <id>`, `resume <id>`, `delete <id>`, `run <id>`, `info <id>`.
    - Browser-owned (like `theme`, `config`, `session-token`) because output is transcript-shaped and confirmations belong inline. Reuses the shared pending-confirm state used by `session-token`.
    - Autocomplete: schedule IDs complete against the active session's schedule list.
  - Phase 4 — Browser Schedules modal
    - New `app/static/js/features/schedules/`. Modal lives beside Workflows. Two-column layout: list on left, detail/edit on right.
    - Cadence editor: preset chips (Every hour / day / week / custom cron) plus a live "next 3 fires" preview computed via a server endpoint (`GET /schedules/preview?cron=...&tz=...`) so the browser does not bundle a croniter clone.
    - History rows for a schedule's past fires link to their run detail.
    - Pressables and confirms follow the design-system primitives.
  - Phase 5 — CLI and API surfaces
    - `/api/v1/schedules` GET/POST/PATCH/DELETE plus `/api/v1/schedules/<id>/run-now` and `/api/v1/schedules/<id>/fires` (paginated audit).
    - CLI: `darklab schedule list / create / pause / resume / delete / run / info / fires`.
    - CLI `darklab schedule create` accepts both `--cron "0 * * * *"` and `--every hourly|daily|weekly` for symmetry with the modal.
  - Phase 6 — hardening, docs, release
    - Docs: new `docs/schedules.md` covering cron support, timezone handling, missed-fire behavior, overlap policy, fan-out to notifications, and the per-session schedule cap.
    - `CONFIGURATION.md` updates for `scheduler.{lock_path, tick_seconds, max_per_session, missed_fire_policy, overlap_policy, default_timezone}`.
    - `ARCHITECTURE.md` gains a "Scheduler process" subsection under Runtime Topology.
    - Log events: `SCHEDULE_FIRED`, `SCHEDULE_SKIPPED_OVERLAP`, `SCHEDULE_FIRE_FAILED`, `SCHEDULER_PROCESS_BOOTED`, `SCHEDULER_MISSED_FIRES_RECOVERED`, `SCHEDULE_DISABLED_REVOKED`.
    - Smoke tests cover a full create → fire → history-link cycle against a fast tick-rate test config.
  - Open Decisions
    - **Scheduler implementation** — APScheduler, `croniter` + custom loop, or Redis sorted-set tick?
      - *Recommended:* `croniter` for parsing plus a small custom loop in `services/scheduler/worker.py`. APScheduler adds API surface (jobstores, executors, listeners) for a feature that is fundamentally "wake up, query SQL, fire, sleep." `croniter` is one well-scoped dependency. Revisit APScheduler if multi-process job affinity or triggers other than cron land.
    - **Scheduler process model** — dedicated process, in-worker thread with leader election, or APScheduler in Gunicorn `on_starting`?
      - *Recommended:* dedicated process started from `entrypoint.sh`, coordinated with a Postgres advisory lock (or filesystem lock on SQLite). Worker threads are fragile under Gunicorn restarts; in-worker means N workers all want to be the leader. A separate process matches the model already used by the broker.
    - **Missed-fire policy** — run all missed fires on recovery, run the most recent only, or skip and reset `next_run_at`?
      - *Recommended:* coalesce — fire **once** if any missed-fire window exists, then resume normal cadence. "All missed" stampedes after long downtime; "skip entirely" silently masks degraded operation. The single catch-up fire restores intent without amplifying load.
    - **Overlap policy when the previous fire is still running** — skip-this-fire, kill-previous-and-fire, queue-this-fire, or operator-configurable per schedule?
      - *Recommended:* skip-this-fire by default, operator-configurable per schedule to `kill-and-fire` for "always run the latest" workflows. Queueing creates an unbounded backlog under a stuck previous run.
    - **Timezone handling** — UTC only, operator-default with per-schedule override, or per-session default?
      - *Recommended:* operator-default in `scheduler.default_timezone` (UTC out of the box) with per-schedule override. Per-session defaults make every UI surface harder to reason about; per-schedule overrides are the unit of work operators actually think in.
    - **What can be scheduled** — single commands only in v1, or commands plus workflows?
      - *Recommended:* commands only in v1. Workflow scheduling needs a stable workflow-fire record shape and the existing workflow surface is still evolving. Promote once workflow runs are first-class in History.
    - **Per-session schedule cap** — yes/no and the number?
      - *Recommended:* yes, cap at 32 schedules per session. Prevents accidental misuse and gives the scheduler a known upper bound for the tick loop. Operator-tunable in `scheduler.max_per_session`.
    - **Cron validation surface** — strict POSIX-cron only, or the croniter extensions (`@hourly`, seconds field)?
      - *Recommended:* five-field POSIX cron only on input. Reject seconds-field and `@`-aliases at create time and translate the cadence presets to canonical five-field cron internally. The surface is small enough to document on one line.
    - **Run-tag visibility** — show "scheduled" badge in History, in Run Details, both, or neither?
      - *Recommended:* both, plus a schedule_id link in Run Details that opens the Schedules modal at that schedule.
    - **Token revocation behavior** — disable the schedule, delete it, or keep firing-then-skipping?
      - *Recommended:* disable on first `skipped_revoked` (do not delete; the operator may want to re-enable after re-issuing the token). Add a "this schedule is paused because its session token was revoked" badge in the modal.

- **Watchers (change-detection monitors)**
  - Goal
    - First-class change-detection. Each watcher is "rerun command X on cadence Y, diff against baseline Z, deliver a notification only when the diff is non-empty." Builds on the scheduler service for cadence and the notifications service for delivery; reuses `app/services/runs/comparison.py` for diff computation.
    - The unit of value: operators stop watching their tabs for "is anything new on this nmap?" and the app tells them.
    - Land **after** scheduler and notifications. A watcher without a scheduler is just a manual diff; a watcher without notifications is just a database row.
    - Non-goals for v1: watchers across multiple commands, watcher graphs, threshold-based alerting (e.g., "only fire if 3 new ports"), watcher history retention beyond a fixed cap.
  - Phase 0 — schema and data model
    - Add `app/core/migrations/v0011_watchers.py` (plus SQLite equivalent):
      - `watchers` — `id, session_token, label, command_text, schedule_id, baseline_run_id, last_run_id, last_diff_summary_json, state ('ok'|'changed'|'firing'|'paused'|'error'), consecutive_no_change, consecutive_changed, created, updated`.
      - `watcher_fires` — `id, watcher_id, run_id, diff_summary_json, diff_kind ('signal'|'textual'|'none'), fired_notifications_count, state_at_fire, created`. Append-only audit.
    - The watcher row owns its schedule, so deleting a watcher cascades to deleting its schedule row. A schedule cannot be shared between a watcher and a regular scheduled run (keeps the data model unambiguous).
    - Acceptance criteria
      - A new watcher inserts both a `watchers` row and a `schedules` row in one transaction.
      - Deleting a watcher removes both rows atomically.
  - Phase 1 — Service composition
    - Add `app/services/watchers/`:
      - `models.py` — `Watcher`, `WatcherFire`, `WatcherDiff` dataclasses.
      - `service.py` — `create / update / delete / pause / resume / accept_baseline / list_for_session` library functions.
      - `runner.py` — the watcher fire hook called by the scheduler worker when it fires a watcher-owned schedule. Responsibilities: kick the run through the broker, wait for completion, compute the diff against `baseline_run_id`, update state, enqueue a notification on `changed`.
      - `diff.py` — thin wrapper over `services/runs/comparison.py` that returns a normalized `WatcherDiff` regardless of which comparator fired (signal-based, textual added/removed).
    - Scheduler hook: extend `scheduler/worker.py` to call `watchers.runner.handle_fire(schedule, run_id)` after `run_complete` for any schedule whose row has a corresponding `watchers.schedule_id`. Watchers do not have a separate timer; they ride the scheduler.
  - Phase 2 — Diff classifier policies
    - First-class signal classifiers in `watchers/classifiers/`:
      - `ports.py` — `nmap`-shaped output: added ports, removed ports, service or state changes.
      - `hosts.py` — subdomain/host lists: added names, removed names.
      - `tls.py` — `openssl s_client` output: issuer, subject, SAN, validity, fingerprint changes.
      - `findings.py` — when the source run carries structured findings, diff finding fingerprints directly.
    - Fallback `textual.py` — line-level added/removed when no classifier matches. Documented as "noisy on tools with non-deterministic output ordering — prefer a signal classifier when one fits."
    - Each classifier exposes `applies_to(command_text, run) -> bool` and `diff(baseline_run, current_run) -> WatcherDiff`. The runner picks the first that applies, falling back to textual.
    - Tests: golden inputs for each classifier in `tests/py/test_watchers_classifiers.py`, asserting the structured diff shape.
  - Phase 3 — REST blueprint
    - Add `app/blueprints/watchers.py`, mounted at `/watchers`:
      - `GET /watchers` — list current-session watchers with derived state.
      - `POST /watchers` — create. Requires a `baseline_run_id` from a completed run in the current session, a `cron_expr`, and either inherits command text from the baseline or accepts an override.
      - `PATCH /watchers/<id>` — pause/resume, change cadence, change label.
      - `DELETE /watchers/<id>` — cascades through to the watcher's owning schedule row.
      - `POST /watchers/<id>/accept-baseline` — promotes the most recent fire's run to the new baseline. Idempotent.
      - `POST /watchers/<id>/run-now` — operator-initiated immediate fire.
    - Tests: cross-session 404, baseline validation, accept-baseline state transitions, cascade delete.
  - Phase 4 — Terminal `watch` built-in
    - Add `watch` to the session built-in family with subcommands: `list`, `create <baseline_run_id> <cron>`, `pause <id>`, `resume <id>`, `delete <id>`, `accept <id>`, `run <id>`, `info <id>`.
    - Symmetric with the `schedule` built-in. Autocomplete completes watcher IDs against the current session.
  - Phase 5 — Browser Watchers modal
    - New `app/static/js/features/watchers/`. Modal lives beside Schedules.
    - Watcher row state: `ok` (last fire matched baseline) / `changed` (last fire had a non-empty diff and is awaiting accept) / `firing` (fire in progress) / `paused` / `error`.
    - Detail pane shows the last diff using a reusable component shared with the existing Run Comparison overlay so visual treatment stays consistent.
    - Accept-baseline is a confirm modal (discards the prior baseline); resume from paused is a single click.
  - Phase 6 — CLI and API surfaces
    - `/api/v1/watchers` GET/POST/PATCH/DELETE plus `/api/v1/watchers/<id>/accept-baseline`, `/run-now`, and `/fires` (paginated audit).
    - CLI: `darklab watch list / create / pause / resume / delete / accept / run / info / fires`.
  - Phase 7 — hardening, docs, release
    - Docs: new `docs/watchers.md` covering the diff model, classifier inventory, baseline lifecycle, and how watchers interact with the scheduler and notifications.
    - `ARCHITECTURE.md` gains a "Watchers" subsection under Backend Architecture.
    - Log events: `WATCHER_FIRED`, `WATCHER_CHANGED`, `WATCHER_BASELINE_ACCEPTED`, `WATCHER_DIFF_FAILED`, `WATCHER_DISABLED_AFTER_ERRORS`.
    - Smoke tests cover a full create → fire (no change) → fire (changed) → notify → accept-baseline cycle.
  - Open Decisions
    - **Signal model — what counts as a diff worth notifying on** — additions only, removals only, both, or all changes?
      - *Recommended:* additions and removals by default, with a per-watcher option to suppress removals (`ports went from open to closed` is interesting for some workflows, noise for others). "Severity or metadata changed" is interesting once findings are structured, but keep it gated behind a per-watcher toggle until classifiers stabilize.
    - **Baseline rotation** — manual accept-only, auto-accept after N stable fires, or both?
      - *Recommended:* manual accept-only in v1. Auto-baselines silently swallow gradual drift (slowly-changing subdomain list) and produce "this watcher never fires" reports that turn out to be a stale baseline. Add auto-accept in v2 once operators ask for it explicitly.
    - **Empty-diff fires** — write a `watcher_fires` row with `diff_kind='none'`, or skip the row entirely?
      - *Recommended:* write the row. The audit "this watcher ran at 14:00 and there was nothing new" is itself a signal; skipping it makes "is this watcher actually firing?" untestable from the audit table.
    - **Failed scheduled run for a watcher (exit≠0)** — treat as `changed`, treat as `error` state, or operator-configurable?
      - *Recommended:* watcher state goes to `error` and a single `scheduled_run_failed` notification fires; the watcher does not promote the failed run to baseline. Consecutive failures escalate to a `WATCHER_DISABLED_AFTER_ERRORS` event after 5 failures so a broken watcher does not pollute notifications indefinitely.
    - **Where classifiers register** — Python entry point, registry decorator inside `watchers/classifiers/`, or operator-config in YAML?
      - *Recommended:* registry decorator inside `watchers/classifiers/`. Entry points overengineer for a feature unlikely to want third-party classifiers in v1; YAML can't express the `applies_to` predicate cleanly. Promote to entry points if a "bring your own classifier" use case appears.
    - **Diff size cap per fire** — unbounded, fixed cap, or operator-tunable?
      - *Recommended:* fixed cap of 1,000 changed signals per fire with a `truncated` flag on the `WatcherDiff`. Operators chasing larger diffs can use Run Comparison directly. Prevents one runaway scan from filling the audit table.
    - **Watcher cap per session** — yes/no and the number?
      - *Recommended:* yes, cap at 32 watchers per session (mirrors the scheduler cap because each watcher owns a schedule). Operator-tunable in `watchers.max_per_session`.
    - **Notification trigger granularity** — one `watcher_fired` trigger, or split into `watcher_changed` / `watcher_recovered` / `watcher_error`?
      - *Recommended:* split. `watcher_changed` is the noisy one operators may want on Slack; `watcher_error` belongs in an ops channel; `watcher_recovered` ("the diff went away again") is optional and off-by-default. Keeps channel routing precise without inflating the schema.
    - **Baseline run lifetime** — what if the baseline run is deleted from history?
      - *Recommended:* on delete, pause the watcher and surface `state='error'` with a clear "baseline was deleted" reason. Do not silently promote the next fire to baseline — that hides the operator's prior decision.
    - **Cross-watcher coordination** — if two watchers wrap the same command, do they share a fire?
      - *Recommended:* no, each watcher fires its own run. Sharing fires couples watcher state in confusing ways (accept-baseline on one would affect the other). The marginal cost of an extra run is small; the simplicity payoff is large.

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
