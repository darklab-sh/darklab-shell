# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded Nuclei takeover evidence from app-reviewed launch context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from services.assessments.nuclei_takeover_identity import (
    NUCLEI_TAKEOVER_JSON_PARSER_VERSION,
    canonical_nuclei_matched_hostname,
    nuclei_takeover_observation_id,
)


_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_TEMPLATE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,159}\Z")
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}\Z")


@dataclass(frozen=True)
class ReviewedNucleiTakeoverTemplate:
    template_id: str
    template_version: str
    template_digest: str
    policy_level: str

    def __post_init__(self) -> None:
        if (
            not all(isinstance(value, str) for value in (
                self.template_id,
                self.template_version,
                self.template_digest,
                self.policy_level,
            ))
            or not _TEMPLATE_ID_RE.fullmatch(self.template_id)
            or not _VERSION_RE.fullmatch(self.template_version)
            or not _DIGEST_RE.fullmatch(self.template_digest)
            or self.policy_level not in {"safe", "standard"}
        ):
            raise ValueError("invalid reviewed Nuclei takeover template")

    def registry_entry(self) -> dict[str, str]:
        return {
            "template_version": self.template_version,
            "template_digest": self.template_digest,
            "policy_level": self.policy_level,
        }


def normalize_nuclei_takeover_observation(
    record: dict[str, Any] | None,
    *,
    source_run_id: str,
    template: ReviewedNucleiTakeoverTemplate | None,
) -> dict[str, str] | None:
    """Use trusted template context; never accept version or policy from output."""
    item = record if isinstance(record, dict) else {}
    run_id = _text(source_run_id, 128)
    if not _RUN_ID_RE.fullmatch(run_id) or template is None:
        return None
    if _text(item.get("template-id") or item.get("template_id"), 160) != template.template_id:
        return None
    hostname = canonical_nuclei_matched_hostname(
        item.get("matched-at") or item.get("matched_at") or item.get("host") or item.get("url")
    )
    observed_at = _text(item.get("timestamp"), 64)
    if not hostname or not _aware_timestamp(observed_at):
        return None
    return {
        "observation_id": nuclei_takeover_observation_id(
            run_id,
            hostname,
            observed_at,
            template.template_id,
            template.template_version,
            template.template_digest,
            template.policy_level,
        ),
        "parser_version": NUCLEI_TAKEOVER_JSON_PARSER_VERSION,
        "adapter": "nuclei",
        "match_state": "matched",
        "template_id": template.template_id,
        "template_version": template.template_version,
        "template_digest": template.template_digest,
        "policy_level": template.policy_level,
        "source_run_id": run_id,
        "matched_hostname": hostname,
        "observed_at": observed_at,
    }


def nuclei_takeover_json_metadata(
    record: dict[str, Any] | None,
    *,
    source_run_id: str,
    template: ReviewedNucleiTakeoverTemplate | None,
) -> dict[str, list[dict[str, str]]]:
    observation = normalize_nuclei_takeover_observation(
        record,
        source_run_id=source_run_id,
        template=template,
    )
    return {"nuclei_takeover_observations": [observation]} if observation else {}


def _aware_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text if len(text) <= limit and not any(ord(char) < 32 for char in raw) else ""


__all__ = [
    "ReviewedNucleiTakeoverTemplate",
    "normalize_nuclei_takeover_observation",
    "nuclei_takeover_json_metadata",
]
