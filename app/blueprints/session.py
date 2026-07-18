# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Session token routes: session token generation and session history migration.
"""

import logging
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from services.commands.registry import load_tour
from core.helpers import get_client_ip, get_log_session_id, get_session_id, is_valid_anonymous_session_id
from services.audit.context import request_audit_fields, route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.session.storage import (
    RECENT_VALUE_KINDS,
    add_starred_command,
    create_session_token,
    get_preferences,
    list_recent_values,
    list_starred_commands,
    mark_tour_seen,
    migrate_session_records,
    normalize_recent_value,
    normalize_recent_value_entries,
    remove_starred_commands,
    revoke_session_token,
    save_preferences,
    save_recent_values,
    session_counts,
    session_token_created,
    session_token_exists,
)
from services.session.variables import list_session_variables
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScopeError, current_request_scope, scope_error_payload
from services.teams.storage import token_hash
from services.workflows.user_workflows import (
    UserWorkflowError,
    create_user_workflow,
    delete_user_workflow,
    get_user_workflow,
    list_user_workflows,
    update_user_workflow,
)
from services.workflows.storage import active_execution_count_for_actor
from services.workspace.files import InvalidWorkspacePath, migrate_session_workspace, workspace_usage

log = logging.getLogger("shell")

session_bp = Blueprint("session", __name__)

_SESSION_WRITE_AUTH_EXEMPT_PATHS = {
    "/session/token/generate",
    "/session/token/info",
    "/session/token/revoke",
    "/session/token/verify",
    "/session/migrate",
}


@session_bp.before_request
def _require_session_write_session():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.path not in _SESSION_WRITE_AUTH_EXEMPT_PATHS:
        if not get_session_id():
            return jsonify({"error": "session_required"}), 401
    return None


def _session_kind(session_id):
    return "token" if str(session_id or "").startswith("tok_") else "anonymous"


def _session_hash(session_id):
    value = str(session_id or "").strip()
    return token_hash(value) if value else ""


def _session_label(session_id):
    value = str(session_id or "").strip()
    if not value:
        return ""
    if value.startswith("tok_"):
        return get_log_session_id(value)
    return value[:8] + "********"


def _session_identity_details(session_id, *, prefix="session"):
    value = str(session_id or "").strip()
    label_key = "session_label" if prefix == "session" else f"{prefix}_session_label"
    hash_key = "session_hash" if prefix == "session" else f"{prefix}_session_hash"
    return {
        label_key: _session_label(value),
        hash_key: _session_hash(value),
    }


def _session_audit_fields(actor_session_id):
    session_id = str(actor_session_id or "").strip()
    return {
        "session_id": session_id,
        "actor_session_id": session_id,
        **request_audit_fields(request),
    }


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


@session_bp.route("/session/token/generate")
def session_token_generate():
    """Generate a new session token, persist it, and return it.

    The token uses a cryptographically random 32-hex-character suffix with a
    ``tok_`` prefix so it is visually distinct from UUID session IDs in logs
    and the database.  The caller is responsible for storing the token in
    ``localStorage`` as ``session_token`` and sending it as ``X-Session-ID``
    on subsequent requests.
    """
    session_token = "tok_" + secrets.token_hex(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    create_session_token(
        session_token,
        created,
        audit_target_id=_session_label(session_token),
        audit_details={
            "source": "browser",
            **_session_identity_details(session_token, prefix="session"),
        },
        audit_fields=_session_audit_fields(get_session_id()),
    )
    log.info("SESSION_TOKEN_GENERATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(get_session_id()),
        "session_kind": _session_kind(get_session_id()),
    })
    return jsonify({"session_token": session_token})


@session_bp.route("/session/token/info")
def session_token_info():
    """Return the current session token and its creation date.

    Returns ``{"token": "tok_...", "created": "YYYY-MM-DD HH:MM:SS"}`` when the
    caller is using a named session token, or ``{"token": null, "created": null}``
    for anonymous UUID sessions.  The ``created`` field may be ``null`` for tokens
    that pre-date the ``created`` column (edge case in older deployments).
    """
    session_id = get_session_id()
    if not session_id.startswith("tok_"):
        return jsonify({"token": None, "created": None})
    created = session_token_created(session_id)
    # get_session_id() already rejects revoked tokens; this row-absent check
    # guards the narrow TOCTOU window between that validation and this query.
    if created is None:
        return jsonify({"token": None, "created": None})
    return jsonify({"token": session_id, "created": created})


@session_bp.route("/session/token/revoke", methods=["POST"])
def session_token_revoke():
    """Permanently delete a session token from the server.

    Accepts ``{"token": "tok_..."}`` in the request body.  The token must carry a
    ``tok_`` prefix and must exist in ``session_tokens``; any other value returns a
    4xx error.  On success the token is deleted and can no longer be used as a
    named session identity.  Associated run history, snapshots, starred commands,
    and saved session preferences remain in the database under the now-orphaned
    session ID; they are not deleted and are not migrated.

    Possession of the token value is the only authorization check — there is no
    higher-level ownership model.  If the caller is revoking their own current
    active token (``X-Session-ID == token``) the client is responsible for
    switching to an anonymous session after this call succeeds.
    """
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    current_session_id = get_session_id()
    if not token:
        log.warning("SESSION_TOKEN_REVOKE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": "missing_token",
        })
        return jsonify({"error": "token is required"}), 400
    if not token.startswith("tok_"):
        log.warning("SESSION_TOKEN_REVOKE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": "not_tok_token",
        })
        return jsonify({"error": "only tok_ tokens can be revoked"}), 400
    revoked_count = revoke_session_token(
        token,
        audit_target_id=_session_label(token),
        audit_details={
            "source": "browser",
            "revoked_current": token == current_session_id,
            **_session_identity_details(token, prefix="session"),
        },
        audit_fields=_session_audit_fields(current_session_id),
    )
    if revoked_count == 0:
        log.warning("SESSION_TOKEN_REVOKE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": "not_found",
        })
        return jsonify({"error": "token not found"}), 404
    log.info("SESSION_TOKEN_REVOKED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(current_session_id),
        "session_kind": _session_kind(current_session_id),
        "revoked_current": token == current_session_id,
    })
    return jsonify({"ok": True})


@session_bp.route("/session/token/verify", methods=["POST"])
def session_token_verify():
    """Check whether a tok_ session token was issued by this server.

    UUID-format tokens are anonymous sessions never stored in ``session_tokens``
    and are treated as always-valid.  Only ``tok_`` prefixed tokens are checked
    against the table.

    Returns ``{"ok": true, "exists": true/false}``.
    """
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token is required"}), 400
    if not token.startswith("tok_"):
        if not is_valid_anonymous_session_id(token):
            return jsonify({"error": "invalid anonymous session id"}), 400
        # Anonymous UUID sessions — no server-side issuance record needed.
        return jsonify({"ok": True, "exists": True})
    return jsonify({"ok": True, "exists": session_token_exists(token)})


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


@session_bp.route("/session/migrate", methods=["POST"])
def session_migrate():
    """Migrate all runs and snapshots from one session ID to another.

    Security: ``from_session_id`` in the request body must match the caller's
    ``X-Session-ID`` header.  This prevents a client from migrating a session
    it does not own.  ``to_session_id`` must be a server-issued token when it
    carries a ``tok_`` prefix — migrating to an unissued token is rejected so a
    typo cannot silently strand run history on an unreachable identity.
    """
    data = request.get_json(silent=True) or {}
    from_session_id = str(data.get("from_session_id") or "").strip()
    to_session_id = str(data.get("to_session_id") or "").strip()

    if not from_session_id or not to_session_id:
        return jsonify({"error": "from_session_id and to_session_id are required"}), 400

    if from_session_id == to_session_id:
        return jsonify({"error": "from_session_id and to_session_id must be different"}), 400

    current_session_id = get_session_id()
    if from_session_id != current_session_id:
        log.warning("SESSION_MIGRATE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": "from_session_id does not match X-Session-ID",
            "from_session_kind": _session_kind(from_session_id),
            "to_session_kind": _session_kind(to_session_id),
        })
        return jsonify({"error": "from_session_id must match your current session"}), 403

    # Reject migration to a tok_ token that was never issued by this server.
    if to_session_id.startswith("tok_"):
        if not session_token_exists(to_session_id):
            log.warning("SESSION_MIGRATE_DENIED", extra={
                "ip": get_client_ip(),
                "session": get_log_session_id(current_session_id),
                "reason": "unknown_destination_token",
                "from_session_kind": _session_kind(from_session_id),
                "to_session_kind": _session_kind(to_session_id),
            })
            return jsonify({"error": "destination token is not a known issued token"}), 400

    if active_execution_count_for_actor(from_session_id):
        return jsonify({
            "error": "active_workflow_execution",
            "message": "Cancel or wait for the active workflow execution before migrating this session.",
        }), 409

    try:
        workspace_migration = migrate_session_workspace(from_session_id, to_session_id)
    except InvalidWorkspacePath as exc:
        log.warning("SESSION_MIGRATE_WORKSPACE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": str(exc),
            "from_session_kind": _session_kind(from_session_id),
            "to_session_kind": _session_kind(to_session_id),
        })
        return jsonify({"error": str(exc)}), 400

    workspace_counts = {
        "migrated_workspace_files": workspace_migration.migrated_files,
        "skipped_workspace_files": workspace_migration.skipped_files,
        "migrated_workspace_directories": workspace_migration.migrated_directories,
        "skipped_workspace_directories": workspace_migration.skipped_directories,
    }
    migration_counts = migrate_session_records(
        from_session_id,
        to_session_id,
        migrated_workspace_file_paths=getattr(workspace_migration, "migrated_file_paths", ()),
        extra_counts=workspace_counts,
        audit_target_id=_session_label(to_session_id),
        audit_details={
            "source": "browser",
            "from_state": _session_kind(from_session_id),
            "to_state": _session_kind(to_session_id),
            **_session_identity_details(from_session_id, prefix="source"),
            **_session_identity_details(to_session_id, prefix="destination"),
        },
        audit_fields=_session_audit_fields(current_session_id),
    )

    log.info("SESSION_MIGRATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(current_session_id),
        "from_session_kind": _session_kind(from_session_id),
        "to_session_kind": _session_kind(to_session_id),
        **migration_counts,
    })
    return jsonify({
        "ok": True,
        **migration_counts,
    })


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
        workflow = create_user_workflow(
            session_id,
            request.get_json(silent=True) or {},
            team_id=scope.team_id if scope else "",
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
            **route_audit_fields(session_id, request, scope),
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
        workflow = update_user_workflow(
            session_id,
            workflow_id,
            request.get_json(silent=True) or {},
            team_id=scope.team_id if scope else "",
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
            **route_audit_fields(session_id, request, scope),
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


@session_bp.route("/session/run-count")
def session_run_count():
    """Return the total run count for the current session, uncapped.

    The pre-migration confirmation prompt needs the true row count so the user
    is not shown the `history_panel_limit` cap that `/history` applies to its
    page of runs. The actual migration UPDATE on `/session/migrate` is already
    uncapped; this endpoint just keeps the confirmation honest.
    """
    session_id = get_session_id()
    counts = session_counts(session_id)
    count = counts["count"]
    workflow_count = counts["workflow_count"]
    recent_value_count = counts["recent_value_count"]
    workspace_files = 0
    try:
        workspace_files = workspace_usage(session_id).file_count
    except Exception as exc:
        log.warning("SESSION_ROUTE_FAILED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "route": "session_run_count",
            "error": str(exc),
        })
        workspace_files = 0
    log.debug("SESSION_RUN_COUNT_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": count,
        "workspace_files": workspace_files,
        "workflow_count": workflow_count,
        "recent_value_count": recent_value_count,
    })
    return jsonify({
        "count": count,
        "workspace_files": workspace_files,
        "workflow_count": workflow_count,
        "recent_value_count": recent_value_count,
    })


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
