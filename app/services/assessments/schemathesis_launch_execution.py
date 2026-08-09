# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Build typed execution from one private Schemathesis launch boundary."""

from collections.abc import Mapping
from typing import Any

from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution
from services.assessments.schemathesis_material import ProtectedSchemathesisMaterial
from services.assessments.schemathesis_report_context import ReviewedSchemathesisReportContext


def reviewed_schemathesis_execution(
    material: ProtectedSchemathesisMaterial,
    plan: Mapping[str, Any],
) -> ReviewedSchemathesisExecution:
    """Bind private paths and report provenance to the reviewed plan snapshot."""
    report_context = ReviewedSchemathesisReportContext(
        schema=material.schema,
        project_id=str(plan.get("project_id") or ""), assessment_id=str(plan.get("assessment_id") or ""),
        check_id=str(plan.get("check_id") or ""), profile_key=str(plan.get("profile_key") or ""),
        profile_version=str(plan.get("profile_version") or ""), read_report=material.read_report,
    )
    return ReviewedSchemathesisExecution(
        material.schema, material.schema_path,
        material.config_path, material.report_path,
        report_context,
    )


__all__ = ["reviewed_schemathesis_execution"]
