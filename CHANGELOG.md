# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.8.0
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.8.3] - Unreleased

No changes yet.

---

## [2.8.2] - 2026-07-28

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
