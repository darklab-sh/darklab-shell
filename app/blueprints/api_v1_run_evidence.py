# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 reads for typed evidence saved with a run."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from services.assessments.nmap_service_evidence_read import list_nmap_service_evidence


@api_routes.api_v1_bp.route("/runs/<run_id>/service-evidence")
@api_routes.require_api_auth
def api_run_service_evidence(run_id):
    owner_scope = api_routes._api_request_scope()
    page = list_nmap_service_evidence(
        api_routes._require_session_id(),
        run_id,
        team_id=owner_scope.team_id,
        limit=api_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=100),
        offset=api_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
    )
    if page is None:
        return api_routes._api_json_error("not_found", "Run not found.", 404)
    return jsonify(page)
