# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed execution material for one reviewed private-OAST Dalfox run."""

from __future__ import annotations

from dataclasses import dataclass, field

from services.assessments.command_plans import command_plan
from services.assessments.dalfox_oast_command import reviewed_dalfox_oast_command_plan
from services.assessments.dalfox_parameter_evidence import (
    ReviewedDalfoxParameterEvidence,
)


@dataclass(frozen=True)
class ReviewedDalfoxOastExecution:
    """Recompute the validated carrier and callback-bearing active command."""

    evidence: ReviewedDalfoxParameterEvidence
    callback_url: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.evidence) is not ReviewedDalfoxParameterEvidence:
            raise ValueError("invalid reviewed Dalfox OAST execution evidence")
        self._plans()

    def _plans(self):
        carrier = command_plan(
            "dalfox",
            "url",
            self.evidence.target,
            protected_display=False,
        )
        active = reviewed_dalfox_oast_command_plan(
            self.evidence,
            callback_url=self.callback_url,
        )
        if carrier is None or active is None:
            raise ValueError("reviewed Dalfox OAST execution is unavailable")
        return carrier, active

    @property
    def validation_command(self) -> str:
        return self._plans()[0].command

    @property
    def execution_command(self) -> str:
        return self._plans()[1].command


__all__ = ["ReviewedDalfoxOastExecution"]
