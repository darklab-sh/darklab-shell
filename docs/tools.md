# Bundled Tools

darklab_shell includes network, web, DNS, TLS, discovery, and reputation tools in its container image. This guide helps users find the right command and understand the app-visible behavior around terminal modes, Files, credentials, and provider access.

## Find the Right Tool

Use the shell's built-in command catalog instead of guessing which flags are supported:

```text
commands
commands search tls
commands info nmap
commands info nmap --json
```

The desktop and mobile Command Registry shows the same descriptions, examples, flags, subcommands, notes, and safe defaults. `help`, `man <command>`, autocomplete, and `which` are useful when you already know the command name.

SecLists is installed at `/usr/share/wordlists/seclists/`. Run `wordlist`, `wordlist search <term>`, or `wordlist show <category>` for copy-friendly paths. Autocomplete suggests installed wordlists only where the selected command accepts one.

## Choose the Right Run Mode

Most tools work in the normal line-oriented shell. darklab_shell adapts a few tools when their native defaults need a full terminal or packet-socket access.

| Tool | Normal behavior | Optional mode |
| --- | --- | --- |
| `mtr` | Runs in readable report mode. | `mtr --interactive <host>` opens its live display when Interactive PTY is enabled. |
| `nmap` | Uses TCP connect scanning when raw readiness is inactive. | The operator raw-packet opt-in can expose SYN, UDP, OS detection, traceroute, and raw host discovery. |
| `naabu` | Uses connect mode when raw readiness is inactive or the target policy is restricted. | Uses SYN mode when the raw readiness check passes. |
| `masscan` | Does not run live scans without raw readiness. | Uses the operator raw-packet opt-in; otherwise choose RustScan or `nmap -sT`. |
| `nc`, `telnet`, `ffuf`, and approved peers | Use normal saved-output mode. | Add `--interactive` when the tool needs a live PTY and the feature is enabled. |

Raw mode is an operator-controlled Linux Docker feature, not a per-command bypass. [Raw-Packet Scanning](../README.md#raw-packet-scanning) explains its platform limits, safety boundaries, fallbacks, and readiness checks.

## Work With Files

When Files is enabled, supported input and output flags accept paths relative to the active personal or team workspace. The app validates and resolves those paths before the tool starts, and it shows workspace paths instead of internal hashed directories in terminal output.

Common examples include:

- `nmap -iL targets.txt -oN scans/nmap.txt`
- `ffuf -w wordlists/paths.txt -o findings/ffuf.json`
- `wget -P downloads https://example.test/file.txt`
- `trufflehog filesystem --directory source --json`
- `puredns bruteforce domains.txt example.test --resolvers resolvers.txt --write results.txt`
- `gau --subs --threads 2 --timeout 10 --o historical-urls.txt example.test`

ProjectDiscovery tools such as `nuclei`, `subfinder`, `dnsx`, `httpx`, `tlsx`, `cdncheck`, `katana`, and `naabu` keep useful config, resume, and generated state under the active workspace's `/tools/` folder. Supported secondary response, screenshot, export, log, and auxiliary-file flags also save through Files. Use the Files panel or the built-in `ls`, `cat`, `mkdir`, `mv`, and confirmed `rm` commands to review and manage those results.

Files is not a general host filesystem. Absolute paths, traversal, hidden paths, symlinks, and unsupported file flags remain blocked. [Session Files](../FEATURES.md#session-files) describes the user-facing limits and team behavior.

## Add Tool Credentials

Save API keys in **Options → Secrets** or start the same protected prompt with `secret set NAME`. `secret list` shows saved names without revealing values, and `providers` shows which intel providers and credentialed commands are ready in the active personal or team scope.

Approved commands receive matching values through their process environment. The key is not added to the command, transcript, history, snapshot, or log. Inline credential flags are blocked where they could leak a secret.

Common CLI bindings include:

| Tool | Secret |
| --- | --- |
| `shodan` | `SHODAN_API_KEY` |
| `vt` | `VT_API_KEY` or `VTCLI_APIKEY` |
| `greynoise` | `GREYNOISE_API_KEY` |
| `ipinfo` | Optional `IPINFO_TOKEN` |
| `urlscan-cli` | `URLSCAN_API_KEY` |
| `chaos` | `PDCP_API_KEY` |
| `wpscan` | Optional `WPSCAN_API_TOKEN` |

Run `commands info <tool>` or open **Options → Secrets → Provider Status** for the current requirement. Team secrets are separate from personal secrets and remain write-only.

## Use Normalized Intel Lookups

The app-native `intel` command combines supported providers into one result with per-provider cache, setup, rate-limit, quota, and outage status:

```text
intel ip 8.8.8.8
intel domain example.com
intel url https://example.com/
intel hash <md5-or-sha1-or-sha256>
intel cve CVE-2025-0001
```

Shodan InternetDB, Team Cymru, live TLS certificate checks, crt.sh, HIBP Pwned Passwords, NVD, and RouteViews work without a saved key. Other providers use the encrypted secret named in Provider Status. IPinfo can return public basics without a token and adds account-backed data when `IPINFO_TOKEN` is saved.

`intel cve` also shows the app's stored FIRST EPSS probability, CISA KEV context, and any accepted NVD status/CVSS/CWE data. Fresh installs have dated offline EPSS/KEV snapshots, so the first part of this prioritization works without a live request. `providers` shows each source mode, date, freshness, and enablement guidance. Operators may load NVD 2.0 JSON locally or retain the result of an explicit Atlas CVE **Refresh intel** action; simply viewing a CVE finding never refreshes a source. EPSS is an exploitation-probability estimate rather than a complete risk score, the CISA due date is federal BOD 22-01 context rather than your remediation deadline, and NVD CVSS does not prove that a scanned product is affected.

FOFA needs `FOFA_EMAIL` plus a key saved as `FOFA_KEY`, `FOFA_API_KEY`, `FOFA_APIKEY`, or `FOFA_TOKEN`, and its search calls need an F-point balance. ZoomEye uses `ZOOMEYE_API_KEY` with the regional `api.zoomeye.ai` service and needs available resource credits. SecurityTrails currently requires a paid account. Provider terms, quotas, and account limits still apply.

Use the external `shodan`, `vt`, `greynoise`, `ipinfo`, `urlscan-cli`, and `chaos` commands when you need provider-native output. See [External Intel](../FEATURES.md#external-intel) for the provider coverage and result fields for each entity type.

## Tool Notes

### `mtr`

Normal shell runs are line-oriented, so darklab_shell adds `--report-wide` when no report flag is present. This keeps live output and saved history readable.

| You type | What runs |
| --- | --- |
| `mtr google.com` | `mtr --report-wide google.com` |
| `mtr -c 20 google.com` | `mtr --report-wide -c 20 google.com` |
| `mtr --report google.com` | Unchanged; it already selects report mode. |

Use `mtr --interactive <host>` for the continuously redrawn display when Interactive PTY is enabled.

### `nmap`, `naabu`, and `masscan`

`nmap` and `naabu` use connect scanning when raw readiness is inactive. An explicit `nmap -sT` always stays a connect scan, and spoofing or link-layer bypass flags remain blocked. Restricted-CIDR deployments keep Naabu in connect mode.

`masscan` has no connect fallback. If raw readiness is unavailable, use RustScan or `nmap -sT`.

### `wget`

With Files enabled, downloads go to the active Files folder. Use `-P downloads` or `--directory-prefix=downloads` to choose a subfolder.

### `gau`

`gau` searches public archives and indexes for URLs that have been seen for a domain. Its results are passive leads, not proof that a URL is still live or vulnerable. Save them with `--o historical-urls.txt`, review the list in Files, and live-check approved URLs before using an active scanner. Custom proxy arguments stay blocked, while `--config` and `--o` can use owner-scoped Files paths.

### `nuclei` and ProjectDiscovery state

The app runs `nuclei` with a writable temporary home and adds `-ud /tmp/nuclei-templates` when no update directory is present. The managed template cache lasts for the container session, so the first run after a restart may spend 30–60 seconds downloading templates.

Saved output records whether a finding used the managed cache, a workspace template path, a pinned-looking template clone, or an operator-updated template set. Normal relative selectors such as `http/` count as managed-cache templates. ProjectDiscovery config, resume, and useful generated state is stored in Files under `/tools/` as described above.

### `dalfox`

darklab_shell uses Dalfox for bounded parameter discovery. Normal commands and the Project Assessment action add discovery-only mode and disable remote mining dictionaries, so Dalfox doesn't send XSS payloads. Server, callback, file/pipe input, proxy, redirect, custom payload, and remote-wordlist modes remain blocked. A protected Project HTTP profile can supply request headers through a short-lived private config without placing their values in the command or saved history.

### `wpscan`

`wpscan` works without a token. Save `WPSCAN_API_TOKEN` for API-backed vulnerability data. Inline `--api-token` values are blocked so they cannot enter saved history or output.

### `trufflehog`

Use `trufflehog filesystem --directory <folder> --json` for a Files folder or `trufflehog git https://... --json` for a public HTTPS Git repository. Private and provider-wide scans use credentials saved through **Options → Secrets** or `secret set NAME`:

```text
secret set GITHUB_TOKEN
trufflehog github --repo https://github.com/example/private-repo
trufflehog github --org example

secret set GITLAB_TOKEN
trufflehog gitlab --repo https://gitlab.com/example/private-repo.git
trufflehog gitlab --group-id 12345
```

Use `--endpoint https://...` with `github` or `gitlab` for a self-hosted provider. Organization, group, and all-accessible-repository scans can cover a lot of repositories, so start with one `--repo` when checking a new token or endpoint. Inline `--token`, credential-bearing URLs, local Git paths, SSH URLs, custom clone directories, and no-cleanup or auth-in-URL modes are blocked so credentials stay out of history and clones stay inside the managed runtime boundary.

### `puredns`

`puredns bruteforce` requires `--resolvers <file>` with a resolver list from Files. `--write`, `--write-massdns`, and `--write-wildcards` save their output back to Files.

## Related Docs

- [README Installed Tools](../README.md#installed-tools) - compact list of bundled commands
- [FEATURES.md](../FEATURES.md) - user-facing shell, Files, secrets, intel, and PTY behavior
- [CONFIGURATION.md](../CONFIGURATION.md) - operator settings for Files, raw scanning, and providers
- [external-command-integrations.md](external-command-integrations.md) - contributor registry and validation contracts
