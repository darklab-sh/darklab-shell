"""
Evidence package helpers for project workspaces.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath
import re

import config as _config
from core.database import DB_BACKEND
from core.database_backend import dialect_for_backend
from core.redaction import apply_redaction_rules
from services.projects.package_presets import known_package_preset_ids
from services.projects.provenance import attach_finding_target_references
from services.projects.contracts import (
    MAX_ENTITY_ID_LEN,
    MAX_ENTITY_NOTE_BODY_LEN,
    MAX_LABEL_LEN,
    MAX_PACKAGE_DESCRIPTION_LEN,
    MAX_PACKAGE_NAME_LEN,
    ProjectWorkspaceError,
)
from services.projects.utils import cfg_int as _cfg_int
from services.projects.utils import cfg_mb_bytes as _cfg_mb_bytes
from services.projects.utils import trim_text as _trim_text


_TEXT_ARTIFACT_PREVIEW_TYPES = {"text", "json", "markdown", "csv", "log", "xml", "yaml", "yml"}
_TEXT_ARTIFACT_EXTENSIONS = {
    ".csv",
    ".htm",
    ".html",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".ndjson",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_TEXT_ARTIFACT_CONTENT_MARKERS = (
    "text/",
    "application/json",
    "application/ld+json",
    "application/xml",
    "application/x-ndjson",
    "application/yaml",
    "application/x-yaml",
)
EVIDENCE_PACKAGE_FORMAT_VERSION = 2
EVIDENCE_PACKAGE_PROVENANCE_SCHEMA_VERSION = 1


def row_to_evidence_package(row):
    if not row:
        return None
    try:
        manifest = dialect_for_backend(DB_BACKEND).decode_json_dict(row["manifest"])
    except (TypeError, ValueError):
        manifest = {}
    manifest = normalize_evidence_package_manifest(manifest)
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "description": row["description"] or "",
        "redaction_mode": row["redaction_mode"],
        "include_artifacts": bool(row["include_artifacts"]),
        "manifest": manifest,
        "status": row["status"],
        "created": row["created"],
        "updated": row["updated"],
    }


def normalize_evidence_package_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("package payload must be an object")
    name = _trim_text(data.get("name"), MAX_PACKAGE_NAME_LEN)
    if not name:
        raise ProjectWorkspaceError("package name is required")
    selection = data.get("selection")
    if selection is not None and not isinstance(selection, dict):
        raise ProjectWorkspaceError("package selection must be an object")
    options = data.get("options")
    if options is not None and not isinstance(options, dict):
        raise ProjectWorkspaceError("package options must be an object")
    redaction_mode = _trim_text(data.get("redaction_mode"), 32).lower() or "raw"
    if redaction_mode not in {"raw", "redacted"}:
        raise ProjectWorkspaceError("package redaction mode must be raw or redacted")
    include_artifacts = bool(data.get("include_artifacts"))
    if not bool(_config.CFG.get("workspace_enabled", False)):
        include_artifacts = False
    labels = []
    raw_labels = data.get("labels")
    if raw_labels is not None:
        if not isinstance(raw_labels, list):
            raise ProjectWorkspaceError("package labels must be a list")
        seen_labels = set()
        for raw_label in raw_labels:
            label = _trim_text(raw_label, MAX_LABEL_LEN)
            if not label:
                continue
            key = label.lower()
            if key in seen_labels:
                continue
            seen_labels.add(key)
            labels.append(label)
        if len(labels) > 20:
            raise ProjectWorkspaceError("label quota exceeded for this entity")
    preset = _trim_text(data.get("preset"), 32).lower() or "custom"
    if preset != "custom" and preset not in known_package_preset_ids(_config.CFG):
        raise ProjectWorkspaceError("package preset is not configured")

    return {
        "name": name,
        "description": _trim_text(data.get("description"), MAX_PACKAGE_DESCRIPTION_LEN),
        "redaction_mode": redaction_mode,
        "include_artifacts": include_artifacts,
        "preset": preset,
        "package_format_version": EVIDENCE_PACKAGE_FORMAT_VERSION,
        "include_private_notes": bool(data.get("include_private_notes")),
        "selection": selection if isinstance(selection, dict) else None,
        "options": options if isinstance(options, dict) else {},
        "labels": labels,
        "notes": _trim_text(data.get("notes"), MAX_ENTITY_NOTE_BODY_LEN),
    }


def redacted_artifact_derivative_reason(artifact):
    """Return a reason when an artifact cannot be included as a redacted derivative."""
    if not isinstance(artifact, dict):
        return "Artifact metadata is unavailable."
    status = str(artifact.get("file_status") or "available")
    if status != "available":
        return str(artifact.get("file_status_detail") or "Artifact is unavailable or changed.")
    preview_type = str(artifact.get("preview_type") or "").strip().lower()
    if preview_type in _TEXT_ARTIFACT_PREVIEW_TYPES:
        return ""
    content_type = str(artifact.get("content_type") or "").strip().lower()
    if content_type and any(marker in content_type for marker in _TEXT_ARTIFACT_CONTENT_MARKERS):
        return ""
    workspace_path = str(artifact.get("workspace_path") or artifact.get("display_name") or "")
    suffix = PurePosixPath(workspace_path.replace("\\", "/")).suffix.lower()
    if suffix in _TEXT_ARTIFACT_EXTENSIONS:
        return ""
    return "Artifact is not a text or JSON type that can be safely redacted."


def redacted_artifact_derivative_warnings(selected_artifacts):
    warnings = []
    for artifact in selected_artifacts:
        if not isinstance(artifact, dict):
            continue
        reason = redacted_artifact_derivative_reason(artifact)
        if not reason:
            continue
        warnings.append({
            "kind": "artifact",
            "id": artifact.get("id") or "",
            "label": artifact.get("display_name") or artifact.get("workspace_path") or artifact.get("id") or "",
            "workspace_path": artifact.get("workspace_path") or "",
            "reason": reason,
        })
    return warnings


def normalized_package_selection_ids(selection, key, allowed_ids):
    allowed = {str(value) for value in allowed_ids if value}
    if not isinstance(selection, dict) or key not in selection:
        return sorted(allowed)
    raw_values = selection.get(key)
    if not isinstance(raw_values, list):
        raise ProjectWorkspaceError(f"package selection {key} must be a list")
    selected = []
    seen = set()
    for value in raw_values:
        normalized = _trim_text(value, MAX_ENTITY_ID_LEN)
        if not normalized:
            continue
        if normalized not in allowed:
            raise ProjectWorkspaceError("package selection includes an entity that is not linked to this project")
        if normalized in seen:
            continue
        seen.add(normalized)
        selected.append(normalized)
    return selected


def _filter_package_items(items, selected_ids):
    selected = {str(value) for value in selected_ids if value}
    return [item for item in items if str(item.get("id") or "") in selected]


def _estimate_package_run_line_count(run):
    try:
        return max(0, int((run or {}).get("output_line_count") or 0))
    except (TypeError, ValueError):
        return 0


def _estimate_package_run_full_output_bytes(run):
    for key in ("full_output_byte_size", "full_output_bytes", "output_artifact_byte_size"):
        try:
            value = int((run or {}).get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _estimate_transcript_html_bytes(line_count, max_lines):
    capped_lines = min(max(0, line_count), max(1, max_lines))
    return 8192 + capped_lines * 240


def _estimate_transcript_text_companion_bytes(run, line_count):
    if line_count <= 0:
        return 0
    full_output_bytes = _estimate_package_run_full_output_bytes(run)
    if full_output_bytes > 0:
        return max(line_count, int(full_output_bytes * 0.65))
    return line_count * 48


def _estimate_text_zip_bytes(value):
    safe_value = max(0, value)
    if not safe_value:
        return 0
    return max(1024, int(safe_value * 0.4))


def estimate_evidence_package_archive(selected_runs, selected_findings, selected_artifacts, selected_targets, payload):
    max_lines = _cfg_int("max_output_lines", 5000) or 5000
    max_archive_bytes = _cfg_mb_bytes("evidence_package_max_mb", 25)
    max_uncompressed_archive_bytes = _cfg_mb_bytes("evidence_package_max_uncompressed_mb", 500)
    redaction_mode = str(payload.get("redaction_mode") or "raw")
    include_artifacts = bool(payload.get("include_artifacts"))
    raw_artifacts_enabled = include_artifacts and redaction_mode != "redacted"
    redacted_artifacts_enabled = include_artifacts and redaction_mode == "redacted"
    raw_artifact_bytes = 0
    redacted_artifact_bytes = 0
    redacted_artifact_count_estimate = 0
    skipped_artifact_count_estimate = 0
    artifact_warnings = []
    if raw_artifacts_enabled or redacted_artifacts_enabled:
        for artifact in selected_artifacts:
            status = str((artifact or {}).get("file_status") or "available")
            if status != "available":
                skipped_artifact_count_estimate += 1
                artifact_warnings.append({
                    "kind": "artifact",
                    "id": (artifact or {}).get("id") or "",
                    "label": (artifact or {}).get("display_name") or (artifact or {}).get("workspace_path") or "",
                    "workspace_path": (artifact or {}).get("workspace_path") or "",
                    "reason": (artifact or {}).get("file_status_detail") or "Artifact is unavailable or changed.",
                })
                continue
            try:
                artifact_bytes = max(0, int((artifact or {}).get("byte_size") or 0))
            except (TypeError, ValueError):
                skipped_artifact_count_estimate += 1
                artifact_warnings.append({
                    "kind": "artifact",
                    "id": (artifact or {}).get("id") or "",
                    "label": (artifact or {}).get("display_name") or (artifact or {}).get("workspace_path") or "",
                    "workspace_path": (artifact or {}).get("workspace_path") or "",
                    "reason": "Artifact size is unavailable.",
                })
                continue
            if raw_artifacts_enabled:
                raw_artifact_bytes += artifact_bytes
                continue
            reason = redacted_artifact_derivative_reason(artifact)
            if reason:
                skipped_artifact_count_estimate += 1
                artifact_warnings.append({
                    "kind": "artifact",
                    "id": (artifact or {}).get("id") or "",
                    "label": (artifact or {}).get("display_name") or (artifact or {}).get("workspace_path") or "",
                    "workspace_path": (artifact or {}).get("workspace_path") or "",
                    "reason": reason,
                })
                continue
            redacted_artifact_bytes += artifact_bytes
            redacted_artifact_count_estimate += 1

    transcript_html_bytes = 0
    transcript_text_companion_bytes = 0
    selection = payload.get("selection")
    transcript_run_ids = set()
    if isinstance(selection, dict) and isinstance(selection.get("transcript_run_ids"), list):
        transcript_run_ids = {str(run_id) for run_id in selection["transcript_run_ids"] if str(run_id)}
    else:
        transcript_run_ids = {str((run or {}).get("id") or "") for run in selected_runs if (run or {}).get("id")}
    transcript_runs = [
        run for run in selected_runs
        if str((run or {}).get("id") or "") in transcript_run_ids
    ]
    for run in transcript_runs:
        line_count = _estimate_package_run_line_count(run)
        transcript_html_bytes += _estimate_transcript_html_bytes(line_count, max_lines)
        if line_count > max_lines:
            transcript_text_companion_bytes += _estimate_transcript_text_companion_bytes(run, line_count)

    metadata_seed = {
        "runs": selected_runs,
        "findings": selected_findings,
        "targets": selected_targets,
        "artifacts": selected_artifacts,
        "options": payload.get("options") or {},
        "preset": payload.get("preset"),
        "redaction_mode": payload.get("redaction_mode"),
    }
    try:
        metadata_bytes = len(json.dumps(metadata_seed, sort_keys=True).encode("utf-8"))
    except (TypeError, ValueError):
        metadata_bytes = 0
    metadata_bytes += 16 * 1024
    required_archive_bytes = (
        raw_artifact_bytes
        + redacted_artifact_bytes
        + transcript_html_bytes
        + metadata_bytes
    )
    estimated_uncompressed_bytes = required_archive_bytes + transcript_text_companion_bytes
    estimated_compressed_archive_bytes = (
        raw_artifact_bytes
        + _estimate_text_zip_bytes(redacted_artifact_bytes)
        + _estimate_text_zip_bytes(transcript_html_bytes)
        + _estimate_text_zip_bytes(metadata_bytes)
    )
    estimated_compressed_archive_bytes_with_optional_companions = (
        estimated_compressed_archive_bytes
        + _estimate_text_zip_bytes(transcript_text_companion_bytes)
    )
    return {
        "estimated_uncompressed_bytes": required_archive_bytes,
        "estimated_archive_bytes": required_archive_bytes,
        "estimated_uncompressed_bytes_with_optional_companions": estimated_uncompressed_bytes,
        "estimated_compressed_archive_bytes": estimated_compressed_archive_bytes,
        "estimated_compressed_archive_bytes_with_optional_companions": (
            estimated_compressed_archive_bytes_with_optional_companions
        ),
        "raw_artifact_bytes": raw_artifact_bytes,
        "redacted_artifact_bytes": redacted_artifact_bytes,
        "redacted_artifact_count_estimate": redacted_artifact_count_estimate,
        "transcript_html_bytes": transcript_html_bytes,
        "transcript_text_companion_bytes": transcript_text_companion_bytes,
        "metadata_bytes": metadata_bytes,
        "selected_run_count": len(selected_runs),
        "selected_transcript_count": len(transcript_runs),
        "selected_artifact_count": len(selected_artifacts),
        "skipped_artifact_count_estimate": skipped_artifact_count_estimate,
        "artifact_warnings": artifact_warnings,
        "max_archive_bytes": max_archive_bytes,
        "max_compressed_archive_bytes": max_archive_bytes,
        "max_uncompressed_archive_bytes": max_uncompressed_archive_bytes,
        "note": (
            "Best-guess pre-build estimate before ZIP compression; "
            "final download enforces ZIP, expanded-content, and drift checks."
        ),
    }


def package_manifest_without_private_notes(manifest):
    if not isinstance(manifest, dict):
        return manifest
    clean = dict(manifest)
    project = clean.get("project")
    if isinstance(project, dict):
        project = dict(project)
        project.pop("note", None)
        clean["project"] = project
    for key in ("runs", "findings", "targets", "artifacts"):
        items = clean.get(key)
        if not isinstance(items, list):
            continue
        cleaned_items = []
        for item in items:
            if not isinstance(item, dict):
                cleaned_items.append(item)
                continue
            next_item = {item_key: item_value for item_key, item_value in item.items() if item_key != "note"}
            if key == "findings" and isinstance(next_item.get("triage"), dict):
                triage = dict(next_item["triage"])
                triage.pop("verification_notes", None)
                next_item["triage"] = triage
            cleaned_items.append(next_item)
        clean[key] = cleaned_items
    return clean


def _selected_entity_counts(selected_entity_ids):
    return {
        key: len(value) if isinstance(value, list) else 0
        for key, value in selected_entity_ids.items()
    }


def _project_link_origin_summary(*item_groups):
    counts_by_origin = {}
    for items in item_groups:
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            provenance = item.get("provenance")
            if not isinstance(provenance, dict):
                continue
            origin = str(provenance.get("origin") or "").strip()
            if not origin:
                continue
            counts_by_origin[origin] = counts_by_origin.get(origin, 0) + 1
    return {
        "origin_sources": sorted(counts_by_origin),
        "counts_by_origin": {
            origin: counts_by_origin[origin]
            for origin in sorted(counts_by_origin)
        },
    }


def _evidence_package_provenance(
    payload,
    project_payload,
    selected_entity_ids,
    counts,
    output_options,
    *,
    selected_runs=None,
    selected_targets=None,
):
    return {
        "schema_version": EVIDENCE_PACKAGE_PROVENANCE_SCHEMA_VERSION,
        "kind": "evidence_package",
        "build": {
            "redaction_mode": payload["redaction_mode"],
            "include_private_notes": payload["include_private_notes"],
            "include_artifacts": payload["include_artifacts"],
            "preset": payload["preset"],
            "options": dict(output_options),
            "selected_entity_ids": dict(selected_entity_ids),
            "selected_entity_counts": _selected_entity_counts(selected_entity_ids),
            "included_entity_counts": dict(counts),
        },
        "sources": {
            "project": {
                "id": project_payload.get("id") or "",
                "name": project_payload.get("name") or "",
                "slug": project_payload.get("slug") or "",
            },
            "project_links": _project_link_origin_summary(selected_runs, selected_targets),
        },
        "privacy": {
            "redaction_mode": payload["redaction_mode"],
            "private_notes_included": payload["include_private_notes"],
        },
    }


def _legacy_evidence_package_provenance(manifest):
    selected_entity_ids = manifest.get("selected_entity_ids")
    if not isinstance(selected_entity_ids, dict):
        selected_entity_ids = {}
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        counts = {}
    project_payload = manifest.get("project")
    if not isinstance(project_payload, dict):
        project_payload = {}
    redaction_mode = str(manifest.get("redaction_mode") or "").strip().lower() or "unknown"
    return {
        "schema_version": EVIDENCE_PACKAGE_PROVENANCE_SCHEMA_VERSION,
        "kind": "evidence_package",
        "build": {
            "redaction_mode": redaction_mode,
            "include_private_notes": bool(manifest.get("include_private_notes")),
            "include_artifacts": bool(manifest.get("include_artifacts")),
            "preset": str(manifest.get("preset") or "custom"),
            "options": dict(manifest.get("options") or {}),
            "selected_entity_ids": dict(selected_entity_ids),
            "selected_entity_counts": _selected_entity_counts(selected_entity_ids),
            "included_entity_counts": dict(counts),
        },
        "sources": {
            "project": {
                "id": project_payload.get("id") or "",
                "name": project_payload.get("name") or "",
                "slug": project_payload.get("slug") or "",
            },
            "project_links": {
                "origin_sources": [],
                "note": "Project-link origin details were not recorded in this package format.",
            },
        },
        "privacy": {
            "redaction_mode": redaction_mode,
            "private_notes_included": bool(manifest.get("include_private_notes")),
        },
    }


def _legacy_evidence_package_import_hints(manifest):
    selected_entity_ids = manifest.get("selected_entity_ids")
    if not isinstance(selected_entity_ids, dict):
        selected_entity_ids = {}
    return {
        "schema_version": 1,
        "kind": "evidence_package_import_hints",
        "mode": "preview_only",
        "summary": {
            "package_metadata": "not_recorded",
            "source_links": "not_recorded",
            "target_relationships": "not_recorded",
            "labels": "not_recorded",
            "notes": "not_recorded",
            "finding_review_state": "not_recorded",
        },
        "selected_entity_ids": dict(selected_entity_ids),
        "warnings": [{
            "code": "legacy_manifest",
            "message": "Import hints were not recorded in this package format.",
        }],
    }


def normalize_evidence_package_manifest(manifest):
    if not isinstance(manifest, dict):
        return {}
    normalized = dict(manifest)
    try:
        package_format_version = int(normalized.get("package_format_version") or normalized.get("format") or 1)
    except (TypeError, ValueError):
        package_format_version = 1
    normalized["package_format_version"] = package_format_version
    normalized.setdefault("format", package_format_version)
    if not isinstance(normalized.get("provenance"), dict):
        normalized["provenance"] = _legacy_evidence_package_provenance(normalized)
    if not isinstance(normalized.get("import_hints"), dict):
        normalized["import_hints"] = _legacy_evidence_package_import_hints(normalized)
    return normalized


def _item_ids(items):
    return [
        str(item.get("id") or "")
        for item in items
        if isinstance(item, dict) and str(item.get("id") or "")
    ]


def _package_import_hint_warnings(
    payload,
    selected_runs,
    selected_artifacts,
    selected_findings,
):
    warnings = []
    if payload["redaction_mode"] == "redacted":
        warnings.append({
            "code": "redacted_package",
            "message": "Raw values were redacted before these import hints were written.",
        })
    if not payload["include_private_notes"]:
        warnings.append({
            "code": "private_notes_excluded",
            "message": "Private notes were excluded and cannot be recreated from this package.",
        })
    for artifact in selected_artifacts:
        if not isinstance(artifact, dict):
            continue
        status = str(artifact.get("file_status") or "available")
        if status == "available":
            continue
        warnings.append({
            "code": "artifact_not_available",
            "entity_type": "run_file_artifact",
            "entity_id": str(artifact.get("id") or ""),
            "status": status,
            "message": str(artifact.get("file_status_detail") or "Artifact file was not available."),
        })
    selected_run_ids = set(_item_ids(selected_runs))
    for finding in selected_findings:
        if not isinstance(finding, dict):
            continue
        references = finding.get("target_references")
        if not isinstance(references, list):
            continue
        for reference in references:
            if not isinstance(reference, dict):
                continue
            source_run_id = str(reference.get("source_run_id") or "")
            if source_run_id and source_run_id not in selected_run_ids:
                warnings.append({
                    "code": "source_run_not_selected",
                    "entity_type": "finding",
                    "entity_id": str(finding.get("id") or ""),
                    "source_run_id": source_run_id,
                    "message": "A target reference points to a source run that is not included in this package.",
                })
    return warnings


def _source_link_import_hints(selected_runs, selected_targets):
    hints = []
    for entity_type, items in (("run", selected_runs), ("atlas_entity", selected_targets)):
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_provenance = item.get("provenance")
            provenance = raw_provenance if isinstance(raw_provenance, dict) else {}
            hints.append({
                "entity_type": entity_type,
                "entity_id": str(item.get("id") or ""),
                "source": str(provenance.get("origin") or item.get("link_source") or item.get("source") or "manual"),
                "confidence": provenance.get("confidence", item.get("confidence", 1.0)),
                "review_state": str(provenance.get("review_state") or item.get("review_state") or "confirmed"),
            })
    return hints


def _target_relationship_import_hints(selected_findings):
    hints = []
    for finding in selected_findings:
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("id") or "")
        references = finding.get("target_references")
        if not isinstance(references, list):
            continue
        for reference in references:
            if not isinstance(reference, dict):
                continue
            hints.append({
                "finding_id": finding_id,
                "target_id": str(reference.get("target_id") or ""),
                "target_type": str(reference.get("type") or "target"),
                "source_run_id": str(reference.get("source_run_id") or ""),
                "relationship_source": str(reference.get("relationship_source") or ""),
                "confidence": reference.get("confidence", 1.0),
            })
    return hints


def _finding_review_import_hints(selected_findings):
    hints = []
    for finding in selected_findings:
        if not isinstance(finding, dict):
            continue
        raw_triage = finding.get("triage")
        triage = raw_triage if isinstance(raw_triage, dict) else {}
        hints.append({
            "finding_id": str(finding.get("id") or ""),
            "review_state": str(finding.get("review_state") or finding.get("status") or "new"),
            "verification_status": str(triage.get("verification_status") or finding.get("verification_status") or ""),
            "has_triage": bool(triage),
        })
    return hints


def _evidence_package_import_hints(
    payload,
    project_payload,
    selected_entity_ids,
    *,
    selected_runs,
    selected_findings,
    selected_artifacts,
    selected_targets,
):
    return {
        "schema_version": 1,
        "kind": "evidence_package_import_hints",
        "mode": "preview_only",
        "note": "These hints describe a future import preview. They are not applied by this release.",
        "package_metadata": {
            "project_id": project_payload.get("id") or "",
            "project_name": project_payload.get("name") or "",
            "preset": payload["preset"],
            "redaction_mode": payload["redaction_mode"],
            "include_private_notes": payload["include_private_notes"],
            "archive_paths": {
                "manifest": "manifest.json",
                "labels": "metadata/labels.json",
                "notes": "notes/entity-notes.json",
                "project_notes": "notes/project.md" if payload["include_private_notes"] and project_payload.get("note") else "",
            },
        },
        "selected_entity_ids": dict(selected_entity_ids),
        "source_links": _source_link_import_hints(selected_runs, selected_targets),
        "target_relationships": _target_relationship_import_hints(selected_findings),
        "labels": {
            "archive_path": "metadata/labels.json",
            "entity_types": ["project", "run", "finding", "target", "run_file_artifact", "package"],
        },
        "notes": {
            "included": payload["include_private_notes"],
            "archive_path": "notes/entity-notes.json",
            "project_archive_path": (
                "notes/project.md"
                if payload["include_private_notes"] and project_payload.get("note")
                else ""
            ),
        },
        "finding_review_state": _finding_review_import_hints(selected_findings),
        "warnings": _package_import_hint_warnings(payload, selected_runs, selected_artifacts, selected_findings),
    }


def evidence_manifest_from_summary(summary, payload, findings=None):
    findings = findings if isinstance(findings, list) else []
    selection = payload.get("selection")
    run_ids = normalized_package_selection_ids(
        selection,
        "run_ids",
        [item.get("id") for item in summary.get("runs", [])],
    )
    transcript_run_ids = normalized_package_selection_ids(
        selection,
        "transcript_run_ids",
        run_ids,
    ) if isinstance(selection, dict) and "transcript_run_ids" in selection else list(run_ids)
    finding_ids = normalized_package_selection_ids(
        selection,
        "finding_ids",
        [item.get("id") for item in findings],
    )
    artifact_ids = normalized_package_selection_ids(
        selection,
        "artifact_ids",
        [item.get("id") for item in summary.get("artifacts", [])],
    )
    target_ids = normalized_package_selection_ids(
        selection,
        "target_ids",
        [item.get("id") for item in summary.get("targets", [])],
    )
    selected_runs = _filter_package_items(summary.get("runs", []), run_ids)
    selected_findings = _filter_package_items(findings, finding_ids)
    selected_artifacts = _filter_package_items(summary.get("artifacts", []), artifact_ids)
    selected_targets = _filter_package_items(summary.get("targets", []), target_ids)
    attach_finding_target_references(selected_findings, summary.get("targets", []))
    include_raw_artifacts = bool(payload["include_artifacts"] and payload["redaction_mode"] != "redacted")
    include_redacted_artifact_derivatives = bool(
        payload["include_artifacts"] and payload["redaction_mode"] == "redacted"
    )
    output_options = {
        "manifest_json": True,
        "index_html": True,
        "transcripts_html": bool(transcript_run_ids),
        "raw_artifacts": include_raw_artifacts,
        "redacted_artifact_derivatives": include_redacted_artifact_derivatives,
    }
    artifact_warnings = (
        redacted_artifact_derivative_warnings(selected_artifacts)
        if include_redacted_artifact_derivatives else []
    )
    project_payload = {
        "id": summary["project"]["id"],
        "name": summary["project"]["name"],
        "slug": summary["project"]["slug"],
        "description": summary["project"].get("description", ""),
    }
    if payload["include_private_notes"] and summary["project"].get("note"):
        project_payload["note"] = summary["project"].get("note")
    selected_entity_ids = {
        "run_ids": run_ids,
        "transcript_run_ids": transcript_run_ids,
        "finding_ids": finding_ids,
        "artifact_ids": artifact_ids,
        "target_ids": target_ids,
    }
    counts = {
        "runs": len(selected_runs),
        "findings": len(selected_findings),
        "artifacts": len(selected_artifacts),
        "targets": len(selected_targets),
    }
    manifest = {
        "format": EVIDENCE_PACKAGE_FORMAT_VERSION,
        "package_format_version": payload["package_format_version"],
        "project": project_payload,
        "counts": counts,
        "project_counts": summary["counts"],
        "selected_entity_ids": selected_entity_ids,
        "preset": payload["preset"],
        "options": output_options,
        "estimated_archive": estimate_evidence_package_archive(
            selected_runs,
            selected_findings,
            selected_artifacts,
            selected_targets,
            {**payload, "options": output_options},
        ),
        "include_private_notes": payload["include_private_notes"],
        "links": summary["links"],
        "runs": selected_runs,
        "findings": selected_findings,
        "targets": selected_targets,
        "artifacts": selected_artifacts,
        "artifact_warnings": artifact_warnings,
        "redaction_mode": payload["redaction_mode"],
        "include_artifacts": payload["include_artifacts"],
        "provenance": _evidence_package_provenance(
            payload,
            project_payload,
            selected_entity_ids,
            counts,
            output_options,
            selected_runs=selected_runs,
            selected_targets=selected_targets,
        ),
        "import_hints": _evidence_package_import_hints(
            payload,
            project_payload,
            selected_entity_ids,
            selected_runs=selected_runs,
            selected_findings=selected_findings,
            selected_artifacts=selected_artifacts,
            selected_targets=selected_targets,
        ),
    }
    if not payload["include_private_notes"]:
        manifest = package_manifest_without_private_notes(manifest)
    return manifest


def package_archive_name(package):
    raw = str(package.get("name") or "evidence-package").strip().lower()
    safe = re.sub(r"[^a-z0-9._-]+", "-", raw).strip(".-")
    return f"{safe or 'evidence-package'}.zip"


def redact_package_value(value, rules):
    if isinstance(value, str):
        return apply_redaction_rules(value, rules)
    if isinstance(value, list):
        return [redact_package_value(item, rules) for item in value]
    if isinstance(value, dict):
        return {key: redact_package_value(item, rules) for key, item in value.items()}
    return value


def strip_target_reference_values(value):
    if isinstance(value, list):
        return [strip_target_reference_values(item) for item in value]
    if not isinstance(value, dict):
        return value
    stripped = {}
    for key, item in value.items():
        if key == "target_references" and isinstance(item, list):
            stripped[key] = [
                {
                    ref_key: strip_target_reference_values(ref_value)
                    for ref_key, ref_value in reference.items()
                    if ref_key != "value"
                }
                if isinstance(reference, dict)
                else strip_target_reference_values(reference)
                for reference in item
            ]
        else:
            stripped[key] = strip_target_reference_values(item)
    return stripped


def package_redaction_rules(redaction_mode, *, cfg=None):
    if redaction_mode != "redacted":
        return []
    return _config.get_share_redaction_rules(cfg)


def redact_package_manifest(manifest, rules):
    if not rules:
        return dict(manifest or {})
    stripped = strip_target_reference_values(manifest or {})
    redacted = redact_package_value(stripped, rules)
    return redacted if isinstance(redacted, dict) else {}


def redact_package_run(run, rules):
    if not rules:
        return dict(run or {})
    redacted = redact_package_value(run or {}, rules)
    return redacted if isinstance(redacted, dict) else {}
