# TODO

This file tracks open work, known issues, technical debt, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Ideas are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
- [Research](#research)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Ideas](#ideas)
- [Architecture](#architecture)

---

## Open TODOs

### Table-size diagnostics in `/diag`
- **Scope**
  - Add a storage breakdown to `/diag` so operators can see which tables and indexes are driving database growth.
  - Include a high-level summary for the major storage buckets: `runs`, `runs_fts*`, snapshots, run artifacts, findings, projects, labels/notes, and indexes.
  - Include content-size estimates for the fields most likely to grow quickly: `runs.output`, `runs.output_preview`, `runs.output_search_text`, and `snapshots.content`.
  - Show row counts beside size estimates so growth is understandable as both bytes and volume.
  - If SQLite `dbstat` is unavailable, show a clear "table page-size breakdown unavailable" message and still render content-size and row-count estimates.
- **Implementation notes**
  - Backend helper should live near the existing diagnostics code and use `dbstat` when `sqlite_compileoption_used('ENABLE_DBSTAT_VTAB') = 1`.
  - Keep the route read-only and cheap enough for occasional operator use; this does not need live polling.
  - Surface the same summary through a terminal built-in later if it fits naturally with `stats`, `retention`, or `limits`.

### External intel service integrations
- **Scope**
  - Three providers in v1: Shodan, VirusTotal, GreyNoise. Together they cover host/port intel, file/URL/domain reputation, and IP triage.
  - Two delivery passes:
    - CLI wrappers — `shodan`, `vt`, `greynoise` registered in `commands.yaml` with env injection from the encrypted secrets vault.
    - App-native `intel ip|domain|hash` built-in producing a uniform card across providers.
  - Provider abstraction with per-(session, provider) Redis token-bucket rate limiter and Redis-backed response cache with per-provider TTL.
  - Audit log of every lookup (session, run, provider, entity type, cache hit, http status). Never logs response bodies or API keys.
  - Entity-aware classifier hooks extract IPs, domains, hashes, and CVEs from any tool output as structured events for downstream consumers (Atlas, Findings, sidecar enrichment).
  - Share-redaction baseline marks intel response bodies as raw-only — excluded from snapshot permalinks and saved HTML/PDF exports.
  - Hard dependency: encrypted secrets vault is landed before any intel integration ships.
- **Provider access reference**
  - Categorize providers by API-key and payment requirements so the v1 ship list and future expansion stay calibrated to what users can actually adopt. Re-check at integration time — vendor terms change.
  - **Tier A — No key required (truly public, no signup):**
    - `crt.sh` — Certificate Transparency log search. Anonymous; rate limits are undocumented; avoid scheduling per-minute queries against the same domain.
    - BGPView — ASN / IP / prefix lookups; no auth.
    - Team Cymru — ASN-to-origin lookup via DNS/whois; no auth.
    - NVD CVE API — usable without a key at 5 requests per 30 seconds (rolling window). A free key raises the limit to 50 requests per 30 seconds.
    - Mnemonic PassiveDNS public API — 10 req/min, 1000/day without auth. Higher limits and private TLP data require a key requested by email.
    - HaveIBeenPwned Pwned Passwords (k-anonymity range endpoint) — free, no auth; separate from the paid breach-search API.
    - ExploitDB — public Git repo and `searchsploit` CLI; no API key, no rate limit.
  - **Tier B — Free API key (registration only, no payment):**
    - AlienVault OTX (LevelBlue) — free signup; 10k req/hr authenticated vs 1k unauthenticated.
    - Chaos (ProjectDiscovery) — free signup at `cloud.projectdiscovery.io`; required for both CLI and API; DNS API portions are invite-only.
    - Hybrid Analysis — free account; restricted API key by default. A one-time vetting form upgrades the key to allow submissions and downloads.
    - ThreatFox / abuse.ch — free Auth-Key via abuse.ch SSO under fair-use. Companies running commercial workflows are expected to move to the paid abuse.ch commercial subscription.
    - GreyNoise Community — free Community API key for limited community lookups. Current public docs describe 50 searches per week across Community API and Visualizer usage; unauthenticated access can be capped at 10 IP lookups/day. Enterprise tier is paid.
    - VirusTotal Public — free key with 500 req/day and 4 req/min. Strictly non-commercial use; commercial workflows must move to Premium.
    - AbuseIPDB free tier — 1,000 lookups/day on the free plan; verified webmasters get 3,000/day.
    - urlscan.io — free key strongly recommended; starting May 2026 some public endpoints reject unauthenticated requests entirely. Pro plan is paid for higher quotas, private scans, and richer search.
    - Censys Search — free signup grants 100 credits/month at no cost; covers host, web property, and certificate lookups.
    - NVD CVE API (with key) — free key raises the unauthenticated 5/30s window to 50/30s.
    - Vulners (free tier) — free signup; `/api/v3/search/id/` is credit-free for CVE enrichment; broader API consumes credits. Researchers and OSS projects can request a free research license.
    - SecurityTrails (free tier) — free key; documented quotas are inconsistent across vendor pages (50 queries/month entry vs 10k/month listed elsewhere). Verify the current dashboard quota at integration time.
    - IntelX free tier — 7-day trial downgrades to a free account with rate-limited access; product integration requires a paid license.
    - BuiltWith free — free API rate-limited to one request per second for basic tech-stack lookups.
  - **Tier C — Paid plan required for meaningful use or API access:**
    - Shodan — free account exists but issues no API credits. Membership is a one-time payment (~$50 standard, often promo at $5) and is the entry point for API use.
    - VirusTotal Premium — paid subscription; pricing not publicly listed; required for commercial use, sample download, behavior data, and higher quotas.
    - ZoomEye — API access is paid-only (one-time lifetime deals or subscription); free account is web-UI only.
    - DeHashed — API requires a paid subscription or credit pack (roughly $3 per 100 credits); no free API tier.
    - HaveIBeenPwned breach API — paid only; entry-tier Core starts at the "cost of a coffee", scales up to High-RPM commercial tiers.
    - IntelX commercial — required for product integration; plans start around $2,000+/month.
    - Recorded Future Triage cloud sandbox API — commercial license bundled with Threat Intelligence or SecOps modules; not a casual free integration.
    - Joe Sandbox — paid, enterprise-priced.
    - PassiveTotal / RiskIQ — paid; now under Microsoft Defender Threat Intelligence licensing.
    - Farsight DNSDB — paid commercial.
    - BuiltWith Advanced/Pro — $144/yr Advanced through $295–$495+/mo Pro; required for list-building or unlimited targets.
    - SecurityTrails paid plans — required for IP DSL queries, DNS/WHOIS history, and professional features.
  - **Tier D — Self-hosted or no vendor relationship:**
    - MISP — operator-deployed instance; auth uses the operator's own keys; no vendor relationship beyond the OSS project.
    - Wappalyzer community forks (`wappybird`, `wappalyzer-next`, `wappalyzer-cli`) — work locally without keys. Official OSS client was closed in 2023; the hosted Wappalyzer API is paid and key-gated, so any future Wappalyzer integration should target a community CLI rather than the hosted API.
  - **Defunct — do not target:**
    - BinaryEdge — standalone platform shut down March 2025; replaced by Coalition Control®. Remove from future-provider considerations.
  - **Plan-impact notes informed by this reference:**
    - The v1 ship list (Shodan, VirusTotal, GreyNoise) spans one paid-membership provider, one free-with-key public provider, and one free-with-key community provider — a balanced first set that exercises every secrets-vault and rate-limit path.
    - The encrypted secrets vault stays a hard prerequisite even though some providers are free, because every Tier B and Tier C provider stores a credential that must not appear in transcripts, history, or shares.
    - Tier A providers do not strictly require the vault. A "no-secret-required" early-value phase covering `crt.sh`, BGPView, Team Cymru, anonymous NVD, Mnemonic, and HIBP Pwned Passwords is viable as a phase 1.5 if the vault slips, and is the right home for "first-time users see immediate value before configuring secrets."
    - Tier C providers should never be added without a clear cost/benefit case and an operator opt-in, because users will hit paywalls during normal recon. Document the cost expectation in the Options → Secrets panel and the `intel` help text.
  - **Reference docs (re-check at integration time — vendor terms change):**
    - Snapshot date: 2026-05-13. Re-verify each row before adding the provider to `commands.yaml` or the `intel` built-in.
    - Tier A:
      - crt.sh — [Certificate Transparency overview (Wikipedia)](https://en.wikipedia.org/wiki/Certificate_Transparency); rate limits undocumented.
      - NVD CVE API (anonymous + with key) — [API Key Announcement](https://nvd.nist.gov/general/news/API-Key-Announcement).
      - Mnemonic PassiveDNS — [Public API docs](https://docs.mnemonic.no/api/services/pdns/01-public_api.html).
    - Tier B:
      - AlienVault OTX (LevelBlue) — [DirectConnect API](https://otx.alienvault.com/api).
      - Chaos (ProjectDiscovery) — [API Key docs](https://chaos.projectdiscovery.io/docs/api-key).
      - Hybrid Analysis vetting — [Issuing full API key for automated submissions](https://hybrid-analysis.com/knowledge-base/issuing-full-api-key-for-automated-submissions).
      - ThreatFox / abuse.ch — [Community API docs](https://threatfox.abuse.ch/api/).
      - GreyNoise Community — [Using the GreyNoise Community API](https://docs.greynoise.io/docs/using-the-greynoise-community-api).
      - VirusTotal Public vs Premium — [Public vs Premium API](https://docs.virustotal.com/reference/public-vs-premium-api).
      - AbuseIPDB — [API Plans & Pricing](https://www.abuseipdb.com/pricing).
      - urlscan.io — [API Documentation](https://urlscan.io/docs/api/). Note: starting May 2026 some public endpoints reject unauthenticated requests.
      - Censys Search — [Data Access Tiers and Entitlements](https://docs.censys.com/docs/data-access-tiers-entitlements).
      - Vulners — [2025 access update (CVE enrichment credit-free)](https://vulners.com/blog/access_update_2025/).
      - SecurityTrails — [Pricing](https://securitytrails.com/corp/pricing); quotas inconsistent across vendor pages, verify in-dashboard.
      - IPinfo free vs token — [Usage limit FAQ](https://ipinfo.io/faq/article/61-usage-limit-free-plan).
      - IntelX free / commercial — [API help](https://help.intelx.io/docs/api/).
      - BuiltWith free API — [Free API docs](https://api.builtwith.com/free-api).
    - Tier C:
      - Shodan Membership — [Account FAQ](https://help.shodan.io/the-basics/account-faq).
      - VirusTotal Premium — [Public vs Premium API](https://docs.virustotal.com/reference/public-vs-premium-api).
      - ZoomEye — [Pricing](https://www.zoomeye.ai/pricing).
      - DeHashed — [API page](https://dehashed.com/api).
      - HaveIBeenPwned breach API — [API key page](https://haveibeenpwned.com/API/Key).
      - Recorded Future Triage cloud sandbox — [Sandbox API docs](https://tria.ge/docs/).
      - BuiltWith Advanced/Pro — [Plans and Pricing Explained](https://kb.builtwith.com/general-questions/plans-and-pricing-explained/).
    - Tier D:
      - Wappalyzer OSS closure context — [HN discussion](https://news.ycombinator.com/item?id=37236746). Community forks: `wappybird`, `wappalyzer-next`, `wappalyzer-cli`.
    - Defunct:
      - BinaryEdge transition (shut down March 2025) — [Transition FAQ](https://www.binaryedge.io/pricing.html). Replaced by Coalition Control®.
- **Phase 0 - Existing-code integration check**
  - Confirm the encrypted secrets vault plan is landed; this plan is gated on it.
  - Audit `app/services/commands/registry.py` runtime env-build path for the secret injection hook.
  - Audit `app/core/output_signals.py` for the cleanest place to extract IP/domain/hash/CVE entities. Decide between extending existing event types or adding `entity_ip`, `entity_domain`, `entity_hash`, `entity_cve` events.
  - Verify the Dockerfile install pipeline can absorb new vendor CLIs (`shodan`, `vt-cli`, `greynoise`) under the scanner-user PATH.
  - Confirm `app/core/redaction.py` extension points support flagging response bodies as raw-only.
- **Phase 1 - Provider abstraction**
  - New `app/services/intel/` service:
    - `base.py` — `Provider` ABC with `lookup_ip`, `lookup_domain`, `lookup_hash`, `lookup_cve`, `rate_limit`, `cache_ttl`.
    - `rate_limiter.py` — Redis token-bucket keyed by `(session_token, provider)`.
    - `cache.py` — Redis-backed `(provider, entity_type, entity_value)` cache with provider-tunable TTL; cache miss falls through to provider; results are normalized before caching so cache hits cannot leak raw response shapes.
    - `audit.py` — emits `INTEL_LOOKUP` with `(session, run_id?, provider, entity_type, cache_hit, http_status)`. Never logs response bodies, API keys, or full entity lists.
  - Provider modules `shodan.py`, `virustotal.py`, `greynoise.py`. Each reads its key from the vault at call time, never caches keys beyond the rate-limit window, and returns a provider-normalized payload.
- **Phase 2 - CLI wrapper pass**
  - Install `shodan`, `vt-cli`, `greynoise` CLIs in the Dockerfile under the scanner-user PATH.
  - Register `commands.yaml` entries with allowed subcommands, allowed flags, and `requires_secrets`:
    - `shodan` → `SHODAN_API_KEY`.
    - `vt` → `VT_API_KEY`.
    - `greynoise` → `GREYNOISE_API_KEY`.
  - Verify deny-prefix coverage so these CLIs cannot reach loopback or escape the allowlist.
  - Add smoke-test fixtures for each CLI to the container smoke test corpus.
- **Phase 3 - App-native `intel` built-in**
  - New `app/services/commands/builtins_intel.py`:
    - `intel ip <ip>` fans out to Shodan + GreyNoise; uniform card shows ports/banners/CVEs and classification/confidence.
    - `intel domain <domain>` uses VirusTotal; uniform card shows reputation, recent URLs, WHOIS summary.
    - `intel hash <sha256|sha1|md5>` uses VirusTotal; uniform card shows verdict, scan engines, tags.
    - `intel cve <id>` is deferred to the future provider list.
  - Built-in output routes through the standard run-broker so it gets history persistence, autocomplete, and pipe support like any external command.
  - Browser-side card module: `app/static/js/features/intel/intel_card.js` with a provider-uniform layout shared across `intel` subcommands and any future enrichment surfaces.
- **Phase 4 - Entity-aware classifier hooks**
  - Extend `app/core/output_signals.py` to extract:
    - IPv4 and IPv6 (with configurable public-context filter that drops loopback/RFC1918 by default).
    - Hostnames / FQDNs (IDN-normalized, lowercased).
    - SHA256, SHA1, MD5 hashes (algorithm-tagged).
    - CVE identifiers (`CVE-YYYY-NNNNN`, uppercased).
  - Emit `entity_ip`, `entity_domain`, `entity_hash`, `entity_cve` events with confidence and source line.
  - These events are the foundation that the Session Entity Atlas plan and the Findings inbox consume.
- **Phase 5 - Sharing, redaction, audit, and tests**
  - `app/core/redaction.py` marks intel response bodies as raw-only. Snapshot permalinks of `intel` runs render a "Intel data omitted from share" placeholder where the card would normally appear. Saved HTML/PDF exports follow the same rule.
  - Backend coverage: provider mocks for each call path, rate-limit token-bucket behavior, cache hit/miss with TTL expiry, audit log shape, secrets-gate pre-launch error, normalized response schema parity across providers, entity extraction false-positive guardrails (loopback IPs, malformed CVE IDs, mid-string false matches).
  - Frontend coverage: intel card render parity across providers, missing-secret pre-launch error UX, cache-hit chip rendering, share-export omits intel sections.
  - Playwright: desktop and mobile flows for `intel ip`, `intel domain`, `intel hash` with mocked provider responses; one share-redaction flow proving intel content is omitted.
- **Open Decisions** (recommended answers below; review before implementation starts)
  - **Per-provider cache TTL defaults.** Question: how long does each provider's normalized response live in Redis? **Recommend:** Shodan IP 24h, Shodan host search 6h, VirusTotal domain 6h, VirusTotal file 24h, GreyNoise IP 1h. All overridable via `intel_cache_ttl_<provider>_<scope>` keys in `app/conf/config.yaml`.
  - **Rate-limiter bucket sizing.** Question: what bucket size + refill matches each provider's documented limits? **Recommend:** Shodan 1 req/sec (bucket 5, refill 1/sec); VirusTotal Public 4/min (bucket 4, refill 1 per 15s); GreyNoise Community conservative default of 50/week (bucket 50, refill 1 every 12,096s) with an optional stricter unauthenticated profile of 10/day. All provider buckets are config-overridable, and the source row is documented in code so future tweaks are auditable.
  - **Cache key canonicalization.** Question: are cache keys normalized the same way Atlas entities are? **Recommend:** **yes** — reuse the canonical-form rules the Atlas Phase 1 spec defines (lowercase IPv4/IPv6, IDN-normalized lowercase domain, lowercase algorithm-tagged hash, uppercase `CVE-YYYY-NNNNN`). Import the canonicalizer from `app/services/atlas/materializer.py` rather than duplicating.
  - **Pre-Atlas canonicalization location.** Question: if the intel plan ships before the Atlas, where do the canonicalization helpers live? **Recommend:** put them in `app/services/intel/canonical.py` and re-export from the Atlas materializer when it lands. Avoids a circular dependency or a copy.
  - **Private/loopback IPs in `intel ip`.** Question: does `intel ip 192.168.1.1` work? **Recommend:** **no** by default. Refuse with `IP <addr> is in a private/loopback range; intel providers cannot meaningfully classify it. Use --include-private if you really want to query.` Aligns with the classifier-extraction public-context filter.
  - **Normalized response schema.** Question: what shape does each provider return after normalization? **Recommend:** define a per-entity-type JSON schema in `app/services/intel/schema.py`:
    - `ip`: `{providers: {shodan: {ports[], banners[], cves[], last_update}, greynoise: {classification, name, last_seen}}, summary: {has_intel, providers_with_data, cache_status}}`.
    - `domain`: `{providers: {virustotal: {reputation, last_analysis_stats, recent_urls[], whois}}, summary: ...}`.
    - `hash`: `{providers: {virustotal: {verdict, last_analysis_stats, type_description, tags[], names[]}}, summary: ...}`.
    - The card module renders `summary` always, plus the matching provider panes. Document the schema in `docs/external-command-integrations.md`.
  - **CLI wrapper allowed-subcommand whitelist.** Question: which subcommands are allowed for each vendor CLI? **Recommend:**
    - `shodan`: `host`, `search`, `count`, `myip`. **Deny** `init` (would persist keys outside the vault), `download`, `parse`, `convert`, `domain`, `data`.
    - `vt`: `ip`, `domain`, `file`, `url`. **Deny** `search` in v1 because search-style queries can burn quota quickly or require higher-tier access; also deny `download`, `monitor`, `analyze`.
    - `greynoise`: `ip`, `quick`. **Deny** `setup` (key persistence), `query` until paid Enterprise plumbing is justified.
    - Document each in `commands.yaml` with explicit allowed flags. Reject any unlisted subcommand pre-launch.
  - **VirusTotal quota exhaustion behavior.** Question: what does `intel domain example.com` do when the 500/day VT quota is gone? **Recommend:** surface a clear error inline in the card (`VirusTotal quota exhausted for today — refresh after midnight UTC, or upgrade to Premium`) and store a negative-cache until the next UTC quota window when the provider response exposes a reset time. If no reset hint is available, cache for several hours rather than one hour so repeated probes do not hammer the provider. Keep raw HTTP-429 response out of transcripts.
  - **`intel hash` algorithm autodetect.** Question: how does the built-in determine which hash algorithm was passed? **Recommend:** autodetect by hex length (`32` → md5, `40` → sha1, `64` → sha256) **and** validate the input is hex; reject anything else with `Hash must be hex MD5/SHA1/SHA256`. No algorithm flag in v1.
  - **Partial-render when some keys are missing.** Question: if Shodan key is configured but GreyNoise is not, what does `intel ip` render? **Recommend:** render the Shodan pane normally and a "GreyNoise: not configured — `secret set GREYNOISE_API_KEY`" placeholder in the GreyNoise pane. The pre-launch error block-launch rule (from the secrets vault plan) only fires when **all** required providers are missing.
  - **Provider key discovery flow.** Question: when the user first runs `intel ip ...` with no keys, what's the UX? **Recommend:** the pre-launch error message includes both the `secret set NAME` shell hint **and** an `(Options → Secrets)` link — the link opens the Options modal at the Secrets section with the env name pre-filled.
  - **Audit log granularity for sidecar/auto-enrich paths.** Question: does future sidecar enrichment emit one `INTEL_LOOKUP` per entity per run, or batched? **Recommend:** v1 emits one row per provider call (cache hit or miss). If volume becomes a problem when sidecar enrichment ships, batch in that phase, not retroactively.
  - **CLI wrapper history persistence.** Question: do `shodan`/`vt`/`greynoise` runs land in normal history? **Recommend:** **yes** — they go through `/runs` like every other command. The response body is shown raw in the transcript; the redaction baseline marks intel response bodies raw-only so the share/permalink path drops them.

- **Future**
  - Tier A (no-key) early-value pass: `crt.sh`, BGPView, Team Cymru, anonymous NVD, Mnemonic PassiveDNS, HIBP Pwned Passwords. Ship before the vault if scheduling requires it, since none of these consume secrets.
  - Tier B (free-key) provider expansion: AlienVault OTX, Chaos (ProjectDiscovery), Hybrid Analysis, ThreatFox, AbuseIPDB, urlscan.io, Censys Search, Vulners (CVE enrichment), SecurityTrails free, IPinfo, BuiltWith free.
  - Tier C (paid-plan) providers — only behind an operator opt-in with documented cost expectation: VirusTotal Premium (commercial workflows), ZoomEye, DeHashed, HaveIBeenPwned breach API, IntelX commercial, Recorded Future Triage, PassiveTotal / Defender TI, Farsight DNSDB, BuiltWith paid.
  - Wappalyzer integration should target a community CLI fork (wappybird / wappalyzer-next / wappalyzer-cli) rather than the paid hosted API.
  - MISP integration if operators ask for it — operator-supplied URL plus an instance API key stored in the vault.
  - Sidecar enrichment panel — opt-in passive lookups fire alongside a scanner run and render in a collapsible side panel.
  - Pipe helpers `| enrich-shodan`, `| enrich-greynoise` via `app/services/commands/postfilters.py`.
  - Project workspace enrichment — pre-fetch passive snapshots when a host or domain is added as a project target.
  - Findings enricher — auto-attach intel snapshots to findings in the inbox or Atlas.
  - Workflow chain templates pairing native tools with intel lookups.
  - Defunct — do not target: BinaryEdge (shut down March 2025; replaced by Coalition Control®).

### Session Entity Atlas (entity-first triage surface)
- **Scope**
  - Top-level Atlas surface with first-class chrome treatment: desktop left-rail entry between History and Workflows, mobile menu item, dedicated keyboard shortcut. Not a stacked modal.
  - Tabs: Findings, Hosts/IPs, Domains, Hashes, CVEs, URLs. Each tab is a filterable, sortable list of distinct entities deduped across every saved run for the active session token.
  - Entity Detail side sheet: identity strip, intel snapshot card, source-run list with jump-to-line, findings on entity, labels and notes (reusing `ui_entity_metadata`), promote-to-project action.
  - Transcript ↔ Atlas wiring: tagged tokens click into entity detail, hover popover summarizes high-signal intel, "see in run" navigation jumps back to source line.
  - Findings tab absorbs the Findings triage inbox plan if both are scheduled — the inbox modal is retired in favor of the Atlas tab.
  - Project workspaces become a curation layer over the entity store; project_links are tags on entity rows, not parallel copies.
  - Schema cleanup is destructive. The run-centric `findings`, project-scoped `project_targets`, and `finding_targets` tables are dropped and replaced by an entity-first schema. Pre-release single-user app — no backwards-compatibility shim, no dual-write phase, no data backfill from legacy rows. The Findings triage inbox's `findings_inbox` table is also collapsed into the unified entity-owned `findings` table here.
  - Hard dependencies: entity-aware classifier hooks from the External intel service integrations plan are landed; encrypted secrets vault is landed for intel refresh actions.
- **Phase 0 - Existing-code integration check**
  - Confirm classifier entity events (`entity_ip`, `entity_domain`, `entity_hash`, `entity_cve`) are landed.
  - Audit `app/services/projects/workspace.py` and `app/services/projects/metadata.py` for label/note/finding/target storage that must be reused, not duplicated.
  - Audit `app/services/runs/comparison.py` for cross-run finding helpers the Atlas should reuse.
  - Audit `app/static/js/ui/ui_entity_metadata.js` to confirm label/note helpers work on Atlas entity types without changes.
  - Inventory every SQL call site against `findings`, `project_targets`, and `finding_targets` across `app/services/projects/workspace.py`, `app/services/projects/metadata.py`, and `app/blueprints/projects.py`. Expect ~30+ touch sites in `workspace.py` alone. The rewrite of these call sites lands with the schema migration in Phase 1, not as a follow-up.
  - Confirm the existing generic `project_links` table (`project_id, entity_type, entity_id`) can absorb entity-to-project tagging by introducing `entity_type='atlas_entity'`. This drops the previously proposed standalone `entity_project_links` table from the plan.
  - Lock the destructive-migration decision: pre-release, single-user app, so v1 drops `project_targets`, `finding_targets`, and the existing run-centric `findings` schema outright. No backfill, no compat shim, no dual-write phase. Document this in the migration commit message so any future operator with persisted data sees the warning.
- **Phase 1 - Backend contracts and storage**
  - **Destructive schema migration in `app/core/database.py`:**
    - **Drop tables:** `project_targets`, `finding_targets`, and the existing run-centric `findings` table.
    - **Drop indexes:** `idx_findings_session_run_created`, `idx_findings_target_created`, `idx_finding_targets_finding`, `idx_finding_targets_target_created`, `idx_finding_targets_run`, `idx_project_targets_project_type_value`.
    - **Keep unchanged:** `runs`, `run_output_artifacts`, `run_file_artifacts`, `snapshots`, `session_tokens`, `session_preferences`, `starred_commands`, `session_variables`, `user_workflows`, `recent_domains`, `projects`, `project_links`, `entity_labels`, `entity_notes`, `evidence_packages`.
    - **Reuse `entity_labels` and `entity_notes`** for Atlas entities by adopting `entity_type='atlas_entity'`. The tables are already keyed by `(session_id, entity_type, entity_id)` so no schema change is needed.
    - **Reuse `project_links`** for entity-to-project tagging with `entity_type='atlas_entity'`. Same generic `(project_id, entity_type, entity_id)` shape that already serves `run` and `finding` links — no parallel `entity_project_links` table.
  - **New `entities` table:**
    - `(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, occurrence_count, created)`.
    - `type` values: `ip`, `domain`, `url`, `hash`, `cve`. The legacy `host` target type is collapsed into `domain` unless the Phase 0 audit surfaces a meaningful distinction.
    - `canonical_value`: pre-normalized form (lowercase IPv4/IPv6, IDN-normalized lowercase domain, lowercase algorithm-tagged hash, uppercase `CVE-YYYY-NNNNN`, percent-encoded URL).
    - `signature_hash`: stable `sha256(type | canonical_value)` for dedup.
    - UNIQUE `(session_id, type, signature_hash)`.
    - Indexes: `idx_entities_session_type_last_seen ON entities (session_id, type, last_seen_at DESC)` for Atlas tab listing and indexed summary counts; `idx_entities_session_value ON entities (session_id, canonical_value)` for transcript-token hover lookups.
  - **New `entity_run_links` table:**
    - `(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count, PRIMARY KEY (entity_id, run_id))`.
    - Replaces the role of `seen_count` / `last_seen` / `source_run_id` formerly on `project_targets`.
    - Index: `idx_entity_run_links_run ON entity_run_links (run_id)` so run pruning can sweep entity links cleanly.
  - **New `entity_intel_snapshots` table:**
    - `(entity_id, provider, payload_json, fetched_at, ttl_seconds, http_status, cache_hit_count, PRIMARY KEY (entity_id, provider))`.
    - One row per (entity, provider). Refresh replaces in place.
    - Index: `idx_entity_intel_snapshots_fetched ON entity_intel_snapshots (fetched_at)` for TTL expiry sweeps.
  - **New entity-owned `findings` table (rewritten, not migrated):**
    - `(id, session_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, status_updated_at, fingerprint, created)`.
    - `status` values: `new`, `triaged`, `confirmed`, `false_positive`. **Triage state lives directly on `findings`** — the Findings triage inbox plan's separate `findings_inbox` table is collapsed into this row.
    - `entity_id` is nullable. Entity-backed findings point to an Atlas entity. Findings without a primary IP/domain/hash/CVE use `entity_id = NULL` and a stable `subject_key` such as `unscoped:<tool_root>:<normalized_signal_key>` so command-scoped warnings remain triageable instead of being dropped.
    - UNIQUE `(session_id, signature_hash)` for cross-run dedup. Signature: `sha256(tool_root | kind | severity | normalized_signal_key | entity.signature_hash_or_subject_key)`.
    - Indexes: `(session_id, status)`, `(session_id, entity_id, last_seen_at DESC)`, `(session_id, tool_root, last_seen_at DESC)`, `(session_id, severity, last_seen_at DESC)`.
  - **New `findings_occurrences` table (per-run sightings):**
    - `(finding_id, run_id, line_number, snippet, seen_at, PRIMARY KEY (finding_id, run_id, line_number))`.
    - Pruned with its source run; the parent `findings` row survives so the historical pattern is preserved.
    - Index: `idx_findings_occurrences_run ON findings_occurrences (run_id)` for prune sweeps.
  - **Service-layer rewrite (lands with the schema migration, not after):**
    - `app/services/projects/workspace.py` — rewrite every helper that reads or writes `project_targets`, `findings`, or `finding_targets`. Non-exhaustive list: `_row_to_target`, `_row_to_finding`, `_row_to_project_finding`, `_finding_target_ids_*`, `_finding_severity_from_text`, `_finding_fingerprint`, `_target_candidate_*`, `list_project_findings`, target listing/dedup/dismiss flows, and evidence-package selection move to `entities` / `findings` / `entity_run_links` reads with `project_links` joins for project membership.
    - `app/services/projects/metadata.py` — `entity_metadata_target_exists` and finding-existence checks switch to the new tables.
    - `app/blueprints/projects.py` — `/projects/<id>/targets*` becomes a typed view over `entities` filtered by `project_links`; `/projects/<id>/findings` reads from the rewritten `findings` table joined to `project_links`; `/findings/<id>/review` becomes a status-update route on the unified `findings` table; `/entities/run/<id>/findings` reads via `entity_run_links` join.
    - `app/services/commands/builtins_project.py` and any `project` built-in target lookups shift from `project_targets`-backed to entity-store-backed via `project_links`.
    - Evidence package builders that emit "targets" sections derive them from project-linked Atlas entities of type `host` / `domain` / `ip` / `url`.
  - **New `app/services/atlas/` service:**
    - `materializer.py` consumes entity events from `output_signals` at run-finalize. Idempotent on re-finalization. Computes stable canonical forms per type.
    - `lookup.py` exposes list/filter/detail queries used by both the Atlas and the rewritten Projects routes.
    - `intel_bridge.py` writes normalized intel payloads into `entity_intel_snapshots` when `intel` runs complete or when sidecar enrichment runs.
  - **Routes in new `app/blueprints/atlas.py`:**
    - `GET /atlas` tab summary (entity counts per type, computed from indexed `entities` rows unless profiling proves a rollup table is needed).
    - `GET /atlas/entities` paginated list with filters (`type`, `q`, `status`, `seen_in_last`, `has_intel`, `project_id`).
    - `GET /atlas/entities/<id>` detail with linked runs, intel snapshots, findings, labels, notes, project links.
    - `POST /atlas/entities/<id>/refresh_intel` triggers a fresh provider fetch via the intel service (rate-limited).
    - `POST /atlas/entities/<id>/project_links` promotes by writing into `project_links` with `entity_type='atlas_entity'`.
    - `DELETE /atlas/entities/<id>/project_links/<project_id>` unpromotes.
    - Findings-status routes live next to the rewritten Projects findings routes — there is one `findings` table, one set of status routes, used by both Atlas and Projects surfaces.
  - **Audit log:** `ATLAS_ENTITY_MATERIALIZED`, `ATLAS_INTEL_REFRESH`, `ATLAS_PROJECT_LINK_ADDED` (extends the existing `PROJECT_LINK_ADDED` family with `entity_type='atlas_entity'`), `ATLAS_PROJECT_LINK_REMOVED`.
- **Phase 2 - Materialization**
  - Hook into the run-finalize path in `app/blueprints/run.py` after classification. Lazy extraction — only process classified entity events, never raw output lines, so cost scales with distinct entities rather than output volume.
  - No backfill is shipped. Pre-release single-user app drops all historic findings/targets in Phase 1 and starts the entity store fresh from the first new run finalized after the migration. Saved runs from before the migration have no Atlas entities; entity-tab counts simply omit them.
  - Retention pruning rule: `entity_run_links` and `findings_occurrences` rows follow their source run; `entities` and `findings` rows survive after the last link is pruned so the historical pattern is preserved.
- **Phase 3 - Browser surface**
  - New `app/static/js/features/atlas/`:
    - `atlas_overlay.js` — full-surface controller wired into the desktop rail and mobile menu, not stacked over History.
    - `atlas_tabs.js` — tab rendering and filter state.
    - `atlas_entity_detail.js` — side sheet with identity, intel card, source runs, findings, labels/notes, project links.
    - `atlas_transcript_links.js` — tagged-token hover popover and click/long-press handler.
  - New `app/static/css/features/atlas.css`.
  - Entry points: left-rail entry between History and Workflows; mobile menu item; keyboard shortcut documented in the `?` overlay; History row context menu "Open entities"; Run Details linked-entities sidebar; Projects modal "Open in Atlas (filtered to this project)".
  - Reuses `ui_dismissible`, `ui_focus_trap`, `ui_outside_click`, `ui_pressable`, `ui_entity_metadata`, and the existing bulk-action toast contract.
  - Hover popover shows the high-signal summary: type, occurrence count, last seen, GreyNoise verdict (if any), Shodan port count (if any), VT positives (if any).
- **Phase 4 - Transcript wiring**
  - Output renderer in `app/static/js/output.js` decorates classifier-extracted entities as tagged spans.
  - Click opens entity detail; long-press / right-click opens a shared action menu (label, note, promote, copy, lookup intel, open in Atlas, see in run). The action menu is the same primitive flagged for the project-workspace transcript right-click idea — that work and this plan share the implementation.
  - "See in run" in entity detail focuses the History drawer or Run Details on the source line with scrollIntoView.
- **Phase 5 - Findings tab absorption**
  - The Findings tab implements the full triage queue described in the Findings triage inbox plan (status transitions, dedupe, filters, project pinning, bulk status update).
  - If the standalone inbox modal has already shipped, its entry points migrate to the Atlas Findings tab and the standalone modal is retired; the backing service and routes are reused unchanged.
  - If the Atlas ships first, the inbox plan does not ship as a separate modal — its scope is absorbed entirely here.
- **Phase 6 - Projects as curation, not gating**
  - Adding an entity to a project writes a row in the existing generic `project_links` table with `entity_type='atlas_entity'`. No new project-link table is introduced.
  - The `project_targets` table is dropped in Phase 1 and not preserved. The "Targets" view in the Projects modal becomes a server-side filter over project-linked Atlas entities of type `host` / `domain` / `ip` / `url`, computed in the rewritten `/projects/<id>/targets` route.
  - Projects modal Findings tab reads from the unified `findings` table joined to `project_links` so it cannot drift from the Atlas Findings tab — there is one findings store, not two.
  - Engagement report builder (separate idea) reads "targets", "findings", and "intel observations" sections from the entity store via the same Atlas service the Projects routes use.
- **Phase 7 - Sharing, redaction, and exports**
  - Entity rows never appear in snapshot permalinks; only the source-run transcript does. Existing share-redaction handles transcript content.
  - Atlas export options ship in v1:
    - Per-entity CSV/JSONL with selected fields.
    - Per-project filtered entity export for engagement handoff.
  - Honors share-redaction baseline so redacted exports omit raw intel response bodies.
- **Phase 8 - Feedback and tests**
  - Empty-state UX: runs producing zero entities are normal and do not surface as warnings. Saved runs from before the migration also produce no Atlas rows and must not appear as broken.
  - Backend coverage: destructive migration drops the legacy `project_targets`, `finding_targets`, and run-centric `findings` tables and re-initializes the new schema from scratch; deduplication signature stability across every entity type; unscoped finding materialization without an entity row; materialization idempotency on re-finalization; intel snapshot freshness and TTL expiry behavior; `project_links` `entity_type='atlas_entity'` round-trip (promote/unpromote); label/note helper reuse against entity rows; cross-session rejection; retention pruning preserves `entities` and `findings` rows when their last run-link or occurrence row is pruned; one consolidated `findings` table services both Projects routes and Atlas routes without divergence.
  - Service-layer regression coverage: rewritten Projects routes (`/projects/<id>/targets*`, `/projects/<id>/findings`, `/findings/<id>/review`, `/entities/run/<id>/findings`) return parity-equivalent shapes to the pre-migration responses where possible, so the Projects modal UI does not need to be reskinned just because the backing store changed.
  - Frontend coverage: tab filter combinations, entity detail render with and without intel snapshots, transcript hover popover and action menu, see-in-run navigation, project promotion and unpromotion, rail entry plus mobile menu integration, keyboard shortcut, empty-state rendering, Projects modal Targets and Findings tabs continue to function against the rewritten routes.
  - Playwright: one desktop and one mobile flow covering scan → atlas → entity detail → intel refresh → promote-to-project → see-in-run → unpromote, plus one regression flow exercising the Projects modal Targets/Findings tabs end-to-end against the rewritten store.
- **Open Decisions** (recommended answers below; review before implementation starts)
  - **Entity ID format.** Question: what shape does `entities.id` take? **Recommend:** `ent_<12-hex>` (mirrors the existing `run-<hex>` / project-id conventions); generated via the same `secrets.token_hex(6)` helper. Cheap to grep, short enough for transcripts.
  - **`ip` type covers IPv4 and IPv6.** Question: do v4 and v6 share `type='ip'` or split into `ipv4` / `ipv6`? **Recommend:** **single `ip` type**. `canonical_value` carries the normalized form (`192.0.2.1` or `2001:db8::1`). Saves a tab and matches how the intel providers treat them. The intel response can carry a `family` field if a card ever needs to differentiate.
  - **`host` vs `domain` collapse.** Question: does the legacy `host` target type stay as a distinct Atlas entity type? **Recommend:** **no** — collapse `host` into `domain` at materialization time. Phase 0 audit should confirm `host` is just an old name for `domain` in the existing schema. If a meaningful distinction surfaces (e.g., "host" meant FQDN-with-port-pair while "domain" was zone-only), keep both and document the rule.
  - **Hash algorithm tag format.** Question: how is the algorithm tag carried in `canonical_value`? **Recommend:** prefixed `sha256:<hex>`, `sha1:<hex>`, `md5:<hex>`. Keeps `canonical_value` a single column; the algorithm survives round-trips and is greppable.
  - **URL canonical form.** Question: what canonicalization rules apply to URL entities? **Recommend:** WHATWG URL parser normalization — lowercase scheme + host, default port stripped, fragment dropped, trailing `/` stripped on path-only URLs, query params preserved in given order. Reject URLs > 2048 bytes at materialization (warn in audit log; do not block the run).
  - **`canonical_value` length cap.** Question: max bytes for any entity's canonical value? **Recommend:** 2048 bytes UTF-8. URLs hit this first; domains/hashes/CVEs are far below. Reject longer entities at materialization with a one-line audit log entry; do not block the surrounding run.
  - **`entity_run_links.occurrence_count` semantics.** Question: counts what — total classifier emit events, or distinct line numbers? **Recommend:** total emit events. `entities.occurrence_count` is the sum across runs. Cheap to maintain; matches the inbox plan's convention.
  - **Tab summary computation cost.** Question: how does `GET /atlas` compute entity counts per type? **Recommend:** start with indexed `COUNT(*) GROUP BY type` over `(session_id, type)` rather than adding a rollup table. This keeps the schema simpler and avoids consistency bugs during prune/recalc. Add an `entity_type_counts` rollup only if profiling shows the indexed count is too slow.
  - **Pagination size and ordering.** Question: default page size and sort? **Recommend:** 50 per page, sorted by `last_seen_at DESC`. Filter chips override. The Findings tab uses the explicit status-priority ordering defined below, then `last_seen_at DESC`.
  - **Atlas keyboard shortcut chord.** Question: which keys open the Atlas? **Recommend:** `Alt+A` (desktop) and document in the `?` overlay. `Alt+H` is History today; `Alt+W` could be Workflows; `Alt+A` is free and mnemonic.
  - **Transcript entity decoration mechanism.** Question: how does the frontend know which output tokens are tagged entities? **Recommend:** backend emits per-line entity offsets in the SSE event metadata (e.g., `{entities: [{type, value, start, end}]}`). Frontend wraps spans cheaply. Re-scanning text client-side would duplicate classifier logic.
  - **Findings without a primary entity.** Question: what happens when a classifier emits a finding that has no extractable IP/domain/hash/CVE? **Recommend:** keep it in the Atlas Findings tab as an unscoped finding with `entity_id = NULL` and a stable `subject_key`. Do not create a synthetic Atlas entity in v1, so entity counts stay meaningful while command-scoped warnings remain visible and triageable.
  - **Project-promotion `source` value.** Question: what value lands in `project_links.source` when promoting from Atlas? **Recommend:** `atlas_promote` (joins the existing `manual` / automated-source family). Document in `app/services/projects/contracts.py`.
  - **Promote-to-project idempotency.** Question: what does promoting an already-linked entity do? **Recommend:** idempotent no-op — return `200 {already_linked: true}` rather than 4xx. Matches the bulk-actions plan's link semantics.
  - **Per-entity export schema.** Question: which fields appear in the CSV/JSONL export? **Recommend:** `id, type, canonical_value, first_seen_at, last_seen_at, occurrence_count, labels, notes, project_names, intel_providers_with_data`. Define a stable v1 schema doc in `docs/atlas-export.md` so consumers can rely on it.
  - **`output.js` decoration for legacy / pre-migration runs.** Question: do saved runs from before the migration get retroactive entity tagging on reopen? **Recommend:** **no** — the SSE pipeline only emits entity offsets for new runs after the classifier change ships. Reopened legacy runs render as plain text. Future work can add a backfill that re-classifies old transcripts.
  - **Findings emitter for the unified `findings` table.** Question: where does the materializer that writes `findings` rows live? **Recommend:** `app/services/atlas/materializer.py` writes both `entities` and `findings` in the same transaction at run-finalize time. The proposed `app/services/findings/inbox.py` from the Findings triage inbox plan is **not** created when the Atlas ships first.
  - **Run-prune sweep order.** Question: when a run is pruned, what's the cascade order? **Recommend:** `findings_occurrences` → `entity_run_links` → recalc `entities.occurrence_count` / `entities.last_seen_at`. Document in the pruning helper. `entities` and `findings` rows survive even after their last link is pruned.
  - **Atlas Findings tab sort default.** Question: default sort when entering the Findings tab? **Recommend:** explicit status priority (`new`, `triaged`, `confirmed`, `false_positive`) then `last_seen_at DESC` within each triage bucket. Do not rely on lexical `status ASC`, which would put the statuses in the wrong order.

- **Future**
  - Entity graph view (visual link map across hosts, domains, hashes, CVEs).
  - Saved Atlas views (named filter combinations).
  - Atlas FTS search across entity values, labels, and notes.
  - Auto-promote rules — entities matching saved patterns auto-promote into a project.
  - Time-travel view: "what did the Atlas look like a week ago?" using retained snapshots.
  - Side-by-side entity comparison (their runs, findings, intel snapshots).
  - Cross-session Atlas view for operators managing multiple sessions or shared infrastructure.
  - Atlas import from external triage tools.

### Findings triage inbox

- **Scope**
  - Cross-run queue of every classifier-emitted finding and warning for the active session, with stable dedupe across runs by finding signature.
  - Per-finding triage status: `new`, `triaged`, `confirmed`, `false_positive`.
  - Filters: severity, status, tool, project, time range, free-text.
  - Detail side sheet with occurrence list, source-run permalinks, line snippets, and pin-to-project action.
  - Bulk status updates with the same partial-success and `results[]` contract as the History multi-select bulk-actions plan.
  - Standalone modal in v1. If the Session Entity Atlas plan ships, this scope folds into the Atlas Findings tab and the standalone modal is retired.
- **Phase 0 - Existing-code integration check**
  - Audit `app/core/output_signals.py` for the finding event shape, persistence point in run finalization, and severity/kind taxonomy.
  - Audit the existing Projects modal Findings tab for filter UI and row patterns to reuse.
  - Confirm dedupe scope: per-session-token (recommended) so cross-tool overlap is captured.
  - Confirm retention-pruning interaction so inbox rows are not orphaned when their source runs are pruned.
- **Phase 1 - Backend contracts and storage**
  - The `findings_inbox` and `findings_inbox_occurrences` tables described here are the **standalone-shipping schema**. If the Session Entity Atlas plan ships first or alongside, the inbox tables are not created — the Atlas's unified entity-owned `findings` and `findings_occurrences` tables carry triage state directly, and this plan's routes are rewired to read from those instead. The two schemas are intentionally column-compatible so this collapse is a route-level swap, not a data migration.
  - New `app/services/findings/inbox.py` materializer that runs at run-finalize, consumes classified signals, computes a stable signature, and upserts inbox rows. Signature: `sha256(tool_root | normalized_kind | normalized_target | severity | normalized_signal_key)`; normalization rules are documented in the module and shared with the frontend. `normalized_signal_key` comes from the classifier fingerprint when available, then a normalized title/subtype, then a normalized snippet fallback so distinct findings on the same target do not collapse into one row.
  - New SQLite tables (standalone path only):
    - `findings_inbox` `(id, session_token, signature_hash, tool_root, kind, severity, first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, status_updated_at)`.
    - `findings_inbox_occurrences` `(finding_id, run_id, line_no, snippet, seen_at)` with retention pruning tied to run pruning.
  - Routes in new `app/blueprints/findings_inbox.py`:
    - `GET /findings/inbox` paginated list with filters.
    - `GET /findings/inbox/<id>` detail with occurrences.
    - `PUT /findings/inbox/<id>/status` single-status update.
    - `PUT /findings/inbox/status` bulk-status update with `{finding_ids: [...], status}`. Same `results` and `reason` contract as the bulk-actions plan; max bulk size 100; `4xx` overflow.
    - `POST /findings/inbox/<id>/pin` promotes into a project as a structured finding via existing `services.projects.workspace` helpers.
  - Audit log: `FINDING_STATUS_CHANGED`, `FINDINGS_BULK_STATUS_CHANGED`, `FINDING_PINNED_TO_PROJECT`.
  - Materialization is idempotent on re-finalization; signatures collapse duplicates.
- **Phase 2 - Schema migration and backfill**
  - Migration in `app/core/database.py` with indexes on `(session_token, signature_hash)` and `(session_token, status)`.
  - Backfill helper walks existing saved runs on first deploy and materializes findings.
  - Pruning rule: occurrence rows follow their source run; inbox rows survive after the last occurrence is pruned (the pattern is the value).
- **Phase 3 - Browser surface**
  - New `app/static/js/features/findings/findings_inbox.js` and `app/static/css/features/findings_inbox.css`.
  - Top-level modal with sticky filter row and paginated row list. Row chrome: severity badge, kind, normalized target, occurrence count, first/last seen, status chip.
  - Detail side sheet: occurrence list with permalinks and snippet excerpts, status controls, pin-to-project picker (active-project-first ordering).
  - Entry points:
    - Desktop chrome rail entry with unread `new` count badge.
    - Mobile menu item.
    - History row action: "Findings" opens inbox prefiltered to that run.
    - Run Details: "Open in inbox" prefiltered to the run.
    - Projects modal: "Open in inbox" prefiltered to the project.
  - Reuses `ui_dismissible`, `ui_focus_trap`, `ui_outside_click`, `ui_pressable`, `ui_entity_metadata`, and the existing bulk-actions toast and `results[]` rendering.
- **Phase 4 - Cross-surface integration**
  - `false_positive` status propagates to Run Details and the project Findings tab as a greyed-out row treatment.
  - Project-pin creates a structured finding using existing `services.projects.workspace` writes; the pinned finding carries the inbox `finding_id` as a back-link.
  - `?` shortcuts overlay gains "Open Findings inbox".
  - Terminal-native built-ins: `findings list`, `findings show <id>`, `findings status <id> <state>`.
- **Phase 5 - Feedback and tests**
  - Bulk status update uses the existing bulk-result toast policy (sticky when non-zero `rejected`/`not_found`).
  - Backend coverage: signature stability across runs of the same tool/target/severity/signal key, distinct-finding separation when target/tool/severity match, re-finalize idempotency, status transition state machine, backfill correctness, bulk status update with mixed not_found/rejected entries (with inline reasons), project-pin creates structured finding and links back, cross-session rejection, max-bulk-size rejection.
  - Frontend coverage: filter combinations, single and bulk status changes, project pin flow, occurrence list rendering, prefiltered entry-point parity (History, Run Details, Projects), unread badge accuracy after status changes.
  - Playwright: one desktop and one mobile flow covering triage end-to-end (open, filter, change status, pin, see status reflect in Run Details).
- **Open Decisions** (recommended answers below; review before implementation starts)
  - **Signature `normalized_target` source.** Question: which "target" gets hashed into the signature — the run's command target (via `extract_target`) or an entity extracted from the finding line? **Recommend:** the run's command target (canonical form). Keeps dedup stable across many similar lines from the same scan; entity-line extraction comes later via the Atlas plan. If a finding has no command target, use the empty string but still include `normalized_signal_key` so unrelated command-scoped findings do not collapse together.
  - **`normalized_kind` source.** Question: where does `kind` come from? **Recommend:** prefer the most specific classifier-provided kind/subtype/fingerprint family. Fall back to the existing `output_signals` event `cls` field (`finding`, `warning`, `error`, `summary`) only when no subtype exists. Document the canonical kind taxonomy in `app/core/output_signals.py`.
  - **Severity taxonomy.** Question: what severity values does the inbox accept and filter on? **Recommend:** `{critical, high, medium, low, info}`. If `output_signals` does not currently emit a severity field, derive at materialization time from the kind (`error` → high, `warning` → medium, `finding` → medium, `summary` → info) and persist on the inbox row. Document the derivation.
  - **Status transition graph.** Question: are arbitrary status transitions allowed, or only certain edges? **Recommend:** any → any in v1, audit-logged via `FINDING_STATUS_CHANGED`. Avoids modal-state UX where users get stuck in a state and can't revert. State-machine constraints are future work if abuse appears.
  - **Backfill scope.** Question: how far back does the first-deploy backfill walk? **Recommend:** every saved run for the session. Retention pruning already bounds the historic set, so the cost is bounded; partial backfill creates a confusing inbox.
  - **Pin-to-project payload.** Question: what does the structured `findings`-row look like when an inbox row is pinned? **Recommend:** copy the latest occurrence's `snippet` into `raw_line`, copy `line_no` into `line_number`, populate `findings.fingerprint` with the inbox `signature_hash` (so the project finding back-links to the inbox row), set `findings.review_state = 'new'`. Document the column mapping in the `pin` route docstring.
  - **Unread badge counting rule.** Question: what does the rail badge actually count? **Recommend:** count of inbox rows with `status = 'new'`. Simple, no per-user read-state to track. Future work can introduce per-user read marks if needed.
  - **Prefilter URL parameter shape.** Question: how do "open inbox prefiltered to this run" links express the filter? **Recommend:** query params on the inbox modal launch — `?run_id=<id>`, `?project_id=<id>`, `?status=new`. The inbox controller renders matching chips at the top so the prefilter is visible and removable.
  - **Signature status persistence.** Question: when a user marks a signature `false_positive`, do future identical-signature occurrences inherit that status? **Recommend:** yes, by preserving the existing row's `status` when a known signature reappears. Materialization writes a fresh row only if the signature does not already exist; if it exists, only `last_seen_at` / `occurrence_count` / `last_run_id` update. This is not a separate suppression-rules engine — future suppression rules layer on top of this signature-status behavior.
  - **Pagination size and ordering.** Question: default page size and sort order? **Recommend:** 50 rows per page, sorted by `last_seen_at DESC` by default. Filter chips override (e.g., severity filter sorts within filtered set). Mirrors history-drawer defaults.
  - **Atlas-collapse routes.** Question: when the Atlas ships, does the inbox blueprint stay registered or is it deleted? **Recommend:** the inbox blueprint is deleted; its routes are rewritten under the Atlas's `/findings/*` and `/atlas/*` namespaces. The inbox modal entry points redirect to the Atlas Findings tab. Spell this out in the absorption commit message so callers know to update their links.

- **Future**
  - Bulk pin (pin many findings into one project in one click).
  - Saved triage views (named filter combinations).
  - Per-finding labels and notes via `ui_entity_metadata` helpers.
  - Suppression rules — auto-mark newly seen signatures as `false_positive` based on regex, tool root, or classifier subtype.
  - Export inbox snapshot as CSV/JSONL.
  - Cross-session triage view for operators managing multiple sessions.
  - Folded into the Session Entity Atlas Findings tab if the Atlas plan ships.

### Future Project Workspace enhancements
- **Security and lifecycle**
  - Validate `workspace_file` entity ownership during session migration, or document that labels/notes on workspace-file paths can drift when a migrated token lands in a session with a different file at the same path.
  - Add a terminal-native `project rename <name-or-id> <new-name>` command so CLI users can rename projects without opening the modal.
  - Add parallel PATCH routes for partial project and target updates if the project workspace API ever becomes more than a trusted browser-only surface.
- **Code organization**
  - Split `project_workspace.py` into focused modules once the surface settles. Natural boundaries are core project CRUD, entity metadata, findings, packages, and session migration.
  - Move Projects modal rendering and event wiring out of `shell_chrome.js` into a dedicated project workspace browser module.
  - Reduce repeated `projects.py` route boilerplate with small serialization/404 helpers.
- **Capture, tagging, and navigation**
  - Expose `Add label`, `Add note`, `Open in project`, and `Add as project target` on transcript right-click or signal-tagged token long-press; this should replace the removed Projects-modal quick-add target flow.
  - Add contextual quick-add target entry points from history rows and workspace file previews once the shared action-menu pattern exists.
  - Consider a per-project current-target sub-state so `${target}` placeholder substitution can follow sustained work on a single host.
  - Decide whether `host` remains a visible target type or is retained only as a backend compatibility value.
  - Add a compact project switcher near the prompt with recently used projects and a Create New action.
  - Show run, finding, artifact, and package counts on project-list rows so project scale is visible before opening each project.
- **Future-state mobile polish**
  - Add OS Back / browser Back support with `history.pushState` after the base sheet navigation is stable.
  - Add a project search/filter input above the mobile list once project counts justify it.
  - Consider swipe gestures for target and finding rows only after overflow-menu interactions are shipped and tested.
- **Findings and comparison**
  - Extend the Findings tab filters beyond target/run/review state to command root, severity, scope, labels, and note state.
  - Add multi-select plus bulk review actions for high-volume finding review.
  - Prefetch finding counts and severity distribution so tab labels can show useful state such as unreviewed/high counts without opening the tab.
  - Extend comparison beyond run-to-run finding/artifact diffs to snapshots and package artifacts.
- **Evidence packages**
  - Materialize evidence package archives at creation time if byte-for-byte repeat downloads become important.
  - Make package presets config-driven so new bundle profiles, such as internal review or external handoff, can be added without code changes.
  - Add richer per-finding remediation or verification fields if findings evolve beyond raw output capture.
  - Add richer target references in package exports, including derived relationships that are not directly visible in selected finding text.
  - Add richer provenance metadata and round-trip import hints for labels, notes, targets, findings, and packages.
  - Explore fuller direct template reuse for package run transcript pages without reintroducing app-hosted asset links.
  - Add redacted text/JSON derivatives for safe artifact types before allowing raw artifact inclusion in redacted packages.
  - Add richer redaction previews and per-item redaction warnings for package creation.
  - Add async package build progress for large Full Archive exports so long builds do not feel like stalled requests.
  - Add generated re-package names that preserve the original selection while incrementing the package label or timestamp.
  - Move package HTML rendering toward shared Jinja autoescape paths so package output escaping is template-owned instead of manual per-call escaping.
- **Retention and mobile**
  - Finish pruning/retention behavior for project-linked runs and run-scoped artifacts.

### Future interactive PTY enhancements
- **Future lifecycle and resilience**
  - Consider auto-displacing prior live attaches when a new browser client attaches to the same PTY run. When `active_run_claim_owner` flips the internal ownership marker to a different `client_id`, publish a single `displaced` event on the PTY stream so the prior tab can close its modal cleanly and append one notice such as `[interactive PTY moved to another tab]`. Skip same-client reconnects so the event only fires when the live view genuinely moves to a different browser context. With this in place, the remaining per-keystroke `[interactive PTY input ignored: ...]` notices in `_ptySendInput` could become rare edge-case failures instead of common transcript noise.
  - Revisit transport after real usage. The current pass uses Redis-brokered SSE plus narrow POST input/resize endpoints to avoid adding a WebSocket server dependency; WebSocket may still be useful if latency, throughput, or bidirectional control behavior becomes a real limitation.
- **Future security**
  - Defer asciinema-style raw byte replay and input auditing until real usage shows they are needed.
- **Future architecture**
  - Split `pty.js` into smaller modules once PTY work resumes in depth. Natural boundaries are orchestration/command detection, modal wiring/timer/status, and xterm session/resize handling.
  - Split `pty_service.py` once more PTY server behavior accumulates. Capture, run lifecycle, Redis stream transport, control-stream draining, and metadata storage are natural module boundaries.
  - Consider dropping the base `#pty-overlay` from `index.html` and building every PTY modal through `_ptyBuildOverlay`. Tab overlays are now normalized and reused, so this is cleanup rather than a leak fix; the benefit would be removing the remaining ID/class selector duality in `_ptyModalEls`.
  - Verify or document PTY modal positioning and mobile-sheet behavior with the overlay scoped inside `.tab-panel`. PTY startup is disabled on mobile, but the shared modal/mobile-sheet CSS still deserves a viewport sanity check if the modal layout changes again.
  - Introduce a small PTY host interface object for browser tests. `pty.js` still reaches into many runner globals; a host object would make tests less brittle and reduce global-surface coupling.
  - Add broader browser unit coverage for PTY tab state transitions and disabled normal-terminal behaviors as future PTY features are added.
- **Future polish and operational visibility**
  - `_PTY_INPUT_MAX_BYTES`, `_PTY_BUFFER_LIMIT`, `_PTY_CONTROL_POLL_SECONDS`, `_PTY_SNAPSHOT_FALLBACK_ENTRY_LIMIT`, and similar tunables are module constants. Move to config so deploys can tune without a rebuild.
  - Add metrics covering concurrent PTY count, average and p95 duration, total input bytes, dropped input bytes, and control queue depth. Expose them through the existing `/diag` surface so operators have visibility comparable to other run paths.
  - The reader loop polls Redis every 200 ms via `xread block=1` for control events. With many concurrent PTYs this is wasted ops. Switch the control channel to Redis Pub/Sub (or a longer block window) so idle PTYs cost zero ops while output latency stays unaffected.
  - Surface snapshot age on the reattach payload. `_load_pty_snapshot` strips `created_at` before returning, so the frontend cannot tell whether the snapshot is fresh or 20+ seconds stale. Return the age and let the frontend show `[reattached - snapshot was Ns old]` when it crosses a threshold, so users know the screen they see may not match what the PTY is currently rendering.
  - Skip the unconditional `_store_pty_snapshot(run, force=True)` in `pty_run_snapshot` when the request hits the worker that owns the PTY. The route already returns the live in-memory payload to the caller, and the next reader-loop tick will publish to Redis naturally; the extra Redis SET costs one round-trip per attach for cross-worker freshness that is rarely consumed.
  - Consider pausing xterm rendering for hidden-tab PTYs. xterm.js running in a `display: none` panel still processes writes and grows scrollback (capped at 1000 lines, but still wasted CPU). Either drop incoming `output` chunks into the modal only when visible (queue and replay on tab focus) or accept the cost as small enough to ignore — worth measuring under a long-running ffuf in a backgrounded tab before spending engineering on it.

### Run comparison follow-ups
- Consider active-tab compare, snapshot/permalink compare, package-artifact compare, and export/share comparison once the run-vs-run model has more production use.
- Add focused large/noisy output regressions if real scanner output exposes performance or alignment gaps beyond the current backend, Vitest, and Playwright coverage.

## Research

### Postgres production backend and storage scaling plan
- **Question**
  - Should darklab_shell keep SQLite as the only supported persistence backend, or add Postgres as the recommended backend for heavy multi-user deployments?
- **Why this matters**
  - A single-user dev database can grow quickly when saved run output, FTS/search data, workspace artifacts, findings, projects, and future Atlas/intel rows all accumulate.
  - SQLite can handle large files, but heavy shared deployments are more likely to feel pain from single-writer contention, pruning/vacuum cost, backup/restore ergonomics, and one large mutable database file.
  - Features already planned in this TODO, especially Session Entity Atlas, Findings triage, external intel snapshots, schedulers, watchers, and notifications, will increase write volume and relational query complexity.
- **Research tasks**
  - Measure the current dev database by table and index size, including FTS tables, `runs.output`, output previews, artifacts, findings, snapshots, and project metadata.
  - Estimate one-year growth for 10, 30, and 100 heavy users using current retention settings and realistic scanner-output sizes.
  - Identify which data should stay relational and which data should move to file/object storage, such as full transcripts, large raw intel payloads, package exports, and bulky artifacts.
  - Compare three storage models:
    - SQLite-only with stronger pruning, compression, vacuum, and table-size diagnostics.
    - Hybrid SQLite metadata plus filesystem/object storage for large transcript and artifact bodies.
    - Postgres production backend with SQLite retained as the default local/dev/single-user backend.
  - Review query and schema differences needed for Postgres compatibility: FTS/search, JSON payloads, upserts, timestamp handling, migrations, row locking, and test fixtures.
  - Decide whether new large features, especially Atlas and intel snapshots, should be written in a Postgres-compatible style from the start.
  - Define the migration and deployment story: config keys, Docker Compose service shape, backup/restore docs, local dev defaults, and an optional SQLite-to-Postgres migration helper.
- **Initial recommendation**
  - Keep SQLite as the default local and single-user backend for now.
  - Plan Postgres as the preferred production backend for heavy multi-user deployments.
  - Before a database swap, reduce storage pressure by separating metadata/search from large transcript, artifact, and raw intel bodies where practical.

---

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Tool-specific guidance
- Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `naabu`, or `nuclei`.
- Good fit for the existing help / FAQ / welcome surfaces.
- Merge this with onboarding and command hints into a broader user guidance layer:
  - command-specific caveats
  - what to expect while a tool runs
  - examples of when to use one tool vs another

### Command catalog future-state
- Add `commands search <term>` for roots, descriptions, categories, examples, and flag text.
- Add `commands --json` or `commands info --json <root>` for debugging, export, and future UI reuse.
- Add optional richer registry fields such as `details`, `notes`, `common_flags`, or `gotchas` when a flag or tool needs more than a short autocomplete description.
- Add command-specific guidance for web-shell behavior, including injected safe defaults, quiet-running tools, generated Files output, and managed session state.
- Add autocomplete side previews later: when a root, subcommand, or flag is highlighted, show the command description or flag note in a small help pane.
- Add hover/focus cards for FAQ chips once the command-details modal behavior has settled.
- Consider including pipe helpers in a separate “Pipes” section once command catalog UX exists.
- Consider linking command catalog entries to real `man` output where available, while keeping app-native allowed-subset details primary.

### Command outcome summaries
- For selected tools, generate short app-native summaries below the raw output. Security tool output is high-volume; a clear findings layer is what separates a purpose-built tool from a raw terminal.
- Keep raw output primary — the summary is additive, never a replacement.
- Start narrow: nmap (open ports + service table), dig (records returned), curl (status code + redirect chain), openssl s_client (cert expiry + trust chain).
- The structured output model (see Architecture) is the right long-term foundation. Build this feature so it can move onto that model later instead of requiring it up front.

### Transcript noise classification
- Future cleanup for saved command output across both normal runs and interactive PTY runs.
- Avoid broad duplicate-line removal because repeated lines can be meaningful findings for some tools.
- Classify known progress/status/redraw lines before history/search/finding classification, starting with high-noise shapes from tools like `masscan`, `ffuf`, `nuclei`, and ProjectDiscovery tools that emit frequent status updates.
- Keep real newline-terminated findings and normal scrollback untouched.
- For interactive PTY runs, keep the final visible frame available so users can still inspect the last terminal state, even when progress/status redraw lines are excluded from searchable saved transcript text.
- For normal runs, prefer command-specific noise classifiers over global suppression so raw output stays faithful while search, findings, summaries, and previews become easier to use.

### Run comparison enhancements
- Future-state enhancements after the shared split-pane comparison flow has real use.
  - Finding-level diffs using persisted signal/finding metadata:
    - New findings.
    - Disappeared findings.
    - Unchanged findings.
    - Changed severity or changed metadata.
  - Tool-aware diffs for common scanner outputs:
    - `nmap`: ports, protocols, services, versions, and state changes.
    - URL/status/title lists: new URLs, disappeared URLs, status changes, title changes.
    - Subdomain lists: new and disappeared names.
    - TLS/certificate output: issuer, subject, SAN, validity, and fingerprint changes.
  - Keep tool-aware parsers additive; raw changed/added/removed output should remain the fallback.
- Future entry points and packaging:
  - Active tab `Compare` action for restored/completed runs.
  - Findings strip action such as `Compare findings with previous run`.
  - Workflow provenance in comparison summaries once workflow-linked runs exist.
  - Snapshot/permalink compare if the run-vs-run model continues to work well.
  - `Export comparison` once share/export packages have a stable artifact model.
- Future UX/testing:
  - Consider date-range filters in the manual compare picker if day grouping plus `Load More` is not enough for deep history.
  - Broaden Playwright coverage for edge/mobile layout paths after the UI settles.
  - Add focused large/noisy comparison regression coverage if real-world outputs expose performance issues beyond current backend and unit coverage.

### Bulk history export and share
- The history drawer can delete all, delete non-favorites, and use visible-page multi-select for bulk project add/remove plus selected-item delete. Bulk export to JSONL/txt and bulk share would close the remaining gap when packaging selected history items after an engagement.

### Autocomplete suggestions from output context
- When a previous command's output is in the active tab, `| grep` completions could suggest patterns already present in that output — IP addresses, hostnames, status codes, CVE strings — as candidates alongside the generic flag list.
- Narrow but would make the pipe stage feel predictive rather than generic.

### Mobile share ergonomics
- The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
  - save/share actions tuned for one-handed use
  - clearer copy/share/export affordances inside the mobile shell
  - better share handoff after snapshot creation

### Scheduled and recurring runs
- Cron-style scheduler so any command or workflow can fire on a cadence (daily nmap, hourly httpx, weekly subdomain sweep) without keeping the tab open. Nothing in the app is currently time-driven.
- **Entry-level scope:**
  - Save a schedule from any command or workflow with a cron expression or a small cadence preset (hourly/daily/weekly).
  - Schedules belong to the active session token and migrate with it.
  - Fired runs land in normal history tagged `scheduled` with the originating schedule ID.
  - List/pause/delete schedules through a new `schedule` built-in plus a Schedules modal beside Workflows.
- **Architecture:**
  - New `app/services/scheduler/` service backed by APScheduler (or a small Redis sorted-set tick loop) running in a dedicated `scheduler` process so worker restarts do not lose ticks.
  - SQLite `schedules` table: id, session_token, command/workflow ref, cron, enabled, last_run_at, next_run_at.
  - At fire time the scheduler enqueues through the existing `/runs` broker under the owning session so allowlist, deny-prefix, registry rewrite, and history persistence are reused unchanged.
  - New `app/blueprints/schedules.py` for CRUD; new `schedule` handler in the session built-in family; new `app/static/js/features/schedules/` for the modal and runtime autocomplete.
  - Gotchas: cron string validation, surfacing missed fires after a container restart, and tearing down schedules when their session token is revoked.

### Watchers (change-detection monitors)
- Pair a recurring command with a stored baseline and notify only when output diverges (new open port, new subdomain, new finding signature, TLS cert change). Builds on the run-comparison diff engine but exposes it as a persistent first-class object, not a one-off compare.
- **Entry-level scope:**
  - Create a watcher from any completed run ("watch this nmap for new open ports").
  - Watchers reuse the scheduler service to re-run on a cadence.
  - Each fire stores a structured diff against the prior accepted baseline; notifications fire only on non-empty diffs.
  - A Watchers modal shows status (ok / changed / firing), last fire, last diff, with accept-new-baseline and pause actions.
- **Architecture:**
  - New `app/services/watchers/` service composing the scheduler service with the existing comparison helpers in `app/services/runs/comparison.py`.
  - SQLite `watchers` table: id, session_token, command, schedule_ref, baseline_run_id, last_run_id, last_diff_summary, state.
  - Reuses the structured finding/signal model when present; falls back to textual added/removed line diffs otherwise. The structured output model called out in Architecture is the natural long-term substrate.
  - Fires through the new outbound-notifications surface so a watcher hit can reach Slack/email/push without duplicating delivery code.

### Outbound notifications (webhooks, Slack, Discord, email)
- Run-complete, finding-classified, and watcher-fired events fan out to external channels per session or per project. Existing notifications are browser-foreground only; this closes the loop for solo operators running long scans away from the tab.
- **Entry-level scope:**
  - Configure one or more channels per session token. Start with a generic JSON webhook; layer Slack, Discord, and SMTP email on the same channel abstraction.
  - Triggers: run-complete (per exit-code policy), finding-classified, watcher-fired, scheduled-run-failed.
  - Per-channel mute plus a global "do not disturb" toggle.
  - Notification body uses only the command root, matching the existing browser desktop-notification policy that intentionally avoids exposing arguments or token values.
- **Architecture:**
  - New `app/services/notifications/` service with a `Channel` base class and `WebhookChannel`, `SlackChannel`, `DiscordChannel`, `EmailChannel` implementations. SMTP is operator-config-gated in `app/conf/config.yaml`.
  - SQLite `notification_channels` table (per session token, encrypted secret column for webhook URL / bot token) and `notification_events` for delivery audit and retry.
  - Hook points: run finalization in `app/blueprints/run.py`, watcher fire path, scheduler error path.
  - Browser surface: Options modal "Notifications" section; new `app/static/js/features/preferences/notification_channels.js`.
  - Secret storage rides on the encrypted-secrets-vault idea below rather than introducing a parallel ciphertext path.

### Headless API and CLI client
- Stable REST endpoints plus a thin `darklab` CLI, authenticated by an existing session token, that can launch runs, poll history, and pull artifacts from CI pipelines or local scripts.
- **Entry-level scope:**
  - REST: `POST /api/v1/runs`, `GET /api/v1/runs/<id>`, `GET /api/v1/runs/<id>/stream` (SSE), `GET /api/v1/history`, `GET /api/v1/history/<id>/output`, authenticated via `Authorization: Bearer tok_...`.
  - CLI: `darklab run "nmap …"`, `darklab tail <id>`, `darklab history`, `darklab download <id> [--workspace]`.
  - Same allowlist, deny-prefix, registry-rewrite, and rate-limit bucket as the browser path so headless use cannot bypass per-session limits.
- **Architecture:**
  - New `app/blueprints/api_v1.py` reusing the existing run broker, history service, and validation; OpenAPI/JSON schema published at `/api/v1/openapi.json` for clients to consume.
  - CLI ships as a tiny Python package under `tools/darklab_cli/` with its own `pyproject.toml`; communicates only via the REST blueprint, no shared imports with the server runtime.
  - Output streaming reuses the broker SSE path so multi-worker reattach already works.
  - Documented in a new `docs/api.md` plus a CONFIGURATION.md section.

### PWA install and service-worker push
- Make the mobile shell installable and deliver completion pings via web-push so phone users get notified when the tab is closed or the device is asleep. Today mobile notifications are intentionally hidden because foreground-only notifications are not useful on phones.
- **Entry-level scope:**
  - Add a manifest, app icons, and a small service worker so users can "Add to Home Screen" and launch into a standalone mobile shell.
  - VAPID-signed web-push subscription tied to the active session token; subscribe and unsubscribe from the Options sheet.
  - Reuse the run-complete event hook from the outbound-notifications surface so push is just another channel.
- **Architecture:**
  - New `app/static/manifest.webmanifest`, icon assets under `app/static/icons/`, and `app/static/sw.js` registered from `app.js` only when the runtime supports it.
  - New `WebPushChannel` in the notifications service; VAPID keys stored as operator config; per-session-token subscription endpoint at `/session/push/subscribe`.
  - Service worker scope is intentionally narrow — render notifications and open the tab on click; no caching of dynamic transcript content so users never see stale output.
  - Gotchas: iOS Safari requires the user to install the PWA before push works; document this in CONFIGURATION.md.

### Engagement report builder
- Turn a project workspace into a styled markdown/PDF engagement report — methodology, scope, targets, findings table, remediation notes, screenshots. Evidence packages today are raw bundles; this is the narrative deliverable a customer reads.
- **Entry-level scope:**
  - One-click "Generate report" from a project, with an editable cover page (engagement name, dates, operator, contact).
  - Sections auto-populated from project data: targets, findings grouped by severity, included runs (with permalinks), artifacts.
  - Output formats: markdown source plus rendered HTML and PDF, reusing the existing export pipeline.
  - Operator-editable section templates in a new `app/conf/report_templates.yaml`.
- **Architecture:**
  - New `app/services/reports/` service composing project-workspace data with existing finding/run/artifact serializers; templating via Jinja autoescape (aligns with the package HTML rendering follow-up in Open TODOs).
  - Adds `GET/POST /projects/<id>/report` to `app/blueprints/projects.py`.
  - Browser surface: a "Report" tab inside the existing Projects modal; renderer reuses `export_html.js` and `export_pdf.js`.
  - Honors share-redaction defaults; the draft is always previewed before download so this stays additive to evidence packages, not a replacement.

### Prometheus `/metrics` endpoint
- Operator observability beyond `/diag`: active-run gauge, exit-code distribution, per-tool runtime histograms, rate-limit rejections — scrapeable for Grafana.
- **Entry-level scope:**
  - New IP-gated `/metrics` route exposing OpenMetrics-format text. Same IP allowlist as `/diag` so it is not internet-exposed by default.
  - Initial metric set:
    - `darklab_active_runs`
    - `darklab_run_total{tool,exit_code}`
    - `darklab_run_duration_seconds{tool}` (histogram)
    - `darklab_rate_limit_rejections_total`
    - `darklab_pty_active`
    - `darklab_workspace_quota_bytes{state}`
- **Architecture:**
  - Use the `prometheus_client` Python library with a multiprocess collector compatible with Gunicorn workers (`PROMETHEUS_MULTIPROC_DIR` writable inside the container).
  - Counters/histograms are updated from the run-finalize path in `app/blueprints/run.py`, the rate limiter in `app/extensions.py`, and the PTY service.
  - Route lives next to `/diag` in `app/blueprints/assets.py`; documented in CONFIGURATION.md alongside the existing diagnostics surface.

### Findings triage inbox
- Folded into the Session Entity Atlas idea below as phase 4 (the Findings tab becomes the inbox surface). Kept here so the standalone scope/architecture stays reviewable if the Atlas does not land first.
- Cross-run, cross-project queue of every finding and warning the classifier has emitted, with status (new / triaged / confirmed / false-positive) and a "seen before in run X" dedupe link. Today findings live per-run; this surfaces patterns over time.
- **Entry-level scope:**
  - A Findings modal listing all classifier-emitted findings and warnings across saved runs for the active session, with filters for severity, status, tool, and project.
  - Per-finding actions: mark triaged, confirm, mark false-positive, jump to source run, optionally pin into a project as a structured finding.
  - Dedupe: identical finding signature across runs collapses into one row with a count and first/last-seen timestamps.
- **Architecture:**
  - New `app/services/findings/` service that materializes per-run finding records from `app/core/output_signals.py` into a `findings_inbox` SQLite table at run-finalize time. Each row carries a stable signature hash for dedupe.
  - New `app/blueprints/findings.py` for list, filter, and status routes.
  - Browser surface: new `app/static/js/features/findings/findings_inbox.js` and `app/static/css/features/findings.css`; entry points from the History drawer, Run Details modal, and Projects modal.
  - The natural consumer of the structured output model in Architecture: design the inbox schema so it can move onto richer line/event data later without breaking the dedupe signature.

### External intel service integrations
- Connect darklab_shell to passive recon and reputation services (Shodan, VirusTotal, GreyNoise, and friends) so scanner output and findings can be enriched without leaving the shell. Existing tools answer "what does this host expose right now?"; intel services answer "what does the rest of the internet already know about it?".
- **v1 ship list — Shodan, VirusTotal, GreyNoise**
  - Rationale:
    - Shodan covers passive ports, banners, and historical CVE data.
    - VirusTotal covers file hashes, URLs, domains, and passive DNS.
    - GreyNoise classifies whether an IP is internet background noise or targeted.
    - Together they answer most "should I care about this host?" triage questions.
  - Ship in two passes:
    - Pass 1 (CLI wrapper): install `shodan`, `vt-cli`, and a `greynoise` CLI in the Dockerfile and register allowed subcommands/flags in `commands.yaml` with declared env-consumer slots (`SHODAN_API_KEY`, `VT_API_KEY`, `GREYNOISE_API_KEY`). Users get the same allowlist, autocomplete, history, Files, and rate-limit behavior as every other tool.
    - Pass 2 (app-native built-in): add an `intel ip|domain|hash` built-in backed by Python provider modules so users have one uniform output card across all three providers.
  - Hard dependencies:
    - Encrypted secrets vault — every provider needs an API key, and a parallel per-integration ciphertext path should not exist.
    - Provider abstraction (below) — landed once, reused by every future provider.
  - Architecture:
    - New `app/services/intel/` service with a `Provider` base class and `shodan.py`, `virustotal.py`, `greynoise.py` modules implementing `lookup_ip`, `lookup_domain`, `lookup_hash`, `lookup_cve` as applicable.
    - Per-provider token-bucket rate limiter plus a Redis-backed response cache with provider-tunable TTL (passive intel data changes slowly).
    - Audit log of which run hit which provider with which entity, written through the structured log channel; never logs the response body.
    - Built-in lives in a new `app/services/commands/builtins_intel.py`; browser surface is a uniform `intel` result card rendered by a new `app/static/js/features/intel/intel_card.js`.
    - Sharing: intel response bodies are treated as raw-only and excluded from snapshot permalinks by the existing share-redaction baseline.
- **Cross-cutting infrastructure to land once, before or with v1**
  - Encrypted secrets vault — required for every integration here.
  - Provider abstraction (`app/services/intel/providers/`):
    - `Provider` base class with shared lookup methods.
    - Per-provider token-bucket rate limiter.
    - Redis-backed response cache.
    - Run/entity audit log.
  - Entity-aware output classifier hooks:
    - Extend `app/core/output_signals.py` to surface extracted IPs, domains, hashes, and CVEs as structured events.
    - Downstream features (sidecar panel, findings enricher, pipe helpers) all consume the same event stream.
    - Aligns with the structured output model called out in Architecture below.
- **Integration patterns (each can land independently once the shared infra exists)**
  - CLI wrapper — install vendor CLI in the Dockerfile, register in `commands.yaml`, inject the secret. Lightest path; first home for Shodan, VT, Censys, BuiltWith, urlscan.
  - App-native `intel` built-in — single command (`intel ip|domain|hash|cve`) aggregating multiple providers behind one uniform output card via `app/services/intel/`.
  - Sidecar enrichment panel — opt-in passive lookups fire alongside a scanner run; render Shodan ports, GreyNoise verdict, IPinfo ASN, VT reputation in a collapsible panel next to the transcript. Off by default per session; auditable per run.
  - Findings enricher — when the classifier extracts an entity, the findings inbox auto-attaches enrichment from relevant providers, turning the inbox from a queue into a triage workbench.
  - Workflow steps — Workflows can chain native tools with intel lookups (for example `subfinder → dnsx → pd-httpx → virustotal-domain → urlscan`).
  - Pipe helper enrichment — new `| enrich-shodan` / `| enrich-greynoise` post-filters that walk stdin for entities and append one annotation per line. Fits the existing synthetic pipe-helper model in `app/services/commands/postfilters.py`.
  - Project workspace enrichment — when a host/domain is added as a project target, optionally pre-fetch passive snapshots and store them as workspace artifacts under `/intel/<target>/`, becoming part of evidence packages and the engagement report builder idea.
- **Future provider candidates (after v1)**
  - Host/port intel — Censys, ZoomEye.
  - URL/file reputation — urlscan.io, Hybrid Analysis, Triage, Joe Sandbox.
  - Passive DNS / asset discovery — SecurityTrails, AlienVault OTX, Chaos (ProjectDiscovery; integrates naturally with the already-shipped subfinder/dnsx/pd-httpx via env var), crt.sh (free, no key needed).
  - Threat intel / reputation — AbuseIPDB, ThreatFox, MISP.
  - ASN / WHOIS / geo — IPinfo, Team Cymru, BGPView (free).
  - Breach / credential exposure — HaveIBeenPwned, DeHashed, IntelX.
  - Tech detection — BuiltWith, Wappalyzer CLI.
  - CVE / vuln data — NVD, Vulners, ExploitDB.
- **Anti-patterns to avoid**
  - Do not call live intel APIs during a scanner run by default. It costs API quota and surprises users; sidecar enrichment must be opt-in per session or project.
  - Do not log API keys, full response bodies, or raw entity lists into shared transcripts, snapshot permalinks, or exports. Treat intel response bodies as raw-only in the share-redaction baseline.
  - Do not reimplement what a vendor CLI already does well — wrap it, inject the secret, log usage, move on.

### Session Entity Atlas (entity-first triage surface)
- Reframe darklab_shell's exploration model so entities (findings, hosts/IPs, domains, hashes, CVEs, URLs) become the primary navigation primitive — not runs, not projects. Runs become the *source* of entities. Projects become a *curated subset* of entities for engagement work. The active session token owns the entity graph.
- **The gap it closes:**
  - Every run already produces classified findings, but the rich exploration UI lives inside Projects. Runs not linked to a project surface findings only inside Run Details with no aggregation, triage state, or cross-run pivot.
  - The proposed `intel` built-in widens the gap because intel data is inherently entity-shaped — a Shodan record is about an IP, not the nmap run that produced it. Without an entity-first surface, Findings, Intel, and Projects each grow parallel triage modals that show fragments of the same picture.
  - Project membership stops being a gate on tooling. Users can recon casually and curate later without losing the engagement-grade Projects surface.
- **UI shape:**
  - New top-level **Atlas** surface with the same prominence as History — desktop left-rail entry, mobile menu item, keyboard shortcut. Not a stacked modal.
  - Atlas tabs across the top: Findings, Hosts/IPs, Domains, Hashes, CVEs, URLs. Each tab is a filterable, sortable list of distinct entities extracted across every saved run for the active session token.
  - Entity Detail side sheet opens from any row or from a tagged transcript token:
    - Identity strip — type, canonical value, first/last seen, run count.
    - Intel snapshot card — Shodan / VT / GreyNoise / IPinfo / etc., with explicit refresh so cache state is visible.
    - Source runs list — every run that mentioned the entity, with command, tool, finding count, jump-to-line link.
    - Findings extracted on the entity across all runs.
    - Labels and notes via the existing `ui_entity_metadata.js` helper.
    - Promote-to-project action.
  - Transcript ↔ Atlas wiring:
    - Tagged tokens become click targets; click opens entity detail; long-press / right-click exposes the full action menu (label, note, promote, copy, lookup intel).
    - Hover popover on tagged tokens shows the high-signal summary (GreyNoise verdict, Shodan port count, VT positives) without leaving the transcript.
    - "See in run" inside entity detail jumps back to the source line in the original run.
- **Phased rollout:**
  - Phase 1 — Read-only Atlas: render Findings, Hosts, Domains, Hashes, CVEs tabs from data already classified by `app/core/output_signals.py`. Rows click into their source run; no new metadata yet. Ships value alone.
  - Phase 2 — Entity Detail: aggregate across runs, attach labels/notes, dedupe via stable signature, "see in run" navigation.
  - Phase 3 — Intel attachment: explicit `intel` results, sidecar enrichment, and pipe-helper enrichment all write into entity-keyed intel rows; entity detail renders them.
  - Phase 4 — Findings triage state: promote the Findings triage inbox actions (new / triaged / confirmed / false-positive, signature dedupe) onto the Findings tab. The standalone Findings triage inbox idea folds in here instead of shipping as its own surface.
  - Phase 5 — Project linking: adding to a project becomes a tag on the entity row; project workspace, evidence packages, and engagement report builder all read from the same entity store.
- **Architecture:**
  - Storage:
    - New `entities` table keyed by (session_token, type, canonical_value, signature_hash) for stable dedupe across runs.
    - `entity_run_links` (entity_id, run_id, first_seen, last_seen, occurrence_count) so cross-run aggregation is a single join.
    - `entity_intel_snapshots` (entity_id, provider, payload_json, fetched_at, ttl) keyed by provider so refresh and quota stories stay tractable.
    - Existing `project_links` rows with `entity_type='atlas_entity'` replace per-project copies of entity rows; no standalone `entity_project_links` table.
  - Services:
    - New `app/services/atlas/` service with materialization helpers that run at run-finalize time, consuming entity events surfaced by the entity-aware output classifier hooks called out under the intel integrations idea.
    - Entities are extracted lazily and deduped via stable signature so long sessions do not balloon SQLite. Materialization is idempotent so re-finalizing a run does not double-count.
    - Reuses the existing label/note helpers, run-comparison structured-finding model, and intel provider modules.
  - Routes:
    - New `app/blueprints/atlas.py` for list, filter, detail, and entity-mutation routes (labels, notes, project links, intel refresh).
    - Existing Findings, Run Details, and Projects routes read from the same entity store rather than maintaining parallel finding queues.
  - Browser surface:
    - New `app/static/js/features/atlas/` for the Atlas surface, tab list rendering, entity detail side sheet, transcript hover popover, and tagged-token action menu.
    - New `app/static/css/features/atlas.css`.
    - Run Details, Projects, and the `intel` result card all link into entity detail rather than re-rendering entity data locally.
  - Sharing and exports:
    - Entity rows themselves never appear in snapshot permalinks; only the source run transcript does. The existing share-redaction baseline already covers raw transcript content.
    - Engagement report builder (separate idea) reads from the entity store for "targets", "findings", and "intel observations" sections, replacing per-project ad-hoc aggregation.
- **Anti-patterns to avoid:**
  - Do not build the Atlas as yet-another-modal stacked over History. It needs first-class chrome treatment (rail entry, shortcut, mobile menu item) or it will be invisible.
  - Do not duplicate entity metadata between Atlas and Projects. Project membership is a tag on the entity row; labels, notes, and intel live on the entity.
  - Do not materialize entities eagerly for every line of output. Extract lazily from classifier events at finalization and dedupe with stable signatures so SQLite cost scales with distinct entities, not output volume.
  - Do not gate intel data on the user calling `intel` explicitly. Sidecar enrichment, pipe-helper enrichment, and explicit `intel` calls must all write through the same per-entity intel rows so a user who never types `intel` still sees enriched data.
  - Do not break runs that have no findings. Utility commands and failed commands produce zero entities; the Atlas must treat that as the normal case, not an empty state worth surfacing.
- **Relationships to other ideas:**
  - Folds in the **Findings triage inbox** idea as phase 4 — the inbox becomes the Findings lens on the Atlas, not a separate surface.
  - Provides the natural home for **External intel service integrations** — entity detail is where intel snapshots live; sidecar enrichment, the `intel` built-in, and pipe-helper enrichment all write here.
  - Consumes the entity-aware output classifier hooks called out under intel integrations and the **structured output model** under Architecture.
  - Reframes **Project workspaces** as a curation layer over the entity store rather than the only triage surface; project linking is a tag, not a copy.

---

## Architecture

### Structured output model
- Preserve richer line/event details consistently for all runs.
- This would improve search, comparison, redaction, exports, and permalink fidelity.
- Command outcome summaries are buildable without this foundation, but design them so they can move onto the structured model later. Summary parsers should consume structured line events, not re-parse raw text forever.

### Unified terminal built-in lifecycle
- Browser-owned built-ins (`theme`, `config`, and `session-token`) need browser execution for DOM state, local storage, clipboard, and transcript-owned confirmations, while server-owned built-ins naturally flow through `/runs`.
- The long-term cleanup target is one terminal-command lifecycle after execution:
  - normalize built-in output into a shared result shape
  - apply pipe helpers against that shape
  - mask sensitive command arguments once
  - render transcript output once
  - persist server-backed history once
  - load recents and prompt history from the same saved run model
- Keep execution ownership separate where it matters, but remove duplicated recents/history/pipe/persistence glue so browser-owned and server-owned built-ins cannot drift.

### Plugin-style helper command registry
- Turn the built-in command layer into a cleaner extension point for future app-native helpers.

### Lightweight Jinja base template
- `index.html`, `permalink_base.html`, and `diag.html` now all share the same ~10 lines of `<head>` bootstrap (charset, viewport, color-scheme meta, favicon, `fonts.css`, `styles.css`, theme var includes, and the two vendor scripts). With three templates the duplication is starting to pay for the indirection.
- A `base.html` factoring out the common `<head>` and `data-theme` body attribute would prevent drift and make adding a fourth page type trivial.

### Interactive PTY transport future-state
- Revisit whether the current Redis-brokered SSE plus POST input/resize transport should move to WebSockets after real use.
- The current model keeps deployment simple and avoids a WebSocket runtime, but a bidirectional socket could reduce input latency and simplify the modal terminal stream once PTY usage grows.
