# UI Capture Scenes — Reviewer Companion

Static reference for reviewing the output of `scripts/capture_ui_screenshots.sh`.
This file describes every scene the capture pack walks, what each scene is
supposed to demonstrate, and what cross-cutting patterns to look for per theme.

A machine-readable manifest (`{desktop,mobile}-manifest.json` with one entry per
rendered PNG) is written alongside the PNG pack at
`/tmp/darklab_shell-ui-capture/`; this doc is the human-authored counterpart and is
the source of truth for scene intent.

## Running the pack

- `npm run capture:ui-screenshots` — desktop + mobile, default theme, writes to
  `/tmp/darklab_shell-ui-capture/`.
- `scripts/capture_ui_screenshots.sh --ui desktop --theme all` — every theme,
  desktop only.
- `scripts/capture_ui_screenshots.sh --ui mobile --theme charcoal_amber` —
  single theme, mobile only.
- `scripts/capture_ui_screenshots.sh --out-dir /tmp/ui-review-2026-04-20` —
  override the output directory.

Capture tests are gated behind `RUN_CAPTURE=1` via the dedicated configs in
`config/playwright.capture.{desktop,mobile}.config.js`, so the pack never runs
as part of `npm run test:e2e`.

## Output layout

```text
/tmp/darklab_shell-ui-capture/
├── desktop-manifest.json
├── mobile-manifest.json
├── desktop/
│   └── <theme>/
│       └── NN-<slug>.png
└── mobile/
    └── <theme>/
        └── NN-<slug>.png
```

`<theme>` is `default` unless `--theme` was passed; `NN` is a zero-padded scene
order index (keeps directory listings lined up with the scene list below).

## Themes

When `--theme all` is passed, every theme in `app/conf/themes/` is rendered.
Currently 18 themes:

`apricot_sand`, `chalk`, `charcoal_amber`, `charcoal_lavender`,
`charcoal_steel`, `cobalt_obsidian`, `darklab_obsidian`, `ember_obsidian`,
`emerald_obsidian`, `lavender_fog`, `mint_glass`, `moss_stone`,
`newsprint`, `olive_grove`, `overcast`, `rose_quartz`, `sage`, `slate_dusk`.

## Cross-cutting patterns to check per theme

These rules apply to every theme and are exercised across many scenes. Flag any
scene where one of these appears to have drifted.

- **Semantic color contract** (see `THEME.md § Semantic Color Contract`) —
  `--amber` / `--red` / `--green` / `--muted` must stay visually distinct.
  Scenes that surface all four signal colors in one frame: any scene with a
  running tab (amber status dot + green exit-ok + muted chrome), any history
  drawer/sheet scene (starred amber stripe + exit-ok green), the HUD/rail in
  the desktop welcome scene.
- **Button primitive family** — every button reads as `.btn` + role + tone, or
  one of `.nav-item` / `.close-btn` / `.toggle-btn` / `.kb-key`. Exceptions are
  documented in `tests/js/fixtures/button_primitive_allowlist.json`. Flag any
  button that looks like a one-off shape (weird padding, stray border radius,
  unique hover state, etc.).
- **Confirmation dialog contract** — every confirm modal stacks actions
  vertically at mobile viewport widths or when the action count is ≥ 3,
  otherwise lays them out horizontally. Cancel-role action is the default
  focus. See `kill-confirmation-modal`,
  `confirm-modal-three-actions-stacked` (desktop only),
  `history-drawer-delete-*-confirmation`, `session-token-clear-confirmation`,
  and the mobile `history-sheet-delete-*-confirmation` scenes.
- **Disclosure affordance rules** — `▸ / ▾` for accordions, `▾` for dropdown
  menus, `✕` for dismissal. Glyph follows behavior, not visual hierarchy.
  See the rail section headers (desktop `rail-*` scenes), the save menu
  (`save-menu-open`), the mobile recents filter disclosure
  (`history-sheet-search-filters-expanded`).
- **Typography & rhythm** — prompt line, output line, header row, and sheet
  rows should sit on a consistent line-height grid across themes.

## Desktop pack (31 scenes)

Order matches the scene array in `tests/js/e2e/ui-capture.desktop.capture.js`.

| # | Slug | Route | What it shows | What to look for |
|---|------|-------|---------------|------------------|
| 01 | `main-welcome-settled` | `/` | Fresh home after the welcome animation finishes playing. | Rail + tab bar + HUD visual balance; welcome settle state; prompt cursor position. |
| 02 | `main-autocomplete` | `/` | Autocomplete dropdown open after `curl -`. | Flag/option hints legibility; dropdown card background vs terminal background; selected-row background contrast. |
| 03 | `main-reverse-history-search` | `/` | Ctrl+R reverse search active with `host` typed. | Search-match highlight tint stays visible on the active row; hist-search dropdown placement (above vs below prompt); no overflow against viewport edges. |
| 04 | `main-multiple-tabs` | `/` | Three tabs open (`hostname` output, `date` output, empty new tab). | Active-tab border treatment (green top border); inactive-tab `color: var(--muted)`; tab-grip six-dot handle visible on every tab; close-glyph opacity 0 on inactive tabs. |
| 05 | `main-running-active-tab` | `/` | Active tab running a long command; non-active tab has finished output. | `STATUS` pill reads `RUNNING - Xs`; active-tab top border turns amber; run timer readable. |
| 06 | `main-running-inactive-tab` | `/` | First tab running, second tab active with finished output. | Amber status dot on the inactive running tab; top-border on that tab stays green (running but not active); focused tab reads as active, not hot. |
| 07 | `kill-confirmation-modal` | `/` | Two-action (cancel + destructive) confirm modal while running a long command. | Backdrop dims the shell; `Cancel` is default focus; `Kill` reads as destructive; actions laid out horizontally at desktop width. |
| 08 | `confirm-modal-three-actions-stacked` | `/` | Three-action stacked confirm (primary / destructive / cancel). | `.modal-actions-stacked` class active even at 1024-wide; cancel row visible; role-typed buttons each read as their role (primary filled, destructive red, cancel muted). |
| 09 | `save-menu-open` | `/` | HUD save dropdown open. | Option list (`save as .txt`, `save as .html`, `save as .pdf`) readable; dropdown attached visually to the `save ▾` trigger; outside-click dismissal not in frame. |
| 10 | `rail-open-both-expanded` | `/` | Rail visible with both Recents + Workflows expanded. | Starred-first ordering in Recents with amber left-edge stripe on starred rows; Workflows section chevron points down (▾); section counts present. |
| 11 | `rail-open-recents-only` | `/` | Rail visible, Recents expanded, Workflows collapsed. | Workflows chevron points right (▸); Recents section still shows rows and section counts. |
| 12 | `rail-open-both-collapsed` | `/` | Rail visible, both sections collapsed. | Both chevrons point right; section headers stack at top of the split-area (not one-at-top / one-at-bottom); section counts still legible. |
| 13 | `rail-closed` | `/` | Rail fully collapsed to the skinny icon rail. | Collapsed nav glyphs at full-strength text color (not muted); `«` / `»` collapse toggle visible; nav glyphs sized consistently. |
| 14 | `search-open-active-match` | `/` | Transcript search bar open with `localhost` matching three occurrences. | `<mark class="search-hl">` on each match; active-match tint stronger than inactive tint; counter reads `1 of 3` or equivalent. |
| 15 | `workflow-modal-example` | `/` | First workflow modal open from the rail. | Step-row two-row grid; per-step ▶ run button present; step body readable; modal card max-width. |
| 16 | `history-drawer` | `/` | History drawer open with one hydrated run. | Alternating row bands (even-row 6% text-on-surface tint); starred rows with amber left-edge stripe; action buttons (restore / permalink / star / delete) revealed on hover (hover state may or may not be captured). |
| 17 | `history-drawer-snapshot-row` | `/` | History drawer showing a saved snapshot row. | Snapshot kind badge reads `SNAPSHOT`; row exposes `open`, `copy link`, and `delete`; snapshot row does not show the run-only star/restore affordances. |
| 18 | `history-drawer-search-chip` | `/` | History drawer with `host` search applied and filter chip visible. | Active filter chip shows the current query; chip dismissal glyph (`✕`) visible; filtered row count reflects the query. |
| 19 | `history-drawer-delete-all-confirmation` | `/` | History drawer + delete-all confirm modal stacked. | Confirm card sits above the drawer with backdrop dim; three buttons (`Cancel` / `Delete non-favorites` / `Delete all`) all fit on one row at 1024-wide. |
| 20 | `history-drawer-delete-confirmation` | `/` | History drawer + single-row delete confirm. | Confirm modal with 2-action horizontal layout; row being deleted still visible behind backdrop. |
| 21 | `options-modal` | `/` | Options modal open from the rail. | Themed native form controls (`<select>`, `<input type="checkbox">`); `.form-*` class group rendering; modal close button in the top-right corner. |
| 22 | `session-token-clear-confirmation` | `/` | Options modal with the session-token clear confirm open. | Confirm copy warns that the token is not recoverable from the app; `Copy token` keeps the dialog open; `Clear token` reads as destructive; `Cancel` is default focus. |
| 23 | `theme-modal` | `/` | Theme picker open from the rail. | Theme cards each render a mini terminal preview (with traffic-light dots); selected card has a visible selection ring; grid alignment. |
| 24 | `faq-modal` | `/` | FAQ modal open from the rail. | Accordion `▸ / ▾` glyphs on each FAQ item; first item expanded by default; clickable command chips render as primitives. |
| 25 | `shortcuts-overlay` | `/` | Keyboard shortcuts overlay (the `?` surface). | Transparent overlay with grouped sections (`Terminal:`, `Tabs:`, `UI:`); section titles styled in blue; key chords left-aligned, descriptions right-aligned; grid alignment holds across themes. |
| 26 | `line-numbers-enabled` | `/` | Transcript with line-number prefix on. | Prefix width stable; content left-edge aligned to prefix right edge; `body.ln-on` rule visible. |
| 27 | `timestamps-enabled` | `/` | Transcript with elapsed-timestamp prefix on. | Timestamp prefix rendering; four ping lines with their timings; prefix visually distinct from content. |
| 28 | `line-numbers-and-timestamps-enabled` | `/` | Both prefixes stacked. | Combined prefix width accommodates both; content wraps correctly inside the remaining width (regression target for the mobile-overflow fix). |
| 29 | `snapshot-page` | `/share/:id` | Permalink landing page from `/share`. | Expiry line promoted above the run-meta row; share-unredacted-vs-redacted treatment visible; page-level save menu present. |
| 30 | `permalink-page` | `/history/:id` | Permalink landing page from `/history`. | Prompt prefix on echoed command lines renders the configured `prompt_prefix` (not a bare `$`); header metadata alignment; green border removed from the page title. |
| 31 | `diag-page` | `/diag` | Operator `/diag` page. | Activity and Outcomes cards are split; generated-at freshness line under the header; config `true` values not green-by-default; diag back-button present only at mobile/touch breakpoints (it should not appear here). |

## Mobile pack (26 scenes)

Order matches the scene array in `tests/js/e2e/ui-capture.mobile.capture.js`.
Mobile viewport: iPhone 15 Pro Max–class (430 × 932 @ 3x, final images 1290 ×
2796).

| # | Slug | Route | What it shows | What to look for |
|---|------|-------|---------------|------------------|
| 01 | `main-welcome-settled` | `/` | Fresh mobile home after welcome settle. | Header + tab bar + composer + hamburger button visual balance; composer bottom placement; status teleport into header. |
| 02 | `main-multiple-tabs` | `/` | Three tabs open on mobile (`hostname`, `date`, empty). | Active-tab top-border color; tab strip scroll-to-active keeping the active tab visible; tab-grip visibility on mobile. |
| 03 | `main-running-active-tab` | `/` | Active tab running on mobile. | Header STATUS pill reads `RUNNING - Xs`; mobile kill button visible; composer remains usable during run. |
| 04 | `main-running-inactive-tab` | `/` | First tab running, second tab active. | Amber status dot on the inactive running tab; header shows active-tab state only. |
| 05 | `main-running-indicator-chip` | `/` | Trailing chip `#mobile-running-chip` with count `2` (two inactive running tabs). | Chip visible in the terminal-bar trailing slot; `.mobile-running-count` text reads `2`; paired edge-glow overlays synced to the running tabs; active tab (third) correctly excluded from the count. |
| 06 | `kill-confirmation-modal` | `/` | Mobile kill confirm. | Stacked actions (mobile viewport is ≤ 480px → `.modal-actions-stacked`); cancel row has default focus; modal sits above the scrim without clipping. |
| 07 | `save-menu-open` | `/` | Per-tab save dropdown open on mobile. | Dropdown positions inside the viewport (no clipping at the trailing edge); option labels legible; attached to the `save ▾` trigger. |
| 08 | `search-open-active-match` | `/` | Mobile search bar open with `localhost` matches. | Counter visible (`1 of 3` or similar); two-row reflow (input row + controls row); match highlight stays legible on the active match. |
| 09 | `line-numbers-enabled` | `/` | Mobile transcript with line-number prefix. | Prefix renders inside the mobile viewport; content wraps at the correct visible edge (not shifted off-screen). |
| 10 | `timestamps-enabled` | `/` | Mobile transcript with elapsed-timestamp prefix. | Same wrap-inside-viewport assertion as above; timestamp column readable on narrow widths. |
| 11 | `line-numbers-and-timestamps-enabled` | `/` | Mobile with both prefixes stacked. | Combined prefix width does not push content off-screen; content wraps correctly. |
| 12 | `history-sheet` | `/` | Mobile recents bottom-sheet open. | Alternating row bands (even-row 6% tint); starred rows with amber left-edge stripe; relative time cell (`Nm ago` / `Nh ago` / `Nd ago`) with absolute time in `title`; grab handle centered at the top. |
| 13 | `history-sheet-snapshot-row` | `/` | Mobile recents sheet showing a saved snapshot row. | Snapshot kind badge reads `SNAPSHOT`; row exposes `open`, `copy link`, and `delete`; row height and action wrapping remain comfortable at 430px width. |
| 14 | `history-sheet-search-filters-expanded` | `/` | Recents sheet with search `host` + filters expanded. | Advanced filter panel visible; `▾` glyph flipped; filter-root input populated; sheet body scrollable. |
| 15 | `history-sheet-search-filters-collapsed-chip` | `/` | Recents sheet with filters collapsed and active-filter chip. | Chip shows the active filter; filters disclosure collapsed back; sheet height stable. |
| 16 | `history-sheet-delete-all-confirmation` | `/` | Recents-sheet delete-all confirm. | Three buttons (`Cancel` / `Delete non-favorites` / `Delete all`) fit on one row at 393–430px widths (regression target for the `.modal-actions-wrap` tightening). |
| 17 | `history-sheet-delete-confirmation` | `/` | Recents-sheet single-row delete confirm. | Two-action confirm stacked on mobile; row being deleted still rendered behind the scrim. |
| 18 | `menu-modal` | `/` | Mobile hamburger bottom-sheet. | Session group (search / line numbers / timestamps submenu); overlay entries (history, workflows, options, theme, FAQ, diag); grab handle at the top; close glyph in the header; `.sheet-close` styling matches desktop modal-close treatment. |
| 19 | `workflows-modal` | `/` | Mobile workflows modal. | Step-row layout reflows for narrow viewport; per-step ▶ run button reachable; modal body scrollable. |
| 20 | `options-modal` | `/` | Mobile options modal. | Form controls render natively in the mobile sheet; modal close reachable with thumb; session-token button visibility follows token state. |
| 21 | `session-token-clear-confirmation` | `/` | Mobile options modal with the session-token clear confirm open. | Confirm copy warns that the token is not recoverable from the app; actions stack cleanly; `Copy token`, `Cancel`, and destructive `Clear token` remain readable. |
| 22 | `theme-modal` | `/` | Mobile theme picker. | Theme cards stack or grid in the narrow viewport; selected card ring visible; traffic-light dots in each preview. |
| 23 | `faq-modal` | `/` | Mobile FAQ modal. | Accordion glyphs; modal body scrollable; close button reachable. |
| 24 | `snapshot-page` | `/share/:id` | Mobile snapshot landing page. | Header metadata stacks vertically; save menu reachable; prompt prefix matches the shell's. |
| 25 | `permalink-page` | `/history/:id` | Mobile permalink landing page. | Same as snapshot page plus the run permalink semantics. |
| 26 | `diag-page` | `/diag` | Mobile diag page. | `.diag-topbar` sibling wrapper keeps the sticky header legible on iOS Safari (the unscoped `mobile.css:84` rule that used to collapse the header is avoided by this structure); back-button visible at mobile/touch breakpoints. |

## Reporting regressions

When a scene looks wrong:

1. Note the UI (`desktop` / `mobile`), the theme, and the scene slug.
2. Link the specific PNG from `/tmp/darklab_shell-ui-capture/<ui>/<theme>/NN-<slug>.png`.
3. Cross-reference the `What to look for` column above so the regression can be
   tied back to a documented pattern or contract.
4. If the regression is cross-cutting (e.g. affects every theme), call that out
   explicitly — it likely points at a base-layer CSS rule or a shared
   primitive.
