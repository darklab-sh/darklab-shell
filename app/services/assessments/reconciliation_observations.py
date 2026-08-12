# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Finding observations supported by one saved assessment check."""

from __future__ import annotations

from typing import Any

from services.projects.finding_details import finding_detail_fields
from services.projects.finding_identity import finding_identity_references
from services.projects.finding_vulnerabilities import finding_cves


_RUN_FINDINGS_SQL = (
    "SELECT f.id, f.session_id, f.team_id, f.target_id, f.entity_id, f.subject_key, "
    "f.signature_hash, f.origin, f.validation_method, f.title, f.raw_line, "
    "f.fingerprint, f.cve_ids_json, 'run' AS support_type, "
    "occurrence.run_id AS support_id FROM project_assessment_evidence evidence "
    "JOIN findings_occurrences occurrence ON occurrence.run_id = evidence.evidence_id "
    "JOIN findings f ON f.id = occurrence.finding_id "
    "WHERE evidence.check_id = ? AND evidence.evidence_type = 'run' "
    "AND evidence.source_state = 'available'"
)
_DIRECT_FINDINGS_SQL = (
    "SELECT f.id, f.session_id, f.team_id, f.target_id, f.entity_id, f.subject_key, "
    "f.signature_hash, f.origin, f.validation_method, f.title, f.raw_line, "
    "f.fingerprint, f.cve_ids_json, 'finding' AS support_type, "
    "evidence.evidence_id AS support_id FROM project_assessment_evidence evidence "
    "JOIN findings f ON f.id = evidence.evidence_id "
    "WHERE evidence.check_id = ? AND evidence.evidence_type = 'finding' "
    "AND evidence.source_state = 'available'"
)
_MANUAL_FINDINGS_SQL = (
    "SELECT f.id, f.session_id, f.team_id, f.target_id, f.entity_id, f.subject_key, "
    "f.signature_hash, f.origin, f.validation_method, f.title, f.raw_line, "
    "f.fingerprint, f.cve_ids_json, 'assessment_check' AS support_type, "
    "link.evidence_id AS support_id FROM finding_evidence_links link "
    "JOIN findings f ON f.id = link.finding_id "
    "WHERE link.evidence_type = 'assessment_check' AND link.evidence_id = ?"
)


def _supported_finding_rows(
    conn: Any,
    check_id: str,
    *,
    include_run_findings: bool,
) -> list[Any]:
    run_rows = conn.execute(
        _RUN_FINDINGS_SQL,
        (check_id,),
    ).fetchall() if include_run_findings else []
    direct_rows = conn.execute(
        _DIRECT_FINDINGS_SQL,
        (check_id,),
    ).fetchall()
    manual_rows = conn.execute(
        _MANUAL_FINDINGS_SQL,
        (check_id,),
    ).fetchall()
    return [*run_rows, *direct_rows, *manual_rows]


def load_check_observations(
    conn: Any,
    check_id: str,
    *,
    include_run_findings: bool = True,
) -> dict[str, dict[str, Any]]:
    """Group exact observations by their stable remediation identity."""
    groups: dict[str, dict[str, Any]] = {}
    for row in _supported_finding_rows(
        conn,
        check_id,
        include_run_findings=include_run_findings,
    ):
        finding = dict(row)
        finding.update(finding_detail_fields(row))
        finding_id = str(finding.get("id") or "")
        evidence_id = f"{row['support_type']}:{row['support_id']}"
        for reference in finding_identity_references(finding, finding_cves(finding)):
            remediation_id = str(reference.get("remediation_id") or "")
            if not remediation_id:
                continue
            group = groups.setdefault(remediation_id, {
                "remediation_id": remediation_id,
                "identity_kind": str(reference.get("identity_kind") or "rule"),
                "vulnerability_id": str(reference.get("vulnerability_id") or ""),
                "rule_identity": str(reference.get("rule_identity") or ""),
                "affected_subject": str(reference.get("affected_subject") or ""),
                "observations": {},
                "evidence_ids": set(),
                "finding_ids": set(),
            })
            observation_id = str(reference.get("observation_id") or "")
            observation = group["observations"].setdefault(observation_id, {
                "observation_id": observation_id,
                "finding_id": finding_id,
                "validation_method": str(reference.get("validation_method") or ""),
                "evidence_ids": set(),
            })
            observation["evidence_ids"].add(evidence_id)
            group["evidence_ids"].add(evidence_id)
            group["finding_ids"].add(finding_id)
    return groups


def serialized_observations(group: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not group:
        return []
    result = []
    for observation in group["observations"].values():
        result.append({
            "observation_id": str(observation.get("observation_id") or ""),
            "finding_id": str(observation.get("finding_id") or ""),
            "validation_method": str(observation.get("validation_method") or ""),
            "evidence_ids": sorted(observation.get("evidence_ids") or ()),
        })
    return sorted(result, key=lambda item: (item["finding_id"], item["observation_id"]))
