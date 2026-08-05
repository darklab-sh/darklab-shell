# Configuration

This is the operator-facing configuration reference for darklab_shell. Production installations use `.env`, local files under `conf/`, and optional Compose overrides beside the installed `compose.yaml`. Source checkouts keep their development overrides under `app/conf/`.

For feature behavior, start with [FEATURES.md](FEATURES.md). For internal configuration flow between Flask and the browser, see [ARCHITECTURE.md](ARCHITECTURE.md#configuration-surfaces).

---

## Configuration Model

Shipped application settings live in `app/conf/config.yaml` inside the release image and source checkout. Production operators normally leave that file immutable and put YAML fine-tuning in the installed `conf/config.local.yaml`. Source development uses `app/conf/config.local.yaml` instead. Deployment wiring and feature switches live in `.env`; this keeps Compose services, container startup, lifecycle commands, and the app on the same settings.

Resolution order for the main app config is:

1. Built-in defaults from `app/config.py`
2. `app/conf/config.yaml`
3. Optional local `config.local.yaml`, either beside the shipped file or under `APP_LOCAL_CONF_DIR`
4. Environment variables for deployment-owned settings and supported overrides

Environment variables win when both sources define the same effective setting. The shipped Compose files intentionally provide deployment defaults for Files, database selection, interactive PTY, restricted target CIDRs, raw-packet scanning, Prometheus multiprocess storage, and core AI provider/features. Configure those through `.env`, not YAML. Database pool/JIT values and AI timeout, queue, rate-limit, output, and provider-network tuning remain valid YAML settings; Compose passes an empty value for their optional environment overrides so `config.local.yaml` isn't shadowed by an unused default.

The loader validates the final config at startup. Malformed YAML, a non-mapping file root, or a structurally invalid value stops startup with specific phase, key, and source context. Unknown keys are ignored and logged as `CONFIG_UNKNOWN_KEY_IGNORED` so typos do not quietly become live settings. Error messages redact secret-looking values, including `ai_api_key`, AI secret names, SMTP password secret ids, credential-bearing DSNs such as `database_url`, and webhook-style fields. Non-secret schema values are shown in a shortened form so ordinary typos are easier to fix.

Config events are captured while the files and environment are being resolved, then written once after the effective `log_level` and `log_format` are ready. `CONFIG_VALIDATED` and `CONFIG_LOADED` report a `warning_count` that includes ignored, dropped, defaulted, clamped, and truncated values. If loading can't finish, the app writes one safe `CONFIG_LOAD_FAILED` record using the most recent usable text or GELF format. It includes bounded phase, source, key, and error-type fields, but not raw parser output, file contents, configuration values, or a traceback.

Nested sections such as `notifications`, `notifications.smtp`, `scheduler`, `watchers`, `project_digests`, and `cve_risk` merge by field. A local file can override one nested value without restating the whole section.

The runtime keeps one validated effective config after startup. Operators normally work with the YAML files and environment variables above; Python callers that need implementation details should use the conventions in [ARCHITECTURE.md](ARCHITECTURE.md#configuration-surfaces) and [CONTRIBUTING.md](CONTRIBUTING.md#branch-workflow).

### Schema Contract

The application settings table below is the YAML fine-tuning reference. Deployment-owned settings appear in [Environment Variables and `.env`](#environment-variables-and-env) instead. Their lowercase effective keys still exist inside the app for runtime checks, logging, registry feature requirements, and tests, but they aren't operator-facing YAML options.

The schema contract is:

| Field group | Validation posture |
|-------------|--------------------|
| Top-level strings, booleans, integers, floats, and lists | Validated by type after file overlays and environment variables are applied. Unknown keys are ignored with `CONFIG_UNKNOWN_KEY_IGNORED` |
| Nested sections | `notifications`, `notifications.smtp`, `notifications.retry`, `notifications.events`, `scheduler`, `watchers`, `project_digests`, and `cve_risk` are structured sections. They merge by field, and invalid shapes such as `scheduler: false` or `notifications: []` stop startup |
| Forgiving booleans | Boolean environment settings plus YAML settings such as `database_postgres_jit`, `audit_log_enabled`, `ai_allow_full_output`, and `ai_require_private_base_url` accept common string forms such as `true`, `false`, `yes`, `no`, `on`, and `off`; invalid values fall back and log `CONFIG_VALUE_DEFAULTED` |
| Forgiving integers | Database pool limits, audit limits, and AI numeric limits accept numeric strings; invalid values fall back, below-minimum values are clamped, and `audit_export_max_rows` is capped at `200000` |
| Forgiving MB values | `output_preview_max_mb` and `full_output_max_mb` accept numeric YAML values and strings such as `25mb`; invalid values fall back |
| Normalized lists | CIDR lists and `output_entity_extra_domain_suffixes` drop invalid entries with key/source warning logs. Redaction rules are normalized through the same snapshot-share rule validator used at runtime |
| Derived effective keys | `output_preview_max_bytes` is derived from `output_preview_max_mb`, and `full_output_max_bytes` is derived from `full_output_max_mb` unless the legacy byte key is supplied and the MB key is still at its built-in default |
| Secret-looking values | Load errors and config object representations redact API keys, secret names/ids, passwords, webhook-like keys, and credential-bearing URLs such as `database_url` |

Settings are read at startup. After changing `config.local.yaml` or `.env`, recreate the app container so environment changes and YAML changes are both applied. In a production installation:

```bash
docker compose up -d --force-recreate shell
```

In a source checkout:

```bash
docker compose -f compose.dev.yaml up -d --force-recreate shell
```

No image rebuild is needed for normal config changes.

---

## Local Override Files

Most operator-owned files under `app/conf/` and `app/conf/themes/` support `*.local.*` overlays. Source development keeps those files beside the shipped files. Production installations keep the same relative names under host `./conf`, mounted at `/config`, while immutable defaults remain under `/app/conf`.

The installer keeps the host overlay tree at `0700` with files at `0600`. Container startup rejects symlinks and special files, then stages the tree into a private `appuser`-owned runtime directory before dropping privileges. Restart the shell container after editing a production host overlay so it stages a fresh snapshot. `CONFIG_LOADED` reports the shipped and local roots, while DEBUG diagnostics can list safe relative names for present supported overlays; neither log includes file contents. Missing and comment-only optional overlays are normal and don't produce warnings.

| Shipped base | Production local overlay | Development overlay | Behavior |
|--------------|-------------------------------|----------------------------|----------|
| `app/conf/config.yaml` | `conf/config.local.yaml` | `app/conf/config.local.yaml` | Overrides application YAML fine-tuning settings |
| `app/conf/assessment_profiles.yaml` | `conf/assessment_profiles.local.yaml` | `app/conf/assessment_profiles.local.yaml` | Adds complete profiles or replaces a complete profile with the same key |
| `app/conf/commands.yaml` | `conf/commands.local.yaml` | `app/conf/commands.local.yaml` | Adds new command roots and merges same-root entries into the base registry |
| `app/conf/faq.yaml` | `conf/faq.local.yaml` | `app/conf/faq.local.yaml` | Appends local FAQ entries |
| `app/conf/welcome.yaml` | `conf/welcome.local.yaml` | `app/conf/welcome.local.yaml` | Appends local welcome samples |
| `app/conf/workflows.yaml` | `conf/workflows.local.yaml` | `app/conf/workflows.local.yaml` | Appends local guided workflows |
| `app/conf/ascii.txt` | `conf/ascii.local.txt` | `app/conf/ascii.local.txt` | Replaces desktop banner art |
| `app/conf/ascii_mobile.txt` | `conf/ascii_mobile.local.txt` | `app/conf/ascii_mobile.local.txt` | Replaces mobile banner art |
| `app/conf/app_hints.txt` | `conf/app_hints.local.txt` | `app/conf/app_hints.local.txt` | Appends desktop hints |
| `app/conf/app_hints_mobile.txt` | `conf/app_hints_mobile.local.txt` | `app/conf/app_hints_mobile.local.txt` | Appends mobile hints |
| `app/conf/themes/<theme>.yaml` | `conf/themes/<theme>.local.yaml` | `app/conf/themes/<theme>.local.yaml` | Overlays one named theme |

A theme overlay can change a shipped theme but doesn't create a new theme-selector entry.

Malformed shipped or local theme YAML falls back to the valid values that remain. The container logs `THEME_OVERLAY_LOAD_FAILED` with only the bounded path, source type, and parser error type; it never includes theme contents or the raw parser message.

Package presets and report templates are complete replacement catalogs rather than merge overlays. Select `package_presets.local.yaml` or `report_templates.local.yaml` in `config.local.yaml`; relative filenames containing `.local.` resolve from the operator root. `tour.yaml` and `wordlists.yaml` are image-owned catalogs and don't have local overlay filenames.

---

## Config File Reload Behavior

The table describes loader behavior after the app process can read the selected files. Source-mounted development stages the checkout into a fresh `/app` snapshot, while production stages its private overlay tree separately. In either mode, restart the shell container after a host-side configuration edit.

| File | When changes take effect |
|------|--------------------------|
| `conf/assessment_profiles.yaml` | Immediately for the next assessment-profile read; invalid reloads keep the last valid catalog |
| `conf/faq.yaml` | Immediately; re-read on every request |
| `conf/ascii.txt` | On next page load |
| `conf/ascii_mobile.txt` | On next page load |
| `conf/app_hints.txt` | On next page load |
| `conf/app_hints_mobile.txt` | On next page load |
| `conf/welcome.yaml` | On next page load |
| `conf/tour.yaml` | Immediately for tour renderers |
| `conf/wordlists.yaml` | Immediately for the `wordlist` command and autocomplete requests |
| `conf/workflows.yaml` | Immediately for Workflows panel, command registry, and smoke-corpus helpers |
| `conf/themes/*.yaml` | After the app process restarts |
| `conf/commands.yaml` | On next page load for autocomplete; immediately for command policy, catalog, diagnostics, and smoke-corpus helpers |
| `conf/config.yaml` | After `docker compose restart` |
| `conf/config.local.yaml` | After `docker compose restart` |

---

## Assessment Profile Catalog

`app/conf/assessment_profiles.yaml` contains the maintained Network and Web assessment profiles. Each profile describes the targets it applies to, its versioned checks, the saved evidence that can satisfy those checks, the action the app should recommend, and the plain-language condition for calling the check complete.

Use `assessment_profiles.local.yaml` to add a deployment-specific profile or replace a shipped profile with the same stable key. A local profile is always a complete definition: individual checks and fields don't merge with the shipped copy. This keeps saved cycle snapshots understandable even after the live catalog changes.

The loader rejects duplicate profile, check, and evidence-rule keys; unsupported target or evidence types; unknown command/workflow references; unsupported policy levels; oversized definitions; and malformed YAML. A rejected local reload leaves the whole last valid catalog active and logs `ASSESSMENT_PROFILE_LOCAL_CATALOG_REJECTED` without logging the file contents. Comment-only local files are inactive and don't produce a warning.

The shipped file is the best starting point for the current schema. Every custom definition uses catalog `version: 1`; stable lowercase keys; dotted profile, check, and evidence-rule versions; one or more target types from `domain`, `ip`, `port`, or `url`; and a recommended action in `command:<root>` or `workflow:<id>` form. Evidence rules can refer only to saved runs, workflow executions, findings, Atlas entities, run artifacts, workspace artifacts, or screenshots. Their command and workflow references must already exist in the active command/workflow catalogs.

---

## Headless CLI Configuration

The bundled `darklab` CLI talks to `/api/v1` and keeps its own client-side settings. These do not change server behavior.

Resolution order is:

1. command flags: `--api-url`, `--token`, `--team`, and `--timeout`
2. environment variables: `DARKLAB_API_URL`, `DARKLAB_TOKEN`, `DARKLAB_TEAM`, and `DARKLAB_TIMEOUT`
3. `~/.config/darklab/config.toml`
4. built-in defaults

Example:

```toml
api_url = "https://shell.example.com"
token = "tok_your_session_token"
team = "team_optional_scope"
timeout = 30
```

`api_url` must include `http://` or `https://`. Custom ports are supported, so local installs can use values like `http://192.168.1.3:9999`. The file is parsed as TOML, so inline comments and numeric timeout values work normally. When the CLI writes this file, it keeps owner-only `0600` permissions because the file can store a session token and active team scope.

Use [docs/api.md](docs/api.md) for endpoint examples and CLI commands.

---

## Application YAML Settings

The values below are the built-in server defaults that operators can fine-tune with `config.local.yaml`. Deployment-owned settings are intentionally omitted and live in `.env` instead.

Project workspace settings cap session-scoped case folders, links, targets, labels, notes, and package exports. Interactive PTY settings tune the separate guarded terminal path after `INTERACTIVE_PTY_ENABLED=true` enables it.

| Setting | Default | Description |
|---------|---------|-------------|
| `app_name` | `darklab_shell` | Name shown in the browser tab, header, permalink pages, and outbound notification titles/messages. Values longer than 20 visible characters are shortened at startup |
| `app_public_base_url` | _(empty)_ | Public URL used by background workers for outbound notification links. Leave empty to send in-app relative paths |
| `prompt_username` | `anon` | Default username shown in the shell prompt and welcome samples. Users can override this in Options for their own session |
| `prompt_domain` | `darklab.sh` | Domain shown after the prompt username. The UI renders `<username>@<domain>:~ $` when workspaces are disabled and `<username>@<domain>:<workspace path> $` when workspaces are enabled |
| `motd` | _(empty)_ | Optional operator message shown at the top of the welcome sequence as a centered “Message From The Operator” notice. Supports `**bold**`, `` `code` ``, `[link](url)`, and newlines. Leave empty to disable |
| `default_theme` | `darklab_obsidian.yaml` | Default theme filename for new visitors. Must match a file in `app/conf/themes/`. Overridden by the user's saved preference |
| `asset_bundle_mode` | `bundle` | Frontend asset rendering mode. `bundle` renders content-hashed files from `app/static/build/` for bundles, lazy modules, fonts, favicon, and standalone vendor/static assets, uses minified ESM build output, serves precompressed Brotli or gzip siblings when the browser supports them, and fails if the committed build output is missing or incomplete; `source` keeps local edit-and-refresh work direct by linking ordered CSS sources and emitting ES module entries plus lazy JS modules as unversioned source URLs so the browser follows each import graph with one URL identity. Classic vendor assets still use direct versioned URLs. `ASSET_BUNDLE_MODE` can also override this setting |
| `share_redaction_enabled` | `true` | Enables the built-in basic snapshot-share redaction baseline for bearer tokens, email addresses, IPv4 addresses, IPv6 addresses, hostnames/dotted domains, and PEM or PGP private-key blocks. Private-key blocks are removed even when they span several output lines. When enabled, the `share snapshot` action asks whether to share the raw or redacted snapshot until the user sets a persistent default in the Options modal. If the prompt’s checkbox is enabled, the chosen raw/redacted mode is written back to that same persistent default. When disabled, no built-in or custom snapshot-share redaction runs |
| `share_redaction_rules` | `[]` | Optional operator-defined regex rules appended after the built-in snapshot-share redaction baseline. Each rule supports `label`, `pattern`, `replacement`, and `flags` (`i`, `m`). This does not change stored run history or the history drawer permalink path; it affects only snapshot sharing |
| `trusted_proxy_cidrs` | `["127.0.0.1/32", "::1/128"]` | IPs / CIDRs allowed to supply `X-Forwarded-For`. Requests outside these ranges ignore forwarded headers and use the direct connection IP |
| `diagnostics_allowed_cidrs` | `[]` | IPs / CIDRs that may access `/diag`, `/diag/audit`, and `/metrics`. Checked against the resolved client IP using the same trusted-proxy rules as the rest of the app, so `X-Forwarded-For` is honored only when the direct peer is inside `trusted_proxy_cidrs`. Empty list disables the diagnostics and audit pages and prevents metrics scrapes. When enabled, a `diag` button appears in the desktop rail and the mobile menu for matching visitors. Anyone allowed here can use the operator-wide audit viewer, including personal/team activity and stored request metadata, so keep this list narrow. Matching clients also bypass the per-session AI assist write quota for operator testing, but the global AI write limit still applies |
| `metrics_enabled` | `true` | Enables the Prometheus `/metrics` endpoint for callers allowed by `diagnostics_allowed_cidrs`. Set to `false` to hide `/metrics` while keeping `/diag` available |
| `metrics_histogram_buckets_run_duration` | `[0.1, 0.5, 1, 2, 5, 10, 30, 60, 300, 900, 1800, 3600]` | Prometheus run and PTY duration histogram buckets, in seconds |
| `metrics_histogram_buckets_http_duration` | `[0.005, 0.01, 0.05, 0.1, 0.5, 1, 5]` | Prometheus HTTP request duration histogram buckets, in seconds |
| `metrics_histogram_buckets_ai_provider_duration` | `[0.1, 0.5, 1, 2, 5, 10, 30, 60]` | Prometheus AI provider duration histogram buckets, in seconds |
| `ai_connect_timeout_seconds` | `5` | Provider TCP connect timeout |
| `ai_timeout_seconds` | `120` | Provider read timeout. Local CPU models can need longer than normal HTTP calls, and AI assists run in the worker path rather than tying up a route worker |
| `ai_max_input_chars` | `24000` | Maximum assembled prompt context size, measured in characters rather than tokens |
| `ai_max_output_tokens` | `120` | Provider output cap for summary JSON responses. Summaries ask the model only for short prose so local CPU providers return sooner |
| `ai_next_commands_max_output_tokens` | `180` | Provider output cap for next-command JSON responses. This is higher than summaries because suggestions need enough room to close valid JSON |
| `ai_max_concurrent` | `1` | Global provider-call concurrency target for the AI worker path |
| `ai_max_queue_depth` | `20` | Maximum queued/in-progress assist backlog before writes should return busy |
| `ai_rate_limit_per_session_hour` | `5` | Per-session AI write limit enforced through Redis before new assists are queued. Clients allowed by `diagnostics_allowed_cidrs` bypass this per-session quota only |
| `ai_rate_limit_global_per_minute` | `2` | Deployment-wide AI write limit enforced through Redis so multiple workers cannot overload a local model |
| `ai_allow_full_output` | `false` | Lets AI context assembly read complete persisted output as source material for bounded prompt sections. It does not send an unbounded full transcript |
| `ai_require_private_base_url` | `true` | Requires provider hosts to resolve to loopback/private/link-local addresses or an allowed CIDR |
| `ai_base_url_allowed_cidrs` | `[]` | Extra CIDRs allowed for AI providers when `ai_require_private_base_url` is enabled |
| `ai_prompt_version_override` | _(empty)_ | Optional prompt version override for staging comparisons |
| `history_panel_limit` | `50` | Number of history rows shown per page in the desktop history drawer and mobile recents sheet |
| `recent_commands_limit` | `50` | Number of distinct recent commands loaded into prompt Up/Down history, desktop rail recents, and the mobile recent peek |
| `data_dir` | auto | Server-side only. Directory used for the default SQLite history database, compressed full-output artifacts, body-store files, and the app-owned secret key file. Postgres deployments still use it for filesystem-backed artifacts and app-owned files. Leave unset to use `/data` when it is writable, otherwise `/tmp` for local/dev fallback. If set explicitly, the directory must be writable at startup |
| `database_pool_min` | `1` | Server-side only. Minimum Postgres pool size. Ignored by SQLite. Can also be set with `DATABASE_POOL_MIN` |
| `database_pool_max` | `5` | Server-side only. Maximum Postgres pool size. Ignored by SQLite. Can also be set with `DATABASE_POOL_MAX` |
| `database_postgres_jit` | `false` | Server-side only. Controls whether app-owned Postgres pool connections allow PostgreSQL JIT compilation. The default keeps interactive pages from paying JIT startup cost on complex queries. Can also be set with `DATABASE_POSTGRES_JIT` |
| `permalink_retention_days` | `365` | Delete runs, snapshots, and related run-output artifacts older than this many days at startup and during the scheduler worker's daily retention pass. `0` means unlimited retention |
| `audit_log_enabled` | `true` | Server-side only. Enables audit event recording. When set to `false`, the audit recorder writes no rows and normal product writes continue; the app logs this once at startup so operators know the compliance trail is disabled |
| `audit_retention_days` | `90` | Server-side only. Delete audit event rows older than this many days on startup and periodically while the app is running. `0` means unlimited retention |
| `audit_export_max_rows` | `10000` | Server-side only. Maximum number of audit rows `/diag/audit` CSV/JSON exports return in one request. Values above `200000` are capped, and truncated exports include a marker row or flag |
| `runs_search_text_inline_max_bytes` | `0` | Server-side only. Offloads oversized `runs.output_search_text` values to compressed files under `data_dir/body-store` when the UTF-8 body is larger than this byte threshold. History search still checks the offloaded body when needed, so terms beyond the stored preview remain findable. `0` keeps values inline |
| `snapshots_inline_max_bytes` | `0` | Server-side only. Offloads oversized tab snapshot bodies under `data_dir/body-store` while share links still read back normally. `0` keeps snapshot content inline |
| `intel_payload_inline_max_bytes` | `0` | Server-side only. Offloads oversized Atlas intel provider payloads under `data_dir/body-store` while entity detail responses still return the provider data. `0` keeps intel payloads inline |
| `output_entity_extra_domain_suffixes` | `[]` | Server-side only. Extra non-public suffixes accepted by generic command-output domain extraction, such as `local` or `corp`. Full URLs, scanner-specific parsers, imports, and explicit project targets use their own stronger paths and are not gated by this setting |
| `rate_limit_enabled` | `true` | Enables the shared HTTP rate limiter. Set to `false` only for test-only or maintenance overlays where throttling should be bypassed |
| `http_rate_limit_per_minute` | `240` | Baseline limit for dynamic app routes that do not already have a tighter route-specific limit. Static assets are exempt, so normal page loads still work while broad scanners hitting random paths are throttled. Set to `0` to disable this baseline while keeping route-specific limits |
| `http_rate_limit_per_second` | `60` | Baseline burst limit for dynamic app routes that do not already have a tighter route-specific limit. This leaves room for the app's first-load request fan-out while the minute limit still caps sustained unknown-path scans. Set to `0` to disable this baseline while keeping route-specific limits |
| `rate_limit_per_minute` | `30` | Max command-start and API requests per minute per IP |
| `rate_limit_per_second` | `5` | Max command-start and API requests per second per IP |
| `team_read_rate_limit_per_minute` | `180` | Max team-management read requests per minute. The Options Teams tab, desktop HUD scope selector, mobile scope selector, and `/api/v1/teams` list/detail routes use this token-keyed limit |
| `team_read_rate_limit_per_second` | `20` | Max team-management read requests per second for the same read surfaces |
| `team_write_rate_limit_per_minute` | `30` | Max team-management write requests per minute for create, join, invite, membership, archive/reactivate, leave, and recovery-code changes |
| `intel_cache_ttl_shodan_ip_seconds` | `86400` | Server-side only. Default cache lifetime for normalized Shodan IP responses |
| `intel_cache_ttl_shodan_search_seconds` | `21600` | Server-side only. Default cache lifetime for normalized Shodan search responses |
| `intel_cache_ttl_shodan_internetdb_ip_seconds` | `86400` | Server-side only. Default cache lifetime for normalized Shodan InternetDB IP responses |
| `intel_cache_ttl_censys_host_seconds` | `21600` | Server-side only. Default cache lifetime for normalized Censys host responses |
| `intel_cache_ttl_virustotal_domain_seconds` | `21600` | Server-side only. Default cache lifetime for normalized VirusTotal domain responses |
| `intel_cache_ttl_virustotal_file_seconds` | `86400` | Server-side only. Default cache lifetime for normalized VirusTotal file or hash responses |
| `intel_cache_ttl_greynoise_ip_seconds` | `3600` | Server-side only. Default cache lifetime for normalized GreyNoise IP responses |
| `intel_cache_ttl_otx_indicator_seconds` | `21600` | Server-side only. Default cache lifetime for normalized AlienVault OTX indicator responses |
| `intel_cache_ttl_abuseipdb_ip_seconds` | `21600` | Server-side only. Default cache lifetime for normalized AbuseIPDB IP responses |
| `intel_cache_ttl_ipinfo_ip_seconds` | `21600` | Server-side only. Default cache lifetime for normalized IPinfo IP responses |
| `intel_cache_ttl_teamcymru_ip_seconds` | `86400` | Server-side only. Default cache lifetime for normalized Team Cymru IP ownership responses |
| `intel_cache_ttl_tls_certificate_domain_seconds` | `21600` | Server-side only. Default cache lifetime for live TLS certificate domain responses |
| `intel_cache_ttl_crtsh_domain_seconds` | `86400` | Server-side only. Default cache lifetime for normalized crt.sh domain responses |
| `intel_cache_ttl_hibp_password_seconds` | `604800` | Server-side only. Default cache lifetime for HIBP Pwned Passwords SHA1 range responses |
| `intel_cache_ttl_nvd_cve_seconds` | `86400` | Server-side only. Default cache lifetime for normalized NVD CVE responses |
| `intel_cache_ttl_vulners_cve_seconds` | `86400` | Server-side only. Default cache lifetime for normalized Vulners CVE responses |
| `intel_cache_ttl_urlscan_search_seconds` | `21600` | Server-side only. Default cache lifetime for normalized urlscan.io search responses |
| `intel_cache_ttl_urlscan_result_seconds` | `86400` | Server-side only. Default cache lifetime for normalized urlscan.io result responses |
| `intel_cache_ttl_urlhaus_host_seconds` | `21600` | Server-side only. Default cache lifetime for normalized URLhaus host responses |
| `intel_cache_ttl_urlhaus_payload_seconds` | `86400` | Server-side only. Default cache lifetime for normalized URLhaus payload hash responses |
| `intel_cache_ttl_urlhaus_url_seconds` | `21600` | Server-side only. Default cache lifetime for normalized URLhaus URL responses |
| `intel_cache_ttl_threatfox_ioc_seconds` | `21600` | Server-side only. Default cache lifetime for normalized ThreatFox IOC responses |
| `intel_cache_ttl_threatfox_hash_seconds` | `86400` | Server-side only. Default cache lifetime for normalized ThreatFox hash responses |
| `intel_cache_ttl_securitytrails_domain_seconds` | `86400` | Server-side only. Default cache lifetime for normalized SecurityTrails domain responses |
| `intel_cache_ttl_routeviews_prefix_seconds` | `21600` | Server-side only. Default cache lifetime for normalized RouteViews prefix responses |
| `intel_cache_ttl_fofa_search_seconds` | `21600` | Server-side only. Default cache lifetime for normalized FOFA search responses |
| `intel_cache_ttl_zoomeye_search_seconds` | `21600` | Server-side only. Default cache lifetime for normalized ZoomEye search responses |
| `intel_rate_limit_shodan_bucket` | `5` | Server-side only. Token-bucket size for Shodan lookups per session |
| `intel_rate_limit_shodan_refill_seconds` | `1` | Server-side only. Seconds between Shodan token refills |
| `intel_rate_limit_shodan_internetdb_bucket` | `30` | Server-side only. Token-bucket size for Shodan InternetDB lookups per session |
| `intel_rate_limit_shodan_internetdb_refill_seconds` | `2` | Server-side only. Seconds between Shodan InternetDB token refills |
| `intel_rate_limit_censys_bucket` | `10` | Server-side only. Token-bucket size for Censys lookups per session |
| `intel_rate_limit_censys_refill_seconds` | `6` | Server-side only. Seconds between Censys token refills |
| `intel_rate_limit_virustotal_public_bucket` | `4` | Server-side only. Token-bucket size for VirusTotal Public API lookups per session |
| `intel_rate_limit_virustotal_public_refill_seconds` | `15` | Server-side only. Seconds between VirusTotal Public API token refills |
| `intel_rate_limit_greynoise_community_bucket` | `50` | Server-side only. Token-bucket size for GreyNoise Community lookups per session |
| `intel_rate_limit_greynoise_community_refill_seconds` | `12096` | Server-side only. Seconds between GreyNoise Community token refills |
| `intel_rate_limit_greynoise_unauthenticated_bucket` | `10` | Server-side only. Token-bucket size for unauthenticated GreyNoise fallback lookups |
| `intel_rate_limit_greynoise_unauthenticated_refill_seconds` | `8640` | Server-side only. Seconds between unauthenticated GreyNoise fallback token refills |
| `intel_rate_limit_otx_bucket` | `30` | Server-side only. Token-bucket size for AlienVault OTX lookups per session |
| `intel_rate_limit_otx_refill_seconds` | `2` | Server-side only. Seconds between AlienVault OTX token refills |
| `intel_rate_limit_abuseipdb_bucket` | `20` | Server-side only. Token-bucket size for AbuseIPDB lookups per session |
| `intel_rate_limit_abuseipdb_refill_seconds` | `4` | Server-side only. Seconds between AbuseIPDB token refills |
| `intel_rate_limit_ipinfo_bucket` | `30` | Server-side only. Token-bucket size for IPinfo lookups per session |
| `intel_rate_limit_ipinfo_refill_seconds` | `2` | Server-side only. Seconds between IPinfo token refills |
| `intel_rate_limit_teamcymru_bucket` | `30` | Server-side only. Token-bucket size for Team Cymru lookups per session |
| `intel_rate_limit_teamcymru_refill_seconds` | `2` | Server-side only. Seconds between Team Cymru token refills |
| `intel_rate_limit_tls_certificate_bucket` | `20` | Server-side only. Token-bucket size for live TLS certificate lookups per session |
| `intel_rate_limit_tls_certificate_refill_seconds` | `3` | Server-side only. Seconds between live TLS certificate token refills |
| `intel_rate_limit_crtsh_bucket` | `10` | Server-side only. Token-bucket size for crt.sh lookups per session |
| `intel_rate_limit_crtsh_refill_seconds` | `6` | Server-side only. Seconds between crt.sh token refills |
| `intel_rate_limit_hibp_bucket` | `10` | Server-side only. Token-bucket size for HIBP Pwned Passwords lookups per session |
| `intel_rate_limit_hibp_refill_seconds` | `2` | Server-side only. Seconds between HIBP Pwned Passwords token refills |
| `intel_rate_limit_nvd_anonymous_bucket` | `5` | Server-side only. Token-bucket size for anonymous NVD lookups per session |
| `intel_rate_limit_nvd_anonymous_refill_seconds` | `6` | Server-side only. Seconds between anonymous NVD token refills |
| `intel_rate_limit_vulners_bucket` | `10` | Server-side only. Token-bucket size for Vulners lookups per session |
| `intel_rate_limit_vulners_refill_seconds` | `6` | Server-side only. Seconds between Vulners token refills |
| `intel_rate_limit_urlscan_bucket` | `10` | Server-side only. Token-bucket size for urlscan.io lookups per session |
| `intel_rate_limit_urlscan_refill_seconds` | `6` | Server-side only. Seconds between urlscan.io token refills |
| `intel_rate_limit_urlhaus_bucket` | `20` | Server-side only. Token-bucket size for URLhaus lookups per session |
| `intel_rate_limit_urlhaus_refill_seconds` | `3` | Server-side only. Seconds between URLhaus token refills |
| `intel_rate_limit_threatfox_bucket` | `20` | Server-side only. Token-bucket size for ThreatFox lookups per session |
| `intel_rate_limit_threatfox_refill_seconds` | `3` | Server-side only. Seconds between ThreatFox token refills |
| `intel_rate_limit_securitytrails_bucket` | `10` | Server-side only. Token-bucket size for SecurityTrails lookups per session |
| `intel_rate_limit_securitytrails_refill_seconds` | `6` | Server-side only. Seconds between SecurityTrails token refills |
| `intel_rate_limit_routeviews_bucket` | `20` | Server-side only. Token-bucket size for RouteViews lookups per session |
| `intel_rate_limit_routeviews_refill_seconds` | `3` | Server-side only. Seconds between RouteViews token refills |
| `intel_rate_limit_fofa_bucket` | `10` | Server-side only. Token-bucket size for FOFA lookups per session |
| `intel_rate_limit_fofa_refill_seconds` | `6` | Server-side only. Seconds between FOFA token refills |
| `intel_rate_limit_zoomeye_bucket` | `10` | Server-side only. Token-bucket size for ZoomEye lookups per session |
| `intel_rate_limit_zoomeye_refill_seconds` | `6` | Server-side only. Seconds between ZoomEye token refills |
| `intel_negative_cache_virustotal_quota_seconds` | `21600` | Server-side only. Fallback cache window for VirusTotal quota-exhausted responses when no reset time is available |
| `intel_negative_cache_censys_quota_seconds` | `21600` | Server-side only. Fallback cache window for Censys quota-exhausted responses when no reset time is available |
| `intel_negative_cache_otx_quota_seconds` | `21600` | Server-side only. Fallback cache window for AlienVault OTX quota-exhausted responses when no reset time is available |
| `intel_negative_cache_abuseipdb_quota_seconds` | `21600` | Server-side only. Fallback cache window for AbuseIPDB quota-exhausted responses when no reset time is available |
| `intel_negative_cache_ipinfo_quota_seconds` | `21600` | Server-side only. Fallback cache window for IPinfo quota-exhausted responses when no reset time is available |
| `intel_negative_cache_urlhaus_quota_seconds` | `21600` | Server-side only. Fallback cache window for URLhaus quota-exhausted responses when no reset time is available |
| `intel_negative_cache_vulners_quota_seconds` | `21600` | Server-side only. Fallback cache window for Vulners quota-exhausted responses when no reset time is available |
| `intel_negative_cache_urlscan_quota_seconds` | `21600` | Server-side only. Fallback cache window for urlscan.io quota-exhausted responses when no reset time is available |
| `intel_negative_cache_threatfox_quota_seconds` | `21600` | Server-side only. Fallback cache window for ThreatFox quota-exhausted responses when no reset time is available |
| `intel_negative_cache_securitytrails_quota_seconds` | `21600` | Server-side only. Fallback cache window for SecurityTrails quota-exhausted responses when no reset time is available |
| `intel_negative_cache_fofa_quota_seconds` | `21600` | Server-side only. Fallback cache window for FOFA quota-exhausted responses when no reset time is available |
| `intel_negative_cache_zoomeye_quota_seconds` | `21600` | Server-side only. Fallback cache window for ZoomEye quota-exhausted responses when no reset time is available |
| `interactive_pty_input_rate_limit_per_minute` | `500` | Max interactive PTY input requests per minute per IP. This is separate from `/runs` because normal terminal typing produces many small input requests |
| `interactive_pty_input_rate_limit_per_second` | `10` | Max interactive PTY input request burst per second per IP |
| `interactive_pty_resize_rate_limit_per_minute` | `600` | Max interactive PTY resize requests per minute per IP. This is separate from `/runs` because normal browser layout changes can produce short resize bursts |
| `interactive_pty_resize_rate_limit_per_second` | `30` | Max interactive PTY resize request burst per second per IP |
| `max_tabs` | `8` | Maximum number of tabs a user can have open at once. `0` means unlimited |
| `max_output_lines` | `5000` | Max rows retained in the live tab DOM and in the saved run preview. Oldest rendered rows are dropped from the top when exceeded, while visible line numbers continue reflecting emitted output order. Server-side `sort` and `uniq` pipe helpers also use this as their buffered input cap and emit a `[post-filter]` notice when later lines are skipped. `0` means unlimited |
| `high_volume_output_line_threshold` | `50000` | Browser-facing. Pauses live rendering for brokered command output after this many received lines. Output keeps counting, kill controls stay available, and backend preview/full-output storage still follows the normal output settings. `0` disables the pause |
| `high_volume_output_status_interval_lines` | `50000` | Browser-facing. When high-volume live-output mode is active, show another status line after this many additional received lines |
| `output_preview_max_mb` | `1 MB` | Server-side only. Hard cap on the saved run preview payload so huge single-line outputs, such as JSON, cannot make history rows enormous. `0` means unlimited |
| `output_preview_max_bytes` | derived from `output_preview_max_mb` | Server-side only. Effective byte value used by storage code after startup. Operators should set `output_preview_max_mb`; this key exists so runtime callers can use one byte-count value |
| `persist_full_run_output` | `true` | Server-side only. Persists full output for completed runs as compressed artifacts while the history drawer and normal run permalink keep using the capped database preview |
| `full_output_max_mb` | `5 MB` | Server-side only. Hard cap on the uncompressed UTF-8 payload written into a full-output artifact before gzip compression. `0` means unlimited |
| `full_output_max_bytes` | derived from `full_output_max_mb` | Server-side only. Effective byte value used by artifact storage after startup. Operators should set `full_output_max_mb`; legacy byte-based config is still accepted only when the MB setting is left at its built-in default |
| `workspace_quota_mb` | `50 MB` | Server-side only. Per-owner workspace quota for each personal or team workspace |
| `workspace_max_file_mb` | `5 MB` | Server-side only. Maximum single app-managed text file size |
| `workspace_max_files` | `100` | Server-side only. Maximum file count per session workspace |
| `workspace_inactivity_ttl_hours` | `1` | Server-side only. Inactive session workspace cleanup threshold in hours; `0` disables age-based cleanup. Workspace activity touches the hashed session directory, and periodic cleanup removes expired `sess_*` directories rather than aging out individual files |
| `max_projects_per_session` | `100` | Server-side only. Maximum project workspace records one session can create |
| `max_project_links_per_project` | `5000` | Server-side only. Maximum linked source records per project |
| `max_project_entities_per_project` | `5000` | Server-side only. Maximum Atlas entities linked into one project |
| `max_project_auto_promote_preview_matches` | `200` | Server-side only. Maximum matches returned by one auto-promote rule preview. API callers can request fewer matches with `limit`, but not more than this configured cap |
| `max_project_auto_promote_scan_candidates` | `5000` | Server-side only. Maximum Atlas entity candidates scanned for match modes that cannot be fully filtered in SQL, such as CIDR |
| `max_project_auto_promote_apply_matches` | `1000` | Server-side only. Maximum links one manual auto-promote apply can create. API callers can request a smaller apply window with `limit`, but not more than this configured cap |
| `max_project_auto_promote_run_matches` | `100` | Server-side only. Maximum Atlas entity matches one auto-promote rule can apply from a single completed run |
| `max_project_auto_promote_rules_per_run` | `50` | Server-side only. Maximum enabled auto-promote rules evaluated for one completed run |
| `max_project_auto_promote_rules_per_project` | `100` | Server-side only. Maximum auto-promote rules stored for one project. `0` means unlimited |
| `project_auto_promote_preview_rate_limit_per_minute` | `30` | Server-side only. Per-session rate limit for auto-promote preview requests |
| `project_auto_promote_preview_rate_limit_per_second` | `2` | Server-side only. Per-session burst limit for auto-promote preview requests |
| `atlas_import_max_upload_mb` | `10 MB` | Server-side only. Maximum uploaded file size for one Atlas import preview |
| `atlas_import_max_rows` | `5000` | Server-side only. Maximum parsed rows accepted for one Atlas import preview or apply |
| `atlas_import_max_findings` | `5000` | Server-side only. Maximum normalized findings accepted for one Atlas import |
| `atlas_import_max_warnings` | `100` | Server-side only. Maximum row warnings retained while parsing one Atlas import |
| `atlas_import_max_xml_elements` | `100000` | Server-side only. Maximum XML elements streamed by one XML Atlas import parser before rejection |
| `atlas_import_preview_sample_limit` | `20` | Server-side only. Maximum entity and finding sample rows returned in one Atlas import preview response |
| `atlas_import_warning_sample_limit` | `50` | Server-side only. Maximum warning samples returned in one Atlas import preview and stored on draft/batch metadata |
| `atlas_import_draft_ttl_minutes` | `30` | Server-side only. Time window in minutes before an unapplied Atlas import draft is treated as abandoned and cleaned up |
| `max_project_targets_per_project` | `200` | Server-side only. Maximum manual or discovered project targets per project, separate from bulk-linked Atlas entities |
| `max_evidence_packages_per_project` | `25` | Server-side only. Maximum draft evidence package manifests per project |
| `max_entity_labels_per_session` | `5000` | Server-side only. Maximum entity labels one session can create |
| `max_entity_labels_per_entity` | `20` | Server-side only. Maximum labels attached to a single supported entity |
| `max_entity_notes_per_session` | `2000` | Server-side only. Maximum one-note-per-entity records one session can create |
| `max_finding_triage_details_per_owner` | `5000` | Server-side only. Maximum finding remediation/verification detail records one personal session or team owner can create |
| `evidence_package_max_mb` | `25 MB` | Maximum final ZIP size for an evidence package download. The package wizard shows a best-guess ZIP estimate before the archive is built, and the server enforces the actual compressed size before returning the file |
| `evidence_package_max_uncompressed_mb` | `500 MB` | Maximum expanded evidence package content before ZIP compression. This keeps very large transcript or artifact selections bounded even when the final ZIP would compress well |
| `evidence_package_max_artifacts` | `100` | Maximum workspace artifacts included in one evidence package archive. The package wizard also uses this value when presenting archive constraints |
| `package_presets_file` | `package_presets.yaml` | Evidence package preset catalog. Normal relative paths use the shipped root; relative `.local.` filenames use the operator root. The catalog reloads when its readable file changes and falls back to shipped presets after an invalid override |
| `report_templates_file` | `report_templates.yaml` | Engagement report template catalog. Normal relative paths use the shipped root; relative `.local.` filenames use the operator root. The catalog reloads when its readable file changes and falls back to shipped templates after an invalid override |
| `evidence_package_download_rate_limit_per_minute` | `10` | Server-side only. Per-session evidence package download limit per minute |
| `evidence_package_download_rate_limit_per_second` | `2` | Server-side only. Per-session evidence package download burst limit per second |
| `notifications` | see nested defaults | Server-side only. Outbound notification delivery guardrails for do-not-disturb, per-channel send rate, and retry behavior. See [docs/notifications.md](docs/notifications.md) for channel setup |
| `notifications.do_not_disturb` | `false` | Server-side only. Stops outbound notification delivery before channel sends while keeping queued event storage available |
| `notifications.delivery_rate_per_minute` | `10` | Server-side only. Per-channel outbound notification send cap used by the worker claim path |
| `notifications.http_timeout_seconds` | `8` | Server-side only. HTTP timeout for outbound webhook-style notification channel sends |
| `notifications.test_timeout_seconds` | `4` | Server-side only. Shorter timeout used for manual notification test sends |
| `notifications.http_private_host_allowlist` | `[]` | Server-side only. Exact hostnames, IPs, or CIDR ranges that webhook-style channels may post to even when they resolve to private, loopback, link-local, or otherwise non-public addresses |
| `notifications.smtp.host` | _(empty)_ | Server-side only. SMTP relay host required before email notification channels can send |
| `notifications.smtp.port` | `587` | Server-side only. SMTP relay port for email notification channels |
| `notifications.smtp.user` | _(empty)_ | Server-side only. SMTP username for the operator-managed relay |
| `notifications.smtp.password_secret_id` | _(empty)_ | Server-side only. Environment variable name that contains the SMTP password; email channels never store this value |
| `notifications.smtp.from_address` | _(empty)_ | Server-side only. From address used for email notification messages |
| `notifications.smtp.tls` | `starttls` | Server-side only. SMTP TLS mode: `starttls`, `ssl`, or `none` |
| `notifications.retry.max_attempts` | `6` | Server-side only. Maximum delivery attempts before a notification event moves to dead-letter state |
| `notifications.retry.max_age_hours` | `24` | Server-side only. Maximum retry window before a notification event moves to dead-letter state |
| `notifications.retry.base_delay_seconds` | `30` | Server-side only. Base delay for exponential notification retry backoff |
| `notifications.events.retention_days` | `30` | Server-side only. Number of days to keep sent notification delivery audit rows; set to `0` to disable pruning |
| `scheduler` | see nested defaults | Server-side only. Cadence and recovery settings for scheduled runs and watcher-owned schedules. See [docs/schedules.md](docs/schedules.md) for behavior details |
| `scheduler.lock_path` | `APP_DATA_DIR/scheduler.lock` | SQLite scheduler worker lock path. Leave empty to use the app data directory default. Postgres deployments use an advisory lock instead |
| `scheduler.tick_seconds` | `5` | How often the scheduler worker checks for due schedules when no immediate fire is found |
| `scheduler.max_per_session` | `32` | Maximum normal schedules a durable session token can own |
| `scheduler.missed_fire_policy` | `coalesce` | Missed-fire behavior. The worker coalesces recent missed windows into one catch-up fire |
| `scheduler.max_catchup_window_seconds` | `3600` | Maximum age for a missed schedule to receive one catch-up fire on worker startup |
| `scheduler.default_timezone` | `UTC` | Default IANA timezone used when a schedule does not set its own timezone |
| `watchers` | see nested defaults | Server-side only. Change-detection monitor limits. Watchers use scheduler-owned cadence rows and notification triggers |
| `watchers.max_per_session` | `32` | Maximum change-detection watchers a durable session token can own |
| `project_digests` | see nested defaults | Server-side only. Defaults used when a project opts into attack-surface digest notifications |
| `project_digests.default_cadence_preset` | `daily` | Initial digest cadence for project digest settings. Projects can choose `hourly`, `daily`, or `weekly`; unsupported values fall back to `daily` and log a warning |
| `project_digests.first_send_lookback_hours` | `24` | Maximum lookback window used for a project's first digest before it has a successful sent timestamp. Values are clamped between 1 hour and the selected cadence's natural window |
| `cve_risk` | see nested defaults | Server-side public CVE risk data. Release-pinned FIRST EPSS and CISA KEV snapshots work offline; live bulk-feed refresh remains an operator opt-in |
| `cve_risk.bootstrap_enabled` | `true` | Loads the release-pinned EPSS and KEV snapshots when the database has no newer accepted data. Bootstrap import is a silent ranking baseline and does not create risk-escalation events |
| `cve_risk.refresh_enabled` | `false` | Lets the scheduler refresh the public EPSS and KEV bulk feeds. Refreshes send no Project, target, finding, package, or CVE inventory values to either source |
| `cve_risk.refresh_interval_seconds` | `86400` | Minimum interval between refresh attempts for each source, from 300 to 604800 seconds |
| `cve_risk.stale_after_hours` | `48` | Age after which accepted feed data is labeled stale, from 1 to 8760 hours |
| `cve_risk.http_timeout_seconds` | `30` | Per-request timeout for an enabled bulk-feed refresh, from 3 to 120 seconds |
| `cve_risk.max_download_bytes` | `67108864` | Maximum compressed response accepted from one feed refresh, from 1024 to 268435456 bytes |
| `cve_risk.max_attempts` | `3` | Maximum refresh attempts after network or validation failures, from 1 to 5 |
| `cve_risk.lease_seconds` | `300` | Database-backed single-flight lease for one source refresh, from 30 to 3600 seconds |
| `cve_risk.work_batch_size` | `100` | Maximum changed-feed work items claimed in one escalation pass, from 1 to 1000 |
| `cve_risk.owner_batch_size` | `100` | Maximum owner groups processed for one changed CVE before its durable cursor yields, from 1 to 1000 |
| `cve_risk.work_max_attempts` | `5` | Maximum isolated attempts for one failed escalation work item, from 1 to 20 |
| `cve_risk.epss_activation_probability` | `0.10` | EPSS probability that activates one owner-scoped risk event after an upward crossing |
| `cve_risk.epss_reset_probability` | `0.08` | Lower EPSS probability that rearms a later upward event. It must remain below the activation probability |
| `cve_risk.advisory_mode` | `disabled` | Shared NVD advisory storage mode: `disabled`, `local`, or `external`. `external` only retains NVD results from an explicit Atlas CVE **Refresh intel** action; it doesn't start background CVE lookups |
| `cve_risk.nvd_local_path` | empty | Path to an operator-managed NVD 2.0 JSON dataset when `advisory_mode` is `local`. The path is required in local mode |
| `cve_risk.advisory_positive_ttl_seconds` | `604800` | Freshness and cache lifetime for accepted NVD records, from 3600 to 2592000 seconds |
| `cve_risk.advisory_negative_ttl_seconds` | `86400` | Cache lifetime for an explicit NVD lookup with no advisory record, from 300 to 604800 seconds |
| `cve_risk.advisory_cvss_downgrade_delta` | `1.0` | Minimum CVSS score decrease recorded as a material NVD change in Project Monitoring. Values must be greater than 0 and no more than 10 |
| `cve_risk.advisory_max_local_bytes` | `268435456` | Largest local NVD JSON file accepted, from 1024 to 1073741824 bytes |
| `cve_risk.advisory_max_records` | `500000` | Largest number of CVE rows accepted from one local NVD dataset, from 1 to 1000000 |
| `cve_risk.allowed_hosts` | `[epss.cyentia.com, www.cisa.gov]` | Exact HTTPS hostnames allowed for the fixed bulk-feed URLs and redirects. Entries must be hostnames, not URLs |
| `command_timeout_seconds` | `3600` | Auto-kill commands that run longer than this many seconds. `0` means disabled |
| `workflow_active_execution_limit` | `3` | Maximum active workflow executions for one personal session or team owner |
| `workflow_execution_max_runtime_seconds` | `14400` | Maximum total lifetime of one workflow execution. The engine checks this before launching or advancing each step |
| `heartbeat_interval_seconds` | `20` | How often to send an SSE heartbeat on idle connections to prevent proxy timeouts |
| `run_broker_enabled` | `true` | Enables the brokered run model for command start, output replay, and live reattachment |
| `run_broker_require_redis` | `true` | Requires Redis for brokered live reattachment. Keep enabled for Docker/production deployments; set to `false` only for single-worker local development where in-memory replay limitations are acceptable. Multi-worker startup still requires Redis for shared active-run state |
| `run_broker_active_stream_ttl_seconds` | `14400` | Safety TTL for active broker streams, refreshed while a run is active |
| `run_broker_completed_stream_ttl_seconds` | `3600` | How long completed broker streams remain replayable after history finalization before completed-run restore relies on saved history rows and artifacts |
| `run_broker_max_replay_bytes` | `10485760` | Maximum replay payload retained per brokered run stream. Replay is also bounded by `max_output_lines`; there is no separate line-limit setting |
| `run_broker_subscriber_block_seconds` | `15` | How long broker stream subscribers wait for new events before receiving a heartbeat |
| `run_broker_heartbeat_seconds` | `20` | How often broker workers emit heartbeat events while a process is idle |
| `run_broker_owner_stale_seconds` | `75` | How long an owner browser can go without touching a run before ownership is considered stale |
| `interactive_pty_max_runtime_seconds` | `900` | Maximum lifetime for an interactive PTY command before the server terminates it |
| `interactive_pty_max_concurrent_per_session` | `4` | Maximum number of active interactive PTY commands one browser session can run at the same time |
| `interactive_pty_buffer_limit` | `512` | Maximum in-memory PTY events kept per local active run before older live events are dropped from the local fallback buffer |
| `interactive_pty_input_max_bytes` | `4096` | Maximum UTF-8 bytes accepted in one PTY input request before pasted or typed input is truncated |
| `interactive_pty_heartbeat_seconds` | `15` | Idle heartbeat interval for PTY event streams |
| `interactive_pty_control_poll_seconds` | `0.2` | How often the PTY owner checks for queued input and resize events |
| `interactive_pty_stream_fetch_count` | `100` | Maximum Redis PTY stream entries read per fetch while serving a PTY event stream |
| `interactive_pty_stream_maxlen` | `5000` | Approximate maximum Redis PTY output-stream entries retained per active run |
| `interactive_pty_snapshot_publish_bytes` | `8192` | Output-byte threshold that makes the PTY owner refresh the shared terminal snapshot |
| `interactive_pty_snapshot_publish_seconds` | `1` | Maximum interval between shared PTY snapshot refreshes while output continues |
| `interactive_pty_snapshot_min_publish_seconds` | `0.2` | Minimum interval between shared PTY snapshot refreshes, even during heavy output bursts |
| `interactive_pty_snapshot_fallback_entry_limit` | `200` | Maximum plain-text fallback entries returned when an ANSI terminal snapshot is unavailable |
| `welcome_char_ms` | `18` | Base delay between each typed character in the welcome animation, in milliseconds. Lower means faster typing |
| `welcome_jitter_ms` | `12` | Random extra delay added per character, in milliseconds. `0` means perfectly even typing; higher values feel more organic |
| `welcome_post_cmd_ms` | `650` | Pause after a welcome command finishes typing, before the next visual step begins |
| `welcome_inter_block_ms` | `850` | Gap between one sampled welcome command block finishing and the next sampled command starting |
| `welcome_first_prompt_idle_ms` | `1500` | Minimum idle time for the first ready prompt before the featured command starts typing |
| `welcome_post_status_pause_ms` | `500` | Extra pause after the fake startup-status block completes and before the first command prompt appears |
| `welcome_sample_count` | `5` | Number of sampled command examples shown after the ASCII/status intro. `0` disables sampled commands |
| `welcome_status_labels` | `["CONFIG","RUNNER","HISTORY","LIMITS","AUTOCOMPLETE"]` | Labels shown in the fake startup-status block during the welcome animation. Best with 4-6 short labels |
| `welcome_hint_interval_ms` | `4200` | Delay between footer-hint rotations while the welcome tab remains idle |
| `welcome_hint_rotations` | `0` | Maximum number of hint states shown while the welcome tab remains idle. `0` keeps rotating until interrupted; `1` keeps only the first hint visible |
| `tour_enabled` | `true` | Enables the app tour entry points. When disabled, the welcome tour prompt, visual tour links, and `tour` built-in command are hidden |
| `log_level` | `INFO` | Log verbosity. Options: `ERROR`, `WARN`, `INFO`, `DEBUG` |
| `log_format` | `text` | Log output format. Options: `text` for human-readable logs or `gelf` for GELF 1.1 JSON |

Release images include dated FIRST EPSS and CISA KEV snapshots, so saved CVE findings can be ranked without network access. Run `providers` to see each snapshot's source, version, age, and whether live refresh is enabled. When `cve_risk.refresh_enabled` is `true`, the scheduler downloads only the fixed public bulk feeds over allowlisted HTTPS; Python's standard `HTTPS_PROXY` and `NO_PROXY` settings still apply. A rejected, oversized, malformed, or failed download leaves the last accepted snapshot in place.

NVD advisory storage is separate from the EPSS/KEV bulk-feed switch. Use `advisory_mode: local` with `nvd_local_path` to load a bounded NVD 2.0 JSON dataset during startup, or use `advisory_mode: external` to retain the normalized result only when a user with finding-triage permission explicitly refreshes a saved CVE in Atlas. The external mode doesn't create a scheduler job or send scan-derived products, packages, targets, or findings to NVD. A failed local reload keeps the last accepted dataset and reports the failure through `providers`, logs, and metrics. Later accepted data records withdrawal, rejection, dispute, reinstatement, and CVSS decreases of at least `advisory_cvss_downgrade_delta` for linked findings; the first accepted record is a silent baseline. `disabled` keeps shared NVD CVSS storage off; the existing explicit `intel cve` provider lookup remains available under its own cache and rate limits.

See [Logging Reference](docs/logging.md) for level semantics, event names, fields, redaction rules, formats, and troubleshooting.

---

## Files Under app/conf

| Path | Purpose |
|------|---------|
| `app/conf/config.yaml` | Main application settings |
| `app/conf/commands.yaml` | Command registry for catalog grouping, autocomplete, allow/deny policy, runtime adaptations, encrypted secret requirements, workspace flags, and smoke-test examples |
| `app/conf/faq.yaml` | Operator FAQ entries appended to the built-in, section-grouped FAQ |
| `app/conf/welcome.yaml` | Welcome command samples and featured sample metadata |
| `app/conf/tour.yaml` | Versioned onboarding tour chapters shared by the `tour` command and visual tour |
| `app/conf/ascii.txt` | Desktop welcome banner art |
| `app/conf/ascii_mobile.txt` | Mobile welcome banner art |
| `app/conf/app_hints.txt` | Desktop rotating welcome hints |
| `app/conf/app_hints_mobile.txt` | Mobile rotating welcome hints |
| `app/conf/wordlists.yaml` | Curated SecLists categories for the `wordlist` command and autocomplete |
| `app/conf/workflows.yaml` | Operator-configured guided workflows shown in the Workflows panel after built-in workflow entries |
| `app/conf/themes/` | Named theme variants used by the shell, permalink pages, diagnostics, and HTML export |
| `app/conf/theme_dark.yaml.example` | Generated dark-theme reference template |
| `app/conf/theme_light.yaml.example` | Generated light-theme reference template |

Theme authoring details live in [THEME.md](THEME.md). Command integration details live in [docs/external-command-integrations.md](docs/external-command-integrations.md).

---

## Onboarding Tour

`app/conf/tour.yaml` stores the shared content for the app tour. Each file has a positive integer `version` and a `chapters` list. Bump `version` when the tour meaningfully changes so the welcome prompt can point returning users at the refreshed tour.

Each chapter supports:

- `id` - stable chapter identifier used by both renderers
- `title` - short display title
- `summary` - end-user copy for the chapter
- `sample` - optional command-chip value for the terminal `tour` command; terminal samples open in a new tab, while the visual tour may replace this with an app action such as opening History, Workflows, Projects, Teams, Files, Options, or FAQ
- `illustration` - optional key for the visual tour renderer
- `requires` - optional exact config key such as `workspace_enabled` or `interactive_pty_enabled`; chapters are hidden when that feature is disabled

The `tour_enabled` setting in `config.yaml` is the kill-switch for tour entry points. Keep `tour.yaml` focused on chapter content.

---

## Command Registry Autocomplete

`app/conf/commands.yaml` stores each external command under `commands`, with policy, help flags, runtime adaptations, encrypted secret requirements, workspace file flags, descriptive knowledge guidance, and root-aware flag, argument, subcommand, and example hints. Optional local additions can live in `app/conf/commands.local.yaml`. A local entry with a new `root` adds a new command; a local entry with an existing `root` merges into the base command entry instead of replacing it wholesale.

```yaml
commands:
  - root: nmap
    category: Port & Service Scanning
    policy:
      allow:
        - nmap
      deny:
        - nmap --privileged
    help:
      flags:
        - -h
        - --help
    runtime_adaptations:
      inject_flags:
        - flags: [-sT]
          position: prepend
          unless_any_regex: ["^-s[AFILMNOSTUWXYZn]"]
    requires_secrets:
      - env: EXAMPLE_API_KEY
        optional: true
      - env: VT_API_KEY
        inject_env: VTCLI_APIKEY
        fallback_envs:
          - VTCLI_APIKEY
    autocomplete:
      examples:
        - value: nmap -h
          description: Show help and usage
          smoke:
            profile: unauthenticated
      flags:
        - value: -sV
          description: Service/version detection
```

`help.flags` marks invocations whose output should stay visible but should not create findings or Atlas entities. Help invocations also bypass required-secret preflight for that command root, so users can run safe `--help` commands before configuring provider keys. An example can opt into the default container smoke corpus with `smoke.profile: unauthenticated` when it is safe to run without provider credentials or workspace setup. Use `smoke.profile: manual` for useful examples that should stay visible to users but are too network-dependent, noisy, or data-sensitive for the default smoke corpus.

`requires_secrets` names encrypted secrets from the active personal or team scope that should be passed to the subprocess environment for that command root. Required missing secrets or a missing session identity block launch before the process starts. Optional missing secrets log a warning and let the command run without that env var; `ipinfo` uses this for `IPINFO_TOKEN` and `wpscan` uses it for `WPSCAN_API_TOKEN` because both tools can still run without a token. Secret values are never rendered into command text. `inject_env` lets a registry entry store a friendly app secret name while exporting the vendor-required env var to the subprocess. `fallback_envs` lets users store an accepted native name instead; the VirusTotal CLI entry accepts either `VT_API_KEY` or `VTCLI_APIKEY` and always launches `vt` with `VTCLI_APIKEY`. `subcommands` limits a declaration to named modes under the same root; TruffleHog uses it to inject `GITHUB_TOKEN` only for `github` and `GITLAB_TOKEN` only for `gitlab`. The urlscan and Chaos CLI wrappers use `URLSCAN_API_KEY` and `PDCP_API_KEY` from the same vault path. Interactive PTY commands can't declare `requires_secrets`; the registry rejects that combination because the PTY path doesn't inject secret env vars.

Users manage matching values from **Options → Secrets** or with `secret set NAME` in the terminal. The browser prompt collects the value; the terminal command line contains only the secret name. Stored values are replace-only: list routes and the Options panel return names, consumer env bindings, and update times, never the saved value. A consumer env name can belong to only one secret in the current personal or team scope, so a command that asks for `SHODAN_API_KEY` can't receive an arbitrary matching row. Personal secrets are not inherited by team scope; team owners and admins create shared team secrets explicitly.

Inside each command's `autocomplete` block, a root can define:

```yaml
argument_limit: 1
arguments:
  - value: https://
    description: Start an HTTP or HTTPS URL
  - placeholder: <url>
    position: 1
    value_type: url
    description: Target URL to request
```

How the keys work:

- `argument_limit`
  - optional cap on how many positional arguments should keep receiving autocomplete hints
  - once that many positional arguments are already filled, positional hints stop, but flags and other non-positional suggestions can still appear
- `examples`
  - complete command examples shown while a root command or unique subcommand prefix is being typed
  - root examples and scoped subcommand examples are flattened only for the root-typing discovery view; they stay separate in the schema so subcommand-specific matching remains clean
  - when an example is accepted, it replaces the typed command prefix rather than only the active token
  - `interactive: true` hides an example unless `interactive_pty_enabled` is enabled; use this for examples that include the command's configured interactive trigger flag
- `flags`
  - suggestions shown when the current token is a flag position for that command root, for example `nmap -`
  - each flag can carry its own next-token behavior:
    - `takes_value: true` means the next token is a value slot for that flag
    - `value_hint` adds display-only guidance for that value slot
    - `suggest` adds concrete insertable examples for that value slot
    - `closes: true` suppresses further autocomplete after that token is accepted
    - `feature_required: workspace` hides workspace-only flags, examples, and value suggestions unless Files are enabled
    - `feature_required: raw_packet_scanning` hides Nmap raw-mode suggestions unless the operator opt-in and Nmap runtime readiness checks are both active; tool-specific gates such as `raw_packet_scanning_masscan` use that scanner's readiness
- `arguments`
  - unflagged argument slots like `<target>`, `<url>`, `<domain>`, or `<port>`
  - these appear both at `command ` and while the user types the argument value
  - use `placeholder` for display guidance and `value` for text the user can insert
  - use 1-based `position` when a command has ordered operands so autocomplete only shows the current slot
  - unpositioned argument hints keep the legacy behavior and can appear in any positional slot; when mixed with positioned hints, they remain general guidance alongside the slot-specific hints
- `subcommands`
  - command trees such as `gobuster dir`, `gobuster vhost`, or other external-tool subcommands
  - each subcommand can also use `takes_value`, `value_hint`, `suggest`, `insert`, and `closes`
  - for tools where each subcommand has its own flags and examples, use a mapping of subcommand names to scoped autocomplete blocks
  - nested examples appear during root discovery and while typing a unique matching subcommand prefix; nested flags appear after the subcommand has been selected
- `pipe_helpers`
  - top-level registry entries for helpers that appear after `command |`
  - each helper has its own `autocomplete.pipe.enabled`, flags, arguments, and optional insert/display metadata

### Command Knowledge

A command root can carry an optional `knowledge` block — operator guidance shown in `commands info <root>`, `commands search`, and the Command Registry modal. It is a sibling of `autocomplete`, not nested inside it:

```yaml
commands:
  - root: nmap
    category: Port & Service Scanning
    knowledge:
      notes:
        - Uses TCP connect scans by default; operators can opt in to capability-backed SYN and raw scan modes.
      gotchas:
        - Raw scan modes require operator opt-in and passing runtime capability checks; --privileged stays app-managed.
      safe_defaults:
        - Use -sT for connect scans and add -Pn to skip host discovery on filtered hosts.
      common_flags:
        - "-sT — TCP connect scan"
        - "-sV — service/version detection"
      artifact_behavior: With Files enabled, -oN/-oX/-oG write report files into the session workspace; raw output paths are otherwise denied.
```

How the fields work:

- `notes`, `gotchas`, `safe_defaults`, `common_flags`
  - list fields, each holding short free-text strings
  - normalized on load: stripped, de-duplicated, empties dropped, capped at five items, each truncated to 200 characters
- `artifact_behavior`
  - a single short scalar string describing where the tool writes output, truncated to 200 characters
- all `knowledge` fields are descriptive only and never affect allow/deny policy, validation, or execution
- in a `commands.local.yaml` overlay, scalar fields replace the base value and list fields extend the base list with de-duplication
- unknown keys inside `knowledge` are ignored on load and reported only by the registry lint helper, so an overlay typo never hard-fails the registry

More examples:

```yaml
commands:
  - root: curl
    category: HTTP & Web
    policy:
      allow:
        - curl
      deny:
        - curl -K
    autocomplete:
      flags:
        - value: -H
          description: Add request header
          takes_value: true
          suggest:
            - value: "Authorization: Bearer <token>"
              description: Example auth header
        - value: -o
          description: Write body to file
          takes_value: true
          suggest:
            - value: /dev/null
              description: Discard body and keep metadata
      arguments:
        - value: https://
          description: Start an HTTP or HTTPS URL
        - placeholder: <url>
          position: 1
          value_type: url
          description: Target URL to request
```

That means:

- `curl -` suggests curl flags
- `curl -H <cursor>` suggests header values
- `curl -o <cursor>` suggests file/value targets like `/dev/null`
- `curl <cursor>` can show both a starter value like `https://` and a persistent `<url>` hint

For commands where positional operands have a strict order, assign each slot a 1-based `position`:

```yaml
commands:
  - root: tcptraceroute
    autocomplete:
      arguments:
        - placeholder: <host>
          position: 1
          hint_only: true
          value_type: domain
          description: Hostname or IP to trace
        - placeholder: <port>
          position: 2
          hint_only: true
          value_type: port_set
          description: TCP port to probe
```

That means:

- `tcptraceroute <cursor>` shows `<host>` guidance, plus any root flags
- `tcptraceroute darklab.sh <cursor>` shows `<port>` guidance instead of repeating `<host>`
- while typing either operand, autocomplete keeps only the hint for that argument slot visible

Interactive PTY examples can be gated separately from the command's normal examples:

```yaml
examples:
  - value: telnet --interactive darklab.sh 443
    description: Connect to a service port through the PTY view
    interactive: true
```

Use `closes: true` for flags or subcommands that should suppress the dropdown after they are typed. This is used for help flags, version flags, and exclusive subcommands that end the command:

```yaml
nmap:
  flags:
    - value: -h
      description: Show help
      closes: true
    - value: -p
      description: Port list
      takes_value: true
      suggest:
        - value: "80,443"
          description: Common web ports

session-token:
  subcommands:
    - value: set
      description: Activate an existing session token
      takes_value: true
      value_hint:
        placeholder: "<token>"
        description: Paste a tok_... token or UUID from another device
    - value: generate
      description: Generate a new session token
      closes: true
    - value: clear
      description: Remove the active session token after confirmation
      closes: true
```

For external tools with richer subcommands, prefer subcommand-scoped blocks. Root flags stay global, root and nested examples are visible during root discovery, and the selected subcommand contributes its own scoped flags, examples, value hints, and positional argument hints:

```yaml
amass:
  flags:
    - value: -h
      description: Show help
      closes: true
  subcommands:
    enum:
      description: Enumerate discovered assets
      examples:
        - value: amass enum -d darklab.sh
          description: Enumerate a root domain
      flags:
        - value: -d
          description: Domain to enumerate
          takes_value: true
          value_hint:
            placeholder: <domain>
            description: Root domain
        - value: -timeout
          description: Minutes to run without progress before terminating
          takes_value: true
          suggest:
            - value: "10"
              description: Ten-minute timeout
    subs:
      description: Print subdomains from the Amass database
      examples:
        - value: amass subs -d darklab.sh -names
          description: Print discovered names
      flags:
        - value: -names
          description: Print discovered names
        - value: -ip
          description: Include IP addresses when used with -names
```

Practical authoring guidance:

- use nested `flags`, `arguments`, and `subcommands` when the next useful suggestion depends on the command root or the preceding flag/subcommand
- use `argument_limit` for commands such as `man`, `which`, or `type` where the shell should stop suggesting additional positional operands after one topic/command has already been provided
- group related behavior together: root `examples` for broadly useful top-level invocations, subcommand `examples` for complete mode-specific invocations, flag value hints under the flag, and subcommand-specific flags under `subcommands`
- use `arguments` for unflagged inputs like hosts, URLs, domains, files, or CIDR targets
- use `position` on multi-operand commands such as `tcptraceroute <host> <port>` or `telnet --interactive <host> <port>` so each placeholder appears only when that argument is next
- use `interactive: true` on examples that should only appear when the instance has Interactive PTY enabled
- add value-type metadata such as `domain`, `host`, `target`, `ip`, `url`, or `port_set` to flag or positional value slots that should capture and suggest recent targets
- add `value_type: workspace_path` to workspace-required file/folder slots that should be replaced with live session workspace suggestions without being treated as scan targets
- use `placeholder: "<...>"` when the hint is explanatory and should persist while typing
- use `value: "..."` when the suggestion should be inserted and prefix-filtered normally
- use `pipe_helpers` entries with `autocomplete.pipe.enabled: true` when a helper should appear after `command |`

The shipped file is intentionally small and focused. Add entries only for commands where token-aware guidance is clearly more useful than the flat whole-command list.

For built-in pipe support, the same file can describe the narrow pipe stage:

```yaml
grep:
  pipe:
    enabled: true
    description: Filter lines by pattern
  flags:
    - value: -i
      description: Ignore case
    - value: -v
      description: Invert match
    - value: -E
      description: Extended regex

wc:
  pipe:
    enabled: true
    insert: "wc -l"
    label: "wc -l"
    description: Count lines
```

That means:

- `help | ` can suggest `grep`, `head`, `tail`, and `wc -l`
- `help | grep -` can suggest `-i`, `-v`, and `-E`
- `help | head -n ` or `help | tail -n ` can suggest common count values
- `help | wc ` can suggest `-l`

To update suggestions, edit `conf/commands.yaml` and/or `conf/commands.local.yaml`, then reload the page. No server restart is needed for autocomplete changes.

---

## Environment Variables and .env

The production installer creates `.env` and installs a matching `.env.example` you can review when a later release adds settings. The source repository keeps a separate development [`.env.example`](.env.example); copy it before starting `compose.dev.yaml` when you want development overrides:

```bash
cp .env.example .env
```

```env
# APP_PORT=8888
# DEV_HOST_BIND_ADDRESS=127.0.0.1
# WORKSPACE_ENABLED=false
# WORKSPACE_BACKEND=tmpfs
# WORKSPACE_ROOT=/tmp/darklab_shell-workspaces
# INTERACTIVE_PTY_ENABLED=false
# RESTRICTED_COMMAND_INPUT_CIDRS=169.254.169.254/32,10.0.0.0/8
# RAW_PACKET_SCANNING_ENABLED=false
# WEB_CONCURRENCY=4
# WEB_THREADS=4
# PROMETHEUS_MULTIPROC_DIR=/tmp/darklab_shell-prom
# NOTIFICATION_WORKER_ENABLED=1
# SCHEDULER_ENABLED=1

# Optional AI assists and bundled llama.cpp model settings.
# Disabled until AI features are enabled.
# If you also use Postgres, include it in COMPOSE_PROFILES, for example:
# COMPOSE_PROFILES=llama,postgres
# AI_WORKER_ENABLED=0
# AI_ENABLED=false
# AI_BASE_URL=http://llama:8080
# AI_MODEL=Llama-3.1-8B-Instruct
# AI_TIMEOUT_SECONDS=120
# AI_MAX_OUTPUT_TOKENS=120
# AI_NEXT_COMMANDS_MAX_OUTPUT_TOKENS=180
# AI_MAX_CONCURRENT=1
# AI_MAX_QUEUE_DEPTH=20
# AI_RATE_LIMIT_PER_SESSION_HOUR=5
# AI_RATE_LIMIT_GLOBAL_PER_MINUTE=2
# AI_FEATURE_SUMMARY=false
# AI_FEATURE_NEXT_COMMANDS=false
# AI_FEATURE_RUN_SUGGESTIONS=false
# LLAMA_HF_MODEL=bartowski/Meta-Llama-3.1-8B-Instruct-GGUF:Q4_K_M
# LLAMA_THREADS=8
# LLAMA_CTX_SIZE=2048
# LLAMA_N_PREDICT=180
# LLAMA_PARALLEL=1

# Optional Postgres backend settings. SQLite remains the default; uncomment
# these when you want Compose to start Postgres and the app to use it. Add
# postgres to COMPOSE_PROFILES above when enabling the bundled Postgres service.
# DATABASE_BACKEND=postgres
# DATABASE_URL=
# DATABASE_POOL_MIN=1
# DATABASE_POOL_MAX=5
# DATABASE_POSTGRES_JIT=false
# POSTGRES_DB=darklab_shell
# POSTGRES_USER=darklab
# POSTGRES_PASSWORD=
# SECRETS_MASTER_KEY=
```

For AI assists in Compose, `AI_ENABLED=true` turns on the app-side AI routes and diagnostics state, while `AI_WORKER_ENABLED=1` starts the worker process that drains queued provider calls. The summary and next-command feature flags control which Run Details cards appear. Without the worker, new assists can be queued but won't complete until a worker is running.

| Variable | Used by | Purpose |
|----------|---------|---------|
| `APP_PORT` | Docker Compose, Dockerfile/entrypoint healthcheck path | App port exposed by the container and published by the base Compose file |
| `HOST_BIND_ADDRESS` | Production Compose | Host address used for the published app port. The public stack defaults to `0.0.0.0` so remote hosts can connect. Use `127.0.0.1` when only a local reverse proxy should reach the app |
| `DARKLAB_IMAGE` | Production Compose | Exact Docker Hub image tag to run. Keep this on a reviewed semantic-version tag rather than `latest` |
| `APP_LOCAL_CONF_DIR` | Flask app | Optional operator root for every supported local overlay. Production sets `/config`; when unset, loaders keep using sibling files beside their shipped assets |
| `WORKSPACE_ENABLED` | Docker Compose, Flask app | Enables or disables personal and team Files |
| `WORKSPACE_BACKEND` | Docker Compose, Flask app | Selects `tmpfs` for short-lived Files or `volume` for persistent mounted storage |
| `WORKSPACE_ROOT` | Docker entrypoint, Docker Compose, Flask app | Path prepared by the container before dropping privileges and used by the app for personal and team Files |
| `INTERACTIVE_PTY_ENABLED` | Docker Compose, Flask app | Enables guarded terminal sessions for approved interactive tools; detailed PTY limits remain in YAML |
| `RESTRICTED_COMMAND_INPUT_CIDRS` | Docker entrypoint, Compose environment, Flask app | Optional comma-separated CIDRs that user-submitted scanner commands cannot target. The same value drives app validation and scanner-user OUTPUT deny rules |
| `RAW_PACKET_SCANNING_ENABLED` | Docker Compose, Flask app | Opts approved scanners into capability-backed SYN/raw modes. Readiness still requires Linux, `CAP_NET_RAW` in the container bounding set, scanner file capabilities, and an executable policy that permits them |
| `WEB_CONCURRENCY` | Gunicorn entrypoint | Number of Gunicorn worker processes |
| `WEB_THREADS` | Gunicorn entrypoint | Number of threads per Gunicorn worker |
| `NOTIFICATION_WORKER_ENABLED` | Docker entrypoint | Starts the outbound notification worker beside Gunicorn when set to `1` or left unset. Set to `0` to run only the web process |
| `SCHEDULER_ENABLED` | Docker entrypoint | Starts the scheduled-run worker beside Gunicorn when set to `1` or left unset. Set to `0` to run only the web process |
| `PROMETHEUS_MULTIPROC_DIR` | Docker Compose, Flask app, Prometheus client | Scratch directory created and exported for `prometheus_client` multiprocess metrics |
| `COMPOSE_PROFILES` | Docker Compose | Optional comma-separated Compose profiles to enable. Set to `llama`, `postgres`, or a comma-separated combination such as `llama,postgres` when you want profile-gated services included without passing `--profile` |
| `AI_WORKER_ENABLED` | Docker entrypoint | Starts the AI worker beside Gunicorn when set to `1`. Leave it `0` when AI is disabled or when another process is responsible for draining the AI queue |
| `AI_ENABLED` / `AI_PROVIDER` / `AI_BASE_URL` / `AI_MODEL` | Docker Compose, Flask app | Core AI provider settings. `AI_ENABLED` permits AI routes and diagnostics; `AI_PROVIDER` is currently `openai_compatible`; `AI_BASE_URL` points at the provider; `AI_MODEL` is sent to chat completions and checked by `/diag` |
| `AI_API_KEY_SECRET_NAME` / `AI_API_KEY` | Flask app | Optional AI provider credentials. The secret-name value reads from the encrypted personal or team vault for the queued request scope; `AI_API_KEY` is the process/config fallback. Local unauthenticated providers usually leave both empty |
| `AI_CONNECT_TIMEOUT_SECONDS` / `AI_TIMEOUT_SECONDS` | Flask app | Optional environment overrides for the YAML provider connect and read timeouts |
| `AI_MAX_INPUT_CHARS` / `AI_MAX_OUTPUT_TOKENS` / `AI_NEXT_COMMANDS_MAX_OUTPUT_TOKENS` | Flask app | Optional environment overrides for the YAML prompt input and provider output caps |
| `AI_MAX_CONCURRENT` / `AI_MAX_QUEUE_DEPTH` | Flask app | Optional environment overrides for YAML worker concurrency and queue limits |
| `AI_RATE_LIMIT_PER_SESSION_HOUR` / `AI_RATE_LIMIT_GLOBAL_PER_MINUTE` | Flask app | Optional environment overrides for YAML Redis-backed AI assist write limits |
| `AI_ALLOW_FULL_OUTPUT` | Flask app | Optional environment override for the YAML full-output context setting |
| `AI_REQUIRE_PRIVATE_BASE_URL` / `AI_BASE_URL_ALLOWED_CIDRS` | Flask app | Optional environment overrides for the YAML provider network guard |
| `AI_PROMPT_VERSION_OVERRIDE` | Flask app | Optional environment override for the YAML staging prompt version |
| `AI_FEATURE_SUMMARY` / `AI_FEATURE_NEXT_COMMANDS` / `AI_FEATURE_RUN_SUGGESTIONS` | Docker Compose, Flask app | AI UI feature flags for summaries, next-command drafts, and opt-in Run buttons for accepted suggestions |
| `LLAMA_HF_MODEL` | Docker Compose | Hugging Face GGUF repo and quantization passed to the optional llama.cpp sidecar |
| `LLAMA_THREADS` / `LLAMA_CTX_SIZE` / `LLAMA_N_PREDICT` / `LLAMA_PARALLEL` | Docker Compose | Runtime sizing for the optional llama.cpp sidecar. These map to llama-server thread count, context size, max generated tokens, and parallel slot count. The bundled default keeps `LLAMA_PARALLEL=1` so serialized AI worker requests reuse one slot more predictably |
| `DATABASE_BACKEND` | Docker Compose, Flask app, lifecycle commands | Selects `sqlite` or `postgres` for the whole deployment |
| `DATABASE_URL` | Docker Compose, Flask app, lifecycle commands | Postgres DSN used when `DATABASE_BACKEND=postgres` |
| `DATABASE_POOL_MIN` / `DATABASE_POOL_MAX` | Flask app | Optional environment overrides for YAML Postgres connection-pool bounds |
| `DATABASE_POSTGRES_JIT` | Flask app | Optional environment override for the YAML Postgres JIT setting |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Docker Compose | Credentials used by the optional `postgres` Compose profile |
| `SECRETS_MASTER_KEY` | Flask app | Optional base64-encoded 32-byte master key for the encrypted personal/team secrets vault. When unset, the app creates `<data_dir>/.secrets_master_key` with mode `0600` on first use and repairs broader existing key-file permissions to `0600` before use. If both env and file exist, the env value wins and the app logs `MASTER_KEY_FILE_IGNORED` |

If `WEB_CONCURRENCY` and `WEB_THREADS` are unset, the entrypoint defaults remain `4` workers and `4` threads. The production stack keeps those defaults unless `.env` changes them. Any value above `1` requires a reachable Redis instance at startup; without Redis, set `WEB_CONCURRENCY=1` for local single-worker fallback mode.

The optional database and AI tuning variables are escape hatches for process-managed deployments. Leave them unset in the shipped Compose stacks to use `config.local.yaml`; their Compose entries intentionally pass empty values, which the app ignores.

---

## Raw-Packet Scanning

Raw-packet scanning is off by default. To enable it in the bundled Compose deployment, set this in `.env` and recreate the shell container:

```env
RAW_PACKET_SCANNING_ENABLED=true
```

```bash
docker compose up -d --force-recreate shell
```

The app checks the Linux capability bounding set, `no-new-privileges`, and each approved scanner binary's effective/permitted `CAP_NET_RAW` file capability before activating raw mode. `CONFIG_LOADED` reports aggregate and per-tool readiness, and an explicit opt-in that can't activate emits `RAW_PACKET_SCANNING_UNAVAILABLE` at WARN. `/diag` reports configured, available, and active states plus the failed prerequisite category. A failed scanner readiness check does not stop the app: Nmap and Naabu keep their connect-mode paths, while raw-only Masscan returns a short readiness error.

When ready, Nmap receives `NMAP_PRIVILEGED=1` from the app's trusted runtime adaptation. This tells Nmap to use the capability already attached to its binary; it does not grant Docker privileged mode. The app does not set `privileged: true`, run commands as root, use host networking, or require Macvlan/IPvlan. User-supplied Nmap `--privileged`, source/decoy/MAC spoofing, and link-layer `--send-eth` remain blocked.

The scanner-user firewall blocks the app port only for destinations local to the container, so a remote authorized host can still be scanned on the same port. At startup, the entrypoint normalizes `RESTRICTED_COMMAND_INPUT_CIDRS` through the app config loader. Every corresponding OUTPUT rule must install or the container stops. A root-owned marker records the installed list, and raw Nmap remains inactive unless it matches; active Nmap adds `--send-ip`. Naabu and Masscan can use packet sockets that do not share that path, so their raw modes stay unavailable whenever restricted CIDRs are configured. There is no setting that treats separate host or Docker bridge firewall rules as readiness proof.

To verify the setup against a system you are authorized to scan, run an explicit SYN scan in the browser and check for a SYN/ACK reason:

```text
nmap -sS -Pn -p 80 --reason <authorized-target>
```

An explicit `nmap -sT ...` remains a connect scan even when raw mode is active.

---

## Database Backend Selection

SQLite is the default database backend and remains the recommended local/single-user path. Postgres is the production-scaling path for heavier deployments.

The app reads the shipped `app/conf/config.yaml`, then the active local `config.local.yaml`, then environment variables. Production gets that local file from installed `conf/config.local.yaml`; source development uses `app/conf/config.local.yaml`. Environment variables win. In Docker Compose environments, prefer `.env` for backend selection because Compose uses the same file to decide which services to start.

For a Compose-managed Postgres deployment, set these values in `.env`:

```env
COMPOSE_PROFILES=postgres
DATABASE_BACKEND=postgres
POSTGRES_PASSWORD=<redacted>
DATABASE_URL=postgresql://darklab:<redacted>@postgres:5432/darklab_shell
```

`COMPOSE_PROFILES=postgres` enables the profile-gated Postgres 18 service without passing `--profile postgres` on every command. `DATABASE_BACKEND` and `DATABASE_URL` select and connect the app backend. `POSTGRES_PASSWORD` is read by the Postgres container at database initialization time. Tune pool bounds and JIT in `conf/config.local.yaml`; the matching environment variables remain available for process-managed deployments but are blank by default in Compose.

For the bundled llama.cpp server, include the `llama` profile:

```env
COMPOSE_PROFILES=llama
AI_ENABLED=true
AI_WORKER_ENABLED=1
AI_BASE_URL=http://llama:8080
AI_MODEL=Llama-3.1-8B-Instruct
AI_FEATURE_SUMMARY=true
AI_FEATURE_NEXT_COMMANDS=true
AI_FEATURE_RUN_SUGGESTIONS=false
LLAMA_HF_MODEL=bartowski/Meta-Llama-3.1-8B-Instruct-GGUF:Q4_K_M
LLAMA_THREADS=8
LLAMA_CTX_SIZE=2048
LLAMA_N_PREDICT=180
LLAMA_PARALLEL=1
```

The llama.cpp sidecar serves the same OpenAI-compatible chat endpoint the app already uses, so `AI_PROVIDER` can stay at `openai_compatible`. The first startup downloads the configured GGUF into the `llama-cache` volume mounted at `/root/.cache`, which preserves both Hugging Face model downloads and llama.cpp cache files across container recreations. Compose passes `AI_MODEL` to `llama-server` as the model alias so `/diag` can match the configured model against `/v1/models`. The bundled profile defaults `LLAMA_PARALLEL=1` because the app already serializes local AI provider calls; using one llama-server slot makes prompt-prefix reuse more predictable on CPU-only hosts. The Compose service does not enable `llama-server --mlock` by default because memory locking depends on host and Docker runtime limits and can make the local sidecar fail to start. If your host is tuned for memory locking and you want that optimization, add `IPC_LOCK`, a `memlock` ulimit, and `--mlock` in a local Compose override. The sidecar healthcheck probes `/v1/models`, and the app container waits for that healthcheck when the `llama` profile is enabled.

The base Compose file defaults `AI_BASE_URL` to `http://llama:8080` and `AI_MODEL` to `Llama-3.1-8B-Instruct`, so those two lines can stay commented in `.env` when you use the bundled llama.cpp sidecar.

Tune AI timeouts, prompt/output caps, queue limits, rate limits, and provider network policy in `conf/config.local.yaml`:

```yaml
ai_timeout_seconds: 120
ai_max_output_tokens: 120
ai_next_commands_max_output_tokens: 180
```

If you use `compose.operator.yaml` for bind-mounted workspaces, make sure it preserves the base service environment or repeats the database environment values; otherwise the container can start with the profile-gated Postgres service present while the app still sees the SQLite defaults.

Postgres connection notes:

- Keep `DATABASE_URL` aligned with any `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB` overrides.
- URL-encode special characters in the password before putting it in `DATABASE_URL`.
- App Postgres connections disable JIT by default because the UI favors predictable low-latency page requests over long analytical queries. Set `database_postgres_jit: true` in `conf/config.local.yaml` only after measuring that your workload benefits from it.
- If `POSTGRES_PASSWORD` changes after the `postgres-data` volume already exists, Postgres does not automatically change the existing role password. Managed SQLite migration and fresh-host backend adoption inspect the cluster over its local container socket before network authentication: they synchronize the configured password only when the destination has no user tables, and refuse to touch a non-empty retained volume. Other Postgres deployments need a deliberate role-password change or volume replacement.
- Keep the same `SECRETS_MASTER_KEY` or copied app-owned key file when migrating encrypted secrets.

For an existing production SQLite install, run `./darklab-deploy migrate-to-postgres` from the installation directory as the user who owns the deployment. Don't use `sudo`: the command uses Docker to read the app-owned SQLite file from the managed `/data` mount, while keeping `.env` and other operator files owned by the deployment user. It creates a verified backup, requires an empty bundled Postgres destination, synchronizes an empty retained cluster with the current installer-generated password, copies and validates the stopped SQLite database, updates the managed environment, and recreates the app on bundled Postgres. A named `postgres-data` volume survives `docker compose down` and deletion of the installation directory; if that retained volume contains user tables, migration refuses to overwrite it and tells you it isn't an empty target. Development checkouts and custom Postgres targets can use the direct helper described in [docs/postgres-migration.md](docs/postgres-migration.md).

Back up the SQLite data directory before migration and keep that snapshot until the Postgres deployment has been validated under real use. Rollback is switching the app config back to SQLite and restoring the untouched data directory snapshot if anything looks wrong after cutover.

For backend development, Postgres tests are opt-in:

```bash
npm run test:postgres
```

By default, the helper uses `DARKLAB_TEST_POSTGRES_DSN` when it is set. When it is not set, it starts a disposable Docker Postgres container on a random localhost port, exports the DSN for the test process, waits for readiness, and removes the container whether the tests pass or fail.

Use `bash scripts/run_postgres_tests.sh --host` when you specifically want to require an existing host-accessible DSN, or pass `--postgres-dsn` when you call pytest directly. To test against the bundled profile-gated Postgres service without publishing port `5432` to the host, run:

```bash
bash scripts/run_postgres_tests.sh --compose
```

The Postgres test lane creates isolated schemas and keeps normal local development SQLite-only unless a test DSN is explicitly set.

---

## Supported Runtimes

This is the canonical current support matrix. The README keeps short prerequisites where operators need them, while feature and architecture docs link here or explain their own user and design context. Changelog entries record the support statement for a specific release and are not a second current-state matrix.

| Runtime surface | Current support |
|-----------------|-----------------|
| Production operating system | Linux |
| Production architecture | AMD64 (`linux/amd64`) and ARM64 (`linux/arm64`) |
| Container orchestration | Docker Compose 2.20.0 or newer |
| Native ARM64 | Supported with the standard Linux Docker Compose deployment |
| SELinux-enforcing Docker | AMD64 compatibility lane; not part of the standard support matrix |
| Rootless Podman | AMD64 compatibility lane; not part of the standard support matrix |
| Other Podman deployments | Best effort |

The production Compose file leaves platform selection to the release image index, so Docker pulls the native AMD64 or ARM64 child from the same version tag. The installer enforces the minimum Compose version before it writes a deployment, and `verify-release-image.sh` rejects unsupported hosts before startup. SELinux and rootless Podman still need host- or runtime-specific setup, and their protected compatibility lanes currently exercise the AMD64 child only.

---

## Docker Compose Files

The production [deploy/compose.yaml](deploy/compose.yaml) pulls `docker.io/darklabsh/darklab-shell:2.8.3` and lets Docker select its native Linux AMD64 or ARM64 child. It doesn't need a source checkout or build context. The installed copy uses host `./conf`, `./data`, and `./workspaces` paths relative to the installation directory, publishes on every host interface by default, and omits fixed container names so separate Compose project directories don't collide. The app doesn't provide a user authentication boundary, so restrict port 8888 to trusted networks with the host or upstream firewall. Set `HOST_BIND_ADDRESS=127.0.0.1` when a local reverse proxy should be the only direct client.

Official builds link the rail footer, mobile menu footer, FAQ, and terminal help to the running release's exact GitLab source tag and README through `PROJECT_SOURCE` in `app/config.py`. A modified build exposed over a network must point that value at the complete corresponding source for the modified version and keep the source offer prominent for its remote users. The full [GNU AGPLv3 license](LICENSE) controls.

Every supported local overlay in `conf/` is active under the production `/config` mount. The entrypoint validates and copies the complete tree into a private runtime path on each container start, so restart after changing any overlay:

```bash
docker compose restart shell
```

SQLite and Redis start by default. The installer generates a private Postgres password but doesn't enable Postgres; set `COMPOSE_PROFILES=postgres`, `DATABASE_BACKEND=postgres`, and keep the generated `DATABASE_URL` when you choose that backend. The `llama` profile is independent and can be combined as `COMPOSE_PROFILES=postgres,llama`.

`/data` is the durable app boundary. Redis has persistence disabled because it holds coordination and cache state. Files are disabled by default. Set `WORKSPACE_ENABLED=true`, `WORKSPACE_BACKEND=volume`, and `WORKSPACE_ROOT=/workspaces` in `.env` for persistent Files. The production Compose file already maps `./workspaces` to that path.

For SELinux-enforcing hosts, add a local Compose override with private relabeling such as `./conf:/config:ro,Z`, `./data:/data:Z`, and `./workspaces:/workspaces:Z`. Rootless Docker and Podman can reject scanner capabilities even when the YAML is otherwise compatible. See [Supported Runtimes](#supported-runtimes) for the current production matrix.

After `docker compose pull`, run `./verify-release-image.sh` before starting the stack. It normalizes the host to AMD64 or ARM64, requires the GitLab and Docker Hub index digests in `release-manifest.json` to agree, confirms `.env` still selects that reviewed release image, and checks the architecture and Python base labels against the recorded platform. The standard Docker CLI is enough; the verifier doesn't require Buildx. Apple Silicon uses the native ARM64 child when one is published and can use Docker's AMD64 emulation for an explicitly degraded AMD64-only release, while Linux ARM64 rejects a release that doesn't include its native child. Any other mismatch or unsupported architecture stops with a named error instead of starting an unverified image. The successful output names the host platform, signed index digest, and selected child digest.

Release assets add publisher identity on top of those digest checks. `SHA256SUMS.sigstore.json` is a keyless Sigstore bundle for the checksum manifest, and both immutable index references plus every listed child manifest carry Cosign signatures. Verify the canonical index digest from `release-manifest.json` as the primary release target with issuer `https://gitlab.com` and certificate identity `https://gitlab.com/darklab.sh/darklab_shell//.gitlab-ci.yml@refs/tags/vX.Y.Z`; release candidates use the same identity ending in `vX.Y.Z-rc.N`. The child digest in the platform map proves what Docker selected locally, but it isn't interchangeable with the signed index digest in operator instructions. The public [Docker Hub overview](https://hub.docker.com/r/darklabsh/darklab-shell) independently publishes the corresponding final-or-candidate identity pattern. The matching `release-evidence.json` ties the index and child digests to the tag, commit, pipeline, per-platform CycloneDX SBOMs and Grype reports, SLSA provenance, and `release-build-inputs.json`. That build-input inventory records one exact Python base index, its platform manifests, and every Dockerfile network-fetching step; the SBOMs record what those steps installed. Release CI records every vulnerability match and blocks fixed Critical vulnerabilities.

Before an upgrade, stop writes and verify a backup of the selected database, `.env`, `conf/`, host `data/`, persistent workspaces, and `release-manifest.json`. The production stack mounts that deployment-directory `./data` path at `/data` inside the container. Run the new installer in a separate empty directory, compare its managed files, preserve operator-owned state, then update `DARKLAB_IMAGE` to the exact new tag and recreate the shell. Startup may apply a forward-only schema migration, and changing the tag back doesn't reverse it.

### Production Compose overrides

The installed `compose.yaml` is release-owned. Its `shell` service includes a commented copy of the optional scanner-tuning settings for discoverability, but don't uncomment them in the managed file. Keep deployment-specific service settings in a separate file beside it so an upgrade can replace the managed stack without overwriting your choices. For example, create `compose.operator.yaml` to add scanner limits:

```yaml
services:
  shell:
    ulimits:
      nofile:
        soft: 65535
        hard: 65535
    sysctls:
      net.ipv4.ip_local_port_range: "1024 65535"
      net.ipv4.tcp_tw_reuse: 1
      net.ipv4.tcp_fin_timeout: 15
      net.ipv4.tcp_max_tw_buckets: 131072
```

```bash
docker compose --env-file .env -f compose.yaml -f compose.operator.yaml config --quiet
docker compose --env-file .env -f compose.yaml -f compose.operator.yaml up -d
```

`darklab-deploy` manages the release-owned base stack and automatically adds an existing `compose.operator.yaml` after it for lifecycle work. Backup, restore, database migration, upgrade validation, and removal all use the layered configuration; restore restarts and upgrade instructions do too. Keep a private copy of this operator-owned file with your deployment backups because managed backups don't automatically include additional top-level Compose files. Application log format remains separate: set `log_format: gelf` in installed `conf/config.local.yaml` only when the application itself should emit GELF-shaped JSON.

### Source-checkout development

The repository-backed [compose.dev.yaml](compose.dev.yaml) is the supported development stack. It builds the same Dockerfile, mounts `./app` read-only at `/opt/darklab-source/app`, and stages a fresh container-owned snapshot at `/app` before the app drops privileges. This keeps private Linux checkout modes readable without making the staged code writable, binds the app to loopback by default, and omits production restart behavior. It isn't a production deployment path.

The base file starts the shell service, an ephemeral Redis sidecar, the shell's writable `/data` volume, tmpfs scratch space, default port binding, and the runtime capabilities needed by supported scanners. It also includes an optional profile-gated Postgres 18 service with a named volume and healthcheck for backend development and testing:

```bash
docker compose -f compose.dev.yaml --profile postgres up -d postgres
```

The app keeps using SQLite by default. The optional Postgres service supports source-based backend work and the opt-in Postgres test lane. Startup runs the app-owned schema migrations for the selected backend, and when `DATABASE_BACKEND=postgres`, normal app database calls route through the Postgres pool.

The bundled Redis service runs with a read-only root filesystem and persistence disabled (`--save ""`, `--appendonly no`). It stores coordination, broker, rate-limit, and cache-like state; durable app data belongs in SQLite/Postgres, `/data`, and any configured workspace volume.

Start the full development stack explicitly so Compose doesn't mistake it for an installed production stack:

```bash
docker compose -f compose.dev.yaml up --build
```

Application log format is independent of container log transport. Development
can set `log_format: gelf` in `app/conf/config.local.yaml`, while production
uses installed `conf/config.local.yaml`. A host-local collector can forward the
resulting standard output without changing the application stack.

### Docker Labels

The Docker image and Compose container include a small static label set for Docker-native inventory tools such as CheckMK's Docker plugin. These labels are meant for quick identification. Use `/metrics` for live values such as health, database size, queue state, and connection-pool state.

Image labels are set by the Dockerfile:

| Label | Value |
|-------|-------|
| `org.opencontainers.image.title` | `darklab_shell` |
| `org.opencontainers.image.description` | Short app description |
| `org.opencontainers.image.source` | Source repository URL |
| `org.opencontainers.image.url` | Project URL |
| `org.opencontainers.image.vendor` | `darklab.sh` |
| `org.opencontainers.image.version` | App version from the `APP_VERSION` build arg |
| `org.opencontainers.image.revision` | Git revision from the `VCS_REF` build arg |
| `org.opencontainers.image.created` | Build timestamp from the `BUILD_DATE` build arg |
| `sh.darklab.app.name` | `darklab_shell` |
| `sh.darklab.app.version` | App version from the same build arg |
| `sh.darklab.git.revision` | Git revision from the same build arg |
| `sh.darklab.python.version` | Python base image version |

The base Compose service adds container labels for runtime configuration that is fixed when the container starts:

| Label | Value |
|-------|-------|
| `sh.darklab.config.database_backend` | `${DATABASE_BACKEND:-sqlite}` |
| `sh.darklab.metrics.path` | `/metrics` |

For a local development image, pass the metadata values you want Docker inventory to show:

```bash
docker compose -f compose.dev.yaml build \
  --build-arg APP_VERSION=2.8.3 \
  --build-arg VCS_REF="$(git rev-parse --short HEAD)" \
  --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

To check the labels on a running container:

```bash
docker inspect "$(docker compose -f compose.dev.yaml ps -q shell)" \
  --format '{{ index .Config.Labels "sh.darklab.config.database_backend" }}'
```

---

## Workspace Storage Recipes

Files/workspace storage has three coordinated settings:

- `WORKSPACE_ENABLED` turns personal and team Files on or off.
- `WORKSPACE_BACKEND` selects short-lived `tmpfs` storage or persistent `volume` storage.
- `WORKSPACE_ROOT` is the path the Docker entrypoint prepares before dropping privileges and the app uses at runtime.

Set all three in `.env` for production and Compose-based source development. Direct source runs export the same variables in the process environment. They aren't `config.local.yaml` options because the entrypoint, mount layout, backup/restore tooling, and app must all use the same deployment contract.

Team Files use the same root as personal Files. Personal directories are named `sess_*`; team directories are named `team_*`. For durable shared team Files, use the `volume` backend with a persistent shared mount. The `tmpfs` backend is useful for scratch personal sessions, but team Files stored there are lost on container restart and are only shared inside one running container.

### Short-lived tmpfs storage

```env
WORKSPACE_ENABLED=true
WORKSPACE_BACKEND=tmpfs
WORKSPACE_ROOT=/tmp/darklab_shell-workspaces
```

### Persistent bind mount

The production Compose file already maps `./workspaces:/workspaces`. Select that persistent location in `.env`:

```env
WORKSPACE_ENABLED=true
WORKSPACE_BACKEND=volume
WORKSPACE_ROOT=/workspaces
```

Prepare the host bind-mount directory with the numeric UID/GID used by `appuser` inside the built image, not a host username. The current image creates `appuser` as `995:995` and `scanner` as `994:994`; scanner commands use the shared `appuser` run group when they access validated workspace files:

```bash
mkdir -p ./workspaces
chown 995:995 ./workspaces
chmod 730 ./workspaces
```

Existing `sess_*` directories should be owned by `995:995` with mode `3730`. Existing app-created files should be `0640`; command-created output files may be `0660` so the `scanner` user can update them through the shared group.

### Docker named volume

```yaml
services:
  shell:
    environment:
      - WORKSPACE_ENABLED=true
      - WORKSPACE_BACKEND=volume
      - WORKSPACE_ROOT=/workspaces
    volumes:
      - darklab_shell_workspaces:/workspaces

volumes:
  darklab_shell_workspaces:
```

---

## Operator Backups

Production installations include the backup and restore path in `darklab-deploy`. It runs the image's backup helper in a one-off Compose container, so the host only needs Docker and Compose. The release image includes the PostgreSQL 18 client used with the bundled PostgreSQL 18 service:

```bash
./darklab-deploy backup --keep-days 14
./darklab-deploy restore backups/darklab-backup-<timestamp>.tar.gz
```

Managed backups include the SQLite snapshot or Postgres dump, `.env`, `conf/`, `/data` including `.secrets_master_key`, the complete managed `/workspaces` directory, release metadata, a redacted manifest, restore notes, and checksums. The workspace directory is included even when Files is currently disabled or `.env` uses optional whitespace or quoting that Compose accepts, so dormant files aren't lost because of configuration state or formatting. The archive stays under the private `backups/` directory and is owned by the host user who ran the command. Restore verifies the archive and creates another verified backup before it stops the app or writes any state. Files are staged inside their destination mounts, and Postgres uses one transaction before staged files are committed. Ordinary restores require the backup and target to use the same database backend, and the target keeps its backend, URL, Postgres credentials, and current image. Restored host files return to the UID/GID that invoked the command. When restored `.env` content changes, the wrapper force-recreates the app container so the restored values take effect, and every successful restore waits for app health before returning. An installed `compose.operator.yaml` remains active for the stop, restore, and restart sequence. A failed restore leaves the app stopped and prints the safety-backup recovery command, so it never deliberately starts against partially restored state.

To move a managed Postgres backup to a newly installed replacement host, use the explicit backend-adoption path:

```bash
./darklab-deploy restore --adopt-backend backups/darklab-backup-<timestamp>.tar.gz
```

This option is only for a Postgres backup restored into a fresh install that's still using its default SQLite backend. Run it without `sudo` as the user who owns the installation; Docker handles access to the app-owned mounts. The command keeps the new installation's image, Postgres URL, username, password, and database name; enables the bundled Postgres profile; confirms the destination database has no user tables; restores the dump in one transaction; and then recreates the app with Postgres active. Without `--adopt-backend`, a backend mismatch fails before the safety backup or app shutdown and prints the adoption command. An adoption attempt also fails before `pg_restore` if the destination Postgres database isn't empty.

`./darklab-deploy upgrade X.Y.Z` uses the same path automatically. It refuses to continue when release-owned files have changed, the target isn't newer, the release archive can't be verified, the candidate base stack doesn't work with the installed `compose.operator.yaml`, or the pre-upgrade backup fails. Every archive must produce a complete readable listing, and each member path is checked before anything is extracted. Online upgrades verify the release's signed `SHA256SUMS` with a digest-pinned Cosign container and the exact GitLab tag identity before downloading the archive. A supplied `--backup /path/to/archive` must pass the same checksum verification. `--archive /path/to/archive` is an operator-trusted offline path: the command checks the adjacent `.sha256` file, but you must verify the publisher's `SHA256SUMS.sigstore.json` separately. The command updates only managed files and the `DARKLAB_IMAGE` line; other `.env` settings and every operator directory stay in place. When a release adds keys to `.env.example`, the command prints only their names and asks you to review the installed example before restarting. It doesn't append defaults, replace existing values, or print values from either file. Afterward, run the printed pull, image-verification, and restart commands; the printed Compose commands include the operator override when it exists. Changing an image tag never reverses a database migration.

The underlying `scripts/operations/backup_system.py` helper remains available to contributors building development fixtures or custom test environments. It isn't a supported production lifecycle interface; production automation should invoke `darklab-deploy backup` from the installation directory.

Completed backups use microsecond UTC names and add a sequence when a timestamp is already present. Archives are published without replacing an existing file, and checksum generation reads large payloads in bounded chunks instead of holding a full file in memory.

When `--keep-days` is set, the manifest records the cutoff, candidates examined, removal candidates, and inspection failures. Retention runs only after the new backup is published, then prints the actual removed and failure totals for cron logs. Candidate metadata or removal failures are warnings rather than silent skips. Expected operator errors stay concise; unexpected script failures also print a traceback with the failing function and line.

Backups contain sensitive material: `.env`, encrypted secret rows, the app-owned secrets key file, and local deployment files may all be present. Store the backup directory with owner-only permissions, keep archives off shared paths, and do not publish `manifest.json` even though it redacts known secret values.

---

## Production Host Tuning

Wide scans can open many outbound sockets quickly. Production operators can add the container's file descriptor limit and network namespace sysctls with the [Compose override](#production-compose-overrides) above. A few host-level settings may still matter.

### Docker daemon file descriptor ceiling

Docker cannot grant a container a `nofile` limit higher than the daemon's own limit. If the daemon is still at a low default, the local override's `ulimits.nofile` setting may not help.

```bash
sudo systemctl edit docker
```

Add or verify:

```ini
[Service]
LimitNOFILE=1048576
```

Then reload and restart Docker:

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

### Connection tracking table

Under wide scans, the host's connection tracking table can fill and start dropping connections. Apply immediately:

```bash
sudo sysctl -w net.netfilter.nf_conntrack_max=131072
```

Persist across reboots:

```bash
echo "net.netfilter.nf_conntrack_max=131072" | sudo tee /etc/sysctl.d/99-conntrack.conf
```

### Redis memory overcommit

The bundled Redis service disables RDB/AOF persistence, but Redis can still warn that memory overcommit must be enabled, especially if you point the app at a custom persistent Redis. Apply immediately:

```bash
sudo sysctl vm.overcommit_memory=1
```

Persist across reboots:

```bash
echo "vm.overcommit_memory = 1" | sudo tee /etc/sysctl.d/99-redis-overcommit.conf
sudo sysctl --system
```

---

## Common Recipes

These recipes lead with production installation paths. YAML snippets belong in installed `conf/config.local.yaml` unless a different file is named. For source development, use the same YAML under `app/conf/config.local.yaml`.

### Enable Files

```env
# .env in the production installation directory
WORKSPACE_ENABLED=true
WORKSPACE_BACKEND=tmpfs
WORKSPACE_ROOT=/tmp/darklab_shell-workspaces
```

For a non-Compose source run, export the same three variables before starting the app.

### Enable Interactive PTY

For production, enable the feature in `.env`:

```env
INTERACTIVE_PTY_ENABLED=true
```

The existing PTY defaults are suitable for most deployments. Fine-tune them in installed `conf/config.local.yaml` when needed:

```yaml
# conf/config.local.yaml
interactive_pty_max_runtime_seconds: 900
interactive_pty_max_concurrent_per_session: 4
interactive_pty_input_rate_limit_per_second: 10
interactive_pty_input_rate_limit_per_minute: 500
```

Non-Compose source runs export `INTERACTIVE_PTY_ENABLED=true`. Multi-worker deployments should keep Redis enabled so PTY output, input, resize, and reattach state work across workers.

### Enable Diagnostics

```yaml
# conf/config.local.yaml
diagnostics_allowed_cidrs:
  - 192.0.2.10/32
trusted_proxy_cidrs:
  - 127.0.0.1/32
  - ::1/128
```

The same allowlist gates Prometheus metrics. Keep the process-level scratch directory in `.env`:

```env
PROMETHEUS_MULTIPROC_DIR=/tmp/darklab_shell-prom
```

Tune metric collection and histogram buckets in YAML:

```yaml
# conf/config.local.yaml
metrics_enabled: true
metrics_histogram_buckets_run_duration: [0.1, 0.5, 1, 2, 5, 10, 30, 60, 300, 900, 1800, 3600]
metrics_histogram_buckets_http_duration: [0.005, 0.01, 0.05, 0.1, 0.5, 1, 5]
metrics_histogram_buckets_ai_provider_duration: [0.1, 0.5, 1, 2, 5, 10, 30, 60]
```

Example Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: darklab_shell
    metrics_path: /metrics
    static_configs:
      - targets:
          - shell.example.internal:8888
```

Metrics use the `darklab_` prefix and bounded labels such as command root, provider ID, Flask endpoint, broker mode, DB operation name, status class, and coarse outcome. A starter Grafana dashboard lives at `examples/grafana/darklab-overview.json`.

Clients allowed by `diagnostics_allowed_cidrs` also bypass the per-session AI assist write quota. This is meant for operator testing from trusted networks; the global AI write limit and worker concurrency still apply.

### Tune Atlas Import Limits

```yaml
# conf/config.local.yaml
atlas_import_max_upload_mb: 10
atlas_import_max_rows: 5000
atlas_import_max_findings: 5000
atlas_import_max_warnings: 100
atlas_import_max_xml_elements: 100000
atlas_import_preview_sample_limit: 20
atlas_import_warning_sample_limit: 50
atlas_import_draft_ttl_minutes: 30
```

These caps apply to Atlas imports before and during apply, so lowering them can make large Nessus, ZAP, Burp, Nuclei, CSV, or JSONL files fail preview with a clear limit error. Invalid values and `0` fall back to the server defaults above.

### Set The Default Theme

```yaml
# conf/config.local.yaml
default_theme: darklab_obsidian.yaml
```

Shipped themes remain under `/app/conf/themes` in the release image. Production theme overlays belong under installed `conf/themes/`. See [THEME.md](THEME.md) for theme authoring.

### Enable GELF Application Logs

```yaml
# conf/config.local.yaml
log_format: gelf
log_level: INFO
```

The application writes GELF-shaped JSON to standard output. Use a host-local
collector when those container logs should be sent to a remote log service.
HTTP response codes are indexed under numeric `_http_status`; provider,
workflow, schedule/watcher, AI, Project, team, and export states use their
documented feature-specific fields. Existing Graylog/OpenSearch dashboards
that query the older `_status` field should be updated to those names. The app
doesn't need an index rotation to stop mapper failures because it no longer
writes `_status`; rotate only when you want to remove that legacy mapping.

### Customize Package Presets

The release image ships its evidence package presets under `/app/conf/package_presets.yaml`. Set `package_presets_file` in installed `conf/config.local.yaml` when you want an operator-managed replacement catalog:

```yaml
# conf/config.local.yaml
package_presets_file: package_presets.local.yaml
```

Normal relative paths resolve from the shipped config root. Relative filenames containing `.local.` resolve from the operator root, so this production example reads `conf/package_presets.local.yaml`; source development uses `app/conf/package_presets.local.yaml`. The app reloads the catalog when the readable YAML file changes. If an override is missing or invalid, the shipped presets stay available and the server logs `PACKAGE_PRESETS_OVERRIDE_INVALID`.

A preset controls the wizard defaults only. Users can still adjust the package before creating it, and package size limits, redaction rules, artifact safety checks, and project link validation still apply.

```yaml
# conf/package_presets.local.yaml
version: 1
presets:
  - id: customer_handoff
    label: Customer Handoff
    description: Client-ready package with reviewed findings and redacted artifacts.
    name_suffix: customer
    redaction_mode: redacted
    include_artifacts: true
    include_private_notes: false
    labels:
      - client
    notes: Ready for customer review.
    selection:
      runs: all
      transcripts: with_findings
      findings: non_false_positive
      artifacts: selectable
    targets: all
```

Supported selection policies are:

| Field | Policies |
| --- | --- |
| `runs` | `all`, `none` |
| `transcripts` | `all`, `none`, `with_findings` |
| `findings` | `all`, `none`, `non_false_positive` |
| `artifacts` | `all`, `none`, `selectable` |
| `targets` | `all`, `none` |

Preset ids must use lowercase letters, numbers, underscores, or hyphens. Keep the shipped `evidence`, `summary`, `full`, and `redacted` presets if you want old package manifests to stay easy to read.

### Customize Report Templates

The release image ships engagement report templates under `/app/conf/report_templates.yaml`. Set `report_templates_file` in installed `conf/config.local.yaml` when you want an operator-managed replacement catalog:

```yaml
# conf/config.local.yaml
report_templates_file: report_templates.local.yaml
```

Normal relative paths resolve from the shipped config root. Relative filenames containing `.local.` resolve from the operator root, so the example works in both deployment layouts. The app reloads the catalog when the readable YAML file changes. If an override is missing or invalid, the shipped templates stay available and the server logs `REPORT_TEMPLATES_OVERRIDE_INVALID`.

### Customize FAQ, Welcome, Commands, Workflows, and Catalogs

- Add FAQ entries in `faq.local.yaml`.
- Add welcome samples in `welcome.local.yaml`.
- Add deployment-specific command registry entries in `commands.local.yaml`.
- Add complete deployment-specific assessment profiles in `assessment_profiles.local.yaml`. A profile with the same key replaces the shipped profile as one unit; its checks don't merge.
- Add deployment-specific legacy or v2 workflows in `workflows.local.yaml`, or save personal/team workflows through the in-app editor. Leave `version` out for legacy entries or set it to `2`; unsupported explicit versions and malformed YAML are rejected. See [Workflow Playbooks](docs/workflows.md) for the full parameter, transition, capture, execution, and compatibility reference.
- Add desktop or mobile hints in `app_hints.local.txt` or `app_hints_mobile.local.txt`.
- Replace banner art with `ascii.local.txt` or `ascii_mobile.local.txt`. These files replace the shipped text, so the installer provides non-active `.example` files instead of empty active placeholders.
- Add deployment-specific evidence package presets in `package_presets.local.yaml` and point `package_presets_file` at that file.
- Add deployment-specific report templates in `report_templates.local.yaml` and point `report_templates_file` at that file.

Use these names under installed `conf/` for production installations or `app/conf/` for source development.

---

## Related Docs

- [README.md](README.md#quick-start) - initial setup and first run
- [FEATURES.md](FEATURES.md) - user-facing behavior behind the settings
- [ARCHITECTURE.md](ARCHITECTURE.md) - runtime and security contracts
- [docs/storage-scaling.md](docs/storage-scaling.md) - storage planning and database growth
- [docs/postgres-migration.md](docs/postgres-migration.md) - SQLite-to-Postgres migration
