# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Deletion boundaries for stored assessment finding comparisons."""

from __future__ import annotations

from typing import Any

from services.projects.utils import now


def reconciliation_deletion_counts(conn: Any, assessment_id: str) -> dict[str, int]:
    comparison = conn.execute(
        "SELECT COUNT(*) AS count FROM project_assessment_check_comparisons "
        "WHERE current_assessment_id = ?",
        (assessment_id,),
    ).fetchone()
    delta = conn.execute(
        "SELECT COUNT(*) AS count FROM project_assessment_finding_deltas "
        "WHERE current_assessment_id = ?",
        (assessment_id,),
    ).fetchone()
    dependent = conn.execute(
        "SELECT COUNT(*) AS count FROM project_assessment_check_comparisons "
        "WHERE previous_assessment_id = ?",
        (assessment_id,),
    ).fetchone()
    return {
        "finding_check_comparisons": int(comparison["count"] or 0),
        "finding_deltas": int(delta["count"] or 0),
        "dependent_comparisons_invalidated": int(dependent["count"] or 0),
    }


def delete_assessment_reconciliation_on_conn(conn: Any, assessment_id: str) -> None:
    dependent_rows = conn.execute(
        "SELECT id FROM project_assessment_check_comparisons "
        "WHERE previous_assessment_id = ?",
        (assessment_id,),
    ).fetchall()
    for dependent in dependent_rows:
        comparison_id = str(dependent["id"])
        conn.execute(
            "DELETE FROM project_assessment_finding_deltas WHERE comparison_id = ?",
            (comparison_id,),
        )
        conn.execute(
            "UPDATE project_assessment_check_comparisons SET "
            "compatibility_state = 'incomparable', "
            "reason = 'The prior assessment cycle was deleted.', "
            "matched_rule_key = '', matched_rule_version = '', "
            "supports_negative_evidence = 0, computed_at = ? WHERE id = ?",
            (now(), comparison_id),
        )
    conn.execute(
        "DELETE FROM project_assessment_finding_deltas WHERE current_assessment_id = ?",
        (assessment_id,),
    )
    conn.execute(
        "DELETE FROM project_assessment_check_comparisons WHERE current_assessment_id = ?",
        (assessment_id,),
    )
