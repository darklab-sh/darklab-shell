"""
Asset and ops routes: vendor JS/fonts, favicon, and the health-check endpoint.
"""

import logging
import mimetypes
import os
import shutil  # noqa: F401 - compatibility seam for diagnostics tests.
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from flask import Blueprint, abort, jsonify, request, send_file
from werkzeug.security import safe_join

from services.assets.diagnostics import (
    fmt_diag_duration_ms,
    fmt_elapsed,
    ping_database,
    status_database_state,
)
from services.audit.queries import iter_event_pages  # noqa: F401 - compatibility seam for diagnostics tests.
from services.ai.diagnostics import run_test_prompt as ai_run_test_prompt  # noqa: F401
from core.helpers import (
    FONT_FILES,
    WEB_FONT_FILES,
    get_client_ip,
    get_log_session_id,
)
from core.process import RedisClientProxy

log = logging.getLogger("shell")

assets_bp = Blueprint("assets", __name__)


redis_client = RedisClientProxy()


def _redis_client():
    return redis_client


def _app_metrics():
    from services import metrics as app_metrics  # noqa: PLC0415

    return app_metrics


def _fmt_elapsed(seconds):
    return fmt_elapsed(seconds)


def _fmt_diag_duration_ms(value):
    return fmt_diag_duration_ms(value)


_ANSI_UP_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "ansi_up.js"
_JSPDF_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "jspdf.umd.min.js"
_XTERM_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "xterm.js"
_XTERM_FIT_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "xterm-addon-fit.js"
_XTERM_CSS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "xterm.css"
_FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
_BUILD_DIR = Path(__file__).resolve().parent.parent / "static" / "build"
_VENDOR_FONT_FILES = frozenset(
    filename
    for _, _, filename in [*FONT_FILES, *WEB_FONT_FILES]
)
_PRECOMPRESSED_BUILD_SUFFIXES = (("br", ".br"), ("gzip", ".gz"))
_PRECOMPRESSED_BUILD_EXTENSIONS = frozenset({".css", ".js", ".json", ".svg"})
_APP_BOOT_TIME = time.time()

# Bounds for the /diag Redis snapshot: SCAN with COUNT=500 chunks the work,
# we cap at 5000 keys per prefix and 50 stream-length samples — enough to
# spot uncontrolled growth without holding the operator on a slow page.
_DIAG_REDIS_SCAN_COUNT = 500
_DIAG_REDIS_SCAN_KEY_CAP = 5000
_DIAG_REDIS_STREAM_SAMPLE_CAP = 50
_DIAG_REDIS_ORPHAN_PROBE_CAP = 100
_DIAG_REDIS_KEY_PREFIXES = (
    ("runstream", "runstream:*"),
    ("proc", "proc:*"),
    ("procmeta", "procmeta:*"),
    ("sessionprocs", "sessionprocs:*"),
    ("teamprocs", "teamprocs:*"),
)
_DIAG_CLASSIFIER_LINE_LIMIT = 4096
_DIAG_CLASSIFIER_COMMAND_LIMIT = 512
_DIAG_CLASSIFIER_CLS_LIMIT = 80
_DIAG_CLASSIFIER_CMD_TYPES = frozenset({"real", "builtin"})
_DIAG_AI_TEST_RATE_SECONDS = 60
_DIAG_AI_TEST_LAST_BY_CLIENT: dict[str, float] = {}


def _prune_diag_ai_test_clients(now: float) -> None:
    cutoff = now - _DIAG_AI_TEST_RATE_SECONDS
    stale_clients = [
        client_ip
        for client_ip, last_seen in _DIAG_AI_TEST_LAST_BY_CLIENT.items()
        if last_seen <= cutoff
    ]
    for client_ip in stale_clients:
        _DIAG_AI_TEST_LAST_BY_CLIENT.pop(client_ip, None)


# Themed groupings for the Config card. Every key emitted into
# `result["config"]` must appear in exactly one group, otherwise it is
# invisible on the rendered page (the drift test
# `test_every_config_key_belongs_to_a_group` enforces this).
_DIAG_CONFIG_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Rate limiting", (
        "rate_limit_enabled",
        "http_rate_limit_per_minute",
        "http_rate_limit_per_second",
        "rate_limit_per_minute",
        "rate_limit_per_second",
    )),
    ("Run execution", (
        "command_timeout_seconds",
        "heartbeat_interval_seconds",
        "high_volume_output_line_threshold",
        "high_volume_output_status_interval_lines",
        "interactive_pty_buffer_limit",
        "interactive_pty_control_poll_seconds",
        "interactive_pty_heartbeat_seconds",
        "interactive_pty_input_max_bytes",
        "interactive_pty_snapshot_min_publish_seconds",
        "interactive_pty_snapshot_fallback_entry_limit",
        "interactive_pty_snapshot_publish_bytes",
        "interactive_pty_snapshot_publish_seconds",
        "interactive_pty_stream_fetch_count",
        "interactive_pty_stream_maxlen",
        "max_output_lines",
        "max_tabs",
    )),
    ("Persistence", (
        "persist_full_run_output",
        "full_output_max_mb",
        "history_panel_limit",
        "permalink_retention_days",
    )),
    ("Sharing and redaction", (
        "share_redaction_enabled",
        "custom_redaction_rule_count",
    )),
    ("Network and logging", (
        "trusted_proxy_cidrs",
        "log_level",
        "log_format",
    )),
    ("AI assists", (
        "ai_enabled",
        "ai_provider",
        "ai_base_url_configured",
        "ai_model",
        "ai_connect_timeout_seconds",
        "ai_timeout_seconds",
        "ai_max_input_chars",
        "ai_max_output_tokens",
        "ai_max_concurrent",
        "ai_max_queue_depth",
        "ai_allow_full_output",
        "ai_require_private_base_url",
        "ai_base_url_allowed_cidrs",
        "ai_prompt_version_override",
        "ai_feature_summary",
        "ai_feature_next_commands",
        "ai_feature_run_suggestions",
    )),
)

@assets_bp.route("/log", methods=["POST"])
def client_log():
    """Receive client-side reports and emit them as server log entries."""
    data = request.get_json(silent=True) or {}
    context = str(data.get("context") or "")[:200]
    message = str(data.get("message") or "")[:500]
    event = str(data.get("event") or "CLIENT_ERROR").strip().upper()[:80]
    if not event.replace("_", "").isalnum():
        event = "CLIENT_ERROR"
    level = str(data.get("level") or "warning").strip().lower()
    extra: dict[str, object] = {
        "ip": get_client_ip(),
        "session": get_log_session_id(),
        "context": context,
        "client_message": message,
    }
    details = data.get("details")
    if isinstance(details, dict):
        client_details: dict[str, object] = {}
        selection_key = str(details.get("selection_key") or "")[:80]
        if selection_key:
            client_details["selection_key"] = selection_key
        for key in ("offset", "limit"):
            if key in details:
                try:
                    client_details[key] = max(0, int(details.get(key) or 0))
                except (TypeError, ValueError):
                    client_details[key] = 0
        if isinstance(details.get("filter_fields"), list):
            client_details["filter_fields"] = [
                str(value or "")[:80]
                for value in details["filter_fields"][:20]
                if str(value or "").strip()
            ]
        if isinstance(details.get("filter_active"), dict):
            client_details["filter_active"] = {
                str(key or "")[:80]: bool(value)
                for key, value in list(details["filter_active"].items())[:20]
                if str(key or "").strip()
            }
        if "has_active_filter" in details:
            client_details["has_active_filter"] = bool(details.get("has_active_filter"))
        for key in ("asset_name", "asset_type", "bundle", "page", "phase", "source"):
            value = str(details.get(key) or "").strip()[:120]
            if value:
                client_details[key] = value
        src = _sanitize_client_asset_src(details.get("src"))
        if src:
            client_details["src"] = src
        if "expected_global" in details:
            client_details["expected_global"] = bool(details.get("expected_global"))
        if client_details:
            extra["client_details"] = client_details
    if level == "debug":
        log.debug(event, extra=extra)
    elif level == "error":
        _app_metrics().record_client_error(context or event or "unknown")
        log.error(event, extra=extra)
    else:
        _app_metrics().record_client_error(context or event or "unknown")
        log.warning(event, extra=extra)
    return jsonify({"ok": True})


def _sanitize_client_asset_src(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw.split("?", 1)[0][:300]
    path = parsed.path or raw.split("?", 1)[0]
    query = parse_qs(parsed.query, keep_blank_values=False)
    version = str((query.get("v") or [""])[0] or "")[:80]
    suffix = f"?{urlencode({'v': version})}" if version else ""
    return f"{path[:300]}{suffix}"


def _build_asset_path(filename: str) -> Path:
    if filename.endswith((".br", ".gz")):
        abort(404)
    safe_path = safe_join(str(_BUILD_DIR), filename)
    if not safe_path:
        abort(404)
    path = Path(safe_path)
    if not path.is_file():
        abort(404)
    return path


def _selected_precompressed_build_asset(path: Path) -> tuple[Path, str]:
    if path.suffix not in _PRECOMPRESSED_BUILD_EXTENSIONS:
        return path, ""
    for encoding, suffix in _PRECOMPRESSED_BUILD_SUFFIXES:
        if request.accept_encodings.quality(encoding) <= 0:
            continue
        compressed = Path(f"{path}{suffix}")
        if compressed.is_file():
            return compressed, encoding
    return path, ""


@assets_bp.route("/static/build/<path:filename>")
def static_build_asset(filename):
    path = _build_asset_path(filename)
    selected_path, encoding = _selected_precompressed_build_asset(path)
    mimetype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = send_file(selected_path, mimetype=mimetype, conditional=True)
    if path.suffix in _PRECOMPRESSED_BUILD_EXTENSIONS:
        response.vary.add("Accept-Encoding")
    if encoding:
        response.headers["Content-Encoding"] = encoding
    return response


@assets_bp.route("/vendor/ansi_up.js")
def vendor_ansi_up_js():
    return send_file(_ANSI_UP_JS, mimetype="application/javascript")


@assets_bp.route("/vendor/jspdf.umd.min.js")
def vendor_jspdf_js():
    return send_file(_JSPDF_JS, mimetype="application/javascript")


@assets_bp.route("/vendor/xterm.js")
def vendor_xterm_js():
    return send_file(_XTERM_JS, mimetype="application/javascript")


@assets_bp.route("/vendor/xterm-addon-fit.js")
def vendor_xterm_fit_js():
    return send_file(_XTERM_FIT_JS, mimetype="application/javascript")


@assets_bp.route("/vendor/xterm.css")
def vendor_xterm_css():
    return send_file(_XTERM_CSS, mimetype="text/css")


@assets_bp.route("/vendor/fonts/<path:filename>")
def vendor_fonts(filename):
    """Serve vendored font files; rejects any filename not in the committed manifest."""
    if filename not in _VENDOR_FONT_FILES:
        abort(404)
    return send_file(_FONT_DIR / filename)


@assets_bp.route("/favicon.ico")
def favicon():
    return send_file(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "favicon.svg"),
        mimetype="image/svg+xml",
    )


@assets_bp.route("/health")
def health():
    """Health check endpoint for Docker HEALTHCHECK and load balancer probes.
    Returns 200 if all critical dependencies are reachable, 503 otherwise."""
    result = {"status": "ok", "db": False, "redis": None}

    # SQLite — critical: app cannot store or serve history without it
    try:
        ping_database()
        result["db"] = True
    except Exception:
        result["status"] = "degraded"
        log.error("HEALTH_DB_FAIL", exc_info=True)

    # Redis — checked only if configured; absence is acceptable (falls back to in-process)
    active_redis = _redis_client()
    if active_redis:
        try:
            active_redis.ping()
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


@assets_bp.route("/status")
def status():
    """Lightweight HUD polling endpoint. Always 200 so probes don't flap the UI."""
    uptime_s = int(time.time() - _APP_BOOT_TIME)

    db_state = status_database_state()

    active_redis = _redis_client()
    if active_redis:
        try:
            active_redis.ping()
            redis_state = "ok"
        except Exception:
            redis_state = "down"
    else:
        redis_state = "none"

    return jsonify({
        "uptime": uptime_s,
        "db": db_state,
        "redis": redis_state,
        "server_time": int(time.time() * 1000),
    })

from blueprints import assets_diag as _assets_diag_routes  # noqa: E402,F401
from blueprints import assets_audit as _assets_audit_routes  # noqa: E402,F401


def _diag_fmt_bytes(n) -> str:
    return _assets_diag_routes._diag_fmt_bytes(n)


def _diag_table_storage_breakdown(conn, table_counts: dict[str, int] | None = None) -> dict:
    return _assets_diag_routes._diag_table_storage_breakdown(conn, table_counts)


def _diag_db_stats() -> dict:
    return _assets_diag_routes._diag_db_stats()


def _diag_tool_entry(name: str) -> dict | None:
    return _assets_diag_routes._diag_tool_entry(name)
