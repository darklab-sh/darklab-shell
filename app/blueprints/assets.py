"""
Asset and ops routes: vendor JS/fonts, favicon, and the health-check endpoint.
"""

import json as _json
import logging
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file

from commands import command_root, load_command_policy
from config import APP_VERSION, CFG, get_theme_entry
from database import DB_PATH, db_connect
from helpers import (
    FONT_FILES,
    GRACEFUL_TERMINATION_EXIT_CODE,
    current_theme_name,
    get_client_ip,
    get_log_session_id,
    ip_is_in_cidrs,
)
from process import fallback_pid_snapshot, redis_client
from run_broker import (
    broker_available,
    broker_mode,
    broker_unavailable_reason,
    memory_store_snapshot,
)

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


def _diag_sqlite_identifier(name: str) -> str:
    """Return a safely quoted SQLite identifier for metadata-derived names."""
    value = str(name)
    if not value or "\x00" in value:
        raise ValueError("invalid SQLite identifier")
    return '"' + value.replace('"', '""') + '"'


_ANSI_UP_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "ansi_up.js"
_JSPDF_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "jspdf.umd.min.js"
_XTERM_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "xterm.js"
_XTERM_FIT_JS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "xterm-addon-fit.js"
_XTERM_CSS = Path(__file__).resolve().parent.parent / "static" / "js" / "vendor" / "xterm.css"
_FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
_VENDOR_FONT_FILES = frozenset(filename for _, _, filename in FONT_FILES)
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
)

# Themed groupings for the Config card. Every key emitted into
# `result["config"]` must appear in exactly one group, otherwise it is
# invisible on the rendered page (the drift test
# `test_every_config_key_belongs_to_a_group` enforces this).
_DIAG_CONFIG_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Rate limiting", (
        "rate_limit_enabled",
        "rate_limit_per_minute",
        "rate_limit_per_second",
    )),
    ("Run execution", (
        "command_timeout_seconds",
        "heartbeat_interval_seconds",
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
)


def _diag_fmt_bytes(n) -> str:
    """Short byte size: '12.4 KB', '3.0 MB', etc. Used by the vendor probe."""
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.1f} GB"


def _diag_vendor_probe(url: str) -> dict:
    """In-process HEAD against a vendor URL via the Flask test client.

    Confirms the route is registered AND `send_file` finds the file on
    disk — file-existence on its own would miss a route that has been
    accidentally unregistered, a wrong-path mount, or an unreadable
    symlink. Test-client dispatches in-process (no socket), so this is
    cheap on a desktop and acceptable on a 10s diag refresh.

    `FileNotFoundError` is collapsed to a 404 because `TESTING=True` makes
    Flask propagate the underlying exception out of the test client
    instead of converting it to the 404 response a production worker
    would return.
    """
    info: dict = {"url": url, "ok": False, "status": 0, "size": 0, "size_human": "0 B"}
    try:
        client = current_app.test_client()
        resp = client.head(url)
        size = int(resp.headers.get("Content-Length") or 0)
        info["status"] = int(resp.status_code)
        info["ok"] = resp.status_code == 200
        info["size"] = size
        info["size_human"] = _diag_fmt_bytes(size)
    except FileNotFoundError as exc:
        info["status"] = 404
        info["error"] = str(exc)
    except Exception as exc:
        info["error"] = str(exc)
    return info


def _diag_tool_entry(name: str) -> dict | None:
    """Resolve a command root through `which`.

    Returns None when the binary is missing so callers can route that into the
    Tools card's `missing` list.
    """
    path = shutil.which(name)
    if not path:
        return None
    return {
        "name": name,
        "path": path,
    }


def _diag_decode_key(raw):
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return str(raw)


def _diag_count_keys(client, pattern, cap):
    """Bounded SCAN. Returns (count, capped_flag, sampled_keys)."""
    count = 0
    sampled: list[str] = []
    cursor = 0
    capped = False
    while True:
        try:
            cursor, batch = client.scan(
                cursor=cursor, match=pattern, count=_DIAG_REDIS_SCAN_COUNT,
            )
        except Exception:
            break
        for raw in batch or []:
            count += 1
            if len(sampled) < _DIAG_REDIS_STREAM_SAMPLE_CAP:
                sampled.append(_diag_decode_key(raw))
            if count >= cap:
                capped = True
                cursor = 0
                break
        if not cursor:
            break
    return count, capped, sampled


def _diag_redis_stats(client):
    """Snapshot Redis health beyond a ping: bounded SCAN + INFO sections.

    Each subsection is independently guarded so a single broken probe
    (e.g. INFO denied by an ACL) never blanks the whole panel.
    """
    stats: dict = {}

    t0 = time.perf_counter()
    try:
        client.ping()
    except Exception as exc:
        stats["error"] = str(exc)
        return stats
    stats["ping_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    try:
        stats["dbsize"] = int(client.dbsize() or 0)
    except Exception:
        pass

    namespaces: list[dict] = []
    runstream_sample: list[str] = []
    for label, pattern in _DIAG_REDIS_KEY_PREFIXES:
        count, capped, sampled = _diag_count_keys(client, pattern, _DIAG_REDIS_SCAN_KEY_CAP)
        entry: dict = {"name": label, "count": count}
        if capped:
            entry["capped"] = True
        namespaces.append(entry)
        if label == "runstream":
            runstream_sample = sampled
    stats["namespaces"] = namespaces

    if runstream_sample:
        lengths: list[int] = []
        for key in runstream_sample[:_DIAG_REDIS_STREAM_SAMPLE_CAP]:
            try:
                lengths.append(int(client.xlen(key) or 0))
            except Exception:
                continue
        if lengths:
            lengths.sort()
            stats["stream_length"] = {
                "samples": len(lengths),
                "min": lengths[0],
                "max": lengths[-1],
                "p50": lengths[len(lengths) // 2],
                "p95": lengths[max(0, int(len(lengths) * 0.95) - 1)],
            }

    # Orphan probe: procmeta entries whose session set no longer references
    # them — non-zero means the on-demand reaper isn't catching everything.
    try:
        cursor = 0
        scanned = 0
        orphans = 0
        while scanned < _DIAG_REDIS_ORPHAN_PROBE_CAP:
            cursor, batch = client.scan(
                cursor=cursor, match="procmeta:*", count=_DIAG_REDIS_SCAN_COUNT,
            )
            for raw_key in batch or []:
                if scanned >= _DIAG_REDIS_ORPHAN_PROBE_CAP:
                    break
                scanned += 1
                key = _diag_decode_key(raw_key)
                run_id = key.split(":", 1)[-1]
                try:
                    raw_val = client.get(key)
                except Exception:
                    continue
                if raw_val is None:
                    continue
                try:
                    payload = _json.loads(raw_val)
                except (ValueError, TypeError):
                    continue
                session_id = str(payload.get("session_id") or "")
                if not session_id:
                    orphans += 1
                    continue
                try:
                    if not client.sismember(f"sessionprocs:{session_id}", run_id):
                        orphans += 1
                except Exception:
                    continue
            if not cursor:
                break
        stats["orphans"] = {"probed": scanned, "orphaned": orphans}
    except Exception:
        pass

    try:
        memory = client.info("memory") or {}
        stats["memory"] = {
            "used":          memory.get("used_memory_human"),
            "peak":          memory.get("used_memory_peak_human"),
            "max":           memory.get("maxmemory_human") or "0",
            "fragmentation": memory.get("mem_fragmentation_ratio"),
        }
    except Exception:
        pass
    try:
        persistence = client.info("persistence") or {}
        rdb_last_save = int(persistence.get("rdb_last_save_time") or 0)
        if rdb_last_save:
            age_s = max(0, int(time.time()) - rdb_last_save)
            rdb_last_save_human = f"{_fmt_elapsed(age_s)} ago"
        else:
            rdb_last_save_human = ""
        stats["persistence"] = {
            "aof_enabled":                  bool(persistence.get("aof_enabled")),
            "rdb_last_save":                rdb_last_save,
            "rdb_last_save_human":          rdb_last_save_human,
            "rdb_changes_since_last_save":  int(persistence.get("rdb_changes_since_last_save") or 0),
        }
    except Exception:
        pass
    try:
        info_stats = client.info("stats") or {}
        stats["evicted_keys"] = int(info_stats.get("evicted_keys") or 0)
        stats["expired_keys"] = int(info_stats.get("expired_keys") or 0)
    except Exception:
        pass
    try:
        clients_info = client.info("clients") or {}
        stats["clients"] = {
            "connected": int(clients_info.get("connected_clients") or 0),
            "rejected":  int(clients_info.get("rejected_connections") or 0),
        }
    except Exception:
        pass

    return stats


def _diag_db_stats() -> dict:
    """Snapshot SQLite health beyond a count probe — file/WAL sizes, last
    write, journal mode, freelist (reclaimable bytes), per-table row
    counts, and FTS5 orphan probe. Each subsection is independently
    guarded so a missing pragma or absent FTS table never blanks the
    whole panel.
    """
    info: dict = {}
    db_path = Path(DB_PATH)

    # File-system stats — independent of the connection.
    try:
        st = db_path.stat()
        info["size"] = int(st.st_size)
        info["size_human"] = _diag_fmt_bytes(info["size"])
        info["mtime"] = int(st.st_mtime)
        info["mtime_age_human"] = (
            f"{_fmt_elapsed(int(time.time()) - info['mtime'])} ago"
        )
    except OSError:
        pass

    wal_path = db_path.with_name(db_path.name + "-wal")
    try:
        wal_size = int(wal_path.stat().st_size)
    except OSError:
        wal_size = 0
    info["wal_size"] = wal_size
    info["wal_size_human"] = _diag_fmt_bytes(wal_size)

    # Pragma + table queries — single connection.
    with db_connect() as conn:
        try:
            row = conn.execute("PRAGMA journal_mode").fetchone()
            info["journal_mode"] = str(row[0]) if row else None
        except Exception:
            pass
        try:
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
            freelist = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
            info["page_count"] = page_count
            info["page_size"] = page_size
            info["freelist_count"] = freelist
            info["reclaimable_size"] = freelist * page_size
            info["reclaimable_size_human"] = _diag_fmt_bytes(freelist * page_size)
        except Exception:
            pass

        # Per-table row counts. SQLite stores FTS5 shadow tables
        # (`<vt>_data`, `_idx`, `_content`, `_docsize`, `_config`) under
        # type='table' alongside regular tables, so to exclude them we
        # first find the FTS5 virtual tables and synthesize their shadow
        # names, then filter the table listing against that set.
        try:
            virtual_names = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE sql LIKE 'CREATE VIRTUAL TABLE%'"
                ).fetchall()
            }
            shadow_suffixes = ("_data", "_idx", "_content", "_docsize", "_config")
            shadow_names: set[str] = {
                f"{vname}{suffix}"
                for vname in virtual_names
                for suffix in shadow_suffixes
            }
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
            tables: list[dict] = []
            for (name,) in rows:
                name = str(name)
                if name in shadow_names:
                    continue
                try:
                    table_identifier = _diag_sqlite_identifier(name)
                    # SQLite does not bind table identifiers; names come from
                    # sqlite_master and are quoted/escaped before interpolation.
                    n = conn.execute(
                        "SELECT COUNT(*) FROM " + table_identifier  # nosec B608
                    ).fetchone()[0]
                    tables.append({"name": name, "rows": int(n)})
                except Exception:
                    continue
            info["tables"] = tables
            # Backward-compat: the original /diag schema exposed `runs`
            # and `snapshots` counts at the top level.
            for t in tables:
                if t["name"] == "runs":
                    info["runs"] = t["rows"]
                elif t["name"] == "snapshots":
                    info["snapshots"] = t["rows"]
        except Exception:
            pass

        # FTS5 orphan probe — runs_fts is keyed by the SQLite integer rowid
        # because the virtual table is declared with content_rowid=rowid.
        # runs.id is the user-facing UUID/text primary key and must not be used
        # here or every indexed row appears orphaned.
        # Same operator value as the Redis procmeta orphan probe: surfaces
        # cleanup that has fallen behind.
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM runs_fts "
                "WHERE rowid NOT IN (SELECT rowid FROM runs)"
            ).fetchone()[0]
            info["fts_orphans"] = int(n)
        except Exception:
            pass

    return info


@assets_bp.route("/log", methods=["POST"])
def client_log():
    """Receive client-side error reports and emit them as server log entries."""
    data = request.get_json(silent=True) or {}
    context = str(data.get("context") or "")[:200]
    message = str(data.get("message") or "")[:500]
    log.warning("CLIENT_ERROR", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(),
        "context": context,
        "client_message": message,
    })
    return jsonify({"ok": True})


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


@assets_bp.route("/status")
def status():
    """Lightweight HUD polling endpoint. Always 200 so probes don't flap the UI."""
    uptime_s = int(time.time() - _APP_BOOT_TIME)

    db_state = "down"
    try:
        with db_connect() as conn:
            conn.execute("SELECT 1")
        db_state = "ok"
    except Exception:
        pass

    if redis_client:
        try:
            redis_client.ping()
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
        t0 = time.perf_counter()
        db_info.update(_diag_db_stats())
        db_info["query_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        db_info["ok"] = True
    except Exception as exc:
        db_info["error"] = str(exc)
    result["db"] = db_info

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_info: dict = {"configured": bool(redis_client)}
    if redis_client:
        stats = _diag_redis_stats(redis_client)
        if "error" in stats and "ping_ms" not in stats:
            redis_info["ok"] = False
            redis_info["error"] = stats["error"]
        else:
            redis_info["ok"] = True
            redis_info["stats"] = stats
    result["redis"] = redis_info

    # ── Run broker ────────────────────────────────────────────────────────────
    # Always include broker mode/availability so an operator can tell whether
    # the in-process fallback is in play. The fallback snapshot only attaches
    # when in_process mode is active — otherwise the in-memory maps stay
    # empty regardless of load.
    broker_info: dict = {
        "mode":                broker_mode(),
        "enabled":             bool(CFG.get("run_broker_enabled", True)),
        "requires_redis":      bool(CFG.get("run_broker_require_redis", True)),
        "available":           broker_available(),
        "unavailable_reason":  broker_unavailable_reason(),
    }
    if broker_info["mode"] == "in_process":
        broker_info["fallback"] = {
            **memory_store_snapshot(),
            **fallback_pid_snapshot(),
        }
    result["broker"] = broker_info

    # ── Vendor assets ─────────────────────────────────────────────────────────
    # In-process HEAD probes against the served URLs — file-existence on its
    # own would miss a route that has been accidentally unregistered or a
    # wrong-path bind mount whose symlink resolves locally but breaks under
    # send_file. Fonts probe a single representative file from the manifest.
    font_probe_url = f"/vendor/fonts/{FONT_FILES[0][2]}" if FONT_FILES else ""
    result["assets"] = {
        "ansi_up": _diag_vendor_probe("/vendor/ansi_up.js"),
        "jspdf":   _diag_vendor_probe("/vendor/jspdf.umd.min.js"),
        "fonts":   _diag_vendor_probe(font_probe_url) if font_probe_url else {
            "url": "", "ok": False, "status": 0, "size": 0, "size_human": "0 B",
            "error": "no fonts in manifest",
        },
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
                         SUM(
                             CASE
                                 WHEN exit_code IS NOT NULL AND exit_code != 0 AND exit_code != ?
                                 THEN 1
                                 ELSE 0
                             END
                         ),
                         SUM(CASE WHEN exit_code IS NULL                         THEN 1 ELSE 0 END)
                       FROM runs""",
                    (GRACEFUL_TERMINATION_EXIT_CODE,),
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
    # Present entries carry only the resolved path; mtime-based "staleness" is
    # intentionally avoided because stable system binaries often have old mtimes.
    allow_prefixes, _ = load_command_policy()
    roots: set[str] = set()
    if allow_prefixes is not None:
        for prefix in allow_prefixes:
            root = command_root(prefix)
            if root:
                roots.add(root)
    present_entries: list[dict] = []
    missing: list[str] = []
    for root in sorted(roots):
        entry = _diag_tool_entry(root)
        if entry is None:
            missing.append(root)
        else:
            present_entries.append(entry)
    result["tools"] = {"present": present_entries, "missing": missing}

    log.info("DIAG_VIEWED", extra={"ip": client_ip})

    if request.args.get("format") == "json":
        return jsonify(result)

    current_theme = get_theme_entry(current_theme_name(), fallback=CFG.get("default_theme", "darklab_obsidian.yaml"))
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return render_template(
        "diag.html",
        app_name=CFG.get("app_name", ""),
        data=result,
        config_groups=_DIAG_CONFIG_GROUPS,
        generated_at=generated_at,
        current_theme=current_theme,
        current_theme_css=current_theme["vars"],
    )
