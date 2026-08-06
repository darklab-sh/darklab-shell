# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable, conservative finding reconciliation across assessment cycles."""

from __future__ import annotations

import secrets
from typing import Any, Mapping

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.reconciliation_observations import (
    load_check_observations,
    serialized_observations,
)
from services.projects.contracts import ProjectWorkspaceError
from services.projects.finding_verification import finding_verification_context_on_conn
from services.projects.utils import cfg_int, now, raise_quota


DEFAULT_MAX_DELTAS_PER_ASSESSMENT = 100_000
_STATE_REASONS = {
    "new": "Observed in this cycle but not in the compatible prior check.",
    "persistent": "Observed in both cycles under the same compatible check contract.",
    "not_observed": (
        "Not observed in this cycle after the compatible check completed with an explicit "
        "negative-evidence contract."
    ),
    "regressed": (
        "Observed again after an authorized verified disposition backed by compatible retest "
        "evidence."
    ),
}


def _new_id(prefix: str) -> str:
    return prefix + secrets.token_hex(12)


def _profile_checks(snapshot: object) -> dict[str, Mapping[str, Any]]:
    dialect = dialect_for_backend(get_db_backend())
    profile = snapshot if isinstance(snapshot, Mapping) else dialect.decode_json_dict(snapshot)
    checks = profile.get("checks", []) if isinstance(profile, Mapping) else []
    return {
        str(check.get("key") or ""): check
        for check in checks
        if isinstance(check, Mapping) and str(check.get("key") or "")
    }


def _assessment(conn: Any, assessment_id: str) -> Any:
    return conn.execute(
        "SELECT id, session_id, team_id, project_id, profile_snapshot, status, "
        "started_at, created_at FROM project_assessments WHERE id = ?",
        (assessment_id,),
    ).fetchone()


def _checks(conn: Any, assessment_id: str) -> list[Any]:
    return conn.execute(
        "SELECT id, assessment_id, check_key, target_type, target_value, target_value_hash "
        "FROM project_assessment_checks WHERE assessment_id = ? ORDER BY id ASC",
        (assessment_id,),
    ).fetchall()


def _previous_check(conn: Any, assessment: Any, check: Any) -> Any:
    return conn.execute(
        "SELECT previous.id, previous.assessment_id, prior.profile_snapshot "
        "FROM project_assessment_checks previous "
        "JOIN project_assessments prior ON prior.id = previous.assessment_id "
        "WHERE prior.project_id = ? AND prior.id != ? "
        "AND prior.status IN ('completed', 'archived') AND prior.started_at < ? "
        "AND previous.check_key = ? AND previous.target_type = ? "
        "AND previous.target_value_hash = ? "
        "ORDER BY prior.started_at DESC, prior.id DESC LIMIT 1",
        (
            str(assessment["project_id"]),
            str(assessment["id"]),
            str(assessment["started_at"] or assessment["created_at"] or ""),
            str(check["check_key"]),
            str(check["target_type"]),
            str(check["target_value_hash"]),
        ),
    ).fetchone()


def _available_rule_versions(conn: Any, check_id: str) -> set[tuple[str, str]]:
    rows = conn.execute(
        "SELECT DISTINCT match_rule_key, match_rule_version "
        "FROM project_assessment_evidence WHERE check_id = ? "
        "AND source_state = 'available' ORDER BY match_rule_key, match_rule_version",
        (check_id,),
    ).fetchall()
    return {
        (str(row["match_rule_key"] or ""), str(row["match_rule_version"] or ""))
        for row in rows
        if str(row["match_rule_key"] or "")
    }


def _rule_definition(
    definitions: Mapping[str, Mapping[str, Any]],
    check_key: str,
    identity: tuple[str, str],
) -> Mapping[str, Any] | None:
    definition = definitions.get(check_key)
    if not isinstance(definition, Mapping):
        return None
    for rule in definition.get("evidence_rules", []):
        if not isinstance(rule, Mapping):
            continue
        if (str(rule.get("key") or ""), str(rule.get("version") or "")) == identity:
            return rule
    return None


def _rule_supports_findings(rule: Mapping[str, Any] | None) -> bool:
    if not isinstance(rule, Mapping):
        return False
    return (
        "finding" in rule.get("evidence_types", [])
        or "findings" in rule.get("structured_output_kinds", [])
    )


def _comparison_contract(
    conn: Any,
    assessment: Any,
    check: Any,
    definitions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    previous = _previous_check(conn, assessment, check)
    if not previous:
        current_rules = sorted(_available_rule_versions(conn, str(check["id"])))
        current_rule = (
            _rule_definition(definitions, str(check["check_key"]), current_rules[0])
            if current_rules
            else None
        )
        return {
            "state": "no_baseline",
            "reason": "No earlier completed cycle contains this exact check and target.",
            "previous": None,
            "rule_key": "",
            "rule_version": "",
            "negative": False,
            "current_findings": _rule_supports_findings(current_rule),
            "previous_findings": False,
        }
    current_rules = _available_rule_versions(conn, str(check["id"]))
    previous_rules = _available_rule_versions(conn, str(previous["id"]))
    common = sorted(current_rules.intersection(previous_rules))
    if not current_rules:
        reason = "The current check has no available evidence that satisfies its frozen rule."
    elif not previous_rules:
        reason = "The prior check's compatible evidence is unavailable."
    else:
        reason = "The two cycles used different evidence-rule versions for this check."
    if not common:
        current_identity = sorted(current_rules)[0] if current_rules else None
        current_rule = (
            _rule_definition(definitions, str(check["check_key"]), current_identity)
            if current_identity
            else None
        )
        previous_definitions = _profile_checks(previous["profile_snapshot"])
        previous_identity = sorted(previous_rules)[0] if previous_rules else None
        previous_rule = (
            _rule_definition(
                previous_definitions,
                str(check["check_key"]),
                previous_identity,
            )
            if previous_identity
            else None
        )
        return {
            "state": "incomparable",
            "reason": reason,
            "previous": previous,
            "rule_key": "",
            "rule_version": "",
            "negative": False,
            "current_findings": _rule_supports_findings(current_rule),
            "previous_findings": _rule_supports_findings(previous_rule),
        }
    identity = common[0]
    rule = _rule_definition(definitions, str(check["check_key"]), identity)
    previous_rule = _rule_definition(
        _profile_checks(previous["profile_snapshot"]),
        str(check["check_key"]),
        identity,
    )
    return {
        "state": "comparable",
        "reason": f"Matched frozen evidence rule {identity[0]} version {identity[1]}.",
        "previous": previous,
        "rule_key": identity[0],
        "rule_version": identity[1],
        "negative": bool(rule and rule.get("negative_evidence")),
        "current_findings": _rule_supports_findings(rule),
        "previous_findings": _rule_supports_findings(previous_rule),
    }


def _verified_before_cycle(
    conn: Any,
    assessment: Any,
    finding_ids: set[str],
) -> bool:
    if not finding_ids:
        return False
    dialect = dialect_for_backend(get_db_backend())
    in_sql, in_params = dialect.in_clause("finding_id", sorted(finding_ids))
    if str(assessment["team_id"] or ""):
        owner_sql = "team_id = ?"
        owner_params: tuple[object, ...] = (str(assessment["team_id"]),)
    else:
        owner_sql = "session_id = ? AND COALESCE(team_id, '') = ''"
        owner_params = (str(assessment["session_id"]),)
    query = "".join((
        "SELECT finding_id FROM finding_triage_details WHERE ",
        owner_sql,
        " AND ",
        in_sql,
        " AND verification_status = 'verified' AND verification_updated_at != '' ",
        "AND verification_updated_at < ?",
    ))
    rows = conn.execute(
        query,
        (*owner_params, *in_params, str(assessment["started_at"] or "")),
    ).fetchall()
    for row in rows:
        try:
            context = finding_verification_context_on_conn(
                conn,
                str(assessment["session_id"]),
                str(assessment["project_id"]),
                str(row["finding_id"]),
                team_id=str(assessment["team_id"] or ""),
            )
        except ProjectWorkspaceError:
            continue
        suggestion = context.get("suggestion", {})
        if suggestion.get("available") and suggestion.get("verification_status") == "verified":
            return True
    return False


def _delta_state(
    conn: Any,
    assessment: Any,
    contract: dict[str, Any],
    current: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> tuple[str, str]:
    if contract["state"] != "comparable":
        return "incomparable", str(contract["reason"])
    if current and previous:
        if _verified_before_cycle(conn, assessment, set(previous["finding_ids"])):
            return "regressed", _STATE_REASONS["regressed"]
        return "persistent", _STATE_REASONS["persistent"]
    if current:
        return "new", _STATE_REASONS["new"]
    if previous and contract["negative"]:
        return "not_observed", _STATE_REASONS["not_observed"]
    return (
        "incomparable",
        "The current rule doesn't define clean negative evidence, so absence can't be classified.",
    )


def _upsert_comparison(
    conn: Any,
    assessment: Any,
    check: Any,
    contract: dict[str, Any],
    computed_at: str,
) -> str:
    previous = contract["previous"]
    comparison_id = _new_id("acmp_")
    conn.execute(
        "INSERT INTO project_assessment_check_comparisons "
        "(id, current_assessment_id, current_check_id, previous_assessment_id, "
        "previous_check_id, compatibility_state, reason, matched_rule_key, "
        "matched_rule_version, supports_negative_evidence, computed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(current_check_id) DO UPDATE SET "
        "previous_assessment_id = excluded.previous_assessment_id, "
        "previous_check_id = excluded.previous_check_id, "
        "compatibility_state = excluded.compatibility_state, reason = excluded.reason, "
        "matched_rule_key = excluded.matched_rule_key, "
        "matched_rule_version = excluded.matched_rule_version, "
        "supports_negative_evidence = excluded.supports_negative_evidence, "
        "computed_at = excluded.computed_at",
        (
            comparison_id,
            str(assessment["id"]),
            str(check["id"]),
            str(previous["assessment_id"]) if previous else None,
            str(previous["id"]) if previous else None,
            contract["state"],
            contract["reason"],
            contract["rule_key"],
            contract["rule_version"],
            1 if contract["negative"] else 0,
            computed_at,
        ),
    )
    row = conn.execute(
        "SELECT id FROM project_assessment_check_comparisons WHERE current_check_id = ?",
        (str(check["id"]),),
    ).fetchone()
    return str(row["id"])


def _insert_delta(
    conn: Any,
    assessment: Any,
    check: Any,
    comparison_id: str,
    contract: dict[str, Any],
    remediation_id: str,
    current: dict[str, Any] | None,
    previous: dict[str, Any] | None,
    computed_at: str,
) -> str:
    state, reason = _delta_state(conn, assessment, contract, current, previous)
    source = current or previous or {}
    dialect = dialect_for_backend(get_db_backend())
    observations_current = serialized_observations(current)
    observations_previous = serialized_observations(previous)
    previous_check = contract["previous"]
    conn.execute(
        "INSERT INTO project_assessment_finding_deltas "
        "(id, comparison_id, current_assessment_id, current_check_id, "
        "previous_assessment_id, previous_check_id, remediation_id, identity_kind, "
        "vulnerability_id, rule_identity, affected_subject, delta_state, reason, "
        "current_observations_json, previous_observations_json, "
        "current_evidence_ids_json, previous_evidence_ids_json, computed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            _new_id("afdl_"),
            comparison_id,
            str(assessment["id"]),
            str(check["id"]),
            str(previous_check["assessment_id"]) if previous_check else None,
            str(previous_check["id"]) if previous_check else None,
            remediation_id,
            str(source.get("identity_kind") or "rule"),
            str(source.get("vulnerability_id") or ""),
            str(source.get("rule_identity") or ""),
            str(source.get("affected_subject") or ""),
            state,
            reason,
            dialect.json_param(observations_current),
            dialect.json_param(observations_previous),
            dialect.json_param(sorted((current or {}).get("evidence_ids") or ())),
            dialect.json_param(sorted((previous or {}).get("evidence_ids") or ())),
            computed_at,
        ),
    )
    return state


def reconcile_assessment_findings_on_conn(conn: Any, assessment_id: str) -> dict[str, int]:
    """Rebuild stored comparisons for one cycle without rewriting source findings."""
    assessment = _assessment(conn, str(assessment_id or ""))
    summary = {
        "checks_compared": 0,
        "comparable_checks": 0,
        "no_baseline_checks": 0,
        "incomparable_checks": 0,
        "deltas_written": 0,
    }
    if not assessment:
        return summary
    definitions = _profile_checks(assessment["profile_snapshot"])
    computed_at = now()
    delta_limit = cfg_int(
        "max_project_assessment_finding_deltas_per_assessment",
        DEFAULT_MAX_DELTAS_PER_ASSESSMENT,
    )
    for check in _checks(conn, str(assessment["id"])):
        contract = _comparison_contract(conn, assessment, check, definitions)
        summary["checks_compared"] += 1
        summary[f"{contract['state']}_checks"] += 1
        comparison_id = _upsert_comparison(conn, assessment, check, contract, computed_at)
        conn.execute(
            "DELETE FROM project_assessment_finding_deltas WHERE comparison_id = ?",
            (comparison_id,),
        )
        current = load_check_observations(
            conn,
            str(check["id"]),
            include_run_findings=bool(contract["current_findings"]),
        )
        previous_check = contract["previous"]
        previous = (
            load_check_observations(
                conn,
                str(previous_check["id"]),
                include_run_findings=bool(contract["previous_findings"]),
            )
            if previous_check
            else {}
        )
        for remediation_id in sorted(set(current).union(previous)):
            if summary["deltas_written"] >= delta_limit:
                raise_quota("assessment finding reconciliation quota exceeded")
            _insert_delta(
                conn,
                assessment,
                check,
                comparison_id,
                contract,
                remediation_id,
                current.get(remediation_id),
                previous.get(remediation_id),
                computed_at,
            )
            summary["deltas_written"] += 1
    return summary


def reconcile_assessments_for_run_on_conn(conn: Any, run_id: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT DISTINCT assessment_id FROM project_assessment_evidence "
        "WHERE evidence_type = 'run' AND evidence_id = ? AND source_state = 'available'",
        (str(run_id or ""),),
    ).fetchall()
    total = {"assessments_reconciled": 0, "deltas_written": 0}
    for row in rows:
        summary = reconcile_assessment_findings_on_conn(conn, str(row["assessment_id"]))
        total["assessments_reconciled"] += 1
        total["deltas_written"] += int(summary["deltas_written"])
    return total


def reconcile_active_assessments_for_finding_on_conn(
    conn: Any,
    finding_id: str,
) -> dict[str, int]:
    """Refresh active cycles whose Project evidence includes one changed finding."""
    rows = conn.execute(
        "SELECT DISTINCT assessment.id FROM project_assessments assessment WHERE "
        "assessment.status = 'active' AND assessment.project_id IN ("
        "SELECT link.project_id FROM finding_evidence_links link WHERE link.finding_id = ? "
        "UNION SELECT project_link.project_id FROM findings_occurrences occurrence "
        "JOIN project_links project_link ON project_link.entity_type = 'run' "
        "AND project_link.entity_id = occurrence.run_id WHERE occurrence.finding_id = ?"
        ") ORDER BY assessment.id",
        (str(finding_id or ""), str(finding_id or "")),
    ).fetchall()
    total = {"assessments_reconciled": 0, "deltas_written": 0}
    for row in rows:
        summary = reconcile_assessment_findings_on_conn(conn, str(row["id"]))
        total["assessments_reconciled"] += 1
        total["deltas_written"] += int(summary["deltas_written"])
    return total
