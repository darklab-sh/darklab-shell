"""
Asset and ops routes: vendor JS/fonts, favicon, and the health-check endpoint.
"""

import csv
import io
import json as _json
import logging
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request, send_file, stream_with_context

from services.commands.registry import command_root, load_command_policy
from config import APP_VERSION, CFG, get_theme_entry
from core.database import DB_BACKEND, DB_PATH, db_connect
from core.database_backend import (
    DatabaseBackend,
    sqlite_journal_mode,
    sqlite_page_stats,
)
from services.diagnostics.storage import (
    PROJECT_WORKSPACE_COUNT_TABLES as _DIAG_PROJECT_WORKSPACE_COUNT_TABLES,
    format_bytes as _storage_fmt_bytes,
    storage_snapshot,
    table_storage_breakdown,
)
from services.audit.models import AuditTargetType, EVENT_SPECS
from services.audit.queries import AuditEventFilters, iter_event_pages, list_events
from services.audit.retention import audit_export_max_rows, audit_log_enabled, maybe_prune_events
from services.diagnostics.classifier_drift import classifier_drift_report
from services.ai.client import AIClientError
from services.ai.diagnostics import provider_probe as ai_provider_probe, run_test_prompt as ai_run_test_prompt
from core.output_signals import OutputSignalClassifier, strip_ansi_codes
from core.helpers import (
    FONT_FILES,
    GRACEFUL_TERMINATION_EXIT_CODE,
    current_theme_name,
    get_client_ip,
    get_log_session_id,
    ip_is_in_cidrs,
)
from core.process import fallback_pid_snapshot, redis_client
from services.runs.broker import (
    broker_available,
    broker_mode,
    broker_unavailable_reason,
    memory_store_snapshot,
)
from services.runs.output_model import line_event_from_legacy
from services import metrics as app_metrics

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


def _fmt_diag_duration_ms(value):
    ms = float(value or 0)
    if ms >= 1000:
        seconds = ms / 1000
        if seconds >= 10:
            return f"{seconds:.0f}s"
        return f"{seconds:.1f}s"
    if ms >= 100:
        return f"{ms:.0f} ms"
    return f"{ms:g} ms"


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
    if hasattr(row, "keys"):
        try:
            return row[key]
        except KeyError:
            pass
    try:
        return row[index]
    except (IndexError, KeyError, TypeError):
        return default


def _diag_table_storage_breakdown(conn, table_counts: dict[str, int] | None = None) -> dict:
    """Return table/index storage diagnostics for /diag.

    This is an occasional operator probe, not a hot path. The shared
    diagnostics service owns the backend-specific row counts, dbstat/catalog
    probes, largest-run hints, and short-lived cache used by /diag and
    Prometheus scrapes.
    """
    return table_storage_breakdown(conn, DB_BACKEND, table_counts)

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


def _diag_bounded_int(value, default: int, *, minimum: int = 0, maximum: int = 500) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _audit_filters_from_args(args) -> AuditEventFilters:
    return AuditEventFilters(
        event_type=str(args.get("event_type", "") or "").strip(),
        actor=str(args.get("actor", "") or "").strip(),
        actor_member_id=str(args.get("actor_member_id", "") or "").strip(),
        actor_session_hash=str(args.get("actor_session_hash", "") or "").strip(),
        owner_session_hash=str(args.get("owner_session_hash", "") or "").strip(),
        session_id=str(args.get("session_id", "") or "").strip(),
        team_id=str(args.get("team_id", "") or "").strip(),
        project_id=str(args.get("project_id", "") or "").strip(),
        target_type=str(args.get("target_type", "") or "").strip(),
        target_id=str(args.get("target_id", "") or "").strip(),
        correlation_id=str(args.get("correlation_id", "") or "").strip(),
        date_from=str(args.get("date_from", "") or "").strip(),
        date_to=str(args.get("date_to", "") or "").strip(),
    )


def _audit_filter_values(filters: AuditEventFilters) -> dict[str, str]:
    return {
        "event_type": filters.event_type,
        "actor": filters.actor,
        "actor_member_id": filters.actor_member_id,
        "actor_session_hash": filters.actor_session_hash,
        "owner_session_hash": filters.owner_session_hash,
        "session_id": filters.session_id,
        "team_id": filters.team_id,
        "project_id": filters.project_id,
        "target_type": filters.target_type,
        "target_id": filters.target_id,
        "correlation_id": filters.correlation_id,
        "date_from": filters.date_from,
        "date_to": filters.date_to,
    }


_AUDIT_LOG_FILTER_VALUE_KEYS = frozenset({
    "event_type",
    "actor_member_id",
    "actor_session_hash",
    "owner_session_hash",
    "team_id",
    "project_id",
    "target_type",
    "target_id",
    "correlation_id",
    "date_from",
    "date_to",
})


def _audit_log_filter_context(filters: AuditEventFilters) -> dict[str, Any]:
    active_filters = {
        key: str(value or "").strip()
        for key, value in _audit_filter_values(filters).items()
        if str(value or "").strip()
    }
    safe_values = {
        key: active_filters[key][:128]
        for key in sorted(active_filters)
        if key in _AUDIT_LOG_FILTER_VALUE_KEYS
    }
    return {
        "filter_count": len(active_filters),
        "filter_keys": sorted(active_filters),
        "filter_values": safe_values,
    }


_AUDIT_EVENT_ACTION_HINTS = {
    "build": "build",
    "change": "change",
    "config_change": "config change",
    "create": "creation",
    "delete": "deletion",
    "invite": "invite",
    "issue": "ticket issue",
    "join": "join",
    "link": "link",
    "preview": "preview",
    "reactivate": "reactivation",
    "redeem": "ticket use",
    "remediation_edit": "remediation edit",
    "member_remove": "member removal",
    "move": "move",
    "accept_baseline": "baseline acceptance",
    "recovery_redeem": "recovery-code redemption",
    "recovery_rotate": "recovery-code rotation",
    "review_change": "review change",
    "revoke": "revoke",
    "role_change": "role change",
    "rotate": "rotation",
    "run_now": "manual run",
    "suppress": "suppression",
    "unlink": "unlink",
    "update": "update",
    "use": "use",
    "verification_edit": "verification edit",
    "write": "write",
}


def _audit_event_type_options() -> list[dict[str, str]]:
    options = []
    for event_type in sorted(EVENT_SPECS):
        spec = EVENT_SPECS[event_type]
        action = event_type.split(".", 1)[-1]
        hint = _AUDIT_EVENT_ACTION_HINTS.get(action, action.replace("_", " "))
        options.append({
            "value": event_type,
            "label": f"{event_type} - {spec.target_type.value.replace('_', ' ')} {hint}",
            "target_type": spec.target_type.value,
        })
    return options


def _audit_query_string(filters: AuditEventFilters, *, limit: int | None = None, offset: int | None = None) -> str:
    values: dict[str, str | int] = {
        key: value
        for key, value in _audit_filter_values(filters).items()
        if str(value or "").strip()
    }
    if limit is not None:
        values["limit"] = limit
    if offset is not None and offset > 0:
        values["offset"] = offset
    return urlencode(values)


def _audit_target_href(event: dict) -> str:
    target_type = str(event.get("target_type") or "")
    target_id = str(event.get("target_id") or "")
    if not target_id:
        return ""
    if target_type == AuditTargetType.RUN.value and target_id:
        return f"/history/{target_id}"
    if target_type == AuditTargetType.SNAPSHOT.value and target_id:
        return f"/share/{target_id}"
    return ""


def _audit_project_href(event: dict) -> str:
    return ""


def _audit_event_detail_payload(event: dict) -> dict[str, Any]:
    return {
        "id": event.get("id") or "",
        "created": event.get("created") or "",
        "event_type": event.get("event_type") or "",
        "actor": {
            "display_name": event.get("actor_display_name") or "",
            "member_id": event.get("actor_member_id") or "",
            "role": event.get("actor_role") or "",
            "session": event.get("actor_session_label") or "",
        },
        "scope": {
            "kind": "team" if event.get("team_id") else "personal",
            "team_id": event.get("team_id") or "",
            "project_id": event.get("project_id") or "",
        },
        "target": {
            "type": event.get("target_type") or "",
            "id": event.get("target_id") or "",
            "href": event.get("target_href") or "",
        },
        "job": {
            "id": event.get("job_id") or "",
            "correlation_id": event.get("correlation_id") or "",
        },
        "details": event.get("details") or {},
    }


def _decorate_audit_events(events: list[dict]) -> list[dict]:
    decorated = []
    for event in events:
        row = dict(event)
        row["target_href"] = _audit_target_href(row)
        row["project_href"] = _audit_project_href(row)
        row["details_json"] = _json.dumps(_audit_event_detail_payload(row), indent=2, sort_keys=True)
        decorated.append(row)
    return decorated


_AUDIT_EXPORT_FIELDNAMES = [
    "id",
    "created",
    "event_type",
    "target_type",
    "target_id",
    "project_id",
    "actor_member_id",
    "actor_display_name",
    "actor_session_label",
    "team_id",
    "correlation_id",
    "job_id",
    "details",
]


def _audit_csv_row(payload: dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_AUDIT_EXPORT_FIELDNAMES)
    writer.writerow(payload)
    return output.getvalue()


def _audit_csv_header() -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_AUDIT_EXPORT_FIELDNAMES)
    writer.writeheader()
    return output.getvalue()


def _audit_export_event_csv_row(event: dict) -> str:
    return _audit_csv_row({
        key: _json.dumps(event.get("details") or {}, sort_keys=True) if key == "details" else event.get(key, "")
        for key in _AUDIT_EXPORT_FIELDNAMES
    })


def _audit_export_truncation_hint(limit: int) -> str:
    return f"Export capped at {int(limit)} rows. Narrow the filters to include older matching rows."


def _audit_export_csv(filters: AuditEventFilters, *, limit: int, client_ip: str) -> Response:
    log_context = _audit_log_filter_context(filters)

    def generate():
        truncated = False
        event_count = 0
        yield _audit_csv_header()
        for page in iter_event_pages(filters, max_rows=limit):
            truncated = bool(page.get("truncated"))
            for event in page["events"]:
                event_count += 1
                yield _audit_export_event_csv_row(event)
        if truncated:
            yield _audit_csv_row({
                "id": "__truncated__",
                "event_type": "export.truncated",
                "details": _audit_export_truncation_hint(limit),
            })
        log.info(
            "DIAG_AUDIT_EXPORTED",
            extra={
                "ip": client_ip,
                "format": "csv",
                "limit": int(limit),
                "event_count": event_count,
                "truncated": truncated,
                **log_context,
            },
        )

    return Response(
        stream_with_context(generate()),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-events.csv"},
    )


def _audit_export_json(filters: AuditEventFilters, *, limit: int, client_ip: str, audit_enabled: bool) -> Response:
    filter_values = _audit_filter_values(filters)
    log_context = _audit_log_filter_context(filters)

    def generate():
        truncated = False
        event_count = 0
        first = True
        yield "{\n  \"events\": ["
        for page in iter_event_pages(filters, max_rows=limit):
            truncated = bool(page.get("truncated"))
            for event in page["events"]:
                event_count += 1
                prefix = "\n    " if first else ",\n    "
                first = False
                yield prefix + _json.dumps(event, sort_keys=True)
        yield "\n  ],\n"
        yield f"  \"filters\": {_json.dumps(filter_values, sort_keys=True)},\n"
        yield f"  \"limit\": {int(limit)},\n"
        yield f"  \"truncated\": {_json.dumps(truncated)},\n"
        yield f"  \"truncation_hint\": {_json.dumps(_audit_export_truncation_hint(limit) if truncated else '')},\n"
        yield f"  \"audit_log_enabled\": {_json.dumps(bool(audit_enabled))}\n"
        yield "}\n"
        log.info(
            "DIAG_AUDIT_EXPORTED",
            extra={
                "ip": client_ip,
                "format": "json",
                "limit": int(limit),
                "event_count": event_count,
                "truncated": truncated,
                **log_context,
            },
        )

    return Response(
        stream_with_context(generate()),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=audit-events.json"},
    )


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

    classifier = OutputSignalClassifier(command, cmd_type=cmd_type)
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
    """Snapshot database health without letting optional probes blank the panel."""
    info: dict = {}
    info["backend"] = DB_BACKEND.value
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        with db_connect() as conn:
            t0 = time.perf_counter()
            conn.execute("SELECT 1").fetchone()
            info["ping_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            info["ping_human"] = _fmt_diag_duration_ms(info["ping_ms"])
            try:
                snapshot = storage_snapshot(conn, DB_BACKEND, db_path=str(DB_PATH))
                table_counts = snapshot["table_counts"]
                info["tables"] = snapshot["tables"]
                info["runs"] = table_counts.get("runs", 0)
                info["snapshots"] = table_counts.get("snapshots", 0)
                info["project_workspace"] = {
                    label: table_counts.get(table_name, 0)
                    for table_name, label in _DIAG_PROJECT_WORKSPACE_COUNT_TABLES.items()
                }
                info["storage"] = snapshot["storage"]
                info["dbstat_available"] = bool(info["storage"].get("dbstat_available"))
                info["storage_stats_available"] = bool(info["storage"].get("storage_stats_available"))
                info["size"] = int(snapshot.get("size") or 0)
                info["size_human"] = snapshot.get("size_human") or _diag_fmt_bytes(info["size"])
            except Exception:
                pass
        return info

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
            t0 = time.perf_counter()
            conn.execute("SELECT 1").fetchone()
            info["ping_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            info["ping_human"] = _fmt_diag_duration_ms(info["ping_ms"])
        except Exception:
            pass
        try:
            info["journal_mode"] = sqlite_journal_mode(conn)
        except Exception:
            pass
        try:
            page_stats = sqlite_page_stats(conn)
            page_count = page_stats["page_count"]
            page_size = page_stats["page_size"]
            freelist = page_stats["freelist_count"]
            info["page_count"] = page_count
            info["page_size"] = page_size
            info["freelist_count"] = freelist
            info["reclaimable_size"] = freelist * page_size
            info["reclaimable_size_human"] = _diag_fmt_bytes(freelist * page_size)
        except Exception:
            pass

        snapshot: dict = {}

        # Per-table row counts. SQLite stores FTS5 shadow tables
        # (`<vt>_data`, `_idx`, `_content`, `_docsize`, `_config`) under
        # type='table' alongside regular tables, so to exclude them we
        # first find the FTS5 virtual tables and synthesize their shadow
        # names, then filter the table listing against that set.
        try:
            snapshot = storage_snapshot(conn, DB_BACKEND, db_path=str(DB_PATH))
            info["tables"] = snapshot["tables"]
            # Backward-compat: the original /diag schema exposed `runs`
            # and `snapshots` counts at the top level.
            table_counts = snapshot["table_counts"]
            for t in snapshot["tables"]:
                if t["name"] == "runs":
                    info["runs"] = t["rows"]
                elif t["name"] == "snapshots":
                    info["snapshots"] = t["rows"]
            project_counts = {
                label: table_counts.get(table_name, 0)
                for table_name, label in _DIAG_PROJECT_WORKSPACE_COUNT_TABLES.items()
            }
            info["project_workspace"] = project_counts
            info["storage"] = snapshot["storage"]
            info["dbstat_available"] = bool(info["storage"].get("dbstat_available"))
            info["storage_stats_available"] = bool(info["storage"].get("storage_stats_available"))
        except Exception:
            pass

        # FTS5 orphan probe — runs_fts is keyed by the SQLite integer rowid
        # because the virtual table is declared with content_rowid=rowid.
        # runs.id is the user-facing UUID/text primary key and must not be used
        # here or every indexed row appears orphaned.
        # Same operator value as the Redis procmeta orphan probe: surfaces
        # cleanup that has fallen behind.
        try:
            info["fts_orphans"] = int(snapshot.get("fts_orphans") or 0)
        except Exception:
            pass

    return info


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
    from services import metrics as app_metrics  # noqa: PLC0415
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
        if client_details:
            extra["client_details"] = client_details
    if level == "debug":
        log.debug(event, extra=extra)
    elif level == "error":
        app_metrics.record_client_error(context or event or "unknown")
        log.error(event, extra=extra)
    else:
        app_metrics.record_client_error(context or event or "unknown")
        log.warning(event, extra=extra)
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
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "favicon.ico"),
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
            try:
                maybe_prune_events(conn=conn)
                conn.commit()
            except Exception:
                rollback = getattr(conn, "rollback", None)
                if callable(rollback):
                    rollback()
                log.warning("AUDIT_RETENTION_PERIODIC_PRUNE_FAILED", exc_info=True)
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

    # ── AI assists ───────────────────────────────────────────────────────────
    result["ai"] = ai_provider_probe()

    # ── Database ─────────────────────────────────────────────────────────────
    db_info: dict = {"ok": False}
    try:
        t0 = time.perf_counter()
        db_info.update(_diag_db_stats())
        probe_ms = round((time.perf_counter() - t0) * 1000, 2)
        db_info["probe_ms"] = probe_ms
        db_info["probe_human"] = _fmt_diag_duration_ms(probe_ms)
        # Backward-compatible alias for callers that still read the original
        # field. The top card now labels this as the full diagnostics probe.
        db_info["query_ms"] = probe_ms
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

    # ── Interactive PTY ──────────────────────────────────────────────────────
    result["pty"] = app_metrics.pty_metrics_snapshot()

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

    # ── Classifier inspector ─────────────────────────────────────────────────
    result["classifier_inspector"] = _diag_classifier_inspector(request.args)

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
                    row = conn.execute(
                        "SELECT COUNT(*) AS count FROM runs WHERE started >= ?",
                        (cutoff,),
                    ).fetchone()
                    n = _diag_row_value(row, "count", 0, 0)
                    activity.append({"label": label, "count": n})
                stats["activity"] = activity

                # Exit-code outcome breakdown
                row = conn.execute(
                    """SELECT
                         SUM(CASE WHEN exit_code = 0                             THEN 1 ELSE 0 END) AS success,
                         SUM(
                             CASE
                                 WHEN exit_code IS NOT NULL AND exit_code != 0 AND exit_code != ?
                                 THEN 1
                                 ELSE 0
                             END
                         ) AS failed,
                         SUM(CASE WHEN exit_code IS NULL                         THEN 1 ELSE 0 END) AS incomplete
                       FROM runs""",
                    (GRACEFUL_TERMINATION_EXIT_CODE,),
                ).fetchone()
                stats["outcomes"] = {
                    "success":    _diag_row_value(row, "success", 0, 0) or 0,
                    "failed":     _diag_row_value(row, "failed", 1, 0) or 0,
                    "incomplete": _diag_row_value(row, "incomplete", 2, 0) or 0,
                }

                # Top 10 commands by run count
                rows = conn.execute(
                    "SELECT command, COUNT(*) AS n FROM runs"
                    " GROUP BY command ORDER BY n DESC LIMIT 10"
                ).fetchall()
                stats["top_by_freq"] = [
                    {
                        "command": _diag_row_value(row, "command", 0, ""),
                        "count": _diag_row_value(row, "n", 1, 0),
                    }
                    for row in rows
                ]

                # Top 5 longest individual runs
                if DB_BACKEND == DatabaseBackend.POSTGRES:
                    duration_sql = """SELECT command,
                                             ROUND(EXTRACT(EPOCH FROM (
                                                 finished::timestamptz - started::timestamptz
                                             ))) AS elapsed_s
                                        FROM runs
                                       WHERE finished IS NOT NULL AND started IS NOT NULL
                                       ORDER BY elapsed_s DESC
                                       LIMIT 5"""
                else:
                    duration_sql = """SELECT command,
                                             ROUND((julianday(finished) - julianday(started)) * 86400) AS elapsed_s
                                        FROM runs
                                       WHERE finished IS NOT NULL AND started IS NOT NULL
                                       ORDER BY elapsed_s DESC
                                       LIMIT 5"""
                rows = conn.execute(duration_sql).fetchall()
                stats["top_by_duration"] = [
                    {
                        "command": _diag_row_value(row, "command", 0, ""),
                        "elapsed": _fmt_elapsed(_diag_row_value(row, "elapsed_s", 1, 0)),
                    }
                    for row in rows
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


@assets_bp.route("/diag/audit")
def diag_audit():
    client_ip = _require_diag_access()
    filters = _audit_filters_from_args(request.args)
    limit = _diag_bounded_int(request.args.get("limit"), 50, minimum=1, maximum=500)
    offset = _diag_bounded_int(request.args.get("offset"), 0, minimum=0, maximum=1_000_000)
    payload = list_events(filters, limit=limit, offset=offset)
    result = {
        "events": _decorate_audit_events(payload["events"]),
        "filters": _audit_filter_values(filters),
        "limit": payload["limit"],
        "offset": payload["offset"],
        "has_more": payload["has_more"],
        "previous_query": _audit_query_string(filters, limit=limit, offset=max(0, offset - limit)),
        "next_query": _audit_query_string(filters, limit=limit, offset=offset + limit),
        "export_query": _audit_query_string(filters),
        "audit_log_enabled": audit_log_enabled(),
        "export_max_rows": audit_export_max_rows(),
        "event_types": sorted(EVENT_SPECS),
        "event_type_options": _audit_event_type_options(),
        "target_types": sorted(item.value for item in AuditTargetType),
    }
    log.info(
        "DIAG_AUDIT_VIEWED",
        extra={
            "ip": client_ip,
            "limit": payload["limit"],
            "offset": payload["offset"],
            "event_count": len(payload["events"]),
            "has_more": payload["has_more"],
            "audit_log_enabled": bool(result["audit_log_enabled"]),
            **_audit_log_filter_context(filters),
        },
    )
    if request.args.get("format") == "json":
        return jsonify(result)

    current_theme = get_theme_entry(current_theme_name(), fallback=CFG.get("default_theme", "darklab_obsidian.yaml"))
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return render_template(
        "diag_audit.html",
        app_name=CFG.get("app_name", ""),
        data=result,
        generated_at=generated_at,
        current_theme=current_theme,
        current_theme_css=current_theme["vars"],
    )


@assets_bp.route("/diag/audit/export")
def diag_audit_export():
    client_ip = _require_diag_access()
    filters = _audit_filters_from_args(request.args)
    max_rows = audit_export_max_rows()
    if request.args.get("format") == "json":
        return _audit_export_json(
            filters,
            limit=max_rows,
            client_ip=client_ip,
            audit_enabled=audit_log_enabled(),
        )
    return _audit_export_csv(filters, limit=max_rows, client_ip=client_ip)


@assets_bp.route("/diag/classifier-inspector")
def diag_classifier_inspector():
    _require_diag_access()
    return jsonify(_diag_classifier_inspector(request.args))


@assets_bp.route("/diag/classifier-drift")
def diag_classifier_drift():
    _require_diag_access()
    try:
        with db_connect() as conn:
            report = classifier_drift_report(
                conn,
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
    now = time.monotonic()
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
        payload = ai_run_test_prompt()
    except AIClientError as exc:
        app_metrics.record_ai_request(
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
