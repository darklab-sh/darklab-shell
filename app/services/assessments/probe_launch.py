# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Materialize the private-free broker context for one confirmed probe plan."""

from __future__ import annotations

from typing import Any, Mapping

import config as app_config
from services.assessments.nuclei_profile_launch import (
    NucleiProfileLaunchError,
    validate_nuclei_profile_launch,
)
from services.assessments.probe_contracts import ProbeError
from services.assessments.run_launch_context import AssessmentRunLaunchContext
from services.runs.signal_context import RunOutputSignalContext
from services.nuclei.template_cache import managed_nuclei_template_snapshot


def probe_run_launch_context(
    plan: Mapping[str, Any],
    *,
    trusted_execution_args: tuple[str, ...] = (),
) -> AssessmentRunLaunchContext:
    """Revalidate launch-only state without creating protected material."""
    action = plan.get("action")
    if not isinstance(action, Mapping) or str(action.get("id") or "") != "nuclei":
        return AssessmentRunLaunchContext(trusted_execution_args=trusted_execution_args)
    profile = plan.get("profile")
    profile_key = str(profile.get("id") or "") if isinstance(profile, Mapping) else ""
    expected = profile.get("template_snapshot") if isinstance(profile, Mapping) else None
    try:
        snapshot = validate_nuclei_profile_launch(
            display_command=plan.get("display_command"),
            profile_key=profile_key,
            expected_snapshot=expected if isinstance(expected, Mapping) else None,
            policy_level=plan.get("policy_level"),
            intrusive_actions_enabled=bool(
                app_config.CFG.get("assessment_intrusive_actions_enabled", False)
            ),
            current_snapshot=managed_nuclei_template_snapshot(),
        )
    except NucleiProfileLaunchError as exc:
        raise ProbeError(exc.code, str(exc), status_code=409) from exc
    return AssessmentRunLaunchContext(
        trusted_execution_args=trusted_execution_args,
        output_signal_context=RunOutputSignalContext(nuclei_template_snapshot=snapshot),
    )


__all__ = ["probe_run_launch_context"]
