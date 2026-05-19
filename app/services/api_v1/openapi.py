"""OpenAPI contract for API v1."""

from __future__ import annotations

from copy import deepcopy

from config import APP_VERSION


def _ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def _json_response(description: str, schema: dict) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def _text_response(description: str) -> dict:
    return {
        "description": description,
        "content": {"text/plain": {"schema": {"type": "string"}}},
    }


def _error_response(description: str = "Error") -> dict:
    return _json_response(description, _ref("ApiError"))


def _common_errors(*, not_found: str | None = None) -> dict:
    responses = {
        "401": _error_response("Missing, invalid, or revoked token"),
        "429": _error_response("Rate limit exceeded"),
    }
    if not_found:
        responses["404"] = _error_response(not_found)
    return responses


def _path_param(name: str, description: str) -> dict:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string"},
    }


PAGE_PARAMS = [
    {
        "name": "limit",
        "in": "query",
        "schema": {"type": "integer", "default": 50, "minimum": 0, "maximum": 100},
    },
    {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0, "minimum": 0}},
]

RUN_ID_PARAM = _path_param("run_id", "Run id")
PROJECT_ID_PARAM = _path_param("project_id", "Project id")
ARTIFACT_ID_PARAM = _path_param("artifact_id", "Artifact id")


OPENAPI_SPEC: dict = {
    "openapi": "3.0.3",
    "info": {
        "title": "darklab_shell API",
        "version": APP_VERSION,
    },
    "servers": [{"url": "/api/v1"}],
    "components": {
        "securitySchemes": {
            "bearerToken": {"type": "http", "scheme": "bearer"},
        },
        "schemas": {
            "Health": {
                "type": "object",
                "required": ["ok", "version"],
                "properties": {
                    "ok": {"type": "boolean"},
                    "version": {"type": "string"},
                },
            },
            "ApiError": {
                "type": "object",
                "required": ["error"],
                "properties": {
                    "error": {
                        "type": "object",
                        "required": ["code", "message"],
                        "properties": {
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                        },
                    },
                },
            },
            "Label": {
                "type": "object",
                "required": ["id", "label"],
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                },
            },
            "Note": {
                "type": "object",
                "required": ["body"],
                "properties": {
                    "id": {"type": "string"},
                    "body": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                    "updated": {"type": "string", "nullable": True},
                },
            },
            "RunSummary": {
                "type": "object",
                "required": [
                    "id",
                    "command",
                    "started",
                    "finished",
                    "status",
                    "exit_code",
                    "run_kind",
                    "output_line_count",
                    "preview_truncated",
                    "full_output_available",
                    "full_output_truncated",
                    "artifact_count",
                    "finding_count",
                    "label_count",
                    "note_count",
                    "atlas_entity_count",
                    "atlas_finding_count",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "command": {"type": "string"},
                    "started": {"type": "string", "nullable": True},
                    "finished": {"type": "string", "nullable": True},
                    "status": {"type": "string"},
                    "exit_code": {"type": "integer", "nullable": True},
                    "run_kind": {"type": "string"},
                    "output_line_count": {"type": "integer"},
                    "preview_truncated": {"type": "boolean"},
                    "full_output_available": {"type": "boolean"},
                    "full_output_truncated": {"type": "boolean"},
                    "artifact_count": {"type": "integer"},
                    "finding_count": {"type": "integer"},
                    "label_count": {"type": "integer"},
                    "note_count": {"type": "integer"},
                    "atlas_entity_count": {"type": "integer"},
                    "atlas_finding_count": {"type": "integer"},
                },
            },
            "RunPage": {
                "type": "object",
                "required": ["runs", "total", "limit", "offset", "has_more"],
                "properties": {
                    "runs": {"type": "array", "items": _ref("RunSummary")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "RunDetail": {
                "type": "object",
                "required": ["run"],
                "properties": {
                    "run": {
                        "allOf": [
                            _ref("RunSummary"),
                            {
                                "type": "object",
                                "properties": {
                                    "artifacts": {"type": "array", "items": _ref("ArtifactSummary")},
                                },
                            },
                        ],
                    },
                },
            },
            "RunOutput": {
                "type": "object",
                "required": ["run_id", "preview", "full_output_available", "truncated", "lines"],
                "properties": {
                    "run_id": {"type": "string"},
                    "preview": {"type": "boolean"},
                    "full_output_available": {"type": "boolean"},
                    "truncated": {"type": "boolean"},
                    "lines": {"type": "array", "items": {"type": "string"}},
                },
            },
            "ArtifactSummary": {
                "type": "object",
                "required": [
                    "id",
                    "run_id",
                    "workspace_path",
                    "display_name",
                    "kind",
                    "byte_size",
                    "detected_by",
                    "content_type",
                    "preview_type",
                    "content_sha256",
                    "created",
                    "file_available",
                    "file_status",
                    "file_status_detail",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "workspace_path": {"type": "string"},
                    "display_name": {"type": "string"},
                    "kind": {"type": "string"},
                    "byte_size": {"type": "integer"},
                    "detected_by": {"type": "string"},
                    "content_type": {"type": "string", "nullable": True},
                    "preview_type": {"type": "string"},
                    "content_sha256": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                    "file_available": {"type": "boolean"},
                    "file_status": {"type": "string"},
                    "file_status_detail": {"type": "string"},
                },
            },
            "ArtifactList": {
                "type": "object",
                "required": ["artifacts"],
                "properties": {"artifacts": {"type": "array", "items": _ref("ArtifactSummary")}},
            },
            "Whoami": {
                "type": "object",
                "required": ["token_created", "last_seen_at"],
                "properties": {
                    "token_created": {"type": "string", "nullable": True},
                    "last_seen_at": {
                        "type": "string",
                        "nullable": True,
                        "description": "Timestamp recorded for the current successful API authentication.",
                    },
                },
            },
            "Project": {
                "type": "object",
                "required": ["id", "session_id", "name", "slug", "description", "status", "color", "created", "updated"],
                "properties": {
                    "id": {"type": "string"},
                    "session_id": {"type": "string"},
                    "name": {"type": "string"},
                    "slug": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string"},
                    "color": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                    "updated": {"type": "string", "nullable": True},
                    "counts": _ref("ProjectCounts"),
                    "finding_summary": {"type": "object", "additionalProperties": {"type": "integer"}},
                    "labels": {"type": "array", "items": _ref("Label")},
                    "note": {"nullable": True, "allOf": [_ref("Note")]},
                },
            },
            "ProjectCounts": {
                "type": "object",
                "properties": {
                    "runs": {"type": "integer"},
                    "entities": {"type": "integer"},
                    "targets": {"type": "integer"},
                    "pending_targets": {"type": "integer"},
                    "artifacts": {"type": "integer"},
                    "packages": {"type": "integer"},
                    "findings": {"type": "integer"},
                    "labels": {"type": "integer"},
                    "notes": {"type": "integer"},
                },
            },
            "ProjectPage": {
                "type": "object",
                "required": ["projects", "total", "limit", "offset", "has_more"],
                "properties": {
                    "projects": {"type": "array", "items": _ref("Project")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "ProjectDetail": {
                "type": "object",
                "required": ["project"],
                "properties": {"project": _ref("Project")},
            },
            "ProjectFindingPage": {
                "type": "object",
                "required": [
                    "findings",
                    "total",
                    "limit",
                    "offset",
                    "has_more",
                    "group_counts",
                    "collapsed_group_counts",
                    "group_order",
                ],
                "properties": {
                    "findings": {"type": "array", "items": _ref("ProjectFinding")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                    "group_counts": {"type": "object", "additionalProperties": {"type": "integer"}},
                    "collapsed_group_counts": {"type": "object", "additionalProperties": {"type": "integer"}},
                    "group_order": {"type": "array", "items": {"type": "string"}},
                },
            },
            "ProjectFinding": {
                "type": "object",
                "required": ["id", "run_id", "status", "review_state", "title", "raw_line", "target_ids", "run_command"],
                "properties": {
                    "id": {"type": "string"},
                    "session_id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "target_ids": {"type": "array", "items": {"type": "string"}},
                    "subject_key": {"type": "string"},
                    "scope": {"type": "string"},
                    "kind": {"type": "string"},
                    "title": {"type": "string"},
                    "raw_line": {"type": "string"},
                    "line_number": {"type": "integer", "nullable": True},
                    "severity": {"type": "string"},
                    "fingerprint": {"type": "string"},
                    "review_state": {"type": "string"},
                    "status": {"type": "string"},
                    "first_seen_at": {"type": "string", "nullable": True},
                    "last_seen_at": {"type": "string", "nullable": True},
                    "occurrence_count": {"type": "integer"},
                    "created": {"type": "string", "nullable": True},
                    "run_command": {"type": "string"},
                    "command_root": {"type": "string"},
                    "source_run_exists": {"type": "boolean"},
                    "orphan_source": {"type": "boolean"},
                },
            },
            "PackagePage": {
                "type": "object",
                "required": ["packages", "total", "limit", "offset", "has_more"],
                "properties": {
                    "packages": {"type": "array", "items": _ref("EvidencePackage")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "EvidencePackage": {
                "type": "object",
                "required": [
                    "id",
                    "session_id",
                    "project_id",
                    "name",
                    "description",
                    "redaction_mode",
                    "include_artifacts",
                    "manifest",
                    "status",
                    "created",
                    "updated",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "session_id": {"type": "string"},
                    "project_id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "redaction_mode": {"type": "string"},
                    "include_artifacts": {"type": "boolean"},
                    "manifest": {"type": "object", "additionalProperties": True},
                    "status": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                    "updated": {"type": "string", "nullable": True},
                    "labels": {"type": "array", "items": _ref("Label")},
                    "note": {"nullable": True, "allOf": [_ref("Note")]},
                },
            },
            "RunStarted": {
                "type": "object",
                "required": ["id", "status", "stream_url", "history_url"],
                "properties": {
                    "id": {"type": "string"},
                    "status": {"type": "string", "enum": ["running", "succeeded", "failed", "complete"]},
                    "stream_url": {"type": "string"},
                    "history_url": {"type": "string"},
                },
            },
            "RunStatus": {
                "type": "object",
                "required": ["run"],
                "properties": {"run": _ref("RunSummary")},
            },
            "RunStartRequest": {
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {"type": "string"},
                    "project_id": {"type": "string", "nullable": True},
                    "workspace_cwd": {"type": "string"},
                },
            },
            "RunStreamEvent": {
                "type": "object",
                "additionalProperties": True,
                "description": "Broker event object. Idle streams may emit type=heartbeat events.",
                "properties": {
                    "type": {"type": "string"},
                    "event_id": {"type": "string"},
                    "text": {"type": "string"},
                    "code": {"type": "integer"},
                },
            },
            "NdjsonStream": {
                "type": "string",
                "description": "Newline-delimited RunStreamEvent objects, including heartbeat rows during idle periods.",
            },
            "RunCancelResponse": {
                "type": "object",
                "required": ["killed", "id"],
                "properties": {
                    "killed": {"type": "boolean"},
                    "id": {"type": "string"},
                },
            },
        },
    },
    "security": [{"bearerToken": []}],
    "paths": {
        "/health": {
            "get": {
                "security": [],
                "responses": {
                    "200": _json_response("Liveness payload", _ref("Health")),
                    "429": _error_response("Rate limit exceeded"),
                },
            },
        },
        "/openapi.json": {
            "get": {
                "security": [],
                "responses": {
                    "200": _json_response("OpenAPI contract", {"type": "object", "additionalProperties": True}),
                    "429": _error_response("Rate limit exceeded"),
                },
            },
        },
        "/whoami": {
            "get": {
                "responses": {
                    "200": _json_response("Current API token metadata", _ref("Whoami")),
                    **_common_errors(),
                },
            },
        },
        "/history": {
            "get": {
                "parameters": [
                    *PAGE_PARAMS,
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                    {"name": "project_id", "in": "query", "schema": {"type": "string"}},
                    {
                        "name": "run_kind",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["external", "real", "builtin", "missing"]},
                    },
                    {"name": "exit_code", "in": "query", "schema": {"type": "string"}},
                    {"name": "since", "in": "query", "schema": {"type": "string", "format": "date-time"}},
                    {"name": "until", "in": "query", "schema": {"type": "string", "format": "date-time"}},
                ],
                "responses": {
                    "200": _json_response("Paginated run history", _ref("RunPage")),
                    **_common_errors(),
                },
            },
        },
        "/history/{run_id}": {
            "get": {
                "parameters": [RUN_ID_PARAM],
                "responses": {
                    "200": _json_response("Run detail", _ref("RunDetail")),
                    **_common_errors(not_found="Run not found"),
                },
            },
        },
        "/history/{run_id}/output": {
            "get": {
                "parameters": [
                    RUN_ID_PARAM,
                    {
                        "name": "format",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["text", "json"], "default": "text"},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Run output",
                        "content": {
                            "text/plain": {"schema": {"type": "string"}},
                            "application/json": {"schema": _ref("RunOutput")},
                        },
                    },
                    **_common_errors(not_found="Run not found"),
                },
            },
        },
        "/history/{run_id}/artifacts": {
            "get": {
                "parameters": [RUN_ID_PARAM],
                "responses": {
                    "200": _json_response("Run artifacts", _ref("ArtifactList")),
                    **_common_errors(not_found="Run not found"),
                },
            },
        },
        "/history/{run_id}/artifacts/{artifact_id}": {
            "get": {
                "parameters": [RUN_ID_PARAM, ARTIFACT_ID_PARAM],
                "responses": {
                    "200": {
                        "description": "Artifact download",
                        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
                    },
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "403": _error_response("Artifact unavailable"),
                    "404": _error_response("Run or artifact not found"),
                    "429": _error_response("Rate limit exceeded"),
                },
            },
        },
        "/projects": {
            "get": {
                "parameters": [
                    *PAGE_PARAMS,
                    {"name": "include_archived", "in": "query", "schema": {"type": "boolean", "default": False}},
                ],
                "responses": {
                    "200": _json_response("Projects", _ref("ProjectPage")),
                    **_common_errors(),
                },
            },
        },
        "/projects/{project_id}": {
            "get": {
                "parameters": [PROJECT_ID_PARAM],
                "responses": {
                    "200": _json_response("Project detail", _ref("ProjectDetail")),
                    **_common_errors(not_found="Project not found"),
                },
            },
        },
        "/projects/{project_id}/findings": {
            "get": {
                "parameters": [
                    PROJECT_ID_PARAM,
                    *PAGE_PARAMS,
                    {
                        "name": "run_id",
                        "in": "query",
                        "schema": {"type": "array", "items": {"type": "string"}},
                        "style": "form",
                        "explode": True,
                    },
                    {
                        "name": "target_id",
                        "in": "query",
                        "schema": {"type": "array", "items": {"type": "string"}},
                        "style": "form",
                        "explode": True,
                    },
                    {
                        "name": "review_state",
                        "in": "query",
                        "schema": {"type": "array", "items": {"type": "string"}},
                        "style": "form",
                        "explode": True,
                    },
                    {
                        "name": "scope",
                        "in": "query",
                        "schema": {"type": "array", "items": {"type": "string"}},
                        "style": "form",
                        "explode": True,
                    },
                    {
                        "name": "severity",
                        "in": "query",
                        "schema": {"type": "array", "items": {"type": "string"}},
                        "style": "form",
                        "explode": True,
                    },
                    {
                        "name": "command_root",
                        "in": "query",
                        "schema": {"type": "array", "items": {"type": "string"}},
                        "style": "form",
                        "explode": True,
                    },
                    {
                        "name": "orphan_filter",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["hide", "only", "all"], "default": "hide"},
                    },
                ],
                "responses": {
                    "200": _json_response("Project findings", _ref("ProjectFindingPage")),
                    **_common_errors(not_found="Project not found"),
                },
            },
        },
        "/projects/{project_id}/packages": {
            "get": {
                "parameters": [PROJECT_ID_PARAM, *PAGE_PARAMS],
                "responses": {
                    "200": _json_response("Evidence packages", _ref("PackagePage")),
                    **_common_errors(not_found="Project not found"),
                },
            },
        },
        "/runs": {
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("RunStartRequest")}},
                },
                "responses": {
                    "202": _json_response("Run started", _ref("RunStarted")),
                    "400": _error_response("Invalid or missing command"),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "409": _error_response("Unsupported run mode or archived project"),
                    "429": _error_response("Rate limit exceeded"),
                    "503": _error_response("Broker unavailable"),
                },
            },
        },
        "/runs/{run_id}": {
            "get": {
                "parameters": [RUN_ID_PARAM],
                "responses": {
                    "200": _json_response("Run status", _ref("RunStatus")),
                    **_common_errors(not_found="Run not found"),
                },
            },
        },
        "/runs/{run_id}/stream": {
            "get": {
                "parameters": [
                    RUN_ID_PARAM,
                    {
                        "name": "format",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["sse", "ndjson"], "default": "sse"},
                    },
                    {"name": "after", "in": "query", "schema": {"type": "string"}},
                    {"name": "Last-Event-ID", "in": "header", "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {
                        "description": "Run stream",
                        "content": {
                            "text/event-stream": {"schema": {"type": "string"}},
                            "application/x-ndjson": {"schema": _ref("NdjsonStream")},
                        },
                    },
                    **_common_errors(not_found="Run not found"),
                },
            },
        },
        "/runs/{run_id}/cancel": {
            "post": {
                "parameters": [RUN_ID_PARAM],
                "responses": {
                    "200": _json_response("Run cancelled", _ref("RunCancelResponse")),
                    **_common_errors(not_found="Run not found"),
                },
            },
        },
    },
}


def openapi_spec() -> dict:
    return deepcopy(OPENAPI_SPEC)
