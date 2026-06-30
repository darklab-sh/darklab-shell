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

- **Improve Overview tab readability and triage density (UI/UX pass).**
  - Motivation: with many targets (e.g. 105, 89 unscanned) the per-target list (`project_overview.js` `renderTargetRow`) renders ~7 labeled lines each, and on scan-light projects most read "No app-captured ports / No ports · No services / Intel none / No app scan". The page becomes a wall of negatives; the real signal (finding counts + severity) is buried, and the same emptiness is repeated across the `Provider:` row, `Intel:` row, `Cert: Unknown` chip, and `Intel: None` chip.
  - Collapse empty per-target detail rows (highest-impact change).
    - Render `Ports`/`Provider`/`Intel`/`Scan` rows only when they carry data; for an all-empty target, replace them with a single muted tail (e.g. `not scanned · no provider intel`) or omit entirely.
    - De-duplicate negatives: the `Provider:`/`Intel:` rows and the `Cert: Unknown`/`Intel: None` chips restate the same "nothing here"; show `Cert`/`Intel` chips only when actionable (expiring, stale), not on every row.
    - Lead with the real content (finding summary + severity) rather than ending with it.
    - Target a compact ~2-line row: title + type/review-state + severity + actions on line 1; a single muted detail line that shows only present data (ports/services inline when available) on line 2.
  - Make severity the primary visual signal.
    - Add a severity-colored left accent/border per target card driven by `top_finding_severity`, using the semantic `--red`/`--amber` tokens, so Critical/High targets are immediately scannable instead of uniform gray.
  - Add prioritization controls for long target lists.
    - Sort/group targets by top finding severity (Critical → High → …) — note `_overview_target_sort_key` already sorts by severity then cert then label, so confirm the UI reflects it and consider grouping headers.
    - Add a filter toggle such as "hide unscanned targets with no findings" to clear the empty cards in one action.
  - Fix the summary's two-tier layout (`renderRollups`).
    - The bordered "primary" cards vs borderless "secondary" items read as unfinished, and the "Watcher context / Recent changes" item floats right with no number — give the secondary row consistent alignment/treatment.
    - Reconsider grouping by theme rather than card size: Coverage (targets, scanned, unscanned), Evidence (app ports, provider ports, drift), Risk/Work (high-risk, verification gaps, certs).
    - Render "App scan coverage" as a ratio or mini progress bar (`16 of 105 · 15%`) rather than a bare count.
  - Reorder sections so aggregate panels are reachable.
    - `renderOverview` currently renders the per-target list immediately after the summary, pushing `renderFindingProgress`/`renderOperationalTempo`/`renderCoverageGaps`/`renderDeliverablesStatus` below up to `OVERVIEW_TARGET_LIMIT` (200) rows. Place aggregates directly under the summary, above the per-target worklist, or make the worklist collapsible.
  - Condense the persistent "Cached provider data" caveat (`renderProviderIntelCaveat`) to one line or an info tooltip on the badge; it partly duplicates the secondary "Cached provider ports" card copy.
  - Related data-correctness flag (cross-reference `docs/overview_update_code_review.md`): the screenshots show "Cached provider ports: 2" but "Provider/app drift: 8 targets differ" (≈ every app-port target), confirming the drift over-flag where `_overview_port_provenance` counts `app_only` as drift even when the provider has no intel (`overview.py` `has_drift`). Gate `app_only` drift on `has_intel` so the drift metric is trustworthy before leaning on it visually.
  - Apply the same density improvements to the mobile Overview surface for parity.
  - Keep all changes within the design system: passive metadata as `.badge`/`.badge-tone-*`, severity color via the semantic tokens, no one-off pill classes (see the existing `.project-overview-port-chip` vs `.badge` note in `docs/overview_update_code_review.md`).

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
