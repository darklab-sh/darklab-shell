# Outbound Notifications

darklab_shell can send queued notifications to external destinations for durable session-token users. Use this when a long run finishes while you are away from the browser, or when automation needs an audit trail of what was sent and what failed.

Browser desktop notifications are still controlled by the **Run Notifications** preference. This page covers outbound channels from the Options **Notifications** tab, `/api/v1`, and the bundled `darklab notify` CLI.

## Channel Types

Notification channels belong to a durable `tok_` session. Anonymous browser sessions cannot create channels because delivery needs an owner that survives browser restarts and can be revoked.

| Kind | Sends to | Secret fields | Config fields |
| --- | --- | --- | --- |
| `webhook` | Generic JSON POST receiver | `url` | `timeout_seconds` |
| `slack` | Slack incoming webhook | `url` | `timeout_seconds` |
| `discord` | Discord incoming webhook | `url` | `timeout_seconds` |
| `telegram` | Telegram Bot API `sendMessage` | `bot_token` | `chat_id`, `timeout_seconds` |
| `pushover` | Pushover message API | `app_token`, `user_key` | `priority`, `sound`, `device`, `timeout_seconds` |
| `email` | SMTP email | server SMTP password from config | `recipients`, `reply_to`, `timeout_seconds` |

Secret values are write-only. List responses show whether required secrets are configured, but they do not return webhook URLs, bot tokens, Pushover keys, or SMTP passwords.

## Triggers

Channels subscribe to one or more trigger names:

| Trigger | What it means |
| --- | --- |
| `run_complete` | A non-interactive external run finalized. Built-in commands and PTY sessions do not use this default fan-out. |
| `pty_session_ended` | An interactive PTY session ended. This trigger is opt-in and separate from `run_complete`. |
| `watcher_changed` | A watcher observed a meaningful change. |
| `watcher_error` | A watcher failed while checking its source. |
| `watcher_recovered` | A watcher that had previously changed or failed returned to a clean state. |
| `scheduled_run_failed` | A scheduled run could not be started or completed by the scheduler path. |
| `test` | A manual test send from the UI, API, or CLI. |

The app currently emits `run_complete` and `test` from the shipped run and channel-management surfaces. The other trigger names are accepted by the channel contract and only produce deliveries when a matching app source enqueues them.

## Payload Shape

Every outbound payload includes:

```json
{
  "trigger": "run_complete",
  "app_name": "darklab_shell",
  "occurred_at": "2026-05-20T00:00:00+00:00"
}
```

`app_name` comes from the configured `app_name` value. `run_complete` payloads also include the run id, command root, exit code, session-token hint, and a summary map:

```json
{
  "trigger": "run_complete",
  "app_name": "darklab_shell",
  "occurred_at": "2026-05-20T00:00:00+00:00",
  "session_token_hint": "1234",
  "run_id": "run-id",
  "command_root": "nmap",
  "exit_code": 0,
  "summary_fields": {
    "artifact_count": 2,
    "finding_count": 4,
    "atlas_entity_count": 12,
    "project_target_count": 1
  }
}
```

`test` payloads are fixed so receivers can whitelist or ignore them:

```json
{
  "trigger": "test",
  "app_name": "darklab_shell",
  "message": "darklab_shell test notification",
  "channel_id": "ntc_example",
  "occurred_at": "2026-05-20T00:00:00+00:00"
}
```

Other accepted trigger names do not produce deliveries unless an app source queues them.

## Redaction

Notification payloads are intentionally small:

- session tokens are never sent; payloads include only the last four characters as `session_token_hint`
- run payloads use the command root, such as `nmap`, instead of the full command line
- channel secrets are stored through the encrypted vault or operator config and are never returned by list APIs
- Telegram, Pushover, and email error messages avoid echoing token values

Receivers still see the payload fields needed for the notification. Send channels only to destinations you trust.

Webhook-style channels only post to public HTTP(S) destinations by default. The sender rejects localhost, loopback, link-local, private-network, multicast, reserved, and other non-public addresses, including hosts that resolve to those addresses. If your deployment intentionally posts to an internal receiver, add that exact host, IP, or CIDR range to `notifications.http_private_host_allowlist`.

## Retry And Dead Letters

Notifications are queued in `notification_events`. A dedicated worker claims due rows, sends them through the registered channel, and records the final state.

- Successful deliveries become `sent`.
- Retryable failures become `retry_wait` with exponential backoff.
- Terminal failures, expired retry windows, and attempts beyond the retry limit become `dead`.
- `notifications.retry.max_attempts` controls attempts.
- `notifications.retry.max_age_hours` defaults to `24` and caps how long an event can keep retrying.
- `notifications.delivery_rate_per_minute` caps each channel's sends.
- `notifications.do_not_disturb` pauses delivery attempts without deleting events or consuming retry attempts.
- Muted channels stay configured, but they do not queue test sends or other deliveries until unmuted.
- If Postgres restarts while the worker is polling, the worker logs `NOTIFICATION_WORKER_DATABASE_INTERRUPTED` and retries instead of treating the restart as a delivery failure.

The delivery audit is visible from the Options **Notifications** tab by opening a channel's **Deliveries** row. It is also available through `/api/v1/notification-events` and `darklab notify events`.

## Webhook Quickstart

Create a durable session token first, then point the API at your darklab_shell host:

```bash
export DARKLAB_API_URL="http://127.0.0.1:5001"
export DARKLAB_TOKEN="tok_..."
```

Create a generic webhook channel with curl:

```bash
curl -sS \
  -H "Authorization: Bearer $DARKLAB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "kind": "webhook",
    "label": "Ops Hook",
    "triggers": ["run_complete"],
    "secret_values": {
      "url": "https://example.test/webhook"
    }
  }' \
  "$DARKLAB_API_URL/api/v1/notification-channels"
```

The CLI can create the same channel without putting the secret on the command line by prompting for required fields:

```bash
darklab notify create webhook --label "Ops Hook" --trigger run_complete
darklab notify list
darklab notify update ntc_... --label "Ops Hook Primary"
darklab notify mute ntc_...
darklab notify unmute ntc_...
darklab notify test ntc_...
darklab notify events --channel ntc_...
```

`--secret-file ./webhook-secrets.json` is also supported when you already have a safely created local JSON file. Avoid building that file with a command that puts the secret literal in shell history.

## Telegram Setup

1. Create a bot with BotFather and copy the bot token.
2. Start a chat with the bot, or add it to the group where messages should land.
3. Get the numeric `chat_id`. A common path is to send the bot a message, then call Telegram's `getUpdates` endpoint with the bot token and read the `chat.id` value.
4. Create a `telegram` channel with `bot_token` as the secret field and `chat_id` in config.

## Pushover Setup

1. Create or choose a Pushover application and copy its app token.
2. Copy your Pushover user key.
3. Create a `pushover` channel with `app_token` and `user_key` as secret fields.
4. Optionally set `device`, `sound`, or integer `priority` in config.

## Email Setup

Email uses the operator-configured SMTP relay under `notifications.smtp.*`. The per-channel config only chooses recipients and an optional reply-to address.

For reliable delivery, use an SMTP relay that already has a trusted sending reputation, such as your domain host, mailbox provider, or an internal relay. Running your own SMTP server from a home or cloud IP often lands in spam folders unless DNS, SPF, DKIM, DMARC, rDNS, and IP reputation are all handled carefully.

The SMTP password is read from the environment variable named by `notifications.smtp.password_secret_id`. See [CONFIGURATION.md](../CONFIGURATION.md) for the full config tree.

## Operator Notes

- The notification worker runs beside Gunicorn and is supervised by the container entrypoint when enabled.
- API and CLI channel management require a durable session token.
- Test sends use the same queued dispatcher path as real events and report whether the selected channel delivered, deferred, or failed the test event.
- Manual test sends use `notifications.test_timeout_seconds`, so a broken webhook or SMTP relay returns feedback faster than normal background delivery.
- Sent delivery audit rows are kept for `notifications.events.retention_days` days. Retry and dead-letter rows remain until they are retried, deleted with their channel/session data, or handled by a future cleanup path.
- Delivery history stays attached to the session token even if a channel row is later deleted.

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
- [docs/api.md](api.md) - headless API and bundled CLI usage guide
- [docs/external-command-integrations.md](external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/postgres-migration.md](postgres-migration.md) - offline SQLite-to-Postgres cutover helper and validation workflow
- [docs/schedules.md](schedules.md) - scheduled-command cadence, timezone, worker, and audit behavior
- [docs/storage-scaling.md](storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [docs/watchers.md](watchers.md) - change-detection watcher baseline, diff, scheduler, and notification behavior
- [tests/README.md](../tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](../tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
