# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Move personal data ownership from session-shaped keys to workspaces."""

from .runner import Migration


# Renaming in place is deliberate. In particular, rebuilding ``runs`` would
# replace SQLite rowids and desynchronize the external-content FTS5 index.
_PERSONAL_OWNER_COLUMNS = (
    ("ai_run_assists", "session_id"),
    ("assessment_batch_previews", "session_id"),
    ("atlas_import_batches", "session_id"),
    ("atlas_import_drafts", "session_id"),
    ("entities", "session_id"),
    ("entity_intel_snapshots", "session_id"),
    ("entity_labels", "session_id"),
    ("entity_notes", "session_id"),
    ("evidence_packages", "session_id"),
    ("finding_evidence_links", "session_id"),
    ("finding_remediation_dispositions", "session_id"),
    ("finding_remediation_merge_members", "session_id"),
    ("finding_triage_details", "session_id"),
    ("findings", "session_id"),
    ("nmap_service_observations", "session_id"),
    ("notification_channels", "session_token"),
    ("notification_events", "session_token"),
    ("oast_correlations", "session_id"),
    ("project_assessments", "session_id"),
    ("project_digest_settings", "session_id"),
    ("project_http_profiles", "session_id"),
    ("project_reports", "session_id"),
    ("projects", "session_id"),
    ("recent_values", "session_id"),
    ("risk_escalation_states", "owner_session_id"),
    ("risk_escalations", "owner_session_id"),
    ("run_file_artifacts", "session_id"),
    ("runs", "session_id"),
    ("scan_target_observations", "session_id"),
    ("schedules", "session_token"),
    ("schemathesis_run_evidence", "session_id"),
    ("session_preferences", "session_id"),
    ("session_variables", "session_id"),
    ("snapshots", "session_id"),
    ("starred_commands", "session_id"),
    ("user_workflows", "session_id"),
    ("watchers", "session_token"),
    ("workflow_executions", "session_id"),
    ("zap_connector_jobs", "session_id"),
)

_RENAME_OWNER_STATEMENTS = tuple(
    f"ALTER TABLE {table_name} RENAME COLUMN {column_name} TO personal_workspace_id"
    for table_name, column_name in _PERSONAL_OWNER_COLUMNS
)

_GENERIC_OWNER_RENAME_STATEMENTS = (
    # A secret vault may be owned by either a personal workspace or a team.
    # Its old flattened token-shaped key therefore becomes a neutral owner id.
    "ALTER TABLE secrets RENAME COLUMN session_token TO owner_id",
)

# Attribution is not authorization. These nullable fields are filled for work
# performed by a principal; existing anonymous and pre-cutover rows retain
# their legacy attribution until the clean-removal migration.
_ATTRIBUTION_STATEMENTS = (
    "ALTER TABLE atlas_import_batches ADD COLUMN actor_principal_id TEXT",
    "ALTER TABLE atlas_import_batches ADD COLUMN actor_credential_id TEXT",
    "ALTER TABLE atlas_import_drafts ADD COLUMN actor_principal_id TEXT",
    "ALTER TABLE atlas_import_drafts ADD COLUMN actor_credential_id TEXT",
    "ALTER TABLE finding_evidence_links ADD COLUMN created_by_principal_id TEXT",
    "ALTER TABLE finding_evidence_links ADD COLUMN created_by_credential_id TEXT",
    "ALTER TABLE finding_remediation_merge_members ADD COLUMN created_by_principal_id TEXT",
    "ALTER TABLE finding_remediation_merge_members ADD COLUMN created_by_credential_id TEXT",
    "ALTER TABLE finding_triage_details ADD COLUMN verification_updated_by_principal_id TEXT",
    "ALTER TABLE finding_triage_details ADD COLUMN verification_updated_by_credential_id TEXT",
    "ALTER TABLE findings ADD COLUMN manual_created_by_principal_id TEXT",
    "ALTER TABLE findings ADD COLUMN manual_created_by_credential_id TEXT",
    "ALTER TABLE findings ADD COLUMN manual_updated_by_principal_id TEXT",
    "ALTER TABLE findings ADD COLUMN manual_updated_by_credential_id TEXT",
    "ALTER TABLE project_assessment_checks ADD COLUMN state_changed_by_principal_id TEXT",
    "ALTER TABLE project_assessment_checks ADD COLUMN state_changed_by_credential_id TEXT",
    "ALTER TABLE project_assessments ADD COLUMN created_by_principal_id TEXT",
    "ALTER TABLE project_assessments ADD COLUMN created_by_credential_id TEXT",
    "ALTER TABLE project_assessments ADD COLUMN updated_by_principal_id TEXT",
    "ALTER TABLE project_assessments ADD COLUMN updated_by_credential_id TEXT",
    "ALTER TABLE project_auto_promote_rules ADD COLUMN created_by_principal_id TEXT",
    "ALTER TABLE project_auto_promote_rules ADD COLUMN created_by_credential_id TEXT",
    "ALTER TABLE project_http_profiles ADD COLUMN created_by_principal_id TEXT",
    "ALTER TABLE project_http_profiles ADD COLUMN created_by_credential_id TEXT",
    "ALTER TABLE project_http_profiles ADD COLUMN updated_by_principal_id TEXT",
    "ALTER TABLE project_http_profiles ADD COLUMN updated_by_credential_id TEXT",
    "ALTER TABLE teams ADD COLUMN created_by_principal_id TEXT",
    "ALTER TABLE teams ADD COLUMN created_by_credential_id TEXT",
    "ALTER TABLE team_members ADD COLUMN principal_id TEXT",
    "ALTER TABLE team_members ADD COLUMN joined_by_credential_id TEXT",
    "ALTER TABLE audit_events ADD COLUMN owner_workspace_hash TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE audit_events ADD COLUMN actor_principal_id TEXT",
    "ALTER TABLE audit_events ADD COLUMN actor_principal_hash TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE audit_events ADD COLUMN actor_credential_id TEXT",
    "ALTER TABLE audit_events ADD COLUMN actor_credential_label TEXT NOT NULL DEFAULT ''",
    "UPDATE audit_events SET owner_workspace_hash = owner_session_hash WHERE owner_workspace_hash = ''",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_team_members_principal "
    "ON team_members (team_id, principal_id) WHERE principal_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_audit_events_owner_workspace_created "
    "ON audit_events (owner_workspace_hash, created DESC) WHERE owner_workspace_hash != ''",
    "CREATE INDEX IF NOT EXISTS idx_audit_events_actor_principal_created "
    "ON audit_events (actor_principal_hash, created DESC) WHERE actor_principal_hash != ''",
)


MIGRATION = Migration(
    version="0080",
    name="principal_ownership_cutover",
    statements=(
        *_RENAME_OWNER_STATEMENTS,
        *_GENERIC_OWNER_RENAME_STATEMENTS,
        *_ATTRIBUTION_STATEMENTS,
    ),
)
