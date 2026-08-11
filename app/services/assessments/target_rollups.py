# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Cycle-wide assessment rollups grouped by frozen Project target."""

from __future__ import annotations

from typing import Any

from services.assessments.serialization import row_to_rollup
from services.assessments.summary import ROLLUP_COLUMNS


def assessment_target_rollups(conn: Any, assessment_id: str) -> list[dict[str, Any]]:
    query = "".join((
        "SELECT c.target_entity_id, c.target_type, c.target_value, ",
        ROLLUP_COLUMNS,
        " FROM project_assessment_checks c WHERE c.assessment_id = ? ",
        "GROUP BY c.target_entity_id, c.target_type, c.target_value ",
        "ORDER BY c.target_type ASC, LOWER(c.target_value) ASC, ",
        "c.target_entity_id ASC",
    ))
    rows = conn.execute(query, (assessment_id,)).fetchall()
    return [
        {
            "target_entity_id": str(row["target_entity_id"] or ""),
            "target_type": str(row["target_type"] or ""),
            "target_value": str(row["target_value"] or ""),
            **row_to_rollup(row),
        }
        for row in rows
    ]
