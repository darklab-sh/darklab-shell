# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Remove the legacy metrics CIDR alias in 3.1.0](#remove-the-legacy-metrics-cidr-alias-in-310)
  - [Manage principal access and validate configuration through darklab-deploy](#manage-principal-access-and-validate-configuration-through-darklab-deploy)
  - [Autoscale ARM64 release runners on EC2 Spot](#autoscale-arm64-release-runners-on-ec2-spot)
- [Feature Enhancements](#feature-enhancements)
- [Technical Debt](#technical-debt)
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

### Remove the legacy metrics CIDR alias in 3.1.0

After the 3.0.1 compatibility release, remove `diagnostics_allowed_cidrs` alias normalization and its deprecation warning. Keep `metrics_allowed_cidrs` as the sole scrape allowlist, with an empty-list default and no operator-access or AI-quota effect. Update migration guidance, the inspection catalog, and compatibility tests; verify canonical configuration precedence and metrics/operator isolation remain covered.

### Manage principal access and validate configuration through darklab-deploy

Make `darklab-deploy access <command> [options]` and `darklab-deploy config check [options]` the normal operator interfaces for principal access and configuration validation in managed installations. Keep `scripts/operations/manage_principal_access.py` and `scripts/operations/check_instance_config.py` packaged under `/app/tools/`; the deployment helper should select the correct deployment and handle invocation while the existing Python services retain responsibility for access changes, transactions, audit records, configuration rules, and safe output.

The main implementation surfaces are `deploy/darklab-deploy.sh.in`, the two packaged Python tools, `scripts/release/build_release_payload.py`, and `tests/py/test_production_install.py`. Follow the existing [principal access operations](CONFIGURATION.md#principal-access-operations), [configuration validation contract](CONFIGURATION.md#validating-instance-configuration), deployment integrity checks, and Compose override handling. This work can land independently of the operator-page access changes above.

- [ ] **1. Add a discoverable access command with the existing operations.**
  - Support the script's current subcommands and options: `bootstrap`, `status`, `operator-grant`, `operator-status`, `operator-revoke`, `issue`, `recover`, `expiry`, `rotate`, `revoke`, `disable`, `enable`, `revoke-all-sessions`, and `rotate-session-signing-key`. Keep their names and required confirmations consistent with direct script use.
  - Add top-level and access-specific help with common examples such as `./darklab-deploy access operator-grant prn_example` and `./darklab-deploy access status prn_example`. Basic help must work without a running container or database access; keep detailed option validation in the Python parser.
  - Forward arguments as separate arguments, preserving spaces, repeated `--scope` options, and literal shell characters. Preserve the script's exit status and safe JSON output, sending deployment diagnostics to stderr so stdout remains usable by automation.
- [ ] **2. Share deployment selection and invoke access operations in the running service.**
  - Reuse managed-file and pinned-image validation plus `deployment_compose` with the installation's `.env`, `compose.yaml`, and optional `compose.operator.yaml`. Resolve the deployment relative to `darklab-deploy`, so invocation from another working directory still targets the intended installation.
  - Execute the packaged access script through the running `shell` service with `exec -T`, retaining the container's configured database, encryption keys, local configuration, and operator execution identity. Keep database access and credential logic inside the container.
  - Report missing Docker access, invalid managed files, missing or stopped services, and unavailable tooling clearly. Permit access operations in an unhealthy but running container when the tool itself can operate; don't require a successful web health check or implicitly start, recreate, upgrade, or retry a mutation. Configuration checking uses the separate disposable-container path below.
  - Preserve the distinction between host operator authority and browser operator grants. Bootstrap must still require a fresh `token_required` deployment, and neither bootstrap nor ordinary credential issuance should automatically grant operator access. Keep recovery confirmations, lockout protection, disabled-principal rules, and suspended-work behavior intact.
- [ ] **3. Make one-time credential retrieval part of the command.**
  - Add a wrapper-owned `--output-file HOST_PATH` option for `bootstrap`, `issue`, `rotate`, and `recover`, for example `./darklab-deploy access bootstrap --output-file ./initial-access.credential`. Resolve relative output paths against the caller's working directory. Preserve the underlying `--secret-file` container-path contract for direct or advanced use, and reject combining the two options.
  - Validate and reserve a new private host destination before invoking a mutation. Use restrictive permissions, reject existing destinations and symlinks, and preserve those protections during transfer. Have the Python tool write to a unique private container file, then securely retrieve it through the same deployment connection without requiring host access to Docker's filesystem or assuming `/data` is a particular host bind mount.
  - Keep credential material out of arguments, environment variables, terminal output, logs, and JSON metadata. Report the host output path only after a successful transfer; remove the temporary container copy after host persistence succeeds.
  - Handle interruption and copy failures explicitly: remove incomplete host output, retain the private container copy if access has already been issued, and report that the mutation may have completed. Provide a deployment-helper retrieval path for that retained file without issuing another credential or repeating recovery. Don't describe a failed transfer as a rolled-back access change.
- [ ] **4. Add configuration checks that work before application startup.**
  - Support `./darklab-deploy config check`, `./darklab-deploy config check --json --strict`, and `./darklab-deploy config check --local-yaml ./candidate.yaml`. Add discoverable help and delegate configuration validation to the packaged Python checker rather than duplicating its rules in shell.
  - Evaluate inputs in a disposable container using the installed image and shared Compose selection, with `--rm`, `--no-deps`, no TTY, and an explicit Python entrypoint. Work with a stopped deployment or configuration that prevents application startup, without starting the web service, dependencies, or normal entrypoint maintenance.
  - Supply the current installation's local YAML explicitly when bypassing entrypoint staging, retaining the image's shipped defaults and Compose-supplied environment overrides. A missing optional local overlay should keep its existing meaning. Preserve normal configuration precedence; an environment override can still win over candidate YAML.
  - Treat the wrapper's `--local-yaml` argument as a host path, resolving relative paths against the caller's working directory and translating it to an explicit read-only container input. Reject missing or unreadable candidates without creating a directory at the requested path. Support the existing daemon-visible deployment-path handling and keep temporary candidate copies private and short-lived.
  - Preserve reviewed redaction, provenance, warnings, versioned JSON, and checker exit codes: `0` for valid input, `1` for warnings under `--strict`, and `2` for invalid or unreadable input. Keep wrapper diagnostics out of JSON stdout and avoid printing raw YAML, environment values, or unreviewed exception text.
  - Label the result as a fresh evaluation of supplied inputs. Explain that running workers may have different loaded settings and that host-only settings still need Compose validation. Checking must not write configuration, create encryption keys, initialize or migrate a database, or apply changes; clean up temporary containers and anonymous volumes on success, failure, and interruption.
- [ ] **5. Qualify dispatch, security, and real container behavior.**
  - Extend deployment-helper tests for every subcommand, argument forwarding, exit status, clean JSON stdout, help, invocation outside the install directory, paths with spaces, Compose overrides, and selecting the intended installation when several exist. Cover Docker failures, stopped services, integrity/image mismatches, and missing packaged tooling without accidental mutations.
  - Cover secure host output, existing-file and symlink rejection before issuance, file permissions, transfer failure, interruption, retained-file retrieval, and cleanup. Assert secrets never appear in captured stdout/stderr or command logs, and that failed transfers don't trigger an automatic retry.
  - Run focused principal lifecycle and operator-grant coverage on SQLite and disposable Postgres. Exercise bootstrap, status, grant/status/revoke, and credential retrieval through the generated deployment helper against disposable release-style installations; retain coverage for recovery confirmations and last-credential protection.
  - Cover configuration checks with running, stopped, and broken-startup installations; current and candidate YAML; an absent optional overlay; environment precedence; operator Compose overrides; paths with spaces; unreadable candidates; strict warnings; invalid input; JSON redaction; and exact checker exit codes. Prove the command bypasses normal startup, leaves configuration and database state unchanged, and removes temporary resources after failure or interruption.
  - Verify the release bundle renders and checksums the updated helper and the image still contains both Python tools. Exercise configuration checking through the generated helper against a disposable release-style installation. Run relevant production-install, configuration-checker, documentation, shell-lint, and release smoke checks; ensure temporary containers and anonymous volumes are removed if the qualification fixtures create them.
- [ ] **6. Update operator guidance and complete the TODO.**
  - Make deployment-helper commands the primary managed-install examples in `CONFIGURATION.md` and `docs/api.md`, including operator grants, first access, PAT issuance, rotation, recovery, and session revocation. Explain host versus container file paths, failed-transfer recovery, running-container requirements, and how to identify the correct principal before changing access.
  - Make `darklab-deploy config check` the primary managed-install validation example in `CONFIGURATION.md`, covering ordinary and strict JSON checks, host-side candidate files, checks while the application is stopped, environment precedence, and the difference between checked inputs and a running worker's loaded settings. Explain that a successful check does not apply configuration changes.
  - Keep direct container invocation documented as a development or troubleshooting path. Update relevant README/FEATURES guidance, architecture and testing references, helper usage output, and any local release drafts. Keep the existing browser sign-in and operator-verification requirements clear.
  - Record the implemented behavior in the active changelog and remove this TODO after qualification.

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

## Technical Debt

No technical debt items are currently tracked.

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
