# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared review state for exact finding remediation identities."""

from __future__ import annotations

from typing import Any, Mapping

from services.projects.finding_details import finding_detail_fields
from services.projects.finding_identity import finding_identity_references, owner_scope_key
from services.projects.finding_vulnerabilities import finding_cves


_DISPOSITION_UPSERT_SQL = (
    "INSERT INTO finding_remediation_dispositions "
    "(session_id, team_id, affected_subject, identity_kind, identity_value, "
    "vulnerability_id, rule_identity, review_state, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(session_id, team_id, affected_subject, identity_value) DO UPDATE SET "
    "identity_kind = excluded.identity_kind, "
    "vulnerability_id = excluded.vulnerability_id, "
    "rule_identity = excluded.rule_identity, "
    "review_state = excluded.review_state, "
    "updated_at = excluded.updated_at"
)


def _identity_value(reference: Mapping[str, Any]) -> str:
    vulnerability_id = str(reference.get("vulnerability_id") or "").strip().upper()
    if vulnerability_id:
        return vulnerability_id
    return f"RULE:{str(reference.get('rule_identity') or '').strip()}"


def _reference_key(
    finding: Mapping[str, Any],
    reference: Mapping[str, Any],
) -> tuple[str, str, str, str]:
    session_id, team_id = owner_scope_key(dict(finding))
    return (
        session_id,
        team_id,
        str(reference.get("affected_subject") or ""),
        _identity_value(reference),
    )


def _finding_payload(row: Any) -> dict[str, Any]:
    finding = dict(row)
    finding.update(finding_detail_fields(row))
    return finding


def _finding_with_owner(
    finding: dict[str, Any],
    owner_by_finding_id: Mapping[str, tuple[str, str]] | None,
) -> dict[str, Any]:
    if not owner_by_finding_id:
        return finding
    owner = owner_by_finding_id.get(str(finding.get("id") or ""))
    if owner is None:
        return finding
    return {**finding, "session_id": owner[0], "team_id": owner[1]}


def attach_remediation_dispositions(
    conn: Any,
    findings: list[dict[str, Any]],
    *,
    owner_by_finding_id: Mapping[str, tuple[str, str]] | None = None,
) -> None:
    """Attach canonical group review state to prepared observation references."""
    requested: set[tuple[str, str, str, str]] = set()
    identity_findings: dict[str, dict[str, Any]] = {}
    for finding in findings:
        identity_finding = _finding_with_owner(finding, owner_by_finding_id)
        identity_findings[str(finding.get("id") or "")] = identity_finding
        for reference in finding.get("observation_references", []):
            if isinstance(reference, dict):
                requested.add(_reference_key(identity_finding, reference))

    dispositions: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    ordered = sorted(requested)
    for offset in range(0, len(ordered), 100):
        chunk = ordered[offset:offset + 100]
        clauses = " OR ".join(
            "(session_id = ? AND team_id = ? AND affected_subject = ? AND identity_value = ?)"
            for _ in chunk
        )
        # The clause shape is fixed above; every value remains bound.
        rows = conn.execute(
            "SELECT session_id, team_id, affected_subject, identity_value, "
            "review_state, updated_at FROM finding_remediation_dispositions WHERE "  # nosec B608
            + clauses,
            tuple(value for key in chunk for value in key),
        ).fetchall()
        for row in rows:
            key = (
                str(row["session_id"] or ""),
                str(row["team_id"] or ""),
                str(row["affected_subject"] or ""),
                str(row["identity_value"] or ""),
            )
            dispositions[key] = dict(row)

    for finding in findings:
        legacy_state = str(
            finding.get("review_state") or finding.get("status") or "new"
        )
        identity_finding = identity_findings[str(finding.get("id") or "")]
        references = [
            reference
            for reference in finding.get("observation_references", [])
            if isinstance(reference, dict)
        ]
        has_saved_disposition = any(
            _reference_key(identity_finding, reference) in dispositions
            for reference in references
        )
        fallback_state = "new" if has_saved_disposition else legacy_state
        groups: list[dict[str, Any]] = []
        for reference in references:
            disposition = dispositions.get(_reference_key(identity_finding, reference))
            reference["review_state"] = (
                str(disposition.get("review_state") or fallback_state)
                if disposition
                else fallback_state
            )
            reference["review_state_source"] = (
                "remediation_group" if disposition else "observation"
            )
            reference["disposition_updated_at"] = (
                str(disposition.get("updated_at") or "") if disposition else ""
            )
            groups.append({
                "remediation_id": str(reference.get("remediation_id") or ""),
                "vulnerability_id": str(reference.get("vulnerability_id") or ""),
                "affected_subject": str(reference.get("affected_subject") or ""),
                "review_state": reference["review_state"],
                "review_state_source": reference["review_state_source"],
                "disposition_updated_at": reference["disposition_updated_at"],
            })
        finding["remediation_groups"] = groups


def apply_primary_remediation_disposition(finding: dict[str, Any]) -> None:
    remediation_id = str(finding.get("remediation_id") or "")
    reference = next(
        (
            item
            for item in finding.get("observation_references", [])
            if isinstance(item, dict)
            and str(item.get("remediation_id") or "") == remediation_id
        ),
        None,
    )
    if not reference:
        return
    review_state = str(reference.get("review_state") or "new")
    finding["review_state"] = review_state
    finding["status"] = review_state


def _rows_for_affected_subject(
    conn: Any,
    session_id: str,
    team_id: str,
    affected_subject: str,
) -> list[Any]:
    if affected_subject.startswith("entity:"):
        value = affected_subject.removeprefix("entity:")
        if team_id:
            return conn.execute(
                "SELECT id, session_id, team_id, entity_id, target_id, subject_key, "
                "signature_hash, origin, validation_method, title, raw_line, fingerprint, "
                "cve_ids_json FROM findings "
                "WHERE team_id = ? AND team_id != '' AND (entity_id = ? OR target_id = ?)",
                (team_id, value, value),
            ).fetchall()
        return conn.execute(
            "SELECT id, session_id, team_id, entity_id, target_id, subject_key, "
            "signature_hash, origin, validation_method, title, raw_line, fingerprint, "
            "cve_ids_json FROM findings "
            "WHERE session_id = ? AND team_id = '' AND (entity_id = ? OR target_id = ?)",
            (session_id, value, value),
        ).fetchall()
    if affected_subject.startswith("subject:"):
        value = affected_subject.removeprefix("subject:")
        if team_id:
            return conn.execute(
                "SELECT id, session_id, team_id, entity_id, target_id, subject_key, "
                "signature_hash, origin, validation_method, title, raw_line, fingerprint, "
                "cve_ids_json FROM findings "
                "WHERE team_id = ? AND team_id != '' AND subject_key = ?",
                (team_id, value),
            ).fetchall()
        return conn.execute(
            "SELECT id, session_id, team_id, entity_id, target_id, subject_key, "
            "signature_hash, origin, validation_method, title, raw_line, fingerprint, "
            "cve_ids_json FROM findings "
            "WHERE session_id = ? AND team_id = '' AND subject_key = ?",
            (session_id, value),
        ).fetchall()
    finding_id = affected_subject.removeprefix("observation:")
    if team_id:
        return conn.execute(
            "SELECT id, session_id, team_id, entity_id, target_id, subject_key, "
            "signature_hash, origin, validation_method, title, raw_line, fingerprint, "
            "cve_ids_json FROM findings "
            "WHERE team_id = ? AND team_id != '' AND id = ?",
            (team_id, finding_id),
        ).fetchall()
    return conn.execute(
        "SELECT id, session_id, team_id, entity_id, target_id, subject_key, "
        "signature_hash, origin, validation_method, title, raw_line, fingerprint, "
        "cve_ids_json FROM findings "
        "WHERE session_id = ? AND team_id = '' AND id = ?",
        (session_id, finding_id),
    ).fetchall()


def set_remediation_group_review_state(
    conn: Any,
    finding_ids: set[str],
    *,
    review_state: str,
    updated_at: str,
) -> dict[str, Any]:
    """Update selected findings and every exact matching observation group member."""
    if not finding_ids:
        return {"remediation_group_count": 0, "affected_finding_ids": set()}
    placeholders = ",".join("?" for _ in finding_ids)
    # Placeholders are generated from the bounded selected-id set; values remain bound.
    rows = conn.execute(
        "SELECT id, session_id, team_id, entity_id, target_id, subject_key, "
        "signature_hash, origin, validation_method, title, raw_line, fingerprint, "
        f"cve_ids_json FROM findings WHERE id IN ({placeholders})",  # nosec
        tuple(sorted(finding_ids)),
    ).fetchall()
    selected = [_finding_payload(row) for row in rows]
    groups: dict[tuple[str, str, str, str], dict[str, str]] = {}
    subjects: set[tuple[str, str, str]] = set()
    for finding in selected:
        references = finding_identity_references(finding, finding_cves(finding))
        session_id, team_id = owner_scope_key(finding)
        for reference in references:
            key = _reference_key(finding, reference)
            groups[key] = {
                "identity_kind": str(reference.get("identity_kind") or "rule"),
                "vulnerability_id": str(reference.get("vulnerability_id") or ""),
                "rule_identity": str(reference.get("rule_identity") or ""),
            }
            subjects.add((session_id, team_id, key[2]))

    conn.executemany(
        _DISPOSITION_UPSERT_SQL,
        [
            (
                session_id,
                team_id,
                affected_subject,
                details["identity_kind"],
                identity_value,
                details["vulnerability_id"],
                details["rule_identity"],
                review_state,
                updated_at,
                updated_at,
            )
            for (session_id, team_id, affected_subject, identity_value), details
            in sorted(groups.items())
        ],
    )

    candidates: dict[str, dict[str, Any]] = {}
    for session_id, team_id, affected_subject in sorted(subjects):
        for row in _rows_for_affected_subject(
            conn,
            session_id,
            team_id,
            affected_subject,
        ):
            candidates[str(row["id"])] = _finding_payload(row)
    affected_ids: set[str] = set()
    for finding_id, finding in candidates.items():
        references = finding_identity_references(finding, finding_cves(finding))
        if any(_reference_key(finding, reference) in groups for reference in references):
            affected_ids.add(finding_id)
    conn.executemany(
        "UPDATE findings SET status = ?, status_updated_at = ? WHERE id = ?",
        [(review_state, updated_at, finding_id) for finding_id in sorted(affected_ids)],
    )
    return {
        "remediation_group_count": len(groups),
        "affected_finding_ids": affected_ids,
    }
