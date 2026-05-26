#!/usr/bin/env python3
"""
darklab_shell - Real-time bash command execution web app
Run: python3 app.py
Then open http://localhost:8888 or read the README.md for Docker instructions.
"""

import logging
import os
from pathlib import Path
import signal  # noqa: F401 — re-exported for test compatibility
import time

from flask import Flask, jsonify, request

# Logging must be configured before other local imports — process.py
# connects to Redis at module import time and emits log calls then.
from config import (  # noqa: F401 — re-exported for test compatibility
    APP_CONF_DIR,
    APP_VERSION,
    CFG,
    CONFIG_LOAD_WARNINGS,
    DARK_THEME,
    SCANNER_PREFIX,
    THEME_REGISTRY,
    THEME_REGISTRY_MAP,
    get_theme_entry,
    theme_runtime_css_vars,
)
from core.logging_setup import configure_logging
configure_logging(CFG)

log = logging.getLogger("shell")


def _log_loaded_config() -> None:
    for warning in CONFIG_LOAD_WARNINGS:
        log.warning("CONFIG_LOCAL_LOAD_FAILED", extra=dict(warning))
    conf_dir = Path(APP_CONF_DIR) if APP_CONF_DIR else Path(__file__).resolve().parent / "conf"
    log.info(
        "CONFIG_LOADED",
        extra={
            "conf_dir": str(conf_dir),
            "local_overlay": (conf_dir / "config.local.yaml").exists(),
            "database_backend": str(CFG.get("database_backend") or ""),
            "workspace_enabled": bool(CFG.get("workspace_enabled")),
            "log_level": str(CFG.get("log_level") or ""),
            "log_format": str(CFG.get("log_format") or ""),
        },
    )


_log_loaded_config()


def _init_metrics_environment():
    from services.metrics import setup_prometheus_multiproc_dir  # noqa: PLC0415
    path = setup_prometheus_multiproc_dir(CFG)
    os.environ.setdefault("DARKLAB_APP_START_TIME_SECONDS", str(int(time.time())))
    return path


def _warn_workspace_root_config_drift(cfg, environ=None):
    """Warn when container env and app config point at different workspace roots."""
    active_environ = os.environ if environ is None else environ
    env_root = str(active_environ.get("WORKSPACE_ROOT") or "").strip()
    cfg_root = str(cfg.get("workspace_root") or "").strip()
    if not env_root or not cfg_root:
        return
    normalized_env_root = Path(env_root).expanduser().resolve(strict=False)
    normalized_cfg_root = Path(cfg_root).expanduser().resolve(strict=False)
    if normalized_env_root == normalized_cfg_root:
        return
    log.warning(
        "WORKSPACE_ROOT_MISMATCH",
        extra={
            "workspace_root_env": str(normalized_env_root),
            "workspace_root_config": str(normalized_cfg_root),
        },
    )


_warn_workspace_root_config_drift(CFG)
_init_metrics_environment()

# Import blueprints and shared helpers after logging is configured.
from extensions import limiter  # noqa: E402
from core.helpers import get_client_ip, get_log_session_id, get_session_id  # noqa: E402, F401 — re-exported
from blueprints.assets import assets_bp  # noqa: E402
from blueprints.api_v1 import api_v1_bp  # noqa: E402
from blueprints.atlas import atlas_bp  # noqa: E402
from blueprints.content import content_bp  # noqa: E402
from blueprints.run import run_bp, SUDO_BIN, KILL_BIN  # noqa: E402, F401 — re-exported
from blueprints.history import history_bp  # noqa: E402
from blueprints.notifications import notifications_bp  # noqa: E402
from blueprints.schedules import schedules_bp  # noqa: E402
from blueprints.session import session_bp  # noqa: E402
from blueprints.secrets import secrets_bp  # noqa: E402
from blueprints.watchers import watchers_bp  # noqa: E402
from blueprints.workspace import workspace_bp  # noqa: E402
from blueprints.projects import projects_bp  # noqa: E402
from core.process import cleanup_stale_active_run_metadata  # noqa: E402
from services.workspace.files import cleanup_inactive_workspaces  # noqa: E402
from services import metrics as app_metrics  # noqa: E402
from services.api_v1.serialization import json_error  # noqa: E402

app = Flask(__name__, template_folder="templates")
app.config["RATELIMIT_ENABLED"] = CFG.get("rate_limit_enabled", True)
limiter.init_app(app)

_WORKSPACE_CLEANUP_INTERVAL_SECONDS = 300
_last_workspace_cleanup_monotonic = 0.0
_REQUEST_COMPLETED_LOG_SKIP_PREFIXES = ("/static/", "/vendor/")
_REQUEST_COMPLETED_LOG_SKIP_PATHS = frozenset({"/favicon.ico"})
_REQUEST_COMPLETED_LOG_DEBUG_PATHS = frozenset({"/health", "/status"})


def _should_log_request_completed() -> bool:
    path = request.path or ""
    if path in _REQUEST_COMPLETED_LOG_SKIP_PATHS:
        return False
    return not path.startswith(_REQUEST_COMPLETED_LOG_SKIP_PREFIXES)


def _request_completed_log_level(status_code: int) -> int | None:
    if not _should_log_request_completed():
        return None
    path = request.path or ""
    if path in _REQUEST_COMPLETED_LOG_DEBUG_PATHS and 200 <= status_code < 400:
        return logging.DEBUG
    return logging.INFO


def _cleanup_active_run_metadata_on_startup():
    try:
        result = cleanup_stale_active_run_metadata()
    except Exception:
        log.exception("ACTIVE_RUN_METADATA_STARTUP_CLEANUP_ERROR")
        return
    removed = int(result.get("metadata_removed", 0) or 0)
    members = int(result.get("session_members_removed", 0) or 0)
    if removed or members:
        log.info("ACTIVE_RUN_METADATA_STARTUP_CLEANUP", extra={
            "metadata_removed": removed,
            "session_members_removed": members,
        })


_cleanup_active_run_metadata_on_startup()


@app.errorhandler(429)
def _rate_limit_handler(e):
    ip = get_client_ip()
    scope = "secrets" if request.path.startswith("/session/secrets") else "global"
    log.warning("RATE_LIMIT", extra={
        "ip": ip,
        "path": request.path,
        "limit": str(e.description),
        "scope": scope,
    })
    app_metrics.record_rate_limit_rejection(request.endpoint or "unknown", scope=scope)
    if request.path.startswith("/api/v1/"):
        return jsonify(json_error("rate_limited", "Rate limit exceeded. Please slow down.")), 429
    if request.path.startswith("/session/secrets"):
        retry_after = None
        limit = getattr(e, "limit", None)
        limit_item = getattr(limit, "limit", None)
        if limit_item and hasattr(limit_item, "get_expiry"):
            retry_after = int(limit_item.get_expiry())
        return jsonify({"error": "rate_limited", "retry_after": retry_after}), 429
    return jsonify({"error": "Rate limit exceeded. Please slow down."}), 429


@app.errorhandler(500)
def _server_error_handler(e):
    app_metrics.record_unhandled_exception(request.endpoint or "unknown")
    try:
        session_for_log = get_log_session_id(get_session_id())
    except Exception:
        session_for_log = ""
    log.error("UNHANDLED_EXCEPTION", exc_info=True, extra={
        "ip": get_client_ip(),
        "session": session_for_log,
        "method": request.method,
        "path": request.path,
        "status": 500,
    })
    if request.path.startswith("/api/v1/"):
        return jsonify(json_error("internal_error", "Internal server error.")), 500
    return jsonify({"error": "Internal server error"}), 500


@app.before_request
def _run_periodic_workspace_cleanup():
    _maybe_cleanup_workspaces()


def _maybe_cleanup_workspaces():
    global _last_workspace_cleanup_monotonic
    if not CFG.get("workspace_enabled"):
        return
    now = time.monotonic()
    if now - _last_workspace_cleanup_monotonic < _WORKSPACE_CLEANUP_INTERVAL_SECONDS:
        return
    _last_workspace_cleanup_monotonic = now
    try:
        removed = cleanup_inactive_workspaces(CFG, skip_session_id=get_session_id())
        if removed:
            log.info("WORKSPACE_CLEANUP", extra={"removed": removed})
    except Exception:
        log.exception("WORKSPACE_CLEANUP_ERROR")


@app.before_request
def _log_request():
    request.environ["darklab_metrics_start"] = str(time.perf_counter())
    if log.isEnabledFor(logging.DEBUG):
        ip = get_client_ip()
        extra: dict = {"ip": ip, "method": request.method, "path": request.path}
        if request.query_string:
            extra["qs"] = request.query_string.decode(errors="replace")
        log.debug("REQUEST", extra=extra)


@app.after_request
def _log_response(response):
    started = request.environ.get("darklab_metrics_start")
    try:
        elapsed = time.perf_counter() - float(started) if started else 0.0
    except (TypeError, ValueError):
        elapsed = 0.0
    app_metrics.record_http_request(
        request.method,
        request.endpoint or "unknown",
        response.status_code,
        elapsed,
    )
    request_completed_level = _request_completed_log_level(response.status_code)
    if request_completed_level is not None and log.isEnabledFor(request_completed_level):
        log_method = log.debug if request_completed_level <= logging.DEBUG else log.info
        log_method(
            "REQUEST_COMPLETED",
            extra={
                "ip": get_client_ip(),
                "session": get_log_session_id(),
                "method": request.method,
                "path": request.path,
                "endpoint": request.endpoint or "unknown",
                "status": response.status_code,
                "duration_ms": int(elapsed * 1000),
            },
        )
    if log.isEnabledFor(logging.DEBUG):
        ip    = get_client_ip()
        extra = {
            "ip": ip, "method": request.method,
            "path": request.path, "status": response.status_code,
        }
        if response.content_length is not None:
            extra["size"] = response.content_length
        log.debug("RESPONSE", extra=extra)
    return response


app.register_blueprint(assets_bp)
app.register_blueprint(api_v1_bp)
app.register_blueprint(atlas_bp)
app.register_blueprint(content_bp)
app.register_blueprint(run_bp)
app.register_blueprint(history_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(schedules_bp)
app.register_blueprint(session_bp)
app.register_blueprint(secrets_bp)
app.register_blueprint(watchers_bp)
app.register_blueprint(workspace_bp)
app.register_blueprint(projects_bp)

log.info("APP_INITIALIZED", extra={
    "version": APP_VERSION,
    "database_backend": str(CFG.get("database_backend") or "sqlite"),
    "workspace_enabled": bool(CFG.get("workspace_enabled")),
})


if __name__ == "__main__":
    # For local development only. In production, Gunicorn is used as the WSGI server
    # via the Dockerfile CMD. Run locally with: python3 app.py
    print("darklab_shell running at http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, threaded=True)  # nosec
