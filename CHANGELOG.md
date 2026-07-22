# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.3.1
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.7.0] - Unreleased

### Added

- **TruffleHog can scan authenticated GitHub and GitLab sources without exposing provider tokens.**
  - **Why:** Files and public HTTPS Git scans couldn't enumerate private repositories, organizations, groups, or self-hosted provider instances.
  - **What:** `trufflehog github` receives `GITHUB_TOKEN` and `trufflehog gitlab` receives `GITLAB_TOKEN` from the active encrypted secrets scope. Repository and endpoint URLs must use credential-free HTTPS; inline tokens, auth-in-URL, custom clone paths, retained clones, and local Git sources remain blocked. GitHub `--org`, GitLab `--group-id`, custom HTTPS endpoints, and workspace-backed include/exclude files are supported, and `providers` reports both command credentials.
  - **Tests:** registry, policy, secret-scope, workspace rewrite, autocomplete, runtime JSON injection, consumer-display, and per-example smoke-source assertions cover both provider sources without adding new test cases.

- **Terminal output can be saved directly to Files, and files can be copied or touched from the prompt** — `command > file` overwrites a workspace file while keeping output out of the live terminal, `command >> file` appends to it, and `command | tee file` overwrites it while still displaying the same post-filtered, redacted output. `file copy` / `cp` copies one file without overwriting an existing destination, while `file touch` / `touch` creates an empty file or refreshes its modified time; every write follows the active Files directory, owner/team permissions, path checks, and workspace limits.

- **Files and completed runs can be compared directly from the terminal** — `diff` accepts workspace files, explicit `file:<path>` sources, completed `run:<run-id>` output, or one of each. `diff --last` compares the last two completed runs from the current tab, while `file diff` keeps the same file-oriented command under the Files namespace. The default output follows classic `diff` with `<` and `>` lines; `-q` / `--brief`, `-u` / `--unified`, and `-y` / `--side-by-side` provide familiar alternate layouts. Run sources follow the same owner scope, output filtering, and comparison limits as the History comparison view, and file sources stay inside the active personal or team workspace. Each file source is limited to 5,000 lines and 500,000 UTF-8 bytes so terminal comparisons stay responsive; oversized files are rejected instead of silently truncated.

### Changed

- **Production installation and source development now have separate, explicit runtime contracts.**
  - **Before:** the root Compose file and environment template mixed development defaults with release-facing settings, while an old checkout-only production override, migration help, direct backup examples, and “repository-free” wording kept a second production path visible.
  - **After:** production starts from the versioned installer, installed `compose.yaml`, `deploy/.env.example`, and `darklab-deploy`; development uses the loopback-only `compose.dev.yaml`, the root development `.env.example`, or the local Python helper. The retired production override and checkout migration procedures are gone, development services no longer claim fixed container names or production restart behavior, and current docs use production-installation language throughout.
  - **Tests:** production-payload contracts pin the correct environment template and production/development Compose boundaries, lifecycle coverage rejects the retired `migration-help` command, documentation checks reject stale deployment paths and terminology, and both Compose files pass rendered-config validation.

- **Release tags publish one native image for Linux AMD64 and ARM64** — Protected tag pipelines resolve one Python base index, build and scan each architecture on a native runner, and assemble the verified child digests into one immutable GitLab OCI index before copying the same index to Docker Hub. The installer manifest, image verifier, SBOMs, vulnerability reports, provenance, signatures, public smoke checks, and release evidence all retain the canonical index digest plus the selected child and platform-base digests. Dual-platform publication fails closed when either child is missing; a manual protected AMD64-only emergency release requires a public reason and stays permanently single-platform. SELinux Docker and rootless Podman remain AMD64 compatibility claims, and ARM64 stays uncached on the storage-limited hosted runner. Three protected rehearsals exercised both native children without publishing release artifacts; the uncached ARM64 lane completed within 50.75 percent of its timeout and retained at least 23.62 percent free storage against its accepted 20 percent floor.

- **Project scripts separate stable commands from implementation helpers** — Release, container, frontend, generator, operator, development, and test-support code now lives in purpose-named directories while documented commands and common test runners keep their existing paths. CI, npm, Docker, hooks, and import-based tests call the grouped implementations directly; compatibility and architecture checks preserve command forwarding, executable modes, working-directory independence, image-copied helpers, and generated-asset ownership metadata.

- **Backend test feedback arrives sooner without reducing release coverage** — The unchanged complete pytest command now has complementary fast and release-integration selections that GitLab runs as required concurrent jobs. An exact node-ID partition guard prevents skipped or duplicated coverage, each lane retains JUnit plus slow-test and file-level timing reports, stable route tests reuse reset applications with fresh clients, and asset working-directory checks avoid duplicate production compression while a focused sidecar test and the full committed-asset check preserve Brotli/gzip coverage. Five consecutive project-runner pipelines passed both lanes; median runner durations were 91.6 seconds for release integration and 301.2 seconds for the fast lane, compared with 477.2 seconds for the previous complete-suite job. The first required result now arrives about 79% sooner than the earlier 433-second test baseline.

- **Scheduled image builds warm every self-managed runner** — The existing `bael`, `bune`, and `botis` fanout now also builds on `babi`, `bile`, `barbas`, `beleth`, `baka`, `bana`, the SELinux-enforcing `baku` runner, and the rootless-Podman `baal` runner.

- **Release image cache behavior is measurable without permanent probe jobs** — Canonical AMD64 publication retains its build or tag-reuse time, cache reference, Python base digest, image size, and pipeline identity, while release publication rejects a cache scope that doesn't match the release line. The cross-runner acceptance run completed both cache export and reuse in under one minute with the expensive builder stages served from cache, so scheduled CI now keeps only the production cache warmers.

- **Multi-platform publisher retry and conflict paths are tested as real shell behavior** — A stub Docker client, registry state, and runner-identity harness executes platform build and reuse, conflicting staging content, wrong-architecture and missing-artifact failures, child-anchor create/reuse/conflict, canonical-index conflict, and Docker Hub copy/reuse/conflict paths through the same publisher script CI runs. The existing Python contract tests continue to validate descriptors and release modes without standing in for publisher behavior.

### Fixed

- **GELF startup and migration logs no longer collide with OpenSearch metadata fields.**
  - **Root cause:** `APP_INITIALIZED` and schema-migration records used a structured field named `version`. The GELF formatter correctly prefixed additional fields with `_`, but that produced `_version`, which OpenSearch reserves for document metadata; the fatal configuration fallback had the same latent problem with `_source`.
  - **Fix:** app startup now reports `app_version`, migration events report `migration_version`, and both normal GELF formatting and fatal startup fallback namespace any OpenSearch-reserved additional name under `_event_*`. GELF protocol version `1.1` and the existing `_app_version` field remain unchanged.
  - **Tests:** formatter coverage rejects `_version` and `_source`, verifies their safe `_event_*` names, and startup plus migration event contracts pin the explicit field names.

- **Deployment settings no longer masquerade as usable YAML overrides.**
  - **Root cause:** both shipped Compose stacks always supplied defaults for Files, database, PTY, raw scanning, Prometheus, and AI environment variables, so matching values in `config.local.yaml` could be silently shadowed even though the YAML reference presented them as operator options.
  - **Fix:** deployment wiring and feature switches now have one documented `.env` surface, including `WORKSPACE_ENABLED`, `WORKSPACE_BACKEND`, and `WORKSPACE_ROOT`. The shipped YAML reference keeps only application fine-tuning, and Compose passes empty optional overrides for database pool/JIT and AI tuning so those YAML values can take effect.
  - **Tests:** production/development Compose contracts pin the environment-owned switches and empty fine-tuning overrides, while the documentation guard keeps deployment-owned keys out of the shipped YAML option list.

- **TruffleHog findings and redacted snapshots no longer expose vendor secret fields or private keys.**
  - **Root cause:** TruffleHog doesn't guarantee that `Redacted` is safe to display, multipart credentials can remain in `SecretParts`, and snapshot redaction handled only independent regex matches rather than private-key blocks spanning several output lines.
  - **Fix:** managed TruffleHog JSON now masks `Raw`, `RawV2`, `Redacted`, every `SecretParts` value, and duplicate copies elsewhere in the row before any transcript, Files output, history, share, export, or finding path receives it. Finding fallback text never reuses a malformed raw row, and redacted shares or packages replace complete PEM and PGP private-key blocks from any command.
  - **Tests:** existing output-sink, structured-finding, Atlas materialization, fallback, and share-route cases now cover verified, unverified, multipart, duplicated-secret, and multiline private-key shapes without changing the documented test count.

- **Development YAML tooling no longer installs a vulnerable `js-yaml` release** — The dependency override moves compatible v4 consumers to patched `js-yaml` 4.3.0 without forcing Markdownlint off its supported v5 dependency or downgrading Stylelint. Theme registry tests declare the patched v5 parser directly and use its named `load` export, so their YAML fixtures work with the current ESM module shape.

- **Development tooling no longer installs the vulnerable `brace-expansion` 5.0.6 release** — The lockfile now selects patched version 5.0.7 for ESLint's Minimatch dependency, clearing the high-severity JavaScript dependency audit without a forced or breaking upgrade.

- **Browser and development dependencies no longer install vulnerable DOMPurify, fast-uri, or linkify-it releases** — The lockfile now selects DOMPurify 3.4.12, fast-uri 3.1.4, and linkify-it 5.0.2, clearing the custom-element sanitizer bypass, URI host-confusion, and quadratic `mailto:` parsing advisories without changing their parent packages.

- **Staging registry cleanup doesn't skip expired tags when pages shift during deletion** — The cleanup job now collects and validates the complete match set before issuing its first delete request. Its regression models 205 temporary tags across three mutable offset-paginated pages and confirms every expired attempt is removed while a release-child anchor remains untouched.

- **ARM64 release smoke checks verify the live Postgres schema instead of a browser-only config response** — The optional Postgres startup gate now confirms that app migrations reached the fresh Postgres service. It no longer expects the public `/config` payload to expose the private database backend setting.

- **Native release smoke checks can validate licenses from the installed image** — The streamed checker now enters installed-image mode before looking for source-only repository files, so AMD64 and ARM64 CI jobs don't mistake the container's `/app` directory for a checkout.

- **Multi-platform release checks report real runner capacity and stay usable on minimal Docker installations.**
  - **Root cause:** the ARM64 DinD lane measured the job container's filesystem instead of the daemon's storage, v2 deployment manifests retained meaningless zero-valued scalar image metrics, and operator verification depended on the optional Buildx plugin while dropping the older Apple Silicon AMD64 fallback.
  - **Fix:** ARM64 metrics now read `/var/lib/docker` through the DinD daemon, v2 keeps measurements only in its per-platform map, and the installed verifier uses the canonical index RepoDigest plus local architecture and base labels with no Buildx requirement. Apple Silicon prefers ARM64 but can verify an explicitly degraded AMD64-only release through Docker's emulation path; Linux ARM64 remains native-only.
  - **Tests:** release-pipeline contracts pin the daemon-backed metric path, v1 retains its scalar compatibility field while v2 omits that ambiguous field, and verifier coverage exercises native selection, Darwin fallback, and Linux ARM64 rejection.

- **Files output capture fails safely before and after a run** — File-descriptor forms such as `2>` and `2>>` are rejected instead of being mistaken for stdout capture, existing directory destinations are caught before a command starts, and scheduled built-ins now record a failed exit when their output can't be saved. Unexpected filesystem errors stay in server logs and return a generic terminal message instead of exposing the workspace's internal host path.

- **Bundled Go tool upgrades keep the requested release while enforcing the security floor.**
  - **Root cause:** the shared installer selected each pinned tool before forcing the reviewed `golang.org/x/crypto` version. Go could satisfy the later request by downgrading a tool whose newer release required a newer crypto module, which made `httpx` v1.10.0 resolve and build as v1.9.0.
  - **Fix:** the installer establishes the crypto version as a minimum first, selects the pinned tool second, and rejects any mismatch in either the selected module graph or the finished binary's embedded module metadata. A tool can still raise `x/crypto` above the baseline when required. DNSX v1.3.0's `-version` banner remains an upstream 1.2.3 string, so the embedded module version is the reliable build identity.
  - **Tests:** focused installer coverage verifies dependency ordering and fails on both graph-level and embedded-binary downgrades, while the runtime-image contract keeps the checks in every Go builder stage.

- **Container smoke tests follow the public workflow contract and enable the optional PTY feature they exercise.**
  - **Root cause:** the workflow capture smoke case still expected private execution variables after those values were removed from public responses, while Compose's disabled-by-default PTY environment switch overrode the smoke-only YAML setting.
  - **Fix:** the workflow case now verifies that variable values stay private while successful capture names and linked steps prove the value flowed downstream. The smoke stack explicitly enables Interactive PTY, and PTY startup failures include the returned HTTP status and JSON error.
  - **Tests:** focused workflow privacy and container PTY smoke coverage exercise the corrected contracts.

- **Release publication tests are isolated from their CI runner** — The fake publisher environment clears inherited GitLab pipeline and job IDs before exercising the missing-ID fallback, while a separate retry path verifies that explicitly supplied IDs still reach the build metrics artifact.

- **Workspace terminal commands load existing files on first use** — `ls`, `ll`, and `file list` now load the lazy Files state before reading it, so an initial listing no longer appears empty until the Files modal has been opened.

---

## [2.6.0] - 2026-07-18

### Added

- **darklab_shell is explicitly licensed under GNU AGPLv3** — Project-owned source and documentation use `AGPL-3.0-only`, while bundled tools and other third-party material keep their own licenses.
  - **Included notices:** the full project license ships in the repository, container, and installer payload. Third-party terms remain listed in `THIRD_PARTY_NOTICES.txt` and `container-licenses.json`.
  - **Source access:** official builds link to their exact source tag from the app. Operators who publish a modified network version must point that link at the corresponding source and follow the license's source-offer requirements.

- **Self-hosted releases install without a repository checkout or local image build** — A checksummed installer creates a small production directory that runs an exact release image while keeping application code inside the image.
  - **Install and configuration:** production publishes port 8888 on every host interface by default so remote operators can connect without first configuring a reverse proxy. Operators can narrow the bind address to loopback or restrict the port with a firewall. Private overlays stay under `conf/`, and only configuration and durable state are mounted, so upgrades don't hide new commands, workflows, themes, or other catalogs. The managed Compose file includes copy-ready commented scanner limits and sysctls, with runtime caveats and directions to keep enabled values in an operator-owned override.
  - **Single install-path setting:** Quick Start and verified-install commands define `DARKLAB_INSTALL_DIR` once, so operators can choose a deployment directory without editing both the installer and follow-up `cd` commands.
  - **Release verification:** the release publishes matching GitLab and Docker Hub image digests, checksums, signatures, an SBOM, vulnerability results, provenance, and a build-input inventory. The installed verifier rejects image or managed-file drift, while publication validates the complete license inventory, required notice paths, and hash-pinned Nmap and WPScan license texts.
  - **State and lifecycle:** `darklab-deploy` reports status, makes and verifies SQLite or Postgres backups, restores after taking a safety backup, migrates managed SQLite data into bundled Postgres, upgrades only to an authenticated newer release, explains clone-backed migration, and removes release-owned files without deleting operator state.
  - **Managed Postgres cutover:** the installed migration command stops SQLite writes, takes a verified backup, initializes and validates a fresh bundled Postgres schema, preserves the destination migration ledger, switches the managed environment only after the copy succeeds, and restarts SQLite automatically when a pre-cutover step fails.
  - **Migration permissions:** the repository-free cutover verifies the app-owned SQLite database through its Docker mount instead of requiring host access to the locked-down `data/` directory, and rejects `sudo` before it can replace operator-owned `.env` state with root-owned files.
  - **Restore path handling:** documented relative backup paths such as `backups/darklab-backup-<timestamp>.tar.gz` are resolved to absolute host paths before Docker bind-mounts them, preventing Docker from mistaking the archive for a named volume.
  - **Postgres backup compatibility:** repository-free backup and restore containers include PostgreSQL 18 client tools that match the bundled PostgreSQL 18 service, and release verification rejects a mismatched client major before lifecycle testing begins.
  - **Supported runtime:** Docker Compose 2.20.0 or newer on Linux AMD64 is the production target. Postgres and the local model remain optional, Redis stays disposable, and raw-packet scanning stays opt-in. Native ARM64, SELinux, and rootless Podman pass protected release gates but remain outside the advertised support matrix because the release publishes only an AMD64 production image and the alternate runtimes need additional host-specific setup.
  - **Validation:** protected release gates exercise installer safety, private overlays, matching registry digests, immutable publication retries, distinct RC-to-RC and RC-to-final upgrades, repository-free startup, durable restarts, and a bundled-Postgres backup/restore round trip.

- **Workflows can run as durable parameterized playbooks** — Explicit `version: 2` workflows run one server-owned step at a time, keep working after the workspace closes, and retain their execution history and linked runs.
  - **Authoring:** the browser editor supports typed inputs, stable reorderable steps, success/failure routes, repeatable exact-exit-code routes, and bounded line, entity, or JSON Pointer captures. Routes follow renamed or reordered steps, and a deleted destination stays visibly invalid until it is repaired or removed.
  - **Running and review:** `Run all` and the terminal `workflow` commands start durable executions. The shared desktop/mobile workspace keeps the searchable catalog and execution list together, shows progress and branch outcomes, and opens or attaches linked runs without losing the selected playbook.
  - **Private values:** sensitive inputs are masked while prompting and shown as `[redacted]` in ordinary run metadata, History, logs, metrics, and notifications. Shared execution responses omit stored inputs, captures, snapshots, owner tokens, and browser ownership details; app-managed Secrets remain the right place for credentials that shouldn't enter workflow history or backups.
  - **Reliability and policy:** executions recover after restart, serialize owner limits, recheck team and token access before each step, distinguish expected nonzero branches from failures in logs, and keep a failed workflow hook from corrupting normal run finalization.
  - **Validation:** backend, browser, and live UI coverage exercises compilation, captures, exact-code routing, privacy, permissions, cancellation, recovery, storage parity, navigation, mobile editing, and capture-fed execution.

- **Run comparisons make saved-run changes easier to trust and reach** — App-launched comparisons consistently place the older baseline on the left and the current run on the right, while direct API pairs remain positional.
  - **Entry points:** comparisons can start from History, Run Details, Projects, the completed active-tab HUD, the mobile menu, or the compact Findings signal. Automatic and manual pickers offer completed external runs from the active personal or team scope, and the Findings shortcut opens a literal findings-only view.
  - **Findings and detected changes:** new per-run finding occurrences retain the severity observed at scan time, so matching findings can show a severity change instead of appearing as unrelated additions and removals. Older rows use a best-effort backfill from retained finding and snippet data and keep a stable add/remove fallback when their original severity or identity can't be recovered. Severity-bearing unscoped subjects use the same neutral identity as their finding text, and large duplicate groups pair in bounded linear passes. Structured summaries also cover discovered hosts and TLS subject, issuer, SAN, validity, fingerprint, and verification changes alongside the existing nmap port/service and web URL groups, while raw transcript diffing remains available when output can't be classified confidently.
  - **Context and navigation:** compared runs show workflow execution and step ancestry when available, with a direct handoff that closes the comparison before opening the playbook. The comparison modal traps focus and returns it to the launching control when it closes, including the HUD, Findings shortcut, and mobile hamburger. Changed findings have baseline/current severity labels and per-side transcript anchors; summary counts, empty states, lazy equal-line expansion, and mobile layouts all understand the new groups.
  - **Access, reliability, and logs:** run candidates, persisted findings and artifacts, workflow ancestry, project resolution, and lazy line reads share the active owner scope. Slow, stale, or failed candidate responses can't replace a newer launcher's source run, and Project Monitoring preserves baseline-left/current-right ordering. Findings-only mode shows persisted changed/added/removed counts without transcript-signal or artifact metrics and omits controls that require hidden transcript panes. Completed and intentionally partial comparisons emit one bounded INFO summary, while candidate and comparison request failures report safe route, stage, status, and run-id context without commands, manual search text, or query strings. Expected 4xx rejections stay at WARN and unexpected transport/runtime failures use ERROR. Focused SQLite/Postgres migration, service, route, Vitest, and desktop/mobile Playwright coverage verifies ordering, isolation, changed findings, derived host/TLS output, workflow context, logging, and every launch path.

- **Linux Docker deployments can opt in to raw-packet scanning without privileged containers** — `RAW_PACKET_SCANNING_ENABLED=true` unlocks capability-backed Nmap, Naabu, and Masscan modes only after each scanner passes its runtime checks.
  - **Scanner behavior:** Nmap can use its normal SYN default or an explicit raw mode, Naabu can use SYN scanning, and Masscan becomes available. Nmap and Naabu keep their connect-mode fallbacks whenever raw readiness is inactive; Masscan points users to a connect-capable alternative.
  - **Safety and limits:** scans still run as the unprivileged scanner user without Docker privileged mode, host networking, or root processes. Spoofing and link-layer bypasses remain blocked. Restricted-CIDR deployments require a matching protected firewall marker for raw Nmap and keep packet-socket Naabu and Masscan inactive; the app-port guard applies only to container-local destinations, so the same port remains scannable on authorized remote targets.
  - **Visibility:** raw-only flags and examples appear only when the matching tool is ready. Startup logs and `/diag` report configured, available, and active state with bounded prerequisite failures.
  - **Validation:** policy, readiness, diagnostics, restricted-network, and container smoke coverage exercises both fallback and raw paths without relying on public targets.

### Changed

- **Project documentation is easier to scan, navigate, and keep current** — The landing page now leads with setup, detailed contracts have clear owners, and generated inventories no longer crowd reader-facing guides.
  - **Everyday guidance:** README leads with the shortest release-install path, keeps checksum and publisher-identity verification under Production Deployment, separates repository-based development workflows from installation, and uses compact feature, tool, and repository summaries. Its installed-tool table now matches the external command registry, while the test handbook points to live suite-listing commands and focused tool and logging guides keep deeper help one click away.
  - **Reference ownership:** FEATURES stays user-focused, ARCHITECTURE keeps stable runtime and front-end design contracts, and CONFIGURATION owns the supported-runtime matrix. Operator recipes now lead with installed `conf/` paths and installation-directory Compose overrides, while checkout-only files are clearly labeled as source-development or custom references. Related-doc sections link only to the most useful next pages.
  - **Release history:** the root changelog keeps the active release plus the two newest dated releases, with older entries preserved intact in major-version archives.
  - **Validation:** offline link and heading checks, table-of-contents checks, published-release integrity hashes, support-matrix executable-contract checks, and focused durability guards protect the new structure. Permanent navigation covers maintained docs without pulling temporary release drafts or pre-merge review findings into the public index.

- **Protected release builds report image failures sooner and reuse portable caches** — Tag pipelines keep one self-contained runtime image while shortening repeated build and verification paths.
  - **Smaller runtime:** independent Go, native, Ruby, and large-asset builder stages leave compilers, development packages, Go caches, apt indexes, build source trees, and local configuration overlays out of the shipped image while copying reviewed notices to durable runtime paths. VirusTotal CLI, Nikto, and SecLists now use reviewed immutable inputs.
  - **Portable rebuilds:** AMD64 builds import and export a serialized, release-line-scoped registry cache with scheduled warmers. Native ARM64 compatibility builds stay uncached on the storage-constrained hosted runner.
  - **Earlier feedback:** ordinary branch images receive the fixed-Critical scan before tagging. Protected tags start the canonical Syft/Grype gate beside runtime compatibility checks, reuse its retained files for evidence and signing, and measure pull time and installed size in the existing smoke pull instead of delaying every downstream job with an extra repull.
  - **Targeted retries:** a manual digest recheck reruns repository-free startup, bundled-tool execution, and vulnerability scanning without rebuilding or republishing the image, while safe long-running branch and cache-warmer builds can be canceled when a newer pipeline replaces them.
  - **Measured release shape:** the v2.6.0 candidate records a 1.45 GB compressed and installed AMD64 image with a 39-second representative cold pull. SecLists accounts for about half of the transfer, but keeping one full image preserves the same tool, wordlist, capability, networking, licensing, and upgrade contract for every operator instead of introducing a divergent slim variant.

### Fixed

- **Managed Postgres cutover no longer fails with repeated authentication errors against an empty retained volume.**
  - **Root cause:** Compose named volumes survive `docker compose down` and deletion of the installation directory, while each fresh install generates a new Postgres password. Reusing an initialized `postgres-data` cluster could therefore make the first network connection fail even when the current installation had never enabled Postgres.
  - **Fix:** SQLite migration and fresh-host Postgres adoption inspect the destination through the Postgres container's local socket before network authentication. An empty cluster has its role password synchronized with the current installation; a cluster containing user tables is left untouched and rejected as a possibly retained deployment instead of producing connection-pool retries.
  - **Tests:** managed lifecycle coverage verifies the local user-table query, non-empty refusal before password or data migration, SQLite recovery, empty-target password synchronization, and ordering before schema initialization and restore.

- **Managed Postgres backups can be restored onto a fresh replacement host.**
  - **Root cause:** restore always preserved the target's database backend and rejected a Postgres archive when a newly installed target still had the default SQLite setting, leaving no safe repository-free path for host replacement.
  - **Fix:** `darklab-deploy restore --adopt-backend BACKUP` keeps the new host's image and generated Postgres credentials, enables and starts bundled Postgres, confirms the destination has no user tables, restores the dump transactionally, adopts the Postgres backend in `.env`, and recreates the app. Ordinary restores keep the backend-mismatch guard and now report the explicit fresh-install command before stopping the app.
  - **Tests:** helper and installed-wrapper coverage verifies the default mismatch guard, empty-destination requirement, target credential preservation, Postgres startup ordering, transactional restore arguments, environment cutover, app recreation, and temporary-file cleanup.

- **Repository-free backups no longer omit workspace files because of `.env` formatting or current feature state.**
  - **Root cause:** the installed wrapper recognized persistent workspaces only when `WORKSPACE_ROOT=/workspaces` started in column one, while the lower-level helper checked `workspace_enabled` before honoring an explicit source. Compose-valid leading spaces or a currently disabled Files feature could therefore produce a successful archive without the managed workspace directory.
  - **Fix:** managed backups always include the installed `./workspaces` bind, and explicit `--workspace-source` requests take precedence over automatic feature-state detection. Missing or unreadable explicitly requested workspace data still fails the backup instead of being silently excluded.
  - **Tests:** existing backup and managed-lifecycle coverage now verifies an explicit bind with file-based workspaces disabled and a repository-free `.env` using the leading-space syntax Compose accepts.

- **Repository-free configuration starters explain their source and syntax** — Every installed `conf/*` starter says whether it merges, appends, or replaces content, links to the matching built-in catalog from the exact release tag, and points to its focused guide. YAML and hint starters include commented examples operators can copy safely. FAQ and welcome guidance no longer presents image-internal `app/conf/*` paths as though they exist in the deployment, while complete-replacement banners, package presets, and report templates direct operators to the full shipped source before editing.

- **Optional features are easier to find and enable** — README now introduces persistent Files, Interactive PTY, and raw-packet scanning immediately after Quick Start, while the installer points operators to a dedicated feature-switch block near the top of `.env`. `WORKSPACE_ENABLED`, `WORKSPACE_BACKEND`, and `INTERACTIVE_PTY_ENABLED` override their matching app settings alongside the existing workspace-root and raw-packet controls, so Compose operators can enable these capabilities without mixing their main switches into YAML fine-tuning. The installed `config.local.yaml` starter points back to `.env`, and every feature remains disabled until the operator opts in.

- **Restores take effect in existing app and browser sessions** — The managed restore wrapper force-recreates the app when restored `.env` content changed and waits for app health before returning. Session-scoped Files listings bypass browser caches and return `no-store`, so terminal workspace commands see restored files without requiring the Files modal to refresh them first.

- **Postgres workflow recovery starts without invalid cursor values** — The first recovery page omits its timestamp cursor predicate until a real cursor exists, so fresh Postgres workers no longer bind an empty string into a `timestamptz` comparison. Postgres integration coverage exercises both the initial page and its follow-up cursor.

- **Repository-free release gates exercise production identity and configuration paths correctly** — The bundled-Postgres backup/restore smoke uses a valid anonymous UUID for authenticated preference writes and translates its Docker-executor workspace to the host daemon's real mount source before lifecycle helper containers read or restore deployment files. The public Docker Hub smoke transfers the installed private configuration into a daemon-managed volume before layering it onto the shipped Compose file, and its marker stays within the app-name length contract.

- **Hosted ARM64 builds stay within the runner's storage budget** — The native release smoke returns to the direct, uncached Docker build that passed before registry caching was introduced, while keeping the explicit DinD readiness check and current runtime verification. The unused ARM cache warmer is removed, and SecLists remains staged at its final runtime path.

- **Run comparisons start only one full comparison request** — The ESM bridge is checked for an installed handler instead of treating the renderer's normal void return as a missing handler, preventing a slower duplicate response from collapsing newly expanded unchanged lines.

- **Release vulnerability evidence is generated in the CI job workspace** — Syft and Grype now stream the SBOM through the job container instead of writing through Docker-daemon bind paths, so the CycloneDX file is retained with the full scan report. The image updates OpenSSL, compiles `gosu` with the current Go toolchain, builds bundled Go tools against the fixed `x/crypto` security baseline, and removes a stale executable shipped inside an upstream module cache so actionable Critical findings still fail closed without suppressions.

- **Pre-commit shell checks match the full repository lint scope** — The hook now uses the same ShellCheck command as CI, including deployment shell templates, and the release smoke helper avoids an ambiguous conditional that ShellCheck correctly rejected.

- **Release image smoke checks isolate storage and privileges for each runner** — Docker-socket jobs, including the anonymous Docker Hub check, use daemon-managed scratch volumes so configuration overlays reach the host daemon. Native rootless and SELinux jobs keep bind-mount scratch data outside the checkout and recover stale pre-checkout directories, while bundled-tool verification grants the raw-network capabilities required to execute Naabu on ARM64.

- **Fresh Postgres starts serialize migration-ledger creation across every process** — Schema branch detection is read-only, leaving the first `schema_migrations` table creation and unified baseline behind the existing transaction-scoped advisory lock when Gunicorn, notification, and scheduler workers start together.

- **Python dependency audits cover development tooling consistently** — The npm audit command now checks both runtime and development requirements, and the development-only setuptools pin moves to the release that fixes its reported advisory while the image keeps the older Shodan-compatible runtime pin.

- **Release image verification uses portable runtime inputs** — The shared Docker and Podman smoke test uses a fully qualified Redis image, valid SELinux relabeling syntax for writable mounts, and an overlay marker that fits the app-name limit.

- **Installed RubyGem inventories stay valid across image builders** — The generated WPScan dependency manifest contains one JSON document without a builder-sensitive escape suffix, forcing the canonical image layer to rebuild so Docker, rootless Podman, and SELinux verification parse it consistently.

- **ARM64 release builds recover promptly from stalled asset downloads** — The hosted Docker-in-Docker network uses a conservative MTU, and RustScan downloads retry within bounded time instead of waiting for a 15-minute idle timeout.

- **Published images keep durable notices for the external-intelligence CLIs** — VirusTotal, IPinfo, and urlscan license files are copied out of Go's temporary module cache into the image documentation directory, so repository-free verification checks the same notices that remain available at runtime.

- **Protected release smoke tests verify the exact image they pull** — The normal AMD64 lane keeps the GitLab registry digest attached through repository-free and bundled-tool checks instead of relying on a tag alias that a digest-qualified pull doesn't create locally.

---

## [2.5.0] - 2026-07-11

### Added

- **Operators can create comprehensive deployment backups** — `scripts/backup_system.py` now creates cron-friendly backups that resolve the effective app config, snapshot SQLite with the online backup API or dump Postgres with `pg_dump`, include `data_dir`, config overlays, `.env`, repeatable `--extra-file` paths, and enabled workspaces, then write restore notes, checksums, and a redacted manifest before archiving.
  - **Data storage:** the script records both the logical app `data_dir` and the physical backup source, so a host-run backup of the bundled Compose stack copies the host `./data` bind mount instead of falling back to the host's local `/tmp` path.
  - **Workspace storage:** the script records both the logical app `workspace_root` and the physical backup source, copying bind mounts from the host path and exporting Docker named volumes through Docker while requiring explicit opt-in for tmpfs/container-only workspaces even when the same tmpfs path exists on the host. When operators pass the same ordered Compose files they use for deployment, the script reads `WORKSPACE_ROOT` and resolves relative workspace bind mounts against the base Compose project directory; `--workspace-root` remains available when the logical app path needs to be supplied directly. If ephemeral workspace backup is requested while the app container is stopped, dry runs and backups report the unavailable container instead of claiming a host bind source.
  - **Container-aware database selection:** host-readable SQLite bind-mount backups continue to work with containers stopped. Auto Postgres backups use `docker compose exec` only when the database URL names a service in the supplied Compose stack; remote and host-reachable URLs keep using local `pg_dump` even when the bundled Postgres container is also running.
  - **Source permissions:** unreadable host bind sources now fail with backup-specific root/bind-mount guidance instead of a raw Python `PermissionError`, while failed runs still remove their lock file.
  - **Lock cleanup:** failed backup runs release and remove their `.backup.lock` file before returning, so a handled failure does not leave a stale lock path behind.
  - **Reliable output and preflight:** large files are checksummed in bounded chunks, microsecond backup names gain an exclusive sequence when needed, existing archives are never replaced, and `--dry-run` rejects the same missing env and extra-file inputs as a real backup before it creates an output directory or lock file.
  - **Tests:** added pytest coverage for SQLite snapshot behavior, Compose bind-mounted `data_dir` resolution, production Compose workspace override detection, live database exclusion from copied `data_dir`, extra/env file inclusion, dry-run input validation, missing extra-file opt-outs, unreadable bind-mount source guidance with lock cleanup, tmpfs workspace skips, stopped-container ephemeral workspace handling, bind-mounted workspace copies, Docker-volume copy command shaping, local and Compose Postgres dump selection, remote Postgres URL isolation from a running Compose service, chunked checksums, collision-safe archive and directory output, default gzip restore contents and checksum validation, retention reporting, stopped-service messaging, and manifest redaction.

- **HTTP and TCP ping tools are available in the shell** — The Docker image now includes Debian's packaged `httping` plus a pinned upstream `tcping` Go install, with command registry entries for examples, help, target/port autocomplete, and container smoke coverage for the recommended syntax.

- **WPScan can use a vault-backed API token** — `wpscan` now receives optional `WPSCAN_API_TOKEN` values from the encrypted secrets vault, while regular scans still run without a token and inline `--api-token` usage is blocked so keys stay out of command text.

### Changed

- **Bundled security tools are current for this release** — Container images now ship Go 1.26.5, Nuclei 3.11.0, httpx 1.10.0, cdncheck 1.2.43, TruffleHog 3.95.8, WPScan 4.0.1, and urlscan-cli 2026.07.07.

- **Initial shell startup and first-open surfaces are lighter** — The initial page now ships less inactive UI, while first-use surfaces still open with the same polished behavior.
  - Feature-owned styles for Projects, Atlas, Command Registry, Run Comparison, Schedules, Status Monitor, Watchers, Workflows, and Files load with their first-use modules instead of blocking the first shell paint.
  - Atlas and Projects mount their large modal shells from first-use HTML fragments, while Schedules, Watchers, and Findings Board create their modal shells when their feature modules load.
  - Finding triage, styled HTML/PDF export, terminal tour commands, and Files use lighter bridges or runtime gates so their full controllers stay off the initial shell path until needed.
  - Source asset mode keeps JS module URLs unversioned, generated bundle-mode ESM ships minified code with linked source maps, and hashed build assets serve committed Brotli/gzip siblings by content negotiation. Compression uses a stable source-size rule so committed asset checks stay consistent across supported CI environments.
  - Browser-facing fonts use WOFF2 on the shell path, `ansi_up.js` defers, and jsPDF still gets the TrueType files it needs for PDF export.
  - Projects starts controller imports, the first project list, and active-project context together; Atlas shows its overlay shell immediately, starts its summary/list requests early, and keeps detail/mobile/board controllers out of the first-open path.
  - **Tests:** route, browser-unit, asset, source-mode Playwright, and mobile Playwright coverage verifies the lighter shell, lazy fragments/styles, bundle/source URL contracts, compression, source maps, first-open behavior, and Files/triage/export/tour bridge boundaries.

- **Project and Atlas first-page reads are cheaper** — The hot list paths now match their indexes and avoid broad count work until callers need it.
  - Personal Atlas and Project reads use the same explicit personal-team predicate as their partial indexes, with startup normalization for legacy personal rows that still have `NULL` team IDs.
  - Project and Atlas first-open sort paths have dedicated SQLite/Postgres indexes, and run file artifact lookups use run-id-leading indexes where the existing primary key does not already cover the path.
  - Project list count loading rolls up the visible page from scoped run/entity links and indexed artifact/finding lookups instead of running the previous broad `COUNT(DISTINCT)` union.
  - Atlas entity and finding pages use `limit + 1` paging by default and defer exact totals/status buckets unless a caller asks for them; API v1 keeps exact totals for headless clients.
  - Initial shell boot and first-open modal paths share in-flight workflow catalog, Files list, and active Project context loads, and anonymous personal sessions skip the boot-only Teams refresh until team UI needs it.
  - **Tests:** SQLite/Postgres query-plan coverage, Project route coverage, Atlas route/browser coverage, and browser-unit tests verify index selection, exact-total opt-in, lower-bound pagination, Project count/finding summary parity, request coalescing, and current source/bundle asset contracts.

- **Performance diagnostics are safer and more useful** — Startup and first-use paths now emit bounded context when they fail without logging raw search text or query-string secrets.
  - Missing generated build assets, lazy module contract failures, Atlas/Projects preload/request failures, Project workspace action failures, and Files lazy-surface failures log structured event names with bounded IDs, route names, asset names, status, and timing context.
  - Project, Project metrics, and Atlas list services emit DEBUG-level timing and branch details for the new pagination/count paths so operators can troubleshoot regressions without turning normal large-list views into warning noise.

- **Docker deployments expose static inventory labels** — Built images and Compose containers now carry OCI and `sh.darklab.*` labels for app version, git revision, build date, Python version, configured database backend, and the metrics path.
  - The database-backend label uses the same `${DATABASE_BACKEND:-sqlite}` Compose interpolation the app receives, while live health, database size, and pool state remain in `/metrics`.
  - **Tests:** one pytest contract verifies the Dockerfile labels, Compose label interpolation, app/package version alignment, and Python base-image label source.

### Fixed

- **Operational and startup logs now preserve severity, config context, cleanup scope, and backup diagnostics** — Browser lifecycle events, configuration loading, destructive cleanup, and scheduled backups now leave an accurate troubleshooting trail without recording secrets, cleanup samples, or raw artifact data.
  - Configuration events emitted before runtime logging is ready are buffered and replayed once through the selected text or GELF formatter at the effective level. Ignored, dropped, defaulted, clamped, and truncated values all contribute to the startup warning count.
  - Fatal configuration failures emit one bounded structured fallback with phase, source, key, and error type. Raw parser details, configuration values, and tracebacks stay out of that path even when startup can't finish.
  - Import-time buffering doesn't attach a logger handler or change the logger level, and Intel missing-secret DEBUG events use a non-reserved context field, so side-effect-free imports and DEBUG provider lookups remain safe.
  - Browser `debug`, `info`, `warn`/`warning`, and `error` reports keep their intended server log levels; normal INFO events no longer increment the client-error metric, unknown levels fall back to WARNING, and bounded artifact IDs survive client-log sanitization.
  - History deletion and Project unlink INFO/audit events record the requested cleanup flags plus removed, curated, and kept entity/finding counts after cleanup completes.
  - Unexpected backup failures print their traceback, while `--keep-days` records its cutoff and candidate scan in the manifest, warns about inspection/removal failures, and prints examined, removed, and failure totals after a successful backup is published.
  - **Maintainability:** cleanup field shaping and snapshot persistence live in focused History and Project service modules, keeping the route and mutation modules inside their architecture size budgets.
  - **Tests:** fresh-process startup coverage verifies text/GELF output, DEBUG/ERROR thresholds, structured warning and fatal context, redaction, warning counts, and one-time replay. Route and backup coverage verifies the client level/metric matrix, artifact ID allowlisting, cleanup INFO/audit fields, retention summaries and inspection warnings, and unexpected-exception tracebacks.

- **Accepted command autocomplete roots now keep examples visible** — Choosing a command root such as `ping` from a partial match like `pin` now refreshes autocomplete after insertion, so the same example commands appear as when the root is typed manually.

- **First-open modal behavior stays polished after the startup trim** — The lazy shell changes now preserve the pre-trim visual and interaction details.
  - Theme selector alignment, Run Details entity rows, Project Runs/Findings placeholders, main-terminal Atlas entity highlights, and Atlas entity tab auto-selection render correctly on first load.
  - Atlas keeps its own fallback shell open while the first-use controller finishes loading, so the import dialog no longer closes itself while previewing a browser import on first open.
  - Atlas and Projects first-open prefetches settle quietly when an open is canceled or module loading fails, and fragment failures show a retryable error toast plus bounded client context instead of leaving a silent rejected promise.
  - The Project Report tab now preserves metadata typed while selector pages finish loading in the background, so preview/export keeps the current engagement name instead of occasionally rendering the default title.

- **Atlas cleanup previews and confirmations explain cleanup choices consistently** — Run deletion, Project unlinking, Project cleanup, and Atlas sibling-cleanup flows now use the same cleanup buckets and clearer copy.
  - Project cleanup, Project unlink, run deletion, and Atlas sibling-cleanup confirmations now explain disposable, kept-by-default, and not-eligible Atlas cleanup buckets with grouped reason labels; Project Runs tab removals still send the selected cleanup flags before summarizing removed entity counts.
  - Cleanup confirmations now treat explicit zero-count reason buckets as authoritative, so stale legacy compatibility counts cannot bring back empty Atlas cleanup checkboxes.
  - History run deletion now leaves optional Atlas cleanup unchecked by default, matching Atlas and Project cleanup confirmations.
  - Cleanup previews and confirmations carry compact display-only samples for kept-by-default and not-eligible rows, including Project unlink previews, and keep those samples collapsed until opened.
  - Kept-by-default run cleanup no longer deletes a parent Atlas entity when that would indirectly delete a child finding that is not eligible for the cleanup.
  - Atlas entity/finding sibling cleanup previews no longer count the row being explicitly deleted as not eligible, so selected rows do not block cleanup of their same-run siblings.
  - Team-scoped History cleanup previews and deletes now classify team-owned Project links and metadata by team ownership, so cross-member Project links keep the same Atlas rows in preview and apply.
  - Team-scoped History cleanup now applies the same team ownership scope during deletion, so Atlas rows previewed for cleanup are removed even when the row was first created by a different teammate.
  - Team-scoped Project run unlink previews now keep entity links when a reviewed child finding belongs to another teammate in the same team.
  - Pending command-discovered Project targets are treated as disposable same-run entities unless another keep signal exists, so fresh command targets do not pull same-run findings into the kept-by-default cleanup bucket.
  - **Tests:** a live History Playwright flow verifies all three preview buckets, unchecked cleanup defaults, sample disclosure, selected request flags, and the resulting Atlas entity and finding state.

- **Optimized Project and API paths keep their old behavior** — The performance work preserves the important edge cases around paging and team scope.
  - API v1 team Project finding lists include cross-member findings reachable through authorized team Project run/entity links, matching Project count and finding-summary rollups.
  - Project list pagination keeps limit handling active even when Python runs with assertions disabled.

- **Command-discovered `nc` Project targets keep hosts and ports separate** — `nc -zv` now treats the first positional value as the target host and later positional values as ports.
  - `nc -zv` command-discovered Project targets now treat positional ports as ports instead of hostnames, so values like `80` no longer become Atlas domain entities.

---
