# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reduce decrypted Interactsh records to provider-independent input."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from services.connectors.oast_config import OastConnectorSettings
from services.connectors.oast_provider_contracts import OastProviderSession


_HTTP_REQUEST_LINE_RE = re.compile(
    r"([A-Z][A-Z0-9_-]{0,15}) ([^ ]{1,4096}) HTTP/\d(?:\.\d)?"
)
_MAX_INTERACTION_BYTES = 65536


def _http_details(raw_request: object) -> dict[str, str]:
    first_line = str(raw_request or "").splitlines()[0] if raw_request else ""
    match = _HTTP_REQUEST_LINE_RE.fullmatch(first_line.strip())
    if match is None:
        return {}
    method, target = match.groups()
    split = urlsplit(target)
    if split.scheme or split.netloc:
        target = split.path or "/"
        if split.query:
            target += "?" + split.query
    return {"method": method, "path": target}


def _smtp_details(raw_request: object) -> dict[str, str]:
    first_line = str(raw_request or "").splitlines()[0] if raw_request else ""
    command = first_line.strip().partition(" ")[0].upper()
    return (
        {"command": command} if re.fullmatch(r"[A-Z][A-Z0-9_-]{0,15}", command) else {}
    )


def normalize_oast_provider_interaction(
    interaction: Mapping[str, object],
    session: OastProviderSession,
    settings: OastConnectorSettings,
) -> dict[str, object] | None:
    """Return one strictly matched, redacted provider-independent record."""
    unique_id = str(interaction.get("unique-id") or "").strip().lower()
    if unique_id != session.callback_label:
        return None
    raw_protocol = str(interaction.get("protocol") or "").strip().lower()
    protocol = {
        "dns": "dns",
        "http": "http",
        "https": "http",
        "smtp": "smtp",
        "smtps": "smtp",
        "ldap": "ldap",
    }.get(raw_protocol)
    if protocol is None:
        return None
    details: dict[str, str] = {}
    if protocol == "dns":
        query_name = str(interaction.get("full-id") or "").strip().lower().rstrip(".")
        if not query_name:
            query_name = f"{session.callback_label}.{settings.allowed_domain}"
        details = {
            "query_name": query_name,
            "query_type": str(interaction.get("q-type") or ""),
        }
    elif protocol == "http":
        details = _http_details(interaction.get("raw-request"))
    elif protocol == "smtp":
        details = _smtp_details(interaction.get("raw-request"))
    canonical = json.dumps(
        dict(interaction), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if len(canonical) > _MAX_INTERACTION_BYTES:
        return None
    return {
        "protocol": protocol,
        "callback_label": session.callback_label,
        "provider_event_id": sha256(canonical).hexdigest(),
        "observed_at": str(interaction.get("timestamp") or ""),
        "details": details,
    }


__all__ = ["normalize_oast_provider_interaction"]
