# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Principal and credential fragments for the API v1 contract."""

from __future__ import annotations

from collections.abc import Callable

from services.auth.contracts import PAT_SCOPES


def pat_security_scheme() -> dict[str, str]:
    return {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "dlp_v1_pat_…",
        "description": "A scoped darklab_shell personal access token.",
    }


def pat_scope_descriptions() -> dict[str, str]:
    descriptions = {
        "identity:read": "Read the current principal and PAT metadata.",
        "history:read": "Read run history, output, artifacts, and active-run state.",
        "runs:execute": "Start, wait for, summarize, or cancel command runs.",
        "projects:read": "Read projects, assessments, findings, and risk data.",
        "projects:write": "Create or change projects, assessments, findings, and risk data.",
        "atlas:read": "Read Atlas entities and findings.",
        "atlas:write": "Perform explicit Atlas lookups and mutations.",
        "automation:read": "Read schedules and watchers.",
        "automation:write": "Create or change schedules and watchers.",
        "notifications:read": "Read notification channels and delivery events.",
        "notifications:write": "Create, change, test, or remove notification channels.",
        "secrets:manage": "Manage secret metadata and values without reading stored values.",
        "teams:read": "Read teams and membership metadata.",
        "teams:write": "Create or change teams, membership, invites, and recovery state.",
    }
    return {scope: description for scope, description in descriptions.items() if scope in PAT_SCOPES}


def access_schemas(ref: Callable[[str], dict]) -> dict[str, dict]:
    credential_metadata = {
        "type": "object",
        "required": [
            "id", "public_prefix", "principal_id", "credential_type", "label",
            "verifier_root_version", "digest_algorithm", "created_by_credential_id",
            "created_at", "updated_at", "last_used_at", "expires_at", "revoked_at",
            "revocation_reason", "scopes",
        ],
        "properties": {
            "id": {"type": "string"},
            "public_prefix": {"type": "string"},
            "principal_id": {"type": "string"},
            "credential_type": {"type": "string", "enum": ["pat"]},
            "label": {"type": "string"},
            "verifier_root_version": {"type": "integer"},
            "digest_algorithm": {"type": "string"},
            "created_by_credential_id": {"type": "string", "nullable": True},
            "created_at": {"type": "string"},
            "updated_at": {"type": "string"},
            "last_used_at": {"type": "string", "nullable": True},
            "expires_at": {"type": "string", "nullable": True},
            "revoked_at": {"type": "string", "nullable": True},
            "revocation_reason": {"type": "string"},
            "scopes": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }
    return {
        "Whoami": {
            "type": "object",
            "required": ["principal_id", "personal_workspace_id", "credential", "last_seen_at"],
            "properties": {
                "principal_id": {"type": "string"},
                "personal_workspace_id": {"type": "string"},
                "credential": {
                    "type": "object",
                    "required": ["id", "type", "created_at", "last_used_at", "expires_at", "scopes"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string", "enum": ["pat"]},
                        "created_at": {"type": "string", "nullable": True},
                        "last_used_at": {"type": "string", "nullable": True},
                        "expires_at": {"type": "string", "nullable": True},
                        "scopes": {"type": "array", "items": {"type": "string"}},
                    },
                    "additionalProperties": False,
                },
                "last_seen_at": {
                    "type": "string",
                    "nullable": True,
                    "description": "Timestamp recorded for the current successful API authentication.",
                },
            },
            "additionalProperties": False,
        },
        "ApiPrincipal": {
            "type": "object",
            "required": ["id", "status", "personal_workspace_id"],
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string", "enum": ["active"]},
                "personal_workspace_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "ApiAuthentication": {
            "type": "object",
            "required": ["method", "credential_id", "credential_type", "scopes"],
            "properties": {
                "method": {"type": "string", "enum": ["pat_bearer"]},
                "credential_id": {"type": "string"},
                "credential_type": {"type": "string", "enum": ["pat"]},
                "scopes": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        "ApiPrincipalResponse": {
            "type": "object",
            "required": ["principal", "authentication"],
            "properties": {
                "principal": ref("ApiPrincipal"),
                "authentication": ref("ApiAuthentication"),
            },
            "additionalProperties": False,
        },
        "CredentialMetadata": credential_metadata,
        "CredentialList": {
            "type": "object",
            "required": ["credentials"],
            "properties": {"credentials": {"type": "array", "items": ref("CredentialMetadata")}},
            "additionalProperties": False,
        },
        "CredentialResponse": {
            "type": "object",
            "required": ["credential"],
            "properties": {"credential": ref("CredentialMetadata")},
            "additionalProperties": False,
        },
    }


def access_paths(
    ref: Callable[[str], dict],
    json_response: Callable[[str, dict], dict],
    error_response: Callable[[str], dict],
    common_errors: Callable[..., dict],
) -> dict[str, dict]:
    return {
        "/principal": {
            "get": {
                "responses": {
                    "200": json_response("Current principal and PAT context", ref("ApiPrincipalResponse")),
                    **common_errors(),
                },
            },
        },
        "/credentials": {
            "get": {
                "responses": {
                    "200": json_response("Current PAT metadata", ref("CredentialList")),
                    **common_errors(),
                },
            },
        },
        "/credentials/current/revoke": {
            "post": {
                "requestBody": {
                    "required": False,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"reason": {"type": "string", "maxLength": 256}},
                                "additionalProperties": False,
                            },
                        },
                    },
                },
                "responses": {
                    "200": json_response("Current PAT revoked", ref("CredentialResponse")),
                    "400": error_response("Invalid revocation request"),
                    **common_errors(),
                },
            },
        },
    }
