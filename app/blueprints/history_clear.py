# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Filtered History clear preview and mutation routes."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.audit.context import route_audit_fields
from services.history.queries import clear_history_runs
from services.history.run_metadata import normalize_history_filter_text
from services.history.selections import matching_history_runs
from services.runs.structured_filters import structured_filters_from_params
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScopeError, current_request_scope, scope_error_payload

history_clear_bp = Blueprint("history_clear", __name__)
log = logging.getLogger("shell")

_HISTORY_TYPES = frozenset({"all", "runs", "runs_builtin", "runs_external", "snapshots"})


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _selection(session_id, owner_scope):
    query, structured_filters = structured_filters_from_params(
        request.args,
        query=normalize_history_filter_text(request.args.get("q")),
    )
    type_filter = normalize_history_filter_text(request.args.get("type")).lower() or "all"
    if type_filter not in _HISTORY_TYPES:
        type_filter = "all"
    return matching_history_runs(
        session_id=session_id,
        owner_scope=owner_scope,
        query=query,
        structured_filters=structured_filters,
        command_root=normalize_history_filter_text(request.args.get("command_root")).lower(),
        exit_code_filter=normalize_history_filter_text(request.args.get("exit_code")).lower(),
        date_range=normalize_history_filter_text(request.args.get("date_range")).lower(),
        type_filter=type_filter,
        project_id=normalize_history_filter_text(request.args.get("project_id")),
        starred_only=_truthy(request.args.get("starred_only")),
        scope=normalize_history_filter_text(request.args.get("scope")).lower(),
    )


def _request_scope():
    session_id = get_session_id()
    if not session_id:
        return None, None, (jsonify({"error": "session_required"}), 401)
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return None, None, (jsonify(payload), status)
    if owner_scope.is_team:
        try:
            require_capability(str((owner_scope.member or {}).get("role") or ""), Capability.MANAGE_HISTORY)
        except TeamPermissionDenied as exc:
            return None, None, (
                jsonify({"error": "team_forbidden", "message": str(exc)}),
                403,
            )
    return session_id, owner_scope, None


@history_clear_bp.route("/history/delete-preview")
def history_delete_preview():
    """Count the runs affected by the current History filters."""
    session_id, owner_scope, error_response = _request_scope()
    if error_response is not None:
        return error_response
    assert session_id is not None
    assert owner_scope is not None
    selection = _selection(session_id, owner_scope)
    return jsonify({
        "ok": True,
        "total_count": selection.total_count,
        "non_starred_count": selection.non_starred_count,
    })


@history_clear_bp.route("/history", methods=["DELETE"])
def clear_history():
    """Delete runs selected by the current History filters."""
    session_id, owner_scope, error_response = _request_scope()
    if error_response is not None:
        return error_response
    assert session_id is not None
    assert owner_scope is not None
    selection = _selection(session_id, owner_scope)
    exclude_starred = _truthy(request.args.get("exclude_starred"))
    selected_ids = selection.non_starred_run_ids if exclude_starred else selection.run_ids
    deleted_count = clear_history_runs(
        owner_scope=owner_scope,
        run_ids=selected_ids,
        audit_fields=route_audit_fields(session_id, request, owner_scope),
    )
    log.info("HISTORY_CLEARED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": deleted_count,
        "filtered": bool(request.query_string),
        "excluded_starred": exclude_starred,
    })
    return jsonify({"ok": True, "deleted_count": deleted_count})
