"""Postgres schema migrations.

SQLite keeps its current bootstrap path in ``core.database``. These migrations
only run when ``database_backend`` is configured as ``postgres``.
"""

from . import (
    v0001_postgres_baseline,
    v0002_postgres_run_search,
    v0003_postgres_atlas_search,
    v0004_postgres_atlas_detail_indexes,
    v0005_postgres_project_findings_indexes,
    v0006_postgres_atlas_suppression,
    v0007_postgres_atlas_metadata_search,
    v0008_postgres_session_token_last_seen,
    v0009_notification_channels,
    v0010_schedules,
    v0011_watchers,
    v0012_run_output_summary,
    v0013_ai_run_assists,
    v0014_ai_assist_progress,
    v0015_teams,
    v0016_team_scope_runs,
    v0017_team_scope_projects,
    v0018_team_scope_automation,
    v0019_team_scope_notifications,
    v0020_team_scope_ai_assists,
    v0021_team_scope_workflows,
    v0022_project_slug_scope,
    v0023_team_code_hash_uniqueness,
    v0024_team_scope_atlas,
    v0025_team_scope_workspace_metadata,
    v0026_project_auto_promote_rules,
)
from .runner import Migration

MIGRATIONS: tuple[Migration, ...] = (
    v0001_postgres_baseline.MIGRATION,
    v0002_postgres_run_search.MIGRATION,
    v0003_postgres_atlas_search.MIGRATION,
    v0004_postgres_atlas_detail_indexes.MIGRATION,
    v0005_postgres_project_findings_indexes.MIGRATION,
    v0006_postgres_atlas_suppression.MIGRATION,
    v0007_postgres_atlas_metadata_search.MIGRATION,
    v0008_postgres_session_token_last_seen.MIGRATION,
    v0009_notification_channels.MIGRATION,
    v0010_schedules.MIGRATION,
    v0011_watchers.MIGRATION,
    v0012_run_output_summary.MIGRATION,
    v0013_ai_run_assists.MIGRATION,
    v0014_ai_assist_progress.MIGRATION,
    v0015_teams.MIGRATION,
    v0016_team_scope_runs.MIGRATION,
    v0017_team_scope_projects.MIGRATION,
    v0018_team_scope_automation.MIGRATION,
    v0019_team_scope_notifications.MIGRATION,
    v0020_team_scope_ai_assists.MIGRATION,
    v0021_team_scope_workflows.MIGRATION,
    v0022_project_slug_scope.MIGRATION,
    v0023_team_code_hash_uniqueness.MIGRATION,
    v0024_team_scope_atlas.MIGRATION,
    v0025_team_scope_workspace_metadata.MIGRATION,
    v0026_project_auto_promote_rules.MIGRATION,
)
