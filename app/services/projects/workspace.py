"""
Session-scoped project workspace helpers.
"""

from __future__ import annotations

import hashlib
import html
import gzip
import ipaddress
import json
import os
import re
import secrets
import shlex
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlparse

import config as _config
import services.runs.comparison as run_comparison
from core.database import (
    DB_BACKEND,
    db_connect,
    validate_project_entity_type,
    validate_project_link_source,
)
from core.database_backend import dialect_for_backend
from core.output_signals import strip_ansi_codes
from services.atlas.materializer import (
    canonicalize_entity_record,
    upsert_entity,
)
from services.history.permalinks import _font_face_css, _format_duration, _permalink_context
from services.intel.canonical import CanonicalizationError, canonical_entity, entity_signature
from services.projects.contracts import (
    ACTIVE_PROJECT_PREF_KEY,
    EvidencePackageTooLarge,
    FINDING_REVIEW_STATES,
    MAX_BULK_RUN_ACTION_ITEMS,
    MAX_ENTITY_ID_LEN,
    MAX_ENTITY_NOTE_BODY_LEN,
    MAX_FINDING_TITLE_LEN,
    MAX_LABEL_LEN,
    MAX_PACKAGE_DESCRIPTION_LEN,
    MAX_PACKAGE_NAME_LEN,
    MAX_PROJECT_COLOR_LEN,
    MAX_PROJECT_DESCRIPTION_LEN,
    MAX_PROJECT_NAME_LEN,
    MAX_PROJECT_NOTES_LEN,
    MAX_PROJECT_TARGET_DISCOVERY_FILE_BYTES,
    MAX_PROJECT_TARGET_DISCOVERY_FILE_LINES,
    MAX_PROJECT_TARGET_DISCOVERY_PER_RUN,
    MAX_TARGET_VALUE_LEN,
    PROJECT_LINK_ENTITY_TYPES,
    PROJECT_STATUSES,
    PROJECT_TARGET_REVIEW_STATES,
    PROJECT_TARGET_SOURCES,
    PROJECT_TARGET_TYPES,
    ProjectWorkspaceError,
    ProjectWorkspaceNotFound,
    ProjectWorkspaceQuotaExceeded,
)
from services.projects.metadata import (
    _attach_package_metadata,
    _attach_project_labels,
    _attach_project_notes,
    _attach_target_metadata,
    _count_entity_metadata_for_ids,
    _entity_labels_by_id,
    _entity_notes_by_id,
    _save_project_note,
)
from services.projects import metadata as project_metadata
from services.projects.preferences import (
    clear_active_project_preference as _clear_active_project_preference,
    load_session_preferences as _load_session_preferences,
    migrate_active_project_preference as _migrate_active_project_preference,
    project_auto_link_external_runs_enabled as _project_auto_link_external_runs_enabled,
    project_auto_link_run_entities_enabled as _project_auto_link_run_entities_enabled,
    save_session_preferences as _save_session_preferences,
)
from core.redaction import apply_redaction_rules, redact_line_entries
from services.runs.kinds import RUN_KIND_EXTERNAL, is_project_linkable_run_kind, normalize_run_kind
from services.runs.output_store import load_full_output_entries
from services.workspace.files import (
    WorkspaceDisabled,
    WorkspaceError,
    open_workspace_file_for_download,
    read_workspace_text_file,
    resolve_workspace_path,
)

MAX_PROJECT_COMPARE_ITEMS_PER_SIDE = run_comparison.MAX_COMPARE_ITEMS_PER_SIDE

list_entity_labels = project_metadata.list_entity_labels
add_entity_label = project_metadata.add_entity_label
delete_entity_label = project_metadata.delete_entity_label
entity_metadata_target_exists = project_metadata.entity_metadata_target_exists
get_entity_note = project_metadata.get_entity_note
upsert_entity_note = project_metadata.upsert_entity_note
delete_entity_note = project_metadata.delete_entity_note

_URL_RE = re.compile(r"https?://[^\s<>'\"`]+", re.I)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b",
    re.I,
)


def _cfg_int(key, default, *, cfg=None):
    if cfg is None:
        from config import CFG
        cfg = CFG
    try:
        value = int(cfg.get(key, default))
    except (AttributeError, TypeError, ValueError):
        value = default
    return max(0, value)


def _cfg_mb_bytes(key, default_mb, *, cfg=None):
    return _cfg_int(key, default_mb, cfg=cfg) * 1024 * 1024


def _quota_exceeded(count, key, default):
    limit = _cfg_int(key, default)
    return limit > 0 and count >= limit


def _raise_quota(message):
    raise ProjectWorkspaceQuotaExceeded(message)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _new_project_id() -> str:
    return "prj_" + secrets.token_hex(8)


def _new_project_link_id() -> str:
    return "pln_" + secrets.token_hex(8)


def _new_run_file_artifact_id() -> str:
    return "rfa_" + secrets.token_hex(8)


def _new_entity_label_id() -> str:
    return "lbl_" + secrets.token_hex(8)


def _new_entity_note_id() -> str:
    return "note_" + secrets.token_hex(8)


def _new_project_target_id() -> str:
    return "tgt_" + secrets.token_hex(8)


def _new_finding_id() -> str:
    return "fnd_" + secrets.token_hex(8)


def _new_finding_target_id() -> str:
    return "fnt_" + secrets.token_hex(8)


def _new_evidence_package_id() -> str:
    return "pkg_" + secrets.token_hex(8)


def _trim_text(value, limit):
    return str(value or "").strip()[:limit]


def _text_exceeds_limit(value, limit):
    return len(str(value or "").strip()) > limit


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return (slug or "project")[:80].strip("-") or "project"


def _row_to_project(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"] or "",
        "status": row["status"],
        "color": row["color"] or "",
        "created": row["created"],
        "updated": row["updated"],
    }


def _row_to_project_run(row):
    if not row:
        return None
    item = {
        "id": row["id"],
        "command": row["command"],
        "started": row["started"],
        "finished": row["finished"],
        "exit_code": row["exit_code"],
        "output_line_count": row["output_line_count"],
        "created": row["created"],
        "link_source": row["link_source"],
    }
    keys = row.keys()
    if "finding_count" in keys:
        item["finding_count"] = int(row["finding_count"] or 0)
    if "artifact_count" in keys:
        item["artifact_count"] = int(row["artifact_count"] or 0)
    return item


def _row_to_link(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "source": row["source"],
        "created": row["created"],
    }


def _entity_note_body(entity):
    note = entity.get("note") if isinstance(entity, dict) else None
    if not isinstance(note, dict):
        return ""
    return str(note.get("body") or "").strip()


def _row_to_target(row):
    if not row:
        return None
    if "canonical_value" in row.keys():
        source_detail = (
            dialect_for_backend(DB_BACKEND).decode_json_dict(row["source_detail"])
            if "source_detail" in row.keys()
            else {}
        )
        return {
            "id": row["id"],
            "project_id": row["project_id"] if "project_id" in row.keys() else "",
            "type": row["type"],
            "value": row["canonical_value"],
            "canonical_value": row["canonical_value"],
            "source_run_id": row["source_run_id"] if "source_run_id" in row.keys() else "",
            "confidence": row["confidence"] if "confidence" in row.keys() else 1.0,
            "review_state": row["review_state"] if "review_state" in row.keys() else "confirmed",
            "status": row["review_state"] if "review_state" in row.keys() else "confirmed",
            "source": "user" if ("source" not in row.keys() or row["source"] == "manual") else row["source"],
            "source_detail": source_detail,
            "seen_count": max(1, int(row["occurrence_count"] or 0)),
            "occurrence_count": int(row["occurrence_count"] or 0),
            "run_count": int(row["run_count"] or 0) if "run_count" in row.keys() else 0,
            "intel_provider_count": int(row["intel_provider_count"] or 0)
            if "intel_provider_count" in row.keys() else 0,
            "intel_providers": [
                provider.strip()
                for provider in str(row["intel_providers"] or "").split(",")
                if provider.strip()
            ] if "intel_providers" in row.keys() else [],
            "intel_last_refreshed": row["intel_last_refreshed"] if "intel_last_refreshed" in row.keys() else "",
            "last_seen": row["last_seen_at"] or "",
            "dismissed_at": "",
            "created": row["created"],
            "updated": row["updated"] if "updated" in row.keys() else row["last_seen_at"] or row["created"],
        }
    source_detail = dialect_for_backend(DB_BACKEND).decode_json_dict(row["source_detail"])
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "type": row["type"],
        "value": row["value"],
        "source_run_id": row["source_run_id"],
        "confidence": row["confidence"],
        "review_state": row["review_state"],
        "source": row["source"],
        "source_detail": source_detail if isinstance(source_detail, dict) else {},
        "seen_count": int(row["seen_count"] or 0),
        "last_seen": row["last_seen"] or "",
        "dismissed_at": row["dismissed_at"] or "",
        "created": row["created"],
        "updated": row["updated"],
    }


def _row_to_run_file_artifact(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "run_id": row["run_id"],
        "workspace_path": row["workspace_path"],
        "display_name": row["display_name"],
        "kind": row["kind"],
        "byte_size": row["byte_size"],
        "detected_by": row["detected_by"],
        "content_type": row["content_type"],
        "preview_type": row["preview_type"],
        "content_sha256": row["content_sha256"],
        "created": row["created"],
    }


def _normalize_sha256(value):
    candidate = _trim_text(value, 128).lower()
    return candidate if re.fullmatch(r"[0-9a-f]{64}", candidate) else ""


def _workspace_file_sha256(session_id, workspace_path):
    try:
        with open_workspace_file_for_download(session_id, workspace_path) as handle:
            digest = hashlib.sha256()
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            return digest.hexdigest()
    except (OSError, WorkspaceError):
        return ""


def _path_sha256(path):
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _artifact_availability(session_id, artifact):
    workspace_path = _trim_text((artifact or {}).get("workspace_path"), MAX_ENTITY_ID_LEN)
    result = {
        "file_status": "missing",
        "file_available": False,
        "current_byte_size": None,
        "file_status_detail": "workspace file is not available",
    }
    if not workspace_path:
        result["file_status_detail"] = "workspace path is missing"
        return result
    try:
        resolved = resolve_workspace_path(session_id, workspace_path)
        if not resolved.is_file():
            return result
        current_size = max(0, int(resolved.stat().st_size))
    except WorkspaceDisabled as exc:
        return {
            "file_status": "disabled",
            "file_available": False,
            "current_byte_size": None,
            "file_status_detail": str(exc),
        }
    except (OSError, WorkspaceError):
        return result
    try:
        recorded_size = max(0, int((artifact or {}).get("byte_size") or 0))
    except (TypeError, ValueError):
        recorded_size = 0
    if current_size != recorded_size:
        return {
            "file_status": "changed",
            "file_available": True,
            "current_byte_size": current_size,
            "file_status_detail": "workspace file size differs from the recorded artifact",
        }
    recorded_hash = _normalize_sha256((artifact or {}).get("content_sha256"))
    if recorded_hash:
        current_hash = _workspace_file_sha256(session_id, workspace_path)
        if current_hash and current_hash != recorded_hash:
            return {
                "file_status": "changed",
                "file_available": True,
                "current_byte_size": current_size,
                "file_status_detail": "workspace file checksum differs from the recorded artifact",
            }
    return {
        "file_status": "available",
        "file_available": True,
        "current_byte_size": current_size,
        "file_status_detail": "",
    }


def _artifact_snapshot_mismatch_reason(artifact, resolved):
    try:
        current_size = max(0, int(resolved.stat().st_size))
    except OSError:
        return "artifact file is not available"
    try:
        recorded_size = max(0, int((artifact or {}).get("byte_size") or 0))
    except (TypeError, ValueError):
        recorded_size = 0
    if current_size != recorded_size:
        return "artifact changed since package creation: workspace file size differs from the recorded artifact"
    recorded_hash = _normalize_sha256((artifact or {}).get("content_sha256"))
    if recorded_hash:
        current_hash = _path_sha256(resolved)
        if current_hash and current_hash != recorded_hash:
            return "artifact changed since package creation: workspace file checksum differs from the recorded artifact"
    return ""


def _row_to_finding(row):
    if not row:
        return None
    if "last_run_id" in row.keys():
        run_id = row["run_id"] if "run_id" in row.keys() else row["last_run_id"]
        line_number = row["line_number"] if "line_number" in row.keys() else None
        snippet = row["snippet"] if "snippet" in row.keys() else row["raw_line"]
        target_id = row["entity_id"] or (row["target_id"] if "target_id" in row.keys() else "")
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "run_id": run_id or row["last_run_id"],
            "target_id": target_id,
            "entity_id": target_id,
            "subject_key": row["subject_key"] or "",
            "scope": row["kind"] or "finding",
            "kind": row["kind"] or "finding",
            "title": row["title"],
            "raw_line": snippet or row["raw_line"],
            "line_number": line_number,
            "severity": row["severity"],
            "fingerprint": row["fingerprint"],
            "review_state": row["status"],
            "status": row["status"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "occurrence_count": int(row["occurrence_count"] or 0),
            "created": row["created"],
        }
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "run_id": row["run_id"],
        "target_id": row["target_id"],
        "scope": row["scope"],
        "title": row["title"],
        "raw_line": row["raw_line"],
        "line_number": row["line_number"],
        "severity": row["severity"],
        "fingerprint": row["fingerprint"],
        "review_state": row["review_state"],
        "created": row["created"],
    }


def _command_root(value):
    try:
        parts = shlex.split(str(value or ""))
    except ValueError:
        parts = str(value or "").split()
    return parts[0] if parts else ""


def _finding_target_ids_from_row(row, relationship_target_ids=None, allowed_target_ids=None):
    result = []
    persisted_ids = [
        str(target_id or "")
        for target_id in (relationship_target_ids if isinstance(relationship_target_ids, list) else [])
        if str(target_id or "")
    ]
    allowed_ids = {str(target_id or "") for target_id in allowed_target_ids} if allowed_target_ids is not None else None

    def can_include(target_id):
        return bool(target_id) and (allowed_ids is None or target_id in allowed_ids)

    def add(target_id):
        normalized = str(target_id or "")
        if can_include(normalized) and normalized not in result:
            result.append(normalized)

    primary = str(row["target_id"] or "") if row and "target_id" in row.keys() else ""
    if not persisted_ids or primary in persisted_ids:
        add(primary)
    for target_id in persisted_ids:
        add(target_id)
    return result


def _row_to_project_finding(row, target_ids=None, allowed_target_ids=None):
    finding = _row_to_finding(row)
    if not finding:
        return None
    finding["target_ids"] = _finding_target_ids_from_row(row, target_ids, allowed_target_ids)
    finding["run_command"] = row["run_command"] or ""
    finding["command_root"] = _command_root(row["run_command"])
    if "source_run_exists" in row.keys():
        finding["source_run_exists"] = bool(row["source_run_exists"])
        finding["orphan_source"] = not bool(row["source_run_exists"])
    return finding


def _row_to_evidence_package(row):
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


def _normalize_project_payload(data, *, partial=False):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("project payload must be an object")
    clean = {}
    if "name" in data or not partial:
        name = _trim_text(data.get("name"), MAX_PROJECT_NAME_LEN)
        if not name:
            raise ProjectWorkspaceError("project name is required")
        clean["name"] = name
    if "description" in data or not partial:
        clean["description"] = _trim_text(data.get("description"), MAX_PROJECT_DESCRIPTION_LEN)
    if "color" in data or not partial:
        clean["color"] = _trim_text(data.get("color"), MAX_PROJECT_COLOR_LEN)
    if "notes" in data:
        clean["notes"] = _trim_text(data.get("notes"), MAX_PROJECT_NOTES_LEN)
    if "status" in data:
        status = _trim_text(data.get("status"), 32).lower()
        if status not in PROJECT_STATUSES:
            raise ProjectWorkspaceError("project status must be active or archived")
        clean["status"] = status
    return clean


def _normalize_evidence_package_payload(data):
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
    if redaction_mode == "redacted" or not bool(_config.CFG.get("workspace_enabled", False)):
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


def _normalized_package_selection_ids(selection, key, allowed_ids):
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


def _estimate_evidence_package_archive(selected_runs, selected_findings, selected_artifacts, selected_targets, payload):
    max_lines = _cfg_int("max_output_lines", 5000) or 5000
    max_archive_bytes = _cfg_mb_bytes("evidence_package_max_mb", 25)
    raw_artifacts_enabled = bool(payload.get("include_artifacts"))
    raw_artifact_bytes = 0
    skipped_artifact_count_estimate = 0
    if raw_artifacts_enabled:
        for artifact in selected_artifacts:
            status = str((artifact or {}).get("file_status") or "available")
            if status != "available":
                skipped_artifact_count_estimate += 1
                continue
            try:
                raw_artifact_bytes += max(0, int((artifact or {}).get("byte_size") or 0))
            except (TypeError, ValueError):
                skipped_artifact_count_estimate += 1

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
        transcript_html_bytes += 4096 + min(line_count, max_lines) * 120
        if line_count > max_lines:
            transcript_text_companion_bytes += line_count * 96

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
    estimated_uncompressed_bytes = (
        raw_artifact_bytes
        + transcript_html_bytes
        + transcript_text_companion_bytes
        + metadata_bytes
    )
    return {
        "estimated_uncompressed_bytes": estimated_uncompressed_bytes,
        "estimated_archive_bytes": estimated_uncompressed_bytes,
        "raw_artifact_bytes": raw_artifact_bytes,
        "transcript_html_bytes": transcript_html_bytes,
        "transcript_text_companion_bytes": transcript_text_companion_bytes,
        "metadata_bytes": metadata_bytes,
        "selected_run_count": len(selected_runs),
        "selected_transcript_count": len(transcript_runs),
        "selected_artifact_count": len(selected_artifacts),
        "skipped_artifact_count_estimate": skipped_artifact_count_estimate,
        "max_archive_bytes": max_archive_bytes,
        "note": "Pre-build estimate before ZIP compression; final download enforces archive caps and drift checks.",
    }


def _package_manifest_without_private_notes(manifest):
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


def _evidence_manifest_from_summary(summary, payload, findings=None):
    findings = findings if isinstance(findings, list) else []
    selection = payload.get("selection")
    run_ids = _normalized_package_selection_ids(
        selection,
        "run_ids",
        [item.get("id") for item in summary.get("runs", [])],
    )
    transcript_run_ids = _normalized_package_selection_ids(
        selection,
        "transcript_run_ids",
        run_ids,
    ) if isinstance(selection, dict) and "transcript_run_ids" in selection else list(run_ids)
    finding_ids = _normalized_package_selection_ids(
        selection,
        "finding_ids",
        [item.get("id") for item in findings],
    )
    artifact_ids = _normalized_package_selection_ids(
        selection,
        "artifact_ids",
        [item.get("id") for item in summary.get("artifacts", [])],
    )
    target_ids = _normalized_package_selection_ids(
        selection,
        "target_ids",
        [item.get("id") for item in summary.get("targets", [])],
    )
    selected_runs = _filter_package_items(summary.get("runs", []), run_ids)
    selected_findings = _filter_package_items(findings, finding_ids)
    selected_artifacts = _filter_package_items(summary.get("artifacts", []), artifact_ids)
    selected_targets = _filter_package_items(summary.get("targets", []), target_ids)
    output_options = {
        "manifest_json": True,
        "index_html": True,
        "transcripts_html": bool(transcript_run_ids),
        "raw_artifacts": bool(payload["include_artifacts"]),
    }
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
        "estimated_archive": _estimate_evidence_package_archive(
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
        "redaction_mode": payload["redaction_mode"],
        "include_artifacts": payload["include_artifacts"],
    }
    if not payload["include_private_notes"]:
        manifest = _package_manifest_without_private_notes(manifest)
    return manifest


def _package_archive_name(package):
    raw = str(package.get("name") or "evidence-package").strip().lower()
    safe = re.sub(r"[^a-z0-9._-]+", "-", raw).strip(".-")
    return f"{safe or 'evidence-package'}.zip"


def _package_zip_artifact_path(workspace_path, used_paths):
    parts = [
        part for part in PurePosixPath(str(workspace_path or "").replace("\\", "/")).parts
        if part not in {"", ".", ".."}
    ]
    relative = "/".join(parts) or "artifact"
    candidate = f"artifacts/{relative}"
    if candidate not in used_paths:
        used_paths.add(candidate)
        return candidate
    stem = PurePosixPath(relative).stem or "artifact"
    suffix = PurePosixPath(relative).suffix
    parent = str(PurePosixPath(relative).parent)
    prefix = "" if parent in {"", "."} else f"{parent}/"
    for index in range(2, 1000):
        candidate = f"artifacts/{prefix}{stem}-{index}{suffix}"
        if candidate not in used_paths:
            used_paths.add(candidate)
            return candidate
    raise ProjectWorkspaceError("could not allocate artifact package path")


def _package_html_escape(value):
    return html.escape("" if value is None else str(value), quote=True)


def _package_short_id(value):
    text = str(value or "")
    return text[:12] if len(text) > 12 else text


def _package_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _package_markdown_text(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ").strip()
    return re.sub(r"([\\`*_{}\[\]<>()#+!|])", r"\\\1", text)


def _package_markdown_code(value):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ").strip()
    if not text:
        return "``"
    text = text.replace("|", "\\|")
    longest_tick = max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)
    fence = "`" * (longest_tick + 1)
    return f"{fence}{text}{fence}" if longest_tick == 0 else f"{fence} {text} {fence}"


def _package_markdown_link(label, href):
    safe_label = _package_markdown_text(label) or "link"
    safe_href = str(href or "").replace(")", "%29").replace(" ", "%20")
    return f"[{safe_label}]({safe_href})" if safe_href else safe_label


def _redact_package_value(value, rules):
    if isinstance(value, str):
        return apply_redaction_rules(value, rules)
    if isinstance(value, list):
        return [_redact_package_value(item, rules) for item in value]
    if isinstance(value, dict):
        return {key: _redact_package_value(item, rules) for key, item in value.items()}
    return value


def _package_redaction_rules(redaction_mode, *, cfg=None):
    if redaction_mode != "redacted":
        return []
    return _config.get_share_redaction_rules(cfg)


def _redact_package_manifest(manifest, rules):
    if not rules:
        return dict(manifest or {})
    redacted = _redact_package_value(manifest or {}, rules)
    return redacted if isinstance(redacted, dict) else {}


def _redact_package_run(run, rules):
    if not rules:
        return dict(run or {})
    redacted = _redact_package_value(run or {}, rules)
    return redacted if isinstance(redacted, dict) else {}


def _package_output_entry(item) -> dict[str, object]:
    if isinstance(item, dict) and isinstance(item.get("text"), str):
        entry = {
            "text": item["text"],
            "cls": str(item.get("cls", "")),
            "tsC": str(item.get("tsC", "")),
            "tsE": str(item.get("tsE", "")),
        }
        if isinstance(item.get("signals"), list):
            entry["signals"] = [str(signal) for signal in item["signals"] if str(signal)]
        if isinstance(item.get("line_index"), int):
            entry["line_index"] = item["line_index"]
        if isinstance(item.get("command_root"), str):
            entry["command_root"] = item["command_root"]
        if isinstance(item.get("target"), str):
            entry["target"] = item["target"]
        return entry
    return {"text": str(item or ""), "cls": "", "tsC": "", "tsE": ""}


def _package_preview_output_entries(run) -> list[dict[str, object]]:
    raw = run.get("output_preview")
    if raw is None:
        raw = run.get("output")
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except (TypeError, ValueError):
        return [{"text": line, "cls": "", "tsC": "", "tsE": ""} for line in str(raw).splitlines()]
    if not isinstance(loaded, list):
        return [{"text": str(loaded), "cls": "", "tsC": "", "tsE": ""}]
    return [_package_output_entry(item) for item in loaded]


def _package_run_rows(conn, session_id, run_ids):
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT r.*, art.rel_path "  # nosec
        "FROM runs r LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
        f"WHERE r.session_id = ? AND r.id IN ({placeholders})",
        [session_id, *ids],
    ).fetchall()
    by_id = {str(row["id"]): dict(row) for row in rows}
    return [by_id[run_id] for run_id in ids if run_id in by_id]


def _package_run_output_entries(run, *, cfg=None, include_companion=False):
    if run.get("full_output_available") and run.get("rel_path"):
        try:
            entries = load_full_output_entries(str(run["rel_path"]))
        except (OSError, gzip.BadGzipFile, EOFError, ValueError):
            entries = _package_preview_output_entries(run)
        if run.get("full_output_truncated"):
            entries.append({
                "text": "[full output truncated by the server-side capture limit]",
                "cls": "warn",
                "tsC": "",
                "tsE": "",
            })
    else:
        entries = _package_preview_output_entries(run)
        if run.get("preview_truncated"):
            entries.append({
                "text": "[preview truncated; full output was not available for this package export]",
                "cls": "warn",
                "tsC": "",
                "tsE": "",
            })

    max_lines = _cfg_int("max_output_lines", 5000, cfg=cfg) or 5000
    if len(entries) > max_lines:
        hidden = len(entries) - max_lines
        companion_entries = list(entries)
        capped_entries: list[dict[str, object]] = list(entries[:max_lines])
        cap_notice: dict[str, object] = {
            "text": f"[package transcript capped at {max_lines} lines; {hidden} additional lines omitted]",
            "cls": "warn",
            "tsC": "",
            "tsE": "",
        }
        capped_entries.append(cap_notice)
        if include_companion:
            return capped_entries, companion_entries, cap_notice
        return capped_entries
    if include_companion:
        return entries, [], None
    return entries


def _package_run_text_bytes(entries, redaction_rules=None):
    entries = redact_line_entries(entries, redaction_rules) if redaction_rules else entries
    lines = []
    for entry in entries:
        if isinstance(entry, dict):
            lines.append(str(entry.get("text") or ""))
        else:
            lines.append(str(entry or ""))
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _package_css():
    return (
        "/* darklab shell evidence package CSS snapshot: package_format_version=1 */\n"
        + _font_face_css(embed=True)
        + "\n"
        + """
:root {
  color-scheme: dark;
  --bg: #0f1215;
  --panel: #171c20;
  --panel-2: #20272d;
  --text: #e6edf3;
  --muted: #9da9b5;
  --accent: #54d18a;
  --border: #303a43;
  --danger: #ff7b72;
  --warn: #f2c94c;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.5;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.page { width: min(1180px, calc(100vw - 32px)); margin: 0 auto; padding: 32px 0 48px; }
.topline { color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.08em; }
h1, h2, h3 { margin: 0; line-height: 1.2; }
h1 { margin-top: 8px; font-size: clamp(2rem, 5vw, 3.7rem); }
h2 { margin: 32px 0 12px; font-size: 1.15rem; }
.subtitle { max-width: 780px; margin: 12px 0 0; color: var(--muted); }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); margin-top: 24px; }
.metric, .card, .transcript {
  border: 1px solid var(--border);
  background: var(--panel);
  border-radius: 8px;
}
.metric { padding: 14px; }
.metric strong { display: block; font-size: 1.6rem; }
.metric span { color: var(--muted); font-size: 0.88rem; }
.card { padding: 16px; margin-top: 12px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-2);
  color: var(--text);
  font-size: 0.82rem;
  padding: 4px 9px;
}
table { width: 100%; border-collapse: collapse; overflow-wrap: anywhere; }
th, td { padding: 10px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
th { color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }
button.table-sort {
  appearance: none;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  cursor: pointer;
}
button.table-sort::after { content: " ↕"; color: var(--muted); }
button.table-sort[aria-sort="ascending"]::after { content: " ↑"; color: var(--accent); }
button.table-sort[aria-sort="descending"]::after { content: " ↓"; color: var(--accent); }
blockquote { margin: 8px 0 0; padding-left: 10px; border-left: 2px solid var(--border); color: var(--muted); }
.muted { color: var(--muted); }
.warn { color: var(--warn); }
.fail { color: var(--danger); }
.mono, .transcript {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}
.run-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
.run-list li { border: 1px solid var(--border); border-radius: 8px; padding: 12px; background: var(--panel); }
.run-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; color: var(--muted); font-size: 0.84rem; }
.transcript { padding: 16px; overflow: auto; white-space: pre-wrap; }
.line { min-height: 1.35em; }
.prompt-echo { color: var(--accent); }
.line.warn { color: var(--warn); }
.line:target { background: color-mix(in srgb, var(--accent) 18%, transparent); outline: 1px solid var(--accent); }
.footer { margin-top: 36px; color: var(--muted); font-size: 0.84rem; }
@media (max-width: 720px) {
  .page { width: min(100vw - 20px, 1180px); padding-top: 20px; }
  th:nth-child(4), td:nth-child(4) { display: none; }
}
""".strip()
    )


def _package_page(title, body, script="", *, css_href="assets/package.css"):
    css_tag = (
        f"<link rel=\"stylesheet\" href=\"{_package_html_escape(css_href)}\">\n"
        if css_href else f"<style>{_package_css()}</style>\n"
    )
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"darklab-package-format\" content=\"1\">\n"
        f"<title>{_package_html_escape(title)}</title>\n"
        f"{css_tag}"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        f"{script}\n"
        "</body>\n"
        "</html>\n"
    )


def _render_package_run_html(
    run,
    entries,
    manifest,
    generated_at,
    *,
    transcript_text_path="",
    redaction_rules=None,
):
    entries = redact_line_entries(entries, redaction_rules) if redaction_rules else entries
    run = _redact_package_run(run, redaction_rules)
    command = str(run.get("command") or "")
    started = str(run.get("started") or "")
    finished = str(run.get("finished") or "")
    duration = _format_duration(started, finished)
    output_line_count = run.get("output_line_count")
    line_count = output_line_count if isinstance(output_line_count, int) else len(entries)
    if isinstance(output_line_count, str) and output_line_count.isdecimal():
        line_count = int(output_line_count)
    meta = {
        "exit_code": run.get("exit_code"),
        "duration": duration,
        "lines": f"{line_count:,} lines",
        "artifact_count": run.get("artifact_count") or 0,
        "finding_count": run.get("finding_count") or 0,
        "label_count": run.get("label_count") or 0,
        "note_count": run.get("note_count") or 0,
    }
    permalink_model = _permalink_context(
        title=command or str(run.get("id") or "Run transcript"),
        label=command,
        created=started or generated_at,
        content_lines=entries,
        json_url="../manifest.json",
        extra_actions=[],
        meta=meta,
    )["page_model"]
    normalized = permalink_model["transcript"]["lines"]
    rendered_lines = []
    for index, entry in enumerate(normalized, start=1):
        text = _package_html_escape(entry.get("text", "") if isinstance(entry, dict) else entry)
        cls = str(entry.get("cls", "") if isinstance(entry, dict) else "")
        line_index = entry.get("line_index") if isinstance(entry, dict) else None
        anchor = f" id=\"L{line_index + 1}\"" if isinstance(line_index, int) else f" id=\"line-{index}\""
        cls_attr = f" line {_package_html_escape(cls)}".strip()
        rendered_lines.append(f"<div{anchor} class=\"{cls_attr}\">{text}</div>")
    if not rendered_lines:
        rendered_lines.append("<div class=\"line muted\">No output captured.</div>")

    header = permalink_model.get("header", {})
    raw_metric_items = header.get("runMetaItems") if isinstance(header, dict) else []
    metric_items = raw_metric_items if isinstance(raw_metric_items, list) else []
    metric_html = "".join(
        "<div class=\"metric\">"
        f"<span>{_package_html_escape(item.get('kind') or 'item')}</span>"
        f"<strong>{_package_html_escape(item.get('text') or '')}</strong>"
        "</div>"
        for item in metric_items
        if isinstance(item, dict)
    )
    if not metric_html:
        metric_html = "".join(
            "<div class=\"metric\">"
            f"<span>{_package_html_escape(label)}</span>"
            f"<strong>{_package_html_escape(value)}</strong>"
            "</div>"
            for label, value in [
                ("Started", started or "unknown"),
                ("Finished", finished or "unknown"),
                ("Duration", duration or "unknown"),
                ("Lines", line_count),
            ]
        )
    project_name = (
        manifest.get("project", {}).get("name", "Project")
        if isinstance(manifest.get("project"), dict)
        else "Project"
    )
    run_id_text = _package_html_escape(run.get("id"))
    transcript_text_link = (
        f"<p><a href=\"../{_package_html_escape(transcript_text_path)}\">"
        "Download full text transcript</a></p>"
        if transcript_text_path else ""
    )
    body = (
        "<main class=\"page\">"
        f"<a href=\"../index.html\">Back to package index</a>"
        f"<div class=\"topline\">{_package_html_escape(project_name)} evidence package</div>"
        f"<h1>{_package_html_escape(command or run.get('id'))}</h1>"
        f"<p class=\"subtitle mono\">Run {run_id_text} · generated {_package_html_escape(generated_at)}</p>"
        f"<section class=\"grid\">{metric_html}</section>"
        "<h2>Transcript</h2>"
        f"{transcript_text_link}"
        f"<section class=\"transcript\">{''.join(rendered_lines)}</section>"
        "<p class=\"footer\">Generated by darklab shell evidence packages.</p>"
        "</main>"
    )
    return _package_page(command or "Run transcript", body, css_href="../assets/package.css")


def _finding_run_anchor(finding):
    run_id = str(finding.get("run_id") or "")
    line_number = finding.get("line_number")
    if isinstance(line_number, int):
        return f"runs/{_package_html_escape(run_id)}.html#L{line_number + 1}"
    return f"runs/{_package_html_escape(run_id)}.html"


def _package_finding_metadata_html(finding):
    labels = finding.get("labels") if isinstance(finding.get("labels"), list) else []
    note = finding.get("note") if isinstance(finding.get("note"), dict) else None
    pieces = []
    if labels:
        label_html = "".join(
            f"<span class=\"chip\">{_package_html_escape(label.get('label') or '')}</span>"
            for label in labels
            if isinstance(label, dict)
        )
        pieces.append(f"<div class=\"chips\">{label_html}</div>")
    if note:
        pieces.append(
            "<blockquote>"
            f"{_package_html_escape(note.get('body') or '')}"
            "</blockquote>"
        )
    return "".join(pieces)


def _package_finding_metadata_markdown(finding):
    labels = finding.get("labels") if isinstance(finding.get("labels"), list) else []
    note = finding.get("note") if isinstance(finding.get("note"), dict) else None
    parts = []
    label_values = [
        _package_markdown_code(label.get("label") or "")
        for label in labels
        if isinstance(label, dict) and label.get("label")
    ]
    if label_values:
        parts.append("Labels: " + ", ".join(label_values))
    if note and note.get("body"):
        parts.append("Note: " + _package_markdown_text(note.get("body") or ""))
    return "<br>" + "<br>".join(parts) if parts else ""


def _package_index_sort_script():
    return """
<script>
(() => {
  const table = document.querySelector("[data-sort-table='findings']");
  if (!table) return;
  const body = table.querySelector("tbody");
  if (!body) return;
  const buttons = table.querySelectorAll("[data-sort-key]");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sortKey;
      const current = button.getAttribute("aria-sort");
      const direction = current === "ascending" ? "descending" : "ascending";
      buttons.forEach((item) => item.removeAttribute("aria-sort"));
      button.setAttribute("aria-sort", direction);
      const rows = Array.from(body.querySelectorAll("tr[data-finding-row]"));
      rows.sort((left, right) => {
        const leftValue = left.dataset[key] || "";
        const rightValue = right.dataset[key] || "";
        const result = leftValue.localeCompare(rightValue, undefined, { numeric: true, sensitivity: "base" });
        return direction === "ascending" ? result : -result;
      });
      rows.forEach((row) => body.appendChild(row));
    });
  });
})();
</script>
""".strip()


def _render_package_index_html(
    package,
    manifest,
    generated_at,
    run_pages,
    run_text_paths,
    artifact_paths,
    skipped_items,
):
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), list) else []
    runs = manifest.get("runs") if isinstance(manifest.get("runs"), list) else []
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []

    metric_html = "".join(
        "<div class=\"metric\">"
        f"<span>{_package_html_escape(label)}</span>"
        f"<strong>{_package_html_escape(counts.get(key, 0))}</strong>"
        "</div>"
        for key, label in (
            ("runs", "Runs"),
            ("findings", "Findings"),
            ("artifacts", "Artifacts"),
            ("targets", "Targets"),
        )
    )
    target_html = "".join(
        "<span class=\"chip\">"
        f"{_package_html_escape(target.get('type', 'target'))}: {_package_html_escape(target.get('value', ''))}"
        "</span>"
        for target in targets
        if isinstance(target, dict)
    ) or "<span class=\"muted\">No selected targets.</span>"
    project_notes = _entity_note_body(project)
    notes_html = (
        "<h2>Project Notes</h2>"
        f"<section class=\"card\"><p>{_package_html_escape(project_notes)}</p></section>"
        if project_notes else ""
    )

    run_html = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_id = str(run.get("id") or "")
        href = run_pages.get(run_id, "")
        text_href = run_text_paths.get(run_id, "")
        text_link = (
            f"<span>{_package_html_escape(run.get('output_line_count') or 0)} lines "
            f"· <a href=\"{_package_html_escape(text_href)}\">full text</a></span>"
            if text_href else
            f"<span>{_package_html_escape(run.get('output_line_count') or 0)} lines</span>"
        )
        run_html.append(
            "<li>"
            f"<a class=\"mono\" href=\"{_package_html_escape(href)}\">{_package_html_escape(run.get('command') or run_id)}</a>"
            "<div class=\"run-meta\">"
            f"<span>{_package_html_escape(run.get('started') or 'unknown start')}</span>"
            f"{text_link}"
            f"<span>{_package_html_escape(run.get('link_source') or 'manual')} link</span>"
            "</div>"
            "</li>"
        )
    if not run_html:
        run_html.append("<li class=\"muted\">No selected runs.</li>")

    finding_rows = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_run_id = str(finding.get("run_id") or "")
        finding_href = _finding_run_anchor(finding) if finding_run_id in run_pages else ""
        finding_label = _package_html_escape(finding.get("title") or finding.get("raw_line"))
        finding_link = f"<a href=\"{finding_href}\">{finding_label}</a>" if finding_href else finding_label
        finding_title = _package_html_escape(finding.get("title") or finding.get("raw_line") or "")
        finding_severity = _package_html_escape(finding.get("severity") or "info")
        finding_status = _package_html_escape(finding.get("review_state") or "new")
        finding_run = _package_html_escape(_package_short_id(finding.get("run_id")))
        finding_rows.append(
            "<tr data-finding-row "
            f"data-finding=\"{finding_title}\" "
            f"data-severity=\"{finding_severity}\" "
            f"data-status=\"{finding_status}\" "
            f"data-run=\"{finding_run}\">"
            f"<td>{finding_link}</td>"
            f"<td>{finding_severity}</td>"
            f"<td>{finding_status}</td>"
            f"<td class=\"mono\">{finding_run}</td>"
            f"<td class=\"mono\">{_package_html_escape(finding.get('raw_line') or '')}"
            f"{_package_finding_metadata_html(finding)}</td>"
            "</tr>"
        )
    if not finding_rows:
        finding_rows.append("<tr><td colspan=\"5\" class=\"muted\">No selected findings.</td></tr>")

    artifact_rows = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("id") or "")
        href = artifact_paths.get(artifact_id, "")
        name = artifact.get("display_name") or artifact.get("workspace_path") or artifact_id
        link = (
            f"<a href=\"{_package_html_escape(href)}\">{_package_html_escape(name)}</a>"
            if href else _package_html_escape(name)
        )
        artifact_rows.append(
            "<tr>"
            f"<td>{link}</td>"
            f"<td>{_package_html_escape(artifact.get('workspace_path') or '')}</td>"
            f"<td>{_package_html_escape(artifact.get('byte_size') or 0)}</td>"
            f"<td class=\"mono\">{_package_html_escape(_package_short_id(artifact.get('run_id')))}</td>"
            "</tr>"
        )
    if not artifact_rows:
        artifact_rows.append("<tr><td colspan=\"4\" class=\"muted\">No selected artifacts.</td></tr>")

    skipped_html = ""
    if skipped_items:
        skipped_rows = "".join(
            "<li>"
            f"<span class=\"chip\">{_package_html_escape(item.get('kind') or 'item')}</span> "
            "<span class=\"mono\">"
            f"{_package_html_escape(item.get('label') or item.get('workspace_path') or item.get('id'))}"
            "</span>"
            f" <span class=\"muted\">{_package_html_escape(item.get('reason') or 'skipped')}</span>"
            "</li>"
            for item in skipped_items
        )
        skipped_html = f"<h2>Skipped Items</h2><section class=\"card\"><ul>{skipped_rows}</ul></section>"

    export_links = [
        ("Manifest JSON", "manifest.json"),
        ("README Markdown", "README.md"),
        ("Findings JSON", "findings/findings.json"),
        ("Findings Markdown", "findings/findings.md"),
        ("Targets JSON", "targets/targets.json"),
        ("Targets Markdown", "targets/targets.md"),
        ("Labels JSON", "metadata/labels.json"),
        ("Entity Notes JSON", "notes/entity-notes.json"),
        ("Entity Notes Markdown", "notes/entity-notes.md"),
    ]
    if project_notes:
        export_links.append(("Project Notes Markdown", "notes/project.md"))
    if skipped_items:
        export_links.append(("Skipped items JSON", "skipped-items.json"))
    export_html = "".join(
        "<li>"
        f"<a href=\"{_package_html_escape(href)}\">{_package_html_escape(label)}</a>"
        "</li>"
        for label, href in export_links
    )

    body = (
        "<main class=\"page\">"
        "<div class=\"topline\">darklab shell evidence package</div>"
        f"<h1>{_package_html_escape(package.get('name') or 'Evidence package')}</h1>"
        f"<p class=\"subtitle\">"
        f"{_package_html_escape(project.get('name') or 'Project')} · generated {_package_html_escape(generated_at)}"
        "</p>"
        f"<section class=\"grid\">{metric_html}</section>"
        f"{notes_html}"
        "<h2>Targets</h2>"
        f"<section class=\"card chips\">{target_html}</section>"
        "<h2>Runs</h2>"
        f"<ul class=\"run-list\">{''.join(run_html)}</ul>"
        "<h2>Findings</h2>"
        "<section class=\"card\">"
        "<table data-sort-table=\"findings\"><thead><tr>"
        "<th><button class=\"table-sort\" type=\"button\" data-sort-key=\"finding\">Finding</button></th>"
        "<th><button class=\"table-sort\" type=\"button\" data-sort-key=\"severity\">Severity</button></th>"
        "<th><button class=\"table-sort\" type=\"button\" data-sort-key=\"status\">Status</button></th>"
        "<th><button class=\"table-sort\" type=\"button\" data-sort-key=\"run\">Run</button></th>"
        "<th>Evidence</th></tr></thead>"
        f"<tbody>{''.join(finding_rows)}</tbody></table>"
        "</section>"
        "<h2>Artifacts</h2>"
        "<section class=\"card\">"
        "<table><thead><tr><th>Artifact</th><th>Workspace path</th><th>Bytes</th><th>Run</th></tr></thead>"
        f"<tbody>{''.join(artifact_rows)}</tbody></table>"
        "</section>"
        "<h2>Package Exports</h2>"
        f"<section class=\"card\"><ul>{export_html}</ul></section>"
        f"{skipped_html}"
        "<p class=\"footer\">Generated by darklab shell evidence packages. Redaction mode is recorded in manifest.json.</p>"
        "</main>"
    )
    return _package_page(
        str(package.get("name") or "Evidence package"),
        body,
        _package_index_sort_script(),
    )


def _render_package_readme(
    package,
    manifest,
    generated_at,
    run_pages,
    run_text_paths,
    artifact_paths,
    skipped_items,
):
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), list) else []
    runs = manifest.get("runs") if isinstance(manifest.get("runs"), list) else []
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    lines = [
        f"# {_package_markdown_text(package.get('name') or 'Evidence package')}",
        "",
        f"- Project: {_package_markdown_text(project.get('name') or 'Project')}",
        f"- Generated: {_package_markdown_text(generated_at)}",
        f"- Preset: {_package_markdown_text(manifest.get('preset') or 'custom')}",
        f"- Redaction mode: {_package_markdown_text(manifest.get('redaction_mode') or 'raw')}",
        "",
        "## Counts",
        "",
        "| Type | Count |",
        "| --- | ---: |",
    ]
    for key, label in (("runs", "Runs"), ("findings", "Findings"), ("artifacts", "Artifacts"), ("targets", "Targets")):
        lines.append(f"| {label} | {_package_int(counts.get(key))} |")
    project_notes = _entity_note_body(project)
    if project_notes:
        lines.extend([
            "",
            "## Project Notes",
            "",
            _package_markdown_text(project_notes),
        ])
    lines.extend(["", "## Targets", ""])
    if targets:
        for target in targets:
            if isinstance(target, dict):
                lines.append(
                    f"- {_package_markdown_code(target.get('type') or 'target')} "
                    f"{_package_markdown_text(target.get('value') or '')}"
                )
    else:
        lines.append("- No selected targets.")
    lines.extend(["", "## Runs", ""])
    if runs:
        for run in runs:
            if not isinstance(run, dict):
                continue
            run_id = str(run.get("id") or "")
            label = run.get("command") or run_id
            lines.append(f"- {_package_markdown_link(label, run_pages.get(run_id, ''))}")
            lines.append(f"  - Started: {_package_markdown_text(run.get('started') or 'unknown')}")
            lines.append(f"  - Lines: {_package_int(run.get('output_line_count'))}")
            if run_text_paths.get(run_id):
                lines.append(f"  - Full text: {_package_markdown_link('transcript text', run_text_paths[run_id])}")
    else:
        lines.append("- No selected runs.")
    lines.extend(["", "## Findings", ""])
    if findings:
        lines.extend(["| Finding | Severity | Status | Run | Evidence |", "| --- | --- | --- | --- | --- |"])
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            run_id = str(finding.get("run_id") or "")
            href = _finding_run_anchor(finding) if run_id in run_pages else ""
            finding_label = finding.get("title") or finding.get("raw_line") or finding.get("id")
            lines.append(
                f"| {_package_markdown_link(finding_label, href)} "
                f"| {_package_markdown_text(finding.get('severity') or 'info')} "
                f"| {_package_markdown_text(finding.get('review_state') or 'new')} "
                f"| {_package_markdown_code(_package_short_id(run_id))} "
                f"| {_package_markdown_code(finding.get('raw_line') or '')}"
                f"{_package_finding_metadata_markdown(finding)} |"
            )
    else:
        lines.append("- No selected findings.")
    lines.extend(["", "## Artifacts", ""])
    if artifacts:
        lines.extend(["| Artifact | Workspace Path | Bytes | Run |", "| --- | --- | ---: | --- |"])
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_id = str(artifact.get("id") or "")
            name = artifact.get("display_name") or artifact.get("workspace_path") or artifact_id
            lines.append(
                f"| {_package_markdown_link(name, artifact_paths.get(artifact_id, ''))} "
                f"| {_package_markdown_code(artifact.get('workspace_path') or '')} "
                f"| {_package_int(artifact.get('byte_size'))} "
                f"| {_package_markdown_code(_package_short_id(artifact.get('run_id')))} |"
            )
    else:
        lines.append("- No selected artifacts.")
    lines.extend(["", "## Skipped Items", ""])
    if skipped_items:
        for item in skipped_items:
            label = item.get("label") or item.get("workspace_path") or item.get("id") or "item"
            lines.append(
                f"- {_package_markdown_code(item.get('kind') or 'item')} "
                f"{_package_markdown_text(label)}: {_package_markdown_text(item.get('reason') or 'skipped')}"
            )
    else:
        lines.append("- No skipped items.")
    lines.extend([
        "",
        "## Package Exports",
        "",
        f"- {_package_markdown_link('Manifest JSON', 'manifest.json')}",
        f"- {_package_markdown_link('Findings JSON', 'findings/findings.json')}",
        f"- {_package_markdown_link('Findings Markdown', 'findings/findings.md')}",
        f"- {_package_markdown_link('Targets JSON', 'targets/targets.json')}",
        f"- {_package_markdown_link('Targets Markdown', 'targets/targets.md')}",
        f"- {_package_markdown_link('Labels JSON', 'metadata/labels.json')}",
        f"- {_package_markdown_link('Entity Notes JSON', 'notes/entity-notes.json')}",
        f"- {_package_markdown_link('Entity Notes Markdown', 'notes/entity-notes.md')}",
    ])
    if project_notes:
        lines.append(f"- {_package_markdown_link('Project Notes Markdown', 'notes/project.md')}")
    if skipped_items:
        lines.append(f"- {_package_markdown_link('Skipped items JSON', 'skipped-items.json')}")
    lines.extend([
        "",
        "## Notes",
        "",
        "Generated by darklab shell evidence packages. Redaction mode is recorded in manifest.json.",
        "",
    ])
    return "\n".join(lines)


def _package_collection_json_bytes(collection_name, items, generated_at, *, extra=None):
    exported = items if isinstance(items, list) else []
    payload = {
        "format": 1,
        "generated_at": generated_at,
        "count": len(exported),
        collection_name: exported,
    }
    if extra:
        payload.update(extra)
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _package_collection_markdown_bytes(title, generated_at, body_lines, *, empty_message):
    lines = [f"# {_package_markdown_text(title)}", ""]
    if generated_at is not None:
        lines.extend([f"Generated: {_package_markdown_text(generated_at)}", ""])
    body = [str(line) for line in body_lines] if isinstance(body_lines, list) else []
    if body:
        lines.extend(body)
    else:
        lines.extend([empty_message, ""])
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def _package_findings_json_bytes(manifest, generated_at, run_pages):
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    exported = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        item = dict(finding)
        run_id = str(item.get("run_id") or "")
        if run_id in run_pages:
            item["run_page"] = _finding_run_anchor(item)
        exported.append(item)
    return _package_collection_json_bytes("findings", exported, generated_at)


def _package_findings_markdown_bytes(manifest, run_pages):
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    finding_count = len([item for item in findings if isinstance(item, dict)])
    lines = [
        "# Findings",
        "",
        f"Selected findings: {finding_count}",
        "",
    ]
    if findings:
        lines.extend(["| Finding | Severity | Status | Run | Evidence |", "| --- | --- | --- | --- | --- |"])
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            run_id = str(finding.get("run_id") or "")
            href = f"../{_finding_run_anchor(finding)}" if run_id in run_pages else ""
            finding_label = finding.get("title") or finding.get("raw_line") or finding.get("id")
            lines.append(
                f"| {_package_markdown_link(finding_label, href)} "
                f"| {_package_markdown_text(finding.get('severity') or 'info')} "
                f"| {_package_markdown_text(finding.get('review_state') or 'new')} "
                f"| {_package_markdown_code(_package_short_id(run_id))} "
                f"| {_package_markdown_code(finding.get('raw_line') or '')}"
                f"{_package_finding_metadata_markdown(finding)} |"
            )
        lines.extend(["", "## Finding Details", ""])
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_label = _package_markdown_text(
                finding.get("title") or finding.get("raw_line") or finding.get("id") or "Finding"
            )
            source_line = finding.get("line_number") if finding.get("line_number") is not None else ""
            lines.extend([
                f"### {finding_label}",
                "",
                f"- ID: {_package_markdown_code(finding.get('id') or '')}",
                f"- Run: {_package_markdown_code(finding.get('run_id') or '')}",
                f"- Scope: {_package_markdown_code(finding.get('scope') or 'finding')}",
                f"- Severity: {_package_markdown_code(finding.get('severity') or 'info')}",
                f"- Review state: {_package_markdown_code(finding.get('review_state') or 'new')}",
                f"- Source line: {_package_markdown_code(source_line)}",
            ])
            target_ids = _package_finding_target_ids(finding)
            if target_ids:
                lines.append("- Targets: " + ", ".join(_package_markdown_code(target_id) for target_id in target_ids))
            raw_line = str(finding.get("raw_line") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
            if raw_line:
                lines.extend(["", "```text", raw_line.replace("```", "`\u200b``"), "```"])
            metadata = _package_finding_metadata_markdown(finding).replace("<br>", "\n")
            if metadata.strip():
                lines.extend(["", metadata.strip()])
            lines.append("")
    else:
        lines.append("- No selected findings.")
    return _package_collection_markdown_bytes(
        "Findings",
        None,
        lines[2:],
        empty_message="- No selected findings.",
    )


def _package_finding_target_ids(finding):
    target_ids = []
    primary = str(finding.get("target_id") or "") if isinstance(finding, dict) else ""
    if primary:
        target_ids.append(primary)
    raw_target_ids = finding.get("target_ids") if isinstance(finding, dict) else None
    if isinstance(raw_target_ids, list):
        for target_id in raw_target_ids:
            normalized = str(target_id or "")
            if normalized and normalized not in target_ids:
                target_ids.append(normalized)
    return target_ids


def _package_targets_json_bytes(manifest, generated_at):
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), list) else []
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    exported = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        item = dict(target)
        target_id = str(item.get("id") or "")
        finding_refs = []
        run_refs = []
        if target_id:
            for finding in findings:
                if not isinstance(finding, dict) or target_id not in _package_finding_target_ids(finding):
                    continue
                finding_id = str(finding.get("id") or "")
                run_id = str(finding.get("run_id") or "")
                if finding_id and finding_id not in finding_refs:
                    finding_refs.append(finding_id)
                if run_id and run_id not in run_refs:
                    run_refs.append(run_id)
        source_run_id = str(item.get("source_run_id") or "")
        if source_run_id and source_run_id not in run_refs:
            run_refs.append(source_run_id)
        item["finding_ids"] = finding_refs
        item["run_ids"] = run_refs
        exported.append(item)
    return _package_collection_json_bytes("targets", exported, generated_at)


def _package_targets_markdown_bytes(manifest):
    targets = manifest.get("targets") if isinstance(manifest.get("targets"), list) else []
    findings = manifest.get("findings") if isinstance(manifest.get("findings"), list) else []
    lines = ["# Targets", "", f"Selected targets: {len([item for item in targets if isinstance(item, dict)])}", ""]
    if not targets:
        lines.append("- No selected targets.")
        return _package_collection_markdown_bytes(
            "Targets",
            None,
            lines[2:],
            empty_message="- No selected targets.",
        )
    for target in targets:
        if not isinstance(target, dict):
            continue
        target_id = str(target.get("id") or "")
        raw_labels = target.get("labels")
        labels = raw_labels if isinstance(raw_labels, list) else []
        primary_label = ""
        for label in labels:
            if isinstance(label, dict) and label.get("label"):
                primary_label = str(label.get("label") or "")
                break
        target_label = _package_markdown_text(primary_label or target.get("value") or target_id or "Target")
        lines.extend([
            f"## {target_label}",
            "",
            f"- ID: {_package_markdown_code(target_id)}",
            f"- Type: {_package_markdown_code(target.get('type') or 'target')}",
            f"- Value: {_package_markdown_code(target.get('value') or '')}",
        ])
        note = target.get("note") if isinstance(target.get("note"), dict) else None
        if note and note.get("body"):
            lines.extend(["", "### Notes", "", _package_markdown_text(note.get("body") or "")])
        if labels:
            label_values = [
                _package_markdown_code(label.get("label") or "")
                for label in labels
                if isinstance(label, dict) and label.get("label")
            ]
            if label_values:
                lines.extend(["", "### Labels", "", ", ".join(label_values)])
        note = target.get("note") if isinstance(target.get("note"), dict) else None
        if note and note.get("body"):
            lines.extend(["", "### Entity Note", "", _package_markdown_text(note.get("body") or "")])
        linked_findings = [
            finding for finding in findings
            if isinstance(finding, dict) and target_id in _package_finding_target_ids(finding)
        ]
        if linked_findings:
            lines.extend(["", "### Related Findings", ""])
            for finding in linked_findings:
                finding_label = _package_markdown_text(finding.get("title") or finding.get("raw_line") or finding.get("id"))
                lines.append(f"- {finding_label} ({_package_markdown_code(finding.get('id') or '')})")
        lines.append("")
    return _package_collection_markdown_bytes(
        "Targets",
        None,
        lines[2:],
        empty_message="- No selected targets.",
    )


def _package_metadata_targets(package, manifest):
    targets = {
        "project": [str(package.get("project_id") or "")],
        "package": [str(package.get("id") or "")],
    }
    selected = manifest.get("selected_entity_ids") if isinstance(manifest.get("selected_entity_ids"), dict) else {}
    mapping = {
        "run": "run_ids",
        "finding": "finding_ids",
        "run_file_artifact": "artifact_ids",
        "target": "target_ids",
    }
    for entity_type, key in mapping.items():
        raw_ids = selected.get(key)
        if isinstance(raw_ids, list):
            targets[entity_type] = [str(value or "") for value in raw_ids if str(value or "")]
    return {
        entity_type: sorted({entity_id for entity_id in entity_ids if entity_id})
        for entity_type, entity_ids in targets.items()
        if any(entity_ids)
    }


def _metadata_items_by_entity(items):
    by_entity = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("entity_type") or ""), str(item.get("entity_id") or ""))
        if not key[0] or not key[1]:
            continue
        by_entity.setdefault(key, []).append(item)
    return by_entity


def _package_manifest_with_inline_metadata(manifest, labels, notes):
    enriched = dict(manifest)
    label_map = _metadata_items_by_entity(labels)
    note_map = _metadata_items_by_entity(notes)

    def _enrich_items(entity_type, key):
        source_items = manifest.get(key) if isinstance(manifest.get(key), list) else []
        enriched_items = []
        for source_item in source_items:
            if not isinstance(source_item, dict):
                continue
            item = dict(source_item)
            entity_id = str(item.get("id") or "")
            item_labels = label_map.get((entity_type, entity_id), [])
            item_note = note_map.get((entity_type, entity_id), [])
            if item_labels:
                item["labels"] = item_labels
            if item_note:
                item["note"] = item_note[0]
            enriched_items.append(item)
        enriched[key] = enriched_items

    _enrich_items("run", "runs")
    _enrich_items("finding", "findings")
    _enrich_items("run_file_artifact", "artifacts")
    _enrich_items("target", "targets")
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    enriched_project = dict(project)
    project_id = str(project.get("id") or "")
    project_labels = label_map.get(("project", project_id), [])
    project_note = note_map.get(("project", project_id), [])
    if project_labels:
        enriched_project["labels"] = project_labels
    if project_note:
        enriched_project["note"] = project_note[0]
    enriched["project"] = enriched_project
    return enriched


def _package_metadata_rows(conn, session_id, table, targets):
    rows = []
    for entity_type, entity_ids in targets.items():
        if not entity_ids:
            continue
        placeholders = ",".join("?" for _ in entity_ids)
        if table == "entity_labels":
            rows.extend(conn.execute(
                "SELECT id, entity_type, entity_id, label, source, created "  # nosec
                f"FROM entity_labels WHERE session_id = ? AND entity_type = ? "
                f"AND entity_id IN ({placeholders}) ORDER BY entity_type ASC, entity_id ASC, label ASC",
                [session_id, entity_type, *entity_ids],
            ).fetchall())
        elif table == "entity_notes":
            rows.extend(conn.execute(
                "SELECT id, entity_type, entity_id, body, created, updated "  # nosec
                f"FROM entity_notes WHERE session_id = ? AND entity_type = ? "
                f"AND entity_id IN ({placeholders}) ORDER BY entity_type ASC, entity_id ASC, updated ASC, id ASC",
                [session_id, entity_type, *entity_ids],
            ).fetchall())
    return rows


def _package_label_dicts(labels, redaction_rules=None):
    return [
        _redact_package_value({
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "label": row["label"],
            "source": row["source"],
            "created": row["created"],
        }, redaction_rules)
        for row in labels
    ]


def _package_labels_json_bytes(labels, generated_at, redaction_rules=None):
    exported = _package_label_dicts(labels, redaction_rules)
    return _package_collection_json_bytes("labels", exported, generated_at)


def _package_note_dicts(notes, redaction_rules=None):
    return [
        _redact_package_value({
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "body": row["body"],
            "created": row["created"],
            "updated": row["updated"],
        }, redaction_rules)
        for row in notes
    ]


def _package_notes_json_bytes(notes, generated_at, *, included, redaction_rules=None):
    exported = _package_note_dicts(notes, redaction_rules)
    return _package_collection_json_bytes(
        "notes",
        exported,
        generated_at,
        extra={"include_private_notes": bool(included)},
    )


def _package_project_notes_markdown_bytes(manifest, generated_at):
    project = manifest.get("project") if isinstance(manifest.get("project"), dict) else {}
    project_notes = _package_markdown_text(_entity_note_body(project))
    lines = []
    if project_notes:
        lines.extend([project_notes, ""])
    else:
        lines.extend(["No project notes were included in this package.", ""])
    return _package_collection_markdown_bytes(
        f"{project.get('name') or 'Project'} Notes",
        generated_at,
        lines,
        empty_message="No project notes were included in this package.",
    )


def _package_notes_markdown_bytes(notes, generated_at, *, included):
    lines = []
    if not included:
        return _package_collection_markdown_bytes(
            "Entity Notes",
            generated_at,
            ["Private entity notes were excluded from this package.", ""],
            empty_message="Private entity notes were excluded from this package.",
        )
    if not notes:
        return _package_collection_markdown_bytes(
            "Entity Notes",
            generated_at,
            ["No selected entity notes were included in this package.", ""],
            empty_message="No selected entity notes were included in this package.",
        )

    for note in notes:
        if not isinstance(note, dict):
            continue
        entity_type = _package_markdown_text(note.get("entity_type") or "entity")
        entity_id = _package_markdown_code(_package_short_id(note.get("entity_id")))
        updated = _package_markdown_text(note.get("updated") or note.get("created") or "unknown")
        body = _package_markdown_text(note.get("body") or "")
        lines.extend([
            f"## {entity_type} {entity_id}",
            "",
            f"- Updated: {updated}",
            "",
            body or "_No note body._",
            "",
        ])
    return _package_collection_markdown_bytes(
        "Entity Notes",
        generated_at,
        lines,
        empty_message="No selected entity notes were included in this package.",
    )


def _allocate_slug(conn, session_id, name, *, project_id=None):
    base = _slugify(name)
    for index in range(0, 100):
        suffix = "" if index == 0 else f"-{index + 1}"
        candidate = f"{base[:80 - len(suffix)]}{suffix}"
        row = conn.execute(
            "SELECT id FROM projects WHERE session_id = ? AND slug = ?",
            (session_id, candidate),
        ).fetchone()
        if not row or row["id"] == project_id:
            return candidate
    return f"{base[:61]}-{secrets.token_hex(4)}"


def migrate_project_workspace_session(conn, from_session_id, to_session_id):
    """Move project workspace records between session IDs during token migration."""
    migrated_projects = 0
    project_rows = conn.execute(
        "SELECT id, name FROM projects WHERE session_id = ? ORDER BY created ASC",
        (from_session_id,),
    ).fetchall()
    for row in project_rows:
        slug = _allocate_slug(conn, to_session_id, row["name"], project_id=row["id"])
        result = conn.execute(
            "UPDATE projects SET session_id = ?, slug = ? WHERE session_id = ? AND id = ?",
            (to_session_id, slug, from_session_id, row["id"]),
        )
        migrated_projects += result.rowcount
    artifact_result = conn.execute(
        "UPDATE run_file_artifacts SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    finding_result = conn.execute(
        "UPDATE findings SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    entity_result = conn.execute(
        "UPDATE entities SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    intel_result = conn.execute(
        "UPDATE entity_intel_snapshots SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    label_result = conn.execute(
        "UPDATE entity_labels SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    note_result = conn.execute(
        "UPDATE entity_notes SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    package_result = conn.execute(
        "UPDATE evidence_packages SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    migrated_active_project_preference = _migrate_active_project_preference(
        conn,
        from_session_id,
        to_session_id,
    )
    return {
        "migrated_projects": migrated_projects,
        "migrated_run_file_artifacts": artifact_result.rowcount,
        "migrated_entities": entity_result.rowcount,
        "migrated_entity_intel_snapshots": intel_result.rowcount,
        "migrated_findings": finding_result.rowcount,
        "migrated_finding_targets": 0,
        "migrated_entity_labels": label_result.rowcount,
        "migrated_entity_notes": note_result.rowcount,
        "migrated_evidence_packages": package_result.rowcount,
        "migrated_active_project_preference": migrated_active_project_preference,
    }


def _project_list_order_sql():
    return (
        "ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END, "
        "CASE WHEN status = 'archived' THEN 1 ELSE 0 END, "
        + dialect_for_backend(DB_BACKEND).case_insensitive_order("name")
        + ", updated DESC, created DESC"
    )


def _active_project_id_from_preferences(conn, session_id):
    preferences = _load_session_preferences(conn, session_id)
    project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if not project_id:
        return ""
    row = conn.execute(
        "SELECT 1 FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
        (session_id, project_id),
    ).fetchone()
    if row:
        return project_id
    _clear_active_project_preference(conn, session_id)
    conn.commit()
    return ""


def _project_list_where_sql(*, include_archived=False):
    if include_archived:
        return "WHERE session_id = ?"
    return "WHERE session_id = ? AND status != 'archived'"


def _project_rows_to_list_projects(conn, session_id, rows, *, include_counts=False):
    projects = [
        project
        for row in rows
        if (project := _row_to_project(row)) is not None
    ]
    _attach_project_notes(conn, session_id, projects)
    _attach_project_labels(conn, session_id, projects)
    if include_counts:
        counts_by_project = _project_list_counts(conn, session_id, [project["id"] for project in projects])
        for project in projects:
            project["counts"] = counts_by_project.get(project["id"], _empty_project_counts())
    return projects


def _empty_project_counts():
    return {
        "runs": 0,
        "entities": 0,
        "targets": 0,
        "pending_targets": 0,
        "artifacts": 0,
        "findings": 0,
        "labels": 0,
        "notes": 0,
        "packages": 0,
    }


def _project_list_counts(conn, session_id, project_ids):
    ids = [str(project_id) for project_id in project_ids if project_id]
    counts = {project_id: _empty_project_counts() for project_id in ids}
    if not ids:
        return counts
    dialect = dialect_for_backend(DB_BACKEND)
    project_filter_sql, project_filter_params = dialect.in_clause("l.project_id", ids)
    package_filter_sql, package_filter_params = dialect.in_clause("project_id", ids)
    meta_filter_sql, meta_filter_params = dialect.in_clause("entity_id", ids)

    for row in conn.execute(
        "SELECT l.project_id, COUNT(*) AS count "  # nosec B608
        "FROM project_links l JOIN runs r ON r.id = l.entity_id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND r.session_id = ? AND r.run_kind = ? "
        "GROUP BY l.project_id",
        (*project_filter_params, session_id, RUN_KIND_EXTERNAL),
    ).fetchall():
        counts[str(row["project_id"])]["runs"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT l.project_id, e.type, l.review_state, COUNT(*) AS count "  # nosec B608
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'atlas_entity' "
        "AND e.session_id = ? "
        "GROUP BY l.project_id, e.type, l.review_state",
        (*project_filter_params, session_id),
    ).fetchall():
        project_counts = counts[str(row["project_id"])]
        count = int(row["count"] or 0)
        project_counts["entities"] += count
        if row["type"] in {"domain", "ip", "url"}:
            if row["review_state"] == "pending":
                project_counts["pending_targets"] += count
            else:
                project_counts["targets"] += count

    for row in conn.execute(
        "SELECT l.project_id, COUNT(a.id) AS count "  # nosec B608
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN run_file_artifacts a ON a.run_id = r.id "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND r.session_id = ? AND r.run_kind = ? "
        "GROUP BY l.project_id",
        (*project_filter_params, session_id, RUN_KIND_EXTERNAL),
    ).fetchall():
        counts[str(row["project_id"])]["artifacts"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT project_id, COUNT(*) AS count FROM evidence_packages "  # nosec B608
        "WHERE session_id = ? AND " + package_filter_sql + " "
        "GROUP BY project_id",
        (session_id, *package_filter_params),
    ).fetchall():
        counts[str(row["project_id"])]["packages"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT project_id, COUNT(DISTINCT finding_id) AS count FROM ("  # nosec B608
        "SELECT l.project_id, fo.finding_id "
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN findings_occurrences fo ON fo.run_id = r.id "
        "JOIN findings f ON f.id = fo.finding_id AND f.session_id = ? "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND r.session_id = ? AND r.run_kind = ? "
        "UNION "
        "SELECT l.project_id, f.id AS finding_id "
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN findings f ON f.session_id = ? "
        "AND (f.run_id = r.id OR f.first_run_id = r.id OR f.last_run_id = r.id) "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'run' "
        "AND r.session_id = ? AND r.run_kind = ? "
        "UNION "
        "SELECT l.project_id, f.id AS finding_id "
        "FROM project_links l "
        "JOIN entities e ON e.id = l.entity_id "
        "JOIN findings f ON f.entity_id = e.id AND f.session_id = ? "
        "WHERE " + project_filter_sql + " AND l.entity_type = 'atlas_entity' "
        "AND e.session_id = ?"
        ") grouped_findings GROUP BY project_id",
        (
            session_id,
            *project_filter_params,
            session_id,
            RUN_KIND_EXTERNAL,
            session_id,
            *project_filter_params,
            session_id,
            RUN_KIND_EXTERNAL,
            session_id,
            *project_filter_params,
            session_id,
        ),
    ).fetchall():
        counts[str(row["project_id"])]["findings"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT entity_id AS project_id, COUNT(*) AS count FROM entity_labels "  # nosec B608
        "WHERE session_id = ? AND entity_type = 'project' AND " + meta_filter_sql + " "
        "GROUP BY entity_id",
        (session_id, *meta_filter_params),
    ).fetchall():
        counts[str(row["project_id"])]["labels"] = int(row["count"] or 0)

    for row in conn.execute(
        "SELECT entity_id AS project_id, COUNT(*) AS count FROM entity_notes "  # nosec B608
        "WHERE session_id = ? AND entity_type = 'project' AND " + meta_filter_sql + " "
        "GROUP BY entity_id",
        (session_id, *meta_filter_params),
    ).fetchall():
        counts[str(row["project_id"])]["notes"] = int(row["count"] or 0)

    return counts


def list_projects(session_id, *, include_archived=False):
    with db_connect() as conn:
        where_sql = _project_list_where_sql(include_archived=include_archived)
        active_project_id = _active_project_id_from_preferences(conn, session_id)
        rows = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "  # nosec B608
            "FROM projects "
            + where_sql
            + " "
            + _project_list_order_sql(),
            (session_id, active_project_id),
        ).fetchall()
        projects = _project_rows_to_list_projects(conn, session_id, rows)
    return projects


def list_projects_page(session_id, *, include_archived=False, limit=50, offset=0, include_counts=False):
    safe_limit = max(1, min(int(limit or 50), 100))
    safe_offset = max(0, int(offset or 0))
    with db_connect() as conn:
        where_sql = _project_list_where_sql(include_archived=include_archived)
        active_project_id = _active_project_id_from_preferences(conn, session_id)
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM projects " + where_sql,  # nosec B608
            (session_id,),
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        rows = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "  # nosec B608
            "FROM projects "
            + where_sql
            + " "
            + _project_list_order_sql()
            + " LIMIT ? OFFSET ?",
            (session_id, active_project_id, safe_limit, safe_offset),
        ).fetchall()
        projects = _project_rows_to_list_projects(conn, session_id, rows, include_counts=include_counts)
    return {
        "projects": projects,
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "has_more": safe_offset + len(projects) < total,
    }


def get_project(session_id, project_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "
            "FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        project = _row_to_project(row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
    return project


def _count_rows_for_ids(conn, table, column, ids):
    values = [str(value) for value in ids if value]
    if not values:
        return 0
    placeholders = ",".join("?" for _ in values)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE {column} IN ({placeholders})",  # nosec
        values,
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _project_run_count_maps(conn, session_id, run_ids):
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return {}, {}
    placeholders = ",".join("?" for _ in ids)
    finding_counts = {run_id: 0 for run_id in ids}
    artifact_counts = {run_id: 0 for run_id in ids}
    finding_rows = conn.execute(
        "SELECT run_id, COUNT(DISTINCT finding_id) AS count FROM ("  # nosec
        "SELECT fo.run_id AS run_id, fo.finding_id AS finding_id "
        "FROM findings_occurrences fo JOIN findings f ON f.id = fo.finding_id "
        f"WHERE f.session_id = ? AND fo.run_id IN ({placeholders}) "
        "UNION "
        "SELECT run_id, id AS finding_id FROM findings "
        f"WHERE session_id = ? AND run_id IN ({placeholders}) "
        "UNION "
        "SELECT first_run_id AS run_id, id AS finding_id FROM findings "
        f"WHERE session_id = ? AND first_run_id IN ({placeholders}) "
        "UNION "
        "SELECT last_run_id AS run_id, id AS finding_id FROM findings "
        f"WHERE session_id = ? AND last_run_id IN ({placeholders})"
        ") grouped_findings WHERE run_id IS NOT NULL AND run_id != '' GROUP BY run_id",
        (session_id, *ids, session_id, *ids, session_id, *ids, session_id, *ids),
    ).fetchall()
    for row in finding_rows:
        finding_counts[str(row["run_id"])] = int(row["count"] or 0)
    artifact_rows = conn.execute(
        "SELECT run_id, COUNT(*) AS count FROM run_file_artifacts "  # nosec
        f"WHERE run_id IN ({placeholders}) GROUP BY run_id",
        ids,
    ).fetchall()
    for row in artifact_rows:
        artifact_counts[str(row["run_id"])] = int(row["count"] or 0)
    return finding_counts, artifact_counts


def _project_atlas_entity_select_sql(*, target_only=False, entity_type=""):
    type_filter = "AND e.type IN ('domain', 'ip', 'url') " if target_only else ""
    if entity_type:
        type_filter += "AND e.type = ? "
    dialect = dialect_for_backend(DB_BACKEND)
    provider_list_expr = dialect.string_agg_distinct("eis.provider")
    value_order_expr = dialect.case_insensitive_order("e.canonical_value")
    return (
        "SELECT e.id, l.project_id, e.type, e.canonical_value, "  # nosec
        "COALESCE(("
        "SELECT erl.run_id FROM entity_run_links erl "
        "JOIN project_links run_link ON run_link.entity_type = 'run' AND run_link.entity_id = erl.run_id "
        "WHERE erl.entity_id = e.id AND run_link.project_id = l.project_id "
        "ORDER BY erl.last_seen_at DESC, erl.run_id DESC LIMIT 1"
        "), '') AS source_run_id, "
        "l.confidence, l.review_state, l.source, l.source_detail, "
        "e.occurrence_count, e.last_seen_at, e.created, COALESCE(NULLIF(l.updated, ''), l.created) AS updated, "
        "COALESCE(("
        "SELECT COUNT(DISTINCT erl.run_id) FROM entity_run_links erl "
        "JOIN runs er ON er.id = erl.run_id AND er.session_id = e.session_id "
        "WHERE erl.entity_id = e.id"
        "), 0) AS run_count, "
        "COALESCE(("
        "SELECT COUNT(DISTINCT eis.provider) FROM entity_intel_snapshots eis "
        "WHERE eis.session_id = e.session_id AND eis.entity_id = e.id "
        "AND (eis.status = 'ok' OR eis.status = 'partial')"
        "), 0) AS intel_provider_count "
        ", COALESCE(("
        "SELECT " + provider_list_expr + " FROM entity_intel_snapshots eis "
        "WHERE eis.session_id = e.session_id AND eis.entity_id = e.id "
        "AND (eis.status = 'ok' OR eis.status = 'partial')"
        "), '') AS intel_providers "
        ", COALESCE(("
        "SELECT MAX(eis.fetched_at) FROM entity_intel_snapshots eis "
        "WHERE eis.session_id = e.session_id AND eis.entity_id = e.id "
        "AND (eis.status = 'ok' OR eis.status = 'partial')"
        "), '') AS intel_last_refreshed "
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND e.session_id = ? "
        + type_filter
        + "ORDER BY e.type ASC, " + value_order_expr
    )


def _project_run_rows_to_items(conn, session_id, rows):
    run_ids = [row["id"] for row in rows if row["id"]]
    finding_counts, artifact_counts = _project_run_count_maps(conn, session_id, run_ids)
    run_labels = _entity_labels_by_id(conn, session_id, "run", run_ids)
    run_notes = _entity_notes_by_id(conn, session_id, "run", run_ids)
    runs = []
    for row in rows:
        item = _row_to_project_run(row)
        if not item:
            continue
        run_id = str(item["id"])
        item["finding_count"] = finding_counts.get(run_id, int(item.get("finding_count") or 0))
        item["artifact_count"] = artifact_counts.get(run_id, int(item.get("artifact_count") or 0))
        item["labels"] = run_labels.get(run_id, [])
        item["note"] = run_notes.get(run_id)
        runs.append(item)
    return runs


def _project_entity_counts_by_type(conn, session_id, project_id):
    rows = conn.execute(
        "SELECT e.type, COUNT(*) AS count "
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND e.session_id = ? "
        "GROUP BY e.type",
        (project_id, session_id),
    ).fetchall()
    return {str(row["type"] or ""): int(row["count"] or 0) for row in rows}


def _project_entity_rows_to_items(conn, session_id, rows):
    entity_ids = [str(row["id"] or "") for row in rows if row["id"]]
    entity_labels = _entity_labels_by_id(conn, session_id, "atlas_entity", entity_ids)
    entity_notes = _entity_notes_by_id(conn, session_id, "atlas_entity", entity_ids)
    entities = []
    for row in rows:
        item = _row_to_target(row)
        if not item:
            continue
        item_id = str(item["id"])
        entities.append({
            **item,
            "labels": entity_labels.get(item_id, []),
            "note": entity_notes.get(item_id),
        })
    return entities


def _project_artifact_rows_to_items(session_id, conn, rows):
    artifact_ids = [str(row["id"] or "") for row in rows if row["id"]]
    artifact_labels = _entity_labels_by_id(conn, session_id, "run_file_artifact", artifact_ids)
    artifact_notes = _entity_notes_by_id(conn, session_id, "run_file_artifact", artifact_ids)
    artifacts = []
    for row in rows:
        item = _row_to_run_file_artifact(row)
        if not item:
            continue
        item_id = str(item["id"])
        artifacts.append({
            **item,
            **_artifact_availability(session_id, item),
            "labels": artifact_labels.get(item_id, []),
            "note": artifact_notes.get(item_id),
        })
    return artifacts


def get_project_summary(session_id, project_id):
    with db_connect() as conn:
        project_row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "
            "FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project_row:
            return None
        project = _row_to_project(project_row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
        run_link_rows = conn.execute(
            "SELECT l.id, l.project_id, l.entity_type, l.entity_id, l.source, l.created "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ? "
            "ORDER BY l.created DESC",
            (project_id, session_id, RUN_KIND_EXTERNAL),
        ).fetchall()
        atlas_link_rows = conn.execute(
            "SELECT l.id, l.project_id, l.entity_type, l.entity_id, l.source, l.created "
            "FROM project_links l JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
            "AND e.session_id = ? "
            "ORDER BY l.created DESC",
            (project_id, session_id),
        ).fetchall()
        link_rows = [*run_link_rows, *atlas_link_rows]
        target_rows = conn.execute(
            _project_atlas_entity_select_sql(target_only=True),
            (project_id, session_id),
        ).fetchall()
        run_ids = [row["entity_id"] for row in run_link_rows if row["entity_type"] == "run"]
        entity_id_rows = conn.execute(
            "SELECT e.id, e.type "
            "FROM project_links l JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND e.session_id = ?",
            (project_id, session_id),
        ).fetchall()
        entity_ids = [row["id"] for row in entity_id_rows]
        entity_counts_by_type = _project_entity_counts_by_type(conn, session_id, project_id)
        artifact_id_rows = []
        finding_rows = []
        run_rows = []
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            run_rows = conn.execute(
                "SELECT r.id, r.command, r.started, r.finished, r.exit_code, r.output_line_count, "
                "l.created, l.source AS link_source "
                "FROM project_links l JOIN runs r ON r.id = l.entity_id "
                "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
                "AND r.run_kind = ? "
                "ORDER BY r.started DESC, l.created DESC",
                (project_id, session_id, RUN_KIND_EXTERNAL),
            ).fetchall()
            artifact_id_rows = conn.execute(
                "SELECT id "
                f"FROM run_file_artifacts WHERE run_id IN ({placeholders}) ",  # nosec B608
                run_ids,
            ).fetchall()
        if run_ids or entity_ids:
            finding_clauses = []
            finding_params = [session_id]
            if run_ids:
                run_placeholders = ",".join("?" for _ in run_ids)
                finding_clauses.append(
                    "EXISTS ("
                    "SELECT 1 FROM findings_occurrences fo "
                    "WHERE fo.finding_id = f.id "
                    f"AND fo.run_id IN ({run_placeholders})"  # nosec
                    ") "
                    f"OR f.run_id IN ({run_placeholders}) "  # nosec
                    f"OR f.first_run_id IN ({run_placeholders}) "  # nosec
                    f"OR f.last_run_id IN ({run_placeholders})"  # nosec
                )
                finding_params.extend([*run_ids, *run_ids, *run_ids, *run_ids])
            if entity_ids:
                entity_placeholders = ",".join("?" for _ in entity_ids)
                finding_clauses.append(f"f.entity_id IN ({entity_placeholders})")  # nosec
                finding_params.extend(entity_ids)
            finding_rows = conn.execute(
                "SELECT DISTINCT f.id FROM findings f WHERE f.session_id = ? AND ("  # nosec
                + " OR ".join(finding_clauses)
                + ")",
                finding_params,
            ).fetchall()
        artifact_ids = [row["id"] for row in artifact_id_rows]
        finding_ids = [row["id"] for row in finding_rows]
        target_ids = [row["id"] for row in target_rows]
        package_rows = conn.execute(
            "SELECT id FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        ).fetchall()
        package_ids = [row["id"] for row in package_rows]
        target_labels = _entity_labels_by_id(conn, session_id, "atlas_entity", target_ids)
        target_notes = _entity_notes_by_id(conn, session_id, "atlas_entity", target_ids)
        label_count = (
            _count_entity_metadata_for_ids(conn, "entity_labels", "project", [project_id])
            + _count_entity_metadata_for_ids(conn, "entity_labels", "run", run_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "run_file_artifact", artifact_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "finding", finding_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "atlas_entity", entity_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "target", target_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "package", package_ids)
        )
        note_count = (
            _count_entity_metadata_for_ids(conn, "entity_notes", "project", [project_id])
            + _count_entity_metadata_for_ids(conn, "entity_notes", "run", run_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "run_file_artifact", artifact_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "finding", finding_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "atlas_entity", entity_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "target", target_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "package", package_ids)
        )
        run_items = _project_run_rows_to_items(conn, session_id, run_rows)
    links = [_row_to_link(row) for row in link_rows]
    targets = []
    for item in (_row_to_target(row) for row in target_rows):
        if not item:
            continue
        item_id = str(item["id"])
        targets.append({
            **item,
            "labels": target_labels.get(item_id, []),
            "note": target_notes.get(item_id),
        })
    confirmed_target_count = sum(1 for target in targets if target and target.get("review_state") == "confirmed")
    pending_target_count = sum(1 for target in targets if target and target.get("review_state") == "pending")
    runs = run_items
    packages = list_evidence_packages(session_id, project_id) or []
    return {
        "project": project,
        "links": links,
        "targets": targets,
        "entities": [],
        "entity_counts": entity_counts_by_type,
        "runs": runs,
        "artifacts": [],
        "packages": packages,
        "counts": {
            "runs": len(run_ids),
            "entities": sum(entity_counts_by_type.values()),
            "targets": confirmed_target_count,
            "pending_targets": pending_target_count,
            "artifacts": len(artifact_ids),
            "findings": len(finding_ids),
            "labels": label_count,
            "notes": note_count,
            "packages": len(package_ids),
        },
    }


def _project_entity_page_payload(entities, total, limit, offset, counts_by_type=None):
    return {
        "entities": entities,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(entities) < total,
        "counts_by_type": counts_by_type if isinstance(counts_by_type, dict) else {},
    }


def list_project_entities(session_id, project_id, *, entity_type="", limit=50, offset=0):
    safe_limit = max(1, min(int(limit or 50), 200))
    safe_offset = max(0, int(offset or 0))
    normalized_type = _trim_text(entity_type, 32).lower()
    with db_connect() as conn:
        project_row = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project_row:
            return None
        counts_by_type = _project_entity_counts_by_type(conn, session_id, project_id)
        total = int(counts_by_type.get(normalized_type, 0)) if normalized_type else sum(counts_by_type.values())
        params = [project_id, session_id]
        if normalized_type:
            params.append(normalized_type)
        rows = conn.execute(
            _project_atlas_entity_select_sql(entity_type=normalized_type)
            + " LIMIT ? OFFSET ?",
            (*params, safe_limit, safe_offset),
        ).fetchall()
        entities = _project_entity_rows_to_items(conn, session_id, rows)
    return _project_entity_page_payload(entities, total, safe_limit, safe_offset, counts_by_type)


def _project_artifact_page_payload(artifacts, total, limit, offset, run_counts=None):
    return {
        "artifacts": artifacts,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(artifacts) < total,
        "run_counts": run_counts if isinstance(run_counts, dict) else {},
    }


def _project_target_filter_run_ids(conn, session_id, project_id, target_ids):
    ids = [str(target_id) for target_id in target_ids if target_id]
    if not ids:
        return None
    placeholders = ",".join("?" for _ in ids)
    target_rows = conn.execute(
        "SELECT e.id, e.canonical_value "
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        "AND e.session_id = ? "
        f"AND e.id IN ({placeholders})",  # nosec
        (project_id, session_id, *ids),
    ).fetchall()
    if len(target_rows) != len(ids):
        return set()
    run_ids = set()
    for row in target_rows:
        value = str(row["canonical_value"] or "").strip().lower()
        if not value:
            continue
        direct_rows = conn.execute(
            "SELECT l.entity_id AS run_id "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ? "
            "AND LOWER(r.command) LIKE ?",
            (project_id, session_id, RUN_KIND_EXTERNAL, f"%{value}%"),
        ).fetchall()
        run_ids.update(str(run["run_id"] or "") for run in direct_rows if run["run_id"])
    finding_rows = conn.execute(
        "WITH project_runs AS ("
        "  SELECT l.entity_id AS run_id FROM project_links l "
        "  JOIN runs r ON r.id = l.entity_id "
        "  WHERE l.project_id = ? AND l.entity_type = 'run' "
        "  AND r.session_id = ? AND r.run_kind = ?"
        "), target_findings AS ("
        "  SELECT f.id, f.run_id, f.first_run_id, f.last_run_id "
        "  FROM findings f WHERE f.session_id = ? "
        f"  AND COALESCE(f.entity_id, f.target_id) IN ({placeholders})"  # nosec
        ") "
        "SELECT DISTINCT run_id FROM ("
        "  SELECT fo.run_id AS run_id FROM findings_occurrences fo "
        "  JOIN target_findings tf ON tf.id = fo.finding_id "
        "  JOIN project_runs pr ON pr.run_id = fo.run_id "
        "  UNION "
        "  SELECT tf.run_id FROM target_findings tf JOIN project_runs pr ON pr.run_id = tf.run_id "
        "  UNION "
        "  SELECT tf.first_run_id FROM target_findings tf JOIN project_runs pr ON pr.run_id = tf.first_run_id "
        "  UNION "
        "  SELECT tf.last_run_id FROM target_findings tf JOIN project_runs pr ON pr.run_id = tf.last_run_id"
        ") matched_runs WHERE run_id IS NOT NULL AND run_id != ''",
        (project_id, session_id, RUN_KIND_EXTERNAL, session_id, *ids),
    ).fetchall()
    run_ids.update(str(row["run_id"] or "") for row in finding_rows if row["run_id"])
    return run_ids


def list_project_artifacts(session_id, project_id, filters=None, *, limit=50, offset=0):
    filters = filters if isinstance(filters, dict) else {}
    safe_limit = max(1, min(int(limit or 50), 200))
    safe_offset = max(0, int(offset or 0))
    with db_connect() as conn:
        project_row = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project_row:
            return None
        linked_run_rows = conn.execute(
            "SELECT l.entity_id AS run_id "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ?",
            (project_id, session_id, RUN_KIND_EXTERNAL),
        ).fetchall()
        allowed_run_ids = {str(row["run_id"] or "") for row in linked_run_rows if row["run_id"]}
        run_ids = _metadata_filter_values(filters, "run_id", MAX_ENTITY_ID_LEN)
        if run_ids:
            candidate_run_ids = allowed_run_ids.intersection(run_ids)
        else:
            candidate_run_ids = set(allowed_run_ids)
        target_ids = _metadata_filter_values(filters, "target_id", MAX_ENTITY_ID_LEN)
        target_run_ids = _project_target_filter_run_ids(conn, session_id, project_id, target_ids)
        if target_run_ids is not None:
            candidate_run_ids = candidate_run_ids.intersection(target_run_ids)
        if not candidate_run_ids:
            return _project_artifact_page_payload([], 0, safe_limit, safe_offset, {})
        ordered_run_ids = sorted(candidate_run_ids)
        placeholders = ",".join("?" for _ in ordered_run_ids)
        count_rows = conn.execute(
            "SELECT run_id, COUNT(*) AS count FROM run_file_artifacts "  # nosec
            "WHERE session_id = ? "
            f"AND run_id IN ({placeholders}) "  # nosec
            "GROUP BY run_id",
            (session_id, *ordered_run_ids),
        ).fetchall()
        run_counts = {str(row["run_id"] or ""): int(row["count"] or 0) for row in count_rows}
        total = sum(run_counts.values())
        rows = conn.execute(
            "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "  # nosec
            "detected_by, content_type, preview_type, content_sha256, created "
            "FROM run_file_artifacts WHERE session_id = ? "
            f"AND run_id IN ({placeholders}) "  # nosec
            "ORDER BY created DESC, id DESC "
            "LIMIT ? OFFSET ?",
            (session_id, *ordered_run_ids, safe_limit, safe_offset),
        ).fetchall()
        artifacts = _project_artifact_rows_to_items(session_id, conn, rows)
    return _project_artifact_page_payload(artifacts, total, safe_limit, safe_offset, run_counts)


def _list_all_project_artifacts(session_id, project_id):
    artifacts = []
    offset = 0
    while True:
        page = list_project_artifacts(session_id, project_id, {}, limit=200, offset=offset)
        if page is None:
            return None
        rows = page.get("artifacts") if isinstance(page, dict) else []
        if not rows:
            break
        artifacts.extend(rows)
        offset += len(rows)
        if offset >= int(page.get("total") or len(artifacts)):
            break
    return artifacts


def list_project_runs(session_id, project_id, *, limit=50, offset=0):
    safe_limit = max(1, min(int(limit or 50), 200))
    safe_offset = max(0, int(offset or 0))
    with db_connect() as conn:
        project_row = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project_row:
            return None
        total_row = conn.execute(
            "SELECT COUNT(*) AS count "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ?",
            (project_id, session_id, RUN_KIND_EXTERNAL),
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        rows = conn.execute(
            "SELECT r.id, r.command, r.started, r.finished, r.exit_code, r.output_line_count, "
            "l.created, l.source AS link_source "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
            "AND r.run_kind = ? "
            "ORDER BY r.started DESC, l.created DESC "
            "LIMIT ? OFFSET ?",
            (project_id, session_id, RUN_KIND_EXTERNAL, safe_limit, safe_offset),
        ).fetchall()
        runs = _project_run_rows_to_items(conn, session_id, rows)
    return {
        "runs": runs,
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "has_more": safe_offset + len(runs) < total,
    }


def get_project_run_file_artifact(session_id, project_id, artifact_id):
    artifact_id = _trim_text(artifact_id, MAX_ENTITY_ID_LEN)
    if not artifact_id:
        return None
    with db_connect() as conn:
        row = conn.execute(
            "SELECT a.id, a.session_id, a.run_id, a.workspace_path, a.display_name, a.kind, "
            "a.byte_size, a.detected_by, a.content_type, a.preview_type, a.content_sha256, a.created "
            "FROM run_file_artifacts a "
            "JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = a.run_id "
            "JOIN projects p ON p.id = l.project_id "
            "JOIN runs r ON r.id = a.run_id "
            "WHERE p.session_id = ? AND p.id = ? AND a.session_id = ? AND a.id = ? "
            "AND r.session_id = ?",
            (session_id, project_id, session_id, artifact_id, session_id),
        ).fetchone()
    artifact = _row_to_run_file_artifact(row)
    if not artifact:
        return None
    return {
        **artifact,
        **_artifact_availability(session_id, artifact),
    }


def create_project(session_id, data):
    payload = _normalize_project_payload(data)
    created = _now()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM projects WHERE session_id = ?",
            [session_id],
        ).fetchone()
        if _quota_exceeded(int(row["count"] or 0) if row else 0, "max_projects_per_session", 100):
            _raise_quota("project quota exceeded for this session")
        for _ in range(10):
            project_id = _new_project_id()
            slug = _allocate_slug(conn, session_id, payload["name"])
            result = conn.execute(
                "INSERT INTO projects "
                "(id, session_id, name, slug, description, status, color, created, updated) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?) "
                "ON CONFLICT(id) DO NOTHING",
                (
                    project_id,
                    session_id,
                    payload["name"],
                    slug,
                    payload["description"],
                    payload["color"],
                    created,
                    created,
                ),
            )
            if result.rowcount:
                if "notes" in payload:
                    _save_project_note(conn, session_id, project_id, payload["notes"])
                conn.commit()
                return get_project(session_id, project_id)
        raise ProjectWorkspaceError("could not allocate a project id")


def update_project(session_id, project_id, data):
    payload = _normalize_project_payload(data, partial=True)
    if not payload:
        raise ProjectWorkspaceError("project update payload is empty")
    updated = _now()
    with db_connect() as conn:
        current = conn.execute(
            "SELECT id, name, slug, description, status, color "
            "FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not current:
            return None
        name = current["name"]
        slug = current["slug"]
        description = current["description"]
        status = current["status"]
        color = current["color"]
        if "name" in payload:
            name = payload["name"]
            slug = _allocate_slug(conn, session_id, payload["name"], project_id=project_id)
        if "description" in payload:
            description = payload["description"]
        if "status" in payload:
            status = payload["status"]
        if "color" in payload:
            color = payload["color"]
        conn.execute(
            "UPDATE projects "
            "SET name = ?, slug = ?, description = ?, status = ?, color = ?, updated = ? "
            "WHERE session_id = ? AND id = ?",
            (name, slug, description, status, color, updated, session_id, project_id),
        )
        if "notes" in payload:
            _save_project_note(conn, session_id, project_id, payload["notes"])
        conn.commit()
    return get_project(session_id, project_id)


def delete_project(session_id, project_id):
    with db_connect() as conn:
        project = conn.execute(
            "SELECT id FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return False
        target_rows = conn.execute(
            "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity'",
            (project_id,),
        ).fetchall()
        target_ids = [row["entity_id"] for row in target_rows if row["entity_id"]]
        package_rows = conn.execute(
            "SELECT id FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        ).fetchall()
        package_ids = [row["id"] for row in package_rows if row["id"]]
        conn.execute(
            "DELETE FROM entity_labels WHERE entity_type = 'project' AND entity_id = ?",
            (project_id,),
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE entity_type = 'project' AND entity_id = ?",
            (project_id,),
        )
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            conn.execute(
                "DELETE FROM entity_labels WHERE entity_type = 'atlas_entity' "  # nosec
                f"AND entity_id IN ({placeholders})",
                target_ids,
            )
            conn.execute(
                "DELETE FROM entity_notes WHERE entity_type = 'atlas_entity' "  # nosec
                f"AND entity_id IN ({placeholders})",
                target_ids,
            )
        if package_ids:
            placeholders = ",".join("?" for _ in package_ids)
            conn.execute(
                "DELETE FROM entity_labels WHERE entity_type = 'package' "  # nosec
                f"AND entity_id IN ({placeholders})",
                package_ids,
            )
            conn.execute(
                "DELETE FROM entity_notes WHERE entity_type = 'package' "  # nosec
                f"AND entity_id IN ({placeholders})",
                package_ids,
            )
        conn.execute("DELETE FROM project_links WHERE project_id = ?", (project_id,))
        conn.execute(
            "DELETE FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        )
        _clear_active_project_preference(conn, session_id, project_id=project_id)
        conn.execute(
            "DELETE FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        )
        conn.commit()
    return True


def list_evidence_packages(session_id, project_id):
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        rows = conn.execute(
            "SELECT id, session_id, project_id, name, description, redaction_mode, "
            "include_artifacts, manifest, status, created, updated "
            "FROM evidence_packages WHERE session_id = ? AND project_id = ? "
            "ORDER BY updated DESC, created DESC",
            (session_id, project_id),
        ).fetchall()
        packages = [_row_to_evidence_package(row) for row in rows]
        _attach_package_metadata(conn, session_id, packages)
    return packages


def get_evidence_package(session_id, project_id, package_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, project_id, name, description, redaction_mode, "
            "include_artifacts, manifest, status, created, updated "
            "FROM evidence_packages WHERE session_id = ? AND project_id = ? AND id = ?",
            [session_id, project_id, package_id],
        ).fetchone()
        package = _row_to_evidence_package(row)
        _attach_package_metadata(conn, session_id, [package])
    return package


def _write_bounded_archive_entry(
    archive,
    name,
    payload_bytes,
    projected_bytes,
    max_archive_bytes,
    message="evidence package exceeds configured size limit",
):
    new_total = projected_bytes + len(payload_bytes)
    if max_archive_bytes and new_total > max_archive_bytes:
        raise EvidencePackageTooLarge(message)
    archive.writestr(name, payload_bytes)
    return new_total


def _package_selected_id_count(manifest, key):
    selected = manifest.get("selected_entity_ids") if isinstance(manifest, dict) else None
    if not isinstance(selected, dict) or not isinstance(selected.get(key), list):
        return 0
    return len([item for item in selected[key] if str(item or "")])


def _evidence_package_estimated_archive_bytes(manifest):
    estimate = manifest.get("estimated_archive") if isinstance(manifest, dict) else None
    if not isinstance(estimate, dict):
        return 0
    for key in ("estimated_archive_bytes", "estimated_uncompressed_bytes"):
        try:
            value = int(estimate.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _raise_if_estimated_archive_too_large(manifest, max_archive_bytes):
    if not max_archive_bytes:
        return
    estimated_bytes = _evidence_package_estimated_archive_bytes(manifest)
    if estimated_bytes > max_archive_bytes:
        raise EvidencePackageTooLarge("evidence package estimate exceeds configured size limit")


def _metadata_filter_values(filters, key, max_len, *, lower=False):
    raw_values = filters.get(key) if isinstance(filters, dict) else None
    if raw_values is None:
        return []
    values = raw_values if isinstance(raw_values, (list, tuple)) else [raw_values]
    normalized_values = []
    seen = set()
    for value in values:
        normalized = _trim_text(value, max_len)
        if lower:
            normalized = normalized.lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_values.append(normalized)
    return normalized_values


def build_evidence_package_archive(session_id, project_id, package_id, *, cfg=None):
    build_started = time.perf_counter()
    timings = {}

    def _elapsed_ms(started):
        return int(round((time.perf_counter() - started) * 1000))

    def _record_timing(name, started):
        timings[f"{name}_ms"] = _elapsed_ms(started)

    package = get_evidence_package(session_id, project_id, package_id)
    if package is None:
        return None
    metadata_started = time.perf_counter()
    generated_at = _now()
    manifest = dict(package.get("manifest") or {})
    redaction_rules = _package_redaction_rules(package.get("redaction_mode"), cfg=cfg)
    render_manifest = _redact_package_manifest(manifest, redaction_rules)
    if not render_manifest.get("include_private_notes"):
        render_manifest = _package_manifest_without_private_notes(render_manifest)
    metadata_targets = _package_metadata_targets(package, manifest)
    with db_connect() as conn:
        label_rows = _package_metadata_rows(conn, session_id, "entity_labels", metadata_targets)
        note_rows = (
            _package_metadata_rows(conn, session_id, "entity_notes", metadata_targets)
            if render_manifest.get("include_private_notes")
            else []
        )
    label_items = _package_label_dicts(label_rows, redaction_rules)
    note_items = _package_note_dicts(note_rows, redaction_rules)
    render_manifest = _package_manifest_with_inline_metadata(
        render_manifest,
        label_items,
        note_items,
    )
    render_package = {
        **package,
        "name": apply_redaction_rules(package["name"], redaction_rules),
        "description": apply_redaction_rules(package["description"], redaction_rules),
    }
    package_labels = _metadata_items_by_entity(label_items).get(("package", str(package.get("id") or "")), [])
    package_notes = _metadata_items_by_entity(note_items).get(("package", str(package.get("id") or "")), [])
    export_package = {
        "id": package["id"],
        "name": render_package["name"],
        "description": render_package["description"],
        "redaction_mode": package["redaction_mode"],
        "include_artifacts": package["include_artifacts"],
        "status": package["status"],
        "created": package["created"],
        "updated": package["updated"],
    }
    if package_labels:
        export_package["labels"] = package_labels
    if package_notes:
        export_package["note"] = package_notes[0]
    export_manifest = {
        "format": 1,
        "generated_at": generated_at,
        "package": export_package,
        "manifest": render_manifest,
    }
    manifest_bytes = json.dumps(export_manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    max_archive_bytes = _cfg_mb_bytes("evidence_package_max_mb", 25, cfg=cfg)
    _raise_if_estimated_archive_too_large(manifest, max_archive_bytes)
    _record_timing("metadata", metadata_started)
    skipped_artifacts = []
    skipped_items = []
    artifact_archive_paths = {}
    temp_file = tempfile.NamedTemporaryFile(
        prefix="darklab-evidence-package-",
        suffix=".zip",
        delete=False,
    )
    archive_path = temp_file.name
    temp_file.close()
    used_paths = set()
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            core_started = time.perf_counter()
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "manifest.json",
                manifest_bytes,
                0,
                max_archive_bytes,
                "evidence package manifest exceeds configured size limit",
            )
            css_bytes = (_package_css() + "\n").encode("utf-8")
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "assets/package.css",
                css_bytes,
                projected_bytes,
                max_archive_bytes,
                "evidence package CSS snapshot exceeds configured size limit",
            )
            _record_timing("core_entries", core_started)
            artifacts_started = time.perf_counter()
            if package["include_artifacts"]:
                artifacts = manifest.get("artifacts")
                artifact_items = artifacts if isinstance(artifacts, list) else []
                max_artifacts = _cfg_int("evidence_package_max_artifacts", 100, cfg=cfg)
                if max_artifacts and len(artifact_items) > max_artifacts:
                    raise EvidencePackageTooLarge("evidence package artifact count exceeds configured limit")
                for artifact in artifact_items:
                    if not isinstance(artifact, dict):
                        continue
                    workspace_path = _trim_text(artifact.get("workspace_path"), MAX_ENTITY_ID_LEN)
                    if not workspace_path:
                        continue
                    try:
                        declared_size = max(0, int(artifact.get("byte_size") or 0))
                    except (TypeError, ValueError):
                        declared_size = 0
                    if max_archive_bytes and declared_size and projected_bytes + declared_size > max_archive_bytes:
                        raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
                    try:
                        resolved = resolve_workspace_path(session_id, workspace_path, cfg)
                        if not resolved.is_file():
                            raise ProjectWorkspaceError("artifact file is not available")
                        mismatch_reason = _artifact_snapshot_mismatch_reason(artifact, resolved)
                        if mismatch_reason:
                            raise ProjectWorkspaceError(mismatch_reason)
                        projected_bytes += resolved.stat().st_size
                        if max_archive_bytes and projected_bytes > max_archive_bytes:
                            raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
                        zip_path = _package_zip_artifact_path(workspace_path, used_paths)
                        archive.write(resolved, arcname=zip_path)
                        artifact_archive_paths[str(artifact.get("id") or "")] = zip_path
                    except (OSError, ProjectWorkspaceError, WorkspaceError) as exc:
                        skipped_artifact = {
                            "kind": "artifact",
                            "id": artifact.get("id") or "",
                            "label": artifact.get("display_name") or workspace_path,
                            "workspace_path": workspace_path,
                            "reason": str(exc),
                        }
                        skipped_artifacts.append(skipped_artifact)
                        skipped_items.append(skipped_artifact)
            if skipped_artifacts:
                skipped_bytes = (
                    json.dumps({"artifacts": skipped_artifacts}, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8")
                projected_bytes = _write_bounded_archive_entry(
                    archive,
                    "skipped-artifacts.json",
                    skipped_bytes,
                    projected_bytes,
                    max_archive_bytes,
                )
            _record_timing("artifacts", artifacts_started)

            run_pages_started = time.perf_counter()
            run_pages = {}
            run_text_paths = {}
            run_ids = []
            transcript_run_ids = []
            selected_entity_ids = manifest.get("selected_entity_ids")
            if isinstance(selected_entity_ids, dict) and isinstance(selected_entity_ids.get("run_ids"), list):
                run_ids = [str(run_id) for run_id in selected_entity_ids["run_ids"] if str(run_id)]
                if isinstance(selected_entity_ids.get("transcript_run_ids"), list):
                    selected_transcripts = {str(run_id) for run_id in selected_entity_ids["transcript_run_ids"] if str(run_id)}
                    transcript_run_ids = [run_id for run_id in run_ids if run_id in selected_transcripts]
                else:
                    transcript_run_ids = list(run_ids)
            with db_connect() as conn:
                run_rows = _package_run_rows(conn, session_id, transcript_run_ids)
            found_run_ids = {str(row.get("id") or "") for row in run_rows}
            for run_id in transcript_run_ids:
                if run_id in found_run_ids:
                    continue
                skipped_items.append({
                    "kind": "run",
                    "id": run_id,
                    "label": run_id,
                    "reason": "run is no longer available or no longer belongs to this session",
                })
            for run in run_rows:
                run_id = str(run.get("id") or "")
                if not run_id:
                    continue
                entries, companion_entries, cap_notice = _package_run_output_entries(
                    run,
                    cfg=cfg,
                    include_companion=True,
                )
                transcript_text_path = ""
                if cap_notice:
                    skipped_items.append({
                        "kind": "transcript",
                        "id": run_id,
                        "label": run.get("command") or run_id,
                        "reason": str(cap_notice.get("text") or "").strip("[]"),
                    })
                    companion_bytes = _package_run_text_bytes(companion_entries, redaction_rules)
                    if max_archive_bytes and projected_bytes + len(companion_bytes) > max_archive_bytes:
                        skipped_items.append({
                            "kind": "transcript_companion",
                            "id": run_id,
                            "label": run.get("command") or run_id,
                            "reason": "full text transcript companion exceeds configured package size limit",
                        })
                    else:
                        transcript_text_path = f"runs/{run_id}.txt"
                        run_text_paths[run_id] = transcript_text_path
                        projected_bytes = _write_bounded_archive_entry(
                            archive,
                            transcript_text_path,
                            companion_bytes,
                            projected_bytes,
                            max_archive_bytes,
                        )
                run_page = _render_package_run_html(
                    run,
                    entries,
                    render_manifest,
                    generated_at,
                    transcript_text_path=transcript_text_path,
                    redaction_rules=redaction_rules,
                )
                run_page_bytes = run_page.encode("utf-8")
                run_path = f"runs/{run_id}.html"
                run_pages[run_id] = run_path
                projected_bytes = _write_bounded_archive_entry(
                    archive,
                    run_path,
                    run_page_bytes,
                    projected_bytes,
                    max_archive_bytes,
                )
            _record_timing("run_pages", run_pages_started)

            findings_started = time.perf_counter()
            findings_json_bytes = _package_findings_json_bytes(render_manifest, generated_at, run_pages)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "findings/findings.json",
                findings_json_bytes,
                projected_bytes,
                max_archive_bytes,
            )
            findings_markdown_bytes = _package_findings_markdown_bytes(render_manifest, run_pages)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "findings/findings.md",
                findings_markdown_bytes,
                projected_bytes,
                max_archive_bytes,
            )
            _record_timing("findings", findings_started)

            targets_started = time.perf_counter()
            targets_json_bytes = _package_targets_json_bytes(render_manifest, generated_at)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "targets/targets.json",
                targets_json_bytes,
                projected_bytes,
                max_archive_bytes,
            )
            targets_markdown_bytes = _package_targets_markdown_bytes(render_manifest)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "targets/targets.md",
                targets_markdown_bytes,
                projected_bytes,
                max_archive_bytes,
            )
            _record_timing("targets", targets_started)

            notes_started = time.perf_counter()
            labels_json_bytes = _package_labels_json_bytes(label_items, generated_at)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "metadata/labels.json",
                labels_json_bytes,
                projected_bytes,
                max_archive_bytes,
            )
            notes_json_bytes = _package_notes_json_bytes(
                note_items,
                generated_at,
                included=bool(render_manifest.get("include_private_notes")),
            )
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "notes/entity-notes.json",
                notes_json_bytes,
                projected_bytes,
                max_archive_bytes,
            )
            notes_markdown_bytes = _package_notes_markdown_bytes(
                note_items,
                generated_at,
                included=bool(render_manifest.get("include_private_notes")),
            )
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "notes/entity-notes.md",
                notes_markdown_bytes,
                projected_bytes,
                max_archive_bytes,
            )
            if _entity_note_body(render_manifest.get("project") if isinstance(render_manifest, dict) else {}):
                project_notes_bytes = _package_project_notes_markdown_bytes(render_manifest, generated_at)
                projected_bytes = _write_bounded_archive_entry(
                    archive,
                    "notes/project.md",
                    project_notes_bytes,
                    projected_bytes,
                    max_archive_bytes,
                )
            _record_timing("notes", notes_started)

            index_started = time.perf_counter()
            index_page = _render_package_index_html(
                render_package,
                render_manifest,
                generated_at,
                run_pages,
                run_text_paths,
                artifact_archive_paths,
                skipped_items,
            )
            index_bytes = index_page.encode("utf-8")
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "index.html",
                index_bytes,
                projected_bytes,
                max_archive_bytes,
            )
            _record_timing("index", index_started)
            readme_started = time.perf_counter()
            readme = _render_package_readme(
                render_package,
                render_manifest,
                generated_at,
                run_pages,
                run_text_paths,
                artifact_archive_paths,
                skipped_items,
            )
            readme_bytes = readme.encode("utf-8")
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "README.md",
                readme_bytes,
                projected_bytes,
                max_archive_bytes,
            )
            _record_timing("readme", readme_started)
            skipped_items_started = time.perf_counter()
            if skipped_items:
                skipped_item_bytes = (
                    json.dumps({"items": skipped_items}, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8")
                projected_bytes = _write_bounded_archive_entry(
                    archive,
                    "skipped-items.json",
                    skipped_item_bytes,
                    projected_bytes,
                    max_archive_bytes,
                )
            _record_timing("skipped_items", skipped_items_started)
            zip_finalize_started = time.perf_counter()
        _record_timing("zip_finalize", zip_finalize_started)
    except Exception:
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        raise
    final_archive_bytes = os.path.getsize(archive_path)
    metrics = {
        **timings,
        "duration_ms": _elapsed_ms(build_started),
        "projected_bytes": projected_bytes,
        "archive_bytes": final_archive_bytes,
        "max_archive_bytes": max_archive_bytes,
        "skipped_artifacts": len(skipped_artifacts),
        "skipped_items": len(skipped_items),
        "selected_runs": _package_selected_id_count(manifest, "run_ids"),
        "selected_transcripts": _package_selected_id_count(manifest, "transcript_run_ids"),
        "selected_findings": _package_selected_id_count(manifest, "finding_ids"),
        "selected_artifacts": _package_selected_id_count(manifest, "artifact_ids"),
        "selected_targets": _package_selected_id_count(manifest, "target_ids"),
    }
    return {
        "filename": _package_archive_name(render_package),
        "mimetype": "application/zip",
        "path": archive_path,
        "byte_size": final_archive_bytes,
        "skipped_artifacts": skipped_artifacts,
        "skipped_items": skipped_items,
        "metrics": metrics,
    }


def _save_new_package_metadata(conn, session_id, package_id, labels, notes):
    label_values = [str(label or "").strip() for label in (labels or []) if str(label or "").strip()]
    for label in label_values:
        session_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_labels WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if _quota_exceeded(
            int(session_count["count"] or 0) if session_count else 0,
            "max_entity_labels_per_session",
            5000,
        ):
            _raise_quota("label quota exceeded for this session")
        for _ in range(10):
            label_id = _new_entity_label_id()
            result = conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, 'package', ?, ?, 'manual', ?) "
                "ON CONFLICT(id) DO NOTHING",
                (label_id, session_id, package_id, label, _now()),
            )
            if result.rowcount:
                break
        else:
            raise ProjectWorkspaceError("could not allocate an entity label id")
    body = _trim_text(notes, MAX_ENTITY_NOTE_BODY_LEN)
    if not body:
        return
    session_count = conn.execute(
        "SELECT COUNT(*) AS count FROM entity_notes WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if _quota_exceeded(
        int(session_count["count"] or 0) if session_count else 0,
        "max_entity_notes_per_session",
        2000,
    ):
        _raise_quota("note quota exceeded for this session")
    now = _now()
    for _ in range(10):
        note_id = _new_entity_note_id()
        result = conn.execute(
            "INSERT INTO entity_notes "
            "(id, session_id, entity_type, entity_id, body, created, updated) "
            "VALUES (?, ?, 'package', ?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            (note_id, session_id, package_id, body, now, now),
        )
        if result.rowcount:
            return
    raise ProjectWorkspaceError("could not allocate an entity note id")


def create_evidence_package(session_id, project_id, data):
    payload = _normalize_evidence_package_payload(data)
    summary = get_project_summary(session_id, project_id)
    if summary is None:
        return None
    summary["artifacts"] = _list_all_project_artifacts(session_id, project_id) or []
    findings = list_project_findings(session_id, project_id) or []
    manifest = _evidence_manifest_from_summary(summary, payload, findings)
    redaction_rules = _package_redaction_rules(payload["redaction_mode"])
    if redaction_rules:
        manifest = _redact_package_manifest(manifest, redaction_rules)
        payload["name"] = apply_redaction_rules(payload["name"], redaction_rules)
        payload["description"] = apply_redaction_rules(payload["description"], redaction_rules)
    created = _now()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            [session_id, project_id],
        ).fetchone()
        if _quota_exceeded(
            int(row["count"] or 0) if row else 0,
            "max_evidence_packages_per_project",
            25,
        ):
            _raise_quota("evidence package quota exceeded for this project")
        for _ in range(10):
            package_id = _new_evidence_package_id()
            result = conn.execute(
                "INSERT INTO evidence_packages "
                "(id, session_id, project_id, name, description, redaction_mode, "
                "include_artifacts, manifest, status, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?) "
                "ON CONFLICT(id) DO NOTHING",
                (
                    package_id,
                    session_id,
                    project_id,
                    payload["name"],
                    payload["description"],
                    payload["redaction_mode"],
                    dialect_for_backend(DB_BACKEND).boolean_param(payload["include_artifacts"]),
                    dialect_for_backend(DB_BACKEND).json_param(manifest),
                    created,
                    created,
                ),
            )
            if result.rowcount:
                _save_new_package_metadata(
                    conn,
                    session_id,
                    package_id,
                    payload["labels"],
                    payload["notes"],
                )
                conn.commit()
                return get_evidence_package(session_id, project_id, package_id)
        raise ProjectWorkspaceError("could not allocate a package id")


def delete_evidence_package(session_id, project_id, package_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id FROM evidence_packages WHERE session_id = ? AND project_id = ? AND id = ?",
            (session_id, project_id, package_id),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "DELETE FROM entity_labels WHERE entity_type = 'package' AND entity_id = ?",
            (package_id,),
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE entity_type = 'package' AND entity_id = ?",
            (package_id,),
        )
        result = conn.execute(
            "DELETE FROM evidence_packages WHERE session_id = ? AND project_id = ? AND id = ?",
            (session_id, project_id, package_id),
        )
        conn.commit()
    return result.rowcount > 0


def _project_finding_page_payload(
    findings,
    total,
    limit,
    offset,
    group_counts=None,
    collapsed_group_counts=None,
    group_order=None,
    has_more=None,
):
    return {
        "findings": findings,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": bool(has_more) if has_more is not None else offset + len(findings) < total,
        "group_counts": group_counts if isinstance(group_counts, dict) else {},
        "collapsed_group_counts": collapsed_group_counts if isinstance(collapsed_group_counts, dict) else {},
        "group_order": group_order if isinstance(group_order, list) else [],
    }


def _project_finding_source_exists_sql():
    return (
        "("
        "EXISTS ("
        "  SELECT 1 FROM findings_occurrences source_fo "
        "  JOIN runs source_run ON source_run.id = source_fo.run_id "
        "  WHERE source_fo.finding_id = f.id AND source_run.session_id = f.session_id"
        ") "
        "OR EXISTS ("
        "  SELECT 1 FROM runs source_direct "
        "  WHERE source_direct.session_id = f.session_id "
        "  AND ("
        "    source_direct.id = f.run_id "
        "    OR source_direct.id = f.first_run_id "
        "    OR source_direct.id = f.last_run_id"
        "  )"
        ")"
        ")"
    )


def list_project_findings(session_id, project_id, filters=None, *, limit=None, offset=0, include_total=False):
    filters = filters if isinstance(filters, dict) else {}
    paginated = limit is not None or include_total
    safe_limit = max(1, min(int(limit or 50), 200)) if paginated else None
    safe_offset = max(0, int(offset or 0)) if paginated else 0
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        run_ids = _metadata_filter_values(filters, "run_id", MAX_ENTITY_ID_LEN)
        target_ids = _metadata_filter_values(filters, "target_id", MAX_ENTITY_ID_LEN)
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            target_count = conn.execute(
                "SELECT COUNT(*) AS count FROM project_links "
                "WHERE project_id = ? AND entity_type = 'atlas_entity' "
                f"AND entity_id IN ({placeholders})",  # nosec
                (project_id, *target_ids),
            ).fetchone()
            if not target_count or int(target_count["count"] or 0) != len(target_ids):
                return _project_finding_page_payload([], 0, safe_limit or 0, safe_offset) if paginated else []
        review_states = _metadata_filter_values(filters, "review_state", 32, lower=True)
        if review_states:
            if any(review_state not in FINDING_REVIEW_STATES for review_state in review_states):
                raise ProjectWorkspaceError(
                    "finding review_state must be new, reviewed, important, false_positive, or needs_followup"
                )
        scope = _trim_text(filters.get("scope"), 64)
        severity = _trim_text(filters.get("severity"), 64).lower()
        labels = _metadata_filter_values(filters, "label", MAX_LABEL_LEN)
        note_state = _trim_text(filters.get("note_state"), 32).lower()
        if note_state:
            if note_state not in {"noted", "unnoted"}:
                raise ProjectWorkspaceError("note_state must be noted or unnoted")
        orphan_filter = _trim_text(filters.get("orphan_filter") or "hide", 32).lower()
        if orphan_filter not in {"hide", "only", "all"}:
            orphan_filter = "hide"
        collapsed_groups = _metadata_filter_values(filters, "collapsed_group", MAX_ENTITY_ID_LEN)
        include_collapsed_group_counts = (
            _trim_text(filters.get("include_collapsed_group_counts") or "1", 16).lower()
            not in {"0", "false", "no", "off"}
        )
        include_group_counts = (
            _trim_text(filters.get("include_group_counts") or "1", 16).lower()
            not in {"0", "false", "no", "off"}
        )
        known_total = max(0, int(filters.get("known_total") or 0)) if str(filters.get("known_total") or "").isdigit() else 0
        command_root = _trim_text(filters.get("command_root"), 128)
        source_exists_sql = _project_finding_source_exists_sql()
        source_run_expr = (
            "COALESCE(NULLIF(f.last_run_id, ''), NULLIF(f.run_id, ''), NULLIF(f.first_run_id, ''))"
        )
        latest_occurrence_run_expr = (
            "(SELECT lfo.run_id FROM findings_occurrences lfo "
            "WHERE lfo.finding_id = f.id "
            "ORDER BY lfo.seen_at DESC, lfo.run_id DESC, lfo.line_number DESC LIMIT 1)"
        )
        latest_occurrence_line_expr = (
            "(SELECT lfo.line_number FROM findings_occurrences lfo "
            "WHERE lfo.finding_id = f.id "
            "ORDER BY lfo.seen_at DESC, lfo.run_id DESC, lfo.line_number DESC LIMIT 1)"
        )
        latest_occurrence_snippet_expr = (
            "(SELECT lfo.snippet FROM findings_occurrences lfo "
            "WHERE lfo.finding_id = f.id "
            "ORDER BY lfo.seen_at DESC, lfo.run_id DESC, lfo.line_number DESC LIMIT 1)"
        )
        page_source_run_expr = (
            "COALESCE(NULLIF(" + latest_occurrence_run_expr + ", ''), "
            "NULLIF(f.last_run_id, ''), NULLIF(f.run_id, ''), NULLIF(f.first_run_id, ''))"
        )
        group_label_expr = "COALESCE(NULLIF(r.command, ''), " + source_run_expr + ")"
        where_clauses = [
            "f.session_id = ?",
            "("
            "EXISTS ("
            "  SELECT 1 FROM findings_occurrences scope_fo "
            "  JOIN project_runs pr ON pr.run_id = scope_fo.run_id "
            "  WHERE scope_fo.finding_id = f.id"
            ") "
            "OR EXISTS ("
            "  SELECT 1 FROM project_runs pr "
            "  WHERE pr.run_id = f.run_id OR pr.run_id = f.first_run_id OR pr.run_id = f.last_run_id"
            ") "
            "OR EXISTS ("
            "  SELECT 1 FROM project_entities pe "
            "  WHERE pe.entity_id = COALESCE(f.entity_id, f.target_id)"
            ")"
            ")",
        ]
        params = [project_id, session_id, project_id, session_id, session_id]
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            where_clauses.append(
                "("
                "EXISTS ("
                "  SELECT 1 FROM findings_occurrences filter_fo "
                "  WHERE filter_fo.finding_id = f.id "
                f"  AND filter_fo.run_id IN ({placeholders})"  # nosec
                ") "
                f"OR f.run_id IN ({placeholders}) "  # nosec
                f"OR f.first_run_id IN ({placeholders}) "  # nosec
                f"OR f.last_run_id IN ({placeholders})"  # nosec
                ")"
            )
            params.extend([*run_ids, *run_ids, *run_ids, *run_ids])
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            where_clauses.append(
                f"(COALESCE(f.entity_id, f.target_id) IN ({placeholders}) OR f.target_id IN ({placeholders}))"  # nosec
            )
            params.extend([*target_ids, *target_ids])
        if review_states:
            placeholders = ",".join("?" for _ in review_states)
            where_clauses.append(f"f.status IN ({placeholders})")  # nosec
            params.extend(review_states)
        if scope:
            where_clauses.append("f.kind = ?")
            params.append(scope)
        if severity:
            where_clauses.append("LOWER(f.severity) = ?")
            params.append(severity)
        if command_root:
            where_clauses.append("(r.command = ? OR r.command LIKE ?)")
            params.extend([command_root, f"{command_root} %"])
        if labels:
            placeholders = ",".join("?" for _ in labels)
            where_clauses.append(
                "EXISTS ("
                "  SELECT 1 FROM entity_labels filter_label "
                "  WHERE filter_label.session_id = f.session_id "
                "  AND filter_label.entity_type = 'finding' "
                "  AND filter_label.entity_id = f.id "
                f"  AND filter_label.label IN ({placeholders})"  # nosec
                ")"
            )
            params.extend(labels)
        if note_state == "noted":
            where_clauses.append(
                "EXISTS ("
                "  SELECT 1 FROM entity_notes filter_note "
                "  WHERE filter_note.session_id = f.session_id "
                "  AND filter_note.entity_type = 'finding' "
                "  AND filter_note.entity_id = f.id"
                ")"
            )
        elif note_state == "unnoted":
            where_clauses.append(
                "NOT EXISTS ("
                "  SELECT 1 FROM entity_notes filter_note "
                "  WHERE filter_note.session_id = f.session_id "
                "  AND filter_note.entity_type = 'finding' "
                "  AND filter_note.entity_id = f.id"
                ")"
            )
        if orphan_filter == "hide":
            where_clauses.append(source_exists_sql)
        elif orphan_filter == "only":
            where_clauses.append(f"NOT {source_exists_sql}")

        pre_collapse_where_clauses = list(where_clauses)
        pre_collapse_params = list(params)
        if collapsed_groups:
            placeholders = ",".join("?" for _ in collapsed_groups)
            where_clauses.append(group_label_expr + f" NOT IN ({placeholders})")  # nosec B608
            params.extend(collapsed_groups)

        def build_base_sql(active_where_clauses):
            return (  # nosec B608
                "WITH project_runs AS ("  # nosec B608
                "  SELECT l.entity_id AS run_id FROM project_links l "
                "  JOIN runs r ON r.id = l.entity_id "
                "  WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ?"
                "), project_entities AS ("
                "  SELECT l.entity_id FROM project_links l "
                "  JOIN entities e ON e.id = l.entity_id "
                "  WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND e.session_id = ?"
                "), project_findings AS ("
                "  SELECT f.id, COALESCE(f.last_seen_at, f.created) AS sort_seen "
                "  FROM findings f "
                "  LEFT JOIN runs r ON r.id = "
                + source_run_expr
                + " AND r.session_id = f.session_id "
                "  WHERE "
                + " AND ".join(active_where_clauses)
                + ") "
            )

        base_sql = build_base_sql(where_clauses)
        total = 0
        group_counts = {}
        collapsed_group_counts = {}
        group_order = []
        has_more = None
        page_limit = safe_limit or 0
        if paginated:
            if include_total:
                total_row = conn.execute(  # nosec B608
                    base_sql + "SELECT COUNT(*) AS count FROM project_findings",  # nosec B608
                    params,
                ).fetchone()
                total = int(total_row["count"] or 0) if total_row else 0
            else:
                total = known_total
        query_params = list(params)
        page_sql = ""
        if paginated:
            page_sql = " LIMIT ? OFFSET ?"
            fetch_limit = page_limit + 1 if not include_total else page_limit
            query_params.extend([fetch_limit, safe_offset])
        rows = conn.execute(  # nosec B608
            base_sql  # nosec B608
            + "SELECT f.id, f.session_id, COALESCE(f.entity_id, f.target_id) AS entity_id, "
            "f.subject_key, f.signature_hash, f.severity, f.kind, f.tool_root, "
            "f.first_run_id, f.last_run_id, f.first_seen_at, f.last_seen_at, "
            "f.occurrence_count, f.status, f.fingerprint, f.title, f.raw_line, f.created, "
            + page_source_run_expr
            + " AS run_id, COALESCE("
            + latest_occurrence_line_expr
            + ", f.line_number) AS line_number, "
            "COALESCE("
            + latest_occurrence_snippet_expr
            + ", f.raw_line) AS snippet, r.command AS run_command, "
            "CASE WHEN "
            + source_exists_sql
            + " THEN 1 ELSE 0 END AS source_run_exists "
            "FROM project_findings pf "
            "JOIN findings f ON f.id = pf.id "
            "LEFT JOIN runs r ON r.id = "
            + page_source_run_expr
            + " AND r.session_id = f.session_id "
            "ORDER BY pf.sort_seen DESC, f.id DESC"
            + page_sql,
            query_params,
        ).fetchall()
        if paginated and not include_total and len(rows) > page_limit:
            has_more = True
            rows = rows[:page_limit]
        if paginated and include_group_counts:
            visible_group_labels = []
            visible_group_set = set()
            for row in rows:
                label = str(row["run_command"] or row["run_id"] or "")
                if label and label not in visible_group_set:
                    visible_group_set.add(label)
                    visible_group_labels.append(label)
            collapsed_group_set = {
                str(label or "") for label in collapsed_groups if include_collapsed_group_counts and str(label or "")
            }
            needed_group_labels = []
            needed_group_set = set()
            requested_group_labels = [
                *(collapsed_groups if include_collapsed_group_counts else []),
                *visible_group_labels,
            ]
            for label in requested_group_labels:
                normalized_label = str(label or "")
                if normalized_label and normalized_label not in needed_group_set:
                    needed_group_set.add(normalized_label)
                    needed_group_labels.append(normalized_label)
            if needed_group_labels:
                placeholders = ",".join("?" for _ in needed_group_labels)
                group_rows = conn.execute(  # nosec B608
                    build_base_sql(pre_collapse_where_clauses)  # nosec B608
                    + "SELECT "
                    + group_label_expr
                    + " AS group_label, COUNT(*) AS count, MAX(pf.sort_seen) AS group_sort_seen "
                    "FROM project_findings pf "
                    "JOIN findings f ON f.id = pf.id "
                    "LEFT JOIN runs r ON r.id = "
                    + source_run_expr
                    + " AND r.session_id = f.session_id "
                    "WHERE "
                    + group_label_expr
                    + f" IN ({placeholders}) "  # nosec B608
                    "GROUP BY 1 "
                    "ORDER BY MAX(pf.sort_seen) DESC, group_label ASC",
                    (*pre_collapse_params, *needed_group_labels),
                ).fetchall()
                for group_row in group_rows:
                    label = str(group_row["group_label"] or "")
                    if not label:
                        continue
                    count = int(group_row["count"] or 0)
                    if label in visible_group_set:
                        group_counts[label] = count
                    if label in collapsed_group_set:
                        collapsed_group_counts[label] = count
                    group_order.append(label)
                for label in needed_group_labels:
                    if label not in group_order:
                        group_order.append(label)
        project_target_rows = conn.execute(
            "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity'",
            (project_id,),
        ).fetchall()
        project_target_ids = {str(row["entity_id"] or "") for row in project_target_rows if row["entity_id"]}
        finding_ids = [str(row["id"] or "") for row in rows if row["id"]]
        finding_labels = _entity_labels_by_id(conn, session_id, "finding", finding_ids)
        finding_notes = _entity_notes_by_id(conn, session_id, "finding", finding_ids)

    findings = [
        item for item in (
            _row_to_project_finding(
                row,
                [row["entity_id"]] if row["entity_id"] else [],
                project_target_ids,
            )
            for row in rows
        )
        if item
    ]
    for item in findings:
        finding_id = str(item["id"] or "")
        item["labels"] = finding_labels.get(finding_id, [])
        item["note"] = finding_notes.get(finding_id)
    if paginated:
        return _project_finding_page_payload(
            findings,
            total,
            page_limit,
            safe_offset,
            group_counts,
            collapsed_group_counts,
            group_order,
            has_more,
        )
    return findings


def _project_linked_run_ids(conn, session_id, project_id):
    rows = conn.execute(
        "SELECT l.entity_id AS run_id "
        "FROM project_links l JOIN runs r ON r.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
        "ORDER BY l.created DESC",
        (project_id, session_id),
    ).fetchall()
    return [row["run_id"] for row in rows]


def _project_labeled_run_id(conn, session_id, project_id, label, excluded_run_ids=None):
    excluded = [str(run_id) for run_id in (excluded_run_ids or []) if run_id]
    params = [project_id, session_id, label]
    excluded_sql = ""
    if excluded:
        placeholders = ",".join("?" for _ in excluded)
        excluded_sql = f"AND r.id NOT IN ({placeholders}) "
        params.extend(excluded)
    row = conn.execute(
        "SELECT r.id "  # nosec
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN entity_labels el ON el.entity_type = 'run' AND el.entity_id = r.id "
        "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
        "AND el.session_id = r.session_id AND el.label = ? "
        f"{excluded_sql}"
        "ORDER BY r.started DESC, l.created DESC LIMIT 1",
        params,
    ).fetchone()
    return row["id"] if row else ""


def _run_compare_summary(row):
    if not row:
        return {}
    return {
        "id": row["id"],
        "command": row["command"],
        "started": row["started"],
        "finished": row["finished"],
        "exit_code": row["exit_code"],
        "output_line_count": int(row["output_line_count"] or 0),
        "preview_truncated": bool(row["preview_truncated"]),
        "full_output_available": bool(row["full_output_available"]),
        "full_output_truncated": bool(row["full_output_truncated"]),
    }


def compare_project_runs(session_id, project_id, filters=None):
    filters = filters if isinstance(filters, dict) else {}
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        linked_run_ids = _project_linked_run_ids(conn, session_id, project_id)
        left_run_id = _trim_text(filters.get("left_run_id"), MAX_ENTITY_ID_LEN)
        right_run_id = _trim_text(filters.get("right_run_id"), MAX_ENTITY_ID_LEN)
        baseline_label = _trim_text(filters.get("baseline_label"), MAX_LABEL_LEN)
        if not left_run_id and len(linked_run_ids) >= 1:
            left_run_id = linked_run_ids[0]
        if not right_run_id and baseline_label:
            right_run_id = _project_labeled_run_id(
                conn,
                session_id,
                project_id,
                baseline_label,
                excluded_run_ids=[left_run_id],
            )
            if not right_run_id:
                raise ProjectWorkspaceError("no linked project run matches the baseline label")
        if not right_run_id and len(linked_run_ids) >= 2:
            right_run_id = linked_run_ids[1]
        if not left_run_id or not right_run_id:
            raise ProjectWorkspaceError("project comparison needs two linked runs")
        if left_run_id == right_run_id:
            raise ProjectWorkspaceError("project comparison needs two different linked runs")
        linked = set(linked_run_ids)
        if left_run_id not in linked or right_run_id not in linked:
            raise ProjectWorkspaceError("comparison runs must both be linked to this project")
        run_rows = conn.execute(
            "SELECT id, command, started, finished, exit_code, output_line_count, "
            "preview_truncated, full_output_available, full_output_truncated "
            "FROM runs WHERE session_id = ? AND id IN (?, ?)",
            (session_id, left_run_id, right_run_id),
        ).fetchall()
        runs_by_id = {str(row["id"]): row for row in run_rows}
        if left_run_id not in runs_by_id or right_run_id not in runs_by_id:
            raise ProjectWorkspaceError("comparison runs must both be linked to this project")
        left_findings, left_finding_count, left_findings_truncated = run_comparison.run_finding_compare_items(
            conn, session_id, left_run_id, include_line_number=True
        )
        right_findings, right_finding_count, right_findings_truncated = run_comparison.run_finding_compare_items(
            conn, session_id, right_run_id, include_line_number=True
        )
        left_artifacts, left_artifact_count, left_artifacts_truncated = run_comparison.run_artifact_compare_items(
            conn, session_id, left_run_id
        )
        right_artifacts, right_artifact_count, right_artifacts_truncated = run_comparison.run_artifact_compare_items(
            conn, session_id, right_run_id
        )
    finding_diff = run_comparison.compare_items(left_findings, right_findings)
    artifact_diff = run_comparison.compare_items(left_artifacts, right_artifacts)
    response = {
        "left_run_id": left_run_id,
        "right_run_id": right_run_id,
        "left": {
            **_run_compare_summary(runs_by_id[left_run_id]),
            "persisted_finding_count": left_finding_count,
            "artifact_count": left_artifact_count,
        },
        "right": {
            **_run_compare_summary(runs_by_id[right_run_id]),
            "persisted_finding_count": right_finding_count,
            "artifact_count": right_artifact_count,
        },
        "baseline_label": baseline_label,
        "objects": {
            "findings": finding_diff,
            "artifacts": artifact_diff,
        },
    }
    if any((
        left_findings_truncated,
        right_findings_truncated,
        left_artifacts_truncated,
        right_artifacts_truncated,
    )):
        response["truncated"] = {
            "left": bool(left_findings_truncated or left_artifacts_truncated),
            "right": bool(right_findings_truncated or right_artifacts_truncated),
            "findings": {
                "left": bool(left_findings_truncated),
                "right": bool(right_findings_truncated),
            },
            "artifacts": {
                "left": bool(left_artifacts_truncated),
                "right": bool(right_artifacts_truncated),
            },
            "item_limit": run_comparison.compare_item_limit(),
        }
    return response


def get_active_project(session_id):
    with db_connect() as conn:
        preferences = _load_session_preferences(conn, session_id)
        project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
        if not project_id:
            return None
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "
            "FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
            [session_id, project_id],
        ).fetchone()
        if not row:
            _clear_active_project_preference(conn, session_id)
            conn.commit()
            return None
        project = _row_to_project(row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
    return project


def set_active_project(session_id, project_id):
    project_id = _trim_text(project_id, MAX_ENTITY_ID_LEN)
    if not project_id:
        raise ProjectWorkspaceError("project_id is required")
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "
            "FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
            (session_id, project_id),
        ).fetchone()
        if not row:
            return None
        preferences = _load_session_preferences(conn, session_id)
        preferences[ACTIVE_PROJECT_PREF_KEY] = row["id"]
        _save_session_preferences(conn, session_id, preferences)
        conn.commit()
        project = _row_to_project(row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
    return project


def clear_active_project(session_id):
    with db_connect() as conn:
        cleared = _clear_active_project_preference(conn, session_id)
        conn.commit()
    return cleared


def link_run_to_active_project(conn, session_id, run_id):
    if not _project_auto_link_external_runs_enabled(conn, session_id):
        return None
    preferences = _load_session_preferences(conn, session_id)
    project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if not project_id:
        return None
    project = conn.execute(
        "SELECT id, name, slug FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
        (session_id, project_id),
    ).fetchone()
    if not project:
        _clear_active_project_preference(conn, session_id)
        return None
    run = conn.execute(
        "SELECT command, run_kind FROM runs WHERE session_id = ? AND id = ?",
        (session_id, run_id),
    ).fetchone()
    if not run:
        return None
    run_kind = normalize_run_kind(run["run_kind"], command=str(run["command"] or ""))
    if not is_project_linkable_run_kind(run_kind):
        return None
    created = _now()
    for _ in range(10):
        link_id = _new_project_link_id()
        conn.execute(
            "INSERT INTO project_links "
            "(id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, 'active_project', ?) "
            "ON CONFLICT(project_id, entity_type, entity_id) DO NOTHING",
            (link_id, project_id, run_id, created),
        )
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = 'run' AND entity_id = ?",
            (project_id, run_id),
        ).fetchone()
        if row:
            link = _row_to_link(row)
            if link is not None:
                link["project_name"] = project["name"] or project["slug"] or project["id"]
            return link
    raise ProjectWorkspaceError("could not allocate an active project link id")


def link_active_project_run_entities(conn, session_id, project_id, run_id):
    if not _project_auto_link_run_entities_enabled(conn, session_id):
        return None
    return _link_project_run_entities_on_conn(
        conn,
        session_id,
        project_id,
        [run_id],
        source="active_project",
    )


def _insert_project_link(
    conn,
    project_id,
    entity_type,
    entity_id,
    source,
    *,
    confidence=1.0,
    review_state="confirmed",
    source_detail=None,
):
    entity_type = validate_project_entity_type(entity_type)
    source = validate_project_link_source(source)
    created = _now()
    detail_json = dialect_for_backend(DB_BACKEND).json_param(source_detail if isinstance(source_detail, dict) else {})
    for _ in range(10):
        link_id = _new_project_link_id()
        conn.execute(
            "INSERT INTO project_links "
            "(id, project_id, entity_type, entity_id, source, confidence, review_state, source_detail, updated, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(project_id, entity_type, entity_id) DO NOTHING",
            (link_id, project_id, entity_type, entity_id, source, confidence, review_state, detail_json, created, created),
        )
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            (project_id, entity_type, entity_id),
        ).fetchone()
        if row:
            return _row_to_link(row)
    raise ProjectWorkspaceError("could not allocate a project link id")


def _run_entity_ids_for_project_link(conn, session_id, run_ids):
    normalized_run_ids = [str(run_id or "").strip() for run_id in run_ids]
    normalized_run_ids = [run_id for run_id in normalized_run_ids if run_id]
    if not normalized_run_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_run_ids)
    rows = conn.execute(
        "SELECT linked.id "
        "FROM ("
        "  SELECT e.id, MAX(e.last_seen_at) AS sort_seen_at, MIN(e.canonical_value) AS sort_value "
        "  FROM entity_run_links erl "
        "  JOIN entities e ON e.id = erl.entity_id "
        "  JOIN runs r ON r.id = erl.run_id "
        f"  WHERE r.session_id = ? AND e.session_id = ? AND erl.run_id IN ({placeholders}) "  # nosec
        "  GROUP BY e.id"
        ") linked "
        "ORDER BY linked.sort_seen_at DESC, linked.sort_value ASC",
        [session_id, session_id, *normalized_run_ids],
    ).fetchall()
    return [str(row["id"]) for row in rows if row["id"]]


def _normalize_project_run_ids_payload(data):
    raw_run_ids = data.get("run_ids") if isinstance(data, dict) else None
    if raw_run_ids is None and isinstance(data, dict):
        raw_run_ids = [data.get("run_id")]
    if not isinstance(raw_run_ids, list):
        raise ProjectWorkspaceError("run_ids must be a list")
    if len(raw_run_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        raise ProjectWorkspaceError("too_many")
    run_ids = []
    seen = set()
    for raw_run_id in raw_run_ids:
        run_id = _trim_text(raw_run_id, MAX_ENTITY_ID_LEN)
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        run_ids.append(run_id)
    if not run_ids:
        raise ProjectWorkspaceError("run_ids is required")
    return run_ids


def _project_run_entity_link_stats(conn, project_id, entity_ids):
    stats = {
        "available": len(entity_ids),
        "added": 0,
        "already_linked": 0,
        "rejected": 0,
        "linkable": 0,
    }
    if not entity_ids:
        return stats
    placeholders = ",".join("?" for _ in entity_ids)
    linked_rows = conn.execute(
        "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' "  # nosec
        f"AND entity_id IN ({placeholders})",
        [project_id, *entity_ids],
    ).fetchall()
    linked_ids = {str(row["entity_id"]) for row in linked_rows}
    stats["already_linked"] = len(linked_ids)
    stats["linkable"] = max(0, len(entity_ids) - len(linked_ids))
    return stats


def preview_project_run_entity_links(session_id, project_id, data):
    run_ids = _normalize_project_run_ids_payload(data)
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        run_maps = _bulk_project_run_maps(conn, session_id, run_ids)
        if any(run_id not in run_maps["owned"] for run_id in run_ids):
            raise ProjectWorkspaceNotFound("run not found for this session")
        if any(run_id not in run_maps["linkable"] for run_id in run_ids):
            raise ProjectWorkspaceError("project links only support external runs")
        entity_ids = _run_entity_ids_for_project_link(conn, session_id, run_ids)
        stats = _project_run_entity_link_stats(conn, project_id, entity_ids)
    stats["run_count"] = len(run_ids)
    return stats


def _project_run_entity_unlink_candidates(conn, session_id, project_id, run_ids):
    stats = {
        "available": 0,
        "removable": 0,
        "kept_curated": 0,
        "removed": 0,
        "run_count": len(run_ids),
    }
    if not run_ids:
        return stats, []
    placeholders = ",".join("?" for _ in run_ids)
    rows = conn.execute(
        "SELECT DISTINCT e.id, l.confidence, l.review_state, l.source_detail, "
        "EXISTS ("
        "  SELECT 1 FROM entity_run_links other_erl "
        "  WHERE other_erl.entity_id = e.id "
        f"  AND other_erl.run_id NOT IN ({placeholders})"
        ") AS has_other_runs, "
        "EXISTS ("
        "  SELECT 1 FROM project_links other_l "
        "  WHERE other_l.entity_type = 'atlas_entity' "
        "  AND other_l.entity_id = e.id "
        "  AND other_l.project_id != ?"
        ") AS has_other_projects, "
        "EXISTS ("
        "  SELECT 1 FROM entity_labels lbl "
        "  WHERE lbl.session_id = ? "
        "  AND lbl.entity_type = 'atlas_entity' "
        "  AND lbl.entity_id = e.id"
        ") AS has_labels, "
        "EXISTS ("
        "  SELECT 1 FROM entity_notes note "
        "  WHERE note.session_id = ? "
        "  AND note.entity_type = 'atlas_entity' "
        "  AND note.entity_id = e.id "
        "  AND trim(note.body) != ''"
        ") AS has_note, "
        "EXISTS ("
        "  SELECT 1 FROM findings child_f "
        "  WHERE child_f.session_id = e.session_id "
        "  AND child_f.entity_id = e.id "
        "  AND ("
        "    COALESCE(NULLIF(child_f.status, ''), 'new') != 'new' "
        "    OR COALESCE(NULLIF(child_f.review_state, ''), 'new') != 'new' "
        "    OR EXISTS ("
        "      SELECT 1 FROM project_links child_link "
        "      WHERE child_link.entity_type = 'finding' "
        "      AND child_link.entity_id = child_f.id"
        "    ) "
        "    OR EXISTS ("
        "      SELECT 1 FROM entity_labels child_label "
        "      WHERE child_label.entity_type = 'finding' "
        "      AND child_label.entity_id = child_f.id"
        "    ) "
        "    OR EXISTS ("
        "      SELECT 1 FROM entity_notes child_note "
        "      WHERE child_note.entity_type = 'finding' "
        "      AND child_note.entity_id = child_f.id"
        "    )"
        "  )"
        ") AS has_curated_findings "
        "FROM entity_run_links erl "
        "JOIN entities e ON e.id = erl.entity_id "
        "JOIN runs r ON r.id = erl.run_id "
        "JOIN project_links l ON l.project_id = ? "
        "AND l.entity_type = 'atlas_entity' "
        "AND l.entity_id = e.id "
        "WHERE r.session_id = ? AND e.session_id = ? "  # nosec
        f"AND erl.run_id IN ({placeholders})",
        [
            *run_ids,
            project_id,
            session_id,
            session_id,
            project_id,
            session_id,
            session_id,
            *run_ids,
        ],
    ).fetchall()
    removable_ids = []
    for row in rows:
        stats["available"] += 1
        source_detail = str(row["source_detail"] or "").strip()
        has_default_project_link = (
            abs(float(row["confidence"] or 1.0) - 1.0) < 0.0001
            and str(row["review_state"] or "confirmed") == "confirmed"
            and source_detail in {"", "{}", "null"}
        )
        is_curated = any((
            int(row["has_other_runs"] or 0) > 0,
            int(row["has_other_projects"] or 0) > 0,
            int(row["has_labels"] or 0) > 0,
            int(row["has_note"] or 0) > 0,
            int(row["has_curated_findings"] or 0) > 0,
            not has_default_project_link,
        ))
        if is_curated:
            stats["kept_curated"] += 1
            continue
        removable_ids.append(str(row["id"]))
    stats["removable"] = len(removable_ids)
    return stats, removable_ids


def preview_project_run_entity_unlinks(session_id, project_id, data):
    run_ids = _normalize_project_run_ids_payload(data)
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        run_maps = _bulk_project_run_maps(conn, session_id, run_ids)
        if any(run_id not in run_maps["owned"] for run_id in run_ids):
            raise ProjectWorkspaceNotFound("run not found for this session")
        stats, _ = _project_run_entity_unlink_candidates(conn, session_id, project_id, run_ids)
    return stats


def unlink_project_run_entities(session_id, project_id, run_ids):
    normalized_run_ids = []
    seen = set()
    for raw_run_id in run_ids:
        run_id = _trim_text(raw_run_id, MAX_ENTITY_ID_LEN)
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        normalized_run_ids.append(run_id)
    with db_connect() as conn:
        conn.execute(dialect_for_backend(DB_BACKEND).begin_immediate_sql())
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        run_maps = _bulk_project_run_maps(conn, session_id, normalized_run_ids)
        owned_run_ids = [run_id for run_id in normalized_run_ids if run_id in run_maps["owned"]]
        stats, removable_ids = _project_run_entity_unlink_candidates(conn, session_id, project_id, owned_run_ids)
        if removable_ids:
            placeholders = ",".join("?" for _ in removable_ids)
            result = conn.execute(
                "DELETE FROM project_links WHERE project_id = ? "
                "AND entity_type = 'atlas_entity' "  # nosec
                f"AND entity_id IN ({placeholders})",
                [project_id, *removable_ids],
            )
            stats["removed"] = max(0, int(result.rowcount or 0))
        conn.commit()
    return stats


def _link_project_run_entities_on_conn(conn, session_id, project_id, run_ids, source="manual"):
    source = validate_project_link_source(source)
    normalized_run_ids = [
        _trim_text(run_id, MAX_ENTITY_ID_LEN)
        for run_id in run_ids
    ]
    normalized_run_ids = [run_id for run_id in normalized_run_ids if run_id]
    if not normalized_run_ids:
        return _project_run_entity_link_stats(conn, project_id, [])
    project = conn.execute(
        "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
        [session_id, project_id],
    ).fetchone()
    if not project:
        return None
    run_maps = _bulk_project_run_maps(conn, session_id, normalized_run_ids)
    linkable_run_ids = [run_id for run_id in normalized_run_ids if run_id in run_maps["linkable"]]
    entity_ids = _run_entity_ids_for_project_link(conn, session_id, linkable_run_ids)
    stats = _project_run_entity_link_stats(conn, project_id, entity_ids)
    count_row = conn.execute(
        "SELECT COUNT(*) AS count FROM project_links WHERE project_id = ?",
        [project_id],
    ).fetchone()
    current_count = int(count_row["count"] or 0) if count_row else 0
    limit = int(_config.CFG.get("max_project_links_per_project", 5000) or 5000)
    new_link_budget = max(0, limit - current_count)
    linked_rows = set()
    if entity_ids:
        placeholders = ",".join("?" for _ in entity_ids)
        linked_rows = {
            str(row["entity_id"])
            for row in conn.execute(
                "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' "  # nosec
                f"AND entity_id IN ({placeholders})",
                [project_id, *entity_ids],
            ).fetchall()
        }
    for entity_id in entity_ids:
        if entity_id in linked_rows:
            continue
        if new_link_budget <= 0:
            stats["rejected"] += 1
            continue
        _insert_project_link(conn, project_id, "atlas_entity", entity_id, source)
        stats["added"] += 1
        new_link_budget -= 1
    stats["linkable"] = max(0, stats["available"] - stats["already_linked"])
    stats["run_count"] = len(normalized_run_ids)
    return stats


def link_project_run_entities(session_id, project_id, run_ids, source="manual"):
    with db_connect() as conn:
        conn.execute(dialect_for_backend(DB_BACKEND).begin_immediate_sql())
        stats = _link_project_run_entities_on_conn(conn, session_id, project_id, run_ids, source=source)
        conn.commit()
    return stats


def record_run_file_artifacts(conn, session_id, run_id, artifacts):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    run = conn.execute(
        "SELECT command, run_kind FROM runs WHERE session_id = ? AND id = ?",
        (session_id, run_id),
    ).fetchone()
    if not run:
        return []
    run_kind = normalize_run_kind(run["run_kind"], command=str(run["command"] or ""))
    if not is_project_linkable_run_kind(run_kind):
        return []

    created = _now()
    recorded = []
    seen_paths = set()
    artifact_items = artifacts if isinstance(artifacts, list) else []
    for item in artifact_items:
        if not isinstance(item, dict):
            continue
        workspace_path = _trim_text(item.get("workspace_path"), MAX_ENTITY_ID_LEN)
        if not workspace_path or workspace_path in seen_paths:
            continue
        seen_paths.add(workspace_path)
        display_name = _trim_text(item.get("display_name"), 255) or workspace_path.rsplit("/", 1)[-1]
        kind = _trim_text(item.get("kind") or "unknown", 64) or "unknown"
        detected_by = _trim_text(item.get("detected_by") or "workspace_flag", 64) or "workspace_flag"
        content_type = _trim_text(item.get("content_type"), 128)
        preview_type = _trim_text(item.get("preview_type"), 64)
        content_sha256 = (
            _normalize_sha256(item.get("content_sha256"))
            or _workspace_file_sha256(session_id, workspace_path)
        )
        try:
            byte_size = max(0, int(item.get("byte_size") or 0))
        except (TypeError, ValueError):
            byte_size = 0

        artifact_id = ""
        for _ in range(10):
            candidate_id = _new_run_file_artifact_id()
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
                "detected_by, content_type, preview_type, content_sha256, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO NOTHING",
                (
                    candidate_id,
                    session_id,
                    run_id,
                    workspace_path,
                    display_name,
                    kind,
                    byte_size,
                    detected_by,
                    content_type,
                    preview_type,
                    content_sha256,
                    created,
                ),
            )
            row = conn.execute(
                "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
                "detected_by, content_type, preview_type, content_sha256, created "
                "FROM run_file_artifacts WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            if row:
                artifact_id = row["id"]
                recorded.append({
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "run_id": row["run_id"],
                    "workspace_path": row["workspace_path"],
                    "display_name": row["display_name"],
                    "kind": row["kind"],
                    "byte_size": row["byte_size"],
                    "detected_by": row["detected_by"],
                    "content_type": row["content_type"],
                    "preview_type": row["preview_type"],
                    "content_sha256": row["content_sha256"],
                    "created": row["created"],
                })
                break
        if not artifact_id:
            raise ProjectWorkspaceError("could not allocate a run file artifact id")
    return recorded


def _finding_severity_from_text(text):
    raw_text = str(text or "")
    bracket_match = re.search(r"\[(info|low|medium|high|critical)\]", raw_text, re.I)
    if bracket_match:
        return bracket_match.group(1).lower()
    key_match = re.search(
        r"(?:\"severity\"|'severity'|\bseverity\b|\brisk\b)\s*[:=]\s*[\"']?"
        r"(info|low|medium|high|critical)\b",
        raw_text,
        re.I,
    )
    if key_match:
        return key_match.group(1).lower()
    phrase_match = re.search(r"\b(info|low|medium|high|critical)\s+severity\b", raw_text, re.I)
    if phrase_match:
        return phrase_match.group(1).lower()
    cvss_match = re.search(r"\bcvss\b[^\n\r]{0,32}\bscore\b\s*[:=]?\s*(10(?:\.0)?|[0-9](?:\.\d)?)\b", raw_text, re.I)
    if not cvss_match:
        return ""
    score = float(cvss_match.group(1))
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0:
        return "low"
    return "info"


def _finding_fingerprint(run_id, line_index, text):
    raw = f"{run_id}\x1f{line_index}\x1f{text}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _finding_signature(tool_root, kind, severity, normalized_signal_key, subject_key):
    raw = "\x1f".join((
        str(tool_root or ""),
        str(kind or "finding"),
        str(severity or ""),
        str(normalized_signal_key or ""),
        str(subject_key or ""),
    )).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _normalize_finding_signal_key(text):
    return re.sub(r"\s+", " ", strip_ansi_codes(str(text or ""))).strip().lower()[:512]


def _entry_primary_entity(conn, session_id, entry, seen_at):
    fallback_payload = _target_payload_from_candidate(entry.get("target") if isinstance(entry, dict) else "")
    if fallback_payload:
        try:
            entity_type, canonical_value = _canonical_target_payload(fallback_payload)
        except ProjectWorkspaceError:
            entity_type = ""
            canonical_value = ""
        if entity_type and canonical_value:
            entity_id = upsert_entity(
                conn,
                session_id,
                entity_type,
                canonical_value,
                seen_at=seen_at,
                occurrence_count=0,
            )
            return entity_id, entity_signature(entity_type, canonical_value)
    raw_entities = entry.get("entities") if isinstance(entry, dict) else None
    if not isinstance(raw_entities, list):
        raw_entities = []
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            continue
        normalized = canonicalize_entity_record(raw_entity)
        if not normalized:
            continue
        entity_type, canonical_value = normalized
        entity_id = upsert_entity(
            conn,
            session_id,
            entity_type,
            canonical_value,
            seen_at=seen_at,
            occurrence_count=0,
        )
        return entity_id, entity_signature(entity_type, canonical_value)
    return "", ""


def record_run_findings(conn, session_id, run_id, entries):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    run = conn.execute(
        "SELECT command, run_kind FROM runs WHERE session_id = ? AND id = ?",
        (session_id, run_id),
    ).fetchone()
    if not run:
        return []
    run_kind = normalize_run_kind(run["run_kind"], command=str(run["command"] or ""))
    if not is_project_linkable_run_kind(run_kind):
        return []

    created = _now()
    existing_rows = conn.execute(
        "SELECT DISTINCT finding_id FROM findings_occurrences WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    existing_finding_ids = [str(row["finding_id"] or "") for row in existing_rows]
    conn.execute("DELETE FROM findings_occurrences WHERE run_id = ?", (run_id,))
    recorded = []
    seen_fingerprints = set()
    entry_items = entries if isinstance(entries, list) else []
    tool_root = _command_root(run["command"])
    for fallback_index, entry in enumerate(entry_items):
        if not isinstance(entry, dict):
            continue
        signals = entry.get("signals")
        signal_values = {str(signal) for signal in signals} if isinstance(signals, list) else set()
        if "findings" not in signal_values:
            continue
        raw_line = strip_ansi_codes(str(entry.get("text") or "")).strip()
        if not raw_line:
            continue
        line_index = entry.get("line_index")
        if not isinstance(line_index, int):
            line_index = fallback_index
        fingerprint = _finding_fingerprint(run_id, line_index, raw_line)
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)
        title = _trim_text(raw_line, MAX_FINDING_TITLE_LEN)
        severity = _finding_severity_from_text(raw_line)
        entity_id, entity_sig = _entry_primary_entity(conn, session_id, entry, created)
        signal_key = _normalize_finding_signal_key(raw_line)
        subject_key = entity_sig if entity_id else f"unscoped:{tool_root}:{signal_key}"
        signature_hash = _finding_signature(tool_root, "finding", severity, signal_key, subject_key)
        row = conn.execute(
            "SELECT id FROM findings WHERE session_id = ? AND signature_hash = ?",
            (session_id, signature_hash),
        ).fetchone()
        if row:
            finding_id = str(row["id"])
            conn.execute(
                "UPDATE findings SET run_id = ?, target_id = ?, last_run_id = ?, last_seen_at = ?, "
                "severity = CASE WHEN ? != '' THEN ? ELSE severity END, "
                "title = ?, raw_line = ? WHERE id = ?",
                (run_id, entity_id, run_id, created, severity, severity, title, raw_line, finding_id),
            )
        else:
            finding_id = "fnd_" + hashlib.sha256(
                f"{session_id}\x1f{signature_hash}".encode("utf-8", errors="replace")
            ).hexdigest()[:32]
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, target_id, scope, line_number, review_state, "
                "entity_id, subject_key, signature_hash, severity, kind, tool_root, "
                "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
                "status_updated_at, fingerprint, title, raw_line, created) "
                "VALUES (?, ?, ?, ?, 'finding', ?, 'new', ?, ?, ?, ?, 'finding', ?, ?, ?, ?, ?, 0, 'new', '', ?, ?, ?, ?)",
                (
                    finding_id,
                    session_id,
                    run_id,
                    entity_id,
                    line_index,
                    entity_id or None,
                    subject_key,
                    signature_hash,
                    severity,
                    tool_root,
                    run_id,
                    run_id,
                    created,
                    created,
                    fingerprint,
                    title,
                    raw_line,
                    created,
                ),
            )
        conn.execute(
            "INSERT INTO findings_occurrences "
            "(finding_id, run_id, line_number, snippet, seen_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(finding_id, run_id, line_number) DO NOTHING",
            (finding_id, run_id, line_index, raw_line, created),
        )
        occurrence_row = conn.execute(
            "SELECT COUNT(*) AS count, MIN(seen_at) AS first_seen_at, MAX(seen_at) AS last_seen_at "
            "FROM findings_occurrences WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        last_run = conn.execute(
            "SELECT run_id FROM findings_occurrences WHERE finding_id = ? ORDER BY seen_at DESC, run_id DESC LIMIT 1",
            (finding_id,),
        ).fetchone()
        conn.execute(
            "UPDATE findings SET occurrence_count = ?, first_seen_at = ?, last_seen_at = ?, last_run_id = ? "
            "WHERE id = ?",
            (
                int(occurrence_row["count"] or 0) if occurrence_row else 0,
                occurrence_row["first_seen_at"] if occurrence_row else created,
                occurrence_row["last_seen_at"] if occurrence_row else created,
                last_run["run_id"] if last_run else run_id,
                finding_id,
            ),
        )
        full_row = conn.execute(
            "SELECT f.id, f.session_id, COALESCE(f.entity_id, f.target_id) AS entity_id, "
            "f.subject_key, f.signature_hash, f.severity, "
            "f.kind, f.tool_root, f.first_run_id, f.last_run_id, f.first_seen_at, f.last_seen_at, "
            "f.occurrence_count, f.status, f.fingerprint, f.title, f.raw_line, f.created, "
            "fo.run_id, fo.line_number, fo.snippet "
            "FROM findings f JOIN findings_occurrences fo ON fo.finding_id = f.id "
            "WHERE f.id = ? AND fo.run_id = ? AND fo.line_number = ?",
            (finding_id, run_id, line_index),
        ).fetchone()
        finding = _row_to_finding(full_row)
        if finding:
            finding["target_ids"] = [entity_id] if entity_id else []
            recorded.append(finding)
    if existing_finding_ids:
        for finding_id in existing_finding_ids:
            row = conn.execute(
                "SELECT COUNT(*) AS count, MIN(seen_at) AS first_seen_at, MAX(seen_at) AS last_seen_at "
                "FROM findings_occurrences WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()
            count = int(row["count"] or 0) if row else 0
            if count <= 0:
                conn.execute(
                    "UPDATE findings SET occurrence_count = 0, run_id = '', last_run_id = '', "
                    "first_seen_at = '', last_seen_at = '', line_number = NULL WHERE id = ?",
                    (finding_id,),
                )
                continue
            last_run = conn.execute(
                "SELECT run_id FROM findings_occurrences WHERE finding_id = ? ORDER BY seen_at DESC, run_id DESC LIMIT 1",
                (finding_id,),
            ).fetchone()
            conn.execute(
                "UPDATE findings SET occurrence_count = ?, first_seen_at = ?, last_seen_at = ?, last_run_id = ? "
                "WHERE id = ?",
                (
                    count,
                    row["first_seen_at"] or "",
                    row["last_seen_at"] or "",
                    last_run["run_id"] if last_run else "",
                    finding_id,
                ),
            )
    return recorded


def _normalize_link_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("project link payload must be an object")
    try:
        entity_type = validate_project_entity_type(_trim_text(data.get("entity_type"), 64))
    except ValueError as exc:
        raise ProjectWorkspaceError(str(exc)) from None
    if entity_type not in PROJECT_LINK_ENTITY_TYPES:
        raise ProjectWorkspaceError(f"project links do not support {entity_type}")
    entity_id = _trim_text(data.get("entity_id"), MAX_ENTITY_ID_LEN)
    if not entity_id:
        raise ProjectWorkspaceError("entity_id is required")
    source = validate_project_link_source(_trim_text(data.get("source") or "manual", 64))
    return entity_type, entity_id, source


def _normalize_bulk_link_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("project link payload must be an object")
    try:
        entity_type = validate_project_entity_type(_trim_text(data.get("entity_type"), 64))
    except ValueError as exc:
        raise ProjectWorkspaceError(str(exc)) from None
    if entity_type not in PROJECT_LINK_ENTITY_TYPES:
        raise ProjectWorkspaceError(f"project links do not support {entity_type}")
    raw_ids = data.get("entity_ids")
    if not isinstance(raw_ids, list):
        raise ProjectWorkspaceError("entity_ids must be a list")
    if len(raw_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        raise ProjectWorkspaceError("too_many")
    entity_ids = []
    seen = set()
    for raw_id in raw_ids:
        entity_id = _trim_text(raw_id, MAX_ENTITY_ID_LEN)
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        entity_ids.append(entity_id)
    if not entity_ids:
        raise ProjectWorkspaceError("entity_ids is required")
    source = validate_project_link_source(_trim_text(data.get("source") or "manual", 64))
    return entity_type, entity_ids, source


def _normalize_target_payload(data, *, partial=False):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("target payload must be an object")
    if any(key in data for key in ("label", "labels", "note", "notes")):
        raise ProjectWorkspaceError("target labels and notes use entity metadata routes")
    clean = {}
    if "type" in data or not partial:
        target_type = _trim_text(data.get("type"), 32).lower()
        if target_type not in PROJECT_TARGET_TYPES:
            raise ProjectWorkspaceError("target type must be domain, url, host, or ip")
        clean["type"] = target_type
    if "value" in data or not partial:
        value = _trim_text(data.get("value"), MAX_TARGET_VALUE_LEN)
        if not value:
            raise ProjectWorkspaceError("target value is required")
        clean["value"] = value
    if "source_run_id" in data or not partial:
        clean["source_run_id"] = _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN)
    if "confidence" in data or not partial:
        try:
            confidence = float(data.get("confidence", 1.0))
        except (TypeError, ValueError):
            raise ProjectWorkspaceError("target confidence must be a number") from None
        clean["confidence"] = min(1.0, max(0.0, confidence))
    if "review_state" in data:
        review_state = _trim_text(data.get("review_state"), 32).lower()
        if review_state not in PROJECT_TARGET_REVIEW_STATES:
            raise ProjectWorkspaceError("target review_state must be confirmed, pending, or dismissed")
        clean["review_state"] = review_state
    if "source" in data:
        source = _trim_text(data.get("source"), 32).lower()
        if source not in PROJECT_TARGET_SOURCES:
            raise ProjectWorkspaceError("target source must be user, auto_command, or auto_input_file")
        clean["source"] = source
    if "source_detail" in data:
        source_detail = data.get("source_detail")
        if not isinstance(source_detail, dict):
            raise ProjectWorkspaceError("target source_detail must be an object")
        clean["source_detail"] = {
            _trim_text(key, 64): _trim_text(value, 512)
            for key, value in source_detail.items()
            if _trim_text(key, 64)
        }
    return clean


def _strip_target_token(value):
    return str(value or "").strip().strip("[](){}<>\"'`,;")


def _target_payload_from_candidate(value):
    candidate = _strip_target_token(value)
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return {"type": "url", "value": candidate}
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        address = None
    if address is not None:
        return {"type": "ip", "value": str(address)}
    if _DOMAIN_RE.fullmatch(candidate):
        return {"type": "domain", "value": candidate.lower()}
    return None


def _target_payload_from_typed_value(value, value_type):
    raw_value = _strip_target_token(value)
    raw_type = _trim_text(value_type, 32).lower()
    if not raw_value or raw_type not in PROJECT_TARGET_TYPES | {"target"}:
        return None
    inferred = _target_payload_from_candidate(raw_value)
    if raw_type == "target":
        return inferred
    if inferred and inferred["type"] == raw_type:
        return inferred
    if raw_type in {"domain", "host"} and inferred and inferred["type"] in {"domain", "host", "ip"}:
        return inferred
    if raw_type == "url" and inferred and inferred["type"] == "url":
        return inferred
    if raw_type == "ip":
        try:
            return {"type": "ip", "value": str(ipaddress.ip_address(raw_value))}
        except ValueError:
            return None
    if raw_type == "host" and raw_value and not raw_value.startswith("-"):
        return {"type": "host", "value": raw_value.lower()}
    return None


def _atlas_type_for_target_type(target_type):
    normalized = _trim_text(target_type, 32).lower()
    if normalized == "host":
        return "domain"
    if normalized in {"domain", "url", "ip", "hash", "cve"}:
        return normalized
    return ""


def _canonical_target_payload(payload):
    target_type = _atlas_type_for_target_type((payload or {}).get("type"))
    if not target_type:
        raise ProjectWorkspaceError("Atlas targets support domain, url, host, ip, hash, and cve")
    raw_value = _trim_text((payload or {}).get("value"), MAX_TARGET_VALUE_LEN)
    if not raw_value:
        raise ProjectWorkspaceError("target value is required")
    try:
        canonical_value = canonical_entity(target_type, raw_value)
    except CanonicalizationError as exc:
        raise ProjectWorkspaceError(str(exc)) from None
    return target_type, canonical_value


def _select_project_target_row(conn, session_id, project_id, entity_id):
    return conn.execute(
        "SELECT e.id, l.project_id, e.type, e.canonical_value, "
        "COALESCE(("
        "SELECT erl.run_id FROM entity_run_links erl "
        "JOIN project_links run_link ON run_link.entity_type = 'run' AND run_link.entity_id = erl.run_id "
        "WHERE erl.entity_id = e.id AND run_link.project_id = l.project_id "
        "ORDER BY erl.last_seen_at DESC, erl.run_id DESC LIMIT 1"
        "), '') AS source_run_id, "
        "l.confidence, l.review_state, l.source, l.source_detail, "
        "e.occurrence_count, e.last_seen_at, e.created, COALESCE(NULLIF(l.updated, ''), l.created) AS updated "
        "FROM project_links l JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        "AND e.session_id = ? AND e.id = ?",
        (project_id, session_id, entity_id),
    ).fetchone()


def _project_link_count(conn, project_id, entity_type):
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM project_links WHERE project_id = ? AND entity_type = ?",
        (project_id, entity_type),
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _ensure_project_entity_link(
    conn,
    session_id,
    project_id,
    entity_type,
    canonical_value,
    source,
    *,
    confidence=1.0,
    review_state="confirmed",
    source_detail=None,
):
    source = validate_project_link_source(source)
    detail_json = dialect_for_backend(DB_BACKEND).json_param(source_detail if isinstance(source_detail, dict) else {})
    entity_id = upsert_entity(
        conn,
        session_id,
        entity_type,
        canonical_value,
        seen_at=_now(),
        occurrence_count=0,
    )
    row = conn.execute(
        "SELECT id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
        (project_id, entity_id),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE project_links SET source = ?, confidence = ?, review_state = ?, source_detail = ?, updated = ? "
            "WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
            (source, confidence, review_state, detail_json, _now(), project_id, entity_id),
        )
        return entity_id
    if not row and _quota_exceeded(
        _project_link_count(conn, project_id, "atlas_entity"),
        "max_project_targets_per_project",
        200,
    ):
        _raise_quota("project target quota exceeded for this project")
    _insert_project_link(
        conn,
        project_id,
        "atlas_entity",
        entity_id,
        source,
        confidence=confidence,
        review_state=review_state,
        source_detail=source_detail,
    )
    return entity_id


def _target_payloads_from_target_list_file(session_id, raw_item):
    if not isinstance(raw_item, dict) or str(raw_item.get("source_kind") or "") != "flag":
        return []
    if str(raw_item.get("target_list_file") or "") != "1":
        return []
    workspace_path = _trim_text(raw_item.get("value"), MAX_TARGET_VALUE_LEN)
    if not workspace_path or os.path.isabs(workspace_path):
        return []
    try:
        text = read_workspace_text_file(session_id, workspace_path, _config.CFG)
    except (OSError, WorkspaceError):
        return []
    payloads = []
    seen = set()
    for raw_line in text[:MAX_PROJECT_TARGET_DISCOVERY_FILE_BYTES].splitlines()[:MAX_PROJECT_TARGET_DISCOVERY_FILE_LINES]:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        payload = _target_payload_from_typed_value(line, raw_item.get("value_type"))
        if not payload:
            continue
        key = (payload["type"], payload["value"])
        if key in seen:
            continue
        seen.add(key)
        payloads.append((payload, {
            "kind": "input_file",
            "name": _trim_text(raw_item.get("source_name"), 128),
            "path": workspace_path,
            "value_type": _trim_text(raw_item.get("value_type"), 32),
        }))
    return payloads


def infer_project_target_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("target payload must be an object")
    if any(key in data for key in ("label", "labels", "note", "notes")):
        raise ProjectWorkspaceError("target labels and notes use entity metadata routes")
    explicit = _target_payload_from_candidate(data.get("value"))
    if explicit:
        return {
            **explicit,
            "source_run_id": _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN),
            "confidence": 1.0,
        }
    text = str(data.get("text") or "")
    for match in _URL_RE.finditer(text):
        inferred = _target_payload_from_candidate(match.group(0))
        if inferred:
            return {
                **inferred,
                "source_run_id": _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN),
                "confidence": 0.9,
            }
    for token in re.split(r"\s+", text):
        inferred = _target_payload_from_candidate(token)
        if inferred:
            return {
                **inferred,
                "source_run_id": _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN),
                "confidence": 0.8,
            }
    raise ProjectWorkspaceError("could not infer a project target from the supplied text")


def _normalize_finding_review_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("finding review payload must be an object")
    review_state = _trim_text(data.get("review_state"), 32).lower()
    if review_state not in FINDING_REVIEW_STATES:
        raise ProjectWorkspaceError(
            "finding review_state must be new, reviewed, important, false_positive, or needs_followup"
        )
    return review_state


def _workspace_file_belongs_to_session(session_id, entity_id):
    try:
        path = resolve_workspace_path(session_id, entity_id, _config.CFG)
        return path.is_file()
    except (OSError, WorkspaceError):
        return False


def _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
    if entity_type == "workspace_file":
        return _workspace_file_belongs_to_session(session_id, entity_id)
    if entity_type in {"atlas_entity", "target"}:
        row = conn.execute(
            "SELECT 1 FROM entities WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "project":
        row = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "run":
        row = conn.execute(
            "SELECT 1 FROM runs WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "snapshot":
        row = conn.execute(
            "SELECT 1 FROM snapshots WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "run_file_artifact":
        row = conn.execute(
            "SELECT 1 FROM run_file_artifacts WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "finding":
        row = conn.execute(
            "SELECT 1 FROM findings WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "package":
        row = conn.execute(
            "SELECT 1 FROM evidence_packages WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    else:
        return False
    return row is not None


def _run_is_project_linkable(conn, session_id, run_id):
    row = conn.execute(
        "SELECT command, run_kind FROM runs WHERE session_id = ? AND id = ?",
        (session_id, run_id),
    ).fetchone()
    if not row:
        return False
    return is_project_linkable_run_kind(normalize_run_kind(row["run_kind"], command=str(row["command"] or "")))


def list_project_links(session_id, project_id):
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        rows = conn.execute(
            "SELECT l.id, l.project_id, l.entity_type, l.entity_id, l.source, l.created "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ? "
            "ORDER BY l.created DESC",
            (project_id, session_id, RUN_KIND_EXTERNAL),
        ).fetchall()
    return [_row_to_link(row) for row in rows]


def link_project_entity(session_id, project_id, data):
    entity_type, entity_id, source = _normalize_link_payload(data)
    created = _now()
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            raise ProjectWorkspaceNotFound(f"{entity_type} not found for this session")
        if entity_type == "run" and not _run_is_project_linkable(conn, session_id, entity_id):
            raise ProjectWorkspaceError("project links only support external runs")
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            [project_id, entity_type, entity_id],
        ).fetchone()
        if row:
            return _row_to_link(row)
        count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_links "
            "WHERE project_id = ?",
            [project_id],
        ).fetchone()
        if _quota_exceeded(
            int(count_row["count"] or 0) if count_row else 0,
            "max_project_links_per_project",
            5000,
        ):
            _raise_quota("project link quota exceeded for this project")
        for _ in range(10):
            link_id = _new_project_link_id()
            conn.execute(
                "INSERT INTO project_links "
                "(id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id, entity_type, entity_id) DO NOTHING",
                (link_id, project_id, entity_type, entity_id, source, created),
            )
            row = conn.execute(
                "SELECT id, project_id, entity_type, entity_id, source, created "
                "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
                [project_id, entity_type, entity_id],
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_link(row)
        raise ProjectWorkspaceError("could not allocate a project link id")


def _project_bulk_result(statuses, entity_type, entity_id, status, *, reason=None):
    statuses[status] = statuses.get(status, 0) + 1
    item = (
        {"entity_id": entity_id, "status": status}
        if entity_type == "atlas_entity"
        else {"run_id": entity_id, "status": status}
    )
    if reason:
        item["reason"] = reason
    return item


def _bulk_project_run_maps(conn, session_id, run_ids):
    placeholders = ",".join("?" for _ in run_ids)
    owned_rows = conn.execute(
        f"SELECT id, command, run_kind FROM runs WHERE session_id = ? AND id IN ({placeholders})",  # nosec
        [session_id, *run_ids],
    ).fetchall()
    owned = {str(row["id"]) for row in owned_rows}
    linkable = {
        str(row["id"])
        for row in owned_rows
        if is_project_linkable_run_kind(normalize_run_kind(row["run_kind"], command=str(row["command"] or "")))
    }
    return {
        "owned": owned,
        "linkable": linkable,
    }


def _bulk_project_entity_maps(conn, session_id, entity_type, entity_ids):
    if entity_type == "run":
        return _bulk_project_run_maps(conn, session_id, entity_ids)
    if entity_type != "atlas_entity":
        return {"owned": set(), "linkable": set()}
    placeholders = ",".join("?" for _ in entity_ids)
    rows = conn.execute(
        f"SELECT id FROM entities WHERE session_id = ? AND id IN ({placeholders})",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    owned = {str(row["id"]) for row in rows}
    return {
        "owned": owned,
        "linkable": set(owned),
    }


def link_project_entities(session_id, project_id, data):
    entity_type, entity_ids, source = _normalize_bulk_link_payload(data)
    counts = {
        "added": 0,
        "already_linked": 0,
        "removed": 0,
        "not_linked": 0,
        "not_found": 0,
        "rejected": 0,
    }
    results = []
    with db_connect() as conn:
        conn.execute(dialect_for_backend(DB_BACKEND).begin_immediate_sql())
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        entity_maps = _bulk_project_entity_maps(conn, session_id, entity_type, entity_ids)
        placeholders = ",".join("?" for _ in entity_ids)
        link_rows = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "  # nosec
            "FROM project_links WHERE project_id = ? AND entity_type = ? "
            f"AND entity_id IN ({placeholders})",
            [project_id, entity_type, *entity_ids],
        ).fetchall()
        linked_by_id = {str(row["entity_id"]): _row_to_link(row) for row in link_rows}
        count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_links "
            "WHERE project_id = ?",
            [project_id],
        ).fetchone()
        current_count = int(count_row["count"] or 0) if count_row else 0
        limit = int(_config.CFG.get("max_project_links_per_project", 5000) or 5000)
        new_link_budget = max(0, limit - current_count)
        links = []
        for entity_id in entity_ids:
            if entity_id not in entity_maps["owned"]:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "not_found"))
                continue
            if entity_id not in entity_maps["linkable"]:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "rejected", reason="builtin"))
                continue
            if entity_id in linked_by_id:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "already_linked"))
                continue
            if new_link_budget <= 0:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "rejected", reason="policy_blocked"))
                continue
            link = _insert_project_link(conn, project_id, entity_type, entity_id, source)
            links.append(link)
            new_link_budget -= 1
            results.append(_project_bulk_result(counts, entity_type, entity_id, "added"))
        conn.commit()
    return {"ok": True, "counts": counts, "results": results, "links": links}


def unlink_project_entity(session_id, project_id, data):
    raw = data if isinstance(data, dict) else {}
    entity_type, entity_id, _ = _normalize_link_payload({**raw, "source": "manual"})
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        result = conn.execute(
            "DELETE FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            (project_id, entity_type, entity_id),
        )
        conn.commit()
    return result.rowcount > 0


def unlink_project_entities(session_id, project_id, data):
    entity_type, entity_ids, _ = _normalize_bulk_link_payload({**(data if isinstance(data, dict) else {}), "source": "manual"})
    counts = {
        "added": 0,
        "already_linked": 0,
        "removed": 0,
        "not_linked": 0,
        "not_found": 0,
        "rejected": 0,
    }
    results = []
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        entity_maps = _bulk_project_entity_maps(conn, session_id, entity_type, entity_ids)
        placeholders = ",".join("?" for _ in entity_ids)
        link_rows = conn.execute(
            "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = ? "  # nosec
            f"AND entity_id IN ({placeholders})",
            [project_id, entity_type, *entity_ids],
        ).fetchall()
        linked_ids = {str(row["entity_id"]) for row in link_rows}
        removable_ids = []
        for entity_id in entity_ids:
            if entity_id not in entity_maps["owned"]:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "not_found"))
                continue
            if entity_id not in linked_ids:
                results.append(_project_bulk_result(counts, entity_type, entity_id, "not_linked"))
                continue
            removable_ids.append(entity_id)
            results.append(_project_bulk_result(counts, entity_type, entity_id, "removed"))
        if removable_ids:
            remove_placeholders = ",".join("?" for _ in removable_ids)
            conn.execute(
                "DELETE FROM project_links WHERE project_id = ? AND entity_type = ? "  # nosec
                f"AND entity_id IN ({remove_placeholders})",
                [project_id, entity_type, *removable_ids],
            )
        conn.commit()
    return {"ok": True, "counts": counts, "results": results}


def list_project_targets(session_id, project_id):
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        rows = conn.execute(
            _project_atlas_entity_select_sql(target_only=True),
            (project_id, session_id),
        ).fetchall()
        targets = [_row_to_target(row) for row in rows]
        _attach_target_metadata(conn, session_id, targets)
    return targets


def add_project_target(session_id, project_id, data):
    payload = _normalize_target_payload(data)
    entity_type, canonical_value = _canonical_target_payload(payload)
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        if payload["source_run_id"] and not _entity_belongs_to_session(conn, session_id, "run", payload["source_run_id"]):
            raise ProjectWorkspaceError("source_run_id not found for this session")
        entity_id = _ensure_project_entity_link(
            conn,
            session_id,
            project_id,
            entity_type,
            canonical_value,
            "manual",
            confidence=payload["confidence"],
            review_state=payload.get("review_state", "confirmed"),
            source_detail=payload.get("source_detail"),
        )
        if payload["source_run_id"]:
            conn.execute(
                "INSERT INTO entity_run_links "
                "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                "VALUES (?, ?, ?, ?, 0) "
                "ON CONFLICT(entity_id, run_id) DO NOTHING",
                (entity_id, payload["source_run_id"], _now(), _now()),
            )
        row = _select_project_target_row(conn, session_id, project_id, entity_id)
        target = _row_to_target(row)
        _attach_target_metadata(conn, session_id, [target])
        conn.commit()
        return target


def record_project_target_discoveries(conn, session_id, project_id, run_id, command_inputs):
    project_id = _trim_text(project_id, MAX_ENTITY_ID_LEN)
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    if not project_id or not run_id:
        return []
    project = conn.execute(
        "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
        (session_id, project_id),
    ).fetchone()
    if not project:
        return []
    created = _now()
    recorded = []
    seen_values = set()
    input_items = command_inputs if isinstance(command_inputs, list) else []
    for raw_item in input_items:
        if len(recorded) >= MAX_PROJECT_TARGET_DISCOVERY_PER_RUN:
            break
        if not isinstance(raw_item, dict):
            continue
        is_target_list_file = str(raw_item.get("target_list_file") or "") == "1"
        direct_payload = None if is_target_list_file else _target_payload_from_typed_value(
            raw_item.get("value"),
            raw_item.get("value_type"),
        )
        source_detail = {
            "kind": _trim_text(raw_item.get("source_kind"), 64),
            "name": _trim_text(raw_item.get("source_name"), 128),
            "value_type": _trim_text(raw_item.get("value_type"), 32),
        }
        source_detail = {key: value for key, value in source_detail.items() if value}
        payload_items = [(direct_payload, source_detail, "auto_command", 1.0)] if direct_payload else []
        if not payload_items:
            payload_items.extend(
                (payload, detail, "auto_input_file", 0.85)
                for payload, detail in _target_payloads_from_target_list_file(session_id, raw_item)
            )
        for payload, detail, source, confidence in payload_items:
            if len(recorded) >= MAX_PROJECT_TARGET_DISCOVERY_PER_RUN:
                break
            if not payload:
                continue
            key = (payload["type"], payload["value"])
            if key in seen_values:
                continue
            seen_values.add(key)
            try:
                entity_type, canonical_value = _canonical_target_payload(payload)
            except ProjectWorkspaceError:
                continue
            existing_entity = conn.execute(
                "SELECT id FROM entities WHERE session_id = ? AND type = ? AND signature_hash = ?",
                (session_id, entity_type, entity_signature(entity_type, canonical_value)),
            ).fetchone()
            already_linked = False
            if existing_entity:
                already_linked = conn.execute(
                    "SELECT 1 FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
                    (project_id, existing_entity["id"]),
                ).fetchone() is not None
            entity_id = _ensure_project_entity_link(
                conn,
                session_id,
                project_id,
                entity_type,
                canonical_value,
                source,
                confidence=confidence,
                review_state="pending",
                source_detail=detail,
            )
            conn.execute(
                "INSERT INTO entity_run_links "
                "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                "VALUES (?, ?, ?, ?, 0) "
                "ON CONFLICT(entity_id, run_id) DO NOTHING",
                (entity_id, run_id, created, created),
            )
            if already_linked:
                continue
            row = _select_project_target_row(conn, session_id, project_id, entity_id)
            target = _row_to_target(row)
            if target and all(item.get("id") != target["id"] for item in recorded):
                recorded.append(target)
    return recorded


def update_project_target(session_id, project_id, target_id, data):
    target_id = _trim_text(target_id, MAX_ENTITY_ID_LEN)
    payload = _normalize_target_payload(data, partial=True)
    if not payload:
        raise ProjectWorkspaceError("target update payload is empty")
    with db_connect() as conn:
        current = _select_project_target_row(conn, session_id, project_id, target_id)
        if not current:
            return None
        if "review_state" in payload and payload["review_state"] == "dismissed":
            target = _row_to_target(current)
            if target:
                target["review_state"] = "dismissed"
                target["status"] = "dismissed"
            conn.execute(
                "DELETE FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
                (project_id, target_id),
            )
            conn.commit()
            return target
        target_type = payload.get("type", current["type"])
        value = payload.get("value", current["canonical_value"])
        source_run_id = payload.get("source_run_id", current["source_run_id"])
        if source_run_id and not _entity_belongs_to_session(conn, session_id, "run", source_run_id):
            raise ProjectWorkspaceError("source_run_id not found for this session")
        entity_type, canonical_value = _canonical_target_payload({"type": target_type, "value": value})
        entity_id = _ensure_project_entity_link(
            conn,
            session_id,
            project_id,
            entity_type,
            canonical_value,
            payload.get("source", current["source"]),
            confidence=payload.get("confidence", current["confidence"]),
            review_state=payload.get("review_state", current["review_state"]),
            source_detail=payload.get("source_detail"),
        )
        if entity_id != target_id:
            conn.execute(
                "DELETE FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
                (project_id, target_id),
            )
        if source_run_id:
            conn.execute(
                "INSERT INTO entity_run_links "
                "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                "VALUES (?, ?, ?, ?, 0) "
                "ON CONFLICT(entity_id, run_id) DO NOTHING",
                (entity_id, source_run_id, _now(), _now()),
            )
        row = _select_project_target_row(conn, session_id, project_id, entity_id)
        target = _row_to_target(row)
        _attach_target_metadata(conn, session_id, [target])
        conn.commit()
    return target


def delete_project_target(session_id, project_id, target_id):
    target_id = _trim_text(target_id, MAX_ENTITY_ID_LEN)
    if not target_id:
        raise ProjectWorkspaceError("target id is required")
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        conn.execute(
            "DELETE FROM entity_labels WHERE session_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
            (session_id, target_id),
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE session_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
            (session_id, target_id),
        )
        result = conn.execute(
            "DELETE FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
            (project_id, target_id),
        )
        conn.commit()
    return result.rowcount > 0


def _run_finding_page_payload(findings, total, limit, offset, occurrence_total=0):
    return {
        "findings": findings,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(findings) < total,
        "occurrence_total": occurrence_total,
    }


def list_run_findings(session_id, run_id, *, limit=None, offset=0, include_total=False):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    paginated = limit is not None or include_total
    safe_limit = max(1, min(int(limit or 50), 200)) if paginated else None
    safe_offset = max(0, int(offset or 0)) if paginated else 0
    base_sql = (
        "WITH run_occurrences AS ("
        "  SELECT finding_id, run_id, line_number, snippet, seen_at, "
        "  COUNT(*) OVER (PARTITION BY finding_id) AS run_occurrence_count, "
        "  ROW_NUMBER() OVER ("
        "    PARTITION BY finding_id "
        "    ORDER BY line_number ASC, seen_at ASC, snippet ASC"
        "  ) AS row_num "
        "  FROM findings_occurrences WHERE run_id = ?"
        "), deduped AS ("
        "  SELECT finding_id, run_id, line_number, snippet, seen_at, run_occurrence_count "
        "  FROM run_occurrences WHERE row_num = 1"
        ") "
    )
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, "run", run_id):
            return None
        total = 0
        occurrence_total = 0
        if paginated:
            total_row = conn.execute(
                base_sql
                + "SELECT COUNT(*) AS count, COALESCE(SUM(d.run_occurrence_count), 0) AS occurrence_total "  # nosec B608
                "FROM deduped d JOIN findings f ON f.id = d.finding_id WHERE f.session_id = ?",
                (run_id, session_id),
            ).fetchone()
            total = int(total_row["count"] or 0) if total_row else 0
            occurrence_total = int(total_row["occurrence_total"] or 0) if total_row else 0
        query_params = [run_id, session_id]
        page_sql = ""
        if paginated:
            page_sql = " LIMIT ? OFFSET ?"
            query_params.extend([safe_limit, safe_offset])
        rows = conn.execute(
            base_sql
            + "SELECT f.id, f.session_id, f.entity_id, f.subject_key, f.signature_hash, f.severity, "  # nosec B608
            "f.kind, f.tool_root, f.first_run_id, f.last_run_id, f.first_seen_at, f.last_seen_at, "
            "f.occurrence_count, f.status, f.fingerprint, f.title, f.raw_line, f.created, "
            "d.run_id, d.line_number, d.snippet, d.run_occurrence_count "
            "FROM deduped d JOIN findings f ON f.id = d.finding_id "
            "WHERE f.session_id = ? "
            "ORDER BY d.line_number ASC, d.seen_at ASC, f.id ASC"
            + page_sql,
            query_params,
        ).fetchall()
    findings = []
    for row in rows:
        finding = _row_to_finding(row)
        if finding:
            finding["target_ids"] = [row["entity_id"]] if row["entity_id"] else []
            finding["run_occurrence_count"] = int(row["run_occurrence_count"] or 0)
            findings.append(finding)
    if paginated:
        return _run_finding_page_payload(findings, total, safe_limit, safe_offset, occurrence_total)
    return findings


def update_finding_review_state(session_id, finding_id, data):
    finding_id = _trim_text(finding_id, MAX_ENTITY_ID_LEN)
    if not finding_id:
        raise ProjectWorkspaceError("finding id is required")
    review_state = _normalize_finding_review_payload(data)
    with db_connect() as conn:
        result = conn.execute(
            "UPDATE findings SET status = ?, status_updated_at = ? WHERE session_id = ? AND id = ?",
            (review_state, _now(), session_id, finding_id),
        )
        if result.rowcount <= 0:
            return None
        row = conn.execute(
            "SELECT id, session_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
            "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
            "fingerprint, title, raw_line, created FROM findings WHERE session_id = ? AND id = ?",
            [session_id, finding_id],
        ).fetchone()
        conn.commit()
    return _row_to_finding(row)
