# TODO

## Status

- Release line: `v1.3` (unreleased)
- Current focus: No active refactor work
- Last major milestone completed: Shared HTML Export Styling Cleanup

---

## Open TODOs

No open follow-ups.

---

## Completed

### Shell-Style Input Refactor

- ~~Shared state, desktop/mobile composer splitting, the dedicated mobile shell, transcript/output layout, autocomplete, session/history navigation, welcome flow, overlays, and browser hardening are all in place.~~
- ~~The remaining mobile work now lives in Phase 10 cleanup and the follow-up bucket above.~~
- ~~Unit coverage already in place: `tests/js/unit/app.test.js`, `tests/js/unit/autocomplete.test.js`, `tests/js/unit/history.test.js`, `tests/js/unit/runner.test.js`, `tests/js/unit/tabs.test.js`, `tests/js/unit/welcome.test.js`.~~
- ~~Playwright coverage already in place: `tests/js/e2e/mobile.spec.js`, `tests/js/e2e/share.spec.js`, `tests/js/e2e/kill.spec.js`, `tests/js/e2e/tabs.spec.js`.~~

### Permalink Page Template Refactor

- ~~Split the live permalink rendering into Jinja templates:~~
  - ~~a shared permalink base/layout template for header, action row, output mount, and toast~~
  - ~~a small error template for missing `/share/<id>` and `/history/<run_id>` pages~~
- ~~Move reusable permalink page chrome and theme rules into shared CSS instead of maintaining the full live-page stylesheet inside `app/permalinks.py`.~~
- ~~Keep permalink pages server-rendered and self-contained at request time; do not turn them into client-fetched shells.~~
- ~~Extract the repeated permalink-page data shaping in `permalinks.py` into smaller helpers:~~
  - ~~theme selection~~
  - ~~line normalization / prompt-echo injection~~
  - ~~timestamp-availability detection~~
  - ~~action-button / extra-action context building~~
- ~~Preserve the current behavior exactly:~~
  - ~~current theme parity with the main shell~~
  - ~~line-number and timestamp toggles~~
  - ~~copy / `save .txt` / `save .html` actions~~
  - ~~`view json` and back-to-shell links~~
  - ~~snapshot/run permalink title, metadata, expiry note, and prompt rendering~~
- ~~Keep the downloadable/exported HTML path fully rendered and portable:~~
  - ~~do not make saved `.html` depend on live app routes after download~~
  - ~~keep embedded fonts / inline CSS / inline JS decisions explicit for the export path, even if the live permalink page moves to shared templates and shared CSS~~
- ~~Keep vendor asset behavior intact for the live page:~~
  - ~~local `ansi_up` browser build~~
  - ~~local vendor font routes for the hosted permalink page~~
- ~~Add regression coverage for both permalink classes and both render paths:~~
  - ~~`/share/<id>` and `/history/<run_id>`~~
  - ~~missing/expired permalink error pages~~
  - ~~live page theme parity and toggle availability~~
  - ~~exported `.html` output staying portable and free of external asset fetches~~
- ~~Refresh docs and release notes to describe the template split, the remaining inline export path, and any shared style changes.~~

### FAQ Single Source Of Truth

- ~~Built-in FAQ entries now live in the backend alongside custom `faq.yaml` entries, and `/faq` is the canonical source for both the modal and terminal `faq` helper output.~~
- ~~Result: rich HTML in modal, plain text in `faq` helper command.~~
- ~~Follow-up: keep modal-only `answer_html` content aligned with the plain-text `answer` used by the `faq` helper command, and extend the same backend FAQ schema if future modal sections need new dynamic render kinds.~~

### Version Source Cleanup

- ~~The backend `/config` response is the canonical version source, the initial header label is generic, and the frontend updates the visible version label only after config loads.~~
- ~~Result: `app/config.py` defines the backend version, `/config` exposes it to the frontend, and the UI falls back to a generic `real-time` label until config loads.~~

### Welcome / Helper Follow-ups

- ~~Keep the hint rotation running until interrupted, on both the main welcome and the mobile welcome.~~
- ~~Create separate app hints for mobile that are mobile specific.~~
- ~~Add a few more snarky easter-egg comments for `sudo`, `rm -fr /`, and `reboot`.~~
- ~~Add subtle section headers above the recommended commands and hints on the main welcome, and carry the same treatment through to mobile hints.~~
