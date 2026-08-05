# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared SQL field fragments for Atlas finding readers."""

FINDING_DETAIL_SELECT_SQL = (
    "f.summary, f.impact, f.reproduction_steps, f.confidence, f.cve_ids_json, "
    "f.cwe_ids_json, f.cvss_vector, f.cvss_score, f.references_json, "
)

FINDING_SEARCH_COLUMNS = (
    "f.title",
    "f.raw_line",
    "f.tool_root",
    "f.summary",
    "f.impact",
    "f.reproduction_steps",
    "f.cvss_vector",
    "e.canonical_value",
)


def finding_detail_sql(run_scope_sql: str, finding_scope_sql: str) -> str:
    """Build the finding-detail query from trusted internal SQL fragments."""
    return "".join(
        (
            "SELECT f.id, f.session_id, f.team_id, f.entity_id, ",
            "e.type AS entity_type, e.canonical_value AS entity_value, ",
            "f.subject_key, f.signature_hash, f.origin, f.validation_method, f.severity, f.kind, f.tool_root, ",
            "f.first_run_id, f.last_run_id, ",
            "r.command AS run_command, r.run_kind AS run_kind, ",
            "f.first_seen_at, f.last_seen_at, f.occurrence_count, f.status, f.title, ",
            "f.raw_line, f.created, ",
            FINDING_DETAIL_SELECT_SQL,
            "f.suppressed, f.suppressed_reason, f.suppressed_at, ",
            "(SELECT fo.line_number FROM findings_occurrences fo WHERE fo.finding_id = f.id ",
            " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS line_number, ",
            "(SELECT fo.snippet FROM findings_occurrences fo WHERE fo.finding_id = f.id ",
            " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS snippet ",
            "FROM findings f ",
            "LEFT JOIN entities e ON e.id = f.entity_id ",
            "LEFT JOIN runs r ON r.id = f.last_run_id AND ",
            run_scope_sql,
            " WHERE ",
            finding_scope_sql,
            " AND f.id = ?",
        )
    )
