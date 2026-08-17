# Project-scoped probes merge request

## Suggested title

Projects: Add bounded one-off probes with reviewed plans

## Summary

- Adds `probe list`, `probe plan`, and `probe run` to the browser terminal, API v1, and `darklab probe` CLI.
- Resolves every probe through one confirmed Project target, previews the exact bounded command, and rechecks the plan digest, scope, permissions, and feature gates before launch.
- Reuses ordinary runs, History, Project links, structured evidence, and Assessment reconciliation without creating a second results or case-management model.
- Supports protected HTTP profiles for the tools that can enforce their saved request boundary. Nuclei remains anonymous because template-generated requests can't reliably stay inside an HTTP profile's scheme, port, root, and path limits.
- Improves terminal ownership and recovery with per-tab confirmation state, same-tab streaming, repeatable run commands in History, Project and HTTP-profile name completion, and target-aware suggestions.
- Prepares an empty managed Nuclei template cache during Compose startup, keeps installed snapshots unchanged until an explicit update, and emits only fixed lifecycle records rather than third-party updater output.

## Review focus

- Confirm catalog actions, policy floors, target compatibility, availability, and command bounds match the maintained Assessment planners.
- Confirm no probe accepts a free-form target outside a confirmed Project link and that stale, suppressed, changed, unlinked, or cross-Project targets fail before the broker.
- Confirm protected values and private Files paths stay out of plans, saved commands, API responses, audit records, metrics, and logs.
- Confirm browser and headless launches share the same preview, digest, permission, Project-link, cleanup, and evidence boundaries.
- Confirm Nuclei plus an HTTP profile returns an unavailable plan before confirmation or materialization, while anonymous safe, standard, and enabled intrusive profiles remain available.
- Confirm the browser keeps the reviewed plan in the originating tab, doesn't duplicate confirmation output, and restores the normal composer and History behavior after launch or failure.

## Validation

The final pre-merge reviews recorded these results before the last documentation and logging-only follow-ups:

- Python: 2,715 passed, 267 skipped.
- Vitest: 1,614 passed.
- Playwright bundle mode: 291 passed, 2 demo-only tests skipped.
- Playwright source mode: 26 passed.
- PostgreSQL: 129 passed.
- Focused probe backend: 111 passed.
- Focused probe browser journeys passed in source and bundle modes.

The final logging follow-up also passes its focused production-install regression, ShellCheck, documentation tests, and Markdown lint. GitLab pipelines provide the final branch-wide qualification. The manual container-smoke lane remains the release-image check for bundled tools, managed Nuclei templates, Files-backed commands, and Linux scanner capabilities.

## Risks and compatibility

- Existing raw commands and Assessment-cycle actions keep their current routes and persistence. Probes add a bounded launcher over shared catalogs and runs rather than replacing either surface.
- A confirmed Project target is mandatory. Auto-discovered targets must be confirmed first, and evidence collection doesn't downgrade that review state.
- Protected Nuclei launches are intentionally incompatible with this release. Operators can run an anonymous reviewed Nuclei profile or choose a profile-aware tool whose adapter enforces the saved boundary.
- The first startup with an empty Nuclei cache can make one bounded outbound template update. Set `NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED=false` when startup must remain offline.
- Intrusive actions remain disabled by default and continue to require the instance setting plus fresh confirmation.

## Documentation

- [Project probes](../../FEATURES.md#project-probes)
- [Configuration](../../CONFIGURATION.md)
- [API and CLI reference](../api.md#project-probes)
- [Architecture](../../ARCHITECTURE.md)
- [Decisions](../../DECISIONS.md)
- [Testing](../../tests/README.md)
