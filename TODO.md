# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Autoscale ARM64 release runners on EC2 Spot](#autoscale-arm64-release-runners-on-ec2-spot)
  - [Bounded assessment plan runner](#bounded-assessment-plan-runner)
  - [Headless assessment and evidence parity](#headless-assessment-and-evidence-parity)
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

### Bounded assessment plan runner

Add a cycle-level **Run assessment plan** action that compiles the cycle's frozen checks into a reviewed, bounded, and resumable batch. This work builds on the shipped Project-scoped probe catalog, target resolution, public plan, policy, confirmation, and ordinary-run services. It must not become a literal **Run all** button: a naive launch across the allowed Project scale could repeat scans, overload the queue, or probe discovered infrastructure the assessor did not intend to include.

#### Final decisions

These decisions define the implementation contract. Record each one in `DECISIONS.md` when its corresponding behavior lands:

- **Execution and coverage identities:** Deduplicate across check ids only when the canonical execution key—exact target entity id/type/value, action, profile, credential-free bounds, and display command—is byte-for-byte identical. Store every assessment/check/frozen-rule relationship under a separate coverage-mapping key and require ordinary evidence reconciliation to prove each mapping independently. Leave the retest queue's existing check-specific grouping unchanged.
- **Selection policy:** Select safe actions by default and support standard actions only in a separate unchecked group. Require an additional confirmation that states the selected targets, command count, fan-out, request/time limits, and credential classification. Exclude intrusive, destructive, credentialed, ZAP, OAST, takeover-confirmation, and Schemathesis work from batches.
- **Coordinator and item limits:** Keep the workflow ceiling unchanged and add one durable assessment-batch parent that partitions confirmed items into ordered chunks of at most 32 children. Default to 128 selected items per batch with an operator-configurable hard ceiling no higher than 512; require another preview and confirmation beyond that limit. Keep four attempts for transient claim/launch failures inside a chunk. Reject, never truncate, any oversized preview or execution.
- **Concurrency:** Default to eight active children per batch, a fixed limit of one active child per target, sixteen per owner, and thirty-two instance-wide across assessment batches. Hard-cap those values at eight, one, thirty-two, and sixty-four respectively. Do not expose per-target concurrency as an operator setting; serial work against one target is a safety invariant. Keep batch, owner, and instance limits configurable within their caps. Apply the fairness gate only to assessment-batch claims so ordinary interactive and workflow runs keep their current behavior, and enforce the most restrictive applicable limit before claiming a child.
- **Events:** Add a dedicated assessment-batch event table with one monotonically increasing sequence per user-facing batch parent. Store immutable, sanitized item/chunk transitions, retain them with the batch, page by sequence, and include original/retry execution ids so reconnect and follow resume after the last acknowledged sequence without changing existing workflow events.
- **Preview transport:** Store the selected preview server-side for 15 minutes. Return a compact summary and item pages of at most 100 entries and 1 MiB each, compute one SHA-256 digest over the complete stable-ordered snapshot, and start with only `preview_id`, digest, and confirmation. Stream or chunk database reads and digest construction within explicit query and memory budgets; never materialize or return an unbounded 50,000-check payload.
- **Cancellation:** Move the batch to `canceling`, stop claims immediately, mark never-launched items canceled, and send the normal cancellation request to every active child. Do not declare the batch terminal while a child is still running; finish as `canceled` after all children settle and retain succeeded, failed, unavailable, canceled, and could-not-cancel counts so the result never implies completed work was erased or an active process was stopped when it was not.
- **Retry and resume:** Keep executions immutable. A user retry creates a new batch linked to its source, generates a current preview, and requires fresh confirmation for failed, unavailable-now-resolved, interrupted, or canceled-before-launch items. Never rerun succeeded or manually excluded items by default. Treat changed profiles, targets, policy, or cycle state as a new preview and lineage entry rather than reopening old rows.
- **Lifecycle conflicts:** When assessment complete, archive, or delete—or Project delete—is requested while a matching batch is queued or running, atomically move the batch toward cancellation, stop new claims, and return an actionable cancellation-pending response with the batch id. Do not queue or silently apply the lifecycle mutation: require a fresh request after every active child settles so permissions, state, and intent are revalidated. If the batch is already canceling, return the same stable response. Allow the lifecycle change after the batch is terminal while retaining ordinary child runs and sanitized batch provenance according to existing retention rules.
- **Notifications:** Suppress per-child completion notifications when a run carries batch context and emit one bounded summary when the batch reaches a terminal state. Include succeeded, failed, unavailable, canceled, and could-not-cancel counts plus the batch link; honor the existing notification preference. Treat each retry as a new batch with its own summary and keep progress notifications off by default.
- **Product and command names:** Use **assessment batch** as the execution noun. Keep **Run assessment plan** as the browser action that opens a batch preview, label the durable monitor **Assessment batch**, and use `darklab assessment batch plan|start|list|show|follow|cancel|retry` externally. Use the same `batch_id`, status names, and action labels in browser and API responses.

#### Phase 0 — Freeze the batch contract and reuse boundary

- [ ] Freeze the final decisions above in contract tests and record each decision in `DECISIONS.md` when its corresponding runtime behavior is introduced.
- [ ] Adapt the existing durable workflow execution and fan-out lifecycle for batch coordination. Reuse its bounded policy normalization, child claim/launch state, checkpoints, cancellation, parent completion, run binding, and startup recovery rather than creating a second generic coordinator. Do not reuse its homogeneous command-template and string-collection expansion layer for heterogeneous assessment items.
- [ ] Add an explicit execution-kind discriminator before storing assessment batches in workflow execution records. Make list/detail queries, active quotas, runtime limits, retention, recovery dispatch, metrics, audit/provenance labels, and the existing workflow UI kind-aware so an assessment batch is never presented or recovered as a saved workflow.
- [ ] Implement one durable user-facing assessment-batch parent that partitions its confirmed items into ordered chunks of at most 32 children. Give the parent atomic creation, cross-chunk cancellation, retry lineage, event ordering, progress rollups, and deterministic terminal-state derivation before adding assessment persistence.
- [ ] Make child initialization execution-kind aware. Existing workflows must still require a frozen `for_each` step, while assessment batches initialize ordinals only from their persisted item or chunk snapshot and never fabricate a workflow definition merely to satisfy the current initializer.
- [ ] Define a narrow assessment-batch adapter and document which completed probe services it calls. Prohibit batch-only forks of catalog, target, public plan, policy, digest, and ordinary-run launch logic.
- [ ] Define the adapter boundary around persisted heterogeneous item identities and revalidated child launch specifications. Each child can have its own action, target, profile, bounds, and check mappings; no command may be re-derived from one shared template plus a string substitution.
- [ ] Define a complete surface-neutral child launch specification containing the execution command, public display command, private values, and any trusted run-start context. Refactor the existing fan-out child launch so its downstream run binding and failure handling accept that specification directly. Keep workflow template rendering and collection substitution in a workflow-only adapter that produces the same specification and preserves existing workflow behavior.
- [ ] Choose the batch module layout before adding files and extend the architecture size-ratchet coverage in the same change. Give every new top-level `app/services/assessments/*.py` module an explicit `ModuleSizeBudget`. If the implementation uses an `app/services/assessments/batch/` subpackage, add that family to the required classifier patterns and budget every module instead of relying on the current non-recursive glob to skip it. Add explicit budgets for new workflow-side launch-specification and adapter modules even though `app/services/workflows/*.py` is not currently a required family.
- [ ] Keep `fanout_child_run.py` within its current 185-line budget and `fanout_launch.py` within its current 170-line budget by moving template rendering and the surface-neutral launch behavior into focused modules. Do not raise either baseline merely to fit the refactor.
- [ ] Extract reusable retest grouping and shared-batch policy helpers instead of copying private `_group_key` or `_batch_reason` behavior. Preserve the existing retest queue's check-specific public behavior while the assessment batch uses the final cross-check execution key and separate safe-default/standard-confirmation policy recorded in `DECISIONS.md`.
- [ ] Define the batch preview, server-owned preview snapshot, confirmed execution, item, check mapping, event, progress rollup, cancellation, retry, duration estimate, and error schemas independently of the browser and database backend.
- [ ] Make the reused workflow child/checkpoint lifecycle the authoritative persisted source for pending, launching/running, completed, failed, skipped, and canceled execution state. Represent assessment-only states such as unavailable or stale scope through fixed reason/error classifications and derived API rollups rather than a second mutable item status. Define the durable batch parent's state as a deterministic rollup over its authoritative chunk children.
- [ ] Define the dedicated assessment-batch event contract and require immutable, monotonically ordered parent-sequence events for claim, launch, run binding, completion, failure, cancellation, retry, recovery, and chunk/parent transitions. The existing step-derived workflow event view is not sufficient for live item progress.
- [ ] Define quotas, retention, expiry, maximum checks per item, and maximum simultaneously active batches per owner before accepting persisted work. Default to at most 128 selected items per batch and allow operators to lower or raise that value only within a hard ceiling of 512. Respect the configured Project ceilings of 200 targets and 50,000 assessment checks, including their documented `0`-means-unlimited behavior, while keeping the separate finite batch cap mandatory so one preview cannot become an unbounded launch.
- [ ] Define the capability matrix: assessment viewers can preview and inspect plans; only roles with `RUN_COMMANDS` can start, cancel, or retry; assessment lifecycle permissions remain unchanged.
- [ ] Define the batch-aware notification context passed through ordinary run finalization. Suppress child completion notifications for batch runs and emit one preference-aware bounded terminal summary without changing notifications for unrelated runs.
- [ ] Add contract tests for schemas, execution-kind isolation, authoritative transitions, per-item event cursors, 15-minute preview snapshots, 100-item/1-MiB pages, notification suppression and summaries, capability rules, 128-item defaults and 512-item hard ceilings, concurrency defaults and caps, and the rule that preview is side-effect free.

#### Phase 1 — Build the read-only cycle plan compiler

- [ ] Load one owner-scoped active assessment and its frozen applicable checks, current manual states, current evidence coverage, confirmed targets, HTTP-role/profile metadata, and current feature/policy gates. Read profile metadata only to classify credentialed checks and explain why they remain individual.
- [ ] Exclude already covered, manually excluded, unavailable-evidence, non-runnable, ZAP, OAST, destructive, intrusive, credentialed, takeover-confirmation, and Schemathesis checks from batch selection while still explaining them in preview totals. The batch runner never materializes protected profile values, allocates callback resources, selects takeover templates, or binds saved API artifacts; those actions remain available through individual cycle launches.
- [ ] Select safe checks by default. Put supported standard checks in a separate unchecked group and include them only after the assessor accepts the separately disclosed standard-action confirmation. Never batch intrusive, destructive, credentialed, ZAP, OAST, takeover-confirmation, or Schemathesis checks.
- [ ] Let the assessor include/exclude confirmed targets and categories. Identify likely third-party and infrastructure targets with explainable metadata, but require the assessor—not a heuristic—to make the final selection.
- [ ] Compile each selected check through the shared probe plan service, then apply the extracted retest policy helpers and the separate execution-deduplication and coverage-mapping identities. Preserve an exact mapping from every shared plan item to the frozen checks and targets it may satisfy without adding check id to a cross-check execution key.
- [ ] Create a bounded, server-owned immutable preview snapshot that expires after 15 minutes and includes selected targets, exact display commands, policy levels, bounds, estimated run count, potential covered-check count, unavailable/skipped reasons, concurrency choices, a conservative completion window, and one SHA-256 digest over every launch-relevant item in stable order. Derive the window from per-command duration bounds, 32-item chunking, selected concurrency, and per-target serialization; label it as a planning estimate rather than a completion promise. Return a compact summary plus pages of at most 100 items and 1 MiB; start accepts only `preview_id`, digest, and confirmation, never a client-echoed item plan.
- [ ] Enforce maximum candidates, selected items, checks per item, page size, response bytes, snapshot age, query count, and planning memory. Reject an oversized preview with an actionable reason rather than building an unbounded in-memory payload.
- [ ] Keep preview read-only: do not create execution rows, runs, callbacks, ZAP jobs, temporary credential files, audit mutations, or external requests.
- [ ] Add unit and route tests for empty cycles, mixed target types, manual states, existing evidence, retest-policy parity, the separate standard-action confirmation, cross-check execution deduplication, coverage mappings, takeover/Schemathesis exclusion, third-party exclusions, changed targets, unavailable profiles, paged snapshots, deterministic cross-page digests, 15-minute expiry, response/query/memory bounds, completion-window calculations, and confirmed-start identifiers. Exercise the configured 200-target and 50,000-check Project boundaries with efficient fixtures, plus 32-item, 33-item, 128-item, 129-item, 512-item, and 513-item cases. Assert exact preview/execution item-count parity through lossless chunking or explicit rejection; silent truncation is never valid.

#### Phase 2 — Add durable execution and item persistence

- [ ] Add dedicated backend-neutral assessment-batch item and item-to-check mapping records. They are required because the existing value-free workflow child row cannot represent heterogeneous commands, actions, targets, profiles, bounds, or coverage mappings. Bind each assessment item to the reused workflow child lifecycle without duplicating its attempt, run, cancellation, or terminal state.
- [ ] Persist the execution kind, selected coordinator/chunk hierarchy, server-owned preview snapshot metadata, and durable per-item events required by the Phase 0 contracts. Add kind- and parent-aware indexes for active quotas, recovery, cleanup, event paging, and Project/assessment lifecycle checks.
- [ ] Keep owner, Project, actor, concurrency policy, lifecycle status, counts, timestamps, cancellation intent, child run ids, and generic failure state in the reused workflow records. Store only the assessment identity, frozen profile/version identity, preview digest, public plan snapshot, selected target/check ids, per-item action/target/profile/bounds identity, item-to-check mappings, retry lineage, and sanitized assessment-specific failure codes that those records cannot represent.
- [ ] Do not store resolved secrets, private arguments, temporary file paths, callback values, raw command output, or mutable copies of assessment evidence.
- [ ] Reuse workflow owner/team, child claim, session-token migration, retention, and compare-and-set behavior through kind-aware adapters. Do not reuse workflow list, quota, recovery, event, or provenance queries until they filter/dispatch by execution kind. Add only the indexes, foreign-key cleanup, Project/assessment lifecycle guards, and quotas required by the assessment mapping.
- [ ] Keep transitions and transactions inside the existing workflow lifecycle primitives so multiple workers, cancellation, finalization, and startup recovery cannot launch an item twice or overwrite newer state.
- [ ] Add migration, rollback/compatibility, adapter CRUD, mapping, quota, cascade, race, workflow-regression, and backend-parity tests.

#### Phase 3 — Implement the bounded execution coordinator

- [ ] Create an execution only after the server regenerates the preview, verifies the supplied digest, enforces safe-by-default selection plus the separate standard-action confirmation, and rechecks owner, role, assessment, Project, targets, profiles, and policy.
- [ ] Drive execution through the reusable workflow child claim, checkpoint, cancellation, parent-completion, and recovery primitives. The assessment adapter must load one persisted heterogeneous item and, after revalidation, render its complete child launch specification; it must not call the workflow string-collection expansion or step-template display rendering paths. Create every confirmed item losslessly under one durable parent with ordered chunks of at most 32 children, and reject more than the configured limit without truncation.
- [ ] Add the assessment-batch fairness gate before child claim. Default to eight active children per batch, one per target, sixteen per owner, and thirty-two instance-wide; enforce hard caps of eight, one, thirty-two, and sixty-four respectively. Keep the per-target value fixed and apply the gate only to assessment-batch claims.
- [ ] Revalidate each claimed item through the shared probe service immediately before launch rather than trusting the stored display command.
- [ ] Launch every item through the refactored shared child-run binding path, passing the execution's `link_project_id`, batch notification context, and complete revalidated launch specification, then bind its run id atomically. Reuse `bind_fanout_child_run`, launch-failure classification, and failed-claim settlement without asking the workflow adapter to reconstruct an assessment command. Let the normal run pipeline own validation, streaming, cancellation, History, and structured evidence finalization while batch context suppresses child completion notifications in favor of one terminal summary.
- [ ] Preserve the confirmed public display command exactly as the run's stored `runs.command`. Treat any mismatch between the regenerated plan, launch specification, and persisted command as a failed launch because command-root and target evidence matching depend on that value.
- [ ] Continue scheduling after an individual failure. Classify stale scope, policy changes, missing profiles, queue failures, command validation failures, timeouts, and run failures separately so retry behavior stays explainable.
- [ ] Consume run-finalization outcomes idempotently, advance item/execution/chunk rollups, append immutable sanitized item events under one monotonically increasing parent sequence, suppress child completion notifications, emit one preference-aware bounded terminal summary, and preserve completed evidence even if later items fail or the batch is canceled.
- [ ] On cancellation, move the batch to `canceling`, stop claims immediately, mark never-launched items canceled, and send the normal cancellation request to every active child. Do not declare the batch terminal until all children settle; retain succeeded, failed, unavailable, canceled, and could-not-cancel counts without implying that completed work was erased or an active process stopped when it did not.
- [ ] Handle lifecycle conflicts atomically. A complete, archive, assessment-delete, or Project-delete request against a queued or running matching batch must record cancellation intent, stop claims, and return the stable cancellation-pending response with the batch id. Return the same response while already canceling. Do not apply or retain a deferred lifecycle mutation; require a fresh request after settlement so permissions, state, and intent are revalidated.
- [ ] Enforce the lifecycle-cancellation policy in both the Project deletion service and the batch claim boundary. Stop new claims and launches before Project deletion can proceed, settle pending items, and reconcile active children without relying on workflow foreign-key cascades that do not exist. Only a fresh Project-delete request after the batch becomes terminal may remove the Project.
- [ ] Extend existing workflow startup recovery for queued, launching, running, and canceling assessment batches. Reattach known runs, use the existing launching-child reset behavior, safely release abandoned claims, fail malformed snapshots, enforce maximum runtime without duplicate launch, and move a batch whose Project or assessment no longer exists into the defined non-runnable terminal state and reason without launching another child.
- [ ] Keep batch executions immutable. Retry creates a new batch linked to its source and, after a fresh preview and confirmation, includes only eligible failed, unavailable-now-resolved, interrupted, or canceled-before-launch items. Do not rerun succeeded or manually excluded items by default; represent changed profiles, targets, policy, or cycle state as a new preview and lineage entry.
- [ ] Add heterogeneous-command, preview-to-`runs.command` equality, coverage reconciliation, workflow-adapter regression, execution-kind isolation, authoritative-status, child-event cursor, notification summary/suppression, exact item-count, 32/33-child or cross-chunk boundary, concurrency, fairness, double-claim, finalize/cancel race, Project-deletion/claim races, missing-Project recovery, broker failure, worker loss, restart recovery, partial success, timeout, stale plan, changed target, and retry-lineage tests on SQLite and PostgreSQL.

#### Phase 4 — Add browser and API lifecycle routes

- [ ] Add browser and API v1 routes for preview, start, list, detail, bounded events, cancel, and retry/resume using one shared service layer and the normal error envelopes.
- [ ] Keep preview available to viewers and writes restricted to `RUN_COMMANDS`. Apply CSRF/session rules to browser routes and token/team-scope rules to API v1.
- [ ] Return stable rollups for pending, launching, running, canceling, succeeded, failed, unavailable, canceled, skipped, and could-not-cancel outcomes plus covered-check potential, target counts, and whether more events/items remain.
- [ ] Make start idempotent for a bounded client request key or return a clear conflict so browser retries cannot create duplicate executions.
- [ ] Record audit events for start, cancel, and retry with safe counts, actor, Project, assessment, and execution id. Add metrics and structured lifecycle logs without target values, commands, or protected data in labels.
- [ ] Give every new `projects*.py` and `api_v1*.py` route module an architecture size budget when it is introduced. Update the exact OpenAPI helper-package allowlist in the same change as any new helper module rather than deferring these hard CI contracts to final qualification.
- [ ] Extend OpenAPI schemas, route inventories, API examples, authentication/capability tests, request-size tests, pagination/event-cursor tests, idempotency tests, and PostgreSQL parity coverage.

#### Phase 5 — Build the assessment-plan browser experience

- [ ] Add **Run assessment plan** to an active cycle only when the user can run commands. Do not hide preview from viewers; show a clear read-only state instead.
- [ ] Build a preview surface that shows target and category selection, exact command groups, policy chips, bounds, estimated runs, the conservative completion window, potential check coverage, deduplication, and unavailable/skipped explanations. Make clear that the duration is an estimate and that target responsiveness, retries, cancellation settlement, and queue pressure can change it.
- [ ] Select safe items by default. Present standard items as a separate unchecked group with an explicit target, fan-out, request, time, and credential-classification confirmation before they enter the final digest. Explain that intrusive, destructive, credentialed, ZAP, OAST, takeover-confirmation, and Schemathesis actions remain individual.
- [ ] Make third-party and infrastructure candidates easy to identify and deselect without silently deciding scope for the assessor. Provide select-all/clear controls that remain usable across the configured Project target limit, including the default ceiling of 200 targets.
- [ ] After start, replace the preview with live progress backed by durable polling/events. Show counts and per-item state, link child runs to History, preserve progress across tab switches/reloads, and keep terminal run activity separate from batch-control state.
- [ ] Add cancel and retry-failed/unfinished actions with clear consequences. When a lifecycle action initiates batch cancellation, link to the affected batch, explain that the lifecycle change was not yet applied, and make the required fresh action after settlement obvious. Never erase completed child runs or evidence when an execution is canceled or retried.
- [ ] Follow the Front End Design contracts for shared buttons, badges, filters, dialogs, focus restoration, keyboard access, reduced motion, responsive layout, theme tokens, empty/error/loading states, and safe text rendering.
- [ ] Register every new lazy Project Assessment module in both `assets.config.json` and `app/templates/index.html`, then run `npm run assets:sync`, `npm run assets:check`, and `npm run assets:inventory:check` in the same implementation phase.
- [ ] Add JavaScript unit and source/bundle Playwright coverage for preview selection, large plans, the safe-only path, the separate standard-confirmation path, stale-preview refresh, start, reload recovery, live progress, partial failure, cancel, retry, permissions, mobile layout, keyboard navigation, and no-secret rendering.

#### Phase 6 — Add complete external CLI control

- [ ] Add `darklab assessment batch plan|start|list|show|follow|cancel|retry` for plan preview, confirmed start, status and event following, cancellation, and immutable retry lineage.
- [ ] Keep preview as the default and require `--confirm` for start and retry. Support explicit target/category selection, safe-by-default selection, the separate standard-action confirmation, concurrency values within server caps, and text/JSON output.
- [ ] Keep the external client thin: it submits selections and digests, follows API state, and formats responses, while the server owns planning, deduplication, scope, policy, launch, and recovery.
- [ ] Return stable exit behavior for complete success, partial success, canceled work, unavailable-only plans, stale confirmation, permission failures, server incompatibility, and interrupted follow mode.
- [ ] Add parser, help, request/response, follow interruption, pagination, error-envelope, packaging, and live API contract tests.

#### Phase 7 — Integrate evidence, findings, packages, and cycle lifecycle

- [ ] Let each successful child run pass through existing run-scoped evidence extraction and assessment reconciliation. The execution/check mapping provides provenance but never marks a check covered by itself.
- [ ] Confirm deduplicated runs can satisfy only the mapped frozen rules whose exact target, command/evidence type, completion, output, and policy contracts independently match.
- [ ] Surface batch execution and child-run provenance in assessment recent evidence, History, reports, and evidence packages where it helps explain how coverage was produced, without copying command output into batch rows.
- [ ] Reconcile findings and retest state through existing finalization paths. A failed or canceled item must not suppress valid evidence from a successful sibling.
- [ ] Enforce the final cancellation-pending behavior for assessment complete, archive, and delete and for Project delete. Document the stable response, batch link, settlement path, required fresh lifecycle request, and recovery behavior. Project deletion must clean terminal coordinator state without deleting retained runs contrary to existing Project rules.
- [ ] Add evidence, negative-evidence, deduplication, finding, report/package provenance, lifecycle-conflict, archive/delete, and retention tests across both database backends.

#### Phase 8 — Harden, document, qualify, and close the batch runner

- [ ] Add dashboards or metrics for active executions, queue depth, launch latency, per-outcome items, partial/canceled executions, stale/scope/policy rejections, recovery outcomes, and concurrency deferrals. Keep labels bounded and secrets or target values out.
- [ ] Add operator controls and document the 128-item default and 512-item ceiling; eight-per-batch default/cap; sixteen-per-owner default and thirty-two cap; thirty-two-instance default and sixty-four cap; fixed one-child-per-target safety limit; four-attempt chunk behavior; 15-minute preview lifetime; 100-item/1-MiB preview pages; retention; maximum runtime; polling/event limits; and cleanup. Validate configuration ranges and startup behavior.
- [ ] Run the full Python, JavaScript, source/bundle Playwright, PostgreSQL, container smoke, security, lint, dependency, asset inventory, OpenAPI, and documentation gates. Stress concurrent batches and repeat race/recovery suites.
- [ ] Update `README.md`, `FEATURES.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`, `DECISIONS.md`, `docs/api.md`, the OpenAPI snapshot, assessment/operator guides, `tests/README.md`, `CONTRIBUTING.md`, `THEME.md`, `CHANGELOG.md`, and current merge-request/release drafts.
- [ ] Update documented test totals and the complete test appendix, then pass documentation link, anchor, route-inventory, configuration-inventory, logging-inventory, and test-count contracts.
- [ ] Qualify personal/team viewer, operator, admin, and owner flows with small, mixed-policy, large, partial-failure, cancellation, restart-recovery, retry, and changed-scope cycles. Confirm no preview allocates resources and no batch execution launches an excluded, intrusive, credentialed, ZAP, OAST, takeover-confirmation, or Schemathesis item.
- [ ] Remove this TODO only after all phases are complete, production configuration and recovery are documented, the shared probe services remain the sole plan/launch implementation, and the full pipeline passes.

### Headless assessment and evidence parity

Close the adjacent API and external CLI gaps independently of the one-off-probe and bounded-runner delivery gates. Reuse the external CLI modules and API conventions established by those plans where available, but do not delay either assessment feature solely for these parity commands.

- [ ] Choose consistent external CLI nouns for structured service evidence, risk/feed status, OSV lookup, manual findings, evidence links, and HTTP profiles so the command tree does not accumulate unrelated top-level verbs.
- [ ] Expose structured Nmap service observations from the existing run service-evidence route through the chosen external CLI noun, with bounded pagination and text/JSON output.
- [ ] Add a read-only API route and `darklab risk status` command for configured CVE feed source, age, bundled/live origin, refresh state, and safe failure information. Reading status must never refresh a feed.
- [ ] Add an external CLI wrapper for the existing explicit OSV lookup route. Preserve exact package/version inputs, permissions, feature gating, cache behavior, provider error handling, and the rule that ordinary reads never start lookups.
- [ ] Add API/CLI parity for assessment-cycle create, complete, archive, and delete operations, including profile selection, lifecycle conflicts, confirmation where destructive, and personal/team permissions.
- [ ] Add external CLI support for manual finding create/edit and evidence list/link/unlink operations with revision checks, exact Project ownership, typed source validation, duplicate handling, and bounded output.
- [ ] Add external CLI support for Project HTTP-profile list/create/show/update/delete operations. Accept only references to protected values and never echo submitted secret material.
- [ ] Split new external CLI parsers, handlers, and formatters into focused ratcheted modules rather than growing the main command module. Give new API/OpenAPI modules their required architecture budgets and allowlist entries when they are added.
- [ ] Add end-to-end API and CLI tests for each command, including help output, JSON stability, authentication, roles, conflict responses, rate/request bounds, and PostgreSQL parity. Update documentation, generated OpenAPI, test inventories/counts, `CHANGELOG.md`, and release drafts with each delivered command family.

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
