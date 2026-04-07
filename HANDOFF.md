# Phase 0 Handoff — Dedicated Mobile UI Plan

Current branch: `v1.3`
All 226 unit tests passing (`npm run test:unit`).
No uncommitted regressions — all changes are behavior-preserving.

---

## What Was Done (Phase 0 so far)

### 1. Shared state layer — `app/static/js/state.js` (new file)

All 36 module-level `let` state declarations were removed from the six browser scripts and centralised here. The module runs first (it is the first `<script>` tag after session.js in `app/templates/index.html`) and uses `Object.defineProperty` to add property descriptors on `globalThis` so every existing script can still read/write state names as plain globals — no call-site changes needed for reads/writes.

Key exports on `globalThis`:
- `APP_STATE` — the raw state object (for test harness use and debugging)
- `resetAppState()` — resets all state to defaults (used in test setup)
- `getAppState()` — returns the state object
- `getTabs()` / `setTabs(v)` — tab array accessors
- `getActiveTabId()` / `setActiveTabId(v)` — active tab ID accessors
- `getActiveTab()` — `state.tabs.find(t => t.id === state.activeTabId)`
- `getTab(id)` — `state.tabs.find(t => t.id === id)`

The 25 inline `tabs.find(t => t.id === …)` call sites across runner.js, tabs.js, output.js, app.js, and history.js were all replaced with `getTab(id)` or `getActiveTab()`.

### 2. Removed redundant `typeof fn === 'function'` guards

All the defensive `typeof fn === 'function' &&` guards were removed from app.js, runner.js, tabs.js, and welcome.js. Scripts load synchronously in a defined order; these guards were dead code. The only remaining `typeof` guards are for functions defined in later-loading scripts (e.g. `getVisibleComposerInput`, `dismissMobileKeyboardAfterSubmit`, `_maybeMountDeferredPrompt`, `syncOutputPrefixes` — all defined in app.js which loads after runner.js/output.js).

### 3. `submitCommand(rawCmd)` — DOM-free command entry point

`runCommand()` was refactored into two functions in `app/static/js/runner.js`:

```
submitCommand(rawCmd)   — shared, DOM-free, returns a signal
runCommand()            — desktop wrapper, reads cmdInput, handles cleanup
```

`submitCommand` return values:
- `'settle'` — empty input during active welcome; caller should focus only
- `true` — command submitted or blank Enter; caller should clear input + focus
- `false` — rejected (tab limit reached, shell operator denied, path denied); caller should leave input unchanged

`runCommand()` consumes the return signal:
```js
function runCommand() {
  if (runBtn && runBtn.disabled) return;
  const result = submitCommand(cmdInput.value);
  if (result === true) {
    _clearDesktopInput();
    focusComposerInputAfterRun();
    if (typeof dismissMobileKeyboardAfterSubmit === 'function') dismissMobileKeyboardAfterSubmit();
  } else if (result === 'settle') {
    focusComposerInputAfterRun();
  }
}
```

`submitCommand` has zero references to `cmdInput` or any DOM input element.

### 4. Composer and overlay interfaces

Two explicit interfaces now sit on top of the shared state layer:

- `setComposerValue(value, start, end, opts)` keeps desktop and mobile prompt inputs in sync while preserving the selection/caret.
- The desktop `cmdInput` input listener now mirrors through `setComposerValue(..., { dispatch: false })` instead of updating the mobile input inline.
- Overlay helpers in `state.js` centralise open/close behavior for kill confirmation, history panel, FAQ, options, and history-delete surfaces.
- Visibility helpers in `state.js` now also cover the search bar and recent-history row, so the desktop UI is no longer managing those toggles inline.
- The run timer and per-tab kill button visibility now also flow through shared helpers, which keeps command-session state updates in one place.
- The mobile menu open/close state now also flows through shared helpers, so the mobile UI menu is no longer managed inline in app.js.
- The MOTD wrapper visibility now also flows through a shared helper at config bootstrap time.
- The autocomplete dropdown open/close state now also flows through shared helpers, instead of app.js and autocomplete.js managing it directly.
- The history loading overlay now also flows through shared helpers, instead of history.js managing its own open/close state.
- The mobile shell / composer row visibility now also flows through a shared helper, which keeps the desktop/mobile shell swap state in one place.
- The FAQ and options overlay click handlers now use shared DOM bindings instead of re-querying the document inline in app.js.

### 5. Unit test harness — `tests/js/unit/helpers/extract.js`

- `state.js` source is read once at module load (`STATE_SRC` constant) and prepended to every eval'd script in `fromScript`, `fromDomScript`, and `fromDomScripts`.
- `fromDomScripts` accepts an optional 4th `initCode` string that runs after state.js but before the script files, with injected globals in scope. Test loaders that inject `tabs` and `activeTabId` as parameters call `setTabs(tabs); setActiveTabId(activeTabId);` in initCode so `getTab()` / `getActiveTab()` find the right objects.
- 226 unit tests across 11 files, all passing.

---

## Phase 0 Complete

The shared state layer, composer/overlay helpers, DOM binding cache, module boundary comments, and tab-node helpers are all in place. The browser modules now rely on those shared helpers instead of ad hoc prompt or overlay state.

The remaining implementation work now starts in Phase 3 with the mobile transcript and output model. Phase 2 is complete.

---

## Phase 1 Complete

The template now includes a real `mobile-shell` root plus dedicated `mobile-shell-chrome`, `mobile-shell-transcript`, `mobile-shell-composer`, and `mobile-shell-overlays` mounts, and the mobile composer dock plus mobile menu are nested inside the shell as first-class mobile-owned UI instead of as separate runtime-moved siblings. The browser can therefore activate a structured mobile shell path instead of relying only on the desktop terminal wrapper. The current mobile behavior is still preserved, and the layout logic now resolves the shell, composer, and overlay refs through one combined mobile UI helper, binds and sets up the mobile composer interactions through helper functions, caches the shared top-level controls in `dom.js`, centralises tab-node lookups behind small tab helpers, and lets the shared state layer trust those cached bindings directly, while still moving the shell sections through grouped helpers in both directions and using a grouped visibility helper for the composer/prompt swap so the boundary is easier to extend.

Phase 1 is complete. Phase 2 is complete as well. The remaining mobile work now starts in Phase 3 with the transcript and output model, followed by autocomplete, session/navigation, and overlay polish in later phases.

---

## Phase 3 In Progress

Phase 3 addresses the mobile transcript and output model. Work completed so far:

**Always-fixed composer (`app/static/css/styles.css`):**
- `#mobile-composer-host` is now `position: fixed; bottom: 0; left: 0; right: 0;` in all `body.mobile-terminal-mode` states, not only when keyboard is open
- On keyboard open (`body.mobile-terminal-mode.mobile-keyboard-open`), the rule only adjusts `bottom`, `left`, `right`, `border`, and `border-radius` — no longer needs to set `position: fixed` (already inherited)
- `body.mobile-terminal-mode .output { padding-bottom: var(--mobile-composer-height, 80px) }` replaces the old `body.mobile-keyboard-open .output { padding-bottom: 100px }` magic number and now applies at all times in mobile mode
- Chrome iOS `74px` `padding-bottom` on `#tab-panels` removed (`.output` padding covers this)

**Dynamic composer height (`app/static/js/app.js`):**
- `syncMobileComposerHeight()` — measures `mobileComposerHost.offsetHeight` and writes to `document.documentElement` CSS var `--mobile-composer-height`
- Called from `syncMobileViewportState()` (every layout sync) and from `syncMobileComposerKeyboard()` (on visualViewport resize/scroll and input focus/blur)

**Keyboard detection reliability (`app/static/js/app.js`):**
- `isMobileKeyboardOpen(offset)` now checks `offset > 40` first before checking `document.activeElement`
- This handles blur-without-dismiss: when user taps away but keyboard is still geometrically open, `visualViewport` hasn't reduced yet but the active-element check would have incorrectly returned false

**Phase 3 complete.** Timestamps and line numbers confirmed off-by-default at `app.js:998-999`. Transcript scroll testing is manual (Safari/Chrome device test).

---

## Phases 4–8 Complete

All six phases now substantially implemented. Summary of key changes:

**Phase 4 (autocomplete):** `.ac-mobile .ac-item` touch targets enlarged to 44px min-height with `flex` layout; `touchstart` handler added with `{ passive: false }` for immediate tap acceptance; row height estimate updated from 22px to 44px; `maxHeight` calculation uses `min(targetHeight, available)` without a hardcap.

**Phase 5 (session bar):** `.dot` and tab scroll arrows hidden in mobile-terminal-mode; `.tab` min-height 44px, font-size 13px; `#new-tab-btn` min-height 44px; `.tab .tab-close` hit area 20×20px.

**Phase 6 (welcome flow):** Already complete before this session.

**Phase 7 (overlays):** `#mobile-menu` converted to a fixed bottom sheet with drag handle `::before`, `env(safe-area-inset-bottom)` padding, 52px button rows; `_closeMajorOverlays()` helper enforces one-overlay-at-a-time; history panel open blurs composer; kill overlay open (`confirmKill` in runner.js) blurs composer; mobile search bar input enlarged to 16px/40px.

**Phase 8 (preferences):** FAQ and options modals become bottom sheets in mobile-terminal-mode (`border-radius: 14px 14px 0 0; width: 100%; max-height: 88svh`); options choice rows and select enlarged for touch.

**All 226 unit tests passing throughout.**

**Remaining work (Phase 9 — browser hardening):**
- Manual testing in iOS Safari and iOS Chrome
- Keyboard open/close, focus-on-tap, autocomplete tap, session create/switch/close
- Long command editing and transcript scroll with compositor always fixed
- After testing: targeted fixes for any regressions found

---

## Key Architecture Facts for Continuing Work

### Script load order (index.html)
```
session.js → state.js → utils.js → config.js → dom.js → output.js →
history.js → search.js → autocomplete.js → runner.js → tabs.js →
welcome.js → app.js
```

`state.js` must remain second (after session.js) because session.js defines `apiFetch` and `logClientError` which other modules depend on, and state.js has no dependencies.

### State property descriptor pattern
All state vars in `state.js` are backed by `Object.defineProperty` descriptors on `globalThis`. This means:
- Reads: `tabs` → `state.tabs` (transparent)
- Writes: `tabs = newVal` → `state.tabs = newVal` (transparent)
- But: `tabs.push(x)` mutates `state.tabs` in place (same reference — correct)
- And: `setTabs(newArr)` replaces `state.tabs` reference (used for reorder in syncTabOrderFromDom)

In the test harness (`new Function(...params, body)`), injected parameters **shadow** the property descriptors. So if `tabs: someArray` is injected as a parameter, reads of `tabs` in script code get the parameter, not `state.tabs`. The `initCode` workaround seeds `state.tabs` via `setTabs(tabs)` so `getTab()`/`getActiveTab()` (which read `state.tabs` directly via closure) work correctly.

### Mobile submit path (current state)
```
user taps Run  →  _mobileSubmit() in app.js
                  → reads the visible composer through getComposerValue()
                  → calls submitComposerCommand(val, { dismissKeyboard: true, focusAfterSubmit: false })
                  → submitCommand(val)
```

`_mobileSubmit` now routes through the shared visible-submit helper directly. The visible mobile composer is the source of truth for the command text, `focusVisibleComposerInput()` / `blurVisibleComposerInput()` keep visible-input focus and blur on one path, `handleComposerInputChange()` lives in the shared state layer for both desktop and mobile input updates, and the shared composer-value accessor keeps the mobile and desktop inputs aligned while the transition continues. Phase 2 is complete. Phase 3 is in progress — the always-fixed composer, dynamic height variable, and keyboard detection reliability improvements are done.

### Test harness pattern for new test files

If adding a test for a script that uses `tabs`/`activeTabId`:

```js
import { fromDomScripts } from './helpers/extract.js'

function loadFns({ tabs = [...], activeTabId = 'tab-1', ...otherGlobals } = {}) {
  return fromDomScripts(
    ['app/static/js/your-script.js'],
    {
      tabs,           // still needed for direct tabs.length etc. in scripts
      activeTabId,    // still needed for direct reads in scripts
      ...otherGlobals,
    },
    `{ exportedFn1, exportedFn2 }`,
    'setTabs(tabs); setActiveTabId(activeTabId);'  // seeds state.tabs for getTab()/getActiveTab()
  )
}
```

The `initCode` string (4th arg) runs after state.js, before your script, with injected globals in scope.

### Running tests
```bash
npm run test:unit        # vitest run (all 226 unit tests)
npm run test:unit:watch  # vitest watch mode
```

No e2e tests need to be run for Phase 0 changes — all Phase 0 work is behavior-preserving refactoring covered by unit tests.

---

## Files Changed in Phase 0

| File | Change |
|------|--------|
| `app/static/js/state.js` | **new** — shared state layer |
| `app/static/js/runner.js` | submitCommand extracted, getTab/getActiveTab, _clearDesktopInput helper |
| `app/static/js/tabs.js` | setTabs/setActiveTabId at reassignment sites, getTab everywhere, typeof guards removed |
| `app/static/js/app.js` | getActiveTab, typeof guards removed |
| `app/static/js/output.js` | getTab everywhere |
| `app/static/js/history.js` | getTab, state vars removed |
| `app/static/js/welcome.js` | state vars removed, typeof guards removed |
| `app/static/js/autocomplete.js` | state vars removed |
| `app/static/js/search.js` | state vars removed |
| `app/templates/index.html` | `<script src="/static/js/state.js">` added (second script tag) |
| `tests/js/unit/helpers/extract.js` | STATE_SRC cached, initCode param added to fromDomScripts |
| `tests/js/unit/runner.test.js` | submitCommand exported + 6 return-contract tests, welcomeActive param, requestWelcomeSettle stub |
| `tests/js/unit/tabs.test.js` | tabs/activeTabId removed from injected globals, getTabs()/getActiveTabId() in return exprs, stubs |
| `tests/js/unit/app.test.js` | initCode, stubs for setupTabScrollControls/hydrateCmdHistory/mountShellPrompt/unmountShellPrompt |
| `tests/js/unit/output.test.js` | initCode |
| `tests/js/unit/welcome.test.js` | stubs for unmountShellPrompt/logClientError |
| `tests/js/unit/autocomplete.test.js` | ac state vars moved to injected globals |
