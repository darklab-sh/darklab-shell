# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fail-closed inputs for persisting one version-inference candidate."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any


_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")
_SOURCE_KINDS = {"run", "import"}
_MATCH_BASES = {"exact_cpe_version", "exact_cpe_nvd_range", "exact_cpe_all_versions"}
_RANGE_TYPES = {"EXACT", "CPE_NUMERIC", "CPE_ALL"}


def normalize_version_inference_candidate(candidate: Any) -> dict[str, str] | None:
    """Return one provenance-complete stored-NVD candidate or fail closed."""
    if not isinstance(candidate, dict) or candidate.get("validation_method") != "version_inference":
        return None
    source = candidate.get("source")
    if not isinstance(source, dict):
        return None
    source_kind = _text(source.get("kind"), 16).lower()
    source_id = _text(source.get("run_id" if source_kind == "run" else "batch_id"), 128)
    record = {
        "source_kind": source_kind,
        "source_id": source_id,
        "observation_id": _text(source.get("observation_id"), 128),
        "target": _text(candidate.get("target"), 512),
        "observed_identifier": _text(candidate.get("observed_identifier"), 512),
        "observed_version": _text(candidate.get("observed_version"), 128),
        "tool_version": _text(source.get("tool_version"), 128),
        "parser_version": _text(source.get("parser_version"), 128),
        "observed_at": _timestamp(source.get("observed_at")),
        "match_basis": _text(candidate.get("match_basis"), 64),
        "affected_range": _text(candidate.get("affected_range"), 256),
        "range_type": _text(candidate.get("range_type"), 32),
        "confidence": _text(candidate.get("confidence"), 32).lower(),
        "vulnerability_id": _text(candidate.get("vulnerability_id"), 128).upper(),
        "advisory_source": _text(candidate.get("advisory_source"), 32).lower(),
        "advisory_source_version": _text(candidate.get("advisory_source_version"), 128),
        "advisory_origin": _text(candidate.get("advisory_origin"), 32).lower(),
        "advisory_expires_at": _optional_timestamp(candidate.get("advisory_expires_at")),
        "advisory_source_state": _text(candidate.get("advisory_source_state"), 32).lower(),
        "advisory_criteria": _text(candidate.get("advisory_criteria"), 1024),
        "advisory_match_criteria_id": _text(candidate.get("advisory_match_criteria_id"), 128),
    }
    required = tuple(value for key, value in record.items() if key != "advisory_expires_at")
    if not all(required):
        return None
    if source_kind not in _SOURCE_KINDS or record["match_basis"] not in _MATCH_BASES:
        return None
    if record["range_type"] not in _RANGE_TYPES or record["confidence"] != "high":
        return None
    if not _CVE_RE.fullmatch(record["vulnerability_id"]):
        return None
    if record["advisory_source"] != "nvd" or record["advisory_origin"] not in {"local", "external"}:
        return None
    if record["advisory_source_state"] not in {"current", "stale", "unknown"}:
        return None
    return record


def _timestamp(value: Any) -> str:
    text = _text(value, 64)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return text if parsed.tzinfo is not None else ""


def _optional_timestamp(value: Any) -> str:
    text = _text(value, 64)
    return _timestamp(text) if text else ""


def _text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit or any(ord(char) < 32 for char in text):
        return ""
    return text


__all__ = ["normalize_version_inference_candidate"]
