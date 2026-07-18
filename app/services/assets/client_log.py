# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Sanitizers for browser log reports."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

_CLIENT_LOG_URL_RE = re.compile(r"((?:https?://|/)[^\s'\"<>]+)")
_CLIENT_LOG_STRING_DETAIL_LIMITS = {
    "action": 80,
    "asset_name": 120,
    "asset_type": 120,
    "artifact_id": 160,
    "bundle": 120,
    "controller_name": 160,
    "error_name": 120,
    "export_name": 160,
    "fragment_name": 120,
    "left_run_id": 160,
    "operation": 120,
    "page": 120,
    "package_id": 160,
    "phase": 120,
    "project_id": 160,
    "reason": 120,
    "resource": 80,
    "role": 80,
    "route": 160,
    "right_run_id": 160,
    "run_id": 160,
    "source": 120,
    "stage": 120,
    "tab": 80,
    "target_id": 160,
    "workspace_tab": 80,
}
_CLIENT_LOG_INT_DETAIL_KEYS = frozenset({"duration_ms", "limit", "offset", "status", "total"})
_CLIENT_LOG_BOOL_DETAIL_KEYS = frozenset({
    "compare_request_error",
    "expected_global",
    "has_active_filter",
    "partial_summary_present",
    "query_active",
    "used_initial_load",
})
_CLIENT_LOG_LIST_DETAIL_LIMITS = {"filter_fields": (20, 80), "module_keys": (80, 160)}


def sanitize_client_asset_src(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw.split("?", 1)[0][:300]
    path = parsed.path or raw.split("?", 1)[0]
    query = parse_qs(parsed.query, keep_blank_values=False)
    version = str((query.get("v") or [""])[0] or "")[:80]
    suffix = f"?{urlencode({'v': version})}" if version else ""
    return f"{path[:300]}{suffix}"


def sanitize_client_log_text(value: Any, limit: int) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    return _CLIENT_LOG_URL_RE.sub(lambda match: sanitize_client_asset_src(match.group(0)), raw)[:limit]


def sanitized_client_log_details(details: Any) -> dict[str, object]:
    if not isinstance(details, dict):
        return {}
    client_details: dict[str, object] = {}
    selection_key = str(details.get("selection_key") or "")[:80]
    if selection_key:
        client_details["selection_key"] = selection_key
    for key in _CLIENT_LOG_INT_DETAIL_KEYS:
        if key in details:
            try:
                client_details[key] = max(0, int(details.get(key) or 0))
            except (TypeError, ValueError):
                client_details[key] = 0
    for key, (item_limit, value_limit) in _CLIENT_LOG_LIST_DETAIL_LIMITS.items():
        if isinstance(details.get(key), list):
            client_details[key] = [
                str(value or "")[:value_limit]
                for value in details[key][:item_limit]
                if str(value or "").strip()
            ]
    if isinstance(details.get("filter_active"), dict):
        client_details["filter_active"] = {
            str(key or "")[:80]: bool(value)
            for key, value in list(details["filter_active"].items())[:20]
            if str(key or "").strip()
        }
    for key in _CLIENT_LOG_BOOL_DETAIL_KEYS:
        if key in details:
            client_details[key] = bool(details.get(key))
    for key, limit in _CLIENT_LOG_STRING_DETAIL_LIMITS.items():
        value = str(details.get(key) or "").strip()[:limit]
        if value:
            client_details[key] = value
    src = sanitize_client_asset_src(details.get("src"))
    if src:
        client_details["src"] = src
    return client_details
