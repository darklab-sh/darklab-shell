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
  - **Future-state mobile polish**
    - Add OS Back / browser Back support with `history.pushState` after the base sheet navigation is stable.
    - Add a project search/filter input above the mobile list once project counts justify it.
    - Consider swipe gestures for target and finding rows only after overflow-menu interactions are shipped and tested.
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

- **Run comparison split-view redesign**
  - Replace the current "changes only" comparison overlay with a hunk-based split-pane diff so users can see *where* changes occurred in each transcript and *what surrounds them* without restoring runs into tabs to recover context. The work is phased so v1 is a self-contained backend + UI redesign and v2 layers navigation, anchoring, and view modes on top of the same hunk model.
  - **Diff scope: transcript lines only.** The hunk-based `SequenceMatcher` diff applies only to run output transcripts, where order matters and adjacent context is meaningful. Finding and artifact comparison keeps the existing normalized-key multiset approach (`_compare_items` in `app/project_workspace.py:3523-3544` and `_compare_object_items` in `app/blueprints/history.py`) because findings and artifacts are identified by content key, not by their position in the transcript. Preserve the newer project-style normalized finding key behavior for project-scoped comparison: normalized `raw_line`, then normalized `title`, with fingerprint/id fallback only when no textual finding identity is available. Artifact keys keep the current flow-specific semantics (`content_sha256 || workspace_path || id` for history comparisons, `workspace_path` for project-scoped comparisons). Re-ordering a list of findings should never register as "all findings changed." Concretely: `_bounded_multiset_line_diff` and `_pair_similar_changed_lines` go away (replaced by `_hunk_line_diff`); `_compare_items` and `_compare_object_items` stay untouched, and the response's `objects: {findings, artifacts}` block keeps its current shape and ordering semantics. The split between "ordered line diff" and "unordered object compare" is the scoping rule the rest of this plan operates under.
  - **Consolidate to a single compare path.** Today there are two divergent routes: `/history/compare` does the full picture (output line diff, findings, artifacts, exit status, duration deltas) and `/projects/<id>/compare` does only findings + artifacts. The redesign collapses them to **one canonical route — `/history/compare`** — so the project flow and the history drawer flow render through the same UI and the same backend code path. Concretely:
    - `/history/compare` gains optional `project_id=<id>` and `baseline_label=<label>` query params. When `project_id` is present, the route scopes its session/auth checks to that project and re-uses the existing project finding/artifact resolution helpers (`_run_finding_compare_items` and `_run_artifact_compare_items` are already shared today, so this is a query-param wiring change, not new compare logic). The output diff, exit/duration deltas, and the new `hunks`/`totals`/`limits` blocks are returned regardless of how the comparison was initiated, since project-flow users want the same context as history-flow users.
    - `/projects/<id>/compare` is removed in v1 (no deprecation window — it is browser-only and trusted, with no third-party consumers per the existing TODO note about partial PATCH routes). `compare_project_runs()` in `app/project_workspace.py` shrinks to a thin helper that the unified route calls when `project_id` is present, and `app/blueprints/projects.py:520-533` deletes the route handler.
    - Frontend convergence: `_renderProjectRunCompareControls` (`shell_chrome.js:3245-3304`) calls the same `fetchAndRenderHistoryComparison(leftId, rightId, options)` entry point used by the history drawer, passing `options.url = '/history/compare?...&project_id=…&baseline_label=…'`. The compare overlay (`#history-compare-overlay`) is the single rendered surface for both flows. The "history-" naming on the overlay/CSS classes stays — renaming `history-compare-*` → `compare-*` is out of scope and would touch every CSS rule, JS helper, and test fixture for no behavior gain.
    - The lazy equal-line endpoint follows the same rule: only `/history/compare/lines` exists, with optional `project_id` for parity. There is no `/projects/<id>/compare/lines`.
  - **v1 — hunk-based backend, split-pane diff, folded context, counts banner**
    - **Display caps and lazy-load strategy.** Existing input caps stay (20,000 non-chrome lines / 3 MiB UTF-8 per side, 4,000-char per-line pairing guardrail, 5,000 findings + 5,000 artifacts per side). The split-pane redesign adds three new display caps tuned so the modal stays comfortable up to ~3,000–4,000 rendered DOM rows on mid-range hardware:
      - `COMPARE_MAX_CHANGED_LINES = 2000` — single budget across `replace`/`insert`/`delete` hunks (replaces the prior 500/section cap); `equal` lines never count against it. Sized so a maximally-changed 20K-line input still surfaces 10% of changes before truncation, which is enough to draw a useful conclusion before the omission notice.
      - `COMPARE_MAX_HUNKS = 3000` — caps the count of distinct change blocks so noisy scanner outputs (`nuclei`, `ffuf`, `masscan`) cannot create thousands of single-line `replace` containers in the DOM. Surplus hunks roll up into a single trailing `… N more change hunks omitted` placeholder rendered by the frontend.
      - `COMPARE_INLINE_EQUAL_CONTEXT = 3` — fixed ±3 inline equal-line context window above and below each change hunk. Equal runs shorter than `2 * COMPARE_INLINE_EQUAL_CONTEXT` (i.e., < 6 lines) inline fully; longer runs collapse to a fold and lazy-load on expand.
      - `COMPARE_LINE_DISPLAY_TRUNCATE = 4000` — soft truncation matching the existing pairing guardrail. Lines beyond 4,000 chars render with a `… +N chars` chip and click-to-expand affordance across `equal`/`replace`/`insert`/`delete` so behavior is uniform.
      - `COMPARE_LAZY_EQUAL_PAGE_LIMIT = 5000` — per-request cap on the lazy equal-line endpoint so a full-expand on a giant equal run cannot blow the browser.
      - `COMPARE_LAZY_EQUAL_BYTE_LIMIT = 512000` — per-request byte cap on the lazy equal-line endpoint, applied alongside `COMPARE_LAZY_EQUAL_PAGE_LIMIT` so long-line equal regions cannot return oversized expansion payloads.
      - `COMPARE_REPLACE_PAIR_MIN_RATIO = 0.5` — `SequenceMatcher.ratio()` floor for treating a left/right line pair as the "same line, modified" inside a `replace` hunk; pairs below the floor fall through to the unpaired buckets and render as delete-then-insert rows within the same hunk (see "Replace-hunk pairing" below).
      - All seven constants live next to `COMPARE_MAX_CHANGED_LINES` (`history.py:42`) and are exposed in the response under a `limits` key for parity with the existing `truncated.item_limit` pattern.
    - **Backend changes** (`app/blueprints/history.py`, `app/project_workspace.py`, `app/blueprints/projects.py`)
      - Add `_hunk_line_diff(left_entries, right_entries, *, max_changed_lines=COMPARE_MAX_CHANGED_LINES, max_hunks=COMPARE_MAX_HUNKS, inline_context=COMPARE_INLINE_EQUAL_CONTEXT)` in `app/blueprints/history.py` that walks `difflib.SequenceMatcher(None, left_texts, right_texts, autojunk=False).get_opcodes()` and emits ordered hunks of shape `{op: "equal"|"replace"|"insert"|"delete", left: {start, end}, right: {start, end}}`. Change hunks (`replace`/`insert`/`delete`) embed their `lines: [{text, line_index}]` directly. `equal` hunks omit `lines` from the initial payload (lazy-loaded; see lazy endpoint below) but always include a sliced `context: {leading: [...], trailing: [...]}` field carrying up to `inline_context` lines from each end so the immediate ±3 window renders without a fetch. Short equal runs (length < `2 * inline_context`) inline fully under `lines` since there is no fold to lazy-load against.
      - **Replace-hunk pairing** (handles uneven left/right lengths). `difflib` regularly emits `replace` opcodes where `j - i ≠ l - k` (e.g., 5 left lines replaced by 3 right lines). The hunk model represents this as one `replace` block carrying both paired and unpaired rows so the surface stays a single user-evident "this region was modified" event:
        - Hunk shape for `replace`: `{op: "replace", left: {start, end, lines: [...]}, right: {start, end, lines: [...]}, changed_pairs: [{left_index, right_index, segments}], left_unpaired: [left_index, ...], right_unpaired: [right_index, ...]}`. `left_index` / `right_index` are absolute indices into `left.lines` / `right.lines` so the frontend can render rows in the recorded order without a second sort.
        - Pairing pass (replaces the current `_pair_similar_changed_lines`): for each left line in original order, walk a bounded right-side candidate window of unpaired lines (cap at the existing 32-candidate guardrail used by the current pairing code), compute `SequenceMatcher(None, left_text, right_text).ratio()`, take the highest-ratio match where `ratio ≥ COMPARE_REPLACE_PAIR_MIN_RATIO`. Skip any line longer than `COMPARE_LINE_DISPLAY_TRUNCATE` (4,000 chars) on either side — those bypass pairing and land directly in the unpaired buckets.
        - 1×1 fast path: when `len(left) == 1 and len(right) == 1`, always pair regardless of ratio. The user-evident structure ("this one line changed to that one line") matches user expectation more than the threshold's purity.
        - All-unpaired case: when no pair meets the threshold (e.g., a block of structurally unrelated lines was inserted next to deleted noise), `changed_pairs` is empty and every left/right line goes to its respective unpaired bucket. The hunk still renders as one `replace` block — the frontend visualizes it as a delete-row sequence followed by an insert-row sequence inside one hunk container.
        - Pairing still respects the existing 4,000-char per-line guardrail; `_changed_line_segments` runs only on paired entries.
      - Apply `max_changed_lines` as a single budget across `replace`/`insert`/`delete` hunks; `equal` lines never count against it. Inside a `replace` hunk a paired row counts as **2 budget units** (one render row per pane), and each unpaired row counts as **1 unit**. When the cap is reached mid-hunk, drop unpaired tails first (cheaper to truncate cleanly), then pair tails — emit `lines_omitted` on the hunk capturing the dropped row count from each side. Subsequent change hunks drop entirely into `hunks_omitted` on the response. Apply `max_hunks` as a separate cap on the count of change hunks before any line is emitted from a hunk; once exceeded, drop the surplus into `hunks_omitted` without rendering line text.
      - Wire the consolidation: `compare_history_runs` (`history.py:1460`) accepts optional `project_id` / `baseline_label` query params and, when present, applies the existing project finding/artifact filters before calling `_hunk_line_diff` on the run pair. Replace the call to `_bounded_multiset_line_diff` at `history.py:1488` with `_hunk_line_diff`. Reduce `compare_project_runs` (`project_workspace.py:3563`) to a small helper that the unified route calls for project-scoped filter resolution, and delete the `/projects/<id>/compare` blueprint route at `app/blueprints/projects.py:520-533`. Delete `_bounded_multiset_line_diff` and `_pair_similar_changed_lines` once no callers remain.
      - Add a single new `GET /history/compare/lines` endpoint that returns a bounded slice of one side's persisted output for lazy fold expansion: `?left=…&right=…&side=a|b&start=…&end=…&project_id=<optional>`. Re-uses `_compare_entries_for_diff` for entry resolution and `get_session_id()` for auth scoping; the optional `project_id` mirrors the parent route's scoping rules. `start` / `end` are indexes into the filtered compare-entry sequence after chrome-line removal, matching the hunk model's index space rather than raw persisted-output offsets. Caps the slice at `COMPARE_LAZY_EQUAL_PAGE_LIMIT` lines or `COMPARE_LAZY_EQUAL_BYTE_LIMIT` bytes per request, whichever comes first, and refuses ranges outside the source run's filtered compare entries. Response shape: `{lines: [{text, line_index}], start, end, truncated: bool, page_limit, byte_limit}`. The frontend re-issues the call to walk past `truncated: true`.
      - Update the unified `/history/compare` response shape:
        - Replace `sections.{changed, added, removed, *_omitted, max_changed_lines}` with `hunks: [...]` (ordered) and `totals: {left_total_lines, right_total_lines, equal_line_count, changed_line_count, added_line_count, removed_line_count}`.
        - Move per-budget truncation flags into `truncated: {left, right, hunks_omitted, lines_omitted, item_limit, findings: {...}, artifacts: {...}}`.
        - Add `limits: {max_changed_lines, max_hunks, inline_equal_context, line_display_truncate, lazy_equal_page_limit, lazy_equal_byte_limit}` so the frontend never hard-codes the numbers.
        - Keep `left`, `right`, `deltas`, `objects` keys identical to today so the run cards, metrics row, and findings/artifact sections need no shape changes. Project-scoped responses populate the same keys (output diff, exit/duration deltas, findings/artifacts) so the rendered UI is identical regardless of entry point.
      - Update the `COMPARE_MAX_CHANGED_LINES` docstring at `history.py:42` so it explicitly states the cap covers changed lines only, not equal context, and reference the sibling caps.
      - Confirm `_run_finding_compare_items` already returns each finding's `line_number`; if a side's index is missing, derive it from the run's persisted output once during comparison so v2 anchoring is unblocked without a second pass. If derivation is non-trivial, defer to v2 — v1 does not depend on it.
    - **Frontend redesign** (`app/static/js/history.js`, `app/static/js/shell_chrome.js`, `app/static/css/components.css`)
      - Converge the project flow onto the history-flow renderer. `_renderProjectRunCompareControls` (`shell_chrome.js:3245-3304`) keeps its dropdown/baseline-label trigger UI but calls `fetchAndRenderHistoryComparison(leftId, rightId, {url: '/history/compare?...&project_id=…&baseline_label=…'})` instead of a project-specific endpoint. The history-drawer flow keeps its existing `fetchAndRenderHistoryComparison(leftId, rightId)` call. Both flows render through the same `_renderHistoryComparison` and the same `#history-compare-overlay` surface — there is no project-specific compare DOM after this change.
      - Rewrite `_renderHistoryComparison` (`history.js:2424`) around the new hunk model. Keep `_historyCompareRunCard`, `_compareMetricCell`, and `_renderHistoryCompareObjectSection` unchanged so the run-card grid, metrics row, and findings/artifacts sections do not move. Only the lines region is replaced.
      - Add `_renderHistoryCompareSplitPane(hunks, totals, truncated)` that emits a two-column flex container with left (`data-side="a"`) and right (`data-side="b"`) tracks. Each track is a `<div class="history-compare-pane nice-scroll">` so the scrollbar contract from `ARCHITECTURE.md § Scrollbar Styling Contract` holds.
      - Render each hunk as a paired row block so left/right stay vertically aligned even when one side is empty:
        - `equal` hunks: render `lines` inline when the backend included them (short equal runs). Longer equal runs arrive without `lines` but with a `context: {leading, trailing}` window — render the leading slice, then a fold placeholder `▸ N unchanged lines` for the gap, then the trailing slice. The placeholder is a `.btn-ghost` pressable wired through `bindDisclosure` from `ui_disclosure.js` (per the disclosure-affordance rule that `▸/▾` indicates expand-in-place state). Activating the placeholder fetches the missing range from `GET /history/compare/lines?…&side=a|b&start=…&end=…` (forwarding the parent overlay's `project_id` query param when set) for both sides, walking through `truncated: true` pages until `lazy_equal_page_limit` no longer caps the response. Cache fetched line arrays on the hunk node so a `▾ Collapse` reset / re-expand cycle does not re-fetch.
        - `replace` hunks: render in three ordered groups inside the same hunk container so a structurally uneven replace stays one visual event:
          1. `changed_pairs` first, sorted by `left_index`. Each pair is a paired row using `_appendHistoryCompareSegments` for char-level highlights — Side A `.history-compare-line-removed`, Side B `.history-compare-line-added`. Reuse the existing `--red`/`--green` semantic tokens — no new color tokens.
          2. `left_unpaired` rows next, in `left_index` order. Render each as a left-only row with a sibling `.history-compare-row-spacer` on the right (mirrors the `delete` hunk render).
          3. `right_unpaired` rows last, in `right_index` order. Render each as a right-only row with a left-side spacer (mirrors the `insert` hunk render).
          - When `changed_pairs` is empty (all-unpaired case from the backend), the hunk renders as a delete sequence followed by an insert sequence inside one container, still bordered/grouped as a single replace block.
          - When the hunk carries `lines_omitted`, append a single `.history-compare-truncation` row inside the hunk reading `… N rows omitted from this block` so users see the truncation locality rather than learning about it only from the modal-level banner.
        - `insert` hunks: render only on the right pane; the left pane gets a sibling `.history-compare-row-spacer` row with `aria-hidden="true"` and a muted background so vertical alignment between panes survives. `delete` mirrors this on the left.
      - Per-line render truncation: when a line's text length exceeds `limits.line_display_truncate`, render the first `limits.line_display_truncate` chars followed by a `.chip .chip-action` reading `… +N chars` that expands the row in place to its full text. Uniform across `equal`/`replace`/`insert`/`delete`. Pairing-derived `segments` for changed pairs are already capped by the 4,000-char pairing guardrail upstream so no extra logic is needed inside `_appendHistoryCompareSegments`.
      - Surplus-hunks placeholder: when `truncated.hunks_omitted > 0`, render a single trailing row spanning both panes reading `… N more change hunks omitted` styled with `.history-compare-truncation`. No fetch — these were dropped at the budget cut.
      - Add a sync-scroll binding: a single `scroll` listener on each pane mirrors `scrollTop` to its sibling, debounced via `requestAnimationFrame` and guarded with a `data-scroll-syncing` flag to avoid feedback loops. Skip the listener entirely when `useMobileTerminalViewportMode()` is true so mobile uses the unified-mode fallback.
      - Add a unified-mode fallback for `@media (max-width: 760px)` and mobile: collapse `.history-compare-split` from `flex-direction: row` to `column`. `replace` hunks render as a top-bottom A/B pair; `insert`/`delete` render as single-side rows with a `+`/`−` gutter mark using the existing line-added/line-removed accents. Same hunk model drives both layouts — no parallel render path.
      - Add `_renderHistoryCompareCountsBanner(totals, truncated)` placed above the split pane and below the metrics row. Render a flex strip of `.badge` pills using existing tone classes — `.badge` for the total-lines pill, `.badge-tone-green` for added, `.badge-tone-red` for removed, `.badge-tone-amber` for changed, `.badge-tone-muted` for unchanged. Append a `.history-compare-truncation` note when `truncated.hunks_omitted` or `truncated.lines_omitted` is non-zero.
      - Update the empty-state branch at `history.js:2586-2594` so it triggers when `totals.changed_line_count + totals.added_line_count + totals.removed_line_count === 0` and no findings/artifacts changed; the message stays "No changed output, findings, or artifacts."
      - Update the `Copy summary` action at `history.js:2543` to read counts from `totals` and emit `Hunks: N changed · M added · K removed · J unchanged context` so the clipboard summary reflects the new model.
      - CSS additions in `app/static/css/components.css` (extend the existing `.history-compare-*` block at lines 1265+):
        - `.history-compare-split` (flex container), `.history-compare-pane` (composes `.nice-scroll`), `.history-compare-row` (paired-row alignment), `.history-compare-row-spacer` (muted background, no text), `.history-compare-fold` (collapsed equal-region pill), `.history-compare-counts` (banner strip).
        - Reuse the existing `.history-compare-line-added` / `.history-compare-line-removed` / `.history-compare-line-delta` accents — no new color tokens.
        - Mobile rules under `@media (max-width: 760px)` swap `.history-compare-split` to column direction and toggle a `.is-unified` class on the overlay so layout-only differences do not require a separate render path.
      - Run-card grid stays inside the modal header band as today — no structural changes to `_ensureHistoryCompareOverlay()` or `.history-compare-modal`.
    - **Tests**
      - Backend: extend the comparison test file under `tests/py/` (or add `tests/py/test_history_compare_hunks.py` if no focused file exists) with cases for:
        - pure-insert hunk, pure-delete hunk, equal-only response.
        - **Consolidation parity**: the same two run ids return identical `hunks` / `totals` / `deltas` / `objects` whether the route is called with no `project_id` (history-drawer flow) or with the project_id of a project that contains both runs (project flow). Project-scoped calls honor `baseline_label` when resolving the right-side run; object comparison then runs against the resolved pair.
        - **Auth/scoping**: `/history/compare?project_id=<id>` rejects when the session does not own the project; `/history/compare` (no project_id) rejects when the session does not own one of the runs. Both rejection paths return the existing 403/404 shape so frontend error handling does not branch on entry point.
        - **Removed route**: `GET /projects/<id>/compare` returns 404 (deleted). A regression test in `tests/py/test_routes.py` (or the existing project routes test) asserts the route is gone, so re-introducing it accidentally fails CI.
        - **Object compare stays order-insensitive**: feed two runs with the same set of findings (and artifacts) emitted in different order; assert `objects.findings.added == []`, `objects.findings.removed == []`, and `objects.findings.unchanged_count == N`. Same for artifacts. Guards the scoping rule that `SequenceMatcher` is for line diffs only — re-ordering findings must not regress to "all findings changed."
        - replace hunk with **even sides** (3 vs 3 lines, all paired, char-level segments populated).
        - replace hunk with **left-heavy sides** (5 vs 3 lines, three pairs + two `left_unpaired` rows, verify pair selection picks the highest-ratio matches and unpaired entries point at the lowest-ratio left lines).
        - replace hunk with **right-heavy sides** (3 vs 5 lines, mirror of above).
        - replace hunk with **no pair above threshold** (e.g., totally unrelated lines on each side; assert `changed_pairs == []` and every line falls into the matching unpaired bucket).
        - replace 1×1 fast path: ratio below the threshold but still paired because both sides have exactly one line.
        - replace hunk where one or more lines exceed `COMPARE_LINE_DISPLAY_TRUNCATE` (verify those skip pairing and land directly in unpaired buckets).
        - budget exhaustion: `COMPARE_MAX_CHANGED_LINES` exhausted mid-replace (verify unpaired tails drop first, then pair tails, with `lines_omitted` reflecting both sides; remaining change hunks drop into `hunks_omitted`). Verify the budget accounting (paired = 2 units, unpaired = 1 unit).
        - `COMPARE_MAX_HUNKS` exhausted at the hunk-count layer (verify surplus hunks land in `hunks_omitted` without their lines being emitted).
        - Inline equal context: short equal runs (length < 6) inline fully, long equal runs ship `context.leading` + `context.trailing` of `inline_context` lines and omit `lines`.
        - `limits` block present in the response and matches the module constants.
      - Backend: cover the new `GET /history/compare/lines` endpoint — happy path slice, range outside filtered compare entries (404/400), `COMPARE_LAZY_EQUAL_PAGE_LIMIT` and `COMPARE_LAZY_EQUAL_BYTE_LIMIT` paging behavior with `truncated: true`, session/auth scoping mirroring the parent compare route, and the optional `project_id` query param (project scoping rules apply, matches the parent `/history/compare` consolidation contract).
      - Frontend: add Vitest coverage in `tests/js/unit/history_compare_split.test.js` for:
        - hunk-to-DOM mapping (one assertion per `op`).
        - replace-hunk render order: `changed_pairs` rows first (sorted by `left_index`), then `left_unpaired` rows (right-side spacer rendered, paired with `aria-hidden="true"`), then `right_unpaired` rows (left-side spacer). Cover even-sided, left-heavy, right-heavy, and all-unpaired hunk inputs.
        - replace-hunk per-block truncation row appears when the hunk carries `lines_omitted`.
        - folded-region disclosure toggle through `bindDisclosure` and the lazy fetch path (mock `apiFetch`, assert single fetch on first expand, no fetch on collapse/re-expand thanks to the cached line arrays, multi-page walk when the mock returns `truncated: true`).
        - per-line display truncation: lines beyond `limits.line_display_truncate` render the `… +N chars` chip and expand inline on click.
        - surplus-hunks placeholder rendered when `truncated.hunks_omitted > 0`.
        - sync-scroll listener no-op when one pane lacks overflow, counts-banner badge-tone mapping, unified-mode fallback at narrow widths.
      - E2E: extend `tests/js/e2e/visual_history_fixture.js` to seed two runs with deterministic line offsets, then add a Playwright spec that opens the compare overlay from the **history drawer flow**, verifies both panes scroll in sync, expands a folded equal region (asserting the network request), expands a long-line truncation chip, and asserts the counts banner text. Add a sibling spec that opens the same comparison from the **project compare control** (`_renderProjectRunCompareControls`) and asserts the rendered DOM is structurally identical to the history-drawer entry — same `#history-compare-overlay`, same `hunks`, same counts banner. This guards the consolidation contract.
      - Update `tests/js/unit/button_primitives_allowlist.test.js` only if a new pressable surface lands without an existing primitive class — the new fold/expand controls inherit `.btn-ghost` and the long-line expander inherits `.chip-action`, so no allowlist change is expected.
    - **Docs**
      - Update the `Findings and comparison` sub-list under `Future Project Workspace enhancements` to drop the "Extend the current Projects modal Compare Runs control" bullet once v1 ships, since the redesign supersedes it.
      - Add a `CHANGELOG.md` entry under the current branch's section describing the redesign and the new display caps.
      - Update `ARCHITECTURE.md § HTTP Route Inventory`: add `/history/compare/lines` to `§ History And Share Routes`, refresh the `/history/compare` entry with the new `hunks` / `totals` / `limits` keys + the optional `project_id` / `baseline_label` query params, and remove `/projects/<id>/compare` from `§ Project Routes` (consolidation note in the section preamble pointing at `/history/compare?project_id=…`).
      - Document the six new constants (`COMPARE_MAX_CHANGED_LINES`, `COMPARE_MAX_HUNKS`, `COMPARE_INLINE_EQUAL_CONTEXT`, `COMPARE_LINE_DISPLAY_TRUNCATE`, `COMPARE_LAZY_EQUAL_PAGE_LIMIT`, `COMPARE_LAZY_EQUAL_BYTE_LIMIT`) wherever the existing input caps (20K lines / 3 MiB / 4,000-char pairing / 5,000 findings / 5,000 artifacts per side) are listed so users see the full picture in one place.
      - Refresh test counts in `tests/README.md`, `CONTRIBUTING.md`, and `ARCHITECTURE.md` once new tests land (per the standing rule that test counts stay in sync across the documented locations).
  - **v2 — minimap rail, finding/artifact anchors, view-mode toggle**
    - **Backend changes** (`app/blueprints/history.py`, `app/project_workspace.py`)
      - Add `density_buckets: [{equal, added, removed, changed}, ...]` to the comparison response. Fixed length via a backend constant `COMPARE_MINIMAP_BUCKETS = 256` so payload shape stays stable across runs of any size; the frontend interpolates to actual rail height. Computed in a single pass over the same `hunks` walk so no extra diff cost.
      - Populate `output_line_index` on each finding/artifact for both sides where derivable. `_run_finding_compare_items` joins `findings.line_number` to the run's persisted line offsets; if the source output is no longer available, the field is omitted and the frontend falls back to non-anchored display.
      - No new endpoints; the consolidated `/history/compare` route gains the new fields and they flow through both entry points (history-drawer and project compare control) automatically.
    - **Frontend additions** (`app/static/js/history.js`, `app/static/css/components.css`, `app/static/js/state.js`)
      - Add `_renderHistoryCompareMinimap(buckets, totals)` rendered as a thin `<div class="history-compare-minimap">` rail anchored to the right edge of the split-pane container. Each bucket is a 2px-tall `<div>` whose background-color is the dominant op tone — `--green` (added), `--red` (removed), `--amber` (changed), low-opacity `--muted` (equal). Click on a bucket scrolls both panes to the corresponding line range through the existing sync-scroll binding. Hidden under `@media (max-width: 760px)` so unified mobile keeps the simpler layout.
      - Wire finding/artifact anchors: on `_renderHistoryCompareObjectSection` row click, find the matching pane row by `data-line-index` and scroll it into view in both panes; pulse a `.history-compare-line-pulse` class (`animation: pulse 800ms ease-out`) for visual confirmation. Emit `emitUiEvent('app:compare-anchor-scroll', {side, line_index})` so future modules can subscribe through the existing cross-module event bus.
      - Render a finding marker in each pane's left gutter at any line carrying an `output_line_index` match. Marker uses `.history-compare-finding-marker` with severity tone (`--red` high/critical, `--amber` medium, `--muted` info). Click on the marker scrolls the linked finding row in the findings section into view.
      - Add a view-mode toggle in the compare-modal header. Implement as a hidden `<select>` enhanced through `enhanceAppSelects()` per the App-native Select Primitive contract so it composes the `.dropdown-surface` / `.dropdown-item-touch` family and inherits keyboard / outside-click / `aria-expanded` behavior automatically. Modes:
        - `Side-by-side` (default at ≥ 760px) — v1 split layout.
        - `Unified` (default below 760px) — v1 unified layout.
        - `Changes only` — collapses every `equal` hunk to a single zero-context fold and skips equal lines entirely. Equivalent to the pre-v1 view but riding on the same hunk model.
        - `Findings only` — hides the split pane entirely, leaving the run cards, metrics row, counts banner, and findings/artifacts sections.
      - Persist the chosen mode in `state.js` as `comparisonViewMode` and add it to the Options modal so the choice survives reload through the same per-session-token preference path used by the rest of the shell. Mobile-first defaults still apply on first load.
      - Add a `±N context` chip row above the split pane composing `.chip` + `.chip-action` with options `±3 / ±10 / All`. Selection updates a frontend-only state and re-renders the lines region without re-fetching.
      - All new pressable surfaces route through `bindPressable`/`bindDisclosure`/`enhanceAppSelects` so they pick up the existing button-primitive allowlist, focus-trap, refocus-composer, and outside-click contracts without local wiring.
    - **Tests**
      - Backend: unit coverage for bucket aggregation (constant bucket count regardless of input size, sum of bucket counts equals total line count, off-by-one at the final bucket, finding `output_line_index` populated when persisted offsets are present and omitted when not).
      - Frontend: Vitest coverage for minimap bucket-to-DOM density mapping, finding-row click → pane scroll → pulse class lifecycle, view-mode toggle preference round-trip through `state.js`, `±N context` chip selection re-rendering folds without re-fetching.
      - E2E: extend the v1 Playwright spec with mode-toggle steps (verify each mode's row counts), minimap-click navigation, and finding-row click anchoring across both panes.
      - Update `tests/js/unit/button_primitives_allowlist.test.js` only if a new pressable surface lands outside the allowed primitive families (the `±N context` chips and the view-mode toggle should both inherit existing primitives).
    - **Docs**
      - Update the `Findings and comparison` sub-list to remove items now covered by v2.
      - If `ARCHITECTURE.md § Browser State Model` enumerates persisted preferences, add `comparisonViewMode` and the `±N context` default to that list.
      - `CHANGELOG.md` entry for v2 mirroring the v1 format.
      - Refresh the test-count locations once new tests land.

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
