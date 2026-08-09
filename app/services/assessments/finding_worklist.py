# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Cycle-scoped, remediation-level fix-first worklist."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.contracts import ASSESSMENT_MAX_FILTER_LEN, AssessmentError
from services.cve_risk.ranking import build_remediation_worklist
from services.projects.finding_details import finding_detail_fields
from services.projects.finding_provenance import (
    normalize_finding_origin,
    normalize_finding_validation_method,
)
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload


ASSESSMENT_FINDING_PRIORITIES = frozenset({"", "kev", "epss", "cvss", "unscored"})
ASSESSMENT_FINDING_PAGE_MAX = 100
_FINDING_QUERY_CHUNK = 500


def _normalized_priority(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) > ASSESSMENT_MAX_FILTER_LEN:
        raise AssessmentError("assessment finding priority filter is too long")
    if normalized not in ASSESSMENT_FINDING_PRIORITIES:
        raise AssessmentError("assessment finding priority filter is unsupported")
    return normalized


def _current_observation_scope(
    conn: Any,
    assessment_id: str,
) -> tuple[set[str], set[str]]:
    rows = conn.execute(
        "SELECT remediation_id, current_observations_json "
        "FROM project_assessment_finding_deltas WHERE current_assessment_id = ?",
        (assessment_id,),
    ).fetchall()
    dialect = dialect_for_backend(get_db_backend())
    finding_ids: set[str] = set()
    remediation_ids: set[str] = set()
    for row in rows:
        observations = dialect.decode_json_list(row["current_observations_json"])
        current_ids = {
            str(observation.get("finding_id") or "")
            for observation in observations
            if isinstance(observation, dict)
            and str(observation.get("finding_id") or "")
        }
        if current_ids:
            finding_ids.update(current_ids)
            remediation_ids.add(str(row["remediation_id"] or ""))
    return finding_ids, remediation_ids


def _finding_payload(row: Any) -> dict[str, Any]:
    finding = dict(row)
    origin = normalize_finding_origin(finding.get("origin"))
    finding.update(finding_detail_fields(row))
    finding["origin"] = origin
    finding["validation_method"] = normalize_finding_validation_method(
        finding.get("validation_method"),
        origin=origin,
    )
    finding["review_state"] = str(finding.get("status") or "new")
    return finding


def _findings(conn: Any, finding_ids: set[str]) -> list[dict[str, Any]]:
    if not finding_ids:
        return []
    dialect = dialect_for_backend(get_db_backend())
    ordered = sorted(finding_ids)
    rows: list[Any] = []
    for offset in range(0, len(ordered), _FINDING_QUERY_CHUNK):
        chunk = ordered[offset:offset + _FINDING_QUERY_CHUNK]
        in_sql, in_params = dialect.in_clause("f.id", chunk)
        rows.extend(conn.execute(
            "SELECT f.* FROM findings f WHERE " + in_sql,  # nosec B608
            in_params,
        ).fetchall())
    return [_finding_payload(row) for row in rows]


def _risk_signal(item: dict[str, Any]) -> tuple[bool, bool, bool]:
    raw_risk = item.get("risk")
    risk = raw_risk if isinstance(raw_risk, dict) else {}
    raw_kev, raw_epss, raw_cvss = (risk.get(key) for key in ("kev", "epss", "cvss"))
    kev = raw_kev if isinstance(raw_kev, dict) else {}
    epss = raw_epss if isinstance(raw_epss, dict) else {}
    cvss = raw_cvss if isinstance(raw_cvss, dict) else {}
    has_kev = bool(kev.get("listed"))
    has_epss = epss.get("probability") is not None
    has_cvss = item.get("cvss_score") is not None or cvss.get("score") is not None
    return has_kev, has_epss, has_cvss


def _matches_priority(item: dict[str, Any], priority: str) -> bool:
    if not priority:
        return True
    has_kev, has_epss, has_cvss = _risk_signal(item)
    if priority == "kev":
        return has_kev
    if priority == "epss":
        return has_epss
    if priority == "cvss":
        return has_cvss
    return not (has_kev or has_epss or has_cvss)


def _rollup(items: list[dict[str, Any]]) -> dict[str, int]:
    rollup = {
        "total": len(items),
        "kev_listed": 0,
        "epss_scored": 0,
        "cvss_scored": 0,
        "unscored": 0,
    }
    for item in items:
        has_kev, has_epss, has_cvss = _risk_signal(item)
        rollup["kev_listed"] += int(has_kev)
        rollup["epss_scored"] += int(has_epss)
        rollup["cvss_scored"] += int(has_cvss)
        rollup["unscored"] += int(not (has_kev or has_epss or has_cvss))
    return rollup


def assessment_finding_worklist_on_conn(
    conn: Any,
    assessment_id: str,
    *,
    priority: object = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Return current-cycle observations collapsed into fix-first remediation rows."""
    normalized_priority = _normalized_priority(priority)
    safe_limit = normalize_page_limit(limit, default=20, maximum=ASSESSMENT_FINDING_PAGE_MAX)
    safe_offset = normalize_page_offset(offset)
    finding_ids, remediation_ids = _current_observation_scope(conn, assessment_id)
    worklist = build_remediation_worklist(_findings(conn, finding_ids), conn=conn)
    worklist = [
        item
        for item in worklist
        if remediation_ids.intersection(item.get("exact_remediation_ids") or ())
    ]
    rollup = _rollup(worklist)
    filtered = [item for item in worklist if _matches_priority(item, normalized_priority)]
    page = filtered[safe_offset:safe_offset + safe_limit]
    return page_payload(
        "items",
        page,
        len(filtered),
        safe_limit,
        safe_offset,
        extra={
            "priority": normalized_priority,
            "rollup": rollup,
            "source_finding_count": len(finding_ids),
        },
    )
