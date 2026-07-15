# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalize personal-scope team ids for partial-index predicates."""

from .runner import Migration


_PERSONAL_SCOPE_TEAM_ID_TABLE_UPDATES = (
    ("runs", "UPDATE runs SET team_id = '' WHERE team_id IS NULL"),
    ("snapshots", "UPDATE snapshots SET team_id = '' WHERE team_id IS NULL"),
    ("user_workflows", "UPDATE user_workflows SET team_id = '' WHERE team_id IS NULL"),
    ("recent_values", "UPDATE recent_values SET team_id = '' WHERE team_id IS NULL"),
    ("notification_channels", "UPDATE notification_channels SET team_id = '' WHERE team_id IS NULL"),
    ("notification_events", "UPDATE notification_events SET team_id = '' WHERE team_id IS NULL"),
    ("audit_events", "UPDATE audit_events SET team_id = '' WHERE team_id IS NULL"),
    ("ai_run_assists", "UPDATE ai_run_assists SET team_id = '' WHERE team_id IS NULL"),
    ("schedules", "UPDATE schedules SET team_id = '' WHERE team_id IS NULL"),
    ("schedule_fires", "UPDATE schedule_fires SET team_id = '' WHERE team_id IS NULL"),
    ("watchers", "UPDATE watchers SET team_id = '' WHERE team_id IS NULL"),
    ("watcher_fires", "UPDATE watcher_fires SET team_id = '' WHERE team_id IS NULL"),
    ("projects", "UPDATE projects SET team_id = '' WHERE team_id IS NULL"),
    ("project_digest_settings", "UPDATE project_digest_settings SET team_id = '' WHERE team_id IS NULL"),
    ("entities", "UPDATE entities SET team_id = '' WHERE team_id IS NULL"),
    ("scan_target_observations", "UPDATE scan_target_observations SET team_id = '' WHERE team_id IS NULL"),
    ("findings", "UPDATE findings SET team_id = '' WHERE team_id IS NULL"),
    ("atlas_import_drafts", "UPDATE atlas_import_drafts SET team_id = '' WHERE team_id IS NULL"),
    ("atlas_import_batches", "UPDATE atlas_import_batches SET team_id = '' WHERE team_id IS NULL"),
    ("entity_labels", "UPDATE entity_labels SET team_id = '' WHERE team_id IS NULL"),
    ("entity_notes", "UPDATE entity_notes SET team_id = '' WHERE team_id IS NULL"),
    ("finding_triage_details", "UPDATE finding_triage_details SET team_id = '' WHERE team_id IS NULL"),
    ("project_reports", "UPDATE project_reports SET team_id = '' WHERE team_id IS NULL"),
)

_PERSONAL_SCOPE_TEAM_ID_TABLES = tuple(
    table_name
    for table_name, _ in _PERSONAL_SCOPE_TEAM_ID_TABLE_UPDATES
)


MIGRATION = Migration(
    version="0040",
    name="personal_scope_team_id_normalization",
    statements=tuple(
        statement
        for _, statement in _PERSONAL_SCOPE_TEAM_ID_TABLE_UPDATES
    ),
)
