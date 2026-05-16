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
    APP_VERSION,
    CFG,
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
from core.helpers import get_client_ip, get_session_id  # noqa: E402, F401 — get_session_id re-exported
from blueprints.assets import assets_bp  # noqa: E402
from blueprints.atlas import atlas_bp  # noqa: E402
from blueprints.content import content_bp  # noqa: E402
from blueprints.run import run_bp, SUDO_BIN, KILL_BIN  # noqa: E402, F401 — re-exported
from blueprints.history import history_bp  # noqa: E402
from blueprints.session import session_bp  # noqa: E402
from blueprints.secrets import secrets_bp  # noqa: E402
from blueprints.workspace import workspace_bp  # noqa: E402
from blueprints.projects import projects_bp  # noqa: E402
from services.workspace.files import cleanup_inactive_workspaces  # noqa: E402
from services import metrics as app_metrics  # noqa: E402

app = Flask(__name__, template_folder="templates")
app.config["RATELIMIT_ENABLED"] = CFG.get("rate_limit_enabled", True)
limiter.init_app(app)

_WORKSPACE_CLEANUP_INTERVAL_SECONDS = 300
_last_workspace_cleanup_monotonic = 0.0


@app.errorhandler(429)
def _rate_limit_handler(e):
    ip = get_client_ip()
    log.warning("RATE_LIMIT", extra={"ip": ip, "path": request.path, "limit": str(e.description)})
    scope = "secrets" if request.path.startswith("/session/secrets") else "global"
    app_metrics.record_rate_limit_rejection(request.endpoint or "unknown", scope=scope)
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
    log.error("UNHANDLED_EXCEPTION", exc_info=True, extra={"path": request.path})
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
app.register_blueprint(atlas_bp)
app.register_blueprint(content_bp)
app.register_blueprint(run_bp)
app.register_blueprint(history_bp)
app.register_blueprint(session_bp)
app.register_blueprint(secrets_bp)
app.register_blueprint(workspace_bp)
app.register_blueprint(projects_bp)


if __name__ == "__main__":
    # For local development only. In production, Gunicorn is used as the WSGI server
    # via the Dockerfile CMD. Run locally with: python3 app.py
    print("darklab_shell running at http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, threaded=True)  # nosec
