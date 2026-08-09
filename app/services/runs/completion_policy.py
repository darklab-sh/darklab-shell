# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Internal completion rules for app-owned structured command launches."""

from __future__ import annotations

from typing import Any

from services.assessments.dalfox_xss_observations import (
    DalfoxXssObservationState,
)
from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution
from services.runs.completion_policy_contracts import (
    DALFOX_FINDINGS_COMPLETION_POLICY,
    SCHEMATHESIS_FINDINGS_COMPLETION_POLICY,
    RunCompletionPolicy,
)
from services.runs.schemathesis_completion import accepts_schemathesis_findings_exit
from services.runs.signal_context import RunOutputSignalContext


def completion_policy_for_signal_context(
    context: RunOutputSignalContext | None,
    *,
    reviewed_execution: object | None = None,
) -> RunCompletionPolicy | None:
    """Derive completion behavior only from an app-owned output context."""
    if type(reviewed_execution) is ReviewedSchemathesisExecution:
        if context is not None and context.dalfox_xss_context is not None:
            return None
        return RunCompletionPolicy(schemathesis_execution=reviewed_execution)
    if context is None or context.dalfox_xss_context is None:
        return None
    return RunCompletionPolicy(context.dalfox_xss_context)


def effective_run_exit_code(
    tool_exit_code: int | None,
    *,
    completion_policy: RunCompletionPolicy | None,
    signal_classifier: Any,
    output_sink_error: bool,
) -> int | None:
    """Map a documented findings exit to success only after valid evidence."""
    if output_sink_error:
        return 1 if tool_exit_code == 0 else tool_exit_code
    if tool_exit_code != 1 or type(completion_policy) is not RunCompletionPolicy:
        return tool_exit_code
    if completion_policy.schemathesis_execution is not None:
        return (
            0
            if accepts_schemathesis_findings_exit(
                completion_policy.schemathesis_execution
            )
            else tool_exit_code
        )
    dalfox_state = getattr(signal_classifier, "dalfox_xss", None)
    if type(dalfox_state) is not DalfoxXssObservationState:
        return tool_exit_code
    if not dalfox_state.accepts_findings_exit(completion_policy.dalfox_xss_context):
        return tool_exit_code
    return 0


__all__ = [
    "DALFOX_FINDINGS_COMPLETION_POLICY",
    "SCHEMATHESIS_FINDINGS_COMPLETION_POLICY",
    "RunCompletionPolicy",
    "completion_policy_for_signal_context",
    "effective_run_exit_code",
]
