# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 route for exact Atlas entity lookup."""

from flask import jsonify

from blueprints import api_v1 as api_routes
from services.atlas.lookup_resolve import AtlasLookupError, resolve_entity_lookup_for_owner
from services.projects.contracts import ProjectWorkspaceError


@api_routes.api_v1_bp.route("/atlas/lookup", methods=["POST"])
@api_routes.require_api_auth
def api_atlas_entity_lookup():
    owner_scope = api_routes._api_request_scope()
    payload = api_routes._json_body()
    try:
        result = resolve_entity_lookup_for_owner(
            api_routes._require_session_id(),
            payload.get("value"),
            requested_type=payload.get("mode") or "auto",
            team_id=owner_scope.team_id,
            project_id=payload.get("project_id") or "",
        )
    except AtlasLookupError as exc:
        return api_routes._api_json_error(exc.code, exc.message, 400)
    except ProjectWorkspaceError as exc:
        return api_routes._api_json_error("invalid_request", str(exc), 400)
    return jsonify(result)
