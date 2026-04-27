# TODO

This file tracks open work items, known issues, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Ideas are speculative — not committed or planned.

---

## Table of Contents

- [Open TODOs](#open-todos)
- [Research](#research)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Ideas](#ideas)
  - [Near-term](#near-term)
  - [Later](#later)
  - [Mobile](#mobile)
  - [Safety and Policy](#safety-and-policy)
  - [Content and Guidance](#content-and-guidance)
  - [Architecture](#architecture)

---

## Open TODOs

- **Run Monitor follow-ups**
  - The base Run Monitor is implemented: `runs` prints app-native active-run metadata, `jobs` aliases it, desktop HUD pills open the monitor when active runs exist, mobile command use opens the monitor as a sheet, and empty HUD clicks stay as a green toast instead of opening an empty panel.
  - Keep the remaining work scoped to richer metadata and debug/operator views:
    - `runs -v` for full IDs, started timestamps, and active-run storage source
    - `runs --json` for debugging and automation
    - `runs --stalled` once PID-aware stalled-stream state exists
    - highlight/filter the monitor by tab when opened from the `TABS` pill
    - expose stale/detached state and a clear-stale action once the backend lifecycle is explicit enough
  - Backend follow-ups:
    - extend `/run` start payload to include tab ID/title so active-run metadata can identify the originating tab
    - consider recording `last_output_at` and `last_stream_at` so `runs` can distinguish quiet, streaming, stalled, and detached states
  - Testing follow-ups:
    - add active-run metadata coverage proving tab fields survive through `/history/active` once `/run` records them

- **ANSI-enhanced built-in output polish**
  - Review and improve app-authored terminal output so built-ins feel more intentional and readable when rendered through `ansi_up`.
  - Current rendering boundary:
    - normal output classes already flow through `ansi_up`, including most `fake-*` built-in command output
    - `prompt-echo`, `notice`, `denied`, `exit-ok`, and `exit-fail` intentionally render with `textContent` plus CSS classes
    - keep that safety boundary unless there is a specific reason to change it; system messages, command echoes, warnings, denials, and process-exit summaries should remain CSS-styled/plain text rather than ANSI-converted
    - external command output should be preserved as emitted by the tool; do not inject additional app ANSI styling into scanner/tool output
  - Add shared ANSI helpers in `app/fake_commands.py`:
    - centralize reset, bold, dim, underline, cyan, green, red, and amber/yellow helpers
    - replace one-off escape helpers such as the current file-list underline helper with the shared helpers
    - keep padding inside the styled text for fixed-width table headers so ANSI escapes do not break alignment
  - Apply consistent table-header styling:
    - keep `file list` headers underlined
    - underline headers for `runs` / `jobs` output: `run`, `pid`, `elapsed`, `command`
    - underline headers for `stats` top-command output: `command`, `runs`, `ok`, `avg`
    - underline headers for shell-shaped summaries such as `ps`, `df -h`, `free -h`, and `route`
  - Add semantic color to key/value built-ins:
    - `status`: database/redis online in green, offline/unavailable in red, anonymous/session metadata muted or cyan where helpful
    - `status` and `stats`: rename lingering `active jobs` labels to `active runs`
    - `limits` and `retention`: enabled/yes values in green, disabled/no values muted or amber depending meaning
    - `session-token list`: active token status in green, anonymous/no-token state muted, security guidance left as normal notice text
  - Improve active-run CLI output:
    - color active elapsed duration green
    - render PID/process-group metadata in dim or cyan
    - render short run IDs in cyan
    - leave command text plain so it remains easy to copy
    - keep empty `runs` / `jobs` output simple: `No active runs.`
  - Improve completed-run and stats output:
    - in `last`, color only the exit-code token: `0` green, non-zero red, unknown/incomplete muted or amber
    - in `stats`, color success-rate summaries lightly while keeping table rows copyable and aligned
    - avoid making whole rows red/green when only one field carries the semantic state
  - Client-side built-in output:
    - consider small ANSI enhancements for normal-class lines emitted by client-side helpers such as `theme`, `config`, and `session-token`
    - do not ANSI-style client-side `notice`, `denied`, `exit-ok`, or `exit-fail` lines unless the renderer contract changes deliberately
  - Export/share considerations:
    - confirm ANSI enhancements survive live output, restored history, permalink/share views, HTML export, and PDF export
    - plain-text export should continue stripping ANSI escape codes cleanly
    - search and command-finding summaries should continue operating on raw text without ANSI spans interfering
  - Testing:
    - add fake-command tests for representative ANSI output in `runs`, `last`, `status`, `stats`, and `file list`
    - add/update JS output tests proving normal classes use `ansi_up` while plain/system classes still do not
    - add export/permalink coverage if new ANSI patterns expose gaps in saved/shared rendering
    - keep assertions focused on stable escape sequences and visible text so future color choices can evolve without brittle tests

- **Session command variables**
  - Explore app-mediated variable substitution for repeated command sets without exposing real shell environment mutation.
  - Use cases:
    - define `HOST=ip.darklab.sh`, `PORT=443`, `IP_ADDR=107.178.109.44`
    - run a sequence of commands that reference `$HOST`, `$PORT`, or `$IP_ADDR`
    - update the variables and re-run the same commands or workflow against a different target
  - Possible user-facing model:
    - `var set HOST ip.darklab.sh`
    - `var list`
    - `var unset HOST`
    - command input can reference `$HOST`, `${HOST}`, `$PORT`, `${PORT}` before policy validation and execution
  - Security and correctness constraints:
    - Treat variables as app-owned text substitution, not process environment variables.
    - Apply substitution before command allow/deny checks so expanded commands still go through the existing command policy.
    - Restrict variable names to a small safe pattern such as `[A-Z][A-Z0-9_]{0,31}`.
    - Preserve command history in a way that makes both the typed command and expanded command understandable.
    - Redact or discourage sensitive values; this should be for targets/ports/paths, not secrets.
  - UX integration:
    - Add autocomplete for defined variable names.
    - Show current variables in `status` or a small Variables modal if the feature grows beyond a few CLI helpers.
    - Let workflow inputs optionally map to session variables so users can update one target value and replay a saved sequence.
  - Testing:
    - Unit-test substitution order, quoting behavior, undefined variables, and policy validation after expansion.
    - E2E-test a variable-driven command sequence and history/share display.

- **Workspace-native chained recon workflows**
  - Add guided workflows that demonstrate the Files feature as an app-mediated pipeline: one recon tool writes a session file, and a later tool reads that generated file through declared workspace-aware flags.
  - Keep these workflows small and reviewable. They should show why Files exists without turning `Run all` into a huge scanner blast.
  - Registry prerequisites:
    - Add `subfinder -o` as a workspace write flag so subdomain discovery can produce a clean line-oriented `subdomains.txt`.
    - Verify `pd-httpx -silent -o live-urls.txt` emits clean URL lines suitable for `nuclei -l` and follow-up probes.
    - Keep all file-reading/file-writing examples marked with `feature_required: workspace` so they only appear when Files are enabled and so generic smoke cases do not run them without setup.
  - Candidate workflow: **Subdomain HTTP Triage**
    - Input: `domain`
    - `subfinder -d {{domain}} -silent -o subdomains.txt`
    - `pd-httpx -l subdomains.txt -silent -o live-urls.txt`
    - `pd-httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt`
    - Output files: `subdomains.txt`, `live-urls.txt`, `http-summary.txt`
  - Candidate workflow: **Crawl And Scan**
    - Input: `url`
    - `katana -u {{url}} -d 1 -silent -o crawled-urls.txt`
    - `pd-httpx -l crawled-urls.txt -status-code -title -o crawled-http.txt`
    - `nuclei -l crawled-urls.txt -severity high,critical -o nuclei-findings.txt`
    - Output files: `crawled-urls.txt`, `crawled-http.txt`, `nuclei-findings.txt`
  - Test coverage:
    - Add/update smoke workspace fixtures for each new chained example that reaches `commands.yaml`.
    - Add workflow rendering coverage so `Run all` preserves sequential same-tab behavior with generated file names.
    - Verify workflows are hidden or clearly disabled when Files are disabled if their steps depend on workspace-only flags.

- **Workspace migration when changing session identity**
  - `/session/migrate` currently moves database-backed state such as runs, snapshots, starred commands, and saved preferences, but it does not move or merge the filesystem workspace directory.
  - This creates a real identity gap: if a user starts anonymously, creates workspace files, then generates or sets a `tok_...` session token and chooses to migrate history, their history follows the token but their workspace files remain under the old anonymous workspace hash.
  - Decide the desired product behavior before implementing:
    - move the source workspace into the destination when the destination workspace is empty
    - merge files when both source and destination workspaces exist
    - refuse migration with a clear warning if both sides contain files
    - keep workspaces separate but make that explicit in the migration prompt
  - Implementation constraints:
    - preserve per-session path validation and symlink rejection
    - avoid overwriting destination files silently
    - preserve scanner/appuser group permissions and sticky/setgid directory modes
    - account for workspace backend differences (`tmpfs` vs volume) and quota checks
  - UX:
    - update `session-token generate`, `session-token set`, and `session-token rotate` migration prompts to mention workspace files once the behavior is defined
    - show the number of migrated or skipped workspace files in the migration result
  - Testing:
    - Add route coverage for migrating with no source workspace, source-only workspace, destination-only workspace, and conflicting files.
    - Add E2E coverage proving Files contents remain visible after accepting a session-token migration.

---

## Research

---

## Known Issues

---

## Technical Debt

- **v1.6 branch review hardening backlog**
  - Track the verified findings from the v1.6 branch review. These are not release-blocking by default, but they are real enough to schedule deliberately instead of letting them disappear into review notes.
  - Priority 1 — command execution and lifecycle hardening:
    - Quote workspace-rewritten command tokens before reassembling command strings.
      - Context: `rewrite_command()` can inject app-derived workspace paths such as managed Amass `-dir <session-workspace>/amass` into a string that is later parsed by `sh -c`.
      - Risk: user-created workspace paths can contain shell metacharacters that are valid relative file names. This is self-injection rather than privilege escalation because the user already controls the submitted command, but app rewrites should not unexpectedly change shell parsing.
      - Plan: use `shlex.quote()` when reassembling rewritten argv tokens, or carry argv through to the subprocess boundary in a larger refactor that avoids `sh -c`.
      - Also decide whether fake-command handling should receive the same rewrite path or explicitly document why fake commands do not need workspace substitution.
      - Tests: add rewrite tests with spaces, semicolons, `$`, backticks, and `&` in workspace path components; add an Amass managed-dir regression case.
    - Add a hard ceiling for detached run drain threads.
      - Context: `_continue_run_detached()` keeps draining output after the SSE client disconnects so orphaned processes can still be logged.
      - Risk: a process that never exits or never closes stdout can leak one background thread and pin active-run state until the worker recycles.
      - Plan: bound detached drain lifetime to `command_timeout_seconds + grace`, kill/cleanup if the ceiling is exceeded, and make sure `pid_pop` plus active-run removal always execute in `finally`.
      - Tests: simulate a detached run with a non-closing reader/process and assert cleanup occurs after the ceiling.
    - Guard stalled-session recovery state application with a run-generation token.
      - Context: the 45-second quiet-stream recovery path checks `/history/active` asynchronously before changing tab state.
      - Risk: rapid tab switches, kills, or overlapping timeout checks can race between “still active?” resolution and UI state application.
      - Plan: capture tab ID plus run ID/generation before awaiting, then re-check the same generation immediately before applying status, notices, or kill-button changes.
      - Tests: add runner unit coverage for stale timeout promises resolving after a kill, tab switch, and newer run start.
  - Priority 2 — workspace filesystem correctness:
    - Repair top-level session-file ownership in `entrypoint.sh`.
      - Context: the current workspace permission repair starts at `-mindepth 2`, which skips files directly under each session directory.
      - Risk: scanner-created top-level output files can keep ownership/mode that later blocks app-side reads or deletes depending on prior volume state.
      - Plan: include top-level session files while preserving session-directory ownership/modes, or split the repair into explicit directory and file passes.
      - Tests: add shellcheck-friendly fixture or integration coverage for a scanner-owned file directly under `sess_<hash>/`.
    - Warn when `WORKSPACE_ROOT` env and `workspace_root` config diverge.
      - Context: Compose files, `entrypoint.sh`, and `app/conf/config.yaml` can point at different workspace roots.
      - Risk: commands can write files in one location while the app lists another, surfacing as empty file lists or missing artifacts.
      - Plan: during startup, if `WORKSPACE_ROOT` is set and differs from `CFG["workspace_root"]`, log a clear warning with both paths.
      - Tests: config/startup unit coverage for matching, missing, and mismatched values.
    - Close the theoretical symlink TOCTOU gap in workspace file opens.
      - Context: `_reject_symlink_components()` rejects existing symlinks before the later open/read/write operation.
      - Risk: a same-principal actor could swap a symlink into the final path between validation and open. Current session-directory permissions make this low practical risk, but deterministic hardening is better.
      - Plan: use `os.open(..., O_NOFOLLOW)` for final-component opens where supported, keep parent validation, and retain current path checks for portability.
      - Tests: add symlink-final-component tests for read/write/delete paths where the platform supports `O_NOFOLLOW`.
    - Log chmod failures in workspace setup instead of swallowing all `OSError`.
      - Context: `workspace.py` intentionally tolerates permission repair failures today.
      - Risk: real volume misconfiguration, especially on NFS or unusual bind mounts, can fail silently.
      - Plan: log warning-level details with path and operation while keeping best-effort behavior where appropriate.
      - Tests: monkeypatch `os.chmod` failure and assert a warning log without breaking workspace creation.
  - Priority 3 — frontend robustness:
    - Replace fragile `searchSignalSummary.innerHTML = compact` assignment with DOM construction or a sanitizing chokepoint.
      - Context: `_formatCompactSignalSummary()` currently emits only hardcoded scope names and numeric counts, so it is safe today.
      - Risk: future edits could accidentally interpolate unsanitized strings into the DOM.
      - Plan: build the compact summary with `createElement`/`textContent`, or route generated markup through a very small allowlisted sanitizer helper used only for signal-summary UI.
      - Tests: unit-test that weird scope/count inputs render as text, not markup.
    - Confirm whether repeated `bindPressable()` calls on search signal-scope buttons accumulate listeners.
      - Context: workspace modal listeners are module-load only, so that flagged leak is not valid. The more plausible issue is `refreshSearchDiscoverabilityUi()` rebinding `[data-search-signal-scope]` buttons on repeated refreshes.
      - Plan: inspect `bindPressable()` idempotency. If it does not dedupe, make the helper idempotent per element or move binding to one-time setup.
      - Tests: add unit coverage that repeated search refreshes trigger one activation per click.
    - Re-evaluate mobile prompt-mount mode on resize.
      - Context: tab activation captures mobile mode once for prompt-mount decisions.
      - Risk: mostly polish, but viewport changes around mobile/desktop breakpoints can leave prompt placement stale.
      - Plan: add a resize/layout-mode listener that re-runs the prompt mount decision for the active tab only when the mode changes.
      - Tests: frontend unit coverage for mode flip without losing draft input.
  - Priority 4 — documentation and operational clarity:
    - Add an inline Dockerfile comment explaining why both sudoers lines for `appuser -> scanner` are present.
      - Context: `appuser ALL=(scanner) NOPASSWD: ALL` and `appuser ALL=(scanner:appuser) NOPASSWD: ALL` look redundant but cover different runas-user/runas-group forms.
      - Plan: comment the distinction near the sudoers lines so future cleanup does not remove one.
    - Re-check README theme-count references before tagging v1.6.
      - Context: the branch now ships 18 themes; any stale “all 17 themes” language should be corrected.
      - Plan: run the docs drift tests and grep for stale theme counts/names after the final theme set lands.
    - Re-confirm checked-in and external release docs test totals before tagging.
      - Context: repo docs are checked by `tests/py/test_docs.py`; external `~/git_docs/v1.6-*` files are not.
      - Plan: update `tests/README.md`, `CONTRIBUTING.md`, `ARCHITECTURE.md`, and the external v1.6 merge/release notes after the final test count stabilizes.
    - Document deny precedence near a representative `commands.yaml` entry.
      - Context: the loader gives deny rules precedence when both `policy.allow` and `policy.deny` exist, but readers have to inspect code to know that.
      - Plan: add one concise YAML comment near a command with both allow and deny policy.
  - Priority 5 — validation and benchmarks:
    - Add a synthetic-output benchmark for `output_signals.py`.
      - Context: the current regex set looks bounded and safe, but it has grown large enough that a baseline would be useful.
      - Plan: run classifier patterns against a 10 MB synthetic transcript with mixed scanner-like lines, hostname/IP noise, and long non-matching lines.
      - Tests/benchmark: add a non-default benchmark script or pytest marked benchmark that records baseline runtime without making normal CI flaky.
    - Log non-blocking stream setup failures in `run.py`.
      - Context: if `os.set_blocking()` fails, the reader can fall back to blocking `readline()`.
      - Risk: a process emitting partial lines without newlines can stall the SSE generator.
      - Plan: warning-log the fallback path with fd/process context and consider a safer partial-read fallback for platforms where non-blocking setup fails.
      - Tests: monkeypatch `os.set_blocking` failure and assert the warning path.
    - Eyeball visual-capture assets after demo fixture star-ratio changes.
      - Context: `seed_history.py` changed the visual fixture star ratio. Binary diffs suggest capture assets were regenerated, but visual review should confirm the intended density.
      - Plan: inspect one desktop and one mobile captured PNG plus the demo video before release notes are finalized.

- **Mobile E2E setup can trip app rate limiting**
  - The mobile tabs overflow coverage rapidly runs several built-in commands to create output-bearing tabs. It currently passes, but it can emit a backend rate-limit warning during full mobile-file runs.
  - Consider mocking `/run` for that setup path or pacing the setup commands so the test keeps validating tab overflow behavior without depending on rate-limit timing.

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Priority order

Ranked by user benefit weighted against implementation complexity. Benefit and complexity use a three-point scale (H / M / L). Items marked ⬡ are foundational — they unlock multiple later features and should be designed before the features that depend on them are built.

**Tier 1 — Quick wins (high benefit, low complexity)**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Better output navigation | H | L | Line classes already exist; only navigation logic needed |
| Run labels from terminal | M | L | Fake command + DB column + history drawer display |
| Richer run metadata in history UI | M | L | Data already stored; surfacing only |

**Tier 2 — High value, moderate effort**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Additional export formats | M | L–M | JSONL is straightforward; Markdown needs formatting logic |
| Bulk history operations | M | L–M | Checkbox mode in history drawer + bulk endpoints |
| Share package | H | M | Unified design reduces total work vs building annotations, notes, and lifecycle separately |
| Mobile share ergonomics | M | L–M | Basic native share-sheet done (v1.5); remaining work is one-handed save/share UX and clearer affordances |
| Tool-specific guidance + onboarding hints | M | L | Primarily content work |
| Session dashboards (`stats` command) | M | L | Fake command + queries that already exist for the diagnostics page |

**Tier 3 — Foundational ⬡ (unlock multiple later features)**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Structured command catalog ⬡ | H | H | Unblocks parameterized forms, improved autocomplete, and policy metadata; design forms against this before building them |

**Tier 4 — Moderate value, moderate effort**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| History bookmarks beyond stars | M | M | Schema change + label management UI; complements run labels from terminal |
| Saved command presets | M | M | New DB table + preset management UI |
| Workflow replay and promotion | M | M–H | Promotion from history is the core feature; YAML parameterization is secondary |
| Run comparison | M | H | Diff algorithm + run-selection UI; more compelling once history filtering is stronger |
| Per-command policy metadata | M | M | Allowlist format extension + hint surfaces |
| Richer audit trail | L–M | L | Logging additions only |
| Autocomplete from output context | L–M | M | Narrow use case; useful but not on the critical path |

**Tier 5 — Major initiatives (high benefit, high complexity)**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Parameterized command forms | M | H | Depends on structured command catalog; do not build independently |
| Run collections / case folders | M | H | New data model + grouping UI |
| Snapshot diff against current tab | M | H | Builds on run comparison; defer until comparison is done |

**Tier 6 — Defer (high complexity relative to incremental value)**

| Idea | Benefit | Complexity | Notes |
|------|---------|------------|-------|
| Full reconnectable live stream | M | H | Separate architecture pass; do not conflate with incremental UI polish |
| Environment capability hints | L–M | M | Pre-run hints have lower per-use value than post-run summaries |
| Interactive PTY mode | M | H | Full PTY + WebSocket architecture for a small allowlisted set |
| Plugin-style helper command registry | L | M | Internal quality; revisit when fake-command layer needs more structure |

---

### Near-term

- **Share package** (annotations, notes, and lifecycle controls)
  - Snapshots currently have no metadata beyond the raw output. Add optional title, note, and tags as a unified share package rather than building annotations, operator notes, and sharing controls as disconnected features — they compose into one coherent model.
  - Share package surface:
    - operator-facing title and note on the snapshot
    - tags
    - optional operator / team label
    - redaction mode used
    - a small generated summary block for the shared run
    - private notes attached to history entries (visible locally, never in public snapshots)
  - Share lifecycle controls:
    - expiring share links
    - one-time reveal links for sensitive snapshot sharing
  - Design all three (annotations, notes, lifecycle) together so the data model is consistent from the start.

- **Better output navigation**
  - For security tool output, 90% of lines are noise and 10% are findings. The most valuable part of this idea is jump-between-errors/warnings, not jump-to-top/bottom.
  - Primary value:
    - jump between warnings / errors / notices (uses existing line classes; this is the core feature)
    - highlight matched lines from search more aggressively
  - Secondary, lower cost:
    - sticky command header for long runs (near-free CSS position: sticky change)
  - Deferred until primary is done:
    - collapse long low-signal sections (genuinely complex, lower incremental value)

- **Run comparison**
  - Compare two runs side by side, especially for repeated scans or before/after checks.
  - More compelling once history filtering is stronger.
  - Focus the first version on repeated commands:
    - compare two runs of the same command
    - show added / removed lines
    - surface exit-code and elapsed-time changes
    - allow a "differences only" view
  - The diff target should explicitly include permalinks and snapshots (not just history entries) — the most common real-world case is comparing a new scan against last month's saved permalink, not two history rows in the same session.

- **Tool-specific guidance**
  - Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `wapiti`, or `nuclei`.
  - Good fit for the existing help / FAQ / welcome surfaces.
  - Merge this with onboarding and command hints into a broader operator-guidance layer:
    - command-specific caveats
    - runtime expectations
    - examples of when to use one tool vs another

- **Richer run metadata in the history UI**
  - Surface preview/full-output availability, retention expectations, and share/export readiness more clearly.
  - Good fit for the existing history drawer and permalink model.
  - Include retention-aware UX:
    - "preview only" vs "full output available"
    - share readiness
    - export readiness
    - expiry / retention timing

- **Command outcome summaries**
  - For selected tools, generate short app-native summaries above the raw output. Security tool output is high-volume; a structured findings layer is what separates a purpose-built tool from a raw terminal.
  - Keep raw output primary — the summary is additive, never a replacement.
  - Start narrow: nmap (open ports + service table), dig (records returned), curl (status code + redirect chain), openssl s_client (cert expiry + trust chain).
  - The structured output model (see Architecture) is the right long-term foundation; build this feature to be retro-fittable once that model is in place rather than requiring it up front.

### Later

- **Saved command presets**
  - Let users save named command templates beyond history/starred entries.
  - Better for repeat workflows like DNS checks, HTTP triage, or common scan recipes.
  - Converge this with structured forms:
    - reusable saved workflows
    - optional structured parameters
    - always editable back to raw shell text

- **Parameterized command forms**
  - Add optional structured builders for common tools like `curl`, `dig`, `nmap`, and `ffuf`.
  - Keep raw-shell usage intact while making common tasks easier.
  - Build these on top of a reusable command/workflow preset model rather than as a disconnected UI feature.
  - The autocomplete YAML already models command structure (`flags`, `expects_value`, `arg_hints`, `__positional__`). Forms should be a structured render of that same data — not a parallel model — so the two features stay consistent and share maintenance. Design against the structured command catalog (see Architecture) before building.

- **Run collections / case folders**
  - Let users group related runs and snapshots into named investigations or cases.
  - Better long-term organization than tabs/history alone.

- **History bookmarks beyond stars**
  - Add richer saved-state labels like `important`, `baseline`, `follow-up`, or `customer-facing`.
  - Stronger foundation for compare/share/history workflows than a single star state.

- **Snapshot diff against current tab**
  - Compare the live tab against a previous run or snapshot without leaving the shell flow.

- **Workflow replay and promotion**
  - Guided workflows are currently stateless prompt-fillers — you cannot save a customized version of a built-in workflow, and there is no way to replay a sequence you discovered through normal use.
  - The compelling feature is "promote this run sequence to a workflow": select 3–5 history entries and save them as a named reusable sequence. That is more useful than just parameterizing the existing YAML format.
  - Turn guided workflows into reusable multi-step sequences that can be replayed, edited, and saved.

- **Additional built-in workflow candidates**
  - Candidate workflow cards that still complement the current guided workflows panel:
  - **WAF Detection** — wafw00f to identify the WAF vendor, curl with unexpected headers/paths to observe the blocking behavior, nmap WAF NSE scripts for a second opinion.
  - **WordPress Audit** — wpscan for known plugin/theme CVEs and user enumeration, curl to confirm common WP paths and the XML-RPC endpoint.
  - **DNS Delegation Diff** — host/nslookup for quick answers, dig @authoritative vs @public-resolver for disagreement checks, dig +trace to walk the delegation chain. More focused than the existing DNS card when the problem is split-brain or propagation lag.
  - **Hostname / Virtual Host Discovery** — gobuster vhost or ffuf Host-header fuzzing to identify name-based virtual hosts, then curl -H 'Host: ...' to validate which ones actually answer. Useful when an IP serves multiple sites and plain HTTP triage is too shallow.
  - **Surface Crawl to Endpoint Follow-up** — katana to crawl reachable URLs, pd-httpx or curl -I to classify what came back, then targeted curl checks against the interesting endpoints. Good middle ground between HTTP triage and heavier vuln scanning.
  - **Screenshot / Tech Fingerprint Sweep** — pd-httpx with title/tech-detect/status probes to quickly map many hosts, then curl on the standouts. Strong fit for the modal because it helps operators decide where to spend deeper scanning budget next.
  - **Certificate Inventory Across Hosts** — subfinder or assetfinder to build a host set, dnsx to keep only resolvable names, then openssl s_client or testssl against the likely HTTPS services. More operationally useful than a single-host TLS check when reviewing a whole domain footprint.
  - **Resolver Reputation / Mail Deliverability Baseline** — dig MX/TXT, nslookup against multiple resolvers, and whois on the sending domain or mail host. Distinct from the existing email card because it aims at “will this domain look sane to remote receivers?” rather than just “is SMTP open?”
  - **Crawlable Web App Triage** — curl -sIL for redirect/header shape, katana for path discovery, nikto for quick misconfig findings. A better default web-app sequence than running nikto cold against an unknown target.
  - **Service Exposure Drift** — repeatable baseline using nmap -F, nc -zv on expected ports, and curl or openssl s_client on the important services. This is less about discovery and more about quickly validating that a host still looks like the last known-good state.
  - Prefer workflow cards that chain 3-4 commands with a clear operator decision at each step; avoid modal entries that are just “run one big scanner.”
  - Prefer sequences that mix cheap classification first and heavier scanning second so the modal remains useful on mobile and in constrained environments.

- **Environment capability hints**
  - Surface when a tool is likely to be slow, noisy, truncated, or constrained by the container/runtime before it runs.

- **Run labels from the terminal**
  - A `tag <label>` built-in command that attaches a label to the most recent completed run directly from the shell flow, without opening the history drawer.
  - Labels like `baseline`, `finding`, `follow-up`, `customer-facing` are more precise than a binary star and set up richer compare/share/history workflows.
  - Complements "History bookmarks beyond stars" — the terminal command is the primary way to label, the history drawer is where labels are visible and filterable.

- **Bulk history operations**
  - The history drawer can delete all or delete non-favorites. Adding multi-select (checkbox mode) with bulk delete, bulk export to JSONL/txt, and bulk share would close a real gap when clearing out a session after an engagement or exporting selected findings.

- **Autocomplete suggestions from output context**
  - When a previous command's output is in the active tab, `| grep` completions could suggest patterns already present in that output — IP addresses, hostnames, status codes, CVE strings — as candidates alongside the generic flag list.
  - Narrow but would make the pipe stage feel predictive rather than generic.

### Mobile

- **Mobile share ergonomics**
  - The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
    - save/share actions tuned for one-handed use
    - clearer copy/share/export affordances inside the mobile shell
    - better share handoff after snapshot creation

### Safety and Policy

- **Richer audit trail**
  - Optional logging around share creation, deletions, and run access patterns.

- **Per-command policy metadata**
  - Allowlist entries could carry metadata like `risky`, `slow`, `high-output`, or `full-output recommended`.
  - The UI could surface this in help, warnings, or command builders.

### Content and Guidance

- **Tool-tips and onboarding hints**
  - Extend the welcome flow and help surfaces so onboarding suggests real tasks and tool combinations, not just isolated commands and hints.
  - Fold this together with tool-specific guidance:
    - "what to run next" suggestions
    - common operator playbooks
    - guidance tied to workflows, autocomplete, and command metadata

### Architecture

- **Full reconnectable live stream**
  - Explore a true reconnectable live-output path that can resume active command streams after reload rather than only restoring a placeholder tab and polling for completion.
  - This is a separate architecture step from the current active-run reconnect support and would likely require:
    - a per-run live output buffer
    - resumable stream offsets or event IDs
    - multi-consumer fan-out instead of one transient SSE consumer
    - explicit lifecycle cleanup once runs complete
  - Best fit is a dedicated live-stream architecture pass rather than incremental UI polish.

- **Structured output model**
  - Preserve richer line/event metadata consistently for all runs.
  - This would improve search, comparison, redaction, exports, and permalink fidelity.
  - Command outcome summaries (see Near-term) are buildable without this foundation, but design them to be retro-fittable once the structured model is in place — the summary parsers should consume structured line events, not re-parse raw text.

- **Unified terminal built-in lifecycle**
  - Browser-owned built-ins (`theme`, `config`, and `session-token`) need browser execution for DOM state, local storage, clipboard, and transcript-owned confirmations, while server-owned built-ins naturally flow through `/run`.
  - The long-term cleanup target is one terminal-command lifecycle after execution:
    - normalize built-in output into a shared result shape
    - apply pipe helpers against that shape
    - mask sensitive command arguments once
    - render transcript output once
    - persist server-backed history once
    - hydrate recents and prompt history from the same saved run model
  - Keep execution ownership separate where it matters, but remove duplicated recents/history/pipe/persistence glue so browser-owned and server-owned built-ins cannot drift.

- **Plugin-style helper command registry**
  - Turn the fake-command layer into a cleaner extension surface for future app-native helpers.

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
