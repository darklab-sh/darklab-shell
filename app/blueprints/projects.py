"""
Project workspace routes.
"""

import logging
import os
import time

from flask import Blueprint, jsonify, request, send_file
from werkzeug.exceptions import BadRequest

from config import CFG
from extensions import limiter
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.download_tickets import (
    DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    DownloadTicketError,
    create_download_ticket,
    read_download_ticket,
)
from services import metrics as app_metrics
from services.projects.contracts import (
    BULK_AUDIT_FAILURE_LIMIT,
    EvidencePackageBuildError,
    EvidencePackageTooLarge,
    MAX_BULK_RUN_ACTION_ITEMS,
    ProjectWorkspaceError,
    ProjectWorkspaceNotFound,
    ProjectWorkspaceQuotaExceeded,
)
from services.projects.active import clear_active_project, get_active_project, set_active_project
from services.projects.auto_promote import (
    apply_stored_rule as apply_auto_promote_rule,
    create_rule as create_auto_promote_rule,
    delete_rule as delete_auto_promote_rule,
    get_rule as get_auto_promote_rule,
    list_rules as list_auto_promote_rules,
    preview_rule as preview_auto_promote_rule,
    update_rule as update_auto_promote_rule,
)
from services.projects.crud import create_project, delete_project, update_project
from services.projects.findings import (
    bulk_update_project_finding_review_states,
    list_project_findings,
    list_run_findings,
    update_finding_review_state,
)
from services.projects.links import (
    link_project_entities,
    link_project_entity,
    link_project_run_entities,
    list_project_links,
    preview_project_run_entity_links,
    preview_project_run_entity_unlinks,
    unlink_project_entities,
    unlink_project_entity,
    unlink_project_run_entities,
)
from services.projects.metadata import (
    add_entity_label,
    delete_entity_label,
    delete_entity_note,
    entity_metadata_target_exists,
    default_finding_triage_details,
    finding_triage_target_exists,
    get_finding_triage_details,
    get_entity_note,
    list_entity_labels,
    upsert_finding_triage_details,
    upsert_entity_note,
)
from services.projects.package_archive import (
    build_evidence_package_archive,
    create_evidence_package,
    delete_evidence_package,
)
from services.projects.package_jobs import (
    discard_evidence_package_archive_job,
    evidence_package_archive_for_job,
    get_evidence_package_archive_job,
    start_evidence_package_archive_job,
)
from services.projects.package_presets import list_package_presets
from services.projects.queries import (
    get_evidence_package,
    get_project,
    get_project_run_file_artifact,
    get_project_summary,
    list_evidence_packages,
    list_project_artifacts,
    list_project_entities,
    list_project_runs,
    list_projects_page,
    list_projects_switcher,
    list_projects,
)
from services.projects.targets import (
    add_project_target,
    delete_project_target,
    list_project_targets,
    update_project_target,
)
from services.projects.artifacts import artifact_owner_context
from services.projects.utils import cfg_int
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied
from services.workspace.files import (
    InvalidWorkspacePath,
    WorkspaceBinaryFile,
    WorkspaceDisabled,
    WorkspaceError,
    WorkspaceFileNotFound,
    WorkspacePathNotFound,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
    open_owner_workspace_file_for_download,
    read_owner_workspace_text_file,
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
        scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return session_id, "", (jsonify(payload), status)
    if required_capability is not None:
        try:
            require_capability(str((scope.member or {}).get("role") or ""), required_capability)
        except TeamPermissionDenied as exc:
            return session_id, "", _team_permission_error_response(exc)
    return session_id, scope.team_id, None


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
        scope = current_request_scope(session_id, request)
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
        "status": status,
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


@projects_bp.route("/projects")
def projects_list():
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    include_archived = str(request.args.get("include_archived") or "").lower() in {"1", "true", "yes"}
    include_counts = str(request.args.get("include_counts") or "").lower() in {"1", "true", "yes"}
    mode = str(request.args.get("mode") or "").strip().lower()
    if mode == "switcher":
        limit = _parse_int(request.args.get("limit"), 8, minimum=1, maximum=20)
        page = list_projects_switcher(
            session_id,
            query=request.args.get("q") or request.args.get("query") or "",
            limit=limit,
            team_id=team_id,
        )
        log.debug("PROJECTS_SWITCHER_VIEWED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "count": len(page["projects"]),
            "total": page["total"],
            "query": page.get("query") or "",
        })
        return jsonify(page)
    if "limit" in request.args or "offset" in request.args or include_counts:
        limit = _parse_int(request.args.get("limit"), 50, minimum=1, maximum=100)
        offset = _parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000)
        page = list_projects_page(
            session_id,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            include_counts=include_counts,
            team_id=team_id,
        )
        log.debug("PROJECTS_VIEWED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "count": len(page["projects"]),
            "total": page["total"],
            "include_archived": include_archived,
        })
        return jsonify(page)
    projects = list_projects(session_id, include_archived=include_archived, team_id=team_id)
    log.debug("PROJECTS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": len(projects),
        "include_archived": include_archived,
    })
    return jsonify({"projects": projects})


@projects_bp.route("/projects", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_create():
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        project = create_project(session_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    log.info("PROJECT_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project["id"] if project else "",
    })
    return jsonify({"ok": True, "project": project}), 201


@projects_bp.route("/projects/active")
def projects_active_get():
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    project = get_active_project(session_id, team_id=team_id)
    return jsonify({"project": project})


@projects_bp.route("/projects/active", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_active_set():
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    try:
        project = set_active_project(session_id, data.get("project_id"), team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if not project:
        return _project_not_found()
    log.info("PROJECT_ACTIVE_SET", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project["id"],
    })
    return jsonify({"ok": True, "project": project})


@projects_bp.route("/projects/active", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_active_clear():
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    cleared = clear_active_project(session_id, team_id=team_id)
    log.info("PROJECT_ACTIVE_CLEARED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "cleared": cleared,
    })
    return jsonify({"ok": True, "cleared": cleared})


@projects_bp.route("/projects/<project_id>")
def projects_get(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    project = get_project(session_id, project_id, team_id=team_id)
    return _project_json_or_404(project, key="project")


@projects_bp.route("/projects/<project_id>/summary")
def projects_summary(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    summary = get_project_summary(session_id, project_id, team_id=team_id)
    return _project_json_or_404(summary)


@projects_bp.route("/projects/package-presets")
def projects_package_presets():
    session_id, _team_id, error_response = _project_owner()
    if error_response:
        return error_response
    try:
        presets = list_package_presets(CFG)
    except ProjectWorkspaceError as exc:
        log.error("PACKAGE_PRESETS_LOAD_FAILED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "error": str(exc),
        })
        return jsonify({
            "error": "package_presets_unavailable",
            "message": "Package presets are unavailable.",
        }), 500
    return jsonify({"presets": presets})


@projects_bp.route("/projects/<project_id>", methods=["PUT"])
@limiter.limit(_project_write_limit)
def projects_update(project_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        project = update_project(session_id, project_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if not project:
        return _project_not_found()
    log.info("PROJECT_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "status": project["status"],
    })
    return jsonify({"ok": True, "project": project})


@projects_bp.route("/projects/<project_id>", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_delete(project_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    deleted = delete_project(session_id, project_id, team_id=team_id)
    if not deleted:
        return _project_not_found()
    log.info("PROJECT_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/links")
def projects_links_list(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    links = list_project_links(session_id, project_id, team_id=team_id)
    return _project_json_or_404(links, key="links")


@projects_bp.route("/projects/<project_id>/runs")
def projects_runs_list(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    runs = list_project_runs(
        session_id,
        project_id,
        limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
        offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
        team_id=team_id,
    )
    return _project_json_or_404(runs)


@projects_bp.route("/projects/<project_id>/entities")
def projects_entities_list(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    filters = {
        "run_id": request.args.getlist("run_id"),
        "target_id": request.args.getlist("target_id"),
    }
    entities = list_project_entities(
        session_id,
        project_id,
        filters,
        entity_type=request.args.get("type") or "",
        limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
        offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
        team_id=team_id,
    )
    return _project_json_or_404(entities)


@projects_bp.route("/projects/<project_id>/auto-promote-rules")
def projects_auto_promote_rules_list(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    rules = list_auto_promote_rules(session_id, project_id, team_id=team_id)
    return _project_json_or_404(rules, key="rules")


@projects_bp.route("/projects/<project_id>/auto-promote-rules/preview", methods=["POST"])
@limiter.limit(_project_auto_promote_preview_limit, key_func=get_session_id)
def projects_auto_promote_rules_preview(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    try:
        preview = preview_auto_promote_rule(
            session_id,
            project_id,
            data,
            team_id=team_id,
            limit=_project_auto_promote_match_limit(
                request.args.get("limit"),
                "max_project_auto_promote_preview_matches",
                200,
                hard_max=1000,
            ),
        )
    except ProjectWorkspaceError as exc:
        _log_project_auto_promote_rejected(
            "PROJECT_AUTO_PROMOTE_RULE_PREVIEW_REJECTED",
            session_id,
            team_id,
            project_id,
            exc,
            data=data,
        )
        return _project_error_response(exc)
    log.debug("PROJECT_AUTO_PROMOTE_RULE_PREVIEWED", extra={
        **_project_auto_promote_log_context(session_id, team_id, project_id),
        **_project_auto_promote_safe_rule(preview.get("rule") if isinstance(preview, dict) else {}),
        **_project_auto_promote_result_fields(preview),
    })
    return jsonify({"ok": True, "preview": preview})


@projects_bp.route("/projects/<project_id>/auto-promote-rules", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_auto_promote_rules_create(project_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    team_context = _project_team_log_context(session_id, team_id)
    try:
        rule = create_auto_promote_rule(
            session_id,
            project_id,
            data,
            team_id=team_id,
            member_id=team_context.get("actor_member_id", ""),
        )
    except ProjectWorkspaceError as exc:
        _log_project_auto_promote_rejected(
            "PROJECT_AUTO_PROMOTE_RULE_CREATE_REJECTED",
            session_id,
            team_id,
            project_id,
            exc,
            data=data,
        )
        return _project_error_response(exc)
    log.info("PROJECT_AUTO_PROMOTE_RULE_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "rule_id": rule["id"],
        **_project_auto_promote_safe_rule(rule),
        **team_context,
    })
    return jsonify({"ok": True, "rule": rule}), 201


@projects_bp.route("/projects/<project_id>/auto-promote-rules/<rule_id>", methods=["PUT"])
@limiter.limit(_project_write_limit)
def projects_auto_promote_rules_update(project_id, rule_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    team_context = _project_team_log_context(session_id, team_id)
    try:
        rule = update_auto_promote_rule(session_id, project_id, rule_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        _log_project_auto_promote_rejected(
            "PROJECT_AUTO_PROMOTE_RULE_UPDATE_REJECTED",
            session_id,
            team_id,
            project_id,
            exc,
            rule_id=rule_id,
            data=data,
        )
        return _project_error_response(exc)
    if rule is None:
        log.warning("PROJECT_AUTO_PROMOTE_RULE_UPDATE_MISS", extra={
            **_project_auto_promote_log_context(session_id, team_id, project_id, rule_id=rule_id),
            "status": 404,
            "reason": "auto-promote rule not found",
        })
        return _project_not_found("auto-promote rule not found")
    log.info("PROJECT_AUTO_PROMOTE_RULE_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "rule_id": rule_id,
        **_project_auto_promote_safe_rule(rule),
        **team_context,
    })
    return jsonify({"ok": True, "rule": rule})


@projects_bp.route("/projects/<project_id>/auto-promote-rules/<rule_id>", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_auto_promote_rules_delete(project_id, rule_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    rule_for_log = get_auto_promote_rule(session_id, project_id, rule_id, team_id=team_id)
    deleted = delete_auto_promote_rule(session_id, project_id, rule_id, team_id=team_id)
    if deleted is None:
        log.warning("PROJECT_AUTO_PROMOTE_RULE_DELETE_MISS", extra={
            **_project_auto_promote_log_context(session_id, team_id, project_id, rule_id=rule_id),
            "status": 404,
            "reason": "auto-promote rule not found",
        })
        return _project_not_found("auto-promote rule not found")
    log.info("PROJECT_AUTO_PROMOTE_RULE_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "rule_id": rule_id,
        **_project_auto_promote_safe_rule(rule_for_log),
        **_project_team_log_context(session_id, team_id),
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/auto-promote-rules/<rule_id>/apply", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_auto_promote_rules_apply(project_id, rule_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        result = apply_auto_promote_rule(
            session_id,
            project_id,
            rule_id,
            team_id=team_id,
            limit=_project_auto_promote_match_limit(
                request.args.get("limit"),
                "max_project_auto_promote_apply_matches",
                1000,
                hard_max=5000,
            ),
        )
    except ProjectWorkspaceError as exc:
        _log_project_auto_promote_rejected(
            "PROJECT_AUTO_PROMOTE_RULE_APPLY_REJECTED",
            session_id,
            team_id,
            project_id,
            exc,
            rule_id=rule_id,
        )
        return _project_error_response(exc)
    if result is None:
        log.warning("PROJECT_AUTO_PROMOTE_RULE_APPLY_MISS", extra={
            **_project_auto_promote_log_context(session_id, team_id, project_id, rule_id=rule_id),
            "status": 404,
            "reason": "auto-promote rule not found",
        })
        return _project_not_found("auto-promote rule not found")
    log.info("PROJECT_AUTO_PROMOTE_RULE_APPLIED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "rule_id": rule_id,
        **_project_auto_promote_safe_rule(result.get("rule") if isinstance(result, dict) else {}),
        **_project_auto_promote_result_fields(result),
        **_project_team_log_context(session_id, team_id),
    })
    return jsonify({"ok": True, "result": result})


@projects_bp.route("/projects/<project_id>/links", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_links_create(project_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and "entity_ids" in data:
        try:
            result = link_project_entities(session_id, project_id, data, team_id=team_id)
        except ProjectWorkspaceError as exc:
            if str(exc) == "too_many":
                return _project_bulk_too_many_response()
            return _project_error_response(exc)
        if result is None:
            return _project_not_found()
        counts = result.get("counts", {})
        log.info("PROJECT_LINKS_BULK_ADDED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "project_id": project_id,
            "entity_type": data.get("entity_type") or "",
            "counts": counts,
            "failures": _project_bulk_failures(result.get("results")),
        })
        if data.get("include_entities") and data.get("entity_type") == "run":
            linked_entities = link_project_run_entities(
                session_id,
                project_id,
                [str(run_id or "") for run_id in data.get("entity_ids") or []],
                data.get("source") or "manual",
                team_id=team_id,
            )
            if linked_entities is not None:
                result["linked_entities"] = linked_entities
        return jsonify(result)
    try:
        link = link_project_entity(session_id, project_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if link is None:
        return _project_not_found()
    log.info("PROJECT_LINK_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "entity_type": link["entity_type"],
        "source": link["source"],
    })
    body = {"ok": True, "link": link}
    if data.get("include_entities") and data.get("entity_type") == "run":
        linked_entities = link_project_run_entities(
            session_id,
            project_id,
            [str(data.get("entity_id") or "")],
            data.get("source") or "manual",
            team_id=team_id,
        )
        if linked_entities is not None:
            body["linked_entities"] = linked_entities
    return jsonify(body), 201


@projects_bp.route("/projects/<project_id>/links/run-entities/preview", methods=["POST"])
def projects_run_entity_link_preview(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    try:
        preview = preview_project_run_entity_links(session_id, project_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        if str(exc) == "too_many":
            return _project_bulk_too_many_response()
        return _project_error_response(exc)
    if preview is None:
        return _project_not_found()
    return jsonify({"ok": True, "preview": preview})


@projects_bp.route("/projects/<project_id>/links/run-entities/remove-preview", methods=["POST"])
def projects_run_entity_unlink_preview(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    try:
        preview = preview_project_run_entity_unlinks(session_id, project_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        if str(exc) == "too_many":
            return _project_bulk_too_many_response()
        return _project_error_response(exc)
    if preview is None:
        return _project_not_found()
    return jsonify({"ok": True, "preview": preview})


@projects_bp.route("/projects/<project_id>/links", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_links_delete(project_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and "entity_ids" in data:
        try:
            result = unlink_project_entities(session_id, project_id, data, team_id=team_id)
        except ProjectWorkspaceError as exc:
            if str(exc) == "too_many":
                return _project_bulk_too_many_response()
            return _project_error_response(exc)
        if result is None:
            return _project_not_found()
        counts = result.get("counts", {})
        log.info("PROJECT_LINKS_BULK_REMOVED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "project_id": project_id,
            "entity_type": data.get("entity_type") or "",
            "counts": counts,
            "failures": _project_bulk_failures(result.get("results")),
        })
        return jsonify(result)
    try:
        deleted = unlink_project_entity(session_id, project_id, data, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if deleted is None:
        return _project_not_found()
    if not deleted:
        return _project_not_found("project link not found")
    body: dict[str, object] = {"ok": True}
    unlinked_entity_count = 0
    if (
        data.get("entity_type") == "run"
        and (data.get("include_entities") or data.get("include_curated_entities"))
    ):
        unlinked_entities = unlink_project_run_entities(
            session_id,
            project_id,
            [str(data.get("entity_id") or "")],
            include_curated=bool(data.get("include_curated_entities")),
            team_id=team_id,
        )
        if unlinked_entities is not None:
            body["unlinked_entities"] = unlinked_entities
            unlinked_entity_count = int(unlinked_entities.get("removed", 0) or 0)
    log.info("PROJECT_LINK_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "entity_type": data.get("entity_type") or "",
        "entity_id": data.get("entity_id") or "",
        "unlinked_entities": unlinked_entity_count,
    })
    return jsonify(body)


@projects_bp.route("/projects/<project_id>/targets")
def projects_targets_list(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    auto_discovered = str(request.args.get("auto_discovered") or "").strip().lower() in {"1", "true", "yes", "on"}
    targets = list_project_targets(
        session_id,
        project_id,
        target_type=request.args.get("type") or "",
        query=request.args.get("q") or "",
        auto_discovered=auto_discovered,
        limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=100),
        offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
        team_id=team_id,
    )
    return _project_json_or_404(targets)


@projects_bp.route("/projects/<project_id>/targets", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_targets_create(project_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        target = add_project_target(session_id, project_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if target is None:
        return _project_not_found()
    log.info("PROJECT_TARGET_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "target_type": target["type"],
    })
    return jsonify({"ok": True, "target": target}), 201


@projects_bp.route("/projects/<project_id>/targets/<target_id>", methods=["PUT"])
@limiter.limit(_project_write_limit)
def projects_targets_update(project_id, target_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        target = update_project_target(session_id, project_id, target_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if target is None:
        return _project_not_found("target not found")
    log.info("PROJECT_TARGET_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "target_type": target["type"],
    })
    return jsonify({"ok": True, "target": target})


@projects_bp.route("/projects/<project_id>/targets/<target_id>", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_targets_delete(project_id, target_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        deleted = delete_project_target(session_id, project_id, target_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if deleted is None:
        return _project_not_found()
    if not deleted:
        return _project_not_found("target not found")
    log.info("PROJECT_TARGET_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "target_id": target_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/packages")
def projects_packages_list(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    packages = list_evidence_packages(session_id, project_id, team_id=team_id)
    return _project_json_or_404(packages, key="packages")


@projects_bp.route("/projects/<project_id>/packages", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_packages_create(project_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        package = create_evidence_package(session_id, project_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if package is None:
        return _project_not_found()
    log.info("EVIDENCE_PACKAGE_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package["id"],
        "redaction_mode": package["redaction_mode"],
        "include_artifacts": package["include_artifacts"],
    })
    return jsonify({"ok": True, "package": package}), 201


@projects_bp.route("/projects/<project_id>/packages/<package_id>")
def projects_packages_get(project_id, package_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    package = get_evidence_package(session_id, project_id, package_id, team_id=team_id)
    if package is None:
        return _project_not_found("package not found")
    log.info("EVIDENCE_PACKAGE_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
    })
    return jsonify({"package": package})


@projects_bp.route("/projects/<project_id>/packages/<package_id>/download")
@limiter.limit(_evidence_package_download_limit)
def projects_packages_download(project_id, package_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    build_started = time.perf_counter()
    try:
        archive = build_evidence_package_archive(session_id, project_id, package_id, team_id=team_id)
    except EvidencePackageTooLarge as exc:
        app_metrics.record_evidence_package_build("too_large", time.perf_counter() - build_started)
        return jsonify({"error": str(exc)}), 413
    except EvidencePackageBuildError as exc:
        app_metrics.record_evidence_package_build("error", time.perf_counter() - build_started)
        log.error("PACKAGE_BUILD_FAILED", exc_info=True, extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "project_id": project_id,
            "package_id": package_id,
            "stage": "download",
            "error": str(exc),
        })
        raise
    if archive is None:
        app_metrics.record_evidence_package_build("not_found", time.perf_counter() - build_started)
        return _project_not_found("package not found")
    metrics = archive.get("metrics") if isinstance(archive.get("metrics"), dict) else {}
    app_metrics.record_evidence_package_build(
        "success",
        time.perf_counter() - build_started,
        archive_bytes=int(metrics.get("archive_bytes") or archive.get("byte_size") or 0),
        skipped_artifacts=int(metrics.get("skipped_artifacts") or 0),
        skipped_other_items=max(
            0,
            int(metrics.get("skipped_items") or 0) - int(metrics.get("skipped_artifacts") or 0),
        ),
    )
    log_extra = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
        "skipped_artifacts": len(archive["skipped_artifacts"]),
    }
    log_extra.update(metrics)
    log.info("EVIDENCE_PACKAGE_DOWNLOADED", extra=log_extra)
    archive_path = archive["path"]
    try:
        response = send_file(
            archive_path,
            mimetype=archive["mimetype"],
            as_attachment=True,
            download_name=archive["filename"],
        )
    except Exception as exc:
        log.warning("PROJECT_ROUTE_FAILED", exc_info=True, extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "project_id": project_id,
            "package_id": package_id,
            "route": "projects_packages_download",
            "error": str(exc),
        })
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        raise

    @response.call_on_close
    def _cleanup_evidence_package_archive():
        try:
            os.unlink(archive_path)
        except OSError:
            pass

    return _set_download_content_length(response, archive.get("byte_size") or metrics.get("archive_bytes"))


@projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs", methods=["POST"])
@limiter.limit(_evidence_package_download_limit)
def projects_packages_download_job_create(project_id, package_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    if get_evidence_package(session_id, project_id, package_id, team_id=team_id) is None:
        return _project_not_found("package not found")
    actor_member_id = ""
    if team_id:
        try:
            scope = current_request_scope(session_id, request)
            actor_member_id = str((scope.member or {}).get("id") or "")
        except RequestScopeError as exc:
            payload, status = scope_error_payload(exc)
            return jsonify(payload), status
    job = start_evidence_package_archive_job(
        session_id,
        project_id,
        package_id,
        cfg=CFG,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    job_id = str(job.get("id") or "") if isinstance(job, dict) else ""
    log.info("EVIDENCE_PACKAGE_BUILD_JOB_STARTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "actor_member_id": actor_member_id,
        "project_id": project_id,
        "package_id": package_id,
        "job_id": job_id,
    })
    return jsonify({"ok": True, "job": job}), 202


@projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs/<job_id>")
def projects_packages_download_job_get(project_id, package_id, job_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    job = get_evidence_package_archive_job(session_id, project_id, package_id, job_id, team_id=team_id)
    return _project_json_or_404(job, key="job", error="package build job not found")


@projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs/<job_id>/download")
@limiter.limit(_evidence_package_download_limit)
def projects_packages_download_job_file(project_id, package_id, job_id):
    ticket = str(request.args.get("ticket") or "").strip()
    if ticket:
        try:
            payload = read_download_ticket(ticket, expected_kind="project_package_job")
            session_id, team_id = _project_download_ticket_owner(
                payload,
                project_id=project_id,
                expected_ids={"package_id": package_id, "job_id": job_id},
            )
        except DownloadTicketError as exc:
            return _project_ticket_error_response(exc)
    else:
        session_id, team_id, error_response = _project_owner()
        if error_response:
            return error_response
    archive = evidence_package_archive_for_job(session_id, project_id, package_id, job_id, team_id=team_id)
    if archive is None:
        return _project_not_found("package build job not found")
    status = archive.get("status")
    if status != "complete":
        status_code = 409 if status not in {"failed"} else 400
        return jsonify({"error": archive.get("error") or "package archive is not ready", "status": status}), status_code
    metrics_value = archive.get("metrics")
    metrics = metrics_value if isinstance(metrics_value, dict) else {}
    log_extra = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
        "job_id": job_id,
        "archive_bytes": int(archive.get("archive_bytes") or 0),
        "skipped_artifacts": int(archive.get("skipped_artifacts") or 0),
    }
    log_extra.update(metrics)
    log.info("EVIDENCE_PACKAGE_BUILD_JOB_DOWNLOADED", extra=log_extra)
    try:
        response = send_file(
            archive["path"],
            mimetype=archive["mimetype"],
            as_attachment=True,
            download_name=archive["filename"],
        )
    except Exception as exc:
        log.warning("PROJECT_ROUTE_FAILED", exc_info=True, extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "project_id": project_id,
            "package_id": package_id,
            "job_id": job_id,
            "route": "projects_packages_download_job_file",
            "error": str(exc),
        })
        discard_evidence_package_archive_job(job_id)
        raise

    @response.call_on_close
    def _cleanup_evidence_package_archive_job():
        discard_evidence_package_archive_job(job_id)

    return _set_download_content_length(response, archive.get("archive_bytes"))


@projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs/<job_id>/download-ticket", methods=["POST"])
@limiter.limit(_evidence_package_download_limit)
def projects_packages_download_job_ticket(project_id, package_id, job_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    archive = evidence_package_archive_for_job(session_id, project_id, package_id, job_id, team_id=team_id)
    if archive is None:
        return _project_not_found("package build job not found")
    status = archive.get("status")
    if status != "complete":
        status_code = 409 if status not in {"failed"} else 400
        return jsonify({"error": archive.get("error") or "package archive is not ready", "status": status}), status_code
    ticket = create_download_ticket({
        "kind": "project_package_job",
        "session_id": session_id,
        "team_id": team_id,
        "project_id": project_id,
        "package_id": package_id,
        "job_id": job_id,
    })
    return jsonify({
        "ok": True,
        "url": (
            f"/projects/{project_id}/packages/{package_id}/download-jobs/"
            f"{job_id}/download?ticket={ticket}"
        ),
        "expires_in_seconds": DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    })


@projects_bp.route("/projects/<project_id>/packages/<package_id>", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_packages_delete(project_id, package_id):
    session_id, team_id, error_response = _project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    deleted = delete_evidence_package(session_id, project_id, package_id, team_id=team_id)
    if not deleted:
        return _project_not_found("package not found")
    log.info("EVIDENCE_PACKAGE_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/artifacts")
def projects_artifacts_list(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    filters = {
        "run_id": request.args.getlist("run_id"),
        "target_id": request.args.getlist("target_id"),
    }
    artifacts = list_project_artifacts(
        session_id,
        project_id,
        filters,
        limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
        offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
        team_id=team_id,
    )
    return _project_json_or_404(artifacts)


@projects_bp.route("/projects/<project_id>/artifacts/<artifact_id>/preview")
def projects_artifacts_preview(project_id, artifact_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    artifact = get_project_run_file_artifact(session_id, project_id, artifact_id, team_id=team_id)
    if artifact is None:
        return _project_not_found("artifact not found")
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), status
    try:
        artifact_session_id = str(artifact.get("session_id") or session_id)
        owner_context = artifact_owner_context(artifact_session_id, artifact)
        text = read_owner_workspace_text_file(owner_context, artifact["workspace_path"], CFG)
    except WorkspaceError as exc:
        return _workspace_project_artifact_error_response(exc)
    return jsonify({"artifact": artifact, "text": text})


@projects_bp.route("/projects/<project_id>/artifacts/<artifact_id>/download")
def projects_artifacts_download(project_id, artifact_id):
    ticket = str(request.args.get("ticket") or "").strip()
    if ticket:
        try:
            payload = read_download_ticket(ticket, expected_kind="project_artifact")
            session_id, team_id = _project_download_ticket_owner(
                payload,
                project_id=project_id,
                expected_ids={"artifact_id": artifact_id},
            )
        except DownloadTicketError as exc:
            return _project_ticket_error_response(exc)
    else:
        session_id, team_id, error_response = _project_owner()
        if error_response:
            return error_response
    artifact = get_project_run_file_artifact(session_id, project_id, artifact_id, team_id=team_id)
    if artifact is None:
        return _project_not_found("artifact not found")
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), status
    try:
        artifact_session_id = str(artifact.get("session_id") or session_id)
        owner_context = artifact_owner_context(artifact_session_id, artifact)
        handle = open_owner_workspace_file_for_download(owner_context, artifact["workspace_path"], CFG)
    except WorkspaceError as exc:
        return _workspace_project_artifact_error_response(exc)
    download_name = artifact.get("display_name") or artifact["workspace_path"].split("/")[-1] or "artifact"
    response = send_file(
        handle,
        as_attachment=True,
        download_name=download_name,
        mimetype=artifact.get("content_type") or "application/octet-stream",
    )
    return _set_download_content_length(response, _download_handle_size(handle))


@projects_bp.route("/projects/<project_id>/artifacts/<artifact_id>/download-ticket", methods=["POST"])
def projects_artifacts_download_ticket(project_id, artifact_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    artifact = get_project_run_file_artifact(session_id, project_id, artifact_id, team_id=team_id)
    if artifact is None:
        return _project_not_found("artifact not found")
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), status
    try:
        artifact_session_id = str(artifact.get("session_id") or session_id)
        owner_context = artifact_owner_context(artifact_session_id, artifact)
        with open_owner_workspace_file_for_download(owner_context, artifact["workspace_path"], CFG):
            pass
    except WorkspaceError as exc:
        return _workspace_project_artifact_error_response(exc)
    ticket = create_download_ticket({
        "kind": "project_artifact",
        "session_id": session_id,
        "team_id": team_id,
        "project_id": project_id,
        "artifact_id": artifact_id,
    })
    return jsonify({
        "ok": True,
        "url": f"/projects/{project_id}/artifacts/{artifact_id}/download?ticket={ticket}",
        "expires_in_seconds": DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    })


@projects_bp.route("/projects/<project_id>/findings")
def projects_findings_list(project_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    paginated = "limit" in request.args or "offset" in request.args
    filters = {
        "run_id": request.args.getlist("run_id"),
        "target_id": request.args.getlist("target_id"),
        "review_state": request.args.getlist("review_state"),
        "scope": request.args.getlist("scope"),
        "severity": request.args.getlist("severity"),
        "command_root": request.args.getlist("command_root"),
        "label": request.args.getlist("label"),
        "note_state": request.args.get("note_state"),
        "verification_status": request.args.getlist("verification_status"),
        "orphan_filter": request.args.get("orphan_filter"),
        "collapsed_group": request.args.getlist("collapsed_group"),
        "include_collapsed_group_counts": request.args.get("include_collapsed_group_counts"),
        "include_group_counts": request.args.get("include_group_counts"),
        "known_total": request.args.get("known_total"),
    }
    include_total = str(request.args.get("include_total") or "1").lower() not in {"0", "false", "no", "off"}
    try:
        if paginated:
            findings = list_project_findings(
                session_id,
                project_id,
                filters,
                limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
                offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
                include_total=include_total,
                team_id=team_id,
            )
        else:
            findings = list_project_findings(session_id, project_id, filters, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_json_error(str(exc), 400)
    if findings is None:
        return _project_not_found()
    if paginated:
        return jsonify(findings)
    return jsonify({"findings": findings})


@projects_bp.route("/projects/<project_id>/findings/review", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_findings_bulk_review_update(project_id):
    session_id, team_id, error_response = _project_owner(Capability.TRIAGE_FINDINGS)
    if error_response:
        return error_response
    try:
        result = bulk_update_project_finding_review_states(
            session_id,
            project_id,
            request.get_json(silent=True) or {},
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        if str(exc) == "too_many":
            return _project_bulk_too_many_response()
        return _project_error_response(exc)
    if result is None:
        return _project_not_found()
    log.info("PROJECT_FINDINGS_BULK_REVIEW_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "review_state": result["review_state"],
        "updated": result["counts"]["updated"],
        "not_found": result["counts"]["not_found"],
    })
    return jsonify(result)


@projects_bp.route("/entities/run/<run_id>/findings")
def run_findings_list(run_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    paginated = "limit" in request.args or "offset" in request.args
    if paginated:
        findings = list_run_findings(
            session_id,
            run_id,
            limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
            offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
            include_total=True,
            team_id=team_id,
        )
    else:
        findings = list_run_findings(session_id, run_id, team_id=team_id)
    if findings is None:
        return _project_not_found("run not found")
    if paginated:
        return jsonify(findings)
    return jsonify({"findings": findings})


@projects_bp.route("/findings/<finding_id>/review", methods=["PUT"])
@limiter.limit(_project_write_limit)
def findings_review_update(finding_id):
    session_id, team_id, error_response = _project_owner(Capability.TRIAGE_FINDINGS)
    if error_response:
        return error_response
    try:
        finding = update_finding_review_state(session_id, finding_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if finding is None:
        return _project_not_found("finding not found")
    log.info("FINDING_REVIEW_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "review_state": finding["review_state"],
    })
    return jsonify({"ok": True, "finding": finding})


@projects_bp.route("/findings/<finding_id>/triage")
def finding_triage_detail(finding_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    try:
        if not finding_triage_target_exists(session_id, finding_id, team_id=team_id):
            return _project_not_found("finding not found")
        triage = get_finding_triage_details(session_id, finding_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    return jsonify({
        "triage": triage or default_finding_triage_details(session_id, finding_id, team_id=team_id),
    })


@projects_bp.route("/findings/<finding_id>/triage", methods=["PUT"])
@limiter.limit(_project_write_limit)
def finding_triage_update(finding_id):
    session_id, team_id, error_response = _project_owner(Capability.TRIAGE_FINDINGS)
    if error_response:
        return error_response
    try:
        if not finding_triage_target_exists(session_id, finding_id, team_id=team_id):
            return _project_not_found("finding not found")
        if request.is_json:
            body_bytes = len(request.get_data(cache=True) or b"")
            try:
                data = request.get_json(silent=False)
            except BadRequest:
                log.warning("FINDING_TRIAGE_PAYLOAD_DECODE_FAILED", extra={
                    "ip": get_client_ip(),
                    "session": get_log_session_id(session_id),
                    "team_id": team_id,
                    "finding_id": finding_id,
                    "content_type": request.content_type or "",
                    "body_bytes": body_bytes,
                })
                return _project_json_error("finding triage payload must be JSON", 400)
        else:
            data = None
        if not isinstance(data, dict):
            raise ProjectWorkspaceError("finding triage payload must be a JSON object")
        previous = get_finding_triage_details(session_id, finding_id, team_id=team_id)
        next_verification_status = str(data.get("verification_status") or "not_started").strip() or "not_started"
        will_clear = (
            not str(data.get("remediation") or "").strip()
            and not str(data.get("verification_steps") or "").strip()
            and next_verification_status == "not_started"
            and not str(data.get("verification_notes") or "").strip()
        )
        log.debug("FINDING_TRIAGE_UPDATE_REQUESTED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "finding_id": finding_id,
            "previous_verification_status": (
                previous.get("verification_status") if previous else "not_started"
            ),
            "next_verification_status": next_verification_status,
            "will_clear": will_clear,
        })
        triage = upsert_finding_triage_details(
            session_id,
            finding_id,
            data,
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if triage is None and not will_clear:
        log.warning("FINDING_TRIAGE_UPDATE_MISS", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "finding_id": finding_id,
            "reason": "target_missing_after_precheck",
        })
        return _project_not_found("finding not found")
    response = triage or default_finding_triage_details(session_id, finding_id, team_id=team_id)
    action = "cleared" if will_clear else ("updated" if previous else "created")
    log.info("FINDING_TRIAGE_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "finding_id": finding_id,
        "action": action,
        "triage_id": response.get("id") or "",
        "verification_status": response.get("verification_status") or "not_started",
        "has_remediation": bool(str(response.get("remediation") or "").strip()),
        "has_verification_steps": bool(str(response.get("verification_steps") or "").strip()),
        "has_verification_notes": bool(str(response.get("verification_notes") or "").strip()),
    })
    return jsonify({"ok": True, "triage": response})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/labels")
def entity_labels_list(entity_type, entity_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    try:
        labels = list_entity_labels(session_id, entity_type, entity_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_json_error(str(exc), 400)
    if labels is None:
        return _project_not_found("entity not found")
    return jsonify({"labels": labels})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/labels", methods=["POST"])
@limiter.limit(_project_write_limit)
def entity_labels_create(entity_type, entity_id):
    session_id, team_id, error_response = _project_owner(_entity_metadata_write_capability(entity_type))
    if error_response:
        return error_response
    try:
        label = add_entity_label(session_id, entity_type, entity_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if label is None:
        return _project_not_found("entity not found")
    log.info("ENTITY_LABEL_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_type": label["entity_type"],
    })
    return jsonify({"ok": True, "label": label}), 201


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/labels", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def entity_labels_delete(entity_type, entity_id):
    session_id, team_id, error_response = _project_owner(_entity_metadata_write_capability(entity_type))
    if error_response:
        return error_response
    try:
        deleted = delete_entity_label(session_id, entity_type, entity_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if deleted is None:
        return _project_not_found("entity not found")
    if not deleted:
        return _project_not_found("label not found")
    log.info("ENTITY_LABEL_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_type": entity_type,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/note")
def entity_note_get(entity_type, entity_id):
    session_id, team_id, error_response = _project_owner()
    if error_response:
        return error_response
    try:
        if not entity_metadata_target_exists(session_id, entity_type, entity_id, team_id=team_id):
            return _project_not_found("entity not found")
        note = get_entity_note(session_id, entity_type, entity_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_json_error(str(exc), 400)
    return jsonify({"note": note})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/note", methods=["PUT"])
@limiter.limit(_project_write_limit)
def entity_note_update(entity_type, entity_id):
    session_id, team_id, error_response = _project_owner(_entity_metadata_write_capability(entity_type))
    if error_response:
        return error_response
    try:
        note = upsert_entity_note(session_id, entity_type, entity_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if note is None:
        return _project_not_found("entity not found")
    log.info("ENTITY_NOTE_SAVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_type": note["entity_type"],
    })
    return jsonify({"ok": True, "note": note})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/note", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def entity_note_delete(entity_type, entity_id):
    session_id, team_id, error_response = _project_owner(_entity_metadata_write_capability(entity_type))
    if error_response:
        return error_response
    try:
        deleted = delete_entity_note(session_id, entity_type, entity_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if deleted is None:
        return _project_not_found("entity not found")
    if not deleted:
        return _project_not_found("note not found")
    log.info("ENTITY_NOTE_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_type": entity_type,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True})
