# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Minimized adapters for reviewed Nmap scripts without structured XML fields."""

from __future__ import annotations

from typing import Any


_FTP_ANONYMOUS_SUCCESS = "Anonymous FTP login allowed (FTP code 230)"


def exact_output_fields(script_id: str, output: Any) -> list[dict[str, Any]] | None:
    """Return typed fields for an exact reviewed output contract, if one applies."""
    if script_id != "ftp-anon":
        return None
    if not isinstance(output, str) or output.strip() != _FTP_ANONYMOUS_SUCCESS:
        return []
    return [
        {"path": ["access"], "value": "allowed"},
        {"path": ["account"], "value": "anonymous"},
        {"path": ["reply_code"], "value": "230"},
    ]


__all__ = ["exact_output_fields"]
