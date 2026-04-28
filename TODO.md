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

- **Refresh theme preview cards for the current desktop shell**
  - The Theme selector preview cards still approximate the pre-v1.6 terminal-window layout instead of the current desktop shell with rail, tabbar, content pane, HUD, and drawer-style chrome.
  - Remove stale visual affordances from the preview cards as they are discovered; the legacy traffic-light dots have already been removed and the old `window_btn_*` theme keys were retired.
  - Redesign the preview thumbnail to show the canonical v1.6 surfaces:
    - left rail / chrome strip using `chrome_bg`
    - top tabbar with an active tab using `tab_active_bg`
    - terminal/content panel using `panel_bg`
    - bottom HUD/chrome row using `chrome_bg` / `chrome_row_bg`
    - representative accent/status elements using the semantic green, amber, red, blue, and muted palette
  - Keep the preview compact and schematic; it should communicate theme contrast and surface relationships, not reproduce the entire UI.
  - Add/update unit coverage around the theme-card DOM structure so obsolete preview-only tokens do not creep back into the theme key set.

- **Run Monitor CPU and memory usage**
  - Add lightweight resource telemetry to the Run Monitor so long-running commands show whether they are actively consuming CPU or memory instead of only showing elapsed time.
  - MVP:
    - Use the existing active-run PID/metadata tracking as the source of truth.
    - Add best-effort backend resource usage to `/history/active` for each active run.
    - Prefer `psutil` so the implementation works consistently in Linux containers and local macOS/Linux development.
    - Aggregate at least the tracked process plus recursive children so scanners that spawn workers are represented more accurately than parent-PID-only stats.
    - Report memory as RSS bytes and cumulative process-tree CPU seconds from the backend; calculate the live CPU percentage in the Run Monitor from adjacent poll samples so multi-worker deployments do not need a shared telemetry cache.
    - Keep the API fail-soft: if stats are unavailable, omit the telemetry or mark it unavailable without breaking active-run listing.
    - Render CPU and memory as stacked circular meters in the Run Monitor drawer/sheet and keep the existing polling cadence modest. Treat 1 GB RSS as 100% fill for the memory meter while still labeling the actual memory value.
    - Add unit coverage for backend resource aggregation and frontend formatting/rendering.
  - Future:
    - Add tiny per-run CPU sparklines using the same polling samples.
    - Track peak memory and maybe peak CPU while the drawer is open.
    - Add an "idle" indicator when CPU stays near zero for a sustained window.
    - Consider container-level CPU/memory totals in the status surface if operators need app/container health, separate from per-run command health.
    - Consider configured warning thresholds for runaway memory or sustained high CPU.

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

---

## Research

---

## Known Issues

---

## Technical Debt

- **Promote object-specific frontend styling into shared primitives**
  - Problem:
    - The surface-token pass aligned major theme values, but several frontend objects still carry their own structural and visual CSS even when they represent the same UI role.
    - This makes later theme work harder because repeated objects such as dropdown menus, chrome rows, filter chips, file rows, history rows, and mobile sheet controls can drift independently even when they should share behavior and appearance.
    - The existing button primitive allowlist is useful, but it also highlights remaining one-off pressable families that deserve review before the `color-mix()` / derived-token cleanup begins.
  - Goal:
    - Introduce a small set of shared structural primitives before centralizing local color transforms.
    - Keep component / ID selectors for layout, sizing, positioning, and true product-specific behavior.
    - Move repeated role styling into primitives so the later derived-token pass can target stable roles instead of many surface-specific selectors.
  - First-pass primitive candidates:
    - **Dropdown/menu primitive**
      - Shared by `.save-menu`, `.app-select-menu`, `.ac-dropdown`, `.hist-search-dropdown`, and mobile recents `.sheet-filter-menu`.
      - Candidate classes: `.dropdown-surface`, `.dropdown-item`, `.dropdown-item-active`, optional `.dropdown-up`.
      - Preserve autocomplete-specific layout such as match highlighting, descriptions, and mobile keyboard positioning as local modifiers.
    - **Chrome/list row primitive**
      - Shared by `.history-entry`, `.run-monitor-item`, mobile recents `.sheet-item`, `.workspace-file-row`, and potentially `.rail-item`.
      - Candidate classes: `.chrome-row`, `.chrome-row-clickable`, `.chrome-row-accent`, `.chrome-row-dense`.
      - Keep row content layout local when the information hierarchy differs, but centralize background, divider, hover, focus, and accent-stripe behavior.
    - **Form/control primitive**
      - Shared by `.form-input`, `.workspace-textarea`, `.search-bar input`, `.history-panel-filters input`, mobile recents filter inputs, and `#mobile-cmd`.
      - Candidate classes: `.form-control`, `.form-control-compact`, `.control-row`.
      - Preserve mobile composer keyboard anchoring and iOS font-size behavior as explicit local exceptions.
    - **Chip/badge primitive**
      - Shared by `.hist-chip`, `.history-active-filter-chip`, mobile `.filter-chip`, `.search-signal-chip`, `.history-entry-kind`, and mobile `.sheet-item-kind`.
      - Candidate classes: `.chip`, `.chip-action`, `.chip-removable`, `.chip-tone-*`, `.badge`.
      - Keep semantic tone decisions (`green`, `amber`, `red`) explicit and avoid making all chips look clickable when they are informational badges.
    - **Drawer/sheet structure primitive**
      - Shared by History drawer, Run Monitor drawer, mobile recents sheet, mobile menu sheet, and modal bottom-sheet mode.
      - Candidate classes: `.chrome-drawer`, `.bottom-sheet`, `.surface-header`, `.surface-body`, `.surface-footer`.
      - Keep placement and animation local where geometry differs, but centralize header/body/footer bands, borders, and sheet/drawer shell treatment.
  - Pressable exceptions to review:
    - `.sheet-clear-btn`
    - `.sheet-filter-row`
    - `.menu-item`
    - `.menu-subitem`
    - `.history-action-btn`
    - `.chrome-btn`
    - `#mobile-run-btn`, `#mobile-kill-btn`
    - `#search-prev`, `#search-next`
    - Decide whether each should move onto `.btn`, `.nav-item`, `.toggle-btn`, `.close-btn`, `.kb-key`, or a new row/control primitive. Keep exceptions only when the surface has a documented structural reason.
  - Lower-priority / likely-specific surfaces:
    - Tabs, status pills, Run Monitor CPU/MEM meters, theme-card previews, and welcome output have enough bespoke behavior that they should not be forced into broad structural primitives in the first pass.
    - These surfaces can still participate in the later derived-token cleanup if they reuse common color roles.
  - Implementation order:
    - Start with the dropdown/menu primitive because it has the clearest duplication and should reduce inconsistencies across save menus, app-native selects, autocomplete, and mobile filter dropdowns.
    - Follow with row and chip primitives because they cover the most repeated chrome/list objects.
    - Then revisit form controls and drawer/sheet structure, where mobile-specific behavior needs more careful regression testing.
    - After each primitive pass, update `ARCHITECTURE.md` Frontend Design System docs and tighten `tests/js/fixtures/button_primitive_allowlist.json` or add runtime primitive tests where JS renders the surface.
  - Guardrails:
    - Avoid introducing primitives that are only aliases for one selector.
    - Avoid making component markup harder to read solely to reduce CSS line count.
    - Keep visual review small but representative: desktop History, Run Monitor, Files, Options, autocomplete, mobile recents, and mobile menu.
    - Run focused unit tests for helper/rendering changes and at least one browser smoke path for any primitive that changes a mobile sheet or keyboard-adjacent surface.

- **Centralize local color transforms into derived theme tokens**
  - Problem:
    - The surface-token pass removed the major one-off surface roles, but the component CSS still contains many local `color-mix()` formulas for washes, soft borders, text blends, glows, shadows, dropdown outlines, search affordances, mobile running indicators, Run Monitor meters, and welcome-screen decorative states.
    - Some local transforms are legitimate state math, but leaving formulas scattered across `app/static/css/*.css` makes it easy for similar states to drift and harder for theme authors to tune the app consistently.
  - Direction:
    - Add a small derived-token layer rather than one token per selector. Candidate roles include soft/medium green washes, amber/red washes, muted text blends, soft borders, dropdown outlines, chrome meter rings, mobile running indicators, search highlight fills, and scrollbar track/thumb colors.
    - Keep semantic transforms in theme/config values when they are true theme roles, and keep one-off animation-only math local when it is purely transient geometry/opacity.
    - Replace repeated local formulas with shared variables only when the visual role is reused or theme authors would reasonably want to tune it.
  - Audit starting points:
    - Prompt selection/caret/dropdown outlines in `app/static/css/base.css`.
    - Search bar, signal chips, toggle buttons, and button primitives in `app/static/css/components.css`.
    - Mobile running chip/edge glows in `app/static/css/mobile.css`.
    - Run Monitor meter accents and HUD affordance details in `app/static/css/shell-chrome.css`.
    - Welcome decorative tints in `app/static/css/welcome.css`.
    - Terminal/export scrollbar styling shared between `app/static/css/shell.css` and `app/static/css/terminal_export.css`.
  - Guardrails:
    - Do not reintroduce surface-specific tokens for modals, chrome, or rows unless a genuinely new role appears.
    - Keep the first pass small enough for visual review across `darklab_obsidian`, a light theme, and one non-green dark theme.
    - Update `THEME.md` only for stable derived roles that theme authors should know about.

- **Normalize theme tokens across shared surfaces**
  - Problem:
    - The theme system has enough surface-specific tokens that visually similar objects can drift apart. For example, Options and Keyboard Shortcuts can render with different modal backgrounds, Files and Shortcuts do not have the same explicit theme sections as older modals, and newer drawer surfaces can end up choosing colors by local CSS instead of shared semantic roles.
    - Several tokens appeared to encode the same role (`faq_modal_bg`, `options_modal_bg`, older confirm modal backgrounds, workspace/workflows/shortcuts modal backgrounds, older mobile menu backgrounds, sheet backgrounds, row backgrounds) while other surfaces relied directly on `surface`, `panel_bg`, or older status-bar roles.
  - Inventory pass:
    - Started in `docs/theme-inventory.md`.
    - Build a table of shared UI objects and their current background/border/text tokens: Options, FAQ, Keyboard Shortcuts, Workflows, Files, Theme selector, Confirm dialogs, History drawer, Run Monitor drawer, mobile sheets, dropdowns, toasts, file/history/run rows, modal sections, form controls, chips, and inline code blocks.
    - For each object, record whether it is a modal, sheet, drawer, row, section, control, or semantic state. The goal is to classify by role before touching colors.
    - Include at least the default dark theme, one light theme, and one non-green dark theme in the first visual comparison so consolidation does not accidentally optimize only for Darklab Obsidian.
  - Target token model:
    - Keep the base palette small: `bg`, `surface`, `border`, `border_bright`, `text`, `muted`, `green`, `amber`, `red`, `blue`.
    - Standardized semantic shared tokens include `modal_bg`, `chrome_bg`, `chrome_header_bg`, `chrome_row_bg`, `chrome_row_hover_bg`, `chrome_control_bg`, `chrome_control_border`, `chrome_divider_color`, `chrome_shadow`, and `inline_surface_bg`.
    - Preserve intentional component identities for surfaces that should differ: `terminal_bar_bg`, tab styling, and theme-selector presentation if it needs special treatment.
    - Retired old per-surface tokens after migrating CSS consumers and regenerated shipped theme examples, rather than keeping a long-term alias layer.
  - CSS refactor direction:
    - Introduce shared structural classes for color decisions: `.modal-surface`, `.sheet-surface`, `.drawer-surface`, `.surface-row`, `.surface-section`, and `.control-surface`.
    - Keep ID selectors for sizing, positioning, and surface-specific layout only. Avoid new ID-level color decisions unless there is a documented exception.
    - Start with modal/sheet background consolidation because it is the most visible inconsistency: Options, FAQ, Keyboard Shortcuts, Workflows, Files, Theme selector, and Confirm dialogs.
    - Then consolidate drawer/row backgrounds for History and Run Monitor.
  - Theme cleanup:
    - Audit all `app/conf/themes/*.yaml` files for identical or near-identical surface tokens that can be removed or changed to canonical values.
    - Mark tokens that are intentionally different per theme versus tokens that only differ because the theme files drifted.
    - Update `THEME.md` with the canonical surface-token roles and examples of when a component-specific override is acceptable.
  - Guardrails:
    - Add tests that every shipped theme defines the required canonical tokens or inherits documented defaults.
    - Add a CSS/theme drift check that flags new hardcoded modal/drawer background colors and new per-surface background tokens unless allowlisted.
    - Add visual capture coverage for Options, FAQ, Keyboard Shortcuts, Workflows, Files, History drawer, Run Monitor, and mobile sheets in default dark plus one light theme.

- **Move built-in autocomplete grammar into the command registry**
  - Current state:
    - External command autocomplete is declarative in `app/conf/commands.yaml`.
    - Several built-in commands (`var`, `file`, `runs`, `session-token`, `config`, `theme`, `man`, `which`, `type`) rebuild similar autocomplete structures in `app/static/js/app.js`.
    - This duplicates registry concepts such as subcommands, flags, `closes: true`, value expectations, examples, and argument hints.
  - Target shape:
    - Add a built-in autocomplete section to the registry, likely separate from external `commands:` entries so app-owned command grammar does not look like external execution policy.
    - Keep static grammar in YAML: roots, subcommands, flags, examples, descriptions, `closes`, `takes_value`, argument placeholders, and sequence/value expectations.
    - Keep dynamic suggestion providers in code behind named hooks, such as workspace files, session variables, theme names, config option values, and command lookup candidates for `man` / `which` / `type`.
    - Have `/autocomplete` merge external command context and built-in command context into the same frontend shape the matcher already understands.
    - Remove duplicated built-in autocomplete object construction from `app/static/js/app.js` after parity tests are in place.
  - Testing:
    - Add loader tests proving built-in registry metadata maps to the same frontend context shape as external command metadata.
    - Add autocomplete tests for `closes: true`, subcommand value expectations, runtime hook fallback, and dynamic suggestions layered onto declarative built-in grammar.
    - Keep workspace/theme/config/session-variable autocomplete regression tests during the migration.

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
