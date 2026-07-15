# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add Project and Atlas sort-order indexes."""

from .runner import Migration


_FINDING_STATUS_SORT_EXPR = (
    "CASE status "
    "WHEN 'new' THEN 0 "
    "WHEN 'needs_followup' THEN 1 "
    "WHEN 'important' THEN 2 "
    "WHEN 'reviewed' THEN 3 "
    "WHEN 'false_positive' THEN 4 "
    "ELSE 9 END"
)


_COMMON_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS idx_projects_personal_updated_sort
    ON projects (session_id, updated DESC, created DESC)
    WHERE team_id = ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_team_updated_sort
    ON projects (team_id, updated DESC, created DESC)
    WHERE team_id != ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_entities_session_last_seen_value
    ON entities (session_id, last_seen_at DESC, canonical_value ASC)
    WHERE team_id = ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_entities_team_last_seen_value
    ON entities (team_id, last_seen_at DESC, canonical_value ASC)
    WHERE team_id != ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_findings_team_first_run_seen
    ON findings (team_id, first_run_id, last_seen_at DESC)
    WHERE team_id != ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_findings_team_last_run_seen
    ON findings (team_id, last_run_id, last_seen_at DESC)
    WHERE team_id != ''
    """,
    f"""
    CREATE INDEX IF NOT EXISTS idx_findings_session_status_sort_seen
    ON findings (session_id, ({_FINDING_STATUS_SORT_EXPR}), last_seen_at DESC, created DESC)
    WHERE team_id = ''
    """,
    f"""
    CREATE INDEX IF NOT EXISTS idx_findings_team_status_sort_seen
    ON findings (team_id, ({_FINDING_STATUS_SORT_EXPR}), last_seen_at DESC, created DESC)
    WHERE team_id != ''
    """,
)


_SQLITE_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS idx_projects_personal_visible_name_sort
    ON projects (session_id, name COLLATE NOCASE ASC, updated DESC, created DESC)
    WHERE team_id = '' AND status != 'archived'
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_team_visible_name_sort
    ON projects (team_id, name COLLATE NOCASE ASC, updated DESC, created DESC)
    WHERE team_id != '' AND status != 'archived'
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_personal_archive_name_sort
    ON projects (
        session_id,
        (CASE WHEN status = 'archived' THEN 1 ELSE 0 END),
        name COLLATE NOCASE ASC,
        updated DESC,
        created DESC
    )
    WHERE team_id = ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_team_archive_name_sort
    ON projects (
        team_id,
        (CASE WHEN status = 'archived' THEN 1 ELSE 0 END),
        name COLLATE NOCASE ASC,
        updated DESC,
        created DESC
    )
    WHERE team_id != ''
    """,
)


_POSTGRES_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS idx_projects_personal_visible_name_sort
    ON projects (session_id, LOWER(name), updated DESC, created DESC)
    WHERE team_id = '' AND status != 'archived'
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_team_visible_name_sort
    ON projects (team_id, LOWER(name), updated DESC, created DESC)
    WHERE team_id != '' AND status != 'archived'
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_personal_archive_name_sort
    ON projects (
        session_id,
        (CASE WHEN status = 'archived' THEN 1 ELSE 0 END),
        LOWER(name),
        updated DESC,
        created DESC
    )
    WHERE team_id = ''
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_team_archive_name_sort
    ON projects (
        team_id,
        (CASE WHEN status = 'archived' THEN 1 ELSE 0 END),
        LOWER(name),
        updated DESC,
        created DESC
    )
    WHERE team_id != ''
    """,
)


MIGRATION = Migration(
    version="0041",
    name="project_atlas_sort_indexes",
    statements=(),
    sqlite_statements=(*_COMMON_STATEMENTS, *_SQLITE_STATEMENTS),
    postgres_statements=(*_COMMON_STATEMENTS, *_POSTGRES_STATEMENTS),
)
