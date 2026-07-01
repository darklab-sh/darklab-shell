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

- **Relate URL entities to their domain, and auto-create the domain on capture.**
  - Scope:
    - Depends on the `host` to `domain` collapse above so URLs, ports, and domains all converge on `domain` or `ip` host entities.
    - Reuse the existing `host_entity_id` relationship column. It already represents "the host this entity belongs to" for ports, and URLs fit that relationship without a schema rename.
    - Apply the relationship to live command capture, imports, package re-import paths, and existing stored URL entities where practical.
  - Phase 1: Define URL host identity once.
    - Add a shared URL host derivation helper in the Atlas materialization layer or nearby utility code.
    - Parse the canonical URL host, then canonicalize it to either `ip` or `domain`.
    - Cover ports, userinfo, mixed-case hostnames, bracketed IPv6 addresses, invalid URLs, and URLs with no host.
  - Phase 2: Link URL entities during materialization.
    - Extend the current port-only `host_entity_id` derivation so `url` entities can derive their host entity ID.
    - Avoid dangling relationships: either ensure the derived host entity exists before storing `host_entity_id`, or only store the link when the host entity is present.
    - Resolve the host entity id within the URL entity's own scope (`session_id` for personal rows, `team_id` for team rows), matching how entity identity and uniqueness are already keyed, so a URL never links to a same-value host entity from another scope.
    - Do not rely only on extraction co-emission. Materialization must handle URL-only callers, imports, and package paths by either ensuring/counting the URL host entity before URL upsert or intentionally leaving `host_entity_id` blank until a matching host entity exists.
    - Keep the existing port behavior intact and avoid changing port canonical values or port relationship semantics.
  - Phase 3: Co-create host entities when URLs are captured.
    - Co-emit the URL's `domain` or `ip` host entity when a URL entity is captured, matching the port host co-emit pattern.
    - Apply this to generic output extraction and scanner-specific extraction paths that produce URL entities.
    - De-duplicate co-emitted host entities with the existing entity de-dupe behavior so URL lines do not create duplicate same-line host observations.
  - Phase 4: Cover import and package paths.
    - Update import parsing and package re-import paths that materialize URL entities so they also create or link the URL host entity.
    - Preserve legacy `host` import inputs as aliases after the host-to-domain collapse.
    - Add tests for imported URL entities so the feature is not limited to live command output.
  - Phase 5: Backfill existing URL entities.
    - Add an idempotent backfill for stored `entities.type = 'url'` rows with missing `host_entity_id`.
    - Match and create host entities within each URL row's own `(session_id, team_id)` scope so team and personal rows stay isolated and no cross-scope link is written.
    - Create missing host entities only if the backfill can assign sensible owner, first/last seen, occurrence, and provenance values; otherwise link only to host entities that already exist and log/measure skipped rows.
    - Land the backfill on both backends with matching semantics (SQLite compatibility migration in `database.py` and the paired Postgres migration under `core/migrations/`) and cover both under the Postgres test lane.
    - Include IP-host URLs and invalid URL rows in backfill tests.
  - Phase 6: Replace Overview's URL host resolver carefully.
    - Prefer stored `host_entity_id` when building Overview app-data rollups.
    - Retire `overview._overview_url_host_entity_ids` only after URL Project targets are guaranteed to have URL entities with stored host links.
    - If Project URL targets can exist without matching Atlas URL entities, keep a small fallback resolver for those targets.
  - Phase 7: Verification and UX payoff.
    - Update Atlas lookup/detail payloads and UI affordances so `domain`/`ip` entities can show and pivot to related URL entities through `host_entity_id`.
    - Add backend tests for URL host derivation, URL materialization links, co-created host entities, imports, package re-imports, backfill, IP-host URLs, and invalid URLs.
    - Add Overview tests proving URL targets roll up app-captured ports/services through stored host relationships.
    - Verify Atlas domain detail views can pivot to related URLs, and that host-grouped comparisons/monitoring consume the relationship consistently.
    - Update docs and test-count documentation if new tests change documented totals.
  - Open TODO: Materialize auto-discovered Project targets into Atlas when run-entity linking is enabled.
    - When an active-project-linked run discovers Project targets from command arguments or supported input files, materialize those `domain`, `ip`, and `url` target values as Atlas entities for the same run when **Also add Atlas entities from auto-linked runs** is enabled.
    - Treat legacy `host` command metadata as a compatibility alias that resolves to `domain` or `ip`, matching the Project target collapse rules.
    - Preserve provenance clearly so these Atlas rows are marked as command-target evidence, not as values observed in command output.
    - De-duplicate against entities already captured from run output and avoid duplicate project links when the same entity is produced by both target discovery and transcript extraction.
    - For URL targets, create/link the URL host entity through the URL host relationship work above so Project URL targets, Atlas URL rows, and host rollups stay consistent.
    - Add tests covering plain command URL targets such as `curl https://ip.darklab.sh`, URL target-list files, IP/domain targets, disabled run-entity linking, and duplicate output-captured entities.
  - Open Decisions:
    - Recommended: keep the column name `host_entity_id`. It is already the established relationship field and describes the role, not the entity type.
    - Recommended: during live capture, ensure the URL host entity exists before storing the URL's `host_entity_id`; this avoids invisible dangling relationships.
    - Recommended: during retroactive backfill, link to existing host entities first. Only create missing host entities when provenance can be preserved clearly enough that the new row does not look like a fresh scan observation.
    - Recommended: keep an Overview fallback for URL Project targets until tests prove every URL target has a materialized URL entity with `host_entity_id`.

---

## Known Issues

No open Known Issues are currently tracked.

---

## Technical Debt

No open Technical Debt items are currently tracked.

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
