# Architectural Decisions

This document records the main design decisions, tradeoffs, bugs, and lessons that shaped darklab_shell.

Use [ARCHITECTURE.md](ARCHITECTURE.md) for the current system structure, diagrams, and persistence model. Use [README.md](README.md#production-deployment) for production deployment setup. Use this file for the reasoning behind those choices. If you're about to change something and want to know what has caused trouble before, start with [Known Gotchas and Lessons Learned](#known-gotchas-and-lessons-learned).

---

## Table of Contents

- [Runtime and Coordination Decisions](#runtime-and-coordination-decisions)
  - [Real-time Output: SSE over WebSockets](#real-time-output-sse-over-websockets)
  - [Redis-Backed Run Broker](#redis-backed-run-broker)
  - [Separate Command Execution, Shared Terminal Completion](#separate-command-execution-shared-terminal-completion)
  - [Multi-worker Process Killing via Redis](#multi-worker-process-killing-via-redis)
  - [Rate Limiting via Redis](#rate-limiting-via-redis)
  - [AI Assists: Private Provider, Worker, and Validation Boundary](#ai-assists-private-provider-worker-and-validation-boundary)
  - [Durable Workflows: Server-Owned Steps and Bounded Captures](#durable-workflows-server-owned-steps-and-bounded-captures)
- [Security and Isolation Decisions](#security-and-isolation-decisions)
  - [Cross-User Process Killing](#cross-user-process-killing)
  - [Two-User Security Model](#two-user-security-model)
  - [Path Blocking (/data and /tmp)](#path-blocking-data-and-tmp)
  - [Workspace Shell Conveniences Stay App-Mediated](#workspace-shell-conveniences-stay-app-mediated)
  - [Loopback Address Blocking](#loopback-address-blocking)
  - [Session Token Security](#session-token-security)
  - [Team Ownership: Session Tokens Stay Actors](#team-ownership-session-tokens-stay-actors)
  - [Deny Flag Matching (anywhere in command)](#deny-flag-matching-anywhere-in-command)
- [Deployment and Packaging Decisions](#deployment-and-packaging-decisions)
  - [Network Copyleft with GNU AGPLv3](#network-copyleft-with-gnu-agplv3)
  - [One Image, Two Compose Modes, and Dual Registry Publishing](#one-image-two-compose-modes-and-dual-registry-publishing)
  - [Keep One Full Release Image](#keep-one-full-release-image)
  - [Startup Sequence (entrypoint.sh)](#startup-sequence-entrypointsh)
  - [nmap Capabilities](#nmap-capabilities)
  - [Go Binary Installation](#go-binary-installation)
  - [SQLite WAL Mode](#sqlite-wal-mode)
  - [FTS5 Tokenizer: Trigram with Unicode61 Fallback](#fts5-tokenizer-trigram-with-unicode61-fallback)
- [Observability Decisions](#observability-decisions)
  - [Structured Logging](#structured-logging)
- [Atlas Decisions](#atlas-decisions)
  - [Port Entity Identity and Evidence](#port-entity-identity-and-evidence)
  - [URL Entity Host Links](#url-entity-host-links)
  - [Quick Lookup Reuses the Atlas Surface](#quick-lookup-reuses-the-atlas-surface)
- [Assessment Decisions](#assessment-decisions)
  - [Assessment Delivery and Runtime Ownership](#assessment-delivery-and-runtime-ownership)
  - [Shared CVE Risk Data and Ranking](#shared-cve-risk-data-and-ranking)
  - [Assessment History, Evidence, and Finding Identity](#assessment-history-evidence-and-finding-identity)
  - [Assessment Execution, Secrets, and Packaging](#assessment-execution-secrets-and-packaging)
- [Backend Architecture Decisions](#backend-architecture-decisions)
  - [Blueprint Parent Modules and Size Ratchets](#blueprint-parent-modules-and-size-ratchets)
  - [Mutable Runtime State Uses Source-Owner Accessors](#mutable-runtime-state-uses-source-owner-accessors)
- [Frontend Decisions](#frontend-decisions)
  - [Shared Jinja Document Shell](#shared-jinja-document-shell)
  - [Shared Frontend State Layer](#shared-frontend-state-layer)
  - [Export Rendering Centralization (ExportHtmlUtils)](#export-rendering-centralization-exporthtmlutils)
  - [Client-Side PDF Export (jsPDF)](#client-side-pdf-export-jspdf)
  - [Save Menu UX (save ▾ dropdown)](#save-menu-ux-save--dropdown)
  - [Native Share-Sheet for Permalink URLs](#native-share-sheet-for-permalink-urls)
  - [Dedicated Mobile Shell](#dedicated-mobile-shell)
  - [Button Primitive Family](#button-primitive-family)
  - [Disclosure Affordance Rules](#disclosure-affordance-rules)
  - [Semantic Color Contract](#semantic-color-contract)
  - [Confirmation Dialog Contract](#confirmation-dialog-contract)
- [Known Gotchas and Lessons Learned](#known-gotchas-and-lessons-learned)
  - [Runtime Streaming and Process Lifecycle](#runtime-streaming-and-process-lifecycle)
  - [Container and Filesystem Behavior](#container-and-filesystem-behavior)
  - [Demo Recording Pipeline](#demo-recording-pipeline)
  - [Linting and Static Analysis Toolchain](#linting-and-static-analysis-toolchain)
  - [Frontend and Rendering Gotchas](#frontend-and-rendering-gotchas)
  - [Long-Running and Local-Dev Edge Cases](#long-running-and-local-dev-edge-cases)
- [Related Docs](#related-docs)

---

## Runtime and Coordination Decisions

### Real-time Output: SSE over WebSockets

**SSE was chosen over WebSockets for output streaming.**

Server-Sent Events are simpler to implement with Flask, work correctly behind nginx-proxy without additional configuration, and are unidirectional (server → client) which is all that's needed for streaming command output. The frontend reads the SSE stream via `fetch()` + `ReadableStream` rather than the `EventSource` API, because `EventSource` doesn't support custom headers (needed for the session ID).

### Redis-Backed Run Broker

**Command execution is owned by the run broker, not by the browser request that started it.**

Earlier command streaming tied subprocess stdout draining directly to the browser's HTTP request. That made the first browser connection special: if the page reloaded, another browser opened the same session token, or the request stream failed, the backend had to choose between losing live output, continuing detached work with a separate drain path, or waiting for completed history. Those paths were hard to reason about and became especially awkward once Status Monitor needed cross-browser attach and kill behavior.

The current model starts commands with `POST /runs`, records active-run ownership metadata, and has a backend worker drain stdout exactly once. The worker publishes normalized events (`started`, `notice`, `output`, `error`, `exit`) to a run stream. Browsers subscribe with `GET /runs/<run_id>/stream`, optionally replaying from an event id. This makes subscribers replaceable: the owning tab, a reloaded tab, a phone on the same session token, and an attached tab all consume the same processed output stream.

Redis Streams were chosen for production because darklab_shell already relies on Redis for cross-worker rate limiting and process coordination. Gunicorn workers do not share memory, so in-process queues cannot provide reliable live-output replay or attach behavior across workers. SQLite is the durable history store, but it is a poor fit for high-frequency temporary stream events and blocking subscriber reads. Redis Streams provide ordered event ids, bounded replay, blocking reads, TTL-backed cleanup, and cross-worker visibility without turning the history database into a message bus.

The app still includes a single-process in-memory broker fallback for local development, but production live reattachment expects Redis. That split is intentional: local development should stay easy to start, while Docker/Gunicorn deployments need one shared broker so active run state, stream replay, and process control behave consistently no matter which worker handles the next request.

The old request-owned `POST /run` execution route was removed instead of kept as a compatibility layer. Maintaining two command execution paths would have duplicated lifecycle behavior, increased test burden, and made active-run behavior more fragile. `POST /run/client` remains separate because browser-owned built-ins such as `theme`, `config`, and `session-token` need local DOM/storage behavior before their rendered transcript is saved to normal run history.

### Separate Command Execution, Shared Terminal Completion

**Browser-owned and server-owned commands execute in different places, but the terminal settles them through one completion contract.**

Commands that need browser APIs still run in the browser: themes change live DOM state, preferences use local storage, secrets open a protected value prompt, and Files actions can launch an editor or download. Commands that launch tools or need authoritative policy enforcement still run through the backend broker and stream output over SSE. Moving either group across that boundary would either push trusted execution into the browser or force browser-only behavior into server routes.

The shared boundary comes after execution. Both paths hand normalized lines, exit state, persistence ownership, recents eligibility, the masked command, and requested refreshes to one coordinator. This prevents browser pipes, workflows, confirmations, and SSE exits from each maintaining their own slightly different status and history logic. Completion is keyed so a late callback or repeated event can't render or persist the same command twice.

Prompt history stays outside that coordinator by design. An accepted command enters prompt history at submit time so arrow-key recall works while it runs; rejected client-side input never enters it. Recents remain completion-time state and only include eligible results. Browser-owned commands use the saved `/run/client` response's command, while server-owned commands use the masked tab command. This keeps recents aligned with persisted history and closes the old gap where a server-run recent could retain a sensitive raw argument.

### Multi-worker Process Killing via Redis

**Problem:** Gunicorn runs 4 workers, each with isolated memory. A kill request could hit a different worker than the one that started the process.

**Approaches tried:**
- In-memory dict — fails immediately (isolated memory per worker)
- `multiprocessing.Manager` shared dict — tried and abandoned; unreliable after Gunicorn forks workers due to broken IPC socket connections under load
- SQLite `active_procs` table — worked correctly but was a misuse of a relational database for ephemeral process state; required a `DELETE FROM active_procs` purge on every startup to clear stale rows from crashes

**Solution:** Redis keys — `SET proc:<run_id> <pid> EX 14400`. Every worker reads and writes the same Redis instance. `GETDEL` (Redis 6.2+) provides an atomic get-and-delete, preventing race conditions between workers. The 4-hour TTL (`EX 14400`) replaces the startup purge — orphaned entries self-expire rather than requiring cleanup on init.

**Fallback for local development:** If `REDIS_URL` is not set, the app falls back to `memory://` for rate limiting and a `threading.Lock` + in-process dict for PID tracking. This works for single-process development (`python3 app.py`) but breaks under Gunicorn multi-worker mode — use Docker Compose for multi-worker testing.

**Critical timing fix:** `Popen` and `pid_register` must happen *before* `return Response(generate(), ...)`. Flask generators are lazy — the generator body doesn't execute until Flask starts streaming. If `pid_register` is inside the generator, a kill request arriving before streaming starts finds nothing in Redis and silently fails.

### Rate Limiting via Redis

**Problem:** Flask-Limiter with its default `memory://` backend gives each Gunicorn worker its own independent counter. With 4 workers, a user effectively gets 4× the configured limit before being rate-limited — the `rate_limit_per_minute` setting in config.yaml becomes meaningless under load.

**Solution:** Redis as the shared backend via `storage_uri=REDIS_URL` in the `Limiter` constructor. All workers increment the same counter in Redis, so the configured limit is enforced accurately across the entire process pool.

Request identity now follows an explicit trusted-proxy allowlist (`trusted_proxy_cidrs`) instead of honoring arbitrary `X-Forwarded-For` from direct clients. If a request arrives from outside the trusted ranges, the app falls back to the direct peer IP and logs the proxy IP so operators can see which Docker bridge, reverse proxy, or local forwarding hop needs to be added.

This is what motivated the Redis addition in the first place. Once Redis was a dependency for rate limiting, it became the natural fit for PID tracking too (replacing the SQLite `active_procs` workaround).

### AI Assists: Private Provider, Worker, and Validation Boundary

**AI assists are an optional metadata layer, not an autonomous command runner.**

The feature was added to summarize completed run output and draft next commands, but several constraints shape the design:

- provider calls are disabled by default
- the provider contract is OpenAI-compatible chat completions rather than provider-specific APIs
- provider URLs are private by default and must resolve to loopback, private, link-local, or explicitly allowed CIDR ranges
- local llama.cpp support is a Compose profile, not a required runtime dependency
- slow model calls run in the dedicated AI worker instead of Gunicorn request workers or scheduler workers
- Redis coordinates write limits, enqueue locks, and global provider-call slots across processes
- model output is always treated as untrusted data

The worker split matters for local CPU models. A llama.cpp 8B model can take tens of seconds or more per request, especially after a cold start. If browser/API routes waited directly on those calls, ordinary app traffic would compete with model latency and Gunicorn worker capacity. The route path therefore validates the request, reuses cached completed assists when possible, writes a queued row, and returns quickly. The AI worker drains the queue, keeps a heartbeat, records progress, and marks assists completed or failed.

Redis is fail-closed for writes because the expensive part is shared infrastructure. Without Redis, multiple web or worker processes cannot reliably enforce per-session write quotas, global write limits, enqueue locks, or provider-call slots. Read-only cached assist listing can still be scoped by the database, but new provider work should not fan out blindly when coordination is unavailable.

The private-base-URL guard is intentionally conservative. The default use case is a local or self-hosted model near the app, where run output and redacted prompt context stay on infrastructure the operator controls. Hosted or public-compatible providers remain possible, but they require an explicit CIDR/config decision instead of happening accidentally because someone set `AI_BASE_URL`.

Suggestion validation sits outside the model. The model may propose only JSON, but the app still checks the command root, command policy, trusted target presence, known open ports for port-scoped suggestions, redaction sentinels, and a small denylist of known hallucinated flags. Accepted suggestions can be copied, and optional Run buttons still submit through the normal composer path so command policy gets the final say. Rejected suggestions are stored and displayed as blocked drafts because they are useful debugging evidence without becoming executable UI.

AI payloads are stored separately from transcripts, findings, Atlas source text, search text, and comparisons. This keeps assistant text additive and auditable while preserving the original command output as the source of truth.

### Durable Workflows: Server-Owned Steps and Bounded Captures

**Durable workflow progress belongs to the server, while each command remains a normal run.**

The original workflow runner queued rendered commands in one browser tab and advanced when that tab's status changed. That works for simple guided lists, but it can't reliably preserve branches, captures, cancellation, or progress after a reload. Explicit v2 and v3 definitions therefore compile into an immutable database snapshot with one state row per stable step id. The server claims and launches work through the existing run broker, then advances only after normal run finalization has saved the completed run.

This design deliberately reuses the command lifecycle instead of introducing a second executor. Every rendered step crosses the same command policy, secret, workspace, team-scope, runtime-readiness, output, finding, artifact, and project-link boundaries as a command typed at the prompt. The execution ledger adds orchestration context and a unique run-to-step link; it doesn't replace run history.

Template substitution is authoritative on the server and quotes each value as one shell scalar before policy validation. The renderer also produces a separate display command: sensitive inputs become `[redacted]`, and values captured by earlier steps become named placeholders. Only the raw command crosses validation and process launch; active-run metadata, saved History command text, logs, metrics, and notifications receive the display command. Captures observe normalized output with a small fixed selector set: eligible lines, structured entities, and JSON Pointer scalar values. Arbitrary expressions and regular expressions aren't accepted because they would add a second untrusted evaluation language and make runtime limits harder to guarantee. Captured values stay local to the execution and are omitted from workflow lifecycle logs.

Version 3 extends that boundary with bounded collection captures and one explicit `for_each` step policy. Collection values stay in the private execution record; child rows keep only stable ordinal, attempt, run link, status, and bounded outcome metadata. Every child is rendered just before launch and crosses the same command and owner checks as a scalar step. Parallel slots, retry count, failure count, and total captured items are fixed by validated limits. The editor presents those limits directly instead of accepting an opaque policy object, and the durable route returns only count-based progress. The execution UI derives its finished, pending, active, succeeded, failed, and skipped labels from that public summary rather than reading child rows.

Maintained collection playbooks prefer structured capture when the next command can consume one item directly. The bounded subdomain assessment therefore keeps its host collection private and avoids a temporary Files list, while its crawl and safe Nuclei stages carry explicit tool limits and exclusions. Files remain the right boundary when users need a durable artifact or a tool genuinely requires file input; they aren't the default workflow transport.

Exact-exit-code routing is part of the same editor contract as success and failure routing. Each code is a repeatable row with an integer and a stable destination ID, so users can see and remove every rule instead of carrying hidden definition state through saves. Step renames update those destination IDs, reordering leaves them unchanged, and deleting a destination keeps a visible invalid choice until the user repairs it. The compiler canonicalizes integer keys and rejects duplicates after canonicalization so values such as `2` and `02` can't create two rules for the same process result.

Durability also needs a bounded recovery rule. Web startup reconciles active execution rows after stale run metadata is cleaned up: it reclaims a step that never reached run binding, advances a linked run that was saved before the workflow hook completed, leaves a still-live broker run alone, and fails a vanished run instead of guessing. The same execution path rechecks the current team, initiating member permission, and initiating session token before every launch. Per-owner concurrency and wall-clock limits keep playbooks from becoming a second way around normal run controls.

Interactive PTY commands remain outside this model. Their completion depends on durable terminal-screen capture and input/replay state, not just a normal command exit and normalized line stream. The workflow launcher therefore detects registry-declared PTY trigger flags and fails that step before broker dispatch instead of silently running it through the wrong transport.

Execution events are derived from the durable execution and step rows rather than copied into another event table. Stable logical ordering gives clients a replay cursor for start, step, capture-name, and terminal changes while keeping commands and values out of the feed. Create, list, detail, and cancel routes project the private execution record into a fixed public status shape, so even an authorized team viewer doesn't receive stored inputs, variables, snapshots, tokens, actor context, or browser ownership hints. The same privacy boundary applies to workflow audit rows, lifecycle logs, and metric labels: they carry bounded ids, counts, status, timing, exit, transition, and failure-class fields only.

---

## Atlas Decisions

### Port Entity Identity and Evidence

**Ports are first-class Atlas entities, but their identity stays separate from host ownership.**

Port entities use canonical `host:port/proto` values, with IPv6 hosts bracketed as `[2001:db8::1]:443/tcp`. Keeping the host text in the canonical value makes imported and transcript-captured ports stable before any database lookup is available. The linked `host_entity_id` is stored separately when materialization can resolve it, so Atlas can join the port back to the host without making the canonical value depend on a mutable database id.

TCP is the default protocol when a parser or import omits one, and TCP/UDP are the supported protocol values. Service, version, and banner details live in lightweight attributes because they describe the observation, not the entity identity.

Ports do not offer provider intel refresh. They are app-captured scan evidence from command output, while provider-backed domains, IPs, URLs, hashes, and CVEs can ask external or configured providers for fresh data. Project Overview keeps that distinction visible: app-captured port evidence can show that a run saw a port, while scan target observations from supported scanners can show that a target was scanned even when no app-captured ports surfaced.

### URL Entity Host Links

**URL entities reuse the host relationship instead of introducing a URL-only link.**

URL entities belong to a host in the same way port entities do, so they use the existing `host_entity_id` field. The relationship points at the scoped `domain` or `ip` entity derived from the canonical URL host. That keeps the URL canonical value stable and readable while letting Atlas and Project Overview roll URL evidence up through the host.

### Quick Lookup Reuses the Atlas Surface

**Quick Lookup is an Atlas mode, not a separate modal.**

Quick Lookup has its own input and result root because finding one exact saved value is different from browsing a filtered Atlas list. Once it finds an entity, however, the user needs the same Overview, Evidence, Findings, Intel, relationship navigation, paging, and return behavior as an ordinary focused Atlas profile. Keeping those paths in one overlay and renderer prevents profile content and actions from drifting.

A second modal would also duplicate the scrim, focus trap, mobile sheet, close behavior, and related-entity stack. The browser therefore enters `data-atlas-mode="lookup"` on the existing Atlas surface and transitions into normal Atlas browsing only through **Open in Atlas**. The exact read route remains separate so it can validate and scope the submitted value without loading Atlas lists or placing URL paths and queries in browser history.

---

## Assessment Decisions

### Assessment Delivery and Runtime Ownership

**CVE risk intelligence ships first, followed by a thin, complete assessment workspace slice.**

The public EPSS and CISA KEV data path is useful without the assessment workspace, so it lands independently before assessment schema and routes depend on it. The first workspace release then carries the Network and Web profiles through cycle creation, evidence matching, API, desktop, and mobile. Network, Web, API, TLS, and Combined profiles share one schema from the start, but the remaining profiles and scanner integrations do not block validation of that first end-to-end slice.

The scheduler owns database-backed feed refresh jobs, leases, and resumable risk-escalation work. Notification workers deliver queued notifications but do not own durable refresh or escalation state, and Redis is not required to preserve either workflow. Optional ZAP, private OAST, and Greenbone systems stay outside the primary image. ZAP has a disabled-by-default operator configuration boundary: its API origin can't carry credentials or a request path, its key comes from an environment reference, every target must resolve inside an explicit CIDR, and concurrency, runtime, TLS, and report-size choices are fixed before any connector call. Its Automation Framework documents are generated locally for review. Safe policy is passive and doesn't submit forms; active scanning requires the separate intrusive-action gate. Protected HTTP profile material isn't written into plans. Reading settings or generating a plan doesn't submit work.

ZAP lifecycle state belongs in the primary database rather than Redis or an in-memory worker. It keeps the owner and reviewed identities, status, fixed deadline, remote plan id, a bounded progress summary, and sanitized report/import metadata. Guarded transitions distinguish cancel intent from remote confirmation and downloaded output from an operator-reviewed import. Plan documents, credentials, report bodies, and full remote logs do not belong in that row.

### Shared CVE Risk Data and Ranking

**A fresh install gets dated, bundled EPSS and KEV data; live network refresh remains an operator choice.**

Each release may carry checked, release-pinned EPSS and CISA KEV snapshots after their redistribution terms, attribution, checksum, and image impact are reviewed. Importing that bundle establishes a silent baseline: it can rank existing CVEs, but it cannot create historical escalation events. The product clearly labels the bundle's age and explains how to enable inventory-neutral live feed updates. Outbound refresh is disabled until the operator enables it.

Normalized NVD CVE advisory storage is independently operator-selectable. Local mode accepts a bounded operator-managed NVD 2.0 JSON file; external mode retains results only from an explicit, capability-checked Atlas CVE Intel refresh. Neither mode sends product inventory, and a CVE advisory alone does not establish product applicability. OSV package matching and NVD CPE/applicability correlation remain separate opt-ins for exact package or defensible CPE identities. An external OSV request sends one exact PURL and version to the fixed allowlisted OSV endpoint only after an explicit acquisition action; it never uploads an SBOM or discovered package inventory, and no assessment, finding, Atlas, Project, or report read can start it.

FIRST, CISA, and NIST source URLs, publication and retrieval dates, model or catalog versions, checksums where applicable, notices, and stable attribution text stay with accepted data and generated reports. Attribution never implies provider endorsement.

The shared fix-first order is explainable: KEV-listed remediation groups first, then EPSS probability and percentile, then CVSS, with finding age as the final stable tie-breaker. Owner-scoped Vulners references remain context and do not change that shared order. A public-exploit signal may become a shared tie-breaker only if an Exploit-DB/SearchSploit dataset is approved and deployed consistently.

Risk escalation always records a new KEV listing for an open remediation group. EPSS escalation activates when probability crosses upward through `0.10`, stays active while the score moves near that boundary, and rearms only after it falls below `0.08`; operators may change both values, but reset must remain below activation. NVD withdrawal, rejection, dispute, and reinstatement remain explicit history, as does a CVSS decrease of at least 1.0 point by default. Operators may change that material-downgrade threshold. Every NVD change keeps both source versions, the first accepted record is silent, model-version crossings stay labeled, and Project digest delivery is opt-in.

### Assessment History, Evidence, and Finding Identity

**Assessment definitions and completed evidence remain reproducible.**

Shipped assessment profiles are immutable, versioned definitions. Local configuration may add a profile or replace a complete profile version by stable key, but it cannot partially merge individual checks. Cycles use `active`, `completed`, and `archived`: completion freezes profile, scope, checks, manual exclusions, and evidence links; archiving changes visibility only; restarting creates a new cycle. Only archived cycles may be hard-deleted, after a dependency preview, and deleting a cycle never deletes its source runs, findings, entities, or artifacts.

Targets retain owner scope, their Project target or entity reference, canonical type and value hash, plus a bounded display snapshot already visible in that Project. They never copy credentials, protected HTTP context, workflow variables, or unrelated discoveries. Every profile check declares accepted evidence kinds, action families, target matching, completion requirements, compatible versions, and whether negative evidence is meaningful. Evidence links store the rule and version that matched; generic Project links and command prefixes do not prove coverage.

Finding observations use owner, affected subject, stable rule, normalized vulnerability, and validation method in their fingerprints. Active confirmation, version inference, imported assertion, and manual assessment stay as separate observations. A remediation identity excludes validation method, so fix-first worklists and headline rollups count one normalized vulnerability against one affected subject once and expand its individual methods only in detail views. Review state and remediation guidance follow that shared identity, while verification steps, status, and notes stay with each observation. Mismatched subjects or vulnerability identities require an explicit human merge.

Project handoff surfaces use one preferred finding-change cycle: the active cycle when one exists, otherwise the newest completed cycle. Overview and Findings show its remediation-level rollup and link back to that exact cycle. Evidence packages and reports filter the same stored comparison to the remediation identities represented by their selected findings, then preserve current and earlier finding/evidence references plus comparison reasons. Archived cycles stay available in Assessment history but don't silently replace the current handoff summary.

That merge never rewrites the exact identities. It records their membership in one owner-scoped logical remediation group only after an assessor searches, previews the affected observations, and confirms the action. The selected target group wins any existing review state and guidance so conflict handling is visible before apply. Ranking and rollups count the logical group once, while evidence, validation, confidence, verification, suppression, and occurrence history continue to belong to their original observations.

Supporting finding evidence uses explicit typed references rather than copying another source record. Runs, zero-based run lines with bounded snippets, run output, run-owned workspace artifacts and screenshots, Atlas entities, curated Project targets, assessment checks, and retest runs must resolve inside the active owner and Project before they can be linked. The exact finding, type, source id, and line form the idempotent identity. If the source later disappears, the link and safe source id remain as unavailable evidence; packages preserve the same typed reference, while full transcripts and artifact bodies remain authoritative in their original stores.

Retest compatibility is an explanation, not a disposition. A Project run is comparable only when it satisfies the originating check's frozen target, tool, completion, version, and output rules, or the original run's tool and affected target when no assessment check exists. Profile drift and missing evidence remain visible, and an assessor may still keep an incomparable run as supporting evidence after a warning. Only an authorized person can save a final verification state; that decision keeps its time and privacy-safe actor independently of later note edits.

Cross-cycle finding change is stored against the newest earlier cycle with the same frozen check key and target hash, and it is comparable only when both checks have available evidence from the same rule and version. The comparison counts each remediation identity once while retaining its individual finding observations on both sides. An earlier issue may be called `not_observed` only when the current rule explicitly supports a clean negative result. Missing, partial, failed, changed, deleted, or otherwise incompatible evidence stays incomparable. `Fixed` remains a human verification disposition; the cycle comparison uses `regressed` only when compatible current evidence observes a remediation group that an authorized person previously verified.

Assessor-authored findings get an opaque identity when they're created, and that identity never depends on editable title, severity, or detail text. Their Project target is immutable. Same-target title matches or shared CVEs are warnings rather than automatic merges: the caller must explicitly keep the duplicate, while optimistic revisions prevent an older editor from overwriting newer work. Private creator/editor session references stay in storage for audit and token migration, but responses expose only safe team-member context. This keeps manual observations stable without pretending that a wording match proves two findings are the same issue.

### Assessment Execution, Secrets, and Packaging

**Policy labels have the same behavior on every launch surface.**

Safe actions use the normal launch confirmation. Standard actions disclose target, fan-out, request, time, and credential bounds. Intrusive actions require operator enablement and per-launch confirmation. Destructive actions are unavailable from assessment recommendations, workflows, API, and CLI.

#### Nuclei Recommendations Use Reviewed Template Profiles

**Generic Nuclei checks use fixed safe, standard, or intrusive profiles instead of an open-ended template selection.**

The frozen Assessment policy selects the profile. Safe covers high and critical exposure, misconfiguration, technology, and TLS checks. Standard adds medium-severity known-CVE, network-service, and API checks. Both exclude intrusive, callback, code, local-file, workflow, headless, fuzzing, brute-force, denial-of-service, and exploit templates. The intrusive profile is separately gated and limited to reviewed headless and low-aggression DAST checks. All profiles disable redirects, Interactsh, and automatic template updates.

The confirmation shows the profile, included families, exclusions, explicit-only update policy, and the installed managed-cache manifest's recorded release, SHA-256 revision, and entry count before the operator starts the run. The app reads that local manifest through fixed byte and entry limits and never contacts ProjectDiscovery during preview. Missing or invalid manifests make the plan unavailable, and launch rejects any snapshot that changed after confirmation. The operator must run `nuclei -update-templates` explicitly and review a fresh plan; opening or refreshing an Assessment never updates templates. Safe, standard, and intrusive profiles have different exact evidence modes so one profile's successful clean run can't complete another profile's check. Unknown profile names fail closed to safe. The dedicated subdomain-takeover check remains a separate digest-pinned one-template contract.

`assessment_intrusive_actions_enabled` is the deployment gate and defaults to `false`. It is a necessary condition, not an authorization bypass: each maintained intrusive plan still has to prove its exact frozen check, Project target, source evidence, bounds, and fresh confirmation immediately before execution. The ordinary command registry remains on its existing policy, and destructive actions have no launch path even when the gate is enabled.

A finding can repeat its saved assessment command only from a freshly recomputed plan tied to the exact originating check and still-confirmed Project target. The operator sees the command, target, policy, Project-only fan-out, request/time bounds, and credential use before confirming the plan digest. This path accepts maintained safe and standard command templates only; it rejects workflows, unsupported commands, stale plans, archived context, and intrusive or destructive policy. The resulting run stays linked to the Project, and neither launch nor completion changes the finding's human verification disposition.

Protected HTTP context uses a reviewed per-tool adapter. It prefers stdin or a tool-native credential channel, then private per-run files in a `0700` directory with `0600` permissions, and uses environment injection only when no safer supported option exists. Secret values never enter argument lists, persisted commands, workflow state, or reusable scanner configuration.

Curl receives request headers and client-certificate paths through a short-lived, escaped config file and runs one HEAD request with ambient config, proxies, and redirects disabled. HTTPx and Nuclei receive request credentials through a short-lived ProjectDiscovery secrets file, Katana receives a short-lived header file, and Dalfox receives a short-lived JSON config containing protected headers with redirects disabled. Dalfox is limited to one target and parameter discovery with active XSS payloads and remote dictionaries disabled. Nuclei client certificates and keys are copied into the same private run directory. The launch rechecks the profile revision, exact Project target, permissions, Secret and Files availability, and supported feature set immediately before execution. Redirect broadening, proxy use without an allowlist, login/token-capture workflows, and unsupported client-certificate combinations fail closed. The run worker removes private material on completion or start failure, and startup recovery removes abandoned directories without placing protected values or paths in user-visible records.

The Project editor stores references, not credential values. Secret creation and replacement stay in Options → Secrets, while Assessment shows only referenced names and availability to members with `MANAGE_SECRETS`; other readers receive counts. Choosing an authenticated role is a separate step before the redacted plan confirmation. Disabled profiles and references known to be missing can't be selected. If a provider rejects a value that it considers expired, the run fails normally and the operator can replace that named Secret without rewriting the profile.

Quota and retention defaults come from measured small, medium, and large Projects. Reaching a hard limit rejects new work clearly instead of evicting assessment history. HTTPx screenshot output uses the existing per-owner Files count, per-file, and total-byte budgets: finalization retains new event-named images in order and removes the excess rather than deleting earlier files. Completed cycles stay until explicit deletion; rebuildable feed caches, acknowledged escalation events, temporary HTTP material, and connector callbacks follow documented retention policies.

The maintained Live Web Review workflow uses Files only for HTTPx's screenshot directory. Dalfox parameter discovery streams structured JSONL through the normal run evidence path, so the playbook doesn't create a transfer file or duplicate captured parameter values in workflow state.

The maintained Port Service Review workflow keeps generic orchestration to one host, one TCP port, connect mode, and Nmap's reviewed `default` selector. A matching fingerprint can unlock a deeper fixed protocol profile only through the existing Assessment recommendation and confirmation flow. Schemathesis keeps the stricter side of the same boundary: its Project-linked schema, reviewed operation set, and private execution material never become generic workflow inputs.

The primary image has an approved compressed-size and cold-start budget. Small, pinned, multi-architecture tools required by maintained profiles may ship in it; protocol client packs and service stacks remain optional and operator-managed. Dalfox uses checksum-pinned Linux AMD64 and ARM64 musl release archives, keeps its reviewed MIT notice at a durable runtime path, and is covered by the normal bundled-tool smoke contract. Schemathesis uses a fully exact-pinned virtual environment that is built and checked separately from the app's Python dependencies, copied into the runtime without pip or bytecode caches, and covered by the same smoke and license gates. Its maintained API profile starts from one unchanged Project-linked OpenAPI JSON artifact chosen by opaque id; preview and launch recheck its saved size and digest before it enters private scanner storage. The visible plan names the operation count and fixed bounds, while a typed internal execution value supplies private schema, cache-disabled configuration, and report paths after the ordinary carrier command passes validation. The finished report crosses back through a bounded no-follow read before cleanup. Schemathesis's findings exit is accepted only when that typed reader returns a complete bounded report with a reviewed failure; incomplete or missing reports and all other exit codes retain their normal meaning. A completed reviewed report is stored once with exact Project, cycle, check, schema, profile, tool, target, and run provenance. Its operation rows keep only bounded counts, response statuses, parameter names, and proof digests. Reviewed failures create separate active-confirmation findings and count as needs-review evidence. A clean report counts as coverage only when its successful operation set exactly matches the unchanged schema; incomplete clean output doesn't imply a negative result. Remote references and server-scope changes are rejected, and generation is limited to read-only operations. Remote schemas, YAML, GraphQL, HTTP-profile injection, and write-operation testing have no maintained execution contract. A tool that exceeds the budget requires a separate packaging decision.

---

## Backend Architecture Decisions

### Pytest Feedback Uses Exact Serial Partitions

**The complete backend suite stays serial, while CI runs two required selections concurrently.**

`npm run test:pytest` remains the canonical pre-merge and release command. CI selects ordinary backend coverage with `not release_integration` and slower installer, publication, signing, and backup/restore boundaries with `release_integration`. A collection guard compares node IDs from both selections with the complete suite, so a misplaced marker can't silently drop or duplicate coverage. Each lane publishes its own JUnit report, slowest-case output, and file-level timing summary.

Stable route modules can opt into one reusable Flask app, but every test still gets a new client and mutable Flask config is restored around each case. Factory behavior, construction-time configuration, extension isolation, logging, imports, and tests that need independent applications continue to call the fresh app helper. This keeps the common HTTP path cheap without changing the factory contract the suite is meant to protect.

`pytest-xdist` isn't used for the backend suite. The current tests intentionally exercise process-wide config, logging, SQLite paths, Redis stand-ins, generated files, and local servers. Isolating all of those per worker would add more machinery than the measured runner capacity justifies, while the exact two-lane split provides earlier feedback without introducing worker-only failures. Parallel workers can be reconsidered if those shared boundaries become independently namespaced and repeated measurements show a worthwhile gain.

### Blueprint Parent Modules and Size Ratchets

**Parent blueprint modules stay as stable registration surfaces while route groups live in focused sibling modules.**

The app factory imports the parent blueprint modules, so those modules keep the public `Blueprint` object and define it before importing route-group siblings. The sibling modules register their routes by importing that parent blueprint. That import side effect is allowed only for route assembly: importing a route module should not start workers, open databases, spawn processes, or perform runtime maintenance.

This pattern keeps Flask registration stable for `app.create_app()` while letting large route surfaces such as runs, projects, API v1, Atlas, and diagnostics split by resource group. It also preserves compatibility imports and monkeypatch seams during refactors, so tests and callers do not have to chase every internal move.

Services split on real responsibility boundaries rather than line count alone. Query reads, payload shaping, lifecycle orchestration, settings/defaults, import/export helpers, and low-level process helpers can live in focused siblings when that makes ownership clearer. Cohesive artifacts such as generated schema baselines or the OpenAPI source dictionary stay whole because splitting them would make review harder, not easier.

The size ratchet in `tests/py/test_architecture.py` records that intent. Split files and cohesive ratchet-only files cannot quietly grow past their current baseline, and every file in the decomposed families must have an explicit budget entry. The route contract and import-compatibility tests make the same point from another angle: decomposition is allowed to move code, but it is not allowed to change user-visible routes or supported parent import surfaces by accident.

### Mutable Runtime State Uses Source-Owner Accessors

**Split services read mutable runtime state from the source owner instead of copying global objects at import time.**

The core modules still own the process-wide state: `config.py` owns the loaded config, `core.database` owns database backend and connection setup, and `core.process` owns Redis/process state. The refactor does not remove those owners. It removes the unsafe pattern where split services copied `CFG`, `DB_BACKEND`, `db_connect`, or `redis_client` into their own module globals and then silently missed later app-factory, worker, or test replacement.

The chosen shape is deliberately small:

- database state goes through `core.database_access.get_db_backend()` and `core.database_access.get_db_connect()`
- Redis state goes through the shared `core.process.RedisClientProxy` compatibility path
- config reads use `config.resolve_effective_cfg(cfg=None)` or an explicit `cfg` argument when the caller already owns scoped config

That design keeps the existing runtime owners intact while making reads late-bound. It also keeps tests honest: patches belong on `core.database.DB_BACKEND`, `core.database.db_connect`, `core.process.redis_client`, or `config.CFG`, not on child-module aliases that production code no longer reads.

Removing the core owners outright would be a much larger settings/runtime-container rewrite and would not solve the immediate stale-binding problem by itself. Copying source globals down into child modules was simpler in the short term, but it made split modules fragile under Postgres route tests, worker bootstrap, app-factory replacement, and runtime Redis initialization. The accessor/proxy layer is the smallest durable boundary that fixes those seams without changing the app's public module surfaces.

The architecture suite enforces this decision. It keeps an explicit compatibility baseline for older route-level `CFG` imports, blocks new local service-module singleton bindings, catches alias-style rebinding such as `db_connect = database.db_connect`, and flags module-qualified stale config reads such as `database.CFG`. If a future change needs to expand that baseline, the test failure should be treated as a design review prompt, not just a lint cleanup.

---

## Security and Isolation Decisions

### Cross-User Process Killing

**Problem:** Gunicorn runs as `appuser`, commands run as `scanner`. Linux won't let `appuser` signal `scanner`-owned processes.

**Solution:** `sudo -u scanner kill -TERM -<pgid>`. The sudoers rule `appuser ALL=(scanner) NOPASSWD: ALL` covers this. The kill sends to the entire process group (negative pgid) to catch child processes spawned by the shell.

**PGID capture timing:** The `/kill` endpoint stores the subprocess PID at spawn time and uses it directly as the PGID (`pgid = pid`) rather than calling `os.getpgid(pid)` at kill time. Since all subprocesses are spawned with `preexec_fn=os.setsid`, PGID equals PID at creation, making the stored PID a safe stand-in. The alternative — calling `os.getpgid()` after `proc.wait()` has reaped the process — returns the PGID of whatever new process reused that PID. If that new process is a freshly spawned Gunicorn worker (workers and scanner subprocesses draw from the same kernel PID pool), `kill -TERM -<worker_pgid>` sends SIGTERM to the entire Gunicorn worker pool.

### Two-User Security Model

**The container runs two unprivileged users: `appuser` for the web process and `scanner` for all user-submitted commands.**

- **`appuser`** — runs Gunicorn, owns `/data` (chmod 700), can write SQLite
- **`scanner`** — runs all user-submitted commands via `sudo -u scanner env HOME=/tmp`, no write access to `/data`

`HOME=/tmp` is critical. Without it, `sudo` resets HOME to `/home/scanner` which doesn't exist on the read-only filesystem. Tools like nuclei and subfinder write to `$HOME` at startup and will fail with "read-only filesystem" errors without this.

### Path Blocking (/data and /tmp)

**Filesystem path references to `/data` and `/tmp` are blocked at validation time using a regex with a negative lookbehind.**

The regex is `(?<![\w:/])/data\b` (and `/tmp`). The negative lookbehind `(?<![\w:/])` prevents false positives on URLs — `https://darklab.sh/data/` won't match because the `/data` segment is immediately preceded by `m` (the last character of `darklab.sh`), which satisfies `\w` in the lookbehind.

Blocking happens at two layers: client-side (immediate feedback) and server-side (authoritative). Internal rewrites (for example `nuclei -ud /tmp/nuclei-templates` and ProjectDiscovery `XDG_CONFIG_HOME` wrappers) are injected by `rewrite_command()` after command validation, so app-owned runtime tokens can point at trusted internal paths without exposing arbitrary `/tmp` input to users.

### Workspace Shell Conveniences Stay App-Mediated

**Workspace file convenience should feel shell-like without becoming shell filesystem access.**

The Files feature supports copy, touch, move/rename, simple `*` patterns, and constrained output capture in common terminal flows. Those features deliberately live in the app layer instead of relying on `/bin/sh`, host filesystem commands, shell glob expansion, or raw redirection.

The decision is:

- `file move` / `mv`, drag-and-drop, and the Files-row move action all use the shared workspace helpers
- `file copy` / `cp` copies one regular file without following links or replacing an existing destination
- `file touch` / `touch` creates an empty file or refreshes its modified time without truncating existing content
- `*` patterns match within one path segment only and are expanded against the active session workspace listing
- moving multiple matches requires the destination to already be a folder
- final `command > file` and `command | tee file` sinks overwrite through the workspace store after output filtering and secret redaction, while final `command >> file` appends through the same boundary; all other redirection remains blocked
- attached file-descriptor forms such as `2>` and `2>>` fail closed before tokenization, existing directory destinations fail before execution, and sink write failures force a nonzero run result without exposing internal workspace paths in the terminal
- deletes still require the transcript-owned confirmation flow, and folders still require `-r` / `-rf`
- backend built-ins mirror the browser behavior so stale clients and server-rendered command paths do not get a different filesystem model

This keeps the feature predictable for users while preserving the security boundary: every source and destination still goes through session-root validation, symlink rejection, traversal checks, overwrite checks, and the same group-permission model used for command-created files.

### Loopback Address Blocking

**Loopback addresses are blocked at validation time to prevent commands from reaching internal Flask endpoints.**

Commands containing loopback addresses (`localhost`, `127.0.0.1`, `0.0.0.0`, `[::1]`) anywhere in the command string are blocked by `_LOOPBACK_RE` in `commands.py`. The regex uses word-boundary anchors (`\b`) so hostnames like `notlocalhost.com` are not caught.

**Why this matters:** the web shell runs commands as the `scanner` user inside the container. Without this block, a user could submit `curl http://localhost:8888/diag` or `curl 127.0.0.1:8888/config` as a command and reach internal Flask endpoints directly. This is not prevented by the `/diag` CIDR gate alone, since connections from inside the container arrive as `127.0.0.1` and would pass any gate that includes that address.

Three complementary layers enforce the restriction:

1. **Server-side regex** (`commands.py` `_is_command_allowed`) — authoritative; catches any tool and any URL form (bare hostname, with port, with scheme, etc.)
2. **Command registry deny entries** (`app/conf/commands.yaml` `policy.deny`) — client-side feedback for the most obvious bare-hostname patterns (`curl localhost`, `curl 127.0.0.1`, etc.)
3. **iptables rule** (`entrypoint.sh`) — OS-level TCP block for the `scanner` uid on the app port; fires before the Flask app sees the request and covers tools that bypass command validation (e.g. scripting languages)

The iptables rule is added by `entrypoint.sh` as root before the `gosu` drop. It uses `REJECT --reject-with tcp-reset` so connections from the scanner user fail immediately rather than timing out. The `|| true` ensures the rule failure does not abort startup in environments where `xt_owner` is unavailable.

### Session Token Security

**Five non-obvious constraints in the session token design:**

**1. `/session/migrate` requires `from_session_id == X-Session-ID`**

The migrate endpoint accepts `from_session_id` and `to_session_id` in the POST body. Without the header check, any client that knew another user's session ID could call `/session/migrate` with `from_session_id=<victim>` and redirect the victim's run history and workspace files to their own token. The `X-Session-ID` header is the requester's current identity — enforcing that it matches `from_session_id` means you can only migrate *your own* session.

**2. `SESSION_ID` must not be updated until after `/session/migrate` completes during rotate, and the switch is gated on migration success**

`session-token rotate` must call `/session/migrate` with `X-Session-ID: <old id>` before calling `updateSessionId(<new token>)`. If `SESSION_ID` were updated first, the migrate request would carry the new token as `X-Session-ID`, which would fail the `from_session_id == X-Session-ID` check (since `from_session_id` is the old ID). The `_doSessionMigration` helper therefore calls `fetch()` directly with an explicit `X-Session-ID` override rather than going through `apiFetch()`, which always uses the current `SESSION_ID`.

Critically, the identity switch (`localStorage.setItem` + `updateSessionId`) only happens if migration succeeds. A failed migration aborts rotate and leaves the old token active — otherwise a transient network failure would strand the user on a fresh token with their history or Files workspace still on the old session.

**3. Other open tabs are kept in sync via the `storage` event**

The `storage` event fires in every same-origin tab that did NOT make the change. `session.js` registers a listener that calls `SESSION_ID = e.newValue || _sessionUuid` when `e.key === 'session_token'`. This means tabs that are already open pick up a token change immediately without a reload — they won't keep sending a stale `X-Session-ID` after another tab runs `session-token set/clear/rotate`. The listener intentionally does not call `updateSessionId()` (which reads back from `localStorage`) because `e.newValue` already carries the new value directly, and `localStorage` reads in another tab may not yet reflect the change on some browsers.

Header sync alone is not sufficient, though. Passive tabs also need to refresh session-scoped UI such as recent-command chips, server-backed starred state, history results, saved Options state, and the options-panel token status. The current listener therefore also calls `reloadSessionHistory()`, `loadSessionPreferences()`, and `_updateOptionsSessionTokenStatus()` when those helpers are present, so visible UI follows the new session identity instead of lagging behind it.

**4. Session-token subcommands are intercepted client-side; bare `session-token` is not**

`generate`, `set`, `copy`, `clear`, `rotate`, `list`, and `revoke` are intercepted in `submitCommand()` after `addToHistory()` and never reach the server. This keeps sensitive token values out of the server command log. Bare `session-token` (status only) passes to the server as a normal bulit-in command so the server-side rendering path handles the output consistently with other status commands. The intercept check is `cmd.trim().toLowerCase().startsWith('session-token ')` — the trailing space ensures it only fires when a subcommand is present. Token-bearing local history entries are masked before storage so the local history/recents surfaces stay useful without echoing raw token values.

**5. Revocation is enforced at the API layer, not just client-side**

`session-token revoke` deletes the token row from `session_tokens`. But that alone is not enough — any client still holding the token string could keep sending it as `X-Session-ID` and get data back, because the old data routes trusted any header value unconditionally. `get_session_id()` in `helpers.py` now looks up every `tok_`-prefixed header value against `session_tokens` on each request. A revoked or never-issued token returns `""` (anonymous), so the caller immediately loses access to session-scoped runs, snapshots, and stars — no client-side coopertion required. The DB lookup adds a single indexed read per request; the `session_tokens` table is small and hit-rate is high, so the overhead is negligible.

### Team Ownership: Session Tokens Stay Actors

**Team mode uses hybrid ownership instead of replacing session identity.**

The app already has durable `tok_` session tokens that own personal history, workspaces, preferences, secrets, and command attribution. Team mode keeps that identity model: a token still represents the operator taking an action, while `team_id` marks records that belong to a shared team scope.

This avoids a disruptive rewrite of every `session_id` path into a new abstract owner table. Existing personal installs keep working as personal scopes, and team-owned surfaces can become shared one at a time by adding nullable `team_id` columns and using the shared scope helpers. Those helpers return the right query predicate for the current request: personal scope filters by the acting token, and team scope filters by the selected team plus membership and capability checks.

The tradeoff is that shared surfaces need to opt in deliberately. A table is not team-owned just because a member created a row; it becomes team-owned only when the route, service, and migration add `team_id` ownership and tests for personal/team isolation. That is intentional. It keeps the security boundary easy to audit, avoids silently moving personal data into a team, and preserves historical attribution even after members leave.

Active scope is request-local. The browser stores the selected team per token and sends it with API calls, while API and CLI callers pass an explicit team id by header, flag, environment variable, or local CLI config. Switching scope never re-homes in-flight runs, queued jobs, schedules, package builds, AI assists, or unsent notifications; those records keep the scope captured when they were created.

### Scheduled Runs Worker And Audit Model

**Scheduled runs fire from a dedicated worker, not from Flask request handlers.**

The scheduler is a Gunicorn-sibling process supervised by `entrypoint.sh`. It stays outside Flask workers so time-based firing is not tied to browser traffic, request lifetimes, or the number of web workers currently serving users. Manual **Run now** is the exception: it fires directly from the operator's request because it is an on-demand action and should not depend on the background worker being healthy.

Only one scheduler worker should fire due rows for a deployment. Postgres uses the reserved `darklab_shell_scheduler` advisory lock, while SQLite uses a filesystem lock under the app data directory unless `scheduler.lock_path` overrides it. Extra workers that cannot take the lock exit cleanly and let the supervisor retry.

Normal schedules and watcher-owned schedules share the physical `schedules` table. The ownership fields (`owner_kind`, `owner_id`, and `session_token`) keep the behavior explicit: browser/API/CLI schedule lists expose only normal user-owned schedules, while watcher-owned cadence rows stay tied to watcher state and cannot be edited as ordinary command schedules.

The firing policy is deliberately conservative:

- schedules require durable `tok_` sessions so revocation can stop later fires
- strict five-field cron and a five-minute minimum custom interval prevent accidental rapid loops
- missed fires are coalesced on worker startup instead of replaying every skipped interval
- overlap policy is stored as `skip` and enforced by recording an audit row instead of starting another copy while the previous scheduled run is still active
- every fire attempt writes `schedule_fires`, so History, Run Details, API clients, and operators can trace why a due schedule fired, skipped, or failed

### Deny Flag Matching (anywhere in command)

**Deny entries match denied flags anywhere in the command, not just as a command prefix.**

Allow-listed tools can have specific flags blocked through `policy.deny` entries in `app/conf/commands.yaml`. Early implementations only matched the deny entry as a prefix of the command — `curl -o` would catch `curl -o /tmp/out` but not `curl -s -o /tmp/out` where other flags precede the denied one.

`_is_denied()` tokenizes both the incoming command and the deny entry using the shared `split_command_argv` helper. Tool names and subcommand prefixes are compared case-insensitively; flags are compared with exact case, so `curl -K` (disable TLS verification, uppercase) does not fire on `curl -k` (lowercase). For short combined flags (`-sU`), `_flag_matches_token` checks whether the denied flag letter appears within the token, so `nmap -sU` catches `-sU`, `-UsT`, and other combinations. The tool prefix must still match first, so `gobuster dir -o` only fires for `gobuster dir` subcommand invocations, not `gobuster dns`.

**`/dev/null` exception:** a denied output flag is allowed when its argument is `/dev/null` (e.g. `curl -o /dev/null -s -w "%{http_code}" <url>`). This is a common pattern for checking HTTP response codes without writing to the filesystem. The exception checks for `flag /dev/null\b` immediately after the flag match.

---

## Deployment and Packaging Decisions

### Two Supported Runtime Contracts

**darklab_shell supports a production installation and a development environment, with no checkout-based production mode.**

Production starts from a versioned release installer, runs the published image with the installed `compose.yaml`, keeps operator state beside that file, and uses `darklab-deploy` for lifecycle work. Development starts from a source checkout, uses `compose.dev.yaml` or the local Python helper, and may invoke internal scripts directly while changing or testing the app. A source checkout isn't an operator deployment interface, and development conveniences aren't production compatibility promises.

The old layered production override and checkout migration instructions were removed rather than kept as a legacy support tier. The project was still pre-release while those paths existed, and maintaining two production models would make install, backup, upgrade, security, and troubleshooting guidance ambiguous. “Production installation” is the user-facing name; “managed” is reserved for the release-owned files and lifecycle boundary where that distinction matters.

### Deployment Environment and YAML Fine-Tuning

**Settings that coordinate the container or deployment live in `.env`; application-only tuning lives in `config.local.yaml`.**

Files enablement/storage, database selection and DSN, interactive PTY enablement, restricted target CIDRs, raw-packet scanning, the Prometheus multiprocess directory, and core AI provider/features affect more than one process or lifecycle tool. Their uppercase environment variables are the supported operator surface so Compose, the entrypoint, backup/restore, migration, workers, and the web app can't disagree. The lowercase effective keys remain internal runtime state, but the shipped YAML reference doesn't present them as operator options.

Files quotas, PTY limits, database pool/JIT behavior, AI timeouts and queue/rate/output/network limits, retention, notifications, and UI behavior are application-only tuning and remain in `config.local.yaml`. Environment overrides for database and AI tuning remain available to process-managed deployments, but shipped Compose files pass them as empty unless the operator sets them; the loader ignores those empty values so they don't silently shadow YAML.

### Network Copyleft with GNU AGPLv3

**darklab_shell's original source code and documentation use `AGPL-3.0-only`.**

MIT was considered because it is short and easy to adopt, but it would allow a proprietary fork to reuse the project without sharing its changes. GPLv3 would keep distributed derivatives under the GPL, but darklab_shell is mainly a network application: a modified hosted version could be used without distributing the program and therefore without returning its source. AGPLv3 adds the network source offer that matches the project goal.

The license does not prohibit commercial use. Companies can run, host, support, and sell services around darklab_shell under the same terms. The boundary is openness, not payment: a modified network version must prominently offer every remote user its complete Corresponding Source at no charge through a standard or customary copying method. A noncommercial restriction was rejected because it would conflict with the project's open-source goals and make ordinary organizational use unclear. The complete `LICENSE` text controls.

Official releases expose their matching source tag through the built-in **What is this?** FAQ entry, record `AGPL-3.0-only` in package and OCI metadata, and carry the complete license in the image and installer payload. That FAQ entry is the official build's default source link, not a declaration that one placement satisfies every modified service. Modified deployments must replace the official link and remain responsible for making their offer prominent to all remote users and providing their complete corresponding source at no charge. Bundled tools, libraries, fonts, and wordlists are not relicensed; their separate terms stay in `THIRD_PARTY_NOTICES.txt` and `container-licenses.json`.

The bundled Debian Nmap package remains under NPSL 0.95. darklab_shell runs its executable as an external command and parses the resulting output; releases include the hash-pinned NPSL text, list Nmap in the third-party inventory and notices, and identify and link to the Nmap Security Scanner in the built-in FAQ. The project owner reviewed those terms and chose to distribute Nmap with this open-source application without making an upstream waiver, OEM license, or separate legal-approval record a release prerequisite. CI verifies the declared license, notice, and bundled text, but it does not enforce a separate redistribution-approval status. This packaging decision does not relicense Nmap or change the NPSL terms.

Project-owned source uses short, machine-readable `SPDX-FileCopyrightText` and `SPDX-License-Identifier` notices instead of repeating the full multi-paragraph AGPL boilerplate in every file. This keeps the license attached when a file is copied without burying the source under legal text. Generated bundles and third-party material are explicitly excluded from the project header, and the lint guard fails when new project-owned source has no notice. The root `LICENSE` is the single full-text copy; a second `LICENSES/AGPL-3.0-only.txt` copy and a formal REUSE-compliance claim were deliberately left out.

### One Image, Two Compose Modes, and Dual Registry Publishing

**Released images contain the app, while development stages its source mount into the same runtime path.**

The earlier Docker path required a repository checkout because the image contained the scanner toolchain but expected `./app:/app:ro` at runtime. That was useful for development, but it made production installation download the whole repository, find private overrides among shipped files, and build a large tool image locally.

The Dockerfile copies `/app` after independent builder stages for ProjectDiscovery, other Go tools, native tools, Ruby tools, wordlists, and script assets. Those stages copy only the required binaries, runtime trees, and durable notices into one final image; compilers, development headers, Go caches, apt indexes, and build source trees stay behind. Development keeps a read-only bind mount at `/opt/darklab-source/app` for the quick edit-and-restart loop. Its root entrypoint clears an ephemeral `/app` tmpfs, copies the current checkout into it, changes the snapshot to `appuser`, and removes every write bit before configuration or workers load. That extra boundary is necessary because native Linux preserves host ownership and modes, so a direct `/app` bind can leave private `0600` source unreadable after privileges drop. Production pulls the same final image, doesn't set the staging trigger, and has no source or `/app` mount. Keeping one Dockerfile, runtime image, and entrypoint avoids a second production-only runtime that could drift in packages, capabilities, users, health behavior, or read-only filesystem assumptions.

Shipped configuration and operator configuration are separate on purpose. The image owns `/app/conf`, while production mounts `./conf` at `/config`. A shared resolver maps supported `*.local.*` files to the operator root and preserves sibling behavior when no separate root is configured. The installer can therefore keep the host tree private while the root entrypoint validates and stages an `appuser`-readable runtime copy before dropping privileges. Mounting a whole host directory over `/app/conf` was rejected because an old deployment directory could hide new commands, themes, workflows, and defaults after an image upgrade.

GitLab is the canonical registry because the source and release pipeline already live there. CI resolves the Python base index once, builds native AMD64 and ARM64 children from that snapshot, verifies and scans both staging digests, then assembles one OCI index only after every required gate passes. AMD64 uses one stable `buildcache-amd64` reference rather than a release-line name because BuildKit's content keys already invalidate entries when the Dockerfile, build arguments, or pinned base content changes. A fixed resource lock serializes the scheduled warmer and release publisher that write that reference. Every BuildKit path uses a tracked `HEAD` Git archive with a fixed tar umask as its context; that preserves Git's executable-bit contract while excluding checkout ownership, timestamps, ACLs, and xattrs such as SELinux labels from content keys. The scheduled warmer can run on any standard self-managed Docker runner; after it succeeds, every named Docker runner imports the recorded cache and pinned base digest without writing back. Cache portability is backed by an acceptance run that exported the release cache through a fresh BuildKit builder on `bael` and imported it through another fresh builder on `botis`; both jobs completed in under one minute with the expensive builder stages cached. CI doesn't keep those probe-only jobs because the production warmer, fanout, and release build exercise the lasting cache path. ARM64 stays uncached because registry-cache import and export for the bundled scanner and SecLists layers exceeds the hosted small runner's storage budget. Three uncached hosted-runner rehearsals completed in 1,790 to 1,827 seconds of a 3,600-second limit and retained 23.62 to 26.72 percent free daemon storage after export. The project accepts a 20 percent post-export floor for this isolated, cache-free lane; a cached or replacement runner must qualify separately. BuildKit cache mounts remain a builder-local optimization rather than cross-runner evidence.

Temporary build tags include the pipeline and base-resolution identity. Successful children receive stable architecture anchors before the canonical tag is created, so 14-day attempt cleanup never needs to delete a manifest by digest or risk the index's reachability. Cleanup collects the complete paginated match set before issuing its first deletion, preventing offset shifts from skipping later tags. A disposable GitLab.com repository exercise published two platform children, created durable architecture anchors, and assembled a canonical index in the production order. The production cleanup code deleted both temporary child tags and the staging-index tag; the canonical tag, canonical digest, anchors, child digests, and runnable AMD64/ARM64 platform content all remained intact. Release-candidate anchors stay with their candidate, and final anchors stay for the final release lifetime. Later physical storage reclamation is useful defense-in-depth evidence, but it doesn't block cleanup or release publication because production cleanup never deletes those anchors. A protected branch rehearsal uses its own `multiarch-rehearsal-*` namespace and stops before Docker Hub, signing, payload, and release work. Dual mode fails closed on a missing child. The AMD64-only emergency mode requires a manual protected pipeline and a public reason; automatic fallback was rejected because it would quietly narrow a release, and adding ARM64 later was rejected because it would move an immutable tag.

After index validation, Buildx imagetools copies the complete index and referenced children to Docker Hub for the shorter public pull path used by production Compose. Pulling, retagging, and pushing through a daemon was rejected because an image store can translate OCI and Docker manifest media types and change the digest even when the layers are identical. Rebuilding for the mirror was rejected because build timestamps and network-resolved packages can produce different bytes under one release version. Both registries use exact tags, and digest plus descriptor-set equality is the release boundary. Per-platform transfer, unpacked size, pull time, base manifest, and child digest travel with release evidence instead of being flattened into one misleading image measurement.

Operator verification deliberately doesn't require Buildx. The locally pulled image must carry the canonical index RepoDigest, match the platform Docker selected, and expose the platform and Python-base labels recorded in the signed release payload; the validated index contains exactly one child for each published architecture. Re-querying the registry for that child through a plugin would add an installation dependency without strengthening the immutable index check. Apple Silicon keeps the older verifier's compatibility behavior: it prefers a native ARM64 child, but an explicitly degraded AMD64-only release may use Docker's emulation path. Linux ARM64 remains native-only.

The installer is small and deliberately non-magical. A release-specific POSIX script downloads one deterministic exact-version archive, verifies its checksum and safe paths, validates the managed-file manifest and Compose, creates private operator paths, and prints the pull/start commands. It does not install Docker, use `sudo`, change firewall rules, generate the vault master key, or start services.

After setup, `darklab-deploy` owns the release-managed side of the directory. The manifest and checksum list make local drift visible without treating `.env`, `conf/`, databases, workspaces, or backups as release files. Exact-release upgrades create and verify a backup before replacing managed files, refuse downgrades because image rollback cannot undo schema changes, and leave container startup as an explicit operator action. Backup and restore run the image's Python and Postgres tools in one-off Compose containers so the public host contract stays at POSIX shell, Docker, and Compose. Same-backend restore remains the default because silently changing storage targets is unsafe. A fresh replacement install can explicitly adopt a Postgres backup while preserving its new connection credentials, but only after the target database is proven empty. Managed backups preserve the installed workspace directory even when Files is disabled because feature state is not a data-retention policy. Removal stops the stack and deletes only managed files.

Release trust uses GitLab's keyless Sigstore identity instead of a long-lived private signing key. A protected tag job signs the immutable GitLab and Docker Hub index references plus every included child manifest, and the payload job signs `SHA256SUMS`; operators verify the canonical index digest with the exact `.gitlab-ci.yml@refs/tags/vX.Y.Z` or `.gitlab-ci.yml@refs/tags/vX.Y.Z-rc.N` certificate identity and issuer `https://gitlab.com`. The locally selected child digest proves platform resolution but is not a substitute for the signed release-index target. The Docker Hub repository overview publishes that issuer and stable certificate-identity pattern independently of each release payload, and the public smoke job refuses a final or candidate artifact when the live overview no longer contains them. Keeping the reviewed overview text in the repository makes the manual Docker Hub setting auditable without pretending that a checksum served beside the payload is a separate trust root. Syft and Grype scan each native child before index assembly. Ordinary branch images receive the same fixed-Critical policy before tagging, and a manual digest recheck can rerun image, tool, and scan verification against either an index-selected platform or a child digest without republishing. Blocking every High or unfixed finding was rejected because it turns upstream remediation lag into a permanent release outage; silent ad hoc suppressions were rejected because they erase the audit trail. SLSA provenance and the release evidence index bind both registry names, release mode, index and child digests, source commit, protected tag, pipeline, shared base resolution, and per-platform SBOMs and scan reports. Release candidates exercise that entire chain and deliberately stop short of creating a GitLab Release, preserving the final release object as a user-facing milestone rather than a CI rehearsal artifact.

Compatibility claims follow evidence from dedicated release gates. Native AMD64 and ARM64 each pull and execute their own child image; ARM64 uses GitLab's hosted small runner with an isolated Docker-in-Docker daemon, while standard AMD64 uses the protected self-managed Docker runner. Production Compose leaves platform selection to the verified index. SELinux-enforcing Docker and rootless Podman use self-managed hosts that expose those real host policies, but those lanes currently verify only the AMD64 child and remain separate compatibility claims. Passing source-level, emulated, or cross-platform manifest inspection was rejected as proof of runtime support.

### Keep One Full Release Image

**The measured v2.6.0 release stays as one complete image; it does not add a slim sibling that omits wordlists or tools.**

The protected `v2.6.0-rc.23` pipeline measured the canonical AMD64 image at 1,450,481,244 compressed bytes and 1,450,509,512 installed bytes. Its representative cold pull took 39 seconds on the release runner. Four layers account for most of the transfer: SecLists is about 709 MB (49%), ProjectDiscovery tools are about 263 MB (18%), the other Go tools are about 159 MB (11%), and runtime packages are about 156 MB (11%). These numbers are release evidence rather than universal download-time promises; the manifest carries exact sizes for each release, while pull time depends on the host and network.

SecLists is the only single exclusion that would cut the image nearly in half, but removing it would make documented wordlist paths, autocomplete, and scanner examples depend on which image an operator chose. Splitting tools into sidecars would also change command execution, capabilities, networking, licensing, upgrades, and support. Keeping one self-contained image preserves the same command surface everywhere and is worth the larger initial pull. A separate variant is justified only if sustained operator evidence shows that transfer or storage cost outweighs that consistency and the alternate image can keep a clear, supportable feature contract.

### Startup Sequence (entrypoint.sh)

Container starts as root → `entrypoint.sh` runs → fixes `/data` ownership (Docker volume mounts reset ownership to the host user) → sets `/tmp` to `1777` → pre-creates `/tmp/.config/nuclei`, `/tmp/.config/uncover`, `/tmp/.cache` owned by scanner → `gosu appuser gunicorn ...`

**Why `gosu` instead of `su`?** `su` forks an extra process; `gosu` does `exec` which replaces the process, giving Gunicorn PID 1 semantics.

**Why `init: true` in Compose?** When Gunicorn is PID 1, orphaned child processes in a scanner subprocess chain are reparented to the Gunicorn master. Scanner commands run as a chain — `sudo → env → sh → tool` — and when the group receives SIGTERM all four processes die simultaneously. If an intermediate parent exits before the leaf process, the leaf becomes an orphan and is adopted by PID 1 (Gunicorn). If that tool exits with a non-zero code (e.g. `wpscan` returns 3 for "potentially interesting findings"), Gunicorn's `reap_workers()` collects it via `waitpid(-1)` and interprets `exit(3)` as `WORKER_BOOT_ERROR`, shutting the entire server down. `init: true` adds Docker's bundled tini init as PID 1; Gunicorn starts as PID 2+, and any orphaned scanner processes are silently reaped by tini without reaching Gunicorn at all.

**Why pre-create `/tmp/.config`?** Without this, the first tool that tries to create it (e.g. nuclei on startup) runs as `scanner`, but the directory doesn't exist yet. If anything root-level touches `$HOME` before the user switch completes, it creates `/tmp/.config` owned by root with `700`, and `scanner` can never write to it.

### nmap Capabilities

**Raw scanning is an operator opt-in built on file capabilities, not a privileged container.**

nmap requires `CAP_NET_RAW` and `CAP_NET_ADMIN` for OS fingerprinting and SYN scans:

```bash
setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap
```

This grants the capabilities to the binary itself — any user who executes nmap gets them for the duration of that process only. The active Compose file must also have `cap_add: [NET_RAW, NET_ADMIN]` or the host kernel won't make those capabilities available to the container. The container stays on its normal bridge network and never uses Docker `privileged: true`.

The default remains TCP connect scanning. `rewrite_command()` injects `-sT` when no scan mode is explicit unless `RAW_PACKET_SCANNING_ENABLED=true` is configured and runtime checks confirm Linux `CAP_NET_RAW`, executable file capabilities, and a compatible executable policy. Ready deployments use a fixed `NMAP_PRIVILEGED=1` environment value so Nmap recognizes the file capabilities and keeps its SYN default. Explicit `-sT` stays unchanged, and user-supplied `--privileged` is always blocked.

The scanner app-port firewall matches only destinations local to the container. A broad destination-port rule looked like a raw-socket failure during multi-host scans because it rejected every remote port `8888` send with `EPERM`. Restricted CIDRs come from the app's effective normalized config and use required scanner-user OUTPUT rules plus a matching root-owned readiness marker; raw Nmap forces `--send-ip`, while `--send-eth` stays blocked. Packet-socket Naabu and Masscan remain unavailable whenever restricted CIDRs are configured because those packets do not cross the owner-matched OUTPUT path. The app does not accept an operator attestation for separate host or bridge firewall rules.

### Go Binary Installation

**Go tools are built into a staged output directory and copied into the runtime for the `scanner` user.**

Go tools such as `nuclei`, `subfinder`, `httpx`, `dnsx`, `naabu`, `katana`, `tlsx`, `cdncheck`, `amass`, `assetfinder`, `gobuster`, `ffuf`, `tcping`, `trufflehog`, and `puredns` build with `GOBIN=/out/usr/local/bin` in the Go stages. The final stage copies that output to `/usr/local/bin`, where the binaries are world-executable and accessible to `scanner`. Versioned installs use a short-lived main module that establishes the reviewed `golang.org/x/crypto` release as a minimum before selecting the pinned tool. A tool can raise that dependency when its release requires a newer version, and the build checks both the selected module graph and the finished binary's embedded module metadata before accepting it. `gosu` builds from pinned source with the same current Go toolchain, so its embedded standard library doesn't lag behind the rest of the image. Reviewed Go and module licenses are copied to stable paths under `/usr/share/doc/darklab-shell/licenses`; the toolchain, module cache, compilation cache, and unrelated upstream executables never enter the runtime image or SBOM. Installing into `/root/go/bin` was rejected because that root-owned path is inaccessible to `scanner`, and symlinking it into `/usr/local/bin` would keep the same target-permission problem.

### TruffleHog Output Redaction

**TruffleHog managed scans use JSON output so every secret-bearing field can be masked before persistence.**

The command registry appends `--json` to managed `trufflehog filesystem`, `git`, `github`, and `gitlab` scans unless the flag is already present or the command is a help request. The run-output path treats detector JSON as a finding and replaces `Raw`, `RawV2`, `Redacted`, and all `SecretParts` values before the line is streamed, stored, written to Files, shared, exported, or used to create findings. Exact copies of those values elsewhere in the JSON row are replaced too.

The app treats TruffleHog's `Redacted` field as secret material because detectors may put an unchanged credential or part of a private key there. Finding text records only detector, verification state, and safe source-location metadata, and a malformed detector row falls back to a generic finding label instead of storing the original text. Redacted share and package paths also recognize PEM and PGP private-key blocks across line boundaries as a defense for output from TruffleHog or any other command. TruffleHog's own verification behavior remains available for users who intentionally run the scanner; the app's safety boundary is controlled command shapes, managed Files inputs, credential-free HTTPS repository and provider endpoints, encrypted environment-only provider tokens, managed temporary clones, JSON output, and server-side transcript masking.

### SQLite WAL Mode

**SQLite runs in WAL mode to support concurrent reads from multiple Gunicorn workers.**

SQLite is configured in WAL (Write-Ahead Logging) mode with `PRAGMA synchronous=NORMAL`. This allows concurrent reads during writes, which is important with 4 Gunicorn workers all reading/writing the same database simultaneously. The `db_connect()` function applies these pragmas on every connection.

Startup bootstrap is serialized explicitly. The web entrypoint calls `runtime_bootstrap.bootstrap()`, and worker processes call `runtime_bootstrap.bootstrap_runtime(...)` with the startup steps they need. `db_init()` runs from that explicit bootstrap path rather than from module import. For SQLite, `_db_init_lock()` takes an exclusive filesystem lock on `/data/history.db.init.lock` (or the `/tmp` fallback) so schema creation, migration, and retention pruning happen one process at a time and workers do not fail with `sqlite3.OperationalError: database is locked`.

### Database Backend Support

**SQLite remains the default backend; Postgres is the supported scaling backend.**

SQLite is the local, single-user, and default deployment backend. It keeps the operational shape simple: one app-owned database file, WAL mode for concurrent readers, FTS5 for local search, and no separate database server requirement.

Postgres is the supported backend for heavier multi-user deployments that need a server database, connection pooling, trigram-backed search, and production-style storage operations. It is selected explicitly with `DATABASE_BACKEND=postgres` plus `DATABASE_URL`; normal app database calls then route through the Postgres compatibility wrapper and backend-aware SQL helpers.

SQLite-to-Postgres data movement is a separate offline cutover, not an automatic startup conversion. Production operators run `darklab-deploy migrate-to-postgres` as the installation owner; it reaches the locked-down SQLite file through the managed Docker mount, requires a Postgres destination with no user tables, copies data into a fresh bundled schema, validates counts and artifacts, and only then switches backend settings. Because Compose named volumes outlive their installation directory, migration checks the cluster through its local socket and may synchronize the configured role password only while the destination is empty; a non-empty retained volume is never repurposed automatically. Development checkouts and custom test targets can use `scripts/migrate_sqlite_to_postgres.py` with the guide in `docs/postgres-migration.md`. Schema management is shared by the app-owned migration runner; data migration remains an explicit maintenance workflow.

### FTS5 Tokenizer: Trigram with Unicode61 Fallback

The `runs_fts` virtual table uses the FTS5 **trigram** tokenizer when available (SQLite ≥ 3.38), falling back to **unicode61** (the FTS5 default, available on all SQLite versions).

**Why trigram:** Security tool output contains port numbers (`443/tcp`), CVEs (`CVE-2024-1234`), IP addresses, hostnames, and flag strings that users typically search for by substring. Trigram tokenization breaks every string into overlapping 3-character sequences, enabling `MATCH "443"` to find `443/tcp open` without the user needing to know the exact token boundary. Unicode61 tokenizes on whitespace and punctuation, so `443` alone would not match `443/tcp` — the user would need to search `443/tcp` exactly.

**Why the fallback matters:** The production Docker image is based on the latest Ubuntu and ships SQLite 3.38+, so trigram is always used in production. The fallback to unicode61 preserves FTS functionality for operators running darklab_shell on platforms with older SQLite (some Alpine-based images, macOS system SQLite). In the fallback case, search remains functional for whole-word and prefix queries; only substring matching within tokens degrades. `_create_fts_schema()` in `database.py` detects the available tokenizer at init time and falls back gracefully; no config change is needed.

---

## Observability Decisions

### Structured Logging

**Problem:** The original `logging.basicConfig(...)` in `app.py` had two issues:
1. Logging setup lived in the app assembly module, which made startup order fragile and tied logging to importing the Flask app.
2. All log records were plain strings, incompatible with GELF structured log aggregation.

**Solution:** `logging_setup.py` provides two formatters and a `configure_logging(cfg)` function. Runtime startup calls it through `runtime_bootstrap.configure_runtime_logging(...)` before process setup, database initialization, or app construction. Configuration records emitted during the earlier `config.py` import are held by `startup_logging.py` and replayed once after the effective level and formatter are known. A fatal load that prevents bootstrap uses the same temporary boundary for one redacted structured fallback. This keeps `import app` side-effect-free while ensuring configuration, Redis, database, worker, and request lifecycle logs use the intended contract.

The `shell` logger is configured with `propagate = False` so records don't double-emit to the root logger. Werkzeug's own request lines are suppressed (`logging.getLogger("werkzeug").setLevel(ERROR)`) because request logging is handled by `before_request` / `after_request` hooks instead.

**Formatter design:**

- `GELFFormatter` — emits compact GELF 1.1 JSON. `short_message` is a bare event name (e.g. `RUN_START`); all context is in `_`-prefixed additional fields. This gives Graylog direct indexable fields (`_ip`, `_run_id`, `_cmd`) without any extraction rules. Additional field names also carry a type contract: numeric HTTP codes use `_http_status`, feature states use string `*_status` fields, and the compatibility path never emits the ambiguous legacy `_status` field.
- `_TextFormatter` — human-readable `2026-04-02T10:00:00Z [INFO ] EVENT  key=value ...` lines. Extra fields are sorted alphabetically and appended after the event name. String values containing spaces are repr-quoted.

Both formatters use a shared `_extra_fields(record)` helper that extracts caller-supplied fields from the LogRecord (anything not in `_STDLIB_ATTRS` and not underscore-prefixed).

The concrete event inventory, output formats, field contracts, redaction rules, and troubleshooting guidance live in [docs/logging.md](docs/logging.md). The formatter and bootstrap boundaries stay in [ARCHITECTURE.md](ARCHITECTURE.md#logging), since those are current-system details rather than decision history.

**Timing note:** `client_ip` is captured once at the top of `run_command()` as a local variable before the `generate()` closure is defined. This avoids a hidden dependency on Flask's request context being active when the generator body runs during streaming. The same `client_ip` local is closed over in `generate()`.

---

## Frontend Decisions

### Shared Jinja Document Shell

**One lightweight base template owns the shared HTML document frame; page templates keep ownership of their payloads.**

The shell, permalink pages, diagnostics, and audit log all need the same doctype, metadata, favicon, application styles, theme-variable styles, and themed body. Keeping those lines in every page made a small change easy to miss on one surface. `base.html` now owns that stable frame, while narrow blocks let each page keep its own title, extra assets, body classes, content, and scripts.

The boundary deliberately stops at document-level structure. Moving the shell's lazy assets, diagnostic timezone behavior, permalink bootstrap reporting, or page markup into shared macros would make unrelated pages depend on one another and hide which page pays for each asset. Permalink content and error pages continue extending `permalink_base.html`, so their existing two-level inheritance stays intact.

### Shared Frontend State Layer

**A single `state.js` module owns shared browser state, with legacy globals rewired to it via `Object.defineProperty` accessors.**

The browser scripts share a single state layer in `app/static/js/core/state.js`. That module loads immediately after `session.js` and installs `Object.defineProperty` accessors on `globalThis`, so the legacy global-style code can keep reading and writing plain names while the actual storage lives in one central object. DOM-centric helpers were split into `app/static/js/ui/ui_helpers.js`, which keeps the state boundary smaller without forcing an ES-module migration.

That choice keeps the codebase free of a larger ES-module migration while still making the shared state explicit. It also keeps the unit-test harness simple: the jsdom loader can seed `state.tabs` and `state.activeTabId` before evaluating the browser scripts, then prepend `ui_helpers.js` before DOM-bound modules so the extracted scripts see the same helper globals as production without rewriting the production call sites.

### Export Rendering Centralization (ExportHtmlUtils)

**Problem:** Save/export had rendering logic in multiple places. `exportTabHtml` in `tabs.js`, `saveHtml` in `permalink.html`, and the PDF surfaces in both files each built their own line rendering, CSS, and document structure. Every visual fix required edits in two or more places. The PDF surfaces were especially fragile because they were structurally identical but unlinked.

**Solution:** `export_html.js` was introduced as the single source of truth for the browser-rendered export model, exposing `window.ExportHtmlUtils`. It owns line preparation, transcript normalization, run-meta normalization, meta-line formatting, export-document preparation, header-model preparation, export-header HTML, inline export CSS, and embedded-font CSS for self-contained HTML downloads. Both the main-shell save path and the permalink/share save path now consume those helpers.

**Follow-through:** PDF rendering was extracted into `export_pdf.js` as `window.ExportPdfUtils`, so the two PDF call sites no longer carry duplicated rendering logic. The current split is deliberate:
- `ExportHtmlUtils` owns the shared browser export semantics and acts as the baseline for permalink/share live pages plus saved HTML
- `ExportPdfUtils` remains a separate renderer because jsPDF cannot reproduce browser layout exactly, but it consumes the same prepared header/meta/line model so PDF visual drift is bounded to renderer limitations rather than duplicated business logic

**Server/page-model follow-through:** permalink/share pages now bootstrap one normalized `page_model` from `app/services/history/permalinks.py`, and both the Jinja template layer and `permalink.js` consume that same shape. That keeps the live permalink/share page and the saved export surfaces aligned without reintroducing duplicated page-bootstrap variables.

### Client-Side PDF Export (jsPDF)

**Why jsPDF over server-side rendering:** The shell has no server-side PDF capability (no headless browser, no LaTeX, no wkhtmltopdf). Adding a server-side PDF renderer would require a new dependency, server CPU, and a separate request lifecycle. jsPDF generates PDFs entirely in the browser from the already-rendered ANSI data, matching the "no server round-trip" model of the existing HTML export.

**Font limitations:** jsPDF cannot reproduce browser typography exactly even when it embeds the same font files. The current PDF path embeds the committed JetBrains Mono fonts when jsPDF's VFS hooks are available and falls back to Courier otherwise, but exact browser kerning, flex layout, glow, and CSS text metrics still are not achievable. The PDF export therefore targets visual parity — matching hierarchy, ordering, spacing intent, and theme colors — rather than pixel-identical output.

**Color resolution:** jsPDF needs RGB arrays, not CSS custom property values. `_parseCssColor()` creates a 1×1 canvas, sets the CSS color string as `fillStyle`, reads back the computed `fillStyle`, and parses the `rgb(...)` result. This handles any CSS color format including `color-mix()` expressions from the theme system.

**Character spacing units:** jsPDF's `setCharSpace(n)` adds `n` points between each character. CSS `letter-spacing: 4px` at 96dpi ≈ 3pt. Using `setCharSpace(2)` with `hAppNamePt: 13` produces visually comparable spacing to the HTML export's `font-size: 20px; letter-spacing: 4px; font-weight: 300` heading.

### Save Menu UX (save ▾ dropdown)

**Why one dropdown instead of separate buttons:** Three export formats (txt, html, pdf) in the HUD action row would consume too much horizontal space alongside the other status pills and action buttons. The `save ▾` dropdown groups them under a single button matching the model already used by other action menus in the shell.

**Consistency across surfaces:** The same dropdown pattern was applied to the permalink page header and the mobile menu so the export interaction is predictable regardless of which surface the user is on.

### Native Share-Sheet for Permalink URLs

**Problem:** "Copy permalink URL" works on desktop but is awkward on mobile — users have to paste from clipboard into a share target manually.

**Solution:** `navigator.share()` (Web Share API) invokes the native OS share sheet when the browser supports it. On unsupported browsers (most desktop browsers at time of writing) the flow falls back to `navigator.clipboard.writeText()` without UI intervention. `AbortError` from the user cancelling the share dialog is caught and suppressed silently — it is not an error.

### Run Notification Title Uses Command Root Only

**Desktop notifications show only the command root (first word), not the full command string.**

Desktop notifications on run completion (`_maybeNotify()` in `runner.js`) use only the command root — the first word — as the notification title (e.g. `$ curl`) rather than the full command string.

**Why not the full command:** The full command can contain bearer tokens (`curl -H "Authorization: Bearer sk-..."`), API keys in query strings, auth headers, internal hostnames, or the literal token value from `session-token revoke <token>`. Browser notifications are visible in the OS notification center and can persist after the browser window is closed. Logging the full command in the notification title would expose secrets in a surface that users may not associate with sensitive data. The command root communicates which tool ran without leaking any arguments.

**Why not suppress the title entirely:** A blank or generic title ("run complete") gives operators no context about which of several concurrent long-running scans just finished. The command root is a reasonable middle ground — enough signal to identify the tool, no risk of credential exposure.

### Dedicated Mobile Shell

**Mobile uses a dedicated `#mobile-shell` surface with explicit chrome/transcript/composer/overlays mounts, but stays in normal document flow rather than pinning with fixed-shell viewport math.**

The mobile UI still uses a dedicated shell rooted at `#mobile-shell` with explicit `chrome`, `transcript`, `composer`, and `overlays` mounts. The difference now is that the shell was deliberately simplified back to a normal-flow layout after a focused repro proved the Firefox mobile bug was coming from the app's integration layer, not from the browser itself.

The current shape is intentional:

- `#tab-panels` is still reparented into the mobile transcript mount at runtime so output rendering stays shared while the mobile surface gets its own container.
- `#mobile-shell` stays in normal document flow instead of pinning the whole mobile terminal with fixed-shell viewport math.
- `#mobile-composer-host` stays free of keyboard-height spacing, and the mobile shell now relies on its simplified normal-flow layout instead of page-scroll resets, `visualViewport` pan compensation, or body-level transforms.
- Mobile input focus is user-driven; the code no longer relies on synthetic focus handlers on the composer host or lower hit area because those were a major source of scroll jumps and transient bad frames on Firefox mobile.
- The active output can surface a tab-scoped jump-to-live / jump-to-bottom helper when follow-output is paused. It is driven by the same `followOutput` and `st` state that already governs live-tail behavior, so the control stays with the panel as it moves between desktop and mobile layouts.
- Overlays are mounted into a separate mobile overlay area so the shell can manage menu, history, FAQ, and options surfaces independently of the desktop wrapper.

The key architectural decision here is negative: the app no longer tries to outsmart the mobile browser with page-scroll correction or fixed full-shell keyboard choreography. Those experiments made the Firefox keyboard bug worse. The stable model is closer to a normal mobile document with a dedicated composer block at the bottom of the shell.

This keeps the mobile surface structured without needing a separate frontend bundle or framework split, while preserving the simplified layout that fixed the Firefox mobile issue.

### Shared Mobile Sheet Contract

**Mobile sheets use one structural contract (`.mobile-sheet-overlay` + `.mobile-sheet-surface`) and close through backdrop / grab / Escape, not per-surface `X` buttons.**

Options, FAQ, workflows, shortcuts, and confirmation surfaces had accumulated a mix of per-ID overlay rules and surface-specific close affordances. That made regressions easy: one sheet could still behave like a centered modal while another rendered as a bottom sheet, and hiding `X` buttons on mobile had to be remembered per surface. The current contract centralizes the structural part of mobile sheets in shared selectors and treats dismissal as a behavior contract rather than a per-surface decoration: backdrop tap, drag/grab handling where applicable, and Escape all route through the same dismissal helpers, while the visible `X` is removed from mobile sheet UIs.

The theme selector is the deliberate exception. It keeps a dedicated full-screen mobile treatment because its grouped theme preview grid is denser than the other sheet-style surfaces and benefits from using the full viewport.

### Desktop-Only Options Stay Out Of The Mobile Sheet

**The Options modal is shared across device classes, but the mobile sheet hides settings whose effect is desktop-specific (`HUD Clock`, `Run Notifications`).**

Not every preference belongs equally on every surface. `HUD Clock` controls the desktop HUD `CLOCK` pill, and run notifications are treated as a desktop-oriented “tab not in focus” affordance rather than a core mobile workflow. Leaving both rows visible on mobile made the Options sheet noisier without adding useful handheld behavior. The underlying preferences still live in the same shared session-scoped/browser-cached preference layer, but the mobile presentation now omits those rows so the sheet stays focused on settings that matter on phones.

### Button Primitive Family

**Every pressable surface in the shell uses one of a small, allowlisted set of primitive classes (`.btn` with role + tone modifiers; `.nav-item`, `.close-btn`, `.toggle-btn`, `.kb-key`) rather than one-off component CSS.**

The shell had accumulated bespoke button styles on individual surfaces (rail sections, the save menu, mobile chrome, the permalink header, confirmation modals) that drifted in padding, tone, focus outline, and press feedback. Each new surface learned the lesson slightly differently. The primitive family collapses that into one set of classes and one shared `bindPressable` helper, so new surfaces inherit the correct contract by default and the rare exception requires an explicit entry in `tests/js/fixtures/button_primitive_allowlist.json` with a reason. The rules and the allowed primitives are listed in [ARCHITECTURE.md § Button Primitive Family](ARCHITECTURE.md#button-primitive-family).

### Disclosure Affordance Rules

**Disclosure glyphs encode a fixed mapping between glyph and behavior: `▸`/`▾` for expand/collapse in place, `>` for drill-in navigation, static `▾` for dropdown triggers, no glyph for plain toggles. The glyph follows the actual behavior, not the visual hierarchy of the surface.**

Early mobile surfaces used `>` on rows that opened a sub-sheet and on rows that expanded in place, because both "felt like going deeper." Users read the glyph as a consistent signal and got surprised when the two behaved differently. Pinning the glyph to the behavior — and naming the one meta-rule explicitly — kept the FAQ, rail section headers, mobile recents filter, and the save menu predictable as surfaces were added. `bindDisclosure` in `app/static/js/ui/ui_disclosure.js` owns the expand/collapse variant so new disclosure sites pick up `aria-expanded` correctly by default. The full mapping is in [ARCHITECTURE.md § Disclosure Affordance Rules](ARCHITECTURE.md#disclosure-affordance-rules).

### Semantic Color Contract

**Theme colors are semantic, not decorative. Four tokens (`--amber`, `--red`, `--green`, `--muted`) have fixed meanings; surface CSS derives tuned variants via `color-mix()` from those tokens rather than hardcoding one-off colors.**

The rules, the binary-not-graded principle, the `running`-is-yellow distinction, and the three documented exceptions (starred items, search-hit highlights, the macOS traffic-light minimize dot) all live in [THEME.md § Semantic Color Contract](THEME.md#semantic-color-contract). Moving the contract into the theme doc rather than the general architecture reference keeps theme authors and surface authors reading the same rule set, instead of two nearly-identical summaries drifting apart. [ARCHITECTURE.md § Semantic Color Contract](ARCHITECTURE.md#semantic-color-contract) carries a short pointer.

### Confirmation Dialog Contract

**Every destructive or mode-switching confirmation routes through one imperative primitive, `showConfirm()`, with role-based action ids, default focus on cancel, `bindFocusTrap` on the card, and stacked actions at narrow widths.**

Confirmations were originally per-surface: the kill flow, history clear, history delete, the share-redaction toggle, and session-token migrations each hand-rolled their own markup, Escape handler, mobile-sheet binding, and focus management. Small inconsistencies (Enter activating confirm instead of cancel, Tab falling through to the rail behind the backdrop, the action row overflowing on narrow viewports) had to be fixed separately each time a new confirm shipped. `showConfirm()` in `app/static/js/ui/ui_confirm.js` centralizes the contract so every confirmation inherits the same dismissal ordering, focus trap, and stacking behavior, and new destructive actions only choose copy, tone, and the role of each button. Full semantics are in [ARCHITECTURE.md § Confirmation Dialog Contract](ARCHITECTURE.md#confirmation-dialog-contract).

---

## Known Gotchas and Lessons Learned

### Runtime Streaming and Process Lifecycle

**Gunicorn generator laziness.** Any setup that must happen before a kill request can arrive (Popen, pid_register) must be outside the generator function passed to `Response()`. The generator only executes when Flask starts iterating it to stream bytes.

**wpscan (and similar tools) exits with code 3 as a normal status.** wpscan returns 3 to mean "potentially interesting findings found" — not a crash. When Gunicorn runs as PID 1 (via `gosu` exec), that exit code from an orphaned subprocess triggers `WORKER_BOOT_ERROR` in `reap_workers()` and halts the server. Fix: `init: true` in Compose. See Startup Sequence above.

**Scanner subprocess chains can orphan their leaf process.** `SIGTERM` sent to the process group kills all four processes (`sudo`, `env`, `sh`, `tool`) simultaneously. If the intermediate parents die first, the leaf tool briefly has no parent and is adopted by PID 1. With `init: true`, PID 1 is tini, not Gunicorn, so the adoption is benign.

### Container and Filesystem Behavior

**Docker volume mount ownership.** Bind-mounting `./data:/data` resets the directory's ownership to the host user who created it. The `entrypoint.sh` `chown -R appuser:appuser /data` corrects this on every start. The `-R` is important — `history.db` itself may also be root-owned if it was created by a previous run as root.

**`multiprocessing.Manager` and fork.** Python's `multiprocessing.Manager` starts a background server process. When Gunicorn forks workers, the Manager proxy objects in the child processes can lose their connection to the Manager server under load. This manifested as intermittent kill failures — some processes couldn't be killed because their PIDs weren't visible to the worker handling the kill request. SQLite is more reliable here.

**sudo resets HOME.** `sudo -u scanner` resets the `HOME` environment variable to the target user's home directory from `/etc/passwd`. For `scanner` (a no-login system user) this is `/home/scanner`, which doesn't exist on the read-only filesystem. All tools that write config/cache to `$HOME` fail. The fix is `sudo -u scanner env HOME=/tmp` to explicitly set HOME before the command runs.

**NMAP_PRIVILEGED vs Docker --privileged.** These are different things. `NMAP_PRIVILEGED=1` tells Nmap to assume it has raw socket access from its existing file capabilities. Docker's `--privileged` gives the container broad host access. The app sets the Nmap environment value only after operator opt-in and readiness checks; Docker privileged mode and user-supplied Nmap `--privileged` remain off-limits.

**`env` doesn't use `--` as a terminator.** `sudo -u scanner env HOME=/tmp -- sh -c "..."` fails because `env` treats `--` as a literal command name. The correct form is `sudo -u scanner env HOME=/tmp sh -c "..."`.

### Demo Recording Pipeline

**OBS is the standard demo recorder.** Playwright's built-in video recorder ignores `deviceScaleFactor`, and the older screenshot-stitcher produced choppy motion for animated UI like the Status Monitor pulse strip. The desktop and mobile demo wrappers now open a headed Chromium window, pause on a holding screen so OBS can select the right window, then start/stop OBS through the grouped development helper. The specs still keep their screenshot-frame fallback for local experiments, but README-quality demo videos should use `scripts/record_demo.sh` or `scripts/record_demo_mobile.sh`.

**Clicking a `<button>` to select a theme causes a one-frame scroll jump.** When the recording spec selects a theme card, even a synthetic `dispatchEvent('click')` focuses the underlying `<button>` element. Chromium's native focus-scroll management then repositions the scroll container to ensure the focused element is in view — even if it already is — producing a visible one-frame jump in the recording. The fix is to call `applyThemeSelection(name)` directly via `page.evaluate()` instead of dispatching any click event. This applies the theme and toggles `theme-card-active` with identical effect, but never touches focus or scroll state. Avoid any approach that causes a DOM click (`.click()`, `.dispatchEvent('click')`, `locator.click()`) on a `<button>` inside a scroll container when you need the scroll position to remain stable.

**`freezeFrame()` is only for the screenshot fallback.** When `DEMO_DISABLE_FRAME_CAPTURE` is unset, the specs can still capture PNG frames with `page.screenshot()`. `freezeFrame(durationMs)` keeps those fallback recordings from compressing pauses into fast-forward by stamping one screenshot across the expected frame count. The normal OBS wrappers disable frame capture, so real-time pauses are handled by the browser and OBS.

**Chromium's mobile keyboard simulation overlay cannot be covered.** In Playwright's headless Chromium mobile emulation, focusing any input element (`input.focus()`, `locator.click()`, or `page.keyboard.type()`) triggers a gray keyboard-simulation overlay that is painted above all page content regardless of z-index. This overlay is not a DOM element and cannot be hidden with CSS, `pointer-events: none`, or JS. The overlay also shrinks the visual viewport, making the composer area shift up and the transcript area shrink — producing a demo that looks nothing like the real mobile app on a phone. The mobile demo spec avoids this entirely by typing through the native `HTMLInputElement.prototype.value` setter + `InputEvent` dispatch, never calling `.focus()` on the input. This keeps the visual viewport stable, the fake keyboard image visible at the bottom of the frame, and the transcript filling the full screen while commands run.

**CSS `overflow-y: visible !important` is silently ignored when `overflow-x` is non-visible.** The CSS spec's mutual-override rule converts `overflow-y: visible` to `overflow-y: auto` at computed-value time whenever `overflow-x` is set to any non-`visible` value (e.g. `scroll` or `auto`). This conversion happens *after* the cascade, so `!important` on the `overflow-y` specified value has no effect — the computed value is still `auto`. The element becomes a scroll container in the Y axis, which clips any child with a negative margin-bottom overhang. Encountered when fixing tab-pill top clipping in the Playwright demo recording (`.tabs-bar` has `overflow-x: scroll`, causing it to clip the tab's `margin-bottom: -1px` overhang). Fix: use the `overflow` shorthand to set both axes simultaneously — `overflow: visible !important` — so the mutual-override rule has no non-visible axis to trigger on.

### Frontend and Rendering Gotchas

**ansi_up and permalink colors.** ansi_up converts ANSI escape codes to HTML spans, consuming the original codes. If you try to re-render from `element.innerText`, all color information is lost. The `rawLines` array stores the original text before ansi_up processes it, enabling the permalink page to run ansi_up fresh and reproduce the exact same colors.

**`vendor/` routes must exist for local development.** `ansi_up.js` and `jspdf.umd.min.js` are served through `/vendor/` directly from `app/static/js/vendor/`. Both files are committed and generated by `npm run vendor:sync` from the npm packages tracked in `package.json`. If the committed files are missing or stale, `AnsiUp` or `jspdf` will be undefined, causing crashes in the ANSI rendering and PDF export paths respectively. Fix: run `npm run vendor:sync` to regenerate from the current npm packages, then commit the result. The symptom of a missing `ansi_up.js` is: tab label updates (it runs before `appendLine`) but no command output and nothing in the server logs — the fetch never happens because `AnsiUp` is undefined.

**SSE via fetch vs EventSource.** `EventSource` doesn't support custom request headers. Since we need `X-Session-ID` on every request, we use `fetch()` with a `ReadableStream` reader instead. This requires manually parsing the SSE format (`data: ...\n\n`) from the raw byte stream.

**Multi-tab stall detection requires per-tab state.** The SSE stall detector fires if no data arrives within 45 seconds. The original implementation used a single module-level `_stalledTimeout` variable. With multiple tabs running commands simultaneously, starting a command in Tab B would cancel Tab A's timeout, leaving Tab A's stalled connection undetected indefinitely. Fixed by replacing the single variable with a `Map` keyed by `tabId` (`_stalledTimeouts = new Map()`). All four call sites (`_resetStalledTimeout`, `_clearStalledTimeout`, and their consumers in the SSE loop and kill handler) must pass `tabId`.

**Partial-line stream readers must not block heartbeat delivery.** The server originally used `select()` followed by `readline()` on `proc.stdout`. That looks safe, but it fails for tools that write partial lines: `select()` reports readability as soon as bytes arrive, then `readline()` can still block waiting for a newline. While blocked, the generator cannot emit heartbeat comments, so the browser can misclassify the stream as stalled even though the subprocess is still alive. The fix is a nonblocking fd reader plus an incremental decoder and a pending-fragment buffer, so complete lines stream immediately, partial fragments wait safely for completion, and heartbeats keep flowing during quiet periods.

**Detached run drains need a ceiling.** When a browser disconnects from `/runs/<run_id>/stream`, the server keeps draining stdout in a background worker so the run can still be persisted. Without a hard ceiling, a process that never exits or never closes stdout can leak work and pin active-run metadata until the worker is recycled. Detached drains are now bounded to the command timeout plus grace, terminate the scanner process group when exceeded, and always run the same PID/active-run cleanup path.

**Workspace file opens use no-follow hardening at the final component.** The normal workspace resolver rejects unsafe relative paths and symlink components before use, but a final symlink can theoretically be swapped in after validation and before open by the same filesystem principal. Reads and downloads now use final-component no-follow opens where supported, which keeps the session-root boundary deterministic without changing the user-facing file API.

### Linting and Static Analysis Toolchain

**ESLint was chosen over Prettier for JS linting.** Prettier's `--check` mode only identifies which files differ from its expected output — it does not show which line or rule is violated. ESLint shows the exact file, line, column, and rule name on every violation, which is far more actionable in a pre-commit hook. ESLint is configured in `.tooling/eslint.config.js` and covers app source, tests, tooling, and scripts. Browser app files use ESLint for syntax/global safety without forcing the test/config formatting rules onto semicolon-heavy source modules; the 2-space `indent`, `singleQuote`, and `semi: never` rules stay scoped to Playwright/config-style files.

**Git hooks live in `scripts/hooks/` instead of `.githooks/` or `.git/hooks/`.** `.git/hooks/` is not version-controlled and requires every developer to manually copy or symlink files after cloning. `.githooks/` is trackable but is a non-standard directory name that requires explicit opt-in. `scripts/hooks/` is tracked like any other script, follows the project's existing `scripts/` convention, and is activated with one command: `git config core.hooksPath scripts/hooks`. The previous Python-only hook at `.githooks/pre-commit` has been superseded; the consolidated hook at `scripts/hooks/pre-commit` covers the tracked local checks (Ruff, bandit, pytest, pip-audit, vitest, eslint, npm audit, shellcheck, hadolint, yamllint, jsonlint, markdownlint, and vendor:check).

### Long-Running and Local-Dev Edge Cases

**Command timeout must fire during continuous output.** The original timeout check was inside the `select()` idle branch — it only ran when no output had arrived for `HEARTBEAT_INTERVAL` seconds. A command producing a constant stream of output (e.g. a flood scan before deny rules were added) would never hit the idle branch and therefore never time out. Fix: moved the timeout check to the top of the `while True:` loop so it runs on every iteration regardless of output activity. The start time is parsed once outside the loop (`datetime.fromisoformat(run_started)`) to avoid repeated parsing overhead.

**HTTP/1.1 browser connection limit (local development only).** Browsers cap concurrent HTTP/1.1 connections per origin at 6. Each running command holds one persistent SSE connection. With multiple app UI tabs each running a command, it's possible to saturate the limit, causing new page loads (JS files etc.) to stall. In production this is a non-issue — nginx-proxy terminates HTTPS, and HTTP/2 multiplexes all requests over a single connection with no per-origin cap. In local development (bare Gunicorn, no proxy, HTTP/1.1), you can hit this limit with enough concurrent tabs. A local Caddy proxy (`brew install caddy`) resolves it if needed.

---

## Related Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) - current runtime and design contracts
- [CONFIGURATION.md](CONFIGURATION.md) - current operator settings
- [FEATURES.md](FEATURES.md) - current user-facing behavior
- [CONTRIBUTING.md](CONTRIBUTING.md) - contributor workflow
- [DOC_STANDARDS.md](DOC_STANDARDS.md) - documentation ownership and maintenance
