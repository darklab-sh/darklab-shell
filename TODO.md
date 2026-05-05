# TODO

This file tracks open work, known issues, technical debt, and product ideas for darklab_shell. Open TODOs, known issues, and technical debt are confirmed items. Ideas are possible future work, not committed plans.

---

## Table of Contents

- [Open TODOs](#open-todos)
- [Research](#research)
- [Known Issues](#known-issues)
- [Technical Debt](#technical-debt)
- [Ideas](#ideas)
- [Architecture](#architecture)

---

## Open TODOs

No open implementation TODOs are currently tracked.

---

## Research

No research items are currently tracked.

---

## Known Issues

No active known issues are currently tracked.

---

## Technical Debt

- **Autocomplete client: hint-source resolution and item construction duplication**
  - `app/static/js/autocomplete.js` rebuilds the same hint-array → item mapping in five separate places (lines 776–786, 799–809, 856–863, 881–890, 897–906), each with the same `value`/`label`/`description`/`replaceStart`/`replaceEnd`/`insertValue` shape. A single `_hintsToItems(hints, ctx)` helper would collapse all five.
  - `_buildContextAutocomplete` repeats a four-step "pick the right hint source" dance four times (sequence-hints branch, direct-hints branch, and two positional branches): compute workspace-path hints, optionally compute workspace-target hints, fall back to the base hints, choose the filter query depending on whether path hints are active, build items, then wrap in `_withTypedValueSlotSuggestions`. Extracting one resolver makes each call site a few lines and removes the drift risk.
  - `_withRecentDomainSuggestions` and `_withWordlistSuggestions` (lines 321–345) are the same function with different special-item producers — both build a lowercased `seen` key set from insert values, then prefix the specials onto a deduped base. One `_prependDedupedItems(specials, base)` covers both; `_withTypedValueSlotSuggestions` keeps the routing.

- **Autocomplete client: three near-identical positional-arg walks**
  - `_countCompletedPositionalValues` (lines 231–258) and `_countCompletedPositionalArgs` (lines 508–533) implement the same skip-next/expects-value/skip-flag/skip-concrete-token traversal. The first is a strict superset; the second can be the more general one called with empty options, or they can be unified outright.
  - `rememberRecentDomainsFromCommand` (lines 354–418) re-implements the same walk a third time to *collect* values instead of *count* them. A shared `walkPositionalArgs(ctx, spec, contextSpec, callback)` that yields `{slotIndex, token, isTriggered, triggeringFlag}` would let counters and collectors share one implementation. Three copies of the same walk is the highest drift-risk surface in this file.

- **Autocomplete client: tiny duplicated predicate and extractor families**
  - `_itemLooksLikeDomainSlot` / `_itemLooksLikeWordlistSlot` / `_itemLooksLikeWorkspaceTargetSlot` (lines 162–172) only differ by the `value_type` constant they compare against — collapse into `_itemValueTypeIs(item, type)`.
  - `_domainArgHintTriggers` (line 184) and `_wordlistArgHintTriggers` (line 191) only differ by predicate — collapse into `_argHintTriggersBy(spec, predicate)`.
  - `_positionalDomainSlots` (line 214) and `_positionalWordlistSlots` (line 221) share shape and differ only by the per-element transform — pass the transform in.

- **Autocomplete client: thin wrappers around `DarklabAutocompleteCore`**
  - About a dozen one-line passthroughs at the top of `autocomplete.js` (lines 4–40, 86–88, 102–112, 154–155, 980) rename `_autocompleteCore.method` to `_acMethod`. They add no indirection and force the reader to map two names to one function. Aliasing the module once (`const core = DarklabAutocompleteCore;`) and calling `core.itemText(...)` at use sites would remove the layer.
  - `_writeRecentDomains` (line 98) is a wrapper that just calls `setRecentDomains` — same category.

- **Autocomplete client: suspected defects to verify while refactoring**
  - Line 848: `flag.value + (ctx.atWhitespace ? '' : '')` — both ternary branches are the empty string. Either dead code or lost intent.
  - `_filterExampleAutocompleteItems` (lines 640–644): filters once, builds a Set of survivors, then re-filters the original list. The only effect is to restore YAML-author order after `_filterAutocompleteItems` sorts by score. If intentional, deserves a one-line comment; otherwise a single `filterItems` call is enough.
  - `_buildPipeAutocomplete` (lines 927–934) with a command root delegates to `_buildContextAutocomplete(ctx)` and never uses the `baseCommand` / `pipeIndex` fields the pipe context attaches. Either those fields are dead weight or the context-builder should be using them and isn't.

- **Autocomplete value-type slot routing should be data-driven**
  - The mapping `value_type → suggestion source` is spread across `_isAutocompleteDomainValueSlot`, `_autocompleteWordlistValueSlot`, and `_workspaceAutocompleteHintsForTargetSlot`. Adding a new typed slot today requires JS edits in several places even though the YAML side already declares `value_type: <kind>`.
  - A small in-JS registry like `{ domain: {...}, wordlist: {...}, target: {...} }` keyed on `value_type` would let new slot kinds be added in one place, with the YAML remaining the source of truth for *which* slot type each hint represents.

- **Placeholder detection should be an explicit YAML flag, not a regex**
  - `DarklabAutocompleteCore.isPlaceholderValue` (autocomplete_core.js:40) decides whether a value is a hint-only placeholder by matching `/^<[^<>\s][^<>]*>$/`. Whether something is a placeholder is fundamentally an authorial choice, and `buildItem` already accepts an explicit `hintOnly`.
  - Promote `hint_only: true` on the YAML entry as the canonical signal, leave the regex as a fallback that emits a warning, then remove the autodetect once authors have migrated.

---

## Ideas

These are product ideas and possible enhancements, not committed TODOs or planned work.

- **Tool-specific guidance**
  - Add lightweight inline notes for tools with non-obvious web-shell behavior like `mtr`, `nmap`, `naabu`, or `nuclei`.
  - Good fit for the existing help / FAQ / welcome surfaces.
  - Merge this with onboarding and command hints into a broader user guidance layer:
    - command-specific caveats
    - what to expect while a tool runs
    - examples of when to use one tool vs another

- **Command outcome summaries**
  - For selected tools, generate short app-native summaries below the raw output. Security tool output is high-volume; a clear findings layer is what separates a purpose-built tool from a raw terminal.
  - Keep raw output primary — the summary is additive, never a replacement.
  - Start narrow: nmap (open ports + service table), dig (records returned), curl (status code + redirect chain), openssl s_client (cert expiry + trust chain).
  - The structured output model (see Architecture) is the right long-term foundation. Build this feature so it can move onto that model later instead of requiring it up front.

- **Run comparison enhancements**
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

- **Bulk history operations**
  - The history drawer can delete all or delete non-favorites. Adding multi-select (checkbox mode) with bulk delete, bulk export to JSONL/txt, and bulk share would close a real gap when clearing out a session after an engagement or exporting selected findings.

- **Autocomplete suggestions from output context**
  - When a previous command's output is in the active tab, `| grep` completions could suggest patterns already present in that output — IP addresses, hostnames, status codes, CVE strings — as candidates alongside the generic flag list.
  - Narrow but would make the pipe stage feel predictive rather than generic.

- **Mobile share ergonomics**
  - The native share-sheet for permalink URLs is done (v1.5, `navigator.share()` with clipboard fallback). What remains is making the broader mobile save/share experience feel intentional:
    - save/share actions tuned for one-handed use
    - clearer copy/share/export affordances inside the mobile shell
    - better share handoff after snapshot creation

---

## Architecture

- **Full reconnectable live stream**
  - Explore a live-output path that can fully resume active command streams after reload rather than restoring a placeholder tab and polling for completion.
  - This is separate from the current active-run reconnect support and would likely require:
    - a per-run live output buffer
    - resumable stream offsets or event IDs
    - multi-consumer fan-out instead of one transient SSE consumer
    - explicit lifecycle cleanup once runs complete
  - Best fit is a dedicated live-stream architecture pass rather than incremental UI polish.

- **Structured output model**
  - Preserve richer line/event details consistently for all runs.
  - This would improve search, comparison, redaction, exports, and permalink fidelity.
  - Command outcome summaries are buildable without this foundation, but design them so they can move onto the structured model later. Summary parsers should consume structured line events, not re-parse raw text forever.

- **Unified terminal built-in lifecycle**
  - Browser-owned built-ins (`theme`, `config`, and `session-token`) need browser execution for DOM state, local storage, clipboard, and transcript-owned confirmations, while server-owned built-ins naturally flow through `/runs`.
  - The long-term cleanup target is one terminal-command lifecycle after execution:
    - normalize built-in output into a shared result shape
    - apply pipe helpers against that shape
    - mask sensitive command arguments once
    - render transcript output once
    - persist server-backed history once
    - load recents and prompt history from the same saved run model
  - Keep execution ownership separate where it matters, but remove duplicated recents/history/pipe/persistence glue so browser-owned and server-owned built-ins cannot drift.

- **Plugin-style helper command registry**
  - Turn the built-in command layer into a cleaner extension point for future app-native helpers.

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
