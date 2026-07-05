"""Diagnostics audit routes for the assets blueprint."""

from __future__ import annotations

import csv
import io
import json as _json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from flask import Response, jsonify, render_template, request, stream_with_context

from blueprints import assets as assets_routes
from blueprints import assets_diag as diag_routes
from config import CFG, get_theme_entry
from core.helpers import current_theme_name
from services.audit.models import AuditTargetType, EVENT_SPECS
from services.audit.queries import AuditEventFilters, list_events
from services.audit.retention import audit_export_max_rows, audit_log_enabled

log = assets_routes.log
assets_bp = assets_routes.assets_bp

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
        for page in assets_routes.iter_event_pages(filters, max_rows=limit):
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
        for page in assets_routes.iter_event_pages(filters, max_rows=limit):
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

@assets_bp.route("/diag/audit")
def diag_audit():
    client_ip = diag_routes._require_diag_access()
    filters = _audit_filters_from_args(request.args)
    limit = diag_routes._diag_bounded_int(request.args.get("limit"), 50, minimum=1, maximum=500)
    offset = diag_routes._diag_bounded_int(request.args.get("offset"), 0, minimum=0, maximum=1_000_000)
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
    client_ip = diag_routes._require_diag_access()
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
