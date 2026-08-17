# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Small shared OpenAPI schemas for probe availability and launch permission."""

from __future__ import annotations

from typing import Any, Callable


def probe_availability_schema(object_schema: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    return object_schema(
        ["available", "code", "reason"],
        {
            "available": {"type": "boolean"},
            "code": {"type": "string"},
            "reason": {"type": "string"},
        },
    )


def probe_launch_authorization_schema(
    object_schema: Callable[..., dict[str, Any]],
    strings_schema: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return object_schema(
        ["authorized", "required_capabilities", "missing_capabilities", "reason"],
        {
            "authorized": {"type": "boolean"},
            "required_capabilities": strings_schema(),
            "missing_capabilities": strings_schema(),
            "reason": {"type": "string"},
        },
    )


__all__ = ["probe_availability_schema", "probe_launch_authorization_schema"]
