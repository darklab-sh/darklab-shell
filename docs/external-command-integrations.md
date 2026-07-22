# External Command Integrations

This contributor guide explains how darklab_shell adapts installed command-line tools so they work cleanly inside the web shell, container sandbox, and personal/team Files workspace model. Users looking for command discovery, run modes, Files, Secrets, or provider setup should start with [Bundled Tools](tools.md).

The goal is not to document every flag a tool supports. The goal is to make app-owned behavior visible: command rewrites, environment overrides, workspace file handling, permission assumptions, and validation rules.

---

## Integration Principles

- Preserve the command the user typed in history and UI wherever possible.
- Rewrite only when the default tool behavior is broken, unsafe, misleading, or inaccessible in the web shell runtime.
- Keep rewrites safe to apply more than once so users can provide the explicit flag themselves without duplicate options.
- Prefer active Files workspace paths for user-visible inputs and outputs.
- Keep useful session-owned files out of `/tmp/.config` when users should be able to inspect them later.
- Treat external-tool adaptation as part of the command trust boundary; all filesystem path expansion must happen through command validation and workspace helpers.

---

## Runtime Model

User-submitted external commands run as the `scanner` user with the shared `appuser` group. The app process runs as `appuser`.

The scanner wrapper sets `HOME=/tmp` so tools that insist on a writable home can use the container tmpfs instead of the read-only application filesystem. That default is useful for caches and temporary tool state, but command-specific integrations may override narrower environment variables when a tool's useful state needs to be session-scoped.

Files are app-managed. Users can name relative files such as `targets.txt` or `amass`, and command validation rewrites those values to the active hashed personal or team workspace path before subprocess launch.

Command-specific runtime behavior is declared in `app/conf/commands.yaml`. The registry supports injected flags, managed workspace directories, environment variables derived from managed workspace paths, and encrypted secret requirements. Python handles the common plumbing; the command registry handles the tool-specific rules.

---

## Integration Matrix

| Tool | App adaptation | Why |
| ---- | -------------- | --- |
| `mtr` | Adds `--report-wide` when no report mode flag is present, unless the run is started through the Interactive PTY trigger. | Plain shell runs need clean line-oriented output for streaming and saved history; `mtr --interactive <host>` uses the PTY path for the live redraw view when the feature is enabled. |
| `nmap` | Adds `-sT` while raw readiness is inactive. When the operator opt-in is ready, it adds trusted `NMAP_PRIVILEGED=1`, leaves the scan mode to Nmap, and reveals raw-only autocomplete choices. Restricted-CIDR deployments also require the matching root-owned firewall marker. | Connect scans remain the portable default, while Linux capability-backed deployments can use SYN, UDP, OS detection, traceroute, and raw host discovery without root or Docker privileged mode. Spoofing and link-layer bypass options remain blocked. |
| `nuclei` | Adds `-ud /tmp/nuclei-templates` when no update-directory flag is present, wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<active workspace>/tools` when Files are enabled, and declares workspace paths for response stores, Markdown/SARIF/JSON/JSONL exports, trace/error logs, resume files, and selected config/secret inputs. | Template storage must be writable under the read-only container filesystem, while useful evidence and logs should be visible in Files without exposing template caches as artifacts. |
| `subfinder` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<active workspace>/tools` when Files are enabled and declares workspace paths for list input, per-domain output directories, resolver lists, config files, and provider config files. | Subfinder otherwise falls back to `$HOME/.config` under `/tmp`, hiding useful artifacts; provider configs can contain API keys and remain owner-scoped rather than share/export artifacts. |
| `dnsx` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<active workspace>/tools` when Files are enabled and declares workspace paths for list input, wordlists, and normal outputs. | DNSX shares the ProjectDiscovery config path conventions and should keep generated state under the active owner folder. |
| `httpx` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<active workspace>/tools` when Files are enabled and declares workspace paths for list/raw-request inputs, normal outputs, response/screenshot store directories, and config files. | Response stores and screenshots are high-value evidence, while config state should remain visible only to the active personal/team owner. |
| `tlsx` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<active workspace>/tools` when Files are enabled and declares workspace paths for list, resolver, config, CA certificate, and output files. | TLS evidence is most useful when JSONL output and supporting resolver/config files stay with the active Files workspace. |
| `cdncheck` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<active workspace>/tools` when Files are enabled and declares workspace paths for resolver and output files. | CDN/cloud/WAF classifications are operator context rather than vulnerabilities, and saved JSONL rows should remain tied to the run workspace. |
| `wget` | When Files are enabled, adds `-P <current workspace folder>` when no directory-prefix flag is present, and declares `-P` / `--directory-prefix` as workspace directory flags. | Default downloads land in the user's Files area instead of failing against the read-only container root, while explicit download folders still stay under the active workspace. |
| `katana` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<active workspace>/tools` when Files are enabled and declares workspace paths for list/config inputs, error logs, stored response directories, and stored field directories. | Katana can generate useful secondary request/response and field-extraction artifacts; keeping those directories in Files makes them inspectable and reusable. |
| `naabu` | Adds `-scan-type c` while raw readiness is inactive or `-scan-type s` when active, wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<active workspace>/tools` when Files are enabled, and declares workspace paths for host lists, exclude lists, ports files, and normal outputs. | Connect mode remains available everywhere; SYN mode is selected only after capability checks pass and is always inactive when restricted CIDRs are configured. |
| `masscan` | Allows live and interactive scans only while Masscan's raw readiness is active; help remains available otherwise. Workspace target lists and outputs still use the normal managed file path. | Masscan has no connect fallback, and its packet-socket path remains unavailable whenever restricted CIDRs are configured. |
| `trufflehog` | Allows workspace folder scans through `filesystem --directory`, allows HTTPS Git repository scans through `git`, declares include/exclude regex files as workspace inputs, and rejects non-HTTPS Git repository arguments before launch. | Secret scanning should not read arbitrary local paths, leave custom clone directories behind, or accept SSH/file Git URLs inside the web shell runtime. |
| `puredns` | Allows `bruteforce` with the packaged SecLists DNS wordlist and declares resolver, trusted-resolver, domain-list, valid-domain, raw massdns, and wildcard output flags as workspace paths. | puredns should use explicit resolver files and save useful outputs in Files instead of relying on hidden home-directory defaults. |
| `amass enum` / `amass subs` / `amass track` / `amass viz` | Adds managed `-dir tools/amass` when absent, rewrites it to the active workspace, and launches with `XDG_CONFIG_HOME=<active workspace>/tools`. | Amass v5 is database-first and auto-starts `amass engine`; the engine and CLI must use the same per-owner database path instead of falling back to `$HOME/.config/amass`. |
| `ipinfo` | Injects optional `IPINFO_TOKEN` from the encrypted secrets vault and blocks config-writing/token-on-command-line flows such as `init`, `config`, `completion install`, and inline token flags. | Users can run the official IPinfo CLI for provider-native IP/ASN output without storing tokens in shell history or letting the CLI write persistent config inside the container. |
| `wpscan` | Injects optional `WPSCAN_API_TOKEN` from the encrypted secrets vault and blocks inline `--api-token` use. | Regular WordPress scans still work without a key, while API-backed vulnerability data can be enabled without putting the token in command history or argv. |
| `urlscan-cli` | Injects `URLSCAN_API_KEY` from the encrypted secrets vault and blocks key/config/completion setup, inline key flags, and stdin-driven scan/result forms. | Users can submit URLs, fetch scan results, and search urlscan.io without writing keys to a local keyring/config file or putting tokens into command history. |
| `chaos` | Injects `PDCP_API_KEY` from the encrypted secrets vault and blocks inline key flags, updater flows, list-file input, and direct output-file writes. | Users can query ProjectDiscovery Chaos for domain subdomains while keeping the provider key in the app vault and avoiding unmanaged file reads/writes. |
| `trufflehog github` / `trufflehog gitlab` | Injects `GITHUB_TOKEN` or `GITLAB_TOKEN` only for the matching source and blocks inline tokens, credential-bearing URLs, auth-in-URL, custom clone paths, and retained clones. | Users can scan private repositories, organizations, groups, and self-hosted provider endpoints without putting a PAT in command history or stored output. |

---

## Workspace-Aware File Flags

Workspace-aware flags are declared in `app/conf/commands.yaml` under each command's `workspace_flags` entries.

Validation behavior:

- Relative workspace values are resolved under the active personal/team workspace.
- Absolute paths are not rewritten and still pass through the normal deny rules.
- Read flags require the Files entry to exist in the active workspace.
- Write and read/write flags prepare the destination path before subprocess launch.
- Directory flags can create and prepare managed session directories.

This covers normal file input/output tools such as `nmap -iL`, `nmap -oN`, `curl -o`, `wget -P`, `ffuf -o`, `subfinder -dL`, `tlsx -l`, `cdncheck -o`, `trufflehog filesystem --directory`, `puredns --resolvers`, `naabu -list`, `nuclei -l`, and Amass database directories. It also covers selected ProjectDiscovery flags that create directories, such as `katana -srd`, `katana -sfd`, `httpx -srd`, `subfinder -oD`, and `nuclei -srd` / `-me`.

## Runtime Adaptations

Runtime adaptations are declared in `app/conf/commands.yaml`:

```yaml
runtime_adaptations:
  inject_flags:
    - flags: ["--report-wide"]
      position: prepend
      unless_any: ["--report", "--report-wide", "-r"]
      notice: "Note: ..."
    - flags: ["env", "XDG_CONFIG_HOME={session_workspace}/tools"]
      position: command_prefix
      requires_workspace: true
    - flags: ["-sT"]
      unless_raw_packets: true
    - flags: ["env", "NMAP_PRIVILEGED=1"]
      position: command_prefix
      requires_raw_packets: true
  managed_workspace_directory:
    flag: -dir
    directory: tools/amass
    subcommands: [enum, subs, track, viz]
    skip_if_any: [-h, -help, --help]
    reject_alternate: true
  environment:
    - name: XDG_CONFIG_HOME
      value: "{managed_workspace_parent}"
      managed_directory_flag: -dir
```

`inject_flags` rewrites command argv tokens with `shlex.join`, so injected values stay safely quoted when paths contain spaces or shell metacharacters. `position: prepend` inserts tokens after the command root, `position: append` adds trailing tokens, and `position: command_prefix` inserts tokens before the command root for wrappers such as `env NAME=value`. `unless_any` and `unless_any_regex` keep rewrites from duplicating flags and prevent help/version commands from being changed. `requires_workspace: true` skips the injection unless Files are enabled and an active workspace is available. `requires_raw_packets: true` and `unless_raw_packets: true` select adaptations from effective runtime readiness rather than the setting alone. Injected tokens may use `{session_workspace}` to point at the active personal/team hashed workspace directory. `notice` prints a short terminal message when a rewrite needs user-facing explanation.

`managed_workspace_directory` is evaluated by workspace-aware validation. When it applies, the declared directory is injected if absent, rewritten through the same workspace directory helper as user-provided directory flags, and optionally rejects alternate user values so tool state does not split across multiple databases.

`environment` wraps the final execution command with `env NAME=value ...` after workspace path rewriting. Entries can use the same `requires_raw_packets` readiness gate and `unless_any` exclusions as flag injection. Nmap uses a command-prefix injection for the fixed `NMAP_PRIVILEGED=1` value so it composes with conditional scan flags; workspace-backed tools use `{managed_workspace_parent}`, which resolves from the declared managed directory flag.

Encrypted credentials use a separate `requires_secrets` declaration instead of the `environment` wrapper. At launch, `/runs` looks up the current session's matching encrypted secrets, decrypts them in memory, and passes them through `subprocess.Popen(env=...)`. Secret values are never inserted into the shell command string. Required missing secrets block launch with a clear error; optional missing secrets log a warning and let the command run without that env var. A declaration can use `subcommands` to scope a credential to one or more command modes; TruffleHog uses this so `github` receives only `GITHUB_TOKEN`, `gitlab` receives only `GITLAB_TOKEN`, and filesystem or ordinary Git scans require neither.

```yaml
requires_secrets:
  - env: SHODAN_API_KEY
    optional: false
  - env: VT_API_KEY
    inject_env: VTCLI_APIKEY
    fallback_envs:
      - VTCLI_APIKEY
```

`inject_env` is for tools whose runtime variable name differs from the app-facing secret name. `fallback_envs` lets users store an accepted vendor-native name too. The shipped VirusTotal CLI entry accepts `VT_API_KEY` or `VTCLI_APIKEY` from the encrypted vault and always launches `vt` with `VTCLI_APIKEY` in its environment.

Shodan's CLI still expects its `shodan init` config file. Users do not need to run that setup command inside darklab_shell: when a Shodan command launches, the app writes the vault-backed `SHODAN_API_KEY` into a temporary per-run Shodan config directory, points that command at the temporary home, and removes the directory when the command exits. The key stays out of command text, history, and stored output.

The Options Secrets picker reads this command-registry metadata so users see the known tool key names first. Custom names remain available for local registry overlays.

`ipinfo` declares `IPINFO_TOKEN` as optional. The CLI can show limited unauthenticated output, while saved tokens unlock the provider data attached to the user's IPinfo account. `wpscan` follows the same optional-secret pattern with `WPSCAN_API_TOKEN`: normal scans run without it, and token-backed vulnerability data is available when the secret is saved.

`urlscan-cli` and `chaos` declare required CLI secrets. `urlscan-cli` receives `URLSCAN_API_KEY`; `chaos` receives `PDCP_API_KEY`. Their setup and inline-key flags are blocked so the vault stays the only supported key path.

Run output is also filtered before it is captured or streamed: absolute paths under the active personal/team workspace are displayed as user-facing workspace paths. For example:

```text
Creating resume file: /workspaces/sess_<hash>/tools/katana/resume-abcd.cfg
```

is shown and stored as:

```text
Creating resume file: /tools/katana/resume-abcd.cfg
```

---

## App-Native Intel Lookups

The `intel` built-in uses the same provider keys when a provider needs them, without launching the vendor CLI:

- `intel ip <ip>` queries Shodan, Shodan InternetDB, Censys, GreyNoise, AlienVault OTX, AbuseIPDB, IPinfo, Team Cymru, URLhaus, ThreatFox, FOFA, ZoomEye, and RouteViews.
- `intel domain <domain>` queries VirusTotal, AlienVault OTX, crt.sh, URLhaus, ThreatFox, urlscan.io, SecurityTrails, FOFA, and ZoomEye.
- `intel url <url>` queries URLhaus, ThreatFox, urlscan.io, FOFA, and ZoomEye.
- `intel hash <md5|sha1|sha256>` queries VirusTotal, AlienVault OTX, URLhaus, and ThreatFox after autodetecting the hash type by hex length, and checks SHA1 hashes against HIBP Pwned Passwords by sending only the first five SHA1 characters.
- `intel cve <CVE-ID>` queries NVD and Vulners.

Provider metadata lives in `app/services/intel/registry.py`, including display labels, supported entity types, secret names and aliases, cache scopes, rate-limit config keys, and user-facing usage labels. FOFA uses `FOFA_EMAIL` plus `FOFA_KEY`, `FOFA_API_KEY`, `FOFA_APIKEY`, or `FOFA_TOKEN`, and search calls need an F-point balance. ZoomEye uses `ZOOMEYE_API_KEY` against the regional API and needs available resource credits. Provider responses are normalized through `app/services/intel/schema.py` before they are rendered, cached, or logged. Each provider pane reports whether the result came from cache, was blocked by rate limiting or quota backoff, or is missing the needed encrypted secret. If all keyed providers for a lookup are missing, the built-in exits with setup guidance only when no no-key or optional-key provider can run. If only some providers are missing, available providers still render normally and the missing providers show placeholders. The same provider metadata feeds the Options Provider Status modal, `secret show-consumers`, the `providers` alias, and the Options Secrets picker for providers that need stored keys, so app-native HTTP providers and CLI-backed provider wrappers are discoverable from one place.

The built-in refuses private, loopback, and other non-public IP addresses by default because passive-intel providers cannot meaningfully classify them. Users can pass `--include-private` when they intentionally want to send that address to configured providers.

Intel response bodies are raw-only outside the live terminal. Snapshot shares, public non-owner run permalinks, and local HTML/PDF exports replace app-native `intel` output groups with `Intel data omitted from share`; saved text exports and owner history restores keep the original transcript.

External command output is also scanned for reusable entity hints as it streams. Public IPs, hostnames, MD5/SHA1/SHA256 hashes, and CVE IDs are attached to the same per-line metadata record as findings/warnings/errors/summaries. The metadata is stored with history previews and full-output artifacts so later triage surfaces can use those entities without making the browser re-parse raw transcripts.

---

## Interactive PTY Commands

Interactive PTY support is declared in `app/conf/commands.yaml` with an `interactive` block per command. The currently shipped PTY commands are:

- `nc --interactive <host> <port>`
- `telnet --interactive [host] [port]`
- `mtr --interactive <host>`
- `ffuf --interactive ...`
- `masscan --interactive ...`

These trigger the dedicated `/pty/runs` path instead of normal `/runs`. The trigger flag is stripped before the process starts, validation re-checks the resulting command, and the command's registry metadata owns terminal size, input policy, max runtime, and saved transcript mode.

Plain non-PTY commands keep their normal adaptations. For example, `mtr darklab.sh` is rewritten to report mode for readable saved output, while `mtr --interactive darklab.sh` opens the live terminal view when Interactive PTY is enabled.

---

## ProjectDiscovery

ProjectDiscovery tools commonly resolve config and resume paths through `XDG_CONFIG_HOME`, falling back to `$HOME/.config` when the variable is absent. Because the scanner wrapper keeps `HOME=/tmp`, those default files would otherwise be written to anonymous tmpfs paths outside the session Files view.

When workspace storage is enabled, `subfinder`, `dnsx`, `httpx`, `tlsx`, `cdncheck`, `katana`, `naabu`, and `nuclei` are launched with:

```bash
env XDG_CONFIG_HOME=/workspaces/sess_<hash>/tools <tool> ...
```

This keeps useful generated state under session-visible folders such as:

```text
/tools/katana
/tools/subfinder
/tools/dnsx
/tools/httpx
/tools/tlsx
/tools/cdncheck
/tools/naabu
/tools/nuclei
```

`nuclei` still receives `-ud /tmp/nuclei-templates` unless the user provides an update directory. Template caches are intentionally left in tmpfs because they are large, reusable container state rather than session evidence.

Nuclei output metadata records template provenance for each run. The app classifies the source as the managed `/tmp/nuclei-templates` cache, an actual session workspace template path passed through `-t`, a pinned-looking `nuclei-templates` clone path, an operator-updated template set when `-update-templates` is used, or a custom update directory. Normal relative template selectors such as `http/`, `cves/`, or `ssl/...` are treated as managed-cache selectors, not workspace templates. Saved output, Run Details restores, and Nuclei JSONL Atlas imports keep this provenance with the line or import `source_detail`, so later review can tell which template source produced the finding.

Several ProjectDiscovery flags are also declared as workspace-aware paths so generated files and secondary outputs can be inspected in Files:

- `katana -srd` / `-store-response-dir` and `katana -sfd` / `-store-field-dir`
- `httpx -srd` / `-store-response-dir`, including response stores and screenshot output directories
- `tlsx` list, resolver, config, CA certificate, and output files
- `cdncheck` resolver and output files
- `nuclei -srd` / `-store-resp-dir`, `-me`, SARIF/JSON/JSONL exports, trace/error logs, and resume/config inputs
- `subfinder -oD`, resolver lists, config files, and provider config files
- `naabu` host-list, exclude-list, ports-file, and output paths

Structured output handling:

- `tlsx -json` rows become findings with domain/IP/certificate-hash Atlas entities and warnings when certificate state flags indicate expired, mismatched, revoked, untrusted, self-signed, wildcard, or failed probe states.
- `cdncheck -jsonl` rows become summaries with host/IP Atlas entities. CDN/cloud/WAF matches are context, not vulnerabilities.
- Plain `tlsx` and `cdncheck` text output is still streamed and stored, but it does not create Atlas entities, findings, warnings, or summaries. Use `-json` for `tlsx` and `-jsonl` for `cdncheck` when you want structured capture.

App-native pipe helpers:

- `jq` is a safe JSON/JSONL selector implemented by darklab_shell, not the host `jq` binary. It supports simple field selection, array iteration, key-existence filters, equality filters, contains filters, pretty JSON output by default, `-c` compact JSON output, and `-r` scalar text output. It rejects arbitrary jq programs and reports malformed input without echoing the source line.

Security note: ProjectDiscovery provider/config files can contain API keys or other operator secrets. The Files view can show them to the current session owner. Share and permalink exports remain transcript-only, but project evidence packages can include selected raw workspace artifacts when artifact inclusion is enabled; redacted packages exclude raw artifacts. Do not select provider/config files for evidence packages unless the operator intends to include those secrets in the archive.

---

## TruffleHog

TruffleHog is exposed for four managed scan shapes:

- `trufflehog filesystem --directory <folder> --json` scans a folder from Files.
- `trufflehog git https://... --json` scans an HTTPS Git repository.
- `trufflehog github --repo https://... --json` scans one or more GitHub repositories, while `--org` can enumerate an organization.
- `trufflehog gitlab --repo https://... --json` scans one or more GitLab repositories, while `--group-id` can enumerate a group and its subgroups.

GitHub scans require `GITHUB_TOKEN`; GitLab scans require `GITLAB_TOKEN`. Both values come from the active personal or team secrets vault and are passed through the vendor-supported environment variables. Inline `--token` values, credential-bearing URLs, and `--auth-in-url` are rejected so PATs cannot enter command history, argv, transcripts, or logs. `providers` and `secret show-consumers` report whether both command credentials are configured.

Repository and `--endpoint` values for GitHub and GitLab must be credential-free HTTPS URLs. A custom HTTPS `--endpoint` supports GitHub Enterprise and self-hosted GitLab. Local paths, `file://` repositories, and `ssh://` repositories are rejected before launch. The registry also blocks custom clone paths, no-cleanup mode, trust-local-git-config, profile/config files, and provider sources outside the four exposed scan paths.

`--include-paths` and `--exclude-paths` can read regex files from Files for filesystem, Git, GitHub, and GitLab scans. TruffleHog writes findings to stdout; stdout JSON rows are the supported report channel for structured capture. Organization, group, and all-accessible-repository scans are allowed, but their fan-out remains bounded by the app's normal command timeout and resource limits.

TruffleHog scan commands receive `--json` automatically unless the user already passed it or is asking for help. Every detector result is treated as a finding, including unverified and multipart results. Before output is streamed, stored, written to Files, shared, exported, or materialized into findings, the live transcript masks `Raw`, `RawV2`, `Redacted`, and every `SecretParts` value, then removes copies of those values from the rest of the JSON row. Persisted Atlas finding text is rebuilt from detector, verification, and source-location metadata instead of trusting vendor secret fields as safe display text. Redacted snapshots also replace PEM and PGP private-key blocks from any command, including blocks printed across several lines. If a TruffleHog command is ever run outside that managed JSON path, plain text output remains transcript-only and does not create structured findings.

---

## puredns

puredns is exposed through `bruteforce` with the packaged SecLists DNS wordlist:

```bash
puredns bruteforce /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt example.com --resolvers resolvers.txt --write puredns-results.txt
```

The registry rejects `bruteforce` commands that omit `--resolvers <file>`, so puredns uses an explicit resolver list from Files instead of its home-directory default. `--resolvers-trusted`, `--domains`, `--write`, `--write-massdns`, and `--write-wildcards` are workspace-aware.

puredns valid-domain rows are treated as findings and materialize domain Atlas entities. Wildcard status rows are treated as warnings. Workspace output files still flow through the run-file artifact records created from workspace flag validation.

The registry supports `puredns bruteforce` with the packaged DNS wordlist. `puredns resolve <file>` and session wordlists as positional operands are not part of the supported command surface; use workspace-aware resolver and output flags for session files.

---

## Grouped Short Flags

Command policy can allow POSIX-style grouped short flags only when the individual flags are explicitly marked in `app/conf/commands.yaml`:

```yaml
autocomplete:
  flags:
    - value: -z
      allow_grouping: true
    - value: -v
      allow_grouping: true
```

Validation treats grouped tokens such as `-zv` and `-vz` as equivalent to those declared single-letter flags only for that command root. Flags that take values and multi-character flags such as `-sV` are not grouped unless represented by separate one-letter flags with `allow_grouping: true`.

`nc` uses this to keep policy compact:

```yaml
policy:
  allow:
    - nc -z
```

That allows `nc -zv`, `nc -vz`, and `nc -zvn` without listing every ordering, while deny entries such as `nc -e` and `nc -c` still take precedence.

---

## Help Output Metadata

Command help flags live with the command entry so the app can treat help output consistently. The same metadata keeps help transcripts out of findings and Atlas entity discovery, lets `/runs` skip required-secret preflight for safe help commands, and lets the container smoke corpus run help examples for tools that normally require encrypted secrets:

```yaml
help:
  flags:
    - -h
    - --help
autocomplete:
  examples:
    - value: shodan --help
      description: Show help and usage
      smoke:
        profile: unauthenticated
```

Only mark an example as `smoke.profile: unauthenticated` when it can run without provider credentials or workspace setup.

---

## Amass

Amass needs special handling because the useful result set lives in its database, not only in stdout.

### Problem

The scanner wrapper intentionally sets `HOME=/tmp`. Without an override, Amass can create its default database under:

```text
/tmp/.config/amass
```

That becomes a cross-session tmpfs location, not a session workspace location.

Amass v5 also auto-starts `amass engine`. The engine can initialize its own default config/database path before or alongside `amass enum`, so merely adding `enum -dir <path>` is not enough if the engine still defaults to `$HOME/.config/amass`.

### App Contract

For `amass enum`, `amass subs`, `amass track`, and `amass viz`, validation enforces a managed workspace directory:

```text
tools/amass
```

If the user omits `-dir`, the app injects it. If the user provides another directory for database commands, validation rejects it to avoid split databases.

The execution command is wrapped like this after workspace rewriting:

```bash
env XDG_CONFIG_HOME=/workspaces/sess_<hash>/tools amass enum ... -dir /workspaces/sess_<hash>/tools/amass
```

That makes Amass' default config path and explicit `-dir` converge on:

```text
/workspaces/sess_<hash>/tools/amass
/workspaces/team_<hash>/tools/amass
```

Expected validation signals:

- `asset.db`, `asset.db-shm`, and `asset.db-wal` grow under the active personal/team workspace.
- `/tmp/.config/amass` is not created for app-launched Amass database commands.
- `amass subs -d <domain> -names` reads findings produced by prior `amass enum` runs in the same active workspace.
- `amass track` and `amass viz` read the same managed database used by `enum` and `subs`.
- A different personal scope or team gets a different workspace directory and does not see the previous owner's Amass database.

Additional workspace output handling:

- `amass subs -o <file>` writes a Files entry in the active workspace.
- `amass viz -o <directory>` writes visualization artifacts under an active workspace directory.

### Manual Smoke

Use a domain you are allowed to enumerate:

```bash
amass enum -d example.com -timeout 10
amass subs -d example.com -names
amass track -d example.com
amass viz -d example.com -d3 -o amass-viz
```

From inside the container, verify database placement:

```bash
find /workspaces -path '*amass*' -name 'asset.db*' -ls
find /tmp/.config -path '*amass*' -ls
```

The first command should show files under the active `sess_*` workspace. The second command should not show an Amass database created by the app-launched run.

---

## Nmap

`nmap` can use raw-socket-related Linux capabilities for SYN scans, OS fingerprinting, and similar features.

The bundled image applies the required file capabilities to all three approved raw scanners:

```bash
setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap
setcap cap_net_raw,cap_net_admin+eip /usr/bin/masscan
setcap cap_net_raw,cap_net_admin+eip /usr/local/bin/naabu
```

TCP connect scanning remains the default: `rewrite_command()` injects `-sT` when no scan mode is present. Operators can set `RAW_PACKET_SCANNING_ENABLED=true` on Linux Docker hosts. Once the runtime confirms `CAP_NET_RAW`, the effective/permitted Nmap file capability, and a compatible executable policy, command preparation adds `NMAP_PRIVILEGED=1` and leaves the scan mode to Nmap. Raw-dependent options fail with connect-mode guidance when readiness is inactive; plain `-sT` stays unchanged, mixed connect/raw options fail clearly, and spoofing/link-layer bypass options are always blocked. With `RESTRICTED_COMMAND_INPUT_CIDRS` configured, the adaptation adds `--send-ip` only after the matching root-owned firewall marker confirms the scanner-user OUTPUT boundary.

Workspace integration is separate from the scan-mode rewrite:

- `-iL` and script-args file flags can read active workspace files.
- output flags such as `-oN`, `-oX`, `-oG`, `-oA`, and `-oS` can write active workspace files.

---

## Naabu

`naabu` supports SYN scanning through libpcap/gopacket and TCP connect scanning as a portable fallback.

The app injects:

```bash
-scan-type c
```

when neither `-scan-type` nor `-st` is present and raw readiness is inactive. Ready deployments inject `-scan-type s` instead. An explicit connect choice is preserved in either mode. When `RESTRICTED_COMMAND_INPUT_CIDRS` is set, Naabu always remains on the connect path. Separate host or Docker bridge firewall rules do not change that readiness decision.

Workspace integration covers list input and output files:

- `-l`, `--list`, and `-list` can read active workspace files.
- `-o` and `--output` can write active workspace files.

---

## Masscan

`masscan` is raw-packet only and has no TCP connect fallback. Live and interactive scans are available only when the operator opt-in is enabled and Masscan's Linux capability, binary, and file-capability readiness checks pass. Its help path remains available when readiness is inactive; actual scans return a short readiness error with RustScan or `nmap -sT` as connect-mode alternatives.

When `RESTRICTED_COMMAND_INPUT_CIDRS` is set, Masscan scans are always unavailable because its packet-socket traffic does not use the scanner-user OUTPUT boundary. Separate host or Docker bridge firewall rules do not reactivate it.

Workspace integration covers target lists and output files:

- `-iL` can read an active workspace target list.
- `-oL`, `-oJ`, `-oX`, `-oG`, `-oB`, and `--output-filename` can write active workspace files.

---

## Adding Or Changing An Integration

The registry is the first stop for a new command, but it is not the only stop. Before merging a new external-command adaptation:

- Add or update the command metadata in `app/conf/commands.yaml`.
- Keep user-facing examples aligned with the app-owned rewrite behavior.
- Add backend tests for validation, rewrite, and workspace path handling.
- Add autocomplete tests if examples, flags, or positional hints change.
- Add or update container smoke expectations when the change affects visible examples or workflow steps. The generic smoke corpus applies required-secret declarations to each example's subcommand, skips credentialed examples, and can include registry-declared help examples marked with `smoke.profile: unauthenticated`. Cover credentialed behavior with registry, policy, secret-injection, or keyed smoke tests.
- Document tool-specific behavior here when the app does more than simple allowlist metadata.

Also check the command-specific surfaces that sit outside the registry:

- Output signals: update `app/core/output_signals.py` when the tool has actionable rows that should become findings, warnings, errors, summaries, or Atlas entities. Use real sample lines for tests, especially when the output has banners, progress lines, ANSI styling, escaped payloads, help text, or non-target domains that should stay out of Atlas.
- Target extraction: add command-specific parsing when the target can appear behind a flag, inside a scan-report line, in a list file, or across multiple output rows. Multi-target commands should avoid pretending there is one safe `SOURCE_TARGET` unless the source is unambiguous.
- AI follow-ups: update `app/services/ai/next_commands.py`, `app/services/ai/prompts.py`, and `app/services/ai/suggestions.py` when the tool should appear in next-command suggestions or needs special validation for targets, ports, scripts, wordlists, known-bad flags, duplicate-source commands, or packaged file paths.
- Durable surfaces: confirm Project Findings, Atlas entities, History search, exports, and evidence packages still show the intended output shape when the command creates reusable findings or entities.
- Tests: add focused output-signal tests for transcript parsing, registry/autocomplete/policy tests for command metadata, smoke coverage for visible examples, and AI validation/context tests when the tool can be suggested or rejected by AI.

## Related Docs

- [tools.md](tools.md) - user and operator guidance for bundled tools
- [../CONTRIBUTING.md](../CONTRIBUTING.md#adding-external-commands) - contributor workflow for adding commands
- [../ARCHITECTURE.md](../ARCHITECTURE.md#security-model) - command trust and process boundaries
- [../tests/README.md](../tests/README.md) - test commands and layer guidance
