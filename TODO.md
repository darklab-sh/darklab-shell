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

### Atlas Import from External Triage Tools

Build an import path that lets operators bring entities and findings from external triage tools into Atlas without pretending those results came from an in-app run.

#### Scope
- Import structured external results into Atlas entities, Atlas findings, and optional project links.
- Support personal and team scopes with the same visibility and capability rules used by Projects and Atlas today.
- Preserve import provenance so users can see which tool/file created or updated each imported item.
- Start with explicit, documented formats instead of a broad "upload anything" parser.
- Keep imported data separate from run history: imports can create Atlas records, but they do not create fake runs, transcripts, or command artifacts.

#### Non-goals
- Do not execute external tools, fetch remote URLs, or poll third-party services during import.
- Do not accept archive uploads in the first implementation.
- Do not auto-trust imported severity, review state, labels, or notes without clear user confirmation.
- Do not try to round-trip every field from every vendor format. Keep the first pass small and predictable.

#### Requirements
- Provide a preview-before-apply flow showing total rows, valid rows, skipped rows, duplicate matches, new entities, updated entities, new findings, and warnings.
- Apply imports idempotently by reusing existing Atlas canonicalization, finding signature, and project-link helpers wherever possible.
- Store enough provenance to answer "where did this come from?": source tool, import name, uploaded filename, original row/line number when available, external id when available, and import timestamp.
- Gate apply actions behind the same mutation capabilities used for project/Atlas changes. Read-only users may view existing imported data but cannot apply a new import.
- Bound import work with configurable limits for upload size, row count, finding count, warning count, and preview result size.
- Treat all imported text as untrusted: sanitize display fields, reject path-like upload names as storage paths, and keep redaction rules active for package/export flows.
- Make failures observable with structured logs for preview rejection, apply rejection, parser errors, and successful apply summaries.

#### Phase 0 - Format and Ownership Decisions
- Pick the first supported formats:
  - Generic CSV for entities and findings with a documented column schema.
  - Generic JSONL for entities and findings with a documented object schema.
  - One external-tool adapter, preferably Nuclei JSONL, because it maps naturally to finding-like data.
- Decide whether `httpx`, `naabu`, and `subfinder` adapters are part of the initial release or follow-up work.
- Define the canonical import fields for entities and findings before writing parsers:
  - Entity fields: kind, value, confidence, source detail, optional tags, optional observed-at timestamp.
  - Finding fields: title, severity, description/evidence, affected entity/value, external id, references, source detail, optional observed-at timestamp.
- Decide whether previews are persisted as short-lived import drafts or computed on demand from the uploaded file.
- Decide whether successful imports need a first-class import history table or can start with provenance metadata on created/updated records.

#### Phase 1 - Data Model and Provenance Contract
- Add the persistence needed for import provenance:
  - Import batch metadata with id, scope, actor, source tool, import name, filename, created timestamp, applied timestamp, status, counts, and warning summary.
  - Per-row provenance only if it is needed to explain skipped rows or link imported Atlas records back to a specific source line.
- Add migrations for SQLite and Postgres together.
- Reuse existing Atlas entity and finding tables rather than introducing parallel imported-entity tables.
- Reuse existing project link insertion helpers so project links stay idempotent and quota-aware.
- Define how imported findings map to review state:
  - Imported findings should default to the same unreviewed/new state as detected findings unless the user explicitly chooses another supported mapping.
  - False-positive or dismissed states from external tools should import as metadata/warnings first, not as trusted local triage state.
- Define how duplicate detection works:
  - Entities dedupe through existing canonical values.
  - Findings dedupe through the existing finding signature path where possible.
  - If an external id is present, store it as provenance but do not make it the only dedupe key.

#### Phase 2 - Parser and Normalization Service
- Build a small parser service that accepts a file stream plus an explicit format id.
- Validate format-specific schemas and return row-level errors without applying any changes.
- Normalize domains, IPs, URLs, CVEs, hashes, and finding severities with the same helpers used by Atlas capture.
- Keep adapter logic narrow:
  - Generic CSV and JSONL adapters map fields directly from documented schema names.
  - Tool adapters translate known external fields into the canonical import fields.
- Add guardrails for large or noisy files:
  - Stop parsing after the configured row limit.
  - Cap stored warning samples.
  - Return a clear preview error when limits are exceeded.
- Ensure parser errors are safe to show in the UI and detailed enough in logs for operators to debug malformed files.

#### Phase 3 - Preview and Apply API
- Add preview and apply endpoints under the existing project/Atlas API shape.
- Require callers to pass the target scope, optional project id, format id, source tool, and import name.
- Preview response should include:
  - Counts for valid, skipped, duplicate, new, and update candidates.
  - A bounded sample of parsed entities/findings.
  - A bounded sample of row warnings/errors.
  - The apply options available for the current user and scope.
- Apply request should include the preview token or draft id plus explicit options:
  - Import entities.
  - Import findings.
  - Link imported records to a project.
  - Create or update project targets from imported domains/IPs/URLs.
- Re-check permissions, limits, and source file integrity at apply time; do not trust an old preview blindly.
- Return actual applied counts, not just preview counts, because project quotas and duplicates can change between preview and apply.

#### Phase 4 - UI Flow
- Add an `Import` action to Atlas and project entity/finding surfaces where it fits existing controls.
- Use a modal flow with clear steps:
  - Choose format/source.
  - Select file and import name.
  - Review preview counts, samples, warnings, and apply options.
  - Apply and show the resulting counts.
- Keep the UI consistent with existing modal and dropdown primitives in the front-end design system.
- Make warnings visible without overwhelming the user:
  - Show a concise summary near the apply action.
  - Provide a scrollable row-warning sample for debugging.
- After apply, refresh the affected Atlas/project lists without requiring a full page reload.
- Show imported provenance in entity/finding detail views with plain labels such as `Imported from Nuclei JSONL`.
- If project target creation is enabled, make it opt-in and explain the count of targets that will be created or updated before applying.

#### Phase 5 - Team Mode and Safety Edges
- Confirm team-scope imports respect team membership and mutation capabilities.
- Ensure imports cannot leak personal-scope data into team projects or team-scope data into personal projects.
- Confirm deleted, archived, or inaccessible projects cannot be used as import targets.
- Add concurrency protections so repeated apply clicks or two users applying the same draft cannot create duplicate entities/findings/links.
- Add cleanup for abandoned upload drafts if preview files are persisted.
- Add operator configuration for import limits with sensible defaults.

#### Phase 6 - Tests, Logging, and Documentation
- Add parser tests for valid CSV, valid JSONL, malformed rows, unsupported entity kinds, invalid severities, duplicate rows, and limit handling.
- Add backend route tests for preview, apply, permission rejection, stale preview rejection, project quota behavior, and idempotent re-apply.
- Add Postgres migration coverage alongside SQLite coverage.
- Add JavaScript unit tests for the modal flow, warning display, apply options, and post-apply refresh.
- Add Playwright coverage for a browser import path using a small fixture file.
- Add logging tests or assertions for preview/apply success and rejection events where the existing test style supports it.
- Update user-facing docs when implemented, including supported formats, import limits, team permissions, and how imported provenance appears in Atlas.
- Update release notes and test counts when tests land.

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
- **Richer per-finding remediation or verification fields.**
  - Worth keeping if findings keep moving toward report-ready triage instead of raw output capture.
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
