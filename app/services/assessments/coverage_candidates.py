# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded candidate reads for ordinary and assessment-batch run evidence."""

from __future__ import annotations

from typing import Any

from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


def candidate_checks_for_run(conn: Any, run_id: str) -> list[dict[str, Any]]:
    """Return active checks, limited to explicit mappings for batch children."""
    rows = conn.execute(
        "SELECT a.id AS assessment_id, a.session_id, a.team_id, a.project_id, "
        "a.profile_snapshot, c.id AS check_id, c.check_key, c.target_type, "
        "c.target_value, c.state, c.state_source, c.state_reason, "
        "c.first_evidence_at, c.last_evidence_at "
        "FROM project_links pl "
        "JOIN project_assessments a ON a.project_id = pl.project_id AND a.status = 'active' "
        "JOIN project_assessment_checks c ON c.assessment_id = a.id "
        "JOIN runs r ON r.id = pl.entity_id "
        "LEFT JOIN workflow_execution_children child ON child.run_id = r.id "
        "LEFT JOIN workflow_executions execution ON execution.id = child.execution_id "
        "LEFT JOIN assessment_batch_items item ON item.batch_id = child.execution_id "
        "AND item.step_id = child.step_id AND item.child_ordinal = child.ordinal "
        "LEFT JOIN assessment_batch_item_checks mapping ON mapping.batch_id = item.batch_id "
        "AND mapping.item_index = item.item_index AND mapping.assessment_id = a.id "
        "AND mapping.check_id = c.id "
        "WHERE pl.entity_type = 'run' AND pl.entity_id = ? "
        "AND a.team_id = r.team_id "
        "AND (a.team_id != '' OR a.session_id = r.session_id) "
        "AND (child.id IS NULL OR execution.execution_kind != ? "
        "OR (item.item_index IS NOT NULL AND mapping.check_id IS NOT NULL)) "
        "ORDER BY a.id ASC, c.id ASC",
        (run_id, ASSESSMENT_BATCH_EXECUTION_KIND),
    ).fetchall()
    return [dict(row) for row in rows]


__all__ = ["candidate_checks_for_run"]
