# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-scoped OpenAPI artifacts and private Schemathesis material."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any

from services.assessments.http_profile_runtime import (
    PrivateHttpMaterialError,
    PrivateHttpRunMaterial,
)
from services.assessments.schemathesis_schema import (
    ReviewedOpenApiSchema,
    SCHEMATHESIS_SCHEMA_MAX_BYTES,
    SchemathesisSchemaError,
    review_local_openapi_json,
)
from services.projects.artifact_queries import get_project_run_file_artifact
from services.projects.artifacts import artifact_owner_context, normalize_sha256
from services.workspace.files import WorkspaceError, open_owner_workspace_file_for_download


class SchemathesisArtifactError(RuntimeError):
    """A stable rejection while resolving or materializing a schema artifact."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProtectedSchemathesisMaterial:
    """One reviewed schema and its short-lived scanner-owned files."""

    schema: ReviewedOpenApiSchema
    schema_path: Path
    report_path: Path
    private_values: tuple[str, ...]
    cleanup: Any


def review_project_openapi_artifact(
    session_id: str,
    project_id: str,
    artifact_id: str,
    *,
    base_url: str,
    team_id: str = "",
) -> ReviewedOpenApiSchema:
    """Read and review one unchanged Project-linked run-file artifact."""
    selected_artifact_id = str(artifact_id or "").strip()
    artifact = get_project_run_file_artifact(
        session_id,
        project_id,
        selected_artifact_id,
        team_id=team_id,
    )
    if not artifact or str(artifact.get("id") or "") != selected_artifact_id:
        raise SchemathesisArtifactError(
            "schema_artifact_not_found",
            "The selected OpenAPI artifact isn't available in this Project.",
        )
    if artifact.get("file_status") != "available" or artifact.get("file_available") is not True:
        raise SchemathesisArtifactError(
            "schema_artifact_unavailable",
            "The selected OpenAPI artifact is unavailable or changed.",
        )
    recorded_size = _recorded_size(artifact)
    recorded_hash = normalize_sha256(artifact.get("content_sha256"))
    if not recorded_hash:
        raise SchemathesisArtifactError(
            "schema_artifact_digest_missing",
            "The selected OpenAPI artifact has no recorded integrity digest.",
        )
    owner = artifact_owner_context(str(artifact.get("session_id") or session_id), artifact)
    try:
        with open_owner_workspace_file_for_download(owner, str(artifact.get("workspace_path") or "")) as handle:
            descriptor_size = max(0, int(os.fstat(handle.fileno()).st_size))
            content = handle.read(SCHEMATHESIS_SCHEMA_MAX_BYTES + 1)
    except (OSError, WorkspaceError) as exc:
        raise SchemathesisArtifactError(
            "schema_artifact_unavailable",
            "The selected OpenAPI artifact couldn't be read safely.",
        ) from exc
    if descriptor_size != recorded_size or len(content) != recorded_size:
        raise SchemathesisArtifactError(
            "schema_artifact_changed",
            "The selected OpenAPI artifact changed after it was recorded.",
        )
    if hashlib.sha256(content).hexdigest() != recorded_hash:
        raise SchemathesisArtifactError(
            "schema_artifact_changed",
            "The selected OpenAPI artifact changed after it was recorded.",
        )
    return review_local_openapi_json(
        content,
        source_artifact_id=selected_artifact_id,
        base_url=base_url,
    )


def materialize_reviewed_schemathesis_schema(
    schema: ReviewedOpenApiSchema,
    *,
    cfg=None,
) -> ProtectedSchemathesisMaterial:
    """Copy one reviewed schema into short-lived private scanner material."""
    reviewed = _rereview(schema)
    material: PrivateHttpRunMaterial | None = None
    try:
        material = PrivateHttpRunMaterial(cfg=cfg)
        schema_path = material.write_bytes("schema.json", reviewed.content)
        report_path = material.write_bytes("events.ndjson", b"")
    except (OSError, PrivateHttpMaterialError) as exc:
        if material:
            material.cleanup()
        raise SchemathesisArtifactError(
            "schemathesis_materialization_failed",
            "Protected Schemathesis run material couldn't be prepared.",
        ) from exc
    return ProtectedSchemathesisMaterial(
        schema=reviewed,
        schema_path=schema_path,
        report_path=report_path,
        private_values=(str(schema_path), str(report_path)),
        cleanup=material.cleanup,
    )


def _recorded_size(artifact: dict[str, Any]) -> int:
    try:
        recorded_size = int(artifact.get("byte_size"))
    except (TypeError, ValueError) as exc:
        raise SchemathesisArtifactError(
            "schema_artifact_size_invalid",
            "The selected OpenAPI artifact has invalid size metadata.",
        ) from exc
    if recorded_size <= 0 or recorded_size > SCHEMATHESIS_SCHEMA_MAX_BYTES:
        raise SchemathesisArtifactError(
            "schema_artifact_size_invalid",
            "The selected OpenAPI artifact is empty or larger than 1 MiB.",
        )
    return recorded_size


def _rereview(schema: Any) -> ReviewedOpenApiSchema:
    if type(schema) is not ReviewedOpenApiSchema:
        raise SchemathesisArtifactError(
            "schema_review_required",
            "Schemathesis material requires one reviewed OpenAPI artifact.",
        )
    try:
        reviewed = review_local_openapi_json(
            schema.content,
            source_artifact_id=schema.source_artifact_id,
            base_url=schema.base_url,
        )
    except SchemathesisSchemaError as exc:
        raise SchemathesisArtifactError(
            "schema_review_changed",
            "The reviewed OpenAPI artifact no longer passes schema review.",
        ) from exc
    if reviewed != schema:
        raise SchemathesisArtifactError(
            "schema_review_changed",
            "The reviewed OpenAPI artifact changed before materialization.",
        )
    return reviewed


__all__ = [
    "ProtectedSchemathesisMaterial",
    "SchemathesisArtifactError",
    "materialize_reviewed_schemathesis_schema",
    "review_project_openapi_artifact",
]
