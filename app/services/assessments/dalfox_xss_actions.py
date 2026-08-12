# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Saved-evidence context for one reviewed Assessment XSS action."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from services.assessments.command_plan_contracts import CommandPlan
from services.assessments.dalfox_parameter_evidence import ReviewedDalfoxParameterEvidence
from services.assessments.dalfox_parameter_options import (
    DalfoxParameterOptions,
    list_project_dalfox_parameter_options,
)
from services.assessments.dalfox_xss_command import reviewed_dalfox_xss_command_plan
from services.assessments.dalfox_xss_contracts import DALFOX_XSS_VALIDATION_CHECK_KEY


@dataclass(frozen=True)
class DalfoxXssActionContext:
    options: DalfoxParameterOptions
    selected: ReviewedDalfoxParameterEvidence | None
    selection_requested: bool
    selection_invalid: bool
    enabled: bool

    def public_selection(self) -> dict[str, Any]:
        selected = self.selected
        return {
            "kind": "dalfox_parameter_observation",
            "required": True,
            "overflow": self.options.overflow,
            "options": self.options.public_items(),
            "selected": ({
                "source_run_id": selected.source_run_id,
                "observation_id": selected.observation_id,
                "parameter": selected.parameter,
                "location": selected.location,
                "tool_version": selected.tool_version,
            } if selected else None),
        }

    def unavailable_reason(self) -> str:
        if not self.enabled:
            return "Intrusive Assessment actions are disabled on this deployment."
        if self.options.overflow:
            return "Saved Dalfox parameter evidence exceeds the review limit. Narrow the Project evidence before launching."
        if self.selection_invalid:
            return "The selected Dalfox parameter evidence is unavailable or no longer matches this target."
        if not self.options.items:
            return "Run parameter discovery for this exact URL before starting XSS validation."
        if not self.selected:
            return "Choose one saved query-parameter observation before reviewing the XSS validation plan."
        return ""

    def command_plan(self, http_profile: Mapping[str, Any] | None) -> CommandPlan | None:
        if not self.selected:
            return None
        plan = reviewed_dalfox_xss_command_plan(self.selected)
        if plan is None or not http_profile:
            return plan
        uses = set(http_profile.get("credential_use") or []) - {"client_certificate"}
        if not uses:
            return plan
        return CommandPlan(
            plan.command + " --config [protected]",
            plan.boundary,
            plan.request_limit,
            plan.time_limit_seconds,
            "protected_http_profile",
        )


def dalfox_xss_action_context(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    check_key: str,
    target: Mapping[str, str] | None,
    selection: Mapping[str, str] | None,
    *,
    enabled: bool,
) -> DalfoxXssActionContext | None:
    """Resolve caller identifiers only against reviewed saved evidence."""
    requested = {
        key: str((selection or {}).get(key) or "").strip()
        for key in ("source_run_id", "parameter_observation_id")
    }
    selection_requested = bool(requested["source_run_id"] or requested["parameter_observation_id"])
    if check_key != DALFOX_XSS_VALIDATION_CHECK_KEY:
        return None
    options = (
        list_project_dalfox_parameter_options(
            conn, session_id, team_id, project_id, str(target.get("value") or ""),
        )
        if target and str(target.get("type") or "") == "url"
        else DalfoxParameterOptions(())
    )
    complete_selection = bool(
        requested["source_run_id"] and requested["parameter_observation_id"]
    )
    selected = options.selected(
        requested["source_run_id"], requested["parameter_observation_id"],
    ) if complete_selection and not options.overflow else None
    return DalfoxXssActionContext(
        options,
        selected,
        selection_requested,
        selection_requested and (not complete_selection or selected is None),
        enabled,
    )


__all__ = ["DalfoxXssActionContext", "dalfox_xss_action_context"]
