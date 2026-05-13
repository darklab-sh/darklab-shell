"""
Shared project workspace limits, types, and exceptions.
"""

from __future__ import annotations


MAX_PROJECT_NAME_LEN = 120
MAX_PROJECT_DESCRIPTION_LEN = 1000
MAX_PROJECT_COLOR_LEN = 32
MAX_PROJECT_NOTES_LEN = 20000
MAX_ENTITY_ID_LEN = 512
MAX_LABEL_LEN = 80
MAX_ENTITY_NOTE_BODY_LEN = 20000
MAX_TARGET_VALUE_LEN = 512
MAX_FINDING_TITLE_LEN = 240
MAX_PACKAGE_NAME_LEN = 120
MAX_PACKAGE_DESCRIPTION_LEN = 1000
MAX_PROJECT_TARGET_DISCOVERY_PER_RUN = 100
MAX_PROJECT_TARGET_DISCOVERY_FILE_BYTES = 256 * 1024
MAX_PROJECT_TARGET_DISCOVERY_FILE_LINES = 2000
MAX_BULK_RUN_ACTION_ITEMS = 100
BULK_AUDIT_FAILURE_LIMIT = 20
ACTIVE_PROJECT_PREF_KEY = "pref_active_project_id"
PROJECT_AUTO_LINK_EXTERNAL_RUNS_PREF_KEY = "pref_project_auto_link_external_runs"

PROJECT_STATUSES = frozenset({"active", "archived"})
PROJECT_LINK_ENTITY_TYPES = frozenset({
    "run",
})
ENTITY_METADATA_TYPES = frozenset({
    "project",
    "run",
    "snapshot",
    "workspace_file",
    "run_file_artifact",
    "finding",
    "target",
    "package",
})
PROJECT_TARGET_TYPES = frozenset({"domain", "url", "host", "ip", "cidr", "port_set"})
PROJECT_TARGET_REVIEW_STATES = frozenset({"confirmed", "pending", "dismissed"})
PROJECT_TARGET_SOURCES = frozenset({"user", "auto_command", "auto_input_file"})
FINDING_REVIEW_STATES = frozenset({"new", "reviewed", "important", "false_positive", "needs_followup"})
EVIDENCE_PACKAGE_STATUSES = frozenset({"draft"})
PROJECT_TARGET_SELECT_COLUMNS = (
    "id, project_id, type, value, source_run_id, confidence, "
    "review_state, source, source_detail, seen_count, last_seen, dismissed_at, created, updated"
)


class ProjectWorkspaceError(ValueError):
    """Raised when project workspace input is invalid."""


class ProjectWorkspaceNotFound(ProjectWorkspaceError):
    """Raised when a referenced project workspace entity is missing."""


class ProjectWorkspaceQuotaExceeded(ProjectWorkspaceError):
    """Raised when a project workspace quota would be exceeded."""


class EvidencePackageTooLarge(ProjectWorkspaceQuotaExceeded):
    """Raised when an evidence package archive would exceed configured limits."""
