# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Revalidate and materialize one reviewed Schemathesis Assessment run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from services.assessments.action_plans import AssessmentActionError
from services.assessments.http_profile_execution import ProtectedHttpLaunch
from services.assessments.schemathesis_actions import SCHEMATHESIS_CHECK_KEY
from services.assessments.schemathesis_artifact import (
    SchemathesisArtifactError,
    review_project_openapi_artifact,
)
from services.assessments.schemathesis_command import reviewed_schemathesis_command_matches
from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution
from services.assessments.schemathesis_launch_execution import reviewed_schemathesis_execution
from services.assessments.schemathesis_material import materialize_reviewed_schemathesis_schema
from services.assessments.schemathesis_schema import SchemathesisSchemaError


@dataclass(frozen=True)
class SchemathesisLaunch:
    protected: ProtectedHttpLaunch
    reviewed_execution: ReviewedSchemathesisExecution


def materialize_reviewed_schemathesis_launch(
    session_id: str,
    project_id: str,
    plan: Mapping[str, Any],
    *,
    team_id: str = "",
) -> SchemathesisLaunch | None:
    """Return protected material only for the exact saved API-check contract."""
    if str(plan.get("check_key") or "") != SCHEMATHESIS_CHECK_KEY:
        return None
    target = plan.get("target")
    action = plan.get("action")
    selection = plan.get("artifact_selection")
    selected = selection.get("selected") if isinstance(selection, Mapping) else None
    if (
        not isinstance(target, Mapping)
        or str(target.get("type") or "") != "url"
        or not isinstance(action, Mapping)
        or str(action.get("id") or "") != "schemathesis"
        or str(plan.get("policy_level") or "") != "standard"
        or not isinstance(selected, Mapping)
    ):
        raise AssessmentActionError(
            "schemathesis_launch_contract_invalid",
            "The reviewed API check no longer has its expected launch contract.",
            status_code=409,
        )
    artifact_id = str(selected.get("artifact_id") or "")
    try:
        schema = review_project_openapi_artifact(
            session_id,
            project_id,
            artifact_id,
            base_url=str(target.get("value") or ""),
            team_id=team_id,
        )
    except (SchemathesisArtifactError, SchemathesisSchemaError) as exc:
        raise AssessmentActionError(
            getattr(exc, "code", "schema_artifact_unavailable"),
            str(exc),
            status_code=409,
        ) from exc
    if not _selection_matches(selected, schema) or not reviewed_schemathesis_command_matches(
        plan.get("display_command"), schema,
    ):
        raise AssessmentActionError(
            "schemathesis_plan_changed",
            "The reviewed OpenAPI plan changed. Preview and confirm it again.",
            status_code=409,
        )
    material = None
    try:
        material = materialize_reviewed_schemathesis_schema(schema)
        execution = reviewed_schemathesis_execution(material, plan)
    except (SchemathesisArtifactError, ValueError) as exc:
        if material is not None:
            material.cleanup()
        raise AssessmentActionError(
            getattr(exc, "code", "schemathesis_materialization_failed"),
            str(exc),
            status_code=503,
        ) from exc
    protected = ProtectedHttpLaunch(
        execution_command=execution.validation_command,
        trusted_execution_args=(),
        private_values=material.private_values,
        cleanup=material.cleanup,
        audit_summary={
            "schema_artifact_id": artifact_id,
            "schema_operation_count": schema.operation_count,
        },
    )
    return SchemathesisLaunch(protected, execution)


def _selection_matches(
    selected: Mapping[str, Any],
    schema: Any,
) -> bool:
    value = selected.get("operation_count")
    if value is None:
        return False
    try:
        operation_count = int(value)
    except (TypeError, ValueError):
        return False
    return bool(
        str(selected.get("artifact_id") or "") == schema.source_artifact_id
        and str(selected.get("schema_sha256") or "") == schema.source_sha256
        and str(selected.get("openapi_version") or "") == schema.schema_version
        and operation_count == schema.operation_count
    )

__all__ = ["SchemathesisLaunch", "materialize_reviewed_schemathesis_launch"]
