# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Build a project assessment workspace for recon and vulnerability validation](#build-a-project-assessment-workspace-for-recon-and-vulnerability-validation)
  - [Autoscale ARM64 release runners on EC2 Spot](#autoscale-arm64-release-runners-on-ec2-spot)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
  - [Retire the local Nuclei kin-openapi compatibility patch](#retire-the-local-nuclei-kin-openapi-compatibility-patch)
- [Feature Enhancements](#feature-enhancements)
- [Research](#research)
- [Ideas](#ideas)
  - [Run replay / scrubbable event stream](#run-replay--scrubbable-event-stream)
  - [Run comparison enhancements — deferred pieces](#run-comparison-enhancements--deferred-pieces)
  - [Bulk history export and share](#bulk-history-export-and-share)
  - [Mobile share ergonomics](#mobile-share-ergonomics)
  - [PWA install and service-worker push](#pwa-install-and-service-worker-push)
  - [Engagement report builder](#engagement-report-builder)
  - [Native ticketing integrations](#native-ticketing-integrations)
  - [Operator-extensible signal and parser rules](#operator-extensible-signal-and-parser-rules)
- [Architecture](#architecture)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

### Build a project assessment workspace for recon and vulnerability validation

Turn the existing Projects, Atlas, Findings, Workflows, Files, and reporting features into a methodical vulnerability-assessment flow. Keep the terminal as the execution surface and the Project workspace as the engagement surface, but make it clear what was tested, which evidence supports that coverage, what still needs work, and which findings need validation or retesting. Add focused tools where they close a real assessment gap instead of growing the image with overlapping scanners.

#### Scope and product boundaries

- [ ] Freeze the product contract before adding schema or routes:
  - Add an **Assessment** tab to the existing Project workspace rather than introducing another top-level overlay, modal, or independent case-management model.
  - Allow a Project to hold multiple dated assessment cycles, with one active cycle and completed cycles kept as read-only historical context. Starting a new cycle must not rewrite the evidence or coverage state of an earlier cycle.
  - Ship maintained Network, Web, API, TLS, and Combined assessment profiles. Each profile must snapshot its version and checks into an assessment cycle so a later catalog update does not silently change an assessment already in progress.
  - Reuse Project targets, Atlas entities and relationships, saved runs, findings, artifacts, workflow executions, evidence packages, and reports as the source records. Assessment records add planning and provenance; they do not copy transcripts, Intel responses, or finding bodies.
  - Keep assessment states factual. A completed command can prove that a check ran, but an empty result must be labeled **covered with no app-captured findings**, never **secure**, **passed**, or another claim the app cannot prove.
  - Use `not_started`, `running`, `covered`, `needs_review`, `blocked`, `failed`, `skipped`, and `not_applicable` as the check states. Store the reason and actor for manual `blocked`, `skipped`, and `not_applicable` decisions.
  - Treat safe, standard, intrusive, and destructive as explicit execution-policy levels. Shipped profiles may recommend safe or standard checks; intrusive checks require a separate confirmation and operator opt-in; destructive checks are never launched by an assessment action.
  - Viewing an assessment, target, entity, finding, or recommendation must remain read-only. It must not run a command, refresh Intel, contact a provider, create an entity, or change coverage until the user explicitly acts.
  - Preserve the current owner boundary: personal assessments stay personal, team assessments stay in their team, archived teams remain readable but cannot be changed, and moving between scopes never exposes another owner's targets, evidence, HTTP context, or assessment status.
  - Reuse `MUTATE_PROJECTS` for assessment-cycle and check mutations, `RUN_COMMANDS` for launches, `TRIAGE_FINDINGS` for manual finding and verification changes, `MANAGE_SECRETS` for protected HTTP context, and `VIEW_TEAM` for team reads. Do not create a parallel permission system unless these capabilities prove unable to express a concrete action.
  - Keep Metasploit, general exploitation, password spraying, credential brute force, denial-of-service checks, and automatic database/file takeover outside this work. Do not bundle ZAP, Greenbone, or an OAST server into the primary application image.
  - Do not add WhatWeb or Arjun in this item while HTTPx technology detection and the planned parameter-testing flow cover the same jobs. Reconsider another scanner only after a measured gap shows what the current tools miss.

#### Open decisions before implementation

Resolve these choices and record the accepted contracts in `DECISIONS.md` before the first assessment-workspace schema migration or production route lands. Once decided, update the relevant phase below so the implementation plan describes one contract rather than carrying alternatives into code review.
- [ ] **Choose assessment-profile customization and versioning semantics.**
  - **Recommended decision:** Treat shipped profiles as immutable versioned definitions. Let local configuration add a new profile or replace an entire profile version by stable key, but do not partially merge individual checks. Require an explicit version change whenever applicability, evidence rules, policy, or recommended actions change.
  - **Why:** Full versioned replacements are easier to validate and reproduce than field-by-field overlays, and cycle snapshots remain meaningful when operators customize the catalog.
- [ ] **Choose the assessment-cycle lifecycle and deletion contract.**
  - **Recommended decision:** Use `active`, `completed`, and `archived` cycle states. Creation makes a cycle active; completion freezes its profile, scope, checks, manual exclusions, and evidence links; archiving changes visibility only; and restart always creates a new cycle. Allow hard deletion only for archived cycles after a dependency preview, without deleting linked source runs, findings, entities, or artifacts.
  - **Why:** A small lifecycle prevents ambiguous draft/reopened behavior and keeps historical evidence stable while still allowing deliberate cleanup.
- [ ] **Choose how target identity and historical target values are snapshotted.**
  - **Recommended decision:** Identify each assessment target with its owner scope, Project target/entity reference, canonical type, canonical-value hash, and a bounded display-value snapshot already visible in that Project. Preserve that snapshot in completed cycles, but never copy HTTP credentials, secret-backed headers, cookies, workflow variables, or unrelated discovered values into the assessment record.
  - **Why:** Historical reports need to say what was tested even if the live Project target later changes, but assessment snapshots must not become a second secret or discovery-data store.
- [ ] **Choose the evidence-compatibility and negative-evidence contract before fixing the schema.**
  - **Recommended decision:** Require every profile check to declare accepted evidence kinds, scanner/action families, target matching, completion requirements, compatible tool/profile versions, and whether it has a defined negative-evidence rule. Store the matched rule/version on each assessment evidence link; do not infer coverage or absence from a generic Project link or command prefix.
  - **Why:** These fields determine whether coverage, cross-cycle comparison, and `not_observed` are trustworthy and therefore need to be part of the first durable contract.
- [ ] **Choose the stable finding identity used for deduplication and cycle reconciliation.**
  - **Recommended decision:** Give every observation a fingerprint built from owner scope, canonical affected component/service/endpoint, stable check/rule identity, normalized vulnerability identity, and validation method. Link active confirmation, version inference, import assertion, and manual assessment as related observations rather than collapsing their provenance. Separately derive a remediation identity from the same owner, affected subject, and normalized vulnerability or rule identity while excluding validation method. Keep review/remediation disposition on the remediation group and method/confidence/verification on each observation. Count each remediation identity once in fix-first worklists and headline rollups, expose its observation/evidence count, and expand the individual methods only in detail views. Require an explicit human merge when affected subjects or vulnerability identities do not match exactly.
  - **Why:** Observation-level identity preserves the difference between inferred and demonstrated vulnerabilities, while remediation-level counting prevents one real issue from inflating the ranked list merely because several tools or methods observed it.
- [ ] **Choose the exact execution-policy behavior for safe, standard, intrusive, and destructive actions.**
  - **Recommended decision:** Let safe actions use the normal launch confirmation; require standard actions to show target, fan-out, request, time, and credential bounds; require intrusive actions to be enabled by the operator and confirmed for every launch; and keep destructive actions unavailable from assessment recommendations, workflows, API, and CLI.
  - **Why:** Policy labels need observable behavior across every launch surface, not just descriptive metadata in a profile.
- [ ] **Choose the protected HTTP-context injection order.**
  - **Recommended decision:** Give each tool a reviewed adapter that prefers stdin or a tool-native credential channel, then a private `0700` per-run directory with `0600` short-lived files, and uses environment injection only when the tool offers no safer supported mechanism. Never render secret material into an argument list, persisted command, workflow state, or reusable scanner config.
  - **Why:** One explicit adapter contract prevents individual integrations from choosing convenient but inspectable credential handling.
- [ ] **Choose quota, retention, and cleanup defaults from measured workloads.**
  - **Recommended decision:** Set configurable hard limits for cycles, checks, evidence links, screenshots, imports, callbacks, and fan-out work after benchmarking the maintained profiles on small, medium, and large Projects. Reject new work clearly at the limit instead of evicting assessment history; retain completed cycles until explicit deletion, while expiring rebuildable feed caches, acknowledged escalation events, temporary HTTP material, and connector callbacks under documented policies.
  - **Why:** Arbitrary limits risk making real assessments unusable, while automatic history eviction would undermine evidence and reporting guarantees.
- [ ] **Choose the primary-image tool budget and optional-pack boundary.**
  - **Recommended decision:** Measure and approve a compressed-image and cold-start budget before adding tools. Keep small, pinned, multi-architecture discovery/validation tools needed by maintained profiles in the primary image; keep protocol client packs and ZAP, Greenbone, OAST, or other service stacks optional and operator-managed. Do not add a tool that exceeds the budget without a separate packaging decision.
  - **Why:** The feature should close assessment gaps without making every installation carry large or overlapping scanners it does not use.
- [ ] **Choose when optional connectors become release blockers.**
  - **Recommended decision:** Treat ZAP, private OAST, and Greenbone integration as follow-on deliverables after assessment cycles, evidence matching, manual findings, imports, and reporting are stable. Keep their contracts in this plan, but do not block the core assessment workspace on an external service deployment.
  - **Why:** The core workflow is useful with local tools and imports, while connector lifecycle, privacy, and failure handling can be qualified independently.

#### Phase 1 — Define the assessment and evidence data contracts

- [ ] Add the next available shared SQLite/Postgres migration after the Phase 0 risk-intelligence migration and register it in `app/core/migrations/__init__.py`:
  - Add `project_assessments` for cycle identity, owner scope, Project, title, profile key/version, status, start/completion timestamps, created/updated actor context, and a bounded immutable profile snapshot.
  - Add `project_assessment_checks` for category, stable check key, target/entity reference, target type/value snapshot, applicability, policy level, state, state reason, recommended workflow/action key, and first/last evidence timestamps.
  - Add `project_assessment_evidence` as a typed link from a check to a run, workflow execution, finding, Atlas entity, run artifact, workspace artifact, or stored screenshot. Reject unsupported types and duplicate links instead of storing unvalidated free-form references.
  - Keep source records authoritative. A deleted or cleaned run may make evidence unavailable, but the check must retain a bounded tombstone with the original evidence type/id, observed time, and unavailable reason so historical coverage does not disappear without explanation.
  - Add owner/project/status/check/evidence indexes required for bounded list and rollup queries on both backends. Extend schema-manifest and migration parity coverage so a missing table or index is reported as drift.
  - Add configurable per-owner/per-project quotas for assessment cycles, checks, and evidence links. Enforce quotas inside the same transaction as inserts and return the existing Project quota error shape.
  - Include assessment records in session-token migration, Project deletion, team archive/read-only behavior, retention cleanup, backup/restore validation, and unified-baseline reconciliation. Do not migrate active team-owned assessments into a personal owner.
- [ ] Implement the domain package under `app/services/assessments/` rather than adding persistence to API helpers or growing `services/projects/overview.py`:
  - Separate profile loading/validation, storage, coverage derivation, evidence matching, recommendations, serialization, cleanup, and permission-neutral contracts into focused modules.
  - Build one scope-aware read model used by the Project browser routes, API v1, evidence packages, and reports. Do not maintain separate browser and API coverage calculations.
  - Derive automatic coverage only from explicit compatible evidence rules such as scanner family, command root, structured output kind, target match, workflow action, and run completion state. A linked run alone is not enough to satisfy an unrelated check.
  - Keep manual state changes separate from derived evidence. New evidence may move `not_started`, `running`, or `failed` into `covered`/`needs_review`, but must not overwrite a deliberate `blocked`, `skipped`, or `not_applicable` decision without confirmation.
  - Recalculate affected checks incrementally when a run finalizes, a workflow step completes, an import is applied, a finding changes, or evidence is deleted. Avoid rescanning every run in an owner or Project on normal reads.
  - Give every rollup both counts and denominators: applicable checks, covered checks, checks awaiting review, untested checks, excluded checks, and unavailable evidence. Never mix `not_applicable` into the completion denominator.

#### Phase 2 — Add assessment routes, API contracts, audit, and observability

- [ ] Finish the assessment-specific audit and safe-log inventory as later features land:
  - HTTP-profile launches now use the shared audit boundary and record only the profile id, role, credential-use categories, and action metadata. Recommended-action launch, cycle lifecycle, manual-state, evidence-link, manual-finding, and retest-disposition events use the same boundary.
  - Log ids, owner kind, Project id, profile/check keys, policy level, state transitions, counts, durations, and error classes. Never log credentials, authorization headers, cookies, client-certificate contents, raw request bodies, provider payloads, finding evidence bodies, or complete target lists.
  - Add low-cardinality metrics for active cycles, check-state transitions, derived-evidence matches, action launches/failures, parser results, and connector job outcomes. Do not use target values, Project ids, commands, CVEs, or workflow ids as metric labels.
  - Apply existing request/rate-limit conventions to mutation and launch routes. Bound recalculation work and emit a clear warning when a safety or quota limit rejects work.
- [ ] Update architecture guards as the remaining routes and modules land:
  - Classify every new decomposed `projects*` or `api_v1*` blueprint and any new required module-family member in the module-size ratchet.
  - Intentionally update the decomposed route count/digest after reviewing method/path ownership.
  - Keep `services/api_v1` limited to auth, serialization, and OpenAPI helpers; assessment persistence stays in its domain service.

#### Phase 5 — Add reusable, secret-backed HTTP assessment profiles

- [x] Add the protected execution foundation and reviewed Curl, HTTPx, Katana, and Nuclei adapters rather than rendering raw credentials into visible commands:
  - Revalidate target scope, team membership, capability, secret availability, Files ownership, and profile enabled state immediately before every run.
  - Generate short-lived scanner-readable config/request material inside a private run directory or use safe environment injection where the tool supports it; delete temporary material after launch/finalization and recovery cleanup.
  - Show a redacted display command in the terminal, History, Run Details, workflow execution state, audit, metrics, notifications, and errors. Apply the existing secret masking pass to tool output as a second line of defense.
  - Never allow a profile to broaden a Project target into an unrelated hostname through redirects, schema servers, callback URLs, or proxy behavior without a visible allowlist decision.
- [x] Add a protected Dalfox parameter-discovery adapter with one-target bounds, no redirects, no remote dictionaries, no active XSS payloads, and private header material.
- [x] Extend protected execution to SQLmap where it has a safe, testable contract. SQLmap is URL-scoped and detection-only; extraction, takeover, fan-out, redirects, and unsupported profile features fail closed. ZAP remains pending until its operator-managed contract is separately reviewed.

#### Phase 6 — Close the web and API discovery/validation gaps

- [ ] Add focused parameter and application testing tools:
  - Prefer version-pinned multi-arch binaries or isolated Python environments that keep the runtime dependency graph reproducible. Update licenses, hashes, SBOM/provenance, image-size budgets, and container smoke checks for every addition.
  - Add structured parsers/adapters under focused modules rather than more broad regexes in `output_signals.py`. Preserve raw output, normalize stable findings/entities, carry tool/profile versions, and make parser failure visible without failing the underlying run.
#### Phase 7 — Add service-aware enumeration and safe next actions

- [ ] Add a central service-to-action registry under the assessment domain:
  - Map normalized port/service evidence to applicable checks and maintained workflows for HTTP(S), SMB, SNMP, LDAP, NFS/RPC, SSH, SMTP/IMAP/POP3, FTP, DNS, and common databases.
  - Give each action a label, rationale, accepted entity/target types, policy level, command/workflow key, required features, expected evidence, and unsupported conditions.
  - Resolve ambiguous service detection conservatively and show why an action is suggested. Do not treat a port number alone as proof of a service when a scanner reported a conflicting service.
  - Register passive `version_cve_correlation` as an evidence/check family with its identifier requirements, supported advisory sources, confidence rules, and active-verification recommendations. It must not be represented as a command that can silently launch from a read surface.
  - Reuse this registry in Assessment target rows, Atlas entity profiles, Project Overview hints, and Quick Lookup while keeping actual launch state in the Assessment/Workflow/Run surfaces.
- [ ] Build curated Nmap NSE workflows first:
  - Separate `safe`, `default`, `version`, `discovery`, and reviewed `vuln` scripts from `auth`, `brute`, `dos`, `exploit`, `external`, `fuzzer`, and `intrusive` categories.
  - Pin allowed script names/categories in app-owned profiles, validate `--script-args` and Files-backed argument files, and keep third-party scripts unavailable unless an operator deliberately installs and allowlists them.
  - Parse useful structured service evidence such as SMB signing/dialect, anonymous access, SSH algorithms/keys, RPC/NFS exports, TLS state, and mail capabilities without classifying every informational row as a vulnerability.
- [ ] Add small protocol-specific tools only where NSE and current commands leave a proven gap:
  - Evaluate `smbclient`/`enum4linux-ng`, Net-SNMP tools, and LDAP client tools as an optional service-enumeration pack with pinned versions, safe command policies, structured adapters, and multi-arch container validation.
  - Keep credential attacks, spraying, unrestricted share downloads, and invasive directory modification disabled. Any future intrusive extension must be a separate operator opt-in and is not part of this item.

#### Phase 8 — Add bounded collection fan-out to durable workflows

- [ ] Introduce an explicit workflow version for collection semantics while leaving legacy and v2 scalar workflows unchanged:
  - Add bounded list captures for lines, entities, and JSON Pointer arrays with type, item limit, byte limit, deduplication, normalization, and required/empty behavior.
  - Add a `for_each`/fan-out step that renders one command per captured item, validates every rendered command and target through normal policy/scope checks, and records each child run against the parent step.
  - Add global execution limits for captured items, generated child runs, parallel children, total requests where known, total runtime, stored output, retries, and failure count.
  - Support fail-fast, continue-and-summarize, and bounded retry policies without letting one failed target erase successful child evidence.
  - Checkpoint pending/completed item state so restart recovery resumes unlaunched work without duplicating completed runs. Cancellation must stop active children and leave a truthful partial summary.
  - Keep collection values out of public execution serializers, logs, metrics, and notifications; expose counts and bounded redacted samples only where the current role may see them.
- [ ] Extend the workflow editor/execution UI and built-in playbooks:
  - Let authors choose scalar or collection captures, configure limits, select a fan-out source, preview command templates with placeholders, and see validation beside the affected field.
  - Show parent-step progress, succeeded/failed/skipped counts, active child runs, and a bounded failure sample on desktop and mobile.
  - Add maintained assessment playbooks such as subdomain → resolve → probe → crawl → scan, live URL → screenshot → parameter inventory, API schema → operations → bounded tests, and port → service-specific enumeration.
  - Require Files only where a tool genuinely needs an intermediate file; use structured captures for orchestration and Files artifacts for user-visible durable output.

#### Phase 9 — Add optional external scanner and OAST connectors

- [ ] Integrate OWASP ZAP as an operator-configured worker/sidecar, not as part of the main image:
  - Add configuration for base URL, authentication secret, TLS verification, allowed network ranges, concurrency, job timeout, and maximum report size.
  - Generate a bounded ZAP Automation Framework plan from selected Project targets, HTTP profile, authentication role, scope exclusions, and safe/intrusive policy; show the plan summary before submission.
  - Track remote job id/status/progress, cancellation, expiry, and errors without proxying unbounded ZAP logs into the app database.
  - Download completed output into the active Files/Project evidence boundary and pass it through the existing ZAP import preview/apply path. Do not silently apply remote findings before the operator reviews the import summary and warnings.
- [ ] Add private OAST support through an operator-configured Interactsh-compatible service:
  - Do not default to a public callback service. Require an explicit server URL, token/secret, allowed domain, TLS policy, retention, and privacy acknowledgement.
  - Issue per-run/per-check correlation ids, keep callback credentials private, and attach bounded DNS/HTTP/SMTP/LDAP interaction evidence to the originating run, assessment check, entity, and finding.
  - Deduplicate callbacks, reject callbacks outside the active correlation window, redact sensitive request fields, and make retention/cleanup behavior visible.
  - Keep OAST use explicit and policy-gated; viewing a recommendation or running unrelated Nuclei checks must not allocate a callback domain.
- [ ] Treat Greenbone/OpenVAS and similar full vulnerability managers as external systems:
  - Add a Greenbone result importer or connector only after its source format, ownership, duplicate handling, and Project/Atlas mapping are defined.
  - Prefer submit/status/result integration with an operator-managed deployment; do not embed its services, feeds, database, or scheduler into darklab_shell.
  - Reuse Atlas import preview/apply, finding provenance, assessment evidence links, and Project reporting rather than building a second external-findings store.

#### Phase 10 — Complete reporting, evidence packages, and retest workflows

- [ ] Add assessment context to Project evidence packages and reports:
  - Include assessment identity, profile/version snapshot, scope/target snapshot, check-state rollups, applicable denominator, manual exclusions with reasons, evidence references, tool/profile versions, tested timestamps, and unavailable-evidence warnings.
  - Add an assessment methodology/coverage section to the existing report composer. Keep untested, blocked, skipped, not-applicable, and no-app-captured-finding states distinct in HTML, Markdown, JSON, print/PDF, and redacted exports.
  - Add a fix-first section using the shared deterministic ranking, with one row per remediation identity and the KEV, EPSS, CVSS, exploit-reference, confidence, exposure, age, source-freshness, and related-observation signals that explain each item's placement. Expand the separate evidence methods without counting them as additional vulnerabilities, and do not collapse the ranking inputs into an unexplained risk score.
  - Add a cross-cycle delta section for new, persistent, not-observed, human-dispositioned fixed, regressed, and incomparable findings. Include the comparison basis and evidence references so absence is never presented as remediation without compatible completed coverage.
  - Let users include selected screenshot evidence while preserving package size estimates, binary checksums, redaction rules, source-run ownership, and missing-artifact warnings.
  - Keep secret names, HTTP headers/cookies, connector credentials, workflow variables, private callback tokens, internal workspace paths, and private verification notes subject to the existing private-note/redaction boundaries.
  - Record the assessment cycle and check ids in package/report manifests so a later reviewer can trace coverage back to the saved Project without treating the export as live state. Include the approved FIRST EPSS and CISA KEV attribution, data dates, model/catalog versions, checksums, and non-endorsement language wherever their signals appear.
- [ ] Add a finding-centered retest queue:
  - Group findings that are ready to verify or need retest by Project target, assessment check, action, and HTTP role/profile.
  - Offer a bounded batch launch only when every item shares a safe compatible action and scope; otherwise keep launches individual and explain the mismatch.
  - Compare the original and verification evidence using existing run comparison where compatible, attach the comparison to the finding, and require a human disposition.
  - Update assessment rollups when verification changes, but preserve the original finding occurrence and earlier assessment-cycle history.

#### Phase 11 — Test, document, and qualify the complete feature

- [ ] Add backend coverage in the existing Python suites:
  - SQLite/Postgres migration parity, schema drift, indexes, foreign/reference cleanup, backup/restore, session migration, Project deletion, team archive/reactivation, quotas, and query plans.
  - EPSS/KEV/OSV feed parsing, bundled bootstrap provenance and attribution, silent baseline installation/upgrade, local/external advisory acquisition modes, outbound lookup opt-in, positive/negative cache expiry, conditional/atomic refresh, refresh leases, size/schema rejection, last-good fallback, staleness, conflicting/withdrawn records, finding-CVE links, snapshot reproducibility, and deterministic risk ordering with missing signals.
  - Risk-escalation activation/reset hysteresis, no-repeat active state, KEV and model-version crossings, changed-CVE-to-remediation lookup plans, observation-to-remediation event deduplication, durable batch resume, per-owner fairness, transactional deduplication, personal/team isolation, archived scopes, multi-Project projection, no-Project behavior, independent acknowledgement, digest opt-in, quiet refreshes, and downgrade/withdrawal/de-list events.
  - Profile validation/snapshot stability, owner/team isolation, role capabilities, archived-team reads, check-state transitions, evidence matching, unavailable evidence, rollup denominators, manual overrides, and incremental recalculation.
  - Browser/API route parity, pagination, malformed payloads, missing/out-of-scope references, forged owner fields, audit contents, log redaction, metrics cardinality, and rate/concurrency limits.
  - Manual finding creation/edit/dedup/evidence, observation-versus-remediation identity, distinct rollup/worklist counts, transcript-line selection, CVE/CVSS/CWE/reference validation, shared risk enrichment, verification-run linkage, compatible/incompatible cross-cycle reconciliation, report/package attribution/rendering, redaction, and cleanup.
  - HTTP-profile secret isolation, temporary-file lifecycle, redirect/schema/callback scope enforcement, display-command masking, recovery cleanup, and permission changes between preview and launch.
  - Structured adapters and parsers for every added tool using small checked-in fixtures for success, empty output, malformed output, tool errors, multiple targets, duplicate results, and version drift. Cover CPE and PURL affected-range boundaries, ambiguous/unversioned product evidence, inferred-versus-confirmed CVEs, SARIF paths/fingerprints, CycloneDX components/VEX states, and potential-versus-confirmed dangling records.
  - Workflow collection compilation, rendering, item/byte/run limits, checkpoint recovery, cancellation, retry, partial failure, redaction, and cross-scope rejection.
  - ZAP/OAST/Greenbone connector tests with local fakes only; normal tests must never contact real targets, providers, callback servers, or scanner services.
- [ ] Add frontend unit and interaction coverage:
  - Assessment tab loading, cycle switching, filters, remediation-group coverage/risk rollups, observation expansion, explained fix-first ordering, bundled/stale feed status and operator guidance, cross-cycle deltas, target expansion, recommendations, manual states, permission/read-only behavior, stale requests, empty/error/degraded states, and preserved return/scroll context.
  - Project Monitoring typed risk events, independent acknowledgement, multi-Project projection, no-Project fallback links, digest risk opt-in, watcher/risk rollup separation, and accessible desktop/mobile event rendering.
  - Manual finding/evidence editor validation, run-line selection, HTTP-profile secret references, screenshot gallery paging/viewing, retest queue, and workflow collection editor/progress.
  - Shared pressable, disclosure, select, focus, dismissal, action-sheet, confirmation, chip/badge, semantic-color, and mobile Back contracts. Do not replace shared helper coverage with implementation-specific event tests.
  - Keep large Atlas/Project Vitest cases deterministic and below the CI timeout by waiting for explicit render state instead of polling broad DOM conditions.
- [ ] Add focused Playwright journeys through the approved helper:
  - Create a Project assessment, review truthful empty coverage, launch a safe recommended workflow, observe derived evidence, create a manual finding from run lines, attach a verification run, and export assessment context.
  - Exercise desktop and mobile Project flows, viewer/operator permissions, personal/team scope changes, archived-team read-only behavior, HTTP-profile missing-secret recovery, and destructive confirmations.
  - Run applicable journeys in bundle and source modes with `bash scripts/run_playwright.sh --asset-bundle-mode bundle ...` and `bash scripts/run_playwright.sh --asset-bundle-mode source ...`.
- [ ] Qualify the runtime and supply chain:
  - Build AMD64 and ARM64 images; verify tool and bundled-data versions/checksums/licenses/attribution, SBOM and vulnerability reports, runtime user, read-only root filesystem, Files behavior, raw-scan readiness, and image-size impact.
  - Run command-policy tests proving disallowed SQLmap/NSE/destructive flags remain blocked and connectors cannot escape configured target/network scope.
  - Run `npm run assets:sync` and `npm run assets:check` for frontend source changes and keep committed hashed assets/compression siblings current.
- [ ] Update current-state documentation as each phase ships:
  - Keep `README.md` and `FEATURES.md` user-focused; document durable contracts and route/data ownership in `ARCHITECTURE.md`; document operator settings and sidecars in `CONFIGURATION.md`; update `docs/tools.md`, `docs/workflows.md`, API/OpenAPI docs, CLI help, `THEME.md` if a semantic token contract changes, and `tests/README.md`/`CONTRIBUTING.md` when test counts or commands change.
  - Add every shipped change to `CHANGELOG.md`, update relevant release/MR drafts under `docs/release-drafts/` when present, and keep those drafts out of official documentation.
  - Remove this TODO only after the final acceptance criteria pass and all shipped behavior is documented as current state.

#### Acceptance criteria

- [ ] A fresh or disconnected install can rank CVE findings from release-pinned, attributed EPSS and CISA KEV bootstrap snapshots, clearly labels their source/date/model/freshness, and never turns baseline import into escalation events. Live EPSS/KEV refresh remains an explicit operator choice; OSV/NVD advisory correlation uses an operator-selected local dataset or explicitly enabled bounded lookups; no source makes a network request from an assessment, finding, Atlas, report, or other read surface.
- [ ] A later feed change can raise one owner-scoped, traceable risk-escalation event without rescanning or leaking inventory; EPSS activation/reset hysteresis prevents threshold flapping, and Project Monitoring and opted-in digests surface the event without synthetic watcher fires, duplicate replay, starvation, or losing downgrade/de-list history.
- [ ] A Project can create, complete, archive, and revisit versioned assessment cycles without changing historical evidence or earlier coverage.
- [ ] Every applicable check clearly distinguishes untested, running, covered with no app-captured findings, findings awaiting review, blocked, failed, skipped, not applicable, and unavailable evidence.
- [ ] Coverage is derived from compatible scoped evidence, not merely from any linked run, and every rollup has an honest denominator.
- [ ] Manual findings can be created from scratch or selected run evidence, carry structured assessment details, link targets/evidence/retests, and flow through existing Atlas, Project, package, report, team, audit, and redaction contracts.
- [ ] CVE-bearing findings keep active confirmation, version/package inference, imported assertion, and manual assessment as distinct observations; related observations share one remediation identity and count once in headline rollups and fix-first worklists. Assessment, Overview, Findings, packages, and reports use the same explainable KEV/EPSS/CVSS-based default priority order and source attribution.
- [ ] Compatible assessment cycles derive new, persistent, not-observed, and incomparable observations from scoped evidence; `fixed` stays a human disposition backed by compatible verification, and `regressed` applies only when a previously-fixed finding is observed again. No missing, failed, or partial check and no one-cycle absence is ever treated as proof of remediation.
- [ ] Authenticated HTTP checks use named secret-backed profiles without exposing credentials in stored commands, browser state, APIs, logs, metrics, audit rows, notifications, exports, or temporary files left after completion/recovery.
- [ ] Historical URL discovery, current crawling/probing, screenshots, parameter testing, API schema testing, Nuclei profiles, service-specific enumeration, passive product/package correlation, SARIF/CycloneDX imports, and dangling-record checks produce structured, provenance-rich evidence through normal command policy and Files boundaries.
- [ ] Safe/standard/intrusive/destructive policy is visible and enforced; no read action runs a scan, and no normal assessment action enables brute-force, denial-of-service, exploitation, data dumping, filesystem writes, resource claiming, or takeover behavior.
- [ ] Collection workflows remain bounded, resumable, cancelable, scope-safe, and truthful about partial success/failure across child runs.
- [ ] Optional ZAP, OAST, and Greenbone integrations fail closed, respect owner/team/target boundaries, and reuse existing import/evidence/reporting surfaces without putting those systems in the primary image.
- [ ] Desktop, mobile, browser, API v1, CLI, Project Overview, Assessment, Atlas, Findings, evidence packages, and reports agree on assessment identity, coverage counts, finding state, risk ordering, cycle deltas, and evidence availability.
- [ ] SQLite and Postgres, AMD64 and ARM64, personal and team scopes, archived teams, bundle/source assets, backup/restore, session migration, redaction, audit/logging, and CI performance all pass their targeted and full-suite gates.

### Autoscale ARM64 release runners on EC2 Spot

Replace the long-running hosted ARM64 release lane with an ephemeral EC2 worker pool managed by GitLab Runner's Docker Autoscaler and AWS fleeting plugin. Keep the runner manager on existing self-hosted infrastructure, scale the AWS Auto Scaling Group from zero only after the manager accepts a matching job, and destroy each worker after one job. Preserve a documented On-Demand or hosted-runner fallback so Spot capacity does not become a hard release blocker.

- [ ] Define the runner and worker contract before provisioning infrastructure:
  - Use the `docker-autoscaler` executor so the existing Docker job images, service containers, privileged Docker-in-Docker flow, and release scripts keep their current execution model.
  - Give this runner configuration its own AWS Auto Scaling Group; do not share the group with another runner manager or `[[runners]]` entry.
  - Start with one job per instance, one use per instance, one maximum instance, no idle capacity, and no local state that must survive termination.
  - Use an ARM64 worker with at least 8 vCPU, 32 GiB RAM, and a 250 GiB `gp3` Docker volume. Treat `m7g.2xlarge` as the baseline while allowing a configurable pool of compatible Graviton instance types.
- [ ] Add Terraform for the AWS worker pool:
  - Define inputs for AWS region, VPC, worker subnets, runner-manager network ranges, ARM64 AMI, instance-type overrides, maximum capacity, root-volume size and performance, and common resource tags.
  - Create a launch template that requires IMDSv2, uses an ARM64 AMI, enables delete-on-termination storage, and provisions the Docker filesystem on a 250 GiB `gp3` volume with configurable IOPS and throughput.
  - Create a worker security group that allows SSH only from the runner manager's fixed address or private network and allows the outbound DNS, HTTPS, and registry traffic needed by release builds.
  - Create a mixed-instances Auto Scaling Group with minimum and desired capacity `0`, maximum capacity `1` by default, multiple subnets and compatible Graviton instance types, `price-capacity-optimized` Spot allocation, no independent scaling policy, instance scale-in protection, and `AZRebalance` suspended.
  - Keep Spot at 100% for normal operation, but make the purchase policy configurable so an operator can temporarily select On-Demand capacity without changing the runner or CI configuration.
  - Create the least-privilege IAM policy needed by the fleeting manager: describe the ASG and instances, change desired capacity and instance protection, terminate workers through the ASG, inspect Spot requests, and publish temporary SSH keys through EC2 Instance Connect when dynamic credentials are enabled.
  - Output the ASG name, region, worker security-group ID, IAM policy ARN, and other values required by runner-manager configuration without outputting secret credentials.
  - Add Terraform formatting, validation, static security checks, and reviewed plan output. Confirm a second plan is empty after apply and that destroying the stack removes workers, launch-template resources, and disposable volumes cleanly.
- [ ] Prepare a fast, reproducible ARM64 worker image:
  - Bake or otherwise version an ARM64 image with Docker Engine, SSH, EC2 Instance Connect support, CA certificates, and the small set of host utilities required by GitLab's Docker Autoscaler.
  - Enable Docker at boot, grant the connector user access to Docker, and verify `docker info` succeeds over the same SSH path the runner manager uses.
  - Keep boot-time configuration short and deterministic; do not install the full toolchain through user data on every scale-out.
  - Record the image identifier as a Terraform input so worker-image updates produce an intentional launch-template revision.
- [ ] Add generic Ansible management for the existing runner manager:
  - Install or update a GitLab Runner version compatible with GitLab.com and the Docker Autoscaler executor.
  - Configure the AWS fleeting plugin with a pinned compatible version and run `gitlab-runner fleeting install` when the selected plugin version is not already installed.
  - Manage a root-readable AWS config containing the selected profile and region. Store AWS credentials through the automation system's secret mechanism rather than in source control, and keep the credential file readable only by the GitLab Runner service account.
  - Manage the runner's `config.toml` entry with `executor = "docker-autoscaler"`, the protected ARM64 runner tags, privileged Docker support, `capacity_per_instance = 1`, `max_use_count = 1`, `max_instances = 1`, and an all-day policy with `idle_count = 0`.
  - Configure the fleeting plugin with the Terraform-provided ASG name and AWS profile, and configure the SSH connector for either the worker's private address or its public address according to the chosen network design.
  - Persist the runner configuration and, if enabled, taskscaler state across manager restarts with restrictive ownership and permissions.
  - Validate the rendered runner configuration, installed plugin, AWS identity, ASG discovery, and service health before restarting the GitLab Runner service. Keep the Ansible run idempotent.
  - Add runner-manager logging and monitoring for scale requests, worker acquisition time, preparation failures, Spot interruption failures, orphaned instances, and ASG desired capacity that remains above zero without an active job.
- [ ] Prove the network and security boundaries:
  - Confirm the runner manager can reach GitLab.com and the required AWS APIs over HTTPS and can connect to workers over SSH, while workers accept no other inbound application traffic.
  - If workers use public addresses, restrict SSH to a fixed runner-manager source address. If workers use private addresses, document and validate the VPN or routed connection into the VPC.
  - Confirm workers can resolve DNS and reach GitLab registries, Docker Hub, GitHub, language package indexes, and every other source used by the release image build without requiring broad inbound access.
  - Verify the runtime IAM identity cannot modify unrelated Auto Scaling Groups or EC2 instances.
- [ ] Migrate the ARM64 CI lane behind a temporary runner tag:
  - Register the autoscaled runner as protected, locked to the intended project or group scope, and unable to accept untagged jobs.
  - Point a temporary ARM64 build job at the new tag before changing the canonical release jobs.
  - Preserve the current DinD service, MTU handling, native architecture checks, artifact contracts, timeouts, and disk measurements.
  - Add a bounded retry for runner-system failures so a Spot interruption or failed worker acquisition can retry an idempotent build without hiding repeatable product failures.
  - Keep the current ARM64 runner path available until the EC2 lane passes qualification and the fallback procedure has been exercised.
- [ ] Qualify performance, cleanup, failure handling, and cost:
  - Demonstrate scale from desired capacity `0` to `1` after job acceptance and back to `0` after completion, with no worker or EBS volume left behind.
  - Run an uncached release image build and record provisioning time, build and export duration, peak disk use, final free-space percentage, CPU and memory pressure, and total Spot runtime.
  - Run consecutive cached builds through the registry cache and confirm the larger worker avoids the cache-import and export-time disk exhaustion seen on the hosted ARM64 lane.
  - Require at least 20% free Docker storage after image export and enough wall-clock margin to stay comfortably within the CI job timeout.
  - Trigger a controlled Spot interruption, confirm the interrupted job fails as a runner-system failure, and confirm its retry starts on a fresh instance without conflicting with staging tags or publication state.
  - Exercise the On-Demand fallback and return the ASG to Spot afterward.
  - Add an AWS budget or cost alarm and confirm the idle-state cost is limited to the always-on runner manager and any intentionally retained supporting infrastructure.
- [ ] Cut over only after three consecutive ARM64 release rehearsals complete without manual repair. Then update the maintained CI and contributor documentation, remove the obsolete runner path, and record the final instance pool, storage floor, fallback policy, and measured build timings in `DECISIONS.md` and `CHANGELOG.md`.

## Known Issues

No open Known Issues are currently tracked.

---

## Technical Debt

### Retire the local Nuclei kin-openapi compatibility patch

Nuclei 3.11.0 still pins the vulnerable kin-openapi 0.132.0 release and doesn't compile against the fixed API without a two-line source patch. The image currently raises kin-openapi to the secure 0.144.0 floor, applies the compatibility patch, and verifies the selected dependency is embedded in the finished Nuclei binary.

- [ ] Wait for a released Nuclei version that supports kin-openapi 0.144.0 or newer without source modification.
- [ ] Update `NUCLEI_VERSION`, build Nuclei without `GO_TOOL_SOURCE_PATCH`, and confirm its embedded kin-openapi version still meets the secure floor.
- [ ] Remove the local patch, its Docker build-context and release-provenance wiring, and the patch-specific regression assertions. Keep the dependency floor and license tracking while kin-openapi remains embedded.
- [ ] Build and scan the AMD64 and ARM64 runtime images. Confirm their SBOMs record the expected Nuclei and kin-openapi versions and Grype no longer reports `GHSA-r277-6w6q-xmqw`.
- [ ] Update `CHANGELOG.md` and remove this item after the unpatched release path passes the protected image and supply-chain gates.

---

## Feature Enhancements

These are possible future improvements, split by whether they look worth carrying forward.

- **Webhook receiver / `POST /api/v1/intel/<provider>` passthrough.**
  - Worth scoping once outbound notifications and external automation mature. The headless API is the right place to receive webhooks that auto-create or update projects.
- **Cross-session Atlas view.**
  - Useful for operators managing multiple sessions or shared infrastructure, especially now that team mode makes shared context more important.
- **Extend comparison beyond run-to-run finding and artifact diffs.**
  - Snapshot and package-artifact comparisons are likely useful once evidence packages become a regular handoff surface.
- **Package re-import preview/apply.**
  - Worth scoping once package handoff archives are used regularly. It should reuse the Atlas import preview/apply pattern and the package manifest import hints before it writes project data.
- **Project Monitoring CLI surface.**
  - Possible future `darklab monitoring <project_id>` and `darklab monitoring ack <project_id> <fire_id> --state STATE [--note NOTE]` commands could expose the Project Monitoring dashboard, rollups, and fire triage flow without opening the browser.
  - Keep this lower priority than watcher creation, Project assignment, policy controls, and baseline acceptance, which are already available through `darklab watch`.
- **Headless API and CLI follow-through.**
  - Let scripts and CI start, inspect, cancel, and follow durable workflows through token-authenticated API routes and matching `darklab workflow` commands. Expose saved-run comparison through the same headless surface once its permission, team-scope, and bounded-output contracts are defined.
  - Put the workflow execution event cursor to work for browser refresh or headless replay, or retire it if execution polling remains the supported path.
  - Add `darklab --version` for the installed client. Treat connected-server version and client/server compatibility reporting as a separate decision.
  - Bring the existing API v1 AI assists to the CLI with summary and next-command commands that handle cached, queued, in-progress, disabled, and failed states cleanly.
- **Revisit PTY transport after real usage.**
  - The current Redis-brokered SSE plus POST endpoints keep deployment simple, but WebSockets may be worth it if latency, throughput, or bidirectional control becomes a real limitation.
- **Split `pty.js` and `pty_service.py` if PTY work grows again.**
  - Worth doing when new PTY behavior lands; orchestration, modal wiring, xterm session handling, lifecycle, transport, and metadata storage are natural boundaries.
- **Introduce a small PTY host interface object and broader PTY browser coverage.**
  - Would make PTY tests less brittle and keep future tab-state or disabled-terminal changes from drifting.
- **Reduce idle PTY control-channel work if concurrency becomes real.**
  - Redis Pub/Sub, a longer block window, or avoiding unnecessary attach-time snapshot writes would be worthwhile if many PTYs are active at once.

## Research

No research items are currently tracked.

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Run replay / scrubbable event stream
- Turn completed runs into replayable structured event logs, building on the Structured Output Model.
- Support a scrub timeline, bookmarks, per-line comments, and command-by-command playback.
- Keep replay integrated with findings, Atlas entities, summaries, and run comparison rather than treating it as a separate asciinema-style recording.

### Run comparison enhancements — deferred pieces
- Run comparison now covers finding severity changes, discovered hosts, TLS fields, workflow context, and completed-tab launch points. The remaining ideas are:
  - Snapshot/permalink compare, once the compare route can resolve snapshot/permalink ids instead of only live `runs` rows.
  - `Export comparison`, once share/export packages have one unified, stable artifact schema version rather than several independent `schema_version` fields.
  - Unifying the comparison-local URL/status/title parsing (`httpx`/`ffuf`/`gobuster`/`katana`) with the shared tool-aware classifier registry that ports/hosts/tls already use.
  - Date-range filters in the manual compare picker, if day grouping plus `Load More` is not enough for deep history.
  - Broader Playwright coverage for additional edge and mobile layout paths.
  - Focused large/noisy comparison regression coverage if real-world outputs expose performance issues beyond current backend and unit coverage.

### Bulk history export and share
- The history drawer can delete all, delete non-favorites, export selected history as text/JSONL, and use visible-page multi-select for bulk project add/remove plus selected-item delete. Bulk share/permalink bundles would close the remaining gap when packaging selected history items after an engagement.

### Mobile share ergonomics
- The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
  - save/share actions tuned for one-handed use
  - clearer copy/share/export affordances inside the mobile shell
  - better share handoff after snapshot creation

### PWA install and service-worker push
- Make the mobile shell installable and deliver completion pings via web-push so phone users get notified when the tab is closed or the device is asleep. Today mobile notifications are intentionally hidden because foreground-only notifications are not useful on phones.
- Reuse the run-complete notification hook so push delivery becomes another channel rather than a separate completion system.
- **Entry-level scope:**
  - Add a manifest, app icons, and a small service worker so users can "Add to Home Screen" and launch into a standalone mobile shell.
  - VAPID-signed web-push subscription tied to the active session token; subscribe and unsubscribe from the Options sheet.
- **Architecture:**
  - New `app/static/manifest.webmanifest`, icon assets under `app/static/icons/`, and `app/static/sw.js` registered from `app.js` only when the runtime supports it.
  - New `WebPushChannel` in the notifications service; VAPID keys stored as operator config; per-session-token subscription endpoint at `/session/push/subscribe`.
  - Service worker scope is intentionally narrow — render notifications and open the tab on click; no caching of dynamic transcript content so users never see stale output.
  - Gotchas: iOS Safari requires the user to install the PWA before push works; document this in CONFIGURATION.md.

### Engagement report builder
- The Project Report tab now covers the base narrative-report flow. Future polish can make reports feel more portable and customer-ready:
  - Add report-created run links or permalinks where needed, carrying the report's redaction mode and showing the `permalink_retention_days` caveat in preview/export metadata.
  - Feed richer package/export provenance into the report once that plan lands, especially source run/import context and target relationships.
  - Tune artifact embedding/listing once provenance and report-created run links are available; screenshot galleries and richer binary handling can stay later work.
  - Run a browser Print/PDF fidelity pass across Chrome, Safari, and Firefox for page breaks, headers/footers, and fonts. If the browser print path cannot produce a consistent customer-grade PDF, revisit a server-side PDF renderer with its Docker/dependency cost documented.
  - Consider saved report versions, richer in-UI template customization, arbitrary custom sections, approvals, and shareable report permalinks after the one-current-draft workflow has real usage.

### Native ticketing integrations
- From the Findings tab, Project views, or evidence package flows, create or update issues in Jira, Linear, GitHub Issues, GitLab, etc., with bidirectional sync of status, notes, and links back into the finding review state.
- Keep the action close to existing triage and review-state controls so tickets feel like an extension of finding review, not a separate export step.
- **Entry-level scope:**
  - Generic webhook + templated payload connector plus first-class adapters for the most common trackers.
  - Secret-backed auth stored in the existing encrypted secrets surface.
  - One-click "Create ticket" and "Link existing" actions on individual findings and bulk on visible-page selections.
  - Map finding review state to ticket status (and vice versa) where the tracker supports webhooks or polling.
- **Architecture:**
  - New `app/services/integrations/ticketing/` package (or a lighter `notifications` extension).
  - Adds project-level and global configuration surfaces under Options or a new Integrations tab.
  - Preserves the existing outbound notification model for fire-and-forget alerts while adding the stateful sync path.

### Operator-extensible signal and parser rules
- Allow operators to extend the built-in findings classifier, entity extractor, and structured metadata logic via a hot-reloadable `conf/signals.yaml` (or small sandboxed snippets) without code changes.
- Custom rules feed the same findings strip, Atlas materialization, search scopes, run comparison diffs, project triage, and export surfaces as core signals.
- Target custom scanner output and internal tooling first; the biggest value is letting self-hosted teams teach darklab_shell their local signal language without carrying a fork.
- **Entry-level scope:**
  - Declarative regex + capture group + mapping rules for common cases (e.g., custom internal scanner output).
  - Optional tiny expression or Lua/JS sandbox for complex parsing.
  - Live reload on file change (consistent with `commands.yaml`, `workflows.yaml`, etc.).
- **Architecture:**
  - Extend or parallel `app/core/output_signals.py` with a user-rules loader.
  - Surface validation and a `/diag` inspector mode for testing new rules against recent output samples.

---

## Architecture

### Interactive PTY transport future-state
- Revisit whether the current Redis-brokered SSE plus POST input/resize transport should move to WebSockets after real use.
- The current model keeps deployment simple and avoids a WebSocket runtime, but a bidirectional socket could reduce input latency and simplify the modal terminal stream once PTY usage grows.
