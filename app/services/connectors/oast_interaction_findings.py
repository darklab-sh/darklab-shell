# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact-target finding links for reviewed private OAST interactions."""

from __future__ import annotations

from typing import Any

from services.assessments.contracts import AssessmentNotFound
from services.assessments.evidence_sources import load_assessment_evidence_source
from services.connectors.oast_correlations import (
    OastCorrelationError,
    _connection_scope,
    _owner_predicate,
)
from services.connectors.oast_interactions import _interaction_row, _select_sql
from services.projects.contracts import ProjectWorkspaceError, ProjectWorkspaceNotFound
from services.projects.finding_evidence import link_finding_evidence_on_conn


def attach_oast_interaction_to_finding(
    session_id: str,
    interaction_id: str,
    finding_id: str,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    conn=None,
) -> dict[str, Any]:
    """Attach one interaction to an exact-target Project finding and its source links."""
    owner_sql, owner_params = _owner_predicate(
        str(session_id or ""), str(team_id or ""), table_prefix="c"
    )
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        row = active_conn.execute(
            _select_sql(owner_sql) + " AND i.id = ?",  # nosec
            (*owner_params, interaction_id),
        ).fetchone()
        if row is None:
            raise OastCorrelationError(
                "oast_interaction_not_found",
                "OAST interaction not found",
            )
        selected_finding_id = str(finding_id or "").strip()
        try:
            load_assessment_evidence_source(
                active_conn,
                str(row["session_id"] or ""),
                str(row["team_id"] or ""),
                str(row["project_id"] or ""),
                "finding",
                selected_finding_id,
            )
        except AssessmentNotFound as exc:
            raise OastCorrelationError(
                "oast_interaction_finding_not_found",
                "The finding was not found in this OAST Project scope",
            ) from exc
        finding = active_conn.execute(
            "SELECT entity_id, target_id FROM findings WHERE id = ?",
            (selected_finding_id,),
        ).fetchone()
        target_id = str(
            (finding["entity_id"] if finding else "")
            or (finding["target_id"] if finding else "")
            or ""
        )
        if target_id != str(row["target_entity_id"] or ""):
            raise OastCorrelationError(
                "oast_interaction_finding_mismatch",
                "The finding target doesn't match this OAST interaction",
            )
        current_finding_id = str(row["finding_id"] or "")
        if current_finding_id and current_finding_id != selected_finding_id:
            raise OastCorrelationError(
                "oast_interaction_finding_conflict",
                "The OAST interaction is already attached to another finding",
            )
        try:
            for evidence_type, evidence_id in (
                ("run", str(row["run_id"] or "")),
                ("assessment_check", str(row["check_id"] or "")),
            ):
                link_finding_evidence_on_conn(
                    active_conn,
                    str(row["session_id"] or ""),
                    str(row["project_id"] or ""),
                    selected_finding_id,
                    {"evidence_type": evidence_type, "evidence_id": evidence_id},
                    team_id=str(row["team_id"] or ""),
                    actor_member_id=str(actor_member_id or ""),
                )
        except (ProjectWorkspaceError, ProjectWorkspaceNotFound) as exc:
            raise OastCorrelationError(
                "oast_interaction_finding_evidence_invalid",
                "The OAST finding evidence couldn't be attached",
            ) from exc
        active_conn.execute(
            "UPDATE oast_interactions SET finding_id = ? WHERE id = ?",
            (selected_finding_id, interaction_id),
        )
        if owns_conn:
            active_conn.commit()
        updated = active_conn.execute(
            _select_sql(owner_sql) + " AND i.id = ?",  # nosec
            (*owner_params, interaction_id),
        ).fetchone()
        return _interaction_row(active_conn, updated)


__all__ = ["attach_oast_interaction_to_finding"]
