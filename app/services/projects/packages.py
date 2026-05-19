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


def row_to_evidence_package(row):
    if not row:
        return None
    try:
        manifest = dialect_for_backend(DB_BACKEND).decode_json_dict(row["manifest"])
    except (TypeError, ValueError):
        manifest = {}
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "description": row["description"] or "",
        "redaction_mode": row["redaction_mode"],
        "include_artifacts": bool(row["include_artifacts"]),
        "manifest": manifest if isinstance(manifest, dict) else {},
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
    return {
        "name": name,
        "description": _trim_text(data.get("description"), MAX_PACKAGE_DESCRIPTION_LEN),
        "redaction_mode": redaction_mode,
        "include_artifacts": include_artifacts,
        "preset": _trim_text(data.get("preset"), 32).lower() or "custom",
        "package_format_version": 1,
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
        clean[key] = [
            {item_key: item_value for item_key, item_value in item.items() if item_key != "note"}
            if isinstance(item, dict) else item
            for item in items
        ]
    return clean


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
    manifest = {
        "format": 1,
        "package_format_version": payload["package_format_version"],
        "project": project_payload,
        "counts": {
            "runs": len(selected_runs),
            "findings": len(selected_findings),
            "artifacts": len(selected_artifacts),
            "targets": len(selected_targets),
        },
        "project_counts": summary["counts"],
        "selected_entity_ids": {
            "run_ids": run_ids,
            "transcript_run_ids": transcript_run_ids,
            "finding_ids": finding_ids,
            "artifact_ids": artifact_ids,
            "target_ids": target_ids,
        },
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


def package_redaction_rules(redaction_mode, *, cfg=None):
    if redaction_mode != "redacted":
        return []
    return _config.get_share_redaction_rules(cfg)


def redact_package_manifest(manifest, rules):
    if not rules:
        return dict(manifest or {})
    redacted = redact_package_value(manifest or {}, rules)
    return redacted if isinstance(redacted, dict) else {}


def redact_package_run(run, rules):
    if not rules:
        return dict(run or {})
    redacted = redact_package_value(run or {}, rules)
    return redacted if isinstance(redacted, dict) else {}
