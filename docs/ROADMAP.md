# ROADMAP

This file tracks the next major product direction for darklab_shell: moving from
a command-at-a-time shell toward a lightweight project/case workspace for
security and diagnostic work.

The goal is not to become a full project manager, ticket tracker, or notes app.
The goal is to help an operator keep related commands, findings, snapshots,
workspace files, targets, and exportable evidence together without losing the
speed and directness of the shell.

---

## Guiding Principles

- **Keep the shell primary.** Projects should organize work; they should not make
  running a command feel heavier.
- **Make project linking cheap.** The happy path should be "run command while
  project is active" and have the app link the run, findings, and files
  automatically.
- **Treat projects as case folders.** A project should be the first-class run
  collection/case folder model: related runs, snapshots, findings, files,
  labels, and targets all collect there instead of adding a second grouping
  concept.
- **Prefer links over copies.** Runs, snapshots, findings,
  and workspace files should remain the source records. Projects should link to
  them instead of copying them.
- **Design for evidence packages early.** Notes, labels, findings, files,
  and run history should share enough structure that export/share packages do
  not require a second model later.
- **Keep notes intentionally small.** One project notes document is enough. The
  app should support investigation context, not compete with a real notes app.
- **Treat targets as first-class context.** Domains, URLs, hosts, IPs, CIDRs, and
  port sets should improve filtering, findings review, autocomplete, and
  workflows.
- **Make privacy boundaries explicit.** Project sharing/export needs clear raw
  vs redacted behavior, session ownership behavior, and file inclusion rules.

---

## Roadmap Overview

| Phase | Theme | Complexity | Outcome |
|-------|-------|------------|---------|
| 0 | Preconditions and safety fixes | Low-Medium | Clearer privacy/session behavior before larger organization features build on it |
| 1 | Project data model | Medium | Users can create projects and manually associate runs, snapshots, and files |
| 2 | Project-aware shell flow | Medium | Active project context automatically captures new runs and generated artifacts |
| 3 | Run-created file artifacts | Medium | Command-created outputs are associated with their source runs and active projects |
| 4 | Targets and autocomplete context | Medium | Projects can own domains, URLs, hosts, and port sets that feed filtering and suggestions |
| 5 | Findings, labels, and annotations | Medium-High | Findings, runs, snapshots, and files can be reviewed, labeled, annotated, and filtered by project |
| 6 | Project notes | Low-Medium | Each project gets one lightweight notes document |
| 7 | Share/export packages | High | Runs, snapshots, findings, annotations, files, and notes can be packaged together |
| 8 | Workflow and comparison layer | High | Projects become useful for repeatable workflows, baselines, and drift comparison |
| 9 | Polish, mobile, and operations | Medium | Project work is smooth across desktop, mobile, diagnostics, and retention paths |

---

## Phase 0: Preconditions And Safety Fixes

These are not the project features themselves. They reduce ambiguity before
projects become another session-scoped persistence layer.

### P0.1 Clarify Session And Permalink Boundaries

- Keep `/history/<run_id>` as an implicit bearer permalink for the current
  history/share model; a user with the copied run URL can view that run without
  the original session identity.
- Treat run IDs in copied links as bearer secrets and consider moving future
  sharing toward explicit snapshot/package creation when project export exists.
- Preserve session ownership checks for history listing, deletion, active-run
  recovery, and kill actions.
- Validate anonymous session IDs server-side instead of accepting arbitrary
  non-`tok_` strings.
- Review `/kill` ownership checks so a run ID alone is not the only authorization
  input if active-run ownership metadata is available.
- Add route tests for invalid anonymous session IDs, cross-session history
  access, and cross-session kill attempts.

### P0.2 Stabilize History Search Semantics

- Fix short history queries so default history search still searches stored
  output, not command text only.
- Add tests for short output-only searches such as `80`, `OK`, `CVE`, and status
  codes that do not appear in the command text.

### P0.3 Inventory Existing State Ownership

- Document the current owner and retention behavior for:
  - runs
  - full-output artifacts
  - snapshots
  - starred commands
  - session variables
  - session preferences
  - workspace files
  - signal metadata / findings
- Identify which records are session-scoped, which are shareable, and which can
  move or link into projects.

---

## Phase 1: Project Data Model

Goal: introduce projects as durable case folders
without changing how command execution works yet.

### P1.1 Core Project Schema

Add a small set of durable project tables:

- `projects`
  - `id`
  - `session_id`
  - `name`
  - `slug` or short display key
  - `description`
  - `status` such as `active`, `archived`
  - `created`
  - `updated`
  - optional `color` or visual accent
- `project_links`
  - `project_id`
  - `entity_type` such as `run`, `snapshot`, `workspace_file`, `finding`
  - `entity_id` or stable path key
  - `created`
  - optional `source` such as `manual`, `active_project`, `target_match`,
    `artifact_capture`
- indexes by `session_id`, `project_id`, `entity_type`, and entity lookup.

Design notes:

- This is the implementation home for the "run collections / case folders"
  idea. A project is the named investigation/case folder that groups related
  runs, snapshots, findings, workspace files, artifacts, targets, notes, and
  future packages.
- Prefer a generic link table for early flexibility, but keep constraints and
  helper functions strict so invalid entity types do not spread through the app.
- Keep runs/snapshots/files usable outside projects.
- Allow one entity to belong to multiple projects unless there is a strong reason
  to enforce one project only. Multi-project linking is useful for shared
  infrastructure, retests, and portfolio-wide findings.

### P1.2 Project CRUD API

- Add routes for listing, creating, renaming, archiving, and deleting projects.
- Add routes for linking and unlinking runs, snapshots, and workspace files.
- Deleting a project should remove project links and project metadata, not delete
  underlying runs/snapshots/files by default.
- Add a separate destructive option later for "delete project and linked data" if
  it proves useful.

### P1.3 Minimal Project UI

- Add a desktop project selector near the existing shell chrome.
- Add a mobile project selector in the menu sheet.
- Add a project drawer or modal with:
  - project list
  - create project
  - rename/archive
  - linked runs
  - linked snapshots
  - linked files
- Add project filter chips to the history drawer and mobile recents/history view.

### P1.4 Terminal Built-ins

Add lightweight terminal commands:

- `project`
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

Terminal support matters because users should be able to stay in shell flow.

---

## Phase 2: Project-Aware Shell Flow

Goal: make project capture feel automatic once the user chooses an active project.

### P2.1 Active Project Context

- Persist the active project per session preference.
- Show active project in desktop HUD or tabbar without crowding the command
  prompt.
- Show active project in mobile menu/header.
- Include active project context in run history rows and restored tabs.
- Add `project clear` to leave project context without deleting anything.

### P2.2 Auto-Link New Runs

- When a command runs while a project is active, link the resulting run to that
  project.
- Store the link source as `active_project`.
- Ensure client-side built-in commands saved through `/run/client` follow the
  same project-link path when appropriate.
- Decide whether purely local UI commands such as `theme set` and `config set`
  should be excluded from project linking by default.

### P2.3 Project-Aware Snapshots

- When a snapshot is created from a tab whose run/project context is known, link
  the snapshot to that project.
- Allow the share prompt to show project context and choose whether the snapshot
  should remain project-linked.
- Add history filters for "snapshots in project."

### P2.4 Project-Aware Files

- Allow users to link existing workspace files to a project directly.
- Show project-linked files in the project view.
- Keep workspace file storage session-scoped at first; project file links should
  reference the current session workspace path.
- Add a migration note for session-token changes: project file links must remain
  valid when workspace files migrate between session identities.

---

## Phase 3: Run-Created File Artifacts

Goal: connect command-created outputs to the run that produced them and,
transitively, to the active project.

### P3.1 Artifact Manifest

Add a durable `run_file_artifacts` or generic artifact table:

- `id`
- `session_id`
- `run_id`
- `workspace_path`
- `display_name`
- `kind` such as `input`, `output`, `database`, `report`, `unknown`
- `byte_size`
- `created`
- `detected_by` such as `declared_flag`, `workspace_diff`, `manual`
- optional `content_type` / `preview_type`

### P3.2 Declared Output Flags

- Extend `commands.yaml` workspace metadata so selected flags can be marked as
  output-producing.
- Examples:
  - `nmap -oN result.txt`
  - `nmap -oX result.xml`
  - `ffuf -o out.json`
  - `nuclei -json-export findings.json`
  - `httpx -o urls.txt`
- When command validation rewrites a workspace output flag, record the
  user-facing path as an expected artifact for the run.

### P3.3 Workspace Diff Capture

- For commands where output files are not declared up front, optionally compare
  workspace file state before and after a run.
- Record newly created or modified files as candidate run artifacts.
- Be conservative: avoid treating every temp/cache file as evidence.
- Start with declared output flags first; add workspace diff capture only after
  artifact UX exists.

### P3.4 Artifact UI

- Show run-created artifacts on:
  - run history rows
  - restored run tabs
  - run permalink pages
  - project detail view
  - Files panel
- Add actions:
  - view
  - download
  - link/unlink project
  - include/exclude from export package
- Add tests for generated artifact association, project transitive association,
  and session-token workspace migration.

---

## Phase 4: Project Targets

Goal: let a project own target context that improves autocomplete, filtering, and
findings organization.

### P4.1 Target Schema

Add project target records:

- `project_targets`
  - `id`
  - `project_id`
  - `type` such as `domain`, `url`, `host`, `ip`, `cidr`, `port_set`
  - `value`
  - `label`
  - `notes`
  - `created`
  - `updated`
  - optional `source_run_id`
  - optional `confidence`

Port sets should support named reusable values:

- `web`: `80,443,8080,8443`
- `common_tcp`: maybe an app default
- custom sets: `22,80,443,3389`

### P4.2 Target Management UI

- Add a Targets section to the project view.
- Allow add/edit/delete for domains, URLs, hosts, IPs, CIDRs, and port sets.
- Support quick-add from selected transcript text, findings, history rows, and
  workspace file previews.
- Support import from newline-delimited text files.

### P4.3 Autocomplete From Project Targets

- When a project is active, suggest project targets in command argument slots.
- Suggest `$PROJECT_DOMAIN`, `$PROJECT_URL`, or project variable-style values
  without forcing users to manually create session variables.
- For port-aware flags such as `-p`, suggest project port sets.
- For URL-aware commands, prefer URL targets; for DNS commands, prefer domains;
  for port scanners, prefer hosts/IPs/CIDRs.
- Keep suggestions visibly scoped so users know they came from the active
  project.

### P4.4 Automatic Target Association

- Infer target references from commands and signal metadata where reliable.
- Link runs/findings/snapshots to project targets when:
  - the run command contains a known target
  - finding metadata names a known target
  - a snapshot contains linked runs with known targets
- Use a confidence/source field so inferred links can be shown differently from
  manual links.

---

## Phase 5: Findings, Labels, And Annotations

Goal: make findings and important runs reviewable project records instead of
transient signal counts or one-off starred history rows.

### P5.1 Persist Finding Records

The current signal metadata is line-oriented and useful in the active transcript.
Add a durable finding model when the classifier identifies high-signal output:

- `findings`
  - `id`
  - `session_id`
  - `run_id`
  - optional `project_id` through `project_links`
  - optional `target_id`
  - `scope` such as `finding`, `warning`, `error`, `summary`
  - `title` or normalized summary
  - `raw_line`
  - `line_number`
  - `severity` when known
  - `fingerprint` for de-duplication
  - `created`

Start simple: persist enough to power project filtering and annotations. Avoid
building a vulnerability-management system too early.

### P5.2 Finding Review States

Add lightweight review state:

- `new`
- `reviewed`
- `important`
- `false_positive`
- `needs_followup`
- `accepted_risk` maybe later, if the app drifts toward reporting

Support filtering by state in the project findings view.

### P5.3 Run Labels And History Bookmarks

Add richer saved-state labels for runs so "starred" is not the only bookmark
state:

- `baseline`
- `finding`
- `follow-up`
- `customer-facing`
- `interesting`
- `retest`

Suggested storage:

- Start with a generic label/bookmark table if it stays simple:
  - `id`
  - `session_id`
  - `entity_type` such as `run`, `snapshot`, `finding`, `workspace_file`
  - `entity_id`
  - `label`
  - `source` such as `terminal`, `history_ui`, `project_view`, `package_flow`
  - `created`
- Keep the existing star as either:
  - a compatibility flag on runs, or
  - a special label rendered as the familiar star affordance.

UI and shell behavior:

- Add label chips to history rows, restored runs, project run lists, compare
  summaries, and package builders.
- Add label filters to history and project views.
- Keep labels short and operator-controlled; avoid building a full tag manager
  in the first pass.
- Add terminal-native labeling:
  - `tag <label>` attaches a label to the most recent completed run.
  - `tag run <run-id> <label>` labels a specific run.
  - `tag remove ...` or a history/project UI action removes labels.
- Labeling from the terminal should be the fast path; the history drawer and
  project view should make labels visible, filterable, and editable.

Project behavior:

- Project runs can be filtered by label.
- Labels should feed comparison and export flows:
  - `baseline` runs become compare candidates.
  - `finding` / `customer-facing` runs become package candidates.
  - `follow-up` / `retest` labels help drive project next-action views.

### P5.4 Annotations

Add annotations that can attach to:

- findings
- runs
- snapshots
- workspace files / artifacts
- project targets

Suggested annotation fields:

- `id`
- `session_id`
- `entity_type`
- `entity_id`
- `body`
- `visibility` such as `private`, `package`
- `created`
- `updated`
- optional `author_label`

Rules:

- Annotations are short comments, not full documents.
- Annotations are private by default.
- Share/export package flow chooses which annotations to include.

### P5.5 Project Findings View

- Add a project-level findings timeline/table.
- Filter by:
  - target
  - run
  - command root
  - severity/scope
  - review state
  - run label/bookmark
  - annotated/unannotated
- Allow opening the original run at the matched line.
- Allow creating a snapshot or package from selected findings.

### P5.6 Output Navigation Improvements

Fold the old "better output navigation" idea into findings work:

- Jump between findings/warnings/errors/summaries.
- Add a "next unreviewed finding" action.
- Keep search scopes and signal chips aligned with persisted finding state.
- Consider sticky command headers for long runs.
- Defer collapsing noisy sections until finding navigation is solid.

---

## Phase 6: Project Notes

Goal: give each project one small notes surface for operator context.

### P6.1 Notes Storage

Use one notes field or one managed notes file per project:

- Option A: `projects.notes` text column.
- Option B: a reserved workspace-backed file such as `.darklab/project-notes.md`
  linked to the project.

Prefer Option A unless there is a strong reason to expose the notes as a normal
workspace file. It is simpler for export, permissions, migration, and retention.

### P6.2 Notes UI

- Add a Notes tab/section inside the project view.
- Support plain text or a narrow safe Markdown subset.
- Autosave with clear saved/error state.
- Keep it deliberately small:
  - no nested pages
  - no backlinks
  - no rich editor
  - no task management beyond simple text

### P6.3 Notes In Packages

- Share/export packages should offer:
  - include project notes
  - exclude project notes
  - include selected excerpt maybe later
- Default should probably be exclude or prompt, because notes may contain private
  operator context.

---

## Phase 7: Share And Export Packages

Goal: package evidence from snapshots, runs, and projects into coherent shareable
or downloadable artifacts.

### P7.1 Package Model

Add a package concept that can be created from:

- one snapshot
- one run
- selected runs
- selected findings
- one project

Package contents can include:

- title
- summary
- project metadata
- targets
- run list
- selected raw outputs or output excerpts
- findings
- annotations
- project notes
- workspace artifacts
- redaction mode
- creation timestamp
- source session/project IDs

### P7.2 Package Builder UI

- Add "Create package" from:
  - active tab
  - history row
  - snapshot row
  - project view
  - findings selection
- Builder choices:
  - raw vs redacted
  - include/exclude notes
  - include/exclude private annotations
  - include full output vs preview vs findings-only
  - include selected files/artifacts
  - include target inventory
  - include command metadata and timings
- Show a redaction preview for high-risk strings before public sharing.

### P7.3 Export Formats

Initial:

- HTML package
- ZIP package containing:
  - `index.html`
  - `manifest.json`
  - raw or redacted text outputs
  - included workspace files
  - findings JSON

Later:

- PDF report
- Markdown report
- JSONL evidence export

### P7.4 Share Lifecycle Controls

- Expiring package links.
- Optional one-time reveal for sensitive packages.
- Delete/revoke package.
- Show package access/lifecycle metadata in history/project views.
- Log package creation/deletion/access events through structured logging.

### P7.5 Package Privacy Tests

Add real-browser tests for:

- redacted package pages do not render secrets
- raw package pages preserve selected content
- downloaded HTML/ZIP contents match redaction choices
- project notes and private annotations are excluded unless explicitly included
- artifact inclusion respects user choices

---

## Phase 8: Project Workflows, Presets, And Comparison

Goal: use projects to make repeated investigation work easier without replacing
the raw shell.

### P8.1 Saved Command Templates

- Let users save named command templates.
- Templates can reference project targets and port sets.
- Example templates:
  - `curl -I $PROJECT_URL`
  - `nmap -sV -p $PROJECT_PORTS $PROJECT_HOST`
  - `ffuf -u $PROJECT_URL/FUZZ -w /usr/share/wordlists/seclists/...`
- Keep every template editable as raw shell text before running.

### P8.2 Workflow Replay And Promotion

- Allow selecting a sequence of history runs and promoting them to a reusable
  workflow.
- Let workflows optionally bind to project targets.
- Track workflow progress inside a project:
  - not started
  - current step
  - completed steps
  - skipped steps
  - run IDs produced by each step
- Keep auto-run off by default; prefill commands one step at a time.

### P8.3 Command Forms From Structured Catalog

- Build optional forms from the existing autocomplete/command registry model.
- Avoid a parallel schema for forms.
- Forms should render common flags, arguments, workspace inputs/outputs, target
  pickers, and port-set pickers.
- The raw command remains visible and editable.

### P8.4 Run Comparison And Baselines

- Let users mark project runs as baselines.
- Compare a run against:
  - previous run of same command
  - project baseline
  - selected snapshot
  - selected package artifact
- Initial comparison:
  - added/removed lines
  - exit code changes
  - duration changes
  - finding count changes
- Later comparison:
  - open-port/service diffs
  - URL/status-code diffs
  - certificate expiry/trust diffs
  - subdomain added/removed diffs

### P8.5 Suggested Next Actions

- Based on project targets and findings, suggest next commands or workflows.
- Keep suggestions modest and transparent:
  - "Run TLS check on URLs with HTTPS"
  - "Run service triage against hosts with open 80/443"
  - "Create package from 4 important findings"
- Do not make the app feel like an opaque scanner automation engine.

---

## Phase 9: Mobile, Operations, And Retention Polish

Goal: make project work practical in the real surfaces operators already use.

### P9.1 Mobile Project Ergonomics

- Project selector in the mobile menu.
- Project detail as a mobile sheet.
- Quick link current run/snapshot/file to project.
- Findings review sheet optimized for one-handed use.
- Package creation flow that works without desktop-only affordances.

### P9.2 Bulk Operations

- Multi-select history rows and findings.
- Bulk link/unlink to project.
- Bulk annotate maybe only as a shared tag/state.
- Bulk export/package.
- Bulk delete with project-aware confirmation copy.

### P9.3 Retention And Storage Awareness

- Project view should show when linked runs or artifacts are near retention
  pruning.
- Decide whether project-linked runs/packages should be retained longer or simply
  warn before pruning.
- Show project storage usage:
  - run output artifacts
  - workspace files
  - package files
- Add config for project/package retention if needed.

### P9.4 Diagnostics And Audit Trail

- Add project counts to `/diag`:
  - projects
  - project-linked runs
  - annotations
  - packages
  - artifact bytes
- Add structured events:
  - `PROJECT_CREATED`
  - `PROJECT_ARCHIVED`
  - `PROJECT_LINK_ADDED`
  - `PROJECT_LINK_REMOVED`
  - `ANNOTATION_CREATED`
  - `PACKAGE_CREATED`
  - `PACKAGE_DELETED`
  - `PACKAGE_VIEWED`

### P9.5 Documentation And Onboarding

- Update `FEATURES.md` with the project model once Phase 1 lands.
- Update `ARCHITECTURE.md` with schema, route, migration, retention, and package
  lifecycle details.
- Add FAQ entries:
  - What is a project?
  - Are project notes shared?
  - How do raw vs redacted packages work?
  - What happens to project files when I rotate a session token?
- Add a small welcome hint only after projects are useful enough to introduce.

---

## Optional Enhancements To Consider

These fit the model, but should not block the core roadmap.

### Project Import

- Create a project from a list of domains/URLs.
- Import targets from workspace files.
- Import findings from supported tool JSON outputs.

### Project Templates

- Template project types:
  - DNS investigation
  - external surface review
  - web app triage
  - TLS/certificate review
  - service exposure baseline
- Templates could pre-create target categories, port sets, saved command
  templates, and recommended workflows.

### Evidence Quality Checks

- Warn when a package includes findings without raw supporting output.
- Warn when annotations reference files that are not included.
- Warn when output was truncated and full artifact is unavailable.
- Warn when package redaction rules changed since the source snapshot/run.

### Lightweight Tags

- Tags can attach to projects, runs, findings, snapshots, files, and packages.
- Consider whether tags are truly needed once projects, targets, review states,
  and annotations exist.
- Avoid building a complicated tag manager too early.

### Target Extraction

- Extract candidate domains, URLs, IPs, CVEs, and ports from output.
- Let users approve extracted targets into the active project.
- Use extraction to improve autocomplete and findings grouping.

### Collaboration Later

- Author labels on annotations.
- Package preparer/reviewer labels.
- Project handoff export/import.
- Do not build real multi-user permissions unless the app grows an actual auth
  model.

---

## Deferred Or Explicitly Out Of Scope For Now

- Full note-taking system with multiple pages, backlinks, or rich editing.
- Issue tracker or task board.
- Multi-user RBAC.
- Automatic vulnerability scanner orchestration that runs large workflows without
  operator review.
- Full interactive PTY mode.
- Full reconnectable live stream. Still valuable, but separate from the project
  workspace model.
- Plugin-style helper command registry. Revisit when command/built-in command
  internals need it, not as part of projects.

---

## Suggested Implementation Order

1. Fix Phase 0 privacy/search preconditions.
2. Add project schema and API without UI fanfare.
3. Add minimal project selector and manual linking.
4. Add active project auto-linking for new runs.
5. Add project-linked workspace files.
6. Add declared output artifact capture for a few high-value tools.
7. Add project targets and autocomplete suggestions.
8. Persist findings and add annotation support.
9. Add run labels/history bookmarks and terminal `tag <label>`.
10. Add project notes.
11. Build package export around the already-linked data.
12. Add workflow replay, baselines, and comparison after project data is real.

This order keeps each phase useful on its own while avoiding the scary version
where everything must exist before anything works.
