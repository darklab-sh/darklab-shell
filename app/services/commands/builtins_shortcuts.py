# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Keyboard shortcut built-in command helpers."""

from __future__ import annotations

from services.commands.builtin_registry import (
    BuiltinCommandSpec,
    build_builtin_command_spec,
)
from services.commands.builtins_copy import _CURRENT_SHORTCUTS
from services.commands.builtins_format import (
    format_native_record as _format_native_record,
    output_line as _output_line,
)


def _is_mac_user_agent(user_agent: str | None) -> bool:
    if not user_agent:
        return False
    return "Mac" in user_agent


def _resolve_shortcut_key(key, is_mac: bool) -> str:
    if isinstance(key, dict):
        return key["mac"] if is_mac else key["other"]
    return key


def _detect_mac_from_request() -> bool:
    try:
        from flask import has_request_context, request
    except ImportError:
        return False
    if not has_request_context():
        return False
    return _is_mac_user_agent(request.user_agent.string)


def get_current_shortcuts(is_mac: bool | None = None) -> dict:
    """Return the shortcut reference as a JSON-serialisable payload.

    Single source of truth consumed by the `shortcuts` built-in command and by
    the browser-side shortcuts overlay (press `?` from the terminal). Pass
    `is_mac=True/False` to force a platform; when omitted, the active Flask
    request's User-Agent is inspected (and falls back to non-Mac outside any
    request context).
    """
    resolved_mac = _detect_mac_from_request() if is_mac is None else is_mac
    return {
        "sections": [
            {
                "title": title,
                "items": [
                    {
                        "key": _resolve_shortcut_key(key, resolved_mac),
                        "description": description,
                    }
                    for key, description in items
                ],
            }
            for title, items in _CURRENT_SHORTCUTS
        ],
    }


def run_builtin_shortcuts() -> list[dict[str, object]]:
    payload = get_current_shortcuts()
    width = max(
        (len(item["key"]) for section in payload["sections"] for item in section["items"]),
        default=0,
    )
    lines: list[dict[str, object]] = []
    for index, section in enumerate(payload["sections"]):
        if index > 0:
            lines.append(_output_line("", "builtin-spacer"))
        lines.append(_output_line(f"{section['title']}:", "builtin-section"))
        for item in section["items"]:
            lines.append(
                _output_line(
                    _format_native_record(item["key"], item["description"], width),
                    "builtin-shortcut",
                )
            )
    return lines


_BUILTIN_AUTOCOMPLETE = {
    "shortcuts": {
        "root": "shortcuts",
        "description": "built-in: show current keyboard shortcuts",
        "autocomplete": {"arguments": []},
    }
}


def builtin_command_specs() -> tuple[BuiltinCommandSpec, ...]:
    return (
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["shortcuts"],
            handler_key="shortcuts",
            handler=lambda _command, _context: run_builtin_shortcuts(),
            name="shortcuts",
            description="Show current keyboard shortcuts.",
        ),
    )
