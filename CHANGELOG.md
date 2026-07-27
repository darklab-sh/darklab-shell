# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.6.0
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.8.1] - Unreleased

### Fixed

- **Watcher runs now stay with the Project saved on the watcher instead of following the session's active Project.**
  - **Root cause:** the scheduler loaded the watcher before each fire but launched only from its owned schedule, dropping the watcher's Project id. Run finalization then used the session's current active Project, which could link the run and its captured evidence to an unrelated workspace.
  - **Fix:** watcher fires now pass their saved Project through the scheduled-run broker and explicitly disable active-Project fallback. Personal and team watchers link external runs to their own Project, while unassigned watchers remain unassigned even if the session has another active Project.
  - **Tests:** existing scheduler, watcher, broker, and Project-scope cases now cover the Project handoff, personal and team assignments, unassigned watchers, finalization without active-Project fallback, and unchanged active-Project behavior for ordinary runs without increasing the test count.

---

## [2.8.0] - 2026-07-26

### Changed

- **Built-in terminal commands now use an immutable registry for resolution, execution, autocomplete, and rich discovery.**
  - **Before:** app-owned helpers depended on separate resolver, dispatch, feature-gate, catalog, and autocomplete sources, while `commands info` and `commands search` could only describe external tools.
  - **After:** one reviewed provider list builds and freezes the registry before request handling. Focused command families now own their handlers, help text, catalog details, aliases, feature requirements, ownership, and full autocomplete grammar; the old central dispatch, catalog, and autocomplete sources are gone. Duplicate identities fail at registration, feature gates are metadata-driven, safe workspace aliases keep resolve-time validation before execution-time scope and role checks, and handlers share a typed context that resolves configuration and owner scope only when requested. Browser-owned commands remain browser-executed while still appearing in backend discovery and stale-client fallbacks, and built-in info/search results now include structured flags, arguments, examples, and subcommands.
  - **Tests:** registry contracts pin provider extension without executor changes, duplicate rejection, immutable metadata, feature gates, lazy memoization, browser/server ownership, nonzero exits, safe two-step workspace aliases, the complete pre-migration root and exact-alias sets, and parity across runtime resolution, help, rich details, search, catalog, and autocomplete. Existing direct, scheduled, workflow, workspace, team-scoped, and special-command paths continue through the shared resolver and executor.

- **Terminal commands now share one completion lifecycle without changing where they execute.**
  - **Before:** browser-owned commands relied on a pipe wrapper that temporarily replaced output, status, recents, and persistence helpers; workflows completed through a separate direct path; and brokered commands repeated similar logic in the SSE exit handler.
  - **After:** browser-owned handlers return normalized output and requested follow-up work, while server-owned commands keep streaming through `/runs`. One exactly-once coordinator now settles transcript output, tab and HUD status, eligible recents, notifications, refreshes, and `/run/client` persistence. `/run/client` returns the saved run summary, and successful browser-owned recents use that response's command instead of a separate optimistic copy. Prompt history remains available at submit time after client checks, while recents remain completion-time state. Server-run recents use the masked command instead of retaining sensitive raw arguments, and queued legacy workflows leave status ownership with the command they launch instead of briefly reporting success before it runs.
  - **Tests:** six new Vitest cases cover the result contract, buffered and streamed ownership, exactly-once rendering and persistence, saved-run hydration, masked server recents, submit-time prompt-history eligibility, confirmation completion, and Files commands after removal of pipe monkey-patching. Existing workflow tests now execute the production lifecycle branches for legacy queues, durable runs, sensitive inputs, status, and cancel behavior.

- **The main pages now share one lightweight Jinja document shell.**
  - **Before:** the shell, permalink base, diagnostics, and audit log each repeated their own doctype, root elements, shared metadata, favicon, application styles, theme variables, and body theme attribute.
  - **After:** `base.html` owns that stable frame, while each page keeps its own title, extra assets, body classes, content, and scripts. Permalink content and error pages still extend `permalink_base.html`, preserving their existing second inheritance level without pulling page-specific behavior into the shared base.
  - **Tests:** route coverage pins one complete rendered document, page title, body classes, theme, and asset contract for the shell, permalink, permalink-error, diagnostics, and audit pages in the existing source and bundled modes. A repository guard rejects duplicate document markup or a broken inheritance boundary without changing the test count.

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

- **`v2.8.0-rc.1` completed the full dual-platform release qualification.** — The previous release cycle already supplied the required three consecutive protected dual-mode candidate pipelines without manual repair. RC1 produced matching native images, registry indexes, signatures, checksums, provenance, SBOMs, release evidence, and installer payloads; passed the installer, Postgres backup and restore, enabled SELinux Docker and rootless Podman lanes, and anonymous public checks; and passed clean installation, upgrade from `v2.7.0`, health, bundled-tool, SQLite, Postgres, backup, restore, and unsupported-architecture checks on native AMD64 and ARM64 hosts.

### Fixed

- **Branch image builds now reuse the shared AMD64 Docker cache.**
  - **Root cause:** the branch image job built without a cache import and resolved its Python base from the bare tag, which selects the image index digest, while the scheduled cache warmer and fanout jobs pin the amd64 child manifest digest. The two paths therefore built separate cache chains, so a branch build missed every warmed layer starting at the first toolchain `RUN` — a step that depends only on the base image and its command rather than on any source change.
  - **Fix:** the branch job now resolves the same amd64 child digest, imports the stable `buildcache-amd64` reference read-only, matches the platform and provenance flags, and builds from the same tracked Git archive context. Toolchain stages that run before any source copy restore from the warmed cache instead of rebuilding after each runner's scheduled prune.
  - **Tests:** the existing CI contract now also pins the branch job's read-only cache import, pinned amd64 base digest, shared archive context, and absence of a cache export alongside the warmer and fanout assertions, without changing the test count.

- **The shared AMD64 Docker cache now survives SELinux-hosted checkouts.**
  - **Root cause:** BuildKit included checkout metadata in `COPY` cache keys, so Fedora's `security.selinux` labels changed the first source-backed layer on `baku` and forced every later Go tool stage to rebuild despite a successful registry-cache import.
  - **Fix:** scheduled Docker cache writers and readers plus protected image publication now feed BuildKit the same tracked Git archive with fixed file modes. Host ownership, timestamps, ACLs, and xattrs stay outside the build context, while Git's executable bits remain intact. Rootless Podman keeps its separate local-store path.
  - **Tests:** the existing container and CI contracts inspect the normalized archive, pin executable and regular-file modes, reject archived xattrs, require the stdin context on every shared-cache BuildKit path, and keep Podman separate without changing the test count.

- **Nuclei no longer embeds a vulnerable kin-openapi release.**
  - **Root cause:** Nuclei 3.11.0 still selected kin-openapi 0.132.0, which contains an authentication-bypass flaw and caused the required Critical vulnerability scan to fail.
  - **Fix:** the image build raises kin-openapi to 0.144.0, applies the two-line Nuclei compatibility change needed for that API, and verifies the selected version is also embedded in the finished binary. The reviewed patch and dependency license are included in release provenance instead of suppressing the finding.
  - **Tests:** the Go installer contract covers dependency floors, patch application, and selected-versus-embedded version mismatches; the container cache and release-evidence contracts track the helper and patch; and a real ProjectDiscovery-stage build confirms Nuclei 3.11.0 compiles with kin-openapi 0.144.0.

- **Development tooling no longer installs vulnerable Brace Expansion, js-yaml, or PostCSS releases.**
  - **Root cause:** compatible dependency ranges still resolved to affected Brace Expansion and PostCSS versions, while Markdownlint pinned the affected js-yaml 5.2.1 release even after the project selected a newer parser.
  - **Fix:** the dependency policy now requires Brace Expansion 5.0.8 and PostCSS 8.5.23, pins the direct js-yaml dependency to 5.2.2, and narrowly overrides Markdownlint's parser dependency to the same compatible patched release. Markdownlint stays on 0.23.1 instead of taking npm's forced downgrade.
  - **Tests:** the JavaScript dependency audit reports no vulnerabilities, the resolved dependency tree contains only the patched releases, and the affected theme parsing, Markdown lint, CSS lint, and asset-build paths remain green.

- **Source-mounted development now starts reliably from private Linux checkouts.**
  - **Root cause:** `compose.dev.yaml` bound `./app` directly over `/app`, so native Linux preserved host ownership and modes such as `0600` after the container dropped to `appuser`.
  - **Fix:** development mounts the checkout read-only at `/opt/darklab-source/app` and gives `/app` an ephemeral tmpfs. The root entrypoint stages a fresh `appuser`-owned snapshot, preserves private read access, removes every write bit, and fails before config or workers start if staging can't complete. Production keeps using the bundled `/app` tree without a source bind or staging trigger.
  - **Tests:** the Compose contract pins the separate source and runtime paths, a focused helper test covers owner-only files and fail-closed startup, and the opt-in Linux container smoke verifies an actual `0600` `config.py` becomes readable but not writable before the app starts.

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
