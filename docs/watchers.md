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
- optional Project membership for keeping the watcher and its future external runs together in a Project Monitoring tab
- a state such as `ok`, `changed`, `firing`, `paused`, or `error`
- validated noise and notification policy fields
- bounded diff details from the last completed check
- recent fire audit rows

Watchers belong to the active personal or team scope. Anonymous browser sessions cannot create watchers because the worker needs a durable `tok_` token after the browser closes, and token revocation must still stop later personal fires. Team-owned watchers stay with the team and are visible to other members when that team scope is active. Team viewers can read watchers and fire audit rows, while watcher creation, edits, deletes, manual fires, and baseline acceptance require automation-management permission.
Archived teams pause their team-owned watchers. Reactivating a team restores access, but archive-paused watchers stay paused until someone resumes them.

Project-linked watchers appear in that Project's **Monitoring** tab. Their future external runs and captured Project evidence stay with that Project even if another Project is active when a check finishes. Unassigned watchers remain unassigned instead of inheriting the session's active Project.

A watcher can be assigned to a Project directly, or it can infer the Project from a baseline run when that run has exactly one same-scope Project link. Ambiguous, unlinked, or cross-scope baseline links leave the watcher unassigned. Deleting a Project clears watcher membership instead of deleting the watcher.

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
darklab watch create --first-run --every hourly --project prj_123 -- nmap -sV darklab.sh
darklab watch create run_123 --every hourly --project prj_123
darklab watch create run_123 --cron "*/15 * * * *" --label "HTTP drift"
darklab watch create run_123 --every hourly --alert-after-repeated-changes 3 --alert-signal-class ports
darklab watch create run_123 --every daily -- curl -I https://darklab.sh
```

The Watchers modal has the same Project selector, and the Project Monitoring tab's **New monitor** action opens the modal with the current project already selected. Use `darklab watch set-project wtr_123 prj_123` to move an existing watcher into a Project Monitoring tab, or `darklab watch set-project wtr_123 --clear` to remove the project link.

If you do not pass a command after `--`, the watcher uses the baseline run's command. If you do pass a command after `--`, that command becomes the watched command while the chosen baseline still provides the comparison point.

Custom cron expressions use the same rules as scheduled runs: five-field POSIX cron, IANA timezone support, and a five-minute minimum interval. Watchers use the physical `schedules` table with `owner_kind='watcher'`, but they are hidden from normal schedule lists and cannot be edited as ordinary scheduled commands.

---

## Baseline lifecycle

The baseline run is the point every new watcher fire compares against.

- A watcher can be created from a completed run visible to the active personal or team scope, or from the first successful watcher fire.
- First-run watchers show as pending until a successful run is captured as the baseline.
- If the first run fails, the watcher records the error and keeps the baseline pending for the next fire or manual **Run now**.
- A watcher can be paused, resumed, manually fired, or deleted without changing the baseline.
- **Accept baseline** promotes the latest watcher fire, or a selected run id, to become the new baseline.
- If the baseline run is deleted from History, the watcher moves to `error`, records `state_reason='baseline_deleted'`, and pauses its owned schedule.

Accepting a baseline is useful when a change is expected. For example, if a new open port is valid, accept the changed run so later watcher checks compare against the new normal.

---

## Fire audit

Every watcher fire writes an audit row, even when there is no diff. Empty checks use `diff_kind='none'`, which makes it clear the watcher is still running. Fire rows also carry `fire_kind` and `state_reason` values such as `changed`, `recovered`, `failed`, `no_change`, `baseline_created`, `baseline_accepted`, and `paused`, so dashboards can show what happened without guessing from the watcher's current state.

The browser fire audit summarizes the actual diff counts in each row, such as added/removed findings or changed ports, and each row can expand to show the bounded added, removed, and changed items stored with that fire. Rows with both a baseline and completed run also include **Compare**, which opens the run comparison view with the baseline on the left and the fire run on the right. If an old baseline or fire run has been deleted, the fire still stays visible with its stored summary and the unavailable action is disabled.

Changed and failed fires can also be triaged from Project Monitoring. The acknowledgement fields are `ack_state`, `ack_note`, `ack_by`, and `ack_at`. `new`, `acknowledged`, and `needs_action` count as unresolved for the current monitor state; `expected` and `resolved` count as resolved. Acknowledging a fire does not change the baseline. Use **Accept baseline** when the new run should become the comparison point.

Useful places to inspect fire history:

- **Watchers** modal — recent fire rows, baseline comparisons, and run handoffs
- Project **Monitoring** tab — project-scoped monitor groups, timeline rows, filters, triage controls, and run handoffs
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

Diff summaries store bounded added, removed, and changed signals. If source output or changed-signal lists are capped, the fire row carries `truncated=true`. Project Monitoring turns those summaries into severity and top-signal rollups for cards, timelines, and attack-surface digest notifications.

Watcher options tune which changes count as diff-worthy:

- `suppress_removals` keeps removal-only churn quiet.
- `notify_metadata_changes` treats metadata-only changes as diff-worthy.

Watcher notification policy tunes when changed notifications are sent:

- `ignore_line_patterns` accepts up to 20 unique strings, each 120 characters or less. These patterns only apply to the textual fallback classifier, where they are matched against individual output lines before the fallback diff is built.
- `alert_after_repeated_changes` is an integer from 1 to 10. Values above 1 keep detected changes visible in the dashboard but suppress `watcher_changed` notification fan-out until the repeated-change threshold is reached.
- `alert_signal_classes` accepts `findings`, `entities`, and `ports`. Empty means all signal classes can notify. Findings covers structured findings, Entities covers host/DNS/textual entity changes, and Ports covers open-port plus certificate/TLS changes.

The bundled CLI exposes the same policy fields. Add `--ignore-line-pattern` and `--alert-signal-class` more than once when a watcher needs several values, use `--alert-after-repeated-changes N` for repeated-change gating, and use `darklab watch set-policy` to replace policy lists or clear them later:

```bash
darklab watch set-policy wtr_123 --ignore-line-pattern "^Host is up" --alert-after-repeated-changes 3
darklab watch set-policy wtr_123 --alert-signal-class findings --alert-signal-class ports
darklab watch set-policy wtr_123 --clear-ignore-line-patterns --clear-alert-signal-classes
```

The textual fallback is intentionally more sensitive than the structured classifiers. It is useful for generic commands, but tools with unstable ordering or timestamps may be noisier until they get a dedicated classifier.

---

## Scheduler and notifications

Watchers do not have a separate timer. The scheduler worker claims due watcher-owned schedule rows, starts the watched command through the same brokered run path as scheduled commands, and records a pending watcher fire.

If a watcher-fired command is still active when you open or reload the UI, it stays in the Status Monitor instead of automatically taking over the terminal. Use **Attach** from Status Monitor when you want to watch that run live.

When the run finalizes, the watcher finalization hook:

- compares the completed run against the baseline
- updates watcher state and counters
- updates the pending fire audit row
- queues watcher notifications when appropriate

Notification behavior:

- a non-empty diff moves the watcher to `changed` and can send `watcher_changed` when the repeated-change threshold and signal-class filter allow it
- an empty diff from `changed` moves the watcher back to `ok` and can send `watcher_recovered`
- an empty diff from `ok` records the audit row but stays quiet
- a failed watcher run moves the watcher toward `error` and can send `watcher_error`

Five consecutive failed watcher runs disable the owned schedule. The watcher row stays visible so you can inspect the error, edit the command, and resume it when ready.

Project digest notifications reuse the same watcher fire summaries instead of re-reading run output. When a Project digest is due, the scheduler asks Project Monitoring for the bounded window since the last successful digest and sends the compact rollup through the notification channels selected on that Project's Monitoring tab.

---

## API and CLI

The API uses the same JSON error envelope as the rest of `/api/v1`.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/watchers` | List watchers for the active personal/team API scope. |
| `POST` | `/api/v1/watchers` | Create a watcher from `baseline_run_id` or `baseline_mode='first_run'`, cadence, optional command override, optional `project_id`, `options`, and `policy`. |
| `GET` | `/api/v1/watchers/<watcher_id>` | Read one watcher. |
| `PATCH` | `/api/v1/watchers/<watcher_id>` | Update command, cadence, label, project membership, options, policy, or pause/resume state. |
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
darklab watch set-project wtr_123 prj_123
darklab watch set-project wtr_123 --clear
darklab watch set-policy wtr_123 --alert-after-repeated-changes 3
darklab watch run wtr_123
darklab watch fires wtr_123
darklab watch accept wtr_123
darklab watch accept wtr_123 --run-id run_456
darklab watch delete wtr_123
```

List and fire-audit routes use the normal `limit`, `offset`, and `has_more` envelope. `darklab watch list` and `darklab watch fires` default to 50 rows and cap at 100.

---

## Limits and config

- `watchers.max_per_session` defaults to `32` per durable personal or team scope.
- Watchers require durable `tok_` sessions.
- Watchers monitor one baseline command at a time.
- Watcher-owned schedules share the scheduler worker, missed-fire recovery, revoked-token handling, overlap policy, and cron rules used by normal schedules.
- Team-owned watchers pause when their team is archived and stay paused after the team is reactivated until someone resumes them.
- Multi-command watcher graphs and blackout calendars are not part of this feature.

---

## Related Docs

- [schedules.md](schedules.md) - scheduler cadence and worker behavior
- [notifications.md](notifications.md) - watcher notification delivery
- [../CONFIGURATION.md](../CONFIGURATION.md) - watcher and worker settings
- [../FEATURES.md](../FEATURES.md) - user-facing watcher behavior
- [api.md](api.md) - watcher API and CLI usage
