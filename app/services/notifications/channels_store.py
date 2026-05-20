"""Session-owned notification channel CRUD helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
from typing import Any

from core import database
from core.database_backend import dialect_for_backend
from services.notifications import dispatcher
from services.notifications.base import channel_class_for_kind
from services.notifications.models import (
    CHANNEL_KIND_DISCORD,
    CHANNEL_KIND_EMAIL,
    CHANNEL_KIND_PUSHOVER,
    CHANNEL_KIND_SLACK,
    CHANNEL_KIND_TELEGRAM,
    CHANNEL_KIND_WEBHOOK,
    CHANNEL_KINDS,
    TRIGGER_RUN_COMPLETE,
    TRIGGER_TEST,
    TRIGGERS,
    NotificationChannel,
    require_durable_session_token,
)
from services.notifications.payloads import build_test_payload
from services.notifications.secrets import channel_secret_name, store_channel_secret
from services.secrets.storage import delete_secret
from services.secrets.vault import MasterKeyError, SecretDecryptError

CHANNEL_SECRET_FIELDS = {
    CHANNEL_KIND_WEBHOOK: ("url",),
    CHANNEL_KIND_SLACK: ("url",),
    CHANNEL_KIND_DISCORD: ("url",),
    CHANNEL_KIND_TELEGRAM: ("bot_token",),
    CHANNEL_KIND_PUSHOVER: ("app_token", "user_key"),
    CHANNEL_KIND_EMAIL: (),
}

CHANNEL_CONFIG_FIELDS = {
    CHANNEL_KIND_WEBHOOK: ("timeout_seconds",),
    CHANNEL_KIND_SLACK: ("timeout_seconds",),
    CHANNEL_KIND_DISCORD: ("timeout_seconds",),
    CHANNEL_KIND_TELEGRAM: ("chat_id", "timeout_seconds"),
    CHANNEL_KIND_PUSHOVER: ("priority", "sound", "device", "timeout_seconds"),
    CHANNEL_KIND_EMAIL: ("recipients", "reply_to", "timeout_seconds"),
}

UI_TRIGGERS = tuple(sorted(TRIGGERS - {TRIGGER_TEST}))
DEFAULT_TRIGGERS = (TRIGGER_RUN_COMPLETE,)
MAX_LABEL_LENGTH = 80


class NotificationChannelError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _channel_id() -> str:
    return f"ntc_{uuid.uuid4().hex[:24]}"


def _json_param(value: Any) -> Any:
    return dialect_for_backend(database.DB_BACKEND).json_param(value)


def _loads_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _channel_rows(conn, session_token: str) -> list[Any]:
    return conn.execute(
        "SELECT id, session_token, kind, label, secrets_json, config_json, triggers_json, muted, created, updated "
        "FROM notification_channels WHERE session_token = ? ORDER BY updated DESC",
        (session_token,),
    ).fetchall()


def _get_channel(conn, session_token: str, channel_id: str) -> NotificationChannel:
    row = conn.execute(
        "SELECT id, session_token, kind, label, secrets_json, config_json, triggers_json, muted, created, updated "
        "FROM notification_channels WHERE session_token = ? AND id = ?",
        (session_token, channel_id),
    ).fetchone()
    if row is None:
        raise NotificationChannelError("not_found", "Notification channel not found.", status_code=404)
    return NotificationChannel.from_row(row)


def _normalize_kind(value: Any) -> str:
    kind = str(value or "").strip().lower()
    if kind not in CHANNEL_KINDS:
        raise NotificationChannelError("invalid_kind", "Choose a supported notification channel type.")
    return kind


def _normalize_label(value: Any, *, kind: str) -> str:
    label = str(value or "").strip()
    if not label:
        label = kind.title()
    return label[:MAX_LABEL_LENGTH]


def _normalize_triggers(value: Any) -> tuple[str, ...]:
    raw_values = value if isinstance(value, list) else DEFAULT_TRIGGERS
    normalized: list[str] = []
    for item in raw_values:
        trigger = str(item or "").strip()
        if trigger == TRIGGER_TEST:
            continue
        if trigger not in UI_TRIGGERS:
            raise NotificationChannelError("invalid_trigger", "Choose supported notification triggers.")
        if trigger not in normalized:
            normalized.append(trigger)
    if not normalized:
        normalized = list(DEFAULT_TRIGGERS)
    normalized.append(TRIGGER_TEST)
    return tuple(normalized)


def _normalize_config(kind: str, raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    allowed = set(CHANNEL_CONFIG_FIELDS[kind])
    config: dict[str, Any] = {}
    for key in allowed:
        value = source.get(key)
        if key == "recipients":
            if isinstance(value, list):
                recipients = [str(item).strip() for item in value if str(item or "").strip()]
            else:
                recipients = [item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()]
            if recipients:
                config[key] = recipients
            continue
        if value is None:
            continue
        text = str(value).strip()
        if text:
            config[key] = text
    return config


def _secret_values(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if str(value or "")}


def _secret_refs_for_values(channel_id: str, kind: str, raw_secret_values: Any) -> dict[str, str]:
    values = _secret_values(raw_secret_values)
    allowed = set(CHANNEL_SECRET_FIELDS[kind])
    return {
        field: channel_secret_name(channel_id, field)
        for field in allowed
        if field in values
    }


def _store_secret_values(session_token: str, channel_id: str, kind: str, raw_secret_values: Any) -> None:
    values = _secret_values(raw_secret_values)
    allowed = set(CHANNEL_SECRET_FIELDS[kind])
    for field in allowed:
        if field in values:
            store_channel_secret(session_token, channel_id, field, values[field])


def _validate_channel(channel: NotificationChannel) -> None:
    channel_cls = channel_class_for_kind(channel.kind)
    if channel_cls is None:
        raise NotificationChannelError("invalid_kind", "Notification channel type is not registered.")
    errors = channel_cls(channel).validate_config(channel.config)
    if errors:
        raise NotificationChannelError("invalid_config", "; ".join(errors))


def _serialize_channel(channel: NotificationChannel) -> dict[str, Any]:
    secret_fields = tuple(CHANNEL_SECRET_FIELDS[channel.kind])
    return {
        "id": channel.id,
        "kind": channel.kind,
        "label": channel.label,
        "config": channel.config,
        "triggers": [trigger for trigger in channel.triggers if trigger != TRIGGER_TEST],
        "secret_fields": [
            {"name": field, "configured": bool(str(channel.secrets.get(field) or "").strip())}
            for field in secret_fields
        ],
        "muted": channel.muted,
        "created": channel.created,
        "updated": channel.updated,
    }


def list_notification_channels(session_token: str) -> list[dict[str, Any]]:
    session_token = require_durable_session_token(session_token)
    with database.db_connect() as conn:
        return [_serialize_channel(NotificationChannel.from_row(row)) for row in _channel_rows(conn, session_token)]


def create_notification_channel(session_token: str, data: dict[str, Any]) -> dict[str, Any]:
    session_token = require_durable_session_token(session_token)
    kind = _normalize_kind(data.get("kind"))
    channel_id = _channel_id()
    now = _utc_now()
    secrets = _secret_refs_for_values(channel_id, kind, data.get("secret_values"))
    channel = NotificationChannel(
        id=channel_id,
        session_token=session_token,
        kind=kind,
        label=_normalize_label(data.get("label"), kind=kind),
        secrets=secrets,
        config=_normalize_config(kind, data.get("config")),
        triggers=_normalize_triggers(data.get("triggers")),
        muted=bool(data.get("muted")),
        created=now,
        updated=now,
    )
    _validate_channel(channel)
    _store_secret_values(session_token, channel_id, kind, data.get("secret_values"))
    with database.db_connect() as conn:
        conn.execute(
            "INSERT INTO notification_channels "
            "(id, session_token, kind, label, secrets_json, config_json, triggers_json, muted, created, updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                channel.id,
                channel.session_token,
                channel.kind,
                channel.label,
                _json_param(channel.secrets),
                _json_param(channel.config),
                _json_param(list(channel.triggers)),
                dialect_for_backend(database.DB_BACKEND).boolean_param(channel.muted),
                channel.created,
                channel.updated,
            ),
        )
        conn.commit()
    return _serialize_channel(channel)


def update_notification_channel(session_token: str, channel_id: str, data: dict[str, Any]) -> dict[str, Any]:
    session_token = require_durable_session_token(session_token)
    with database.db_connect() as conn:
        existing = _get_channel(conn, session_token, channel_id)
        kind = _normalize_kind(data.get("kind", existing.kind))
        if kind != existing.kind:
            raise NotificationChannelError("kind_locked", "Create a new channel to change the channel type.")
        secret_values = data.get("secret_values")
        secrets = {**existing.secrets, **_secret_refs_for_values(channel_id, kind, secret_values)}
        channel = NotificationChannel(
            id=existing.id,
            session_token=existing.session_token,
            kind=existing.kind,
            label=_normalize_label(data.get("label", existing.label), kind=existing.kind),
            secrets=secrets,
            config=_normalize_config(existing.kind, data.get("config", existing.config)),
            triggers=_normalize_triggers(data.get("triggers", list(existing.triggers))),
            muted=bool(data.get("muted", existing.muted)),
            created=existing.created,
            updated=_utc_now(),
        )
        _validate_channel(channel)
        _store_secret_values(session_token, channel_id, kind, secret_values)
        conn.execute(
            "UPDATE notification_channels "
            "SET label = ?, secrets_json = ?, config_json = ?, triggers_json = ?, muted = ?, updated = ? "
            "WHERE session_token = ? AND id = ?",
            (
                channel.label,
                _json_param(channel.secrets),
                _json_param(channel.config),
                _json_param(list(channel.triggers)),
                dialect_for_backend(database.DB_BACKEND).boolean_param(channel.muted),
                channel.updated,
                session_token,
                channel.id,
            ),
        )
        conn.commit()
    return _serialize_channel(channel)


def delete_notification_channel(session_token: str, channel_id: str) -> bool:
    session_token = require_durable_session_token(session_token)
    removed = False
    with database.db_connect() as conn:
        channel = _get_channel(conn, session_token, channel_id)
        cur = conn.execute(
            "DELETE FROM notification_channels WHERE session_token = ? AND id = ?",
            (session_token, channel_id),
        )
        removed = int(getattr(cur, "rowcount", 0) or 0) > 0
        conn.commit()
    if removed:
        for secret_name in _loads_json_dict(channel.secrets).values():
            try:
                delete_secret(session_token, str(secret_name))
            except (ValueError, MasterKeyError, SecretDecryptError):
                continue
    return removed


def send_test_notification(session_token: str, channel_id: str) -> list[str]:
    session_token = require_durable_session_token(session_token)
    with database.db_connect() as conn:
        _get_channel(conn, session_token, channel_id)
        event_ids = dispatcher.enqueue(
            TRIGGER_TEST,
            build_test_payload(channel_id),
            session_token,
            conn=conn,
            dispatch_sync=True,
        )
        conn.commit()
    return event_ids
