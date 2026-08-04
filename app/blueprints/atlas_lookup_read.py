# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only browser route for exact Atlas entity lookup."""

from flask import jsonify, request

from blueprints import atlas as atlas_routes
from services.atlas import route_observability as lookup


@lookup.route(atlas_routes.atlas_bp, event="ATLAS_LOOKUP_COMPLETED", surface="browser")
def atlas_entity_lookup():
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_body", "message": "Request body must be a JSON object."}), 400
    try:
        result = atlas_routes.run_atlas_read(lambda conn: lookup.resolve_entity_lookup(
            conn,
            session_id,
            payload.get("value"),
            requested_type=payload.get("mode") or "auto",
            team_id=owner_scope.team_id,
            project_id=payload.get("project_id") or "",
        ))
    except lookup.AtlasLookupError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), 400
    except lookup.ProjectWorkspaceError as exc:
        return jsonify({"error": "invalid_project", "message": str(exc)}), 400
    return jsonify(result)
