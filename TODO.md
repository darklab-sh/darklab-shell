# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Decompose oversized blueprint and core modules](#decompose-oversized-blueprint-and-core-modules)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
  - [Dedicated positional workspace-file value type](#dedicated-positional-workspace-file-value-type)
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
  - [Replace global singletons with injected dependencies](#replace-global-singletons-with-injected-dependencies)
  - [Typed, validated configuration model](#typed-validated-configuration-model)
  - [Right-size project documentation](#right-size-project-documentation)
  - [Unified terminal built-in lifecycle](#unified-terminal-built-in-lifecycle)
  - [Plugin-style helper command registry](#plugin-style-helper-command-registry)
  - [Lightweight Jinja base template](#lightweight-jinja-base-template)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

### Decompose oversized blueprint and core modules

- **Problem:** the largest modules mix routing, business logic, content generation, and (historically) persistence in single files, so review, testing, and change isolation are harder than the feature set warrants.
- **Refreshed inventory (the original numbers were stale).** The data-access-layer and schema-unification work already shrank several named modules as a side effect, and surfaced new large service modules. Current line counts:
  - Still oversized, in scope:
    - `services/commands/registry.py` — 3,755 (untouched by prior work; the single biggest file)
    - `blueprints/run.py` — 3,357 (10 routes but ~93 helper functions; ~1,390 lines of run-lifecycle logic sit before the first route, plus PTY route handlers)
    - `blueprints/projects.py` — 2,786 (67 routes, already delegating to `services/projects/*`; oversized by route *count*, not fat handlers)
    - `blueprints/api_v1.py` — 2,484 (68 routes, down from ~3,080; the same resource-count problem)
    - `blueprints/atlas.py` — 1,459
  - Already effectively resolved by prior work — confirm against the target and close out, do not re-split:
    - `core/database.py` — 1,005 (was ~2,910; the `_migrate_schema` ladder was retired and `_create_schema` moved to `core/migrations/baseline.py`)
    - `blueprints/history.py` — 1,417 (was ~2,580; queries moved to `services/history/queries.py`)
  - New oversized service modules that appeared during the refactors — triage, do not assume all need splitting:
    - `services/api_v1/openapi.py` — 2,597, `core/output_signals.py` — 2,186, `services/atlas/lookup.py` — 2,139, `services/projects/overview.py` — 1,766, `services/workspace/files.py` — 1,740, `core/migrations/baseline.py` — 1,689, `services/pty/service.py` — 1,553, `services/history/queries.py` — 1,428, `services/projects/queries.py` — 1,426, `services/atlas/import_workflow.py` — 1,426
  - Current inventory items that Phase 0 must classify explicitly before work starts, because they are over or near the proposed thresholds:
    - `blueprints/assets.py` — 1,341; decide whether to split static/vendor delivery, `/health`, `/diag`, and operator diagnostics into separate route modules or mark it deferred with a reason
    - `core/process.py` — 1,169; classify as split-target or ratchet-only process-state module
    - `services/metrics/__init__.py` — 983; classify metrics registration/collection shape before deciding whether to split
    - `services/projects/auto_promote.py` — 963; classify as split-target or cohesive service
    - `core/schema_manifest.py` — 899 and `core/database_backend.py` — 845; classify as cohesive infrastructure or split-target
    - `services/commands/builtins_runtime.py` — 830 and `blueprints/teams.py` — 796; ratchet-track even if they stay under the first pass route/service target
- **Why now:** the seams and precedents already exist.
  - The `services/` tree is already the established home for extracted logic, and the data-access work made blueprints thin controllers, so route files mostly need *grouping*, not business-logic surgery.
  - The commands package already demonstrates the target shape: `services/commands/` holds `builtins.py`, `builtins_runtime.py`, `builtins_intel.py`, `builtins_discovery.py`, `builtins_team.py`, `builtins_workspace.py`, `builtins_notify.py`, and `registry_loader.py` — `registry.py` is simply the one file that never got split.
  - `tests/py/test_architecture.py` already exists as the enforcement home for a size ratchet.
- **Scope:**
  - In scope:
    - split the still-oversized modules by **responsibility**, using the split strategy that fits each module *type* (below), so no route module exceeds ~800 lines and no service module owns more than one domain concern
    - a **size ratchet** in `tests/py/test_architecture.py` seeded from the current per-file line counts, failing when any tracked module grows past its baseline, so decomposition sticks and new bloat is caught
    - objective thresholds for the ratchet: route modules target <800 raw lines; service/core modules over ~1,200 raw lines must be classified as split-target or cohesive-artifact; service/core modules over ~800 raw lines are ratchet-tracked; cohesive artifacts get a short justification in the ratchet map
    - a documented target and the split-by-type policy in `ARCHITECTURE.md`/`CONTRIBUTING.md`
  - Out of scope:
    - files that are legitimately one cohesive artifact where splitting hurts readability: `services/api_v1/openapi.py` (a single OpenAPI spec dict — data, not logic) and `core/migrations/baseline.py` (the generated-from-SQLite schema baseline). Keep these as ratchet-tracked "do not grow" entries rather than split targets, unless a natural seam emerges
    - behavior changes of any kind — every split is a pure move-and-reimport refactor
    - re-splitting `core/database.py` and `history.py`, which prior work already brought to/near target — only confirm and add them to the ratchet
    - moving business logic that the data-access item already relocated; this item is about file organization, not another persistence pass
- **Split strategy by module type** (line count is the trigger, responsibility is the cut):
  - **Concern-heavy single files → sibling modules by concern.** `registry.py` mixes FAQ content generation (`_builtin_faq`, `render_faq_markup`, `_faq_inline_markup`), registry file load/normalize/merge (`_load_commands_registry_file`, the `_normalize_*` helpers, `_merge_command_registry_entries`), the frozen-dict/list machinery, registry build/access, and `validate_command`. Split into `registry_faq.py`, `registry_normalize.py` (or fold into the existing `registry_loader.py`), and `registry_validate.py`, leaving `registry.py` as the assembled registry surface. `output_signals.py`, `atlas/lookup.py`, `projects/overview.py`, and `workspace/files.py` get the same by-sub-responsibility treatment.
  - **Business-logic-in-route files → services.** `run.py`'s ~1,390 lines of pre-route run-lifecycle/finalization helpers move into `services/runs/` (which already holds `persistence.py`, `start.py`, and finalization-adjacent helpers), and its five PTY routes either move to a `blueprints/pty.py` or delegate further into `services/pty/service.py`, leaving `run.py` a thin route file. Predeclare the target service seams in Phase 0 so this does not create a new catch-all module: likely `services/runs/lifecycle.py` or `execution.py` for subprocess lifecycle helpers, `services/runs/finalization.py` for completion/finding/artifact/project hooks, and route-only PTY handlers in a blueprint while transport/session logic stays in `services/pty`.
  - **Route-count-heavy blueprints → split by resource group.** `projects.py`, `api_v1.py`, and `atlas.py` are already thin per route (~36–41 lines/route) but hold too many routes in one file. Split each into resource-group modules that register onto the same blueprint (for example Projects CRUD vs targets vs findings vs packages vs reports vs monitoring; API v1 by resource family) so the blueprint object stays one registration but the routes live in cohesive files.
    - Registration contract: the existing public blueprint symbol stays in the parent module (`projects_bp`, `api_v1_bp`, `atlas_bp`, and so on); resource-group submodules import that blueprint object and register routes when imported; the parent imports those submodules exactly once for route registration; `app.create_app()` continues importing only the parent blueprint symbol. Route-registration side effects are allowed inside blueprint assembly, while runtime side effects remain forbidden at import.
- **Phase 0 — inventory, targets, and ratchet:**
  - Regenerate the exact per-file line-count inventory (the numbers above will drift); classify each module as split-target, already-resolved, or legitimately-cohesive.
  - Land the ratchet in `tests/py/test_architecture.py` first: a per-file baseline map of the tracked modules that fails on any increase. Use raw line counts consistently, seed from current counts so it can only shrink, and include new split-package files with their own max thresholds so bloat cannot move sideways. Cohesive artifacts get "no growth beyond baseline"; active split-targets get temporary baselines during the phase and final max thresholds at close-out.
  - Decide the split boundaries per module with the strategy above, and record the target file layout so splits are reviewable as move-only diffs. Include an explicit keep/split/defer decision for `blueprints/assets.py` rather than leaving it implicit.
- **Phase 1 — `registry.py` (highest leverage, no route risk):**
  - Extract FAQ generation, normalize/merge, and validation into sibling modules per the strategy; keep public imports stable (re-export from `registry.py` or update call sites). Drop `registry.py`'s ratchet baseline as it clears.
- **Phase 2 — `run.py`:**
  - Move the run-lifecycle/finalization helpers into `services/runs/`, and separate the PTY routes. `run.py` becomes a thin route file under ~800 lines. This is the riskiest blueprint split (SSE streaming, PTY transport, run finalization), so it gets the deepest regression attention.
- **Phase 3 — resource-group blueprint splits:**
  - Split `projects.py`, then `api_v1.py`, then `atlas.py` into resource-group modules registering onto the existing blueprint. One blueprint per phase-step, full suite green after each, no route path or response change.
- **Phase 4 — remaining oversized service modules:**
  - Split `output_signals.py`, `atlas/lookup.py`, `projects/overview.py`, `workspace/files.py`, `pty/service.py`, and the `*/queries.py` files by sub-responsibility where a clean seam exists; leave the cohesive-artifact files (`openapi.py`, `baseline.py`) as ratchet-only.
- **Phase 5 — tests-follow-decomposition and close-out:**
  - Where the monolithic test files (notably `tests/py/test_backend_modules.py`) now span multiple new module boundaries, split the corresponding test classes into files that mirror the modules decomposed by this plan so failures localize. This is useful but not required for every unrelated test area; do not turn decomposition close-out into a full test-suite reorganization. Keep `tests/README.md` counts and appendix entries current for any new test files.
  - Empty the ratchet's shrink allowance to a hard "no tracked module over its target," update `ARCHITECTURE.md`/`CONTRIBUTING.md` with the split-by-type policy, and record the change in `CHANGELOG.md`.
- **Test criteria:**
  - The full suite passes after every phase — every split is behavior-preserving, so `test_routes.py`, `test_api_v1.py`, the container smoke test, and the blueprint/service unit tests are the primary regression net; route paths, response shapes, and status codes are unchanged.
  - The size ratchet in `tests/py/test_architecture.py` passes at every phase with a monotonically shrinking per-file baseline, and enforces the final targets at close-out.
  - Import-stability check: public symbols that moved keep working for their callers (either re-exported from the original module or all call sites updated), verified by the suite importing without error and by a grep/AST check for stale imports of moved symbols.
  - Route registration check: the app's route map is unchanged after each blueprint split, except for internal endpoint function names if those are intentionally accepted and documented. Prefer a route-map snapshot/comparison test if no equivalent guard already exists.
  - Documentation check: run `tests/py/test_docs.py` after every phase because new modules must be reflected in README project structure and any new test files must be reflected in the test appendix.
  - Architecture guard check: keep the direct-database-access blueprint guard recursive over any new blueprint subpackages, so moving route handlers into grouped modules does not weaken the persistence boundary.
  - The OpenAPI snapshot test still matches (`api_v1.py`/`openapi.py` route changes must not alter the generated `docs/api-v1-openapi.json`).
- **Success criteria:**
  - No route blueprint exceeds ~800 lines and no service module owns more than one domain concern; the split-target modules are decomposed and the already-resolved and cohesive-artifact modules are tracked by the ratchet.
  - The size ratchet fails the build when a tracked module grows past its target, so the decomposition cannot silently regress.
  - Every split was behavior-preserving: route paths, response shapes, and the OpenAPI snapshot are unchanged.
  - The split-by-type policy is documented in `ARCHITECTURE.md`/`CONTRIBUTING.md`, and the change is recorded in `CHANGELOG.md`.

## Known Issues

No open Known Issues are currently tracked.

---

## Technical Debt

### Dedicated positional workspace-file value type

- The `mv` and `file move` builtins declare their session-path argument as `value_type: target` under `feature_required: workspace`. The autocomplete layer reinterprets that as "list workspace file/folder entries" (via the `target` handler's `sourceHints`) and suppresses scan-target/recent injection for any workspace-required spec, so the behavior is correct. But `value_type: target` on a file-move command is misleading in the grammar, and these two specs are the only place the overload exists — file *flags* already have a clean dedicated mechanism (`workspace_flags` → `workspace_file_flags`).
- The clean form would be a first-class positional workspace-file value type (for example `value_type: workspace_file`) whose handler sources workspace entries and injects nothing, then migrating `mv` and `file move` off `value_type: target`. Note this is a real refactor, not a rename: the only mechanism that currently lists top-level session entries for a positional arg is the `target` handler's `sourceHints`, so the entry-listing behavior has to be factored into the new handler (plus loader plumbing and a guard test). `workspace_path_arg_kinds` does not cover this — it only drills into a path once a `/` is typed.
- Low priority: the current behavior is correct and drift-proofed at the suggestion chokepoint, and the overload is documented inline in `builtin_autocomplete.yaml` and the `target` handler. The one case that would justify the refactor is a future workspace command that needs both a session-file argument and a real scan-target argument, which the current spec-level suppression would get wrong.

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

### Replace global singletons with injected dependencies
- Problem: `redis_client`, `limiter`, and `CFG` are module-level globals imported throughout the app. This is workable but drives the re-export/compat gymnastics in `app.py` and makes isolated testing awkward, since collaborators are bound at import time rather than passed in.
- Approach:
  - Pass dependencies explicitly (or attach them to an app-scoped registry / Flask extensions pattern) instead of importing module globals.
  - Sequence this after the application factory lands, since the factory provides the natural place to construct and wire these dependencies once per app.

### Typed, validated configuration model
- Problem: configuration is effectively its own subsystem with no schema. `config.py` is ~1,190 lines feeding on large YAML inputs (`commands.yaml` ~184K, `config.yaml` ~42K) plus a ~3,760-line command `registry.py`, and it is consumed through untyped `CFG.get(...)` access scattered across the code. Misconfiguration surfaces late and diffusely rather than at boot.
- Approach:
  - Introduce a typed, validated settings model (for example pydantic-settings or equivalent) that fails fast at startup with a clear message when config is missing or malformed.
  - Replace ad-hoc `CFG.get(...)` reads with attribute access on the validated model so config keys are discoverable and type-checked.

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
