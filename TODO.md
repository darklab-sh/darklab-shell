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
  - [Right-size project documentation](#right-size-project-documentation)
  - [Unified terminal built-in lifecycle](#unified-terminal-built-in-lifecycle)
  - [Plugin-style helper command registry](#plugin-style-helper-command-registry)
  - [Lightweight Jinja base template](#lightweight-jinja-base-template)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

- **Curated cleanup reason labels for run deletion and Project unlinking.**
  - **Scope:**
    - Improve the confirmation copy and reason labels for deleting runs and removing runs from Projects so users can tell why Atlas entities and findings are considered disposable, kept by default, or not eligible for this cleanup.
    - Primary UI scope is the run deletion Atlas cleanup modal and the Project run unlink cleanup modal.
    - Audit Atlas entity/finding delete sibling-cleanup previews because they reuse the same public cleanup preview shape. Add backend reason summaries to sibling cleanup if the shared model naturally reaches `_public_preview`; decide separately whether those modals get grouped reason UI now or a follow-up TODO.
    - Keep the current conservative cleanup defaults unless implementation research finds a clear classification bug.
    - Keep this focused on preview/apply payloads, modal copy, reason grouping, helper consolidation, and regression coverage; broader cleanup policy changes should become separate TODOs.
  - **Phase 1 — Map the current cleanup classification paths:**
    - Trace the run deletion preview/apply path through `app/services/atlas/cleanup.py` and `history_mutations.js`, including the entity/finding delete sibling-preview callers that use `_public_preview`.
    - Trace the Project unlink preview/apply path through `app/services/projects/links.py`, `project_workspace_actions.js`, and `history_project_actions.js`.
    - List every current signal that moves an entity or finding out of the disposable bucket, including Project links, link source/confidence/review state/source-detail flags, labels, notes, finding review/status state, source-run overlap, imported Atlas rows, project-linked finding occurrences, direct project-linked runs, parent entity Project links, and finding attachment to a kept entity.
    - Separate "kept by default because curated" from "not eligible for this cleanup." In run deletion, rows seen in other runs and imported rows are filtered out before curated counts; in Project unlink, rows seen in other runs are counted as curated/kept.
    - Record where the two flows intentionally differ so the UI can explain the difference instead of hiding it behind one generic "curated" label.
    - Reconcile signals that share a name but differ in predicate across the two flows before mapping them to one reason code. Classify each divergence as either a classification bug or an intentional policy choice before changing behavior. Bug fixes can make more rows disposable when they remove incorrect cross-session or cross-owner signals; policy choices should default to the more conservative, keeps-more-items behavior unless the product decision is explicit.
    - Treat the missing session scope on run deletion's entity label and note checks as a likely correctness bug to investigate and fix on its own merits. The finding-label check in the same run deletion path already scopes by session, and Project unlink scopes entity labels and notes by session.
    - Decide the empty-note behavior explicitly. Run deletion treats any `entity_notes` row as curated, while Project unlink requires `trim(note.body) != ''`; if empty notes are a policy choice rather than a bug, keep the more conservative behavior or use flow-specific copy so users are not misled.
    - Map the team-scope gap; it is already reachable, not hypothetical. The direct Atlas cleanup routes are session-gated by `run_belongs_to_session` (`app/blueprints/atlas_mutations.py`), but history deletion finds the run with the team-aware `owner_scope` predicate and then calls the Atlas cleanup with only `session_id` (`app/services/history/mutations.py` `delete_history_run`), so a team-owned run reaches session-only cleanup predicates today. Treat team-aware cleanup predicates (or an explicit guard on the history-delete cleanup call) as likely work in this effort, not a distant maybe.
    - Fix the preview/delete scope asymmetry on the history path regardless of the labeling work: `history_run_cleanup_preview` is session-only while `delete_history_run` deletes via the team-aware `owner_scope`, so a team-owned run can show an empty/"not found" preview yet still delete the run while Atlas cleanup is computed through a session-only path, causing preview/apply disagreement and likely missed cleanup. The Phase 4 preview/apply parity tests must cover this cross-team boundary.
    - Capture one or two representative payload fixtures for fresh scan, Project-linked scan, and manually curated scan cases.
    - **Completion notes — Phase 1 first pass:**
      - Run deletion path mapped: `history_mutations.js` loads `/history/<run_id>/atlas-cleanup-preview`, `app/blueprints/history.py` delegates to `history_run_cleanup_preview`, deletion uses `delete_history_run`, and both converge on `atlas_run_cleanup_preview` / `delete_atlas_cleanup_preview` in `app/services/atlas/cleanup.py`. Direct Atlas run cleanup and entity/finding sibling previews also reuse `atlas_run_cleanup_preview` and `_public_preview`.
      - Project unlink path mapped: Project workspace and history entry points call `/projects/<project_id>/links/run-entities/remove-preview` and `DELETE /projects/<project_id>/links`, which delegate to `preview_project_run_entity_unlinks`, `unlink_project_run_entities`, and `_project_run_entity_unlink_candidates` in `app/services/projects/links.py`.
      - Run deletion buckets mapped: disposable items are single-source, non-imported, non-excluded rows that do not trip the curated predicates and whose child findings can also be removed. Rows seen in other runs, imported rows, explicit exclusions, and entities with remaining child findings are not eligible for this cleanup. Kept-by-default curated signals include Project links, reviewed/status-changed findings, finding Project links, finding labels/notes, project-linked finding occurrences, direct project-linked source runs, and parent entity Project links.
      - Project unlink buckets mapped: disposable entity links are default/auto-target links that are only sourced by the unlinked run set and have no other keep signal. Kept-by-default signals include other source runs, other Project links, labels, non-empty notes, kept child findings, and non-disposable/manual/custom link metadata. Project unlink counts findings by how Project visibility changes after removing the run link and then removable or kept-by-default entity links.
      - Classification fixes landed: run deletion entity label/note curation now scopes metadata to the entity owner session, matching the existing finding label/note checks; Project unlink candidate queries now use shared owner predicates for run/entity/finding visibility and metadata-owner predicates for entity and child-finding labels/notes.
      - Team-scope cleanup landed: history cleanup preview now authorizes through the same owner scope as deletion, history deletion computes Atlas cleanup from the authorized run row's Atlas owner session, and Atlas cleanup reason predicates classify team-owned Project links and metadata by team ownership instead of only by the source run creator's session.
      - Empty-note policy left unchanged for now: run deletion still treats an owner-scoped note row as curated even if the body is empty, while Project unlink keeps the existing non-empty-note predicate. Phase 2 reason labels should preserve that distinction unless the product decision changes.
      - Representative fixtures added in tests: cross-session entity metadata no longer marks run cleanup as curated, team-owned history cleanup preview matches delete for owner-scoped Atlas rows, and team Project run unlink preview matches delete for owner-scoped entities.
  - **Phase 2 — Add a shared reason summary model:**
    - Treat the run deletion backend as the heavier lift: decompose `_finding_curated_sql`, `_entity_curated_sql`, and the hard-exclusion predicates into reason-level signals instead of assuming the existing aggregate `curated_entity_count` / `curated_finding_count` values can explain themselves.
    - Derive an item's bucket membership and its per-reason flags from a single evaluation per item, not two parallel code paths, so the disposable/kept/not-eligible decision and the reason attribution cannot drift and each look correct in isolation while disagreeing.
    - Measure preview latency on a large run before and after reason summaries. Prefer one candidate query that emits per-reason boolean flags per row and aggregates in Python over many separate `COUNT` scans, especially because multi-reason attribution means the query cannot short-circuit after the first matched reason. Use separate count queries only if the measured database plans are clearly better.
    - Treat Project unlink as the lighter lift: tally the existing per-row booleans (`has_other_runs`, `has_other_projects`, `has_labels`, `has_note`, `has_curated_findings`) plus the `_project_run_entity_link_is_disposable` result into the same reason-summary shape.
    - Introduce named cleanup reason codes with user-facing labels and short descriptions for the actual predicates, including disposable default Project links, non-disposable/manual/custom Project links, other Project links, other source runs, entity labels, entity notes, finding review/status state, finding Project links, finding labels, finding notes, finding occurrence in a project-linked run, direct project-linked source run, parent entity Project link, finding attached to a kept entity, imported entity/finding, and rows not eligible for this cleanup.
    - Mark which reason codes are shared versus single-flow. Finding occurrence in a project-linked run, direct project-linked source run, parent entity Project link, and imported-row exclusion exist only on the run deletion path today, so the payload contract and tests must not assume every code can appear from both endpoints; a shared vocabulary that emits structurally empty codes on one side repeats the `seen_in_other_runs` mismatch this plan already fixes.
    - Model reason groups separately from item buckets so the payload can distinguish disposable, kept-by-default/curated, and items not eligible for this cleanup.
    - Return grouped reason summaries from both primary preview endpoints, with counts per reason and per item kind.
    - Keep item IDs and raw values bounded or omitted unless the existing modal already exposes them.
    - Reuse the same reason mapping when apply responses summarize what was removed or kept.
    - **Completion notes — Phase 2 first pass:**
      - Added `services.cleanup_reasons` as the shared reason-summary model. It defines the additive `cleanup_reasons` payload with stable bucket names (`disposable`, `kept_by_default`, `not_eligible`), per-kind bucket totals, and per-reason counts keyed by code and bucket.
      - Run deletion now derives cleanup IDs, kept-by-default counts, not-eligible counts, and reason attribution from one candidate row evaluation per item kind instead of the old aggregate OR-chain count queries. The existing public fields (`entities`, `findings`, `curated_entities`, `curated_findings`, `curated_total`) remain unchanged for compatibility.
      - Run deletion reason coverage includes reviewed findings, finding Project links, finding labels/notes, Project-linked finding occurrences, direct Project-linked source runs, parent entity Project links, entity Project links, entity labels/notes, imported rows, rows seen in other runs, explicit exclusions, and entities blocked by kept findings.
      - Project unlink previews now attach the same `cleanup_reasons` shape by tallying the existing per-row booleans for other source runs, other Project links, labels, non-empty notes, curated child findings, and non-disposable/custom Project link metadata. Disposable Project link reasons distinguish default Project links from auto-target Project links.
      - Finding reason summaries for Project unlink are derived from the existing visibility deltas: source-run removal, findings attached to removed entity links, and findings attached to kept entity links.
      - Sibling Atlas entity/finding delete previews receive backend reason summaries automatically through `_public_preview`; grouped sibling-preview UI remains deferred to Phase 3/4 unless it is low-cost during the modal copy work.
      - The first pass is counts-only and intentionally omits raw IDs/values from the public reason payload. Kept/not-eligible samples remain a Phase 3 UI decision.
  - **Phase 3 — Update the confirmation modals:**
    - Move run deletion directly to grouped reason copy instead of doing a temporary parity-only copy pass, unless that interim wording has standalone release value.
    - Replace broad curated wording with grouped explanation copy that says why items will be kept by default or not eligible for this cleanup.
    - Use compact labels or chips where space is tight, such as "seen elsewhere", "imported", or "excluded", while keeping the full phrase "not eligible for this cleanup" in explanatory copy.
    - Keep destructive checkboxes explicit, especially when only one cleanup option is visible.
    - Show findings attached to kept entities with their own clear reason instead of making them look manually curated.
    - Make run deletion and Project unlinking use the same labels where the underlying reason is the same, while preserving flow-specific context where it differs.
    - Consolidate the near-duplicate Project unlink modal render blocks into a shared reason-rendering helper instead of editing `project_workspace_actions.js` and `history_project_actions.js` independently.
    - Use the shared helper from the run deletion modal too where the copy structure matches; keep only flow-specific sentence fragments local.
    - **Completion notes — Phase 3 first pass:**
      - Added `app/static/js/ui/cleanup_reasons.js` as the shared cleanup-preview copy helper for run deletion and Project unlink confirmations.
      - Project workspace and Run Details Project unlink confirmations now delegate to the shared helper and use the same "disposable", "kept by default", and "not eligible for this cleanup" wording.
      - Run deletion now uses grouped cleanup reason copy, keeps the destructive checkboxes explicit, and shows a not-eligible note when imported, seen-elsewhere, excluded, or kept-child-finding rows are present.
      - Atlas entity/finding delete sibling-cleanup previews now use the shared grouped reason copy too, so same-run cleanup language stays aligned across History delete, Project unlink, direct source-run cleanup, and sibling delete prompts.
      - Browser-unit harnesses load the shared helper, and copy assertions now cover the new kept-by-default and not-eligible wording.
  - **Phase 4 — Add regression coverage and docs:**
    - Add route/service tests for reason summaries in fresh, Project-linked, manually linked/custom-linked, reviewed/status-changed, labeled/noted, imported/not-eligible-for-this-cleanup, project-linked finding, parent-entity-linked, finding-attached-to-kept-entity, and cross-run cases.
    - Add preview/apply parity tests that assert preview reason buckets, item IDs, and apply results agree for removed, kept-by-default, and not-eligible items. Include the path where run deletion recomputes the preview before applying cleanup.
    - Add browser-unit coverage for modal copy and checkbox visibility when only disposable, only kept-by-default/curated, only not eligible for this cleanup, or mixed buckets are present.
    - Add focused coverage for the shared Project unlink render helper so history and Project workspace entry points cannot drift.
    - Add focused Playwright coverage only if a real browser interaction risk remains after browser-unit coverage.
    - Update `CHANGELOG.md` and any relevant user-facing docs if the final labels or modal behavior materially change.
    - **Completion notes — Phase 4 first pass:**
      - Route coverage now asserts reason-summary buckets for disposable default links, auto-target links, custom Project link metadata, other Project links, entity labels, entity notes, imported rows, seen-elsewhere rows, Project-linked finding occurrences, and findings attached to kept entities.
      - Preview/apply parity coverage now includes run deletion recomputing cleanup before apply, history cleanup preview versus delete for team rows with cross-member Project links, and Project unlink preview versus delete for owner-scoped team entities.
      - Browser-unit coverage now asserts the shared modal wording for mixed disposable/kept/not-eligible buckets in both Run Details and Project workspace entry points.
      - Atlas browser-unit coverage now asserts entity/finding sibling cleanup prompts render grouped disposable and kept-by-default reasons from the shared preview payload.
      - Focused Playwright coverage is deferred for now because the shared helper is covered through browser-unit harnesses and no remaining browser-only interaction risk is known.
      - `CHANGELOG.md`, `README.md`, `FEATURES.md`, and the documented test-count appendix now describe the clearer cleanup buckets and current coverage.
  - **Decision resolution notes:**
    - UI copy now uses "disposable", "kept by default", and "not eligible for this cleanup"; "curated" is no longer the primary modal label.
    - Reason summaries remain counts-only in this implementation. Bounded kept/not-eligible value samples are a follow-up candidate because they require extending the public preview shape and both cleanup classifiers without making large previews heavy.
    - The backend model counts each item under every matching reason, while destructive modals keep bucket counts as the visible reconciliation surface and show reason labels as explanatory copy.
    - Because this implementation is counts-only, destructive modals render aggregate reason labels as a short capped sentence rather than as chips. Per-item reason chips remain part of the bounded-samples follow-up, where each chip can attach to a specific kept/not-eligible row instead of looking like another headline count.
    - Findings attached to kept entities use a dedicated reason instead of inheriting the parent entity's reason label.
    - Entity/finding sibling delete previews receive backend reason summaries and now render grouped reason UI through the same helper as the primary cleanup flows.
    - Team-owned history cleanup preview/delete now use team-aware cleanup predicates for the reachable history path. Direct Atlas cleanup routes remain session-gated by design.
    - Reason codes remain UI preview metadata rather than a stable headless API contract.
  - **Resolved decision record:**
    - UI wording uses "disposable", "kept by default", and "not eligible for this cleanup." The word "curated" remains only as legacy shorthand in older test names or implementation-facing compatibility fields.
    - Reason summaries are counts-only in this implementation. Bounded kept/not-eligible value samples are tracked as the separate follow-up below.
    - The backend counts each item under every matching reason so no signal is hidden. Destructive modals reconcile by bucket totals and show reason labels as explanatory copy, so reason totals do not have to equal bucket totals.
    - Findings attached to kept entities use the dedicated `finding_attached_to_kept_entity` reason instead of inheriting the parent entity's labels or Project-link reason.
    - Entity/finding delete sibling-cleanup previews receive the same backend reason summary shape and render grouped reason copy through the shared cleanup helper.
    - Team-owned history cleanup preview/delete use team-aware cleanup predicates for the reachable history path. Direct Atlas cleanup routes remain session-gated by design.
    - Reason codes are browser-preview metadata for confirmation copy, not a frozen headless API contract.
- **Add bounded kept/not-eligible samples to cleanup previews.**
  - **Scope:**
    - Extend the cleanup preview reason payload with a small, bounded set of display-only samples for rows kept by default or not eligible for cleanup.
    - Keep the headline bucket counts as the primary destructive-confirmation surface; samples should help users understand surprising kept rows without turning large cleanup previews into heavy payloads.
    - Do not add disposable-row samples in the first version.
    - Prefer user-facing values such as entity canonical values and finding titles over raw IDs, and cap samples per bucket/kind so large scans cannot make the modal noisy.
    - Preserve personal/team scope and redaction boundaries; do not expose raw command text, output snippets, hidden IDs, or unbounded labels/notes in the sample payload.
  - **Implementation notes:**
    - Add samples in the same candidate evaluation pass that builds bucket/reason summaries so sample rows cannot drift from the counted buckets.
    - Render samples in collapsed or compact modal details for History delete, Project unlink, Atlas source-run cleanup, and Atlas sibling delete prompts. Use passive reason badges/chips on those per-item samples when space allows, while keeping the aggregate bucket reasons as short explanatory text.
    - Add tests for sample caps, empty-sample payloads, team-scope ownership, and copy behavior when samples are present.
- **Expose static boot-time metadata as Docker container labels.**
  - **Scope:**
    - Surface a small set of static, boot-time app facts as Docker image/container labels so CheckMK's Docker plugin (and any other label-aware tooling) can show them alongside the container without scraping `/metrics`.
    - This complements rather than replaces the existing Prometheus surface at `/metrics`, which already exposes `darklab_version_info`, `darklab_build_info`, `darklab_db_backend_info`, health, and sizes. Labels are the at-a-glance, Docker-native inventory view; Prometheus stays the live/numeric path.
  - **What to expose (static or config-derived only):**
    - App version, plus git revision and Python version where useful.
    - Configured database backend (`sqlite`/`postgres`).
    - Candidates worth considering: broker mode, image build date, and standard OCI provenance fields (title, source, revision).
    - Keep the set to values that are fixed for the container's lifetime. Live or changing values such as health, database size, and pool state stay in Prometheus, since labels are frozen at container creation.
  - **Approach:**
    - Drive build-time constants from OCI `LABEL`s in the Dockerfile via a version build-arg, using `org.opencontainers.image.*` keys where they fit.
    - Source runtime-config values from interpolated labels in `docker-compose.yml` that read the same env the app reads, for example `${DATABASE_BACKEND:-sqlite}`, so the label matches the app's actual resolution. The backend is resolved purely from the `database_backend` config key, so a label mirroring `DATABASE_BACKEND` does not drift from a `DATABASE_URL` override.
    - Pick one source of truth for the version string before wiring it in; `config.py` `APP_VERSION` and `package.json` currently disagree (`2.4` versus `2.4.0`).
    - Namespace custom labels under a stable prefix such as `sh.darklab.*` and keep the set documented.
  - **Docs and verification:**
    - Document the label set and the CheckMK Docker-plugin consumption path in the monitoring/configuration docs, noting labels are the static inventory view and `/metrics` is the live view.
    - Verify labels appear via `docker inspect` and that the database-backend label tracks `DATABASE_BACKEND` when it changes.

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

### Right-size project documentation
- Problem: several docs are treated as append-only logs and have grown past the point of being read or kept accurate — `CHANGELOG.md` (~792K), `README.md` (~127K), `ARCHITECTURE.md` (~280K), `FEATURES.md` (~188K). Documentation this large drifts from reality and buries the parts newcomers actually need.
- Approach:
  - Keep the README navigational and short; let it point into deeper docs rather than duplicating them.
  - Make `ARCHITECTURE.md` and `FEATURES.md` describe current state concisely, and confine chronological history to `CHANGELOG.md`.
  - Align with the existing documentation standards work so state docs stay free of migration/phase narrative that belongs in the changelog.

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
