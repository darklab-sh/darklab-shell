# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Diagnostics and metrics routes for the assets blueprint."""

from __future__ import annotations

import json as _json
from datetime import datetime, timezone

from flask import abort, current_app, jsonify, render_template, request

from blueprints import assets as assets_routes
from config import APP_VERSION, CFG, get_theme_entry
from core.helpers import FONT_FILES, WEB_FONT_FILES, current_theme_name, get_client_ip, ip_is_in_cidrs
from core.output_signals import OutputSignalClassifier, strip_ansi_codes
from core.process import fallback_pid_snapshot
from services.assets.diagnostics import (
    classifier_drift_report_from_db,
    diag_database_stats,
    diag_table_storage_breakdown,
    diag_usage_stats,
    format_bytes as _storage_fmt_bytes,
)
from services.ai.client import AIClientError
from services.ai.diagnostics import provider_probe as ai_provider_probe
from services.commands.registry import command_root, load_command_policy
from services.commands.raw_packets import raw_packet_diagnostics
from services.runs.broker import broker_available, broker_mode, broker_unavailable_reason, memory_store_snapshot
from services.runs.output_model import line_event_from_legacy

log = assets_routes.log
assets_bp = assets_routes.assets_bp
_DIAG_AI_TEST_LAST_BY_CLIENT = assets_routes._DIAG_AI_TEST_LAST_BY_CLIENT
_DIAG_AI_TEST_RATE_SECONDS = assets_routes._DIAG_AI_TEST_RATE_SECONDS
_DIAG_CLASSIFIER_CLS_LIMIT = assets_routes._DIAG_CLASSIFIER_CLS_LIMIT
_DIAG_CLASSIFIER_CMD_TYPES = assets_routes._DIAG_CLASSIFIER_CMD_TYPES
_DIAG_CLASSIFIER_COMMAND_LIMIT = assets_routes._DIAG_CLASSIFIER_COMMAND_LIMIT
_DIAG_CLASSIFIER_LINE_LIMIT = assets_routes._DIAG_CLASSIFIER_LINE_LIMIT
_DIAG_CONFIG_GROUPS = assets_routes._DIAG_CONFIG_GROUPS
_DIAG_REDIS_KEY_PREFIXES = assets_routes._DIAG_REDIS_KEY_PREFIXES
_DIAG_REDIS_ORPHAN_PROBE_CAP = assets_routes._DIAG_REDIS_ORPHAN_PROBE_CAP
_DIAG_REDIS_SCAN_COUNT = assets_routes._DIAG_REDIS_SCAN_COUNT
_DIAG_REDIS_SCAN_KEY_CAP = assets_routes._DIAG_REDIS_SCAN_KEY_CAP
_DIAG_REDIS_STREAM_SAMPLE_CAP = assets_routes._DIAG_REDIS_STREAM_SAMPLE_CAP
_prune_diag_ai_test_clients = assets_routes._prune_diag_ai_test_clients

def _require_diag_access() -> str:
    allowed_cidrs = CFG.get("diagnostics_allowed_cidrs") or []
    client_ip = get_client_ip()
    if not ip_is_in_cidrs(client_ip, allowed_cidrs):
        log.warning("DIAG_DENIED", extra={"ip": client_ip, "allowed_cidrs": allowed_cidrs})
        abort(404)
    return client_ip


def _diag_fmt_bytes(n) -> str:
    """Short byte size: '12.4 KB', '3.0 MB', etc. Used by the vendor probe."""
    return _storage_fmt_bytes(n)


def _diag_row_value(row, key: str, index: int, default=None):
    from services.assets.diagnostics import row_value

    return row_value(row, key, index, default)


def _diag_table_storage_breakdown(conn, table_counts: dict[str, int] | None = None) -> dict:
    """Return table/index storage diagnostics for /diag.

    This is an occasional operator probe, not a hot path. The shared
    diagnostics service owns the backend-specific row counts, dbstat/catalog
    probes, largest-run hints, and short-lived cache used by /diag and
    Prometheus scrapes.
    """
    return diag_table_storage_breakdown(conn, table_counts)

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
    path = assets_routes.shutil.which(name)
    if not path:
        return None
    return {
        "name": name,
        "path": path,
    }


def _diag_bounded_int(value, default: int, *, minimum: int = 0, maximum: int = 500) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))

def _diag_classifier_inspector(args) -> dict:
    line = str(args.get("classifier_line", ""))[:_DIAG_CLASSIFIER_LINE_LIMIT]
    command = str(args.get("classifier_command", ""))[:_DIAG_CLASSIFIER_COMMAND_LIMIT]
    legacy_cls = str(args.get("classifier_cls", ""))[:_DIAG_CLASSIFIER_CLS_LIMIT]
    cmd_type = str(args.get("classifier_cmd_type", "real")).strip().lower()
    if cmd_type not in _DIAG_CLASSIFIER_CMD_TYPES:
        cmd_type = "real"
    submitted = any(key in args for key in (
        "classifier_line",
        "classifier_command",
        "classifier_cls",
        "classifier_cmd_type",
    ))
    payload: dict = {
        "submitted": submitted,
        "line": line,
        "command": command,
        "cls": legacy_cls,
        "cmd_type": cmd_type,
        "result": None,
    }
    if not submitted or not line.strip():
        return payload

    classifier = OutputSignalClassifier(
        command,
        cmd_type=cmd_type,
        extra_domain_suffixes=CFG.get("output_entity_extra_domain_suffixes", []),
    )
    metadata = classifier.classify_line(line, cls=legacy_cls)
    base_event = line_event_from_legacy(line, legacy_cls)
    role = str(metadata.get("role") or base_event.role.value)
    raw_signals = metadata.get("signals")
    signals = [str(signal) for signal in raw_signals if str(signal)] if isinstance(raw_signals, list) else []
    raw_entities = metadata.get("entities")
    entities = [
        entity
        for entity in raw_entities
        if isinstance(entity, dict)
    ] if isinstance(raw_entities, list) else []
    raw_line_index = metadata.get("line_index")
    line_index = raw_line_index if isinstance(raw_line_index, int) and not isinstance(raw_line_index, bool) else 0
    payload["result"] = {
        "kind": base_event.kind.value,
        "role": role,
        "signals": signals,
        "entities": entities,
        "line_index": line_index,
        "command_root": str(metadata.get("command_root") or ""),
        "target": str(metadata.get("target") or ""),
        "normalized_text": strip_ansi_codes(line).strip(),
    }
    return payload


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
        except Exception as exc:
            log.warning(
                "DIAG_REDIS_SCAN_INCOMPLETE",
                extra={
                    "stage": "key_scan",
                    "pattern": pattern,
                    "count": count,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
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

    t0 = assets_routes.time.perf_counter()
    try:
        client.ping()
    except Exception as exc:
        stats["error"] = str(exc)
        return stats
    stats["ping_ms"] = round((assets_routes.time.perf_counter() - t0) * 1000, 2)

    try:
        stats["dbsize"] = int(client.dbsize() or 0)
    except Exception as exc:
        log.warning("DIAG_REDIS_SCAN_INCOMPLETE", extra={"stage": "dbsize", "error": str(exc)})

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
            except Exception as exc:
                log.debug("DIAG_REDIS_SCAN_KEY_FAILED", extra={"stage": "stream_length", "error": str(exc)})
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
        cleaned = 0
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
                except Exception as exc:
                    log.debug("DIAG_REDIS_SCAN_KEY_FAILED", extra={"stage": "orphan_get", "error": str(exc)})
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
                    session_key = f"sessionprocs:{session_id}"
                    if not client.sismember(session_key, run_id):
                        orphans += 1
                        proc_key = f"proc:{run_id}"
                        if client.get(proc_key) is None:
                            client.delete(key, proc_key)
                            client.srem(session_key, run_id)
                            cleaned += 1
                except Exception as exc:
                    log.debug("DIAG_REDIS_SCAN_KEY_FAILED", extra={"stage": "orphan_membership", "error": str(exc)})
                    continue
            if not cursor:
                break
        stats["orphans"] = {"probed": scanned, "orphaned": orphans}
        if cleaned:
            stats["orphans"]["cleaned"] = cleaned
    except Exception as exc:
        log.warning("DIAG_REDIS_SCAN_INCOMPLETE", extra={"stage": "orphan_probe", "error": str(exc)})

    try:
        memory = client.info("memory") or {}
        stats["memory"] = {
            "used":          memory.get("used_memory_human"),
            "peak":          memory.get("used_memory_peak_human"),
            "max":           memory.get("maxmemory_human") or "0",
            "fragmentation": memory.get("mem_fragmentation_ratio"),
        }
    except Exception as exc:
        log.debug("DIAG_REDIS_INFO_SECTION_FAILED", extra={
            "section": "memory",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
    try:
        persistence = client.info("persistence") or {}
        rdb_last_save = int(persistence.get("rdb_last_save_time") or 0)
        if rdb_last_save:
            age_s = max(0, int(assets_routes.time.time()) - rdb_last_save)
            rdb_last_save_human = f"{assets_routes._fmt_elapsed(age_s)} ago"
        else:
            rdb_last_save_human = ""
        stats["persistence"] = {
            "aof_enabled":                  bool(persistence.get("aof_enabled")),
            "rdb_last_save":                rdb_last_save,
            "rdb_last_save_human":          rdb_last_save_human,
            "rdb_changes_since_last_save":  int(persistence.get("rdb_changes_since_last_save") or 0),
        }
    except Exception as exc:
        log.debug("DIAG_REDIS_INFO_SECTION_FAILED", extra={
            "section": "persistence",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
    try:
        info_stats = client.info("stats") or {}
        stats["evicted_keys"] = int(info_stats.get("evicted_keys") or 0)
        stats["expired_keys"] = int(info_stats.get("expired_keys") or 0)
    except Exception as exc:
        log.debug("DIAG_REDIS_INFO_SECTION_FAILED", extra={
            "section": "stats",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
    try:
        clients_info = client.info("clients") or {}
        stats["clients"] = {
            "connected": int(clients_info.get("connected_clients") or 0),
            "rejected":  int(clients_info.get("rejected_connections") or 0),
        }
    except Exception as exc:
        log.debug("DIAG_REDIS_INFO_SECTION_FAILED", extra={
            "section": "clients",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })

    return stats


def _diag_db_stats() -> dict:
    """Snapshot database health without letting optional probes blank the panel."""
    return diag_database_stats()

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
    client_ip = _require_diag_access()
    result: dict = {}
    # ── App ──────────────────────────────────────────────────────────────────
    result["app"] = {
        "version": APP_VERSION,
        "name": CFG.get("app_name", ""),
    }
    # ── Operational config ───────────────────────────────────────────────────
    result["config"] = {
        "rate_limit_enabled":         CFG.get("rate_limit_enabled"),
        "http_rate_limit_per_minute": CFG.get("http_rate_limit_per_minute"),
        "http_rate_limit_per_second": CFG.get("http_rate_limit_per_second"),
        "rate_limit_per_minute":      CFG.get("rate_limit_per_minute"),
        "rate_limit_per_second":      CFG.get("rate_limit_per_second"),
        "command_timeout_seconds":    CFG.get("command_timeout_seconds"),
        "raw_packet_scanning_enabled": CFG.get("raw_packet_scanning_enabled"),
        "heartbeat_interval_seconds": CFG.get("heartbeat_interval_seconds"),
        "high_volume_output_line_threshold": CFG.get("high_volume_output_line_threshold"),
        "high_volume_output_status_interval_lines": CFG.get("high_volume_output_status_interval_lines"),
        "max_output_lines":           CFG.get("max_output_lines"),
        "max_tabs":                   CFG.get("max_tabs"),
        "interactive_pty_buffer_limit": CFG.get("interactive_pty_buffer_limit"),
        "interactive_pty_control_poll_seconds": CFG.get("interactive_pty_control_poll_seconds"),
        "interactive_pty_heartbeat_seconds": CFG.get("interactive_pty_heartbeat_seconds"),
        "interactive_pty_input_max_bytes": CFG.get("interactive_pty_input_max_bytes"),
        "interactive_pty_snapshot_min_publish_seconds": CFG.get("interactive_pty_snapshot_min_publish_seconds"),
        "interactive_pty_snapshot_fallback_entry_limit": CFG.get("interactive_pty_snapshot_fallback_entry_limit"),
        "interactive_pty_snapshot_publish_bytes": CFG.get("interactive_pty_snapshot_publish_bytes"),
        "interactive_pty_snapshot_publish_seconds": CFG.get("interactive_pty_snapshot_publish_seconds"),
        "interactive_pty_stream_fetch_count": CFG.get("interactive_pty_stream_fetch_count"),
        "interactive_pty_stream_maxlen": CFG.get("interactive_pty_stream_maxlen"),
        "persist_full_run_output":    CFG.get("persist_full_run_output"),
        "full_output_max_mb":         CFG.get("full_output_max_mb"),
        "history_panel_limit":        CFG.get("history_panel_limit"),
        "permalink_retention_days":   CFG.get("permalink_retention_days"),
        "share_redaction_enabled":    CFG.get("share_redaction_enabled"),
        "custom_redaction_rule_count": len(CFG.get("share_redaction_rules") or []),
        "trusted_proxy_cidrs":        CFG.get("trusted_proxy_cidrs", []),
        "log_level":                  CFG.get("log_level"),
        "log_format":                 CFG.get("log_format"),
        "ai_enabled":                 CFG.get("ai_enabled"),
        "ai_provider":                CFG.get("ai_provider"),
        "ai_base_url_configured":     bool(CFG.get("ai_base_url")),
        "ai_model":                   CFG.get("ai_model"),
        "ai_connect_timeout_seconds": CFG.get("ai_connect_timeout_seconds"),
        "ai_timeout_seconds":         CFG.get("ai_timeout_seconds"),
        "ai_max_input_chars":         CFG.get("ai_max_input_chars"),
        "ai_max_output_tokens":       CFG.get("ai_max_output_tokens"),
        "ai_max_concurrent":          CFG.get("ai_max_concurrent"),
        "ai_max_queue_depth":         CFG.get("ai_max_queue_depth"),
        "ai_allow_full_output":       CFG.get("ai_allow_full_output"),
        "ai_require_private_base_url": CFG.get("ai_require_private_base_url"),
        "ai_base_url_allowed_cidrs":  CFG.get("ai_base_url_allowed_cidrs", []),
        "ai_prompt_version_override": CFG.get("ai_prompt_version_override"),
        "ai_feature_summary":         CFG.get("ai_feature_summary"),
        "ai_feature_next_commands":   CFG.get("ai_feature_next_commands"),
        "ai_feature_run_suggestions": CFG.get("ai_feature_run_suggestions"),
    }
    result["raw_packets"] = raw_packet_diagnostics(CFG)

    # ── AI assists ───────────────────────────────────────────────────────────
    result["ai"] = ai_provider_probe()

    # ── Database ─────────────────────────────────────────────────────────────
    db_info: dict = {"ok": False}
    try:
        t0 = assets_routes.time.perf_counter()
        db_info.update(_diag_db_stats())
        probe_ms = round((assets_routes.time.perf_counter() - t0) * 1000, 2)
        db_info["probe_ms"] = probe_ms
        db_info["probe_human"] = assets_routes._fmt_diag_duration_ms(probe_ms)
        # Backward-compatible alias for callers that still read the original
        # field. The top card now labels this as the full diagnostics probe.
        db_info["query_ms"] = probe_ms
        db_info["ok"] = True
    except Exception as exc:
        db_info["error"] = str(exc)
    result["db"] = db_info

    # ── Redis ─────────────────────────────────────────────────────────────────
    active_redis = assets_routes._redis_client()
    redis_info: dict = {"configured": bool(active_redis)}
    if active_redis:
        stats = _diag_redis_stats(active_redis)
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

    # ── Interactive PTY ──────────────────────────────────────────────────────
    result["pty"] = assets_routes._app_metrics().pty_metrics_snapshot()

    # ── Vendor assets ─────────────────────────────────────────────────────────
    # In-process HEAD probes against the served URLs — file-existence on its
    # own would miss a route that has been accidentally unregistered or a
    # wrong-path bind mount whose symlink resolves locally but breaks under
    # send_file. Fonts probe a single representative file from the manifest.
    font_probe_files = WEB_FONT_FILES or FONT_FILES
    font_probe_url = f"/vendor/fonts/{font_probe_files[0][2]}" if font_probe_files else ""
    result["assets"] = {
        "ansi_up": _diag_vendor_probe("/vendor/ansi_up.js"),
        "jspdf":   _diag_vendor_probe("/vendor/jspdf.umd.min.js"),
        "fonts":   _diag_vendor_probe(font_probe_url) if font_probe_url else {
            "url": "", "ok": False, "status": 0, "size": 0, "size_human": "0 B",
            "error": "no fonts in manifest",
        },
    }

    # ── Classifier inspector ─────────────────────────────────────────────────
    result["classifier_inspector"] = _diag_classifier_inspector(request.args)

    # ── Usage stats ──────────────────────────────────────────────────────────
    stats: dict = {"ok": False}
    if db_info.get("ok"):
        stats = diag_usage_stats(request.args.get("tz_offset", 0))
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

@assets_bp.route("/diag/classifier-inspector")
def diag_classifier_inspector():
    _require_diag_access()
    return jsonify(_diag_classifier_inspector(request.args))


@assets_bp.route("/diag/classifier-drift")
def diag_classifier_drift():
    _require_diag_access()
    try:
        report = classifier_drift_report_from_db(
            run_limit=request.args.get("runs"),
            line_limit=request.args.get("lines"),
            command_root_filter=request.args.get("root"),
            include_full=request.args.get("include_full"),
        )
    except Exception as exc:
        log.warning("CLASSIFIER_DRIFT_REPORT_FAILED", exc_info=True, extra={"reason": type(exc).__name__})
        report = {"ok": False, "error": str(exc)}
    return jsonify(report)


@assets_bp.route("/diag/ai-test", methods=["POST"])
def diag_ai_test():
    client_ip = _require_diag_access()
    now = assets_routes.time.monotonic()
    _prune_diag_ai_test_clients(now)
    last = _DIAG_AI_TEST_LAST_BY_CLIENT.get(client_ip, 0.0)
    if now - last < _DIAG_AI_TEST_RATE_SECONDS:
        return jsonify({
            "ok": False,
            "error_code": "ai_rate_limited",
            "error": "AI test prompt is limited to once per minute per diagnostics client.",
        }), 429
    _DIAG_AI_TEST_LAST_BY_CLIENT[client_ip] = now
    try:
        payload = assets_routes.ai_run_test_prompt()
    except AIClientError as exc:
        assets_routes._app_metrics().record_ai_request(
            "diag_test",
            "error",
            0.0,
            error_code=exc.code,
            provider=CFG.get("ai_provider", "openai_compatible"),
        )
        log.warning(
            "AI_DIAG_TEST_FAILED",
            extra={
                "ip": client_ip,
                "provider": CFG.get("ai_provider", "openai_compatible"),
                "model": CFG.get("ai_model", ""),
                "error_code": exc.code,
                "status": exc.status,
            },
        )
        return jsonify({"ok": False, "error_code": exc.code, "error": str(exc)}), 502
    return jsonify(payload)


@assets_bp.route("/metrics")
def metrics():
    """Prometheus scrape endpoint, hidden behind the diagnostics IP gate."""
    if not CFG.get("metrics_enabled", True):
        abort(404)
    allowed_cidrs = CFG.get("diagnostics_allowed_cidrs") or []
    client_ip = get_client_ip()
    if not ip_is_in_cidrs(client_ip, allowed_cidrs):
        log.warning("METRICS_DENIED", extra={"ip": client_ip, "allowed_cidrs": allowed_cidrs})
        abort(404)

    from services.metrics import PROMETHEUS_CONTENT_TYPE, render_latest_metrics  # noqa: PLC0415
    return current_app.response_class(
        render_latest_metrics(),
        content_type=PROMETHEUS_CONTENT_TYPE,
    )
