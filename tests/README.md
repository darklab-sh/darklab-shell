# Tests

This directory contains the project’s test suites and the practical notes for running and extending them.

This is the main testing handbook for the repo. Keep setup, suite purposes, commands, workflow, and maintenance notes here. Keep `README.md`, `ARCHITECTURE.md`, and `DECISIONS.md` to short testing summaries with links back to this file.

## What Lives Here

- `tests/py/` - pytest coverage for backend validation, Flask routes, database helpers, and structured logging
- `tests/js/unit/` - Vitest coverage for browser-module helpers and DOM-bound client logic
- `tests/js/e2e/` - Playwright coverage for the full browser UI against a live Flask server

The suites are layered on purpose:

1. pytest checks backend rules and edge cases quickly, without a browser
2. Vitest checks client-side helper logic and browser-module failure paths in jsdom
3. Playwright checks the full UI, network behavior, and cross-module interactions in a real browser

Workspace file behavior is intentionally split across all three layers: pytest owns route/path-safety checks plus owner-scoped copy/touch/overwrite/append sinks, destination preflight, safe write failures, scheduled-run exit status, file/run source resolution, file comparison limits, and shell-style formatting; Vitest owns browser command parsing, fail-closed file-descriptor redirects, output capture, and Files browser sorting, filtering, full-row activation, parent navigation/drop targets, quota, desktop inspector, and action-menu behavior; and Playwright covers the live desktop inspector/full-view workflow plus the narrow-screen browser and focused viewer.

Project workspace behavior follows the same split: pytest owns project routes, schema, migration, assessment profiles and cycle services, the shared bounded-action registry, exact Project target resolution, IPv6-safe probe URLs, typed probe OpenAPI payloads and examples, probe-plan digests, anonymous and protected probe launches, privacy-safe probe failure logs, observed and retryable protected-material cleanup across prelaunch and run lifecycle failures, cross-cycle finding reconciliation, shared active-cycle, coverage, fix-first, finding-change handoffs, assessment-batch parent/event schema, safe-default preview compilation, exact plan deduplication and frozen-check mappings, atomic confirmed-start snapshots and replay, immutable retry previews and source lineage, serialized batch/target/owner/instance claim limits, fixed concurrency and chunking limits, exact item revalidation, Project-linked heterogeneous child launches, notification suppression, sanitized finalization events, cross-chunk advancement, truthful active-run cancellation, failed-signal rollups, lifecycle cancellation conflicts and fresh-request behavior, kind-isolated startup recovery, abandoned-claim release, live-run attachment, bounded missing-run retries, scope, runtime, and permission-loss settlement, deterministic progress with distinct skipped outcomes, bounded list/detail/item/event routes, latest-attempt paging, owner-isolated read cursors, bounded external ZAP jobs and prepared Atlas draft reads, private OAST reservation, ready-only launch, run binding, and redacted interaction evidence, Web Surface reads, filters, and visual comparisons, overview and monitoring payloads, packages, reports, history/share integration, public CVE risk and NVD advisory storage, Project/no-Project risk projections, and persistence edge cases; Vitest owns Projects modal, Assessment coverage, probe parsing, terminal output, per-tab confirmation, lifecycle invalidation, and same-tab run binding, private OAST recovery, polling, confirmation, and redacted status rendering, ZAP plan confirmation, job recovery, and explicit Atlas import review/apply, fix-first, finding-change rendering, the Web Surface gallery with its shared filters, comparison states, grouping, and full-image navigation, shared Overview/Findings summaries, exact-cycle and priority-filter navigation, desktop/mobile Monitoring tab rendering, compact finding-risk labels, history drawer, Files metadata, and package-wizard browser behavior; Playwright covers full user flows when focus, navigation, or live browser state is the important risk, including bounded Assessment start, reload, cancellation, and retry lineage, lazy mobile-width probe planning, declined and reload-invalidated confirmations, and a harmless confirmed probe that streams in the same tab and reaches History and its Project, plus mobile risk acknowledgement that stays separate from watcher triage. Interactive PTY behavior is split between pytest service/route coverage, Vitest browser-controller coverage, and focused Playwright checks for the real terminal modal path.

---

## Table of Contents

- [What Lives Here](#what-lives-here)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Running the Suites](#running-the-suites)
- [Recommended Workflow](#recommended-workflow)
- [Suite Summaries](#suite-summaries)
  - [Pytest](#pytest)
  - [Vitest](#vitest)
  - [Playwright](#playwright)
- [History Seeding](#history-seeding)
- [Choosing the Right Test Layer](#choosing-the-right-test-layer)
- [Test Artifacts](#test-artifacts)
- [Testing Conventions](#testing-conventions)
- [Related Docs](#related-docs)

---

## Prerequisites

You need different local dependencies depending on the suite:

| Suite | Required locally | Notes |
| --- | --- | --- |
| `pytest` | Python, repo virtualenv, Python dev dependencies | Normal backend coverage does not require Docker |
| `Vitest` | Node.js, npm dependencies | Runs in jsdom; no Flask server required |
| `Playwright` | Node.js, npm dependencies, Playwright browsers | Uses a real browser; `.tooling/playwright.config.js` is the single-project editor/debug config and `.tooling/playwright.parallel.config.js` is the isolated parallel CLI config |
| Container Smoke Test | Docker + Docker Compose | Opt-in verification path for image/tooling changes |

Recommended local baseline:

- Python virtual environment at `.venv`
- Python deps from [app/requirements.txt](../app/requirements.txt) and [requirements-dev.txt](../requirements-dev.txt)
- Node deps from [package.json](../package.json)
- Playwright browsers installed through the project npm tooling

---

## Local Setup

For the general repo setup, use [README.md](../README.md). For test-specific local setup, the normal path is:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r app/requirements.txt -r requirements-dev.txt
npm install
npx playwright install
```

Notes:

- `npm run test:pytest` uses `.venv/bin/pytest` automatically when the repo virtualenv exists
- `npm run test:pytest:fast` skips only the scenarios marked `release_integration`; `npm run test:pytest:release` runs those release-boundary scenarios on their own
- keep the Python virtualenv active for lint and backend debugging work
- `Vitest` and `Playwright` use the repo-local npm dependencies; do not rely on global installs
- most day-to-day test work does not require Docker
- CI runs the Postgres backend lane automatically. Locally, use `npm run test:postgres` to run the Postgres smoke, route, and migration integration tests against isolated schemas. The route smoke exercises browser and API Assessment reads, protected HTTP-profile references, and compatible completed-run reconciliation through the configured app. The configured-app startup smoke also performs a complete cold start, including migrations and the bundled EPSS/KEV baseline import, so it allows extra time for a contended shared runner without treating elapsed startup time as a performance assertion. The helper uses `DARKLAB_TEST_POSTGRES_DSN` when it is set; otherwise it starts a disposable Docker Postgres container and removes it after the run. You can also pass `--postgres-dsn` to pytest directly, or use `bash scripts/run_postgres_tests.sh --compose` to run the same lane against the bundled Compose Postgres service without publishing the database port.
- the container smoke test is slower and is meant for Dockerfile, dependency, and toolchain validation rather than the normal fast iteration loop

---

## Running the Suites

Run the full sets before merging or releasing:

```bash
npm run test:pytest
npm run test:unit
npm run test:e2e:source
npm run test:e2e
```

For a quicker backend loop while you're editing, run:

```bash
npm run test:pytest:fast
```

The fast command covers normal backend and route behavior. The complementary
`npm run test:pytest:release` covers slower production installers,
publication, signing, and backup/restore paths. Its publisher coverage runs the
real release shell script against stubbed Docker, registry state, and runner
identity so first publication, retry, and immutable-tag conflicts stay aligned
with CI without contacting a registry. Production Compose coverage also pins
the isolated ZAP/OAST worker profiles, shared durable mounts and database
settings, fixed credential bindings, read-only runtime, health checks, and the
entrypoint's allowlisted process-role dispatch. CI runs both required serial
lanes at the same time, retains separate JUnit, slow-test, and file-timing
reports, and verifies that their node IDs are disjoint and add up to the
unchanged complete suite. Use `npm run test:pytest`, not just the fast command,
for the final local backend check.

Run focused slices while iterating:

```bash
bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. tests/py/test_routes.py -v
npm run test:unit -- tests/js/unit/history.test.js tests/js/unit/runner.test.js
npm run test:e2e -- tests/js/e2e/failure-paths.spec.js
bash scripts/run_playwright.sh tests/js/e2e/failure-paths.spec.js --grep "history"
```

List the live suites without running them:

```bash
bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. --collect-only -q
npx vitest list --config .tooling/vitest.config.js
npx playwright test --config .tooling/playwright.parallel.config.js --list
npx playwright test --config .tooling/playwright.demo.config.js --list
npx playwright test --config .tooling/playwright.demo.mobile.config.js --list
npx playwright test --config .tooling/playwright.capture.desktop.config.js --list
npx playwright test --config .tooling/playwright.capture.mobile.config.js --list
```

The direct Playwright commands above only list dedicated suites. Use `bash scripts/run_playwright.sh ...` for actual end-to-end runs so the approved helper handles assets, ports, isolated servers, and failure logs.

Playwright notes:

- `npm run test:e2e` delegates to [`scripts/run_playwright.sh`](../scripts/run_playwright.sh), which clears the configured e2e ports, keeps local Playwright output quiet by default, captures isolated server logs under `test-results/e2e-server-logs/`, and prints server log tails only when Playwright exits non-zero. Each server keeps the shipped catalogs under `app/conf` and writes only its private settings overlay to a per-slot temporary directory. The helper uses [.tooling/playwright.parallel.config.js](../.tooling/playwright.parallel.config.js) unless a `--config` argument is supplied. Add `--debug-logs` when live app/server logs are needed, `--ci` for CI-style retries, `--serial` to force one isolated project while debugging worker contention, `--server-timeout <ms>` to give slower hosts more startup time, `--asset-bundle-mode source` to debug source-file loading instead of the default bundles, `PLAYWRIGHT_PROJECT_COUNT=N` to tune worker load, or `--force-color` when color must be forced through non-TTY output.
- `npm run test:e2e:source` runs a fast source-mode Playwright slice against the Project Assessment lifecycle, boot resilience, share/permalink flows, and the high-risk lazy shell surfaces. Its lazy-surface check also runs a workflow terminal command before the Workflows controller has loaded, which keeps cold-start command lifecycle regressions covered. It is included in `npm test` so browser-native ESM import loading stays covered even though the full browser suite stays in bundle mode.
- The wrapper defaults `PW_DISABLE_TS_ESM=1` because the repo's current Playwright configs/specs are plain JavaScript and do not require Playwright's TypeScript/ESM loader. Set `PW_DISABLE_TS_ESM=0` only when adding TypeScript Playwright files that need the loader.
- plain `npx playwright test` uses [.tooling/playwright.config.js](../.tooling/playwright.config.js), the single-project config intended for VS Code Test Explorer and focused local debugging
- each parallel project gets its own Flask server port plus isolated `APP_DATA_DIR` state, so SQLite history, run-output artifacts, and limiter/process state do not leak between workers
- modal interaction specs wait for app-level `data-interaction-ready` markers before driving real keyboard focus movement, keeping focus-trap coverage browser-native without fixed sleeps or synthetic key events

---

## Recommended Workflow

Use the smallest useful layer first:

1. backend/config/route/logging changes:
   run `pytest` first
2. browser-helper or DOM-bound client logic:
   run `Vitest` first
3. browser-visible integrated behavior:
   run focused `Playwright` coverage after unit/backend checks
4. Dockerfile, base image, or packaged-tool changes:
   run the container smoke test before considering the change done

A practical local loop is usually:

1. run the narrowest relevant `pytest` or `Vitest` file while iterating
2. run the matching focused `Playwright` spec if the behavior is browser-visible
3. use `npm run test:pytest:fast` for broad backend feedback while iterating
4. run the complete suite slice for the touched layer before pushing
5. run the container smoke test only when the change can affect the built image or installed tools

---

## Suite Summaries

These summaries explain what belongs in each layer. Use the live-listing commands above when you need the current test inventory.

### Pytest

Use pytest for backend rules, Flask routes, persistence, configuration, command policy, and structured server behavior:

```bash
npm run test:pytest
```

#### Core backend, Atlas, and CVE risk

`tests/py/` covers backend contracts, route behavior, persistence, loaders, configuration/theme resolution, command validation, diagnostics gating, and structured logging. Atlas exact-lookup coverage pins canonical identity detection, single-host CIDR rejection, personal/team/project isolation, team visibility through runs and imports, bounded legacy ambiguity, URL-parent fallback after both misses and unreadable matches, privacy-safe browser/API completion, rejection, ambiguity, and degraded-profile logs, migration parity, and indexed SQLite/Postgres candidate plans without invoking providers, materializing records, or writing raw submitted URLs to audit data. Shared CVE risk coverage validates the bundled EPSS/KEV manifest, feed parsers, strict full-record OSV package normalization, configured local OSV startup loading and unchanged detection, bounded exact external OSV requests, redirect rejection, query-scoped hash caching, atomic SQLite/Postgres OSV applicability replacement and last-good rollback, bounded read-only SQLite/Postgres OSV package-version correlation, backend-owned feed status through the browser command catalog, privacy-safe OSV failure and provider status, normalized NVD status/CVSS/CWE parsing, bounded local-file acceptance, capability-checked explicit persistence, hash-only positive/negative caches, last-good and no-network refresh behavior, allowlisted redirects, committed short-lived refresh leases, concurrent SQLite writers during a blocked download, stale-owner publication rejection on SQLite/Postgres, origin, age, live-refresh and freshness states in enriched findings and the browser catalog, deterministic enrichment and ordering, exact remediation grouping, explicit remediation-group search/preview/apply, stale-preview rejection, target-winner disposition, shared review and remediation-guidance state, observation-specific verification, explicit guidance clearing, observation/evidence counts, personal/team and subject isolation, session-migration conflict handling, EPSS hysteresis, owner batching, retry isolation, NVD transition thresholds and source-version preservation, complete read-only NVD version-inference candidate provenance, bounded structured-Nmap and HTTPx CPE extraction, capped reject-don't-evict materialization, parser-to-command agreement, cross-tool rejection, and explicit inference persistence with immutable source decisions on SQLite/Postgres, Project projections and acknowledgements, report snapshots, complete rendered source provenance, attribution, and privacy-safe failure logs. Project finding-evidence coverage pins all supported source types, exact-line snippets, idempotency, personal/Project scope, configurable quota semantics, unavailable-source reads, package preservation, audit events, and the browser/API OpenAPI contract. Its verification coverage also pins frozen assessment origins, bounded completed-run candidates, target/tool/profile compatibility, unavailable evidence, comparison pairs, privacy-safe final actors, audit events, and session migration without automatic dispositions. Project assessment coverage keeps SQLite and Postgres tables and indexes aligned, validates the shipped Network, Web, API, TLS, and Combined profiles plus the local catalog, and rejects multiple active cycles, ownerless cycles, invalid lifecycle/check/evidence states, duplicate checks or evidence, archived and out-of-scope Projects, incompatible targets, and quota overflow. Service, browser-route, API v1, and CLI tests also pin immutable profile and target snapshots, personal/team isolation, team-viewer read-only access, forward-only completion and archiving, completed-cycle immutability, archived-only deletion previews, source-record preservation, lifecycle and manual check/evidence audit events, exact versus host-and-descendant target matching, command/workflow/completion/version/structured-output compatibility, unrelated and cross-scope saved-source rejection, idempotent evidence links, transactional evidence quotas, reasoned manual states with safe actor metadata, decision clearing and state re-derivation, manual exclusion protection, bounded newest-first manual-link reads, shared desktop/mobile link and unlink controls, manual-link removal without source deletion, session-token migration of assessment ownership and actors, audit-failure rollback, finding-aware state derivation, manual/active and auto-promoted completed-run matching, savepoint rollback, bounded cycle/check pages and filters, owner-scoped paged Nmap service-evidence API and browser reads, cross-owner browser rejection, capped Assessment-check attachment, free-form NSE omission, safe serialization, truthful coverage denominators, unavailable-evidence rollups, read-only target-scoped Nuclei recommendations from bounded technology/CVE/service/DNS signals, intrusive-profile abstention, guarded finding-verification plans, exact digest confirmation, current-target and frozen-action revalidation, safe/standard policy enforcement, broker handoff, Project linking, reviewed ZAP preview/queue/status/cancel routes, target and HTTP-profile digest revalidation, owner and nested-check isolation, public connector-state redaction, target/command-safe audit and logging, public error envelopes, privacy-safe OpenAPI responses, CLI request/output/completion shapes, idempotent SQLite/Postgres source tombstones across single, bulk, filtered History, and automatic-retention deletion, and explicit Project cleanup. The registered-route inventory also keeps browser and API Assessment mutations paired with their limiter and capability contracts. Its role matrix covers viewer, operator, admin, and owner behavior in personal, team, active, archived, and cross-team scopes, confirms denied handlers aren't called, and proves a protected action rechecks a downgraded member before creating private launch files. The app-owned helper registry coverage pins provider registration, duplicate rejection, lazy execution context, browser/server ownership, safe two-step workspace alias resolution, the complete root and exact-alias sets, and parity across execution, discovery, rich details, search, and autocomplete. Stable route modules reuse an application with a fresh client and reset Flask config for each test; application-factory, construction-time configuration, logging, import, and extension-isolation tests still create independent applications.

#### Imports and reviewed scanning

Atlas import coverage also streams native Greenbone GMP XML through the bounded parser, rejects unsafe DTD/entity input and incomplete results, keeps NVT OIDs as stable rule identity across changing result UUIDs and report text, and verifies normal Atlas deduplication and Project mapping without contacting a scanner.

Reviewed Nuclei profile coverage pins safe, standard, and explicitly intrusive template families, tags, protocols, exclusions, callback/redirect/update boundaries, frozen-policy selection, public plan metadata, desktop/mobile confirmation details, and takeover-template isolation. Exact command-mode coverage keeps clean safe, standard, and intrusive runs from satisfying a different profile's check, including when protected HTTP placeholders are present. The intrusive launch cases also pin the default-off deployment gate, fresh warning confirmation, exact profile revalidation, and launch-time gate changes. Managed-cache coverage pins bounded manifest parsing, exact recorded-release directory matching, stable SHA-256 revisions, missing-cache guidance, plan-digest inclusion, launch-time drift rejection, and result provenance.

Explicit OSV API coverage also pins personal and team-operator access, team-viewer rejection before acquisition, stable disabled/provider-failure responses, count-only audit records, and privacy-safe application logs.

#### Private connectors and API checks

Private OAST coverage keeps the connector disabled by default, validates its private HTTPS origin, exact callback suffix, environment-only token reference, bounded retention, and privacy acknowledgement, and proves settings reads have no provider side effects. Correlation coverage pins the default 20-character id plus 13-character nonce identity, explicit intrusive-action and confirmed-target revalidation, personal/team scope, non-secret stored identities, owner and check quotas, guarded one-run-per-check activation, closure, expiry, purge, session migration, Project cleanup, and SQLite/PostgreSQL schema parity. Transport coverage uses local fakes to pin exact registration, encrypted polling and deregistration requests, authorization-header placement, RSA-OAEP/AES-CTR compatibility, strict callback matching, shared-scope omission, bounded responses, raw-field redaction, and fail-closed redirects without contacting a provider. Session-spool coverage proves the generated provider secret and private key are encrypted with the app key, kept under private modes, bound to the exact durable callback identity, recoverable after a restart, and rejected after tampering, key drift, path traversal, or symlink substitution. Worker coverage pins singleton ownership, bounded active-before-reserved work, exact provider-scope recovery, restart-safe polling, retryable credential and provider outages, fail-closed private-session loss, provider-side reject counts, terminal deregistration, and bounded orphan cleanup. The blind-XSS command contract separately pins one saved query parameter, the redacted app-owned callback placeholder, fixed request and time bounds, exact saved-command mode recognition, strict private callback origins, and the absence of scanner-managed OAST or broader active options. Browser/API coverage pins Web profile 1.6, provider-free preview, stale-digest rejection, the blocked generic launch path, explicit reservation, bounded redacted recovery, exact ready-state callback disclosure, ready-only launch and reuse rejection, typed private callback execution, callback-free public commands and responses, exact run binding, parameter-discovery suppression, nested owner and check isolation, safe audit details, and OpenAPI parity without resolving a token or calling a provider from the web process. Shared desktop/mobile controller coverage adds reload recovery, exact status polling, fresh prepare and launch confirmations, callback-free DOM and modal state, interaction and retention rendering, terminal handoff, and Run Details recovery.

Schemathesis contract coverage keeps local OpenAPI review and generated API traffic inside the reviewed API base URL. It pins Project and owner scope, saved size and digest checks, strict JSON parsing, internal references, fixed in-scope servers, read-operation and document limits, bounded newest-first artifact selection, reject-don't-evict overflow, exact private schema/config/report material, disabled scanner caches, bounded no-follow report reads under both app and scanner ownership, partial-file cleanup, GET/HEAD-only negative generation, deterministic request bounds, browser/API digest confirmation, safe audit metadata, and rejection of direct or drifted commands. Completion coverage accepts the tool's findings exit only from that typed private reader after a complete report contains reviewed failures; malformed, incomplete, empty, or no-failure reports, output-write failures, and other tool exits retain their normal failure meaning. SQLite integration coverage pins idempotent report and operation persistence, minimized failure data, typed active-confirmation findings and evidence links, exact target matching, schema-drift rejection, and fail-closed clean coverage. SQLite and real Postgres schema tests keep report and operation constraints, indexes, deletion previews, and Project/assessment cleanup aligned.

#### Structured run evidence

Workspace artifact and finalization coverage marks validated Nmap XML intent from separate and attached `-oX` values, rejects extension guesses, unrelated commands, and ambiguous rewritten paths, and pins successful owner-scoped reads, entity-before-inference ordering, count-only events, failed-run abstention, and optional-hook savepoint rollback. Structured NSE service coverage separately pins exact informational-script mapping, open-port and canonical-target requirements, Nmap/parser/run/time provenance, bounded structured paths and values, truncation signals, and omission of free-form output, unknown or vulnerability scripts, output-only rows, closed ports, and unsafe XML. Persistence coverage pins successful owner-scoped Nmap sources, idempotent typed rows, conflict rejection, JSON/boolean/timestamp parity, no free-form output, one artifact read shared by independent service and inference savepoints, count-only logs, and failure isolation. HTTPx screenshot coverage pins its safe relative-path metadata, one validated output directory, PNG/JPEG/WebP signatures, owner-scoped no-follow reads, aggregate Files count/byte and per-file limits, earlier-file preservation, invalid/over-limit/failed-run cleanup, and rejection of traversal paths, symlinks, ambiguous directories, and non-image content without losing other completed-run artifacts. The Project Web Surface read tests cover SQLite and Postgres-compatible query paths, bounded paging and comparison windows, image-only artifact selection, file state, source-run provenance, exact same-run URL/host links, exact URL/role prior-capture matching, changed/unchanged/incomparable/baseline states, duplicate metadata conflicts, owner isolation, and omission of captured markup and binary data.

Structured HTTPx coverage pins the maintained JSON/CPE command, exact versioned technology-to-CPE agreement, canonical target and source-run provenance, bounded event serialization, read-only stored-NVD candidate correlation, guarded and capped inference persistence on SQLite and Postgres, complete tool/parser context, and fail-closed handling for unversioned, conflicting, mismatched, credential-bearing, malformed, incomplete, cross-tool, or ambiguous rows.

Structured DNSx coverage pins bounded CNAME, address, response, resolver, provider, wildcard-filter, scope, time, source-run, and parser context; unchecked-target labeling; raw and credential-bearing resolver omission; resolver-entity exclusion; conservative takeover states; and run-event serialization. Correlation coverage separately pins exact ultimate-target matching, decision-critical parser-v2 observation identities, owner-scoped run allowlists, complete bounded chains, a 24-hour evidence window, parser provenance, safe target references, and fail-closed truncated, stale, mismatched, unscoped, tampered, or transient evidence. Persisted-event review coverage pins newest-result selection, same-time conflicts, strict run ids, and whole-review rejection for oversized event or observation sets. Nuclei confirmation coverage revalidates the DNSx evidence pair and pins the immutable reviewed-template id/version/digest, safe and standard policy boundary, exact owner and hostname match, deterministic confirmation reference, timestamp requirement, and rejection of caller-made potential objects, legacy booleans, intrusive templates, credential-bearing targets, or mismatched provenance. Structured Nuclei takeover coverage separately pins trusted launch metadata, bounded JSON, normal run-event serialization, ignored version/digest/policy claims from output, parser provenance, deterministic observation identity, rejection after any event tampering, typed broker transport tied to the generated run id, fail-closed internal context, omission of caller-provided context from browser and API run routes, the checked-in template's exact digest, one-request no-redirect shape, fixed matchers, regular-file boundary, and tamper or symlink rejection, plus the maintained Web profile's dedicated check, exact canonical domain command, one-request bounds, no-credential and no-Interactsh launch, generic-Nuclei isolation, trusted-argument composition, contract-drift rejection, and template-failure logging at both launch routes. Finalization coverage pins a single deterministic high-severity finding only when an exact successful dedicated check has compatible owner- and Project-scoped DNS source and negative-target evidence within 24 hours of the Nuclei match. It also pins the three exact run-line evidence links, idempotent persistence, bounded preview review, and fail-closed behavior for failed runs, command drift, stale or partial evidence, and savepoint failures.

#### Imported evidence and reconciliation

Structured CycloneDX component coverage pins shared document bounds, separate exact PURL/version and CPE/version observations, component and import provenance, conflicting-version rejection, read-only stored-OSV and stored-NVD candidates on SQLite and Postgres, and the no-network, no-inventory-write, no-finding boundary.

Atlas CycloneDX import coverage separately pins bounded nested components, dependency edges, document provenance, vulnerability ratings and references, affected component links, every supported VEX category, durable batch evidence, team permissions, and the rule that imported dispositions don't update existing triage or verification state.

Nessus import coverage pins exact service CPE normalization, host and port context, scan-time and scanner-version provenance, malformed and wildcard rejection, bounded typed evidence, and durable preview/apply storage without treating an observed version as a confirmed vulnerability.

Nessus inference coverage re-reads owner-scoped typed evidence from an applied batch before saving. SQLite and real Postgres tests pin exact observation, target, subject signature, CPE/version, tool/parser, and timestamp matching; tampered candidates, unrelated owners, and incomplete batches fail closed, while repeated valid materialization stays idempotent. A focused identity guard keeps that imported inference separate from later active Nuclei confirmation while grouping both observations under one remediation row and counting their source evidence independently.

SARIF import coverage pins bounded tool and automation identity, rule metadata, full and partial fingerprints, direct and artifact-index locations, source regions, safe web and repository-relative provenance, and warning-backed rejection of file URIs, traversal, credentials, backslashes, and invalid references. Atlas browser coverage keeps SARIF and CycloneDX available through the existing import picker with format-appropriate file hints, evidence counts and samples, and permission-aware apply controls.

Compressed Atlas import coverage pins bounded gzip and single-report ZIP expansion, the original-upload digest, file-picker hints, and fail-closed rejection of oversized, malformed, nested, multi-report, and unsafe-path archives. Prepared-draft coverage pins owner-scoped bounded review, expiry, digest revalidation, omission of normalized rows, and the browser's explicit handoff from a ready ZAP job into the existing Atlas apply flow.

#### Findings and protected HTTP actions

Cross-cycle reconciliation coverage pins exact check, target, and evidence-rule compatibility; one-count-per-remediation rollups; new, persistent, and not-observed derivation; bounded current and earlier observation links; incomparable cleanup; the preferred active-or-latest-completed handoff; selected-finding filtering; package/report references and reasons; and the shared API/OpenAPI read shape.

Assessor-authored finding coverage pins strict fields and references, confirmed-target and owner scope, bounded initial line evidence, CVE risk links, duplicate overrides, stable identity, optimistic edits, safe actor metadata, session migration, cleanup, audit records, OpenAPI, and real SQLite/Postgres behavior.

HTTP assessment profile coverage pins personal/team and Project scope, exact confirmed hosts, recovery from malformed confirmed entities without dropping valid scope, Secret and Files references without stored credential values, team-viewer redaction, Secret-management permissions, optimistic revisions, duplicate and quota rejection, archived-Project behavior, safe audit/log fields, session migration, browser/API CRUD, OpenAPI, and matching SQLite/Postgres schema shapes. Protected-launch coverage also pins last-moment revision and scope checks, Curl/HTTPx/Katana/Dalfox/SQLmap adapters, Nuclei's anonymous-only boundary, Curl config escaping and request bounds, Dalfox discovery-only policy and private JSON config, redacted commands, scanner-user handoff, private file modes, output masking, cleanup after failure and completion, bounded startup recovery, unsupported-feature rejection, broker handoff, and privacy-safe audit records.

Dalfox output coverage pins the discovery-only JSONL command contract, exact canonical URL matching, documented parameter locations, tool and parser provenance, stable ids, deduplication, malformed and out-of-scope rejection, the fixed observation cap, and durable run-event serialization without creating XSS findings. The SQLite/PostgreSQL saved-evidence resolver separately rereads one exact successful owner- and Project-scoped run, rejects partial output, scope or command drift, duplicate evidence, and identity or provenance changes, and derives its active context from the stored observation rather than request data. The active-command contract accepts one URL-bound query observation, pins its location-qualified parameter plus payload, rate, worker, target, reported-request, and time bounds, and rejects unsupported location, provenance, identity, or command changes. Selection coverage caps the reviewed Project catalog, rejects whole-catalog overflow, preserves newest semantic observations, requires paired source-run and observation ids, and keeps cross-owner, cross-Project, stale, and changed evidence unavailable. Execution coverage validates the exact discovery carrier through ordinary policy before replacing only that carrier with the saved-evidence command, requires the matching typed parser context, revalidates the frozen intrusive check and deployment gate, composes protected HTTP material after replacement, and rejects caller-made contexts and carrier or evidence drift without changing direct Dalfox launches. Active-result coverage requires that reviewed context and stream summary, keeps V/A/R confidence distinct, binds proof to its source parameter observation, rejects full request/response capture, and enforces request, row, and field bounds while ordinary Dalfox commands remain discovery-only. Completion coverage accepts Dalfox's findings exit only after a valid reviewed summary and observation, keeps the raw tool code visible, lets output-write failures win, and leaves every ordinary run's exit semantics unchanged. Finding-finalization coverage then rereads the source evidence and active run, recomputes the command, reparses the complete stream, and pins separate V/A/R severity, confidence, validation, identity, and CWE-79 fields. SQLite and PostgreSQL cases cover idempotent occurrences, exact active-line and discovery-run evidence, protected-profile commands, safe summaries without raw proof, and rejection of incomplete, failed, tampered, drifted, or cross-Project output without losing the completed run.

Dalfox evidence-mode coverage recognizes only the maintained discovery, active, and blind-XSS command shapes, validates the separate Web 1.6 discovery and validation rules, and proves clean negative evidence from one mode can't satisfy another mode's check.

#### Query-plan coverage

The SQLite and PostgreSQL plan contracts seed enough Projects, cycles, checks, findings, risk events, and work items to make index choice meaningful. They run the production query builders under `EXPLAIN` and require indexed cycle paging, check filtering and evidence counts, Project risk projection, changed-CVE observation lookup, and due-work selection without depending on a backend's complete plan text.

### Vitest

Use Vitest for browser-module behavior and DOM-bound failure paths that don't require a live server:

```bash
npm run test:unit
```

The shared Vitest configuration runs at most two test files at once. This keeps
the jsdom-heavy suites responsive on high-core development and CI hosts. Tests
also have a 20-second wall-clock ceiling so a ready worker isn't mistaken for a
hung interaction when a constrained host takes longer to schedule it.

#### Shared browser modules and Atlas

`tests/js/unit/` covers browser-module logic in jsdom, including shared composer state, tab/output/history behavior, welcome sequencing, autocomplete, search, and export helpers. Atlas coverage includes the lazy Quick Lookup bridge, list-free lookup mode, entry-point toggling, local validation and retry, failed-replacement recovery without stale-request overwrite, scoped request payloads, cache/provider abstention, privacy-safe events across every log level, exactly-once launch failures across the rail, mobile menu, and shortcut, shared profile tabs, New lookup navigation, stale candidate cancellation, submitted-value owner-scope refresh with stale-result invalidation, no-record actions, bounded ambiguity choices, URL-parent handoff, compact outcome controls, **Search Atlas** versus profile handoff, command prefilling without execution or option-shaped target reinterpretation, copy and explicit Intel refresh actions, exact ambiguous and hidden-record handoff into ordinary Atlas, Project round-trip restoration, all four finding buckets and profile collection pagers, Back focus on desktop and mobile, Project-scoped entity finding creation, and manual-finding edits. Finding-risk helpers keep CISA KEV, EPSS probability and percentile, positive public-exploit-reference flags, NVD CVSS/advisory state, origin, snapshot age, refresh guidance, and stale/unavailable-source labels compact and consistent across Atlas and Projects without coercing `null` values to zero or treating missing data as a no-exploit result. Provider Status coverage pins the same bundled/live source details, publication date, source and model versions, freshness, and exact live-refresh setting guidance shown by the browser catalog. Shared finding-editor coverage pins explicit remediation-group candidate search, preview, confirmation, apply, unsaved-change protection, and view-only controls, plus assessor-authored create/edit payloads, confirmed-target paging and filtering, exact source-target inference, escaped evidence previews, display-only evidence stripping, identifier/reference validation, duplicate confirmation, immutable edit targets, optimistic revisions, Project refresh wiring, final-disposition actor copy, origin/profile drift, comparable and incomparable retest runs, attachment warnings, evidence removal, original-run comparison, guarded verification preview and exact structured confirmation, exactly-once launch, terminal handoff, and the absence of an automatic verification update. Run Details coverage selects bounded saved output lines, creates a finding with source context, attaches exact-line evidence idempotently, retains selection across failures, edits manual findings, enforces view-only permissions, and renders typed Nmap service evidence without free-form output. Project Monitoring coverage pins risk-event acknowledgement, digest opt-in behavior, and readable NVD transition labels. The static button-primitive guard scans both templates and lazy HTML fragments, while Atlas assertions cover the candidate buttons built at runtime. Terminal lifecycle coverage pins normalized browser and server results, exactly-once completion and persistence, masked recents, submit-time prompt history, confirmations, and Files output piping or redirection.

#### Monitoring and Project Assessment

Project Monitoring coverage runs the same event, acknowledgement, view-only, empty, and recovery states through its desktop and mobile renderers. It keeps feed-driven CVE risk actions separate from watcher-fire triage, proves that unassigned events don't appear in a Project, shares one canonical event across linked Projects, and exercises mobile acknowledgement against both source modules and committed bundles.

Project Assessment coverage pins its lazy entry, safe cycle-profile picker, desktop/mobile rendering parity, truthful coverage states, assessment-first section order, cycle-wide target rollups across bounded check pages, target disclosures, bounded newest-first check evidence previews and cycle recent evidence on SQLite/Postgres, bounded Project-scoped service suggestions, reviewed Nmap selectors and blocked broad categories, rejection of custom NSE arguments and argument files, the fixed no-listing FTP anonymous-access check, exact typed success evidence, profile labels and typed Nmap service evidence on desktop and mobile, free-form output omission, ambiguous/conflicting-service abstention, no-launch recommendation reads, category, state, policy, and evidence-availability filters, paging, isolated check and fix-first refresh states that keep the rest of the tab visible, post-attachment per-Project scroll restoration and expansion state, active-tab return context, profile-driven cycle creation and final successful rendering after create and lifecycle reloads, remediation-group finding-change counts, comparison explanations, current and earlier finding links, fix-first observation disclosure state, contextual finding launches with typed check evidence, guarded recommended-action previews, exact digest confirmation, reviewed XSS parameter and OpenAPI artifact selection, one-launch terminal handoff, focus restoration, forward-only lifecycle confirmations, forced reloads that supersede stale cycle detail, lifecycle response-error handling, post-delete empty-state rendering without waiting for HTTP Profiles, preview-backed archived-cycle deletion, cancellation without mutation, touch-sized shared mobile action-sheet choices, view-only permissions, and the shared themed scrollbar on bounded ZAP target selection. The finding-centered retest cases add exact target/check/action/HTTP-role grouping, mismatch explanations, the two-to-ten safe credential-free batch bound, stale digest rejection, independent evidence linking after partial failure, desktop/mobile rendering, explicit confirmation, terminal handoff, and the required human disposition. HTTP-profile browser coverage also pins the shared list and editor, reference-name availability without values, viewer redaction, recoverable load failures, superseded request generations, the Options → Secrets handoff, disabled and incomplete states, explicit role selection, and matching profile ids across preview and launch. Web Surface browser coverage pins authenticated image retrieval, the shared screenshot-preview disclosure and pressable contracts, shared status-badge tones, safe metadata and unavailable-state rendering, bounded paging, visual-change labels and explanations, comparison filtering and grouping, bounded-window notices, full-image navigation, URL and source-run navigation, object-URL cleanup, lazy loading, and matching desktop/mobile tab placement. The shared finding-change component pins the same totals, cycle link, and distinct-remediation copy across desktop Overview, desktop Findings, and the mobile Findings sheet. Browser and API route coverage separately checks that cycle lists receive only bounded profile summaries rather than complete live definitions; API and architecture coverage pin owner scope, frozen target/action revalidation, safe logging and audit fields, OpenAPI parity, and route/module inventories.

Project probe coverage pins the complete reviewed action registry, domain/IP/URL catalog filtering across the service, browser/API routes, and CLI text/JSON output, invalid target-type rejection, policy floors, supported Nmap and Nuclei profiles, feature-gated intrusive Nuclei autocomplete, the anonymous-only Nuclei HTTP boundary, the non-intrusive Dalfox boundary, feature and target failures, the versioned digest projection, stale confirmation, exact personal/team Project target resolution, viewer-safe catalog and plan routes, and anonymous and protected launch permissions. The digest matrix mutates every execution and approval field, including protected-profile revision and template provenance, while proving presentation fields and set-like list order remain stable. Browser and API boundary cases reject empty selectors, unsupported targets, same-owner entities linked only to another Project, and confirmations made after the reviewed entity is suppressed, unlinked, or changed; no rejected confirmation reaches the broker. Launch cases cover explicit Project binding, ordinary run provenance, no direct Assessment writes, compatible coverage reconciliation, protected-profile revision and scope checks, reviewable domain/IP/URL scope summaries without private references, exact safe protected role and credential audit fields, secret-safe public and audit shapes, production-owned private-file cleanup after success, preparation failure, failed spawn, unexpected start failure, repeated cleanup, or incomplete removal, bounded metrics, and SQLite/Postgres routing. The configured PostgreSQL case confirms both anonymous and protected plans through captured broker launches, checks explicit Project and origin-tab binding, inspects redacted and private command material, runs the cleanup hook, and rejects a protected confirmation after the saved profile changes. Browser and API protected-route cases both verify Project binding, private broker arguments, redacted public commands, and cleanup; safe, standard, and intrusive Nuclei profile selections with an HTTP profile stay unavailable and never call the broker. The team matrix requires secret-management permission, and the external CLI confirms a protected launch without exposing private execution fields. Observability cases drive successful, unavailable, rejected, and failed decorator outcomes through their exact log levels and metric labels, prove protected cleanup is retryable and counted once after success, reject control characters and oversized or unknown identifiers before structured fields are formatted, and keep distinctive targets, commands, secrets, and private paths out of records. They also correlate browser and API service records to the generated request and masked owner, keep the same request id in launch logs and audit rows, cover bounded exact-target success, ambiguity, and resolve metrics without target values, and scan probe services, routes, and browser-terminal event literals against the canonical logging inventory. Vitest covers terminal parsing, exact-target-to-entity resolution, readable catalog and plan output including protected role and scope, unavailable responses, disabled History and Recent-command persistence for reads, per-tab accept/decline behavior, same-tab run binding, and bounded browser diagnostics for catalog, response-shape, and confirmed-launch failures. The focused live browser journey exercises the lazy planner and confirmation through normal keyboard submission, then accepts one harmless probe and verifies the browser POST, streamed terminal result, retained preview, exact History command, same-tab behavior, and Project run link.

The external probe CLI coverage also keeps requested service recommendations visible in text output, including the action, optional Nmap profile, compatible targets, and rationale.

#### Assessment handoff and test helpers

Report and evidence-package coverage selects current and archived cycles, preserves the frozen profile, target/check snapshot, rollups, exclusions, evidence and tool provenance, fix-first rows, finding changes, screenshot and unavailable-source warnings, and redaction boundaries, then checks both readable HTML/Markdown and machine-readable archive provenance. The package and report browser controllers keep the selected cycle in their saved payloads and restore archived choices when an existing deliverable is reopened.

The shared Assessment controller coverage also sets and clears reason-required manual check decisions, renders their saved reason, privacy-safe actor, and time on desktop and mobile, checks both action paths, and keeps the control disabled for view-only members.

Large jsdom setup lives in focused helper modules under `tests/js/unit/helpers/` so high-change areas such as app chrome, session identity, and Files/workspace behavior can share setup without growing individual spec files.

### Playwright

Use Playwright for browser-visible behavior where focus, layout, navigation, or live server state is part of the contract:

```bash
bash scripts/run_playwright.sh --asset-bundle-mode bundle
```

#### Browser journeys

`tests/js/e2e/` covers the browser UI against a live Flask server, including mobile behavior, kill/history/search/share flows, team scope switching, browser-visible output behavior, and startup resilience. Project coverage creates and edits an assessor-authored finding through the shared editor against a real confirmed target, including the immutable target shown during edit, and creates another finding from selected saved Run Details lines before verifying the exact typed evidence through the live route. Focused Quick Lookup flows cover the desktop rail, mobile menu, and `Alt+Q` / `Option+Q`, hostname and IP profiles, URL-parent recovery, app and cached-provider evidence, live source-run paging, related-entity navigation, owner-scope refresh, Atlas handoff, and direct form/profile close-to-composer focus restoration without leaking an Option-key glyph. Both bundled and source asset modes exercise these paths.

#### Project Assessment journeys

The focused Assessment spec runs in both bundle and source modes. It creates and removes real cycles, checks empty and derived coverage, reviews a bounded recommendation without contacting an external target, verifies missing-Secret recovery, preserves focus through destructive previews, exercises the mobile action sheet, switches personal and team scope, and confirms that archived team Project history remains readable but can't be changed. Assessment-batch service coverage pins operator ceilings, configured runtime behavior, startup recovery ordering, retry-lineage-aware retention, and preservation of ordinary child runs. The live Project handoff journeys also create a finding from selected transcript lines, attach another saved run as verification evidence, and export the Project report context.

The focused probe spec runs in bundle and source modes. It creates active Projects and confirmed targets through the live routes, submits `probe plan` and a declined `probe run` from the terminal at mobile width, and verifies the exact bounded preview, transcript confirmation, same-tab behavior, and lazy module load without contacting those targets. Unit and CLI coverage also pins active-Project slug completion and conversion to canonical route ids for list, plan, and confirmed run requests. Reloading while that approval is pending proves the old prompt can't launch afterward. A separate harmless Ping against the public test endpoint accepts the confirmation, crosses the browser launch and SSE stream paths, keeps the reviewed plan in the origin tab, and verifies the exact saved History command and Project run link.

#### Browser harness

The browser layer now uses a split config model:

- [.tooling/playwright.config.js](../.tooling/playwright.config.js) keeps a simple single-project run path for editor integration and focused debugging
- [.tooling/playwright.parallel.config.js](../.tooling/playwright.parallel.config.js) is the normal CLI path and balances the suite across 5 isolated projects by default using measured per-file runtime weights. CI currently sets `PLAYWRIGHT_PROJECT_COUNT=3` to reduce browser/server contention on the shared runner.

### Demo Recording

Standalone Playwright specs that record the README demo videos (`tests/js/e2e/demo.spec.js` desktop, `tests/js/e2e/demo.mobile.spec.js` mobile). **Not part of the normal test suite** — excluded from both Playwright configs, guarded by `test.skip(!process.env.RUN_DEMO, ...)`, and run only through wrapper scripts:

```bash
scripts/record_demo.sh                              # desktop OBS recording, 1600×900 app viewport
scripts/record_demo_mobile.sh                       # mobile OBS recording, 502×932 OBS canvas by default
scripts/record_demo.sh --base-url http://localhost:9000
scripts/record_demo.sh --no-arm                     # start immediately when OBS is already lined up
```

Wrappers health-check the container, seed/register the demo session token through the configured app database, probe `GET /workspace/files` with that token so the Files segment can create `response.html`, set `RUN_DEMO=1`, open a headed Chromium window, and use the grouped OBS helper to start and stop recording over its WebSocket API. By default the wrapper pauses on a holding screen before recording starts, which gives you time to select the correct Chromium window in OBS without missing the welcome animation. Use `--no-arm` when OBS is already lined up. The desktop and mobile demos both open the Status Monitor during the long-running ffuf segment so the active run rows and pulse strip are visible in the final video. See [DECISIONS.md](../DECISIONS.md#demo-recording-pipeline) for the rationale behind the capture pipeline.

OBS must be installed and running before you start either wrapper. Enable the WebSocket server in `Tools -> WebSocket Server Settings`; set `OBS_WS_PASSWORD` if your OBS WebSocket requires one.

Desktop OBS preset:

- `OBS -> Settings -> Video`
  - Base (Canvas) Resolution: `1600x900`
  - Output (Scaled) Resolution: `1600x900`
- `OBS -> Settings -> Output -> Recording`
  - Recording Quality: `Indistinguishable Quality, Large File Size`
  - Recording Format: `MPEG-4 (.mpg)`
  - Video Encoding: `Hardware (H.264)`
- `OBS -> Settings -> Audio -> Global Audio Devices`
  - All: `Disabled`
- `Sources -> Add Source -> Screen Capture`
  - Name: `Darklab Desktop Demo`
  - Method: `Window Capture`
  - Window: `[Google Chrome for Testing] darklab_shell`
  - Leave all source options unchecked.
- `Transform -> Edit Transform`
  - Position: `X 0.00`, `Y 0.00`
  - Size: `Width 1600 px`, `Height 900 px`
  - Bounds: `Stretch`, `Width 1600 px`, `Height 900 px`
  - Crop: `Left 0 px`, `Right 4 px`, `Top 174 px`, `Bottom 0 px`

Mobile OBS preset:

- `OBS -> Settings -> Video`
  - Base (Canvas) Resolution: `502x932`
  - Output (Scaled) Resolution: `502x932`
- `OBS -> Settings -> Output -> Recording`
  - Recording Quality: `Indistinguishable Quality, Large File Size`
  - Recording Format: `MPEG-4 (.mpg)`
  - Video Encoding: `Hardware (H.264)`
- `OBS -> Settings -> Audio -> Global Audio Devices`
  - All: `Disabled`
- `Sources -> Add Source -> Screen Capture`
  - Name: `Darklab Mobile Demo`
  - Method: `Window Capture`
  - Window: `[Google Chrome for Testing] darklab_shell`
  - Leave all source options unchecked.
- `Transform -> Edit Transform`
  - Position: `X 0.00`, `Y 0.00`
  - Size: `Width 502 px`, `Height 932 px`
  - Bounds: `Stretch`, `Width 502 px`, `Height 932 px`
  - Crop: `Left 0 px`, `Right 4 px`, `Top 174 px`, `Bottom 0 px`

Desktop and mobile demo configs share a central visual contract in [.tooling/playwright.visual.contracts.js](../.tooling/playwright.visual.contracts.js), and both specs assert that contract at startup through `tests/js/e2e/visual_guardrails.js`. That keeps viewport, pixel density, touch/mobile-mode assumptions, and `/status` health aligned with the wrapper/config setup instead of drifting silently.

Both demo specs also read from one named visual-history fixture in `tests/js/e2e/visual_history_fixture.js`, which returns realistic paginated `/history` payloads with enough rows to keep the history drawer and mobile recents sheet in their pagination state during recordings.

### UI Screenshot Capture

Standalone Playwright specs that generate a curated screenshot pack for design review, theming, and visual QA (`tests/js/e2e/ui-capture.desktop.capture.js`, `tests/js/e2e/ui-capture.mobile.capture.js`). Guarded by `test.skip(!process.env.RUN_CAPTURE, ...)` and run only via the wrapper. The wrapper accepts `--asset-bundle-mode source|bundle` when a capture needs to compare local source assets with the committed release bundles.

```bash
scripts/capture_ui_screenshots.sh
scripts/capture_ui_screenshots.sh --ui desktop
scripts/capture_ui_screenshots.sh --theme apricot_sand --ui mobile
scripts/capture_ui_screenshots.sh --theme all
scripts/capture_ui_screenshots.sh --theme all --theme-variant light
```

The wrapper sets `RUN_CAPTURE=1` and writes PNGs, per-UI manifest JSON files, and a static `index.html` review page to `/tmp/darklab_shell-ui-capture/`. Unset `--theme` and `--theme default` resolve to the configured app default theme slug from `app/config.py`, so default captures are stored under that real theme name instead of a duplicate `default/` folder. The review page groups scenes by UI/theme and includes a full-screen image viewer with left/right keyboard navigation. Capture runs boot an isolated temp app instance with seeded history, workspace storage enabled, a fixed capture session token, and an in-memory fake Redis client so HUD status, `/diag`, recents, history-heavy states, Files panel states, and the Status Monitor active-telemetry modal look production-like. See [`tests/ui-capture-scenes.md`](./ui-capture-scenes.md) for the reviewer companion that describes every scene (desktop + mobile) with per-scene "what to look for" notes and the cross-cutting design-system contracts each scene exercises.

The capture configs use the same shared visual contract file as the demo pipeline, and `ui_capture_shared.js` runs `visual_guardrails.js` during each `freshHome(...)` reset. That means every captured scene re-checks viewport, density, touch/mobile-mode expectations, `/status` health, the fixed capture token, and the minimum seeded `/history` shape before screenshots are taken.

Capture theme application now waits for the requested theme name, the active theme-registry entry, and the resolved `--bg` CSS variable to agree before screenshots are taken. The wrapper also accepts `--theme-variant light|dark|all` to restrict `--theme all` runs to one color-scheme family without changing the underlying theme registry or file order.

Capture seeding uses the named `visual-flows` preset in `scripts/seed_history.py`, so the isolated app instance always starts with the same history volume and age spread instead of relying on hard-coded wrapper flags. That preset now stars only two commands so the desktop rail still shows Recent items, and its seeded commands come from the command-registry example set rather than hand-written built-in commands.

### Container Smoke Test

`scripts/container_smoke_test.sh` reuses the stable `darklab_shell-test:cache` image when it exists and still matches the Docker runtime inputs, runs every user-facing command from the shared smoke corpus through the live app, and compares each command's output against `tests/py/fixtures/container_smoke_test-expectations.json`. The wrapper uses `scripts/run_pytest.sh`, so it selects the repository virtualenv when one exists and otherwise uses the installed `pytest` command. Pass `--build` to force a cache-image rebuild; otherwise the cache refreshes itself when `Dockerfile`, `app/requirements.txt`, `entrypoint.sh`, or a container helper changes. The live fixture copies an app tree containing an owner-only `config.py` into the read-only development source location, starts with an ephemeral `/app`, and verifies the staged file is readable but not writable as `appuser` before exercising the app. The shared corpus includes `app/conf/commands.yaml` examples that do not require workspace setup or encrypted provider secrets, plus workflow step commands, so the smoke suite covers the commands the shell suggests directly plus the guided playbooks exposed through the workflows UI. Required-secret tools can still contribute registry-declared help examples when those examples are marked with `smoke.profile: unauthenticated`, which catches broken CLI imports without needing provider keys. The release bundled-tool pass separately checks every required executable and probes version output, including the isolated Schemathesis CLI. It also enables Files in the smoke container, fails fixture startup if the Files endpoint is unavailable, and runs the workspace-required command examples from `app/conf/commands.yaml` against `tests/py/fixtures/container_smoke_test-workspace-expectations.json`, covering session-file reads, writes, managed Amass database directories, and generated output files. Interactive PTY examples marked with `interactive: true` run through `/pty/runs` against `tests/py/fixtures/container_smoke_test-interactive-expectations.json`, so the smoke pass can catch missing PTY-only tools and broken trigger-flag wiring separately from regular `/runs` commands. Nuclei cases seed a retained workspace version marker while the managed cache is empty, warm the real templates, then require the `appuser` process to read the resulting snapshot from the scanner-owned cache before any template-backed check continues. Focused production-install coverage separately proves the startup bootstrap skips disabled and populated caches, installs an empty cache, rejects a manifest symlink, leaves startup successful after update or manifest failures, and suppresses updater stdout and stderr. Raw-packet readiness is enabled inside the isolated smoke project, where Nmap, Naabu, and Masscan scan test-owned services. The HTTP targets deliberately listen on `8888`, proving the scanner can reach that port on remote containers while both connect and raw-IP attempts against the local app stay blocked. A second app service applies a restricted CIDR to a hostname-resolved target, confirms Nmap's raw traffic is rejected while an adjacent target remains reachable, keeps Naabu in connect mode, and denies Masscan's packet-socket path. The live stack also saves a v2 playbook, captures a response from a test-owned service, feeds it into a second command, and verifies both linked runs keep their execution ancestry. The fixture removes stale `darklab_shell-test-*` Compose containers, networks, and volumes before startup and after teardown so interrupted local runs don't leave test resources behind. It catches drift between surfaced commands and actual tool behavior, including renamed flags, changed output, missing tools, broken workspace path rewriting, or lost Linux scanner capabilities. It's not part of the default fast loop; run it after Dockerfile, packaged-tool, base-image, command-registry example, workspace file-flag, interactive PTY example, or workflow command changes.

```bash
./scripts/container_smoke_test.sh                           # full run
./scripts/container_smoke_test.sh --build                   # force cache-image rebuild, then run
./scripts/container_smoke_test.sh -k nmap                   # filter by pattern
./scripts/container_smoke_test.sh --cmd "nmap -h"           # single command
```

GitLab CI exposes this as the manual `container-smoke-test` job for verifying a fresh image before merging dependency or Dockerfile changes. Ordinary branch image builds also retain a CycloneDX SBOM and full Grype report and fail on fixed Critical findings before a release tag is created. Protected tags resolve one Python base index, build native AMD64 and ARM64 staging children, and run production-installation, bundled-tool, Syft, and Grype checks against each child before the canonical image index can exist. The ARM64 smoke also starts Redis and Postgres. Later evidence and signing jobs consume the retained platform contracts, SBOMs, and reports. A protected branch rehearsal publishes a temporary index and repeats anonymous native pulls without promoting or creating release artifacts. Maintainers can use `release-image-recheck` to rerun production startup, bundled tools, and the scan against either an existing child digest or an index digest plus its selected platform without rebuilding it.

---

## History Seeding

`scripts/seed_history.py` populates the history database with realistic runs for a specific session (UUID or `tok_` token). It's a manual-QA helper, not a test — use it when you want to exercise user-facing flows that only reveal themselves against a populated history: the history drawer, fuzzy history search, reverse-i-search, date/exit/star filters, and token-migration workflows.

Seeded commands are pulled from the command-registry example catalog, so the generated history stays aligned with the user-facing command examples shown in the app. The seeder also avoids adjacent duplicate commands, which keeps Recent/history surfaces looking closer to a real session while still allowing duplicates across the broader run set.

The script must run **inside the container** so the same SQLite version that owns the DB does the writes; it refuses to write from the host by default.

```bash
docker compose -f compose.dev.yaml exec -T shell python - --new-token < scripts/seed_history.py
```

Use `--help` for the full flag list and invocation forms.

---

## Choosing the Right Test Layer

Use `pytest` when the change primarily affects:

- Flask routes
- config/theme loading
- command validation and rewrites
- persistence or retention logic
- trusted-proxy behavior
- structured logging

Use `Vitest` when the change primarily affects:

- browser helpers
- state management
- prompt/composer logic
- tab/history/search/output behavior that can be exercised in jsdom
- DOM wiring that does not need a real browser engine

Use `Playwright` when the change primarily affects:

- real browser focus and keyboard behavior
- scroll geometry or layout-dependent UI behavior
- mobile interactions
- live SSE/browser timing behavior
- integrated flows spanning multiple browser modules

Use the container smoke test when the change primarily affects:

- command-registry example commands (adding, removing, or editing examples)
- Dockerfile contents
- packaged binaries or scanners
- runtime image behavior
- compose/runtime wiring that cannot be trusted from unit tests alone

If a change touches more than one layer, still start with the cheapest one that can fail meaningfully.

---

## Test Artifacts

Local and CI test runs can write debugging output under the repo’s test-result paths.

Common artifact locations:

| Path | Produced by | Purpose |
| --- | --- | --- |
| `test-results/` | Playwright and other focused test helpers | Browser failure context, screenshots, error markdown, and related debugging output |
| `tests/py/fixtures/container_smoke_test-expectations.json` | smoke-test capture workflow | Stored expected command corpus output for the Container Smoke Test |
| `test-results/container_smoke_test.xml` | container smoke test | JUnit-style result output when the smoke test is run directly or through its wrapper |

Practical note:

- if a Playwright test fails, inspect `test-results/` first
- if the smoke test output changed intentionally, recapture the baseline before treating the diff as expected

---

## Testing Conventions

- Prefer focused tests for specific behavior regressions instead of large all-purpose integration tests.
- When a branch depends on a browser API or network error, make the failure deterministic in the harness instead of relying on the environment.
- For browser tests that interact with history, remember that the server is eventually consistent around run persistence. Retry or re-open the drawer when needed.
- Python and Playwright harnesses raise app rate limits by default so unrelated tests should not carry per-test limiter workarounds.
- For tests that explicitly exercise per-IP rate-limit behavior, use `makeTestIp()` to get a deterministic `198.18.x.x` test-network address in `X-Forwarded-For`.
- For browser tests that need a long-running command, prefer a browser-side `window.fetch` mock that returns an open SSE stream, like the kill-spec coverage.
- When a browser test needs to exercise a `.catch(...)` branch, prefer aborting the request or rejecting the promise rather than returning a 500 response.
- `npm run lint:licenses` checks SPDX notices on project-owned source used by every test layer while leaving generated fixtures and third-party files under their existing terms.
- Keep the live-listing commands, compact README Repository Layout, and configuration reference current. `tests/py/test_docs.py` checks those documentation contracts along with local links, full tables of contents, runtime support, capture-scene guidance, asset references, and operator-facing defaults.

---

## Related Docs

- [CONTRIBUTING.md](../CONTRIBUTING.md) - contributor setup, validation, and merge request workflow
- [ARCHITECTURE.md](../ARCHITECTURE.md#test-suite) - testing architecture and runtime boundaries
- [DOC_STANDARDS.md](../DOC_STANDARDS.md) - documentation contracts enforced by the meta-tests
- [ui-capture-scenes.md](ui-capture-scenes.md) - visual-review scenes and capture workflow
