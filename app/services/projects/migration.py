# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project workspace session migration helpers.
"""

from __future__ import annotations

from services.projects.preferences import migrate_active_project_preference
from services.projects.finding_remediation_merge_store import migrate_remediation_merge_members
from services.projects.slugs import allocate_slug


def _update_workspace_file_metadata(conn, from_session_id, to_session_id, table_name, migrated_file_paths):
    paths = sorted({str(path or "").strip() for path in migrated_file_paths if str(path or "").strip()})
    if not paths:
        return 0
    placeholders = ",".join("?" for _ in paths)
    result = conn.execute(
        f"UPDATE {table_name} SET session_id = ? "  # nosec
        "WHERE session_id = ? AND entity_type = 'workspace_file' "
        "AND (team_id IS NULL OR team_id = '') "
        f"AND entity_id IN ({placeholders})",
        [to_session_id, from_session_id, *paths],
    )
    return result.rowcount


def _count_workspace_file_metadata(conn, session_id, table_name):
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM {table_name} "  # nosec
        "WHERE session_id = ? AND entity_type = 'workspace_file' "
        "AND (team_id IS NULL OR team_id = '')",
        (session_id,),
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def migrate_project_workspace_session(
    conn,
    from_session_id,
    to_session_id,
    *,
    migrated_workspace_file_paths=(),
):
    """Move project workspace records between session IDs during token migration."""
    migrated_projects = 0
    project_rows = conn.execute(
        "SELECT id, name FROM projects WHERE session_id = ? ORDER BY created ASC",
        (from_session_id,),
    ).fetchall()
    for row in project_rows:
        slug = allocate_slug(conn, to_session_id, row["name"], project_id=row["id"])
        result = conn.execute(
            "UPDATE projects SET session_id = ?, slug = ? WHERE session_id = ? AND id = ?",
            (to_session_id, slug, from_session_id, row["id"]),
        )
        migrated_projects += result.rowcount
    artifact_result = conn.execute(
        "UPDATE run_file_artifacts SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    finding_result = conn.execute(
        "UPDATE findings SET session_id = ?, "
        "manual_created_by_session_id = CASE WHEN manual_created_by_session_id = ? THEN ? "
        "ELSE manual_created_by_session_id END, "
        "manual_updated_by_session_id = CASE WHEN manual_updated_by_session_id = ? THEN ? "
        "ELSE manual_updated_by_session_id END "
        "WHERE session_id = ?",
        (
            to_session_id,
            from_session_id,
            to_session_id,
            from_session_id,
            to_session_id,
            from_session_id,
        ),
    )
    disposition_rows = conn.execute(
        "SELECT affected_subject, identity_kind, identity_value, vulnerability_id, "
        "rule_identity, review_state, remediation, created_at, updated_at, "
        "remediation_updated_at "
        "FROM finding_remediation_dispositions "
        "WHERE session_id = ? AND team_id = ''",
        (from_session_id,),
    ).fetchall()
    conn.executemany(
        "INSERT INTO finding_remediation_dispositions "
        "(session_id, team_id, affected_subject, identity_kind, identity_value, "
        "vulnerability_id, rule_identity, review_state, remediation, created_at, "
        "updated_at, remediation_updated_at) "
        "VALUES (?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(session_id, team_id, affected_subject, identity_value) DO UPDATE SET "
        "identity_kind = CASE WHEN excluded.updated_at >= finding_remediation_dispositions.updated_at "
        "THEN excluded.identity_kind ELSE finding_remediation_dispositions.identity_kind END, "
        "vulnerability_id = CASE WHEN excluded.updated_at >= finding_remediation_dispositions.updated_at "
        "THEN excluded.vulnerability_id ELSE finding_remediation_dispositions.vulnerability_id END, "
        "rule_identity = CASE WHEN excluded.updated_at >= finding_remediation_dispositions.updated_at "
        "THEN excluded.rule_identity ELSE finding_remediation_dispositions.rule_identity END, "
        "review_state = CASE WHEN excluded.updated_at >= finding_remediation_dispositions.updated_at "
        "THEN excluded.review_state ELSE finding_remediation_dispositions.review_state END, "
        "remediation = CASE WHEN excluded.remediation_updated_at IS NOT NULL AND "
        "(finding_remediation_dispositions.remediation_updated_at IS NULL OR "
        "excluded.remediation_updated_at >= finding_remediation_dispositions.remediation_updated_at) "
        "THEN excluded.remediation ELSE finding_remediation_dispositions.remediation END, "
        "created_at = CASE WHEN excluded.created_at < finding_remediation_dispositions.created_at "
        "THEN excluded.created_at ELSE finding_remediation_dispositions.created_at END, "
        "updated_at = CASE WHEN excluded.updated_at > finding_remediation_dispositions.updated_at "
        "THEN excluded.updated_at ELSE finding_remediation_dispositions.updated_at END, "
        "remediation_updated_at = CASE WHEN excluded.remediation_updated_at IS NOT NULL AND "
        "(finding_remediation_dispositions.remediation_updated_at IS NULL OR "
        "excluded.remediation_updated_at > finding_remediation_dispositions.remediation_updated_at) "
        "THEN excluded.remediation_updated_at "
        "ELSE finding_remediation_dispositions.remediation_updated_at END",
        [
            (
                to_session_id,
                row["affected_subject"],
                row["identity_kind"],
                row["identity_value"],
                row["vulnerability_id"],
                row["rule_identity"],
                row["review_state"],
                row["remediation"],
                row["created_at"],
                row["updated_at"],
                row["remediation_updated_at"],
            )
            for row in disposition_rows
        ],
    )
    if disposition_rows:
        conn.execute(
            "DELETE FROM finding_remediation_dispositions "
            "WHERE session_id = ? AND team_id = ''",
            (from_session_id,),
        )
    migrated_remediation_merge_members = migrate_remediation_merge_members(
        conn,
        from_session_id,
        to_session_id,
    )
    entity_result = conn.execute(
        "UPDATE entities SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    intel_result = conn.execute(
        "UPDATE entity_intel_snapshots SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    source_workspace_file_labels = _count_workspace_file_metadata(conn, from_session_id, "entity_labels")
    source_workspace_file_notes = _count_workspace_file_metadata(conn, from_session_id, "entity_notes")
    label_result = conn.execute(
        "UPDATE entity_labels SET session_id = ? WHERE session_id = ? AND entity_type != 'workspace_file'",
        (to_session_id, from_session_id),
    )
    migrated_workspace_file_labels = _update_workspace_file_metadata(
        conn,
        from_session_id,
        to_session_id,
        "entity_labels",
        migrated_workspace_file_paths,
    )
    note_result = conn.execute(
        "UPDATE entity_notes SET session_id = ? WHERE session_id = ? AND entity_type != 'workspace_file'",
        (to_session_id, from_session_id),
    )
    migrated_workspace_file_notes = _update_workspace_file_metadata(
        conn,
        from_session_id,
        to_session_id,
        "entity_notes",
        migrated_workspace_file_paths,
    )
    package_result = conn.execute(
        "UPDATE evidence_packages SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    assessment_result = conn.execute(
        "UPDATE project_assessments SET session_id = ? "
        "WHERE session_id = ? AND team_id = ''",
        (to_session_id, from_session_id),
    )
    schemathesis_result = conn.execute(
        "UPDATE schemathesis_run_evidence SET session_id = ? "
        "WHERE session_id = ? AND team_id = ''",
        (to_session_id, from_session_id),
    )
    assessment_actor_result = conn.execute(
        "UPDATE project_assessments SET "
        "created_by_session_id = CASE WHEN created_by_session_id = ? THEN ? "
        "ELSE created_by_session_id END, "
        "updated_by_session_id = CASE WHEN updated_by_session_id = ? THEN ? "
        "ELSE updated_by_session_id END "
        "WHERE created_by_session_id = ? OR updated_by_session_id = ?",
        (
            from_session_id,
            to_session_id,
            from_session_id,
            to_session_id,
            from_session_id,
            from_session_id,
        ),
    )
    http_profile_result = conn.execute(
        "UPDATE project_http_profiles SET session_id = ?, "
        "created_by_session_id = CASE WHEN created_by_session_id = ? THEN ? "
        "ELSE created_by_session_id END, "
        "updated_by_session_id = CASE WHEN updated_by_session_id = ? THEN ? "
        "ELSE updated_by_session_id END "
        "WHERE session_id = ? AND team_id = ''",
        (
            to_session_id,
            from_session_id,
            to_session_id,
            from_session_id,
            to_session_id,
            from_session_id,
        ),
    )
    zap_job_result = conn.execute(
        "UPDATE zap_connector_jobs SET session_id = ? "
        "WHERE session_id = ? AND team_id = ''",
        (to_session_id, from_session_id),
    )
    oast_correlation_result = conn.execute(
        "UPDATE oast_correlations SET session_id = ? "
        "WHERE session_id = ? AND team_id = ''",
        (to_session_id, from_session_id),
    )
    check_actor_result = conn.execute(
        "UPDATE project_assessment_checks SET state_changed_by_session_id = ? "
        "WHERE state_changed_by_session_id = ?",
        (to_session_id, from_session_id),
    )
    finding_evidence_result = conn.execute(
        "UPDATE finding_evidence_links SET session_id = ?, "
        "created_by_session_id = CASE WHEN created_by_session_id = ? THEN ? "
        "ELSE created_by_session_id END "
        "WHERE session_id = ? AND team_id = ''",
        (to_session_id, from_session_id, to_session_id, from_session_id),
    )
    finding_triage_result = conn.execute(
        "UPDATE finding_triage_details SET session_id = ?, "
        "verification_updated_by_session_id = CASE "
        "WHEN verification_updated_by_session_id = ? THEN ? "
        "ELSE verification_updated_by_session_id END "
        "WHERE session_id = ? AND team_id = ''",
        (to_session_id, from_session_id, to_session_id, from_session_id),
    )
    migrated_active_project_preference = migrate_active_project_preference(
        conn,
        from_session_id,
        to_session_id,
    )
    return {
        "migrated_projects": migrated_projects,
        "migrated_run_file_artifacts": artifact_result.rowcount,
        "migrated_entities": entity_result.rowcount,
        "migrated_entity_intel_snapshots": intel_result.rowcount,
        "migrated_findings": finding_result.rowcount,
        "migrated_finding_remediation_dispositions": len(disposition_rows),
        "migrated_finding_remediation_guidance": sum(
            1 for row in disposition_rows if row["remediation_updated_at"] is not None
        ),
        "migrated_finding_remediation_merge_members": migrated_remediation_merge_members,
        "migrated_finding_targets": 0,
        "migrated_entity_labels": label_result.rowcount + migrated_workspace_file_labels,
        "migrated_entity_notes": note_result.rowcount + migrated_workspace_file_notes,
        "skipped_workspace_file_labels": source_workspace_file_labels - migrated_workspace_file_labels,
        "skipped_workspace_file_notes": source_workspace_file_notes - migrated_workspace_file_notes,
        "migrated_evidence_packages": package_result.rowcount,
        "migrated_project_assessments": assessment_result.rowcount,
        "migrated_schemathesis_run_evidence": schemathesis_result.rowcount,
        "migrated_project_assessment_actors": assessment_actor_result.rowcount,
        "migrated_project_http_profiles": http_profile_result.rowcount,
        "migrated_zap_connector_jobs": zap_job_result.rowcount,
        "migrated_oast_correlations": oast_correlation_result.rowcount,
        "migrated_project_assessment_check_actors": check_actor_result.rowcount,
        "migrated_finding_evidence_links": finding_evidence_result.rowcount,
        "migrated_finding_triage_details": finding_triage_result.rowcount,
        "migrated_active_project_preference": migrated_active_project_preference,
    }
