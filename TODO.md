# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Shorten release image builds and failure feedback](#shorten-release-image-builds-and-failure-feedback)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
  - [Reduce pytest feedback time without weakening release coverage](#reduce-pytest-feedback-time-without-weakening-release-coverage)
  - [Organize script entrypoints and implementation helpers](#organize-script-entrypoints-and-implementation-helpers)
- [Feature Enhancements](#feature-enhancements)
- [Research](#research)
- [Ideas](#ideas)
  - [Run replay / scrubbable event stream](#run-replay--scrubbable-event-stream)
  - [Run comparison enhancements — deferred pieces](#run-comparison-enhancements--deferred-pieces)
  - [Bulk history export and share](#bulk-history-export-and-share)
  - [Mobile share ergonomics](#mobile-share-ergonomics)
  - [PWA install and service-worker push](#pwa-install-and-service-worker-push)
  - [Engagement report builder](#engagement-report-builder)
  - [Native ticketing integrations](#native-ticketing-integrations)
  - [Operator-extensible signal and parser rules](#operator-extensible-signal-and-parser-rules)
- [Architecture](#architecture)
  - [Unified terminal built-in lifecycle](#unified-terminal-built-in-lifecycle)
  - [Plugin-style helper command registry](#plugin-style-helper-command-registry)
  - [Lightweight Jinja base template](#lightweight-jinja-base-template)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

### Shorten release image builds and failure feedback

The multi-stage image, early vulnerability gate, release-line AMD64 registry cache, uncached native ARM64 policy, and complete compatibility and supply-chain checks shipped in v2.6.0. Release feedback dropped from roughly 80–90 minutes to 40–45 minutes, and the runtime image no longer carries its build toolchains or caches. BuildKit cache mounts and a separately published scanner base aren't planned because the added complexity isn't justified by the measured result.

- [ ] Run a scheduled pipeline on the protected active release branch with `RELEASE_CACHE_PROBE=1`. Confirm `release-cache-probe-amd64-export` passes on `bael`, then `release-cache-probe-amd64-reuse` passes on `botis` with every tracked expensive builder step reported as `CACHED`.
- [ ] Record both probe durations and retain the plain BuildKit logs long enough to confirm the cache import, export, Python base digest, and remaining uncached work. Remove this section after the cross-runner result is confirmed.

## Known Issues

No open Known Issues are currently tracked.

---

## Technical Debt

### Reduce pytest feedback time without weakening release coverage

The backend suite now takes about 150 seconds even though collecting its roughly 2,400 cases takes only about a second. A July 2026 profiling pass found three costs worth addressing:

- Ordinary route tests build a fresh Flask app for nearly every test client. `create_app()` takes about 59 ms under the test configuration, and the suite has roughly 770 direct or helper-mediated app construction sites.
- `TestProjectStructureCoverage.test_asset_build_output_does_not_depend_on_cwd` runs the complete ESM asset build twice and takes about 25 seconds. Each build also creates the production Brotli and gzip sidecars.
- `test_production_install.py` takes about 23 seconds because it exercises archive, signing, publication, installer, upgrade, and restore flows through subprocesses.

- [ ] Reuse a module- or session-scoped Flask app for ordinary route tests, with deliberate cleanup of mutable config, extension, database, and request state between cases. Keep focused factory tests that build independent apps and verify application-factory isolation.
- [ ] Make the asset working-directory determinism check exercise the generated asset graph without paying for production precompression twice. A no-precompression build mode plus focused Brotli/gzip coverage is the preferred starting point; the full committed-asset check must remain in CI.
- [ ] Give the production installer and release-publication scenarios an explicit integration/slow marker and a dedicated full-suite lane. Keep a fast developer pytest command for routine feedback while CI and release validation continue to run the complete coverage.
- [ ] Publish a pytest duration report in CI so new slow tests and file-level runtime changes are visible before they accumulate.
- [ ] Reconsider parallel pytest execution only after mutable application config, SQLite state, logging globals, and extension state are isolated well enough to avoid order-dependent failures.

**Done when:** the documented fast pytest path is materially quicker, the complete suite still covers fresh application factories, production asset output, and release installation, and CI makes future runtime regressions easy to spot.

### Organize script entrypoints and implementation helpers

The `scripts/` directory has 34 tracked files covering operator workflows, test runners, release publication, container construction, generated artifacts, frontend assets, and demo capture. Most still live at the top level, which makes supported commands hard to distinguish from internal helpers.

Keep `scripts/` as the home for executable project tooling, but organize internal files by purpose rather than programming language or whether CI happens to call them. Treat top-level scripts as stable, supported entrypoints and keep commonly documented commands such as `run_playwright.sh`, `run_postgres_tests.sh`, and `run_pytest.sh` at their current paths.

- [ ] Classify each current script as a stable entrypoint or an internal helper. Preserve documented operator and developer commands with their current path or a thin forwarding wrapper; don't create a permanent file-by-file documentation inventory.
- [ ] Introduce purpose-based directories for `operations/`, `release/`, `container/`, `frontend/`, `generate/`, `development/`, and `test-support/`. Keep `hooks/`, and place Playwright server lifecycle helpers under the test-support boundary while retaining `scripts/run_playwright.sh` as the public runner.
- [ ] Move scripts one purpose group at a time without renaming them in the same change. Start with release and container internals, then frontend and generators, followed by development, media-capture, and test-support helpers.
- [ ] Keep backup, restore, and SQLite-to-Postgres migration commands easy for operators to find. If their implementation moves under `operations/`, preserve any documented source-checkout commands with forwarding entrypoints until the documentation and supported command contract deliberately change.
- [ ] Update `.gitlab-ci.yml`, `package.json`, `Dockerfile`, `.dockerignore`, the pre-commit hook, release-evidence collection, project documentation, and tests after each group moves. Check scripts that derive the repository root from `Path.parents[...]`, `dirname`, or relative `../` paths from their new depth.
- [ ] Keep script names action-oriented within each directory: `build_*` creates artifacts, `generate_*` refreshes checked-in output, `check_*` performs static validation, `verify_*` exercises built artifacts, and `run_*` remains a user-facing wrapper.
- [ ] Add focused path and invocation coverage for Docker-only helpers, release jobs, stable wrappers, and generated-artifact commands before removing old paths. Run the full lint, test, container smoke, and release checks after the final cluster moves.

**Done when:** the top level of `scripts/` contains only stable commands and clearly named purpose directories, existing documented command lines still work, internal helpers are easy to locate by responsibility, and local, CI, container-build, and release workflows pass without compatibility shims that no longer serve a supported path.

---

## Feature Enhancements

These are possible future improvements, split by whether they look worth carrying forward.

- **Publish one release image for Linux AMD64 and Linux ARM64.**
  - Start after the current AMD64-only release pipeline has been fully validated. Build each architecture on a native Linux runner, push immutable architecture-specific staging references, verify both, and create the canonical GitLab multi-architecture index only after every gate passes. Promote that complete index to Docker Hub instead of publishing one architecture and later changing the tag.
  - Record the index digest, both platform digests, and both Python base-image digests in the release evidence. Generate SBOM and vulnerability results for each platform, and make signatures, attestations, retry handling, and tag-immutability checks understand the index and its platform images.
  - Pull the canonical index on native AMD64 and ARM64 runners and run the repository-free startup, bundled-tool, capability, durable-restart, architecture-label, and registry-parity checks against the platform image Docker actually selects.
  - Remove the production Compose and installer AMD64 pin, make installation and verification architecture-aware, and confirm required Redis and Postgres images resolve on both supported platforms.
  - Update the support matrix and release documentation to advertise Linux AMD64 and Linux ARM64 only after the published ARM64 path passes consistently. Keep macOS testing as useful development coverage without presenting Docker Desktop as a native production target.
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
- **Headless API and CLI follow-through.**
  - Let scripts and CI start, inspect, cancel, and follow durable workflows through token-authenticated API routes and matching `darklab workflow` commands. Expose saved-run comparison through the same headless surface once its permission, team-scope, and bounded-output contracts are defined.
  - Put the workflow execution event cursor to work for browser refresh or headless replay, or retire it if execution polling remains the supported path.
  - Add `darklab --version` for the installed client. Treat connected-server version and client/server compatibility reporting as a separate decision.
  - Bring the existing API v1 AI assists to the CLI with summary and next-command commands that handle cached, queued, in-progress, disabled, and failed states cleanly.
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

### Run replay / scrubbable event stream
- Turn completed runs into replayable structured event logs, building on the Structured Output Model.
- Support a scrub timeline, bookmarks, per-line comments, and command-by-command playback.
- Keep replay integrated with findings, Atlas entities, summaries, and run comparison rather than treating it as a separate asciinema-style recording.

### Run comparison enhancements — deferred pieces
- Run comparison now covers finding severity changes, discovered hosts, TLS fields, workflow context, and completed-tab launch points. The remaining ideas are:
  - Snapshot/permalink compare, once the compare route can resolve snapshot/permalink ids instead of only live `runs` rows.
  - `Export comparison`, once share/export packages have one unified, stable artifact schema version rather than several independent `schema_version` fields.
  - Unifying the comparison-local URL/status/title parsing (`httpx`/`ffuf`/`gobuster`/`katana`) with the shared tool-aware classifier registry that ports/hosts/tls already use.
  - Date-range filters in the manual compare picker, if day grouping plus `Load More` is not enough for deep history.
  - Broader Playwright coverage for additional edge and mobile layout paths.
  - Focused large/noisy comparison regression coverage if real-world outputs expose performance issues beyond current backend and unit coverage.

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
