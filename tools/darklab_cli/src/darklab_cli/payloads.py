# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded JSON-object input for script-friendly CLI mutations."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from .errors import DarklabCliError


MAX_STRUCTURED_PAYLOAD_BYTES = 1024 * 1024


def read_json_object(source: object) -> dict[str, Any]:
    """Read one bounded JSON object from a named file or standard input."""
    value = str(source or "").strip()
    if not value:
        raise DarklabCliError("structured input path is required")
    try:
        if value == "-":
            raw = sys.stdin.read(MAX_STRUCTURED_PAYLOAD_BYTES + 1)
        else:
            with Path(value).open(encoding="utf-8") as handle:
                raw = handle.read(MAX_STRUCTURED_PAYLOAD_BYTES + 1)
    except (OSError, UnicodeError) as exc:
        raise DarklabCliError(f"couldn't read structured input: {exc}") from exc
    if len(raw.encode("utf-8")) > MAX_STRUCTURED_PAYLOAD_BYTES:
        raise DarklabCliError(
            f"structured input exceeds {MAX_STRUCTURED_PAYLOAD_BYTES} bytes"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DarklabCliError(
            f"structured input must be valid JSON: line {exc.lineno} column {exc.colno}"
        ) from exc
    if not isinstance(payload, dict):
        raise DarklabCliError("structured input must contain one JSON object")
    return payload


__all__ = ["MAX_STRUCTURED_PAYLOAD_BYTES", "read_json_object"]
