# External Command Integrations

This document tracks how darklab_shell adapts installed command-line tools so they behave well inside the web shell, container sandbox, and session workspace model.

The goal is not to document every flag a tool supports. The goal is to make app-owned behavior visible: command rewrites, environment overrides, workspace file handling, permissions assumptions, and validation expectations.

---

## Integration Principles

- Preserve the command the user typed in history and UI wherever possible.
- Rewrite only when the default tool behavior is broken, unsafe, misleading, or inaccessible in the web shell runtime.
- Keep rewrites idempotent so users can provide the explicit flag themselves without duplicate options.
- Prefer session workspace paths for user-visible inputs and outputs.
- Keep durable or inspectable artifacts out of `/tmp/.config` when they represent session-owned work.
- Treat external-tool adaptation as part of the command trust boundary; all filesystem path expansion must happen through command validation and workspace helpers.

---

## Runtime Model

User-submitted external commands run as the `scanner` user with the shared `appuser` group. The app process runs as `appuser`.

The scanner wrapper sets `HOME=/tmp` so tools that insist on a writable home can use the container tmpfs instead of the read-only application filesystem. That default is useful for caches and temporary tool state, but command-specific integrations may override narrower environment variables when a tool's useful state needs to be session-scoped.

Session workspace files are app-mediated. Users can name relative files such as `targets.txt` or `amass`, and command validation rewrites those values to the active hashed session workspace path before subprocess launch.

---

## Integration Matrix

| Tool | App adaptation | Why |
| ---- | -------------- | --- |
| `mtr` | Adds `--report-wide` when no report mode flag is present. | Interactive `mtr` expects a real TTY and redraws in place; report mode streams clean text over SSE. |
| `nmap` | Adds `-sT` when no scan mode is explicit. | TCP connect scans work reliably as the unprivileged `scanner` user; raw SYN scans (`-sS`) and explicit `--privileged` mode are blocked. |
| `nuclei` | Adds `-ud /tmp/nuclei-templates` when no update-directory flag is present. | Template storage must be writable under the read-only container filesystem. |
| `wapiti` | Adds `-f txt -o /dev/stdout` when no output path is present. | Wapiti writes reports to files by default; stdout keeps results visible in the terminal transcript. |
| `naabu` | Adds `-scan-type c` when no scan type is present. | TCP connect scanning works reliably inside container runtimes where raw SYN scanning via libpcap may fail. |
| `amass enum` / `amass subs` / `amass track` / `amass viz` | Adds managed `-dir amass` when absent, rewrites it to the session workspace, and launches with `XDG_CONFIG_HOME=<session workspace>`. | Amass v5 is database-first and auto-starts `amass engine`; the engine and CLI must use the same per-session database path instead of falling back to `$HOME/.config/amass`. |

---

## Workspace-Aware File Flags

Workspace-aware flags are declared in `app/conf/commands.yaml` under each command's `workspace_flags` entries.

Validation behavior:

- Relative workspace values are resolved under the active session workspace.
- Absolute paths are not rewritten and still pass through the normal deny rules.
- Read flags require the session file to exist.
- Write and read/write flags prepare the destination path before subprocess launch.
- Directory flags can create and prepare managed session directories.

This covers normal file input/output tools such as `nmap -iL`, `nmap -oN`, `curl -o`, `ffuf -o`, `subfinder -dL`, `naabu -list`, `nuclei -l`, and Amass database directories.

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
amass
```

If the user omits `-dir`, the app injects it. If the user provides another directory for database commands, validation rejects it to avoid split databases.

The execution command is wrapped like this after workspace rewriting:

```bash
env XDG_CONFIG_HOME=/workspaces/sess_<hash> amass enum ... -dir /workspaces/sess_<hash>/amass
```

That makes Amass' default config path and explicit `-dir` converge on:

```text
/workspaces/sess_<hash>/amass
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
- Add or update container smoke expectations when the change affects surfaced examples or workflow steps.
- Document tool-specific behavior here when the app does more than simple allowlist metadata.
