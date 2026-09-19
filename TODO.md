# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Unify operator access and separate metrics network permissions](#unify-operator-access-and-separate-metrics-network-permissions)
  - [Autoscale ARM64 release runners on EC2 Spot](#autoscale-arm64-release-runners-on-ec2-spot)
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
  - [Local accounts for deployments without an identity provider](#local-accounts-for-deployments-without-an-identity-provider)
  - [Operator admin console for instance settings](#operator-admin-console-for-instance-settings)
- [Architecture](#architecture)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

**v3.0 delivery scope.** Managed sign-in is implemented; production-like staging qualification remains the access release gate. The ARM64 release-runner autoscaling work remains independent and is not a v3.0 release requirement.

Land each coherent change through a short-lived branch and merge request while keeping `main` functional and the complete validation suite green. Keep access-profile changes reviewable with explicit transition tests.

Exercise open and restricted modes in a production-like staging deployment during the `release/3.0` candidate cycle, starting with `v3.0.0-rc.1`. Use that feedback to close any browser-session, recovery, bootstrap, proxy, and operator-workflow gaps. Confirm the release gates pass on both database backends and the complete documentation reflects shipped behavior before the final release.

### Unify operator access and separate metrics network permissions

Use the existing principal-bound operator grant for `/admin/`, `/diag`, and every `/diag/*` route. Operators should be able to use these pages from any network after signing in and completing recent verification. Replace `diagnostics_allowed_cidrs` with `metrics_allowed_cidrs` for `/metrics` only; don't introduce a replacement network restriction for operator pages.

The main implementation surfaces are `app/services/auth/operator_access.py`, the request hooks in `app/app.py`, `app/blueprints/admin.py`, `app/blueprints/assets_diag.py`, `app/blueprints/assets_audit.py`, `app/blueprints/content.py`, `app/services/ai/assists.py`, and the shared configuration builder/catalog. Reuse the existing grant and browser-session services, [operator verification policy](CONFIGURATION.md#operator-settings-console), [logging contracts](docs/logging.md), and [frontend contracts](ARCHITECTURE.md#front-end-design).

- [ ] **1. Establish one operator access policy without an IP gate.**
  - Require an active principal, a current operator grant, an eligible browser-cookie session, and recent credential or signed-provider verification. Team roles, PATs, direct credential headers, and membership in the metrics allowlist must not confer operator access.
  - Remove the CIDR dependency from `/admin/`, its verification page, and provider verification callbacks as well as diagnostics. Recheck grants and session eligibility through the shared service; keep failures closed when authentication storage is unavailable.
  - Preserve the existing `token_required`, `oidc_required`, and `mixed` profile rules. Operator routes remain unavailable in `open`; a dedicated operator sign-in flow for public deployments is outside this task. Document that existing network-only diagnostics in open deployments will no longer be available.
  - Apply `admin_console_reauth_minutes` consistently across operator pages, updating its description to reflect the shared verification window. Preserve absolute session deadlines and verified provider timestamps; activity and page refreshes must not extend verification.
- [ ] **2. Make the metrics allowlist independent and migrate the old setting.**
  - Add `metrics_allowed_cidrs` with an empty-list default. Require both `metrics_enabled` and a matching client IP for `/metrics`, retaining trusted-proxy handling. Scrapes must work without browser sign-in, operator grants, or operator verification.
  - Accept `diagnostics_allowed_cidrs` as a deprecated metrics-only alias for one compatibility release. Normalize the alias within each configuration layer before validation: an explicit canonical key in the same layer wins, including an empty list; higher-priority layers retain their normal precedence. Preserve truthful provenance and issue a bounded deprecation warning without logging CIDR values.
  - Cover legacy-only, canonical-only, both-key, empty-list, and cross-layer configurations. Neither key may authorize an operator page, grant a principal any privilege, or bypass an AI quota. Record the alias removal release in the migration guidance when implementing the change.
  - Update typed configuration, the pure builder, shipped examples, the inspection catalog, standalone validation, and affected fixtures/helpers together. Expose one canonical metrics setting in the operator inventory, with accurate source and migration guidance.
- [ ] **3. Protect the complete diagnostics route family.**
  - Apply the shared policy before handlers read data or launch probes for `/diag`, its JSON representation, `/diag/audit`, `/diag/audit/export`, `/diag/classifier-inspector`, `/diag/classifier-drift`, and `POST /diag/ai-test`. Review the route inventory so no representation or auxiliary endpoint retains network-only access.
  - Keep ineligible principals hidden behind the existing generic denial behavior. Distinguish sign-in from stale verification for eligible browser journeys, while invalid or revoked credentials continue to fail closed.
  - Recheck authorization before export data is emitted and at the applicable streaming boundaries. Preserve bounded exports, redaction, and current disclosure rules; operator inspection must not grant general workspace access or configuration writes.
  - Keep the AI test an explicit, CSRF-protected POST with bounded rate limits. Use the authenticated operator as the identity for its per-operator limit, retaining applicable provider/global protections; rendering or refreshing diagnostics must not run that test.
- [ ] **4. Share verification, privacy, and expired-access behavior.**
  - Generalize the current `/admin/`-specific request matching and return handling. Credential and provider verification must return to the requested operator page using validated same-origin paths, preserving useful audit filters without replaying a POST or probe.
  - Return an explicit unauthorized JSON response and safe verification destination to background data requests instead of redirecting them to an HTML sign-in form. Update diagnostics refreshes, classifier requests, AI-test handling, and audit interactions to understand this contract.
  - Clear displayed diagnostic/audit data on access loss, stop further protected refreshes until access is restored, and ignore stale responses that arrive afterward. Preserve browsing state only while access remains valid; information already downloaded cannot be recalled.
  - Apply the shared private/no-store response policy to operator pages, JSON, exports, redirects, and errors. Keep cookie/session CSRF protections intact through verification and profile changes.
- [ ] **5. Align navigation and remove the unrelated AI quota exemption.**
  - Derive desktop/mobile diagnostics and settings navigation from the same operator eligibility policy. An eligible operator with stale verification should still be able to select a page and complete verification; a metrics-allowed client without a grant must not see operator navigation.
  - Remove the `diagnostics_allowed_cidrs` exemption from ordinary AI-assist workspace quotas, including browser and API callers. Operators follow normal workspace/global limits; any future exemption requires a separate explicit policy and is outside this task.
  - Preserve safe request attribution and existing rate-limit failure behavior. Update messages and documentation that currently describe an IP-based testing exemption.
- [ ] **6. Attribute diagnostic access to the operator.**
  - Include the authenticated principal and existing safe request context in diagnostic view, audit view/export, and AI-test records. Keep event levels, field types, and denial reasons consistent with `docs/logging.md` and the existing operator audit conventions.
  - Record meaningful access and export outcomes without dumping configuration, audit rows, provider responses, credential material, or unreviewed filter values. Avoid multiplying log/audit volume through automatic refreshes, and preserve truthful completion/failure behavior for streamed exports.
- [ ] **7. Qualify authorization, migration, and browser behavior.**
  - Add focused backend coverage on SQLite and disposable Postgres for eligible operators outside the old allowlist, ungranted users inside the metrics allowlist, anonymous callers, disabled principals, revoked grants/credentials, expired sessions, stale verification, invalid authentication, and unavailable authentication storage.
  - Exercise every protected HTML, JSON, export, and POST endpoint, including CSRF failures and revocation before export or probe execution. Verify trusted and spoofed proxy headers affect metrics access correctly and never establish operator authority.
  - Prove an empty metrics allowlist or disabled metrics endpoint leaves eligible operator access available. Prove an allowed scraper needs no browser credentials, while neither the old nor new CIDR setting nor an operator grant bypasses ordinary AI quotas.
  - Cover alias normalization, precedence, explicit empty overrides, deprecation warnings, catalog parity, and standalone-checker/runtime agreement. Qualify restricted-profile transitions and the explicit denial of operator pages in open mode.
  - Add focused Vitest tests for navigation and refresh/expiry handling. Run desktop/mobile Playwright coverage in source and bundle modes across credential, mixed-provider, and provider-only profiles, plus the documented Postgres access-profile matrix. Cover direct links, verification returns, audit filters/exports, safe AI-test interaction, and content clearing after access loss.
  - Generate assets before browser qualification and run the relevant lint, route-contract, configuration, logging, documentation, and asset checks. Keep failure artifacts and CI's flaky-test guards intact.
- [ ] **8. Document the implemented access model and finish the migration.**
  - Update `CONFIGURATION.md` with metrics-only CIDRs, the compatibility alias, operator grant/sign-in/recovery instructions, the shared verification window, open-profile behavior, removal of the AI quota exemption, and the actual restart/recreation requirements.
  - Align README/FEATURES user guidance, ARCHITECTURE's authorization and route contracts, DECISIONS' rationale, `docs/logging.md`, tests/README, and relevant UI guidance. Review other maintained docs and any local release drafts for affected claims without describing unfinished behavior as shipped.
  - Record the completed behavior and compatibility changes in the active changelog, then remove this TODO. Keep a separate follow-up TODO for retiring the deprecated alias after its documented compatibility release.

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

## Feature Enhancements

These are possible future improvements, split by whether they look worth carrying forward.

- **Webhook receiver / `POST /api/v1/intel/<provider>` passthrough.**
  - Worth scoping once outbound notifications and external automation mature. The headless API is the right place to receive webhooks that auto-create or update projects.
- **Cross-workspace Atlas view.**
  - Useful for operators managing multiple workspaces or shared infrastructure, especially now that team mode makes shared context more important.
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
  - VAPID-signed web-push subscription tied to the active personal workspace; subscribe and unsubscribe from the Options sheet.
- **Architecture:**
  - New `app/static/manifest.webmanifest`, icon assets under `app/static/icons/`, and `app/static/sw.js` registered from `app.js` only when the runtime supports it.
  - New `WebPushChannel` in the notifications service; VAPID keys stored as operator config; a workspace-scoped subscription endpoint under the current notification API.
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

### Local accounts for deployments without an identity provider
- Only worth scoping if restricted credentials and managed sign-in leave a real gap: installations that require managed identities but cannot run or reach an identity provider.
- If local authentication is added, allow pseudonymous usernames and do not require email. Define whether registration is disabled, invite-only, or public for each compatible access profile.
- Prefer passkeys where the deployment and browser support them, with downloadable recovery codes and an operator recovery procedure that does not depend on collecting personal information.
- If passwords are supported, use a maintained Argon2id implementation, long-password and password-manager-friendly rules, compromised-password screening, login throttling, safe reset flows, session revocation, and optional MFA. Do not add arbitrary composition rules, password hints, security questions, or periodic rotation.
- Document and test username enumeration, credential stuffing, recovery abuse, lockout denial-of-service, passkey loss, and operator reset boundaries before enabling local registration.

### Operator admin console for instance settings

Consider browser-side proposal validation, copyable configuration snippets, and applying settings without host shell access as additions to the [read-only operator console and local validator](CONFIGURATION.md#operator-settings-console).

- Reuse the read-only console's operator authorization, settings catalog, redaction, and shared configuration builder. Define a separate permission for configuration writes; an inspection grant must not silently gain write access after an upgrade.
- Keep host files and environment variables outside the app's write boundary. Store any admin overrides in an `instance_settings` table on SQLite and Postgres with value, revision, changed-by principal and credential, and timestamps. Explicit environment and operator-local YAML values should win and lock the corresponding controls; shipped YAML remains an overridable default. Provide a reset action for admin-owned values.
- Keep access profile, OIDC, database and Files backend, interactive PTY, raw-packet scanning, intrusive-action switches, restricted command-input CIDRs, proxy/diagnostics trust, share redaction policy, AI egress policy, ports, image, and every secret value host-owned. Continue using environment variable references for SMTP, ZAP, and OAST secrets.
- Begin any editable allowlist with branding, MOTD, default theme, and welcome/tour tuning. Retention can delete saved evidence, and output/Files limits, notification retries, scheduler/watchers, and assessment concurrency can affect existing work or resource use. Treat those as separate decisions with impact previews and suitable confirmation.
- Validate proposed changes through the shared builder, reject stale revisions, and commit related changes and their `instance.config_change` audit event atomically. Audit key names and redacted before/after values. Require a recent managed browser session and explicit write permission; leave open-profile writes unsupported.
- Design database bootstrap before adding database-backed settings: host configuration must select the backend and initialize or migrate the settings table before operational overrides load. Specify missing-table, unavailable-database, renamed/removed-key, and newly invalid-value behavior. Include a local recovery command that can inspect and revert overrides when the web app cannot start.
- Track the saved configuration revision separately from the revision loaded by each affected process. Cover web workers, scheduler, notifications, optional AI, ZAP, and OAST workers; offline or unobserved consumers remain pending or unknown. A successful save or reload request must not claim that all consumers applied the change.
- Qualify graceful web-worker reload before exposing it, including active commands, long-lived streams, failed replacement workers, and mixed revisions during transition. Retain the host-file snapshot limitation. Worker/container changes should provide precise host commands; do not add a Docker socket to the app.
- Keep live apply separate. It would need validated snapshot replacement while preserving the `CFG` object held by importers, explicit treatment of values cached outside that object, and coordinated process acknowledgements. Merely changing `CFG` cannot update startup-only consumers.
- Include settings persistence in schema manifests, backup, restore, and Postgres migration coverage. Test authorization, precedence, recovery, atomic audit, revision conflicts, and partial apply on both backends, with desktop/mobile browser coverage in both asset modes.
- Keep content-catalog editing separate: `commands.yaml`, workflows, themes, and assessment profiles need their own validation and ownership rules. In particular, `commands.yaml` is part of the command-policy boundary.

---

## Architecture

### Interactive PTY transport future-state
- Revisit whether the current Redis-brokered SSE plus POST input/resize transport should move to WebSockets after real use.
- The current model keeps deployment simple and avoids a WebSocket runtime, but a bidirectional socket could reduce input latency and simplify the modal terminal stream once PTY usage grows.
