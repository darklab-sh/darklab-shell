# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Saved OpenAPI artifact choices for the reviewed Schemathesis action."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from services.assessments.command_plan_contracts import CommandPlan
from services.assessments.schemathesis_artifact import (
    SchemathesisArtifactError,
    review_project_openapi_artifact,
)
from services.assessments.schemathesis_command import reviewed_schemathesis_command_plan
from services.assessments.schemathesis_schema import (
    ReviewedOpenApiSchema,
    SCHEMATHESIS_SCHEMA_MAX_BYTES,
    SchemathesisSchemaError,
)
from services.projects.scope import shared_owner_where


SCHEMATHESIS_CHECK_KEY = "openapi_negative_testing"
SCHEMATHESIS_ARTIFACT_OPTION_LIMIT = 64
_JSON_CONTENT_TYPES = frozenset({
    "application/json",
    "application/openapi+json",
    "application/vnd.oai.openapi+json",
})


@dataclass(frozen=True)
class SchemathesisActionContext:
    """Bounded candidates and one optional fully reviewed schema."""

    options: tuple[dict[str, Any], ...]
    selected_option: dict[str, Any] | None
    reviewed_schema: ReviewedOpenApiSchema | None
    selection_requested: bool
    selection_invalid: bool
    overflow: bool
    review_error: str = ""

    def public_selection(self) -> dict[str, Any]:
        selected = dict(self.selected_option) if self.selected_option else None
        if selected and self.reviewed_schema:
            selected.update({
                "openapi_version": self.reviewed_schema.schema_version,
                "operation_count": self.reviewed_schema.operation_count,
                "schema_sha256": self.reviewed_schema.source_sha256,
            })
        return {
            "kind": "project_openapi_artifact",
            "required": True,
            "overflow": self.overflow,
            "options": [dict(option) for option in self.options],
            "selected": selected,
        }

    def unavailable_reason(self) -> str:
        if self.overflow:
            return (
                "Saved JSON artifacts exceed the review limit. Remove unrelated "
                "artifacts before launching API negative testing."
            )
        if self.selection_invalid:
            return self.review_error or (
                "The selected OpenAPI artifact is unavailable or no longer passes review."
            )
        if not self.options:
            return "Save an OpenAPI JSON run artifact in this Project before testing the API."
        if not self.reviewed_schema:
            return "Choose one saved OpenAPI JSON artifact before reviewing the API test plan."
        return ""

    def command_plan(self) -> CommandPlan | None:
        if not self.reviewed_schema:
            return None
        return reviewed_schemathesis_command_plan(self.reviewed_schema)


def schemathesis_action_context(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    check_key: str,
    target: Mapping[str, str] | None,
    selection: Mapping[str, str] | None,
) -> SchemathesisActionContext | None:
    """Resolve one caller artifact ID only through the saved Project boundary."""
    requested_id = str((selection or {}).get("schema_artifact_id") or "").strip()
    if check_key != SCHEMATHESIS_CHECK_KEY:
        return None
    options, overflow = _artifact_options(conn, session_id, team_id, project_id)
    selected = next(
        (option for option in options if option["artifact_id"] == requested_id),
        None,
    ) if requested_id and not overflow else None
    reviewed = None
    review_error = ""
    if selected and target and str(target.get("type") or "") == "url":
        try:
            reviewed = review_project_openapi_artifact(
                session_id,
                project_id,
                requested_id,
                base_url=str(target.get("value") or ""),
                team_id=team_id,
            )
        except (SchemathesisArtifactError, SchemathesisSchemaError) as exc:
            review_error = str(exc)
    selection_invalid = bool(
        requested_id and (selected is None or reviewed is None)
    )
    return SchemathesisActionContext(
        options,
        selected,
        reviewed,
        bool(requested_id),
        selection_invalid,
        overflow,
        review_error,
    )


def _artifact_options(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
) -> tuple[tuple[dict[str, Any], ...], bool]:
    project_sql, project_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p",
    )
    run_sql, run_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="r",
    )
    rows = conn.execute(
        "SELECT a.id, a.run_id, a.display_name, a.workspace_path, a.byte_size, "
        "a.content_type, a.content_sha256, a.created FROM projects p "
        "JOIN project_links pl ON pl.project_id = p.id AND pl.entity_type = 'run' "
        "JOIN runs r ON r.id = pl.entity_id "
        "JOIN run_file_artifacts a ON a.run_id = r.id "
        "WHERE p.id = ? AND " + project_sql + " AND " + run_sql + " "  # nosec
        "AND a.byte_size > 0 AND a.byte_size <= ? "
        "AND (LOWER(COALESCE(a.content_type, '')) LIKE 'application/json%' "
        "OR LOWER(COALESCE(a.content_type, '')) LIKE 'application/openapi+json%' "
        "OR LOWER(COALESCE(a.content_type, '')) LIKE 'application/vnd.oai.openapi+json%' "
        "OR LOWER(COALESCE(a.display_name, '')) LIKE '%.json' "
        "OR LOWER(COALESCE(a.workspace_path, '')) LIKE '%.json') "
        "ORDER BY a.created DESC, a.id DESC LIMIT ?",
        (
            project_id,
            *project_params,
            *run_params,
            SCHEMATHESIS_SCHEMA_MAX_BYTES,
            SCHEMATHESIS_ARTIFACT_OPTION_LIMIT + 1,
        ),
    ).fetchall()
    candidates = [_public_option(row) for row in rows if _looks_like_json(row)]
    overflow = len(candidates) > SCHEMATHESIS_ARTIFACT_OPTION_LIMIT
    return tuple(candidates[:SCHEMATHESIS_ARTIFACT_OPTION_LIMIT]), overflow


def _looks_like_json(row: Any) -> bool:
    content_type = str(row["content_type"] or "").split(";", 1)[0].strip().lower()
    name = str(row["display_name"] or row["workspace_path"] or "").lower()
    return content_type in _JSON_CONTENT_TYPES or name.endswith(".json")


def _public_option(row: Any) -> dict[str, Any]:
    return {
        "artifact_id": str(row["id"] or ""),
        "run_id": str(row["run_id"] or ""),
        "name": str(row["display_name"] or "OpenAPI JSON"),
        "byte_size": int(row["byte_size"] or 0),
        "content_type": str(row["content_type"] or ""),
        "recorded_sha256": str(row["content_sha256"] or ""),
        "created": str(row["created"] or ""),
    }


__all__ = [
    "SCHEMATHESIS_ARTIFACT_OPTION_LIMIT",
    "SCHEMATHESIS_CHECK_KEY",
    "SchemathesisActionContext",
    "schemathesis_action_context",
]
