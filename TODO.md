# TODO

## Status

- Release line: `v1.3` (unreleased)
- Current focus: No active refactor work
- Last major milestone completed: Shell-Style Input Refactor

---

## Open TODOs

### Follow-ups

- Keep the hint rotation running until interrupted, on both the main welcome and the mobile welcome.
- Rename the synthetic `keys` command to something clearer and more obvious.
- Add a few more snarky easter-egg comments for `sudo`, `rm -fr /`, and `reboot`.
- Add subtle section headers above the recommended commands and hints on the main welcome, and carry the same treatment through to mobile hints.

---

## Completed

### Shell-Style Input Refactor

- ~~Shared state, desktop/mobile composer splitting, the dedicated mobile shell, transcript/output layout, autocomplete, session/history navigation, welcome flow, overlays, and browser hardening are all in place.~~
- ~~The remaining mobile work now lives in Phase 10 cleanup and the follow-up bucket above.~~
- ~~Unit coverage already in place: `tests/js/unit/app.test.js`, `tests/js/unit/autocomplete.test.js`, `tests/js/unit/history.test.js`, `tests/js/unit/runner.test.js`, `tests/js/unit/tabs.test.js`, `tests/js/unit/welcome.test.js`.~~
- ~~Playwright coverage already in place: `tests/js/e2e/mobile.spec.js`, `tests/js/e2e/share.spec.js`, `tests/js/e2e/kill.spec.js`, `tests/js/e2e/tabs.spec.js`.~~

### FAQ Single Source Of Truth

- ~~Built-in FAQ entries now live in the backend alongside custom `faq.yaml` entries, and `/faq` is the canonical source for both the modal and terminal `faq` helper output.~~
- ~~Result: rich HTML in modal, plain text in `faq` helper command.~~
- ~~Follow-up: keep modal-only `answer_html` content aligned with the plain-text `answer` used by the `faq` helper command, and extend the same backend FAQ schema if future modal sections need new dynamic render kinds.~~

### Version Source Cleanup

- ~~The backend `/config` response is the canonical version source, the initial header label is generic, and the frontend updates the visible version label only after config loads.~~
- ~~Result: `app/config.py` defines the backend version, `/config` exposes it to the frontend, and the UI falls back to a generic `real-time` label until config loads.~~
