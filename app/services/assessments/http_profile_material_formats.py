# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Private file formats used by protected HTTP assessment adapters."""

import json
from typing import Mapping


class HttpProfileMaterialFormatError(ValueError):
    """Raised when a private adapter file cannot encode a supplied value."""


def _curl_config_value(value: str) -> str:
    if any(ord(character) < 32 and character not in {"\t"} for character in value):
        raise HttpProfileMaterialFormatError("Curl profile material contains an unsafe value")
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")


def curl_config(headers: list[tuple[str, str]], copied: Mapping[str, str]) -> bytes:
    """Return a Curl config with escaped header and certificate values."""
    lines = [
        f'header = "{_curl_config_value(f"{name}: {value}")}"'
        for name, value in headers
    ]
    if copied:
        lines.extend([
            f'cert = "{_curl_config_value(copied["client_certificate"])}"',
            f'key = "{_curl_config_value(copied["client_key"])}"',
        ])
    return ("\n".join(lines) + "\n").encode("utf-8")


def dalfox_config(headers: list[tuple[str, str]]) -> bytes:
    """Return a minimal Dalfox config that cannot broaden the target scope."""
    payload = {
        "scan": {
            "follow_redirects": False,
            "headers": [f"{name}: {value}" for name, value in headers],
        },
    }
    return (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sqlmap_config(headers: list[tuple[str, str]]) -> bytes:
    """Return a minimal SQLmap INI carrying only protected headers."""
    lines = ["[Target]", "", "[Request]"]
    if headers:
        lines.append(f"headers = {headers[0][0]}: {headers[0][1]}")
        lines.extend(f" {name}: {value}" for name, value in headers[1:])
    lines.append("ignoreRedirects = True")
    return ("\n".join(lines) + "\n").encode("utf-8")
