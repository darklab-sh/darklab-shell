# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Sanitize secret-bearing fields in TruffleHog JSON results."""

from __future__ import annotations

import json
from typing import Any


_SECRET_FIELDS = ("Raw", "RawV2", "Redacted")
_MALFORMED_RESULT = {
    "DetectorName": "Unknown",
    "Verified": False,
    "Redacted": "[redacted]",
    "ParseError": True,
}


def _replace_secret_copies(value: object, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, list):
        return [_replace_secret_copies(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: _replace_secret_copies(item, secrets) for key, item in value.items()}
    return value


def redact_trufflehog_json_line(line: str, *, assume_trufflehog: bool = False) -> str:
    """Return a safe TruffleHog result row while leaving unrelated output unchanged."""
    raw_line = str(line)
    suffix = "\n" if raw_line.endswith("\n") else ""
    try:
        parsed = json.loads(raw_line.rstrip("\n"))
    except (TypeError, ValueError):
        if assume_trufflehog and raw_line.lstrip().startswith("{"):
            return json.dumps(_MALFORMED_RESULT, separators=(",", ":")) + suffix
        return line
    if not isinstance(parsed, dict):
        return line
    if not assume_trufflehog and not any(key in parsed for key in ("DetectorName", "DetectorType")):
        return line
    secret_parts = parsed.get("SecretParts")
    candidates = [parsed.get(field) for field in _SECRET_FIELDS]
    if isinstance(secret_parts, dict):
        candidates.extend(secret_parts.values())
    secrets = tuple(sorted({
        value for value in candidates
        if isinstance(value, str) and value not in ("", "[redacted]")
    }, key=len, reverse=True))
    if not secrets:
        return line
    parsed = _replace_secret_copies(parsed, secrets)
    for secret_field in _SECRET_FIELDS:
        if secret_field in parsed and parsed[secret_field] not in ("", None):
            parsed[secret_field] = "[redacted]"
    secret_parts = parsed.get("SecretParts")
    if isinstance(secret_parts, dict):
        parsed["SecretParts"] = dict.fromkeys(secret_parts, "[redacted]")
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) + suffix
