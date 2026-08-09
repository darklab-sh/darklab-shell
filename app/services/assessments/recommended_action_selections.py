# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Resolve check-specific saved selections for one Assessment action."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import config as app_config
from services.assessments.action_plans import AssessmentActionError
from services.assessments.dalfox_xss_actions import (
    DalfoxXssActionContext,
    dalfox_xss_action_context,
)
from services.assessments.schemathesis_actions import (
    SchemathesisActionContext,
    schemathesis_action_context,
)


@dataclass(frozen=True)
class RecommendedActionSelections:
    dalfox_xss: DalfoxXssActionContext | None
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
    xss = dalfox_xss_action_context(
        conn,
        session_id,
        team_id,
        project_id,
        check_key,
        target,
        selection,
        enabled=bool(
            app_config.CFG.get("assessment_intrusive_actions_enabled", False)
        ),
    )
    schemathesis = schemathesis_action_context(
        conn,
        session_id,
        team_id,
        project_id,
        check_key,
        target,
        selection,
    )
    supported_keys = set()
    if xss is not None:
        supported_keys.update({"source_run_id", "parameter_observation_id"})
    if schemathesis is not None:
        supported_keys.add("schema_artifact_id")
    supplied = {key for key, value in (selection or {}).items() if str(value or "").strip()}
    if supplied - supported_keys:
        raise AssessmentActionError(
            "unsupported_evidence_selection",
            "Saved evidence selection doesn't apply to this reviewed action.",
        )
    return RecommendedActionSelections(xss, schemathesis)


__all__ = [
    "RecommendedActionSelections",
    "resolve_recommended_action_selections",
]
