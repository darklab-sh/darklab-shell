# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed execution material for one saved-evidence Dalfox XSS check."""

from __future__ import annotations

from dataclasses import dataclass

from services.assessments.command_plans import command_plan
from services.assessments.dalfox_parameter_evidence import ReviewedDalfoxParameterEvidence
from services.assessments.dalfox_xss_command import reviewed_dalfox_xss_command_plan
from services.assessments.dalfox_xss_observations import ReviewedDalfoxXssContext


@dataclass(frozen=True)
class ReviewedDalfoxXssExecution:
    """Recompute both the validated carrier and active command from saved evidence."""

    evidence: ReviewedDalfoxParameterEvidence

    def __post_init__(self) -> None:
        if type(self.evidence) is not ReviewedDalfoxParameterEvidence:
            raise ValueError("invalid reviewed Dalfox execution evidence")
        self._plans()

    def _plans(self):
        carrier = command_plan(
            "dalfox",
            "url",
            self.evidence.target,
            protected_display=False,
        )
        active = reviewed_dalfox_xss_command_plan(self.evidence)
        if carrier is None or active is None:
            raise ValueError("reviewed Dalfox execution is unavailable")
        return carrier, active

    @property
    def validation_command(self) -> str:
        return self._plans()[0].command

    @property
    def execution_command(self) -> str:
        return self._plans()[1].command

    @property
    def output_context(self) -> ReviewedDalfoxXssContext:
        active = self._plans()[1]
        return self.evidence.xss_context(request_limit=int(active.request_limit or 0))


__all__ = ["ReviewedDalfoxXssExecution"]
