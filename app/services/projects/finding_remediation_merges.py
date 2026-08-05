# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explicit owner-scoped merges for otherwise distinct remediation groups."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.atlas.scope import finding_source_scope_params, finding_source_scope_sql
from services.cve_risk.ranking import attach_risk_to_findings
from services.projects.contracts import ProjectWorkspaceError
from services.projects.finding_details import finding_detail_fields
from services.projects.finding_identity import finding_identity_references
from services.projects.finding_remediation_merge_store import (
    MEMBER_UPSERT_SQL as _MEMBER_UPSERT_SQL,
    member_payload as _member_payload,
    owner_scope as _owner,
    remediation_identity_value as _identity_value,
    remediation_reference_key,
    rows_by_keys as _rows_by_keys,
    rows_by_merge_ids as _rows_by_merge_ids,
)
from services.projects.finding_vulnerabilities import finding_cves


MAX_MERGE_PREVIEW_OBSERVATIONS = 500
MAX_MERGE_CANDIDATES = 12
MAX_MERGE_QUERY_LEN = 200
_LIKE_ESCAPE = "\\"

_FINDING_COLUMNS = (
    "id, session_id, team_id, entity_id, target_id, subject_key, signature_hash, "
    "origin, validation_method, status, severity, title, raw_line, fingerprint, "
    "summary, impact, reproduction_steps, confidence, cve_ids_json, cwe_ids_json, "
    "cvss_vector, cvss_score, references_json, first_seen_at, last_seen_at, created"
)

_DISPOSITION_UPSERT_SQL = (
    "INSERT INTO finding_remediation_dispositions "
    "(session_id, team_id, affected_subject, identity_kind, identity_value, "
    "vulnerability_id, rule_identity, review_state, remediation, created_at, "
    "updated_at, remediation_updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(session_id, team_id, affected_subject, identity_value) DO UPDATE SET "
    "identity_kind = excluded.identity_kind, vulnerability_id = excluded.vulnerability_id, "
    "rule_identity = excluded.rule_identity, review_state = excluded.review_state, "
    "remediation = excluded.remediation, updated_at = excluded.updated_at, "
    "remediation_updated_at = excluded.remediation_updated_at"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finding_payload(row: Any, *, session_id: str, team_id: str) -> dict[str, Any]:
    finding = dict(row)
    finding.update(finding_detail_fields(row))
    owner_session_id, owner_team_id = _owner(session_id, team_id)
    finding["session_id"] = owner_session_id
    finding["team_id"] = owner_team_id
    return finding


def _load_finding(
    conn: Any,
    session_id: str,
    finding_id: str,
    *,
    team_id: str,
) -> dict[str, Any] | None:
    scope_sql = finding_source_scope_sql("f", team_id)
    query = (
        f"SELECT {_FINDING_COLUMNS} FROM findings f WHERE {scope_sql} "  # nosec
        "AND f.id = ?"
    )
    row = conn.execute(
        query,
        (*finding_source_scope_params(session_id, team_id), finding_id),
    ).fetchone()
    if not row:
        return None
    finding = _finding_payload(row, session_id=session_id, team_id=team_id)
    attach_risk_to_findings(
        [finding],
        conn=conn,
        owner_by_finding_id={
            str(finding.get("id") or ""): _owner(session_id, team_id),
        },
    )
    return finding


def _primary_member(finding: dict[str, Any]) -> dict[str, str]:
    references = finding_identity_references(finding, finding_cves(finding))
    primary_remediation_id = str(finding.get("remediation_id") or "")
    reference = next(
        (
            item for item in references
            if str(item.get("remediation_id") or "") == primary_remediation_id
        ),
        references[0],
    )
    key = remediation_reference_key(
        str(finding.get("session_id") or ""),
        str(finding.get("team_id") or ""),
        reference,
    )
    return _member_payload(key, reference)


def _member_rows_for_primary(conn: Any, member: dict[str, str]) -> list[dict[str, str]]:
    key = (
        member["session_id"],
        member["team_id"],
        member["affected_subject"],
        member["identity_value"],
    )
    rows = _rows_by_keys(conn, {key})
    if not rows:
        return [dict(member)]
    merge_id = str(rows[0]["merge_id"] or "")
    return [
        {
            "session_id": str(row["session_id"] or ""),
            "team_id": str(row["team_id"] or ""),
            "affected_subject": str(row["affected_subject"] or ""),
            "identity_kind": str(row["identity_kind"] or "rule"),
            "identity_value": str(row["identity_value"] or ""),
            "vulnerability_id": str(row["vulnerability_id"] or ""),
            "rule_identity": str(row["rule_identity"] or ""),
            "remediation_id": "",
            "merge_id": merge_id,
        }
        for row in _rows_by_merge_ids(conn, {(key[0], key[1], merge_id)})
    ]


def _matching_observations(
    conn: Any,
    session_id: str,
    team_id: str,
    members: list[dict[str, str]],
) -> list[dict[str, str]]:
    scope_sql = finding_source_scope_sql("f", team_id)
    scope_params = finding_source_scope_params(session_id, team_id)
    findings: dict[str, dict[str, Any]] = {}
    for affected_subject in sorted({item["affected_subject"] for item in members}):
        subject_clause = "f.id = ?"
        value = affected_subject.removeprefix("observation:")
        params: tuple[Any, ...] = (*scope_params, value)
        if affected_subject.startswith("entity:"):
            subject_clause = "(f.entity_id = ? OR f.target_id = ?)"
            value = affected_subject.removeprefix("entity:")
            params = (*scope_params, value, value)
        elif affected_subject.startswith("subject:"):
            subject_clause = "f.subject_key = ?"
            value = affected_subject.removeprefix("subject:")
            params = (*scope_params, value)
        query = (
            f"SELECT {_FINDING_COLUMNS} FROM findings f WHERE {scope_sql} "  # nosec
            f"AND {subject_clause} ORDER BY f.id LIMIT ?"
        )
        rows = conn.execute(
            query,
            (*params, MAX_MERGE_PREVIEW_OBSERVATIONS + 1),
        ).fetchall()
        if len(rows) > MAX_MERGE_PREVIEW_OBSERVATIONS:
            raise ProjectWorkspaceError("remediation merge affects too many observations")
        for row in rows:
            findings[str(row["id"])] = _finding_payload(
                row,
                session_id=session_id,
                team_id=team_id,
            )
    member_keys = {
        (
            item["session_id"],
            item["team_id"],
            item["affected_subject"],
            item["identity_value"],
        )
        for item in members
    }
    observations: dict[str, dict[str, str]] = {}
    for finding in findings.values():
        for reference in finding_identity_references(finding, finding_cves(finding)):
            key = remediation_reference_key(
                str(finding.get("session_id") or ""),
                str(finding.get("team_id") or ""),
                reference,
            )
            if key not in member_keys:
                continue
            observation_id = str(reference.get("observation_id") or "")
            observations[observation_id] = {
                "observation_id": observation_id,
                "finding_id": str(finding.get("id") or ""),
                "title": str(finding.get("title") or finding.get("raw_line") or "Finding")[:240],
                "validation_method": str(reference.get("validation_method") or ""),
                "affected_subject": str(reference.get("affected_subject") or ""),
                "vulnerability_id": str(reference.get("vulnerability_id") or ""),
                "rule_identity": str(reference.get("rule_identity") or ""),
            }
    if len(observations) > MAX_MERGE_PREVIEW_OBSERVATIONS:
        raise ProjectWorkspaceError("remediation merge affects too many observations")
    return [observations[key] for key in sorted(observations)]


def _group_summary(finding: dict[str, Any], member: dict[str, str]) -> dict[str, Any]:
    reference = next((
        item for item in finding.get("remediation_groups", [])
        if str(item.get("remediation_id") or "") == member["remediation_id"]
    ), {})
    return {
        "finding_id": str(finding.get("id") or ""),
        "title": str(finding.get("title") or finding.get("raw_line") or "Finding")[:240],
        "remediation_id": member["remediation_id"],
        "affected_subject": member["affected_subject"],
        "identity_kind": member["identity_kind"],
        "vulnerability_id": member["vulnerability_id"],
        "rule_identity": member["rule_identity"],
        "review_state": str(reference.get("review_state") or finding.get("status") or "new"),
        "has_remediation": bool(reference.get("has_remediation")),
        "remediation_preview": str(reference.get("remediation_preview") or ""),
    }


def _preview_token(payload: dict[str, Any]) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()


def _build_preview(
    conn: Any,
    session_id: str,
    finding_id: str,
    target_finding_id: str,
    *,
    team_id: str,
) -> dict[str, Any] | None:
    source = _load_finding(conn, session_id, finding_id, team_id=team_id)
    target = _load_finding(conn, session_id, target_finding_id, team_id=team_id)
    if not source or not target:
        return None
    if finding_id == target_finding_id:
        raise ProjectWorkspaceError("choose a different finding to merge")
    source_primary = _primary_member(source)
    target_primary = _primary_member(target)
    source_members = _member_rows_for_primary(conn, source_primary)
    target_members = _member_rows_for_primary(conn, target_primary)
    all_members = {
        (
            item["session_id"],
            item["team_id"],
            item["affected_subject"],
            item["identity_value"],
        ): item
        for item in [*source_members, *target_members]
    }
    source_keys = {
        (item["session_id"], item["team_id"], item["affected_subject"], item["identity_value"])
        for item in source_members
    }
    target_keys = {
        (item["session_id"], item["team_id"], item["affected_subject"], item["identity_value"])
        for item in target_members
    }
    if source_keys == target_keys:
        raise ProjectWorkspaceError("these findings already share a remediation group")
    observations = _matching_observations(
        conn,
        session_id,
        team_id,
        list(all_members.values()),
    )
    source_summary = _group_summary(source, source_primary)
    target_summary = _group_summary(target, target_primary)
    token_payload = {
        "source_finding_id": finding_id,
        "target_finding_id": target_finding_id,
        "members": [list(key) for key in sorted(all_members)],
        "observations": [item["observation_id"] for item in observations],
        "source": source_summary,
        "target": target_summary,
    }
    return {
        "source": source_summary,
        "target": target_summary,
        "member_count": len(all_members),
        "observation_count": len(observations),
        "observations": observations,
        "preview_token": _preview_token(token_payload),
        "_members": list(all_members.values()),
    }


def preview_remediation_group_merge(
    session_id: str,
    finding_id: str,
    target_finding_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        preview = _build_preview(
            conn,
            session_id,
            finding_id,
            target_finding_id,
            team_id=team_id,
        )
    if preview:
        preview.pop("_members", None)
    return preview


def _dispositions_for_members(conn: Any, members: list[dict[str, str]]) -> list[dict[str, Any]]:
    keys = {
        (item["session_id"], item["team_id"], item["affected_subject"], item["identity_value"])
        for item in members
    }
    rows: list[Any] = []
    ordered = sorted(keys)
    for offset in range(0, len(ordered), 80):
        chunk = ordered[offset:offset + 80]
        clauses = " OR ".join(
            "(session_id = ? AND team_id = ? AND affected_subject = ? AND identity_value = ?)"
            for _ in chunk
        )
        # The clause shape is fixed; every owner and identity value remains bound.
        rows.extend(conn.execute(
            "SELECT session_id, team_id, affected_subject, identity_value, review_state, "
            "remediation, created_at, updated_at, remediation_updated_at "
            "FROM finding_remediation_dispositions WHERE "  # nosec B608
            + clauses,
            tuple(value for key in chunk for value in key),
        ).fetchall())
    return [dict(row) for row in rows]


def _winning_disposition(
    dispositions: list[dict[str, Any]],
    target: dict[str, Any],
    *,
    default_review_state: str,
) -> dict[str, Any]:
    target_key = (
        target["affected_subject"],
        _identity_value(target),
    )
    target_rows = [
        row for row in dispositions
        if (str(row.get("affected_subject") or ""), str(row.get("identity_value") or ""))
        == target_key
    ]
    review_row = (target_rows or sorted(
        dispositions,
        key=lambda row: str(row.get("updated_at") or ""),
        reverse=True,
    ))[:1]
    guidance_rows = [row for row in target_rows if row.get("remediation_updated_at") is not None]
    if not guidance_rows:
        guidance_rows = sorted(
            (row for row in dispositions if row.get("remediation_updated_at") is not None),
            key=lambda row: str(row.get("remediation_updated_at") or ""),
            reverse=True,
        )
    review = review_row[0] if review_row else {}
    guidance = guidance_rows[0] if guidance_rows else {}
    return {
        "review_state": str(review.get("review_state") or default_review_state or "new"),
        "remediation": str(guidance.get("remediation") or ""),
        "remediation_updated_at": guidance.get("remediation_updated_at"),
    }


def merge_remediation_groups(
    session_id: str,
    finding_id: str,
    target_finding_id: str,
    preview_token: str,
    *,
    team_id: str = "",
) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        conn.execute(dialect_for_backend(get_db_backend()).begin_immediate_sql())
        preview = _build_preview(
            conn,
            session_id,
            finding_id,
            target_finding_id,
            team_id=team_id,
        )
        if not preview:
            return None
        if not preview_token or not secrets.compare_digest(
            str(preview_token), str(preview["preview_token"])
        ):
            raise ProjectWorkspaceError("remediation merge preview is stale; preview it again")
        members = preview.pop("_members")
        member_keys = {
            (item["session_id"], item["team_id"], item["affected_subject"], item["identity_value"])
            for item in members
        }
        existing = _rows_by_keys(conn, member_keys)
        target_finding = _load_finding(
            conn,
            session_id,
            target_finding_id,
            team_id=team_id,
        )
        if not target_finding:
            return None
        target_member = _primary_member(target_finding)
        target_key = (
            target_member["session_id"],
            target_member["team_id"],
            target_member["affected_subject"],
            target_member["identity_value"],
        )
        target_merge_id = next((
            str(row["merge_id"] or "")
            for row in existing
            if (
                str(row["session_id"] or ""), str(row["team_id"] or ""),
                str(row["affected_subject"] or ""), str(row["identity_value"] or ""),
            ) == target_key
        ), "")
        merge_id = target_merge_id or "rmg_" + secrets.token_hex(16)
        created_at = _now()
        conn.executemany(_MEMBER_UPSERT_SQL, [
            (
                item["session_id"], item["team_id"], merge_id,
                item["affected_subject"], item["identity_kind"], item["identity_value"],
                item["vulnerability_id"], item["rule_identity"], session_id, created_at,
            )
            for item in members
        ])
        stale_merge_ids = {
            str(row["merge_id"] or "") for row in existing
            if str(row["merge_id"] or "") and str(row["merge_id"] or "") != merge_id
        }
        for stale_merge_id in sorted(stale_merge_ids):
            conn.execute(
                "UPDATE finding_remediation_merge_members SET merge_id = ? "
                "WHERE session_id = ? AND team_id = ? AND merge_id = ?",
                (merge_id, target_key[0], target_key[1], stale_merge_id),
            )
        final_rows = _rows_by_merge_ids(conn, {(target_key[0], target_key[1], merge_id)})
        final_members = [{
            "session_id": str(row["session_id"] or ""),
            "team_id": str(row["team_id"] or ""),
            "affected_subject": str(row["affected_subject"] or ""),
            "identity_kind": str(row["identity_kind"] or "rule"),
            "identity_value": str(row["identity_value"] or ""),
            "vulnerability_id": str(row["vulnerability_id"] or ""),
            "rule_identity": str(row["rule_identity"] or ""),
        } for row in final_rows]
        winner = _winning_disposition(
            _dispositions_for_members(conn, final_members),
            preview["target"],
            default_review_state=str(target_finding.get("status") or "new"),
        )
        conn.executemany(_DISPOSITION_UPSERT_SQL, [
            (
                item["session_id"], item["team_id"], item["affected_subject"],
                item["identity_kind"], item["identity_value"], item["vulnerability_id"],
                item["rule_identity"], winner["review_state"], winner["remediation"],
                created_at, created_at, winner["remediation_updated_at"],
            )
            for item in final_members
        ])
        finding_ids = {item["finding_id"] for item in preview["observations"]}
        conn.executemany(
            "UPDATE findings SET status = ?, status_updated_at = ? WHERE id = ?",
            [(winner["review_state"], created_at, item) for item in sorted(finding_ids)],
        )
        conn.commit()
    return {
        "merge_id": merge_id,
        "member_count": len(final_members),
        "observation_count": preview["observation_count"],
        "source": preview["source"],
        "target": preview["target"],
    }


def search_remediation_merge_candidates(
    session_id: str,
    finding_id: str,
    query: str,
    *,
    team_id: str = "",
) -> list[dict[str, Any]] | None:
    normalized_query = str(query or "").strip()
    if len(normalized_query) < 2:
        return []
    if len(normalized_query) > MAX_MERGE_QUERY_LEN:
        raise ProjectWorkspaceError("remediation merge search is too long")
    with get_db_connect()() as conn:
        source = _load_finding(conn, session_id, finding_id, team_id=team_id)
        if not source:
            return None
        source_member = _primary_member(source)
        source_rows = _member_rows_for_primary(conn, source_member)
        source_keys = {
            (item["session_id"], item["team_id"], item["affected_subject"], item["identity_value"])
            for item in source_rows
        }
        scope_sql = finding_source_scope_sql("f", team_id)
        escaped_query = (
            normalized_query
            .replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
            .replace("%", _LIKE_ESCAPE + "%")
            .replace("_", _LIKE_ESCAPE + "_")
        )
        search_like = f"%{escaped_query}%"
        query = (
            f"SELECT {_FINDING_COLUMNS} FROM findings f WHERE {scope_sql} "  # nosec
            "AND f.id != ? AND (LOWER(f.id) LIKE LOWER(?) ESCAPE '\\' OR "
            "LOWER(COALESCE(f.title, '')) LIKE LOWER(?) ESCAPE '\\' OR "
            "LOWER(COALESCE(f.raw_line, '')) LIKE LOWER(?) ESCAPE '\\' OR "
            "LOWER(COALESCE(f.subject_key, '')) LIKE LOWER(?) ESCAPE '\\' OR "
            "LOWER(COALESCE(f.cve_ids_json, '')) LIKE LOWER(?) ESCAPE '\\') "
            "ORDER BY COALESCE(NULLIF(f.last_seen_at, ''), f.created) DESC, f.id DESC LIMIT ?"
        )
        rows = conn.execute(
            query,
            (
                *finding_source_scope_params(session_id, team_id),
                finding_id,
                search_like, search_like, search_like, search_like, search_like,
                MAX_MERGE_CANDIDATES + 1,
            ),
        ).fetchall()
        findings = [
            _finding_payload(row, session_id=session_id, team_id=team_id)
            for row in rows
        ]
        attach_risk_to_findings(
            findings,
            conn=conn,
            owner_by_finding_id={
                str(finding.get("id") or ""): _owner(session_id, team_id)
                for finding in findings
            },
        )
        candidates: list[dict[str, Any]] = []
        for finding in findings:
            member = _primary_member(finding)
            candidate_rows = _member_rows_for_primary(conn, member)
            candidate_keys = {
                (item["session_id"], item["team_id"], item["affected_subject"], item["identity_value"])
                for item in candidate_rows
            }
            if candidate_keys == source_keys:
                continue
            candidates.append(_group_summary(finding, member))
            if len(candidates) >= MAX_MERGE_CANDIDATES:
                break
        return candidates
