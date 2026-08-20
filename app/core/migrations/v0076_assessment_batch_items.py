# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add server-owned previews and heterogeneous assessment-batch items."""

from .runner import Migration


_SQLITE_PREVIEWS = """
CREATE TABLE IF NOT EXISTS assessment_batch_previews (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    team_id TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    profile_key TEXT NOT NULL DEFAULT '',
    profile_version TEXT NOT NULL DEFAULT '',
    selection_json TEXT NOT NULL DEFAULT '{}',
    summary_json TEXT NOT NULL DEFAULT '{}',
    plan_digest TEXT NOT NULL,
    candidate_item_count INTEGER NOT NULL,
    selected_item_count INTEGER NOT NULL,
    mapping_count INTEGER NOT NULL,
    safe_item_count INTEGER NOT NULL DEFAULT 0,
    standard_item_count INTEGER NOT NULL DEFAULT 0,
    unavailable_check_count INTEGER NOT NULL DEFAULT 0,
    skipped_check_count INTEGER NOT NULL DEFAULT 0,
    estimated_min_seconds INTEGER NOT NULL DEFAULT 0,
    estimated_max_seconds INTEGER NOT NULL DEFAULT 0,
    max_parallel INTEGER NOT NULL,
    max_target_parallel INTEGER NOT NULL DEFAULT 1,
    max_owner_parallel INTEGER NOT NULL,
    max_instance_parallel INTEGER NOT NULL,
    started_execution_id TEXT NOT NULL DEFAULT '',
    claimed_at TEXT,
    expires_at TEXT NOT NULL,
    created TEXT NOT NULL,
    CHECK (candidate_item_count >= 0 AND candidate_item_count <= 512),
    CHECK (selected_item_count >= 0 AND selected_item_count <= candidate_item_count),
    CHECK (mapping_count >= 0 AND mapping_count <= 50000),
    CHECK (safe_item_count >= 0 AND standard_item_count >= 0),
    CHECK (safe_item_count + standard_item_count = candidate_item_count),
    CHECK (unavailable_check_count >= 0 AND unavailable_check_count <= 50000),
    CHECK (skipped_check_count >= 0 AND skipped_check_count <= 50000),
    CHECK (estimated_min_seconds >= 0),
    CHECK (estimated_max_seconds >= estimated_min_seconds),
    CHECK (max_parallel >= 1 AND max_parallel <= 8),
    CHECK (max_target_parallel = 1),
    CHECK (max_owner_parallel >= 1 AND max_owner_parallel <= 32),
    CHECK (max_instance_parallel >= 1 AND max_instance_parallel <= 64),
    CHECK (length(plan_digest) = 64),
    CHECK (length(started_execution_id) <= 64)
)
"""

_SQLITE_PREVIEW_ITEMS = """
CREATE TABLE IF NOT EXISTS assessment_batch_preview_items (
    preview_id TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    execution_key TEXT NOT NULL,
    selected INTEGER NOT NULL DEFAULT 1,
    policy_level TEXT NOT NULL,
    action_key TEXT NOT NULL,
    action_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_value TEXT NOT NULL,
    profile_identity_json TEXT NOT NULL DEFAULT '{}',
    bounds_json TEXT NOT NULL DEFAULT '{}',
    display_command TEXT NOT NULL,
    public_plan_digest TEXT NOT NULL,
    public_plan_json TEXT NOT NULL DEFAULT '{}',
    duration_bound_seconds INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL,
    PRIMARY KEY (preview_id, item_index),
    UNIQUE (preview_id, execution_key),
    CHECK (item_index >= 0 AND item_index < 512),
    CHECK (length(execution_key) = 64),
    CHECK (selected IN (0, 1)),
    CHECK (policy_level IN ('safe', 'standard')),
    CHECK (length(action_key) >= 1 AND length(action_key) <= 128),
    CHECK (length(action_id) <= 64),
    CHECK (length(target_entity_id) >= 1 AND length(target_entity_id) <= 64),
    CHECK (length(target_type) >= 1 AND length(target_type) <= 32),
    CHECK (length(target_value) >= 1 AND length(target_value) <= 4096),
    CHECK (length(display_command) >= 1 AND length(display_command) <= 8192),
    CHECK (length(public_plan_digest) = 64),
    CHECK (duration_bound_seconds >= 0),
    FOREIGN KEY (preview_id) REFERENCES assessment_batch_previews(id) ON DELETE CASCADE
)
"""

_SQLITE_PREVIEW_CHECKS = """
CREATE TABLE IF NOT EXISTS assessment_batch_preview_item_checks (
    preview_id TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    mapping_index INTEGER NOT NULL,
    assessment_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    check_key TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    coverage_key TEXT NOT NULL,
    frozen_check_digest TEXT NOT NULL,
    created TEXT NOT NULL,
    PRIMARY KEY (preview_id, item_index, mapping_index),
    UNIQUE (preview_id, check_id),
    CHECK (mapping_index >= 0 AND mapping_index < 256),
    CHECK (length(coverage_key) = 64),
    CHECK (length(frozen_check_digest) = 64),
    FOREIGN KEY (preview_id, item_index)
        REFERENCES assessment_batch_preview_items(preview_id, item_index) ON DELETE CASCADE
)
"""

_SQLITE_ITEMS = """
CREATE TABLE IF NOT EXISTS assessment_batch_items (
    batch_id TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    step_id TEXT NOT NULL,
    child_ordinal INTEGER NOT NULL,
    source_preview_id TEXT NOT NULL,
    execution_key TEXT NOT NULL,
    policy_level TEXT NOT NULL,
    action_key TEXT NOT NULL,
    action_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_value TEXT NOT NULL,
    profile_identity_json TEXT NOT NULL DEFAULT '{}',
    bounds_json TEXT NOT NULL DEFAULT '{}',
    display_command TEXT NOT NULL,
    public_plan_digest TEXT NOT NULL,
    public_plan_json TEXT NOT NULL DEFAULT '{}',
    duration_bound_seconds INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL,
    PRIMARY KEY (batch_id, item_index),
    UNIQUE (batch_id, execution_key),
    UNIQUE (batch_id, step_id, child_ordinal),
    CHECK (item_index >= 0 AND item_index < 512),
    CHECK (child_ordinal >= 0 AND child_ordinal < 32),
    CHECK (length(source_preview_id) >= 1 AND length(source_preview_id) <= 64),
    CHECK (length(execution_key) = 64),
    CHECK (policy_level IN ('safe', 'standard')),
    CHECK (length(action_key) >= 1 AND length(action_key) <= 128),
    CHECK (length(action_id) <= 64),
    CHECK (length(target_entity_id) >= 1 AND length(target_entity_id) <= 64),
    CHECK (length(target_type) >= 1 AND length(target_type) <= 32),
    CHECK (length(target_value) >= 1 AND length(target_value) <= 4096),
    CHECK (length(display_command) >= 1 AND length(display_command) <= 8192),
    CHECK (length(public_plan_digest) = 64),
    CHECK (duration_bound_seconds >= 0),
    FOREIGN KEY (batch_id) REFERENCES assessment_batches(execution_id) ON DELETE CASCADE
)
"""

_SQLITE_ITEM_CHECKS = """
CREATE TABLE IF NOT EXISTS assessment_batch_item_checks (
    batch_id TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    mapping_index INTEGER NOT NULL,
    assessment_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    check_key TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    coverage_key TEXT NOT NULL,
    frozen_check_digest TEXT NOT NULL,
    created TEXT NOT NULL,
    PRIMARY KEY (batch_id, item_index, mapping_index),
    UNIQUE (batch_id, check_id),
    CHECK (mapping_index >= 0 AND mapping_index < 256),
    CHECK (length(coverage_key) = 64),
    CHECK (length(frozen_check_digest) = 64),
    FOREIGN KEY (batch_id, item_index)
        REFERENCES assessment_batch_items(batch_id, item_index) ON DELETE CASCADE
)
"""


def _postgres(statement: str) -> str:
    return (
        statement.replace("selection_json TEXT", "selection_json JSONB")
        .replace("summary_json TEXT", "summary_json JSONB")
        .replace("profile_identity_json TEXT", "profile_identity_json JSONB")
        .replace("bounds_json TEXT", "bounds_json JSONB")
        .replace("public_plan_json TEXT", "public_plan_json JSONB")
        .replace("claimed_at TEXT", "claimed_at TIMESTAMPTZ")
        .replace("expires_at TEXT", "expires_at TIMESTAMPTZ")
        .replace("created TEXT", "created TIMESTAMPTZ")
        .replace("DEFAULT '{}'", "DEFAULT '{}'::jsonb")
    )


_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_assessment_batch_previews_personal_expiry "
    "ON assessment_batch_previews (session_id, expires_at, id) WHERE team_id = ''",
    "CREATE INDEX IF NOT EXISTS idx_assessment_batch_previews_team_expiry "
    "ON assessment_batch_previews (team_id, expires_at, id) WHERE team_id != ''",
    "CREATE INDEX IF NOT EXISTS idx_assessment_batch_previews_assessment_created "
    "ON assessment_batch_previews (assessment_id, created DESC, id)",
    "CREATE INDEX IF NOT EXISTS idx_assessment_batch_preview_items_page "
    "ON assessment_batch_preview_items (preview_id, item_index)",
    "CREATE INDEX IF NOT EXISTS idx_assessment_batch_preview_checks_check "
    "ON assessment_batch_preview_item_checks (preview_id, check_id)",
    "CREATE INDEX IF NOT EXISTS idx_assessment_batch_items_child "
    "ON assessment_batch_items (batch_id, step_id, child_ordinal)",
    "CREATE INDEX IF NOT EXISTS idx_assessment_batch_item_checks_check "
    "ON assessment_batch_item_checks (batch_id, check_id)",
)


_TABLES = (
    _SQLITE_PREVIEWS,
    _SQLITE_PREVIEW_ITEMS,
    _SQLITE_PREVIEW_CHECKS,
    _SQLITE_ITEMS,
    _SQLITE_ITEM_CHECKS,
)


MIGRATION = Migration(
    version="0076",
    name="assessment_batch_items",
    statements=(),
    sqlite_statements=(*_TABLES, *_INDEXES),
    postgres_statements=(*(_postgres(statement) for statement in _TABLES), *_INDEXES),
)
