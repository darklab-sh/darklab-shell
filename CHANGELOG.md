# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [3.x releases](docs/changelog/3.x.md) - versions 3.0.0 through 3.1.0
- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.9.2
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [3.1.3] - Unreleased

### Fixed

- Host worker smoke jobs skip the global pip install and inherited service containers, so qualification only requires the runtime baked into each worker image.

### Changed

- **SELinux and rootless Podman checks target disposable AWS workers.** Scheduled builds and optional release gates use capability tags with native host execution, preserving enforcing SELinux, rootless ownership, and bind mounts. CI regression checks cover all four jobs and prevent inherited Docker-in-Docker settings.

- **Dependency versions are updated.** Updated `jsdom` from `^30.1.3` to `^31.0.0`.

- **Dependency updates include preparation and compatibility evidence.** Project-owned checks keep generated assets, complete browser license notices, scanner constraints, and changelog summaries aligned. Production and CI Python resolutions remain separate from isolated scanners. CI exercises real Schemathesis reports against disposable APIs and audits installed scanner dependencies alongside app and development requirements. Hadolint uses one release/checksum manifest. Preparation reports identify independent parser, patch, license, and major-version reviews without claiming target CI has passed.

- **Bundled tool versions are discoverable by the central Renovate report.** Explicit Dockerfile annotations identify upstream packages and version schemes. Central preparation keeps linked scanner constraints and configured integrity pins together, while build compatibility and license review remain part of the project checks.

- **Application dependencies, bundled tools, and CI images use current releases.** Python packages, Playwright, Vitest 5, Stylelint 18, Markdownlint, and the packaged scanners are updated, along with checksums, exact scanner dependencies, and WPScan license records. CI uses Python 3.15.2, Node 26.13.0, Docker 29.9.2, and the digest-pinned GitLab CLI 1.128.0. Production Python stays at 3.14.10 for SSLyze compatibility, and the local `braces` security patch remains in place. Lint overrides include the RE2JS security fix.

- **TLS tools use compatible OpenSSL libraries.** The standalone command uses OpenSSL 4.1 and retains its legacy provider. sslscan 2.2.3 builds against Debian's OpenSSL 3 libraries, preserving the protocol APIs it still needs.

### Fixed

- **Docker CI jobs run without a worker socket mount.** Build, smoke, cache, image verification, and release jobs share version-matched DinD over TLS with a readiness check. Nested image scanners use that daemon's TLS endpoint; dedicated SELinux and rootless Podman checks retain their native host behavior. Contributor guidance and CI regression checks cover the runner boundaries.

- **Dependency qualification runs on the AWS ephemeral runners.** The CI job uses a version-matched Docker-in-Docker service over TLS instead of requiring the worker's Docker socket, and waits for the daemon before starting its checks.

- **Generated dependency changelog entries keep valid Markdown spacing.** Preparation inserts one blank line around new entries and newly created Changed sections without altering published history. Regression coverage checks repeated updates and empty sections.

- **Routine dependency updates use the build pins in version checks.** Production-image tests check exact pins, wiring, constraints, and release evidence without duplicating current dependency versions. Gau and Schemathesis smoke version expectations read the Dockerfile defaults. Reviewed security minimums, compatibility contracts, and the independent Schemathesis parser version remain enforced; regression coverage accepts routine updates and rejects downgrades and stale binary output.

- **Bundled Go scanners use patched Brotli decoding.** Shared builds require Brotli 1.2.7 or newer and reject stale or replaced embedded copies, addressing the vulnerability scan findings across gau, ffuf, Chaos, and the affected ProjectDiscovery tools. The image includes the module's MIT license, and the fixed-Critical vulnerability gate remains in place.

- **Schemathesis rejection fixtures pass editor type checks.** The report helper explicitly accepts a null failure message so tests can verify that malformed reports are rejected.

- **Dockerfile linting rejects failed or damaged Hadolint downloads during setup.** CI uses the correct release asset name, pins Hadolint 2.15.1 and its SHA-256, retries failed downloads, and checks the installed tool before running the linters. The Linux contributor setup uses the same verified release.

- **Schemathesis 4.33.1 scans and reports remain compatible with reviewed Assessments.** Commands use the current deterministic-generation options. Report parsing accepts the release's lowercase phase names and empty failure descriptions while checking the exact tool version, approved operations, evidence limits, and private-data handling. Regression checks keep the packaged version, isolated constraints, parser contract, and smoke version expectation aligned, and reject reports from the preceding release. Smoke expectations check the CLI usage and required configuration option. A local scan against a disposable API verifies the command and report together.

- **Container helpers handle file paths and module loading explicitly.** The Shodan patch uses a writable filesystem path, and security tests reject missing module loaders before importing helpers, resolving the reported editor type errors.

- **Container vulnerability scan cleanup passes CI shell linting.** The scan removes its temporary container directly in the exit trap, avoiding a false unreachable-code warning while preserving cleanup and scanner exit status.

- **Container dependencies include the critical security fixes.** Python 3.14.10, Go 1.27.3, the shared Go networking dependency, and Debian Brotli use patched releases. SSLyze runs in an isolated environment with compatible dependencies, and the pinned Shodan CLI uses standard Python package metadata. Builds check Python dependency consistency and Debian certificate trust; vulnerability scans retain the critical gate with one path-scoped exception for Debian certifi, which delegates to the patched system trust store.

- **Access recovery tests allow authentication redirects to finish.** Cookie-loss coverage arms its recovery request before removing the cookie and deliberately checks denied reads after navigation. Saved-credential coverage restores into a new page after the previous shell stops polling, preventing navigation from interrupting storage setup under load.

- **Mobile chart preview actions stay reachable after scrolling.** Status Monitor brings a selected preview into view before the next tap. Its own scroll event keeps the preview open; subsequent scrolling still dismisses it without launching a run or opening History. Regression coverage opens a preview from a partially scrolled chart.

- **Shell-chrome unit tests release their browser listeners between cases.** Mocked requests settle on the next event-loop turn without accumulating real timer delays, and document/window listeners no longer retain previous fixtures. The long Project interaction test keeps its existing timeout and assertions.

- **Frontend inventory checks reuse syntax-tree structure.** The inventory reuses each parsed node's child list across its analysis passes, reducing cold-scan work without changing the reported browser boundaries, checks, or test timeouts.

- **JavaScript dependencies include the reported security fixes.** Vitest and its coverage package use patched releases, and the lockfile updates DOMPurify, fast-uri, Undici, and Vite. Markdownlint supplies patched Markdown and TOML parsers, with scoped overrides for math rendering, regular-expression matching, and ESLint glob matching. The local `braces` security patch remains in use.

- **Repeated UI setup releases the previous select observer.** Shared select enhancement keeps one active observer, preventing old observers from processing later DOM updates. Regression coverage checks observer replacement, browser-global inventory runs in Node, and provider-only credential checks wait for Access data and select enhancement before interacting with the editor.

- **Python dependencies include the security fixes for sign-in, certificate trust, and package installation.** Authlib and joserfc use patched releases, the application and isolated Schemathesis scanner share the updated certifi bundle, and development, container, and CLI builds require patched setuptools. The scanner also uses patched GraphQL-core, urllib3, and Werkzeug dependencies. Token-exchange logging follows Authlib's response validation while preserving HTTP status and keeping provider data out of logs.

- **Container builds retain Python 3.14 compatibility with SSLyze.** The production base and image metadata use Python 3.14.10, with matching license notice paths. SSLyze 6.3.1 requires nassl 5.4.x, which doesn't publish Python 3.15 distributions. Installation checks require an exact slim-image version that matches the metadata, so dependency updates no longer require a second hardcoded test pin.

---

## [3.1.2] - 2026-10-06

**Upgrade note:** This release retains the v3 access model: pseudonymous principals have stable personal workspaces, portable credentials sign browsers in, and scoped PATs authenticate API and CLI requests. Legacy `tok_` values remain intentionally invalid, and databases with retired identity schemas are rejected. Private deployments can require credentials, OIDC, or either sign-in method. Before upgrading, complete the [operator preflight](CONFIGURATION.md#upgrade-preflight), verify a working sign-in and explicit operator grant, and preserve a tested backup of the database, matching secrets key, Files, and operator configuration. These access requirements were introduced in earlier v3 releases; 3.1.2 fixes workspace identity and cleanup handling.

### Changed

- **3.1.2 is the stable release.** Application, npm, container, deployment, license-inventory, OpenAPI, and production-install expectations use the final version. Installation and signing examples select its exact tag. The dated changelog section is included in the published-text integrity baseline.

### Fixed

- **Development dependencies resolve the reported npm security advisories.** Markdown linting uses patched KaTeX and TOML parsing, while CSS linting and browser tests use patched selector and source-map parsing. The dependency updates preserve the existing Markdownlint release and local `braces` security patch.

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
