"""Session-owned notification channel CRUD helpers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import uuid
from typing import Any

from core import database
from core.database_backend import dialect_for_backend
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.notifications import dispatcher
from services.notifications.base import channel_class_for_kind
from services.notifications.channels import register_builtin_channels
from services.notifications.channels._format import parse_email_recipients
from services.notifications.models import (
    CHANNEL_KIND_DISCORD,
    CHANNEL_KIND_EMAIL,
    CHANNEL_KIND_PUSHOVER,
    CHANNEL_KIND_SLACK,
    CHANNEL_KIND_TELEGRAM,
    CHANNEL_KIND_WEBHOOK,
    CHANNEL_KINDS,
    EVENT_STATUSES,
    TRIGGER_PTY_SESSION_ENDED,
    TRIGGER_RUN_COMPLETE,
    TRIGGER_SCHEDULED_RUN_FAILED,
    TRIGGER_TEST,
    TRIGGER_WATCHER_CHANGED,
    TRIGGER_WATCHER_ERROR,
    TRIGGER_WATCHER_RECOVERED,
    TRIGGERS,
    NotificationChannel,
    NotificationEvent,
    require_durable_session_token,
)
from services.notifications.payloads import build_test_payload
from services.notifications.secrets import channel_secret_name, emit_channel_secret_audits, store_channel_secret_with_connection
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

CHANNEL_KIND_ORDER = (
    CHANNEL_KIND_WEBHOOK,
    CHANNEL_KIND_SLACK,
    CHANNEL_KIND_DISCORD,
    CHANNEL_KIND_TELEGRAM,
    CHANNEL_KIND_PUSHOVER,
    CHANNEL_KIND_EMAIL,
)

CHANNEL_KIND_LABELS = {
    CHANNEL_KIND_WEBHOOK: "Webhook",
    CHANNEL_KIND_SLACK: "Slack",
    CHANNEL_KIND_DISCORD: "Discord",
    CHANNEL_KIND_TELEGRAM: "Telegram",
    CHANNEL_KIND_PUSHOVER: "Pushover",
    CHANNEL_KIND_EMAIL: "Email",
}

CHANNEL_SECRET_FIELD_LABELS = {
    CHANNEL_KIND_WEBHOOK: {"url": "Webhook URL"},
    CHANNEL_KIND_SLACK: {"url": "Slack webhook URL"},
    CHANNEL_KIND_DISCORD: {"url": "Discord webhook URL"},
    CHANNEL_KIND_TELEGRAM: {"bot_token": "Bot token"},
    CHANNEL_KIND_PUSHOVER: {"app_token": "App token", "user_key": "User key"},
    CHANNEL_KIND_EMAIL: {},
}

CHANNEL_CONFIG_FIELD_DEFINITIONS = {
    CHANNEL_KIND_WEBHOOK: ({"name": "timeout_seconds", "label": "Timeout seconds", "optional": True},),
    CHANNEL_KIND_SLACK: ({"name": "timeout_seconds", "label": "Timeout seconds", "optional": True},),
    CHANNEL_KIND_DISCORD: ({"name": "timeout_seconds", "label": "Timeout seconds", "optional": True},),
    CHANNEL_KIND_TELEGRAM: (
        {"name": "chat_id", "label": "Chat ID"},
        {"name": "timeout_seconds", "label": "Timeout seconds", "optional": True},
    ),
    CHANNEL_KIND_PUSHOVER: (
        {"name": "priority", "label": "Priority", "optional": True},
        {"name": "sound", "label": "Sound", "optional": True},
        {"name": "device", "label": "Device", "optional": True},
        {"name": "timeout_seconds", "label": "Timeout seconds", "optional": True},
    ),
    CHANNEL_KIND_EMAIL: (
        {"name": "recipients", "label": "Recipients", "help": "Comma-separated email addresses."},
        {"name": "reply_to", "label": "Reply-To", "optional": True},
        {"name": "timeout_seconds", "label": "Timeout seconds", "optional": True},
    ),
}

CHANNEL_CONFIG_FIELDS = {
    kind: tuple(str(field["name"]) for field in fields)
    for kind, fields in CHANNEL_CONFIG_FIELD_DEFINITIONS.items()
}

TRIGGER_LABELS = {
    TRIGGER_RUN_COMPLETE: "Run complete",
    TRIGGER_PTY_SESSION_ENDED: "PTY session ended",
    TRIGGER_SCHEDULED_RUN_FAILED: "Scheduled run failed",
    TRIGGER_WATCHER_CHANGED: "Watcher changed",
    TRIGGER_WATCHER_ERROR: "Watcher error",
    TRIGGER_WATCHER_RECOVERED: "Watcher recovered",
}

UI_TRIGGERS = (
    TRIGGER_RUN_COMPLETE,
    TRIGGER_PTY_SESSION_ENDED,
    TRIGGER_SCHEDULED_RUN_FAILED,
    TRIGGER_WATCHER_CHANGED,
    TRIGGER_WATCHER_ERROR,
    TRIGGER_WATCHER_RECOVERED,
)
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
    return f"ntc_{uuid.uuid4().hex}"


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


def _owner_where(session_token: str, team_id: str = "") -> tuple[str, tuple[str, ...]]:
    if team_id:
        return "team_id = ?", (team_id,)
    return "(team_id IS NULL OR team_id = '') AND session_token = ?", (session_token,)


def _channel_rows(conn, session_token: str, team_id: str = "") -> list[Any]:
    owner_sql, owner_params = _owner_where(session_token, team_id)
    return conn.execute(
        "SELECT id, session_token, team_id, kind, label, secrets_json, config_json, triggers_json, "
        "muted, created, updated "
        f"FROM notification_channels WHERE {owner_sql} ORDER BY lower(label) ASC, created ASC, id ASC",  # nosec
        owner_params,
    ).fetchall()


def _get_channel(conn, session_token: str, channel_id: str, team_id: str = "") -> NotificationChannel:
    owner_sql, owner_params = _owner_where(session_token, team_id)
    row = conn.execute(
        "SELECT id, session_token, team_id, kind, label, secrets_json, config_json, triggers_json, "
        "muted, created, updated "
        f"FROM notification_channels WHERE {owner_sql} AND id = ?",  # nosec
        (*owner_params, channel_id),
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
            recipients = parse_email_recipients(value)
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


def _store_secret_values(conn, session_token: str, channel_id: str, kind: str, raw_secret_values: Any) -> list[tuple[dict, bool]]:
    values = _secret_values(raw_secret_values)
    allowed = set(CHANNEL_SECRET_FIELDS[kind])
    audit_records = []
    for field in allowed:
        if field in values:
            _, metadata, created = store_channel_secret_with_connection(conn, session_token, channel_id, field, values[field])
            audit_records.append((metadata, created))
    return audit_records


def _validate_channel(channel: NotificationChannel) -> None:
    channel_cls = channel_class_for_kind(channel.kind)
    if channel_cls is None:
        register_builtin_channels()
        channel_cls = channel_class_for_kind(channel.kind)
    if channel_cls is None:
        raise NotificationChannelError("invalid_kind", "Notification channel type is not registered.")
    errors = channel_cls(channel).validate_config(channel.config)
    if errors:
        raise NotificationChannelError("invalid_config", "; ".join(errors))


def _serialize_channel(channel: NotificationChannel) -> dict[str, Any]:
    secret_fields = tuple(CHANNEL_SECRET_FIELDS[channel.kind])
    payload = {
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
    if channel.team_id:
        payload["team_id"] = channel.team_id
    return payload


def _audit_details(
    channel: NotificationChannel,
    *,
    action: str,
    source: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "action": action,
        "source": source,
        "channel_id": channel.id,
        "kind": channel.kind,
        "label": channel.label,
        "muted": bool(channel.muted),
        "triggers": [trigger for trigger in channel.triggers if trigger != TRIGGER_TEST],
    }
    details.update({key: value for key, value in dict(extra or {}).items() if value not in (None, "")})
    return details


def _record_config_change(
    channel: NotificationChannel,
    *,
    action: str,
    audit_fields: Mapping[str, Any] | None,
    source: str,
    conn,
    details: Mapping[str, Any] | None = None,
) -> None:
    if not audit_fields:
        return
    record_event(
        AuditEventType.NOTIFICATION_CONFIG_CHANGE,
        target_id=channel.id,
        details=_audit_details(channel, action=action, source=source, extra=details),
        conn=conn,
        **dict(audit_fields),
    )


def _serialize_event(event: NotificationEvent) -> dict[str, Any]:
    payload = {
        "id": event.id,
        "channel_id": event.channel_id,
        "trigger": event.trigger,
        "payload": event.payload,
        "status": event.status,
        "attempts": event.attempts,
        "next_attempt_at": event.next_attempt_at,
        "last_attempt_at": event.last_attempt_at,
        "last_error": event.last_error,
        "run_id": event.run_id,
        "created": event.created,
        "dead_at": event.dead_at,
    }
    if event.team_id:
        payload["team_id"] = event.team_id
    return payload


def _serialize_test_event(event: NotificationEvent) -> dict[str, Any]:
    return {
        "event_id": event.id,
        "status": event.status,
        "last_error": event.last_error,
    }


def notification_channel_kind_contract() -> dict[str, Any]:
    kinds = []
    for kind in CHANNEL_KIND_ORDER:
        secret_labels = CHANNEL_SECRET_FIELD_LABELS[kind]
        kinds.append({
            "kind": kind,
            "label": CHANNEL_KIND_LABELS[kind],
            "secret_fields": [
                {"name": field, "label": secret_labels.get(field, field)}
                for field in CHANNEL_SECRET_FIELDS[kind]
            ],
            "config_fields": [dict(field) for field in CHANNEL_CONFIG_FIELD_DEFINITIONS[kind]],
        })
    return {
        "kinds": kinds,
        "triggers": [
            {"value": trigger, "label": TRIGGER_LABELS.get(trigger, trigger.replace("_", " ").title())}
            for trigger in UI_TRIGGERS
        ],
    }


def _test_event_statuses(conn, event_ids: list[str]) -> list[dict[str, Any]]:
    if not event_ids:
        return []
    placeholders = ", ".join("?" for _ in event_ids)
    rows = conn.execute(
        "SELECT id, session_token, team_id, channel_id, trigger, payload_json, status, attempts, "
        "next_attempt_at, last_attempt_at, last_error, run_id, created, dead_at "
        f"FROM notification_events WHERE id IN ({placeholders})",  # nosec
        event_ids,
    ).fetchall()
    events_by_id = {str(row["id"]): NotificationEvent.from_row(row) for row in rows}
    return [
        _serialize_test_event(events_by_id[event_id])
        for event_id in event_ids
        if event_id in events_by_id
    ]


def list_notification_channels(session_token: str, *, team_id: str = "") -> list[dict[str, Any]]:
    session_token = require_durable_session_token(session_token)
    with database.db_connect() as conn:
        return [_serialize_channel(NotificationChannel.from_row(row)) for row in _channel_rows(conn, session_token, team_id)]


def list_notification_events(
    session_token: str,
    *,
    limit: int,
    offset: int,
    status: str = "",
    channel_id: str = "",
    trigger: str = "",
    team_id: str = "",
) -> dict[str, Any]:
    session_token = require_durable_session_token(session_token)
    normalized_status = str(status or "").strip()
    normalized_channel_id = str(channel_id or "").strip()
    normalized_trigger = str(trigger or "").strip()
    if normalized_status and normalized_status not in EVENT_STATUSES:
        raise NotificationChannelError("invalid_status", "Choose a supported notification event status.")
    if normalized_trigger and normalized_trigger not in TRIGGERS:
        raise NotificationChannelError("invalid_trigger", "Choose a supported notification trigger.")

    owner_sql, owner_params = _owner_where(session_token, team_id)
    clauses = [owner_sql]
    params: list[Any] = list(owner_params)
    if normalized_status:
        clauses.append("status = ?")
        params.append(normalized_status)
    if normalized_channel_id:
        clauses.append("channel_id = ?")
        params.append(normalized_channel_id)
    if normalized_trigger:
        clauses.append("trigger = ?")
        params.append(normalized_trigger)
    where_sql = " AND ".join(clauses)
    with database.db_connect() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS count FROM notification_events WHERE {where_sql}",  # nosec B608
            params,
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        rows = conn.execute(
            "SELECT id, session_token, team_id, channel_id, trigger, payload_json, status, attempts, "
            "next_attempt_at, last_attempt_at, last_error, run_id, created, dead_at "
            f"FROM notification_events WHERE {where_sql} "  # nosec
            "ORDER BY created DESC, id DESC LIMIT ? OFFSET ?",
            [*params, int(limit), int(offset)],
        ).fetchall()
    events = [_serialize_event(NotificationEvent.from_row(row)) for row in rows]
    return {
        "events": events,
        "total": total,
        "limit": int(limit),
        "offset": int(offset),
        "has_more": int(offset) + len(events) < total,
    }


def create_notification_channel(
    session_token: str,
    data: dict[str, Any],
    *,
    team_id: str = "",
    audit_fields: Mapping[str, Any] | None = None,
    audit_source: str = "",
) -> dict[str, Any]:
    session_token = require_durable_session_token(session_token)
    kind = _normalize_kind(data.get("kind"))
    channel_id = _channel_id()
    now = _utc_now()
    secrets = _secret_refs_for_values(channel_id, kind, data.get("secret_values"))
    channel = NotificationChannel(
        id=channel_id,
        session_token=session_token,
        team_id=team_id,
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
    audit_records = []
    with database.db_connect() as conn:
        audit_records = _store_secret_values(
            conn,
            channel.secret_owner_token,
            channel_id,
            kind,
            data.get("secret_values"),
        )
        conn.execute(
            "INSERT INTO notification_channels "
            "(id, session_token, team_id, kind, label, secrets_json, config_json, triggers_json, muted, created, updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                channel.id,
                channel.session_token,
                channel.team_id,
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
        _record_config_change(
            channel,
            action="create",
            audit_fields=audit_fields,
            source=audit_source,
            conn=conn,
        )
        conn.commit()
    emit_channel_secret_audits(channel.secret_owner_token, audit_records)
    return _serialize_channel(channel)


def update_notification_channel(
    session_token: str,
    channel_id: str,
    data: dict[str, Any],
    *,
    team_id: str = "",
    audit_fields: Mapping[str, Any] | None = None,
    audit_source: str = "",
) -> dict[str, Any]:
    session_token = require_durable_session_token(session_token)
    with database.db_connect() as conn:
        existing = _get_channel(conn, session_token, channel_id, team_id)
        kind = _normalize_kind(data.get("kind", existing.kind))
        if kind != existing.kind:
            raise NotificationChannelError("kind_locked", "Create a new channel to change the channel type.")
        secret_values = data.get("secret_values")
        secrets = {**existing.secrets, **_secret_refs_for_values(channel_id, kind, secret_values)}
        channel = NotificationChannel(
            id=existing.id,
            session_token=existing.session_token,
            team_id=existing.team_id,
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
        audit_records = _store_secret_values(conn, channel.secret_owner_token, channel_id, kind, secret_values)
        owner_sql, owner_params = _owner_where(session_token, team_id)
        conn.execute(
            "UPDATE notification_channels "
            "SET label = ?, secrets_json = ?, config_json = ?, triggers_json = ?, muted = ?, updated = ? "
            f"WHERE {owner_sql} AND id = ?",  # nosec
            (
                channel.label,
                _json_param(channel.secrets),
                _json_param(channel.config),
                _json_param(list(channel.triggers)),
                dialect_for_backend(database.DB_BACKEND).boolean_param(channel.muted),
                channel.updated,
                *owner_params,
                channel.id,
            ),
        )
        changed_fields = [
            field for field in ("label", "config", "triggers", "muted", "secret_refs")
            if (
                (field == "label" and channel.label != existing.label)
                or (field == "config" and channel.config != existing.config)
                or (field == "triggers" and list(channel.triggers) != list(existing.triggers))
                or (field == "muted" and channel.muted != existing.muted)
                or (field == "secret_refs" and channel.secrets != existing.secrets)
            )
        ]
        _record_config_change(
            channel,
            action="update",
            audit_fields=audit_fields,
            source=audit_source,
            conn=conn,
            details={"changed_fields": changed_fields},
        )
        conn.commit()
    emit_channel_secret_audits(channel.secret_owner_token, audit_records)
    return _serialize_channel(channel)


def delete_notification_channel(
    session_token: str,
    channel_id: str,
    *,
    team_id: str = "",
    audit_fields: Mapping[str, Any] | None = None,
    audit_source: str = "",
) -> bool:
    session_token = require_durable_session_token(session_token)
    removed = False
    with database.db_connect() as conn:
        channel = _get_channel(conn, session_token, channel_id, team_id)
        owner_sql, owner_params = _owner_where(session_token, team_id)
        cur = conn.execute(
            f"DELETE FROM notification_channels WHERE {owner_sql} AND id = ?",  # nosec
            (*owner_params, channel_id),
        )
        removed = int(getattr(cur, "rowcount", 0) or 0) > 0
        if removed:
            _record_config_change(
                channel,
                action="delete",
                audit_fields=audit_fields,
                source=audit_source,
                conn=conn,
            )
        conn.commit()
    if removed:
        for secret_name in channel.secrets.values():
            try:
                delete_secret(channel.secret_owner_token, str(secret_name))
            except (ValueError, MasterKeyError, SecretDecryptError):
                continue
    return removed


def migrate_notification_channels_session(conn, from_session_id: str, to_session_id: str) -> dict[str, int]:
    channels_result = conn.execute(
        "UPDATE notification_channels SET session_token = ? WHERE session_token = ?",
        (to_session_id, from_session_id),
    )
    events_result = conn.execute(
        "UPDATE notification_events SET session_token = ? WHERE session_token = ?",
        (to_session_id, from_session_id),
    )
    return {
        "migrated_notification_channels": int(getattr(channels_result, "rowcount", 0) or 0),
        "migrated_notification_events": int(getattr(events_result, "rowcount", 0) or 0),
    }


def send_test_notification(
    session_token: str,
    channel_id: str,
    *,
    team_id: str = "",
    audit_fields: Mapping[str, Any] | None = None,
    audit_source: str = "",
) -> dict[str, Any]:
    session_token = require_durable_session_token(session_token)
    with database.db_connect() as conn:
        channel = _get_channel(conn, session_token, channel_id, team_id)
        event_ids = dispatcher.enqueue(
            TRIGGER_TEST,
            build_test_payload(channel_id),
            session_token,
            conn=conn,
            dispatch_sync=True,
            channel_ids=[channel_id],
            include_muted=True,
            team_id=team_id,
        )
        events = _test_event_statuses(conn, event_ids)
        _record_config_change(
            channel,
            action="test",
            audit_fields=audit_fields,
            source=audit_source,
            conn=conn,
            details={"count": len(event_ids), "result": "queued"},
        )
        conn.commit()
    return {"queued": len(event_ids), "event_ids": event_ids, "events": events}
