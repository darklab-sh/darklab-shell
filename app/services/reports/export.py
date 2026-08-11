# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Report archive export helpers."""

from __future__ import annotations

from collections.abc import Mapping

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import tempfile
from typing import Any
import zipfile

from services.projects.contracts import EvidencePackageTooLarge
from services.projects.utils import cfg_mb_bytes

from .composition import compose_report_context
from .models import normalize_report_draft
from .rendering import (
    render_report_html_from_context,
    render_report_markdown_from_context,
    report_generation_metadata,
)


REPORT_ARCHIVE_FORMAT_VERSION = 2
REPORT_ARCHIVE_PROVENANCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ReportExportBundle:
    markdown: str
    html: str
    generation: dict[str, str]
    context: dict[str, Any]


def build_report_export_bundle(
    draft: dict[str, Any] | None,
    *,
    project: dict[str, Any] | None = None,
    session_id: str = "",
    project_id: str = "",
    team_id: str = "",
    cfg: Mapping[str, Any] | None = None,
) -> ReportExportBundle:
    generated_at = datetime.now(timezone.utc)
    context = compose_report_context(
        draft,
        project=project,
        session_id=session_id,
        project_id=project_id,
        team_id=team_id,
        cfg=cfg,
    )
    generation = report_generation_metadata(context, generated_at=generated_at, cfg=cfg)
    return ReportExportBundle(
        markdown=render_report_markdown_from_context(context, generated_at=generated_at, cfg=cfg),
        html=render_report_html_from_context(context, generated_at=generated_at, cfg=cfg),
        generation=generation,
        context=context,
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
    context: dict[str, Any] | None = None,
    audit_handoff: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized_draft = normalize_report_draft(draft or {})
    selection = normalized_draft.get("selection") or {}
    selection_filters = normalized_draft.get("selection_filters") or {}
    selection_exclude_ids = normalized_draft.get("selection_exclude_ids") or {}
    resolved_counts = (context or {}).get("counts") if isinstance(context, dict) else {}
    resolved_counts = resolved_counts if isinstance(resolved_counts, dict) else {}
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
            "selection_filters": {
                key: dict(value) if isinstance(value, dict) else {}
                for key, value in selection_filters.items()
            },
            "selection_exclude_ids": {
                key: list(value) if isinstance(value, list) else []
                for key, value in selection_exclude_ids.items()
            },
            "resolved_entity_counts": {
                key: int(value or 0)
                for key, value in resolved_counts.items()
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
    risk_snapshot = (context or {}).get("cve_risk_snapshot")
    if isinstance(risk_snapshot, dict) and risk_snapshot:
        provenance["sources"]["cve_risk"] = risk_snapshot
    finding_changes = (context or {}).get("assessment_finding_changes")
    if isinstance(finding_changes, dict) and finding_changes:
        provenance["sources"]["assessment_finding_changes"] = finding_changes
    assessment_context = (context or {}).get("assessment_context")
    if isinstance(assessment_context, dict) and assessment_context:
        provenance["sources"]["assessment_context"] = assessment_context
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


def _report_export_metrics(
    *,
    byte_size: int,
    context: dict[str, Any],
    draft: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_draft = normalize_report_draft(draft or {})
    counts = context.get("counts") if isinstance(context, dict) else {}
    counts = counts if isinstance(counts, dict) else {}
    totals = context.get("selection_totals") if isinstance(context, dict) else {}
    totals = totals if isinstance(totals, dict) else {}
    exclusions = normalized_draft.get("selection_exclude_ids") or {}
    metrics: dict[str, Any] = {
        "archive_bytes": int(byte_size or 0),
        "files": 3,
        "selection_modes": dict(normalized_draft.get("selection_modes") or {}),
        "selection_excluded_counts": {
            key: len(value) if isinstance(value, list) else 0
            for key, value in exclusions.items()
        },
    }
    for plural_key, metric_key in (
        ("runs", "run"),
        ("targets", "target"),
        ("findings", "finding"),
        ("artifacts", "artifact"),
    ):
        metrics[f"{metric_key}_count"] = int(counts.get(plural_key) or 0)
        metrics[f"{metric_key}_total"] = int(totals.get(plural_key) or 0)
    return metrics


def build_report_export_archive(
    draft: dict[str, Any] | None,
    *,
    project: dict[str, Any] | None = None,
    session_id: str = "",
    project_id: str = "",
    team_id: str = "",
    cfg: Mapping[str, Any] | None = None,
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
            context=bundle.context,
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
        "metrics": _report_export_metrics(
            byte_size=byte_size,
            context=bundle.context,
            draft=draft,
        ),
    }
