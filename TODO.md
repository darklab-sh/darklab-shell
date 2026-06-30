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

- **Enhance the project Overview tab with app-captured data.**
  - The Overview payload (`app/services/projects/overview.py`) is built almost entirely from `entity_intel_snapshots` (cached external provider data). Ports, services, certificates, provider count, and target highlights are all provider-sourced; only the high-risk finding count and watcher recent-changes are app-native. The tab reads as a mirror of external intel rather than the state of the engagement.
  - Completion note: The finding-count rendering slice is implemented. Overview now renders project-wide triage and verification progress from the existing per-target `finding_counts`, and target rows summarize new, awaiting-verification, false-positive, and suppressed finding work without changing the backend payload.
  - North star: the Overview tab should answer what targets have been touched, what still needs review, what has been verified, what has no scan evidence, and whether the project deliverables are stale.
  - Render the per-target `finding_counts` block (`by_review_state`, `by_verification_state`, `suppressed`) that the backend already computes and the frontend (`project_overview.js`) currently discards.
    - Add a project-wide triage funnel rollup: New → Reviewed → Important/Needs-followup, plus suppressed and false-positive counts.
    - Add a verification progress funnel: not_started → ready → verified → needs_retest. Show `not_applicable` as an aside count, not a funnel stage (like suppressed/false-positive in the triage funnel), so the funnel math reconciles with the total. The backend `FINDING_VERIFICATION_STATE_ORDER` is not_started → ready_to_verify → verified → needs_retest → not_applicable.
    - Frontend-only; no backend change needed since the data is already on the wire.
  - Add operational tempo from runs and the audit timeline as a bounded backend summary in the Overview payload.
    - Last run time, runs in the last 7d, last finding triaged, last artifact captured.
    - A short recent-activity strip with deep-links, reusing the Activity tab's target-type → workspace-tab mapping.
  - Completion note: The operational-tempo slice is implemented. Overview now returns a bounded `operational_tempo` summary for linked runs, triage, and artifacts, plus a short `recent_activity` strip sourced from scoped audit events. The UI renders those fields as compact cards and activity jump buttons that reuse the existing workspace tabs.
  - Add coverage/gap signals by crossing app-captured runs and findings against the target list. Split these into what is answerable now versus what is gated on future capture.
    - Answerable now from app data (ship first): targets no app run has touched (targets carry `source_run_id`, and findings/runs link back — no provider port data needed), targets with findings awaiting verification, and targets with stale or missing follow-up.
    - Gated on future app-native port/service capture: "scanned but nothing found" style gaps. The Overview's ports/services come only from `entity_intel_snapshots` today; there is no per-target app-native port rollup (nmap-import parsing lands in findings/entities, not a port structure), so this gap waits on that capture work.
    - Negative evidence is a distinct requirement: port entities prove "this scan found open ports," but they cannot by themselves prove "this host was scanned and had none." Distinguishing "scanned, no open ports" from "untouched" needs scan-observation evidence (which host a run actually scanned), tracked as its own stream — see the port entity TODO's scan-observation item. Caveat: even with that evidence we usually do not know the scan's port coverage, so the honest claim is "scanned in a run that surfaced no ports," not "no open ports exist."
    - Treat provider-derived ports/services separately from app-captured evidence. If a gap uses cached provider ports, label it clearly as provider-derived until the backend has app-native port evidence for that target.
    - Turns Overview into an actionable worklist instead of just a read-only intel summary.
  - Completion note: The answerable coverage-gap slice is implemented. Overview now returns bounded `coverage_gaps` for targets with no app-captured scan, targets awaiting verification, and targets needing review/follow-up, plus rollup counts for targets awaiting verification and needing follow-up. The UI renders those gaps as a compact worklist with existing Entities/Findings deep-links.
  - Add a deliverables status line for Packages/Report as another bounded backend summary.
    - Last package built, last report saved/exported, and report freshness versus the latest finding or triage update.
  - Completion note: The deliverables-status slice is implemented. Overview now returns a bounded `deliverables_status` summary for latest package save/build, latest report save/export, latest finding activity, and report freshness. The UI renders it as compact deliverable cards with a freshness badge.
  - Demote external intel honestly: keep the ports/services/cert panel, but make provider freshness more visible.
    - `last_checked_at`, stale flags, and `Intel: Stale`/`Intel: None` already exist; surface them more clearly in summary and row details.
    - Add a clear "cached provider data" caveat anywhere the UI might otherwise imply live app-captured state.
  - Completion note: The cached-provider polish slice is implemented. Overview now labels provider-backed port/service counts as cached provider data, shows a visible cached-provider caveat before target rows, and includes per-target provider freshness details with stale/no-intel states and the latest checked timestamp when available.
  - Suggested sequencing:
    - First: render finding triage and verification rollups from existing `finding_counts`.
    - Second: add backend overview summaries for app-captured runs, artifacts, and recent activity.
    - Third: add the coverage gaps that are answerable now from run/finding linkage (untouched targets, awaiting verification, stale follow-up); defer the port-dependent "scanned but nothing found" gap until app-native port capture exists.
    - Fourth: add deliverables status for Packages/Report.
    - Fifth: polish copy and visual treatment around cached provider intel.

- **Add a project filter to the Atlas modal and surface the project scope as a clearable chip.**
  - "Open in Atlas" from the Projects modal (`project_navigation.js` → `openAtlas`) launches the Atlas overlay scoped to the project, but the scope is invisible: it lives only in `state.projectId`/`state.projectName` (`atlas_overlay.js`) and surfaces faintly in the subtitle. There is no filter control or chip, no way to clear it, and no way to filter by project from within Atlas — the Projects-modal button is the only entry point.
  - Add a project filter control alongside the existing Atlas filters (run search/select, finding status, orphan, suppression) in the template (`app/templates/index.html`, the `atlas-*-filter` row) so users can scope to any project from inside the modal.
  - Model it on the existing run filter: a `select` plus a clearable chip (`atlas-run-filter-chip` is the pattern), wired into `state` and the existing filter request/persistence path (the `filters` payload already carries `project_id`/`project_name`).
  - When launched via "Open in Atlas", show the project filter as applied — the chip is visible and the dropdown reflects the launched project.
  - Give it the same clear behavior as other filters: clicking the chip's `x` and the "Clear filters" button (`atlas-clear-filters-btn`) both reset the project scope, and changing the dropdown re-scopes.
  - Completion note: The Atlas project-filter slice is implemented. Atlas now has a project filter select beside the existing run/status/orphan/suppression filters, shows project-launched scope as a clearable chip, lets users switch to another project from inside Atlas, preserves project scope in saved views, and clears project scope through either the chip or **Clear filters**.

- **Change Findings-tab row click to open the finding in Atlas instead of restoring its source run.**
  - Today a finding row (and its "Open" button) fire `open-finding`, which restores the source run into a terminal tab, highlights the finding's output line, and closes the Projects workspace (`project_workspace_events.js`, `action === 'open-finding'`). A primary click doing something destructive — tearing down the modal and dropping into the terminal — is surprising and inconsistent with the Entities tab, where row click opens the entity in Atlas (`open-project-entity`).
  - Make a finding row's primary click open that finding in Atlas, matching the Entities-tab pattern. Atlas already manages findings (finding filters, bulk triage, findings board, and finding detail in `atlas_entity_detail.js`); confirm or add a deep-link/focus path to a single finding.
  - Keep run access as an explicit secondary action rather than removing it — viewing a finding in its raw output context with the exact line highlighted is unique value Atlas does not provide.
  - Decide where that secondary action lands, noting the line-highlight tradeoff.
    - The current terminal-restore path highlights the finding's exact output line (`highlightLineIndex`).
    - The Run Details modal (`openHistoryRunDetails`, `history_run_details.js`) is less disruptive (overlay, preserves project context) but currently has no line-highlight support.
    - Either keep "See in run" doing the terminal restore, or port line-highlight into the Run Details modal before pointing the action there; do not lose line-highlight in the swap.
  - Apply the same change to the mobile findings surface for parity.
  - Completion note: The Findings-row primary action slice is implemented. Desktop and mobile Project Findings rows now open the selected finding in project-scoped Atlas, Atlas accepts a requested finding id and selects it after the Findings list loads, and the raw source-run path remains available as an explicit **See in run** action with the original terminal line highlight.

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
