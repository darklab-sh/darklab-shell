# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Changed-NVD detection for linked CVEs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .store import queue_work_item


_NON_ACTIVE_STATUSES = frozenset({"disputed", "rejected", "withdrawn"})
_STATUS_TRANSITIONS = {
    "disputed": "nvd_disputed",
    "rejected": "nvd_rejected",
    "withdrawn": "nvd_withdrawn",
}


@dataclass(frozen=True)
class NvdRiskState:
    status: str
    cvss_score: float | None
    source_version: str


def _score(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def state_from_values(values: Mapping[str, Any], *, source_version: str) -> NvdRiskState:
    return NvdRiskState(
        status=str(values.get("advisory_status") or "unknown"),
        cvss_score=_score(values.get("cvss_score")),
        source_version=str(source_version or ""),
    )


def linked_nvd_states(conn: Any) -> dict[str, NvdRiskState]:
    rows = conn.execute(
        "SELECT DISTINCT r.cve_id, r.advisory_status, r.cvss_score, r.nvd_source_version "
        "FROM cve_risk_records r JOIN finding_cve_links l ON l.cve_id = r.cve_id "
        "WHERE r.nvd_origin != 'unavailable' AND r.nvd_source_version != ''"
    ).fetchall()
    return {
        str(row["cve_id"]): NvdRiskState(
            status=str(row["advisory_status"] or "unknown"),
            cvss_score=_score(row["cvss_score"]),
            source_version=str(row["nvd_source_version"] or ""),
        )
        for row in rows
    }


def linked_nvd_state(conn: Any, cve_id: str) -> NvdRiskState | None:
    row = conn.execute(
        "SELECT r.advisory_status, r.cvss_score, r.nvd_source_version "
        "FROM cve_risk_records r WHERE r.cve_id = ? "
        "AND r.nvd_origin != 'unavailable' AND r.nvd_source_version != '' "
        "AND EXISTS (SELECT 1 FROM finding_cve_links l WHERE l.cve_id = r.cve_id) ",
        (cve_id,),
    ).fetchone()
    if row is None:
        return None
    return NvdRiskState(
        status=str(row["advisory_status"] or "unknown"),
        cvss_score=_score(row["cvss_score"]),
        source_version=str(row["nvd_source_version"] or ""),
    )


def queue_nvd_transitions(
    conn: Any,
    *,
    cve_id: str,
    previous: NvdRiskState | None,
    current: NvdRiskState,
    downgrade_delta: float,
    now: str,
) -> int:
    """Queue meaningful NVD changes; a first accepted record is a silent baseline."""
    if previous is None:
        return 0
    transitions: list[tuple[str, Any, Any]] = []
    if previous.status != current.status:
        if current.status == "active" and previous.status in _NON_ACTIVE_STATUSES:
            transitions.append(("nvd_reinstated", previous.status, current.status))
        else:
            transition = _STATUS_TRANSITIONS.get(current.status)
            if transition:
                transitions.append((transition, previous.status, current.status))
    if (
        previous.cvss_score is not None
        and current.cvss_score is not None
        and previous.cvss_score - current.cvss_score >= max(0.1, float(downgrade_delta))
    ):
        transitions.append((
            "nvd_cvss_downgraded",
            previous.cvss_score,
            current.cvss_score,
        ))
    for transition_kind, old_value, new_value in transitions:
        queue_work_item(
            conn,
            source="nvd",
            feed_version=current.source_version,
            cve_id=cve_id,
            transition_kind=transition_kind,
            old_value=old_value,
            new_value=new_value,
            old_source_version=previous.source_version,
            new_source_version=current.source_version,
            now=now,
        )
    return len(transitions)
