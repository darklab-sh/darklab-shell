# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Short-lived private material for one reviewed Schemathesis run."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from services.assessments.http_profile_runtime import (
    PrivateHttpMaterialError,
    PrivateHttpRunMaterial,
)
from services.assessments.schemathesis_artifact import SchemathesisArtifactError
from services.assessments.schemathesis_report import SCHEMATHESIS_REPORT_MAX_BYTES
from services.assessments.schemathesis_schema import (
    ReviewedOpenApiSchema,
    SchemathesisSchemaError,
    review_local_openapi_json,
)


_SCHEMATHESIS_CONFIG = b'[cache]\nenabled = false\n\n[generation]\ndatabase = "none"\n'


@dataclass(frozen=True)
class ProtectedSchemathesisMaterial:
    """One reviewed schema and its short-lived scanner-owned files."""

    schema: ReviewedOpenApiSchema
    schema_path: Path
    config_path: Path
    report_path: Path
    private_values: tuple[str, ...]
    read_report: Any
    cleanup: Any


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
        config_path = material.write_bytes("schemathesis.toml", _SCHEMATHESIS_CONFIG)
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
        config_path=config_path,
        report_path=report_path,
        private_values=tuple(map(str, (schema_path, config_path, report_path))),
        read_report=partial(
            material.read_bytes,
            "events.ndjson",
            max_bytes=SCHEMATHESIS_REPORT_MAX_BYTES,
        ),
        cleanup=material.cleanup,
    )


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
    "materialize_reviewed_schemathesis_schema",
]
