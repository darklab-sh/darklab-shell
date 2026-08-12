# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Idempotent persistence for reviewed Dalfox XSS observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.atlas.recalculation import recalculate_atlas_findings
from services.projects.finding_evidence import link_finding_evidence_on_conn
from services.projects.findings import row_to_finding
from services.projects.utils import now


_RESULT_PRESENTATION = {
    "V": ("high", "high", "active_confirmation", "Confirmed XSS"),
    "A": ("medium", "medium", "captured_observation", "Potential XSS"),
    "R": ("low", "low", "captured_observation", "Reflected input"),
}


def persist_dalfox_xss_observations(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    run_id: str,
    observed_at: str,
    entity: Any,
    observations: Sequence[Mapping[str, Any]],
    line_numbers: Sequence[int],
    *,
    source_parameter_run_id: str,
) -> list[dict[str, Any]]:
    """Group repeated proofs by reviewed vector and keep every exact occurrence."""
    grouped: dict[str, dict[str, Any]] = {}
    for observation, line_number in zip(observations, line_numbers, strict=True):
        signature = _signature(str(entity["id"]), observation)
        item = grouped.setdefault(signature, {
            "observation": dict(observation),
            "occurrences": [],
        })
        item["occurrences"].append((int(line_number), dict(observation)))
    persisted: list[dict[str, Any]] = []
    for signature, item in grouped.items():
        observation = item["observation"]
        finding_id, created = _upsert_finding(
            conn, session_id, team_id, entity, signature, observation,
        )
        for line_number, proof in item["occurrences"]:
            _upsert_occurrence(
                conn, finding_id, run_id, line_number, observed_at, entity, proof,
            )
            _link_run_line(
                conn, session_id, team_id, project_id, finding_id, run_id,
                line_number, proof,
            )
        _link_source_run(
            conn, session_id, team_id, project_id, finding_id, source_parameter_run_id,
        )
        recalculate_atlas_findings(conn, [finding_id])
        finding = row_to_finding(
            conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
        )
        if finding:
            finding.update({
                "created_now": created,
                "observation_ids": [
                    str(proof.get("observation_id") or "")
                    for _line, proof in item["occurrences"]
                ],
                "target_ids": [str(entity["id"])],
            })
            persisted.append(finding)
    return persisted


def _signature(entity_id: str, observation: Mapping[str, Any]) -> str:
    material = "\x1f".join((
        "dalfox_xss",
        entity_id,
        str(observation.get("parameter") or ""),
        str(observation.get("location") or ""),
        str(observation.get("result_type") or ""),
        str(observation.get("inject_type") or ""),
        str(observation.get("method") or ""),
    ))
    return hashlib.sha256(material.encode()).hexdigest()


def _upsert_finding(
    conn: Any,
    session_id: str,
    team_id: str,
    entity: Any,
    signature: str,
    observation: Mapping[str, Any],
) -> tuple[str, bool]:
    result_type = str(observation.get("result_type") or "")
    severity, confidence, validation_method, label = _RESULT_PRESENTATION[result_type]
    parameter = str(observation.get("parameter") or "")
    location = str(observation.get("location") or "").lower()
    target = str(entity["canonical_value"])
    title = f"{label} in {parameter}"
    safe_line = f"{label}: {location} parameter {parameter} ({observation['proof_digest']})"
    owner_id = team_id or session_id
    finding_id = "fnd_" + hashlib.sha256(f"{owner_id}\x1f{signature}".encode()).hexdigest()[:32]
    json_param = dialect_for_backend(get_db_backend()).json_param
    created_at = now()
    result = conn.execute(
        "INSERT INTO findings (id, session_id, team_id, run_id, target_id, scope, line_number, "
        "review_state, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
        "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
        "status_updated_at, fingerprint, title, raw_line, created, origin, validation_method, "
        "summary, impact, reproduction_steps, confidence, cwe_ids_json) "
        "VALUES (?, ?, ?, '', ?, 'finding', NULL, 'new', ?, ?, ?, ?, 'finding', 'dalfox', "
        "'', '', '', '', 0, 'new', '', ?, ?, ?, ?, 'run', ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT DO NOTHING",
        (
            finding_id, session_id, team_id, entity["id"], entity["id"],
            f"url\x1f{target}", signature, severity, signature, title, safe_line, created_at,
            validation_method,
            _summary_for(result_type, parameter, location),
            "An attacker-controlled value may execute script in another user's browser "
            "within the affected application origin.",
            "Review the linked Dalfox line and discovery run, then reproduce the exact "
            "parameter using an authorized test account before remediation.",
            confidence,
            json_param(["CWE-79"]),
        ),
    )
    created = max(0, int(getattr(result, "rowcount", 0) or 0)) > 0
    if created:
        return finding_id, True
    row = conn.execute(
        "SELECT id FROM findings WHERE ((? != '' AND team_id = ?) OR "
        "(? = '' AND session_id = ? AND team_id = '')) AND signature_hash = ?",
        (team_id, team_id, team_id, session_id, signature),
    ).fetchone()
    if not row:
        raise RuntimeError("reviewed Dalfox finding identity conflict")
    return str(row["id"]), False


def _summary_for(result_type: str, parameter: str, location: str) -> str:
    if result_type == "V":
        meaning = "Dalfox reported browser execution for the reviewed payload"
    elif result_type == "A":
        meaning = "Dalfox found an AST-level execution path that still needs browser confirmation"
    else:
        meaning = "Dalfox observed reflection without confirming script execution"
    return f"{meaning} in the {location} parameter {parameter}."


def _upsert_occurrence(
    conn: Any,
    finding_id: str,
    run_id: str,
    line_number: int,
    observed_at: str,
    entity: Any,
    observation: Mapping[str, Any],
) -> None:
    result_type = str(observation.get("result_type") or "")
    severity, _confidence, _method, label = _RESULT_PRESENTATION[result_type]
    snippet = f"{label}: {observation['location']} parameter {observation['parameter']}"
    comparison_key = "dalfox_xss:" + ":".join((
        str(entity["id"]),
        str(observation.get("parameter") or ""),
        result_type,
        str(observation.get("proof_digest") or ""),
    ))
    conn.execute(
        "INSERT INTO findings_occurrences "
        "(finding_id, run_id, line_number, snippet, seen_at, observed_severity, comparison_key) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(finding_id, run_id, line_number) DO UPDATE SET "
        "snippet = excluded.snippet, seen_at = excluded.seen_at, "
        "observed_severity = excluded.observed_severity, comparison_key = excluded.comparison_key",
        (finding_id, run_id, line_number, snippet, observed_at, severity, comparison_key),
    )


def _link_run_line(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
    run_id: str,
    line_number: int,
    observation: Mapping[str, Any],
) -> None:
    label = _RESULT_PRESENTATION[str(observation.get("result_type") or "")][3]
    link_finding_evidence_on_conn(
        conn,
        session_id,
        project_id,
        finding_id,
        {
            "evidence_type": "run_line",
            "evidence_id": run_id,
            "line_number": line_number,
            "snippet": f"{label} for reviewed parameter {observation['parameter']}.",
        },
        team_id=team_id,
    )


def _link_source_run(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
    source_run_id: str,
) -> None:
    link_finding_evidence_on_conn(
        conn,
        session_id,
        project_id,
        finding_id,
        {"evidence_type": "run", "evidence_id": source_run_id},
        team_id=team_id,
    )


__all__ = ["persist_dalfox_xss_observations"]
