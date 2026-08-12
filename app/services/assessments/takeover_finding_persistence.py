# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Idempotent persistence for confirmed takeover findings and evidence."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

from services.atlas.recalculation import recalculate_atlas_findings
from services.projects.finding_evidence import link_finding_evidence_on_conn
from services.projects.findings import row_to_finding
from services.projects.utils import now


def persist_takeover_confirmation(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    run_id: str,
    hostname: str,
    confirmed: Mapping[str, Any],
    nuclei_line: int,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any] | None:
    entity = _owned_domain_entity(conn, session_id, team_id, run_id, hostname)
    if entity is None:
        return None
    finding_id, created = _upsert_confirmation_finding(
        conn, session_id, team_id, run_id, entity, confirmed, nuclei_line,
    )
    template_id = str(confirmed["confirmation"]["template_id"])
    _link_confirmation_evidence(
        conn, session_id, team_id, project_id, finding_id, run_id, hostname,
        nuclei_line, source, target, template_id,
    )
    recalculate_atlas_findings(conn, [finding_id])
    finding = row_to_finding(conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone())
    if finding is None:
        return None
    finding.update({
        "created_now": created,
        "confirmation_id": str(confirmed["confirmation"]["confirmation_id"]),
        "target_ids": [str(entity["id"])],
    })
    return finding


def _owned_domain_entity(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    hostname: str,
) -> Any | None:
    if team_id:
        return conn.execute(
            "SELECT e.id, e.type, e.canonical_value FROM entities e "
            "JOIN entity_run_links link ON link.entity_id = e.id "
            "WHERE e.team_id = ? AND e.team_id != '' AND e.type = 'domain' "
            "AND e.canonical_value = ? AND link.run_id = ?",
            (team_id, hostname, run_id),
        ).fetchone()
    return conn.execute(
        "SELECT e.id, e.type, e.canonical_value FROM entities e "
        "JOIN entity_run_links link ON link.entity_id = e.id "
        "WHERE e.session_id = ? AND e.team_id = '' AND e.type = 'domain' "
        "AND e.canonical_value = ? AND link.run_id = ?",
        (session_id, hostname, run_id),
    ).fetchone()


def _upsert_confirmation_finding(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    entity: Any,
    confirmed: Mapping[str, Any],
    line_number: int,
) -> tuple[str, bool]:
    confirmation = confirmed["confirmation"]
    hostname = str(entity["canonical_value"])
    template_id = str(confirmation["template_id"])
    signature = hashlib.sha256(
        f"subdomain_takeover\x1f{entity['id']}\x1f{template_id}".encode()
    ).hexdigest()
    owner_id = team_id or session_id
    finding_id = "fnd_" + hashlib.sha256(f"{owner_id}\x1f{signature}".encode()).hexdigest()[:32]
    title = f"Subdomain takeover confirmed for {hostname}"
    observed_at = str(confirmation["observed_at"])
    result = conn.execute(
        "INSERT INTO findings (id, session_id, team_id, run_id, target_id, scope, line_number, "
        "review_state, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
        "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
        "status_updated_at, fingerprint, title, raw_line, created, origin, validation_method, "
        "summary, impact, reproduction_steps, confidence) "
        "VALUES (?, ?, ?, '', ?, 'finding', NULL, 'new', ?, ?, ?, 'high', 'finding', 'nuclei', "
        "'', '', ?, ?, 0, 'new', '', ?, ?, ?, ?, 'run', 'active_confirmation', ?, ?, ?, 'high') "
        "ON CONFLICT DO NOTHING",
        (
            finding_id, session_id, team_id, entity["id"], entity["id"],
            f"domain\x1f{hostname}", signature, observed_at, observed_at,
            str(confirmation["confirmation_id"]), title, title, now(),
            "A reviewed, digest-pinned provider fingerprint matched after compatible saved DNS "
            "evidence showed a dangling CNAME.",
            "Another party may be able to attach the provider resource and serve content from "
            "this hostname.",
            "Review the linked DNS and Nuclei run lines, then remove the stale DNS record or "
            "restore the intended provider resource.",
        ),
    )
    conn.execute(
        "INSERT INTO findings_occurrences "
        "(finding_id, run_id, line_number, snippet, seen_at, observed_severity, comparison_key) "
        "VALUES (?, ?, ?, ?, ?, 'high', ?) "
        "ON CONFLICT(finding_id, run_id, line_number) DO UPDATE SET "
        "snippet = excluded.snippet, seen_at = excluded.seen_at, "
        "observed_severity = excluded.observed_severity, comparison_key = excluded.comparison_key",
        (finding_id, run_id, line_number, title, observed_at, f"takeover:{entity['id']}:{template_id}"),
    )
    return finding_id, max(0, int(getattr(result, "rowcount", 0) or 0)) > 0


def _link_confirmation_evidence(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
    run_id: str,
    hostname: str,
    nuclei_line: int,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    template_id: str,
) -> None:
    evidence = (
        (source, f"DNSx observed the CNAME chain for {hostname}."),
        (target, "DNSx observed the provider target as unresolved."),
    )
    for row, snippet in evidence:
        link_finding_evidence_on_conn(
            conn, session_id, project_id, finding_id,
            {"evidence_type": "run_line", "evidence_id": row["run_id"],
             "line_number": row["line_number"], "snippet": snippet},
            team_id=team_id,
        )
    link_finding_evidence_on_conn(
        conn, session_id, project_id, finding_id,
        {"evidence_type": "run_line", "evidence_id": run_id,
         "line_number": nuclei_line,
         "snippet": f"Reviewed {template_id} matched {hostname}."},
        team_id=team_id,
    )


__all__ = ["persist_takeover_confirmation"]
