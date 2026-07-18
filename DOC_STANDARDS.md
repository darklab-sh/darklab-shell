# Documentation Standards

This document explains how project docs should be written and kept up to date.

The goal is not to make the docs shorter for its own sake. The goal is to keep the useful detail while making each page easier to scan, browse, and review.

For documentation cleanup backlog, see [TODO.md](TODO.md). This file is the standing guide for how docs should sound and be shaped.

---

## Core Principles

- Preserve detail. Do not flatten technical meaning just to make a section shorter.
- Make docs easy to scan. Long dense prose should become summary lines, flat bullets, short subsections, tables, or examples when that helps the reader find things.
- Keep prose where sequence matters. Request flows, rationale, and decision history should remain prose-first when order is part of the meaning.
- Keep one idea per paragraph, bullet, or table row. Avoid mixing user-visible behavior, implementation detail, and validation notes unless they really belong together.
- Match the doc to its reader. End-user/operator docs should not drift into internal implementation notes, and developer docs should not lose the technical detail they need.
- Give detailed procedures, tables, and contracts one canonical home. Other docs may keep short audience-specific context or point-of-action warnings, then link to the canonical detail.
- Write like a person. Use plain language, contractions, and a conversational tone when they make the text clearer. Prefer everyday words over jargon when the simpler word says the same thing.
- Preserve anchors, cross-links, and doc-test expectations unless there is a strong reason to change them. Add replacement checks before removing an existing documentation guard.

---

## General Rules

### Summary first

Lead long sections with one of the following:

- a short framing paragraph
- a bold lead sentence
- a summary bullet

The lead should tell the reader what the section is about before the details begin.

### Use the right shape for the content

- Use prose for narratives, request flows, and rationale.
- Use flat bullets for responsibilities, inventories, rules, and constraints.
- Use tables for lookup-oriented reference material such as route inventories, config keys, or feature matrices.
- Use short subsections when a section is trying to explain multiple related but distinct concerns.

### Avoid structural drift

- Do not introduce deep nesting unless the content truly needs hierarchy.
- If a bullet gets too long, split it or promote the content into a short subsection.
- If a labeled bullet or sub-bullet still carries several parallel points, split it into short child bullets rather than leaving it as a 4-5 sentence block.
- One additional bullet level is allowed when the parent is acting as a labeled container such as `Before`, `After`, `Fix`, `What`, `Tests`, `Behavior`, or `Configuration`, and the child bullets stay parallel and flat.
- If a section has a repeated pattern, normalize the shape across sibling sections.

### Prefer stability

- Keep tables of contents and heading anchors stable when possible.
- If a doc is covered by a documentation contract test, structural changes must still satisfy that contract or replace it with a more durable check first.
- Keep permanent navigation focused on maintained project docs. Release drafts, merge-request drafts, and pre-merge review findings stay out of canonical indexes, but their local links must still resolve while they exist.

### When in doubt, leave as prose

If a section is already stable, coherent, and not mixing concerns, do not “bullet-ify” it just because a style guide exists.

---

## Preferred Templates

These templates show the preferred shape for common doc types in this project. Copy the shape, not the exact wording.

Each template lists **Must keep** points. Keep those points even when you adapt the template.

### T1. Release-entry umbrella shape

Use for broad multi-subsystem refactors in `CHANGELOG.md`.

Shape:

```md
- **{Refactor name} — {one-sentence framing of scope + motivation}** so that {outcome}.
  - **{Subsystem or surface} — {what changed, one line}.**
    - Contract: {what callers/readers get}
    - Migrated: {files or surfaces touched}
    - Removed: {what was retired}
    - Test coverage: {new tests or coverage additions}
    - Net delta: {suite counts or measurable impact if relevant}
  - **{Next subsystem or surface} — ...**
```

Must keep:

- The umbrella lead is self-contained — a reader gets the full scope without reading every child bullet.
- Every child bullet is itself bold-led and skimmable.
- Child bullets share consistent axes (Contract / Migrated / Removed / Test coverage).

Use this when the reader benefits from repeated structure across related subsystems. Do not use it for simple one-shot changes — reach for T2 instead.

### T2. Release-entry single-shot shape

Use for one-shot `Added`, `Changed`, `Fixed`, or `Removed` entries in `CHANGELOG.md`. T2 has a short form and a long form; pick based on the entry's complexity.

#### T2 short form

Use when the entry is ≤4 sentences and carries a single concept.

Shape:

```md
- **{Outcome in one bold sentence}** — {short follow-on explanation covering mechanism, constraint, or scope}.
```

Must keep:

- Bold lead is skimmable on its own.
- The implementation note is short — one sentence, one scope.

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

Must keep:

- Bold lead is still skimmable on its own — the long form never buries the outcome.
- Sub-bullet labels match the section they live in (do not mix Root-cause labels into `### Added` entries or vice versa).
- The **Tests** sub-bullet is always present, even if the value is `no new cases — {how the change was verified}`.
- One additional child-bullet level is allowed inside labeled sub-bullets such as `Before`, `After`, `Fix`, `What`, or `Tests` when it improves scanability by splitting parallel points.
- Use T1 only when the change is genuinely an umbrella with multiple stages or coordinated subprojects, not merely because a T2 long entry needs child bullets for clarity.
- When sibling entries in the same changelog subsection are already using the section-specific long form, prefer that same shape for new comparable entries so the section scans consistently.

#### T1 vs T2 long: which one?

Both shapes use indented sub-bullets, so the choice is easy to get wrong.

- **T1** — one *umbrella* change split across multiple related subsystems or surfaces. Each sub-bullet has Contract / Migrated / Removed / Tests axes.
- **T2 long** — one *atomic* change decomposed into the three semantic axes for its changelog section (Root cause / Fix / Tests, etc.). Child bullets are fine when they keep those axes readable; phases are not.

If the work shipped as one commit or one coordinated change, use T2 long. If it spans multiple reader-relevant subsystems, use T1.

### T3. Architecture section shape

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

Must keep:

- Framing paragraph comes first; the table or bullet list follows.
- Request-flow narratives stay prose — do not convert them into bullets when order is part of the meaning.
- Sibling sections across the doc feel consistent in shape.

### T4. Feature inventory shape

Use for `FEATURES.md` sections where the reader is looking up how a feature works.

Preferred order:

```md
## {Feature name}
**Purpose:** {one line}

{Behavior paragraph or bullets}

**Limits:** {if applicable}
**Configuration:** {if applicable}
**Learn more:** {if a focused user or operator guide adds useful detail}
```

Must keep:

- **Purpose:** is always present.
- Other labeled fields are optional, but sibling sections that genuinely have limits or configuration must not silently skip them.
- Keep implementation paths and test-file inventories out of feature entries. Put durable contributor contracts in architecture, contributing, or a focused contributor guide.
- Detailed reference material (YAML examples, tables, long lists) sits below the labeled fields, not inline within them.

### T5. Testing overview shape

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

Must keep:

- Summary first; use the live runner-listing commands when readers need the current inventory.
- The command block is the canonical invocation reviewers will copy-paste.
- Notes after the command cover config, artifacts, and gotchas — not implementation trivia.

### T6. Release-note entry shape

Use for release-note drafts.

Shape:

```md
### {User-facing feature name}
{Framing paragraph in end-user/operator language}

- {concrete improvement}
- {concrete improvement}
```

Must keep:

- End-user / operator voice throughout — no internal function names, private module paths, or raw test-count deltas.
- Operator-facing references (config keys, routes, keyboard chords, tool names) are fine.
- Framing paragraph leads; concrete improvements follow as bullets.

### T7. Focused guide shape

Use for a topic-specific guide under `docs/`.

Preferred order:

```md
# {Guide name}
{Who this guide is for and what it helps them do.}

## {Task or reference section}
{Direct guidance, table, or example.}

## Related Docs
- [{Nearest prerequisite or next step}](...)
```

Must keep:

- State the audience and purpose before the detail.
- Own one named topic instead of repeating broad README, feature, configuration, or architecture material.
- Link to canonical configuration, architecture, or contributor contracts instead of copying them.
- Keep Related Docs curated to the few pages a reader is most likely to need next.
- Keep security, privacy, data-loss, licensing, and platform-limit warnings beside the action they constrain.

---

## Per-Document Guidance

### `README.md`

- Keep it oriented to end-users and operators first.
- Treat it as the landing page: explain what the app does, how to start it, and where to look next.
- Keep Quick Start focused on the normal release install. Put optional installer checksum and publisher-identity checks under Production Deployment, and keep repository-based workflows under Running in a Development Environment.
- Keep Installed Tools aligned with the external commands in the base command registry. List executable command names, not upstream project names or internal dependencies; keep app-native built-ins and pipe helpers in the feature reference.
- Keep the Repository Layout at directory level. The grouped Documentation Map is the exhaustive index of maintained project docs.

### `FEATURES.md`

- Keep it as the high-detail feature reference.
- Normalize feature sections where practical so readers can skim similar fields in similar order.
- Separate examples and authoring notes from the core feature description when a section becomes too dense.
- If `Behavior`, `Limits`, `Configuration`, or `Learn more` starts carrying several parallel points, split that field into short child bullets instead of leaving it as one dense block.
- Keep internal modules and test-file inventories out. Link focused user/operator guidance through `Learn more` and move durable contributor contracts to their owning technical guide.

### `ARCHITECTURE.md`

- Keep deep technical detail.
- Keep one stable `## Front End Design` section as the contributor-facing home for browser composition and design-system contracts.
- Use short framing paragraphs plus bullets/tables for contracts and inventories.
- Keep request flows and system narratives prose-first.
- Prefer grouping related runtime concepts together rather than repeating small architecture notes across distant sections.
- When a contract or inventory bullet becomes a dense reference blob, split it into child bullets instead of forcing readers through long mixed-purpose prose.
- Keep current design and runtime contracts here. Put rationale, rejected alternatives, and durable tradeoffs in `DECISIONS.md`.

### `DECISIONS.md`

- Keep the reasoning first.
- Strong one-line lead statements are good.
- Preserve the ADR-style feel of each entry.
- Use labeled groups like problem, solution, tradeoffs, or consequences when that makes a decision easier to review.

### `CONTRIBUTING.md`

- Keep it concise and workflow-focused.
- Link out to deeper standards docs rather than embedding full style guidance inline.

### `CONFIGURATION.md`

- Keep operator settings, deployment choices, and the canonical Supported Runtimes table here.
- Validate support claims against executable deployment and release contracts instead of comparing prose across documents.
- Keep procedures beside the settings they affect and link to focused guides for longer workflows.

### `tests/README.md`

- Keep it handbook-like and summary-first; don't maintain a table of every test or exact suite totals.
- Keep the lightweight pytest, Vitest, and direct Playwright listing commands current. Use `bash scripts/run_playwright.sh ...` for actual browser runs, not simple listing.
- Keep suite purpose, setup, workflow, layer selection, artifact, smoke-test, and convention guidance here.
- Any structural changes must still pass the durable contracts in `tests/py/test_docs.py`.
- If overview notes grow into several distinct caveats, configs, or artifact rules, split them into child bullets rather than one long note block.

### `CHANGELOG.md`

- Favor skimmable bold-lead entries.
- Include user/operator-visible outcomes, compatibility or support changes, security or privacy changes, data/schema/upgrade effects, and meaningful contributor contracts.
- Fold routine file moves, generated-asset refreshes, test-only maintenance, count deltas, and minor visual polish into a relevant outcome or omit them.
- Use one top-level entry per cohesive reader outcome. Summarize meaningful validation in a child bullet instead of listing every test or changed file.
- Separate user-visible outcomes from internal implementation notes when possible.
- Use T2 short for one-scope entries (≤4 sentences).
- Use T2 long when the entry is ≥5 sentences or has distinct root-cause / implementation / tests concepts.
- Use T1 only for broad subsystem umbrellas — not as a substitute for T2 long.
- If a `Before` / `After` / `Fix` / `What` / `Tests` bullet still contains several distinct points, split it into one additional child-bullet level instead of leaving a paragraph-sized block.
- Keep the active `Unreleased` section and the two newest dated releases in the root file. Move older entries intact to one archive per major version after the next active section is seeded.
- Treat a change to an already published release as an explicit historical correction with separate review. Do not rewrite published sections during routine cleanup or archive rotation.

### `THEME.md`

- Prefer short rules, tables, and lookup-oriented sections for theme tokens and authoring guidance.
- Keep longer prose only where sequencing or resolution order matters.

### Merge-request and release-note drafts

- Merge-request drafts must keep the required MR section contract.
- Release-note drafts should stay user- and operator-facing, not turn into engineering change logs.
- Keep drafts and pre-merge review findings out of the permanent Documentation Map and changelog archives.
- Validate repository-relative links and heading fragments while drafts exist.

### Focused guides under `docs/`

- Each guide owns its named user, operator, or contributor topic.
- Use T7 as the default shape and link back to canonical configuration, architecture, or feature material.
- Do not create another broad overview when a focused task or reference page is enough.
- Keep event names, levels, fields, redaction expectations, and troubleshooting in `docs/logging.md`; keep logging settings in `CONFIGURATION.md`, runtime boundaries in `ARCHITECTURE.md`, user-visible benefits in `FEATURES.md`, and rationale in `DECISIONS.md`.
- Keep bundled-tool discovery and app-visible usage guidance in `docs/tools.md`; keep registry schema, rewrite/environment contracts, workspace validation, and integration checklists in `docs/external-command-integrations.md`.

---

## Review Checklist

Before finishing doc changes, check:

- Does the section still contain the same substantive detail?
- Is the lead clearer than before?
- Did any bullet become too dense or try to carry too many ideas?
- Does any labeled bullet or sub-bullet still contain multiple sentence-level ideas that should become child bullets?
- Would a reader have to parse a 4-5 sentence block to find one fact that should be scannable?
- Was prose kept where sequencing or rationale matters?
- Are sibling sections more consistent than before?
- Do anchors and cross-links still resolve?
- If the doc has a full table of contents, does it include every reader-facing H2 section?
- Is detailed material in one canonical home, with only necessary context repeated elsewhere?
- Are Related Docs limited to the few pages this reader is most likely to need next?
- Does README's Documentation Map still list every maintained project Markdown document?
- For CHANGELOG entries, does the T2 short vs T2 long choice match the ≥5-sentence / multi-concept threshold?
- Does `python -m pytest tests/py/test_docs.py -q` still pass?
- Does `npm run lint:md` still report zero errors?

---

## Anti-Patterns

Avoid these:

- turning every paragraph into bullets without improving structure
- mixing user-facing behavior, implementation detail, and validation notes in one long bullet
- nesting bullets so deeply that the section is harder to scan than the original prose
- keeping paragraph-sized labeled bullets when the content is really a small list of parallel points
- moving contributor-only details into end-user docs
- adding implementation trivia to release notes
- regenerating test inventories, exact test totals, or an exhaustive source-file tree in reader-facing docs
- turning Related Docs into a mirror of every project document instead of a short next-step list
- mirroring a current-state contract across several docs and comparing their wording in tests
- creating a focused guide that copies another guide's procedures, tables, or implementation contract

---

## Decision Rule

If a proposed rewrite makes the structure cleaner but the meaning flatter, do not take it.

The standard is not “more bullets.” The standard is “same detail, easier to navigate.”
