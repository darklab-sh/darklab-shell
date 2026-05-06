# TODO

This file tracks open work, known issues, technical debt, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Ideas are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
- [Research](#research)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Ideas](#ideas)
- [Architecture](#architecture)

---

## Open TODOs

- **Project workspace implementation plan**
  - **Current state:** `docs/ROADMAP.md` defines the next major direction as a project/case workspace that keeps the shell primary while organizing runs, snapshots, findings, files, targets, notes, and exportable evidence. The current app already has durable sessions, run history, snapshots, full-output artifacts, starred commands, workflows, recent domains, PTY persistence, and bounded history/search paths, but those records are still mostly session-scoped islands instead of a shared project data model.
  - **Completed so far:** the database relationship foundation, project CRUD/link routes, session migration support, session-scoped active project API, automatic active-project linking for completed server-owned and browser-owned runs, snapshot linking for project-associated tabs, and project-aware history filtering are in place.
  - **Sequencing principle:** Build the database schema and relationship layer first. Projects, artifact capture, targets, persisted findings, labels, annotations, packages, workflow replay, and comparison should all reuse the same entity/link vocabulary instead of each feature adding its own one-off relationship model.
  - **Phase 0: schema and relationship foundation**
    - Define the canonical project entity vocabulary before adding UI:
      - `project`
      - `run`
      - `snapshot`
      - `workspace_file`
      - `run_file_artifact`
      - `finding`
      - `target`
      - `annotation`
      - `package`
    - Add strict app-level constants/helpers for entity types and link sources so generic tables stay flexible without allowing arbitrary strings to spread through routes, UI code, and tests.
    - Add core project tables:
      - `projects`: `id`, `session_id`, `name`, `slug`, `description`, `status`, `color`, `notes`, `created`, `updated`.
      - `project_links`: `id`, `project_id`, `entity_type`, `entity_id`, `source`, `created`.
    - Add early relationship-ready tables even if their full UI lands later:
      - `run_file_artifacts`: durable manifest rows for input/output/report/database files produced or consumed by runs.
      - `project_targets`: project-owned domains, URLs, hosts, IPs, CIDRs, and port sets.
      - `findings`: persisted output-signal/finding rows linked back to runs and optionally targets.
      - `entity_labels`: short labels/bookmarks for runs, snapshots, findings, files, artifacts, projects, and packages.
      - `annotations`: short private/package-ready comments attached to supported entity types.
    - Keep projects as link owners, not copy owners. Runs, snapshots, findings, and workspace files should remain source records and be linked into projects.
    - Allow one entity to belong to multiple projects unless a concrete UX or retention rule proves that harmful.
    - Add indexes for expected query shapes before UI work depends on them:
      - session project list: `(session_id, status, updated DESC)`
      - project contents: `(project_id, entity_type, created DESC)`
      - reverse lookup: `(entity_type, entity_id)`
      - artifact lookup: `(session_id, run_id, workspace_path)`
      - targets: `(project_id, type, value)`
      - findings: `(session_id, run_id, created)` and `(target_id, created)`
      - labels/annotations: `(entity_type, entity_id, created)`
    - Add database migration/bootstrap tests that prove fresh databases, existing v1.x databases, and repeated startup migrations all converge on the same schema.
    - Update `ARCHITECTURE.md` with the project schema diagram and relationship rules as soon as the schema lands, before feature UI makes the model harder to revise.
  - **Phase 1: project CRUD and manual linking**
    - Add project create/list/rename/archive/delete routes.
    - Add link/unlink routes for runs, snapshots, workspace files, artifacts, findings, and targets through the shared relationship helpers.
    - Delete project metadata and project links by default, not linked source records.
    - Add terminal built-ins for the shell-first path:
      - `project list`
      - `project create <name>`
      - `project use <name-or-id>`
      - `project current`
      - `project archive <name-or-id>`
      - `project link last`
      - `project link run <run-id>`
      - `project link snapshot <snapshot-id>`
      - `project link file <path>`
      - `project unlink ...`
    - Add a minimal project selector and project detail surface after the API works.
  - **Phase 2: active project context**
    - Persist active project per session preference. (Backend API complete.)
    - Show active project context in desktop and mobile shell chrome without making command entry heavier.
    - Auto-link newly completed server-owned runs to the active project with `source=active_project`. (Complete.)
    - Ensure browser-owned built-ins persisted through `/run/client` use the same project-link path when appropriate. (Complete.)
    - Link snapshots created from project-associated tabs. (Complete.)
    - Add history filters for project-linked runs and snapshots. (Complete.)
  - **Phase 3: run-created file artifact capture**
    - Extend command registry workspace metadata for known input and output flags.
    - Record expected output artifacts when command validation rewrites workspace file flags.
    - Add conservative workspace diff capture only after declared-flag artifact capture and UI affordances are solid.
    - Show run artifacts in history rows, restored tabs, run permalinks, project details, and the Files modal.
    - Add session-token migration tests for linked workspace files and artifacts.
  - **Phase 4: project targets and autocomplete context**
    - Add target management for domains, URLs, hosts, IPs, CIDRs, and named port sets.
    - Let users quick-add targets from selected output text, findings, history rows, and workspace file previews.
    - Feed active project targets into autocomplete with visible project scoping.
    - Infer target links from commands and persisted finding metadata only when confidence is high enough to explain to the user.
  - **Phase 5: persisted findings, labels, and annotations**
    - Persist high-signal output findings from the existing classifier instead of treating them only as transient transcript signals.
    - Add finding review states such as `new`, `reviewed`, `important`, `false_positive`, and `needs_followup`.
    - Add label/bookmark support for runs and other entities, preserving the current starred-command behavior as a compatibility surface.
    - Add short annotations for findings, runs, snapshots, files, artifacts, and targets.
    - Add project findings filters for target, run, command root, severity/scope, review state, label, and annotation state.
  - **Phase 6: project notes and evidence packages**
    - Store one small notes field per project first; avoid a multi-page notes system.
    - Build package creation around the already-linked data:
      - selected runs
      - selected findings
      - snapshots
      - artifacts/files
      - targets
      - labels
      - annotations
      - project notes
    - Support raw/redacted package choices, artifact inclusion choices, and a manifest that records source project/session/entity IDs.
  - **Phase 7: workflow, comparison, and baseline layer**
    - Let users promote history sequences into reusable workflows that can bind to project targets.
    - Add project baseline labels and compare against previous runs, baselines, snapshots, or package artifacts.
    - Keep workflow steps editable as raw shell commands; do not introduce a parallel form schema when the command registry can drive optional forms later.
  - **Phase 8: retention, diagnostics, docs, and mobile polish**
    - Decide whether project-linked runs/artifacts are retained longer or only warned before pruning.
    - Add project, artifact, finding, annotation, and package counts to `/diag`.
    - Add structured log events for project creation, link changes, annotations, package creation/deletion/access, and retention warnings.
    - Update `FEATURES.md`, `README.md`, `ARCHITECTURE.md`, release drafts, and tests as each project workspace slice lands.
    - Make mobile project selection, project details, findings review, and package creation practical after the desktop flow proves the model.
  - **First implementation slice**
    - Completed the schema foundation: project workspace relationship tables, entity/link-source helpers, migrations, indexes, database tests, and architecture docs.
    - Initial backend routes now cover session-scoped project CRUD, archive filtering, supported entity link/unlink, project link listing, source-record ownership checks, and session migration for project workspace records.
    - Do not build substantial UI until the backend can represent projects, links, artifacts, targets, findings, labels, and annotations consistently.
    - Keep `docs/ROADMAP.md` as the product-direction narrative; use this TODO section as the executable implementation checklist.

- **Future interactive PTY enhancements**
  - **Current state:** `mtr --interactive <host>`, `ffuf --interactive ...`, and `masscan --interactive ...` have a guarded PTY path behind `interactive_pty_enabled`, use dedicated `/pty/runs` start/stream/input/resize routes, broker PTY events through Redis in multi-worker deployments, support bounded concurrent PTY runs per session with each live terminal scoped to its owning tab, require registry-owned input-safety profiles, render the live terminal in an xterm.js modal, and append completed PTY runs back into the normal terminal/history output path using server-side terminal capture. Redis PTY snapshots support cross-worker reattach, use bounded publish rates, and return specific failure statuses for missing, closed, stale, or not-yet-available runs.
  - **Future lifecycle and resilience**
    - Consider auto-displacing prior live attaches when a new browser client attaches to the same PTY run. When `active_run_claim_owner` flips the internal ownership marker to a different `client_id`, publish a single `displaced` event on the PTY stream so the prior tab can close its modal cleanly and append one notice such as `[interactive PTY moved to another tab]`. Skip same-client reconnects so the event only fires when the live view genuinely moves to a different browser context. With this in place, the remaining per-keystroke `[interactive PTY input ignored: ...]` notices in `_ptySendInput` could become rare edge-case failures instead of common transcript noise.
    - Revisit transport after real usage. The current pass uses Redis-brokered SSE plus narrow POST input/resize endpoints to avoid adding a WebSocket server dependency; WebSocket may still be useful if latency, throughput, or bidirectional control behavior becomes a real limitation.
  - **Future security**
    - Defer asciinema-style raw byte replay and input auditing until real usage shows they are needed.
  - **Future architecture**
    - Split `pty.js` into smaller modules once PTY work resumes in depth. Natural boundaries are orchestration/command detection, modal wiring/timer/status, and xterm session/resize handling.
    - Split `pty_service.py` once more PTY server behavior accumulates. Capture, run lifecycle, Redis stream transport, control-stream draining, and metadata storage are natural module boundaries.
    - Consider dropping the base `#pty-overlay` from `index.html` and building every PTY modal through `_ptyBuildOverlay`. Tab overlays are now normalized and reused, so this is cleanup rather than a leak fix; the benefit would be removing the remaining ID/class selector duality in `_ptyModalEls`.
    - Verify or document PTY modal positioning and mobile-sheet behavior with the overlay scoped inside `.tab-panel`. PTY startup is disabled on mobile, but the shared modal/mobile-sheet CSS still deserves a viewport sanity check if the modal layout changes again.
    - Introduce a small PTY host interface object for browser tests. `pty.js` still reaches into many runner globals; a host object would make tests less brittle and reduce global-surface coupling.
    - Add broader browser unit coverage for PTY tab state transitions and disabled normal-terminal behaviors as future PTY features are added.
  - **Future polish and operational visibility**
    - `_PTY_INPUT_MAX_BYTES`, `_PTY_BUFFER_LIMIT`, `_PTY_CONTROL_POLL_SECONDS`, `_PTY_SNAPSHOT_FALLBACK_ENTRY_LIMIT`, and similar tunables are module constants. Move to config so deploys can tune without a rebuild.
    - Add metrics covering concurrent PTY count, average and p95 duration, total input bytes, dropped input bytes, and control queue depth. Expose them through the existing `/diag` surface so operators have visibility comparable to other run paths.
    - The reader loop polls Redis every 200 ms via `xread block=1` for control events. With many concurrent PTYs this is wasted ops. Switch the control channel to Redis Pub/Sub (or a longer block window) so idle PTYs cost zero ops while output latency stays unaffected.
    - Surface snapshot age on the reattach payload. `_load_pty_snapshot` strips `created_at` before returning, so the frontend cannot tell whether the snapshot is fresh or 20+ seconds stale. Return the age and let the frontend show `[reattached - snapshot was Ns old]` when it crosses a threshold, so users know the screen they see may not match what the PTY is currently rendering.
    - Skip the unconditional `_store_pty_snapshot(run, force=True)` in `pty_run_snapshot` when the request hits the worker that owns the PTY. The route already returns the live in-memory payload to the caller, and the next reader-loop tick will publish to Redis naturally; the extra Redis SET costs one round-trip per attach for cross-worker freshness that is rarely consumed.
    - Consider pausing xterm rendering for hidden-tab PTYs. xterm.js running in a `display: none` panel still processes writes and grows scrollback (capped at 1000 lines, but still wasted CPU). Either drop incoming `output` chunks into the modal only when visible (queue and replay on tab focus) or accept the cost as small enough to ignore — worth measuring under a long-running ffuf in a backgrounded tab before spending engineering on it.

## Research

No research items are currently tracked.

---

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

No technical debt items are currently tracked.

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

- **Tool-specific guidance**
  - Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `naabu`, or `nuclei`.
  - Good fit for the existing help / FAQ / welcome surfaces.
  - Merge this with onboarding and command hints into a broader user guidance layer:
    - command-specific caveats
    - what to expect while a tool runs
    - examples of when to use one tool vs another

- **Command catalog future-state**
  - Add `commands search <term>` for roots, descriptions, categories, examples, and flag text.
  - Add `commands --json` or `commands info --json <root>` for debugging, export, and future UI reuse.
  - Add optional richer registry fields such as `details`, `notes`, `common_flags`, or `gotchas` when a flag or tool needs more than a short autocomplete description.
  - Add command-specific guidance for web-shell behavior, including injected safe defaults, quiet-running tools, generated Files output, and managed session state.
  - Add autocomplete side previews later: when a root, subcommand, or flag is highlighted, show the command description or flag note in a small help pane.
  - Add hover/focus cards for FAQ chips once the command-details modal behavior has settled.
  - Consider including pipe helpers in a separate “Pipes” section once command catalog UX exists.
  - Consider linking command catalog entries to real `man` output where available, while keeping app-native allowed-subset details primary.

- **Command outcome summaries**
  - For selected tools, generate short app-native summaries below the raw output. Security tool output is high-volume; a clear findings layer is what separates a purpose-built tool from a raw terminal.
  - Keep raw output primary — the summary is additive, never a replacement.
  - Start narrow: nmap (open ports + service table), dig (records returned), curl (status code + redirect chain), openssl s_client (cert expiry + trust chain).
  - The structured output model (see Architecture) is the right long-term foundation. Build this feature so it can move onto that model later instead of requiring it up front.

- **Transcript noise classification**
  - Future cleanup for saved command output across both normal runs and interactive PTY runs.
  - Avoid broad duplicate-line removal because repeated lines can be meaningful findings for some tools.
  - Classify known progress/status/redraw lines before history/search/finding classification, starting with high-noise shapes from tools like `masscan`, `ffuf`, `nuclei`, and ProjectDiscovery tools that emit frequent status updates.
  - Keep real newline-terminated findings and normal scrollback untouched.
  - For interactive PTY runs, keep the final visible frame available so users can still inspect the last terminal state, even when progress/status redraw lines are excluded from searchable saved transcript text.
  - For normal runs, prefer command-specific noise classifiers over global suppression so raw output stays faithful while search, findings, summaries, and previews become easier to use.

- **Run comparison enhancements**
  - Future-state enhancements after the v1 history-row comparison flow has real use.
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
    - Project baseline compare once projects exist.
    - Snapshot/permalink compare if the run-vs-run model continues to work well.
    - `Export comparison` once share/export packages have a stable artifact model.
  - Future UX/testing:
    - Consider date-range filters in the manual compare picker if day grouping plus `Load More` is not enough for deep history.
    - Add Playwright coverage for the compare launcher/result flow on desktop and mobile after the UI settles.
    - Add focused large/noisy comparison regression coverage if real-world outputs expose performance issues beyond current backend and unit coverage.

- **Bulk history operations**
  - The history drawer can delete all or delete non-favorites. Adding multi-select (checkbox mode) with bulk delete, bulk export to JSONL/txt, and bulk share would close a real gap when clearing out a session after an engagement or exporting selected findings.

- **Autocomplete suggestions from output context**
  - When a previous command's output is in the active tab, `| grep` completions could suggest patterns already present in that output — IP addresses, hostnames, status codes, CVE strings — as candidates alongside the generic flag list.
  - Narrow but would make the pipe stage feel predictive rather than generic.

- **Mobile share ergonomics**
  - The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
    - save/share actions tuned for one-handed use
    - clearer copy/share/export affordances inside the mobile shell
    - better share handoff after snapshot creation

---

## Architecture

- **Structured output model**
  - Preserve richer line/event details consistently for all runs.
  - This would improve search, comparison, redaction, exports, and permalink fidelity.
  - Command outcome summaries are buildable without this foundation, but design them so they can move onto the structured model later. Summary parsers should consume structured line events, not re-parse raw text forever.

- **Unified terminal built-in lifecycle**
  - Browser-owned built-ins (`theme`, `config`, and `session-token`) need browser execution for DOM state, local storage, clipboard, and transcript-owned confirmations, while server-owned built-ins naturally flow through `/runs`.
  - The long-term cleanup target is one terminal-command lifecycle after execution:
    - normalize built-in output into a shared result shape
    - apply pipe helpers against that shape
    - mask sensitive command arguments once
    - render transcript output once
    - persist server-backed history once
    - load recents and prompt history from the same saved run model
  - Keep execution ownership separate where it matters, but remove duplicated recents/history/pipe/persistence glue so browser-owned and server-owned built-ins cannot drift.

- **Plugin-style helper command registry**
  - Turn the built-in command layer into a cleaner extension point for future app-native helpers.

- **Lightweight Jinja base template**
  - `index.html`, `permalink_base.html`, and `diag.html` now all share the same ~10 lines of `<head>` bootstrap (charset, viewport, color-scheme meta, favicon, `fonts.css`, `styles.css`, theme var includes, and the two vendor scripts). With three templates the duplication is starting to pay for the indirection.
  - A `base.html` factoring out the common `<head>` and `data-theme` body attribute would prevent drift and make adding a fourth page type trivial.

- **Interactive PTY transport future-state**
  - Revisit whether the current Redis-brokered SSE plus POST input/resize transport should move to WebSockets after real use.
  - The current model keeps deployment simple and avoids a WebSocket runtime, but a bidirectional socket could reduce input latency and simplify the modal terminal stream once PTY usage grows.
