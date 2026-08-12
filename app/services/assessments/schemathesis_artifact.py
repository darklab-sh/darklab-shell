# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-scoped OpenAPI artifacts and private Schemathesis material."""

from __future__ import annotations

import hashlib
import os
from typing import Any, cast

from services.assessments.schemathesis_schema import (
    ReviewedOpenApiSchema,
    SCHEMATHESIS_SCHEMA_MAX_BYTES,
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


def _recorded_size(artifact: dict[str, Any]) -> int:
    try:
        recorded_size = int(cast(Any, artifact.get("byte_size")))
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


__all__ = [
    "SchemathesisArtifactError",
    "review_project_openapi_artifact",
]
