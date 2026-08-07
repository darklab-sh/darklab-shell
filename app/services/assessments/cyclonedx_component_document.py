# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared bounded document validation for CycloneDX component adapters."""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any


CYCLONEDX_MAX_BYTES = 10 * 1024 * 1024
CYCLONEDX_MAX_COMPONENTS = 5000
_SPEC_VERSION_RE = re.compile(r"^1\.\d{1,3}$")


def parse_cyclonedx_component_document(
    payload: bytes | str,
    *,
    observed_at: str = "",
) -> dict[str, Any]:
    """Return one bounded component document or an empty fail-closed result."""
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not isinstance(raw, bytes) or not raw or len(raw) > CYCLONEDX_MAX_BYTES:
        return _empty()
    try:
        document = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return _empty()
    if not isinstance(document, dict) or str(document.get("bomFormat") or "").casefold() != "cyclonedx":
        return _empty()
    spec_version = _text(document.get("specVersion"), 16)
    components = document.get("components")
    timestamp = _observed_at(document, observed_at)
    if not _SPEC_VERSION_RE.fullmatch(spec_version) or not timestamp or not isinstance(components, list):
        return _empty()
    return {
        "spec_version": spec_version,
        "observed_at": timestamp,
        "components": components[:CYCLONEDX_MAX_COMPONENTS],
        "truncated": len(components) > CYCLONEDX_MAX_COMPONENTS,
    }


def _observed_at(document: dict[str, Any], explicit: str) -> str:
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    value = _text(explicit or metadata.get("timestamp"), 64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return value if parsed.tzinfo is not None else ""


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text if text and len(text) <= limit and not any(ord(char) < 32 for char in raw) else ""


def _empty() -> dict[str, Any]:
    return {"spec_version": "", "observed_at": "", "components": [], "truncated": False}


__all__ = [
    "CYCLONEDX_MAX_COMPONENTS",
    "parse_cyclonedx_component_document",
]
