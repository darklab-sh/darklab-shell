# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Pinned JSON schemas and validation helpers for AI provider responses."""

from __future__ import annotations

from typing import Any

SUMMARY_SCHEMA_VERSION = "summary.v1"
NEXT_COMMANDS_SCHEMA_VERSION = "next_commands.v1"
DIAG_TEST_SCHEMA_VERSION = "diag_test.v1"
RISK_LABELS = frozenset({"low", "medium", "high", "unknown"})

SUMMARY_RESPONSE_SCHEMA = {
    "summary": "string",
    "key_findings": ["string"],
    "warnings": ["string"],
    "next_steps_hint": "string",
}

NEXT_COMMANDS_RESPONSE_SCHEMA = {
    "suggestions": [{
        "command": "string",
        "reason": "string",
        "risk_label": "low|medium|high|unknown",
        "target": "string|null",
    }],
}

DIAG_TEST_RESPONSE_SCHEMA = {
    "status": "ok",
    "message": "string",
}


class AISchemaError(ValueError):
    """Raised when provider JSON is syntactically valid but schema-invalid."""


def _string_list(value: Any, field: str, *, limit: int = 20, item_limit: int = 500) -> list[str]:
    if not isinstance(value, list):
        raise AISchemaError(f"{field} must be a list")
    items = []
    for item in value[:limit]:
        if not isinstance(item, str):
            raise AISchemaError(f"{field} items must be strings")
        text = item.strip()
        if text:
            items.append(text[:item_limit])
    return items


def _summary_string_list(value: Any, *, limit: int = 20, item_limit: int = 500) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        return []
    items = []
    preferred_keys = ("text", "line", "finding", "summary", "title", "message", "value")
    for item in value[:limit]:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = next((str(item.get(key) or "").strip() for key in preferred_keys if item.get(key)), "")
            if not text:
                text = " ".join(str(part).strip() for part in item.values() if part not in (None, ""))
        else:
            text = str(item).strip() if isinstance(item, (int, float, bool)) else ""
        if text:
            items.append(text[:item_limit])
    return items


def validate_summary_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AISchemaError("summary payload must be an object")
    summary = str(payload.get("summary") or "").strip()
    next_steps_hint = str(payload.get("next_steps_hint") or "").strip()
    if not summary:
        raise AISchemaError("summary is required")
    return {
        "summary": summary[:4000],
        "key_findings": _summary_string_list(payload.get("key_findings")),
        "warnings": _summary_string_list(payload.get("warnings")),
        "next_steps_hint": next_steps_hint[:1000],
    }


def validate_next_commands_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AISchemaError("next_commands payload must be an object")
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        raise AISchemaError("suggestions must be a list")
    normalized = []
    for item in suggestions[:3]:
        if not isinstance(item, dict):
            raise AISchemaError("suggestion items must be objects")
        command = str(item.get("command") or "").strip()
        reason = str(item.get("reason") or "").strip()
        risk_label = str(item.get("risk_label") or "unknown").strip().lower()
        target = item.get("target")
        if not command:
            raise AISchemaError("suggestion command is required")
        if risk_label not in RISK_LABELS:
            risk_label = "unknown"
        normalized.append({
            "command": command[:2000],
            "reason": reason[:240],
            "risk_label": risk_label,
            "target": str(target).strip()[:500] if target not in (None, "") else None,
        })
    return {"suggestions": normalized}


def validate_diag_test_payload(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise AISchemaError("diag test payload must be an object")
    status = str(payload.get("status") or "").strip().lower()
    message = str(payload.get("message") or "").strip()
    if status != "ok":
        raise AISchemaError("status must be ok")
    return {"status": "ok", "message": message[:240]}
