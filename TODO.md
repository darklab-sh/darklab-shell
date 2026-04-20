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

### Whole-App UI Review Follow-Through Plan

- **Goal** — turn the full-app UI review into an incremental implementation plan that fixes the highest-signal UX issues first, then consolidates repeated patterns into shared UI primitives and stronger visual semantics.

- **Source brief** — full rationale, review findings, guiding principles, and ownership notes live in `~/git_docs/ui_review_plan.md`. This TODO entry is the executable task list; consult the source when a phase bullet needs more context.

- **Gate** — after every phase, `python -m pytest tests/py/test_docs.py -q` (21/21) and `npm run lint:md` stay green. Design-system surfaces that change visually must be re-captured in the UI screenshot scenes so regressions are visible in the next design pack.

- **Milestones** — the work ships as five sequential milestones. Each milestone is its own branch (`ui_review_milestone_N`) off `v1.5`, with commits per phase item completed, merged back to `v1.5` when the milestone is done.

  - **Milestone 1 — trust, clarity, and consistency** (Phase 1 + Workstream E prelude)
    - rail workflow title readability (Phase 1 item 1)
    - desktop theme active-state indicator (Phase 1 item 3)
    - history destructive-action hierarchy (Phase 1 item 2)
    - disclosure-language rules documented and applied to the highest-traffic surfaces (Phase 1 item 4)
    - mobile non-active running-state indicator (Phase 2 Workstream E prelude, shipped alongside Phase 1 because it is a trust fix, not just polish)
    - That set addresses the sharpest issues from the review while establishing the design-system rules the rest of the cleanup depends on.

  - **Milestone 2 — shared system primitives** (Phase 2 Workstreams A–D; E shipped in milestone 1)
    - button hierarchy and destructive semantics (Workstream A)
    - confirmation-dialog primitive (Workstream B)
    - themed desktop form controls (Workstream C)
    - color-semantics audit (Workstream D)

  - **Milestone 3 — desktop surface polish** (Phase 3)
    - rail collapsed-state behavior, snapshot metadata hierarchy, status-bar wording, compact dialog spacing, workflow modal usability, save-menu copy, permalink prompt consistency, diagnostics page clarity, toolbar and discoverability polish.

  - **Milestone 4 — mobile surface polish** (Phase 4)
    - history-sheet clarity, delete-all confirmation on narrow screens, main terminal action-row density, filter-chip affordance clarity, mobile menu toggle ergonomics, mobile search clarity.

  - **Milestone 5 — cross-cutting review and follow-through** (Phase 5)
    - audit new patterns against UI screenshot capture scenes, update theme audits and interaction-contract tests where new semantics become a shared contract, reflect finalized design-system rules in `FEATURES.md` / `ARCHITECTURE.md` / `DECISIONS.md` as appropriate.

- **Open product decisions** — resolve these before coding the related phase items so the work does not churn mid-implementation. Decisions are grouped by the phase they gate; resolved decisions carry an inline `Decision:` line.
  - **Phase 1 decisions**
    - **Rail strategy** — wrap workflow titles, widen the expanded rail, or tooltip-only fallback? (gates Phase 1 item 1)
      - Decision: Wrap workflow titles
    - **Wrap line cap** — wrap to two lines maximum with truncation beyond, or allow unlimited wrapping? Pinning this prevents an unusually long custom workflow from breaking rail rhythm later. (gates Phase 1 item 1)
      - Decision: Wrap to two lines maximum. After two lines, truncate with ... and a hover tool-tip with full text.
    - **History actions** — overflow menu, or always-visible delete with destructive styling? (gates Phase 1 item 2)
      - Decision: always visible delete with destructive styling
    - **Destructive styling treatment** — red text, red icon, red on hover only, or ghost button with red label? Same treatment must apply to desktop history rows, mobile history cards, and the delete-all entry point so all three share one visual contract. (gates Phase 1 item 2)
      - Decision: current button container with red border (and red label text), shared across desktop rows and mobile cards. Same format on delete-all
    - **Theme active-state vehicle** — visual card treatment alone, or also a textual `active` label/badge? Decide before the audit so all shipped themes get the same treatment in one pass. (gates Phase 1 item 3)
      - Decision: Visual card treatment alone
    - **Disclosure-rule boundary cases** — for the `▸/▾` (expand/collapse) vs `>` (drill-in/navigation) rule, how do these edge cases resolve: menu rows that open a sheet (drill-in or expand?), popovers and dropdowns (glyph or none?), and composite cases (a drill-in row whose sheet contains expand/collapse subsections)? Without this the audit will produce inconsistent calls. (gates Phase 1 item 4)
      - Meta-rule: glyph follows actual behavior, not visual hierarchy. Apply this rule to resolve every disclosure-language question; the cases below are concrete applications of it.
      - Menu rows that open a sheet: Use `>` (sheets count as navigation to a new surface).
      - Popovers and dropdowns: rotating `▾` (permitted only on dropdown/popover triggers; not interchangeable with `▸/▾` block disclosure).
      - Composite cases: glyph must match actual behavior. If a row expands inline, use `▾`; if it navigates to a new surface, use `>`. Audit and fix per row — likely a small set (e.g. the mobile menu `timestamps` row swaps `›` → `▾` because it expands an inline submenu rather than navigating).
      - Toggle rows take no disclosure glyph; the toggle state label (`off` / `on`) is the affordance (e.g. the mobile menu `line numbers` row drops its `›`).
  - **Phase 2 decisions**
    - **Mobile running-state treatment** — header pill augmentation, hamburger badge, or dedicated jump-to-running affordance? (gates Phase 2 Workstream E)
      - Decision: tab-bar edge glow + docked running-count chip on the tab bar. The pulsing edge fade signals that a running tab is scrolled off-screen and indicates which direction to scroll; the docked chip (e.g. `● 2`) appears only when background tabs are running and taps to jump to the next running tab. The header status pill is left untouched and remains the canonical run-state surface for the active tab.
    - **Chip placement** — leading or trailing edge of the tab bar? Trailing matches notification-badge convention; leading lands earlier in the natural reading sweep. (gates Phase 2 Workstream E)
      - Decision: Trailing edge of the tab bar
    - **Chip count semantics** — does the count include the active tab if it is also running, or only background tabs? Background-only avoids double-signalling what the pill already shows. (gates Phase 2 Workstream E)
      - Decision: all running non-active tabs
    - **Chip tap behavior** — cycle through running tabs on repeated taps, or always jump to a fixed target (oldest-running, or nearest-off-screen)? Cycling scales with many runs; fixed-target is more predictable. (gates Phase 2 Workstream E)
      - Decision: Cycle through running tabs in order of their tab row placement.
    - **Button role tokens** — do the four roles (`primary` / `secondary` / `ghost` / `destructive`) reuse existing CSS variables, or introduce new role tokens? Affects every theme file and downstream theme contributions. (gates Phase 2 Workstream A)
    - **Confirmation primitive scope** — does the new primitive replace the current modal helper, or wrap it? Determines whether kill, history-delete, and share-redaction confirmations migrate in one PR or incrementally. (gates Phase 2 Workstream B)
      Decision: Replace it. And all modular code needs to be implemented via the helpers where possible for easy re-use in the future.
    - **Desktop form controls** — fully custom desktop selects and checkboxes, or minimal restyle of native controls first? (gates Phase 2 Workstream C)
      - Decision: minimal restyle of native controls first
    - **Per-theme legibility bar for custom controls** — minimum contrast and state-visibility threshold a custom select or checkbox must hit across every shipped theme, set up front so themes do not need to be revisited per workstream. (gates Phase 2 Workstream C)
    - **Color-semantics yellow scope** — does the new "yellow = caution / reversible / expiring" rule force a token rename across themes, or only a usage audit on existing tokens? Renaming touches every theme; usage-only is local. (gates Phase 2 Workstream D)
  - **Phase 3 decisions**
    - **Workflow execution** — `run` per step only, or `run` plus `run all` in the same pass? (gates Phase 3 workflow-modal item)
      - Decision: Run per step only because the workflow commands are only examples. Unless we add inputs into the workflow form such as "target" or "domain", a run all wouldn't make sense.
    - **Rail collapsed-state auto-switch** — when both rail sections are collapsed, auto-switch to the skinny icon rail, or stay as-is? Behavior change vs visual-only. (gates Phase 3 rail collapsed-state item)
    - **Snapshot metadata critical set** — which fields stay emphasized in the snapshot header (expiry only, or also redaction mode / share state)? (gates Phase 3 snapshot metadata item)
    - **Status-bar wording** — concrete replacements for `RUNS 1 / 2`; and during an active run, does `LAST EXIT` dim, relabel, or hide? (gates Phase 3 status-bar item)
    - **Save-menu labels** — concrete new wording to replace `txt / html / pdf` (e.g. `Plain text` / `Themed page` / `PDF`)? (gates Phase 3 save-menu item)
    - **Permalink prompt fidelity** — preserve full prompt identity on permalink pages, or keep the reduced echo? Yes/no decision; affects snapshot HTML output. (gates Phase 3 permalink prompt item)
    - **Diagnostics split axis** — which buckets does the activity section split into (counts vs status vs config, or some other axis)? (gates Phase 3 diagnostics item)
  - **Phase 4 decisions**
    - **Mobile menu toggle conversion** — convert line-numbers and timestamps from drill-in rows to direct toggles, or keep them as drill-in rows? Changes the menu's interaction model. (gates Phase 4 mobile menu item)
    - **Mobile action-row trim** — confirm `clear` moves to the menu; decide whether any other action (copy, share, save) also moves. (gates Phase 4 main terminal action-row item)
    - **Mobile search layout** — single row with a counter, or secondary row for advanced toggles when width is tight? (gates Phase 4 mobile search item)
  - **Phase 5 decisions**
    - **Documentation home for finalized rules** — pick the default home (`FEATURES.md`, `ARCHITECTURE.md`, or `DECISIONS.md`) for the durable design-system rules established in Phases 1–2: button roles, disclosure language, color semantics, and confirmation primitive contract. Pinning this now prevents each workstream from re-litigating where its rules live. (gates Phase 5)

#### Phase 1 — Must-fix clarity issues

- **Desktop rail workflow title truncation**
  - Decide between three treatments: two-line wrapping, wider expanded rail, or fallback truncation with tooltip support.
  - Audit built-in workflow names against the current rail width and identify which titles currently read as broken rather than intentionally abbreviated.
  - Implement the chosen rail treatment and verify the rail still feels balanced with both `Recent` and `Workflows` expanded.
  - Add coverage for long workflow names in desktop UI capture scenes so truncation regressions are visible in design packs.

- **History action hierarchy on desktop and mobile**
  - Re-rank history-row actions so destructive actions no longer compete visually with safe utility actions.
  - Prototype an overflow/action-sheet treatment for `permalink` and `delete`, keeping `copy` as the primary visible action.
  - Apply the same hierarchy rules to desktop history rows and mobile history cards/sheets.
  - Revisit delete-all entry points so destructive actions remain discoverable without reading as peer-primary actions.

- **Desktop theme modal active-state indicator**
  - Mirror the stronger active-theme treatment already present on mobile.
  - Add an explicit selected-state indicator on desktop cards, optionally with a small `active` label or badge.
  - Verify selected-theme clarity across both desktop and mobile theme pickers in all shipped themes.

- **Disclosure affordance unification**
  - Standardize disclosure icon language: `▸/▾` for expand-collapse, `>` only for drill-in or navigation.
  - Audit FAQ, rail section headers, save menus, mobile menu rows, and any remaining popovers/dropdowns that still imply a different disclosure contract.
  - Update icons, affordance spacing, and any paired labels/tooltips so users can infer the interaction type from the affordance alone.

#### Phase 2 — Shared system workstreams

- **Workstream A: button hierarchy and destructive semantics**
  - Define four reusable button roles: `primary`, `secondary`, `ghost`, and `destructive`.
  - Audit current usage across history rows, modal actions, toolbar buttons, rail/menu actions, and terminal action rows.
  - Align destructive actions so they never read like safe peer-primary actions.
  - Reserve `primary` for the dominant action in a cluster and use `ghost` for low-emphasis utilities.
  - Apply the same role system to mobile action sheets and confirmation dialogs.

- **Workstream B: confirmation-dialog primitive**
  - Standardize one confirmation-dialog pattern with title, body copy, destructive level, and 1–3 actions.
  - Normalize sentence-case labels, button placement, spacing, and destructive emphasis.
  - Support desktop modal layout and mobile stacked-button/narrow-width behavior from the same primitive.
  - Migrate kill, history delete, share-redaction, and other destructive confirmations onto the same pattern.

- **Workstream C: themed desktop form controls**
  - Design app-native themed `select` and `checkbox` treatments for desktop surfaces.
  - Apply them first in the Options modal.
  - Keep native select behavior on mobile unless the themed treatment proves clearly better there too.
  - Confirm the controls remain legible across all shipped themes.

- **Workstream D: color-semantics audit**
  - Write explicit semantic color rules:
    - yellow = caution / reversible destructive / expiring
    - red = destructive / kill / error / irreversible
    - green = active / success / enabled / current
    - dim = neutral metadata
  - Audit high-visibility violations first, especially snapshot metadata, diagnostics values, and warning-like metadata that currently overuse yellow.
  - Update component docs or theme guidance where semantic usage needs to be pinned.

- **Workstream E: mobile running-state visibility**
  - Add a system-level mobile indicator when any non-active tab is running.
  - Evaluate candidate treatments: header badge, hamburger badge, running-tab jump target, or running-count pill.
  - Keep the desktop model largely unchanged unless a small parity/clarity tweak is justified.
  - Verify the mobile state model no longer reads as globally idle while another tab is still running.

#### Phase 3 — Desktop surface polish

- **Rail collapsed-state behavior**
  - Evaluate whether the rail should auto-switch to the skinny icon rail when both sections are collapsed.
  - Confirm the collapsed state still communicates available navigation clearly.

- **Snapshot metadata hierarchy**
  - Keep expiry emphasized.
  - Dim non-critical metadata so the snapshot header reads as information hierarchy instead of flat emphasis.

- **Status-bar wording clarity**
  - Revisit ambiguous labels like `RUNS 1 / 2`.
  - Decide whether `LAST EXIT` should dim or relabel while an active run is still in progress.

- **Compact dialog spacing**
  - Tighten body-to-action spacing and action alignment in smaller modals.
  - Recheck narrow-width dialog rhythm after the shared confirmation primitive lands.

- **Workflow modal usability**
  - Add per-step `run` affordances.
  - Align step columns and spacing so multi-step workflows scan more cleanly.

- **Save-menu copy clarity**
  - Reword `txt / html / pdf` into more descriptive save actions.
  - Optionally strengthen the visual attachment cue between the trigger and the menu.

- **Permalink prompt consistency**
  - Decide whether permalink pages should preserve the full prompt identity rather than a reduced prompt echo.
  - Apply only if it aligns with product intent across normal runs and snapshots.

- **Diagnostics page clarity**
  - Split activity sections by concept where the page currently mixes counts and status in one block.
  - Add a generated-at timestamp.
  - Align diagnostics coloring with the color-semantics audit above.

- **Toolbar and discoverability polish**
  - Improve autocomplete selected-row visibility.
  - Highlight substring matches in reverse search.
  - Add tooltips for icon-only rail or toolbar states where needed.
  - Explain starred-first grouping in history if the resulting ordering is otherwise unclear.
  - Revisit decorative traffic-light controls if they remain non-functional visual chrome.

#### Phase 4 — Mobile surface polish

- **History-sheet clarity**
  - Add stronger card separation or subtle background grouping.
  - Surface relative timestamps on mobile history rows where they improve scanability.

- **Delete-all confirmation on narrow screens**
  - Stack buttons vertically when narrow-width layouts would otherwise compress the action row too aggressively.
  - Keep action emphasis aligned with the shared confirmation primitive.

- **Main terminal action-row density**
  - Reduce visible action count on narrow devices.
  - Likely move `clear` into the menu rather than keeping it in the always-visible row.

- **Filter-chip affordance clarity**
  - Make removable chips visibly removable in both expanded and collapsed filter states.
  - Verify the chip affordance remains clear inside the mobile history/search flow.

- **Mobile menu toggle ergonomics**
  - Reassess whether line numbers and timestamps should remain drill-in rows or become direct toggles.
  - Keep any sub-menu behavior aligned with the disclosure-affordance rules from Phase 1.

- **Mobile search clarity**
  - Add a visible match counter.
  - Recheck search-state visibility when combined with active filters or chips.

#### Phase 5 — Cross-cutting review and follow-through

- Audit all new patterns against UI screenshot capture scenes and demo-recording outputs so visual regressions are caught in the design-review pipeline.
- Update theme audits or interaction-contract tests where the new semantics become part of a shared contract.
- Reflect any finalized design-system rules in `FEATURES.md`, `ARCHITECTURE.md`, or `DECISIONS.md` if the changes establish durable UI behavior rather than one-off polish.

### ARCHITECTURE.md Restructure Plan

- **Goal** — reorganize `ARCHITECTURE.md` around clearer conceptual clusters without reducing technical depth, flattening request-flow narratives, or breaking useful reference sections that already work well.

- **Source brief** — full rationale, problem diagnosis, proposed 14-section order, and the minimal-regrouping fallback live in `~/git_docs/architecture_restructure.md`. This TODO entry is the executable task list; consult the source when a phase bullet needs more context.

- **Gate** — after every phase, `python -m pytest tests/py/test_docs.py -q` (21/21) and `npm run lint:md` stay green. Cross-doc references from `README.md`, `FEATURES.md`, `DECISIONS.md`, `tests/README.md`, and `~/git_docs/*` are re-checked before a phase is marked complete.

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
- the doc gate (`tests/py/test_docs.py`, 21/21) and `npm run lint:md` stay green, and cross-doc references from `README.md`, `FEATURES.md`, `DECISIONS.md`, `tests/README.md`, and `~/git_docs/*` still resolve

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
