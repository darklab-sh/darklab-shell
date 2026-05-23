# External Command Integrations

This document explains how darklab_shell adapts installed command-line tools so they work cleanly inside the web shell, container sandbox, and session workspace model.

The goal is not to document every flag a tool supports. The goal is to make app-owned behavior visible: command rewrites, environment overrides, workspace file handling, permission assumptions, and validation rules.

---

## Integration Principles

- Preserve the command the user typed in history and UI wherever possible.
- Rewrite only when the default tool behavior is broken, unsafe, misleading, or inaccessible in the web shell runtime.
- Keep rewrites safe to apply more than once so users can provide the explicit flag themselves without duplicate options.
- Prefer session workspace paths for user-visible inputs and outputs.
- Keep useful session-owned files out of `/tmp/.config` when users should be able to inspect them later.
- Treat external-tool adaptation as part of the command trust boundary; all filesystem path expansion must happen through command validation and workspace helpers.

---

## Runtime Model

User-submitted external commands run as the `scanner` user with the shared `appuser` group. The app process runs as `appuser`.

The scanner wrapper sets `HOME=/tmp` so tools that insist on a writable home can use the container tmpfs instead of the read-only application filesystem. That default is useful for caches and temporary tool state, but command-specific integrations may override narrower environment variables when a tool's useful state needs to be session-scoped.

Session workspace files are app-managed. Users can name relative files such as `targets.txt` or `amass`, and command validation rewrites those values to the active hashed session workspace path before subprocess launch.

Command-specific runtime behavior is declared in `app/conf/commands.yaml`. The registry supports injected flags, managed workspace directories, environment variables derived from managed workspace paths, and encrypted secret requirements. Python handles the common plumbing; the command registry handles the tool-specific rules.

---

## Integration Matrix

| Tool | App adaptation | Why |
| ---- | -------------- | --- |
| `mtr` | Adds `--report-wide` when no report mode flag is present, unless the run is started through the Interactive PTY trigger. | Plain shell runs need clean line-oriented output for streaming and saved history; `mtr --interactive <host>` uses the PTY path for the live redraw view when the feature is enabled. |
| `nmap` | Adds `-sT` when no scan mode is explicit. | TCP connect scans work reliably as the unprivileged `scanner` user; raw SYN scans (`-sS`) and explicit `--privileged` mode are blocked. |
| `nuclei` | Adds `-ud /tmp/nuclei-templates` when no update-directory flag is present, wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<session workspace>/tools` when Files are enabled, and declares workspace paths for response stores, Markdown/SARIF/JSON/JSONL exports, trace/error logs, resume files, and selected config/secret inputs. | Template storage must be writable under the read-only container filesystem, while useful per-session evidence and logs should be visible in Files without exposing template caches as session artifacts. |
| `subfinder` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<session workspace>/tools` when Files are enabled and declares workspace paths for list input, per-domain output directories, resolver lists, config files, and provider config files. | Subfinder otherwise falls back to `$HOME/.config` under `/tmp`, hiding useful session artifacts; provider configs can contain API keys and remain session-owned rather than share/export artifacts. |
| `dnsx` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<session workspace>/tools` when Files are enabled and declares workspace paths for list input, wordlists, and normal outputs. | DNSX shares the ProjectDiscovery config path conventions and should keep generated state under the session-owned tool folder. |
| `httpx` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<session workspace>/tools` when Files are enabled and declares workspace paths for list/raw-request inputs, normal outputs, response/screenshot store directories, and config files. | Response stores and screenshots are high-value session evidence, while config state should remain visible only to the active session owner. |
| `wget` | When Files are enabled, adds `-P <current workspace folder>` when no directory-prefix flag is present, and declares `-P` / `--directory-prefix` as workspace directory flags. | Default downloads land in the user's Files area instead of failing against the read-only container root, while explicit download folders still stay under the session workspace. |
| `katana` | Wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<session workspace>/tools` when Files are enabled and declares workspace paths for list/config inputs, error logs, stored response directories, and stored field directories. | Katana can generate useful secondary request/response and field-extraction artifacts; keeping those directories in Files makes them inspectable and reusable. |
| `naabu` | Adds `-scan-type c` when no scan type is present, wraps ProjectDiscovery config state with `XDG_CONFIG_HOME=<session workspace>/tools` when Files are enabled, and declares workspace paths for host lists, exclude lists, ports files, and normal outputs. | TCP connect scanning works reliably inside container runtimes where raw SYN scanning via libpcap may fail; config state and secondary input lists should remain session-visible. |
| `amass enum` / `amass subs` / `amass track` / `amass viz` | Adds managed `-dir tools/amass` when absent, rewrites it to the session workspace, and launches with `XDG_CONFIG_HOME=<session workspace>/tools`. | Amass v5 is database-first and auto-starts `amass engine`; the engine and CLI must use the same per-session database path instead of falling back to `$HOME/.config/amass`. |
| `ipinfo` | Injects optional `IPINFO_TOKEN` from the encrypted secrets vault and blocks config-writing/token-on-command-line flows such as `init`, `config`, `completion install`, and inline token flags. | Users can run the official IPinfo CLI for provider-native IP/ASN output without storing tokens in shell history or letting the CLI write persistent config inside the container. |
| `urlscan-cli` | Injects `URLSCAN_API_KEY` from the encrypted secrets vault and blocks key/config/completion setup, inline key flags, and stdin-driven scan/result forms. | Users can submit URLs, fetch scan results, and search urlscan.io without writing keys to a local keyring/config file or putting tokens into command history. |
| `chaos` | Injects `PDCP_API_KEY` from the encrypted secrets vault and blocks inline key flags, updater flows, list-file input, and direct output-file writes. | Users can query ProjectDiscovery Chaos for domain subdomains while keeping the provider key in the app vault and avoiding unmanaged file reads/writes. |

---

## Workspace-Aware File Flags

Workspace-aware flags are declared in `app/conf/commands.yaml` under each command's `workspace_flags` entries.

Validation behavior:

- Relative workspace values are resolved under the active session workspace.
- Absolute paths are not rewritten and still pass through the normal deny rules.
- Read flags require the session file to exist.
- Write and read/write flags prepare the destination path before subprocess launch.
- Directory flags can create and prepare managed session directories.

This covers normal file input/output tools such as `nmap -iL`, `nmap -oN`, `curl -o`, `wget -P`, `ffuf -o`, `subfinder -dL`, `naabu -list`, `nuclei -l`, and Amass database directories. It also covers selected ProjectDiscovery flags that create directories, such as `katana -srd`, `katana -sfd`, `httpx -srd`, `subfinder -oD`, and `nuclei -srd` / `-me`.

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

`inject_flags` rewrites command argv tokens with `shlex.join`, so injected values stay safely quoted when paths contain spaces or shell metacharacters. `position: prepend` inserts tokens after the command root, `position: append` adds trailing tokens, and `position: command_prefix` inserts tokens before the command root for wrappers such as `env NAME=value`. `unless_any` and `unless_any_regex` keep rewrites from duplicating flags and prevent help/version commands from being changed. `requires_workspace: true` skips the injection unless Files are enabled and a session workspace is available. Injected tokens may use `{session_workspace}` to point at the current session's hashed workspace directory. `notice` prints a short terminal message when a rewrite needs user-facing explanation.

`managed_workspace_directory` is evaluated by workspace-aware validation. When it applies, the declared directory is injected if absent, rewritten through the same workspace directory helper as user-provided directory flags, and optionally rejects alternate user values so tool state does not split across multiple databases.

`environment` wraps the final execution command with `env NAME=value ...` after workspace path rewriting. The current template used by shipped commands is `{managed_workspace_parent}`, which resolves from the declared managed directory flag.

Encrypted credentials use a separate `requires_secrets` declaration instead of the `environment` wrapper. At launch, `/runs` looks up the current session's matching encrypted secrets, decrypts them in memory, and passes them through `subprocess.Popen(env=...)`. Secret values are never inserted into the shell command string. Required missing secrets block launch with a clear error; optional missing secrets log a warning and let the command run without that env var.

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

The Options Secrets picker reads this command-registry metadata so users see the known tool key names first. Custom names remain available for local registry overlays and future integrations.

`ipinfo` declares `IPINFO_TOKEN` as optional. The CLI can show limited unauthenticated output, while saved tokens unlock the provider data attached to the user's IPinfo account.

`urlscan-cli` and `chaos` declare required CLI secrets. `urlscan-cli` receives `URLSCAN_API_KEY`; `chaos` receives `PDCP_API_KEY`. Their setup and inline-key flags are blocked so the vault stays the only supported key path.

Run output is also filtered before it is captured or streamed: absolute paths under the current session workspace are displayed as user-facing workspace paths. For example:

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

- `intel ip <ip>` queries Shodan, Censys, GreyNoise, AlienVault OTX, AbuseIPDB, IPinfo, Team Cymru, URLhaus, ThreatFox, and RouteViews.
- `intel domain <domain>` queries VirusTotal, AlienVault OTX, crt.sh, URLhaus, ThreatFox, urlscan.io, and SecurityTrails.
- `intel url <url>` queries URLhaus, ThreatFox, and urlscan.io.
- `intel hash <md5|sha1|sha256>` queries VirusTotal, AlienVault OTX, URLhaus, and ThreatFox after autodetecting the hash type by hex length, and checks SHA1 hashes against HIBP Pwned Passwords by sending only the first five SHA1 characters.
- `intel cve <CVE-ID>` queries NVD and Vulners.

Provider metadata lives in `app/services/intel/registry.py`, including display labels, supported entity types, secret names and aliases, cache scopes, rate-limit config keys, and user-facing usage labels. Provider responses are normalized through `app/services/intel/schema.py` before they are rendered, cached, or logged. Each provider pane reports whether the result came from cache, was blocked by rate limiting or quota backoff, or is missing the needed encrypted secret. If all keyed providers for a lookup are missing, the built-in exits with setup guidance only when no no-key or optional-key provider can run. If only some providers are missing, available providers still render normally and the missing providers show placeholders. The same provider metadata feeds the Options Provider Status modal, `secret show-consumers`, the `providers` alias, and the Options Secrets picker for providers that need stored keys, so app-native HTTP providers and CLI-backed provider wrappers are discoverable from one place.

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

When workspace storage is enabled, `subfinder`, `dnsx`, `httpx`, `katana`, `naabu`, and `nuclei` are launched with:

```bash
env XDG_CONFIG_HOME=/workspaces/sess_<hash>/tools <tool> ...
```

This keeps useful generated state under session-visible folders such as:

```text
/tools/katana
/tools/subfinder
/tools/dnsx
/tools/httpx
/tools/naabu
/tools/nuclei
```

`nuclei` still receives `-ud /tmp/nuclei-templates` unless the user provides an update directory. Template caches are intentionally left in tmpfs because they are large, reusable container state rather than session evidence.

Several ProjectDiscovery flags are also declared as workspace-aware paths so generated files and secondary outputs can be inspected in Files:

- `katana -srd` / `-store-response-dir` and `katana -sfd` / `-store-field-dir`
- `httpx -srd` / `-store-response-dir`, including response stores and screenshot output directories
- `nuclei -srd` / `-store-resp-dir`, `-me`, SARIF/JSON/JSONL exports, trace/error logs, and resume/config inputs
- `subfinder -oD`, resolver lists, config files, and provider config files
- `naabu` host-list, exclude-list, ports-file, and output paths

Security note: ProjectDiscovery provider/config files can contain API keys or other operator secrets. The Files view can show them to the current session owner. Share and permalink exports remain transcript-only, but project evidence packages can include selected raw workspace artifacts when artifact inclusion is enabled; redacted packages exclude raw artifacts. Do not select provider/config files for evidence packages unless the operator intends to include those secrets in the archive.

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
```

Expected validation signals:

- `asset.db`, `asset.db-shm`, and `asset.db-wal` grow under the session workspace.
- `/tmp/.config/amass` is not created for app-launched Amass database commands.
- `amass subs -d <domain> -names` reads findings produced by prior `amass enum` runs in the same browser session.
- `amass track` and `amass viz` read the same managed database used by `enum` and `subs`.
- A different session token gets a different workspace directory and does not see the previous session's Amass database.

Additional workspace output handling:

- `amass subs -o <file>` writes a session file.
- `amass viz -o <directory>` writes visualization artifacts under a session directory.

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

Container setup applies file capabilities:

```bash
setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap
```

Those raw-socket features are not reliable for the app's unprivileged `scanner` execution path across Docker hosts and security profiles, so the app standardizes on TCP connect scans. `rewrite_command()` injects `-sT` when an `nmap` command does not already specify a scan mode, and command validation blocks `-sS` plus explicit `--privileged` mode before launch.

Workspace integration is separate from the scan-mode rewrite:

- `-iL` and script-args file flags can read session files.
- output flags such as `-oN`, `-oX`, `-oG`, `-oA`, and `-oS` can write session files.

---

## Naabu

`naabu` defaults to SYN scanning, which relies on libpcap/gopacket and raw packet behavior that is not reliable across Docker Desktop, rootless runtimes, and production container hosts.

The app injects:

```bash
-scan-type c
```

when neither `-scan-type` nor `-st` is present. This makes naabu use TCP connect mode, which is slower but much more predictable in the app runtime. Users can still explicitly request another scan type.

Workspace integration covers list input and output files:

- `-l`, `--list`, and `-list` can read session files.
- `-o` and `--output` can write session files.

---

## Adding Or Changing An Integration

Before merging a new external-command adaptation:

- Add or update the command metadata in `app/conf/commands.yaml`.
- Keep user-facing examples aligned with the app-owned rewrite behavior.
- Add backend tests for validation, rewrite, and workspace path handling.
- Add autocomplete tests if examples, flags, or positional hints change.
- Add or update container smoke expectations when the change affects visible examples or workflow steps. The generic smoke corpus skips normal examples for commands with required encrypted secrets, but it can include registry-declared help examples marked with `smoke.profile: unauthenticated`. Cover credentialed behavior with registry, policy, secret-injection, or keyed smoke tests.
- Document tool-specific behavior here when the app does more than simple allowlist metadata.
