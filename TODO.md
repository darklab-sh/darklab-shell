# TODO

## Status

- Release line: `v1.3` (unreleased)
- Current focus: Phase 10 migration and cleanup
- Last major milestone completed: Phase 9 browser hardening

---

## Open TODOs

### 1) Shell-Style Input Refactor (Stabilization)

#### Objective
Keep the new terminal-native prompt flow stable across desktop/mobile and remove remaining legacy assumptions.

#### Completed
- ~~hidden real input remains source of truth~~
- ~~inline rendered prompt with caret/selection mirroring~~
- ~~prompt unmounts while command is running~~
- ~~command echo lines preserve prompt styling in output~~
- ~~welcome settle/skip integrated with inline prompt model~~
- ~~blank `Enter` and `Ctrl+C` shell-like behaviors~~
- ~~tab switch input neutrality (no command repopulation)~~
- ~~tab overflow arrows and drag reorder~~
- ~~mobile touch-and-drag tab reorder with visual lift/drop indicators~~
- ~~terminal-style autocomplete placement (above/below)~~
- ~~app-safe keyboard shortcuts for tab lifecycle and tab actions~~
- ~~readline-style editing for `Ctrl+W`, `Ctrl+U`, `Ctrl+K`, `Alt/Option+B`, and `Alt/Option+F`~~
- ~~readline-style cursor movement for `Ctrl+A` and `Ctrl+E`~~
- ~~`keys` helper command plus FAQ/README shortcut documentation~~
- ~~macOS-friendly `Option` shortcut handling and E2E coverage~~
- ~~user options modal with cookie-persisted theme, timestamp, and line-number preferences~~
- ~~permalink viewer toggles for line numbers on all permalinks and timestamps on metadata-backed permalinks~~
- ~~structured run-output persistence for fresh history permalinks so line metadata survives into `/history/<run_id>`~~
- ~~first-pass inline selection visibility improvements for shell-style Shift+Arrow editing~~
- ~~permalink export coverage for filenames and view-state-aware txt/html content~~
- ~~mobile shell-input hygiene: disabled autocap/autocorrect/spellcheck, mobile prompt visibility syncing via `visualViewport`, and keyboard dismissal after submit~~
- ~~mobile composer refinement: visible mobile Run action and shortened live prompt chrome while the keyboard is open~~
- ~~detached mobile composer host: live prompt now mounts outside the transcript while the keyboard is open and drops back into the output flow afterward~~
- ~~mobile keyboard-open behavior: transient overlays/menu/history close while typing, autocomplete renders as a sheet above the composer, and body scroll is locked to the terminal pane~~
- ~~version source cleanup: backend version is canonical, frontend header fallback is generic, and `/config` populates the visible version label~~
- ~~dedicated mobile composer dock: the mobile shell now uses a visible composer row/host with a touch-focused input, visible Run action, and mobile-only mounting path while the desktop shell remains intact~~
- ~~mobile helper-row polish: the compact edit helpers stay hidden until the keyboard is open, sync with the visible mobile input, and avoid letting autocomplete cover the helper row~~
- ~~batched live-output rendering: fast bursts flush in small chunks so the browser can repaint, and the terminal follows the bottom only while the user has not scrolled away~~
- ~~shared Run-button guard: desktop and mobile Run controls disable together while a command is active so duplicate submits are blocked consistently~~

#### Open items
- continue refining inline selection visibility for advanced keyboard flows
- keep the `keys` helper command, FAQ entry, and README shortcut section aligned as bindings ship
- mobile follow-ups to consider if a concrete need appears:
  - tab reorder on touch
  - history drawer touch refinements, including larger hit targets and swipe-to-close
  - history delete / kill modal close-focus behavior
  - mobile-only preferences such as compact mode and transcript density

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

**Completed**
- ~~`app/static/js/state.js` introduced: single `APP_STATE` object backed by `Object.defineProperty` descriptors so every module can still read/write state vars as plain globals while the actual storage is centralised~~
- ~~all 36 module-level `let` state declarations removed from autocomplete.js, history.js, runner.js, search.js, tabs.js, welcome.js — they now live only in state.js~~
- ~~`getAppState()` / `resetAppState()` helpers exposed for the browser and unit test harness~~
- ~~tab accessor helpers added: `getTabs()`, `setTabs(v)`, `getActiveTabId()`, `setActiveTabId(v)`, `getActiveTab()`, `getTab(id)` — replace 25 inline `tabs.find(t => t.id === …)` call sites across runner.js, tabs.js, output.js, app.js, history.js~~
- ~~`setTabs()` / `setActiveTabId()` used at the two reassignment sites in tabs.js (syncTabOrderFromDom, activateTab)~~
- ~~all redundant `typeof fn === 'function'` guards removed from app.js, runner.js, tabs.js, welcome.js (scripts load in a defined order; guards were dead code)~~
- ~~`submitCommand(rawCmd)` extracted from `runCommand()` as the shared DOM-free entry point for command execution; returns `true` (submitted), `false` (rejected/blocked), or `'settle'` (empty welcome input); `runCommand()` is now the desktop wrapper that reads cmdInput and handles input cleanup based on the return signal~~
- ~~`_clearDesktopInput()` helper extracted; `dismissMobileKeyboardAfterSubmit` moved to `runCommand()` caller~~
- ~~desktop input mirroring now routes through `setComposerValue()` instead of a hand-rolled mobile sync branch~~
- ~~overlay helpers centralized in `state.js` for kill confirmation, history panel, FAQ, options, and history-delete surfaces~~
- ~~search bar and recent-history row visibility now route through shared helpers instead of ad hoc style toggles~~
- ~~run timer and per-tab kill button visibility now route through shared helpers instead of ad hoc style toggles~~
- ~~mobile menu open/close state now routes through shared helpers instead of ad hoc class toggles~~
- ~~MOTD wrapper visibility now routes through a shared helper instead of an ad hoc startup toggle~~
- ~~autocomplete dropdown visibility now routes through shared helpers instead of ad hoc style toggles~~
- ~~history loading overlay visibility now routes through shared helpers instead of ad hoc class toggles~~
- ~~mobile shell visibility now routes through shared helpers instead of direct hidden + aria-hidden writes~~
- ~~module boundary annotation across browser scripts~~
- ~~shared action path cleanup across tabs.js, welcome.js, and app.js~~
- ~~unit test harness updated: `state.js` prepended to all eval'd scripts; `fromDomScripts` accepts an `initCode` string so test loaders can call `setTabs(tabs); setActiveTabId(activeTabId)` to seed shared state; `STATE_SRC` cached at module level~~
- ~~227 unit tests passing (11 test files, no regressions)~~

**Phase 0 Complete**

The shared state layer, composer/overlay helpers, shared DOM binding cache, grouped mobile shell layout helpers, and tab-node helpers are all in place. The browser modules now rely on those shared helpers instead of ad hoc prompt or overlay state. The remaining work has moved into Phase 10 and beyond.

##### Phase 1: Mobile Shell Skeleton

**Completed**

- ~~Add a dedicated mobile root container in the template instead of reusing the desktop terminal structure.~~
- ~~Render desktop and mobile shells side-by-side in the DOM if needed, but show only one surface at a time by breakpoint/device mode.~~
- ~~Mobile shell should contain:~~
  - compact header
  - recent-command rail
  - transcript viewport
  - composer block
  - autocomplete sheet mount
  - modal/drawer mounts
  - mobile menu overlay
- ~~The desktop shell should remain structurally unchanged during this phase.~~
- ~~Create mobile-specific CSS and JS sections rather than continuing to grow desktop mobile override rules.~~
- ~~Current implementation status: the dedicated mobile composer dock exists and is wired into the mobile presentation path, including the helper row, Run/Enter submission, history chips, and autocomplete sync; the wider mobile shell split still needs to be completed.~~
- ~~Current implementation status: the template now includes a real `mobile-shell` root plus dedicated `mobile-shell-chrome`, `mobile-shell-transcript`, `mobile-shell-composer`, and `mobile-shell-overlays` mounts, with the mobile composer dock and menu nested inside the mobile shell; the current layout code resolves the shell, composer, and overlay refs through one combined mobile UI helper, binds and sets up the mobile composer interactions through helper functions, caches the shared top-level controls in `dom.js`, centralises tab-node lookups behind small tab helpers, and lets the shared state layer trust those cached bindings directly, while still moving the sections through grouped shell helpers in both directions and using a grouped visibility helper for the composer/prompt swap, and the remaining work is to finish the mobile-first layout and move the last desktop-shaped assumptions out of the way.~~

**Status**

Phase 1 is complete. The dedicated mobile shell root, chrome/transcript/composer/overlay mounts, shell-owned mobile menu, and shared mobile UI helpers are in place. Remaining mobile work now moves into Phase 10 and beyond.

##### Phase 2: Real Mobile Composer

**Completed**

- ~~The mobile composer now submits through the shared `submitVisibleComposerCommand()` helper directly, with mobile-specific keyboard dismissal and no desktop-style refocus on mobile.~~
- ~~Touch focus lands on the visible mobile composer through the shared `getVisibleComposerInput()` resolver instead of the hidden desktop input.~~
- ~~Autocomplete acceptance keeps focus on that visible composer.~~
- ~~The shared `focusVisibleComposerInput()` / `blurVisibleComposerInput()` helpers keep visible-input behavior on one path.~~
- ~~`handleComposerInputChange()` keeps desktop and mobile input updates on one path while the value-sync layer keeps the hidden desktop input compatible during the transition.~~
- ~~The mobile composer text now also flows through `getComposerValue()` so the submit path reads the shared visible composer value only through the shared submit helper boundary.~~

**Status**

Phase 2 is complete. The dedicated visible mobile composer, shared visible-input resolver, and mobile keyboard/focus helpers are in place. The active-tab-aware run-button guard and close-running-tab kill/reset path are also complete. The next mobile work now starts in Phase 10 with migration and cleanup, while any extra touch polish stays in the open follow-up bucket below.

##### Phase 3: Mobile Transcript And Output Model (Complete)

**Completed**
- ~~`#mobile-shell-transcript` receives `#tab-panels` via DOM reparenting at runtime; output routing (`appendLine`, `getOutput`) is already shared~~
- ~~`#mobile-composer-host` is now `position: fixed` at all times in mobile mode; keyboard-open only adjusts `bottom`/`left`/`right`/`border-radius`~~
- ~~`body.mobile-terminal-mode .output` uses `padding-bottom: var(--mobile-composer-height, 80px)` so content is never hidden behind the fixed composer~~
- ~~`syncMobileComposerHeight()` measures `#mobile-composer-host.offsetHeight` and writes to `--mobile-composer-height` on `documentElement`; called from `syncMobileViewportState` and `syncMobileComposerKeyboard` (on visualViewport resize/scroll and input focus/blur)~~
- ~~hardcoded `100px` and Chrome iOS `74px` rules removed~~
- ~~`isMobileKeyboardOpen` now checks viewport offset first (`offset > 40`) before falling back to focus-based detection — handles blur-without-dismiss (keyboard stays geometrically open after focus leaves the input)~~
- ~~`Timestamps and line numbers both default to 'off'` via `getPreference('pref_timestamps') || 'off'` at app.js:998-999; no code change needed~~
- ~~Independent transcript scroll on long-output and long-command cases was re-tested manually in Safari and Chrome after the fixed-composer change~~

**Status**

Phase 3 is complete. Transcript/output layout, fixed composer spacing, and keyboard-detection reliability are in place, and the remaining mobile work now continues in Phase 10 and beyond.

##### Phase 4: Mobile Autocomplete

**Completed**

- ~~Replace the current terminal-style dropdown logic on mobile with a dedicated autocomplete sheet.~~
- ~~Mobile autocomplete behavior is now touch-first:~~
  - ~~anchored to composer (already done via reparenting into `#mobile-composer-row`)~~
  - ~~easy tap targets: `.ac-mobile .ac-item` now uses `padding: 10px 14px`, `font-size: 14px`, `min-height: 44px`, `display: flex; align-items: center`; `::before` prefix glyph hidden on mobile~~
  - ~~stable vertical placement: always above the fixed composer (`bottom: calc(100% + 4px)`, `ac-up`); height caps at `min(targetHeight, available)` where available = space above composer~~
  - ~~no dependency on desktop up/down inversion rules: mobile takes the always-above path~~
- ~~`touchstart` handler added alongside `mousedown` in `acShow` for immediate tap acceptance without 300ms delay; `{ passive: false }` + `e.preventDefault()` prevents focus-loss before accept~~
- ~~Row height estimate updated from 22px to 44px; max item count for height calculation capped at 8; `maxHeight` uses full available space (no 200px hardcap) so the sheet can grow to fill the space above the composer~~
- ~~Filtering logic stays shared with desktop~~
- ~~Tap suggestion, keyboard enter, escape/close, empty input behaviors all already handled by existing shared paths~~

**Remaining:**

- Add regression coverage for first-open placement in Safari and Chrome (manual verification)

##### Phase 5: Mobile Session And History Navigation

**Completed**

- ~~Replace the squeezed desktop tab bar with a mobile-friendly session bar:~~
  - ~~`.dot` elements (macOS decorative dots) hidden in `mobile-terminal-mode`~~
  - ~~Tab scroll arrow buttons hidden in `mobile-terminal-mode` (replaced by native touch scroll)~~
  - ~~`.tab` touch targets enlarged: `min-height: 44px; padding: 0 14px; font-size: 13px; gap: 8px`~~
  - ~~`#new-tab-btn` enlarged: `min-height: 44px; padding: 0 16px; font-size: 16px`~~
  - ~~`.tab .tab-close` hit area enlarged: `20×20px`~~
  - ~~Status pill font adjusted for compact mobile header~~
- ~~Create/switch/rename/close session all work through the existing shared tab logic — no new JS needed~~

**Remaining:**

- Reorder on touch: not yet addressed
- History drawer touch refinement: large row targets / permalink/copy/delete on touch

##### Phase 6: Mobile Welcome Flow

1. ~~Keep the mobile welcome banner abbreviated and timing-aligned with desktop.~~
2. ~~Rework it to fit the dedicated mobile shell:~~
   - ~~compact text block at top of transcript~~
   - ~~recent commands directly below~~
   - ~~composer visible immediately~~
3. ~~Mobile welcome should never own the composer lifecycle.~~
4. ~~Typing, tapping the composer, or choosing a recent command should always bypass welcome immediately.~~
5. ~~Keep the mobile banner and status rows within the visible viewport on Chrome and Safari mobile without reintroducing browser-specific wording.~~

##### Phase 7: Mobile Overlay And Action System

**Completed**

- ~~Mobile menu converted to bottom sheet in `mobile-terminal-mode`:~~
  - ~~`position: fixed; bottom: 0; left: 0; right: 0` with `border-radius: 14px 14px 0 0`~~
  - ~~Safe-area inset bottom padding (`env(safe-area-inset-bottom, 0)`)~~
  - ~~Bottom sheet drag handle via `#mobile-menu::before` pseudo-element~~
  - ~~Button rows enlarged to `min-height: 52px; padding: 16px 20px; font-size: 15px`~~
- ~~`_closeMajorOverlays()` helper added to app.js — closes history panel, FAQ, and options overlays; called before opening any major overlay (FAQ, options, history)~~
- ~~History panel open now calls `blurVisibleComposerInputIfMobile()` and `_closeMajorOverlays()`; close restores focus via `refocusTerminalInput()`~~
- ~~Kill confirmation open (`confirmKill` in runner.js) now calls `blurVisibleComposerInputIfMobile()` before showing the modal~~
- ~~Search bar mobile overrides: `font-size: 16px`, input `min-height: 40px`, nav and toggle buttons `min-height: 40px` with larger padding~~

**Remaining:**

- History drawer touch refinement: larger action button hit areas, swipe-to-close
- History delete modal and kill modal close currently call `refocusTerminalInput()` — on mobile this may or may not be desired; revisit if we decide to change the close-focus policy later

##### Phase 8: Mobile Preference And Display Policy

**Completed**

- ~~Theme stays shared (existing behavior)~~
- ~~Timestamps and line numbers both default to `'off'` already — confirmed in Phase 3~~
- ~~FAQ and options overlays now render as bottom sheets in `mobile-terminal-mode`:~~
  - ~~`align-items: flex-end` on overlay backgrounds~~
  - ~~`width: 100%; border-radius: 14px 14px 0 0; max-height: 88svh`~~
  - ~~Drag handle via `::before` pseudo-element~~
  - ~~Safe-area bottom padding (`env(safe-area-inset-bottom, 0)`)~~
  - ~~Options choice rows enlarged to `min-height: 44px`; select enlarged to `min-height: 44px; font-size: 15px`~~

**Remaining:**

- Mobile-only preferences (compact mode, transcript density) remain a possible future follow-up if a concrete need appears

##### Phase 9: Browser Hardening (Complete)

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

Phase 9 is complete. Browser hardening and the manual mobile matrix have been exercised, and the remaining mobile refinement items are now treated as general follow-ups rather than phase-locked work.

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
- mobile shell first load uses the abbreviated mobile welcome banner
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

---

## Completed

### FAQ Single Source Of Truth

Built-in FAQ entries now live in the backend alongside custom `faq.yaml` entries, and `/faq` is the canonical source for both the modal and terminal `faq` helper output.

Result:
- rich HTML in modal
- plain text in `faq` helper command

Follow-up:
- keep modal-only `answer_html` content aligned with the plain-text `answer` used by the `faq` helper command
- extend the same backend FAQ schema if future modal sections need new dynamic render kinds

### Version Source Cleanup

The backend `/config` response is the canonical version source, the initial header label is generic, and the frontend updates the visible version label only after config loads.

Result:
- `app/config.py` defines the backend version
- `/config` exposes it to the frontend
- the UI falls back to a generic `real-time` label until config loads
