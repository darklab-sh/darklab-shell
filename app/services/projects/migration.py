"""
Project workspace session migration helpers.
"""

from __future__ import annotations

from services.projects.preferences import migrate_active_project_preference
from services.projects.slugs import allocate_slug


def migrate_project_workspace_session(conn, from_session_id, to_session_id):
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
    label_result = conn.execute(
        "UPDATE entity_labels SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    note_result = conn.execute(
        "UPDATE entity_notes SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    package_result = conn.execute(
        "UPDATE evidence_packages SET session_id = ? WHERE session_id = ?",
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
        "migrated_entity_labels": label_result.rowcount,
        "migrated_entity_notes": note_result.rowcount,
        "migrated_evidence_packages": package_result.rowcount,
        "migrated_active_project_preference": migrated_active_project_preference,
    }
