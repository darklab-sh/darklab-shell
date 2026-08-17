# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Audit event registry and policy metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


DETAILS_VERSION = 1


class RecordingMode(str, Enum):
    FAIL_CLOSED = "fail_closed"
    BEST_EFFORT = "best_effort"


class AuditTargetType(str, Enum):
    RUN = "run"
    SNAPSHOT = "snapshot"
    FILE = "file"
    PROJECT = "project"
    PACKAGE = "package"
    REPORT = "report"
    ENTITY = "entity"
    FINDING = "finding"
    SECRET = "secret"
    DOWNLOAD_TICKET = "download_ticket"
    NOTIFICATION = "notification"
    TEAM = "team"
    SCOPE = "scope"
    LABEL = "label"
    NOTE = "note"
    TARGET = "target"
    SCHEDULE = "schedule"
    WATCHER = "watcher"
    SESSION_TOKEN = "session_token"
    IMPORT = "import"
    WORKFLOW = "workflow"
    WORKFLOW_EXECUTION = "workflow_execution"
    CVE_RISK_SOURCE = "cve_risk_source"
    RISK_ESCALATION = "risk_escalation"
    ASSESSMENT = "assessment"
    ASSESSMENT_CHECK = "assessment_check"
    ASSESSMENT_BATCH = "assessment_batch"
    HTTP_PROFILE = "http_profile"


class AuditEventType(str, Enum):
    HISTORY_DELETE = "history.delete"
    SNAPSHOT_DELETE = "snapshot.delete"
    FILE_WRITE = "file.write"
    FILE_MOVE = "file.move"
    FILE_DELETE = "file.delete"
    PROJECT_UNLINK = "project.unlink"
    PROJECT_DELETE = "project.delete"
    PACKAGE_DELETE = "package.delete"
    ENTITY_DELETE = "entity.delete"
    ENTITY_SUPPRESS = "entity.suppress"
    FINDING_DELETE = "finding.delete"
    FINDING_SUPPRESS = "finding.suppress"
    SNAPSHOT_CREATE = "snapshot.create"
    REDACTION_USE = "redaction.use"
    PACKAGE_BUILD = "package.build"
    REPORT_BUILD = "report.build"
    DOWNLOAD_TICKET_ISSUE = "download_ticket.issue"
    EXPORT_PREVIEW = "export.preview"
    DOWNLOAD_TICKET_REDEEM = "download_ticket.redeem"
    SECRET_CREATE = "secret.create"
    SECRET_UPDATE = "secret.update"
    SECRET_DELETE = "secret.delete"
    SECRET_ROTATE = "secret.rotate"
    NOTIFICATION_CONFIG_CHANGE = "notification.config_change"
    TEAM_CREATE = "team.create"
    TEAM_JOIN = "team.join"
    TEAM_INVITE = "team.invite"
    TEAM_REVOKE = "team.revoke"
    TEAM_MEMBER_REMOVE = "team.member_remove"
    TEAM_LEAVE = "team.leave"
    TEAM_ARCHIVE = "team.archive"
    TEAM_REACTIVATE = "team.reactivate"
    TEAM_ROLE_CHANGE = "team.role_change"
    TEAM_RECOVERY_ROTATE = "team.recovery_rotate"
    TEAM_RECOVERY_REDEEM = "team.recovery_redeem"
    SCOPE_WRITE = "scope.write"
    FINDING_REVIEW_CHANGE = "finding.review_change"
    PROJECT_LINK = "project.link"
    REMEDIATION_EDIT = "finding.remediation_edit"
    REMEDIATION_MERGE = "finding.remediation_merge"
    FINDING_EVIDENCE_LINK = "finding.evidence_link"
    FINDING_EVIDENCE_UNLINK = "finding.evidence_unlink"
    FINDING_MANUAL_CREATE = "finding.manual_create"
    FINDING_MANUAL_UPDATE = "finding.manual_update"
    VERIFICATION_EDIT = "finding.verification_edit"
    LABEL_CHANGE = "label.change"
    NOTE_CHANGE = "note.change"
    TARGET_CHANGE = "target.change"
    SCHEDULE_CREATE = "schedule.create"
    SCHEDULE_UPDATE = "schedule.update"
    SCHEDULE_DELETE = "schedule.delete"
    SCHEDULE_RUN_NOW = "schedule.run_now"
    WATCHER_CREATE = "watcher.create"
    WATCHER_UPDATE = "watcher.update"
    WATCHER_PAUSE = "watcher.pause"
    WATCHER_RESUME = "watcher.resume"
    WATCHER_DELETE = "watcher.delete"
    WATCHER_ACCEPT_BASELINE = "watcher.accept_baseline"
    WATCHER_RUN_NOW = "watcher.run_now"
    WATCHER_ACK = "watcher.ack"
    SESSION_TOKEN_GENERATE = "session_token.generate"
    SESSION_TOKEN_REVOKE = "session_token.revoke"
    SESSION_MIGRATE = "session.migrate"
    IMPORT_APPLY = "import.apply"
    WORKFLOW_CREATE = "workflow.create"
    WORKFLOW_UPDATE = "workflow.update"
    WORKFLOW_DELETE = "workflow.delete"
    WORKFLOW_EXECUTION_START = "workflow_execution.start"
    WORKFLOW_EXECUTION_CANCEL = "workflow_execution.cancel"
    CVE_RISK_REFRESH = "cve_risk.refresh"
    CVE_ADVISORY_REFRESH = "cve_advisory.refresh"
    RISK_ESCALATION_ACK = "risk_escalation.ack"
    ASSESSMENT_CREATE = "assessment.create"
    ASSESSMENT_UPDATE = "assessment.update"
    ASSESSMENT_COMPLETE = "assessment.complete"
    ASSESSMENT_ARCHIVE = "assessment.archive"
    ASSESSMENT_DELETE = "assessment.delete"
    ASSESSMENT_CHECK_STATE_CHANGE = "assessment.check_state_change"
    ASSESSMENT_EVIDENCE_LINK = "assessment.evidence_link"
    ASSESSMENT_EVIDENCE_UNLINK = "assessment.evidence_unlink"
    ASSESSMENT_ACTION_LAUNCH = "assessment.action_launch"
    ASSESSMENT_BATCH_START = "assessment_batch.start"
    ASSESSMENT_BATCH_CANCEL = "assessment_batch.cancel"
    PROBE_LAUNCH = "probe.launch"
    ASSESSMENT_OAST_RESERVE = "assessment.oast_reserve"
    ASSESSMENT_ZAP_JOB_SUBMIT = "assessment.zap_job_submit"
    ASSESSMENT_ZAP_JOB_CANCEL = "assessment.zap_job_cancel"
    HTTP_PROFILE_CREATE = "http_profile.create"
    HTTP_PROFILE_UPDATE = "http_profile.update"
    HTTP_PROFILE_DELETE = "http_profile.delete"


COMMON_DETAIL_KEYS = frozenset({
    "action",
    "ack_state",
    "artifact_count",
    "artifact_total",
    "archive_bytes",
    "already_applied",
    "batch_id",
    "byte_size",
    "changed_fields",
    "channel_id",
    "correlation_id",
    "count",
    "counts",
    "consumer_envs",
    "created_count",
    "deleted_count",
    "details_truncated",
    "download_ticket_id",
    "draft_id",
    "entity_ids",
    "entity_id",
    "entity_type",
    "file_id",
    "file_count",
    "fire_id",
    "file_path",
    "include_artifacts",
    "is_new_secret",
    "format_id",
    "kind",
    "finding_count",
    "finding_total",
    "finding_ids",
    "finding_id",
    "from_state",
    "job_id",
    "label",
    "omitted_detail_keys",
    "options",
    "package_id",
    "project_id",
    "reason",
    "redaction_mode",
    "report_id",
    "result",
    "review_state",
    "role",
    "run_count",
    "run_total",
    "run_ids",
    "run_id",
    "safe_label",
    "schedule_id",
    "secret_name",
    "selection_excluded_counts",
    "selection_modes",
    "snapshot_id",
    "snapshot_ids",
    "source",
    "source_path",
    "source_tool",
    "source_tool_key",
    "status",
    "destination_path",
    "suppressed",
    "surface",
    "timezone",
    "target_invite_id",
    "target_member_id",
    "target_recovery_id",
    "target_count",
    "target_total",
    "target_id",
    "to_state",
    "to_role",
    "from_role",
    "paused_schedules",
    "paused_watchers",
    "updated_count",
    "baseline_run_id",
    "cadence_preset",
    "cron_expr",
    "enabled",
    "fired_at",
    "last_error",
    "next_run_at",
    "note_chars",
    "watcher_id",
    "destination_session_hash",
    "destination_session_label",
    "migration_counts",
    "muted",
    "revoked_current",
    "session_hash",
    "session_label",
    "source_session_hash",
    "source_session_label",
    "triggers",
    "origin",
    "outcome",
    "record_count",
    "source_version",
    "transition_kind",
    "observation_count",
    "member_count",
    "remediation_group_id",
    "assessment_id",
    "check_id",
    "check_key",
    "evidence_id",
    "evidence_link_id",
    "evidence_type",
    "policy_level",
    "profile_key",
    "profile_version",
    "profile_id",
})

HISTORY_DELETE_DETAIL_KEYS = COMMON_DETAIL_KEYS | frozenset({
    "assessment_evidence_unavailable_count",
    "prune_atlas_requested",
    "prune_curated_atlas_requested",
    "atlas_removed_entity_count",
    "atlas_removed_finding_count",
    "atlas_removed_curated_entity_count",
    "atlas_removed_curated_finding_count",
    "atlas_kept_entity_count",
    "atlas_kept_finding_count",
})

PROJECT_UNLINK_DETAIL_KEYS = COMMON_DETAIL_KEYS | frozenset({
    "include_entities_requested",
    "include_curated_entities_requested",
    "unlinked_entity_count",
    "unlinked_finding_count",
    "unlinked_curated_entity_count",
    "unlinked_curated_finding_count",
    "kept_entity_count",
    "kept_finding_count",
})

MANUAL_FINDING_DETAIL_KEYS = COMMON_DETAIL_KEYS | frozenset({
    "manual_revision",
    "severity",
    "evidence_count",
    "duplicate_override",
})

ASSESSMENT_ACTION_DETAIL_KEYS = COMMON_DETAIL_KEYS | frozenset({
    "parameter_observation_id",
    "parameter_source_run_id",
    "schema_artifact_id",
    "schema_operation_count",
})

PROBE_LAUNCH_DETAIL_KEYS = COMMON_DETAIL_KEYS | frozenset({
    "credential_use",
    "profile_role",
})


@dataclass(frozen=True)
class EventSpec:
    event_type: AuditEventType
    target_type: AuditTargetType
    recording_mode: RecordingMode
    allowed_detail_keys: frozenset[str] = COMMON_DETAIL_KEYS


def _spec(
    event_type: AuditEventType,
    target_type: AuditTargetType,
    recording_mode: RecordingMode,
    *,
    detail_keys: frozenset[str] = COMMON_DETAIL_KEYS,
) -> EventSpec:
    return EventSpec(event_type, target_type, recording_mode, detail_keys)


EVENT_SPECS: dict[str, EventSpec] = {
    AuditEventType.FINDING_MANUAL_CREATE.value: _spec(
        AuditEventType.FINDING_MANUAL_CREATE,
        AuditTargetType.FINDING,
        RecordingMode.FAIL_CLOSED,
        detail_keys=MANUAL_FINDING_DETAIL_KEYS,
    ),
    AuditEventType.FINDING_MANUAL_UPDATE.value: _spec(
        AuditEventType.FINDING_MANUAL_UPDATE,
        AuditTargetType.FINDING,
        RecordingMode.FAIL_CLOSED,
        detail_keys=MANUAL_FINDING_DETAIL_KEYS,
    ),
    AuditEventType.ASSESSMENT_CREATE.value: _spec(
        AuditEventType.ASSESSMENT_CREATE,
        AuditTargetType.ASSESSMENT,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.ASSESSMENT_UPDATE.value: _spec(
        AuditEventType.ASSESSMENT_UPDATE,
        AuditTargetType.ASSESSMENT,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.ASSESSMENT_COMPLETE.value: _spec(
        AuditEventType.ASSESSMENT_COMPLETE,
        AuditTargetType.ASSESSMENT,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.ASSESSMENT_ARCHIVE.value: _spec(
        AuditEventType.ASSESSMENT_ARCHIVE,
        AuditTargetType.ASSESSMENT,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.ASSESSMENT_DELETE.value: _spec(
        AuditEventType.ASSESSMENT_DELETE,
        AuditTargetType.ASSESSMENT,
        RecordingMode.FAIL_CLOSED,
    ),
    AuditEventType.ASSESSMENT_CHECK_STATE_CHANGE.value: _spec(
        AuditEventType.ASSESSMENT_CHECK_STATE_CHANGE,
        AuditTargetType.ASSESSMENT_CHECK,
        RecordingMode.FAIL_CLOSED,
    ),
    AuditEventType.ASSESSMENT_EVIDENCE_LINK.value: _spec(
        AuditEventType.ASSESSMENT_EVIDENCE_LINK,
        AuditTargetType.ASSESSMENT_CHECK,
        RecordingMode.FAIL_CLOSED,
    ),
    AuditEventType.ASSESSMENT_EVIDENCE_UNLINK.value: _spec(
        AuditEventType.ASSESSMENT_EVIDENCE_UNLINK,
        AuditTargetType.ASSESSMENT_CHECK,
        RecordingMode.FAIL_CLOSED,
    ),
    AuditEventType.ASSESSMENT_ACTION_LAUNCH.value: _spec(
        AuditEventType.ASSESSMENT_ACTION_LAUNCH,
        AuditTargetType.ASSESSMENT_CHECK,
        RecordingMode.BEST_EFFORT,
        detail_keys=ASSESSMENT_ACTION_DETAIL_KEYS,
    ),
    AuditEventType.ASSESSMENT_BATCH_START.value: _spec(
        AuditEventType.ASSESSMENT_BATCH_START,
        AuditTargetType.ASSESSMENT_BATCH,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.ASSESSMENT_BATCH_CANCEL.value: _spec(
        AuditEventType.ASSESSMENT_BATCH_CANCEL,
        AuditTargetType.ASSESSMENT_BATCH,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.PROBE_LAUNCH.value: _spec(
        AuditEventType.PROBE_LAUNCH,
        AuditTargetType.RUN,
        RecordingMode.BEST_EFFORT,
        detail_keys=PROBE_LAUNCH_DETAIL_KEYS,
    ),
    AuditEventType.ASSESSMENT_OAST_RESERVE.value: _spec(
        AuditEventType.ASSESSMENT_OAST_RESERVE,
        AuditTargetType.ASSESSMENT_CHECK,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.ASSESSMENT_ZAP_JOB_SUBMIT.value: _spec(
        AuditEventType.ASSESSMENT_ZAP_JOB_SUBMIT,
        AuditTargetType.ASSESSMENT_CHECK,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.ASSESSMENT_ZAP_JOB_CANCEL.value: _spec(
        AuditEventType.ASSESSMENT_ZAP_JOB_CANCEL,
        AuditTargetType.ASSESSMENT_CHECK,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.HTTP_PROFILE_CREATE.value: _spec(
        AuditEventType.HTTP_PROFILE_CREATE,
        AuditTargetType.HTTP_PROFILE,
        RecordingMode.FAIL_CLOSED,
    ),
    AuditEventType.HTTP_PROFILE_UPDATE.value: _spec(
        AuditEventType.HTTP_PROFILE_UPDATE,
        AuditTargetType.HTTP_PROFILE,
        RecordingMode.FAIL_CLOSED,
    ),
    AuditEventType.HTTP_PROFILE_DELETE.value: _spec(
        AuditEventType.HTTP_PROFILE_DELETE,
        AuditTargetType.HTTP_PROFILE,
        RecordingMode.FAIL_CLOSED,
    ),
    AuditEventType.CVE_ADVISORY_REFRESH.value: _spec(
        AuditEventType.CVE_ADVISORY_REFRESH,
        AuditTargetType.CVE_RISK_SOURCE,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.CVE_RISK_REFRESH.value: _spec(
        AuditEventType.CVE_RISK_REFRESH,
        AuditTargetType.CVE_RISK_SOURCE,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.RISK_ESCALATION_ACK.value: _spec(
        AuditEventType.RISK_ESCALATION_ACK,
        AuditTargetType.RISK_ESCALATION,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.HISTORY_DELETE.value: _spec(
        AuditEventType.HISTORY_DELETE,
        AuditTargetType.RUN,
        RecordingMode.FAIL_CLOSED,
        detail_keys=HISTORY_DELETE_DETAIL_KEYS,
    ),
    AuditEventType.SNAPSHOT_DELETE.value: _spec(
        AuditEventType.SNAPSHOT_DELETE, AuditTargetType.SNAPSHOT, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.FILE_WRITE.value: _spec(
        AuditEventType.FILE_WRITE, AuditTargetType.FILE, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.FILE_MOVE.value: _spec(
        AuditEventType.FILE_MOVE, AuditTargetType.FILE, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.FILE_DELETE.value: _spec(
        AuditEventType.FILE_DELETE, AuditTargetType.FILE, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.PROJECT_UNLINK.value: _spec(
        AuditEventType.PROJECT_UNLINK,
        AuditTargetType.PROJECT,
        RecordingMode.FAIL_CLOSED,
        detail_keys=PROJECT_UNLINK_DETAIL_KEYS,
    ),
    AuditEventType.PROJECT_DELETE.value: _spec(
        AuditEventType.PROJECT_DELETE, AuditTargetType.PROJECT, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.PACKAGE_DELETE.value: _spec(
        AuditEventType.PACKAGE_DELETE, AuditTargetType.PACKAGE, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.ENTITY_DELETE.value: _spec(
        AuditEventType.ENTITY_DELETE, AuditTargetType.ENTITY, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.ENTITY_SUPPRESS.value: _spec(
        AuditEventType.ENTITY_SUPPRESS, AuditTargetType.ENTITY, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.FINDING_DELETE.value: _spec(
        AuditEventType.FINDING_DELETE, AuditTargetType.FINDING, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.FINDING_SUPPRESS.value: _spec(
        AuditEventType.FINDING_SUPPRESS, AuditTargetType.FINDING, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.SNAPSHOT_CREATE.value: _spec(
        AuditEventType.SNAPSHOT_CREATE, AuditTargetType.SNAPSHOT, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.REDACTION_USE.value: _spec(
        AuditEventType.REDACTION_USE, AuditTargetType.PROJECT, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.PACKAGE_BUILD.value: _spec(
        AuditEventType.PACKAGE_BUILD, AuditTargetType.PACKAGE, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.REPORT_BUILD.value: _spec(
        AuditEventType.REPORT_BUILD, AuditTargetType.REPORT, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.DOWNLOAD_TICKET_ISSUE.value: _spec(
        AuditEventType.DOWNLOAD_TICKET_ISSUE, AuditTargetType.DOWNLOAD_TICKET, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.EXPORT_PREVIEW.value: _spec(
        AuditEventType.EXPORT_PREVIEW, AuditTargetType.PROJECT, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.DOWNLOAD_TICKET_REDEEM.value: _spec(
        AuditEventType.DOWNLOAD_TICKET_REDEEM, AuditTargetType.DOWNLOAD_TICKET, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.SECRET_CREATE.value: _spec(
        AuditEventType.SECRET_CREATE, AuditTargetType.SECRET, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.SECRET_UPDATE.value: _spec(
        AuditEventType.SECRET_UPDATE, AuditTargetType.SECRET, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.SECRET_DELETE.value: _spec(
        AuditEventType.SECRET_DELETE, AuditTargetType.SECRET, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.SECRET_ROTATE.value: _spec(
        AuditEventType.SECRET_ROTATE, AuditTargetType.SECRET, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.NOTIFICATION_CONFIG_CHANGE.value: _spec(
        AuditEventType.NOTIFICATION_CONFIG_CHANGE, AuditTargetType.NOTIFICATION, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.TEAM_CREATE.value: _spec(
        AuditEventType.TEAM_CREATE, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_JOIN.value: _spec(
        AuditEventType.TEAM_JOIN, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_INVITE.value: _spec(
        AuditEventType.TEAM_INVITE, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_REVOKE.value: _spec(
        AuditEventType.TEAM_REVOKE, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_MEMBER_REMOVE.value: _spec(
        AuditEventType.TEAM_MEMBER_REMOVE, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_LEAVE.value: _spec(
        AuditEventType.TEAM_LEAVE, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_ARCHIVE.value: _spec(
        AuditEventType.TEAM_ARCHIVE, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_REACTIVATE.value: _spec(
        AuditEventType.TEAM_REACTIVATE, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_ROLE_CHANGE.value: _spec(
        AuditEventType.TEAM_ROLE_CHANGE, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_RECOVERY_ROTATE.value: _spec(
        AuditEventType.TEAM_RECOVERY_ROTATE, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.TEAM_RECOVERY_REDEEM.value: _spec(
        AuditEventType.TEAM_RECOVERY_REDEEM, AuditTargetType.TEAM, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.SCOPE_WRITE.value: _spec(
        AuditEventType.SCOPE_WRITE, AuditTargetType.SCOPE, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.FINDING_REVIEW_CHANGE.value: _spec(
        AuditEventType.FINDING_REVIEW_CHANGE, AuditTargetType.FINDING, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.PROJECT_LINK.value: _spec(
        AuditEventType.PROJECT_LINK, AuditTargetType.PROJECT, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.REMEDIATION_EDIT.value: _spec(
        AuditEventType.REMEDIATION_EDIT, AuditTargetType.FINDING, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.REMEDIATION_MERGE.value: _spec(
        AuditEventType.REMEDIATION_MERGE, AuditTargetType.FINDING, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.FINDING_EVIDENCE_LINK.value: _spec(
        AuditEventType.FINDING_EVIDENCE_LINK, AuditTargetType.FINDING, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.FINDING_EVIDENCE_UNLINK.value: _spec(
        AuditEventType.FINDING_EVIDENCE_UNLINK, AuditTargetType.FINDING, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.VERIFICATION_EDIT.value: _spec(
        AuditEventType.VERIFICATION_EDIT, AuditTargetType.FINDING, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.LABEL_CHANGE.value: _spec(
        AuditEventType.LABEL_CHANGE, AuditTargetType.LABEL, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.NOTE_CHANGE.value: _spec(
        AuditEventType.NOTE_CHANGE, AuditTargetType.NOTE, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.TARGET_CHANGE.value: _spec(
        AuditEventType.TARGET_CHANGE, AuditTargetType.TARGET, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.SCHEDULE_CREATE.value: _spec(
        AuditEventType.SCHEDULE_CREATE, AuditTargetType.SCHEDULE, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.SCHEDULE_UPDATE.value: _spec(
        AuditEventType.SCHEDULE_UPDATE, AuditTargetType.SCHEDULE, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.SCHEDULE_DELETE.value: _spec(
        AuditEventType.SCHEDULE_DELETE, AuditTargetType.SCHEDULE, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.SCHEDULE_RUN_NOW.value: _spec(
        AuditEventType.SCHEDULE_RUN_NOW, AuditTargetType.SCHEDULE, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WATCHER_CREATE.value: _spec(
        AuditEventType.WATCHER_CREATE, AuditTargetType.WATCHER, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WATCHER_UPDATE.value: _spec(
        AuditEventType.WATCHER_UPDATE, AuditTargetType.WATCHER, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WATCHER_PAUSE.value: _spec(
        AuditEventType.WATCHER_PAUSE, AuditTargetType.WATCHER, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WATCHER_RESUME.value: _spec(
        AuditEventType.WATCHER_RESUME, AuditTargetType.WATCHER, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WATCHER_DELETE.value: _spec(
        AuditEventType.WATCHER_DELETE, AuditTargetType.WATCHER, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.WATCHER_ACCEPT_BASELINE.value: _spec(
        AuditEventType.WATCHER_ACCEPT_BASELINE, AuditTargetType.WATCHER, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WATCHER_RUN_NOW.value: _spec(
        AuditEventType.WATCHER_RUN_NOW, AuditTargetType.WATCHER, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WATCHER_ACK.value: _spec(
        AuditEventType.WATCHER_ACK, AuditTargetType.WATCHER, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.SESSION_TOKEN_GENERATE.value: _spec(
        AuditEventType.SESSION_TOKEN_GENERATE, AuditTargetType.SESSION_TOKEN, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.SESSION_TOKEN_REVOKE.value: _spec(
        AuditEventType.SESSION_TOKEN_REVOKE, AuditTargetType.SESSION_TOKEN, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.SESSION_MIGRATE.value: _spec(
        AuditEventType.SESSION_MIGRATE, AuditTargetType.SESSION_TOKEN, RecordingMode.FAIL_CLOSED
    ),
    AuditEventType.IMPORT_APPLY.value: _spec(
        AuditEventType.IMPORT_APPLY, AuditTargetType.IMPORT, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WORKFLOW_CREATE.value: _spec(
        AuditEventType.WORKFLOW_CREATE, AuditTargetType.WORKFLOW, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WORKFLOW_UPDATE.value: _spec(
        AuditEventType.WORKFLOW_UPDATE, AuditTargetType.WORKFLOW, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WORKFLOW_DELETE.value: _spec(
        AuditEventType.WORKFLOW_DELETE, AuditTargetType.WORKFLOW, RecordingMode.BEST_EFFORT
    ),
    AuditEventType.WORKFLOW_EXECUTION_START.value: _spec(
        AuditEventType.WORKFLOW_EXECUTION_START,
        AuditTargetType.WORKFLOW_EXECUTION,
        RecordingMode.BEST_EFFORT,
    ),
    AuditEventType.WORKFLOW_EXECUTION_CANCEL.value: _spec(
        AuditEventType.WORKFLOW_EXECUTION_CANCEL,
        AuditTargetType.WORKFLOW_EXECUTION,
        RecordingMode.BEST_EFFORT,
    ),
}


def event_spec(event_type: str | AuditEventType) -> EventSpec:
    value = event_type.value if isinstance(event_type, AuditEventType) else str(event_type or "").strip()
    if value not in EVENT_SPECS:
        raise ValueError(f"unknown audit event type: {value}")
    return EVENT_SPECS[value]
