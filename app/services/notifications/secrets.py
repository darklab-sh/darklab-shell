"""Notification-channel secret helpers backed by the existing vault."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from services.secrets.storage import (
    emit_secret_upsert_audit,
    get_secret_value_for_env,
    upsert_secret,
    upsert_secret_with_connection,
)

_SAFE_FIELD_RE = re.compile(r"[^A-Z0-9_]+")


def channel_secret_name(channel_id: str, field: str) -> str:
    digest = hashlib.sha256(str(channel_id or "").encode("utf-8")).hexdigest()[:16].upper()
    safe_field = _SAFE_FIELD_RE.sub("_", str(field or "VALUE").upper()).strip("_") or "VALUE"
    return f"NOTIFY_{digest}_{safe_field}"[:64]


def store_channel_secret(session_token: str, channel_id: str, field: str, value: str) -> str:
    secret_name = channel_secret_name(channel_id, field)
    upsert_secret(session_token, secret_name, value, [secret_name])
    return secret_name


def store_channel_secret_with_connection(
    conn,
    session_token: str,
    channel_id: str,
    field: str,
    value: str,
) -> tuple[str, dict, bool]:
    secret_name = channel_secret_name(channel_id, field)
    metadata, created = upsert_secret_with_connection(conn, session_token, secret_name, value, [secret_name])
    return secret_name, metadata, created


def emit_channel_secret_audits(session_token: str, audit_records: list[tuple[dict, bool]]) -> None:
    for metadata, created in audit_records:
        emit_secret_upsert_audit(session_token, metadata, created)


def get_channel_secret(session_token: str, secret_name: str) -> str | None:
    return get_secret_value_for_env(session_token, secret_name)


def first_secret_ref(secrets: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(secrets.get(key) or "").strip()
        if value:
            return value
    return ""
