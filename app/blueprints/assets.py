"""
Asset and ops routes: vendor JS/fonts, favicon, and the health-check endpoint.
"""

import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from commands import command_root, load_allowed_commands
from config import APP_VERSION, CFG, get_theme_entry
from database import db_connect
from helpers import FONT_FILES, current_theme_name, get_client_ip, get_session_id, ip_is_in_cidrs
from process import redis_client

log = logging.getLogger("shell")

assets_bp = Blueprint("assets", __name__)


def _fmt_elapsed(seconds):
    # Diagnostics prefers short operator-readable durations over raw second
    # counts for summary cards and activity tables.
    s = int(seconds or 0)
    if s >= 3600:
        h, m = s // 3600, (s % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"
    if s >= 60:
        m, r = s // 60, s % 60
        return f"{m}m {r}s" if r else f"{m}m"
    return f"{s}s"

_ANSI_UP_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "ansi_up.js"
_JSPDF_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "jspdf.umd.min.js"
_FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
_VENDOR_FONT_FILES = frozenset(filename for _, _, filename in FONT_FILES)


@assets_bp.route("/log", methods=["POST"])
def client_log():
    """Receive client-side error reports and emit them as server log entries."""
    data = request.get_json(silent=True) or {}
    context = str(data.get("context") or "")[:200]
    message = str(data.get("message") or "")[:500]
    log.warning("CLIENT_ERROR", extra={
        "ip": get_client_ip(),
        "session": get_session_id(),
        "context": context,
        "message": message,
    })
    return jsonify({"ok": True})


@assets_bp.route("/vendor/ansi_up.js")
def vendor_ansi_up_js():
    return send_file(_ANSI_UP_JS, mimetype="application/javascript")


@assets_bp.route("/vendor/jspdf.umd.min.js")
def vendor_jspdf_js():
    return send_file(_JSPDF_JS, mimetype="application/javascript")


@assets_bp.route("/vendor/fonts/<path:filename>")
def vendor_fonts(filename):
    """Serve vendored font files; rejects any filename not in the committed manifest."""
    if filename not in _VENDOR_FONT_FILES:
        abort(404)
    return send_file(_FONT_DIR / filename)


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


@assets_bp.route("/diag")
def diag():
    """Operator diagnostics endpoint.

    Returns 404 unless the resolved client IP falls within
    diagnostics_allowed_cidrs. The client IP is resolved through the shared
    trusted-proxy path, so X-Forwarded-For is only honored when the direct
    peer IP is in trusted_proxy_cidrs.

    Enable in config.local.yaml:
        diagnostics_allowed_cidrs:
          - "127.0.0.1/32"
          - "172.16.0.0/12"
    """
    allowed_cidrs = CFG.get("diagnostics_allowed_cidrs") or []
    client_ip = get_client_ip()
    if not ip_is_in_cidrs(client_ip, allowed_cidrs):
        log.warning("DIAG_DENIED", extra={"ip": client_ip, "allowed_cidrs": allowed_cidrs})
        abort(404)

    result: dict = {}

    # ── App ──────────────────────────────────────────────────────────────────
    result["app"] = {
        "version": APP_VERSION,
        "name": CFG.get("app_name", ""),
    }

    # ── Operational config ───────────────────────────────────────────────────
    result["config"] = {
        "rate_limit_enabled":         CFG.get("rate_limit_enabled"),
        "rate_limit_per_minute":      CFG.get("rate_limit_per_minute"),
        "rate_limit_per_second":      CFG.get("rate_limit_per_second"),
        "command_timeout_seconds":    CFG.get("command_timeout_seconds"),
        "heartbeat_interval_seconds": CFG.get("heartbeat_interval_seconds"),
        "max_output_lines":           CFG.get("max_output_lines"),
        "max_tabs":                   CFG.get("max_tabs"),
        "persist_full_run_output":    CFG.get("persist_full_run_output"),
        "full_output_max_mb":         CFG.get("full_output_max_mb"),
        "history_panel_limit":        CFG.get("history_panel_limit"),
        "permalink_retention_days":   CFG.get("permalink_retention_days"),
        "share_redaction_enabled":    CFG.get("share_redaction_enabled"),
        "custom_redaction_rule_count": len(CFG.get("share_redaction_rules") or []),
        "trusted_proxy_cidrs":        CFG.get("trusted_proxy_cidrs", []),
        "log_level":                  CFG.get("log_level"),
        "log_format":                 CFG.get("log_format"),
    }

    # ── Database ─────────────────────────────────────────────────────────────
    db_info: dict = {"ok": False}
    try:
        with db_connect() as conn:
            db_info["runs"] = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            db_info["snapshots"] = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        db_info["ok"] = True
    except Exception as exc:
        db_info["error"] = str(exc)
    result["db"] = db_info

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_info: dict = {"configured": bool(redis_client)}
    if redis_client:
        try:
            redis_client.ping()
            redis_info["ok"] = True
        except Exception as exc:
            redis_info["ok"] = False
            redis_info["error"] = str(exc)
    result["redis"] = redis_info

    # ── Vendor assets ─────────────────────────────────────────────────────────
    result["assets"] = {
        "ansi_up": "loaded" if _ANSI_UP_JS.exists() else "missing",
        "jspdf":   "loaded" if _JSPDF_JS.exists() else "missing",
        "fonts":   "loaded" if _FONT_DIR.exists() and any(_FONT_DIR.iterdir()) else "missing",
    }

    # ── Usage stats ──────────────────────────────────────────────────────────
    stats: dict = {"ok": False}
    if db_info.get("ok"):
        try:
            with db_connect() as conn:
                # Browser passes its UTC offset in minutes via ?tz_offset so
                # calendar boundaries (today, month, year) align with local
                # midnight rather than UTC midnight.
                try:
                    tz_offset_min = int(request.args.get("tz_offset", 0))
                except (TypeError, ValueError):
                    tz_offset_min = 0
                # getTimezoneOffset() returns positive-east convention inverted
                # (UTC-5 → +300), so negate to get a proper UTC offset.
                local_tz = timezone(timedelta(minutes=-tz_offset_min))
                now_local = datetime.now(timezone.utc).astimezone(local_tz)
                fmt = "%Y-%m-%d %H:%M:%S"
                cutoffs = [
                    ("today",      now_local.replace(hour=0, minute=0, second=0, microsecond=0)
                                            .astimezone(timezone.utc).strftime(fmt)),
                    ("this week",  (datetime.now(timezone.utc) - timedelta(days=7)).strftime(fmt)),
                    ("this month", now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                                            .astimezone(timezone.utc).strftime(fmt)),
                    ("this year",  now_local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                                            .astimezone(timezone.utc).strftime(fmt)),
                ]
                activity = []
                for label, cutoff in cutoffs:
                    n = conn.execute(
                        "SELECT COUNT(*) FROM runs WHERE started >= ?",
                        (cutoff,),
                    ).fetchone()[0]
                    activity.append({"label": label, "count": n})
                stats["activity"] = activity

                # Exit-code outcome breakdown
                row = conn.execute(
                    """SELECT
                         SUM(CASE WHEN exit_code = 0                             THEN 1 ELSE 0 END),
                         SUM(CASE WHEN exit_code IS NOT NULL AND exit_code != 0  THEN 1 ELSE 0 END),
                         SUM(CASE WHEN exit_code IS NULL                         THEN 1 ELSE 0 END)
                       FROM runs"""
                ).fetchone()
                stats["outcomes"] = {
                    "success":    row[0] or 0,
                    "failed":     row[1] or 0,
                    "incomplete": row[2] or 0,
                }

                # Top 10 commands by run count
                rows = conn.execute(
                    "SELECT command, COUNT(*) AS n FROM runs"
                    " GROUP BY command ORDER BY n DESC LIMIT 10"
                ).fetchall()
                stats["top_by_freq"] = [{"command": r[0], "count": r[1]} for r in rows]

                # Top 5 longest individual runs
                rows = conn.execute(
                    """SELECT command,
                              ROUND((julianday(finished) - julianday(started)) * 86400) AS elapsed_s
                         FROM runs
                        WHERE finished IS NOT NULL AND started IS NOT NULL
                        ORDER BY elapsed_s DESC
                        LIMIT 5"""
                ).fetchall()
                stats["top_by_duration"] = [
                    {"command": r[0], "elapsed": _fmt_elapsed(r[1])}
                    for r in rows
                ]

            stats["ok"] = True
        except Exception as exc:
            stats["error"] = str(exc)
    result["stats"] = stats

    # ── Tools ─────────────────────────────────────────────────────────────────
    # Collect unique command roots from the allow list and probe each with which().
    allow_prefixes, _ = load_allowed_commands()
    roots: set[str] = set()
    if allow_prefixes is not None:
        for prefix in allow_prefixes:
            root = command_root(prefix)
            if root:
                roots.add(root)
    present = sorted(r for r in roots if shutil.which(r))
    missing = sorted(r for r in roots if not shutil.which(r))
    result["tools"] = {"present": present, "missing": missing}

    log.info("DIAG_VIEWED", extra={"ip": client_ip})

    if request.args.get("format") == "json":
        return jsonify(result)

    current_theme = get_theme_entry(current_theme_name(), fallback=CFG.get("default_theme", "darklab_obsidian.yaml"))
    return render_template(
        "diag.html",
        app_name=CFG.get("app_name", ""),
        data=result,
        current_theme=current_theme,
        current_theme_css=current_theme["vars"],
    )
