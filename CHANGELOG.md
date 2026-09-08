# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.9.0
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [3.0.0] - Unreleased

### Changed

- **Legacy owner-scoped SQL now has a checked query-adapter boundary ahead of the principal cutover.**
  - **Before:** Personal-only, team-capable, token-keyed, composite-key, and actor-attribution queries built their owner predicates independently, so a seemingly mechanical helper conversion could change which `NULL` or empty-team rows were returned.
  - **After:** Shared adapters keep the current session identity as the personal owner while requiring each caller to state its table shape and personal team-row representation. A checked inventory records all 460 current ownership SQL sites, their tables, operations, key and team-column shapes, present result sets, planned subsystem branch, and later principal-era replacement; migration and principal-foundation SQL are named exceptions while the remaining Phase 3A sites are converted.
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
