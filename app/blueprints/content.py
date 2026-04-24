"""
Content and config routes: main index, config, themes, FAQ, autocomplete, welcome.
"""

import logging

from flask import Blueprint, Response, jsonify, render_template, request

import config as _config
from commands import (
    load_all_faq,
    load_all_workflows,
    load_allowed_commands,
    load_allowed_commands_grouped,
    load_ascii_art,
    load_ascii_mobile_art,
    load_autocomplete_context,
    load_mobile_welcome_hints,
    load_welcome,
    load_welcome_hints,
)
from fake_commands import get_current_shortcuts, get_special_command_keys
from helpers import get_client_ip, get_log_session_id, ip_is_in_cidrs, resolve_theme

log = logging.getLogger("shell")

content_bp = Blueprint("content", __name__)


def _log_content_view(route: str, **extra):
    log.info(
        "CONTENT_VIEWED",
        extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(),
            "route": route,
            **extra,
        },
    )


def _current_theme_entry():
    name, source = resolve_theme()
    log.debug(
        "THEME_SELECTED",
        extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(),
            "route": request.path,
            "theme": name,
            "source": source,
        },
    )
    return _config.get_theme_entry(
        name,
        fallback=_config.CFG.get("default_theme", "darklab_obsidian.yaml"),
    )


def _request_pref_bool(name: str, default: bool) -> bool:
    raw = (request.cookies.get(name) or "").strip().lower()
    if raw in {"1", "true"}:
        return True
    if raw in {"0", "false"}:
        return False
    return default


def _request_pref_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (request.cookies.get(name) or "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _initial_rail_state():
    return {
        "collapsed": _request_pref_bool("pref_rail_collapsed", False),
        "width": _request_pref_int("pref_rail_width", 214, 180, 360),
        "recent_open": _request_pref_bool("pref_rail_recent_open", True),
        "workflows_open": _request_pref_bool("pref_rail_workflows_open", True),
    }


def _frontend_config_payload():
    """Return the browser-facing config payload derived from server config."""
    cfg = _config.CFG
    return {
        "version":               _config.APP_VERSION,
        "app_name":              cfg["app_name"],
        "project_name":          _config.PROJECT_NAME,
        "prompt_prefix":         cfg["prompt_prefix"],
        "project_readme":        _config.PROJECT_README,
        "default_theme":         cfg["default_theme"],
        "share_redaction_enabled": cfg["share_redaction_enabled"],
        "share_redaction_rules": _config.get_share_redaction_rules(cfg),
        "motd":                  cfg["motd"],
        "recent_commands_limit": cfg["recent_commands_limit"],
        "max_output_lines":      cfg["max_output_lines"],
        "max_tabs":              cfg["max_tabs"],
        "history_panel_limit":      cfg["history_panel_limit"],
        "command_timeout_seconds":  cfg["command_timeout_seconds"],
        "permalink_retention_days": cfg["permalink_retention_days"],
        "welcome_char_ms":          cfg["welcome_char_ms"],
        "welcome_jitter_ms":      cfg["welcome_jitter_ms"],
        "welcome_post_cmd_ms":    cfg["welcome_post_cmd_ms"],
        "welcome_inter_block_ms": cfg["welcome_inter_block_ms"],
        "welcome_first_prompt_idle_ms": cfg["welcome_first_prompt_idle_ms"],
        "welcome_post_status_pause_ms": cfg["welcome_post_status_pause_ms"],
        "welcome_sample_count":   cfg["welcome_sample_count"],
        "welcome_status_labels":  cfg["welcome_status_labels"],
        "welcome_hint_interval_ms": cfg["welcome_hint_interval_ms"],
        "welcome_hint_rotations": cfg["welcome_hint_rotations"],
        "diag_enabled": ip_is_in_cidrs(
            get_client_ip(),
            cfg.get("diagnostics_allowed_cidrs") or [],
        ),
    }


@content_bp.route("/")
def index():
    current_theme = _current_theme_entry()
    log.info(
        "PAGE_LOAD",
        extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(),
            "theme": current_theme["name"],
        },
    )
    return render_template(
        "index.html",
        app_name=_config.CFG["app_name"],
        project_name=_config.PROJECT_NAME,
        version=_config.APP_VERSION,
        project_readme=_config.PROJECT_README,
        initial_rail=_initial_rail_state(),
        prompt_prefix=_config.CFG["prompt_prefix"],
        current_theme=current_theme,
        current_theme_css=current_theme["vars"],
        theme_registry={"current": current_theme, "themes": _config.THEME_REGISTRY},
        fallback_theme_css=_config.theme_runtime_css_vars(_config.DARK_THEME),
        frontend_config=_frontend_config_payload(),
    )


@content_bp.route("/config")
def get_config():
    """Return frontend-relevant config values."""
    payload = _frontend_config_payload()
    _log_content_view("/config", key_count=len(payload))
    return jsonify(payload)


@content_bp.route("/themes")
def get_themes():
    """Return the available theme registry and the active selection."""
    current = _current_theme_entry()
    payload = {
        "current": current,
        "themes": _config.THEME_REGISTRY,
    }
    _log_content_view("/themes", current=current.get("name"), count=len(payload["themes"]))
    return jsonify(payload)


@content_bp.route("/allowed-commands")
def allowed_commands():
    """Return the list of allowed command prefixes for display in the UI."""
    prefixes, _ = load_allowed_commands()
    if prefixes is None:
        _log_content_view("/allowed-commands", restricted=False, count=0)
        return jsonify({"restricted": False, "commands": [], "groups": []})
    groups = load_allowed_commands_grouped() or []
    _log_content_view("/allowed-commands", restricted=True, count=len(prefixes))
    return jsonify({"restricted": True, "commands": prefixes, "groups": groups})


@content_bp.route("/faq")
def faq():
    """Return built-in FAQ entries plus any custom faq.yaml entries."""
    items = load_all_faq(_config.CFG["app_name"], _config.PROJECT_README)
    _log_content_view("/faq", count=len(items))
    return jsonify({"items": items})


@content_bp.route("/workflows")
def workflows():
    """Return built-in workflow entries plus any custom workflows.yaml entries."""
    items = load_all_workflows()
    _log_content_view("/workflows", count=len(items))
    return jsonify({"items": items})


@content_bp.route("/shortcuts")
def shortcuts():
    """Return the keyboard shortcut reference used by the `shortcuts` built-in
    command and the browser-side shortcuts overlay (`?` key).
    """
    payload = get_current_shortcuts()
    total = sum(len(section["items"]) for section in payload["sections"])
    _log_content_view("/shortcuts", count=total)
    return jsonify(payload)


@content_bp.route("/autocomplete")
def autocomplete():
    """Return external-tool autocomplete context from autocomplete.yaml."""
    context = load_autocomplete_context()
    special_commands = get_special_command_keys()
    _log_content_view("/autocomplete")
    return jsonify({"suggestions": [], "context": context, "special_commands": special_commands})


@content_bp.route("/welcome")
def get_welcome():
    """Return welcome message blocks for the startup typeout animation."""
    blocks = load_welcome()
    _log_content_view("/welcome", count=len(blocks))
    return jsonify(blocks)


@content_bp.route("/welcome/ascii")
def get_welcome_ascii():
    """Return the ASCII banner art used by the welcome animation."""
    _log_content_view("/welcome/ascii")
    return Response(load_ascii_art(), mimetype="text/plain")


@content_bp.route("/welcome/ascii-mobile")
def get_welcome_ascii_mobile():
    """Return the compact ASCII banner art used by mobile welcome."""
    _log_content_view("/welcome/ascii-mobile")
    return Response(load_ascii_mobile_art(), mimetype="text/plain")


@content_bp.route("/welcome/hints")
def get_welcome_hints():
    """Return rotating footer hints for the welcome animation."""
    items = load_welcome_hints()
    _log_content_view("/welcome/hints", count=len(items))
    return jsonify({"items": items})


@content_bp.route("/welcome/hints-mobile")
def get_mobile_welcome_hints():
    """Return rotating footer hints for the mobile welcome animation."""
    items = load_mobile_welcome_hints()
    _log_content_view("/welcome/hints-mobile", count=len(items))
    return jsonify({"items": items})
