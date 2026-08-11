# Logging Reference

This operator and developer reference describes darklab_shell log levels, output formats, structured event names, fields, redaction boundaries, and troubleshooting workflow.

## Runtime and Redaction Boundaries

The application uses a dedicated `shell` logger configured by `logging_setup.py`. Logging is part of the runtime architecture rather than just a deployment concern because request hooks, run lifecycle handlers, diagnostics gates, and startup bootstrap all emit structured events that operators rely on for troubleshooting and auditing.

Configuration loading starts before runtime bootstrap can build the final logger. `startup_logging.py` captures those records in memory without attaching a handler, and `configure_logging()` replays each one once through the selected formatter while applying the effective level. If configuration can't finish, the same boundary writes one safe `CONFIG_LOAD_FAILED` record in the most recent usable text or GELF format. That fallback includes only bounded phase, source, key, and error-type context; it doesn't include parser contents, configuration values, or a traceback. Ignored, dropped, defaulted, clamped, and truncated configuration values all contribute to the `warning_count` reported by `CONFIG_VALIDATED` and `CONFIG_LOADED`.

Structured events use the `session` field for request correlation. Anonymous session IDs are logged as-is, while `tok_` session-token values are masked before logging because they are bearer credentials.

Browser `/log` reports normalize `warn` to `warning`, preserve supported DEBUG/INFO/WARNING/ERROR levels, and count only warning/error reports in the client-error metric. Client details pass through an explicit bounded allowlist. Run-comparison reports accept bounded left/right ids, canonical route paths, response stage/status, and a comparison-request flag; manual search text, commands, and query strings aren't accepted. Atlas Quick Lookup reports accept only bounded modes, result states, scope kinds, request sequence numbers, counts, booleans, failure stages, and timings. Submitted drafts, normalized values, canonical values, URL paths or queries, and request bodies aren't accepted. Destructive History and Project cleanup logs use flags and counts only; cleanup samples, entity values, finding text, and arbitrary client detail keys stay out of structured and audit records.

Public CVE risk and advisory events log source names, feed versions, acquisition modes, outcomes, counts, timings, and error classes. Positive and negative NVD persistence events use counts only. They don't enumerate CVEs, package identities, targets, Projects, provider payloads, or finding evidence. Project acknowledgement logs keep only the escalation id, acknowledgement state, and bounded note length; the note itself stays in the database and out of logs.

Assessment evidence matching logs bounded run, Project, team, and result counts after a completed run. Quota skips record the fixed quota reason, and unexpected failures record the exception through the normal error logger. These events don't include commands, target values, finding text, output, profile snapshots, or evidence payloads. History deletion and automatic retention record only how many assessment evidence links became unavailable; the preserved evidence ids and reasons stay in the database and audit boundary rather than application logs.

Private OAST provider, cleanup, and readiness records keep only a correlation id, fixed phase or state flags, timings, attempts, counts, and bounded error metadata. Successful external calls use DEBUG, while provider-ready, positive ingestion, and confirmed terminal cleanup use INFO. They never include the provider URL, callback domain or URL, service token, provider payload, session secret, private key, ciphertext, or spool path. Repeated readiness, stale-scan, and scope-mismatch warnings are suppressed for a bounded interval; the next emitted record reports how many repeats were skipped.

Private ZAP plan-spool cleanup records keep only a validated job id, fixed cleanup stage, counts, and bounded error classes. They never include filesystem paths, Automation Framework YAML, selected targets, authentication roles, API keys, or report content. Repeated stale-scan warnings are suppressed for a bounded interval, and the next emitted warning reports how many repeats were skipped.

HTTPx screenshot finalization logs only owner/run ids, counts, limits, and fixed failure classes. Storage-limit and cleanup events never include workspace paths, URLs, page titles, technologies, captured bytes, or target values.

## Level Semantics

| Level | Use |
| --- | --- |
| `DEBUG` | Detailed request, branch, timing, cache, and lifecycle context used during troubleshooting. |
| `INFO` | Expected lifecycle outcomes and meaningful operator-visible state changes. |
| `WARNING` | Rejected, degraded, missing, or recoverable conditions that deserve attention without an exception traceback. |
| `ERROR` | Failed operations or unexpected runtime conditions; tracebacks are included only where the event contract calls for one. |
| `CRITICAL` | A startup safety condition that prevents the app from running correctly. |

Configure the minimum emitted level with `log_level`. Applications and browser clients use `WARNING`; some transports or dashboards may display that level as `WARN`.

## Output Formats

The logging layer supports two output formats selected by `log_format` in installed `conf/config.local.yaml`. Source development uses `app/conf/config.local.yaml` instead:

- `text`
  - human-readable single-line logs for local development and plain `docker compose logs`
  - output shape is `timestamp [LEVEL] EVENT key=value ...`
  - extra fields are sorted alphabetically and appended after the event name
  - string values containing spaces are repr-quoted so copy/paste remains readable
- `gelf`
  - newline-delimited GELF 1.1 JSON for Graylog-style aggregation
  - `short_message` is the bare event name such as `RUN_START`
  - event context is emitted as `_`-prefixed additional fields such as `_ip`, `_run_id`, and `_cmd`
  - this makes the application logs directly indexable by a GELF-aware backend without extra parsing rules

Container log transport and the application formatter are intentionally
separate controls. A host-local collector can forward container standard
output, while `log_format: gelf` controls whether the application itself emits
GELF-shaped records or plain text.

### Field type contract

GELF field names keep one OpenSearch-compatible value type across every event.
HTTP response codes use the numeric `http_status` field, while feature states
use string fields such as `provider_status`, `workflow_status`,
`fire_status`, `assist_status`, `project_status`, `team_status`, and
`job_status`.

The GELF boundary also protects older or dynamically-built records that still
send a generic `status` extra. Integer values become `_http_status`; other
values become the string `_event_status`. It never emits `_status`. A
non-numeric `http_status` is isolated as `_event_http_status` instead of being
sent to the numeric field, and other `*_status` values are serialized as
strings. This keeps new records compatible with indexes where the legacy
`_status` field is already mapped as a number.

## Log Event Inventory

The current event inventory is:

| Level | Event | Where | Key extra fields |
| ------- | ------- | ------- | ----------------- |
| DEBUG | `REQUEST` | `before_request` | ip, request_id, method, path, qs |
| DEBUG | `RESPONSE` | `after_request` | ip, request_id, method, path, http_status, size |
| DEBUG | `REQUEST_SESSION_RESOLUTION_FAILED` | `errorhandler(500)` | method, path, request_id (+ traceback) |
| DEBUG | `RUNTIME_BOOTSTRAP_STEP_STARTED` | runtime bootstrap | step, runtime |
| DEBUG | `RUNTIME_BOOTSTRAP_STEP_COMPLETED` | runtime bootstrap | step, runtime |
| DEBUG | `RUNTIME_BOOTSTRAP_STEP_SKIPPED` | runtime bootstrap | step, reason, runtime |
| DEBUG | `PROCESS_RUNTIME_INIT_STARTED` | process tracking startup | force, redis_configured, fake_redis |
| DEBUG | `PROCESS_RUNTIME_INIT_SKIPPED` | process tracking startup | reason, redis_mode |
| DEBUG | `DB_INIT_LOCK_WAITING` | database startup lock | backend, lock_path |
| DEBUG | `DB_INIT_LOCK_ACQUIRED` | database startup lock | backend, lock_path, wait_ms |
| DEBUG | `DB_INIT_LOCK_RELEASED` | database startup lock | backend, lock_path |
| DEBUG | `ACTIVE_RUN_METADATA_STARTUP_CLEANUP_SKIPPED` | active-run startup cleanup | reason, pid |
| DEBUG | `KILL_MISS` | `kill_command` | ip, run_id, session, team_id, actor_member_id, team_role |
| DEBUG | `HEALTH_OK` | `health()` | — |
| DEBUG | `ACTIVE_RUNS_VIEWED` | `get_active_history_runs` | ip, session, count |
| DEBUG | `HISTORY_DELETE_MISS` | `delete_run` | ip, run_id, session |
| DEBUG | `THEME_SELECTED` | current theme resolution | ip, session, route, theme, source |
| DEBUG | `CMD_PIPE` | `run_command` | ip, session, cmd, pipe_to |
| DEBUG | `HISTORY_COMMANDS_VIEWED` | `get_history_commands` | ip, session, count, limit |
| DEBUG | `SESSION_RUN_COUNT_VIEWED` | `session_run_count` | ip, session, session_kind, count |
| DEBUG | `STARRED_COMMANDS_VIEWED` | `session_starred_list` | ip, session, session_kind, count |
| DEBUG | `API_OPENAPI_FETCHED` | `api_openapi` | ip |
| DEBUG | `API_RUN_STREAM_ATTACHED` | API run stream routes | ip, session, run_id, after_id, format |
| DEBUG | `BROKER_STREAM_CLIENT_GONE` | `stream_run_events` | run_id, reason |
| DEBUG | `BROKER_STREAM_REATTACHED` | `stream_run_events` | run_id, after_id |
| DEBUG | `BROKER_REDIS_TRIM_RETRY` | broker Redis replay trimming | key, maxlen, reason |
| DEBUG | `ADVISORY_LOCK_ACQUIRED` | Schema migration runner | namespace, lock_id |
| DEBUG | `PTY_METRIC_WRITE_FAILED` | PTY service metrics writes | run_id, metric, error |
| DEBUG | `PTY_CONTROL_APPLIED` | interactive PTY control handling | run_id, action, bytes/rows/cols |
| DEBUG | `DIAG_REDIS_SCAN_KEY_FAILED` | `/diag` Redis probes | stage, error |
| DEBUG | `METRICS_INTEL_CACHE_COLLECT_FAILED` | Prometheus runtime collector | (+ traceback) |
| DEBUG | `METRICS_AI_ASSIST_COLLECT_FAILED` | Prometheus runtime collector | (+ traceback) |
| DEBUG | `AI_WORKER_TICK` | AI worker loop | processed |
| DEBUG | `AI_WORKER_DEPENDENCIES_LOADING` | AI worker startup | — |
| DEBUG | `AI_WORKER_DEPENDENCIES_SKIPPED` | AI worker startup | reason |
| DEBUG | `AI_ASSIST_PROGRESS_UPDATE_FAILED` | AI worker progress storage | assist_id, run_id (+ traceback) |
| DEBUG | `AI_COORDINATION_LEGACY_SLOT_DELETE_FAILED` | AI Redis coordination cleanup | (+ traceback) |
| DEBUG | `NOTIFICATION_WORKER_TICK` | notification worker | delivered, limit |
| DEBUG | `NOTIFICATION_HTTP_REQUEST` | notification HTTP channels | label, host, timeout, test_send |
| DEBUG | `NOTIFICATION_HTTP_RESPONSE` | notification HTTP channels | label, http_status, test_send |
| DEBUG | `INTEL_HTTP_RESPONSE` | intel provider HTTP client | provider_host, method, path, http_status, response_bytes, elapsed_ms |
| DEBUG / WARN | `PROJECT_OVERVIEW_INTEL_PAYLOAD_SKIPPED` | Project overview intel normalization | session, team_id, project_id, entity_id, snapshot_id, provider, provider_status, shape |
| DEBUG | `NOTIFICATION_SMTP_SEND_ATTEMPT` | notification email channel | host, port, tls_mode, timeout, channel_id |
| DEBUG | `SCHEDULE_FIRE_CLAIMED` | scheduler dispatch | schedule_id, owner_kind, session, claimed, fired_at, command_root |
| DEBUG | `BODY_STORE_DELETE_MISS` | large body storage | rel_path, kind |
| DEBUG | `CONFIG_SOURCE_SELECTED` | config loading | conf_dir, local_conf_dir, local_overlay |
| DEBUG | `CONFIG_OVERLAY_INVENTORY` | app startup | supported_local_overlays, present_local_overlays |
| DEBUG | `CONFIG_OVERLAY_CHECKED` | config loading | source, present, known_keys, unknown_keys |
| DEBUG | `CONFIG_OVERLAY_APPLIED` | config loading | source, known_keys, unknown_keys |
| DEBUG | `CONFIG_ENV_OVERRIDES_APPLIED` | config loading | env_keys |
| DEBUG | `CONFIG_LEGACY_KEY_MIGRATED` | config loading | legacy_key, target_key, source |
| DEBUG | `ATLAS_LOOKUP_CANDIDATES_RESOLVED` | exact Atlas lookup resolver | session, entity_type, scope_kind, project_scoped, lookup_role, row_count, preferred_count, direct_team_preferred, match_state, candidates_truncated, duration_ms |
| DEBUG / WARN | `ATLAS_LOOKUP_REJECTED` | browser/API exact Atlas lookup routes | ip, session, request_id, team_id, surface, reason, scope_kind, project_scoped, http_status, duration_ms; rejected project scope also includes project_id and uses WARNING |
| DEBUG | `ATLAS_QUICK_LOOKUP_REQUEST_STARTED` / `SETTLED` / `DISCARDED` | browser Quick Lookup state through `/log` | ip, session, context, client_details with lookup_mode, detected_type, match_state, scope_kind, project_scoped, candidate_count, parent_candidate, request_seq, reason, duration_ms |
| INFO | `LOGGING_CONFIGURED` | `configure_logging` | level, format |
| INFO | `CONFIG_VALIDATED` | config loading | schema_field_count, derived_keys, warning_count |
| INFO | `CONFIG_LOADED` | app startup | conf_dir, local_conf_dir, local_overlay, supported_local_overlays, overlays, database_backend, workspace_enabled, raw_packet_scanning_configured, raw_packet_scanning_state, raw_packet_scanning_active_tools, raw_packet_scanning_unavailable_tools, per-tool raw_packet_*_active/reason, log_level, log_format, warning_count, schema_field_count, env_key_count, legacy_key_migrated |
| INFO | `APP_INITIALIZED` | app startup | app_version, database_backend, workspace_enabled, pid, app_name, blueprint_count, before_request_handlers, after_request_handlers, limiter_storage, duration_ms |
| INFO | `RUNTIME_BOOTSTRAP_COMPLETED` | runtime bootstrap | runtime, init_metrics, init_logging, init_process, init_db, cleanup_active_runs, duration_ms |
| INFO | `METRICS_ENVIRONMENT_CONFIGURED` | metrics startup | prometheus_multiproc_dir, source, app_start_time_set |
| INFO | `DB_BACKEND_SELECTED` | `db_init` | backend |
| INFO | `POSTGRES_POOL_OPENED` | Postgres backend pool | pool_min, pool_max, jit_enabled |
| INFO | `POSTGRES_POOL_CLOSED` | Postgres backend pool | — |
| INFO | `REDIS_CONNECTED` | process tracking startup | redis_scheme, redis_host, redis_port, redis_db |
| INFO | `REDIS_FAKE_ENABLED` | process tracking startup | fallback |
| INFO | `REDIS_FALLBACK_IN_PROCESS` | process tracking startup | redis_configured, workers, fallback |
| INFO | `ACTIVE_RUN_METADATA_STARTUP_CLEANUP` | active-run startup cleanup | metadata_removed, session_members_removed, team_members_removed, pid, cleanup_owner, lock_type |
| INFO | `MIGRATION_APPLIED` | Schema migration runner | migration_version, migration_name |
| INFO | `CVE_RISK_BOOTSTRAP_LOADED` | bundled public-risk bootstrap | source, source_version, record_count, origin |
| INFO | `CVE_RISK_REFRESH_COMPLETED` | public-risk feed refresh | source, source_version, record_count, outcome, attempt |
| INFO | `CVE_ADVISORY_LOCAL_LOADED` | local NVD advisory loader | source, source_version, record_count, transition_count |
| INFO | `CVE_ADVISORY_LOOKUP_STORED` | explicit Atlas CVE Intel refresh | source, outcome, record_count |
| INFO | `RISK_ESCALATION_CREATED` | changed-CVE work processor | source, transition_kind, feed_version, owner_kind, observation_count, project_count, model_changed |
| INFO | `PROJECT_RISK_ESCALATION_ACK_UPDATED` | Project Monitoring risk-event route | ip, session, team_id, project_id, escalation_id, ack_state, note_chars |
| INFO | `PROJECT_ASSESSMENT_CREATED` | Project assessment create route | ip, session, team_id, project_id, assessment_id, profile_key, profile_version, check_count |
| INFO | `PROJECT_ASSESSMENT_UPDATED` | Project assessment lifecycle route | ip, session, team_id, project_id, assessment_id, from_status, to_status, transition_kind, title_changed |
| INFO | `PROJECT_ASSESSMENT_DELETED` | Project assessment deletion route | ip, session, team_id, project_id, assessment_id, check_count, evidence_count |
| INFO | `PROJECT_ASSESSMENT_CHECK_STATE_CHANGED` | Project assessment check route | ip, session, team_id, project_id, assessment_id, check_id, check_key, policy_level, from_state, to_state, manual_override_cleared |
| INFO | `PROJECT_ASSESSMENT_EVIDENCE_LINKED` | Project assessment evidence route | ip, session, team_id, project_id, assessment_id, check_id, evidence_type, evidence_id, from_state, to_state, manual_state_preserved |
| INFO | `PROJECT_ASSESSMENT_EVIDENCE_UNLINKED` | Project assessment evidence route | ip, session, team_id, project_id, assessment_id, check_id, evidence_type, evidence_id, from_state, to_state, manual_state_preserved |
| INFO | `API_PROJECT_ASSESSMENT_CREATED` | API v1 Project assessment create route | ip, session, team_id, project_id, assessment_id, source, profile_key, profile_version, check_count |
| INFO | `API_PROJECT_ASSESSMENT_UPDATED` | API v1 Project assessment lifecycle route | ip, session, team_id, project_id, assessment_id, source, from_status, to_status, transition_kind, title_changed |
| INFO | `API_PROJECT_ASSESSMENT_DELETED` | API v1 Project assessment deletion route | ip, session, team_id, project_id, assessment_id, source, check_count, evidence_count |
| INFO | `API_PROJECT_ASSESSMENT_CHECK_STATE_CHANGED` | API v1 Project assessment check route | ip, session, team_id, project_id, assessment_id, check_id, source, check_key, policy_level, from_state, to_state, manual_override_cleared |
| INFO | `API_PROJECT_ASSESSMENT_EVIDENCE_LINKED` | API v1 Project assessment evidence route | ip, session, team_id, project_id, assessment_id, check_id, source, evidence_type, evidence_id, from_state, to_state, manual_state_preserved |
| INFO | `API_PROJECT_ASSESSMENT_EVIDENCE_UNLINKED` | API v1 Project assessment evidence route | ip, session, team_id, project_id, assessment_id, check_id, source, evidence_type, evidence_id, from_state, to_state, manual_state_preserved |
| INFO | `GUNICORN_WORKER_BOOTED` | Gunicorn worker hook | pid |
| INFO | `GUNICORN_CHILD_EXIT` | Gunicorn worker hook | pid, hook |
| INFO | `GUNICORN_WORKER_EXIT` | Gunicorn worker hook | pid, hook |
| INFO | `CMD_REWRITE` | `run_command` | ip, original, rewritten |
| INFO | `REQUEST_COMPLETED` | `after_request` | ip, session, request_id, method, path, endpoint, http_status, duration_ms |
| INFO | `RUN_START` | `run_command` | ip, run_id, session, pid, cmd, cmd_type, scan_transport (raw/connect scanner runs only) |
| INFO | `RUN_END` | run finalization | ip, run_id, session, exit_code, elapsed, cmd, cmd_type, output_line_count, artifact_count, finding_count, atlas_entity_count, version_inference_count, full_output_truncated |
| INFO | `RUN_OUTPUT_ARTIFACT_OPENED` | full-output artifact capture | run_id, rel_path, format_version |
| INFO | `RUN_OUTPUT_ARTIFACT_FINALIZED` | full-output artifact capture | run_id, rel_path, artifact_bytes, lines, truncated, available |
| INFO | `WORKFLOW_EXECUTION_STARTED` | durable workflow route | execution_id, workflow_id, workflow_source, step_count, team_id, session, ip |
| INFO | `WORKFLOW_STEP_STARTED` | workflow execution engine | execution_id, step_id, run_id, cmd_type |
| INFO | `WORKFLOW_STEP_COMPLETED` | workflow execution engine | execution_id, step_id, step_status, exit_code, duration_ms, transition, transition_reason |
| INFO | `WORKFLOW_EXECUTION_COMPLETED` | workflow execution engine | execution_id, workflow_status, duration_ms |
| INFO | `WORKFLOW_EXECUTION_CANCELED` | durable workflow route | execution_id, run_id, step_count, duration_ms, team_id, session, ip |
| INFO | `WORKFLOW_RECOVERY_COMPLETED` | workflow startup recovery | examined, recovered, left_running, failed, ignored, errors, pid, recovery_owner |
| INFO | `PTY_SESSION_STARTED` | interactive PTY service | ip, run_id, session, pid, cmd, rows, cols, allow_input |
| INFO | `PTY_SESSION_ENDED` | interactive PTY service | ip, run_id, session, exit_code, elapsed, cmd |
| INFO | `PTY_OWNERSHIP_DISPLACED` | interactive PTY ownership claim | run_id, session, owner_client_id, owner_tab_id, displaced_client_id, displaced_tab_id |
| INFO | `PTY_SNAPSHOT_PERSISTED` | interactive PTY service | run_id, session, rows, cols, forced |
| INFO | `RUN_KILL` | `kill_command` | ip, run_id, session, team_id, actor_member_id, team_role, pid, pgid |
| INFO | `TEAM_ACTION` | browser/API team management routes | action, team_id, session, ip, result, source, team_status, actor_member_id/target ids |
| INFO | `TEAM_ARCHIVE_AUTOMATION_PAUSED` | browser/API team management routes | action, team_id, session, ip, source, team_status, paused_watchers, paused_schedules |
| INFO | `DB_PRUNED` | `db_init` | runs, snapshots, retention_days |
| INFO | `API_RUN_STARTED` | API run start routes | ip, session, run_id, cmd, cmd_type, project_id |
| INFO | `API_ARTIFACT_DOWNLOADED` | API artifact download route | ip, session, run_id, artifact_id, byte_size |
| INFO | `PACKAGE_BUILD_STARTED` | evidence package archive builder | session, project_id, package_id, redaction_mode |
| INFO | `PACKAGE_BUILD_COMPLETED` | evidence package archive builder | session, project_id, package_id, archive_bytes, projected_bytes, duration_ms, skipped_items, redacted_artifacts |
| INFO | `PAGE_LOAD` | `index` | ip, session, theme |
| INFO | `CONTENT_VIEWED` | content routes | ip, session, route, count/restricted/current/key_count |
| INFO | `SESSION_TOKEN_GENERATED` | `session_token_generate` | ip, session, session_kind |
| INFO | `SESSION_TOKEN_REVOKED` | `session_token_revoke` | ip, session, session_kind, revoked_current |
| INFO | `SESSION_MIGRATED` | `session_migrate` | ip, session, from_session_kind, to_session_kind, migrated_runs, migrated_snapshots, migrated_stars, migrated_preferences |
| INFO | `SESSION_PREFERENCES_SAVED` | `session_preferences_save` | ip, session, session_kind, key_count |
| INFO | `STARRED_COMMAND_ADDED` | `session_starred_add` | ip, session, session_kind, command_root, changed |
| INFO | `STARRED_COMMAND_REMOVED` | `session_starred_remove` | ip, session, session_kind, command_root, count |
| INFO | `STARRED_COMMANDS_CLEARED` | `session_starred_remove` | ip, session, session_kind, count |
| INFO | `SHARE_CREATED` | `save_share` | ip, session, share_id, label, redacted, run_id, included_artifacts, redaction_mode |
| INFO | `SHARE_VIEWED` | `get_share` | ip, session, share_id, label |
| INFO | `SHARE_DELETED` | `delete_share` | ip, session, share_id, deleted |
| INFO | `RUN_VIEWED` | `get_run` | ip, run_id, cmd |
| INFO | `RUN_COMPARISON_VIEWED` | `compare_history_runs` | owner_scope, project_scoped, left_run_id, right_run_id, duration_ms, left/right output sources, finding-change counts, derived_group_ids, output/changed-lines/findings/artifacts/derived truncation flags, comparison_partial |
| INFO | `HISTORY_VIEWED` | `get_history` | ip, session, count, q, output_search, command_root, exit_code_filter, date_range |
| INFO | `ATLAS_LOOKUP_COMPLETED` / `API_ATLAS_LOOKUP_COMPLETED` | browser/API exact Atlas lookup routes | ip, session, request_id, team_id, surface, requested_type, detected_type, match_state, scope_kind, project_scoped, candidate_count, candidates_truncated, parent_candidate, detail_loaded, duration_ms |
| INFO | `ATLAS_RUN_CLEANED` | Atlas cleanup route | ip, session, run_id, include_curated, detached_entities, detached_findings, deleted_entities, deleted_findings |
| INFO | `ATLAS_ENTITY_SUPPRESSION_UPDATED` | Atlas suppression routes | ip, session, entity_id/count, suppressed, reason, bulk |
| INFO | `ATLAS_FINDING_SUPPRESSION_UPDATED` | Atlas suppression routes | ip, session, finding_id/count, suppressed, reason, bulk |
| INFO | `ATLAS_SAVED_VIEW_CREATED` | Atlas saved-view routes | ip, session, view_id, name |
| INFO | `ATLAS_SAVED_VIEW_UPDATED` | Atlas saved-view routes | ip, session, view_id, name |
| INFO | `ATLAS_SAVED_VIEW_DELETED` | Atlas saved-view routes | ip, session, view_id |
| INFO | `ATLAS_IMPORT_PREVIEW_CREATED` | Atlas import preview workflow | session, team_id, actor_member_id, actor_role, draft_id, format_id, source_tool_key, upload_bytes, expires_at, has_filename, filename_present, rows/valid/skipped/warnings/new/updated/entity/finding/project-target counts |
| INFO | `ATLAS_IMPORT_PREVIEW_SUCCEEDED` | Atlas import preview route | ip, session, team_id, actor_member_id, actor_role, draft_id, format_id, source_tool_key, has_file, filename_present, content_length, expires_at, rows/valid/skipped/warnings/new/updated/entity/finding/project-target counts |
| INFO | `ATLAS_IMPORT_APPLIED` | Atlas import apply workflow | session, team_id, actor_member_id, actor_role, draft_id, batch_id, project_id, format_id, source_tool_key, required_capabilities, option_import_entities, option_import_findings, option_link_to_project, option_create_project_targets, entity/finding/source/project count fields |
| INFO | `ATLAS_IMPORT_APPLY_SUCCEEDED` | Atlas import apply route | ip, session, team_id, actor_member_id, actor_role, draft_id, batch_id, project_id, already_applied, format_id, option_import_entities, option_import_findings, option_link_to_project, option_create_project_targets, entity/finding/source/project count fields |
| INFO | `ATLAS_IMPORT_APPLY_REPLAYED` | Atlas import apply workflow | session, team_id, actor_member_id, actor_role, draft_id, batch_id, project_id, draft_status, option_import_entities, option_import_findings, option_link_to_project, option_create_project_targets, entity/finding/source/project count fields |
| INFO | `ATLAS_IMPORT_DRAFTS_CLEANED` | Atlas import draft cleanup | previewed_count, applying_count, cutoff |
| INFO | `SECRET_STORED` | secrets vault storage | session, secret_name, consumer_envs, is_new_secret |
| INFO | `SECRET_RETRIEVED` | secrets vault storage | session, consumer_envs |
| INFO | `VAULT_KEY_LOADED` | secrets vault | source |
| INFO | `VAULT_KEY_ROTATION_COMPLETED` | secrets vault storage | session, count |
| INFO | `INTEL_PROVIDER_LOOKUP_COMPLETED` | Atlas intel refresh | session, entity_id, provider, provider_status |
| INFO | `NOTIFICATION_ENQUEUED` | notification dispatcher | trigger, queued, run_id, session |
| INFO | `NOTIFICATION_DISPATCHED` | notification dispatcher | event_id, channel_id, trigger, session |
| INFO | `NOTIFICATION_DEFERRED` | notification dispatcher | event_id, channel_id, trigger, session, reason |
| INFO | `NOTIFICATION_EVENTS_PRUNED` | notification dispatcher | count, retention_days |
| DEBUG | `SCHEDULER_TICK` | scheduler worker | now, limit, due_count |
| DEBUG | `SCHEDULE_FIRE_DISPATCH` | scheduler dispatch | schedule_id, owner_kind, session, team_id, fired_at, command_root |
| DEBUG | `SCHEDULE_RUN_PREPARED` | scheduler dispatch | schedule_id, team_id, dispatch_path, command_root |
| DEBUG | `SCHEDULE_PERSISTED` | scheduler storage | schedule_id, owner_kind, enabled, cron_expr, cadence_preset, timezone, next_run_at |
| DEBUG | `SCHEDULE_STATE_UPDATED` | scheduler storage | schedule_id, owner_kind, enabled, cron_expr, cadence_preset, timezone, next_run_at |
| DEBUG | `SCHEDULE_AFTER_FIRE_UPDATED` | scheduler storage | schedule_id, owner_kind, run_id, fired_at, next_run_at, consecutive_failures |
| DEBUG | `SCHEDULE_PREVIEW_GENERATED` | browser schedule routes | ip, session, team_id, cron_expr, cadence_preset, timezone, next_fire_count |
| DEBUG | `SCHEDULES_LISTED` | browser schedule routes | ip, session, team_id, count |
| DEBUG | `SCHEDULE_FIRES_LISTED` | browser schedule routes | ip, session, team_id, schedule_id, count, total, limit, offset |
| DEBUG | `API_SCHEDULES_LISTED` | API schedule routes | ip, session, team_id, count, limit, offset |
| DEBUG | `API_SCHEDULE_FIRES_LISTED` | API schedule routes | ip, session, team_id, schedule_id, count, total, limit, offset |
| DEBUG | `PROJECT_AUTO_PROMOTE_RULE_PREVIEWED` | Project auto-promote preview route | ip, session, team_id, actor_member_id, actor_role, project_id, target_entity_kind, match_mode, matched/new/promotable/quota/cap counts, limit, truncated |
| DEBUG | `PROJECT_AUTO_PROMOTE_MATCH_SCAN` | Project auto-promote matching service | session, team_id, project_id, rule_id, target_entity_kind, match_mode, source filter counts, sql_matched, include_suppressed, scan/candidate/match/quota/cap counts, limit, truncated |
| DEBUG | `PROJECT_AUTO_PROMOTE_LINK_DECISION_SUMMARY` | Project auto-promote apply service | session, team_id, project_id, run_id, rule_id, target_entity_kind, match_mode, source filter counts, linked/promoted/already-linked/new/quota/cap counts, limit, truncated |
| DEBUG | `OUTPUT_SIGNAL_PORT_ENTITY_SKIPPED` | output signal classifier | command_root, line_index, reason, port, proto, host_kind, host_hash |
| DEBUG | `ATLAS_ENTITY_MATERIALIZATION_SUMMARY` | Atlas entity materializer | session, team_id, run_id, command_root, entity/occurrence/invalid/port/url/url-host/attribute/scan-observation counts |
| INFO | `ATLAS_URL_HOST_BACKFILL_COMPLETED` | startup URL host-link backfill | backend, url_entity_count, updated_count, skipped_count |
| WARN | `ATLAS_URL_HOST_BACKFILL_SKIPPED_ROWS` | startup URL host-link backfill | backend, url_entity_count, invalid_url_count, host_upsert_miss_count, update_miss_count |
| ERROR | `ATLAS_URL_HOST_BACKFILL_ROW_FAILED` | startup URL host-link backfill | backend, stage, url_entity_id, session, team_id, host_entity_type |
| DEBUG | `SCAN_TARGET_OBSERVATIONS_SKIPPED` | Atlas entity materializer | session, team_id, run_id, command_root, deleted_count, reason |
| DEBUG | `ATLAS_ENTITY_ATTRIBUTES_DROPPED` | Atlas entity materializer | session, team_id, run_id, entity_id, entity_type, value_type, reason |
| DEBUG | `ATLAS_IMPORT_PARSE_STARTED` | Atlas import parser | format_id, upload_bytes, max_rows, max_warnings, max_xml_elements |
| DEBUG | `ATLAS_IMPORT_PARSE_COMPLETED` | Atlas import parser | format_id, upload_bytes, rows, entities, findings, skipped, warning_count, suppressed_warning_count, warning_codes, max_rows, max_warnings, max_xml_elements |
| DEBUG | `AI_CONTEXT_BUILT` | AI context assembly | run_id, session, variant, output_source, output_truncated, max_input_chars, input_chars, estimated_input_tokens, redacted_bytes, pre_redaction_bytes, useful, omitted_sections, section_count, context_hash |
| DEBUG | `AI_SUGGESTION_VALIDATION_COMPLETED` | AI suggestion validation | suggestion_count, accepted_count, rejected_count, rejection_reasons, trusted_target_count, known_port_count |
| DEBUG | `AI_WORKER_BUSY` | AI worker coordination | max_concurrent |
| DEBUG | `HTTPX_SCREENSHOT_OUTPUT_CLEANED` | HTTPx screenshot finalization | run_id, session, team_id, candidate_count, invalid_count, retained_count, removed_count, cleanup_failed_count, protected_cleanup_skip_count, protected_lookup_failed, protected_lookup_error, candidate_truncated |
| DEBUG | `OAST_PROVIDER_RETRY_SUPPRESSED` | private OAST retry suppression | retry_event, correlation_id when applicable, correlation_status, correlation_count when applicable, attempt, retryable, next_retry_seconds, occurrence_count, suppressed_repeat_count, error_class, error_code |
| DEBUG | `OAST_PROVIDER_CALL_COMPLETED` | private OAST provider calls | correlation_id, phase, duration_ms, attempt, accepted_count, rejected_count, duplicate_count |
| INFO | `SCHEDULE_CREATED` | browser schedule routes | ip, session, team_id, source, schedule_id, enabled, cron_expr, cadence_preset, timezone, next_run_at |
| INFO | `SCHEDULE_UPDATED` | browser schedule routes | ip, session, team_id, source, schedule_id, changed_fields, enabled, next_run_at |
| INFO | `SCHEDULE_DELETED` | browser schedule routes | ip, session, team_id, source, schedule_id, removed |
| INFO | `PROJECT_AUTO_PROMOTE_RULE_CREATED` / `UPDATED` / `DELETED` | Project auto-promote rule routes | ip, session, team_id, actor_member_id, actor_role, project_id, rule_id, enabled, apply_on_run, target_entity_kind, match_mode |
| INFO | `PROJECT_AUTO_PROMOTE_RULE_APPLIED` | Project auto-promote apply route | ip, session, team_id, actor_member_id, actor_role, project_id, rule_id, target_entity_kind, match_mode, matched/linked/promoted/skipped/quota/cap counts, limit, truncated |
| INFO | `PROJECT_AUTO_PROMOTE_RUN_APPLIED` | run finalization | run_id, session, team_id, project_ids, rule_ids, bounded rule_results, aggregate match/link/promote/quota/cap counts |
| INFO | `PROJECT_UPDATED` | Project update route | ip, session, project_id, project_status |
| INFO | `ATLAS_ENTITIES_CAPTURED` | run finalization | run_id, session, team_id, count, entity_type_counts, port_entity_count, scan_observation_count |
| INFO | `NMAP_VERSION_INFERENCE_FINALIZED` | run finalization | run_id, session, team_id, observation_count, candidate_count, attempted_count, materialized_count, finding_created_count, source_created_count, rejected_count, skipped_count, truncated |
| WARN | `NMAP_VERSION_INFERENCE_ARTIFACT_REJECTED` | run finalization | run_id, session, team_id, marked_artifact_count |
| ERROR | `NMAP_VERSION_INFERENCE_FINALIZE_ERROR` | run finalization | run_id, session, team_id, error_class |
| INFO | `SCHEDULE_RUN_NOW` | browser schedule routes | ip, session, team_id, source, schedule_id, fire_status, fired_at, run_id, last_error |
| INFO | `API_SCHEDULE_CREATED` | API schedule routes | ip, session, team_id, source, schedule_id, enabled, cron_expr, cadence_preset, timezone, next_run_at |
| INFO | `API_SCHEDULE_UPDATED` | API schedule routes | ip, session, team_id, source, schedule_id, changed_fields, enabled, next_run_at |
| INFO | `API_SCHEDULE_DELETED` | API schedule routes | ip, session, team_id, source, schedule_id, removed |
| INFO | `API_SCHEDULE_RUN_NOW` | API schedule routes | ip, session, team_id, source, schedule_id, fire_status, fired_at, run_id, last_error |
| INFO | `BUILTIN_SCHEDULE_CREATED` | terminal schedule built-in | session, source, schedule_id, enabled, cron_expr, cadence_preset, timezone, next_run_at |
| INFO | `BUILTIN_SCHEDULE_PAUSED` | terminal schedule built-in | session, source, schedule_id, enabled |
| INFO | `BUILTIN_SCHEDULE_RESUMED` | terminal schedule built-in | session, source, schedule_id, enabled, next_run_at |
| INFO | `BUILTIN_SCHEDULE_DELETED` | terminal schedule built-in | session, source, schedule_id, removed |
| INFO | `BUILTIN_SCHEDULE_RUN_NOW` | terminal schedule built-in | session, source, schedule_id, fire_status, fired_at, run_id, last_error |
| INFO | `WATCHER_ROUTE_RUN_NOW` | browser watcher routes | ip, session, team_id, source, watcher_id, schedule_id, fire_status, fired_at, run_id, last_error |
| INFO | `API_WATCHER_RUN_NOW` | API watcher routes | ip, session, team_id, source, watcher_id, schedule_id, fire_status, fired_at, run_id, last_error |
| INFO | `BUILTIN_WATCH_RUN_NOW` | terminal watcher built-in | session, source, watcher_id, schedule_id, fire_status, fired_at, run_id, last_error |
| INFO | `BUILTIN_NOTIFY_CREATED` | terminal notify built-in | session, source, channel_id, kind, muted |
| INFO | `BUILTIN_NOTIFY_UPDATED` | terminal notify built-in | session, source, channel_id, muted |
| INFO | `BUILTIN_NOTIFY_MUTED` | terminal notify built-in | session, source, channel_id |
| INFO | `BUILTIN_NOTIFY_UNMUTED` | terminal notify built-in | session, source, channel_id |
| INFO | `BUILTIN_NOTIFY_DELETED` | terminal notify built-in | session, source, channel_id, removed |
| INFO | `SCHEDULE_FIRED` | scheduler dispatch | schedule_id, owner_kind, session, team_id, run_id, fired_at, next_run_at, command_root |
| INFO | `SCHEDULE_FIRE_SKIPPED_OVERLAP` | scheduler dispatch | schedule_id, session, team_id, run_id, fired_at, active_run_count, command_root |
| INFO | `WATCHER_FIRED` | watcher scheduler hook | watcher_id, schedule_id, run_id, baseline_run_id, session, fired_at |
| INFO | `WATCHER_SCHEDULE_FIRED` | scheduler dispatch | schedule_id, owner_kind, session, team_id, run_id, fired_at, command_root |
| INFO | `WATCHER_UPDATED` | watcher service | watcher_id, schedule_id, session |
| INFO | `WATCHER_BASELINE_ACCEPTED` | watcher service | watcher_id, baseline_run_id, session |
| INFO | `WATCHER_CHANGED` | watcher finalization | watcher_id, schedule_id, session, state, run_id, notification_count |
| INFO | `WATCHER_RECOVERED` | watcher finalization | watcher_id, schedule_id, session, state, run_id, notification_count |
| INFO | `AI_RATE_LIMIT_SESSION_BYPASSED` | AI route rate limiting | ip, session, variant |
| INFO | `AI_ASSIST_ENQUEUE_RESULT` | AI assist route enqueue | assist_id, run_id, session, variant, assist_status, inserted, force, model, prompt_version, prompt_version_source, input_chars, estimated_input_tokens, redacted_bytes, pre_redaction_bytes |
| INFO | `AI_WORKER_DEPENDENCIES_LOADED` | AI worker startup | variants, metrics_initialized |
| INFO | `AI_WORKER_STARTED` | AI worker startup | — |
| INFO | `AI_ASSIST_PROVIDER_REQUEST` | AI provider call start | assist_id, run_id, variant, model, connect_timeout_seconds, read_timeout_seconds |
| INFO | `AI_ASSIST_COMPLETED` | AI worker completion | assist_id, run_id, variant, duration_ms, context_hash, input_chars, output_chars, estimated_input_tokens, redacted_bytes, suggestion_count, rejected_count, provider timing fields |
| INFO | `AI_ASSIST_SUMMARY_FALLBACK` | AI summary orchestration | assist_id, run_id, variant, reason |
| INFO | `AI_ASSIST_NEXT_COMMANDS_FALLBACK` | AI next-command orchestration | assist_id, run_id, variant, reason |
| INFO | `AI_WORKER_STOPPED` | AI worker shutdown | — |
| INFO | `NOTIFICATION_WORKER_STARTED` | notification worker | pid, poll_seconds, limit |
| INFO | `NOTIFICATION_WORKER_STOPPED` | notification worker | pid |
| INFO | `SCHEDULER_WORKER_STARTED` | scheduler worker | tick_seconds, limit, database_backend, lock_type, lock_path |
| INFO | `SCHEDULER_WORKER_LOCK_HELD` | scheduler worker | tick_seconds, limit, database_backend, lock_type, lock_path |
| INFO | `SCHEDULER_WORKER_STOPPED` | scheduler worker | tick_seconds, limit, database_backend, lock_type, lock_path |
| INFO | `ZAP_WORKER_STARTED` | ZAP connector worker | pid |
| INFO | `ZAP_WORKER_LOCK_HELD` | ZAP connector worker | — |
| INFO | `ZAP_WORKER_STOPPED` | ZAP connector worker | pid |
| INFO | `OAST_PROVIDER_SESSION_READY` | private OAST provider registration | correlation_id, correlation_status |
| INFO | `OAST_INTERACTIONS_INGESTED` | private OAST interaction ingestion | correlation_id, correlation_status, accepted_count, rejected_count, duplicate_count |
| INFO | `OAST_PROVIDER_SESSION_CLEANED` | private OAST terminal cleanup | correlation_id, correlation_status |
| INFO | `SCHEDULER_RECOVERY_APPLIED` | scheduler recovery | fired, skipped |
| WARN | `FTS_SEARCH_FALLBACK` | `get_history` | session, q, error |
| INFO | `HISTORY_DELETED` | `delete_run` | ip, run_id, session, cleanup flags, removed/curated/kept counts |
| INFO | `PROJECT_LINK_REMOVED` | Project unlink route | project_id, entity_type, entity_id, cleanup flags, unlinked/curated/kept counts |
| INFO | `HISTORY_CLEARED` | `clear_history` | ip, session, count |
| INFO | `DIAG_VIEWED` | `diag()` | ip |
| WARN | `RUN_NOT_FOUND` | `get_run` | ip, run_id |
| WARN | `SHARE_NOT_FOUND` | `get_share` | ip, share_id |
| WARN | `CMD_DENIED` | `run_command` | ip, session, cmd, reason, deny_kind, rule_id |
| WARN | `RAW_PACKET_SCANNING_UNAVAILABLE` | app startup | tool, reason, availability_reason |
| WARN | `CMD_MISSING` | `run_command` | ip, session, cmd |
| WARN | `API_AUTH_FAILED` | API auth error handler | ip, code, http_status |
| WARN | `PROJECT_HTTP_PROFILE_INVALID_TARGETS_SKIPPED` | Project HTTP-profile scope discovery | project_id, team_scope, invalid_target_count, invalid_target_types |
| WARN / ERROR | `TEAM_ACTION_REJECTED` / `TEAM_ROUTE_FAILED` / `TEAM_ACTION_FAILED` | browser/API team management routes | action, team_id, session, ip, result, source, reason, error_code, http_status, route, method |
| WARN | `API_BROKER_UNAVAILABLE` | API run start routes | ip, reason |
| WARN | `API_FULL_OUTPUT_LOAD_FAILED` | API output route | run_id, session, rel_path, error |
| WARN | `RUN_FULL_OUTPUT_INDEX_FALLBACK` | run finalization | run_id, session, rel_path, error |
| WARN | `BROKER_PUBLISH_FAILED` | broker event publish | run_id, event_type, reason, error |
| WARN | `PTY_INPUT_DROPPED` | interactive PTY control handling | run_id, session, reason, bytes |
| WARN | `PTY_INPUT_WRITE_FAILED` | interactive PTY control handling | run_id, session, bytes, error |
| WARN | `PTY_RESIZE_IOCTL_FAILED` | interactive PTY control handling | fd, rows, cols, error |
| WARN | `PTY_TERMINATE_FAILED` | interactive PTY cleanup | run_id, pid, cmd, error (+ traceback) |
| WARN | `PTY_STARTUP_CLEANUP_FAILED` | interactive PTY startup cleanup | run_id, stage, error (+ traceback) |
| WARN | `NOTIFICATION_CHANNEL_REGISTRY_MISS` | notification dispatcher | event_id, channel_id, kind |
| WARN | `NOTIFICATION_RETRIED` | notification dispatcher | event_id, channel_id, trigger, session, attempts, next_attempt_at, retryable, age_expired, max_attempts, error |
| WARN | `NOTIFICATION_DELIVERY_FAILED` | notification dispatcher | event_id, channel_id, trigger, session, attempts, retryable, age_expired, max_attempts, error |
| WARN | `NOTIFICATION_WORKER_DATABASE_INTERRUPTED` | notification worker | phase, limit, poll_seconds, error_type, sqlstate |
| WARN | `NOTIFICATION_HTTP_NETWORK_ERROR` | notification HTTP channels | label, host, error |
| WARN | `NOTIFICATION_SMTP_SEND_FAILED` | notification email channel | host, port, tls_mode, channel_id, error |
| WARN | `API_NOTIFICATION_CHANNEL_REJECTED` | API notification routes | ip, session, code, http_status, route, method |
| WARN | `SCHEDULER_CONFIG_INVALID` | scheduler config readers | key, value, fallback |
| WARN | `SCHEDULE_REQUEST_REJECTED` | browser schedule routes | ip, session, team_id, source, action, schedule_id, http_status, error |
| WARN | `API_SCHEDULE_REJECTED` | API schedule routes | ip, session, team_id, code, http_status, route, method, error |
| WARN | `WATCHER_REQUEST_REJECTED` | browser watcher routes | ip, session, source, action, watcher_id, http_status, error |
| WARN | `API_WATCHER_REJECTED` | API watcher routes | ip, session, code, http_status, route, method, error |
| WARN | `BUILTIN_SCHEDULE_REJECTED` | terminal schedule built-in | session, source, subcommand, error |
| WARN | `BUILTIN_NOTIFY_REJECTED` | terminal notify built-in | session, source, subcommand, error |
| WARN | `SCHEDULE_DISABLED_REVOKED` | scheduler dispatch | schedule_id, owner_kind, session, team_id, fired_at, next_run_at, command_root |
| WARN | `WATCHER_FIRE_SKIPPED_OVERLAP` | scheduler dispatch | schedule_id, owner_kind, session, team_id, run_id, fired_at, active_run_count, command_root |
| WARN | `WATCHER_ERROR` | watcher finalization | watcher_id, schedule_id, session, state, run_id, error, notification_count |
| WARN | `WATCHER_DIFF_FAILED` | watcher finalization | watcher_id, schedule_id, session, state, run_id, error |
| WARN | `WATCHER_DISABLED_AFTER_ERRORS` | watcher finalization | watcher_id, schedule_id, session, state, run_id, consecutive_failures |
| WARN | `WATCHER_BASELINE_DELETED` | run cleanup | watcher_id, baseline_run_id, session |
| WARN | `AI_RATE_LIMIT_REJECTED` | AI route rate limiting | ip, session, variant, error_code, retry_after_seconds, bypass_session_limit |
| WARN | `AI_ASSIST_JSON_DECODE_FAILED` | AI assist storage | assist_id, column |
| WARN | `AI_BASE_URL_ALLOWED_CIDR_INVALID` | config loading | cidr |
| WARN | `SCHEDULE_RECOVERY_SKIPPED_INVALID_NEXT_RUN` | scheduler recovery | schedule_id, owner_kind, next_run_at, fired_at |
| WARN | `SCHEDULE_RECOVERY_SKIPPED_STALE` | scheduler recovery | schedule_id, owner_kind, next_run_at, fired_at, catchup_window_seconds |
| WARN | `SCHEDULE_FIRE_CLAIM_TIME_INVALID` | scheduler dispatch | schedule_id, owner_kind, session, last_run_at, command_root |
| WARN | `SCHEDULER_WORKER_DATABASE_INTERRUPTED` | scheduler worker | phase, tick_seconds, limit, database_backend, lock_type, error_type, sqlstate |
| WARN | `SCHEDULER_LOCK_RELEASE_SKIPPED` | scheduler worker | phase, error_type, sqlstate |
| WARN | `ZAP_JOB_FAILED` | ZAP connector worker | job_id, phase, error_class |
| WARN | `ZAP_CANCEL_RETRY` | ZAP connector worker | job_id, error_class |
| WARN | `ZAP_CANCEL_CREDENTIAL_RETRY` | ZAP connector worker | job_id, error_class |
| WARN | `ZAP_PLAN_SPOOL_SCAN_DEGRADED` | private ZAP plan reconciliation | failure_count, error_classes, suppressed_repeat_count |
| WARN | `OAST_SESSION_SPOOL_SCAN_DEGRADED` | private OAST session reconciliation | failure_count, error_classes, suppressed_repeat_count |
| WARN | `OAST_SESSION_SPOOL_UNAVAILABLE` | private OAST readiness check | correlation_id, error_class, error_code, suppressed_repeat_count |
| WARN | `OAST_PROVIDER_CLEANUP_SCOPE_MISMATCH` | private OAST terminal cleanup | correlation_id, correlation_status, connector_disabled, privacy_acknowledgement_missing, callback_scope_changed, service_origin_changed, suppressed_repeat_count |
| WARN | `OAST_PROVIDER_SCOPE_RETRY` | private OAST scope recovery | correlation_id, correlation_status, attempt, retryable, next_retry_seconds, occurrence_count, suppressed_repeat_count, error_class, error_code |
| WARN | `OAST_PROVIDER_RETRY` | private OAST provider recovery | correlation_id, correlation_status, attempt, retryable, next_retry_seconds, occurrence_count, suppressed_repeat_count, error_class, error_code |
| WARN | `OAST_PROVIDER_CLEANUP_RETRY` | private OAST terminal cleanup | correlation_id, correlation_status, attempt, retryable, next_retry_seconds, occurrence_count, suppressed_repeat_count, error_class, error_code |
| WARN | `OAST_INTERACTION_REJECTED` | private OAST interaction ingestion | correlation_id, correlation_status, attempt, retryable, next_retry_seconds, occurrence_count, suppressed_repeat_count, error_class, error_code |
| WARN | `OAST_PROVIDER_CREDENTIAL_RETRY` | private OAST credential recovery | correlation_count, attempt, retryable, next_retry_seconds, occurrence_count, suppressed_repeat_count, error_class, error_code |
| WARN | `SCHEDULE_FIRE_LOOKUP_UNAVAILABLE` | scheduler history helper | run_count, error |
| WARN | `PROJECT_QUOTA_HIT` | project quota helper | reason |
| WARN | `CVE_RISK_BOOTSTRAP_UNAVAILABLE` | bundled public-risk bootstrap | reason |
| WARN | `CVE_RISK_REFRESH_RETRY` | public-risk feed refresh | source, attempt, max_attempts, error_type |
| WARN | `PROJECT_RISK_ESCALATION_ACK_REJECTED` | Project Monitoring risk-event route | ip, session, team_id, project_id, escalation_id, http_status, reason |
| WARN | `PROJECT_ROUTE_FAILED` | project download routes | ip, session, project_id, package_id, route, error |
| WARN | `PACKAGE_PRESETS_OVERRIDE_INVALID` | evidence package preset catalog loader | path, fallback_path, error |
| WARN | `PROJECT_AUTO_PROMOTE_RULE_PREVIEW_REJECTED` / `CREATE_REJECTED` / `UPDATE_REJECTED` / `APPLY_REJECTED` | Project auto-promote rule routes | ip, session, team_id, actor_member_id, actor_role, project_id, rule_id, target_entity_kind, match_mode, http_status, reason |
| WARN | `PROJECT_AUTO_PROMOTE_RULE_UPDATE_MISS` / `DELETE_MISS` / `APPLY_MISS` | Project auto-promote rule routes | ip, session, team_id, actor_member_id, actor_role, project_id, rule_id, http_status, reason |
| WARN | `PROJECT_AUTO_PROMOTE_QUOTA_LIMITED` | Project auto-promote apply service | session, team_id, project_id, run_id, rule_id, target_entity_kind, match_mode, quota_limited_count, linked_count, new_link_count, promoted_count |
| WARN | `PROJECT_AUTO_PROMOTE_MATCH_CAP_LIMITED` | Project auto-promote matching service | session, team_id, project_id, run_id, rule_id, target_entity_kind, match_mode, matched/candidate/cap counts, candidate_scan_limit, limit, truncated |
| WARN | `PROJECT_AUTO_PROMOTE_RULE_CAP_LIMITED` | Project auto-promote run-finalization service | session, team_id, run_id, rule_cap_limited_count, candidate_rule_count, rule_limit |
| WARN | `ATLAS_IMPORT_PREVIEW_REJECTED` | Atlas import routes/workflow | ip, session, team_id, actor_member_id, actor_role, draft_id, format_id, source_tool_key, has_file, filename_present, content_length, upload_bytes, max_upload_bytes, request_limit_bytes, stage, http_status, reason |
| WARN | `ATLAS_IMPORT_APPLY_REJECTED` | Atlas import routes/workflow | ip, session, team_id, actor_member_id, actor_role, draft_id, batch_id, project_id, project_present, http_status, reason, draft_status, required_capabilities, option_import_entities, option_import_findings, option_link_to_project, option_create_project_targets |
| WARN | `ATLAS_IMPORT_LIMIT_REJECTED` | Atlas import workflow guardrails | limit_key, configured_limit, actual_count, draft_id, format_id, team_id, stage |
| WARN | `ATLAS_IMPORT_WARNINGS_TRUNCATED` | Atlas import parser | format_id, skipped, warning_count, suppressed_warning_count, max_warnings, warning_codes |
| WARN | `ATLAS_IMPORT_APPLY_STALE_CLEANED` | Atlas import draft cleanup | previewed_count, applying_count, cutoff |
| WARN | `ATLAS_IMPORT_CONFIG_LIMIT_INVALID` | Atlas import config readers | key, default, configured_type, configured_value |
| WARN | `SCAN_TARGET_OBSERVATIONS_DROPPED` | Atlas entity materializer | session, team_id, run_id, command_root, deleted_count, reason |
| WARN | `ATLAS_ENTITY_ATTRIBUTES_DECODE_FAILED` | Atlas entity materializer | session, team_id, entity_id, entity_type, value_type, reason |
| WARN | `ATLAS_LOOKUP_AMBIGUOUS` | exact Atlas lookup resolver | session, entity_type, scope_kind, project_scoped, lookup_role, row_count, preferred_count, direct_team_preferred, match_state, candidates_truncated, duration_ms |
| WARN | `ATLAS_LOOKUP_PROFILE_UNAVAILABLE` | exact Atlas lookup profile aggregation | session, entity_type, entity_id, scope_kind, project_scoped, reason |
| WARN | `SESSION_ROUTE_FAILED` | session routes | ip, session, route, error |
| WARN | `DIAG_REDIS_SCAN_INCOMPLETE` | `/diag` Redis probes | stage, error |
| WARN | `INTEL_PROVIDERS_DISABLED` | Atlas intel refresh | session, entity_id, entity_type |
| WARN | `INTEL_PROVIDER_LOOKUP_SKIPPED` | Atlas intel refresh | session, entity_id, provider, provider_status, provider_message |
| WARN | `INTEL_HTTP_REDIRECT_BLOCKED` / `INTEL_HTTP_JSON_DECODE_FAILED` / `INTEL_HTTP_JSON_SHAPE_UNEXPECTED` | intel provider HTTP client | provider_host, method/path when available, http_status, redirect_host or shape |
| WARN | `VAULT_DECRYPT_FAILED` | secrets vault | source |
| WARN | `CLIENT_ERROR` | `client_log` | ip, session, context, client_message |
| ERROR | `ATLAS_QUICK_LOOKUP_OPEN_FAILED` | desktop rail, mobile menu, or keyboard shortcut through `/log` | ip, session, context, client_message, client_details with source and stage |
| WARN / ERROR | `HISTORY_COMPARE_CANDIDATES_FETCH_FAILED` / `HISTORY_COMPARE_MANUAL_CANDIDATES_FETCH_FAILED` | comparison launcher through `client_log` | ip, session, context, client_details with bounded error_name, stage, status, run_id, route |
| WARN / ERROR | `HISTORY_COMPARE_API_FETCH_FALLBACK` / `HISTORY_COMPARE_FETCH_FAILED` | comparison renderer through `client_log` | ip, session, context, client_details with bounded error_name, status, left_run_id, right_run_id, route, compare_request_error |
| WARN | `DIAG_DENIED` | `diag()` | ip, allowed_cidrs |
| WARN | `SESSION_TOKEN_REVOKE_DENIED` | `session_token_revoke` | ip, session, reason |
| WARN | `SESSION_MIGRATE_DENIED` | `session_migrate` | ip, session, reason, from_session_kind, to_session_kind |
| WARN | `SESSION_PREFERENCES_INVALID` | `session_preferences_get` | ip, session, session_kind |
| WARN | `UNTRUSTED_PROXY` | `get_client_ip` | ip, proxy_ip, forwarded_for, path |
| WARN | `RATE_LIMIT` | HTTP rate-limit handlers | ip, request_id, path, limit_policy, scope |
| WARN | `RATE_LIMIT_STORAGE_FALLBACK` | rate-limit storage setup | reason, fallback, redis_configured |
| WARN | `CMD_TIMEOUT` | `generate()` | ip, run_id, session, timeout, cmd |
| WARN | `CMD_TIMEOUT_TERMINATE_FAILED` | brokered run timeout cleanup | ip, run_id, session, cmd (+ traceback) |
| WARN | `CLIENT_RUN_OUTPUT_INVALID` | client-side run persistence | ip, session, cmd, payload_type |
| WARN | `CLIENT_RUN_OUTPUT_TRUNCATED` | client-side run persistence | ip, session, cmd, raw_line_count, stored_line_count, limit |
| WARN | `RUN_OUTPUT_ARTIFACT_TRUNCATED` | full-output artifact capture | run_id, rel_path, artifact_bytes, limit, reason |
| WARN | `RUN_OUTPUT_ARTIFACT_PARSE_FALLBACK` | full-output artifact loading | rel_path, row_index, reason, error |
| WARN | `HTTPX_SCREENSHOT_PROTECTED_PATH_LOOKUP_FAILED` | HTTPx screenshot finalization | run_id, session, team_id, candidate_count, invalid_count, retained_count, removed_count, cleanup_failed_count, protected_cleanup_skip_count, protected_lookup_failed, protected_lookup_error, candidate_truncated |
| WARN | `HTTPX_SCREENSHOT_STORAGE_LIMIT_REACHED` | HTTPx screenshot finalization | run_id, session, team_id, candidate_count, invalid_count, retained_count, removed_count, cleanup_failed_count, protected_cleanup_skip_count, protected_lookup_failed, protected_lookup_error, candidate_truncated, quota_rejected_count, available_file_slots, available_bytes, usage_unavailable |
| WARN | `HTTPX_SCREENSHOT_CLEANUP_INCOMPLETE` | HTTPx screenshot finalization | run_id, session, team_id, candidate_count, invalid_count, retained_count, removed_count, cleanup_failed_count, protected_cleanup_skip_count, protected_lookup_failed, protected_lookup_error, candidate_truncated |
| WARN | `HTTPX_SCREENSHOT_CLEANUP_SKIPPED_PROTECTED` | HTTPx screenshot finalization | run_id, session, team_id, candidate_count, invalid_count, retained_count, removed_count, cleanup_failed_count, protected_cleanup_skip_count, protected_lookup_failed, protected_lookup_error, candidate_truncated |
| WARN | `COMMAND_REGISTRY_LOCAL_OVERLAY_INVALID` | command registry loading | path, error |
| WARN | `THEME_OVERLAY_LOAD_FAILED` | theme loading | path, source, error_type |
| WARN | `BODY_STORE_LOAD_FALLBACK` | large body storage | rel_path, kind, error |
| WARN | `CONFIG_UNKNOWN_KEY_IGNORED` | config loading | key, source |
| WARN | `CONFIG_VALUE_DROPPED` | config loading | key, source, reason, cidr/suffix |
| WARN | `CONFIG_VALUE_DEFAULTED` | config loading | key, source, reason, fallback |
| WARN | `CONFIG_VALUE_CLAMPED` | config loading | key, source, reason, minimum/maximum |
| WARN | `POSTGRES_READ_RETRY` | Postgres backend read retry | sqlstate, operation, retry_delay_ms |
| WARN | `REDIS_UNAVAILABLE` | process tracking startup | redis_scheme, redis_host, redis_port, redis_db, redis_configured, fallback |
| WARN | `WORKSPACE_ROOT_MISMATCH` | runtime bootstrap | workspace_root_env, workspace_root_config |
| WARN | `AI_SECRET_LOOKUP_FAILED` | AI provider credentials | secret_name (+ traceback) |
| WARN | `AI_CONTEXT_SECRET_METADATA_LOAD_FAILED` | AI context redaction | session (+ traceback) |
| WARN | `AI_CONTEXT_FULL_OUTPUT_LOAD_FAILED` | AI context assembly | run_id, rel_path, error |
| WARN | `AI_PROVIDER_SCHEMA_RETRY` | AI provider JSON validation | variant, attempt, model, finish_reason, output_chars, error_type, provider_truncated |
| WARN | `AI_SUGGESTION_SECRET_LOOKUP_FAILED` | AI suggestion validation | session, env, error_type (+ traceback) |
| WARN | `AI_SUGGESTIONS_REJECTED` | AI suggestion validation | suggestion_count, accepted_count, rejected_count, rejection_reasons, trusted_target_count, known_port_count |
| WARN | `AI_DIAG_TEST_FAILED` | AI diagnostics test prompt | ip, provider, model, error_code, http_status |
| WARN | `AI_PROVIDER_PROBE_FAILED` | AI provider diagnostics | provider, model, base_url_configured, error_code, http_status, latency_ms |
| WARN | `AI_COORDINATION_RELEASE_SKIPPED` | AI Redis coordination release | reason |
| WARN | `AI_COORDINATION_RELEASE_FAILED` | AI Redis coordination release | (+ traceback) |
| WARN | `AI_COORDINATION_HEARTBEAT_FAILED` | AI Redis coordination heartbeat | (+ traceback) |
| WARN | `AI_WORKER_COORDINATION_UNAVAILABLE` | AI worker coordination | error |
| WARN | `AI_ASSIST_STALE_RECLAIMED` | AI worker queue recovery | count, stale_after_seconds |
| WARN | `AI_ASSIST_FAILED` | AI worker completion | assist_id, run_id, session, variant, model, prompt_version, prompt_version_source, context_hash, error_code, error_message, http_status |
| WARN | `AI_WORKER_DATABASE_INTERRUPTED` | AI worker database loop | error_type |
| WARN | `ACTIVE_RUN_METADATA_DECODE_FAILED` | process tracking metadata | key, error |
| WARN | `ACTIVE_RUN_METADATA_STARTUP_CLEANUP_DEGRADED` | active-run startup cleanup | reason, fallback, pid |
| WARN | `REDIS_SESSION_SET_READ_FAILED` | process tracking metadata | key (+ traceback) |
| WARN | `REDIS_SCAN_FAILED` | process tracking metadata | pattern (+ traceback) |
| WARN | `METRICS_DB_COLLECT_FAILED` | Prometheus runtime collector | database_backend (+ traceback) |
| WARN | `METRICS_REDIS_COLLECT_FAILED` | Prometheus runtime collector | (+ traceback) |
| WARN | `BROKER_REPLAY_TRIMMED` | broker replay storage | run_id, mode, max_events, max_bytes, remaining_events |
| WARN | `BROKER_PAYLOAD_DECODE_FAILED` | broker Redis stream decode | run_id, event_id, reason, error |
| WARN | `BROKER_REDIS_TRIM_UNAVAILABLE` | broker Redis replay trimming | key, reason |
| WARN | `PACKAGE_FULL_OUTPUT_PREVIEW_FALLBACK` | evidence package transcript rendering | run_id, rel_path, error |
| WARN | `PACKAGE_TRANSCRIPT_CAPPED` | evidence package transcript rendering | run_id, max_lines, hidden_lines, include_companion |
| WARN | `SHARE_REDACTION_RULE_INVALID` | share/export redaction config | label, pattern_hash, error |
| WARN | `SHARE_REDACTION_RULE_FAILED` | share/export redaction application | label, pattern_hash, error |
| WARN | `KILL_FAILED` | `kill_command` | ip, run_id, session, team_id, actor_member_id, team_role, pid, pgid, error |
| WARN | `WORKFLOW_DEFINITION_REJECTED` | operator workflow catalog | source, entry_index and error_type (when known), reason |
| WARN | `WORKFLOW_DEFINITION_VALIDATION_FAILED` | saved workflow create/update route | action, error_count, team_id, session |
| WARN | `WORKFLOW_EXECUTION_VALIDATION_FAILED` | durable workflow start route | reason, workflow_id and error_type (when known), session |
| WARN | `WORKFLOW_CAPTURE_FAILED` | workflow execution engine | execution_id, step_id, reason |
| WARN | `WORKFLOW_STEP_FAILED` | workflow execution engine | execution_id, step_id, exit_code, transition_reason |
| WARN | `WORKFLOW_STEP_DEFINITION_MISSING` | workflow execution engine | execution_id, step_id |
| WARN | `WORKFLOW_STEP_RENDER_FAILED` | workflow execution engine | execution_id, step_id, error_type |
| WARN | `WORKFLOW_INTERACTIVE_STEP_REJECTED` | workflow execution engine | execution_id, step_id |
| WARN | `WORKFLOW_STEP_LAUNCH_FAILED` | workflow execution engine | execution_id, step_id, error_type, stage |
| WARN | `WORKFLOW_CANCEL_SIGNAL_FAILED` | durable workflow cancel route | execution_id, run_id, error_type |
| WARN | `WORKFLOW_EXECUTION_LIMIT_REACHED` | durable workflow start route | limit, team_id, session, ip |
| WARN | `WORKFLOW_EXECUTION_TIMEOUT` | workflow execution engine | execution_id, step_id, max_runtime_seconds |
| WARN | `WORKFLOW_EXECUTION_PERMISSION_REVOKED` | workflow execution engine | execution_id, step_id, team_id, actor_member_id, reason |
| WARN | `WORKFLOW_RECOVERY_OUTPUT_LOAD_FAILED` | workflow startup recovery | execution_id, step_id, run_id, stage, reason |
| WARN | `WORKFLOW_RECOVERY_FAILED` | workflow startup recovery | execution_id, step_id, run_id (when known), reason |
| WARN | `HEALTH_DEGRADED` | `health()` | db, redis |
| ERROR | `RUN_SPAWN_ERROR` | `run_command` | ip, session, cmd (+ traceback) |
| ERROR | `RUN_STREAM_ERROR` | `generate()` | ip, run_id, session, cmd (+ traceback) |
| ERROR | `RUN_SAVED_ERROR` | `generate()` | run_id, session, cmd (+ traceback) |
| ERROR | `CONFIG_LOAD_FAILED` | config loading | phase, source, key, error |
| ERROR | `RUNTIME_BOOTSTRAP_FAILED` | runtime bootstrap | phase, runtime, init_metrics, init_logging, init_process, init_db, cleanup_active_runs (+ traceback) |
| ERROR | `ACTIVE_RUN_METADATA_STARTUP_CLEANUP_ERROR` | active-run startup cleanup | (+ traceback) |
| ERROR | `DB_INIT_FAILED` | database startup | backend, phase, schema_action (+ traceback) |
| ERROR | `CVE_RISK_BOOTSTRAP_MANIFEST_INVALID` | bundled public-risk bootstrap | reason when available (+ traceback for unreadable or invalid JSON) |
| ERROR | `CVE_RISK_BOOTSTRAP_FAILED` | bundled public-risk bootstrap | source (+ traceback) |
| ERROR | `CVE_RISK_REFRESH_FAILED` | public-risk feed refresh | source, attempts, error_type (+ traceback) |
| ERROR | `CVE_ADVISORY_LOCAL_LOAD_FAILED` | local NVD advisory loader | source, error_type |
| ERROR | `CVE_RISK_WORK_ITEM_FAILED` | changed-CVE work processor | source, attempt, max_attempts, error_type (+ traceback) |
| ERROR | `METRICS_ENVIRONMENT_SETUP_FAILED` | metrics startup | prometheus_multiproc_dir, source (+ traceback) |
| ERROR | `GUNICORN_WORKER_CLEANUP_FAILED` | Gunicorn worker hook | hook, pid (+ traceback) |
| ERROR | `PROJECT_AUTO_PROMOTE_RUN_ERROR` | run finalization | run_id, session, team_id, cmd (+ traceback); per-rule context is logged by `PROJECT_AUTO_PROMOTE_RULE_RUN_APPLY_ERROR` |
| ERROR | `WATCHER_FINALIZE_ERROR` | run finalization watcher hook | run_id, session (+ traceback) |
| ERROR | `WORKFLOW_STEP_LAUNCH_ERROR` | workflow execution engine | execution_id, step_id, error_type, stage (+ traceback) |
| ERROR | `WORKFLOW_FINALIZE_ERROR` | run finalization workflow hook | execution_id, step_id, run_id, stage, session (+ traceback) |
| ERROR | `WORKFLOW_RECOVERY_ERROR` | workflow startup recovery | execution_id, stage, pid, recovery_owner (+ traceback) |
| ERROR | `WATCHER_BASELINE_DELETE_HOOK_ERROR` | run cleanup watcher hook | (+ traceback) |
| ERROR | `PACKAGE_BUILD_FAILED` | evidence package builders | ip, session, project_id, package_id, job_id, stage, error (+ traceback) |
| ERROR | `PACKAGE_JOB_FAILED` | evidence package job worker | session, project_id, package_id, job_id, stage, error (+ traceback) |
| ERROR | `PACKAGE_BUILD_AUDIT_FAILED` / `REPORT_EXPORT_AUDIT_FAILED` | background export audit fallback | job_id, project_id, package_id when applicable, team_id, actor_member_id, job_status, reason, archive/count fields (+ traceback) |
| ERROR | `PACKAGE_PRESETS_LOAD_FAILED` | Project package preset route | ip, session, error |
| ERROR | `ATLAS_IMPORT_PREVIEW_FAILED` | Atlas import preview workflow | session, team_id, actor_member_id, actor_role, format_id, source_tool_key, stage, upload_bytes, has_filename, filename_present (+ traceback) |
| ERROR | `ATLAS_IMPORT_APPLY_FAILED` | Atlas import apply workflow | session, team_id, actor_member_id, actor_role, draft_id, batch_id, project_id, format_id, source_tool_key, stage, draft_status, required_capabilities, option_import_entities, option_import_findings, option_link_to_project, option_create_project_targets (+ traceback) |
| ERROR | `PROJECT_AUTO_PROMOTE_RULE_RUN_APPLY_ERROR` | Project auto-promote run-finalization service | session, team_id, run_id, project_id, rule_id, target_entity_kind, match_mode, limit (+ traceback) |
| ERROR | `NOTIFICATION_RUN_COMPLETE_ENQUEUE_ERROR` | run finalization notification hook | run_id, session (+ traceback) |
| ERROR | `NOTIFICATION_CHANNEL_SEND_EXCEPTION` | notification dispatcher | event_id, channel_id, kind, trigger (+ traceback) |
| ERROR | `NOTIFICATION_WORKER_BOOTSTRAP_FAILED` | notification worker | phase (+ traceback) |
| ERROR | `NOTIFICATION_WORKER_CRASHED` | notification worker | phase, limit, poll_seconds (+ traceback) |
| ERROR | `POSTGRES_POOL_OPEN_FAILED` | Postgres backend pool | pool_min, pool_max, jit_enabled (+ traceback) |
| ERROR | `SCHEDULE_FIRE_FAILED` | scheduler dispatch | schedule_id, owner_kind, session, fired_at, next_run_at, consecutive_failures, error, command_root (+ traceback) |
| ERROR | `SCHEDULE_FAILURE_NOTIFICATION_ERROR` | scheduler dispatch | schedule_id (+ traceback) |
| ERROR | `SCHEDULER_WORKER_CRASHED` | scheduler worker | phase, tick_seconds, limit, database_backend, lock_type (+ traceback) |
| ERROR | `SCHEDULER_WORKER_BOOTSTRAP_FAILED` | scheduler worker | phase, pid (+ traceback) |
| ERROR | `ZAP_WORKER_TICK_FAILED` | ZAP connector worker | (+ traceback) |
| ERROR | `ZAP_PLAN_SPOOL_CLEANUP_FAILED` | private ZAP plan cleanup | job_id, cleanup_stage, error_class (+ sanitized traceback) |
| ERROR | `OAST_SESSION_SPOOL_CLEANUP_FAILED` | private OAST terminal or orphan cleanup | correlation_id, cleanup_stage, error_class (+ sanitized traceback) |
| ERROR | `OAST_PROVIDER_DEREGISTRATION_FAILED` | private OAST registration rollback | correlation_id, cleanup_stage, error_class, error_code (+ sanitized traceback) |
| ERROR | `OAST_PROVIDER_SESSION_FAILED` | private OAST terminal session failure | correlation_id, from_status, to_status, error_class, error_code (+ sanitized traceback) |
| ERROR | `AI_WORKER_BOOTSTRAP_FAILED` | AI worker startup | phase (+ traceback) |
| ERROR | `AI_WORKER_CRASHED` | AI worker loop | (+ traceback) |
| ERROR | `MIGRATION_FAILED` | Schema migration runner | migration_version, migration_name, error (+ traceback) |
| ERROR | `HEALTH_DB_FAIL` | `health()` | (+ traceback) |
| ERROR | `HEALTH_REDIS_FAIL` | `health()` | (+ traceback) |
| ERROR | `UNHANDLED_EXCEPTION` | `errorhandler(500)` | ip, session, request_id, method, path, http_status (+ traceback) |
| CRITICAL | `REDIS_REQUIRED_FOR_MULTI_WORKER` | process tracking startup | workers, redis_configured |

## Logging Shape Notes

- request/response logging is owned by Flask hooks rather than Werkzeug's default request-line logging
- GELF keeps its required top-level `version: "1.1"` field separate from the app release in `_app_version`. Structured context names that would become OpenSearch metadata fields are emitted under `_event_*` instead, such as `_event_version` and `_event_source`, so Graylog can index them without colliding with `_version` or `_source`
- GELF never emits the legacy `_status` additional field. Numeric response codes use `_http_status`; string lifecycle fields keep their feature-specific names and one stable type
- run lifecycle logs intentionally carry `ip`, `session`, and `run_id` so start/end/kill/failure events can be correlated without reconstructing request flow from surrounding lines
- web bootstrap runs active-run metadata cleanup through a Redis-backed ownership guard; no-Redis deployments keep the previous per-worker cleanup fallback, while multi-worker startup without Redis fails closed with `REDIS_REQUIRED_FOR_MULTI_WORKER`
- diagnostics, history, permalink, and share routes each emit their own events so operator-visible surfaces remain observable outside the command-execution path
- proxy-aware identity resolution is shared across logging, rate limiting, and diagnostics gating, so the logged `ip` field tracks the same resolved client identity used elsewhere in the runtime

## Troubleshooting

1. Start with `log_format: text` for local `docker compose logs`, or use `gelf` when the destination indexes GELF additional fields.
2. Raise `log_level` to `DEBUG` only for the troubleshooting window; high-volume request, timing, cache, and branch events are intentionally below normal production levels.
3. Filter by the stable event name, then correlate with `request_id`, masked `session`, `run_id`, `team_id`, or the feature-specific identifier listed in the inventory.
4. Check `/diag` for current service and runtime state when the event points to database, Redis, workspace, provider, asset, or worker readiness.
5. Lower the level after collecting the needed context. Do not add raw commands, search text, credentials, file contents, finding text, or unbounded exception details to an ad hoc log statement.

Existing Graylog searches, dashboards, alerts, pipelines, and index templates
that use `_status` should move HTTP filters to `_http_status` and lifecycle
filters to the documented feature-specific field. The application change does
not require an index rotation because it stops writing the conflicting field.
Rotate only if you want to remove the old `_status` mapping from index
metadata. Replaying a previously rejected raw record requires renaming its
string `_status` value first; otherwise it will fail against the same numeric
mapping again.

Free-form `message` text and HTTP or error codes are supporting context, not stable selectors. Dashboards and alerts should key on the event name, level, and documented fields.

## Related Docs

- [../ARCHITECTURE.md](../ARCHITECTURE.md#logging) - formatter, bootstrap, and runtime logging boundaries
- [../CONFIGURATION.md](../CONFIGURATION.md) - `log_level`, `log_format`, and diagnostics settings
- [../FEATURES.md](../FEATURES.md#structured-logging) - user-visible observability benefits and limits
- [../DECISIONS.md](../DECISIONS.md#structured-logging) - logging design rationale and tradeoffs
