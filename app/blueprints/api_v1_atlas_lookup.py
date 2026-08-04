# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 route for exact Atlas entity lookup."""

from blueprints import api_v1 as api_routes
from services.atlas import route_observability as lookup


@lookup.route(api_routes.api_v1_bp, event="API_ATLAS_LOOKUP_COMPLETED", surface="api_v1")
@api_routes.require_api_auth
def api_atlas_entity_lookup():
    owner_scope = api_routes._api_request_scope()
    payload = api_routes._json_body()
    if set(payload) - {"mode", "value", "project_id"}:
        return api_routes._api_json_error("invalid_request", "Request body contains unsupported fields.", 400)
    try:
        result = lookup.resolve_entity_lookup_for_owner(
            api_routes._require_session_id(),
            payload.get("value"),
            requested_type=payload.get("mode") or "auto",
            team_id=owner_scope.team_id,
            project_id=payload.get("project_id") or "",
        )
    except lookup.AtlasLookupError as exc:
        return api_routes._api_json_error(exc.code, exc.message, 400)
    except lookup.ProjectWorkspaceError as exc:
        return api_routes._api_json_error("invalid_project", str(exc), 400)
    return result
