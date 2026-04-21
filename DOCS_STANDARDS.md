# Documentation Standards

This document defines how project documentation should be structured and maintained.

The goal is not to make the docs shorter. The goal is to keep the same level of detail while making the docs easier to scan, browse, and review.

For planned documentation cleanup work, see [TODO.md](TODO.md). This file is the standing source of truth for how docs should be written going forward.

---

## Core principles

- Preserve detail. Do not simplify away technical nuance just to make a section shorter.
- Optimize for scanability. Long dense prose should become summary lines, flat bullets, short subsections, tables, or examples when that improves lookup and navigation.
- Keep prose where sequence matters. Request flows, rationale, and decision history should remain prose-first when order is part of the meaning.
- Keep one concern per unit. Avoid bullets or paragraphs that mix user-visible behavior, implementation detail, and validation notes unless that grouping is genuinely necessary.
- Respect the audience boundary of each document. End-user/operator docs should not drift into internal implementation notes, and developer docs should not lose the technical detail they need.
- Preserve anchors, cross-links, and doc-test expectations unless there is a strong reason to change them.

---

## General rules

### Summary first

Lead long sections with one of the following:

- a short framing paragraph
- a bold lead sentence
- a summary bullet

The lead should tell the reader what the section is about before the details begin.

### Use the right shape for the content

- Use prose for narratives, request flows, and rationale.
- Use flat bullets for contracts, responsibilities, inventories, and constraints.
- Use tables for lookup-oriented reference material such as route inventories, config keys, or feature matrices.
- Use short subsections when a section is trying to explain multiple related but distinct concerns.

### Avoid structural drift

- Do not introduce deep nesting unless the content truly needs hierarchy.
- If a bullet gets too long, split it or promote the content into a short subsection.
- If a labeled bullet or sub-bullet still carries multiple parallel points, split it into short child bullets rather than leaving it as a 4-5 sentence blob.
- One additional bullet level is allowed when the parent is acting as a labeled container such as `Before`, `After`, `Fix`, `What`, `Tests`, `Behavior`, or `Configuration`, and the child bullets stay parallel and flat.
- If a section has a repeated pattern, normalize the shape across sibling sections.

### Prefer stability

- Keep tables of contents, heading anchors, and appendix structures stable when possible.
- If a doc is covered by doc-drift or appendix tests, structural changes must still satisfy those tests.

### When in doubt, leave as prose

If a section is already stable, coherent, and not mixing concerns, do not “bullet-ify” it just because a style guide exists.

---

## Canonical templates

These templates define the preferred shape for common doc types in this project. Copy the shape, not the literal wording.

Each template lists a set of **Invariants** — the contract the shape is meant to carry. Honour the invariants even when the skeleton is adapted.

### T1. Release-entry umbrella shape

Use for multi-phase or multi-subsystem refactors in `CHANGELOG.md`.

Shape:

```md
- **{Refactor name} — {one-sentence framing of scope + motivation}** so that {outcome}.
  - **Phase 1 — {what changed, one line}.**
    - Contract: {what callers/readers get}
    - Migrated: {files or surfaces touched}
    - Removed: {what was retired}
    - Test coverage: {new tests or coverage additions}
    - Net delta: {suite counts or measurable impact if relevant}
  - **Phase 2 — ...**
```

Invariants:

- Umbrella lead is self-contained — a reader gets the full scope without reading any phase.
- Every phase is itself bold-led and skimmable.
- Phases share consistent axes (Contract / Migrated / Removed / Test coverage).

Use this when the reader benefits from seeing repeated structure across phases. Do not use it for simple one-shot changes — reach for T2 instead.

### T2. Release-entry single-shot shape

Use for one-shot `Added`, `Changed`, `Fixed`, or `Removed` entries in `CHANGELOG.md`. T2 has a short form and a long form; pick based on the entry's complexity.

#### T2 short form

Use when the entry is ≤4 sentences and carries a single concept.

Shape:

```md
- **{Outcome in one bold sentence}** — {short follow-on explanation covering mechanism, constraint, or scope}.
```

Invariants:

- Bold lead is skimmable on its own.
- Implementation note is short — one sentence, one scope.

#### T2 long form

Use when the entry is ≥5 sentences, OR has distinct root-cause / implementation / tests concepts that blur together as prose. The sub-bullet labels depend on the section the entry lives in:

- `### Fixed` — **Root cause / Fix / Tests**
- `### Added` — **Why / What / Tests**
- `### Changed` — **Before / After / Tests**

Shape:

```md
- **{Outcome in one bold sentence}** — {optional 1-sentence framing}.
  - **{Context label}:** {what was there before / what motivated the change}
  - **{Change label}:** {what happened — mechanism, files, key invariant}
  - **Tests:** {cases added or changed + suite delta if applicable}
```

Invariants:

- Bold lead is still skimmable on its own — the long form never buries the outcome.
- Sub-bullet labels match the section semantics (do not mix Root-cause labels into `### Added` entries or vice versa).
- The **Tests** sub-bullet is always present, even if the value is `no new cases — {how the change was verified}`.
- One additional child-bullet level is allowed inside labeled sub-bullets such as `Before`, `After`, `Fix`, `What`, or `Tests` when it improves scanability by splitting parallel points.
- Use T1 only when the change is genuinely an umbrella with multiple stages or coordinated subprojects, not merely because a T2 long entry needs child bullets for clarity.

#### T1 vs T2 long: which one?

Both shapes use indented sub-bullets, so the choice is easy to get wrong.

- **T1** — one *umbrella* change split across multiple *phases*. Each sub-bullet is its own phase with Contract / Migrated / Removed / Tests axes.
- **T2 long** — one *atomic* change decomposed into the three semantic axes for its changelog section (Root cause / Fix / Tests, etc.). Child bullets are fine when they keep those axes readable; phases are not.

If the work shipped as one commit or one coordinated change, use T2 long. If it shipped across multiple deliberate stages the reader needs to walk through, use T1.

### T3. Merge-request doc shape

Use for merge-request drafts.

Required section contract (top-level headings):

- `Summary`
- `Validation`
- `Risks`
- `Docs`

Do not add or remove those top-level headings. Sub-structure inside each section is the author's choice — the shape below is a suggested starting point, not a second layer of requirements.

Suggested shape:

```md
## Summary
### What changed
{paragraph + inventory bullets}

### Why it changed
- {pain point}
- {pain point}

## Validation
- {checks run}
- {test totals or coverage deltas}

## Risks
- {risk and mitigation}

## Docs
- **{file}** — {what changed}
```

Invariants:

- The four required top-level headings are always present, in order.
- Validation carries concrete evidence (commands run, counts, deltas) — not a promise that it was tested.
- Risks names the risk and its mitigation in the same bullet.

### T4. Architecture section shape

Use for `ARCHITECTURE.md` sections that are inventory- or contract-shaped.

Shape:

```md
## {Section name}
{Short framing paragraph}

- {responsibility}
- {responsibility}
```

Or, for lookup-heavy sections:

```md
## {Section name}
{Short framing paragraph}

| Column | Column | Column |
| ------ | ------ | ------ |
| ...    | ...    | ...    |
```

Invariants:

- Framing paragraph comes first; the table or bullet list follows.
- Request-flow narratives stay prose — do not convert them into bullets when order is part of the meaning.
- Sibling sections across the doc feel consistent in shape.

### T5. Feature inventory shape

Use for `FEATURES.md` sections where the reader is looking up how a feature works.

Preferred order:

```md
## {Feature name}
**Purpose:** {one line}

{Behavior paragraph or bullets}

**Limits:** {if applicable}
**Configuration:** {if applicable}
**Related files:** {if useful for contributors}
```

Invariants:

- **Purpose:** is always present.
- Other labeled fields are optional, but sibling sections that genuinely have limits or configuration must not silently skip them.
- Detailed reference material (YAML examples, tables, long lists) sits below the labeled fields, not inline within them.

### T6. Testing overview shape

Use for `tests/README.md` overview sections.

Preferred order:

````md
### {Suite name}
{What the suite covers}

```bash
{recommended command}
```

{Optional notes on config, artifacts, or gotchas}
````

Note: the outer fence here is four backticks so the inner ```bash command block nests cleanly. Use the same trick (or `~~~md`) any time a template skeleton needs to contain a fenced block.

Invariants:

- Summary first — heavy detail belongs in the appendix, not the overview.
- The command block is the canonical invocation reviewers will copy-paste.
- Notes after the command cover config, artifacts, and gotchas — not implementation trivia.

### T7. Release-note entry shape

Use for release-note drafts.

Shape:

```md
### {User-facing feature name}
{Framing paragraph in end-user/operator language}

- {concrete improvement}
- {concrete improvement}
```

Invariants:

- End-user / operator voice throughout — no internal function names, private module paths, or raw test-count deltas.
- Operator-facing references (config keys, routes, keyboard chords, tool names) are fine.
- Framing paragraph leads; concrete improvements follow as bullets.

---

## Per-document guidance

### `README.md`

- Keep it oriented to end-users and operators first.
- Separate what the app does, how to run it, and where to look next.
- Prefer lookup-friendly sections for configuration and project structure.

### `FEATURES.md`

- Keep it as the high-detail feature reference.
- Normalize feature sections where practical so readers can skim similar fields in similar order.
- Separate examples and authoring notes from the core feature description when a section becomes too dense.
- If `Behavior`, `Limits`, `Configuration`, or `Related files` starts carrying several parallel points, split that field into short child bullets instead of leaving it as one dense block.

### `ARCHITECTURE.md`

- Keep deep technical detail.
- Use short framing paragraphs plus bullets/tables for contracts and inventories.
- Keep request flows and system narratives prose-first.
- Prefer grouping related runtime concepts together rather than repeating small architecture notes across distant sections.
- When a contract or inventory bullet becomes a dense reference blob, split it into child bullets instead of forcing readers through long mixed-purpose prose.

### `DECISIONS.md`

- Keep rationale-first writing.
- Strong one-line lead statements are good.
- Preserve the ADR-style feel of each entry.
- Use labeled groups like problem, solution, tradeoffs, or consequences when that makes a decision easier to review.

### `CONTRIBUTING.md`

- Keep it concise and workflow-focused.
- Link out to deeper standards docs rather than embedding full style guidance inline.

### `tests/README.md`

- Keep the appendix exhaustive.
- Keep overview sections handbook-like and summary-first.
- Any structural changes must still pass `tests/py/test_docs.py`.
- If overview notes grow into several distinct caveats, configs, or artifact rules, split them into child bullets rather than one long note block.

### `CHANGELOG.md`

- Favor skimmable bold-lead entries.
- Separate user-visible outcomes from internal implementation notes when possible.
- Use T2 short for one-scope entries (≤4 sentences).
- Use T2 long when the entry is ≥5 sentences or has distinct root-cause / implementation / tests concepts.
- Use T1 only for multi-phase umbrellas — not as a substitute for T2 long.
- If a `Before` / `After` / `Fix` / `What` / `Tests` bullet still contains several distinct points, split it into one additional child-bullet level instead of leaving a paragraph-sized block.

### `THEME.md`

- Prefer short rules, tables, and lookup-oriented sections for theme tokens and authoring guidance.
- Keep longer prose only where sequencing or resolution order matters.

### Merge-request and release-note drafts

- Merge-request drafts must keep the required MR section contract.
- Release-note drafts should stay user- and operator-facing, not turn into engineering change logs.

---

## Review checklist

Before finalizing doc changes, check:

- Does the section still contain the same substantive detail?
- Is the lead clearer than before?
- Did any bullet become too dense or try to carry too many concerns?
- Does any labeled bullet or sub-bullet still contain multiple sentence-level ideas that should become child bullets?
- Would a reader have to parse a 4-5 sentence block to find one fact that should be scannable?
- Was prose kept where sequencing or rationale matters?
- Are sibling sections more consistent than before?
- Do anchors and cross-links still resolve?
- For CHANGELOG entries, does the T2 short vs T2 long choice match the ≥5-sentence / multi-concept threshold?
- Does `python -m pytest tests/py/test_docs.py -q` still pass (21/21)?
- Does `npm run lint:md` still report zero errors?

---

## Anti-patterns

Avoid these:

- turning every paragraph into bullets without improving structure
- mixing user-facing behavior, implementation detail, and validation notes in one long bullet
- over-nesting bullets until the section becomes harder to scan than the original prose
- keeping paragraph-sized labeled bullets when the content is really a small list of parallel points
- moving contributor-only details into end-user docs
- adding implementation trivia to release notes
- restructuring tested appendices or file trees casually without checking the doc gates

---

## Decision rule

If a proposed rewrite makes the structure cleaner but the meaning flatter, do not take it.

The standard is not “more bullets.” The standard is “same detail, easier to navigate.”
