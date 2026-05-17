# Architecture

This document explains how darklab_shell is put together today: runtime boundaries, request flow, browser code, backend code, persistence, observability, and tests.

For the architectural rationale, tradeoffs, and implementation-history notes behind those structures, see [DECISIONS.md](DECISIONS.md).

---

## Table of Contents

- [System Overview](#system-overview)
- [System Structure](#system-structure)
- [Request Flow Walkthroughs](#request-flow-walkthroughs)
- [HTTP Route Inventory](#http-route-inventory)
- [Frontend](#frontend)
- [Back-end Architecture](#back-end-architecture)
- [Run Lifecycle](#run-lifecycle)
- [Secrets and Vault](#secrets-and-vault)
- [Intel and Provider Integrations](#intel-and-provider-integrations)
- [Session Workspace and Files](#session-workspace-and-files)
- [Projects Workspace](#projects-workspace)
- [Atlas and Entity Model](#atlas-and-entity-model)
- [State And Persistence](#state-and-persistence)
- [Observability And Diagnostics](#observability-and-diagnostics)
- [Security Model](#security-model)
- [Configuration Surfaces](#configuration-surfaces)
- [Theme System](#theme-system)
- [Test Suite](#test-suite)
- [Related Docs](#related-docs)

---

## System Overview

darklab_shell is a web-based shell for running network diagnostics and vulnerability scanning commands against remote targets. It uses Flask + Gunicorn on the backend, a classic-script browser frontend, SQLite by default or Postgres for larger deployments, Redis for shared live-run state, and SSE for live output.

At a high level, it works like this:

- The browser loads a Flask-rendered shell page, then fetches focused startup data from routes such as `/config`, `/themes`, `/faq`, `/autocomplete`, and `/welcome*`.
- Command execution starts with `POST /runs` and streams through replayable `/runs/<run_id>/stream` SSE subscriptions. The backend validates and rewrites commands, handles app-native built-ins, starts isolated scanner subprocesses when needed, and publishes output events.
- Redis stores shared state that must work across multiple Gunicorn workers: rate limits, active run PID tracking for `/kill`, production run-broker replay, and interactive PTY event/control streams.
- The configured database stores completed run metadata, preview output, snapshots, and full-output file metadata so history and share links survive restarts.
- The browser client has no build step. Classic scripts share one global runtime, and browser cookies/storage handle local continuity around session identity, preferences, and reload restore.
- The Docker runtime uses two unprivileged users: Gunicorn runs as `appuser`, while user-submitted commands run as `scanner` with the shared `appuser` group. That group lets validated session workspace files stay group-readable or group-writable without making them world-readable.

The rest of this document is organized by concern rather than file order: system structure first, then browser/backend composition, then core runtime flows such as run lifecycle, state, observability, and security.

---

## System Structure

Start here for the stable big-picture views before the doc dives into request flow, browser behavior, and persistence details.

### Logical Runtime Layers

```mermaid
flowchart TB
  User["Browser User"]

  subgraph Client["Browser Runtime"]
    Templates["HTML templates + CSS theme vars"]
    JS["Vanilla JavaScript UI/state"]
    BrowserApis["Cookies · localStorage · sessionStorage · fetch · SSE"]
  end

  subgraph App["Python Web Application"]
    Flask["Flask + Gunicorn"]
    Routing["HTTP routes + template rendering"]
    Orchestration["Validation + built-in command handling + run orchestration"]
  end

  subgraph Runtime["Execution + Persistence Services"]
    Redis["Redis"]
    Database["SQLite/Postgres"]
    Artifacts["Full-output artifacts"]
    Subprocesses["Scanner subprocesses"]
    Config["YAML config + theme files"]
  end

  User --> Client
  Client -->|HTTP + SSE| Flask
  Templates --> JS
  JS --> BrowserApis
  Flask --> Routing
  Routing --> Orchestration
  Flask <--> Redis
  Flask <--> Database
  Flask <--> Artifacts
  Flask --> Subprocesses
  Flask <--> Config
```

This diagram is intentionally about runtime layers rather than individual modules. It answers “which layer owns which responsibility?” without duplicating the more detailed diagrams later in the doc.

- the browser owns rendering, local interaction state, and web APIs such as cookies, `localStorage`, `sessionStorage`, `fetch`, and SSE reads
- the Python web app owns routing, template rendering, config/theme loading, request validation, built-in command handling, and real command setup
- Redis owns the cross-worker coordination that cannot safely live inside one Gunicorn worker process
- The configured database and output files own the run/share state that must survive reloads and restarts
- scanner subprocesses are a distinct execution boundary rather than an in-process extension of the Flask app
- YAML config and theme files are shown separately because they shape both backend behavior and frontend presentation, even though they load from the local filesystem rather than over the network

This section should stay stable even when app modules, blueprints, or frontend files move around. The sections below cover those app-level pieces directly.

### Runtime Topology

```mermaid
flowchart TB
  Browser["Browser UI"]
  Flask["Flask + Gunicorn"]
  Redis["Redis"]
  Database["SQLite/Postgres"]
  Artifacts["Artifacts"]
  Scanner["Scanner subprocesses"]

  Browser -->|HTTP bootstrap reads| Flask
  Browser -->|HTTP POST /runs + SSE stream| Flask
  Browser -->|HTTP POST /kill| Flask
  Browser -->|HTTP history/share/diag reads| Flask

  Flask <--> |Redis protocol| Redis
  Flask <--> |SQL reads/writes| Database
  Flask <--> |filesystem artifact I/O| Artifacts
  Flask -->|spawn / signal process groups| Scanner
```

This is the transport and boundary view. It focuses on stable communication paths rather than the internal modules that implement them.

- browser traffic is plain HTTP plus one-way SSE streaming for live command output
- Redis is used for shared worker coordination and brokered active-run event replay, not as a general application datastore
- The configured database and output files are the durable history/share boundary
- command execution remains out-of-process, which keeps the Flask worker lifecycle separate from tool execution

---

## Request Flow Walkthroughs

```mermaid
sequenceDiagram
  participant B as Browser
  participant C as content/history/assets routes
  participant R as /runs + /kill
  participant X as Redis
  participant P as scanner process
  participant D as DB + artifacts

  B->>C: GET / + startup content routes
  C-->>B: HTML + config/theme/FAQ/autocomplete/welcome payloads

  B->>R: POST /runs
  R->>X: register run_id -> pid
  R->>P: spawn built-in command or real process
  R->>X: publish started/output/exit events
  B->>R: GET /runs/<run_id>/stream
  R-->>B: replay + live SSE events
  R->>D: save preview and metadata
  R->>D: save full artifact when enabled

  B->>R: POST /kill
  R->>X: getdel pid
  R->>P: kill process group

  B->>C: GET /history /history/active /share /diag
  C->>D: read run/snapshot/usage state
  C-->>B: JSON or themed HTML
```

There are three core request classes:

- content/bootstrap reads
- run/kill lifecycle
- history/share/diagnostic reads

`/history/active` is part of that third class. It exposes only the current session's in-flight run metadata so the browser can rebuild running tabs after a reload, keep kill available, render the submitted command as a normal prompt line, and subscribe back to `/runs/<run_id>/stream` for replay plus live output. Active-run metadata includes a browser-level origin identity (`owner_client_id`), the originating terminal tab id (`owner_tab_id`), and `owner_last_seen` liveness so the same session token can be open on a laptop and phone without the second browser automatically creating terminal tabs for live commands it did not start. If the origin is another live client, Status Monitor can attach a local tab to the broker stream on demand. Session membership is the process-control boundary: any browser using the same session token that can see the run can explicitly kill it, and subscribed peers receive a broker `killed` event such as `[killed by another browser]`. Non-running tabs and drafts are restored separately from browser `sessionStorage`, which keeps the reload path split cleanly between browser-owned idle state and server-owned active-run state.

That split is reflected directly in the blueprint structure.

---

## HTTP Route Inventory

This route list belongs in the architecture document because it describes the application surface that contributors maintain, not the operator workflow.
Methods below list the routes declared by the app; Flask may add automatic `HEAD` and `OPTIONS` handling for those routes.
The `/static/<path:filename>` row is included even though Flask registers it automatically rather than through a blueprint decorator.

### Content And Bootstrap Routes

| Method | Endpoint | Description |
| -------- | ---------- | ------------- |
| `GET` | `/` | Serves the Flask-rendered shell UI, frontend bootstrap config, active theme CSS variables, and initial rail state. |
| `GET` | `/config` | Returns browser-facing runtime config derived from `config.yaml` and `config.local.yaml`. |
| `GET` | `/themes` | Returns the active theme plus the complete theme registry used by the Options modal. |
| `GET` | `/allowed-commands` | Returns the allowed command prefixes grouped from `commands.yaml` for command reference surfaces. |
| `GET` | `/commands/catalog` | Returns compact command registry entries for the Command Registry modal and sheet. |
| `GET` | `/commands/catalog/<root>` | Returns the app-native command reference payload for one supported external command root. |
| `GET` | `/commands/catalog/<root>/<subcommand>` | Returns a subcommand-scoped command reference payload when the registry has subcommand metadata. |
| `GET` | `/faq` | Returns built-in FAQ entries plus custom `faq.yaml` entries, including their display sections. |
| `GET` | `/workflows` | Returns current-session user workflows followed by built-in and custom `workflows.yaml` entries, filtered by feature gates such as Files/workspace support. |
| `GET` | `/shortcuts` | Returns the keyboard shortcut reference used by the `shortcuts` built-in and the browser overlay. |
| `GET` | `/autocomplete` | Returns merged external-command and app-owned built-in autocomplete context, built-in command roots, and special command keys. |
| `GET` | `/welcome` | Returns welcome command samples from `welcome.yaml`. |
| `GET` | `/welcome/ascii` | Returns the desktop welcome ASCII banner from `ascii.txt` as plain text. |
| `GET` | `/welcome/ascii-mobile` | Returns the mobile welcome ASCII banner from `ascii_mobile.txt` as plain text. |
| `GET` | `/welcome/hints` | Returns rotating desktop welcome footer hints from `app_hints.txt`. |
| `GET` | `/welcome/hints-mobile` | Returns rotating mobile welcome footer hints from `app_hints_mobile.txt`. |

### Run Lifecycle Routes

| Method | Endpoint | Description |
| -------- | ---------- | ------------- |
| `POST` | `/runs` | Validates, expands session variables, rewrites, starts brokered execution, and returns the run id plus stream URL. |
| `GET` | `/runs/<run_id>/stream` | Replays brokered events and follows live output over SSE for a current-session run. |
| `GET` | `/runs/<run_id>/events` | Returns bounded brokered event backfill for tests and non-SSE clients. |
| `POST` | `/pty/runs` | Starts a config-gated interactive PTY run for an allowlisted screen tool and returns the PTY run id plus stream URL. |
| `GET` | `/pty/runs/<run_id>/snapshot` | Returns a terminal snapshot, dimensions, and resume event id for active PTY reattach. |
| `GET` | `/pty/runs/<run_id>/stream` | Streams bounded PTY output events over SSE for the owning session. |
| `POST` | `/pty/runs/<run_id>/input` | Sends bounded keyboard or paste input to an active interactive PTY run. |
| `POST` | `/pty/runs/<run_id>/resize` | Applies browser terminal row/column changes to an active interactive PTY run. |
| `POST` | `/run/client` | Persists allowlisted browser-owned built-in output, such as client-side theme/session commands, as normal run history. |
| `POST` | `/kill` | Kills an active process group by `run_id` and clears active-run tracking. |

### History And Share Routes

| Method | Endpoint | Description |
| -------- | ---------- | ------------- |
| `GET` | `/history` | Returns paginated current-session history items with run/snapshot/run-subtype filters, linked-run project filters, command/output search, starred-only filtering, labels/notes, and command-root summaries. |
| `DELETE` | `/history` | Deletes all run history for the current session and removes matching full-output artifacts. |
| `POST` | `/history/bulk-delete` | Deletes selected completed current-session runs, returning per-run results while rejecting running or missing runs without failing the whole request. |
| `GET` | `/history/commands` | Returns newest distinct command strings for prompt history, desktop recents, and mobile recents. |
| `GET` | `/history/stats` | Returns compact current-session counters for the Status Monitor dashboard. |
| `GET` | `/history/insights` | Returns compact visual history data for Status Monitor constellation, heatmap, ticker, and command mix widgets. |
| `GET` | `/history/active` | Returns active-run metadata and telemetry for reload recovery and the Status Monitor. |
| `GET` | `/history/<run_id>/compare-candidates` | Returns ranked previous current-session runs for the History drawer's compare launcher. |
| `GET` | `/history/compare` | Compares two current-session runs, optionally scoped by `project_id` / `baseline_label`, and returns metadata deltas, bounded output hunks, totals, limits, and finding/artifact object diffs. |
| `GET` | `/history/compare/lines` | Returns bounded filtered-output slices for lazy expansion of folded comparison hunks, using `left`/`right` run ids, `side`, `start`/`end`, and optional `project_id` scoping. |
| `GET` | `/history/<run_id>` | Serves an implicit-bearer styled run permalink, or raw JSON with `?json`; uses full-output artifacts when available unless `?preview=1` is set. |
| `GET` | `/history/<run_id>/atlas-cleanup-preview` | Previews non-curated Atlas rows that can be removed with a run delete. |
| `DELETE` | `/history/<run_id>` | Deletes one current-session run and its matching full-output artifact; `prune_atlas=1` also removes non-curated Atlas rows only linked to that run. |
| `POST` | `/share` | Saves a tab snapshot, omits raw-only intel response bodies, optionally applies share redaction, and returns a snapshot permalink URL. |
| `POST` | `/share/bulk-delete` | Deletes selected current-session snapshot permalinks, returning per-snapshot results without failing the whole request. |
| `GET` | `/share/<share_id>` | Serves a styled snapshot permalink, or raw JSON with `?json`. |
| `DELETE` | `/share/<share_id>` | Deletes one current-session snapshot permalink. |

Run comparison applies bounded transcript-diff caps before returning hunk payloads:
`COMPARE_MAX_CHANGED_LINES` limits emitted changed-line units to 2,000,
`COMPARE_MAX_HUNKS` limits emitted change blocks to 3,000,
`COMPARE_INLINE_EQUAL_CONTEXT` inlines three equal context lines on each side of a change,
`COMPARE_LINE_DISPLAY_TRUNCATE` caps displayed line text at 4,000 characters with client-side expansion,
`COMPARE_LAZY_EQUAL_PAGE_LIMIT` pages folded equal regions at 5,000 lines, and
`COMPARE_LAZY_EQUAL_BYTE_LIMIT` caps each lazy equal-region page at 512,000 UTF-8 bytes.
Replace-line pairing is bounded by `COMPARE_REPLACE_PAIR_CANDIDATES` (32 nearest candidate lines)
and accepts pairs at `COMPARE_REPLACE_PAIR_MIN_RATIO` (0.5), with a matching
`COMPARE_REPLACE_PAIR_QUICK_RATIO` prefilter to avoid expensive full similarity checks when the
cheap upper bound is already below the threshold. Transcript hunks preserve source output order.
Finding and artifact object diffs are intentionally order-insensitive: finding keys normalize
stored `raw_line` / `title` text with fingerprint fallback, while artifact keys prefer
`content_sha256`, then workspace path, then artifact id.

### Atlas Routes

| Method | Endpoint | Description |
| -------- | ---------- | ------------- |
| `GET` | `/atlas` | Returns current-session Atlas entity counts by entity type, honoring the orphan-source filter. |
| `GET` | `/atlas/entities` | Returns a paginated current-session entity list, with optional `type`, text search, project, orphan-source, limit, and offset parameters. |
| `GET` | `/atlas/entities/export` | Downloads current-session Atlas entity rows as CSV or JSONL, honoring optional type, text, project, orphan-source, and limit filters. |
| `GET` | `/atlas/entities/<entity_id>` | Returns one current-session entity with source runs, labels, notes, project links, cached intel snapshots, and related findings. |
| `POST` | `/atlas/entities/bulk-delete` | Deletes selected current-session Atlas entities and any findings attached to those entities. |
| `GET` | `/atlas/entities/<entity_id>/delete-preview` | Previews related Atlas cleanup before deleting an entity. |
| `DELETE` | `/atlas/entities/<entity_id>` | Deletes one Atlas entity and its attached findings, with optional same-source cleanup for non-curated siblings. |
| `GET` | `/atlas/findings` | Returns the paginated Atlas Findings queue with optional text, project, review-state, orphan-source, limit, and offset filters. |
| `POST` | `/atlas/findings/review` | Bulk-updates the review state for selected current-session findings. |
| `POST` | `/atlas/findings/bulk-delete` | Deletes selected current-session Atlas findings. |
| `GET` | `/atlas/findings/<finding_id>/delete-preview` | Previews same-source cleanup before deleting a finding. |
| `DELETE` | `/atlas/findings/<finding_id>` | Deletes one Atlas finding, with optional same-source cleanup for non-curated siblings. |
| `POST` | `/atlas/entities/<entity_id>/refresh_intel` | Refreshes app-native intel for one current-session entity and stores provider snapshots on the entity. |
| `POST` | `/atlas/entities/<entity_id>/project_links` | Adds an Atlas entity to a project through the shared project-link model. |
| `DELETE` | `/atlas/entities/<entity_id>/project_links/<project_id>` | Removes an Atlas entity from a project. |

### Session Routes

| Method | Endpoint | Description |
| -------- | ---------- | ------------- |
| `GET` | `/session/token/generate` | Generates and stores a new persistent `tok_...` session token. |
| `GET` | `/session/token/info` | Returns the active named token and creation timestamp, or null fields for anonymous sessions. |
| `POST` | `/session/token/revoke` | Revokes a named token so future requests with that token fall back to anonymous session handling. |
| `POST` | `/session/token/verify` | Checks whether a supplied `tok_...` token was issued by this server. |
| `GET` | `/session/recent-values` | Returns current-session recent target values for metadata-gated autocomplete suggestions. |
| `POST` | `/session/recent-values` | Saves normalized recent values for the current session and prunes each value kind to the autocomplete cap. |
| `POST` | `/session/migrate` | Migrates runs, snapshots, starred commands, preferences, command variables, user workflows, project workspace records, recent values, and non-conflicting workspace paths between session IDs. |
| `GET` | `/session/secrets` | Lists encrypted secret names, consumer env bindings, and update timestamps for the current session without returning values. |
| `POST` | `/session/secrets` | Creates or replaces one encrypted current-session secret value. |
| `POST` | `/session/secrets/rotate` | Re-wraps the current session's encrypted secret rows under the active master key. |
| `DELETE` | `/session/secrets/<name>` | Removes one encrypted secret from the current session. |
| `GET` | `/session/preferences` | Returns the current session's normalized saved Options snapshot. |
| `POST` | `/session/preferences` | Persists the current session's normalized saved Options snapshot. |
| `POST` | `/session/tour-seen` | Records that the current session opened the current onboarding tour version. |
| `GET` | `/session/variables` | Returns current session command-variable names and values for autocomplete and runtime refresh. |
| `GET` | `/session/workflows` | Returns current-session user-created workflows. |
| `POST` | `/session/workflows` | Creates a current-session user workflow. |
| `GET` | `/session/workflows/<workflow_id>` | Returns one current-session user workflow. |
| `PUT` | `/session/workflows/<workflow_id>` | Updates one current-session user workflow. |
| `DELETE` | `/session/workflows/<workflow_id>` | Deletes one current-session user workflow. |
| `GET` | `/session/run-count` | Returns uncapped run count plus workspace file, user workflow, and recent-value counts for migration confirmation. |
| `GET` | `/session/starred` | Returns the current session's starred command list. |
| `POST` | `/session/starred` | Adds one command to the current session's starred list. |
| `DELETE` | `/session/starred` | Removes one command, or clears the whole starred list, for the current session. |

### Project Routes

| Method | Endpoint | Description |
| -------- | ---------- | ------------- |
| `GET` | `/projects` | Returns current-session projects, excluding archived projects unless requested. |
| `POST` | `/projects` | Creates a current-session project/case folder. |
| `GET` | `/projects/active` | Returns the current session's active project context, or null when none is set. |
| `POST` | `/projects/active` | Sets the active project context after validating current-session ownership. |
| `DELETE` | `/projects/active` | Clears the active project context for the current session. |
| `GET` | `/projects/<project_id>` | Returns one current-session project. |
| `GET` | `/projects/<project_id>/summary` | Returns one project plus linked-record, package, and derived metadata counts. |
| `PUT` | `/projects/<project_id>` | Updates project display metadata, status, entity-note-backed notes, and slug. |
| `DELETE` | `/projects/<project_id>` | Deletes project metadata and project links without deleting linked source records. |
| `GET` | `/projects/<project_id>/links` | Lists run source records linked into a project. |
| `POST` | `/projects/<project_id>/links` | Links supported current-session runs or Atlas entities into a project. Run-link payloads can also include the run's Atlas entities. |
| `DELETE` | `/projects/<project_id>/links` | Removes supported run or Atlas entity links from a project. Run-unlink payloads can also remove same-run, non-curated Atlas entity links from that project. |
| `POST` | `/projects/<project_id>/links/run-entities/preview` | Counts Atlas entities that can be added with selected run links. |
| `POST` | `/projects/<project_id>/links/run-entities/remove-preview` | Counts same-run, non-curated Atlas entity links that can be removed when selected run links are removed. |
| `GET` | `/projects/<project_id>/targets` | Lists project-scoped targets. |
| `POST` | `/projects/<project_id>/targets` | Adds an idempotent project target. |
| `PUT` | `/projects/<project_id>/targets/<target_id>` | Updates one project target. |
| `DELETE` | `/projects/<project_id>/targets/<target_id>` | Deletes one project target. |
| `GET` | `/projects/<project_id>/packages` | Lists draft evidence package manifests for a project. |
| `POST` | `/projects/<project_id>/packages` | Creates a draft evidence package manifest from current project records, with optional package labels/notes. |
| `GET` | `/projects/<project_id>/packages/<package_id>` | Returns one draft evidence package manifest. |
| `GET` | `/projects/<project_id>/packages/<package_id>/download` | Downloads one draft evidence package archive. |
| `DELETE` | `/projects/<project_id>/packages/<package_id>` | Deletes one draft evidence package manifest. |
| `GET` | `/projects/<project_id>/artifacts/<artifact_id>/preview` | Returns text preview content for one project-linked run artifact. |
| `GET` | `/projects/<project_id>/artifacts/<artifact_id>/download` | Downloads one available project-linked run artifact from the workspace. |
| `GET` | `/projects/<project_id>/findings` | Lists findings reached through project-linked runs or linked Atlas entities, with project filters. |
| `GET` | `/entities/run/<run_id>/findings` | Lists persisted findings captured for a current-session run. |
| `PUT` | `/findings/<finding_id>/review` | Updates the review state for one current-session finding. |
| `GET` | `/entities/<entity_type>/<path:entity_id>/labels` | Lists current-session labels for a supported entity. |
| `POST` | `/entities/<entity_type>/<path:entity_id>/labels` | Adds an idempotent manual label to a supported entity. |
| `DELETE` | `/entities/<entity_type>/<path:entity_id>/labels` | Removes one manual label from a supported entity. |
| `GET` | `/entities/<entity_type>/<path:entity_id>/note` | Returns the current-session note for a supported entity. |
| `PUT` | `/entities/<entity_type>/<path:entity_id>/note` | Creates or replaces the one current-session note for a supported entity. |
| `DELETE` | `/entities/<entity_type>/<path:entity_id>/note` | Deletes the current-session note for a supported entity. |

### Workspace Routes

| Method | Endpoint | Description |
| -------- | ---------- | ------------- |
| `GET` | `/workspace/files` | Returns current-session workspace directories, files, labels/notes, usage, and quota limits. |
| `POST` | `/workspace/files` | Writes a text file into the current session workspace and returns the refreshed workspace payload; file labels/notes are managed through the generic entity metadata routes. |
| `DELETE` | `/workspace/files` | Deletes a file or folder plus matching workspace-file labels/notes from the current session workspace and returns the refreshed workspace payload. |
| `POST` | `/workspace/files/move` | Moves or renames a file or folder inside the current session workspace, moves matching workspace-file labels/notes, and returns the refreshed workspace payload. |
| `POST` | `/workspace/directories` | Creates a current-session workspace directory and returns the refreshed workspace payload. |
| `GET` | `/workspace/files/read` | Reads a workspace text file for the UI viewer/editor; binary files return an explicit unsupported-media response. |
| `GET` | `/workspace/files/info` | Returns metadata for a workspace path, including directory file counts used by delete confirmations. |
| `GET` | `/workspace/files/download` | Streams one workspace file as an attachment. |

### Asset And Operator Routes

| Method | Endpoint | Description |
| -------- | ---------- | ------------- |
| `POST` | `/log` | Receives client-side error reports and emits them through server logging. |
| `GET` | `/static/<path:filename>` | Flask's built-in static-file route for committed frontend assets under `app/static/`. |
| `GET` | `/vendor/ansi_up.js` | Serves the vendored `ansi_up` script. |
| `GET` | `/vendor/jspdf.umd.min.js` | Serves the vendored `jsPDF` script used by export flows. |
| `GET` | `/vendor/xterm.js` | Serves the vendored xterm browser terminal script used by interactive PTY tabs. |
| `GET` | `/vendor/xterm-addon-fit.js` | Serves the vendored xterm fit addon used to size interactive PTY terminals. |
| `GET` | `/vendor/xterm.css` | Serves the vendored xterm stylesheet used by interactive PTY terminals. |
| `GET` | `/vendor/fonts/<path:filename>` | Serves only committed font files from the vendored font manifest. |
| `GET` | `/favicon.ico` | Serves the site favicon. |
| `GET` | `/health` | Returns Docker/load-balancer health with DB and optional Redis checks; degraded dependencies return 503. |
| `GET` | `/status` | Returns lightweight HUD status data for uptime, DB, Redis, and server time; always responds 200. |
| `GET` | `/diag` | Serves IP-gated operator diagnostics as HTML or JSON; returns 404 outside `diagnostics_allowed_cidrs`. |
| `GET` | `/metrics` | Serves IP-gated Prometheus text metrics; returns 404 when metrics are disabled or the caller is outside `diagnostics_allowed_cidrs`. |

---

## Frontend

This section is the browser-runtime home for page composition, prompt/composer state, mobile shell behavior, the helper layer that keeps the classic-script UI consistent, and the cross-cutting UI primitives that every surface in the shell composes against.

### Frontend Composition

```mermaid
flowchart TD
  subgraph Foundations["Foundations"]
    Session["session.js"]
    State["state.js"]
    DOM["dom.js + ui_helpers.js"]
    Bootstrap["config.js + app.js"]
  end

  subgraph Features["Feature Modules"]
    Tabs["tabs.js"]
    Output["output.js"]
    Search["search.js + autocomplete.js"]
    History["history.js"]
    Welcome["welcome.js"]
    Runner["runner.js"]
  end

  Controller["controller.js"]

  Session --> State
  State --> DOM
  DOM --> Tabs
  DOM --> History
  DOM --> Runner
  Bootstrap --> Controller
  Tabs --> Controller
  Output --> Controller
  Search --> Controller
  History --> Controller
  Welcome --> Controller
  Runner --> Controller
```

This is still a classic-script frontend, not an ES-module app. The architecture relies on a deliberate load order:

- `state.js` owns shared state
- `ui_helpers.js` owns DOM-facing setters/getters
- domain scripts own tab/output/search/history/welcome/runner logic
- `config.js` and `app.js` handle bootstrap concerns, while `controller.js` is the composition root and last loader

Prompt ownership lives in `composerState`, not in whichever DOM input happened to update last.

The options modal is part of that same browser-owned layer. It does not change backend config; it owns user-specific UX preferences (timestamp/line-number quick toggles, welcome-intro behavior, snapshot redaction defaults, run-notification state, HUD clock timezone mode), session-token shortcuts, and encrypted secret management for the active session. The modal is split into a **Preferences** tab for display, identity, run, and compare controls and a **Secrets** tab for Provider Status, add/refresh actions, and the dynamic secret list; the selected tab is saved with the session preference snapshot. The modal feeds preference changes back into the classic-script runtime during boot and session changes. The terminal-native `config` command calls the same preference application path as the modal, so terminal and modal changes stay equivalent. Browser-owned terminal commands (`theme`, `config`, `workflow`, `secret set`, and `session-token`) render locally, then persist their masked command and transcript output through `/run/client` so history, recents, and reload hydration use the same server-backed history model as brokered `/runs`. `secret set NAME` opens the same replace-only Options value prompt and never accepts the value on the command line. `workflow run` uses that local command path for catalog lookup, input prompting, and queue setup, then submits the rendered workflow steps through the normal `/runs` execution path. Those preferences now persist server-side per session through the session-token model, while browser cookies/local storage remain the local cache and anonymous-session fallback layer. On mobile, that same shared Options surface hides the desktop-only `HUD Clock` and `Run Notifications` rows even though the underlying preference set remains shared with desktop.

### Browser Runtime

Modular frontend with no build step. `index.html` is the HTML shell — no inline styles or scripts.

**CSS composition.** CSS is split across ordered static files under `static/css/`, with `styles.css` acting as the compatibility entrypoint that imports core tokens, shell foundations, reusable primitives, desktop/mobile chrome, and feature-owned stylesheets under `static/css/features/`.

**Desktop shell chrome.** `shell-chrome.css` and its companion `static/js/shell_chrome.js` own the left rail (app title, recent commands, workflows, options, history, Atlas, theme, FAQ, diag, version footer), the tabbar row, and the bottom HUD bar (eleven live status pills — STATUS, LAST EXIT, TABS, TRANSPORT, LATENCY, MODE, SESSION, UPTIME, CLOCK, DB, REDIS — plus the `share snapshot / copy / save ▾ / clear` actions and the kill button). The visible desktop navigation lives in the rail and calls the shared desktop action helpers directly, so desktop and mobile are parallel trigger layers over the same behavior instead of one UI surface proxying through another.

**HUD runtime.** Polls `GET /status` on a visibility-aware cadence: every 3 seconds while the tab is visible and every 15 seconds while hidden, with an immediate refresh when the tab becomes visible again. Round-trip latency is measured client-side via `performance.now()`, server uptime is interpolated locally between polls, and the clock pill ticks once per second. The clock mode is user-selectable from the Options modal (`UTC` vs browser-local time); local mode prefers the browser's short timezone label (for example `CDT`) and falls back to a GMT offset label when the browser cannot provide a stable abbreviation. The `SESSION` pill reflects the active session identity and updates via a `storage` event listener so cross-tab token switches are picked up without a reload. `LAST EXIT` is updated from `runner.js` on every SSE `exit` event and on kill through the shared document-level UI event stream rather than a shell-chrome-specific global.

**Mobile chrome.** The original top header, recent-command chip row, and per-tab footer action row are hidden on both desktop and mobile by `shell-chrome.css` / `mobile-chrome.css`, but remain in the DOM because parts of the classic tab and composer DOM are still re-parented into the mobile shell through `syncMobileShellLayout()`. The mobile chrome (tabs, header, transcript framing, recents peek + pull-up sheet, bottom-sheet menu, and the keyboard edit-helper row) is composed through `mobile-chrome.css` and its companion `mobile_chrome.js`. Shared mobile sheet structure now comes from common `.mobile-sheet-overlay` / `.mobile-sheet-surface` scaffolding in `shell.css` plus the mobile overrides in `mobile.css`, so options / FAQ / workflows / shortcuts use one mobile sheet contract instead of per-ID structural CSS. The theme selector is the intentional exception and keeps its dedicated full-screen mobile treatment.

**Page exceptions.** The permalink and diag pages are explicitly scoped out of the desktop header hide so their own `<header class="export-header">` still renders. The diagnostics page (`/diag`) uses a separate `diag.css` rather than inline styles; it also links `terminal_export.css` to share the same header chrome foundation (`export-header`, `export-header-copy` classes) used by permalink pages. The mobile chrome on `/diag` (back button, header layout) activates at `@media (max-width: 900px) and (pointer: coarse)` — matching the same width + touch criteria used by the shell's `useMobileTerminalViewportMode()` — while layout-only changes (grid collapse, column widths) continue at `max-width: 760px` for all device types.

**JS composition.** Logic is split across `static/js/` into focused modules loaded via plain `<script src="...">` tags. Load order matters: the shared store lives in `state.js`, DOM-facing helpers live in `ui_helpers.js`, `app.js` provides shared browser helpers, feature modules under `static/js/features/` own larger user-facing surfaces, and `controller.js` loads last to perform the initialization and event wiring. No bundler, no transpilation.

Within that non-module shell, repeated tab/history/FAQ-limit surfaces are built with direct DOM node creation instead of stitched HTML strings, and the template’s modal chrome uses class-based wrappers for hidden state and dialog layout. That keeps the render paths more maintainable without changing the page composition model.

**Cross-module UI events.** The classic-script runtime still uses globals, but cross-module UI synchronization no longer relies on wrapper monkey-patching as the default bridge. `state.js` exposes `emitUiEvent(...)` / `onUiEvent(...)` helpers built on document-level `CustomEvent`, and the main publishers (`history.js`, `app.js`, `controller.js`, `tabs.js`, `runner.js`, `ui_helpers.js`) emit explicit lifecycle events such as `app:history-rendered`, `app:workflows-rendered`, `app:tab-activated`, `app:tab-status-changed`, `app:status-changed`, `app:last-exit-changed`, and `app:mobile-keyboard-state`. `shell_chrome.js` and `mobile_chrome.js` subscribe to those events instead of wrapping globals like `renderHistory` / `setTabStatus` or mirroring state through unrelated `MutationObserver` hooks. That keeps UI ownership closer to the module where the state changes actually happen while staying compatible with the current plain-script load model.

External dependencies: local vendor routes serving committed builds of `ansi_up`, `jspdf`, xterm, and the xterm fit addon from `app/static/js/vendor/`, plus committed font files from `app/static/fonts/`. These browser libraries are tracked in `package.json` under `dependencies`. `scripts/build_vendor.mjs` generates `app/static/js/vendor/ansi_up.js` (an IIFE-wrapped browser global, because `ansi_up` v6 is ESM-only), `app/static/js/vendor/jspdf.umd.min.js` (copied from the npm UMD build), and the xterm JS/CSS files used by interactive PTY tabs. The generated files are committed so local development and docker-compose runs never need an explicit build step. Run `npm run vendor:sync` to regenerate after a version bump; `npm run vendor:check` verifies the committed files in `app/static/js/vendor/` match what `build_vendor.mjs` would produce from the current `node_modules/` packages. Fonts are committed to `app/static/fonts/` and served through `/vendor/fonts/`.

**JS module load order:** `session.js` → `state.js` → `utils.js` → `export_html.js` → `config.js` → `dom.js` → `ui_helpers.js` → `ui_pressable.js` → `ui_disclosure.js` → `ui_dismissible.js` → `ui_focus_trap.js` → `ui_confirm.js` → `ui_outside_click.js` → `ui_entity_metadata.js` → `export_pdf.js` → `tabs.js` → `output.js` → `search.js` → `autocomplete.js` → `history_core.js` → `history.js` → `workspace_core.js` → `workspace.js` → `welcome.js` → `status_monitor.js` → `atlas_tabs.js` → `atlas_entity_detail.js` → `atlas_overlay.js` → `runner_core.js` → `pty.js` → `runner.js` → `app_preferences_core.js` → `app.js` → `preferences.js` → `secrets_panel.js` → `session_token_controls.js` → `tour_modal.js` → `mobile_sheet.js` → `controller.js` → `shell_chrome.js` → `mobile_chrome.js`. `state.js` owns the shared store boundary, `ui_helpers.js` owns DOM-facing setters/getters and visibility helpers, the `ui_*` helper modules form the shared UI interaction layer (see **UI Interaction Helpers** below), `ui_entity_metadata.js` owns the shared `/entities/<type>/<id>` label/note client consumed by Files, Projects, and Atlas, `app.js` still provides reusable browser helpers, `secrets_panel.js` owns the Options Secrets list plus the terminal `secret set NAME` value prompt, `tour_modal.js` owns the desktop visual onboarding carousel, `controller.js` owns the composition root, and `shell_chrome.js` / `mobile_chrome.js` load last so their rail, tabbar, HUD, and mobile-sheet wiring can attach after all tab, search, and action helpers are defined. `welcome.js` must precede `runner.js` because `runner.js` calls `cancelWelcome()` at the top of `runCommand()`.

**Session Entity Atlas surface.** Atlas is a top-level overlay backed by its own service, schema, and routes. The full surface contract — entity dedup, transcript-token wiring, intel snapshots, findings triage, run-delete cleanup, and bulk-delete confirmations — lives in **Atlas and Entity Model**.

**UI Interaction Helpers.** A five-helper family in `static/js/ui_helpers.js` + four sibling `ui_*.js` modules is the single contract for chrome-surface interaction. Every module loads before the domain scripts that consume it, so every downstream module sees the helpers as plain globals — no wiring glue at call sites.

- `refocusComposerAfterAction({ preventScroll = true, defer = false })` in `ui_helpers.js` is the canonical post-action composer refocus. Handles mobile-skip, `preventScroll` default, and `getVisibleComposerInput()` target resolution in one place. `defer: true` preserves legacy `setTimeout(0)` semantics for chrome-close paths that need a pending blur to finish first. 46+ call sites across `controller.js`, `app.js`, `tabs.js`, `runner.js`, `welcome.js`, `autocomplete.js`, `shell_chrome.js`, and `history.js` route through it.
- `focusElement(el, { preventScroll })` and `blurActiveElement()` in `ui_helpers.js` are the canonical wrappers for raw DOM focus/blur. `focusElement` collapses the `try { el.focus({ preventScroll: true }) } catch (_) { el.focus() }` pattern, null-guards non-focusable targets, and returns a bool; `blurActiveElement` blurs `document.activeElement` if it is blurrable. Only two direct focus/blur calls remain outside helper internals: the clipboard `execCommand('copy')` fallback in `utils.js` and the helper-internal blur in `ui_pressable.js`.
- `bindPressable(el, { onActivate, refocusComposer, preventFocusTheft, preventScroll, defer, clearPressStyle })` in `ui_pressable.js` is the single contract for press-to-activate surfaces. Click + `Enter`/`Space` activation (keyboard only on non-`<button>` elements so native buttons don't double-fire), post-activation blur + canonical composer refocus (opt-out via `refocusComposer: false`), `preventFocusTheft` on primary-contact pointerdown, and `clearPressStyle` double-`requestAnimationFrame` for `role="button"` divs whose sticky `:hover`/`:active` residue doesn't clear on blur. Idempotent via `data-pressable-bound`.
- `bindDisclosure(trigger, { panel, openClass, hiddenClass, initialOpen, onToggle, stopPropagation, ...pressableOpts })` in `ui_disclosure.js` composes `bindPressable` for the trigger and owns `aria-expanded` sync + panel class lifecycle + `onToggle` emission. Returns an imperative handle (`isOpen / open / close / toggle`). `panel: null` lets the caller own visibility (used by rail section headers where `applySectionsState()` is the sole writer of `.closed`). Idempotent via `data-disclosure-bound`.
- `bindDismissible(el, { level, isOpen, onClose, closeButtons, closeOnBackdrop, backdropEl })` in `ui_dismissible.js` owns scrim-backed modal/sheet dismissal and registers the surface with a shared level-priority dispatcher. `closeTopmostDismissible()` collapses the Escape cascade: priority `modal > sheet > panel`, within-level most-recent-open wins, returns `true` if it closed something so the keydown handler can `preventDefault`. Backdrop semantics: default `e.target === el`; sheets with a detached scrim pass `backdropEl: <scrim>`; `closeOnBackdrop: false` disables (used by the history panel, which is a side panel rather than a modal). Composes `bindPressable` for each close button and idempotent via `data-dismissible-bound`.
- `bindOutsideClickClose(panel, { triggers, isOpen, onClose, exemptSelectors, scope })` in `ui_outside_click.js` owns ambient document-level (or scope-overridden) outside-click dismissal for unbacked panels. Companion to `bindDismissible`: `bindDismissible` owns backed surfaces, `bindOutsideClickClose` owns menus whose trigger sits outside the surface. Encodes the trigger-exemption contract (clicks on registered `triggers` are treated as "inside" via `.contains()`, replacing hand-rolled `e.stopPropagation()` patterns), `exemptSelectors` ancestor-based exemption via `.closest()`, `panel: null` for sibling-set cases (multiple peer dropdowns on a shared parent), and `scope` override for per-sheet listeners.

**App-native Select Primitive.** Native `<select>` popup styling is not themeable consistently across browsers, so user-facing select controls are progressively enhanced into app-native dropdowns by `enhanceAppSelects()` in `ui_helpers.js`. The original `<select>` remains in the DOM as the state owner and accessibility fallback, while the visible `.app-select` wrapper renders a themed button/listbox menu using `dropdown_*` and `chrome_control_*` tokens.

The enhancement targets `select.form-select` and History drawer filter selects. `ui_helpers.js` also watches the DOM and automatically enhances matching selects inserted after startup, so dynamically rendered modal, sheet, and detail controls do not fall back to browser-native dropdown chrome. Selecting an item in the app-native menu updates the real select and dispatches a normal bubbling `change` event, so existing Options and History logic does not need a parallel API. Long app-native menus are height-capped and scroll internally, and selects inside dialogs, modals, and sheets automatically portal their menus to the page layer so provider, command, and Options lists stay reachable on desktop and mobile. When code changes a select value programmatically, it must call `syncAppSelect(select)` or `syncAppSelects()` after writing `.value` / `.disabled`; `syncOptionsControls()` and `_syncHistoryFilterControls()` are the canonical examples.

The native select is visually hidden but left measurable/actionable enough for Playwright's `selectOption()` to keep working in E2E tests. The primitive owns outside-click and Escape closure for all enhanced selects, keeps `aria-expanded` / `aria-selected` synchronized, and supports keyboard stepping with ArrowUp/ArrowDown from the trigger. Unit coverage lives in `tests/js/unit/ui_focus_helpers.test.js`, and browser-level regression coverage comes from the Options preference E2E path.

The contract the helpers jointly enforce: focus returns to the composer after non-text chrome actions; pressed/highlight state clears after activation; `Enter`/`Space` activate pressables consistently; disclosures keep `aria-expanded` and visual state in sync; scrim overlays close consistently via button, backdrop, and `Escape` with a shared priority dispatcher; ambient-click menus close on any outside click but not on clicks inside the panel or trigger. Each helper has its own Vitest unit suite (`ui_focus_helpers.test.js`, `ui_pressable.test.js`, `ui_disclosure.test.js`, `ui_dismissible.test.js`, `ui_outside_click.test.js`). End-to-end verification against real mounted surfaces lives in `tests/js/e2e/interaction-contract.spec.js`.

**Why not ES modules (`type="module"`)?** ES modules are deferred by default and each runs in its own scope, which would require explicit `export`/`import` everywhere. The plain script approach shares a single global scope — simpler and sufficient for this scale.

**Export rendering modules (`export_html.js` / `export_pdf.js`).** Browser export rendering is split into two shared modules. `window.ExportHtmlUtils` owns the browser-rendered export model and the shared export-preparation helpers. In addition to `buildExportLinesHtml` (converts raw line objects to styled HTML spans, respecting `tsMode`/`lnMode` prefix state), `buildExportMetaLine`, `buildExportHeaderModel`, `buildTerminalExportHeaderHtml`, `buildTerminalExportStyles` (produces the full inline CSS block with theme variables), `buildTerminalExportHtml` (assembles the complete standalone HTML document), `fetchVendorFontFacesCss` (fetches and base64-encodes fonts for self-contained export files), and `fetchTerminalExportCss` (fetches `terminal_export.css` with module-level caching so the shared export stylesheet is embedded in every exported document), it now also exposes `normalizeExportTranscriptLines`, `normalizeExportRunMeta`, and `buildExportDocumentModel` so the main-shell save paths and permalink/share save paths prepare transcript/meta data through the same logic. `window.ExportPdfUtils` owns jsPDF rendering and consumes that same prepared header/meta/line model so PDF stays aligned with the browser export baseline while still handling PDF-only responsibilities such as font embedding, wrapping, pagination, and geometric drawing. All save surfaces — `exportTabHtml` / `exportTabPdf` in `tabs.js` and `saveHtml` / `savePdf` in `permalink.js` — delegate to these shared modules so visual changes and transcript-preparation rules propagate from one place instead of being rebuilt independently per surface.

**Permalink/share page model.** `app/services/history/permalinks.py` now builds one normalized `page_model` for `/history/<run_id>` and `/share/<id>`. That model carries:
- `header` — app name, meta line, ordered run-meta items, and optional expiry HTML
- `transcript` — normalized line objects plus `hasTimestampMetadata`
- `export` — app/export context consumed by `permalink.js` (`appName`, `label`, `created`, `createdDisplay`, embedded font CSS, normalized run meta)
- `actions` — JSON URL and any extra header actions

The Jinja templates and `window.PermData` now consume that same structure directly, so the live permalink/share page and the saved export surfaces are reading from the same server-provided model instead of parallel template variables.

---

### Prompt And Composer Runtime

The prompt architecture is built around one editing state and two render surfaces:

- the hidden real `#cmd` input remains the canonical editing source for browser focus, selection, and keyboard semantics
- the rendered prompt line inside the active output pane is only a visual mirror of that state
- on desktop, starting a text selection gesture inside the visible prompt temporarily yields focus away from the hidden input so browser-native range selection can complete without the composer stealing focus back
- on touch-sized viewports, `#mobile-cmd` becomes the visible editing surface, but it still syncs into the same shared composer state instead of creating a second command model
- the mobile edit bar is a thin action layer over that same shared composer state, so word-jump and delete helpers reuse the same selection/update path as desktop keyboard shortcuts instead of forking mobile-specific command state
- prompt rows that appear in transcript history are rendered output records, not live editable DOM

This split keeps browser editing semantics predictable without relying on `contenteditable`, while still letting the app present a terminal-like prompt inside the transcript.

### Browser State Model

Each tab is an object: `{ id, label, command, runId, runStart, exitCode, rawLines, killed, pendingKill, st, draftInput }`.

- `command` — the command associated with this tab, set both when the user runs a command directly and when a tab is created by loading a run from the history drawer; used for dedup when the history drawer's `restore` action button is pressed (if a matching tab already exists, that tab is activated instead of creating a new one). Row clicks on history entries take the re-run path instead — they inject the command into the composer and do not touch the tab set.
- `runId` — the UUID from the SSE `started` message, used for kill requests
- `runStart` — `Date.now()` timestamp set *after* the `$ cmd` prompt line is appended, so the prompt line itself has no elapsed timestamp
- `rawLines` — array of `{text, cls, tsC, tsE}` objects storing the pre-`ansi_up` text with ANSI codes intact; `tsC` is the clock time (`HH:MM:SS`), `tsE` is the elapsed offset (`+12.3s`) relative to `runStart`. Used for permalink generation and HTML export
- `killed` — boolean flag set by `doKill()` to prevent the subsequent `-15` exit code from overwriting the KILLED status with ERROR
- `pendingKill` — boolean flag set when the user clicks Kill before the SSE `started` message has arrived (i.e. `runId` is not yet known); the `started` handler checks this and sends the kill request immediately
- `st` — current status string (`'idle'`, `'running'`, `'ok'`, `'fail'`, `'killed'`); set synchronously by `setTabStatus()` so `runCommand()` can check it without waiting for the async SSE `started` message
- `draftInput` — unsaved command text for that tab; restored from browser session state for non-running tabs during reload continuity

Tab activation is intentionally stateful rather than stateless rendering. `activateTab()` preserves the leaving tab's draft, restores the arriving tab's draft without reopening autocomplete, and resets transient input-mode state such as history-navigation and autocomplete selection. During full session restore, draft-flush side effects are suppressed until the saved tab set has been rebuilt so non-active drafts cannot be overwritten by the final active-tab selection.

Session-scoped user preferences are normalized by `app/static/js/core/app_preferences_core.js`, cached in cookies/local storage as a browser fallback, and persisted through `/session/preferences` so session tokens carry the user's shell state across browsers. The persisted set includes theme, timestamps, line numbers, welcome intro, share-redaction default, external-run project capture, run notifications, HUD clock, prompt username, active project, onboarding tour version, the last selected Options tab, and run comparison preferences. Run comparison stores `pref_compare_view_mode` (`auto`, `side_by_side`, `unified`, `changes_only`, `findings_only`) plus `pref_compare_context` (`3`, `10`, `all`), defaulting to responsive `auto` view mode and `±3` equal-line context.

### Welcome Bootstrap Flow

`welcome.js` owns a staged boot flow that is separate from normal run output. The important architectural points are:

- welcome state is tab-scoped, so clearing or running commands in another tab cannot tear down the active welcome tab
- desktop and mobile share the same timing/config pipeline but can read different banner/hint assets
- the browser fetches narrow typed endpoints such as `/welcome`, `/welcome/ascii`, `/welcome/ascii-mobile`, `/welcome/hints`, and `/config` rather than reading raw files directly
- the same frontend-owned preference layer that controls timestamps and line numbers also controls welcome-intro behavior

The detailed user-visible welcome behavior belongs in the README. Here, the important distinction is that welcome is a client-owned bootstrap experience built from server-normalized content routes, not a special command-execution transcript.

### Input Modes And Dropdown State Machines

Command editing is split into separate state machines rather than one overloaded dropdown path:

- normal autocomplete consumes structured external-tool and app-owned built-in `context` hints from `/autocomplete`, then overlays only dynamic runtime suggestions such as loaded Files, session variables, workflow names, theme names, config values, and command lookup targets before passing everything through the same token-aware ranked matcher
- reverse-history search owns its own pre-draft, query, selection, and exit paths
- `controller.js` routes keyboard events into the appropriate mode before the normal submit/edit handlers run
- navigation semantics stay consistent regardless of whether a dropdown opens above or below the prompt

The structured autocomplete path is intentionally token-aware rather than shell-aware. It inspects command root, current token, and prior tokens to decide whether a suggestion should replace the whole input or only the active token. Examples act as discovery suggestions: a unique root or fuzzy root match can flatten root and subcommand examples into full-command replacements, while a selected subcommand switches the matcher to subcommand-scoped flags and value hints. Ambiguous subcommand matches remain token suggestions until only one subcommand matches. The matcher ranks exact matches, prefixes, token-boundary/camel-ish hits, substrings, and fuzzy character matches in that order, while preserving authored example order once an example is eligible. That preserves the classic-shell feel for long scanner commands without turning the frontend into a general shell parser.

Recent target autocomplete is session-token-backed state. `autocomplete.js` keeps a page-local cache for immediate suggestions, but `GET`/`POST /session/recent-values` persist normalized domains, IPs, URLs, and port sets in SQLite under the active session ID. Each value kind is capped at 10 entries and migrates with `/session/migrate`. Capture and suggestions still require explicit value-type metadata in the command registry; placeholder text and descriptions are display-only and do not make a slot record recent targets. URLs are saved without query strings or fragments so pasted tokens do not become suggestions.

Synthetic post-filters also sit on a distinct path before the normal shell-operator denial logic. `parse_synthetic_postfilter()` in `commands.py` recognizes one narrow `command | helper ...` stage for `grep`, `head`, `tail`, and `wc -l`, validates only the base command, and the broker worker applies the selected helper before lines are emitted or persisted. That keeps shell-like helpers app-native without reopening general shell piping or chaining.

### Design System Primitives

This subsection is the single home for the finalized cross-cutting UI rules that apply to every pressable surface, disclosure, color decision, and modal in the shell. Each family below states the rule, names the shared primitive that enforces it, and points at the owning helper module or theme contract. Rationale and historical context for each rule live in [DECISIONS.md § Frontend Decisions](DECISIONS.md#frontend-decisions).

#### Button Primitive Family

Every clickable surface in the shell uses one of a small, allowlisted set of primitive classes. The primary pressable primitive is `.btn`, composed with one role modifier and at most one tone modifier:

- **Role modifiers** (mutually exclusive): `.btn-primary`, `.btn-secondary`, `.btn-ghost`, `.btn-destructive`. Role controls the visual weight of the button — primary is the main action in a group, secondary is the alternate, ghost is a low-weight inline action, and destructive is a labeled irreversible action.
- **Tone modifiers** (mutually exclusive, optional): `.btn-danger`, `.btn-warning`. Tone overlays a semantic color from the theme contract. A tone without a role is not valid.

Nine non-`btn` pressable primitives exist for surfaces that are structurally not buttons but still need consistent pressable behavior: `.nav-item` (rail and menu navigation), `.tab-strip-item` (modal and panel tabs inside `.tab-strip`), `.close-btn` (modal and sheet close controls), `.toggle-btn` (on/off switches with no destructive semantics), `.kb-key` (keyboard-key glyphs in help copy), `.dropdown-item` (menu/listbox choices inside app-owned dropdowns), `.control-row` (row-shaped filter/select controls), `.hud-action-cell` (clickable HUD summary cells), and `.gesture-handle` (mobile sheet drag/tap handles). New pressable surfaces must pick one of these primitives rather than introducing one-off classes.

All pressable primitives route through `bindPressable` in `app/static/js/ui/ui_pressable.js` so click + Enter/Space activation, press-style timing, and composer-refocus behavior stay consistent. A jsdom contract test (`tests/js/unit/button_primitives_allowlist.test.js`) enumerates every `<button>` / `[role="button"]` in the rendered shell and fails CI on any element that does not carry one of the allowed class families; exceptions are listed in `tests/js/fixtures/button_primitive_allowlist.json` with a short reason per entry.

#### Tab Strip Primitive

Modal and panel tabs use the shared `.tab-strip` / `.tab-strip-item` primitive pair. The primitive owns the horizontal overflow behavior, hidden scrollbar, top-border active tab treatment, non-active hover color, pressed-state cleanup, and focus styling. Surface classes such as `.atlas-tab`, `.history-run-tab`, `.project-explorer-tab`, and `.project-mobile-tab` remain as JS hooks or for small local count-chip/layout tweaks, but they don't redefine the tab chrome.

Current consumers are Run Details, Atlas, Project desktop tabs, Project mobile tabs, Project entity-type tabs, and the Options modal tabs. Terminal document tabs keep their separate `.tab` contract because they are draggable workspace tabs rather than simple modal tabs.

#### Dropdown/Menu Primitive Family

App-owned dropdowns share the `.dropdown-surface` / `.dropdown-item` primitive family. The primitive owns common themed menu treatment: `dropdown_*` background, border, shadow, font family, default item text, hover/focus state, selected state, and upward-shadow direction via `.dropdown-up`. Surface selectors keep placement, width, z-index, max-height, and any behavior-specific layout.

Density is explicit rather than global. `.dropdown-item-compact` is used for small command menus such as Save, `.dropdown-item-touch` for app-native select and mobile sheet menus, and `.dropdown-item-dense` for terminal autocomplete rows. Autocomplete remains a specialized dropdown consumer: it shares the surface and active-row styling, but keeps its terminal prefix marker, descriptions, match highlighting, fixed positioning, and mobile keyboard positioning local.

Current consumers are terminal/permalink/HUD Save menus, app-native selects, command autocomplete, History root autocomplete, Ctrl+R history search, and mobile recents filter menus. New app-owned menu surfaces should compose these primitives before adding local selectors.

#### Row Primitive Family

Repeated list rows use shared row primitives instead of rebuilding background, divider, hover, and accent behavior per surface. `.chrome-row` is for shell-chrome lists such as History drawer rows, Status Monitor run rows, and mobile recents rows. `.chrome-row-clickable` adds the shared hover/focus state for rows that activate on click or keyboard. Accent classes such as `.row-accent-green` and `.row-accent-amber` are visual only; each component still decides when a run is active or a history row is starred.

Modal and panel content uses `.panel-row` instead of `.chrome-row`. The Files modal composes `.panel-row` for file, folder, and empty-state rows so it gets consistent border/radius/focus treatment without visually becoming a History or Status Monitor chrome row. Rail navigation stays under the `.nav-item` primitive because selected navigation state and rail density are different from content-list row behavior.

#### Chip And Badge Primitive Family

Pill-shaped UI uses two separate primitives so visual affordance matches behavior. `.chip` is for clickable or removable pill actions such as prompt history chips, active History filters, mobile recents filter chips, FAQ command chips, and workflow command chips. `.chip-action` keeps command-loading chips toolbar-like, while `.chip-removable` is used for active filters that clear state.

`.badge` is for passive metadata labels that should not look clickable. History and mobile recents use badges for `RUN` / `SNAPSHOT` labels, project workspace metadata chips compose badges for entity labels/notes, and tone classes such as `.badge-tone-green` and `.badge-tone-muted` carry the semantic color. Search signal chips intentionally remain text-like buttons even though they compose the chip primitive, because the search summary reads as inline metadata rather than a filter-chip row.

#### Form And Control Primitive Family

Text fields and compact filter controls compose `.form-control` and `.control-row` instead of rebuilding input chrome per surface. `.form-control` owns the shared `chrome_control_*` background/border, mono font, radius, padding, and focus border. `.form-control-compact` is used for dense History/search controls, while `.form-control-quiet` keeps the search input visually light inside the search strip.

`.control-row` is for row-shaped controls that are not plain text inputs, such as app-native select triggers and mobile recents filter rows. It is also part of the pressable primitive allowlist because several control rows are rendered as `<button>` dropdown/toggle triggers. `.control-row-touch` keeps mobile sheet controls large enough for touch without changing desktop filter density. The mobile command composer (`#mobile-cmd`) intentionally remains a local exception because its keyboard anchoring, caret behavior, and viewport sizing are more fragile than normal form controls.

#### Drawer And Sheet Primitive Family

Drawer-like chrome surfaces compose `.chrome-drawer`, `.surface-header`, and `.surface-body` so shared background, header band, scroll containment, and mono typography stay consistent. History uses this family as a side panel, while the desktop Status Monitor presents its dashboard inside a centered modal and mobile keeps the sheet treatment.

Mobile bottom sheets compose `.bottom-sheet`, `.bottom-sheet-header`, `.bottom-sheet-body`, `.bottom-sheet-footer`, and `.gesture-handle`. These primitives own the shared sheet background, top border, top radius, shadow, grab-handle affordance, and basic header/body/footer structure. Context menus that need bottom-sheet behavior use `openActionSheet()` from `ui_action_sheet.js`, which reuses one singleton sheet for Projects and Atlas mobile actions and closes before confirmation modals open. Scrims, keyboard-aware modal sizing, and sheet-specific controls remain local because those details are tied to mobile interaction behavior rather than general visual treatment.

#### Disclosure Affordance Rules

Disclosure glyphs in the shell encode a fixed mapping between glyph and behavior. The meta-rule is: **the glyph follows the actual behavior, not the visual hierarchy**. A surface that opens in place is never marked with a drill-in glyph even if it looks like a list row, and a row that navigates away is never marked with a chevron even if it visually resembles an expandable group.

| Glyph | Behavior | Example |
|-------|----------|---------|
| `▸` / `▾` | Expand/collapse in place. Glyph indicates state: `▸` closed, `▾` open. | FAQ items, rail section headers, mobile recents advanced-filter toggle |
| `>` | Drill-in. Opens a different surface or navigates to another view. | Sheet rows that open a sub-sheet |
| `▾` (static) | Dropdown trigger. Always shown as `▾`; the glyph is a type label, not a state indicator. | `save ▾`, mobile header menus |
| (no glyph) | Toggle or non-navigational action. No disclosure semantics. | `.toggle-btn`, run-tab pill |

The expand/collapse case is owned by `bindDisclosure` in `app/static/js/ui/ui_disclosure.js`, which wires `aria-expanded`, panel visibility, and the pressable contract in one call. Callers supply the trigger and panel; they do not manage `aria-expanded` by hand.

#### Semantic Color Contract

Theme colors in the shell are semantic, not decorative. Every theme exposes four semantic tokens — `--amber` (caution / in-progress), `--red` (destructive / error), `--green` (completed success / enabled), `--muted` (neutral metadata) — and every UI decision that reaches for one of these colors must match the semantic meaning of that token rather than picking on visual taste. Themes control the exact visual tone of each token; the mapping from token to meaning is fixed.

Full rules, the allowed exceptions (starred items, search-hit highlights, decorative macOS traffic-light chrome), and the `color-mix()`-in-theme-file pattern for surface-local tuning live in [THEME.md § Semantic Color Contract](THEME.md#semantic-color-contract). That document is the source of truth — this section does not restate the rules.

#### Scrollbar Styling Contract

App-owned vertical scroll regions use the `.nice-scroll` CSS primitive so terminal output, autocomplete dropdowns, modal bodies, history surfaces, mobile sheets, rail lists, permalink output, and saved HTML export output share the same themed scrollbar treatment. New scrollable panels, drawers, sheets, dropdowns, and transcript-like surfaces should add `.nice-scroll` instead of hand-rolling `scrollbar-width`, `scrollbar-color`, or `::-webkit-scrollbar` selectors.

Intentional hidden-scrollbar surfaces are separate from this primitive. Horizontally scrolling tab strips and touch-first overflow strips keep their explicit no-scrollbar rules because their contract is edge-glow or drag affordance, not visible scrollbar affordance.

#### Confirmation Dialog Contract

App-level modal confirmations — kill, history-delete, history-clear, share-redaction, Options-driven session-token actions, Options Secrets replace/delete prompts, delete-all — go through a single imperative primitive, `showConfirm()` in `app/static/js/ui/ui_confirm.js`. Surfaces do not hand-roll confirm markup, do not wire their own Escape handler, and do not manage their own backdrop. Terminal-owned `session-token` confirms are the intentional exception: they stay inside the transcript and use the shared pending-confirm state in `runner.js` instead of a modal surface.

The contract:

- **One at a time.** A second `showConfirm()` call while another is open is rejected. The shell never stacks confirms.
- **Role-based action ids.** Each action carries `role: 'primary' | 'secondary' | 'ghost' | 'cancel'` and an optional `tone: 'danger' | 'warning'`. `role` drives the button primitive class (`btn-primary` / `btn-secondary` / `btn-ghost`); `tone` adds the destructive overlay. Callers receive the id of the activated action, or `null` for cancel.
- **Default focus on cancel.** For confirmations, the cancel action is focused on open so browser native Enter-activates-focused-button makes `Enter === cancel`. Callers with a form input in the `content` slot can override via `defaultFocus`.
- **Focus is trapped inside the card.** `bindFocusTrap` in `app/static/js/ui/ui_focus_trap.js` keeps Tab / Shift+Tab cycling between the card's focusable descendants so keyboard focus cannot fall through to the rail, tabs, or HUD behind the backdrop while a modal is open. Every modal surface in the shell uses this helper: `#confirm-host` binds per-open because its card content changes between shows, and the app-level modals (`#options-modal`, `#theme-modal`, `#faq-modal`, `#workspace-modal`, `#workflows-modal`, `#workflow-editor-form`) bind once at startup via `setupModalFocusTraps()` in `controller.js` because their DOM is persistent.
- **Dismissal is layered.** `bindDismissible` at `level: 'modal'` owns Escape + backdrop click. `bindMobileSheet` owns the drag-down-to-close handle on mobile. Both resolve the promise with `null` so callers cannot accidentally treat dismissal as confirmation.
- **Actions stack at narrow widths.** The action row adds `.modal-actions-stacked` when the viewport is ≤480px or the action count is ≥3. A `matchMedia` listener keeps the class reactive to resize while the modal is open.
- **Gate via `onActivate`.** An action can supply `onActivate` to run validation before close. Returning a falsy value (or a Promise resolving to one) keeps the modal open so form errors stay on screen; any truthy return closes and resolves with the action id.

---

## Back-end Architecture

This section centralizes the Python/runtime-side composition: the Flask surface, shared infrastructure, command orchestration, and the durable services the browser depends on.

### Backend Composition

The backend is intentionally split so that request handling, shared infrastructure, and command policy stay testable in isolation rather than collapsing into one large Flask module.

The Python backend is split into focused layers with acyclic dependencies:

```mermaid
flowchart TB
  Config["config.py"]
  Logging["logging_setup.py"]

  subgraph Infra["Infrastructure + Shared Helpers"]
    Helpers["helpers.py"]
    Database["database.py"]
    Process["process.py"]
    Permalinks["permalinks.py"]
    OutputStore["run_output_store.py"]
    Extensions["extensions.py"]
  end

  subgraph Commands["Command Layer"]
    CommandRules["commands.py"]
    BuiltinCommands["builtin_commands.py"]
  end

  subgraph Http["HTTP Layer"]
    Assets["assets.py"]
    Content["content.py"]
    Run["run.py"]
    History["history.py"]
    Session["session.py"]
    WorkspaceBp["workspace.py"]
    Projects["projects.py"]
  end

  App["app.py"]

  Config --> Logging
  Logging --> Helpers
  Logging --> Database
  Logging --> Process
  Logging --> Permalinks
  Logging --> OutputStore
  Extensions --> Http
  Helpers --> Http
  Database --> Http
  Process --> Http
  Permalinks --> Http
  OutputStore --> Http
  CommandRules --> Run
  BuiltinCommands --> Run
  CommandRules --> Projects
  BuiltinCommands --> Projects
  Http --> App
```

- `config.py` is the root configuration/theme layer and stays free of Flask app dependencies.
- `logging_setup.py` must initialize before the rest of the app because module-import-time startup work, especially Redis setup, can log immediately.
- The infrastructure/helper layer owns shared concerns like request metadata, persistence, process tracking, permalink shaping, artifact storage, and the Flask-Limiter singleton.
- `commands.py` and `builtin_commands.py` stay logically adjacent to the run path but remain separate from the Flask factory so command policy and shell-helper behavior can be tested in isolation.
- The HTTP layer owns the actual request/response surface across assets/content, run streaming, history/share, session-token/session-state APIs, workspace-file APIs, and project workspace APIs. `app.py` remains a thin factory that composes logging, limiter setup, blueprint registration, and request hooks.

### Backend Runtime Boundaries

This boundary view answers a different question than the dependency graph above: not "which module imports which," but "which runtime service owns which responsibility."

- Flask + Gunicorn own routing, request hooks, response shaping, and template rendering.
- Redis owns the shared coordination required across Gunicorn workers: rate limiting, active-run PID tracking for `/kill`, replayable run-broker streams, and PTY event/control streams when those brokered runtimes are enabled.
- The configured database plus artifact files own durable run, snapshot, token, workflow, workspace metadata, project workspace, package, and search state.
- Scanner subprocesses remain an out-of-process boundary rather than an in-worker extension of the Flask app.
- Config and theme YAML files are filesystem-backed dependencies that shape both backend behavior and frontend presentation but do not become a general runtime datastore.

---

## Run Lifecycle

This section groups the full command path — validation, rewrite, execution, streaming, kill, and completion persistence — into one coherent runtime story.

### Validation And Rewrites

The run path applies policy before any subprocess launch:

- command validation blocks filesystem references to `/data` and `/tmp` before subprocess launch
- loopback targets such as `localhost`, `127.0.0.1`, `0.0.0.0`, and `[::1]` are blocked at both the client and server
- when the allowlist is active, shell operators such as `&&`, `||`, `|`, `;`, redirection, and command substitution stay blocked so users cannot chain into disallowed commands
- optional `restricted_command_input_cidrs` settings reject literal IP/CIDR values in metadata-known target slots before launch, including URL hosts, host:port values, overlapping CIDR arguments, and app-readable workspace input files supplied through declared read flags

These rewrites are declared in `app/conf/commands.yaml` under `runtime_adaptations` and applied by the shared command layer through `rewrite_command()` (no user-visible notice unless specified):

| Command | Rewrite | Reason |
| --------- | --------- | -------- |
| `mtr` | Adds `--report-wide` | mtr requires a TTY for interactive mode; report mode works without one. User is shown a notice. |
| `nmap` | Adds `-sT` when no scan mode is explicit | Uses TCP connect scanning for reliable non-root container execution; `-sS` and `--privileged` are blocked. Silent. |
| `nuclei` | Adds `-ud /tmp/nuclei-templates`; uses session-scoped `XDG_CONFIG_HOME=<workspace>/tools` when Files are enabled | Redirects template storage to tmpfs while keeping useful ProjectDiscovery config/resume state under the session workspace's `tools/` folder. Silent. |
| `naabu` | Adds `-scan-type c` | Uses TCP connect scanning instead of raw SYN mode for container reliability. Silent. |

Session command variables are expanded inside the app before command policy validation and execution. `app/services/session/variables.py` owns the `[A-Z][A-Z0-9_]{0,31}` name rules, SQLite storage, and `$NAME` / `${NAME}` replacement. The run-start path keeps `var` itself unexpanded so `var set HOST ...` is data management, expands other commands before synthetic post-filter parsing, validates the expanded command, and still persists the typed command in history while emitting a transcript notice with the expanded form.

Workspace-aware validation also rewrites declared file and directory flags from `app/conf/commands.yaml` into the active session workspace. Rewritten token lists are reassembled with shell-safe quoting before they cross the existing `sh -c` subprocess boundary, so app-injected workspace paths cannot accidentally change shell parsing when a valid session file or folder name contains spaces or shell metacharacters. The same command metadata drives target-value restrictions: flags and positional arguments declared with target-like `value_type` values (`domain`, `host`, `ip`, `cidr`, `target`, or `url`) can be checked against configured restricted networks without blanket string scanning. Runtime adaptation metadata also owns managed workspace directories, environment wrappers, and command-prefix injections; Amass declares its database-backed subcommands there, so `amass enum`, `amass subs`, `amass track`, and `amass viz` get a managed `-dir tools/amass` workspace directory and `XDG_CONFIG_HOME` is pointed at the session workspace's `tools/` folder so `amass engine` and the CLI share the same per-session database path. ProjectDiscovery tools declare a workspace-required `env XDG_CONFIG_HOME=<session workspace>/tools` prefix through the same metadata, and run output filters display absolute session-workspace paths as user-facing paths like `/tools/katana/resume.cfg`. See [External Command Integrations](docs/external-command-integrations.md) for the command-specific integration contracts.

Registry-owned `requires_secrets` declarations resolve against the encrypted session vault before validation-owned runtime wrappers can change the executed shell text; required missing secrets block the launch and successful injection emits a `SECRET_INJECTED` audit event. The full vault model — master-key bootstrap, AES-GCM row encryption, alias mapping, command-catalog integration, and the Options Secrets picker — lives in **Secrets and Vault** below.

The app-native `intel` built-in uses the same encrypted-secret boundary without spawning a provider CLI. The full intel pipeline, provider fan-out, and provider directory are covered in **Intel and Provider Integrations** below. Workspace move, glob, and permission-repair behavior is covered in **Session Workspace and Files**.

Synthetic post-filters also sit on this run-lifecycle boundary rather than on the shell-parser path. `parse_synthetic_postfilter()` recognizes one narrow `command | helper ...` stage for `grep`, `head`, `tail`, and `wc -l`, validates only the base command, and the brokered stream applies the selected helper before lines are emitted or persisted.

### Spawn And Stream

Commands flow through `POST /runs`, which validates and rewrites the request, resolves any app-native built-in commands, starts brokered execution, and returns a run id plus stream URL. The browser then subscribes to `GET /runs/<run_id>/stream`, which replays available broker events and follows live output over SSE. Production deployments require Redis for cross-worker replay; single-process local development can opt into the in-memory broker fallback.

Interactive PTY runs use a separate, narrower lifecycle because interactive and screen-redrawing tools need cursor-oriented input/output instead of line-oriented transcript events. `POST /pty/runs` accepts command roots that declare `interactive: { mode: pty, trigger_flag: ... }` in `commands.yaml`; today that covers `nc --interactive <host> <port>`, `telnet --interactive <host> <port>`, `mtr --interactive <host>`, `ffuf --interactive ...`, and `masscan --interactive ...`. The route strips the configured trigger flag, validates the resulting command through the same registry policy plus the PTY-only execution allowance for that command root, enforces the per-session PTY concurrency limit, and passes the registry-owned terminal defaults, input policy, input-safety profile, max runtime, and completed transcript mode into the PTY service. The service spawns the PTY under the same scanner/process-group model and publishes PTY output to Redis streams when Redis is available. Browser input and resize events post back through `/pty/runs/<run_id>/input` and `/pty/runs/<run_id>/resize`, which enqueue control events for the PTY owner to drain. The browser renders live PTY interaction in an app modal with vendored xterm.js and the xterm fit addon, so ANSI formatting, cursor movement, keyboard input, paste, and resize handling use a real terminal emulator instead of app-specific escape parsing. Server-side pyte capture maintains the saved transcript according to each command's registry-owned transcript mode and a bounded ANSI terminal snapshot; Redis-backed PTY owners also publish bounded snapshot payloads under the active stream TTL so reload recovery and Status Monitor Attach can restore the latest snapshot from any worker, then resume the live stream from the snapshot event id. PTY snapshot, input, resize, and stream paths cross-check active process metadata and prune stale Redis PTY state when the owning process disappears, so clients stop treating orphaned PTY metadata as recoverable live state. The original tab remains the command/history owner: it echoes the submitted command, listens for lifecycle events, keeps live redraw output inside the modal, and appends the saved static PTY transcript plus exit status after the run persists. That means a multi-worker deployment does not need request stickiness after the PTY starts: any worker can serve the SSE stream, input/resize controls, and active reattach snapshots because the file descriptor owner and the browser communicate through Redis. Without Redis, the PTY path remains an in-process single-worker development fallback.

Fast output bursts are rendered in small batches instead of forcing a full DOM update per line. The batching keeps commands like `man curl` responsive enough for the browser to repaint while output is streaming, and the terminal stays pinned to the bottom only while the user has not scrolled away. If the user scrolls up, live following stops until they return to the tail.

The brokered stream keeps the transport alive with heartbeat comments during idle periods, while the backend-owned worker drains subprocess stdout exactly once and publishes normalized `started`, `notice`, `output`, `exit`, and `error` events. The subprocess stdout reader uses a nonblocking buffered path rather than `select()` followed by `readline()`. That matters for tools that emit partial progress lines: partial output no longer wedges the drain waiting for a newline and starving the heartbeat stream. If a platform refuses nonblocking setup, the server warning-logs the fallback so a deployment that could stall on partial-line output leaves an operator-visible trail. On the browser side, `runner.js` treats 45 seconds of browser-visible silence as a potentially stalled stream, then checks `/history/active` before changing tab state. If the run is still active, the tab stays `RUNNING`, Kill remains available, and the warning copy says the process is still alive; only inactive runs fall back to the history/final-result recovery path. The async recovery path captures the tab/run generation before it awaits backend state and re-checks that generation before applying status, which prevents stale timeout promises from overwriting a newer run after rapid tab switches, kills, or restarts. If the same stream later resumes, the runner prints an explicit recovery notice and keeps the tab/HUD in the running state instead of leaving the UI failed-looking while output silently continues.

Active-run metadata is also the source for the Status Monitor's run section. `/history/active` returns the current run IDs, PIDs, commands, start times, metadata source, origin fields, and best-effort `psutil` resource telemetry when available. The backend reports summed RSS bytes and cumulative process-tree CPU seconds for the tracked process plus recursive children. `/history/insights` supplies bounded visual history payloads for the monitor's constellation, activity heatmap, command treemap, and event ticker without overfetching full history rows; the browser loads that heavier payload once on monitor open and refreshes it exactly once when the active-run count transitions `>0 → 0` in the same session, so a freshly completed run lands in the heatmap "today" cell, the treemap percentages, and the constellation without a polling timer. The desktop Status Monitor is a centered modal available from the rail, HUD cells, and `Alt+M`; mobile exposes the same monitor as a bottom sheet from the normal menu and running-tab peek. Both surfaces can open while idle and render system health, workspace quota, session statistics, visual history, a continuous glowing CPU-driven heartbeat strip, app-native constellation/day heatmap popovers, a seeded ambient constellation sky for sparse history, labeled calendar heat, and a `No active runs` row at the bottom. To avoid browser connection starvation when many tabs already hold live SSE streams, opening Status Monitor pauses non-active tab subscriptions and resubscribes them from the last broker event id on close; `/history/active` polling refreshes same-client origin liveness while those streams are paused. Runs already open in a local tab activate that tab when clicked; other visible current-session runs expose Attach to open a subscribed tab and Kill to terminate the backend process group intentionally. Closing a running tab opens a confirmation modal with `Keep running`, `Kill run`, and `Cancel`; `Keep running` detaches only that browser tab and leaves the backend run visible in Status Monitor for later reattach. The monitor calculates the displayed CPU percentage from adjacent poll samples in the browser and caps the display at 100%, which avoids per-worker CPU sample caches and keeps multi-worker deployments from flickering when successive polls land on different workers. Memory fill is normalized client-side against a 1 GB scale while the label continues to show the actual RSS value. Telemetry failures are intentionally non-fatal and omitted from the response rather than breaking reload recovery, stall checks, or the terminal `runs` command.

Two compact history endpoints feed the Status Monitor dashboard without exposing full run bodies. `/history/stats` returns current-session counters: `runs.total`, `runs.succeeded`, `runs.failed`, `runs.incomplete`, `runs.average_elapsed_seconds`, plus `snapshots`, `starred_commands`, and `active_runs`. SIGTERM-style `-15` exits are retained in totals but excluded from `failed` so user-killed, timeout-cleaned, or supervisor-stopped runs do not inflate failure visuals. `/history/insights` accepts `days=auto` or an integer clamped to 28-365 days. It returns `activity` day buckets for the selected window, `max_day_count`, capped `command_mix` data, capped recent-run `constellation` data, recent `events`, and a `windows` object that records the resolved activity, command-mix, and constellation ranges. Command mix uses 30 days, expanding to 90 days when fewer than 25 runs exist; constellation uses 30 days, expanding to 90 days when fewer than 40 plotted runs exist, and caps plotted stars at 350. Those resolved windows are part of the response so the UI can label sparse or expanded panels honestly. App built-ins (the command roots routed by the `builtin_commands` layer — `pwd`, `whoami`, `help`, …) are filtered server-side from `/history/insights` so all Status Monitor visualizations reflect real recon work only without each consumer reimplementing the filter.

### Output Prefixes And Follow State

Line numbers and timestamps are rendered from stored per-line metadata rather than by rebuilding transcript text. Each appended `.line` keeps timestamp attributes plus a stable `data-line-number` assigned at append time; trimming old rows at `max_output_lines` does not renumber the remaining DOM. The same per-line metadata can also carry server-classified signal scopes and extracted entities, so restored history and full-output artifacts keep public IP, hostname, hash, and CVE metadata beside the original text. The `data-prefix` attribute carries only the active timestamp fragment, and the shared prefix width is updated incrementally during normal appends while `syncOutputPrefixes()` is reserved for restore/toggle paths that intentionally revisit existing rows. Output appends flush in larger batches for bursty commands, offscreen rows opt into browser `content-visibility`, and live trimming uses a live row collection instead of snapshotting every `.line` on each append.

Welcome rows are excluded from normal prefix numbering, and `tab.runStart` is captured after the submitted prompt line is appended so elapsed timing applies only to run output.

### Kill Flow And Exit Reconciliation

Because commands run as `scanner` and Gunicorn runs as `appuser`, the web worker cannot directly signal `scanner`-owned processes. The kill path therefore uses `sudo -u scanner kill -TERM -<pgid>` so the signal is sent by the user that owns the process group.

This gets more important with multiple Gunicorn workers. The worker that receives `POST /kill` may not be the worker that launched the process. To solve that:

- `pid_register(run_id, pid)` writes the process id to Redis with a 4-hour TTL
- `pid_pop(run_id)` uses Redis `GETDEL` so lookup and removal are atomic
- any worker can therefore resolve and kill the correct process group without relying on shared in-memory state

When a user clicks Kill:

1. `doKill()` sets `tab.killed = true`, shows KILLED status
2. Server receives SIGTERM, process exits with code -15
3. SSE stream sends `exit` message with code -15
4. Exit handler checks `tab.killed` — if true, skips status update and resets flag

Without the `killed` flag, the `-15` exit code causes the exit handler to set status to ERROR, briefly flashing KILLED before reverting.

---

## Secrets and Vault

The encrypted-secrets vault is the single boundary between user-supplied API keys and the processes that consume them. Vault behavior is consumed by external command CLIs that declare `requires_secrets` in the registry and by the app-native `intel` built-in; both routes resolve secrets through the same code path before launch.

`/runs` resolves the original command root's secret declarations against the current session vault before validation-owned runtime wrappers can change the executed shell text. Required missing secrets or missing session identity block the launch; optional missing secrets log a warning. Found values are decrypted in memory and passed through `subprocess.Popen(env=...)`, never inserted into the shell command text. A declaration can look up one or more vault names and inject the value under a different runtime env name, which is how the VirusTotal CLI accepts either `VT_API_KEY` or `VTCLI_APIKEY` while receiving `VTCLI_APIKEY` in the child process. Optional declarations cover tools such as `ipinfo`, where unauthenticated output can still work but `IPINFO_TOKEN` unlocks richer account-backed results. The urlscan-cli and Chaos CLI wrappers use the same boundary for `URLSCAN_API_KEY` and `PDCP_API_KEY`, with setup/key-writing commands blocked by policy so keys stay in the app vault instead of vendor config files or argv. The command catalog exposes this metadata without values so the Options Secrets picker can suggest known tool keys before falling back to a custom name. In the container scanner path, sudo preserves only the declared secret env names so the scanner process receives them without exposing values in argv or preserving unrelated app env. Interactive PTY registry entries cannot also declare `requires_secrets`; registry loading rejects that combination because the PTY path does not inject secret environment variables. Successful secret use emits one `SECRET_INJECTED` audit event for the run with env names only.

Storage shape, encryption, and master-key bootstrap are described under the `secrets` table in **State And Persistence**: AES-GCM ciphertext, per-row nonce, `(session_token, name)` uniqueness, and a `consumer_envs` binding that prevents two secrets from claiming the same runtime env name in one session. The wrapping key comes from `SECRETS_MASTER_KEY` or `<data_dir>/.secrets_master_key`, with HKDF-SHA256 deriving the row-encryption key; the file is created or repaired at `0600` when used.

---

## Intel and Provider Integrations

The app-native `intel` built-in uses the same encrypted-secret boundary as external CLIs but does not spawn a provider CLI. `app/services/intel/registry.py` owns provider metadata such as labels, supported entity types, secret env names and aliases, access notes, cache scopes, rate-limit config keys, and provider usage labels. `app/services/intel/lookup.py` canonicalizes requested IP, domain, URL, hash, and CVE values; verifies required provider secrets for the current session; checks Redis-backed cache and quota state; applies per-session provider token buckets; calls the app-native provider clients for Shodan, Censys, GreyNoise, VirusTotal, AlienVault OTX, AbuseIPDB, IPinfo, Team Cymru, crt.sh, HIBP Pwned Passwords, NVD, URLhaus, ThreatFox, Vulners, urlscan.io, SecurityTrails, and RouteViews; stores normalized provider responses; and emits redacted `INTEL_LOOKUP` audit events. The HTTPS clients use the configured CA environment when present and otherwise prefer the system CA bundle, so container builds with source-built OpenSSL still verify provider certificates against the OS trust store. Missing keyed providers render as terminal placeholders beside configured provider results, optional-key providers can still run with public data, and no-key providers participate in fan-out with the same cache and rate-limit protections. The same provider metadata feeds the Options Secrets picker, the Options Provider Status modal, `secret show-consumers`, and the `providers` alias, so users can see which app-native and CLI-backed providers are usable before running lookups or provider CLIs.

The terminal command fans out by entity type. Private, loopback, and other non-public IPs are blocked before provider lookup unless the user passes `--include-private`.

| Command | Providers |
| --------- | --------- |
| `intel ip <ip>` | Shodan, Censys, GreyNoise, AlienVault OTX, AbuseIPDB, IPinfo, Team Cymru, URLhaus, ThreatFox, RouteViews |
| `intel domain <domain>` | VirusTotal, AlienVault OTX, crt.sh, urlscan.io, URLhaus, ThreatFox, SecurityTrails |
| `intel url <url>` | urlscan.io, URLhaus, ThreatFox |
| `intel hash <md5\|sha1\|sha256>` | VirusTotal, AlienVault OTX, HIBP Pwned Passwords for SHA1 only, URLhaus, ThreatFox |
| `intel cve <CVE-ID>` | NVD, Vulners |

### Provider Directory

The provider table covers both app-native `intel` providers and provider CLI wrappers exposed through the command registry. App-native and CLI-backed rows feed the Options Provider Status modal, `secret show-consumers`, and the `providers` alias, and their secret metadata feeds the command catalog and Options Secrets suggestions. "No" in the API key column means the app-native provider works without a stored session secret, but the app still applies its own cache and per-session token bucket before calling the third-party service. "Optional" means the lookup or CLI can run without a key but gets richer account-backed results when the session vault has one.

| Provider | Used by | API key required | Accepted secret names | Access note | Darklab use |
| --------- | --------- | --------- | --------- | --------- | --------- |
| Shodan | `ip`, `shodan` CLI | Yes | `SHODAN_API_KEY` | Free signup; paid tiers | Host ports, banners, CVEs, tags, organization, and ISP context |
| Censys | `ip` | Yes | `CENSYS_PAT`, optional `CENSYS_ORGANIZATION_ID` | Account-backed; paid tiers | Platform host services, protocols, location, names, ASN, and ownership context, with optional org-scoped requests |
| GreyNoise | `ip`, `greynoise` CLI | Yes | `GREYNOISE_API_KEY` | Free community key | Internet-noise classification, actor, tags, and last-seen context |
| AlienVault OTX | `ip`, `domain`, `hash` | Yes | `OTX_API_KEY` | Free signup | Pulse counts, malware families, tags, and indicator metadata |
| AbuseIPDB | `ip` | Yes | `ABUSEIPDB_API_KEY` | Free signup; paid tiers | Abuse confidence, report counts, usage type, ISP, and country context |
| Team Cymru | `ip` | No | None | Free public lookup | DNS TXT origin and ASN-description lookups for IP-to-ASN ownership |
| RouteViews | `ip` | No | None | Free public lookup | Prefix, origin ASN, collector, and RPKI-style BGP context |
| IPinfo | `ip`, `ipinfo` CLI | Optional | `IPINFO_TOKEN` | Free unauthenticated basics; account token optional | IP geolocation, ASN, ownership, hostname, and account-backed context through app-native lookups and the `ipinfo` CLI |
| VirusTotal | `domain`, `hash`, `vt` CLI | Yes | `VT_API_KEY`, `VTCLI_APIKEY` | Free signup; paid tiers | Domain reputation, analysis stats, recent URLs, WHOIS summary, and file/hash reputation |
| crt.sh | `domain` | No | None | Free public lookup | Certificate Transparency certificate names, issuers, and first/last sightings |
| urlscan.io | `domain`, `url`, `urlscan-cli` CLI | Yes | `URLSCAN_API_KEY` | Free signup; paid tiers | Read-only search/result context for observed pages and verdicts; app-native scan submission is not enabled |
| URLhaus | `ip`, `domain`, `url`, `hash` | Yes | `URLHAUS_AUTH_KEY` | Free abuse.ch Auth-Key | Malware URL, host, and payload-hash status from abuse.ch |
| ThreatFox | `ip`, `domain`, `url`, `hash` | Yes | `THREATFOX_AUTH_KEY` | Free abuse.ch Auth-Key | IOC and malware context for hosts, URLs, IPs, and hashes |
| SecurityTrails | `domain` | Yes | `SECURITYTRAILS_API_KEY` | Paid account required | DNS records, WHOIS summary, and subdomain pivots |
| ProjectDiscovery Chaos | `chaos` CLI | Yes | `PDCP_API_KEY` | ProjectDiscovery Cloud account key | Provider-native known-subdomain lookups through the `chaos` CLI, with key-writing and file-output flows blocked by policy |
| HIBP Pwned Passwords | `hash` | No | None | Free public lookup | SHA1 k-anonymity range lookups; only the first five SHA1 characters are sent |
| NVD | `cve` | No | None | Free public lookup | CVE severity, scores, summaries, dates, and references |
| Vulners | `cve` | Yes | `VULNERS_API_KEY` | Free signup; paid tiers | CVE document and exploitability context beyond NVD |

Atlas entity detail responses include a backend-derived `intel_summary` built from these cached provider snapshots, so the detail view can render provider-grouped high-signal fields without re-querying providers on every open. The `/atlas/entities/<entity_id>/refresh_intel` route writes through the same provider orchestration used by the terminal command.

---

## Session Workspace and Files

The session workspace is the per-session file scratchpad that command rewrites, file built-ins, and the Files panel all share. Workspaces live under the configured `workspace_root`, one hashed `sess_*` directory per session, with the runtime `0730` mode on the root and `3730` on the hashed session directories. App-created files sit at `0640`; command-created files that the `scanner` user must still write to land at `0660` through the shared `appuser` run group.

For workspace-backed host bind mounts, the host path should already be owned by the numeric UID/GID for the image's `appuser` account. The current image creates `appuser` as `995:995` and `scanner` as `994:994`, and launches scanner commands with the shared `appuser` run group when executing user commands. The runtime still attempts to repair ownership and modes on startup, including files directly inside each `sess_*` directory, but pre-setting the bind mount keeps rootless Docker, NFS-like mounts, and stricter host policies from leaving the workspace root owned by `root:root`. Permission-repair failures are warning-logged rather than swallowed, and startup warning-logs if the `WORKSPACE_ROOT` environment value prepared by the entrypoint differs from the app's configured `workspace_root`.

Workspace cleanup is request-driven rather than a separate daemon. Each worker checks periodically before handling a request, then calls the backend cleanup helper when workspace storage is enabled. Cleanup evaluates the hashed session directory mtime as the workspace activity marker and only deletes resolved `sess_*` roots under the configured workspace root. Normal workspace path resolution rejects symlink components before use, and file reads/downloads also open the final component with no-follow semantics where the platform supports it so a same-principal symlink swap cannot escape the session root between validation and open.

Workspace move and glob behavior stays app-mediated too. `move_workspace_path()` resolves both source and destination through the same session-root checks used by reads and deletes, rejects overwrites, rejects symlink escapes, prevents moving a folder into itself, and falls back to the scanner user for command-owned files that need group-write movement. Browser-side `file ls`, `file move` / `mv`, and confirmed `file delete` expand simple `*` patterns from the loaded session workspace cache for fast terminal feedback; backend built-ins use `expand_workspace_path_pattern()` so stale-browser or server-rendered paths follow the same one-segment matching rule. The shell never asks `/bin/sh` to expand workspace patterns. Before list/read-style operations, `normalize_session_workspace_permissions()` also repairs scanner-created child modes so tool config folders written under session-scoped `XDG_CONFIG_HOME` remain visible to the app without making the workspace world-readable.

Workspace-aware validation in **Run Lifecycle** rewrites declared file and directory flags from `commands.yaml` into the active session workspace; the same metadata declares the managed workspace directories (Amass `-dir tools/amass`, ProjectDiscovery `XDG_CONFIG_HOME=<workspace>/tools`) that share per-session state across the CLI and engine paths. Persistent file-artifact rows live in `run_file_artifacts`, described in **State And Persistence**.

---

## Projects Workspace

Project workspace tables are the relationship foundation for case-style grouping. Projects link to completed runs and Atlas entities instead of copying them, so source records can remain usable outside any project and can belong to more than one project when that is useful. Snapshots and manually selected workspace files remain in their share/history/files surfaces and are not project-linked. Run-owned artifacts stay attached to their source run and surface in project views through linked runs; findings surface through linked runs or linked Atlas entities so entity-first triage and project triage stay aligned.

`project_links` is a generic membership table `(project_id, entity_type, entity_id)` shared across `run` and `atlas_entity` entity types — there is no parallel per-feature membership table. Atlas-entity links also carry target-list metadata such as source, confidence, review state, and source detail so the Projects modal can keep its target workflow without a separate target table. Evidence packages (`evidence_packages`) record draft package manifests scoped to a project and session, capture redaction mode and artifact-inclusion preference, and export the manifest plus any still-available selected workspace artifacts as a downloadable archive. Project-level labels and notes use the generic `entity_labels` / `entity_notes` tables with `entity_type='project'`.

The full route surface is enumerated in **HTTP Route Inventory → Project Routes**. Schema shapes for `projects`, `project_links`, and `evidence_packages` live in **State And Persistence → Database**. Atlas entity linkage from the project side is covered in **Atlas and Entity Model**.

---

## Atlas and Entity Model

Atlas is the entity-first triage surface that turns saved external-run output into a session-scoped, deduplicated graph of public IPs, domains, URLs, hashes, and CVEs. Runs are the *source* of entities; projects are a *curated subset*; the active session token owns the entity graph.

**Materialization.** Entity rows are written at run-finalize time from classifier-extracted ranges, deduplicated by `(session_id, type, signature_hash)`, and joined to runs through `entity_run_links` with per-run first/last-seen timestamps and occurrence counts. Materialization is idempotent so re-finalizing a run does not double-count. Builtin runs do not produce entities — only external-run output participates in materialization. The full schema is described under **State And Persistence → Database**.

**Surface.** `static/js/features/atlas/` owns the top-level Atlas overlay used from the desktop rail, mobile menu, `Alt+A`, History actions, Run Details, project-filtered launches from Projects, and entity tokens rendered inside transcripts. The Atlas surface lists deduped session entities by type, opens an entity detail side sheet, refreshes app-native intel snapshots, links entities to the active project, exports filtered entity rows as CSV or JSONL, and edits labels/notes through `ui_entity_metadata.js`. Entity detail responses include a backend-derived `intel_summary` built from the latest normalized provider snapshots, so the detail view can show compact provider-grouped high-signal fields while expandable provider cards keep the full structured per-provider detail close by. Its dedicated tab row uses the same tab primitive as Run Details, and its left-side entity/finding lists use the same full-width row treatment as the History drawer. Its Findings tab reads the same unified `findings` table as Projects and Run Details, gives users a cross-run triage queue with review-state and orphan-source filters, and supports single or visible-page bulk review updates. All Atlas tabs share History-style select mode for visible-page bulk deletion; entity bulk delete also removes findings attached to the selected entities. The detail view can delete one entity or finding, and the confirmation can also sweep non-curated sibling Atlas items that only came from the same source run. The desktop split is tab-aware: Findings keeps the wide queue on the left, while entity tabs narrow the index column and give the detail/intel pane most of the width. Mobile Atlas uses the same controller state with a dedicated list/detail drill-in surface in `atlas_mobile.js` and `atlas-mobile.css`: tabs, filters, select mode, action sheets, Back navigation, and detail-first launches are rendered as mobile-native views instead of collapsing the desktop split. `output.js` decorates classifier-provided entity ranges as transcript tokens and routes token clicks, long-presses, and context menus into Atlas. `static/css/features/atlas.css` and `static/css/features/atlas-mobile.css` keep the surface and transcript-token actions on the same sheet/menu primitives as History, Projects, and Status Monitor.

**Intel snapshots.** Per-entity cached intel data lives in `entity_intel_snapshots`, keyed `(entity_id, provider)` so refresh, expiry, and per-provider quota stories stay tractable. The refresh route writes through the same provider orchestration used by the terminal `intel` command — see **Intel and Provider Integrations**.

**Findings model.** `findings` is a single entity-owned table deduped across runs by a stable signature; `findings_occurrences` records per-run sightings. The Projects modal, Run Details, and the Atlas Findings tab all read this same table so review state never drifts between surfaces. Project linkage for findings flows through linked source runs or linked Atlas entities, not separate finding membership rows.

**Run-delete cleanup and orphan model.** Deleting a run removes its `entity_run_links` and `findings_occurrences` rows but leaves the parent entity and finding rows in place so labels, notes, project links, and triage state survive transcript pruning. Run-delete confirmations can opt in to also remove non-curated entities and findings whose only source run was the deleted one; curated items (labels, notes, project links, non-`new` triage status) are always kept. Atlas surfaces expose an orphan-source filter so operators can audit entities and findings whose source runs have all been deleted, and the entity/finding delete confirmations can sweep non-curated siblings whose only source run is the same as the selected item.

**Project linkage.** Project membership for Atlas entities flows through the generic `project_links` table with `entity_type='atlas_entity'`. There is no separate per-entity project table; promotion from Atlas to a project is a tag on the entity row, not a copy.

### Export Schema

Atlas can export the current session's entity rows as CSV or JSONL for handoff, offline review, and quick spreadsheet work. Exports include entity summary fields and lightweight metadata but do not include raw provider response bodies.

**Endpoint.** `GET /atlas/entities/export` is session-scoped — it only returns entities owned by the current browser session or named session token.

**Query parameters.**

| Parameter | Values | Default | Notes |
| --- | --- | --- | --- |
| `format` | `csv`, `jsonl` | `csv` | Controls the file format. |
| `type` | `ip`, `domain`, `url`, `hash`, `cve` | all types | Matches the Atlas entity tabs. |
| `q` | text | empty | Filters by canonical entity value. |
| `project_id` | project id | empty | Limits results to entities linked to that project. |
| `orphan_filter` | `hide`, `all`, `only` | `hide` | Controls whether rows without a live source run are hidden, included, or exported by themselves. |
| `limit` | `1` to `10000` | `10000` | Caps the number of exported rows. |

The Atlas UI sends the same `type`, search text, project filter, and orphan-source filter that are active in the entity tab when the user clicks **CSV** or **JSONL**.

**Schema.**

| Field | CSV | JSONL | Description |
| --- | --- | --- | --- |
| `id` | string | string | Atlas entity id. |
| `type` | string | string | Entity type: `ip`, `domain`, `url`, `hash`, or `cve`. |
| `canonical_value` | string | string | Normalized entity value. |
| `first_seen_at` | string | string | First time Atlas saw the entity in this session. |
| `last_seen_at` | string | string | Most recent time Atlas saw the entity in this session. |
| `occurrence_count` | number | number | Total materialized occurrences across saved source runs. |
| `labels` | `; ` separated string | array | Labels attached to the Atlas entity. |
| `notes` | string | string | The entity note body, if one exists. |
| `project_names` | `; ` separated string | array | Projects linked to the entity. |
| `intel_providers_with_data` | `; ` separated string | array | Provider names whose cached Atlas intel snapshot contains usable data. |

CSV uses a header row and semicolon-separated strings for list fields so the file opens cleanly in spreadsheet tools. JSONL emits one JSON object per line and keeps list fields as arrays.

**Redaction.** Atlas exports are session-owned working files, so they include the visible Atlas entity values and metadata from the current filtered view. They include provider names that have usable cached intel, but they do not include raw intel response bodies. Treat CSV and JSONL exports as raw triage data: entity values, labels, notes, and project names are exported as shown in Atlas.

---

## State And Persistence

This section groups durable server state, browser-owned session state, session identity, and reload continuity into one model of where state lives and how it survives reloads or moves between devices.

### Persistence Model

The key architectural distinction is that the app does not use one monolithic store for everything. It deliberately splits fast interactive state, durable share state, and optional full-output storage so each surface can stay efficient without losing fidelity where it matters.

```mermaid
flowchart TB
  Runs["runs table"]
  Snapshots["snapshots table"]
  ArtifactRows["artifact rows"]
  Files["gzip full-output files"]

  Runs -->|interactive history + restore queries| Hist["History consumers"]
  Runs -->|canonical run retrieval| RunPage["Run permalink consumers"]
  Snapshots -->|snapshot retrieval| SharePage["Snapshot permalink consumers"]
  ArtifactRows --> Files
  ArtifactRows -->|full-output lookup| RunPage
```

The persistence model is intentionally split:

- `runs` stores fast, capped preview data for the interactive UI
- `snapshots` stores share-specific captured state
- `run_output_artifacts` plus gzip files store optional full output without bloating the main `runs` table

That split is what allows the app to keep the interactive shell fast while still supporting durable full-output permalinks and exports.

### Database

SQLite is the default database backend and stores data in `<data_dir>/history.db` with WAL mode, twenty-two persistent tables, one FTS5 virtual table, and file-backed run-output artifacts. `data_dir` is an operator config key; when unset, the app uses writable `/data` and falls back to `/tmp` for local/dev runs where the image-created `/data` directory is not mounted writable. Postgres is the supported production-scaling backend for deployments that need a server database. The server has a `database_backend` selector and a database backend/dialect helper for connection setup, JSON column types and parameters, boolean storage and parameters, timestamps, placeholders, `IN` clauses, limit/offset clauses, upsert clauses, text search expressions, concatenation, SQLite diagnostics, Postgres identifier quoting, advisory-lock IDs, lazy psycopg pool setup, `pg_trgm` availability checks, and storage rows. History search has a backend-aware SQL helper: SQLite keeps its FTS5-first path with `LIKE` fallback for short terms, while Postgres uses substring `ILIKE` clauses backed by trigram indexes. Atlas entity and finding searches use the same backend-aware substring shape so Postgres can use trigram indexes for entity values and finding text. The History list, command recents, stats routes, terminal `stats` built-in, completed-run inserts, full-output artifact metadata writes, snapshot share routes, session preferences, recent values, starred commands, user workflows, secret session migration path, Projects workspace create/link/target paths, Files metadata paths, Atlas list/detail/finding paths, `/diag`, and `/metrics` use the normal backend-aware app query path on both SQLite and Postgres. Postgres startup runs app-owned migrations from `app/core/migrations/` behind a transaction-scoped advisory lock; the first migration is a baseline schema for the current app tables, indexes, JSONB columns, booleans, bytea secret payloads, and triggers, the second adds `pg_trgm` run-history search indexes, and the third adds Atlas entity/finding search indexes. When `database_backend` is `postgres`, normal app `db_connect()` calls go through the Postgres pool with an app-compatibility wrapper for the existing `?` placeholder style and a narrow read-only transient-error retry.

Logical relationships are owned by the app rather than SQLite foreign-key constraints. Anonymous browser sessions can appear as `session_id` values without a matching `session_tokens` row.

Project workspace tables are the relationship foundation for case-style grouping. Projects link to completed runs and Atlas entities instead of copying them, so source records can remain usable outside any project and can belong to more than one project when that is useful. Snapshots and manually selected workspace files remain in their share/history/files surfaces and are not project-linked. Run-owned artifacts stay attached to their source run and surface in project views through linked runs; findings surface through linked runs or linked Atlas entities.

The schema is shown as one compact topology diagram for the full relationship model, then three field-level diagrams for the clusters where column shapes carry real meaning. The diagrams use SQLite table names for the default backend. Postgres creates the same app-owned tables through migrations plus `schema_migrations`, but it does not create `runs_fts`; Postgres run search uses `pg_trgm` GIN indexes on `runs.command` and `runs.output_search_text`, and Atlas search uses trigram indexes on entity values plus finding title/raw-line/tool fields. Per-table field reference continues in the prose list below.

#### Schema topology

Every app-owned persistent table in the default SQLite topology and its relationships, without field bodies. `LOGICAL_SESSION` is the shared `session_id` value rather than a stored table.

```mermaid
erDiagram
  SESSION_TOKENS ||--o| LOGICAL_SESSION : "named token"
  LOGICAL_SESSION ||--o| SESSION_PREFERENCES : "stores"
  LOGICAL_SESSION ||--o{ STARRED_COMMANDS : "stars"
  LOGICAL_SESSION ||--o{ SESSION_VARIABLES : "defines"
  LOGICAL_SESSION ||--o{ USER_WORKFLOWS : "saves"
  LOGICAL_SESSION ||--o{ RECENT_VALUES : "remembers"
  LOGICAL_SESSION ||--o{ SECRETS : "stores encrypted"
  LOGICAL_SESSION ||--o{ RUNS : "owns"
  LOGICAL_SESSION ||--o{ SNAPSHOTS : "owns"
  LOGICAL_SESSION ||--o{ RUN_FILE_ARTIFACTS : "tracks"
  LOGICAL_SESSION ||--o{ ENTITIES : "indexes"
  LOGICAL_SESSION ||--o{ FINDINGS : "captures"
  LOGICAL_SESSION ||--o{ ENTITY_LABELS : "labels"
  LOGICAL_SESSION ||--o{ ENTITY_NOTES : "notes"
  LOGICAL_SESSION ||--o{ PROJECTS : "owns"
  LOGICAL_SESSION ||--o{ EVIDENCE_PACKAGES : "packages"
  RUNS ||--o| RUN_OUTPUT_ARTIFACTS : "full output"
  RUNS ||--o| RUNS_FTS : "search index"
  RUNS ||--o{ RUN_FILE_ARTIFACTS : "creates"
  RUNS ||--o{ FINDINGS : "emits"
  RUNS ||--o{ ENTITY_RUN_LINKS : "mentions"
  ENTITIES ||--o{ ENTITY_RUN_LINKS : "seen in"
  ENTITIES ||--o{ ENTITY_INTEL_SNAPSHOTS : "caches"
  ENTITIES ||--o{ FINDINGS : "subject of"
  FINDINGS ||--o{ FINDINGS_OCCURRENCES : "seen in runs"
  PROJECTS ||--o{ PROJECT_LINKS : "membership"
  PROJECTS ||--o{ EVIDENCE_PACKAGES : "exports"
```

`ENTITY_LABELS` and `ENTITY_NOTES` are polymorphic on `(entity_type, entity_id)` and attach to several record types — projects, runs, snapshots, workspace files, run file artifacts, Atlas entities, findings, and packages — without separate FKs per type, which is why they sit under `LOGICAL_SESSION` rather than chaining off one specific parent.

#### Atlas entity model

Entity-first triage tables. `ENTITIES` is the deduped session-scoped record; `ENTITY_RUN_LINKS` is the many-to-many to source runs; `ENTITY_INTEL_SNAPSHOTS` caches normalized provider responses; `FINDINGS` are entity-owned signature-deduped findings with per-run sightings in `FINDINGS_OCCURRENCES`.

```mermaid
erDiagram
  ENTITIES {
    TEXT id PK
    TEXT session_id
    TEXT type
    TEXT canonical_value
    TEXT signature_hash
    TEXT first_seen_at
    TEXT last_seen_at
    INTEGER occurrence_count
    TEXT created
  }
  ENTITY_RUN_LINKS {
    TEXT entity_id PK
    TEXT run_id PK
    TEXT first_seen_at
    TEXT last_seen_at
    INTEGER occurrence_count
  }
  ENTITY_INTEL_SNAPSHOTS {
    TEXT id PK
    TEXT session_id
    TEXT entity_id
    TEXT provider
    TEXT status
    TEXT summary
    TEXT data_json
    TEXT fetched_at
    TEXT expires_at
  }
  FINDINGS {
    TEXT id PK
    TEXT session_id
    TEXT run_id
    TEXT entity_id
    TEXT subject_key
    TEXT signature_hash
    TEXT severity
    TEXT kind
    TEXT tool_root
    TEXT first_run_id
    TEXT last_run_id
    TEXT first_seen_at
    TEXT last_seen_at
    INTEGER occurrence_count
    TEXT status
    TEXT status_updated_at
    TEXT review_state
    TEXT fingerprint
    TEXT title
    TEXT raw_line
    TEXT created
  }
  FINDINGS_OCCURRENCES {
    TEXT finding_id
    TEXT run_id
    INTEGER line_number
    TEXT snippet
    TEXT seen_at
  }
  ENTITIES ||--o{ ENTITY_RUN_LINKS : "seen in"
  ENTITIES ||--o{ ENTITY_INTEL_SNAPSHOTS : "caches"
  ENTITIES ||--o{ FINDINGS : "subject of"
  FINDINGS ||--o{ FINDINGS_OCCURRENCES : "seen in runs"
```

#### Run output and workspace artifacts

Run history with its two artifact families. `RUN_OUTPUT_ARTIFACTS` points at gzip-compressed full transcripts under `<data_dir>/run-output/`; `RUNS_FTS` is the SQLite-only FTS5 content table backing history search; `RUN_FILE_ARTIFACTS` tracks workspace files produced or consumed by a run. Postgres search uses trigram indexes instead of an FTS table. `SNAPSHOTS` is a sibling share/permalink record without an FK to `RUNS`.

```mermaid
erDiagram
  RUNS {
    TEXT id PK
    TEXT session_id
    TEXT run_kind
    TEXT owner_tab_id
    TEXT command
    TEXT started
    TEXT finished
    INTEGER exit_code
    TEXT output_preview
    TEXT output_search_text
  }
  RUN_OUTPUT_ARTIFACTS {
    TEXT run_id PK
    TEXT rel_path
    TEXT compression
    INTEGER byte_size
    INTEGER line_count
    INTEGER truncated
    TEXT created
  }
  RUNS_FTS {
    INTEGER rowid PK
    TEXT command
    TEXT output_search_text
  }
  RUN_FILE_ARTIFACTS {
    TEXT id PK
    TEXT session_id
    TEXT run_id
    TEXT workspace_path
    TEXT display_name
    TEXT kind
    INTEGER byte_size
    TEXT detected_by
    TEXT content_type
    TEXT preview_type
    TEXT content_sha256
    TEXT created
  }
  RUNS ||--o| RUN_OUTPUT_ARTIFACTS : "gzip transcript"
  RUNS ||--o| RUNS_FTS : "search index"
  RUNS ||--o{ RUN_FILE_ARTIFACTS : "creates"
```

#### Projects and shared metadata

Project workspace tables plus the polymorphic metadata layer. `PROJECT_LINKS` carries the membership shape `(project_id, entity_type, entity_id)` and the Atlas-target metadata columns. `ENTITY_LABELS` and `ENTITY_NOTES` use `(entity_type, entity_id)` to attach to many record types without per-type FKs — including the records shown in the other diagrams.

```mermaid
erDiagram
  PROJECTS {
    TEXT id PK
    TEXT session_id
    TEXT name
    TEXT slug
    TEXT description
    TEXT status
    TEXT color
    TEXT created
    TEXT updated
  }
  PROJECT_LINKS {
    TEXT id PK
    TEXT project_id
    TEXT entity_type
    TEXT entity_id
    TEXT source
    REAL confidence
    TEXT review_state
    TEXT source_detail
    TEXT created
    TEXT updated
  }
  EVIDENCE_PACKAGES {
    TEXT id PK
    TEXT session_id
    TEXT project_id
    TEXT name
    TEXT description
    TEXT redaction_mode
    INTEGER include_artifacts
    TEXT manifest
    TEXT status
    TEXT created
    TEXT updated
  }
  ENTITY_LABELS {
    TEXT id PK
    TEXT session_id
    TEXT entity_type
    TEXT entity_id
    TEXT label
    TEXT source
    TEXT created
  }
  ENTITY_NOTES {
    TEXT id PK
    TEXT session_id
    TEXT entity_type
    TEXT entity_id
    TEXT body
    TEXT created
    TEXT updated
  }
  PROJECTS ||--o{ PROJECT_LINKS : "membership"
  PROJECTS ||--o{ EVIDENCE_PACKAGES : "exports"
```

- `runs` — one row per completed command. Stores run metadata, including `run_kind` (`builtin` or `external`) so history filters, project links, and finding capture can use a durable classification instead of re-reading the command text. It also stores `owner_tab_id` for completed runs that came from a terminal tab, which lets terminal-native commands such as `project link run last` resolve "last" within the tab that issued the command. It also stores a capped `output_preview` JSON payload for the history drawer and `/history/<id>`. Fresh previews store structured `{text, cls, tsC, tsE}` entries plus optional signal and entity metadata so run permalinks can preserve prompt echo, timestamp metadata, scoped findings, and extracted public IP/domain/hash/CVE hints. The preview is capped by both `max_output_lines` and `output_preview_max_mb`, which protects the default SQLite database from huge single-line outputs while full artifacts retain the larger text when enabled. Also stores `output_search_text` (plain text extracted from the full artifact when available, otherwise the preview) for backend search indexing. When `runs_search_text_inline_max_bytes` is set, oversized search bodies move to `data_dir/body-store` and the column keeps pointer metadata plus a short preview. Persists across restarts. Pruned by `permalink_retention_days`.
- `runs_fts` — SQLite-only FTS5 virtual table (content table backed by `runs`, `content_rowid=rowid`) indexing the `command` and `output_search_text` columns. Uses the trigram tokenizer when available (SQLite ≥ 3.38), falling back to unicode61. Kept in sync with `runs` via INSERT/DELETE triggers. Enables history drawer full-text search across both command text and stored run output on SQLite. Postgres does not create this table; its migrations create `pg_trgm` GIN indexes for the same command/output substring search behavior and for Atlas entity/finding substring search.
- `schema_migrations` — Postgres-only migration bookkeeping table. It records app-owned migration versions so startup and the SQLite-to-Postgres migration helper can verify that a destination schema has the expected baseline before app data is copied.
- `run_output_artifacts` — metadata rows pointing at compressed full-output artifacts under `<data_dir>/run-output/`. This keeps the `runs` table lean while still allowing the canonical `/history/<id>` permalink to serve full output when it exists.
- `snapshots` — one row per tab permalink (`/share/<id>`). Contains `{text, cls, tsC, tsE}` objects with raw ANSI codes and timestamp data for accurate HTML export reproduction, and now feeds the `SNAPSHOT` rows in the shared history surfaces. When `snapshots_inline_max_bytes` is set, oversized snapshot bodies move to `data_dir/body-store` while share links still read through the pointer.
- `session_tokens` — one row per issued named session token `(token TEXT PRIMARY KEY, created TEXT)`. Used to validate `tok_`-prefixed `X-Session-ID` headers and to support `session-token list` and `session-token revoke`.
- `session_preferences` — one row per session ID `(session_id TEXT PRIMARY KEY, preferences TEXT, updated TEXT)`. Stores the normalized Options snapshot that follows a named session token across browsers while still allowing browser-local UUID sessions to keep independent defaults.
- `starred_commands` — one row per starred command per session `(session_id, command)`. Backs the `/session/starred` endpoints and follows session tokens across devices via the migration path.
- `session_variables` — one row per session command variable `(session_id, name, value, updated)`. Backs the `var` built-in, `/session/variables`, and app-managed command expansion before validation.
- `user_workflows` — one row per saved workflow `(id, session_id, title, description, inputs, steps, created, updated)`. Backs the Workflows panel's **My workflows** section, the `workflow` terminal command, and session-token migration.
- `recent_values` — one row per recently used autocomplete value per session `(session_id, kind, value, last_used, use_count)`. `kind` is one of `domain`, `ip`, `url`, or `port_set`; each kind is capped independently at 10 entries. URL recents keep the scheme, host, and path but drop query strings and fragments before storage.
- `secrets` — one row per encrypted secret name per session `(session_token, name, ciphertext, nonce, consumer_envs, created_at, updated_at)`, with a unique `(session_token, name)` binding so replacing a secret updates the existing row. Storage also rejects attempts to bind the same consumer env name to two different secrets in one session, keeping command-time lookup unambiguous. Values are AES-GCM ciphertext and are never returned by list routes or stored in transcripts. The wrapping key comes from `SECRETS_MASTER_KEY` or `<data_dir>/.secrets_master_key`, with a fixed HKDF-SHA256 app context deriving the key used for row encryption. When the key file is used, the app creates or repairs it with `0600` permissions.
- `projects` — one row per project/case folder. Stores session ownership, display metadata, status, timestamps, and a session-scoped slug. Project notes are stored through `entity_notes` with `entity_type='project'`.
- `project_links` — generic project membership rows `(project_id, entity_type, entity_id)`. The app owns the valid entity vocabulary and link sources so projects can link completed runs and Atlas entities without copying source data. Atlas-entity links also carry target-list metadata such as source, confidence, review state, and source detail so the Projects modal can keep its target workflow without a separate target table. Run-owned file artifacts are intentionally reached through linked runs, while findings are reached through linked runs or linked Atlas entities instead of direct project links.
- `entities` — session-scoped Atlas rows for normalized public IPs, domains, URLs, hashes, and CVEs extracted from saved external-run output metadata. The app stores a canonical value, a stable signature hash, first/last seen timestamps, and an aggregate occurrence count so entity lists are deduplicated across runs.
- `entity_run_links` — many-to-many Atlas source links from entities to runs, with first/last seen timestamps and per-run occurrence counts. Run pruning removes these link rows while leaving the deduplicated entity row available for labels, notes, project links, and future intel snapshots. Run-delete confirmations can also remove non-curated entities and findings that only came from the deleted run; curated items are kept.
- `entity_intel_snapshots` — cached, normalized provider snapshots attached to an Atlas entity. The row shape stores provider name, status, short summary, JSON payload, fetch time, and expiry time so Atlas detail views can render intel cards without re-querying providers on every open. When `intel_payload_inline_max_bytes` is set, oversized provider JSON moves to `data_dir/body-store` and detail reads resolve the pointer before rendering. Atlas derives compact `intel_summary` highlights from these rows at read time instead of storing duplicate summary columns. The refresh route writes through the same app-native intel provider orchestration used by the `intel` terminal command.
- `run_file_artifacts` — durable file manifest rows for workspace files produced or consumed by a run, including recorded size and optional SHA-256 content checksum so project views can flag missing or changed workspace files. This is separate from `run_output_artifacts`, which stores the terminal transcript artifact behind a run permalink.
- `findings` — entity-owned finding rows deduped across runs by a stable signature. Findings keep a primary Atlas entity when one is available, an unscoped subject key when one is not, first/last run IDs, first/last seen timestamps, occurrence count, severity, status, and lightweight title/raw-line context. The Projects modal, Run Details, and Atlas read the same table, so finding review state does not drift between surfaces.
- `findings_occurrences` — per-run sightings for findings, keyed by finding, run, and line number. Run pruning removes these occurrence rows while leaving the parent finding row in place so labels, notes, and triage state can survive after the original transcript ages out.
- `entity_labels` — short user-controlled labels/bookmarks for supported entities, including Atlas entities, projects, runs, snapshots, workspace files, run file artifacts, findings, targets, and packages.
- `entity_notes` — one private note attached to each supported entity per session, including Atlas entities and project notes. Notes are intentionally singular so entity metadata remains an editable note surface instead of a comment thread.
- `evidence_packages` — draft package manifests scoped to a project and session. The first pass records package name/description, redaction mode, artifact-inclusion preference, and a JSON manifest over the currently linked project data, then exports that manifest plus any still-available selected workspace artifacts as a downloadable archive. Package-level labels/notes are stored through the generic entity metadata tables.
- Supporting indexes are part of the schema even though the ER diagram stays table-focused. `idx_runs_session_command_started` backs the Recent menu and prompt-history distinct-command query shape `(session_id, command, started DESC)`, `idx_runs_session_kind_started` backs built-in/external history filtering, while `idx_runs_session_started`, `idx_snapshots_session_created`, `idx_user_workflows_session_updated_created`, `idx_recent_values_session_kind_last_used`, and `idx_secrets_session_updated` keep session-scoped startup, history, workflow, share, autocomplete, and secret-list reads bounded on large history databases. Atlas indexes cover session/type/last-seen lists, entity value lookup, run-link cleanup, finding status/entity/tool/severity filters, finding occurrence cleanup, and cached intel snapshot reads. Project workspace indexes cover session project lists, project contents, reverse entity lookup, run file artifacts, labels, notes, and evidence packages before UI routes depend on those query shapes.
- Redis-backed active-run metadata plus browser `sessionStorage` form a second persistence layer for reload continuity:
  - `/history/active` covers in-flight runs owned by the server/session
  - browser `sessionStorage` covers non-running tabs, transcript previews, status, draft input, and active-tab selection

The storage model is intentionally split:

- live tabs and normal history restore use `max_output_lines`, `output_preview_max_mb`, and the `runs.output_preview` payload, which keeps only the most recent bounded preview lines
- full-output persistence is controlled by backend-only config keys `persist_full_run_output` and `full_output_max_mb`
- `full_output_max_mb` is multiplied by `1024 * 1024` and enforced on the uncompressed UTF-8 stream before gzip compression, so the limit tracks output volume rather than the final on-disk `.gz` size
- full-output artifacts for fresh runs are stored as gzip-compressed JSON-lines records, not plain text, so prompt/timestamp/class metadata can be reused by canonical run permalinks
- the main-page permalink button upgrades to the persisted full artifact when one exists, so `/share/<id>` and `/history/<run_id>` both surface the same complete result when available
- artifact readers stay backward-compatible with older plain-text gzip artifacts by normalizing them into structured `{text, cls, tsC, tsE}` entries at load time
- deleting a run, clearing history, or retention pruning removes both the DB metadata and any associated artifact files

Active process tracking (`run_id → pid`) was previously a third table (`active_procs`) cleared on startup. It has been replaced by Redis keys with a 4-hour TTL, which keeps the kill path correct across multiple Gunicorn workers without pushing ephemeral run state into SQLite.

---

### Session Identity

Session identity is a two-tier model managed in `app/static/js/session.js`:

1. **UUID session (anonymous)** — generated by `_generateUUID()` on first visit and persisted in `localStorage` under `session_id`. Always present; never removed. `_generateUUID()` tries `crypto.randomUUID()` first (HTTPS/localhost) and falls back to `crypto.getRandomValues()` so HTTP LAN deployments (e.g. `http://192.168.x.x`) work without a secure context.
2. **Session token (named)** — a `tok_<32 hex>` string generated server-side by `GET /session/token/generate` and persisted in `localStorage` under `session_token`. Takes precedence over the UUID when present. Stored in the `session_tokens` database table `(token TEXT PRIMARY KEY, created TEXT)`.

`SESSION_ID` is initialised at page load by preferring `session_token` over `session_id`. `updateSessionId(newId)` switches identity at runtime without a page reload — used by `session-token generate/set/clear/rotate/revoke`. Every API call sends the active identity as `X-Session-ID` via `apiFetch()`. History, stars, saved Options state, and app-managed workspace files are scoped to this identity; clearing a session token reverts to the UUID rather than losing the anonymous session. Terminal `session-token` flows keep their prompts in the transcript, while the Options-panel clear/set actions use `showConfirm()`.

**Server-side token validation:** `get_session_id()` in `helpers.py` validates `tok_`-prefixed header values against the `session_tokens` table on every request. A revoked or never-issued `tok_` token is treated as anonymous (returns `""`) so the caller loses access to session-scoped data immediately, without requiring a client-side logout. UUID-format session IDs pass through without a DB lookup.

`maskSessionToken(token)` in `session.js` produces display-safe representations: `tok_XXXX••••` for named tokens and `uuid8ch••••••••` for UUIDs.

History and workspace-file migration between identities goes through `POST /session/migrate` — see `### Session Token Security` in [DECISIONS.md](DECISIONS.md) for the constraints on that endpoint.

### Reload Continuity

There are two persistence layers for reload restore:

- `/history/active` covers in-flight runs owned by the server/session
- browser `sessionStorage` covers non-running tabs, transcript previews, status, draft input, and active-tab selection

`/history/active` exposes only the current session's in-flight run metadata so the browser can rebuild running tabs after a reload, keep kill available, render the submitted command as a normal prompt line, and then hand those tabs back to the normal `/history/<run_id>` restore path once the run completes. Non-running tabs and drafts are restored separately from browser `sessionStorage`, which keeps the reload path split cleanly between browser-owned idle state and server-owned active-run state.

That split is also what lets the browser keep a separate `sessionStorage` snapshot for non-running tabs and draft input without persisting that UI state across browser sessions.

---

## Observability And Diagnostics

This section groups log emission, health/status surfaces, and the operator diagnostics page into one observability story rather than scattering them across unrelated runtime sections.

### Logging

The application uses a dedicated `shell` logger configured by `logging_setup.py`. Logging is part of the runtime architecture rather than just a deployment concern because request hooks, run lifecycle handlers, diagnostics gates, and startup bootstrap all emit structured events that operators rely on for troubleshooting and auditing.

Structured events use the `session` field for request correlation. Anonymous session IDs are logged as-is, while `tok_` session-token values are masked before logging because they are bearer credentials.

### Output Formats

The logging layer supports two output formats selected by `log_format` in `config.yaml`:

- `text`
  - human-readable single-line logs for local development and plain `docker compose logs`
  - output shape is `timestamp [LEVEL] EVENT key=value ...`
  - extra fields are sorted alphabetically and appended after the event name
  - string values containing spaces are repr-quoted so copy/paste remains readable
- `gelf`
  - newline-delimited GELF 1.1 JSON for Graylog-style aggregation
  - `short_message` is the bare event name such as `RUN_START`
  - event context is emitted as `_`-prefixed additional fields such as `_ip`, `_run_id`, and `_cmd`
  - this makes the application logs directly indexable by a GELF-aware backend without extra parsing rules

The Docker logging driver and the application formatter are intentionally separate controls. The production Compose override can ship container stdout over Docker GELF transport, while `log_format: gelf` controls whether the application itself emits GELF-shaped records or plain text.

### Log Event Inventory

The current event inventory is:

| Level | Event | Where | Key extra fields |
| ------- | ------- | ------- | ----------------- |
| DEBUG | `REQUEST` | `before_request` | ip, method, path, qs |
| DEBUG | `RESPONSE` | `after_request` | ip, method, path, status, size |
| DEBUG | `KILL_MISS` | `kill_command` | ip, run_id |
| DEBUG | `HEALTH_OK` | `health()` | — |
| DEBUG | `ACTIVE_RUNS_VIEWED` | `get_active_history_runs` | ip, session, count |
| DEBUG | `HISTORY_DELETE_MISS` | `delete_run` | ip, run_id, session |
| DEBUG | `THEME_SELECTED` | current theme resolution | ip, session, route, theme, source |
| DEBUG | `CMD_PIPE` | `run_command` | ip, session, cmd, pipe_to |
| DEBUG | `HISTORY_COMMANDS_VIEWED` | `get_history_commands` | ip, session, count, limit |
| DEBUG | `SESSION_RUN_COUNT_VIEWED` | `session_run_count` | ip, session, session_kind, count |
| DEBUG | `STARRED_COMMANDS_VIEWED` | `session_starred_list` | ip, session, session_kind, count |
| INFO | `LOGGING_CONFIGURED` | `configure_logging` | level, format |
| INFO | `CMD_REWRITE` | `run_command` | ip, original, rewritten |
| INFO | `RUN_START` | `run_command` | ip, run_id, session, pid, cmd, cmd_type |
| INFO | `RUN_END` | `generate()` | ip, run_id, session, exit_code, elapsed, cmd, cmd_type |
| INFO | `RUN_KILL` | `kill_command` | ip, run_id, pid, pgid |
| INFO | `DB_PRUNED` | `db_init` | runs, snapshots, retention_days |
| INFO | `PAGE_LOAD` | `index` | ip, session, theme |
| INFO | `CONTENT_VIEWED` | content routes | ip, session, route, count/restricted/current/key_count |
| INFO | `SESSION_TOKEN_GENERATED` | `session_token_generate` | ip, session, session_kind |
| INFO | `SESSION_TOKEN_REVOKED` | `session_token_revoke` | ip, session, session_kind, revoked_current |
| INFO | `SESSION_MIGRATED` | `session_migrate` | ip, session, from_session_kind, to_session_kind, migrated_runs, migrated_snapshots, migrated_stars, migrated_preferences |
| INFO | `SESSION_PREFERENCES_SAVED` | `session_preferences_save` | ip, session, session_kind, key_count |
| INFO | `STARRED_COMMAND_ADDED` | `session_starred_add` | ip, session, session_kind, command_root, changed |
| INFO | `STARRED_COMMAND_REMOVED` | `session_starred_remove` | ip, session, session_kind, command_root, count |
| INFO | `STARRED_COMMANDS_CLEARED` | `session_starred_remove` | ip, session, session_kind, count |
| INFO | `SHARE_CREATED` | `save_share` | ip, session, share_id, label, redacted |
| INFO | `SHARE_VIEWED` | `get_share` | ip, session, share_id, label |
| INFO | `SHARE_DELETED` | `delete_share` | ip, session, share_id, deleted |
| INFO | `RUN_VIEWED` | `get_run` | ip, run_id, cmd |
| INFO | `HISTORY_VIEWED` | `get_history` | ip, session, count, q, output_search, command_root, exit_code_filter, date_range |
| WARN | `FTS_SEARCH_FALLBACK` | `get_history` | session, q, error |
| INFO | `HISTORY_DELETED` | `delete_run` | ip, run_id, session |
| INFO | `HISTORY_CLEARED` | `clear_history` | ip, session, count |
| INFO | `DIAG_VIEWED` | `diag()` | ip |
| WARN | `RUN_NOT_FOUND` | `get_run` | ip, run_id |
| WARN | `SHARE_NOT_FOUND` | `get_share` | ip, share_id |
| WARN | `CMD_DENIED` | `run_command` | ip, session, cmd, reason |
| WARN | `CMD_MISSING` | `run_command` | ip, session, cmd |
| WARN | `CLIENT_ERROR` | `client_log` | ip, session, context, client_message |
| WARN | `DIAG_DENIED` | `diag()` | ip, allowed_cidrs |
| WARN | `SESSION_TOKEN_REVOKE_DENIED` | `session_token_revoke` | ip, session, reason |
| WARN | `SESSION_MIGRATE_DENIED` | `session_migrate` | ip, session, reason, from_session_kind, to_session_kind |
| WARN | `SESSION_PREFERENCES_INVALID` | `session_preferences_get` | ip, session, session_kind |
| WARN | `UNTRUSTED_PROXY` | `get_client_ip` | ip, proxy_ip, forwarded_for, path |
| WARN | `RATE_LIMIT` | `errorhandler(429)` | ip, path, limit |
| WARN | `CMD_TIMEOUT` | `generate()` | ip, run_id, session, timeout, cmd |
| WARN | `KILL_FAILED` | `kill_command` | ip, run_id, pid, error |
| WARN | `HEALTH_DEGRADED` | `health()` | db, redis |
| ERROR | `RUN_SPAWN_ERROR` | `run_command` | ip, session, cmd (+ traceback) |
| ERROR | `RUN_STREAM_ERROR` | `generate()` | ip, run_id, session, cmd (+ traceback) |
| ERROR | `RUN_SAVED_ERROR` | `generate()` | run_id, session, cmd (+ traceback) |
| ERROR | `HEALTH_DB_FAIL` | `health()` | (+ traceback) |
| ERROR | `HEALTH_REDIS_FAIL` | `health()` | (+ traceback) |

### Logging Shape Notes

- request/response logging is owned by Flask hooks rather than Werkzeug's default request-line logging
- run lifecycle logs intentionally carry `ip`, `session`, and `run_id` so start/end/kill/failure events can be correlated without reconstructing request flow from surrounding lines
- diagnostics, history, permalink, and share routes each emit their own events so operator-visible surfaces remain observable outside the command-execution path
- proxy-aware identity resolution is shared across logging, rate limiting, and diagnostics gating, so the logged `ip` field tracks the same resolved client identity used elsewhere in the runtime

---

### Health, Status, And Diagnostics Surfaces

- `/health` remains the load-balancer contract and reports whether DB and Redis are healthy, with degraded states surfacing through status code.
- `/status` is intentionally a softer browser-HUD contract and always responds 200 so status-pill polling never causes UI flapping or reconnect churn.
- `/diag` is the operator-facing structured view that surfaces runtime config, service health, asset presence, database storage breakdowns, tool availability, and activity summaries without opening a shell session.
- `/metrics` is the Prometheus scrape contract for trendable operational signals, including HTTP traffic, runs, PTYs, rate limits, broker mode/activity, DB/Redis/workspace gauges, selected database hot-path latency, intel provider outcomes/cache size, evidence package builds, findings, snapshots, and error counters.

These surfaces share the same runtime health model, but they target different consumers: infrastructure checks, browser chrome, operator diagnostics, and time-series monitoring.

### Operator Diagnostics

The diagnostics page and Prometheus metrics endpoint live behind the same trusted-proxy-aware client IP resolution path used by logging and rate limiting. When enabled through `diagnostics_allowed_cidrs`, `/diag` exposes a live operator view of the running instance and reuses the same themed header foundation as permalink/export surfaces. `/metrics` returns Prometheus text for allowlisted callers when `metrics_enabled` is true.

Operationally, `/diag` sits on top of the same underlying sources described earlier in the document:

- Redis and database health come from the same runtime boundary described in **System Structure**
- run counts, top commands, and stored artifacts come from the persistence layer described in **State And Persistence**
- table/index or relation storage, logical payload estimates, search-index rollups, and largest saved-run hints come from the same database connection as the Database card; SQLite allocated byte counts appear when SQLite was built with `SQLITE_ENABLE_DBSTAT_VTAB`, while Postgres relation sizes come from catalog functions
- config values reflect the browser/backend config split described in **Configuration Surfaces**
- access control and denied-access logging reuse the same client-IP trust model described in **Security Model** and **Logging**
- Prometheus counters, histograms, label normalizers, cardinality policies, and multiprocess registry setup live in `app/services/metrics/__init__.py`; scrape-time collectors for database, Redis, broker mode, workspace, intel cache size, Atlas, findings, snapshots, and provider-secret health live in `app/services/metrics/collectors.py`
- the container entrypoint prepares `PROMETHEUS_MULTIPROC_DIR` under `/tmp/darklab_shell-prom`, clears stale worker shards on startup, keeps the directory ephemeral with the existing tmpfs runtime, and starts Gunicorn with `app/gunicorn_conf.py` so dead worker metric shards are removed when workers exit

---

## Security Model

The runtime security model is layered across process ownership, command validation, and container-level controls.

### User Separation

The container uses two unprivileged system users:

- `appuser`
  - owns the Flask/Gunicorn web process
  - owns the configured data directory and can read or write SQLite data files, artifact metadata, and body-store files
- `scanner`
  - owns all user-submitted command processes
  - does not get write access to `./data`
  - runs with `HOME=/tmp` so tools that expect config/cache directories stay inside tmpfs rather than a persistent home directory

The container starts as root only long enough for `entrypoint.sh` to fix `/data` ownership after volume mount, normalize the optional workspace root, set `/tmp` to `1777`, pre-create `/tmp/.config` and `/tmp/.cache` for `scanner`, and then drop to `appuser` via `gosu`.

Workspace-specific permission, bind-mount, and cleanup behavior are covered in **Session Workspace and Files**, since they describe the workspace surface rather than the broader two-user model.

### Trust Boundary Notes

- command validation and rewrite behavior are part of the trust boundary, but the execution mechanics themselves now live in **Run Lifecycle** above because they are also central runtime behavior
- session identity is isolation, not authentication; the actual session model lives in **State And Persistence**
- cross-worker kill relies on Redis-backed PID lookup and a user-bound signal path, as described in **Run Lifecycle**

### nmap Scan Mode Model

`nmap` can use raw-socket-related Linux capabilities for SYN scans, OS fingerprinting, and similar features. In practice, those capabilities are not reliable for the app's unprivileged `scanner` execution path across Docker hosts and security profiles, even when the binary has file capabilities:

```bash
setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap
```

For predictable behavior, the app treats TCP connect scans as the supported `nmap` mode. `rewrite_command()` injects `-sT` when an `nmap` command does not already specify a scan mode. Command validation blocks `-sS` and explicit `--privileged` so users do not get confusing raw-socket `Operation not permitted` failures after launch.

---

## Configuration Surfaces

The Flask index route embeds the same normalized browser config payload that `/config` returns, and `config.js` reads that server-rendered JSON into `APP_CONFIG` before the rest of the classic-script frontend loads. The `/config` endpoint remains available for runtime refresh and diagnostics, but both paths are built from the same Python payload helper. That payload is the browser bootstrap boundary for runtime values the frontend actually needs: naming, prompt text, limits, welcome timing, and selected browser-facing feature flags. It is intentionally narrower than `config.yaml`; backend-only persistence and storage controls do not cross that boundary.

Not every `config.yaml` key is exposed to the browser. Server-side persistence and storage controls such as `persist_full_run_output`, `full_output_max_mb`, and the `workspace_*` settings stay backend-only because the frontend does not need to know them to render the normal tab or history flows. The MB values are converted to bytes internally before artifact or workspace quota logic runs.

This is also where backend configuration crosses into presentation: the browser bootstrap payload, the resolved theme palette, and the frontend-owned preference layer all meet here, but they do not collapse into one generic config blob. The full theme contract lives in its own top-level section below.

---

## Theme System

Theme values are resolved server-side from named YAML variants in `app/conf/themes/` and injected into every presentation surface — live shell, permalink pages, runtime selector, and exported HTML — through a single shared palette. No surface maintains its own independent palette logic. See [THEME.md](THEME.md) for the full architecture, token reference, and authoring workflow.

---

## Test Suite

The test stack is intentionally split into three layers:

- `pytest` for backend contracts, route behavior, persistence, loaders, and logging
- `Vitest` for client-side helpers and DOM-bound browser logic in jsdom
- `Playwright` for the integrated browser UI against a live Flask server

Current totals:

- behavior tests: 2,871
- docs/inventory meta-tests: 32
- `pytest`: 1490 (1458 behavior + 32 meta)
- `vitest`: 1161
- `playwright`: 252
- total: 2,903

### Testing Architecture

This split exists to keep each risk at the cheapest useful layer:

- backend behavior stays fast and deterministic in `pytest`
- browser-module logic is isolated in `Vitest` without changing the classic-script frontend architecture
- browser-only integration risks such as real focus, scroll, SSE timing, and mobile layout behavior stay in `Playwright`
  - browser-visible autocomplete behavior spans two contexts:
    - command-root-aware flag/value suggestions
    - the allowlisted built-in pipe-helper context after `command |`, including chained helper stages

The browser test harness mirrors production constraints rather than abstracting them away:

- the frontend remains a no-build classic-script app, so `Vitest` uses extraction helpers instead of converting the runtime to ES modules
- `Playwright` uses two configs: a simple single-project default config for VS Code/debugging and a parallel CLI config that balances the suite across 5 isolated projects
- the standalone demo/capture Playwright configs share one visual-contract file so desktop/mobile viewport, density, touch, token, and seeded-history assumptions stay aligned across recording and screenshot flows
- each parallel browser project gets its own Flask server port plus isolated internal `APP_DATA_DIR` state so SQLite history, run-output artifacts, and limiter/process state do not collide across workers
- backend tests keep the app’s real relative-path assumptions by changing into `app/` before imports
- the browser suite also carries focused regressions for the split welcome specs, pipe-stage autocomplete, and the responsive FAQ limits renderer because those are easiest to verify in the real UI

Keep the detailed suite appendix, focused run commands, and maintenance notes in [tests/README.md](tests/README.md). Keep the rationale behind this layered split in [DECISIONS.md](DECISIONS.md).

---

## Related Docs

- [Default.md](.gitlab/merge_request_templates/Default.md) - default GitLab merge request template
- [CHANGELOG.md](CHANGELOG.md) - release-by-release changes
- [CONFIGURATION.md](CONFIGURATION.md) - operator config reference for `app/conf/`, `.env`, Compose, storage, and production tuning
- [CONTRIBUTING.md](CONTRIBUTING.md) - local setup, test workflow, linting, branch workflow, and merge request guidance
- [CONTRIBUTORS.md](CONTRIBUTORS.md) - contributor and acknowledgement notes
- [DECISIONS.md](DECISIONS.md) - architectural rationale, tradeoffs, and implementation-history notes
- [DOCS_STANDARDS.md](DOCS_STANDARDS.md) - documentation structure, templates, and review rules
- [FEATURES.md](FEATURES.md) - full per-feature reference
- [README.md](README.md) - project overview, quick start, documentation map, and installed tools
- [THEME.md](THEME.md) - theme registry, token reference, and custom theme authoring
- [TODO.md](TODO.md) - open follow-ups, research notes, known issues, and future ideas
- [Atlas and Entity Model → Export Schema](#export-schema) - Session Entity Atlas CSV/JSONL export schema and filters
- [docs/external-command-integrations.md](docs/external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/postgres-migration.md](docs/postgres-migration.md) - offline SQLite-to-Postgres cutover helper and validation workflow
- [docs/storage-scaling.md](docs/storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [tests/README.md](tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
