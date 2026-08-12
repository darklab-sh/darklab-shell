# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persist one fully reviewed Schemathesis report inside run finalization."""

from __future__ import annotations

import hashlib
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from core.output_targets import command_root
from services.assessments.schemathesis_actions import SCHEMATHESIS_CHECK_KEY
from services.assessments.schemathesis_finding_persistence import (
    persist_schemathesis_findings,
)
from services.assessments.schemathesis_report_context import (
    ReviewedSchemathesisReportContext,
)
from services.assessments.schemathesis_report_contracts import (
    SchemathesisFailureExample,
    SchemathesisOperationEvidence,
    SchemathesisReport,
)
from services.projects.artifacts import normalize_sha256
from services.projects.scope import shared_owner_where


class SchemathesisEvidenceError(RuntimeError):
    """A stable fail-closed rejection at the structured persistence boundary."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def persist_reviewed_schemathesis_report(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    observed_at: str,
    context: ReviewedSchemathesisReportContext,
) -> dict[str, Any]:
    """Revalidate immutable launch provenance before storing bounded evidence."""
    if type(context) is not ReviewedSchemathesisReportContext:
        raise _error("context_invalid", "Reviewed Schemathesis provenance is unavailable.")
    report = context.parse()
    if type(report) is not SchemathesisReport or not report.complete:
        raise _error("report_incomplete", "Schemathesis report completion isn't valid.")
    contract = _load_storage_contract(conn, session_id, team_id, run_id, context)
    report_id, created_now = _insert_report(
        conn, session_id, team_id, run_id, observed_at, context, report,
    )
    for operation in report.operations:
        _insert_operation(conn, report_id, observed_at, operation)
    findings = persist_schemathesis_findings(
        conn,
        session_id,
        team_id,
        context.project_id,
        context.check_id,
        run_id,
        observed_at,
        str(contract["target_entity_id"]),
        str(contract["target_value"]),
        report,
    )
    return {
        "report_id": report_id,
        "created_now": created_now,
        "operation_count": len(report.operations),
        "case_count": report.case_count,
        "failure_count": report.failure_count,
        "missing_operation_count": len(report.missing_operations),
        "finding_count": len(findings),
        "finding_created_count": sum(bool(item.get("created_now")) for item in findings),
        "findings": findings,
    }


def _load_storage_contract(
    conn: Any, session_id: str, team_id: str, run_id: str,
    context: ReviewedSchemathesisReportContext,
) -> Any:
    assessment_owner_sql, assessment_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="a")
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
    schema_owner_sql, schema_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="schema_run")
    query_template = (
        "SELECT p.status AS project_status, a.status AS assessment_status, "
        "a.profile_key, a.profile_version, c.check_key, c.target_entity_id, "
        "c.target_type, c.target_value, c.applicability, c.policy_level, "
        "c.recommended_action_key, e.type AS entity_type, "
        "e.canonical_value AS entity_value, r.command AS run_command, r.run_kind, "
        "r.finished AS run_finished, r.exit_code AS run_exit_code, "
        "schema_artifact.content_sha256 AS schema_sha256, "
        "schema_artifact.byte_size AS schema_byte_size "
        "FROM project_assessment_checks c "
        "JOIN project_assessments a ON a.id = c.assessment_id "
        "JOIN projects p ON p.id = a.project_id "
        "AND p.session_id = a.session_id AND p.team_id = a.team_id "
        "JOIN entities e ON e.id = c.target_entity_id "
        "AND e.session_id = a.session_id AND e.team_id = a.team_id "
        "JOIN project_links target_link ON target_link.project_id = p.id "
        "AND target_link.entity_type = 'atlas_entity' "
        "AND target_link.entity_id = e.id AND target_link.review_state = 'confirmed' "
        "JOIN project_links run_link ON run_link.project_id = p.id "
        "AND run_link.entity_type = 'run' AND run_link.entity_id = ? "
        "JOIN runs r ON r.id = run_link.entity_id AND {run_owner} "
        "JOIN run_file_artifacts schema_artifact ON schema_artifact.id = ? "
        "JOIN project_links schema_link ON schema_link.project_id = p.id "
        "AND schema_link.entity_type = 'run' AND schema_link.entity_id = schema_artifact.run_id "
        "JOIN runs schema_run ON schema_run.id = schema_artifact.run_id AND {schema_owner} "
        "WHERE a.id = ? AND a.project_id = ? AND c.id = ? "
        "AND {assessment_owner}"
    )
    query = query_template.format(run_owner=run_owner_sql, schema_owner=schema_owner_sql, assessment_owner=assessment_owner_sql)
    row = conn.execute(
        query,
        (
            run_id,
            *run_owner_params,
            context.schema.source_artifact_id,
            *schema_owner_params,
            context.assessment_id,
            context.project_id,
            context.check_id,
            *assessment_owner_params,
        ),
    ).fetchone()
    if not row:
        raise _error("scope_changed", "Reviewed Schemathesis scope is no longer available.")
    valid = (
        str(row["project_status"] or "") == "active"
        and str(row["assessment_status"] or "") == "active"
        and str(row["profile_key"] or "") == context.profile_key
        and str(row["profile_version"] or "") == context.profile_version
        and str(row["check_key"] or "") == SCHEMATHESIS_CHECK_KEY
        and str(row["target_type"] or "") == "url"
        and str(row["target_value"] or "") == context.schema.base_url
        and str(row["entity_type"] or "") == "url"
        and str(row["entity_value"] or "") == context.schema.base_url
        and str(row["applicability"] or "") == "applicable"
        and str(row["policy_level"] or "") == "standard"
        and str(row["recommended_action_key"] or "") == "command:schemathesis"
        and str(row["run_kind"] or "") == "external"
        and command_root(str(row["run_command"] or "")) == "schemathesis"
        and bool(str(row["run_finished"] or ""))
        and int(row["run_exit_code"] if row["run_exit_code"] is not None else -1) == 0
        and normalize_sha256(row["schema_sha256"]) == context.schema.source_sha256
        and int(row["schema_byte_size"] or 0) == len(context.schema.content)
    )
    if not valid:
        raise _error("contract_changed", "Reviewed Schemathesis provenance no longer matches.")
    return row


def _insert_report(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    observed_at: str,
    context: ReviewedSchemathesisReportContext,
    report: SchemathesisReport,
) -> tuple[str, bool]:
    owner_id = team_id or session_id
    report_id = "str_" + hashlib.sha256(
        f"{owner_id}\x1f{context.check_id}\x1f{run_id}".encode()
    ).hexdigest()[:32]
    dialect = dialect_for_backend(get_db_backend())
    result = conn.execute(
        "INSERT INTO schemathesis_run_evidence "
        "(id, session_id, team_id, project_id, assessment_id, check_id, run_id, "
        "schema_artifact_id, schema_sha256, schema_version, profile_key, profile_version, "
        "tool_version, seed, stop_reason, running_time_seconds, expected_operation_count, "
        "observed_operation_count, case_count, failure_count, missing_operations_json, "
        "observed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        (
            report_id,
            session_id,
            team_id,
            context.project_id,
            context.assessment_id,
            context.check_id,
            run_id,
            report.schema_artifact_id,
            report.schema_sha256,
            report.schema_version,
            report.profile_key,
            report.profile_version,
            report.tool_version,
            report.seed,
            report.stop_reason,
            report.running_time_seconds,
            report.expected_operation_count,
            report.observed_operation_count,
            report.case_count,
            report.failure_count,
            dialect.json_param(list(report.missing_operations)),
            observed_at,
            observed_at,
        ),
    )
    created_now = max(0, int(getattr(result, "rowcount", 0) or 0)) > 0
    row = conn.execute(
        "SELECT * FROM schemathesis_run_evidence WHERE id = ?",
        (report_id,),
    ).fetchone()
    if not row or not _report_matches(row, report, context, run_id, dialect):
        raise _error("report_identity_conflict", "Schemathesis report identity conflicts.")
    return report_id, created_now


def _report_matches(
    row: Any,
    report: SchemathesisReport,
    context: ReviewedSchemathesisReportContext,
    run_id: str,
    dialect: Any,
) -> bool:
    return (
        str(row["project_id"] or "") == context.project_id
        and str(row["assessment_id"] or "") == context.assessment_id
        and str(row["check_id"] or "") == context.check_id
        and str(row["run_id"] or "") == run_id
        and str(row["schema_artifact_id"] or "") == report.schema_artifact_id
        and str(row["schema_sha256"] or "") == report.schema_sha256
        and str(row["schema_version"] or "") == report.schema_version
        and str(row["profile_key"] or "") == report.profile_key
        and str(row["profile_version"] or "") == report.profile_version
        and str(row["tool_version"] or "") == report.tool_version
        and int(row["seed"] or 0) == report.seed
        and str(row["stop_reason"] or "") == report.stop_reason
        and float(row["running_time_seconds"] or 0) == report.running_time_seconds
        and int(row["expected_operation_count"] or 0) == report.expected_operation_count
        and int(row["observed_operation_count"] or 0) == report.observed_operation_count
        and int(row["case_count"] or 0) == report.case_count
        and int(row["failure_count"] or 0) == report.failure_count
        and dialect.decode_json_list(row["missing_operations_json"])
        == list(report.missing_operations)
    )


def _insert_operation(
    conn: Any,
    report_id: str,
    observed_at: str,
    operation: SchemathesisOperationEvidence,
) -> None:
    operation_id = "sop_" + hashlib.sha256(
        f"{report_id}\x1f{operation.operation}".encode()
    ).hexdigest()[:32]
    dialect = dialect_for_backend(get_db_backend())
    failure_examples = [_failure_payload(item) for item in operation.failures]
    conn.execute(
        "INSERT INTO schemathesis_operation_evidence "
        "(id, report_id, operation_key, method, path, status, case_count, failure_count, "
        "response_statuses_json, failure_examples_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        (
            operation_id,
            report_id,
            operation.operation,
            operation.method,
            operation.path,
            operation.status,
            operation.case_count,
            operation.failure_count,
            dialect.json_param(list(operation.response_statuses)),
            dialect.json_param(failure_examples),
            observed_at,
        ),
    )
    row = conn.execute(
        "SELECT * FROM schemathesis_operation_evidence WHERE id = ?",
        (operation_id,),
    ).fetchone()
    if not row or not (
        str(row["report_id"] or "") == report_id
        and str(row["operation_key"] or "") == operation.operation
        and str(row["method"] or "") == operation.method
        and str(row["path"] or "") == operation.path
        and str(row["status"] or "") == operation.status
        and int(row["case_count"] or 0) == operation.case_count
        and int(row["failure_count"] or 0) == operation.failure_count
        and dialect.decode_json_list(row["response_statuses_json"])
        == list(operation.response_statuses)
        and dialect.decode_json_list(row["failure_examples_json"]) == failure_examples
    ):
        raise _error("operation_identity_conflict", "Schemathesis operation identity conflicts.")


def _failure_payload(failure: SchemathesisFailureExample) -> dict[str, Any]:
    return {
        "fingerprint": failure.fingerprint,
        "check_name": failure.check_name,
        "failure_type": failure.failure_type,
        "title": failure.title,
        "severity": failure.severity,
        "response_status": failure.response_status,
        "parameter_names": list(failure.parameter_names),
        "body_media_type": failure.body_media_type,
        "example_digest": failure.example_digest,
        "message_digest": failure.message_digest,
    }


def _error(code: str, message: str) -> SchemathesisEvidenceError:
    return SchemathesisEvidenceError(code, message)


__all__ = [
    "SchemathesisEvidenceError",
    "persist_reviewed_schemathesis_report",
]
