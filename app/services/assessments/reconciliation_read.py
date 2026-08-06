# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded read model for stored assessment finding comparisons."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.reconciliation_read_filters import (
    DELTA_STATE_RANKS,
    delta_rollup,
)


_ITEM_LIMIT = 100


def _comparison_rollup(conn: Any, assessment_id: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT compatibility_state, COUNT(*) AS count "
        "FROM project_assessment_check_comparisons WHERE current_assessment_id = ? "
        "GROUP BY compatibility_state",
        (assessment_id,),
    ).fetchall()
    counts = {str(row["compatibility_state"]): int(row["count"] or 0) for row in rows}
    total = sum(counts.values())
    comparable = counts.get("comparable", 0)
    no_baseline = counts.get("no_baseline", 0)
    incomparable = counts.get("incomparable", 0)
    if not total:
        status = "pending"
    elif comparable and comparable == total:
        status = "comparable"
    elif comparable:
        status = "partial"
    elif no_baseline == total:
        status = "no_baseline"
    else:
        status = "incomparable"
    return {
        "status": status,
        "total_checks": total,
        "comparable_checks": comparable,
        "no_baseline_checks": no_baseline,
        "incomparable_checks": incomparable,
    }


def _grouped_rows(
    conn: Any,
    assessment_id: str,
    remediation_ids: list[str],
) -> list[dict[str, Any]]:
    if not remediation_ids:
        return []
    dialect = dialect_for_backend(get_db_backend())
    in_sql, in_params = dialect.in_clause("delta.remediation_id", remediation_ids)
    query = "".join((
        "SELECT delta.id, delta.current_check_id, delta.previous_assessment_id, ",
        "delta.previous_check_id, delta.remediation_id, delta.identity_kind, ",
        "delta.vulnerability_id, delta.rule_identity, delta.affected_subject, ",
        "delta.delta_state, delta.reason, delta.current_observations_json, ",
        "delta.previous_observations_json, delta.current_evidence_ids_json, ",
        "delta.previous_evidence_ids_json, current_check.check_key, ",
        "current_check.target_type, current_check.target_value ",
        "FROM project_assessment_finding_deltas delta ",
        "JOIN project_assessment_checks current_check ON current_check.id = delta.current_check_id ",
        "WHERE delta.current_assessment_id = ? AND ",
        in_sql,
        " ORDER BY CASE delta.delta_state ",
        "WHEN 'regressed' THEN 0 WHEN 'new' THEN 1 WHEN 'persistent' THEN 2 ",
        "WHEN 'not_observed' THEN 3 ELSE 4 END, delta.remediation_id, delta.id",
    ))
    rows = conn.execute(
        query,
        (assessment_id, *in_params),
    ).fetchall()
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        remediation_id = str(row["remediation_id"] or "")
        group = groups.setdefault(remediation_id, {
            "remediation_id": remediation_id,
            "identity_kind": str(row["identity_kind"] or "rule"),
            "vulnerability_id": str(row["vulnerability_id"] or ""),
            "rule_identity": str(row["rule_identity"] or ""),
            "affected_subject": str(row["affected_subject"] or ""),
            "state": str(row["delta_state"] or "incomparable"),
            "reasons": [],
            "checks": [],
            "current_observations": [],
            "previous_observations": [],
            "current_evidence_ids": set(),
            "previous_evidence_ids": set(),
            "previous_assessment_ids": set(),
        })
        state = str(row["delta_state"] or "incomparable")
        if DELTA_STATE_RANKS.get(state, 0) > DELTA_STATE_RANKS.get(group["state"], 0):
            group["state"] = state
        reason = str(row["reason"] or "")
        if reason and reason not in group["reasons"]:
            group["reasons"].append(reason)
        group["checks"].append({
            "current_check_id": str(row["current_check_id"] or ""),
            "previous_check_id": str(row["previous_check_id"] or ""),
            "check_key": str(row["check_key"] or ""),
            "target_type": str(row["target_type"] or ""),
            "target_value": str(row["target_value"] or ""),
            "state": state,
        })
        group["current_observations"].extend(
            dialect.decode_json_list(row["current_observations_json"])
        )
        group["previous_observations"].extend(
            dialect.decode_json_list(row["previous_observations_json"])
        )
        group["current_evidence_ids"].update(
            str(value) for value in dialect.decode_json_list(row["current_evidence_ids_json"])
        )
        group["previous_evidence_ids"].update(
            str(value) for value in dialect.decode_json_list(row["previous_evidence_ids_json"])
        )
        if row["previous_assessment_id"]:
            group["previous_assessment_ids"].add(str(row["previous_assessment_id"]))
    ordered = sorted(
        groups.values(),
        key=lambda item: (-DELTA_STATE_RANKS.get(item["state"], 0), item["remediation_id"]),
    )
    return ordered


def _finding_summaries(conn: Any, groups: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    finding_ids = sorted({
        str(observation.get("finding_id") or "")
        for group in groups
        for side in ("current_observations", "previous_observations")
        for observation in group[side]
        if isinstance(observation, dict) and str(observation.get("finding_id") or "")
    })
    if not finding_ids:
        return {}
    dialect = dialect_for_backend(get_db_backend())
    in_sql, params = dialect.in_clause("f.id", finding_ids)
    query = "".join((
        "SELECT f.id, f.title, f.severity, f.origin, f.validation_method, ",
        "COALESCE(triage.verification_status, 'not_started') AS verification_status ",
        "FROM findings f LEFT JOIN finding_triage_details triage ",
        "ON triage.finding_id = f.id AND (",
        "(f.team_id != '' AND triage.team_id = f.team_id) OR ",
        "(f.team_id = '' AND triage.session_id = f.session_id ",
        "AND COALESCE(triage.team_id, '') = '')) WHERE ",
        in_sql,
    ))
    rows = conn.execute(
        query,
        params,
    ).fetchall()
    return {
        str(row["id"]): {
            "id": str(row["id"]),
            "title": str(row["title"] or "Saved finding"),
            "severity": str(row["severity"] or "info"),
            "origin": str(row["origin"] or "run"),
            "validation_method": str(row["validation_method"] or ""),
            "verification_status": str(row["verification_status"] or "not_started"),
        }
        for row in rows
    }


def _hydrate(groups: list[dict[str, Any]], findings: dict[str, dict[str, Any]]) -> None:
    for group in groups:
        for side in ("current", "previous"):
            observations = group[f"{side}_observations"]
            unique: dict[str, dict[str, Any]] = {}
            for observation in observations:
                if not isinstance(observation, dict):
                    continue
                observation_id = str(observation.get("observation_id") or "")
                unique.setdefault(observation_id, observation)
            group[f"{side}_observations"] = list(unique.values())
            finding_ids = sorted({
                str(item.get("finding_id") or "")
                for item in unique.values()
                if str(item.get("finding_id") or "")
            })
            group[f"{side}_findings"] = [
                findings.get(finding_id, {
                    "id": finding_id,
                    "title": "Finding source unavailable",
                    "severity": "info",
                    "origin": "",
                    "validation_method": "",
                    "verification_status": "not_started",
                })
                for finding_id in finding_ids
            ]
            group[f"{side}_evidence_ids"] = sorted(group[f"{side}_evidence_ids"])
        group["previous_assessment_ids"] = sorted(group["previous_assessment_ids"])


def assessment_finding_delta_read_model(
    conn: Any,
    assessment_id: str,
    *,
    remediation_ids: list[str] | None = None,
    item_limit: int = _ITEM_LIMIT,
) -> dict[str, Any]:
    comparison = _comparison_rollup(conn, assessment_id)
    safe_item_limit = max(1, min(int(item_limit), _ITEM_LIMIT))
    if remediation_ids is not None:
        remediation_ids = sorted({str(value) for value in remediation_ids if str(value)})
    rollup, page_remediation_ids = delta_rollup(
        conn,
        assessment_id,
        remediation_ids=remediation_ids,
        item_limit=safe_item_limit,
    )
    groups = _grouped_rows(conn, assessment_id, page_remediation_ids)
    findings = _finding_summaries(conn, groups)
    _hydrate(groups, findings)
    total = sum(rollup.values())
    return {
        "comparison": comparison,
        "rollup": {**rollup, "total": total},
        "items": groups,
        "item_limit": safe_item_limit,
        "truncated": total > len(groups),
    }
