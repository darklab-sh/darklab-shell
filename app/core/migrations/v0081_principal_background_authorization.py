# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add principal authorization and safe credential attribution to durable work."""

from .runner import Migration


# Credential ids here are attribution only. They deliberately have no foreign
# key so historical records survive credential deletion and key retirement.
_DURABLE_DEFINITION_TABLES = (
    "schedules",
    "watchers",
    "user_workflows",
    "notification_channels",
    "project_digest_settings",
    "evidence_packages",
    "project_reports",
)

_BACKGROUND_RECORD_TABLES = (
    "workflow_executions",
    "notification_events",
    "ai_run_assists",
    "zap_connector_jobs",
    "oast_correlations",
)

_CHILD_RECORD_TABLES = ("schedule_fires", "watcher_fires")

_DEFINITION_COLUMNS = tuple(
    statement
    for table in _DURABLE_DEFINITION_TABLES
    for statement in (
        f"ALTER TABLE {table} ADD COLUMN principal_id TEXT",
        f"ALTER TABLE {table} ADD COLUMN created_by_credential_id TEXT",
        f"ALTER TABLE {table} ADD COLUMN last_changed_by_credential_id TEXT",
    )
)

_BACKGROUND_COLUMNS = tuple(
    statement
    for table in _BACKGROUND_RECORD_TABLES
    for statement in (
        f"ALTER TABLE {table} ADD COLUMN principal_id TEXT",
        f"ALTER TABLE {table} ADD COLUMN originating_credential_id TEXT",
    )
)

_CHILD_COLUMNS = tuple(
    statement
    for table in _CHILD_RECORD_TABLES
    for statement in (
        f"ALTER TABLE {table} ADD COLUMN principal_id TEXT",
        f"ALTER TABLE {table} ADD COLUMN originating_credential_id TEXT",
    )
)

_PROVIDER_SECRET_COLUMNS = (
    "ALTER TABLE secrets ADD COLUMN principal_id TEXT",
    "ALTER TABLE secrets ADD COLUMN created_by_credential_id TEXT",
    "ALTER TABLE secrets ADD COLUMN last_changed_by_credential_id TEXT",
)

_PRINCIPAL_BACKFILLS = tuple(
    "UPDATE " + table + " SET principal_id = ("  # nosec B608 -- fixed internal table names
    "SELECT personal_workspaces.principal_id FROM personal_workspaces "
    f"WHERE personal_workspaces.id = {table}.personal_workspace_id"
    ") WHERE principal_id IS NULL"
    for table in (*_DURABLE_DEFINITION_TABLES, *_BACKGROUND_RECORD_TABLES)
)

_CHILD_PRINCIPAL_BACKFILLS = (
    "UPDATE schedule_fires SET principal_id = (SELECT schedules.principal_id FROM schedules "
    "WHERE schedules.id = schedule_fires.schedule_id) WHERE principal_id IS NULL",
    "UPDATE watcher_fires SET principal_id = (SELECT watchers.principal_id FROM watchers "
    "WHERE watchers.id = watcher_fires.watcher_id) WHERE principal_id IS NULL",
)

_PROVIDER_SECRET_BACKFILL = (
    "UPDATE secrets SET principal_id = ("
    "SELECT personal_workspaces.principal_id FROM personal_workspaces "
    "WHERE personal_workspaces.id = secrets.owner_id"
    ") WHERE principal_id IS NULL",
)

_INDEXES = tuple(
    f"CREATE INDEX IF NOT EXISTS idx_{table}_principal ON {table} (principal_id)"
    for table in (*_DURABLE_DEFINITION_TABLES, *_BACKGROUND_RECORD_TABLES, *_CHILD_RECORD_TABLES)
)

_PROVIDER_SECRET_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_secrets_principal ON secrets (principal_id)",
    "CREATE INDEX IF NOT EXISTS idx_secrets_created_credential "
    "ON secrets (created_by_credential_id)",
    "CREATE INDEX IF NOT EXISTS idx_secrets_changed_credential "
    "ON secrets (last_changed_by_credential_id)",
)


MIGRATION = Migration(
    version="0081",
    name="principal_background_authorization",
    statements=(
        *_DEFINITION_COLUMNS,
        *_BACKGROUND_COLUMNS,
        *_CHILD_COLUMNS,
        *_PROVIDER_SECRET_COLUMNS,
        *_PRINCIPAL_BACKFILLS,
        *_CHILD_PRINCIPAL_BACKFILLS,
        *_PROVIDER_SECRET_BACKFILL,
        *_INDEXES,
        *_PROVIDER_SECRET_INDEXES,
    ),
)
