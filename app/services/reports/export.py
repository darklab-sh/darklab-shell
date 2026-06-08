"""Report archive export helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import tempfile
from typing import Any
import zipfile

from services.projects.contracts import EvidencePackageTooLarge
from services.projects.utils import cfg_mb_bytes

from .models import normalize_report_draft
from .rendering import render_report_html, render_report_markdown, report_generation_metadata


REPORT_ARCHIVE_FORMAT_VERSION = 2
REPORT_ARCHIVE_PROVENANCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ReportExportBundle:
    markdown: str
    html: str
    generation: dict[str, str]


def build_report_export_bundle(
    draft: dict[str, Any] | None,
    *,
    project: dict[str, Any] | None = None,
    session_id: str = "",
    project_id: str = "",
    team_id: str = "",
    cfg: dict | None = None,
) -> ReportExportBundle:
    generated_at = datetime.now(timezone.utc)
    generation = report_generation_metadata(
        {"export": (draft or {}).get("export") if isinstance(draft, dict) else {}},
        generated_at=generated_at,
        cfg=cfg,
    )
    return ReportExportBundle(
        markdown=render_report_markdown(
            draft,
            project=project,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            cfg=cfg,
            generated_at=generated_at,
        ),
        html=render_report_html(
            draft,
            project=project,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            cfg=cfg,
            generated_at=generated_at,
        ),
        generation=generation,
    )


def _archive_filename(project: dict[str, Any] | None) -> str:
    project_id = str((project or {}).get("id") or "").strip()
    slug = str((project or {}).get("slug") or project_id or "project").strip()
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in slug.lower())
    normalized = "-".join(part for part in normalized.split("-") if part) or "project"
    return f"{normalized}-engagement-report.zip"


def _report_manifest_provenance(
    draft: dict[str, Any] | None,
    generation: dict[str, str],
    *,
    project: dict[str, Any] | None = None,
    audit_handoff: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized_draft = normalize_report_draft(draft or {})
    selection = normalized_draft.get("selection") or {}
    selected_entity_ids = {
        key: list(value) if isinstance(value, list) else []
        for key, value in selection.items()
    }
    included_sections = [
        {
            "type": str(section.get("type") or ""),
            "title": str(section.get("title") or ""),
        }
        for section in normalized_draft.get("sections", [])
        if isinstance(section, dict) and section.get("enabled")
    ]
    export_prefs = normalized_draft.get("export") or {}
    provenance = {
        "schema_version": REPORT_ARCHIVE_PROVENANCE_SCHEMA_VERSION,
        "kind": "engagement_report",
        "build": {
            "redaction_mode": generation["redaction_mode"],
            "include_private_notes": bool(export_prefs.get("include_private_notes")),
            "selection_modes": dict(normalized_draft.get("selection_modes") or {}),
            "selected_entity_ids": selected_entity_ids,
            "selected_entity_counts": {
                key: len(value)
                for key, value in selected_entity_ids.items()
            },
            "included_sections": included_sections,
        },
        "sources": {
            "project": {
                "id": str((project or {}).get("id") or ""),
                "name": str((project or {}).get("name") or ""),
                "slug": str((project or {}).get("slug") or ""),
            },
        },
        "privacy": {
            "redaction_mode": generation["redaction_mode"],
            "private_notes_included": bool(export_prefs.get("include_private_notes")),
        },
    }
    if audit_handoff:
        provenance["audit"] = {
            key: str(value)
            for key, value in audit_handoff.items()
            if str(value or "").strip()
        }
    return provenance


def _archive_audit_handoff(event_type: str, job_id: str = "") -> dict[str, str]:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return {}
    return {
        "event_type": event_type,
        "correlation_id": normalized_job_id,
        "job_id": normalized_job_id,
    }


def build_report_export_archive(
    draft: dict[str, Any] | None,
    *,
    project: dict[str, Any] | None = None,
    session_id: str = "",
    project_id: str = "",
    team_id: str = "",
    cfg: dict | None = None,
    archive_dir: str | os.PathLike[str] | None = None,
    progress_callback=None,
    build_job_id: str = "",
) -> dict[str, Any]:
    if progress_callback:
        progress_callback("rendering", "Rendering report")
    bundle = build_report_export_bundle(
        draft,
        project=project,
        session_id=session_id,
        project_id=project_id,
        team_id=team_id,
        cfg=cfg,
    )
    active_cfg = cfg or {}
    max_uncompressed_bytes = cfg_mb_bytes(
        "evidence_package_max_uncompressed_mb",
        500,
        cfg=active_cfg,
    )
    projected_uncompressed = len(bundle.markdown.encode("utf-8")) + len(bundle.html.encode("utf-8"))
    if max_uncompressed_bytes and projected_uncompressed > max_uncompressed_bytes:
        raise EvidencePackageTooLarge("report expanded content estimate exceeds configured size limit")
    manifest = {
        "kind": "engagement_report",
        "format_version": REPORT_ARCHIVE_FORMAT_VERSION,
        "generated_at": bundle.generation["generated_at"],
        "generated_by": {
            "app_name": bundle.generation["app_name"],
            "version": bundle.generation["version"],
        },
        "redaction_mode": bundle.generation["redaction_mode"],
        "project_id": str((project or {}).get("id") or ""),
        "project_name": str((project or {}).get("name") or ""),
        "files": ["report.md", "report.html"],
        "provenance": _report_manifest_provenance(
            draft,
            bundle.generation,
            project=project,
            audit_handoff=_archive_audit_handoff("report.build", build_job_id),
        ),
    }
    if progress_callback:
        progress_callback("archiving", "Writing report archive")
    archive_parent = str(archive_dir or tempfile.gettempdir())
    os.makedirs(archive_parent, mode=0o700, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".zip",
        prefix="report-export-",
        dir=archive_parent,
        delete=False,
    )
    archive_path = handle.name
    handle.close()
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            archive.writestr("report.md", bundle.markdown)
            archive.writestr("report.html", bundle.html)
        byte_size = os.path.getsize(archive_path)
        max_archive_bytes = cfg_mb_bytes("evidence_package_max_mb", 25, cfg=active_cfg)
        if max_archive_bytes and byte_size > max_archive_bytes:
            raise EvidencePackageTooLarge("report ZIP exceeds configured size limit")
    except Exception:
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        raise
    return {
        "path": archive_path,
        "filename": _archive_filename(project),
        "mimetype": "application/zip",
        "byte_size": byte_size,
        "metrics": {
            "archive_bytes": byte_size,
            "files": 3,
        },
    }
