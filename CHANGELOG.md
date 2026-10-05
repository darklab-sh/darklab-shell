# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [3.x releases](docs/changelog/3.x.md) - version 3.0.0
- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.9.2
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [3.1.2] - Unreleased

**Upgrade note:** This candidate retains the v3 access model: pseudonymous principals have stable personal workspaces, portable credentials sign browsers in, and scoped PATs authenticate API and CLI requests. Legacy `tok_` values remain intentionally invalid, and databases with retired identity schemas are rejected. Private deployments can require credentials, OIDC, or either sign-in method. Before upgrading, complete the [operator preflight](CONFIGURATION.md#upgrade-preflight), verify a working sign-in and explicit operator grant, and preserve a tested backup of the database, matching secrets key, Files, and operator configuration. These access requirements were introduced in earlier v3 releases; 3.1.2 fixes workspace identity and cleanup handling.

### Changed

- **3.1.2-rc.1 identifies this release candidate.** Application, npm, container, deployment, license-inventory, OpenAPI, and production-install expectations use the candidate version. Installation and signing examples select its exact tag.

### Fixed

- **Browser readiness and terminal confirmation tests stay reliable when startup or stream processing yields.**
  - **Root cause:** The browser helper could stop waiting before its test hooks existed. Runner unit tests could leave exit events queued against the next test's tab state, and mobile body classes could affect later focus checks.
  - **Fix:** Hook readiness uses a synchronous polling condition. Finite-stream tests wait for terminal completion, runner fixtures clean up streams and timers, and each case starts with fresh body classes.
  - **Tests:** Browser coverage holds test hooks back after the shell is ready, and runner coverage forces a stream to yield between output and exit.

- **Expired browser sessions no longer produce workspace cleanup errors or postpone maintenance.**
  - **Root cause:** A public request with a rejected browser cookie claimed the worker's cleanup interval before resolving its owner. Authentication then raised inside the cleanup block, which logged an ERROR without attempting cleanup.
  - **Fix:** Cleanup reads the cached authentication result and quietly skips rejected identities before claiming the interval. The next eligible request can run cleanup immediately. Valid owners stay excluded, genuine cleanup failures retain their ERROR traceback and five-minute retry interval, and SQLite checkpoints remain independent.
  - **Tests:** SQLite and Postgres regressions cover expired, revoked, malformed, and disabled browser identities in open and restricted profiles, public and protected responses, owner exclusions, actual expired-directory removal, retry timing, and text/GELF logging.

- **Cleanup protects the current workspace after it has been kept.**
  - **Root cause:** Cleanup derived the directory to exclude by hashing the owner id. Keeping an anonymous workspace changes its owner id but preserves its original directory, so cleanup could remove that current workspace when its activity timestamp was old.
  - **Fix:** The exclusion uses the shared workspace path resolver and its stored directory name.
  - **Tests:** SQLite and Postgres checks keep an anonymous workspace through the production service, age its directory, and verify that cleanup preserves its files while removing another expired workspace.

- **Workspace requests without an identity return an authentication response instead of a server error.**
  - **Root cause:** Open-profile requests without an anonymous identity or browser session could pass an empty owner id to preferences, starred commands, and the active Project, causing HTTP 500 responses.
  - **Fix:** Workspace helpers require an owner and return HTTP 401 with `credential_required` when none is available. Public content and open-profile run permalinks keep their optional identity behavior, including private-metadata filtering, and invalid credentials retain their specific rejection. A browser that loses its session cookie can sign in again and recover its saved workspace.
  - **Tests:** SQLite and Postgres checks cover missing and rejected identities, owner isolation, public routes and run permalinks, and sampled text/GELF warnings. Desktop and mobile browser checks cover cookie loss and recovery, including a background request starting sign-in before the test's explicit request, alongside the four-profile source/bundle qualification matrix.

---

## [3.1.1] - 2026-10-03

**Upgrade note:** This release retains the v3 access model: pseudonymous principals own personal workspaces, portable credentials sign browsers in, and scoped PATs authenticate API and CLI requests. Legacy `tok_` values are intentionally invalid, and databases with retired identity schemas are rejected. Private deployments can require credentials, OIDC, or either sign-in method over HTTPS. Operators must complete the [upgrade preflight](CONFIGURATION.md#upgrade-preflight), verify their explicit operator grant and recent browser verification, and preserve a tested backup of the database, matching secrets key, Files, and operator configuration before changing the image. These access requirements were introduced in earlier v3 releases.

### Changed

- **3.1.1 is the stable release.** Application, npm, container, deployment, license-inventory, OpenAPI, and production-install expectations use the final version. Installation and signing examples select its exact tag. The dated changelog section is included in the published-text integrity baseline.

### Fixed

- **Mobile chart scrolling tests work on Linux CI runners as well as macOS.** They send native touch start, move, and end events while still checking that charts scroll and swipes don't open runs or History.

- **Signing in stays on the restored workspace when an older request finishes late.** Authentication errors from an anonymous request or a previous browser session no longer interrupt a successful sign-in, including when access changes across tabs.

- **Mobile Status Monitor charts stay readable and let you scroll without opening runs or History.** Constellation and Command Territory legends wrap above their charts. Tap a star or territory to preview it, then use **Open run** or **View history** in the pop-up. Desktop interactions stay the same.

- **Mobile sign-in avoids zooming when you tap the credential field.** The field uses 16px text on small screens, including when verifying operator access.

- **JavaScript dependencies resolve the reported npm security advisories.** The dependency tree uses patched brace-expansion, DOMPurify, fast-uri, js-yaml, Markdown parsing, and Undici releases. Markdownlint's patch release supplies its corrected dependencies without the old overrides. Markdown and CSS linting use a reviewed local `braces` patch that bounds recursive nesting for GHSA-vfj7-8cjw-p6xm. The audit command verifies that patched dependency with security regressions before running the existing high/critical registry audit.

- **Credential lifecycle checks stay valid as the calendar advances.** The workspace-stability test uses a future expiry relative to its run date, preserving the final-credential lockout checks.

---

## [3.1.0] - 2026-09-21

**Upgrade note:** Diagnostics, Audit log, and Operator settings now require a verified browser session and an explicit principal grant in every access profile, including `open`. To retain operator access, sign in and grant an active principal access using the [operator setup instructions](CONFIGURATION.md#operator-settings-console). Update audit bookmarks and export links from `/diag/audit` and `/diag/audit/export` to `/audit` and `/audit/export`; the old routes do not redirect. Rename `diagnostics_allowed_cidrs` to `metrics_allowed_cidrs` before upgrading; the removed key is ignored and no longer enables metrics scrapes. Complete the [operator upgrade preflight](CONFIGURATION.md#upgrade-preflight) and keep a verified backup before changing the image.

### Added

- **Operators can inspect settings, diagnostics, and audit activity through one protected console.** Desktop and mobile navigation connects the three read-only pages.
  - **Settings:** Search and filter reviewed values by group, source, and warning. Filter links survive reloads and verification; refresh preserves expanded details, focus, and position. Cards distinguish loaded values, accepted inputs, host guidance, and unobserved deployment defaults across all themes.
  - **Snapshots and privacy:** Each snapshot identifies the serving worker, the process that loaded configuration, and its load time. Sensitive settings show approved summaries or withheld markers; diagnostics distinguishes withheld values from unset ones. Private responses and access checks clear stale page data after authority is lost.
  - **Grants and verification:** Browser sessions in every access profile need an explicit principal grant and recent same-account credential or signed-provider proof. Open mode retains anonymous workspace access; authenticated cookies use the same CSRF, expiry, and privilege-rotation protections. Verification preserves the session's original deadline, explains missing provider freshness, and supports expired-form recovery. Team roles, direct credentials, and PATs don't grant console access; denied requests retain HTTP and failed-authentication limits.
  - **Browser sessions:** Authenticated browsers in all profiles use protected cookie sessions with CSRF checks; each profile retains its permitted sign-in methods. Open browsers retain anonymous use, migrate older saved credentials once with an authenticated reload, and can return anonymously after sign-out. Removing an older saved credential requires explicit acknowledgment. Workspace attachment and session creation commit together; rejected cookies preserve the one-time credential for recovery, and failed exchanges stay blocked.
  - **Local administration:** Grant, list, inspect, and revoke operator access independently of Team roles. Grants survive backups and database migration, repeated changes are quiet, and disabled principals can't gain access. CLI changes emit post-commit logs on stderr while stdout remains JSON. `operator-status` separates grant eligibility from the CLI's evaluated access policy and explicitly reports that the serving application and browser verification were not observed.
  - **Audit and diagnostics:** Audit viewing and exports move to `/audit` and `/audit/export`; old URLs don't redirect. Filters explain operator events and survive verification. Exports recheck authority between pages and abort on access loss or lookup failure; interrupted CSV ends with an incomplete-file warning, while interrupted JSON remains unparseable. Lookup failures and genuine denials have separate safe log classifications, and repeated warnings are sampled.
  - **Qualification:** All four profiles have SQLite/Postgres and desktop/mobile browser coverage in source and bundle modes, including navigation, filtering, verification, and anonymous sign-in redirects. Request checks cover profile transitions, CSRF, and streamed grant/session/freshness changes. Screenshot scenes cover all three pages in each theme. Production-like staging qualification covers open and restricted modes, including sign-in, recovery, bootstrap, proxy settings, and operator workflows.

- **Managed installations can administer access through `darklab-deploy access`.** Commands preserve principal safeguards, use the selected installation's Compose files, and write credentials to private host files with recovery after interrupted transfers. Host checks support GNU and BSD `stat`, reject unsafe or replaced destinations, and keep secrets out of command output. Required tests execute the shipped private-file transport against disposable paths.

- **Configuration can be validated without a working application process.** `darklab-deploy config check` and the standalone checker evaluate current or candidate YAML without applying changes, initializing services, or creating keys.
  - **Inputs:** Shared startup rules preserve normalization, validation, environment precedence, and warnings. Current checks honor the selected container mounts and local configuration root; only explicit candidates replace the selected overlay.
  - **Results:** Strict mode and versioned JSON report reviewed values, source layers, warnings, counts, presence, and withheld markers. A fresh evaluation is distinct from a running worker's captured startup snapshot; the field catalog also explains host apply requirements.
  - **Qualification:** Loader characterization, invalid-input checks, and generated-helper tests cover precedence, disclosure, custom mounts, and cleanup. Configuration guidance separates installed-image commands from source-checkout commands.

- **Coding agents have a shared repository guide.** `AGENTS.md` links the architecture, security, UI, testing, logging, documentation, and authorized Git/CI contracts. Contributor guidance uses live test inventories instead of maintaining exact totals.

### Changed

- **Shell startup and test feedback do less repeated work while preserving access checks and coverage.**
  - **Page load:** The shell reuses its embedded configuration and becomes usable without waiting for command recall or secondary catalogs. Late responses preserve privacy defaults, restored runs, typed drafts, and workspace scope. Theme previews load on demand with retry and latest-choice protection; active and exported palettes remain available immediately. Asset-manifest reads use an app-owned cache with file invalidation and existing error behavior.
  - **Backend tests:** Ordinary SQLite fixtures clone a validated pristine database. Postgres tests and browser profiles clone independent databases from a migrated template, with schema isolation for restricted roles and custom locales. Migration, startup, rollback, and real-pool tests keep their production initialization paths. Request tests reuse stable app wiring with fresh clients and data; repository guards share bounded syntax analysis. Postgres query fixtures match production's JIT default, and report fixtures restore only changed settings.
  - **Test preparation:** The Postgres lane avoids duplicating required SQLite coverage, Compose reuses runtime-qualified Python dependencies, and focused browser runs start only selected servers. Refreshed project weights account for qualification work. Bundle runs verify generated fingerprints without rebuilding; required CI still checks complete reproducibility. Browser jobs reuse versioned package and headless-browser downloads.
  - **Evidence and safeguards:** Successful runs retain safe pytest phase/CPU and browser timing summaries, including fresh-context/reload prompt readiness and first paint. Disposable Postgres runs separately record database-container CPU. Isolation, failure recovery, theme loading, late startup responses, cache invalidation, and selected-project behavior have regression coverage. Cache permission tests set their intended modes regardless of the caller's umask. Serial pytest policy, immutable migration history, authentication, and flaky-test guards remain intact.

- **Metrics network permissions are independent of operator access.**
  - **Before:** Metrics and diagnostics shared the `diagnostics_allowed_cidrs` network gate.
  - **After:** `metrics_allowed_cidrs` controls `/metrics` only, while granted operators can use the console from any network. The old key is removed starting with 3.1.0: YAML loading warns and ignores it, strict configuration checks fail on the warning, and runtime mutations reject it. Metrics permissions don't bypass AI workspace quotas; diagnostic AI tests retain CSRF and shared per-operator/global limits without charging the operator when global capacity is busy.
  - **Tests:** Configuration and checker cases preserve canonical layer precedence, source reporting, the empty-list default, and safe warnings. Metrics and operator checks verify independent access controls and AI limits.

- **3.1.0 is the stable release.** Application, npm, container, deployment, license-inventory, OpenAPI, and production-install expectations use the final version. Installation and signing examples select its exact tag. Changelog checks accept both the dated release layout and the active development layout, with the finalized 3.1.0 section included in the published-text integrity baseline.

- **Browser CI uses isolated app servers and preserves failure evidence.** Each project runs one browser worker, with a total CI cap of three; independent workflows and controlled readiness keep shared-runner contention from distorting checks. Traces retain original failed attempts, and CI still rejects flaky results.

### Fixed

- **Pylance resolves shared development and test helpers and checks their callers accurately.** Analysis paths include the shared helper directories, browser-session and configuration accessors preserve their concrete types, and Postgres tests declare dictionary rows explicitly. Tests check optional results and callback signatures without suppressing diagnostics or weakening their assertions.

- **Project Activity keeps pending filter edits during background refreshes.** Refreshing project data no longer clears fields before Apply is clicked. Paging continues to use the applied filters, and Clear resets both pending and applied values. Unit and browser regressions cover refreshes between editing and applying.

- **Container logs use the expected severity streams.** Application, background-worker, and Gunicorn process logs send DEBUG/INFO to stdout and warnings or errors to stderr. Existing verbosity, formatting, redaction, and exception details are preserved, and repeated configuration doesn't duplicate records. Collector guidance covers both streams.

- **Disposable test containers clean up their anonymous volumes.** Postgres tests, release-image checks, CI probes, and smoke-test cleanup remove attached anonymous volumes with their containers. Recovery after interrupted smoke runs also removes volumes that lack Compose project labels.

- **Backup exports reject missing Docker volume sources.** The helper checks source volumes before export, so a misspelled or unavailable source fails instead of creating an empty named volume and recording an empty export. Existing source volumes remain in place.

- **Managed backups include `compose.operator.yaml` when present.** The archive keeps a private, checksum-verified copy for manual recovery alongside `.env` and operator configuration. Restore preserves the destination host's Compose settings, and older backups remain compatible.

- **The bundled TruffleHog uses a patched AMQP dependency.** TruffleHog v3.97.5 includes `amqp091-go` v1.13.0 upstream to address AMQP parser and TLS vulnerabilities, removing the local dependency override. The image build verifies the dependency embedded in the executable and includes its license notice.
