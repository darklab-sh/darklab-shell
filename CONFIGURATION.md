# Configuration

This is the operator-facing configuration reference for darklab_shell. It covers the application config files under `app/conf/`, local override files, Docker Compose settings, `.env`, production overlays, and common deployment recipes.

For feature behavior, start with [FEATURES.md](FEATURES.md). For internal configuration flow between Flask and the browser, see [ARCHITECTURE.md](ARCHITECTURE.md#configuration-surfaces).

---

## Configuration Model

Application settings live in `app/conf/config.yaml`. The checked-in file acts as the deployment override layer on top of built-in defaults from `app/config.py`.

Resolution order for the main app config is:

1. Built-in defaults from `app/config.py`
2. `app/conf/config.yaml`
3. Optional untracked `app/conf/config.local.yaml`

Most settings in `config.yaml` are read at startup. After changing `config.yaml` or `config.local.yaml`, restart the app container:

```bash
docker compose restart
```

No image rebuild is needed for normal config changes.

---

## Local Override Files

Most operator-owned files under `app/conf/` and `app/conf/themes/` support sibling `*.local.*` overlays. These local files are intentionally useful for private deployment changes that should not be committed.

| Base file | Local overlay | Behavior |
|-----------|---------------|----------|
| `app/conf/config.yaml` | `app/conf/config.local.yaml` | Overrides any subset of app settings |
| `app/conf/commands.yaml` | `app/conf/commands.local.yaml` | Adds new command roots and merges same-root entries into the base registry |
| `app/conf/faq.yaml` | `app/conf/faq.local.yaml` | Appends local FAQ entries |
| `app/conf/welcome.yaml` | `app/conf/welcome.local.yaml` | Appends local welcome samples |
| `app/conf/workflows.yaml` | `app/conf/workflows.local.yaml` | Appends local guided workflows |
| `app/conf/ascii.txt` | `app/conf/ascii.local.txt` | Replaces desktop banner art |
| `app/conf/ascii_mobile.txt` | `app/conf/ascii_mobile.local.txt` | Replaces mobile banner art |
| `app/conf/app_hints.txt` | `app/conf/app_hints.local.txt` | Appends desktop hints |
| `app/conf/app_hints_mobile.txt` | `app/conf/app_hints_mobile.local.txt` | Appends mobile hints |
| `app/conf/themes/<theme>.yaml` | `app/conf/themes/<theme>.local.yaml` | Overlays one named theme |

---

## Config File Reload Behavior

| File | When changes take effect |
|------|--------------------------|
| `conf/faq.yaml` | Immediately; re-read on every request |
| `conf/ascii.txt` | On next page load |
| `conf/ascii_mobile.txt` | On next page load |
| `conf/app_hints.txt` | On next page load |
| `conf/app_hints_mobile.txt` | On next page load |
| `conf/welcome.yaml` | On next page load |
| `conf/tour.yaml` | Immediately for tour renderers |
| `conf/wordlists.yaml` | Immediately for the `wordlist` command and autocomplete requests |
| `conf/workflows.yaml` | Immediately for Workflows panel, command registry, and smoke-corpus helpers |
| `conf/themes/*.yaml` | On next page load, permalink load, diagnostics load, or HTML export |
| `conf/commands.yaml` | On next page load for autocomplete; immediately for command policy, catalog, diagnostics, and smoke-corpus helpers |
| `conf/config.yaml` | After `docker compose restart` |

---

## Headless CLI Configuration

The bundled `darklab` CLI talks to `/api/v1` and keeps its own client-side settings. These do not change server behavior.

Resolution order is:

1. command flags: `--api-url`, `--token`, and `--timeout`
2. environment variables: `DARKLAB_API_URL`, `DARKLAB_TOKEN`, and `DARKLAB_TIMEOUT`
3. `~/.config/darklab/config.toml`
4. built-in defaults

Example:

```toml
api_url = "https://shell.example.com"
token = "tok_your_session_token"
timeout = 30
```

`api_url` must include `http://` or `https://`. Custom ports are supported, so local installs can use values like `http://192.168.1.3:9999`. The file is parsed as TOML, so inline comments and numeric timeout values work normally.

Use [docs/api.md](docs/api.md) for endpoint examples and CLI commands.

---

## Application Settings

The values below are the built-in server defaults from `app/config.py`.

Project workspace settings cap session-scoped case folders, links, targets, labels, notes, and package exports. Interactive PTY settings enable a separate guarded terminal path for approved interactive tools; leave `interactive_pty_enabled` off unless the deployment is prepared for the runtime and Redis requirements described below.

| Setting | Default | Description |
|---------|---------|-------------|
| `app_name` | `darklab_shell` | Name shown in the browser tab, header, and permalink pages |
| `prompt_username` | `anon` | Default username shown in the shell prompt and welcome samples. Users can override this in Options for their own session |
| `prompt_domain` | `darklab.sh` | Domain shown after the prompt username. The UI renders `<username>@<domain>:~ $` when workspaces are disabled and `<username>@<domain>:<workspace path> $` when workspaces are enabled |
| `motd` | _(empty)_ | Optional operator message shown at the top of the welcome sequence as a centered “Message From The Operator” notice. Supports `**bold**`, `` `code` ``, `[link](url)`, and newlines. Leave empty to disable |
| `default_theme` | `darklab_obsidian.yaml` | Default theme filename for new visitors. Must match a file in `app/conf/themes/`. Overridden by the user's saved preference |
| `share_redaction_enabled` | `true` | Enables the built-in basic snapshot-share redaction baseline for bearer tokens, email addresses, IPv4 addresses, IPv6 addresses, and hostnames/dotted domains. When enabled, the `share snapshot` action asks whether to share the raw or redacted snapshot until the user sets a persistent default in the Options modal. If the prompt’s checkbox is enabled, the chosen raw/redacted mode is written back to that same persistent default. When disabled, no built-in or custom snapshot-share redaction rules run |
| `share_redaction_rules` | `[]` | Optional operator-defined regex rules appended after the built-in snapshot-share redaction baseline. Each rule supports `label`, `pattern`, `replacement`, and `flags` (`i`, `m`). This does not change stored run history or the history drawer permalink path; it affects only snapshot sharing |
| `trusted_proxy_cidrs` | `["127.0.0.1/32", "::1/128"]` | IPs / CIDRs allowed to supply `X-Forwarded-For`. Requests outside these ranges ignore forwarded headers and use the direct connection IP |
| `diagnostics_allowed_cidrs` | `[]` | IPs / CIDRs that may access `/diag` and `/metrics`. Checked against the resolved client IP using the same trusted-proxy rules as the rest of the app, so `X-Forwarded-For` is honored only when the direct peer is inside `trusted_proxy_cidrs`. Empty list disables the page entirely and prevents metrics scrapes. When enabled, a `diag` button appears in the desktop rail and the mobile menu for matching visitors |
| `metrics_enabled` | `true` | Enables the Prometheus `/metrics` endpoint for callers allowed by `diagnostics_allowed_cidrs`. Set to `false` to hide `/metrics` while keeping `/diag` available |
| `prometheus_multiproc_dir` | `/tmp/darklab_shell-prom` | Writable shared directory used by `prometheus_client` to aggregate counters and histograms across Gunicorn workers. `PROMETHEUS_MULTIPROC_DIR` overrides this value when set |
| `metrics_histogram_buckets_run_duration` | `[0.1, 0.5, 1, 2, 5, 10, 30, 60, 300, 900, 1800, 3600]` | Prometheus run and PTY duration histogram buckets, in seconds |
| `metrics_histogram_buckets_http_duration` | `[0.005, 0.01, 0.05, 0.1, 0.5, 1, 5]` | Prometheus HTTP request duration histogram buckets, in seconds |
| `restricted_command_input_cidrs` | `[]` | IPs / CIDRs that command validation rejects when supplied in metadata-known target slots. Applies to literal IP/CIDR values, URLs with literal IP hosts, host:port values, and inspectable workspace input files passed through declared read flags. Domain names are not DNS-resolved |
| `history_panel_limit` | `50` | Number of history rows shown per page in the desktop history drawer and mobile recents sheet |
| `recent_commands_limit` | `50` | Number of distinct recent commands loaded into prompt Up/Down history, desktop rail recents, and the mobile recent peek |
| `data_dir` | auto | Server-side only. Directory used for the default SQLite history database, compressed full-output artifacts, body-store files, and the app-owned secret key file. Postgres deployments still use it for filesystem-backed artifacts and app-owned files. Leave unset to use `/data` when it is writable, otherwise `/tmp` for local/dev fallback. If set explicitly, the directory must be writable at startup |
| `database_backend` | `sqlite` | Server-side only. Selects the database backend. SQLite remains the default local/single-user path. When set to `postgres`, startup runs the app-owned Postgres schema migrations and normal `db_connect()` calls use the Postgres pool |
| `database_url` | _(empty)_ | Server-side only. Postgres DSN used when `database_backend: postgres`. Ignored by SQLite. Can also be set with the `DATABASE_URL` environment variable |
| `database_pool_min` | `1` | Server-side only. Minimum Postgres pool size. Ignored by SQLite. Can also be set with `DATABASE_POOL_MIN` |
| `database_pool_max` | `5` | Server-side only. Maximum Postgres pool size. Ignored by SQLite. Can also be set with `DATABASE_POOL_MAX` |
| `database_postgres_jit` | `false` | Server-side only. Controls whether app-owned Postgres pool connections allow PostgreSQL JIT compilation. The default keeps interactive pages from paying JIT startup cost on complex queries. Can also be set with `DATABASE_POSTGRES_JIT` |
| `permalink_retention_days` | `365` | Delete runs and snapshots older than this many days on startup. `0` means unlimited retention |
| `runs_search_text_inline_max_bytes` | `0` | Server-side only. Offloads oversized `runs.output_search_text` values to compressed files under `data_dir/body-store` when the UTF-8 body is larger than this byte threshold. History search still checks the offloaded body when needed, so terms beyond the stored preview remain findable. `0` keeps values inline |
| `snapshots_inline_max_bytes` | `0` | Server-side only. Offloads oversized tab snapshot bodies under `data_dir/body-store` while share links still read back normally. `0` keeps snapshot content inline |
| `intel_payload_inline_max_bytes` | `0` | Server-side only. Offloads oversized Atlas intel provider payloads under `data_dir/body-store` while entity detail responses still return the provider data. `0` keeps intel payloads inline |
| `rate_limit_enabled` | `true` | Enables the shared `/runs` and `/api/v1` rate limiter. Set to `false` only for test-only or maintenance overlays where throttling should be bypassed |
| `rate_limit_per_minute` | `30` | Max `/runs` and `/api/v1` requests per minute per IP |
| `rate_limit_per_second` | `5` | Max `/runs` and `/api/v1` requests per second per IP |
| `intel_cache_ttl_shodan_ip_seconds` | `86400` | Server-side only. Default cache lifetime for normalized Shodan IP responses |
| `intel_cache_ttl_shodan_search_seconds` | `21600` | Server-side only. Default cache lifetime for normalized Shodan search responses |
| `intel_cache_ttl_censys_host_seconds` | `21600` | Server-side only. Default cache lifetime for normalized Censys host responses |
| `intel_cache_ttl_virustotal_domain_seconds` | `21600` | Server-side only. Default cache lifetime for normalized VirusTotal domain responses |
| `intel_cache_ttl_virustotal_file_seconds` | `86400` | Server-side only. Default cache lifetime for normalized VirusTotal file or hash responses |
| `intel_cache_ttl_greynoise_ip_seconds` | `3600` | Server-side only. Default cache lifetime for normalized GreyNoise IP responses |
| `intel_cache_ttl_otx_indicator_seconds` | `21600` | Server-side only. Default cache lifetime for normalized AlienVault OTX indicator responses |
| `intel_cache_ttl_abuseipdb_ip_seconds` | `21600` | Server-side only. Default cache lifetime for normalized AbuseIPDB IP responses |
| `intel_cache_ttl_ipinfo_ip_seconds` | `21600` | Server-side only. Default cache lifetime for normalized IPinfo IP responses |
| `intel_cache_ttl_teamcymru_ip_seconds` | `86400` | Server-side only. Default cache lifetime for normalized Team Cymru IP ownership responses |
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
| `intel_rate_limit_shodan_bucket` | `5` | Server-side only. Token-bucket size for Shodan lookups per session |
| `intel_rate_limit_shodan_refill_seconds` | `1` | Server-side only. Seconds between Shodan token refills |
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
| `interactive_pty_input_rate_limit_per_minute` | `500` | Max interactive PTY input requests per minute per IP. This is separate from `/runs` because normal terminal typing produces many small input requests |
| `interactive_pty_input_rate_limit_per_second` | `10` | Max interactive PTY input request burst per second per IP |
| `max_tabs` | `8` | Maximum number of tabs a user can have open at once. `0` means unlimited |
| `max_output_lines` | `5000` | Max rows retained in the live tab DOM and in the saved run preview. Oldest rendered rows are dropped from the top when exceeded, while visible line numbers continue reflecting emitted output order. `0` means unlimited |
| `high_volume_output_line_threshold` | `50000` | Browser-facing. Pauses live rendering for brokered command output after this many received lines. Output keeps counting, kill controls stay available, and backend preview/full-output storage still follows the normal output settings. `0` disables the pause |
| `high_volume_output_status_interval_lines` | `50000` | Browser-facing. When high-volume live-output mode is active, show another status line after this many additional received lines |
| `output_preview_max_mb` | `1 MB` | Server-side only. Hard cap on the saved run preview payload so huge single-line outputs, such as JSON, cannot make history rows enormous. `0` means unlimited |
| `persist_full_run_output` | `true` | Server-side only. Persists full output for completed runs as compressed artifacts while the history drawer and normal run permalink keep using the capped database preview |
| `full_output_max_mb` | `5 MB` | Server-side only. Hard cap on the uncompressed UTF-8 payload written into a full-output artifact before gzip compression. `0` means unlimited |
| `workspace_enabled` | `false` | Server-side only. Enables the app-managed per-session workspace foundation. This does not enable shell navigation or redirection by itself |
| `workspace_backend` | `tmpfs` | Server-side only. Storage intent label for workspaces: `tmpfs` for short-lived in-memory storage or `volume` for a Docker-mounted location. The label does not mount storage by itself |
| `workspace_root` | `/tmp/darklab_shell-workspaces` | Server-side only. Root directory that contains hashed per-session workspace directories. In Compose deployments, `WORKSPACE_ROOT` overrides this value so the entrypoint and app use the same path |
| `workspace_quota_mb` | `50 MB` | Server-side only. Per-session workspace quota |
| `workspace_max_file_mb` | `5 MB` | Server-side only. Maximum single app-managed text file size |
| `workspace_max_files` | `100` | Server-side only. Maximum file count per session workspace |
| `workspace_inactivity_ttl_hours` | `1` | Server-side only. Inactive session workspace cleanup threshold in hours; `0` disables age-based cleanup. Workspace activity touches the hashed session directory, and periodic cleanup removes expired `sess_*` directories rather than aging out individual files |
| `max_projects_per_session` | `100` | Server-side only. Maximum project workspace records one session can create |
| `max_project_links_per_project` | `5000` | Server-side only. Maximum linked source records per project |
| `max_project_entities_per_project` | `5000` | Server-side only. Maximum Atlas entities linked into one project |
| `max_project_targets_per_project` | `200` | Server-side only. Maximum manual or discovered project targets per project, separate from bulk-linked Atlas entities |
| `max_evidence_packages_per_project` | `25` | Server-side only. Maximum draft evidence package manifests per project |
| `max_entity_labels_per_session` | `5000` | Server-side only. Maximum entity labels one session can create |
| `max_entity_labels_per_entity` | `20` | Server-side only. Maximum labels attached to a single supported entity |
| `max_entity_notes_per_session` | `2000` | Server-side only. Maximum one-note-per-entity records one session can create |
| `evidence_package_max_mb` | `25 MB` | Maximum final ZIP size for an evidence package download. The package wizard shows a best-guess ZIP estimate before the archive is built, and the server enforces the actual compressed size before returning the file |
| `evidence_package_max_uncompressed_mb` | `500 MB` | Maximum expanded evidence package content before ZIP compression. This keeps very large transcript or artifact selections bounded even when the final ZIP would compress well |
| `evidence_package_max_artifacts` | `100` | Maximum workspace artifacts included in one evidence package archive. The package wizard also uses this value when presenting archive constraints |
| `evidence_package_download_rate_limit_per_minute` | `10` | Server-side only. Per-session evidence package download limit per minute |
| `evidence_package_download_rate_limit_per_second` | `2` | Server-side only. Per-session evidence package download burst limit per second |
| `notifications` | see nested defaults | Server-side only. Outbound notification delivery guardrails for do-not-disturb, per-channel send rate, and retry behavior |
| `notifications.do_not_disturb` | `false` | Server-side only. Stops outbound notification delivery before channel sends while keeping queued event storage available |
| `notifications.delivery_rate_per_minute` | `10` | Server-side only. Per-channel outbound notification send cap used by the worker claim path |
| `notifications.http_timeout_seconds` | `8` | Server-side only. HTTP timeout for outbound webhook-style notification channel sends |
| `notifications.retry.max_attempts` | `6` | Server-side only. Maximum delivery attempts before a notification event moves to dead-letter state |
| `notifications.retry.max_age_hours` | `24` | Server-side only. Maximum retry window before a notification event moves to dead-letter state |
| `notifications.retry.base_delay_seconds` | `30` | Server-side only. Base delay for exponential notification retry backoff |
| `command_timeout_seconds` | `3600` | Auto-kill commands that run longer than this many seconds. `0` means disabled |
| `heartbeat_interval_seconds` | `20` | How often to send an SSE heartbeat on idle connections to prevent proxy timeouts |
| `run_broker_enabled` | `true` | Enables the brokered run model for command start, output replay, and live reattachment |
| `run_broker_require_redis` | `true` | Requires Redis for brokered live reattachment. Keep enabled for Docker/production deployments; set to `false` only for single-process local development where in-memory replay limitations are acceptable |
| `run_broker_active_stream_ttl_seconds` | `14400` | Safety TTL for active broker streams, refreshed while a run is active |
| `run_broker_completed_stream_ttl_seconds` | `3600` | How long completed broker streams remain replayable after history finalization before completed-run restore relies on saved history rows and artifacts |
| `run_broker_max_replay_bytes` | `10485760` | Maximum replay payload retained per brokered run stream. Replay is also bounded by `max_output_lines`; there is no separate line-limit setting |
| `run_broker_subscriber_block_seconds` | `15` | How long broker stream subscribers wait for new events before receiving a heartbeat |
| `run_broker_heartbeat_seconds` | `20` | How often broker workers emit heartbeat events while a process is idle |
| `run_broker_owner_stale_seconds` | `75` | How long an owner browser can go without touching a run before ownership is considered stale |
| `interactive_pty_enabled` | `false` | Enables the guarded interactive PTY path for allowlisted tools such as `nc --interactive`, `telnet --interactive`, `mtr --interactive`, `ffuf --interactive`, and `masscan --interactive`. Multi-worker deployments require Redis so PTY output, input, and resize events can be brokered across workers; without Redis this mode is limited to `WEB_CONCURRENCY=1` |
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
- `sample` - optional command-chip value for the terminal `tour` command; terminal samples open in a new tab, while the visual tour may replace this with an app action such as opening History, Workflows, Projects, Files, Options, or FAQ
- `illustration` - optional key for the visual tour renderer
- `requires` - optional exact config key such as `workspace_enabled` or `interactive_pty_enabled`; chapters are hidden when that feature is disabled

The `tour_enabled` setting in `config.yaml` is the kill-switch for tour entry points. Keep `tour.yaml` focused on chapter content.

---

## Command Registry Autocomplete

`app/conf/commands.yaml` stores each external command under `commands`, with policy, runtime adaptations, encrypted secret requirements, workspace file flags, and root-aware flag, argument, subcommand, and example hints. Optional local additions can live in `app/conf/commands.local.yaml`. A local entry with a new `root` adds a new command; a local entry with an existing `root` merges into the base command entry instead of replacing it wholesale.

```yaml
commands:
  - root: nmap
    category: Port & Service Scanning
    policy:
      allow:
        - nmap
      deny:
        - nmap -sU
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
      flags:
        - value: -sV
          description: Service/version detection
```

`requires_secrets` names encrypted session secrets that should be passed to the subprocess environment for that command root. Required missing secrets or a missing session identity block launch before the process starts. Optional missing secrets log a warning and let the command run without that env var; the `ipinfo` wrapper uses this for `IPINFO_TOKEN` because the CLI can still return limited unauthenticated output. Secret values are never rendered into command text. `inject_env` lets a registry entry store a friendly app secret name while exporting the vendor-required env var to the subprocess. `fallback_envs` lets users store an accepted native name instead; the VirusTotal CLI entry accepts either `VT_API_KEY` or `VTCLI_APIKEY` and always launches `vt` with `VTCLI_APIKEY`. The urlscan and Chaos CLI wrappers use `URLSCAN_API_KEY` and `PDCP_API_KEY` from the same vault path. Interactive PTY commands can't declare `requires_secrets`; the registry rejects that combination because the PTY path doesn't inject secret env vars.

Users manage matching values from **Options → Secrets** or with `secret set NAME` in the terminal. The browser prompt collects the value; the terminal command line contains only the secret name. Stored values are replace-only: list routes and the Options panel return names, consumer env bindings, and update times, never the saved value. A consumer env name can belong to only one secret in the current session, so a command that asks for `SHODAN_API_KEY` can't receive an arbitrary matching row.

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
- add `value_type: target` to workspace-required file/folder slots that should be replaced with live session workspace suggestions
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

The repo includes [`.env.example`](.env.example). Copy it to `.env` before starting Compose if you want local overrides:

```bash
cp .env.example .env
```

```env
APP_PORT=8888
WORKSPACE_ROOT=/tmp/darklab_shell-workspaces
# WEB_CONCURRENCY=4
# WEB_THREADS=4
# PROMETHEUS_MULTIPROC_DIR=/tmp/darklab_shell-prom
# COMPOSE_PROFILES=postgres
# DATABASE_BACKEND=postgres
# DATABASE_URL=postgresql://darklab:darklab_dev_password@postgres:5432/darklab_shell
# DATABASE_POOL_MIN=1
# DATABASE_POOL_MAX=5
# DATABASE_POSTGRES_JIT=false
# POSTGRES_DB=darklab_shell
# POSTGRES_USER=darklab
# POSTGRES_PASSWORD=darklab_dev_password
# SECRETS_MASTER_KEY=
# DOCKER_GELF_ADDRESS=udp://loghost.darklab.sh:12201/
```

| Variable | Used by | Purpose |
|----------|---------|---------|
| `APP_PORT` | Docker Compose, Dockerfile/entrypoint healthcheck path | App port exposed by the container and published by the base Compose file |
| `WORKSPACE_ROOT` | Docker entrypoint, Compose environment, Flask app | Path prepared by the container before dropping privileges. When set, it also overrides `workspace_root` in app config so Compose deployments only need one workspace path setting |
| `WEB_CONCURRENCY` | Gunicorn entrypoint | Number of Gunicorn worker processes |
| `WEB_THREADS` | Gunicorn entrypoint | Number of threads per Gunicorn worker |
| `NOTIFICATION_WORKER_ENABLED` | Docker entrypoint | Starts the outbound notification worker beside Gunicorn when set to `1` or left unset. Set to `0` to run only the web process |
| `PROMETHEUS_MULTIPROC_DIR` | Docker Compose, Flask app, Prometheus client | Optional override for `prometheus_multiproc_dir`. The app creates this scratch directory and exports it for `prometheus_client` multiprocess metrics |
| `COMPOSE_PROFILES` | Docker Compose | Optional comma-separated Compose profiles to enable. Set to `postgres` when you want the profile-gated Postgres service included without passing `--profile postgres` |
| `DATABASE_BACKEND` | Flask app | Optional override for `database_backend`. Use `sqlite` for the default local/single-user path or `postgres` for a Postgres-backed deployment |
| `DATABASE_URL` | Flask app | Optional override for `database_url`, normally a Postgres DSN when `DATABASE_BACKEND=postgres` |
| `DATABASE_POOL_MIN` / `DATABASE_POOL_MAX` | Flask app | Optional Postgres connection-pool bounds |
| `DATABASE_POSTGRES_JIT` | Flask app | Optional override for `database_postgres_jit`. Leave unset or `false` for lower-latency interactive app queries |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Docker Compose | Credentials used by the optional `postgres` Compose profile |
| `SECRETS_MASTER_KEY` | Flask app | Optional base64-encoded 32-byte master key for the encrypted per-session secrets vault. When unset, the app creates `<data_dir>/.secrets_master_key` with mode `0600` on first use and repairs broader existing key-file permissions to `0600` before use. If both env and file exist, the env value wins and the app logs `MASTER_KEY_FILE_IGNORED` |
| `DOCKER_GELF_ADDRESS` | Production Compose overlay | GELF log destination for Docker's logging driver |

If `WEB_CONCURRENCY` and `WEB_THREADS` are unset, the entrypoint defaults remain `4` workers and `4` threads. The production overlay currently defaults `WEB_CONCURRENCY` to `8` when that variable is not set.

---

## Database Backend Selection

SQLite is the default database backend and remains the recommended local/single-user path. Postgres is the production-scaling path for heavier deployments.

The app reads database settings from `app/conf/config.yaml`, then `app/conf/config.local.yaml`, then environment variables. Environment variables win. In Docker Compose deployments, prefer `.env` for backend selection because Compose uses the same file to decide which services to start.

For a Compose-managed Postgres deployment, set these values in `.env`:

```env
COMPOSE_PROFILES=postgres
DATABASE_BACKEND=postgres
POSTGRES_PASSWORD=<redacted>
DATABASE_URL=postgresql://darklab:<redacted>@postgres:5432/darklab_shell
```

`COMPOSE_PROFILES=postgres` enables the profile-gated `postgres` service without passing `--profile postgres` on every command. `DATABASE_BACKEND`, `DATABASE_URL`, `DATABASE_POOL_MIN`, `DATABASE_POOL_MAX`, and `DATABASE_POSTGRES_JIT` are read by the Flask app. `POSTGRES_PASSWORD` is read by the Postgres container at database initialization time.

If you run the app outside Compose, or you prefer file-based app config, the equivalent app-side settings are:

```yaml
database_backend: postgres
database_url: postgresql://darklab:<redacted>@postgres:5432/darklab_shell
```

Do not set conflicting values in `.env` and `config.local.yaml`: the environment wins, so `.env` will override `config.local.yaml`. If you use a Compose override file such as `docker-compose.local.yml` for bind-mounted workspaces, make sure it preserves the base service environment or repeats the database environment values; otherwise the container can start with the profile-gated Postgres service present while the app still sees the SQLite defaults.

Postgres connection notes:

- Keep `DATABASE_URL` aligned with any `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB` overrides.
- URL-encode special characters in the password before putting it in `DATABASE_URL`.
- App Postgres connections disable JIT by default because the UI favors predictable low-latency page requests over long analytical queries. Set `DATABASE_POSTGRES_JIT=true` only after measuring that your workload benefits from it.
- If `POSTGRES_PASSWORD` changes after the `postgres-data` volume already exists, Postgres does not automatically change the existing role password. Change the role password manually or recreate the volume intentionally.
- Keep the same `SECRETS_MASTER_KEY` or copied app-owned key file when migrating encrypted secrets.

For an existing SQLite install, run the offline migration before switching the app over. See [docs/postgres-migration.md](docs/postgres-migration.md).

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

## Docker Compose Files

The base [docker-compose.yml](docker-compose.yml) is the standalone local/test stack. It starts the shell service, Redis, the writable `/data` volume, tmpfs scratch space, default port binding, and the runtime capabilities needed by supported scanners. It also includes an optional profile-gated `postgres` service with a named volume and healthcheck for the production backend track:

```bash
docker compose --profile postgres up -d postgres
```

The app keeps using SQLite by default. The optional Postgres service supports production-style deployments and the opt-in Postgres test lane. When `database_backend` is `postgres`, startup runs the app-owned schema migrations and normal app database calls route through the Postgres pool.

The optional production overlay at [examples/docker-compose.prod.yml](examples/docker-compose.prod.yml) is layered on top of the base file:

```bash
docker compose -f docker-compose.yml -f examples/docker-compose.prod.yml up --build
```

The production overlay adds:

1. Docker GELF log transport for `shell`, `redis`, and the optional `postgres` service
2. Reverse-proxy environment values such as `VIRTUAL_HOST` and `LETSENCRYPT_HOST`
3. External Docker network usage instead of a direct host `ports:` binding
4. Deployment-specific container names
5. Optional Gunicorn sizing via `.env`
6. A persistent `./workspaces:/workspaces` bind mount for session Files
7. Scanner-friendly `ulimits` and network namespace sysctls

Application log format and Docker log transport are separate controls. To emit GELF-shaped application logs, set `log_format: gelf` in `config.yaml` or `config.local.yaml`. To send container stdout/stderr through Docker's GELF driver, use the production overlay and set `DOCKER_GELF_ADDRESS`.

---

## Workspace Storage Recipes

Files/workspace storage has two coordinated settings:

- `WORKSPACE_ROOT` in Compose is the path the Docker entrypoint prepares before dropping privileges. The app also treats it as the runtime `workspace_root` override, so Compose deployments only need this setting.
- `workspace_root` in `app/conf/config.yaml` or `app/conf/config.local.yaml` is still available for non-Compose runs or file-based config.

Do not set conflicting values in `.env` and `config.local.yaml`: the environment wins.

### Short-lived tmpfs storage

```yaml
# app/conf/config.local.yaml
workspace_enabled: true
workspace_backend: tmpfs
```

```yaml
# docker-compose.yml or an override
services:
  shell:
    environment:
      - WORKSPACE_ROOT=/tmp/darklab_shell-workspaces
```

### Persistent bind mount

The production Compose override uses `./workspaces:/workspaces` plus `WORKSPACE_ROOT=/workspaces`. Pair that with the volume backend in app config:

```yaml
# app/conf/config.local.yaml
workspace_enabled: true
workspace_backend: volume
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
      - WORKSPACE_ROOT=/workspaces
    volumes:
      - darklab_shell_workspaces:/workspaces

volumes:
  darklab_shell_workspaces:
```

Use the same app config as the bind-mount example:

```yaml
workspace_enabled: true
workspace_backend: volume
```

---

## Production Host Tuning

Wide scans can open many outbound sockets quickly. The production Compose overlay raises the container's file descriptor limit and sets network namespace sysctls, but a few host-level settings may still matter.

### Docker daemon file descriptor ceiling

Docker cannot grant a container a `nofile` limit higher than the daemon's own limit. If the daemon is still at a low default, the overlay's `ulimits.nofile` setting may not help.

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

Redis may warn that memory overcommit must be enabled. Apply immediately:

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

### Enable Files

```yaml
# app/conf/config.local.yaml
workspace_enabled: true
workspace_backend: tmpfs
```

For Compose runs, set `WORKSPACE_ROOT` when you want a path other than the default. The app uses that environment value as the runtime workspace root.

### Enable Interactive PTY

```yaml
# app/conf/config.local.yaml
interactive_pty_enabled: true
interactive_pty_max_runtime_seconds: 900
interactive_pty_max_concurrent_per_session: 4
interactive_pty_input_rate_limit_per_second: 10
interactive_pty_input_rate_limit_per_minute: 500
```

Multi-worker deployments should keep Redis enabled so PTY output, input, resize, and reattach state work across workers.

### Enable Diagnostics

```yaml
# app/conf/config.local.yaml
diagnostics_allowed_cidrs:
  - 192.0.2.10/32
trusted_proxy_cidrs:
  - 127.0.0.1/32
  - ::1/128
```

The same allowlist gates Prometheus metrics:

```yaml
# app/conf/config.local.yaml
metrics_enabled: true
prometheus_multiproc_dir: /tmp/darklab_shell-prom
metrics_histogram_buckets_run_duration: [0.1, 0.5, 1, 2, 5, 10, 30, 60, 300, 900, 1800, 3600]
metrics_histogram_buckets_http_duration: [0.005, 0.01, 0.05, 0.1, 0.5, 1, 5]
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

### Set The Default Theme

```yaml
# app/conf/config.local.yaml
default_theme: darklab_obsidian.yaml
```

Theme files live under `app/conf/themes/`. See [THEME.md](THEME.md) for theme authoring.

### Enable GELF Application Logs

```yaml
# app/conf/config.local.yaml
log_format: gelf
log_level: INFO
```

Use the production Compose overlay and `DOCKER_GELF_ADDRESS` if Docker should also ship container logs through the GELF driver.

### Customize FAQ, Welcome, Commands, and Workflows

- Add FAQ entries in `app/conf/faq.local.yaml`.
- Add welcome samples in `app/conf/welcome.local.yaml`.
- Add deployment-specific command registry entries in `app/conf/commands.local.yaml`.
- Add deployment-specific workflows in `app/conf/workflows.local.yaml` or through the in-app workflow editor.

---

## Related Docs

- [Default.md](.gitlab/merge_request_templates/Default.md) - default GitLab merge request template
- [ARCHITECTURE.md](ARCHITECTURE.md) - runtime layers, request flow, persistence, security, and app internals
- [CHANGELOG.md](CHANGELOG.md) - release-by-release changes
- [CONTRIBUTING.md](CONTRIBUTING.md) - local setup, test workflow, linting, branch workflow, and merge request guidance
- [CONTRIBUTORS.md](CONTRIBUTORS.md) - contributor and acknowledgement notes
- [DECISIONS.md](DECISIONS.md) - architectural rationale, tradeoffs, and implementation-history notes
- [DOCS_STANDARDS.md](DOCS_STANDARDS.md) - documentation structure, templates, and review rules
- [FEATURES.md](FEATURES.md) - full per-feature reference
- [README.md](README.md) - project overview, quick start, documentation map, and installed tools
- [THEME.md](THEME.md) - theme registry, token reference, and custom theme authoring
- [TODO.md](TODO.md) - open follow-ups, research notes, known issues, and future ideas
- [ARCHITECTURE.md → Atlas Export Schema](ARCHITECTURE.md#export-schema) - Session Entity Atlas CSV/JSONL export schema and filters
- [docs/api.md](docs/api.md) - headless API and bundled CLI usage guide
- [docs/external-command-integrations.md](docs/external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/postgres-migration.md](docs/postgres-migration.md) - offline SQLite-to-Postgres cutover helper and validation workflow
- [docs/storage-scaling.md](docs/storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [tests/README.md](tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
