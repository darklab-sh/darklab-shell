# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed blind-XSS commands backed by the private OAST boundary."""

from __future__ import annotations

from typing import Any, cast

import pytest

from core.output_signals import OutputSignalClassifier
from services.assessments.command_modes import (
    DALFOX_OAST_VALIDATION_MODE,
    assessment_command_mode,
)
from services.assessments.dalfox_oast_command import (
    DALFOX_OAST_DISPLAY_CALLBACK,
    reviewed_dalfox_oast_command_plan,
)
from services.assessments.dalfox_oast_execution import ReviewedDalfoxOastExecution
from services.assessments.dalfox_parameter_evidence import (
    ReviewedDalfoxParameterEvidence,
)
from services.assessments.dalfox_parameter_observations import (
    DALFOX_DISCOVERY_PARSER_VERSION,
    dalfox_parameter_observation_id,
)
from services.runs.execution_override import apply_reviewed_execution
from services.runs.contracts import RunPreparationError
from services.runs.lifecycle import PreparedRealCommand
from services.runs.signal_context import RunOutputSignalContext


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


def test_reviewed_oast_execution_keeps_callback_private_and_discovery_disabled():
    callback = "https://abc123.callbacks.example.test"
    reviewed = ReviewedDalfoxOastExecution(_evidence(), callback)
    classifier = OutputSignalClassifier(
        reviewed.validation_command,
        source_run_id="12345678-1234-4123-8123-123456789abc",
        dalfox_oast_validation=True,
    )

    assert callback in reviewed.execution_command
    assert callback not in reviewed.validation_command
    metadata = classifier.classify_line(
        '{"meta":{"mode":"only_discovery","dalfox_version":"v3.1.2",'
        '"params_discovered":1}}'
    )
    source_detail = metadata.get("source_detail")
    assert not isinstance(source_detail, dict) or (
        "parameter_discovery" not in source_detail
    )


def test_reviewed_oast_execution_requires_typed_output_suppression_context():
    reviewed = ReviewedDalfoxOastExecution(
        _evidence(),
        "https://abc123.callbacks.example.test",
    )
    prepared = PreparedRealCommand(
        registry_command=reviewed.validation_command,
        execution_command=reviewed.validation_command,
        command=reviewed.validation_command,
        rewrite_notice="carrier",
        validation=cast(Any, None),
        missing_runtime=None,
        display_missing_runtime=None,
        env_overrides={},
        secret_env_names=[],
    )

    active = apply_reviewed_execution(
        prepared,
        reviewed,
        output_signal_context=RunOutputSignalContext(
            dalfox_oast_validation=True,
        ),
    )

    assert active.execution_command == reviewed.execution_command
    assert active.rewrite_notice is None
    with pytest.raises(RunPreparationError, match="private OAST execution context"):
        apply_reviewed_execution(prepared, reviewed)
