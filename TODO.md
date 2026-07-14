# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Repository-free production installation](#repository-free-production-installation)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Feature Enhancements](#feature-enhancements)
- [Research](#research)
- [Ideas](#ideas)
  - [Run replay / scrubbable event stream](#run-replay--scrubbable-event-stream)
  - [Run comparison enhancements — deferred pieces](#run-comparison-enhancements--deferred-pieces)
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

### Repository-free production installation

**Outcome:** Operators can install and run a released darklab_shell stack from a small, versioned deployment directory without cloning the source repository or building the image locally. Developers keep the current source-mounted workflow. CI publishes the canonical self-contained image to the GitLab Container Registry first, then promotes that exact image to Docker Hub for the public, user-facing pull path used by production deployments.

#### Delivery milestones

Each milestone is independently releasable and has its own exit criteria. Milestones 2 through 4 improve the initial install path, but they do not block Milestone 1 unless a task is explicitly marked as a first-public-image gate.

##### Milestone 1: Repository-free install

- [ ] Run the protected `v2.6.0` tag pipeline on a native Linux AMD64 runner. Confirm the repository-free image smoke test, exact-tag immutability/retry behavior, license gate, installer payload, and Docker Hub promotion all complete.
- [ ] Confirm anonymous access to the GitLab image, Docker Hub mirror, setup files, checksums, and notices. Verify both registries report the same digest and a clean Docker host reaches a healthy app from the installed directory.
- [ ] Record the pipeline's compressed transfer size, unpacked image size, layer composition, and representative cold-pull time. Add those measured expectations to the operator docs and decide whether SecLists or another tool group justifies a later slim image.

**Milestone 1 exit:** A clean Docker host can verify the installer, create a deployment directory, pull the exact public Docker Hub image tag, confirm it matches the canonical GitLab image digest, and reach a healthy app without Git, Python, Node, a local build, or a source checkout. The existing development stack and sibling `config.local.yaml` behavior still work.

##### Milestone 2: Complete external overlay model

- [ ] Introduce the shared shipped/local config-path resolver and move every supported YAML and text overlay consumer to it without changing that surface's merge, replace, reload, validation, or fallback semantics.
- [ ] Add the remaining safe, comment-only `*.local.yaml` placeholders and update diagnostics, cache signatures, logging, docs, and regression coverage for the complete overlay inventory.
- [ ] Decide and document how themes, text replacements, package presets, report templates, tour content, and wordlists participate instead of implying unsupported filenames work.

**Milestone 2 exit:** Every documented local override can live under mounted `./conf`, edits invalidate the correct caches and reload as documented, and an empty local directory leaves all image-bundled defaults visible.

##### Milestone 3: Managed deployment lifecycle

- [ ] Replace the minimal per-file installer payload with the deterministic deployment archive, release manifest, managed-file checksums, exact-release upgrade support, migration help, and safe removal behavior.
- [ ] Package repository-free backup and restore operations behind Docker/Compose-only commands, then make automated upgrades create and verify a pre-upgrade backup or refuse to continue.
- [ ] Add two-release upgrade tests that prove operator config, `.env`, data, workspaces, and backups survive while managed files and the image reference advance atomically.

**Milestone 3 exit:** Install, upgrade, backup, restore, migration from a clone-backed deployment, conflict handling, and removal all work without a repository checkout and clearly separate release-managed files from operator-owned data.

##### Milestone 4: Supply-chain and compatibility hardening

- [ ] Make bundle generation fully reproducible, pin or account for moving build inputs, publish SBOM and provenance, scan the image, sign the image digest and checksum manifest, and document verification against an out-of-band trusted identity.
- [ ] Audit every architecture-specific download before adding `linux/arm64`, and add an explicit Podman/rootless/SELinux test lane before claiming those runtimes as supported.
- [ ] Revisit image composition using the measured pull-size data. Add a slim or separately packaged wordlist/tool variant only when its maintenance and UX costs are justified.

**Milestone 4 exit:** Published artifacts are traceable and independently verifiable, every advertised architecture/runtime has automated coverage, and image-size tradeoffs are documented with measured data.

#### Remaining implementation detail

##### Milestone 2: external overlays

- [ ] Add one resolver for immutable image defaults and mounted operator overrides, including theme subdirectories and safe filename handling.
- [ ] Move the command registry, FAQ, welcome content, workflows, banners, hints, and themes to the resolver without changing their merge, replace, reload, validation, or fallback behavior.
- [ ] Make cache invalidation include every base and local file that can change a loader's result, especially `commands.yaml` and `commands.local.yaml`.
- [ ] Inventory the rest of `app/conf/` and decide explicitly how package presets, report templates, tour content, text replacements, and wordlists participate.
- [ ] Add harmless comment-only placeholders only for supported overlays. Preserve operator files and use non-active examples where an empty file would replace shipped content.
- [ ] Expand startup diagnostics, logs, documentation, and regression coverage to the complete supported overlay inventory without exposing values or secrets.

##### Milestone 3: managed lifecycle

- [ ] Replace the per-file installer payload with a deterministic, checksummed deployment archive in GitLab's Generic Package Registry.
- [ ] Add managed install and upgrade tooling that validates the current manifest, preserves operator files, creates and verifies a backup, and advances managed files atomically.
- [ ] Refuse unsafe downgrades, explain that changing an image tag does not reverse database migrations, and provide migration and removal flows for repository-backed deployments.
- [ ] Package SQLite and Postgres backup and restore operations behind Docker/Compose-only commands while preserving secret-key continuity, workspaces, checksums, retention, and cron-friendly output.
- [ ] Add two-release install, upgrade, conflict, backup, restore, and migration tests that run only from generated release artifacts.
- [ ] Update operator docs and the changelog when the managed lifecycle ships, then remove the completed Milestone 3 tasks from this plan.

##### Milestone 4: supply chain and compatibility

- [ ] Make release archives reproducible and account for every moving base image, tool download, source checkout, and build input.
- [ ] Publish an SBOM and provenance, scan the image under a documented policy, and sign the image digest and checksum manifest against an out-of-band trusted identity.
- [ ] Audit and parameterize architecture-specific downloads before publishing `linux/arm64`.
- [ ] Add SELinux-enforcing Docker and rootless Podman compatibility lanes before advertising those host models as supported.
- [ ] Use measured image-size and pull-time data to decide whether a slim or separately packaged wordlist/tool image is worth maintaining.
- [ ] Update verification docs and the changelog when the hardening work ships, then remove the completed Milestone 4 tasks and this plan.

#### End-state acceptance criteria

- [ ] All documented local overlays work from mounted `./conf`, preserve shipped defaults, invalidate the right caches, and reload as documented.
- [ ] Install, upgrade, backup, restore, migration, rollback guidance, and removal work without a repository checkout and distinguish managed files from operator-owned content.
- [ ] GitLab images, Docker Hub mirrors, packages, checksums, SBOM/provenance, signatures, and release links are anonymously accessible and independently verifiable as documented.
- [ ] Every advertised architecture and container runtime has automated compatibility coverage.

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
