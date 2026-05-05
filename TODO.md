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

- **Output finding matcher coverage from `/tmp/findings.txt` review**
  - Goal:
    - Expand `app/output_signals.py` so command-specific findings summaries catch high-value lines that are currently missed without making broad global hostname/URL patterns noisy.
    - Prefer command-scoped matchers for DNS enumeration, web enumeration, TLS posture, WordPress scanning, and ProjectDiscovery output. Avoid global hostname matching because many tools print target names in progress/status lines.
  - DNS and subdomain enumeration tools:
    - `dnsx`
      - Current summary: `[summarize not active]`.
      - Add a `dnsx`-scoped hostname/subdomain result matcher for bare result lines:
        - `ip.darklab.sh`
        - `www.darklab.sh`
      - Exclude banner/version lines such as `[INF] Current dnsx version...`.
    - `fierce`
      - Current summary: `[summarize not active]`.
      - Add `fierce`-scoped matchers for discovered DNS records:
        - `NS: frank.ns.cloudflare.com. ruth.ns.cloudflare.com.`
        - `SOA: frank.ns.cloudflare.com. (173.245.59.166)`
        - `Found: h.darklab.sh. (192.168.1.3)`
        - `Found: ip.darklab.sh. (107.178.109.44)`
        - `Found: loghost.darklab.sh. (107.178.106.165)`
        - `Found: logs.darklab.sh. (107.178.106.165)`
        - `Found: monitoring.darklab.sh. (107.178.106.165)`
        - `Found: p.darklab.sh. (107.178.109.44)`
        - `Found: r.darklab.sh. (107.178.109.44)`
      - Consider whether `Nearby:` PTR dictionaries are findings or supporting context; they are useful enrichment but much noisier than `Found:` lines.
    - `dnsenum`
      - Current summary catches A records well.
      - Add `dnsenum`-scoped network range findings or summaries for class-C ranges:
        - `104.21.4.0/24`
        - `172.67.131.0/24`
      - Keep existing AXFR/read-only errors as errors.
    - `dnsrecon`
      - Current summary catches SOA/NS/MX/A/AAAA/TXT lines well.
      - Consider adding DNSSEC configuration as a summary/finding if useful:
        - `[*] DNSSEC is configured for darklab.sh`
      - Leave `Bind Version...` lines out of findings unless we decide server-version exposure should be summarized.
  - ProjectDiscovery web and crawl tools:
    - `pd-httpx`
      - Current summary: `[summarize not active]`.
      - Add `pd-httpx`/`httpx`-scoped result-line matcher for URL + status + title/tech brackets:
        - `https://ip.darklab.sh [200] [Nginx]`
      - Keep dashboard/version/banner lines out of findings; warning matcher already catches dashboard warning.
    - `katana`
      - Current summary: `[summarize not active]`.
      - Add `katana`-scoped URL result matcher for clean crawled URLs:
        - `https://p.darklab.sh`
        - `https://p.darklab.sh/js/legacy.js?2.0.4`
        - `https://p.darklab.sh/js/kjua-0.10.0.js`
        - `https://p.darklab.sh/manifest.json?2.0.4`
        - `https://p.darklab.sh/css/bootstrap/privatebin.css?2.0.4`
        - `https://p.darklab.sh/js/privatebin.js?2.0.4`
        - `https://p.darklab.sh/css/bootstrap/darkstrap-0.9.3.css`
      - Exclude JavaScript-template artifacts that are technically URL-shaped but not real crawl findings:
        - `https://p.darklab.sh/js/'+t+'`
        - `https://p.darklab.sh/js/'+a+'`
        - `https://p.darklab.sh/js/$1`
  - Web fingerprinting and app scanners:
    - `wafw00f`
      - Current summary: `[summarize not active]`.
      - Add WAF-detection matcher:
        - `[+] The site https://darklab.sh is behind Cloudflare (Cloudflare Inc.) WAF.`
      - Treat `[~] Number of requests: 2` as a summary at most, not a finding.
    - `nikto`
      - Current summary only captures errors.
      - Add `nikto`-scoped informational findings for target/server/TLS posture:
        - `+ Target IP:          107.178.109.44`
        - `+ Target Hostname:    ip.darklab.sh`
        - `+ SSL Info:           Subject:  /CN=ip.darklab.sh`
        - `CN:       ip.darklab.sh`
        - `SAN:      ip.darklab.sh`
        - `Issuer:   /C=US/O=Let's Encrypt/CN=R13`
        - `+ Server: nginx`
      - Add `nikto` item/result matcher for positive findings in future outputs, but avoid counting progress/status lines:
        - include `+ <finding text>` when it is not `+ Start Time`, `+ End Time`, `+ 1 host(s) tested`, or `+ ERROR`.
      - Keep existing `+ ERROR...` lines as errors.
    - `wpscan`
      - Current summary only catches `[+] Enumerating Vulnerable Plugins...`, which is progress, not the most useful finding.
      - Add `wpscan`-scoped matchers for the actual interesting finding headers:
        - `[+] Headers`
        - `[+] robots.txt found: https://churchint.org/robots.txt`
        - `[+] XML-RPC seems to be enabled: https://churchint.org/xmlrpc.php`
        - `[+] WordPress readme found: https://churchint.org/readme.html`
        - `[+] Debug Log found: https://churchint.org/wp-content/debug.log`
        - `[+] The external WP-Cron seems to be enabled: https://churchint.org/wp-cron.php`
        - `[+] WordPress version 6.9.4 identified (Latest, released on 2026-03-11).`
        - `[+] WordPress theme in use: Divi-Child-Theme`
      - Treat `|  - /wp-admin/`, `|  - /wp-admin/admin-ajax.php`, and other `Interesting Entries` children as supporting findings or child details if we add structured findings later.
      - Do not treat footer/progress lines as findings:
        - `[+] Finished...`
        - `[+] Requests Done: 2`
        - `[+] Data Sent...`
        - `[+] Memory used...`
      - Treat `[!] No WPScan API Token given...` as warning, not finding.
  - TLS scanners:
    - `testssl`
      - Current summary catches many vulnerability result lines, but misses TLS posture, certificate, HTTP header, and grade lines.
      - Add `testssl`-scoped findings for protocol/cipher posture:
        - `TLS 1.2    offered (OK)`
        - `TLS 1.3    offered (OK): final`
        - `ALPN/HTTP2 h2, http/1.1 (offered)`
        - `Forward Secrecy strong encryption (AEAD ciphers)  offered (OK)`
        - `FS is offered (OK)           DHE-RSA-AES128-GCM-SHA256`
        - `Elliptic curves offered:     prime256v1 secp384r1 secp521r1`
      - Add `testssl`-scoped certificate/header findings:
        - `Common Name (CN)             ip.darklab.sh  (request w/o SNI didn't succeed)`
        - `subjectAltName (SAN)         ip.darklab.sh`
        - `Trust (hostname)             Ok via SAN and CN (SNI mandatory)`
        - `Certificate Validity (UTC)   41 >= 30 days (2026-03-18 08:22 --> 2026-06-16 08:22)`
        - `Issuer                       R13 (Let's Encrypt from US)`
        - `HTTP Status Code             200 OK`
        - `Strict Transport Security    not offered`
        - `Server banner                nginx`
      - Add `testssl`-scoped grade finding:
        - `Overall Grade                A+`
      - Capture vulnerability result lines even when they do not include the exact phrase `not vulnerable`:
        - `ROBOT                                     Server does not support any cipher suites that use RSA key transport`
        - `Secure Renegotiation (RFC 5746)           supported (OK)`
        - `BREACH (CVE-2013-3587)                    no gzip/deflate/compress/br HTTP compression (OK)  - only supplied "/" tested`
        - `LOGJAM (CVE-2015-4000), experimental      common prime with 4096 bits detected: RFC7919/ffdhe4096 (4096 bits),`
    - `sslscan`
      - Current summary only catches heartbleed lines.
      - Add `sslscan`-scoped protocol/cipher findings:
        - `TLSv1.2   enabled`
        - `TLSv1.3   enabled`
        - `Server supports TLS Fallback SCSV`
        - `Preferred TLSv1.3  128 bits  TLS_AES_128_GCM_SHA256`
        - `Accepted  TLSv1.3  256 bits  TLS_AES_256_GCM_SHA384`
        - `Preferred TLSv1.2  256 bits  ECDHE-RSA-AES256-GCM-SHA384   Curve 25519 DHE 253`
      - Add `sslscan`-scoped certificate findings:
        - `Signature Algorithm: sha256WithRSAEncryption`
        - `RSA Key Strength:    4096`
        - `Subject:  ip.darklab.sh`
        - `Altnames: DNS:ip.darklab.sh`
        - `Issuer:   R13`
        - `Not valid before: Mar 18 08:22:43 2026 GMT`
        - `Not valid after:  Jun 16 08:22:42 2026 GMT`
    - `sslyze`
      - Current summary catches some non-vulnerable lines, one certificate transparency warning, and the compliance failure.
      - Add `sslyze`-scoped certificate findings:
        - `Common Name:                       ip.darklab.sh`
        - `Issuer:                            R13`
        - `Not Before:                        2026-03-18`
        - `Not After:                         2026-06-16`
        - `Key Size:                          4096`
        - `SubjAltName - DNS Names:           ['ip.darklab.sh']`
        - `Received Chain:                    ip.darklab.sh --> R13`
        - `Verified Chain:                    ip.darklab.sh --> R13 --> ISRG Root X1`
      - Add `sslyze`-scoped accepted cipher findings:
        - `TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256       256       ECDH: X25519 (253 bits)`
        - `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384             256       ECDH: secp256r1 (256 bits)`
        - `TLS_AES_256_GCM_SHA384                            256       ECDH: X25519 (253 bits)`
      - Add `sslyze`-scoped posture findings:
        - `Forward Secrecy                    OK - Supported`
        - `TLS_FALLBACK_SCSV:                 OK - Supported`
        - `Supported curves:                  X25519, X448, secp256r1, secp384r1, secp521r1`
      - Keep compliance failures as errors:
        - `ip.darklab.sh:443: FAILED - Not compliant.`
  - Port scanners:
    - `naabu`
      - Current summary: `[summarize not active]`.
      - Add `naabu`-scoped host:port result matcher:
        - `ip.darklab.sh:80`
        - `ip.darklab.sh:443`
      - Treat `[INF] Found 2 ports on host ip.darklab.sh (107.178.109.44)` as a summary line, not a finding.
    - `rustscan`
      - Current summary catches embedded Nmap findings, but misses RustScan's own `Open` lines.
      - Add `rustscan`-scoped matcher:
        - `Open 107.178.109.44:443`
        - `Open 107.178.109.44:80`
      - Keep existing `Discovered open port...` and Nmap table matchers.
    - `masscan`
      - Current summary catches all eight `Discovered open port...` lines. No matcher change needed from this corpus.
  - `nuclei`
    - Current summary misses all 21 template matches and only reports warnings/errors.
    - Add a `nuclei`-scoped template result matcher for lines with template id, protocol, severity, target, and optional extracted value:
      - `[waf-detect:nginxgeneric] [http] [info] https://ip.darklab.sh`
      - `[tls-version] [ssl] [info] ip.darklab.sh:443 ["tls12"]`
      - `[tls-version] [ssl] [info] ip.darklab.sh:443 ["tls13"]`
      - `[tech-detect:nginx] [http] [info] https://ip.darklab.sh`
      - `[cpanel-backup-exclude-exposure] [http] [info] https://ip.darklab.sh/cpbackup-exclude.conf`
      - `[http-missing-security-headers:strict-transport-security] [http] [info] https://ip.darklab.sh`
      - `[dns-saas-service-detection] [dns] [info] ip.darklab.sh ["fw-vx2-vp1.darklab.sh"]`
      - `[ssl-issuer] [ssl] [info] ip.darklab.sh:443 ["Let's Encrypt"]`
      - `[ssl-dns-names] [ssl] [info] ip.darklab.sh:443 ["ip.darklab.sh"]`
    - Treat `[INF] Scan completed in 4m. 21 matches found.` as a summary line.
    - Keep `[WRN] Found 2 templates with runtime error...` and skipped/unresponsive target lines as warnings/errors.
  - Implementation notes:
    - Add command-scoped helper functions rather than growing only `_SIGNAL_PATTERNS["findings"]`.
    - Keep noisy global excludes for banners, progress, update checks, request counts, and completion footers.
    - Add focused tests using these exact example lines so future command-output drift is visible.
    - Consider storing structured finding metadata later (`kind`, `host`, `port`, `url`, `severity`, `record_type`) once the structured output model work begins.

## Research

No research items are currently tracked.

---

## Known Issues

No known issues are currently tracked.

---

## Technical Debt

No technical debt items are currently tracked.

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

- **Tool-specific guidance**
  - Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `naabu`, or `nuclei`.
  - Good fit for the existing help / FAQ / welcome surfaces.
  - Merge this with onboarding and command hints into a broader user guidance layer:
    - command-specific caveats
    - what to expect while a tool runs
    - examples of when to use one tool vs another

- **Command catalog future-state**
  - Add `commands search <term>` for roots, descriptions, categories, examples, and flag text.
  - Add `commands --json` or `commands info --json <root>` for debugging, export, and future UI reuse.
  - Add optional richer registry fields such as `details`, `notes`, `common_flags`, or `gotchas` when a flag or tool needs more than a short autocomplete description.
  - Add command-specific guidance for web-shell behavior, including injected safe defaults, quiet-running tools, generated Files output, and managed session state.
  - Add autocomplete side previews later: when a root, subcommand, or flag is highlighted, show the command description or flag note in a small help pane.
  - Add hover/focus cards for FAQ chips once the command-details modal behavior has settled.
  - Consider including pipe helpers in a separate “Pipes” section once command catalog UX exists.
  - Consider linking command catalog entries to real `man` output where available, while keeping app-native allowed-subset details primary.

- **Command outcome summaries**
  - For selected tools, generate short app-native summaries below the raw output. Security tool output is high-volume; a clear findings layer is what separates a purpose-built tool from a raw terminal.
  - Keep raw output primary — the summary is additive, never a replacement.
  - Start narrow: nmap (open ports + service table), dig (records returned), curl (status code + redirect chain), openssl s_client (cert expiry + trust chain).
  - The structured output model (see Architecture) is the right long-term foundation. Build this feature so it can move onto that model later instead of requiring it up front.

- **Run comparison enhancements**
  - Future-state enhancements after the v1 history-row comparison flow has real use.
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
    - Project baseline compare once projects exist.
    - Snapshot/permalink compare if the run-vs-run model continues to work well.
    - `Export comparison` once share/export packages have a stable artifact model.
  - Future UX/testing:
    - Consider date-range filters in the manual compare picker if day grouping plus `Load More` is not enough for deep history.
    - Add Playwright coverage for the compare launcher/result flow on desktop and mobile after the UI settles.
    - Add focused large/noisy comparison regression coverage if real-world outputs expose performance issues beyond current backend and unit coverage.

- **Bulk history operations**
  - The history drawer can delete all or delete non-favorites. Adding multi-select (checkbox mode) with bulk delete, bulk export to JSONL/txt, and bulk share would close a real gap when clearing out a session after an engagement or exporting selected findings.

- **Autocomplete suggestions from output context**
  - When a previous command's output is in the active tab, `| grep` completions could suggest patterns already present in that output — IP addresses, hostnames, status codes, CVE strings — as candidates alongside the generic flag list.
  - Narrow but would make the pipe stage feel predictive rather than generic.

- **Mobile share ergonomics**
  - The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
    - save/share actions tuned for one-handed use
    - clearer copy/share/export affordances inside the mobile shell
    - better share handoff after snapshot creation

---

## Architecture

- **Full reconnectable live stream**
  - Explore a live-output path that can fully resume active command streams after reload rather than restoring a placeholder tab and polling for completion.
  - This is separate from the current active-run reconnect support and would likely require:
    - a per-run live output buffer
    - resumable stream offsets or event IDs
    - multi-consumer fan-out instead of one transient SSE consumer
    - explicit lifecycle cleanup once runs complete
  - Best fit is a dedicated live-stream architecture pass rather than incremental UI polish.

- **Structured output model**
  - Preserve richer line/event details consistently for all runs.
  - This would improve search, comparison, redaction, exports, and permalink fidelity.
  - Command outcome summaries are buildable without this foundation, but design them so they can move onto the structured model later. Summary parsers should consume structured line events, not re-parse raw text forever.

- **Unified terminal built-in lifecycle**
  - Browser-owned built-ins (`theme`, `config`, and `session-token`) need browser execution for DOM state, local storage, clipboard, and transcript-owned confirmations, while server-owned built-ins naturally flow through `/runs`.
  - The long-term cleanup target is one terminal-command lifecycle after execution:
    - normalize built-in output into a shared result shape
    - apply pipe helpers against that shape
    - mask sensitive command arguments once
    - render transcript output once
    - persist server-backed history once
    - load recents and prompt history from the same saved run model
  - Keep execution ownership separate where it matters, but remove duplicated recents/history/pipe/persistence glue so browser-owned and server-owned built-ins cannot drift.

- **Plugin-style helper command registry**
  - Turn the built-in command layer into a cleaner extension point for future app-native helpers.

- **Lightweight Jinja base template**
  - `index.html`, `permalink_base.html`, and `diag.html` now all share the same ~10 lines of `<head>` bootstrap (charset, viewport, color-scheme meta, favicon, `fonts.css`, `styles.css`, theme var includes, and the two vendor scripts). With three templates the duplication is starting to pay for the indirection.
  - A `base.html` factoring out the common `<head>` and `data-theme` body attribute would prevent drift and make adding a fourth page type trivial.

- **Interactive PTY mode for screen-based tools**
  - Explore an optional PTY + WebSocket + browser terminal emulator path for a small allowlisted set of interactive or screen-redrawing tools such as `mtr`, without turning the app into a general-purpose remote shell.
  - Best fit is a separate interactive-command mode or tab type, not a full browser shell session.
  - This would be a larger architecture change because it needs:
    - server-side PTY management
    - bidirectional browser transport
    - terminal resize handling
    - stricter command scoping and lifecycle cleanup
