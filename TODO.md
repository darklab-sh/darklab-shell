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

- **Project Workspace code review follow-ups**
  - **Keep terminal documentation aligned**
    - Keep terminal `project` help aligned with actual shell-supported operations. Current shell commands intentionally stop at project CRUD/link/target operations.
- **Mobile Projects modal implementation plan**
  - **Goal**
    - Build a mobile-friendly Projects experience without changing the current desktop modal.
    - Use a separate mobile DOM root inside the existing Projects overlay, selected at open time when `body.mobile-terminal-mode` is set.
    - Share project data, selectors, `apiFetch`, `DarklabEntityMetadata`, `bindPressable`, `bindDisclosure`, `bindMobileSheet`, and app primitives with the desktop implementation, but do not reuse the desktop two-column layout markup.
    - Remove the existing two-pane mobile fallback rules in `app/static/css/mobile.css:623-653` when the new flow ships.
    - Anchor the visual reference to the Files modal/editor/viewer and existing mobile sheets: same list-to-detail flow, header behavior, sheet handle, buttons, inputs, row treatments, and dismiss mechanics.
  - **Phase 1: Mobile root and project list**
    - Add the mobile Projects root inside the existing Projects overlay without duplicating desktop modal IDs; use mobile-specific IDs, generated elements, or data hooks.
    - Render the list as a full-height mobile sheet using the existing `.sheet-grab.gesture-handle` / `bindMobileSheet` behavior.
    - Provide a top header/list action for New Project that opens a create sheet instead of keeping a persistent inline create input in the list.
    - Create sheet contains one project-name input matching the desktop form, with the same 120-character cap and submit behavior.
    - Pin the active project first, then show current projects using the same desktop sidebar ordering (`_orderedProjectRows(...)`), with archived projects collapsed by default.
    - Project rows show name, active/archived state, compact count chips, and up to 3 label chips plus a `+N` overflow chip; the full label list appears after drill-in.
    - Count chips are independent tap targets that stop row propagation and drill into the matching tab.
    - Tapping the rest of the row opens the project using the normal initial-tab rule.
    - Row trailing affordances use stable ordering: `⋮` overflow first, then a non-interactive `›` chevron.
  - **Phase 2: Project detail shell and tab navigation**
    - Build a drill-in detail screen with a fixed top bar containing `‹ Back`, project name, active/status indicator, and project overflow menu.
    - Lay the top bar out as a sibling wrapper rather than stacking content inside an `.export-header`-style sticky container, so the unscoped sticky-header rule at `app/static/css/mobile.css:84` does not collapse the title row on iOS Safari.
    - Add a sticky tab row for Details, Runs, Findings, Artifacts, and Packages; hide Artifacts entirely when Files are disabled.
    - Clamp tab counts to `999+`; never strip counts to fit narrow viewports, and shorten labels before dropping count context in extreme cases.
    - Set mobile tab `min-height` to 44px, add left/right edge fade gradients for horizontal scroll, and auto-scroll the active tab into view with direct `scrollLeft` assignment instead of `scrollIntoView({behavior:'smooth'})`.
    - Initial tab behavior:
      - same project preserves the last tab
      - different project opens Details
      - targeted navigation, such as a count chip, opens the relevant tab
    - Render only the active tab body. Preserve existing module-owned state such as selected tab and finding/artifact group collapsed state; reset scroll position and transient DOM-only state on tab switches.
    - Add existing-style loading panels for in-flight project list/summary loads and retryable inline error panels for fetch failures, including missing/deleted projects.
    - Use the current toast/status path for non-fatal updates such as create, edit, archive, delete, link, and package actions.
  - **Phase 3: Mobile tab content**
    - Details tab:
      - show summary/status, labels, notes, and targets
      - use a section-level Add Target action
      - move target-row actions into overflow menus
    - Runs tab:
      - row tap performs the primary run action
      - metadata edit, restore, and remove live in overflow menus
      - Link last run appears as a top action or empty-state CTA
    - Findings tab:
      - keep grouped-by-run collapsible sections
      - row tap restores/highlights source output and auto-dismisses the sheet so the user lands on the terminal
      - review state and metadata editing live in overflow menus
      - empty states split by cause: no linked runs offers Link last run or a muted "open Runs to link a run" hint; linked runs with no findings show "No findings captured for linked runs yet"; active filters show "No findings match selected filters"
    - Artifacts tab:
      - group by run
      - preserve availability/status badges
      - preview, download, and metadata edit live in overflow menus
      - hidden entirely when Files are disabled
    - Packages tab:
      - show package rows with summary counts
      - package actions live in overflow menus
      - Build Package is the empty-state CTA
  - **Phase 4: Action sheets, editors, compare, and packages**
    - Render every mobile row overflow as a mobile action sheet, not as a desktop-style dropdown.
    - Action-sheet items use app primitives, 48px touch rows, destructive tone for Delete, and the same focus/dismiss behavior as other mobile sheets.
    - Project-level overflow actions are Mark active / Unmark, Archive / Unarchive, Delete, and Edit metadata.
    - Edit metadata invokes the shared metadata editor with the project entity object, for example `openEntityMetadataEditor('project', project, { projectId: project.id, onSaved: ... })`.
    - Target editor, entity metadata editor, and package manifest preview follow the File Edit / File Viewer mobile sheet pattern: full-width `mobile-sheet-surface`, clear header context, stacked fields/content, visible close/back action, and bottom-aligned primary actions.
    - The visual split is intentional: editing/reading surfaces are full-width Files-style sheets because they contain forms or dense content, while one-tap destructive confirmations stay compact through `showConfirm`.
    - Destructive actions reuse the existing `showConfirm` compact confirmation overlay; do not add mobile-specific confirmation UI.
    - Compare runs becomes a full-screen 3-step stepper: Left run -> mode -> Right run/label/baseline, with sticky Back/Next/Run footer and `baseline_label` parity with desktop.
    - Package wizard renders as a full-screen sheet with sticky step header, scrollable body, and sticky Back/Next/Create footer.
  - **Phase 5: Mobile mechanics, accessibility, and browser behavior**
    - Reuse existing `bindMobileSheet` behavior and visible `.sheet-grab.gesture-handle` format for every Projects mobile sheet, including drag-to-close, tap-outside-to-close, and tap/keyboard activation on the handle.
    - Nested sheets such as project detail and package wizard still expose header `‹ Back` as the primary in-flow navigation affordance.
    - Hide legacy `✕` buttons on mobile sheets; do not introduce new per-sheet close buttons.
    - Defer `history.pushState` / OS Back integration until after the base mobile Projects flow is stable. Until then, only in-app Back is guaranteed to step between mobile Projects levels; OS/browser Back follows existing app overlay/page behavior and should not be treated as nested Projects navigation in first-pass tests.
    - When a nested sheet is shown, move focus into the top layer before setting the parent `inert` and `aria-hidden="true"`; restore focus when popping back.
    - Apply `isolation: isolate` to every mobile sheet surface to prevent high-DPR paint bleed.
    - Pair `overscroll-behavior: contain` on inner scrollers with the existing touchmove fallback pattern where needed to suppress pull-to-refresh.
    - Place `safe-area-inset-bottom` padding on scroll containers, not sheet shells.
    - For form-bearing sheets, reposition sticky action rows above the virtual keyboard via `visualViewport.resize`, scroll focused fields into view on `focus`, and allow `min-height` overrides while focused so iOS Safari `dvh` shrinkage does not clip content.
    - Meet touch minimums: 44px tab strip, 44x44 row chevrons/overflow hit zones, and 48px action-sheet items.
  - **Phase 6: Design audit and test coverage**
    - Before implementation, audit existing mobile sheets/modals/shell surfaces and match their colors, borders, spacing, typography, button sizing, close actions, toggles, dropdowns, inputs, focus states, scroll behavior, and empty states.
    - Use Files modal/editor/viewer as the closest structural analogue, then compare with mobile menu sheet, Workflows sheet, FAQ/options/theme/shortcuts overlays, confirmation dialogs, PTY modal constraints, and shared app-select menus.
    - Add mobile-specific browser coverage for:
      - project list to detail navigation and internal Back behavior
      - count-chip drill-in targets with row-tap propagation stopped
      - loading and retryable error states for project list and project summary fetches
      - tab switching without layout jumps and active-tab auto-scroll on narrow viewports
      - overflow actions for project rows, run rows, target rows, findings, artifacts, and packages
      - first-pass browser/OS Back behavior as existing app-level overlay/page behavior, not nested Projects navigation
      - Files-disabled behavior with the Artifacts tab hidden
      - package wizard sticky actions on narrow viewports, including the `visualViewport` keyboard-adjust path
      - focus trap and dismissible behavior for nested sheets, including `inert` / `aria-hidden` propagation to parents
      - Compare runs stepper round-trip including `baseline_label`
      - Findings tap-to-restore auto-dismiss landing on the terminal
  - **Future-state mobile polish**
    - Add OS Back / browser Back support with `history.pushState` after the base sheet navigation is stable.
    - Add a project search/filter input above the mobile list once project counts justify it.
    - Consider swipe gestures for target and finding rows only after overflow-menu interactions are shipped and tested.
- **Future Project Workspace enhancements**
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
  - **Workspace-disabled behavior**
    - Add focused Playwright coverage with Files disabled for project summary artifact messaging, package wizard defaults, and transcript-only package creation/download. Backend and browser-unit coverage now cover the route/payload behavior; the remaining risk is real-modal wiring in a live browser.
    - Consider returning an explicit Files-disabled response for direct `workspace_file` metadata API calls. The Files UI is hidden when workspaces are disabled, but direct generic metadata calls can still look like ordinary missing-entity responses.
  - **Findings and comparison**
    - Extend the Findings tab filters beyond target/run/review state to command root, severity, scope, labels, and note state.
    - Add multi-select plus bulk review actions for high-volume finding review.
    - Prefetch finding counts and severity distribution so tab labels can show useful state such as unreviewed/high counts without opening the tab.
    - Extend the current Projects modal Compare Runs control with a row action for selecting a baseline and a diff view for changed severity, changed exit code, and richer artifact changes.
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
