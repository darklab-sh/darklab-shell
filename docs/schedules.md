# Scheduled Runs

Scheduled runs let a durable session token keep running one saved command on a cadence, even when no browser tab is open. Use them for routine checks such as a daily `nmap`, an hourly health probe, or a recurring passive recon command that should land in normal History.

Schedules are owned by `tok_` session tokens. Anonymous browser sessions cannot create them because the worker needs a durable owner it can check after the browser closes, and token revocation must stop future fires.

## Creating Schedules

You can manage schedules from three places:

- the browser **Schedules** modal, opened from the desktop rail or mobile menu
- the terminal `schedule` command
- `/api/v1/schedules` or the bundled `darklab schedule` CLI

Each schedule stores:

- one command
- an optional label
- an enabled or paused state
- a timezone
- either a preset cadence (`hourly`, `daily`, `weekly`) or a custom cron expression

The browser editor includes **Next Runs**, which asks the server for the next three fire times and displays them in the selected schedule timezone. That preview uses the same cron and timezone code as the scheduler worker, so what you see in the modal is what the worker will use.

## Cron And Timezones

Cron support is intentionally strict:

- five-field POSIX cron only
- presets normalize to canonical cron strings before storage
- custom cron expressions cannot run more often than every five minutes
- each schedule stores an IANA timezone, such as `UTC` or `America/Chicago`

Some cron expressions are valid but rare. For example, a schedule for a day that does not happen every month will simply move to the next real matching date. The preview shows the next three times before you save, so check it when using day-of-month rules.

For example:

| Expression | Result |
| --- | --- |
| `0 * * * *` | valid, hourly |
| `*/5 * * * *` | valid, every five minutes |
| `*/4 * * * *` | rejected, faster than the minimum interval |
| `* * * * *` | rejected, every minute |

The default timezone comes from `scheduler.default_timezone`, which defaults to `UTC`. The browser uses that value for new schedules, and you can choose a different timezone from the dropdown before saving or previewing.

When using the bundled CLI, put `--` before the command so command flags are treated as part of the scheduled command:

```bash
darklab schedule create --every hourly -- nmap -p 80 darklab.sh
```

## Firing And History Links

Due schedules are fired by the scheduler worker, not by Flask request handlers. The worker launches user-owned schedules through the same brokered run path as browser and API starts, including command policy, command registry rewrites, workspace output handling, history persistence, Atlas capture, active-project capture, and outbound `run_complete` notifications.

Each fire writes a `schedule_fires` audit row. Successful fires store the run id on the audit row and on the schedule. History rows and Run Details use that link to show a `scheduled` badge, and clicking the badge reopens the originating schedule.

Manual **Run now** actions use the same fire-audit path. They run directly from the request that the operator initiated, so they do not depend on the background scheduler process being healthy.

## Missed Fires

When the scheduler worker starts, it checks for schedules that became due while the worker was offline.

- Recent missed fires inside `scheduler.max_catchup_window_seconds` are coalesced into one catch-up fire.
- Older missed windows are skipped and recorded in the fire audit as `skipped_overlap` with the reason `missed fire outside catch-up window`.
- Invalid stored `next_run_at` values are also skipped as `skipped_overlap`, with the reason `invalid next_run_at during scheduler recovery`.
- `scheduler.missed_fire_policy` is `coalesce`.

This keeps a short restart from losing one run, while avoiding a burst of old commands after a long outage.

If command registry changes later turn a previously schedulable command into an interactive PTY command, the next fire is blocked, recorded as a failed fire, and can send `scheduled_run_failed` notifications. Edit or delete the schedule after changing command registry behavior.

## Overlap Policy

The current overlap policy is `skip`. If the previous scheduled run is still active when the next fire is due, the worker records a `skipped_overlap` audit row and advances to the next fire window instead of queueing another copy of the command.

The overlap policy is stored on the schedule row for forward compatibility, but v1 always writes and enforces `skip`.

## Revoked Tokens

Schedules belong to the session token that created them. If that token is revoked, the worker records `skipped_revoked`, disables the schedule, and keeps the row in storage instead of deleting it. Clients using the revoked token lose access to session-scoped schedule routes, so they will not be able to list or edit those rows after revocation.

## Notifications

Scheduled runs reuse the outbound notification system:

- successful external scheduled runs use the normal `run_complete` fan-out after the run finalizes
- scheduler fire failures can enqueue `scheduled_run_failed`
- notification channel delivery still follows channel triggers, muted state, do-not-disturb, rate limits, retries, and dead-letter behavior

See [docs/notifications.md](notifications.md) for channel setup and delivery behavior.

## Limits

- `scheduler.max_per_session` defaults to `32` normal schedules per durable session token.
- Watcher-owned schedules use the same physical table but are hidden from normal schedule lists and cannot be edited as ordinary command schedules.
- Interactive PTY commands cannot be scheduled.
- Workflow scheduling, blackout calendars, holiday handling, cross-session schedules, and per-target schedules are not part of scheduled runs.

## Configuration

Scheduler settings live under `scheduler` in `config.yaml`:

| Key | Default | Meaning |
| --- | --- | --- |
| `scheduler.lock_path` | `APP_DATA_DIR/scheduler.lock` | SQLite scheduler worker lock path. Postgres uses an advisory lock. |
| `scheduler.tick_seconds` | `5` | How often the worker checks for due schedules when nothing is ready now. |
| `scheduler.max_per_session` | `32` | Maximum normal schedules per durable session token. |
| `scheduler.missed_fire_policy` | `coalesce` | Missed-fire behavior on worker startup. |
| `scheduler.max_catchup_window_seconds` | `3600` | How far back the worker will coalesce a missed fire. |
| `scheduler.default_timezone` | `UTC` | Default timezone for new schedules. |

The container entrypoint starts and supervises the scheduler worker when `SCHEDULER_ENABLED` is unset or set to `1`. Set `SCHEDULER_ENABLED=0` if you only want the web process.

## Operator Checks

Useful places to inspect scheduler behavior:

- **Schedules modal** — current schedules, next fires, paused state, fire audit rows, and previous-fire comparisons for completed fire rows
- **History** — `scheduled` badges on runs created by a schedule
- **Run Details** — the originating schedule link for scheduled runs
- `darklab schedule info <id>` — one schedule's full command, cadence, next fires, last fire, and recent audit rows
- `/api/v1/schedules/<id>/fires` or `darklab schedule fires <id>` — paged audit rows
- logs — `SCHEDULE_CREATED`, `SCHEDULE_UPDATED`, `SCHEDULE_DELETED`, `SCHEDULE_RUN_NOW`, `API_SCHEDULE_CREATED`, `API_SCHEDULE_UPDATED`, `API_SCHEDULE_DELETED`, `API_SCHEDULE_RUN_NOW`, `BUILTIN_SCHEDULE_CREATED`, `BUILTIN_SCHEDULE_PAUSED`, `BUILTIN_SCHEDULE_RESUMED`, `BUILTIN_SCHEDULE_DELETED`, `BUILTIN_SCHEDULE_RUN_NOW`, `SCHEDULE_FIRED`, `SCHEDULE_FIRE_SKIPPED_OVERLAP`, `SCHEDULE_FIRE_FAILED`, `SCHEDULE_FAILURE_NOTIFICATION_ERROR`, `SCHEDULE_REQUEST_REJECTED`, `API_SCHEDULE_REJECTED`, `BUILTIN_SCHEDULE_REJECTED`, `SCHEDULE_DISABLED_REVOKED`, `SCHEDULE_RECOVERY_SKIPPED_INVALID_NEXT_RUN`, `SCHEDULE_RECOVERY_SKIPPED_STALE`, `SCHEDULER_WORKER_STARTED`, `SCHEDULER_WORKER_LOCK_HELD`, `SCHEDULER_WORKER_STOPPED`, `SCHEDULER_WORKER_DATABASE_INTERRUPTED`, `SCHEDULER_LOCK_RELEASE_SKIPPED`, `SCHEDULER_WORKER_CRASHED`, and `SCHEDULER_RECOVERY_APPLIED`

## Related Docs

- [Default.md](../.gitlab/merge_request_templates/Default.md) - default GitLab merge request template
- [ARCHITECTURE.md](../ARCHITECTURE.md) - runtime layers, scheduler process details, advisory locks, and persistence notes
- [CHANGELOG.md](../CHANGELOG.md) - release-by-release changes
- [CONFIGURATION.md](../CONFIGURATION.md) - operator config reference for scheduler settings
- [CONTRIBUTING.md](../CONTRIBUTING.md) - local setup, test workflow, linting, branch workflow, and merge request guidance
- [CONTRIBUTORS.md](../CONTRIBUTORS.md) - contributor and acknowledgement notes
- [DECISIONS.md](../DECISIONS.md) - architectural rationale, tradeoffs, and implementation-history notes
- [DOC_STANDARDS.md](../DOC_STANDARDS.md) - documentation structure, templates, and review rules
- [FEATURES.md](../FEATURES.md) - user-facing scheduled-runs feature reference
- [README.md](../README.md) - project overview, quick start, documentation map, and installed tools
- [THEME.md](../THEME.md) - theme registry, token reference, and custom theme authoring
- [TODO.md](../TODO.md) - open follow-ups, research notes, known issues, and future ideas
- [ARCHITECTURE.md -> Atlas Export Schema](../ARCHITECTURE.md#export-schema) - Session Entity Atlas CSV/JSONL export schema and filters
- [docs/ai-privacy.md](ai-privacy.md) - AI assist privacy posture, provider boundaries, redaction, storage, and logging
- [docs/api.md](api.md) - API and `darklab schedule` CLI usage
- [docs/external-command-integrations.md](external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/notifications.md](notifications.md) - outbound notification channels, triggers, and retry behavior
- [docs/postgres-migration.md](postgres-migration.md) - offline SQLite-to-Postgres cutover helper and validation workflow
- [docs/storage-scaling.md](storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [docs/watchers.md](watchers.md) - change-detection watcher baseline, diff, scheduler, and notification behavior
- [tests/README.md](../tests/README.md) - test coverage appendix and focused test commands
- [tests/ui-capture-scenes.md](../tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
