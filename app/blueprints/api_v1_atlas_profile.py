# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 Atlas entity profile route."""

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from services.atlas.lookup import atlas_entity_for_owner
from services.projects.contracts import ProjectWorkspaceError
from services.projects.utils import normalize_page_offset


@api_routes.api_v1_bp.route("/atlas/entities/<entity_id>")
@api_routes.require_api_auth
def api_atlas_entity(entity_id):
    owner_scope = api_routes._api_request_scope()
    offset = lambda name: normalize_page_offset(request.args.get(name))  # noqa: E731
    try:
        detail = atlas_entity_for_owner(
            api_routes._require_session_id(),
            entity_id,
            team_id=owner_scope.team_id,
            project_id=request.args.get("project_id") or "",
            runs_offset=offset("runs_offset"),
            findings_offset=offset("findings_offset"),
            finding_bucket=request.args.get("finding_bucket") or "direct",
            related_urls_offset=offset("related_urls_offset"),
            related_ports_offset=offset("related_ports_offset"),
        )
    except (ProjectWorkspaceError, ValueError) as exc:
        return api_routes._api_json_error("invalid_request", str(exc), 400)
    if detail is None:
        return api_routes._api_json_error("not_found", "Atlas entity not found.", 404)
    return jsonify(detail)
