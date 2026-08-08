# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Internal completion rules for app-owned structured command launches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.assessments.dalfox_xss_observations import (
    DalfoxXssObservationState,
    ReviewedDalfoxXssContext,
)
from services.runs.signal_context import RunOutputSignalContext


DALFOX_FINDINGS_COMPLETION_POLICY = "dalfox_findings"


@dataclass(frozen=True)
class RunCompletionPolicy:
    """One typed completion exception derived from trusted signal context."""

    dalfox_xss_context: ReviewedDalfoxXssContext

    def __post_init__(self) -> None:
        if type(self.dalfox_xss_context) is not ReviewedDalfoxXssContext:
            raise ValueError("invalid Dalfox completion context")

    @property
    def name(self) -> str:
        return DALFOX_FINDINGS_COMPLETION_POLICY


def completion_policy_for_signal_context(
    context: RunOutputSignalContext | None,
) -> RunCompletionPolicy | None:
    """Derive completion behavior only from an app-owned output context."""
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
    dalfox_state = getattr(signal_classifier, "dalfox_xss", None)
    if type(dalfox_state) is not DalfoxXssObservationState:
        return tool_exit_code
    if not dalfox_state.accepts_findings_exit(completion_policy.dalfox_xss_context):
        return tool_exit_code
    return 0


__all__ = [
    "DALFOX_FINDINGS_COMPLETION_POLICY",
    "RunCompletionPolicy",
    "completion_policy_for_signal_context",
    "effective_run_exit_code",
]
