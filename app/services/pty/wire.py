# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""PTY Redis key and payload wire-format helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("shell")


def stream_key(run_id: str) -> str:
    return f"ptystream:{run_id}"


def control_key(run_id: str) -> str:
    return f"ptycontrol:{run_id}"


def meta_key(run_id: str) -> str:
    return f"ptymeta:{run_id}"


def snapshot_key(run_id: str) -> str:
    return f"ptysnapshot:{run_id}"


def coerce_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def json_payload_size(payload: str) -> int:
    return len(payload.encode("utf-8", errors="replace"))


def is_valid_stream_event_id(event_id: str | None) -> bool:
    try:
        left, right = str(event_id or "").split("-", 1)
        int(left)
        int(right)
    except (TypeError, ValueError):
        return False
    return True


def normalize_event_id(event_id: str | None) -> str:
    if not event_id or event_id in {"-", "0", "0-0"}:
        return "0-0"
    return str(event_id) if is_valid_stream_event_id(str(event_id)) else "0-0"


def log_pty_payload_decode_failed(
    *,
    run_id: str = "",
    event_id: str = "",
    reason: str,
    context: str = "",
) -> None:
    log.warning("PTY_PAYLOAD_DECODE_FAILED", extra={
        "run_id": run_id,
        "event_id": event_id,
        "reason": reason,
        "context": context,
    })


def decode_payload(
    fields: object,
    *,
    run_id: str = "",
    event_id: str = "",
    context: str = "",
) -> dict[str, Any] | None:
    if not isinstance(fields, dict):
        log_pty_payload_decode_failed(run_id=run_id, event_id=event_id, reason="fields_not_dict", context=context)
        return None
    raw = fields.get("payload")
    if raw is None:
        raw = fields.get(b"payload")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        reason = "missing_payload" if raw is None else "payload_not_text"
        log_pty_payload_decode_failed(run_id=run_id, event_id=event_id, reason=reason, context=context)
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        log_pty_payload_decode_failed(run_id=run_id, event_id=event_id, reason="invalid_json", context=context)
        return None
    if not isinstance(payload, dict):
        log_pty_payload_decode_failed(run_id=run_id, event_id=event_id, reason="payload_not_object", context=context)
        return None
    return payload
