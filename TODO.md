# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Quick Lookup for saved Atlas entities](#quick-lookup-for-saved-atlas-entities)
  - [Autoscale ARM64 release runners on EC2 Spot](#autoscale-arm64-release-runners-on-ec2-spot)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
  - [Retire the local Nuclei kin-openapi compatibility patch](#retire-the-local-nuclei-kin-openapi-compatibility-patch)
- [Feature Enhancements](#feature-enhancements)
- [Research](#research)
- [Ideas](#ideas)
  - [Run replay / scrubbable event stream](#run-replay--scrubbable-event-stream)
  - [Run comparison enhancements — deferred pieces](#run-comparison-enhancements--deferred-pieces)
  - [Bulk history export and share](#bulk-history-export-and-share)
  - [Mobile share ergonomics](#mobile-share-ergonomics)
  - [PWA install and service-worker push](#pwa-install-and-service-worker-push)
  - [Engagement report builder](#engagement-report-builder)
  - [Native ticketing integrations](#native-ticketing-integrations)
  - [Operator-extensible signal and parser rules](#operator-extensible-signal-and-parser-rules)
- [Architecture](#architecture)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

### Quick Lookup for saved Atlas entities

Add a global Quick Lookup entry point for hostnames, IP addresses, and HTTP(S) URLs. The result should present the same app-first Overview, Evidence, Findings, and Intel profile that Atlas already exposes, but in a focused lookup workflow that does not require users to choose an Atlas tab, search a paged list, or work around the list's orphan and suppression filters. Keep Atlas as the single source of truth: Quick Lookup is a dedicated mode of the existing Atlas overlay and entity-profile renderer, not a second modal, a copied aggregation service, or a new entity store.

#### Scope and boundaries

- [ ] Keep the first implementation deliberately narrow:
  - Accept `auto`, `hostname`, `ip`, and `url` lookup modes. Map the user-facing **Hostname** label to the existing `domain` Atlas entity type; do not add a separate stored `host` type.
  - In `auto` mode, recognize an absolute `http://` or `https://` URL first, then a valid IPv4 or IPv6 literal, and otherwise validate the input as a hostname through the existing canonicalization rules in `services/intel/canonical.py`.
  - Require an explicit HTTP(S) scheme for URL lookups. Return a useful validation message for URL-shaped input without a scheme instead of guessing whether it is a hostname or URL.
  - Search the active personal or team owner scope by default. Accept an explicit `project_id` only when the caller intentionally launches a project-scoped lookup, and preserve `validate_profile_project()` semantics so a project lookup cannot broaden visibility.
  - Resolve suppressed entities and entities whose source runs have been deleted. These are valid exact matches even though the normal Atlas list hides them by default; the profile must show their existing suppression and orphan-source state clearly.
  - Read saved application observations, findings, relationships, metadata, projects, source runs, imports, and cached provider snapshots. Do not contact external providers automatically when a lookup is submitted.
  - Treat persisted `entity_intel_snapshots` rows as the external data available to Quick Lookup. Do not expose `services/intel/cache.py` responses for a value that has no Atlas entity: that Redis/process cache is keyed only by provider, entity type, and canonical value, is not owner-scoped Atlas data, and may have been populated by another session. Closing that gap would require a separate owner/provenance contract and is outside this implementation.
  - Keep **Refresh Intel** as the existing explicit, rate-limited mutation after a stored entity has been found. A lookup must not create an Atlas entity, run a command, consume provider quota, or add a project link on its own.
  - Do not add ports, hashes, CVEs, fuzzy matching, wildcard search, or DNS-derived domain-to-IP relationships in this work. Related ports and URLs already reached through `host_entity_id` remain visible inside the returned profile.
  - Do not add a `lookup <value>` built-in command. Lookup values—especially URLs with paths or queries—must not enter recent-command history or saved run records merely to open this browser surface.
  - Treat "everything the app knows" as access to the complete bounded profile, not one unbounded response. Continue to page source runs, findings, related URLs, and related ports through the existing collection offsets and `has_more` contract.

#### Phase 1 — Define and implement the exact lookup contract

- [x] Add the Atlas-owned resolver in `app/services/atlas/lookup_resolve.py`, which is already covered by the `app/services/atlas/lookup*.py` module-size ratchet pattern, rather than placing persistence logic in either browser or API blueprints:
  - Normalize the requested mode, detect the entity type for `auto`, and canonicalize with `canonical_entity()` so materialization, Intel, Atlas lists, and Quick Lookup use identical entity identities.
  - Enforce the existing canonical-value length ceiling before querying. Reject empty, malformed, unsupported, and overlong input with stable error codes and user-friendly messages.
  - Resolve candidates by stored type and `entity_signature()` first, then apply the existing `services/atlas/scope.py` personal/team visibility predicate to that bounded set. Personal scope should have at most one owner row. In team scope, prefer the directly team-owned row over compatibility-visible personal rows; if legacy data still leaves more than one equally valid candidate, return an explicit bounded `ambiguous` result instead of merging profiles or choosing by accident. Do not search a filtered first page from `list_entities()`.
  - Keep detection deterministic so a valid input has one detected type. Explicit modes must not silently fall through to another type when validation or resolution fails.
  - For a URL that has no saved URL entity, resolve its canonical parent hostname or IP as an optional, clearly labeled fallback candidate. Do not silently return the parent profile as though it were the requested URL.
  - When a match exists, call the existing `entity_detail()` aggregation for the initial profile so finding buckets, app/provider provenance, project monitoring, relationships, metadata, and Intel freshness cannot drift from Atlas.
  - Return a stable envelope with lookup metadata (`requested_type`, `detected_type`, `canonical_value`, and `match_state`), the normal entity-detail payload when found, a bounded candidate list when ambiguous, and the optional parent-host candidate when applicable. Treat `not_found` and `ambiguous` as expected lookup results; reserve request errors for invalid input or scope.
- [x] Add an index that makes the candidate-first resolver efficient for both owner models:
  - Add the next available forward migration (`v0045_atlas_entity_exact_lookup_index.py` at the time this plan was written) with a non-unique `idx_entities_type_signature` index on `(type, signature_hash)` for SQLite and Postgres, and register it in `app/core/migrations/__init__.py`.
  - Keep the existing personal and team unique signature indexes. The new index is a lookup accelerator, not a replacement for owner-level uniqueness.
  - Use the type/signature seek before applying `entity_scope_sql()`. This avoids an owner-wide entity scan when team visibility includes directly team-owned rows plus personally owned rows visible through team runs or Atlas imports—the `OR EXISTS` shape that cannot use either owner-leading partial signature index by itself.
  - Ensure the current schema manifest discovers `idx_entities_type_signature`, reports it as `missing_index` when absent, and keeps generated SQLite/Postgres head inventories aligned. Add migration upgrade, fresh-schema, manifest-drift, and backend index-parity coverage.
- [x] Add read-only browser and API v1 routes without duplicating their owner-scope rules:
  - Add `POST /atlas/lookup` beside the existing Atlas profile read routes and `POST /api/v1/atlas/lookup` beside `GET /api/v1/atlas/entities/<entity_id>`.
  - Accept the lookup value in a JSON body so full URL paths and query strings are not copied into access-log query strings or browser history. Never include the raw lookup value in structured logs; log only the detected type, outcome, scope, timing, and a bounded non-reversible identifier if correlation is needed.
  - Use `_atlas_request_scope_response()` for browser requests and `_api_request_scope()` plus `require_api_auth` for API requests. Apply the existing API route limit and preserve team membership and project-visibility rejection behavior.
  - Treat browser `POST /atlas/lookup` as an Atlas read route despite its POST transport: keep it off `_atlas_write_limit`, require the normal `X-Session-ID` header, and intentionally follow the existing browser Atlas read routes under `default_limits=[]`. The authenticated API v1 route still inherits the normal API route limit.
  - Keep subsequent profile paging on `GET /atlas/entities/<entity_id>` and `GET /api/v1/atlas/entities/<entity_id>` using the resolved ID. Do not invent parallel lookup paging endpoints.
  - Extend `app/services/api_v1/openapi_atlas_profile.py`, the generated OpenAPI document, the architecture route inventory, and API contract tests with the lookup request, match envelope, invalid-input response, and authenticated personal/team scope behavior.
  - Put the small route adapters in `app/blueprints/atlas_lookup_read.py` and `app/blueprints/api_v1_atlas_lookup.py` so profile and API read modules do not grow without bound. Register them through the existing decomposed blueprint import path and add explicit module-size budget entries.
  - Intentionally update `_DECOMPOSED_ROUTE_CONTRACT_COUNT` and `_DECOMPOSED_ROUTE_CONTRACT_SHA256` in `tests/py/test_architecture.py` after reviewing the two added method/path/endpoint tuples. Do not treat the expected route fingerprint change as an unrelated snapshot failure.

#### Phase 2 — Add a dedicated Quick Lookup mode to Atlas

- [x] Extend the Atlas controller contract instead of mounting another overlay:
  - Add an explicit lookup launch mode to `openAtlas()` or expose a small `openAtlasQuickLookup()` bridge that delegates to it. Keep ordinary list, quick-detail, focused-profile, project-return, transcript-token, and Run Details launches unchanged.
  - Implement the lookup-mode state and transitions in `app/static/js/features/atlas/atlas_quick_lookup_mode.js`, with `atlas_overlay.js` delegating to it. Keep the module Atlas-owned and loaded with the existing lazy Atlas asset graph; do not add hundreds of lookup-specific lines to the current 3,700-plus-line overlay.
  - Let that module own the raw draft, selected mode, submitted canonical value, lookup result, request status, launch scope, lookup-root transitions, and decisions about which normal Atlas loads are skipped. Abort stale lookup and entity-detail requests through the existing Atlas request-controller lifecycle.
  - In lookup mode, skip the Atlas summary/list, saved-view, run-filter, import/export, select-mode, and bulk-action requests that are irrelevant to an exact lookup.
  - Reuse the current `atlas_entity_detail.js` focused renderer for Overview, Evidence, Findings, and Intel, including `direct`, `related_urls`, `related_ports`, and `combined` finding buckets. Preserve every backend pager rather than truncating long collections in the lookup view.
  - Keep one Atlas scrim, one focus trap, and one mobile sheet. Mark the shell with a dedicated lookup mode so Atlas list chrome can be hidden without maintaining a second copy of the entity profile markup or styles.
- [x] Give lookup mode its own clear navigation root:
  - Show a **QUICK LOOKUP** heading, one prominent input, an `Auto / Hostname / IP / URL` selector, current Personal/Team/Project scope, and a submit action using the established form and button primitives.
  - Make **New lookup** return to the lookup form, not the Atlas results list. Keep the current result available while a replacement lookup is loading so an error does not erase useful context.
  - Keep related-entity navigation on the Atlas-owned profile stack. Back from a related URL, port, or parent host returns to the prior lookup profile and local tab; Back at the stack root returns to the lookup form.
  - Add **Open in Atlas** as an explicit transition to ordinary Atlas results/profile mode with the resolved entity type, ID/value, owner/project scope, active local view, and finding bucket carried forward.
  - Closing Quick Lookup returns focus through the established composer-focus contract. Do not reopen Atlas list mode or another modal unless the user explicitly chose **Open in Atlas**.
  - If the active personal/team scope changes while Quick Lookup is open, invalidate the old owner-scoped result and rerun the submitted lookup in the new scope or return to a clearly labeled stale-free form state.

#### Phase 3 — Complete the result, empty, and action states

- [x] Make lookup outcomes understandable without implying data the app does not have:
  - Use the existing profile header to show the entity type, canonical value, first/last observation, project-link count, and suppression/orphan badges before the local profile tabs.
  - Keep Overview app-first: show saved scan coverage and services, direct and related finding rollups, one-hop stored relationships, and cached external Intel freshness/highlights before the longer source-run collection.
  - Show a specific no-record state for the active scope. Explain that no saved Atlas entity exists without suggesting that the hostname/IP/URL itself is invalid.
  - If legacy scope data produces an ambiguous exact match, show the bounded candidates with their direct-team or compatibility-visible provenance and let the user choose one. Do not combine evidence from separate entity IDs inside the browser.
  - For the URL parent fallback, offer an explicit **Open known parent host** action with its canonical host value and type. Keep the original URL visible so users understand that the app has host data but not that exact URL record.
  - Offer non-destructive next steps such as **Search Atlas**, **Switch scope**, and type-appropriate command suggestions. Suggestions may prefill the active composer through the existing composer helper, but must never execute automatically or create terminal history merely by rendering the state.
  - Preserve existing profile actions for copy, project linking, finding review/suppression, Run Details, Project transitions, and explicit Intel refresh. Their permission, return-state, and audit behavior must remain identical to ordinary Atlas profile mode.
  - Render cached provider information as cached data with its existing freshness states. Do not describe an empty or stale provider snapshot as a live external lookup.
- [x] Keep optional discovery separate from exact resolution:
  - Do not require typeahead for the initial release. If added during this work, keep it bounded and debounced, source suggestions from the active-scope `/atlas/entities` list, identify each suggestion by entity type and last-seen time, and still submit through the exact resolver.
  - Never send every keystroke to external providers or persist lookup drafts as Atlas entities, recent commands, or run records.

#### Phase 4 — Add shell and mobile entry points

- [ ] Make Quick Lookup easy to reach without confusing it with transcript search:
  - Add a primary desktop rail action beside **Atlas** in `app/templates/index.html` and route it through the shared shell action helpers in `app/static/js/shell_chrome.js`.
  - Add a matching application-navigation item beside Atlas in the mobile menu and handle it in `app/static/js/features/mobile/mobile_menu_actions.js`. Desktop and mobile triggers must call the same lazy Atlas lookup API.
  - Do not place the action in the current-output search toolbar; that search is scoped to terminal transcript text, while Quick Lookup is a database-wide entity action.
  - Add the currently unassigned `Alt+Q` / `Option+Q` through `app/static/js/features/shortcuts/global_shortcuts.js`. Reuse `eventMatchesLetter()` and add `q: ['œ']` to `MAC_OPTION_KEY_ALIASES` as the macOS fallback, include the chord in the shared keyboard-shortcut inventory, and prevent the Option glyph from leaking into the composer.
  - Update the Atlas lazy-loader/bridge in `app/static/js/core/lazy_assets.js` and `app/static/js/features/atlas/atlas_bridge.js` so the first lookup opens the same fragment, JS, and CSS assets as Atlas and does not increase the initial shell payload.
  - Ensure `closeMajorOverlays()` treats Quick Lookup as Atlas-owned state, not a separate competing overlay, and preserve the existing desktop/mobile modal exclusivity and focus restoration contracts.
  - Leave `.atlas-entity-token` click, keyboard, context-menu, and long-press behavior unchanged. Recognized output entities already open the exact focused Atlas profile, so adding Quick Lookup beside **Open in Atlas** and **Refresh intel** would duplicate navigation and blur the stored-data versus provider-refresh boundary.
  - Do not intercept the browser context menu for arbitrary unclassified text selections in the first implementation. That is the transcript case where Quick Lookup could add distinct value, but it needs a separate selection-action design that preserves copy/select behavior and applies the same server-side validation safely.

#### Phase 5 — Prove parity, privacy, and cross-surface behavior

- [ ] Add backend and route regression coverage:
  - Cover auto and explicit detection for IDNA/case-normalized hostnames, IPv4, compressed IPv6, normalized URLs, default URL ports, fragments, paths, and queries, plus malformed schemes, whitespace-only input, unsupported types, and overlong values.
  - Prove exact resolution is independent of list page size and the normal orphan/suppression filters, while remaining isolated across personal sessions and team scopes.
  - Cover owner-wide and explicit project lookups, out-of-scope projects, entities not linked to the selected project, deleted-source-run entities, suppressed entities, URL parent candidates, direct-team precedence, bounded legacy ambiguity, and ordinary not-found results.
  - Assert that lookups do not insert entities, project links, runs, Intel snapshots, or audit rows that contain the raw submitted URL, and do not invoke provider clients.
  - Verify the returned initial detail is contract-identical to `entity_detail()` for the same entity, project, finding bucket, and collection offsets.
  - Exercise SQLite and Postgres query behavior and keep exact candidate lookup on the new type/signature index before owner-scope filtering; add query-plan coverage that protects against a full owner-wide entity scan.
  - Assert SQLite and Postgres use `idx_entities_type_signature` to bound exact lookup candidates before evaluating personal/team visibility, including a personally owned entity made team-visible through a scoped run or import.
  - Extend API v1 authentication, token/team isolation, OpenAPI generation, architecture boundaries, and module-size ratchet tests rather than creating a lookup-only test harness.
- [ ] Add frontend unit coverage in the existing Atlas, shell-chrome, shortcut, and mobile-menu suites:
  - Cover first open, input validation, successful lookup, invalid/not-found/parent-fallback states, stale-request cancellation, retry, New lookup, Open in Atlas, explicit Intel refresh, and owner-scope changes.
  - Assert lookup mode does not request Atlas lists, saved views, exports, imports, or provider refresh until the corresponding explicit action occurs.
  - Cover profile tabs, finding buckets, collection paging, related-entity stack restoration, project/Run Details return descriptors, Escape/close behavior, and composer refocus.
  - Cover desktop rail, mobile menu, and `Alt+Q` entry points with the same action payload and no duplicate overlay or focus trap, and assert existing output entity-token actions remain unchanged.
- [ ] Add focused Playwright coverage using the approved helper in both asset modes:
  - Exercise a desktop hostname lookup through the rail, a URL parent fallback, an IP result with app and cached-provider evidence, Open in Atlas, and close-to-composer focus restoration.
  - Exercise the mobile menu, lookup form, focused profile tabs, related-entity navigation, New lookup, and owner-scope change in the mobile sheet.
  - Run the focused scenarios with `bash scripts/run_playwright.sh --asset-bundle-mode bundle ...` and `bash scripts/run_playwright.sh --asset-bundle-mode source ...`.
  - Regenerate committed frontend assets and require `npm run assets:check`, targeted Vitest/Pytest/API/Postgres suites, documentation guards, and `git diff --check` before the TODO is closed.

#### Phase 6 — Finish documentation and close the TODO

- [ ] Document only the shipped final-state behavior:
  - Add the user-facing Quick Lookup workflow to `README.md` and `FEATURES.md` in terms of finding what the app has already captured, including the difference between saved/cached data and explicit Intel refresh.
  - Update `ARCHITECTURE.md` with the lookup route contract, exact resolver, Atlas-owned lookup mode, privacy boundary, owner/project scope, shell entry points, and reuse of the focused profile renderer.
  - Update `DECISIONS.md` only if the choice to use an Atlas mode instead of a second modal needs durable rationale beyond the current focused-profile decision.
  - Update `tests/README.md`, `CONTRIBUTING.md`, and documented test totals/appendices only where the added coverage changes their maintained contracts. Check `CONFIGURATION.md` and `THEME.md` for relevant rate-limit or reusable-component guidance rather than adding empty sections.
  - Add a human-readable `CHANGELOG.md` entry describing the user outcome, privacy behavior, and validation. Keep implementation phases and file inventories in this TODO until completion, not in final-state documentation.
  - Keep any active merge-request or release-note drafts under `docs/release-drafts/` synchronized without referencing those transient files from official documentation.
  - Remove this entire TODO item only after the implementation, generated assets, tests, and documentation are complete.

#### Acceptance criteria

- [ ] From the desktop rail, mobile menu, or `Alt+Q`, a user can submit a hostname, IP, or absolute HTTP(S) URL and receive the same scoped Atlas profile data that the stored entity exposes in ordinary focused profile mode.
- [ ] Exact lookup works for matches outside the first Atlas list page and for suppressed or orphan-source entities without crossing personal, team, or project boundaries.
- [ ] The default lookup performs database reads only, including owner-scoped persisted `entity_intel_snapshots`; it does not read the unscoped `services/intel/cache.py` response cache, create records, run commands, call providers, or put raw URL query strings into route or structured logs.
- [ ] Overview, Evidence, Findings, Intel, finding buckets, related entities, and every paged collection behave consistently on desktop and mobile, with no duplicated modal, scrim, focus trap, or aggregation contract.
- [ ] Not-found, ambiguous, invalid-input, URL-parent, scope-change, and permission states are explicit and recoverable; ambiguous results require an explicit bounded candidate choice, and **Open in Atlas** is the only action that transitions from the lookup root into normal Atlas browsing.
- [ ] SQLite, Postgres, API v1/OpenAPI, Vitest, bundle/source Playwright, asset, architecture, documentation, and lint guards pass with the completed feature.

### Autoscale ARM64 release runners on EC2 Spot

Replace the long-running hosted ARM64 release lane with an ephemeral EC2 worker pool managed by GitLab Runner's Docker Autoscaler and AWS fleeting plugin. Keep the runner manager on existing self-hosted infrastructure, scale the AWS Auto Scaling Group from zero only after the manager accepts a matching job, and destroy each worker after one job. Preserve a documented On-Demand or hosted-runner fallback so Spot capacity does not become a hard release blocker.

- [ ] Define the runner and worker contract before provisioning infrastructure:
  - Use the `docker-autoscaler` executor so the existing Docker job images, service containers, privileged Docker-in-Docker flow, and release scripts keep their current execution model.
  - Give this runner configuration its own AWS Auto Scaling Group; do not share the group with another runner manager or `[[runners]]` entry.
  - Start with one job per instance, one use per instance, one maximum instance, no idle capacity, and no local state that must survive termination.
  - Use an ARM64 worker with at least 8 vCPU, 32 GiB RAM, and a 250 GiB `gp3` Docker volume. Treat `m7g.2xlarge` as the baseline while allowing a configurable pool of compatible Graviton instance types.
- [ ] Add Terraform for the AWS worker pool:
  - Define inputs for AWS region, VPC, worker subnets, runner-manager network ranges, ARM64 AMI, instance-type overrides, maximum capacity, root-volume size and performance, and common resource tags.
  - Create a launch template that requires IMDSv2, uses an ARM64 AMI, enables delete-on-termination storage, and provisions the Docker filesystem on a 250 GiB `gp3` volume with configurable IOPS and throughput.
  - Create a worker security group that allows SSH only from the runner manager's fixed address or private network and allows the outbound DNS, HTTPS, and registry traffic needed by release builds.
  - Create a mixed-instances Auto Scaling Group with minimum and desired capacity `0`, maximum capacity `1` by default, multiple subnets and compatible Graviton instance types, `price-capacity-optimized` Spot allocation, no independent scaling policy, instance scale-in protection, and `AZRebalance` suspended.
  - Keep Spot at 100% for normal operation, but make the purchase policy configurable so an operator can temporarily select On-Demand capacity without changing the runner or CI configuration.
  - Create the least-privilege IAM policy needed by the fleeting manager: describe the ASG and instances, change desired capacity and instance protection, terminate workers through the ASG, inspect Spot requests, and publish temporary SSH keys through EC2 Instance Connect when dynamic credentials are enabled.
  - Output the ASG name, region, worker security-group ID, IAM policy ARN, and other values required by runner-manager configuration without outputting secret credentials.
  - Add Terraform formatting, validation, static security checks, and reviewed plan output. Confirm a second plan is empty after apply and that destroying the stack removes workers, launch-template resources, and disposable volumes cleanly.
- [ ] Prepare a fast, reproducible ARM64 worker image:
  - Bake or otherwise version an ARM64 image with Docker Engine, SSH, EC2 Instance Connect support, CA certificates, and the small set of host utilities required by GitLab's Docker Autoscaler.
  - Enable Docker at boot, grant the connector user access to Docker, and verify `docker info` succeeds over the same SSH path the runner manager uses.
  - Keep boot-time configuration short and deterministic; do not install the full toolchain through user data on every scale-out.
  - Record the image identifier as a Terraform input so worker-image updates produce an intentional launch-template revision.
- [ ] Add generic Ansible management for the existing runner manager:
  - Install or update a GitLab Runner version compatible with GitLab.com and the Docker Autoscaler executor.
  - Configure the AWS fleeting plugin with a pinned compatible version and run `gitlab-runner fleeting install` when the selected plugin version is not already installed.
  - Manage a root-readable AWS config containing the selected profile and region. Store AWS credentials through the automation system's secret mechanism rather than in source control, and keep the credential file readable only by the GitLab Runner service account.
  - Manage the runner's `config.toml` entry with `executor = "docker-autoscaler"`, the protected ARM64 runner tags, privileged Docker support, `capacity_per_instance = 1`, `max_use_count = 1`, `max_instances = 1`, and an all-day policy with `idle_count = 0`.
  - Configure the fleeting plugin with the Terraform-provided ASG name and AWS profile, and configure the SSH connector for either the worker's private address or its public address according to the chosen network design.
  - Persist the runner configuration and, if enabled, taskscaler state across manager restarts with restrictive ownership and permissions.
  - Validate the rendered runner configuration, installed plugin, AWS identity, ASG discovery, and service health before restarting the GitLab Runner service. Keep the Ansible run idempotent.
  - Add runner-manager logging and monitoring for scale requests, worker acquisition time, preparation failures, Spot interruption failures, orphaned instances, and ASG desired capacity that remains above zero without an active job.
- [ ] Prove the network and security boundaries:
  - Confirm the runner manager can reach GitLab.com and the required AWS APIs over HTTPS and can connect to workers over SSH, while workers accept no other inbound application traffic.
  - If workers use public addresses, restrict SSH to a fixed runner-manager source address. If workers use private addresses, document and validate the VPN or routed connection into the VPC.
  - Confirm workers can resolve DNS and reach GitLab registries, Docker Hub, GitHub, language package indexes, and every other source used by the release image build without requiring broad inbound access.
  - Verify the runtime IAM identity cannot modify unrelated Auto Scaling Groups or EC2 instances.
- [ ] Migrate the ARM64 CI lane behind a temporary runner tag:
  - Register the autoscaled runner as protected, locked to the intended project or group scope, and unable to accept untagged jobs.
  - Point a temporary ARM64 build job at the new tag before changing the canonical release jobs.
  - Preserve the current DinD service, MTU handling, native architecture checks, artifact contracts, timeouts, and disk measurements.
  - Add a bounded retry for runner-system failures so a Spot interruption or failed worker acquisition can retry an idempotent build without hiding repeatable product failures.
  - Keep the current ARM64 runner path available until the EC2 lane passes qualification and the fallback procedure has been exercised.
- [ ] Qualify performance, cleanup, failure handling, and cost:
  - Demonstrate scale from desired capacity `0` to `1` after job acceptance and back to `0` after completion, with no worker or EBS volume left behind.
  - Run an uncached release image build and record provisioning time, build and export duration, peak disk use, final free-space percentage, CPU and memory pressure, and total Spot runtime.
  - Run consecutive cached builds through the registry cache and confirm the larger worker avoids the cache-import and export-time disk exhaustion seen on the hosted ARM64 lane.
  - Require at least 20% free Docker storage after image export and enough wall-clock margin to stay comfortably within the CI job timeout.
  - Trigger a controlled Spot interruption, confirm the interrupted job fails as a runner-system failure, and confirm its retry starts on a fresh instance without conflicting with staging tags or publication state.
  - Exercise the On-Demand fallback and return the ASG to Spot afterward.
  - Add an AWS budget or cost alarm and confirm the idle-state cost is limited to the always-on runner manager and any intentionally retained supporting infrastructure.
- [ ] Cut over only after three consecutive ARM64 release rehearsals complete without manual repair. Then update the maintained CI and contributor documentation, remove the obsolete runner path, and record the final instance pool, storage floor, fallback policy, and measured build timings in `DECISIONS.md` and `CHANGELOG.md`.

## Known Issues

No open Known Issues are currently tracked.

---

## Technical Debt

### Retire the local Nuclei kin-openapi compatibility patch

Nuclei 3.11.0 still pins the vulnerable kin-openapi 0.132.0 release and doesn't compile against the fixed API without a two-line source patch. The image currently raises kin-openapi to the secure 0.144.0 floor, applies the compatibility patch, and verifies the selected dependency is embedded in the finished Nuclei binary.

- [ ] Wait for a released Nuclei version that supports kin-openapi 0.144.0 or newer without source modification.
- [ ] Update `NUCLEI_VERSION`, build Nuclei without `GO_TOOL_SOURCE_PATCH`, and confirm its embedded kin-openapi version still meets the secure floor.
- [ ] Remove the local patch, its Docker build-context and release-provenance wiring, and the patch-specific regression assertions. Keep the dependency floor and license tracking while kin-openapi remains embedded.
- [ ] Build and scan the AMD64 and ARM64 runtime images. Confirm their SBOMs record the expected Nuclei and kin-openapi versions and Grype no longer reports `GHSA-r277-6w6q-xmqw`.
- [ ] Update `CHANGELOG.md` and remove this item after the unpatched release path passes the protected image and supply-chain gates.

---

## Feature Enhancements

These are possible future improvements, split by whether they look worth carrying forward.

- **Webhook receiver / `POST /api/v1/intel/<provider>` passthrough.**
  - Worth scoping once outbound notifications and external automation mature. The headless API is the right place to receive webhooks that auto-create or update projects.
- **Cross-session Atlas view.**
  - Useful for operators managing multiple sessions or shared infrastructure, especially now that team mode makes shared context more important.
- **Extend comparison beyond run-to-run finding and artifact diffs.**
  - Snapshot and package-artifact comparisons are likely useful once evidence packages become a regular handoff surface.
- **Package re-import preview/apply.**
  - Worth scoping once package handoff archives are used regularly. It should reuse the Atlas import preview/apply pattern and the package manifest import hints before it writes project data.
- **Project Monitoring CLI surface.**
  - Possible future `darklab monitoring <project_id>` and `darklab monitoring ack <project_id> <fire_id> --state STATE [--note NOTE]` commands could expose the Project Monitoring dashboard, rollups, and fire triage flow without opening the browser.
  - Keep this lower priority than watcher creation, Project assignment, policy controls, and baseline acceptance, which are already available through `darklab watch`.
- **Headless API and CLI follow-through.**
  - Let scripts and CI start, inspect, cancel, and follow durable workflows through token-authenticated API routes and matching `darklab workflow` commands. Expose saved-run comparison through the same headless surface once its permission, team-scope, and bounded-output contracts are defined.
  - Put the workflow execution event cursor to work for browser refresh or headless replay, or retire it if execution polling remains the supported path.
  - Add `darklab --version` for the installed client. Treat connected-server version and client/server compatibility reporting as a separate decision.
  - Bring the existing API v1 AI assists to the CLI with summary and next-command commands that handle cached, queued, in-progress, disabled, and failed states cleanly.
- **Revisit PTY transport after real usage.**
  - The current Redis-brokered SSE plus POST endpoints keep deployment simple, but WebSockets may be worth it if latency, throughput, or bidirectional control becomes a real limitation.
- **Split `pty.js` and `pty_service.py` if PTY work grows again.**
  - Worth doing when new PTY behavior lands; orchestration, modal wiring, xterm session handling, lifecycle, transport, and metadata storage are natural boundaries.
- **Introduce a small PTY host interface object and broader PTY browser coverage.**
  - Would make PTY tests less brittle and keep future tab-state or disabled-terminal changes from drifting.
- **Reduce idle PTY control-channel work if concurrency becomes real.**
  - Redis Pub/Sub, a longer block window, or avoiding unnecessary attach-time snapshot writes would be worthwhile if many PTYs are active at once.

## Research

No research items are currently tracked.

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Run replay / scrubbable event stream
- Turn completed runs into replayable structured event logs, building on the Structured Output Model.
- Support a scrub timeline, bookmarks, per-line comments, and command-by-command playback.
- Keep replay integrated with findings, Atlas entities, summaries, and run comparison rather than treating it as a separate asciinema-style recording.

### Run comparison enhancements — deferred pieces
- Run comparison now covers finding severity changes, discovered hosts, TLS fields, workflow context, and completed-tab launch points. The remaining ideas are:
  - Snapshot/permalink compare, once the compare route can resolve snapshot/permalink ids instead of only live `runs` rows.
  - `Export comparison`, once share/export packages have one unified, stable artifact schema version rather than several independent `schema_version` fields.
  - Unifying the comparison-local URL/status/title parsing (`httpx`/`ffuf`/`gobuster`/`katana`) with the shared tool-aware classifier registry that ports/hosts/tls already use.
  - Date-range filters in the manual compare picker, if day grouping plus `Load More` is not enough for deep history.
  - Broader Playwright coverage for additional edge and mobile layout paths.
  - Focused large/noisy comparison regression coverage if real-world outputs expose performance issues beyond current backend and unit coverage.

### Bulk history export and share
- The history drawer can delete all, delete non-favorites, export selected history as text/JSONL, and use visible-page multi-select for bulk project add/remove plus selected-item delete. Bulk share/permalink bundles would close the remaining gap when packaging selected history items after an engagement.

### Mobile share ergonomics
- The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
  - save/share actions tuned for one-handed use
  - clearer copy/share/export affordances inside the mobile shell
  - better share handoff after snapshot creation

### PWA install and service-worker push
- Make the mobile shell installable and deliver completion pings via web-push so phone users get notified when the tab is closed or the device is asleep. Today mobile notifications are intentionally hidden because foreground-only notifications are not useful on phones.
- Reuse the run-complete notification hook so push delivery becomes another channel rather than a separate completion system.
- **Entry-level scope:**
  - Add a manifest, app icons, and a small service worker so users can "Add to Home Screen" and launch into a standalone mobile shell.
  - VAPID-signed web-push subscription tied to the active session token; subscribe and unsubscribe from the Options sheet.
- **Architecture:**
  - New `app/static/manifest.webmanifest`, icon assets under `app/static/icons/`, and `app/static/sw.js` registered from `app.js` only when the runtime supports it.
  - New `WebPushChannel` in the notifications service; VAPID keys stored as operator config; per-session-token subscription endpoint at `/session/push/subscribe`.
  - Service worker scope is intentionally narrow — render notifications and open the tab on click; no caching of dynamic transcript content so users never see stale output.
  - Gotchas: iOS Safari requires the user to install the PWA before push works; document this in CONFIGURATION.md.

### Engagement report builder
- The Project Report tab now covers the base narrative-report flow. Future polish can make reports feel more portable and customer-ready:
  - Add report-created run links or permalinks where needed, carrying the report's redaction mode and showing the `permalink_retention_days` caveat in preview/export metadata.
  - Feed richer package/export provenance into the report once that plan lands, especially source run/import context and target relationships.
  - Tune artifact embedding/listing once provenance and report-created run links are available; screenshot galleries and richer binary handling can stay later work.
  - Run a browser Print/PDF fidelity pass across Chrome, Safari, and Firefox for page breaks, headers/footers, and fonts. If the browser print path cannot produce a consistent customer-grade PDF, revisit a server-side PDF renderer with its Docker/dependency cost documented.
  - Consider saved report versions, richer in-UI template customization, arbitrary custom sections, approvals, and shareable report permalinks after the one-current-draft workflow has real usage.

### Native ticketing integrations
- From the Findings tab, Project views, or evidence package flows, create or update issues in Jira, Linear, GitHub Issues, GitLab, etc., with bidirectional sync of status, notes, and links back into the finding review state.
- Keep the action close to existing triage and review-state controls so tickets feel like an extension of finding review, not a separate export step.
- **Entry-level scope:**
  - Generic webhook + templated payload connector plus first-class adapters for the most common trackers.
  - Secret-backed auth stored in the existing encrypted secrets surface.
  - One-click "Create ticket" and "Link existing" actions on individual findings and bulk on visible-page selections.
  - Map finding review state to ticket status (and vice versa) where the tracker supports webhooks or polling.
- **Architecture:**
  - New `app/services/integrations/ticketing/` package (or a lighter `notifications` extension).
  - Adds project-level and global configuration surfaces under Options or a new Integrations tab.
  - Preserves the existing outbound notification model for fire-and-forget alerts while adding the stateful sync path.

### Operator-extensible signal and parser rules
- Allow operators to extend the built-in findings classifier, entity extractor, and structured metadata logic via a hot-reloadable `conf/signals.yaml` (or small sandboxed snippets) without code changes.
- Custom rules feed the same findings strip, Atlas materialization, search scopes, run comparison diffs, project triage, and export surfaces as core signals.
- Target custom scanner output and internal tooling first; the biggest value is letting self-hosted teams teach darklab_shell their local signal language without carrying a fork.
- **Entry-level scope:**
  - Declarative regex + capture group + mapping rules for common cases (e.g., custom internal scanner output).
  - Optional tiny expression or Lua/JS sandbox for complex parsing.
  - Live reload on file change (consistent with `commands.yaml`, `workflows.yaml`, etc.).
- **Architecture:**
  - Extend or parallel `app/core/output_signals.py` with a user-rules loader.
  - Surface validation and a `/diag` inspector mode for testing new rules against recent output samples.

---

## Architecture

### Interactive PTY transport future-state
- Revisit whether the current Redis-brokered SSE plus POST input/resize transport should move to WebSockets after real use.
- The current model keeps deployment simple and avoids a WebSocket runtime, but a bidirectional socket could reduce input latency and simplify the modal terminal stream once PTY usage grows.
