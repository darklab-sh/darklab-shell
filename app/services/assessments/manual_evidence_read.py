# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded manual evidence links attached to Assessment checks."""

from __future__ import annotations

from typing import Any

from services.assessments.serialization import row_to_evidence
from services.projects.utils import page_payload


ASSESSMENT_MANUAL_EVIDENCE_PER_CHECK = 20


def attach_manual_evidence(
    conn: Any,
    checks: list[dict[str, Any]],
) -> None:
    """Attach newest-first manual evidence links for each returned check."""
    check_ids = [str(check.get("id") or "") for check in checks if check.get("id")]
    grouped: dict[str, list[dict[str, Any]]] = {
        check_id: [] for check_id in check_ids
    }
    totals: dict[str, int] = {check_id: 0 for check_id in check_ids}
    if check_ids:
        placeholders = ",".join("?" for _ in check_ids)
        rows = conn.execute(
            "SELECT * FROM (SELECT e.*, "
            "ROW_NUMBER() OVER (PARTITION BY e.check_id "
            "ORDER BY e.observed_at DESC, e.id DESC) AS item_rank, "
            "COUNT(*) OVER (PARTITION BY e.check_id) AS item_total "
            "FROM project_assessment_evidence e "
            "WHERE e.linked_by = 'manual' AND e.check_id IN ("
            + placeholders
            + ")) ranked WHERE item_rank <= ? "
            "ORDER BY check_id ASC, observed_at DESC, id DESC",  # nosec
            (*check_ids, ASSESSMENT_MANUAL_EVIDENCE_PER_CHECK),
        ).fetchall()
        for row in rows:
            check_id = str(row["check_id"] or "")
            evidence = row_to_evidence(row)
            if evidence is not None:
                grouped.setdefault(check_id, []).append(evidence)
            totals[check_id] = int(row["item_total"] or 0)
    for check in checks:
        check_id = str(check.get("id") or "")
        check["manual_evidence"] = page_payload(
            "evidence",
            grouped.get(check_id, []),
            totals.get(check_id, 0),
            ASSESSMENT_MANUAL_EVIDENCE_PER_CHECK,
            0,
        )


__all__ = ["attach_manual_evidence"]
