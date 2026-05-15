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

### Session Entity Atlas (entity-first triage surface)
- **Scope**
  - Top-level Atlas surface with first-class chrome treatment: desktop left-rail entry between History and Workflows, mobile menu item, dedicated keyboard shortcut. Not a stacked modal.
  - Tabs: Findings, Hosts/IPs, Domains, Hashes, CVEs, URLs. Each tab is a filterable, sortable list of distinct entities deduped across every saved run for the active session token.
  - Entity Detail side sheet: identity strip, intel snapshot card, source-run list with jump-to-line, findings on entity, labels and notes (reusing `ui_entity_metadata`), promote-to-project action.
  - Intel snapshot cards are driven by the external-intel provider registry, including provider labels, supported entity types, missing-secret state, cache state, and explicit refresh actions.
  - Transcript ↔ Atlas wiring: tagged tokens click into entity detail, long-press / right-click opens entity actions, and "see in run" navigation opens the source run.
  - Findings tab absorbs the Findings triage inbox plan if both are scheduled — the inbox modal is retired in favor of the Atlas tab.
  - Project workspaces become a curation layer over the entity store; project_links are tags on entity rows, not parallel copies.
  - Schema cleanup is destructive. The run-centric `findings`, project-scoped `project_targets`, and `finding_targets` tables are dropped and replaced by an entity-first schema. Pre-release single-user app — no backwards-compatibility shim, no dual-write phase, no data backfill from legacy rows. The Findings triage inbox's `findings_inbox` table is also collapsed into the unified entity-owned `findings` table here.
  - Hard dependencies: entity-aware classifier hooks are landed; encrypted secrets vault is landed for intel refresh actions.
- **Current implementation status**
  - Landed: Phase 1 backend contracts and storage, including the destructive project/finding/target rewrite onto `entities`, `project_links(entity_type='atlas_entity')`, unified `findings`, and `findings_occurrences`; Phase 2 run-finalize entity/finding materialization and retention pruning rules; `/atlas` summary/list/detail/refresh/project-link routes; shared label/note/project-link support for `atlas_entity`; Phase 3 browser Atlas surface with rail/mobile/shortcut/history/run-details/project entry points; Phase 4 transcript entity-token navigation; and Phase 5 Findings tab absorption with status filters, single-finding updates, and visible-page bulk review updates.
  - Still pending: richer Atlas entity-list filters, project curation/export follow-through, and the later UI/export/test work described below.
- **Phase 0 - Existing-code integration check (complete)**
  - Confirm classifier entity metadata (`entities: [{type, value, canonical_value, confidence, source_line}]`) is landed.
  - Audit `app/services/projects/workspace.py` and `app/services/projects/metadata.py` for label/note/finding/target storage that must be reused, not duplicated.
  - Audit `app/services/runs/comparison.py` for cross-run finding helpers the Atlas should reuse.
  - Audit `app/static/js/ui/ui_entity_metadata.js` to confirm label/note helpers work on Atlas entity types without changes.
  - Inventory every SQL call site against `findings`, `project_targets`, and `finding_targets` across `app/services/projects/workspace.py`, `app/services/projects/metadata.py`, and `app/blueprints/projects.py`. Expect ~30+ touch sites in `workspace.py` alone. The rewrite of these call sites lands with the schema migration in Phase 1, not as a follow-up.
  - Confirm the existing generic `project_links` table (`project_id, entity_type, entity_id`) can absorb entity-to-project tagging by introducing `entity_type='atlas_entity'`. This drops the previously proposed standalone `entity_project_links` table from the plan.
  - Lock the destructive-migration decision: pre-release, single-user app, so v1 drops `project_targets`, `finding_targets`, and the existing run-centric `findings` schema outright. No backfill, no compat shim, no dual-write phase. Document this in the migration commit message so any future operator with persisted data sees the warning.
- **Phase 1 - Backend contracts and storage (complete)**
  - **Destructive schema migration in `app/core/database.py`:**
    - **Drop tables:** `project_targets`, `finding_targets`, and the existing run-centric `findings` table.
    - **Drop indexes:** `idx_findings_session_run_created`, `idx_findings_target_created`, `idx_finding_targets_finding`, `idx_finding_targets_target_created`, `idx_finding_targets_run`, `idx_project_targets_project_type_value`.
    - **Keep unchanged:** `runs`, `run_output_artifacts`, `run_file_artifacts`, `snapshots`, `session_tokens`, `session_preferences`, `starred_commands`, `session_variables`, `user_workflows`, `recent_domains`, `projects`, `project_links`, `entity_labels`, `entity_notes`, `evidence_packages`.
    - **Reuse `entity_labels` and `entity_notes`** for Atlas entities by adopting `entity_type='atlas_entity'`. The tables are already keyed by `(session_id, entity_type, entity_id)` so no schema change is needed.
    - **Reuse `project_links`** for entity-to-project tagging with `entity_type='atlas_entity'`. Same generic `(project_id, entity_type, entity_id)` shape that already serves `run` and `finding` links — no parallel `entity_project_links` table.
  - **New `entities` table:**
    - `(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, occurrence_count, created)`.
    - `type` values: `ip`, `domain`, `url`, `hash`, `cve`. The legacy `host` target type is collapsed into `domain` unless the Phase 0 audit surfaces a meaningful distinction.
    - `canonical_value`: pre-normalized form (lowercase IPv4/IPv6, IDN-normalized lowercase domain, lowercase algorithm-tagged hash, uppercase `CVE-YYYY-NNNNN`, percent-encoded URL).
    - `signature_hash`: stable `sha256(type | canonical_value)` for dedup.
    - UNIQUE `(session_id, type, signature_hash)`.
    - Indexes: `idx_entities_session_type_last_seen ON entities (session_id, type, last_seen_at DESC)` for Atlas tab listing and indexed summary counts; `idx_entities_session_value ON entities (session_id, canonical_value)` for transcript-token hover lookups.
  - **New `entity_run_links` table:**
    - `(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count, PRIMARY KEY (entity_id, run_id))`.
    - Replaces the role of `seen_count` / `last_seen` / `source_run_id` formerly on `project_targets`.
    - Index: `idx_entity_run_links_run ON entity_run_links (run_id)` so run pruning can sweep entity links cleanly.
  - **New `entity_intel_snapshots` table:**
    - Current foundation shape: `(id, session_id, entity_id, provider, status, summary, data_json, fetched_at, expires_at)`.
    - One row per (entity, provider). Refresh replaces in place.
    - Index: `idx_entity_intel_snapshots_entity_fetched ON entity_intel_snapshots (entity_id, fetched_at DESC)` for detail-card reads; TTL-expiry sweeps can add a broader fetched/expiry index if profiling shows it is needed.
  - **New entity-owned `findings` table (rewritten, not migrated):**
    - `(id, session_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, status_updated_at, fingerprint, created)`.
    - `status` values reuse the existing finding review vocabulary: `new`, `reviewed`, `important`, `false_positive`, and `needs_followup`. **Triage state lives directly on `findings`** — the Findings triage inbox plan's separate `findings_inbox` table is collapsed into this row.
    - `entity_id` is nullable. Entity-backed findings point to an Atlas entity. Findings without a primary IP/domain/hash/CVE use `entity_id = NULL` and a stable `subject_key` such as `unscoped:<tool_root>:<normalized_signal_key>` so command-scoped warnings remain triageable instead of being dropped.
    - UNIQUE `(session_id, signature_hash)` for cross-run dedup. Signature: `sha256(tool_root | kind | severity | normalized_signal_key | entity.signature_hash_or_subject_key)`.
    - Indexes: `(session_id, status)`, `(session_id, entity_id, last_seen_at DESC)`, `(session_id, tool_root, last_seen_at DESC)`, `(session_id, severity, last_seen_at DESC)`.
  - **New `findings_occurrences` table (per-run sightings):**
    - `(finding_id, run_id, line_number, snippet, seen_at, PRIMARY KEY (finding_id, run_id, line_number))`.
    - Pruned with its source run; the parent `findings` row survives so the historical pattern is preserved.
    - Index: `idx_findings_occurrences_run ON findings_occurrences (run_id)` for prune sweeps.
  - **Service-layer rewrite (lands with the schema migration, not after):**
    - `app/services/projects/workspace.py` — rewrite every helper that reads or writes `project_targets`, `findings`, or `finding_targets`. Non-exhaustive list: `_row_to_target`, `_row_to_finding`, `_row_to_project_finding`, `_finding_target_ids_*`, `_finding_severity_from_text`, `_finding_fingerprint`, `_target_candidate_*`, `list_project_findings`, target listing/dedup/dismiss flows, and evidence-package selection move to `entities` / `findings` / `entity_run_links` reads with `project_links` joins for project membership.
    - `app/services/projects/metadata.py` — `entity_metadata_target_exists` and finding-existence checks switch to the new tables.
    - `app/blueprints/projects.py` — `/projects/<id>/targets*` becomes a typed view over `entities` filtered by `project_links`; `/projects/<id>/findings` reads from the rewritten `findings` table joined to `project_links`; `/findings/<id>/review` becomes a status-update route on the unified `findings` table; `/entities/run/<id>/findings` reads via `entity_run_links` join.
    - `app/services/commands/builtins_project.py` and any `project` built-in target lookups shift from `project_targets`-backed to entity-store-backed via `project_links`.
    - Evidence package builders that emit "targets" sections derive them from project-linked Atlas entities of type `host` / `domain` / `ip` / `url`.
  - **New `app/services/atlas/` service:**
    - `materializer.py` consumes entity events from `output_signals` at run-finalize. Idempotent on re-finalization. Computes stable canonical forms per type.
    - `lookup.py` exposes list/filter/detail queries used by both the Atlas and the rewritten Projects routes.
    - `intel_bridge.py` writes normalized intel payloads into `entity_intel_snapshots` when `intel` runs complete or when sidecar enrichment runs.
    - Explicit `intel` commands, sidecar enrichment, and future pipe-helper enrichment all write through the same provider lookup path so cache, quota, missing-secret, and audit behavior cannot drift.
    - Project enrichment stores selected snapshots under the entity/project model rather than creating parallel project-only intel records.
  - **Routes in new `app/blueprints/atlas.py`:**
    - `GET /atlas` tab summary (landed: entity counts per type, computed from indexed `entities` rows unless profiling proves a rollup table is needed).
    - `GET /atlas/entities` paginated list with filters (landed: `type`, `q`, `project_id`, `limit`, `offset`; still pending: `status`, `seen_in_last`, `has_intel`).
    - `GET /atlas/entities/<id>` detail with linked runs, intel snapshots, findings, labels, notes, project links.
    - `GET /atlas/findings` paginated Findings-tab list with text, project, review-state, limit, and offset filters.
    - `POST /atlas/findings/review` visible-page bulk review-state update route for selected findings.
    - `POST /atlas/entities/<id>/refresh_intel` triggers a fresh provider fetch via the intel service (rate-limited).
    - `POST /atlas/entities/<id>/project_links` promotes by writing into `project_links` with `entity_type='atlas_entity'`.
    - `DELETE /atlas/entities/<id>/project_links/<project_id>` unpromotes.
    - Findings-status routes live next to the rewritten Projects findings routes — there is one `findings` table, one set of status routes, used by both Atlas and Projects surfaces.
  - **Audit log:** `ATLAS_ENTITY_MATERIALIZED`, `ATLAS_INTEL_REFRESH`, `ATLAS_PROJECT_LINK_ADDED` (extends the existing `PROJECT_LINK_ADDED` family with `entity_type='atlas_entity'`), `ATLAS_PROJECT_LINK_REMOVED`.
- **Phase 2 - Materialization (complete)**
  - Hook into the run-finalize path in `app/blueprints/run.py` after classification. Lazy extraction — only process classified entity events, never raw output lines, so cost scales with distinct entities rather than output volume.
  - No backfill is shipped. Pre-release single-user app drops all historic findings/targets in Phase 1 and starts the entity store fresh from the first new run finalized after the migration. Saved runs from before the migration have no Atlas entities; entity-tab counts simply omit them.
  - Retention pruning rule: `entity_run_links` and `findings_occurrences` rows follow their source run; `entities` and `findings` rows survive after the last link is pruned so the historical pattern is preserved.
- **Phase 3 - Browser surface (complete)**
  - New `app/static/js/features/atlas/`:
    - `atlas_overlay.js` — full-surface controller wired into the desktop rail and mobile menu, not stacked over History.
    - `atlas_tabs.js` — tab rendering and filter state.
    - `atlas_entity_detail.js` — side sheet with identity, intel card, source runs, findings, labels/notes, project links.
  - New `app/static/css/features/atlas.css`.
  - Entry points: left-rail entry between History and Workflows; mobile menu item; keyboard shortcut documented in the `?` overlay; History row action menu; Run Details Atlas action; Projects modal "Open in Atlas" filtered to the selected project.
  - Reuses `ui_dismissible`, `ui_focus_trap`, `ui_outside_click`, `ui_pressable`, `ui_entity_metadata`, and the existing bulk-action toast contract.
  - Intel snapshot card renders from provider registry metadata so future providers appear with consistent labels, setup state, cache state, and refresh affordances.
- **Phase 4 - Transcript wiring (complete)**
  - Output renderer in `app/static/js/output.js` decorates classifier-extracted entities as tagged spans.
  - Click opens entity detail; long-press / right-click opens a shared action menu for opening Atlas, editing metadata in Atlas, promoting through Atlas, copying the value, refreshing intel, or focusing the current transcript line.
  - "See in run" in entity detail opens the source run in the existing Run Details overlay.
- **Phase 5 - Findings tab absorption (complete)**
  - The Findings tab now lists deduped findings from the unified `findings` table with text, project, and review-state filters.
  - Selecting a finding opens the shared detail renderer with source-run navigation, entity navigation, evidence text, and the same review-state control used by Run Details and Projects.
  - Visible-page selection supports bulk review-state updates through `/atlas/findings/review`; mixed missing rows return count/result feedback instead of failing the whole action.
  - The standalone Findings triage inbox does not ship as a separate modal because its scope is absorbed by the Atlas Findings tab.
- **Phase 6 - Projects as curation, not gating**
  - Adding an entity to a project writes a row in the existing generic `project_links` table with `entity_type='atlas_entity'`. No new project-link table is introduced.
  - The `project_targets` table is dropped in Phase 1 and not preserved. The "Targets" view in the Projects modal becomes a server-side filter over project-linked Atlas entities of type `host` / `domain` / `ip` / `url`, computed in the rewritten `/projects/<id>/targets` route.
  - Projects modal Findings tab reads from the unified `findings` table joined to `project_links` so it cannot drift from the Atlas Findings tab — there is one findings store, not two.
  - Engagement report builder (separate idea) reads "targets", "findings", and "intel observations" sections from the entity store via the same Atlas service the Projects routes use.
- **Phase 7 - Sharing, redaction, and exports**
  - Entity rows never appear in snapshot permalinks; only the source-run transcript does. Existing share-redaction handles transcript content.
  - Atlas export options ship in v1:
    - Per-entity CSV/JSONL with selected fields.
    - Per-project filtered entity export for engagement handoff.
  - Honors share-redaction baseline so redacted exports omit raw intel response bodies.
- **Phase 8 - Feedback and tests**
  - Empty-state UX: runs producing zero entities are normal and do not surface as warnings. Saved runs from before the migration also produce no Atlas rows and must not appear as broken.
  - Backend coverage: destructive migration drops the legacy `project_targets`, `finding_targets`, and run-centric `findings` tables and re-initializes the new schema from scratch; deduplication signature stability across every entity type; unscoped finding materialization without an entity row; materialization idempotency on re-finalization; intel snapshot freshness and TTL expiry behavior; entity refresh respects missing-secret/provider availability states; cache state is visible; share/export omission still applies to refreshed intel; `project_links` `entity_type='atlas_entity'` round-trip (promote/unpromote); label/note helper reuse against entity rows; cross-session rejection; retention pruning preserves `entities` and `findings` rows when their last run-link or occurrence row is pruned; one consolidated `findings` table services both Projects routes and Atlas routes without divergence.
  - Service-layer regression coverage: rewritten Projects routes (`/projects/<id>/targets*`, `/projects/<id>/findings`, `/findings/<id>/review`, `/entities/run/<id>/findings`) return parity-equivalent shapes to the pre-migration responses where possible, so the Projects modal UI does not need to be reskinned just because the backing store changed.
  - Frontend coverage: tab filter combinations, entity detail render with and without intel snapshots, transcript token action menu, see-in-run navigation, project promotion and unpromotion, rail entry plus mobile menu integration, keyboard shortcut, empty-state rendering, Projects modal Targets and Findings tabs continue to function against the rewritten routes.
  - Playwright: one desktop and one mobile flow covering scan → atlas → entity detail → intel refresh → promote-to-project → see-in-run → unpromote, plus one regression flow exercising the Projects modal Targets/Findings tabs end-to-end against the rewritten store.
- **Open Decisions** (recommended answers below; review before implementation starts)
  - **Entity ID format.** Question: what shape does `entities.id` take? **Recommend:** `ent_<12-hex>` (mirrors the existing `run-<hex>` / project-id conventions); generated via the same `secrets.token_hex(6)` helper. Cheap to grep, short enough for transcripts.
  - **`ip` type covers IPv4 and IPv6.** Question: do v4 and v6 share `type='ip'` or split into `ipv4` / `ipv6`? **Recommend:** **single `ip` type**. `canonical_value` carries the normalized form (`192.0.2.1` or `2001:db8::1`). Saves a tab and matches how the intel providers treat them. The intel response can carry a `family` field if a card ever needs to differentiate.
  - **`host` vs `domain` collapse.** Question: does the legacy `host` target type stay as a distinct Atlas entity type? **Recommend:** **no** — collapse `host` into `domain` at materialization time. Phase 0 audit should confirm `host` is just an old name for `domain` in the existing schema. If a meaningful distinction surfaces (e.g., "host" meant FQDN-with-port-pair while "domain" was zone-only), keep both and document the rule.
  - **Hash algorithm tag format.** Question: how is the algorithm tag carried in `canonical_value`? **Recommend:** prefixed `sha256:<hex>`, `sha1:<hex>`, `md5:<hex>`. Keeps `canonical_value` a single column; the algorithm survives round-trips and is greppable.
  - **URL canonical form.** Question: what canonicalization rules apply to URL entities? **Recommend:** WHATWG URL parser normalization — lowercase scheme + host, default port stripped, fragment dropped, trailing `/` stripped on path-only URLs, query params preserved in given order. Reject URLs > 2048 bytes at materialization (warn in audit log; do not block the run).
  - **`canonical_value` length cap.** Question: max bytes for any entity's canonical value? **Recommend:** 2048 bytes UTF-8. URLs hit this first; domains/hashes/CVEs are far below. Reject longer entities at materialization with a one-line audit log entry; do not block the surrounding run.
  - **`entity_run_links.occurrence_count` semantics.** Question: counts what — total classifier emit events, or distinct line numbers? **Recommend:** total emit events. `entities.occurrence_count` is the sum across runs. Cheap to maintain; matches the inbox plan's convention.
  - **Tab summary computation cost.** Question: how does `GET /atlas` compute entity counts per type? **Recommend:** start with indexed `COUNT(*) GROUP BY type` over `(session_id, type)` rather than adding a rollup table. This keeps the schema simpler and avoids consistency bugs during prune/recalc. Add an `entity_type_counts` rollup only if profiling shows the indexed count is too slow.
  - **Pagination size and ordering.** Question: default page size and sort? **Recommend:** 50 per page, sorted by `last_seen_at DESC`. Filter chips override. The Findings tab uses the explicit status-priority ordering defined below, then `last_seen_at DESC`.
  - **Atlas keyboard shortcut chord.** Question: which keys open the Atlas? **Recommend:** `Alt+A` (desktop) and document in the `?` overlay. `Alt+H` is History today; `Alt+W` could be Workflows; `Alt+A` is free and mnemonic.
  - **Transcript entity decoration mechanism.** Question: how does the frontend know which output tokens are tagged entities? **Recommend:** backend emits per-line entity offsets in the SSE event metadata (e.g., `{entities: [{type, value, start, end}]}`). Frontend wraps spans cheaply. Re-scanning text client-side would duplicate classifier logic.
  - **Findings without a primary entity.** Question: what happens when a classifier emits a finding that has no extractable IP/domain/hash/CVE? **Recommend:** keep it in the Atlas Findings tab as an unscoped finding with `entity_id = NULL` and a stable `subject_key`. Do not create a synthetic Atlas entity in v1, so entity counts stay meaningful while command-scoped warnings remain visible and triageable.
  - **Project-promotion `source` value.** Question: what value lands in `project_links.source` when promoting from Atlas? **Recommend:** `atlas_promote` (joins the existing `manual` / automated-source family). Document in `app/services/projects/contracts.py`.
  - **Promote-to-project idempotency.** Question: what does promoting an already-linked entity do? **Recommend:** idempotent no-op — return `200 {already_linked: true}` rather than 4xx. Matches the bulk-actions plan's link semantics.
  - **Per-entity export schema.** Question: which fields appear in the CSV/JSONL export? **Recommend:** `id, type, canonical_value, first_seen_at, last_seen_at, occurrence_count, labels, notes, project_names, intel_providers_with_data`. Define a stable v1 schema doc in `docs/atlas-export.md` so consumers can rely on it.
  - **`output.js` decoration for legacy / pre-migration runs.** Question: do saved runs from before the migration get retroactive entity tagging on reopen? **Recommend:** **no** — the SSE pipeline only emits entity offsets for new runs after the classifier change ships. Reopened legacy runs render as plain text. Future work can add a backfill that re-classifies old transcripts.
  - **Findings emitter for the unified `findings` table.** Question: where does the materializer that writes `findings` rows live? **Recommend:** `app/services/atlas/materializer.py` writes both `entities` and `findings` in the same transaction at run-finalize time. The proposed `app/services/findings/inbox.py` from the Findings triage inbox plan is **not** created when the Atlas ships first.
  - **Run-prune sweep order.** Question: when a run is pruned, what's the cascade order? **Recommend:** `findings_occurrences` → `entity_run_links` → recalc `entities.occurrence_count` / `entities.last_seen_at`. Document in the pruning helper. `entities` and `findings` rows survive even after their last link is pruned.
  - **Atlas Findings tab sort default.** Question: default sort when entering the Findings tab? **Recommend:** explicit status priority (`new`, `needs_followup`, `important`, `reviewed`, `false_positive`) then `last_seen_at DESC` within each triage bucket. Do not rely on lexical `status ASC`, which would put the statuses in the wrong order.

- **Future**
  - Entity graph view (visual link map across hosts, domains, hashes, CVEs).
  - Saved Atlas views (named filter combinations).
  - Atlas FTS search across entity values, labels, and notes.
  - Auto-promote rules — entities matching saved patterns auto-promote into a project.
  - Time-travel view: "what did the Atlas look like a week ago?" using retained snapshots.
  - Side-by-side entity comparison (their runs, findings, intel snapshots).
  - Cross-session Atlas view for operators managing multiple sessions or shared infrastructure.
  - Atlas import from external triage tools.

### Table-size diagnostics in `/diag`
- **Scope**
  - Add a full storage breakdown panel to the `/diag` page so an operator can answer "which table or column is driving DB growth?" in one glance, without leaving the diagnostics surface.
  - Capture three orthogonal views per table: **allocated bytes** (page-level cost, from `dbstat`), **payload bytes** (logical row cost, from `SUM(LENGTH(col))` across the widest columns), and **row count** (volume).
  - Include every user table created by `_create_schema` and `_create_project_workspace_schema`, every FTS5 virtual table, every FTS shadow table grouped back under its parent virtual table, and every index — not just the historically-noisy ones. Sparse coverage hides regressions in the next-fastest-growing table.
  - Surface content-size estimates for the fields most likely to grow quickly so operators can correlate row growth with bytes: `runs.output`, `runs.output_preview`, `runs.output_search_text`, `snapshots.content`, `entity_intel_snapshots.data_json`, `findings.raw_line`, `evidence_packages.manifest`, `project_links.source_detail`, and `run_output_artifacts.byte_size` (sum, since it's already bytes).
  - Group tables into operator-meaningful buckets so the panel scans quickly: **Runs & transcripts** (`runs`, `run_output_artifacts`, `runs_fts*`), **Snapshots & permalinks** (`snapshots`), **Atlas & findings** (`entities`, `entity_run_links`, `entity_intel_snapshots`, `findings`, `findings_occurrences`, `entity_labels`, `entity_notes`), **Projects & workspace** (`projects`, `project_links`, `run_file_artifacts`, `evidence_packages`), **Session state** (`session_tokens`, `session_preferences`, `starred_commands`, `session_variables`, `user_workflows`, `recent_domains`), and **Security** (`secrets`).
  - When `dbstat` is unavailable (compile-option missing), still render row counts and payload-byte estimates and surface a clear "table page-size breakdown unavailable — rebuild SQLite with `SQLITE_ENABLE_DBSTAT_VTAB`" banner inside the new panel only, so the rest of `/diag` is unaffected.
- **Backend implementation**
  - Add a new helper `_diag_table_storage_breakdown()` in `app/blueprints/assets.py` next to the existing `_diag_db_stats()`. It must reuse the safe-identifier wrapper `_diag_sqlite_identifier` for every name pulled from `sqlite_master` and never bind table names as parameters.
  - Detect `dbstat` availability once per request via `SELECT sqlite_compileoption_used('ENABLE_DBSTAT_VTAB')`; cache the result on `result["db"]` as `dbstat_available` so the template can branch without re-probing.
  - Per-table page-level metrics, when `dbstat` is available, in a single pass: `SELECT name, SUM(pgsize) AS allocated, SUM(payload) AS payload, SUM(pgsize - payload - unused) AS overhead, SUM(unused) AS unused, COUNT(*) AS pages FROM dbstat GROUP BY name`. Join the result against `sqlite_master` to classify each name as `table`, `index`, or `virtual-shadow`, and to recover the parent virtual table for FTS shadow tables.
  - Roll FTS shadow tables (`runs_fts_data`, `runs_fts_idx`, `runs_fts_content`, `runs_fts_docsize`, `runs_fts_config`) up under their parent `runs_fts` entry with a `shadows: [{name, allocated, payload, pages}]` array so the operator sees both the aggregate and the breakdown. Use the same parent-detection logic already in `_diag_db_stats()` for shadow names.
  - Per-table payload-byte estimates from the live data, executed even when `dbstat` is missing, one query per table chosen for cost (no `LENGTH(*)`):
    - `runs`: `SUM(LENGTH(output))`, `SUM(LENGTH(output_preview))`, `SUM(LENGTH(output_search_text))`, `SUM(LENGTH(command))`, plus row count and average row size.
    - `snapshots`: `SUM(LENGTH(content))`, `SUM(LENGTH(label))`, row count.
    - `entity_intel_snapshots`: `SUM(LENGTH(data_json))`, `SUM(LENGTH(summary))`, row count, breakdown by `provider` (`GROUP BY provider`) so a single noisy provider is visible.
    - `findings`: `SUM(LENGTH(raw_line))`, `SUM(LENGTH(title))`, row count.
    - `findings_occurrences`: `SUM(LENGTH(snippet))`, row count.
    - `evidence_packages`: `SUM(LENGTH(manifest))`, `SUM(LENGTH(description))`, row count.
    - `project_links`: `SUM(LENGTH(source_detail))`, row count.
    - `run_output_artifacts`: `SUM(byte_size)`, row count (this is on-disk gzip; clarify in the rendered label).
    - `run_file_artifacts`: `SUM(byte_size)`, row count, breakdown by `kind`.
    - Every other table: row count and average row size only (avoids a full scan on small-row tables like `session_variables`).
  - Per-index sizing (allocated bytes, page count, parent table) so an index that has quietly grown larger than its table — common with FTS shadows and `idx_findings_*` — is visible. Order indexes within each parent table by allocated bytes descending.
  - Include three top-level summary fields on the new payload: `total_allocated_bytes`, `total_payload_bytes`, and `wasted_bytes = total_allocated - total_payload - freelist_count * page_size`. The wasted-bytes field is the single number an operator watches before running `VACUUM`.
  - Add a `largest_runs` probe — `SELECT id, started, LENGTH(output) + LENGTH(COALESCE(output_search_text,'')) AS size FROM runs ORDER BY size DESC LIMIT 10` — so a single oversized run (typical cause of unexpected DB growth) is named, not just sized in aggregate.
  - Wrap each subsection in its own `try/except` matching the surrounding `_diag_db_stats` pattern; one failing pragma or missing table never blanks the whole panel.
  - Keep the route read-only and cheap enough for occasional operator use. The new payload-byte sums on `runs` and `snapshots` will scan the table once each; document the expected ms cost on a 1 GB database in the function docstring and gate the largest_runs probe behind `dbstat_available or table_row_count('runs') < 100000` so it never lands as the new slowest part of `/diag`.
- **Frontend rendering**
  - Add a new section in `app/templates/diag.html` after the existing Database Details card, titled **Storage breakdown**. Render one collapsible group per operator bucket, with the bucket header showing aggregate allocated bytes and a sparkline-style bar across the page for visual scale.
  - Within each bucket render a table with columns: name, kind (table/index/fts-shadow), allocated, payload, overhead, unused, rows, avg row, notable columns (e.g. `output: 312 MB`, `output_search_text: 41 MB`).
  - Sort tables within each bucket by allocated bytes descending. FTS shadow tables render indented under their parent virtual table with the existing `.diag-muted` styling.
  - When `dbstat_available` is false, render the entire allocated/payload/overhead/unused/pages columns as `—` and show the rebuild banner once at the top of the section.
  - Add a single top-line callout above the buckets: "Database file 4.2 GB · 1.1 GB reclaimable (`VACUUM`) · 312 MB largest table: `runs.output`".
  - Reuse `_diag_fmt_bytes` for every byte value and the existing `.diag-section-title`, `.diag-muted`, and `.diag-ok`/`.diag-fail` classes so the new panel matches the rest of `/diag` without new CSS.
- **Terminal integration (follow-up, not blocking)**
  - Expose the same summary through a terminal built-in once the panel is stable — natural homes are the existing `stats`, `retention`, or `limits` commands in `app/services/commands/builtins_runtime.py`. Reuse the helper directly rather than re-querying so SQL changes only land in one place.
- **Tests**
  - Add `tests/py/test_diag_storage_breakdown.py` covering: `dbstat` available path renders allocated bytes; `dbstat` missing path falls back gracefully without 500s; FTS shadow tables roll up under `runs_fts`; payload-byte sums match `SUM(LENGTH(col))` on a seeded fixture; `largest_runs` returns sorted rows; the bucket grouping covers every table that `_create_schema` and `_create_project_workspace_schema` create (drift guard so new tables can't silently appear "uncategorized").
  - Add a Playwright smoke test that loads `/diag` against a seeded DB and asserts the **Storage breakdown** section renders with at least one row and the rebuild banner is absent when SQLite has `dbstat`.

### Prometheus `/metrics` endpoint
- **Scope**
  - Add a new IP-gated `/metrics` route that exposes OpenMetrics-format text suitable for Prometheus scrape and Grafana dashboards. Gated by the same `diagnostics_allowed_cidrs` config key as `/diag` so it is never internet-exposed by default.
  - First-pass metric set is broad on purpose — operators should be able to answer the common questions (active load, failure rate, per-tool latency, queue depth, cache hit rate, storage growth, rate-limit pressure, intel-provider health) without a follow-up release.
  - All metric names are prefixed `darklab_` and use Prometheus base units (seconds, bytes, ratio). Label cardinality is bounded — `tool` is the normalized command root, never the full command string; `provider` is the registered intel provider key; `route` for HTTP metrics is the Flask endpoint name, never the raw path.
- **Library and process model**
  - Add `prometheus_client` to `app/requirements.txt`.
  - Use the `prometheus_client.multiprocess` collector so counters and histograms aggregate correctly across Gunicorn workers. The collector requires a writable shared directory.
  - New config key `prometheus_multiproc_dir` defaulting to `/tmp/darklab_shell-prom`. Set `PROMETHEUS_MULTIPROC_DIR` from this value at process boot in `app.py` before any metric is registered, and create the directory if missing.
  - Update `docker-compose.yml` / `Dockerfile` to ensure the multiproc dir lives on a tmpfs (small, ephemeral, per-container) so dead-worker cleanup is automatic on container restart.
  - Add the `MultiProcessCollector` registry inside the `/metrics` handler; per-worker counters are still defined as module-level globals (one definition site, exported through `app/services/metrics/__init__.py`).
- **Initial metric set**
  - **Application/build info**
    - `darklab_build_info{version,git_sha,python_version}` — gauge fixed at 1; cheap way to correlate metric series with a release.
    - `darklab_app_start_time_seconds` — gauge set once at boot; uptime is `time() - app_start_time_seconds` in Grafana.
  - **Runs (external + builtin)**
    - `darklab_active_runs` — gauge of currently-tracked active runs (read from `active_runs_for_session` aggregated across sessions, or maintained inline at `active_run_register` / `active_run_remove`).
    - `darklab_runs_started_total{tool,run_kind}` — counter; `run_kind` is `external`/`builtin`, `tool` is the normalized command root.
    - `darklab_runs_finished_total{tool,run_kind,exit_code_class}` — counter; `exit_code_class` is `success` (0), `error` (>0), `signal` (negative or `>=128`), or `timeout` (the graceful-termination exit code constant in `core/helpers.GRACEFUL_TERMINATION_EXIT_CODE`). Keep the raw exit code out of the label to bound cardinality.
    - `darklab_run_duration_seconds{tool,run_kind}` — histogram; buckets at `0.1, 0.5, 1, 2, 5, 10, 30, 60, 300, 900, 1800, 3600`. Tools like nmap and ffuf stretch the long end; the buckets reflect that.
    - `darklab_run_output_bytes{tool}` — histogram; buckets at `1KB, 10KB, 100KB, 1MB, 10MB, 100MB`. Measures captured output before gzip.
    - `darklab_run_output_truncated_total{tool}` — counter; incremented when `preview_truncated` or `full_output_truncated` is true at finalize.
    - `darklab_run_finalize_errors_total{stage}` — counter; `stage` is one of `capture`, `db_write`, `artifact_write`, `entity_materialize`.
    - Instrumentation point: `app/blueprints/run.py::_finalize_completed_run` and `_persist_completed_pty_run`. Add a single helper in the new metrics module so both call sites stay one-liners.
  - **PTY**
    - `darklab_pty_active` — gauge of live PTY sessions.
    - `darklab_pty_started_total{tool}` — counter.
    - `darklab_pty_duration_seconds{tool}` — histogram; same long-tail buckets as run duration.
    - `darklab_pty_input_bytes_total` — counter; total bytes that the browser sent into PTYs.
    - `darklab_pty_input_dropped_bytes_total{reason}` — counter; `reason` is `rate_limit`, `oversize`, `not_owner`, `closed`.
    - `darklab_pty_control_queue_depth` — gauge sampled at reader-loop tick.
    - `darklab_pty_snapshot_age_seconds` — histogram; how stale a reattach snapshot was when served.
    - Instrumentation point: `app/services/pty/service.py` around input rate-limit checks, snapshot store/load, and lifecycle hooks.
  - **Rate limiting**
    - `darklab_rate_limit_rejections_total{route,scope}` — counter; `route` is the Flask endpoint name, `scope` is `global`, `secrets`, `pty_input`, or `intel`. Updated from the `@app.errorhandler(429)` handler in `app.py` and from the per-feature manual rate limiters in `secrets.py`, `run.py`, and the intel rate limiter.
    - `darklab_intel_provider_rate_limit_waits_seconds{provider}` — histogram of how long a provider call was deferred by the token-bucket limiter in `services/intel/rate_limiter.py`.
  - **HTTP request volume and latency** (lightweight, every request)
    - `darklab_http_requests_total{method,endpoint,status_class}` — counter; `status_class` is `2xx`/`3xx`/`4xx`/`5xx`. Use Flask endpoint, never raw path, to bound cardinality.
    - `darklab_http_request_duration_seconds{endpoint}` — histogram; buckets at `0.005, 0.01, 0.05, 0.1, 0.5, 1, 5`.
    - Instrumentation point: `@app.before_request` records start time; `@app.after_request` records the metric.
  - **Run broker (Redis or in-process)**
    - `darklab_broker_mode_info{mode}` — gauge fixed at 1, where `mode` is `redis`/`in_process` (mirrors the `/diag` value).
    - `darklab_broker_events_published_total{event_type}` — counter; `event_type` is `output`/`status`/`heartbeat`/`pty_output`/`pty_input`/`pty_control`.
    - `darklab_broker_subscribers` — gauge of attached SSE subscribers.
    - `darklab_broker_publish_errors_total{cause}` — counter; `cause` is `redis_unavailable`, `serialize`, `unknown`.
  - **Database (SQLite)**
    - `darklab_db_size_bytes` — gauge (file size).
    - `darklab_db_wal_size_bytes` — gauge.
    - `darklab_db_reclaimable_bytes` — gauge (freelist × page size). Operators alert when reclaimable crosses a threshold to schedule `VACUUM`.
    - `darklab_db_table_rows{table}` — gauge per user table; sampled at scrape time by the same helper that powers `/diag` table rows.
    - `darklab_db_table_allocated_bytes{table}` — gauge per user table, only when `dbstat` is available (reuses the helper from the Table-size diagnostics plan above).
    - `darklab_db_fts_orphans` — gauge.
    - `darklab_db_query_duration_seconds{operation}` — histogram; `operation` covers `run_insert`, `run_finalize`, `history_list`, `atlas_summary`, `atlas_detail`, `fts_search`. Instrument the small number of hot paths, not every connection.
  - **Redis (when configured)**
    - `darklab_redis_up` — gauge (0/1 from a ping at scrape time).
    - `darklab_redis_ping_seconds` — gauge of last ping latency.
    - `darklab_redis_keys{prefix}` — gauge per known prefix (`runstream`, `proc`, `procmeta`, `sessionprocs`). Reuses the existing `/diag` SCAN helper with the same capped bounds.
    - `darklab_redis_stream_length{prefix}` — gauge sampled across the existing capped sample set.
    - `darklab_redis_connected_clients` — gauge.
  - **Workspace storage**
    - `darklab_workspace_bytes_used` — gauge (sum across all sessions).
    - `darklab_workspace_quota_bytes` — gauge from `workspace_quota_mb` × 1MB.
    - `darklab_workspace_files` — gauge of file count.
    - `darklab_workspace_evictions_total{reason}` — counter; `reason` is `quota`, `inactive`, `manual`.
    - `darklab_workspace_quota_rejections_total` — counter; incremented in `services/workspace/files.py` where a write is rejected for exceeding quota.
  - **Intel providers**
    - `darklab_intel_requests_total{provider,outcome}` — counter; `outcome` is `success`, `cache_hit`, `error`, `missing_secret`, `rate_limited`, `disabled`.
    - `darklab_intel_request_duration_seconds{provider}` — histogram.
    - `darklab_intel_cache_entries{provider}` — gauge.
    - `darklab_intel_provider_secret_missing{provider}` — gauge (1 if the provider is registered but its secret is absent). Drives a "configuration drift" Grafana alert.
    - Instrumentation point: `services/intel/lookup.py` and the per-provider client wrappers.
  - **Atlas entities and findings**
    - `darklab_atlas_entities{type}` — gauge of distinct entities per type (`ip`, `domain`, `url`, `hash`, `cve`); cheap `GROUP BY type` at scrape time.
    - `darklab_findings_total{severity,status}` — gauge.
    - `darklab_findings_materialized_total{run_kind}` — counter incremented from `services/atlas/materializer.py` per run finalize.
  - **Snapshots and shares**
    - `darklab_snapshots_total` — gauge.
    - `darklab_snapshot_creates_total{trigger}` — counter; `trigger` is `manual`, `permalink`, `auto`.
    - `darklab_snapshot_views_total{redacted}` — counter; `redacted` is `true`/`false`.
  - **Health and errors**
    - `darklab_health_status{component}` — gauge per component (`db`, `redis`); 1 = ok, 0 = down/degraded. Sampled at scrape time so it tracks the same surface as `/health`.
    - `darklab_client_errors_total{context}` — counter incremented from the existing `/log` browser-error endpoint; `context` is bounded by an allowlist in the handler to stop a malicious client from inflating cardinality.
    - `darklab_unhandled_exceptions_total{endpoint}` — counter incremented from the Flask `errorhandler(500)`.
- **Architecture**
  - New `app/services/metrics/__init__.py` is the single definition site for every metric: counters, histograms, gauges, label sets, and bucket choices. Every blueprint imports from here so a metric is registered exactly once even with the multiprocess collector.
  - New `app/services/metrics/collectors.py` houses scrape-time gauges that read from the DB and Redis (table row counts, table bytes, workspace bytes, redis key counts, atlas entity counts, findings totals). Implemented as `prometheus_client.Collector` subclasses so they only execute when Prometheus actually scrapes — not on every request.
  - `/metrics` route lives next to `/diag` in `app/blueprints/assets.py`. It calls `ip_is_in_cidrs(get_client_ip(), CFG.get("diagnostics_allowed_cidrs") or [])` first, returns 404 on deny (matches `/diag`), then renders the multiprocess registry with `generate_latest(registry)` and `Content-Type: text/plain; version=0.0.4; charset=utf-8`.
  - Histograms and counters update at the existing instrumentation points listed per-metric above. Adding a new instrumented call site is a one-liner against the metrics module — no per-call-site registry plumbing.
  - For the multiprocess collector, gauges declared as "scrape-time samples" use `multiprocess_mode='livesum'` or `'liveall'` as appropriate; document the choice next to each gauge definition.
- **Configuration**
  - New config keys, defaults sensible for a single-host deploy:
    - `metrics_enabled: true` — when false, the route returns 404 even if the IP is in `diagnostics_allowed_cidrs`.
    - `prometheus_multiproc_dir: "/tmp/darklab_shell-prom"`.
    - `metrics_histogram_buckets_run_duration` and `metrics_histogram_buckets_http_duration` — operator overrides for the duration buckets; defaults baked in.
  - Document `metrics_enabled`, `prometheus_multiproc_dir`, and the IP-gate behavior in CONFIGURATION.md alongside the existing `/diag` section. Include a sample `scrape_configs` block for Prometheus and a starter Grafana dashboard JSON in `docs/grafana/darklab-overview.json`.
- **Operational concerns**
  - Scrape cost: the scrape-time collectors run ~6 grouped SQL queries plus 4 Redis SCANs. Cap the SCANs with the existing `_DIAG_REDIS_SCAN_KEY_CAP` constant so a malicious or runaway key namespace cannot stall a scrape.
  - Multiproc-dir cleanup: on app startup, remove stale `*.db` files matching the dead-worker pattern so an unclean shutdown doesn't double-count.
  - Cardinality guard: add a startup assertion that walks the metrics module and refuses to boot if any metric declares a label set whose enumerable values aren't bounded (e.g. unrestricted `tool` strings). The check uses the same command-root normalizer as the existing classifier.
- **Tests**
  - Add `tests/py/test_metrics_endpoint.py` covering: IP-gate denies non-allowlisted callers; allowlisted callers get a 200 with `text/plain; version=0.0.4`; every metric documented above appears in the rendered output on a seeded fixture; a run-finalize emits `darklab_runs_finished_total{tool,run_kind,exit_code_class}` with the right labels; a 429 from the rate limiter increments `darklab_rate_limit_rejections_total`; an intel call increments `darklab_intel_requests_total` with the right `outcome`.
  - Add a drift guard test that imports the metrics module and asserts every metric name starts with `darklab_` and every histogram declares explicit buckets (no implicit defaults).
  - Update the existing Docker integration smoke test to assert the multiproc directory is writable from the gunicorn worker.
  - Cardinality guard: add a startup assertion that walks the metrics module and refuses to boot if any metric declares a label set whose enumerable values aren't bounded (e.g. unrestricted `tool` strings). The check uses the same command-root normalizer as the existing classifier.
- **Tests**
  - Add `tests/py/test_metrics_endpoint.py` covering: IP-gate denies non-allowlisted callers; allowlisted callers get a 200 with `text/plain; version=0.0.4`; every metric documented above appears in the rendered output on a seeded fixture; a run-finalize emits `darklab_runs_finished_total{tool,run_kind,exit_code_class}` with the right labels; a 429 from the rate limiter increments `darklab_rate_limit_rejections_total`; an intel call increments `darklab_intel_requests_total` with the right `outcome`.
  - Add a drift guard test that imports the metrics module and asserts every metric name starts with `darklab_` and every histogram declares explicit buckets (no implicit defaults).
  - Update the existing Docker integration smoke test to assert the multiproc directory is writable from the gunicorn worker.
  - Cardinality guard: add a startup assertion that walks the metrics module and refuses to boot if any metric declares a label set whose enumerable values aren't bounded (e.g. unrestricted `tool` strings). The check uses the same command-root normalizer as the existing classifier.
- **Tests**
  - Add `tests/py/test_metrics_endpoint.py` covering: IP-gate denies non-allowlisted callers; allowlisted callers get a 200 with `text/plain; version=0.0.4`; every metric documented above appears in the rendered output on a seeded fixture; a run-finalize emits `darklab_runs_finished_total{tool,run_kind,exit_code_class}` with the right labels; a 429 from the rate limiter increments `darklab_rate_limit_rejections_total`; an intel call increments `darklab_intel_requests_total` with the right `outcome`.
  - Add a drift guard test that imports the metrics module and asserts every metric name starts with `darklab_` and every histogram declares explicit buckets (no implicit defaults).
  - Update the existing Docker integration smoke test to assert the multiproc directory is writable from the gunicorn worker.
  - Cardinality guard: add a startup assertion that walks the metrics module and refuses to boot if any metric declares a label set whose enumerable values aren't bounded (e.g. unrestricted `tool` strings). The check uses the same command-root normalizer as the existing classifier.
- **Tests**
  - Add `tests/py/test_metrics_endpoint.py` covering: IP-gate denies non-allowlisted callers; allowlisted callers get a 200 with `text/plain; version=0.0.4`; every metric documented above appears in the rendered output on a seeded fixture; a run-finalize emits `darklab_runs_finished_total{tool,run_kind,exit_code_class}` with the right labels; a 429 from the rate limiter increments `darklab_rate_limit_rejections_total`; an intel call increments `darklab_intel_requests_total` with the right `outcome`.
  - Add a drift guard test that imports the metrics module and asserts every metric name starts with `darklab_` and every histogram declares explicit buckets (no implicit defaults).
  - Update the existing Docker integration smoke test to assert the multiproc directory is writable from the gunicorn worker.

### Postgres production backend and storage scaling plan
- **Decision frame**
  - Pre-condition: this plan converts the existing Research entry into an implementation track. The decision the work converges on is **keep SQLite as the default local/single-user backend** and **add Postgres as the recommended backend for heavy multi-user deployments**, with no flag day — both backends ship side by side and an operator chooses at deploy time.
  - Hard constraint: every query path the app uses today must run unmodified on SQLite. Postgres support is additive; SQLite is not deprecated.
  - Soft constraint: write new query code in a portable subset from the start. The Atlas, intel, and findings tables added since v1.5 are the natural baseline because they already exist in `app/core/database.py` and have not yet sprouted SQLite-only optimizations beyond the FTS5 virtual table.
- **Phase 0 — Measure current pressure (one-time research, blocking)**
  - Run the new Storage breakdown panel (see plan above) on a seeded production-shape database and capture: per-table allocated bytes, per-column payload bytes, FTS shadow-table cost, and the largest-run distribution.
  - Project one-year growth at 10, 30, and 100 heavy users using the captured per-run averages (output bytes, search-text bytes, artifact bytes, entity-row count, finding-row count, snapshot bytes). Multiply by the configured `permalink_retention_days` and pruning policy.
  - Identify the candidate "fat" columns for offload to filesystem/object storage: `runs.output`, `runs.output_search_text`, `snapshots.content` for very long shares, and `entity_intel_snapshots.data_json` for raw provider payloads.
  - Output of this phase is a short `docs/storage-scaling.md` with the measured numbers and a sizing recommendation per deployment tier. Without this, the rest of the plan is guesswork.
- **Phase 1 — Storage abstraction in `app/core/database.py`**
  - Introduce a thin `DatabaseBackend` enum (`sqlite`, `postgres`) selected at boot from a new config key `database_backend` (default `sqlite`).
  - Move every `sqlite3`-specific call (`db_connect`, pragmas, `sqlite_compileoption_used`, `dbstat`) behind a backend-aware module. SQLite path keeps its current behavior bit-for-bit; the Postgres path stays unimplemented in this phase but the interface lands.
  - Replace bare `?` parameter placeholders with a backend-aware paramstyle helper (`?` for SQLite, `%s` for Postgres) or migrate to named placeholders (`:name`) which both backends support — the named-placeholder route is preferred because it survives `INSERT ... RETURNING` rewrites.
  - Define a small "dialect" module covering: `JSON` column type (TEXT for SQLite, JSONB for Postgres), `now()`/`datetime('now')`, upsert syntax (`ON CONFLICT ... DO UPDATE` works on both — confirm Postgres ≥ 9.5), boolean handling (INTEGER 0/1 vs BOOLEAN), `RETURNING` support, and substring/concat operators. Document each chosen idiom in the dialect module so call sites don't reinvent them.
  - Audit every existing `db_connect()` call site against the dialect rules. Today's hot paths in `services/projects/workspace.py`, `services/runs/comparison.py`, `services/atlas/lookup.py`, `services/atlas/materializer.py`, and `blueprints/run.py` are the priority — collectively they own most of the schema's writes and reads.
- **Phase 2 — Schema portability for the new tables**
  - Apply the dialect to the schema definitions in `_create_schema` and `_create_project_workspace_schema`. Concrete deltas:
    - Replace `INTEGER` boolean columns with portable equivalents: keep `INTEGER NOT NULL DEFAULT 0` everywhere since both backends accept it and it preserves on-disk shape for SQLite users.
    - Switch JSON-bearing TEXT columns (`session_preferences.preferences`, `user_workflows.inputs`, `user_workflows.steps`, `entity_intel_snapshots.data_json`, `project_links.source_detail`, `evidence_packages.manifest`) to a portable `JSON_COLUMN` macro that resolves to `TEXT` on SQLite and `JSONB` on Postgres.
    - Audit every `UNIQUE (...)` and `PRIMARY KEY (...)` constraint for case-sensitivity differences — Postgres collations affect index reuse where SQLite is byte-exact.
    - FTS: do not attempt to port FTS5 to Postgres. Instead, behind the backend flag, build the search path on Postgres using `tsvector` + GIN indexes maintained by an `AFTER INSERT` trigger on `runs`. The application API (`search_runs(query)`) stays unchanged; only the implementation diverges.
  - Migrations: introduce `app/core/migrations/` with numbered, idempotent migration files. SQLite continues to run schema creation on boot; Postgres runs migrations on boot guarded by an advisory lock so concurrent gunicorn workers don't race. The first migration codifies the current schema as the v1 baseline; new tables land as additional numbered migrations.
- **Phase 3 — Large-body offload (independent of backend choice)**
  - Add a configurable filesystem-backed body store for `runs.output_search_text` (already lossy-ok), `snapshots.content` (when above a configurable threshold), and `entity_intel_snapshots.data_json` raw payloads. The DB keeps a pointer (`rel_path`, `byte_size`, `sha256`) like `run_output_artifacts` already does.
  - Configurable thresholds: `runs_search_text_inline_max_bytes`, `snapshots_inline_max_bytes`, `intel_payload_inline_max_bytes`. Below the threshold, content stays in the column; above it, the column stores the pointer and a short preview.
  - This phase is independent of Postgres — it reduces SQLite pressure on its own and reduces Postgres row width if/when the swap happens. Document in `docs/storage-scaling.md` which deployments benefit most from offload alone vs. needing Postgres.
- **Phase 4 — Postgres adapter and Docker Compose service**
  - Add `psycopg[binary]` to `app/requirements.txt` (gated import; only loaded when `database_backend == "postgres"`).
  - Implement the Postgres dialect concretely: connection pool via `psycopg_pool`, transaction-per-request, the FTS replacement, advisory-lock-guarded migrations, and per-backend retry behavior for transient errors.
  - Reuse the existing `_diag_db_stats` and Storage breakdown plan against `pg_class`, `pg_indexes`, and `pg_stat_user_tables` so `/diag` remains useful on Postgres without a parallel UI.
  - New Docker Compose service `postgres:` with a named volume, version-pinned image, healthcheck, and `depends_on` from the app service. Document Compose overrides for operators who already run their own Postgres.
  - New config keys: `database_backend`, `database_url` (DSN for Postgres), `database_pool_min`, `database_pool_max`. SQLite path ignores all of them and continues to use `DB_PATH`.
- **Phase 5 — Migration helper**
  - New `python -m core.migrate_sqlite_to_postgres` command that streams every table from a source SQLite file into a fresh Postgres database, preserving primary keys, foreign relationships, and JSON column values. Idempotent (`INSERT ... ON CONFLICT DO NOTHING`) so an interrupted migration resumes cleanly.
  - The migration helper does NOT rebuild FTS data — it stops with a clear message after the metadata copy, then runs the Postgres-side `tsvector` trigger to backfill search rows. This avoids reimplementing FTS5 tokenization in Python.
  - Document a recommended cutover procedure in `docs/postgres-migration.md`: snapshot the SQLite file, run the migration helper into a staging Postgres, validate row counts via the new `/diag` storage panel against both backends, switch `database_backend` and `database_url`, restart.
- **Phase 6 — Test matrix**
  - Parameterize `tests/py/conftest.py` so the existing backend-module and route tests run against both SQLite (default) and Postgres (when `DARKLAB_TEST_POSTGRES_DSN` is set in the environment). CI runs both lanes; local dev runs SQLite only unless the env var is set.
  - Add a per-backend smoke test exercising: run insert + finalize, FTS-equivalent search, Atlas materialize, project link, intel snapshot insert with a JSON payload, snapshot create.
  - Add the migration-helper integration test: build a SQLite fixture, run the migration, query the Postgres database, assert row-count equality and JSON-column equality table by table.
- **Documentation**
  - Add `docs/storage-scaling.md` (deliverable from Phase 0) and `docs/postgres-migration.md` (deliverable from Phase 5).
  - Update CONFIGURATION.md with the new keys (`database_backend`, `database_url`, `database_pool_min`, `database_pool_max`, the offload thresholds), the Docker Compose `postgres:` service shape, and the supported version matrix.
  - Update ARCHITECTURE.md with the new dialect module, the FTS divergence, and the offload-store concept so future contributors don't reinvent either piece.
  - Update CHANGELOG.md and the v2.x release notes in `docs/release-drafts/` as each phase lands; the merge-request draft tracks the cross-phase rollout so reviewers see the staged plan.
- **Non-goals**
  - No multi-master, no read replicas. The first Postgres release targets the same single-writer-with-many-readers shape the app already assumes.
  - No automatic backend selection by load. The deployment-time config key is the only switch.
  - No backward compatibility wrappers in Python data classes for SQLite vs. Postgres row shapes — every row reader uses keyed access (`row["column"]`) already, which works on both backends.

### External intel provider enhancements
- **Lower-priority candidates**
  - **MISP** for operator-owned intel. Treat it as a self-hosted integration with `MISP_URL` plus `MISP_API_KEY`, not as a globally available default.
  - BuiltWith Pro and other commercial tech-fingerprint services until local/lightweight tech detection proves insufficient.
  - DeHashed, IntelligenceX, PassiveTotal/Defender TI, and DNSDB until entity storage, provider-status UI, and operator policy controls exist.
  - More vendor CLIs unless the CLI adds a materially better workflow than an app-native REST call.
- **Provider management follow-up**
  - Add an optional operator provider denylist if deployments need to block outbound calls to specific vendors.
  - Revisit mutating provider flows, such as urlscan.io scan submission, only after privacy, terms, visibility, and user-confirmation rules are explicit.

### Future Project Workspace enhancements
- **Security and lifecycle**
  - Validate `workspace_file` entity ownership during session migration, or document that labels/notes on workspace-file paths can drift when a migrated token lands in a session with a different file at the same path.
  - Add a terminal-native `project rename <name-or-id> <new-name>` command so CLI users can rename projects without opening the modal.
  - Add parallel PATCH routes for partial project and target updates if the project workspace API ever becomes more than a trusted browser-only surface.
- **Code organization**
  - Split `project_workspace.py` into focused modules once the surface settles. Natural boundaries are core project CRUD, entity metadata, findings, packages, and session migration.
  - Move Projects modal rendering and event wiring out of `shell_chrome.js` into a dedicated project workspace browser module.
  - Reduce repeated `projects.py` route boilerplate with small serialization/404 helpers.
- **Capture, tagging, and navigation**
  - Expose `Add label`, `Add note`, `Open in project`, and `Add as project target` on transcript right-click or signal-tagged token long-press; this should replace the removed Projects-modal quick-add target flow.
  - Add contextual quick-add target entry points from history rows and workspace file previews once the shared action-menu pattern exists.
  - Consider a per-project current-target sub-state so `${target}` placeholder substitution can follow sustained work on a single host.
  - Decide whether `host` remains a visible target type or is retained only as a backend compatibility value.
  - Add a compact project switcher near the prompt with recently used projects and a Create New action.
  - Show run, finding, artifact, and package counts on project-list rows so project scale is visible before opening each project.
- **Future-state mobile polish**
  - Add OS Back / browser Back support with `history.pushState` after the base sheet navigation is stable.
  - Add a project search/filter input above the mobile list once project counts justify it.
  - Consider swipe gestures for target and finding rows only after overflow-menu interactions are shipped and tested.
- **Findings and comparison**
  - Extend the Findings tab filters beyond target/run/review state to command root, severity, scope, labels, and note state.
  - Add multi-select plus bulk review actions for high-volume finding review.
  - Prefetch finding counts and severity distribution so tab labels can show useful state such as unreviewed/high counts without opening the tab.
  - Extend comparison beyond run-to-run finding/artifact diffs to snapshots and package artifacts.
- **Evidence packages**
  - Materialize evidence package archives at creation time if byte-for-byte repeat downloads become important.
  - Make package presets config-driven so new bundle profiles, such as internal review or external handoff, can be added without code changes.
  - Add richer per-finding remediation or verification fields if findings evolve beyond raw output capture.
  - Add richer target references in package exports, including derived relationships that are not directly visible in selected finding text.
  - Add richer provenance metadata and round-trip import hints for labels, notes, targets, findings, and packages.
  - Explore fuller direct template reuse for package run transcript pages without reintroducing app-hosted asset links.
  - Add redacted text/JSON derivatives for safe artifact types before allowing raw artifact inclusion in redacted packages.
  - Add richer redaction previews and per-item redaction warnings for package creation.
  - Add async package build progress for large Full Archive exports so long builds do not feel like stalled requests.
  - Add generated re-package names that preserve the original selection while incrementing the package label or timestamp.
  - Move package HTML rendering toward shared Jinja autoescape paths so package output escaping is template-owned instead of manual per-call escaping.
- **Retention and mobile**
  - Finish pruning/retention behavior for project-linked runs and run-scoped artifacts.

### Future interactive PTY enhancements
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

### Run comparison follow-ups
- Consider active-tab compare, snapshot/permalink compare, package-artifact compare, and export/share comparison once the run-vs-run model has more production use.
- Add focused large/noisy output regressions if real scanner output exposes performance or alignment gaps beyond the current backend, Vitest, and Playwright coverage.

## Research

No research items are currently tracked.

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Tool-specific guidance
- Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `naabu`, or `nuclei`.
- Good fit for the existing help / FAQ / welcome surfaces.
- Merge this with onboarding and command hints into a broader user guidance layer:
  - command-specific caveats
  - what to expect while a tool runs
  - examples of when to use one tool vs another

### Command catalog future-state
- Add `commands search <term>` for roots, descriptions, categories, examples, and flag text.
- Add `commands --json` or `commands info --json <root>` for debugging, export, and future UI reuse.
- Add optional richer registry fields such as `details`, `notes`, `common_flags`, or `gotchas` when a flag or tool needs more than a short autocomplete description.
- Add command-specific guidance for web-shell behavior, including injected safe defaults, quiet-running tools, generated Files output, and managed session state.
- Add autocomplete side previews later: when a root, subcommand, or flag is highlighted, show the command description or flag note in a small help pane.
- Add hover/focus cards for FAQ chips once the command-details modal behavior has settled.
- Consider including pipe helpers in a separate “Pipes” section once command catalog UX exists.
- Consider linking command catalog entries to real `man` output where available, while keeping app-native allowed-subset details primary.

### Command outcome summaries
- For selected tools, generate short app-native summaries below the raw output. Security tool output is high-volume; a clear findings layer is what separates a purpose-built tool from a raw terminal.
- Keep raw output primary — the summary is additive, never a replacement.
- Start narrow: nmap (open ports + service table), dig (records returned), curl (status code + redirect chain), openssl s_client (cert expiry + trust chain).
- The structured output model (see Architecture) is the right long-term foundation. Build this feature so it can move onto that model later instead of requiring it up front.

### Transcript noise classification
- Future cleanup for saved command output across both normal runs and interactive PTY runs.
- Avoid broad duplicate-line removal because repeated lines can be meaningful findings for some tools.
- Classify known progress/status/redraw lines before history/search/finding classification, starting with high-noise shapes from tools like `masscan`, `ffuf`, `nuclei`, and ProjectDiscovery tools that emit frequent status updates.
- Keep real newline-terminated findings and normal scrollback untouched.
- For interactive PTY runs, keep the final visible frame available so users can still inspect the last terminal state, even when progress/status redraw lines are excluded from searchable saved transcript text.
- For normal runs, prefer command-specific noise classifiers over global suppression so raw output stays faithful while search, findings, summaries, and previews become easier to use.

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
- The history drawer can delete all, delete non-favorites, and use visible-page multi-select for bulk project add/remove plus selected-item delete. Bulk export to JSONL/txt and bulk share would close the remaining gap when packaging selected history items after an engagement.

### Autocomplete suggestions from output context
- When a previous command's output is in the active tab, `| grep` completions could suggest patterns already present in that output — IP addresses, hostnames, status codes, CVE strings — as candidates alongside the generic flag list.
- Narrow but would make the pipe stage feel predictive rather than generic.

### Mobile share ergonomics
- The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
  - save/share actions tuned for one-handed use
  - clearer copy/share/export affordances inside the mobile shell
  - better share handoff after snapshot creation

### Scheduled and recurring runs
- Cron-style scheduler so any command or workflow can fire on a cadence (daily nmap, hourly httpx, weekly subdomain sweep) without keeping the tab open. Nothing in the app is currently time-driven.
- **Entry-level scope:**
  - Save a schedule from any command or workflow with a cron expression or a small cadence preset (hourly/daily/weekly).
  - Schedules belong to the active session token and migrate with it.
  - Fired runs land in normal history tagged `scheduled` with the originating schedule ID.
  - List/pause/delete schedules through a new `schedule` built-in plus a Schedules modal beside Workflows.
- **Architecture:**
  - New `app/services/scheduler/` service backed by APScheduler (or a small Redis sorted-set tick loop) running in a dedicated `scheduler` process so worker restarts do not lose ticks.
  - SQLite `schedules` table: id, session_token, command/workflow ref, cron, enabled, last_run_at, next_run_at.
  - At fire time the scheduler enqueues through the existing `/runs` broker under the owning session so allowlist, deny-prefix, registry rewrite, and history persistence are reused unchanged.
  - New `app/blueprints/schedules.py` for CRUD; new `schedule` handler in the session built-in family; new `app/static/js/features/schedules/` for the modal and runtime autocomplete.
  - Gotchas: cron string validation, surfacing missed fires after a container restart, and tearing down schedules when their session token is revoked.

### Watchers (change-detection monitors)
- Pair a recurring command with a stored baseline and notify only when output diverges (new open port, new subdomain, new finding signature, TLS cert change). Builds on the run-comparison diff engine but exposes it as a persistent first-class object, not a one-off compare.
- **Entry-level scope:**
  - Create a watcher from any completed run ("watch this nmap for new open ports").
  - Watchers reuse the scheduler service to re-run on a cadence.
  - Each fire stores a structured diff against the prior accepted baseline; notifications fire only on non-empty diffs.
  - A Watchers modal shows status (ok / changed / firing), last fire, last diff, with accept-new-baseline and pause actions.
- **Architecture:**
  - New `app/services/watchers/` service composing the scheduler service with the existing comparison helpers in `app/services/runs/comparison.py`.
  - SQLite `watchers` table: id, session_token, command, schedule_ref, baseline_run_id, last_run_id, last_diff_summary, state.
  - Reuses the structured finding/signal model when present; falls back to textual added/removed line diffs otherwise. The structured output model called out in Architecture is the natural long-term substrate.
  - Fires through the new outbound-notifications surface so a watcher hit can reach Slack/email/push without duplicating delivery code.

### Outbound notifications (webhooks, Slack, Discord, email)
- Run-complete, finding-classified, and watcher-fired events fan out to external channels per session or per project. Existing notifications are browser-foreground only; this closes the loop for solo operators running long scans away from the tab.
- **Entry-level scope:**
  - Configure one or more channels per session token. Start with a generic JSON webhook; layer Slack, Discord, and SMTP email on the same channel abstraction.
  - Triggers: run-complete (per exit-code policy), finding-classified, watcher-fired, scheduled-run-failed.
  - Per-channel mute plus a global "do not disturb" toggle.
  - Notification body uses only the command root, matching the existing browser desktop-notification policy that intentionally avoids exposing arguments or token values.
- **Architecture:**
  - New `app/services/notifications/` service with a `Channel` base class and `WebhookChannel`, `SlackChannel`, `DiscordChannel`, `EmailChannel` implementations. SMTP is operator-config-gated in `app/conf/config.yaml`.
  - SQLite `notification_channels` table (per session token, encrypted secret column for webhook URL / bot token) and `notification_events` for delivery audit and retry.
  - Hook points: run finalization in `app/blueprints/run.py`, watcher fire path, scheduler error path.
  - Browser surface: Options modal "Notifications" section; new `app/static/js/features/preferences/notification_channels.js`.
  - Secret storage rides on the encrypted-secrets-vault idea below rather than introducing a parallel ciphertext path.

### Headless API and CLI client
- Stable REST endpoints plus a thin `darklab` CLI, authenticated by an existing session token, that can launch runs, poll history, and pull artifacts from CI pipelines or local scripts.
- **Entry-level scope:**
  - REST: `POST /api/v1/runs`, `GET /api/v1/runs/<id>`, `GET /api/v1/runs/<id>/stream` (SSE), `GET /api/v1/history`, `GET /api/v1/history/<id>/output`, authenticated via `Authorization: Bearer tok_...`.
  - CLI: `darklab run "nmap …"`, `darklab tail <id>`, `darklab history`, `darklab download <id> [--workspace]`.
  - Same allowlist, deny-prefix, registry-rewrite, and rate-limit bucket as the browser path so headless use cannot bypass per-session limits.
- **Architecture:**
  - New `app/blueprints/api_v1.py` reusing the existing run broker, history service, and validation; OpenAPI/JSON schema published at `/api/v1/openapi.json` for clients to consume.
  - CLI ships as a tiny Python package under `tools/darklab_cli/` with its own `pyproject.toml`; communicates only via the REST blueprint, no shared imports with the server runtime.
  - Output streaming reuses the broker SSE path so multi-worker reattach already works.
  - Documented in a new `docs/api.md` plus a CONFIGURATION.md section.

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
  - New `app/services/reports/` service composing project-workspace data with existing finding/run/artifact serializers; templating via Jinja autoescape (aligns with the package HTML rendering follow-up in Open TODOs).
  - Adds `GET/POST /projects/<id>/report` to `app/blueprints/projects.py`.
  - Browser surface: a "Report" tab inside the existing Projects modal; renderer reuses `export_html.js` and `export_pdf.js`.
  - Honors share-redaction defaults; the draft is always previewed before download so this stays additive to evidence packages, not a replacement.

### Session Entity Atlas (entity-first triage surface)
- Reframe darklab_shell's exploration model so entities (findings, hosts/IPs, domains, hashes, CVEs, URLs) become the primary navigation primitive — not runs, not projects. Runs become the *source* of entities. Projects become a *curated subset* of entities for engagement work. The active session token owns the entity graph.
- **The gap it closes:**
  - Every run already produces classified findings, but the rich exploration UI lives inside Projects. Runs not linked to a project surface findings only inside Run Details with no aggregation, triage state, or cross-run pivot.
  - The proposed `intel` built-in widens the gap because intel data is inherently entity-shaped — a Shodan record is about an IP, not the nmap run that produced it. Without an entity-first surface, Findings, Intel, and Projects each grow parallel triage modals that show fragments of the same picture.
  - Project membership stops being a gate on tooling. Users can recon casually and curate later without losing the engagement-grade Projects surface.
- **UI shape:**
  - New top-level **Atlas** surface with the same prominence as History — desktop left-rail entry, mobile menu item, keyboard shortcut. Not a stacked modal.
  - Atlas tabs across the top: Findings, Hosts/IPs, Domains, Hashes, CVEs, URLs. Each tab is a filterable, sortable list of distinct entities extracted across every saved run for the active session token.
  - Entity Detail side sheet opens from any row or from a tagged transcript token:
    - Identity strip — type, canonical value, first/last seen, run count.
    - Intel snapshot card — Shodan / VT / GreyNoise / IPinfo / etc., with explicit refresh so cache state is visible.
    - Source runs list — every run that mentioned the entity, with command, tool, finding count, jump-to-line link.
    - Findings extracted on the entity across all runs.
    - Labels and notes via the existing `ui_entity_metadata.js` helper.
    - Promote-to-project action.
  - Transcript ↔ Atlas wiring:
    - Tagged tokens become click targets; click opens entity detail; long-press / right-click exposes the full action menu (label, note, promote, copy, lookup intel).
    - Hover popover on tagged tokens shows the high-signal summary (GreyNoise verdict, Shodan port count, VT positives) without leaving the transcript.
    - "See in run" inside entity detail jumps back to the source line in the original run.
- **Phased rollout:**
  - Phase 1 — Read-only Atlas: render Findings, Hosts, Domains, Hashes, CVEs tabs from data already classified by `app/core/output_signals.py`. Rows click into their source run; no new metadata yet. Ships value alone.
  - Phase 2 — Entity Detail: aggregate across runs, attach labels/notes, dedupe via stable signature, "see in run" navigation.
  - Phase 3 — Intel attachment: explicit `intel` results, sidecar enrichment, and pipe-helper enrichment all write into entity-keyed intel rows; entity detail renders them.
  - Phase 4 — Findings triage state: keep finding review actions (`new`, `reviewed`, `important`, `false_positive`, `needs_followup`) on the Findings tab. The standalone Findings triage inbox idea folds in here instead of shipping as its own surface.
  - Phase 5 — Project linking: adding to a project becomes a tag on the entity row; project workspace, evidence packages, and engagement report builder all read from the same entity store.
- **Architecture:**
  - Storage:
    - New `entities` table keyed by (session_token, type, canonical_value, signature_hash) for stable dedupe across runs.
    - `entity_run_links` (entity_id, run_id, first_seen, last_seen, occurrence_count) so cross-run aggregation is a single join.
    - `entity_intel_snapshots` (entity_id, provider, payload_json, fetched_at, ttl) keyed by provider so refresh and quota stories stay tractable.
    - Existing `project_links` rows with `entity_type='atlas_entity'` replace per-project copies of entity rows; no standalone `entity_project_links` table.
  - Services:
    - New `app/services/atlas/` service with materialization helpers that run at run-finalize time, consuming entity events surfaced by the entity-aware output classifier hooks called out under the intel integrations idea.
    - Entities are extracted lazily and deduped via stable signature so long sessions do not balloon SQLite. Materialization is idempotent so re-finalizing a run does not double-count.
    - Reuses the existing label/note helpers, run-comparison structured-finding model, and intel provider modules.
  - Routes:
    - New `app/blueprints/atlas.py` for list, filter, detail, and entity-mutation routes (labels, notes, project links, intel refresh).
    - Existing Findings, Run Details, and Projects routes read from the same entity store rather than maintaining parallel finding queues.
  - Browser surface:
    - New `app/static/js/features/atlas/` for the Atlas surface, tab list rendering, entity detail side sheet, transcript hover popover, and tagged-token action menu.
    - New `app/static/css/features/atlas.css`.
    - Run Details, Projects, and the `intel` result card all link into entity detail rather than re-rendering entity data locally.
  - Sharing and exports:
    - Entity rows themselves never appear in snapshot permalinks; only the source run transcript does. The existing share-redaction path already covers raw transcript content and raw-only intel omissions.
    - Engagement report builder (separate idea) reads from the entity store for "targets", "findings", and "intel observations" sections, replacing per-project ad-hoc aggregation.
- **Anti-patterns to avoid:**
  - Do not build the Atlas as yet-another-modal stacked over History. It needs first-class chrome treatment (rail entry, shortcut, mobile menu item) or it will be invisible.
  - Do not duplicate entity metadata between Atlas and Projects. Project membership is a tag on the entity row; labels, notes, and intel live on the entity.
  - Do not materialize entities eagerly for every line of output. Extract lazily from classifier events at finalization and dedupe with stable signatures so SQLite cost scales with distinct entities, not output volume.
  - Do not gate intel data on the user calling `intel` explicitly. Sidecar enrichment, pipe-helper enrichment, and explicit `intel` calls must all write through the same per-entity intel rows so a user who never types `intel` still sees enriched data.
  - Do not break runs that have no findings. Utility commands and failed commands produce zero entities; the Atlas must treat that as the normal case, not an empty state worth surfacing.
- **Relationships to other ideas:**
  - Folds finding triage into the Atlas Findings lens instead of adding a separate inbox surface.
  - Provides the natural home for **External intel provider enhancements** — entity detail is where intel snapshots live; sidecar enrichment, the `intel` built-in, and pipe-helper enrichment all write here.
  - Consumes the entity-aware output classifier hooks called out under intel integrations and the **structured output model** under Architecture.
  - Reframes **Project workspaces** as a curation layer over the entity store rather than the only triage surface; project linking is a tag, not a copy.

---

## Architecture

### Structured output model
- Preserve richer line/event details consistently for all runs.
- This would improve search, comparison, redaction, exports, and permalink fidelity.
- Command outcome summaries are buildable without this foundation, but design them so they can move onto the structured model later. Summary parsers should consume structured line events, not re-parse raw text forever.

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
