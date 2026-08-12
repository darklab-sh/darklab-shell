# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser reads for typed evidence saved with a run."""

from flask import jsonify, request

from blueprints import history as history_routes
from core.helpers import get_session_id
from services.assessments.nmap_service_evidence_read import list_nmap_service_evidence
from services.projects.utils import normalize_page_limit, normalize_page_offset
from services.teams.request_scope import (
    RequestScopeError,
    current_request_scope,
    scope_error_payload,
)


@history_routes.history_bp.route("/runs/<run_id>/service-evidence")
def history_run_service_evidence(run_id):
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    try:
        owner_scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    page = list_nmap_service_evidence(
        session_id,
        run_id,
        team_id=owner_scope.team_id,
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
    )
    if page is None:
        return jsonify({"error": "run not found"}), 404
    return jsonify(page)
