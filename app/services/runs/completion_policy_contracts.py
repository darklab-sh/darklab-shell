# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed completion exceptions for app-owned structured command launches."""

from dataclasses import dataclass

from services.assessments.dalfox_xss_observations import ReviewedDalfoxXssContext
from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution


DALFOX_FINDINGS_COMPLETION_POLICY = "dalfox_findings"
SCHEMATHESIS_FINDINGS_COMPLETION_POLICY = "schemathesis_findings"


@dataclass(frozen=True)
class RunCompletionPolicy:
    """One typed completion exception derived from app-owned run context."""

    dalfox_xss_context: ReviewedDalfoxXssContext | None = None
    schemathesis_execution: ReviewedSchemathesisExecution | None = None

    def __post_init__(self) -> None:
        dalfox = type(self.dalfox_xss_context) is ReviewedDalfoxXssContext
        schemathesis = type(self.schemathesis_execution) is ReviewedSchemathesisExecution
        if dalfox == schemathesis:
            raise ValueError("invalid run completion context")

    @property
    def name(self) -> str:
        if self.schemathesis_execution is not None:
            return SCHEMATHESIS_FINDINGS_COMPLETION_POLICY
        return DALFOX_FINDINGS_COMPLETION_POLICY


__all__ = [
    "DALFOX_FINDINGS_COMPLETION_POLICY",
    "SCHEMATHESIS_FINDINGS_COMPLETION_POLICY",
    "RunCompletionPolicy",
]
