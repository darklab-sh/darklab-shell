# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for the Atlas entity profile contract."""

from __future__ import annotations

from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def atlas_profile_schemas() -> dict[str, Any]:
    count_map = {"type": "object", "additionalProperties": {"type": "integer"}}
    return {
        "AtlasFindingRollup": {
            "type": "object",
            "required": [
                "applicable",
                "total",
                "all_total",
                "suppressed",
                "occurrence_count",
                "latest_activity_at",
                "by_severity",
                "by_review_state",
                "by_verification_state",
                "by_suppression",
                "sample",
                "navigation_hint",
            ],
            "properties": {
                "applicable": {"type": "boolean"},
                "total": {"type": "integer"},
                "all_total": {"type": "integer"},
                "suppressed": {"type": "integer"},
                "occurrence_count": {"type": "integer"},
                "latest_activity_at": {"type": "string"},
                "by_severity": count_map,
                "by_review_state": count_map,
                "by_verification_state": count_map,
                "by_suppression": count_map,
                "sample": {"type": "array", "items": _ref("AtlasFinding")},
                "navigation_hint": {"type": "object", "additionalProperties": True},
            },
        },
        "AtlasEntityFindingSummary": {
            "type": "object",
            "required": ["scope", "direct", "related_urls", "related_ports", "combined"],
            "properties": {
                "scope": {"type": "object", "additionalProperties": True},
                "direct": _ref("AtlasFindingRollup"),
                "related_urls": _ref("AtlasFindingRollup"),
                "related_ports": _ref("AtlasFindingRollup"),
                "combined": _ref("AtlasFindingRollup"),
            },
        },
        "AtlasAppEvidence": {
            "type": "object",
            "required": [
                "applicable",
                "coverage_state",
                "scan_run_count",
                "last_observed_at",
                "port_entity_count",
                "app_port_count",
                "app_port_run_count",
                "project_entity_port_count",
                "command_roots",
                "host_entity_id",
                "scope_note",
                "coverage_caveat",
            ],
            "properties": {
                "applicable": {"type": "boolean"},
                "coverage_state": {
                    "type": "string",
                    "enum": ["app_ports_found", "scanned_no_ports_seen", "not_scanned", "not_applicable"],
                },
                "scan_run_count": {"type": "integer"},
                "last_observed_at": {"type": "string"},
                "port_entity_count": {"type": "integer"},
                "app_port_count": {"type": "integer"},
                "app_port_run_count": {"type": "integer"},
                "project_entity_port_count": {"type": "integer"},
                "command_roots": {"type": "array", "items": {"type": "string"}},
                "host_entity_id": {"type": "string"},
                "scope_note": {"type": "string"},
                "coverage_caveat": {"type": "string"},
            },
        },
        "AtlasAppPortEvidence": {
            "type": "object",
            "required": [
                "port",
                "proto",
                "service",
                "version",
                "banner_available",
                "occurrence_count",
                "last_seen_at",
                "source_run_count",
            ],
            "properties": {
                "port": {"type": "integer"},
                "proto": {"type": "string"},
                "service": {"type": "string"},
                "version": {"type": "string"},
                "banner_available": {"type": "boolean"},
                "banner": {"type": "string"},
                "occurrence_count": {"type": "integer"},
                "last_seen_at": {"type": "string"},
                "source_run_count": {"type": "integer"},
            },
        },
        "AtlasProjectMonitoringContext": {
            "type": "object",
            "required": [
                "applicable",
                "project_id",
                "project_name",
                "state",
                "watcher_count",
                "counts",
                "latest_change_at",
                "recent_changes",
                "links",
            ],
            "properties": {
                "applicable": {"type": "boolean"},
                "project_id": {"type": "string"},
                "project_name": {"type": "string"},
                "state": {
                    "type": "string",
                    "enum": [
                        "not_applicable",
                        "not_monitored",
                        "active",
                        "changed",
                        "failed",
                        "quiet",
                        "paused",
                        "unavailable",
                    ],
                },
                "watcher_count": {"type": "integer"},
                "counts": count_map,
                "latest_change_at": {"type": "string"},
                "recent_changes": {
                    "type": "array",
                    "items": {"type": "object", "additionalProperties": True},
                },
                "links": {"type": "object", "additionalProperties": {"type": "string"}},
            },
        },
        "AtlasEntityObservedSummary": {
            "type": "object",
            "required": [
                "state",
                "source_run_count",
                "occurrence_count",
                "first_seen_at",
                "last_seen_at",
                "app_ports",
                "app_port_count",
                "app_ports_truncated",
                "app_services",
                "app_evidence",
                "project_monitoring",
            ],
            "properties": {
                "state": {"type": "string", "enum": ["observed"]},
                "source_run_count": {"type": "integer"},
                "occurrence_count": {"type": "integer"},
                "first_seen_at": {"type": "string"},
                "last_seen_at": {"type": "string"},
                "app_ports": {"type": "array", "items": _ref("AtlasAppPortEvidence")},
                "app_port_count": {"type": "integer"},
                "app_ports_truncated": {"type": "boolean"},
                "app_services": {"type": "array", "items": {"type": "string"}},
                "app_evidence": _ref("AtlasAppEvidence"),
                "project_monitoring": _ref("AtlasProjectMonitoringContext"),
            },
        },
        "AtlasCertificateEvidence": {
            "type": "object",
            "required": ["status", "expires_at", "days_until_expiry", "last_checked_at"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["expired", "expiring_14d", "expiring_30d", "healthy", "unknown"],
                },
                "expires_at": {"type": "string"},
                "days_until_expiry": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}],
                },
                "last_checked_at": {"type": "string"},
            },
        },
        "AtlasPortDivergence": {
            "type": "object",
            "required": ["app_only", "provider_only", "has_drift"],
            "properties": {
                "app_only": {"type": "array", "items": {"type": "integer"}},
                "provider_only": {"type": "array", "items": {"type": "integer"}},
                "has_drift": {"type": "boolean"},
            },
        },
        "AtlasPortProvenance": {
            "type": "object",
            "required": ["app", "provider", "divergence"],
            "properties": {
                "app": {"type": "array", "items": _ref("AtlasAppPortEvidence")},
                "provider": {"type": "array", "items": {"type": "integer"}},
                "divergence": _ref("AtlasPortDivergence"),
            },
        },
        "AtlasIntelOverview": {
            "type": "object",
            "required": [
                "status",
                "freshness",
                "snapshot_count",
                "provider_count",
                "providers_with_data",
                "last_refresh_at",
                "highlight_count",
                "highlights",
                "provider_ports",
                "provider_services",
                "certificate",
                "port_provenance",
                "summary",
            ],
            "properties": {
                "status": {"type": "string", "enum": ["none", "empty", "available"]},
                "freshness": {
                    "type": "string",
                    "enum": ["fresh", "stale", "unknown", "not_available"],
                },
                "snapshot_count": {"type": "integer"},
                "provider_count": {"type": "integer"},
                "providers_with_data": {"type": "array", "items": {"type": "string"}},
                "last_refresh_at": {"type": "string"},
                "highlight_count": {"type": "integer"},
                "highlights": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "provider_ports": {"type": "array", "items": {"type": "integer"}},
                "provider_services": {"type": "array", "items": {"type": "string"}},
                "certificate": _ref("AtlasCertificateEvidence"),
                "port_provenance": _ref("AtlasPortProvenance"),
                "summary": {"type": "object", "additionalProperties": True},
            },
        },
        "AtlasEntityOverview": {
            "type": "object",
            "required": ["observed", "finding_summary", "relationships", "intel"],
            "properties": {
                "observed": _ref("AtlasEntityObservedSummary"),
                "finding_summary": _ref("AtlasEntityFindingSummary"),
                "relationships": {"type": "object", "additionalProperties": True},
                "intel": _ref("AtlasIntelOverview"),
            },
        },
        "AtlasEntityDetail": {
            "type": "object",
            "required": [
                "entity",
                "overview",
                "scope",
                "parent_host",
                "runs",
                "related_urls",
                "related_ports",
                "relationship_summary",
                "finding_summary",
                "findings",
                "intel_snapshots",
                "intel_summary",
                "detail_limits",
            ],
            "properties": {
                "entity": _ref("AtlasEntity"),
                "overview": _ref("AtlasEntityOverview"),
                "scope": {"type": "object", "additionalProperties": True},
                "parent_host": {"anyOf": [_ref("AtlasEntity"), {"type": "null"}]},
                "runs": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "related_urls": {"type": "array", "items": _ref("AtlasEntity")},
                "related_ports": {"type": "array", "items": _ref("AtlasEntity")},
                "relationship_summary": {"type": "object", "additionalProperties": True},
                "finding_summary": _ref("AtlasEntityFindingSummary"),
                "findings": {"type": "array", "items": _ref("AtlasFinding")},
                "intel_snapshots": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "intel_summary": {"type": "object", "additionalProperties": True},
                "detail_limits": {"type": "object", "additionalProperties": True},
            },
        },
        "AtlasEntityLookupRequest": {
            "type": "object",
            "required": ["value"],
            "additionalProperties": False,
            "properties": {
                "value": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "One hostname, IP address, or absolute HTTP(S) URL. "
                        "Canonical values may not exceed 2,048 UTF-8 bytes."
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "hostname", "ip", "url"],
                    "default": "auto",
                    "description": (
                        "Input type. Hostname resolves the stored Atlas domain type; "
                        "URL requires an explicit http:// or https:// scheme."
                    ),
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional visible Project scope for the exact lookup.",
                },
            },
        },
        "AtlasEntityLookupCandidate": {
            "type": "object",
            "required": [
                "entity_id",
                "type",
                "canonical_value",
                "provenance",
                "first_seen_at",
                "last_seen_at",
                "occurrence_count",
                "suppressed",
            ],
            "additionalProperties": False,
            "properties": {
                "entity_id": {"type": "string"},
                "type": {"type": "string", "enum": ["domain", "ip", "url"]},
                "canonical_value": {"type": "string"},
                "provenance": {
                    "type": "string",
                    "enum": ["personal", "direct_team", "compatibility_visible"],
                },
                "first_seen_at": {"type": "string"},
                "last_seen_at": {"type": "string"},
                "occurrence_count": {"type": "integer"},
                "suppressed": {"type": "boolean"},
            },
        },
        "AtlasEntityLookupParentCandidate": {
            "type": "object",
            "required": [
                "detected_type",
                "canonical_value",
                "match_state",
                "entity",
                "candidates",
                "candidates_truncated",
            ],
            "additionalProperties": False,
            "properties": {
                "detected_type": {"type": "string", "enum": ["domain", "ip"]},
                "canonical_value": {"type": "string"},
                "match_state": {"type": "string", "enum": ["found", "ambiguous"]},
                "entity": {
                    "anyOf": [_ref("AtlasEntityLookupCandidate"), {"type": "null"}],
                },
                "candidates": {
                    "type": "array",
                    "items": _ref("AtlasEntityLookupCandidate"),
                    "maxItems": 10,
                },
                "candidates_truncated": {"type": "boolean"},
            },
        },
        "AtlasEntityLookupResponse": {
            "type": "object",
            "required": [
                "requested_type",
                "detected_type",
                "canonical_value",
                "project_id",
                "match_state",
                "detail",
                "candidates",
                "candidates_truncated",
                "parent_host_candidate",
            ],
            "additionalProperties": False,
            "properties": {
                "requested_type": {
                    "type": "string",
                    "enum": ["auto", "hostname", "ip", "url"],
                },
                "detected_type": {"type": "string", "enum": ["domain", "ip", "url"]},
                "canonical_value": {"type": "string"},
                "project_id": {"type": "string"},
                "match_state": {
                    "type": "string",
                    "enum": ["found", "not_found", "ambiguous"],
                },
                "detail": {"anyOf": [_ref("AtlasEntityDetail"), {"type": "null"}]},
                "candidates": {
                    "type": "array",
                    "items": _ref("AtlasEntityLookupCandidate"),
                    "maxItems": 10,
                },
                "candidates_truncated": {"type": "boolean"},
                "parent_host_candidate": {
                    "anyOf": [_ref("AtlasEntityLookupParentCandidate"), {"type": "null"}],
                },
            },
        },
    }


def atlas_profile_query_parameters() -> list[dict[str, Any]]:
    return [
        {"name": "project_id", "in": "query", "schema": {"type": "string"}},
        {
            "name": "finding_bucket",
            "in": "query",
            "schema": {
                "type": "string",
                "enum": ["direct", "related_urls", "related_ports", "combined"],
                "default": "direct",
            },
        },
        *[
            {"name": name, "in": "query", "schema": {"type": "integer", "default": 0, "minimum": 0}}
            for name in ("runs_offset", "findings_offset", "related_urls_offset", "related_ports_offset")
        ],
    ]
