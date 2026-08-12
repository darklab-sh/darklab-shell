# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Resolve typed saved-evidence contexts for Assessment action previews."""

from __future__ import annotations

from typing import Any, Mapping

import config as app_config
from services.assessments.action_plans import AssessmentActionError
from services.assessments.dalfox_oast_actions import (
    DalfoxOastActionContext,
    dalfox_oast_action_context,
)
from services.assessments.dalfox_xss_actions import (
    DalfoxXssActionContext,
    dalfox_xss_action_context,
)
from services.assessments.schemathesis_actions import (
    SchemathesisActionContext,
    schemathesis_action_context,
)
from services.connectors.oast_config import oast_connector_settings


def resolve_selection_contexts(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    check_key: str,
    target: Mapping[str, str] | None,
    selection: Mapping[str, str] | None,
) -> tuple[
    DalfoxXssActionContext | None,
    DalfoxOastActionContext | None,
    SchemathesisActionContext | None,
]:
    """Resolve caller ids only through the matching reviewed action contract."""
    intrusive_enabled = bool(
        app_config.CFG.get("assessment_intrusive_actions_enabled", False)
    )
    xss = dalfox_xss_action_context(
        conn,
        session_id,
        team_id,
        project_id,
        check_key,
        target,
        selection,
        enabled=intrusive_enabled,
    )
    oast = dalfox_oast_action_context(
        conn,
        session_id,
        team_id,
        project_id,
        check_key,
        target,
        selection,
        intrusive_enabled=intrusive_enabled,
        connector_settings=oast_connector_settings(),
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
    if xss is not None or oast is not None:
        supported_keys.update({"source_run_id", "parameter_observation_id"})
    if schemathesis is not None:
        supported_keys.add("schema_artifact_id")
    supplied = {
        key
        for key, value in (selection or {}).items()
        if str(value or "").strip()
    }
    if supplied - supported_keys:
        raise AssessmentActionError(
            "unsupported_evidence_selection",
            "Saved evidence selection doesn't apply to this reviewed action.",
        )
    return xss, oast, schemathesis


__all__ = ["resolve_selection_contexts"]
