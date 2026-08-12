# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Expose only complete reviewed API evidence to assessment matching."""

from __future__ import annotations

from typing import Any, Callable

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend


def schemathesis_run_evidence_facts(
    conn: Any,
    run_id: str,
) -> tuple[tuple[str, str] | None, frozenset[str]]:
    """Return an exact target only when the saved report proves useful coverage."""
    row = conn.execute(
        "SELECT report.id, report.expected_operation_count, "
        "report.observed_operation_count, report.failure_count, "
        "report.missing_operations_json, check_row.target_type, check_row.target_value "
        "FROM schemathesis_run_evidence report "
        "JOIN project_assessment_checks check_row ON check_row.id = report.check_id "
        "AND check_row.assessment_id = report.assessment_id WHERE report.run_id = ?",
        (run_id,),
    ).fetchone()
    if not row:
        return None, frozenset()
    operation_rows = conn.execute(
        "SELECT status FROM schemathesis_operation_evidence "
        "WHERE report_id = ? ORDER BY operation_key ASC",
        (str(row["id"]),),
    ).fetchall()
    expected = int(row["expected_operation_count"] or 0)
    observed = int(row["observed_operation_count"] or 0)
    failures = int(row["failure_count"] or 0)
    missing = dialect_for_backend(get_db_backend()).decode_json_list(
        row["missing_operations_json"]
    )
    clean_complete = (
        expected > 0
        and expected == observed == len(operation_rows)
        and not missing
        and all(str(item["status"] or "") == "success" for item in operation_rows)
    )
    identity = None
    if failures > 0 or clean_complete:
        identity = (str(row["target_type"] or ""), str(row["target_value"] or ""))
    return identity, frozenset({"api_operations"})


def merge_schemathesis_run_evidence_facts(
    conn: Any,
    run_id: str,
    identities: set[Any],
    structured_kinds: set[str],
    canonicalize: Callable[[object, object], Any],
) -> None:
    """Merge saved API facts without coupling the parser to evidence types."""
    identity, kinds = schemathesis_run_evidence_facts(conn, run_id)
    structured_kinds.update(kinds)
    if identity is not None and (canonical := canonicalize(identity[1], identity[0])) is not None:
        identities.add(canonical)


__all__ = ["merge_schemathesis_run_evidence_facts", "schemathesis_run_evidence_facts"]
