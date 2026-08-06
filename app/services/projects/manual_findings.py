# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persistence and edit semantics for assessor-authored findings."""

from __future__ import annotations

import hashlib
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.atlas.recalculation import recalculate_atlas_findings
from services.cve_risk.links import replace_manual_finding_cve_links
from services.cve_risk.ranking import attach_risk_to_findings
from services.projects.contracts import ProjectWorkspaceNotFound
from services.projects.finding_evidence import (
    link_finding_evidence_on_conn,
    list_finding_evidence_links_on_conn,
)
from services.projects.findings import row_to_finding
from services.projects.manual_finding_inputs import (
    normalize_manual_finding_create,
    normalize_manual_finding_update,
)
from services.projects.scope import shared_owner_where
from services.projects.utils import new_finding_id, now, quota_exceeded, raise_quota
from services.runs.comparison_findings import finding_comparison_key


_MANUAL_SELECT_PREFIX = "SELECT f.* FROM findings f WHERE "


def _project_target(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    target_id: str,
) -> dict[str, str]:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p"
    )
    # The owner clause comes from the Project scope service; all values remain bound.
    sql = "".join((
        "SELECT e.id, e.type, e.canonical_value FROM projects p ",
        "JOIN project_links pl ON pl.project_id = p.id ",
        "AND pl.entity_type = 'atlas_entity' AND pl.review_state = 'confirmed' ",
        "JOIN entities e ON e.id = pl.entity_id WHERE ",
        owner_sql,
        " AND p.id = ? AND p.status != 'archived' AND e.id = ?",
    ))
    row = conn.execute(
        sql,
        (*owner_params, project_id, target_id),
    ).fetchone()
    if not row:
        raise ProjectWorkspaceNotFound(
            "manual finding target was not found in this active project scope"
        )
    return {
        "id": str(row["id"] or ""),
        "type": str(row["type"] or ""),
        "canonical_value": str(row["canonical_value"] or ""),
    }


def _owner_count(conn: Any, session_id: str, team_id: str) -> int:
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    sql = "".join((
        "SELECT COUNT(*) AS count FROM findings WHERE ",
        owner_sql,
        " AND origin = 'manual'",
    ))
    row = conn.execute(sql, owner_params).fetchone()
    return int(row["count"] or 0) if row else 0


def _manual_row(
    conn: Any,
    session_id: str,
    team_id: str,
    finding_id: str,
) -> Any:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="f"
    )
    sql = "".join((
        _MANUAL_SELECT_PREFIX,
        owner_sql,
        " AND f.id = ? AND f.origin = 'manual'",
    ))
    return conn.execute(sql, (*owner_params, finding_id)).fetchone()


def _json_param(value: list[str]) -> Any:
    return dialect_for_backend(get_db_backend()).json_param(value)


def _signature(finding_id: str) -> str:
    return hashlib.sha256(f"manual\x1f{finding_id}".encode()).hexdigest()


def _subject_key(target: dict[str, str]) -> str:
    return f"{target['type']}\x1f{target['canonical_value']}"


def _comparison_key(finding: dict[str, Any], snippet: str) -> str:
    return finding_comparison_key(
        tool_root="manual",
        kind="finding",
        subject_key=finding["subject_key"],
        text=snippet,
    )


def _duplicate_candidates(
    conn: Any,
    session_id: str,
    team_id: str,
    target_id: str,
    finding: dict[str, Any],
    *,
    exclude_id: str = "",
) -> list[dict[str, Any]]:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="f"
    )
    sql = "".join((
        "SELECT f.* FROM findings f WHERE ",
        owner_sql,
        " AND f.origin = 'manual' AND COALESCE(f.entity_id, f.target_id) = ? ",
        "ORDER BY f.created DESC, f.id DESC LIMIT 100",
    ))
    rows = conn.execute(
        sql,
        (*owner_params, target_id),
    ).fetchall()
    title_key = str(finding.get("title") or "").strip().casefold()
    cve_ids = {str(value) for value in finding.get("cve_ids", [])}
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if str(row["id"] or "") == exclude_id:
            continue
        candidate = row_to_finding(row)
        candidate_cves = {str(value) for value in candidate.get("cve_ids", [])}
        reasons = []
        if title_key and str(candidate.get("title") or "").strip().casefold() == title_key:
            reasons.append("same_title")
        if cve_ids and cve_ids.intersection(candidate_cves):
            reasons.append("shared_cve")
        if not reasons:
            continue
        candidates.append({
            "id": candidate["id"],
            "title": candidate["title"],
            "severity": candidate["severity"],
            "cve_ids": candidate_cves and sorted(candidate_cves) or [],
            "manual_revision": candidate["manual_revision"],
            "reasons": reasons,
        })
    return candidates[:20]


def _serialize_manual_finding(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    row: Any,
) -> dict[str, Any]:
    finding = row_to_finding(row)
    finding["target_ids"] = [finding["target_id"]] if finding["target_id"] else []
    finding["evidence_links"] = list_finding_evidence_links_on_conn(
        conn,
        session_id,
        project_id,
        finding["id"],
        team_id=team_id,
    )
    attach_risk_to_findings(
        [finding],
        conn,
        owner_by_finding_id={finding["id"]: (session_id, team_id)},
    )
    return finding


def create_manual_finding_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    data: Any,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    payload = normalize_manual_finding_create(data)
    target = _project_target(conn, session_id, team_id, project_id, payload["target_id"])
    if quota_exceeded(
        _owner_count(conn, session_id, team_id), "max_manual_findings_per_owner", 5000
    ):
        raise_quota("manual finding quota exceeded for this owner")
    duplicates = _duplicate_candidates(
        conn, session_id, team_id, target["id"], payload
    )
    if duplicates and not payload["allow_duplicate"]:
        return {
            "created": False,
            "conflict": "possible_duplicate",
            "duplicates": duplicates,
        }
    finding_id = new_finding_id()
    signature = _signature(finding_id)
    created_at = now()
    subject_key = _subject_key(target)
    conn.execute(
        "INSERT INTO findings ("
        "id, session_id, team_id, run_id, target_id, scope, line_number, review_state, "
        "entity_id, subject_key, signature_hash, severity, kind, tool_root, first_run_id, "
        "last_run_id, first_seen_at, last_seen_at, occurrence_count, status, status_updated_at, "
        "fingerprint, title, raw_line, created, origin, validation_method, summary, impact, "
        "reproduction_steps, confidence, cve_ids_json, cwe_ids_json, cvss_vector, cvss_score, "
        "references_json, manual_revision, manual_created_by_session_id, "
        "manual_created_by_member_id, manual_updated_by_session_id, "
        "manual_updated_by_member_id, manual_updated_at"
        ") VALUES (?, ?, ?, '', ?, 'finding', NULL, 'new', ?, ?, ?, ?, 'finding', 'manual', "
        "'', '', ?, ?, 1, 'new', ?, ?, ?, '', ?, 'manual', 'manual_assessment', ?, ?, ?, ?, "
        "?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
        (
            finding_id,
            session_id,
            team_id,
            target["id"],
            target["id"],
            subject_key,
            signature,
            payload["severity"],
            created_at,
            created_at,
            created_at,
            signature,
            payload["title"],
            created_at,
            payload["summary"],
            payload["impact"],
            payload["reproduction_steps"],
            payload["confidence"],
            _json_param(payload["cve_ids"]),
            _json_param(payload["cwe_ids"]),
            payload["cvss_vector"],
            payload["cvss_score"],
            _json_param(payload["references"]),
            session_id,
            actor_member_id,
            session_id,
            actor_member_id,
            created_at,
        ),
    )
    first_snippet = ""
    for evidence_payload in payload["evidence"]:
        result = link_finding_evidence_on_conn(
            conn,
            session_id,
            project_id,
            finding_id,
            evidence_payload,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
        evidence = result["evidence"]
        if evidence["evidence_type"] != "run_line":
            continue
        first_snippet = first_snippet or evidence["snippet"]
        conn.execute(
            "INSERT INTO findings_occurrences "
            "(finding_id, run_id, line_number, snippet, seen_at, observed_severity, comparison_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(finding_id, run_id, line_number) DO UPDATE SET "
            "snippet = excluded.snippet, observed_severity = excluded.observed_severity, "
            "comparison_key = excluded.comparison_key",
            (
                finding_id,
                evidence["run_id"],
                evidence["line_number"],
                evidence["snippet"],
                evidence["observed_at"] or created_at,
                payload["severity"],
                _comparison_key({"subject_key": subject_key}, evidence["snippet"]),
            ),
        )
    if first_snippet:
        conn.execute("UPDATE findings SET raw_line = ? WHERE id = ?", (first_snippet, finding_id))
        recalculate_atlas_findings(conn, [finding_id])
    finding_for_links = {"id": finding_id, **payload, "subject_key": subject_key, "fingerprint": signature}
    replace_manual_finding_cve_links(conn, finding_for_links, created_at=created_at)
    row = _manual_row(conn, session_id, team_id, finding_id)
    return {
        "created": True,
        "duplicate_override": bool(duplicates),
        "finding": _serialize_manual_finding(
            conn, session_id, team_id, project_id, row
        ),
    }


def update_manual_finding_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    finding_id: str,
    data: Any,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    row = _manual_row(conn, session_id, team_id, finding_id)
    if not row:
        raise ProjectWorkspaceNotFound("manual finding was not found")
    existing = row_to_finding(row)
    _project_target(conn, session_id, team_id, project_id, existing["target_id"])
    payload = normalize_manual_finding_update(data, existing=existing)
    current_revision = int(existing["manual_revision"] or 0)
    if payload["expected_revision"] != current_revision:
        return {
            "updated": False,
            "conflict": "stale_revision",
            "current_revision": current_revision,
        }
    duplicates = _duplicate_candidates(
        conn,
        session_id,
        team_id,
        existing["target_id"],
        payload,
        exclude_id=finding_id,
    )
    if duplicates and not payload["allow_duplicate"]:
        return {
            "updated": False,
            "conflict": "possible_duplicate",
            "duplicates": duplicates,
        }
    updated_at = now()
    next_revision = current_revision + 1
    update_cursor = conn.execute(
        "UPDATE findings SET title = ?, severity = ?, summary = ?, impact = ?, "
        "reproduction_steps = ?, confidence = ?, cve_ids_json = ?, cwe_ids_json = ?, "
        "cvss_vector = ?, cvss_score = ?, references_json = ?, manual_revision = ?, "
        "manual_updated_by_session_id = ?, manual_updated_by_member_id = ?, manual_updated_at = ? "
        "WHERE id = ? AND manual_revision = ?",
        (
            payload["title"],
            payload["severity"],
            payload["summary"],
            payload["impact"],
            payload["reproduction_steps"],
            payload["confidence"],
            _json_param(payload["cve_ids"]),
            _json_param(payload["cwe_ids"]),
            payload["cvss_vector"],
            payload["cvss_score"],
            _json_param(payload["references"]),
            next_revision,
            session_id,
            actor_member_id,
            updated_at,
            finding_id,
            current_revision,
        ),
    )
    if update_cursor.rowcount != 1:
        latest = _manual_row(conn, session_id, team_id, finding_id)
        return {
            "updated": False,
            "conflict": "stale_revision",
            "current_revision": int(latest["manual_revision"] or 0) if latest else 0,
        }
    conn.execute(
        "UPDATE findings_occurrences SET observed_severity = ? WHERE finding_id = ?",
        (payload["severity"], finding_id),
    )
    finding_for_links = {
        "id": finding_id,
        **payload,
        "subject_key": existing["subject_key"],
        "fingerprint": existing["fingerprint"],
    }
    replace_manual_finding_cve_links(conn, finding_for_links, created_at=updated_at)
    from services.assessments.reconciliation import (  # noqa: PLC0415
        reconcile_active_assessments_for_finding_on_conn,
    )

    reconcile_active_assessments_for_finding_on_conn(conn, finding_id)
    updated_row = _manual_row(conn, session_id, team_id, finding_id)
    return {
        "updated": True,
        "duplicate_override": bool(duplicates),
        "changed_fields": sorted(
            key
            for key in (
                "title", "severity", "summary", "impact", "reproduction_steps", "confidence",
                "cve_ids", "cwe_ids", "cvss_vector", "cvss_score", "references",
            )
            if payload.get(key) != existing.get(key)
        ),
        "finding": _serialize_manual_finding(
            conn, session_id, team_id, project_id, updated_row
        ),
    }
