# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.3.1
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.7.1] - Unreleased

### Changed

- **Container logging guidance now keeps remote transport outside the app's Compose stack** — the operator docs still explain how to emit structured GELF JSON on standard output, but no longer recommend Docker's direct GELF driver or the retired `DOCKER_GELF_ADDRESS` setting. A host-local collector can forward container logs without making application startup depend on the remote log service.

- **Files now feels like a compact file browser instead of a stack of oversized cards.**
  - **Before:** folders, files, and the parent directory each occupied a large card with repeated action buttons, while quota details and linked-record context were packed into general metadata text.
  - **After:** the modal uses a dense, responsive browser with folders first, familiar columns, file-type icons, breadcrumbs and an Up control, client-side search and sorting, separate quota indicators, and one accessible overflow menu per row. A compact `..` row appears outside the Files root so users can open the parent folder or drag files and folders back into it. Clicking anywhere outside a row's overflow actions selects its file or opens its folder, while file names remain the keyboard-accessible primary controls with a clean text-only hover state and a separate focus outline. Every row retains its lower separator, so selected files use the same complete highlight even at the bottom of the list. The sort menu expands inward so every option stays inside the modal and viewport. On desktop, selecting a file opens an in-place inspector with a bounded quick preview, metadata, linked runs and projects, labels, notes, and common actions; narrow screens continue opening the focused full viewer. Linked projects and runs stay easy to scan, read-only team actions explain why they're unavailable, and mobile keeps the same controls in a compact two-column row.
  - **Tests:** workspace and shared-select unit coverage pins sorting, filtering, full-row activation, parent navigation and drag-to-parent moves, desktop inspector content, right-edge menu placement, timestamps, quota state, and keyboard-operated action menus; Playwright exercises the live desktop inspector, bounded preview layout, full viewer, consistent middle/final-row selection borders, full-row file/folder/parent activation, viewport-safe sort menu, and narrow-screen viewer flow in source and bundled asset modes.

- **Scheduled Docker fanout now hydrates every Docker runner from one shared AMD64 cache.**
  - **Before:** `bael` alone wrote a release-line-specific registry cache, while the remaining fanout jobs performed unrelated local builds that couldn't reuse it.
  - **After:** one prerequisite cache warmer can run on any standard self-managed Docker runner and writes the stable `buildcache-amd64` reference under the same lock as release publication. Once it succeeds, every standard and SELinux Docker runner imports the recorded cache and pinned Python base digest read-only while the fanout runs concurrently; the rootless Podman job keeps its separate image store.
  - **Tests:** the existing CI contract pins the prerequisite stage, generic cache reference, fixed writer lock, runner-agnostic warmer, read-only fanout imports, and the complete host-tag map without changing the test count.

- **Contributor branches now merge into `main`, while release branches are reserved for short stabilization windows** — the documented lifecycle cuts `release/MAJOR.MINOR` only after the release scope is complete, routes candidate fixes through merge requests, freezes unrelated `main` merges during RC validation, merges the finished release back into `main`, and tags that exact merged commit before retiring the release branch.

### Fixed

- **Rate-limit GELF events no longer conflict with numeric OpenSearch fields.**
  - **Root cause:** worker and output events correctly recorded numeric values under `limit`, while `RATE_LIMIT` reused that field for descriptions such as `240 per minute; 60 per second`. GELF serialized both as `_limit`, so OpenSearch's numeric mapping rejected the descriptive rate policy.
  - **Fix:** `RATE_LIMIT` now records its human-readable threshold as `limit_policy`, leaving `_limit` consistently numeric for existing events.
  - **Tests:** existing Flask-Limiter, baseline HTTP guard, and GELF formatter assertions pin `_limit_policy` and reject the old string-valued `_limit` shape without changing the test count.

- **Fresh Redis-backed live replays no longer show a false trimmed-output warning.**
  - **Root cause:** Redis read the newest retained events and then queried the stream length separately, so an active command publishing between those requests could make a short replay look truncated.
  - **Fix:** replay now requests one extra tail record in the same Redis read and treats only that extra oldest record as proof that the retained window omitted earlier events.
  - **Tests:** focused broker coverage exercises genuine tail truncation, the former active-stream growth race, the retained-event warning count, and the absence of the second Redis length query.

- **Release signing tolerates registry signature propagation without adding duplicate signatures on job retries.**
  - **Root cause:** the supply-chain job verified each image immediately after signing it, but Docker Hub could accept a signature before making it visible to the following verification request. Retrying the job then signed targets that had already completed successfully.
  - **Fix:** each release target first reuses an existing signature that matches the protected tag identity. Missing signatures are created once, then verification polls with bounded exponential backoff while registry referrers become visible.
  - **Tests:** the existing release-pipeline contract pins the reuse check, sign-once ordering, bounded retry count, and backoff behavior without adding a new test case.

---

## [2.7.0] - 2026-07-22

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

- **Release tags publish one native image for Linux AMD64 and ARM64** — Protected tag pipelines resolve one Python base index, build and scan each architecture on a native runner, and assemble the verified child digests into one immutable GitLab OCI index before copying the same index to Docker Hub. The installer manifest, image verifier, SBOMs, vulnerability reports, provenance, signatures, public smoke checks, and release evidence all retain the canonical index digest plus the selected child and platform-base digests. Dual-platform publication fails closed when either child is missing; a manual protected AMD64-only emergency release requires a public reason and stays permanently single-platform. SELinux Docker and rootless Podman remain AMD64 compatibility claims, and ARM64 stays uncached on the storage-limited hosted runner. Three protected rehearsals exercised both native children without publishing release artifacts; the uncached ARM64 lane completed within 50.75 percent of its timeout and retained at least 23.62 percent free storage against its accepted 20 percent floor. A disposable GitLab registry exercise used the production cleanup code to remove both temporary children and the staging index while the canonical index and durable architecture anchors kept their exact digests and remained runnable for both platforms.

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
