# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Idempotent persistence for provenance-complete version inference."""

from __future__ import annotations

import hashlib
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from core.output_targets import command_root
from services.assessments.cpe_applicability import match_cpe_applicability, normalize_observed_cpe
from services.assessments.version_inference_inputs import normalize_version_inference_candidate
from services.atlas.recalculation import recalculate_atlas_findings
from services.projects.utils import now


def persist_version_inference_candidate(
    conn: Any,
    session_id: str,
    candidate: Any,
    *,
    team_id: str = "",
) -> dict[str, Any] | None:
    """Save one revalidated candidate and its immutable source decision."""
    record = normalize_version_inference_candidate(candidate)
    owner_session = str(session_id or "").strip()
    owner_team = str(team_id or "").strip()
    if record is None or not (owner_session or owner_team):
        return None
    source = _source_record(conn, owner_session, owner_team, record)
    entity = _source_entity(conn, owner_session, owner_team, record)
    if source is None or entity is None or not _advisory_rule_matches(conn, record):
        return None
    finding = _upsert_finding(conn, owner_session, owner_team, record, entity)
    if finding is None:
        return None
    finding_id, created = finding
    created_at = now()
    provenance_id = _provenance_id(finding_id, record)
    result = conn.execute(
        "INSERT INTO finding_version_inference_sources ("
        "id, finding_id, source_kind, source_id, observation_id, target, observed_identifier, "
        "observed_version, tool_version, parser_version, observed_at, match_basis, affected_range, "
        "range_type, confidence, advisory_source, advisory_source_version, advisory_origin, "
        "advisory_expires_at, advisory_source_state, advisory_criteria, advisory_match_criteria_id, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(finding_id, source_kind, source_id, observation_id, advisory_source, "
        "advisory_source_version, advisory_match_criteria_id) DO NOTHING",
        (
            provenance_id, finding_id, record["source_kind"], record["source_id"],
            record["observation_id"], record["target"], record["observed_identifier"],
            record["observed_version"], record["tool_version"], record["parser_version"],
            record["observed_at"], record["match_basis"], record["affected_range"],
            record["range_type"], record["confidence"], record["advisory_source"],
            record["advisory_source_version"], record["advisory_origin"],
            record["advisory_expires_at"], record["advisory_source_state"],
            record["advisory_criteria"], record["advisory_match_criteria_id"], created_at,
        ),
    )
    conn.execute(
        "INSERT INTO finding_cve_links (finding_id, cve_id, link_source, created_at) "
        "VALUES (?, ?, 'version_inference', ?) ON CONFLICT(finding_id, cve_id) DO NOTHING",
        (finding_id, record["vulnerability_id"], created_at),
    )
    recalculate_atlas_findings(conn, [finding_id])
    return {
        "finding_id": finding_id,
        "entity_id": str(entity["id"]),
        "created": created,
        "source_created": max(0, int(getattr(result, "rowcount", 0) or 0)) > 0,
    }


def _source_record(conn: Any, session_id: str, team_id: str, record: dict[str, str]) -> Any:
    query = "SELECT s.* FROM runs s " if record["source_kind"] == "run" else (
        "SELECT s.* FROM atlas_import_batches s "
    )
    row = conn.execute(
        query + "WHERE ((? != '' AND s.team_id = ?) OR "
        "(? = '' AND s.session_id = ? AND s.team_id = '')) AND s.id = ?",
        (team_id, team_id, team_id, session_id, record["source_id"]),
    ).fetchone()
    if not row:
        return None
    if record["source_kind"] == "run":
        if row["finished"] is None or row["exit_code"] != 0 or command_root(row["command"]) != "nmap":
            return None
    elif str(row["status"] or "") != "applied":
        return None
    return row


def _source_entity(conn: Any, session_id: str, team_id: str, record: dict[str, str]) -> Any:
    query = (
        "SELECT e.id, e.type, e.canonical_value FROM entities e "
        "WHERE ((? != '' AND e.team_id = ?) OR "
        "(? = '' AND e.session_id = ? AND e.team_id = '')) "
        "AND e.canonical_value = ? AND "
    )
    source_query = (
        "EXISTS (SELECT 1 FROM entity_run_links l WHERE l.entity_id = e.id AND l.run_id = ?) "
        if record["source_kind"] == "run" else
        "EXISTS (SELECT 1 FROM atlas_entity_import_links l WHERE l.entity_id = e.id AND l.batch_id = ?) "
    )
    query += source_query + "ORDER BY e.id LIMIT 2"
    rows = conn.execute(
        query,
        (team_id, team_id, team_id, session_id, record["target"], record["source_id"]),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


def _advisory_rule_matches(conn: Any, record: dict[str, str]) -> bool:
    row = conn.execute(
        "SELECT * FROM cve_advisory_cpe_matches WHERE source = 'nvd' AND cve_id = ? "
        "AND match_criteria_id = ? AND criteria = ? AND source_version = ? AND origin = ?",
        (
            record["vulnerability_id"], record["advisory_match_criteria_id"],
            record["advisory_criteria"], record["advisory_source_version"],
            record["advisory_origin"],
        ),
    ).fetchone()
    observed = normalize_observed_cpe(
        record["observed_identifier"], explicit_version=record["observed_version"]
    )
    if not row or observed is None or str(row["expires_at"] or "") != record["advisory_expires_at"]:
        return False
    match = match_cpe_applicability(observed, [{
        "criteria": str(row["criteria"] or ""),
        "vulnerable": True,
        "applicability_complete": True,
        "negate": False,
        "version_start_including": str(row["version_start_including"] or ""),
        "version_start_excluding": str(row["version_start_excluding"] or ""),
        "version_end_including": str(row["version_end_including"] or ""),
        "version_end_excluding": str(row["version_end_excluding"] or ""),
        "all_versions": bool(row["all_versions"]),
    }])
    return bool(match and all(
        match[key] == record[key] for key in ("match_basis", "affected_range", "range_type")
    ))


def _upsert_finding(
    conn: Any,
    session_id: str,
    team_id: str,
    record: dict[str, str],
    entity: Any,
) -> tuple[str, bool] | None:
    signature = hashlib.sha256(
        f"version_cve_correlation\x1f{entity['id']}\x1f{record['vulnerability_id']}".encode()
    ).hexdigest()
    owner_id = team_id or session_id
    finding_id = "fnd_" + hashlib.sha256(f"{owner_id}\x1f{signature}".encode()).hexdigest()[:32]
    title = f"Version may be affected by {record['vulnerability_id']}"
    subject_key = f"{entity['type']}\x1f{entity['canonical_value']}"
    origin = "run" if record["source_kind"] == "run" else "import"
    # Leave the legacy run columns empty at insert time so its compatibility
    # trigger doesn't manufacture a second occurrence. Recalculation derives
    # those columns from the immutable inference source after it is inserted.
    run_id = ""
    json_param = dialect_for_backend(get_db_backend()).json_param
    result = conn.execute(
        "INSERT INTO findings (id, session_id, team_id, run_id, target_id, scope, line_number, "
        "review_state, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
        "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
        "status_updated_at, fingerprint, title, raw_line, created, origin, validation_method, "
        "summary, confidence, cve_ids_json) VALUES (?, ?, ?, ?, ?, 'finding', NULL, 'new', ?, ?, ?, "
        "'info', 'finding', ?, ?, ?, ?, ?, 0, 'new', '', ?, ?, ?, ?, ?, 'version_inference', ?, "
        "'high', ?) ON CONFLICT DO NOTHING",
        (
            finding_id, session_id, team_id, run_id, entity["id"], entity["id"], subject_key,
            signature, "nmap" if origin == "run" else "import", run_id, run_id,
            record["observed_at"], record["observed_at"], signature, title, title, now(), origin,
            "An exact observed product version matches a stored NVD applicability rule; "
            "this is an inference, not confirmation of vulnerable behavior.",
            json_param([record["vulnerability_id"]]),
        ),
    )
    if max(0, int(getattr(result, "rowcount", 0) or 0)) > 0:
        return finding_id, True
    existing = conn.execute(
        "SELECT id FROM findings WHERE ((? != '' AND team_id = ?) OR "
        "(? = '' AND session_id = ? AND team_id = '')) AND signature_hash = ?",
        (team_id, team_id, team_id, session_id, signature),
    ).fetchone()
    return (str(existing["id"]), False) if existing else None


def _provenance_id(finding_id: str, record: dict[str, str]) -> str:
    material = "\x1f".join((
        finding_id, record["source_kind"], record["source_id"], record["observation_id"],
        record["advisory_source"], record["advisory_source_version"],
        record["advisory_match_criteria_id"],
    ))
    return "vinf_" + hashlib.sha256(material.encode()).hexdigest()[:32]


__all__ = ["persist_version_inference_candidate"]
