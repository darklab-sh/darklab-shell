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

- **Active-run explicit attach/takeover actions**
  - Build on client-aware active-run ownership so non-owning browsers can do more than monitor.
  - Add explicit Run Monitor actions for cross-client active runs:
    - `Attach here`: follow live output in a new/restored tab if the backend supports safe multi-consumer streaming.
    - `Take over`: claim ownership when the original owner is stale, with clear copy that the stream is moving to this browser.
  - Decide whether the first implementation should be multi-consumer SSE fan-out or a stricter one-owner stream transfer.
  - Add two-browser Playwright coverage for same session token, different client ids, monitor-only default state, stale-owner takeover, and no mobile focus theft.

- **Workflow provenance and promotion follow-ups**
  - Link generated runs back to the workflow id/name and step index.
  - Surface workflow provenance in history rows, restored runs, compare/export packages, and future project views.
  - Add "promote recent runs to workflow" from selected history rows, including a step to replace repeated literals with `{{variables}}`.
  - Add duplicate/import/export actions once the core user-workflow editor has had real use.
  - Consider command metadata such as `risky`, `slow`, or `high-output` before adding stronger Run all confirmations.

- **Run comparison**
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

- **Declarative command runtime adaptations in `commands.yaml`**
  - Move command-specific runtime rewrites and environment tweaks out of app-owned Python branches and into the command registry.
    - Current hardcoded examples to migrate include:
      - `nmap` injecting `--privileged` when absent.
      - `nuclei` injecting `-ud /tmp/nuclei-templates` when absent.
      - `naabu` injecting `-scan-type c` when no scan type is present.
      - `mtr` injecting `--report-wide` plus the user-facing non-interactive note.
      - `wapiti` injecting `-f txt -o /dev/stdout` plus the terminal-output note.
      - `amass` managed database behavior: inject managed `-dir amass`, reject alternate DB dirs for database subcommands, rewrite that directory to the session workspace, and launch with `XDG_CONFIG_HOME=<session workspace>`.
    - Keep the registry expressive enough for future ProjectDiscovery runtime state handling without adding more per-tool Python conditionals.
  - Proposed `commands.yaml` model:
    - `runtime_adaptations.inject_flags`: append or prepend flags when none of a set of equivalent flags is already present.
    - `runtime_adaptations.managed_workspace_directory`: declare a tool-owned relative directory, applicable subcommands, the flag that receives it, whether alternate user values are rejected, and whether it counts as a workspace write.
    - `runtime_adaptations.environment`: declare environment variables for subprocess launch, including templated values such as `{workspace_root}`, `{session_workspace}`, and `{managed_workspace_parent}`.
    - `runtime_adaptations.output_notice`: optional notice text when a rewrite changes user-visible behavior.
    - `runtime_adaptations.applies_to`: root/subcommand/help-flag guards so help commands are not mutated unexpectedly.
  - Implementation notes:
    - Normalize this metadata in the existing command-registry loader, with schema validation and safe defaults.
    - Apply declarative adaptations after workspace flag rewriting and before deny-prefix evaluation when the injected flags need deny exemptions, or explicitly model the correct phase if some adaptations must happen later.
    - Keep the final execution command assembled with `shlex.join` so injected paths with spaces/metacharacters stay safe.
    - Preserve current behavior exactly during migration before adding new behavior.
    - Do not expose arbitrary environment injection from local config without considering operator/security boundaries; this is command-registry behavior, not a free-form user command escape hatch.
  - Testing expectations:
    - Backend registry normalization tests for each adaptation shape.
    - Migration parity tests proving `nmap`, `nuclei`, `naabu`, `mtr`, `wapiti`, and `amass` produce the same execution commands/notices as before.
    - Negative tests for Amass alternate DB directories and help commands that should not receive managed directories.
    - Tests for quoting templated workspace paths containing spaces or shell metacharacters.
    - Docs drift tests after adding or renaming test cases.
  - Documentation expectations:
    - Update `docs/external-command-integrations.md` to describe declarative runtime adaptations as the source of truth.
    - Update `ARCHITECTURE.md` command execution details so special command behavior points at `commands.yaml` instead of Python branches.
    - Update README tool notes only where user-visible behavior changes or becomes more clearly explained.

- **ProjectDiscovery session-scoped runtime state and output path surfacing**
  - Make ProjectDiscovery tools write useful config, resume, and generated artifact state into the active session workspace instead of anonymous `/tmp/.config/...` paths.
    - Start with `nuclei`, `subfinder`, `pd-httpx`, `katana`, and `naabu`.
    - Keep the existing `amass` managed `-dir amass` behavior as the model for command-specific state that should persist across related commands in one session.
    - Treat ProjectDiscovery tools as a shared family because their Go helpers generally resolve config paths through `$XDG_CONFIG_HOME` when set, falling back to `$HOME/.config`.
  - Add a command-runtime environment layer for tool-owned state.
    - For these tools, set `XDG_CONFIG_HOME=<session workspace>` when workspace storage is enabled so default paths become session-visible folders such as `katana/`, `subfinder/`, `httpx/`, `naabu/`, and `nuclei/`.
    - Preserve the current `nuclei -ud /tmp/nuclei-templates` injection so large template caches stay tmpfs-backed unless we deliberately decide templates should become workspace artifacts.
    - Keep `HOME=/tmp` in the scanner wrapper for generic tool scratch behavior.
    - Do not make provider/API-key config files public by accident. Audit share/export package behavior before including generated ProjectDiscovery config directories.
  - Surface container paths as user-facing workspace paths.
    - Add a run-output postfilter that rewrites absolute paths under the current session workspace root to `/relative/path`.
    - Example: `Creating resume file: /workspaces/sess_<hash>/katana/resume-abc.cfg` should display as `Creating resume file: /katana/resume-abc.cfg`.
    - Keep the stored full-output artifact aligned with the user-facing transcript so restored history and share pages do not expose hashed session paths.
  - Expand workspace-aware flags for generated directories and secondary outputs.
    - `katana`: support `-store-response-dir` / `-srd`, `-store-field-dir` / `-sfd`, and validate whether `-resume` should autocomplete from session files.
    - `pd-httpx`: support `-store-response-dir` / `-srd`, screenshot / response-store output directories where applicable, and config-file reads if useful.
    - `nuclei`: review resume, trace/error log, headless artifact, and config/template related paths; keep template cache policy explicit.
    - `subfinder`: review `-config` and provider config behavior carefully because those files can contain API keys.
    - `naabu`: review config, input/output, nmap integration output, and metrics behavior.
  - Testing expectations:
    - Backend tests for command validation wrapping each selected root with `XDG_CONFIG_HOME=<session workspace>` only when workspaces are enabled.
    - Backend tests that `nuclei` keeps `-ud /tmp/nuclei-templates` while also receiving the ProjectDiscovery config env.
    - Route/streaming tests for rewriting current-session absolute workspace paths in output lines.
    - Command-registry tests for any newly declared workspace directory flags.
    - Container smoke coverage for at least `katana` resume output and one `pd-httpx` or `katana` stored-response directory.
  - Documentation expectations:
    - Update `docs/external-command-integrations.md` with a ProjectDiscovery section before or after the Amass section.
    - Update README tool notes for any visible behavior changes.
    - Update CHANGELOG and release drafts with the user-facing path behavior and the security note around provider configs.

## Research

---

## Known Issues

---

## Technical Debt

- **JS unit harness modularization**
  - Gradually reduce implementation-coupled unit tests that extract private functions from browser scripts via `tests/js/unit/helpers/extract.js`.
  - Move high-value pure logic into importable modules before changing tests, so the tests can target supported module boundaries rather than source-string extraction.
  - Split the largest feature areas out of `tests/js/unit/app.test.js` and `tests/js/unit/runner.test.js` only when the underlying source seams exist; avoid churn-only file shuffles.
  - Prefer browser-visible Playwright assertions for flows already covered at the UI layer, and keep unit tests focused on pure transforms, edge-case branch logic, and fast failure localization.
  - Start with session-token, Options, mobile shell, and workspace command helpers because those are high-change areas with large synthetic DOM harnesses.

- **Playwright readiness hooks for race-prone UI flows**
  - Continue replacing fixed sleeps with state-aware waits on server-backed history, DOM readiness, or explicit UI state.
  - Review the remaining synthetic-event workaround in `tests/js/e2e/interaction-contract.spec.js` and add a small app/test readiness signal if the product surface can expose one cleanly.
  - Prefer tiny observable hooks over lower-level event synthesis when validating focus, modal, or keyboard contracts under parallel load.

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
  - The autocomplete YAML already models command structure (`flags`, `arguments`, `subcommands`, and `pipe_helpers`). Forms should be a structured render of that same data — not a parallel model — so the two features stay consistent and share maintenance. Design against the structured command catalog (see Architecture) before building.

- **Run collections / case folders**
  - Let users group related runs and snapshots into named investigations or cases.
  - Better long-term organization than tabs/history alone.

- **History bookmarks beyond stars**
  - Add richer saved-state labels like `important`, `baseline`, `follow-up`, or `customer-facing`.
  - Stronger foundation for compare/share/history workflows than a single star state.

- **Snapshot diff against current tab**
  - Compare the live tab against a previous run or snapshot without leaving the shell flow.

- **Workflow promotion from history**
  - User-created workflows now cover manual save/edit/replay from the Workflows panel and `workflow` CLI.
  - The next compelling feature is "promote this run sequence to a workflow": select 3-5 history entries and save them as a named reusable sequence.
  - During promotion, help users replace repeated literals with `{{variables}}` so history-derived workflows stay reusable instead of becoming one-off transcripts.

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
