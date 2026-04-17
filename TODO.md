# TODO

This file tracks open work items, known issues, and product ideas for darklab shell. Open TODOs, known issues, and technical debt are confirmed items. Ideas are speculative — not committed or planned.

---

## Table of Contents

- [Open TODOs](#open-todos)
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

### Persistent session tokens (cross-browser identity)

Allow users to generate a personal session token so their run history, snapshots, and starred commands follow them across browsers and workstations — without a login screen.

**Design rules**
- No login screen. Tokens are the only identity mechanism.
- Token = session ID. The server treats a `tok_…` string identically to a UUID — all existing session-scoped queries work unchanged.
- Token is stored in `localStorage` and sent as `X-Session-ID`, same as the auto-generated UUID today.
- Tokens are server-generated (cryptographically random, `tok_` prefix) to prevent guessing and to distinguish them from UUID sessions in logs and the DB.

**Phase 1 — token management + history migration** ✅ _implemented in v1.5_

_Backend_
- ✅ `GET /session/token/generate` — generates a `tok_<32 hex>` token, persists it in the `session_tokens` table, returns it.
- ✅ `POST /session/migrate` — migrates all runs and snapshots from `from_session_id` to `to_session_id`. Security constraint: `from_session_id` must match the `X-Session-ID` header.
- ✅ `session_tokens` table added to `database.py` schema with automatic migration for existing databases.

_Frontend — terminal commands_
- ✅ `session-token` — shows session token status (masked active token or "anonymous session").
- ✅ `session-token generate` — generates a token, saves to `localStorage`, prompts to migrate existing history if runs are present.
- ✅ `session-token set <value>` — accepts an existing token, optionally migrates history from the current session.
- ✅ `session-token clear` — removes session token from `localStorage`, reverts to auto-generated UUID.
- ✅ `session-token rotate` — generates a new token, migrates history atomically before switching identity.

_Frontend — options menu_
- ✅ "Session token" row in options panel with masked token status and Set/Clear buttons.

_session.js change_
- ✅ `SESSION_ID` prefers `localStorage.session_token` over the UUID `session_id`; `updateSessionId()` switches identity at runtime; `maskSessionToken()` provides display-safe representation.

**Phase 2 — server-side starred commands (cross-browser star sync)** ✅ _implemented in v1.5_

- ✅ Add `starred_commands` table: `(session_id TEXT, command TEXT, PRIMARY KEY (session_id, command))`.
- ✅ Add `GET /session/starred` — return starred command list for the current session.
- ✅ Add `POST /session/starred` and `DELETE /session/starred` — toggle a star server-side.
- ✅ Update `_getStarred()` and `_toggleStar()` in `history.js` to call these endpoints (async). Keep a local cache to avoid blocking the UI on every render.
- ✅ On `token set` / `token generate`: seed from `localStorage` on first token activation; `token rotate` migrates stars along with runs and snapshots.
- ✅ Seed from `localStorage` on first token activation for users who already have stars — read the existing `starred` array and POST each command to the new endpoint, then clear `localStorage` entry.

**Notes**
- "Token is a shared secret" — surface a short warning in the `token generate` output: tokens grant full session access to anyone who has them. Don't share.
- `token rotate` is a safety valve, not a core workflow — keep it simple.

---

## Known Issues

---

## Technical Debt

### Mobile shell and standalone page chrome parity

The recent header/export de-duplication work is already the right pattern for save flows: `ExportHtmlUtils` and `ExportPdfUtils` should remain the single source of truth for HTML/PDF output, including on mobile. The remaining duplication is around page chrome and responsive headers on mobile-facing pages, especially the main shell mobile header/menu and the diagnostics page header/back action.

**Plan**
- Extract a shared page-header partial or macro for standalone pages so `diag.html`, `permalink.html`, and any future mobile-friendly page can share the same title/meta/action scaffold instead of repeating header structure and responsive overrides.
- Move the mobile shell header/menu state updates out of page-specific DOM writes where possible so desktop and mobile labels for timestamps, line numbers, status, and menu actions come from the same helper path.
- Pull the mobile header sizing and spacing rules into reusable CSS tokens or a shared mobile chrome block, then keep only page-specific overrides local to `index.html` and `diag.html`.
- Keep the export renderers shared; do not add a separate mobile export pipeline. Any mobile save/share surface should call the existing `ExportHtmlUtils` / `ExportPdfUtils` helpers.
- Add a mobile viewport smoke test for the main shell header/menu, the diagnostics page back button, and a save/export action to catch regressions in the shared chrome layer.

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

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

- **Additional export formats**
  - Add Markdown and JSONL export in addition to `.txt` and themed `.html`.
  - Pairs naturally with the existing export system and structured output work.
  - Make structured exports first-class:
    - include command, timestamps, exit code, line classes, and preview/full-output metadata
    - treat `JSONL` as a real machine-readable export, not just another text dump

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

- **Full history search**
  - The history drawer searches the last 50 runs. There is no way to find a specific result from months ago without knowing the exact command.
  - Full-text search across all stored run history (command text + output) closes a real gap for operators who reuse the tool over extended engagements.
  - SQLite FTS is the natural backend; this is a query problem not an architecture change.

- **Browser notifications on run completion**
  - Scans frequently take 5–15 minutes. Operators work in another tab while waiting and miss the result.
  - Wire the existing run timer and SSE lifecycle tracking to the browser Notifications API with a one-time opt-in.
  - Notification body: command text, exit status, elapsed time.
  - Scope to completed and killed events only — do not notify for intermediate output.

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

- **Session dashboards**
  - Add a compact session summary view. The lowest-complexity version of this is a `session` or `stats` built-in command rather than a dedicated page — it fits the shell-primary interaction model and reuses the existing fake-command layer.
  - Built-in command output:
    - command breakdown by tool root
    - success/fail rates and average scan durations
    - starred artifact count
    - active session token status
  - Natural fit with history, diagnostics, and session tokens.

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

- **Environment capability hints**
  - Surface when a tool is likely to be slow, noisy, truncated, or constrained by the container/runtime before it runs.

- **Session token audit**
  - The current token lifecycle is missing two safety operations: `session-token list` and `session-token revoke`.
  - `session-token list` — show all tokens issued under the current identity with creation dates, so operators know which tokens are active across devices.
  - `session-token revoke <token>` — server-side DELETE from `session_tokens` to retire a compromised or lost token without triggering a full rotation. Currently the only recourse for a leaked token is `session-token rotate`, which migrates to a new token but does not explicitly invalidate the old one server-side.
  - Follows existing backend and terminal command patterns exactly.

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

- **Mobile share flow**
  - Better native share-sheet integration where the platform allows it.
  - Expand this into mobile-first action ergonomics:
    - save/share actions tuned for one-handed use
    - better share handoff after snapshot creation
    - clearer copy/share/export affordances inside the mobile shell

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

- **Structured command catalog**
  - Move from plain-text allowlist-only metadata toward a richer command catalog model.
  - This would unlock better autocomplete, command forms, grouped help, and policy hints.
  - Design parameterized command forms (see Later) against this catalog model before building them — both features need the same structured command data and will diverge if built independently.

- **Structured output model**
  - Preserve richer line/event metadata consistently for all runs.
  - This would improve search, comparison, redaction, exports, and permalink fidelity.
  - Command outcome summaries (see Near-term) are buildable without this foundation, but design them to be retro-fittable once the structured model is in place — the summary parsers should consume structured line events, not re-parse raw text.

- **Plugin-style helper command registry**
  - Turn the fake-command layer into a cleaner extension surface for future app-native helpers.

- **Ephemeral per-session workspace mode**
  - Add an optional tmpfs-backed per-session working directory so users can create short-lived files and use more natural shell workflows such as `ls`, `cat`, `rm`, and output redirection into files.
  - Treat this as a separate execution mode with its own validation, cleanup, quota, and audit model rather than as a small shell-ergonomics enhancement.
  - The existing allowed_commands system would need a paired workspace mode — `ls`, `cat`, `rm`, `mv`, and output redirection (`>`, `>>`) are either blocked metacharacters or not in the allowlist today. A workspace mode needs explicit allowlist support, not just a tmpfs allocation.
  - Scope the safety model explicitly:
    - per-session byte quota
    - max file size
    - max file count / inode-style limit
    - aggressive cleanup on expiry
    - optional app-mediated file download support from the active session workspace
  - Consider a stronger isolation path as a later phase:
    - a real per-session chroot-style jail or equivalent container-level filesystem jail so the shell process cannot see outside the session workspace at all
    - this would make the feature feel much more like a real shell while reducing accidental filesystem exposure

- **Lightweight Jinja base template**
  - `index.html` and `permalink_base.html` share ~10 lines of `<head>` bootstrap (charset, viewport, color-scheme meta, favicon, `fonts.css`, `styles.css`, theme var includes, and the two vendor scripts). With two templates this is not worth the indirection.
  - Revisit if the app adds a third distinct page type (e.g. a standalone diagnostics page, a mobile-specific shell view, or a public landing page) — at that point a `base.html` factoring out the common `<head>` and `data-theme` body attribute pays for itself.

- **Interactive PTY mode for screen-based tools**
  - Explore an optional PTY + WebSocket + browser terminal emulator path for a small allowlisted set of interactive or screen-redrawing tools such as `mtr`, without turning the app into a general-purpose remote shell.
  - Best fit is a separate interactive-command mode or tab type, not a full browser shell session.
  - This would be a larger architecture change because it needs:
    - server-side PTY management
    - bidirectional browser transport
    - terminal resize handling
    - stricter command scoping and lifecycle cleanup
