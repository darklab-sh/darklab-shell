# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalize private OAST callbacks into small, redacted evidence records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any
from urllib.parse import urlsplit


_PROTOCOLS = frozenset({"dns", "http", "smtp", "ldap"})
_TOP_LEVEL_FIELDS = frozenset({
    "protocol",
    "callback_label",
    "provider_event_id",
    "observed_at",
    "details",
})
_SAFE_FIELDS = {
    "dns": {"query_name": 253, "query_type": 16},
    "http": {"method": 16, "path": 256},
    "smtp": {"command": 16, "recipient_domain": 253},
    "ldap": {"operation": 16},
}
_CALLBACK_LABEL_RE = re.compile(r"[a-z0-9]{33}")
_DNS_NAME_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9_-]{0,15}")
_MAX_INPUT_BYTES = 65536
_MAX_PROVIDER_EVENT_ID = 512
_MAX_DETAIL_FIELDS = 64
_MAX_SUMMARY_BYTES = 2048


class OastInteractionReviewError(ValueError):
    """Raised when normalized callback input isn't safe to retain."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReviewedOastInteraction:
    protocol: str
    callback_label: str
    provider_event_sha256: str
    event_fingerprint: str
    observed_at: str
    summary: dict[str, str]
    redacted_field_count: int
    truncated_field_count: int


def _timestamp(value: object) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OastInteractionReviewError(
            "oast_interaction_time_invalid",
            "The OAST interaction timestamp is invalid",
        ) from exc
    if parsed.tzinfo is None:
        raise OastInteractionReviewError(
            "oast_interaction_time_invalid",
            "The OAST interaction timestamp must include a timezone",
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _bounded_input(payload: Mapping[str, object]) -> None:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OastInteractionReviewError(
            "oast_interaction_invalid",
            "The OAST interaction payload is invalid",
        ) from exc
    if len(encoded) > _MAX_INPUT_BYTES:
        raise OastInteractionReviewError(
            "oast_interaction_too_large",
            "The OAST interaction payload exceeds the review limit",
        )


def _normalized_dns_name(value: object, field: str) -> str:
    text = str(value or "").strip().lower().rstrip(".")
    if text and not _DNS_NAME_RE.fullmatch(text):
        raise OastInteractionReviewError(
            "oast_interaction_invalid",
            f"The OAST interaction {field} is invalid",
        )
    return text


def _normalized_token(value: object, field: str) -> str:
    text = str(value or "").strip().upper()
    if text and not _TOKEN_RE.fullmatch(text):
        raise OastInteractionReviewError(
            "oast_interaction_invalid",
            f"The OAST interaction {field} is invalid",
        )
    return text


def _safe_value(protocol: str, field: str, value: object) -> tuple[str, int, int]:
    redacted = 0
    truncated = 0
    if field in {"query_name", "recipient_domain"}:
        text = _normalized_dns_name(value, field)
    elif field in {"query_type", "method", "command", "operation"}:
        text = _normalized_token(value, field)
    elif field == "path":
        raw = str(value or "").strip()
        if raw and (not raw.startswith("/") or any(ord(char) < 32 for char in raw)):
            raise OastInteractionReviewError(
                "oast_interaction_invalid",
                "The OAST interaction path is invalid",
            )
        split = urlsplit(raw)
        text = split.path or "/"
        redacted = int(bool(split.query or split.fragment))
    else:
        text = str(value or "").strip()
    maximum = _SAFE_FIELDS[protocol][field]
    if len(text) > maximum:
        text = text[:maximum]
        truncated = 1
    return text, redacted, truncated


def review_oast_interaction(payload: object) -> ReviewedOastInteraction:
    """Return only the bounded callback fields safe for durable evidence."""
    if not isinstance(payload, Mapping):
        raise OastInteractionReviewError(
            "oast_interaction_invalid",
            "The OAST interaction payload must be an object",
        )
    if set(payload) - _TOP_LEVEL_FIELDS:
        raise OastInteractionReviewError(
            "oast_interaction_invalid",
            "The OAST interaction payload contains unsupported fields",
        )
    _bounded_input(payload)
    protocol = str(payload.get("protocol") or "").strip().lower()
    if protocol not in _PROTOCOLS:
        raise OastInteractionReviewError(
            "oast_interaction_protocol_invalid",
            "The OAST interaction protocol is unsupported",
        )
    callback_label = str(payload.get("callback_label") or "").strip().lower()
    if not _CALLBACK_LABEL_RE.fullmatch(callback_label):
        raise OastInteractionReviewError(
            "oast_interaction_callback_invalid",
            "The OAST interaction callback label is invalid",
        )
    provider_event_id = str(payload.get("provider_event_id") or "")
    if len(provider_event_id) > _MAX_PROVIDER_EVENT_ID:
        raise OastInteractionReviewError(
            "oast_interaction_invalid",
            "The OAST provider event id exceeds the review limit",
        )
    details = payload.get("details", {})
    if not isinstance(details, Mapping) or len(details) > _MAX_DETAIL_FIELDS:
        raise OastInteractionReviewError(
            "oast_interaction_invalid",
            "The OAST interaction details are invalid",
        )
    allowed = _SAFE_FIELDS[protocol]
    summary: dict[str, str] = {}
    redacted_count = 0
    truncated_count = 0
    for raw_key, value in details.items():
        if not isinstance(raw_key, str):
            raise OastInteractionReviewError(
                "oast_interaction_invalid",
                "The OAST interaction detail names are invalid",
            )
        key = raw_key.strip().lower()
        if key not in allowed:
            redacted_count += 1
            continue
        text, redacted, truncated = _safe_value(protocol, key, value)
        redacted_count += redacted
        truncated_count += truncated
        if text:
            summary[key] = text
    if len(json.dumps(summary, separators=(",", ":"), sort_keys=True).encode()) > _MAX_SUMMARY_BYTES:
        raise OastInteractionReviewError(
            "oast_interaction_too_large",
            "The redacted OAST interaction summary exceeds the storage limit",
        )
    observed_at = _timestamp(payload.get("observed_at"))
    provider_hash = (
        sha256(provider_event_id.encode("utf-8")).hexdigest()
        if provider_event_id
        else ""
    )
    identity: dict[str, Any] = {
        "callback_label": callback_label,
        "observed_at": observed_at,
        "protocol": protocol,
        "summary": summary,
    }
    if provider_hash:
        identity = {"callback_label": callback_label, "provider_event_sha256": provider_hash}
    fingerprint = sha256(
        json.dumps(identity, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return ReviewedOastInteraction(
        protocol=protocol,
        callback_label=callback_label,
        provider_event_sha256=provider_hash,
        event_fingerprint=fingerprint,
        observed_at=observed_at,
        summary=summary,
        redacted_field_count=redacted_count,
        truncated_field_count=truncated_count,
    )


__all__ = [
    "OastInteractionReviewError",
    "ReviewedOastInteraction",
    "review_oast_interaction",
]
