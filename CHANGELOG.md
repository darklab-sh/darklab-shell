# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.9.0
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [3.0.0] - Unreleased

### Changed

- **The remaining owner-scoped queries now use the reviewed adapter boundary without changing ownership behavior.**
  - **Before:** The final Phase 3A slice contained 52 direct sites across AI assists and context, shell built-ins, CVE risk escalation, structured finding diffs, team storage, audit browsing, startup backfills, and the additive principal foundation.
  - **After:** All 52 sites have an explicit equivalence decision. Thirty-four now use personal-only, team-capable, team-only, or composite adapters. The 12 principal-foundation queries, two legacy membership-hash lookups, two exact risk-state compound keys, one attribution-only audit filter, and one cross-table watcher backfill remain named exceptions with Phase 3B replacements. Personal ownership still means the current session identity, no stored owner or result set changed, and no unclassified direct ownership predicate remains.
  - **Tests:** SQLite and Postgres fixtures exercise two personal owners, team ownership, `NULL` team rows, and empty-team rows together across every adopted adapter shape. Focused subsystem suites and the final review ledger cover reads, mutations, cleanup, worker paths, last-owner protection, and the complete checked exception boundary. Atlas mobile profile coverage waits for the completed Back-navigation render before checking list and detail visibility, avoiding a full-suite timing race without weakening the expected UI state.
- **Automation, notifications, OAST, and ZAP ownership queries now use the reviewed query-adapter boundary without changing ownership behavior.**
  - **Before:** This slice contained 28 direct ownership predicates across schedules, watchers, notification channels and events, OAST correlations, and ZAP connector jobs.
  - **After:** All 28 sites have an explicit equivalence decision. Twenty-seven now use the team-capable, token-keyed, or composite adapters; the exact ZAP assessment-to-HTTP-profile correlation remains a named exception for the principal cutover. Personal ownership still means the current session or durable token, connector rows keep their empty-team-only rule, automation and notification rows keep accepting `NULL` or empty personal team markers, no stored owner changed, and this slice required no non-equivalent behavior correction.
  - **Tests:** SQLite and Postgres fixtures exercise two personal owners, team ownership, `NULL` team rows, and empty-team rows together through the actual connector, schedule, watcher, and notification owner helpers. Focused subsystem coverage pins list, detail, mutation, import, cleanup, retention, archived-team pausing, and worker behavior plus the reviewed exception ledger.
- **Files, workflows, secrets, and supporting session state now use the reviewed query-adapter boundary without changing ownership behavior.**
  - **Before:** This slice contained 40 direct ownership predicates across preferences, variables, recent values, starred commands, session migration, workflow definitions and executions, encrypted secrets, and workspace-file metadata.
  - **After:** All 40 sites have an explicit equivalence decision. Thirty-nine now use the personal-only, team-capable, token-keyed, or composite adapters; the exact workspace-metadata expression that supports both direct team ownership and its older flattened owner key remains a named exception for the principal cutover. Personal ownership still means the current session identity, team secret scopes still use their existing flattened vault key, no stored owner changed, and this slice required no non-equivalent behavior correction.
  - **Tests:** SQLite and Postgres fixtures exercise two personal owners, team ownership, `NULL` team rows, and empty-team rows together through the actual workflow, recent-value, secret-scope, and workspace-metadata helpers. Focused and subsystem coverage pins list, detail, mutation, session migration, cleanup, retention, and worker behavior plus the reviewed exception ledger.
- **Projects, Assessments, and Atlas ownership queries now use the reviewed query-adapter boundary without changing what users can see or modify.**
  - **Before:** This slice contained 156 ownership predicates spread across Project records and metadata, assessment evidence and findings, Atlas imports and lookups, evidence packages, reports, cleanup, and supporting worker paths.
  - **After:** All 156 sites have an explicit equivalence decision. One hundred sixteen now use the personal-only, team-capable, token-keyed, or composite adapters; 40 exact row correlations, flattened metadata keys, compound keys, conflict targets, ranking expressions, and attribution hashes remain named exceptions because the generic adapters do not represent those shapes. Personal ownership still means the current session identity, no stored owner changed, and this slice required no non-equivalent behavior correction.
  - **Tests:** SQLite and Postgres fixtures exercise two personal owners, team ownership, `NULL` team rows, and empty-team rows together. Positive owner fixtures use production-valid UUIDs, and the credential dump check now verifies the complete URL-safe secret payload even when it contains underscores. Focused and subsystem coverage pins Project, Assessment, and Atlas list, detail, mutation, import, export, cleanup, retention, and worker result sets plus the reviewed exception ledger.
- **History and run ownership queries now use the reviewed query-adapter boundary without changing what users can see or modify.**
  - **Before:** The History/run slice contained 28 direct ownership predicates whose session and team behavior had to be inferred from each SQL fragment.
  - **After:** All 28 sites have an explicit equivalence decision. Twenty-two now use the personal-only, team-capable, or composite owner adapters; six column-to-column ownership correlations remain named exceptions for the principal cutover. Personal ownership still means the current session identity, and no stored owner or result set changed.
  - **Tests:** SQLite and Postgres fixtures exercise two personal owners, team ownership, `NULL` team rows, and empty-team rows. Focused cases also pin History filtering, run visibility, snapshot mutation, workspace-path retention, and the reviewed exception ledger.
- **Legacy owner-scoped SQL now has a checked query-adapter boundary ahead of the principal cutover.**
  - **Before:** Personal-only, team-capable, token-keyed, composite-key, and actor-attribution queries built their owner predicates independently, so a seemingly mechanical helper conversion could change which `NULL` or empty-team rows were returned.
  - **After:** Shared adapters keep the current session identity as the personal owner while requiring each caller to state its table shape and personal team-row representation. The first checked inventory recorded 322 direct ownership SQL sites, their tables, operations, key and team-column shapes, present result sets, planned subsystem branch, and later principal-era replacement; migration, principal-foundation, and reviewed relational SQL remain named exceptions after the bounded Phase 3A conversions.
  - **Tests:** SQLite and real Postgres fixtures contain two personal owners, a team owner, `team_id IS NULL`, and `team_id = ''` at the same time, proving each adapter's exact result set. A repository check fails when direct ownership SQL changes without refreshing the reviewed inventory.
- **Principal credentials now resolve through one fail-closed authentication boundary with a complete self-service lifecycle.**
  - **Before:** Legacy identity parsing was spread across request helpers, and a revoked or unknown session token could collapse into an empty anonymous owner instead of preserving the authentication failure.
  - **After:** A typed resolver distinguishes missing, valid, malformed, unknown, expired, revoked, and disabled-principal states before owner resolution. The additive `/auth` surface supports anonymous workspace upgrade, one-time portable credential and scoped PAT issuance, safe metadata reads, labels, expiry, replacement-first rotation, independent revocation, final-credential lockout protection, bounded use tracking, and privacy-safe rate limits and audit events. Existing session-owned product routes remain behind an explicit temporary adapter and reject principal credentials until their ownership cutover.
  - **Tests:** SQLite and real Postgres coverage exercises every credential state, malformed and conflicting transports, scope enforcement, one-time secret responses, audit redaction, issuance and redemption limits, bounded activity writes, and concurrent revocation without accidental principal lockout.
- **The v3 principal model now has an additive persistence foundation without changing the active identity flow.**
  - **Before:** The accepted principal and credential contracts existed only in documentation, while all live requests and stored ownership still used anonymous UUIDs or raw `tok_` session tokens.
  - **After:** Matching SQLite and Postgres tables now store stable principals, one personal workspace per principal, immutable workspace storage keys, digest-only credentials, and encrypted versioned verifier roots. Storage services cover atomic anonymous-workspace attachment, one-time credential issuance, safe metadata reads, credential lifecycle changes, principal disable/enable, and bounded last-used writes; the existing route and browser flow remains unchanged.
  - **Tests:** SQLite and real Postgres cases cover schema parity, safe serialization, backup and backend migration, stable paths through rotation, storage-key containment, key rewrapping, bounded writes, and rollback after injected attachment failures. A dormant startup guard is ready to reject legacy token-owned schema only after the later coordinated cutover enables it.
- **The v3 authentication design is fixed before the ownership cutover.** The accepted contract defines pseudonymous principals, personal workspaces, access credentials, scoped PATs, request and anonymous contexts, recovery, revocation, durable work, restricted-profile public shares, verifier keys, the clean production cutover, and its threat model. A 2026-09-06 production check found only the known operator and unused test tokens, and the latest backup passed a complete checksum verification.
- **Server-side tests now use the same identity-validation path as production.** Shared fixtures provide canonical anonymous UUIDs, issue durable tokens through the real session storage service, and keep one identity stable across related requests. Literal malformed, unknown, and revoked values remain only where a test deliberately verifies rejection; request-construction-only JavaScript fixtures remain isolated, and Playwright continues to obtain live identities from the running application.
- **Shell-output entities now open a compact action menu for investigation and reuse.**
  - **Before:** Activating an entity opened Atlas immediately, while a separate long-press or right-click menu exposed a larger set of output-only actions. That made it easy to navigate away when the intent was to select or reuse the value.
  - **After:** A deliberate click, tap, or keyboard activation offers **Open in Atlas**, **Copy to Clipboard**, and **Insert into command**. The menu uses the entity's canonical value, respects the desktop or mobile command selection without running anything, preserves normal text selection and native right-click behavior, and closes when its context changes.
  - **Tests:** Vitest covers supported entity types, selection suppression, action wiring, keyboard navigation, viewport placement, clipboard outcomes, and every dismissal path. Playwright exercises live output in source and bundle modes, including mouse, keyboard, Atlas handoff, exact composer insertion, shell typing, and a narrow touch viewport.
- **The development roadmap now defines the v3.0 release scope and delivery gates.** The remaining tracked work covers easier entity reuse, pseudonymous principals and credentials, restricted deployments, and managed sign-in. It keeps ARM64 runner autoscaling independent, requires reviewable changes to land on a working `main`, and puts a production-like restricted-profile soak before OpenID Connect and the `v3.0.0-rc.1` release cycle.

### Fixed

- **JavaScript dependency audits no longer flag vulnerable `colord` or `js-yaml` releases.** The Stylelint toolchain now resolves `colord` 2.10.0 and patched `js-yaml` 4.3.2 without changing the parent tooling versions.
- **WHOIS lookups now save only the queried IP address or domain as an Atlas entity.** Registration ranges, registry and registrar hosts, nameservers, contact handles, RDAP and referral links, and policy URLs remain visible in the transcript without becoming Atlas records or Project targets.
- **Diagnostic audit-route tests no longer expire as the calendar advances.** The test app now recognizes the real migration table instead of rerunning database maintenance for every client, and audit fixtures initialize their database first and use retention-safe timestamps.
- **JavaScript dependency audits no longer flag known `fast-uri` request-parsing vulnerabilities.** The development-only dependency used through the Stylelint toolchain is now locked to version 3.1.7.
- **Container vulnerability scans no longer flag the bundled OpenSSL build.** OpenSSL is updated to the 3.6.4 security patch release with its source archive still protected by a pinned SHA-256 checksum.

---

## [2.9.2] - 2026-08-29

### Changed

- **The desktop and mobile demo tours now reflect the current investigation workflow.** Both recordings cover reusable Workflows, the Project overview, Assessment planning, report preview, and Atlas Quick Lookup alongside the existing command, Files, comparison, monitoring, History, theme, and desktop PTY scenes. The wrappers also accept `--playback-only` to run the complete seeded journey headlessly and catch stale selectors or stalled scenes without requiring OBS.
- **The UI screenshot review pack now covers the current desktop and mobile investigation surfaces.** Its 48 desktop and 41 mobile scenes add the Files inspector and full viewer, parameterized Workflows, Project Overview, monitoring digest settings, Assessment planning, Web Surface, and Atlas Quick Lookup. Filtered History deletion previews now show their real scope and counts, and the capture wrapper uses the normal Playwright helper for both source and bundle runs.

---

## [2.9.1] - 2026-08-26

### Fixed

- **DNS command options and resolvers no longer become Project entities.** `dig` and `nslookup` target discovery now recognizes the actual query and waits for a matching parsed answer before adding it. Record types, output options, selected resolvers, and names from negative lookups stay out of Atlas and Project targets.
