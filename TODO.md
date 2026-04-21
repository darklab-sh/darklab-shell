# TODO

This file tracks open work items, known issues, and product ideas for darklab shell. Open TODOs, known issues, and technical debt are confirmed items. Ideas are speculative — not committed or planned.

---

## Table of Contents

- [Open TODOs](#open-todos)
- [Research](#research)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Ideas](#ideas)
  - [Near-term](#near-term)
  - [Later](#later)
  - [Mobile](#mobile)
  - [Safety and Policy](#safety-and-policy)
  - [Content and Guidance](#content-and-guidance)
  - [Architecture](#architecture)

---

## Open TODOs

- **HUD clock UTC / local-time toggle** — the HUD `CLOCK` pill always renders UTC. Add an Options preference that toggles between UTC and the browser's local timezone, persist the choice in the existing options cookie set, and make the pill label or tooltip reflect which mode is active.

- **Capture/demo parity guardrails** — add a lightweight guardrail for the Playwright demo and UI-capture pipelines so the intended desktop/mobile viewport classes, seeded history shape, and production-like health state do not silently drift. At minimum, keep viewport/config parity explicit and fail fast when capture/demo assumptions diverge.

- **History/session seed fixtures for visual flows** — formalise the seeded demo/capture history dataset as a named fixture so screenshot packs, demo recordings, and documentation screenshots stay stable across releases instead of depending on ad hoc generated history.

- **History drawer/sheet pagination instead of a hard cap** — the configured history limit should act as a page size, not a global ceiling, because the full run history is already stored in SQLite and searchable via the history filters and reverse-i-search. Add pagination controls to the desktop history drawer and mobile history sheet, and show a count summary at the top such as `N of Total shown` so it is clear the current view is paginated rather than truncated.

- **CI Docker images covered by the version-check script** — `scripts/check_versions.sh` (or the equivalent vendor / dependency check) should also pin and verify the CI base images so the runner environments do not drift silently from the production image. Add the CI images to the same source-of-truth list and fail the check when they fall behind.

- **Chain multiple pipe helpers in a single command** — today the shell accepts a single pipe stage (e.g. `ping -c 4 darklab.sh | grep 'bytes from'`) but rejects longer pipelines. Allow strung-together helpers (e.g. `ping -c 4 darklab.sh | grep 'bytes from' | wc -l`) so common post-processing workflows work without leaving the shell. Each stage must still be individually allowlisted, metacharacter-blocked, and policy-checked; apply the same pipe-helper rules uniformly across every stage rather than loosening guards for the additional segments.

---

## Research

- **Surface starred state in the desktop rail's Recent section** — the rail's Recent list lost the starred-first ordering and the star indicator that the older chip strip carried. Research whether the right fix is simply restoring starred-first ordering plus a visible marker, or whether the rail needs a broader information-density pass. Verify the same change does not regress the mobile recents sheet (which already shows star state per row).

- **Rail information density tuning** — reassess how much metadata belongs in the desktop rail's Recent and Workflows entries now that the rail owns more of the shell chrome. Explore whether star state, recency, status, or lightweight badges should be visible without making the rail noisy.

---

## Known Issues

- **Desktop rail Workflows entries styled differently from Recent entries** — in the desktop rail the Workflows section's list items blend into the Workflows header visually, while the Recent section above it uses a clearer, more readable text treatment. The actual workflow entries should match the Recent command entries' text styling so the two rail sections look consistent and the Workflows list is as scannable as the Recent list.

- **Mobile run timer duplicated in header status pill and top of output window** — on mobile, when a command is running there are two live timers visible at the same time: one in the header status pill and one at the top of the output window. The header pill is the canonical location; remove the duplicated timer at the top of the output window so there is a single authoritative run-timer surface on mobile.

- **Shortcuts overlay close button placement is inconsistent** — the keyboard-shortcuts overlay `X` sits beside the modal title instead of being anchored in the expected top-right corner, which makes the close affordance feel misaligned relative to the rest of the shell overlays.

- **Mobile sheet close affordance is redundant or unclear** — mobile sheets currently include an `X` close button even though the sheet pattern already has a grab handle, supports drag-down dismissal, and closes on backdrop tap. Reassess whether the extra `X` is needed at all, or whether it is just adding visual noise and competing close metaphors.

---

## Technical Debt

- **CI/runtime source-of-truth drift** — production, CI, and version-checking logic currently need to stay aligned across multiple files. Consolidate Python base-image/runtime declarations so the production image, CI jobs, and version-check script cannot silently diverge.

- **Duplicated page bootstrap in Jinja templates** — `index.html`, `permalink_base.html`, and `diag.html` now share enough `<head>` and theme/bootstrap wiring that the duplication is real maintenance overhead. Factor the common bootstrap into a lightweight shared base before a fourth page type makes the drift worse.

- **Cross-module UI event flow is still coupled through wrappers and observers** — `shell_chrome.js` and `mobile_chrome.js` currently mirror shared UI state by wrapping globals (`renderHistory`, `renderRailWorkflows`, `closeWorkflows`, `refreshHistoryPanel`, `setTabStatus`), and by using three `MutationObserver`s in `mobile_chrome.js` (`:107` on the status pill `class` attr, `:113` on the run-timer `characterData`, `:699` on the body `class` list) to mirror state changes they have no other way to hear about. Replace those ad hoc integrations with a small UI event bus or equivalent explicit publish/subscribe layer so cross-module synchronization does not depend on monkey-patching exported functions.

### CHANGELOG.md v1.5 Regrouping Plan

- **Goal** — improve scanability of the very large `v1.5` section by grouping related entries under a small number of explicit sub-sections, without dropping detail or rewriting the underlying entry content.

- **Why this is needed**
  - `v1.5` currently reads as one long flat stream, even when 4-10 adjacent entries are clearly part of the same initiative.
  - The `v1.5` UI work is really one release-level initiative with three connected parts: the desktop UI refactor, the mobile UI refactor, and the later polish/consistency pass that addressed issues revealed by both refactors. As separate flat bullets, that story is fragmented and visually competes with unrelated fixes like `session-token revoke` or reverse-i-search regressions.
  - Several other repeated themes also deserve grouping so readers can skim by initiative instead of reading every bullet in order.

- **Constraints**
  - Keep the existing T1/T2/T7 structures from `DOCS_STANDARDS.md`; this is regrouping work, not compression work.
  - Do not reduce technical detail inside the entries.
  - Do not merge distinct entries into one giant umbrella unless the before/after/tests story is genuinely shared.
  - Preserve release chronology inside each new group where it still helps tell the implementation story.

#### Phase 1 — Add sub-section structure to `v1.5`

- Add lightweight sub-heads inside `## [1.5]` so the current `### Added / Changed / Fixed / Removed` blocks are not the only navigation layer.
- Use a small number of stable group labels rather than many tiny buckets.
- Preferred shape:
  - `UI Overhaul`
  - `Keyboard Shortcuts and Discoverability`
  - `Visual QA, Demo, and Capture Pipeline`
  - `Session Identity and History`
  - `Search, Autocomplete, and Prompt UX`
  - `Mobile Shell and Sheet Behavior`
  - `Testing, CI, and Smoke Infrastructure`
  - `Documentation and Structure`

#### Phase 2 — Regroup the full `v1.5` UI initiative as one umbrella

- Pull all three UI efforts under one explicit parent grouping instead of treating them as separate top-level initiatives mixed through the full `### Added` / `### Changed` / `### Fixed` stream.
- Preferred umbrella shape:
  - `Desktop UI Refactor`
  - `Mobile UI Refactor`
  - `UI Polish and Consistency`
- The guiding rule is release narrative over exact commit chronology: entries should live where they best explain the user-facing `v1.5` UI story, even if that means some unrelated smaller fixes sit above or below the umbrella section.
- Within the umbrella:
  - keep desktop-refactor entries together
  - keep mobile-refactor entries together
  - keep the later polish / consistency / contract-hardening items together
- Do not use milestone, phase, or branch-language headings in the changelog structure. Group by what changed from the reader’s perspective, not by how the work was implemented.
- Keep the individual entries intact; this is grouping work, not content merge or chronology rewrite.

#### Phase 3 — Regroup the keyboard/discoverability work

- Group the three related `### Added` entries:
  - `Alt+/ FAQ shortcut plus tooltip audit`
  - `Desktop chrome keyboard shortcuts`
  - `Dedicated keyboard-shortcuts overlay with a single source of truth`
- Present them as one `Keyboard Shortcuts and Discoverability` subsection with the three entries underneath.
- Keep the later shortcut-reference cleanup/grouping entries in the same broad area if they remain in `### Changed`.

#### Phase 4 — Regroup the capture/demo/visual-review work

- Group these entries under a `Visual QA, Demo, and Capture Pipeline` subsection:
  - `UI screenshot capture pipeline for design review, theming, and visual QA`
  - Milestone 5 Phase 5 item 1 capture-scene audit
  - `Demo recording viewports bumped to larger, more modern screen sizes`
  - any adjacent capture/demo-only fixes that are really pipeline maintenance rather than product behavior
- Treat the capture pipeline as one evolving initiative rather than separate isolated bullets.

#### Phase 5 — Regroup the session/history identity work

- Create one `Session Identity and History` subsection for the long cluster that currently spans:
  - persistent session tokens
  - server-side starred commands
  - history drawer filtering/full-text search
  - reconnect active runs after reload
  - session restore for tabs and drafts
  - later `session-token` fixes and migration-count fixes
  - history star sync / bulk-clear sync / stale star fallback fixes
- Keep identity, migration, stars, history persistence, and restore continuity together so readers can follow the session-model story in one place.

#### Phase 6 — Regroup the search/autocomplete/prompt UX work

- Create one `Search, Autocomplete, and Prompt UX` subsection spanning:
  - more bash-like tab completion
  - context-aware autocomplete
  - pipe-stage autocomplete
  - search/full-text output search
  - reverse-i-search fixes
  - search-bar visibility and search-helper regressions
  - composer/prompt-state-drive refactor bullets where they are primarily prompt UX rather than architecture
- Keep all hist-search, autocomplete, and prompt-entry behavior close together instead of scattering them across Added/Fixed/Changed with unrelated infra entries between them.

#### Phase 7 — Regroup the mobile-shell behavior work

- Create one `Mobile Shell and Sheet Behavior` subsection for the repeated mobile-only cluster:
  - mobile shell rebuild and shell polish
  - mobile keyboard/helper/composer fixes
  - mobile bottom-sheet / drag-handle unification
  - mobile search close affordance
  - mobile output-wrap, timer, follow-tail, and running-indicator-adjacent fixes
- Keep purely mobile UI behavior separate from the broader desktop/UI-review milestone group so the changelog is readable by platform concern.

#### Phase 8 — Regroup test/CI/infrastructure maintenance

- Create one `Testing, CI, and Smoke Infrastructure` subsection that collects:
  - JavaScript testing framework addition
  - dependency/version check items
  - CI jobs for dependency drift and container smoke tests
  - Container Smoke Test DinD, corpus, timeout, resume, and rate-limit bypass changes
  - test-only helpers and e2e flake fixes that are not user-facing product changes
- The goal is to stop these from fragmenting the product-facing changelog narrative.

#### Phase 9 — Regroup documentation/meta work

- Create one `Documentation and Structure` subsection that collects:
  - Documentation Structure Refactor
  - `DOCS_STANDARDS.md` adoption
  - doc map / standards / structure references
  - changelog-only or docs-only cleanup entries that are currently mixed with product changes
- Keep pure documentation work visible, but not interleaved with runtime UX features.

#### Phase 10 — Final consistency pass

- Re-check that each grouped subsection is still internally coherent and not just “things that happened nearby.”
- Avoid duplicating entries across groups; pick the primary narrative home for each item.
- Prefer a few strong groupings over exhaustive taxonomy.
- Accept that strict commit order may be softened inside the `UI Overhaul` umbrella when that produces a clearer release narrative; do not force unrelated small fixes into the middle of the UI story just to preserve chronology.
- Re-read `v1.5` top-to-bottom after regrouping to confirm:
  - the desktop refactor, mobile refactor, and follow-through work now read as one coherent `v1.5` UI initiative
  - the session/history story is easier to follow
  - capture/demo/test-infra work no longer interrupts product-facing UX narratives
  - section headings improve navigation instead of adding noise

### ARCHITECTURE.md Restructure Plan

- **Goal** — reorganize `ARCHITECTURE.md` around clearer conceptual clusters without reducing technical depth, flattening request-flow narratives, or breaking useful reference sections that already work well.

- **Gate** — after every phase, `python -m pytest tests/py/test_docs.py -q` (21/21) and `npm run lint:md` stay green. Cross-doc references from `README.md`, `FEATURES.md`, `DECISIONS.md`, and `tests/README.md` are re-checked before a phase is marked complete.

- **Constraints** — preservation contract honored across all phases:
  - keep the current level of technical detail
  - do not flatten request-flow narratives into bullets where sequence matters
  - do not remove existing diagrams unless replaced with something better
  - preserve anchors and cross-links where practical, and update `README.md` / `FEATURES.md` / `DECISIONS.md` / `tests/README.md` when an anchor they reference must change
  - avoid turning the document into a giant taxonomy — regroup only where it improves navigation

#### Phase 1 — Structural framing and move map

- Preserve the current strong anchors:
  - `HTTP Route Inventory`
  - `Primary Request Flows`
  - the expanded `Frontend Architecture` cluster
  - `Logging`
  - `Theme System`
  - `Test Suite`
- Draft the new top-level order:
  - `System Overview`
  - `System Structure`
  - `Primary Request Flows`
  - `HTTP Route Inventory`
  - `Front-end Architecture`
  - `Back-end Architecture`
  - `Run Lifecycle`
  - `State And Persistence`
  - `Observability And Diagnostics`
  - `Security Model`
  - `Configuration Surfaces`
  - `Test Suite`
  - `Production Deployment Notes`
  - `Related Docs`
- Map current sections into this new order before moving prose so the restructure is intentional rather than piecemeal.
- **Concrete move map** — use these target homes when migrating prose in Phases 2–8 so individual moves stay consistent with the whole restructure:
  - **Into Front-end Architecture** — `Shell Prompt Model`, `Tab State`, `Live Output Rendering`, `Output Prefixes: Line Numbers And Timestamps`, `Welcome Bootstrap Flow`, `Input State Machines`, and front-end/browser-state portions of `System Overview`.
  - **Into Back-end Architecture** — the Python backend dependency graph currently under `Persistence Model`, plus backend composition explanations currently implied across overview / persistence / config sections.
  - **Into Run Lifecycle** — `Validation And Network Guards`, `Command Auto-Rewrites`, `The KILLED Race Condition`, and run/kill execution details now spread across request flow, output rendering, and security sections.
  - **Into State And Persistence** — `Persistence Model`, `Session Identity` (or most of it), the `/history/active` reload continuity explanation, and the browser `sessionStorage` restore explanation.
  - **Into Observability And Diagnostics** — `Logging`, the operational meaning of `/health`, `/status`, `/diag`, and the deployment/logging transport relationship currently noted in deployment notes.
  - **Keep in place, improve cross-links** — `HTTP Route Inventory`, `Primary Request Flows`, `Theme System`, `Test Suite`, `Production Deployment Notes`.

#### Phase 2 — System Structure cluster

- Create a parent `System Structure` cluster for the document’s stable structural views.
- Move or regroup:
  - `Logical Runtime Layers`
  - `Runtime Topology`
  - the backend dependency graph currently embedded under `Persistence Model`
- Add a short framing paragraph explaining that this cluster shows the stable system boundaries before the doc dives into runtime details.
- Keep existing diagrams unless a better replacement is introduced.

#### Phase 3 — Front-end Architecture consolidation

- Make the front-end section the explicit home for all browser-runtime details.
- Keep or regroup:
  - current `Frontend Composition`
  - current `Frontend Architecture`
  - browser-owned state details now described in `System Overview`
  - `Shell Prompt Model`
  - `Tab State`
  - `Input State Machines`
  - `Welcome Bootstrap Flow`
  - mobile shell runtime details
  - UI interaction helper layer details
  - export rendering architecture
- Break the cluster into clearer sub-blocks such as:
  - `Frontend Composition`
  - `Browser State Model`
  - `Prompt And Composer Runtime`
  - `Input Modes And Dropdown State Machines`
  - `Mobile Shell Runtime`
  - `UI Interaction Helper Layer`
  - `Export Rendering`
- Keep persistence tables, server orchestration, and deployment/runtime container concerns out of this cluster except where a cross-link is necessary.

#### Phase 4 — Explicit Back-end Architecture section

- Add a centralized `Back-end Architecture` section that explains the Python/runtime side as one coherent system.
- Cover:
  - backend module boundaries
  - Flask/Gunicorn role
  - HTTP layer responsibilities
  - command and run orchestration
  - Redis role
  - SQLite role
  - artifact storage role
  - config-loading boundary
  - limiter/logging/request-hook integration points
- Consider sub-blocks such as:
  - `Backend Composition`
  - `HTTP Layer`
  - `Command And Run Orchestration`
  - `Shared Infrastructure`
  - `Worker Coordination`
  - `Persistence And Artifact Services`
- Summarize here, then cross-link to deeper persistence/logging/route sections rather than duplicating all detail inline.

#### Phase 5 — Run Lifecycle section

- Create a dedicated `Run Lifecycle` section so readers can follow one coherent run story without jumping around the doc.
- Pull together:
  - `/run` request flow
  - validation and network guards
  - command auto-rewrites
  - subprocess launch
  - SSE streaming
  - output batching and follow-state behavior
  - kill flow
  - killed-state race handling
  - persistence on completion
- Use sub-blocks such as:
  - `Validation And Rewrites`
  - `Spawn And Stream`
  - `Live Output And Follow State`
  - `Kill Flow`
  - `Persistence On Completion`
- Keep this section prose-first where sequence matters.

#### Phase 6 — State And Persistence cluster

- Create a broader `State And Persistence` section for state location, durability, and reload continuity concerns.
- Group:
  - SQLite tables and artifact files
  - browser `sessionStorage` restore data
  - session identity model
  - active-run metadata for reload continuity
  - distinction between browser-owned idle state and server-owned active-run state
- Consider sub-blocks such as:
  - `Durable Server State`
  - `Browser-Owned Session State`
  - `Session Identity`
  - `Reload Continuity`
- Move or cross-link current material from `Persistence Model`, `Session Identity`, `Tab State`, and `/history/active`-related explanations.

#### Phase 7 — Observability And Diagnostics cluster

- Create a single `Observability And Diagnostics` cluster so operator-facing runtime visibility reads as one coherent story.
- Group:
  - `Logging`
  - health/status/diag surfaces
  - operator-facing diagnostics behavior
  - deployment notes that are specifically about log transport or observability wiring
- Keep the log-event inventory intact, but place it under a parent framing section that ties it to `/health`, `/status`, and `/diag`.
- Add tighter cross-links between logging output, health routes, and diagnostics surfaces.

#### Phase 8 — Security and configuration regrouping

- Reframe `Runtime Security Model` as a broader `Security Model` cluster, preserving:
  - user separation
  - validation and network guards
  - command auto-rewrites where they are genuinely part of the trust boundary
  - cross-user signalling and multi-worker kill
  - `nmap` capability model
- Create a `Configuration Surfaces` cluster for:
  - `Config Loading`
  - `Theme System`
  - browser-facing normalized config payload and theme injection boundaries where relevant
- Make the relationship between backend config loading, theme resolution, and browser bootstrap more explicit without duplicating the deeper theme-authoring detail from `THEME.md`.

#### Phase 9 — Final polish, anchors, and cross-links

- Preserve or intentionally update anchors and table-of-contents entries after the regrouping.
- Re-check all cross-doc references from `README.md`, `FEATURES.md`, `DECISIONS.md`, `tests/README.md`, and any git-doc notes that link into `ARCHITECTURE.md`.
- Ensure route inventory, request-flow narratives, and reference tables remain intact where they already work well.
- Do a final pass for sections that still feel like scattered conceptual siblings and either regroup them or add explicit cross-links.

#### Success criteria

The restructure is successful if:

- a contributor can find browser-runtime architecture in one obvious place
- a contributor can find backend/runtime architecture in one obvious place
- the run lifecycle can be read without jumping across half the document
- state, persistence, and reload continuity read as one coherent model
- logging, status, health, and diagnostics read as one observability story
- the document remains as detailed as it is today, just easier to navigate
- the doc gate (`tests/py/test_docs.py`, 21/21) and `npm run lint:md` stay green, and cross-doc references from `README.md`, `FEATURES.md`, `DECISIONS.md`, and `tests/README.md` still resolve

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Priority order

Ranked by user benefit weighted against implementation complexity. Benefit and complexity use a three-point scale (H / M / L). Items marked ⬡ are foundational — they unlock multiple later features and should be designed before the features that depend on them are built.

**Tier 1 — Quick wins (high benefit, low complexity)**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Better output navigation | H | L | Line classes already exist; only navigation logic needed |
| Run labels from terminal | M | L | Fake command + DB column + history drawer display |
| Richer run metadata in history UI | M | L | Data already stored; surfacing only |

**Tier 2 — High value, moderate effort**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Command outcome summaries | H | M | Start narrow (nmap, dig, curl, openssl); highest signal-to-noise value of any feature on the list |
| Additional export formats | M | L–M | JSONL is straightforward; Markdown needs formatting logic |
| Bulk history operations | M | L–M | Checkbox mode in history drawer + bulk endpoints |
| Share package | H | M | Unified design reduces total work vs building annotations, notes, and lifecycle separately |
| Mobile share ergonomics | M | L–M | Basic native share-sheet done (v1.5); remaining work is one-handed save/share UX and clearer affordances |
| Tool-specific guidance + onboarding hints | M | L | Primarily content work |
| Session dashboards (`stats` command) | M | L | Fake command + queries that already exist for the diagnostics page |

**Tier 3 — Foundational ⬡ (unlock multiple later features)**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Structured command catalog ⬡ | H | H | Unblocks parameterized forms, improved autocomplete, and policy metadata; design forms against this before building them |
| Structured output model ⬡ | H | H | Unblocks command summaries, run comparison, and richer exports; build summaries to be retro-fittable once this is in place |

**Tier 4 — Moderate value, moderate effort**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| History bookmarks beyond stars | M | M | Schema change + label management UI; complements run labels from terminal |
| Saved command presets | M | M | New DB table + preset management UI |
| Workflow replay and promotion | M | M–H | Promotion from history is the core feature; YAML parameterization is secondary |
| Run comparison | M | H | Diff algorithm + run-selection UI; more compelling once history filtering is stronger |
| Per-command policy metadata | M | M | Allowlist format extension + hint surfaces |
| Richer audit trail | L–M | L | Logging additions only |
| Autocomplete from output context | L–M | M | Narrow use case; useful but not on the critical path |

**Tier 5 — Major initiatives (high benefit, high complexity)**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Ephemeral per-session workspace | H | H | Needs allowlist workspace mode, quota, cleanup, and isolation model — not just tmpfs allocation |
| Parameterized command forms | M | H | Depends on structured command catalog; do not build independently |
| Run collections / case folders | M | H | New data model + grouping UI |
| Snapshot diff against current tab | M | H | Builds on run comparison; defer until comparison is done |

**Tier 6 — Defer (high complexity relative to incremental value)**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Full reconnectable live stream | M | H | Separate architecture pass; do not conflate with incremental UI polish |
| Environment capability hints | L–M | M | Pre-run hints have lower per-use value than post-run summaries |
| Interactive PTY mode | M | H | Full PTY + WebSocket architecture for a small allowlisted set |
| Plugin-style helper command registry | L | M | Internal quality; revisit when fake-command layer needs more structure |
| Lightweight Jinja base template | L | L | Third page type now exists (`diag.html`); three templates share the same `<head>` bootstrap |

---

### Near-term

- **Share package** (annotations, notes, and lifecycle controls)
  - Snapshots currently have no metadata beyond the raw output. Add optional title, note, and tags as a unified share package rather than building annotations, operator notes, and sharing controls as disconnected features — they compose into one coherent model.
  - Share package surface:
    - operator-facing title and note on the snapshot
    - tags
    - optional operator / team label
    - redaction mode used
    - a small generated summary block for the shared run
    - private notes attached to history entries (visible locally, never in public snapshots)
  - Share lifecycle controls:
    - expiring share links
    - one-time reveal links for sensitive snapshot sharing
  - Design all three (annotations, notes, lifecycle) together so the data model is consistent from the start.

- **Additional export formats**
  - Add Markdown and JSONL export in addition to `.txt` and themed `.html`.
  - Pairs naturally with the existing export system and structured output work.
  - Make structured exports first-class:
    - include command, timestamps, exit code, line classes, and preview/full-output metadata
    - treat `JSONL` as a real machine-readable export, not just another text dump

- **Better output navigation**
  - For security tool output, 90% of lines are noise and 10% are findings. The most valuable part of this idea is jump-between-errors/warnings, not jump-to-top/bottom.
  - Primary value:
    - jump between warnings / errors / notices (uses existing line classes; this is the core feature)
    - highlight matched lines from search more aggressively
  - Secondary, lower cost:
    - sticky command header for long runs (near-free CSS position: sticky change)
  - Deferred until primary is done:
    - collapse long low-signal sections (genuinely complex, lower incremental value)

- **Run comparison**
  - Compare two runs side by side, especially for repeated scans or before/after checks.
  - More compelling once history filtering is stronger.
  - Focus the first version on repeated commands:
    - compare two runs of the same command
    - show added / removed lines
    - surface exit-code and elapsed-time changes
    - allow a "differences only" view
  - The diff target should explicitly include permalinks and snapshots (not just history entries) — the most common real-world case is comparing a new scan against last month's saved permalink, not two history rows in the same session.

- **Tool-specific guidance**
  - Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `wapiti`, or `nuclei`.
  - Good fit for the existing help / FAQ / welcome surfaces.
  - Merge this with onboarding and command hints into a broader operator-guidance layer:
    - command-specific caveats
    - runtime expectations
    - examples of when to use one tool vs another

- **Richer run metadata in the history UI**
  - Surface preview/full-output availability, retention expectations, and share/export readiness more clearly.
  - Good fit for the existing history drawer and permalink model.
  - Include retention-aware UX:
    - "preview only" vs "full output available"
    - share readiness
    - export readiness
    - expiry / retention timing

- **Command outcome summaries**
  - For selected tools, generate short app-native summaries above the raw output. Security tool output is high-volume; a structured findings layer is what separates a purpose-built tool from a raw terminal.
  - Keep raw output primary — the summary is additive, never a replacement.
  - Start narrow: nmap (open ports + service table), dig (records returned), curl (status code + redirect chain), openssl s_client (cert expiry + trust chain).
  - The structured output model (see Architecture) is the right long-term foundation; build this feature to be retro-fittable once that model is in place rather than requiring it up front.

- **Capture pack review manifest**
  - Generate a simple HTML or Markdown index alongside screenshot packs so designers, themers, and reviewers can browse labeled scenes quickly without opening dozens of PNGs by hand.
  - Include theme, viewport, and scene labels in one place so capture packs are easier to share and audit.

### Later

- **Saved command presets**
  - Let users save named command templates beyond history/starred entries.
  - Better for repeat workflows like DNS checks, HTTP triage, or common scan recipes.
  - Converge this with structured forms:
    - reusable saved workflows
    - optional structured parameters
    - always editable back to raw shell text

- **Parameterized command forms**
  - Add optional structured builders for common tools like `curl`, `dig`, `nmap`, and `ffuf`.
  - Keep raw-shell usage intact while making common tasks easier.
  - Build these on top of a reusable command/workflow preset model rather than as a disconnected UI feature.
  - The autocomplete YAML already models command structure (`flags`, `expects_value`, `arg_hints`, `__positional__`). Forms should be a structured render of that same data — not a parallel model — so the two features stay consistent and share maintenance. Design against the structured command catalog (see Architecture) before building.

- **Session dashboards**
  - Add a compact session summary view. The lowest-complexity version of this is a `session` or `stats` built-in command rather than a dedicated page — it fits the shell-primary interaction model and reuses the existing fake-command layer.
  - Built-in command output:
    - command breakdown by tool root
    - success/fail rates and average scan durations
    - starred artifact count
    - active session token status
  - Natural fit with history, diagnostics, and session tokens.

- **Run collections / case folders**
  - Let users group related runs and snapshots into named investigations or cases.
  - Better long-term organization than tabs/history alone.

- **History bookmarks beyond stars**
  - Add richer saved-state labels like `important`, `baseline`, `follow-up`, or `customer-facing`.
  - Stronger foundation for compare/share/history workflows than a single star state.

- **Snapshot diff against current tab**
  - Compare the live tab against a previous run or snapshot without leaving the shell flow.

- **Workflow replay and promotion**
  - Guided workflows are currently stateless prompt-fillers — you cannot save a customized version of a built-in workflow, and there is no way to replay a sequence you discovered through normal use.
  - The compelling feature is "promote this run sequence to a workflow": select 3–5 history entries and save them as a named reusable sequence. That is more useful than just parameterizing the existing YAML format.
  - Turn guided workflows into reusable multi-step sequences that can be replayed, edited, and saved.

- **Additional built-in workflows**
  - New workflow cards to add to the guided workflows panel. Each complements the existing five (DNS troubleshooting, TLS/HTTPS check, HTTP triage, quick reachability, email server check):
  - **Subdomain Enumeration & Validation** — subfinder to discover subdomains passively, dnsx to resolve and filter live ones, pd-httpx to probe which ones serve HTTP/S. Natural three-phase recon sequence.
  - **Fast Port Discovery → Service Fingerprint** — naabu or rustscan for a quick full-port sweep, then nmap -sV on the discovered open ports only. Two-phase approach: broad-then-deep.
  - **Web Directory Discovery** — gobuster or ffuf against a target URL with a wordlist, then curl to follow up on interesting paths. Good companion to HTTP triage.
  - **SSL/TLS Deep Dive** — sslscan for cipher enumeration, sslyze for known protocol vulnerabilities (BEAST, POODLE, ROBOT, etc.), openssl s_client for raw cert chain inspection. Extends the existing TLS check with the newer dedicated tools.
  - **WAF Detection** — wafw00f to identify the WAF vendor, curl with unexpected headers/paths to observe the blocking behavior, nmap WAF NSE scripts for a second opinion.
  - **WordPress Audit** — wpscan for known plugin/theme CVEs and user enumeration, curl to confirm common WP paths and the XML-RPC endpoint.
  - **Network Path Analysis** — mtr for live traceroute with packet-loss stats, fping for fast multi-host sweep, traceroute for a static path dump. Useful when a host is reachable but intermittently slow.
  - **Domain OSINT / Passive Recon** — whois, subfinder in passive mode, dnsrecon for zone-transfer attempts and common record enumeration. All read-only queries; no active scanning.
  - **DNS Delegation Diff** — host/nslookup for quick answers, dig @authoritative vs @public-resolver for disagreement checks, dig +trace to walk the delegation chain. More focused than the existing DNS card when the problem is split-brain or propagation lag.
  - **Hostname / Virtual Host Discovery** — gobuster vhost or ffuf Host-header fuzzing to identify name-based virtual hosts, then curl -H 'Host: ...' to validate which ones actually answer. Useful when an IP serves multiple sites and plain HTTP triage is too shallow.
  - **Surface Crawl → Endpoint Follow-up** — katana to crawl reachable URLs, pd-httpx or curl -I to classify what came back, then targeted curl checks against the interesting endpoints. Good middle ground between HTTP triage and heavier vuln scanning.
  - **Screenshot / Tech Fingerprint Sweep** — pd-httpx with title/tech-detect/status probes to quickly map many hosts, then curl on the standouts. Strong fit for the modal because it helps operators decide where to spend deeper scanning budget next.
  - **Certificate Inventory Across Hosts** — subfinder or assetfinder to build a host set, dnsx to keep only resolvable names, then openssl s_client or testssl against the likely HTTPS services. More operationally useful than a single-host TLS check when reviewing a whole domain footprint.
  - **Resolver Reputation / Mail Deliverability Baseline** — dig MX/TXT, nslookup against multiple resolvers, and whois on the sending domain or mail host. Distinct from the existing email card because it aims at “will this domain look sane to remote receivers?” rather than just “is SMTP open?”
  - **Crawlable Web App Triage** — curl -sIL for redirect/header shape, katana for path discovery, nikto for quick misconfig findings. A better default web-app sequence than running nikto cold against an unknown target.
  - **API Recon** — katana to discover paths, curl with `Accept: application/json` / OPTIONS / HEAD requests to inspect behavior, then ffuf against likely versioned or documented prefixes. Worth a dedicated card because JSON APIs behave differently from brochure sites and need a different first-pass sequence.
  - **CDN / Edge Behavior Check** — dig and whois to infer provider ownership, curl from HTTP and HTTPS variants to inspect redirect/cache headers, wafw00f to distinguish CDN vs WAF edge behavior. Useful for debugging “works from browser, weird from scanner” cases.
  - **Service Exposure Drift** — repeatable baseline using nmap -F, nc -zv on expected ports, and curl or openssl s_client on the important services. This is less about discovery and more about quickly validating that a host still looks like the last known-good state.
  - Prefer workflow cards that chain 3-4 commands with a clear operator decision at each step; avoid modal entries that are just “run one big scanner.”
  - Prefer sequences that mix cheap classification first and heavier scanning second so the modal remains useful on mobile and in constrained environments.

- **Environment capability hints**
  - Surface when a tool is likely to be slow, noisy, truncated, or constrained by the container/runtime before it runs.

- **Run labels from the terminal**
  - A `tag <label>` built-in command that attaches a label to the most recent completed run directly from the shell flow, without opening the history drawer.
  - Labels like `baseline`, `finding`, `follow-up`, `customer-facing` are more precise than a binary star and set up richer compare/share/history workflows.
  - Complements "History bookmarks beyond stars" — the terminal command is the primary way to label, the history drawer is where labels are visible and filterable.

- **Bulk history operations**
  - The history drawer can delete all or delete non-favorites. Adding multi-select (checkbox mode) with bulk delete, bulk export to JSONL/txt, and bulk share would close a real gap when clearing out a session after an engagement or exporting selected findings.

- **Autocomplete suggestions from output context**
  - When a previous command's output is in the active tab, `| grep` completions could suggest patterns already present in that output — IP addresses, hostnames, status codes, CVE strings — as candidates alongside the generic flag list.
  - Narrow but would make the pipe stage feel predictive rather than generic.

### Mobile

- **Mobile share ergonomics**
  - The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
    - save/share actions tuned for one-handed use
    - clearer copy/share/export affordances inside the mobile shell
    - better share handoff after snapshot creation

### Safety and Policy

- **Richer audit trail**
  - Optional logging around share creation, deletions, and run access patterns.

- **Per-command policy metadata**
  - Allowlist entries could carry metadata like `risky`, `slow`, `high-output`, or `full-output recommended`.
  - The UI could surface this in help, warnings, or command builders.

### Content and Guidance

- **Tool-tips and onboarding hints**
  - Extend the welcome flow and help surfaces so onboarding suggests real tasks and tool combinations, not just isolated commands and hints.
  - Fold this together with tool-specific guidance:
    - "what to run next" suggestions
    - common operator playbooks
    - guidance tied to workflows, autocomplete, and command metadata

### Architecture

- **Full reconnectable live stream**
  - Explore a true reconnectable live-output path that can resume active command streams after reload rather than only restoring a placeholder tab and polling for completion.
  - This is a separate architecture step from the current active-run reconnect support and would likely require:
    - a per-run live output buffer
    - resumable stream offsets or event IDs
    - multi-consumer fan-out instead of one transient SSE consumer
    - explicit lifecycle cleanup once runs complete
  - Best fit is a dedicated live-stream architecture pass rather than incremental UI polish.

- **Structured command catalog**
  - Move from plain-text allowlist-only metadata toward a richer command catalog model.
  - This would unlock better autocomplete, command forms, grouped help, and policy hints.
  - Design parameterized command forms (see Later) against this catalog model before building them — both features need the same structured command data and will diverge if built independently.

- **Structured output model**
  - Preserve richer line/event metadata consistently for all runs.
  - This would improve search, comparison, redaction, exports, and permalink fidelity.
  - Command outcome summaries (see Near-term) are buildable without this foundation, but design them to be retro-fittable once the structured model is in place — the summary parsers should consume structured line events, not re-parse raw text.

- **Plugin-style helper command registry**
  - Turn the fake-command layer into a cleaner extension surface for future app-native helpers.

- **Ephemeral per-session workspace mode**
  - Add an optional tmpfs-backed per-session working directory so users can create short-lived files and use more natural shell workflows such as `ls`, `cat`, `rm`, and output redirection into files.
  - Treat this as a separate execution mode with its own validation, cleanup, quota, and audit model rather than as a small shell-ergonomics enhancement.
  - The existing allowed_commands system would need a paired workspace mode — `ls`, `cat`, `rm`, `mv`, and output redirection (`>`, `>>`) are either blocked metacharacters or not in the allowlist today. A workspace mode needs explicit allowlist support, not just a tmpfs allocation.
  - Scope the safety model explicitly:
    - per-session byte quota
    - max file size
    - max file count / inode-style limit
    - aggressive cleanup on expiry
    - optional app-mediated file download support from the active session workspace
  - Consider a stronger isolation path as a later phase:
    - a real per-session chroot-style jail or equivalent container-level filesystem jail so the shell process cannot see outside the session workspace at all
    - this would make the feature feel much more like a real shell while reducing accidental filesystem exposure

- **Lightweight Jinja base template**
  - `index.html`, `permalink_base.html`, and `diag.html` now all share the same ~10 lines of `<head>` bootstrap (charset, viewport, color-scheme meta, favicon, `fonts.css`, `styles.css`, theme var includes, and the two vendor scripts). With three templates the duplication is starting to pay for the indirection.
  - A `base.html` factoring out the common `<head>` and `data-theme` body attribute would prevent drift and make adding a fourth page type trivial.

- **Interactive PTY mode for screen-based tools**
  - Explore an optional PTY + WebSocket + browser terminal emulator path for a small allowlisted set of interactive or screen-redrawing tools such as `mtr`, without turning the app into a general-purpose remote shell.
  - Best fit is a separate interactive-command mode or tab type, not a full browser shell session.
  - This would be a larger architecture change because it needs:
    - server-side PTY management
    - bidirectional browser transport
    - terminal resize handling
    - stricter command scoping and lifecycle cleanup
