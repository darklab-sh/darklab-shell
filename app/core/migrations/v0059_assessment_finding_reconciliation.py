# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persist explainable finding comparisons between assessment cycles."""

from .runner import Migration


_COMMON_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_assessment_check_comparisons_assessment_state "
    "ON project_assessment_check_comparisons "
    "(current_assessment_id, compatibility_state, current_check_id)",
    "CREATE INDEX IF NOT EXISTS idx_assessment_finding_deltas_assessment_state "
    "ON project_assessment_finding_deltas "
    "(current_assessment_id, delta_state, remediation_id)",
    "CREATE INDEX IF NOT EXISTS idx_assessment_finding_deltas_remediation "
    "ON project_assessment_finding_deltas (remediation_id, current_assessment_id)",
)

_SQLITE_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS project_assessment_check_comparisons (
        id TEXT PRIMARY KEY,
        current_assessment_id TEXT NOT NULL,
        current_check_id TEXT NOT NULL,
        previous_assessment_id TEXT,
        previous_check_id TEXT,
        compatibility_state TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        matched_rule_key TEXT NOT NULL DEFAULT '',
        matched_rule_version TEXT NOT NULL DEFAULT '',
        supports_negative_evidence INTEGER NOT NULL DEFAULT 0,
        computed_at TEXT NOT NULL,
        UNIQUE (current_check_id),
        CHECK (compatibility_state IN ('comparable', 'no_baseline', 'incomparable')),
        CHECK (supports_negative_evidence IN (0, 1)),
        FOREIGN KEY (current_assessment_id, current_check_id)
            REFERENCES project_assessment_checks(assessment_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_assessment_finding_deltas (
        id TEXT PRIMARY KEY,
        comparison_id TEXT NOT NULL,
        current_assessment_id TEXT NOT NULL,
        current_check_id TEXT NOT NULL,
        previous_assessment_id TEXT,
        previous_check_id TEXT,
        remediation_id TEXT NOT NULL,
        identity_kind TEXT NOT NULL,
        vulnerability_id TEXT NOT NULL DEFAULT '',
        rule_identity TEXT NOT NULL,
        affected_subject TEXT NOT NULL,
        delta_state TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        current_observations_json TEXT NOT NULL DEFAULT '[]',
        previous_observations_json TEXT NOT NULL DEFAULT '[]',
        current_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
        previous_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
        computed_at TEXT NOT NULL,
        UNIQUE (current_check_id, remediation_id),
        CHECK (identity_kind IN ('vulnerability', 'rule')),
        CHECK (delta_state IN (
            'new', 'persistent', 'not_observed', 'regressed', 'incomparable'
        )),
        FOREIGN KEY (comparison_id)
            REFERENCES project_assessment_check_comparisons(id) ON DELETE CASCADE,
        FOREIGN KEY (current_assessment_id, current_check_id)
            REFERENCES project_assessment_checks(assessment_id, id) ON DELETE CASCADE
    )
    """,
)

_POSTGRES_TABLES = tuple(
    statement.replace("computed_at TEXT NOT NULL", "computed_at TIMESTAMPTZ NOT NULL")
    .replace(
        "current_observations_json TEXT NOT NULL DEFAULT '[]'",
        "current_observations_json JSONB NOT NULL DEFAULT '[]'::jsonb",
    )
    .replace(
        "previous_observations_json TEXT NOT NULL DEFAULT '[]'",
        "previous_observations_json JSONB NOT NULL DEFAULT '[]'::jsonb",
    )
    .replace(
        "current_evidence_ids_json TEXT NOT NULL DEFAULT '[]'",
        "current_evidence_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb",
    )
    .replace(
        "previous_evidence_ids_json TEXT NOT NULL DEFAULT '[]'",
        "previous_evidence_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb",
    )
    for statement in _SQLITE_TABLES
)


MIGRATION = Migration(
    version="0059",
    name="assessment_finding_reconciliation",
    statements=(),
    sqlite_statements=(*_SQLITE_TABLES, *_COMMON_INDEXES),
    postgres_statements=(*_POSTGRES_TABLES, *_COMMON_INDEXES),
)
