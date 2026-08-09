# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed blind-XSS commands backed by the private OAST boundary."""

from __future__ import annotations

from services.assessments.command_modes import (
    DALFOX_OAST_VALIDATION_MODE,
    assessment_command_mode,
)
from services.assessments.dalfox_oast_command import (
    DALFOX_OAST_DISPLAY_CALLBACK,
    reviewed_dalfox_oast_command_plan,
)
from services.assessments.dalfox_parameter_evidence import (
    ReviewedDalfoxParameterEvidence,
)
from services.assessments.dalfox_parameter_observations import (
    DALFOX_DISCOVERY_PARSER_VERSION,
    dalfox_parameter_observation_id,
)


def _evidence() -> ReviewedDalfoxParameterEvidence:
    run_id = "run-dalfox-discovery"
    target = "https://app.example.test/search?q=one"
    parameter = "q"
    location = "Query"
    return ReviewedDalfoxParameterEvidence(
        source_run_id=run_id,
        observation_id=dalfox_parameter_observation_id(
            run_id, target, location, parameter,
        ),
        target=target,
        parameter=parameter,
        location=location,
        tool_version="v3.1.2",
        parser_version=DALFOX_DISCOVERY_PARSER_VERSION,
    )


def test_reviewed_blind_xss_command_uses_only_the_app_callback_path():
    evidence = _evidence()
    plan = reviewed_dalfox_oast_command_plan(evidence)

    assert plan is not None
    assert f"--blind '{DALFOX_OAST_DISPLAY_CALLBACK}'" in plan.command
    assert assessment_command_mode(plan.command) == DALFOX_OAST_VALIDATION_MODE
    assert assessment_command_mode(
        plan.command + " --config [protected]"
    ) == DALFOX_OAST_VALIDATION_MODE
    assert plan.request_limit == 256
    assert plan.time_limit_seconds == 90
    assert all(flag not in plan.command for flag in (
        "--blind-oob", "--blind-oob-secret", "--remote-payloads",
        "--custom-blind-xss-payload", "--follow-redirects", "--deep-scan",
    ))
    actual = reviewed_dalfox_oast_command_plan(
        evidence,
        callback_url="https://abc123.callbacks.example.test",
    )
    assert actual is not None
    assert "--blind https://abc123.callbacks.example.test" in actual.command
    assert reviewed_dalfox_oast_command_plan(
        evidence,
        callback_url="https://user:secret@callbacks.example.test/path?token=one",
    ) is None
    assert reviewed_dalfox_oast_command_plan(
        evidence,
        callback_url="https://ABC123.callbacks.example.test",
    ) is None
    assert reviewed_dalfox_oast_command_plan(
        evidence,
        callback_url="https://abc123.callbacks.example.test:443",
    ) is None
    assert assessment_command_mode(
        plan.command.replace("--rate-limit 2", "--rate-limit 3")
    ) == ""
