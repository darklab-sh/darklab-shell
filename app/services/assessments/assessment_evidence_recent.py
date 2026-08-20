# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded recent evidence for one assessment cycle."""

from __future__ import annotations

from typing import Any

from services.assessments.batch.provenance import (
    apply_assessment_batch_evidence_provenance,
)
from services.assessments.serialization import row_to_evidence
from services.projects.utils import page_payload


ASSESSMENT_RECENT_EVIDENCE_LIMIT = 20


def recent_assessment_evidence(conn: Any, assessment_id: str) -> dict[str, Any]:
    """Return the newest evidence links across one assessment cycle."""
    rows = conn.execute(
        "SELECT e.*, c.check_key, c.target_type, c.target_value, "
        "COUNT(*) OVER () AS item_total "
        "FROM project_assessment_evidence e "
        "JOIN project_assessment_checks c ON c.id = e.check_id "
        "WHERE e.assessment_id = ? "
        "ORDER BY e.observed_at DESC, e.id DESC LIMIT ?",
        (assessment_id, ASSESSMENT_RECENT_EVIDENCE_LIMIT),
    ).fetchall()
    items: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        evidence = row_to_evidence(row)
        if evidence is None:
            continue
        evidence.update({
            "check_key": str(row["check_key"] or ""),
            "target_type": str(row["target_type"] or ""),
            "target_value": str(row["target_value"] or ""),
        })
        items.append(evidence)
        total = int(row["item_total"] or 0)
    apply_assessment_batch_evidence_provenance(conn, items)
    return page_payload(
        "evidence",
        items,
        total,
        ASSESSMENT_RECENT_EVIDENCE_LIMIT,
        0,
    )


__all__ = ["recent_assessment_evidence"]
