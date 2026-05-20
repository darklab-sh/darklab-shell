"""Notification-channel secret helpers backed by the existing vault."""

from __future__ import annotations

import hashlib
import re

from services.secrets.storage import get_secret_value_for_env, upsert_secret

_SAFE_FIELD_RE = re.compile(r"[^A-Z0-9_]+")


def channel_secret_name(channel_id: str, field: str) -> str:
    digest = hashlib.sha256(str(channel_id or "").encode("utf-8")).hexdigest()[:16].upper()
    safe_field = _SAFE_FIELD_RE.sub("_", str(field or "VALUE").upper()).strip("_") or "VALUE"
    return f"NOTIFY_{digest}_{safe_field}"[:64]


def store_channel_secret(session_token: str, channel_id: str, field: str, value: str) -> str:
    secret_name = channel_secret_name(channel_id, field)
    upsert_secret(session_token, secret_name, value, [secret_name])
    return secret_name


def get_channel_secret(session_token: str, secret_name: str) -> str | None:
    return get_secret_value_for_env(session_token, secret_name)
