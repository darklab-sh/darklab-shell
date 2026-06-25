# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Project-scoped target intelligence overview](#project-scoped-target-intelligence-overview)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Feature Enhancements](#feature-enhancements)
- [Research](#research)
- [Ideas](#ideas)
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

### Project-scoped target intelligence overview

A read-first engagement console for a project: roll up hosts, ports, services, cert
expirations, top findings by severity, and provider-enriched context per target so an
operator can understand the current attack surface before drilling into individual runs,
Atlas rows, or findings. This is the pull surface that complements the attack-surface delta
digest notifications (which only say *that* the surface changed). It is primarily an
aggregation + read layer over data that already exists — reuse, not new subsystems.

Data sources to join (all already present):
- Linked Atlas target entities via `_project_atlas_entity_select_sql(target_only=True)` and
  `list_project_entities` in `app/services/projects/queries.py`.
- Intel provider snapshots from `entity_intel_snapshots`, summarized through
  `summarize_intel_snapshots` in `app/services/atlas/lookup.py` (cert expiry, open ports,
  services, provider highlights).
- Findings rollup via `_project_finding_summary_rows` / `list_project_findings` in
  `app/services/projects/findings.py`.
- Monitoring/delta context via `get_project_monitoring_summary` in
  `app/services/projects/monitoring.py` (recent attack-surface changes per target).
- Target relationships and review state already exposed by `get_project_summary`.

#### Open Decisions

- **Target identity for v1.**
  - Recommended decision: build overview rows from Project targets plus linked Atlas target
    entities, merged by the existing Atlas `entity_id`. Do not add a parallel `target_key`
    dialect; the Project target path already canonicalizes with `canonical_entity(...)`,
    deduplicates with `entity_signature(...)`, and materializes targets through
    `upsert_entity(...)`. Keep a human-readable `type:value` value only as a display label or
    fallback for degraded data.
  - Type-vocabulary mismatch to resolve in Phase 1: `PROJECT_TARGET_TYPES` is
    `{domain, url, host, ip}` while Atlas `ENTITY_TYPES` is `{ip, domain, hash, cve, url}`, and
    the project Atlas-target filter (`_project_atlas_entity_select_sql(target_only=True)`) is
    further restricted to `domain/ip/url`. There is no `cidr` target type today. Pin and test
    the existing `host` mapping from `_canonical_target_payload`: IP-like host values become
    Atlas `ip` entities, and other host values become Atlas `domain` entities.
  - Phase 1 should also define the `target_id` filter contract explicitly: overview
    deep-links should pass the Atlas `entity_id`, which is also the Project target identifier
    exposed by current target rows. Legacy finding `target_id` fields may still match through
    existing `COALESCE(f.entity_id, f.target_id)` filters, but the overview should not invent
    another identifier.
- **Severity and review-state semantics.**
  - Recommended decision: show the highest-severity finding that is not suppressed and not
    marked `false_positive` as the default target severity, while carrying counts broken down
    by the real `FINDING_REVIEW_STATES` (`new`, `reviewed`, `important`, `needs_followup`,
    `false_positive`) plus the separate `suppressed` flag, so reviewers can understand why a
    target looks quiet. (There is no `accepted-risk` or `resolved` review state.)
  - Use the same severity vocabulary and ordering as `findingSeverityRank` in
    `project_workspace_constants.js` so the backend aggregator and browser sort/display logic
    agree on what "highest severity" means.
  - Open question for Phase 1: finding review state and `FINDING_VERIFICATION_STATES`
    (`not_started`…`verified`…`not_applicable`) are distinct axes in `contracts.py`. Decide
    whether the overview's "quieting" logic and counts key off review state, verification
    state, or both.
- **Certificate expiry thresholds.**
  - Recommended decision: use `expired`, `<=14 days`, `<=30 days`, `healthy`, and a distinct
    `unknown/no-data` bucket for the first version. Keep the raw expiry timestamp and derived
    `days_until_expiry` in the payload so the UI can sort and label without recalculating, and
    never render missing certificate intel as healthy.
- **Recent-change window.**
  - Recommended decision: use the same bounded Project Monitoring window semantics as digest
    notifications when a digest window exists, and fall back to the latest watcher-fire
    context when no successful digest window has been established yet. If neither digest nor
    watcher context exists, omit or disable the recent-change rollup instead of showing
    `0 changes`.
- **Deep-link filter contract.**
  - Recommended decision: define backend-provided filter hints for each target row using the
    existing query params, not a new filter language. For v1, populate Findings links with
    `target_id` and optional `review_state`/`severity`, and Entities links with `target_id` or
    `run_id` where applicable. Those hints should carry the same Atlas `entity_id` used as the
    overview merge identity and should validate through `_project_entity_filter_clause` and
    the Findings filter SQL.

#### Phase 1 — Contract and source mapping — Complete

- Define the stable payload shape and version before writing UI:
  `{ project, generated_at, payload_version, targets: [...], rollups: {...},
  recent_changes: [...] }`.
- Define the canonical row identity (`entity_id`), display label, target type, source flags,
  and merge rules for Project targets, Atlas target entities, findings, intel snapshots, and
  monitoring rows.
- Define `host` target canonicalization as a required mapping: IP-like `host` values resolve
  to Atlas `ip` entities, all other valid `host` values resolve to Atlas `domain` entities,
  and no `cidr` target row is introduced.
- Define the `target_id` deep-link/filter meaning as Atlas `entity_id`; document that current
  Project target row IDs already use that value, and that legacy findings are only supported
  through existing `COALESCE(f.entity_id, f.target_id)` filters.
- Define display fallback behavior for legacy or degraded data without an `entity_id`, keeping
  fallback `type:value` labels display-only and out of merge/filter identity.
- Define the finding rollup contract: top severity is the highest non-suppressed,
  non-`false_positive` finding; counts include every `FINDING_REVIEW_STATES` value plus the
  separate `suppressed` count.
- Decide whether verification-state counts are included in the first payload. If included,
  keep them under a distinct `finding_counts_by_verification_state` field instead of mixing
  them with review-state counts.
- Define the backend severity order from the same vocabulary as `findingSeverityRank`
  (`critical`, `high`, `medium`, `low`, `info`) so backend and browser ranking cannot drift.
- Define certificate status as `expired`, `expiring_14d`, `expiring_30d`, `healthy`, or
  `unknown`, with `unknown` used for missing/no-data certificate intel.
- Define target row limits, per-target highlight limits, stale/missing provider behavior, and
  deterministic sort order for large projects.
- Define empty and degraded states for projects with no targets, targets with no intel,
  findings without provider data, stale provider snapshots, missing certificate data, and
  monitoring data with deleted run references.
- Define recent-change states separately for `windowed`, `watcher-context-only`, and
  `not-monitored` projects so an unmonitored project never looks like a monitored project with
  zero changes.
- Define target deep-link filter hints as existing endpoint query params: Findings hints may
  include `target_id`, `review_state`, and `severity`; Entities hints may include `target_id`
  and `run_id`. Do not create a new filter syntax.
- Add focused contract tests for Atlas entity identity, host-to-domain/IP mapping,
  duplicate-source merging, payload bounds, empty states, no-window/no-watcher monitoring
  states, certificate `unknown` vs `healthy`, severity ordering, deep-link filter params, and
  cross-scope exclusion.

#### Phase 2 — Backend aggregator implementation — Complete

- Add `get_project_intel_overview(session_id, project_id, *, team_id="")` to
  `app/services/projects/queries.py` (or a new `app/services/projects/overview.py` if the
  join logic grows past ~150 lines).
- Return the Phase 1 payload shape. Each target row carries host/value, canonical
  `entity_id`, display label, target type, target review state, source flags, open ports +
  services, cert expiry with a `days_until_expiry` derived field and an explicit
  `unknown/no-data` state, top finding severity ranked with the shared severity order, finding
  counts by review state and suppression state, `summarize_intel_snapshots` highlights,
  recent-change markers, and deep-link filter hints populated with existing filter params.
- Build overview rows by Atlas `entity_id`: start with linked Project target entities,
  include explicitly linked Atlas-only target entities in the same owner scope, and join intel
  snapshots, findings, and monitoring context back to that same ID.
- Reuse `canonical_entity(...)`, `entity_signature(...)`, and target materialization behavior
  instead of rebuilding URL/domain/IP normalization inside the overview aggregator.
- Keep certificate `unknown` separate from healthy in rollups, row badges, and sorting.
- Return recent-change state metadata so the UI can distinguish `windowed`,
  `watcher-context-only`, and `not-monitored` without guessing from empty arrays.
- Populate deep-link hints server-side with Atlas `entity_id` filter params that already work
  with `_project_entity_filter_clause` and the Findings filter SQL.
- Reuse existing owner/scope clauses (`shared_owner_where`, `_project_entity_owner_clause`)
  so team-mode and session scoping stay identical to the rest of the workspace.
- Bound the result the same way `get_project_summary` does (target `LIMIT`, capped highlight
  counts) so large engagements don't produce unbounded payloads.
- Unit-test the aggregator against a seeded project with mixed targets, expiring/expired
  certs, duplicate target sources, suppressed entities, stale/missing intel snapshots, and
  findings across severities, review states, suppression states, and verification states.

#### Phase 3 — HTTP endpoint — Complete

- Add `GET /projects/<project_id>/overview` to `app/blueprints/projects.py`, following the
  exact `_project_owner()` + `_project_json_or_404` pattern used by `projects_summary`.
- Return 404 for missing/out-of-scope projects; never leak cross-session data.
- Add blueprint-level tests covering owner scoping, team scope, empty project, and the
  populated shape.
- Add route tests proving `target_id` deep-link hints use linked Atlas entity IDs, reject
  out-of-scope entities, and round-trip through the existing Entities/Findings filter params.
- Add route coverage for projects with no monitoring window and no watcher context so the API
  exposes `not-monitored` instead of a false zero-change state.

#### Phase 4 — Workspace tab (desktop) — Complete

- Register an `overview` tab in both tab-list definitions in
  `app/static/js/features/projects/project_navigation.js` (place it right after `details`).
- Add a new feature module `app/static/js/features/projects/project_overview.js` exporting
  `renderProjectOverview(content, projectId, summary)`; wire it into
  `app/static/js/features/projects/project_workspace_renderer.js` alongside the other
  `activeTab === ...` branches.
- Render with shared workspace primitives (`project_shared_ui.js`) — summary cards for the
  rollups, then a per-target table/list with severity, ports/services, cert-expiry badge,
  and a provider-highlight chip. No one-off CSS/markup; extend shared helpers if a primitive
  is missing.
- Fetch lazily on first activation (mirror the `loadProjectFindings` pattern) and cache on
  the workspace state object; refresh on project switch.
- Render explicit empty/degraded states for no targets, no intel yet, missing cert data, stale
  provider data, and no findings.
- Render healthy certificate status separately from unknown/no-data, and avoid green/clean
  styling for missing provider intel.
- Render recent-change rollups only when the payload reports `windowed` or
  `watcher-context-only`; show a neutral not-monitored state when that is the contract value.
- Use the backend-provided deep-link filter hints for Entities and Findings tab actions.
  Treat those hints as existing endpoint query params populated by the backend, not browser-side
  target matching logic.

#### Phase 5 — Mobile + cross-surface polish — Complete

- Cover the overview in the mobile shell (`project_mobile_detail.js` / mobile tab list) with
  one-handed-friendly stacked cards; reuse the same fetch/state path as desktop.
- Make each target row deep-link into the existing Entities/Findings tabs filtered to that
  target so the overview is a launchpad, not a dead end.
- Preserve the same backend-provided filter hints and certificate/recent-change states in the
  mobile layout; do not fork mobile-specific target matching or status rules.
- Surface the cert-expiry and recent-change rollups as the natural follow-through from a
  delta digest notification (link target where a digest deep-link already lands).

#### Phase 6 — Tests, docs, and release polish — Complete

- Add focused Playwright coverage for one populated desktop path, one mobile smoke path, and
  one target→Findings deep-link. Keep exhaustive empty/degraded state coverage in backend and
  Vitest tests unless the browser behavior itself becomes the risk.
- Add backend/Vitest coverage for the decision-heavy cases: Atlas `entity_id` identity,
  host-to-domain/IP mapping, severity rank parity, certificate unknown vs healthy, no-monitoring
  recent-change state, and existing-query-param deep-link hints.
- Update FEATURES/ARCHITECTURE/README for the new tab and endpoint, add a CHANGELOG entry,
  and update the frontend inventory allowlist for the new JS module.
- Update the documented test counts in all the tracked locations when new tests land.

#### Success Criteria

- The Overview endpoint and UI never leak target, finding, intel, run, or notification context
  across personal/team scopes.
- Target rows merge duplicate source records predictably through the existing Atlas `entity_id`.
- Large projects return bounded payloads with stable ordering and capped per-target highlights.
- Overview rows show useful empty/degraded states instead of implying missing intel is clean.
- Certificate status keeps healthy and unknown/no-data targets visually and semantically
  distinct.
- Desktop and mobile Overview surfaces render the same data contract with app-consistent
  project workspace controls.
- Target rows can launch into Entities and Findings with filters that preserve the selected
  target through the same Atlas entity identifier used by the overview row.
- Cert-expiry, top-severity, service/port, provider, and recent-change rollups match the
  underlying Atlas, finding, intel snapshot, and monitoring data.
- Official docs describe the Overview tab and endpoint as current behavior, and test counts
  stay in sync after coverage lands.

## Known Issues

- **Replace crt.sh as the primary certificate intel source.**
  - crt.sh is useful when it responds, but the public JSON endpoint is too prone to timeouts
    and 5xx responses to be the only source behind Project Overview certificate status.
  - Find a more reliable provider or app-native collection path for certificate expiry,
    issuer, subject/SAN, and observed-at data. Candidate directions include reusing
    `tlsx`/TLS scan output already collected by operators, another passive certificate
    transparency provider with better availability, or a hybrid where crt.sh is retained as
    a best-effort enrichment source instead of the primary status source.
  - Success criteria: Project Overview certificate badges should not depend on crt.sh
    availability, missing provider data must still render as `unknown` rather than healthy,
    and provider failures should remain visible as degraded intel instead of silently looking
    like no certificate data exists.

---

## Technical Debt

- **Unify terminal `intel` lookups with Atlas intel snapshots.**
  - The terminal `intel <type> <value>` built-in currently calls provider lookup and renders
    results, but it does not persist successful provider data into `entity_intel_snapshots`.
    Atlas modal **Refresh intel** uses a separate persistence path, so Projects -> Overview
    only sees updated provider data after a modal refresh.
  - Add a shared persistence helper that can store lookup results for an existing matching
    Atlas entity in the active personal/team scope. Keep casual terminal lookups from creating
    new Atlas entities unexpectedly unless that behavior is explicitly designed later.
  - Success criteria: when a terminal `intel` lookup succeeds for an entity that already
    exists in Atlas, Atlas detail and Project Overview should show the refreshed provider data
    without requiring a second manual refresh from the Atlas modal.

---

## Feature Enhancements

These are possible future improvements, split by whether they look worth carrying forward.

- **Webhook receiver / `POST /api/v1/intel/<provider>` passthrough.**
  - Worth scoping once outbound notifications and external automation mature. The headless API is the right place to receive webhooks that auto-create or update projects.
- **Cross-session Atlas view.**
  - Useful for operators managing multiple sessions or shared infrastructure, especially now that team mode makes shared context more important.
- **Extend comparison beyond run-to-run finding and artifact diffs.**
  - Snapshot and package-artifact comparisons are likely useful once evidence packages become a regular handoff surface.
- **Package re-import preview/apply.**
  - Worth scoping once package handoff archives are used regularly. It should reuse the Atlas import preview/apply pattern and the package manifest import hints before it writes project data.
- **Project Monitoring CLI surface.**
  - Possible future `darklab monitoring <project_id>` and `darklab monitoring ack <project_id> <fire_id> --state STATE [--note NOTE]` commands could expose the Project Monitoring dashboard, rollups, and fire triage flow without opening the browser.
  - Keep this lower priority than watcher creation, Project assignment, policy controls, and baseline acceptance, which are already available through `darklab watch`.
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

### Workflows v2 — playbooks with parameters
- Evolve workflows from saved command lists into reusable runbooks.
- Add typed parameters such as target, port set, and wordlist reference, then prompt for those values at execute time.
- Add conditional next-step behavior based on exit code.
- Let each step capture selected output into named variables that later steps can consume.
- Build on the existing session-variable and workflow foundations so operators can turn repeat scans into parameterized profiles without rewriting commands by hand.

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
- Reuse the run-complete notification hook so push delivery becomes another channel rather than a separate completion system.
- **Entry-level scope:**
  - Add a manifest, app icons, and a small service worker so users can "Add to Home Screen" and launch into a standalone mobile shell.
  - VAPID-signed web-push subscription tied to the active session token; subscribe and unsubscribe from the Options sheet.
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
- Keep the action close to existing triage and review-state controls so tickets feel like an extension of finding review, not a separate export step.
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
- Target custom scanner output and internal tooling first; the biggest value is letting self-hosted teams teach darklab_shell their local signal language without carrying a fork.
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
