# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Apply one exact reviewed Schemathesis execution over its safe carrier."""

from dataclasses import replace
from typing import Any

from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution
from services.runs.contracts import RunPreparationError


def apply_schemathesis_execution(
    prepared: Any,
    reviewed: ReviewedSchemathesisExecution,
) -> Any:
    try:
        validation_command = reviewed.validation_command
        execution_command = reviewed.execution_command
    except ValueError as exc:
        raise RunPreparationError("Reviewed execution context is unavailable.") from exc
    if str(getattr(prepared, "registry_command", "")) != validation_command:
        raise RunPreparationError("Reviewed execution carrier no longer matches validation.")
    return replace(
        prepared,
        execution_command=execution_command,
        command=execution_command,
        rewrite_notice=None,
    )


__all__ = ["apply_schemathesis_execution"]
