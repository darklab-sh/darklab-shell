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

- **Global focus-return-and-press-clear helper for UI interactions** — introduce a single modular helper that every chrome affordance (mobile FAQ expand/collapse, desktop rail section toggles for Recent/Workflows, sheets, menus, overlays) can call after activation to (a) clear any lingering press/hover/focus-visible highlight on the invoking control and (b) return keyboard focus to the terminal prompt. Today each surface solves this ad hoc, which is why the mobile FAQ still stays visibly highlighted after press and the desktop rail does not return focus to the prompt without clicking back into the terminal. A shared helper replaces the scattered one-off fixes and resolves the `Interaction state does not reset consistently after chrome actions` known issue below.

---

## Research

- **Surface starred state in the desktop rail's Recent section** — the rail's Recent list lost the starred-first ordering and the star indicator that the older chip strip carried. Research whether the right fix is simply restoring starred-first ordering plus a visible marker, or whether the rail needs a broader information-density pass. Verify the same change does not regress the mobile recents sheet (which already shows star state per row).

- **Rail information density tuning** — reassess how much metadata belongs in the desktop rail's Recent and Workflows entries now that the rail owns more of the shell chrome. Explore whether star state, recency, status, or lightweight badges should be visible without making the rail noisy.

---

## Known Issues

- **Interaction state does not reset consistently after chrome actions** — some UI affordances keep the wrong visual or focus state after activation instead of returning the shell to a clean ready state. Two distinct symptoms show up today: (1) press/click highlight states linger — mobile FAQ entries stay visibly pressed/highlighted after expand/collapse, and all press/click highlight syntaxes should clear immediately on action completion; (2) focus does not return to the prompt — desktop rail section toggles for Recent/Workflows do not restore terminal focus after expand/collapse, so the user has to click back into the terminal to keep typing. Both symptoms should be resolved by the shared modular helper tracked under `Global focus-return-and-press-clear helper for UI interactions` in Open TODOs.

- **Desktop rail Workflows entries styled differently from Recent entries** — in the desktop rail the Workflows section's list items blend into the Workflows header visually, while the Recent section above it uses a clearer, more readable text treatment. The actual workflow entries should match the Recent command entries' text styling so the two rail sections look consistent and the Workflows list is as scannable as the Recent list.

- **Mobile run timer duplicated in header status pill and top of output window** — on mobile, when a command is running there are two live timers visible at the same time: one in the header status pill and one at the top of the output window. The header pill is the canonical location; remove the duplicated timer at the top of the output window so there is a single authoritative run-timer surface on mobile.

- **Shortcuts overlay close button placement is inconsistent** — the keyboard-shortcuts overlay `X` sits beside the modal title instead of being anchored in the expected top-right corner, which makes the close affordance feel misaligned relative to the rest of the shell overlays.

- **Mobile sheet close affordance is redundant or unclear** — mobile sheets currently include an `X` close button even though the sheet pattern already has a grab handle, supports drag-down dismissal, and closes on backdrop tap. Reassess whether the extra `X` is needed at all, or whether it is just adding visual noise and competing close metaphors.

---

## Technical Debt

- **CI/runtime source-of-truth drift** — production, CI, and version-checking logic currently need to stay aligned across multiple files. Consolidate Python base-image/runtime declarations so the production image, CI jobs, and version-check script cannot silently diverge.

- **Duplicated page bootstrap in Jinja templates** — `index.html`, `permalink_base.html`, and `diag.html` now share enough `<head>` and theme/bootstrap wiring that the duplication is real maintenance overhead. Factor the common bootstrap into a lightweight shared base before a fourth page type makes the drift worse.

- **Cross-module UI event flow is still coupled through wrappers and observers** — `shell_chrome.js` and `mobile_chrome.js` currently mirror shared UI state by wrapping globals (`renderHistory`, `renderRailWorkflows`, `closeWorkflows`, `refreshHistoryPanel`, `setTabStatus`), and by using three `MutationObserver`s in `mobile_chrome.js` (`:107` on the status pill `class` attr, `:113` on the run-timer `characterData`, `:699` on the body `class` list) to mirror state changes they have no other way to hear about. Replace those ad hoc integrations with a small UI event bus or equivalent explicit publish/subscribe layer so cross-module synchronization does not depend on monkey-patching exported functions. Relationship to the UI Interaction Helper Refactor Plan: the interaction helpers do not block on this, but without the event bus they will still have to reach into shared state via the same wrapper pattern — the two refactors are independent but both benefit when landed together.

### UI Interaction Helper Refactor Plan

- **Goal** — reduce repeated UI interaction wiring across `app/static/js` so focus restoration, pressed/highlight cleanup, disclosures, and dismissible surfaces behave consistently instead of being re-implemented per control.

- **Prior art to follow** — `bindMobileSheet()` in `app/static/js/mobile_sheet.js` is the working model for "bind one behavior contract across N surfaces" in this codebase. Every helper introduced by the phases below should follow the same shape: one function, takes the target element plus an options bag, asserts its preconditions, owns the full behavior contract from the inside, and is idempotent via a `data-*-bound` guard.

- **Phase dependencies** — Phases 1 (refocus) and 2 (pressable) are tightly coupled and should be **designed together** even if shipped incrementally: without Phase 2's press-clear path, Phase 1's refocus still leaves lingering highlight on `role="button"` elements (the concrete FAQ bug), and without Phase 1's refocus target, Phase 2's pressable has no coherent place to hand focus after activation. Phase 3 (disclosure) composes on top of Phase 2 — a disclosure trigger is a pressable. Phase 4 (dismissible) also composes on top of Phase 2 — close buttons and triggers are pressables. Build Phase 2 thick enough that Phases 3 and 4 don't need their own parallel activation paths.

- **Phase 1: unify post-action focus and cleanup** — ✅ **Done (2026-04-19)**
  - `refocusComposerAfterAction()` in `ui_helpers.js` is now the canonical refocus helper. It gained a `{ defer: true }` option to preserve the `setTimeout(0)` semantics of the retired `refocusTerminalInput()`, and `preventScroll` now defaults to `true` (eliminates scroll-into-view jank on chrome close).
  - Retired: `refocusTerminalInput()` in `app.js`, `refocusTabsTerminalInput()` in `tabs.js`, `focusComposerInputAfterRun()` in `runner.js`, the raw `cmdInput.focus()` fallback in `ui_helpers.js`'s `hideSearchBar`.
  - Migrated ~46 call sites across `controller.js` (20 + 2 keypress-redirect paths), `app.js` (6), `tabs.js` (6 + local wrapper removal), `welcome.js` (5), `runner.js` (3 + local wrapper removal), `autocomplete.js` (2), `shell_chrome.js` (1 rail Recent item click), `history.js` (1 chip click).
  - Test harness updated (`tests/js/unit/app.test.js` export list + the `does not programmatically focus the mobile composer` case). All 475 Vitest, 731 pytest, 169 Playwright tests pass.
  - **Intentionally not migrated** (mobile edit path, opposite semantics): 2 bare `focusAnyComposerInput({ preventScroll: true })` calls inside `performMobileEditAction` in `app.js` (lines 1060 and 1132 post-migration). Those force focus onto the mobile composer, whereas the canonical helper skips on mobile. A future phase will introduce a sibling `refocusMobileEditingInput()` helper for that path.
  - **Pending follow-ups not part of Phase 1** (still open — roll into Phase 2 or a later phase):
    - `history.js` per-row action buttons (star/copy/permalink/delete) still use `setTimeout(() => btn.blur(), 0)` for cleanup (Phase 2 pressable target).
    - Desktop rail Recent / Workflows section toggles (`shell_chrome.js:193–194`) do not currently call any refocus helper. Adding refocus here is blocked on Phase 2's press-clear path — without it, the rail section headers' `role="button"` divs will keep their press highlight even after focus returns to the composer. Phase 2 will address both simultaneously.
    - FAQ expand/collapse controls (`app.js:1836`) — same as above, blocked on Phase 2.

- **Phase 2: add a reusable pressable helper** (build this before the disclosure helper — a disclosure is a pressable that toggles state, and the concrete "press highlight lingers" bug is a pressable-level problem that occurs whether or not the control also toggles a panel)
  - Generalise the consistency approach already used by `bindMobileSheet()` so non-sheet UI controls can share one activation model for click / tap / keyboard behavior.
  - The helper should standardise:
    - pointer/click/keyboard activation
    - immediate clearing of transient pressed/highlight state after activation when the control should not keep focus, including the `role="button"` case (e.g. the FAQ `<div role="button">` at `app.js:1833` never receives DOM focus, so `.blur()` is a no-op — the helper needs a non-blur cleanup path for those)
    - `Enter` / `Space` activation for non-`<button>` elements, replacing the 6 copies of `if (e.key === 'Enter' || e.key === ' ')` across `welcome.js:430, 475, 711`, `mobile_chrome.js:640`, `mobile_sheet.js:120`, `app.js:1841`
    - optional prevention of focus theft from the composer (several `_bindMobileEditBarInteractions` callers today use `pointerdown` + `preventDefault` just to keep the composer focused — this pattern belongs in the helper)
  - Escape hatch for CSS-state residue: most press-highlight cases clear when focus/blur is controlled correctly, but a few surfaces (sticky `:hover` on touch devices, manually toggled `.is-pressed`-style classes, custom `:active` retention) will not respond to `.blur()`. The helper should expose a `data-*` attribute toggle so those surfaces can opt in to an explicit post-activation un-style pass without each call site re-inventing it.
  - Concrete migration targets, in order:
    - the 4 copies of `setTimeout(() => btn.blur(), 0)` in `history.js:780, 788, 795` and `tabs.js:627–630`
    - the `_makeHudBtn` factory in `shell_chrome.js:344` and the parallel `_recentsMakeAction` factory in `mobile_chrome.js:289` (both build chrome buttons but neither clears press state or calls the Phase 1 refocus helper)
    - mobile FAQ items (`app.js:1836`)
    - desktop rail section headers
    - mobile menu sheet rows and recents-sheet action rows
    - welcome card activations (`welcome.js:430, 475, 711`)

- **Phase 3: add a reusable disclosure helper**
  - Create a generic disclosure binder for expandable/collapsible controls so `aria-expanded`, open/closed classes, panel visibility, and focus cleanup do not drift. Composes on top of the Phase 2 pressable so aria wiring is automatic for the trigger.
  - Five hand-rolled disclosures exist today, each getting aria-expanded slightly wrong in a different way:
    - FAQ question toggles (`app.js:1836` — toggles aria on `q` only)
    - desktop rail Recent / Workflows section headers (`shell_chrome.js:193–194` — toggles a `closed` class on the section but never sets `aria-expanded` on the header)
    - mobile timestamps sub-menu (`mobile_chrome.js:177–180`)
    - mobile recents advanced filters toggle (`mobile_chrome.js:560–594`)
    - save-menu dropdowns — three near-identical copies at `tabs.js:621`, `permalink.js:115`, `shell_chrome.js:383–384`
  - The helper should support configurable open classes / hidden classes while owning the common behavior contract (aria-expanded sync, panel show/hide, optional post-action refocus).

- **Phase 4: add two dismissible-surface helpers** (splitting what was one phase — scrim-backed overlays and ambient-click menus need different behavior contracts and are not interchangeable today)
  - Both helpers below should consume the Phase 2 pressable for their close buttons and triggers so a "dismiss me" button is not its own parallel activation codepath.
  - **4a. Scrim overlay / modal helper** — consolidates backdrop click + explicit close button + `Escape` wiring for surfaces that dim the rest of the shell. Configures whether close should refocus the composer and whether it should clear local transient state. Biggest win: replaces most of the duplicated close wiring in `controller.js:803–918` (kill, histDel, shareRedaction, FAQ, Options, Theme, Workflows, Shortcuts, history panel) and the sheet-specific copy in `mobile_chrome.js:629–634` with one registry, while preserving the current close-priority order instead of flattening it into an unordered generic dismiss action.
    - API shape to preserve that ordering: `bindDismissible(el, { level, onClose, ... })` where `level` is one of `'modal' | 'panel' | 'sheet'` (matches the three tiers already implicit in the current cascade). A shared `closeTopmostDismissible()` dispatcher is what the global `Escape` listener invokes; it closes the topmost open surface at the highest populated level and returns, matching today's early-return-after-close behavior.
    - Migration targets: FAQ, Workflows, Theme, Options, Shortcuts, kill confirmation, share-redaction, history panel, plus mobile menu-sheet and recents-sheet (Escape paths).
  - **4b. Ambient outside-click menu helper** — `bindOutsideClickClose(panel, { triggers, onClose })` for menus that dismiss on any document click outside the panel/trigger. Today this pattern is re-implemented with ad-hoc `closest()`/`contains()` checks in at least six places:
    - mobile menu + history panel + autocomplete — `controller.js:997–1009`
    - per-tab save-menu — `tabs.js:604`
    - permalink save-menu — `permalink.js:117, 205`
    - HUD save-menu — `shell_chrome.js:415`
    - recents filter dropdowns — `mobile_chrome.js` (`_closeRecentsDropdowns`)
  - **Trigger-exemption contract (applies to 4b, and to 4a when a trigger exists):** the pressable(s) passed as `triggers` are exempt from outside-click dismissal even though they sit outside the panel element — the helper must treat a click that lands on a registered trigger as "inside", not "outside". This is the thing all six current copy-pasted sites get subtly wrong in different ways (some test `e.target === trigger`, some test `trigger.contains(e.target)`, some omit the check entirely and rely on the trigger toggling the panel back open on the same click).

- **Phase 5: narrow the direct focus API**
  - Reduce raw DOM `focus()` / `blur()` calls across the UI modules and route them through a small set of helpers in `ui_helpers.js`. Concrete residuals to address: `ui_helpers.js:456` (the fallback inside `hideSearchBar` calling `cmdInput.focus()` directly) and the scattered `activeElement.blur()` cases in `tabs.js:38–39` and `history.js:478`.
  - The intended steady state is:
    - helper-owned focus selection logic
    - helper-owned blur behavior for mobile
    - minimal or no direct `element.focus()` calls outside helper internals
  - This should make future interaction fixes land in one place instead of being patched per component.

- **Phase 6: test and documentation follow-through**
  - Add or update tests for the shared interaction contract rather than only the individual widgets.
  - At minimum cover:
    - focus returns to the composer after non-text chrome actions
    - transient pressed/highlight state clears after activation (both for `<button>` and for `role="button"` elements, since the mechanisms differ)
    - `Enter` / `Space` activate pressables consistently
    - disclosures keep `aria-expanded` and visual state in sync
    - scrim overlays close consistently via button, backdrop, and `Escape`
    - ambient-click menus close on any outside click but not on clicks inside the panel or trigger
  - Update any shortcut/help text if interaction ownership changes user-visible behavior.

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
