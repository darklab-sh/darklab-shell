# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI paths for Project-scoped one-off probes."""

from __future__ import annotations

from typing import Any

from services.api_v1.openapi_probe_examples import (
    catalog_response_example,
    plan_response_examples,
    run_response_example,
    stable_error_example,
    target_response_example,
)
from services.api_v1.openapi_probe_schemas import probe_component_schemas


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _media(schema: str, *, example: Any = None, examples: Any = None) -> dict[str, Any]:
    media: dict[str, Any] = {"schema": _ref(schema)}
    if example is not None:
        media["example"] = example
    if examples is not None:
        media["examples"] = examples
    return {"application/json": media}


def _response(
    description: str,
    schema: str,
    *,
    example: Any = None,
    examples: Any = None,
) -> dict[str, Any]:
    return {
        "description": description,
        "content": _media(schema, example=example, examples=examples),
    }


def _error(description: str = "Stable probe error") -> dict[str, Any]:
    return _response(description, "ApiError", example=stable_error_example())


def _request(schema: str, example: dict[str, Any]) -> dict[str, Any]:
    return {
        "required": True,
        "content": _media(schema, example=example),
    }


def probe_schemas() -> dict[str, Any]:
    return probe_component_schemas()


def probe_paths() -> dict[str, Any]:
    project = {
        "name": "project_id",
        "in": "path",
        "required": True,
        "description": "Project that owns the confirmed target.",
        "schema": {"type": "string"},
    }
    errors = {str(status): _error() for status in (400, 401, 403, 404, 409, 429)}
    return {
        "/projects/{project_id}/probes": {
            "get": {
                "summary": "List reviewed probes and profiles for a Project",
                "parameters": [
                    project,
                    {
                        "name": "service", "in": "query",
                        "description": "Optional discovered service name for recommendations.",
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "target_type", "in": "query",
                        "description": "Optional compatible target type.",
                        "schema": {"type": "string", "enum": ["domain", "ip", "url"]},
                    },
                ],
                "responses": {
                    "200": _response(
                        "Reviewed probe catalog",
                        "ProbeCatalogResponse",
                        example=catalog_response_example(),
                    ),
                    **errors,
                },
            },
        },
        "/projects/{project_id}/probes/plan": {
            "post": {
                "summary": "Preview one bounded Project probe",
                "parameters": [project],
                "requestBody": _request(
                    "ProbePlanRequest",
                    {"action_id": "ping", "entity_id": "ent_example"},
                ),
                "responses": {
                    "200": _response(
                        "Current launchable or unavailable probe plan",
                        "ProbePlanResponse",
                        examples=plan_response_examples(),
                    ),
                    **errors,
                },
            },
        },
        "/projects/{project_id}/probes/targets/resolve": {
            "post": {
                "summary": "Resolve one exact confirmed Project target for a probe",
                "parameters": [project],
                "requestBody": _request(
                    "ProbeTargetResolveRequest",
                    {"target_value": "example.test"},
                ),
                "responses": {
                    "200": _response(
                        "Resolved Project target",
                        "ProbeTargetResolveResponse",
                        example=target_response_example(),
                    ),
                    **errors,
                },
            },
        },
        "/projects/{project_id}/probes/run": {
            "post": {
                "summary": "Confirm and start one bounded Project probe",
                "parameters": [project],
                "requestBody": _request(
                    "ProbeRunRequest",
                    {
                        "action_id": "ping", "entity_id": "ent_example",
                        "confirmed": True, "plan_digest": "a" * 64,
                    },
                ),
                "responses": {
                    "202": _response(
                        "Probe run started",
                        "ProbeRunResponse",
                        example=run_response_example(),
                    ),
                    **errors,
                    "500": _error("Probe run could not start"),
                    "503": _error("Run broker unavailable"),
                },
            },
        },
    }


__all__ = ["probe_paths", "probe_schemas"]
