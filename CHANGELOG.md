# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.8.1
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [2.9.1] - Unreleased

### Fixed

- **DNS command options and resolvers no longer become Project entities.** `dig` and `nslookup` target discovery now recognizes the actual query and waits for a matching parsed answer before adding it. Record types, output options, selected resolvers, and names from negative lookups stay out of Atlas and Project targets.

---

## [2.9.0] - 2026-08-25

### Added

- **Projects now have an end-to-end Assessment workspace.** Assessors can start frozen Network, Web, API, TLS, or Combined cycles; review target coverage; record manual decisions; link saved evidence; create and verify findings; group matching remediation; prioritize fixes; queue compatible retests; compare cycles; and carry one selected cycle into reports and evidence packages. Personal and Team ownership, capability checks, archived read-only history, optimistic revisions, quotas, and forward-only lifecycle rules apply across the browser, API, and storage layers. Existing SQLite and PostgreSQL installations receive the required schema through the normal migration path.
  - Checks retain typed evidence from runs, workflows, findings, Atlas entities, artifacts, screenshots, Nmap services and versions, Dalfox parameters, DNS observations, HTTP technology, and imported reports. Evidence-derived state stays separate from an assessor's explicit decision, and removing a manual link never deletes its source.
  - Finding handoff keeps observation identity, shared remediation guidance, verification history, CVE-risk context, and provenance together. Completed and archived cycles remain usable as review and export history without reopening their mutations.

- **Assessment plans can run as bounded, durable batches.** A server-owned preview shows selected targets, exact commands, exclusions, policy, limits, expected coverage, and estimated duration before anything starts. Safe work is selected by default, standard work requires separate confirmation, and intrusive or unsupported work stays excluded. Approved plans use fair concurrency, startup recovery, truthful cancellation, immutable retries, retained evidence, and child-run provenance; Projects, Status Monitor, History, notifications, reports, and evidence packages show the same durable progress.
  - Managed Nuclei preflight reports the installed template snapshot and blocks incompatible work. Operators can atomically update and validate the cache, rebuild the preview, and retain the last good snapshot after failure. Compose installs an empty cache on first startup unless bootstrap is disabled; set both `NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED=false` and `NUCLEI_TEMPLATE_REFRESH_ENABLED=false` when the deployment must never make an outbound template update request.
  - Configurable command and concurrency ceilings are enforced by the API as well as the browser. Batch request bodies, stored events, recovery work, retries, notifications, logs, and metrics remain bounded and omit targets, commands, credentials, and protected profile material.

- **Reviewed Assessment actions cover common network, web, API, TLS, and connector workflows.** Maintained actions include Nmap service review, protected Curl, HTTPx, Katana, detection-only SQLmap, Dalfox discovery and evidence-backed validation, Schemathesis, reviewed Nuclei profiles, historical URL discovery, screenshot capture, takeover confirmation, and selected service-specific checks. Reusable HTTP profiles bind allowed scheme, host, port, roots, included and excluded paths, request limits, headers, and app-managed Secret or Files references without storing credentials in the profile.
  - Intrusive actions are disabled by default, require fresh confirmation, and never enable destructive actions. ZAP and private OAST integrations are opt-in, use encrypted private job material, revalidate scope at launch, and keep provider credentials, callback data, targets, plans, and reports out of logs and public state. ZAP also requires scanner-side DNS and CIDR attestation before submission.
  - Nmap, Nessus, HTTPx, CycloneDX, DNSx, Dalfox, Schemathesis, ZAP, and OAST results can produce bounded typed observations or findings only after their provenance and reviewed launch contract are revalidated.

- **Projects can run one reviewed probe without opening an Assessment cycle.** The browser terminal, API, and `darklab probe` CLI list, preview, and launch maintained Project-scoped actions through ordinary runs. Every probe resolves one confirmed Project target and rechecks its plan digest, scope, permission, policy, feature gate, and protected HTTP material before launch. Existing History, Project links, evidence reconciliation, and run cleanup continue to apply; probes don't create a second execution or results model.

- **The headless API and CLI now cover the complete supported assessor workflow.** Scripts can manage Assessment lifecycles, actions, batches, retries, cancellation, assessor-authored findings, typed evidence links, Nmap service evidence, HTTP profiles, EPSS/KEV status, and explicit exact-package OSV lookups. Bounded JSON input, stable text/JSON/NDJSON output, explicit revisions, destructive confirmations, actionable permission and lifecycle errors, shell completion, and real API integration coverage make these commands suitable for automation. Browser-owned Project administration, interactive Atlas intelligence, monitoring, Web Surface, grouped retests, and template refresh remain intentionally outside this general mutation surface.

- **Evidence imports and risk intelligence retain more review-ready context.** Atlas accepts bounded Greenbone, Nessus, SARIF 2.1.0, CycloneDX, and compressed reports; imported paths and source dispositions aren't trusted as local authority. Exact package and service versions can correlate with stored OSV and NVD applicability, while bundled or live EPSS and CISA KEV snapshots add source, publication, model, freshness, checksum, and non-endorsement context to the browser and reports. Explicit external OSV lookups are opt-in, rate-limited, deduplicated, time-bounded, and never run as a side effect of an ordinary read.

- **Web Surface keeps verified screenshots and comparisons with Project evidence.** HTTPx captures become bounded run artifacts with source provenance, then appear in a responsive, filterable gallery with a full-image viewer and compatible-baseline comparison. Packages and reports preserve the capture and redaction boundary, while stale, missing, or oversized artifacts fail visibly instead of being treated as evidence.

- **Workflows can fan one collection step out across bounded child runs.** Versioned workflow definitions can expand a reviewed collection command, persist private captures and restart-safe checkpoints, retry within policy, expose value-free progress, resume after startup, and cancel unfinished children without losing completed attempts. Each child keeps its workflow ancestry in History and Project evidence, and the parent advances exactly once when the collection reaches a terminal result. The migration is additive and keeps earlier workflow definitions and ordinary execution behavior compatible.

- **Atlas entity profiles and Quick Lookup connect saved evidence around an asset.** Relationship-aware profiles organize app observations, findings, related URLs and ports, source runs, Project context, monitoring changes, and cached provider intelligence into focused Overview, Evidence, Findings, and Intel views on desktop and mobile. Quick Lookup opens the same profile for an exact saved hostname, IP address, or HTTP(S) URL from the desktop rail, mobile menu, or `Alt+Q` / `Option+Q`, including explicit not-found, ambiguity, and URL-parent fallback states.
  - Lookup is read-only: submitted values stay in request bodies and out of structured logs, no entity is created, no provider is contacted, and only owner-visible saved intelligence is returned. Existing Atlas detail fields remain available for API compatibility, while new collections are independently bounded and scoped to the active personal, Team, and optional Project context.

### Changed

- **Atlas entity extraction now distinguishes observed targets from tool and provider infrastructure.** SQLmap examples, HTTPx model downloads and resolvers, selected `dig` and `nslookup` servers, testssl.sh documentation and third-party references, WHOIS registrar and policy infrastructure, and similar tool-owned values no longer become entities. DNS extraction follows the actual query and answer chain: it keeps relevant A, AAAA, CNAME, PTR, same-project MX/NS/SRV, and CAA owners while rejecting SOA contacts, TXT references, DNSSEC data, reverse-zone owners, trace infrastructure, malformed owners, negative lookup subjects, and rejected targets' addresses. Complete run output, findings, search, comparison, and exports are unchanged, and existing noisy entities aren't deleted automatically because they may have valid provenance from another run.

- **Runtime dependencies, CI images, and bundled tools use current compatible releases.** The release moves to Python 3.14.7 and Go 1.27, refreshes Python and Node locks, updates the Python, Node, Docker, and digest-pinned GitLab CLI images, and updates maintained scanners and report contracts. Nuclei now builds against its upstream kin-openapi compatibility path without the retired local patch. OpenSSL remains on 3.6.3 and TLSX on 1.2.2 because their newer upstream lines don't yet meet the image's compatibility and immutable-source requirements.
  - Version checks now use OCI Registry v2 with bounded authentication, pagination, caching, complete-list enforcement, `v`-tag support, and digest verification instead of Docker Hub's rate-limited website API. The daily cache warm-up refreshes the runtime APT layer without discarding stable tool-build layers. Required container smoke tests are deterministic and network-free; public DNS and HTTP checks run separately on scheduled pipelines, and source-mode browser coverage is a required merge gate with retries disabled.

### Fixed

- **ARM64 release builds no longer duplicate the SecLists tree while assembling the runtime image.**
  - **Root cause:** Copying SecLists from an independent asset stage created a second multi-gigabyte BuildKit snapshot and exhausted GitLab's 30 GB hosted ARM64 runner before export.
  - **Fix:** The runtime stage now inherits the SecLists asset stage, preserving the same packaged wordlists in one shared layer while the ARM64 publisher remains uncached.
  - **Tests:** The production-installation contract now requires the shared stage ancestry and rejects a separate SecLists copy; focused Dockerfile, documentation, and license checks cover the release inputs.

- **Assessment launch boundaries now fail closed on scope, size, and provider limits.** Domain- and IP-based protected HTTP launches enforce saved roots and included/excluded paths, and protected Katana crawls keep the saved scheme, port, roots, and path scope instead of applying only headers. Assessment mutation endpoints enforce their 16 KiB or 64 KiB limits even when `Content-Length` is missing, and external OSV requests release database connections before a bounded provider call. These fixes preserve the existing public error envelopes and keep protected values out of responses, audit data, metrics, and logs.

- **Assessment operators now get useful, privacy-safe lifecycle diagnostics.** Catalog failures, batch deferrals and terminal outcomes, Nuclei refresh failures, optional run-finalization errors, ZAP jobs, and private OAST sessions use consistent DEBUG, INFO, WARNING, and ERROR records with fixed phases, bounded counts, safe ids, retry context, and sanitized tracebacks. Targets, commands, profile material, provider responses, callback data, credentials, report contents, and filesystem paths remain redacted.

- **Assessment and Atlas browser state now survives routine refreshes.** Planner and batch updates preserve scroll and focus, batch controls remain discoverable, Entity selection no longer jumps to the top, worklist filters and paging replace only their affected region, and stale lifecycle responses can't leave the Assessment tab stuck in a loading state. Archived Team assessments remain readable while mutation controls stay disabled.

- **Contributor type checks now understand structured test records.** Assessment batch log assertions model their custom fields, container smoke filters preserve each case's mapping type, and logging tests narrow stream handlers before replacing their output stream.

---

## [2.8.3] - 2026-07-29

### Fixed

- **GELF status fields now keep one OpenSearch-compatible type across the event stream.**
  - **Root cause:** request logs used the generic `_status` field for numeric HTTP codes while Intel provider and other lifecycle events reused it for text such as `ok` and `error`. Once OpenSearch mapped `_status` as a number, it rejected later text values with `mapper_parsing_exception`.
  - **Fix:** HTTP codes now use numeric `http_status`, while provider, workflow, schedule/watcher, AI, Project, team, and export states use feature-specific string fields. The shared GELF boundary no longer emits `_status`; it safely routes any remaining generic or invalid status value away from established numeric mappings.
  - **Tests:** formatter coverage exercises current semantic status fields, legacy numeric and string status payloads, invalid HTTP values, and explicit-field precedence. Existing request, Intel, AI, team, Atlas, Project, and export-log assertions now pin their replacement fields without increasing the test count.
