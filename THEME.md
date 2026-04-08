# Theme System

This document is the full reference for the shell theme system. It explains how the theme files are loaded, how the values flow into the browser, and what every configurable key does.

## Overview

Theme support is split into a small pipeline:

1. `app/conf/theme_dark.yaml` and `app/conf/theme_light.yaml` are the operator-editable source files.
2. `app/config.py` loads those files, merges them with the built-in defaults, and filters out unknown keys.
3. `theme_css_vars()` converts the resolved theme values into CSS custom properties such as `--theme-panel-bg`.
4. `app/templates/theme_vars_style.html` injects the resolved CSS variables into the page so `styles.css` can use them directly.
5. `app/templates/theme_vars_script.html` exposes the same resolved values as `window.ThemeCssVars` for browser-side export helpers.
6. `app/static/css/styles.css` consumes the theme vars for the live UI, permalink pages, and shared chrome.
7. `app/static/js/export_html.js` reads the injected theme vars when generating downloadable HTML, so exported snapshots stay portable and match the active theme.

The live app, permalink pages, and exported HTML all read from the same resolved theme values. That is the main reason the theme system was externalized.

## Editing Rules

- Both theme files use commented-out defaults. Uncomment only the keys you want to override.
- Unknown keys are ignored by `app/config.py`; only keys that exist in `_THEME_DEFAULTS` are accepted.
- Values may be any valid CSS color, length, gradient, or shadow string, depending on the key.
- Restart the container after changing either theme file. No rebuild is required.
- Example variants such as `app/conf/theme_light_blue.yaml`, `app/conf/theme_light_olive.yaml`, and `app/conf/theme_light_sand.yaml` can live beside the canonical files as inspiration or starting points, but the loader only reads `theme_dark.yaml` and `theme_light.yaml` directly.
- The base palette keys are exposed as normal CSS variables such as `--bg`, `--surface`, `--text`, `--green`, and `--blue`.
- The component chrome keys are exposed as `--theme-*` variables, for example `--theme-panel-bg`, `--theme-tab-active-text`, and `--theme-toast-border`.

## File Roles

| File | Role |
|------|------|
| `app/conf/theme_dark.yaml` | Dark theme operator overrides and inline documentation |
| `app/conf/theme_light.yaml` | Light theme operator overrides and inline documentation |
| `app/config.py` | Loads, validates, and resolves theme values |
| `app/templates/theme_vars_style.html` | Injects resolved CSS variables into the page |
| `app/templates/theme_vars_script.html` | Exposes resolved theme values to browser JS |
| `app/static/css/styles.css` | Consumes the theme vars for live UI styling |
| `app/static/js/export_html.js` | Builds downloadable HTML snapshots from the resolved vars |

## How The Code Works

### 1. Load and merge

`load_theme(name)` in `app/config.py` starts with `_THEME_DEFAULTS[name]` and merges any values from `app/conf/theme_<name>.yaml`. If a key is missing, the built-in default remains in effect.

### 2. Export as CSS vars

`theme_css_vars(theme)` walks `_THEME_CSS_ORDER` and converts each accepted key into a CSS custom property named `--theme-<key>`. The ordering is stable so the injected CSS is deterministic.

### 3. Inject into the templates

`app.py` and `permalinks.py` pass `dark_theme_css` and `light_theme_css` into the templates. `theme_vars_style.html` turns those dictionaries into a `<style>` block containing `:root { ... }` and `body.light { ... }` declarations. That means the browser never needs to guess at the current palette.

### 4. Expose the values to JS

`theme_vars_script.html` serializes the same resolved values into `window.ThemeCssVars`. Browser-side helpers, especially the HTML export builder, can then read the exact runtime theme without duplicating a hardcoded palette.

### 5. Consume from CSS and export helpers

`styles.css` now uses the shared vars for the live shell, tabs, history drawer, FAQ, modals, mobile UI, welcome art, and toast surfaces. `export_html.js` uses the same vars when building downloadable HTML snapshots so the saved file matches the active theme instead of drifting over time.

## Appendix: Theme Options

The tables below list every supported theme key from `_THEME_DEFAULTS`. The dark and light files share the same key set; only the values differ.

### Base Palette

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `bg` | `#0d0d0d` | `#b8c4d0` | Page background behind the terminal shell |
| `surface` | `#141414` | `#eef2f6` | Core panel, modal, and dropdown surface color |
| `border` | `#1f1f1f` | `rgba(0,0,0,0.15)` | Subtle separators and low-emphasis borders |
| `border_bright` | `#2e2e2e` | `rgba(0,0,0,0.28)` | Stronger borders, focus outlines, and modal chrome |
| `text` | `#e0e0e0` | `#101820` | Primary body text |
| `muted` | `#7a7a7a` | `#5a6878` | Secondary labels, hints, and timestamps |
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

### Terminal Panes and Panels

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `panel_bg` | `#141414` | `#d4e0ec` | Main panel background |
| `panel_alt_bg` | `#101010` | `#e8eef6` | Alternate panel background |
| `panel_border` | `#2e2e2e` | `rgba(0,0,0,0.28)` | Panel borders |
| `panel_shadow` | `rgba(0,0,0,0.7)` | `rgba(0,0,0,0.22)` | Panel drop shadow |
| `terminal_bar_bg` | `#0d0d0d` | `#b8c4d0` | Top terminal bar background |
| `terminal_bar_border` | `#1f1f1f` | `#8898b0` | Top terminal bar border |
| `terminal_actions_bg` | `transparent` | `rgba(0,0,0,0.025)` | Actions strip behind top controls |
| `terminal_wrap_border` | `#2e2e2e` | `rgba(0,0,0,0.42)` | Outer terminal wrapper border |
| `terminal_wrap_shadow` | `rgba(0,0,0,0.7)` | `rgba(0,0,0,0.22)` | Outer terminal wrapper shadow |

### Toolbar Buttons and Chips

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `toolbar_button_bg` | `transparent` | `#c8d4e0` | Header and toolbar button backgrounds |
| `toolbar_button_border` | `#2e2e2e` | `#8898b0` | Header and toolbar button borders |
| `toolbar_button_text` | `#7a7a7a` | `#202838` | Header and toolbar button text |
| `toolbar_button_hover_bg` | `transparent` | `#b8c8d8` | Hover background for header buttons |
| `toolbar_button_hover_border` | `#1a7a08` | `#6880a0` | Hover border for header buttons |
| `toolbar_button_hover_text` | `#39ff14` | `#101820` | Hover text for header buttons |
| `toolbar_button_active_bg` | `rgba(57,255,20,0.06)` | `#a0b4c8` | Active header button background |
| `toolbar_button_active_border` | `#1a7a08` | `#6880a0` | Active header button border |
| `toolbar_button_active_text` | `#39ff14` | `#101820` | Active header button text |
| `chip_bg` | `transparent` | `#c8d4e0` | History chips and starred chips |
| `chip_border` | `#2e2e2e` | `#8898b0` | Chip borders |
| `chip_text` | `#7a7a7a` | `#202838` | Default chip text |
| `chip_hover_bg` | `rgba(57,255,20,0.12)` | `#b8c8d8` | Chip hover background |
| `chip_hover_border` | `#1a7a08` | `#6880a0` | Chip hover border |
| `chip_hover_text` | `#e0e0e0` | `#101820` | Chip hover text |
| `chip_overflow_text` | `#39ff14` | `#274f17` | “More” / overflow chip text |

### Tabs and Tab Controls

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `tabs_bar_bg` | `#0d0d0d` | `#a0b0c4` | Tabs bar background |
| `tabs_bar_scrollbar_track` | `rgba(255,255,255,0.06)` | `rgba(0,0,0,0.08)` | Tabs bar scrollbar track |
| `tabs_bar_scrollbar_thumb` | `#555555` | `#7890a8` | Tabs bar scrollbar thumb |
| `tabs_bar_scrollbar_thumb_hover` | `#777777` | `#5a6878` | Hover thumb color |
| `tabs_scroll_btn_bg` | `transparent` | `#c4d0dc` | Tab-scroll button background |
| `tabs_scroll_btn_border` | `#1f1f1f` | `#8898b0` | Tab-scroll button border |
| `tabs_scroll_btn_text` | `#7a7a7a` | `#202838` | Tab-scroll button text |
| `tabs_scroll_btn_hover_bg` | `transparent` | `#b4c4d4` | Tab-scroll button hover background |
| `tabs_scroll_btn_hover_border` | `#2e2e2e` | `#6880a0` | Tab-scroll button hover border |
| `tabs_scroll_btn_hover_text` | `#e0e0e0` | `#101010` | Tab-scroll button hover text |
| `tab_bg` | `linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01))` | `linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01))` | Inactive tab background |
| `tab_border` | `#2e2e2e` | `rgba(0,0,0,0.15)` | Inactive tab border |
| `tab_text` | `#7a7a7a` | `#5a6878` | Inactive tab text |
| `tab_hover_text` | `#e0e0e0` | `#101820` | Hovered tab text |
| `tab_active_bg` | `rgba(57,255,20,0.04)` | `#c0cedd` | Active tab background |
| `tab_active_border` | `color-mix(in srgb, var(--green) 42%, transparent)` | `#8898b0` | Active tab border |
| `tab_active_text` | `#39ff14` | `#101820` | Active tab text |
| `tab_active_shadow` | `none` | `inset 0 0 0 1px rgba(255,255,255,0.22)` | Active tab depth styling |
| `tab_close_bg` | `rgba(255,255,255,0.02)` | `rgba(255,255,255,0.02)` | Close-button background inside a tab |
| `tab_close_border` | `rgba(255,255,255,0.06)` | `rgba(255,255,255,0.06)` | Close-button border inside a tab |
| `tab_close_hover_bg` | `color-mix(in srgb, var(--red) 18%, transparent)` | `color-mix(in srgb, var(--red) 18%, transparent)` | Close-button hover background |
| `tab_close_hover_border` | `color-mix(in srgb, var(--red) 30%, transparent)` | `color-mix(in srgb, var(--red) 30%, transparent)` | Close-button hover border |
| `tab_close_hover_text` | `inherit` | `inherit` | Close-button hover text color |
| `tab_touch_drag_text_shadow` | `0 0 10px color-mix(in srgb, var(--green) 14%, transparent)` | `0 0 10px rgba(42,93,24,0.08)` | Drag feedback on touch devices |
| `tab_drop_shadow` | `0 0 10px color-mix(in srgb, var(--green) 45%, transparent)` | `0 0 10px rgba(42,93,24,0.18)` | Drag/drop emphasis for reordered tabs |

### History and Restore Overlays

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `history_panel_bg` | `#0d0d0d` | `#c8d8e8` | History drawer background |
| `history_entry_hover_bg` | `rgba(57,255,20,0.12)` | `rgba(26,90,170,0.06)` | Hover background for history entries |
| `history_load_overlay_bg` | `rgba(0,0,0,0.76)` | `rgba(0,0,0,0.76)` | Overlay shown while restoring a history entry |
| `history_load_modal_bg` | `color-mix(in srgb, var(--surface) 88%, #000)` | `#e8eef6` | Restore modal background |
| `history_load_modal_shadow` | `rgba(0,0,0,0.35)` | `rgba(0,0,0,0.35)` | Restore modal shadow |

### Modals and Dropdowns

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `faq_modal_bg` | `#141414` | `#e8eef6` | FAQ modal background |
| `options_modal_bg` | `#141414` | `#e8eef6` | Options modal background |
| `kill_modal_bg` | `#141414` | `#d4e0ec` | Kill confirmation modal background |
| `hist_del_modal_bg` | `#141414` | `#d4e0ec` | History delete confirmation modal background |
| `dropdown_bg` | `color-mix(in srgb, var(--surface) 96%, transparent)` | `#d4e0ec` | Main autocomplete dropdown background |
| `dropdown_border` | `color-mix(in srgb, var(--green) 18%, transparent)` | `rgba(26,90,170,0.25)` | Main autocomplete border |
| `dropdown_shadow` | `rgba(0,0,0,0.35)` | `rgba(0,0,0,0.14)` | Main autocomplete shadow |
| `dropdown_up_bg` | `color-mix(in srgb, var(--surface) 98%, transparent)` | `#d4e0ec` | Upward-opening autocomplete background |
| `dropdown_up_border` | `color-mix(in srgb, var(--green) 28%, transparent)` | `rgba(26,90,170,0.35)` | Upward-opening autocomplete border |
| `dropdown_up_shadow` | `rgba(0,0,0,0.45)` | `rgba(0,0,0,0.14)` | Upward-opening autocomplete shadow |
| `dropdown_item_text` | `#7a7a7a` | `#4a5868` | Text for autocomplete items |
| `faq_code_bg` | `#141414` | `#dce6f0` | Code-styled FAQ tokens and examples |
| `allowed_chip_bg` | `#141414` | `#dce6f0` | Allowed-command chips in the FAQ |
| `options_select_bg` | `#141414` | `#e0e8f4` | Options modal select controls |

### Status and Toasts

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `tab_status_ok_bg` | `#39ff14` | `#22a040` | Success dot / OK status on tabs |
| `toast_bg` | `#141414` | `#e4eef8` | Normal toast background |
| `toast_text` | `#39ff14` | `#2a5d18` | Normal toast text |
| `toast_border` | `#1a7a08` | `rgba(0,0,0,0.28)` | Normal toast border |
| `toast_error_bg` | `color-mix(in srgb, var(--red) 8%, var(--bg))` | `#e4eef8` | Error toast background |
| `toast_error_text` | `#ff3c3c` | `#cc2200` | Error toast text |
| `toast_error_border` | `color-mix(in srgb, var(--red) 45%, transparent)` | `rgba(204,34,0,0.38)` | Error toast border |

### Mobile Shell and Menu

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `mobile_composer_host_bg` | `linear-gradient(180deg, rgba(20,20,20,0.92), rgba(20,20,20,0.98))` | `linear-gradient(180deg, rgba(20,20,20,0.92), rgba(20,20,20,0.98))` | Mobile composer host background in dark mode and base fallback |
| `mobile_composer_host_light_bg` | `linear-gradient(180deg, rgba(238,242,246,0.94), rgba(238,242,246,0.99))` | `linear-gradient(180deg, rgba(238,242,246,0.94), rgba(238,242,246,0.99))` | Mobile composer host background in light mode |
| `mobile_menu_bg` | `#141414` | `#eef2f6` | Mobile overflow/menu panel background |
| `mobile_menu_border` | `#2e2e2e` | `rgba(0,0,0,0.28)` | Mobile menu border |
| `mobile_menu_shadow` | `rgba(0,0,0,0.6)` | `rgba(0,0,0,0.6)` | Mobile menu shadow |
| `mobile_menu_button_border` | `#1f1f1f` | `#dce6f0` | Mobile menu button border |
| `mobile_menu_button_hover_bg` | `var(--green-glow)` | `var(--bg)` | Mobile menu button hover background |
| `mobile_menu_button_hover_text` | `#39ff14` | `#101820` | Mobile menu button hover text |

### Welcome and Onboarding

| Key | Dark default | Light default | Used for |
|-----|--------------|---------------|----------|
| `welcome_command_hover_bg` | `color-mix(in srgb, var(--green) 6%, transparent)` | `rgba(42,93,24,0.06)` | Hover state for clickable welcome commands |
| `welcome_command_hover_shadow` | `0 0 0 1px var(--green-glow)` | `0 0 0 1px rgba(42,93,24,0.1)` | Hover outline for clickable welcome commands |
| `welcome_ascii_text_shadow` | `0 0 10px color-mix(in srgb, var(--green) 14%, transparent), 0 0 4px color-mix(in srgb, var(--green) 18%, transparent), 0 1px 0 rgba(8,16,12,0.4)` | `0 0 0 transparent, 0 0 0 transparent, 0 1px 0 rgba(255,255,255,0.5)` | Welcome ASCII art text shadow |
| `welcome_ascii_filter` | `saturate(1.12) contrast(1.08) brightness(1.08)` | `saturate(0.9) contrast(0.95) brightness(0.9)` | Welcome ASCII art filter |

## Practical Notes

- The YAML files are intentionally verbose so operators can tune the shell without touching code.
- Most values are safe to tweak live as long as they remain valid CSS values.
- The theme layer is shared by the live app, permalink pages, and export HTML, so a change in these files can affect all three surfaces.
- If you are trying to restyle something and cannot find a key in this appendix, it is probably still hardcoded elsewhere in CSS and should be moved to the theme system next.
