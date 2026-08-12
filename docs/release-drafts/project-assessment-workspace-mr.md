# Project Assessment Workspace merge request

## Summary

- Adds a complete Project Assessment workspace with maintained Network, Web, API, TLS, and Combined cycles.
- Turns saved runs, findings, entities, artifacts, screenshots, and manual decisions into truthful check coverage without treating a Project link as proof.
- Adds guarded recommended actions, reusable HTTP profiles, a grouped retest queue, cross-cycle finding changes, fix-first prioritization, and complete report and evidence-package handoff.
- Adds optional ZAP and private OAST worker paths while keeping remote scanners, credentials, callbacks, and protected request material outside public responses and saved commands.
- Adds the same owner-scoped Assessment lifecycle to desktop, mobile, API, and CLI clients, including Postgres parity and a real browser qualification journey.

The workspace closes the gap between collecting evidence and explaining what was tested, what still needs review, and what should happen next. Completed and archived cycles keep frozen scope and evidence context so later catalog changes don't rewrite historical work.

## Validation

- `bash scripts/run_pytest.sh tests/py`
- `npm run test:js`
- `bash scripts/run_postgres_tests.sh`
- `bash scripts/run_playwright.sh --asset-bundle-mode source tests/js/e2e/assessment.spec.js`
- `bash scripts/run_playwright.sh --asset-bundle-mode bundle tests/js/e2e/assessment.spec.js`
- `bash scripts/container_smoke_test.sh`
- `npm run assets:check`
- `npm run assets:inventory:check`
- `bash scripts/run_pytest.sh tests/py/test_docs.py -q`

The connector suites use local fakes and don't contact a scanner, callback provider, advisory service, or assessment target. The full container lane remains the release-image qualification gate for bundled command behavior and Files-backed adapters.

## Risks

- The schema and read model add high-volume Assessment, evidence, risk, connector, and reconciliation tables. Bounded pagination, quotas, indexed query-plan checks, and SQLite/Postgres parity reduce that risk.
- Protected HTTP, schema, ZAP, and OAST material crosses process-private execution paths. Digest confirmation, launch-time permission and scope checks, no-follow files, fixed cleanup, and redaction tests protect those boundaries.
- ZAP and private OAST depend on operator-managed services and network policy. They remain disabled until configured, run in separate Compose profiles, and preserve durable retry or recovery state when a worker or provider is unavailable.
- Risk feeds and advisory stores can be large or slow. Acquisition is opt-in where it makes an outbound request, accepts data only after complete validation, and doesn't hold SQLite's writer lock during a download.

## Docs

- [User overview](../../README.md#features)
- [Project Workspace feature reference](../../FEATURES.md#project-workspaces)
- [Assessment profiles](../../CONFIGURATION.md#assessment-profile-catalog)
- [ZAP and OAST worker setup](../../CONFIGURATION.md#running-zap-and-oast-workers)
- [Headless Assessment API](../api.md#project-assessments)
- [Assessment architecture](../../ARCHITECTURE.md#assessment-profile-catalog)
- [Assessment decisions](../../DECISIONS.md#assessment-decisions)
- [Assessment log events](../logging.md#log-event-inventory)
- [Browser and container test guide](../../tests/README.md#playwright)
