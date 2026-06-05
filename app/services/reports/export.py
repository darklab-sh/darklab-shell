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

from .rendering import render_report_html, render_report_markdown, report_generation_metadata


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
        "format_version": 1,
        "generated_at": bundle.generation["generated_at"],
        "generated_by": {
            "app_name": bundle.generation["app_name"],
            "version": bundle.generation["version"],
        },
        "redaction_mode": bundle.generation["redaction_mode"],
        "project_id": str((project or {}).get("id") or ""),
        "project_name": str((project or {}).get("name") or ""),
        "files": ["report.md", "report.html"],
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
