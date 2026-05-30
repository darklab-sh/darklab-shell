# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Feature Enhancements](#feature-enhancements)
  - [Atlas Enhancements](#atlas-enhancements)
  - [Future Project Workspace enhancements](#future-project-workspace-enhancements)
  - [Future interactive PTY enhancements](#future-interactive-pty-enhancements)
- [Research](#research)
- [Ideas](#ideas)
  - [Audit log surface](#audit-log-surface)
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

### Team-scoped Files workspace

Build Files/workspace storage so it follows the same active personal/team scope model as runs, History, Projects, Atlas, workflows, schedules, watchers, notifications, AI assists, and team secrets. Personal scope keeps using the current session workspace. Team scope shows a durable shared team workspace, rewrites workspace-aware command paths into that team workspace, and keeps personal files separate.

**Current surface to reconcile**
- `app/services/workspace/files.py` is session-id first: directory naming, path resolution, quota checks, migration, cleanup, permission repair, read/write/list/delete/move/download, and command preparation all take `session_id`.
- `app/blueprints/workspace.py` resolves only `get_session_id()`, so `/workspace/files*` currently ignores `X-Team-ID` and cannot enforce team role permissions.
- File labels/notes and run-file artifact metadata are keyed by `session_id` plus `entity_type='workspace_file'`; team scope needs metadata reads/writes to follow owner scope so two members see the same team-file labels/notes without leaking personal file metadata.
- Workspace-aware command validation and runtime adaptations in `app/services/commands/registry.py` use `ensure_session_workspace()`, `resolve_workspace_path()`, and `read_workspace_text_file()` with the current session id; `wget` defaults, ProjectDiscovery `XDG_CONFIG_HOME`, Amass managed directories, and workspace file flags all need the active owner workspace.
- Browser Files state in `app/static/js/workspace.js` assumes one current Files payload and one tab-local cwd model; active scope changes should reload the Files payload, reset stale open viewers/editors as needed, and keep tab cwd from leaking between personal and team scope.
- The current inactivity cleanup removes only `sess_*` directories. Team workspace directories must not be aged out by session inactivity cleanup.

**Committed first-pass decisions**
- Use one configured workspace root. Personal directories stay `sess_<hash>`. Team directories become `team_<hash>` under the same `workspace_root`; no separate `team_workspace_root` config is added in the first pass.
- Existing `workspace_quota_mb`, `workspace_max_file_mb`, and `workspace_max_files` apply per owner workspace, whether the owner is a personal session or a team.
- Durable shared team Files require `workspace_backend: volume` with a persistent shared `workspace_root` mount. When `workspace_backend: tmpfs` is used, team workspaces are best-effort single-container scratch space and are lost on restart; the UI/API must report that limitation clearly or hard-disable team Files under tmpfs before claiming durability.
- Team workspaces are team-owned workspace data. They are not migrated from personal workspaces automatically, not mixed into personal Files, and not deleted by session-inactivity cleanup.
- Active-scope switches change what the Files panel and new workspace-aware commands see. In-flight runs, PTYs, and already-open command streams retain the workspace owner captured when they started.
- Team viewers can list, read, preview, and download team files. Team write actions require a dedicated `manage_workspace_files` capability granted to owners, admins, and operators; viewers stay read-only.
- Files is the one team surface that intentionally keeps archived teams readable. Phase 1 must add an explicit read-only archived-team resolver path, such as `current_request_scope(..., allow_archived=True)` or a small sibling helper, that returns the normal `RequestScope` plus an archived/read-only flag instead of hard-rejecting with `team_archived`.
- Team deletion/archive behavior mirrors other durable team data: archived teams stay readable but cannot mutate Files; team deletion may remove the team workspace only through the team deletion path, not by background cleanup.
- Quota enforcement for team workspaces must be serialized per owner around quota-gated writes. Prefer the existing database/advisory-lock pattern keyed by owner id instead of a filesystem-only lock, because team Files may be served by multiple workers or containers sharing the same database.
- Out of scope: auto-merging personal files into a team workspace, combined personal+team file views, per-folder ACLs, cross-team sharing, real-time collaborative editing, file comments, and package-style bulk workspace export.

**Phase 1 — Owner-aware workspace contract**
- Reuse the existing team scope model instead of introducing a parallel workspace owner type. Owner-aware workspace helpers should accept `OwnerContext` or `RequestScope` from `services/teams/scope.py` and `services/teams/request_scope.py`, then derive `sess_<hash(session_id)>` for personal scope and `team_<hash(team_id)>` for team scope.
- Keep the existing session helper names as compatibility wrappers that build a personal `OwnerContext`, then delegate to owner-aware helpers such as `workspace_owner_name()`, `owner_workspace_dir()`, `ensure_owner_workspace()`, `resolve_owner_workspace_path()`, `owner_workspace_usage()`, and owner-aware list/read/write/delete/move/download helpers.
- Add `Capability.MANAGE_WORKSPACE_FILES` to the Python role matrix. Owners get it automatically through `frozenset(Capability)`, admins and operators get it explicitly, and viewers do not.
- Add the archived-team read resolver needed by Files routes. The helper must preserve the normal hard rejection for existing surfaces unless callers explicitly opt into archived read-only scope.
- Add a `v0025_*` migration for workspace-file metadata ownership. Backfill `team_id=''` on `entity_labels`, `entity_notes`, and any other workspace-file metadata table that needs shared team reads. Drop the existing table-level unique constraints first, then add the established personal/team partial unique indexes: `entity_labels` uniqueness includes `label`; `entity_notes` uniqueness is only `entity_type` + `entity_id` within the personal or team owner.
- Add a per-owner lock around quota-gated writes and directory creates that can increase file count or bytes used.
- Guard `migrate_session_workspace()` so token rotation remains personal-to-personal only and can never read from or write to a `team_*` directory. Apply the same personal-only guard to the token-rotation workspace metadata migration helpers in `app/services/projects/migration.py` so `_update_workspace_file_metadata()` and `_count_workspace_file_metadata()` never touch `team_id!=''` rows.
- Add tests for directory naming, owner separation, quota isolation under concurrent writes, symlink/path traversal rejection, archived read-only resolver behavior, the metadata migration/index shape, personal compatibility wrappers, and the migration guard.

**Phase 2 — Workspace routes honor active scope and role gates**
- Update `/workspace/files`, `/workspace/files/read`, `/workspace/files/info`, `/workspace/files/download`, `/workspace/directories`, `/workspace/files/move`, and `/workspace/files` delete/write routes to resolve `current_request_scope()` from `X-Team-ID`/`team_id`.
- Use the archived-read resolver for list/read/info/download only. Mutating routes keep the normal active-team requirement and return a clear `team_archived` denial for archived teams.
- Apply read permission for any active or archived team member, and write/delete/move/create permission for `manage_workspace_files` on active teams only.
- Return owner metadata in the Files payload, including scope, team id when active, display label, read-only flag, and denial message for write actions.
- Convert file metadata helpers for labels/notes and artifact counts to owner-aware predicates using `shared_owner_predicate()` so team members share team-file labels/notes while personal file metadata remains private. Reuse the existing `team_id` parameters already threaded through project metadata helpers instead of adding a parallel metadata API.
- Add route tests for personal isolation, cross-member team reads/writes, viewer read-only denials, archived-team read-only behavior, non-member denial, metadata sharing, and download/read parity.

**Phase 3 — Commands and runtime workspace rewrites**
- Thread owner workspace context through command validation/startup so workspace-aware flags, default `wget -P`, runtime `XDG_CONFIG_HOME`, managed Amass directories, and output path redaction resolve to the active personal or team workspace.
- Capture the workspace owner on run start and PTY start. Persist enough metadata on active runs so stream/kill/finalize paths can continue to describe the correct workspace even after the browser switches scope.
- Update terminal `file`, `ls`, `cat`, `mkdir`, `mv`, `rm`, `grep`, `head`, `tail`, `wc`, `sort`, and `uniq` browser/server built-ins to use the active owner workspace and to reject write commands for team viewers before opening confirmations.
- Ensure command output path rewriting maps absolute `team_*` paths back to user-facing Files paths without exposing hashed directory names.
- Add tests for workspace-aware command rewrites in team scope, viewer write denial, in-flight scope retention after switching back to personal scope, ProjectDiscovery tool config paths, Amass managed directory behavior, and restricted-input checks reading team-scoped list files.

**Phase 4 — Browser Files scope switching and mobile parity**
- Make the Files panel reload when the active team scope changes, close or refresh stale open viewers/editors, reset cwd per scope, and show a compact personal/team scope label consistent with History/Projects/Atlas.
- Disable create/edit/delete/move/upload-like controls for team viewers and archived teams on desktop and mobile; keep read/preview/download available.
- Ensure drag/drop move behavior, viewer header actions, file metadata editor, terminal `file add/edit/delete/move` handoffs, autocomplete cache, and current-directory prompt updates all follow the active scope.
- Add browser unit coverage for personal/team payload swaps, viewer read-only controls, archived-team read-only state, scope-switch reloads, mobile Files controls, autocomplete cache separation, and stale server-denial messages.
- Add a focused Playwright path if the existing mobile/desktop Files scenes cannot cover a team scope switch plus read-only controls.

**Phase 5 — Cleanup, lifecycle, artifacts, and packages**
- Update cleanup so session inactivity only removes `sess_*` directories and never touches `team_*` directories.
- Add explicit team workspace removal or archival behavior under team lifecycle services, with audit/logging and permission checks on destructive deletion.
- Verify run-file artifact capture records the owner workspace for team-owned runs so Projects, artifact previews/downloads, and evidence packages resolve team workspace files for every member while preserving personal isolation.
- Artifact read-side resolution must derive the workspace owner from the persisted run record, never from the requester's currently active `X-Team-ID`. Name and update the history/project artifact preview and download routes that currently resolve workspace artifacts by `session_id`, including `services/projects/workspace_artifacts.py`, so member B can preview/download artifacts from member A's team run without switching to member A's personal workspace or accidentally resolving a same-named personal file.
- Ensure package archive builders and package jobs restore team workspace context when running asynchronously, matching the existing team workflow/package scope restoration model.
- Add tests for cleanup skipping team dirs, team delete/archive lifecycle, artifact preview/download across members, evidence package archive resolution, and package worker scope restoration.

**Phase 6 — Documentation and release readiness**
- Update `README.md`, `FEATURES.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`, `DECISIONS.md`, `docs/external-command-integrations.md`, `tests/README.md`, and release-draft entries in current-state language once the implementation lands.
- Keep `TODO.md` as the only phase/future-state document while the work is in progress.
- Update CHANGELOG under the single Team-Mode feature entry.
- Update test counts in `ARCHITECTURE.md`, `CONTRIBUTING.md`, and `tests/README.md`, plus the full test appendix.
- Run focused workspace/unit/route tests, `tests/py/test_docs.py`, markdownlint, `git diff --check`, and a team-scope Files browser smoke path before closing the item.

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

No technical debt items are currently tracked.

---

## Feature Enhancements

### API / CLI Enhancements
- **Webhook receiver / `POST /api/v1/intel/<provider>` passthrough.**
  - Not for v1.1, but worth scoping — once outbound notifications land, the headless API becomes the natural place to receive `pull-request-merged` / `engagement-kicked-off` webhooks that auto-create projects.
### Atlas Enhancements
- **Future**
  - Entity graph view (visual link map across hosts, domains, hashes, CVEs).
  - Auto-promote rules — entities matching saved patterns auto-promote into a project.
  - Time-travel view: "what did the Atlas look like a week ago?" using retained snapshots.
  - Side-by-side entity comparison (their runs, findings, intel snapshots).
  - Cross-session Atlas view for operators managing multiple sessions or shared infrastructure.
  - Atlas import from external triage tools.

### Future Project Workspace enhancements
- **Security and lifecycle**
  - Add parallel PATCH routes for partial project and target updates if the project workspace API ever becomes more than a trusted browser-only surface.
- **Capture, tagging, and navigation**
  - Add a compact project switcher near the prompt with recently used projects and a Create New action.
- **Future-state mobile polish**
  - Consider swipe gestures for target and finding rows only after overflow-menu interactions are shipped and tested.
- **Findings and comparison**
  - Extend comparison beyond run-to-run finding/artifact diffs to snapshots and package artifacts.
- **Evidence packages**
  - Materialize evidence package archives at creation time if byte-for-byte repeat downloads become important.
  - Make package presets config-driven so new bundle profiles, such as internal review or external handoff, can be added without code changes.
  - Add richer per-finding remediation or verification fields if findings evolve beyond raw output capture.
  - Add richer target references in package exports, including derived relationships that are not directly visible in selected finding text.
  - Add richer provenance metadata and round-trip import hints for labels, notes, targets, findings, and packages.
  - Explore fuller direct template reuse for package run transcript pages without reintroducing app-hosted asset links.
  - Add generated re-package names that preserve the original selection while incrementing the package label or timestamp.

### Future interactive PTY enhancements
- **Future lifecycle and resilience**
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
  - The reader loop polls Redis every 200 ms via `xread block=1` for control events. With many concurrent PTYs this is wasted ops. Switch the control channel to Redis Pub/Sub (or a longer block window) so idle PTYs cost zero ops while output latency stays unaffected.
  - Skip the unconditional `_store_pty_snapshot(run, force=True)` in `pty_run_snapshot` when the request hits the worker that owns the PTY. The route already returns the live in-memory payload to the caller, and the next reader-loop tick will publish to Redis naturally; the extra Redis SET costs one round-trip per attach for cross-worker freshness that is rarely consumed.
  - Consider pausing xterm rendering for hidden-tab PTYs. xterm.js running in a `display: none` panel still processes writes and grows scrollback (capped at 1000 lines, but still wasted CPU). Either drop incoming `output` chunks into the modal only when visible (queue and replay on tab focus) or accept the cost as small enough to ignore — worth measuring under a long-running ffuf in a backgrounded tab before spending engineering on it.

## Research

No research items are currently tracked.

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Audit log surface
- Add a queryable audit table for consequential actions such as delete, share, redaction toggle, secret create/replace, project link, suppression, and evidence package build.
- Add an audit viewer on `/diag` or inside Options so operators can inspect what happened without reconstructing it from structured logs after the fact.
- Many engagement contracts require this kind of operator-visible trail, so this would make compliance and post-engagement review easier.

### Workflows v2 — playbooks with parameters
- Evolve workflows from saved command lists into reusable runbooks.
- Add typed parameters such as target, port set, and wordlist reference, then prompt for those values at execute time.
- Add conditional next-step behavior based on exit code.
- Let each step capture selected output into named variables that later steps can consume.

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
- **Entry-level scope:**
  - Add a manifest, app icons, and a small service worker so users can "Add to Home Screen" and launch into a standalone mobile shell.
  - VAPID-signed web-push subscription tied to the active session token; subscribe and unsubscribe from the Options sheet.
  - Reuse the run-complete event hook from the outbound-notifications surface so push is just another channel.
- **Architecture:**
  - New `app/static/manifest.webmanifest`, icon assets under `app/static/icons/`, and `app/static/sw.js` registered from `app.js` only when the runtime supports it.
  - New `WebPushChannel` in the notifications service; VAPID keys stored as operator config; per-session-token subscription endpoint at `/session/push/subscribe`.
  - Service worker scope is intentionally narrow — render notifications and open the tab on click; no caching of dynamic transcript content so users never see stale output.
  - Gotchas: iOS Safari requires the user to install the PWA before push works; document this in CONFIGURATION.md.

### Engagement report builder
- Turn a project workspace into a styled markdown/PDF engagement report — methodology, scope, targets, findings table, remediation notes, screenshots. Evidence packages today are raw bundles; this is the narrative deliverable a customer reads.
- **Entry-level scope:**
  - One-click "Generate report" from a project, with an editable cover page (engagement name, dates, operator, contact).
  - Sections auto-populated from project data: targets, findings grouped by severity, included runs (with permalinks), artifacts.
  - Output formats: markdown source plus rendered HTML and PDF, reusing the existing export pipeline.
  - Operator-editable section templates in a new `app/conf/report_templates.yaml`.
- **Architecture:**
  - New `app/services/reports/` service composing project-workspace data with existing finding/run/artifact serializers; templating via Jinja autoescape.
  - Adds `GET/POST /projects/<id>/report` to `app/blueprints/projects.py`.
  - Browser surface: a "Report" tab inside the existing Projects modal; renderer reuses `export_html.js` and `export_pdf.js`.
  - Honors share-redaction defaults; the draft is always previewed before download so this stays additive to evidence packages, not a replacement.

### Native ticketing integrations
- From the Findings tab, Project views, or evidence package flows, create or update issues in Jira, Linear, GitHub Issues, GitLab, etc., with bidirectional sync of status, notes, and links back into the finding review state.
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
