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
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlparse

import config as _config
from database import (
    db_connect,
    validate_project_entity_type,
    validate_project_link_source,
)
from permalinks import _format_duration, _normalize_permalink_lines
from redaction import apply_redaction_rules, redact_line_entries
from run_output_store import load_full_output_entries
from workspace import WorkspaceError, open_workspace_file_for_download, resolve_workspace_path

MAX_PROJECT_NAME_LEN = 120
MAX_PROJECT_DESCRIPTION_LEN = 1000
MAX_PROJECT_COLOR_LEN = 32
MAX_PROJECT_NOTES_LEN = 20000
MAX_ENTITY_ID_LEN = 512
MAX_LABEL_LEN = 80
MAX_ANNOTATION_BODY_LEN = 20000
MAX_AUTHOR_LABEL_LEN = 120
MAX_TARGET_VALUE_LEN = 512
MAX_TARGET_LABEL_LEN = 160
MAX_TARGET_NOTES_LEN = 2000
MAX_FINDING_TITLE_LEN = 240
MAX_PACKAGE_NAME_LEN = 120
MAX_PACKAGE_DESCRIPTION_LEN = 1000
MAX_PROJECT_WORKFLOW_STEPS = 40
ACTIVE_PROJECT_PREF_KEY = "pref_active_project_id"
PROJECT_AUTO_LINK_EXTERNAL_RUNS_PREF_KEY = "pref_project_auto_link_external_runs"

PROJECT_STATUSES = frozenset({"active", "archived"})
PROJECT_LINK_ENTITY_TYPES = frozenset({
    "run",
    "snapshot",
    "workspace_file",
})
ENTITY_METADATA_TYPES = frozenset({
    "project",
    "run",
    "snapshot",
    "workspace_file",
    "run_file_artifact",
    "finding",
    "target",
    "package",
})
ANNOTATION_VISIBILITIES = frozenset({"private"})
PROJECT_TARGET_TYPES = frozenset({"domain", "url", "host", "ip", "cidr", "port_set"})
FINDING_REVIEW_STATES = frozenset({"new", "reviewed", "important", "false_positive", "needs_followup"})
EVIDENCE_PACKAGE_STATUSES = frozenset({"draft"})

_URL_RE = re.compile(r"https?://[^\s<>'\"`]+", re.I)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b",
    re.I,
)


class ProjectWorkspaceError(ValueError):
    """Raised when project workspace input is invalid."""


class ProjectWorkspaceQuotaExceeded(ProjectWorkspaceError):
    """Raised when a project workspace quota would be exceeded."""


class EvidencePackageTooLarge(ProjectWorkspaceQuotaExceeded):
    """Raised when an evidence package archive would exceed configured limits."""


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


def _new_annotation_id() -> str:
    return "ann_" + secrets.token_hex(8)


def _new_project_target_id() -> str:
    return "tgt_" + secrets.token_hex(8)


def _new_finding_id() -> str:
    return "fnd_" + secrets.token_hex(8)


def _new_evidence_package_id() -> str:
    return "pkg_" + secrets.token_hex(8)


def _trim_text(value, limit):
    return str(value or "").strip()[:limit]


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
        "notes": row["notes"] or "",
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


def _load_session_preferences(conn, session_id):
    row = conn.execute(
        "SELECT preferences FROM session_preferences WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return {}
    try:
        preferences = json.loads(row["preferences"] or "{}")
    except (TypeError, ValueError):
        return {}
    return preferences if isinstance(preferences, dict) else {}


def _save_session_preferences(conn, session_id, preferences):
    updated = _now()
    conn.execute(
        "INSERT INTO session_preferences (session_id, preferences, updated) VALUES (?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET preferences = excluded.preferences, updated = excluded.updated",
        (session_id, json.dumps(preferences, sort_keys=True), updated),
    )


def _clear_active_project_preference(conn, session_id, *, project_id=None):
    preferences = _load_session_preferences(conn, session_id)
    current_project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if not current_project_id or (project_id is not None and current_project_id != project_id):
        return False
    preferences.pop(ACTIVE_PROJECT_PREF_KEY, None)
    _save_session_preferences(conn, session_id, preferences)
    return True


def _project_auto_link_external_runs_enabled(conn, session_id):
    preferences = _load_session_preferences(conn, session_id)
    value = str(preferences.get(PROJECT_AUTO_LINK_EXTERNAL_RUNS_PREF_KEY) or "on").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _project_is_active_for_session(conn, session_id, project_id):
    project_id = str(project_id or "")
    if not project_id:
        return False
    row = conn.execute(
        "SELECT 1 FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
        (session_id, project_id),
    ).fetchone()
    return row is not None


def _migrate_active_project_preference(conn, from_session_id, to_session_id):
    source_preferences = _load_session_preferences(conn, from_session_id)
    source_project_id = str(source_preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if not source_project_id:
        return 0
    if not _project_is_active_for_session(conn, to_session_id, source_project_id):
        return 0

    destination_preferences = _load_session_preferences(conn, to_session_id)
    current_project_id = str(destination_preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if current_project_id == source_project_id:
        return 1
    if _project_is_active_for_session(conn, to_session_id, current_project_id):
        return 0

    destination_preferences[ACTIVE_PROJECT_PREF_KEY] = source_project_id
    _save_session_preferences(conn, to_session_id, destination_preferences)
    return 1


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


def _row_to_label(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "label": row["label"],
        "source": row["source"],
        "created": row["created"],
    }


def _row_to_annotation(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "body": row["body"],
        "visibility": row["visibility"],
        "author_label": row["author_label"],
        "created": row["created"],
        "updated": row["updated"],
    }


def _row_to_target(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "type": row["type"],
        "value": row["value"],
        "label": row["label"],
        "notes": row["notes"],
        "source_run_id": row["source_run_id"],
        "confidence": row["confidence"],
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


def _finding_target_ids_from_row(row, target_rows=None):
    target_ids = []
    primary = str(row["target_id"] or "") if row and "target_id" in row.keys() else ""
    if primary:
        target_ids.append(primary)
    for target in target_rows or []:
        if _target_value_matches_text(target, row["raw_line"] if row and "raw_line" in row.keys() else ""):
            target_id = _target_row_id(target)
            if target_id and target_id not in target_ids:
                target_ids.append(target_id)
    return target_ids


def _row_to_project_finding(row, target_rows=None):
    finding = _row_to_finding(row)
    if not finding:
        return None
    finding["target_ids"] = _finding_target_ids_from_row(row, target_rows)
    finding["run_command"] = row["run_command"] or ""
    finding["command_root"] = _command_root(row["run_command"])
    return finding


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
    if redaction_mode == "redacted":
        include_artifacts = False
    return {
        "name": name,
        "description": _trim_text(data.get("description"), MAX_PACKAGE_DESCRIPTION_LEN),
        "redaction_mode": redaction_mode,
        "include_artifacts": include_artifacts,
        "preset": _trim_text(data.get("preset"), 32).lower() or "custom",
        "package_format_version": 1,
        "include_private_annotations": bool(data.get("include_private_annotations")),
        "selection": selection if isinstance(selection, dict) else None,
        "options": options if isinstance(options, dict) else {},
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


def _evidence_manifest_from_summary(summary, payload, findings=None):
    findings = findings if isinstance(findings, list) else []
    selection = payload.get("selection")
    run_ids = _normalized_package_selection_ids(
        selection,
        "run_ids",
        [item.get("id") for item in summary.get("runs", [])],
    )
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
        "transcripts_html": True,
        "raw_artifacts": bool(payload["include_artifacts"]),
    }
    return {
        "format": 1,
        "package_format_version": payload["package_format_version"],
        "project": {
            "id": summary["project"]["id"],
            "name": summary["project"]["name"],
            "slug": summary["project"]["slug"],
            "description": summary["project"].get("description", ""),
            "notes": summary["project"].get("notes", ""),
        },
        "counts": {
            "runs": len(selected_runs),
            "findings": len(selected_findings),
            "artifacts": len(selected_artifacts),
            "targets": len(selected_targets),
        },
        "project_counts": summary["counts"],
        "selected_entity_ids": {
            "run_ids": run_ids,
            "finding_ids": finding_ids,
            "artifact_ids": artifact_ids,
            "target_ids": target_ids,
        },
        "preset": payload["preset"],
        "options": output_options,
        "include_private_annotations": payload["include_private_annotations"],
        "links": summary["links"],
        "runs": selected_runs,
        "findings": selected_findings,
        "targets": selected_targets,
        "artifacts": selected_artifacts,
        "redaction_mode": payload["redaction_mode"],
        "include_artifacts": payload["include_artifacts"],
    }


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
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


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


def _package_output_entry(item):
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


def _package_preview_output_entries(run):
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
        "SELECT r.*, art.rel_path "
        "FROM runs r LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
        f"WHERE r.session_id = ? AND r.id IN ({placeholders})",  # nosec B608
        [session_id, *ids],
    ).fetchall()
    by_id = {str(row["id"]): dict(row) for row in rows}
    return [by_id[run_id] for run_id in ids if run_id in by_id]


def _package_run_output_entries(run, *, cfg=None):
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
        entries = entries[:max_lines]
        entries.append({
            "text": f"[package transcript capped at {max_lines} lines; {hidden} additional lines omitted]",
            "cls": "warn",
            "tsC": "",
            "tsE": "",
        })
    return entries


def _package_css():
    return """
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


def _package_page(title, body):
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{_package_html_escape(title)}</title>\n"
        f"<style>{_package_css()}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def _render_package_run_html(run, entries, manifest, generated_at, *, redaction_rules=None):
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
    normalized = _normalize_permalink_lines(entries, command)
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

    exit_code = run.get("exit_code")
    exit_text = "still running" if exit_code is None else f"exit {exit_code}"
    metrics = [
        ("Started", started or "unknown"),
        ("Finished", finished or "unknown"),
        ("Duration", duration or "unknown"),
        ("Lines", line_count),
        ("Status", exit_text),
    ]
    metric_html = "".join(
        "<div class=\"metric\">"
        f"<span>{_package_html_escape(label)}</span>"
        f"<strong>{_package_html_escape(value)}</strong>"
        "</div>"
        for label, value in metrics
    )
    project_name = (
        manifest.get("project", {}).get("name", "Project")
        if isinstance(manifest.get("project"), dict)
        else "Project"
    )
    run_id_text = _package_html_escape(run.get("id"))
    body = (
        "<main class=\"page\">"
        f"<a href=\"../index.html\">Back to package index</a>"
        f"<div class=\"topline\">{_package_html_escape(project_name)} evidence package</div>"
        f"<h1>{_package_html_escape(command or run.get('id'))}</h1>"
        f"<p class=\"subtitle mono\">Run {run_id_text} · generated {_package_html_escape(generated_at)}</p>"
        f"<section class=\"grid\">{metric_html}</section>"
        "<h2>Transcript</h2>"
        f"<section class=\"transcript\">{''.join(rendered_lines)}</section>"
        "<p class=\"footer\">Generated by darklab shell evidence packages.</p>"
        "</main>"
    )
    return _package_page(command or "Run transcript", body)


def _finding_run_anchor(finding):
    run_id = str(finding.get("run_id") or "")
    line_number = finding.get("line_number")
    if isinstance(line_number, int):
        return f"runs/{_package_html_escape(run_id)}.html#L{line_number + 1}"
    return f"runs/{_package_html_escape(run_id)}.html"


def _render_package_index_html(package, manifest, generated_at, run_pages, artifact_paths, skipped_items):
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

    run_html = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_id = str(run.get("id") or "")
        href = run_pages.get(run_id, "")
        run_html.append(
            "<li>"
            f"<a class=\"mono\" href=\"{_package_html_escape(href)}\">{_package_html_escape(run.get('command') or run_id)}</a>"
            "<div class=\"run-meta\">"
            f"<span>{_package_html_escape(run.get('started') or 'unknown start')}</span>"
            f"<span>{_package_html_escape(run.get('output_line_count') or 0)} lines</span>"
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
        finding_rows.append(
            "<tr>"
            f"<td>{finding_link}</td>"
            f"<td>{_package_html_escape(finding.get('severity') or 'info')}</td>"
            f"<td>{_package_html_escape(finding.get('review_state') or 'new')}</td>"
            f"<td class=\"mono\">{_package_html_escape(_package_short_id(finding.get('run_id')))}</td>"
            f"<td class=\"mono\">{_package_html_escape(finding.get('raw_line') or '')}</td>"
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

    body = (
        "<main class=\"page\">"
        "<div class=\"topline\">darklab shell evidence package</div>"
        f"<h1>{_package_html_escape(package.get('name') or 'Evidence package')}</h1>"
        f"<p class=\"subtitle\">"
        f"{_package_html_escape(project.get('name') or 'Project')} · generated {_package_html_escape(generated_at)}"
        "</p>"
        f"<section class=\"grid\">{metric_html}</section>"
        "<h2>Targets</h2>"
        f"<section class=\"card chips\">{target_html}</section>"
        "<h2>Runs</h2>"
        f"<ul class=\"run-list\">{''.join(run_html)}</ul>"
        "<h2>Findings</h2>"
        "<section class=\"card\">"
        "<table><thead><tr><th>Finding</th><th>Severity</th><th>Status</th><th>Run</th><th>Evidence</th></tr></thead>"
        f"<tbody>{''.join(finding_rows)}</tbody></table>"
        "</section>"
        "<h2>Artifacts</h2>"
        "<section class=\"card\">"
        "<table><thead><tr><th>Artifact</th><th>Workspace path</th><th>Bytes</th><th>Run</th></tr></thead>"
        f"<tbody>{''.join(artifact_rows)}</tbody></table>"
        "</section>"
        f"{skipped_html}"
        "<p class=\"footer\">Generated by darklab shell evidence packages. Redaction mode is recorded in manifest.json.</p>"
        "</main>"
    )
    return _package_page(str(package.get("name") or "Evidence package"), body)


def _render_package_readme(package, manifest, generated_at, run_pages, artifact_paths, skipped_items):
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
    lines.extend(["", "## Targets", ""])
    if targets:
        for target in targets:
            if isinstance(target, dict):
                lines.append(
                    f"- `{_package_markdown_text(target.get('type') or 'target')}` "
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
                f"| `{_package_markdown_text(_package_short_id(run_id))}` "
                f"| `{_package_markdown_text(finding.get('raw_line') or '')}` |"
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
                f"| `{_package_markdown_text(artifact.get('workspace_path') or '')}` "
                f"| {_package_int(artifact.get('byte_size'))} "
                f"| `{_package_markdown_text(_package_short_id(artifact.get('run_id')))}` |"
            )
    else:
        lines.append("- No selected artifacts.")
    lines.extend(["", "## Skipped Items", ""])
    if skipped_items:
        for item in skipped_items:
            label = item.get("label") or item.get("workspace_path") or item.get("id") or "item"
            lines.append(
                f"- `{_package_markdown_text(item.get('kind') or 'item')}` "
                f"{_package_markdown_text(label)}: {_package_markdown_text(item.get('reason') or 'skipped')}"
            )
    else:
        lines.append("- No skipped items.")
    lines.extend([
        "",
        "## Notes",
        "",
        "Generated by darklab shell evidence packages. Redaction mode is recorded in manifest.json.",
        "",
    ])
    return "\n".join(lines)


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
    payload = {
        "format": 1,
        "generated_at": generated_at,
        "count": len(exported),
        "findings": exported,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


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
                f"| `{_package_markdown_text(_package_short_id(run_id))}` "
                f"| `{_package_markdown_text(finding.get('raw_line') or '')}` |"
            )
    else:
        lines.append("- No selected findings.")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


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
    payload = {
        "format": 1,
        "generated_at": generated_at,
        "count": len(exported),
        "targets": exported,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _package_metadata_targets(package, manifest):
    targets = {"project": [str(package.get("project_id") or "")]}
    selected = manifest.get("selected_entity_ids") if isinstance(manifest.get("selected_entity_ids"), dict) else {}
    mapping = {
        "run": "run_ids",
        "finding": "finding_ids",
        "run_file_artifact": "artifact_ids",
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


def _package_metadata_rows(conn, session_id, table, targets):
    rows = []
    for entity_type, entity_ids in targets.items():
        if not entity_ids:
            continue
        placeholders = ",".join("?" for _ in entity_ids)
        if table == "entity_labels":
            rows.extend(conn.execute(
                "SELECT id, entity_type, entity_id, label, source, created "
                f"FROM entity_labels WHERE session_id = ? AND entity_type = ? "  # nosec B608
                f"AND entity_id IN ({placeholders}) ORDER BY entity_type ASC, entity_id ASC, label ASC",
                [session_id, entity_type, *entity_ids],
            ).fetchall())
        elif table == "annotations":
            rows.extend(conn.execute(
                "SELECT id, entity_type, entity_id, body, visibility, author_label, created, updated "
                f"FROM annotations WHERE session_id = ? AND entity_type = ? "  # nosec B608
                f"AND entity_id IN ({placeholders}) ORDER BY entity_type ASC, entity_id ASC, created ASC, id ASC",
                [session_id, entity_type, *entity_ids],
            ).fetchall())
    return rows


def _package_labels_json_bytes(labels, generated_at, redaction_rules=None):
    exported = [
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
    payload = {
        "format": 1,
        "generated_at": generated_at,
        "count": len(exported),
        "labels": exported,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _package_annotations_json_bytes(annotations, generated_at, *, included, redaction_rules=None):
    exported = [
        _redact_package_value({
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "body": row["body"],
            "visibility": row["visibility"],
            "author_label": row["author_label"],
            "created": row["created"],
            "updated": row["updated"],
        }, redaction_rules)
        for row in annotations
    ]
    payload = {
        "format": 1,
        "generated_at": generated_at,
        "include_private_annotations": bool(included),
        "count": len(exported),
        "annotations": exported,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _replace_target_token(command, target_value):
    token = str(target_value or "").strip()
    if not token:
        return str(command or ""), 0
    # Keep replacements scoped to standalone target values. This avoids turning
    # api.example.com into api.{{target}} when the project target is example.com.
    boundary = r"A-Za-z0-9_.-"
    pattern = re.compile(rf"(?<![{boundary}]){re.escape(token)}(?![{boundary}])")
    return pattern.subn("{{target}}", str(command or ""))


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
    label_result = conn.execute(
        "UPDATE entity_labels SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    annotation_result = conn.execute(
        "UPDATE annotations SET session_id = ? WHERE session_id = ?",
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
        "migrated_entity_labels": label_result.rowcount,
        "migrated_annotations": annotation_result.rowcount,
        "migrated_evidence_packages": package_result.rowcount,
        "migrated_active_project_preference": migrated_active_project_preference,
    }


def list_projects(session_id, *, include_archived=False):
    sql = (
        "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
        "FROM projects WHERE session_id = ? ORDER BY updated DESC, created DESC"
    )
    params = (session_id,)
    with db_connect() as conn:
        if not include_archived:
            sql = (
                "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
                "FROM projects WHERE session_id = ? AND status != 'archived' "
                "ORDER BY updated DESC, created DESC"
            )
        rows = conn.execute(
            sql,
            params,
        ).fetchall()
    return [_row_to_project(row) for row in rows]


def get_project(session_id, project_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
            "FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
    return _row_to_project(row)


def _count_rows_for_ids(conn, table, column, ids):
    values = [str(value) for value in ids if value]
    if not values:
        return 0
    placeholders = ",".join("?" for _ in values)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE {column} IN ({placeholders})",  # nosec B608
        values,
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _count_entity_metadata_for_ids(conn, table, entity_type, entity_ids):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return 0
    placeholders = ",".join("?" for _ in values)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE entity_type = ? AND entity_id IN ({placeholders})",  # nosec B608
        [entity_type, *values],
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def get_project_summary(session_id, project_id):
    with db_connect() as conn:
        project_row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
            "FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project_row:
            return None
        link_rows = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? ORDER BY created DESC",
            (project_id,),
        ).fetchall()
        target_rows = conn.execute(
            "SELECT id, project_id, type, value, label, notes, source_run_id, confidence, created, updated "
            "FROM project_targets WHERE project_id = ? ORDER BY type ASC, value COLLATE NOCASE ASC",
            (project_id,),
        ).fetchall()
        package_row = conn.execute(
            "SELECT COUNT(*) AS count FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        ).fetchone()
        run_ids = [row["entity_id"] for row in link_rows if row["entity_type"] == "run"]
        snapshot_ids = [row["entity_id"] for row in link_rows if row["entity_type"] == "snapshot"]
        workspace_file_ids = [row["entity_id"] for row in link_rows if row["entity_type"] == "workspace_file"]
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
                "ORDER BY r.started DESC, l.created DESC",
                (project_id, session_id),
            ).fetchall()
            artifact_rows = conn.execute(
                "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
                "detected_by, content_type, preview_type, content_sha256, created "
                f"FROM run_file_artifacts WHERE run_id IN ({placeholders}) "  # nosec B608
                "ORDER BY created DESC, id DESC",
                run_ids,
            ).fetchall()
            finding_rows = conn.execute(
                f"SELECT id FROM findings WHERE run_id IN ({placeholders})",  # nosec B608
                run_ids,
            ).fetchall()
        artifact_ids = [row["id"] for row in artifact_rows]
        finding_ids = [row["id"] for row in finding_rows]
        label_count = (
            _count_entity_metadata_for_ids(conn, "entity_labels", "project", [project_id])
            + _count_entity_metadata_for_ids(conn, "entity_labels", "run", run_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "snapshot", snapshot_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "workspace_file", workspace_file_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "run_file_artifact", artifact_ids)
            + _count_entity_metadata_for_ids(conn, "entity_labels", "finding", finding_ids)
        )
        annotation_count = (
            _count_entity_metadata_for_ids(conn, "annotations", "project", [project_id])
            + _count_entity_metadata_for_ids(conn, "annotations", "run", run_ids)
            + _count_entity_metadata_for_ids(conn, "annotations", "snapshot", snapshot_ids)
            + _count_entity_metadata_for_ids(conn, "annotations", "workspace_file", workspace_file_ids)
            + _count_entity_metadata_for_ids(conn, "annotations", "run_file_artifact", artifact_ids)
            + _count_entity_metadata_for_ids(conn, "annotations", "finding", finding_ids)
        )
    links = [_row_to_link(row) for row in link_rows]
    targets = [_row_to_target(row) for row in target_rows]
    runs = [item for item in (_row_to_project_run(row) for row in run_rows) if item]
    artifacts = []
    for item in (_row_to_run_file_artifact(row) for row in artifact_rows):
        if not item:
            continue
        artifacts.append({
            **item,
            **_artifact_availability(session_id, item),
        })
    packages = list_evidence_packages(session_id, project_id) or []
    return {
        "project": _row_to_project(project_row),
        "links": links,
        "targets": targets,
        "runs": runs,
        "artifacts": artifacts,
        "packages": packages,
        "counts": {
            "runs": len(run_ids),
            "snapshots": len(snapshot_ids),
            "workspace_files": len(workspace_file_ids),
            "targets": len(targets),
            "artifacts": len(artifacts),
            "findings": len(finding_ids),
            "labels": label_count,
            "annotations": annotation_count,
            "packages": int(package_row["count"] or 0) if package_row else 0,
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
            (session_id,),
        ).fetchone()
        if _quota_exceeded(int(row["count"] or 0) if row else 0, "max_projects_per_session", 100):
            _raise_quota("project quota exceeded for this session")
        for _ in range(10):
            project_id = _new_project_id()
            slug = _allocate_slug(conn, session_id, payload["name"])
            result = conn.execute(
                "INSERT OR IGNORE INTO projects "
                "(id, session_id, name, slug, description, status, color, notes, created, updated) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, '', ?, ?)",
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
            "SELECT id, name, slug, description, status, color, notes "
            "FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not current:
            return None
        name = current["name"]
        slug = current["slug"]
        description = current["description"]
        status = current["status"]
        color = current["color"]
        notes = current["notes"]
        if "name" in payload:
            name = payload["name"]
            slug = _allocate_slug(conn, session_id, payload["name"], project_id=project_id)
        if "description" in payload:
            description = payload["description"]
        if "status" in payload:
            status = payload["status"]
        if "color" in payload:
            color = payload["color"]
        if "notes" in payload:
            notes = payload["notes"]
        conn.execute(
            "UPDATE projects "
            "SET name = ?, slug = ?, description = ?, status = ?, color = ?, notes = ?, updated = ? "
            "WHERE session_id = ? AND id = ?",
            (name, slug, description, status, color, notes, updated, session_id, project_id),
        )
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
        package_rows = conn.execute(
            "SELECT id FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        ).fetchall()
        package_ids = [row["id"] for row in package_rows if row["id"]]
        if package_ids:
            placeholders = ",".join("?" for _ in package_ids)
            conn.execute(
                "DELETE FROM entity_labels WHERE entity_type = 'package' "
                f"AND entity_id IN ({placeholders})",  # nosec B608
                package_ids,
            )
            conn.execute(
                "DELETE FROM annotations WHERE entity_type = 'package' "
                f"AND entity_id IN ({placeholders})",  # nosec B608
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
    return [_row_to_evidence_package(row) for row in rows]


def get_evidence_package(session_id, project_id, package_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, project_id, name, description, redaction_mode, "
            "include_artifacts, manifest, status, created, updated "
            "FROM evidence_packages WHERE session_id = ? AND project_id = ? AND id = ?",
            (session_id, project_id, package_id),
        ).fetchone()
    return _row_to_evidence_package(row)


def build_evidence_package_archive(session_id, project_id, package_id, *, cfg=None):
    package = get_evidence_package(session_id, project_id, package_id)
    if package is None:
        return None
    generated_at = _now()
    manifest = dict(package.get("manifest") or {})
    redaction_rules = _package_redaction_rules(package.get("redaction_mode"), cfg=cfg)
    render_manifest = _redact_package_manifest(manifest, redaction_rules)
    render_package = {
        **package,
        "name": apply_redaction_rules(package["name"], redaction_rules),
        "description": apply_redaction_rules(package["description"], redaction_rules),
    }
    export_manifest = {
        "format": 1,
        "generated_at": generated_at,
        "package": {
            "id": package["id"],
            "name": render_package["name"],
            "description": render_package["description"],
            "redaction_mode": package["redaction_mode"],
            "include_artifacts": package["include_artifacts"],
            "status": package["status"],
            "created": package["created"],
            "updated": package["updated"],
        },
        "manifest": render_manifest,
    }
    manifest_bytes = json.dumps(export_manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    max_archive_bytes = _cfg_mb_bytes("evidence_package_max_mb", 25, cfg=cfg)
    if max_archive_bytes and len(manifest_bytes) > max_archive_bytes:
        raise EvidencePackageTooLarge("evidence package manifest exceeds configured size limit")
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
            archive.writestr("manifest.json", manifest_bytes)
            projected_bytes = len(manifest_bytes)
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
                projected_bytes += len(skipped_bytes)
                if max_archive_bytes and projected_bytes > max_archive_bytes:
                    raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
                archive.writestr("skipped-artifacts.json", skipped_bytes)

            run_pages = {}
            run_ids = []
            selected_entity_ids = manifest.get("selected_entity_ids")
            if isinstance(selected_entity_ids, dict) and isinstance(selected_entity_ids.get("run_ids"), list):
                run_ids = [str(run_id) for run_id in selected_entity_ids["run_ids"] if str(run_id)]
            with db_connect() as conn:
                run_rows = _package_run_rows(conn, session_id, run_ids)
            found_run_ids = {str(row.get("id") or "") for row in run_rows}
            for run_id in run_ids:
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
                entries = _package_run_output_entries(run, cfg=cfg)
                for entry in entries:
                    if str(entry.get("text") or "").startswith("[package transcript capped"):
                        skipped_items.append({
                            "kind": "transcript",
                            "id": run_id,
                            "label": run.get("command") or run_id,
                            "reason": str(entry.get("text") or "").strip("[]"),
                        })
                        break
                run_page = _render_package_run_html(
                    run,
                    entries,
                    render_manifest,
                    generated_at,
                    redaction_rules=redaction_rules,
                )
                run_page_bytes = run_page.encode("utf-8")
                projected_bytes += len(run_page_bytes)
                if max_archive_bytes and projected_bytes > max_archive_bytes:
                    raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
                run_path = f"runs/{run_id}.html"
                run_pages[run_id] = run_path
                archive.writestr(run_path, run_page_bytes)

            findings_json_bytes = _package_findings_json_bytes(render_manifest, generated_at, run_pages)
            projected_bytes += len(findings_json_bytes)
            if max_archive_bytes and projected_bytes > max_archive_bytes:
                raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
            archive.writestr("findings/findings.json", findings_json_bytes)
            findings_markdown_bytes = _package_findings_markdown_bytes(render_manifest, run_pages)
            projected_bytes += len(findings_markdown_bytes)
            if max_archive_bytes and projected_bytes > max_archive_bytes:
                raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
            archive.writestr("findings/findings.md", findings_markdown_bytes)

            targets_json_bytes = _package_targets_json_bytes(render_manifest, generated_at)
            projected_bytes += len(targets_json_bytes)
            if max_archive_bytes and projected_bytes > max_archive_bytes:
                raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
            archive.writestr("targets/targets.json", targets_json_bytes)

            metadata_targets = _package_metadata_targets(package, manifest)
            with db_connect() as conn:
                label_rows = _package_metadata_rows(conn, session_id, "entity_labels", metadata_targets)
                annotation_rows = (
                    _package_metadata_rows(conn, session_id, "annotations", metadata_targets)
                    if render_manifest.get("include_private_annotations")
                    else []
                )
            labels_json_bytes = _package_labels_json_bytes(label_rows, generated_at, redaction_rules)
            projected_bytes += len(labels_json_bytes)
            if max_archive_bytes and projected_bytes > max_archive_bytes:
                raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
            archive.writestr("metadata/labels.json", labels_json_bytes)
            annotations_json_bytes = _package_annotations_json_bytes(
                annotation_rows,
                generated_at,
                included=bool(render_manifest.get("include_private_annotations")),
                redaction_rules=redaction_rules,
            )
            projected_bytes += len(annotations_json_bytes)
            if max_archive_bytes and projected_bytes > max_archive_bytes:
                raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
            archive.writestr("notes/annotations.json", annotations_json_bytes)

            index_page = _render_package_index_html(
                render_package,
                render_manifest,
                generated_at,
                run_pages,
                artifact_archive_paths,
                skipped_items,
            )
            index_bytes = index_page.encode("utf-8")
            projected_bytes += len(index_bytes)
            if max_archive_bytes and projected_bytes > max_archive_bytes:
                raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
            archive.writestr("index.html", index_bytes)
            readme = _render_package_readme(
                render_package,
                render_manifest,
                generated_at,
                run_pages,
                artifact_archive_paths,
                skipped_items,
            )
            readme_bytes = readme.encode("utf-8")
            projected_bytes += len(readme_bytes)
            if max_archive_bytes and projected_bytes > max_archive_bytes:
                raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
            archive.writestr("README.md", readme_bytes)
            if skipped_items:
                skipped_item_bytes = (
                    json.dumps({"items": skipped_items}, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8")
                projected_bytes += len(skipped_item_bytes)
                if max_archive_bytes and projected_bytes > max_archive_bytes:
                    raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
                archive.writestr("skipped-items.json", skipped_item_bytes)
    except Exception:
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        raise
    return {
        "filename": _package_archive_name(render_package),
        "mimetype": "application/zip",
        "path": archive_path,
        "byte_size": os.path.getsize(archive_path),
        "skipped_artifacts": skipped_artifacts,
    }


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
            (session_id, project_id),
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
            "DELETE FROM annotations WHERE entity_type = 'package' AND entity_id = ?",
            (package_id,),
        )
        result = conn.execute(
            "DELETE FROM evidence_packages WHERE session_id = ? AND project_id = ? AND id = ?",
            (session_id, project_id, package_id),
        )
        conn.commit()
    return result.rowcount > 0


def _workflow_input_type_for_target(target_type, target_value):
    if target_type == "url":
        return "url"
    if target_type == "port_set":
        return "port" if str(target_value or "").isdigit() else ""
    return "host"


def _workflow_target_ref(data):
    if not isinstance(data, dict):
        return "", ""
    target_id = _trim_text(data.get("target_id"), MAX_ENTITY_ID_LEN)
    target_value = _trim_text(data.get("target_value") or data.get("target"), MAX_TARGET_VALUE_LEN)
    return target_id, target_value


def _workflow_target_candidates(target_rows, steps):
    candidates = []
    for target in target_rows:
        target_id = str(target["id"] or "")
        target_value = str(target["value"] or "").strip()
        target_type = str(target["type"] or "").strip().lower()
        input_type = _workflow_input_type_for_target(target_type, target_value)
        if not target_value or not input_type:
            continue
        transformed_steps = []
        replacement_count = 0
        for step in steps:
            replaced_cmd, replacements = _replace_target_token(step["cmd"], target_value)
            transformed_steps.append({**step, "cmd": replaced_cmd})
            replacement_count += replacements
        if replacement_count:
            candidates.append({
                "id": target_id,
                "type": target_type,
                "value": target_value,
                "input_type": input_type,
                "replacement_count": replacement_count,
                "steps": transformed_steps,
            })
    return candidates


def _select_workflow_target_candidate(data, candidates, target_rows):
    target_id, target_value = _workflow_target_ref(data)
    if target_id or target_value:
        selected_target = None
        for target in target_rows:
            if target_id and str(target["id"] or "") == target_id:
                selected_target = target
                break
            if target_value and str(target["value"] or "") == target_value:
                selected_target = target
                break
        if not selected_target:
            raise ProjectWorkspaceError("selected target is not linked to this project")
        selected_id = str(selected_target["id"] or "")
        selected_value = str(selected_target["value"] or "")
        for candidate in candidates:
            if candidate["id"] == selected_id or candidate["value"] == selected_value:
                return candidate
        raise ProjectWorkspaceError("selected target does not appear in the promoted run commands")
    if len(candidates) > 1:
        raise ProjectWorkspaceError("multiple project targets match promoted runs; provide target_id")
    return candidates[0] if candidates else None


def _workflow_target_metadata(candidate):
    if not candidate:
        return None
    return {
        "id": candidate["id"],
        "type": candidate["type"],
        "value": candidate["value"],
        "input_type": candidate["input_type"],
        "replacement_count": candidate["replacement_count"],
    }


def build_project_workflow_payload(session_id, project_id, data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("workflow promotion payload must be an object")
    with db_connect() as conn:
        project = conn.execute(
            "SELECT id, name FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        rows = conn.execute(
            "SELECT l.entity_id AS run_id, r.command, l.created "
            "FROM project_links l JOIN runs r ON r.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
            "ORDER BY l.created ASC",
            (project_id, session_id),
        ).fetchall()
        target_rows = conn.execute(
            "SELECT id, type, value FROM project_targets "
            "WHERE project_id = ? ORDER BY created ASC",
            (project_id,),
        ).fetchall()

    available_run_count = len(rows)
    selected_ids = data.get("run_ids")
    if selected_ids is not None:
        if not isinstance(selected_ids, list):
            raise ProjectWorkspaceError("run_ids must be a list")
        selected_ids = [_trim_text(item, MAX_ENTITY_ID_LEN) for item in selected_ids if _trim_text(item, MAX_ENTITY_ID_LEN)]
        if len(selected_ids) > MAX_PROJECT_WORKFLOW_STEPS:
            raise ProjectWorkspaceError(f"workflow promotion can include at most {MAX_PROJECT_WORKFLOW_STEPS} runs")
        by_id = {row["run_id"]: row for row in rows}
        missing = [run_id for run_id in selected_ids if run_id not in by_id]
        if missing:
            raise ProjectWorkspaceError("selected run is not linked to this project")
        rows = [by_id[run_id] for run_id in selected_ids]
    if not rows:
        raise ProjectWorkspaceError("project needs at least one linked run to promote a workflow")
    requested_run_count = len(rows)
    truncated_runs = max(0, len(rows) - MAX_PROJECT_WORKFLOW_STEPS)
    if truncated_runs:
        rows = rows[:MAX_PROJECT_WORKFLOW_STEPS]

    steps = [{"cmd": str(row["command"] or ""), "note": "Promoted from project history"} for row in rows]
    candidates = _workflow_target_candidates(target_rows, steps)
    selected_target = _select_workflow_target_candidate(data, candidates, target_rows)
    inputs = []
    if selected_target:
        steps = selected_target["steps"]
        inputs.append({
            "id": "target",
            "label": "Target",
            "type": selected_target["input_type"],
            "required": True,
            "placeholder": selected_target["value"],
            "default": selected_target["value"],
            "help": "Project target used when this workflow was promoted.",
        })

    title = _trim_text(data.get("title"), MAX_PACKAGE_NAME_LEN) or f"{project['name']} workflow"
    description = _trim_text(
        data.get("description") or f"Promoted from {len(steps)} project run{'s' if len(steps) != 1 else ''}.",
        MAX_PACKAGE_DESCRIPTION_LEN,
    )
    return {
        "workflow": {
            "title": title,
            "description": description,
            "inputs": inputs,
            "steps": steps,
        },
        "promotion": {
            "project_id": project_id,
            "available_run_count": available_run_count,
            "requested_run_count": requested_run_count,
            "promoted_run_count": len(steps),
            "step_limit": MAX_PROJECT_WORKFLOW_STEPS,
            "truncated_runs": truncated_runs,
            "selected_run_ids": [str(row["run_id"] or "") for row in rows],
            "target": _workflow_target_metadata(selected_target),
            "matching_targets": [_workflow_target_metadata(candidate) for candidate in candidates],
        },
    }


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
        run_id = _trim_text(filters.get("run_id"), MAX_ENTITY_ID_LEN)
        if run_id:
            clauses.append("f.run_id = ?")
            params.append(run_id)
        target_id = _trim_text(filters.get("target_id"), MAX_ENTITY_ID_LEN)
        review_state = _trim_text(filters.get("review_state"), 32).lower()
        if review_state:
            if review_state not in FINDING_REVIEW_STATES:
                raise ProjectWorkspaceError(
                    "finding review_state must be new, reviewed, important, false_positive, or needs_followup"
                )
            clauses.append("f.review_state = ?")
            params.append(review_state)
        scope = _trim_text(filters.get("scope"), 64)
        if scope:
            clauses.append("f.scope = ?")
            params.append(scope)
        severity = _trim_text(filters.get("severity"), 64).lower()
        if severity:
            clauses.append("LOWER(f.severity) = ?")
            params.append(severity)
        label = _trim_text(filters.get("label"), MAX_LABEL_LEN)
        if label:
            clauses.append(
                "EXISTS ("
                "SELECT 1 FROM entity_labels el "
                "WHERE el.session_id = ? AND el.entity_type = 'finding' "
                "AND el.entity_id = f.id AND el.label = ?"
                ")"
            )
            params.extend([session_id, label])
        annotation_state = _trim_text(filters.get("annotation_state"), 32).lower()
        if annotation_state:
            if annotation_state not in {"annotated", "unannotated"}:
                raise ProjectWorkspaceError("annotation_state must be annotated or unannotated")
            operator = "EXISTS" if annotation_state == "annotated" else "NOT EXISTS"
            clauses.append(
                f"{operator} ("  # nosec B608
                "SELECT 1 FROM annotations ann "
                "WHERE ann.session_id = ? AND ann.entity_type = 'finding' "
                "AND ann.entity_id = f.id"
                ")"
            )
            params.append(session_id)
        rows = conn.execute(
            "SELECT f.id, f.session_id, f.run_id, f.target_id, f.scope, f.title, f.raw_line, "
            "f.line_number, f.severity, f.fingerprint, f.review_state, f.created, "
            "r.command AS run_command "
            "FROM project_links l "
            "JOIN runs r ON r.id = l.entity_id "
            "JOIN findings f ON f.run_id = r.id AND f.session_id = r.session_id "
            f"WHERE {' AND '.join(clauses)} "  # nosec B608
            "ORDER BY f.created DESC, f.id DESC",
            params,
        ).fetchall()
        target_rows = conn.execute(
            "SELECT id, type, value FROM project_targets WHERE project_id = ?",
            (project_id,),
        ).fetchall()

    findings = [item for item in (_row_to_project_finding(row, target_rows) for row in rows) if item]
    if target_id:
        findings = [
            item for item in findings
            if target_id == item.get("target_id") or target_id in (item.get("target_ids") or [])
        ]
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
        excluded_sql = f"AND r.id NOT IN ({placeholders}) "  # nosec B608
        params.extend(excluded)
    row = conn.execute(
        "SELECT r.id "
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN entity_labels el ON el.entity_type = 'run' AND el.entity_id = r.id "
        "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
        "AND el.session_id = r.session_id AND el.label = ? "
        f"{excluded_sql}"  # nosec B608
        "ORDER BY r.started DESC, l.created DESC LIMIT 1",
        params,
    ).fetchone()
    return row["id"] if row else ""


def _run_finding_compare_items(conn, session_id, run_id):
    rows = conn.execute(
        "SELECT id, raw_line, title, severity, fingerprint, review_state, created "
        "FROM findings WHERE session_id = ? AND run_id = ? ORDER BY created ASC, id ASC",
        (session_id, run_id),
    ).fetchall()
    items = []
    for row in rows:
        key = row["fingerprint"] or row["raw_line"]
        items.append({
            "key": key,
            "id": row["id"],
            "title": row["title"],
            "raw_line": row["raw_line"],
            "severity": row["severity"],
            "review_state": row["review_state"],
        })
    return items


def _run_artifact_compare_items(conn, session_id, run_id):
    rows = conn.execute(
        "SELECT id, workspace_path, kind, byte_size, detected_by, created "
        "FROM run_file_artifacts WHERE session_id = ? AND run_id = ? ORDER BY created ASC, id ASC",
        (session_id, run_id),
    ).fetchall()
    return [{
        "key": row["workspace_path"],
        "id": row["id"],
        "workspace_path": row["workspace_path"],
        "kind": row["kind"],
        "byte_size": row["byte_size"],
        "detected_by": row["detected_by"],
    } for row in rows]


def _compare_items(left_items, right_items):
    left_by_key = {item["key"]: item for item in left_items if item.get("key")}
    right_by_key = {item["key"]: item for item in right_items if item.get("key")}
    left_keys = set(left_by_key)
    right_keys = set(right_by_key)
    return {
        "added": [left_by_key[key] for key in sorted(left_keys - right_keys)],
        "removed": [right_by_key[key] for key in sorted(right_keys - left_keys)],
        "unchanged_count": len(left_keys & right_keys),
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
        if not right_run_id and len(linked_run_ids) >= 2:
            right_run_id = linked_run_ids[1]
        if not left_run_id or not right_run_id:
            raise ProjectWorkspaceError("project comparison needs two linked runs")
        linked = set(linked_run_ids)
        if left_run_id not in linked or right_run_id not in linked:
            raise ProjectWorkspaceError("comparison runs must both be linked to this project")
        left_findings = _run_finding_compare_items(conn, session_id, left_run_id)
        right_findings = _run_finding_compare_items(conn, session_id, right_run_id)
        left_artifacts = _run_artifact_compare_items(conn, session_id, left_run_id)
        right_artifacts = _run_artifact_compare_items(conn, session_id, right_run_id)
    return {
        "left_run_id": left_run_id,
        "right_run_id": right_run_id,
        "baseline_label": baseline_label,
        "findings": _compare_items(left_findings, right_findings),
        "artifacts": _compare_items(left_artifacts, right_artifacts),
    }


def get_active_project(session_id):
    with db_connect() as conn:
        preferences = _load_session_preferences(conn, session_id)
        project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
        if not project_id:
            return None
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
            "FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
            (session_id, project_id),
        ).fetchone()
        if not row:
            _clear_active_project_preference(conn, session_id)
            conn.commit()
            return None
    return _row_to_project(row)


def set_active_project(session_id, project_id):
    project_id = _trim_text(project_id, MAX_ENTITY_ID_LEN)
    if not project_id:
        raise ProjectWorkspaceError("project_id is required")
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
            "FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
            (session_id, project_id),
        ).fetchone()
        if not row:
            return None
        preferences = _load_session_preferences(conn, session_id)
        preferences[ACTIVE_PROJECT_PREF_KEY] = row["id"]
        _save_session_preferences(conn, session_id, preferences)
        conn.commit()
    return _row_to_project(row)


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
        "SELECT id FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
        (session_id, project_id),
    ).fetchone()
    if not project:
        _clear_active_project_preference(conn, session_id)
        return None
    run = conn.execute(
        "SELECT 1 FROM runs WHERE session_id = ? AND id = ?",
        (session_id, run_id),
    ).fetchone()
    if not run:
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
            return _row_to_link(row)
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


def link_snapshot_to_project_context(conn, session_id, snapshot_id, *, source_run_id=""):
    snapshot_id = _trim_text(snapshot_id, MAX_ENTITY_ID_LEN)
    source_run_id = _trim_text(source_run_id, MAX_ENTITY_ID_LEN)
    snapshot = conn.execute(
        "SELECT 1 FROM snapshots WHERE session_id = ? AND id = ?",
        (session_id, snapshot_id),
    ).fetchone()
    if not snapshot:
        return []
    project_ids = []
    if source_run_id:
        rows = conn.execute(
            "SELECT DISTINCT l.project_id "
            "FROM project_links l "
            "JOIN projects p ON p.id = l.project_id "
            "JOIN runs r ON r.id = l.entity_id "
            "WHERE p.session_id = ? AND p.status != 'archived' "
            "AND l.entity_type = 'run' AND l.entity_id = ? AND r.session_id = ?",
            (session_id, source_run_id, session_id),
        ).fetchall()
        project_ids = [row["project_id"] for row in rows]
    if not project_ids:
        preferences = _load_session_preferences(conn, session_id)
        active_project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
        if active_project_id:
            project = conn.execute(
                "SELECT id FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
                (session_id, active_project_id),
            ).fetchone()
            if project:
                project_ids = [project["id"]]
            else:
                _clear_active_project_preference(conn, session_id)
    links = []
    for project_id in project_ids:
        links.append(_insert_project_link(
            conn,
            project_id,
            "snapshot",
            snapshot_id,
            "snapshot_capture",
        ))
    return links


def record_run_file_artifacts(conn, session_id, run_id, artifacts):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    run = conn.execute(
        "SELECT 1 FROM runs WHERE session_id = ? AND id = ?",
        (session_id, run_id),
    ).fetchone()
    if not run:
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
    match = re.search(r"\[(info|low|medium|high|critical)\]", str(text or ""), re.I)
    return match.group(1).lower() if match else ""


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


def record_run_findings(conn, session_id, run_id, entries):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    run = conn.execute(
        "SELECT 1 FROM runs WHERE session_id = ? AND id = ?",
        (session_id, run_id),
    ).fetchone()
    if not run:
        return []

    target_rows = conn.execute(
        "SELECT t.id, t.type, t.value "
        "FROM project_targets t "
        "JOIN project_links l ON l.project_id = t.project_id "
        "WHERE l.entity_type = 'run' AND l.entity_id = ? "
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
        raw_line = str(entry.get("text") or "").strip()
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
        target_id = _target_id_for_finding(target_rows, entry, raw_line)
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
                recorded.append(_row_to_finding(row))
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


def _normalize_metadata_target(entity_type, entity_id):
    try:
        entity_type = validate_project_entity_type(_trim_text(entity_type, 64))
    except ValueError as exc:
        raise ProjectWorkspaceError(str(exc)) from None
    if entity_type not in ENTITY_METADATA_TYPES:
        raise ProjectWorkspaceError(f"entity metadata does not support {entity_type}")
    entity_id = _trim_text(entity_id, MAX_ENTITY_ID_LEN)
    if not entity_id:
        raise ProjectWorkspaceError("entity_id is required")
    return entity_type, entity_id


def _normalize_label_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("label payload must be an object")
    label = _trim_text(data.get("label"), MAX_LABEL_LEN)
    if not label:
        raise ProjectWorkspaceError("label is required")
    return label


def _normalize_annotation_payload(data, *, partial=False):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("annotation payload must be an object")
    clean = {}
    if "body" in data or not partial:
        body = _trim_text(data.get("body"), MAX_ANNOTATION_BODY_LEN)
        if not body:
            raise ProjectWorkspaceError("annotation body is required")
        clean["body"] = body
    if "visibility" in data or not partial:
        visibility = _trim_text(data.get("visibility") or "private", 32).lower()
        if visibility not in ANNOTATION_VISIBILITIES:
            raise ProjectWorkspaceError("annotation visibility must be private")
        clean["visibility"] = visibility
    if "author_label" in data or not partial:
        clean["author_label"] = _trim_text(data.get("author_label"), MAX_AUTHOR_LABEL_LEN)
    return clean


def _normalize_target_payload(data, *, partial=False):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("target payload must be an object")
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
    if "label" in data or not partial:
        clean["label"] = _trim_text(data.get("label"), MAX_TARGET_LABEL_LEN)
    if "notes" in data or not partial:
        clean["notes"] = _trim_text(data.get("notes"), MAX_TARGET_NOTES_LEN)
    if "source_run_id" in data or not partial:
        clean["source_run_id"] = _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN)
    if "confidence" in data or not partial:
        try:
            confidence = float(data.get("confidence", 1.0))
        except (TypeError, ValueError):
            raise ProjectWorkspaceError("target confidence must be a number") from None
        clean["confidence"] = min(1.0, max(0.0, confidence))
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


def infer_project_target_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("target payload must be an object")
    explicit = _target_payload_from_candidate(data.get("value"))
    if explicit:
        return {
            **explicit,
            "label": _trim_text(data.get("label"), MAX_TARGET_LABEL_LEN),
            "notes": _trim_text(data.get("notes"), MAX_TARGET_NOTES_LEN),
            "source_run_id": _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN),
            "confidence": 1.0,
        }
    text = str(data.get("text") or "")
    for match in _URL_RE.finditer(text):
        inferred = _target_payload_from_candidate(match.group(0))
        if inferred:
            return {
                **inferred,
                "label": _trim_text(data.get("label"), MAX_TARGET_LABEL_LEN),
                "notes": _trim_text(data.get("notes"), MAX_TARGET_NOTES_LEN),
                "source_run_id": _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN),
                "confidence": 0.9,
            }
    for token in re.split(r"\s+", text):
        inferred = _target_payload_from_candidate(token)
        if inferred:
            return {
                **inferred,
                "label": _trim_text(data.get("label"), MAX_TARGET_LABEL_LEN),
                "notes": _trim_text(data.get("notes"), MAX_TARGET_NOTES_LEN),
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


def _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
    if entity_type == "workspace_file":
        return not entity_id.startswith("/") and "\x00" not in entity_id and ".." not in entity_id.split("/")
    if entity_type == "project":
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


def list_project_links(session_id, project_id):
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        rows = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? ORDER BY created DESC",
            (project_id,),
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
            raise ProjectWorkspaceError(f"{entity_type} not found for this session")
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            (project_id, entity_type, entity_id),
        ).fetchone()
        if row:
            return _row_to_link(row)
        count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_links WHERE project_id = ?",
            (project_id,),
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
                (project_id, entity_type, entity_id),
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_link(row)
        raise ProjectWorkspaceError("could not allocate a project link id")


def unlink_project_entity(session_id, project_id, data):
    raw = data if isinstance(data, dict) else {}
    entity_type, entity_id, _ = _normalize_link_payload({**raw, "source": "manual"})
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        result = conn.execute(
            "DELETE FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            (project_id, entity_type, entity_id),
        )
        conn.commit()
    return result.rowcount > 0


def list_project_targets(session_id, project_id):
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        rows = conn.execute(
            "SELECT id, project_id, type, value, label, notes, source_run_id, confidence, created, updated "
            "FROM project_targets WHERE project_id = ? ORDER BY type ASC, value COLLATE NOCASE ASC",
            (project_id,),
        ).fetchall()
    return [_row_to_target(row) for row in rows]


def add_project_target(session_id, project_id, data):
    payload = _normalize_target_payload(data)
    created = _now()
    updated = created
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        if payload["source_run_id"] and not _entity_belongs_to_session(conn, session_id, "run", payload["source_run_id"]):
            raise ProjectWorkspaceError("source_run_id not found for this session")
        row = conn.execute(
            "SELECT id, project_id, type, value, label, notes, source_run_id, confidence, created, updated "
            "FROM project_targets WHERE project_id = ? AND type = ? AND value = ?",
            (project_id, payload["type"], payload["value"]),
        ).fetchone()
        if row:
            return _row_to_target(row)
        count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_targets WHERE project_id = ?",
            (project_id,),
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
                "(id, project_id, type, value, label, notes, source_run_id, confidence, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    target_id,
                    project_id,
                    payload["type"],
                    payload["value"],
                    payload["label"],
                    payload["notes"],
                    payload["source_run_id"],
                    payload["confidence"],
                    created,
                    updated,
                ),
            )
            row = conn.execute(
                "SELECT id, project_id, type, value, label, notes, source_run_id, confidence, created, updated "
                "FROM project_targets WHERE project_id = ? AND type = ? AND value = ?",
                (project_id, payload["type"], payload["value"]),
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_target(row)
        raise ProjectWorkspaceError("could not allocate a project target id")


def update_project_target(session_id, project_id, target_id, data):
    target_id = _trim_text(target_id, MAX_ENTITY_ID_LEN)
    payload = _normalize_target_payload(data, partial=True)
    if not payload:
        raise ProjectWorkspaceError("target update payload is empty")
    with db_connect() as conn:
        current = conn.execute(
            "SELECT t.id, t.project_id, t.type, t.value, t.label, t.notes, t.source_run_id, t.confidence "
            "FROM project_targets t JOIN projects p ON p.id = t.project_id "
            "WHERE p.session_id = ? AND t.project_id = ? AND t.id = ?",
            (session_id, project_id, target_id),
        ).fetchone()
        if not current:
            return None
        target_type = payload.get("type", current["type"])
        value = payload.get("value", current["value"])
        label = payload.get("label", current["label"])
        notes = payload.get("notes", current["notes"])
        source_run_id = payload.get("source_run_id", current["source_run_id"])
        confidence = payload.get("confidence", current["confidence"])
        if source_run_id and not _entity_belongs_to_session(conn, session_id, "run", source_run_id):
            raise ProjectWorkspaceError("source_run_id not found for this session")
        updated = _now()
        try:
            conn.execute(
                "UPDATE project_targets SET type = ?, value = ?, label = ?, notes = ?, "
                "source_run_id = ?, confidence = ?, updated = ? "
                "WHERE project_id = ? AND id = ?",
                (target_type, value, label, notes, source_run_id, confidence, updated, project_id, target_id),
            )
        except sqlite3.IntegrityError:
            raise ProjectWorkspaceError("target already exists for this project") from None
        row = conn.execute(
            "SELECT id, project_id, type, value, label, notes, source_run_id, confidence, created, updated "
            "FROM project_targets WHERE project_id = ? AND id = ?",
            (project_id, target_id),
        ).fetchone()
        conn.commit()
    return _row_to_target(row)


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
    return [_row_to_finding(row) for row in rows]


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
            (session_id, finding_id),
        ).fetchone()
        conn.commit()
    return _row_to_finding(row)


def list_entity_labels(session_id, entity_type, entity_id):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        rows = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, label, source, created "
            "FROM entity_labels WHERE session_id = ? AND entity_type = ? AND entity_id = ? "
            "ORDER BY label COLLATE NOCASE ASC, created ASC",
            (session_id, entity_type, entity_id),
        ).fetchall()
    return [_row_to_label(row) for row in rows]


def add_entity_label(session_id, entity_type, entity_id, data):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    label = _normalize_label_payload(data)
    created = _now()
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        row = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, label, source, created "
            "FROM entity_labels WHERE session_id = ? AND entity_type = ? "
            "AND entity_id = ? AND label = ?",
            (session_id, entity_type, entity_id, label),
        ).fetchone()
        if row:
            return _row_to_label(row)
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
        entity_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_labels "
            "WHERE session_id = ? AND entity_type = ? AND entity_id = ?",
            (session_id, entity_type, entity_id),
        ).fetchone()
        if _quota_exceeded(
            int(entity_count["count"] or 0) if entity_count else 0,
            "max_entity_labels_per_entity",
            20,
        ):
            _raise_quota("label quota exceeded for this entity")
        for _ in range(10):
            label_id = _new_entity_label_id()
            conn.execute(
                "INSERT OR IGNORE INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, ?, ?, ?, 'manual', ?)",
                (label_id, session_id, entity_type, entity_id, label, created),
            )
            row = conn.execute(
                "SELECT id, session_id, entity_type, entity_id, label, source, created "
                "FROM entity_labels WHERE session_id = ? AND entity_type = ? "
                "AND entity_id = ? AND label = ?",
                (session_id, entity_type, entity_id, label),
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_label(row)
        raise ProjectWorkspaceError("could not allocate an entity label id")


def delete_entity_label(session_id, entity_type, entity_id, data):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    label = _normalize_label_payload(data)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        result = conn.execute(
            "DELETE FROM entity_labels WHERE session_id = ? AND entity_type = ? "
            "AND entity_id = ? AND label = ?",
            (session_id, entity_type, entity_id, label),
        )
        conn.commit()
    return result.rowcount > 0


def list_entity_annotations(session_id, entity_type, entity_id):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        rows = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, body, visibility, author_label, created, updated "
            "FROM annotations WHERE session_id = ? AND entity_type = ? AND entity_id = ? "
            "ORDER BY created ASC, id ASC",
            (session_id, entity_type, entity_id),
        ).fetchall()
    return [_row_to_annotation(row) for row in rows]


def add_entity_annotation(session_id, entity_type, entity_id, data):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    payload = _normalize_annotation_payload(data)
    created = _now()
    with db_connect() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            return None
        session_count = conn.execute(
            "SELECT COUNT(*) AS count FROM annotations WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if _quota_exceeded(
            int(session_count["count"] or 0) if session_count else 0,
            "max_entity_annotations_per_session",
            2000,
        ):
            _raise_quota("annotation quota exceeded for this session")
        entity_count = conn.execute(
            "SELECT COUNT(*) AS count FROM annotations "
            "WHERE session_id = ? AND entity_type = ? AND entity_id = ?",
            (session_id, entity_type, entity_id),
        ).fetchone()
        if _quota_exceeded(
            int(entity_count["count"] or 0) if entity_count else 0,
            "max_entity_annotations_per_entity",
            50,
        ):
            _raise_quota("annotation quota exceeded for this entity")
        for _ in range(10):
            annotation_id = _new_annotation_id()
            conn.execute(
                "INSERT OR IGNORE INTO annotations "
                "(id, session_id, entity_type, entity_id, body, visibility, author_label, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    annotation_id,
                    session_id,
                    entity_type,
                    entity_id,
                    payload["body"],
                    payload["visibility"],
                    payload["author_label"],
                    created,
                    created,
                ),
            )
            row = conn.execute(
                "SELECT id, session_id, entity_type, entity_id, body, visibility, author_label, created, updated "
                "FROM annotations WHERE id = ? AND session_id = ?",
                (annotation_id, session_id),
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_annotation(row)
        raise ProjectWorkspaceError("could not allocate an annotation id")


def update_entity_annotation(session_id, annotation_id, data):
    annotation_id = _trim_text(annotation_id, MAX_ENTITY_ID_LEN)
    payload = _normalize_annotation_payload(data, partial=True)
    if not payload:
        raise ProjectWorkspaceError("annotation update is empty")
    assignments = []
    values = []
    for key in ("body", "visibility", "author_label"):
        if key in payload:
            assignments.append(f"{key} = ?")
            values.append(payload[key])
    updated = _now()
    assignments.append("updated = ?")
    values.append(updated)
    values.extend([session_id, annotation_id])
    with db_connect() as conn:
        result = conn.execute(
            f"UPDATE annotations SET {', '.join(assignments)} WHERE session_id = ? AND id = ?",  # nosec B608
            values,
        )
        if result.rowcount <= 0:
            return None
        row = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, body, visibility, author_label, created, updated "
            "FROM annotations WHERE session_id = ? AND id = ?",
            (session_id, annotation_id),
        ).fetchone()
        conn.commit()
    return _row_to_annotation(row)


def delete_entity_annotation(session_id, annotation_id):
    annotation_id = _trim_text(annotation_id, MAX_ENTITY_ID_LEN)
    if not annotation_id:
        raise ProjectWorkspaceError("annotation id is required")
    with db_connect() as conn:
        result = conn.execute(
            "DELETE FROM annotations WHERE session_id = ? AND id = ?",
            (session_id, annotation_id),
        )
        conn.commit()
    return result.rowcount > 0
