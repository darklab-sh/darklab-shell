"""Outbound notification built-in command handler."""

from __future__ import annotations

import logging
from typing import Any

from core.helpers import get_log_session_id
from services.commands.builtins_format import format_native_record, output_line
from services.commands.registry import split_command_argv
from services.notifications.channels_store import (
    CHANNEL_KIND_LABELS,
    CHANNEL_SECRET_FIELDS,
    NotificationChannelError,
    create_notification_channel,
    delete_notification_channel,
    list_notification_channels,
    list_notification_events,
    notification_channel_kind_contract,
    send_test_notification,
    update_notification_channel,
)

log = logging.getLogger("shell")


class BuiltinNotifyError(ValueError):
    """Raised when notify built-in input is invalid."""


def _notify_usage() -> list[dict[str, object]]:
    return [
        output_line("Notification commands:", "builtin-section"),
        output_line("  notify list", "builtin-help-row"),
        output_line("  notify kinds", "builtin-help-row"),
        output_line("  notify info <id>", "builtin-help-row"),
        output_line("  notify mute <id>", "builtin-help-row"),
        output_line("  notify unmute <id>", "builtin-help-row"),
        output_line("  notify delete <id>", "builtin-help-row"),
        output_line("  notify test <id>", "builtin-help-row"),
        output_line("  notify events [--channel <id>] [--status sent|dead|pending|retry_wait]", "builtin-help-row"),
        output_line("  notify create <kind> [--label TEXT] [--trigger NAME] [--config KEY=VALUE]", "builtin-help-row"),
        output_line("Secrets are entered from Options > Notifications, not on the command line.", "builtin-note"),
    ]


def _durable_session_error(session_id: str) -> str:
    if str(session_id or "").startswith("tok_"):
        return "notify: this token is not registered; run `session-token generate` or reload with a saved token."
    return "notify: persistent session token required. Run `session-token generate` first."


def _is_durable_session(session_id: str) -> bool:
    return str(session_id or "").startswith("tok_")


def _notify_ref(parts: list[str], usage: str) -> str:
    if len(parts) < 3 or not str(parts[2] or "").strip():
        raise BuiltinNotifyError(usage)
    return str(parts[2]).strip()


def _read_option_value(parts: list[str], index: int, option: str) -> tuple[str, int]:
    if index + 1 >= len(parts):
        raise BuiltinNotifyError(f"notify: {option} requires a value")
    return parts[index + 1], index + 2


def _parse_key_value(value: str, *, option: str) -> tuple[str, str]:
    if "=" not in value:
        raise BuiltinNotifyError(f"notify: {option} values must use KEY=VALUE")
    key, raw = value.split("=", 1)
    key = key.strip()
    if not key:
        raise BuiltinNotifyError(f"notify: {option} key is required")
    return key, raw.strip()


def _parse_create_or_update(parts: list[str], *, create: bool) -> dict[str, Any]:
    min_len = 3 if create else 3
    if len(parts) < min_len:
        raise BuiltinNotifyError("Usage: notify create <kind>" if create else "Usage: notify update <id>")
    payload: dict[str, Any] = {"triggers": [], "config": {}}
    if create:
        payload["kind"] = str(parts[2] or "").strip().lower()
        index = 3
    else:
        index = 3
    while index < len(parts):
        option = parts[index]
        if option == "--label":
            payload["label"], index = _read_option_value(parts, index, option)
            continue
        if option == "--trigger":
            trigger, index = _read_option_value(parts, index, option)
            payload["triggers"].append(trigger)
            continue
        if option == "--config":
            value, index = _read_option_value(parts, index, option)
            key, raw = _parse_key_value(value, option=option)
            payload["config"][key] = raw
            continue
        if option == "--muted":
            payload["muted"] = True
            index += 1
            continue
        raise BuiltinNotifyError(f"notify: unknown option {option}")
    if not payload["triggers"]:
        payload.pop("triggers")
    if not payload["config"]:
        payload.pop("config")
    return payload


def _parse_events(parts: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"limit": 10, "offset": 0}
    index = 2
    while index < len(parts):
        option = parts[index]
        if option in {"--channel", "--channel-id"}:
            payload["channel_id"], index = _read_option_value(parts, index, option)
            continue
        if option == "--status":
            payload["status"], index = _read_option_value(parts, index, option)
            continue
        if option == "--trigger":
            payload["trigger"], index = _read_option_value(parts, index, option)
            continue
        if option == "--limit":
            raw, index = _read_option_value(parts, index, option)
            try:
                payload["limit"] = max(1, min(100, int(raw)))
            except ValueError as exc:
                raise BuiltinNotifyError("notify events: --limit must be a number") from exc
            continue
        if option == "--offset":
            raw, index = _read_option_value(parts, index, option)
            try:
                payload["offset"] = max(0, int(raw))
            except ValueError as exc:
                raise BuiltinNotifyError("notify events: --offset must be a number") from exc
            continue
        raise BuiltinNotifyError(f"notify events: unknown option {option}")
    return payload


def _channel_for_session(channel_id: str, session_id: str) -> dict[str, Any]:
    for channel in list_notification_channels(session_id):
        if str(channel.get("id") or "") == channel_id:
            return channel
    raise BuiltinNotifyError(f"notification channel not found: {channel_id}")


def _channel_secret_state(channel: dict[str, Any]) -> str:
    fields = channel.get("secret_fields")
    if not isinstance(fields, list) or not fields:
        return "none"
    configured = [
        str(field.get("name") or "")
        for field in fields
        if isinstance(field, dict) and field.get("configured")
    ]
    missing = [
        str(field.get("name") or "")
        for field in fields
        if isinstance(field, dict) and not field.get("configured")
    ]
    chunks = []
    if configured:
        chunks.append("configured: " + ", ".join(configured))
    if missing:
        chunks.append("missing: " + ", ".join(missing))
    return "; ".join(chunks) if chunks else "none"


def _format_trigger_list(value: Any) -> str:
    items = [str(item or "").strip() for item in (value if isinstance(value, list) else []) if str(item or "").strip()]
    return ", ".join(items) if items else "-"


def _format_config(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "-"
    return ", ".join(f"{key}={value[key]}" for key in sorted(value))


def _notify_lines(session_id: str) -> list[dict[str, object]]:
    channels = list_notification_channels(session_id)
    if not channels:
        return [
            output_line(
                "notify: no notification channels yet. Add one from Options > Notifications.",
                "builtin-note",
            )
        ]
    lines = [output_line("Notification channels:", "builtin-section")]
    lines.append(output_line(f"{'id':<36} {'kind':<10} {'muted':<6} label", "builtin-table-header"))
    for channel in channels:
        muted = "yes" if channel.get("muted") else "no"
        lines.append(output_line(
            f"{channel.get('id', ''):<36} {channel.get('kind', ''):<10} {muted:<6} {channel.get('label', '')}",
            "builtin-table-row",
        ))
    return lines


def _kind_lines() -> list[dict[str, object]]:
    contract = notification_channel_kind_contract()
    lines = [output_line("Notification channel types:", "builtin-section")]
    for kind in contract.get("kinds") or []:
        if not isinstance(kind, dict):
            continue
        secret_fields = ", ".join(str(field.get("name") or "") for field in kind.get("secret_fields") or []) or "none"
        config_fields = ", ".join(str(field.get("name") or "") for field in kind.get("config_fields") or []) or "none"
        label = str(kind.get("label") or kind.get("kind") or "")
        detail = f"secrets: {secret_fields}; config: {config_fields}"
        lines.append(output_line(format_native_record(label, detail, 12), "builtin-kv"))
    trigger_values = [str(item.get("value") or "") for item in contract.get("triggers") or [] if isinstance(item, dict)]
    if trigger_values:
        lines.append(output_line(format_native_record("triggers", ", ".join(trigger_values), 12), "builtin-kv"))
    return lines


def _info_lines(channel: dict[str, Any]) -> list[dict[str, object]]:
    width = 12
    return [
        output_line("Notification channel:", "builtin-section"),
        output_line(format_native_record("id", channel.get("id", ""), width), "builtin-kv"),
        output_line(format_native_record("kind", channel.get("kind", ""), width), "builtin-kv"),
        output_line(format_native_record("label", channel.get("label", "") or "-", width), "builtin-kv"),
        output_line(format_native_record("muted", "yes" if channel.get("muted") else "no", width), "builtin-kv"),
        output_line(format_native_record("triggers", _format_trigger_list(channel.get("triggers")), width), "builtin-kv"),
        output_line(format_native_record("config", _format_config(channel.get("config")), width), "builtin-kv"),
        output_line(format_native_record("secrets", _channel_secret_state(channel), width), "builtin-kv"),
        output_line(format_native_record("updated", channel.get("updated", "") or "-", width), "builtin-kv"),
    ]


def _create_channel(parts: list[str], session_id: str) -> list[dict[str, object]]:
    payload = _parse_create_or_update(parts, create=True)
    kind = str(payload.get("kind") or "").strip().lower()
    if CHANNEL_SECRET_FIELDS.get(kind):
        label = CHANNEL_KIND_LABELS.get(kind, kind)
        return [
            output_line(f"notify: {label} channels require secret values.", "builtin-note"),
            output_line(
                "Open Options > Notifications to create this channel so secrets stay out of shell history.",
                "builtin-note",
            ),
        ]
    channel = create_notification_channel(session_id, payload)
    log.info("BUILTIN_NOTIFY_CREATED", extra={
        "session": get_log_session_id(session_id),
        "source": "builtin",
        "channel_id": channel.get("id"),
        "kind": channel.get("kind"),
        "muted": bool(channel.get("muted")),
    })
    return [
        output_line(f"notify: created {channel.get('id')}", "builtin-success"),
        output_line(format_native_record("kind", channel.get("kind", ""), 8), "builtin-kv"),
        output_line(format_native_record("label", channel.get("label", ""), 8), "builtin-kv"),
    ]


def _update_channel(parts: list[str], session_id: str) -> list[dict[str, object]]:
    channel_id = _notify_ref(parts, "Usage: notify update <id> [--label TEXT] [--trigger NAME] [--config KEY=VALUE]")
    payload = _parse_create_or_update(parts, create=False)
    if not payload:
        raise BuiltinNotifyError("notify update: use --label, --trigger, --config, or --muted")
    channel = update_notification_channel(session_id, channel_id, payload)
    log.info("BUILTIN_NOTIFY_UPDATED", extra={
        "session": get_log_session_id(session_id),
        "source": "builtin",
        "channel_id": channel_id,
        "muted": bool(channel.get("muted")),
    })
    return [output_line(f"notify: updated {channel_id}", "builtin-success")]


def _events_lines(session_id: str, parts: list[str]) -> list[dict[str, object]]:
    params = _parse_events(parts)
    data = list_notification_events(session_id, **params)
    events = data.get("events") or []
    if not events:
        return [output_line("notify: no delivery events matched.", "builtin-note")]
    lines = [output_line(f"Notification events ({data.get('total', len(events))} total):", "builtin-section")]
    lines.append(output_line(f"{'created':<25} {'status':<10} {'trigger':<22} channel", "builtin-table-header"))
    for event in events:
        lines.append(output_line(
            f"{event.get('created', ''):<25} {event.get('status', ''):<10} "
            f"{event.get('trigger', ''):<22} {event.get('channel_id', '')}",
            "builtin-table-row",
        ))
        if event.get("last_error"):
            lines.append(output_line(f"  error: {event.get('last_error')}", "builtin-note"))
    if data.get("has_more"):
        lines.append(output_line("More events are available; rerun with a larger --offset.", "builtin-note"))
    return lines


def run_builtin_notify(command: str, session_id: str) -> list[dict[str, object]]:
    parts = split_command_argv(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "list"
    if subcommand in {"help", "-h", "--help"}:
        return _notify_usage()
    if subcommand in {"kinds", "types"}:
        return _kind_lines()
    if not _is_durable_session(session_id):
        log.warning("BUILTIN_NOTIFY_REJECTED", extra={
            "session": get_log_session_id(session_id),
            "source": "builtin",
            "subcommand": subcommand,
            "error": "session token required",
        })
        return [output_line(_durable_session_error(session_id))]
    try:
        if subcommand in {"list", "ls"}:
            return _notify_lines(session_id)
        if subcommand == "create":
            return _create_channel(parts, session_id)
        if subcommand == "update":
            return _update_channel(parts, session_id)
        if subcommand == "info":
            return _info_lines(_channel_for_session(_notify_ref(parts, "Usage: notify info <id>"), session_id))
        if subcommand == "mute":
            channel_id = _notify_ref(parts, "Usage: notify mute <id>")
            channel = update_notification_channel(session_id, channel_id, {"muted": True})
            log.info("BUILTIN_NOTIFY_MUTED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "channel_id": channel_id,
            })
            return [output_line(f"notify: muted {channel.get('id', channel_id)}", "builtin-success")]
        if subcommand == "unmute":
            channel_id = _notify_ref(parts, "Usage: notify unmute <id>")
            channel = update_notification_channel(session_id, channel_id, {"muted": False})
            log.info("BUILTIN_NOTIFY_UNMUTED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "channel_id": channel_id,
            })
            return [output_line(f"notify: unmuted {channel.get('id', channel_id)}", "builtin-success")]
        if subcommand == "delete":
            channel_id = _notify_ref(parts, "Usage: notify delete <id>")
            removed = delete_notification_channel(session_id, channel_id)
            log.info("BUILTIN_NOTIFY_DELETED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "channel_id": channel_id,
                "removed": bool(removed),
            })
            message = f"notify: deleted {channel_id}" if removed else f"notify: not found {channel_id}"
            return [output_line(message, "builtin-success" if removed else "builtin-note")]
        if subcommand == "test":
            channel_id = _notify_ref(parts, "Usage: notify test <id>")
            result = send_test_notification(session_id, channel_id)
            lines = [output_line(f"notify: queued {result.get('queued', 0)} test event(s)", "builtin-success")]
            for event in result.get("events") or []:
                lines.append(output_line(
                    format_native_record(str(event.get("event_id") or ""), str(event.get("status") or ""), 36),
                    "builtin-kv",
                ))
                if event.get("last_error"):
                    lines.append(output_line(f"  error: {event.get('last_error')}", "builtin-note"))
            return lines
        if subcommand == "events":
            return _events_lines(session_id, parts)
        return [
            output_line(f"notify: unknown subcommand '{subcommand}'"),
            *_notify_usage(),
        ]
    except BuiltinNotifyError as exc:
        return [output_line(str(exc))]
    except NotificationChannelError as exc:
        return [output_line(f"notify: {exc}")]
    except ValueError as exc:
        return [output_line(f"notify: {exc}")]
