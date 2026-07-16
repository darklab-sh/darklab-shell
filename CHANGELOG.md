# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.3.1
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.6.0] - Unreleased

### Added

- **darklab_shell is explicitly licensed under GNU AGPLv3** — Project-owned source and documentation use `AGPL-3.0-only`, while bundled tools and other third-party material keep their own licenses.
  - **Included notices:** the full project license ships in the repository, container, and installer payload. Third-party terms remain listed in `THIRD_PARTY_NOTICES.txt` and `container-licenses.json`.
  - **Source access:** official builds link to their exact source tag from the app. Operators who publish a modified network version must point that link at the corresponding source and follow the license's source-offer requirements.

- **Self-hosted releases install without a repository checkout or local image build** — A checksummed installer creates a small production directory that runs an exact release image while keeping application code inside the image.
  - **Install and configuration:** production binds to host loopback by default, stores private operator overlays under `conf/`, and mounts only configuration and durable state. Shipped defaults stay in the image, so upgrades don't hide new commands, workflows, themes, or other catalogs.
  - **Release verification:** the release publishes matching GitLab and Docker Hub image digests, checksums, signatures, an SBOM, vulnerability results, provenance, and a build-input inventory. The installed verifier rejects image or managed-file drift, while publication validates the complete license inventory, required notice paths, and hash-pinned Nmap and WPScan license texts.
  - **State and lifecycle:** `darklab-deploy` reports status, makes and verifies SQLite or Postgres backups, restores after taking a safety backup, upgrades only to an authenticated newer release, explains clone-backed migration, and removes release-owned files without deleting operator state.
  - **Supported runtime:** Docker Compose 2.20.0 or newer on Linux AMD64 is the production target. Postgres and the local model remain optional, Redis stays disposable, and raw-packet scanning stays opt-in. ARM64, SELinux, and rootless Podman have dedicated release gates but don't expand the supported matrix until those gates are enabled and pass.
  - **Validation:** release coverage exercises installer safety, private overlays, matching registry digests, immutable artifacts, repository-free startup, durable restarts, and a bundled-Postgres backup/restore round trip before the final release is created.

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
  - **Reference ownership:** FEATURES stays user-focused, ARCHITECTURE keeps stable runtime and front-end design contracts, CONFIGURATION owns the supported-runtime matrix, and related-doc sections link only to the most useful next pages.
  - **Release history:** the root changelog keeps the active release plus the two newest dated releases, with older entries preserved intact in major-version archives.
  - **Validation:** offline link and heading checks, table-of-contents checks, published-release integrity hashes, support-matrix executable-contract checks, and focused durability guards protect the new structure.

- **Protected release builds reach compatibility verification sooner** — Tag pipelines skip the redundant branch image build, volatile image labels are applied last, and native ARM64 validation builds beside the canonical AMD64 image while the ordinary test, lint, and audit jobs remain unchanged.

### Fixed

- **Pre-commit shell checks match the full repository lint scope** — The hook now uses the same ShellCheck command as CI, including deployment shell templates, and the release smoke helper avoids an ambiguous conditional that ShellCheck correctly rejected.

- **Release image smoke checks use paths and privileges that match their runners** — Docker-socket jobs translate build paths to the host daemon's view, native rootless and SELinux jobs restore temporary bind-mount access before cleanup, and bundled-tool verification grants the raw-network capabilities required to execute Naabu on ARM64.

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

## [2.4] — 2026-07-06

### Added

- **URL entities now stay linked to their host** — Captured or imported URL entities now create and store a scoped relationship to the matching domain or IP entity, so Project Overview and Atlas can roll URL evidence up through the host without reparsing every URL later.
  - Generic output extraction records the URL itself plus its host, direct URL target discovery such as `curl https://ip.darklab.sh` creates the Atlas URL and host link, and startup backfills older URL rows on SQLite and Postgres through the same canonical URL-host parser when the host can be resolved safely.
  - Command-discovered URL project targets keep source-run provenance after Atlas output materialization, and their derived hosts get the same run link, so fresh command targets no longer appear only as orphaned Atlas URLs.
  - Bracketed IPv6 URL hosts stay bracketed in canonical URL values and link to the matching IP entity instead of creating a bogus domain from the first IPv6 segment.
  - Generic extraction keeps its private-IP filtering policy for URL hosts too, so a private or loopback IP URL is ignored unless the caller explicitly opts into private IP capture.
  - Atlas domain and IP detail views now list related URL entities and let you open the URL entity from the host context.
  - **Tests:** focused backend coverage verifies URL extraction, materialized URL host relationships, direct URL upserts, Project target discovery, route-created URL targets, URL-host backfill, Overview's stored host-link behavior, team-scoped Overview host evidence, bracketed IPv6 URL hosts, and the live extractor-to-materializer path so URL hosts are not double-counted.

- **Atlas port entities from scan output** — Atlas now captures open ports as first-class app-native entities from supported scanner output.
  - Nmap, masscan, rustscan, naabu domain/IP output, `nc -zv`, and curl connection lines can emit host-linked `port` entities with canonical `host:port/proto` values; `nc -zv` failed reverse-DNS output uses the bracketed IP as the port host, and nmap service/version/banner data survives persistence as lightweight port attributes.
  - Scanner-scoped port extraction records private/internal targets when the user-directed scanner output reports them, while generic entity extraction keeps its separate private-IP filtering policy.
  - Postgres materialization now writes port attributes through the JSONB adapter path, so service/version/banner metadata saves correctly outside SQLite.
  - Atlas and Project Entities gain a Ports tab/filter, port rows and detail views surface protocol/service/version/banner and host-link metadata, generic CSV/JSONL imports accept full `host:port/proto` port rows, CSV/JSONL exports include port host metadata plus decoded `attributes`, and provider intel refresh stays hidden for ports because they are app-captured evidence rather than external-provider lookup targets.
  - Atlas port detail action menus open as viewport-positioned dropdowns and close on outside click or Escape, and entity rows keep their compact default height while expanding when long ports, hashes, URLs, or metadata need to wrap.
  - Supported port-scan runs record app-native scan target observations, including command-target-only scans that surface no ports, so Project Overview can distinguish untouched targets from targets scanned by the app with no surfaced ports.
  - Deleted runs now remove their app-native scan target observations, so Project Overview does not count scan evidence after its source run is gone.
  - Project Overview labels cached-provider ports separately from app-captured scan coverage and shows app-native port evidence without claiming that a scan with no surfaced ports proves no ports exist. Provider/app drift only appears when there is cached provider intel to compare, and app-native totals count all distinct captured ports even when the visible per-target list is capped.
  - Project Overview now renders finding review and verification progress from app-captured finding counts, with false-positive, suppressed, and not-applicable findings shown outside the main funnels.
  - Project Overview now shows operational tempo from linked runs, triage updates, and run artifacts, plus a short recent-activity strip that jumps into the matching project workspace tab.
  - Project Overview now surfaces app-data coverage gaps for targets with no app-captured scan, targets awaiting verification, and targets needing review or follow-up, with deep-links into the existing project tabs.
  - Project Overview now renders app-captured ports and service/version metadata as the primary port signal, keeps cached-provider ports as a labeled cross-reference, flags provider/app port drift for scanned targets, uses host-scoped app port evidence for URL targets when the host entity is known, separates positive port-evidence run counts from scan-coverage observations, and opens drift actions on the host-filtered Project Entities Ports tab with a clearable host chip when the displayed ports are linked into the project.
  - Project Overview now uses primary/secondary summary groups, brings target rows higher in the tab without burying aggregate panels under long target lists, renders app-captured ports as compact chips, and presents per-target provider, intel, scan, and finding details as labeled rows.
  - Project Overview now uses a denser dashboard-first layout: aggregate panels sit above the target worklist, summary cards are grouped by coverage/evidence/risk, target rows lead with severity and finding work, repeated no-data rows collapse into a compact muted line, and an optional worklist toggle hides unscanned targets with no findings while showing how many targets are currently visible.
  - Project Overview now shows deliverables status for latest package save/build, report save/export, and report freshness against the latest finding activity.
  - Project Overview now makes the cached-provider boundary clearer by labeling provider-backed port/service counts, adding a cached-provider caveat, and showing each target's provider freshness or no-intel state with the latest checked timestamp when available.
  - Atlas now exposes project scope as a first-class filter with a project selector and clearable chip. Project-launched Atlas opens show the applied project, saved views keep project scope, and the project chip or **Clear filters** can remove the scope.
  - Project Findings rows now open the selected finding in project-scoped Atlas instead of dropping straight back into the terminal, while an explicit **See in run** action opens the source run in Run Details on desktop and mobile.
  - **Tests:** focused backend coverage verifies port canonicalization, scanner extraction including private/internal scanner targets, SQLite/Postgres attribute materialization, materialized host relationships and attributes, Project Entities port metadata payloads, command-target and quiet-scan observations, run-deletion cleanup, masscan/curl scan-coverage boundaries, Project Overview app-scan evidence, app port/service rollups, provider/app drift, project-backed port drill-in hints, curl-derived app-port run counts, URL host-scoped port evidence and scan-state nuance, defensive app-port row filtering, capped-list total counts, operational tempo, recent activity, coverage gaps, deliverables status, and generic CSV import support; focused browser-module and Playwright coverage verifies port metadata row/detail rendering, host-filtered Project Entity requests and chips, Overview app-port rendering and scoped port badge assertions, dense Overview worklist rendering and filtering, project-backed Ports actions, real endpoint app-port drill-ins, app-port run-count copy, finding progress, provider caveats, provider freshness, tempo, activity, coverage-gap, deliverables rendering, Atlas project-filter controls, and Project Findings row/source-run actions.

- **Typed configuration loading with validated settings** — Config loading now returns a pydantic-backed `AppConfig` mapping with typed nested sections, deep-merged local overlays, unknown-key warnings, fatal malformed YAML/root-shape errors, redacted validation errors, schema-validated mutation semantics, normalized test overrides, and startup logging that no longer replays ignored-key warnings under the retired local-load-failure event.
  - Recoverable coercions and fatal load failures log structured key/source context, and config object representations redact secret-looking values by default.
  - **Docs:** `CONFIGURATION.md` documents the config resolution order, schema posture, nested sections, forgiving/coerced fields, derived byte-count keys, redaction behavior, and `config.local.yaml` restart behavior.
  - **Tests:** loader and architecture coverage pins unknown top-level/nested keys, malformed root and local config files, partial nested overlays, typed nested attribute access, forgiving field coercion, secret redaction for top-level and nested paths, provider-name redaction false positives, mapping compatibility, mapping-compatible section helpers, override-derived normalization, startup config logging alignment, runtime mutation validation, nested-section fail-fast errors, and the guard against unapproved bare-dict `CFG` replacement sentinels. A shared `build_test_config(...)` helper keeps wholesale test replacements validated.

- **Workspace file autocomplete uses a dedicated path value type** — Workspace move commands now use `workspace_path` for `mv` and `file move`, so files and folders autocomplete from the active workspace without being treated as scan targets.
  - Workspace paths no longer prepend recent/project targets, no longer create bogus filename-based project targets after a run, and no longer trip `restricted_command_input_cidrs` when a workspace path looks like an IP address.
  - Autocomplete for workspace file input flags such as `nmap -iL`, `masscan -iL`, and `nuclei -l` now stays scoped to session files instead of prepending active project targets before a filename is typed.
  - Older runs may already have created filename-shaped project targets; operators can remove those manually from the Project target list when they see them.

### Fixed

- Runtime-injected command flags with no explicit position now keep the pre-split behavior of inserting immediately after the command root instead of drifting to the end of the command.
- Split run and diagnostics route modules now import cleanly on their own, so route registration no longer depends on a fragile parent-first import order.
- Atlas lookup routes now propagate patched database backends into the split lookup helper modules, so Postgres route tests and runtime paths use the intended dialect after the decomposition.
- Project artifact and evidence-package query wrappers now propagate patched database connections into their split helper modules, preserving the established Postgres test seam after the decomposition.
- Workspace cleanup now routes failed scanner-user `rm -rf` fallback attempts back through the inactive-workspace repair flow with bounded helper stderr, so stale scanner-owned files no longer cause repeated `WORKSPACE_CLEANUP_ERROR` loops.
  - **Tests:** added regression coverage for a scanner-owned workspace child where appuser removal fails, scanner-user removal returns non-zero, repair runs, and the expired workspace is still removed.
- Diagnostics helper compatibility exports now stay visible on `blueprints.assets`, so existing route tests and monkeypatch seams keep working after the assets route split.
- Search discoverability refresh no longer crashes in jsdom teardown or other partial DOM environments when the global `Element` constructor is temporarily unavailable.
- Existing SQLite databases that reached the current schema before the unified migration ledger now stamp cleanly when the only drift is SQLite's legacy inability to add `watcher_fires` table-level `CHECK` constraints after table creation.
- Scheduler recovery no longer misreports Redis as unavailable on startup. The scheduler worker now initializes the same process-level Redis state as the web workers before it fires missed schedules, and the run broker reads that Redis state dynamically instead of keeping a stale import-time copy.
- E2E coverage is more deterministic: status-monitor and session-token autocomplete checks no longer depend on external DNS resolving `darklab.sh`, run-comparison scroll-sync coverage uses test-owned overflow so flex/grid settlement on a loaded worker cannot invalidate its precondition, and Atlas browser flows wait for the lazy-loaded controller to be ready before interacting with it.
- Command output flags now prepare workspace write targets as `scanner:appuser` files, so scanner tools can truncate app-created placeholders without hitting permission errors.
- The Commands modal category strip now hides the native horizontal scrollbar and uses tab-style arrow scrollers when the category list overflows.
- Generic command-output hostname extraction now uses an offline Public Suffix List gate plus conservative file-context checks, so dotted code identifiers such as `classlist.add` and `document.queryselector` no longer become Atlas domains while real domains and URL/scanner-specific capture paths keep their existing behavior.
- App-launched `curl` runs now suppress curl's progress meter by default, so headers and response bodies don't get mixed with progress rows in the terminal transcript while explicit silent/help/progress modes stay unchanged.
- The team-scope menu now keeps the last loaded team list visible if a later refresh fails, so a temporary `/session/teams` hiccup no longer removes selectable teams from the active-scope dropdown.

### Changed

- **Backend modules now have focused ownership boundaries** — Oversized blueprint, route, command-registry, run, history, workspace, Atlas, Project, PTY, output-signal, diagnostics, and import helpers now live in smaller modules with the same public import surfaces for callers.
  - Project, API v1, Atlas, assets, run, and diagnostics routes keep their existing blueprint registration points while their route groups live in focused modules.
  - Command registry, History queries, Atlas lookup/import helpers, Project Overview/query helpers, Workspace services, PTY services, run lifecycle helpers, and output-signal parsing now keep domain-specific logic in focused modules instead of large catch-all files.
  - Module-size ratchets and parent-import compatibility tests guard the split modules so future changes keep the same boundaries.
  - Command, workspace, run, API streaming, and diagnostics helpers keep operator-visible breadcrumbs for YAML load failures, workspace migration/cleanup degradation, process signaling, run finalization degradation, NDJSON stream fallback, and partial Redis diagnostics probes.

- **Shared process dependencies now use explicit access helpers** — Mutable database, Redis, and config state flows through shared accessors instead of local singleton copies that can go stale after tests, workers, or bootstrap code replace the source state.
  - Redis client access uses one shared `core.process.RedisClientProxy` for assets diagnostics, runtime status built-ins, and PTY service aliases, preserving test monkeypatch visibility without three duplicated proxy classes.
  - App code reads database backend/connect state through shared lazy accessors instead of direct `core.database` imports, and the split Atlas lookup, project query/list/package, and history mutation helpers no longer need parent modules to copy patched DB values into child modules.
  - Built-in command modules, permalink rendering, classifier-drift diagnostics, metrics helpers, PTY helpers, scheduler and watcher quota helpers, notification helpers, project digest/metadata/package helpers, report helpers, run lifecycle/scope/broker helpers, audit helpers, Atlas import/intel helpers, app-native intel helpers, AI helpers, workspace helpers, runtime bootstrap, and core request/theme helpers now read mutable config through `resolve_effective_cfg()` or explicit caller-provided config instead of stale local `CFG` aliases.
  - Run-start and broker startup paths log dependency-resolution failures before subprocess or stream handling begins, and broker/Redis availability logs include enough context to distinguish deliberate disabled states from missing or degraded dependencies.
  - Architecture and contributor docs describe the shared Redis proxy, database accessor, and effective-config helper conventions, while architecture tests guard against new local DB, config, Redis, alias-style rebinding, duplicate Redis proxy singleton bindings, and module-qualified `database.CFG` reads.
  - Worker, Redis-consumer, and split database-helper tests prove late source-owner dependency replacements are observed after module import, covering worker config, Redis process state, and lazy database connection access across the migrated seams.
- **Flask app startup now uses the application factory contract** — `app.create_app(...)` assembles Darklab's blueprints and hooks around `app_factory.py`, while runtime startup work such as logging, metrics setup, Redis initialization, `db_init()`, and guarded active-run metadata cleanup runs through explicit bootstrap helpers.
  - Gunicorn and the Playwright server boot through `wsgi:application`, pytest route clients build factory apps, and imports stay side-effect-free until bootstrap runs.
  - Metrics imports are lazy so Prometheus initializes after the bootstrap-created multiprocess directory exists.
  - Startup, request, database, worker, and Gunicorn logs carry clearer runtime, request-id, process, startup-stage, and cleanup context.
  - Factory regression coverage pins Flask config overrides, per-app hooks/error handlers/static asset resolution, the local `python app.py` launch path, and AI worker bootstrap ordering.
- Pytest factory helpers now skip redundant SQLite initialization when the active test database already has the core schema, so route/client-heavy tests keep using factory-built apps without rerunning startup maintenance for every client.
- **Project targets now use the same `domain`, `url`, and `ip` vocabulary as Atlas** — `host` is no longer presented as a separate target type, while legacy `host` API/import inputs are still accepted as aliases and resolve to `domain` or `ip`.
- **Data access now lives behind service-owned helpers instead of blueprint SQL** so route files stay focused on HTTP parsing, capability checks, service calls, and response shaping.
  - **Blueprint boundary — direct persistence is a hard ban.**
    - Contract: blueprints may not open database connections, call execute-family methods, build SQL-shaped strings, import backend/dialect symbols, or call persistence cleanup helpers.
    - Migrated: the previous team, watcher, schedule, project, Atlas, run, workspace, asset diagnostics, history, session, and API v1 route persistence paths now call service helpers.
    - Removed: the old per-module ratchet allowlist is empty, so new persistence access under `app/blueprints/` fails the architecture suite.
    - Test coverage: `tests/py/test_architecture.py` catches direct and aliased `db_connect`, execute-family calls, SQL-shaped fragments, core database imports, backend/dialect imports, and blueprint subpackages.
  - **Service ownership — shared helpers own query and transaction boundaries.**
    - Contract: service functions open their own connection by default, while multi-step workflows can use service-layer transaction/read wrappers from `services.storage.transactions`.
    - Migrated: history list/search, stats, insights, compare metadata, delete/export/share operations, run persistence, workspace metadata, asset diagnostics, and session state storage moved into domain services.
    - Removed: blueprint-owned commits, rollbacks, owner predicates, and dialect decisions for those paths.
    - Test coverage: service-level pytest coverage now checks history list metadata shape, team-scoped workspace metadata move/delete behavior, diagnostics partial-probe responses, and session migration counts/cleanup across runs, snapshots, stars, preferences, variables, workflows, projects, notifications, recent values, and secrets.
  - **API v1 reuse — headless routes use domain services rather than a parallel API query layer.**
    - Contract: `services/api_v1` stays focused on auth, serialization, and OpenAPI, while history, Atlas, team, schedule, watcher, project, artifact, and run persistence lives with the matching domain service.
    - Migrated: API history/output/detail, Atlas, team, schedule, watcher, artifact, and project-link reads and writes route through shared service helpers.
    - Removed: API route-level database imports, connection opens, execute calls, and API-owned owner-clause helpers.
    - Test coverage: API tests cover output fallback logging/source metadata, token/team scoping, route payloads, and the architecture suite protects the `services/api_v1` non-persistence boundary.
    - Net delta: the documented suite total is now 4,017 tests.
- **SQLite and Postgres now share one schema-management path** — Fresh installs enter through the unified `0039` baseline, existing Postgres ledgers through `0038` verify the live schema before stamping the baseline marker, and SQLite startup verifies current pre-ledger databases before stamping.
  - SQLite remains the source schema, Postgres fresh installs render the generated baseline from that source, and future database changes ship as post-baseline migrations.
  - Schema work routes through the shared migration helper with backend-aware ledger DDL, dialect-specific statements, per-migration commit/rollback boundaries, transaction-scoped advisory-lock refreshes on Postgres, and shared post-schema maintenance afterward.
  - Unsupported pre-ledger SQLite schemas fail closed with a concrete bridge path: start once with `darklab_shell` 2.3.1 so the retired compatibility ladder reaches current head, then move to the unified schema-ledger path.
  - The drift guard compares both backend heads for missing or extra tables/columns and normalized column shape, while the stricter baseline-equivalence test checks generated Postgres columns, constraints, and indexes against the authoritative migration head.
  - SQLite's `session_preferences.preferences` default now matches the Postgres baseline, and SQLite startup rebuilds `runs_fts` in the same transaction when legacy `output_search_text` is backfilled.
  - Schema startup logs distinguish executed baseline DDL from stamped legacy ledger rows, name SQLite/Postgres init branches, record advisory-lock waits and post-schema maintenance steps, and include bounded DDL previews when a migration fails.
  - Contributor, architecture, decision, and migration docs describe the current SQLite-source/Postgres-generated model and the release gate for future schema changes.
- Frontend inventory checks now share the scanner in-process during Vitest runs and cache per-file analysis between fixture cases, cutting the inventory unit file from about 46 seconds to about 7 seconds locally while keeping the CLI output path intact.
- Port-entity diagnostics now include bounded DEBUG/WARN breadcrumbs for scanner candidate drops, SQLite compatibility migration failures, malformed Atlas attributes, and scan-observation replacement, plus INFO-level port and scan-observation counts when runs capture Atlas evidence.

---
