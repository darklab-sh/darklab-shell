# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Apply exact app-owned execution only after an ordinary command validates."""

from dataclasses import replace
from typing import Any

from services.assessments.dalfox_xss_execution import ReviewedDalfoxXssExecution
from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution
from services.runs.contracts import RunPreparationError
from services.runs.schemathesis_execution_override import apply_schemathesis_execution
from services.runs.signal_context import RunOutputSignalContext

def apply_reviewed_execution(
    prepared: Any,
    reviewed_execution: object | None,
    *,
    output_signal_context: RunOutputSignalContext | None = None,
) -> Any:
    """Replace a validated carrier with its evidence-derived active command."""
    if reviewed_execution is None:
        return prepared
    if type(reviewed_execution) is ReviewedSchemathesisExecution:
        return apply_schemathesis_execution(prepared, reviewed_execution)
    if type(reviewed_execution) is not ReviewedDalfoxXssExecution:
        raise RunPreparationError("Reviewed execution context is invalid.")
    try:
        validation_command = reviewed_execution.validation_command
        execution_command = reviewed_execution.execution_command
        reviewed_output_context = reviewed_execution.output_context
    except ValueError as exc:
        raise RunPreparationError("Reviewed execution context is unavailable.") from exc
    if (
        type(output_signal_context) is not RunOutputSignalContext
        or output_signal_context.dalfox_xss_context != reviewed_output_context
    ):
        raise RunPreparationError(
            "Reviewed execution output context no longer matches saved evidence."
        )
    if str(getattr(prepared, "registry_command", "")) != validation_command:
        raise RunPreparationError("Reviewed execution carrier no longer matches validation.")
    return replace(
        prepared,
        execution_command=execution_command,
        command=execution_command,
        rewrite_notice=None,
    )


__all__ = ["apply_reviewed_execution"]
