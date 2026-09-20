# Changelog

All notable changes to darklab_shell are documented here.

Entries favor clear outcomes first, then implementation and test details when they help future maintainers understand why the change matters.

## Archives

- [2.x releases](docs/changelog/2.x.md) - versions 2.0 through 2.9.1
- [1.x releases](docs/changelog/1.x.md) - versions 1.0 through 1.7

---

## [3.0.1] - Unreleased

### Added

- **Operators can inspect loaded settings from a read-only desktop and mobile console.** Explicitly granted browser sessions can search reviewed values, source layers, warnings, and host apply guidance. Sensitive settings show approved summaries or withheld markers, snapshots identify the serving worker, and refresh clears stale information after access loss. Existing diagnostics retain their permitted field exposure.

- **Operator verification preserves session limits.** Credential and provider step-up verify the same account, recheck current access, and rotate live browser sessions without extending their original absolute deadline. Operator requests enforce the restricted profile before identity lookup and keep responses private. Signed provider proof is tracked separately from ordinary sign-in recency, so providers that omit it can still use existing session-revocation controls.

- **Instance inspection grants are explicit and auditable.** Local operators can grant, inspect, and revoke principal-bound access independently of Team roles. Grants persist through both database backends, backups, and database migration; repeated operations are predictable and disabled principals cannot receive access.

- **Operators can validate configuration without a working application process.** The local checker shares startup rules, supports candidate YAML and strict/versioned JSON output, and reports reviewed values, counts, presence, or withheld markers without initializing services. A complete field catalog tracks supported inputs and host apply guidance.

- **Configuration evaluation is available without starting the application.** The import-safe builder shares startup normalization and validation, isolates each evaluation's warnings, and exposes a captured startup snapshot without re-reading files or environment.

- **Configuration regression checks pin the existing loading contract.** A table-driven corpus covers effective values, nested provenance, environment precedence, warnings, derived defaults, and invalid-input outcomes.

- **Coding agents have a shared repository guide.** `AGENTS.md` collects the project rules for architecture, security, UI consistency, tests, logging, documentation, and authorized Git/CI work, with links to the detailed contracts. The authorized `todo` workflow uses CI for broad validation, permits a temporary uncommitted pre-commit hook bypass with restoration, and checks pipelines between implementation slices and before final handoff. Contributor guidance uses live test inventories instead of maintaining exact totals.

### Changed

- **Settings, diagnostics, and audit share one operator access policy.** A current principal grant, eligible browser session, and recent credential or provider verification allow access from any network. All three pages are available from the desktop More menu and mobile menu. The audit viewer is at `/audit`, with CSV and JSON downloads at `/audit/export`. Open profiles, Team roles, direct credentials, and PATs don't qualify. Verification preserves useful audit filters, protected requests return safe sign-in destinations, and visible pages clear data and stop refreshes after access loss. Audit exports recheck authorization while streaming; diagnostic records attribute access to the operator without logging filter values. Regression checks cover operator-only navigation, keyboard command expansion, open-profile audit denial, and real Project actions in the granted-operator viewer; diagnostics screenshot scenes use disposable operator grants.

- **Metrics network permissions are independent of operator access.** `metrics_allowed_cidrs` controls `/metrics` only. The deprecated `diagnostics_allowed_cidrs` alias remains metrics-only for 3.0.1, with per-layer precedence, truthful source reporting, and a bounded warning; upgrade guidance identifies its removal in 3.1.0. Neither setting bypasses ordinary AI workspace quotas. Explicit diagnostic AI tests use a shared per-operator limit and retain the global limit and CSRF protection.

### Fixed

- **Container logs use the expected severity streams.** Application, background-worker, and Gunicorn process logs send DEBUG/INFO to stdout and warnings or errors to stderr. Existing verbosity, formatting, redaction, and exception details are preserved, and repeated configuration doesn't duplicate records. Startup and container checks cover both streams, including fatal configuration failures and worker exceptions.

- **Masscan's deterministic smoke check reaches its test container directly.** The fixture supplies the target's Docker MAC address, avoiding Masscan's default gateway path and its dependence on the runner's forwarding policy. Packet traces and the required SYN-ACK preserve evidence of a real successful scan.

- **Browser CI reduces contention across concurrent test projects.** The parallel suite caps CI execution at three workers in total, including the dedicated sign-in projects. Comparison, assessment-batch, output-menu, and logout checks use independent journeys; settings and sign-in checks wait for the relevant response or navigation, and the assessment polling check verifies focus after the monitor is replaced. Test deadlines and failure-on-flaky safeguards remain unchanged.

- **Browser qualification keeps independent workflows within their test budgets.** Operator navigation, settings controls, and access verification run as separate journeys, as do credential management, restoration, and invalid-input checks. The mobile Access test waits for its action to become usable and covers a deliberately held module download. Existing timeout limits and CI's rejection of flaky results stay in place.

- **Disposable test containers clean up their anonymous volumes.** Postgres tests, release-image checks, CI probes, and smoke-test cleanup remove attached anonymous volumes with their containers. Recovery after interrupted smoke runs also removes volumes that lack Compose project labels.

- **Backup exports reject missing Docker volume sources.** The helper checks source volumes before export, so a misspelled or unavailable source fails instead of creating an empty named volume and recording an empty export. Existing source volumes remain in place.

- **Operator pages share consistent headers and navigation.** Diagnostics, Audit log, and Operator settings show the app name, a page subtitle, and links to the other two pages. The desktop overflow menu opens Operator settings in a separate tab or window, keeping the shell available.

- **Operator settings stay easy to browse as the inventory grows.** Group, source, and warning filters respond immediately, including styled dropdown and keyboard selection after refresh. Expandable groups show match counts, Clear filters restores the earlier browsing view, and refresh preserves expanded details, focus, and scroll. Compact cards separate loaded sources from host configuration locations and explain accepted values in plain language; desktop filters stay within reach and mobile controls remain touch-safe. Failed or expired refreshes still clear the inventory.

- **Operator-console helpers have explicit configuration and authentication types.** Configuration failures declare their diagnostic fields, retention accepts the shared configuration mapping, and provider verification checks that proof is present. PostgreSQL fixtures use typed row connections and quoted schema identifiers; authentication tests assert that sessions, rows, and response payloads exist before reading them.

- **The bundled TruffleHog uses a patched AMQP dependency.** Its pinned source release is built with `amqp091-go` v1.13.0 to address AMQP parser and TLS vulnerabilities. The image build verifies the dependency embedded in the executable and includes its license notice.

- **Managed backups now include `compose.operator.yaml` when present.** The archive keeps a private, checksum-verified copy for manual recovery alongside `.env` and operator configuration. Restore preserves the destination host's Compose settings, and older backups remain compatible.

- **Browser tests keep one worker per isolated app server.** Separate projects still run in parallel, while diagnostics layout checks avoid an extra page render from timezone detection. A dedicated browser check covers that redirect, and traces retain the original failed attempt even when its retry passes. CI continues to reject flaky results.

- **Assessment browser checks reliably observe loading states.** Preview and template-refresh fixtures hold their responses until loading-state and scroll checks finish, removing a race caused by fixed response delays on busy CI runners.

- **Access and comparison browser checks tolerate busy CI runners.** Multi-step token, logout, and provider journeys have enough time for their repeated page loads and refreshes. Comparison checks capture the finding highlight when navigation happens, before its brief animation expires.

- **Provider browser checks can repeat after an interrupted attempt.** The local test provider keeps a separate identity for each browser context, and the linking journey clears any operator link left by an earlier attempt before signing in.

- **Access-profile browser checks wait reliably for sign-in navigation.** Credential and provider journeys wait for the new document with a dedicated navigation budget, then verify shell readiness. A successful redirect no longer fails because a URL assertion also waits for every page asset within five seconds.

---

## [3.0.0] - 2026-09-15

### Changed

- **3.0.0 is the stable release.** Application metadata, container defaults, the API contract, and installation and signing examples use the final version. Changelog checks accept both the dated release layout and the active development layout while preserving published release text.

- **Workspace Access introduces pseudonymous principals with portable credentials, scoped API tokens, and optional provider sign-in.** A principal is a stable identity that owns a personal workspace without requiring a username, email address, or password. Personal data and Team membership stay with that identity while credentials and sign-in methods change. **Options → Access** brings workspace access, device and API credentials, provider linking, and session management together.
  - **Keep and manage a workspace:** In an open deployment, **Options → Access** lets anonymous users keep their existing workspace, use a saved credential on another browser, and add, rename, expire, rotate, or revoke credentials. Desktop and mobile show the current access state and only its available actions. Secrets are masked, shown once, and erased from the reveal after use; status indicators show safe hints. Rotation preserves the label, permissions, and expiry and lets the user save the replacement before revoking the old credential. Removing local access doesn't delete the workspace, and other tabs refresh when access changes.
  - **Log out:** The desktop rail's **more** menu and the mobile menu offer a direct **Log out** action when signed in. Confirmation ends access in the current browser and returns to sign-in or a fresh anonymous workspace, preserving the saved workspace, credentials, and other devices. Cancellation restores focus; failed logout remains retryable. Browser coverage exercises desktop keyboard and mobile interactions across all four access profiles, plus failure recovery and isolation from another browser's session.
  - **API tokens and CLI:** Access can issue PATs with chosen permissions and a 1–365-day lifetime, defaulting to 90 days. API v1 accepts only scoped PATs through `Authorization: Bearer`; PATs can't use browser product routes or manage other credentials. Explicit identity reads and self-revocation keep their own scope restrictions, with `oidc_required` accepting PATs only through API v1. The CLI uses `--pat`, `DARKLAB_PAT`, and an owner-only `pat` configuration entry. The shell's `credential` command sends secret-bearing actions to Access rather than accepting secrets in command history. The [API guide](docs/api.md#create-a-pat) covers issuance, permissions, private transfer, expiry, rotation, and verification.
  - **Private sign-in:** Operators can choose `open`, `token_required`, `oidc_required`, or `mixed`. Restricted profiles require sign-in before workspace routes and disable anonymous use and public credential issuance. Credential sign-in exchanges a portable credential for a server-held browser session; normal application JavaScript doesn't receive the reusable credential. A container-only bootstrap creates the first principal in an empty credential-required deployment and writes its one-time secret to a new owner-only file before committing.
  - **Provider sign-in and linking:** OIDC uses HTTPS authorization code, PKCE S256, one-time state and nonce, and signed ID tokens. Provisioning can be disabled, limited to exact provider subjects, or automatic. Linking requires recent proof of both the credential and provider identities; Access offers a direct reauthentication path when needed. Unlinking requires a usable recovery credential and closes every browser session. Provider identities store only issuer and subject, grant no Team roles, and don't transfer ownership when a subject changes. Provider-only deployments offer self-service PATs; portable recovery credentials require an operator-enabled credential sign-in path. [Provider compatibility](CONFIGURATION.md#provider-compatibility) lists the required client authentication, signing algorithms, callbacks, claims, and failure diagnostics.
  - **Sessions and public shares:** HTTPS sessions use secure HttpOnly cookies, CSRF checks, idle and absolute deadlines, and an encrypted signing keyring shared across workers. Team changes and linking preserve the original absolute deadline; fresh sign-in can renew it. Sign-out closes the current session, and **Sign out everywhere** closes all workspace browser sessions while keeping credentials and PATs usable. Recent sign-in is required where applicable. Expired or revoked sessions return to sign-in on the next protected request; failed logout remains retryable. Return links stay on the same deployment, and cross-site requests can't clear saved local access. Public shares are off by default in restricted profiles, with matching desktop, mobile, and keyboard feedback; operators can explicitly allow those capability URLs. Local sign-out doesn't end the provider's own session.
  - **Ownership and storage:** Authenticated data belongs to an immutable personal workspace; Team membership and authority belong to the principal. Credentials are replaceable access methods stored as keyed digests, with encrypted verifier roots and bounded activity writes. Rotation and revocation don't move data or directories. Keeping an anonymous workspace retires its old Files access and download links while preserving files in place; failed attachment preserves anonymous access, and a restored browser can recover by proving its credential. Concurrent first-time SQLite upgrades share one verifier root. Shared owner-query adapters state each table's key and personal-Team representation explicitly, and a checked exception inventory guards relational queries across every subsystem.
  - **Runs and background work:** Workers resolve current principal, workspace, Team membership, and capability state without retaining reusable credentials. Run streams recheck access within 15 seconds, including idle streams, without extending session activity. Revocation disconnects streams and stops a controlling interactive PTY; accepted ordinary commands can finish. Principal disablement stops that principal's personal and Team commands, suspends definitions and queued work, and leaves other principals' work alone. Package and report builds recheck authorization throughout generation, deny completed archives after access loss, and retain private cleanup retries when removal fails.
  - **Recovery and operator controls:** Local commands support safe status, issuance, expiry, rotation, revocation, principal enable/disable, session revocation, and signing-key rotation. Issuing another credential keeps existing access; recovery revokes all portable credentials, PATs, and browser sessions and pauses related schedules, watchers, notifications, and Project digests. Credential revocation can preview and pause related work. Operator status lists work suspended by principal disablement with its workspace and review location. Existing manual pauses stay intact, and enabling access never resumes work automatically. [The operator guide](CONFIGURATION.md#principal-access-operations) covers private secret output, recovery effects, and restoring intended access.
  - **Failure handling and diagnostics:** Malformed, unknown, expired, revoked, and disabled-principal credentials fail closed. Failed-attempt limits are checked before verification and return HTTP 429 with a retry delay, even for a correct credential while the limit is active. Redis degradation preserves local enforcement and reports recovery. Committed lifecycle changes emit INFO milestones; rejected attempts produce sampled warnings; DEBUG records safe decisions and stage timings; unavailable storage, keys, or providers produce sanitized errors. Records omit credentials, provider responses, and private inputs. Provider-details failures remain visible with a retry control. Discovery and signing keys are cached for five minutes, unknown key IDs trigger one refresh, and custom CA changes replace a bounded private bundle. Provider outages reject new sign-ins while valid app sessions retain their normal lifetime.
  - **Identity and schema contract:** Credentials prove access to a principal; personal workspaces own data. Retired session credentials and identity schemas are rejected. Backups retain the matching database backend, vault key, private configuration, and files.
  - **Validation:** SQLite and PostgreSQL cover credential states, scopes, ownership isolation, Team permissions, lifecycle transactions, revocation, storage-key containment, migration and rollback, and digest-only storage. Signed-provider tests cover invalid proofs, freshness and expiry boundaries, replay, binding conflicts, and access lost before callback without changing ownership or identities.
    - **Browser coverage:** Desktop and mobile journeys exercise all four access profiles on SQLite and PostgreSQL in source and bundled asset modes. They check sign-in choices, protected reads and cookies, personal and Team scope, file round trips, reload, and logout, alongside deeper Access lifecycle, provider-linking, public-share, and recovery suites. CI runs both PostgreSQL browser asset modes.
    - **Credential checks:** PostgreSQL request-policy cases cover scoped PAT access. Both backends measure concurrent portable/PAT lookup latency, enforce bounded last-used writes, and reject stored reusable credentials. Disclosure checks compare the complete secret payload, including underscores. Related Python fixtures use explicit state assertions and compatible logging callbacks.

- **SQLite fixture reuse reduces local pytest runtime without weakening database qualification.**
  - **Before:** Ordinary isolated route and backend tests rebuilt the complete current SQLite schema for each case, so a clean fast-lane run grew to roughly six and a half minutes even though most of those tests weren't exercising initialization.
  - **After:** Each pytest process now builds one pristine database through the production initialization path, packages and validates a sidecar-free source, and copies it to a unique path for ordinary empty-schema tests. Migration, schema reconciliation, startup, cutover, failure, rollback, retention, and backend-parity coverage still uses the real initialization path.
  - **Tests:** New guards cover migration head, integrity, foreign keys, FTS, principal-only schema, sidecars, overwrite refusal, and cross-copy isolation. Recorded benchmarks completed three fast-lane runs in 174.86–174.99 seconds; the complete SQLite run fell from 414.35 to 203.70 seconds, and PostgreSQL qualification passed.

- **Shell-output entities now open a compact action menu for investigation and reuse.**
  - **Before:** Activating an entity opened Atlas immediately, while a separate long-press or right-click menu exposed a larger set of output-only actions. That made it easy to navigate away when the intent was to select or reuse the value.
  - **After:** A deliberate click, tap, or keyboard activation offers **Open in Atlas**, **Copy to Clipboard**, and **Insert into command**. The menu uses the entity's canonical value, respects the desktop or mobile command selection without running anything, preserves normal text selection and native right-click behavior, and closes when its context changes. While output follows new lines, the menu stays open and repositions.
  - **Tests:** Vitest covers supported entity types, selection suppression, action wiring, keyboard navigation, viewport placement, clipboard outcomes, and every dismissal path. Playwright exercises live output in source and bundle modes, including real pointer insertion, streaming output scrolling, keyboard use, Atlas handoff, exact composer insertion, shell typing, and a narrow touch viewport.

### Removed

- **Retired the one-time principal identity conversion tool and its migration runbook.** The application uses principal-owned workspaces, and startup continues to reject retired identity schemas. Current credential management, anonymous-workspace attachment, backups, restores, and SQLite-to-Postgres migration remain supported.

### Fixed

- **Mobile Options keeps text fields visible above the keyboard.** Text fields use a 16px font to avoid iOS focus zoom, and the sheet fits above the keyboard while its body scrolls the focused field into view. The backdrop still covers the header so tapping outside closes Options after the browser pans. Browser regressions cover keyboard resizing, backdrop dismissal, and provider sign-in.

- **Workspace preferences survive overlapping loads and routine Options refreshes.** Refreshing an unchanged control no longer counts as a local edit, and older responses can't replace the latest workspace's preferences. Late startup preferences keep the current Options tab open, including Access after a provider sign-in handoff. Regression tests also check that real edits made during loading are preserved.

- **Restoring workspace access avoids repeated credential refreshes.** Applying saved preferences no longer announces the already-selected Options tab as a new selection. This prevents overlapping Access requests from delaying the authenticated state on busy servers. Unit and browser regressions cover the repeated preference sync that caused intermittent CI failures.

- **Environment examples apply the settings they advertise.** The production example keeps all optional Compose profiles in one assignment, so enabling a model or database service isn't overridden by a later empty value. Both OIDC examples leave subjects empty unless allowlist provisioning is selected. Development Compose now forwards `WEB_CONCURRENCY` and `WEB_THREADS`, making the documented overrides effective.

- **Projects modal cards stay readable as the list grows.** Cards keep enough height for wrapped names and count badges, and the sidebar scrolls within the modal while the create controls stay visible. Browser coverage checks adding and deleting across the six-to-seven-project threshold, eight and longer lists, short desktop windows, and mobile navigation.

- **Project workspaces preserve typing, focus, and actions during background refreshes.**
  - **Assessments:** expanded worklists keep their scroll position. Canceling a confirmation returns focus to the current opening control, while choosing another control keeps that choice through later updates.
  - **Package drafts:** loading presets or Assessment choices preserves the focused field, its text, and cursor selection.
  - **Actions:** linking a run keeps its completed confirmation closed. Refreshes don't swallow the click that opens a finding editor, and shared actions run once per click.

- **Concurrent workflow recovery keeps completed steps from failing healthy work.** Recovery reads each execution and its current step together, then advances a completed run only once.

- **Team form refreshes preserve typing and clicks.** Refreshing the Team list keeps the current create, join, or recovery form mounted and usable, so an update cannot disable a focused field or replace the Submit button during a click.

- **Autocomplete recovers when its first catalog request fails.** Startup retries once after a network or server failure, without overlapping requests. Authorization and malformed-response failures stop immediately.

- **Branch images now pick up fixed Debian glibc packages.** The runtime install explicitly refreshes `libc6` and `libc-bin`, and branch CI can bypass the runtime cache for a security recheck without rebuilding the compiled tool stages.

- **WHOIS lookups save the queried target only after a matching registration record.** No-match responses, rate-limit notices, errors, and unrelated records create no Atlas entity. Registration ranges, registry and registrar hosts, nameservers, contact handles, RDAP and referral links, and policy URLs remain in the transcript without becoming Atlas records or Project targets. Existing noisy WHOIS entities remain until you suppress them. See [entity recognition](FEATURES.md#command-findings) for the separate generic, DNS, and WHOIS rules.

- **JavaScript tooling dependencies include the reviewed security fixes.**
  - **Markdown linting:** the scoped override uses `smol-toml` 1.8.0.
  - **Stylelint tooling:** the resolved dependencies use `colord` 2.10.0, `js-yaml` 4.3.2, and `fast-uri` 3.1.7 without changing the parent tooling versions.

- **Container vulnerability scans no longer flag the bundled OpenSSL build.** OpenSSL is updated to the 3.6.4 security patch release with its source archive still protected by a pinned SHA-256 checksum.

---

## [2.9.2] - 2026-08-29

### Changed

- **The desktop and mobile demo tours now reflect the current investigation workflow.** Both recordings cover reusable Workflows, the Project overview, Assessment planning, report preview, and Atlas Quick Lookup alongside the existing command, Files, comparison, monitoring, History, theme, and desktop PTY scenes. The wrappers also accept `--playback-only` to run the complete seeded journey headlessly and catch stale selectors or stalled scenes without requiring OBS.
- **The UI screenshot review pack now covers the current desktop and mobile investigation surfaces.** Its 48 desktop and 41 mobile scenes add the Files inspector and full viewer, parameterized Workflows, Project Overview, monitoring digest settings, Assessment planning, Web Surface, and Atlas Quick Lookup. Filtered History deletion previews now show their real scope and counts, and the capture wrapper uses the normal Playwright helper for both source and bundle runs.
