# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Describe assessment-owned rows removed by historical cleanup."""

from __future__ import annotations

from typing import Any

from services.assessments.reconciliation_cleanup import reconciliation_deletion_counts
from services.assessments.serialization import row_to_assessment


def assessment_deletion_preview(conn: Any, row: Any) -> dict[str, Any]:
    assessment_id = str(row["id"] or "")
    check_row = conn.execute(
        "SELECT COUNT(*) AS count FROM project_assessment_checks "
        "WHERE assessment_id = ?",
        (assessment_id,),
    ).fetchone()
    evidence_rows = conn.execute(
        "SELECT evidence_type, source_state, COUNT(*) AS count "
        "FROM project_assessment_evidence WHERE assessment_id = ? "
        "GROUP BY evidence_type, source_state "
        "ORDER BY evidence_type ASC, source_state ASC",
        (assessment_id,),
    ).fetchall()
    by_type: dict[str, int] = {}
    available = 0
    unavailable = 0
    for evidence in evidence_rows:
        evidence_type = str(evidence["evidence_type"] or "")
        count = int(evidence["count"] or 0)
        by_type[evidence_type] = by_type.get(evidence_type, 0) + count
        if str(evidence["source_state"] or "") == "available":
            available += count
        else:
            unavailable += count
    schemathesis_row = conn.execute(
        "SELECT COUNT(DISTINCT report.id) AS report_count, "
        "COUNT(operation.id) AS operation_count FROM schemathesis_run_evidence report "
        "LEFT JOIN schemathesis_operation_evidence operation ON operation.report_id = report.id "
        "WHERE report.assessment_id = ?",
        (assessment_id,),
    ).fetchone()
    serialized = row_to_assessment(row) or {}
    return {
        "assessment": {
            key: serialized.get(key)
            for key in (
                "id", "project_id", "owner_kind", "team_id", "title",
                "profile_key", "profile_version", "status",
            )
        },
        "can_delete": str(row["status"] or "") == "archived",
        "requires_archived": True,
        "will_delete": {
            "assessments": 1,
            "checks": int(check_row["count"] or 0) if check_row else 0,
            "evidence_links": available + unavailable,
            "available_evidence_links": available,
            "unavailable_evidence_links": unavailable,
            "evidence_links_by_type": by_type,
            "schemathesis_reports": int(schemathesis_row["report_count"] or 0),
            "schemathesis_operations": int(schemathesis_row["operation_count"] or 0),
            **reconciliation_deletion_counts(conn, assessment_id),
        },
        "source_records_deleted": False,
    }
