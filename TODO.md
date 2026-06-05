# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Richer package/export provenance implementation plan](#richer-packageexport-provenance-implementation-plan)
  - [Audit log surface implementation plan](#audit-log-surface-implementation-plan)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Feature Enhancements](#feature-enhancements)
- [Research](#research)
- [Ideas](#ideas)
  - [Audit log surface](#audit-log-surface)
  - [Workflows v2 — playbooks with parameters](#workflows-v2--playbooks-with-parameters)
  - [Run replay / scrubbable event stream](#run-replay--scrubbable-event-stream)
  - [Run comparison enhancements](#run-comparison-enhancements)
  - [Bulk history export and share](#bulk-history-export-and-share)
  - [Mobile share ergonomics](#mobile-share-ergonomics)
  - [PWA install and service-worker push](#pwa-install-and-service-worker-push)
  - [Engagement report builder](#engagement-report-builder)
- [Architecture](#architecture)
  - [Unified terminal built-in lifecycle](#unified-terminal-built-in-lifecycle)
  - [Plugin-style helper command registry](#plugin-style-helper-command-registry)
  - [Lightweight Jinja base template](#lightweight-jinja-base-template)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

### Richer package/export provenance implementation plan

Improve package and report handoff metadata so exported work explains where evidence came from, how it was selected, and what context should survive import/export loops. Land the provenance schema ahead of the report builder where practical, but keep reports able to consume provenance as optional input with clean fallbacks.

**Goal and boundaries**
- Make package manifests and reports show clear source context for targets, findings, artifacts, runs, imports, labels, notes, and package builds.
- Add explicit target references when selected findings rely on derived relationships that are not obvious in the finding text.
- Preserve source and curation hints so labels, notes, targets, findings, and packages survive a handoff/round-trip with less manual repair — without ever auto-writing project data on import.

**Foundations to reuse (already in the codebase)**
- Manifest builder: `evidence_manifest_from_summary` in `services/projects/packages.py` already emits `package_format_version`, `selected_entity_ids`, `preset`, `options`, and `links` — the provenance block slots in here.
- Manifest writer/format: `package_archive.py` writes `manifest.json` with a top-level `format`/`package_format_version`; bump the format and add a versioned parser/normalizer so old packages still render with a consistent "not recorded" provenance shape.
- Link origin sources: `project_links.source`, `project_links.source_detail`, and `PROJECT_LINK_SOURCES` in `core.database` are the source of truth for project-link provenance. Atlas import provenance is a separate path through `atlas_entity_import_links` / `atlas_finding_import_occurrences` and `v0027_atlas_import_sources`.
- Redaction/private-note handling: route provenance through the same package helpers used by the report builder, because source commands, target values, import source names, labels, and note status can disclose sensitive context even when the finding body is redacted.

**Decisions and risks**
- Do not invent a parallel origin enum. Map the persisted `PROJECT_LINK_SOURCES` values into the manifest provenance shape: `manual`, `active_project`, `auto_command`, `auto_input_file`, `auto_promote_rule`, `package_flow`, and `migration`.
- Keep project-link origin provenance separate from Atlas import provenance. Atlas import details come from the import-source tables, not from a synthetic `import` project-link source.
- Keep the first slice manifest-only for import hints. Emit enough context for a future preview/apply flow, but do not build package re-import or auto-rehydration behavior in v2.2.
- Ship stored relationship confidence in the first slice. The column is data-backed and at least some writers use non-default values; defer only new scoring logic or prominent confidence UI that would imply the values are fully calibrated.
- Expose one normalized provenance shape to the API, package preview, and report builder so consumers do not each branch on manifest version details.

**Phase P1 — Manifest provenance schema**
- Define a versioned provenance block in `packages.py` carrying per-item source context for targets, findings, artifacts, runs, imports, labels, notes, and the package build itself.
  - Source run ids and redaction-safe run commands where those dimensions were captured.
  - Import source ids and external tool format (from `atlas_import_sources`) when safe to expose.
  - Project-link origin mapped from `PROJECT_LINK_SOURCES`: `manual`, `active_project`, `auto_command`, `auto_input_file`, `auto_promote_rule` (with rule id/details), `package_flow`, and `migration`.
  - Labels and notes included-vs-excluded status without leaking excluded private note bodies.
  - Target relationship source, source detail/reason, and stored confidence.
  - Package build settings: redaction mode, preset/template id, and selected entity ids.
- Bump `package_format_version`, add an explicit normalizer branch for the prior format, and record the schema change in a manifest-format note in `ARCHITECTURE.md`.

**Phase P2 — Serializer provenance fields**
- Normalize or add provenance fields in the project serializers (`queries.py`, `links.py`, `metadata.py`, `findings.py`, `targets.py`) before changing any browser display, so the manifest and UI read from one source.
- Map existing `project_links.source`, `source_detail`, and `confidence` onto the provenance block's origin/source-detail/confidence fields. This is a serializer task, not a schema migration.
- Keep Atlas import provenance serializers separate: read source tool, file hash, and `source_detail_json` from the Atlas import-source/link tables instead of treating imports as project-link origins.

**Phase P3 — Target and finding references**
- Add richer target context to package/report finding rows: redaction-safe target value, target type, relationship source/reason, source run, and linked entity when known.
- When a finding references a host/domain/URL indirectly, surface the target relationship in the manifest and report instead of relying on the raw line alone.
- Keep references compact in UI rows and detailed in manifest/report output; feed the same structure into the report builder so both tell one story.

**Phase P4 — Round-trip / import hints**
- Add an import-hint block describing how a future import should recreate labels, notes, target relationships, source links, package metadata, and finding review state.
- Keep this phase to emitted hints and warnings only. Package re-import preview/apply stays a later implementation and must reuse the Atlas import preview/apply pattern before it writes project data.
- Emit warnings when package data is redacted, private notes are excluded, or source runs/artifacts are no longer available.

**Phase P5 — Browser surface**
- Update the package preview and manifest viewer (`project_packages.js`) to show a concise provenance summary above the raw JSON.
- Add compact "source"/"provenance" chips only where they explain package rows without crowding the project UI (reuse `project_shared_ui.js`); put fuller detail in the manifest/provenance summary.
- Feed the same provenance summary into the report-builder display.

**Phase P6 — Validation and docs**
- Pytest: manifest schema and provenance fields; target relationship serialization; redaction/private-note exclusion; redacted provenance does not leak original commands/targets; backward compatibility (older-format manifests still read and normalize); `PROJECT_LINK_SOURCES` mapping; Atlas import provenance stays separate from project-link origin.
- Vitest: package preview/manifest provenance rendering; older-manifest "not recorded" display; report-builder provenance display.
- Playwright: create a package from project data and verify the visible provenance summary plus the manifest JSON.
- Docs: API/OpenAPI (`blueprints/api_v1.py`) for manifest schema/version changes and any payload fields; `ARCHITECTURE.md` manifest-schema note; `CHANGELOG.md`; release drafts.

**Cut line**
- v2.2 target (full-featured): manifest provenance fields; project-link origin mapped from existing `source`/`source_detail` values; Atlas import provenance kept on its own path; target references with stored confidence in package/report output; package-preview provenance summary; format-version bump with backward-compatible normalization; import hints emitted but not applied; full tests.
- Later: package re-import preview/apply; cross-package lineage; richer confidence scoring; package comparison.

### Audit log surface implementation plan

Add an operator-visible audit trail for consequential actions so team/project work can be reviewed without reconstructing events from structured logs. Team-Mode (v2.1) raised the stakes here: with multiple users sharing scope, "who shared / toggled redaction / deleted / built a package or report" is now an operational and compliance need.

**Goal and boundaries**
- Store durable audit events for actions that change data, reveal/share data, or affect evidence handoff.
- Provide a plain, fast viewer: event list, filters, detail drawer, and CSV/JSON export.
- Keep details safe by construction: no secret values, no raw private-note bodies, no full command output, and no raw bearer/session tokens.

**Foundations to reuse (already in the codebase)**
- Retention precedent: `notifications.events.retention_days` already keeps "delivery audit rows" with a configurable prune (migration `v0009`); mirror its retention + startup-cleanup shape (also see `permalink_retention_days` startup pruning).
- Scope precedent: the `session_id` + `team_id` scoping and conditional indexes from `finding_triage_details` (`v0028`).
- Diag surface precedent: `/diag` and its JSON sub-routes (`/diag/classifier-inspector`, `/diag/classifier-drift`) in `blueprints/assets.py`, gated by `_require_diag_access`; `templates/diag.html` + `static/css/diag.css` for the viewer.
- Actor/context helpers: the `Capability`/role data in `services/teams/capabilities.py` and `get_log_session_id`/request-id helpers in `core/helpers.py`.
- Existing audit-like surfaces: notification delivery rows are already durable and owner-scoped; secret audit helpers currently emit log-only structured events.

**Decisions and risks**
- `/diag/audit` is the operator-wide first surface. It is IP-gated by `_require_diag_access` and may query across personal/team scopes; any later Options/team-owner surface must use separate capability-gated routes and owner-scoped queries.
- Because `/diag/audit` is operator-wide and IP-gated, every team's activity is visible to anyone with diag access. That fits single-operator self-hosting, but it is not appropriate for multi-tenant hosting until owner-scoped routes exist.
- Use fail-closed same-transaction recording for destructive/compliance-sensitive events such as deletes, shares/exports, secret changes, and team permission changes. Use best-effort post-commit recording for routine curation events such as label edits or finding review moves so an audit hiccup does not block low-risk product work.
- Details payloads are allowlist-based per event type. Record stable ids, counts, changed field names, redaction mode, safe labels, and result status; never store raw private notes, secret values, full command output, raw tokens, or full sensitive request bodies.
- Recorder allowlist validation should be defensive: unknown detail keys are dropped or moved to a safe `omitted_detail_keys` count instead of raising for routine best-effort events, while fail-closed event types may reject invalid details before commit.
- Keep the new operational audit stream distinct from existing notification delivery history. For notification actions, record configuration changes and high-level references in `audit_events`, while delivery attempt history stays in `notification_events`.
- Route existing log-only secret audit emitters through the new recorder once the table exists, preserving their safe naming behavior without copying secret values.
- Use correlation ids for multi-step actions. Async package/report jobs should share a job/correlation id across start, completion, failure, ticket issuance, and any tracked ticket redemption event.

**Phase A1 — Data model and recorder service**
- Add the next audit migration (placeholder name: `v0030_audit_events`) plus the parallel SQLite bootstrap.
  - Columns: `id`, owner `session_id`, `team_id`, actor (session/team-member id and display name when available), `event_type`, `target_type`, `target_id`, `project_id`, `request_id`, `correlation_id`, optional `job_id`, `created` timestamp, IP/user-agent summary, and a bounded JSON `details` payload.
  - Indexes: personal scope by `(session_id, created)` where `team_id = ''`, team scope by `(team_id, created)` where `team_id != ''`, plus `(event_type, created)`, `(project_id, created)`, `(target_type, target_id, created)`, and `(correlation_id)`.
- Add `app/services/audit/` with:
  - `models.py` — event-type and target-type enums, with each event type carrying its recording mode (`fail_closed` or `best_effort`) so call sites do not choose policy ad hoc.
  - `recorder.py` — a `record_event(...)` helper that accepts an active DB connection for same-transaction writes, trims/bounds the JSON payload, validates details against per-event allowlists, and strips unsafe values.
  - `queries.py` — paginated, filtered reads.
  - `retention.py` — cleanup keyed on `audit_retention_days`, run at startup and periodically from the app's normal background/worker path so long-running deployments continue pruning.
- Config: `audit_log_enabled` (default on) and `audit_retention_days` (sensible default, e.g. 90; `0` = unlimited).

**Phase A2 — Instrumentation at completed-action boundaries**
- For fail-closed synchronous mutations, record events in the same transaction after the mutation succeeds and before commit. For best-effort curation events, record after commit and log recorder failures without rolling back the user action. For async jobs, record start/completion/failure at job-state transitions.
- Cover, by category:
  - Destructive: history delete, snapshot delete, file delete, project unlink/delete, package delete, finding delete/suppression.
  - Share/export: snapshot create, redaction toggle/use, package/report build, export preview, download-ticket issuance, and ticket redemption where the shared ticket flow exposes enough context.
  - Secrets and integrations: secret create/replace/delete/rotation, notification channel changes, and future ticketing/webhook config changes.
  - Team and scope: team create/join/invite/revoke/archive/reactivate, role changes, and scope changes that lead to writes.
  - Curation: finding review changes, remediation/verification edits, label/note changes, project link/unlink, and target changes.
- For async package/report builds, record start and completion/failure events with the job id, correlation id, and safe artifact metadata (hook into `package_jobs.py` and the report export job).
- Add helper wrappers where repeated project-metadata mutations already share code (`services/projects/metadata.py`).

**Phase A3 — Routes and viewer**
- Add `/diag/audit` read route(s) with pagination, filters, and CSV/JSON export; gate with `_require_diag_access` for the operator-wide first version.
- Filters: event type, actor, project, target type, date range, and team/personal scope.
- Detail drawer showing the safe JSON details plus cross-links back to project/history/package/report surfaces when resolvable.
- Keep query helpers able to run owner-scoped reads so a later Options/team-owner view can reuse the same service without inheriting `/diag`'s cross-scope access.

**Phase A4 — Validation and docs**
- Pytest: table-driven event-type recording-mode coverage; fail-closed event creation in the same transaction as successful mutations; rollback does not leave orphan audit rows; best-effort curation events do not roll back product writes on recorder failure; owner-scoped and operator-wide reads; details allowlist/redaction; pagination and filtering; startup and periodic retention cleanup; async build start/complete/failure correlation; notification/secret audit integration boundaries.
- Vitest: viewer filters, row rendering, detail drawer, and empty/error states.
- Playwright: perform a project/finding/package action and verify it appears in the audit viewer.
- Docs: `CONFIGURATION.md` (retention/enable settings); `ARCHITECTURE.md` (audit-event ownership, transaction, access, and details-safety rules); `CHANGELOG.md`; release drafts.

**Cut line**
- v2.2 target (full-featured): table, recorder, and queries; fail-closed same-transaction audit writes for destructive/compliance-sensitive mutations; best-effort audit writes for routine curation; correlated package/report/share/export job events; audit records for delete/project-link/finding-review actions; a `/diag` operator-wide viewer with filters and CSV/JSON export; startup plus periodic retention; full tests.
- Later: team-member actor display names everywhere; webhook/ticketing audit events; richer cross-links; an Options-surface viewer for team owners.

**Sequencing across the three v2.2 plans**
- The report builder foundation has landed. Provenance should still expose one normalized shape that reports can consume when available.
- Wire audit instrumentation after the remaining provenance/package pieces where practical so it can cover report, package, share, and export actions consistently.
- Migration identifiers in these plans are placeholders. Assign final migration numbers at merge time so the provenance, report, and audit branches do not collide if they land in a different order.

---

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

No technical debt items are currently tracked.

---

## Feature Enhancements

These are possible future improvements, split by whether they look worth carrying forward.

- **Webhook receiver / `POST /api/v1/intel/<provider>` passthrough.**
  - Worth scoping once outbound notifications and external automation mature. The headless API is the right place to receive webhooks that auto-create or update projects.
- **Cross-session Atlas view.**
  - Useful for operators managing multiple sessions or shared infrastructure, especially now that team mode makes shared context more important.
- **Extend comparison beyond run-to-run finding and artifact diffs.**
  - Snapshot and package-artifact comparisons are likely useful once evidence packages become a regular handoff surface.
- **Richer target references in package exports.**
  - Useful when selected findings rely on derived relationships that are not directly visible in the finding text.
- **Richer provenance metadata and round-trip import hints.**
  - Helps labels, notes, targets, findings, and packages survive export/import workflows with less manual repair.
- **Revisit PTY transport after real usage.**
  - The current Redis-brokered SSE plus POST endpoints keep deployment simple, but WebSockets may be worth it if latency, throughput, or bidirectional control becomes a real limitation.
- **Split `pty.js` and `pty_service.py` if PTY work grows again.**
  - Worth doing when new PTY behavior lands; orchestration, modal wiring, xterm session handling, lifecycle, transport, and metadata storage are natural boundaries.
- **Introduce a small PTY host interface object and broader PTY browser coverage.**
  - Would make PTY tests less brittle and keep future tab-state or disabled-terminal changes from drifting.
- **Reduce idle PTY control-channel work if concurrency becomes real.**
  - Redis Pub/Sub, a longer block window, or avoiding unnecessary attach-time snapshot writes would be worthwhile if many PTYs are active at once.

## Research

No research items are currently tracked.

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Audit log surface
- Add a queryable audit table for consequential actions such as delete, share, redaction toggle, secret create/replace, project link, suppression, and evidence package build.
- Add an audit viewer on `/diag` or inside Options so operators can inspect what happened without reconstructing it from structured logs after the fact.
- Many engagement contracts require this kind of operator-visible trail, so this would make compliance and post-engagement review easier.

### Workflows v2 — playbooks with parameters
- Evolve workflows from saved command lists into reusable runbooks.
- Add typed parameters such as target, port set, and wordlist reference, then prompt for those values at execute time.
- Add conditional next-step behavior based on exit code.
- Let each step capture selected output into named variables that later steps can consume.

### Run replay / scrubbable event stream
- Turn completed runs into replayable structured event logs, building on the Structured Output Model.
- Support a scrub timeline, bookmarks, per-line comments, and command-by-command playback.
- Keep replay integrated with findings, Atlas entities, summaries, and run comparison rather than treating it as a separate asciinema-style recording.

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
- The history drawer can delete all, delete non-favorites, export selected history as text/JSONL, and use visible-page multi-select for bulk project add/remove plus selected-item delete. Bulk share/permalink bundles would close the remaining gap when packaging selected history items after an engagement.

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
- The Project Report tab now covers the base narrative-report flow. Future polish can make reports feel more portable and customer-ready:
  - Add report-created run links or permalinks where needed, carrying the report's redaction mode and showing the `permalink_retention_days` caveat in preview/export metadata.
  - Feed richer package/export provenance into the report once that plan lands, especially source run/import context and target relationships.
  - Tune artifact embedding/listing once provenance and report-created run links are available; screenshot galleries and richer binary handling can stay later work.
  - Run a browser Print/PDF fidelity pass across Chrome, Safari, and Firefox for page breaks, headers/footers, and fonts. If the browser print path cannot produce a consistent customer-grade PDF, revisit a server-side PDF renderer with its Docker/dependency cost documented.
  - Consider saved report versions, richer in-UI template customization, arbitrary custom sections, approvals, and shareable report permalinks after the one-current-draft workflow has real usage.

### Native ticketing integrations
- From the Findings tab, Project views, or evidence package flows, create or update issues in Jira, Linear, GitHub Issues, GitLab, etc., with bidirectional sync of status, notes, and links back into the finding review state.
- **Entry-level scope:**
  - Generic webhook + templated payload connector plus first-class adapters for the most common trackers.
  - Secret-backed auth stored in the existing encrypted secrets surface.
  - One-click "Create ticket" and "Link existing" actions on individual findings and bulk on visible-page selections.
  - Map finding review state to ticket status (and vice versa) where the tracker supports webhooks or polling.
- **Architecture:**
  - New `app/services/integrations/ticketing/` package (or a lighter `notifications` extension).
  - Adds project-level and global configuration surfaces under Options or a new Integrations tab.
  - Preserves the existing outbound notification model for fire-and-forget alerts while adding the stateful sync path.

### Operator-extensible signal and parser rules
- Allow operators to extend the built-in findings classifier, entity extractor, and structured metadata logic via a hot-reloadable `conf/signals.yaml` (or small sandboxed snippets) without code changes.
- Custom rules feed the same findings strip, Atlas materialization, search scopes, run comparison diffs, project triage, and export surfaces as core signals.
- **Entry-level scope:**
  - Declarative regex + capture group + mapping rules for common cases (e.g., custom internal scanner output).
  - Optional tiny expression or Lua/JS sandbox for complex parsing.
  - Live reload on file change (consistent with `commands.yaml`, `workflows.yaml`, etc.).
- **Architecture:**
  - Extend or parallel `app/core/output_signals.py` with a user-rules loader.
  - Surface validation and a `/diag` inspector mode for testing new rules against recent output samples.

---

## Architecture

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
