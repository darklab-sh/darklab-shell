# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.8.1
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.8.4] - Unreleased

No changes yet.

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
