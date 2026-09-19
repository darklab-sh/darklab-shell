# Agent Guide

This file contains repository-wide guidance for coding agents working on darklab_shell. Use it with the task's instructions and the detailed guides below. Keep it focused on durable working rules; feature inventories and implementation plans belong in their existing documents.

## Working on a Task

- Check the current branch, working-tree changes, and relevant code before editing. Preserve unrelated work, including changes made by the user or another agent.
- For an implementation request, finish the agreed behavior, appropriate regression coverage, logging, generated outputs, and relevant documentation. For a review or planning request, keep the work within that scope.
- Start with the supplied failure, artifact, or requirement and trace the actual caller, helper, and runtime boundary. Verify assumptions against current code; TODO items and historical changelog entries aren't evidence that a feature exists today.
- Follow nearby naming and formatting conventions. Prefer existing services and helpers, small cohesive changes, and explicit failure handling. Avoid speculative abstractions and unrelated cleanup.
- Use the OpenAI developer documentation MCP server when working with the OpenAI API, ChatGPT Apps SDK, Codex, or related OpenAI tooling, without waiting for the user to request it. If it's unavailable, say so and use official documentation as the fallback.
- At handoff, explain the outcome, validation performed, and remaining limitations. Distinguish local checks from CI results, deployment, and publication.

## Where to Read First

Read the guides that govern the affected behavior before changing it. The [README Documentation Map](README.md#documentation-map) indexes the maintained project documentation.

| Work | Canonical guidance |
| --- | --- |
| Setup, branches, checks, and merge requests | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Runtime boundaries, ownership, persistence, and security | [ARCHITECTURE.md](ARCHITECTURE.md); [DECISIONS.md](DECISIONS.md) for rationale |
| Browser composition and shared UI | [Front End Design](ARCHITECTURE.md#front-end-design), [THEME.md](THEME.md), and similar existing components |
| Configuration, supported runtimes, and operations | [CONFIGURATION.md](CONFIGURATION.md) |
| Tests, fixtures, and failure artifacts | [tests/README.md](tests/README.md); [UI capture scenes](tests/ui-capture-scenes.md) for visual review |
| Logging, audit context, and redaction | [docs/logging.md](docs/logging.md); [AI privacy](docs/ai-privacy.md) when assists are affected |
| Commands, scanner integration, and Files flags | [External command integrations](docs/external-command-integrations.md); [Bundled tools](docs/tools.md) for user-facing behavior |
| Public API and CLI | [docs/api.md](docs/api.md) and the Python OpenAPI source |
| Automation and notifications | [Workflows](docs/workflows.md), [Schedules](docs/schedules.md), [Watchers](docs/watchers.md), and [Notifications](docs/notifications.md) |
| Storage and data cutover | [Postgres migration](docs/postgres-migration.md) and [Storage scaling](docs/storage-scaling.md) |
| Documentation and planned work | [DOC_STANDARDS.md](DOC_STANDARDS.md), [FEATURES.md](FEATURES.md), [CHANGELOG.md](CHANGELOG.md), and [TODO.md](TODO.md) |

## Backend and Data Contracts

- Keep Flask routes thin. Services own queries, transactions, and lifecycle behavior; don't add SQL or direct persistence calls to blueprints. Respect caller-owned transactions and emit success only after the relevant commit succeeds.
- Keep startup work in the established runtime-bootstrap path. Preserve the separation between Flask construction, process initialization, and standalone workers; don't introduce import-time startup work into reusable modules.
- Use the shared runtime accessors: `config.resolve_effective_cfg(cfg=None)`, `core.database_access.get_db_backend()` / `get_db_connect()`, and `core.process.RedisClientProxy`. Don't add local singleton bindings for `CFG`, database functions/backend state, or Redis clients. Use typed attribute access for known config fields and `build_test_config(...)` in tests that need overrides.
- Use `services.teams.ownership_queries` for owner-scoped SQL. Personal workspaces own data; principals and credentials establish authority and attribution. State each table's owner key and personal/team representation explicitly. Query refactors must preserve the existing result set unless the task intentionally changes it.
- When ownership SQL changes, follow the inventory and review checks in CONTRIBUTING. Preserve route-contract, singleton-binding, and module-size gates. Update an inventory deliberately for an intentional contract change; don't raise a budget or widen an allowlist just to silence a failure.
- Add schema changes as new numbered, registered migrations through the shared dialect layer. Keep the frozen baseline unchanged and qualify changes on both SQLite and Postgres, including upgrade behavior where applicable.
- Preserve configuration precedence: built-in defaults → shipped `config.yaml` → `config.local.yaml` → supported environment overrides. Use the existing shipped/local path helpers, normalization, and validation. Keep browser configuration limited to fields the browser needs; the effective server config isn't a public payload.
- Configuration changes must account for all consumers, including entrypoint setup and workers. Document the actual reload/restart behavior: production stages local overlays at startup, and a fresh CLI process doesn't prove what an existing web worker has loaded.
- Keep API v1 changes additive within its compatibility contract. Update the Python spec in `app/services/api_v1/openapi.py`, regenerate `docs/api-v1-openapi.json` with `python scripts/generate_api_openapi.py`, and keep CLI behavior and examples aligned.

## Security, Execution, and Privacy

- Enforce authorization on the server. Preserve the distinction between anonymous identity, portable credentials, browser sessions, and scoped PATs. Invalid or revoked credentials must fail closed rather than becoming anonymous access. Team headers and UI visibility aren't authorization.
- Recheck current ownership and capabilities at the existing launch, background-work, stream, and export boundaries. Scope changes must not move work already accepted under another owner.
- Keep command policy, target restrictions, workspace containment, symlink/traversal checks, secret injection, and the separate unprivileged scanner process intact. Adapt external commands through the registry and shared preparation path; keep rewrites idempotent and preserve the user's visible command where the contract allows it.
- Preserve explicit preview/confirmation boundaries. Reading a plan or stored evidence must not launch work, allocate external resources, refresh a provider, or widen approved scope. Launch must revalidate the reviewed plan against current state.
- Keep secrets out of command arguments, shell history, public responses, browser storage where prohibited, logs, metrics, and committed fixtures. Use the existing vault and protected input/output paths. Treat scanner output, imported reports, and AI responses as untrusted data.
- AI output stays separate from original transcripts and evidence. Preserve redaction, owner scope, provider policy, and normal command validation before any suggested command can run.
- Use disposable databases and test-owned targets for validation. Never point destructive test helpers at production data or write a container's live SQLite database with host SQLite tooling. Backup and restore work must preserve the database, matching encryption key, Files, and operator configuration together.

## Frontend and Generated Assets

- Read **Front End Design** in ARCHITECTURE and inspect comparable UI before adding a component. Reuse shared pressable, button, tab, dropdown, row, badge, chip, form, drawer, sheet, and scrollbar primitives.
- Use `bindPressable`, `bindDisclosure`, `showConfirm`, `bindFocusTrap`, and the shared dismissal/mobile-sheet helpers where their contracts apply. Preserve keyboard activation, accessible names, cancel focus, focus restoration, touch targets, and narrow-screen behavior.
- Follow THEME's semantic colors and existing tokens. Keep live pages, standalone pages, and exports consistent; don't introduce an independent palette or one-off semantic colors.
- Keep browser code in focused ES modules with explicit imports and established state boundaries. Avoid new legacy globals, duplicated state, and oversized controllers. Background refreshes must preserve active edits, focus, selection, and scroll position, and ignore stale responses.
- Edit source assets, then run `npm run assets:sync` and review the tracked generated output. Complete generation before starting Playwright. Use `npm run assets:check` and `npm run assets:inventory:check` for the corresponding contracts; don't hand-edit generated bundles.
- For vendor or theme-default changes, use `npm run vendor:sync` or `python scripts/generate_theme_examples.py` as appropriate. Keep dependency pins, generated references, and third-party notices aligned with the source change.

## Tests and Validation

Choose the cheapest layer that can meaningfully catch the regression: pytest for backend contracts, Vitest for browser-module logic, and Playwright for real browser behavior. Use more than one layer when the change crosses boundaries. Documentation-only work generally needs documentation checks and Markdown lint, not new application tests.

Run commands from the repository root. Prefer the repository virtual environment and installed dependencies. These are focused examples; use the affected suites described in the testing guide.

| Check | Command |
| --- | --- |
| Backend example | `bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. tests/py/test_routes.py -q` |
| Documentation contracts | `bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. tests/py/test_docs.py -q` |
| Browser unit tests | `npm run test:unit -- tests/js/unit/<file>.test.js` |
| Source-mode browser tests | `bash scripts/run_playwright.sh --asset-bundle-mode source tests/js/e2e/<file>.spec.js` |
| Bundle-mode browser tests | `bash scripts/run_playwright.sh --asset-bundle-mode bundle tests/js/e2e/<file>.spec.js` |
| Disposable Postgres tests | `bash scripts/run_postgres_tests.sh -- <pytest arguments>` |
| Markdown lint | `npm run lint:md` |
| Whitespace errors | `git diff --check` |

- Always use `bash scripts/run_playwright.sh ...` for ordinary E2E execution. Prefer its `--asset-bundle-mode source|bundle` flag over environment-variable prefixes. Use the documented Postgres browser and capture wrappers for those specialized lanes; direct Playwright listing is fine for inventory only.
- Use the Postgres helper's disposable instance or documented explicit test-target modes; don't assume a database at `localhost:5432`. Keep pytest's documented serial fast/release partitions; don't introduce parallel execution without qualifying fixture isolation.
- Use shared identity fixtures and production services for authenticated backend tests. Use pristine SQLite copies for ordinary empty-current-schema cases, but real initialization for migration, startup, rollback, and schema-reconciliation tests.
- Cover meaningful outcomes, denial/failure paths, and ownership isolation. Keep tests independent and deterministic. Use controllable responses and readiness conditions for browser timing; don't paper over a regression with sleeps, retries, skipped assertions, or broad timeout increases.
- For access-profile changes, follow the documented desktop/mobile, source/bundle, SQLite/Postgres qualification matrix. For Dockerfile, packaged-tool, command-example, or workspace-flag changes, run the relevant deterministic container smoke coverage and build a fresh smoke image when required.
- Investigate E2E failures from the supplied `error-context.md`, traces, screenshots, and isolated server logs first. Preserve failed-attempt evidence. A passing retry is still a flaky result; keep CI's flaky-test and focused-test guards enabled.
- Run relevant lint and architecture checks in addition to behavior tests. These checks may run locally or in CI under the authorized workflow below. Before a merge or release, complete the broader checks required by CONTRIBUTING. Report the checks actually run and any blocked or outstanding checks.

## Logging and Review

- Follow the `shell` logger and structured event conventions in [docs/logging.md](docs/logging.md). Use DEBUG for bounded diagnostic detail, INFO for meaningful completed lifecycle changes, WARNING for rejected or degraded conditions, ERROR for failed operations, and CRITICAL for startup safety failures.
- Include useful safe context, such as permitted correlation ids, fixed reasons, counts, and timings. Keep field types stable: numeric `http_status`, descriptive string fields such as `job_status`. Bound metric labels and repeated warnings.
- Apply each event's redaction and traceback contract. Don't dump config, request bodies, command text, provider payloads, or exception messages merely to improve diagnostics. Preserve transaction-aware audit behavior and update the event reference when its contract changes.
- Reviews should prioritize correctness, security, data isolation, error handling, and concurrency before style. Check whether tests prove the behavior and docs describe it accurately. Give actionable findings with file references and impact, separating blockers from suggestions.

## Documentation and TODOs

- Follow [DOC_STANDARDS.md](DOC_STANDARDS.md). Write plain, human prose, use contractions naturally, and explain features from the reader's perspective. README and FEATURES describe what people can do; implementation detail belongs in contributor references.
- Update the relevant parts of README, FEATURES, ARCHITECTURE, CONFIGURATION, CONTRIBUTING, CONTRIBUTORS, DECISIONS, tests/README, THEME, and focused guides. Check relevance rather than adding filler to every file. Keep a single canonical home for a contract and link to it.
- TODO is the home for future work and implementation plans. Other maintained docs describe the current behavior definitively, without MVP, phase, or first-pass framing. Historical rationale belongs in DECISIONS and published history in the changelog.
- When completing a TODO, remove the completed item and record the implemented outcome in the active CHANGELOG section using its existing style. Record meaningful product, operations, security, compatibility, and contributor changes; backlog-only edits don't need a changelog entry.
- Preserve published changelog text and archives. Historical corrections and release finalization follow the documented review and integrity checks; don't rewrite released entries during routine work.
- Keep testing guidance and live inventory commands current. Don't hardcode exact test totals or recreate an exhaustive test appendix; current DOC_STANDARDS and `tests/py/test_docs.py` enforce that policy.
- Add new maintained Markdown documents to README's Documentation Map. Use repository-relative links, preserve useful anchors, and check links and tables of contents. Never link shared docs to a contributor's private filesystem.
- If local merge-request or release drafts exist under `docs/release-drafts/`, keep them aligned with the final change. They are transient: don't reference them from permanent project docs or include them in shipped release documentation.
- Preserve project SPDX headers and third-party attribution. Follow the existing license and generated-notice checks when adding source, assets, dependencies, or bundled data.

## Commits, CI, and Release Work

- Commit, push, open or update merge requests, and publish only within the user's authorized task. Implementation assignments using the user's explicitly configured `todo` workflow authorize per-slice commits and pushes unless the user or coordinating agent narrows the assignment, such as to local edits only. Review or planning requests alone don't authorize that workflow; merging, release publication, and force-pushing require explicit authorization.
- In the authorized `todo` workflow, use CI for broad test, lint, and audit coverage. Run quick local syntax and whitespace checks, plus focused checks when they help implementation or diagnosis. Complete required asset generation before committing, and keep CI jobs and assertions intact.
- For that workflow, inspect the effective Git hook configuration and temporarily comment out the executable body of the repository-local pre-commit hook, normally `scripts/hooks/pre-commit`. Preserve its shebang and permissions and save its original contents outside the repository. Keep the bypass confined to this checkout; never stage, commit, or push the temporary hook changes.
- Restore the saved hook contents and permissions when finishing, pausing, or returning control, including after an error. Preserve hook edits that predate the task rather than replacing them with the HEAD version. Disclose the bypass and confirm restoration at handoff, or report any restoration failure.
- Use cohesive slices, concise commit subjects, explicit staging, and a review of the staged diff before each commit. When agents share a checkout, one agent owns Git and hook operations at a time. Keep machine-specific paths, host aliases, credentials, and command-approval rules out of shared instructions; those rules alone don't authorize Git actions.
- After each push and before starting another slice, use `glab` to inspect pipelines for the pushed revision, including both branch and merge-request pipelines and any corresponding merged-results pipeline. Fix completed failures caused by the change before starting another feature slice. Pending or running pipelines don't block useful work on the next slice; check their results at subsequent slice boundaries.
- After the final slice, monitor the latest revision's required pipelines through completion and fix attributable failures. If CI is unavailable, blocked, missing, or still running when the user ends the task, report the outstanding status without claiming full validation. Distinguish unrelated or infrastructure failures from failures caused by the change.
- Use the repository's [merge-request template](.gitlab/merge_request_templates/Default.md) when writing an authorized merge request. Describe the final diff, validation, risks, and documentation; include relevant pipeline links and outcomes in the task handoff.
- Follow CONTRIBUTING's release checklist for release work. Keep production installation and source-development Compose workflows distinct, preserve immutable release artifacts, and never treat a successful local build as proof of deployment or publication.
