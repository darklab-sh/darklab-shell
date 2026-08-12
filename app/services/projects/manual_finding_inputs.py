# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Strict input contracts for assessor-authored findings."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from services.projects.contracts import MAX_ENTITY_ID_LEN, MAX_FINDING_TITLE_LEN, ProjectWorkspaceError
from services.projects.finding_details import (
    FINDING_CONFIDENCE_LEVELS,
    MAX_FINDING_CVSS_VECTOR_LEN,
    MAX_FINDING_IDENTIFIER_COUNT,
    MAX_FINDING_IMPACT_LEN,
    MAX_FINDING_REFERENCE_COUNT,
    MAX_FINDING_REFERENCE_LEN,
    MAX_FINDING_REPRODUCTION_STEPS_LEN,
    MAX_FINDING_SUMMARY_LEN,
)


FINDING_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
MAX_INITIAL_EVIDENCE_LINKS = 20
_CREATE_FIELDS = frozenset({
    "target_id", "title", "severity", "summary", "impact", "reproduction_steps",
    "confidence", "cve_ids", "cwe_ids", "cvss_vector", "cvss_score", "references",
    "evidence", "allow_duplicate",
})
_UPDATE_FIELDS = frozenset({
    "expected_revision", "title", "severity", "summary", "impact", "reproduction_steps",
    "confidence", "cve_ids", "cwe_ids", "cvss_vector", "cvss_score", "references",
    "allow_duplicate",
})
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$")
_CWE_RE = re.compile(r"^CWE-\d+$")
_CVSS_RE = re.compile(
    r"^(?:CVSS:(?:2\.0|3\.[01]|4\.0)/)?"
    r"[A-Za-z]{1,4}:[A-Za-z0-9.-]+(?:/[A-Za-z]{1,4}:[A-Za-z0-9.-]+)+$"
)


def _object(data: Any, allowed: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ProjectWorkspaceError(f"{label} payload must be a JSON object")
    unsupported = sorted(set(data) - allowed)
    if unsupported:
        raise ProjectWorkspaceError(f"{label} payload contains unsupported fields")
    return data


def _text(value: Any, *, name: str, limit: int, required: bool = False) -> str:
    if value is not None and not isinstance(value, str):
        raise ProjectWorkspaceError(f"manual finding {name} must be a string")
    normalized = str(value or "").strip()
    if required and not normalized:
        raise ProjectWorkspaceError(f"manual finding {name} is required")
    if len(normalized) > limit:
        raise ProjectWorkspaceError(f"manual finding {name} exceeds {limit} characters")
    return normalized


def _boolean(data: dict[str, Any], name: str) -> bool:
    value = data.get(name, False)
    if not isinstance(value, bool):
        raise ProjectWorkspaceError(f"manual finding {name} must be a boolean")
    return value


def _identifiers(value: Any, *, name: str, pattern: re.Pattern[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProjectWorkspaceError(f"manual finding {name} must be an array")
    if len(value) > MAX_FINDING_IDENTIFIER_COUNT:
        raise ProjectWorkspaceError(
            f"manual finding {name} exceeds {MAX_FINDING_IDENTIFIER_COUNT} items"
        )
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not pattern.fullmatch(item.strip().upper()):
            raise ProjectWorkspaceError(f"manual finding {name} contains an invalid identifier")
        identifier = item.strip().upper()
        if identifier not in result:
            result.append(identifier)
    return result


def _references(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProjectWorkspaceError("manual finding references must be an array")
    if len(value) > MAX_FINDING_REFERENCE_COUNT:
        raise ProjectWorkspaceError(
            f"manual finding references exceeds {MAX_FINDING_REFERENCE_COUNT} items"
        )
    result: list[str] = []
    for item in value:
        reference = _text(item, name="reference", limit=MAX_FINDING_REFERENCE_LEN, required=True)
        parsed = urlsplit(reference)
        if (
            "\\" in reference
            or any(ord(char) < 32 for char in reference)
            or parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ProjectWorkspaceError("manual finding references must use safe HTTP(S) URLs")
        if reference not in result:
            result.append(reference)
    return result


def _details(data: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(existing or {})
    merged.update({key: data[key] for key in (
        "summary", "impact", "reproduction_steps", "confidence", "cve_ids", "cwe_ids",
        "cvss_vector", "cvss_score", "references",
    ) if key in data})
    confidence = _text(merged.get("confidence", "unknown"), name="confidence", limit=16).lower()
    if confidence not in FINDING_CONFIDENCE_LEVELS:
        raise ProjectWorkspaceError("manual finding confidence is unsupported")
    cvss_vector = _text(
        merged.get("cvss_vector"), name="cvss_vector", limit=MAX_FINDING_CVSS_VECTOR_LEN
    )
    if cvss_vector and not _CVSS_RE.fullmatch(cvss_vector):
        raise ProjectWorkspaceError("manual finding cvss_vector is invalid")
    raw_score = merged.get("cvss_score")
    if raw_score in (None, ""):
        cvss_score = None
    else:
        if isinstance(raw_score, bool):
            raise ProjectWorkspaceError("manual finding cvss_score must be a number")
        try:
            cvss_score = float(raw_score)
        except (TypeError, ValueError) as exc:
            raise ProjectWorkspaceError("manual finding cvss_score must be a number") from exc
        if not 0 <= cvss_score <= 10:
            raise ProjectWorkspaceError("manual finding cvss_score must be between 0 and 10")
    return {
        "summary": _text(merged.get("summary"), name="summary", limit=MAX_FINDING_SUMMARY_LEN),
        "impact": _text(merged.get("impact"), name="impact", limit=MAX_FINDING_IMPACT_LEN),
        "reproduction_steps": _text(
            merged.get("reproduction_steps"),
            name="reproduction_steps",
            limit=MAX_FINDING_REPRODUCTION_STEPS_LEN,
        ),
        "confidence": confidence,
        "cve_ids": _identifiers(merged.get("cve_ids"), name="cve_ids", pattern=_CVE_RE),
        "cwe_ids": _identifiers(merged.get("cwe_ids"), name="cwe_ids", pattern=_CWE_RE),
        "cvss_vector": cvss_vector,
        "cvss_score": cvss_score,
        "references": _references(merged.get("references")),
    }


def normalize_manual_finding_create(data: Any) -> dict[str, Any]:
    payload = _object(data, _CREATE_FIELDS, "manual finding")
    target_id = _text(payload.get("target_id"), name="target_id", limit=MAX_ENTITY_ID_LEN, required=True)
    title = _text(payload.get("title"), name="title", limit=MAX_FINDING_TITLE_LEN, required=True)
    severity = _text(payload.get("severity"), name="severity", limit=16, required=True).lower()
    if severity not in FINDING_SEVERITIES:
        raise ProjectWorkspaceError("manual finding severity is unsupported")
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list):
        raise ProjectWorkspaceError("manual finding evidence must be an array")
    if len(evidence) > MAX_INITIAL_EVIDENCE_LINKS:
        raise ProjectWorkspaceError(
            f"manual finding evidence exceeds {MAX_INITIAL_EVIDENCE_LINKS} items"
        )
    return {
        "target_id": target_id,
        "title": title,
        "severity": severity,
        **_details(payload),
        "evidence": evidence,
        "allow_duplicate": _boolean(payload, "allow_duplicate"),
    }


def normalize_manual_finding_update(
    data: Any,
    *,
    existing: dict[str, Any],
) -> dict[str, Any]:
    payload = _object(data, _UPDATE_FIELDS, "manual finding update")
    if "expected_revision" not in payload:
        raise ProjectWorkspaceError("manual finding expected_revision is required")
    if isinstance(payload["expected_revision"], bool) or not isinstance(
        payload["expected_revision"], int
    ):
        raise ProjectWorkspaceError("manual finding expected_revision must be an integer")
    expected_revision = payload["expected_revision"]
    if expected_revision < 0:
        raise ProjectWorkspaceError("manual finding expected_revision must be non-negative")
    editable_fields = _UPDATE_FIELDS - {"expected_revision", "allow_duplicate"}
    if not any(field in payload for field in editable_fields):
        raise ProjectWorkspaceError("manual finding update requires an editable field")
    title = _text(
        payload.get("title", existing.get("title")),
        name="title",
        limit=MAX_FINDING_TITLE_LEN,
        required=True,
    )
    severity = _text(
        payload.get("severity", existing.get("severity")), name="severity", limit=16, required=True
    ).lower()
    if severity not in FINDING_SEVERITIES:
        raise ProjectWorkspaceError("manual finding severity is unsupported")
    return {
        "expected_revision": expected_revision,
        "title": title,
        "severity": severity,
        **_details(payload, existing=existing),
        "allow_duplicate": _boolean(payload, "allow_duplicate"),
    }
