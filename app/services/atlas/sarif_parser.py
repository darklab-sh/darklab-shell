# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded SARIF 2.1 result normalization for Atlas imports."""

from __future__ import annotations

import json

from services.atlas.sarif_details import (
    safe_sarif_web_uri,
    sarif_automation_details,
    sarif_entity,
    sarif_fingerprints,
    sarif_location_summary,
    sarif_locations,
)


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
        raw_tool = run.get("tool")
        tool = raw_tool if isinstance(raw_tool, dict) else {}
        raw_driver = tool.get("driver")
        driver = raw_driver if isinstance(raw_driver, dict) else {}
        tool_name = _safe_text(driver.get("name"), limit=128) or "SARIF tool"
        tool_version = _safe_text(driver.get("version"), limit=128)
        tool_semantic_version = _safe_text(driver.get("semanticVersion"), limit=128)
        tool_information_uri = safe_sarif_web_uri(driver.get("informationUri"))
        automation_details = sarif_automation_details(run)
        raw_rules = driver.get("rules")
        rules = {
            str(rule.get("id")): rule
            for rule in (
                raw_rules[:state.limits.max_rows]
                if isinstance(raw_rules, list)
                else []
            )
            if isinstance(rule, dict) and _safe_text(rule.get("id"), limit=256)
        }
        raw_artifacts = run.get("artifacts")
        artifacts = raw_artifacts if isinstance(raw_artifacts, list) else []
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for result in results:
            row_number = state.next_row()
            if not isinstance(result, dict):
                state.warn(row_number, "invalid_sarif_result", "SARIF result must be an object.")
                continue
            rule_id = _safe_text(result.get("ruleId"), limit=256)
            rule = rules.get(rule_id) or {}
            locations, rejected_location_count, locations_truncated = sarif_locations(
                result, artifacts, state, row_number
            )
            entity = sarif_entity(locations, row_number, state)
            if entity:
                entities.append(entity)
            raw_message = result.get("message")
            message = raw_message if isinstance(raw_message, dict) else {}
            title = _safe_text(rule.get("name") or rule_id or "SARIF result")
            help_uri = safe_sarif_web_uri(rule.get("helpUri"))
            fingerprints = sarif_fingerprints(result)
            finding = _make_finding(
                row_number=row_number, tool_root="sarif", title=title,
                severity=_normalize_severity(result.get("level")), affected_entity=entity,
                subject=rule_id or title, description=message.get("text") or message.get("markdown"),
                evidence=sarif_location_summary(locations), external_id=rule_id,
                references=[help_uri] if help_uri else [],
                source_detail={
                    "adapter": "sarif",
                    "tool": tool_name,
                    "tool_version": tool_version,
                    "tool_semantic_version": tool_semantic_version,
                    "tool_information_uri": tool_information_uri,
                    "rule_id": rule_id,
                    "rule_name": _safe_text(rule.get("name"), limit=256),
                    "level": _safe_text(result.get("level"), limit=32),
                    "kind": _safe_text(result.get("kind"), limit=32),
                    "baseline_state": _safe_text(result.get("baselineState"), limit=32),
                    "result_guid": _safe_text(result.get("guid"), limit=128),
                    "result_correlation_guid": _safe_text(
                        result.get("correlationGuid"), limit=128
                    ),
                    "automation_details": automation_details,
                    "locations": locations,
                    "location_count": len(locations),
                    "rejected_location_count": rejected_location_count,
                    "locations_truncated": locations_truncated,
                    **fingerprints,
                },
            )
            if finding:
                findings.append(finding)
            else:
                state.warn(row_number, "invalid_sarif_subject", "SARIF result had no safe target subject.")
