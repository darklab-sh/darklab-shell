# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable identity and host normalization for Nuclei takeover evidence."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit


NUCLEI_TAKEOVER_JSON_PARSER_VERSION = "nuclei-takeover-json-v1"


def canonical_nuclei_matched_hostname(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" in text:
        try:
            parsed = urlsplit(text)
        except ValueError:
            return ""
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.fragment:
            return ""
        text = str(parsed.hostname or "")
    text = text.casefold().rstrip(".")
    if not text or len(text) > 253 or any(char in text for char in "/:@?#\\"):
        return ""
    try:
        encoded = text.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    labels = encoded.split(".")
    if len(labels) < 2 or any(
        not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
        for label in labels
    ):
        return ""
    return encoded if all(re.fullmatch(r"[a-z0-9-]+", label) for label in labels) else ""


def nuclei_takeover_observation_id(
    run_id: str,
    hostname: str,
    observed_at: str,
    template_id: str,
    template_version: str,
    template_digest: str,
    policy_level: str,
) -> str:
    source = "\x1f".join((
        run_id,
        hostname,
        observed_at,
        template_id,
        template_version,
        template_digest,
        policy_level,
    ))
    return "nucobs_" + hashlib.sha256(source.encode()).hexdigest()[:32]


__all__ = [
    "NUCLEI_TAKEOVER_JSON_PARSER_VERSION",
    "canonical_nuclei_matched_hostname",
    "nuclei_takeover_observation_id",
]
