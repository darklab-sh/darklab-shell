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
            ("# Soft border (low-contrast separators inside denser chrome)", "border_soft"),
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
                "# Terminal panes / panels / shell chrome",
                [
                    "panel_bg",
                    "panel_border",
                    "panel_shadow",
                    "terminal_bar_bg",
                    "chrome_bg",
                    "chrome_header_bg",
                    "chrome_row_bg",
                    "chrome_row_hover_bg",
                    "chrome_control_bg",
                    "chrome_control_border",
                    "chrome_divider_color",
                    "chrome_shadow",
                    "scrollbar_track",
                    "scrollbar_thumb",
                    "scrollbar_thumb_hover",
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
                "# Button primitives",
                [
                    "button_secondary_bg",
                    "button_secondary_border",
                    "button_secondary_text",
                    "button_secondary_hover_bg",
                    "button_secondary_hover_border",
                    "button_ghost_border",
                    "button_ghost_text",
                    "button_ghost_hover_bg",
                    "button_ghost_hover_border",
                    "button_destructive_bg",
                    "button_destructive_text",
                    "button_destructive_hover_bg",
                ],
            ),
            (
                "# Tabs bar / tabs",
                [
                    "tab_text",
                    "tab_hover_text",
                    "tab_active_bg",
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
                "# Restore overlay",
                [
                    "history_load_overlay_bg",
                ],
            ),
            (
                "# Modals",
                [
                    "modal_bg",
                ],
            ),
            (
                "# Dropdowns / autocomplete / app-native selects",
                [
                    "dropdown_bg",
                    "dropdown_border",
                    "dropdown_border_soft",
                    "dropdown_shadow",
                    "dropdown_shadow_ring",
                    "dropdown_shadow_ring_strong",
                    "dropdown_item_text",
                    "overlay_backdrop_bg",
                ],
            ),
            (
                "# Search highlights",
                [
                    "search_highlight_bg",
                    "search_highlight_current_bg",
                    "search_signal_bg",
                    "search_signal_accent",
                    "search_signal_current_bg",
                    "search_signal_current_accent",
                ],
            ),
            (
                "# Inline surfaces",
                ["inline_surface_bg"],
            ),
            (
                "# Toasts",
                [
                    "toast_bg",
                    "toast_text",
                    "toast_border",
                    "toast_error_bg",
                    "toast_error_text",
                    "toast_error_border",
                    "toast_shadow",
                ],
            ),
            (
                "# Welcome / onboarding styling",
                [
                    "welcome_ascii_color",
                    "welcome_command_hover_bg",
                    "welcome_command_hover_shadow",
                    "welcome_ascii_text_shadow",
                    "welcome_ascii_filter",
                ],
            ),
            (
                "# Action / selection text colors",
                [
                    "on_accent_text",
                    "selection_text",
                    "selection_line_text",
                    "modal_danger_btn_text",
                    "modal_warning_btn_text",
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
