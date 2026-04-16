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

**Phase 1 — token management + history migration**

_Backend_
- `GET /session/token/generate` — generate a new `tok_…` token, persist it in a `tokens` table `(token TEXT PRIMARY KEY, created TEXT)`, return it. Does not migrate anything.
- `POST /session/migrate` — migrate all runs and snapshots from `from_session_id` to `to_session_id` in a single transaction:

  ```sql
  UPDATE runs      SET session_id = :to WHERE session_id = :from;
  UPDATE snapshots SET session_id = :to WHERE session_id = :from;
  ```

  Security constraint: `from_session_id` must equal the requester's current `X-Session-ID` header. Reject any request where they don't match to prevent cross-user history theft.
- Add `tokens` table to `database.py` schema (single column, no FK constraints needed — the session ID space is shared).

_Frontend — terminal commands_
- `token` — show token status: active token (masked, e.g. `tok_a1b2••••`) or "none (anonymous session)".
- `token generate` — call `/session/token/generate`, save the returned token to `localStorage` as `token_id`, update `SESSION_ID` in `session.js` to use it going forward. If the current session has any runs, prompt: _"You have N runs in this session. Migrate history to your new token? [yes/no]"_ — if yes, call `/session/migrate`.
- `token set <value>` — enter an existing token (e.g. from another device). Save to `localStorage`. If the current browser session has runs, offer the same migration prompt. If the current session is empty, silently switch.
- `token clear` — remove `token_id` from `localStorage`, revert to the auto-generated UUID. Does not delete any data.
- `token rotate` — generate a new token, migrate history from the current token to it, update `localStorage`. Old token's data is left in the DB under the old ID (effectively orphaned unless the user has another copy).

_Frontend — options menu_
- Add a "Session token" row to the options panel: shows current token status, with "Set token" and "Clear" controls as an alternative entry point for users who don't know the terminal commands.

_session.js change_
- On load: check `localStorage` for `token_id` first; if present, use it as `SESSION_ID`. Otherwise fall back to the existing `session_id` UUID. This is the only change needed to make the rest of the app token-aware.

**Phase 2 — server-side starred commands (cross-browser star sync)**

Starred commands are currently `localStorage`-only (`starred` key, array of command strings). They migrate automatically within the same browser (same `localStorage`) but won't follow a token to a new machine.

- Add `starred_commands` table: `(session_id TEXT, command TEXT, PRIMARY KEY (session_id, command))`.
- Add `GET /session/starred` — return starred command list for the current session.
- Add `POST /session/starred` and `DELETE /session/starred/:command` — toggle a star server-side.
- Update `_getStarred()` and `_toggleStar()` in `history.js` to call these endpoints (async). Keep a local cache to avoid blocking the UI on every render.
- On `token set` / `token generate`: migrate starred commands the same way as runs — `INSERT OR IGNORE INTO starred_commands SELECT :to, command FROM starred_commands WHERE session_id = :from`.
- Seed from `localStorage` on first token activation for users who already have stars — read the existing `starred` array and POST each command to the new endpoint, then clear `localStorage` entry.

**Notes**
- Document in `token generate` / `token set` output that Phase 1 migrates history and snapshots but not stars (until Phase 2 ships).
- "Token is a shared secret" — surface a short warning in the `token generate` output: tokens grant full session access to anyone who has them. Don't share.
- `token rotate` is a safety valve, not a core workflow — keep it simple.

---

## Known Issues

---

## Technical Debt

### Export rendering fragmentation

The save/export pipeline currently has rendering logic scattered across several places that must be kept in sync manually. The HTML export surface was partially consolidated into `ExportHtmlUtils` (`export_html.js`), but the PDF surface was not.

**Affected surfaces**

| Surface | HTML export | PDF export |
|---|---|---|
| Main UI (tab panel) | `exportTabHtml()` in `tabs.js` via `ExportHtmlUtils` | `exportTabPdf()` in `tabs.js` — standalone ~100-line function |
| Permalink page | `saveHtml()` in `permalink.html` via `ExportHtmlUtils` | `savePdf()` in `permalink.html` — near-duplicate of the above |
| Mobile | Inherits tab panel actions (same `terminal-actions` div moved to mobile transcript) — not separately verified | Same inheritance — not separately tested |

**Known drift points**
- `exportTabPdf()` and `savePdf()` are structurally identical but live in two files. Every visual tweak (font size, header layout, badge alignment, background colours) requires editing both.
- `buildTerminalExportStyles()` in `export_html.js` inlines a separate CSS block for downloaded HTML files. Changes to the live permalink page styles (`components.css`) do not automatically propagate to downloaded HTML, and vice versa — they are maintained independently.
- The permalink page's live header meta uses `text-transform: uppercase` via `components.css`; downloaded HTML uses `export_html.js` CSS. These can drift independently.
- Mobile save/export has never been explicitly tested after export changes were made.

**Recommended consolidation path**
- Extract the shared PDF rendering logic into a `ExportPdfUtils` module (e.g. `export_pdf.js`, loaded via Flask route like `export_html.js`). Both `tabs.js` and `permalink.html` call through it, passing a descriptor object with lines, metadata, and a `getPrefix` callback — same pattern as `buildExportLinesHtml`.
- Audit `buildTerminalExportStyles()` against the live `components.css` permalink styles and either unify them or document the intentional divergence so future changes don't silently drift.
- Add a mobile smoke-test pass to the export workflow whenever export changes ship.

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Near-term

- **Share annotations**
  - Add optional title, note, and tags to a snapshot permalink.
  - Good value without changing the core sharing model.

- **Additional export formats**
  - Add Markdown and JSONL export in addition to `.txt` and themed `.html`.
  - Pairs naturally with the existing export system and structured output work.

- **Better output navigation**
  - Jump to top/bottom, jump between warnings/errors, sticky command header for long runs, and optional output collapsing.
  - Best as a focused transcript usability pass rather than one-off controls.

- **Run comparison**
  - Compare two runs side by side, especially for repeated scans or before/after checks.
  - More compelling once history filtering is stronger.

- **Tool-specific guidance**
  - Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `wapiti`, or `nuclei`.
  - Good fit for the existing help / FAQ / welcome surfaces.

- **Richer run metadata in the history UI**
  - Surface preview/full-output availability, retention expectations, and share/export readiness more clearly.
  - Good fit for the existing history drawer and permalink model.

### Later

- **Saved command presets**
  - Let users save named command templates beyond history/starred entries.
  - Better for repeat workflows like DNS checks, HTTP triage, or common scan recipes.

- **Parameterized command forms**
  - Add optional structured builders for common tools like `curl`, `dig`, `nmap`, and `ffuf`.
  - Keep raw-shell usage intact while making common tasks easier.

### Mobile

- **Mobile share flow**
  - Better native share-sheet integration where the platform allows it.

### Safety and Policy

- **Richer audit trail**
  - Optional logging around share creation, deletions, and run access patterns.

- **Per-command policy metadata**
  - Allowlist entries could carry metadata like `risky`, `slow`, `high-output`, or `full-output recommended`.
  - The UI could surface this in help, warnings, or command builders.

### Content and Guidance

- **Tool-tips and onboarding hints**
  - Extend the welcome flow and help surfaces so onboarding suggests real tasks and tool combinations, not just isolated commands and hints.

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

- **Structured output model**
  - Preserve richer line/event metadata consistently for all runs.
  - This would improve search, comparison, redaction, exports, and permalink fidelity.

- **Plugin-style helper command registry**
  - Turn the fake-command layer into a cleaner extension surface for future app-native helpers.

- **Ephemeral per-session workspace mode**
  - Add an optional tmpfs-backed per-session working directory so users can create short-lived files and use more natural shell workflows such as `ls`, `cat`, `rm`, and output redirection into files.
  - Treat this as a separate execution mode with its own validation, cleanup, quota, and audit model rather than as a small shell-ergonomics enhancement.
  - Scope the safety model explicitly:
    - per-session byte quota
    - max file size
    - max file count / inode-style limit
    - aggressive cleanup on expiry
    - optional app-mediated file download support from the active session workspace
  - Consider a stronger isolation path as a later phase:
    - a real per-session chroot-style jail or equivalent container-level filesystem jail so the shell process cannot see outside the session workspace at all
    - this would make the feature feel much more like a real shell while reducing accidental filesystem exposure

- **Interactive PTY mode for screen-based tools**
  - Explore an optional PTY + WebSocket + browser terminal emulator path for a small allowlisted set of interactive or screen-redrawing tools such as `mtr`, without turning the app into a general-purpose remote shell.
  - Best fit is a separate interactive-command mode or tab type, not a full browser shell session.
  - This would be a larger architecture change because it needs:
    - server-side PTY management
    - bidirectional browser transport
    - terminal resize handling
    - stricter command scoping and lifecycle cleanup
