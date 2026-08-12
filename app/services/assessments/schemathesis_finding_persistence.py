# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Materialize safe findings from reviewed Schemathesis failures."""

from __future__ import annotations

import hashlib
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.atlas.recalculation import recalculate_atlas_findings
from services.assessments.schemathesis_report_contracts import (
    SchemathesisFailureExample,
    SchemathesisReport,
)
from services.projects.contracts import MAX_FINDING_TITLE_LEN
from services.projects.finding_evidence import link_finding_evidence_on_conn
from services.projects.findings import row_to_finding


def persist_schemathesis_findings(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    check_id: str,
    run_id: str,
    observed_at: str,
    target_entity_id: str,
    target_value: str,
    report: SchemathesisReport,
) -> list[dict[str, Any]]:
    """Create one stable finding per operation and failed reviewed rule."""
    grouped: dict[str, SchemathesisFailureExample] = {}
    for operation in report.operations:
        for failure in operation.failures:
            signature = _signature(target_entity_id, failure)
            grouped.setdefault(signature, failure)
    findings: list[dict[str, Any]] = []
    for signature, failure in sorted(grouped.items()):
        finding_id, created_now = _upsert_finding(
            conn,
            session_id,
            team_id,
            target_entity_id,
            target_value,
            signature,
            failure,
            observed_at,
        )
        _upsert_occurrence(conn, finding_id, run_id, observed_at, signature, failure)
        recalculate_atlas_findings(conn, [finding_id])
        _link_evidence(
            conn,
            session_id,
            team_id,
            project_id,
            finding_id,
            run_id,
            check_id,
        )
        finding = row_to_finding(
            conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
        )
        if finding:
            finding.update({
                "created_now": created_now,
                "operation": failure.operation,
                "target_ids": [target_entity_id],
            })
            findings.append(finding)
    return findings


def _signature(entity_id: str, failure: SchemathesisFailureExample) -> str:
    material = "\x1f".join((
        "schemathesis",
        entity_id,
        failure.operation,
        failure.check_name,
        failure.failure_type,
    ))
    return hashlib.sha256(material.encode()).hexdigest()


def _upsert_finding(
    conn: Any,
    session_id: str,
    team_id: str,
    target_entity_id: str,
    target_value: str,
    signature: str,
    failure: SchemathesisFailureExample,
    observed_at: str,
) -> tuple[str, bool]:
    owner_id = team_id or session_id
    finding_id = "fnd_" + hashlib.sha256(
        f"{owner_id}\x1f{signature}".encode()
    ).hexdigest()[:32]
    title = f"{failure.title}: {failure.operation}"[:MAX_FINDING_TITLE_LEN]
    status = str(failure.response_status) if failure.response_status is not None else "none"
    raw_line = (
        f"{failure.title} for {failure.operation}; response={status}; "
        f"example={failure.example_digest[:16]}"
    )
    json_param = dialect_for_backend(get_db_backend()).json_param
    result = conn.execute(
        "INSERT INTO findings (id, session_id, team_id, run_id, target_id, scope, line_number, "
        "review_state, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
        "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
        "status_updated_at, fingerprint, title, raw_line, created, origin, validation_method, "
        "summary, impact, reproduction_steps, confidence, cwe_ids_json) "
        "VALUES (?, ?, ?, '', ?, 'finding', NULL, 'new', ?, ?, ?, ?, 'finding', "
        "'schemathesis', '', '', '', '', 0, 'new', ?, ?, ?, ?, ?, 'run', "
        "'active_confirmation', ?, ?, ?, 'high', ?) ON CONFLICT DO NOTHING",
        (
            finding_id,
            session_id,
            team_id,
            target_entity_id,
            target_entity_id,
            f"url\x1f{target_value}",
            signature,
            failure.severity,
            observed_at,
            signature,
            title,
            raw_line,
            observed_at,
            f"Schemathesis reported {failure.title.lower()} while testing {failure.operation}.",
            "The response may reveal an input-validation or response-handling weakness "
            "that needs assessor review.",
            "Review the linked API operation evidence, then reproduce the behavior in "
            "authorized scope. Generated values and response bodies aren't retained.",
            json_param(["CWE-20"]),
        ),
    )
    created_now = max(0, int(getattr(result, "rowcount", 0) or 0)) > 0
    row = conn.execute(
        "SELECT id, entity_id, signature_hash, origin, validation_method FROM findings "
        "WHERE id = ? AND ((? != '' AND team_id = ?) OR "
        "(? = '' AND session_id = ? AND team_id = ''))",
        (finding_id, team_id, team_id, team_id, session_id),
    ).fetchone()
    if not row or (
        str(row["entity_id"] or "") != target_entity_id
        or str(row["signature_hash"] or "") != signature
        or str(row["origin"] or "") != "run"
        or str(row["validation_method"] or "") != "active_confirmation"
    ):
        raise RuntimeError("reviewed Schemathesis finding identity conflict")
    return finding_id, created_now


def _upsert_occurrence(
    conn: Any,
    finding_id: str,
    run_id: str,
    observed_at: str,
    signature: str,
    failure: SchemathesisFailureExample,
) -> None:
    snippet = f"{failure.title} for {failure.operation}"
    conn.execute(
        "INSERT INTO findings_occurrences "
        "(finding_id, run_id, line_number, snippet, seen_at, observed_severity, comparison_key) "
        "VALUES (?, ?, 0, ?, ?, ?, ?) "
        "ON CONFLICT(finding_id, run_id, line_number) DO UPDATE SET "
        "snippet = excluded.snippet, seen_at = excluded.seen_at, "
        "observed_severity = excluded.observed_severity, comparison_key = excluded.comparison_key",
        (
            finding_id,
            run_id,
            snippet,
            observed_at,
            failure.severity,
            f"schemathesis:{signature}",
        ),
    )


def _link_evidence(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
    run_id: str,
    check_id: str,
) -> None:
    for evidence_type, evidence_id in (("run", run_id), ("assessment_check", check_id)):
        link_finding_evidence_on_conn(
            conn,
            session_id,
            project_id,
            finding_id,
            {"evidence_type": evidence_type, "evidence_id": evidence_id},
            team_id=team_id,
        )


__all__ = ["persist_schemathesis_findings"]
