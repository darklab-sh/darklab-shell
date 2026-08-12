# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded evidence previews for assessment-cycle read models."""

from __future__ import annotations

from typing import Any

from services.assessments.serialization import row_to_evidence
from services.projects.utils import page_payload


ASSESSMENT_EVIDENCE_PREVIEW_PER_CHECK = 3
ASSESSMENT_RECENT_EVIDENCE_LIMIT = 20


def attach_evidence_previews(conn: Any, checks: list[dict[str, Any]]) -> None:
    """Attach the newest evidence links for each returned check."""
    check_ids = [str(check.get("id") or "") for check in checks if check.get("id")]
    grouped: dict[str, list[dict[str, Any]]] = {check_id: [] for check_id in check_ids}
    totals: dict[str, int] = {check_id: 0 for check_id in check_ids}
    if check_ids:
        placeholders = ",".join("?" for _ in check_ids)
        # Check IDs stay bound; only generated parameter markers are interpolated.
        query = (
            "SELECT * FROM (SELECT e.*, "  # nosec B608
            "ROW_NUMBER() OVER (PARTITION BY e.check_id "
            "ORDER BY e.observed_at DESC, e.id DESC) AS item_rank, "
            "COUNT(*) OVER (PARTITION BY e.check_id) AS item_total "
            "FROM project_assessment_evidence e WHERE e.check_id IN ("
            + placeholders
            + ")) ranked WHERE item_rank <= ? "
            "ORDER BY check_id ASC, observed_at DESC, id DESC"
        )
        rows = conn.execute(
            query,
            (*check_ids, ASSESSMENT_EVIDENCE_PREVIEW_PER_CHECK),
        ).fetchall()
        for row in rows:
            check_id = str(row["check_id"] or "")
            evidence = row_to_evidence(row)
            if evidence is not None:
                grouped.setdefault(check_id, []).append(evidence)
            totals[check_id] = int(row["item_total"] or 0)
    for check in checks:
        check_id = str(check.get("id") or "")
        check["evidence_previews"] = page_payload(
            "evidence",
            grouped.get(check_id, []),
            totals.get(check_id, 0),
            ASSESSMENT_EVIDENCE_PREVIEW_PER_CHECK,
            0,
        )


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
    return page_payload(
        "evidence",
        items,
        total,
        ASSESSMENT_RECENT_EVIDENCE_LIMIT,
        0,
    )


__all__ = ["attach_evidence_previews", "recent_assessment_evidence"]
