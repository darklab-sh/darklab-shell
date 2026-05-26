"""
Session-scoped project workspace helpers.
"""

from __future__ import annotations

from services.projects.active import (
    clear_active_project as clear_active_project,
    get_active_project as get_active_project,
    set_active_project as set_active_project,
)
from services.projects.artifacts import record_run_file_artifacts as record_run_file_artifacts
from services.projects.comparisons import (
    MAX_PROJECT_COMPARE_ITEMS_PER_SIDE as MAX_PROJECT_COMPARE_ITEMS_PER_SIDE,
    compare_project_runs as compare_project_runs,
)
from services.projects.contracts import ProjectWorkspaceError as ProjectWorkspaceError
from services.projects.crud import (
    create_project as create_project,
    delete_project as delete_project,
    update_project as update_project,
)
from services.projects.findings import (
    list_project_findings as list_project_findings,
    list_run_findings as list_run_findings,
    record_run_findings as record_run_findings,
    update_finding_review_state as update_finding_review_state,
)
from services.projects.links import (
    link_active_project_run_entities as link_active_project_run_entities,
    link_project_entities as link_project_entities,
    link_project_entity as link_project_entity,
    link_project_run_entities as link_project_run_entities,
    link_run_to_active_project as link_run_to_active_project,
    list_project_links as list_project_links,
    preview_project_run_entity_links as preview_project_run_entity_links,
    preview_project_run_entity_unlinks as preview_project_run_entity_unlinks,
    unlink_project_entities as unlink_project_entities,
    unlink_project_entity as unlink_project_entity,
    unlink_project_run_entities as unlink_project_run_entities,
)
from services.projects.metadata import (
    add_entity_label as add_entity_label,
    delete_entity_label as delete_entity_label,
    delete_entity_note as delete_entity_note,
    entity_metadata_target_exists as entity_metadata_target_exists,
    get_entity_note as get_entity_note,
    list_entity_labels as list_entity_labels,
    upsert_entity_note as upsert_entity_note,
)
from services.projects.package_archive import (
    build_evidence_package_archive as build_evidence_package_archive,
    create_evidence_package as create_evidence_package,
    delete_evidence_package as delete_evidence_package,
)
from services.projects.queries import (
    get_evidence_package as get_evidence_package,
    get_project as get_project,
    get_project_run_file_artifact as get_project_run_file_artifact,
    get_project_summary as get_project_summary,
    list_evidence_packages as list_evidence_packages,
    list_project_artifacts as list_project_artifacts,
    list_project_entities as list_project_entities,
    list_project_runs as list_project_runs,
    list_projects as list_projects,
    list_projects_page as list_projects_page,
)
from services.projects.targets import (
    _normalize_target_payload as _normalize_target_payload,
    add_project_target as add_project_target,
    delete_project_target as delete_project_target,
    infer_project_target_payload as infer_project_target_payload,
    list_project_targets as list_project_targets,
    record_project_target_discoveries as record_project_target_discoveries,
    update_project_target as update_project_target,
)

__all__ = [
    "MAX_PROJECT_COMPARE_ITEMS_PER_SIDE",
    "ProjectWorkspaceError",
    "_normalize_target_payload",
    "add_entity_label",
    "add_project_target",
    "build_evidence_package_archive",
    "clear_active_project",
    "compare_project_runs",
    "create_evidence_package",
    "create_project",
    "delete_entity_label",
    "delete_entity_note",
    "delete_evidence_package",
    "delete_project",
    "delete_project_target",
    "entity_metadata_target_exists",
    "get_active_project",
    "get_entity_note",
    "get_evidence_package",
    "get_project",
    "get_project_run_file_artifact",
    "get_project_summary",
    "infer_project_target_payload",
    "link_active_project_run_entities",
    "link_project_entities",
    "link_project_entity",
    "link_project_run_entities",
    "link_run_to_active_project",
    "list_entity_labels",
    "list_evidence_packages",
    "list_project_artifacts",
    "list_project_entities",
    "list_project_findings",
    "list_project_links",
    "list_project_runs",
    "list_project_targets",
    "list_projects",
    "list_projects_page",
    "list_run_findings",
    "preview_project_run_entity_links",
    "preview_project_run_entity_unlinks",
    "record_project_target_discoveries",
    "record_run_file_artifacts",
    "record_run_findings",
    "set_active_project",
    "unlink_project_entities",
    "unlink_project_entity",
    "unlink_project_run_entities",
    "update_finding_review_state",
    "update_project",
    "update_project_target",
    "upsert_entity_note",
]
