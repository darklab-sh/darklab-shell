# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.8.1
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.8.4] - Unreleased

### Added

- **Atlas now has an exact, read-only lookup workflow for saved hostnames, IP addresses, and HTTP(S) URLs.** Browser and API clients can resolve a canonical value directly in the active personal, team, or project scope without searching a paged entity list, including suppressed and orphan-source entities. The response keeps legacy ambiguity and unmatched URL parent candidates explicit, never creates or refreshes data, and reuses the normal bounded Atlas profile. In the browser, Quick Lookup is a dedicated mode of the existing Atlas dialog, with its own form and navigation root, the shared Overview, Evidence, Findings, and Intel renderer, preserved collection paging and related-entity navigation, and an explicit **Open in Atlas** transition. It skips normal list, saved-view, filter, import, export, and bulk-action loads while active, reruns a submitted value when owner scope changes, and keeps one desktop/mobile surface and focus lifecycle. A new cross-owner type/signature index keeps the candidate seek efficient on SQLite and Postgres.

### Changed

- **Atlas entity details now put app-captured evidence before external provider data.** Domain and IP profiles separate findings on the host from findings on their immediate URL and port children, show a clearly labeled combined host-surface total, and list both related URLs and related ports with working pagination. A new scan-coverage section distinguishes app-captured ports, scans that surfaced no ports, and entities without an app port scan. Host profiles also show a bounded app-captured port list with protocol, service, version, banner availability, sightings, last-seen time, and source-run count. URL profiles can reuse that list only as clearly labeled parent-host evidence. Project Overview and Atlas now calculate direct finding totals, severities, review states, verification states, suppression, occurrences, and latest activity through the same contract; suppressed findings stay visible as a separate count without inflating active review or verification work. Cached Intel also uses one coverage and freshness contract across both surfaces, including provider and snapshot counts, last refresh time, high-signal highlights, certificate state, and a provenance-aware comparison of app-captured and provider-reported ports. Domain profiles surface relevant certificate evidence, while host profiles label recorded port differences without turning them into findings; raw provider responses remain in the existing expandable collection. Project-filtered profiles add the selected entity's watcher state and recent matched changes, while owner-wide profiles omit Project monitoring instead of presenting project activity out of context. The quick detail pane follows a stable Observed, Findings, Relationships, Evidence, Metadata, then External intelligence order, gives section separators balanced breathing room, and caps long finding, relationship, port, run, and import collections at three rows before linking to the focused profile. Direct findings and related entities use the same full-width clickable row treatment as the rest of Atlas, while a source run's command opens Run Details and its cleanup action stays in the focused Evidence view. Direct findings return to the same profile scroll position, linked projects can be opened without removing their link, and URL or port details link back to their stored parent host. The same owner or project scope is carried through the browser route and API v1 response, whose compatible detail payload now also groups the normalized overview as observed evidence, finding summary, relationships, and Intel.
- **Atlas now offers focused entity profiles without leaving the current results.** **View profile** expands the existing dialog into Overview, Evidence, Findings, and Intel views, while **Back to results** restores the active filters, page, selected row, and reading position without reloading unrelated detail. Finding summary cards open exact direct, related-URL, related-port, or combined result sets instead of widening the query behind the displayed count. Related entity profiles can return to the previous entity and local view, Project round trips reopen the same Atlas profile, and finding review changes refresh the affected detail without reloading the result list. Provider/app port differences link directly to the app evidence and cached provider data that explain them. Empty and partial profiles point to the next useful action, including running a scan, refreshing Intel, or opening the parent host. Entity links from transcripts, Run Details, Projects, and Project Overview open the focused profile immediately. Mobile uses the same views and its existing drill-in navigation instead of stacking another overlay.

### Tests

- **Exact Atlas lookup coverage pins canonicalization, owner isolation, project scope, legacy ambiguity, URL-parent fallback, schema migration, and indexed query plans.** Route, API v1, OpenAPI, architecture, SQLite, and Postgres checks also prove that found results reuse the ordinary entity-detail contract and that lookup does not materialize a missing entity.
- **Atlas Quick Lookup browser coverage pins its dedicated mode and shared profile handoff.** Unit checks cover the lazy bridge, personal and project request bodies, list-free first open, New lookup and result restoration, scoped profile rendering, and the explicit transition into ordinary Atlas without adding a second overlay.

- **Atlas profile coverage now pins relationship, finding, scan, app-port, and project-monitoring boundaries across SQLite and Postgres.** Existing route, API v1, team-scope, Postgres, and browser tests cover child-only critical findings, direct-versus-related totals, project-scoped navigation hints, parent-host resolution, personal/team isolation, related URL and port paging, app-first grouping, linked-project navigation, entity-matched watcher changes, owner-wide monitoring exclusion, and desktop/mobile finding drill-in. Representative large-history fixtures also cover hundreds of related URLs, ports, findings, and source runs, bounded first responses and port samples, port metadata and source-run counts, unresolved and IPv6 values, long mobile URLs, quiet scans, stale or missing Intel, Project Overview/Atlas scan, port/service, direct-finding, certificate, and provider/app comparison parity, degraded provider payload logging, the public overview schema, and portable SQLite/Postgres query-plan checks that accept the supported indexed relationship plans without a schema change.
- **Focused Atlas profile coverage keeps each browser workflow within a CI-friendly runtime budget.** Desktop and mobile assertions run against both bundled and source assets and cover quick-detail expansion, local profile views, keyboard navigation, direct profile launches, exact finding-bucket navigation, related-entity and Project return paths, detail-only finding mutation refreshes, provider/app evidence actions, actionable degraded states, Back-to-results state restoration, Project Overview handoff, and the absence of unrelated list or detail requests. Route, API v1, OpenAPI, and Postgres assertions keep every finding bucket owner/project-scoped, bounded, and independently paged.

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
