# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Resolve check-specific saved selections for one Assessment action."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from services.assessments.dalfox_oast_actions import DalfoxOastActionContext
from services.assessments.dalfox_xss_actions import DalfoxXssActionContext
from services.assessments.recommended_action_selection_contexts import (
    resolve_selection_contexts,
)
from services.assessments.schemathesis_actions import SchemathesisActionContext


@dataclass(frozen=True)
class RecommendedActionSelections:
    dalfox_xss: DalfoxXssActionContext | None
    dalfox_oast: DalfoxOastActionContext | None
    schemathesis: SchemathesisActionContext | None


def resolve_recommended_action_selections(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    check_key: str,
    target: Mapping[str, str] | None,
    selection: Mapping[str, str] | None,
) -> RecommendedActionSelections:
    """Resolve only identifiers owned by the exact frozen check contract."""
    xss, oast, schemathesis = resolve_selection_contexts(
        conn,
        session_id,
        team_id,
        project_id,
        check_key,
        target,
        selection,
    )
    return RecommendedActionSelections(xss, oast, schemathesis)


__all__ = [
    "RecommendedActionSelections",
    "resolve_recommended_action_selections",
]
