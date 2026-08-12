# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded rich-detail contracts for saved findings."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend


FINDING_CONFIDENCE_LEVELS = frozenset({"unknown", "low", "medium", "high"})
MAX_FINDING_SUMMARY_LEN = 4000
MAX_FINDING_IMPACT_LEN = 20000
MAX_FINDING_REPRODUCTION_STEPS_LEN = 20000
MAX_FINDING_IDENTIFIER_COUNT = 50
MAX_FINDING_REFERENCE_COUNT = 50
MAX_FINDING_REFERENCE_LEN = 2048
MAX_FINDING_CVSS_VECTOR_LEN = 256

_CVE_ID_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")
_CWE_ID_RE = re.compile(r"^CWE-\d+$")
_CVSS_VECTOR_RE = re.compile(
    r"^(?:CVSS:(?:2\.0|3\.[01]|4\.0)/)?"
    r"[A-Za-z]{1,4}:[A-Za-z0-9.-]+(?:/[A-Za-z]{1,4}:[A-Za-z0-9.-]+)+$"
)


def _row_value(row: Any, key: str, default: Any = "") -> Any:
    if not row or not hasattr(row, "keys") or key not in row.keys():
        return default
    value = row[key]
    return default if value is None else value


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def normalize_finding_confidence(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in FINDING_CONFIDENCE_LEVELS else "unknown"


def _normalized_identifiers(value: Any, pattern: re.Pattern[str]) -> list[str]:
    items = dialect_for_backend(get_db_backend()).decode_json_list(value)
    normalized: list[str] = []
    for item in items:
        identifier = str(item or "").strip().upper()
        if pattern.fullmatch(identifier) and identifier not in normalized:
            normalized.append(identifier)
        if len(normalized) >= MAX_FINDING_IDENTIFIER_COUNT:
            break
    return normalized


def _normalized_references(value: Any) -> list[str]:
    items = dialect_for_backend(get_db_backend()).decode_json_list(value)
    normalized: list[str] = []
    for item in items:
        reference = _bounded_text(item, MAX_FINDING_REFERENCE_LEN)
        if not reference or "\\" in reference or any(ord(char) < 32 for char in reference):
            continue
        parsed = urlsplit(reference)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            continue
        if reference not in normalized:
            normalized.append(reference)
        if len(normalized) >= MAX_FINDING_REFERENCE_COUNT:
            break
    return normalized


def _normalized_cvss_score(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 10 else None


def _normalized_cvss_vector(value: Any) -> str:
    vector = _bounded_text(value, MAX_FINDING_CVSS_VECTOR_LEN)
    return vector if _CVSS_VECTOR_RE.fullmatch(vector) else ""


def finding_detail_fields(row: Any) -> dict[str, Any]:
    """Return a stable, defensive detail payload from a finding row."""

    return {
        "summary": _bounded_text(_row_value(row, "summary"), MAX_FINDING_SUMMARY_LEN),
        "impact": _bounded_text(_row_value(row, "impact"), MAX_FINDING_IMPACT_LEN),
        "reproduction_steps": _bounded_text(
            _row_value(row, "reproduction_steps"),
            MAX_FINDING_REPRODUCTION_STEPS_LEN,
        ),
        "confidence": normalize_finding_confidence(_row_value(row, "confidence", "unknown")),
        "cve_ids": _normalized_identifiers(_row_value(row, "cve_ids_json", []), _CVE_ID_RE),
        "cwe_ids": _normalized_identifiers(_row_value(row, "cwe_ids_json", []), _CWE_ID_RE),
        "cvss_vector": _normalized_cvss_vector(_row_value(row, "cvss_vector")),
        "cvss_score": _normalized_cvss_score(_row_value(row, "cvss_score", None)),
        "references": _normalized_references(_row_value(row, "references_json", [])),
    }


def manual_finding_fields(row: Any) -> dict[str, Any]:
    """Return public manual-edit metadata without exposing session identifiers."""

    try:
        revision = max(0, int(_row_value(row, "manual_revision", 0) or 0))
    except (TypeError, ValueError):
        revision = 0
    return {
        "manual_revision": revision,
        "manual_created_by_member_id": _bounded_text(
            _row_value(row, "manual_created_by_member_id"), 128
        ),
        "manual_updated_by_member_id": _bounded_text(
            _row_value(row, "manual_updated_by_member_id"), 128
        ),
        "manual_updated_at": _bounded_text(_row_value(row, "manual_updated_at"), 64),
    }
