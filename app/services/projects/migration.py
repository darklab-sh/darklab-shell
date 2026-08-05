# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project workspace session migration helpers.
"""

from __future__ import annotations

from services.projects.preferences import migrate_active_project_preference
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
        "UPDATE findings SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
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
    check_actor_result = conn.execute(
        "UPDATE project_assessment_checks SET state_changed_by_session_id = ? "
        "WHERE state_changed_by_session_id = ?",
        (to_session_id, from_session_id),
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
        "migrated_finding_targets": 0,
        "migrated_entity_labels": label_result.rowcount + migrated_workspace_file_labels,
        "migrated_entity_notes": note_result.rowcount + migrated_workspace_file_notes,
        "skipped_workspace_file_labels": source_workspace_file_labels - migrated_workspace_file_labels,
        "skipped_workspace_file_notes": source_workspace_file_notes - migrated_workspace_file_notes,
        "migrated_evidence_packages": package_result.rowcount,
        "migrated_project_assessments": assessment_result.rowcount,
        "migrated_project_assessment_actors": assessment_actor_result.rowcount,
        "migrated_project_assessment_check_actors": check_actor_result.rowcount,
        "migrated_active_project_preference": migrated_active_project_preference,
    }
