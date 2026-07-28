# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.7.0
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.8.2] - Unreleased

### Fixed

- **Production lifecycle commands now keep operator Compose overrides active.** When `compose.operator.yaml` exists beside the installed stack, `darklab-deploy` includes it for backup, restore, database migration, upgrade validation and printed restart commands, and removal. Restored containers no longer restart from the release-owned base alone.

- **History bulk deletion now follows the active filters and previews the exact number of affected runs.** The confirmation shows matching and non-favorite totals, and both desktop History and mobile recents delete the complete filtered result set instead of clearing unrelated runs or processing only the first page.

- **Unassigned watcher Project scope is now represented consistently in run-finalization type hints.** This removes a false editor error from the watcher-scope regression coverage without changing runtime behavior.

---

## [2.8.1] - 2026-07-27

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
