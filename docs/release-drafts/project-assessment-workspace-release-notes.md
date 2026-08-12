# Project Assessment Workspace release notes

Projects now include an Assessment workspace that keeps scope, checks, evidence, findings, and retests together from the first review through the final handoff.

## What assessors can do

- Start a maintained Network, Web, API, TLS, or Combined cycle. Each cycle freezes the profile and Project targets it started with, so its history stays understandable after the live catalog changes.
- See honest covered, awaiting-review, untested, excluded, and unavailable-evidence totals. A saved run counts only when it matches the check's target, tool, outcome, version, and evidence rules.
- Preview and start reviewed actions without leaving the Project. Safe, standard, and enabled intrusive actions show their exact target, scope, limits, and credential use before confirmation; destructive actions aren't available.
- Save reusable HTTP roles that refer to darklab_shell Secrets and Files without copying credential values into the profile or visible command.
- Create findings from checks or saved output, attach typed supporting evidence, compare compatible retest runs, and keep the final verification decision with a person.
- Work from a grouped retest queue when several findings share the same safe, credential-free plan. Mismatched scope, action, or HTTP context stays separate with an explanation.
- Compare completed cycles and distinguish new, persistent, no-longer-observed, regressed, and incomparable issues without turning missing evidence into a clean result.
- Choose an earlier or archived Assessment when building an evidence package or report. Exports keep the frozen scope, coverage, exclusions, evidence references, priorities, changes, and warnings about unavailable sources.

Desktop and mobile use the same saved state and permissions. Team viewers can review work without changing it, while authorized members can manage cycles, evidence, findings, profiles, and runs. The headless API and `darklab assessment` CLI expose the same core lifecycle for automation.

## Optional integrations

Operators can connect an external ZAP service for reviewed safe or separately enabled intrusive web scans. The app shows the exact non-secret plan, keeps progress across reloads, supports cancellation, saves the report through Files, and waits for an assessor to review and apply the Atlas import.

A private Interactsh-compatible service can support the maintained blind-XSS check. Callback reservations are short-lived and recoverable, while provider credentials, callback addresses, and raw interactions stay outside public commands, browser storage, logs, and exported records.

Both integrations are off by default and run through separate production Compose profiles. Setup and recovery steps are in [Configuration](../../CONFIGURATION.md#running-zap-and-oast-workers).

## Risk and advisory context

Saved CVEs can use dated, release-pinned EPSS and CISA KEV data without making an outbound request. Operators can separately enable live feed refresh, local NVD or OSV data, or exact one-package OSV lookups. Risk changes appear in Project Monitoring and help order the fix-first list, but they never make an untested Assessment check look complete.

## Learn more

- [Project Workspace features](../../FEATURES.md#project-workspaces)
- [Assessment API](../api.md#project-assessments)
- [Assessment profiles and custom catalogs](../../CONFIGURATION.md#assessment-profile-catalog)
- [Logging and troubleshooting](../logging.md#troubleshooting)
