# TODO

## Open TODOs


### Phase 9: Documentation And Test Follow-Through

- After each cleanup phase, update:
  - [README.md](/Users/nona/repos/shell.darklab.sh/README.md)
  - [ARCHITECTURE.md](/Users/nona/repos/shell.darklab.sh/ARCHITECTURE.md)
  - [tests/README.md](/Users/nona/repos/shell.darklab.sh/tests/README.md)
  - release-note drafts under `/tmp/` when the work is user-visible
- Keep the architecture docs honest about:
  - trusted proxy assumptions
  - module boundaries
  - asset loading behavior
  - export/permalink rendering paths
- Recheck suite counts and appendix entries only when tests are actually added or removed

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Highest-Value Ideas

- **Redacted permalinks and exports**
  - Allow masking IPs, hostnames, tokens, cookies, or regex-matched values before creating a permalink or export.
  - Strong fit for a security-oriented sharing tool.

- **Saved command presets**
  - Let users save named command templates beyond history/starred entries.
  - Better for repeat workflows like DNS checks, HTTP triage, or common scan recipes.

- **Richer history filtering and search**
  - Add filtering by command root, exit code, starred status, date, and full-output availability.
  - Current history is useful, but it will become harder to navigate as usage grows.

- **Operator diagnostics page/helper**
  - Show installed binaries, missing tools, wordlist paths, Redis/SQLite health, asset source status, and retention settings.
  - Useful for deployment debugging and instance validation.

- **Per-tab draft input persistence**
  - Keep unrun composer text separate per tab.
  - Makes tabs feel more like real working contexts.

- **Context-aware autocomplete**
  - Move beyond a flat suggestion list and tailor completions by command root and prior tokens.
  - Especially useful for long scanner commands with many flags.

### Medium-Size Product Ideas

- **Parameterized command forms**
  - Add optional structured builders for common tools like `curl`, `dig`, `nmap`, and `ffuf`.
  - Keep raw-shell usage intact while making common tasks easier.

- **Better long-run continuity**
  - Let users reconnect to running commands after a reload instead of only finding them later in history.

- **Run comparison**
  - Compare two runs side by side, especially for repeated scans or before/after checks.

- **Share annotations**
  - Add optional title, note, and tags to a snapshot permalink.

- **Additional export formats**
  - Add Markdown and JSONL export in addition to `.txt` and themed `.html`.

- **Snapshot metadata block**
  - Include command, exit code, duration, timestamp mode, line-number mode, truncation state, and app version in shared/exported artifacts.

- **Command recall improvements**
  - Add reverse-history search or a shell-style history search flow inside the prompt.

- **Better output navigation**
  - Jump to top/bottom, jump between warnings/errors, sticky command header for long runs, and optional output collapsing.

### Mobile-Focused Ideas

- **More mobile-native history actions**
  - Larger tap targets and less drawer churn for common actions like copy command and permalink.

- **Mobile share flow**
  - Better native share-sheet integration where the platform allows it.

- **Mobile keyboard enhancements**
  - Optional compact edit presets, faster cursor movement, or gesture-friendly editing helpers.

### Safety / Policy Ideas

- **Output redaction rules**
  - Add instance-level masking rules before persistence/share for secrets, tokens, or internal identifiers.

- **Richer audit trail**
  - Optional logging around share creation, deletions, and run access patterns.

- **Per-command policy metadata**
  - Allowlist entries could carry metadata like `risky`, `slow`, `high-output`, or `full-output recommended`.
  - The UI could surface this in help, warnings, or command builders.

### Content / Guidance Ideas

- **Starter workflows**
  - Curated task-oriented entry points such as DNS troubleshooting, TLS checks, quick HTTP triage, or subdomain discovery.

- **Tool-specific guidance**
  - Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `wapiti`, or `nuclei`.

- **Task-driven welcome hints**
  - Make the onboarding flow suggest real tasks, not just commands and hints.

### Architecture-Driven Product Bets

- **Structured command catalog**
  - Move from plain-text allowlist-only metadata toward a richer command catalog model.
  - This would unlock better autocomplete, command forms, grouped help, and policy hints.

- **Structured output model**
  - Preserve richer line/event metadata consistently for all runs.
  - This would improve search, comparison, redaction, exports, and permalink fidelity.

- **Plugin-style helper command registry**
  - Turn the fake-command layer into a cleaner extension surface for future app-native helpers.

---

## Completed

### Phase 7: Content/Presentation Separation

- Replaced the three inline `style="color:var(--...)"` attributes and the `<ul style="...">` layout attribute in the built-in FAQ `answer_html` entries with CSS classes (`.faq-link` for green documentation links, `.faq-kill-verb` for the red Kill label). The keyboard-shortcuts `<ul>` inline style was removed entirely; the existing `.faq-a ul` rule already handles list layout.
- Replaced the 30-branch `if/elif` chain in `execute_fake_command()` with a module-level `_FAKE_COMMAND_DISPATCH` dict of lambdas normalised to `(cmd, sid) -> list[dict]`. The public function body is four lines; adding a new helper requires one dict entry.
- Reviewed all other config/content surfaces (help text, shortcuts output, MOTD renderer, operator-editable YAML assets, FAQ limits builder): no inline styles or presentation mixing found.

### Backend Route Decomposition

`app/app.py` has been split into Flask Blueprints under `app/blueprints/`: `assets.py` (vendor assets, favicon, health check), `content.py` (index, config, themes, FAQ, autocomplete, welcome), `run.py` (execution and kill with run-output helpers), and `history.py` (history and share with preview-output helpers). Shared per-request utilities live in `app/helpers.py` (trusted-proxy IP resolution, session-ID extraction) and the Flask-Limiter singleton in `app/extensions.py`. `app/app.py` is now a thin factory. All route behavior, response formats, status codes, rate limits, and SSE streaming are unchanged. Route test patches were updated to target blueprint namespaces.

### Frontend Controller Split

`app/static/js/app.js` now keeps the shared UI helpers, while the page bootstrap, config loading, top-level button wiring, search/history/FAQ orchestration, and mobile composer setup live in `app/static/js/controller.js`. The browser template and JS unit loader both load the controller after `app.js` so the classic-script globals stay intact. The controller split keeps the welcome flow, mobile keyboard handling, overlay open/close behavior, FAQ loading, and command-chip behavior stable.

Validation:
- `python3 -m pytest tests/py/test_routes.py -q`
- `npx vitest run tests/js/unit/app.test.js`
- `npx vitest run tests/js/unit/runner.test.js`
- `npx vitest run tests/js/unit/*.test.js`

### Global-State And Script-Order Coupling

`app/static/js/state.js` now owns the shared store boundary and explicit accessors for tabs and active-tab state, while DOM-facing helpers moved into `app/static/js/ui_helpers.js`. The browser template loads `ui_helpers.js` immediately after `dom.js`, and `tests/js/unit/helpers/extract.js` mirrors that order so the jsdom harness sees the same classic-script globals as production. That keeps the non-module browser architecture intact while reducing the number of implicit dependencies on script order.

Validation:
- `python3 -m pytest tests/js/unit/app.test.js tests/js/unit/tabs.test.js tests/js/unit/runner.test.js -q`
- `npx vitest run tests/js/unit/*.test.js`
- `node --check app/static/js/state.js`
- `node --check app/static/js/ui_helpers.js`
- `node --check tests/js/unit/helpers/extract.js`

### DOM Construction And Template Cleanup

The repeated `innerHTML` fragments in `app/static/js/history.js`, `app/static/js/tabs.js`, and the FAQ limits / allowed-command sections in `app/static/js/app.js` now use direct DOM construction instead of stitched HTML strings. The browser template also uses class-based modal and hidden-state wrappers for the shell chrome, which removes the remaining avoidable inline layout styles without changing labels, copy, or accessibility behavior.

Validation:
- `npx vitest run tests/js/unit/app.test.js tests/js/unit/history.test.js tests/js/unit/tabs.test.js`
- `npx vitest run tests/js/unit/*.test.js`

### Search Highlighting Hardening

`app/static/js/search.js` now highlights matches by walking text nodes and cloning the line structure instead of rewriting serialized `innerHTML`. That keeps mixed-content lines intact, preserves prompt/helper markup, and still supports plain-text search, regex mode, case sensitivity, current-match navigation, and scroll-into-view.

Validation:
- `npx vitest run tests/js/unit/search.test.js`
- `npx vitest run tests/js/unit/*.test.js`

### Trust Boundary And Request Identity

`trusted_proxy_cidrs` is now a config key in `app/conf/config.yaml`. The `get_client_ip()` helper in `app/helpers.py` only honors `X-Forwarded-For` when the direct peer IP falls within those CIDRs; all other requests use `remote_addr` directly. Rate-limiting and all request-log fields use this resolver. Regression coverage lives in `test_routes.py`. Docs updated in `README.md` and `ARCHITECTURE.md`.

### Runtime Theme Selector

The implementation now uses named YAML themes under `app/conf/themes/`, a filename-based `default_theme` in `app/conf/config.yaml`, and the baked-in dark fallback palette in `app/config.py` when a selected theme cannot be resolved.

The selector itself is a dedicated preview-card modal launched from the top-bar theme button. Theme metadata is explicit and operator-controlled: `label:` provides the friendly card name, `group:` controls the modal section header, and `sort:` controls ordering within the grouped preview grid. The modal applies the chosen theme live, persists it in `localStorage` / cookies, and keeps permalinks and downloadable HTML exports aligned with the selected variant.

Theme resolution follows the documented order:

1. `localStorage.theme`
2. `default_theme` from `app/conf/config.yaml`
3. baked-in dark fallback palette

Mobile uses the same selector with a full-screen chooser and a two-column preview layout on wider phones. The theme examples in `app/conf/theme_dark.yaml.example` and `app/conf/theme_light.yaml.example` are copyable templates only; the runtime selector reads the registry in `app/conf/themes/`.

---

### Shell-Style Input Refactor

- Shared state, desktop/mobile composer splitting, the dedicated mobile shell, transcript/output layout, autocomplete, session/history navigation, welcome flow, overlays, and browser hardening are complete.
- Unit coverage in place: `tests/js/unit/app.test.js`, `tests/js/unit/autocomplete.test.js`, `tests/js/unit/history.test.js`, `tests/js/unit/runner.test.js`, `tests/js/unit/tabs.test.js`, `tests/js/unit/welcome.test.js`.
- Playwright coverage in place: `tests/js/e2e/mobile.spec.js`, `tests/js/e2e/share.spec.js`, `tests/js/e2e/kill.spec.js`, `tests/js/e2e/tabs.spec.js`.

### Permalink Page Template Refactor

- Split the live permalink rendering into Jinja templates:
  - a shared permalink base/layout template for header, action row, output mount, and toast
  - a small error template for missing `/share/<id>` and `/history/<run_id>` pages
- Move reusable permalink page chrome and theme rules into shared CSS instead of maintaining the full live-page stylesheet inside `app/permalinks.py`.
- Keep permalink pages server-rendered and self-contained at request time; do not turn them into client-fetched shells.
- Extract the repeated permalink-page data shaping in `permalinks.py` into smaller helpers:
  - theme selection
  - line normalization / prompt-echo injection
  - timestamp-availability detection
  - action-button / extra-action context building
- Preserve the current behavior exactly:
  - current theme parity with the main shell
  - line-number and timestamp toggles
  - copy / `save .txt` / `save .html` actions
  - `view json` and back-to-shell links
  - snapshot/run permalink title, metadata, expiry note, and prompt rendering
- Keep the downloadable/exported HTML path fully rendered and portable:
  - do not make saved `.html` depend on live app routes after download
  - keep embedded fonts / inline CSS / inline JS decisions explicit for the export path, even if the live permalink page moves to shared templates and shared CSS
- Keep vendor asset behavior intact for the live page:
  - local `ansi_up` browser build
  - local vendor font routes for the hosted permalink page
- Add regression coverage for both permalink classes and both render paths:
  - `/share/<id>` and `/history/<run_id>`
  - missing/expired permalink error pages
  - live page theme parity and toggle availability
  - exported `.html` output staying portable and free of external asset fetches
- Refresh docs and release notes to describe the template split, the remaining inline export path, and any shared style changes.

### FAQ Single Source Of Truth

- Built-in FAQ entries now live in the backend alongside custom `faq.yaml` entries, and `/faq` is the canonical source for both the modal and terminal `faq` helper output.
- Result: rich HTML in modal, plain text in `faq` helper command.
- Follow-up: keep modal-only `answer_html` content aligned with the plain-text `answer` used by the `faq` helper command, and extend the same backend FAQ schema if future modal sections need new dynamic render kinds.

### Version Source Cleanup

- The backend `/config` response is the canonical version source, the initial header label is generic, and the frontend updates the visible version label only after config loads.
- Result: `app/config.py` defines the backend version, `/config` exposes it to the frontend, and the UI falls back to a generic `real-time` label until config loads.

### Welcome / Helper Follow-ups

- Keep the hint rotation running until interrupted, on both the main welcome and the mobile welcome.
- Create separate app hints for mobile that are mobile specific.
- Add a few more snarky easter-egg comments for `sudo`, `rm -fr /`, and `reboot`.
- Add subtle section headers above the recommended commands and hints on the main welcome, and carry the same treatment through to mobile hints.
