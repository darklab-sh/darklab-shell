# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project workspace routes.
"""

import logging
import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest

from config import CFG
from extensions import limiter  # noqa: F401 - compatibility seam for route modules/tests
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.audit.context import route_audit_fields
from services.audit.recorder import record_event  # noqa: F401 - compatibility seam for route modules/tests
from services.download_tickets import DownloadTicketError
from services.projects.contracts import (
    BULK_AUDIT_FAILURE_LIMIT,
    MAX_ENTITY_ID_LEN,
    MAX_BULK_RUN_ACTION_ITEMS,
    ProjectWorkspaceNotFound,
    ProjectWorkspaceQuotaExceeded,
)
from services.notifications.channels_store import list_notification_channels
from services.notifications.models import is_durable_session_token
from services.projects.auto_promote import (
    apply_stored_rule as apply_auto_promote_rule,  # noqa: F401 - compatibility seam for projects_auto_promote/tests
    create_rule as create_auto_promote_rule,  # noqa: F401 - compatibility seam for projects_auto_promote/tests
    delete_rule as delete_auto_promote_rule,  # noqa: F401 - compatibility seam for projects_auto_promote/tests
    get_rule as get_auto_promote_rule,  # noqa: F401 - compatibility seam for projects_auto_promote/tests
    list_rules as list_auto_promote_rules,  # noqa: F401 - compatibility seam for projects_auto_promote/tests
    preview_rule as preview_auto_promote_rule,  # noqa: F401 - compatibility seam for projects_auto_promote/tests
    update_rule as update_auto_promote_rule,  # noqa: F401 - compatibility seam for projects_auto_promote/tests
)
from services.projects.metadata import upsert_finding_triage_details  # noqa: F401 - compatibility seam for projects_findings/tests
from services.projects.overview import get_project_intel_overview  # noqa: F401 - compatibility seam for projects_core/tests
from services.projects.utils import cfg_int
from services.reports.composition import compose_report_context  # noqa: F401 - compatibility seam for projects_report/tests
from services.reports.models import normalize_report_draft
from services.reports.rendering import (  # noqa: F401 - compatibility seam for projects_report/tests
    render_report_html_from_context,
    render_report_markdown_from_context,
)
from services.teams.capabilities import Capability, require_capability, role_can
from services.teams.contracts import TeamPermissionDenied
from services.workspace.files import (
    InvalidWorkspacePath,
    WorkspaceBinaryFile,
    WorkspaceDisabled,
    WorkspaceFileNotFound,
    WorkspacePathNotFound,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
)
from services.teams.request_scope import (
    RequestScopeError,
    current_request_scope,
    requested_team_id,
    scope_error_payload,
)

log = logging.getLogger("shell")
projects_bp = Blueprint("projects", __name__)


@projects_bp.before_request
def _require_project_write_session():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not get_session_id():
        return jsonify({"error": "session_required"}), 401
    return None


def _project_write_limit():
    return f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"


def _project_auto_promote_preview_limit():
    minute_limit = int(CFG.get("project_auto_promote_preview_rate_limit_per_minute") or 30)
    second_limit = int(CFG.get("project_auto_promote_preview_rate_limit_per_second") or 2)
    return f"{minute_limit} per minute; {second_limit} per second"


def _parse_int(value, default, *, minimum=0, maximum=100):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _route_filter_stats(values, *, max_len=MAX_ENTITY_ID_LEN):
    seen = set()
    normalized_count = 0
    dropped_empty_count = 0
    trimmed_count = 0
    for raw_value in values:
        raw_text = str(raw_value or "").strip()
        if not raw_text:
            dropped_empty_count += 1
            continue
        normalized = raw_text[:max_len]
        if normalized != raw_text:
            trimmed_count += 1
        if normalized not in seen:
            seen.add(normalized)
            normalized_count += 1
    return {
        "count": normalized_count,
        "dropped_empty_count": dropped_empty_count,
        "trimmed_count": trimmed_count,
    }


def _parse_optional_iso_datetime(value, *, name: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    if "T" not in normalized and " " not in normalized:
        raise BadRequest(f"{name} must be an ISO 8601 datetime such as 2026-05-19T00:00:00Z.")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BadRequest(f"{name} must be an ISO 8601 datetime such as 2026-05-19T00:00:00Z.") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat()


def _project_auto_promote_match_limit(value, key, default, *, hard_max):
    configured = cfg_int(key, default, cfg=CFG)
    configured = max(1, min(configured, hard_max))
    if value is None:
        return configured
    return _parse_int(value, configured, minimum=1, maximum=configured)


def _evidence_package_download_limit():
    return (
        f"{CFG['evidence_package_download_rate_limit_per_minute']} per minute; "
        f"{CFG['evidence_package_download_rate_limit_per_second']} per second"
    )


def _project_error_response(exc):
    status = _project_error_status(exc)
    return _project_json_error(str(exc), status)


def _project_error_status(exc):
    if isinstance(exc, ProjectWorkspaceNotFound):
        return 404
    if isinstance(exc, ProjectWorkspaceQuotaExceeded):
        return 409
    return 400


def _project_json_error(message, status):
    return jsonify({"error": message}), status


def _project_not_found(message="project not found"):
    return _project_json_error(message, 404)


def _report_preview_log_extra(session_id, team_id, project_id, draft, exc):
    draft = draft if isinstance(draft, dict) else {}
    raw_selection = draft.get("selection")
    raw_selection_modes = draft.get("selection_modes")
    raw_selection_filters = draft.get("selection_filters")
    raw_selection_exclude_ids = draft.get("selection_exclude_ids")
    selection = raw_selection if isinstance(raw_selection, dict) else {}
    selection_modes = raw_selection_modes if isinstance(raw_selection_modes, dict) else {}
    selection_filters = raw_selection_filters if isinstance(raw_selection_filters, dict) else {}
    selection_exclude_ids = raw_selection_exclude_ids if isinstance(raw_selection_exclude_ids, dict) else {}
    filter_fields = {}
    filter_active = {}
    for key, value in selection_filters.items():
        if not isinstance(value, dict):
            continue
        fields = sorted(str(field) for field in value.keys())
        filter_fields[str(key)] = fields
        filter_active[str(key)] = any(
            bool(item) if isinstance(item, bool) else bool(str(item or "").strip())
            for item in value.values()
        )
    return {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "selection_modes": {
            str(key): str(value or "")
            for key, value in selection_modes.items()
        },
        "selected_counts": {
            str(key): len(value)
            for key, value in selection.items()
            if isinstance(value, list)
        },
        "excluded_counts": {
            str(key): len(value)
            for key, value in selection_exclude_ids.items()
            if isinstance(value, list)
        },
        "filter_fields": filter_fields,
        "filter_active": filter_active,
        "exception_type": type(exc).__name__,
    }


def _project_json_or_404(value, *, key=None, error="project not found"):
    if value is None:
        return _project_not_found(error)
    if key:
        return jsonify({key: value})
    return jsonify(value)


def _team_permission_error_response(exc):
    return jsonify({"error": "team_forbidden", "message": str(exc)}), 403


def _project_owner(required_capability=None):
    session_id = get_session_id()
    if not requested_team_id(request):
        return session_id, "", None
    try:
        scope = current_request_scope(session_id, request, allow_archived=request.method == "GET")
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return session_id, "", (jsonify(payload), status)
    if required_capability is not None:
        try:
            require_capability(str((scope.member or {}).get("role") or ""), required_capability)
        except TeamPermissionDenied as exc:
            return session_id, "", _team_permission_error_response(exc)
    return session_id, scope.team_id, None


def _project_owner_any_capability(capabilities):
    session_id = get_session_id()
    if not requested_team_id(request):
        return session_id, "", None
    try:
        scope = current_request_scope(session_id, request, allow_archived=request.method == "GET")
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return session_id, "", (jsonify(payload), status)
    role = str((scope.member or {}).get("role") or "")
    if any(role_can(role, capability) for capability in capabilities):
        return session_id, scope.team_id, None
    try:
        require_capability(role, capabilities[0])
    except TeamPermissionDenied as exc:
        return session_id, "", _team_permission_error_response(exc)
    return session_id, scope.team_id, None


def _can_manage_project_digest_settings(session_id, team_id):
    if not is_durable_session_token(session_id):
        return False
    if not team_id:
        return True
    try:
        scope = current_request_scope(session_id, request, allow_archived=request.method == "GET")
    except RequestScopeError:
        return False
    role = str((scope.member or {}).get("role") or "")
    return role_can(role, Capability.MANAGE_AUTOMATION) or role_can(role, Capability.MANAGE_NOTIFICATIONS)


def _project_notification_channels(session_id, team_id):
    if not is_durable_session_token(session_id):
        return []
    return list_notification_channels(session_id, team_id=team_id)


def _project_ticket_error_response(exc):
    return jsonify({"error": str(exc)}), 403


def _project_download_ticket_owner(payload, *, project_id, expected_ids):
    if str(payload.get("project_id") or "") != str(project_id or ""):
        raise DownloadTicketError("download ticket project is invalid")
    for key, expected in expected_ids.items():
        if str(payload.get(key) or "") != str(expected or ""):
            raise DownloadTicketError("download ticket target is invalid")
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        raise DownloadTicketError("download ticket session is invalid")
    return session_id, str(payload.get("team_id") or "").strip()


def _project_actor_member_id(session_id, team_id):
    if not team_id:
        return ""
    try:
        scope = current_request_scope(session_id, request, allow_archived=request.method == "GET")
    except RequestScopeError:
        return ""
    return str((scope.member or {}).get("id") or "")


def _project_audit_fields(session_id, team_id):
    scope = None
    if team_id:
        try:
            scope = current_request_scope(session_id, request, allow_archived=request.method == "GET")
        except RequestScopeError:
            scope = None
    return route_audit_fields(session_id, request, scope)


def _report_request_payload():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise BadRequest("report payload must be a JSON object")
    return data


def _report_draft_from_payload(data, fallback):
    draft = data.get("draft") if isinstance(data.get("draft"), dict) else fallback
    return normalize_report_draft(draft or {})


def _report_draft_requires_mutate(draft):
    export = draft.get("export") if isinstance(draft, dict) else {}
    return (
        str((export or {}).get("redaction_mode") or "redacted") == "raw"
        or bool((export or {}).get("include_private_notes"))
    )


def _report_mutation_permission_error(session_id, draft):
    if not _report_draft_requires_mutate(draft) or not requested_team_id(request):
        return None
    _, _, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    return error_response


def _set_download_content_length(response, size):
    try:
        known_size = int(size)
    except (TypeError, ValueError):
        return response
    if known_size >= 0:
        response.content_length = known_size
    return response


def _download_handle_size(handle):
    try:
        return os.fstat(handle.fileno()).st_size
    except (AttributeError, OSError, ValueError):
        return None


def _entity_metadata_write_capability(entity_type):
    if str(entity_type or "").strip() == "workspace_file":
        return Capability.MANAGE_WORKSPACE_FILES
    return Capability.TRIAGE_FINDINGS


def _project_bulk_too_many_response():
    return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400


def _project_bulk_failures(results):
    failures = []
    for item in results or []:
        status = item.get("status") if isinstance(item, dict) else ""
        if status not in {"not_found", "rejected"}:
            continue
        failure = {
            "run_id": item.get("run_id") or "",
            "status": status,
        }
        if item.get("reason"):
            failure["reason"] = item.get("reason")
        failures.append(failure)
        if len(failures) >= BULK_AUDIT_FAILURE_LIMIT:
            break
    return failures


def _project_team_log_context(session_id, team_id):
    if not team_id:
        return {}
    context = {"team_id": team_id}
    try:
        scope = current_request_scope(session_id, request, allow_archived=request.method == "GET")
    except RequestScopeError:
        return context
    member = scope.member or {}
    context["team_id"] = scope.team_id
    context["actor_member_id"] = member.get("id") or ""
    context["actor_role"] = member.get("role") or ""
    return context


def _project_auto_promote_safe_rule(rule):
    if not isinstance(rule, dict):
        return {}
    safe = {}
    for key in ("enabled", "apply_on_run", "target_entity_kind", "match_mode"):
        if key in rule:
            safe[key] = rule.get(key)
    return safe


def _project_auto_promote_safe_payload(data):
    if not isinstance(data, dict):
        return {}
    safe = {}
    for key in ("enabled", "apply_on_run", "target_entity_kind", "match_mode"):
        if key in data:
            safe[key] = data.get(key)
    return safe


def _project_auto_promote_result_fields(result):
    if not isinstance(result, dict):
        return {}
    fields = {}
    for key in (
        "matched_count",
        "shown_match_count",
        "matched_in_scan_count",
        "already_linked_count",
        "new_link_count",
        "promotable_count",
        "linked_count",
        "promoted_count",
        "skipped_suppressed_count",
        "quota_limited_count",
        "match_cap_limited_count",
        "candidate_scan_limited_count",
        "candidate_scan_count",
        "candidate_scan_limit",
        "limit",
    ):
        if key in result:
            fields[key] = result.get(key)
    fields["truncated"] = bool(result.get("truncated") or result.get("candidate_scan_truncated"))
    return fields


def _project_auto_promote_log_context(session_id, team_id, project_id, *, rule_id=""):
    context = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
    }
    if rule_id:
        context["rule_id"] = rule_id
    context.update(_project_team_log_context(session_id, team_id))
    return context


def _log_project_auto_promote_rejected(event, session_id, team_id, project_id, exc, *, rule_id="", data=None):
    status = _project_error_status(exc)
    log.warning(event, extra={
        **_project_auto_promote_log_context(session_id, team_id, project_id, rule_id=rule_id),
        **_project_auto_promote_safe_payload(data),
        "http_status": status,
        "reason": str(exc),
    })
    return status


def _workspace_project_artifact_error_response(exc):
    if isinstance(exc, WorkspaceDisabled):
        return jsonify({"error": "Files are disabled on this instance"}), 403
    if isinstance(exc, WorkspaceQuotaExceeded):
        return jsonify({"error": str(exc)}), 413
    if isinstance(exc, (WorkspaceFileNotFound, WorkspacePathNotFound)):
        return jsonify({"error": str(exc)}), 404
    if isinstance(exc, WorkspacePermissionDenied):
        return jsonify({"error": str(exc)}), 403
    if isinstance(exc, WorkspaceBinaryFile):
        return jsonify({"error": str(exc)}), 415
    if isinstance(exc, InvalidWorkspacePath):
        return jsonify({"error": str(exc)}), 400
    raise exc


from blueprints.projects_core import (  # noqa: E402,F401
    projects_active_clear,
    projects_active_get,
    projects_active_set,
    projects_activity,
    projects_create,
    projects_entities_list,
    projects_get,
    projects_list,
    projects_overview,
    projects_package_presets,
    projects_runs_list,
    projects_summary,
    projects_update,
)
from blueprints.projects_delete import projects_delete  # noqa: E402,F401
from blueprints.projects_targets import (  # noqa: E402,F401
    projects_targets_create,
    projects_targets_delete,
    projects_targets_list,
    projects_targets_update,
)
from blueprints import projects_assessment_action_launch, projects_assessment_actions, projects_assessment_batch_previews, projects_assessment_checks, projects_assessment_oast, projects_assessment_oast_launch, projects_assessment_zap, projects_assessments, projects_finding_evidence, projects_finding_merges, projects_finding_triage, projects_http_profiles, projects_probe_launch, projects_probe_targets, projects_probes, projects_retest_queue, projects_verification_actions  # noqa: E402,F401,E501
from blueprints.projects_auto_promote import (  # noqa: E402,F401
    projects_auto_promote_rules_apply,
    projects_auto_promote_rules_create,
    projects_auto_promote_rules_delete,
    projects_auto_promote_rules_list,
    projects_auto_promote_rules_preview,
    projects_auto_promote_rules_update,
)
from blueprints.projects_links import (  # noqa: E402,F401
    projects_links_create,
    projects_links_delete,
    projects_links_list,
    projects_run_entity_link_preview,
    projects_run_entity_unlink_preview,
)
from blueprints.projects_monitoring import (  # noqa: E402,F401
    projects_digest_settings_get,
    projects_digest_settings_update,
    projects_monitoring,
    projects_monitoring_fire_update,
    projects_monitoring_summary,
)
from blueprints.projects_monitoring_risk import projects_monitoring_risk_event_update  # noqa: E402,F401
from blueprints.projects_report import (  # noqa: E402,F401
    projects_report_export_job_create,
    projects_report_export_job_file,
    projects_report_export_job_get,
    projects_report_export_job_ticket,
    projects_report_get,
    projects_report_preview,
    projects_report_save,
)
from blueprints.projects_packages import (  # noqa: E402,F401
    projects_packages_create,
    projects_packages_delete,
    projects_packages_download,
    projects_packages_download_job_create,
    projects_packages_download_job_file,
    projects_packages_download_job_get,
    projects_packages_download_job_ticket,
    projects_packages_get,
    projects_packages_list,
)
from blueprints.projects_artifacts import (  # noqa: E402,F401
    projects_artifacts_download,
    projects_artifacts_download_ticket,
    projects_artifacts_list,
    projects_artifacts_preview,
)
from blueprints.projects_web_surface import projects_web_surface_list  # noqa: E402,F401
from blueprints.projects_findings import (  # noqa: E402,F401
    findings_review_update,
    projects_findings_bulk_review_update,
    projects_findings_list,
    run_findings_list,
)
from blueprints.projects_finding_triage import finding_triage_detail, finding_triage_update  # noqa: E402,F401,E501
from blueprints import projects_manual_findings as _projects_manual_findings  # noqa: E402,F401
from blueprints.projects_metadata import (  # noqa: E402,F401
    entity_labels_create,
    entity_labels_delete,
    entity_labels_list,
    entity_note_delete,
    entity_note_get,
    entity_note_update,
)
