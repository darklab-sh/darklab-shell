# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Safe provenance shaping for project relationships.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from core.database import PROJECT_LINK_SOURCES
from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend


PROJECT_PROVENANCE_SCHEMA_VERSION = 1

PROJECT_LINK_SOURCE_UNKNOWN = "unknown"

SAFE_PROJECT_LINK_SOURCE_DETAIL_KEYS = frozenset({
    "candidate_count",
    "category",
    "kind",
    "limit",
    "linked_count",
    "match_count",
    "match_mode",
    "matched_count",
    "rule_id",
    "skipped_count",
    "source_category",
    "source_kind",
    "target_entity_kind",
    "truncated",
    "value_type",
})


def _decode_source_detail(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    try:
        return dialect_for_backend(get_db_backend()).decode_json_dict(value)
    except (TypeError, ValueError):
        return {}


def _safe_detail_value(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if value == value and value not in {float("inf"), float("-inf")} else None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped[:160] if stripped else ""
    return None


def safe_project_link_source_detail(source_detail: Any) -> dict[str, Any]:
    """Return the bounded, customer-safe subset of a project-link source_detail blob."""
    decoded = _decode_source_detail(source_detail)
    safe: dict[str, Any] = {}
    for key in sorted(SAFE_PROJECT_LINK_SOURCE_DETAIL_KEYS):
        if key not in decoded:
            continue
        value = _safe_detail_value(decoded[key])
        if value not in (None, ""):
            safe[key] = value
    return safe


def normalized_project_link_origin(source: Any) -> str:
    normalized = str(source or "manual").strip() or "manual"
    if normalized in PROJECT_LINK_SOURCES:
        return normalized
    return PROJECT_LINK_SOURCE_UNKNOWN


def project_link_provenance(
    source: Any,
    *,
    source_detail: Any = None,
    confidence: Any = None,
    review_state: Any = None,
    link_id: Any = None,
    entity_type: Any = None,
    entity_id: Any = None,
    created: Any = None,
) -> dict[str, Any]:
    provenance = {
        "schema_version": PROJECT_PROVENANCE_SCHEMA_VERSION,
        "origin": normalized_project_link_origin(source),
        "confidence": _safe_confidence(confidence),
        "review_state": str(review_state or "").strip(),
        "source_detail": safe_project_link_source_detail(source_detail),
    }
    optional = {
        "link_id": link_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "created": created,
    }
    for key, value in optional.items():
        text = str(value or "").strip()
        if text:
            provenance[key] = text
    return provenance


def _safe_confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 1.0
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return 1.0
    return max(0.0, min(1.0, parsed))


def finding_target_reference(target: dict[str, Any]) -> dict[str, Any]:
    raw_provenance = target.get("provenance")
    provenance: dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
    origin = str(provenance.get("origin") or target.get("source") or "manual").strip() or "manual"
    reference = {
        "target_id": str(target.get("id") or ""),
        "entity_id": str(target.get("id") or ""),
        "type": str(target.get("type") or "target"),
        "value": str(target.get("value") or target.get("canonical_value") or ""),
        "source_run_id": str(target.get("source_run_id") or ""),
        "relationship_source": origin,
        "relationship_reason": _relationship_reason(origin),
        "confidence": _safe_confidence(provenance.get("confidence", target.get("confidence"))),
        "review_state": str(provenance.get("review_state") or target.get("review_state") or "").strip(),
    }
    source_detail = provenance.get("source_detail")
    if isinstance(source_detail, dict) and source_detail:
        reference["source_detail"] = dict(source_detail)
    return reference


def attach_finding_target_references(
    findings: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets_by_id = {
        str(target.get("id") or ""): target
        for target in targets
        if isinstance(target, dict) and str(target.get("id") or "")
    }
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        references = []
        seen = set()
        for target_id in _finding_target_ids(finding):
            target = targets_by_id.get(target_id)
            if not target:
                continue
            reference = finding_target_reference(target)
            ref_id = str(reference.get("target_id") or "")
            if ref_id and ref_id not in seen:
                seen.add(ref_id)
                references.append(reference)
        if not references:
            for target in targets_by_id.values():
                target_id = str(target.get("id") or "")
                if target_id in seen or not _finding_mentions_target(finding, target):
                    continue
                reference = finding_target_reference(target)
                ref_id = str(reference.get("target_id") or "")
                if ref_id:
                    seen.add(ref_id)
                    references.append(reference)
        finding["target_references"] = references
    return findings


def _finding_target_ids(finding: dict[str, Any]) -> list[str]:
    target_ids = []
    for key in ("target_id", "entity_id"):
        value = str(finding.get(key) or "")
        if value and value not in target_ids:
            target_ids.append(value)
    raw_target_ids = finding.get("target_ids")
    if isinstance(raw_target_ids, list):
        for target_id in raw_target_ids:
            value = str(target_id or "")
            if value and value not in target_ids:
                target_ids.append(value)
    return target_ids


def _finding_mentions_target(finding: dict[str, Any], target: dict[str, Any]) -> bool:
    values = _target_match_values(target)
    if not values:
        return False
    haystack = " ".join(
        str(finding.get(key) or "")
        for key in ("raw_line", "title", "subject_key", "run_command")
    ).lower()
    target_type = str(target.get("type") or "").strip().lower()
    return any(_target_value_matches_text(value, haystack, target_type) for value in values)


def _target_match_values(target: dict[str, Any]) -> list[str]:
    values = []
    target_type = str(target.get("type") or "").strip().lower()
    for key in ("value", "canonical_value"):
        value = str(target.get(key) or "").strip().lower()
        if target_type == "domain":
            value = value.rstrip(".")
        if value and value not in values:
            values.append(value)
    return values


def _target_value_matches_text(value: str, haystack: str, target_type: str) -> bool:
    escaped = re.escape(value)
    if target_type == "domain":
        # Match apex domains as their own hostname token. This avoids attaching
        # example.com to notexample.com, www.example.com, or example.com.evil.
        pattern = rf"(?<![a-z0-9_-])(?<![a-z0-9_-]\.){escaped}(?![a-z0-9_-])(?!\.[a-z0-9_-])"
        return re.search(pattern, haystack, re.IGNORECASE) is not None
    if target_type == "url":
        return _bounded_literal_match(value, haystack, r"a-z0-9._~:/?#\[\]@!$&'()*+,;=%-")
    try:
        parsed_ip = ipaddress.ip_address(value)
    except ValueError:
        parsed_ip = None
    if parsed_ip:
        if parsed_ip.version == 4:
            pattern = rf"(?<![a-z0-9])(?<!\d\.){escaped}(?![a-z0-9])(?!\.\d)"
        else:
            pattern = rf"(?<![a-f0-9:.]){escaped}(?![a-f0-9:.])"
        return re.search(pattern, haystack, re.IGNORECASE) is not None
    return _bounded_literal_match(value, haystack, r"a-z0-9_.-")


def _bounded_literal_match(value: str, haystack: str, token_chars: str) -> bool:
    escaped = re.escape(value)
    pattern = rf"(?<![{token_chars}]){escaped}(?![{token_chars}])"
    return re.search(pattern, haystack, re.IGNORECASE) is not None


def _relationship_reason(origin: str) -> str:
    return {
        "active_project": "Linked while this project was active.",
        "auto_command": "Discovered from linked command output.",
        "auto_input_file": "Discovered from a linked run input file.",
        "auto_promote_rule": "Confirmed by a project auto-promote rule.",
        "manual": "Selected in the project by an operator.",
        "migration": "Carried forward from older project data.",
        "package_flow": "Selected during package assembly.",
    }.get(origin, "Relationship source was not recorded.")
