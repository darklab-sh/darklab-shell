# Watchers

Watchers turn a command into a recurring change check. A watcher reruns one command on a cadence, compares each new run against a baseline run, and records whether anything meaningful changed.

You can manage watchers from four places:

- the **Watchers** modal
- the terminal `watch` command
- `/api/v1/watchers`
- the bundled `darklab watch` CLI

Each watcher stores:

- one baseline run id, or a pending first-run baseline
- one command, usually inherited from the baseline run
- one owned schedule row for cadence
- a state such as `ok`, `changed`, `firing`, `paused`, or `error`
- bounded diff details from the last completed check
- recent fire audit rows

Watchers require a durable `tok_` session token. Anonymous browser sessions cannot create watchers because the worker needs a stable owner after the browser closes, and token revocation must still stop future fires.

---

## Creating a watcher

The easiest path is to let the watcher capture its own baseline:

1. Open **Watchers**.
2. Choose **First run** as the baseline mode.
3. Enter the command, pick a cadence, and save.

The first successful watcher fire becomes the baseline. That first audit row is recorded as a baseline capture, not a changed result, and it does not send a watcher-changed notification.

You can also start from a completed run:

1. Open the run from History or Run Details.
2. Choose **Create watcher from this baseline**.
3. Pick a cadence and save.

The browser pre-fills the baseline run and command. If you prefer to paste a run id, choose **Existing run** in the Watchers modal and use the helper beside **Baseline Run**.

From the bundled CLI:

```bash
darklab watch create --first-run --every hourly -- nmap -sV darklab.sh
darklab watch create run_123 --every hourly
darklab watch create run_123 --cron "*/15 * * * *" --label "HTTP drift"
darklab watch create run_123 --every daily -- curl -I https://darklab.sh
```

If you do not pass a command after `--`, the watcher uses the baseline run's command. If you do pass a command after `--`, that command becomes the watched command while the chosen baseline still provides the comparison point.

Custom cron expressions use the same rules as scheduled runs: five-field POSIX cron, IANA timezone support, and a five-minute minimum interval. Watchers use the physical `schedules` table with `owner_kind='watcher'`, but they are hidden from normal schedule lists and cannot be edited as ordinary scheduled commands.

---

## Baseline lifecycle

The baseline run is the point every new watcher fire compares against.

- A watcher can be created from a completed run visible to the current token, or from the first successful watcher fire.
- First-run watchers show as pending until a successful run is captured as the baseline.
- If the first run fails, the watcher records the error and keeps the baseline pending for the next fire or manual **Run now**.
- A watcher can be paused, resumed, manually fired, or deleted without changing the baseline.
- **Accept baseline** promotes the latest watcher fire, or a selected run id, to become the new baseline.
- If the baseline run is deleted from History, the watcher moves to `error`, records `state_reason='baseline_deleted'`, and pauses its owned schedule.

Accepting a baseline is useful when a change is expected. For example, if a new open port is valid, accept the changed run so future watcher checks compare against the new normal.

---

## Fire audit

Every watcher fire writes an audit row, even when there is no diff. Empty checks use `diff_kind='none'`, which makes it clear the watcher is still running. The browser fire audit summarizes the actual diff counts in each row, such as added/removed findings or changed ports, and each row can expand to show the bounded added, removed, and changed items stored with that fire. Rows with both a baseline and completed run also include **Compare**, which opens the run comparison view with the baseline on the left and the fire run on the right.

Useful places to inspect fire history:

- **Watchers** modal — recent fire rows, baseline comparisons, and run handoffs
- `watch info <watcher_id>` in the terminal shell
- `darklab watch fires <watcher_id>`
- `/api/v1/watchers/<watcher_id>/fires`

Manual **Run now** actions use the same audit path as worker-fired watchers. They start directly from the operator request, so they do not depend on the background scheduler process being ready at that moment.

---

## Diff model

Watcher diffs prefer structured signals before falling back to plain text. This makes alerts more useful than "some line changed" when darklab_shell can understand the output.

Classifier order:

1. **Findings** — compares persisted findings by stable finding signature.
2. **nmap ports and services** — detects added, removed, and changed port/service rows.
3. **Host lists** — detects added and removed host/domain/subdomain-style values.
4. **TLS certificate fields** — detects selected `openssl s_client` certificate changes.
5. **Textual fallback** — compares bounded output lines when no structured classifier applies. It ignores progress/status-line/PTY chrome and records added, removed, and unchanged entity counts when the structured output metadata is available.

Diff summaries store bounded added, removed, and changed signals. If source output or changed-signal lists are capped, the fire row carries `truncated=true`.

Two options tune the noise level:

- `suppress_removals` keeps removal-only churn quiet.
- `notify_metadata_changes` treats metadata-only changes as diff-worthy.

The textual fallback is intentionally more sensitive than the structured classifiers. It is useful for generic commands, but tools with unstable ordering or timestamps may be noisier until they get a dedicated classifier.

---

## Scheduler and notifications

Watchers do not have a separate timer. The scheduler worker claims due watcher-owned schedule rows, starts the watched command through the same brokered run path as scheduled commands, and records a pending watcher fire.

When the run finalizes, the watcher finalization hook:

- compares the completed run against the baseline
- updates watcher state and counters
- updates the pending fire audit row
- queues watcher notifications when appropriate

Notification behavior:

- a non-empty diff moves the watcher to `changed` and can send `watcher_changed`
- an empty diff from `changed` moves the watcher back to `ok` and can send `watcher_recovered`
- an empty diff from `ok` records the audit row but stays quiet
- a failed watcher run moves the watcher toward `error` and can send `watcher_error`

Five consecutive failed watcher runs disable the owned schedule. The watcher row stays visible so you can inspect the error, edit the command, and resume it when ready.

---

## API and CLI

The API uses the same JSON error envelope as the rest of `/api/v1`.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/watchers` | List current-token watchers. |
| `POST` | `/api/v1/watchers` | Create a watcher from `baseline_run_id` or `baseline_mode='first_run'`, cadence, and optional command override. |
| `GET` | `/api/v1/watchers/<watcher_id>` | Read one watcher. |
| `PATCH` | `/api/v1/watchers/<watcher_id>` | Update command, cadence, label, options, or pause/resume state. |
| `DELETE` | `/api/v1/watchers/<watcher_id>` | Delete one watcher and its owned schedule. |
| `POST` | `/api/v1/watchers/<watcher_id>/run-now` | Fire one watcher immediately. |
| `POST` | `/api/v1/watchers/<watcher_id>/accept-baseline` | Promote the latest fire or provided `run_id` to the new baseline. |
| `GET` | `/api/v1/watchers/<watcher_id>/fires` | Read paged fire audit rows. |

CLI examples:

```bash
darklab watch list
darklab watch info wtr_123
darklab watch pause wtr_123
darklab watch resume wtr_123
darklab watch run wtr_123
darklab watch fires wtr_123
darklab watch accept wtr_123
darklab watch accept wtr_123 --run-id run_456
darklab watch delete wtr_123
```

List and fire-audit routes use the normal `limit`, `offset`, and `has_more` envelope. `darklab watch list` and `darklab watch fires` default to 50 rows and cap at 100.

---

## Limits and config

- `watchers.max_per_session` defaults to `32`.
- Watchers require durable `tok_` sessions.
- Watchers monitor one baseline command at a time.
- Watcher-owned schedules share the scheduler worker, missed-fire recovery, revoked-token handling, overlap policy, and cron rules used by normal schedules.
- Threshold-based alerting, multi-command watcher graphs, blackout calendars, and cross-session watchers are not part of this feature.

---

## Related Docs

- [Default.md](../.gitlab/merge_request_templates/Default.md) - default GitLab merge request template
- [ARCHITECTURE.md](../ARCHITECTURE.md) - runtime layers, request flow, persistence, security, and app internals
- [CHANGELOG.md](../CHANGELOG.md) - release-by-release changes
- [CONFIGURATION.md](../CONFIGURATION.md) - operator config reference for `app/conf/`, `.env`, Compose, storage, and production tuning
- [CONTRIBUTING.md](../CONTRIBUTING.md) - local setup, test workflow, linting, branch workflow, and merge request guidance
- [CONTRIBUTORS.md](../CONTRIBUTORS.md) - contributor and acknowledgement notes
- [DECISIONS.md](../DECISIONS.md) - architectural rationale, tradeoffs, and implementation-history notes
- [DOC_STANDARDS.md](../DOC_STANDARDS.md) - documentation structure, templates, and review rules
- [FEATURES.md](../FEATURES.md) - full per-feature reference
- [README.md](../README.md) - project overview, quick start, documentation map, and installed tools
- [THEME.md](../THEME.md) - theme registry, token reference, and custom theme authoring
- [TODO.md](../TODO.md) - open follow-ups, research notes, known issues, and future ideas
- [ARCHITECTURE.md -> Atlas Export Schema](../ARCHITECTURE.md#export-schema) - Session Entity Atlas CSV/JSONL export schema and filters
- [docs/ai-privacy.md](ai-privacy.md) - AI assist privacy posture, provider boundaries, redaction, storage, and logging
- [docs/api.md](api.md) - headless API and bundled CLI usage guide
- [docs/external-command-integrations.md](external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/notifications.md](notifications.md) - outbound notification channels, payloads, retries, and setup guide
- [docs/postgres-migration.md](postgres-migration.md) - offline SQLite-to-Postgres cutover helper and validation workflow
- [docs/schedules.md](schedules.md) - scheduled-command cadence, timezone, worker, and audit behavior
- [docs/storage-scaling.md](storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [tests/README.md](../tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](../tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
