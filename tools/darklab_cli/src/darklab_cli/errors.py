# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Structured, backward-compatible errors for the darklab CLI."""

from __future__ import annotations

import json
import urllib.error
from typing import Any


class DarklabCliError(Exception):
    """A readable CLI failure with optional public API error metadata."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str = "",
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details


def error_from_http_error(exc: urllib.error.HTTPError) -> DarklabCliError:
    """Decode the API's public error envelope without exposing details by default."""
    try:
        body = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(body) if body else {}
    except Exception:
        payload = {}
    conflict = payload.get("conflict") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and payload.get("ok") is False and isinstance(conflict, str) and conflict:
        return DarklabCliError(conflict, status=exc.code, code=conflict, details=payload)
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = str(error.get("code") or exc.code)
        message = str(error.get("message") or exc.reason)
        return DarklabCliError(f"{code}: {message}", status=exc.code, code=code,
                               details=error.get("details"))
    if isinstance(error, str):
        return DarklabCliError(error, status=exc.code)
    return DarklabCliError(f"HTTP {exc.code}: {exc.reason}", status=exc.code)


__all__ = ["DarklabCliError", "error_from_http_error"]
