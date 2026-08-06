# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI contract for API v1."""

from __future__ import annotations

from copy import deepcopy

from config import APP_VERSION
from services.api_v1 import openapi_assessments as assessments, openapi_manual_findings as manual
from services.api_v1.openapi_atlas_profile import atlas_profile_query_parameters, atlas_profile_schemas
from services.api_v1.openapi_cve_risk import cve_risk_schemas
from services.api_v1.openapi_findings import finding_schemas
from services.api_v1.openapi_finding_evidence import finding_evidence_paths, finding_evidence_schemas
from services.api_v1.openapi_verification_actions import verification_action_paths as action_paths, verification_action_schemas
from services.scheduler.models import CADENCE_PRESETS
from services.watchers.models import (
    DIFF_KINDS,
    WATCHER_ACK_STATES,
    WATCHER_FIRE_KINDS,
    WATCHER_OPTION_DEFAULTS,
    WATCHER_POLICY_SIGNAL_CLASSES,
    WATCHER_STATES,
)

CADENCE_PRESET_ENUM = list(CADENCE_PRESETS)
WATCHER_DIFF_KIND_ENUM = sorted(DIFF_KINDS)
WATCHER_FIRE_KIND_ENUM = sorted(WATCHER_FIRE_KINDS)
WATCHER_ACK_STATE_ENUM = sorted(WATCHER_ACK_STATES)
WATCHER_OPTION_KEYS = tuple(WATCHER_OPTION_DEFAULTS)
WATCHER_STATE_ENUM = sorted(WATCHER_STATES)


def _ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def _json_response(description: str, schema: dict) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def _text_response(description: str) -> dict:
    schema = {"type": "string"}
    return {"description": description, "content": {"text/plain": {"schema": schema}}}


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

STRUCTURED_OUTPUT_PARAMS = [
    {
        "name": "signal",
        "in": "query",
        "description": "Filter output lines by structured signal, such as findings.",
        "schema": {"type": "array", "items": {"type": "string"}},
        "style": "form",
        "explode": True,
    },
    {
        "name": "kind",
        "in": "query",
        "description": "Filter output lines by typed kind.",
        "schema": {"type": "array", "items": {"type": "string", "enum": ["info", "notice", "warn", "error"]}},
        "style": "form",
        "explode": True,
    },
    {
        "name": "not_kind",
        "in": "query",
        "description": "Exclude output lines with this typed kind.",
        "schema": {"type": "array", "items": {"type": "string", "enum": ["info", "notice", "warn", "error"]}},
        "style": "form",
        "explode": True,
    },
    {
        "name": "role",
        "in": "query",
        "description": "Filter output lines by structural role.",
        "schema": {"type": "array", "items": {"type": "string"}},
        "style": "form",
        "explode": True,
    },
    {
        "name": "entity",
        "in": "query",
        "description": "Filter output lines by entity value or type:value.",
        "schema": {"type": "array", "items": {"type": "string"}},
        "style": "form",
        "explode": True,
    },
    {
        "name": "entity_type",
        "in": "query",
        "description": "Filter output lines by captured entity type, such as domain, ip, url, hash, or cve.",
        "schema": {"type": "array", "items": {"type": "string"}},
        "style": "form",
        "explode": True,
    },
]

RUN_ID_PARAM = _path_param("run_id", "Run id")
PROJECT_ID_PARAM = _path_param("project_id", "Project id")
ARTIFACT_ID_PARAM = _path_param("artifact_id", "Artifact id")
NOTIFICATION_CHANNEL_ID_PARAM = _path_param("channel_id", "Notification channel id")
SCHEDULE_ID_PARAM = _path_param("schedule_id", "Schedule id")
WATCHER_ID_PARAM = _path_param("watcher_id", "Watcher id")
TEAM_ID_PARAM = _path_param("team_id", "Team id")
TEAM_MEMBER_ID_PARAM = _path_param("member_id", "Team member id")
TEAM_INVITE_ID_PARAM = _path_param("invite_id", "Team invite id")


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
            "TeamMember": {
                "type": "object",
                "required": ["id", "team_id", "role", "capabilities", "display_name", "status"],
                "properties": {
                    "id": {"type": "string"},
                    "team_id": {"type": "string"},
                    "role": {"type": "string", "enum": ["owner", "admin", "operator", "viewer"]},
                    "capabilities": {"type": "array", "items": {"type": "string"}},
                    "display_name": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "removed"]},
                    "joined_at": {"type": "string"},
                    "last_seen_at": {"type": "string"},
                    "removed_at": {"type": "string"},
                    "is_current": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            "TeamMembership": {
                "type": "object",
                "required": ["id", "role", "capabilities", "display_name", "joined_at"],
                "properties": {
                    "id": {"type": "string"},
                    "role": {"type": "string", "enum": ["owner", "admin", "operator", "viewer"]},
                    "capabilities": {"type": "array", "items": {"type": "string"}},
                    "display_name": {"type": "string"},
                    "joined_at": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "Team": {
                "type": "object",
                "required": ["id", "name", "slug", "status", "member"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "slug": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "archived", "deleted"]},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                    "archived_at": {"type": "string"},
                    "deleted_at": {"type": "string"},
                    "member": _ref("TeamMembership"),
                },
                "additionalProperties": False,
            },
            "TeamInvite": {
                "type": "object",
                "required": ["id", "team_id", "role", "label"],
                "properties": {
                    "id": {"type": "string"},
                    "team_id": {"type": "string"},
                    "role": {"type": "string", "enum": ["owner", "admin", "operator", "viewer"]},
                    "label": {"type": "string"},
                    "created_by_member_id": {"type": "string"},
                    "expires_at": {"type": "string"},
                    "max_uses": {"type": "integer"},
                    "use_count": {"type": "integer"},
                    "revoked_at": {"type": "string"},
                    "created_at": {"type": "string"},
                    "code": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "TeamRecoveryCode": {
                "type": "object",
                "required": ["id", "team_id"],
                "properties": {
                    "id": {"type": "string"},
                    "team_id": {"type": "string"},
                    "created_by_member_id": {"type": "string"},
                    "created_at": {"type": "string"},
                    "rotated_at": {"type": "string"},
                    "revoked_at": {"type": "string"},
                    "used_at": {"type": "string"},
                    "code": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "TeamList": {
                "type": "object",
                "required": ["teams"],
                "properties": {"teams": {"type": "array", "items": _ref("Team")}},
                "additionalProperties": False,
            },
            "TeamDetail": {
                "type": "object",
                "required": ["team", "members", "invites", "recovery_codes"],
                "properties": {
                    "team": _ref("Team"),
                    "members": {"type": "array", "items": _ref("TeamMember")},
                    "invites": {"type": "array", "items": _ref("TeamInvite")},
                    "recovery_codes": {"type": "array", "items": _ref("TeamRecoveryCode")},
                },
                "additionalProperties": False,
            },
            "TeamCreateRequest": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "slug": {"type": "string"},
                    "display_name": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "TeamCreateResponse": {
                "type": "object",
                "required": ["team", "recovery_code"],
                "properties": {
                    "team": _ref("Team"),
                    "recovery_code": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "TeamUpdateRequest": {
                "type": "object",
                "properties": {"status": {"type": "string", "enum": ["active", "archived"]}},
                "additionalProperties": False,
            },
            "TeamInviteCreateRequest": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["owner", "admin", "operator", "viewer"]},
                    "label": {"type": "string"},
                    "expires_at": {"type": "string"},
                    "max_uses": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            "TeamInviteResponse": {
                "type": "object",
                "required": ["invite"],
                "properties": {"invite": _ref("TeamInvite")},
                "additionalProperties": False,
            },
            "TeamJoinRequest": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "display_name": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "TeamMemberUpdateRequest": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["owner", "admin", "operator", "viewer"]},
                    "display_name": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "TeamMemberResponse": {
                "type": "object",
                "required": ["member"],
                "properties": {"member": _ref("TeamMember")},
                "additionalProperties": False,
            },
            "TeamRecoveryRotateResponse": {
                "type": "object",
                "required": ["recovery_code", "recovery"],
                "properties": {
                    "recovery_code": {"type": "string"},
                    "recovery": _ref("TeamRecoveryCode"),
                },
                "additionalProperties": False,
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
                    "scheduled",
                    "schedule_id",
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
                    "scheduled": {"type": "boolean"},
                    "schedule_id": {"type": "string"},
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
            "HistorySearchMatch": {
                "type": "object",
                "required": [
                    "run_id",
                    "command",
                    "started",
                    "finished",
                    "line_number",
                    "line",
                    "context_before",
                    "context_after",
                ],
                "properties": {
                    "run_id": {"type": "string"},
                    "command": {"type": "string"},
                    "started": {"type": "string", "nullable": True},
                    "finished": {"type": "string", "nullable": True},
                    "line_number": {"type": "integer", "minimum": 1},
                    "line": {"type": "string"},
                    "kind": {"type": "string", "enum": ["info", "notice", "warn", "error"]},
                    "role": {"type": "string"},
                    "signals": {"type": "array", "items": {"type": "string"}},
                    "entities": {"type": "array", "items": _ref("RunStreamEntity")},
                    "context_before": {"type": "array", "items": {"type": "string"}},
                    "context_after": {"type": "array", "items": {"type": "string"}},
                },
            },
            "HistorySearchPage": {
                "type": "object",
                "required": ["matches", "total", "limit", "offset", "has_more", "query", "context"],
                "properties": {
                    "matches": {"type": "array", "items": _ref("HistorySearchMatch")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                    "query": {"type": "string"},
                    "context": {"type": "integer"},
                    "filters": {"type": "object", "additionalProperties": True},
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
                "required": ["run_id", "preview", "full_output_available", "truncated", "line_count", "lines"],
                "properties": {
                    "run_id": {"type": "string"},
                    "preview": {"type": "boolean"},
                    "full_output_available": {"type": "boolean"},
                    "truncated": {"type": "boolean"},
                    "line_count": {"type": "integer"},
                    "returned": {"type": "integer"},
                    "range": {
                        "type": "object",
                        "required": ["start", "end", "returned"],
                        "properties": {
                            "start": {"type": "integer"},
                            "end": {"type": "integer"},
                            "returned": {"type": "integer"},
                        },
                    },
                    "lines": {"type": "array", "items": {"type": "string"}},
                    "entries": {"type": "array", "items": _ref("RunStreamEvent")},
                    "filters": {"type": "object", "additionalProperties": True},
                },
            },
            "AtlasSummary": {
                "type": "object",
                "required": ["total", "counts", "findings"],
                "properties": {
                    "total": {"type": "integer"},
                    "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
                    "findings": {"type": "integer"},
                },
            },
            "AtlasSourceRun": {
                "type": "object",
                "required": ["id", "run_id", "command", "entity_count", "finding_count"],
                "properties": {
                    "id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "command": {"type": "string"},
                    "started": {"type": "string", "nullable": True},
                    "finished": {"type": "string", "nullable": True},
                    "exit_code": {"type": "integer", "nullable": True},
                    "entity_count": {"type": "integer"},
                    "finding_count": {"type": "integer"},
                },
            },
            "AtlasRunList": {
                "type": "object",
                "required": ["runs", "limit"],
                "properties": {
                    "runs": {"type": "array", "items": _ref("AtlasSourceRun")},
                    "limit": {"type": "integer"},
                },
            },
            "AtlasEntity": {
                "type": "object",
                "required": ["id", "type", "canonical_value", "occurrence_count", "run_count"],
                "properties": {
                    "id": {"type": "string"},
                    "session_id": {"type": "string"},
                    "type": {"type": "string"},
                    "canonical_value": {"type": "string"},
                    "host_entity_id": {"type": "string", "nullable": True},
                    "attributes": {"type": "object", "additionalProperties": True},
                    "first_seen_at": {"type": "string", "nullable": True},
                    "last_seen_at": {"type": "string", "nullable": True},
                    "occurrence_count": {"type": "integer"},
                    "run_count": {"type": "integer"},
                    "suppressed": {"type": "boolean"},
                    "suppressed_reason": {"type": "string"},
                    "suppressed_at": {"type": "string"},
                    "labels": {"type": "array", "items": _ref("Label")},
                    "project_link_count": {"type": "integer"},
                    "project_links": {"type": "array", "items": _ref("ProjectLink")},
                    "note": {"nullable": True, "allOf": [_ref("Note")]},
                },
            },
            "AtlasEntityPage": {
                "type": "object",
                "required": ["entities", "total", "limit", "offset", "has_more", "total_exact"],
                "properties": {
                    "entities": {"type": "array", "items": _ref("AtlasEntity")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                    "total_exact": {"type": "boolean"},
                },
            },
            **cve_risk_schemas(),
            **finding_schemas(),
            "AtlasFindingPage": {
                "type": "object",
                "required": [
                    "findings",
                    "total",
                    "limit",
                    "offset",
                    "has_more",
                    "total_exact",
                    "counts",
                    "counts_exact",
                ],
                "properties": {
                    "findings": {"type": "array", "items": _ref("AtlasFinding")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                    "total_exact": {"type": "boolean"},
                    "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
                    "counts_exact": {"type": "boolean"},
                },
            },
            **atlas_profile_schemas(),
            **assessments.assessment_schemas(),
            **(finding_evidence_schemas() | manual.manual_finding_schemas() | verification_action_schemas()),
            "AtlasFindingDetail": {
                "type": "object",
                "required": ["finding", "occurrences", "detail_limits"],
                "properties": {
                    "finding": _ref("AtlasFinding"),
                    "occurrences": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    "detail_limits": {"type": "object", "additionalProperties": True},
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
            "ProjectRun": {
                "type": "object",
                "required": ["id", "command", "started", "finished", "exit_code", "output_line_count", "created", "link_source"],
                "properties": {
                    "id": {"type": "string"},
                    "command": {"type": "string"},
                    "started": {"type": "string", "nullable": True},
                    "finished": {"type": "string", "nullable": True},
                    "exit_code": {"type": "integer", "nullable": True},
                    "output_line_count": {"type": "integer"},
                    "created": {"type": "string", "nullable": True},
                    "link_source": {"type": "string"},
                    "finding_count": {"type": "integer"},
                    "artifact_count": {"type": "integer"},
                    "labels": {"type": "array", "items": _ref("Label")},
                    "note": {"nullable": True, "allOf": [_ref("Note")]},
                    "full_output_available": {"type": "boolean"},
                    "full_output_truncated": {"type": "boolean"},
                    "full_output_byte_size": {"type": "integer"},
                    "full_output_line_count": {"type": "integer"},
                },
            },
            "ProjectRunPage": {
                "type": "object",
                "required": ["runs", "total", "limit", "offset", "has_more"],
                "properties": {
                    "runs": {"type": "array", "items": _ref("ProjectRun")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "ProjectLink": {
                "type": "object",
                "required": ["id", "project_id", "entity_type", "entity_id", "source", "created"],
                "properties": {
                    "id": {"type": "string"},
                    "project_id": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "entity_id": {"type": "string"},
                    "source": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                },
            },
            "ProjectRunLinkResponse": {
                "type": "object",
                "required": ["ok", "link"],
                "properties": {
                    "ok": {"type": "boolean"},
                    "link": _ref("ProjectLink"),
                },
            },
            "OkResponse": {
                "type": "object",
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
            },
            "ProjectEntity": {
                "type": "object",
                "required": ["id", "type", "value", "canonical_value", "occurrence_count", "run_count"],
                "properties": {
                    "id": {"type": "string"},
                    "project_id": {"type": "string"},
                    "type": {"type": "string"},
                    "value": {"type": "string"},
                    "canonical_value": {"type": "string"},
                    "source_run_id": {"type": "string"},
                    "confidence": {"type": "number"},
                    "review_state": {"type": "string"},
                    "status": {"type": "string"},
                    "source": {"type": "string"},
                    "source_detail": {"type": "object", "additionalProperties": True},
                    "seen_count": {"type": "integer"},
                    "occurrence_count": {"type": "integer"},
                    "suppressed": {"type": "boolean"},
                    "suppressed_reason": {"type": "string"},
                    "suppressed_at": {"type": "string"},
                    "run_count": {"type": "integer"},
                    "intel_provider_count": {"type": "integer"},
                    "intel_providers": {"type": "array", "items": {"type": "string"}},
                    "intel_last_refreshed": {"type": "string"},
                    "last_seen": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                    "updated": {"type": "string", "nullable": True},
                    "labels": {"type": "array", "items": _ref("Label")},
                    "note": {"nullable": True, "allOf": [_ref("Note")]},
                },
            },
            "ProjectEntityPage": {
                "type": "object",
                "required": ["entities", "total", "limit", "offset", "has_more", "counts_by_type"],
                "properties": {
                    "entities": {"type": "array", "items": _ref("ProjectEntity")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                    "counts_by_type": {"type": "object", "additionalProperties": {"type": "integer"}},
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
            "Schedule": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "owner_kind",
                    "owner_id",
                    "team_id",
                    "kind",
                    "command_text",
                    "cron_expr",
                    "timezone",
                    "enabled",
                    "next_run_at",
                    "last_run_at",
                    "last_run_id",
                    "overlap_policy",
                    "consecutive_failures",
                    "label",
                    "paused_reason",
                    "last_error",
                    "created",
                    "updated",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "owner_kind": {"type": "string", "enum": ["user", "watcher"]},
                    "owner_id": {"type": "string"},
                    "team_id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["command"]},
                    "command_text": {"type": "string"},
                    "cron_expr": {"type": "string"},
                    "cadence_preset": {"type": "string", "nullable": True, "enum": CADENCE_PRESET_ENUM},
                    "timezone": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "next_run_at": {"type": "string", "nullable": True},
                    "last_run_at": {"type": "string"},
                    "last_run_id": {"type": "string"},
                    "overlap_policy": {"type": "string", "enum": ["skip"]},
                    "consecutive_failures": {"type": "integer"},
                    "label": {"type": "string"},
                    "paused_reason": {"type": "string"},
                    "last_error": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                    "updated": {"type": "string", "nullable": True},
                },
            },
            "SchedulePage": {
                "type": "object",
                "required": ["schedules", "total", "limit", "offset", "has_more"],
                "properties": {
                    "schedules": {"type": "array", "items": _ref("Schedule")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "ScheduleResponse": {
                "type": "object",
                "required": ["schedule"],
                "properties": {
                    "schedule": _ref("Schedule"),
                    "next_fires": {"type": "array", "items": {"type": "string"}},
                },
            },
            "ScheduleCreateRequest": {
                "type": "object",
                "required": ["command"],
                "properties": {
                    "command": {"type": "string"},
                    "command_text": {"type": "string"},
                    "cron_expr": {"type": "string"},
                    "cadence_preset": {"type": "string", "enum": CADENCE_PRESET_ENUM},
                    "timezone": {"type": "string"},
                    "label": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "workspace_cwd": {"type": "string"},
                },
            },
            "ScheduleUpdateRequest": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "command_text": {"type": "string"},
                    "cron_expr": {"type": "string"},
                    "cadence_preset": {"type": "string", "enum": CADENCE_PRESET_ENUM},
                    "timezone": {"type": "string"},
                    "label": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "paused_reason": {"type": "string"},
                    "workspace_cwd": {"type": "string"},
                },
            },
            "ScheduleFire": {
                "type": "object",
                "required": [
                    "id",
                    "schedule_id",
                    "owner_kind",
                    "owner_id",
                    "team_id",
                    "fired_at",
                    "run_id",
                    "status",
                    "reason",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "schedule_id": {"type": "string"},
                    "owner_kind": {"type": "string"},
                    "owner_id": {"type": "string"},
                    "team_id": {"type": "string"},
                    "fired_at": {"type": "string", "nullable": True},
                    "run_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["skipped_overlap", "skipped_revoked", "fired", "fire_failed"],
                    },
                    "reason": {"type": "string"},
                },
            },
            "ScheduleFirePage": {
                "type": "object",
                "required": ["fires", "total", "limit", "offset", "has_more"],
                "properties": {
                    "fires": {"type": "array", "items": _ref("ScheduleFire")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "ScheduleRunNowResponse": {
                "type": "object",
                "required": ["status", "fired_at", "schedule"],
                "properties": {
                    "status": {"type": "string"},
                    "fired_at": {"type": "string"},
                    "schedule": _ref("Schedule"),
                },
            },
            "WatcherOptions": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    key: {"type": "boolean"}
                    for key in WATCHER_OPTION_KEYS
                },
            },
            "WatcherPolicy": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ignore_line_patterns": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 120},
                        "maxItems": 20,
                    },
                    "alert_after_repeated_changes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "alert_signal_classes": {
                        "type": "array",
                        "items": {"type": "string", "enum": sorted(WATCHER_POLICY_SIGNAL_CLASSES)},
                        "uniqueItems": True,
                    },
                },
            },
            "WatcherDiffSummary": {
                "type": "object",
                "additionalProperties": True,
                "description": "Bounded classifier summary for added, removed, and changed signals.",
            },
            "Watcher": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "team_id",
                    "project_id",
                    "label",
                    "command_text",
                    "schedule_id",
                    "baseline_run_id",
                    "last_run_id",
                    "last_diff_summary",
                    "state",
                    "state_reason",
                    "last_error",
                    "options",
                    "policy",
                    "consecutive_no_change",
                    "consecutive_changed",
                    "consecutive_failures",
                    "created",
                    "updated",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "team_id": {"type": "string"},
                    "project_id": {"type": "string"},
                    "label": {"type": "string"},
                    "command_text": {"type": "string"},
                    "schedule_id": {"type": "string"},
                    "baseline_run_id": {"type": "string"},
                    "last_run_id": {"type": "string"},
                    "last_diff_summary": _ref("WatcherDiffSummary"),
                    "state": {"type": "string", "enum": WATCHER_STATE_ENUM},
                    "state_reason": {"type": "string"},
                    "last_error": {"type": "string"},
                    "options": _ref("WatcherOptions"),
                    "policy": _ref("WatcherPolicy"),
                    "consecutive_no_change": {"type": "integer"},
                    "consecutive_changed": {"type": "integer"},
                    "consecutive_failures": {"type": "integer"},
                    "created": {"type": "string", "nullable": True},
                    "updated": {"type": "string", "nullable": True},
                    "schedule": _ref("Schedule"),
                },
            },
            "WatcherPage": {
                "type": "object",
                "required": ["watchers", "total", "limit", "offset", "has_more"],
                "properties": {
                    "watchers": {"type": "array", "items": _ref("Watcher")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "WatcherResponse": {
                "type": "object",
                "required": ["watcher"],
                "properties": {"watcher": _ref("Watcher")},
            },
            "WatcherCreateRequest": {
                "type": "object",
                "properties": {
                    "baseline_mode": {"type": "string", "enum": ["existing_run", "first_run"]},
                    "baseline_run_id": {"type": "string"},
                    "command": {"type": "string"},
                    "command_text": {"type": "string"},
                    "cron_expr": {"type": "string"},
                    "cadence_preset": {"type": "string", "enum": CADENCE_PRESET_ENUM},
                    "timezone": {"type": "string"},
                    "timezone_name": {"type": "string"},
                    "label": {"type": "string"},
                    "project_id": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "options": _ref("WatcherOptions"),
                    "policy": _ref("WatcherPolicy"),
                    "workspace_cwd": {"type": "string"},
                },
            },
            "WatcherUpdateRequest": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "command_text": {"type": "string"},
                    "cron_expr": {"type": "string"},
                    "cadence_preset": {"type": "string", "enum": CADENCE_PRESET_ENUM},
                    "timezone": {"type": "string"},
                    "timezone_name": {"type": "string"},
                    "label": {"type": "string"},
                    "project_id": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "state": {"type": "string", "enum": ["ok", "active", "resume", "paused"]},
                    "pause": {"type": "boolean"},
                    "resume": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "options": _ref("WatcherOptions"),
                    "policy": _ref("WatcherPolicy"),
                    "workspace_cwd": {"type": "string"},
                },
            },
            "WatcherFire": {
                "type": "object",
                "required": [
                    "id",
                    "team_id",
                    "watcher_id",
                    "baseline_run_id",
                    "run_id",
                    "diff_summary",
                    "diff_kind",
                    "truncated",
                    "notification_event_ids",
                    "state_at_fire",
                    "state_reason",
                    "fire_kind",
                    "ack_state",
                    "ack_note",
                    "ack_by",
                    "ack_at",
                    "created",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "team_id": {"type": "string"},
                    "watcher_id": {"type": "string"},
                    "baseline_run_id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "diff_summary": _ref("WatcherDiffSummary"),
                    "diff_kind": {"type": "string", "enum": WATCHER_DIFF_KIND_ENUM},
                    "truncated": {"type": "boolean"},
                    "notification_event_ids": {"type": "array", "items": {"type": "string"}},
                    "state_at_fire": {"type": "string", "enum": WATCHER_STATE_ENUM},
                    "state_reason": {"type": "string"},
                    "fire_kind": {"type": "string", "enum": WATCHER_FIRE_KIND_ENUM},
                    "ack_state": {"type": "string", "enum": WATCHER_ACK_STATE_ENUM},
                    "ack_note": {"type": "string"},
                    "ack_by": {"type": "string"},
                    "ack_at": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                },
            },
            "WatcherFirePage": {
                "type": "object",
                "required": ["fires", "total", "limit", "offset", "has_more"],
                "properties": {
                    "fires": {"type": "array", "items": _ref("WatcherFire")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "WatcherRunNowResponse": {
                "type": "object",
                "required": ["status", "fired_at", "watcher"],
                "properties": {
                    "status": {"type": "string"},
                    "fired_at": {"type": "string"},
                    "watcher": _ref("Watcher"),
                },
            },
            "WatcherAcceptBaselineRequest": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                },
            },
            "NotificationSecretField": {
                "type": "object",
                "required": ["name", "configured"],
                "properties": {
                    "name": {"type": "string"},
                    "configured": {"type": "boolean"},
                },
            },
            "NotificationChannelKindField": {
                "type": "object",
                "required": ["name", "label"],
                "properties": {
                    "name": {"type": "string"},
                    "label": {"type": "string"},
                    "optional": {"type": "boolean"},
                    "help": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "NotificationChannelKind": {
                "type": "object",
                "required": ["kind", "label", "secret_fields", "config_fields"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["webhook", "slack", "discord", "telegram", "pushover", "email"],
                    },
                    "label": {"type": "string"},
                    "secret_fields": {"type": "array", "items": _ref("NotificationChannelKindField")},
                    "config_fields": {"type": "array", "items": _ref("NotificationChannelKindField")},
                },
                "additionalProperties": False,
            },
            "NotificationTriggerOption": {
                "type": "object",
                "required": ["value", "label"],
                "properties": {
                    "value": {"type": "string"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "NotificationChannelKindList": {
                "type": "object",
                "required": ["kinds", "triggers"],
                "properties": {
                    "kinds": {"type": "array", "items": _ref("NotificationChannelKind")},
                    "triggers": {"type": "array", "items": _ref("NotificationTriggerOption")},
                },
            },
            "NotificationChannel": {
                "type": "object",
                "required": ["id", "kind", "label", "config", "triggers", "secret_fields", "muted", "created", "updated"],
                "properties": {
                    "id": {"type": "string"},
                    "team_id": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["webhook", "slack", "discord", "telegram", "pushover", "email"],
                    },
                    "label": {"type": "string"},
                    "config": {"type": "object", "additionalProperties": True},
                    "triggers": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "run_complete",
                                "pty_session_ended",
                                "watcher_changed",
                                "watcher_error",
                                "watcher_recovered",
                                "scheduled_run_failed",
                            ],
                        },
                    },
                    "secret_fields": {"type": "array", "items": _ref("NotificationSecretField")},
                    "muted": {"type": "boolean"},
                    "created": {"type": "string", "nullable": True},
                    "updated": {"type": "string", "nullable": True},
                },
            },
            "NotificationChannelList": {
                "type": "object",
                "required": ["channels"],
                "properties": {"channels": {"type": "array", "items": _ref("NotificationChannel")}},
            },
            "NotificationChannelCreateRequest": {
                "type": "object",
                "required": ["kind"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["webhook", "slack", "discord", "telegram", "pushover", "email"],
                    },
                    "label": {"type": "string"},
                    "config": {"type": "object", "additionalProperties": True},
                    "triggers": {"type": "array", "items": {"type": "string"}},
                    "muted": {"type": "boolean"},
                    "secret_values": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "writeOnly": True,
                    },
                },
            },
            "NotificationChannelUpdateRequest": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["webhook", "slack", "discord", "telegram", "pushover", "email"],
                    },
                    "label": {"type": "string"},
                    "config": {"type": "object", "additionalProperties": True},
                    "triggers": {"type": "array", "items": {"type": "string"}},
                    "muted": {"type": "boolean"},
                    "secret_values": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "writeOnly": True,
                    },
                },
            },
            "NotificationChannelResponse": {
                "type": "object",
                "required": ["channel"],
                "properties": {"channel": _ref("NotificationChannel")},
            },
            "NotificationTestResponse": {
                "type": "object",
                "required": ["queued", "event_ids", "events"],
                "properties": {
                    "queued": {"type": "integer"},
                    "event_ids": {"type": "array", "items": {"type": "string"}},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["event_id", "status", "last_error"],
                            "properties": {
                                "event_id": {"type": "string"},
                                "status": {"type": "string", "enum": ["pending", "retry_wait", "sent", "dead"]},
                                "last_error": {"type": "string"},
                            },
                        },
                    },
                },
            },
            "NotificationEvent": {
                "type": "object",
                "required": ["id", "channel_id", "trigger", "payload", "status", "attempts", "created"],
                "properties": {
                    "id": {"type": "string"},
                    "team_id": {"type": "string"},
                    "channel_id": {"type": "string"},
                    "trigger": {"type": "string"},
                    "payload": {"type": "object", "additionalProperties": True},
                    "status": {"type": "string", "enum": ["pending", "retry_wait", "sent", "dead"]},
                    "attempts": {"type": "integer"},
                    "next_attempt_at": {"type": "string"},
                    "last_attempt_at": {"type": "string"},
                    "last_error": {"type": "string"},
                    "run_id": {"type": "string"},
                    "created": {"type": "string", "nullable": True},
                    "dead_at": {"type": "string"},
                },
            },
            "NotificationEventPage": {
                "type": "object",
                "required": ["events", "total", "limit", "offset", "has_more"],
                "properties": {
                    "events": {"type": "array", "items": _ref("NotificationEvent")},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "has_more": {"type": "boolean"},
                },
            },
            "DeleteResponse": {
                "type": "object",
                "required": ["removed"],
                "properties": {"removed": {"type": "boolean"}},
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
            "AIAssist": {
                "type": "object",
                "required": ["id", "run_id", "variant", "status", "payload", "progress"],
                "properties": {
                    "id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "variant": {"type": "string", "enum": ["summary", "next_commands"]},
                    "status": {"type": "string", "enum": ["queued", "in_progress", "completed", "failed"]},
                    "payload": {"type": "object", "additionalProperties": True},
                    "progress": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "phase": {"type": "string"},
                            "elapsed_ms": {"type": "integer"},
                            "output_chars_seen": {"type": "integer"},
                            "tokens_seen": {"type": "integer"},
                            "input_tokens_seen": {"type": "integer"},
                            "output_tokens_seen": {"type": "integer"},
                        },
                    },
                    "error_code": {"type": "string"},
                    "error_message": {"type": "string"},
                    "model": {"type": "string"},
                    "prompt_version": {"type": "string"},
                    "prompt_version_source": {"type": "string", "enum": ["canonical", "override"]},
                    "payload_schema_version": {"type": "string"},
                    "input_chars": {"type": "integer"},
                    "output_chars": {"type": "integer"},
                    "estimated_input_tokens": {"type": "integer"},
                    "duration_ms": {"type": "integer"},
                    "redacted_bytes": {"type": "integer"},
                    "pre_redaction_bytes": {"type": "integer"},
                    "active_project_id": {"type": "string"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"},
                },
            },
            "AIAssistList": {
                "type": "object",
                "required": ["assists"],
                "properties": {"assists": {"type": "array", "items": _ref("AIAssist")}},
            },
            "AIAssistResponse": {
                "type": "object",
                "required": ["assist"],
                "properties": {"assist": _ref("AIAssist")},
            },
            "AIAssistRequest": {
                "type": "object",
                "properties": {"force": {"type": "boolean", "default": False}},
            },
            "ActiveRunList": {
                "type": "object",
                "required": ["runs", "total"],
                "properties": {
                    "runs": {"type": "array", "items": _ref("RunSummary")},
                    "total": {"type": "integer"},
                },
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
                "description": (
                    "Broker event object. Streams start with a schema row "
                    "({type=schema,event=schema,v=1,kind=line_event}); output and notice rows use the "
                    "versioned line-event payload while preserving type and legacy cls for older clients. "
                    "High-volume live streams may emit output_batch rows with a lines array of line events. "
                    "Idle streams may emit type=heartbeat events."
                ),
                "properties": {
                    "type": {"type": "string"},
                    "event": {"type": "string"},
                    "v": {"type": "integer"},
                    "kind": {"type": "string"},
                    "role": {"type": "string"},
                    "cls": {"type": "string"},
                    "event_id": {"type": "string"},
                    "text": {"type": "string"},
                    "lines": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "tsC": {"type": "string"},
                    "tsE": {"type": "string"},
                    "code": {"type": "integer"},
                    "signals": {"type": "array", "items": {"type": "string"}},
                    "line_index": {"type": "integer", "nullable": True},
                    "command_root": {"type": "string"},
                    "target": {"type": "string"},
                    "entities": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/RunStreamEntity"},
                    },
                },
            },
            "RunStreamEntity": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "type": {"type": "string"},
                    "value": {"type": "string"},
                    "canonical_value": {"type": "string"},
                    "confidence": {"type": "string"},
                    "source_line": {"type": "integer"},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                },
            },
            "NdjsonStream": {
                "type": "string",
                "description": (
                    "Newline-delimited RunStreamEvent objects. The first row is the line-event schema row; "
                    "output rows include v=1 plus kind/role metadata, and idle streams may include heartbeat rows."
                ),
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
    "paths": assessments.assessment_paths() | finding_evidence_paths() | manual.manual_finding_paths() | action_paths() | {
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
        "/teams": {
            "get": {
                "responses": {
                    "200": _json_response("Teams for the current token", _ref("TeamList")),
                    **_common_errors(),
                },
            },
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("TeamCreateRequest")}},
                },
                "responses": {
                    "201": _json_response("Team created", _ref("TeamCreateResponse")),
                    "400": _error_response("Invalid team request"),
                    "409": _error_response("Team slug unavailable"),
                    **_common_errors(),
                },
            },
        },
        "/teams/join": {
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("TeamJoinRequest")}},
                },
                "responses": {
                    "201": _json_response("Invite redeemed", _ref("TeamDetail")),
                    "400": _error_response("Invalid invite code"),
                    "409": _error_response("Team is archived"),
                    **_common_errors(),
                },
            },
        },
        "/teams/recovery/redeem": {
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("TeamJoinRequest")}},
                },
                "responses": {
                    "200": _json_response("Recovery code redeemed", _ref("TeamDetail")),
                    "400": _error_response("Invalid recovery code"),
                    "409": _error_response("Team is archived"),
                    **_common_errors(),
                },
            },
        },
        "/teams/{team_id}": {
            "get": {
                "parameters": [TEAM_ID_PARAM],
                "responses": {
                    "200": _json_response("Team detail", _ref("TeamDetail")),
                    **_common_errors(not_found="Team not found"),
                },
            },
            "patch": {
                "parameters": [TEAM_ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("TeamUpdateRequest")}},
                },
                "responses": {
                    "200": _json_response("Team updated", _ref("TeamDetail")),
                    "403": _error_response("Role lacks required team capability"),
                    "409": _error_response("Team state conflict"),
                    **_common_errors(not_found="Team not found"),
                },
            },
        },
        "/teams/{team_id}/invites": {
            "post": {
                "parameters": [TEAM_ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("TeamInviteCreateRequest")}},
                },
                "responses": {
                    "201": _json_response("Team invite created", _ref("TeamInviteResponse")),
                    "403": _error_response("Role lacks required team capability"),
                    "409": _error_response("Team is archived"),
                    **_common_errors(not_found="Team not found"),
                },
            },
        },
        "/teams/{team_id}/invites/{invite_id}": {
            "delete": {
                "parameters": [TEAM_ID_PARAM, TEAM_INVITE_ID_PARAM],
                "responses": {
                    "200": _json_response("Team invite revoked", _ref("DeleteResponse")),
                    "403": _error_response("Role lacks required team capability"),
                    "409": _error_response("Team is archived"),
                    **_common_errors(not_found="Team not found"),
                },
            },
        },
        "/teams/{team_id}/members/{member_id}": {
            "patch": {
                "parameters": [TEAM_ID_PARAM, TEAM_MEMBER_ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("TeamMemberUpdateRequest")}},
                },
                "responses": {
                    "200": _json_response("Team member updated", _ref("TeamMemberResponse")),
                    "403": _error_response("Role lacks required team capability"),
                    "409": _error_response("Team is archived or must retain an owner"),
                    **_common_errors(not_found="Team member not found"),
                },
            },
            "delete": {
                "parameters": [TEAM_ID_PARAM, TEAM_MEMBER_ID_PARAM],
                "responses": {
                    "200": _json_response("Team member removed", _ref("DeleteResponse")),
                    "403": _error_response("Role lacks required team capability"),
                    "409": _error_response("Team is archived or must retain an owner"),
                    **_common_errors(not_found="Team member not found"),
                },
            },
        },
        "/teams/{team_id}/leave": {
            "post": {
                "parameters": [TEAM_ID_PARAM],
                "responses": {
                    "200": _json_response("Left team", _ref("DeleteResponse")),
                    "409": _error_response("Team must retain an owner"),
                    **_common_errors(not_found="Team not found"),
                },
            },
        },
        "/teams/{team_id}/recovery/rotate": {
            "post": {
                "parameters": [TEAM_ID_PARAM],
                "responses": {
                    "200": _json_response("Recovery code rotated", _ref("TeamRecoveryRotateResponse")),
                    "403": _error_response("Role lacks required team capability"),
                    "409": _error_response("Team is archived"),
                    **_common_errors(not_found="Team not found"),
                },
            },
        },
        "/history": {
            "get": {
                "parameters": [
                    *PAGE_PARAMS,
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                    *STRUCTURED_OUTPUT_PARAMS,
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
        "/history/search": {
            "get": {
                "parameters": [
                    *PAGE_PARAMS,
                    {
                        "name": "q",
                        "in": "query",
                        "required": True,
                        "description": (
                            "Literal text to locate in saved run output. Structured selector tokens such as "
                            "signal:findings are also accepted."
                        ),
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "context",
                        "in": "query",
                        "schema": {"type": "integer", "default": 2, "minimum": 0, "maximum": 10},
                    },
                    *STRUCTURED_OUTPUT_PARAMS,
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
                    "200": _json_response("Paginated output search matches", _ref("HistorySearchPage")),
                    "400": _error_response("Missing query or invalid filter"),
                    **_common_errors(),
                },
            },
        },
        "/atlas": {
            "get": {
                "parameters": [
                    {"name": "run_id", "in": "query", "schema": {"type": "string"}},
                    {"name": "project_id", "in": "query", "schema": {"type": "string"}},
                    {
                        "name": "orphan_filter",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["hide", "all", "only"], "default": "hide"},
                    },
                    {
                        "name": "suppression_filter",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["hide", "all", "only"], "default": "hide"},
                    },
                ],
                "responses": {
                    "200": _json_response("Atlas summary", _ref("AtlasSummary")),
                    **_common_errors(),
                },
            },
        },
        "/atlas/runs": {
            "get": {
                "parameters": [
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                    {"name": "run_id", "in": "query", "schema": {"type": "string"}},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 30, "minimum": 1, "maximum": 50}},
                ],
                "responses": {
                    "200": _json_response("Atlas source runs", _ref("AtlasRunList")),
                    **_common_errors(),
                },
            },
        },
        "/atlas/entities": {
            "get": {
                "parameters": [
                    *PAGE_PARAMS,
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                    {"name": "project_id", "in": "query", "schema": {"type": "string"}},
                    {"name": "run_id", "in": "query", "schema": {"type": "string"}},
                    {
                        "name": "entity_type",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["domain", "ip", "url", "hash", "cve", "port"]},
                    },
                    {
                        "name": "orphan_filter",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["hide", "all", "only"], "default": "hide"},
                    },
                    {
                        "name": "suppression_filter",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["hide", "all", "only"], "default": "hide"},
                    },
                ],
                "responses": {
                    "200": _json_response("Atlas entities", _ref("AtlasEntityPage")),
                    **_common_errors(),
                },
            },
        },
        "/atlas/lookup": {
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _ref("AtlasEntityLookupRequest"),
                        },
                    },
                },
                "responses": {
                    "200": _json_response("Exact Atlas entity lookup", _ref("AtlasEntityLookupResponse")),
                    "400": _error_response("Invalid lookup value, type, or project scope"),
                    **_common_errors(),
                },
            },
        },
        "/atlas/entities/{entity_id}": {
            "get": {
                "parameters": [
                    _path_param("entity_id", "Atlas entity id"),
                    *atlas_profile_query_parameters(),
                ],
                "responses": {
                    "200": _json_response("Atlas entity detail", _ref("AtlasEntityDetail")),
                    **_common_errors(not_found="Atlas entity not found"),
                },
            },
        },
        "/atlas/findings": {
            "get": {
                "parameters": [
                    *PAGE_PARAMS,
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                    {"name": "project_id", "in": "query", "schema": {"type": "string"}},
                    {"name": "run_id", "in": "query", "schema": {"type": "string"}},
                    {
                        "name": "review_state",
                        "in": "query",
                        "schema": {"type": "array", "items": {"type": "string"}},
                        "style": "form",
                        "explode": True,
                    },
                    {
                        "name": "orphan_filter",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["hide", "all", "only"], "default": "hide"},
                    },
                    {
                        "name": "suppression_filter",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["hide", "all", "only"], "default": "hide"},
                    },
                ],
                "responses": {
                    "200": _json_response("Atlas findings", _ref("AtlasFindingPage")),
                    **_common_errors(),
                },
            },
        },
        "/atlas/findings/{finding_id}": {
            "get": {
                "parameters": [_path_param("finding_id", "Atlas finding id")],
                "responses": {
                    "200": _json_response("Atlas finding detail", _ref("AtlasFindingDetail")),
                    **_common_errors(not_found="Atlas finding not found"),
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
                    {
                        "name": "range",
                        "in": "query",
                        "description": "1-based inclusive line range, such as 10-40.",
                        "schema": {"type": "string", "pattern": "^[1-9][0-9]*-[1-9][0-9]*$"},
                    },
                    *STRUCTURED_OUTPUT_PARAMS,
                ],
                "responses": {
                    "200": {
                        "description": "Run output",
                        "content": {
                            "text/plain": {"schema": {"type": "string"}},
                            "application/json": {"schema": _ref("RunOutput")},
                        },
                    },
                    "400": _error_response("Invalid range"),
                    **_common_errors(not_found="Run not found"),
                },
            },
        },
        "/runs/{run_id}/output": {
            "get": {
                "parameters": [
                    RUN_ID_PARAM,
                    {
                        "name": "format",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["text", "json"], "default": "text"},
                    },
                    {
                        "name": "range",
                        "in": "query",
                        "description": "1-based inclusive line range, such as 10-40.",
                        "schema": {"type": "string", "pattern": "^[1-9][0-9]*-[1-9][0-9]*$"},
                    },
                    *STRUCTURED_OUTPUT_PARAMS,
                ],
                "responses": {
                    "200": {
                        "description": "Run output",
                        "content": {
                            "text/plain": {"schema": {"type": "string"}},
                            "application/json": {"schema": _ref("RunOutput")},
                        },
                    },
                    "400": _error_response("Invalid range"),
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
            "post": manual.manual_finding_create_operation(),
        },
        "/projects/{project_id}/runs": {
            "get": {
                "parameters": [PROJECT_ID_PARAM, *PAGE_PARAMS],
                "responses": {
                    "200": _json_response("Project runs", _ref("ProjectRunPage")),
                    **_common_errors(not_found="Project not found"),
                },
            },
        },
        "/projects/{project_id}/entities": {
            "get": {
                "parameters": [
                    PROJECT_ID_PARAM,
                    *PAGE_PARAMS,
                    {
                        "name": "entity_type",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["domain", "ip", "url", "hash", "cve", "port"]},
                    },
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
                ],
                "responses": {
                    "200": _json_response("Project entities", _ref("ProjectEntityPage")),
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
        "/schedules": {
            "get": {
                "parameters": [*PAGE_PARAMS],
                "responses": {
                    "200": _json_response("Scheduled commands", _ref("SchedulePage")),
                    **_common_errors(),
                },
            },
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("ScheduleCreateRequest")}},
                },
                "responses": {
                    "201": _json_response("Schedule created", _ref("ScheduleResponse")),
                    "400": _error_response("Invalid schedule or command"),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "409": _error_response("Schedule quota exceeded"),
                    "429": _error_response("Rate limit exceeded"),
                },
            },
        },
        "/schedules/{schedule_id}": {
            "get": {
                "parameters": [SCHEDULE_ID_PARAM],
                "responses": {
                    "200": _json_response("Schedule detail", _ref("ScheduleResponse")),
                    **_common_errors(not_found="Schedule not found"),
                },
            },
            "patch": {
                "parameters": [SCHEDULE_ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("ScheduleUpdateRequest")}},
                },
                "responses": {
                    "200": _json_response("Schedule updated", _ref("ScheduleResponse")),
                    "400": _error_response("Invalid schedule or command"),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "404": _error_response("Schedule not found"),
                    "409": _error_response("Schedule quota exceeded"),
                    "429": _error_response("Rate limit exceeded"),
                },
            },
            "delete": {
                "parameters": [SCHEDULE_ID_PARAM],
                "responses": {
                    "200": _json_response("Schedule deleted", _ref("DeleteResponse")),
                    **_common_errors(not_found="Schedule not found"),
                },
            },
        },
        "/schedules/{schedule_id}/run-now": {
            "post": {
                "parameters": [SCHEDULE_ID_PARAM],
                "responses": {
                    "200": _json_response("Schedule fired immediately", _ref("ScheduleRunNowResponse")),
                    "400": _error_response("Invalid schedule"),
                    **_common_errors(not_found="Schedule not found"),
                },
            },
        },
        "/schedules/{schedule_id}/fires": {
            "get": {
                "parameters": [SCHEDULE_ID_PARAM, *PAGE_PARAMS],
                "responses": {
                    "200": _json_response("Schedule fire audit rows", _ref("ScheduleFirePage")),
                    **_common_errors(not_found="Schedule not found"),
                },
            },
        },
        "/watchers": {
            "get": {
                "parameters": [*PAGE_PARAMS],
                "responses": {
                    "200": _json_response("Change-detection watchers", _ref("WatcherPage")),
                    **_common_errors(),
                },
            },
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("WatcherCreateRequest")}},
                },
                "responses": {
                    "201": _json_response("Watcher created", _ref("WatcherResponse")),
                    "400": _error_response("Invalid watcher or command"),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "404": _error_response("Baseline run not found"),
                    "409": _error_response("Watcher quota exceeded"),
                    "429": _error_response("Rate limit exceeded"),
                },
            },
        },
        "/watchers/{watcher_id}": {
            "get": {
                "parameters": [WATCHER_ID_PARAM],
                "responses": {
                    "200": _json_response("Watcher detail", _ref("WatcherResponse")),
                    **_common_errors(not_found="Watcher not found"),
                },
            },
            "patch": {
                "parameters": [WATCHER_ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("WatcherUpdateRequest")}},
                },
                "responses": {
                    "200": _json_response("Watcher updated", _ref("WatcherResponse")),
                    "400": _error_response("Invalid watcher or command"),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "404": _error_response("Watcher not found"),
                    "409": _error_response("Watcher quota exceeded"),
                    "429": _error_response("Rate limit exceeded"),
                },
            },
            "delete": {
                "parameters": [WATCHER_ID_PARAM],
                "responses": {
                    "200": _json_response("Watcher deleted", _ref("DeleteResponse")),
                    **_common_errors(not_found="Watcher not found"),
                },
            },
        },
        "/watchers/{watcher_id}/run-now": {
            "post": {
                "parameters": [WATCHER_ID_PARAM],
                "responses": {
                    "200": _json_response("Watcher fired immediately", _ref("WatcherRunNowResponse")),
                    "400": _error_response("Invalid watcher"),
                    **_common_errors(not_found="Watcher not found"),
                },
            },
        },
        "/watchers/{watcher_id}/fires": {
            "get": {
                "parameters": [WATCHER_ID_PARAM, *PAGE_PARAMS],
                "responses": {
                    "200": _json_response("Watcher fire audit rows", _ref("WatcherFirePage")),
                    **_common_errors(not_found="Watcher not found"),
                },
            },
        },
        "/watchers/{watcher_id}/accept-baseline": {
            "post": {
                "parameters": [WATCHER_ID_PARAM],
                "requestBody": {
                    "required": False,
                    "content": {"application/json": {"schema": _ref("WatcherAcceptBaselineRequest")}},
                },
                "responses": {
                    "200": _json_response("Watcher baseline accepted", _ref("WatcherResponse")),
                    "400": _error_response("Invalid baseline"),
                    **_common_errors(not_found="Watcher not found"),
                },
            },
        },
        "/notification-channels": {
            "get": {
                "responses": {
                    "200": _json_response("Notification channels", _ref("NotificationChannelList")),
                    **_common_errors(),
                },
            },
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("NotificationChannelCreateRequest")}},
                },
                "responses": {
                    "201": _json_response("Notification channel created", _ref("NotificationChannelResponse")),
                    "400": _error_response("Invalid notification channel"),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "429": _error_response("Rate limit exceeded"),
                    "503": _error_response("Vault unavailable"),
                },
            },
        },
        "/notification-channel-kinds": {
            "get": {
                "responses": {
                    "200": _json_response(
                        "Notification channel kind contract",
                        _ref("NotificationChannelKindList"),
                    ),
                    **_common_errors(),
                },
            },
        },
        "/notification-channels/{channel_id}": {
            "patch": {
                "parameters": [NOTIFICATION_CHANNEL_ID_PARAM],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("NotificationChannelUpdateRequest")}},
                },
                "responses": {
                    "200": _json_response("Notification channel updated", _ref("NotificationChannelResponse")),
                    "400": _error_response("Invalid notification channel"),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "404": _error_response("Notification channel not found"),
                    "429": _error_response("Rate limit exceeded"),
                    "503": _error_response("Vault unavailable"),
                },
            },
            "delete": {
                "parameters": [NOTIFICATION_CHANNEL_ID_PARAM],
                "responses": {
                    "200": _json_response("Notification channel deleted", _ref("DeleteResponse")),
                    **_common_errors(not_found="Notification channel not found"),
                },
            },
        },
        "/notification-channels/{channel_id}/test": {
            "post": {
                "parameters": [NOTIFICATION_CHANNEL_ID_PARAM],
                "responses": {
                    "200": _json_response(
                        "Test notification queued and delivered when possible",
                        _ref("NotificationTestResponse"),
                    ),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "404": _error_response("Notification channel not found"),
                    "429": _error_response("Rate limit exceeded"),
                    "503": _error_response("Vault unavailable"),
                },
            },
        },
        "/notification-events": {
            "get": {
                "parameters": [
                    *PAGE_PARAMS,
                    {"name": "channel_id", "in": "query", "schema": {"type": "string"}},
                    {
                        "name": "trigger",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": [
                                "run_complete",
                                "pty_session_ended",
                                "watcher_changed",
                                "watcher_error",
                                "watcher_recovered",
                                "scheduled_run_failed",
                                "test",
                            ],
                        },
                    },
                    {
                        "name": "status",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["pending", "retry_wait", "sent", "dead"]},
                    },
                ],
                "responses": {
                    "200": _json_response("Notification delivery audit events", _ref("NotificationEventPage")),
                    "400": _error_response("Invalid notification event filter"),
                    **_common_errors(),
                },
            },
        },
        "/runs": {
            "get": {
                "responses": {
                    "200": _json_response("Active runs for the current token", _ref("ActiveRunList")),
                    **_common_errors(),
                },
            },
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
        "/runs/{run_id}/wait": {
            "post": {
                "parameters": [
                    RUN_ID_PARAM,
                    {
                        "name": "timeout",
                        "in": "query",
                        "schema": {"type": "number", "default": 30, "minimum": 0, "maximum": 3600},
                    },
                ],
                "responses": {
                    "200": _json_response("Terminal run status", _ref("RunStatus")),
                    "408": _error_response("Run is still running"),
                    **_common_errors(not_found="Run not found"),
                },
            },
        },
        "/runs/{run_id}/ai-assists": {
            "get": {
                "parameters": [RUN_ID_PARAM],
                "responses": {
                    "200": _json_response("Cached and in-flight AI assists", _ref("AIAssistList")),
                    **_common_errors(not_found="Run not found"),
                },
            },
        },
        "/runs/{run_id}/ai-summary": {
            "post": {
                "parameters": [RUN_ID_PARAM],
                "requestBody": {
                    "required": False,
                    "content": {"application/json": {"schema": _ref("AIAssistRequest")}},
                },
                "responses": {
                    "200": _json_response("Cached summary assist", _ref("AIAssistResponse")),
                    "202": _json_response("Queued or in-progress summary assist", _ref("AIAssistResponse")),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "403": _error_response("AI disabled or team role denied"),
                    "404": _error_response("Run not found"),
                    "409": _error_response("Run still active"),
                    "422": _error_response("No useful AI context"),
                    "429": _error_response("AI queue full or rate limit exceeded"),
                    "503": _error_response("AI coordination or provider unavailable"),
                },
            },
        },
        "/runs/{run_id}/ai-next-commands": {
            "post": {
                "parameters": [RUN_ID_PARAM],
                "requestBody": {
                    "required": False,
                    "content": {"application/json": {"schema": _ref("AIAssistRequest")}},
                },
                "responses": {
                    "200": _json_response("Cached next-command assist", _ref("AIAssistResponse")),
                    "202": _json_response("Queued or in-progress next-command assist", _ref("AIAssistResponse")),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "403": _error_response("AI disabled or team role denied"),
                    "404": _error_response("Run not found"),
                    "409": _error_response("Run still active"),
                    "422": _error_response("No useful AI context"),
                    "429": _error_response("AI queue full or rate limit exceeded"),
                    "503": _error_response("AI coordination or provider unavailable"),
                },
            },
        },
        "/runs/{run_id}/projects/{project_id}": {
            "post": {
                "parameters": [RUN_ID_PARAM, PROJECT_ID_PARAM],
                "responses": {
                    "201": _json_response("Run linked to project", _ref("ProjectRunLinkResponse")),
                    "400": _error_response("Invalid project link"),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "404": _error_response("Run or project not found"),
                    "409": _error_response("Archived project or quota exceeded"),
                    "429": _error_response("Rate limit exceeded"),
                },
            },
            "delete": {
                "parameters": [RUN_ID_PARAM, PROJECT_ID_PARAM],
                "responses": {
                    "200": _json_response("Run unlinked from project", _ref("OkResponse")),
                    "400": _error_response("Invalid project link"),
                    "401": _error_response("Missing, invalid, or revoked token"),
                    "404": _error_response("Run, project, or project link not found"),
                    "409": _error_response("Archived project"),
                    "429": _error_response("Rate limit exceeded"),
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
