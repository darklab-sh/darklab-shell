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
  - [Diff-aware scheduled monitoring dashboards](#diff-aware-scheduled-monitoring-dashboards)
  - [Attack-surface delta digest notifications](#attack-surface-delta-digest-notifications)
  - [Project-scoped target intelligence overview](#project-scoped-target-intelligence-overview)
- [Architecture](#architecture)
  - [Unified terminal built-in lifecycle](#unified-terminal-built-in-lifecycle)
  - [Plugin-style helper command registry](#plugin-style-helper-command-registry)
  - [Lightweight Jinja base template](#lightweight-jinja-base-template)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

### Frontend asset build pipeline

The shell now has a committed, manifest-backed build pipeline for CSS and classic JavaScript bundles. The remaining work is to make bundle mode the shipping default, then follow with a separate lazy-loading pass for rarely-first-paint code.

**Why this is open:**
- Bundle mode is still opt-in. Production, CI, and end-to-end runs should switch to `asset_bundle_mode=bundle` so they exercise the same content-hashed files that ship.
- Bundling the current classic scripts reduces request count, not first-load JavaScript bytes. The first byte-weight win should come from lazy-loading rarely-first-paint features, not from concatenating every eager module into one file.
- Immutable cache headers are applied by `/static/` and `/vendor/` path prefix. The build already covers bundle membership and order, but the repo still needs a template guard that rejects hard-coded static/vendor URLs without `static_asset()` or `asset_bundle()`.

**Implementation plan:**
- Keep `asset_bundle_mode` deterministic: `source` renders ordered source-file tags from the manifest, and `bundle` renders single hashed bundle tags while failing loudly at runtime if the manifest is missing or incomplete. Production, CI, and end-to-end runs should use `bundle` so they exercise exactly what ships.
- Do not force `bundle` everywhere: bundle-only would tax the dev inner loop (a rebuild on every source edit), risk silently serving stale bundles during development, and couple Python route tests and local e2e to a fresh Node artifact. The source/bundle divergence risk that a single mode would avoid is covered by the dual-mode route tests, the order-equivalence assertion, and the structural coverage check.
- Keep stale-manifest detection in `assets:check`, not in request rendering. The check can compare source hashes to the manifest during build/CI, while runtime bundle mode should only enforce that the manifest is present and complete.
- Keep `/static/build/...` on immutable cache headers. Dynamic HTML should stay fresh.
- Two cache-busting schemes coexisting is intentional, not a half-done migration: bundles use content-hashed filenames, while non-bundled static assets (fonts, images, and standalone vendor such as jspdf and xterm) keep the existing `static_asset()` `?v=` query string. Those files change rarely, so `?v=` is sufficient and hashing their filenames is not worth the extra build machinery now. See the Technical Debt note about unifying this later.
- Do not carve a lean permalink-only CSS bundle now, even though permalink's JS is self-contained. CSS is treated differently from JS here on purpose: the JS decoupling was driven by correctness and coupling (shell-core runs session/teams/state logic permalink never executes, and a shell-core change could break the share page), whereas unused CSS is only wasted bytes and cannot break anything. Carving permalink CSS would require auditing which shared stylesheets it actually needs, with real regression risk for modest byte savings, so permalink loads the shared `app.css` as it does today. A lean permalink CSS bundle is a future lever to pursue only if permalink CSS weight is ever measured as a problem.
- Preserve the existing source files as the canonical files for development and unit tests.

**Implementation phases:**

Each phase is independently shippable and verifiable. `source` mode lets the full pipeline land without changing what ships, so the foundation is proven before the order-sensitive JS cutover. Do not start a phase until the previous phase's exit criteria are met.

- **Phase 3 — Make bundle the default and remove the source-list fallback.** Set production, CI, and e2e to `asset_bundle_mode=bundle`, confirm everything stays green, then remove any template path that still emits the full source-file list in normal operation.
  - Exit criteria: bundle mode is the production default; no template emits the raw source-file list in normal operation; `source` mode remains available for local development and Python route tests.
- **Phase 4 (later, separate) — lazy-loading and ESM.** Make `jspdf`/`export_pdf` lazy on first PDF export, then pursue broader lazy-loading of rarely-first-paint modules (Projects, Atlas, Watchers, report builder, Findings Board, PTY/xterm) and an incremental ESM migration, one low-risk area at a time. This is the first-load byte-reduction pass and is explicitly distinct from the request-count work in Phases 1–3; keep it deferred until those wins are in place.

**Testing and documentation:**
- Add `assets:check` coverage for stale manifests by changing a source file after build and asserting the check fails without requiring runtime re-hashing.
- Add a CI lint/test that scans templates and fails when a `/static/` or `/vendor/` URL is hard-coded instead of being resolved through `static_asset()` or the bundle manifest helper.
- Keep route tests covering source and bundle modes, missing-manifest failures, and `/static/build/...` cache headers as the bundle manifest grows.
- Keep Vitest coverage against source modules; the build should not make tests depend on minified output.
- Run targeted browser coverage through `bash scripts/run_playwright.sh ...` for shell boot, run streaming, and permalink rendering when switching production/CI/e2e to bundle mode.
- Update README.md, FEATURES.md, ARCHITECTURE.md, CONFIGURATION.md if needed, CHANGELOG.md, release drafts, and test-count docs when implementation changes behavior or coverage.

**Acceptance criteria:**
- First-load static request count drops substantially without breaking local development ergonomics.
- First-load byte size does not need to drop in the classic-bundle pass, and the plan keeps an explicit follow-up path for lazy-loading heavy feature modules.
- The first rollout stays dependency-free and unminified. Minification is out of scope until sourcemaps and separate review coverage are added.
- Static bundles use content-hashed filenames and immutable cache headers.
- HTML templates reference manifest-backed bundle URLs in normal operation, and CI rejects unversioned `/static/` or `/vendor/` references that would receive immutable cache headers without a cache-buster.
- `asset_bundle_mode` is exactly two modes, `source` and `bundle` (no `auto`), each deterministic and testable, including a fail-loud bundle mode when the manifest is unavailable.
- Production, CI, and e2e use `asset_bundle_mode=bundle`; local development and Python route tests default to `source` so the suite runs on a clean checkout without a Node build.
- `assets.config.json` is the single source of truth for bundle membership and order; templates compose bundles rather than listing source files, and Flask renders both modes from the compiled `manifest.json` alone.
- Every `app/static/js/**` source file is covered by at least one bundle or the explicit lazy/excluded allowlist, enforced structurally by `assets:check`, so a new unbundled file fails CI. Files shared intentionally across bundles (such as render primitives reused by the self-contained `permalink` bundle) are allowed in more than one bundle.
- `permalink` is a self-contained bundle with no dependency on `shell-core`, and PDF export becomes lazy on the permalink surface in the later lazy-loading pass.
- Missing or incomplete build output fails loudly at runtime in bundle mode; stale build output fails in `assets:check` and CI without adding per-request source hashing.
- Built bundles and the manifest are committed, `.gitignore`-allowlisted, regenerated by `assets:sync`, and drift-guarded by `assets:check` in CI — with no new runtime-image build dependency and no bundle generation at container boot.
- Existing shell, permalink, diagnostics, and mobile flows keep working with the bundled assets.

---

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

- **Unify static-asset cache-busting on content-hashed filenames.** After the frontend asset build pipeline lands, the app uses two cache-busting schemes: content-hashed filenames for bundles and `static_asset()` `?v=` query strings for non-bundled assets (fonts, images, and standalone vendor such as jspdf and xterm). The split is intentional for now because those files change rarely, but a future pass could move them to hashed filenames too for one consistent scheme and to avoid query-string URLs that some proxies and CDNs cache conservatively. This needs the build to rewrite in-CSS font/image references to the hashed paths, so it is deferred until the bundle pipeline is stable.

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

- **External tool integration candidates:** add the strongest reviewed tool gaps when they fit the sandboxed registry, findings, Atlas, and provenance model. High-value candidates are ProjectDiscovery's `tlsx` for TLS/certificate metadata and `cdncheck` for CDN/WAF classification, plus `trufflehog` or `gitleaks` for exposed-secret findings from repos and files. Medium candidates are resolver-backed brute-force DNS tools such as `puredns` or `shuffledns`, Shodan InternetDB as a free/no-key IP context provider, optional FOFA/ZoomEye providers for users with keys, and a `nuclei` template management or pinning surface so scan provenance can explain which template set produced a result. A lower-risk app-native `jq`-style JSON/JSONL selector could also extend safe post-filtering without exposing real shell pipes.

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

### Diff-aware scheduled monitoring dashboards
- Combine schedules, Watchers, run comparison, and tool-aware diff parsing into a project-level monitoring view.
- Let an operator schedule a command, choose a baseline, and review each later run as a timeline of changes instead of reading every transcript from scratch.
- Surface high-signal deltas such as new or closed ports, new or disappeared subdomains, HTTP status/title changes, and TLS certificate changes.
- Keep the dashboard tied to Projects, Atlas entities, findings, and notifications so monitoring results become part of the normal engagement workflow.

### Attack-surface delta digest notifications
- Send scheduled project summaries such as "since last week: 3 new subdomains, 2 new open ports, 1 certificate expiring soon" through the existing notification channels.
- Build the digest from watcher diffs, run-comparison classifiers, Atlas entity counts, and provider-enriched target context instead of inventing a separate reporting path.
- Let operators tune cadence and scope per project so noisy scan projects can stay quiet while recurring monitoring projects stay visible.

### Project-scoped target intelligence overview
- Add a project overview surface that rolls up hosts, ports, services, cert expirations, top findings by severity, and provider-enriched context for each target.
- Treat the overview as an engagement console: enough context to understand the current attack surface before drilling into individual runs, targets, Atlas rows, or findings.
- Reuse existing project summaries, Atlas materialization, target relationships, findings, and intel provider snapshots so the overview stays consistent with the rest of the workspace.

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
