"""
Asset and ops routes: vendor JS/fonts, favicon, and the health-check endpoint.
"""

import logging
import os
from pathlib import Path

from flask import Blueprint, abort, jsonify, send_file

from database import db_connect
from process import redis_client

log = logging.getLogger("shell")

assets_bp = Blueprint("assets", __name__)

_ANSI_UP_PATH = Path("/usr/local/share/shell-assets/js/vendor/ansi_up.js")
_ANSI_UP_FALLBACK = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "ansi_up.js"
_FONT_DIR = Path("/usr/local/share/shell-assets/fonts")
_FONT_FALLBACK_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
_VENDOR_FONT_FILES = frozenset({
    "JetBrainsMono-300.ttf",
    "JetBrainsMono-400.ttf",
    "JetBrainsMono-700.ttf",
    "Syne-700.ttf",
    "Syne-800.ttf",
})


@assets_bp.route("/vendor/ansi_up.js")
def vendor_ansi_up_js():
    """Serve ansi_up from the build-time vendor path, with a repo fallback."""
    if _ANSI_UP_PATH.exists():
        return send_file(_ANSI_UP_PATH, mimetype="application/javascript")
    return send_file(_ANSI_UP_FALLBACK, mimetype="application/javascript")


@assets_bp.route("/vendor/fonts/<path:filename>")
def vendor_fonts(filename):
    """Serve vendored font files from the build-time path, with a repo fallback."""
    if filename not in _VENDOR_FONT_FILES:
        abort(404)
    font_path = _FONT_DIR / filename
    if font_path.exists():
        return send_file(font_path)
    return send_file(_FONT_FALLBACK_DIR / filename)


@assets_bp.route("/favicon.ico")
def favicon():
    return send_file(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "favicon.ico"),
        mimetype="image/x-icon",
    )


@assets_bp.route("/health")
def health():
    """Health check endpoint for Docker HEALTHCHECK and load balancer probes.
    Returns 200 if all critical dependencies are reachable, 503 otherwise."""
    result = {"status": "ok", "db": False, "redis": None}

    # SQLite — critical: app cannot store or serve history without it
    try:
        with db_connect() as conn:
            conn.execute("SELECT 1")
        result["db"] = True
    except Exception:
        result["status"] = "degraded"
        log.error("HEALTH_DB_FAIL", exc_info=True)

    # Redis — checked only if configured; absence is acceptable (falls back to in-process)
    if redis_client:
        try:
            redis_client.ping()
            result["redis"] = True
        except Exception:
            result["redis"] = False
            result["status"] = "degraded"
            log.error("HEALTH_REDIS_FAIL", exc_info=True)

    http_status = 200 if result["status"] == "ok" else 503
    if result["status"] == "ok":
        log.debug("HEALTH_OK")
    else:
        log.warning("HEALTH_DEGRADED", extra={"db": result["db"], "redis": result["redis"]})
    return jsonify(result), http_status
