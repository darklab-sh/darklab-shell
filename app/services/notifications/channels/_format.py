# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

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
    if str(payload.get("notification_kind") or "") == "assessment_batch":
        app_name = str(payload.get("app_name") or "").strip() or notification_app_name()
        return truncate_text(f"{app_name} assessment batch complete", 120)
    if str(payload.get("trigger") or "") == "project_digest":
        app_name = str(payload.get("app_name") or "").strip() or notification_app_name()
        project_name = str(payload.get("project_name") or "").strip() or "Project"
        return truncate_text(f"{app_name} project digest: {project_name}", 120)
    trigger = str(payload.get("trigger") or "notification").replace("_", " ")
    app_name = str(payload.get("app_name") or "").strip() or notification_app_name()
    root = str(payload.get("command_root") or "").strip()
    if root:
        return truncate_text(f"{app_name} {trigger}: {root}", 120)
    return truncate_text(f"{app_name} {trigger}", 120)


def format_summary_fields(payload: dict[str, Any]) -> list[tuple[str, str]]:
    if str(payload.get("notification_kind") or "") == "assessment_batch":
        return _format_assessment_batch_fields(payload)
    if str(payload.get("trigger") or "") == "project_digest":
        return _format_project_digest_fields(payload)

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


def _format_assessment_batch_fields(payload: dict[str, Any]) -> list[tuple[str, str]]:
    summary = payload.get("summary_fields")
    summary_fields = summary if isinstance(summary, dict) else {}
    fields: list[tuple[str, str]] = []
    batch_id = payload.get("batch_id")
    if batch_id not in ("", None):
        fields.append(("Batch", truncate_run_id(batch_id)))
    for key, label in (
        ("status", "Status"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("unavailable", "Unavailable"),
        ("canceled", "Canceled"),
        ("could_not_cancel", "Could Not Cancel"),
        ("batch_link", "Assessment Batch"),
    ):
        value = summary_fields.get(key)
        if value not in ("", None):
            fields.append((label, truncate_text(value)))
    return fields


def _format_project_digest_fields(payload: dict[str, Any]) -> list[tuple[str, str]]:
    summary = payload.get("summary_fields")
    summary_fields = summary if isinstance(summary, dict) else {}
    fields: list[tuple[str, str]] = []
    ordered = (
        ("project", "Project"),
        ("window", "Window"),
        ("changed", "Changed"),
        ("recovered", "Recovered"),
        ("failed", "Failed"),
        ("highest_severity", "Highest Severity"),
        ("cve_risk_changes", "CVE Risk Changes"),
        ("unacknowledged_cve_risk_changes", "Unacknowledged CVE Risk Changes"),
        ("quiet", "Quiet Digest"),
        ("monitoring_link", "Monitoring"),
    )
    for key, label in ordered:
        value = summary_fields.get(key)
        if value not in ("", None):
            fields.append((label, truncate_text(value)))

    top_changes = payload.get("top_changes")
    if isinstance(top_changes, list):
        for index, item in enumerate(top_changes[:5], start=1):
            if not isinstance(item, dict):
                continue
            label = truncate_text(item.get("label") or item.get("fire_kind") or "Change", 120)
            severity = str(item.get("severity") or "none").strip()
            watcher = str(item.get("watcher_label") or "").strip()
            detail = f"{severity}: {label}"
            if watcher:
                detail = f"{detail} ({truncate_text(watcher, 80)})"
            fields.append((f"Top Change {index}", truncate_text(detail, 220)))
    risk_changes = payload.get("risk_changes")
    if isinstance(risk_changes, list):
        for index, item in enumerate(risk_changes[:5], start=1):
            if not isinstance(item, dict):
                continue
            cve_id = str(item.get("cve_id") or "CVE").strip()
            transition = str(item.get("transition_kind") or "risk changed").replace("_", " ").strip()
            source = str(item.get("source") or "").upper().strip()
            detail = f"{cve_id}: {transition}"
            if source:
                detail = f"{detail} ({source})"
            fields.append((f"Risk Change {index}", truncate_text(detail, 220)))
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
