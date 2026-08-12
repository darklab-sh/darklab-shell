# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Evidence package archive creation and mutation helpers.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import zipfile
from collections.abc import Mapping, Sequence
from typing import cast

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from core.redaction import apply_redaction_rules, line_entries_from_events, line_events_from_entries, redact_line_entries
from services.assessments.export_context import get_project_assessment_context
from services.runs.output_model import LineEvent, is_noise_event
from services.projects.artifacts import (
    artifact_owner_context as _artifact_owner_context,
    artifact_snapshot_mismatch_reason as _artifact_snapshot_mismatch_reason,
    row_to_run_file_artifact as _row_to_run_file_artifact,
)
from services.projects.contracts import (
    EvidencePackageBuildError,
    EvidencePackageTooLarge,
    MAX_ENTITY_ID_LEN,
    MAX_ENTITY_NOTE_BODY_LEN,
    ProjectWorkspaceError,
)
from services.projects.findings import list_project_findings
from services.projects.finding_evidence import attach_finding_evidence_links
from services.projects.metadata import (
    _full_finding_triage_by_id,
    _metadata_owner_where,
    _metadata_row_owner_values,
)
from services.projects.models import entity_note_body as _entity_note_body
from services.projects.package_rendering import (
    _metadata_items_by_entity,
    _package_css,
    _package_findings_json_bytes,
    _package_findings_markdown_bytes,
    _package_label_dicts,
    _package_labels_json_bytes,
    _package_manifest_with_inline_metadata,
    _package_metadata_rows,
    _package_metadata_targets,
    _package_note_dicts,
    _package_notes_json_bytes,
    _package_notes_markdown_bytes,
    _package_project_notes_markdown_bytes,
    _package_run_output_entries,
    _package_run_rows,
    _package_run_text_bytes,
    _package_targets_json_bytes,
    _package_targets_markdown_bytes,
    _package_zip_artifact_path,
    _render_package_index_html,
    _render_package_readme,
    _render_package_run_html,
)
from services.projects.packages import (
    EVIDENCE_PACKAGE_FORMAT_VERSION as _EVIDENCE_PACKAGE_FORMAT_VERSION,
    evidence_manifest_from_summary as _evidence_manifest_from_summary,
    normalize_evidence_package_payload as _normalize_evidence_package_payload,
    package_archive_name as _package_archive_name,
    package_manifest_without_private_notes as _package_manifest_without_private_notes,
    package_redaction_rules as _package_redaction_rules,
    redacted_artifact_derivative_reason as _redacted_artifact_derivative_reason,
    redact_package_manifest as _redact_package_manifest,
)
from services.projects.queries import (
    _list_all_project_artifacts,
    get_evidence_package,
    get_project_summary,
)
from services.projects.scope import shared_owner_where
from services.projects.utils import (
    cfg_int as _cfg_int,
    cfg_mb_bytes as _cfg_mb_bytes,
    new_entity_label_id as _new_entity_label_id,
    new_entity_note_id as _new_entity_note_id,
    new_evidence_package_id as _new_evidence_package_id,
    now as _now,
    quota_exceeded as _quota_exceeded,
    raise_quota as _raise_quota,
    trim_text as _trim_text,
)
from services.workspace.files import WorkspaceError, resolve_owner_workspace_path

log = logging.getLogger("shell")


def _write_bounded_archive_entry(
    archive,
    name,
    payload_bytes,
    projected_bytes,
    max_uncompressed_archive_bytes,
    message="evidence package expanded content exceeds configured size limit",
):
    new_total = projected_bytes + len(payload_bytes)
    if max_uncompressed_archive_bytes and new_total > max_uncompressed_archive_bytes:
        raise EvidencePackageTooLarge(message)
    archive.writestr(name, payload_bytes)
    return new_total


def _redacted_artifact_bytes(resolved, redaction_rules):
    payload = resolved.read_bytes()
    if b"\x00" in payload:
        raise ProjectWorkspaceError("Artifact appears to be binary and cannot be safely redacted.")
    text = payload.decode("utf-8", errors="replace")
    redacted = apply_redaction_rules(text, redaction_rules)
    return redacted.encode("utf-8")


def _raw_artifact_row_for_archive(session_id, project_id, artifact_id, *, team_id=""):
    if not str(artifact_id or "").strip():
        return None
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
        row = conn.execute(
            "SELECT a.id, a.session_id, a.run_id, a.workspace_path, a.display_name, a.kind, a.byte_size, "
            "a.detected_by, a.content_type, a.preview_type, a.content_sha256, a.created, "
            "r.team_id AS run_team_id "
            "FROM run_file_artifacts a "
            "JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = a.run_id "
            "JOIN projects p ON p.id = l.project_id "
            "JOIN runs r ON r.id = a.run_id "
            "WHERE " + project_owner_sql + " AND p.id = ? AND a.id = ? "  # nosec
            "AND " + run_owner_sql,
            (*project_owner_params, project_id, artifact_id, *run_owner_params),
        ).fetchone()
    return _row_to_run_file_artifact(row)


def _attach_package_finding_triage(session_id, findings, *, team_id=""):
    items = [finding for finding in findings if isinstance(finding, dict)]
    if not items:
        return findings
    finding_ids = [str(finding.get("id") or "") for finding in items if finding.get("id")]
    if not finding_ids:
        return findings
    with get_db_connect()() as conn:
        triage_by_id = _full_finding_triage_by_id(
            conn,
            session_id,
            finding_ids,
            team_id=team_id,
        )
    for finding in items:
        triage = triage_by_id.get(str(finding.get("id") or ""))
        if triage:
            finding["triage"] = triage
            finding["verification_status"] = triage.get("verification_status") or finding.get("verification_status")
    return findings


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


def _package_transcript_manifest_entry(run, entries, archive_path, text_archive_path=""):
    run_id = str(run.get("id") or "")
    lines = []
    for fallback_index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        raw_signals = entry.get("signals")
        signals: list[object] = raw_signals if isinstance(raw_signals, list) else []
        raw_entities = entry.get("entities")
        entities: list[object] = raw_entities if isinstance(raw_entities, list) else []
        try:
            raw_line_index = entry.get("line_index")
            line_index = fallback_index if raw_line_index is None else int(raw_line_index)
        except (TypeError, ValueError):
            line_index = fallback_index
        line = {
            "line_index": line_index,
            "signals": [str(signal) for signal in signals if str(signal or "").strip()],
            "entities": [
                {
                    "type": str(entity.get("type") or ""),
                    "value": str(entity.get("value") or entity.get("canonical_value") or ""),
                    "canonical_value": str(entity.get("canonical_value") or entity.get("value") or ""),
                }
                for entity in entities
                if isinstance(entity, dict)
                and str(entity.get("type") or "").strip()
                and str(entity.get("canonical_value") or entity.get("value") or "").strip()
            ],
        }
        if entry.get("cls"):
            line["cls"] = str(entry.get("cls") or "")
        lines.append(line)
    return {
        "run_id": run_id,
        "archive_path": archive_path,
        "text_archive_path": text_archive_path,
        "line_count": len(lines),
        "lines": lines,
    }


def _raise_if_estimated_archive_too_large(manifest, max_uncompressed_archive_bytes):
    if not max_uncompressed_archive_bytes:
        return
    estimated_bytes = _evidence_package_estimated_archive_bytes(manifest)
    if estimated_bytes > max_uncompressed_archive_bytes:
        raise EvidencePackageTooLarge("evidence package expanded content estimate exceeds configured size limit")


def _archive_audit_handoff(event_type, job_id):
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return {}
    return {
        "event_type": event_type,
        "correlation_id": normalized_job_id,
        "job_id": normalized_job_id,
    }


def _manifest_with_audit_handoff(manifest, audit_handoff):
    if not audit_handoff:
        return manifest
    updated = dict(manifest or {})
    provenance = updated.get("provenance")
    provenance = dict(provenance) if isinstance(provenance, dict) else {}
    provenance["audit"] = dict(audit_handoff)
    updated["provenance"] = provenance
    return updated


def build_evidence_package_archive(
    session_id,
    project_id,
    package_id,
    *,
    cfg=None,
    progress_callback=None,
    archive_dir=None,
    team_id="",
    build_job_id="",
):
    build_started = time.perf_counter()
    timings = {}

    def _progress(phase, message):
        if not callable(progress_callback):
            return
        progress_callback(phase, message)

    def _elapsed_ms(started):
        return int(round((time.perf_counter() - started) * 1000))

    def _record_timing(name, started):
        timings[f"{name}_ms"] = _elapsed_ms(started)

    _progress("loading", "Loading package")
    package = get_evidence_package(session_id, project_id, package_id, team_id=team_id)
    if package is None:
        return None
    log.info("PACKAGE_BUILD_STARTED", extra={
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
        "redaction_mode": package.get("redaction_mode"),
    })
    metadata_started = time.perf_counter()
    _progress("metadata", "Collecting package metadata")
    generated_at = _now()
    manifest = dict(package.get("manifest") or {})
    redaction_rules = _package_redaction_rules(package.get("redaction_mode"), cfg=cfg)
    render_manifest = _redact_package_manifest(manifest, redaction_rules)
    if not render_manifest.get("include_private_notes"):
        render_manifest = _package_manifest_without_private_notes(render_manifest)
    metadata_targets = _package_metadata_targets(package, manifest)
    with get_db_connect()() as conn:
        label_rows = _package_metadata_rows(conn, session_id, "entity_labels", metadata_targets, team_id=team_id)
        note_rows = (
            _package_metadata_rows(conn, session_id, "entity_notes", metadata_targets, team_id=team_id)
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
    render_manifest = _manifest_with_audit_handoff(
        render_manifest,
        _archive_audit_handoff("package.build", build_job_id),
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
        "format": _EVIDENCE_PACKAGE_FORMAT_VERSION,
        "generated_at": generated_at,
        "package": export_package,
        "manifest": render_manifest,
        "provenance": render_manifest.get("provenance") if isinstance(render_manifest, dict) else {},
    }
    max_compressed_archive_bytes = _cfg_mb_bytes("evidence_package_max_mb", 25, cfg=cfg)
    max_uncompressed_archive_bytes = _cfg_mb_bytes("evidence_package_max_uncompressed_mb", 500, cfg=cfg)
    _raise_if_estimated_archive_too_large(manifest, max_uncompressed_archive_bytes)
    _record_timing("metadata", metadata_started)
    skipped_artifacts = []
    skipped_items = []
    redacted_artifacts = []
    artifact_archive_paths = {}
    temp_file = tempfile.NamedTemporaryFile(
        prefix="darklab-evidence-package-",
        suffix=".zip",
        delete=False,
        dir=archive_dir,
    )
    archive_path = temp_file.name
    temp_file.close()
    used_paths = set()
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            core_started = time.perf_counter()
            _progress("core", "Writing package assets")
            css_bytes = (_package_css() + "\n").encode("utf-8")
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "assets/package.css",
                css_bytes,
                0,
                max_uncompressed_archive_bytes,
                "evidence package CSS snapshot exceeds configured size limit",
            )
            _record_timing("core_entries", core_started)
            artifacts_started = time.perf_counter()
            _progress("artifacts", "Collecting package artifacts")
            if package["include_artifacts"]:
                artifacts = manifest.get("artifacts")
                artifact_items = artifacts if isinstance(artifacts, list) else []
                max_artifacts = _cfg_int("evidence_package_max_artifacts", 100, cfg=cfg)
                if max_artifacts and len(artifact_items) > max_artifacts:
                    raise EvidencePackageTooLarge("evidence package artifact count exceeds configured limit")
                redacted_artifact_mode = package.get("redaction_mode") == "redacted"
                for artifact in artifact_items:
                    if not isinstance(artifact, dict):
                        continue
                    archive_artifact = artifact
                    if redacted_artifact_mode:
                        raw_artifact = _raw_artifact_row_for_archive(
                            session_id,
                            project_id,
                            artifact.get("id"),
                            team_id=team_id,
                        )
                        if raw_artifact:
                            archive_artifact = raw_artifact
                    artifact_owner_session = str(archive_artifact.get("session_id") or artifact.get("session_id") or session_id)
                    owner_context = _artifact_owner_context(artifact_owner_session, archive_artifact)
                    public_workspace_path = _trim_text(artifact.get("workspace_path"), MAX_ENTITY_ID_LEN)
                    workspace_path = public_workspace_path
                    if redacted_artifact_mode:
                        workspace_path = _trim_text(archive_artifact.get("workspace_path"), MAX_ENTITY_ID_LEN)
                        if not public_workspace_path:
                            public_workspace_path = apply_redaction_rules(workspace_path, redaction_rules)
                    if not workspace_path:
                        continue
                    try:
                        declared_size = max(0, int(archive_artifact.get("byte_size") or 0))
                    except (TypeError, ValueError):
                        declared_size = 0
                    if (
                        max_uncompressed_archive_bytes
                        and declared_size
                        and projected_bytes + declared_size > max_uncompressed_archive_bytes
                    ):
                        raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
                    try:
                        resolved = resolve_owner_workspace_path(owner_context, workspace_path, cfg)
                        if not resolved.is_file():
                            raise ProjectWorkspaceError("artifact file is not available")
                        mismatch_reason = _artifact_snapshot_mismatch_reason(archive_artifact, resolved)
                        if mismatch_reason:
                            raise ProjectWorkspaceError(mismatch_reason)
                        if redacted_artifact_mode:
                            derivative_reason = _redacted_artifact_derivative_reason(archive_artifact)
                            if derivative_reason:
                                raise ProjectWorkspaceError(derivative_reason)
                            derivative_bytes = _redacted_artifact_bytes(resolved, redaction_rules)
                            zip_path = _package_zip_artifact_path(
                                public_workspace_path,
                                used_paths,
                                root="artifacts-redacted",
                            )
                            projected_bytes = _write_bounded_archive_entry(
                                archive,
                                zip_path,
                                derivative_bytes,
                                projected_bytes,
                                max_uncompressed_archive_bytes,
                            )
                            redacted_artifacts.append({
                                "id": archive_artifact.get("id") or "",
                                "workspace_path": public_workspace_path,
                                "display_name": artifact.get("display_name") or public_workspace_path,
                                "archive_path": zip_path,
                                "source_byte_size": declared_size,
                                "byte_size": len(derivative_bytes),
                            })
                        else:
                            projected_bytes += resolved.stat().st_size
                            if max_uncompressed_archive_bytes and projected_bytes > max_uncompressed_archive_bytes:
                                raise EvidencePackageTooLarge("evidence package exceeds configured size limit")
                            zip_path = _package_zip_artifact_path(public_workspace_path, used_paths)
                            archive.write(resolved, arcname=zip_path)
                        artifact_archive_paths[str(artifact.get("id") or "")] = zip_path
                    except (OSError, ProjectWorkspaceError, WorkspaceError) as exc:
                        skipped_artifact = {
                            "kind": "artifact",
                            "id": artifact.get("id") or "",
                            "label": artifact.get("display_name") or public_workspace_path,
                            "workspace_path": public_workspace_path,
                            "reason": str(exc),
                        }
                        skipped_artifacts.append(skipped_artifact)
                        skipped_items.append(skipped_artifact)
            if redacted_artifacts:
                redacted_artifact_bytes = (
                    json.dumps({"artifacts": redacted_artifacts}, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8")
                projected_bytes = _write_bounded_archive_entry(
                    archive,
                    "redacted-artifacts.json",
                    redacted_artifact_bytes,
                    projected_bytes,
                    max_uncompressed_archive_bytes,
                )
            if skipped_artifacts:
                skipped_bytes = (
                    json.dumps({"artifacts": skipped_artifacts}, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8")
                projected_bytes = _write_bounded_archive_entry(
                    archive,
                    "skipped-artifacts.json",
                    skipped_bytes,
                    projected_bytes,
                    max_uncompressed_archive_bytes,
                )
            _record_timing("artifacts", artifacts_started)

            run_pages_started = time.perf_counter()
            _progress("runs", "Rendering run transcripts")
            run_pages = {}
            run_text_paths = {}
            transcript_manifest_entries = []
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
            with get_db_connect()() as conn:
                run_rows = _package_run_rows(conn, session_id, transcript_run_ids, team_id=team_id)
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
                    if max_uncompressed_archive_bytes and projected_bytes + len(companion_bytes) > max_uncompressed_archive_bytes:
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
                            max_uncompressed_archive_bytes,
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
                line_entries = cast(Sequence[LineEvent | Mapping[str, object] | str], entries)
                manifest_events = (
                    redact_line_entries(line_entries, redaction_rules)
                    if redaction_rules
                    else line_events_from_entries(line_entries)
                )
                manifest_entries = line_entries_from_events(
                    [event for event in manifest_events if not is_noise_event(event)]
                )
                transcript_manifest_entries.append(_package_transcript_manifest_entry(
                    run,
                    manifest_entries,
                    run_path,
                    transcript_text_path,
                ))
                projected_bytes = _write_bounded_archive_entry(
                    archive,
                    run_path,
                    run_page_bytes,
                    projected_bytes,
                    max_uncompressed_archive_bytes,
                )
            _record_timing("run_pages", run_pages_started)

            manifest_started = time.perf_counter()
            _progress("manifest", "Writing package manifest")
            if transcript_manifest_entries:
                export_manifest["transcripts"] = transcript_manifest_entries
            manifest_bytes = json.dumps(export_manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "manifest.json",
                manifest_bytes,
                projected_bytes,
                max_uncompressed_archive_bytes,
                "evidence package manifest exceeds configured size limit",
            )
            _record_timing("manifest", manifest_started)

            findings_started = time.perf_counter()
            _progress("findings", "Writing findings exports")
            findings_json_bytes = _package_findings_json_bytes(render_manifest, generated_at, run_pages)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "findings/findings.json",
                findings_json_bytes,
                projected_bytes,
                max_uncompressed_archive_bytes,
            )
            findings_markdown_bytes = _package_findings_markdown_bytes(render_manifest, run_pages)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "findings/findings.md",
                findings_markdown_bytes,
                projected_bytes,
                max_uncompressed_archive_bytes,
            )
            _record_timing("findings", findings_started)

            targets_started = time.perf_counter()
            _progress("targets", "Writing target exports")
            targets_json_bytes = _package_targets_json_bytes(render_manifest, generated_at)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "targets/targets.json",
                targets_json_bytes,
                projected_bytes,
                max_uncompressed_archive_bytes,
            )
            targets_markdown_bytes = _package_targets_markdown_bytes(render_manifest)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "targets/targets.md",
                targets_markdown_bytes,
                projected_bytes,
                max_uncompressed_archive_bytes,
            )
            _record_timing("targets", targets_started)

            notes_started = time.perf_counter()
            _progress("notes", "Writing labels and notes")
            labels_json_bytes = _package_labels_json_bytes(label_items, generated_at)
            projected_bytes = _write_bounded_archive_entry(
                archive,
                "metadata/labels.json",
                labels_json_bytes,
                projected_bytes,
                max_uncompressed_archive_bytes,
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
                max_uncompressed_archive_bytes,
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
                max_uncompressed_archive_bytes,
            )
            if _entity_note_body(render_manifest.get("project") if isinstance(render_manifest, dict) else {}):
                project_notes_bytes = _package_project_notes_markdown_bytes(render_manifest, generated_at)
                projected_bytes = _write_bounded_archive_entry(
                    archive,
                    "notes/project.md",
                    project_notes_bytes,
                    projected_bytes,
                    max_uncompressed_archive_bytes,
                )
            _record_timing("notes", notes_started)

            index_started = time.perf_counter()
            _progress("index", "Rendering package index")
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
                max_uncompressed_archive_bytes,
            )
            _record_timing("index", index_started)
            readme_started = time.perf_counter()
            _progress("readme", "Writing package README")
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
                max_uncompressed_archive_bytes,
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
                    max_uncompressed_archive_bytes,
                )
            _record_timing("skipped_items", skipped_items_started)
            zip_finalize_started = time.perf_counter()
            _progress("finalizing", "Finalizing archive")
        _record_timing("zip_finalize", zip_finalize_started)
    except EvidencePackageTooLarge:
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        raise
    except Exception as exc:
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        log.error("PACKAGE_BUILD_FAILED", exc_info=True, extra={
            "session": get_log_session_id(session_id),
            "project_id": project_id,
            "package_id": package_id,
            "stage": "archive",
        })
        raise EvidencePackageBuildError("evidence package archive build failed") from exc
    final_archive_bytes = os.path.getsize(archive_path)
    if max_compressed_archive_bytes and final_archive_bytes > max_compressed_archive_bytes:
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        raise EvidencePackageTooLarge("evidence package ZIP exceeds configured size limit")
    _progress("complete", "Archive ready")
    metrics = {
        **timings,
        "duration_ms": _elapsed_ms(build_started),
        "projected_bytes": projected_bytes,
        "archive_bytes": final_archive_bytes,
        "max_archive_bytes": max_compressed_archive_bytes,
        "max_compressed_archive_bytes": max_compressed_archive_bytes,
        "max_uncompressed_archive_bytes": max_uncompressed_archive_bytes,
        "skipped_artifacts": len(skipped_artifacts),
        "skipped_items": len(skipped_items),
        "redacted_artifacts": len(redacted_artifacts),
        "selected_runs": _package_selected_id_count(manifest, "run_ids"),
        "selected_transcripts": _package_selected_id_count(manifest, "transcript_run_ids"),
        "selected_findings": _package_selected_id_count(manifest, "finding_ids"),
        "selected_artifacts": _package_selected_id_count(manifest, "artifact_ids"),
        "selected_targets": _package_selected_id_count(manifest, "target_ids"),
    }
    log.info("PACKAGE_BUILD_COMPLETED", extra={
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
        "archive_bytes": final_archive_bytes,
        "projected_bytes": projected_bytes,
        "duration_ms": metrics["duration_ms"],
        "skipped_items": len(skipped_items),
        "redacted_artifacts": len(redacted_artifacts),
    })
    return {
        "filename": _package_archive_name(render_package),
        "mimetype": "application/zip",
        "path": archive_path,
        "byte_size": final_archive_bytes,
        "skipped_artifacts": skipped_artifacts,
        "skipped_items": skipped_items,
        "metrics": metrics,
    }


def _save_new_package_metadata(conn, session_id, package_id, labels, notes, *, team_id=""):
    metadata_session, metadata_team_id = _metadata_row_owner_values(session_id, team_id)
    metadata_owner_sql, metadata_owner_params = _metadata_owner_where(session_id, team_id)
    label_values = [str(label or "").strip() for label in (labels or []) if str(label or "").strip()]
    for label in label_values:
        session_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_labels WHERE " + metadata_owner_sql,  # nosec
            metadata_owner_params,
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
                "(id, session_id, team_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, ?, 'package', ?, ?, 'manual', ?) "
                "ON CONFLICT(id) DO NOTHING",
                (label_id, metadata_session, metadata_team_id, package_id, label, _now()),
            )
            if result.rowcount:
                break
        else:
            raise ProjectWorkspaceError("could not allocate an entity label id")
    body = _trim_text(notes, MAX_ENTITY_NOTE_BODY_LEN)
    if not body:
        return
    session_count = conn.execute(
        "SELECT COUNT(*) AS count FROM entity_notes WHERE " + metadata_owner_sql,  # nosec
        metadata_owner_params,
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
            "(id, session_id, team_id, entity_type, entity_id, body, created, updated) "
            "VALUES (?, ?, ?, 'package', ?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            (note_id, metadata_session, metadata_team_id, package_id, body, now, now),
        )
        if result.rowcount:
            return
    raise ProjectWorkspaceError("could not allocate an entity note id")


def create_evidence_package(session_id, project_id, data, *, team_id=""):
    payload = _normalize_evidence_package_payload(data)
    summary = get_project_summary(
        session_id,
        project_id,
        team_id=team_id,
        include_provenance=True,
    )
    if summary is None:
        return None
    summary["artifacts"] = _list_all_project_artifacts(session_id, project_id, team_id=team_id) or []
    findings = list_project_findings(session_id, project_id, team_id=team_id) or []
    _attach_package_finding_triage(session_id, findings, team_id=team_id)
    manifest = _evidence_manifest_from_summary(summary, payload, findings)
    attach_finding_evidence_links(
        session_id,
        project_id,
        manifest.get("findings", []),
        team_id=team_id,
    )
    assessment_context = get_project_assessment_context(
        session_id,
        project_id,
        assessment_id=payload["assessment_id"],
        findings=manifest.get("findings", []),
        selected_artifact_ids=(
            str(artifact.get("id") or "")
            for artifact in manifest.get("artifacts", [])
            if isinstance(artifact, dict)
        ),
        team_id=team_id,
    )
    manifest["assessment_context"] = assessment_context
    manifest["assessment_finding_changes"] = (
        assessment_context.get("finding_changes")
        if isinstance(assessment_context, dict)
        else None
    )
    redaction_rules = _package_redaction_rules(payload["redaction_mode"])
    if redaction_rules:
        manifest = _redact_package_manifest(manifest, redaction_rules)
        payload["name"] = apply_redaction_rules(payload["name"], redaction_rules)
        payload["description"] = apply_redaction_rules(payload["description"], redaction_rules)
    created = _now()
    with get_db_connect()() as conn:
        package_where = "project_id = ?"
        package_params = [project_id]
        if not team_id:
            package_where += " AND session_id = ?"
            package_params.append(session_id)
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM evidence_packages WHERE " + package_where,  # nosec
            package_params,
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
                    dialect_for_backend(get_db_backend()).boolean_param(payload["include_artifacts"]),
                    dialect_for_backend(get_db_backend()).json_param(manifest),
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
                    team_id=team_id,
                )
                conn.commit()
                return get_evidence_package(session_id, project_id, package_id, team_id=team_id)
        raise ProjectWorkspaceError("could not allocate a package id")


def delete_evidence_package(session_id, project_id, package_id, *, team_id="", conn=None):
    if conn is None:
        with get_db_connect()() as opened:
            deleted = delete_evidence_package(
                session_id,
                project_id,
                package_id,
                team_id=team_id,
                conn=opened,
            )
            if deleted:
                opened.commit()
            return deleted
    else:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
        package_owner_sql = ""
        package_params = [*project_owner_params, project_id, package_id]
        if not team_id:
            package_owner_sql = " AND ep.session_id = ?"
            package_params.append(session_id)
        row = conn.execute(
            "SELECT ep.id FROM evidence_packages ep "
            "JOIN projects p ON p.id = ep.project_id "
            "WHERE " + project_owner_sql + " AND ep.project_id = ? AND ep.id = ?" + package_owner_sql,  # nosec
            package_params,
        ).fetchone()
        if not row:
            return False
        metadata_owner_sql, metadata_owner_params = _metadata_owner_where(session_id, team_id)
        conn.execute(
            "DELETE FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'package' AND entity_id = ?",  # nosec
            (*metadata_owner_params, package_id),
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'package' AND entity_id = ?",  # nosec
            (*metadata_owner_params, package_id),
        )
        delete_where = "project_id = ? AND id = ?"
        delete_params = [project_id, package_id]
        if not team_id:
            delete_where += " AND session_id = ?"
            delete_params.append(session_id)
        result = conn.execute(
            "DELETE FROM evidence_packages WHERE " + delete_where,  # nosec
            delete_params,
        )
    return result.rowcount > 0
