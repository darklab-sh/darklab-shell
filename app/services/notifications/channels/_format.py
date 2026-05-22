"""Payload formatting helpers for outbound notification channels."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.notifications.models import notification_app_name

MAX_FIELD_VALUE_LENGTH = 320
MAX_MESSAGE_LENGTH = 1800


def truncate_text(value: Any, limit: int = MAX_FIELD_VALUE_LENGTH) -> str:
    text = str(value if value is not None else "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def truncate_run_id(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    if len(text) <= 18:
        return text
    return f"...{text[-8:]}"


def parse_email_recipients(value: Any) -> list[str]:
    if isinstance(value, list):
        candidates = value
    elif isinstance(value, str):
        candidates = value.replace(";", ",").split(",")
    else:
        candidates = []
    return [str(item).strip() for item in candidates if str(item or "").strip()]


def humanize_key(value: str) -> str:
    return str(value or "").replace("_", " ").strip().title()


def _format_mapping_value(value: Mapping[Any, Any]) -> str:
    pairs: list[tuple[str, int]] = []
    for raw_key, raw_count in value.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        try:
            count = int(raw_count or 0)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        pairs.append((key, count))
    if not pairs:
        return ""
    return ", ".join(f"{key} {count}" for key, count in sorted(pairs))


def format_field_value(value: Any) -> str:
    if isinstance(value, Mapping):
        return truncate_text(_format_mapping_value(value))
    return truncate_text(value)


def notification_title(payload: dict[str, Any]) -> str:
    trigger = str(payload.get("trigger") or "notification").replace("_", " ")
    app_name = str(payload.get("app_name") or "").strip() or notification_app_name()
    root = str(payload.get("command_root") or "").strip()
    if root:
        return truncate_text(f"{app_name} {trigger}: {root}", 120)
    return truncate_text(f"{app_name} {trigger}", 120)


def format_summary_fields(payload: dict[str, Any]) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for key, label in (
        ("run_id", "Run"),
        ("command_root", "Command"),
        ("exit_code", "Exit"),
        ("schedule_id", "Schedule"),
        ("watcher_id", "Watcher"),
    ):
        value = payload.get(key)
        if value not in ("", None):
            display_value = truncate_run_id(value) if key == "run_id" else truncate_text(value)
            fields.append((label, display_value))

    summary_fields = payload.get("summary_fields")
    if isinstance(summary_fields, dict):
        for key in sorted(summary_fields):
            value = summary_fields.get(key)
            if value not in ("", None):
                display_value = format_field_value(value)
                if display_value:
                    fields.append((humanize_key(str(key)), display_value))
    return fields


def format_plain_text(payload: dict[str, Any]) -> str:
    lines = [notification_title(payload)]
    message = str(payload.get("message") or "").strip()
    if message:
        lines.append(truncate_text(message, 400))
    for label, value in format_summary_fields(payload):
        lines.append(f"{label}: {value}")
    occurred_at = str(payload.get("occurred_at") or "").strip()
    if occurred_at:
        lines.append(f"At: {occurred_at}")
    return truncate_text("\n".join(lines), MAX_MESSAGE_LENGTH)


def format_slack_payload(payload: dict[str, Any]) -> dict[str, Any]:
    title = notification_title(payload)
    fields = format_summary_fields(payload)
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
    ]
    if fields:
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{label}*\n{value}"}
                for label, value in fields[:10]
            ],
        })
    return {"text": title, "blocks": blocks}


def format_discord_payload(payload: dict[str, Any]) -> dict[str, Any]:
    title = notification_title(payload)
    fields = format_summary_fields(payload)
    embed: dict[str, Any] = {
        "title": title,
        "fields": [
            {"name": label, "value": value or "-", "inline": True}
            for label, value in fields[:12]
        ],
    }
    occurred_at = str(payload.get("occurred_at") or "").strip()
    if occurred_at:
        embed["footer"] = {"text": occurred_at}
    return {"embeds": [embed]}
