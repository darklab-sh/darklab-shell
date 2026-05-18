"""
Evidence package archive creation and mutation helpers.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import zipfile

from core.database import DB_BACKEND, db_connect
from core.database_backend import dialect_for_backend
from core.redaction import apply_redaction_rules
from services.projects.artifacts import artifact_snapshot_mismatch_reason as _artifact_snapshot_mismatch_reason
from services.projects.contracts import (
    EvidencePackageTooLarge,
    MAX_ENTITY_ID_LEN,
    MAX_ENTITY_NOTE_BODY_LEN,
    ProjectWorkspaceError,
)
from services.projects.findings import list_project_findings
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
    evidence_manifest_from_summary as _evidence_manifest_from_summary,
    normalize_evidence_package_payload as _normalize_evidence_package_payload,
    package_archive_name as _package_archive_name,
    package_manifest_without_private_notes as _package_manifest_without_private_notes,
    package_redaction_rules as _package_redaction_rules,
    redact_package_manifest as _redact_package_manifest,
)
from services.projects.queries import (
    _list_all_project_artifacts,
    get_evidence_package,
    get_project_summary,
)
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
from services.workspace.files import WorkspaceError, resolve_workspace_path


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
