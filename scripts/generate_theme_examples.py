#!/usr/bin/env python3
"""Generate the checked-in dark/light theme example files from _THEME_DEFAULTS."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONF_DIR = ROOT / "app" / "conf"
APP_DIR = ROOT / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from config import _THEME_DEFAULTS  # noqa: E402


SECTION_ORDER = [
    (
        "# ── Backgrounds ───────────────────────────────────────────────────────────────",
        [
            ("# Page background (body) — shown around and behind the terminal window", "bg"),
            ("# Surface background — used for modals, panels, and dropdowns", "surface"),
        ],
    ),
    (
        "# ── Borders ───────────────────────────────────────────────────────────────────",
        [
            ("# Subtle border (dividers, section separators)", "border"),
            ("# Prominent border (input focus rings, modal outlines)", "border_bright"),
        ],
    ),
    (
        "# ── Text ──────────────────────────────────────────────────────────────────────",
        [
            ("# Primary text color", "text"),
            ("# Muted / secondary text color (labels, hints, timestamps)", "muted"),
        ],
    ),
    (
        "# ── Accent Colors ─────────────────────────────────────────────────────────────",
        [
            ("# Primary green — used for the terminal prompt, run button, highlights, and\n# success indicators", "green"),
            ("# Dimmed green — used for borders, focus rings, and subtle highlights", "green_dim"),
            ("# Green glow — used for box-shadows and background tints (should be rgba)", "green_glow"),
            ("# Amber — used for warnings, the RUNNING status pill, starred items, and\n# denied-command messages", "amber"),
            ("# Red — used for errors, the FAIL/KILLED status, and the kill-task modal border", "red"),
            ("# Blue — used for the prompt prefix, welcome screen labels, notice lines, and command badges", "blue"),
        ],
    ),
    (
        "# ── Typography ────────────────────────────────────────────────────────────────",
        [
            ("# Terminal output font size", "terminal_font_size"),
            ("# Terminal output line height", "terminal_line_height"),
        ],
    ),
    (
        "# ── Component Chrome ─────────────────────────────────────────────────────────",
        [
            ("# Text used for the live prompt line shown above the hidden input", "prompt_line_text"),
            (
                "# Terminal pane / panel styling",
                [
                    "panel_bg",
                    "panel_alt_bg",
                    "panel_border",
                    "panel_shadow",
                    "terminal_bar_bg",
                    "terminal_bar_border",
                    "terminal_actions_bg",
                    "terminal_wrap_border",
                    "terminal_wrap_shadow",
                    "window_btn_close",
                    "window_btn_minimize",
                    "window_btn_maximize",
                ],
            ),
            (
                "# Header / toolbar buttons",
                [
                    "toolbar_button_bg",
                    "toolbar_button_border",
                    "toolbar_button_text",
                    "toolbar_button_hover_bg",
                    "toolbar_button_hover_border",
                    "toolbar_button_hover_text",
                    "toolbar_button_active_bg",
                    "toolbar_button_active_border",
                    "toolbar_button_active_text",
                ],
            ),
            (
                "# History chips / starred chips",
                [
                    "chip_bg",
                    "chip_border",
                    "chip_text",
                    "chip_hover_bg",
                    "chip_hover_border",
                    "chip_hover_text",
                    "chip_overflow_text",
                ],
            ),
            (
                "# Tabs bar / tabs",
                [
                    "tabs_bar_scrollbar_track",
                    "tabs_bar_scrollbar_thumb",
                    "tabs_bar_scrollbar_thumb_hover",
                    "tabs_scroll_btn_bg",
                    "tabs_scroll_btn_border",
                    "tabs_scroll_btn_text",
                    "tabs_scroll_btn_hover_bg",
                    "tabs_scroll_btn_hover_border",
                    "tabs_scroll_btn_hover_text",
                    "tab_bg",
                    "tab_border",
                    "tab_text",
                    "tab_hover_text",
                    "tab_active_bg",
                    "tab_active_border",
                    "tab_active_text",
                    "tab_active_shadow",
                    "tab_close_bg",
                    "tab_close_border",
                    "tab_close_hover_bg",
                    "tab_close_hover_border",
                    "tab_close_hover_text",
                    "tab_touch_drag_text_shadow",
                    "tab_drop_shadow",
                ],
            ),
            (
                "# History panel and restore overlay",
                [
                    "history_panel_bg",
                    "history_panel_shadow",
                    "history_entry_hover_bg",
                    "history_load_overlay_bg",
                    "history_load_modal_bg",
                    "history_load_modal_border",
                    "history_load_modal_shadow",
                ],
            ),
            (
                "# Modals",
                [
                    "faq_modal_bg",
                    "options_modal_bg",
                    "confirm_modal_bg",
                ],
            ),
            (
                "# Dropdowns / autocomplete",
                [
                    "dropdown_bg",
                    "dropdown_border",
                    "dropdown_shadow",
                    "dropdown_up_bg",
                    "dropdown_up_border",
                    "dropdown_up_shadow",
                    "dropdown_item_text",
                    "overlay_backdrop_bg",
                ],
            ),
            (
                "# FAQ / options controls",
                ["faq_code_bg", "allowed_chip_bg", "form_control_bg"],
            ),
            (
                "# Status / toasts",
                [
                    "tab_status_ok_bg",
                    "toast_bg",
                    "toast_text",
                    "toast_border",
                    "toast_error_bg",
                    "toast_error_text",
                    "toast_error_border",
                ],
            ),
            (
                "# Mobile shell / menu",
                [
                    "mobile_composer_host_bg",
                    "mobile_composer_host_light_bg",
                    "mobile_menu_bg",
                    "mobile_menu_border",
                    "mobile_menu_shadow",
                    "mobile_menu_button_border",
                    "mobile_menu_button_hover_bg",
                    "mobile_menu_button_hover_text",
                ],
            ),
            (
                "# Welcome / onboarding styling",
                [
                    "welcome_command_hover_bg",
                    "welcome_command_hover_shadow",
                    "welcome_ascii_text_shadow",
                    "welcome_ascii_filter",
                ],
            ),
        ],
    ),
]


INTRO = [
    "# darklab_shell — Theme Reference Template",
    "# -------------------------------------------",
    "# Copy this file to app/conf/themes/<filename>.yaml to create a selectable",
    "# theme variant. The runtime selector ignores *.yaml.example files and only",
    "# scans app/conf/themes/*.yaml.",
    "# Full reference: THEME.md",
    "# label: is optional and becomes the friendly name shown in the theme preview",
    "# modal. If omitted, the selector falls back to a humanized filename stem.",
    "# group: is optional and controls the preview-modal section header.",
    "# sort: is optional and controls ordering within the modal and between groups.",
    "# Theme values are plain CSS strings. You may reference other resolved theme",
    "# variables with CSS var(--name) syntax, or use CSS functions like color-mix();",
    "# the browser resolves those strings after the theme vars are injected.",
    "# app/conf/config.yaml default_theme should point at a full filename from",
    "# app/conf/themes/ (for example darklab_obsidian.yaml).",
    "# All values are CSS color strings (hex, rgb, rgba, hsl, etc.) or other valid",
    "# CSS values for the given key.",
    "# Changes take effect after a container restart (docker compose restart).",
    "# No rebuild needed.",
    "#",
    "# Leave a value commented out or omit it entirely to keep the app's built-in",
    "# fallback defaults from app/config.py.",
    "",
    "color_scheme: {family}",
]


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _emit_key(theme: dict, key: str) -> list[str]:
    return [f"{key}: {_quote(str(theme[key]))}"]


def generate_theme_example_text(family: str) -> str:
    theme = _THEME_DEFAULTS[family]
    lines: list[str] = [line.format(family=family) for line in INTRO]
    for section_title, entries in SECTION_ORDER:
        lines.extend(["", section_title, ""])
        for comment_or_title, key_or_keys in entries:
            lines.append(comment_or_title)
            if isinstance(key_or_keys, list):
                for key in key_or_keys:
                    lines.extend(_emit_key(theme, key))
            else:
                lines.extend(_emit_key(theme, key_or_keys))
            lines.append("")
        if lines[-1] == "":
            lines.pop()
    return "\n".join(lines) + "\n"


def write_theme_examples() -> None:
    (CONF_DIR / "theme_dark.yaml.example").write_text(generate_theme_example_text("dark"))
    (CONF_DIR / "theme_light.yaml.example").write_text(generate_theme_example_text("light"))


if __name__ == "__main__":
    write_theme_examples()
