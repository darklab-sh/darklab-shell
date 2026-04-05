# TODO

## Overview

This file tracks follow-up work and planned refactors after the `v1.2` release.

Current priority areas:
- shell-style input refactor
- FAQ source-of-truth cleanup
- version-source cleanup

---

## 1. Shell-Style Input Refactor

### Goal

Remove the visible standalone input box and make the terminal itself feel like the command-entry surface, while preserving:
- the current backend `/run` model
- autocomplete and Tab completion
- history recall
- welcome-flow interactions
- mobile usability

### Recommended Technical Approach

Keep a real input element internally, but hide it from the visible layout.

Use:
- a hidden real `<input>` or `<textarea>` for:
  - browser focus
  - keyboard input
  - mobile virtual keyboard support
  - accessibility
- a rendered in-terminal prompt line that mirrors the hidden input value

Avoid:
- `contenteditable` as the primary command-entry surface

Reason:
- lower implementation risk
- better mobile behavior
- easier autocomplete reuse
- easier testing
- fewer caret and selection bugs

### Scope

Backend impact should be low:
- `/run`, `/kill`, history, permalinks, fake commands, and welcome logic can remain mostly unchanged

Frontend impact is moderate to high:
- prompt rendering
- keyboard handling
- autocomplete anchoring
- scroll behavior
- history navigation
- tab restore behavior
- mobile focus behavior

### Implementation Plan

#### Phase 1: Visual Embed

Objective:
- make the terminal visually own command entry without changing the underlying command model

Tasks:
- keep the current real input logic
- remove the visible input box from the layout
- render a terminal prompt row at the bottom of the active terminal output
- mirror the hidden input value into that prompt row
- keep the existing run button behavior initially

Notes:
- clicking the terminal should focus the hidden input
- the prompt should visually match the rest of the terminal
- the prompt row should remain visible and stable while output scrolls

Risk:
- low to moderate

#### Phase 2: Inline Interaction

Objective:
- make the rendered prompt feel like the actual command-entry surface

Tasks:
- clicking anywhere in the terminal focuses the hidden input
- render the caret in the inline prompt
- visually edit command text in place through the mirrored prompt
- anchor autocomplete to the inline prompt rather than the old visible input area

Notes:
- keep the hidden input as the source of truth
- the prompt line is a renderer, not the editable DOM source
- keep current Tab completion behavior, but reposition the suggestion panel

Risk:
- moderate

#### Phase 3: Shell-Like Editing

Objective:
- make command entry feel closer to a shell than a form field

Tasks:
- refine left/right cursor behavior
- support Home/End cleanly
- preserve blank-input Up/Down history recall
- preserve typed-draft restore during history navigation
- optionally add limited shell-style shortcuts later:
  - `Ctrl+A`
  - `Ctrl+E`
  - `Ctrl+U`

Notes:
- do not add full readline behavior in the first pass
- rely on browser-native editing semantics wherever possible

Risk:
- moderate to high

#### Phase 4: Cleanup

Objective:
- remove old visible-input assumptions from the UI

Tasks:
- delete obsolete visible-input layout code
- simplify prompt wrapper CSS and DOM
- update welcome, history, and search integration to reference the shell prompt surface instead of a visible form field

Risk:
- low once earlier phases are stable

### Affected Areas

#### DOM / Layout

Likely files:
- `app/templates/index.html`
- `app/static/css/styles.css`
- `app/static/js/dom.js`

Expected work:
- add a dedicated terminal prompt render area
- remove or hide the visible command bar
- preserve focusability through the hidden input

#### Input / App Wiring

Likely files:
- `app/static/js/app.js`
- `app/static/js/runner.js`
- `app/static/js/history.js`
- `app/static/js/welcome.js`

Expected work:
- mirror hidden-input state into the inline prompt
- shift click-to-focus behavior to the terminal surface
- keep submission logic unchanged where possible
- update history restore and welcome sample loading to write into the hidden input and prompt renderer

#### Autocomplete

Expected work:
- reuse current filtering logic
- reposition the dropdown relative to the inline prompt
- keep Tab and Enter acceptance behavior stable

#### Search / History / Welcome

Expected work:
- ensure search shortcuts do not interfere with prompt focus
- preserve blank-input history recall
- preserve welcome sample click/load behavior
- preserve typing-to-settle welcome behavior

### Risks

Highest-risk areas:
1. Mobile keyboard and focus behavior
2. Caret rendering and long-command wrapping
3. Autocomplete regressions
4. Accessibility regression
5. Scroll behavior that makes the prompt feel detached from the terminal

### Constraints

For the first implementation:
- no `contenteditable`
- no attempt to emulate a full terminal editor
- no shell parsing changes
- no backend protocol changes unless a real frontend blocker appears
- do not remove the hidden real input

### Testing Plan

#### Unit Tests

Add or update tests for:
- hidden-input to inline-prompt mirroring
- click-to-focus terminal behavior
- blank-input Up/Down history navigation
- autocomplete acceptance from the inline prompt
- welcome sample click/load into the inline prompt
- typing during welcome settles the intro correctly

#### E2E Tests

Add or update tests for:
- command entry entirely through the terminal surface
- autocomplete with Tab from the inline prompt
- history restore followed by command editing
- mobile viewport focus and typing behavior
- welcome flow with the inline prompt active after settle

#### Manual Checks

Required:
- desktop Chrome/Chromium
- mobile viewport
- long command wrapping
- autocomplete panel placement
- search bar interaction
- history drawer interaction
- tab switching and command recall

### First Milestone

Deliver only this first:
- hidden real input remains
- visible old input box is removed from layout
- inline prompt mirrors hidden input value
- clicking the terminal focuses the input
- Enter still runs commands
- existing autocomplete continues to work

That should deliver most of the visual gain with the least architectural risk.

### Open Decisions

Decide before implementation:
- should the prompt be pinned to the bottom or flow as part of terminal output?
- should the run button stay visible, or should Enter become the primary-only affordance?
- should the terminal click target be the full output area or only the prompt row?
- how shell-like should editing become in the first pass?

---

## 2. FAQ Source Of Truth Cleanup

### Problem

Built-in FAQ content now exists in two places:
- backend plain-text FAQ data in `app/commands.py`
- hard-coded modal HTML in `app/templates/index.html`

Current behavior:
- the `faq` shell command uses backend FAQ data
- the modal still uses hard-coded HTML plus `/faq` for custom entries only

Risk:
- the shell `faq` output and modal FAQ can drift over time

### Goal

Create one canonical FAQ source and render it differently for:
- the modal
- the `faq` shell command

### Recommended Approach

Move built-in FAQ content fully into backend data and render it per surface:
- rich HTML rendering for the modal
- plain-text rendering for the shell command

Avoid:
- scraping modal HTML into text
- keeping two independent hard-coded copies

### Follow-Up Tasks

- define a canonical FAQ data structure
- move current built-in FAQ content into backend data
- update the modal to render from that data
- keep `/faq` semantics clear:
  - either custom-only
  - or merged built-in + custom
- update tests to cover the single-source behavior

---

## 3. Version Source Cleanup

### Problem

The app version is currently duplicated in multiple places:
- `app/config.py`
- `app/static/js/config.js`
- `app/templates/index.html`

They are aligned today, but they can drift in future releases.

### Goal

Reduce the number of manually updated version sources for future releases.

### Recommended Approach

Prefer one canonical backend version source and make the frontend/header depend on it as early as possible.

Possible follow-up options:
- keep `APP_VERSION` only in backend config and make frontend fallback version less specific
- or generate the fallback/header version from one shared build/release step

### Follow-Up Tasks

- decide whether frontend fallback version still needs a hard-coded value
- decide whether the static header should ship with a placeholder or current version
- document the release-step expectation clearly if duplication remains

---

## 4. General Follow-Up Principle

For post-`v1.2` cleanup:
- prefer single sources of truth for shared content
- keep backend behavior stable and move UI complexity to isolated frontend layers
- avoid clever terminal emulation if a simpler browser-safe approach exists
