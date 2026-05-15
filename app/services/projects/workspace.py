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
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlparse

import config as _config
import services.runs.comparison as run_comparison
from core.database import (
    db_connect,
    validate_project_entity_type,
    validate_project_link_source,
)
from core.output_signals import strip_ansi_codes
from services.history.permalinks import _font_face_css, _format_duration, _permalink_context
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
    PROJECT_TARGET_SELECT_COLUMNS,
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
    return {
        "id": row["id"],
        "command": row["command"],
        "started": row["started"],
        "finished": row["finished"],
        "exit_code": row["exit_code"],
        "output_line_count": row["output_line_count"],
        "created": row["created"],
        "link_source": row["link_source"],
    }


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
    try:
        source_detail = json.loads(row["source_detail"] or "{}")
    except (TypeError, ValueError):
        source_detail = {}
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
    return finding


def _finding_target_ids_by_finding(conn, session_id, finding_ids, project_id=None):
    ids = [str(finding_id or "") for finding_id in finding_ids if finding_id]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    params = [session_id, *ids]
    if project_id:
        rows = conn.execute(
            "SELECT ft.finding_id, ft.target_id "  # nosec
            "FROM finding_targets ft "
            "JOIN project_targets t ON t.id = ft.target_id "
            f"WHERE ft.session_id = ? AND ft.finding_id IN ({placeholders}) "
            "AND t.project_id = ? "
            "ORDER BY ft.created ASC, ft.id ASC",
            [*params, project_id],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT finding_id, target_id FROM finding_targets "  # nosec
            f"WHERE session_id = ? AND finding_id IN ({placeholders}) "
            "ORDER BY created ASC, id ASC",
            params,
        ).fetchall()
    grouped = {finding_id: [] for finding_id in ids}
    for row in rows:
        finding_id = str(row["finding_id"] or "")
        target_id = str(row["target_id"] or "")
        if finding_id and target_id and target_id not in grouped.setdefault(finding_id, []):
            grouped[finding_id].append(target_id)
    return grouped


def _row_to_evidence_package(row):
    if not row:
        return None
    try:
        manifest = json.loads(row["manifest"] or "{}")
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
    finding_target_result = conn.execute(
        "UPDATE finding_targets SET session_id = ? WHERE session_id = ?",
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
        "migrated_findings": finding_result.rowcount,
        "migrated_finding_targets": finding_target_result.rowcount,
        "migrated_entity_labels": label_result.rowcount,
        "migrated_entity_notes": note_result.rowcount,
        "migrated_evidence_packages": package_result.rowcount,
        "migrated_active_project_preference": migrated_active_project_preference,
    }


def list_projects(session_id, *, include_archived=False):
    sql = (
        "SELECT id, session_id, name, slug, description, status, color, created, updated "
        "FROM projects WHERE session_id = ? ORDER BY updated DESC, created DESC"
    )
    params = (session_id,)
    with db_connect() as conn:
        if not include_archived:
            sql = (
                "SELECT id, session_id, name, slug, description, status, color, created, updated "
                "FROM projects WHERE session_id = ? AND status != 'archived' "
                "ORDER BY updated DESC, created DESC"
            )
        rows = conn.execute(
            sql,
            params,
        ).fetchall()
        projects = [_row_to_project(row) for row in rows]
        _attach_project_notes(conn, session_id, projects)
        _attach_project_labels(conn, session_id, projects)
    return projects


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
        link_rows = conn.execute(
            "SELECT l.id, l.project_id, l.entity_type, l.entity_id, l.source, l.created "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' "
            "AND r.session_id = ? AND r.run_kind = ? "
            "ORDER BY l.created DESC",
            (project_id, session_id, RUN_KIND_EXTERNAL),
        ).fetchall()
        target_rows = conn.execute(
            f"SELECT {PROJECT_TARGET_SELECT_COLUMNS} "  # nosec
            "FROM project_targets WHERE project_id = ? AND review_state != 'dismissed' "
            "ORDER BY type ASC, value COLLATE NOCASE ASC",
            (project_id,),
        ).fetchall()
        run_ids = [row["entity_id"] for row in link_rows if row["entity_type"] == "run"]
        artifact_rows = []
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
            artifact_rows = conn.execute(
                "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "  # nosec
                "detected_by, content_type, preview_type, content_sha256, created "
                f"FROM run_file_artifacts WHERE run_id IN ({placeholders}) "
                "ORDER BY created DESC, id DESC",
                run_ids,
            ).fetchall()
            finding_rows = conn.execute(
                f"SELECT id FROM findings WHERE run_id IN ({placeholders})",  # nosec
                run_ids,
            ).fetchall()
        artifact_ids = [row["id"] for row in artifact_rows]
        finding_ids = [row["id"] for row in finding_rows]
        target_ids = [row["id"] for row in target_rows]
        package_rows = conn.execute(
            "SELECT id FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        ).fetchall()
        package_ids = [row["id"] for row in package_rows]
        run_labels = _entity_labels_by_id(conn, session_id, "run", run_ids)
        run_notes = _entity_notes_by_id(conn, session_id, "run", run_ids)
        artifact_labels = _entity_labels_by_id(conn, session_id, "run_file_artifact", artifact_ids)
        artifact_notes = _entity_notes_by_id(conn, session_id, "run_file_artifact", artifact_ids)
        target_labels = _entity_labels_by_id(conn, session_id, "target", target_ids)
        target_notes = _entity_notes_by_id(conn, session_id, "target", target_ids)
        label_count = (
            _count_entity_metadata_for_ids(conn, "entity_labels", "project", [project_id])
            + _count_entity_metadata_for_ids(conn, "entity_labels", "run", run_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "run_file_artifact", artifact_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "finding", finding_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "target", target_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "package", package_ids)
        )
        note_count = (
            _count_entity_metadata_for_ids(conn, "entity_notes", "project", [project_id])
            + _count_entity_metadata_for_ids(conn, "entity_notes", "run", run_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "run_file_artifact", artifact_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "finding", finding_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "target", target_ids)
            + _count_entity_metadata_for_ids(conn, "entity_notes", "package", package_ids)
        )
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
    runs = []
    for item in (_row_to_project_run(row) for row in run_rows):
        if not item:
            continue
        runs.append({
            **item,
            "labels": run_labels.get(str(item["id"]), []),
            "note": run_notes.get(str(item["id"])),
        })
    artifacts = []
    for item in (_row_to_run_file_artifact(row) for row in artifact_rows):
        if not item:
            continue
        artifacts.append({
            **item,
            **_artifact_availability(session_id, item),
            "labels": artifact_labels.get(str(item["id"]), []),
            "note": artifact_notes.get(str(item["id"])),
        })
    packages = list_evidence_packages(session_id, project_id) or []
    return {
        "project": project,
        "links": links,
        "targets": targets,
        "runs": runs,
        "artifacts": artifacts,
        "packages": packages,
        "counts": {
            "runs": len(run_ids),
            "targets": confirmed_target_count,
            "pending_targets": pending_target_count,
            "artifacts": len(artifacts),
            "findings": len(finding_ids),
            "labels": label_count,
            "notes": note_count,
            "packages": len(package_ids),
        },
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
                "INSERT OR IGNORE INTO projects "
                "(id, session_id, name, slug, description, status, color, created, updated) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)",
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
            "SELECT id FROM project_targets WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        target_ids = [row["id"] for row in target_rows if row["id"]]
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
                "DELETE FROM finding_targets WHERE session_id = ? "  # nosec
                f"AND target_id IN ({placeholders})",
                [session_id, *target_ids],
            )
            _repair_primary_finding_targets(conn, session_id, target_ids)
            conn.execute(
                "DELETE FROM entity_labels WHERE entity_type = 'target' "  # nosec
                f"AND entity_id IN ({placeholders})",
                target_ids,
            )
            conn.execute(
                "DELETE FROM entity_notes WHERE entity_type = 'target' "  # nosec
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
        conn.execute("DELETE FROM project_targets WHERE project_id = ?", (project_id,))
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
                "INSERT OR IGNORE INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, 'package', ?, ?, 'manual', ?)",
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
            "INSERT OR IGNORE INTO entity_notes "
            "(id, session_id, entity_type, entity_id, body, created, updated) "
            "VALUES (?, ?, 'package', ?, ?, ?, ?)",
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
                "INSERT OR IGNORE INTO evidence_packages "
                "(id, session_id, project_id, name, description, redaction_mode, "
                "include_artifacts, manifest, status, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
                (
                    package_id,
                    session_id,
                    project_id,
                    payload["name"],
                    payload["description"],
                    payload["redaction_mode"],
                    1 if payload["include_artifacts"] else 0,
                    json.dumps(manifest, sort_keys=True),
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


def list_project_findings(session_id, project_id, filters=None):
    filters = filters if isinstance(filters, dict) else {}
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        params = [project_id, session_id]
        clauses = [
            "l.project_id = ?",
            "l.entity_type = 'run'",
            "r.session_id = ?",
        ]
        run_ids = _metadata_filter_values(filters, "run_id", MAX_ENTITY_ID_LEN)
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            clauses.append(f"f.run_id IN ({placeholders})")
            params.extend(run_ids)
        target_ids = _metadata_filter_values(filters, "target_id", MAX_ENTITY_ID_LEN)
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            target_count = conn.execute(
                f"SELECT COUNT(*) AS count FROM project_targets WHERE project_id = ? AND id IN ({placeholders})",  # nosec
                (project_id, *target_ids),
            ).fetchone()
            if not target_count or int(target_count["count"] or 0) != len(target_ids):
                return []
            clauses.append(
                "("  # nosec
                f"f.target_id IN ({placeholders}) OR EXISTS ("
                "SELECT 1 FROM finding_targets ft "
                "WHERE ft.session_id = f.session_id AND ft.finding_id = f.id "
                f"AND ft.target_id IN ({placeholders})"
                ")"
                ")"
            )
            params.extend([*target_ids, *target_ids])
        review_states = _metadata_filter_values(filters, "review_state", 32, lower=True)
        if review_states:
            if any(review_state not in FINDING_REVIEW_STATES for review_state in review_states):
                raise ProjectWorkspaceError(
                    "finding review_state must be new, reviewed, important, false_positive, or needs_followup"
                )
            placeholders = ",".join("?" for _ in review_states)
            clauses.append(f"f.review_state IN ({placeholders})")
            params.extend(review_states)
        scope = _trim_text(filters.get("scope"), 64)
        if scope:
            clauses.append("f.scope = ?")
            params.append(scope)
        severity = _trim_text(filters.get("severity"), 64).lower()
        if severity:
            clauses.append("LOWER(f.severity) = ?")
            params.append(severity)
        labels = _metadata_filter_values(filters, "label", MAX_LABEL_LEN)
        if labels:
            placeholders = ",".join("?" for _ in labels)
            clauses.append(
                "EXISTS ("  # nosec
                "SELECT 1 FROM entity_labels el "
                "WHERE el.session_id = ? AND el.entity_type = 'finding' "
                f"AND el.entity_id = f.id AND el.label IN ({placeholders})"
                ")"
            )
            params.extend([session_id, *labels])
        note_state = _trim_text(filters.get("note_state"), 32).lower()
        if note_state:
            if note_state not in {"noted", "unnoted"}:
                raise ProjectWorkspaceError("note_state must be noted or unnoted")
            operator = "EXISTS" if note_state == "noted" else "NOT EXISTS"
            clauses.append(
                f"{operator} ("  # nosec
                "SELECT 1 FROM entity_notes note "
                "WHERE note.session_id = ? AND note.entity_type = 'finding' "
                "AND note.entity_id = f.id"
                ")"
            )
            params.append(session_id)
        rows = conn.execute(
            "SELECT f.id, f.session_id, f.run_id, f.target_id, f.scope, f.title, f.raw_line, "  # nosec
            "f.line_number, f.severity, f.fingerprint, f.review_state, f.created, "
            "r.command AS run_command "
            "FROM project_links l "
            "JOIN runs r ON r.id = l.entity_id "
            "JOIN findings f ON f.run_id = r.id AND f.session_id = r.session_id "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY f.created DESC, f.id DESC",
            params,
        ).fetchall()
        target_rows = conn.execute(
            "SELECT id FROM project_targets WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        project_target_ids = {str(row["id"] or "") for row in target_rows if row["id"]}
        relationship_ids = _finding_target_ids_by_finding(
            conn,
            session_id,
            [row["id"] for row in rows],
            project_id,
        )
        finding_ids = [str(row["id"] or "") for row in rows if row["id"]]
        finding_labels = _entity_labels_by_id(conn, session_id, "finding", finding_ids)
        finding_notes = _entity_notes_by_id(conn, session_id, "finding", finding_ids)

    findings = [
        item for item in (
            _row_to_project_finding(row, relationship_ids.get(str(row["id"])), project_target_ids)
            for row in rows
        )
        if item
    ]
    for item in findings:
        finding_id = str(item["id"] or "")
        item["labels"] = finding_labels.get(finding_id, [])
        item["note"] = finding_notes.get(finding_id)
    command_root = _trim_text(filters.get("command_root"), 128)
    if command_root:
        findings = [item for item in findings if item["command_root"] == command_root]
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
            "INSERT OR IGNORE INTO project_links "
            "(id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, 'active_project', ?)",
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


def _insert_project_link(conn, project_id, entity_type, entity_id, source):
    entity_type = validate_project_entity_type(entity_type)
    source = validate_project_link_source(source)
    created = _now()
    for _ in range(10):
        link_id = _new_project_link_id()
        conn.execute(
            "INSERT OR IGNORE INTO project_links "
            "(id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (link_id, project_id, entity_type, entity_id, source, created),
        )
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            (project_id, entity_type, entity_id),
        ).fetchone()
        if row:
            return _row_to_link(row)
    raise ProjectWorkspaceError("could not allocate a project link id")


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
                "INSERT OR IGNORE INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
                "detected_by, content_type, preview_type, content_sha256, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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


_NMAP_TARGET_WITH_IP_RE = re.compile(r"^(.+?)\s+\(([^)]+)\)$")
_TARGET_BOUNDARY_CHARS = r"A-Za-z0-9._:-"
_PORT_TOKEN_RE = re.compile(r"^\s*(\d{1,5})(?:\s*-\s*(\d{1,5}))?\s*$")
_PORT_TEXT_PATTERNS = [
    re.compile(r"\b(\d{1,5})/(?:tcp|udp)\b", re.I),
    re.compile(r"\bopen\s+port\s+(\d{1,5})\b", re.I),
    re.compile(r"(?<!:):(\d{1,5})(?!\d)"),
]


def _clean_target_candidate(value):
    return str(value or "").strip().strip("[](){}<>'\"`,;")


def _target_candidate_aliases(value):
    raw = _clean_target_candidate(value)
    if not raw:
        return set()
    candidates = [raw]
    report_match = _NMAP_TARGET_WITH_IP_RE.match(raw)
    if report_match:
        candidates.extend([
            _clean_target_candidate(report_match.group(1)),
            _clean_target_candidate(report_match.group(2)),
        ])

    aliases = set()
    for candidate in candidates:
        candidate = _clean_target_candidate(candidate)
        if not candidate:
            continue
        aliases.add(candidate.lower().rstrip("."))
        parsed = urlparse(candidate)
        if parsed.scheme and parsed.hostname:
            aliases.add(parsed.hostname.lower().rstrip("."))
            continue
        no_path = candidate.split("/", 1)[0].strip()
        if no_path.startswith("[") and "]" in no_path:
            host = no_path[1:no_path.index("]")]
        elif no_path.count(":") == 1 and no_path.rsplit(":", 1)[1].isdigit():
            host = no_path.rsplit(":", 1)[0]
        else:
            host = no_path
        host = _clean_target_candidate(host).lower().rstrip(".")
        if host:
            aliases.add(host)
    return aliases


def _target_candidate_ip_addresses(value):
    addresses = []
    for alias in _target_candidate_aliases(value):
        try:
            addresses.append(ipaddress.ip_address(alias))
        except ValueError:
            continue
    return addresses


def _target_row_value(target):
    try:
        return str(target["value"] or "").strip()
    except (KeyError, TypeError):
        return ""


def _target_row_type(target):
    try:
        return str(target["type"] or "").strip().lower()
    except (KeyError, TypeError):
        return ""


def _target_row_id(target):
    try:
        return str(target["id"] or "")
    except (KeyError, TypeError):
        return ""


def _target_row_matches_cidr(target, candidate):
    target_type = _target_row_type(target)
    target_value = _target_row_value(target)
    if target_type != "cidr" and "/" not in target_value:
        return False
    try:
        network = ipaddress.ip_network(target_value, strict=False)
    except ValueError:
        return False
    return any(address.version == network.version and address in network for address in _target_candidate_ip_addresses(candidate))


def _normalize_port(value):
    try:
        port = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def _target_port_ranges(value):
    ranges = []
    for part in re.split(r"[\s,]+", str(value or "").strip()):
        if not part:
            continue
        match = _PORT_TOKEN_RE.match(part)
        if not match:
            continue
        start = _normalize_port(match.group(1))
        end = _normalize_port(match.group(2) or match.group(1))
        if start is None or end is None:
            continue
        ranges.append((min(start, end), max(start, end)))
    return ranges


def _ports_from_text(text):
    ports = []
    seen = set()
    for pattern in _PORT_TEXT_PATTERNS:
        for match in pattern.finditer(str(text or "")):
            port = _normalize_port(match.group(1))
            if port is None or port in seen:
                continue
            seen.add(port)
            ports.append(port)
    return ports


def _target_row_matches_port_set(target, text):
    if _target_row_type(target) != "port_set":
        return False
    ranges = _target_port_ranges(_target_row_value(target))
    if not ranges:
        return False
    return any(
        start <= port <= end
        for port in _ports_from_text(text)
        for start, end in ranges
    )


def _target_id_from_candidate(target_rows, candidate):
    candidate_aliases = _target_candidate_aliases(candidate)
    if not candidate_aliases:
        return ""
    for target in target_rows:
        if _target_row_type(target) == "cidr":
            continue
        target_aliases = _target_candidate_aliases(_target_row_value(target))
        if candidate_aliases.intersection(target_aliases):
            return _target_row_id(target)
    for target in target_rows:
        if _target_row_matches_cidr(target, candidate):
            return _target_row_id(target)
    return ""


def _target_value_matches_text(target, text):
    target_type = _target_row_type(target)
    if target_type == "port_set":
        return _target_row_matches_port_set(target, text)
    if target_type == "cidr":
        return False
    raw_text = str(text or "")
    for alias in sorted(_target_candidate_aliases(_target_row_value(target)), key=len, reverse=True):
        if len(alias) < 3:
            continue
        pattern = rf"(?<![{_TARGET_BOUNDARY_CHARS}]){re.escape(alias)}(?![{_TARGET_BOUNDARY_CHARS}])"
        if re.search(pattern, raw_text, re.I):
            return True
    return False


def _target_ids_for_finding(target_rows, entry, raw_line):
    target_ids = []

    def add(target_id):
        normalized = str(target_id or "")
        if normalized and normalized not in target_ids:
            target_ids.append(normalized)

    if isinstance(entry, dict):
        target_id = _target_id_from_candidate(target_rows, entry.get("target"))
        if target_id:
            add(target_id)
    for target in target_rows:
        if _target_value_matches_text(target, raw_line):
            add(_target_row_id(target))
    return target_ids


def _target_id_for_finding(target_rows, entry, raw_line):
    target_ids = _target_ids_for_finding(target_rows, entry, raw_line)
    return target_ids[0] if target_ids else ""


def _insert_finding_target_relationships(conn, session_id, run_id, finding_id, target_ids, created):
    inserted = []
    for index, target_id in enumerate(target_ids or []):
        normalized = str(target_id or "")
        if not normalized or normalized in inserted:
            continue
        source = "primary_match" if index == 0 else "line_match"
        for _ in range(10):
            conn.execute(
                "INSERT OR IGNORE INTO finding_targets "
                "(id, session_id, finding_id, target_id, run_id, source, confidence, created) "
                "VALUES (?, ?, ?, ?, ?, ?, 1.0, ?)",
                (
                    _new_finding_target_id(),
                    session_id,
                    finding_id,
                    normalized,
                    run_id,
                    source,
                    created,
                ),
            )
            row = conn.execute(
                "SELECT 1 FROM finding_targets "
                "WHERE session_id = ? AND finding_id = ? AND target_id = ?",
                (session_id, finding_id, normalized),
            ).fetchone()
            if row:
                inserted.append(normalized)
                break
        else:
            raise ProjectWorkspaceError("could not allocate a finding target relationship id")
    return inserted


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

    target_rows = conn.execute(
        "SELECT t.id, t.type, t.value "
        "FROM project_targets t "
        "JOIN project_links l ON l.project_id = t.project_id "
        "WHERE l.entity_type = 'run' AND l.entity_id = ? "
        "AND t.review_state != 'dismissed' "
        "ORDER BY LENGTH(t.value) DESC, t.confidence DESC",
        (run_id,),
    ).fetchall()
    created = _now()
    recorded = []
    seen_fingerprints = set()
    entry_items = entries if isinstance(entries, list) else []
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
        target_ids = _target_ids_for_finding(target_rows, entry, raw_line)
        target_id = target_ids[0] if target_ids else ""
        for _ in range(10):
            finding_id = _new_finding_id()
            conn.execute(
                "INSERT OR IGNORE INTO findings "
                "(id, session_id, run_id, target_id, scope, title, raw_line, line_number, "
                "severity, fingerprint, review_state, created) "
                "VALUES (?, ?, ?, ?, 'finding', ?, ?, ?, ?, ?, 'new', ?)",
                (
                    finding_id,
                    session_id,
                    run_id,
                    target_id,
                    title,
                    raw_line,
                    line_index,
                    severity,
                    fingerprint,
                    created,
                ),
            )
            row = conn.execute(
                "SELECT id, session_id, run_id, target_id, scope, title, raw_line, line_number, "
                "severity, fingerprint, review_state, created FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()
            if row:
                relationship_ids = _insert_finding_target_relationships(
                    conn,
                    session_id,
                    run_id,
                    finding_id,
                    target_ids,
                    created,
                )
                finding = _row_to_finding(row)
                if finding:
                    finding["target_ids"] = _finding_target_ids_from_row(row, relationship_ids)
                    recorded.append(finding)
                break
        else:
            raise ProjectWorkspaceError("could not allocate a finding id")
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
    if entity_type != "run":
        raise ProjectWorkspaceError(f"bulk project links do not support {entity_type}")
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
            raise ProjectWorkspaceError("target type must be domain, url, host, ip, cidr, or port_set")
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
        network = ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        network = None
    if network is not None and "/" in candidate:
        return {"type": "cidr", "value": str(network)}
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
    if raw_type == "port_set":
        return {"type": "port_set", "value": raw_value} if _target_port_ranges(raw_value) else None
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
    if raw_type == "cidr":
        try:
            return {"type": "cidr", "value": str(ipaddress.ip_network(raw_value, strict=False))}
        except ValueError:
            return None
    if raw_type == "host" and raw_value and not raw_value.startswith("-"):
        return {"type": "host", "value": raw_value.lower()}
    return None


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
    if entity_type == "atlas_entity":
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
    elif entity_type == "target":
        row = conn.execute(
            "SELECT 1 FROM project_targets t "
            "JOIN projects p ON p.id = t.project_id "
            "WHERE p.session_id = ? AND t.id = ?",
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
            1000,
        ):
            _raise_quota("project link quota exceeded for this project")
        for _ in range(10):
            link_id = _new_project_link_id()
            conn.execute(
                "INSERT OR IGNORE INTO project_links "
                "(id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
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


def _project_bulk_result(statuses, run_id, status, *, reason=None):
    statuses[status] = statuses.get(status, 0) + 1
    item = {"run_id": run_id, "status": status}
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
        conn.execute("BEGIN IMMEDIATE")
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        run_maps = _bulk_project_run_maps(conn, session_id, entity_ids)
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
            "WHERE project_id = ? AND entity_type = 'run'",
            [project_id],
        ).fetchone()
        current_count = int(count_row["count"] or 0) if count_row else 0
        limit = int(_config.CFG.get("max_project_links_per_project", 1000) or 1000)
        new_link_budget = max(0, limit - current_count)
        links = []
        for entity_id in entity_ids:
            if entity_id not in run_maps["owned"]:
                results.append(_project_bulk_result(counts, entity_id, "not_found"))
                continue
            if entity_id not in run_maps["linkable"]:
                results.append(_project_bulk_result(counts, entity_id, "rejected", reason="builtin"))
                continue
            if entity_id in linked_by_id:
                results.append(_project_bulk_result(counts, entity_id, "already_linked"))
                continue
            if new_link_budget <= 0:
                results.append(_project_bulk_result(counts, entity_id, "rejected", reason="policy_blocked"))
                continue
            link = _insert_project_link(conn, project_id, entity_type, entity_id, source)
            links.append(link)
            new_link_budget -= 1
            results.append(_project_bulk_result(counts, entity_id, "added"))
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
        run_maps = _bulk_project_run_maps(conn, session_id, entity_ids)
        placeholders = ",".join("?" for _ in entity_ids)
        link_rows = conn.execute(
            "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = ? "  # nosec
            f"AND entity_id IN ({placeholders})",
            [project_id, entity_type, *entity_ids],
        ).fetchall()
        linked_ids = {str(row["entity_id"]) for row in link_rows}
        removable_ids = []
        for entity_id in entity_ids:
            if entity_id not in run_maps["owned"]:
                results.append(_project_bulk_result(counts, entity_id, "not_found"))
                continue
            if entity_id not in linked_ids:
                results.append(_project_bulk_result(counts, entity_id, "not_linked"))
                continue
            removable_ids.append(entity_id)
            results.append(_project_bulk_result(counts, entity_id, "removed"))
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
            f"SELECT {PROJECT_TARGET_SELECT_COLUMNS} "  # nosec
            "FROM project_targets WHERE project_id = ? AND review_state != 'dismissed' "
            "ORDER BY type ASC, value COLLATE NOCASE ASC",
            [project_id],
        ).fetchall()
        targets = [_row_to_target(row) for row in rows]
        _attach_target_metadata(conn, session_id, targets)
    return targets


def add_project_target(session_id, project_id, data):
    payload = _normalize_target_payload(data)
    created = _now()
    updated = created
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            [session_id, project_id],
        ).fetchone()
        if not project:
            return None
        if payload["source_run_id"] and not _entity_belongs_to_session(conn, session_id, "run", payload["source_run_id"]):
            raise ProjectWorkspaceError("source_run_id not found for this session")
        row = conn.execute(
            f"SELECT {PROJECT_TARGET_SELECT_COLUMNS} "  # nosec
            "FROM project_targets WHERE project_id = ? AND type = ? AND value = ?",
            [project_id, payload["type"], payload["value"]],
        ).fetchone()
        if row:
            if row["review_state"] in {"pending", "dismissed"}:
                updated = _now()
                conn.execute(
                    "UPDATE project_targets SET review_state = 'confirmed', source = 'user', "
                    "source_run_id = ?, confidence = ?, source_detail = '{}', "
                    "last_seen = ?, dismissed_at = '', updated = ? "
                    "WHERE project_id = ? AND id = ?",
                    (
                        payload["source_run_id"],
                        payload["confidence"],
                        updated,
                        updated,
                        project_id,
                        row["id"],
                    ),
                )
                conn.commit()
                row = conn.execute(
                    f"SELECT {PROJECT_TARGET_SELECT_COLUMNS} "  # nosec
                    "FROM project_targets WHERE project_id = ? AND id = ?",
                    [project_id, row["id"]],
                ).fetchone()
            target = _row_to_target(row)
            _attach_target_metadata(conn, session_id, [target])
            return target
        count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_targets WHERE project_id = ?",
            [project_id],
        ).fetchone()
        if _quota_exceeded(
            int(count_row["count"] or 0) if count_row else 0,
            "max_project_targets_per_project",
            200,
        ):
            _raise_quota("project target quota exceeded for this project")
        for _ in range(10):
            target_id = _new_project_target_id()
            conn.execute(
                "INSERT OR IGNORE INTO project_targets "
                "(id, project_id, type, value, source_run_id, confidence, "
                "review_state, source, source_detail, seen_count, last_seen, dismissed_at, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, 'confirmed', 'user', '{}', 1, ?, '', ?, ?)",
                (
                    target_id,
                    project_id,
                    payload["type"],
                    payload["value"],
                    payload["source_run_id"],
                    payload["confidence"],
                    created,
                    created,
                    updated,
                ),
            )
            row = conn.execute(
                f"SELECT {PROJECT_TARGET_SELECT_COLUMNS} "  # nosec
                "FROM project_targets WHERE project_id = ? AND type = ? AND value = ?",
                [project_id, payload["type"], payload["value"]],
            ).fetchone()
            if row:
                target = _row_to_target(row)
                _attach_target_metadata(conn, session_id, [target])
                conn.commit()
                return target
        raise ProjectWorkspaceError("could not allocate a project target id")


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
            source_detail_json = json.dumps(detail, sort_keys=True)
            row = conn.execute(
                f"SELECT {PROJECT_TARGET_SELECT_COLUMNS} "  # nosec
                "FROM project_targets WHERE project_id = ? AND type = ? AND value = ?",
                (project_id, payload["type"], payload["value"]),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE project_targets SET seen_count = seen_count + 1, last_seen = ?, updated = ? "
                    "WHERE project_id = ? AND id = ?",
                    (created, created, project_id, row["id"]),
                )
                continue
            count_row = conn.execute(
                "SELECT COUNT(*) AS count FROM project_targets WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if _quota_exceeded(
                int(count_row["count"] or 0) if count_row else 0,
                "max_project_targets_per_project",
                200,
            ):
                break
            for _ in range(10):
                target_id = _new_project_target_id()
                conn.execute(
                    "INSERT OR IGNORE INTO project_targets "
                    "(id, project_id, type, value, source_run_id, confidence, "
                    "review_state, source, source_detail, seen_count, last_seen, dismissed_at, created, updated) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, 1, ?, '', ?, ?)",
                    (
                        target_id,
                        project_id,
                        payload["type"],
                        payload["value"],
                        run_id,
                        confidence,
                        source,
                        source_detail_json,
                        created,
                        created,
                        created,
                    ),
                )
                row = conn.execute(
                    f"SELECT {PROJECT_TARGET_SELECT_COLUMNS} "  # nosec
                    "FROM project_targets WHERE project_id = ? AND type = ? AND value = ?",
                    (project_id, payload["type"], payload["value"]),
                ).fetchone()
                if row:
                    target = _row_to_target(row)
                    if target:
                        recorded.append(target)
                    break
            else:
                raise ProjectWorkspaceError("could not allocate a project target id")
    return recorded


def update_project_target(session_id, project_id, target_id, data):
    target_id = _trim_text(target_id, MAX_ENTITY_ID_LEN)
    payload = _normalize_target_payload(data, partial=True)
    if not payload:
        raise ProjectWorkspaceError("target update payload is empty")
    with db_connect() as conn:
        current = conn.execute(
            "SELECT t.id, t.project_id, t.type, t.value, t.source_run_id, t.confidence, "
            "t.review_state, t.source, t.source_detail, t.seen_count, t.last_seen, t.dismissed_at "
            "FROM project_targets t JOIN projects p ON p.id = t.project_id "
            "WHERE p.session_id = ? AND t.project_id = ? AND t.id = ?",
            [session_id, project_id, target_id],
        ).fetchone()
        if not current:
            return None
        target_type = payload.get("type", current["type"])
        value = payload.get("value", current["value"])
        source_run_id = payload.get("source_run_id", current["source_run_id"])
        confidence = payload.get("confidence", current["confidence"])
        review_state = payload.get("review_state", current["review_state"])
        source = payload.get("source", current["source"])
        source_detail = payload.get("source_detail")
        source_detail_json = (
            json.dumps(source_detail, sort_keys=True)
            if isinstance(source_detail, dict)
            else current["source_detail"]
        )
        dismissed_at = current["dismissed_at"]
        if source_run_id and not _entity_belongs_to_session(conn, session_id, "run", source_run_id):
            raise ProjectWorkspaceError("source_run_id not found for this session")
        updated = _now()
        if review_state == "dismissed" and current["review_state"] != "dismissed":
            dismissed_at = updated
        elif review_state != "dismissed":
            dismissed_at = ""
        try:
            conn.execute(
                "UPDATE project_targets SET type = ?, value = ?, "
                "source_run_id = ?, confidence = ?, review_state = ?, source = ?, source_detail = ?, "
                "dismissed_at = ?, updated = ? "
                "WHERE project_id = ? AND id = ?",
                (
                    target_type,
                    value,
                    source_run_id,
                    confidence,
                    review_state,
                    source,
                    source_detail_json,
                    dismissed_at,
                    updated,
                    project_id,
                    target_id,
                ),
            )
        except sqlite3.IntegrityError:
            raise ProjectWorkspaceError("target already exists for this project") from None
        row = conn.execute(
            f"SELECT {PROJECT_TARGET_SELECT_COLUMNS} "  # nosec
            "FROM project_targets WHERE project_id = ? AND id = ?",
            [project_id, target_id],
        ).fetchone()
        target = _row_to_target(row)
        _attach_target_metadata(conn, session_id, [target])
        conn.commit()
    return target


def _repair_primary_finding_targets(conn, session_id, removed_target_ids):
    target_ids = [_trim_text(target_id, MAX_ENTITY_ID_LEN) for target_id in removed_target_ids if target_id]
    if not target_ids:
        return
    placeholders = ",".join("?" for _ in target_ids)
    conn.execute(
        "UPDATE findings SET target_id = COALESCE(("  # nosec
        "SELECT ft.target_id FROM finding_targets ft "
        "JOIN project_targets t ON t.id = ft.target_id "
        "WHERE ft.session_id = findings.session_id AND ft.finding_id = findings.id "
        "ORDER BY ft.created ASC, ft.id ASC LIMIT 1"
        "), '') "
        "WHERE session_id = ? "
        f"AND target_id IN ({placeholders})",
        [session_id, *target_ids],
    )


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
            "DELETE FROM finding_targets WHERE session_id = ? AND target_id = ?",
            (session_id, target_id),
        )
        _repair_primary_finding_targets(conn, session_id, [target_id])
        conn.execute(
            "DELETE FROM entity_labels WHERE session_id = ? AND entity_type = 'target' AND entity_id = ?",
            (session_id, target_id),
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE session_id = ? AND entity_type = 'target' AND entity_id = ?",
            (session_id, target_id),
        )
        result = conn.execute(
            "DELETE FROM project_targets WHERE project_id = ? AND id = ?",
            (project_id, target_id),
        )
        conn.commit()
    return result.rowcount > 0


def list_run_findings(session_id, run_id):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, "run", run_id):
            return None
        rows = conn.execute(
            "SELECT id, session_id, run_id, target_id, scope, title, raw_line, line_number, "
            "severity, fingerprint, review_state, created "
            "FROM findings WHERE session_id = ? AND run_id = ? ORDER BY line_number ASC, created ASC",
            (session_id, run_id),
        ).fetchall()
        relationship_ids = _finding_target_ids_by_finding(
            conn,
            session_id,
            [row["id"] for row in rows],
        )
    findings = []
    for row in rows:
        finding = _row_to_finding(row)
        if finding:
            finding["target_ids"] = _finding_target_ids_from_row(row, relationship_ids.get(str(row["id"])))
            findings.append(finding)
    return findings


def update_finding_review_state(session_id, finding_id, data):
    finding_id = _trim_text(finding_id, MAX_ENTITY_ID_LEN)
    if not finding_id:
        raise ProjectWorkspaceError("finding id is required")
    review_state = _normalize_finding_review_payload(data)
    with db_connect() as conn:
        result = conn.execute(
            "UPDATE findings SET review_state = ? WHERE session_id = ? AND id = ?",
            (review_state, session_id, finding_id),
        )
        if result.rowcount <= 0:
            return None
        row = conn.execute(
            "SELECT id, session_id, run_id, target_id, scope, title, raw_line, line_number, "
            "severity, fingerprint, review_state, created FROM findings WHERE session_id = ? AND id = ?",
            [session_id, finding_id],
        ).fetchone()
        conn.commit()
    return _row_to_finding(row)
