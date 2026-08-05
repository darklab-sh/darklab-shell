# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""CVE extraction and stable remediation identities for saved findings."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Iterable

from services.projects.finding_identity import (
    canonical_affected_subject as canonical_affected_subject,
    owner_scope_key as owner_scope_key,
    remediation_identity as remediation_identity,
)
from services.projects.finding_provenance import normalize_finding_validation_method


_CVE_IN_TEXT_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
_CONTEXT_KEYS = ("criticality", "environment", "role")


def extract_cve_ids(*values: Any) -> tuple[str, ...]:
    found: set[str] = set()
    for value in values:
        found.update(match.upper() for match in _CVE_IN_TEXT_RE.findall(str(value or "")))
    return tuple(sorted(found))


def finding_priority_context(finding: dict[str, Any]) -> dict[str, Any]:
    """Keep contextual assessment signals separate from public CVE ordering."""
    confidence = finding.get("confidence")
    if confidence is None or confidence == "":
        confidence = None
    exposure = finding.get("target_exposure", finding.get("exposure"))
    if exposure is None or exposure == "":
        exposure = None
    raw_asset = finding.get("asset_context")
    asset = {
        key: str(raw_asset.get(key) or "").strip()
        for key in _CONTEXT_KEYS
        if isinstance(raw_asset, dict) and str(raw_asset.get(key) or "").strip()
    }
    return {
        "confidence": confidence,
        "exposure": exposure,
        "asset": asset,
    }


def finding_validation_method(finding: dict[str, Any]) -> str:
    origin = str(finding.get("origin") or "").strip().lower()
    if not origin and finding.get("import_sources"):
        origin = "import"
    return normalize_finding_validation_method(
        finding.get("validation_method"),
        origin=origin,
    )


def finding_evidence_keys(finding: dict[str, Any]) -> set[str]:
    """Return typed evidence identities visible in one serialized observation."""
    keys: set[str] = set()
    for field in ("run_id", "first_run_id", "last_run_id"):
        value = str(finding.get(field) or "").strip()
        if value:
            keys.add(f"run:{value}")
    import_sources = finding.get("import_sources")
    if isinstance(import_sources, list):
        for source in import_sources:
            if not isinstance(source, dict):
                continue
            batch_id = str(source.get("batch_id") or "").strip()
            if batch_id:
                keys.add(f"import:{batch_id}")
    evidence = finding.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if not isinstance(item, dict):
                continue
            evidence_type = str(item.get("type") or "").strip().lower()
            evidence_id = str(item.get("id") or "").strip()
            if evidence_type and evidence_id:
                keys.add(f"{evidence_type}:{evidence_id}")
    return keys


def finding_cves(finding: dict[str, Any]) -> tuple[str, ...]:
    explicit = finding.get("cve_ids")
    if isinstance(explicit, (list, tuple)):
        normalized = extract_cve_ids(*explicit)
        if normalized:
            return normalized
    return extract_cve_ids(
        finding.get("title"),
        finding.get("raw_line"),
        finding.get("fingerprint"),
        finding.get("subject_key"),
    )


def sync_finding_cve_links(conn: Any, *, limit: int = 5000) -> int:
    rows = conn.execute(
        "SELECT f.id, f.title, f.raw_line, f.fingerprint, f.subject_key "
        "FROM findings f "
        "WHERE NOT EXISTS (SELECT 1 FROM finding_cve_links l WHERE l.finding_id = f.id) "
        "ORDER BY f.created, f.id LIMIT ?",
        (max(1, min(int(limit), 50000)),),
    ).fetchall()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for row in rows:
        for cve_id in extract_cve_ids(
            row["title"], row["raw_line"], row["fingerprint"], row["subject_key"]
        ):
            result = conn.execute(
                "INSERT INTO finding_cve_links (finding_id, cve_id, link_source, created_at) "
                "VALUES (?, ?, 'captured_text', ?) ON CONFLICT(finding_id, cve_id) DO NOTHING",
                (str(row["id"]), cve_id, now),
            )
            inserted += max(0, int(getattr(result, "rowcount", 0) or 0))
    return inserted


def linked_cve_ids(conn: Any) -> set[str]:
    return {str(row["cve_id"]) for row in conn.execute(
        "SELECT DISTINCT cve_id FROM finding_cve_links"
    ).fetchall()}


def observations_for_cve(conn: Any, cve_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT f.* FROM finding_cve_links l JOIN findings f ON f.id = l.finding_id "
        "WHERE l.cve_id = ? AND COALESCE(f.suppressed, FALSE) = FALSE "
        "AND COALESCE(f.status, f.review_state, 'new') NOT IN ('false_positive', 'resolved') "
        "ORDER BY f.created, f.id",
        (str(cve_id).upper(),),
    ).fetchall()
    return [dict(row) for row in rows]


def group_observations(
    findings: Iterable[dict[str, Any]], cve_id: str
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for finding in findings:
        team_id = str(finding.get("team_id") or "")
        session_id = "" if team_id else str(finding.get("session_id") or "")
        key = (session_id, team_id, remediation_identity(finding, cve_id))
        grouped.setdefault(key, []).append(finding)
    return grouped
