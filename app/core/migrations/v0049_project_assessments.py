# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add durable Project assessment cycles, checks, and evidence links."""

from .runner import Migration


_COMMON_INDEXES = (
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_project_assessments_active_project
    ON project_assessments (project_id) WHERE status = 'active'
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_assessments_project_updated
    ON project_assessments (project_id, updated_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_assessments_personal_status
    ON project_assessments (session_id, status, updated_at DESC, id DESC)
    WHERE team_id = ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_assessments_team_status
    ON project_assessments (team_id, status, updated_at DESC, id DESC)
    WHERE team_id != ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_assessment_checks_assessment_state
    ON project_assessment_checks (assessment_id, state, updated_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_assessment_checks_assessment_category
    ON project_assessment_checks (assessment_id, category, state, id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_assessment_checks_target
    ON project_assessment_checks (assessment_id, target_entity_id, target_type, state)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_assessment_evidence_check_observed
    ON project_assessment_evidence (check_id, observed_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_assessment_evidence_assessment_type
    ON project_assessment_evidence (assessment_id, evidence_type, observed_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_project_assessment_evidence_source
    ON project_assessment_evidence (evidence_type, evidence_id, assessment_id)
    """,
)


_SQLITE_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS project_assessments (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        team_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        profile_key TEXT NOT NULL,
        profile_version TEXT NOT NULL,
        profile_snapshot TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'active',
        started_at TEXT NOT NULL,
        completed_at TEXT,
        archived_at TEXT,
        created_by_session_id TEXT NOT NULL DEFAULT '',
        created_by_member_id TEXT NOT NULL DEFAULT '',
        updated_by_session_id TEXT NOT NULL DEFAULT '',
        updated_by_member_id TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (status IN ('active', 'completed', 'archived')),
        CHECK ("""
        "(status = 'active' AND completed_at IS NULL AND archived_at IS NULL) OR "
        "(status = 'completed' AND completed_at IS NOT NULL AND archived_at IS NULL) OR "
        "(status = 'archived' AND archived_at IS NOT NULL)"
        """),
        CHECK (session_id != '' OR team_id != ''),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_assessment_checks (
        id TEXT PRIMARY KEY,
        assessment_id TEXT NOT NULL,
        category TEXT NOT NULL,
        check_key TEXT NOT NULL,
        target_entity_id TEXT NOT NULL DEFAULT '',
        target_type TEXT NOT NULL,
        target_value TEXT NOT NULL,
        target_value_hash TEXT NOT NULL,
        applicability TEXT NOT NULL DEFAULT 'applicable',
        policy_level TEXT NOT NULL DEFAULT 'safe',
        state TEXT NOT NULL DEFAULT 'not_started',
        state_source TEXT NOT NULL DEFAULT 'derived',
        state_reason TEXT NOT NULL DEFAULT '',
        recommended_action_key TEXT NOT NULL DEFAULT '',
        first_evidence_at TEXT,
        last_evidence_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (assessment_id, id),
        UNIQUE (assessment_id, check_key, target_type, target_value_hash),
        CHECK (applicability IN ('applicable', 'not_applicable', 'unknown')),
        CHECK (policy_level IN ('safe', 'standard', 'intrusive', 'destructive')),
        CHECK (state IN ("""
        "'not_started', 'running', 'covered', 'needs_review', "
        "'failed', 'blocked', 'skipped', 'not_applicable'"
        """)),
        CHECK (state_source IN ('derived', 'manual')),
        FOREIGN KEY (assessment_id) REFERENCES project_assessments(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_assessment_evidence (
        id TEXT PRIMARY KEY,
        assessment_id TEXT NOT NULL,
        check_id TEXT NOT NULL,
        evidence_type TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        source_state TEXT NOT NULL DEFAULT 'available',
        observed_at TEXT NOT NULL,
        unavailable_at TEXT,
        unavailable_reason TEXT NOT NULL DEFAULT '',
        match_rule_key TEXT NOT NULL,
        match_rule_version TEXT NOT NULL,
        linked_by TEXT NOT NULL DEFAULT 'derived',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (check_id, evidence_type, evidence_id),
        CHECK (evidence_type IN ("""
        "'run', 'workflow_execution', 'finding', 'atlas_entity', "
        "'run_artifact', 'workspace_artifact', 'screenshot'"
        """)),
        CHECK (source_state IN ('available', 'unavailable')),
        CHECK ("""
        "(source_state = 'available' AND unavailable_at IS NULL AND unavailable_reason = '') OR "
        "(source_state = 'unavailable' AND unavailable_at IS NOT NULL AND unavailable_reason != '')"
        """),
        CHECK (linked_by IN ('derived', 'manual', 'imported')),
        FOREIGN KEY (assessment_id, check_id) REFERENCES project_assessment_checks(assessment_id, id) ON DELETE CASCADE
    )
    """,
)


_POSTGRES_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS project_assessments (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        team_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL,
        title TEXT NOT NULL,
        profile_key TEXT NOT NULL,
        profile_version TEXT NOT NULL,
        profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
        status TEXT NOT NULL DEFAULT 'active',
        started_at TIMESTAMPTZ NOT NULL,
        completed_at TIMESTAMPTZ,
        archived_at TIMESTAMPTZ,
        created_by_session_id TEXT NOT NULL DEFAULT '',
        created_by_member_id TEXT NOT NULL DEFAULT '',
        updated_by_session_id TEXT NOT NULL DEFAULT '',
        updated_by_member_id TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        CHECK (status IN ('active', 'completed', 'archived')),
        CHECK ("""
        "(status = 'active' AND completed_at IS NULL AND archived_at IS NULL) OR "
        "(status = 'completed' AND completed_at IS NOT NULL AND archived_at IS NULL) OR "
        "(status = 'archived' AND archived_at IS NOT NULL)"
        """),
        CHECK (session_id != '' OR team_id != ''),
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_assessment_checks (
        id TEXT PRIMARY KEY,
        assessment_id TEXT NOT NULL,
        category TEXT NOT NULL,
        check_key TEXT NOT NULL,
        target_entity_id TEXT NOT NULL DEFAULT '',
        target_type TEXT NOT NULL,
        target_value TEXT NOT NULL,
        target_value_hash TEXT NOT NULL,
        applicability TEXT NOT NULL DEFAULT 'applicable',
        policy_level TEXT NOT NULL DEFAULT 'safe',
        state TEXT NOT NULL DEFAULT 'not_started',
        state_source TEXT NOT NULL DEFAULT 'derived',
        state_reason TEXT NOT NULL DEFAULT '',
        recommended_action_key TEXT NOT NULL DEFAULT '',
        first_evidence_at TIMESTAMPTZ,
        last_evidence_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        UNIQUE (assessment_id, id),
        UNIQUE (assessment_id, check_key, target_type, target_value_hash),
        CHECK (applicability IN ('applicable', 'not_applicable', 'unknown')),
        CHECK (policy_level IN ('safe', 'standard', 'intrusive', 'destructive')),
        CHECK (state IN ("""
        "'not_started', 'running', 'covered', 'needs_review', "
        "'failed', 'blocked', 'skipped', 'not_applicable'"
        """)),
        CHECK (state_source IN ('derived', 'manual')),
        FOREIGN KEY (assessment_id) REFERENCES project_assessments(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_assessment_evidence (
        id TEXT PRIMARY KEY,
        assessment_id TEXT NOT NULL,
        check_id TEXT NOT NULL,
        evidence_type TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        source_state TEXT NOT NULL DEFAULT 'available',
        observed_at TIMESTAMPTZ NOT NULL,
        unavailable_at TIMESTAMPTZ,
        unavailable_reason TEXT NOT NULL DEFAULT '',
        match_rule_key TEXT NOT NULL,
        match_rule_version TEXT NOT NULL,
        linked_by TEXT NOT NULL DEFAULT 'derived',
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        UNIQUE (check_id, evidence_type, evidence_id),
        CHECK (evidence_type IN ("""
        "'run', 'workflow_execution', 'finding', 'atlas_entity', "
        "'run_artifact', 'workspace_artifact', 'screenshot'"
        """)),
        CHECK (source_state IN ('available', 'unavailable')),
        CHECK ("""
        "(source_state = 'available' AND unavailable_at IS NULL AND unavailable_reason = '') OR "
        "(source_state = 'unavailable' AND unavailable_at IS NOT NULL AND unavailable_reason != '')"
        """),
        CHECK (linked_by IN ('derived', 'manual', 'imported')),
        FOREIGN KEY (assessment_id, check_id) REFERENCES project_assessment_checks(assessment_id, id) ON DELETE CASCADE
    )
    """,
)


MIGRATION = Migration(
    version="0049",
    name="project_assessments",
    statements=(),
    sqlite_statements=(*_SQLITE_TABLES, *_COMMON_INDEXES),
    postgres_statements=(*_POSTGRES_TABLES, *_COMMON_INDEXES),
)
