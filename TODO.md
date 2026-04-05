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

#### Remaining
- improve inline selection visibility for advanced keyboard flows
- consider adding additional readline-like shortcuts (`Ctrl+W` done; evaluate `Ctrl+U`, `Ctrl+K`, `Alt+B/F`)
- run a focused post-refactor UX pass for mobile long-command editing

#### Risks
- keyboard/focus edge cases around hidden input + rendered caret
- mobile virtual keyboard behavior differences by browser

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
- keep bad-path tests for welcome interruption, history restore latency, and autocomplete placement regressions
- continue validating no-output action toasts and permalink/full-output consistency paths
