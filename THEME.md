# Theme System

This document is the full reference for the shell theme system. It explains how theme files are loaded, how values flow into the browser, and what every configurable key does.

---

## Table of Contents

- [Overview](#overview)
- [Semantic Color Contract](#semantic-color-contract)
- [Theme Resolution Order](#theme-resolution-order)
- [Baked-In Fallback Palette](#baked-in-fallback-palette)
- [How the Code Works](#how-the-code-works)
- [File Roles](#file-roles)
- [Runtime Theme Selector](#runtime-theme-selector)
- [Editing Rules](#editing-rules)
- [Practical Notes](#practical-notes)
- [Keeping example files in sync](#keeping-example-files-in-sync)
- [Theme Key Reference](#theme-key-reference)
- [Related Docs](#related-docs)

---

## Overview

The theme system externalizes all visual palette values into named YAML files that the runtime loads, resolves against built-in fallback defaults, and injects into every presentation surface. The live shell, permalink pages, the runtime theme selector, exported HTML, and PDF export all read from the same resolved semantic tokens rather than each maintaining a separate palette. Themes are selectable at runtime through the preview modal or the `theme` terminal command without requiring code changes or a container rebuild.

---

## Semantic Color Contract

Every theme provides four semantic colors with fixed meanings. Themes may choose any visual tone for each color, but the four must stay visually distinct within a single theme so each meaning remains recognizable.

| Semantic | Token | Meaning |
|----------|-------|---------|
| yellow | `--amber` | caution / reversible destructive / expiring / in-progress (running, live, pending) |
| red | `--red` | destructive / kill / error / irreversible |
| green | `--green` | completed success / enabled / current-focus (the "done/selected" tier) |
| dim | `--muted` | neutral metadata — labels, timestamps, non-critical values |

### Rules

- **Binary, not graded.** One color, one meaning. If a surface needs a softer treatment (e.g. dimmed expiry text) it uses the `dim` token plus the semantic color on the label only, not a second intensity tier of the same color.
- **All four must stay distinct per theme.** A theme that collapses caution into danger (yellow ≈ red) defeats the purpose of the contract. Theme authors must verify red, yellow, green, and dim are visually separable inside each theme, not just in aggregate across the palette family.
- **In-progress belongs to yellow, not green.** A "running" task is yellow; a "completed success" task is green. This keeps the two states visually distinct even when both are "active" in the loose sense. Use yellow for running, live, pending, and the HUD `RUNNING` pill; use green only for completed success, enabled switches, and current-focus indicators.
- **Use existing theme tokens.** Do not introduce surface-local amber / red / green variants. If a surface needs tuning, add a new `--theme-*` chrome token derived from the base semantic token via `color-mix()` in the theme file — never hardcode a one-off color.

### Documented exceptions

These uses of yellow do not match the strict semantic meaning above, but are retained because they match widely established cross-product conventions. They should not be cited as precedent for introducing further exceptions.

- **Starred items.** A yellow star icon on favorited / starred entries (history rows, chips, sheet items) — matches the universal star-is-yellow convention (GitHub, Gmail, etc.).
- **Search-hit highlights.** `mark.search-hl` tints matches yellow — matches browser and IDE find-in-page convention.

---

## Theme Resolution Order

The runtime theme choice is resolved in this order:

1. `localStorage.theme`
2. `default_theme` from `app/conf/config.yaml`
3. the baked-in dark fallback palette in `app/config.py`

That means the browser always prefers the user's last selected theme, then the instance default filename, and only falls back to the built-in dark values if the saved or configured theme cannot be loaded. The selector does not promote the first registry theme as a hidden third fallback, and an empty registry simply leaves the preview modal empty while the app uses the baked-in fallback colors. Legacy `pref_theme_name` / `pref_theme` cookies are still read for backwards compatibility, but `localStorage.theme` is the canonical value.

---

## Baked-In Fallback Palette

The theme framework has two built-in, hard-coded palettes: a dark palette and a light palette. Both live in `app/config.py` under `_THEME_DEFAULTS["dark"]` and `_THEME_DEFAULTS["light"]`. These are not selectable theme files — they are the compile-time baseline that the loader falls back to for any key a custom theme file does not specify.

Every key listed in the [Theme Key Reference](#theme-key-reference) section below has a baked-in value in both palettes. If you need the exact source of truth, inspect `_THEME_DEFAULTS` in [app/config.py](app/config.py).

### Which built-in palette fills in missing keys

Each theme file in `app/conf/themes/` declares its intended palette family with a `color_scheme` field:

```yaml
color_scheme: dark   # or: light
```

When `load_theme(name)` merges a custom theme file, it uses `color_scheme` to pick the right built-in as the base:

- `color_scheme: dark` → missing keys are filled from `_THEME_DEFAULTS["dark"]`
- `color_scheme: light` → missing keys are filled from `_THEME_DEFAULTS["light"]`
- absent → falls back to `_THEME_DEFAULTS["dark"]`

This means a light-family custom theme only needs to specify the values it actually changes. All unspecified keys automatically inherit the built-in light defaults rather than the dark ones. The two built-in palettes were designed as complementary starting points: all keys have sensible values in both, and any theme file is free to override as many or as few as it needs.

### Generated example files

The checked-in files `app/conf/theme_dark.yaml.example` and `app/conf/theme_light.yaml.example` are generated directly from `_THEME_DEFAULTS` by `scripts/generate_theme_examples.py`. They serve as full annotated references that show every supported key and its built-in default value. The dark example is intentionally aligned with the active `app/conf/themes/darklab_obsidian.yaml` theme file. See [Keeping example files in sync](#keeping-example-files-in-sync) for when to regenerate them.

---

## How the Code Works

### 1. Load and merge

`load_theme(name)` in `app/config.py` loads the YAML file from `app/conf/themes/<name>.yaml`, reads the `color_scheme` field (`dark` or `light`, defaulting to `dark`), merges the file values on top of the matching `_THEME_DEFAULTS` palette, and then applies an optional sibling `app/conf/themes/<name>.local.yaml` overlay if one exists. It accepts either the filename stem or the full filename, so `darklab_obsidian.yaml` and `darklab_obsidian` both resolve to the same registry entry. Any key absent from the file (and from the local overlay) retains the built-in default for the chosen palette family.

### 2. Export as CSS vars

`theme_css_vars(theme)` walks `_THEME_CSS_ORDER` and converts each accepted key into a CSS custom property named `--theme-<key>`. The ordering is stable so the injected CSS is deterministic.

### 3. Inject into the templates

`app.py` and `permalinks.py` pass runtime CSS vars built from the built-in default palettes into the templates. `theme_vars_style.html` turns the selected theme's variables into a `<style>` block containing `:root { ... }` declarations. That means the browser never needs to guess at the current palette.

### 4. Expose the values to JS

`theme_vars_script.html` serializes the current resolved values into `window.ThemeCssVars` and the full registry into `window.ThemeRegistry`. Browser-side helpers, especially the HTML export builder, runtime theme selector, and `theme` terminal command, can then read the exact runtime theme without duplicating a hardcoded palette.

### 5. Consume from CSS and export helpers

`styles.css` uses the shared vars for the live shell, tabs, history drawer, FAQ, modals, mobile UI, welcome art, and toast surfaces. `app.js` applies the selected theme live by swapping the root CSS variables on `:root`. `export_html.js` uses the same vars when building downloadable HTML snapshots so the saved file matches the active theme instead of drifting over time, and `export_pdf.js` resolves the same semantic tokens into RGB values for jsPDF so PDF export follows the active theme as closely as the PDF renderer allows.

---

## File Roles

| File | Role |
|------|------|
| `app/conf/theme_dark.yaml.example` | Generated dark theme reference file built from `_THEME_DEFAULTS["dark"]` |
| `app/conf/theme_light.yaml.example` | Generated light theme reference file built from `_THEME_DEFAULTS["light"]` |
| `app/conf/themes/` | Additional named theme variants loaded into the runtime selector; sibling `.local.yaml` overlays merge into the matching base theme but are not listed separately |
| `app/config.py` | Loads, validates, and resolves theme values |
| `scripts/generate_theme_examples.py` | Regenerates the checked-in dark/light example files from `_THEME_DEFAULTS` |
| `app/app.py` | Exposes `/themes` and injects the current theme into the main shell |
| `app/templates/theme_vars_style.html` | Injects resolved CSS variables into the page |
| `app/templates/theme_vars_script.html` | Exposes resolved theme values and the theme registry to browser JS |
| `app/static/css/styles.css` | Consumes the theme vars for live UI styling |
| `app/static/js/app.js` | Applies the selected theme on the fly from the theme selector modal preview cards |
| `app/static/js/export_html.js` | Builds downloadable HTML snapshots and the shared browser export header model from the resolved vars |
| `app/static/js/export_pdf.js` | Resolves the active theme tokens for jsPDF and renders PDF export against the same semantic palette |

---

## Runtime Theme Selector

The theme preview grid is driven by the runtime theme registry. Clicking a preview card immediately applies that theme and persists the selection to `localStorage`. Each preview card renders a compact schematic of the current desktop shell — rail sections, tabbar with an active tab, terminal panel, HUD bar, and a small modal surface — so theme contrast is judged against the same surface relationships used by the live app. On desktop, the selector opens as a right-side drawer so the shell remains visible behind it while comparing themes. On mobile, it remains a full-screen chooser with a two-column preview layout on wider phones.

The built-in `theme` button is a shortcut to the selector. The preview grid is the source of truth for named variants — registry entries without an explicit `label:` fall back to a humanized filename stem, and entries without a `group:` appear under "Other".

The current built-in selector ships 18 named themes:

- Dark Neon: `darklab_obsidian`, `emerald_obsidian`, `ember_obsidian`, `cobalt_obsidian`
- Dark Neutral: `charcoal_amber`, `charcoal_steel`, `charcoal_lavender`
- Dark Mid-tone: `slate_dusk`, `moss_stone`
- Warm Light: `apricot_sand`, `olive_grove`, `rose_quartz`
- Cool Light: `lavender_fog`, `mint_glass`
- Neutral Light: `newsprint`, `chalk`
- Neutral Mid-tone: `overcast`
- Neutral Green Mid-tone: `sage`

---

## Editing Rules

### Authoring a theme

- Copy `theme_dark.yaml.example` or `theme_light.yaml.example` into `app/conf/themes/<filename>.yaml` to expose it in the runtime selector. The loader reads the canonical files plus every YAML file in `app/conf/themes/`.
- For a private overlay on an existing base theme, create `app/conf/themes/<filename>.local.yaml` next to it; the loader merges the overlay after the checked-in base file.
- Unknown keys are ignored — only keys present in `_THEME_DEFAULTS` (`app/config.py`) are accepted.
- Values may be any valid CSS color, length, gradient, or shadow string, depending on the key.
- To derive one value from another, use CSS custom-property references such as `var(--green)` or `color-mix(in srgb, var(--surface) 88%, #000)`. The loader preserves those strings exactly; the browser resolves them after injection.

For regenerating the `.yaml.example` reference files, see [Keeping example files in sync](#keeping-example-files-in-sync).

### Operational behavior

- If a theme YAML file is malformed, the loader falls back to the built-in defaults instead of crashing. The runtime selector keeps working; fix the file before treating it as usable.
- Restart the container after changing any loaded theme file under `app/conf/themes/` or after changing `config.yaml`. No rebuild is required.

### Metadata fields

Theme YAMLs may include four optional metadata fields that control how the theme appears in the selector:

| Field | Effect | Fallback when absent |
|-------|--------|----------------------|
| `label` | Visible card name in the theme selector | Humanized filename stem |
| `group` | Section header in the theme modal | `Other` |
| `sort` | Ordering between cards and sections | Entry sorted after all explicitly sorted themes |
| `color_scheme` | Set to `dark` or `light` to control which built-in fallback family supplies missing keys (see [Baked-In Fallback Palette](#baked-in-fallback-palette)) | Dark default family |

There is no filename-based or palette-based group inference — `group` must be set explicitly if you want the theme to appear under a specific section.

### CSS variable exposure

- Base palette keys are exposed as plain CSS variables: `--bg`, `--surface`, `--text`, `--green`, `--blue`, and so on.
- Component chrome keys are exposed as `--theme-*` variables, for example `--theme-panel-bg`, `--theme-tab-active-text`, `--theme-toast-border`.

---

## Practical Notes

- Theme YAML files are explicit and self-contained so operators can tune the shell appearance without touching code.
- Most values are safe to tweak live as long as they remain valid CSS values.
- The theme layer is shared by the live app, permalink pages, and export HTML, so a change in these files can affect all three surfaces.
- If you are trying to restyle something and cannot find a key in this appendix, it is probably still hardcoded elsewhere in CSS and should be moved to the theme system next.

---

## Keeping example files in sync

`app/conf/theme_dark.yaml.example` and `app/conf/theme_light.yaml.example` are generated files. They must stay in sync with the `_THEME_DEFAULTS` dictionaries in `app/config.py`.

A pytest regression (`TestThemeRegistry.test_theme_example_files_match_generated_defaults`) compares the checked-in files against the output of `scripts/generate_theme_examples.py` on every test run. If the test fails, it means the built-in defaults changed but the example files were not regenerated. Fix it by running:

```bash
./.venv/bin/python scripts/generate_theme_examples.py
```

Then commit both updated `.yaml.example` files alongside the `app/config.py` change that triggered the drift.

**When you need to regenerate:**

- You added, removed, or renamed a key in `_THEME_DEFAULTS` in `app/config.py`
- You changed a default value in `_THEME_DEFAULTS`
- The test `test_theme_example_files_match_generated_defaults` fails

**When you do not need to regenerate:**

- You created or edited a theme file under `app/conf/themes/` — those are independent of the example files
- You changed something in `scripts/generate_theme_examples.py` itself (though in that case you should still run it to confirm the output)

---

## Theme Key Reference

The tables below list every supported theme key from `_THEME_DEFAULTS`. Each row includes the dark and light default values for reference — these are the values used when a key is absent from a theme file, not selectable modes. The runtime selector always applies a single fully resolved theme at a time.

### Base Palette

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `bg` | `#000000` | `#b8c4d0` | Page background behind the terminal shell |
| `surface` | `#141414` | `#eef2f6` | Core panel, modal, and dropdown surface color |
| `border` | `#2a2a2a` | `rgba(0,0,0,0.15)` | Subtle separators and low-emphasis borders |
| `border_bright` | `#3c3c3c` | `rgba(0,0,0,0.28)` | Stronger borders, focus outlines, and modal chrome |
| `border_soft` | `rgba(255, 255, 255, 0.08)` | `rgba(0,0,0,0.12)` | Soft dividers where a full border would read too heavy |
| `text` | `#e0e0e0` | `#101820` | Primary body text |
| `muted` | `#9a9a9a` | `#5a6878` | Secondary labels, hints, and timestamps |
| `green` | `#39ff14` | `#2a5d18` | Prompt, success states, and primary active accent |
| `green_dim` | `#1a7a08` | `#355f24` | Dimmed green accent for borders and low-key highlights |
| `green_glow` | `rgba(57,255,20,0.12)` | `rgba(42,93,24,0.08)` | Glow, focus rings, and accent tints |
| `amber` | `#ffb800` | `#9a4200` | Running state, warnings, and starred items |
| `red` | `#ff3c3c` | `#cc2200` | Fail states, kill actions, and destructive highlights |
| `blue` | `#6ab0f5` | `#1a5aaa` | Prompt prefix, welcome labels, and command badges |

### Typography

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `terminal_font_size` | `14px` | `14px` | Output font size inside the terminal pane |
| `terminal_line_height` | `1.65` | `1.65` | Line spacing for terminal output |
| `prompt_line_text` | `#e8e8e8` | `#1c201a` | Text color for the live prompt line above the hidden input |

### Terminal Panes, Panels, and Shell Chrome

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `panel_bg` | `#141414` | `#d4e0ec` | Main panel background |
| `panel_border` | `#3c3c3c` | `rgba(0,0,0,0.28)` | Panel borders |
| `panel_shadow` | `rgba(170,170,170,0.12)` | `rgba(0,0,0,0.22)` | Panel drop shadow |
| `terminal_bar_bg` | `#000000` | `#b8c4d0` | Top terminal bar background |
| `chrome_bg` | `#0c0c0c` | `#b8c4d0` | Shared shell chrome background for the rail, HUD, History drawer, Status Monitor, mobile recents, and mobile menu |
| `chrome_header_bg` | `#0c0c0c` | `#b8c4d0` | Header bands inside shell chrome surfaces |
| `chrome_row_bg` | `#0c0c0c` | `#b8c4d0` | Rows inside shell chrome surfaces |
| `chrome_row_hover_bg` | `rgba(57,255,20,0.12)` | `rgba(26,90,170,0.06)` | Hover/focus rows inside shell chrome surfaces |
| `chrome_control_bg` | `color-mix(in srgb, var(--surface) 92%, transparent)` | `color-mix(in srgb, var(--surface) 92%, transparent)` | Inputs and compact controls inside shell chrome surfaces |
| `chrome_control_border` | `var(--border-bright)` | `var(--border-bright)` | Inputs and compact control borders inside shell chrome surfaces |
| `chrome_divider_color` | `#2a2a2a` | `rgba(0,0,0,0.15)` | Divider lines inside shell chrome surfaces |
| `chrome_shadow` | `rgba(0,0,0,0.6)` | `rgba(0,0,0,0.6)` | Shared shadow for chrome drawers and sheets |
| `scrollbar_track` | `color-mix(in srgb, var(--surface) 72%, transparent)` | `color-mix(in srgb, var(--surface) 72%, transparent)` | Shared terminal/permalink scrollbar track |
| `scrollbar_thumb` | `color-mix(in srgb, var(--muted) 44%, var(--border-bright))` | `color-mix(in srgb, var(--muted) 44%, var(--border-bright))` | Shared terminal/permalink scrollbar thumb |
| `scrollbar_thumb_hover` | `color-mix(in srgb, var(--text) 38%, var(--border-bright))` | `color-mix(in srgb, var(--text) 38%, var(--border-bright))` | Shared terminal/permalink scrollbar thumb hover |

### Toolbar Buttons and Chips

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `toolbar_button_bg` | `transparent` | `#c8d4e0` | Chrome button (rail, HUD, toolbar) backgrounds |
| `toolbar_button_border` | `#3c3c3c` | `#8898b0` | Chrome button (rail, HUD, toolbar) borders |
| `toolbar_button_text` | `#9a9a9a` | `#202838` | Chrome button (rail, HUD, toolbar) text |
| `toolbar_button_hover_bg` | `transparent` | `#b8c8d8` | Hover background for chrome buttons |
| `toolbar_button_hover_border` | `#1a7a08` | `#6880a0` | Hover border for chrome buttons |
| `toolbar_button_hover_text` | `#39ff14` | `#101820` | Hover text for chrome buttons |
| `toolbar_button_active_bg` | `rgba(57,255,20,0.06)` | `#a0b4c8` | Active chrome button background |
| `toolbar_button_active_border` | `#1a7a08` | `#6880a0` | Active chrome button border |
| `toolbar_button_active_text` | `#39ff14` | `#101820` | Active chrome button text |
| `button_secondary_bg` | `color-mix(in srgb, var(--surface) 66%, transparent)` | `color-mix(in srgb, var(--surface) 66%, transparent)` | Shared secondary button background |
| `button_secondary_border` | `color-mix(in srgb, var(--border-bright) 88%, transparent)` | `color-mix(in srgb, var(--border-bright) 88%, transparent)` | Shared secondary button border |
| `button_secondary_text` | `color-mix(in srgb, var(--muted) 86%, var(--text))` | `color-mix(in srgb, var(--muted) 86%, var(--text))` | Shared secondary button text |
| `button_secondary_hover_bg` | `color-mix(in srgb, var(--_tone) 7%, transparent)` | `color-mix(in srgb, var(--_tone) 7%, transparent)` | Shared secondary button hover wash; resolves against the active button tone |
| `button_secondary_hover_border` | `color-mix(in srgb, var(--_tone-dim) 72%, var(--border-bright))` | `color-mix(in srgb, var(--_tone-dim) 72%, var(--border-bright))` | Shared secondary button hover border; resolves against the active button tone |
| `button_ghost_border` | `color-mix(in srgb, var(--border-bright) 58%, transparent)` | `color-mix(in srgb, var(--border-bright) 58%, transparent)` | Shared ghost button border |
| `button_ghost_text` | `color-mix(in srgb, var(--muted) 86%, var(--text))` | `color-mix(in srgb, var(--muted) 86%, var(--text))` | Shared ghost button text |
| `button_ghost_hover_bg` | `color-mix(in srgb, var(--_tone) 10%, transparent)` | `color-mix(in srgb, var(--_tone) 10%, transparent)` | Shared ghost button hover wash; resolves against the active button tone |
| `button_ghost_hover_border` | `color-mix(in srgb, var(--_tone-dim) 62%, var(--border-bright))` | `color-mix(in srgb, var(--_tone-dim) 62%, var(--border-bright))` | Shared ghost button hover border; resolves against the active button tone |
| `button_destructive_bg` | `color-mix(in srgb, var(--_tone) 8%, transparent)` | `color-mix(in srgb, var(--_tone) 8%, transparent)` | Shared destructive button background; resolves against the active destructive tone |
| `button_destructive_text` | `color-mix(in srgb, var(--muted) 86%, var(--text))` | `color-mix(in srgb, var(--muted) 86%, var(--text))` | Shared destructive button text |
| `button_destructive_hover_bg` | `color-mix(in srgb, var(--_tone) 16%, transparent)` | `color-mix(in srgb, var(--_tone) 16%, transparent)` | Shared destructive button hover background; resolves against the active destructive tone |

### Tabs and Tab Controls

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `tab_text` | `#9a9a9a` | `#5a6878` | Inactive tab text |
| `tab_hover_text` | `#e0e0e0` | `#101820` | Hovered tab text |
| `tab_active_bg` | `rgba(57,255,20,0.04)` | `#c0cedd` | Active tab background |
| `tab_close_bg` | `rgba(255,255,255,0.02)` | `rgba(255,255,255,0.02)` | Close-button background inside a tab |
| `tab_close_border` | `rgba(255,255,255,0.06)` | `rgba(255,255,255,0.06)` | Close-button border inside a tab |
| `tab_close_hover_bg` | `color-mix(in srgb, var(--green-dim) 18%, transparent)` | `color-mix(in srgb, var(--red) 18%, transparent)` | Close-button hover background |
| `tab_close_hover_border` | `color-mix(in srgb, var(--green-dim) 30%, transparent)` | `color-mix(in srgb, var(--red) 30%, transparent)` | Close-button hover border |
| `tab_close_hover_text` | `inherit` | `inherit` | Close-button hover text color |
| `tab_touch_drag_text_shadow` | `0 0 10px color-mix(in srgb, var(--green) 14%, transparent)` | `0 0 10px rgba(42,93,24,0.08)` | Drag feedback on touch devices |
| `tab_drop_shadow` | `0 0 10px color-mix(in srgb, var(--green) 45%, transparent)` | `0 0 10px rgba(42,93,24,0.18)` | Drag/drop emphasis for reordered tabs |

### History and Restore Overlays

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `history_load_overlay_bg` | `rgba(0,0,0,0.76)` | `rgba(0,0,0,0.76)` | Overlay shown while restoring a history entry |

### Modals, Dropdowns, and Inline Surfaces

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `modal_bg` | `#141414` | `#e8eef6` | Shared background for standard modal surfaces and the Theme selector |
| `dropdown_bg` | `color-mix(in srgb, var(--surface) 96%, transparent)` | `#d4e0ec` | Shared dropdown background for autocomplete, save menus, and app-native select menus |
| `dropdown_border` | `color-mix(in srgb, var(--green) 18%, transparent)` | `rgba(26,90,170,0.25)` | Shared dropdown border for autocomplete, save menus, and app-native select menus |
| `dropdown_border_soft` | `color-mix(in srgb, var(--green) 14%, transparent)` | `rgba(26,90,170,0.18)` | Softer dropdown border used when dropdowns dock against mobile keyboard chrome |
| `dropdown_shadow` | `rgba(0,0,0,0.35)` | `rgba(0,0,0,0.14)` | Shared dropdown shadow for autocomplete, save menus, and app-native select menus |
| `dropdown_shadow_ring` | `color-mix(in srgb, var(--theme-dropdown-shadow) 24%, transparent)` | `color-mix(in srgb, var(--theme-dropdown-shadow) 24%, transparent)` | Subtle one-pixel shadow ring for dropdown surfaces |
| `dropdown_shadow_ring_strong` | `color-mix(in srgb, var(--theme-dropdown-shadow) 36%, transparent)` | `color-mix(in srgb, var(--theme-dropdown-shadow) 36%, transparent)` | Stronger dropdown shadow ring for keyboard-docked mobile dropdowns |
| `dropdown_item_text` | `#9a9a9a` | `#4a5868` | Text for autocomplete and menu items |
| `overlay_backdrop_bg` | `rgba(0,0,0,0.76)` | `rgba(34,58,88,0.22)` | Shared backdrop behind modals and overlays |

### Search and Output Highlights

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `search_highlight_bg` | `color-mix(in srgb, var(--amber) 35%, transparent)` | `rgba(154,66,0,0.18)` | Inline search match highlight fill |
| `search_highlight_current_bg` | `color-mix(in srgb, var(--amber) 70%, transparent)` | `rgba(154,66,0,0.34)` | Inline current search match highlight fill |
| `search_signal_bg` | `color-mix(in srgb, var(--amber) 8%, transparent)` | `rgba(154,66,0,0.08)` | Output-line background for signal-scoped search matches |
| `search_signal_accent` | `color-mix(in srgb, var(--amber) 55%, transparent)` | `rgba(154,66,0,0.28)` | Output-line left accent for signal-scoped search matches |
| `search_signal_current_bg` | `color-mix(in srgb, var(--amber) 16%, transparent)` | `rgba(154,66,0,0.14)` | Output-line background for the current signal-scoped search match |
| `search_signal_current_accent` | `color-mix(in srgb, var(--amber) 88%, transparent)` | `rgba(154,66,0,0.42)` | Output-line left accent for the current signal-scoped search match |

### Inline Surfaces

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `inline_surface_bg` | `#141414` | `#dce6f0` | Inline code, allowed-command chips, and compact embedded surfaces |

### Toasts

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `toast_bg` | `#141414` | `#e4eef8` | Normal toast background |
| `toast_text` | `#39ff14` | `#2a5d18` | Normal toast text |
| `toast_border` | `#1a7a08` | `rgba(0,0,0,0.28)` | Normal toast border |
| `toast_error_bg` | `color-mix(in srgb, var(--red) 8%, var(--bg))` | `#e4eef8` | Error toast background |
| `toast_error_text` | `#ff3c3c` | `#cc2200` | Error toast text |
| `toast_error_border` | `color-mix(in srgb, var(--red) 45%, transparent)` | `rgba(204,34,0,0.38)` | Error toast border |
| `toast_shadow` | `0 12px 28px color-mix(in srgb, var(--theme-panel-shadow) 74%, transparent)` | `0 12px 28px color-mix(in srgb, var(--theme-panel-shadow) 74%, transparent)` | Shared toast elevation shadow |

### Welcome and Onboarding

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `welcome_ascii_color` | `var(--green)` | `var(--green)` | Direct ASCII-art text color before filter and shadow treatment |
| `welcome_command_hover_bg` | `color-mix(in srgb, var(--green) 6%, transparent)` | `rgba(42,93,24,0.06)` | Hover state for clickable welcome commands |
| `welcome_command_hover_shadow` | `0 0 0 1px var(--green-glow)` | `0 0 0 1px rgba(42,93,24,0.1)` | Hover outline for clickable welcome commands |
| `welcome_ascii_text_shadow` | `0 0 10px color-mix(in srgb, var(--green) 14%, transparent), 0 0 4px color-mix(in srgb, var(--green) 18%, transparent), 0 1px 0 rgba(8,16,12,0.4)` | `0 0 0 transparent, 0 0 0 transparent, 0 1px 0 rgba(255,255,255,0.5)` | Welcome ASCII art text shadow |
| `welcome_ascii_filter` | `saturate(1.12) contrast(1.08) brightness(1.08)` | `saturate(0.9) contrast(0.95) brightness(0.9)` | Welcome ASCII art filter |

### Action and Selection Text

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `on_accent_text` | `#000` | `#000` | Text on bright accent fills such as the caret block and run button |
| `selection_text` | `#f7fff2` | `#f7fff2` | Prompt selection text color |
| `selection_line_text` | `#eef7ee` | `#eef7ee` | Prompt line text while a selection is active |
| `modal_danger_btn_text` | `#fff` | `#fff` | Text for danger-tone modal buttons |
| `modal_warning_btn_text` | `#000` | `#000` | Text for warning-tone modal buttons |

---

## Related Docs

- [README.md](README.md) — quick summary, quick start, installed tools, and configuration reference
- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime layers, request flow, persistence schema, and security mechanics
- [FEATURES.md](FEATURES.md) — full per-feature reference including purpose and use
- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, test workflow, linting, and merge request guidance
- [DECISIONS.md](DECISIONS.md) — architectural rationale, tradeoffs, and implementation-history notes
- [tests/README.md](tests/README.md) — test suite appendix, smoke-test coverage, and focused test commands
