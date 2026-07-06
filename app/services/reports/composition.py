"""Report composition helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import config as _config
from core.database_access import get_db_connect
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


def _run_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {"query": str((filters or {}).get("q") or "")}


def _target_filters(filters: dict[str, Any]) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    return {
        "target_type": str(raw.get("type") or ""),
        "query": str(raw.get("q") or ""),
        "auto_discovered": bool(raw.get("auto_discovered")),
    }


def _finding_filters(filters: dict[str, Any]) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    return {
        "orphan_filter": "all",
        "include_group_counts": "0",
        "q": str(raw.get("q") or ""),
        "review_state": [str(raw.get("review_state") or "")] if raw.get("review_state") else [],
        "severity": [str(raw.get("severity") or "")] if raw.get("severity") else [],
    }


def _artifact_filters(filters: dict[str, Any]) -> dict[str, Any]:
    raw = filters if isinstance(filters, dict) else {}
    return {"q": str(raw.get("q") or "")}


def _has_active_filter(filters: Any) -> bool:
    if not isinstance(filters, dict):
        return False
    for value in filters.values():
        if isinstance(value, bool):
            if value:
                return True
            continue
        if str(value or "").strip():
            return True
    return False


def _empty_page(item_key: str, offset: int) -> dict[str, Any]:
    return {
        item_key: [],
        "total": 0,
        "limit": _REPORT_PAGE_LIMIT,
        "offset": max(0, int(offset or 0)),
        "has_more": False,
    }


def _fetch_runs_page(session_id: str, project_id: str, offset: int, *, filters=None, team_id: str = "") -> dict[str, Any]:
    page = list_project_runs(
        session_id,
        project_id,
        limit=_REPORT_PAGE_LIMIT,
        offset=offset,
        team_id=team_id,
        include_provenance=True,
        **_run_filters(filters if isinstance(filters, dict) else {}),
    )
    return page if isinstance(page, dict) else _empty_page("runs", offset)


def _fetch_targets_page(session_id: str, project_id: str, offset: int, *, filters=None, team_id: str = "") -> dict[str, Any]:
    page = list_project_targets(
        session_id,
        project_id,
        limit=_REPORT_PAGE_LIMIT,
        offset=offset,
        team_id=team_id,
        include_provenance=True,
        **_target_filters(filters if isinstance(filters, dict) else {}),
    )
    return page if isinstance(page, dict) else _empty_page("targets", offset)


def _fetch_findings_page(session_id: str, project_id: str, offset: int, *, filters=None, team_id: str = "") -> dict[str, Any]:
    page = list_project_findings(
        session_id,
        project_id,
        _finding_filters(filters if isinstance(filters, dict) else {}),
        limit=_REPORT_PAGE_LIMIT,
        offset=offset,
        include_total=True,
        team_id=team_id,
    )
    return page if isinstance(page, dict) else {"findings": page if isinstance(page, list) else []}


def _fetch_artifacts_page(session_id: str, project_id: str, offset: int, *, filters=None, team_id: str = "") -> dict[str, Any]:
    page = list_project_artifacts(
        session_id,
        project_id,
        _artifact_filters(filters if isinstance(filters, dict) else {}),
        limit=_REPORT_PAGE_LIMIT,
        offset=offset,
        team_id=team_id,
    )
    return page if isinstance(page, dict) else _empty_page("artifacts", offset)


def _page_total(payload: Any, item_count: int) -> int:
    if not isinstance(payload, dict):
        return item_count
    if "total" not in payload:
        return item_count
    return max(0, int(payload.get("total") or 0))


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


def _collect_matching_items(
    *,
    key: str,
    item_key: str,
    fetch_page,
    exclude_ids: list[str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    excluded = {str(value or "") for value in (exclude_ids or []) if str(value or "")}
    offset = 0
    total = 0
    while True:
        page = fetch_page(offset)
        if page is None:
            raise ProjectWorkspaceError(f"report selection could not resolve {key} items")
        rows = _page_items(page, item_key)
        if offset == 0:
            total = _page_total(page, len(rows))
        for row in rows:
            row_id = str(row.get("id") or "")
            if not row_id or row_id in seen:
                continue
            seen.add(row_id)
            if row_id not in excluded:
                items.append(row)
        if not rows or not _page_has_more(page, offset, len(rows)):
            break
        offset += len(rows)
    return items, total


def _resolve_report_selection(
    *,
    selected_ids: list[str],
    mode: str,
    key: str,
    item_key: str,
    fetch_page,
    exclude_ids: list[str],
    fetch_selected_page=None,
) -> tuple[list[dict[str, Any]], int]:
    if mode != "manual":
        return _collect_matching_items(
            key=key,
            item_key=item_key,
            fetch_page=fetch_page,
            exclude_ids=exclude_ids,
        )
    if not selected_ids:
        return [], 0
    selected = _resolve_selected_items(
        [],
        selected_ids,
        key=key,
        item_key=item_key,
        fetch_page=fetch_selected_page or fetch_page,
    )
    return selected, len(selected)


def _target_references_need_full_project_set(
    *,
    selected_findings: list[dict[str, Any]],
    target_mode: str,
    target_filters: Any,
    target_exclude_ids: list[str],
) -> bool:
    if not selected_findings:
        return False
    return (
        target_mode == "manual"
        or _has_active_filter(target_filters)
        or bool(target_exclude_ids)
    )


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
    with get_db_connect()() as conn:
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
    selection = normalized_draft.get("selection") or {}
    selection_modes = normalized_draft.get("selection_modes") or {}
    selection_filters = normalized_draft.get("selection_filters") or {}
    selection_exclude_ids = normalized_draft.get("selection_exclude_ids") or {}
    selected_runs, run_total = _resolve_report_selection(
        selected_ids=selection.get("run_ids") or [],
        mode=str(selection_modes.get("run_ids") or "all"),
        key="run",
        item_key="runs",
        fetch_page=lambda offset: _fetch_runs_page(
            session_id,
            selected_project_id,
            offset,
            filters=selection_filters.get("run_ids") or {},
            team_id=team_id,
        ),
        exclude_ids=selection_exclude_ids.get("run_ids") or [],
        fetch_selected_page=lambda offset: _fetch_runs_page(
            session_id,
            selected_project_id,
            offset,
            team_id=team_id,
        ),
    )
    selected_targets, target_total = _resolve_report_selection(
        selected_ids=selection.get("target_ids") or [],
        mode=str(selection_modes.get("target_ids") or "all"),
        key="target",
        item_key="targets",
        fetch_page=lambda offset: _fetch_targets_page(
            session_id,
            selected_project_id,
            offset,
            filters=selection_filters.get("target_ids") or {},
            team_id=team_id,
        ),
        exclude_ids=selection_exclude_ids.get("target_ids") or [],
        fetch_selected_page=lambda offset: _fetch_targets_page(
            session_id,
            selected_project_id,
            offset,
            team_id=team_id,
        ),
    )
    selected_findings, finding_total = _resolve_report_selection(
        selected_ids=selection.get("finding_ids") or [],
        mode=str(selection_modes.get("finding_ids") or "all"),
        key="finding",
        item_key="findings",
        fetch_page=lambda offset: _fetch_findings_page(
            session_id,
            selected_project_id,
            offset,
            filters=selection_filters.get("finding_ids") or {},
            team_id=team_id,
        ),
        exclude_ids=selection_exclude_ids.get("finding_ids") or [],
        fetch_selected_page=lambda offset: _fetch_findings_page(
            session_id,
            selected_project_id,
            offset,
            team_id=team_id,
        ),
    )
    selected_artifacts, artifact_total = _resolve_report_selection(
        selected_ids=selection.get("artifact_ids") or [],
        mode=str(selection_modes.get("artifact_ids") or "all"),
        key="artifact",
        item_key="artifacts",
        fetch_page=lambda offset: _fetch_artifacts_page(
            session_id,
            selected_project_id,
            offset,
            filters=selection_filters.get("artifact_ids") or {},
            team_id=team_id,
        ),
        exclude_ids=selection_exclude_ids.get("artifact_ids") or [],
        fetch_selected_page=lambda offset: _fetch_artifacts_page(
            session_id,
            selected_project_id,
            offset,
            team_id=team_id,
        ),
    )
    selected = {
        "runs": selected_runs,
        "targets": selected_targets,
        "findings": selected_findings,
        "artifacts": selected_artifacts,
    }
    resolved_totals = {
        "runs": run_total,
        "targets": target_total,
        "findings": finding_total,
        "artifacts": artifact_total,
    }
    if session_id:
        _attach_full_finding_triage(session_id, selected["findings"], team_id=team_id)
    target_reference_targets = selected["targets"]
    if _target_references_need_full_project_set(
        selected_findings=selected["findings"],
        target_mode=str(selection_modes.get("target_ids") or "all"),
        target_filters=selection_filters.get("target_ids") or {},
        target_exclude_ids=selection_exclude_ids.get("target_ids") or [],
    ):
        target_reference_targets, _ = _collect_matching_items(
            key="target",
            item_key="targets",
            fetch_page=lambda offset: _fetch_targets_page(
                session_id,
                selected_project_id,
                offset,
                team_id=team_id,
            ),
        )
    attach_finding_target_references(selected["findings"], target_reference_targets)
    selected["artifacts"], artifact_warnings = _attach_artifact_previews(
        session_id,
        selected["artifacts"],
        cfg=cfg,
    )
    context = {
        "draft": normalized_draft,
        "project": dict(project or {}),
        "counts": _compose_counts(selected),
        # `all_counts` is kept as a compatibility alias for older render/context
        # consumers. In large-selection reports it means the matched selector
        # total before exclusions, not the full project-wide dataset size.
        "all_counts": resolved_totals,
        "selection_totals": resolved_totals,
        "selection_filters": selection_filters,
        "selection_exclude_ids": selection_exclude_ids,
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
