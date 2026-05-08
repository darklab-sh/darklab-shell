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
  - **Current state:** the project workspace foundation has landed. Projects are session-scoped organizing layers over reusable app records rather than owners of copied data. Runs, snapshots, and workspace files can be linked into projects; run-derived findings and artifacts surface through linked runs. Targets, labels, annotations, findings, artifacts, and evidence packages are persisted as general app records that can be viewed through a project when related.
  - **Landed foundation:** schema, migrations, indexes, architecture docs, project CRUD/link routes, summary/findings/package APIs, project terminal built-ins, active-project session context, automatic run/snapshot linking, history project filters, declared file artifact capture, persisted finding capture/review APIs, entity label/annotation APIs, project target CRUD/quick-add APIs, active-project target autocomplete, draft evidence package manifests/downloads, project comparison endpoints, diagnostics counts, structured logs, session migration support, and the first-pass Projects modal are in place.
  - **Remaining implementation slices**
    - **Project Explorer UI depth**
      - Add project finding filters for target, run, command root, severity/scope, review state, label, and annotation state.
      - Group artifacts by run command and add preview/download actions for captured artifact rows.
      - Add package actions: download, delete, and manifest preview.
    - **Project actions and capture**
      - Add UI entry points for quick-adding targets from selected transcript text, findings, history rows, and workspace file previews.
      - Add a `Link last run` action in the Runs tab for manual backfill without using the terminal builtin.
      - Make the HUD/mobile active-project display clickable so it opens the Projects modal scoped to the active project.
      - Add a keyboard shortcut for opening the Projects modal.
      - Decide whether `host` remains a visible target type or is retained only as a backend compatibility value.
    - **Evidence and workflows**
      - Replace all-or-derived package creation with a package wizard that can select specific runs, findings, snapshots, artifacts/files, targets, labels, annotations, and notes.
      - Add redacted evidence packages only after archive generation can enforce redaction across manifests and included artifact content.
      - Build the project-modal workflow promotion UI around explicit run and target selection. The backend now reports automatic run truncation and requires `target_id` when multiple project targets match promoted commands.
      - Extend comparison beyond first-pass run-to-run finding/artifact diffs to snapshots and package artifacts.
    - **Retention, mobile, and polish**
      - Finish pruning/retention behavior for project-linked runs and run-scoped artifacts.
      - Improve the mobile project workspace flow after the desktop model settles, likely with a staged layout instead of the dense two-pane modal.
      - Keep `FEATURES.md`, `README.md`, `ARCHITECTURE.md`, release drafts, and tests aligned as each remaining slice lands.

- **Project workspace fixes and enhancements**
  - **Security and hardening**
    - `_entity_belongs_to_session` for `workspace_file` only validates path shape, not session ownership. SQL queries filter by `session_id`, so cross-session reads are mitigated, but `migrate_project_workspace_session` moves labels/annotations along with the session and reattaches them to whatever file lives under that path in the new session's workspace. Either validate the file exists in the target workspace at migration time or document the migration semantics so users know labeled-file metadata can drift on token migration.
  - **Lifecycle and consistency**
    - Auto-link of completed runs to the active project is silent. Surface a one-line transcript notice such as `[project] linked run to <project name>` so users notice when they have forgotten to clear an active project before unrelated work, mirroring the workspace-file save notices.
    - The `project` builtin lacks `delete` and `rename` subcommands even though the HTTP layer supports both. Add `project delete <name-or-id>` (with confirmation) and `project rename <new-name>` so terminal users can finish what the modal can do.
    - Project routes use PUT for partial updates (`/projects/<id>` and `/projects/<id>/targets/<id>`). REST convention is PATCH for partial / PUT for full replacement. Pragmatic but worth a parallel PATCH route if the API ever leaves the trusted browser-only context.
  - **Test coverage gaps**
  - **Architecture and code organization**
    - `project_workspace.py` is 2040 lines covering CRUD, entities, findings, packages, and migration. Reasonable for the scope but at the edge of "single file"; natural splits are `core.py`, `entities.py`, `findings.py`, `packages.py`, `migration.py` once the surface settles.
    - `shell_chrome.js` grew by ~700 lines for the project workspace UI and is now 1567 lines, diluting the file's chrome scope (HUD, status, time). Move project-modal rendering and event wiring into a dedicated `projects_workspace.js` module loaded after `shell_chrome.js`.
    - Many `projects.py` routes follow identical fetch/normalize/404/jsonify boilerplate. A small `_serialize_or_404(result, key)` helper would tighten the file without changing behavior.
  - **UX: capture and tagging**
    - Expose `Add label`, `Add annotation`, `Open in project`, and `Add as project target` on transcript right-click (or signal-tagged token long-press). Label, annotation, and target APIs all exist; the UI doesn't reach them, so signal-tagged data goes one-way into history.
    - Add a "Link last run" button in the Runs tab so users can backfill manual links without dropping to the `project link last` builtin.
    - Consider a per-project "current target" sub-state. Marking one of the project's targets as active would let `${target}` placeholder substitution work at command-submit time, paying off the targets data structure for sustained work on a single host.
  - **UX: findings review**
    - Add a filter and sort bar to the Findings tab for `review_state`, `severity`, and run. The route accepts these filters; the UI doesn't expose them, and the flat "grouped by run" view does not scale past a handful of runs.
    - Add multi-select plus bulk review actions on findings (e.g., "mark all open ports as confirmed", "snooze everything below medium severity"). Once a project has 50+ findings, single-row review becomes the bottleneck.
    - Prefetch finding counts and severity distribution so the Findings tab label can show "5 unreviewed (2 high)" without entering the tab. The summary already returns counts; the per-finding fetch is the only on-demand cost.
    - Build a Compare runs view on top of the existing `/projects/<id>/compare` route. A `Compare to ...` button on a run row plus a diff view (added findings, disappeared findings, changed severity, changed exit code) is the payoff for repeated scans of the same target.
  - **UX: artifacts and packages**
    - Group artifacts in the Artifacts tab by run command, not raw `run_id` (`_renderProjectArtifacts` at `shell_chrome.js:1076`). The run summary already carries the command.
    - Add `Download` and (for text/JSON kinds) `Preview` actions on artifact rows. The Files modal handles workspace files generally; artifacts captured from runs are workspace files at heart and deserve the same affordances inside the project view.
    - Add `Download`, `Delete`, and `View manifest` actions on each row in the Packages tab. The download endpoint exists but the modal lists packages with no way to act on them.
    - Build a "Build package" wizard with checkboxes against the project's runs/findings/artifacts (default all-checked). Today the manifest is auto-derived from the project summary; a real evidence flow needs selective inclusion. Server side: extend the manifest schema to record selected entity ids and respect them during archive build.
    - Show a manifest preview before download (manifest tree plus included artifact paths) so users can verify what they are about to share.
    - Add evidence package redaction as an explicit package option once archive generation can actually apply redaction to manifests and included artifact content. Until then, packages stay raw-only so the UI does not imply a protection that is not enforced.
  - **UX: navigation and discovery**
    - Render run/finding/package counts on each row of the project list. `_loadProjectSummaries` already populates the counts; the list view ignores them, so users have to enter every project to see its scale.
    - Make the HUD active-project cell clickable so it opens the project workspace modal scoped to that project (mobile row same). The cell is read-only display today.
    - Add a project switcher near the prompt — a small project chip in the HUD that opens a popover (recently used plus "Create new"). Switching today requires either typing `project use <name>` or opening the modal and clicking through.
    - Visually separate archived projects in the list (sub-section, tab, or filter toggle). `include_archived=1` is requested but archived rows mingle with active ones.
    - Add a keyboard shortcut to open the project workspace modal, matching the rest of the chrome (`?`, `H`, etc.).
    - Wire the existing `?project_id=X` history filter into the history drawer UI so users can scope the history drawer to a project without round-tripping through the project modal.
  - **UX: cross-tab and mobile**
    - Refresh the open Projects modal when another tab in the same session mutates project data. Pair with the `app:project-workspace-changed` event and `darklab_project_workspace_changed` storage signal that autocomplete now uses so cross-tab edits stop showing stale data.
    - Replace or supplement the desktop-style modal with a mobile-friendly stage layout (Pick project → Pick tab → Detail with back navigation), or move the project workspace to its own route entirely. The current bottom-sheet treatment is dense for phones, and tab + list + form + badges all in one surface is uncomfortable on small screens.
    - Add swipe gestures on target rows and finding rows for mobile (swipe to edit/remove, swipe to mark reviewed) once the desktop affordances are in place.

- **Best-case project evidence packages**
  - **Current state:** `build_evidence_package_archive` (`project_workspace.py`) builds a temp-file-backed zip with `manifest.json`, `README.md`, `index.html`, per-selected-run `runs/<run-id>.html` transcript pages, `findings/findings.json`, `findings/findings.md`, and any included artifacts under `artifacts/`, and the download route streams that path with cleanup after the response closes. The Packages tab lists package rows with `Download`, `Re-package`, `Delete`, and `View manifest` actions, and package creation uses a first-pass four-stage wizard for preset, entity selection, metadata, redaction mode, and package preview. The backend stores explicit selected entity ids, `package_format_version`, package options, and private-notes inclusion state in the manifest, then limits archive artifacts to the selected artifact ids. Missing artifacts, missing selected runs, and transcript caps are surfaced through `index.html`, `README.md`, `skipped-items.json`, and the compatibility `skipped-artifacts.json` file. Redacted packages now apply share/export redaction rules to manifest contents, `index.html`, `README.md`, finding exports, run transcript pages, and package filenames; raw artifact bytes are excluded from redacted packages until artifact-content redaction exists.
  - **Goal:** turn a project package into a self-contained handoff bundle. Recipients should be able to extract the zip, double-click `index.html`, and read the project the way it looks in the live app, without internet access or app login. Selective inclusion is wizard-driven; outputs scale from a manifest-only summary to a full archive with rendered run transcripts.
  - **Snapshot semantics:** package creation should produce a point-in-time bundle, not a live query that silently changes on later download. The package row should store explicit selected entity ids, archive options, recorded artifact hashes/sizes, skipped-item reasons, and generated-at metadata. If the physical archive is materialized at creation time, later downloads serve that exact artifact; if the archive is rebuilt on demand, the rebuild must verify hashes/skip state and surface drift rather than silently packaging changed files.
  - **Wizard UX (four-stage in-modal stepper inside the existing project modal, not a nested modal)**
    - The stepper temporarily replaces the Packages tab content and has a clear `Cancel` path back to the package list. Avoid modal-on-modal behavior so Escape, focus trapping, and mobile sheet behavior stay predictable.
    - **Stage 1 — Preset or custom.** Pick `Summary` / `Evidence` / `Full Archive` / `Custom`. Each preset pre-fills the next stages but does not lock anything; the user can still un-check items. Make presets config-driven so a future "External handoff" or "Internal review" preset is a registry change rather than code.
    - **Stage 2 — Include selections.** A small tree per area, not a flat checklist:
      - Runs: collapse/expand each run with a sub-toggle for `include transcript` per run. Default: all runs checked, transcripts on for runs with findings, off for runs without.
      - Findings: default-include `new`, `reviewed`, `important`, and `needs_followup`; default-exclude `false_positive`. Filter chips at the top mirror the Findings tab's filter bar (review_state, severity, run).
      - Artifacts: show file size next to each row so users can see what is driving the package size before they commit.
      - Targets, labels, and project notes: default-include all, easy to uncheck individually.
      - Notes and annotations: include a clearly named `Include private notes/annotations` checkbox. Keep private notes/annotations excluded unless the user explicitly opts in, then include only the private items the user leaves checked.
      - Every default selection should match what `Custom` would produce if the user reviewed each item once. Avoid presets that hide their effects.
    - **Stage 3 — Package metadata.** Name (auto-suggest `{project-slug}-{YYYY-MM-DD}-{preset}`), description, output options (`manifest.json` only / + `index.html` / + transcripts as HTML / + raw artifacts). Hide the redaction control until the redaction code path actually exists; shipping a confirmed-redacted bundle that is not redacted is a real-incident-class bug.
    - **Stage 4 — Preview and build.** Manifest tree with counts and estimated archive size. List of items that would be skipped and why (artifact missing, transcript over cap, run no longer linked). Confirm → backend builds → row appears in the Packages tab with `Download` / `Re-package` / `Delete` / `View manifest` actions visible immediately.
  - **Package contents (zip layout)**
    - `manifest.json` — explicit list of selected entity ids, counts, provenance (app version, package format version, generated timestamp, source project/session identifiers with masking where appropriate, redaction mode, preset), plus skipped-artifact details.
    - `README.md` — same human-readable summary as `index.html`, plain Markdown so it renders in code-review tools and terminals.
    - `index.html` — self-contained app-styled landing page (see polish notes below).
    - `runs/<run-id>.html` — per-run transcript pages rendered through the existing permalink template, one per included run with `include transcript` checked.
    - `findings/findings.json` and `findings/findings.md` — landed first pass: selected finding rows with title, scope/severity, raw line, review state, source run id/command, source line number, associated target details when present, and transcript links when the source run transcript is included. Still future: inline labels and annotations.
    - `targets/targets.json` — type/value, notes/labels, references to runs and findings that mention each target.
    - `artifacts/<stable-path>` — captured workspace files under stable archive paths matching `manifest.json` artifact entries (original path, size, content type, producing/consuming run, skipped/missing reasons).
    - `notes/` — project notes, per-run notes, per-finding notes, labels, and package-ready annotation metadata. Private notes/annotations only appear when `Include private notes/annotations` is enabled and the specific note/annotation remains checked in Stage 2.
    - `metadata/` — anything else needed for round-trip provenance that does not belong in the top-level manifest.
  - **Self-contained HTML index polish (the differentiator)**
    - Reuse the existing permalink renderer. `app/templates/permalink_base.html` already renders a run's output with signal classes, finding highlights, exit code, command echo, and timestamps. Render `runs/<run-id>.html` through that same template at package-build time so package run pages stay indistinguishable from the live app's share pages, with no duplicate renderer to maintain.
    - One self-contained zip. Inline the CSS subset and fonts (woff2 base64 or shipped under `assets/`) so `index.html` opens offline from any extracted directory. No network fetches, no API calls, no CDN references, no theme switcher — bake one theme in.
    - `index.html` structure: project name, description, notes, generation timestamp, app version, package preset; a counts strip mirroring the project header; targets section as chips; sortable findings table (pure static rendering plus a small inline `<script>` for client-side sort, no frameworks) with rows linked to `runs/<run-id>.html#L<line-number>`; runs list grouped by command with finding counts and transcript links; artifacts section grouped by run command with download links into `artifacts/`; annotations/labels surfaced inline next to the entities they attach to, not in a separate section; skipped items section at the end with honest skip reasons.
    - `README.md` carries the same content for terminal/text-only consumers and tools that auto-render Markdown (GitHub, code review, Linear).
    - Snapshot the relevant CSS into the package keyed to `package_format_version` so future packages can revise styling without breaking older packages or making readers wonder why an old package looks different from the live app.
  - **Phase 1 — `index.html` + run transcript pages.** Landed first pass: packages now include an app-styled `index.html`, selected run transcript pages under `runs/`, selected artifact links, target chips, findings, skipped-artifact reporting, and raw-only transcript output capped by the existing output-line setting. Still future: sortable tables, fuller live-permalink template reuse, annotations/labels inline, and stronger CSS/font snapshotting.
  - **Phase 2 — `README.md` companion and expanded skipped-items reporting.** Landed first pass: packages now include a human-readable `README.md` companion, and skipped artifacts, missing selected runs, and capped transcripts are surfaced in HTML, Markdown, and `skipped-items.json`. Still future: skipped finding-specific reasons, richer Markdown parity with inline labels/annotations, and pre-build size estimation in the wizard. Redaction control still stays hidden; Markdown and metadata outputs remain raw-only until Phase 3.
  - **Phase 3 — Redaction pass and the "redacted" preset.** Landed first pass: redacted packages apply share/export redaction rules across manifest contents, static HTML, Markdown, run transcript pages, and package filenames; the wizard exposes a redaction selector plus a `Redacted Evidence` preset; redacted packages exclude raw artifact bytes because artifact-content redaction is not implemented. Still future: redacted text/JSON artifact derivatives, richer redaction previews, and per-item redaction warnings.
  - **Phase 4 — "Re-package with same selection" action.** Landed first pass: existing package rows can reopen the wizard from the package manifest with prior selected runs, findings, artifacts, targets, redaction mode, artifact inclusion, private-metadata opt-in, name, and description restored. Still future: clearer drift messaging for selected entities that no longer exist, pre-build size estimation, and an optional generated name that preserves the original selection but increments the package label.
  - **Trade-offs and gaps**
    - **Redacted artifact content.** Redacted packages currently exclude raw artifact bytes instead of rewriting them. Add redacted text/JSON derivatives for safe artifact types before allowing raw artifact inclusion in redacted packages.
    - **Build cost.** Rendering HTML for many runs is real work. Cap rendered transcript size per run (config-driven), keep the existing total package size cap, and keep using the temp-file-backed archive builder so the build cost shows up as latency rather than RAM.
    - **CSS coupling.** Snapshot CSS into the package at build time keyed to `package_format_version`. Future format versions can revise styling without breaking older packages.
    - **Run transcript size.** A single noisy run can carry tens of KB of HTML. Default to `include transcript` only for runs with findings; cap the transcript region per run in HTML and link to a `_full.txt` companion when truncated.
    - **Async vs. sync builds.** A `Full Archive` of a large project may take 10–30 s. Stage 4 should show progress via a poll-for-status indicator; do not silently time out the user's request.
    - **Versioned packages.** Same project will produce many packages over time. Date-stamp list rows, allow same-name with different timestamps, and refine "Re-package with same selection" so users can either keep the original label or generate an incremented one.
    - **Private notes and annotations.** Treat private notes/annotations as intentionally excluded unless `Include private notes/annotations` is checked. The wizard should make this choice visible in the preview and record it in `manifest.json` so package recipients and future re-package flows know whether private metadata was included.
    - **Encoding safety.** Use Jinja autoescape for all rendered HTML (commands, finding text, notes). Same pattern as the live templates, so escaping is automatic, not per-call.
    - **Permalink reuse caveat.** Permalinks render against live SQLite and apply share redaction at request time; the package version renders against frozen JSON inside the zip and applies redaction at build time. The template needs to accept either backing source cleanly, with the redaction step explicit at the call site.
    - **Skipped items honestly.** `skipped-artifacts.json` already exists; extend it to include skipped runs/transcripts/findings and surface the reasons in `index.html` and `README.md` rather than hiding them in a metadata file most readers will not open.

- **Improve project target matching**
  - **Where the gap is**
    - `record_run_findings` (`project_workspace.py:1595-1670`) attributes findings to project targets via a single mechanism: substring `target_value in raw_line` against the run's project's targets, ordered `LENGTH(t.value) DESC, t.confidence DESC`. That works only when the command literally contains the target *and* the same string appears in output lines.
    - It under-attributes or attributes nothing when targets come from input files (`nmap -iL targets.txt`), CIDR/range arguments where output emits per-host lines, scans that discover hosts the user never declared, and tools where target attribution is structural rather than literal (`gobuster vhost`, `nuclei -l hosts.txt`, `ffuf` with `Host:` headers, `httpx`, `pd-httpx`).
  - **Logic already in place that we can reuse**
    - `OutputSignalClassifier` (`output_signals.py:391-437`) already attributes a per-line target. `extract_target(command)` parses the command line into a baseline target. `_line_target` watches output for `_NMAP_REPORT_TARGET_RE` and updates `current_target` per host, so subsequent finding lines until the next header inherit it.
    - The result lands on each line as `metadata["target"]`, persists into `output_preview`/`output_search_text`, flows through `_broker_output_payload` (`run.py:203-204`) to the browser, ends up as `data-signal-target` on the rendered span, and is what the Summarize button groups by (`search.js:751`).
    - For any nmap run with `-iL targets.txt`, the classifier already knows which target each finding pertains to. That metadata is sitting unused in `entries[i]["target"]` while `record_run_findings` does substring matching instead.
    - `_target_payload_from_candidate` (`project_workspace.py:1764`) already normalizes a string into `{type, value}` for IPs, CIDRs, URLs, and domains, with `infer_project_target_payload` driving the existing quick-add target inference.
    - Before implementing, confirm every persisted finding path keeps the line metadata intact: normal `/runs`, PTY synthesized output, restored/history output, and any browser-owned run persistence. The matcher should consume `entry["target"]` when available, not re-parse rendered DOM state.
  - **Ideas, ordered by ambition**
    - **Use the classifier's per-line target as the primary attribution source.** Smallest change, biggest leverage. In `record_run_findings`, before the substring fallback, read `entry.get("target")` and match it against the run's project targets by exact value (case-insensitive for hosts/lowercased domains), with an IP-in-CIDR check so a project target like `10.0.0.0/24` collects findings whose extracted target is `10.0.0.5`. Fall back to substring matching only when no metadata target was tagged. This single change closes the `-iL targets.txt` case for nmap immediately.
    - **Centralize target candidate normalization.** Add one helper that turns classifier metadata and raw output context into comparable aliases: raw value, lowercased host/domain, URL hostname, host without port, IP literal, and both sides of nmap's `host (ip)` report form. Use the same helper for finding attribution, candidate target creation, workflow promotion, and future re-attribution so these surfaces do not drift.
    - **Auto-discover project targets from finding-line metadata.** When a finding's classifier-extracted target doesn't match any project target, optionally run it through `_target_payload_from_candidate` and insert with `source_run_id = run_id`, lower confidence (~0.7), and a `discovered`/`auto-discovered` source flag. Link the finding to the new target so subsequent runs benefit too.
    - **Surface auto-discovered targets distinctly in the UI.** Render auto-discovered targets in the Targets section with a small `auto` badge, plus inline `Confirm` / `Dismiss` actions. The data layer already supports `confidence` and `source_run_id`; the UI just needs to use them. Without this distinction, auto-discovery quickly turns the targets list into noise.
    - **Generalize per-tool output target extraction.** The classifier hardcodes nmap's regex. Add similar declarative extractors for `gobuster vhost`, `nuclei -jsonl` (host field), `httpx`/`pd-httpx`, and `ffuf` JSON output. These could live next to `_NMAP_REPORT_TARGET_RE` as a registry, or — cleaner — as part of the `commands.yaml` interactive/output block so adding a new tool is a registry change.
    - **Parse input files captured as workspace artifacts.** When a run consumes `-iL targets.txt`, `_workspace_artifacts_from_validation` already captures the file as a `kind="input"` artifact. Read those captured input files at run-completion time, run each non-comment line through `_target_payload_from_candidate`, and surface the parses as **candidate targets** — a lightweight intermediate state separate from `project_targets` that the UI lists as "12 candidate targets discovered in `targets.txt` for this project — Confirm all / Pick / Dismiss". A gentler version: don't auto-promote, just store the parsed list as artifact metadata so the project explorer can show "this run consumed targets.txt: 12 hosts, 3 CIDRs."
    - **Bound the substring fallback with word boundaries.** The current `target_value in raw_line` matches `"80"` inside `"8080"` (same bug class as workflow promotion's substring substitution). Switch to `re.search(rf"\b{re.escape(target_value)}\b", raw_line)`. Skip CIDR targets entirely in the substring path since they don't appear literally in per-host output.
    - **Batch backfill on demand.** For runs that completed before this lands, add an `Re-attribute findings` action on a project (or a one-shot `project link last --reattribute`) that walks each linked run's findings, re-applies the new attribution rules, and updates `findings.target_id`. Useful when the user adds more project targets and wants prior runs to catch up.
    - **Add explicit regression fixtures.** Cover nmap multi-host output from `-iL`, nmap `host (ip)` reports where either the host or IP exists as a project target, URL/port normalization, IP-in-CIDR matching, no partial-octet/substring false positives, and the fallback path for tools whose finding line contains the target directly.
  - **Trade-offs to think about**
    - **Auto-discovery noise.** A `nmap -iL big-list.txt` against 250 hosts could create 250 project targets, most of which the user does not care about. Mitigations: confidence threshold (only auto-create from `findings`-tagged lines, not from every report header), per-run cap, or land them in a "candidate targets" staging area rather than `project_targets`.
    - **Auto-discovery vs. existing CIDR targets.** If the user has `10.0.0.0/24` as a CIDR target and the scan finds `10.0.0.5`, the IP should attach to the CIDR target rather than create a new IP target. The IP-in-CIDR check needs to run *before* the auto-create path fires.
    - **Alias collisions.** A hostname can resolve to an IP that also belongs to a broader CIDR target. Prefer the most specific user-declared target first (exact host/IP, then URL/domain, then CIDR), and only auto-create when no declared target wins.
    - **Workflow promotion shares this logic.** `build_project_workflow_payload` does its own substring replace with the same blind spots. Once the classifier-aware attribution and per-tool extractors land, workflow promotion can offer "found these targets in the run output — pick which one becomes `{{target}}`" instead of guessing from the command line.
    - **Input-file size and content.** Reading user-supplied content needs to respect the existing workspace size caps, ignore blank lines and comments (`#`-prefixed), and strip ports/paths before target classification.
    - **Re-attribution cost.** Walking N findings to rewrite `target_id` should be batched and bounded; surface a count of updated rows in the UI confirmation.
  - **Smallest viable first step:** ship the classifier-as-primary-source change plus the IP-in-CIDR check (idea 1). That alone makes `-iL targets.txt` work for nmap with no new schema, no auto-discovery surface, and no migration — the metadata has been quietly riding the wire all along; `record_run_findings` just needs to read it.

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
