# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.8.1
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.8.4] - Unreleased

### Added

- **Findings now include offline EPSS and CISA KEV context, with feed-driven Project Monitoring alerts.**
  - **Why:** Assessors can put known-exploited and higher-probability CVEs first without sending saved targets or findings to another provider when they open a result.
  - **What:**
    - Release-pinned, attributed FIRST EPSS and CISA KEV snapshots provide a dated offline baseline. Operators can opt into daily allowlisted refreshes with conditional requests, database leases, strict validation, bounded retries, and last-good fallback; `providers` shows the current source and freshness state.
    - `intel cve`, Atlas, Project Findings, reports, evidence packages, API responses, and desktop/mobile finding rows use the same stored public-risk signals. KEV and EPSS are kept separate, missing or stale data stays explicit, and CISA dates are labeled as federal context rather than an operator SLA.
    - Findings are ordered by KEV, EPSS probability and percentile, then age until normalized CVSS storage lands. Reports and evidence packages pin the exact source versions and values used so an older export stays explainable.
    - Accepted feed changes can raise owner-scoped KEV and EPSS threshold events without rescanning. Durable work cursors, EPSS hysteresis, canonical acknowledgements, Project projections, and an opt-in digest setting prevent replay, flapping, duplicate Project alerts, and cross-owner disclosure.
  - **Tests:** Focused backend coverage exercises bundle validation, refresh safety, stale and unavailable states, ranking, queue fairness and retries, escalation hysteresis, acknowledgement scope, report provenance, configuration bounds, and privacy-safe errors. Browser unit coverage pins compact KEV/EPSS labels and Project Monitoring acknowledgement and digest behavior; migration, architecture, OpenAPI, asset, and documentation checks cover the shared schema and public contracts.
- **Atlas now has an exact, read-only lookup workflow for saved hostnames, IP addresses, and HTTP(S) URLs.**
  - **Why:** Quick Lookup opens saved evidence directly, including suppressed and source-less records, without searching or paging through the Atlas list.
  - **What:**
    - Browser and API clients resolve canonical values in personal, team, or explicit Project scope and reuse the same bounded Overview, Evidence, Findings, and Intel profile shown in Atlas.
    - Invalid input, no-record results, bounded legacy ambiguity, and unmatched URL parent hosts stay distinct and recoverable. **Open in Atlas** is an explicit transition, while search, scope switching, copy, and command-prefill actions remain non-destructive.
    - Lookup reads only saved evidence and owner-scoped Intel snapshots. It doesn't create records, run commands, contact providers, or log submitted and canonical values; **Refresh intel** remains a separate action.
    - Owner changes clear stale results, irrelevant Atlas list and bulk loads stay out of lookup mode, and the type/signature index keeps exact candidate searches efficient on SQLite and Postgres.
  - **Tests:** Resolver, route, API, browser, PostgreSQL, privacy, logging, query-plan, and bundled/source Playwright coverage is summarized in the Tests section below.
- **Quick Lookup is available beside Atlas throughout the shell.** The desktop rail, mobile application menu, and `Alt+Q` / `Option+Q` shortcut all open the same lazy Atlas lookup mode without adding another modal or increasing the initial shell payload. Using the active entry again closes Quick Lookup instead of resetting the current result in place.

### Changed

- **JavaScript development dependencies now include current security fixes for brace expansion, URL parsing, and HTTP handling.** The locked dependency tree uses `brace-expansion` 5.0.9, `fast-uri` 3.1.5, and `undici` 7.29.0, clearing the reported high-severity advisories without changing the app's runtime behavior.
- **The cryptography runtime dependency now uses 50.0.0.** This includes the upstream fix for CVE-2026-69247 while keeping the app's existing certificate parsing and encrypted-secrets behavior.
- **Atlas entity details now put app-captured evidence before external provider data.** Domain and IP profiles separate findings on the host from findings on their immediate URL and port children, show a clearly labeled combined host-surface total, and list both related URLs and related ports with working pagination. A new scan-coverage section distinguishes app-captured ports, scans that surfaced no ports, and entities without an app port scan. Host profiles also show a bounded app-captured port list with protocol, service, version, banner availability, sightings, last-seen time, and source-run count. URL profiles can reuse that list only as clearly labeled parent-host evidence. Project Overview and Atlas now calculate direct finding totals, severities, review states, verification states, suppression, occurrences, and latest activity through the same contract; suppressed findings stay visible as a separate count without inflating active review or verification work. Cached Intel also uses one coverage and freshness contract across both surfaces, including provider and snapshot counts, last refresh time, high-signal highlights, certificate state, and a provenance-aware comparison of app-captured and provider-reported ports. Domain profiles surface relevant certificate evidence, while host profiles label recorded port differences without turning them into findings; raw provider responses remain in the existing expandable collection. Project-filtered profiles add the selected entity's watcher state and recent matched changes, while owner-wide profiles omit Project monitoring instead of presenting project activity out of context. The quick detail pane follows a stable Observed, Findings, Relationships, Evidence, Metadata, then External intelligence order, gives section separators balanced breathing room, and caps long finding, relationship, port, run, and import collections at three rows before linking to the focused profile. Direct findings and related entities use the same full-width clickable row treatment as the rest of Atlas, while a source run's command opens Run Details and its cleanup action stays in the focused Evidence view. Direct findings return to the same profile scroll position, linked projects can be opened without removing their link, and URL or port details link back to their stored parent host. The same owner or project scope is carried through the browser route and API v1 response, whose compatible detail payload now also groups the normalized overview as observed evidence, finding summary, relationships, and Intel.
- **Atlas now offers focused entity profiles without leaving the current results.** **View profile** expands the existing dialog into Overview, Evidence, Findings, and Intel views, while **Back to results** restores the active filters, page, selected row, and reading position without reloading unrelated detail. On both desktop and mobile, the existing profile now shows the canonical identity, first and last observation, project-link count, suppression, and missing-source state above its tabs and includes a **Copy value** action. Finding summary cards open exact direct, related-URL, related-port, or combined result sets instead of widening the query behind the displayed count. Related entity profiles can return to the previous entity and local view, Project round trips reopen the same Atlas profile, and finding review changes refresh the affected detail without reloading the result list. Provider/app port differences link directly to the app evidence and cached provider data that explain them. Empty and partial profiles point to the next useful action, including running a scan, refreshing Intel, or opening the parent host. Entity links from transcripts, Run Details, Projects, and Project Overview open the focused profile immediately. Mobile uses the same views and its existing drill-in navigation instead of stacking another overlay.

### Tests

- **Exact Atlas lookup coverage pins canonicalization, single-host CIDR rejection, owner isolation, project scope, legacy ambiguity, unreadable-URL parent fallback, privacy-safe completion, rejection, ambiguity, and degraded-profile logging, schema migration, and indexed query plans.** Route, API v1, OpenAPI, architecture, SQLite, and Postgres checks prove that found results reuse the ordinary entity-detail contract, personally owned entities shared through team runs or imports remain correctly scoped, candidate lists stay bounded, and lookup does not materialize records, log submitted values, write raw submitted URLs to audit data, or contact Intel providers.
- **Atlas Quick Lookup coverage pins its privacy boundary, recoverable outcomes, shared profile handoff, and shell entry points.** Backend checks prove browser and API lookups don't read the process or Redis Intel cache, contact providers, mutate protected tables, or place submitted URLs in structured logs; the PostgreSQL fixture covers project filtering, direct-team precedence, ambiguity, URL-parent fallback, suppressed orphan records, and saved owner-scoped Intel snapshots. Browser unit checks cover failed-replacement recovery, stale-request rejection, all four finding buckets and collection pagers, related-entity and finding return state, root Back behavior, entry-point toggling, and the unchanged transcript entity-token menu. Focused Playwright coverage exercises `Alt+Q` / `Option+Q`, one-overlay focus, direct form and profile dismissal, source-run paging, hostname, URL-parent, and IP evidence, Atlas handoff, and close-to-composer focus restoration without leaking an Option-key glyph.

- **Atlas profile coverage now pins relationship, finding, scan, app-port, and project-monitoring boundaries across SQLite and Postgres.** Existing route, API v1, team-scope, Postgres, and browser tests cover child-only critical findings, direct-versus-related totals, project-scoped navigation hints, parent-host resolution, personal/team isolation, related URL and port paging, app-first grouping, linked-project navigation, entity-matched watcher changes, owner-wide monitoring exclusion, and desktop/mobile finding drill-in. Representative large-history fixtures also cover hundreds of related URLs, ports, findings, and source runs, bounded first responses and port samples, port metadata and source-run counts, unresolved and IPv6 values, long mobile URLs, quiet scans, stale or missing Intel, Project Overview/Atlas scan, port/service, direct-finding, certificate, and provider/app comparison parity, degraded provider payload logging, the public overview schema, and portable SQLite/Postgres query-plan checks that accept the supported indexed relationship plans without a schema change.
- **Focused Atlas profile coverage keeps each browser workflow within a CI-friendly runtime budget.** Desktop and mobile assertions run against both bundled and source assets and cover quick-detail expansion, local profile views, keyboard navigation, direct profile launches, exact finding-bucket navigation, related-entity and Project return paths, detail-only finding mutation refreshes, provider/app evidence actions, actionable degraded states, Back-to-results state restoration, Project Overview handoff, and the absence of unrelated list or detail requests. The longest composite entity-profile and desktop/mobile port-profile checks have narrow CI allowances without changing the suite-wide timeout. Route, API v1, OpenAPI, and Postgres assertions keep every finding bucket owner/project-scoped, bounded, and independently paged.

---

## [2.8.3] - 2026-07-29

### Fixed

- **GELF status fields now keep one OpenSearch-compatible type across the event stream.**
  - **Root cause:** request logs used the generic `_status` field for numeric HTTP codes while Intel provider and other lifecycle events reused it for text such as `ok` and `error`. Once OpenSearch mapped `_status` as a number, it rejected later text values with `mapper_parsing_exception`.
  - **Fix:** HTTP codes now use numeric `http_status`, while provider, workflow, schedule/watcher, AI, Project, team, and export states use feature-specific string fields. The shared GELF boundary no longer emits `_status`; it safely routes any remaining generic or invalid status value away from established numeric mappings.
  - **Tests:** formatter coverage exercises current semantic status fields, legacy numeric and string status payloads, invalid HTTP values, and explicit-field precedence. Existing request, Intel, AI, team, Atlas, Project, and export-log assertions now pin their replacement fields without increasing the test count.

---

## [2.8.2] - 2026-07-28

### Fixed

- **Production lifecycle commands now keep operator Compose overrides active.** When `compose.operator.yaml` exists beside the installed stack, `darklab-deploy` includes it for backup, restore, database migration, upgrade validation and printed restart commands, and removal. Restored containers no longer restart from the release-owned base alone.

- **History bulk deletion now follows the active filters and previews the exact number of affected runs.** The confirmation shows matching and non-favorite totals, and both desktop History and mobile recents delete the complete filtered result set instead of clearing unrelated runs or processing only the first page.

- **Unassigned watcher Project scope is now represented consistently in run-finalization type hints.** This removes a false editor error from the watcher-scope regression coverage without changing runtime behavior.
