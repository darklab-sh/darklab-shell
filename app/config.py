"""
Application configuration and scanner-user setup.
Imported by database, process, permalinks, and app modules.
"""

import os
import pwd
from pathlib import Path
import yaml
from redaction import BUILTIN_SHARE_REDACTION_RULES, normalize_redaction_rules

APP_VERSION = "1.6"
PROJECT_NAME = "darklab_shell"

PROJECT_README = "ttps://gitlab.com/darklab.sh/darklab_shell/-/tree/v1.6?ref_type=heads#darklab_shell"
# PROJECT_README = "https://gitlab.com/darklab.sh/darklab_shell#darklab_shell"
APP_CONF_DIR = os.environ.get("APP_CONF_DIR", "")


def _load_yaml_config(path):
    if not path.exists():
        return {}
    with open(path) as f:
        loaded = yaml.safe_load(f) or {}
    return loaded if isinstance(loaded, dict) else {}


def _load_yaml_config_optional(path):
    try:
        return _load_yaml_config(path)
    except yaml.YAMLError:
        return {}


def _coerce_mb_value(value):
    # Accept both numeric YAML scalars and human-edited strings like "25" or
    # "25mb" so the config layer stays forgiving without leaking bad values.
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        token = value.strip().lower().replace(" ", "")
        if token.endswith("mb"):
            token = token[:-2]
        elif token.endswith("m"):
            token = token[:-1]
        if not token:
            return None
        try:
            return max(0, int(token))
        except ValueError:
            try:
                return max(0, int(float(token)))
            except ValueError:
                return None
    return None


def load_config(conf_dir=None):
    """Load config.yaml plus optional config.local.yaml overlays.

    config.local.yaml is read after config.yaml, so it can override selected
    keys while leaving the checked-in defaults in place.
    """
    defaults = {
        "app_name":                   "darklab_shell",
        "prompt_prefix":              "anon@darklab.sh",
        "motd":                       "",
        "default_theme":              "darklab_obsidian.yaml",
        "history_panel_limit":        50,
        "recent_commands_limit":      50,
        "data_dir":                   "",
        "permalink_retention_days":   365,
        "log_level":                  "INFO",
        "log_format":                 "text",
        "trusted_proxy_cidrs":        ["127.0.0.1/32", "::1/128"],
        "diagnostics_allowed_cidrs":  [],
        "restricted_command_input_cidrs": [],
        "share_redaction_enabled":    True,
        "share_redaction_rules":      [],
        "rate_limit_enabled":         True,
        "rate_limit_per_minute":      30,
        "rate_limit_per_second":      5,
        "max_output_lines":           5000,
        "persist_full_run_output":    True,
        "full_output_max_mb":         5,
        "workspace_enabled":          False,
        "workspace_backend":          "tmpfs",
        # Intentional server-side workspace root default. Workspaces are
        # disabled unless explicitly enabled and all file names are validated
        # relative to hashed per-session directories before use.
        "workspace_root":             "/tmp/darklab_shell-workspaces",  # nosec
        "workspace_quota_mb":         50,
        "workspace_max_file_mb":      5,
        "workspace_max_files":        100,
        "workspace_inactivity_ttl_hours": 1,
        "max_tabs":                   8,
        "command_timeout_seconds":    3600,
        "heartbeat_interval_seconds": 20,
        "run_broker_enabled":         True,
        "run_broker_require_redis":   True,
        "run_broker_active_stream_ttl_seconds": 14400,
        "run_broker_completed_stream_ttl_seconds": 3600,
        "run_broker_max_replay_bytes": 10485760,
        "run_broker_subscriber_block_seconds": 15,
        "run_broker_heartbeat_seconds": 20,
        "run_broker_owner_stale_seconds": 75,
        "welcome_char_ms":            18,
        "welcome_jitter_ms":          12,
        "welcome_post_cmd_ms":        650,
        "welcome_inter_block_ms":     850,
        "welcome_first_prompt_idle_ms": 1500,
        "welcome_post_status_pause_ms": 500,
        "welcome_sample_count":       5,
        "welcome_status_labels":      ["CONFIG", "RUNNER", "HISTORY", "LIMITS", "AUTOCOMPLETE"],
        "welcome_hint_interval_ms":   4200,
        "welcome_hint_rotations":     0,
    }
    if conf_dir is not None:
        conf_path = Path(conf_dir)
    elif APP_CONF_DIR:
        conf_path = Path(APP_CONF_DIR)
    else:
        conf_path = Path(__file__).resolve().parent / "conf"
    defaults.update(_load_yaml_config(conf_path / "config.yaml"))
    defaults.update(_load_yaml_config_optional(conf_path / "config.local.yaml"))
    legacy_full_output_max_bytes = defaults.pop("full_output_max_bytes", None)
    full_output_max_mb = _coerce_mb_value(defaults.get("full_output_max_mb"))
    if full_output_max_mb is None and legacy_full_output_max_bytes is not None:
        try:
            legacy_bytes = max(0, int(legacy_full_output_max_bytes))
        except (TypeError, ValueError):
            legacy_bytes = 0
        defaults["full_output_max_mb"] = max(0, (legacy_bytes + (1024 * 1024) - 1) // (1024 * 1024))
        defaults["full_output_max_bytes"] = legacy_bytes
        return defaults
    if full_output_max_mb is None:
        full_output_max_mb = 5
    defaults["full_output_max_mb"] = full_output_max_mb
    defaults["full_output_max_bytes"] = full_output_max_mb * 1024 * 1024
    # Share/export redaction rules are normalized up front so the browser and
    # the snapshot endpoint both receive the same validated rule set.
    defaults["share_redaction_rules"] = normalize_redaction_rules(
        defaults.get("share_redaction_rules", [])
    )
    return defaults


CFG = load_config()


def _is_writable_directory(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe_path = os.path.join(path, f".darklab_write_probe_{os.getpid()}")
        with open(probe_path, "w", encoding="utf-8") as f:
            f.write("")
        os.unlink(probe_path)
        return True
    except OSError:
        return False


def _configured_data_dir(value):
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _require_writable_data_dir(path, source):
    resolved = os.path.expanduser(path)
    if not _is_writable_directory(resolved):
        raise RuntimeError(f"{source} is not writable: {resolved}")
    return resolved


def resolve_data_dir(cfg=None):
    """Return the writable directory used for SQLite and run-output artifacts."""
    env_data_dir = _configured_data_dir(os.environ.get("APP_DATA_DIR"))
    if env_data_dir:
        return _require_writable_data_dir(env_data_dir, "APP_DATA_DIR")

    active_cfg = CFG if cfg is None else cfg
    configured = _configured_data_dir(active_cfg.get("data_dir"))
    if configured:
        return _require_writable_data_dir(configured, "data_dir")

    if _is_writable_directory("/data"):
        return "/data"
    return _require_writable_data_dir("/tmp", "fallback data_dir")  # nosec B108


def get_share_redaction_rules(cfg=None):
    """Return the effective share/export redaction rules for the current config."""
    active_cfg = cfg or CFG
    if not active_cfg.get("share_redaction_enabled", True):
        return []
    # Built-in rules provide a conservative baseline. Operator-defined rules are
    # appended so deployments can add environment-specific masking on top.
    return BUILTIN_SHARE_REDACTION_RULES + list(active_cfg.get("share_redaction_rules") or [])


_THEME_DEFAULTS = {
    # These builtin families are the source of truth for generated example
    # themes and for missing-key fallback when custom themes are partial.
    "dark": {
        "bg":                  "#000000",
        "surface":             "#141414",
        "border":              "#2a2a2a",
        "border_bright":       "#3c3c3c",
        "border_soft":         "rgba(255, 255, 255, 0.08)",
        "text":                "#e0e0e0",
        "muted":               "#9a9a9a",
        "green":               "#39ff14",
        "green_dim":           "#1a7a08",
        "green_glow":          "rgba(57,255,20,0.12)",
        "amber":               "#ffb800",
        "red":                 "#ff3c3c",
        "blue":                "#6ab0f5",
        "terminal_font_size":  "14px",
        "terminal_line_height": "1.65",
        "prompt_line_text":    "#e8e8e8",
        "panel_bg":            "#141414",
        "panel_border":        "#3c3c3c",
        "panel_shadow":        "rgba(170,170,170,0.12)",
        "terminal_bar_bg":     "#000000",
        "chrome_bg":           "#0c0c0c",
        "chrome_header_bg":    "#0c0c0c",
        "chrome_row_bg":       "#0c0c0c",
        "chrome_row_hover_bg": "rgba(57,255,20,0.12)",
        "chrome_control_bg":   "color-mix(in srgb, var(--surface) 92%, transparent)",
        "chrome_control_border": "var(--border-bright)",
        "chrome_divider_color": "#2a2a2a",
        "chrome_shadow":       "rgba(0,0,0,0.6)",
        "scrollbar_track":     "color-mix(in srgb, var(--surface) 72%, transparent)",
        "scrollbar_thumb":     "color-mix(in srgb, var(--muted) 44%, var(--border-bright))",
        "scrollbar_thumb_hover": "color-mix(in srgb, var(--text) 38%, var(--border-bright))",
        "toolbar_button_bg":   "transparent",
        "toolbar_button_border": "#3c3c3c",
        "toolbar_button_text": "#9a9a9a",
        "toolbar_button_hover_bg": "transparent",
        "toolbar_button_hover_border": "#1a7a08",
        "toolbar_button_hover_text": "#39ff14",
        "toolbar_button_active_bg": "rgba(57,255,20,0.06)",
        "toolbar_button_active_border": "#1a7a08",
        "toolbar_button_active_text": "#39ff14",
        "button_secondary_bg": "color-mix(in srgb, var(--surface) 66%, transparent)",
        "button_secondary_border": "color-mix(in srgb, var(--border-bright) 88%, transparent)",
        "button_secondary_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_secondary_hover_bg": "color-mix(in srgb, var(--_tone) 7%, transparent)",
        "button_secondary_hover_border": "color-mix(in srgb, var(--_tone-dim) 72%, var(--border-bright))",
        "button_ghost_border": "color-mix(in srgb, var(--border-bright) 58%, transparent)",
        "button_ghost_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_ghost_hover_bg": "color-mix(in srgb, var(--_tone) 10%, transparent)",
        "button_ghost_hover_border": "color-mix(in srgb, var(--_tone-dim) 62%, var(--border-bright))",
        "button_destructive_bg": "color-mix(in srgb, var(--_tone) 8%, transparent)",
        "button_destructive_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_destructive_hover_bg": "color-mix(in srgb, var(--_tone) 16%, transparent)",
        "tab_text":             "#9a9a9a",
        "tab_hover_text":       "#e0e0e0",
        "tab_active_bg":        "rgba(57,255,20,0.04)",
        "tab_close_bg":         "rgba(255,255,255,0.02)",
        "tab_close_border":     "rgba(255,255,255,0.06)",
        "tab_close_hover_bg":   "color-mix(in srgb, var(--green-dim) 18%, transparent)",
        "tab_close_hover_border": "color-mix(in srgb, var(--green-dim) 30%, transparent)",
        "tab_close_hover_text": "inherit",
        "tab_touch_drag_text_shadow": "0 0 10px color-mix(in srgb, var(--green) 14%, transparent)",
        "tab_drop_shadow":      "0 0 10px color-mix(in srgb, var(--green) 45%, transparent)",
        "history_load_overlay_bg": "rgba(0,0,0,0.76)",
        "modal_bg":             "#141414",
        "dropdown_bg":          "color-mix(in srgb, var(--surface) 96%, transparent)",
        "dropdown_border":      "color-mix(in srgb, var(--green) 18%, transparent)",
        "dropdown_border_soft": "color-mix(in srgb, var(--green) 14%, transparent)",
        "dropdown_shadow":      "rgba(0,0,0,0.35)",
        "dropdown_shadow_ring": "color-mix(in srgb, var(--theme-dropdown-shadow) 24%, transparent)",
        "dropdown_shadow_ring_strong": "color-mix(in srgb, var(--theme-dropdown-shadow) 36%, transparent)",
        "dropdown_item_text":   "#9a9a9a",
        "overlay_backdrop_bg":  "rgba(0,0,0,0.76)",
        "search_highlight_bg": "color-mix(in srgb, var(--amber) 35%, transparent)",
        "search_highlight_current_bg": "color-mix(in srgb, var(--amber) 70%, transparent)",
        "search_signal_bg":    "color-mix(in srgb, var(--amber) 8%, transparent)",
        "search_signal_accent": "color-mix(in srgb, var(--amber) 55%, transparent)",
        "search_signal_current_bg": "color-mix(in srgb, var(--amber) 16%, transparent)",
        "search_signal_current_accent": "color-mix(in srgb, var(--amber) 88%, transparent)",
        "inline_surface_bg":    "#141414",
        "toast_bg":             "#141414",
        "toast_text":           "#39ff14",
        "toast_border":         "#1a7a08",
        "toast_error_bg":       "color-mix(in srgb, var(--red) 8%, var(--bg))",
        "toast_error_text":     "#ff3c3c",
        "toast_error_border":   "color-mix(in srgb, var(--red) 45%, transparent)",
        "toast_shadow":         "0 12px 28px color-mix(in srgb, var(--theme-panel-shadow) 74%, transparent)",
        "welcome_command_hover_bg": "color-mix(in srgb, var(--green) 6%, transparent)",
        "welcome_command_hover_shadow": "0 0 0 1px var(--green-glow)",
        "welcome_ascii_text_shadow": (
            "0 0 10px color-mix(in srgb, var(--green) 14%, transparent), "
            "0 0 4px color-mix(in srgb, var(--green) 18%, transparent), "
            "0 1px 0 rgba(8,16,12,0.4)"
        ),
        "welcome_ascii_color": "var(--green)",
        "welcome_ascii_filter": "saturate(1.12) contrast(1.08) brightness(1.08)",
        "on_accent_text":      "#000",
        "selection_text":      "#f7fff2",
        "selection_line_text": "#eef7ee",
        "modal_danger_btn_text": "#fff",
        "modal_warning_btn_text": "#000",
    },
    "light": {
        "bg":                  "#b8c4d0",
        "surface":             "#eef2f6",
        "border":              "rgba(0,0,0,0.15)",
        "border_bright":       "rgba(0,0,0,0.28)",
        "border_soft":         "rgba(0,0,0,0.12)",
        "text":                "#101820",
        "muted":               "#5a6878",
        "green":               "#2a5d18",
        "green_dim":           "#355f24",
        "green_glow":          "rgba(42,93,24,0.08)",
        "amber":               "#9a4200",
        "red":                 "#cc2200",
        "blue":                "#1a5aaa",
        "terminal_font_size":  "14px",
        "terminal_line_height": "1.65",
        "prompt_line_text":    "#1c201a",
        "panel_bg":            "#d4e0ec",
        "panel_border":        "rgba(0,0,0,0.28)",
        "panel_shadow":        "rgba(0,0,0,0.22)",
        "terminal_bar_bg":     "#b8c4d0",
        "chrome_bg":           "#b8c4d0",
        "chrome_header_bg":    "#b8c4d0",
        "chrome_row_bg":       "#b8c4d0",
        "chrome_row_hover_bg": "rgba(26,90,170,0.06)",
        "chrome_control_bg":   "color-mix(in srgb, var(--surface) 92%, transparent)",
        "chrome_control_border": "var(--border-bright)",
        "chrome_divider_color": "rgba(0,0,0,0.15)",
        "chrome_shadow":       "rgba(0,0,0,0.6)",
        "scrollbar_track":     "color-mix(in srgb, var(--surface) 72%, transparent)",
        "scrollbar_thumb":     "color-mix(in srgb, var(--muted) 44%, var(--border-bright))",
        "scrollbar_thumb_hover": "color-mix(in srgb, var(--text) 38%, var(--border-bright))",
        "toolbar_button_bg":   "#c8d4e0",
        "toolbar_button_border": "#8898b0",
        "toolbar_button_text": "#202838",
        "toolbar_button_hover_bg": "#b8c8d8",
        "toolbar_button_hover_border": "#6880a0",
        "toolbar_button_hover_text": "#101820",
        "toolbar_button_active_bg": "#a0b4c8",
        "toolbar_button_active_border": "#6880a0",
        "toolbar_button_active_text": "#101820",
        "button_secondary_bg": "color-mix(in srgb, var(--surface) 66%, transparent)",
        "button_secondary_border": "color-mix(in srgb, var(--border-bright) 88%, transparent)",
        "button_secondary_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_secondary_hover_bg": "color-mix(in srgb, var(--_tone) 7%, transparent)",
        "button_secondary_hover_border": "color-mix(in srgb, var(--_tone-dim) 72%, var(--border-bright))",
        "button_ghost_border": "color-mix(in srgb, var(--border-bright) 58%, transparent)",
        "button_ghost_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_ghost_hover_bg": "color-mix(in srgb, var(--_tone) 10%, transparent)",
        "button_ghost_hover_border": "color-mix(in srgb, var(--_tone-dim) 62%, var(--border-bright))",
        "button_destructive_bg": "color-mix(in srgb, var(--_tone) 8%, transparent)",
        "button_destructive_text": "color-mix(in srgb, var(--muted) 86%, var(--text))",
        "button_destructive_hover_bg": "color-mix(in srgb, var(--_tone) 16%, transparent)",
        "tab_text":             "#5a6878",
        "tab_hover_text":       "#101820",
        "tab_active_bg":        "#c0cedd",
        "tab_close_bg":         "rgba(255,255,255,0.02)",
        "tab_close_border":     "rgba(255,255,255,0.06)",
        "tab_close_hover_bg":   "color-mix(in srgb, var(--red) 18%, transparent)",
        "tab_close_hover_border": "color-mix(in srgb, var(--red) 30%, transparent)",
        "tab_close_hover_text": "inherit",
        "tab_touch_drag_text_shadow": "0 0 10px rgba(42,93,24,0.08)",
        "tab_drop_shadow":      "0 0 10px rgba(42,93,24,0.18)",
        "history_load_overlay_bg": "rgba(0,0,0,0.76)",
        "modal_bg":             "#e8eef6",
        "dropdown_bg":          "#d4e0ec",
        "dropdown_border":      "rgba(26,90,170,0.25)",
        "dropdown_border_soft": "rgba(26,90,170,0.18)",
        "dropdown_shadow":      "rgba(0,0,0,0.14)",
        "dropdown_shadow_ring": "color-mix(in srgb, var(--theme-dropdown-shadow) 24%, transparent)",
        "dropdown_shadow_ring_strong": "color-mix(in srgb, var(--theme-dropdown-shadow) 36%, transparent)",
        "dropdown_item_text":   "#4a5868",
        "overlay_backdrop_bg":  "rgba(34,58,88,0.22)",
        "search_highlight_bg": "rgba(154,66,0,0.18)",
        "search_highlight_current_bg": "rgba(154,66,0,0.34)",
        "search_signal_bg":    "rgba(154,66,0,0.08)",
        "search_signal_accent": "rgba(154,66,0,0.28)",
        "search_signal_current_bg": "rgba(154,66,0,0.14)",
        "search_signal_current_accent": "rgba(154,66,0,0.42)",
        "inline_surface_bg":    "#dce6f0",
        "toast_bg":             "#e4eef8",
        "toast_text":           "#2a5d18",
        "toast_border":         "rgba(0,0,0,0.28)",
        "toast_error_bg":       "#e4eef8",
        "toast_error_text":     "#cc2200",
        "toast_error_border":   "rgba(204,34,0,0.38)",
        "toast_shadow":         "0 12px 28px color-mix(in srgb, var(--theme-panel-shadow) 74%, transparent)",
        "welcome_command_hover_bg": "rgba(42,93,24,0.06)",
        "welcome_command_hover_shadow": "0 0 0 1px rgba(42,93,24,0.1)",
        "welcome_ascii_color": "var(--green)",
        "welcome_ascii_text_shadow": "0 0 0 transparent, 0 0 0 transparent, 0 1px 0 rgba(255,255,255,0.5)",
        "welcome_ascii_filter": "saturate(0.9) contrast(0.95) brightness(0.9)",
        "on_accent_text":      "#000",
        "selection_text":      "#f7fff2",
        "selection_line_text": "#eef7ee",
        "modal_danger_btn_text": "#fff",
        "modal_warning_btn_text": "#000",
    },
}

_THEME_CONF_DIR = Path(__file__).resolve().parent / "conf"
_THEME_VARIANT_DIR = _THEME_CONF_DIR / "themes"
_THEME_BASE_CSS_KEYS = (
    "bg",
    "surface",
    "border",
    "border_bright",
    "border_soft",
    "text",
    "muted",
    "green",
    "green_dim",
    "green_glow",
    "amber",
    "red",
    "blue",
    "terminal_font_size",
    "terminal_line_height",
)


_THEME_CSS_ORDER = (
    "bg",
    "surface",
    "border",
    "border_bright",
    "border_soft",
    "text",
    "muted",
    "green",
    "green_dim",
    "green_glow",
    "amber",
    "red",
    "blue",
    "terminal_font_size",
    "terminal_line_height",
    "prompt_line_text",
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
    "toolbar_button_bg",
    "toolbar_button_border",
    "toolbar_button_text",
    "toolbar_button_hover_bg",
    "toolbar_button_hover_border",
    "toolbar_button_hover_text",
    "toolbar_button_active_bg",
    "toolbar_button_active_border",
    "toolbar_button_active_text",
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
    "history_load_overlay_bg",
    "modal_bg",
    "dropdown_bg",
    "dropdown_border",
    "dropdown_border_soft",
    "dropdown_shadow",
    "dropdown_shadow_ring",
    "dropdown_shadow_ring_strong",
    "dropdown_item_text",
    "overlay_backdrop_bg",
    "search_highlight_bg",
    "search_highlight_current_bg",
    "search_signal_bg",
    "search_signal_accent",
    "search_signal_current_bg",
    "search_signal_current_accent",
    "inline_surface_bg",
    "toast_bg",
    "toast_text",
    "toast_border",
    "toast_error_bg",
    "toast_error_text",
    "toast_error_border",
    "toast_shadow",
    "welcome_ascii_color",
    "welcome_command_hover_bg",
    "welcome_command_hover_shadow",
    "welcome_ascii_text_shadow",
    "welcome_ascii_filter",
    "on_accent_text",
    "selection_text",
    "selection_line_text",
    "modal_danger_btn_text",
    "modal_warning_btn_text",
)


def theme_css_vars(theme: dict) -> dict:
    """Return CSS custom property names for a theme dict."""
    # Export only the ordered theme keys that CSS/templates are expected to read.
    css_vars = {}
    for key in _THEME_CSS_ORDER:
        if key in theme:
            css_vars[f"--theme-{key.replace('_', '-')}"] = theme[key]
    return css_vars


def theme_runtime_css_vars(theme: dict) -> dict:
    """Return the full runtime CSS custom property map for a theme dict."""
    css_vars = {}
    for key in _THEME_BASE_CSS_KEYS:
        if key in theme:
            css_vars[f"--{key.replace('_', '-')}"] = theme[key]
    css_vars.update(theme_css_vars(theme))
    return css_vars


def _parse_theme_rgb(value: str):
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("#"):
        hex_value = raw[1:]
        if len(hex_value) == 3:
            try:
                return tuple(int(ch * 2, 16) for ch in hex_value)
            except ValueError:
                return None
        if len(hex_value) == 6:
            try:
                return tuple(int(hex_value[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                return None
        return None
    if raw.lower().startswith("rgb(") or raw.lower().startswith("rgba("):
        parts = raw[raw.find("(") + 1: raw.rfind(")")].split(",")
        if len(parts) < 3:
            return None
        try:
            return tuple(max(0, min(255, int(float(parts[i].strip())))) for i in range(3))
        except ValueError:
            return None
    return None


def theme_color_scheme(theme: dict) -> str:
    """Return a best-effort document color-scheme hint for the resolved theme."""
    for key in ("bg", "surface", "panel_bg"):
        rgb = _parse_theme_rgb(theme.get(key, ""))
        if rgb is None:
            continue
        red, green, blue = rgb
        luminance = (0.299 * red) + (0.587 * green) + (0.114 * blue)
        return "only light" if luminance >= 160 else "only dark"
    return "light dark"


def _theme_name_stem(name: str) -> str:
    stem = str(name).strip()
    if stem.lower().endswith(".yaml"):
        stem = stem[:-5]
    return stem


def _theme_label_from_name(name: str) -> str:
    stem = _theme_name_stem(name)
    for prefix in ("cg_", "c_", "g_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    if stem.startswith("theme_light_"):
        stem = stem[len("theme_light_"):]
    elif stem.startswith("theme_dark_"):
        stem = stem[len("theme_dark_"):]
    elif stem.startswith("light_"):
        stem = stem[len("light_"):]
    elif stem.startswith("dark_"):
        stem = stem[len("dark_"):]
    stem = stem.replace("_", " ").strip()
    return stem.title() if stem else name.replace("_", " ").title()


def _theme_sort_value(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _theme_default_family(theme_data: dict) -> str:
    # color_scheme selects which builtin family fills any keys the theme omits.
    raw = str(theme_data.get("color_scheme", "")).strip().lower()
    if raw in ("light", "only light"):
        return "light"
    if raw in ("dark", "only dark"):
        return "dark"
    return "dark"


def _theme_file_candidates(name):
    stem = _theme_name_stem(name)
    return (_THEME_VARIANT_DIR / f"{stem}.yaml",)


def _load_theme_yaml(name):
    # Support both exact filenames and stem-like names so operator config can be
    # human friendly while the on-disk registry stays filename based.
    theme_data = {}
    for theme_path in _theme_file_candidates(name):
        if not os.path.exists(theme_path):
            continue
        try:
            with open(theme_path) as f:
                loaded = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            loaded = {}
        if isinstance(loaded, dict):
            theme_data.update(loaded)
        local_overlay = theme_path.with_name(f"{theme_path.stem}.local{theme_path.suffix}")
        if local_overlay.exists():
            try:
                with open(local_overlay) as f:
                    local_loaded = yaml.safe_load(f) or {}
            except yaml.YAMLError:
                local_loaded = {}
            if isinstance(local_loaded, dict):
                theme_data.update(local_loaded)
        return theme_data
    return {}


def load_theme(name):
    """Load a theme YAML file, falling back to the matching built-in defaults for missing keys."""
    # Partial or malformed themes should still resolve to a complete palette so
    # the UI never renders with missing CSS variables.
    name = _theme_name_stem(name)
    user_theme = _load_theme_yaml(name)
    defaults = dict(_THEME_DEFAULTS[_theme_default_family(user_theme)])
    defaults.update({k: str(v) for k, v in user_theme.items() if k in defaults})
    return defaults


def _builtin_theme_entry(name):
    theme = dict(_THEME_DEFAULTS["dark"])
    return {
        "name": name,
        "label": _theme_label_from_name(name),
        "group": "Other",
        "sort": 0,
        "source": "built-in",
        "color_scheme": theme_color_scheme(theme),
        "vars": theme_runtime_css_vars(theme),
        "theme_vars": theme_css_vars(theme),
    }


DARK_THEME = dict(_THEME_DEFAULTS["dark"])


def _theme_entry(name, *, source="variant"):
    theme_name = _theme_name_stem(name)
    user_theme = _load_theme_yaml(theme_name)
    label = str(user_theme.get("label", "")).strip() or _theme_label_from_name(theme_name)
    group = str(user_theme.get("group", "")).strip() or "Other"
    theme = load_theme(theme_name)
    return {
        "name": theme_name,
        "filename": f"{theme_name}.yaml",
        "label": label,
        "group": group,
        "sort": _theme_sort_value(user_theme.get("sort")),
        "source": source,
        "color_scheme": theme_color_scheme(theme),
        "vars": theme_runtime_css_vars(theme),
        "theme_vars": theme_css_vars(theme),
    }


def load_theme_registry():
    """Return the full list of selectable themes."""
    # Preserve selector metadata like label/group/sort/source; the frontend uses
    # it to render the theme chooser declaratively.
    entries = []
    seen = set()
    if _THEME_VARIANT_DIR.exists():
        for theme_path in sorted(_THEME_VARIANT_DIR.glob("*.yaml")):
            if theme_path.name.endswith(".local.yaml"):
                continue
            name = theme_path.stem
            if name in seen:
                continue
            entries.append(_theme_entry(name, source="variant"))
            seen.add(name)
    entries.sort(key=lambda entry: (
        entry.get("sort") is None,
        entry.get("sort") if entry.get("sort") is not None else 0,
        str(entry.get("group", "")),
        str(entry.get("label", "")),
        str(entry.get("name", "")),
    ))
    return entries


THEME_REGISTRY = load_theme_registry()
THEME_REGISTRY_MAP = {}
for entry in THEME_REGISTRY:
    THEME_REGISTRY_MAP[entry["name"]] = entry
    filename = entry.get("filename")
    if filename:
        THEME_REGISTRY_MAP[filename] = entry


def get_theme_entry(name, fallback="dark"):
    """Return a resolved theme registry entry."""
    if name in THEME_REGISTRY_MAP:
        return THEME_REGISTRY_MAP[name]
    if _theme_name_stem(name) in THEME_REGISTRY_MAP:
        return THEME_REGISTRY_MAP[_theme_name_stem(name)]
    if fallback in THEME_REGISTRY_MAP:
        return THEME_REGISTRY_MAP[fallback]
    if _theme_name_stem(fallback) in THEME_REGISTRY_MAP:
        return THEME_REGISTRY_MAP[_theme_name_stem(fallback)]
    return _builtin_theme_entry("dark")

# Scanner user wrapping — prepend sudo to run commands as the unprivileged
# scanner user with the shared appuser group. The explicit run group keeps
# validated workspace files readable/writable without making them world-accessible.
# appuser (Gunicorn) is granted NOPASSWD sudo rights to that runas pair in
# /etc/sudoers. Falls back to running directly if sudo/scanner aren't available
# (local dev).
SCANNER_PREFIX = []
try:
    pwd.getpwnam("scanner")
    # Pass HOME=/tmp explicitly so nuclei (and other tools) use the tmpfs mount
    # for config/cache instead of /home/scanner which doesn't exist on the
    # read-only filesystem.
    SCANNER_PREFIX = ["sudo", "-u", "scanner", "-g", "appuser", "env", "HOME=/tmp"]
except KeyError:
    pass  # scanner user doesn't exist — local dev, run directly
