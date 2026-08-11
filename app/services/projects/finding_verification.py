# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-scoped verification provenance for one saved finding."""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.assessments.evidence_matching import (
    load_run_evidence_facts,
    matching_run_rule,
    target_matches,
)
from services.assessments.evidence_sources import load_assessment_evidence_source
from services.assessments.contracts import AssessmentNotFound
from services.assessments.profile_summaries import list_assessment_profile_summaries
from services.assessments.profiles import AssessmentProfileCatalogError
from services.projects.finding_evidence import list_finding_evidence_links_on_conn
from services.projects.finding_evidence import link_finding_evidence_on_conn
from services.projects.finding_details import finding_detail_fields
from services.projects.finding_identity import finding_identity_references
from services.projects.finding_vulnerabilities import finding_cves
from services.projects.contracts import ProjectWorkspaceError, ProjectWorkspaceNotFound
from services.projects.scope import shared_owner_where
from services.runs.kinds import RUN_KIND_EXTERNAL


VERIFICATION_RUN_LIMIT = 25
log = logging.getLogger("shell")


def _finding_row(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
) -> Any:
    try:
        load_assessment_evidence_source(
            conn,
            session_id,
            team_id,
            project_id,
            "finding",
            finding_id,
        )
    except AssessmentNotFound as exc:
        raise ProjectWorkspaceNotFound(
            "finding was not found in this project scope"
        ) from exc
    return conn.execute(
        "SELECT f.id, f.run_id, f.first_run_id, f.last_run_id, f.target_id, f.entity_id, "
        "COALESCE(target.type, entity.type, '') AS target_type, "
        "COALESCE(target.canonical_value, entity.canonical_value, f.subject_key, '') "
        "AS target_value, f.session_id, f.team_id, f.subject_key, f.signature_hash, "
        "f.origin, f.validation_method, f.title, f.raw_line, f.fingerprint, f.cve_ids_json "
        "FROM findings f "
        "LEFT JOIN entities target ON target.id = f.target_id "
        "LEFT JOIN entities entity ON entity.id = f.entity_id WHERE f.id = ?",
        (finding_id,),
    ).fetchone()


def _origin_checks(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
) -> list[dict[str, Any]]:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="link"
    )
    # shared_owner_where supplies this trusted SQL fragment; all owner values
    # and finding identifiers remain bound parameters.
    sql = "".join((
        "SELECT link.id AS evidence_link_id, link.evidence_id AS check_id, ",
        "c.assessment_id, c.check_key, c.target_type, c.target_value, c.policy_level, ",
        "c.recommended_action_key, a.profile_key, a.profile_version, a.profile_snapshot ",
        "FROM finding_evidence_links link ",
        "LEFT JOIN project_assessment_checks c ON c.id = link.evidence_id ",
        "LEFT JOIN project_assessments a ON a.id = c.assessment_id AND a.project_id = link.project_id ",
        "WHERE ",
        owner_sql,
        " AND link.project_id = ? AND link.finding_id = ? ",
        "AND link.evidence_type = 'assessment_check' ",
        "ORDER BY link.created_at ASC, link.id ASC",
    ))
    rows = conn.execute(
        sql,
        (*owner_params, project_id, finding_id),
    ).fetchall()
    dialect = dialect_for_backend(get_db_backend())
    try:
        current_versions = {
            str(profile.get("key") or ""): str(profile.get("version") or "")
            for profile in list_assessment_profile_summaries()
        }
    except AssessmentProfileCatalogError:
        current_versions = {}
    result: list[dict[str, Any]] = []
    for row in rows:
        available = bool(row["assessment_id"])
        profile_key = str(row["profile_key"] or "")
        profile_version = str(row["profile_version"] or "")
        current_profile_version = current_versions.get(profile_key, "")
        if not current_profile_version:
            profile_version_state = "unavailable"
        elif current_profile_version == profile_version:
            profile_version_state = "current"
        else:
            profile_version_state = "changed"
        result.append({
            "evidence_link_id": str(row["evidence_link_id"] or ""),
            "check_id": str(row["check_id"] or ""),
            "assessment_id": str(row["assessment_id"] or ""),
            "check_key": str(row["check_key"] or ""),
            "target_type": str(row["target_type"] or ""),
            "target_value": str(row["target_value"] or ""),
            "policy_level": str(row["policy_level"] or ""),
            "recommended_action_key": str(row["recommended_action_key"] or ""),
            "profile_key": profile_key,
            "profile_version": profile_version,
            "current_profile_version": current_profile_version,
            "profile_version_state": profile_version_state,
            "profile_snapshot": (
                dialect.decode_json_dict(row["profile_snapshot"])
                if available
                else {}
            ),
            "source_state": "available" if available else "unavailable",
        })
    return result


def _check_definition(check: Mapping[str, Any]) -> Mapping[str, Any] | None:
    snapshot = check.get("profile_snapshot")
    if not isinstance(snapshot, Mapping):
        return None
    check_key = str(check.get("check_key") or "")
    for item in snapshot.get("checks", []):
        if isinstance(item, Mapping) and str(item.get("key") or "") == check_key:
            return item
    return None


def _baseline_run_id(finding: Any, evidence: list[dict[str, Any]]) -> str:
    for field in ("first_run_id", "run_id", "last_run_id"):
        value = str(finding[field] or "")
        if value:
            return value
    for link in evidence:
        if str(link.get("evidence_type") or "") in {"run", "run_line", "run_artifact"}:
            value = str(link.get("run_id") or "")
            if value:
                return value
    return ""


def _run_payload(row: Any, facts: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"] or ""),
        "command": str(row["command"] or ""),
        "command_root": str(facts.command_root if facts else ""),
        "started": str(row["started"] or ""),
        "finished": str(row["finished"] or ""),
        "exit_code": row["exit_code"],
    }


def _compatibility(
    facts: Any,
    *,
    origin_checks: list[dict[str, Any]],
    finding: Any,
    baseline_facts: Any,
) -> dict[str, Any]:
    def result(
        state: str,
        reason: str,
        *,
        check_id: str = "",
        rule: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "state": state,
            "reason": reason,
            "matched_check_id": check_id,
            "matched_rule_key": str((rule or {}).get("key") or ""),
            "supports_negative_evidence": bool((rule or {}).get("negative_evidence")),
        }

    if facts is None or not facts.finished_at:
        return result("unavailable", "The saved verification run is unavailable or incomplete.")
    available_checks = [
        check
        for check in origin_checks
        if check["source_state"] == "available" and _check_definition(check)
    ]
    for check in available_checks:
        definition = _check_definition(check)
        rule = matching_run_rule(
            definition or {},
            facts,
            target_type=check["target_type"],
            target_value=check["target_value"],
        )
        if rule:
            return result(
                "compatible",
                "Matches the originating check's frozen target, tool, and completion rules.",
                check_id=check["check_id"],
                rule=rule,
            )
    if available_checks:
        return result(
            "incomparable",
            "The run doesn't satisfy the originating check's frozen target, tool, completion, or output rules.",
        )
    if origin_checks:
        return result("unavailable", "The originating assessment check is no longer available.")
    if baseline_facts is None:
        return result(
            "unavailable",
            "The original run is unavailable, so comparability can't be established.",
        )
    if facts.command_root != baseline_facts.command_root:
        return result(
            "incomparable",
            "The verification run uses a different tool than the original evidence.",
        )
    target_type = str(finding["target_type"] or "")
    target_value = str(finding["target_value"] or "")
    if target_type and target_value and not target_matches(
        facts.target_identities,
        target_type,
        target_value,
        "host_or_descendant",
    ):
        return result(
            "incomparable",
            "The verification run targets a different host or endpoint.",
        )
    return result("compatible", "Matches the original tool and affected target.")


def _remediation_ids(finding: Any) -> set[str]:
    payload = dict(finding)
    payload.update(finding_detail_fields(finding))
    return {
        str(reference.get("remediation_id") or "")
        for reference in finding_identity_references(payload, finding_cves(payload))
        if str(reference.get("remediation_id") or "")
    }


def _run_remediation_ids(conn: Any, run_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT f.id, f.session_id, f.team_id, f.target_id, f.entity_id, "
        "f.subject_key, f.signature_hash, f.origin, f.validation_method, f.title, "
        "f.raw_line, f.fingerprint, f.cve_ids_json FROM findings_occurrences occurrence "
        "JOIN findings f ON f.id = occurrence.finding_id WHERE occurrence.run_id = ?",
        (run_id,),
    ).fetchall()
    return {identity for row in rows for identity in _remediation_ids(row)}


def _verification_suggestion(
    conn: Any,
    finding: Any,
    retest_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    default = {
        "available": False,
        "verification_status": "",
        "reason": "No compatible completed retest evidence is linked yet.",
        "run_id": "",
        "evidence_link_id": "",
        "matched_check_id": "",
        "matched_rule_key": "",
    }
    compatible = sorted(
        (
            run for run in retest_runs
            if run.get("source_state") == "available"
            and run.get("compatibility", {}).get("state") == "compatible"
        ),
        key=lambda run: (str(run.get("finished") or ""), str(run.get("id") or "")),
        reverse=True,
    )
    if not compatible:
        return default
    run = compatible[0]
    compatibility = run["compatibility"]
    support = {
        **default,
        "run_id": str(run.get("id") or ""),
        "evidence_link_id": str(run.get("evidence_link_id") or ""),
        "matched_check_id": str(compatibility.get("matched_check_id") or ""),
        "matched_rule_key": str(compatibility.get("matched_rule_key") or ""),
    }
    if _remediation_ids(finding).intersection(_run_remediation_ids(conn, support["run_id"])):
        return {
            **support,
            "available": True,
            "verification_status": "needs_retest",
            "reason": (
                "The newest compatible retest observed the same exact affected subject "
                "and vulnerability or scanner rule again."
            ),
        }
    if run.get("exit_code") == 0 and compatibility.get("supports_negative_evidence"):
        return {
            **support,
            "available": True,
            "verification_status": "verified",
            "reason": (
                "The newest compatible retest completed successfully, the frozen rule accepts "
                "clean negative evidence, and the same vulnerability or scanner rule was not observed again."
            ),
        }
    support["reason"] = (
        "The newest compatible retest does not provide the successful clean-negative contract "
        "required to suggest verified."
    )
    return support


def _project_runs(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
) -> list[Any]:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="run"
    )
    # shared_owner_where supplies this trusted SQL fragment; all owner values
    # and project identifiers remain bound parameters.
    sql = "".join((
        "SELECT run.id, run.command, run.started, run.finished, run.exit_code ",
        "FROM project_links link JOIN runs run ON run.id = link.entity_id ",
        "WHERE link.project_id = ? AND link.entity_type = 'run' AND ",
        owner_sql,
        " AND run.run_kind = ? AND run.finished IS NOT NULL ",
        "ORDER BY run.started DESC, link.created DESC, run.id DESC LIMIT ?",
    ))
    return conn.execute(
        sql,
        (project_id, *owner_params, RUN_KIND_EXTERNAL, VERIFICATION_RUN_LIMIT),
    ).fetchall()


def _comparison_payload(baseline_run_id: str, verification_run_id: str) -> dict[str, Any]:
    available = bool(
        baseline_run_id
        and verification_run_id
        and baseline_run_id != verification_run_id
    )
    return {
        "available": available,
        "left_run_id": baseline_run_id if available else "",
        "right_run_id": verification_run_id if available else "",
    }


def finding_verification_context_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    finding_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    """Return bounded origin, retest, and compatibility context for one finding."""
    finding = _finding_row(conn, session_id, team_id, project_id, finding_id)
    evidence = list_finding_evidence_links_on_conn(
        conn, session_id, project_id, finding_id, team_id=team_id
    )
    origin_checks = _origin_checks(
        conn, session_id, team_id, project_id, finding_id
    )
    baseline_run_id = _baseline_run_id(finding, evidence)
    baseline_facts = load_run_evidence_facts(conn, baseline_run_id) if baseline_run_id else None
    rows = _project_runs(conn, session_id, team_id, project_id)
    rows_by_id = {str(row["id"]): row for row in rows}
    linked_retests = {
        str(link.get("evidence_id") or ""): link
        for link in evidence
        if str(link.get("evidence_type") or "") == "retest_run"
    }
    retest_runs: list[dict[str, Any]] = []
    candidate_runs: list[dict[str, Any]] = []
    for run_id, link in linked_retests.items():
        row = rows_by_id.get(run_id)
        facts = load_run_evidence_facts(conn, run_id)
        payload = _run_payload(row, facts) if row else {
            "id": run_id,
            "command": "",
            "command_root": str(facts.command_root if facts else ""),
            "started": "",
            "finished": str(facts.finished_at if facts else ""),
            "exit_code": facts.exit_code if facts else None,
        }
        retest_runs.append({
            **payload,
            "evidence_link_id": str(link.get("id") or ""),
            "source_state": str(link.get("source_state") or "unavailable"),
            "compatibility": _compatibility(
                facts,
                origin_checks=origin_checks,
                finding=finding,
                baseline_facts=baseline_facts,
            ),
            "comparison": _comparison_payload(baseline_run_id, run_id),
        })
    for row in rows:
        run_id = str(row["id"] or "")
        if run_id in linked_retests or run_id == baseline_run_id:
            continue
        facts = load_run_evidence_facts(conn, run_id)
        candidate_runs.append({
            **_run_payload(row, facts),
            "compatibility": _compatibility(
                facts,
                origin_checks=origin_checks,
                finding=finding,
                baseline_facts=baseline_facts,
            ),
            "comparison": _comparison_payload(baseline_run_id, run_id),
        })
    public_checks = [
        {key: value for key, value in check.items() if key != "profile_snapshot"}
        for check in origin_checks
    ]
    return {
        "evidence": evidence,
        "baseline_run_id": baseline_run_id,
        "baseline_source_state": "available" if baseline_facts else "unavailable",
        "origin_checks": public_checks,
        "retest_runs": retest_runs,
        "candidate_runs": candidate_runs,
        "candidate_limit": VERIFICATION_RUN_LIMIT,
        "suggestion": _verification_suggestion(conn, finding, retest_runs),
    }


def get_finding_verification_context(
    session_id: str,
    project_id: str,
    finding_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    with get_db_connect()() as conn:
        return finding_verification_context_on_conn(
            conn,
            session_id,
            project_id,
            finding_id,
            team_id=team_id,
        )


def link_completed_verification_run(
    session_id: str,
    project_id: str,
    finding_id: str,
    check_id: str,
    run_id: str,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    with get_db_connect()() as conn:
        checks = _origin_checks(conn, session_id, team_id, project_id, finding_id)
        if not any(
            check["check_id"] == check_id and check["source_state"] == "available"
            for check in checks
        ):
            raise ProjectWorkspaceNotFound(
                "originating assessment check was not found for this finding"
            )
        linked = link_finding_evidence_on_conn(
            conn,
            session_id,
            project_id,
            finding_id,
            {"evidence_type": "retest_run", "evidence_id": run_id},
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
        conn.commit()
        return linked


def verification_run_finalized_hook(
    session_id: str,
    plan: Mapping[str, Any],
    *,
    team_id: str = "",
) -> Callable[[str, dict[str, Any]], None]:
    """Return a safe completion hook that retains a launched run as retest evidence."""
    project_id = str(plan.get("project_id") or "")
    finding_id = str(plan.get("finding_id") or "")
    check_id = str(plan.get("check_id") or "")

    def finalized(run_id: str, result: dict[str, Any]) -> None:
        summary = result.get("finalize_summary") if isinstance(result, dict) else {}
        project_link = result.get("active_project_link") if isinstance(result, dict) else {}
        if (
            not isinstance(summary, dict)
            or not summary.get("persisted")
            or not isinstance(project_link, dict)
            or str(project_link.get("project_id") or "") != project_id
        ):
            log.warning("PROJECT_VERIFICATION_EVIDENCE_LINK_SKIPPED", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "project_id": project_id,
                "finding_id": finding_id,
                "check_id": check_id,
                "reason": "run_finalization_unavailable",
            })
            return
        try:
            linked = link_completed_verification_run(
                session_id,
                project_id,
                finding_id,
                check_id,
                run_id,
                team_id=team_id,
            )
        except ProjectWorkspaceError as exc:
            log.warning("PROJECT_VERIFICATION_EVIDENCE_LINK_SKIPPED", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "project_id": project_id,
                "finding_id": finding_id,
                "check_id": check_id,
                "reason": str(exc),
            })
            return
        except Exception:
            log.error("PROJECT_VERIFICATION_EVIDENCE_LINK_ERROR", exc_info=True, extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "project_id": project_id,
                "finding_id": finding_id,
                "check_id": check_id,
            })
            return
        log.info("PROJECT_VERIFICATION_EVIDENCE_LINKED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "finding_id": finding_id,
            "check_id": check_id,
            "created": bool(linked.get("created")),
        })

    return finalized
