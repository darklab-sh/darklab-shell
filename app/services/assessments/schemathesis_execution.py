# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed execution material for one reviewed Schemathesis API check."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.assessments.schemathesis_command import reviewed_schemathesis_command_plan
from services.assessments.schemathesis_schema import ReviewedOpenApiSchema


@dataclass(frozen=True)
class ReviewedSchemathesisExecution:
    """Recompute the protected command from one unchanged reviewed schema."""

    schema: ReviewedOpenApiSchema
    schema_path: Path
    config_path: Path
    report_path: Path
    report_context: object

    def __post_init__(self) -> None:
        if type(self.schema) is not ReviewedOpenApiSchema:
            raise ValueError("invalid reviewed Schemathesis schema")
        if self._plan() is None:
            raise ValueError("reviewed Schemathesis execution is unavailable")

    def _plan(self):
        return reviewed_schemathesis_command_plan(
            self.schema,
            schema_path=self.schema_path,
            config_path=self.config_path,
            report_path=self.report_path,
        )

    @property
    def validation_command(self) -> str:
        return "schemathesis --help"

    @property
    def execution_command(self) -> str:
        plan = self._plan()
        if plan is None:
            raise ValueError("reviewed Schemathesis execution is unavailable")
        return plan.command
