# TODO

## Status

- Release line: `v1.3` (unreleased)
- Current focus: shell-style terminal UX hardening and source-of-truth cleanup
- Last major milestone completed: inline prompt refactor (phases 1-3 shipped)

---

## Active Workstreams

### 1) Shell-Style Input Refactor (Stabilization)

#### Objective
Keep the new terminal-native prompt flow stable across desktop/mobile and remove remaining legacy assumptions.

#### Implemented
- hidden real input remains source of truth
- inline rendered prompt with caret/selection mirroring
- prompt unmounts while command is running
- command echo lines preserve prompt styling in output
- welcome settle/skip integrated with inline prompt model
- blank `Enter` and `Ctrl+C` shell-like behaviors
- tab switch input neutrality (no command repopulation)
- tab overflow arrows and drag reorder
- mobile touch-and-drag tab reorder with visual lift/drop indicators
- terminal-style autocomplete placement (above/below)
- app-safe keyboard shortcuts for tab lifecycle and tab actions
- readline-style editing for `Ctrl+W`, `Ctrl+U`, `Ctrl+K`, `Alt/Option+B`, and `Alt/Option+F`
- readline-style cursor movement for `Ctrl+A` and `Ctrl+E`
- `keys` helper command plus FAQ/README shortcut documentation
- macOS-friendly `Option` shortcut handling and E2E coverage
- user options modal with cookie-persisted theme, timestamp, and line-number preferences
- permalink viewer toggles for line numbers on all permalinks and timestamps on metadata-backed permalinks
- structured run-output persistence for fresh history permalinks so line metadata survives into `/history/<run_id>`
- first-pass inline selection visibility improvements for shell-style Shift+Arrow editing
- permalink export coverage for filenames and view-state-aware txt/html content
- mobile shell-input hygiene: disabled autocap/autocorrect/spellcheck, mobile prompt visibility syncing via `visualViewport`, and keyboard dismissal after submit
- mobile composer refinement: visible mobile Run action and shortened live prompt chrome while the keyboard is open
- detached mobile composer host: live prompt now mounts outside the transcript while the keyboard is open and drops back into the output flow afterward
- mobile keyboard-open behavior: transient overlays/menu/history close while typing, autocomplete renders as a sheet above the composer, and body scroll is locked to the terminal pane
- version source cleanup: backend version is canonical, frontend header fallback is generic, and `/config` populates the visible version label
- dedicated mobile composer dock: the mobile shell now uses a visible composer row/host with a touch-focused input, visible Run action, and mobile-only mounting path while the desktop shell remains intact
- mobile helper-row polish: the compact edit helpers stay hidden until the keyboard is open, sync with the visible mobile input, and avoid letting autocomplete cover the helper row

#### Remaining
- continue refining inline selection visibility for advanced keyboard flows
- keep the `keys` helper command, FAQ entry, and README shortcut section aligned as bindings ship

#### Dedicated Mobile UI Plan

**Decision:** stop treating mobile as a responsive variant of the desktop terminal DOM. Keep one backend, one command engine, one history/permalink model, and one shared app state layer, but build a dedicated mobile presentation layer with its own layout, input model, and interaction patterns.

**Why this is the right direction now:**
- mobile is the majority usage path
- the current mobile implementation works, but it is built on desktop-first assumptions: hidden input mirroring, prompt re-mounting, viewport gymnastics, and browser-specific focus/keyboard workarounds
- Safari and Chrome have diverged enough that more responsive patching is likely to create recurring regressions
- a dedicated mobile surface will be simpler to reason about, simpler to test, and easier to evolve

**Non-goals:**
- do not fork the backend
- do not create a separate mobile app or separate routes with different command semantics
- do not duplicate execution, history, permalink, or allowlist logic
- do not regress desktop terminal behavior while mobile is being rebuilt

**Target mobile UX:**
- a fixed mobile app shell with a compact top bar
- a dedicated transcript area that scrolls independently
- a real visible mobile composer with a native text input or textarea as the source of truth
- a visible `Run` action at all times
- touch-first autocomplete as a sheet anchored to the composer
- a compact recent-command rail designed for one row and touch scrolling
- a mobile tab switcher that feels like session/workspace switching, not desktop tabs squeezed into a narrow bar
- simple, deterministic overlay behavior for history, FAQ, options, and kill confirmation

**Desktop/mobile architecture target:**
- shared:
  - Flask routes and data contracts
  - command execution lifecycle
  - history, permalink, and output persistence
  - welcome content sources
  - allowlist, FAQ, autocomplete, and config endpoints
  - shared session/tab state model where practical
- desktop-specific:
  - inline shell prompt rendering inside transcript
  - current terminal bar and tab strip behavior
  - keyboard-first interactions
- mobile-specific:
  - dedicated visible composer component
  - mobile transcript layout
  - touch-first actions, menus, and overlays
  - mobile tab/session switcher

**Required design constraint:** mobile must use a real visible editable control as its primary input. The hidden mirrored desktop input model can remain for desktop, but mobile should use native browser editing behavior for:
- caret placement
- text selection handles
- copy/paste
- keyboard open/close behavior
- browser-native word editing gestures

##### Phase 0: State And Boundary Cleanup

1. Extract a clear shared state layer for:
   - active tab/session id
   - current command value
   - run state
   - welcome state
   - autocomplete state
   - history metadata
   - preferences
2. Identify which current modules are desktop-rendering modules versus actual shared logic modules.
3. Refactor code so shared command/history/permalink operations are callable without assuming a desktop prompt DOM exists.
4. Define explicit interfaces for:
   - submit command
   - update current input value
   - open/close overlays
   - append output
   - switch tab/session
   - refresh history
5. Keep this refactor behavior-preserving before any mobile surface changes.

##### Phase 1: Mobile Shell Skeleton

1. Add a dedicated mobile root container in the template instead of reusing the desktop terminal structure.
2. Render desktop and mobile shells side-by-side in the DOM if needed, but show only one surface at a time by breakpoint/device mode.
3. Mobile shell should contain:
   - compact header
   - recent-command rail
   - transcript viewport
   - composer block
   - autocomplete sheet mount
   - modal/drawer mounts
4. The desktop shell should remain structurally unchanged during this phase.
5. Create mobile-specific CSS and JS sections rather than continuing to grow desktop mobile override rules.
6. Current implementation status: the dedicated mobile composer dock exists and is wired into the mobile presentation path, including the helper row, Run/Enter submission, history chips, and autocomplete sync; the wider mobile shell split still needs to be completed.

##### Phase 2: Real Mobile Composer

1. Replace the mobile mirrored prompt with a dedicated visible input component:
   - likely a single-line `input` initially
   - optionally promote to auto-growing `textarea` if long commands are easier to edit that way
2. Composer should include:
   - prompt label
   - native input field
   - Run button
   - optional clear/edit affordances only if still needed after switching to native input
3. Submitted commands should still echo into transcript using the existing prompt echo styling.
4. Mobile input should own:
   - keyboard open/close lifecycle
   - focus policy
   - autocorrect/autocapitalize/autocomplete/spellcheck settings
   - selection/caret behavior
5. Remove mobile dependence on the hidden desktop prompt mirror once parity is reached.

##### Phase 3: Mobile Transcript And Output Model

1. Build a mobile transcript renderer optimized for readability and touch scrolling.
2. Preserve existing output semantics:
   - prompt echo lines
   - stdout/stderr styling
   - exit lines
   - timestamps/line numbers when enabled
3. Decide mobile defaults for timestamps and line numbers:
   - likely off by default
   - still configurable in options
4. Ensure transcript and composer are fully independent:
   - transcript scrolls
   - composer stays fixed
   - keyboard does not obscure transcript or composer
5. Re-test long-output and long-command cases in both Safari and Chrome.

##### Phase 4: Mobile Autocomplete

1. Replace the current terminal-style dropdown logic on mobile with a dedicated autocomplete sheet.
2. Mobile autocomplete behavior should be touch-first:
   - anchored to composer
   - easy tap targets
   - stable vertical placement
   - no dependency on desktop up/down menu inversion rules
3. Keep filtering logic shared with desktop, but mobile rendering and interaction should be separate.
4. Define behavior for:
   - tap suggestion
   - keyboard enter
   - escape/close
   - empty input
   - scrolling long suggestion lists
5. Add strict regression coverage for first-open placement in Safari and Chrome.

##### Phase 5: Mobile Session And History Navigation

1. Replace the squeezed desktop tab bar with a mobile-specific session switcher.
2. Candidate approach:
   - horizontal session chips plus overflow button
   - or a session drawer / bottom sheet
3. Mobile switching should support:
   - create session
   - switch session
   - rename session
   - close session
   - reorder later only if still valuable on touch
4. Keep recent-command rail separate from session switching.
5. History drawer should be designed for touch:
   - large row hit targets
   - clear restore feedback
   - easy permalink/copy/delete actions

##### Phase 6: Mobile Welcome Flow

1. Keep the compact mobile welcome approach.
2. Rework it to fit the dedicated mobile shell:
   - compact text block at top of transcript
   - recent commands directly below
   - composer visible immediately
3. Mobile welcome should never own the composer lifecycle.
4. Typing, tapping the composer, or choosing a recent command should always bypass welcome immediately.
5. The Firefox note can remain until Chrome behavior is genuinely equivalent.

##### Phase 7: Mobile Overlay And Action System

1. Convert mobile menu, FAQ, options, history, kill confirm, and future actions into a consistent touch overlay system.
2. Prefer bottom sheets or full-height drawers over desktop modal patterns on mobile.
3. Define one mobile overlay manager so only one major overlay is open at a time.
4. Make input focus behavior deterministic:
   - opening overlay blurs mobile composer
   - closing overlay restores focus only when appropriate
5. Ensure search is also reconsidered for mobile rather than inherited from desktop layout.

##### Phase 8: Mobile Preference And Display Policy

1. Decide which preferences are global versus device-specific.
2. Recommended:
   - theme can stay shared
   - timestamps/line numbers may need mobile-specific defaults
   - mobile-only preferences may be needed later for compact mode and transcript density
3. Add a mobile-first options surface rather than reusing desktop options layout unchanged.
4. Ensure cookies/preferences do not force awkward desktop choices onto mobile and vice versa.

##### Phase 9: Browser Hardening

1. Treat iOS Safari as the primary mobile reference browser.
2. Treat iOS Chrome as a supported-but-quirky secondary target because it still rides WebKit but adds its own heuristics.
3. Explicitly test:
   - keyboard open/close
   - focus-on-tap
   - autocomplete tap acceptance
   - recent command taps
   - history restore
   - permalink/copy/export actions
   - long command editing
4. Document known limitations only after exhausting clean fixes, not as a substitute for product quality.

##### Phase 10: Migration And Cleanup

1. Once mobile parity is achieved on the dedicated surface, remove mobile-only hacks from the desktop prompt path.
2. Delete no-longer-needed mobile composer remount logic from the desktop inline prompt implementation.
3. Reduce CSS override complexity by removing old mobile special cases that only existed to make desktop markup fit phones.
4. Keep desktop and mobile code paths intentionally separate where behavior is different, but keep shared services and state centralized.
5. Update docs so the architecture explicitly states:
   - desktop shell and mobile shell are separate presentation layers
   - backend and persistence remain shared

##### Detailed Implementation Order

1. Refactor shared state and command actions out of prompt-specific DOM code.
2. Add dedicated mobile shell markup and hide it behind current mobile detection.
3. Implement mobile composer with real visible input and Run button.
4. Hook mobile composer into shared run flow and transcript echo.
5. Build mobile autocomplete sheet.
6. Build mobile recent-command rail and history drawer against the new shell.
7. Replace mobile tab bar with mobile session switcher.
8. Move mobile FAQ/options/search/menu into touch-appropriate overlays.
9. Remove old mobile prompt remount logic.
10. Cleanup, docs, and test expansion.

##### Testing Plan For Dedicated Mobile UI

**Unit coverage to add:**
- mobile shell boot state
- mobile composer value/focus lifecycle
- mobile autocomplete sheet interactions
- mobile recent-command rail overflow behavior
- mobile session switcher state
- mobile overlay manager behavior

**Playwright coverage to add:**
- mobile shell first load in compact welcome mode
- composer focus and keyboard-open state transitions
- suggestion tap acceptance
- long-command edit and caret movement
- recent-command replay
- history restore into current/new session
- mobile session creation/switch/close
- mobile permalink/copy/export actions
- options and FAQ flows inside mobile overlays

**Manual browser verification matrix:**
- iPhone Safari
- iPhone Chrome
- Android Chrome
- one narrow desktop browser width as a non-touch sanity check

##### Risks

- extracting shared state from the current DOM-heavy desktop prompt code is the biggest engineering step
- mobile and desktop can drift if shared service boundaries are not established early
- trying to preserve too much desktop visual language on mobile will recreate the current problem

##### Success Criteria

- mobile composer is always visible without layout hacks
- tapping composer reliably opens the keyboard on Safari and Chrome
- autocomplete is stable and touch-friendly
- recent commands and history feel native on touch
- long command editing works with native browser editing behavior
- mobile code no longer depends on desktop prompt remount tricks to stay usable
- desktop shell remains stable and simpler after mobile-specific hacks are removed

#### Risks
- keyboard/focus edge cases around hidden input + rendered caret
- mobile virtual keyboard behavior differences by browser

#### Keyboard Shortcut Rollout Spec
- keep browser-conflicting bindings optional; define app-safe shortcuts as the primary contract

Planned tab bindings:
- shipped: `Alt/Option+T` new tab
- shipped: `Alt/Option+W` close current tab
- shipped: `Alt/Option+ArrowRight` / `Alt/Option+ArrowLeft` next / previous tab
- shipped: `Alt/Option+1` ... `Alt/Option+9` direct tab jump

Planned action bindings:
- shipped: `Enter` / `Escape` confirm / cancel kill dialog
- shipped: `Alt/Option+P` create permalink
- shipped: `Alt/Option+Shift+C` copy active-tab output
- shipped: `Ctrl+L` clear current tab output

Planned readline-style editing:
- shipped: `Ctrl+U` kill to beginning of line
- shipped: `Ctrl+K` kill to end of line
- shipped: `Ctrl+A` / `Ctrl+E` move to start / end of line
- shipped: `Alt/Option+B` / `Alt/Option+F` move backward / forward by word
- remaining: consider yank/kill-ring behavior, more advanced selection feedback, and additional shell-native editing keys

Helper-command plan:
- `keys` is now the dedicated shortcut-discovery helper command
- keep `keys` printing a `Current shortcuts:` section for shipped behavior
- keep `keys` printing a `Fallback notes:` section for browser-native combos like `Ctrl/Cmd+T` and `Ctrl/Cmd+W` while those remain environment-dependent

---

### 2) FAQ Single Source Of Truth

#### Status
Shipped. Built-in FAQ entries now live in the backend alongside custom `faq.yaml` entries, and `/faq` is the canonical source for both the modal and terminal `faq` helper output.

#### Result
One canonical backend FAQ dataset now renders:
- rich HTML in modal
- plain text in `faq` helper command

#### Follow-Up
- keep modal-only `answer_html` content aligned with the plain-text `answer` used by the `faq` helper command
- extend the same backend FAQ schema if future modal sections need new dynamic render kinds

---

### 3) Version Source Cleanup

#### Status
Shipped. The backend `/config` response is the canonical version source, the initial header label is generic, and the frontend updates the visible version label only after config loads.

#### Result
One release version touchpoint remains:
- `app/config.py` defines the backend version
- `/config` exposes it to the frontend
- the UI falls back to a generic `real-time` label until config loads

---

## Documentation Follow-Ups

- keep README feature list aligned with inline prompt behavior and tab UX
- keep ARCHITECTURE test totals and module behavior synced with current suites
- keep `tests/README.md` suite breakdown synced to real spec/test names
- maintain changelog entries as behavior changes, not just file-level diffs

---

## Testing Follow-Ups

- add targeted unit/e2e coverage whenever keyboard editing semantics change
- add coverage for keyboard shortcuts discovery and preference persistence flows
- keep coverage for permalink rendering options in sync as run-permalink metadata support expands
- keep bad-path tests for welcome interruption, history restore latency, and autocomplete placement regressions
- continue validating no-output action toasts and permalink/full-output consistency paths
