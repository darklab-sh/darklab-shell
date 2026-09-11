# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace preferences, variables, workflows, and history helpers."""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from services.commands.registry import load_tour
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.session.storage import (
    RECENT_VALUE_KINDS,
    add_starred_command,
    get_preferences,
    list_recent_values,
    list_starred_commands,
    mark_tour_seen,
    normalize_recent_value,
    normalize_recent_value_entries,
    remove_starred_commands,
    save_preferences,
    save_recent_values,
)
from services.session.variables import list_session_variables
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScopeError, current_request_scope, scope_error_payload
from services.workflows.user_workflows import (
    UserWorkflowError,
    create_user_workflow,
    delete_user_workflow,
    get_user_workflow,
    list_user_workflows,
    update_user_workflow,
)

log = logging.getLogger("shell")

session_bp = Blueprint("session", __name__)

@session_bp.before_request
def _require_session_write_session():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not get_session_id():
            return jsonify({"error": "session_required"}), 401
    return None


def _session_kind(session_id):
    return "workspace" if str(session_id or "").startswith("wsp_") else "anonymous"


def _active_scope_or_response(session_id):
    try:
        return current_request_scope(session_id, request), None
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return None, (jsonify(payload), status)


def _require_team_workflow_manager(scope):
    if not scope or not scope.is_team:
        return None
    role = str((scope.member or {}).get("role") or "")
    try:
        require_capability(role, Capability.MANAGE_WORKFLOWS)
    except TeamPermissionDenied:
        return jsonify({"error": "team_forbidden", "message": "Your team role cannot manage shared workflows."}), 403
    return None


def _command_root(command):
    return str(command or "").strip().split(maxsplit=1)[0].lower()


def _current_tour_version():
    tour = load_tour()
    version = tour.get("version", 0)
    try:
        return int(version)
    except (TypeError, ValueError):
        return 0


def _normalize_recent_value(kind, value):
    return normalize_recent_value(kind, value)


def _normalize_recent_value_entries(values):
    return normalize_recent_value_entries(values)


def _requested_recent_value_kinds():
    raw_kinds = []
    for value in request.args.getlist("kind"):
        raw_kinds.extend(str(value or "").split(","))
    if not raw_kinds:
        return list(RECENT_VALUE_KINDS), ""
    kinds = []
    for raw_kind in raw_kinds:
        kind = raw_kind.strip().lower()
        if not kind:
            continue
        if kind not in RECENT_VALUE_KINDS:
            return [], f"unsupported recent value kind: {kind}"
        if kind not in kinds:
            kinds.append(kind)
    return kinds or list(RECENT_VALUE_KINDS), ""


@session_bp.route("/session/recent-values")
def session_recent_values_list():
    """Return recently used typed values for autocomplete in this session."""
    kinds, error = _requested_recent_value_kinds()
    if error:
        return jsonify({"error": error}), 400
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    values = list_recent_values(session_id, owner_scope.team_id, kinds)
    return jsonify({"values": values})


@session_bp.route("/session/recent-values", methods=["POST"])
def session_recent_values_save():
    """Persist recently used typed values for autocomplete in this session."""
    data = request.get_json(silent=True) or {}
    raw_values = data.get("values")
    if not isinstance(raw_values, list):
        return jsonify({"error": "values must be a list"}), 400
    session_id = get_session_id()
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    saved, values = save_recent_values(session_id, owner_scope.team_id, raw_values)
    total_count = sum(len(items) for items in values.values())
    log.debug("SESSION_RECENT_VALUES_SAVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "saved": saved,
        "count": total_count,
    })
    return jsonify({"ok": True, "values": values, "saved": saved})


@session_bp.route("/session/preferences")
def session_preferences_get():
    """Return the saved preference snapshot for the current session."""
    session_id = get_session_id()
    return jsonify(get_preferences(session_id))


@session_bp.route("/session/preferences", methods=["POST"])
def session_preferences_save():
    """Persist the current session's full preference snapshot."""
    raw_data = request.get_json(silent=True)
    data: dict[str, object] = dict(raw_data) if isinstance(raw_data, dict) else {}
    raw_preferences_value = data.get("preferences")
    raw_preferences: dict[str, object] = (
        dict(raw_preferences_value) if isinstance(raw_preferences_value, dict) else {}
    )
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    session_id = get_session_id()
    prefs = save_preferences(session_id, raw_preferences, updated)
    log.info("SESSION_PREFERENCES_SAVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "key_count": len(prefs),
    })
    return jsonify({"ok": True, "preferences": prefs, "updated": updated})


@session_bp.route("/session/tour-seen", methods=["POST"])
def session_tour_seen():
    """Record that the current session opened the current tour version."""
    tour_version = _current_tour_version()
    if tour_version < 1:
        return jsonify({"error": "tour is not available"}), 404
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    session_id = get_session_id()
    prefs = mark_tour_seen(session_id, tour_version, updated)
    log.info("SESSION_TOUR_SEEN", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "tour_version": tour_version,
    })
    return jsonify({
        "ok": True,
        "tour_version": tour_version,
        "preferences": prefs,
        "updated": updated,
    })


@session_bp.route("/session/variables")
def session_variables_list():
    """Return command-variable names and values for the current session."""
    session_id = get_session_id()
    variables = list_session_variables(session_id)
    log.debug("SESSION_VARIABLES_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": len(variables),
    })
    return jsonify({
        "variables": [
            {"name": name, "value": value}
            for name, value in variables.items()
        ],
    })


@session_bp.route("/session/workflows")
def session_workflows_list():
    """Return user-created workflows for the current session."""
    session_id = get_session_id()
    scope, error_response = _active_scope_or_response(session_id)
    if error_response:
        return error_response
    workflows = list_user_workflows(session_id, team_id=scope.team_id if scope else "")
    log.debug("USER_WORKFLOWS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": len(workflows),
    })
    return jsonify({"items": workflows})


@session_bp.route("/session/workflows", methods=["POST"])
def session_workflows_create():
    """Create a user workflow for the current session."""
    session_id = get_session_id()
    scope, error_response = _active_scope_or_response(session_id)
    if error_response:
        return error_response
    forbidden = _require_team_workflow_manager(scope)
    if forbidden:
        return forbidden
    try:
        audit_fields = route_audit_fields(session_id, request, scope)
        workflow = create_user_workflow(
            session_id,
            request.get_json(silent=True) or {},
            team_id=scope.team_id if scope else "",
            principal_id=str(audit_fields.get("actor_principal_id") or ""),
            credential_id=str(audit_fields.get("actor_credential_id") or ""),
        )
    except UserWorkflowError as exc:
        log.warning("WORKFLOW_DEFINITION_VALIDATION_FAILED", extra={
            "action": "create",
            "error_count": len(exc.errors),
            "team_id": scope.team_id if scope else "",
            "session": get_log_session_id(session_id),
        })
        return jsonify({"error": str(exc), "errors": exc.errors}), 400
    log.info("USER_WORKFLOW_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "team_id": scope.team_id if scope else "",
        "workflow_id": workflow["id"] if workflow else "",
    })
    if scope and scope.is_team and workflow:
        record_event(
            AuditEventType.WORKFLOW_CREATE,
            target_id=str(workflow["id"]),
            details={"action": "create", "source": "team"},
            **audit_fields,
        )
    return jsonify({"ok": True, "workflow": workflow}), 201


@session_bp.route("/session/workflows/<workflow_id>", methods=["GET"])
def session_workflows_get(workflow_id):
    """Return one user workflow for the current session."""
    session_id = get_session_id()
    scope, error_response = _active_scope_or_response(session_id)
    if error_response:
        return error_response
    workflow = get_user_workflow(session_id, workflow_id, team_id=scope.team_id if scope else "")
    if not workflow:
        return jsonify({"error": "workflow not found"}), 404
    return jsonify({"workflow": workflow})


@session_bp.route("/session/workflows/<workflow_id>", methods=["PUT"])
def session_workflows_update(workflow_id):
    """Update a user workflow for the current session."""
    session_id = get_session_id()
    scope, error_response = _active_scope_or_response(session_id)
    if error_response:
        return error_response
    forbidden = _require_team_workflow_manager(scope)
    if forbidden:
        return forbidden
    try:
        audit_fields = route_audit_fields(session_id, request, scope)
        workflow = update_user_workflow(
            session_id,
            workflow_id,
            request.get_json(silent=True) or {},
            team_id=scope.team_id if scope else "",
            credential_id=str(audit_fields.get("actor_credential_id") or ""),
        )
    except UserWorkflowError as exc:
        log.warning("WORKFLOW_DEFINITION_VALIDATION_FAILED", extra={
            "action": "update",
            "error_count": len(exc.errors),
            "team_id": scope.team_id if scope else "",
            "session": get_log_session_id(session_id),
        })
        return jsonify({"error": str(exc), "errors": exc.errors}), 400
    if not workflow:
        return jsonify({"error": "workflow not found"}), 404
    log.info("USER_WORKFLOW_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "team_id": scope.team_id if scope else "",
        "workflow_id": workflow_id,
    })
    if scope and scope.is_team:
        record_event(
            AuditEventType.WORKFLOW_UPDATE,
            target_id=workflow_id,
            details={"action": "update", "source": "team"},
            **audit_fields,
        )
    return jsonify({"ok": True, "workflow": workflow})


@session_bp.route("/session/workflows/<workflow_id>", methods=["DELETE"])
def session_workflows_delete(workflow_id):
    """Delete a user workflow for the current session."""
    session_id = get_session_id()
    scope, error_response = _active_scope_or_response(session_id)
    if error_response:
        return error_response
    forbidden = _require_team_workflow_manager(scope)
    if forbidden:
        return forbidden
    if not delete_user_workflow(session_id, workflow_id, team_id=scope.team_id if scope else ""):
        return jsonify({"error": "workflow not found"}), 404
    log.info("USER_WORKFLOW_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "team_id": scope.team_id if scope else "",
        "workflow_id": workflow_id,
    })
    if scope and scope.is_team:
        record_event(
            AuditEventType.WORKFLOW_DELETE,
            target_id=workflow_id,
            details={"action": "delete", "source": "team"},
            **route_audit_fields(session_id, request, scope),
        )
    return jsonify({"ok": True})


@session_bp.route("/session/starred")
def session_starred_list():
    """Return the starred command list for the current session."""
    session_id = get_session_id()
    commands = list_starred_commands(session_id)
    log.debug("STARRED_COMMANDS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": len(commands),
    })
    return jsonify({"commands": commands})


@session_bp.route("/session/starred", methods=["POST"])
def session_starred_add():
    """Add a command to the starred list for the current session."""
    data = request.get_json(silent=True) or {}
    command = str(data.get("command") or "").strip()
    if not command:
        return jsonify({"error": "command is required"}), 400
    session_id = get_session_id()
    changed = add_starred_command(session_id, command)
    log.info("STARRED_COMMAND_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "command_root": _command_root(command),
        "changed": bool(changed),
    })
    return jsonify({"ok": True})


@session_bp.route("/session/starred", methods=["DELETE"])
def session_starred_remove():
    """Remove one command (body: {"command": "..."}) or all commands (no body) from the starred list."""
    data = request.get_json(silent=True) or {}
    command = str(data.get("command") or "").strip()
    session_id = get_session_id()
    count = remove_starred_commands(session_id, command)
    event = "STARRED_COMMAND_REMOVED" if command else "STARRED_COMMANDS_CLEARED"
    extra = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": count,
    }
    if command:
        extra["command_root"] = _command_root(command)
    log.info(event, extra=extra)
    return jsonify({"ok": True})
