"""Report composition helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import config as _config
from core.database import db_connect
from services.projects.artifacts import artifact_owner_context
from services.projects.contracts import ProjectWorkspaceError
from services.projects.findings import list_project_findings
from services.projects.metadata import _finding_triage_by_id
from services.projects.packages import (
    redact_package_value,
    redacted_artifact_derivative_reason,
    strip_target_reference_values,
)
from services.projects.provenance import attach_finding_target_references
from services.projects.queries import list_project_artifacts, list_project_runs
from services.projects.targets import list_project_targets
from services.workspace.files import WorkspaceError, read_owner_workspace_text_file

from .models import normalize_report_draft
from .redaction import report_redaction_rules


_REPORT_PAGE_LIMIT = 500
_ARTIFACT_PREVIEW_CHAR_LIMIT = 12000
_SEVERITY_ORDER = ("critical", "high", "medium", "low", "info", "unknown")


def _page_items(payload: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    items = payload.get(key)
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _findings_page(session_id: str, project_id: str, offset: int, *, team_id: str = "") -> dict[str, Any]:
    page = list_project_findings(
        session_id,
        project_id,
        {"orphan_filter": "all", "include_group_counts": "0"},
        limit=_REPORT_PAGE_LIMIT,
        offset=offset,
        include_total=True,
        team_id=team_id,
    )
    return page if isinstance(page, dict) else {"findings": page if isinstance(page, list) else []}


def _all_project_inputs(session_id: str, project_id: str, *, team_id: str = "") -> dict[str, list[dict[str, Any]]]:
    runs_page = list_project_runs(
        session_id,
        project_id,
        limit=_REPORT_PAGE_LIMIT,
        team_id=team_id,
        include_provenance=True,
    )
    targets_page = list_project_targets(
        session_id,
        project_id,
        limit=_REPORT_PAGE_LIMIT,
        team_id=team_id,
        include_provenance=True,
    )
    findings_page = _findings_page(session_id, project_id, 0, team_id=team_id)
    artifacts_page = list_project_artifacts(session_id, project_id, {}, limit=_REPORT_PAGE_LIMIT, team_id=team_id)
    return {
        "runs": _page_items(runs_page, "runs"),
        "targets": _page_items(targets_page, "targets"),
        "findings": _page_items(findings_page, "findings"),
        "artifacts": _page_items(artifacts_page, "artifacts"),
    }


def _page_has_more(payload: Any, offset: int, item_count: int) -> bool:
    if not isinstance(payload, dict):
        return False
    if "has_more" in payload:
        return bool(payload.get("has_more"))
    total = int(payload.get("total") or 0)
    return bool(total and offset + item_count < total)


def _resolve_selected_items(
    items: list[dict[str, Any]],
    selected_ids: list[str],
    *,
    key: str,
    item_key: str,
    fetch_page,
) -> list[dict[str, Any]]:
    by_id = {str(item.get("id") or ""): item for item in items}
    missing = [item_id for item_id in selected_ids if item_id not in by_id]
    offset = len(items)
    while missing:
        page = fetch_page(offset)
        rows = _page_items(page, item_key)
        if not rows:
            break
        for row in rows:
            row_id = str(row.get("id") or "")
            if row_id and row_id not in by_id:
                by_id[row_id] = row
        missing = [item_id for item_id in selected_ids if item_id not in by_id]
        if not _page_has_more(page, offset, len(rows)):
            break
        offset += len(rows)
    if missing:
        raise ProjectWorkspaceError(f"report selection includes an unknown {key} item")
    return [by_id[item_id] for item_id in selected_ids]


def _selected_items(
    items: list[dict[str, Any]],
    selected_ids: list[str],
    *,
    key: str,
    include_all: bool = True,
    item_key: str = "",
    fetch_page=None,
) -> list[dict[str, Any]]:
    if not selected_ids:
        return list(items) if include_all else []
    by_id = {str(item.get("id") or ""): item for item in items}
    missing = [item_id for item_id in selected_ids if item_id not in by_id]
    if missing:
        if fetch_page and item_key:
            return _resolve_selected_items(
                items,
                selected_ids,
                key=key,
                item_key=item_key,
                fetch_page=fetch_page,
            )
        raise ProjectWorkspaceError(f"report selection includes an unknown {key} item")
    return [by_id[item_id] for item_id in selected_ids]


def _strip_notes(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_notes(item) for item in value]
    if not isinstance(value, dict):
        return value
    clean = {}
    for key, item in value.items():
        if key == "note":
            continue
        if key == "triage" and isinstance(item, dict):
            triage = dict(item)
            triage.pop("verification_notes", None)
            clean[key] = _strip_notes(triage)
            continue
        clean[key] = _strip_notes(item)
    return clean


def _severity_key(finding: dict[str, Any]) -> str:
    severity = str(finding.get("severity") or "unknown").strip().lower()
    return severity if severity in _SEVERITY_ORDER else "unknown"


def _severity_groups(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = []
    for severity in _SEVERITY_ORDER:
        items = [finding for finding in findings if _severity_key(finding) == severity]
        if items:
            groups.append({"severity": severity, "findings": items, "count": len(items)})
    return groups


def _attach_full_finding_triage(session_id: str, findings: list[dict[str, Any]], *, team_id: str = "") -> None:
    finding_ids = [str(finding.get("id") or "") for finding in findings if finding.get("id")]
    if not finding_ids:
        return
    with db_connect() as conn:
        triage_by_id = _finding_triage_by_id(conn, session_id, finding_ids, team_id=team_id)
    for finding in findings:
        triage = triage_by_id.get(str(finding.get("id") or ""))
        if triage:
            finding["triage"] = triage
            finding["verification_status"] = triage.get("verification_status") or finding.get("verification_status")


def _artifact_preview_text(session_id: str, artifact: dict[str, Any], *, cfg: dict | None = None) -> dict[str, Any]:
    label = str(artifact.get("display_name") or artifact.get("workspace_path") or artifact.get("id") or "artifact")
    if not artifact.get("file_available"):
        return {"embedded": False, "reason": artifact.get("file_status_detail") or "Artifact file is not available."}
    reason = redacted_artifact_derivative_reason(artifact)
    if reason:
        return {"embedded": False, "reason": reason}
    try:
        owner = artifact_owner_context(str(artifact.get("session_id") or session_id or ""), artifact)
        text = read_owner_workspace_text_file(owner, str(artifact.get("workspace_path") or ""), cfg or _config.CFG)
    except WorkspaceError as exc:
        return {"embedded": False, "reason": str(exc) or "Artifact preview is unavailable."}
    truncated = len(text) > _ARTIFACT_PREVIEW_CHAR_LIMIT
    if truncated:
        text = text[:_ARTIFACT_PREVIEW_CHAR_LIMIT].rstrip() + "\n...[truncated]"
    return {
        "embedded": True,
        "label": label,
        "text": text,
        "truncated": truncated,
    }


def _attach_artifact_previews(
    session_id: str,
    artifacts: list[dict[str, Any]],
    *,
    cfg: dict | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rendered = []
    warnings = []
    for artifact in artifacts:
        item = dict(artifact)
        preview = _artifact_preview_text(session_id, item, cfg=cfg)
        item["report_preview"] = preview
        if not preview.get("embedded"):
            warnings.append({
                "kind": "artifact",
                "id": item.get("id") or "",
                "label": item.get("display_name") or item.get("workspace_path") or item.get("id") or "",
                "reason": preview.get("reason") or "Artifact is listed instead of embedded.",
            })
        rendered.append(item)
    return rendered, warnings


def _compose_counts(data: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    return {key: len(value) for key, value in data.items()}


def compose_report_context(
    draft: dict[str, Any] | None,
    *,
    project: dict[str, Any] | None = None,
    session_id: str = "",
    project_id: str = "",
    team_id: str = "",
    cfg: dict | None = None,
) -> dict[str, Any]:
    """Return a bounded report context ready for renderers."""
    normalized_draft = normalize_report_draft(draft or {})
    selected_project_id = str(project_id or (project or {}).get("id") or "").strip()
    if session_id and selected_project_id:
        all_inputs = _all_project_inputs(session_id, selected_project_id, team_id=team_id)
    else:
        all_inputs = {"runs": [], "targets": [], "findings": [], "artifacts": []}
    selection = normalized_draft.get("selection") or {}
    selection_modes = normalized_draft.get("selection_modes") or {}
    selected = {
        "runs": _selected_items(
            all_inputs["runs"],
            selection.get("run_ids") or [],
            key="run",
            include_all=selection_modes.get("run_ids") != "manual",
            item_key="runs",
            fetch_page=lambda offset: list_project_runs(
                session_id,
                selected_project_id,
                limit=_REPORT_PAGE_LIMIT,
                offset=offset,
                team_id=team_id,
                include_provenance=True,
            ),
        ),
        "targets": _selected_items(
            all_inputs["targets"],
            selection.get("target_ids") or [],
            key="target",
            include_all=selection_modes.get("target_ids") != "manual",
            item_key="targets",
            fetch_page=lambda offset: list_project_targets(
                session_id,
                selected_project_id,
                limit=_REPORT_PAGE_LIMIT,
                offset=offset,
                team_id=team_id,
                include_provenance=True,
            ),
        ),
        "findings": _selected_items(
            all_inputs["findings"],
            selection.get("finding_ids") or [],
            key="finding",
            include_all=selection_modes.get("finding_ids") != "manual",
            item_key="findings",
            fetch_page=lambda offset: _findings_page(
                session_id,
                selected_project_id,
                offset,
                team_id=team_id,
            ),
        ),
        "artifacts": _selected_items(
            all_inputs["artifacts"],
            selection.get("artifact_ids") or [],
            key="artifact",
            include_all=selection_modes.get("artifact_ids") != "manual",
            item_key="artifacts",
            fetch_page=lambda offset: list_project_artifacts(
                session_id,
                selected_project_id,
                {},
                limit=_REPORT_PAGE_LIMIT,
                offset=offset,
                team_id=team_id,
            ),
        ),
    }
    if session_id:
        _attach_full_finding_triage(session_id, selected["findings"], team_id=team_id)
    attach_finding_target_references(selected["findings"], all_inputs["targets"])
    selected["artifacts"], artifact_warnings = _attach_artifact_previews(
        session_id,
        selected["artifacts"],
        cfg=cfg,
    )
    context = {
        "draft": normalized_draft,
        "project": dict(project or {}),
        "counts": _compose_counts(selected),
        "all_counts": _compose_counts(all_inputs),
        "runs": selected["runs"],
        "targets": selected["targets"],
        "findings": selected["findings"],
        "findings_by_severity": _severity_groups(selected["findings"]),
        "artifacts": selected["artifacts"],
        "artifact_warnings": artifact_warnings,
        "export": normalized_draft.get("export") or {},
    }
    if not bool(context["export"].get("include_private_notes")):
        context = _strip_notes(context)
    rules = report_redaction_rules(context.get("export"), cfg=cfg)
    if rules:
        context = strip_target_reference_values(context)
        context = redact_package_value(deepcopy(context), rules)
    return context if isinstance(context, dict) else {}
