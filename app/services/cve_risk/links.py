# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""CVE extraction and stable remediation identities for saved findings."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Iterable


_CVE_IN_TEXT_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)


def extract_cve_ids(*values: Any) -> tuple[str, ...]:
    found: set[str] = set()
    for value in values:
        found.update(match.upper() for match in _CVE_IN_TEXT_RE.findall(str(value or "")))
    return tuple(sorted(found))


def remediation_identity(finding: dict[str, Any], cve_id: str) -> str:
    team_id = str(finding.get("team_id") or "")
    session_id = "" if team_id else str(finding.get("session_id") or "")
    subject = str(
        finding.get("entity_id")
        or finding.get("target_id")
        or finding.get("subject_key")
        or finding.get("fingerprint")
        or finding.get("id")
        or ""
    )
    material = "\x1f".join((team_id, session_id, subject, str(cve_id).upper()))
    return "rmd_" + hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:32]


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
