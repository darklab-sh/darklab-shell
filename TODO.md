# TODO

This file tracks open work, feature enhancements, known issues, technical debt, research items, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Feature enhancements, ideas, and research are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
  - [Autoscale ARM64 release runners on EC2 Spot](#autoscale-arm64-release-runners-on-ec2-spot)
  - [Make shell-output entities easier to select and reuse](#make-shell-output-entities-easier-to-select-and-reuse)
  - [Establish pseudonymous principals and hardened credentials](#establish-pseudonymous-principals-and-hardened-credentials)
  - [Add a restricted token deployment profile](#add-a-restricted-token-deployment-profile)
  - [Add managed sign-in through OpenID Connect](#add-managed-sign-in-through-openid-connect)
- [Known Issues](#known-issues)
  - [Make WHOIS entity extraction target-aware](#make-whois-entity-extraction-target-aware)
- [Technical Debt](#technical-debt)
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
- [Architecture](#architecture)
  - [Interactive PTY transport future-state](#interactive-pty-transport-future-state)

---

## Open TODOs

**v3.0 delivery scope.** The planned v3.0.0 release includes the shell-output entity menu, pseudonymous principal and credential model, restricted deployment profile, managed OpenID Connect sign-in, and the WHOIS parsing fix under Known Issues. The ARM64 release-runner autoscaling work remains independent and is not a v3.0 release requirement.

Land each coherent change through a short-lived branch and merge request while keeping `main` functional and the complete validation suite green. Start with the target-aware WHOIS fix, then the shell-output entity menu. For authentication, land the production-realistic test-identity pre-work and final contract decisions before schema work; split the principal roadmap into its numbered phases and split Phase 3A further into bounded subsystem conversions. Additive foundations may merge early, but do not leave personal ownership partly resolved from session tokens and partly from principals between merge requests. Treat the semantic ownership switch, public interfaces, UI, and legacy removal as coordinated slices with explicit transition tests.

After the restricted deployment profile merges, exercise open and restricted modes in a production-like staging deployment and use that feedback to close any browser-session, recovery, bootstrap, proxy, and operator-workflow gaps before starting OpenID Connect. Once every in-scope TODO is removed, the Known Issue is resolved, both database backends and deployment profiles pass qualification, and the complete documentation reflects shipped behavior, create `release/3.0` from `main` and begin the normal release cycle with `v3.0.0-rc.1`.

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

### Make shell-output entities easier to select and reuse

Discovered entities in shell output are visually useful, but their normal click action opens Atlas immediately. That makes it easy to leave the shell by accident when the intent was to select an IP, domain, URL, or other value for the next command. Keep entity tokens interactive, but make their first action a small, nearby menu that supports both investigation and reuse.

- [ ] Replace direct click, tap, `Enter`, and `Space` navigation with a compact menu anchored next to the entity token. Keep the primary menu deliberately small:
  - **Open in Atlas** opens the entity's Atlas profile.
  - **Copy to Clipboard** copies the canonical entity value and confirms success without exposing a second prompt.
  - **Insert into command** is the recommended third action. Insert the value at the current selection or caret in the visible desktop or mobile composer through shared `composerState`, restore focus, and never submit the command automatically.
- [ ] Reconcile the existing six-action right-click, keyboard-context-menu, and long-press menu with the new primary menu. Keep deeper work such as editing metadata, adding the entity to a Project, and refreshing intelligence in Atlas instead of crowding this small reuse menu; remove redundant output-only actions unless testing shows a clear need for them.
- [ ] Preserve normal text interaction. Dragging across an entity or finishing a text selection must not open the menu, and right-click or touch selection must retain the browser's normal copy and selection affordances rather than being captured only for app actions.
- [ ] Close the menu when the user clicks or taps outside it, types into either shell composer, presses `Escape`, chooses an action, opens another entity menu, changes tabs, or removes or rerenders the output that owns the token. Clicking inside the menu must not close it before the selected action runs.
- [ ] Reuse the app's dropdown surface, pressable, focus, clipboard, and outside-click helpers. Keep one menu open at a time, clamp it to the visible viewport without covering the entity when space allows, and use the existing mobile action-sheet pattern only when an anchored menu cannot remain usable on a narrow screen.
- [ ] Keep the interaction accessible: expose the token's menu state with the appropriate ARIA relationship, support arrow keys plus `Home` and `End`, return focus predictably after `Escape`, and announce copy failures and successes through the existing toast/status path. Pointer activation should not steal focus from someone who is selecting text.
- [ ] Apply the same contract wherever the shared interactive entity renderer is used in the live transcript and History Run Details. Keep static HTML/PDF exports and permalink output selectable and non-interactive.

**Acceptance criteria**

- [ ] Mouse, touch, and keyboard users can select entity text without an accidental Atlas navigation or menu opening, while a deliberate activation always opens the compact menu next to the entity.
- [ ] Open, copy, and insert actions use the canonical value and work for every supported entity type. Insert respects the active composer selection, adds no surprising whitespace, works on desktop and mobile, and does not execute or save a command by itself.
- [ ] Outside interaction and shell typing close the menu in both desktop and mobile composer modes, and no detached menu remains after tab changes, transcript trimming, History Run Details rerenders, scrolling, or viewport changes.
- [ ] Unit coverage pins selection suppression, action wiring, keyboard navigation, positioning, and every close path. Playwright covers the real live-output flow in source and bundle modes, including mobile behavior, and maintained documentation, test counts, generated assets, and `CHANGELOG.md` are updated when the feature ships.

### Establish pseudonymous principals and hardened credentials

Separate the stable actor and personal workspace from the credential used to access them, so credentials can be added, rotated, expired, or revoked without moving or orphaning data. Treat this as a coordinated pre-release cutover: replace the session-token ownership model, raw-token storage, and `session-token` terminology rather than carrying compatibility code forward. The default deployment remains anonymous-first, and users can still carry a pseudonymous workspace between devices without providing a username, email address, or other personal information.

This clean-cutover choice is based on the deployment state recorded on 2026-08-31: the public instance is still unadvertised, its production audit found one used operator-owned session token plus one never-seen test token, and there are no known external users to preserve. The default production path is therefore a clean application-data reset after a verified backup; a specifically selected conversion of the operator's local data remains optional. Re-check this assumption before implementation starts and redesign the cutover if real external usage appears.

This entry is the foundation for the restricted deployment and OIDC entries below. It includes principals, personal-workspace ownership, portable credentials, scoped API/CLI tokens, team and worker authorization, and the complete open-profile credential UI. The restricted request gate, HttpOnly cookie exchange, CSRF protection, and managed-provider sign-in remain in the later entries.

#### Product and security contracts

- Anonymous UUID sessions remain the default in the `open` profile. Visiting the app must not create a principal or durable server-side credential automatically.
- Upgrading an anonymous workspace creates one stable pseudonymous principal, attaches one personal workspace, and issues the first portable credential atomically. The user does not choose whether individual data categories move.
- A principal may have multiple independently labeled credentials. The same portable credential may be used on several devices, but the UI recommends separate credentials so one lost device can be revoked without affecting the others.
- A credential authenticates a principal but never owns runs, files, projects, preferences, workflows, secrets, teams, or background work. Personal ownership resolves through the principal's workspace; team authorization resolves through principal membership and server-side capabilities.
- Invalid, expired, or revoked credentials fail closed. A request that attempts credential authentication must never fall back to an anonymous UUID.
- Empty or missing owner ids never resolve to a shared anonymous owner. Anonymous access uses an explicit, validated per-browser UUID context; failed credential authentication produces a typed authentication failure before owner resolution.
- Each personal workspace stores an immutable, validated relative storage key or directory name that is independent of its principal and credentials. Attaching an anonymous workspace preserves its existing directory rather than renaming filesystem state during an ownership change.
- Revoking one credential immediately blocks that credential from new authenticated actions. Its effect on durable work created from that credential follows the explicit policy chosen below; disabling a principal remains the guaranteed global stop for every credential and all new personal or team-owned background work while preserving data for operator recovery or review.
- Raw credential secrets are shown once, are never recoverable from the server, and never enter URLs, command arguments, prompt history, recents, saved transcripts, logs, audit details, diagnostics, exports, error responses, or telemetry.
- The cutover invalidates existing `tok_` values, removes `/session/migrate`, and keeps no deprecated command, endpoint, header, or raw-owner compatibility alias.

#### Open decisions to close before implementation

- [ ] Choose the final user-facing term and command root. Prefer **access credential** and `credential` unless the recovery-only meaning of **recovery credential** is intentional; use the chosen term consistently in UI copy, CLI output, configuration, API descriptions, audit events, and documentation.
- [ ] Choose opaque identifier and secret formats for principals, workspaces, credentials, and PATs, including safe display prefixes, version markers, parsing limits, and collision handling.
- [ ] Choose the server-side verifier. Prefer a public lookup id plus a high-entropy secret protected by a versioned keyed digest computed in application code, never SQL. Reuse the secrets vault's master-key loading, `0600` file handling, environment override, caching, backup, and restore machinery, but derive a separate domain-labeled verifier key rather than reusing the AES-GCM wrapping key directly; record the reason if a completely separate root key is chosen.
- [ ] Choose the temporary open-profile browser transport used until the restricted-profile cookie exchange ships. Record whether the browser sends the portable credential through `Authorization: Bearer` or a dedicated header, how CORS treats it, and why the script-readable browser credential remains an accepted interim boundary.
- [ ] Decide whether the later `browser_sessions` table is created now or deferred until the restricted-profile entry. Do not add unused session rows merely to reserve a schema.
- [ ] Define recovery when every credential is lost. Decide whether recovery is possession-only, can use another already-linked credential, or permits an explicit operator reset by principal id; do not introduce email, security questions, or identity proofing by implication.
- [ ] Decide whether credential revocation disconnects established run streams and PTY connections immediately or blocks only their next authenticated action. Completed and still-running server work must have an explicit, tested outcome either way.
- [ ] Decide what revoking a credential does to schedules, watchers, workflow continuations, notifications, and other durable definitions created or last changed through that credential. Choose whether those definitions continue, pause automatically, or are paused through an explicit revoke option; retain safe originating-credential metadata either way so a stolen-device response does not require guessing or disabling the entire principal.
- [ ] Define PAT scopes, default and maximum expiry, rotation, rate limits, and whether an `oidc_required` deployment may issue PATs before the later access-profile plan relies on them.
- [ ] Reconfirm the one-time production cutover disposition against a fresh usage audit. Keep a clean application-data reset as the default under the recorded deployment assumption; convert only explicitly selected operator-owned data into a new principal after a verified backup. Do not build an automatic general-purpose legacy-token migration.

#### Pre-work — Make test identities production-realistic

This is independently shippable against the current session-token model and must land before the security-critical resolver changes. The 2026-08-31 inventory finds 1,643 `X-Session-ID` occurrences across 20 test files: 1,636 occurrences in 16 Python files and seven occurrences in four JavaScript files. The Python files are the fixture-conversion target because their values reach the server resolver. Do not turn header-only JavaScript unit values into database fixtures; keep those tests focused on request construction until Phase 5 replaces the header. The current end-to-end cases already obtain live identities from the page and should continue proving the browser path rather than receiving synthetic replacements.

**Steps**

- [ ] Add shared test factories for valid anonymous UUID identities and real durable tokens issued through the current storage service. Preserve stable identity across related requests without teaching tests to bypass production validation.
- [ ] Convert route, service, worker, SQLite, and Postgres fixtures from arbitrary owner strings to those factories. Classify each remaining malformed value as an intentional negative test rather than performing an unreviewed bulk substitution.
- [ ] Remove `ALLOW_LEGACY_TEST_SESSION_IDS` and `_allow_legacy_test_session_id()` after the fixtures are converted; do not replace them with another default-on or production-resolver bypass.
- [ ] Preserve `"../bad"` and `"../other-session"` as explicit rejected-identity regressions, then reuse those cases in Phase 1 against the stored workspace-key validator so the new persistence model does not lose the path-safety coverage that owner hashing currently provides incidentally.

**Acceptance criteria**

- [ ] Every non-negative Python `X-Session-ID` fixture that reaches the server resolver is a valid anonymous UUID or a durable token issued through the real test storage path, and intentional malformed values are visibly named and assert rejection. Header-only JavaScript unit values remain isolated request-construction data, while end-to-end cases continue to use identities obtained from the running app.
- [ ] Test configuration contains no legacy identity bypass, and the same identity-validation code runs in tests and production.
- [ ] The current application behavior is unchanged outside test setup, and the complete Python, Postgres, JavaScript, and live-browser gates pass before principal/credential implementation begins. Run the browser coverage through `bash scripts/run_playwright.sh --asset-bundle-mode source ...` and `bash scripts/run_playwright.sh --asset-bundle-mode bundle ...` so removing the bypass is proven against the real page in both maintained asset modes.

#### Phase 0 — Freeze contracts and inventory the current model

**Steps**

- [ ] Inventory every schema column, foreign key, unique constraint, query helper, route, service, worker, audit field, browser state key, API/CLI option, test fixture, and documentation reference that treats `session_id`, `session_token`, `X-Session-ID`, or a `tok_` value as an actor or owner. Explicitly include the current invalid-token `""` result, `owner_context_for_scope("")` shared-`"anonymous"` path, owner-derived workspace directories, session-token API fallback, and confirmation that the pre-work removed the former test bypass.
- [ ] Use the existing `OwnerContext`, `personal_owner_context()`, and `team_owner_context()` types as the target ownership contract rather than introducing a parallel abstraction, but do not treat them as an already-adopted query seam. Record production usage of each predicate helper and inventory every direct personal/team SQL predicate that still bypasses them.
- [ ] Define one request-independent authentication context containing the principal id, personal-workspace id, credential id and type, authentication method, selected team id, and resolved team role/capabilities. Define a separate anonymous UUID context that cannot be mistaken for a failed credential attempt or an empty owner id.
- [ ] Define the authorization rules for personal reads/writes, team reads/writes, principal-disabled state, credential expiry/revocation, and background execution. Authentication resolves an actor; ownership and capability checks remain separate decisions.
- [ ] Resolve every open decision above and record the final contracts in `DECISIONS.md`, including the clean-cutover rationale and the boundary with the restricted-profile work. Mark **Session Token Security** and **Team Ownership: Session Tokens Stay Actors** as superseded instead of leaving contradictory current-state decisions; explain why credential rotation, independent revocation, durable work, and the shipped team ownership model now justify the stable-principal boundary. Supersede the scheduler's token-revocation guarantee with the chosen durable-work revocation policy and its stolen-device response.
- [ ] Threat-model database disclosure, credential guessing and stuffing, XSS theft from browser storage, replay, cross-principal access, team-role changes, worker execution, operator recovery, backup disclosure, and denial-of-service through unauthenticated credential issuance.

**Acceptance criteria**

- [ ] The inventory names an owner and replacement path for every legacy identity dependency on both SQLite and Postgres; repository searches reveal no unexplained token-owned surface.
- [ ] The authentication context and route failure semantics are documented closely enough that browser, API, CLI, worker, and test code can share them without inventing local interpretations.
- [ ] No blocking identity, naming, verifier, transport, recovery, live-connection revocation, durable-work revocation, PAT, or production-data decision remains open when schema implementation starts.
- [ ] The deployment usage assumption is rechecked immediately before schema work; any known external users stop the clean-cutover plan until a bounded compatibility or migration design is approved.

#### Phase 1 — Add the principal, workspace, and credential persistence model

**Steps**

- [ ] Add matching SQLite and Postgres records for principals, personal workspaces, and credentials. Keep one personal workspace per principal unless the Phase 0 contract deliberately allows more.
- [ ] Give each personal workspace an immutable, server-generated, validated relative storage key or directory name instead of deriving its path from a principal, credential, or owner id. Never persist an absolute path. When an anonymous workspace is attached, store its existing validated `sess_<digest>` directory name so the ownership transaction does not rename or move files.
- [ ] Use one storage-key validator and one workspace-root resolver for newly generated names and preserved anonymous `sess_<digest>` names. Do not keep a permissive legacy validation branch for attached workspaces; both provenances must satisfy the same character, length, prefix, traversal, symlink, containment, and uniqueness rules.
- [ ] Store only safe credential metadata: non-secret id/prefix, principal id, type, label, verifier digest and key version, created/last-used timestamps, optional expiry, revoked timestamp/reason, and safe creator/audit references.
- [ ] Add an explicit principal state with active and disabled behavior, bounded reason metadata, created/updated timestamps, and constraints that prevent credentials or personal workspaces from referring to missing principals.
- [ ] Build storage services for atomic principal creation, anonymous-workspace attachment, credential issuance, listing, labeling, expiry, rotation, revocation, and principal disable/enable. Keep SQL out of route and browser adapters.
- [ ] Make last-used updates bounded so ordinary request volume does not turn every authenticated read into a database write.
- [ ] Resolve durable personal workspace paths from the persisted workspace storage key. Keep explicit anonymous UUID path resolution only for not-yet-attached workspaces, and remove both the `migrate_session_workspace()` implementation in `workspace/maintenance.py` and its re-export in `workspace/files.py` with the legacy migration flow once no live path needs an owner-derived rename.
- [ ] Add startup/schema guards that reject the old token schema after cutover and fail clearly when the database and application code do not agree.

**Acceptance criteria**

- [ ] SQLite and Postgres schema manifests, migrations, constraints, indexes, transaction behavior, backup/restore behavior, and storage-service results stay in parity.
- [ ] No reusable raw credential can be recovered from a database dump, audit row, log record, or safe serializer.
- [ ] Principal creation plus first workspace/credential attachment is atomic, and an injected failure leaves the anonymous workspace and all of its data unchanged.
- [ ] Credential rotation or revocation changes no ownership key and requires no data migration.
- [ ] Attaching, re-keying, rotating, revoking, or rolling back an identity leaves the persisted workspace directory name unchanged and performs no filesystem rename; path validation prevents traversal, absolute paths, and references outside the configured workspace root.
- [ ] The shared storage-key validator rejects the existing `"../bad"` and `"../other-session"` regression seeds, malformed preserved names, symlinks, duplicates, and names that resolve outside the workspace root on both database backends.

#### Phase 2 — Centralize authentication and credential lifecycle handling

**Steps**

- [ ] Replace `get_session_id()` token validation with one central resolver that distinguishes no credential, valid credential, malformed credential, unknown credential, expired credential, revoked credential, and disabled principal. The resolver returns a typed authentication result or raises a typed error; it never represents failed authentication as `""`.
- [ ] Make every supplied-but-invalid credential return an explicit authentication failure rather than an empty identity or anonymous fallback. Keep truly credential-free open-profile requests on the anonymous path.
- [ ] Make personal owner construction reject empty ids and the shared literal `"anonymous"`. Require a validated anonymous UUID or an authenticated personal-workspace id before `OwnerContext` construction so `owner_context_for_scope("")` cannot become a data-access path.
- [ ] Generate high-entropy, versioned secrets through `POST` routes, show them once, and extend the existing per-IP dynamic route limiter for anonymous upgrades and failed redemption attempts.
- [ ] Implement authenticated self-service lifecycle operations for listing safe metadata, adding and labeling credentials, changing expiry, rotating, and revoking. Rotation issues the replacement before the old credential is revoked so the UI cannot strand the principal on a failed copy or response.
- [ ] Protect the last usable credential from accidental self-revocation unless the user completes the recovery/lockout confirmation defined in Phase 0. Keep local browser clearing separate from server-side revocation.
- [ ] Add separately typed and scoped PATs for API/CLI use with `Authorization: Bearer`, default expiry, safe last-used metadata, and no ability to retrieve the secret after issuance.
- [ ] Record safe audit events for principal creation/disable/enable and credential create/redeem/label/expiry/rotate/revoke/failure without recording secrets, submitted bearer values, or stable cross-deployment fingerprints.

**Acceptance criteria**

- [ ] Resolver tests run without a legacy test bypass, cover every credential state, and prove that malformed, unknown, expired, revoked, and disabled credentials cannot read or mutate another principal's data.
- [ ] Focused regressions prove that invalid `tok_`, empty-owner, missing-owner, and shared-`"anonymous"` paths cannot construct a personal owner context or reach shared database rows or a shared workspace directory.
- [ ] Issuance, rotation, and PAT secrets appear exactly once in successful responses and are absent from later list/detail responses.
- [ ] Concurrent create/rotate/revoke requests preserve at least one usable credential unless the caller explicitly chose the tested lockout path.
- [ ] Rate-limit and audit behavior is bounded, privacy-safe, and identical across SQLite and Postgres.

#### Phase 3A — Build and adopt the `OwnerContext` query-ownership seam

Treat this as query-ownership design and adoption, not as a mostly completed mechanical conversion. `OwnerContext` is already threaded through many function signatures and workspace paths, but `personal_scope_predicate()` currently has no production caller and `shared_owner_predicate()` has only a handful; most ownership SQL still bypasses both.

**Steps**

- [ ] Build a baseline inventory that records every direct ownership predicate, its table and operation, current result-set semantics, team-column nullability/default, key shape, and whether it is personal-only, team-capable, attribution-only, or migration code. Record production call counts for each existing predicate helper so adoption is measured rather than inferred from type annotations.
- [ ] Design and test the missing query adapters before broad conversion. Cover tables keyed by `session_id` or `session_token`, personal-only tables with no `team_id`, team-capable tables with nullable or non-null/empty team ids, composite-primary-key tables such as stars, recent values, and secrets, and tables whose actor attribution is separate from ownership.
- [ ] Classify each conversion as **equivalent** or **non-equivalent** before changing it. In particular, compare direct `session_id = ?` behavior with the personal form of `shared_owner_predicate()`, which also adds `(team_id IS NULL OR team_id = '')`; record the count and location of sites where adopting the helper would change the returned rows.
- [ ] Convert equivalent sites in behavior-preserving batches while keeping the existing session ids and schema meaning. Land every non-equivalent site separately with tests that pin the old and intended result sets, an explicit determination that the change is a bug fix or rejected regression, and the documentation/changelog update required for any user-visible correction.
- [ ] Cover list, detail, mutation, export, cleanup, retention, import, worker, and filesystem paths across runs, active-run metadata, History, snapshots and shares, preferences, stars, recent values, Files, workflows, Projects, Assessments, Atlas, findings, packages, secrets, schedules, watchers, notifications, provider state, and other personal/team surfaces.
- [ ] Consolidate subsystem-specific scope helpers onto the shared context contract where their behavior is equivalent. Keep small, named adapters where a table has a genuinely different owner shape instead of constructing ownership SQL at arbitrary call sites.
- [ ] Add targeted adapter and subsystem tests that place rows for two personal owners, team scope, `team_id IS NULL`, and `team_id = ''` into the same fixture, then prove the exact list/detail/mutation boundary on SQLite and Postgres. Do not treat a broad suite pass as evidence that the new helpers executed.
- [ ] Land Phase 3A in bounded subsystem merge requests rather than one repository-wide rewrite; each merge request must identify its equivalent and non-equivalent sites, preserve or deliberately correct behavior as declared, list remaining direct-predicate exceptions, and leave the branch releasable.

**Acceptance criteria**

- [ ] The completed inventory provides counts by query shape and equivalence class, and every non-equivalent site has a reviewed disposition before conversion begins.
- [ ] Every mechanical batch changes no ownership semantics or stored owner values and can merge independently with the current session-token model still functioning; semantic fixes are isolated from those batches and reviewed as behavior changes.
- [ ] Focused tests actively exercise every adopted `OwnerContext` query adapter and personal/team result-set variant on both backends; repository scans limit direct ownership predicates to audited storage adapters, schema/migration code, and narrowly documented exceptions.
- [ ] Every remaining exception has a named Phase 3B replacement path, so the semantic cutover has a finite and auditable blast radius.

#### Phase 3B — Switch personal ownership and attribution to principals and workspaces

**Steps**

- [ ] Change authenticated personal contexts to carry the principal's personal-workspace id as `owner_id` plus separate principal and credential actor metadata. Keep team contexts owned by `team_id` while attribution and capability checks use the principal/member identity rather than a token value.
- [ ] Replace direct token/session ownership columns and foreign keys across the Phase 3A inventory with personal-workspace or principal references on both backends. Treat the existing `team_members.session_token_hash` and `teams.created_by_session_token_hash` fields as a digest-only precedent to migrate away from, not as durable owner keys to preserve.
- [ ] Replace private actor references used for attribution with principal references while keeping public pseudonymous display data bounded and optional.
- [ ] Replace `team_members` token references and uniqueness constraints with principal membership on both backends. Preserve owner, admin, operator, and viewer capability behavior and explicit personal/team scope selection.
- [ ] Remove `/session/migrate`. Anonymous upgrade uses the atomic attachment operation; activating, adding, or rotating a credential never moves records.
- [ ] Re-key authenticated share mutations, including `delete_share`, through the new owner context. Review unauthenticated `get_share` permalink access separately so this phase does not accidentally change the public-share behavior reserved for the access-profile decision.

**Acceptance criteria**

- [ ] Cross-principal, personal/team, cross-team, import, export, retention, cleanup, and backup/restore tests prove that no route or service still authorizes from a credential value.
- [ ] Credential rotation, device revocation, label changes, and team removal leave history, files, projects, preferences, secrets, audit attribution, and team-owned records correctly attached.
- [ ] Repository schema/query scans find no remaining token owner or token foreign key outside intentionally historical migration fixtures.
- [ ] The semantic diff is concentrated in the authentication-to-owner context boundary and explicit schema/storage adapters; it does not repeat Phase 3A's mechanical query churn or rely on compatibility shims.

#### Phase 4 — Move durable and background work onto principal authorization

**Steps**

- [ ] Store schedules, watchers, workflow executions, notifications, provider secrets, package jobs, and other durable work against the personal workspace or team scope captured at creation time, with stable principal attribution.
- [ ] Preserve safe `created_by_credential_id` and, where changes affect later execution, `last_changed_by_credential_id` metadata on durable definitions. These references support audit and stolen-device response but never become ownership or worker authentication keys.
- [ ] Give scheduler, watcher, notification, workflow, and other supervised workers a principal-resolution path that does not depend on Flask request context or a reusable browser credential.
- [ ] Re-check principal state, team membership, and required role capability immediately before each team-owned launch or mutation so removal or downgrade takes effect before later work executes.
- [ ] Implement the chosen credential-revocation policy for durable definitions and provide an operator-visible way to list and pause work created or last changed through a specific credential. Define principal-disable and principal-reenable behavior for queued work, running work, streams, PTYs, notifications, and retry/recovery loops separately.
- [ ] Keep historical attribution stable after credential rotation, credential deletion, principal disablement, display-name changes, or team membership removal.

**Acceptance criteria**

- [ ] Revoking one device credential immediately blocks new authentication and applies the recorded continue/pause policy to attributable durable work without orphaning it; disabling the principal prevents every new personal and team-owned execution.
- [ ] A stolen-device exercise can identify the credential, revoke it, enumerate affected durable definitions, and stop any related future fires without guessing from logs or unnecessarily disabling the entire principal unless the recorded policy explicitly requires that fallback.
- [ ] A removed or downgraded team member cannot exercise stale capabilities through schedules, watchers, workflow continuations, queued jobs, or retries.
- [ ] Worker logs and audit rows use safe principal/credential hints and never need a raw credential to authorize work.
- [ ] Restart and recovery tests prove durable work resumes with the captured owner/scope without reconstructing identity from request-local state.

#### Phase 5 — Replace browser, API, CLI, and operator interfaces

**Steps**

- [ ] Replace the `session-token` command family with the Phase 0 command root. Status and list operations may render safe metadata in the terminal; create, use, rotate, and recovery operations that handle a raw secret open the shared Access UI instead of accepting secrets on the command line.
- [ ] Replace the legacy session routes with principal/credential endpoints for anonymous upgrade, credential redemption/verification, current-principal summary, credential lifecycle management, and local access clearing. Regenerate the API v1 OpenAPI document after final route shapes settle.
- [ ] Replace `X-Session-ID` and token-shaped CLI configuration with the chosen browser transport and scoped PAT configuration. Keep CLI files owner-only and make diagnostics show only credential type, safe prefix, expiry, and principal state.
- [ ] Remove API v1's explicit `X-Session-ID` fallback from `token_from_request()` and require scoped PATs through `Authorization: Bearer`. Treat this as its own API-visible breaking change with focused contract tests, CLI migration guidance, changelog entry, and release-note callout.
- [ ] Add an operator lifecycle command for safe principal lookup, credential issuance, expiry, rotation, revocation, disable/enable, and recovery. Newly issued secrets print once and require an explicit output destination or interactive acknowledgement when appropriate.
- [ ] Update command discovery, autocomplete, help, FAQ data, config validation, masking, audit classification, notification redaction, and administrative-command persistence rules for the replacement terminology.

**Acceptance criteria**

- [ ] No supported browser, API, CLI, or operator path accepts a legacy `tok_` credential, `X-Session-ID`, `/session/migrate`, or `session-token` command.
- [ ] Secret-bearing values cannot enter terminal prompt history, command recents, saved client runs, shell history through documented CLI examples, URLs, or generated OpenAPI examples.
- [ ] Browser portable credentials and PATs resolve the same principal while retaining separate credential type, scope, expiry, audit, and revocation behavior.
- [ ] CLI/API contract tests cover valid, missing, malformed, expired, revoked, under-scoped, and disabled-principal credentials.

#### Phase 6 — Replace the session-token UI with principal and credential management

**Steps**

- [ ] Add an **Access** tab to the existing Options tab strip, immediately after **Preferences**. Keep **Prompt Name** in Preferences, move durable identity controls out of the current Session Token card, and keep one shared controller/state model for desktop and mobile.
- [ ] Design the anonymous state around a clear user outcome: explain that the current workspace is private to this browser, offer a primary **Keep this workspace** action, and explain that no username, email address, or password is required.
- [ ] Make **Keep this workspace** atomically attach all current anonymous data, request an optional credential label, activate the new principal only after success, and leave the anonymous workspace untouched on any failure. Do not present the old optional category-by-category migration prompt.
- [ ] Present the first credential secret in a one-time reveal state with a masked-by-default field, explicit Reveal and Copy actions, a safe credential label, and a clear instruction to save it in a password manager. Remove the secret from the rendered DOM when the reveal closes and never offer the current always-available **Copy token** behavior later.
- [ ] Add **Use an existing credential** through a paste-safe secret input that never places the value in a URL or terminal command. A rejected credential keeps the current UI state, shows an inline error, and does not silently activate a fresh anonymous identity for the failed request.
- [ ] Render existing credentials as `.panel-row` items with label, safe prefix, type, created, last-used, expiry, revoked state, and a passive **Current** badge where applicable. Support add-for-another-device, rename, expiry, rotate, and revoke without ever returning an existing secret.
- [ ] Allow the same saved credential on several devices while recommending one labeled credential per device. Make **Remove access from this browser** clear only local credential state and return to an anonymous UUID; keep **Revoke credential** as a separate destructive server action.
- [ ] Before revocation, show the durable-work impact required by the Phase 0 policy: identify schedules, watchers, or other future actions attributed to that credential and either explain that they continue, explain that they pause, or offer the approved **also pause related work** choice. After revocation, provide a direct way to review the affected items.
- [ ] Make rotation a two-step UI: issue and save the replacement first, then revoke the old credential through `showConfirm()`. Warn before revoking the current or last usable credential and provide the recovery path chosen in Phase 0.
- [ ] Update the desktop HUD and mobile session/scope summaries to show **ANON** or a safe durable-access hint without exposing a principal id or raw credential. Broadcast identity and credential changes through explicit UI events so other tabs refresh or leave revoked state consistently.
- [ ] Update Teams, Notifications, Schedules, Watchers, Secrets, onboarding, FAQ, command registry, autocomplete, diagnostics, and empty/error states to say **durable identity**, **principal**, or the chosen credential term instead of session token where that wording reaches users.
- [ ] Reuse the established UI contracts: `.tab-strip` for Access navigation, `.panel-row` for credential rows, `.form-control` and app-native selects for inputs, the existing button family, `showConfirm()` for revoke/disable actions, shared modal dismissal/focus trapping, `.nice-scroll` for long lists, and the existing semantic color tokens. Do not introduce a second modal system or one-off mobile controls.
- [ ] Keep the Options mobile sheet keyboard-safe and touch-sized. Use an in-panel list/detail or disclosure flow for credential details rather than stacking another modal over Options; keep action rows reachable at narrow widths and return focus to the action that opened each editor or confirmation.
- [ ] Add `role="status"`/`aria-live` feedback for successful lifecycle actions, `role="alert"` for validation/authentication failures, complete keyboard operation, visible focus, non-color-only status labels, and safe focus restoration after reveal, copy, rotate, revoke, and local-clear flows.
- [ ] Replace `session_token_controls.js` and its neutral bridge with focused principal/credential modules that communicate through imports, state APIs, or explicit UI events. Update asset configuration and committed source/bundle output without adding undocumented browser globals.

**Acceptance criteria**

- [ ] Desktop and mobile users can remain anonymous, keep an anonymous workspace, save the one-time credential, use an existing credential, add a device credential, rotate, revoke, and remove local access without losing or moving principal-owned data.
- [ ] The UI never retrieves an existing raw credential after its one-time reveal, and DOM, clipboard-trigger labels, transcript, recents, browser logs, error artifacts, screenshots, and accessibility text expose only deliberately revealed or safely masked values.
- [ ] Credential lists and actions stay usable with zero, one, many, expired, revoked, and current credentials; slow, failed, duplicated, and out-of-order responses cannot replace newer authoritative state.
- [ ] Options, HUD, terminal command, Teams, Notifications, Schedules, Watchers, and cross-tab state all agree on anonymous, durable, expired, revoked, and disabled-principal status.
- [ ] The stolen-device UI path clearly separates local removal, credential revocation, related durable-work handling, and principal disablement so an operator can choose the narrowest effective response.
- [ ] Playwright covers the complete Access flow on desktop and mobile in source and bundled asset modes, including keyboard/focus behavior, narrow action stacking, one-time reveal removal, invalid credential handling, last-credential warnings, cross-tab refresh, and a revoked-current-credential path.
- [ ] UI capture scenes and their reviewer notes cover anonymous Access, first-credential reveal, credential list/current row, rotate confirmation, revoke warning, and mobile list/detail states across the maintained themes.

#### Phase 7 — Perform the clean pre-release cutover and remove legacy identity code

**Steps**

- [ ] Add an operator preflight that verifies the backup, reports current legacy owner/token counts without displaying secrets, and confirms that deployment usage still matches the recorded pre-release assumption. Default to a fresh application-data set while retaining the old data/workspace state for rollback; require an explicit selection for the one operator-owned conversion path.
- [ ] Run the SQLite preflight and cutover through the application container, or another explicitly verified runtime using the same SQLite build and FTS5 tokenizer support as the application that owns the database. The operator tool must refuse unverified direct host-side SQLite writes with a clear supported invocation; do not assume a host `sqlite3` or Python build is compatible merely because it can open `history.db`.
- [ ] Check the production workspace root for the current shared-anonymous directory `sess_2f183a4e64493af3f377f745eda50236` (`sha256("anonymous")[:32]`). If it exists, inventory its contents without assuming they belong to one actor and record an explicit quarantine, archive, discard, or manual-review disposition before cutover; never attach mixed contents to the new principal automatically.
- [ ] For a selected conversion, validate and persist each existing workspace directory name before changing ownership, then perform the database ownership conversion, constraints, and credential issuance in one transaction. Re-keying identity must not rename, copy, or delete workspace directories; startup fails clearly if a committed workspace storage key is missing, invalid, duplicated, or outside the configured root.
- [ ] Treat `runs` and its external-content `runs_fts` table as one migration unit. Backfill new ownership fields with in-place `UPDATE` statements so ownership changes do not alter `rowid`, `command`, or `output_search_text`, and do not rebuild `runs` merely to re-key ownership. If removing legacy columns requires table reconstruction, preserve every `runs.rowid` explicitly, recreate the supporting triggers, and run `INSERT INTO runs_fts(runs_fts) VALUES ('rebuild')` in the same transaction before commit.
- [ ] Replace the baseline comment that says runs are never updated after insert with the real invariant: ownership-only updates may occur, while any update to `command` or `output_search_text` must update or rebuild `runs_fts`. Add migration tests that fail if a future `runs` schema rewrite leaves the external-content index stale.
- [ ] Invalidate all legacy `tok_` values, remove raw `session_tokens` storage, remove token-keyed team constraints and owner columns, remove `/session/token/*` and `/session/migrate`, remove `X-Session-ID`, and remove local-storage/current-command compatibility code in the same release.
- [ ] Remove migration prompts, token-copy UI, token-aware browser bridges, masking paths that exist only for legacy commands, obsolete CLI config, and legacy fixtures rather than leaving dormant code behind.
- [ ] Verify rollback restores the complete pre-cutover database and workspace state; rollback must not claim that newly issued credentials remain usable against the restored legacy application.

**Acceptance criteria**

- [ ] A copied legacy token cannot authenticate through any browser, API, CLI, worker, stream, or background path after cutover.
- [ ] The database conversion is all-or-nothing: a failed transaction leaves the complete old ownership model, while a committed transaction contains only principal/workspace ownership and every workspace row still resolves the unchanged pre-cutover directory. No owner-derived filesystem rename is part of the transaction or recovery path.
- [ ] SQLite cutover tests verify `runs`/`runs_fts` row-count and `rowid` parity, pass the FTS5 integrity check, and find a seeded known substring through the normal History search path after both a successful conversion and a rollback. A cutover attempted from an unverified host SQLite runtime fails before opening a write transaction.
- [ ] The default clean-reset rehearsal starts against a fresh complete data set and can return to the retained pre-cutover database and workspace state without combining old and new identity records.
- [ ] Repository searches find no live `session-token`, `tok_`, `X-Session-ID`, raw `session_tokens`, or `/session/migrate` contract outside historical changelog/decision context and intentional rejection tests.
- [ ] The selected production data disposition is rehearsed against a restored backup before the production upgrade runs.

#### Phase 8 — Qualify, document, and release the principal model

**Steps**

- [ ] Run the full mode matrix across browser, API, CLI, personal scope, team scope, Files, Projects, Assessments, Atlas, History/shares, interactive PTY, long-lived streams, schedules, watchers, workflows, notifications, secrets, backup/restore, SQLite, and Postgres.
- [ ] Exercise `scripts/operations/migrate_sqlite_to_postgres.py` from a fully migrated SQLite source into a freshly initialized Postgres destination. Confirm the helper requires the new application migration level, copies principal/workspace/credential records and immutable workspace storage keys correctly, continues to skip SQLite FTS tables, and leaves Postgres search indexes valid. Define and test whether the workspace root is shared, copied separately, or intentionally unavailable after a backend move; the migration must not report success while copied storage keys resolve against the wrong root.
- [ ] Add focused security regression coverage for digest-only storage, one-time display, redaction, cross-principal isolation, invalid-credential fail-closed behavior, principal disablement, rate limiting, recovery abuse, concurrent lifecycle actions, and execution-time team authorization.
- [ ] Measure indexed credential resolution and bounded last-used writes under representative request concurrency so the new authentication lookup does not create a database bottleneck.
- [ ] Update `README.md`, `FEATURES.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`, `CONTRIBUTORS.md`, `DECISIONS.md`, `tests/README.md`, CLI help/man pages, API OpenAPI output, UI capture notes, release drafts, and `CHANGELOG.md`.
- [ ] Recalculate and synchronize the maintained test counts in `ARCHITECTURE.md`, `CONTRIBUTING.md`, and `tests/README.md`, and regenerate the complete test appendix in `tests/README.md` before running the documentation guard.
- [ ] Call out the intentional legacy credential invalidation, API v1 removal of the `X-Session-ID` fallback, superseded token-as-actor model, and the chosen credential-revocation effect on durable work in the changelog, upgrade guidance, and release notes.
- [ ] Run documentation links/contracts, Python and JavaScript unit/integration suites, Postgres tests through the approved helper, source/bundle Playwright suites through `bash scripts/run_playwright.sh --asset-bundle-mode ...`, asset checks, lint/type checks, audits, and container smoke tests.

**Acceptance criteria**

- [ ] Anonymous open-profile behavior remains the default and requires no identifying information, while durable users can recover the same principal-owned workspace from multiple independently revocable credentials.
- [ ] No credential value is an owner key, no raw reusable secret is stored server-side, and no authorization decision depends on a browser-local token string.
- [ ] Principal disablement, credential revocation, team-role changes, worker execution, API/CLI PATs, UI state, backup/restore, and rollback all match the recorded decisions on both database backends.
- [ ] The supported SQLite-to-Postgres migration preserves the principal model and either resolves every persisted workspace storage key against the declared destination root or fails with actionable missing-root details before backend cutover.
- [ ] All required validation passes from a clean checkout, generated assets and OpenAPI output are current, documentation describes final shipped behavior rather than migration phases, and the release notes call out the intentional pre-release credential invalidation.

### Add a restricted token deployment profile

Give private deployments a real authentication boundary while keeping anonymous access the default. This entry adds the access profile contract, the fail-closed request gate, and the browser session exchange that a restricted deployment needs.

- [ ] Define the access profile and public-route contracts:
  - Define explicit access profiles instead of an open-ended set of interacting booleans:
    - `open` preserves the current anonymous UUID flow and optional portable credentials and remains the default for existing installations.
    - `token_required` rejects anonymous use and accepts only operator-issued pseudonymous access credentials.
    - `oidc_required` rejects anonymous use and requires a configured OpenID Connect provider, implemented by the managed sign-in entry below.
    - `mixed` allows anonymous use while offering optional credential or managed sign-in for operators who want portability, recovery, or centrally managed access.
  - Enumerate every route that is reachable today without a session before defining the allowlist. Snapshot permalinks serve a full styled page with no session check at all, so an allowlist written only from health, static, sign-in, and callback routes would silently change or break existing behavior.
  - Define the small public-route allowlist for restricted profiles, including health/readiness checks, static assets, sign-in or credential redemption, and provider callbacks. All other routes must fail closed before they read or mutate session-scoped data.
  - Decide whether share permalinks remain a deliberate unauthenticated capability, become profile-gated, or gain their own capability token, and record the decision in `DECISIONS.md`.
  - Return an explicit `401` for a missing, invalid, expired, or revoked credential in restricted profiles. Never downgrade a failed authentication attempt into an anonymous session.
- [ ] Exchange portable credentials for shorter-lived browser sessions:
  - Record the trade this makes. Requests currently authenticate with a browser-storage value sent in a request header, which no cross-site request can forge. A cookie session removes the script-readable credential and takes on CSRF exposure the header scheme does not have, so the CSRF work below is the cost of the exchange rather than unrelated hardening.
  - Exchange a portable credential presented by the browser for a shorter-lived server-side session carried in a `Secure`, `HttpOnly`, appropriately `SameSite` cookie. Remove the portable secret from browser storage after a successful exchange.
  - Add a persisted session signing key with defined storage, file permissions, sharing across worker processes, and rotation procedure. The app has no signing key today, and a regenerated or lost key signs every operator out at once.
  - Add session-id rotation after authentication and privilege changes, idle and absolute expiry, logout, revoke-all-sessions, and CSRF protection for cookie-authenticated mutations.
- [ ] Implement the restricted profile as the first non-default deployment option:
  - Disable anonymous UUID access and unauthenticated credential issuance when this profile is active.
  - Provide a focused credential-entry screen that redeems the credential into a browser session without exposing the rest of the application first.
  - Support operator-controlled issuance through the lifecycle command before considering invite links or self-service enrollment. Avoid a bootstrap endpoint whose public availability would defeat the restricted profile.
  - Record safe audit events for credential creation, redemption, failed authentication, rotation, expiry, and revocation, with bounded rate-limit signals for repeated failures.
  - Confirm a fresh restricted deployment can be bootstrapped without editing the database and that losing one browser session does not destroy the principal's workspace or only recovery credential.
- [ ] Qualify this entry before it ships:
  - Add a mode matrix covering browser, API, CLI, personal scope, team scope, Files, projects, interactive PTY, long-lived run streams, schedules, watchers, notifications, secrets, backup/restore, SQLite, and Postgres behavior.
  - Add regression coverage for invalid-credential fail-closed behavior, the public-route allowlist, cookie flags, CSRF, session fixation, and idle/absolute expiry.
  - Add focused browser coverage for anonymous upgrade, restricted credential redemption, logout, expired and revoked sessions, credential management, and mobile sign-in surfaces in both source and bundled asset modes.
  - Threat-model reverse-proxy and HTTPS requirements, XSS and CSRF exposure, database disclosure, credential theft, and account recovery. Record accepted boundaries in `DECISIONS.md`.
  - Update `README.md`, `FEATURES.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`, `CONTRIBUTORS.md`, `DECISIONS.md`, `tests/README.md`, release drafts, and `CHANGELOG.md`. Keep current test counts and the test appendix synchronized.

### Add managed sign-in through OpenID Connect

Let operators point a deployment at an existing identity provider without darklab_shell collecting names, email addresses, or passwords. Scope this entry only after the restricted token profile has real deployment feedback.

- [ ] Implement the provider flow:
  - Use the authorization-code flow with current state, nonce, PKCE, issuer, signature, audience, redirect, and expiry validation through a maintained OIDC client library.
  - Persist only the provider issuer and subject needed for a stable credential. Make display name optional and do not require or retain email, real name, or unrelated profile claims.
- [ ] Define provisioning, linking, and configuration coherence:
  - Support disabled, invite/allowlist, and automatic provisioning policies so an operator controls whether a valid identity-provider user may create a principal.
  - Validate the access profile and provisioning policy together at startup and refuse to start on an incoherent pair, such as a profile requiring managed sign-in while provisioning is disabled. The stated goal is explicit profiles rather than interacting booleans, and these are two dimensions that can still contradict.
  - Let an existing credential principal link a provider identity after proving possession of both credentials. Require recent authentication for credential linking, unlinking, recovery changes, and session-wide revocation.
- [ ] Define failure and recovery behavior:
  - Define local logout, provider logout guidance, provider-unavailable behavior, identity-provider subject changes, and the recovery path when a provider credential is the principal's only authenticator.
  - Keep initial team roles managed by darklab_shell. Treat identity-provider group-to-team or group-to-role mapping as a separate follow-up decision rather than silently granting capabilities from unreviewed claims.
- [ ] Qualify this entry before it ships:
  - Extend the mode matrix and add browser coverage for provider sign-in success, provider failure, linking, and unlinking.
  - Threat-model provider compromise, subject reuse, privilege changes, and background-work authorization. Record accepted boundaries in `DECISIONS.md`.
  - Update `README.md`, `FEATURES.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`, `DECISIONS.md`, `tests/README.md`, release drafts, and `CHANGELOG.md`. Keep current test counts and the test appendix synchronized.

## Known Issues

### Make WHOIS entity extraction target-aware

A basic WHOIS lookup currently passes most response lines through generic entity extraction. For `whois 164.111.15.52`, the queried IP is useful, but the ARIN response also adds allocation boundaries (`164.111.0.0` and `164.111.255.255`), registry hosts (`rdap.arin.net` and `www.arin.net`), RDAP entity and network references, and ARIN terms-of-use and inaccuracy-reporting URLs to Atlas. Those values describe the registry response; they are not assets discovered for the queried target.

- [ ] Add a WHOIS-specific, command-aware entity extraction path instead of expanding the provider-specific exclusion regex one line at a time. Treat the parsed command target as the authoritative entity and treat the response as registration metadata unless a reviewed WHOIS field has an explicit entity meaning.
- [ ] Keep the queried IP or domain while excluding allocation range endpoints, CIDR network/broadcast values, registrar or RIR infrastructure, referral and `Ref` URLs, contact/entity handles, nameserver/provider hosts, terms-of-use links, and inaccuracy-reporting links from saved entity metadata. Do not change the visible command output or useful WHOIS finding and summary classification as a side effect.
- [ ] Pin the reported ARIN response as a full-transcript regression: the exact saved entity set for `whois 164.111.15.52` contains only the IP `164.111.15.52`, with no `164.111.0.0`, `164.111.255.255`, `rdap.arin.net`, `www.arin.net`, `/registry/entity/`, `/registry/ip/`, terms-of-use, or inaccuracy-reporting entities.
- [ ] Add representative domain WHOIS and non-ARIN/RDAP fixtures so the rule follows field meaning rather than one provider's current wording. Cover command-target parsing, streamed line metadata, final Atlas materialization, Project linkage, and the SQLite/Postgres persistence paths that consume extracted entities.
- [ ] When the fix ships, remove this Known Issue and update the relevant architecture/feature/test documentation, synchronized test counts and appendix, `CHANGELOG.md`, and any active release draft.

---

## Technical Debt

No open technical debt items are currently tracked.

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

### Local accounts for deployments without an identity provider
- Only worth scoping if restricted credentials and managed sign-in leave a real gap: installations that require managed identities but cannot run or reach an identity provider.
- If local authentication is added, allow pseudonymous usernames and do not require email. Define whether registration is disabled, invite-only, or public for each compatible access profile.
- Prefer passkeys where the deployment and browser support them, with downloadable recovery codes and an operator recovery procedure that does not depend on collecting personal information.
- If passwords are supported, use a maintained Argon2id implementation, long-password and password-manager-friendly rules, compromised-password screening, login throttling, safe reset flows, session revocation, and optional MFA. Do not add arbitrary composition rules, password hints, security questions, or periodic rotation.
- Document and test username enumeration, credential stuffing, recovery abuse, lockout denial-of-service, passkey loss, and operator reset boundaries before enabling local registration.

---

## Architecture

### Interactive PTY transport future-state
- Revisit whether the current Redis-brokered SSE plus POST input/resize transport should move to WebSockets after real use.
- The current model keeps deployment simple and avoids a WebSocket runtime, but a bidirectional socket could reduce input latency and simplify the modal terminal stream once PTY usage grows.
