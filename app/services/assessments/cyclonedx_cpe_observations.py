# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded exact product observations from CycloneDX component CPEs."""

from __future__ import annotations

import hashlib
from typing import Any

from services.assessments.cpe_applicability import normalize_observed_cpe
from services.assessments.cyclonedx_component_document import (
    parse_cyclonedx_component_document,
)


CYCLONEDX_CPE_PARSER_VERSION = "cyclonedx-cpe-v1"
CYCLONEDX_MAX_CPE_OBSERVATIONS = 256


def parse_cyclonedx_cpe_observations(
    payload: bytes | str,
    *,
    source_batch_id: str,
    observed_at: str = "",
) -> dict[str, Any]:
    """Return exact versioned component CPEs without creating inventory or findings."""
    batch_id = _text(source_batch_id, 128)
    if not batch_id:
        return _empty(batch_id=batch_id)
    document = parse_cyclonedx_component_document(payload, observed_at=observed_at)
    spec_version = document["spec_version"]
    timestamp = document["observed_at"]
    if not spec_version or not timestamp:
        return _empty(batch_id=batch_id)
    truncated = document["truncated"]
    observations: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in document["components"]:
        component = value if isinstance(value, dict) else {}
        cpe = _text(component.get("cpe"), 512)
        normalized = normalize_observed_cpe(cpe, explicit_version=component.get("version"))
        if normalized is None or cpe in seen:
            continue
        if len(observations) >= CYCLONEDX_MAX_CPE_OBSERVATIONS:
            truncated = True
            break
        seen.add(cpe)
        observations.append({
            "observation_id": _observation_id(batch_id, cpe),
            "target": cpe,
            "cpe": cpe,
            "version": str(normalized["version"]),
            "component_name": _text(component.get("name"), 256),
            "component_type": _text(component.get("type"), 64),
            "component_purl": _text(component.get("purl"), 512),
            "bom_ref": _text(component.get("bom-ref"), 512),
            "source_batch_id": batch_id,
            "observed_at": timestamp,
            "tool_version": f"CycloneDX {spec_version}",
            "parser_version": CYCLONEDX_CPE_PARSER_VERSION,
        })
    return {
        "source": "cyclonedx_json",
        "source_batch_id": batch_id,
        "tool_version": f"CycloneDX {spec_version}",
        "parser_version": CYCLONEDX_CPE_PARSER_VERSION,
        "observed_at": timestamp,
        "observations": observations,
        "truncated": truncated,
    }


def _observation_id(batch_id: str, cpe: str) -> str:
    digest = hashlib.sha256(f"{batch_id}\x1f{cpe}".encode()).hexdigest()
    return "obs_" + digest[:32]


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text if text and len(text) <= limit and not any(ord(char) < 32 for char in raw) else ""


def _empty(*, batch_id: str = "") -> dict[str, Any]:
    return {
        "source": "cyclonedx_json", "source_batch_id": batch_id, "tool_version": "",
        "parser_version": CYCLONEDX_CPE_PARSER_VERSION, "observed_at": "",
        "observations": [], "truncated": False,
    }


__all__ = [
    "CYCLONEDX_CPE_PARSER_VERSION",
    "CYCLONEDX_MAX_CPE_OBSERVATIONS",
    "parse_cyclonedx_cpe_observations",
]
