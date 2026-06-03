# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
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

### Richer per-finding remediation and verification fields

Findings are moving from raw scanner output toward report-ready triage records. Add structured fields that let an operator capture what should be fixed and how to prove it was fixed, without turning the feature into ticketing, SLA tracking, or AI-authored remediation.

**Measurable first scope**

- Add structured finding triage fields:
  - Remediation text.
  - Verification steps.
  - Verification status: `not_started`, `ready_to_verify`, `verified`, `needs_retest`, or `not_applicable`.
  - Optional verification notes.
- Store these fields separately from canonical finding identity/source data, so dedupe, source occurrence counts, and review state keep their current meaning.
- Surface the fields in Atlas and Project finding read/edit flows, with compact list badges instead of full text on every row.
- Include the fields in evidence package finding JSON and Markdown exports.
- Keep generic labels and notes unchanged; these fields are for repeatable remediation and verification handoff.
- Use `verification_status` everywhere; don't add another bare `status` field because findings already use status/review state for triage.

**Out of scope for this pass**

- Creating or syncing external tickets.
- SLA dates, assignment queues, or multi-step workflow state.
- AI-generated remediation text. Imported tools may preserve provided remediation text if the parser has a trustworthy field, but the app shouldn't invent guidance in this pass.
- Project-specific overrides unless real usage shows the same canonical finding needs different remediation per Project.

**Phase 1: Data model and service contract**

- Add a `finding_triage_details`-style table through the repo's asymmetric database paths:
  - SQLite: add `CREATE TABLE IF NOT EXISTS finding_triage_details (...)` to the bootstrap path in `app/core/database.py`, near the existing `entity_notes` table, plus indexes near the existing metadata indexes.
  - Postgres: add a new `v0028_*` migration module and register it in `app/core/migrations/__init__.py`.
- Match the existing metadata owner model instead of inventing a generic owner key:
  - Store both `session_id` and `team_id` on every row.
  - Read with the same personal/team fallback shape used by `_metadata_owner_where`.
  - Add personal and team partial-unique indexes equivalent to the `entity_notes` uniqueness pattern for `(entity_type, entity_id)`, adapted to `finding_id`.
- Fields should include bounded text columns for remediation, verification steps, verification notes, verification status, `created`, and `updated`.
- Add `FINDING_VERIFICATION_STATES` and max text limits in `services.projects.contracts`, next to `FINDING_REVIEW_STATES`, and validate text with the existing `_trim_text` pattern.
- Add service helpers for loading and upserting triage details for one finding and batches of findings. Build a shared `_finding_triage_by_id(...)` helper, mirroring `_entity_notes_by_id(...)`, so Atlas, Projects, and packages use one loader.
- Add a per-owner stored-row cap as cheap abuse protection. Unlike notes, this is one row per finding, so the cap should protect total owner growth rather than per-finding count.
- Ensure deleting a finding cleans up its structured triage row in `delete_atlas_findings(...)`. There is no portable FK cascade, and the Postgres path doesn't have the SQLite-only `findings_ad` trigger, so rely on the service-layer delete.
- Completion signal: migration parity tests pass, service tests prove save/load/update/delete cleanup, delete-path tests prove `delete_atlas_findings(...)` removes triage rows, and finding aggregate recalculation does not mutate the separate triage table.

**Phase 2: Routes, capabilities, and serialization**

- Add a net-new read/write surface, such as `GET` and `PUT /findings/<finding_id>/triage`, because there isn't currently a single-finding detail GET route to extend.
- Gate writes behind the same finding-triage capability used for review-state changes.
- Gate reads and writes with `finding_exists_in_scope(...)` so both run-backed and import-only findings are writable when they are visible in the active scope.
- Serializers now need to join two sources: the canonical finding row for identity/source/review state and the triage row for remediation/verification fields.
- Add compact enrichment to Atlas and Project finding lists: `verification_status`, presence booleans, and short snippets if needed. Do not add full remediation or verification text to every list row.
- Decide and implement list filtering for `verification_status` in Phase 2 if the UI will show verification badges; adding the join/WHERE now is cheaper than retrofitting it after users rely on the badges.
- Completion signal: route tests cover read, update, invalid verification status, oversized text rejection, read-only/team viewer behavior, active-scope enforcement, imported findings, and verification-status filtering if the filter ships.

**Phase 3: UI workflow**

- Extend the finding edit/detail experience with clear Remediation and Verification sections.
- Show compact verification status indicators in Atlas and Project finding lists when present.
- Keep the editor consistent with existing metadata/edit modal behavior, including focus management, read-only states, save errors, and mobile layout.
- Completion signal: users can edit, save, refresh, and see the fields again from both Atlas and Project finding surfaces; unit or browser coverage pins the happy path and validation/error states.

**Phase 4: Packages, imports, and AI context**

- Include remediation and verification fields in evidence package finding JSON and Markdown output.
- Route package-export remediation and verification values through the same package redaction path used for other package manifest values, using `_redact_package_value(...)` / `redaction_rules` before rendering finding JSON or Markdown.
- Decide the private-notes posture explicitly:
  - Remediation and verification steps are report-ready finding fields and should be included with selected findings after package redaction.
  - Verification notes are internal operator notes and should be gated behind `include_private_notes`, matching `entity_notes`.
- If imported tools provide explicit remediation fields, map them into remediation text only when the source field is clearly intended as remediation.
- Add a compact AI context summary for findings with remediation or verification state so summaries and next-command suggestions can mention known fix/verify work without reading long free-form notes.
- Pass every remediation and verification value included in AI context through the same redaction path used for other finding fields; these fields are free-form operator text and may contain hosts, credentials, or customer-sensitive details.
- Completion signal: package tests prove report-ready fields export, private verification notes follow the `include_private_notes` gate, package redaction applies before JSON/Markdown rendering, import parser tests cover at least one trustworthy remediation source if mapping is added, and AI context tests prove compact remediation/verification context is present.

**Phase 5: Documentation and regression coverage**

- Update the user-facing docs to describe what the fields are for and where they appear.
- Update architecture docs for the internal route contract, response fields, and evidence package export shape. Keep the triage route internal-only like `PUT /findings/<finding_id>/review` unless the implementation deliberately adds a headless API v1 surface; only update `services/api_v1/openapi.py` if that v1 route ships.
- Update the changelog and the test-count docs in `ARCHITECTURE.md`, `CONTRIBUTING.md`, and `tests/README.md` with the finished implementation.
- Follow `DOC_STANDARDS.md` when writing the final docs, especially the bullet-depth and current-state wording rules.
- Completion signal: doc-drift tests, targeted backend tests, relevant JS tests, and any touched Playwright flows pass.

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
- Turn a project workspace into a styled markdown/PDF engagement report — methodology, scope, targets, findings table, remediation notes, screenshots. Evidence packages today are raw bundles; this is the narrative deliverable a customer reads.
- **Entry-level scope:**
  - One-click "Generate report" from a project, with an editable cover page (engagement name, dates, operator, contact).
  - Sections auto-populated from project data: targets, findings grouped by severity, included runs (with permalinks), artifacts.
  - Output formats: markdown source plus rendered HTML and PDF, reusing the existing export pipeline.
  - Operator-editable section templates in a new `app/conf/report_templates.yaml`.
- **Architecture:**
  - New `app/services/reports/` service composing project-workspace data with existing finding/run/artifact serializers; templating via Jinja autoescape.
  - Adds `GET/POST /projects/<id>/report` to `app/blueprints/projects.py`.
  - Browser surface: a "Report" tab inside the existing Projects modal; renderer reuses `export_html.js` and `export_pdf.js`.
  - Honors share-redaction defaults; the draft is always previewed before download so this stays additive to evidence packages, not a replacement.

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
