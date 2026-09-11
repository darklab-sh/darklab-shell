# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Transactional attachment of personal data to a durable workspace."""

from __future__ import annotations

import hashlib
from typing import Any

from core.database_backend import DatabaseBackend


# These are fixed schema identifiers, never request values. Every update is an
# in-place owner-key update; ``runs`` must never be rebuilt because its rowid is
# the content key for ``runs_fts``.
PERSONAL_OWNER_TABLES = (
    "ai_run_assists",
    "assessment_batch_previews",
    "atlas_import_batches",
    "atlas_import_drafts",
    "entities",
    "entity_intel_snapshots",
    "entity_labels",
    "entity_notes",
    "evidence_packages",
    "finding_evidence_links",
    "finding_remediation_dispositions",
    "finding_remediation_merge_members",
    "finding_triage_details",
    "findings",
    "nmap_service_observations",
    "notification_channels",
    "notification_events",
    "oast_correlations",
    "project_assessments",
    "project_digest_settings",
    "project_http_profiles",
    "project_reports",
    "projects",
    "recent_values",
    "risk_escalation_states",
    "risk_escalations",
    "run_file_artifacts",
    "runs",
    "scan_target_observations",
    "schedules",
    "schemathesis_run_evidence",
    "session_preferences",
    "session_variables",
    "snapshots",
    "starred_commands",
    "user_workflows",
    "watchers",
    "workflow_executions",
    "zap_connector_jobs",
)

_ATTRIBUTION_COLUMNS = (
    ("atlas_import_batches", "actor_session_id", "actor_principal_id", "actor_credential_id"),
    ("atlas_import_drafts", "actor_session_id", "actor_principal_id", "actor_credential_id"),
    ("finding_evidence_links", "created_by_session_id", "created_by_principal_id", "created_by_credential_id"),
    (
        "finding_remediation_merge_members",
        "created_by_session_id",
        "created_by_principal_id",
        "created_by_credential_id",
    ),
    (
        "finding_triage_details",
        "verification_updated_by_session_id",
        "verification_updated_by_principal_id",
        "verification_updated_by_credential_id",
    ),
    ("findings", "manual_created_by_session_id", "manual_created_by_principal_id", "manual_created_by_credential_id"),
    ("findings", "manual_updated_by_session_id", "manual_updated_by_principal_id", "manual_updated_by_credential_id"),
    (
        "project_assessment_checks",
        "state_changed_by_session_id",
        "state_changed_by_principal_id",
        "state_changed_by_credential_id",
    ),
    ("project_assessments", "created_by_session_id", "created_by_principal_id", "created_by_credential_id"),
    ("project_assessments", "updated_by_session_id", "updated_by_principal_id", "updated_by_credential_id"),
    (
        "project_auto_promote_rules",
        "created_by_session_id",
        "created_by_principal_id",
        "created_by_credential_id",
    ),
    ("project_http_profiles", "created_by_session_id", "created_by_principal_id", "created_by_credential_id"),
    ("project_http_profiles", "updated_by_session_id", "updated_by_principal_id", "updated_by_credential_id"),
)

_BACKGROUND_PRINCIPAL_TABLES = (
    "schedules",
    "watchers",
    "user_workflows",
    "notification_channels",
    "project_digest_settings",
    "evidence_packages",
    "project_reports",
    "workflow_executions",
    "notification_events",
    "ai_run_assists",
    "zap_connector_jobs",
    "oast_correlations",
)

_BACKGROUND_CHILD_TABLES = (
    ("schedule_fires", "schedule_id", "schedules"),
    ("watcher_fires", "watcher_id", "watchers"),
)


def _cutover_schema_is_active(conn: Any, backend: DatabaseBackend) -> bool:
    if backend == DatabaseBackend.SQLITE:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if table is None:
            return False
    else:
        table = conn.execute("SELECT to_regclass('schema_migrations') AS table_name").fetchone()
        if table is None or not table["table_name"]:
            return False
    return conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        ("0080",),
    ).fetchone() is not None


def _background_authorization_schema_is_active(conn: Any) -> bool:
    return conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        ("0081",),
    ).fetchone() is not None


def attach_personal_ownership(
    conn: Any,
    *,
    backend: DatabaseBackend,
    source_owner_id: str,
    workspace_id: str,
    principal_id: str,
    credential_id: str,
) -> dict[str, int]:
    """Attach every anonymous-owned row without changing filesystem state."""
    if not _cutover_schema_is_active(conn, backend):
        return {}

    counts: dict[str, int] = {}
    for table_name in PERSONAL_OWNER_TABLES:
        cursor = conn.execute(
            f"UPDATE {table_name} SET personal_workspace_id = ? WHERE personal_workspace_id = ?",  # nosec
            (workspace_id, source_owner_id),
        )
        counts[table_name] = max(0, int(cursor.rowcount or 0))

    cursor = conn.execute(
        "UPDATE secrets SET owner_id = ? WHERE owner_id = ?",
        (workspace_id, source_owner_id),
    )
    counts["secrets"] = max(0, int(cursor.rowcount or 0))

    if _background_authorization_schema_is_active(conn):
        # Anonymous work predates credentials, so attach it to the new
        # principal without claiming that the upgrade credential created or
        # last changed it. Those credential-attribution columns remain NULL.
        for table_name in _BACKGROUND_PRINCIPAL_TABLES:
            conn.execute(
                f"UPDATE {table_name} SET principal_id = ? "  # nosec
                "WHERE personal_workspace_id = ? AND principal_id IS NULL",
                (principal_id, workspace_id),
            )
        conn.execute(
            "UPDATE secrets SET principal_id = ? "
            "WHERE owner_id = ? AND principal_id IS NULL",
            (principal_id, workspace_id),
        )
        for child_table, parent_key, parent_table in _BACKGROUND_CHILD_TABLES:
            conn.execute(
                f"UPDATE {child_table} SET principal_id = ("  # nosec
                f"SELECT {parent_table}.principal_id FROM {parent_table} "
                f"WHERE {parent_table}.id = {child_table}.{parent_key}"
                ") WHERE principal_id IS NULL AND EXISTS ("
                f"SELECT 1 FROM {parent_table} WHERE {parent_table}.id = {child_table}.{parent_key} "
                f"AND {parent_table}.personal_workspace_id = ?)",
                (workspace_id,),
            )

    for table_name, legacy_column, principal_column, credential_column in _ATTRIBUTION_COLUMNS:
        conn.execute(
            f"UPDATE {table_name} SET {principal_column} = ?, {credential_column} = ? "  # nosec
            f"WHERE {legacy_column} = ?",
            (principal_id, credential_id, source_owner_id),
        )

    source_owner_hash = hashlib.sha256(source_owner_id.encode("utf-8")).hexdigest()
    workspace_hash = hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()
    conn.execute(
        "UPDATE audit_events SET owner_workspace_hash = ?, actor_principal_id = ?, "
        "actor_principal_hash = ?, actor_credential_id = ? "
        "WHERE team_id = '' AND owner_session_hash = ?",
        (
            workspace_hash,
            principal_id,
            hashlib.sha256(principal_id.encode("utf-8")).hexdigest(),
            credential_id,
            source_owner_hash,
        ),
    )
    return counts


__all__ = ["PERSONAL_OWNER_TABLES", "attach_personal_ownership"]
