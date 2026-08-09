# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed findings-exit handling for the pinned Schemathesis report."""

from __future__ import annotations

import logging

from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution
from services.assessments.schemathesis_report_context import (
    ReviewedSchemathesisReportContext,
)


log = logging.getLogger("shell")


def accepts_schemathesis_findings_exit(execution: object) -> bool:
    """Accept exit 1 only when its exact private report proves reviewed failures."""
    if type(execution) is not ReviewedSchemathesisExecution:
        return False
    context = execution.report_context
    if (
        type(context) is not ReviewedSchemathesisReportContext
        or context.schema != execution.schema
    ):
        return False
    try:
        report = context.parse()
    except (OSError, RuntimeError, ValueError) as exc:
        log.warning(
            "SCHEMATHESIS_FINDINGS_EXIT_REJECTED",
            extra={"reason": str(getattr(exc, "code", "report_unavailable"))[:64]},
        )
        return False
    if not report.complete or report.failure_count <= 0:
        log.warning(
            "SCHEMATHESIS_FINDINGS_EXIT_REJECTED",
            extra={
                "reason": "incomplete_report" if not report.complete else "no_reviewed_failures",
            },
        )
        return False
    return True


__all__ = ["accepts_schemathesis_findings_exit"]
