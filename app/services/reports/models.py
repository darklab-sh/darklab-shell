"""Report draft and section models."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import re
from typing import Any

from services.projects.contracts import MAX_ENTITY_ID_LEN, ProjectWorkspaceError
from services.projects.utils import trim_text as _trim_text


REPORT_FORMAT_VERSION = 1
REPORT_SECTION_TYPES = (
    "cover",
    "executive_summary",
    "scope_targets",
    "methodology",
    "findings_by_severity",
    "included_runs",
    "artifacts",
    "appendix",
)
REPORT_SELECTION_KEYS = ("run_ids", "artifact_ids", "finding_ids", "target_ids")
REPORT_SELECTION_MODES = frozenset({"all", "manual"})
REPORT_REDACTION_MODES = frozenset({"redacted", "raw"})
REPORT_SELECTION_ID_LIMIT = 500
REPORT_SELECTION_EXCLUSION_LIMIT = 500

_SECTION_TITLES = {
    "cover": "Cover",
    "executive_summary": "Executive summary",
    "scope_targets": "Scope and targets",
    "methodology": "Methodology",
    "findings_by_severity": "Findings by severity",
    "included_runs": "Included runs",
    "artifacts": "Artifacts",
    "appendix": "Appendix",
}
_DATE_RANGE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})$")
_REPORT_TARGET_FILTER_TYPES = frozenset({"", "domain", "ip", "url"})
_REPORT_FINDING_FILTER_REVIEW_STATES = frozenset({"", "new", "reviewed", "important", "false_positive", "needs_followup"})
_REPORT_FINDING_FILTER_SEVERITIES = frozenset({"", "critical", "high", "medium", "low", "info"})


@dataclass(frozen=True)
class ReportSectionDefinition:
    type: str
    title: str
    enabled: bool = True


def default_section_definitions() -> tuple[ReportSectionDefinition, ...]:
    return tuple(
        ReportSectionDefinition(type=section_type, title=_SECTION_TITLES[section_type], enabled=True)
        for section_type in REPORT_SECTION_TYPES
    )


def _normalize_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _normalize_date_range(value: Any) -> str:
    normalized = _trim_text(value, 120)
    if not normalized:
        return ""
    match = _DATE_RANGE_RE.fullmatch(normalized)
    if not match:
        raise ProjectWorkspaceError("report date range must use YYYY-MM-DD to YYYY-MM-DD")
    try:
        start = date.fromisoformat(match.group(1))
        end = date.fromisoformat(match.group(2))
    except ValueError as exc:
        raise ProjectWorkspaceError("report date range contains an invalid calendar date") from exc
    if end < start:
        raise ProjectWorkspaceError("report date range end date must be on or after the start date")
    return normalized


def _normalize_section(raw: Any, fallback: ReportSectionDefinition) -> dict[str, Any]:
    entry = raw if isinstance(raw, dict) else {}
    section_type = str(entry.get("type") or fallback.type).strip()
    if section_type not in REPORT_SECTION_TYPES:
        raise ProjectWorkspaceError(f"unsupported report section type: {section_type}")
    return {
        "type": section_type,
        "title": _trim_text(entry.get("title"), 120) or _SECTION_TITLES[section_type],
        "enabled": _normalize_bool(entry.get("enabled"), default=fallback.enabled),
    }


def normalize_report_sections(value: Any) -> list[dict[str, Any]]:
    defaults = default_section_definitions()
    if not isinstance(value, list):
        return [_normalize_section({}, fallback) for fallback in defaults]
    by_type: dict[str, dict[str, Any]] = {}
    for raw in value:
        section_type = str((raw or {}).get("type") or "").strip() if isinstance(raw, dict) else ""
        if not section_type:
            continue
        if section_type not in REPORT_SECTION_TYPES:
            raise ProjectWorkspaceError(f"unsupported report section type: {section_type}")
        by_type[section_type] = _normalize_section(raw, ReportSectionDefinition(section_type, _SECTION_TITLES[section_type]))
    normalized = []
    for fallback in defaults:
        normalized.append(by_type.get(fallback.type) or _normalize_section({}, fallback))
    ordered = []
    seen = set()
    for raw in value:
        section_type = str((raw or {}).get("type") or "").strip() if isinstance(raw, dict) else ""
        if section_type in by_type and section_type not in seen:
            ordered.append(by_type[section_type])
            seen.add(section_type)
    for section in normalized:
        if section["type"] not in seen:
            ordered.append(section)
            seen.add(str(section["type"]))
    return ordered


def _normalize_metadata(value: Any) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {
        "engagement_name": _trim_text(raw.get("engagement_name"), 160),
        "date_range": _normalize_date_range(raw.get("date_range")),
        "operator": _trim_text(raw.get("operator"), 120),
        "client": _trim_text(raw.get("client"), 160),
        "contact": _trim_text(raw.get("contact"), 160),
        "executive_summary": _trim_text(raw.get("executive_summary"), 20000),
        "methodology": _trim_text(raw.get("methodology"), 20000),
        "cover_notes": _trim_text(raw.get("cover_notes"), 10000),
    }


def _normalize_selection_values(values: Any, *, limit: int | None = None, label: str = "selection") -> list[str]:
    if values in (None, ""):
        return []
    if not isinstance(values, list):
        raise ProjectWorkspaceError("report selection values must be lists")
    selected = []
    seen = set()
    for value in values:
        normalized = _trim_text(value, MAX_ENTITY_ID_LEN)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        selected.append(normalized)
        if limit is not None and len(selected) > limit:
            raise ProjectWorkspaceError(f"report {label} values are limited to {limit} ids per section")
    return selected


def normalize_report_selection(value: Any) -> dict[str, list[str]]:
    raw = value if isinstance(value, dict) else {}
    target_values = raw.get("target_ids")
    if not target_values and raw.get("entity_ids"):
        target_values = raw.get("entity_ids")
    return {
        key: _normalize_selection_values(
            target_values if key == "target_ids" else raw.get(key),
            limit=REPORT_SELECTION_ID_LIMIT,
            label="manual selection",
        )
        for key in REPORT_SELECTION_KEYS
    }


def normalize_report_selection_exclude_ids(value: Any) -> dict[str, list[str]]:
    raw = value if isinstance(value, dict) else {}
    exclusions: dict[str, list[str]] = {}
    for key in REPORT_SELECTION_KEYS:
        normalized = _normalize_selection_values(
            raw.get(key),
            limit=REPORT_SELECTION_EXCLUSION_LIMIT,
            label="selection exclusion",
        )
        exclusions[key] = normalized
    return exclusions


def _normalize_selection_filter(key: str, value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    if key in {"run_ids", "artifact_ids"}:
        unsupported = set(raw) - {"q"}
        if unsupported:
            raise ProjectWorkspaceError(f"unsupported report {key} filter: {sorted(unsupported)[0]}")
        return {"q": _trim_text(raw.get("q"), 128)}
    if key == "target_ids":
        unsupported = set(raw) - {"q", "type", "auto_discovered"}
        if unsupported:
            raise ProjectWorkspaceError(f"unsupported report target_ids filter: {sorted(unsupported)[0]}")
        target_type = _trim_text(raw.get("type"), 32).lower()
        if target_type not in _REPORT_TARGET_FILTER_TYPES:
            raise ProjectWorkspaceError("report target filter type must be domain, ip, url, or empty")
        auto_discovered = raw.get("auto_discovered")
        return {
            "q": _trim_text(raw.get("q"), 128),
            "type": target_type,
            "auto_discovered": bool(auto_discovered) if auto_discovered is not None else False,
        }
    if key == "finding_ids":
        unsupported = set(raw) - {"q", "review_state", "severity"}
        if unsupported:
            raise ProjectWorkspaceError(f"unsupported report finding_ids filter: {sorted(unsupported)[0]}")
        review_state = _trim_text(raw.get("review_state"), 32).lower()
        severity = _trim_text(raw.get("severity"), 32).lower()
        if review_state not in _REPORT_FINDING_FILTER_REVIEW_STATES:
            raise ProjectWorkspaceError(
                "report finding review filter must be new, reviewed, important, false_positive, needs_followup, or empty"
            )
        if severity not in _REPORT_FINDING_FILTER_SEVERITIES:
            raise ProjectWorkspaceError("report finding severity filter must be critical, high, medium, low, info, or empty")
        return {
            "q": _trim_text(raw.get("q"), 128),
            "review_state": review_state,
            "severity": severity,
        }
    return {}


def normalize_report_selection_filters(value: Any) -> dict[str, dict[str, Any]]:
    raw = value if isinstance(value, dict) else {}
    return {key: _normalize_selection_filter(key, raw.get(key)) for key in REPORT_SELECTION_KEYS}


def normalize_report_selection_modes(value: Any) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    modes = {}
    for key in REPORT_SELECTION_KEYS:
        mode = str(raw.get(key) or "all").strip().lower()
        modes[key] = mode if mode in REPORT_SELECTION_MODES else "all"
    return modes


def normalize_report_export_prefs(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    redaction_mode = str(raw.get("redaction_mode") or "redacted").strip().lower()
    if redaction_mode not in REPORT_REDACTION_MODES:
        raise ProjectWorkspaceError("report redaction mode must be raw or redacted")
    return {
        "redaction_mode": redaction_mode,
        "include_private_notes": bool(raw.get("include_private_notes", False)),
    }


def default_report_draft() -> dict[str, Any]:
    return {
        "metadata": _normalize_metadata({}),
        "sections": normalize_report_sections(None),
        "selection": normalize_report_selection({}),
        "selection_modes": normalize_report_selection_modes({}),
        "selection_filters": normalize_report_selection_filters({}),
        "selection_exclude_ids": normalize_report_selection_exclude_ids({}),
        "export": normalize_report_export_prefs({}),
    }


def normalize_report_draft(value: Any) -> dict[str, Any]:
    raw = deepcopy(value) if isinstance(value, dict) else {}
    return {
        "metadata": _normalize_metadata(raw.get("metadata")),
        "sections": normalize_report_sections(raw.get("sections")),
        "selection": normalize_report_selection(raw.get("selection")),
        "selection_modes": normalize_report_selection_modes(raw.get("selection_modes")),
        "selection_filters": normalize_report_selection_filters(raw.get("selection_filters")),
        "selection_exclude_ids": normalize_report_selection_exclude_ids(raw.get("selection_exclude_ids")),
        "export": normalize_report_export_prefs(raw.get("export")),
    }
