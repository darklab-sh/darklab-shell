# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded operator audit exports with live authorization between pages."""

import csv
import io
import json as _json
import logging
from typing import Any

from flask import Response, stream_with_context
from services.auth.operator_access import OperatorAccessLost, OperatorAccessUnavailable, recheck_access

log = logging.getLogger("shell")


def _authorized_pages(iter_pages, filters, limit):
    pages = iter(iter_pages(filters, max_rows=limit))
    try:
        while True:
            recheck_access()
            page = next(pages, None)
            if page is None:
                return
            recheck_access()
            yield page
    finally:
        close = getattr(pages, "close", None)
        if close:
            close()


def _observe_export(chunks, context):
    completed = False
    reason = "interrupted"
    try:
        yield from chunks
        completed = True
    except (OperatorAccessLost, OperatorAccessUnavailable) as exc:
        unavailable = isinstance(exc, OperatorAccessUnavailable)
        reason = "check_unavailable" if unavailable else "access_lost"
        if context["format"] == "csv":
            yield _audit_csv_row({
                "id": "__access_unavailable__" if unavailable else "__access_lost__",
                "event_type": "export.interrupted",
                "details": (
                    "Export incomplete: operator access could not be checked. Discard this file and retry later."
                    if unavailable else
                    "Export incomplete: operator access was lost. Discard this file and verify access before exporting again."
                ),
            })
        raise
    finally:
        chunks.close()
        if not completed:
            log.warning("DIAG_AUDIT_EXPORT_INTERRUPTED", extra={**context, "reason": reason})


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


def export_csv(filters, *, limit, log_context, iter_pages) -> Response:

    def generate():
        recheck_access()
        truncated = False
        event_count = 0
        yield _audit_csv_header()
        for page in _authorized_pages(iter_pages, filters, limit):
            truncated = bool(page.get("truncated"))
            for event in page["events"]:
                event_count += 1
                yield _audit_export_event_csv_row(event)
        recheck_access()
        if truncated:
            yield _audit_csv_row({
                "id": "__truncated__",
                "event_type": "export.truncated",
                "details": _audit_export_truncation_hint(limit),
            })
        log.info(
            "DIAG_AUDIT_EXPORTED",
            extra={
                "format": "csv",
                "limit": int(limit),
                "event_count": event_count,
                "truncated": truncated,
                **log_context,
            },
        )

    return Response(
        stream_with_context(_observe_export(generate(), {**log_context, "format": "csv", "limit": int(limit)})),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-events.csv"},
    )


def export_json(filters, *, limit, audit_enabled, filter_values, log_context, iter_pages) -> Response:

    def generate():
        recheck_access()
        truncated = False
        event_count = 0
        first = True
        yield "{\n  \"events\": ["
        for page in _authorized_pages(iter_pages, filters, limit):
            truncated = bool(page.get("truncated"))
            for event in page["events"]:
                event_count += 1
                prefix = "\n    " if first else ",\n    "
                first = False
                yield prefix + _json.dumps(event, sort_keys=True)
        recheck_access()
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
                "format": "json",
                "limit": int(limit),
                "event_count": event_count,
                "truncated": truncated,
                **log_context,
            },
        )

    return Response(
        stream_with_context(_observe_export(generate(), {**log_context, "format": "json", "limit": int(limit)})),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=audit-events.json"},
    )
