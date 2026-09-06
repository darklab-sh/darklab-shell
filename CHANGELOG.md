# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.9.0
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.9.3] - Unreleased

### Fixed

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
