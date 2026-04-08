# TODO

## Open TODOs

### Phase 1: Trust Boundary And Request Identity

Implement an explicit trusted-proxy client IP resolver and use it everywhere the app currently derives request identity.

1. Add a trusted-proxy config surface in [app/conf/config.yaml](/Users/nona/repos/shell.darklab.sh/app/conf/config.yaml)
   - define one setting for trusted proxy CIDRs or IPs
   - keep the default safe by not trusting forwarded headers unless the request comes from a configured proxy
   - document the operator expectation for reverse-proxy deployments
2. Add a single resolver helper in [app/app.py](/Users/nona/repos/shell.darklab.sh/app/app.py)
   - if `remote_addr` is not in a trusted proxy range, ignore `X-Forwarded-For`
   - if it is trusted, parse the forwarded chain and choose the real client IP
   - if the header is malformed or empty, fall back to `remote_addr`
3. Replace all direct request-identity lookups with the shared resolver
   - rate limiting keys
   - request logging fields
   - any helper that scopes history or limiter buckets
4. Keep local development and tests practical
   - allow direct local requests to work without a proxy
   - keep the existing test helpers able to isolate limiter buckets when needed
   - avoid special-casing browser tests outside the backend resolver
5. Add regression coverage for the trust boundary
   - direct client requests cannot spoof `X-Forwarded-For`
   - trusted proxy requests still honor valid forwarded chains
   - malformed forwarded chains fall back safely
   - existing rate-limit and request-log paths still see the resolved client IP
6. Update docs after the implementation lands
   - explain when forwarded headers are honored
   - explain the trusted-proxy deployment assumption
   - note the fallback behavior for local dev and tests

### Phase 2: Backend Route Decomposition

- Break [app/app.py](/Users/nona/repos/shell.darklab.sh/app/app.py) into smaller backend modules or Blueprints:
  - content/config routes: `/config`, `/allowed-commands`, `/faq`, `/autocomplete`, `/welcome*`
  - run/execution routes: `/run`, `/kill`
  - history/share routes: `/history*`, `/share*`
  - asset/ops routes: `/vendor/*`, `/health`, `/favicon.ico`
- Move route-adjacent helpers out of `app.py` where it makes the boundaries clearer:
  - preview/full-output shaping
  - synthetic run response helpers
  - shared history/permalink fetch helpers
- Keep the Flask app factory/bootstrap path simple:
  - logging setup
  - limiter initialization
  - blueprint registration
- Preserve current route behavior exactly while refactoring:
  - response formats
  - status codes
  - rate limits
  - SSE streaming behavior
- Add or keep focused tests around any moved route logic so the split is structural, not behavioral

### Phase 3: Frontend Controller Split

- Decompose [app/static/js/app.js](/Users/nona/repos/shell.darklab.sh/app/static/js/app.js) into feature-oriented modules:
  - bootstrap/config loading
  - keyboard shortcuts and prompt interactions
  - overlays/modals
  - FAQ rendering
  - mobile viewport/composer wiring
  - search-bar and terminal-bar controls
- Identify the current composition root responsibilities in `app.js` and leave only orchestration there
- Keep browser behavior stable during the split:
  - welcome flow
  - mobile keyboard handling
  - overlay open/close and refocus behavior
  - FAQ loading and command-chip behavior
- Add or update unit tests around the extracted modules before removing the original code paths

### Phase 4: Reduce Global-State And Script-Order Coupling

- Refactor [app/static/js/state.js](/Users/nona/repos/shell.darklab.sh/app/static/js/state.js) toward a smaller store boundary:
  - reduce direct property exposure on `window`
  - prefer explicit getter/setter APIs over broad writable globals
  - separate DOM-focused helpers from app-state storage
- Review which globals are true shared state versus convenience wrappers that can move into feature modules
- Reduce dependence on classic-script load ordering across:
  - `state.js`
  - `tabs.js`
  - `history.js`
  - `runner.js`
  - `app.js`
- Revisit the unit-test extraction strategy in [tests/js/unit/helpers/extract.js](/Users/nona/repos/shell.darklab.sh/tests/js/unit/helpers/extract.js):
  - avoid leaning harder on `new Function(...)` and concatenated script execution as modules are split
  - keep tests focused on public behavior, not on the current script-bundle shape
- Decide whether the next step is:
  - incremental ES module adoption, or
  - a tighter non-module global boundary with fewer exported names

### Phase 5: DOM Construction And Template Cleanup

- Replace repeated `innerHTML`-built UI fragments with more maintainable structures where the payoff is high:
  - history entries in [app/static/js/history.js](/Users/nona/repos/shell.darklab.sh/app/static/js/history.js)
  - tab headers and terminal action rows in [app/static/js/tabs.js](/Users/nona/repos/shell.darklab.sh/app/static/js/tabs.js)
  - FAQ limits/allowed-command dynamic sections in [app/static/js/app.js](/Users/nona/repos/shell.darklab.sh/app/static/js/app.js)
- Prefer one of:
  - small DOM builder helpers, or
  - `<template>` elements in [app/templates/index.html](/Users/nona/repos/shell.darklab.sh/app/templates/index.html)
- Remove avoidable inline styles from:
  - [app/templates/index.html](/Users/nona/repos/shell.darklab.sh/app/templates/index.html)
  - runtime HTML snippets in JS
  - built-in FAQ HTML in [app/commands.py](/Users/nona/repos/shell.darklab.sh/app/commands.py)
- Move presentation details into CSS classes where possible so the theme-selector styling stays centralized
- Keep the behavior and semantics unchanged:
  - action button labels
  - modal copy
  - ARIA labels and focus behavior

### Phase 6: Search Highlighting Hardening

- Rework [app/static/js/search.js](/Users/nona/repos/shell.darklab.sh/app/static/js/search.js) so it no longer rewrites serialized `innerHTML`
- Make search highlighting operate on safer primitives:
  - text nodes, or
  - raw output entries before DOM rendering, or
  - a dedicated highlight layer
- Preserve the current feature set:
  - plain-text and regex search
  - case-sensitive toggle
  - current-match navigation and scroll-into-view
- Add regression coverage for mixed-content lines:
  - prompt lines
  - ANSI-rendered spans
  - line numbers / timestamp prefixes
  - lines containing markup-bearing helper elements

### Phase 7: Content/Presentation Separation

- Simplify the built-in FAQ data in [app/commands.py](/Users/nona/repos/shell.darklab.sh/app/commands.py):
  - reduce inline style usage inside `answer_html`
  - keep content data-oriented where possible
  - reserve richer markup only for cases that actually need it
- Rework [app/fake_commands.py](/Users/nona/repos/shell.darklab.sh/app/fake_commands.py) synthetic command dispatch from a long `if`/`elif` chain into a handler registry or dispatch map
- Review other config/content surfaces for similar mixing:
  - help text
  - shortcuts output
  - operator-editable config-driven content
- Keep terminal output and UI output aligned while reducing duplication or style leakage

### Phase 8: CSS Surface Cleanup

- Split [app/static/css/styles.css](/Users/nona/repos/shell.darklab.sh/app/static/css/styles.css) into clearer sections or files by surface:
  - shell/transcript
  - mobile shell
  - history/search/FAQ/options overlays
  - permalink/export-specific rules
- Remove remaining style drift between:
  - static template markup
  - JS-generated UI fragments
  - permalink/export surfaces
- Keep theme tokens centralized so light/dark fixes do not require scattered selector overrides
- Add a light pass over selector specificity and duplication once the structural split is in place

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
