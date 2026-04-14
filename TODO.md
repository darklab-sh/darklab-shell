# TODO

## Open TODOs

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

### Next

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

### Mobile-Focused Ideas

- **Mobile share flow**
  - Better native share-sheet integration where the platform allows it.

### Safety / Policy Ideas

- **Richer audit trail**
  - Optional logging around share creation, deletions, and run access patterns.

- **Per-command policy metadata**
  - Allowlist entries could carry metadata like `risky`, `slow`, `high-output`, or `full-output recommended`.
  - The UI could surface this in help, warnings, or command builders.

### Content / Guidance Ideas

- **Guided workflows and onboarding**
  - Curated task-oriented entry points such as DNS troubleshooting, TLS checks, quick HTTP triage, or subdomain discovery.
  - Extend the welcome flow and help surfaces so onboarding suggests real tasks, not just isolated commands and hints.

### Live Stream Reattach

- **Full reconnectable live stream**
  - Explore a true reconnectable live-output path that can resume active command streams after reload rather than only restoring a placeholder tab and polling for completion.
  - This is a separate architecture step from the current active-run reconnect support and would likely require:
    - a per-run live output buffer
    - resumable stream offsets or event IDs
    - multi-consumer fan-out instead of one transient SSE consumer
    - explicit lifecycle cleanup once runs complete
  - Best fit is a dedicated live-stream architecture pass rather than incremental UI polish.

### Architecture-Driven Product Bets

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
