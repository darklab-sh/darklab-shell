# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded SARIF 2.1 result normalization for Atlas imports."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit


def parse_sarif_json(payload, state, entities, findings) -> None:
    """Append safe SARIF results to the shared Atlas parser collections."""
    from services.atlas.import_parser import (
        ImportParseError, _make_finding, _normalize_severity, _safe_text,
    )
    try:
        document = json.loads(payload.decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ImportParseError("SARIF report could not be decoded.") from exc
    if not isinstance(document, dict) or document.get("version") != "2.1.0":
        raise ImportParseError("SARIF report must declare version 2.1.0.")
    runs = document.get("runs")
    if not isinstance(runs, list):
        raise ImportParseError("SARIF report is missing a runs array.")
    for run in runs:
        if not isinstance(run, dict):
            state.warn(state.next_row(), "invalid_sarif_run", "SARIF run must be an object.")
            continue
        tool = run.get("tool") if isinstance(run.get("tool"), dict) else {}
        driver = tool.get("driver") if isinstance(tool.get("driver"), dict) else {}
        tool_name = _safe_text(driver.get("name"), limit=128) or "SARIF tool"
        tool_version = _safe_text(driver.get("version"), limit=128)
        rules = {
            str(rule.get("id")): rule for rule in driver.get("rules", [])
            if isinstance(rule, dict) and _safe_text(rule.get("id"), limit=256)
        }
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for result in results:
            row_number = state.next_row()
            if not isinstance(result, dict):
                state.warn(row_number, "invalid_sarif_result", "SARIF result must be an object.")
                continue
            rule_id = _safe_text(result.get("ruleId"), limit=256)
            rule = rules.get(rule_id, {})
            entity = _sarif_entity(result, row_number, state)
            if entity:
                entities.append(entity)
            message = result.get("message") if isinstance(result.get("message"), dict) else {}
            title = _safe_text(rule.get("name") or rule_id or "SARIF result")
            help_uri = _safe_uri(rule.get("helpUri"))
            finding = _make_finding(
                row_number=row_number, tool_root="sarif", title=title,
                severity=_normalize_severity(result.get("level")), affected_entity=entity,
                subject=rule_id or title, description=message.get("text") or message.get("markdown"),
                evidence=_sarif_location_summary(result), external_id=rule_id,
                references=[help_uri] if help_uri else [],
                source_detail={"adapter": "sarif", "tool": tool_name, "tool_version": tool_version,
                               "rule_id": rule_id, "rule_name": _safe_text(rule.get("name"), limit=256),
                               "level": _safe_text(result.get("level"), limit=32)},
            )
            if finding:
                findings.append(finding)
            else:
                state.warn(row_number, "invalid_sarif_subject", "SARIF result had no safe target subject.")


def _safe_uri(value: Any) -> str:
    uri = str(value or "").strip()
    parsed = urlsplit(uri)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc and "@" not in parsed.netloc:
        return uri[:2048]
    return ""


def _sarif_entity(result: dict[str, Any], row_number: int, state: Any):
    from services.atlas.import_parser import _entity_from_target
    for location in result.get("locations", []) if isinstance(result.get("locations"), list) else []:
        if not isinstance(location, dict):
            continue
        physical = location.get("physicalLocation")
        artifact = physical.get("artifactLocation") if isinstance(physical, dict) else None
        uri = artifact.get("uri") if isinstance(artifact, dict) else ""
        safe_uri = _safe_uri(uri)
        if safe_uri:
            return _entity_from_target(safe_uri, row_number, state, {"adapter": "sarif"})
    return None


def _sarif_location_summary(result: dict[str, Any]) -> str:
    from services.atlas.import_parser import _safe_multiline, _safe_text
    summaries = []
    locations = result.get("locations") if isinstance(result.get("locations"), list) else []
    for location in locations[:8]:
        physical = location.get("physicalLocation") if isinstance(location, dict) else None
        artifact = physical.get("artifactLocation") if isinstance(physical, dict) else None
        uri = _safe_text(artifact.get("uri"), limit=512) if isinstance(artifact, dict) else ""
        if uri:
            summaries.append(uri)
    return _safe_multiline("; ".join(summaries))
