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
- terminal-style autocomplete placement (above/below)
- app-safe keyboard shortcuts for tab lifecycle and tab actions
- readline-style editing for `Ctrl+W`, `Ctrl+U`, `Ctrl+K`, `Alt/Option+B`, and `Alt/Option+F`
- `keys` helper command plus FAQ/README shortcut documentation
- macOS-friendly `Option` shortcut handling and E2E coverage

#### Remaining
- improve inline selection visibility for advanced keyboard flows
- keep the `keys` helper command, FAQ entry, and README shortcut section aligned as bindings ship
- add a user options modal for timestamps, line numbers, and other preferences with cookie persistence
- add phase 2 for tab drag reorder: mobile touch-and-drag behavior
- research permalink output presentation for line numbers/timestamps when they were enabled at save time
- run a focused post-refactor UX pass for mobile long-command editing

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
- shipped: `Alt/Option+B` / `Alt/Option+F` move backward / forward by word
- remaining: consider `Ctrl+A`, `Ctrl+E`, yank/kill-ring behavior, and additional shell-native editing keys

Helper-command plan:
- `keys` is now the dedicated shortcut-discovery helper command
- keep `keys` printing a `Current shortcuts:` section for shipped behavior
- keep `keys` printing a `Planned shortcuts:` section while rollout is incomplete
- keep the note that browser-native combos like `Ctrl/Cmd+T` and `Ctrl/Cmd+W` remain environment-dependent fallbacks

---

### 2) FAQ Single Source Of Truth

#### Problem
Built-in FAQ content still has split ownership across backend data and modal HTML presentation.

#### Goal
Use one canonical backend FAQ dataset and render:
- rich HTML in modal
- plain text in `faq` helper command

#### Next Steps
- define canonical FAQ schema and renderer contract
- move built-in FAQ content out of hard-coded modal HTML
- update `/faq` response semantics and tests for merged behavior

---

### 3) Version Source Cleanup

#### Problem
Version string is still duplicated (`backend config`, frontend fallback, static header fallback).

#### Goal
Minimize manual version touchpoints during release.

#### Next Steps
- keep backend version canonical
- keep frontend fallback generic or generated
- document exact release-step expectations

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
- add coverage for permalink rendering options tied to saved timestamp/line-number state
- keep bad-path tests for welcome interruption, history restore latency, and autocomplete placement regressions
- continue validating no-output action toasts and permalink/full-output consistency paths
