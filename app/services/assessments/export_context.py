# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Complete saved Assessment context for Project reports and evidence packages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from core.output_targets import tokenize_command
from services.assessments.command_modes import assessment_command_mode
from services.assessments.contracts import AssessmentError
from services.assessments.finding_worklist import assessment_finding_worklist_on_conn
from services.assessments.reconciliation_read import assessment_finding_delta_read_model
from services.assessments.serialization import row_to_assessment, row_to_check, row_to_evidence
from services.assessments.summary import assessment_category_rollups, assessment_rollup
from services.projects.finding_identity import finding_identity_references
from services.projects.finding_vulnerabilities import finding_cves
from services.projects.scope import shared_owner_where


_FIX_FIRST_LIMIT = 100


def _selected_remediation_ids(
    findings: Iterable[Mapping[str, Any]] | None,
) -> list[str] | None:
    if findings is None:
        return None
    remediation_ids: set[str] = set()
    for source in findings:
        finding = dict(source)
        references = finding.get("observation_references")
        if not isinstance(references, list):
            references = finding_identity_references(finding, finding_cves(finding))
        remediation_ids.update(
            str(reference.get("remediation_id") or "")
            for reference in references
            if isinstance(reference, dict) and str(reference.get("remediation_id") or "")
        )
    return sorted(remediation_ids)


def _assessment_row(conn: Any, project_id: str, assessment_id: str) -> tuple[Any, str]:
    if assessment_id:
        row = conn.execute(
            "SELECT * FROM project_assessments WHERE project_id = ? AND id = ? LIMIT 1",
            (project_id, assessment_id),
        ).fetchone()
        if not row:
            raise AssessmentError("selected assessment cycle was not found in this project")
        return row, "selected"
    row = conn.execute(
        "SELECT * FROM project_assessments WHERE project_id = ? "
        "ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END, "
        "updated_at DESC, id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    return row, "current_or_newest"


def _source_run_metadata(conn: Any, evidence_rows: list[Any]) -> dict[str, dict[str, Any]]:
    run_ids = sorted({
        str(row["evidence_id"] or "")
        for row in evidence_rows
        if str(row["evidence_type"] or "") == "run" and str(row["evidence_id"] or "")
    })
    if not run_ids:
        return {}
    dialect = dialect_for_backend(get_db_backend())
    in_sql, params = dialect.in_clause("id", run_ids)
    rows = conn.execute(
        "SELECT id, command, started, finished, exit_code FROM runs WHERE " + in_sql,  # nosec
        params,
    ).fetchall()
    versions: dict[str, set[str]] = {run_id: set() for run_id in run_ids}
    in_sql, params = dialect.in_clause("run_id", run_ids)
    version_rows = [
        *conn.execute(
            "SELECT run_id, tool_version FROM nmap_service_observations WHERE " + in_sql,  # nosec
            params,
        ).fetchall(),
        *conn.execute(
            "SELECT run_id, tool_version FROM schemathesis_run_evidence WHERE " + in_sql,  # nosec
            params,
        ).fetchall(),
    ]
    for row in version_rows:
        version = str(row["tool_version"] or "")
        if version:
            versions.setdefault(str(row["run_id"] or ""), set()).add(version)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        command = str(row["command"] or "")
        tokens = tokenize_command(command)
        run_id = str(row["id"] or "")
        result[run_id] = {
            "tool": tokens[0] if tokens else "",
            "tool_versions": sorted(versions.get(run_id, set())),
            "command_mode": assessment_command_mode(command),
            "started_at": row["started"],
            "finished_at": row["finished"],
            "exit_code": row["exit_code"],
        }
    return result


def _checks_and_evidence(conn: Any, assessment_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    check_rows = conn.execute(
        "SELECT c.*, "
        "(SELECT COUNT(*) FROM project_assessment_evidence e WHERE e.check_id = c.id) "
        "AS evidence_count, "
        "(SELECT COUNT(*) FROM project_assessment_evidence e WHERE e.check_id = c.id "
        "AND e.source_state = 'available') AS available_evidence_count, "
        "(SELECT COUNT(*) FROM project_assessment_evidence e WHERE e.check_id = c.id "
        "AND e.source_state = 'unavailable') AS unavailable_evidence_count "
        "FROM project_assessment_checks c WHERE c.assessment_id = ? "
        "ORDER BY c.category, c.target_type, LOWER(c.target_value), c.check_key, c.id",
        (assessment_id,),
    ).fetchall()
    evidence_rows = conn.execute(
        "SELECT * FROM project_assessment_evidence WHERE assessment_id = ? "
        "ORDER BY check_id, observed_at, id",
        (assessment_id,),
    ).fetchall()
    source_runs = _source_run_metadata(conn, list(evidence_rows))
    evidence: list[dict[str, Any]] = []
    by_check: dict[str, list[str]] = {}
    for row in evidence_rows:
        item = row_to_evidence(row) or {}
        if item.get("evidence_type") == "run":
            item["source_run"] = source_runs.get(str(item.get("evidence_id") or ""), {})
        evidence.append(item)
        by_check.setdefault(str(item.get("check_id") or ""), []).append(str(item.get("id") or ""))
    checks: list[dict[str, Any]] = []
    for row in check_rows:
        check = row_to_check(row) or {}
        check["evidence_ids"] = by_check.get(str(check.get("id") or ""), [])
        checks.append(check)
    return checks, evidence


def _target_snapshot(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for check in checks:
        key = (
            str(check.get("target_entity_id") or ""),
            str(check.get("target_type") or ""),
            str(check.get("target_value") or ""),
        )
        target = targets.setdefault(key, {
            "entity_id": key[0],
            "type": key[1],
            "value": key[2],
            "check_ids": [],
            "state_counts": {},
        })
        target["check_ids"].append(str(check.get("id") or ""))
        state = str(check.get("state") or "not_started")
        target["state_counts"][state] = int(target["state_counts"].get(state) or 0) + 1
    return list(targets.values())


def _methodology(assessment: dict[str, Any], rollup: dict[str, int]) -> dict[str, Any]:
    denominator = int(rollup.get("applicable_checks") or 0)
    covered = int(rollup.get("covered_checks") or 0)
    return {
        "summary": (
            f"The saved {assessment.get('profile_key') or 'assessment'} profile snapshot was applied "
            f"to {denominator} applicable target checks. {covered} checks have compatible saved "
            "evidence; missing app-captured findings alone never count as coverage."
        ),
        "applicable_denominator": denominator,
        "state_meanings": {
            "covered": "Compatible saved evidence satisfies the frozen rule.",
            "needs_review": "Evidence exists but still needs a person to review it.",
            "untested": "The check is not started, running, or failed without complete evidence.",
            "blocked": "A person recorded a blocking condition and reason.",
            "skipped": "A person intentionally skipped the check and recorded why.",
            "not_applicable": "The frozen check does not apply to this saved target.",
            "unavailable_evidence": "A saved reference no longer resolves to its source.",
        },
    }


def project_assessment_export_context_on_conn(
    conn: Any,
    project_id: str,
    *,
    assessment_id: str,
    findings: Iterable[Mapping[str, Any]] | None,
    selected_artifact_ids: Iterable[str] | None,
) -> dict[str, Any] | None:
    row, selection_mode = _assessment_row(conn, project_id, assessment_id)
    if not row:
        return None
    assessment = row_to_assessment(row) or {}
    selected_id = str(assessment.get("id") or "")
    rollup = assessment_rollup(conn, selected_id)
    checks, evidence = _checks_and_evidence(conn, selected_id)
    manual_exclusions = [
        {
            "check_id": str(check.get("id") or ""),
            "check_key": str(check.get("check_key") or ""),
            "target_type": str(check.get("target_type") or ""),
            "target_value": str(check.get("target_value") or ""),
            "state": str(check.get("state") or ""),
            "reason": str(check.get("state_reason") or ""),
            "changed_at": check.get("state_changed_at"),
        }
        for check in checks
        if check.get("state_source") == "manual"
        and check.get("state") in {"blocked", "skipped", "not_applicable"}
    ]
    unavailable = [
        {
            "evidence_id": str(item.get("id") or ""),
            "check_id": str(item.get("check_id") or ""),
            "source_type": str(item.get("evidence_type") or ""),
            "source_id": str(item.get("evidence_id") or ""),
            "reason": str(item.get("unavailable_reason") or ""),
            "unavailable_at": item.get("unavailable_at"),
        }
        for item in evidence
        if item.get("source_state") == "unavailable"
    ]
    selected_artifacts = {str(value or "") for value in selected_artifact_ids or () if str(value or "")}
    screenshots = [item for item in evidence if item.get("evidence_type") == "screenshot"]
    screenshot_warnings = [
        {
            "evidence_id": str(item.get("id") or ""),
            "artifact_id": str(item.get("evidence_id") or ""),
            "reason": "Screenshot metadata is included, but its file wasn't selected for this export.",
        }
        for item in screenshots
        if str(item.get("evidence_id") or "") not in selected_artifacts
    ]
    remediation_ids = _selected_remediation_ids(findings)
    finding_change_model = assessment_finding_delta_read_model(
        conn,
        selected_id,
        remediation_ids=remediation_ids,
    )
    finding_changes = (
        None
        if remediation_ids is not None and not finding_change_model["rollup"]["total"]
        else {"assessment": assessment, **finding_change_model}
    )
    targets = _target_snapshot(checks)
    return {
        "schema_version": 1,
        "selection": {
            "mode": selection_mode,
            "requested_assessment_id": assessment_id,
            "selected_assessment_id": selected_id,
            "rule": (
                "Use the selected saved cycle."
                if selection_mode == "selected"
                else "Use the active cycle, otherwise the newest completed cycle, otherwise the newest archived cycle."
            ),
        },
        "assessment": assessment,
        "scope": {
            "targets": targets,
            "target_count": len(targets),
            "check_count": len(checks),
        },
        "rollup": rollup,
        "category_rollups": assessment_category_rollups(conn, selected_id),
        "checks": checks,
        "evidence": evidence,
        "manual_exclusions": manual_exclusions,
        "unavailable_evidence_warnings": unavailable,
        "screenshot_evidence": screenshots,
        "screenshot_warnings": screenshot_warnings,
        "methodology": _methodology(assessment, rollup),
        "fix_first": assessment_finding_worklist_on_conn(
            conn,
            selected_id,
            limit=_FIX_FIRST_LIMIT,
        ),
        "finding_changes": finding_changes,
        "redaction_boundaries": {
            "excluded": [
                "secret values and connector credential references",
                "HTTP headers and cookies",
                "connector credentials and private callback tokens",
                "workflow variables and internal workspace paths",
                "private verification notes unless explicitly included",
            ],
            "screenshot_files_require_selection": True,
        },
    }


def get_project_assessment_context(
    session_id: str,
    project_id: str,
    *,
    assessment_id: str = "",
    findings: Iterable[Mapping[str, Any]] | None = None,
    selected_artifact_ids: Iterable[str] | None = None,
    team_id: str = "",
) -> dict[str, Any] | None:
    """Return one complete, owner-scoped saved Assessment export context."""
    with get_db_connect()() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        ).fetchone()
        if not project:
            return None
        return project_assessment_export_context_on_conn(
            conn,
            project_id,
            assessment_id=str(assessment_id or "").strip(),
            findings=findings,
            selected_artifact_ids=selected_artifact_ids,
        )


__all__ = [
    "get_project_assessment_context",
    "project_assessment_export_context_on_conn",
]
